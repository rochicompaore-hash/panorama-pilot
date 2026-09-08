"""F1 Real Catalog Seed — idempotente.

Cosa fa:
  1. Categoria PORTEFINESTRE -> active=False (soft delete §2 direttiva).
  2. Anagrafica ``product_colors`` seed (13 colori approvati con
     pvc_color_category + cassonetti_price_family espliciti).
  3. Rimozione dal catalogo commerciale delle fixture (TEST_ZANZARIERA_AREA_130
     -> active=False, is_test_fixture resta true).
  4. Seed ``zanzariere_colors`` con placeholder BASE/WOOD/MARBLE/SPECIAL default
     per collaudo (§8 direttiva mapping).
  5. Seed 5 modelli reali zanzariere (SWITCH_5, SKAT, UNIKLAT, UNIKVER, UNIKCAT).
  6. Seed 1 prodotto reale TAPPARELLA con AREA + color_map {RAL, LEGNO, RAFFAELLO}.
  7. Seed 1 prodotto CASSONETTO con pricing_model=GRID + griglia importata dal
     workbook ``listino_completo_con_costi.xlsx`` (file JSON pre-processato).

Utilizzo:
  python -m app.scripts.seed_real_catalog_v1 --all-tenants [--dry-run]
"""
from __future__ import annotations
import argparse, asyncio, json, os, sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.db import get_db, close_db
from app.models import new_id


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


PVC_COLORS = [
    # code, name, ral, pvc_category, cassonetti_family, finish_type, mass_color, foil, hex
    ("003", "BIANCO MASSA",           "9016", "MASS_COLOR", "BIANCO_MASSA", "MASS",   True,  False, "#F5F5F0"),
    ("100", "BIANCO CLASSICO",        "9016", "STANDARD",   "STANDARD",     "FOIL",   False, True,  "#F0F0EB"),
    ("096", "CREMA",                  "9001", "STANDARD",   "STANDARD",     "FOIL",   False, True,  "#F0EAD6"),
    ("694", "CEDRO SBIANCATO",        None,   "STANDARD",   "STANDARD",     "WOOD_EFFECT", False, True, "#D9C8A6"),
    ("110", "CILIEGIO / GOLDEN OAK",  None,   "STANDARD",   "STANDARD",     "WOOD_EFFECT", False, True, "#B87333"),
    ("154", "NOCE",                   None,   "STANDARD",   "STANDARD",     "WOOD_EFFECT", False, True, "#5D3A1A"),
    ("048", "GRIGIO ANTRACITE LISCIO","7016", "STANDARD",   "STANDARD",     "MASS",   True,  False, "#383E42"),
    ("019", "BIANCO CALDO",           "9010", "SPECIAL",    "NON_STANDARD", "FOIL",   False, True,  "#F5F1E8"),
    ("145", "QUERCIA IRLANDESE",      None,   "SPECIAL",    "NON_STANDARD", "WOOD_EFFECT", False, True, "#7B4B24"),
    ("146", "CILIEGIO RUSTICO",       None,   "SPECIAL",    "NON_STANDARD", "WOOD_EFFECT", False, True, "#8B3A2A"),
    ("109", "WINCHESTER",             None,   "SPECIAL",    "NON_STANDARD", "WOOD_EFFECT", False, True, "#6B3410"),
    ("402", "DOUGLAS",                None,   "SPECIAL",    "NON_STANDARD", "WOOD_EFFECT", False, True, "#9C6A3C"),
    ("663", "NOCE SORRENTO BALSAMICO",None,   "SPECIAL",    "NON_STANDARD", "WOOD_EFFECT", False, True, "#4A2818"),
]


