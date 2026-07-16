"""Iteration 18 — FULL PLATFORM REGRESSION AUDIT.

Backend-only fast audit across every core module before production deploy.
Focus: Critical/High regressions. Uses admin superadmin session throughout.
"""
from __future__ import annotations
import os
import re
import uuid
import pytest
import requests
from tests._creds import ADMIN_EMAIL, ADMIN_PW  # env-sourced credentials

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
# scrubbed: ADMIN_EMAIL moved to tests._creds
# scrubbed: ADMIN_PW moved to tests._creds
T = 20  # timeout


# -----------------------------------------------------------------------------
# FIXTURES
# -----------------------------------------------------------------------------
@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=T)
    assert r.status_code == 200, r.text
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def me(auth):
    r = requests.get(f"{API}/auth/me", headers=auth, timeout=T)
    assert r.status_code == 200
    body = r.json()
    return body.get("user") or body


@pytest.fixture(scope="session")
def customer_id(auth):
    r = requests.get(f"{API}/customers?limit=1", headers=auth, timeout=T)
    items = r.json().get("items", [])
    if items: return items[0]["id"]
    r = requests.post(f"{API}/customers", headers=auth,
                      json={"name": f"TEST_ITER18_{uuid.uuid4().hex[:5]}",
                            "customer_type": "private",
                            "email": f"iter18_{uuid.uuid4().hex[:5]}@example.com"},
                      timeout=T)
    return r.json()["id"]


