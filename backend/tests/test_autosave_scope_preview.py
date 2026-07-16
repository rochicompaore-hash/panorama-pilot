"""Backend tests: Autosave (M3.3.1) + Pricing scope semantics via configurator preview.

Covers:
  - Login super admin + /api/auth/me
  - /api/configurator/preview economics for qty=1/2/5 with WIN_PVC_STANDARD film_diff
  - /api/quotes/{id}/autosave success, version conflict (409), consolidated status (400),
    whitelist enforcement, mixed whitelist+non-whitelist fields, tenant_id protection
  - Regression: PATCH /api/quotes/{id} with stale If-Match -> 409, force=true w/o reason -> 400
"""
import os
import time
import uuid
import pytest
import requests
from tests._creds import ADMIN_EMAIL, ADMIN_PWD  # env-sourced credentials

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]).rstrip("/")
# scrubbed: ADMIN_EMAIL moved to tests._creds
# scrubbed: ADMIN_PWD moved to tests._creds
# ------------- Fixtures -------------
@pytest.fixture(scope="session")
def s():
    return requests.Session()


@pytest.fixture(scope="session")
def admin_h(s):
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no access_token in response: {r.text}"
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def me(s, admin_h):
    r = s.get(f"{BASE_URL}/api/auth/me", headers=admin_h)
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="session")
def tenant_id(me):
    u = me.get("user") or me
    tid = u.get("tenant_id")
    assert tid, f"no tenant_id in /me response: {me}"
    return tid


@pytest.fixture(scope="session")
def seed_lead(s, admin_h, tenant_id):
    """Create a TEST_ lead for the autosave draft tests (idempotent per session)."""
    # try to fetch first available lead
    r = s.get(f"{BASE_URL}/api/leads", headers=admin_h, params={"limit": 1})
    if r.status_code == 200:
        items = r.json().get("items") or []
        if items:
            return items[0]["id"]
    # else create one
    payload = {
        "first_name": "TEST_Autosave",
        "last_name": f"L{uuid.uuid4().hex[:6]}",
        "email": f"test_{uuid.uuid4().hex[:6]}@example.com",
        "phone": "+390000000",
        "source": "manual",
    }
    r = s.post(f"{BASE_URL}/api/leads", json=payload, headers=admin_h)
    assert r.status_code in (200, 201), f"lead create failed {r.status_code} {r.text}"
    return r.json()["id"]


# ------------- Auth basics -------------
class TestAuth:
    def test_login_ok(self, admin_h):
        assert "Authorization" in admin_h

    def test_me_returns_user(self, me):
        u = me.get("user") or me
        assert u.get("email") == ADMIN_EMAIL
        assert u.get("tenant_id")


# ------------- Configurator preview economics -------------
def _preview_body(qty):
    return {
        "product_key": "WIN_PVC_STANDARD",
        "product_config": {"color_kind": "film_diff"},
        "width_mm": 1200,
        "height_mm": 1400,
        "quantity": qty,
    }


