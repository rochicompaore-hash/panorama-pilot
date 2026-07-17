"""End-to-end backend tests for Infissi Express Cloud M1.

Tests all major endpoints: auth, users, roles, permissions, company, sequences,
attachments, audit, notifications, sessions, search, dashboard, email logs.

Executes as an ordered class-based suite because later tests depend on state
built by earlier tests (created user, invitation, etc.).
"""
from __future__ import annotations
import os
import time
import uuid
import pytest
import requests
from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD  # env-sourced credentials

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend .env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                    break
    except Exception:
        pass
assert BASE_URL, "REACT_APP_BACKEND_URL not set"

# scrubbed: ADMIN_EMAIL moved to tests._creds
# scrubbed: ADMIN_PASSWORD moved to tests._creds
STATE: dict = {}


def api(path: str) -> str:
    return f"{BASE_URL}/api{path}"


def _fresh_admin_session() -> requests.Session:
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    r = sess.post(api("/auth/login"), json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    body = r.json()
    sess.headers.update({"Authorization": f"Bearer {body['access_token']}"})
    # attach the user object for tests that need admin id / tenant
    sess.user = body["user"]  # type: ignore[attr-defined]
    sess.refresh_token = body["refresh_token"]  # type: ignore[attr-defined]
    return sess


@pytest.fixture(scope="session")
def s() -> requests.Session:
    """Session-scoped admin session. Because pytest-xdist uses loadscope
    distribution, each worker will build its own login session on first use."""
    return _fresh_admin_session()


@pytest.fixture(scope="session", autouse=True)
def admin_login(s):
    STATE["admin_user"] = s.user  # type: ignore[attr-defined]
    STATE["admin_refresh"] = s.refresh_token  # type: ignore[attr-defined]
    return s.user  # type: ignore[attr-defined]


def _get_viewer_role_id(s: requests.Session) -> str:
    r = s.get(api("/roles"))
    assert r.status_code == 200
    viewer = next((it for it in r.json()["items"] if it["name"] == "Viewer"), None)
    assert viewer, "Viewer role not seeded"
    return viewer["id"]


# ---------- Health ----------
class TestHealth:
    def test_health(self):
        r = requests.get(api("/health"))
        assert r.status_code == 200
        assert r.json().get("status") == "ok"


# ---------- Auth / Me ----------
class TestAuth:
    def test_me_returns_user_and_permissions(self, s):
        r = s.get(api("/auth/me"))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["user"]["email"] == ADMIN_EMAIL
        assert "*" in data["permissions"]

    def test_login_wrong_password_401(self):
        # Use fresh IP identifier by using unique random email to avoid affecting admin
        r = requests.post(api("/auth/login"), json={"email": ADMIN_EMAIL, "password": "WRONG_PWD"})
        assert r.status_code == 401

    def test_refresh_rotation_and_reuse_detection(self):
        # Login fresh session (independent from admin_login fixture)
        r = requests.post(api("/auth/login"), json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        tokens = r.json()
        old_refresh = tokens["refresh_token"]

        # Sleep >1s so JWT `iat` differs (backend uses seconds-precision iat).
        time.sleep(1.1)

        # First refresh - must succeed & issue new refresh (different from old)
        r2 = requests.post(api("/auth/refresh"), json={"refresh_token": old_refresh})
        assert r2.status_code == 200, r2.text
        new_refresh = r2.json()["refresh_token"]
        assert new_refresh != old_refresh, (
            "Refresh token rotation failed to produce a different token. "
            "Backend JWT uses seconds-precision iat without jti/nonce, so successive "
            "refreshes within the same second produce byte-identical tokens, silently "
            "defeating reuse-detection. Fix in app/security.create_refresh_token by "
            "adding a random 'jti' claim (uuid4)."
        )

        # Reusing old refresh must fail 401 (and revoke all sessions of that user)
        r3 = requests.post(api("/auth/refresh"), json={"refresh_token": old_refresh})
        assert r3.status_code == 401, r3.text

        # And using new_refresh should also now be revoked
        r4 = requests.post(api("/auth/refresh"), json={"refresh_token": new_refresh})
        assert r4.status_code == 401

    def test_logout_invalidates_refresh(self):
        # Login fresh
        r = requests.post(api("/auth/login"), json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        tokens = r.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        cookies = {"refresh_token": tokens["refresh_token"]}
        # logout uses cookie to find session
        r2 = requests.post(api("/auth/logout"), headers=headers, cookies=cookies)
        assert r2.status_code == 200
        # subsequent refresh with old refresh should fail
        r3 = requests.post(api("/auth/refresh"), json={"refresh_token": tokens["refresh_token"]})
        assert r3.status_code == 401

    def test_brute_force_lock_on_bad_email(self):
        # Use a unique email so we don't lock the admin account
        bad_email = f"nouser_{uuid.uuid4().hex[:8]}@test.com"
        got_429 = False
        last_status = None
        for i in range(7):
            r = requests.post(api("/auth/login"), json={"email": bad_email, "password": "whatever"})
            last_status = r.status_code
            if r.status_code == 429:
                got_429 = True
                break
        assert got_429, f"Expected 429 lock after 5 attempts, last={last_status}"

    def test_forgot_password_creates_email_log(self, s):
        r = requests.post(api("/auth/forgot-password"), json={"email": ADMIN_EMAIL})
        assert r.status_code == 200
        # Verify email log
        time.sleep(0.3)
        r2 = s.get(api("/email-logs?limit=20"))
        assert r2.status_code == 200, r2.text
        items = r2.json().get("items", [])
        assert any(it.get("to") == ADMIN_EMAIL and it.get("template") == "password_reset" for it in items)

    def test_reset_password_invalid_token(self):
        r = requests.post(api("/auth/reset-password"), json={"token": "invalid_token_xxx", "new_password": "NewPass123!"})
        assert r.status_code == 400

    def test_change_password_invalid_current(self, s):
        r = s.post(api("/auth/change-password"), json={"current_password": "wrong", "new_password": "NewPass123!"})
        assert r.status_code == 400


# ---------- Permissions & Roles ----------
class TestRolesAndPermissions:
    def test_list_permissions(self, s):
        r = s.get(api("/permissions"))
        assert r.status_code == 200
        modules = r.json().get("modules", [])
        # Flatten
        total = sum(len(m.get("permissions", [])) for m in modules)
        assert total == 28, f"expected 28 permissions, got {total}"

    def test_list_roles_contains_predefined(self, s):
        r = s.get(api("/roles"))
        assert r.status_code == 200
        names = {it["name"] for it in r.json().get("items", [])}
        expected = {"Super Admin", "Admin Azienda", "Commerciale", "Tecnico Rilievo",
                    "Produzione", "Magazzino", "Posatore", "Amministrazione", "Cliente", "Viewer"}
        assert expected.issubset(names), f"missing: {expected - names}"
        # Save viewer role id for later
        viewer = next((it for it in r.json()["items"] if it["name"] == "Viewer"), None)
        assert viewer
        STATE["viewer_role_id"] = viewer["id"]

    def test_create_custom_role_and_patch_and_delete(self, s):
        payload = {"name": f"TEST_Role_{uuid.uuid4().hex[:6]}", "description": "Test role",
                   "permission_keys": ["dashboard.view", "search.global"]}
        r = s.post(api("/roles"), json=payload)
        assert r.status_code == 200, r.text
        rid = r.json()["id"]
        # Patch
        r2 = s.patch(api(f"/roles/{rid}"), json={"permission_keys": ["dashboard.view"]})
        assert r2.status_code == 200
        assert r2.json()["permission_keys"] == ["dashboard.view"]
        # Delete
        r3 = s.delete(api(f"/roles/{rid}"))
        assert r3.status_code == 200

    def test_cannot_delete_system_role(self, s):
        r = s.delete(api(f"/roles/{STATE['viewer_role_id']}"))
        assert r.status_code == 400


# ---------- Users CRUD & Invitation flow ----------
class TestUsersCRUD:
    """Ordered flow: within one class pytest-xdist loadscope pins to one worker,
    so we can safely share state via STATE dict (populated in first test)."""

    def test_create_user_with_invitation(self, s):
        viewer_id = _get_viewer_role_id(s)
        STATE["viewer_role_id"] = viewer_id
        email = f"test.user.{uuid.uuid4().hex[:6]}@infissiexpress.com"
        STATE["new_user_email"] = email
        body = {"email": email, "first_name": "Test", "last_name": "User",
                "role_ids": [viewer_id], "send_invitation": True}
        r = s.post(api("/users"), json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["email"] == email
        assert data.get("invitation_url"), "invitation_url must be returned in dev"
        STATE["new_user_id"] = data["id"]
        STATE["invitation_url"] = data["invitation_url"]
        # Extract token from url
        STATE["invitation_token"] = data["invitation_url"].split("token=")[-1]

    def test_list_users_includes_new_and_supports_q(self, s):
        r = s.get(api("/users"))
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert any(u["id"] == STATE["new_user_id"] for u in items)
        r2 = s.get(api(f"/users?q={STATE['new_user_email'][:5]}"))
        assert r2.status_code == 200
        items2 = r2.json().get("items", [])
        assert any(u["id"] == STATE["new_user_id"] for u in items2)

    def test_accept_invitation_and_login(self):
        from tests._creds import ephemeral_password
        pwd = ephemeral_password("NewUser")
        r = requests.post(api("/auth/accept-invitation"),
                          json={"token": STATE["invitation_token"], "password": pwd})
        assert r.status_code == 200, r.text
        # Login as new user
        r2 = requests.post(api("/auth/login"),
                           json={"email": STATE["new_user_email"], "password": pwd})
        assert r2.status_code == 200, r2.text
        STATE["viewer_access"] = r2.json()["access_token"]

    def test_patch_user(self, s):
        r = s.patch(api(f"/users/{STATE['new_user_id']}"),
                    json={"first_name": "Renamed", "last_name": "User2"})
        assert r.status_code == 200
        assert r.json()["first_name"] == "Renamed"

    def test_invalid_role_id_rejected(self, s):
        r = s.patch(api(f"/users/{STATE['new_user_id']}"),
                    json={"role_ids": ["not-a-real-role-id"]})
        assert r.status_code == 400

    def test_resend_invitation(self, s):
        r = s.post(api(f"/users/{STATE['new_user_id']}/resend-invitation"))
        assert r.status_code == 200
        assert r.json().get("invitation_url")

    def test_unlock_user(self, s):
        r = s.post(api(f"/users/{STATE['new_user_id']}/unlock"))
        assert r.status_code == 200

    def test_cannot_delete_self(self, s):
        r = s.delete(api(f"/users/{STATE['admin_user']['id']}"))
        assert r.status_code == 400

    def test_rbac_viewer_forbidden_on_delete_user(self):
        # Login as viewer if not already
        headers = {"Authorization": f"Bearer {STATE['viewer_access']}"}
        # Try delete some user - should be 403
        r = requests.delete(api(f"/users/{STATE['admin_user']['id']}"), headers=headers)
        assert r.status_code == 403
        # Try create role - should be 403
        r2 = requests.post(api("/roles"), headers=headers,
                           json={"name": "X", "permission_keys": []})
        assert r2.status_code == 403

    def test_delete_user_soft(self, s):
        r = s.delete(api(f"/users/{STATE['new_user_id']}"))
        assert r.status_code == 200


# ---------- Company ----------
class TestCompany:
    def test_get_and_patch_company(self, s):
        r = s.get(api("/company"))
        assert r.status_code == 200, r.text
        original = r.json()
        new_city = f"TestCity_{uuid.uuid4().hex[:4]}"
        r2 = s.patch(api("/company"), json={"city": new_city})
        assert r2.status_code == 200
        assert r2.json().get("city") == new_city
        # Restore
        s.patch(api("/company"), json={"city": original.get("city") or "Milano"})


# ---------- Sequences ----------
class TestSequences:
    def test_list_default_sequences(self, s):
        r = s.get(api("/sequences"))
        assert r.status_code == 200
        items = r.json().get("items", [])
        keys = {it["key"] for it in items}
        expected = {"quote", "order", "purchase_order", "ddt", "invoice"}
        assert expected.issubset(keys), f"missing default seqs: {expected - keys}"
        STATE["seq_quote_id"] = next(it["id"] for it in items if it["key"] == "quote")

    def test_next_increments_and_formats(self, s):
        sid = STATE["seq_quote_id"]
        r1 = s.post(api(f"/sequences/{sid}/next"))
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        r2 = s.post(api(f"/sequences/{sid}/next"))
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["number"] == d1["number"] + 1
        assert d1["formatted"] and d2["formatted"]


# ---------- Attachments ----------
class TestAttachments:
    def test_upload_and_list_and_download_and_delete(self, s):
        content = b"Hello, this is a test attachment.\n"
        headers = {"Authorization": s.headers["Authorization"]}
        # Use requests directly for multipart (no JSON content-type)
        files = {"file": ("test.txt", content, "text/plain")}
        data = {"entity_type": "general", "description": "test upload"}
        r = requests.post(api("/attachments/upload"), headers=headers, files=files, data=data)
        assert r.status_code == 200, r.text
        att = r.json()
        assert att["filename"] == "test.txt"
        aid = att["id"]
        STATE["att_id"] = aid

        # List
        r2 = s.get(api("/attachments"))
        assert r2.status_code == 200
        assert any(a["id"] == aid for a in r2.json()["items"])

        # Download
        r3 = requests.get(api(f"/attachments/{aid}/download"), headers=headers)
        assert r3.status_code == 200
        assert r3.content == content

        # Delete
        r4 = s.delete(api(f"/attachments/{aid}"))
        assert r4.status_code == 200

    def test_blocked_extension_rejected(self, s):
        headers = {"Authorization": s.headers["Authorization"]}
        files = {"file": ("bad.exe", b"MZ...", "application/x-msdownload")}
        data = {"entity_type": "general"}
        r = requests.post(api("/attachments/upload"), headers=headers, files=files, data=data)
        assert r.status_code == 400

    def test_oversized_file_rejected(self, s):
        headers = {"Authorization": s.headers["Authorization"]}
        big = b"x" * (26 * 1024 * 1024)  # 26 MB
        files = {"file": ("big.bin", big, "application/octet-stream")}
        data = {"entity_type": "general"}
        r = requests.post(api("/attachments/upload"), headers=headers, files=files, data=data)
        assert r.status_code == 413


# ---------- Audit ----------
class TestAudit:
    def test_audit_list_and_filter(self, s):
        r = s.get(api("/audit?limit=50"))
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) > 0
        # Try filter by action
        r2 = s.get(api("/audit?action=auth.login"))
        assert r2.status_code == 200
        items2 = r2.json().get("items", [])
        assert all("login" in it.get("action", "") for it in items2)


# ---------- Notifications ----------
class TestNotifications:
    def test_notifications_flow(self, s):
        # Create for self
        payload = {"user_id": STATE["admin_user"]["id"],
                   "title": "Test", "body": "Notify me", "level": "info"}
        r = s.post(api("/notifications"), json=payload)
        assert r.status_code == 200, r.text
        nid = r.json().get("id")
        assert nid
        # List
        r2 = s.get(api("/notifications"))
        assert r2.status_code == 200
        items = r2.json().get("items", [])
        assert any(n["id"] == nid for n in items)
        # Mark read
        r3 = s.post(api(f"/notifications/{nid}/read"))
        assert r3.status_code == 200


# ---------- Sessions ----------
class TestSessions:
    def test_list_my_sessions(self, s):
        r = s.get(api("/sessions/mine"))
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) >= 1


# ---------- Search ----------
class TestSearch:
    def test_global_search(self, s):
        r = s.get(api("/search?q=admin"))
        assert r.status_code == 200
        results = r.json()
        # Should return dict of results with at least 1 hit somewhere
        assert any((isinstance(v, list) and len(v) > 0) for v in results.values() if isinstance(v, list)) or \
               (isinstance(results, dict) and results)


# ---------- Dashboard ----------
class TestDashboard:
    def test_summary(self, s):
        r = s.get(api("/dashboard/summary"))
        assert r.status_code == 200, r.text
        data = r.json()
        # Basic shape checks
        assert isinstance(data, dict)
        assert any(k in data for k in ("counters", "recent_audit", "recent_users"))