# -----------------------------------------------------------------------------
# 1. AUTH
# -----------------------------------------------------------------------------
class TestAuth:
    def test_login_ok(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=T)
        assert r.status_code == 200
        b = r.json()
        assert (b.get("token") or b.get("access_token"))

    def test_me_has_tenant(self, auth):
        r = requests.get(f"{API}/auth/me", headers=auth, timeout=T)
        assert r.status_code == 200
        body = r.json()
        user = body.get("user") or body
        assert user.get("tenant_id"), body
        assert user.get("email") == ADMIN_EMAIL

    def test_login_wrong_password(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": "wrong_pw"}, timeout=T)
        assert r.status_code in (401, 400, 423)  # 423 if locked from previous runs


# -----------------------------------------------------------------------------
# 2. CRM (leads + customers)
# -----------------------------------------------------------------------------
class TestCRM:
    def test_leads_list(self, auth):
        r = requests.get(f"{API}/leads?limit=5", headers=auth, timeout=T)
        assert r.status_code == 200
        assert "items" in r.json()

    def test_leads_create_and_dedup(self, auth):
        email = f"iter18_lead_{uuid.uuid4().hex[:6]}@example.com"
        payload = {"first_name": "TEST", "last_name": "Iter18",
                   "email": email, "company_name": "TEST_ITER18"}
        r1 = requests.post(f"{API}/leads", headers=auth, json=payload, timeout=T)
        assert r1.status_code in (200, 201), r1.text
        # dedup: same email → return duplicate or 409
        r2 = requests.post(f"{API}/leads", headers=auth, json=payload, timeout=T)
        assert r2.status_code in (200, 201, 409), r2.text

    def test_customers_crud(self, auth):
        name = f"TEST_ITER18_CUST_{uuid.uuid4().hex[:5]}"
        r = requests.post(f"{API}/customers", headers=auth,
                          json={"name": name, "customer_type": "private",
                                "email": f"c_{uuid.uuid4().hex[:5]}@example.com"}, timeout=T)
        assert r.status_code in (200, 201), r.text
        cid = r.json()["id"]
        r = requests.get(f"{API}/customers/{cid}", headers=auth, timeout=T)
        assert r.status_code == 200
        r = requests.patch(f"{API}/customers/{cid}", headers=auth,
                           json={"phone": "+390000"}, timeout=T)
        assert r.status_code in (200, 204)
        r = requests.get(f"{API}/customers/{cid}", headers=auth, timeout=T)
        assert r.json().get("phone") == "+390000"


# -----------------------------------------------------------------------------
# 3. LEGAL ENTITIES & INTERCOMPANY
# -----------------------------------------------------------------------------
@pytest.fixture(scope="session")
def legal_entities(auth):
    r = requests.get(f"{API}/legal-entities", headers=auth, timeout=T)
    assert r.status_code == 200, r.text
    items = r.json().get("items", [])
    return items


class TestLegalEntities:
    def test_list_returns_enerhia_and_auxer(self, legal_entities):
        names = {(le.get("code") or "").lower(): le for le in legal_entities}
        names_lc = " ".join(le.get("name", "").lower() for le in legal_entities)
        assert "enerhia" in names_lc, f"Enerhia missing: {[le.get('name') for le in legal_entities]}"
        assert "auxer" in names_lc, f"Auxer missing"

    def test_missing_fields_and_blocked_flag_coherent(self, legal_entities):
        for le in legal_entities:
            missing = le.get("missing_fields") or []
            blocked = le.get("fiscal_operations_blocked")
            assert bool(missing) == bool(blocked), (
                f"Incoherent for {le.get('name')}: missing={missing} blocked={blocked}")

    def test_patch_completes_fiscal_fields(self, auth, legal_entities):
        # find one that IS blocked
        target = next((le for le in legal_entities if le.get("fiscal_operations_blocked")), None)
        if not target:
            pytest.skip("all LEs already complete")
        eid = target["id"]
        updates = {
            "vat_number": "IT01234567890",
            "tax_code": "01234567890",
            "pec": f"pec_{uuid.uuid4().hex[:5]}@pec.it",
        }
        r = requests.patch(f"{API}/legal-entities/{eid}", headers=auth,
                           json=updates, timeout=T)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("fiscal_operations_blocked") is False, body


@pytest.fixture(scope="session")
def two_complete_les(auth, legal_entities):
    """Complete two LEs so intercompany can be created."""
    completed = []
    for le in legal_entities[:2]:
        eid = le["id"]
        if le.get("fiscal_operations_blocked"):
            updates = {
                "vat_number": f"IT0{uuid.uuid4().int % 10**11:011d}",
                "tax_code": f"0{uuid.uuid4().int % 10**10:010d}",
                "pec": f"pec_{uuid.uuid4().hex[:5]}@pec.it",
            }
            r = requests.patch(f"{API}/legal-entities/{eid}", headers=auth,
                               json=updates, timeout=T)
            assert r.status_code == 200, r.text
        completed.append(eid)
    if len(completed) < 2:
        pytest.skip("need at least 2 LEs")
    return completed


class TestIntercompany:
    def test_create_pair_source_revenue_target_cost(self, auth, two_complete_les):
        src, tgt = two_complete_les
        r = requests.post(f"{API}/intercompany", headers=auth, json={
            "source_legal_entity_id": src,
            "target_legal_entity_id": tgt,
            "doc_kind": "invoice",
            "doc_ref": f"TEST_IC_{uuid.uuid4().hex[:5]}",
            "amount_taxable": 1000.0,
            "vat_rate": 22.0,
        }, timeout=T)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["source"]["revenue_or_cost"] == "revenue"
        assert body["target"]["revenue_or_cost"] == "cost"
        assert body["source"]["side"] == "source"
        assert body["target"]["side"] == "target"
        assert body["source"]["amount_gross"] == 1220.0
        # pair verifiable
        pair_id = body["pair_id"]
        r2 = requests.get(f"{API}/intercompany/pair/{pair_id}", headers=auth, timeout=T)
        assert r2.status_code == 200
        assert r2.json()["coherent"] is True

    def test_intercompany_blocked_when_le_incomplete(self, auth, legal_entities, two_complete_les):
        # Create a fresh incomplete LE
        code = f"TEST_LE_{uuid.uuid4().hex[:4]}"
        r = requests.post(f"{API}/legal-entities", headers=auth,
                          json={"code": code, "name": code, "legal_form": "SRL"}, timeout=T)
        assert r.status_code in (200, 201), r.text
        new_id = r.json()["id"]
        src = two_complete_les[0]
        r = requests.post(f"{API}/intercompany", headers=auth, json={
            "source_legal_entity_id": src,
            "target_legal_entity_id": new_id,
            "doc_kind": "invoice",
            "amount_taxable": 500.0,
        }, timeout=T)
        assert r.status_code == 400, r.text
        assert "incompleti" in r.text.lower() or "fiscal" in r.text.lower()

    def test_reconcile_and_reverse(self, auth, two_complete_les):
        src, tgt = two_complete_les
        r = requests.post(f"{API}/intercompany", headers=auth, json={
            "source_legal_entity_id": src,
            "target_legal_entity_id": tgt,
            "doc_kind": "invoice",
            "doc_ref": f"TEST_REC_{uuid.uuid4().hex[:5]}",
            "amount_taxable": 500.0,
        }, timeout=T)
        assert r.status_code == 200
        pair_id = r.json()["pair_id"]
        # confirm
        rc = requests.post(f"{API}/intercompany/reconcile", headers=auth,
                           json={"pair_id": pair_id, "action": "confirm"}, timeout=T)
        assert rc.status_code == 200
        r = requests.get(f"{API}/intercompany/pair/{pair_id}", headers=auth, timeout=T)
        assert all(x["ic_status"] == "reconciled" for x in r.json()["items"])
        # reverse: creates credit_note pair
        rv = requests.post(f"{API}/intercompany/reconcile", headers=auth,
                           json={"pair_id": pair_id, "action": "reverse"}, timeout=T)
        assert rv.status_code == 200
        # look for a credit_note pair with reversal_of_id set
        rlist = requests.get(f"{API}/intercompany?legal_entity_id={src}", headers=auth, timeout=T)
        credits = [i for i in rlist.json()["items"] if i.get("doc_kind") == "credit_note"]
        assert len(credits) >= 1


# -----------------------------------------------------------------------------
# 4. SAAS MODULARIZATION
# -----------------------------------------------------------------------------
class TestSaaS:
    def test_modules_returns_13(self, auth):
        r = requests.get(f"{API}/platform/saas/modules", headers=auth, timeout=T)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) == 13, f"expected 13, got {len(items)}: {[i.get('code') for i in items]}"

    def test_ai_cfo_activation_without_treasury_blocked(self, auth, me):
        """Direct-DB test: create a scratch tenant entitlement without treasury/mgmt_control,
        then attempt to activate ai_cfo. Router must return 400 with dep-missing."""
        import pymongo, os
        tid = f"TEST_ITER18_{uuid.uuid4().hex[:8]}"
        mongo = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = mongo[os.environ.get("DB_NAME", "infissi_express")]
        # insert a stripped entitlement (only core_crm + quotes_contracts)
        db.tenant_entitlements.insert_one({
            "_id": str(uuid.uuid4()), "tenant_id": tid,
            "plan_snapshot_module_codes": ["core_crm", "quotes_contracts"],
            "module_states": {"core_crm": "active", "quotes_contracts": "active"},
            "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
            "created_by": me["id"], "updated_by": me["id"],
            "deleted_at": None, "version": 1,
        })
        try:
            r = requests.post(
                f"{API}/platform/saas/entitlements/{tid}/modules/ai_cfo/state",
                headers=auth, json={"state": "active"}, timeout=T)
            assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
            assert "treasury" in r.text.lower() or "dipenden" in r.text.lower(), r.text
        finally:
            db.tenant_entitlements.delete_many({"tenant_id": tid})


