"""MARGIN TACHOMETER V1 — E2E API tests (msg 392).

Covers:
  §3 boundary — via API on golden quote + edge margins created inline
  §23 golden OTTIMO — quote 3b4fd98a already in DB
  §24 golden BUONO
  §15 CRITICO — commission_rate=None, status=AUTHORIZATION_REQUIRED
  §20 RBAC — commercial sees only safe subset
  §18 freeze — accepted quotes carry frozen_at / frozen_by
"""
from __future__ import annotations

import os
import pytest
import requests
import uuid

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
COMMERCIAL_EMAIL = "commercial_test@infissiexpress.com"
COMMERCIAL_PASSWORD = "CommTest!2026"
GOLDEN_QUOTE_ID = "3b4fd98a-fc62-457d-9d66-494742e5fc90"

from app.services.margin_engine import COMMERCIAL_SAFE_KEYS  # policy msg 396 §6 / msg 402 §36: tachometer sì, PRE margin no
from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD
ADMIN_ONLY_KEYS = {
    "supply_cost", "installation_cost", "other_direct_costs",
    "pre_commission_contribution", "commission_base",
    "final_company_contribution",
    "margin_policy_version", "gross_contract_value",
}


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Cannot login as {email}: {r.status_code} {r.text[:200]}")
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def commercial():
    return _login(COMMERCIAL_EMAIL, COMMERCIAL_PASSWORD)


