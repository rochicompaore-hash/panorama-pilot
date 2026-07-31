"""One-shot seed per test motore commercial_perimeter (DEV ONLY).

Crea:
  - Prodotto 'PROEVOLUTION — TEST MOTORE' (key=PROEVOLUTION_TEST_MOTORE)
  - Listino demo 'TEST-MOTORE Listino' con entries per telaio/anta/rinforzi/fermavetro (BIANCO)
  - Glass recipe custom per il product_key sopra
  - production_config con hourly_cost, tempo produzione 1-anta, margine

Tutto marcato is_demo=true per rimozione veloce.

Uso:
  python scripts/seed_test_motor.py
"""
from __future__ import annotations
import asyncio, os
from datetime import datetime, timezone
from decimal import Decimal
import motor.motor_asyncio

TENANT_ID = os.environ.get("SEED_TENANT_ID", "5e353147-2416-4ef7-aa3f-3e0007435c42")
DEMO_MARKER = "TEST-MOTORE"
PRODUCT_KEY = "PROEVOLUTION_TEST_MOTORE"
PRODUCT_ID = "test-motor-product-proevolution"
PRICELIST_ID = "test-motor-pricelist-01"


async def main():
    c = motor.motor_asyncio.AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = c[os.environ.get("DB_NAME", "infissi_express")]
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Prodotto test
    product = {
        "_id": PRODUCT_ID,
        "tenant_id": TENANT_ID,
        "key": PRODUCT_KEY,
        "name": f"PROEVOLUTION — {DEMO_MARKER}",
        "description": "Prodotto demo per validazione motore commercial_perimeter",
        "lifecycle": "active", "status": "active",
        "brand": "TestBrand", "system": "PVC standard",
        "components": [
            {"category": "telaio", "code": "5103", "required": True, "waste_percentage": 5},
            {"category": "anta_standard", "code": "12130", "required": True, "waste_percentage": 5},
            {"category": "rinforzo_telaio", "code": "RT-STD", "required": True, "waste_percentage": 0},
            {"category": "rinforzo_anta", "code": "RA-STD", "required": True, "waste_percentage": 0},
            {"category": "fermavetro", "code": "FV-STD", "required": True, "waste_percentage": 5},
            {"category": "scambio_battuta", "code": "7379", "applies_to": "finestra_2a", "waste_percentage": 5},
            {"category": "rinforzo_scambio", "code": "RS-STD", "applies_to": "finestra_2a", "waste_percentage": 0},
        ],
        "default_hardware_kit": {"code": "KIT-STD-1A", "price": 45.00},
        "default_other_components_cost": 0.0,
        "is_demo": True, "created_at": now_iso, "updated_at": now_iso,
        "deleted_at": None, "created_by": "system:test-motor",
    }
    await db.products.replace_one({"_id": PRODUCT_ID}, product, upsert=True)
    print(f"✓ Prodotto '{product['name']}' upsert")

    # 2. Listino componenti (item_pricelists.entries[])
    pricelist = {
        "_id": PRICELIST_ID,
        "tenant_id": TENANT_ID,
        "name": f"{DEMO_MARKER} Listino Componenti",
        "active": True, "pl_status": "active",
        "valid_from": now_iso,
        "entries": [
            {"code": "5103", "description": "Telaio 5103 BIANCO", "color_code": "BIANCO", "unit_price": 8.50, "unit": "ml"},
            {"code": "12130", "description": "Anta 12130 BIANCO", "color_code": "BIANCO", "unit_price": 9.20, "unit": "ml"},
            {"code": "RT-STD", "description": "Rinforzo telaio RT-STD", "color_code": "", "unit_price": 3.10, "unit": "ml"},
            {"code": "RA-STD", "description": "Rinforzo anta RA-STD", "color_code": "", "unit_price": 3.30, "unit": "ml"},
            {"code": "FV-STD", "description": "Fermavetro FV-STD BIANCO", "color_code": "BIANCO", "unit_price": 2.20, "unit": "ml"},
            {"code": "7379", "description": "Scambio battuta 7379 BIANCO", "color_code": "BIANCO", "unit_price": 6.40, "unit": "ml"},
            {"code": "RS-STD", "description": "Rinforzo scambio RS-STD", "color_code": "", "unit_price": 2.80, "unit": "ml"},
        ],
        "is_demo": True, "created_at": now_iso, "updated_at": now_iso, "deleted_at": None,
    }
    await db.item_pricelists.replace_one({"_id": PRICELIST_ID}, pricelist, upsert=True)
    print(f"✓ Listino '{pricelist['name']}' con {len(pricelist['entries'])} entries")

    # 3. Colore BIANCO non-premium (per color_categories)
    color_doc = {
        "_id": f"color-test-BIANCO-{TENANT_ID}",
        "tenant_id": TENANT_ID, "code": "BIANCO", "name": "Bianco RAL 9016",
        "is_premium": False, "is_demo": True,
        "created_at": now_iso, "updated_at": now_iso, "deleted_at": None,
    }
    await db.color_categories.replace_one({"_id": color_doc["_id"]}, color_doc, upsert=True)
    print("✓ Colore BIANCO (non premium)")

    # 4. Glass recipe per il product test key, finestra 1 anta
    recipe_id = f"gr-test-{PRODUCT_KEY}-5103-apribile-1"
    recipe = {
        "_id": recipe_id,
        "tenant_id": TENANT_ID,
        "product_key": PRODUCT_KEY,
        "frame_code": "5103", "sash_code": "12130",
        "window_type": "apribile", "number_of_sashes": 1,
        "formula_type": "structured",
        "structured": {"width_reduction_mm": 206, "height_reduction_mm": 206,
                       "split_factor": 1, "quantity": 1},
        "status": "active", "is_system": False, "is_demo": True,
        "version": 1, "created_at": now_iso, "updated_at": now_iso,
        "deleted_at": None, "created_by": "system:test-motor",
    }
    await db.glass_recipes.replace_one({"_id": recipe_id}, recipe, upsert=True)
    print(f"✓ Glass recipe {PRODUCT_KEY} 1-anta")

    # 5. Production config (hourly_cost, tempi, margine, vetro default)
    prod_cfg_id = f"prodcfg-{TENANT_ID}"
    prod_cfg = {
        "_id": prod_cfg_id,
        "tenant_id": TENANT_ID,
        "hourly_cost": 28.00,
        "fixed_window_time_minutes": 30,
        "one_sash_time_minutes": 45,
        "two_sash_time_minutes": 60,
        "three_sash_time_minutes": 80,
        "four_sash_time_minutes": 100,
        "production_time_default_minutes": 45,
        "default_margin_pct": 35.0,
        "default_glass_price_per_sqm": 76.00,
        "default_glass_min_sqm": 0.5,
        "is_demo": True, "created_at": now_iso, "updated_at": now_iso, "deleted_at": None,
    }
    await db.production_config.replace_one({"_id": prod_cfg_id}, prod_cfg, upsert=True)
    print("✓ Production config (hourly=28€, tempo 1a=45min, margine=35%, vetro 76€/mq)")

    c.close()
    print(f"\n✅ Seed completato per tenant {TENANT_ID}")
    print(f"   Product ID: {PRODUCT_ID}")
    print(f"   Listino ID: {PRICELIST_ID}")


if __name__ == "__main__":
    asyncio.run(main())
