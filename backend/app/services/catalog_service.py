"""Catalog service — helpers for the new admin area.

Responsibilities (all tenant-scoped):
- Load ProductionConfig for a tenant (never returns a default with 0€; missing
  values remain None and surface as MISSING_* upstream).
- Load a product with its components[] (from `products.components` field).
- Resolve unit prices for a set of component codes and a colour, from the
  active pricelist. Returns a dict `{code: Decimal | None}` — missing values
  stay None so the recipe engine can raise MISSING_*_PRICE.
- Persist the auto-mapping table used during importer wizard.
"""
from __future__ import annotations
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

from app.db import get_db
from app.mongo_utils import from_mongo


# --------------------------------------------------------------------
# Production config
# --------------------------------------------------------------------
DEFAULT_PROD_CFG = {
    # BUG-03 FIX (audit v1) — rimossi i default silent per glass_price/min_sqm.
    # Motore deve emergere MISSING_GLASS_PRICE / MISSING_GLASS_MINIMUM se il tenant
    # non ha configurato esplicitamente questi valori (P6: nessun valore inventato).
    "hourly_cost": None,
    "production_time_default_minutes": None,
    "default_margin_pct": None,
    "default_glass_price_per_sqm": None,   # was 76.0 (silent) → obbliga configurazione esplicita
    "default_glass_min_sqm": None,          # was 0.50 (silent)
    "premium_pvc_surcharge_pct": 6.0,       # 6% è documentato normativamente, resta default
    "default_bar_length_pvc_mm": 6500,      # tecnico standard PVC, resta default
    "default_bar_length_reinforcement_mm": 6000,  # tecnico standard acciaio, resta default
}


async def get_production_config(tenant_id: str) -> Dict[str, Any]:
    db = get_db()
    doc = await db.production_config.find_one({"tenant_id": tenant_id, "deleted_at": None})
    if not doc:
        # Return the *defaults but NOT the required ones*. Required stay None so
        # the recipe surfaces MISSING_HOURLY_COST / _TIME / _MARGIN.
        return {"tenant_id": tenant_id, **DEFAULT_PROD_CFG, "exists": False}
    # Merge: stored doc wins over defaults, but any default not present in doc is added.
    merged = {**DEFAULT_PROD_CFG, **{k: v for k, v in doc.items() if v is not None}}
    merged["tenant_id"] = tenant_id
    merged["exists"] = True
    merged["_id"] = doc.get("_id")
    merged["updated_at"] = doc.get("updated_at")
    merged["updated_by"] = doc.get("updated_by")
    return merged


