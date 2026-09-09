"""PO msg 407 §7-§30 — sconto globale preventivo + promo code (tenant-scoped, backend-validated), IVA dopo sconto, margine ricalcolato."""
import os, pytest, requests
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"]}, timeout=20)
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


def _quote(admin):
    cust = admin.get(f"{BASE_URL}/api/customers?limit=1", timeout=20).json()
    cid = (cust.get("items") or cust)[0]["id"]
    qid = admin.post(f"{BASE_URL}/api/quotes", json={"title": "DISC", "customer_id": cid}, timeout=20).json()["id"]
    admin.post(f"{BASE_URL}/api/quotes/{qid}/lines", json={"category": "window", "description": "W", "quantity": 1, "base_price": 8500, "internal_cost": 4000}, timeout=20)
    admin.post(f"{BASE_URL}/api/quotes/{qid}/lines", json={"category": "installation", "description": "P", "quantity": 1, "base_price": 1000, "internal_cost": 1000}, timeout=20)
    admin.post(f"{BASE_URL}/api/quotes/{qid}/lines", json={"category": "extra", "description": "O", "quantity": 1, "base_price": 500, "internal_cost": 500}, timeout=20)
    return qid


def _patch(admin, qid, body):
    r = admin.patch(f"{BASE_URL}/api/quotes/{qid}", json=body, timeout=20)
    return r.status_code, r.json()


def test_golden_10pct_manual(admin):
    qid = _quote(admin)
    st, q = _patch(admin, qid, {"global_discount_percent": 10})
    assert st == 200
    fs = q["financial_snapshot"]
    assert q["commercial_subtotal"] == 10000 and q["global_discount_amount"] == 1000 and q["subtotal"] == 9000
    assert q["vat_amount"] == round(q["vat_amount"], 2) and abs(q["total"] - (9000 + q["vat_amount"])) < 0.01  # IVA dopo sconto
    assert fs["net_revenue_ex_vat"] == 9000 and fs["supply_cost"] == 4000 and fs["installation_cost"] == 1000 and fs["other_direct_costs"] == 500
    assert fs["pre_commission_contribution"] == 3500 and abs(fs["pre_commission_margin"] - 38.8889) < 0.01
    assert fs["commission_rate"] == 0.15 and fs["commission_gross"] == 1350
    assert fs["final_company_contribution"] == 2150 and abs(fs["final_company_margin"] - 23.89) < 0.01
    assert fs["tachometer_value"] == fs["final_company_margin"]
    # persist / reload
    q2 = admin.get(f"{BASE_URL}/api/quotes/{qid}", timeout=20).json()
    assert q2["global_discount_amount"] == 1000 and q2["total"] == q["total"] and q2["financial_snapshot"]["tachometer_value"] == fs["tachometer_value"]
    # modify → recompute on new base (§21)
    admin.post(f"{BASE_URL}/api/quotes/{qid}/lines", json={"category": "window", "description": "W2", "quantity": 1, "base_price": 2000, "internal_cost": 800}, timeout=20)
    q3 = admin.get(f"{BASE_URL}/api/quotes/{qid}", timeout=20).json()
    assert q3["commercial_subtotal"] == 12000 and q3["global_discount_amount"] == 1200 and q3["subtotal"] == 10800
    # remove (§22)
    st, q4 = _patch(admin, qid, {"global_discount_percent": 0})
    assert q4["global_discount_amount"] == 0 and q4["subtotal"] == 12000 and q4["financial_snapshot"]["net_revenue_ex_vat"] == 12000


def test_enea_cost_not_discounted(admin):
    qid = _quote(admin)
    _patch(admin, qid, {"tax_deduction_requested": True, "enea_practice_code": "ENEA_STANDARD"})
    st, q = _patch(admin, qid, {"global_discount_percent": 10})
    fs = q["financial_snapshot"]
    assert q["commercial_subtotal"] == 10100 and q["global_discount_amount"] == 1010 and fs["net_revenue_ex_vat"] == 9090
    assert fs["other_direct_costs"] == 550   # 500 + ENEA 50 invariato


@pytest.mark.parametrize("code,expected", [("PROMO10", 200), ("EXPIRED5", 400), ("OFF20", 400), ("NOPE", 400), ("TENANTB15", 400)])
def test_promo_codes(admin, code, expected):
    qid = _quote(admin)
    st, q = _patch(admin, qid, {"promo_code": code})
    assert st == expected, q
    q = admin.get(f"{BASE_URL}/api/quotes/{qid}", timeout=20).json()
    if expected == 200:
        assert q["promo_code"] == "PROMO10" and q["global_discount_amount"] == 1000 and q["subtotal"] == 9000
    else:
        assert q["global_discount_amount"] == 0 and q["subtotal"] == 10000 and q.get("promo_code") in (None, "")


def test_stacking_global_then_full_upfront(admin):
    qid = _quote(admin)
    _patch(admin, qid, {"promo_code": "PROMO10"})
    st, q = _patch(admin, qid, {"payment_terms": "FULL_UPFRONT"})
    # sequenziale: 10000 → -1000 → 9000 → -5% (450) → 8550
    assert q["global_discount_amount"] == 1000 and q["payment_discount_amount"] == 450 and q["subtotal"] == 8550
    assert q["total_discount_amount"] == 1450 and q["financial_snapshot"]["net_revenue_ex_vat"] == 8550


def test_frontend_cannot_set_discount_value_directly(admin):
    qid = _quote(admin)
    st, q = _patch(admin, qid, {"global_discount_value": 50, "global_discount_type": "PERCENT"})
    q = admin.get(f"{BASE_URL}/api/quotes/{qid}", timeout=20).json()
    assert q["global_discount_amount"] == 0 and q["subtotal"] == 10000
