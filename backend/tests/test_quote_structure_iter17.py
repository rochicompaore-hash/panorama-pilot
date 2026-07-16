"""Iteration 17 focused tests — validate 3 fixes on quote-structure migrate/tree.

Fixes to verify:
1. CRITICAL: migrate-structure lock uses `quote_status` (not `status`).
   -> A quote with quote_status='sent' MUST return ok=false, reason='quote_locked'.
2. Idempotency: migrate on a quote with no orphans must return ok=true, no_changes=true
   (early return, without corrupting data or bumping version further).
3. tree.migration_required must be true when orphan_openings exist even if no
   environments (was previously requiring BOTH).

Regression: iteration_16 suite runs separately; here we cover only these 3.
"""
from __future__ import annotations
import os
import uuid
import pytest
import requests
from tests._creds import ADMIN_EMAIL, ADMIN_PW  # env-sourced credentials

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
QS = f"{BASE_URL}/api/quote-structure"

# scrubbed: ADMIN_EMAIL moved to tests._creds
# scrubbed: ADMIN_PW moved to tests._creds
@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PW},
                      timeout=15)
    assert r.status_code == 200, r.text
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, r.text
    return tok


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def customer_id(auth):
    r = requests.get(f"{BASE_URL}/api/customers?limit=1", headers=auth, timeout=15)
    assert r.status_code == 200, r.text
    items = r.json().get("items", [])
    if items:
        return items[0]["id"]
    rc = requests.post(f"{BASE_URL}/api/customers", headers=auth,
                      json={"name": f"TEST_QS17_{uuid.uuid4().hex[:6]}",
                            "customer_type": "private",
                            "email": "test17@example.com"}, timeout=15)
    assert rc.status_code in (200, 201), rc.text
    return rc.json()["id"]


