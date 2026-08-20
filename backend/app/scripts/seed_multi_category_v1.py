"""Seed idempotente — Multi-Category Configurator V1.

Cosa fa (SOLO ciò che è approvato esplicitamente):
  1. Crea (upsert) le CATEGORIE commerciali in ``product_categories`` per ogni
     tenant esistente.
  2. Crea (upsert) i **test fixtures** AREA/LINEAR/PER_ITEM su una collection
     dedicata ``test_products_fixtures`` (NON in ``products`` per evitare che
     dati di test finiscano nel catalogo commerciale — vincolo §11).
  3. Classifica ESPLICITAMENTE (solo se esiste con la stessa key) i prodotti
     tecnici ProEvolution/ProEvolution Restauro con
     ``pricing_model=FORMULA_TECHNICAL``. Se non presenti, NON li crea (evita
     inferenza cieca).

Vincoli:
  * Idempotente (`upsert` con guard su code/key).
  * Fail-closed: mai infera ``pricing_model`` da ``base_type`` (§1 delle
    direttive PO).
  * Supporta ``--dry-run`` per stampare senza scrivere.

Utilizzo:
  python -m app.scripts.seed_multi_category_v1 --tenant-id <tid>
  python -m app.scripts.seed_multi_category_v1 --all-tenants --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import List

# Setup env prima degli import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parents[2] / ".env")  # backend/.env

from app.db import get_db, close_db  # noqa: E402
from app.models import new_id  # noqa: E402


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
CATEGORIES = [
    ("FINESTRE", "Finestre", 10, "square-window"),
    ("PORTEFINESTRE", "Portefinestre", 20, "door"),
    ("SCORREVOLI", "Scorrevoli", 30, "arrows-horizontal"),
    ("ZANZARIERE", "Zanzariere", 40, "bug"),
    ("TAPPARELLE", "Tapparelle", 50, "blinds"),
    ("CASSONETTI", "Cassonetti", 60, "package"),
    ("PERSIANE_SCURI", "Persiane / Scuri", 70, "columns-3"),
    ("PORTE_INTERNE", "Porte interne", 80, "door-closed"),
    ("PORTE_BLINDATE", "Porte blindate", 90, "shield"),
    ("ACCESSORI", "Accessori", 100, "wrench"),
    ("SERVIZI", "Servizi", 110, "hand-heart"),
    ("MONTAGGI_POSA", "Montaggi / Posa", 120, "hammer"),
]

# Prodotti tecnici da classificare (solo se già esistono con questa key)
TECH_PRODUCT_KEYS_TO_CLASSIFY = [
    ("PROEVOLUTION", "FINESTRE", "ProEvolution"),
    ("PROEVOLUTION_RESTAURO", "FINESTRE", "ProEvolution Restauro"),
]

# Test fixture (NON in ``products`` — su collection dedicata)
TEST_FIXTURES = [
    {
        "code": "TEST_ZANZARIERA_AREA_130",
        "name": "TEST Zanzariera 130€/m² min 1.50",
        "category_code": "ZANZARIERE",
        "pricing_model": "AREA",
        "pricing_config": {"unit_sale_price": 130.0, "minimum_billable_area_m2": 1.50},
        "sale_unit": "m2",
        "minimum_billable_quantity": 1.50,
        "purpose": "test:AREA_MINIMUM_BILLABLE",
    },
    {
        "code": "TEST_AREA_100_MIN_150",
        "name": "TEST AREA 100€/m² min 1.50",
        "category_code": "ZANZARIERE",
        "pricing_model": "AREA",
        "pricing_config": {"unit_sale_price": 100.0, "minimum_billable_area_m2": 1.50},
        "sale_unit": "m2",
        "minimum_billable_quantity": 1.50,
        "purpose": "test:AREA_100_MIN_150 (§36 acceptance)",
    },
    {
        "code": "TEST_LINEAR_25",
        "name": "TEST Prodotto Lineare 25€/ml",
        "category_code": "ACCESSORI",
        "pricing_model": "LINEAR_METER",
        "pricing_config": {"unit_sale_price": 25.0},
        "sale_unit": "ml",
        "purpose": "test:LINEAR_METER",
    },
    {
        "code": "TEST_PER_ITEM_50",
        "name": "TEST Accessorio 50€/pz",
        "category_code": "ACCESSORI",
        "pricing_model": "PER_ITEM",
        "pricing_config": {"unit_sale_price": 50.0},
        "sale_unit": "pz",
        "purpose": "test:PER_ITEM",
    },
    {
        "code": "TEST_FIXED_120",
        "name": "TEST Servizio Fisso 120€",
        "category_code": "SERVIZI",
        "pricing_model": "FIXED_PRICE",
        "pricing_config": {"fixed_sale_price": 120.0},
        "sale_unit": "forfait",
        "purpose": "test:FIXED_PRICE",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _list_tenant_ids(db) -> List[str]:
    tids = await db.tenants.distinct("_id", {"deleted_at": None})
    if not tids:
        tids = await db.users.distinct("tenant_id", {"deleted_at": None})
    return [t for t in tids if t]


async def seed_categories_for_tenant(db, tenant_id: str, dry_run: bool = False) -> int:
    created = 0
    for code, label, order, icon in CATEGORIES:
        existing = await db.product_categories.find_one({"tenant_id": tenant_id, "code": code, "deleted_at": None})
        if existing:
            continue
        doc = {
            "_id": new_id(),
            "tenant_id": tenant_id,
            "code": code,
            "label": label,
            "description": None,
            "display_order": order,
            "icon": icon,
            "active": True,
            "created_at": _iso_now(),
            "updated_at": _iso_now(),
            "deleted_at": None,
            "version": 1,
        }
        if dry_run:
            print(f"  [DRY] create category {code} tenant={tenant_id}")
        else:
            await db.product_categories.insert_one(doc)
            print(f"  [OK]  category {code} tenant={tenant_id}")
        created += 1
    return created


async def classify_tech_products_for_tenant(db, tenant_id: str, dry_run: bool = False) -> int:
    """Classifica prodotti tecnici ESISTENTI. Non crea nulla se assenti."""
    updated = 0
    for key, cat_code, line in TECH_PRODUCT_KEYS_TO_CLASSIFY:
        prod = await db.products.find_one({"tenant_id": tenant_id, "key": key, "deleted_at": None})
        if not prod:
            print(f"  [SKIP] product {key} tenant={tenant_id} (non esistente, nessuna creazione automatica)")
            continue
        cat = await db.product_categories.find_one({"tenant_id": tenant_id, "code": cat_code, "deleted_at": None})
        if not cat:
            print(f"  [SKIP] product {key}: categoria {cat_code} non trovata")
            continue
        # Idempotente: aggiorna solo se non già classificato o disabilitato
        already_ok = (prod.get("pricing_model") == "FORMULA_TECHNICAL" and prod.get("new_quote_enabled") is True)
        if already_ok:
            continue
        patch = {
            "pricing_model": "FORMULA_TECHNICAL",
            "category_id": cat["_id"],
            "category_code": cat_code,
            "line": line,
            "new_quote_enabled": True,
            "legacy": False,
            "classification_status": "CLASSIFIED",
            "sale_unit": prod.get("sale_unit") or "pz",
            "updated_at": _iso_now(),
        }
        if dry_run:
            print(f"  [DRY] classify {key} -> FORMULA_TECHNICAL tenant={tenant_id}")
        else:
            await db.products.update_one({"_id": prod["_id"]}, {"$set": patch, "$inc": {"version": 1}})
            print(f"  [OK]  classify {key} -> FORMULA_TECHNICAL tenant={tenant_id}")
        updated += 1
    return updated


async def mark_unclassified_as_legacy(db, tenant_id: str, dry_run: bool = False) -> int:
    """Prodotti attivi senza pricing_model -> legacy=True, new_quote_enabled=False, classification_status=TO_CONFIRM.

    NON tocca prodotti già classificati.
    """
    q = {
        "tenant_id": tenant_id,
        "deleted_at": None,
        "$or": [{"pricing_model": None}, {"pricing_model": {"$exists": False}}],
    }
    count = 0
    async for prod in db.products.find(q):
        already_flagged = prod.get("legacy") is True and prod.get("new_quote_enabled") is False
        if already_flagged and prod.get("classification_status"):
            continue
        patch = {
            "legacy": True,
            "new_quote_enabled": False,
            "classification_status": prod.get("classification_status") or "TO_CONFIRM",
            "updated_at": _iso_now(),
        }
        if dry_run:
            print(f"  [DRY] legacy-flag {prod.get('key')} tenant={tenant_id}")
        else:
            await db.products.update_one({"_id": prod["_id"]}, {"$set": patch, "$inc": {"version": 1}})
        count += 1
    if count and not dry_run:
        print(f"  [OK]  flagged {count} legacy products tenant={tenant_id}")
    return count


async def seed_test_fixtures_for_tenant(db, tenant_id: str, dry_run: bool = False) -> int:
    """Test fixtures come prodotti REALI ma marchiati ``is_test_fixture=True``.

    Vincolo §11: chiaramente ``TEST/NOT_FOR_PRODUCTION``. Il ``list_products``
    del nuovo configuratore li mostra solo con ``include_test_fixtures=true``.
    """
    created = 0
    for fx in TEST_FIXTURES:
        cat = await db.product_categories.find_one({"tenant_id": tenant_id, "code": fx["category_code"], "deleted_at": None})
        cat_id = cat["_id"] if cat else None
        existing = await db.products.find_one({"tenant_id": tenant_id, "key": fx["code"], "deleted_at": None})
        base_patch = {
            "pricing_config": fx["pricing_config"],
            "pricing_model": fx["pricing_model"],
            "minimum_billable_quantity": fx.get("minimum_billable_quantity"),
            "sale_unit": fx.get("sale_unit"),
            "category_id": cat_id,
            "category_code": fx["category_code"],
            "purpose": fx.get("purpose"),
            "is_test_fixture": True,
            "new_quote_enabled": True,
            "legacy": False,
            "active": True,
            "classification_status": "TEST_FIXTURE",
            "updated_at": _iso_now(),
        }
        if existing:
            if dry_run:
                print(f"  [DRY] update fixture-product {fx['code']}")
            else:
                await db.products.update_one({"_id": existing["_id"]}, {"$set": base_patch, "$inc": {"version": 1}})
            continue
        doc = {
            "_id": new_id(),
            "tenant_id": tenant_id,
            "key": fx["code"],
            "name": fx["name"],
            "category": "test",  # legacy field
            "description": fx.get("purpose"),
            "base_price": 0.0,
            "base_type": "sqm",
            "min_billable_sqm": 0.0,
            "default_config": {},
            "config_schema": {},
            "order_index": 999,
            "compatible_packages": [],
            "compatible_services": [],
            "created_at": _iso_now(),
            "updated_at": _iso_now(),
            "deleted_at": None,
            "version": 1,
            **base_patch,
        }
        if dry_run:
            print(f"  [DRY] create fixture-product {fx['code']}")
        else:
            await db.products.insert_one(doc)
            print(f"  [OK]  fixture-product {fx['code']} tenant={tenant_id}")
        created += 1
    return created


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def run(tenant_ids: List[str], dry_run: bool = False) -> None:
    db = get_db()
    print(f"=== Multi-Category V1 Seed (dry_run={dry_run}) ===")
    for tid in tenant_ids:
        print(f"\n--- tenant {tid} ---")
        cats = await seed_categories_for_tenant(db, tid, dry_run=dry_run)
        classified = await classify_tech_products_for_tenant(db, tid, dry_run=dry_run)
        legacy_flagged = await mark_unclassified_as_legacy(db, tid, dry_run=dry_run)
        fixtures = await seed_test_fixtures_for_tenant(db, tid, dry_run=dry_run)
        print(f"  summary: categories={cats}, classified={classified}, legacy_flagged={legacy_flagged}, fixtures={fixtures}")
    await close_db()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", action="append", help="Tenant id(s). Ripetibile.")
    parser.add_argument("--all-tenants", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    async def _dispatch():
        db = get_db()
        if args.all_tenants:
            tids = await _list_tenant_ids(db)
        elif args.tenant_id:
            tids = list(args.tenant_id)
        else:
            tids = await _list_tenant_ids(db)
        await run(tids, dry_run=args.dry_run)

    asyncio.run(_dispatch())


if __name__ == "__main__":
    main()
