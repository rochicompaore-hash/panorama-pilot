"""M7.TREASURY consolidation backend tests.

Coverage:
- Public landing config + lead submit (with dedup, package suggestion, invalid email/privacy)
- Platform Owner site config PATCH with email validation
- Legal Entities: fiscal gating + missing fields refresh
- Intercompany: create with mirroring + fiscal-block error + reconcile + reconciliation-report
- SaaS Platform: modules/plans/dependencies + set_module_state dependency check
- Management Control: budget simulate + preset-scenarios + fixed cost + personnel + consolidation
- Product Catalog: types (18), drawing SVG (no scripts), site-conditions evaluate
- Installation & Access rules seeded
- Regression: auth/me, quotes list, parametric preview
"""
import os
import time
import uuid
import pytest
import requests
from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD  # env-sourced credentials

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
# scrubbed: ADMIN_EMAIL moved to tests._creds
# scrubbed: ADMIN_PASSWORD moved to tests._creds
# -------------- Fixtures --------------
@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def api(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def entities(api):
    r = api.get(f"{BASE_URL}/api/legal-entities", timeout=15)
    assert r.status_code == 200
    items = r.json()["items"]
    codes = {x["code"]: x for x in items}
    return codes


# ================= AUTH / REGRESSION =================
class TestAuthRegression:
    def test_auth_me(self, api):
        r = api.get(f"{BASE_URL}/api/auth/me", timeout=10)
        assert r.status_code == 200
        d = r.json()
        # response shape: {"user": {...}, "permissions": [...]}
        user = d.get("user") if "user" in d else d
        assert user.get("email") == ADMIN_EMAIL

    def test_quotes_list(self, api):
        r = api.get(f"{BASE_URL}/api/quotes", timeout=15)
        # 200 with items list is expected
        assert r.status_code == 200
        j = r.json()
        assert "items" in j or isinstance(j, list)

    def test_parametric_endpoints_exist(self, api):
        # Verify parametric routes are wired (422 without payload = router active)
        r = api.post(f"{BASE_URL}/api/parametric/preview", json={}, timeout=10)
        assert r.status_code in (200, 400, 422), f"parametric router missing: {r.status_code}"


# ================= PUBLIC LANDING =================
class TestPublicLanding:
    def test_config_public(self):
        r = requests.get(f"{BASE_URL}/api/public-site/config", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["is_published"] is True
        assert len(d["public_module_codes"]) == 13
        assert len(d["packages"]) == 6
        # No email recipients exposed
        assert "lead_notification_recipients" not in d

    def test_lead_submit_valid_and_dedup(self):
        email = f"test_dedup_{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "first_name": "TEST_Dedup", "last_name": "User", "email": email,
            "company_name": "TEST_DedupCorp",
            "privacy_consent": True,
            "interested_module_codes": ["core_crm"],
        }
        r1 = requests.post(f"{BASE_URL}/api/public-site/leads", json=payload, timeout=15)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1["ok"] is True
        assert d1["duplicate"] is False
        assert d1["suggested_package"] == "sales"
        lead_id = d1["lead_id"]

        # Dedup — same email
        r2 = requests.post(f"{BASE_URL}/api/public-site/leads", json=payload, timeout=15)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["duplicate"] is True
        assert d2["lead_id"] == lead_id

    def test_lead_privacy_consent_missing(self):
        r = requests.post(f"{BASE_URL}/api/public-site/leads", json={
            "first_name": "T", "last_name": "T",
            "email": f"nopriv_{uuid.uuid4().hex[:6]}@example.com",
            "company_name": "TEST_NP",
            "privacy_consent": False,
        }, timeout=10)
        assert r.status_code == 400
        assert "privacy" in r.json()["detail"].lower()

    def test_lead_invalid_email_422(self):
        r = requests.post(f"{BASE_URL}/api/public-site/leads", json={
            "first_name": "T", "last_name": "T",
            "email": "not-an-email",
            "company_name": "TEST_BAD",
            "privacy_consent": True,
        }, timeout=10)
        assert r.status_code == 422

    def test_package_suggestion_enterprise(self):
        r = requests.post(f"{BASE_URL}/api/public-site/leads", json={
            "first_name": "T", "last_name": "T",
            "email": f"ent_{uuid.uuid4().hex[:6]}@example.com",
            "company_name": "TEST_ENT",
            "privacy_consent": True,
            "interested_module_codes": ["multi_company", "ai_cfo"],
        }, timeout=10)
        assert r.status_code == 200
        assert r.json()["suggested_package"] == "enterprise"

    def test_package_suggestion_production(self):
        r = requests.post(f"{BASE_URL}/api/public-site/leads", json={
            "first_name": "T", "last_name": "T",
            "email": f"prod_{uuid.uuid4().hex[:6]}@example.com",
            "company_name": "TEST_PROD",
            "privacy_consent": True,
            "has_internal_production": True,
        }, timeout=10)
        assert r.status_code == 200
        assert r.json()["suggested_package"] == "production"

    def test_package_suggestion_finance(self):
        r = requests.post(f"{BASE_URL}/api/public-site/leads", json={
            "first_name": "T", "last_name": "T",
            "email": f"fin_{uuid.uuid4().hex[:6]}@example.com",
            "company_name": "TEST_FIN",
            "privacy_consent": True,
            "interested_module_codes": ["treasury"],
        }, timeout=10)
        assert r.status_code == 200
        assert r.json()["suggested_package"] == "finance"

    def test_package_suggestion_sales(self):
        r = requests.post(f"{BASE_URL}/api/public-site/leads", json={
            "first_name": "T", "last_name": "T",
            "email": f"sal_{uuid.uuid4().hex[:6]}@example.com",
            "company_name": "TEST_SAL",
            "privacy_consent": True,
            "interested_module_codes": ["core_crm"],
        }, timeout=10)
        assert r.status_code == 200
        assert r.json()["suggested_package"] == "sales"

    def test_package_suggestion_starter_when_empty(self):
        r = requests.post(f"{BASE_URL}/api/public-site/leads", json={
            "first_name": "T", "last_name": "T",
            "email": f"stt_{uuid.uuid4().hex[:6]}@example.com",
            "company_name": "TEST_STT",
            "privacy_consent": True,
        }, timeout=10)
        assert r.status_code == 200
        assert r.json()["suggested_package"] == "starter"


# ================= PLATFORM OWNER SITE CONFIG =================
class TestPlatformSiteConfig:
    def test_get_config(self, api):
        r = api.get(f"{BASE_URL}/api/platform/site-config", timeout=10)
        assert r.status_code == 200
        d = r.json()
        # email_status can be either configured or configuration_required (may have been PATCHed previously)
        assert d["email_status"] in ("configured", "configuration_required")

    def test_patch_invalid_email_rejected(self, api):
        r = api.patch(f"{BASE_URL}/api/platform/site-config",
                      json={"lead_notification_recipients": ["checonpaorechioccilagmail.com"]},
                      timeout=10)
        assert r.status_code == 400
        assert "non valid" in r.json()["detail"].lower() or "invalid" in r.json()["detail"].lower()

    def test_patch_valid_email_sets_configured(self, api):
        r = api.patch(f"{BASE_URL}/api/platform/site-config",
                      json={"lead_notification_recipients": ["ops@infissiexpress.com",
                                                             "cfo@infissiexpress.com"]},
                      timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["email_status"] == "configured"
        assert "ops@infissiexpress.com" in d["lead_notification_recipients"]

    def test_patch_mixed_valid_and_invalid_rejected(self, api):
        r = api.patch(f"{BASE_URL}/api/platform/site-config",
                      json={"lead_notification_recipients": ["valid@ok.it", "@nope@@"]},
                      timeout=10)
        assert r.status_code == 400


# ================= LEGAL ENTITIES =================
class TestLegalEntities:
    def test_list_returns_enerhia_and_auxer(self, entities):
        assert "ENERHIA" in entities and "AUXER" in entities

    def test_fiscal_state_consistent(self, entities):
        # Either seed state (to_complete, blocked) OR unblocked (already PATCHed)
        for code, e in entities.items():
            if e["fiscal_operations_blocked"]:
                assert e["le_status"] == "to_complete"
                assert set(e["missing_fields"]).issubset({"vat_number", "tax_code", "pec"})
            else:
                assert e["le_status"] == "active"
                assert e["missing_fields"] == []

    def test_patch_fiscal_fields_unblocks(self, api, entities):
        e = entities["ENERHIA"]
        r = api.patch(f"{BASE_URL}/api/legal-entities/{e['id']}",
                      json={"vat_number": "IT12345678901",
                            "tax_code": "12345678901",
                            "pec": "enerhia@pec.it"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["fiscal_operations_blocked"] is False
        assert d["missing_fields"] == []
        assert d["le_status"] == "active"


# ================= INTERCOMPANY =================
class TestIntercompany:
    def _get_ids(self, api):
        r = api.get(f"{BASE_URL}/api/legal-entities", timeout=10)
        items = {x["code"]: x for x in r.json()["items"]}
        return items["ENERHIA"]["id"], items["AUXER"]["id"]

    def _ensure_unblocked(self, api):
        r = api.get(f"{BASE_URL}/api/legal-entities", timeout=10)
        for e in r.json()["items"]:
            if e["fiscal_operations_blocked"]:
                api.patch(f"{BASE_URL}/api/legal-entities/{e['id']}",
                          json={"vat_number": f"IT{uuid.uuid4().hex[:11]}",
                                "tax_code": uuid.uuid4().hex[:11].upper(),
                                "pec": f"{e['code'].lower()}@pec.it"}, timeout=10)

    def test_intercompany_blocked_when_fiscal_incomplete(self, api):
        # Ensure the two seed entities are unblocked first
        self._ensure_unblocked(api)
        ener_id, _ = self._get_ids(api)
        # NOW create a fresh incomplete LE (will remain blocked)
        payload = {"code": f"TEST_LE_{uuid.uuid4().hex[:6].upper()}",
                   "name": "TEST Fresh LE",
                   "legal_form": "SRL"}
        r = api.post(f"{BASE_URL}/api/legal-entities", json=payload, timeout=10)
        assert r.status_code == 200
        fresh_id = r.json()["id"]
        assert r.json()["fiscal_operations_blocked"] is True

        # Attempt intercompany create — fresh LE is blocked, must return 400
        r2 = api.post(f"{BASE_URL}/api/intercompany",
                      json={"source_legal_entity_id": fresh_id,
                            "target_legal_entity_id": ener_id,
                            "doc_kind": "invoice", "doc_ref": "TEST-BLOCK-001",
                            "amount_taxable": 1000.0, "vat_rate": 22.0}, timeout=15)
        assert r2.status_code == 400, r2.text
        assert "fiscal" in r2.json()["detail"].lower() or "incomplet" in r2.json()["detail"].lower()

    def test_intercompany_create_and_mirror(self, api):
        self._ensure_unblocked(api)
        src_id, tgt_id = self._get_ids(api)
        r = api.post(f"{BASE_URL}/api/intercompany",
                     json={"source_legal_entity_id": src_id,
                           "target_legal_entity_id": tgt_id,
                           "doc_kind": "invoice",
                           "doc_ref": f"TEST-IC-{uuid.uuid4().hex[:6]}",
                           "amount_taxable": 1000.0,
                           "vat_rate": 22.0,
                           "currency": "EUR",
                           "due_date": "2026-12-31"}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "pair_id" in d
        # Check gross computation
        assert abs(d["source"]["amount_gross"] - 1220.0) < 0.01
        # Verify source vs target
        assert d["source"]["side"] == "source"
        assert d["source"]["revenue_or_cost"] == "revenue"
        assert d["source"]["debit_credit"] == "credit"
        assert d["target"]["side"] == "target"
        assert d["target"]["revenue_or_cost"] == "cost"
        assert d["target"]["debit_credit"] == "debit"

        # Verify pair endpoint
        pr = api.get(f"{BASE_URL}/api/intercompany/pair/{d['pair_id']}", timeout=10)
        assert pr.status_code == 200
        assert pr.json()["coherent"] is True
        assert len(pr.json()["items"]) == 2

        # Reconcile confirm
        rc = api.post(f"{BASE_URL}/api/intercompany/reconcile",
                      json={"pair_id": d["pair_id"], "action": "confirm"}, timeout=10)
        assert rc.status_code == 200
        assert rc.json()["new_status"] == "reconciled"

        # Reverse creates mirrored credit note
        rv = api.post(f"{BASE_URL}/api/intercompany/reconcile",
                      json={"pair_id": d["pair_id"], "action": "reverse"}, timeout=10)
        assert rv.status_code == 200

    def test_intercompany_same_entity_rejected(self, api):
        self._ensure_unblocked(api)
        src_id, _ = self._get_ids(api)
        r = api.post(f"{BASE_URL}/api/intercompany",
                     json={"source_legal_entity_id": src_id,
                           "target_legal_entity_id": src_id,
                           "doc_kind": "invoice", "doc_ref": "TEST-SAME",
                           "amount_taxable": 100.0, "vat_rate": 22.0}, timeout=10)
        assert r.status_code == 400

    def test_reconciliation_report(self, api):
        r = api.get(f"{BASE_URL}/api/intercompany/reconciliation-report", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "total_pairs" in d and "issues" in d
        assert isinstance(d["issues"], list)


# ================= SAAS PLATFORM =================
class TestSaaSPlatform:
    def test_modules_13(self, api):
        r = api.get(f"{BASE_URL}/api/platform/saas/modules", timeout=10)
        assert r.status_code == 200
        assert len(r.json()["items"]) == 13

    def test_plans_3_tiers(self, api):
        r = api.get(f"{BASE_URL}/api/platform/saas/plans", timeout=10)
        assert r.status_code == 200
        codes = [p["code"] for p in r.json()["items"]]
        assert set(codes) == {"starter", "professional", "enterprise"}

    def test_dependencies_includes_quotes_to_crm(self, api):
        r = api.get(f"{BASE_URL}/api/platform/saas/dependencies", timeout=10)
        assert r.status_code == 200
        pairs = [(d["module_code"], d["requires_module"]) for d in r.json()["items"]]
        assert ("quotes_contracts", "core_crm") in pairs

    def test_set_module_state_dependency_block(self, api):
        # Assign starter plan (only core_crm + quotes_contracts) to a fresh fake tenant,
        # then attempt to activate ai_cfo — should fail with 400 (missing treasury+management_control).
        plans = api.get(f"{BASE_URL}/api/platform/saas/plans", timeout=10).json()["items"]
        starter = next((p for p in plans if p["code"] == "starter"), None)
        assert starter is not None, "starter plan missing"
        fake_tid = f"TEST-TENANT-{uuid.uuid4().hex[:8]}"
        r0 = api.post(f"{BASE_URL}/api/platform/saas/entitlements/{fake_tid}/assign-plan",
                      json={"plan_id": starter["id"]}, timeout=10)
        assert r0.status_code == 200, r0.text

        # Now try to activate ai_cfo — deps treasury+management_control missing → 400
        r = api.post(f"{BASE_URL}/api/platform/saas/entitlements/{fake_tid}/modules/ai_cfo/state",
                     json={"state": "active"}, timeout=10)
        assert r.status_code == 400, r.text
        detail = r.json()["detail"].lower()
        assert "treasury" in detail or "management_control" in detail or "dipendenz" in detail


# ================= MANAGEMENT CONTROL =================
class TestManagementControl:
    def test_preset_scenarios_returns_3(self, api):
        r = api.get(f"{BASE_URL}/api/control/budget/preset-scenarios", timeout=10)
        assert r.status_code == 200
        data = r.json()
        # Response may be list or dict of scenarios
        if isinstance(data, dict):
            keys = list(data.keys())
            assert len(keys) >= 3
        else:
            assert len(data) >= 3

    def test_budget_simulate_and_save(self, api):
        payload = {
            "label": "TEST_SimGrowth", "year": 2026, "scenario_kind": "growth",
            "save_as_scenario": True,
            "inputs": {
                "yearly_revenue": 800000, "average_ticket": 5000,
                "close_rate_pct": 25.0, "material_cost_pct": 40,
                "installation_cost_pct": 8, "personnel_cost_yearly": 150000,
                "fixed_costs_yearly": 60000, "target_profit": 50000,
            },
        }
        r = api.post(f"{BASE_URL}/api/control/budget/simulate", json=payload, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["saved"] is True
        assert "scenario_id" in d
        out = d["outputs"]
        assert out["forecast_revenue"] > 0
        assert out["break_even_revenue"] >= 0
        assert "waterfall" in out
        assert isinstance(out["waterfall"], list)
        assert "ebitda" in out
        assert "contribution_margin" in out

    def test_fixed_cost_yearly_normalization(self, api):
        r = api.post(f"{BASE_URL}/api/control/fixed-costs", json={
            "label": f"TEST_YearlyIns_{uuid.uuid4().hex[:6]}",
            "category": "insurance", "amount_raw": 1200.0,
            "recurrence": "yearly",
        }, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert abs(d["amount_monthly"] - 100.0) < 0.01

    def test_personnel_cost_monthly_total(self, api):
        r = api.post(f"{BASE_URL}/api/control/personnel-costs", json={
            "full_name": f"TEST_Person_{uuid.uuid4().hex[:6]}",
            "role": "Test", "department": "test",
            "ral_yearly": 36000.0, "social_charges_pct": 30.0,
            "monthly_indirect": 0.0,
        }, timeout=10)
        assert r.status_code == 200
        d = r.json()
        # 36000/12 = 3000 gross; total = 3000 + 30% = 3900
        assert abs(d["monthly_gross"] - 3000.0) < 0.01
        assert abs(d["monthly_total_cost"] - 3900.0) < 0.01

    def test_consolidation_endpoint(self, api):
        r = api.get(f"{BASE_URL}/api/control/consolidation", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "entities" in d
        assert "gross_totals" in d
        assert "eliminations" in d
        assert "consolidated" in d
        assert "intercompany_revenue" in d["eliminations"]


# ================= PRODUCT CATALOG =================
class TestProductCatalog:
    def test_types_include_key_codes(self, api):
        r = api.get(f"{BASE_URL}/api/product-catalog/types", timeout=10)
        assert r.status_code == 200
        j = r.json()
        items = j.get("items") if isinstance(j, dict) else j
        codes = [x["code"] for x in items]
        assert len(items) >= 18
        expected = {"window_3", "french_door", "sliding", "shutter",
                    "roller_shutter", "roller_box", "entrance_door"}
        assert expected.issubset(set(codes))

    def test_drawing_svg_composition(self, api):
        payload = {
            "composition": {
                "product_type_code": "window_3",
                "total_width_mm": 2400, "total_height_mm": 1500,
                "num_modules": 3,
                "modules": [
                    {"index": 0, "kind": "battente", "hinges_side": "left",
                     "width_ratio": 1.0, "is_openable": True, "is_fixed": False},
                    {"index": 1, "kind": "fixed", "hinges_side": "none",
                     "width_ratio": 1.0, "is_openable": False, "is_fixed": True},
                    {"index": 2, "kind": "battente_ribalta", "hinges_side": "right",
                     "width_ratio": 1.0, "is_openable": True, "is_fixed": False},
                ],
                "has_sopraluce": True, "sopraluce_height_mm": 300,
            },
            "show_dimensions": True, "show_opening_symbols": True,
        }
        r = api.post(f"{BASE_URL}/api/product-catalog/drawing", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "svg" in d and "hash" in d
        svg = d["svg"]
        assert svg.startswith("<svg") or "<svg" in svg[:200]
        # No script tags (sanitized)
        assert "<script" not in svg.lower()

    def test_site_conditions_platform_required(self, api):
        payload = {
            "conditions": {
                "floor_level": "2nd", "has_elevator": False,
                "platform_status": "required",
                "public_soil_occupation_needed": True,
                "truck_access": True,
            },
            "product_types": ["window_1"],
            "num_pieces": 3, "total_sqm": 6.0,
        }
        r = api.post(f"{BASE_URL}/api/product-catalog/site-conditions/evaluate",
                     json=payload, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["is_quotable"] is True
        assert d["conditions"]["access_complexity"] == "with_platform"
        assert len(d["surcharges_applied"]) >= 3
        # Warnings mention platform
        warns = " ".join(d.get("warnings") or [])
        assert "piattaforma" in warns.lower() or "platform" in warns.lower()

    def test_site_conditions_no_truck_not_quotable(self, api):
        payload = {
            "conditions": {
                "floor_level": "ground", "truck_access": False,
            },
            "product_types": ["window_1"],
            "num_pieces": 1, "total_sqm": 2.0,
        }
        r = api.post(f"{BASE_URL}/api/product-catalog/site-conditions/evaluate",
                     json=payload, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["is_quotable"] is False
        assert d["conditions"]["access_complexity"] == "not_quotable_without_survey"

    def test_installation_rules_seeded(self, api):
        r = api.get(f"{BASE_URL}/api/product-catalog/installation-rules", timeout=10)
        assert r.status_code == 200
        j = r.json()
        items = j.get("items") if isinstance(j, dict) else j
        codes = [x["code"] for x in items]
        assert len(items) >= 10
        for k in ("inst_window", "inst_french_door", "inst_sliding",
                  "inst_roller", "inst_entrance"):
            assert k in codes, f"missing {k}"

    def test_access_rules_seeded(self, api):
        r = api.get(f"{BASE_URL}/api/product-catalog/access-rules", timeout=10)
        assert r.status_code == 200
        j = r.json()
        items = j.get("items") if isinstance(j, dict) else j
        codes = [x["code"] for x in items]
        assert len(items) >= 6
        for k in ("floor_no_elev", "elev_inad", "platform_req",
                  "ztl_permit", "occ_soil", "muni_auth"):
            assert k in codes, f"missing {k}"