ZANZARIERE_MODELS = [
    # code, name, min_billable, purchase_cost_table
    ("SWITCH_5", "Zanzariera Switch 5", 2.00, {"BASE": 57.20, "WOOD_EFFECT": 74.36, "MARBLE": 62.92, "SPECIAL": 62.92}),
    ("SKAT",     "Zanzariera Skat",     1.50, {"BASE": 57.00, "WOOD_EFFECT": 78.62, "MARBLE": 57.00, "SPECIAL": 57.00}),
    ("UNIKLAT",  "Zanzariera Uniklat",  2.00, {"BASE": 29.04, "WOOD_EFFECT": 40.66, "MARBLE": 31.94, "SPECIAL": 31.94}),
    ("UNIKVER",  "Zanzariera Unikver",  1.50, {"BASE": 21.56, "WOOD_EFFECT": 30.18, "MARBLE": 23.72, "SPECIAL": 23.72}),
    ("UNIKCAT",  "Zanzariera Unikcat",  1.50, {"BASE": 23.32, "WOOD_EFFECT": 32.65, "MARBLE": 25.65, "SPECIAL": 25.65}),
]


ZANZARIERE_COLOR_PLACEHOLDERS = [
    # placeholder colors — real catalog TO_CONFIRM by PO
    ("ZC_BASE_DEFAULT", "Colore Base (default)", "BASE", "#DDDDDD"),
    ("ZC_WOOD_DEFAULT", "Effetto Legno (default)", "WOOD_EFFECT", "#8B5A2B"),
    ("ZC_MARBLE_DEFAULT", "Marmo (default)", "MARBLE", "#C9C0B0"),
    ("ZC_SPECIAL_DEFAULT", "Speciale (default)", "SPECIAL", "#4A4A4A"),
]


TAPPARELLE_COLOR_MAP = {
    # colore commerciale -> price category (embedded nel prodotto)
    "RAL_STANDARD": "RAL",
    "WOOD_EFFECT":  "LEGNO",
    "RAFFAELLO":    "RAFFAELLO",
}


async def seed_colors(db, tenant_id: str, dry: bool) -> int:
    n = 0
    for i, (code, name, ral, pcat, cass_fam, finish, mass, foil, hex_) in enumerate(PVC_COLORS):
        existing = await db.product_colors.find_one({"tenant_id": tenant_id, "code": code, "deleted_at": None})
        base = {
            "name": name, "ral_reference": ral, "pvc_color_category": pcat,
            "cassonetti_price_family": cass_fam, "finish_type": finish,
            "mass_color": mass, "foil": foil, "visual_hex": hex_,
            "display_order": i * 10, "active": True, "updated_at": _iso(),
        }
        if existing:
            await db.product_colors.update_one({"_id": existing["_id"]}, {"$set": base, "$inc": {"version": 1}})
            continue
        doc = {
            "_id": new_id(), "tenant_id": tenant_id, "code": code,
            "available_internal": True, "available_external": True,
            "created_at": _iso(), "deleted_at": None, "version": 1, **base,
        }
        if not dry:
            await db.product_colors.insert_one(doc); n += 1
    return n


async def seed_zanzariere_colors(db, tenant_id: str, dry: bool) -> int:
    n = 0
    all_models = [m[0] for m in ZANZARIERE_MODELS]
    for i, (code, name, cat, hex_) in enumerate(ZANZARIERE_COLOR_PLACEHOLDERS):
        existing = await db.zanzariere_colors.find_one({"tenant_id": tenant_id, "code": code, "deleted_at": None})
        base = {"name": name, "price_category": cat, "applies_to_models": all_models, "visual_hex": hex_, "display_order": i * 10, "active": True, "updated_at": _iso()}
        if existing:
            await db.zanzariere_colors.update_one({"_id": existing["_id"]}, {"$set": base, "$inc": {"version": 1}})
            continue
        doc = {"_id": new_id(), "tenant_id": tenant_id, "code": code, "created_at": _iso(), "deleted_at": None, "version": 1, **base}
        if not dry:
            await db.zanzariere_colors.insert_one(doc); n += 1
    return n


async def soft_delete_portefinestre(db, tenant_id: str, dry: bool) -> int:
    """§2 direttiva: categoria PORTEFINESTRE -> active=False (soft delete)."""
    r = await db.product_categories.update_one(
        {"tenant_id": tenant_id, "code": "PORTEFINESTRE", "deleted_at": None},
        {"$set": {"active": False, "updated_at": _iso()}, "$inc": {"version": 1}},
    )
    return int(r.modified_count)


