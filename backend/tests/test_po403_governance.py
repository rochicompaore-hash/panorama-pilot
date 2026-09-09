"""PO msg 403 governance fixes tests (§4,§5,§6,§7)."""
import os
import pytest
import requests
from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_PWD = ADMIN_PASSWORD


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def s(admin_token):
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module")
def customer_id(s):
    r = s.get(f"{API}/customers?limit=1", timeout=30)
    assert r.status_code == 200, r.text
    items = r.json()
    if isinstance(items, dict):
        items = items.get("items") or items.get("data") or []
    assert items, "no customers"
    return items[0]["id"]


def _create_quote(s, customer_id, title="TEST_PO403"):
    r = s.post(f"{API}/quotes", json={"title": title, "customer_id": customer_id}, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# §6 EXPRESS delivery not purchasable + regression FULL_UPFRONT + §7 ENEA
class TestDeliveryAndENEA:
    def test_full_flow(self, s, customer_id):
        qid = _create_quote(s, customer_id, "TEST_PO403_MAIN")

        # Add window line
        line = {"category": "window", "description": "Base", "quantity": 1,
                "base_price": 10000, "internal_cost": 4000}
        rl = s.post(f"{API}/quotes/{qid}/lines", json=line, timeout=30)
        assert rl.status_code in (200, 201), rl.text

        # GET quote defaults
        rq = s.get(f"{API}/quotes/{qid}", timeout=30)
        assert rq.status_code == 200, rq.text
        q = rq.json()
        assert q.get("delivery_mode") == "STANDARD", f"delivery_mode={q.get('delivery_mode')}"
        assert q.get("estimated_delivery_min_days") == 90, q.get("estimated_delivery_min_days")
        assert float(q.get("delivery_surcharge_amount") or 0) == 0.0

        # PATCH EXPRESS → 400 EXPRESS_DELIVERY_NOT_READY_FOR_CUSTOMER_USE
        rp = s.patch(f"{API}/quotes/{qid}", json={"delivery_mode": "EXPRESS"}, timeout=30)
        assert rp.status_code == 400, f"expected 400 got {rp.status_code}: {rp.text}"
        detail = rp.json().get("detail", {})
        code = detail.get("code") if isinstance(detail, dict) else None
        assert code == "EXPRESS_DELIVERY_NOT_READY_FOR_CUSTOMER_USE", f"code={code} body={rp.text}"

        # Verify still STANDARD, total 12200
        rq2 = s.get(f"{API}/quotes/{qid}", timeout=30)
        q2 = rq2.json()
        assert q2.get("delivery_mode") == "STANDARD"
        total = float(q2.get("total") or q2.get("total_amount") or 0)
        assert abs(total - 12200.0) < 0.5, f"total={total}"

        # PATCH FULL_UPFRONT → 5% discount
        rp2 = s.patch(f"{API}/quotes/{qid}", json={"payment_terms": "FULL_UPFRONT"}, timeout=30)
        assert rp2.status_code == 200, rp2.text
        rq3 = s.get(f"{API}/quotes/{qid}", timeout=30)
        q3 = rq3.json()
        assert float(q3.get("automatic_discount_percent") or 0) == 5.0, q3.get("automatic_discount_percent")
        assert abs(float(q3.get("payment_discount_amount") or 0) - 500.0) < 0.5
        assert abs(float(q3.get("subtotal") or 0) - 9500.0) < 0.5
        total3 = float(q3.get("total") or q3.get("total_amount") or 0)
        assert abs(total3 - 11590.0) < 0.5, f"total={total3}"

        # PATCH ENEA
        rp3 = s.patch(f"{API}/quotes/{qid}",
                      json={"tax_deduction_requested": True, "enea_practice_code": "ENEA_STANDARD"},
                      timeout=30)
        assert rp3.status_code == 200, rp3.text
        rq4 = s.get(f"{API}/quotes/{qid}", timeout=30)
        q4 = rq4.json()

        # find ENEA line with base_price 100
        lines = q4.get("lines") or q4.get("line_items") or []
        enea_lines = [ln for ln in lines if ln.get("enea_practice")]
        assert enea_lines, f"no enea line found in {[ln.get('description') for ln in lines]}"
        assert abs(float(enea_lines[0].get("base_price") or 0) - 100.0) < 0.01, enea_lines[0].get("base_price")

        fs = q4.get("financial_snapshot") or {}
        # ENEA costing definitivo (50 € standard / 120 € assicurata, msg 620): il costo interno è configurato,
        # quindi nessun MISSING_INTERNAL_COST_ENEA e snapshot non bloccato da ENEA.
        errs = fs.get("financial_snapshot_errors") or []
        assert "MISSING_INTERNAL_COST_ENEA" not in errs, errs
        assert q4.get("withholding_applicable") is True


# §4 PROFILING service on PROEVOLUTION line
class TestProfilingPO:
    def test_profiling_needs_po(self, s, customer_id):
        # get product_id for PROEVOLUTION
        rp = s.get(f"{API}/multi-cat/products?category_code=FINESTRE", timeout=30)
        assert rp.status_code == 200, rp.text
        prods = rp.json()
        if isinstance(prods, dict):
            prods = prods.get("items") or prods.get("data") or []
        proe = next((p for p in prods if (p.get("product_code") or p.get("code") or p.get("key") or p.get("product_key")) == "PROEVOLUTION"), None)
        assert proe, f"PROEVOLUTION not found in {[p.get('product_code') or p.get('code') or p.get('key') for p in prods]}"
        product_id = proe.get("id") or proe.get("product_id")

        qid = _create_quote(s, customer_id, "TEST_PO403_PROFILING")

        line = {
            "category": "finestre",
            "product_key": "PROEVOLUTION",
            "quantity": 1,
            "base_price": 1,
            "description": "F",
            "source": "MULTI_CATEGORY_V1",
            "category_code": "FINESTRE",
            "product_id": product_id,
            "product_code": "PROEVOLUTION",
            "pricing_model": "FORMULA_TECHNICAL",
            "width_mm": 1200,
            "height_mm": 1500,
            "configuration_snapshot": {
                "product_key": "PROEVOLUTION",
                "window_type": "WINDOW",
                "number_of_sashes": 1,
                "width_mm": 1200,
                "height_mm": 1500,
                "color_internal": "WHITE_MASS",
                "color_external": "WHITE_MASS",
                "glass_type": "DOUBLE_STANDARD",
                "quantity": 1,
            },
        }
        rl = s.post(f"{API}/quotes/{qid}/lines", json=line, timeout=60)
        assert rl.status_code in (200, 201), rl.text
        body = rl.json()

        # Look for automatic_services PROFILING
        auto_services = body.get("automatic_services") or []
        # may be at quote level; fetch quote
        rq = s.get(f"{API}/quotes/{qid}", timeout=30)
        q = rq.json()
        if not auto_services:
            auto_services = q.get("automatic_services") or []
            if not auto_services:
                for ln in (q.get("lines") or []):
                    svc = ln.get("automatic_services") or []
                    auto_services.extend(svc)
        prof = next((a for a in auto_services if (a.get("code") or a.get("service_code") or "").upper() == "PROFILING"), None)
        assert prof, f"no PROFILING in {[a.get('code') or a.get('service_code') for a in auto_services]}"
        assert abs(float(prof.get("perimeter_ml") or 0) - 5.4) < 0.01, prof.get("perimeter_ml")
        assert abs(float(prof.get("unit_sale_price") or 0) - 43.2) < 0.01, prof.get("unit_sale_price")
        assert prof.get("internal_cost_status") == "NEEDS_PO_COSTING", prof.get("internal_cost_status")

        fs = q.get("financial_snapshot") or {}
        assert fs.get("financial_snapshot_status") == "INCOMPLETE", fs
        errs = fs.get("financial_snapshot_errors") or []
        assert "MISSING_INTERNAL_COST_PROFILING" in errs, errs


# §5 static check
class TestFoilSurchargeStatic:
    def test_grep(self):
        p = "/app/backend/app/services/pricing_v3/formulas.py"
        with open(p) as f:
            src = f.read()
        assert 'STANDARD_FOIL_SURCHARGE_PERCENT = Decimal("10")' in src
        assert 'STANDARD_FOIL_SURCHARGE_STATUS = "ACTIVE"' in src