async def upsert_production_config(tenant_id: str, patch: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    db = get_db()
    now = datetime.now(timezone.utc)
    payload = {**{k: v for k, v in patch.items() if v is not None},
                "updated_at": now.isoformat(), "updated_by": user_id, "tenant_id": tenant_id,
                "deleted_at": None}
    await db.production_config.update_one(
        {"tenant_id": tenant_id},
        {"$set": payload,
         "$setOnInsert": {"_id": f"pc-{tenant_id}", "created_at": now.isoformat(),
                          "created_by": user_id}},
        upsert=True,
    )
    doc = await db.production_config.find_one({"tenant_id": tenant_id})
    return from_mongo(doc)


# --------------------------------------------------------------------
# Product loading (with components[])
# --------------------------------------------------------------------
async def load_product(tenant_id: str, product_id: Optional[str] = None,
                        product_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not product_id and not product_key:
        return None
    db = get_db()
    q: Dict[str, Any] = {"tenant_id": tenant_id, "deleted_at": None}
    if product_id:
        q["_id"] = product_id
    else:
        q["key"] = product_key
    doc = await db.products.find_one(q)
    return from_mongo(doc) if doc else None


def get_component_code(product: Dict[str, Any], category: str,
                        applies_to: Optional[str] = None) -> Optional[str]:
    """Return the component code for a category in a product.

    If `applies_to` is provided, prefer components whose `applies_to` list
    contains it. Falls back to the first component matching the category.
    """
    components = product.get("components") or []
    if applies_to:
        for c in components:
            if c.get("category") == category and applies_to in (c.get("applies_to") or []):
                return c.get("code")
    for c in components:
        if c.get("category") == category:
            return c.get("code")
    return None


# --------------------------------------------------------------------
# Pricelist lookup
# --------------------------------------------------------------------
async def resolve_component_prices(
    tenant_id: str,
    codes_by_kind: Dict[str, str],  # {"frame": "5103", "sash": "12130", ...}
    color_code: str,
    pricelist_id: Optional[str] = None,
) -> Tuple[Dict[str, Optional[Decimal]], Optional[Dict[str, Any]]]:
    """Return {kind: Decimal €/ml or None} + active pricelist doc.

    Lookup strategy on `item_pricelists.entries[]` (existing importer schema):
      match: entry.code == code AND entry.color_code == color_code (or blank)
             AND entry.tenant_id == tenant AND parent pricelist is active.
    Rinforzi (kind starts with 'reinforcement_' / 'rinforzo_') are colour-independent.
    """
    db = get_db()
    now_iso = datetime.now(timezone.utc).isoformat()
    pl_query: Dict[str, Any] = {
        "tenant_id": tenant_id, "deleted_at": None,
        "$and": [
            {"$or": [{"active": True}, {"pl_status": "active"}]},
        ],
    }
    if pricelist_id:
        pl_query["_id"] = pricelist_id
    # BUG-02 FIX (audit v1) — ordering deterministico: version DESC, updated_at DESC.
    # Se coesistono più listini attivi (design consente) → vince il più recente.
    pl_cursor = db.item_pricelists.find(pl_query).sort([
        ("version", -1), ("updated_at", -1), ("_id", -1),
    ]).limit(1)
    pls = await pl_cursor.to_list(1)
    pl = pls[0] if pls else None

    prices: Dict[str, Optional[Decimal]] = {kind: None for kind in codes_by_kind}
    if not pl:
        return prices, None

    entries: List[Dict[str, Any]] = pl.get("entries") or []
    for kind, code in codes_by_kind.items():
        if not code:
            continue
        best_price = None
        is_reinforcement = kind.startswith("reinforcement_") or kind.startswith("rinforzo_")
        for e in entries:
            if str(e.get("code")).strip() != str(code).strip():
                continue
            ecol = (e.get("color_code") or "").strip()
            if not is_reinforcement:
                # Colour-sensitive: require exact match or blank (generic price)
                if ecol and ecol.lower() != color_code.strip().lower():
                    continue
            price_val = e.get("unit_price") or e.get("price") or e.get("price_per_ml")
            if price_val is None:
                continue
            try:
                # Guard against zero — surface as missing per spec
                p = Decimal(str(price_val))
                if p <= 0:
                    continue
                # Prefer coloured match over generic
                if not is_reinforcement and ecol and ecol.lower() == color_code.strip().lower():
                    best_price = p
                    break
                if best_price is None:
                    best_price = p
            except (ValueError, ArithmeticError):
                continue
        prices[kind] = best_price
    return prices, from_mongo(pl)


# --------------------------------------------------------------------
# Colour metadata (is_premium)
# --------------------------------------------------------------------
async def get_color_is_premium(tenant_id: str, color_code: str) -> Optional[bool]:
    """Read `is_premium` from `color_categories` for the given colour code.

    Returns None if the colour record is not found.
    """
    if not color_code:
        return None
    db = get_db()
    doc = await db.color_categories.find_one({
        "tenant_id": tenant_id, "deleted_at": None, "code": color_code,
    })
    if not doc:
        return None
    return bool(doc.get("is_premium", False))


# --------------------------------------------------------------------
# Auto-mapping table
# --------------------------------------------------------------------
FACTORY_CODE_MAPPINGS: List[Dict[str, Any]] = [
    {"code": "5103", "component_category": "telaio", "material": "PVC",
     "description": "Telaio Premier-Elegant (ProEvolution)"},
    {"code": "5105", "component_category": "telaio", "material": "PVC",
     "description": "Telaio restauro Premier-Elegant (ProEvolution Restauro)"},
    {"code": "12130", "component_category": "anta_standard", "material": "PVC",
     "description": "Anta standard Premier-Elegant"},
    {"code": "7379", "component_category": "scambio_battuta", "material": "PVC",
     "description": "Scambio battuta / riporto"},
]


async def get_code_mapping(tenant_id: str, code: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    doc = await db.catalog_code_mappings.find_one({
        "$or": [
            {"tenant_id": tenant_id, "code": code, "deleted_at": None},
            {"tenant_id": None, "code": code, "is_system": True, "deleted_at": None},
        ],
    })
    return from_mongo(doc) if doc else None


async def seed_factory_code_mappings() -> int:
    """Seed the system-wide code mappings (tenant_id=None) — idempotent."""
    db = get_db()
    inserted = 0
    now = datetime.now(timezone.utc).isoformat()
    for m in FACTORY_CODE_MAPPINGS:
        existing = await db.catalog_code_mappings.find_one({
            "tenant_id": None, "code": m["code"], "is_system": True,
        })
        if existing:
            continue
        await db.catalog_code_mappings.insert_one({
            "_id": f"ccm-sys-{m['code']}",
            "tenant_id": None,
            "code": m["code"],
            "component_category": m["component_category"],
            "material": m["material"],
            "description": m["description"],
            "is_system": True,
            "created_at": now, "updated_at": now,
            "created_by": "system:seed",
            "deleted_at": None, "version": 1,
        })
        inserted += 1
    return inserted
