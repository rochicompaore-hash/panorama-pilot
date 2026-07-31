"""HARD TEST — motore commercial_perimeter con listino completo.

Regole:
- NON può fare skip in nessuna condizione (nessun pytest.skip)
- Se prezzo=0 → FAIL
- Se snapshot mancante → FAIL
- Se pricing_status != 'ok' → FAIL
- Se total != breakdown → FAIL

Prerequisito: eseguire prima `python backend/scripts/seed_test_motor.py`.
"""
from __future__ import annotations
import os
import requests

from tests._creds import ADMIN_EMAIL, ADMIN_PW

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
T = 20

TEST_PRODUCT_ID = "test-motor-product-proevolution"


def _auth() -> dict:
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=T)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _customer_id(h) -> str:
    r = requests.get(f"{API}/customers?limit=1", headers=h, timeout=T)
    assert r.status_code == 200, r.text
    items = r.json().get("items") or []
    assert items, "Nessun cliente disponibile per il test"
    return items[0]["id"]


def _create_quote(h) -> str:
    r = requests.post(f"{API}/quotes", json={
        "customer_id": _customer_id(h),
        "title": "HARD TEST motore",
        "intervention_type": "new",
    }, headers=h, timeout=T)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _create_opening(h, qid) -> str:
    r = requests.post(f"{API}/quote-structure/openings", json={
        "quote_id": qid,
        "environment_name": "Cucina hard-test",
        "environment_kind": "kitchen",
        "display_name": "V01",
        "dimensions": {"width_mm": 900, "height_mm": 1500},
    }, headers=h, timeout=T)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_motor_returns_pricing_status_ok_with_full_listino():
    """MANDATORY test — must NEVER be skipped.

    Deve girare dopo aver eseguito il seed script `scripts/seed_test_motor.py`.
    Verifica che con listino completo il motore restituisce pricing_status=ok
    e un prezzo finale >0 coerente con il breakdown.
    """
    h = _auth()

    # Verifica che il prodotto di test esista (altrimenti fail — non skip)
    import motor.motor_asyncio, asyncio
    async def check_seed():
        c = motor.motor_asyncio.AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = c[os.environ.get("DB_NAME", "infissi_express")]
        p = await db.products.find_one({"_id": TEST_PRODUCT_ID})
        pl = await db.item_pricelists.find_one({"_id": "test-motor-pricelist-01"})
        gr = await db.glass_recipes.find_one({"product_key": "PROEVOLUTION_TEST_MOTORE",
                                                "number_of_sashes": 1})
        pc = await db.production_config.find_one({"tenant_id": p["tenant_id"] if p else None})
        c.close()
        return p, pl, gr, pc

    p, pl, gr, pc = asyncio.run(check_seed())
    assert p is not None, "Seed prodotto mancante: esegui `python backend/scripts/seed_test_motor.py`"
    assert pl is not None, "Seed listino mancante"
    assert gr is not None, "Seed glass recipe mancante"
    assert pc is not None and pc.get("hourly_cost"), "Seed production_config mancante"

    qid = _create_quote(h)
    oid = _create_opening(h, qid)

    payload = {
        "product_id": TEST_PRODUCT_ID, "quantity": 1,
        "width_mm": 900, "height_mm": 1500, "number_of_sashes": 1,
        "window_type": "apribile", "color_code": "BIANCO", "is_color_premium": False,
        "hardware_kit_price": 45.0, "installation_cost": 50.0,
        "transport_cost": 15.0, "accessory_cost": 0.0,
        "other_components_cost": 0.0, "other_components_declared_zero": True,
        # BUG-03 fix (audit v1): glass_price / min_sqm devono essere espliciti (no silent default)
        "glass_price_per_sqm": 76.0, "glass_min_sqm": 0.50,
    }
    r = requests.post(
        f"{API}/quote-structure/{qid}/openings/{oid}/products/compute-and-add",
        json=payload, headers=h, timeout=T,
    )
    # NO SKIP — se 422 con blocking_errors qui è un vero FAIL
    assert r.status_code == 200, (
        f"MOTORE HA FALLITO CON LISTINO COMPLETO. status={r.status_code}\n"
        f"response={r.text[:2000]}"
    )
    data = r.json()
    assert data["pricing_status"] == "ok", data
    line = data["line"]

    # Assert prezzo > 0
    assert float(line["unit_price_final"]) > 0, "Prezzo finale è zero — REGOLA D'ORO VIOLATA"
    assert float(line["subtotal_line"]) > 0, "Subtotal è zero"

    # Assert snapshot presente e completo
    s = line.get("pricing_snapshot")
    assert s, "pricing_snapshot mancante"
    assert s["pricing_status"] == "ok"
    assert line.get("pricing_snapshot_hash"), "pricing_snapshot_hash mancante"

    # Assert coerenza total ≈ breakdown
    total = float(s.get("total") or s.get("sale_price") or 0)
    materials = float(s.get("materials_cost") or 0)
    labor = float(s.get("labor_cost") or 0)

    # Assert coerenza breakdown: total_internal = production_cost + services
    production_cost = float(s.get("production_cost") or 0)
    total_internal = float(s.get("total_internal_cost") or 0)
    services = total_internal - production_cost  # derivato: motore non lo espone
    margin_pct = float(s.get("margin_pct") or 0)
    discount = float(s.get("discount_amount") or 0)

    # production_cost = materials + labor
    assert abs(production_cost - (materials + labor)) < 0.05, (
        f"BREAKDOWN INCOERENTE: production_cost={production_cost} vs materials+labor={materials+labor}"
    )
    # services ≈ posa+trasporto+accessori (50+15+0 = 65)
    assert services >= 0, f"services derivato negativo: {services}"
    expected_services = 50.0 + 15.0
    assert abs(services - expected_services) < 0.05, (
        f"SERVICES MISMATCH: derivato={services} atteso={expected_services}"
    )
    # sale_price = total_internal * (1 + margin/100) - discount
    expected_sale = total_internal * (1 + margin_pct / 100.0) - discount
    assert abs(total - expected_sale) < 0.05, (
        f"BREAKDOWN INCOERENTE: sale={total} attesa={expected_sale}"
    )

    print(f"\n=== MOTORE OK ===")
    print(f"  perimetro esterno:  {s.get('external_perimeter_ml')} ml")
    print(f"  perimetro ante:     {s.get('sash_perimeter_ml')} ml")
    print(f"  materials_cost:     € {materials}")
    print(f"  labor_cost:         € {labor}")
    print(f"  services:           € {services}")
    print(f"  total_internal:     € {total_internal}")
    print(f"  margine:            {margin_pct}%")
    print(f"  sconto:             € {discount}")
    print(f"  PREZZO VENDITA:     € {total}")
    print(f"  snapshot_hash:      {line['pricing_snapshot_hash'][:16]}...")
