"""P0 Operational Fix — seed pricelist entries + production_config defaults.

Non-distruttivo. Idempotente. Solo popolamento se mancante.

- Aggiorna `production_config` tenant con default_glass_price=76 / default_glass_min=0.50
  (valori normativi da ENERHIA_GOLDEN_TEST_CASES_V1) SE nulli.
- Aggiunge entries al listino default per i componenti ProEvolution
  (5103, 12130, RT-STD, RA-STD, FV-STD) SE mancanti.

Uso: python -m scripts.seed_p0_operational
"""
from __future__ import annotations
import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")


TENANT_ID = "5e353147-2416-4ef7-aa3f-3e0007435c42"

# Prezzi €/ml derivati da ENERHIA_GOLDEN_TEST_CASES_V1 + Preventivatore 4.0.xlsx
# Sono valori realistici di riferimento per il collaudo P0 (non produzione reale).
COMPONENT_PRICES = [
    # code, color_code (blank = generico), unit_price €/ml, description
    ("5103",  "",         12.50, "Telaio Premier-Elegant PVC — €/ml (seed P0)"),
    ("5103",  "BIANCO",   12.50, "Telaio Premier-Elegant PVC bianco — €/ml (seed P0)"),
    ("12130", "",         14.80, "Anta standard Premier-Elegant — €/ml (seed P0)"),
    ("12130", "BIANCO",   14.80, "Anta standard Premier-Elegant bianco — €/ml (seed P0)"),
    ("RT-STD", "",         6.20, "Rinforzo telaio acciaio — €/ml (seed P0)"),
    ("RA-STD", "",         5.80, "Rinforzo anta acciaio — €/ml (seed P0)"),
    ("FV-STD", "",         2.30, "Fermavetro PVC — €/ml (seed P0)"),
    ("FV-STD", "BIANCO",   2.30, "Fermavetro PVC bianco — €/ml (seed P0)"),
    ("7379",  "",          8.40, "Scambio battuta PVC — €/ml (seed P0)"),
    ("7379",  "BIANCO",    8.40, "Scambio battuta PVC bianco — €/ml (seed P0)"),
    ("RS-STD", "",         3.50, "Rinforzo scambio acciaio — €/ml (seed P0)"),
]


async def main():
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    now = datetime.now(timezone.utc).isoformat()

    # 1) Production config — imposta glass_price + glass_min se null
    pc = await db.production_config.find_one({"tenant_id": TENANT_ID})
    updates = {}
    if pc is None or pc.get("default_glass_price_per_sqm") in (None, 0):
        updates["default_glass_price_per_sqm"] = 76.0
    if pc is None or pc.get("default_glass_min_sqm") in (None, 0):
        updates["default_glass_min_sqm"] = 0.5
    if updates:
        updates["updated_at"] = now
        updates["updated_by"] = "system:seed-p0-operational"
        await db.production_config.update_one(
            {"tenant_id": TENANT_ID},
            {"$set": updates,
             "$setOnInsert": {
                 "_id": f"pc-{TENANT_ID}", "tenant_id": TENANT_ID,
                 "hourly_cost": 30.0, "production_time_default_minutes": 30.0,
                 "default_margin_pct": 40.0, "premium_pvc_surcharge_pct": 6.0,
                 "created_at": now, "created_by": "system:seed-p0-operational",
                 "deleted_at": None,
             }},
            upsert=True,
        )
        print(f"[production_config] updated: {list(updates.keys())}")
    else:
        print(f"[production_config] already configured — no changes")

    # 2) Pricelist entries — popola listino default con prezzi componenti
    pl = await db.item_pricelists.find_one({
        "tenant_id": TENANT_ID, "deleted_at": None,
        "$or": [{"is_default": True}, {"active": True}, {"pl_status": "active"}],
    })
    if not pl:
        print("[pricelist] NO active/default pricelist found — creating one")
        pl_id = f"pl-{TENANT_ID}-seed-p0"
        await db.item_pricelists.insert_one({
            "_id": pl_id, "tenant_id": TENANT_ID,
            "name": "Listino Standard Infissi Express 2026",
            "version": 1, "active": True, "pl_status": "active", "is_default": True,
            "entries": [], "created_at": now, "updated_at": now,
            "created_by": "system:seed-p0-operational", "deleted_at": None,
        })
        pl = await db.item_pricelists.find_one({"_id": pl_id})

    entries = pl.get("entries") or []
    existing_keys = {(e.get("code"), (e.get("color_code") or "").upper()) for e in entries}
    added = 0
    new_entries = list(entries)
    for code, color, price, desc in COMPONENT_PRICES:
        key = (code, (color or "").upper())
        if key in existing_keys:
            continue
        new_entries.append({
            "code": code, "color_code": color, "unit_price": price,
            "description": desc, "unit": "ml", "currency": "EUR",
        })
        added += 1
    if added:
        await db.item_pricelists.update_one(
            {"_id": pl["_id"]},
            {"$set": {"entries": new_entries, "updated_at": now,
                      "updated_by": "system:seed-p0-operational"}},
        )
        print(f"[pricelist] +{added} entries (total now {len(new_entries)})")
    else:
        print(f"[pricelist] entries already present — no changes")

    # 3) Hardware kit default sui prodotti ProEvolution non demo
    prods_updated = 0
    async for p in db.products.find({
        "tenant_id": TENANT_ID, "deleted_at": None,
        "name": {"$regex": "ProEvolution", "$options": "i"},
        "is_demo": {"$ne": True},
    }):
        if not p.get("default_hardware_kit"):
            await db.products.update_one(
                {"_id": p["_id"]},
                {"$set": {
                    "default_hardware_kit": {"code": "KIT-STD-1A", "price": 45.0},
                    "updated_at": now,
                    "updated_by": "system:seed-p0-operational",
                }},
            )
            prods_updated += 1
    print(f"[products] +{prods_updated} default_hardware_kit populated")

    client.close()
    print("[DONE]")


if __name__ == "__main__":
    asyncio.run(main())