async def deactivate_zanzariera_test_fixture(db, tenant_id: str, dry: bool) -> int:
    """Rimuove TEST_ZANZARIERA_AREA_130 dal catalogo commerciale (§5 direttiva)."""
    r = await db.products.update_one(
        {"tenant_id": tenant_id, "key": "TEST_ZANZARIERA_AREA_130", "deleted_at": None},
        {"$set": {"active": False, "new_quote_enabled": False, "updated_at": _iso()}, "$inc": {"version": 1}},
    )
    return int(r.modified_count)


async def seed_zanzariere_products(db, tenant_id: str, dry: bool) -> int:
    cat = await db.product_categories.find_one({"tenant_id": tenant_id, "code": "ZANZARIERE", "deleted_at": None})
    if not cat:
        return 0
    n = 0
    for i, (code, name, min_bill, cost_table) in enumerate(ZANZARIERE_MODELS):
        pricing_config = {
            "purchase_cost_table_per_m2": cost_table,
            "minimum_billable_area_m2": min_bill,
            "commercial_multiplier": 3.00,
            "color_domain": "ZANZARIERE",
            "pricing_version": "zanzariere_2026_08",
        }
        base_patch = {
            "name": name, "pricing_model": "AREA", "pricing_config": pricing_config,
            "category_id": cat["_id"], "category_code": "ZANZARIERE",
            "sale_unit": "m2", "minimum_billable_quantity": min_bill,
            "line": "Deceuninck", "subcategory": code,
            "new_quote_enabled": True, "legacy": False, "active": True,
            "is_test_fixture": False, "classification_status": "CLASSIFIED",
            "updated_at": _iso(),
        }
        existing = await db.products.find_one({"tenant_id": tenant_id, "key": code, "deleted_at": None})
        if existing:
            if not dry:
                await db.products.update_one({"_id": existing["_id"]}, {"$set": base_patch, "$inc": {"version": 1}})
            continue
        doc = {
            "_id": new_id(), "tenant_id": tenant_id, "key": code, "category": "screen",
            "description": f"{name} — costo acquisto ×3 (min {min_bill} m²/pz)",
            "base_price": 0.0, "base_type": "sqm", "min_billable_sqm": min_bill,
            "default_config": {}, "config_schema": {}, "order_index": 100 + i,
            "compatible_packages": ["BASE", "ADVANCED", "PREMIUM"],
            "compatible_services": [],
            "created_at": _iso(), "deleted_at": None, "version": 1, **base_patch,
        }
        if not dry:
            await db.products.insert_one(doc); n += 1
    return n


async def seed_tapparella_product(db, tenant_id: str, dry: bool) -> int:
    cat = await db.product_categories.find_one({"tenant_id": tenant_id, "code": "TAPPARELLE", "deleted_at": None})
    if not cat:
        return 0
    # Policy AGGIORNATA 20 Ago 2026: TAPPARELLE ×3 (superata la vecchia "NO ×3").
    # 35/40/45 sono PURCHASE COST €/m². Sale = purchase × 3 = 105/120/135 €/m².
    pricing_config = {
        "purchase_cost_table_per_m2": {"RAL": 35.00, "LEGNO": 40.00, "RAFFAELLO": 45.00},
        "minimum_billable_area_m2": 1.50,
        "commercial_multiplier": 3.00,
        "color_domain": "INTERNAL_MAP",
        "color_map": {"RAL_STANDARD": "RAL", "WOOD_EFFECT": "LEGNO", "RAFFAELLO": "RAFFAELLO"},
        "pricing_version": "tapparelle_2026_08_v2_x3",
        "policy_note": "Aggiornata policy ×3 il 20 Ago 2026. Posa separata via simple_services.",
    }
    base = {
        "name": "Tapparella PVC (3 varianti — ×3)",
        "pricing_model": "AREA", "pricing_config": pricing_config,
        "category_id": cat["_id"], "category_code": "TAPPARELLE",
        "sale_unit": "m2", "minimum_billable_quantity": 1.50,
        "line": "Standard", "new_quote_enabled": True, "legacy": False, "active": True,
        "is_test_fixture": False, "classification_status": "CLASSIFIED",
        "updated_at": _iso(),
    }
    existing = await db.products.find_one({"tenant_id": tenant_id, "key": "TAPPARELLA_STANDARD", "deleted_at": None})
    if existing:
        if not dry:
            await db.products.update_one({"_id": existing["_id"]}, {"$set": base, "$inc": {"version": 1}})
        return 0
    doc = {
        "_id": new_id(), "tenant_id": tenant_id, "key": "TAPPARELLA_STANDARD",
        "category": "roller",
        "description": "Tapparella — purchase €/m² × 3 (RAL 105 / LEGNO 120 / RAFFAELLO 135 €/m² sale) · min 1.50 m²/pz",
        "base_price": 0.0, "base_type": "sqm", "min_billable_sqm": 1.50,
        "order_index": 200, "compatible_packages": ["BASE","ADVANCED","PREMIUM"],
        "compatible_services": [], "created_at": _iso(), "deleted_at": None, "version": 1, **base,
    }
    if not dry:
        await db.products.insert_one(doc); return 1
    return 0