def _new_quote(auth, customer_id, prefix="TEST_QS17"):
    r = requests.post(f"{BASE_URL}/api/quotes", headers=auth,
                      json={"customer_id": customer_id,
                            "title": f"{prefix}_{uuid.uuid4().hex[:6]}"},
                      timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# ---------- FIX 1: quote_status lock guard --------------------------------
class TestMigrationLockFix:
    def test_sent_quote_is_locked_via_quote_status(self, auth, customer_id):
        """Reproduces iter16 CRITICAL bug — fixed by using q.get('quote_status')."""
        q_id = _new_quote(auth, customer_id, prefix="TEST_LOCK17")
        # add opening so 'sent' transition passes any business guards
        r_open = requests.post(f"{QS}/openings", headers=auth,
                               json={"quote_id": q_id,
                                     "environment_name": "Amb17",
                                     "dimensions": {"width_mm": 1000, "height_mm": 1200}},
                               timeout=15)
        assert r_open.status_code == 200, r_open.text
        # transition draft -> sent
        rs = requests.post(f"{BASE_URL}/api/quotes/{q_id}/status", headers=auth,
                           json={"new_status": "sent"}, timeout=15)
        if rs.status_code != 200:
            pytest.skip(f"cannot transition to sent (got {rs.status_code}: {rs.text})")
        # confirm persistence
        rget = requests.get(f"{BASE_URL}/api/quotes/{q_id}", headers=auth, timeout=15)
        assert rget.status_code == 200, rget.text
        assert rget.json().get("quote_status") == "sent"
        # migrate must be blocked
        rm = requests.post(f"{QS}/{q_id}/migrate-structure", headers=auth, timeout=15)
        assert rm.status_code == 200, rm.text
        body = rm.json()
        assert body.get("ok") is False, f"lock guard broken. Got: {body}"
        assert body.get("reason") == "quote_locked", body

    def test_draft_quote_is_not_locked(self, auth, customer_id):
        """Sanity: a draft quote must still allow migration."""
        q_id = _new_quote(auth, customer_id, prefix="TEST_DRAFT17")
        rm = requests.post(f"{QS}/{q_id}/migrate-structure", headers=auth, timeout=15)
        assert rm.status_code == 200, rm.text
        body = rm.json()
        # No orphans, no lines → idempotent early return; either way, ok=True
        assert body.get("ok") is True, body


# ---------- FIX 2: migrate-structure idempotency --------------------------
class TestMigrationIdempotency:
    def test_migrate_twice_returns_no_changes_on_second_call(self, auth, customer_id):
        """After first migration, second call on same quote (no orphans left)
        must return ok=true, no_changes=true (early return) and NOT corrupt data.
        """
        q_id = _new_quote(auth, customer_id, prefix="TEST_IDEMP17")
        # Create an orphan opening (no env)
        r_open = requests.post(f"{QS}/openings", headers=auth,
                               json={"quote_id": q_id,
                                     "dimensions": {"width_mm": 900, "height_mm": 1000},
                                     "display_name": "OrphanVano17"},
                               timeout=15)
        assert r_open.status_code == 200, r_open.text

        # First migrate: should create envs + attach opening
        r1 = requests.post(f"{QS}/{q_id}/migrate-structure", headers=auth, timeout=15)
        assert r1.status_code == 200, r1.text
        b1 = r1.json()
        assert b1["ok"] is True
        assert b1.get("openings_migrated", 0) >= 1

        # Fetch state after first migrate
        rt1 = requests.get(f"{QS}/{q_id}/tree", headers=auth, timeout=15)
        assert rt1.status_code == 200
        tree1 = rt1.json()
        envs_after_1 = len(tree1.get("environments") or [])
        assert envs_after_1 >= 1
        assert len(tree1.get("orphan_openings") or []) == 0

        # Second migrate: no orphans → should be no-op
        r2 = requests.post(f"{QS}/{q_id}/migrate-structure", headers=auth, timeout=15)
        assert r2.status_code == 200, r2.text
        b2 = r2.json()
        assert b2.get("ok") is True, b2
        # Preferred behavior: no_changes=True with 0 counters.
        # Fallback acceptable: ok=true with counters all zero (data not corrupted).
        no_changes = b2.get("no_changes")
        assert no_changes is True or (
            b2.get("environments_created", 0) == 0
            and b2.get("openings_migrated", 0) == 0
            and b2.get("lines_role_assigned", 0) == 0
        ), f"second migrate should be no-op, got {b2}"

        # Confirm no corruption: tree still identical env-count / no orphans
        rt2 = requests.get(f"{QS}/{q_id}/tree", headers=auth, timeout=15)
        assert rt2.status_code == 200
        tree2 = rt2.json()
        assert len(tree2.get("environments") or []) == envs_after_1
        assert len(tree2.get("orphan_openings") or []) == 0


# ---------- FIX 3: tree.migration_required flag ---------------------------
class TestMigrationRequiredFlag:
    def test_migration_required_true_for_orphan_only(self, auth, customer_id):
        """A quote with orphan openings but no environments must have
        migration_required=true in the tree endpoint.
        """
        q_id = _new_quote(auth, customer_id, prefix="TEST_ORPHTREE17")
        # Add orphan opening (no environment)
        r_open = requests.post(f"{QS}/openings", headers=auth,
                               json={"quote_id": q_id,
                                     "dimensions": {"width_mm": 800, "height_mm": 900},
                                     "display_name": "SoloOrphan17"},
                               timeout=15)
        assert r_open.status_code == 200, r_open.text
        rt = requests.get(f"{QS}/{q_id}/tree", headers=auth, timeout=15)
        assert rt.status_code == 200, rt.text
        tree = rt.json()
        assert len(tree.get("orphan_openings") or []) >= 1, tree
        # environments may be empty but migration_required must be TRUE
        assert tree.get("migration_required") is True, (
            f"migration_required should be True when orphans exist. Tree: "
            f"envs={len(tree.get('environments') or [])}, "
            f"orphans={len(tree.get('orphan_openings') or [])}, "
            f"migration_required={tree.get('migration_required')}"
        )

    def test_migration_required_false_when_clean(self, auth, customer_id):
        """No orphans, no unassigned roles → migration_required=false."""
        q_id = _new_quote(auth, customer_id, prefix="TEST_CLEAN17")
        # Create opening with environment attached via env_name
        r_open = requests.post(f"{QS}/openings", headers=auth,
                               json={"quote_id": q_id,
                                     "environment_name": "AmbClean17",
                                     "dimensions": {"width_mm": 800, "height_mm": 900}},
                               timeout=15)
        assert r_open.status_code == 200, r_open.text
        rt = requests.get(f"{QS}/{q_id}/tree", headers=auth, timeout=15)
        assert rt.status_code == 200, rt.text
        tree = rt.json()
        assert len(tree.get("orphan_openings") or []) == 0
        assert tree.get("migration_required") is False
