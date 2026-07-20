"""Catalog admin area — new endpoints for Opzione A.

Non-invasive: does NOT modify existing pricing / products routers. Adds:

    GET/PATCH /api/catalog/production-config          — tenant-wide (pricing_admin.manage)
    GET       /api/catalog/code-mappings              — list (catalog.view)
    POST      /api/catalog/code-mappings              — create tenant override (catalog.manage)
    PATCH     /api/catalog/code-mappings/{id}         — update (catalog.manage)
    POST      /api/catalog/products/{id}/components   — set component associations (catalog.manage)
    POST      /api/catalog/products/{id}/lifecycle    — draft/validated/active/superseded/archived
    POST      /api/catalog/products/{id}/simulate     — simulate 1-anta window (catalog.view)
"""
from __future__ import annotations
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.db import get_db
from app.deps import require_permission, get_client_ip, get_current_user
from app.mongo_utils import from_mongo, to_mongo
from app.services.audit import record_audit
from app.models_catalog import (
    ProductComponentAssoc, ProductionConfigUpdate,
    CatalogCodeMappingCreate, CatalogCodeMappingUpdate,
    ProductSimulateRequest,
    ALL_COMPONENT_CATEGORIES,
)
from app.services.catalog_service import (
    get_production_config, upsert_production_config,
    load_product, get_component_code,
    resolve_component_prices, get_color_is_premium,
)
from app.services.recipes import (
    compute_finestra_1a, FinestraAInput, FINESTRA_1A_CODE,
)
from app.services.recipes.finestra_1a import display_dict as _display_finestra_1a


router = APIRouter(prefix="/catalog", tags=["catalog"])


# --------------------------------------------------------------------
# 1. Production config
# --------------------------------------------------------------------
@router.get("/production-config")
async def get_prod_cfg(user: dict = Depends(require_permission("pricing_admin.view"))):
    return await get_production_config(user["tenant_id"])


@router.patch("/production-config")
async def patch_prod_cfg(body: ProductionConfigUpdate, request: Request,
                          user: dict = Depends(require_permission("pricing_admin.manage"))):
    patch = body.model_dump(exclude_unset=True)
    result = await upsert_production_config(user["tenant_id"], patch, user["id"])
    await record_audit(
        action="catalog.production_config.update",
        tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"],
        ip=get_client_ip(request),
        entity_type="production_config", entity_id=result.get("_id") or result.get("id"),
        after=patch,
    )
    return result


# --------------------------------------------------------------------
# 2. Code auto-mapping table
# --------------------------------------------------------------------
@router.get("/code-mappings")
async def list_code_mappings(user: dict = Depends(require_permission("catalog.view"))):
    db = get_db()
    docs = await db.catalog_code_mappings.find({
        "$or": [
            {"tenant_id": user["tenant_id"], "deleted_at": None},
            {"tenant_id": None, "is_system": True, "deleted_at": None},
        ],
    }).sort("code", 1).to_list(500)
    return {"items": [from_mongo(d) for d in docs]}


@router.post("/code-mappings")
async def create_code_mapping(body: CatalogCodeMappingCreate, request: Request,
                                user: dict = Depends(require_permission("catalog.manage"))):
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    from app.models import new_id
    doc = {
        "_id": new_id(), "tenant_id": user["tenant_id"],
        "code": body.code, "component_category": body.component_category,
        "material": body.material, "description": body.description,
        "is_system": False,
        "created_at": now, "updated_at": now,
        "created_by": user["id"], "updated_by": user["id"],
        "deleted_at": None, "version": 1,
    }
    await db.catalog_code_mappings.insert_one(doc)
    await record_audit(
        action="catalog.code_mapping.create", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="code_mapping", entity_id=doc["_id"], after=body.model_dump(),
    )
    return from_mongo(doc)