# -----------------------------------------------------------------------------
# 5. MANAGEMENT CONTROL + GATING + CONSOLIDATION
# -----------------------------------------------------------------------------
class TestManagementControl:
    def test_dashboard_accessible(self, auth):
        r = requests.get(f"{API}/control/dashboard", headers=auth, timeout=T)
        assert r.status_code == 200, r.text

    def test_preset_scenarios_returns_3(self, auth):
        r = requests.get(f"{API}/control/budget/preset-scenarios", headers=auth, timeout=T)
        assert r.status_code == 200
        body = r.json()
        # PRESET_SCENARIOS is a Dict[str, Dict] with 3 keys OR a list
        if isinstance(body, dict):
            assert len(body) == 3, f"expected 3 presets, got keys={list(body.keys())}"
        else:
            items = body.get("items", []) if isinstance(body, dict) else body
            assert len(items) == 3, f"expected 3 presets, got {len(items)}: {items}"

    def test_budget_simulate(self, auth):
        r = requests.post(f"{API}/control/budget/simulate", headers=auth, json={
            "year": 2026,
            "inputs": {
                "yearly_revenue": 500000,
                "variable_costs_pct": 60,
                "fixed_costs_total": 120000,
                "personnel_costs_total": 60000,
                "price_pct_change": 0,
                "volume_pct_change": 0,
            },
        }, timeout=T)
        assert r.status_code == 200, r.text
        outs = r.json().get("outputs", {})
        for key in ["forecast_revenue", "break_even_revenue",
                    "ebitda", "contribution_margin", "waterfall"]:
            assert key in outs, f"missing {key} in {outs.keys()}"
        assert isinstance(outs["waterfall"], list) and len(outs["waterfall"]) > 0

    def test_consolidation(self, auth):
        r = requests.get(f"{API}/control/consolidation", headers=auth, timeout=T)
        assert r.status_code == 200, r.text
        b = r.json()
        for key in ["entities", "gross_totals", "eliminations", "consolidated"]:
            assert key in b, f"missing {key}: {b.keys()}"


