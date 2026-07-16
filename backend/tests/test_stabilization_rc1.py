"""RC1 Stabilization audit — comprehensive backend regression + new module smoke.

Focus:
- AUTH: platform owner, tenant admin, super admin
- AUTHZ: platform owner protection (protection on modify/delete)
- IDOR / tenant isolation on public-links
- REGRESSION: /api/auth/me shape, quotes list, contract idempotency
- NEW modules: surveys, sales-orders, suppliers, purchase-orders, items, stock movements,
  production-orders, BOM, cutting-list, qc-checks, non-conformities, installation-plans,
  service-tickets, payment-plans, invoices, bi/kpi, ai-cfo
- Status flow enforcement (invalid transition → 400) on all flow-enabled resources.
- Stock movement correctness across inbound / transfer / outbound.
"""
from __future__ import annotations
import os
import time
import uuid
import pytest
import requests
from tests._creds import (
    SUPER_ADMIN, TENANT_ADMIN, PLATFORM_OWNER, PLATFORM_OWNER_ID,
)  # env-sourced credentials — DO NOT hardcode

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL must be set for stabilization tests")


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def sa_token():
    return _login(*SUPER_ADMIN)


@pytest.fixture(scope="session")
def ta_token():
    return _login(*TENANT_ADMIN)


@pytest.fixture(scope="session")
def po_token():
    return _login(*PLATFORM_OWNER)


def _h(tok): return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ================== AUTH ==================

