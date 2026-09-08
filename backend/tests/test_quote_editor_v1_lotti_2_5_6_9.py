"""msg 402 — Lotto 2 (site validation), Lotto 5 (payment terms + sconto 5%), Lotto 6 (profilatura), Lotto 9 (delivery)."""
from __future__ import annotations
import os
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"]}, timeout=20)
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


@pytest.fixture(scope="module")
def cid(admin):
    cust = admin.get(f"{BASE_URL}/api/customers?limit=1", timeout=20).json()
    return (cust.get("items") or cust)[0]["id"]


FULL_SITE = {"name": "Cantiere test", "address": "Via Roma", "street_number": "10", "postal_code": "20100", "city": "Milano",
             "province": "MI", "floor": "2", "has_elevator": True, "site_contact_phone": "3331234567"}


class TestSiteValidation:
    @pytest.mark.parametrize("missing,code", [
        ("address", "SITE_ADDRESS_REQUIRED"), ("street_number", "SITE_ADDRESS_REQUIRED"), ("postal_code", "SITE_ADDRESS_REQUIRED"),
        ("city", "SITE_ADDRESS_REQUIRED"), ("province", "SITE_ADDRESS_REQUIRED"), ("floor", "SITE_FLOOR_REQUIRED"),
        ("has_elevator", "SITE_ELEVATOR_REQUIRED"), ("site_contact_phone", "SITE_PHONE_REQUIRED"),
    ])
    def test_missing_field_rejected(self, admin, cid, missing, code):
        body = {**FULL_SITE, "customer_id": cid}
        body.pop(missing)
        r = admin.post(f"{BASE_URL}/api/sites", json=body, timeout=20)
        assert r.status_code == 400 and code in r.json()["detail"]["codes"]

    def test_complete_site_create_edit_quote(self, admin, cid):
        r = admin.post(f"{BASE_URL}/api/sites", json={**FULL_SITE, "customer_id": cid}, timeout=20)
        assert r.status_code in (200, 201), r.text
        sid = r.json()["id"]
        # edit: cannot blank a mandatory field
        r = admin.patch(f"{BASE_URL}/api/sites/{sid}", json={"floor": ""}, timeout=20)
        assert r.status_code == 400
        r = admin.patch(f"{BASE_URL}/api/sites/{sid}", json={"floor": "3"}, timeout=20)
        assert r.status_code == 200 and r.json()["floor"] == "3"
        q = admin.post(f"{BASE_URL}/api/quotes", json={"title": "Q", "customer_id": cid, "site_id": sid}, timeout=20)
        assert q.status_code in (200, 201), q.text
        assert q.json()["payment_terms_code"] == "DEPOSIT_50_BALANCE_50" and q.json()["delivery_mode"] == "STANDARD"


def _quote_10000(admin, cid):
    qid = admin.post(f"{BASE_URL}/api/quotes", json={"title": "PAY", "customer_id": cid}, timeout=20).json()["id"]
    r = admin.post(f"{BASE_URL}/api/quotes/{qid}/lines", json={"category": "window", "description": "Base", "quantity": 1, "base_price": 10000, "internal_cost": 4000}, timeout=20)
    assert r.status_code == 200, r.text
    return qid


class TestPaymentTerms:
    def test_50_50_no_discount_full_upfront_5pct(self, admin, cid):
        qid = _quote_10000(admin, cid)
        q = admin.patch(f"{BASE_URL}/api/quotes/{qid}", json={"payment_terms": "DEPOSIT_50_BALANCE_50"}, timeout=20).json()
        assert q["automatic_discount_percent"] == 0 and q["payment_discount_amount"] == 0
        assert q["subtotal"] == 10000 and q["vat_amount"] == 2200 and q["total"] == 12200
        assert [s["percent"] for s in q["payment_schedule"]] == [50, 50]
        q = admin.patch(f"{BASE_URL}/api/quotes/{qid}", json={"payment_terms": "FULL_UPFRONT"}, timeout=20).json()
        assert q["automatic_discount_percent"] == 5 and q["payment_discount_amount"] == 500
        assert q["subtotal_before_payment_discount"] == 10000
        assert q["subtotal"] == 9500 and q["vat_amount"] == 2090 and q["total"] == 11590
        fs = q["financial_snapshot"]
        assert fs["net_revenue_ex_vat"] == 9500 and fs["supply_cost"] == 4000
        assert fs["pre_commission_margin"] == round((9500 - 4000) / 9500 * 100, 4) and fs["commission_rate"] == 0.15
        assert fs["tachometer_value"] == fs["final_company_margin"]
        assert q["payment_policy_version"] == "payment_terms_v1_msg402"

    @pytest.mark.parametrize("code,fin", [("DEPOSIT_30_SURVEY_20_BALANCE_50", None), ("FINANCING_WITHOUT_DEPOSIT", "WITHOUT_DEPOSIT"), ("FINANCING_WITH_DEPOSIT", "WITH_DEPOSIT")])
    def test_other_modes_no_discount(self, admin, cid, code, fin):
        qid = _quote_10000(admin, cid)
        q = admin.patch(f"{BASE_URL}/api/quotes/{qid}", json={"payment_terms": code}, timeout=20).json()
        assert q["automatic_discount_percent"] == 0 and q["total"] == 12200 and q["financing_mode"] == fin

    def test_invalid_code_fail_closed(self, admin, cid):
        qid = _quote_10000(admin, cid)
        r = admin.patch(f"{BASE_URL}/api/quotes/{qid}", json={"payment_terms": "BOGUS"}, timeout=20)
        assert r.status_code == 400 and r.json()["detail"]["code"] == "PAYMENT_TERMS_INVALID"


