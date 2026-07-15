"""EmailProvider abstract + Mock (dev) + Resend (prod stub).

Emails NEVER block main flow: send() catches all exceptions and logs to email_logs.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional
from app.config import settings
from app.db import get_db
from app.models import EmailLog, new_id

logger = logging.getLogger("email")


class EmailProvider:
    name = "abstract"

    async def _deliver(self, to: str, subject: str, html: str, text: str) -> None:
        raise NotImplementedError


class MockEmailProvider(EmailProvider):
    name = "mock"

    async def _deliver(self, to: str, subject: str, html: str, text: str) -> None:
        logger.info("========== [MOCK EMAIL] ==========")
        logger.info("To: %s", to)
        logger.info("Subject: %s", subject)
        logger.info("Body:\n%s", text)
        logger.info("==================================")


class ResendEmailProvider(EmailProvider):
    name = "resend"

    async def _deliver(self, to: str, subject: str, html: str, text: str) -> None:
        # Real Resend integration to be enabled before production
        # via resend python SDK. Placeholder to keep interface stable.
        if not settings.RESEND_API_KEY:
            raise RuntimeError("RESEND_API_KEY not configured")
        try:
            import resend  # type: ignore
        except ImportError as e:
            raise RuntimeError("resend package not installed") from e
        resend.api_key = settings.RESEND_API_KEY
        resend.Emails.send({
            "from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>",
            "to": [to],
            "subject": subject,
            "html": html,
            "text": text,
        })


def _provider() -> EmailProvider:
    if settings.EMAIL_PROVIDER == "resend":
        return ResendEmailProvider()
    return MockEmailProvider()


async def send_email(to: str, subject: str, template: str, html: str, text: str) -> str:
    """Send an email via configured provider. Never raises. Returns log id."""
    db = get_db()
    log = EmailLog(
        id=new_id(),
        to=to,
        subject=subject,
        template=template,
        status="queued",
        provider=settings.EMAIL_PROVIDER,
    )
    doc = _to_mongo(log.model_dump(by_alias=True))
    await db.email_logs.insert_one(doc)
    prov = _provider()
    try:
        await prov._deliver(to=to, subject=subject, html=html, text=text)
        await db.email_logs.update_one(
            {"_id": log.id},
            {"$set": {"status": "sent", "sent_at": datetime.now(timezone.utc).isoformat()}},
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Email delivery failed to %s", to)
        await db.email_logs.update_one(
            {"_id": log.id},
            {"$set": {"status": "failed", "error": str(e)[:500]}},
        )
    return log.id


def _to_mongo(d: dict) -> dict:
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


# Template builders (kept simple; production versions would use Jinja/MJML)
def render_invitation(company_name: str, invite_url: str) -> tuple[str, str, str]:
    subject = f"Invito a {company_name} — Infissi Express Cloud"
    text = (
        f"Sei stato invitato ad accedere a {company_name} su Infissi Express Cloud.\n\n"
        f"Imposta la tua password al seguente link (valido 72 ore):\n{invite_url}\n"
    )
    html = f"""<div style='font-family:system-ui,sans-serif'>
      <h2>Benvenuto in {company_name}</h2>
      <p>Sei stato invitato ad accedere a <b>Infissi Express Cloud</b>.</p>
      <p><a href='{invite_url}' style='background:#09090B;color:#fff;padding:12px 20px;text-decoration:none'>Imposta password</a></p>
      <p style='color:#71717A;font-size:12px'>Il link scade in 72 ore.</p>
    </div>"""
    return subject, html, text


def render_password_reset(reset_url: str) -> tuple[str, str, str]:
    subject = "Recupero password — Infissi Express Cloud"
    text = (
        f"Hai richiesto il recupero password.\n\n"
        f"Segui il link (valido 30 minuti):\n{reset_url}\n"
        f"Se non hai fatto tu la richiesta, ignora questa email.\n"
    )
    html = f"""<div style='font-family:system-ui,sans-serif'>
      <h2>Recupero password</h2>
      <p>Hai richiesto il recupero password su Infissi Express Cloud.</p>
      <p><a href='{reset_url}' style='background:#D9381E;color:#fff;padding:12px 20px;text-decoration:none'>Reimposta password</a></p>
      <p style='color:#71717A;font-size:12px'>Il link scade in 30 minuti.</p>
    </div>"""
    return subject, html, text