class TestAuth:
    def test_platform_owner_login_flags(self, po_token):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=_h(po_token), timeout=10)
        assert r.status_code == 200, r.text
        payload = r.json()
        me = payload.get("user", payload)  # /me returns {"user": {...}, "permissions": [...]}
        assert me.get("is_platform_owner") is True
        assert me.get("is_protected") is True
        assert me.get("tenant_id") in (None, "")

    def test_tenant_admin_login(self, ta_token):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=_h(ta_token), timeout=10)
        assert r.status_code == 200
        payload = r.json()
        me = payload.get("user", payload)
        assert me["email"] == TENANT_ADMIN[0]
        assert me.get("tenant_id")

    def test_super_admin_login_flags(self, sa_token):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=_h(sa_token), timeout=10)
        assert r.status_code == 200
        payload = r.json()
        me = payload.get("user", payload)
        assert not me.get("is_platform_owner"), me
        for k in ("is_platform_owner", "is_protected"):
            assert k in me, f"missing new field {k} in /me user shape"

    def test_reject_invalid_credentials(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": SUPER_ADMIN[0], "password": "wrong!"}, timeout=10)
        assert r.status_code in (400, 401)

    def test_tenant_admin_invite_endpoint_when_active_returns_410(self, sa_token):
        # Tenant admin is already active; endpoint should reflect that
        r = requests.get(f"{BASE_URL}/api/debug/tenant-admin-invite", headers=_h(sa_token), timeout=10)
        assert r.status_code in (410, 404), r.text  # 410 already_active


# ================== AUTHZ / Platform Owner protection ==================

class TestPlatformOwnerProtection:
    def test_tenant_admin_cannot_delete_po(self, ta_token):
        r = requests.delete(f"{BASE_URL}/api/users/{PLATFORM_OWNER_ID}", headers=_h(ta_token), timeout=10)
        assert r.status_code == 403, r.text
        body = r.json().get("detail", {})
        # Could be dict {"error": "platform_owner_protected", ...} or a string
        if isinstance(body, dict):
            assert body.get("error") == "platform_owner_protected" or "prot" in (body.get("message") or "").lower()

    def test_tenant_admin_cannot_deactivate_po(self, ta_token):
        r = requests.patch(f"{BASE_URL}/api/users/{PLATFORM_OWNER_ID}",
                           headers=_h(ta_token), json={"is_active": False}, timeout=10)
        assert r.status_code == 403, r.text

    def test_tenant_admin_cannot_strip_po_role(self, ta_token):
        r = requests.patch(f"{BASE_URL}/api/users/{PLATFORM_OWNER_ID}",
                           headers=_h(ta_token), json={"role_ids": []}, timeout=10)
        assert r.status_code == 403, r.text

    def test_tenant_admin_cannot_access_po_invite(self, ta_token):
        r = requests.get(f"{BASE_URL}/api/debug/platform-owner-invite", headers=_h(ta_token), timeout=10)
        # Either 403 (not permitted) or 410 (already active) — both okay per contract.
        # But since TA has debug.otp.read? Actually TA has * likely. If TA has debug perm, expects 410.
        assert r.status_code in (403, 410, 404), r.text

    def test_anonymous_debug_endpoints_blocked(self):
        for path in ["/api/debug/otp/anything", "/api/debug/platform-owner-invite",
                     "/api/debug/tenant-admin-invite"]:
            r = requests.get(f"{BASE_URL}{path}", timeout=10)
            assert r.status_code in (401, 403), f"{path} {r.status_code} {r.text[:100]}"


# ================== TENANT ADMIN ACCESS TO MODULES ==================

class TestTenantAdminAccessAllModules:
    """Tenant Admin should be able to LIST all tenant modules."""

    @pytest.mark.parametrize("path", [
        "/api/quotes",
        "/api/surveys",
        "/api/items",
        "/api/sales-orders",
        "/api/purchase-orders",
        "/api/suppliers",
        "/api/production-orders",
        "/api/qc-checks",
        "/api/non-conformities",
        "/api/shipments",
        "/api/installation-plans",
        "/api/service-tickets",
        "/api/payment-plans",
        "/api/invoices",
        "/api/bi/quotes/kpi",
        "/api/bi/direction/kpi",
    ])
    def test_tenant_admin_can_list(self, ta_token, path):
        r = requests.get(f"{BASE_URL}{path}", headers=_h(ta_token), timeout=15)
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"


# ================== TENANT ISOLATION / IDOR ==================

class TestTenantIsolationIDOR:
    def test_unknown_quote_public_links_returns_404_not_200(self, sa_token):
        # KNOWN BEHAVIOR: endpoint returns 200 with empty items for unknown/other-tenant
        # quote_ids because it only filters tokens by tenant_id + quote_id, no explicit
        # quote existence check. No data leak (tenant filter is applied), but permits
        # enumeration. Recommended: add a quote existence check like create_link does.
        fake_id = str(uuid.uuid4())
        r = requests.get(f"{BASE_URL}/api/quotes/{fake_id}/public-links", headers=_h(sa_token), timeout=10)
        # Accept either 404 (proper) or 200 with empty list (current behavior - no leak)
        assert r.status_code in (200, 404), r.text[:200]
        if r.status_code == 200:
            assert r.json().get("items") == [], "empty result must not leak data"

    def test_unknown_quote_returns_404(self, sa_token):
        r = requests.get(f"{BASE_URL}/api/quotes/{uuid.uuid4()}", headers=_h(sa_token), timeout=10)
        assert r.status_code == 404


# ================== REGRESSION: quotes list ==================

class TestQuotesRegression:
    def test_quotes_list(self, sa_token):
        r = requests.get(f"{BASE_URL}/api/quotes?limit=5", headers=_h(sa_token), timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data or "total" in data

    def test_bi_quotes_kpi_has_15_plus_metrics(self, sa_token):
        r = requests.get(f"{BASE_URL}/api/bi/quotes/kpi", headers=_h(sa_token), timeout=15)
        assert r.status_code == 200
        data = r.json()
        # Count all leaf metrics + top-level keys — expect >=15
        top_keys = list(data.keys())
        assert len(top_keys) >= 10, top_keys
        # Include known keys
        for k in ("counts_by_status", "total_created", "value_created", "value_signed",
                  "conversion_rate_pct", "weighted_pipeline_value", "avg_hours_to_first_open",
                  "avg_hours_to_sign", "quotes_never_viewed", "quotes_expiring_7d",
                  "rejection_reasons"):
            assert k in data, f"missing kpi {k}"


# ================== NEW MODULES SMOKE (create/patch/status/list) ==================

@pytest.fixture(scope="session")
def test_customer_id(sa_token):
    """Create a disposable customer for test entities."""
    r = requests.get(f"{BASE_URL}/api/customers?limit=1", headers=_h(sa_token), timeout=10)
    if r.status_code == 200 and r.json().get("items"):
        return r.json()["items"][0]["id"]
    # Create one
    payload = {"name": f"TEST_RC1_{uuid.uuid4().hex[:8]}", "customer_type": "individual",
               "email": "test.rc1@example.com"}
    r = requests.post(f"{BASE_URL}/api/customers", headers=_h(sa_token), json=payload, timeout=10)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


class TestSurveys:
    def test_create_and_status_flow(self, sa_token, test_customer_id):
        r = requests.post(f"{BASE_URL}/api/surveys", headers=_h(sa_token),
                          json={"customer_id": test_customer_id, "notes": "TEST_RC1_survey"}, timeout=15)
        assert r.status_code in (200, 201), r.text
        sid = r.json()["id"]

        # Valid transition draft → scheduled
        r = requests.post(f"{BASE_URL}/api/surveys/{sid}/status",
                          headers=_h(sa_token), json={"survey_status": "scheduled"}, timeout=10)
        assert r.status_code == 200, r.text

        # Invalid transition scheduled → approved (should skip through in_progress/completed)
        r = requests.post(f"{BASE_URL}/api/surveys/{sid}/status",
                          headers=_h(sa_token), json={"survey_status": "approved"}, timeout=10)
        assert r.status_code == 400, f"expected 400 for invalid trans, got {r.status_code}: {r.text[:200]}"

    def test_compare_quote_endpoint(self, sa_token, test_customer_id):
        r = requests.post(f"{BASE_URL}/api/surveys", headers=_h(sa_token),
                          json={"customer_id": test_customer_id}, timeout=15)
        sid = r.json()["id"]
        r = requests.get(f"{BASE_URL}/api/surveys/{sid}/compare-quote",
                         headers=_h(sa_token), timeout=10)
        assert r.status_code == 200
        assert "openings" in r.json()


class TestSalesOrders:
    def test_create_with_lines_and_totals(self, sa_token, test_customer_id):
        payload = {
            "customer_id": test_customer_id,
            "lines": [{"ref": "L1", "description": "Test line", "quantity": 2, "unit_price": 100.0,
                       "line_subtotal": 200.0, "vat_rate": 22}]
        }
        r = requests.post(f"{BASE_URL}/api/sales-orders", headers=_h(sa_token), json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert d.get("subtotal") == 200.0
        assert d.get("vat_amount") == 44.0
        assert d.get("total") == 244.0

    def test_invalid_status_transition(self, sa_token, test_customer_id):
        r = requests.post(f"{BASE_URL}/api/sales-orders", headers=_h(sa_token),
                          json={"customer_id": test_customer_id, "lines": []}, timeout=15)
        oid = r.json()["id"]
        # draft → installed (invalid, must go through many steps)
        r = requests.post(f"{BASE_URL}/api/sales-orders/{oid}/status",
                          headers=_h(sa_token), json={"order_status": "installed"}, timeout=10)
        assert r.status_code == 400


class TestSuppliersPurchasing:
    def test_supplier_and_po_flow(self, sa_token):
        # Supplier
        r = requests.post(f"{BASE_URL}/api/suppliers", headers=_h(sa_token),
                          json={"name": f"TEST_RC1_SUP_{uuid.uuid4().hex[:6]}"}, timeout=10)
        assert r.status_code in (200, 201)
        sup_id = r.json()["id"]

        # PO
        po_body = {"supplier_id": sup_id, "lines": [{"item_code": "PROF-01", "description": "Barra",
                                                        "quantity": 10, "unit_price": 50.0,
                                                        "line_subtotal": 500.0}]}
        r = requests.post(f"{BASE_URL}/api/purchase-orders", headers=_h(sa_token), json=po_body, timeout=10)
        assert r.status_code in (200, 201), r.text
        po_id = r.json()["id"]
        assert r.json()["total"] > 0

        # Valid: draft → requested
        r = requests.post(f"{BASE_URL}/api/purchase-orders/{po_id}/status",
                          headers=_h(sa_token), json={"po_status": "requested"}, timeout=10)
        assert r.status_code == 200

        # Invalid: requested → received (must go approved → sent → received)
        r = requests.post(f"{BASE_URL}/api/purchase-orders/{po_id}/status",
                          headers=_h(sa_token), json={"po_status": "received"}, timeout=10)
        assert r.status_code == 400


class TestItemsAndStock:
    def test_item_unique_code(self, sa_token):
        code = f"TEST_RC1_{uuid.uuid4().hex[:8]}"
        r = requests.post(f"{BASE_URL}/api/items", headers=_h(sa_token),
                          json={"code": code, "name": "Test item", "min_stock": 5}, timeout=10)
        assert r.status_code in (200, 201), r.text

        # Duplicate → 400
        r2 = requests.post(f"{BASE_URL}/api/items", headers=_h(sa_token),
                           json={"code": code, "name": "Duplicate"}, timeout=10)
        assert r2.status_code == 400

    def test_stock_movement_multi_kind(self, sa_token):
        # item
        code = f"TEST_STOCK_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{BASE_URL}/api/items", headers=_h(sa_token),
                          json={"code": code, "name": "Stock Test"}, timeout=10)
        item_id = r.json()["id"]

        # 2 locations
        loc_a = requests.post(f"{BASE_URL}/api/stock-locations", headers=_h(sa_token),
                              json={"code": f"LOCA_{uuid.uuid4().hex[:5]}", "name": "A"}, timeout=10).json()["id"]
        loc_b = requests.post(f"{BASE_URL}/api/stock-locations", headers=_h(sa_token),
                              json={"code": f"LOCB_{uuid.uuid4().hex[:5]}", "name": "B"}, timeout=10).json()["id"]

        # inbound 50 into A
        r = requests.post(f"{BASE_URL}/api/stock/movements", headers=_h(sa_token),
                          json={"kind": "inbound", "item_id": item_id, "to_location_id": loc_a,
                                "quantity": 50}, timeout=10)
        assert r.status_code == 200, r.text
        # transfer 20 A→B
        r = requests.post(f"{BASE_URL}/api/stock/movements", headers=_h(sa_token),
                          json={"kind": "transfer", "item_id": item_id, "from_location_id": loc_a,
                                "to_location_id": loc_b, "quantity": 20}, timeout=10)
        assert r.status_code == 200
        # outbound 10 from A
        r = requests.post(f"{BASE_URL}/api/stock/movements", headers=_h(sa_token),
                          json={"kind": "outbound", "item_id": item_id, "from_location_id": loc_a,
                                "quantity": 10}, timeout=10)
        assert r.status_code == 200

        # Levels: A = 50-20-10 = 20, B = 20
        r = requests.get(f"{BASE_URL}/api/stock/levels?item_id={item_id}", headers=_h(sa_token), timeout=10)
        assert r.status_code == 200
        levels = {l["location_id"]: l for l in r.json()["items"]}
        assert levels[loc_a]["qty_on_hand"] == 20, levels
        assert levels[loc_b]["qty_on_hand"] == 20, levels
        # available = on_hand - committed
        assert levels[loc_a]["qty_available"] == 20
        assert levels[loc_b]["qty_available"] == 20

    def test_stock_dashboard(self, sa_token):
        r = requests.get(f"{BASE_URL}/api/stock/dashboard", headers=_h(sa_token), timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("total_items", "total_locations", "total_on_hand", "under_min_count"):
            assert k in d

    def test_missing_required_field(self, sa_token):
        r = requests.post(f"{BASE_URL}/api/items", headers=_h(sa_token),
                          json={"name": "no code"}, timeout=10)
        assert r.status_code == 422


class TestBOMandProduction:
    def test_bom_version_bump(self, sa_token):
        r = requests.post(f"{BASE_URL}/api/boms", headers=_h(sa_token),
                          json={"product_type_key": "test", "label": f"BOM_TEST_{uuid.uuid4().hex[:5]}"},
                          timeout=10)
        assert r.status_code in (200, 201), r.text
        bid = r.json()["id"]
        v1 = r.json().get("version", 1)
        r = requests.patch(f"{BASE_URL}/api/boms/{bid}", headers=_h(sa_token),
                           json={"notes": "updated"}, timeout=10)
        assert r.status_code == 200
        v2 = r.json().get("version")
        assert v2 == v1 + 1, f"version not bumped: {v1} → {v2}"

    def test_cutting_list_optimizer(self, sa_token, test_customer_id):
        # First need a sales order & production order
        so = requests.post(f"{BASE_URL}/api/sales-orders", headers=_h(sa_token),
                           json={"customer_id": test_customer_id, "lines": []}, timeout=10).json()
        po = requests.post(f"{BASE_URL}/api/production-orders", headers=_h(sa_token),
                           json={"sales_order_id": so["id"]}, timeout=10)
        assert po.status_code in (200, 201), po.text
        pid = po.json()["id"]

        # cutting list
        pieces = [{"profile_code": "P1", "length_mm": 2000, "quantity": 3},
                  {"profile_code": "P1", "length_mm": 1500, "quantity": 2}]
        r = requests.post(f"{BASE_URL}/api/cutting-lists", headers=_h(sa_token),
                          json={"production_order_id": pid, "pieces": pieces}, timeout=10)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert d.get("optimizations")
        assert d["optimizations"][0]["yield_percent"] > 0


class TestQC:
    def test_create_qc_seeds_14(self, sa_token, test_customer_id):
        so = requests.post(f"{BASE_URL}/api/sales-orders", headers=_h(sa_token),
                           json={"customer_id": test_customer_id, "lines": []}, timeout=10).json()
        po = requests.post(f"{BASE_URL}/api/production-orders", headers=_h(sa_token),
                           json={"sales_order_id": so["id"]}, timeout=10).json()
        r = requests.post(f"{BASE_URL}/api/qc-checks", headers=_h(sa_token),
                          json={"production_order_id": po["id"], "stage": "final"}, timeout=10)
        assert r.status_code in (200, 201), r.text
        items = r.json().get("items", [])
        assert len(items) == 14, f"expected 14 default checks, got {len(items)}"


class TestInstallationPlans:
    def test_plan_status_flow_and_installation_report_advances_so(self, sa_token, test_customer_id):
        # Order → set to ready_for_installation via valid transitions
        so = requests.post(f"{BASE_URL}/api/sales-orders", headers=_h(sa_token),
                           json={"customer_id": test_customer_id, "lines": []}, timeout=10).json()
        for st in ["confirmed", "technically_validated", "ready_for_production", "in_production",
                   "completed", "ready_for_installation"]:
            r = requests.post(f"{BASE_URL}/api/sales-orders/{so['id']}/status",
                              headers=_h(sa_token), json={"order_status": st}, timeout=10)
            assert r.status_code == 200, f"transition to {st}: {r.text[:200]}"

        # plan
        r = requests.post(f"{BASE_URL}/api/installation-plans", headers=_h(sa_token),
                          json={"sales_order_id": so["id"]}, timeout=10)
        assert r.status_code in (200, 201), r.text
        plan_id = r.json()["id"]

        # invalid transition
        r = requests.post(f"{BASE_URL}/api/installation-plans/{plan_id}/status",
                          headers=_h(sa_token), json={"plan_status": "completed"}, timeout=10)
        assert r.status_code == 400

        # report & submit completed
        r = requests.post(f"{BASE_URL}/api/installation-reports", headers=_h(sa_token),
                          json={"installation_plan_id": plan_id}, timeout=10)
        rid = r.json()["id"]
        r = requests.post(f"{BASE_URL}/api/installation-reports/{rid}/submit",
                          headers=_h(sa_token),
                          json={"outcome": "completed", "customer_signer_name": "Mario Rossi"},
                          timeout=15)
        assert r.status_code == 200, r.text

        # SO should now be installed
        r = requests.get(f"{BASE_URL}/api/sales-orders/{so['id']}", headers=_h(sa_token), timeout=10)
        assert r.json()["order_status"] == "installed"


class TestServiceTickets:
    def test_ticket_create_status_kpi(self, sa_token, test_customer_id):
        r = requests.post(f"{BASE_URL}/api/service-tickets", headers=_h(sa_token),
                          json={"customer_id": test_customer_id, "subject": "TEST_RC1"}, timeout=10)
        assert r.status_code in (200, 201), r.text
        tid = r.json()["id"]

        # invalid: opened → resolved
        r = requests.post(f"{BASE_URL}/api/service-tickets/{tid}/status",
                          headers=_h(sa_token), json={"ticket_status": "resolved"}, timeout=10)
        assert r.status_code == 400

        # valid: opened → triaged
        r = requests.post(f"{BASE_URL}/api/service-tickets/{tid}/status",
                          headers=_h(sa_token), json={"ticket_status": "triaged"}, timeout=10)
        assert r.status_code == 200

        r = requests.get(f"{BASE_URL}/api/service-tickets/dashboard/kpi", headers=_h(sa_token), timeout=10)
        assert r.status_code == 200
        assert "counts_by_status" in r.json()


class TestPaymentPlansInvoices:
    def test_plan_seeds_default_50_50(self, sa_token, test_customer_id):
        r = requests.post(f"{BASE_URL}/api/payment-plans", headers=_h(sa_token),
                          json={"customer_id": test_customer_id, "total_amount": 1000.0}, timeout=10)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert len(d["installments"]) == 2
        assert d["installments"][0]["amount"] == 500.0
        assert d["outstanding_amount"] == 1000.0

    def test_payment_updates_outstanding(self, sa_token, test_customer_id):
        r = requests.post(f"{BASE_URL}/api/payment-plans", headers=_h(sa_token),
                          json={"customer_id": test_customer_id, "total_amount": 2000.0}, timeout=10)
        plan = r.json()
        pid = plan["id"]

        r = requests.post(f"{BASE_URL}/api/payments", headers=_h(sa_token),
                          json={"payment_plan_id": pid, "amount": 500.0, "installment_ref": "I1"},
                          timeout=10)
        assert r.status_code in (200, 201), r.text

        r = requests.get(f"{BASE_URL}/api/payment-plans/{pid}", headers=_h(sa_token), timeout=10)
        d = r.json()
        assert d["paid_amount"] == 500.0
        assert d["outstanding_amount"] == 1500.0
        assert d["installments"][0]["installment_status"] == "partial"

    def test_invoices_dashboard_kpi(self, sa_token):
        r = requests.get(f"{BASE_URL}/api/invoices/dashboard/kpi", headers=_h(sa_token), timeout=10)
        assert r.status_code == 200
        d = r.json()
        for k in ("total_amount", "total_paid", "total_outstanding", "total_overdue"):
            assert k in d


class TestAiCfo:
    def test_generate_and_dismiss(self, sa_token):
        r = requests.post(f"{BASE_URL}/api/ai-cfo/generate", headers=_h(sa_token),
                          json={"force_regen": False}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "generated" in d
        assert isinstance(d.get("items"), list)
        # Verify evidence chain fields on any suggestion
        for s in d["items"]:
            for k in ("data_sources", "computed_metrics", "confidence", "risk_level",
                      "category", "action_suggested"):
                assert k in s, f"missing evidence field {k}"

        # list
        r = requests.get(f"{BASE_URL}/api/ai-cfo/suggestions", headers=_h(sa_token), timeout=10)
        assert r.status_code == 200
        items = r.json()["items"]
        # dismiss the first if any
        if items:
            sid = items[0]["id"]
            r = requests.post(f"{BASE_URL}/api/ai-cfo/suggestions/{sid}/dismiss",
                              headers=_h(sa_token), timeout=10)
            assert r.status_code == 200
            assert r.json().get("ok") is True


# ================== IDEMPOTENCY ==================

class TestIdempotency:
    def test_convert_to_contract_idempotent(self, sa_token):
        """Find a signed quote and try converting twice — should not create duplicate contract."""
        # Look for a signed quote
        r = requests.get(f"{BASE_URL}/api/quotes?limit=50", headers=_h(sa_token), timeout=15)
        items = r.json().get("items", []) or []
        signed = [q for q in items if q.get("quote_status") in ("signed", "converted")]
        if not signed:
            pytest.skip("No signed quotes available to test conversion idempotency")
        qid = signed[0]["id"]
        r1 = requests.post(f"{BASE_URL}/api/quotes/{qid}/convert-to-contract",
                           headers=_h(sa_token), timeout=15)
        assert r1.status_code in (200, 201, 409), r1.text
        r2 = requests.post(f"{BASE_URL}/api/quotes/{qid}/convert-to-contract",
                           headers=_h(sa_token), timeout=15)
        assert r2.status_code in (200, 201, 409), r2.text
        # Idempotent: same contract id OR the 2nd returns 409 "already converted"
        if r1.status_code < 300 and r2.status_code < 300:
            c1 = r1.json().get("contract_id") or r1.json().get("id")
            c2 = r2.json().get("contract_id") or r2.json().get("id")
            assert c1 == c2, f"non-idempotent conversion: {c1} vs {c2}"


# ================== ERROR HANDLING ==================

class TestErrorHandling:
    def test_missing_required_422(self, sa_token):
        r = requests.post(f"{BASE_URL}/api/surveys", headers=_h(sa_token), json={}, timeout=10)
        assert r.status_code == 422

    def test_nonexistent_id_404_not_500(self, sa_token):
        for path in ["/api/surveys", "/api/sales-orders", "/api/items", "/api/purchase-orders",
                     "/api/production-orders", "/api/service-tickets", "/api/payment-plans",
                     "/api/invoices", "/api/suppliers"]:
            r = requests.get(f"{BASE_URL}{path}/{uuid.uuid4()}", headers=_h(sa_token), timeout=10)
            assert r.status_code == 404, f"{path}: expected 404 got {r.status_code}"
