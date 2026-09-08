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


# =====================================================================
# GLASS PRICES — Milestone 2 (Enerhia Operating Core)
# =====================================================================
# Regole ufficiali BR-07:
#   DOUBLE_STANDARD = 76 €/m²
#   DOUBLE_SATIN    = 96 €/m²
#   TRIPLE_STANDARD = 125 €/m²
#   TRIPLE_SATIN    = 156.25 €/m² (PO msg 402 definitivo)
# minimum_billable_area_per_pane = 0.50 m² (per singolo pannello)
GLASS_TYPES_DEFAULT = [
    ("DOUBLE_STANDARD", 76.00,  0.50, "Doppio vetro standard"),
    ("DOUBLE_SATIN",    96.00,  0.50, "Doppio vetro satinato"),
    ("TRIPLE_STANDARD", 125.00, 0.50, "Triplo vetro standard"),
    ("TRIPLE_SATIN",    156.25, 0.50, "Triplo vetro satinato"),
]


class GlassPricePayload(BaseModel):
    glass_type: str = Field(..., min_length=1, max_length=40)
    unit_price_per_sqm: float = Field(..., gt=0)
    min_billable_sqm: float = Field(0.50, ge=0)
    description: Optional[str] = ""


async def _ensure_glass_seed(db, tenant_id: str):
    n = await db.glass_price_configs.count_documents({"tenant_id": tenant_id, "deleted_at": None})
    if n:
        return
    now = _now()
    for gt, price, minb, desc in GLASS_TYPES_DEFAULT:
        import uuid
        await db.glass_price_configs.insert_one({
            "_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "glass_type": gt,
            "unit_price_per_sqm": price,
            "min_billable_sqm": minb,
            "description": desc,
            "active": True,
            "version": 1,
            "created_at": now, "updated_at": now,
            "deleted_at": None,
        })


@router.get("/glass-prices")
async def list_glass_prices(user: dict = Depends(require_permission("pricing_admin.manage"))):
    db = get_db()
    await _ensure_glass_seed(db, user["tenant_id"])
    items = []
    async for d in db.glass_price_configs.find(
        {"tenant_id": user["tenant_id"], "deleted_at": None, "active": True}
    ).sort("glass_type", 1):
        items.append({
            "id": d["_id"],
            "glass_type": d["glass_type"],
            "unit_price_per_sqm": d.get("unit_price_per_sqm"),
            "min_billable_sqm": d.get("min_billable_sqm", 0.5),
            "description": d.get("description", ""),
            "version": d.get("version", 1),
        })
    return {"items": items, "total": len(items)}


@router.put("/glass-prices/{glass_type}")
async def upsert_glass_price(glass_type: str, payload: GlassPricePayload,
                              user: dict = Depends(require_permission("pricing_admin.manage"))):
    db = get_db()
    if payload.glass_type != glass_type:
        raise HTTPException(400, "glass_type nel body deve coincidere con URL")
    now = _now()
    existing = await db.glass_price_configs.find_one({
        "tenant_id": user["tenant_id"], "glass_type": glass_type, "deleted_at": None,
    })
    if existing:
        await db.glass_price_configs.update_one(
            {"_id": existing["_id"]},
            {"$set": {"unit_price_per_sqm": payload.unit_price_per_sqm,
                       "min_billable_sqm": payload.min_billable_sqm,
                       "description": payload.description or "",
                       "active": True, "updated_at": now,
                       "updated_by": user.get("email") or user["id"]},
             "$inc": {"version": 1}},
        )
        return {"glass_type": glass_type, "updated": True}
    import uuid
    await db.glass_price_configs.insert_one({
        "_id": str(uuid.uuid4()),
        "tenant_id": user["tenant_id"],
        "glass_type": glass_type,
        "unit_price_per_sqm": payload.unit_price_per_sqm,
        "min_billable_sqm": payload.min_billable_sqm,
        "description": payload.description or "",
        "active": True,
        "version": 1,
        "created_at": now, "updated_at": now,
        "created_by": user.get("email") or user["id"],
        "deleted_at": None,
    })
    return {"glass_type": glass_type, "created": True}


