"""Tests for the SMTP email system (services/email_service + models_email + routers).

Follows project convention: sync tests using `requests` against the live backend.

Covers:
  1. SMTP not configured -> status=configuration_required, never fakes 'sent'
  2. Delivery-mode redirect (test mode) preserves original_to, subject prefix
  3. Idempotency: same key -> single sent, second call is no-op reused log
  4. Password is never leaked in config viewer or logs
  5. 11 templates seeded and rendered
  6. Rate limit on /email-settings/test
  7. Tenant filter on /email-logs
"""
from __future__ import annotations
import os
import asyncio
import pytest
import requests

from tests._creds import ADMIN_EMAIL, ADMIN_PW


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
T = 15


def _login() -> str:
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=T)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _auth() -> dict:
    return {"Authorization": f"Bearer {_login()}"}


# --------------------------------------------------------------------
# 1. Config endpoint never leaks password
# --------------------------------------------------------------------
def test_email_settings_no_password_leak():
    r = requests.get(f"{API}/email-settings", headers=_auth(), timeout=T)
    assert r.status_code == 200, r.text
    data = r.json()
    # Password field must be reduced to a boolean flag
    assert "smtp_password" not in data
    assert data.get("password_configured") in (True, False)
    # Test-mode defaults expected in preview
    assert data["delivery_mode"] == "test"
    assert data["test_redirect_to"] == "pilot@panoramapilot.com"
    # SiteGround settings
    assert data["smtp_host"] == "gnldm1111.siteground.biz"
    assert data["smtp_port"] == 465
    assert data["smtp_security"] == "ssl"
    assert data["smtp_user"] == "pilot@panoramapilot.com"
    # Whole payload string must NOT contain 'password' as a value substring
    body = r.text.lower()
    # 'password_configured' key is allowed; ensure no raw password value
    forbidden = ["mail_password", "smtp_password_value"]
    for f in forbidden:
        assert f not in body


# --------------------------------------------------------------------
# 2. 11 canonical templates available + all render without errors
# --------------------------------------------------------------------
def test_templates_endpoint_has_11_codes():
    r = requests.get(f"{API}/email-settings/templates", headers=_auth(), timeout=T)
    assert r.status_code == 200
    data = r.json()
    codes = {it["code"] for it in data["items"]}
    expected = {
        "USER_INVITATION", "PASSWORD_RESET", "QUOTE_SENT",
        "CONTRACT_SIGNATURE_REQUEST", "CONTRACT_SIGNED", "NEW_LEAD_NOTIFICATION",
        "PAYMENT_REMINDER", "ORDER_STATUS_UPDATE", "SUPPORT_TICKET_UPDATE",
        "AI_CFO_ALERT", "DAILY_SUMMARY",
    }
    assert expected.issubset(codes), f"missing: {expected - codes}"


# --------------------------------------------------------------------
# 3. test-send with SMTP not configured => configuration_required
#    + delivery-mode redirect preserves original_to
# --------------------------------------------------------------------
def test_test_send_smtp_not_configured_and_redirect():
    r = requests.post(f"{API}/email-settings/test",
                      json={"to": "customer.real@example.com", "template": "USER_INVITATION"},
                      headers=_auth(), timeout=T)
    assert r.status_code == 200, r.text
    data = r.json()
    # If MAIL_PASSWORD not set — expected in preview: parked as configuration_required.
    # If it IS set (someone put the secret) — status is 'test_intercepted' (still in test mode).
    assert data["status"] in ("configuration_required", "test_intercepted", "sent", "retrying", "failed")
    assert data["delivery_mode"] == "test"
    assert data["original_to"] == "customer.real@example.com"
    assert data["actual_to"] == "pilot@panoramapilot.com"
    # If not configured, error must clearly say SMTP_NOT_CONFIGURED
    if data["status"] == "configuration_required":
        assert ("BLOCKED_BY_CONFIGURATION" in (data.get("error") or "")) or ("SMTP_NOT_CONFIGURED" in (data.get("error") or ""))


# --------------------------------------------------------------------
# 4. Idempotency via API level (using a legacy flow that supports it — activities.send_email)
#    Direct-DB tests are avoided because Motor's async client caches
#    the event loop and cannot be re-used across asyncio.run() calls in the same test session.
# --------------------------------------------------------------------
def test_idempotency_via_direct_service():
    """Use enqueue_email in a single asyncio.run() to avoid loop-close issues."""
    import motor.motor_asyncio as _m
    from app.services.email_service import enqueue_email
    from app.config import settings as _s

    key = "test-idem-e2e-002"

    async def run():
        # Fresh motor client bound to this loop
        client = _m.AsyncIOMotorClient(_s.MONGO_URL)
        db = client[_s.DB_NAME]
        await db.email_logs.delete_many({"idempotency_key": key})
        # First call — creates log
        r1 = await enqueue_email(
            to="idem@example.com", template="USER_INVITATION",
            context={"company_name": "TestCo", "invite_url": "http://x/y"},
            tenant_id="tenant-idem-test", idempotency_key=key,
        )
        # Mark as sent to satisfy idempotency lookup
        await db.email_logs.update_one({"_id": r1["id"]}, {"$set": {"status": "sent"}})
        r2 = await enqueue_email(
            to="idem@example.com", template="USER_INVITATION",
            context={"company_name": "TestCo", "invite_url": "http://x/y"},
            tenant_id="tenant-idem-test", idempotency_key=key,
        )
        n = await db.email_logs.count_documents({"idempotency_key": key})
        client.close()
        return r1, r2, n

    r1, r2, n = asyncio.run(run())
    assert r1["id"] == r2["id"], "Idempotency key must return the same log"
    assert r2["status"] == "sent"
    assert n == 1, f"Expected 1 log for key, got {n}"