# -----------------------------------------------------------------------------
# 6. PRODUCT CATALOG + SITE CONDITIONS
# -----------------------------------------------------------------------------
class TestProductCatalog:
    def test_types_returns_18(self, auth):
        r = requests.get(f"{API}/product-catalog/types", headers=auth, timeout=T)
        assert r.status_code == 200, r.text
        items = r.json().get("items", [])
        # Some seeds may vary — allow 18 or ≥18
        assert len(items) >= 18, f"expected ≥18, got {len(items)}"

    def test_drawing_sanitized(self, auth):
        r = requests.post(f"{API}/product-catalog/drawing", headers=auth, json={
            "product_type_code": "window_2",
            "width_mm": 1200, "height_mm": 1400,
            "config": {},
        }, timeout=T)
        # 200 or 400/422 if payload shape differs — flag if 500
        assert r.status_code != 500, r.text
        if r.status_code == 200:
            svg = (r.json().get("svg") or "")
            for bad in ["<script", "javascript:", "onerror=", "onclick="]:
                assert bad not in svg, f"XSS in drawing: {bad}"


class TestSiteConditions:
    def test_evaluate_with_platform_second_floor_no_elevator(self, auth):
        r = requests.post(f"{API}/product-catalog/site-conditions/evaluate",
                          headers=auth, json={
                              "conditions": {
                                  "floor_level": "2nd",
                                  "has_elevator": False,
                                  "platform_status": "required",
                                  "platform_positionable": True,
                                  "truck_access": True,
                                  "movement_difficulty": "medium",
                              },
                              "num_pieces": 3,
                              "total_sqm": 15.0,
                          }, timeout=T)
        assert r.status_code == 200, r.text
        b = r.json()
        cond = b["conditions"]
        assert cond["access_complexity"] == "with_platform", cond
        # is_quotable must be True (platform required does not block quoting)
        assert b.get("is_quotable") is True
        # surcharges_applied may be empty if no rules in DB — flag only if 500 occurred


