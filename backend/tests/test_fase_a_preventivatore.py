"""FASE A — Preventivatore completo: dropdown sconto step 1%, max dinamico, smontaggio 30€/unità nel calcolo economico."""
from __future__ import annotations

import math
import os
import uuid

import pytest
import requests

from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
COMM_EMAIL, COMM_PWD = "commercial_test@infissiexpress.com", "CommTest!2026"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def commercial():
    return _login(COMM_EMAIL, COMM_PWD)


def _mk_quote(admin, lines):
    tag = uuid.uuid4().hex[:6]
    rc = admin.post(f"{BASE_URL}/api/customers", json={"customer_type": "private", "first_name": "FaseA", "last_name": f"Test{tag}",
                                                        "email": f"fasea_{tag}@x.it", "phone": "3331234567", "tax_code": "RSSMRA80A01H501U",
                                                        "address": {"street": "Via Roma 1", "city": "Milano", "zip_code": "20100", "province": "MI"}}, timeout=15)
    assert rc.status_code in (200, 201), rc.text
    rq = admin.post(f"{BASE_URL}/api/quotes", json={"customer_id": rc.json()["id"], "title": f"FASE A {tag}",
                                                     "site_address": {"street": "Via Cantiere 9", "city": "Monza", "zip_code": "20900", "province": "MB"}}, timeout=15)
    assert rq.status_code in (200, 201), rq.text
    qid = rq.json()["id"]
    for ln in lines:
        rl = admin.post(f"{BASE_URL}/api/quotes/{qid}/lines", json=ln, timeout=15)
        assert rl.status_code in (200, 201), rl.text
    return qid


def _fs(sess, qid):
    r = sess.get(f"{BASE_URL}/api/quotes/{qid}/financial-snapshot", timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["financial_snapshot"]


WINDOW = {"description": "Finestra PVC", "category": "window", "quantity": 1, "base_price": 1000.0, "internal_cost": 400.0,
          "technical_snapshot": {"total_internal_cost": 400.0}, "width_mm": 1200, "height_mm": 1400}


class TestDiscountDropdown:
    @pytest.fixture(scope="class")
    def qid(self, admin):
        return _mk_quote(admin, [WINDOW])

    @pytest.mark.parametrize("bad", [12.5, 101, -1, 0.3])
    def test_non_step_or_out_of_range_rejected(self, admin, qid, bad):
        r = admin.patch(f"{BASE_URL}/api/quotes/{qid}", json={"global_discount_percent": bad}, timeout=15)
        assert r.status_code == 400 and r.json()["detail"]["code"] == "GLOBAL_DISCOUNT_INVALID", r.text

    def test_over_30_requires_admin_cap_permission(self, commercial, qid):
        r = commercial.patch(f"{BASE_URL}/api/quotes/{qid}", json={"global_discount_percent": 31}, timeout=15)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "ADMIN_APPROVAL_REQUIRED", r.text

    def test_integer_step_accepted(self, admin, qid):
        r = admin.patch(f"{BASE_URL}/api/quotes/{qid}", json={"global_discount_percent": 12}, timeout=15)
        assert r.status_code == 200, r.text
        assert admin.get(f"{BASE_URL}/api/quotes/{qid}", timeout=15).json()["global_discount_value"] == 12
        admin.patch(f"{BASE_URL}/api/quotes/{qid}", json={"global_discount_percent": 0}, timeout=15)

    def test_max_step_is_integer_floor_and_commercial_visible(self, admin, commercial, qid):
        fs = _fs(admin, qid)
        m = fs["max_commercial_discount_step_percent"]
        assert isinstance(m, int) and 0 <= m <= 30
        assert m <= math.floor(fs["max_discount_available_percent"] + 1e-9)  # mai arrotondato verso l'alto
        # 1000 ricavo, 400 costo: max effettivo = floor((1-400/(0.8499*1000))*100)=52.93 → step 30 (cap dropdown)
        assert m == 30
        cfs = _fs(commercial, qid)
        assert cfs["max_commercial_discount_step_percent"] == m
        assert "supply_cost" not in cfs and "post_margin_percent" not in cfs

    def test_max_step_accounts_for_full_upfront(self, admin):
        # ricavo 1000, costo 780 → max effettivo D = floor((1-780/849.9)*100)= 8.22% ; con FULL_UPFRONT 5%: g = 1-(1-0.0822)/0.95 = 3.39 → 3
        qid = _mk_quote(admin, [{**WINDOW, "internal_cost": 780.0, "technical_snapshot": {"total_internal_cost": 780.0}}])
        fs0 = _fs(admin, qid)
        assert fs0["max_commercial_discount_step_percent"] == 8
        r = admin.patch(f"{BASE_URL}/api/quotes/{qid}", json={"payment_terms": "FULL_UPFRONT"}, timeout=15)
        assert r.status_code == 200, r.text
        fs1 = _fs(admin, qid)
        assert fs1["max_commercial_discount_step_percent"] == 3
        # oltre il max → BLOCCATO dal backend (pre-check, niente persistenza)
        r = admin.patch(f"{BASE_URL}/api/quotes/{qid}", json={"global_discount_percent": 4}, timeout=15)
        assert r.status_code == 400 and r.json()["detail"]["code"] == "DISCOUNT_BLOCKED_MARGIN_FLOOR", r.text
        r = admin.patch(f"{BASE_URL}/api/quotes/{qid}", json={"global_discount_percent": 3}, timeout=15)
        assert r.status_code == 200, r.text
        fs2 = _fs(admin, qid)
        assert fs2["discount_status"] in ("ALLOWED", "LOW_MARGIN") and fs2["post_margin_percent"] > 15.0


class TestSmontaggio:
    def test_three_elements_30_each_and_in_financials(self, admin):
        qid = _mk_quote(admin, [{**WINDOW, "quantity": 3, "product_key": "PROEVOLUTION", "category_code": "FINESTRE"}])
        r = admin.patch(f"{BASE_URL}/api/quotes/{qid}", json={"installation_mode": "SUPPLY_AND_INSTALLATION", "dismantling_mode": "INCLUDED"}, timeout=15)
        assert r.status_code == 200, r.text
        q = admin.get(f"{BASE_URL}/api/quotes/{qid}", timeout=15).json()
        svcs = [s for l in q["lines"] for s in (l.get("automatic_services") or []) if s.get("service_type") == "SMONTAGGIO"]
        assert svcs, q["lines"][0].get("automatic_services")
        assert sum(float(s["sale_price_total"]) for s in svcs) == 90.0  # 3 × 30 €
        assert all(float(s["unit_sale_price"] if "unit_sale_price" in s else s["sale_price_total"] / s["quantity"]) == 30.0 for s in svcs)
        fs = _fs(admin, qid)
        # ricavo include smontaggio; costo interno 20€/unità nel bucket OTHER (canonico Iter 50 §22)
        assert fs["other_direct_costs"] >= 60.0
        assert fs["net_revenue_ex_vat"] >= 3000.0 + 90.0
        # rimozione → torna a zero
        admin.patch(f"{BASE_URL}/api/quotes/{qid}", json={"dismantling_mode": "EXCLUDED"}, timeout=15)
        q2 = admin.get(f"{BASE_URL}/api/quotes/{qid}", timeout=15).json()
        assert not [s for l in q2["lines"] for s in (l.get("automatic_services") or []) if s.get("service_type") == "SMONTAGGIO"]
