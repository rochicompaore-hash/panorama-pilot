"""Configurazione tecnica — endpoint amministrativi per il motore Unified Pricing v3.

Consente all'admin di gestire da UI (senza toccare MongoDB):
  - workshop_cost_configs   → hourly_workshop_cost (versionato)
  - commercial_pricing_rules → moltiplicatore/markup/margin/fixed (versionato)
  - technical_recipes       → ricette tecniche (mapping product+recipe → profile_system)
  - item_pricelists (v3 schema) → prezzi componenti €/ml, €/pz, €/m²

Preventivi esistenti restano invariati: il salvataggio congelato (pricing_snapshot)
non viene ricalcolato. Solo NUOVI /api/pricing/compute usano i nuovi valori.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import get_db
from app.deps import require_permission


router = APIRouter(prefix="/tech-config", tags=["Configurazione tecnica"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------
# WORKSHOP COST
# ---------------------------------------------------------------------
class WorkshopCostPayload(BaseModel):
    hourly_workshop_cost: float = Field(..., gt=0)


@router.get("/workshop-cost")
async def get_workshop_cost(user: dict = Depends(require_permission("pricing_admin.manage"))):
    db = get_db()
    doc = await db.workshop_cost_configs.find_one({
        "tenant_id": user["tenant_id"], "active": True, "deleted_at": None,
    })
    if not doc:
        return {"hourly_workshop_cost": None, "version": 0, "configured": False}
    return {
        "hourly_workshop_cost": float(doc["hourly_workshop_cost"]),
        "version": int(doc.get("version", 1)),
        "currency": doc.get("currency", "EUR"),
        "updated_at": doc.get("updated_at"),
        "configured": True,
    }


@router.put("/workshop-cost")
async def put_workshop_cost(payload: WorkshopCostPayload,
                             user: dict = Depends(require_permission("pricing_admin.manage"))):
    """Aggiorna il costo officina. Bump automatico della `version`.

    Preventivi esistenti NON vengono ricalcolati (usano il proprio pricing_snapshot).
    """
    db = get_db()
    tenant_id = user["tenant_id"]
    now = _now()
    existing = await db.workshop_cost_configs.find_one({"tenant_id": tenant_id, "active": True})
    new_version = int((existing or {}).get("version", 0)) + 1
    doc_id = (existing or {}).get("_id") or f"workshop:{tenant_id}"
    await db.workshop_cost_configs.update_one(
        {"_id": doc_id},
        {"$set": {
            "tenant_id": tenant_id,
            "hourly_workshop_cost": payload.hourly_workshop_cost,
            "currency": "EUR",
            "version": new_version,
            "active": True,
            "updated_at": now,
            "updated_by": user.get("email") or user["id"],
            "deleted_at": None,
        }, "$setOnInsert": {"_id": doc_id, "created_at": now}},
        upsert=True,
    )
    return {"hourly_workshop_cost": payload.hourly_workshop_cost, "version": new_version}


# ---------------------------------------------------------------------
# COMMERCIAL PRICING RULE
# ---------------------------------------------------------------------
class CommercialRulePayload(BaseModel):
    method: str = Field(..., pattern="^(MULTIPLIER|MARKUP_ON_COST|TARGET_GROSS_MARGIN|FIXED_PRICE)$")
    multiplier: Optional[float] = None
    markup_pct: Optional[float] = None
    gross_margin_pct: Optional[float] = None
    fixed_price: Optional[float] = None
    name: Optional[str] = None


@router.get("/commercial-rule")
async def get_commercial_rule(user: dict = Depends(require_permission("pricing_admin.manage"))):
    db = get_db()
    doc = await db.commercial_pricing_rules.find_one({
        "tenant_id": user["tenant_id"], "active": True, "deleted_at": None,
    })
    if not doc:
        return {"configured": False, "version": 0}
    return {
        "method": doc.get("method"),
        "multiplier": doc.get("multiplier"),
        "markup_pct": doc.get("markup_pct"),
        "gross_margin_pct": doc.get("gross_margin_pct"),
        "fixed_price": doc.get("fixed_price"),
        "name": doc.get("name"),
        "version": int(doc.get("version", 1)),
        "updated_at": doc.get("updated_at"),
        "configured": True,
    }


@router.put("/commercial-rule")
async def put_commercial_rule(payload: CommercialRulePayload,
                                user: dict = Depends(require_permission("pricing_admin.manage"))):
    if payload.method == "MULTIPLIER" and payload.multiplier is None:
        raise HTTPException(400, "MULTIPLIER richiede il campo `multiplier`")
    if payload.method == "MARKUP_ON_COST" and payload.markup_pct is None:
        raise HTTPException(400, "MARKUP_ON_COST richiede il campo `markup_pct`")
    if payload.method == "TARGET_GROSS_MARGIN" and payload.gross_margin_pct is None:
        raise HTTPException(400, "TARGET_GROSS_MARGIN richiede `gross_margin_pct`")
    if payload.method == "FIXED_PRICE" and payload.fixed_price is None:
        raise HTTPException(400, "FIXED_PRICE richiede `fixed_price`")

    db = get_db()
    tenant_id = user["tenant_id"]
    now = _now()
    existing = await db.commercial_pricing_rules.find_one({"tenant_id": tenant_id, "active": True})
    new_version = int((existing or {}).get("version", 0)) + 1
    doc_id = (existing or {}).get("_id") or f"rule:{tenant_id}:default"
    await db.commercial_pricing_rules.update_one(
        {"_id": doc_id},
        {"$set": {
            "tenant_id": tenant_id,
            "method": payload.method,
            "multiplier": payload.multiplier,
            "markup_pct": payload.markup_pct,
            "gross_margin_pct": payload.gross_margin_pct,
            "fixed_price": payload.fixed_price,
            "name": payload.name or "Default rule",
            "version": new_version,
            "active": True,
            "updated_at": now,
            "updated_by": user.get("email") or user["id"],
            "deleted_at": None,
        }, "$setOnInsert": {"_id": doc_id, "created_at": now}},
        upsert=True,
    )
    return {"method": payload.method, "version": new_version}


# ---------------------------------------------------------------------
# COMPONENT PRICE (item_pricelists entries) — v3 schema
# ---------------------------------------------------------------------
class ComponentPricePayload(BaseModel):
    code: str = Field(..., min_length=1)
    unit_price: float = Field(..., ge=0)
    unit: str = "ml"
    color_code: Optional[str] = None
    description: Optional[str] = None


@router.get("/component-prices")
async def list_component_prices(user: dict = Depends(require_permission("pricing_admin.manage"))):
    """Ritorna tutte le entries del listino attivo (schema v3)."""
    db = get_db()
    pl = await db.item_pricelists.find_one({
        "tenant_id": user["tenant_id"], "active": True, "deleted_at": None,
    }, sort=[("version", -1)])
    entries = (pl or {}).get("entries") or []
    v3_entries = [e for e in entries if e.get("code")]   # schema v3
    return {
        "pricelist_id": (pl or {}).get("_id"),
        "pricelist_name": (pl or {}).get("name"),
        "version": (pl or {}).get("version", 0),
        "entries": v3_entries,
    }


@router.put("/component-prices/{code}")
async def upsert_component_price(code: str, payload: ComponentPricePayload,
                                    user: dict = Depends(require_permission("pricing_admin.manage"))):
    """Inserisce/aggiorna entry di listino per un componente v3."""
    db = get_db()
    tenant_id = user["tenant_id"]
    now = _now()
    pl = await db.item_pricelists.find_one({
        "tenant_id": tenant_id, "active": True, "deleted_at": None,
    }, sort=[("version", -1)])
    if not pl:
        pl_id = f"pl:{tenant_id}:v3-default"
        pl = {
            "_id": pl_id, "tenant_id": tenant_id,
            "name": "Listino Componenti v3", "version": 1,
            "active": True, "is_default": True, "entries": [],
            "created_at": now, "created_by": user.get("email") or user["id"],
            "deleted_at": None,
        }
        await db.item_pricelists.insert_one(pl)

    entries = list(pl.get("entries") or [])
    key = (code, (payload.color_code or "").upper())
    replaced = False
    for e in entries:
        e_key = (e.get("code"), (e.get("color_code") or "").upper())
        if e_key == key:
            e["unit_price"] = payload.unit_price
            e["unit"] = payload.unit
            e["description"] = payload.description or e.get("description")
            replaced = True
            break
    if not replaced:
        entries.append({
            "code": code,
            "color_code": payload.color_code or "",
            "unit_price": payload.unit_price,
            "unit": payload.unit,
            "description": payload.description or "",
            "currency": "EUR",
        })
    await db.item_pricelists.update_one(
        {"_id": pl["_id"]},
        {"$set": {"entries": entries, "updated_at": now,
                   "updated_by": user.get("email") or user["id"]},
         "$inc": {"version": 1}},
    )
    return {"code": code, "unit_price": payload.unit_price, "replaced": replaced}


# ---------------------------------------------------------------------
# TECHNICAL RECIPES (read-only for Milestone A)
# ---------------------------------------------------------------------
@router.get("/technical-recipes")
async def list_technical_recipes(user: dict = Depends(require_permission("pricing_admin.manage"))):
    db = get_db()
    cur = db.technical_recipes.find({
        "$or": [{"tenant_id": user["tenant_id"]}, {"tenant_id": "*"}],
        "deleted_at": None,
    })
    items = []
    async for d in cur:
        items.append({
            "id": d.get("_id"),
            "product_key": d.get("product_key"),
            "recipe_code": d.get("recipe_code"),
            "profile_system_code": d.get("profile_system_code"),
            "version": d.get("version"),
            "production_time_hours": d.get("production_time_hours"),
            "active": d.get("active"),
        })
    return {"items": items, "total": len(items)}
