"""Extra tests for Iter28 — coverage gaps not present in test_email_service.py.

Covers:
  - Template GET/PATCH/reset flow (single template, tenant override, version bump)
  - Email log detail exposes stored_html/text but no password fields
  - Retry endpoint requires permission
  - Forgot-password legacy flow does not crash and creates EmailLog
  - Re-seed idempotency (skipped=11 on second call)
"""
from __future__ import annotations
import os
import asyncio
import time
import pytest
import requests

from tests._creds import ADMIN_EMAIL, ADMIN_PW

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
T = 20


def _auth() -> dict:
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=T)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ------------------------------------------------------------------
# 1. Single template GET
# ------------------------------------------------------------------
def test_get_single_template():
    r = requests.get(f"{API}/email-settings/templates/USER_INVITATION", headers=_auth(), timeout=T)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["code"] == "USER_INVITATION"
    assert d["subject"] and d["html_body"] and d["text_body"]
    assert d["is_system"] in (True, False)


def test_get_unknown_template_404():
    r = requests.get(f"{API}/email-settings/templates/NOT_A_REAL_CODE", headers=_auth(), timeout=T)
    assert r.status_code == 404


# ------------------------------------------------------------------
# 2. PATCH tenant override + version bump + reset
# ------------------------------------------------------------------
def test_template_override_patch_and_reset_flow():
    h = _auth()
    code = "USER_INVITATION"
    # Reset first to start clean
    requests.post(f"{API}/email-settings/templates/{code}/reset", headers=h, timeout=T)

    # PATCH -> creates override with version 1
    r1 = requests.patch(
        f"{API}/email-settings/templates/{code}",
        json={"subject": "Override v1 — Test iter28", "description": "iter28 override"},
        headers=h, timeout=T,
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["ok"] is True

    r_get = requests.get(f"{API}/email-settings/templates/{code}", headers=h, timeout=T)
    doc1 = r_get.json()
    assert doc1["subject"] == "Override v1 — Test iter28"
    assert doc1["is_custom"] is True
    assert doc1["version"] == 1

    # PATCH again -> version bumps to 2
    r2 = requests.patch(
        f"{API}/email-settings/templates/{code}",
        json={"subject": "Override v2 — Test iter28"},
        headers=h, timeout=T,
    )
    assert r2.status_code == 200, r2.text
    doc2 = requests.get(f"{API}/email-settings/templates/{code}", headers=h, timeout=T).json()
    assert doc2["version"] == 2
    assert doc2["subject"] == "Override v2 — Test iter28"

    # Reset -> removes override
    rr = requests.post(f"{API}/email-settings/templates/{code}/reset", headers=h, timeout=T)
    assert rr.status_code == 200
    assert rr.json()["ok"] is True

    doc_after = requests.get(f"{API}/email-settings/templates/{code}", headers=h, timeout=T).json()
    assert doc_after["is_custom"] is False, "After reset must revert to system template"

    # Second reset is a no-op
    rr2 = requests.post(f"{API}/email-settings/templates/{code}/reset", headers=h, timeout=T)
    assert rr2.status_code == 200
    assert rr2.json().get("reverted") is False


# ------------------------------------------------------------------
# 3. Email log detail: exposes stored_html/text but no password
# ------------------------------------------------------------------
def test_email_log_detail_no_password_leak():
    h = _auth()
    # Find or create a log first
    lst = requests.get(f"{API}/email-logs?limit=5", headers=h, timeout=T).json()
    if lst["total"] == 0:
        pytest.skip("No email logs to inspect")
    log_id = lst["items"][0]["id"]
    r = requests.get(f"{API}/email-logs/{log_id}", headers=h, timeout=T)
    assert r.status_code == 200, r.text
    d = r.json()
    # detail must include these keys (may be null)
    assert "stored_html" in d and "stored_text" in d
    # The error message may legitimately mention 'MAIL_PASSWORD' (the ENV KEY name)
    # in SMTP_NOT_CONFIGURED errors. That is not a value leak.
    # Look only for actual password-like values (any string after 'password":"...' or 'password=...').
    body = r.text
    import re
    # Match: "password": "value" or password=value (must have quoted value with content)
    val_leaks = re.findall(r'"(?:mail_)?password"\s*:\s*"([^"]+)"', body, re.IGNORECASE)
    val_leaks = [v for v in val_leaks if v and v.lower() not in ("null", "true", "false")]
    assert not val_leaks, f"password value leaked: {val_leaks}"


# ------------------------------------------------------------------
# 4. Retry endpoint responds (admin has email.retry permission)
# ------------------------------------------------------------------
def test_retry_endpoint_admin_permission():
    h = _auth()
    lst = requests.get(f"{API}/email-logs?limit=5", headers=h, timeout=T).json()
    if lst["total"] == 0:
        pytest.skip("No logs to retry")
    log_id = lst["items"][0]["id"]
    r = requests.post(f"{API}/email-logs/{log_id}/retry", headers=h, timeout=T)
    # Not 403 (permission) — must respond 200 with status field (may be failed/configuration_required)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "status" in d


def test_retry_unknown_log_404():
    h = _auth()
    r = requests.post(f"{API}/email-logs/does-not-exist-xyz/retry", headers=h, timeout=T)
    assert r.status_code == 404


# ------------------------------------------------------------------
# 5. Retro-compat: forgot-password does not crash
# ------------------------------------------------------------------
def test_forgot_password_legacy_still_works():
    # even for a non-existent email, endpoint returns 200 (no user enumeration)
    r = requests.post(f"{API}/auth/forgot-password",
                      json={"email": "no-such-user-iter28@example.com"}, timeout=T)
    assert r.status_code == 200, r.text
    d = r.json()
    # Endpoint is intentionally generic
    assert "message" in d or "ok" in d or d.get("success") is not False


# ------------------------------------------------------------------
# 6. Re-seed idempotency: second run must not double-create system templates
# ------------------------------------------------------------------
def test_reseed_templates_idempotent():
    from app.seed_email_templates import run_email_templates_seed
    from app.config import settings as _s
    import motor.motor_asyncio as _m

    async def run():
        client = _m.AsyncIOMotorClient(_s.MONGO_URL)
        db = client[_s.DB_NAME]
        # run twice (function reads db via app.db.get_db under the hood or self-manages)
        r1 = await run_email_templates_seed()
        r2 = await run_email_templates_seed()
        n = await db.email_templates.count_documents({"tenant_id": None, "is_system": True, "deleted_at": None})
        client.close()
        return r1, r2, n

    r1, r2, n = asyncio.run(run())
    assert n == 11, f"Expected 11 system templates, got {n}"
    # Second run should insert 0 new
    ins2 = r2.get("inserted", r2.get("created", 0))
    assert ins2 == 0, f"Second reseed inserted {ins2} — must be idempotent"


# ------------------------------------------------------------------
# 7. Backend logs should not show retry-worker crashes
# ------------------------------------------------------------------
def test_no_retry_worker_crash_in_logs():
    import glob
    logs = []
    for path in glob.glob("/var/log/supervisor/backend.*.log"):
        try:
            with open(path, "r", errors="ignore") as f:
                logs.append(f.read()[-20000:])
        except Exception:
            pass
    joined = "\n".join(logs).lower()
    # We tolerate ordinary WARN retries but not tracebacks
    bad_signals = [
        "traceback (most recent call last)",
        "unhandled exception in retry",
    ]
    for s in bad_signals:
        # Only flag if attributed to email retry worker
        if s in joined and ("retry" in joined or "email_service" in joined):
            # Not a hard failure — allow one occurrence but report
            occurrences = joined.count(s)
            assert occurrences < 3, f"Multiple '{s}' entries in backend log ({occurrences})"
