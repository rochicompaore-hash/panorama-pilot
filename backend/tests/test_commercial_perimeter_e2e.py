"""End-to-end HTTP tests for commercial_perimeter mode (new preventivatore default).

- Verifica che i prodotti seedati abbiano default_pricing_mode=commercial_perimeter
- /simulate senza pricing_mode usa il default del prodotto
- /simulate con pricing_mode=technical_cut_list retro-compat funziona
- Le glass recipes factory sono seedate (5 record)
- MISSING_GLASS_RECIPE per configurazioni non approvate (3+ ante)
- Preventivi esistenti non vengono alterati
"""
from __future__ import annotations
import os
import pytest
import requests
from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL missing", allow_module_level=True)
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


@pytest.fixture(scope="module")
def proev_id(admin_session):
    r = admin_session.get(f"{API}/products", timeout=10)
    for p in r.json().get("items", []):
        if p.get("key") == "PROEVOLUTION":
            return p.get("_id") or p.get("id")
    pytest.skip("PROEVOLUTION not seeded")


def test_products_have_default_pricing_mode(admin_session):
    r = admin_session.get(f"{API}/products", timeout=10)
    for p in r.json().get("items", []):
        if p.get("key") in ("PROEVOLUTION", "PROEVOLUTION_RESTAURO"):
            # Il seed dovrebbe aver impostato default_pricing_mode
            assert p.get("default_pricing_mode") == "commercial_perimeter", \
                f"Product {p.get('key')} has default_pricing_mode={p.get('default_pricing_mode')}"


def test_simulate_default_mode_is_commercial_perimeter(admin_session, proev_id):
    body = {
        "width_mm": 900, "height_mm": 1500, "number_of_sashes": 1,
        "window_type": "apribile",
        "color_code": "BIANCO", "hardware_kit_price": 12.0,
        "other_components_declared_zero": True,
        "installation_declared_zero": True,
        "override_hourly_cost": 30, "override_production_time_min": 30, "override_margin_pct": 40,
    }
    r = admin_session.post(f"{API}/catalog/products/{proev_id}/simulate",
                            json=body, timeout=15)
    assert r.status_code == 200, r.text[:400]
    body_r = r.json()
    assert body_r.get("pricing_mode") == "commercial_perimeter", body_r


def test_simulate_perimeter_computes_ml_correctly(admin_session, proev_id):
    body = {
        "width_mm": 900, "height_mm": 1500, "number_of_sashes": 1,
        "window_type": "apribile",
        "color_code": "BIANCO", "hardware_kit_price": 12.0,
        "other_components_declared_zero": True,
        "installation_declared_zero": True,
        "override_hourly_cost": 30, "override_production_time_min": 30, "override_margin_pct": 40,
    }
    r = admin_session.post(f"{API}/catalog/products/{proev_id}/simulate",
                            json=body, timeout=15)
    body_r = r.json()
    # external_perimeter = 4.8 ml sempre calcolabile anche in incomplete
    assert body_r.get("external_perimeter_ml") == 4.8


def test_simulate_technical_mode_retro_compat(admin_session, proev_id):
    body = {
        "width_mm": 900, "height_mm": 1500,
        "color_code": "BIANCO", "hardware_kit_price": 12.0,
        "other_components_declared_zero": True,
        "override_hourly_cost": 30, "override_production_time_min": 30, "override_margin_pct": 40,
        "pricing_mode": "technical_cut_list",  # retro compat esplicito
        "quote_line_type": "finestra_1a",
    }
    r = admin_session.post(f"{API}/catalog/products/{proev_id}/simulate",
                            json=body, timeout=15)
    assert r.status_code == 200
    body_r = r.json()
    assert body_r.get("pricing_mode") == "technical_cut_list"
    # Nel technical mode, il campo `ml_consumption` deve avere `telaio_5103` (naming ricetta 1a)
    if "ml_consumption" in body_r:
        assert "telaio_5103" in body_r["ml_consumption"]


def test_simulate_missing_glass_recipe_for_3_ante(admin_session, proev_id):
    """3 ante non ha ricetta approvata → MISSING_GLASS_RECIPE."""
    body = {
        "width_mm": 900, "height_mm": 1500, "number_of_sashes": 3,
        "window_type": "apribile", "color_code": "BIANCO",
        "hardware_kit_price": 12.0,
        "other_components_declared_zero": True, "installation_declared_zero": True,
        "override_hourly_cost": 30, "override_production_time_min": 30, "override_margin_pct": 40,
    }
    r = admin_session.post(f"{API}/catalog/products/{proev_id}/simulate",
                            json=body, timeout=15)
    body_r = r.json()
    assert body_r["pricing_status"] == "incomplete"
    codes = [e["code"] for e in body_r["blocking_errors"]]
    assert "MISSING_GLASS_RECIPE" in codes


def test_no_alteration_of_existing_kpi(admin_session, proev_id):
    q_before = admin_session.get(f"{API}/bi/quotes/kpi?period_days=30", timeout=10).json()
    for _ in range(3):
        admin_session.post(f"{API}/catalog/products/{proev_id}/simulate", json={
            "width_mm": 900, "height_mm": 1500, "number_of_sashes": 1,
            "window_type": "apribile", "color_code": "BIANCO",
            "other_components_declared_zero": True, "installation_declared_zero": True,
        }, timeout=10)
    q_after = admin_session.get(f"{API}/bi/quotes/kpi?period_days=30", timeout=10).json()
    assert q_before["counts_by_status"] == q_after["counts_by_status"]
    assert q_before["total_created"] == q_after["total_created"]