async def seed_cassonetto_product(db, tenant_id: str, dry: bool) -> int:
    cat = await db.product_categories.find_one({"tenant_id": tenant_id, "code": "CASSONETTI", "deleted_at": None})
    if not cat:
        return 0
    grid_path = Path(__file__).resolve().parents[1] / "data" / "cassonetti_grid_2026.json"
    if not grid_path.exists():
        print(f"  [SKIP] cassonetti grid data not found: {grid_path}")
        return 0
    with open(grid_path) as fp:
        grid_data = json.load(fp)
    pricing_config = {
        "grid_version": grid_data["version"],
        "source_file": grid_data["source_file"],
        "depths_mm": grid_data["depths_mm"],
        "ceiling_liner_options": grid_data["ceiling_liner_options"],
        "finish_families": grid_data["finish_families"],
        "widths_mm": grid_data.get("widths_mm"),
        "heights_mm": grid_data.get("heights_mm"),
        "imported_at": grid_data.get("imported_at"),
        "grid": grid_data["grid"],
        "color_domain": "PVC",  # risolvi finish_family da product_colors.cassonetti_price_family
        "pricing_formula_metadata": {
            "commercial_multiplier": 2.5,
            "surcharge_h_above_500_or_l_below_700": 0.30,
            "surcharge_h_above_500_and_l_below_700": 0.50,
            "note": "Formula documentata ma NON usata per il compute — il file vince (§9/15 direttive)",
        },
    }
    base = {
        "name": "Cassonetto — Listino Ufficiale 2026",
        "pricing_model": "GRID", "pricing_config": pricing_config,
        "category_id": cat["_id"], "category_code": "CASSONETTI",
        "sale_unit": "pz", "line": "Standard",
        "new_quote_enabled": True, "legacy": False, "active": True,
        "is_test_fixture": False, "classification_status": "CLASSIFIED",
        "updated_at": _iso(),
    }
    existing = await db.products.find_one({"tenant_id": tenant_id, "key": "CASSONETTO_STD", "deleted_at": None})
    if existing:
        if not dry:
            await db.products.update_one({"_id": existing["_id"]}, {"$set": base, "$inc": {"version": 1}})
        return 0
    doc = {
        "_id": new_id(), "tenant_id": tenant_id, "key": "CASSONETTO_STD",
        "category": "box", "description": "Cassonetto — griglia ufficiale (L × H × profondità × cielino × famiglia colore)",
        "base_price": 0.0, "base_type": "piece", "min_billable_sqm": 0.0,
        "order_index": 300, "compatible_packages": ["BASE","ADVANCED","PREMIUM"],
        "compatible_services": [], "created_at": _iso(), "deleted_at": None, "version": 1, **base,
    }
    if not dry:
        await db.products.insert_one(doc); return 1
    return 0


