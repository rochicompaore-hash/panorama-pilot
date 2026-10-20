"""PO directive EMAIL DELIVERY + ADMIN DISCOUNT 40% + VAT RECALC — backend tests."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid

import pytest
import requests

from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD
from tests.test_quote_economic_control_v2 import _login, _quote, _get, _line, VALID_DOSSIER, BASE


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def comm():
    return _login("commercial_test@infissiexpress.com", "CommTest!2026")


def _disc(s, qid, pct):
    return s.patch(f"{BASE}/quotes/{qid}", json={"global_discount_percent": pct}, timeout=15)


class TestAdminDiscount40:
    def test_admin_cap_min_40_and_floor(self, admin):
        # costi 4000 su 10000 → max sostenibile ≈ 52.9% → Admin max = 40 (tetto rigido)
        qid = _quote(admin, [_line("P", "window", 10000, 4000)])
        fs = admin.get(f"{BASE}/quotes/{qid}/financial-snapshot", timeout=15).json()["financial_snapshot"]
        assert fs["max_admin_discount_step_percent"] == 40 and fs["admin_master_max_discount_percent"] == 40
        assert fs["max_commercial_discount_step_percent"] == 30
        assert _disc(admin, qid, 40).status_code == 200
        q = _get(admin, qid)
        assert q["subtotal"] == 6000 and q["vat_amount"] == 1320 and q["total"] == 7320  # §B esempio PO
        r = _disc(admin, qid, 41)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "ADMIN_DISCOUNT_CAP_EXCEEDED"

    def test_admin_floor_below_40(self, admin):
        # costi 6500 su 10000 → max sostenibile floor(>15%) ≈ 23.5% → Admin max 23, e 24 bloccato dal floor
        qid = _quote(admin, [_line("P", "window", 10000, 6500)])
        fs = admin.get(f"{BASE}/quotes/{qid}/financial-snapshot", timeout=15).json()["financial_snapshot"]
        m = fs["max_admin_discount_step_percent"]
        assert m < 30 and m == fs["max_commercial_discount_step_percent"]
        assert _disc(admin, qid, m).status_code == 200
        assert _get(admin, qid)["financial_snapshot"]["post_margin_percent"] > 15.0
        r = _disc(admin, qid, m + 1)
        assert r.status_code == 400 and r.json()["detail"]["code"] == "DISCOUNT_BLOCKED_MARGIN_FLOOR"

    def test_commercial_blocked_over_30(self, admin, comm):
        qid = _quote(admin, [_line("P", "window", 10000, 4000)])
        r = _disc(comm, qid, 31)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "ADMIN_APPROVAL_REQUIRED"
        assert _disc(comm, qid, 30).status_code == 200
        fs = comm.get(f"{BASE}/quotes/{qid}/financial-snapshot", timeout=15).json()["financial_snapshot"]
        assert "post_margin_percent" not in fs  # RBAC: commerciale non vede margine


class TestVatAfterDiscount:
    def test_mixed_vat_after_discount(self, admin):
        qid = _quote(admin, [_line("Prodotto", "window", 8000, 3000), _line("Posa", "installation", 2000, 800)])
        r = admin.patch(f"{BASE}/quotes/{qid}/fiscal-dossier", json={"requested_regime": "VAT_MIXED_10_22", **VALID_DOSSIER}, timeout=15)
        assert r.status_code == 200, r.text
        assert _disc(admin, qid, 20).status_code == 200
        q = _get(admin, qid)
        assert q["subtotal"] == 8000
        bd = {b["rate_pct"]: b for b in q["vat_breakdown"]}
        assert bd[10]["taxable"] == 1600 and bd[10]["tax"] == 160
        assert bd[22]["taxable"] == 6400 and bd[22]["tax"] == 1408
        assert q["vat_amount"] == 1568 and q["total"] == 9568


class TestQuoteEmail:
    def test_preview_and_send_without_pdf_or_key(self, admin):
        qid = _quote(admin, [_line("P", "window", 1000, 400)])
        p = admin.get(f"{BASE}/quotes/{qid}/email/preview", timeout=15).json()
        assert p["to"] and p["sender"]["from_email"].endswith("@panoramapilot.com") and p["sender"]["sender_mode"] == "PANORAMA_MANAGED"
        assert "DEFINITIVE_PDF_MISSING" in p["blockers"]
        r = admin.post(f"{BASE}/quotes/{qid}/email/send", json={}, timeout=15)
        assert r.status_code == 400 and r.json()["detail"]["code"] == "DEFINITIVE_PDF_MISSING"

    def test_status_sent_does_not_send_email(self, admin):
        qid = _quote(admin, [_line("P", "window", 1000, 400)])
        r = admin.post(f"{BASE}/quotes/{qid}/status", json={"new_status": "sent"}, timeout=15)
        assert r.status_code == 200
        assert admin.get(f"{BASE}/quotes/{qid}/emails", timeout=15).json()["items"] == []

    def test_send_with_pdf(self, admin):
        qid = _quote(admin, [_line("P", "window", 1000, 400)])
        g = admin.post(f"{BASE}/quotes/{qid}/pdf/generate", json={"force": True}, timeout=60)
        if g.status_code == 503:
            pytest.skip("PDF engine non disponibile in questo ambiente")
        assert g.status_code == 200, g.text
        r = admin.post(f"{BASE}/quotes/{qid}/email/send", json={"message": "Test <b>x</b>"}, timeout=60)
        configured = admin.get(f"{BASE}/email-settings", timeout=15).json()["resend_configured"]
        items = admin.get(f"{BASE}/quotes/{qid}/emails", timeout=15).json()["items"]
        assert len(items) == 1 and items[0]["attachments"][0]["filename"].endswith(".pdf")
        if configured:
            assert r.status_code == 200 and r.json()["ok"] and items[0]["delivery_status"] == "provider_accepted"
            assert _get(admin, qid)["quote_status"] == "sent"
        else:
            assert r.status_code == 503 and r.json()["detail"]["status"] == "BLOCKED_BY_CONFIGURATION"
            assert items[0]["status"] == "configuration_required"
            assert _get(admin, qid)["quote_status"] == "draft"  # nessun "inviato" fittizio


class TestWebhook:
    def test_invalid_signature_rejected(self):
        r = requests.post(f"{BASE}/email-webhooks/resend", data=b"{}", headers={"svix-id": "x", "svix-timestamp": str(int(time.time())), "svix-signature": "v1,abc"}, timeout=15)
        assert r.status_code in (400, 503)

    def test_valid_signature_when_secret_present(self):
        secret = os.environ.get("RESEND_WEBHOOK_SECRET", "")
        if not secret:
            pytest.skip("RESEND_WEBHOOK_SECRET assente")
        body = json.dumps({"type": "email.delivered", "created_at": "2026-09-28T10:00:00Z", "data": {"email_id": "nope-" + uuid.uuid4().hex}}).encode()
        mid, ts = "msg_" + uuid.uuid4().hex, str(int(time.time()))
        key = base64.b64decode(secret.split("_", 1)[1])
        sig = base64.b64encode(hmac.new(key, f"{mid}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
        r = requests.post(f"{BASE}/email-webhooks/resend", data=body, headers={"svix-id": mid, "svix-timestamp": ts, "svix-signature": f"v1,{sig}", "content-type": "application/json"}, timeout=15)
        assert r.status_code == 200 and r.json()["matched"] is False
        r2 = requests.post(f"{BASE}/email-webhooks/resend", data=body, headers={"svix-id": mid, "svix-timestamp": ts, "svix-signature": f"v1,{sig}", "content-type": "application/json"}, timeout=15)
        assert r2.json().get("duplicate") is True


class TestTenantSender:
    def test_settings_and_custom_mode_requires_verified(self, admin):
        s = admin.get(f"{BASE}/tenant-email/settings", timeout=15).json()
        assert s["provider"] == "RESEND" and s["custom_smtp_per_tenant"] == "NOT_IN_SCOPE"
        assert s["effective_sender"]["from_email"].endswith("@panoramapilot.com")
        r = admin.patch(f"{BASE}/tenant-email/settings", json={"sender_mode": "CUSTOM_VERIFIED_DOMAIN"}, timeout=15)
        if s["domain_status"] != "VERIFIED":
            assert r.status_code == 400 and r.json()["detail"]["code"] == "DOMAIN_NOT_VERIFIED"
        r = admin.patch(f"{BASE}/tenant-email/settings", json={"reply_to": "non-valida"}, timeout=15)
        assert r.status_code == 400
