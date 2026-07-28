"""Fase 1 · Backend motore commerciale integrato — test end-to-end.

Verifica:
  1. Endpoint /compute-and-add crea riga con pricing_snapshot + engine="commercial_perimeter"
  2. Preventivo vuoto NON è legacy
  3. Preventivo con line manuale (base_price>0, no snapshot) risulta legacy
  4. Compute-and-add su preventivo legacy → 409 LEGACY_QUOTE_READ_ONLY
  5. Product inesistente → 404
  6. Endpoint /legacy-status esposto correttamente
  7. Regressione: lista preventivi ancora funzionante
"""
from __future__ import annotations
import os, asyncio
import requests
import pytest

from tests._creds import ADMIN_EMAIL, ADMIN_PW

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
T = 15


def _auth_headers() -> dict:
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=T)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _find_active_product_id() -> str | None:
    import motor.motor_asyncio
    async def q():
        c = motor.motor_asyncio.AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = c[os.environ.get("DB_NAME", "infissi_express")]
        p = await db.products.find_one({"deleted_at": None, "lifecycle": "active"})
        c.close()
        return p["_id"] if p else None
    return asyncio.run(q())


def _get_or_create_customer(headers) -> str:
    """Trova un cliente esistente o ne crea uno di test."""
    r = requests.get(f"{API}/customers?limit=1", headers=headers, timeout=T)
    if r.status_code == 200 and r.json().get("items"):
        return r.json()["items"][0]["id"]
    r2 = requests.post(f"{API}/customers", json={
        "customer_type": "person",
        "first_name": "Test",
        "last_name": "Fase1",
        "email": "testfase1@example.com",
    }, headers=headers, timeout=T)
    assert r2.status_code in (200, 201), r2.text
    return r2.json()["id"]


def _create_quote(headers) -> str:
    cid = _get_or_create_customer(headers)
    r = requests.post(f"{API}/quotes", json={
        "customer_id": cid,
        "title": "Test fase1 motor",
        "intervention_type": "new",
        "notes": "test fase1",
    }, headers=headers, timeout=T)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _create_opening(headers, quote_id) -> str:
    r = requests.post(f"{API}/quote-structure/openings", json={
        "quote_id": quote_id,
        "environment_name": "Cucina test",
        "environment_kind": "kitchen",
        "display_name": "Vano 1",
        "dimensions": {"width_mm": 900, "height_mm": 1500},
    }, headers=headers, timeout=T)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# --------------------------------------------------------------------
def test_compute_and_add_creates_snapshot_or_reports_incomplete():
    h = _auth_headers()
    product_id = _find_active_product_id()
    if not product_id:
        pytest.skip("Nessun prodotto attivo nel catalogo")

    qid = _create_quote(h)
    oid = _create_opening(h, qid)

    payload = {
        "product_id": product_id,
        "quantity": 1,
        "width_mm": 900, "height_mm": 1500,
        "number_of_sashes": 1,
        "window_type": "apribile",
        "color_code": "BIANCO",
        "is_color_premium": False,
        "glass_price_per_sqm": 76.0,
        "glass_min_sqm": 0.5,
        "hardware_kit_price": 45.0,
        "other_components_cost": 0.0,
        "other_components_declared_zero": True,
        "installation_cost": 0.0,
        "installation_declared_zero": True,
        "description": "Test cucina",
        "role": "primary_frame",
    }
    r = requests.post(
        f"{API}/quote-structure/{qid}/openings/{oid}/products/compute-and-add",
        json=payload, headers=h, timeout=T,
    )
    if r.status_code == 422:
        err = r.json()["detail"]
        assert err["code"] in ("PRICING_INCOMPLETE", "COMPUTED_ZERO"), err
        # Listini incompleti — comportamento previsto (P6)
        return
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["pricing_status"] == "ok"
    line = data["line"]
    assert line["unit_price_final"] > 0
    assert line["pricing_engine"] == "commercial_perimeter"
    assert line["pricing_snapshot"] is not None
    assert line["pricing_snapshot"].get("pricing_status") == "ok"
    assert line["pricing_snapshot_hash"]


# --------------------------------------------------------------------
def test_legacy_status_on_fresh_quote_is_false():
    h = _auth_headers()
    qid = _create_quote(h)
    r = requests.get(f"{API}/quote-structure/{qid}/legacy-status", headers=h, timeout=T)
    assert r.status_code == 200, r.text
    assert r.json()["is_legacy"] is False


# --------------------------------------------------------------------
def test_legacy_status_after_manual_line_becomes_true():
    """Simuliamo scenario legacy inserendo direttamente in DB una line con base_price>0 senza snapshot."""
    import motor.motor_asyncio
    h = _auth_headers()
    qid = _create_quote(h)
    oid = _create_opening(h, qid)

    async def inject_legacy_line():
        c = motor.motor_asyncio.AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = c[os.environ.get("DB_NAME", "infissi_express")]
        await db.quotes.update_one(
            {"_id": qid},
            {"$push": {"lines": {
                "id": "legacy-line-1", "opening_id": oid,
                "role": "primary_frame", "base_price": 500.0,
                "unit_price_final": 500.0, "subtotal_line": 500.0,
                # no pricing_snapshot -> quote diventa legacy
            }}},
        )
        c.close()
    asyncio.run(inject_legacy_line())

    r = requests.get(f"{API}/quote-structure/{qid}/legacy-status", headers=h, timeout=T)
    assert r.status_code == 200
    assert r.json()["is_legacy"] is True, "quote con line manuale senza snapshot deve essere legacy"

    # Compute-and-add su legacy -> 409
    r2 = requests.post(
        f"{API}/quote-structure/{qid}/openings/{oid}/products/compute-and-add",
        json={"product_id": "x", "quantity": 1, "width_mm": 900, "height_mm": 1500,
              "color_code": "BIANCO"},
        headers=h, timeout=T,
    )
    assert r2.status_code == 409, r2.text
    err = r2.json()["detail"]
    assert err["code"] == "LEGACY_QUOTE_READ_ONLY"


# --------------------------------------------------------------------
def test_compute_and_add_nonexistent_product_returns_404():
    h = _auth_headers()
    qid = _create_quote(h)
    oid = _create_opening(h, qid)
    r = requests.post(
        f"{API}/quote-structure/{qid}/openings/{oid}/products/compute-and-add",
        json={"product_id": "nonexistent-xxx", "quantity": 1,
              "width_mm": 900, "height_mm": 1500, "color_code": "BIANCO"},
        headers=h, timeout=T,
    )
    assert r.status_code == 404, r.text


# --------------------------------------------------------------------
def test_regression_quotes_list_still_works():
    h = _auth_headers()
    r = requests.get(f"{API}/quotes?limit=5", headers=h, timeout=T)
    assert r.status_code == 200
    d = r.json()
    assert "items" in d and "total" in d


# --------------------------------------------------------------------
def test_health_endpoint_still_up():
    r = requests.get(f"{API}/health", timeout=T)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