# =====================================================================
# HARDWARE RULES — Milestone 2
# =====================================================================
# Regole ufficiali (BR-08):
#   WINDOW_1_SASH        = 60 €/serramento
#   WINDOW_2_SASH        = 80 €/serramento
#   DOOR_WINDOW_1_SASH   = 75 €/serramento
#   DOOR_WINDOW_2_SASH   = 90 €/serramento
#   SLIDING_DOOR_WINDOW  = 380 €/anta (per_sash=True)
#   VASISTAS_ONLY        = 40 €/serramento
HARDWARE_DEFAULTS = [
    ("WINDOW",              1, 60.00,  False, "Ferramenta finestra 1 anta"),
    ("WINDOW",              2, 80.00,  False, "Ferramenta finestra 2 ante"),
    ("DOOR_WINDOW",         1, 75.00,  False, "Ferramenta portafinestra 1 anta"),
    ("DOOR_WINDOW",         2, 90.00,  False, "Ferramenta portafinestra 2 ante"),
    ("SLIDING_DOOR_WINDOW", None, 380.00, True, "Ferramenta scorrevole (per anta)"),
    ("VASISTAS_ONLY",       1, 40.00,  False, "Ferramenta esclusivamente vasistas"),
]


class HardwareRulePayload(BaseModel):
    opening_type: str
    number_of_sashes: Optional[int] = None
    cost_per_unit: float = Field(..., ge=0)
    per_sash: bool = False
    description: Optional[str] = ""


async def _ensure_hardware_seed(db, tenant_id: str):
    n = await db.hardware_rules.count_documents({"tenant_id": tenant_id, "deleted_at": None})
    if n:
        return
    now = _now()
    for ot, ns, cost, per_sash, desc in HARDWARE_DEFAULTS:
        import uuid
        await db.hardware_rules.insert_one({
            "_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "opening_type": ot,
            "number_of_sashes": ns,
            "cost_per_unit": cost,
            "per_sash": per_sash,
            "description": desc,
            "active": True,
            "version": 1,
            "created_at": now, "updated_at": now,
            "deleted_at": None,
        })


@router.get("/hardware-rules")
async def list_hardware_rules(user: dict = Depends(require_permission("pricing_admin.manage"))):
    db = get_db()
    await _ensure_hardware_seed(db, user["tenant_id"])
    items = []
    async for d in db.hardware_rules.find(
        {"tenant_id": user["tenant_id"], "deleted_at": None, "active": True}
    ).sort([("opening_type", 1), ("number_of_sashes", 1)]):
        items.append({
            "id": d["_id"],
            "opening_type": d["opening_type"],
            "number_of_sashes": d.get("number_of_sashes"),
            "cost_per_unit": d.get("cost_per_unit"),
            "per_sash": d.get("per_sash", False),
            "description": d.get("description", ""),
            "version": d.get("version", 1),
        })
    return {"items": items, "total": len(items)}