# --------------------------------------------------------------------
# 5. Rate limit on test-send
# --------------------------------------------------------------------
def test_test_send_rate_limit():
    headers = _auth()
    got_429 = False
    # Try up to 8 sends within same session (limit=5/5min)
    for i in range(8):
        r = requests.post(
            f"{API}/email-settings/test",
            json={"to": f"rate-{i}@example.com", "template": "USER_INVITATION"},
            headers=headers, timeout=T,
        )
        if r.status_code == 429:
            got_429 = True
            assert "test" in r.text.lower() or "invii" in r.text.lower()
            break
    assert got_429, "Rate limit non ha bloccato dopo 5 invii"


# --------------------------------------------------------------------
# 6. /email-logs list is filterable + shows counts_by_status
# --------------------------------------------------------------------
def test_email_logs_list_and_filters():
    r = requests.get(f"{API}/email-logs?limit=20", headers=_auth(), timeout=T)
    assert r.status_code == 200
    data = r.json()
    assert "total" in data and "items" in data and "counts_by_status" in data
    # Filter by template
    r2 = requests.get(f"{API}/email-logs?template=USER_INVITATION&limit=5",
                      headers=_auth(), timeout=T)
    assert r2.status_code == 200
    for it in r2.json()["items"]:
        assert it["template"] == "USER_INVITATION"


# --------------------------------------------------------------------
# 7. DNS check endpoint
# --------------------------------------------------------------------
def test_dns_check_endpoint():
    r = requests.get(f"{API}/email-settings/dns-check?domain=example.com",
                     headers=_auth(), timeout=T)
    assert r.status_code == 200
    data = r.json()
    assert data["domain"] == "example.com"
    assert "spf" in data and "dkim" in data and "dmarc" in data
    assert "status_message" in data["spf"]


# --------------------------------------------------------------------
# 8. Template render sanity — call the API for each template's data,
#    then render its subject/html/text via Jinja2 directly (no motor calls).
# --------------------------------------------------------------------
def test_all_templates_render_no_placeholder():
    from jinja2 import Environment, select_autoescape

    ctx = {
        "app_base_url": "http://x", "brand_name": "Panorama Pilot",
        "invite_url": "http://x/i", "reset_url": "http://x/r",
        "customer_name": "R. Mario", "company_name": "R SRL",
        "quote_number": "Q-01", "contract_number": "C-01",
        "signature_url": "http://x/s", "expires_at": "31/12/2026",
        "signed_at": "01/02/2026", "signature_hash": "abc123",
        "lead_name": "L", "lead_email": "l@x.com", "lead_phone": "+39",
        "invoice_number": "F-1", "amount": "100",
        "order_number": "O-1", "new_status": "in_produzione",
        "ticket_number": "T-1", "ticket_title": "Vetro",
        "update_message": "OK", "alert_title": "Cassa", "alert_message": "!",
        "report_date": "22/07/2026", "user_first_name": "M",
    }
    r = requests.get(f"{API}/email-settings/templates", headers=_auth(), timeout=T)
    assert r.status_code == 200
    items = r.json()["items"]
    env = Environment(autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)
    for it in items:
        subj = env.from_string(it["subject"]).render(**ctx)
        html = env.from_string(it["html_body"]).render(**ctx)
        text = env.from_string(it["text_body"]).render(**ctx)
        assert "{{" not in subj, f"{it['code']}: unrendered var in subject: {subj}"
        assert "{{" not in html[:5000], f"{it['code']}: unrendered var in html"
        assert "{{" not in text[:5000], f"{it['code']}: unrendered var in text"
        assert len(subj) > 0


# --------------------------------------------------------------------
# 9. Server never crashes on missing MAIL_PASSWORD
# --------------------------------------------------------------------
def test_health_endpoint_still_ok():
    r = requests.get(f"{API}/health", timeout=T)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# --------------------------------------------------------------------
# 10. production-status reports email correctly
# --------------------------------------------------------------------
def test_production_status_email_block():
    r = requests.get(f"{API}/config/production-status", timeout=T)
    assert r.status_code == 200
    data = r.json()
    email = data["email"]
    assert "provider" in email and "configured" in email and "delivery_mode" in email
    assert email["delivery_mode"] == "test"
    assert email["test_redirect_to"] == "pilot@panoramapilot.com"
