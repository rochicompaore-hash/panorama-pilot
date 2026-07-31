"""Supplementary tests for Opzione A catalog area, covering scenarios
not present in test_catalog_area.py:
  - MISSING_ADDITIONAL_COMPONENTS_COST when neither cost nor declared_zero
  - Visibility gating: 'Commerciale' role (no pricing_admin.view_costs) must
    NOT see unit_prices / component_costs / materials_cost / labor_cost /
    production_cost / margin_pct, but MUST still see sale_price / discount.
  - PROEVOLUTION has 7 components + lifecycle_status='active'
  - PATCH production-config then GET returns updated + defaults present
  - Regression: /api/bi/quotes/kpi unchanged around 3 simulate calls.
"""
from __future__ import annotations
import os
import time
import urllib.parse as up
import pytest
import requests

from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD, ephemeral_password

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL missing", allow_module_level=True)

API = f"{BASE_URL}/api"

COMMERCIALE_ROLE_ID = "c9015476-9c2b-4b7f-9c15-97e4bd85088e"  # tenant admin scoped; will lookup at runtime


# --------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------
def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text[:200]
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


@pytest.fixture(scope="module")
def admin() -> requests.Session:
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def commerciale_role_id(admin) -> str:
    """Find the Commerciale role id in the admin tenant."""
    r = admin.get(f"{API}/roles", timeout=10)
    assert r.status_code == 200
    for role in r.json().get("items", []):
        if role.get("name") == "Commerciale":
            return role.get("_id") or role.get("id")
    pytest.skip("Commerciale role not present in tenant")


@pytest.fixture(scope="module")
def proevolution_id(admin) -> str:
    r = admin.get(f"{API}/products", timeout=10)
    assert r.status_code == 200
    for p in r.json().get("items", []):
        if p.get("key") == "PROEVOLUTION":
            return p.get("_id") or p.get("id")
    pytest.skip("ProEvolution not seeded")


@pytest.fixture(scope="module")
def commerciale_session(admin, commerciale_role_id) -> requests.Session:
    """Create a TEST_ Commerciale user, accept invitation, return authenticated session."""
    email = f"test_commerciale_{int(time.time())}@example.com"
    password = ephemeral_password("Comm")
    r = admin.post(f"{API}/users", json={
        "email": email,
        "first_name": "TEST",
        "last_name": "Commerciale",
        "role_ids": [commerciale_role_id],
        "send_invitation": True,
    }, timeout=15)
    assert r.status_code in (200, 201), r.text[:300]
    body = r.json()
    invite_url = body.get("invitation_url")
    assert invite_url, "invitation_url missing from create-user response"
    # Extract token
    q = up.urlparse(invite_url).query
    params = up.parse_qs(q)
    token = params["token"][0]
    # Accept invitation
    ar = requests.post(f"{API}/auth/accept-invitation", json={
        "token": token, "password": password,
        "first_name": "TEST", "last_name": "Commerciale",
    }, timeout=15)
    assert ar.status_code == 200, ar.text[:300]
    # Login
    s = _login(email, password)
    yield s
    # Teardown: soft-delete the test user
    try:
        me = s.get(f"{API}/auth/me", timeout=10).json()
        uid = me.get("id") or me.get("_id")
        if uid:
            admin.delete(f"{API}/users/{uid}", timeout=10)
    except Exception:
        pass


