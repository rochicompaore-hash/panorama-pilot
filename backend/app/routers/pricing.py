"""Pricelists + Price Rules + Products routers (M3.2)."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from app.db import get_db
from app.deps import require_permission, get_client_ip, get_permission_keys_for_user
from app.models import new_id
from app.models_quote import Pricelist
from app.models_pricing import (
    PricelistCreate, PricelistUpdate,
    PriceRuleV2, PriceRuleV2Create, PriceRuleV2Update,
    ConfiguratorPreviewRequest, ConfiguratorPreviewResponse,
    ProductCatalog, ProductCatalogCreate, ProductCatalogUpdate,
    ForceOverrideRequest,
)
from app.mongo_utils import to_mongo, from_mongo
from app.services.audit import record_audit
from app.services.formula import validate_formula
from app.services.pricing_v2 import compute_preview
from app.services.concurrency import update_with_version, get_if_match_version, user_has_permission

router = APIRouter(tags=["pricing"])


# ---------- Pricelists ----------
@router.get("/pricelists")
async def list_pricelists(user: dict = Depends(require_permission("pricelists.view"))):
    db = get_db()
    docs = await db.pricelists.find({"tenant_id": user["tenant_id"], "deleted_at": None}).sort("priority", 1).to_list(200)
    return {"items": [from_mongo(d) for d in docs]}


@router.get("/pricelists/{pid}")
async def get_pricelist(pid: str, user: dict = Depends(require_permission("pricelists.view"))):
    db = get_db()
    d = await db.pricelists.find_one({"_id": pid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not d: raise HTTPException(status_code=404, detail="Listino non trovato")
    return from_mongo(d)


@router.post("/pricelists")
async def create_pricelist(body: PricelistCreate, request: Request, user: dict = Depends(require_permission("pricelists.manage"))):
    db = get_db()
    p = Pricelist(
        id=new_id(), tenant_id=user["tenant_id"],
        name=body.name, description=body.description, currency=body.currency,
        valid_from=body.valid_from, valid_to=body.valid_to,
        priority=body.priority, is_default=body.is_default,
        created_by=user["id"], updated_by=user["id"],
    )
    doc = to_mongo(p.model_dump(by_alias=True))
    await db.pricelists.insert_one(doc)
    if body.is_default:
        await db.pricelists.update_many({"tenant_id": user["tenant_id"], "_id": {"$ne": p.id}}, {"$set": {"is_default": False}})
    await record_audit(action="pricelists.create", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="pricelist", entity_id=p.id, after=body.model_dump())
    return from_mongo(await db.pricelists.find_one({"_id": p.id}))


@router.patch("/pricelists/{pid}")
async def update_pricelist(
    pid: str, body: PricelistUpdate, request: Request,
    expected_version: Optional[int] = Depends(get_if_match_version),
    user: dict = Depends(require_permission("pricelists.manage")),
):
    payload = body.model_dump(exclude_unset=True)
    updated = await update_with_version(
        collection="pricelists", entity_id=pid, tenant_id=user["tenant_id"],
        entity_type="pricelist", expected_version=expected_version,
        set_fields=payload, user=user, request=request,
    )
    if body.is_default:
        db = get_db()
        await db.pricelists.update_many({"tenant_id": user["tenant_id"], "_id": {"$ne": pid}}, {"$set": {"is_default": False}})
    await record_audit(action="pricelists.update", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="pricelist", entity_id=pid, after=payload)
    return updated


@router.delete("/pricelists/{pid}")
async def delete_pricelist(pid: str, request: Request, user: dict = Depends(require_permission("pricelists.manage"))):
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    r = await db.pricelists.update_one({"_id": pid, "tenant_id": user["tenant_id"]}, {"$set": {"deleted_at": now, "updated_at": now, "updated_by": user["id"]}, "$inc": {"version": 1}})
    if r.modified_count == 0: raise HTTPException(status_code=404, detail="Listino non trovato")
    await record_audit(action="pricelists.delete", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="pricelist", entity_id=pid)
    return {"ok": True}


# ---------- Price rules v2 ----------
@router.get("/price-rules")
async def list_rules(
    pricelist_id: Optional[str] = None,
    category: Optional[str] = None,
    active: Optional[bool] = None,
    user: dict = Depends(require_permission("pricelists.view")),
):
    db = get_db()
    q: dict = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if pricelist_id: q["pricelist_id"] = pricelist_id
    if category: q["category"] = category
    if active is not None: q["active"] = active
    docs = await db.price_rules.find(q).sort([("priority", 1), ("code", 1)]).to_list(1000)
    return {"items": [from_mongo(d) for d in docs]}


@router.get("/price-rules/{rid}")
async def get_rule(rid: str, user: dict = Depends(require_permission("pricelists.view"))):
    db = get_db()
    d = await db.price_rules.find_one({"_id": rid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not d: raise HTTPException(status_code=404, detail="Regola non trovata")
    return from_mongo(d)


@router.post("/price-rules/validate")
async def validate_rule_formula(body: dict, user: dict = Depends(require_permission("pricelists.view"))):
    ok, err = validate_formula(body.get("formula") or "")
    return {"ok": ok, "error": err}


@router.post("/price-rules")
async def create_rule(body: PriceRuleV2Create, request: Request, user: dict = Depends(require_permission("pricelists.manage"))):
    db = get_db()
    ok, err = validate_formula(body.formula)
    if not ok: raise HTTPException(status_code=400, detail=f"Formula non valida: {err}")
    # Validate pricelist exists
    pl = await db.pricelists.find_one({"_id": body.pricelist_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not pl: raise HTTPException(status_code=400, detail="Listino non valido")
    r = PriceRuleV2(
        id=new_id(), tenant_id=user["tenant_id"],
        pricelist_id=body.pricelist_id, code=body.code, name=body.name,
        description=body.description, category=body.category,
        conditions=body.conditions, formula=body.formula, effect_type=body.effect_type,
        effect_target=body.effect_target, priority=body.priority,
        cumulative=body.cumulative, active=body.active,
        created_by=user["id"], updated_by=user["id"],
    )
    await db.price_rules.insert_one(to_mongo(r.model_dump(by_alias=True)))
    await record_audit(action="price_rules.create", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="price_rule", entity_id=r.id, after=body.model_dump())
    return from_mongo(await db.price_rules.find_one({"_id": r.id}))


@router.patch("/price-rules/{rid}")
async def update_rule(
    rid: str, body: PriceRuleV2Update, request: Request,
    expected_version: Optional[int] = Depends(get_if_match_version),
    user: dict = Depends(require_permission("pricelists.manage")),
):
    payload = body.model_dump(exclude_unset=True)
    if "formula" in payload and payload["formula"] is not None:
        ok, err = validate_formula(payload["formula"])
        if not ok: raise HTTPException(status_code=400, detail=f"Formula non valida: {err}")
    if "conditions" in payload and payload["conditions"] is not None:
        payload["conditions"] = [c if isinstance(c, dict) else c.model_dump() for c in payload["conditions"]]
    updated = await update_with_version(
        collection="price_rules", entity_id=rid, tenant_id=user["tenant_id"],
        entity_type="price_rule", expected_version=expected_version,
        set_fields=payload, user=user, request=request,
    )
    await record_audit(action="price_rules.update", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="price_rule", entity_id=rid, after=payload)
    return updated


@router.delete("/price-rules/{rid}")
async def delete_rule(rid: str, request: Request, user: dict = Depends(require_permission("pricelists.manage"))):
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    r = await db.price_rules.update_one({"_id": rid, "tenant_id": user["tenant_id"]}, {"$set": {"deleted_at": now, "updated_at": now, "updated_by": user["id"]}, "$inc": {"version": 1}})
    if r.modified_count == 0: raise HTTPException(status_code=404, detail="Regola non trovata")
    await record_audit(action="price_rules.delete", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="price_rule", entity_id=rid)
    return {"ok": True}


# ---------- Products (Catalog) ----------
@router.get("/products")
async def list_products(
    category: Optional[str] = None, active: Optional[bool] = None,
    user: dict = Depends(require_permission("products.view")),
):
    db = get_db()
    q: dict = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if category: q["category"] = category
    if active is not None: q["active"] = active
    docs = await db.products.find(q).sort([("order_index", 1), ("name", 1)]).to_list(500)
    return {"items": [from_mongo(d) for d in docs]}


@router.get("/products/{pid}")
async def get_product(pid: str, user: dict = Depends(require_permission("products.view"))):
    db = get_db()
    d = await db.products.find_one({"_id": pid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not d: raise HTTPException(status_code=404, detail="Prodotto non trovato")
    return from_mongo(d)


@router.post("/products")
async def create_product(body: ProductCatalogCreate, request: Request, user: dict = Depends(require_permission("products.manage"))):
    db = get_db()
    if await db.products.find_one({"tenant_id": user["tenant_id"], "key": body.key, "deleted_at": None}):
        raise HTTPException(status_code=400, detail="Chiave prodotto già esistente")
    p = ProductCatalog(
        id=new_id(), tenant_id=user["tenant_id"],
        key=body.key, name=body.name, category=body.category,
        description=body.description, base_price=body.base_price, base_type=body.base_type,
        min_billable_sqm=body.min_billable_sqm, default_config=body.default_config,
        schema=body.schema, order_index=body.order_index,
        created_by=user["id"], updated_by=user["id"],
    )
    await db.products.insert_one(to_mongo(p.model_dump(by_alias=True)))
    await record_audit(action="products.create", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="product", entity_id=p.id, after=body.model_dump())
    return from_mongo(await db.products.find_one({"_id": p.id}))


@router.patch("/products/{pid}")
async def update_product(
    pid: str, body: ProductCatalogUpdate, request: Request,
    expected_version: Optional[int] = Depends(get_if_match_version),
    user: dict = Depends(require_permission("products.manage")),
):
    payload = body.model_dump(exclude_unset=True)
    updated = await update_with_version(
        collection="products", entity_id=pid, tenant_id=user["tenant_id"],
        entity_type="product", expected_version=expected_version,
        set_fields=payload, user=user, request=request,
    )
    await record_audit(action="products.update", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="product", entity_id=pid, after=payload)
    return updated


@router.delete("/products/{pid}")
async def delete_product(pid: str, request: Request, user: dict = Depends(require_permission("products.manage"))):
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    r = await db.products.update_one({"_id": pid, "tenant_id": user["tenant_id"]}, {"$set": {"deleted_at": now, "updated_at": now, "updated_by": user["id"]}, "$inc": {"version": 1}})
    if r.modified_count == 0: raise HTTPException(status_code=404, detail="Prodotto non trovato")
    return {"ok": True}


# ---------- Live pricing preview ----------
@router.post("/configurator/preview", response_model=ConfiguratorPreviewResponse)
async def preview_price(body: ConfiguratorPreviewRequest, user: dict = Depends(require_permission("quotes.view"))):
    db = get_db()
    # Resolve product
    product = await db.products.find_one({
        "tenant_id": user["tenant_id"], "key": body.product_key, "deleted_at": None,
    })
    # Resolve pricelist (default if not provided)
    pl_query: dict = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if body.pricelist_id:
        pl_query["_id"] = body.pricelist_id
    else:
        pl_query["is_default"] = True
    pl = await db.pricelists.find_one(pl_query)
    if not pl and not body.pricelist_id:
        # Also try highest priority
        pl = await db.pricelists.find_one({"tenant_id": user["tenant_id"], "deleted_at": None}, sort=[("priority", 1)])
    pricelist_id = pl.get("_id") if pl else None
    pricelist_name = pl.get("name") if pl else None
    rules = []
    if pl:
        rules = await db.price_rules.find({
            "tenant_id": user["tenant_id"], "pricelist_id": pl["_id"], "deleted_at": None, "active": True,
        }).sort("priority", 1).to_list(1000)

    perms = set(await get_permission_keys_for_user(user))
    can_see_costs = user.get("is_superadmin") or "*" in perms or "quotes.view_costs" in perms or "quotes.view_margins" in perms

    result = compute_preview(
        product=from_mongo(product) if product else None,
        rules=[from_mongo(r) for r in rules],
        product_config=body.product_config or {},
        width_mm=body.width_mm, height_mm=body.height_mm,
        quantity=body.quantity,
        discount_pct=body.discount_pct, discount_amount=body.discount_amount,
        vat_rate=body.vat_rate, internal_cost=body.internal_cost,
        can_see_costs=can_see_costs,
        pricelist_id=pricelist_id, pricelist_name=pricelist_name,
        request_id=body.request_id,
    )
    return result