@router.patch("/code-mappings/{mid}")
async def update_code_mapping(mid: str, body: CatalogCodeMappingUpdate, request: Request,
                                user: dict = Depends(require_permission("catalog.manage"))):
    db = get_db()
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    patch["updated_by"] = user["id"]
    r = await db.catalog_code_mappings.update_one(
        {"_id": mid, "tenant_id": user["tenant_id"], "deleted_at": None, "is_system": False},
        {"$set": patch, "$inc": {"version": 1}},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Mapping non trovato o di sistema (non modificabile)")
    await record_audit(
        action="catalog.code_mapping.update", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="code_mapping", entity_id=mid, after=patch,
    )
    return from_mongo(await db.catalog_code_mappings.find_one({"_id": mid}))


# --------------------------------------------------------------------
# 3. Product component associations & lifecycle
# --------------------------------------------------------------------
class SetComponentsRequest(BaseModel):
    components: List[ProductComponentAssoc] = Field(default_factory=list)


class LifecycleRequest(BaseModel):
    lifecycle_status: str  # draft | validated | active | superseded | archived
    reason: Optional[str] = None


@router.get("/products/{pid}")
async def get_catalog_product(pid: str, user: dict = Depends(require_permission("catalog.view"))):
    doc = await load_product(user["tenant_id"], product_id=pid)
    if not doc:
        raise HTTPException(404, "Prodotto non trovato")
    return doc


@router.post("/products/{pid}/components")
async def set_product_components(pid: str, body: SetComponentsRequest, request: Request,
                                    user: dict = Depends(require_permission("catalog.manage"))):
    db = get_db()
    # Validate categories
    for c in body.components:
        if c.category not in ALL_COMPONENT_CATEGORIES:
            raise HTTPException(400, f"Categoria non valida: {c.category}")
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "components": [c.model_dump() for c in body.components],
        "updated_at": now, "updated_by": user["id"],
    }
    r = await db.products.update_one(
        {"_id": pid, "tenant_id": user["tenant_id"], "deleted_at": None},
        {"$set": payload, "$inc": {"version": 1}},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Prodotto non trovato")
    await record_audit(
        action="catalog.product.set_components", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="product", entity_id=pid,
        after={"n_components": len(body.components)},
    )
    return from_mongo(await db.products.find_one({"_id": pid}))


VALID_LIFECYCLES = {"draft", "validated", "active", "superseded", "archived"}


@router.post("/products/{pid}/lifecycle")
async def set_product_lifecycle(pid: str, body: LifecycleRequest, request: Request,
                                 user: dict = Depends(require_permission("catalog.publish"))):
    if body.lifecycle_status not in VALID_LIFECYCLES:
        raise HTTPException(400, f"Stato non valido. Ammessi: {sorted(VALID_LIFECYCLES)}")
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    r = await db.products.update_one(
        {"_id": pid, "tenant_id": user["tenant_id"], "deleted_at": None},
        {"$set": {
            "lifecycle_status": body.lifecycle_status,
            "lifecycle_reason": body.reason,
            "lifecycle_updated_at": now,
            "lifecycle_updated_by": user["id"],
            "updated_at": now,
        }, "$inc": {"version": 1}},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Prodotto non trovato")
    await record_audit(
        action=f"catalog.product.lifecycle.{body.lifecycle_status}",
        tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="product", entity_id=pid,
        after={"lifecycle_status": body.lifecycle_status, "reason": body.reason},
    )
    return from_mongo(await db.products.find_one({"_id": pid}))


# --------------------------------------------------------------------
# 4. Simulate — the operational tool for tomorrow's collaudo
# --------------------------------------------------------------------
async def _load_recipe_inputs(user: dict, body: ProductSimulateRequest) -> FinestraAInput:
    """Assemble a FinestraAInput from product+colour+pricelist+config."""
    tenant = user["tenant_id"]
    product = await load_product(tenant, body.product_id, body.product_key)
    if not product:
        raise HTTPException(404, "Prodotto non trovato")

    codes = {
        "frame":                 get_component_code(product, "telaio", applies_to="finestra_1a"),
        "sash":                  get_component_code(product, "anta_standard", applies_to="finestra_1a"),
        "glazing_bead":          get_component_code(product, "fermavetro", applies_to="finestra_1a"),
        "reinforcement_frame":   get_component_code(product, "rinforzo_telaio", applies_to="finestra_1a"),
        "reinforcement_sash":    get_component_code(product, "rinforzo_anta", applies_to="finestra_1a"),
    }
    prices, pricelist = await resolve_component_prices(
        tenant, codes, body.color_code,
    )

    cfg = await get_production_config(tenant)
    is_premium = body.is_color_premium
    if not is_premium:
        db_flag = await get_color_is_premium(tenant, body.color_code)
        if db_flag is True:
            is_premium = True

    def dec(v: Any) -> Optional[Decimal]:
        return Decimal(str(v)) if v is not None else None

    hardware_price = body.hardware_kit_price
    default_kit = product.get("default_hardware_kit") or {}
    if hardware_price is None:
        hardware_price = default_kit.get("price")

    other_cost = body.other_components_cost
    other_declared_zero = body.other_components_declared_zero
    if other_cost is None:
        # Product-level default?
        prod_other = product.get("default_other_components_cost")
        if prod_other is not None:
            other_cost = prod_other

    glass_price = body.glass_price_per_sqm or cfg.get("default_glass_price_per_sqm")
    glass_min = body.glass_min_sqm or cfg.get("default_glass_min_sqm")

    return FinestraAInput(
        L=body.width_mm, H=body.height_mm, S=body.weld_allowance_mm,
        P_5103=dec(prices.get("frame")),
        P_12130=dec(prices.get("sash")),
        P_RINFORZO_TELAIO=dec(prices.get("reinforcement_frame")),
        P_RINFORZO_ANTA=dec(prices.get("reinforcement_sash")),
        P_FERMAVETRO=dec(prices.get("glazing_bead")),
        P_VETRO=dec(glass_price),
        MQ_MINIMO_VETRO=dec(glass_min),
        P_FERRAMENTA=dec(hardware_price),
        C_ALTRI=dec(other_cost),
        C_ALTRI_declared_zero=other_declared_zero,
        COSTO_ORARIO=dec(body.override_hourly_cost or cfg.get("hourly_cost")),
        TEMPO_PRODUZIONE_MINUTI=dec(body.override_production_time_min
                                     or cfg.get("production_time_default_minutes")),
        MARGINE_PERCENTUALE=dec(body.override_margin_pct or cfg.get("default_margin_pct")),
        SCONTO_AUTORIZZATO=Decimal(str(body.discount_amount)),
        is_color_premium=is_premium,
        premium_pct=dec(cfg.get("premium_pvc_surcharge_pct")) or Decimal("6"),
        color_code=body.color_code,
        product_id=product.get("_id") or product.get("id"),
        product_key=product.get("key"),
        pricelist_version=(pricelist or {}).get("version") if pricelist else None,
    )


# Which fields are considered "internal" and hidden from users without view_costs
INTERNAL_FIELDS = {
    "unit_prices", "component_costs", "materials_cost", "premium_surcharge",
    "labor_cost", "production_cost", "margin_pct",
}


def _redact_costs(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Remove internal cost fields — keep only sale price + status."""
    out = {k: v for k, v in payload.items() if k not in INTERNAL_FIELDS}
    return out


@router.post("/products/{pid}/simulate")
async def simulate_product(pid: str, body: ProductSimulateRequest, request: Request,
                            user: dict = Depends(get_current_user)):
    """Run the recipe engine. Everyone with catalog.view can see the result,
    but internal costs are visible ONLY to users with pricing_admin.view_costs.
    """
    perms = user.get("permission_keys") or []
    is_super = user.get("is_superadmin") or user.get("is_platform_owner") or "*" in perms
    if not is_super and "catalog.view" not in perms and "products.view" not in perms:
        raise HTTPException(403, "Permesso negato — catalog.view / products.view")
    body.product_id = pid
    inputs = await _load_recipe_inputs(user, body)

    # Only finestra_1a recipe supported in this iteration
    if body.quote_line_type != "finestra_1a":
        raise HTTPException(400, f"Ricetta {body.quote_line_type} non ancora implementata")

    result = compute_finestra_1a(inputs)
    payload = _display_finestra_1a(result)
    payload["product_id"] = pid
    payload["color_is_premium"] = inputs.is_color_premium

    can_view_costs = is_super or "pricing_admin.view_costs" in perms or "quotes.view_costs" in perms
    if not can_view_costs:
        payload = _redact_costs(payload)
        payload["_costs_hidden"] = True
    else:
        payload["_costs_hidden"] = False
    return payload