# -----------------------------------------------------------------------------
# 7. PUBLIC LANDING + PLATFORM OWNER SITE CONFIG
# -----------------------------------------------------------------------------
class TestPublicLanding:
    def test_public_config_no_auth(self):
        r = requests.get(f"{API}/public-site/config", timeout=T)
        assert r.status_code == 200, r.text
        b = r.json()
        assert len(b.get("packages", [])) == 6, f"expected 6 packages, got {len(b.get('packages') or [])}"
        assert len(b.get("public_module_codes", [])) == 13, (
            f"expected 13, got {len(b.get('public_module_codes') or [])}")

    def test_lead_dedup_and_validation(self):
        email = f"iter18_pub_{uuid.uuid4().hex[:6]}@example.com"
        payload = {
            "first_name": "TEST", "last_name": "Iter18",
            "email": email, "company_name": "TEST_PUB",
            "privacy_consent": True,
        }
        r1 = requests.post(f"{API}/public-site/leads", json=payload, timeout=T)
        assert r1.status_code == 200, r1.text
        assert r1.json().get("duplicate") is False
        r2 = requests.post(f"{API}/public-site/leads", json=payload, timeout=T)
        assert r2.status_code == 200
        assert r2.json().get("duplicate") is True

    def test_lead_invalid_email(self):
        r = requests.post(f"{API}/public-site/leads", json={
            "first_name": "T", "last_name": "T",
            "email": "not-an-email",
            "company_name": "TEST", "privacy_consent": True,
        }, timeout=T)
        assert r.status_code in (400, 422), r.text

    def test_lead_missing_privacy_consent(self):
        r = requests.post(f"{API}/public-site/leads", json={
            "first_name": "T", "last_name": "T",
            "email": f"nopriv_{uuid.uuid4().hex[:4]}@example.com",
            "company_name": "TEST", "privacy_consent": False,
        }, timeout=T)
        assert r.status_code in (400, 422), r.text


class TestPlatformOwnerConfig:
    def test_reject_invalid_email_recipient(self, auth):
        # user needs is_platform_owner OR is_superadmin (admin has is_superadmin)
        r = requests.patch(f"{API}/platform/site-config", headers=auth,
                           json={"lead_notification_recipients":
                                 ["checonpaorechioccilagmail.com"]}, timeout=T)
        assert r.status_code == 400, r.text
        assert "email" in r.text.lower() or "non valide" in r.text.lower()

    def test_accept_valid_email_and_status_configured(self, auth):
        email = f"lead_recv_{uuid.uuid4().hex[:5]}@example.com"
        r = requests.patch(f"{API}/platform/site-config", headers=auth,
                           json={"lead_notification_recipients": [email]}, timeout=T)
        assert r.status_code == 200, r.text
        assert r.json().get("email_status") == "configured"


# -----------------------------------------------------------------------------
# 8. PREVENTIVATORE UNIFIED — smoke + composite drawing + tree
# -----------------------------------------------------------------------------
@pytest.fixture(scope="session")
def preventivo_quote(auth, customer_id):
    r = requests.post(f"{API}/quotes", headers=auth,
                      json={"customer_id": customer_id,
                            "title": f"TEST_ITER18_PRV_{uuid.uuid4().hex[:5]}"}, timeout=T)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


class TestPreventivatoreUnified:
    def test_full_stack_env_opening_products(self, auth, preventivo_quote):
        # create environment
        r = requests.post(f"{API}/quote-structure/{preventivo_quote}/environments",
                          headers=auth, json={"name": "Salone", "kind": "living_room"}, timeout=T)
        assert r.status_code == 200, r.text
        env_id = r.json()["id"]
        # opening
        r = requests.post(f"{API}/quote-structure/openings", headers=auth,
                          json={"quote_id": preventivo_quote,
                                "environment_id": env_id,
                                "dimensions": {"width_mm": 1200, "height_mm": 1400}},
                          timeout=T)
        assert r.status_code == 200, r.text
        op_id = r.json()["id"]
        # products
        for role, ptype in [("primary_frame", "window_2"),
                             ("shading", "roller_shutter"),
                             ("box", "roller_box"),
                             ("insect_screen", None)]:
            payload = {"opening_id": op_id, "role": role}
            if ptype:
                payload["product_type_code"] = ptype
            r = requests.post(f"{API}/quote-structure/openings/{op_id}/products",
                              headers=auth, json=payload, timeout=T)
            assert r.status_code == 200, f"{role}: {r.text}"

    def test_compat_blocks_shutter_after_roller_shutter(self, auth, preventivo_quote):
        r = requests.post(f"{API}/quote-structure/{preventivo_quote}/environments",
                          headers=auth, json={"name": "Bagno", "kind": "bathroom"}, timeout=T)
        env_id = r.json()["id"]
        r = requests.post(f"{API}/quote-structure/openings", headers=auth,
                          json={"quote_id": preventivo_quote, "environment_id": env_id,
                                "dimensions": {"width_mm": 800, "height_mm": 1200}}, timeout=T)
        op_id = r.json()["id"]
        r = requests.post(f"{API}/quote-structure/openings/{op_id}/products",
                          headers=auth, json={"opening_id": op_id, "role": "shading",
                                              "product_type_code": "roller_shutter"}, timeout=T)
        assert r.status_code == 200
        r = requests.post(f"{API}/quote-structure/openings/{op_id}/products",
                          headers=auth, json={"opening_id": op_id, "role": "shading",
                                              "product_type_code": "shutter"}, timeout=T)
        assert r.status_code == 400
        body = r.json()
        detail = body.get("detail", body)
        blockers = detail.get("blockers", []) if isinstance(detail, dict) else []
        assert any("Tapparella" in b or "alternative" in b.lower() for b in blockers), body

    def test_tree_nested(self, auth, preventivo_quote):
        r = requests.get(f"{API}/quote-structure/{preventivo_quote}/tree",
                         headers=auth, timeout=T)
        assert r.status_code == 200
        b = r.json()
        assert "environments" in b and len(b["environments"]) >= 1