class TestPreviewEconomics:
    def _post(self, s, admin_h, qty):
        r = s.post(f"{BASE_URL}/api/configurator/preview",
                   json=_preview_body(qty), headers=admin_h)
        assert r.status_code == 200, f"preview qty={qty} failed: {r.status_code} {r.text}"
        return r.json()

    def test_qty1(self, s, admin_h):
        d = self._post(s, admin_h, 1)
        assert d["unit_price_pre_qty"] == pytest.approx(983.81, abs=0.02)
        assert d["subtotal_line"] == pytest.approx(1133.81, abs=0.02)
        codes = {b.get("code"): b for b in d["breakdown"]}
        assert codes["BASE"]["scope"] == "unit"
        pct = codes["COLOR_FILM_DIFF_PCT"]
        assert pct["scope"] == "unit"
        assert pct["amount"] == pytest.approx(177.41, abs=0.02)
        fixed = codes["COLOR_FILM_DIFF_FIXED"]
        assert fixed["scope"] == "line"
        assert fixed["amount"] == pytest.approx(150.0, abs=0.01)

    def test_qty2_fixed_once(self, s, admin_h):
        d = self._post(s, admin_h, 2)
        assert d["subtotal_line"] == pytest.approx(2117.62, abs=0.02), \
            f"expected 2117.62 got {d['subtotal_line']} (regression: fixed×qty would be 2267.62)"
        fixed = next(b for b in d["breakdown"] if b.get("code") == "COLOR_FILM_DIFF_FIXED")
        assert fixed["amount"] == pytest.approx(150.0, abs=0.01)
        assert fixed["scope"] == "line"

    def test_qty5_fixed_still_once(self, s, admin_h):
        d = self._post(s, admin_h, 5)
        # 983.808 * 5 + 150 = 5069.04
        assert d["subtotal_line"] == pytest.approx(5069.04, abs=0.05)
        fixed = next(b for b in d["breakdown"] if b.get("code") == "COLOR_FILM_DIFF_FIXED")
        assert fixed["amount"] == pytest.approx(150.0, abs=0.01)
        assert fixed["amount"] != pytest.approx(750.0)


# ------------- Autosave -------------
@pytest.fixture
def draft_quote(s, admin_h, seed_lead):
    r = s.post(f"{BASE_URL}/api/quotes",
               json={"lead_id": seed_lead, "title": f"TEST_Autosave {uuid.uuid4().hex[:6]}"},
               headers=admin_h)
    assert r.status_code in (200, 201), f"quote create failed: {r.status_code} {r.text}"
    q = r.json()
    return {"id": q["id"], "version": q.get("version", 1)}


