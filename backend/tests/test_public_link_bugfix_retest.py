"""M3.3.3 Retest — fix HIGH bug: PublicQuoteResponse.valid_until datetime → 500

Verifies fix in routers/public.py::public_get_quote (_iso helper for issue_date/valid_until).
Scenarios:
1. Quote with future valid_until → public GET 200 + is_expired:false + valid_until ISO string
2. Quote with past valid_until → public GET 200 + is_expired:true
3. Response DTO does NOT leak internal fields (_id, tenant_id, quote_id, internal_cost, margin_abs, cost_price)
"""
import os
import re
import uuid
import pytest
import requests
from tests._creds import ADMIN_EMAIL, ADMIN_PWD  # env-sourced credentials

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
# scrubbed: ADMIN_EMAIL moved to tests._creds
# scrubbed: ADMIN_PWD moved to tests._creds
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def a_lead(admin_session):
    r = admin_session.get(f"{API}/leads?limit=5")
    assert r.status_code == 200
    items = r.json().get("items") or []
    assert items, "seed leads missing"
    return items[0]


# ---------- helpers ----------
def _create_quote_with_line(admin_session, a_lead) -> tuple[str, int]:
    body = {
        "lead_id": a_lead["id"],
        "title": f"TEST_M333_BUGFIX_{uuid.uuid4().hex[:6]}",
        "intervention_type": "new",
        "site_address": {"street": "Via Test 1", "city": "Milano", "zip_code": "20100", "province": "MI", "country": "IT"},
    }
    r = admin_session.post(f"{API}/quotes", json=body)
    assert r.status_code == 200, r.text
    q = r.json()
    qid = q["id"]
    # add line
    line = {
        "category": "window", "description": "Finestra test bugfix",
        "width_mm": 1200, "height_mm": 1400, "quantity": 1.0, "base_price": 500.0,
    }
    r2 = admin_session.post(f"{API}/quotes/{qid}/lines", json=line)
    assert r2.status_code == 200, r2.text
    q2 = r2.json()
    return qid, q2.get("version", 1)


def _patch_valid_until(admin_session, qid, version, valid_until_iso: str) -> int:
    """PATCH quote.valid_until with If-Match (fetches current version), return new version."""
    # Fetch fresh version to avoid conflict from previous line ops
    r0 = admin_session.get(f"{API}/quotes/{qid}")
    assert r0.status_code == 200, r0.text
    cur_ver = r0.json().get("version", version)
    r = admin_session.patch(
        f"{API}/quotes/{qid}",
        json={"valid_until": valid_until_iso},
        headers={"If-Match": str(cur_ver)},
    )
    assert r.status_code == 200, f"PATCH failed: {r.status_code} {r.text}"
    d = r.json()
    return d.get("version", cur_ver + 1)


def _generate_pdf(admin_session, qid):
    r = admin_session.post(f"{API}/quotes/{qid}/pdf/generate", json={})
    assert r.status_code == 200, r.text
    return r.json()


def _create_public_link(admin_session, qid) -> str:
    r = admin_session.post(f"{API}/quotes/{qid}/public-links", json={"validity_days": 30})
    assert r.status_code == 200, r.text
    d = r.json()
    raw = d["raw_token"]
    assert raw and len(raw) == 43, f"raw_token unexpected: {raw}"
    return raw


# ---------- Tests ----------
class TestBugFixValidUntilNotExpired:
    """PATCH future valid_until → public GET 200 with is_expired=false."""

    def test_future_valid_until_returns_200(self, admin_session, a_lead):
        qid, ver = _create_quote_with_line(admin_session, a_lead)
        # PATCH future date
        future = "2026-12-31T23:59:59Z"
        _patch_valid_until(admin_session, qid, ver, future)
        _generate_pdf(admin_session, qid)
        raw = _create_public_link(admin_session, qid)

        # Public GET without auth
        anon = requests.Session()
        r = anon.get(f"{API}/public/quotes/{raw}")
        assert r.status_code == 200, f"expected 200 got {r.status_code}: {r.text}"
        assert "application/json" in r.headers.get("Content-Type", "")
        d = r.json()
        # Required fields
        assert d.get("quote_number"), f"missing quote_number: {d}"
        assert isinstance(d.get("total"), (int, float)) and d["total"] > 0, f"total not positive: {d.get('total')}"
        vu = d.get("valid_until")
        assert isinstance(vu, str) and ISO_RE.match(vu), f"valid_until not ISO string: {vu!r}"
        assert d.get("is_expired") is False, f"is_expired must be False: {d}"


class TestBugFixValidUntilExpired:
    """PATCH past valid_until → public GET 200 with is_expired=true."""

    def test_past_valid_until_returns_200_expired(self, admin_session, a_lead):
        qid, ver = _create_quote_with_line(admin_session, a_lead)
        past = "2020-01-01T00:00:00Z"
        _patch_valid_until(admin_session, qid, ver, past)
        _generate_pdf(admin_session, qid)
        raw = _create_public_link(admin_session, qid)

        anon = requests.Session()
        r = anon.get(f"{API}/public/quotes/{raw}")
        assert r.status_code == 200, f"expected 200 got {r.status_code}: {r.text}"
        d = r.json()
        vu = d.get("valid_until")
        assert isinstance(vu, str) and ISO_RE.match(vu), f"valid_until not ISO string: {vu!r}"
        assert d.get("is_expired") is True, f"is_expired must be True (past date): {d}"
        # allowed_actions must exclude accept/sign
        assert "accept" not in (d.get("allowed_actions") or [])
        assert "sign" not in (d.get("allowed_actions") or [])


class TestNoInternalFieldsLeak:
    """Regression: response DTO must not contain internal fields."""

    FORBIDDEN = {"_id", "tenant_id", "quote_id", "internal_cost", "margin_abs", "cost_price",
                 "margin_pct", "notes_interne", "cost_matrix", "openings"}

    def test_public_dto_has_no_internal_fields(self, admin_session, a_lead):
        qid, ver = _create_quote_with_line(admin_session, a_lead)
        # future date
        _patch_valid_until(admin_session, qid, ver, "2026-12-31T23:59:59Z")
        _generate_pdf(admin_session, qid)
        raw = _create_public_link(admin_session, qid)

        anon = requests.Session()
        r = anon.get(f"{API}/public/quotes/{raw}")
        assert r.status_code == 200
        assert "application/json" in r.headers.get("Content-Type", "")
        d = r.json()
        top_keys = set(d.keys())
        leaked = top_keys & self.FORBIDDEN
        assert not leaked, f"forbidden fields leaked at top-level: {leaked}"
        # Also check nested does not contain suspicious keys
        flat = str(d)
        for key in ("internal_cost", "margin_abs", "cost_price", "tenant_id"):
            assert f'"{key}"' not in flat, f"{key} leaked in response body"
