"""SMTP configuration loader — reads env only, never persists MAIL_PASSWORD."""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MailConfig:
    smtp_host: str
    smtp_port: int
    smtp_security: str  # ssl | starttls | none
    smtp_user: str
    smtp_password: str  # NEVER include in logs / API responses / DB
    mail_from: str
    mail_from_name: str
    reply_to: Optional[str]
    delivery_mode: str  # test | live
    test_redirect_to: Optional[str]
    app_base_url: str
    provider_name: str  # siteground_smtp | mock

    @property
    def is_configured(self) -> bool:
        # SMTP considered configured only if host + user + password all present
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)


def get_mail_config() -> MailConfig:
    smtp_host = os.environ.get("MAIL_HOST", "").strip()
    smtp_port = int(os.environ.get("MAIL_PORT", "465"))
    smtp_security = os.environ.get("MAIL_SECURITY", "ssl").strip().lower()
    smtp_user = os.environ.get("MAIL_USER", "").strip()
    smtp_password = os.environ.get("MAIL_PASSWORD", "")  # never logged
    mail_from = os.environ.get("MAIL_FROM", smtp_user or "no-reply@infissiexpress.local").strip()
    mail_from_name = os.environ.get("MAIL_FROM_NAME", "Infissi Express Cloud").strip()
    reply_to = os.environ.get("MAIL_REPLY_TO", "").strip() or None
    delivery_mode = os.environ.get("MAIL_DELIVERY_MODE", "test").strip().lower()
    if delivery_mode not in ("test", "live"):
        delivery_mode = "test"
    test_redirect_to = os.environ.get("MAIL_TEST_REDIRECT_TO", "").strip() or None
    app_base_url = os.environ.get("APP_BASE_URL", "http://localhost:3000").strip()

    if smtp_host and smtp_user and smtp_password:
        provider_name = "siteground_smtp"
    else:
        provider_name = "mock"

    return MailConfig(
        smtp_host=smtp_host, smtp_port=smtp_port, smtp_security=smtp_security,
        smtp_user=smtp_user, smtp_password=smtp_password,
        mail_from=mail_from, mail_from_name=mail_from_name, reply_to=reply_to,
        delivery_mode=delivery_mode, test_redirect_to=test_redirect_to,
        app_base_url=app_base_url, provider_name=provider_name,
    )


def get_public_config() -> dict:
    """Config viewer — SAFE for API responses. Never contains password."""
    c = get_mail_config()
    return {
        "smtp_host": c.smtp_host,
        "smtp_port": c.smtp_port,
        "smtp_security": c.smtp_security,
        "smtp_user": c.smtp_user,
        "mail_from": c.mail_from,
        "mail_from_name": c.mail_from_name,
        "reply_to": c.reply_to,
        "delivery_mode": c.delivery_mode,
        "test_redirect_to": c.test_redirect_to,
        "password_configured": bool(c.smtp_password),
        "provider_name": c.provider_name,
        "is_configured": c.is_configured,
    }