class TestAutosave:
    def test_success_flow_saves_and_increments_version(self, s, admin_h, draft_quote):
        qid = draft_quote["id"]
        rid = f"r-{uuid.uuid4().hex[:8]}"
        r = s.post(f"{BASE_URL}/api/quotes/{qid}/autosave",
                   json={"version": draft_quote["version"],
                         "fields": {"notes": "test", "payment_terms": "30/70"},
                         "request_id": rid},
                   headers=admin_h)
        assert r.status_code == 200, f"autosave failed: {r.status_code} {r.text}"
        d = r.json()
        assert d["ok"] is True
        assert d["version"] == draft_quote["version"] + 1
        assert d["updated_at"]
        assert d["request_id"] == rid
        # Verify persistence via GET
        g = s.get(f"{BASE_URL}/api/quotes/{qid}", headers=admin_h)
        assert g.status_code == 200
        gd = g.json()
        assert gd["notes"] == "test"
        assert gd["payment_terms"] == "30/70"

    def test_version_conflict_returns_409(self, s, admin_h, draft_quote):
        qid = draft_quote["id"]
        # First autosave (v1 -> v2)
        r1 = s.post(f"{BASE_URL}/api/quotes/{qid}/autosave",
                    json={"version": draft_quote["version"], "fields": {"notes": "first"}},
                    headers=admin_h)
        assert r1.status_code == 200
        # Second autosave using stale v1
        r2 = s.post(f"{BASE_URL}/api/quotes/{qid}/autosave",
                    json={"version": draft_quote["version"], "fields": {"notes": "stale"}},
                    headers=admin_h)
        assert r2.status_code == 409, f"expected 409, got {r2.status_code}: {r2.text}"
        detail = r2.json().get("detail") or {}
        assert detail.get("error") == "version_conflict"
        assert detail.get("expected_version") == draft_quote["version"]
        assert detail.get("current_version") == draft_quote["version"] + 1
        server_data = detail.get("server_data") or {}
        # tenant scoping — server_data must belong to same tenant
        # (Existence + non-empty is a good proxy since we're the tenant owner)
        assert server_data.get("id") == qid or server_data.get("_id") == qid or "version" in server_data

    def test_autosave_on_consolidated_returns_400(self, s, admin_h, draft_quote):
        qid = draft_quote["id"]
        # Bring quote to 'sent' via status transitions (need lines? sent should still work)
        # Path: draft -> sent is allowed by STATUS_FLOW
        r = s.post(f"{BASE_URL}/api/quotes/{qid}/status",
                   json={"new_status": "sent"}, headers=admin_h)
        assert r.status_code == 200, f"status change failed: {r.status_code} {r.text}"
        g = s.get(f"{BASE_URL}/api/quotes/{qid}", headers=admin_h)
        cur_v = g.json().get("version", 1)
        r2 = s.post(f"{BASE_URL}/api/quotes/{qid}/autosave",
                    json={"version": cur_v, "fields": {"notes": "should_not_save"}},
                    headers=admin_h)
        assert r2.status_code == 400, f"expected 400 consolidated, got {r2.status_code}: {r2.text}"
        detail = r2.json().get("detail", "")
        assert "consolidato" in (detail if isinstance(detail, str) else str(detail)).lower()

    def test_whitelist_all_fields_rejected(self, s, admin_h, draft_quote):
        qid = draft_quote["id"]
        r = s.post(f"{BASE_URL}/api/quotes/{qid}/autosave",
                   json={"version": draft_quote["version"],
                         "fields": {"tenant_id": "HACK", "total": 99999, "internal_cost": 0}},
                   headers=admin_h)
        assert r.status_code == 400
        assert "autosalvabile" in (r.json().get("detail") or "").lower()
        # tenant_id must not have changed
        g = s.get(f"{BASE_URL}/api/quotes/{qid}", headers=admin_h)
        assert g.json().get("tenant_id") != "HACK"

    def test_whitelist_mixed_fields_only_whitelisted_saved(self, s, admin_h, draft_quote):
        qid = draft_quote["id"]
        original_tenant = None
        g0 = s.get(f"{BASE_URL}/api/quotes/{qid}", headers=admin_h)
        original_tenant = g0.json().get("tenant_id")
        r = s.post(f"{BASE_URL}/api/quotes/{qid}/autosave",
                   json={"version": draft_quote["version"],
                         "fields": {"notes": "ok", "tenant_id": "HACK"}},
                   headers=admin_h)
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
        g = s.get(f"{BASE_URL}/api/quotes/{qid}", headers=admin_h)
        assert g.json().get("notes") == "ok"
        assert g.json().get("tenant_id") == original_tenant


# ------------- Regression spot check -------------
class TestConcurrencyRegression:
    def test_patch_with_stale_if_match_returns_409(self, s, admin_h, seed_lead):
        r = s.post(f"{BASE_URL}/api/quotes",
                   json={"lead_id": seed_lead, "title": f"TEST_regress {uuid.uuid4().hex[:6]}"},
                   headers=admin_h)
        assert r.status_code in (200, 201)
        qid = r.json()["id"]
        v = r.json().get("version", 1)
        # First update bumps to v+1
        r1 = s.patch(f"{BASE_URL}/api/quotes/{qid}",
                     json={"notes": "n1"},
                     headers={**admin_h, "If-Match": str(v)})
        assert r1.status_code == 200
        # Stale If-Match
        r2 = s.patch(f"{BASE_URL}/api/quotes/{qid}",
                     json={"notes": "n2"},
                     headers={**admin_h, "If-Match": str(v)})
        assert r2.status_code == 409

    def test_force_without_reason_returns_400(self, s, admin_h, seed_lead):
        r = s.post(f"{BASE_URL}/api/quotes",
                   json={"lead_id": seed_lead, "title": f"TEST_force {uuid.uuid4().hex[:6]}"},
                   headers=admin_h)
        qid = r.json()["id"]
        r2 = s.patch(f"{BASE_URL}/api/quotes/{qid}?force=true",
                     json={"notes": "forced"},
                     headers=admin_h)
        assert r2.status_code == 400, f"expected 400, got {r2.status_code}: {r2.text}"