async def seed_persiana_product(db, tenant_id: str, dry: bool) -> int:
    """PERSIANE — AREA_PURCHASE_MULTIPLIER (msg 401 §12-§23).

    purchase €/m²: RAL 285 · WOOD 299 · SPECIAL 350 · orientabile +99 €/m² (pre-multiplier)
    minimum 1.30 m² PER PEZZO · commercial ×2.5 · posa/smontaggio separati (listino montaggio).
    """
    cat = await db.product_categories.find_one({"tenant_id": tenant_id, "code": "PERSIANE_SCURI", "deleted_at": None})
    if not cat:
        return 0
    pricing_config = {
        "purchase_cost_table_per_m2": {"RAL": 285.00, "WOOD": 299.00, "SPECIAL": 350.00},
        "minimum_billable_area_m2": 1.30,
        "commercial_multiplier": 2.5,
        "orientable_surcharge_per_m2": 99.00,
        "color_domain": "INTERNAL_MAP",
        "color_map": {"RAL": "RAL", "WOOD_EFFECT": "WOOD", "SPECIAL_RAFFAELLO": "SPECIAL"},
        "pricing_version": "persiane_2026_09_v1",
        "policy_note": "Purchase ×2.5. Minimo 1.30 m² per unità. Orientabile +99 €/m² sul costo acquisto prima del multiplier. Posa 150 € (INSTALL_SHUTTER_1_2_SASH) e smontaggio 30 €/pz cliente (REMOVE_SHUTTER, msg 402) separati.",
    }
    base = {
        "name": "Persiana in alluminio (RAL / Effetto legno / Speciali)",
        "pricing_model": "AREA_PURCHASE_MULTIPLIER", "pricing_config": pricing_config,
        "category_id": cat["_id"], "category_code": "PERSIANE_SCURI",
        "sale_unit": "m2", "minimum_billable_quantity": 1.30,
        "line": "Standard", "new_quote_enabled": True, "legacy": False, "active": True,
        "is_test_fixture": False, "classification_status": "CLASSIFIED",
        "updated_at": _iso(),
    }
    existing = await db.products.find_one({"tenant_id": tenant_id, "key": "PERSIANA_STD", "deleted_at": None})
    if existing:
        if not dry:
            await db.products.update_one({"_id": existing["_id"]}, {"$set": base, "$inc": {"version": 1}})
        return 0
    doc = {
        "_id": new_id(), "tenant_id": tenant_id, "key": "PERSIANA_STD",
        "category": "shutter",
        "description": "Persiana — costo acquisto €/m² × 2.5 · min 1,30 m²/pz · orientabile +99 €/m²",
        "base_price": 0.0, "base_type": "sqm", "min_billable_sqm": 1.30,
        "order_index": 250, "compatible_packages": ["BASE", "ADVANCED", "PREMIUM"],
        "compatible_services": [], "created_at": _iso(), "deleted_at": None, "version": 1, **base,
    }
    if not dry:
        await db.products.insert_one(doc); return 1
    return 0


async def _list_tenant_ids(db):
    tids = await db.tenants.distinct("_id", {"deleted_at": None})
    if not tids:
        tids = await db.users.distinct("tenant_id", {"deleted_at": None})
    return [t for t in tids if t]


async def run(tenant_ids, dry_run):
    db = get_db()
    print(f"=== F1 Real Catalog Seed (dry={dry_run}) ===")
    for tid in tenant_ids:
        print(f"\n--- tenant {tid} ---")
        c1 = await seed_colors(db, tid, dry_run); print(f"  colors: {c1} new")
        c2 = await seed_zanzariere_colors(db, tid, dry_run); print(f"  zanzariere_colors: {c2} new")
        c3 = await soft_delete_portefinestre(db, tid, dry_run); print(f"  portefinestre soft-delete: {c3}")
        c4 = await deactivate_zanzariera_test_fixture(db, tid, dry_run); print(f"  test fixture deactivated: {c4}")
        c5 = await seed_zanzariere_products(db, tid, dry_run); print(f"  zanzariere real products: {c5} new")
        c6 = await seed_tapparella_product(db, tid, dry_run); print(f"  tapparella: {c6} new")
        c7 = await seed_cassonetto_product(db, tid, dry_run); print(f"  cassonetto: {c7} new")
        c8 = await seed_persiana_product(db, tid, dry_run); print(f"  persiana: {c8} new")
    await close_db()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tenant-id", action="append")
    p.add_argument("--all-tenants", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    async def _d():
        db = get_db()
        if args.all_tenants: tids = await _list_tenant_ids(db)
        elif args.tenant_id: tids = list(args.tenant_id)
        else: tids = await _list_tenant_ids(db)
        await run(tids, dry_run=args.dry_run)
    asyncio.run(_d())


if __name__ == "__main__":
    main()
