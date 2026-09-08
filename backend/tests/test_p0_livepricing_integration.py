"""P0 HOTFIX — Integration tests via public /api endpoints.

Verifies the canonical live-pricing contract for Tapparelle/Zanzariere
through the configure endpoint, including RBAC redaction for Commerciale.
"""
from __future__ import annotations

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://serramento-ops.preview.emergentagent.com").rstrip("/")

ADMIN = ("admin@infissiexpress.com", "Admin!2025")
COMMERCIAL = ("commercial_test@infissiexpress.com", "CommTest!2026")

PID_TAP = "1ddf23e0-cc3e-444f-91af-cdfd5e270bc2"
PID_UV = "c9b14d1f-553e-4d7d-8237-88e7bc9fb6a8"


def _login(email: str, password: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text}"
    data = r.json()
    tok = data.get("access_token") or data.get("token") or (data.get("data") or {}).get("access_token")
    assert tok, f"no token in response: {data}"
    return tok


@pytest.fixture(scope="module")
def admin_headers():
    return {"Authorization": f"Bearer {_login(*ADMIN)}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def commercial_headers():
    return {"Authorization": f"Bearer {_login(*COMMERCIAL)}", "Content-Type": "application/json"}


def _configure(headers, pid, color_code, w=1200, h=1400, qty=1):
    body = {"simple_inputs": {"width_mm": w, "height_mm": h, "quantity": qty, "options": {"color_code": color_code}}}
    r = requests.post(f"{BASE_URL}/api/multi-cat/products/{pid}/configure", json=body, headers=headers, timeout=20)
    return r


class TestTapparellaLivePrice:
    @pytest.mark.parametrize("color,expected", [
        ("RAL_STANDARD", 176.40),
        ("WOOD_EFFECT", 201.60),
        ("RAFFAELLO", 226.80),
    ])
    def test_tap_prices(self, admin_headers, color, expected):
        r = _configure(admin_headers, PID_TAP, color)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("pricing_status") == "ok", data
        snap = data.get("simple_snapshot") or {}
        assert snap.get("unit_price_final") == expected, f"got {snap.get('unit_price_final')}"
        assert snap.get("sale_price_total") == expected


class TestUnikverLivePrice:
    def test_uv_800x800_base(self, admin_headers):
        r = _configure(admin_headers, PID_UV, "ZC_BASE_DEFAULT", w=800, h=800, qty=1)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("pricing_status") == "ok", data
        snap = data.get("simple_snapshot") or {}
        assert snap.get("unit_price_final") == 97.02, snap
        assert snap.get("sale_price_total") == 97.02


class TestRBACCommercial:
    def test_commercial_sees_price_but_no_cost(self, commercial_headers):
        r = _configure(commercial_headers, PID_TAP, "RAL_STANDARD")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("pricing_status") == "ok", data
        snap = data.get("simple_snapshot") or {}
        # Sale-side visible
        assert snap.get("unit_price_final") == 176.40
        assert snap.get("sale_price_total") == 176.40
        # Cost-side redacted
        assert snap.get("purchase_unit_cost_per_m2") is None, f"leak: {snap.get('purchase_unit_cost_per_m2')}"
        assert snap.get("purchase_cost_per_item") is None, f"leak: {snap.get('purchase_cost_per_item')}"
        assert snap.get("commercial_multiplier") is None, f"leak: {snap.get('commercial_multiplier')}"
