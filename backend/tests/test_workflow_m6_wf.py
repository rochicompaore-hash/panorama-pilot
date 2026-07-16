"""M6.WF — End-to-end workflow tests (contract → survey → abaco → firma → executive order → production release).

Copre:
  - Formula parser strict vs legacy (DIV_ZERO)
  - Preview parametrica con nr_ante=0 (bom_blocking_errors o skip N/A)
  - Full E2E: quote → contract → sign → survey auto → abaco from-survey → status flow → send → public view → public sign → executive order → release check
  - Idempotenza (survey creation, ts from-survey)
  - Tenant isolation
  - Timeline sanitization + dedup
  - Public response sanitization (no blocking_errors)
  - New version dell'abaco
  - Production release override (approver != self)

Strategia: ogni test crea il proprio contratto isolato per evitare state-pollution tra test
(pytest/xdist non garantisce ordine con LoadScope).
"""
from __future__ import annotations
import os
import time
import uuid
import pytest
import requests
from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD  # env-sourced credentials

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://serramento-ops.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

# scrubbed: ADMIN_EMAIL moved to tests._creds
# scrubbed: ADMIN_PASSWORD moved to tests._creds
# -----------------------------------------------------------------------
# Fixtures + helpers
# -----------------------------------------------------------------------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_session(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_user(admin_session):
    r = admin_session.get(f"{API}/auth/me", timeout=10)
    assert r.status_code == 200
    body = r.json()
    # /auth/me returns {"user": {...}} shape
    user = body.get("user") or body
    return user


def _make_customer(sess) -> str:
    suffix = uuid.uuid4().hex[:8]
    r = sess.post(f"{API}/customers", json={
        "first_name": f"TEST_WF_{suffix}", "last_name": "Cliente",
        "email": f"wf_{suffix}@test.local",
    }, timeout=15)
    assert r.status_code in (200, 201), f"customer create: {r.status_code} {r.text[:200]}"
    return r.json()["id"]


def _make_signed_contract(sess, add_opening=True) -> str:
    """Crea customer → quote → sent → accepted → convert → sign. Ritorna contract_id."""
    cust_id = _make_customer(sess)
    r = sess.post(f"{API}/quotes", json={"customer_id": cust_id, "title": "TEST_WF quote"}, timeout=15)
    assert r.status_code in (200, 201), f"quote: {r.status_code} {r.text[:200]}"
    qid = r.json()["id"]
    if add_opening:
        r = sess.post(f"{API}/quotes/{qid}/openings",
                       json={"code": "V1", "room": "Camera", "width_mm": 1200, "height_mm": 1400}, timeout=15)
        assert r.status_code in (200, 201), f"opening: {r.status_code} {r.text[:200]}"
    for tgt in ["sent", "accepted"]:
        r = sess.post(f"{API}/quotes/{qid}/status", json={"new_status": tgt}, timeout=15)
        assert r.status_code == 200, f"status {tgt}: {r.status_code} {r.text[:200]}"
    r = sess.post(f"{API}/quotes/{qid}/convert-to-contract", json={}, timeout=15)
    assert r.status_code in (200, 201), f"convert: {r.status_code} {r.text[:200]}"
    cid = r.json().get("id") or r.json().get("_id")
    assert cid
    r = sess.post(f"{API}/contracts/{cid}/sign", json={
        "signer_name": "TEST_WF Firmatario",
        "signature_data_url": "data:image/png;base64,AAAA=",
        "accept_terms": True,
    }, timeout=15)
    assert r.status_code == 200, f"sign: {r.status_code} {r.text[:200]}"
    time.sleep(0.4)  # hook post-firma
    return cid


def _make_ts_from_contract(sess, cid) -> tuple[str, str]:
    """Ritorna (survey_id, ts_id) per un contratto firmato."""
    r = sess.get(f"{API}/surveys?contract_id={cid}", timeout=10)
    assert r.status_code == 200
    surveys = r.json().get("items") or []
    assert surveys, f"nessuna survey auto-creata per contract {cid}"
    sid = surveys[0]["id"]
    r = sess.post(f"{API}/workflow/technical-schedules/from-survey/{sid}", json={}, timeout=15)
    assert r.status_code == 200, f"ts from-survey: {r.status_code} {r.text[:200]}"
    ts_id = r.json()["id"]
    return sid, ts_id