class TestDeliveryPolicy:
    def test_standard_and_express(self, admin, cid):
        qid = _quote_10000(admin, cid)
        q = admin.get(f"{BASE_URL}/api/quotes/{qid}", timeout=20).json()
        assert q["delivery_mode"] == "STANDARD" and q["estimated_delivery_min_days"] == 90 and q["delivery_surcharge_amount"] == 0
        q = admin.patch(f"{BASE_URL}/api/quotes/{qid}", json={"delivery_mode": "EXPRESS"}, timeout=20).json()
        assert q["delivery_surcharge_percent"] == 20 and q["delivery_surcharge_amount"] == 2000
        assert q["express_days_status"] == "NEEDS_PO_CONFIRMATION" and q["estimated_delivery_min_days"] is None
        assert q["subtotal"] == 12000 and q["vat_amount"] == 2640 and q["total"] == 14640
        assert q["financial_snapshot"]["net_revenue_ex_vat"] == 12000
        q = admin.patch(f"{BASE_URL}/api/quotes/{qid}", json={"payment_terms": "FULL_UPFRONT"}, timeout=20).json()
        assert q["payment_discount_amount"] == 600 and q["subtotal"] == 11400   # sconto dopo maggiorazione
        q = admin.patch(f"{BASE_URL}/api/quotes/{qid}", json={"delivery_mode": "STANDARD"}, timeout=20).json()
        assert q["delivery_surcharge_amount"] == 0 and q["subtotal"] == 9500


class TestProfiling:
    def test_profiling_8_eur_ml(self, admin, cid):
        items = admin.get(f"{BASE_URL}/api/multi-cat/products?category_code=FINESTRE", timeout=20).json()["items"]
        pid = [p for p in items if p["key"] == "PROEVOLUTION"][0]["id"]
        qid = admin.post(f"{BASE_URL}/api/quotes", json={"title": "PROF", "customer_id": cid}, timeout=20).json()["id"]
        cfg = {"product_key": "PROEVOLUTION", "window_type": "WINDOW", "number_of_sashes": 1, "width_mm": 1200, "height_mm": 1500,
               "color_internal": "WHITE_MASS", "color_external": "WHITE_MASS", "glass_type": "DOUBLE_STANDARD", "quantity": 2}
        r = admin.post(f"{BASE_URL}/api/quotes/{qid}/lines", json={"category": "finestre", "product_key": "PROEVOLUTION", "quantity": 2, "base_price": 1,
                       "description": "F", "source": "MULTI_CATEGORY_V1", "category_code": "FINESTRE", "product_id": pid, "product_code": "PROEVOLUTION",
                       "pricing_model": "FORMULA_TECHNICAL", "width_mm": 1200, "height_mm": 1500, "configuration_snapshot": cfg}, timeout=30)
        assert r.status_code == 200, r.text
        prof = [s for s in r.json()["automatic_services"] if s["service_code"] == "PROFILING"][0]
        assert prof["perimeter_ml"] == 5.4 and prof["unit_sale_price"] == 43.2 and prof["quantity"] == 2 and prof["sale_price_total"] == 86.4
        assert prof["internal_cost_status"] == "NEEDS_PO_COSTING"
        q = admin.get(f"{BASE_URL}/api/quotes/{qid}", timeout=20).json()
        assert "MISSING_INTERNAL_COST_PROFILING" in q["financial_snapshot"]["financial_snapshot_errors"]
