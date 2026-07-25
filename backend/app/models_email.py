"""Email models — EmailLog v2 (multi-tenant, idempotent, retry) + EmailTemplate.

Preserva la compatibilità con la vecchia collection `email_logs`: i nuovi record
usano il campo esteso, i vecchi restano leggibili.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from app.models import new_id, BaseDoc


# ---------- Constants ----------
EMAIL_STATUS_QUEUED = "queued"
EMAIL_STATUS_SENDING = "sending"
EMAIL_STATUS_SENT = "sent"
EMAIL_STATUS_FAILED = "failed"
EMAIL_STATUS_RETRYING = "retrying"
EMAIL_STATUS_BOUNCED = "bounced"
EMAIL_STATUS_TEST_INTERCEPTED = "test_intercepted"  # sent but redirected in test mode
EMAIL_STATUS_CONFIG_REQUIRED = "configuration_required"

DELIVERY_MODE_TEST = "test"
DELIVERY_MODE_LIVE = "live"

# 11 canonical templates approved by product owner (msg 329)
EMAIL_TEMPLATE_CODES = [
    "USER_INVITATION",
    "PASSWORD_RESET",
    "QUOTE_SENT",
    "CONTRACT_SIGNATURE_REQUEST",
    "CONTRACT_SIGNED",
    "NEW_LEAD_NOTIFICATION",
    "PAYMENT_REMINDER",
    "ORDER_STATUS_UPDATE",
    "SUPPORT_TICKET_UPDATE",
    "AI_CFO_ALERT",
    "DAILY_SUMMARY",
]


class EmailLogV2(BaseDoc):
    """Log completo di un invio email — tenant isolato, retry-safe, idempotente."""
    tenant_id: Optional[str] = None
    # Original vs actual (may differ if delivery_mode=test)
    to: str  # actual recipient the SMTP call used (may be redirect address)
    original_to: str  # what the caller asked for (real customer, always preserved)
    subject: str
    template: str  # template code (e.g. USER_INVITATION) or legacy string
    template_version: Optional[int] = None
    delivery_mode: str = DELIVERY_MODE_TEST
    status: str = EMAIL_STATUS_QUEUED
    provider: str = "mock"
    error: Optional[str] = None
    smtp_response: Optional[str] = None
    # Retry / idempotency
    attempt_count: int = 0
    max_attempts: int = 3
    next_retry_at: Optional[datetime] = None
    last_attempt_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    idempotency_key: Optional[str] = None
    payload_hash: Optional[str] = None
    # Context for retry (payload rebuilt from stored html/text or from context)
    stored_html: Optional[str] = None
    stored_text: Optional[str] = None
    reply_to: Optional[str] = None


class EmailTemplateDoc(BaseDoc):
    """Template personalizzabile per tenant. tenant_id=None = template di sistema."""
    tenant_id: Optional[str] = None
    code: str  # e.g. USER_INVITATION
    subject: str  # Jinja2 template
    html_body: str  # Jinja2 template
    text_body: str  # Jinja2 template
    version: int = 1
    is_system: bool = False
    is_active: bool = True
    description: Optional[str] = None


class EmailTemplateUpdate(BaseModel):
    subject: Optional[str] = None
    html_body: Optional[str] = None
    text_body: Optional[str] = None
    description: Optional[str] = None


class TestEmailRequest(BaseModel):
    to: str = Field(..., min_length=3, max_length=200)
    template: str = "USER_INVITATION"
    context_override: Optional[Dict[str, Any]] = None


class DnsCheckResult(BaseModel):
    domain: str
    spf: Dict[str, Any]
    dkim: Dict[str, Any]
    dmarc: Dict[str, Any]


class EmailSettingsResponse(BaseModel):
    """Public config viewer — NEVER contains the SMTP password."""
    smtp_host: str
    smtp_port: int
    smtp_security: str
    smtp_user: str
    mail_from: str
    mail_from_name: str
    reply_to: Optional[str] = None
    delivery_mode: str
    test_redirect_to: Optional[str] = None
    password_configured: bool
    provider_name: str
    is_configured: bool