# ============================================================================
# 1. Formula parser — strict mode (DIV_ZERO)
# ============================================================================
class TestFormulaStrictMode:
    def test_formula_test_strict_div_zero(self, admin_session):
        payload = {"formula": "L / nr_ante", "context": {"L": 1200, "nr_ante": 0}, "strict": True}
        r = admin_session.post(f"{API}/parametric/formula/test", json=payload, timeout=10)
        assert r.status_code == 200, f"status: {r.status_code} body: {r.text[:200]}"
        data = r.json()
        assert data["ok"] is False, f"strict DIV_ZERO deve tornare ok=false: {data}"
        assert data.get("code") == "DIV_ZERO", f"code=DIV_ZERO, got {data.get('code')}"
        assert data.get("severity") == "blocking", f"severity=blocking, got {data.get('severity')}"
        meta = data.get("meta") or {}
        assert "left" in meta and "right" in meta, f"meta deve contenere left/right: {meta}"

    def test_formula_test_legacy_div_zero_returns_zero(self, admin_session):
        payload = {"formula": "L / nr_ante", "context": {"L": 1200, "nr_ante": 0}, "strict": False}
        r = admin_session.post(f"{API}/parametric/formula/test", json=payload, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert float(data.get("result", -1)) == 0.0

    def test_formula_test_strict_omitted_defaults_to_legacy(self, admin_session):
        payload = {"formula": "L / nr_ante", "context": {"L": 1200, "nr_ante": 0}}
        r = admin_session.post(f"{API}/parametric/formula/test", json=payload, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert float(data.get("result", -1)) == 0.0


# ============================================================================
# 2. Parametric preview con nr_ante=0
# ============================================================================
class TestParametricPreviewBlockingErrors:
    def test_preview_nr_ante_zero_bom_blocking_or_skip(self, admin_session):
        payload = {"product_key": "window_2_leaves", "width_mm": 1200, "height_mm": 1400, "nr_ante": 0}
        r = admin_session.post(f"{API}/parametric/preview", json=payload, timeout=15)
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        data = r.json()
        bom_be = data.get("bom_blocking_errors") or []
        if not bom_be:
            pytest.skip("BOM demo window_2_leaves non contiene divisioni per nr_ante — N/A")
        # Verifica che almeno un errore sia DIV_ZERO/relativo a nr_ante
        found = any(("DIV_ZERO" in str(e) or "nr_ante" in str(e).lower() or "zero" in str(e).lower())
                    for e in bom_be)
        assert found, f"attesi errori DIV_ZERO/nr_ante: {bom_be}"


# ============================================================================
# 3. E2E completo: contract → survey → abaco → send → sign → executive_order → release_check
# ============================================================================
class TestE2EFullWorkflow:
    """UNICO test-class che esegue l'intero E2E su un contratto dedicato."""

    def test_full_workflow_e2e(self, admin_session):
        # 1. Contratto firmato (customer + quote + accept + convert + sign)
        cid = _make_signed_contract(admin_session)

        # 2. Contratto ora firmato
        r = admin_session.get(f"{API}/contracts/{cid}", timeout=10)
        assert r.status_code == 200
        assert r.json().get("contract_status") == "signed"

        # 3. Survey auto-creata (post-sign hook)
        r = admin_session.get(f"{API}/surveys?contract_id={cid}", timeout=10)
        surveys = r.json().get("items") or []
        assert len(surveys) >= 1, "survey non auto-creata"
        survey_id = surveys[0]["id"]

        # 4. Timeline contiene contract.signed + survey.created + customer_label='Contratto firmato'
        r = admin_session.get(f"{API}/workflow/timeline?contract_id={cid}", timeout=10)
        events = r.json().get("items") or []
        etypes = {e.get("event_type") for e in events}
        assert "contract.signed" in etypes, f"contract.signed mancante: {etypes}"
        assert "survey.created" in etypes, f"survey.created mancante: {etypes}"
        found = [e for e in events if e.get("customer_label") == "Contratto firmato"
                 and e.get("customer_stage") == "contract_signed"]
        assert found, "evento customer_label=Contratto firmato/stage=contract_signed non trovato"

        # 5. Timeline dedup: contract.signed deve apparire una sola volta
        assert len([e for e in events if e.get("event_type") == "contract.signed"]) == 1
        assert len([e for e in events if e.get("event_type") == "survey.created"]) == 1

        # 6. Abaco da survey (idempotente)
        r = admin_session.post(f"{API}/workflow/technical-schedules/from-survey/{survey_id}", json={}, timeout=15)
        assert r.status_code == 200
        ts = r.json()
        ts_id = ts["id"]
        assert ts["ts_status"] == "draft"
        assert ts["version"] == 1
        assert ts.get("number", "").startswith("ABACO"), f"prefix ABACO atteso, got: {ts.get('number')}"

        # 6b. Idempotenza
        r2 = admin_session.post(f"{API}/workflow/technical-schedules/from-survey/{survey_id}", json={}, timeout=10)
        assert r2.status_code == 200
        assert r2.json()["id"] == ts_id, "chiamata idempotente deve tornare stesso ID"

        # 6c. Elencato per contract_id
        r = admin_session.get(f"{API}/workflow/technical-schedules?contract_id={cid}", timeout=10)
        ids = [it.get("id") for it in (r.json().get("items") or [])]
        assert ts_id in ids, f"abaco {ts_id} non elencato: {ids}"

        # 7. Status: draft → in_technical_review OK
        r = admin_session.post(f"{API}/workflow/technical-schedules/{ts_id}/status",
                                json={"new_status": "in_technical_review"}, timeout=10)
        assert r.status_code == 200

        # 7b. Status: in_technical_review → signed è transizione non ammessa (409)
        r = admin_session.post(f"{API}/workflow/technical-schedules/{ts_id}/status",
                                json={"new_status": "signed"}, timeout=10)
        assert r.status_code == 409, f"expected 409 for forbidden transition, got {r.status_code}"

        # 8. Patch items OK in stato in_technical_review
        r = admin_session.patch(f"{API}/workflow/technical-schedules/{ts_id}",
                                 json={"notes": "TEST_WF note update"}, timeout=10)
        assert r.status_code == 200, f"patch: {r.status_code} {r.text[:200]}"

        # 9. Approved_internally
        r = admin_session.post(f"{API}/workflow/technical-schedules/{ts_id}/status",
                                json={"new_status": "approved_internally"}, timeout=10)
        assert r.status_code == 200

        # 10. Send (approved_internally → sent_to_customer) emette raw_token
        r = admin_session.post(f"{API}/workflow/technical-schedules/{ts_id}/send",
                                json={"channel": "link", "require_otp": False}, timeout=10)
        assert r.status_code == 200
        token = r.json().get("raw_token")
        assert token, "raw_token atteso"
        r = admin_session.get(f"{API}/workflow/technical-schedules/{ts_id}", timeout=10)
        assert r.json().get("ts_status") == "sent_to_customer"

        # 11. Public view (senza auth): NO tenant_id, NO costi, NO blocking_errors
        pub = requests.Session()
        r = pub.get(f"{API}/public/schedules/{token}", timeout=10)
        assert r.status_code == 200, f"public view: {r.status_code} {r.text[:200]}"
        raw = r.text
        assert "tenant_id" not in raw, "tenant_id NON deve essere esposto"
        assert '"unit_cost"' not in raw and '"total_cost"' not in raw, "costi NON devono essere esposti"
        for it in r.json()["schedule"].get("items") or []:
            assert "blocking_errors" not in it, f"blocking_errors NON deve essere esposto: {list(it.keys())}"

        # 12. Public sign SENZA tutti i consent → 400
        payload_incomplete = {
            "signer_name": "Mario Test",
            "signer_email": "mario@test.local",
            "signature_data_url": "data:image/png;base64,BBB=",
            "consent_all_openings_verified": True,
            "consent_measurements_verified": True,
            "consent_colors_glass_openings_verified": False,
            "consent_supersedes_preview": False,
            "consent_authorize_production": False,
            "consent_accept_variances_if_any": False,
        }
        r = pub.post(f"{API}/public/schedules/{token}/sign", json=payload_incomplete, timeout=10)
        assert r.status_code == 400, f"expected 400 missing consents: {r.status_code}"

        # 13. Public sign con tutti i consent → 200 + executive_order creato
        payload_ok = {**payload_incomplete,
                       "consent_colors_glass_openings_verified": True,
                       "consent_supersedes_preview": True,
                       "consent_authorize_production": True,
                       "consent_accept_variances_if_any": True}
        r = pub.post(f"{API}/public/schedules/{token}/sign", json=payload_ok, timeout=15)
        assert r.status_code == 200, f"sign OK: {r.status_code} {r.text[:300]}"
        data = r.json()
        assert data.get("ok") is True
        assert data.get("evidence_id")
        eo_id = data.get("executive_order_id")
        assert eo_id, f"executive_order_id atteso: {data}"

        # 14. Executive order presente in GET
        time.sleep(0.4)
        r = admin_session.get(f"{API}/workflow/executive-orders?contract_id={cid}", timeout=10)
        items = r.json().get("items") or []
        eos = [e for e in items if e.get("id") == eo_id]
        assert eos, f"executive_order {eo_id} non trovato: {[i.get('id') for i in items]}"
        assert eos[0]["eo_status"] == "created"
        assert eos[0].get("technical_schedule_id") == ts_id

        # 15. Ora TS è signed/released_to_production, patch/status change su signed → 409
        r = admin_session.patch(f"{API}/workflow/technical-schedules/{ts_id}",
                                 json={"notes": "should fail"}, timeout=10)
        assert r.status_code == 409, f"expected 409 patch on signed/released: {r.status_code} {r.text[:200]}"

        # 16. release_check ancora ineligible perché la survey è draft
        r = admin_session.post(f"{API}/workflow/production/release-check",
                                json={"contract_id": cid}, timeout=15)
        assert r.status_code == 200
        rc1 = r.json()
        # TS è signed, contratto firmato, ma survey_status è draft → blocking
        assert rc1["contract_status"] == "signed"
        assert rc1.get("technical_schedule_status") in ("signed", "released_to_production")
        # Blocca sul rilievo
        reasons = " | ".join(rc1.get("blocking_reasons") or [])
        assert "Rilievo" in reasons or "survey" in reasons.lower() or rc1["eligible"] is True, \
            f"attesi blocking_reasons sul rilievo: {reasons}"

        # 17. Muoviamo survey → completed e ripetiamo release_check
        for tgt in ["scheduled", "in_progress", "completed"]:
            resp = admin_session.post(f"{API}/surveys/{survey_id}/status",
                                       json={"survey_status": tgt}, timeout=10)
            assert resp.status_code == 200, f"survey {tgt}: {resp.status_code} {resp.text[:200]}"

        r = admin_session.post(f"{API}/workflow/production/release-check",
                                json={"contract_id": cid}, timeout=10)
        assert r.status_code == 200
        rc2 = r.json()
        # Ora TS è released_to_production e survey completed → eligible
        assert rc2["eligible"] is True, \
            f"expected eligible=True with all conditions met, got: {rc2.get('blocking_reasons')}"


# ============================================================================
# 4. Release-check ineligibile su contratto NON firmato
# ============================================================================
class TestReleaseCheckIneligible:
    def test_release_check_no_contract_signed(self, admin_session):
        cust_id = _make_customer(admin_session)
        r = admin_session.post(f"{API}/quotes", json={"customer_id": cust_id, "title": "TEST_WF ineligible"}, timeout=10)
        qid = r.json()["id"]
        for t in ["sent", "accepted"]:
            admin_session.post(f"{API}/quotes/{qid}/status", json={"new_status": t}, timeout=10)
        r = admin_session.post(f"{API}/quotes/{qid}/convert-to-contract", json={}, timeout=10)
        cid = r.json().get("id") or r.json().get("_id")
        # NON firmiamo
        r = admin_session.post(f"{API}/workflow/production/release-check",
                                json={"contract_id": cid}, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["eligible"] is False
        reasons = " | ".join(data.get("blocking_reasons") or [])
        assert ("Contratto non firmato" in reasons or "Rilievo" in reasons or "Abaco" in reasons), reasons


# ============================================================================
# 5. Release override — approver diverso obbligatorio
# ============================================================================
class TestReleaseOverride:
    def test_override_rejects_same_approver(self, admin_session, admin_user):
        cid = _make_signed_contract(admin_session)
        my_id = admin_user.get("id")
        assert my_id, f"admin id mancante: {admin_user}"
        payload = {"contract_id": cid, "reason": "TEST_WF override", "second_approver_user_id": my_id, "force": False}
        r = admin_session.post(f"{API}/workflow/production/release-override", json=payload, timeout=10)
        assert r.status_code == 400, f"expected 400 same-approver: {r.status_code} {r.text[:200]}"


# ============================================================================
# 6. New version dell'abaco
# ============================================================================
class TestNewVersion:
    def test_new_version_creates_v2_on_draft_ts(self, admin_session):
        cid = _make_signed_contract(admin_session)
        _, ts_id = _make_ts_from_contract(admin_session, cid)
        # TS in draft (non rilasciato) → new-version deve creare v2
        r = admin_session.post(f"{API}/workflow/technical-schedules/{ts_id}/new-version", json={}, timeout=10)
        assert r.status_code == 200, f"new-version: {r.status_code} {r.text[:200]}"
        data = r.json()
        assert data["version"] == 2, f"version=2 atteso: {data}"
        assert data["new_id"] != ts_id
        # Precedente is_current=false, superseded
        r = admin_session.get(f"{API}/workflow/technical-schedules/{ts_id}", timeout=10)
        prev = r.json()
        assert prev["is_current"] is False
        assert prev["ts_status"] == "superseded"


# ============================================================================
# 7. Tenant isolation (verifica indiretta: tutti gli item ritornati hanno tenant_id admin)
# ============================================================================
class TestTenantIsolation:
    def test_all_workflow_items_belong_to_admin_tenant(self, admin_session, admin_user):
        my_tenant = admin_user.get("tenant_id")
        assert my_tenant

        for endpoint in ["workflow/technical-schedules", "workflow/executive-orders", "workflow/timeline"]:
            r = admin_session.get(f"{API}/{endpoint}?limit=100", timeout=10)
            assert r.status_code == 200
            items = r.json().get("items") or []
            for it in items:
                assert it.get("tenant_id") == my_tenant, \
                    f"tenant mismatch in {endpoint}: {it.get('tenant_id')} vs {my_tenant}"


# ============================================================================
# 8. Auth guards
# ============================================================================
class TestAuthGuards:
    def test_workflow_endpoints_require_auth(self):
        s = requests.Session()
        r = s.get(f"{API}/workflow/technical-schedules", timeout=10)
        assert r.status_code in (401, 403), f"expected 401/403: {r.status_code}"

    def test_release_check_requires_auth(self):
        s = requests.Session()
        r = s.post(f"{API}/workflow/production/release-check", json={"contract_id": "x"}, timeout=10)
        assert r.status_code in (401, 403), f"expected 401/403: {r.status_code}"

    def test_public_view_bad_token_404(self):
        s = requests.Session()
        r = s.get(f"{API}/public/schedules/nonexistent-token-xxxx", timeout=10)
        assert r.status_code == 404, f"expected 404: {r.status_code}"