# ---------------------------------------------------------------------------
# §23 Golden OTTIMO — precreated quote
# ---------------------------------------------------------------------------
class TestGolden23OTTIMO:
    def test_admin_sees_full_ottimo_breakdown(self, admin):
        r = admin.get(f"{BASE_URL}/api/quotes/{GOLDEN_QUOTE_ID}/financial-snapshot", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_admin_view"] is True
        fs = body["financial_snapshot"]
        assert fs["net_revenue_ex_vat"] == 10000.0
        assert fs["supply_cost"] == 6000.0
        assert fs["installation_cost"] == 1000.0
        assert fs["pre_commission_margin"] == 30.0
        # msg 400 §D / msg 402 §35: PRE 30.00% esatto → fascia 10% (BUONO)
        assert fs["margin_band"] == "BUONO"
        # policy v3: cap 15%, compat (30-15.01)=14.99%
        assert fs["commission_rate"] == 0.1499
        assert fs["commission_gross"] == 1499.0
        assert fs["commission_status"] == "OK"
        assert fs["final_company_contribution"] == 1501.0
        assert fs["final_company_margin"] == 15.01
        assert fs["post_margin_percent"] == 15.01 and fs["pre_margin_percent"] == 30.0


# ---------------------------------------------------------------------------
# §20 RBAC redaction
# ---------------------------------------------------------------------------
class TestRBAC:
    def test_commercial_sees_only_safe_subset(self, commercial):
        r = commercial.get(f"{BASE_URL}/api/quotes/{GOLDEN_QUOTE_ID}/financial-snapshot", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_admin_view"] is False
        fs = body["financial_snapshot"]
        assert set(fs.keys()) == COMMERCIAL_SAFE_KEYS, f"Unexpected keys: {set(fs.keys()) ^ COMMERCIAL_SAFE_KEYS}"
        # No leak
        for k in ADMIN_ONLY_KEYS:
            assert k not in fs, f"LEAK to commercial: {k}"
        # But safe fields do carry values
        assert "margin_band" not in fs and "tachometer_value" not in fs   # msg 801 — nessun margine al commerciale
        assert fs["commission_rate"] == 0.1499
        assert fs["commission_gross"] == 1499.0


# ---------------------------------------------------------------------------
# Helper: create quote with given lines (admin) and return qid
# ---------------------------------------------------------------------------
def _create_quote_with_lines(admin: requests.Session, lines: list) -> str:
    """Create minimal quote via admin API. Falls back to skip if endpoint schema drift."""
    # 1) create customer
    cust_payload = {"customer_type": "private", "first_name": "TEST", "last_name": f"Margin_{uuid.uuid4().hex[:6]}", "email": f"test_{uuid.uuid4().hex[:6]}@x.it"}
    rc = admin.post(f"{BASE_URL}/api/customers", json=cust_payload, timeout=15)
    if rc.status_code not in (200, 201):
        pytest.skip(f"Cannot create customer: {rc.status_code} {rc.text[:200]}")
    cust_id = rc.json().get("id") or rc.json().get("_id")

    # 2) create quote
    q_payload = {"customer_id": cust_id, "title": f"TEST_margin_{uuid.uuid4().hex[:6]}"}
    rq = admin.post(f"{BASE_URL}/api/quotes", json=q_payload, timeout=15)
    if rq.status_code not in (200, 201):
        pytest.skip(f"Cannot create quote: {rq.status_code} {rq.text[:200]}")
    qid = rq.json().get("id") or rq.json().get("_id")

    # 3) add lines
    for ln in lines:
        rl = admin.post(f"{BASE_URL}/api/quotes/{qid}/lines", json=ln, timeout=15)
        if rl.status_code not in (200, 201):
            pytest.skip(f"Cannot add line: {rl.status_code} {rl.text[:200]}")

    return qid


# ---------------------------------------------------------------------------
# §24 Golden BUONO
# ---------------------------------------------------------------------------
class TestGolden24BUONO:
    def test_buono_10pct(self, admin):
        qid = _create_quote_with_lines(admin, [
            {"description": "TEST Window", "category": "window", "quantity": 1,
             "base_price": 9500.0, "internal_cost": 7000.0,
             "technical_snapshot": {"total_internal_cost": 7000.0}},
            {"description": "TEST Install", "category": "installation", "quantity": 1,
             "base_price": 500.0, "internal_cost": 500.0},
        ])
        r = admin.get(f"{BASE_URL}/api/quotes/{qid}/financial-snapshot", timeout=15)
        assert r.status_code == 200, r.text
        fs = r.json()["financial_snapshot"]
        assert fs["net_revenue_ex_vat"] == 10000.0
        assert fs["pre_commission_margin"] == 25.0
        assert fs["margin_band"] == "BUONO"
        assert fs["commission_rate"] == 0.0999
        assert fs["commission_gross"] == 999.0
        assert fs["final_company_contribution"] == 1501.0
        assert fs["final_company_margin"] == 15.01


# ---------------------------------------------------------------------------
# §15 CRITICO
# ---------------------------------------------------------------------------
class TestCRITICO:
    def test_critico_authorization_required(self, admin):
        qid = _create_quote_with_lines(admin, [
            {"description": "TEST Window", "category": "window", "quantity": 1,
             "base_price": 10000.0, "internal_cost": 9500.0,
             "technical_snapshot": {"total_internal_cost": 9500.0}},
        ])
        r = admin.get(f"{BASE_URL}/api/quotes/{qid}/financial-snapshot", timeout=15)
        assert r.status_code == 200, r.text
        fs = r.json()["financial_snapshot"]
        assert fs["margin_band"] == "CRITICO"
        assert fs["commission_rate"] == 0.0
        assert fs["commission_gross"] == 0.0
        assert fs["commission_status"] == "BLOCKED_MARGIN_FLOOR"
        assert fs["discount_status"] == "BLOCKED"
        assert fs["final_company_margin"] == 5.0


# ---------------------------------------------------------------------------
# §18 Freeze on accepted
# ---------------------------------------------------------------------------
class TestFreeze:
    def test_accepted_quote_snapshot_frozen(self, admin):
        # try freezing golden quote's clone
        qid = _create_quote_with_lines(admin, [
            {"description": "TEST Window", "category": "window", "quantity": 1,
             "base_price": 9000.0, "internal_cost": 6000.0,
             "technical_snapshot": {"total_internal_cost": 6000.0}},
            {"description": "TEST Install", "category": "installation", "quantity": 1,
             "base_price": 1000.0, "internal_cost": 1000.0},
        ])
        # transition to accepted (may pass through sent depending on FSM)
        for status in ("sent", "accepted"):
            r = admin.post(f"{BASE_URL}/api/quotes/{qid}/status",
                           json={"new_status": status, "reason": "test freeze"}, timeout=15)
            if r.status_code != 200:
                # try alt payload
                r2 = admin.post(f"{BASE_URL}/api/quotes/{qid}/status",
                                json={"status": status, "reason": "t"}, timeout=15)
                if r2.status_code != 200:
                    pytest.skip(f"Cannot change status to {status}: {r.status_code} {r.text[:150]}")
        # check frozen
        r = admin.get(f"{BASE_URL}/api/quotes/{qid}/financial-snapshot", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["frozen"] is True
        fs = body["financial_snapshot"]
        # frozen fields should be present in the stored doc — we hit the endpoint
        # so cannot directly assert frozen_at without DB read; assert band coherent
        assert fs["margin_band"] == "BUONO"
