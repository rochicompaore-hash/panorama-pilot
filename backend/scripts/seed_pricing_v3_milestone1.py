"""Seed Milestone 1 — dati minimi per far funzionare la vertical slice ProEvolution 1-anta.

Popola 3 nuove collezioni (Sistema B target — NON copia dati in `products`):
- technical_recipes         → ricetta PROEVOLUTION:WINDOW_1_SASH
- workshop_cost_configs     → hourly_workshop_cost = 180 €/h (V1_3 BR-06)
- commercial_pricing_rules  → multiplier = 3.0 (V1_3)

Idempotente. Non-distruttivo. Solo tenant target (preview).

Uso: python -m scripts.seed_pricing_v3_milestone1
"""
from __future__ import annotations
import asyncio
import os
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")


TENANT_ID = "5e353147-2416-4ef7-aa3f-3e0007435c42"


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    now = datetime.now(timezone.utc).isoformat()

    # 1) technical_recipes — PROEVOLUTION:WINDOW_1_SASH
    recipe_id = f"recipe:{TENANT_ID}:PROEVOLUTION:WINDOW_1_SASH:v1"
    r = await db.technical_recipes.find_one({"_id": recipe_id})
    if not r:
        await db.technical_recipes.insert_one({
            "_id": recipe_id,
            "tenant_id": TENANT_ID,
            "product_key": "PROEVOLUTION",
            "recipe_code": "WINDOW_1_SASH",
            "version": 1,
            "profile_system_id": f"ps:{TENANT_ID}:PROEVOLUTION:v1",
            "profile_system_code": "PROEVOLUTION",
            "profile_system_version": 1,
            "hardware_role": "WINDOW_STD",
            "production_time_hours": 0.75,
            "notes": "Ricetta V1_3 GT-01. Formule pure in pricing_v3/formulas.py.",
            "active": True,
            "created_at": now,
            "created_by": "system:milestone1-seed",
            "deleted_at": None,
        })
        print(f"[technical_recipes] created {recipe_id}")
    else:
        print(f"[technical_recipes] already present")

    # 2) workshop_cost_configs — 180 €/h (V1_3 BR-06)
    wc_id = f"workshop:{TENANT_ID}"
    w = await db.workshop_cost_configs.find_one({"_id": wc_id})
    if not w:
        await db.workshop_cost_configs.insert_one({
            "_id": wc_id,
            "tenant_id": TENANT_ID,
            "hourly_workshop_cost": 180.0,
            "currency": "EUR",
            "version": 1,
            "active": True,
            "source": "V1_3 BR-06",
            "created_at": now,
            "created_by": "system:milestone1-seed",
            "deleted_at": None,
        })
        print(f"[workshop_cost_configs] created {wc_id} @ 180€/h")
    else:
        print(f"[workshop_cost_configs] already present ({w.get('hourly_workshop_cost')} €/h)")

    # 3) commercial_pricing_rules — MULTIPLIER 3.0
    rule_id = f"rule:{TENANT_ID}:default"
    ru = await db.commercial_pricing_rules.find_one({"_id": rule_id})
    if not ru:
        await db.commercial_pricing_rules.insert_one({
            "_id": rule_id,
            "tenant_id": TENANT_ID,
            "method": "MULTIPLIER",
            "multiplier": 3.0,
            "name": "Default multiplier (V1_3)",
            "version": 1,
            "active": True,
            "created_at": now,
            "created_by": "system:milestone1-seed",
            "deleted_at": None,
        })
        print(f"[commercial_pricing_rules] created {rule_id} @ ×3.0")
    else:
        print(f"[commercial_pricing_rules] already present (method={ru.get('method')}, multiplier={ru.get('multiplier')})")

    client.close()
    print("[DONE]")


if __name__ == "__main__":
    asyncio.run(main())
