"""PO msg 407 §1-§6 — ENEA costi interni definitivi: STANDARD 100/50, INSURED 350/120 → OTHER_DIRECT_COSTS, snapshot COMPLETE."""
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
    qid = admin.post(f"{BASE_URL}/api/quotes", json={"title": "ENEA", "customer_id": cid}, timeout=20).json()["id"]
    admin.post(f"{BASE_URL}/api/quotes/{qid}/lines", json={"category": "window", "description": "W", "quantity": 1, "base_price": 10000, "internal_cost": 4000}, timeout=20)
    admin.post(f"{BASE_URL}/api/quotes/{qid}/lines", json={"category": "extra", "description": "Other", "quantity": 1, "base_price": 500, "internal_cost": 500}, timeout=20)
    return qid


@pytest.mark.parametrize("code,sale,cost", [("ENEA_STANDARD", 100.0, 50.0), ("ENEA_INSURED", 350.0, 120.0)])
def test_enea_cost_in_other_direct_costs(admin, code, sale, cost):
    qid = _quote(admin)
    q0 = admin.get(f"{BASE_URL}/api/quotes/{qid}", timeout=20).json()
    fs0 = q0["financial_snapshot"]
    q = admin.patch(f"{BASE_URL}/api/quotes/{qid}", json={"tax_deduction_requested": True, "enea_practice_code": code}, timeout=20).json()
    fs = q["financial_snapshot"]
    enea = [l for l in q["lines"] if l.get("enea_practice")][0]
    assert enea["base_price"] == sale and enea["internal_cost"] == cost
    assert fs["net_revenue_ex_vat"] == round(fs0["net_revenue_ex_vat"] + sale, 2)
    assert fs["other_direct_costs"] == round(fs0["other_direct_costs"] + cost, 2)
    assert fs["supply_cost"] == fs0["supply_cost"] and fs["installation_cost"] == fs0["installation_cost"]
    assert "MISSING_INTERNAL_COST_ENEA" not in fs["financial_snapshot_errors"]
    assert fs["financial_snapshot_status"] == "COMPLETE" and fs["commission_status"] == "OK"
    # il costo ENEA è realmente sottratto nelle formule (con withholding 11% attivo)
    exp_pre = fs["net_revenue_ex_vat"] - fs["supply_cost"] - fs["installation_cost"] - fs["other_direct_costs"] - fs["withholding_cost"]
    assert abs(fs["pre_commission_contribution"] - exp_pre) < 0.02
    assert abs(fs["final_company_contribution"] - (exp_pre - fs["commission_gross"])) < 0.02
    assert fs["tachometer_value"] == fs["final_company_margin"]