# --------------------------------------------------------------------
# 1. product seeded + 7 components + lifecycle active
# --------------------------------------------------------------------
def test_proevolution_has_seven_components_and_active(admin, proevolution_id):
    r = admin.get(f"{API}/catalog/products/{proevolution_id}", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body.get("key") == "PROEVOLUTION"
    comps = body.get("components") or []
    assert len(comps) == 7, f"expected 7 components, got {len(comps)}: {[c.get('code') for c in comps]}"
    assert body.get("lifecycle_status") == "active"


# --------------------------------------------------------------------
# 2. Missing additional components → explicit error code
# --------------------------------------------------------------------
def test_missing_additional_components_cost_blocks(admin, proevolution_id):
    payload = {
        "width_mm": 900, "height_mm": 1500, "color_code": "BIANCO",
        "hardware_kit_price": 12.0,
        # NB: neither other_components_cost nor other_components_declared_zero
        "override_hourly_cost": 30, "override_production_time_min": 30,
        "override_margin_pct": 40,
    }
    r = admin.post(f"{API}/catalog/products/{proevolution_id}/simulate", json=payload, timeout=15)
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert body["pricing_status"] == "incomplete"
    codes = [e["code"] for e in body["blocking_errors"]]
    assert "MISSING_ADDITIONAL_COMPONENTS_COST" in codes, codes


# --------------------------------------------------------------------
# 3. Visibility gating for Commerciale role
# --------------------------------------------------------------------
def test_commerciale_role_cannot_see_internal_costs(commerciale_session, proevolution_id):
    """Visibility gating spec: a Commerciale user (has products.view but NOT
    pricing_admin.view_costs) must reach the endpoint and receive a payload
    where internal cost fields are redacted and _costs_hidden=True.

    NB: current catalog.py:300 reads user.get('permission_keys') but
    get_current_user in app/deps.py does NOT populate permission_keys for
    non-super users → any non-super user gets 403 here. Reported to main agent.
    """
    payload = {
        "width_mm": 900, "height_mm": 1500, "color_code": "BIANCO",
        "hardware_kit_price": 12.0, "other_components_declared_zero": True,
        "override_hourly_cost": 30, "override_production_time_min": 30,
        "override_margin_pct": 40,
    }
    r = commerciale_session.post(f"{API}/catalog/products/{proevolution_id}/simulate",
                                    json=payload, timeout=15)
    assert r.status_code == 200, (
        "BUG: /simulate returns 403 for Commerciale because permission_keys "
        "are not resolved for non-super users. Response: " + r.text[:300]
    )
    body = r.json()
    # Costs must be hidden
    assert body.get("_costs_hidden") is True
    for k in ("unit_prices", "component_costs", "materials_cost",
               "labor_cost", "production_cost", "margin_pct",
               "premium_surcharge"):
        assert k not in body, f"internal field {k} leaked to Commerciale"
    # Sale-facing fields — allowed to be None when incomplete, but the KEYS
    # must be present in the payload so the UI can render "n/d".
    assert "sale_price" in body
    assert "sale_price_before_discount" in body
    assert "discount" in body or "sconto" in body or "discount_amount" in body
    # Status flags must still be there
    assert "pricing_status" in body
    assert "blocking_errors" in body


def test_admin_sees_all_fields(admin, proevolution_id):
    payload = {
        "width_mm": 900, "height_mm": 1500, "color_code": "BIANCO",
        "hardware_kit_price": 12.0, "other_components_declared_zero": True,
        "override_hourly_cost": 30, "override_production_time_min": 30,
        "override_margin_pct": 40,
    }
    r = admin.post(f"{API}/catalog/products/{proevolution_id}/simulate", json=payload, timeout=15)
    body = r.json()
    assert body.get("_costs_hidden") is False
    # Even in incomplete state, the ml_consumption should be shown
    assert "ml_consumption" in body


# --------------------------------------------------------------------
# 4. Production-config PATCH → GET round-trip
# --------------------------------------------------------------------
def test_prod_config_patch_and_get_roundtrip(admin):
    patch_body = {"hourly_cost": 30.0,
                   "production_time_default_minutes": 30,
                   "default_margin_pct": 40.0}
    p = admin.patch(f"{API}/catalog/production-config", json=patch_body, timeout=10)
    assert p.status_code == 200, p.text[:200]
    g = admin.get(f"{API}/catalog/production-config", timeout=10)
    assert g.status_code == 200
    cfg = g.json()
    assert cfg["hourly_cost"] == 30.0
    assert cfg["production_time_default_minutes"] == 30
    assert cfg["default_margin_pct"] == 40.0
    # defaults still present
    # BUG-03 (audit v1): default silent glass_price/min_sqm rimossi
    assert cfg["default_glass_price_per_sqm"] is None
    assert cfg["default_glass_min_sqm"] is None
    assert cfg["premium_pvc_surcharge_pct"] == 6.0


# --------------------------------------------------------------------
# 5. Regression: kpi unchanged around simulate
# --------------------------------------------------------------------
def test_kpi_unchanged_around_simulate(admin, proevolution_id):
    before = admin.get(f"{API}/bi/quotes/kpi?period_days=30", timeout=10).json()
    for _ in range(3):
        admin.post(f"{API}/catalog/products/{proevolution_id}/simulate",
                    json={"width_mm": 900, "height_mm": 1500,
                           "color_code": "BIANCO",
                           "other_components_declared_zero": True},
                    timeout=10)
    after = admin.get(f"{API}/bi/quotes/kpi?period_days=30", timeout=10).json()
    assert before.get("counts_by_status") == after.get("counts_by_status")
    assert before.get("total_created") == after.get("total_created")