@router.put("/hardware-rules/{rule_id}")
async def update_hardware_rule(rule_id: str, payload: HardwareRulePayload,
                                user: dict = Depends(require_permission("pricing_admin.manage"))):
    db = get_db()
    existing = await db.hardware_rules.find_one({"_id": rule_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not existing:
        raise HTTPException(404, "Regola ferramenta non trovata")
    await db.hardware_rules.update_one(
        {"_id": rule_id},
        {"$set": {"opening_type": payload.opening_type,
                   "number_of_sashes": payload.number_of_sashes,
                   "cost_per_unit": payload.cost_per_unit,
                   "per_sash": payload.per_sash,
                   "description": payload.description or "",
                   "updated_at": _now(),
                   "updated_by": user.get("email") or user["id"]},
         "$inc": {"version": 1}},
    )
    return {"id": rule_id, "updated": True}


@router.post("/hardware-rules")
async def create_hardware_rule(payload: HardwareRulePayload,
                                user: dict = Depends(require_permission("pricing_admin.manage"))):
    db = get_db()
    import uuid
    now = _now()
    _id = str(uuid.uuid4())
    await db.hardware_rules.insert_one({
        "_id": _id,
        "tenant_id": user["tenant_id"],
        "opening_type": payload.opening_type,
        "number_of_sashes": payload.number_of_sashes,
        "cost_per_unit": payload.cost_per_unit,
        "per_sash": payload.per_sash,
        "description": payload.description or "",
        "active": True,
        "version": 1,
        "created_at": now, "updated_at": now,
        "created_by": user.get("email") or user["id"],
        "deleted_at": None,
    })
    return {"id": _id, "created": True}


# =====================================================================
# PRODUCTION TIME CONFIG — Milestone 2
# =====================================================================
# Regole ufficiali (BR-05):
#   WINDOW_1_SASH       = 0.75 h
#   WINDOW_2_SASH       = 1.00 h
#   DOOR_WINDOW_1_SASH  = 1.00 h
#   DOOR_WINDOW_2_SASH  = 1.50 h
#   WINDOW_3_SASH       = 2.30 h
#   DOOR_WINDOW_3_SASH  = 3.00 h
PRODUCTION_TIME_DEFAULTS = [
    ("WINDOW_1_SASH",       0.75, "Finestra 1 anta"),
    ("WINDOW_2_SASH",       1.00, "Finestra 2 ante"),
    ("WINDOW_3_SASH",       2.30, "Finestra 3 ante"),
    ("DOOR_WINDOW_1_SASH",  1.00, "Portafinestra 1 anta"),
    ("DOOR_WINDOW_2_SASH",  1.50, "Portafinestra 2 ante"),
    ("DOOR_WINDOW_3_SASH",  3.00, "Portafinestra 3 ante"),
    ("VASISTAS_ONLY_1_SASH", 0.75, "Vasistas puro (1 anta)"),
]


class ProductionTimePayload(BaseModel):
    recipe_code: str
    hours: float = Field(..., ge=0)
    description: Optional[str] = ""


async def _ensure_production_time_seed(db, tenant_id: str):
    n = await db.production_time_configs.count_documents({"tenant_id": tenant_id, "deleted_at": None})
    if n:
        return
    now = _now()
    for rc, hours, desc in PRODUCTION_TIME_DEFAULTS:
        import uuid
        await db.production_time_configs.insert_one({
            "_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "recipe_code": rc,
            "hours": hours,
            "description": desc,
            "active": True,
            "version": 1,
            "created_at": now, "updated_at": now,
            "deleted_at": None,
        })


@router.get("/production-times")
async def list_production_times(user: dict = Depends(require_permission("pricing_admin.manage"))):
    db = get_db()
    await _ensure_production_time_seed(db, user["tenant_id"])
    items = []
    async for d in db.production_time_configs.find(
        {"tenant_id": user["tenant_id"], "deleted_at": None, "active": True}
    ).sort("recipe_code", 1):
        items.append({
            "id": d["_id"],
            "recipe_code": d["recipe_code"],
            "hours": d.get("hours"),
            "description": d.get("description", ""),
            "version": d.get("version", 1),
        })
    return {"items": items, "total": len(items)}


@router.put("/production-times/{recipe_code}")
async def upsert_production_time(recipe_code: str, payload: ProductionTimePayload,
                                   user: dict = Depends(require_permission("pricing_admin.manage"))):
    db = get_db()
    if payload.recipe_code != recipe_code:
        raise HTTPException(400, "recipe_code nel body deve coincidere con URL")
    now = _now()
    existing = await db.production_time_configs.find_one({
        "tenant_id": user["tenant_id"], "recipe_code": recipe_code, "deleted_at": None,
    })
    if existing:
        await db.production_time_configs.update_one(
            {"_id": existing["_id"]},
            {"$set": {"hours": payload.hours, "description": payload.description or "",
                       "active": True, "updated_at": now,
                       "updated_by": user.get("email") or user["id"]},
             "$inc": {"version": 1}},
        )
        return {"recipe_code": recipe_code, "updated": True}
    import uuid
    await db.production_time_configs.insert_one({
        "_id": str(uuid.uuid4()),
        "tenant_id": user["tenant_id"],
        "recipe_code": recipe_code,
        "hours": payload.hours,
        "description": payload.description or "",
        "active": True,
        "version": 1,
        "created_at": now, "updated_at": now,
        "created_by": user.get("email") or user["id"],
        "deleted_at": None,
    })
    return {"recipe_code": recipe_code, "created": True}
