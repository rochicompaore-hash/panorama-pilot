"""Router — Product Categories (Multi-Category V1).

CRUD data-driven per le categorie commerciali del preventivatore.
Il frontend NON contiene alcuna lista hardcoded — la ottiene da questi endpoint.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models import new_id
from app.models_multi_category import (
    ProductCategory,
    ProductCategoryCreate,
    ProductCategoryUpdate,
)
from app.mongo_utils import to_mongo, from_mongo
from app.services.audit import record_audit


router = APIRouter(prefix="/product-categories", tags=["multi-category-catalog"])


@router.get("")
async def list_categories(
    active: Optional[bool] = None,
    user: dict = Depends(require_permission("products.view")),
):
    db = get_db()
    q: dict = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if active is not None:
        q["active"] = active
    docs = await db.product_categories.find(q).sort([("display_order", 1), ("label", 1)]).to_list(200)
    return {"items": [from_mongo(d) for d in docs]}


@router.get("/{cid}")
async def get_category(cid: str, user: dict = Depends(require_permission("products.view"))):
    db = get_db()
    d = await db.product_categories.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not d:
        raise HTTPException(status_code=404, detail="Categoria non trovata")
    return from_mongo(d)


@router.post("")
async def create_category(
    body: ProductCategoryCreate,
    request: Request,
    user: dict = Depends(require_permission("products.manage")),
):
    db = get_db()
    existing = await db.product_categories.find_one({"tenant_id": user["tenant_id"], "code": body.code, "deleted_at": None})
    if existing:
        raise HTTPException(status_code=400, detail="Categoria con code già esistente")
    c = ProductCategory(
        id=new_id(),
        tenant_id=user["tenant_id"],
        code=body.code.upper(),
        label=body.label,
        description=body.description,
        display_order=body.display_order,
        icon=body.icon,
        active=body.active,
        created_by=user["id"],
        updated_by=user["id"],
    )
    await db.product_categories.insert_one(to_mongo(c.model_dump(by_alias=True)))
    await record_audit(
        action="product_categories.create",
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        user_email=user["email"],
        ip=get_client_ip(request),
        entity_type="product_category",
        entity_id=c.id,
        after=body.model_dump(),
    )
    return from_mongo(await db.product_categories.find_one({"_id": c.id}))


@router.patch("/{cid}")
async def update_category(
    cid: str,
    body: ProductCategoryUpdate,
    request: Request,
    user: dict = Depends(require_permission("products.manage")),
):
    db = get_db()
    payload = body.model_dump(exclude_unset=True)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload["updated_by"] = user["id"]
    r = await db.product_categories.update_one(
        {"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None},
        {"$set": payload, "$inc": {"version": 1}},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Categoria non trovata")
    await record_audit(
        action="product_categories.update",
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        user_email=user["email"],
        ip=get_client_ip(request),
        entity_type="product_category",
        entity_id=cid,
        after=payload,
    )
    return from_mongo(await db.product_categories.find_one({"_id": cid}))


@router.delete("/{cid}")
async def delete_category(
    cid: str,
    request: Request,
    user: dict = Depends(require_permission("products.manage")),
):
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    r = await db.product_categories.update_one(
        {"_id": cid, "tenant_id": user["tenant_id"]},
        {"$set": {"deleted_at": now, "updated_at": now, "updated_by": user["id"]}, "$inc": {"version": 1}},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Categoria non trovata")
    await record_audit(
        action="product_categories.delete",
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        user_email=user["email"],
        ip=get_client_ip(request),
        entity_type="product_category",
        entity_id=cid,
    )
    return {"ok": True}
