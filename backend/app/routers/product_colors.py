"""Router — Product Colors (PVC anagrafica + Zanzariere colors)."""
from __future__ import annotations
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import get_db
from app.services.delivery_lead_time import color_delivery_class
from app.deps import require_permission, get_client_ip
from app.models import new_id
from app.models_colors import (
    ProductColor, ProductColorCreate, ProductColorUpdate, ZanzarieraColor,
)
from app.mongo_utils import to_mongo, from_mongo
from app.services.audit import record_audit


router = APIRouter(prefix="/product-colors", tags=["real-catalog-v1"])


@router.get("")
async def list_colors(
    active: Optional[bool] = None,
    pvc_color_category: Optional[str] = None,
    cassonetti_price_family: Optional[str] = None,
    user: dict = Depends(require_permission("products.view")),
):
    db = get_db()
    q: dict = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if active is not None:
        q["active"] = active
    if pvc_color_category:
        q["pvc_color_category"] = pvc_color_category
    if cassonetti_price_family:
        q["cassonetti_price_family"] = cassonetti_price_family
    docs = await db.product_colors.find(q).sort([("display_order", 1), ("code", 1)]).to_list(500)
    for d in docs:
        d.setdefault("delivery_class", color_delivery_class(d.get("code")))
    return {"items": [from_mongo(d) for d in docs]}


@router.get("/{color_id}")
async def get_color(color_id: str, user: dict = Depends(require_permission("products.view"))):
    db = get_db()
    d = await db.product_colors.find_one({"_id": color_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not d:
        raise HTTPException(status_code=404, detail="Colore non trovato")
    return from_mongo(d)


@router.post("")
async def create_color(body: ProductColorCreate, request: Request, user: dict = Depends(require_permission("products.manage"))):
    db = get_db()
    existing = await db.product_colors.find_one({"tenant_id": user["tenant_id"], "code": body.code, "deleted_at": None})
    if existing:
        raise HTTPException(status_code=400, detail="Codice colore già esistente")
    c = ProductColor(id=new_id(), tenant_id=user["tenant_id"], created_by=user["id"], updated_by=user["id"], **body.model_dump())
    await db.product_colors.insert_one(to_mongo(c.model_dump(by_alias=True)))
    await record_audit(action="product_colors.create", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="product_color", entity_id=c.id, after=body.model_dump())
    return from_mongo(await db.product_colors.find_one({"_id": c.id}))


@router.patch("/{color_id}")
async def update_color(color_id: str, body: ProductColorUpdate, request: Request, user: dict = Depends(require_permission("products.manage"))):
    db = get_db()
    payload = body.model_dump(exclude_unset=True)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload["updated_by"] = user["id"]
    r = await db.product_colors.update_one({"_id": color_id, "tenant_id": user["tenant_id"], "deleted_at": None}, {"$set": payload, "$inc": {"version": 1}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Colore non trovato")
    await record_audit(action="product_colors.update", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="product_color", entity_id=color_id, after=payload)
    return from_mongo(await db.product_colors.find_one({"_id": color_id}))


# Zanzariere colors — collection separata
z_router = APIRouter(prefix="/zanzariere-colors", tags=["real-catalog-v1"])


@z_router.get("")
async def list_zanzariere_colors(user: dict = Depends(require_permission("products.view"))):
    db = get_db()
    q = {"tenant_id": user["tenant_id"], "deleted_at": None, "active": True}
    docs = await db.zanzariere_colors.find(q).sort([("display_order", 1)]).to_list(200)
    return {"items": [from_mongo(d) for d in docs]}
