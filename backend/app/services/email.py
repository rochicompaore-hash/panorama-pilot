"""Compatibility wrapper for the legacy send_email API.

Preserves the existing call sites:
- send_email(to, subject, template, html, text)
- send_email(to=..., subject=..., template=..., body=..., ...)  (landing.py)
- render_invitation(company_name, invite_url)
- render_password_reset(reset_url)

Delegates to services/email_service.py (new SMTP + retry + tenant + idempotency).
No new call sites should use this wrapper; use email_service.enqueue_email instead.
"""
from __future__ import annotations
import logging
from typing import Optional, Any

from app.services.email_service import enqueue_email

logger = logging.getLogger("email_compat")


async def send_email(
    to: str,
    subject: Optional[str] = None,
    template: str = "legacy",
    html: Optional[str] = None,
    text: Optional[str] = None,
    body: Optional[str] = None,       # legacy landing.py signature
    tenant_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    **_ignored: Any,
) -> str:
    """Backward-compatible wrapper. Returns log_id (or empty string on hard failure)."""
    # Legacy landing.py passes `body=...` instead of `text=...`
    if text is None and body is not None:
        text = body
    try:
        result = await enqueue_email(
            to=to, subject=subject or "(no subject)", template=template,
            html=html, text=text,
            tenant_id=tenant_id, idempotency_key=idempotency_key,
        )
        return result.get("id") or result.get("_id") or ""
    except Exception:  # noqa: BLE001 — send_email must never crash the caller
        logger.exception("send_email failed for to=%s template=%s", to, template)
        return ""


def render_invitation(company_name: str, invite_url: str) -> tuple[str, str, str]:
    """Legacy renderer — returns (subject, html, text) via the USER_INVITATION template.
    Kept for callers that pre-render then pass to send_email(html=, text=).
    New callers should pass template='USER_INVITATION' + context to send_email directly.
    """
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