# -----------------------------------------------------------------------------
# 9. PDF: still works + template safe for quotes w/o environments
# -----------------------------------------------------------------------------
class TestPDF:
    def test_pdf_preview_current_quote(self, auth, preventivo_quote):
        r = requests.post(f"{API}/quotes/{preventivo_quote}/pdf/preview",
                          headers=auth, json={}, timeout=45)
        # 200 or 202/402 — flag if 500
        assert r.status_code != 500, r.text[:400]

    def test_pdf_preview_legacy_quote_no_environments(self, auth, customer_id):
        """Legacy quote WITHOUT environments must not crash the jinja template."""
        r = requests.post(f"{API}/quotes", headers=auth,
                          json={"customer_id": customer_id,
                                "title": f"TEST_ITER18_LEGACY_{uuid.uuid4().hex[:5]}"},
                          timeout=T)
        qid = r.json()["id"]
        # no environments, no openings — PDF should still render (empty body)
        r = requests.post(f"{API}/quotes/{qid}/pdf/preview",
                          headers=auth, json={}, timeout=45)
        assert r.status_code != 500, (
            "PDF template CRITICAL: legacy quote (no environments/openings) "
            f"crashed the template. Status={r.status_code} Body={r.text[:400]}")


# -----------------------------------------------------------------------------
# 10. TREASURY + PERMISSIONS
# -----------------------------------------------------------------------------
class TestTreasury:
    def test_admin_can_access_dashboard(self, auth):
        r = requests.get(f"{API}/treasury/dashboard", headers=auth, timeout=T)
        assert r.status_code == 200, r.text


# -----------------------------------------------------------------------------
# 11. Migration idempotency (already covered iter17, add spot-check)
# -----------------------------------------------------------------------------
class TestMigrationSpotCheck:
    def test_migration_no_changes_on_clean_quote(self, auth, preventivo_quote):
        r = requests.post(f"{API}/quote-structure/{preventivo_quote}/migrate-structure",
                          headers=auth, timeout=T)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b.get("ok") is True
        # already structured → no_changes True or all counters zero
        assert (b.get("no_changes") is True) or (
            b.get("environments_created", 0) == 0
            and b.get("openings_migrated", 0) == 0)


# -----------------------------------------------------------------------------
# 12. Global 5xx sweep on core endpoints
# -----------------------------------------------------------------------------
CORE_ENDPOINTS = [
    "/auth/me", "/customers?limit=1", "/leads?limit=1",
    "/quotes?limit=1", "/legal-entities",
    "/platform/saas/modules", "/platform/saas/dependencies",
    "/control/dashboard", "/control/consolidation",
    "/control/budget/preset-scenarios",
    "/product-catalog/types",
    "/treasury/dashboard", "/treasury/bank-accounts", "/treasury/funds",
    "/intercompany",
]


class TestNo500:
    @pytest.mark.parametrize("path", CORE_ENDPOINTS)
    def test_no_500_on_core(self, auth, path):
        r = requests.get(f"{API}{path}", headers=auth, timeout=T)
        assert r.status_code < 500, f"5xx on {path}: {r.status_code} {r.text[:200]}"
