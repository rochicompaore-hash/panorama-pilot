"""P0 Operational Test — Verify simulator returns ok price with seeded data.

Regression guard for iter40: la seed di production_config + pricelist entries
deve permettere al motore commercial_perimeter di ritornare un prezzo > 0
per ProEvolution 900x1500 con installation_declared_zero.
"""
from __future__ import annotations
import os
import pytest
import requests
from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or os.environ.get("BASE_URL")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break

PROEVOLUTION_TEST_PRODUCT_ID = "8e1cafd0-9707-47c7-8939-b97c9a404021"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_p0_production_config_has_glass_defaults(token):
    """La production_config del tenant test deve avere glass_price e glass_min impostati."""
    r = requests.get(f"{BASE_URL}/api/catalog/production-config",
                     headers={"Authorization": f"Bearer {token}"},
                     timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("default_glass_price_per_sqm") is not None, "MISSING glass_price"
    assert d.get("default_glass_min_sqm") is not None, "MISSING glass_min"
    assert d["default_glass_price_per_sqm"] > 0
    assert d["default_glass_min_sqm"] > 0


def test_p0_simulate_proevolution_900x1500_returns_ok(token):
    """P0 golden test: ProEvolution 900x1500 BIANCO deve tornare prezzo > 0."""
    r = requests.post(
        f"{BASE_URL}/api/catalog/products/{PROEVOLUTION_TEST_PRODUCT_ID}/simulate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "width_mm": 900, "height_mm": 1500, "quantity": 1,
            "color_code": "BIANCO",
            "other_components_declared_zero": True,
            "installation_declared_zero": True,
        }, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("pricing_status") == "ok", f"blockers={d.get('blocking_errors')}"
    assert d.get("sale_price") is not None and d["sale_price"] > 0
    # Geometrie
    assert d.get("external_perimeter_ml") == 4.8
    assert d.get("glass_area_sqm") is not None and d["glass_area_sqm"] > 0
    # Snapshot presente
    assert d.get("snapshot_hash")
    assert d.get("recipe_code") == "commercial_perimeter"


def test_p0_simulate_without_declared_zero_shows_missing_error(token):
    """Senza installation_declared_zero deve mostrare MISSING_INSTALLATION_PRICE (fail-closed)."""
    r = requests.post(
        f"{BASE_URL}/api/catalog/products/{PROEVOLUTION_TEST_PRODUCT_ID}/simulate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "width_mm": 900, "height_mm": 1500, "quantity": 1,
            "color_code": "BIANCO",
            "other_components_declared_zero": True,
            # NO installation_declared_zero
        }, timeout=15)
    assert r.status_code == 200
    d = r.json()
    codes = [b.get("code") for b in d.get("blocking_errors", [])]
    assert "MISSING_INSTALLATION_PRICE" in codes
    assert d.get("pricing_status") == "incomplete"
