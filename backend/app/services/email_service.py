"""Real SMTP email service (SiteGround-ready) with:
- Multi-tenant email_logs (tenant_id preserved)
- Idempotency (idempotency_key -> single successful send)
- Delivery mode: test (intercept -> MAIL_TEST_REDIRECT_TO) vs live
- Retry with backoff 1m / 5m / 15m via background task
- Never crashes the caller flow; failures are logged with status
- No fallback silenziosa a "sent" quando SMTP non è configurato: status=configuration_required
- Password letta SOLO da env (MAIL_PASSWORD); mai loggata; mai esposta

Compatibility: expose `send_email(to, subject, template, html, text, ...)` so existing
routers keep working without changes.
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
import ssl
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Optional, Dict, Any, Tuple, List
from pathlib import Path

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateNotFound

from app.db import get_db
from app.mongo_utils import to_mongo, from_mongo
from app.models import new_id
from app.models_email import (
    EMAIL_STATUS_BOUNCED,
    EmailLogV2, EmailTemplateDoc,
    EMAIL_STATUS_QUEUED, EMAIL_STATUS_SENDING, EMAIL_STATUS_SENT,
    EMAIL_STATUS_FAILED, EMAIL_STATUS_RETRYING, EMAIL_STATUS_CONFIG_REQUIRED,
    EMAIL_STATUS_TEST_INTERCEPTED, DELIVERY_MODE_TEST, EMAIL_TEMPLATE_CODES,
)
from app.services.email_config import get_mail_config
from app.services import resend_provider
from app.services.tenant_email import resolve_sender

logger = logging.getLogger("email_service")

# Stati delivery (PO §E/§10): provider_accepted (SENT) ≠ delivered
DELIVERY_QUEUED, DELIVERY_SENT, DELIVERY_DELIVERED, DELIVERY_DEFERRED = "queued", "provider_accepted", "delivered", "deferred"
DELIVERY_BOUNCED, DELIVERY_FAILED, DELIVERY_COMPLAINED = "bounced", "failed", "complained"

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"
_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

RETRY_BACKOFF_SECONDS = [60, 300, 900]  # 1m, 5m, 15m


# ---------------------------------------------------------------------------
# Idempotency & payload
# ---------------------------------------------------------------------------
def compute_payload_hash(to: str, subject: str, html: str, text: str) -> str:
    h = hashlib.sha256()
    h.update(to.encode("utf-8", "replace"))
    h.update(b"\x1f")
    h.update(subject.encode("utf-8", "replace"))
    h.update(b"\x1f")
    h.update((html or "").encode("utf-8", "replace"))
    h.update(b"\x1f")
    h.update((text or "").encode("utf-8", "replace"))
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------
async def _load_template(code: str, tenant_id: Optional[str]) -> Optional[EmailTemplateDoc]:
    db = get_db()
    # Prefer tenant-specific override
    if tenant_id:
        doc = await db.email_templates.find_one({
            "tenant_id": tenant_id, "code": code, "is_active": True, "deleted_at": None,
        })
        if doc:
            return EmailTemplateDoc(**from_mongo(doc))
    doc = await db.email_templates.find_one({
        "tenant_id": None, "code": code, "is_active": True, "deleted_at": None,
    })
    if doc:
        return EmailTemplateDoc(**from_mongo(doc))
    return None


def _render_from_file(code: str, context: Dict[str, Any]) -> Tuple[str, str, str]:
    """Fallback: render from static template files if no DB template."""
    try:
        subj_tpl = _jinja_env.get_template(f"{code}.subject.txt")
        html_tpl = _jinja_env.get_template(f"{code}.html")
        text_tpl = _jinja_env.get_template(f"{code}.txt")
        return (
            subj_tpl.render(**context).strip(),
            html_tpl.render(**context),
            text_tpl.render(**context),
        )
    except TemplateNotFound as e:
        raise RuntimeError(f"Template file '{code}' not found: {e}") from e


async def render_template(code: str, context: Dict[str, Any],
                          tenant_id: Optional[str] = None) -> Tuple[str, str, str, Optional[int]]:
    """Return (subject, html, text, template_version). DB > file."""
    doc = await _load_template(code, tenant_id)
    if doc:
        subj = _jinja_env.from_string(doc.subject).render(**context)
        html = _jinja_env.from_string(doc.html_body).render(**context)
        text = _jinja_env.from_string(doc.text_body).render(**context)
        return subj.strip(), html, text, doc.version
    subj, html, text = _render_from_file(code, context)
    return subj, html, text, None


# ---------------------------------------------------------------------------
# SMTP delivery
# ---------------------------------------------------------------------------
async def _smtp_deliver(cfg, to: str, subject: str, html: str, text: str,
                        reply_to: Optional[str] = None) -> str:
    """Send via aiosmtplib. Raises on failure. Returns SMTP server response."""
    msg = EmailMessage()
    msg["From"] = f"{cfg.mail_from_name} <{cfg.mail_from}>" if cfg.mail_from_name else cfg.mail_from
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=(cfg.mail_from or "panoramapilot.com").split("@")[-1])
    if reply_to:
        msg["Reply-To"] = reply_to
    elif cfg.reply_to:
        msg["Reply-To"] = cfg.reply_to
    msg.set_content(text or " ")
    if html:
        msg.add_alternative(html, subtype="html")

    security = (cfg.smtp_security or "ssl").lower()
    use_tls = security == "ssl"
    start_tls = security in ("starttls", "tls")
    tls_context = ssl.create_default_context() if (use_tls or start_tls) else None

    resp = await aiosmtplib.send(
        msg,
        hostname=cfg.smtp_host,
        port=cfg.smtp_port,
        username=cfg.smtp_user,
        password=cfg.smtp_password,
        use_tls=use_tls,
        start_tls=start_tls if not use_tls else False,
        tls_context=tls_context,
        timeout=30,
    )
    # aiosmtplib.send returns (errors, message) — errors is a dict of failed recipients
    errors, srv_msg = resp
    if errors:
        raise RuntimeError(f"SMTP recipient errors: {errors}")
    return (srv_msg or "").strip()[:400], msg["Message-ID"]


# ---------------------------------------------------------------------------
# Resend delivery
# ---------------------------------------------------------------------------
async def _load_attachments(log_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    from app.routers.pdf_router import _fetch_pdf_bytes
    db = get_db()
    out = []
    for a in log_doc.get("attachments") or []:
        if not a.get("pdf_id"):
            continue
        d = await db.quote_pdfs.find_one({"_id": a["pdf_id"], "tenant_id": log_doc.get("tenant_id")})
        if not d:
            raise resend_provider.ResendError(400, f"Allegato {a.get('filename')} non trovato", "attachment_missing")
        out.append({"filename": a.get("filename") or d.get("filename") or "documento.pdf", "content": await _fetch_pdf_bytes(d)})
    return out


async def _resend_deliver(log_doc: Dict[str, Any]) -> Tuple[str, str]:
    from_email = log_doc.get("from_email")
    if not from_email:
        raise resend_provider.ResendError(400, "Mittente non risolvibile: PANORAMA_MANAGED_DOMAIN non configurato", "sender_unresolved")
    mid = await resend_provider.send_email(
        from_email=from_email, from_name=log_doc.get("from_name") or "", to=log_doc["to"], subject=log_doc["subject"],
        html=log_doc.get("stored_html") or "", text=log_doc.get("stored_text") or "", reply_to=log_doc.get("reply_to"),
        attachments=await _load_attachments(log_doc), idempotency_key=f"panorama:{log_doc['id']}",
        tags={"tenant_id": log_doc.get("tenant_id") or "platform", "event_type": log_doc.get("event_type") or log_doc.get("template") or "email"},
    )
    return "resend_accepted", mid


# ---------------------------------------------------------------------------
# Main send API
# ---------------------------------------------------------------------------
async def enqueue_email(
    *,
    to: str,
    subject: Optional[str] = None,
    template: str,
    context: Optional[Dict[str, Any]] = None,
    html: Optional[str] = None,
    text: Optional[str] = None,
    tenant_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    reply_to: Optional[str] = None,
    attempt_send_now: bool = True,
    event_type: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    customer_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Enqueue an email + attempt immediate send.

    attachments: [{"filename": str, "pdf_id": str}] — i byte vengono risolti al momento dell'invio (mai nel log).

    Two modes:
      1. Template-based: pass `template` (code) + `context`. subject/html/text ignored.
      2. Legacy: pass `template` (arbitrary string) + `subject` + `html` + `text` already rendered.

    Idempotency: if `idempotency_key` is provided AND an existing log with same key exists
    with status=sent, return that existing log without resending.

    Never raises. Returns the created (or existing) log document.
    """
    db = get_db()
    cfg = get_mail_config()
    ctx = dict(context or {})
    ctx.setdefault("app_base_url", cfg.app_base_url)
    sender = await resolve_sender(db, tenant_id) if tenant_id else {"from_name": cfg.mail_from_name, "from_email": cfg.mail_from, "reply_to": cfg.reply_to, "sender_mode": "PLATFORM"}
    ctx.setdefault("brand_name", sender.get("from_name") or cfg.mail_from_name or "Panorama Pilot")

    # --- Idempotency check ---
    if idempotency_key:
        existing = await db.email_logs.find_one({
            "tenant_id": tenant_id, "idempotency_key": idempotency_key,
            # una sola email per evento: qualsiasi log non definitivamente fallito è un hit (il retry lo gestisce il worker)
            "status": {"$nin": [EMAIL_STATUS_FAILED, EMAIL_STATUS_BOUNCED]},
        })
        if existing:
            logger.info("email idempotent hit key=%s status=%s", idempotency_key, existing.get("status"))
            return from_mongo(existing)

    # --- Render body ---
    template_version: Optional[int] = None
    if template in EMAIL_TEMPLATE_CODES:
        try:
            subject_r, html_r, text_r, template_version = await render_template(
                template, ctx, tenant_id=tenant_id,
            )
            subject = subject_r
            html = html_r
            text = text_r
        except Exception as e:  # noqa: BLE001
            logger.exception("email template render failed template=%s: %s", template, e)
            # fall through with whatever html/text/subject we have; mark failure below
    if subject is None:
        subject = "(no subject)"
    if html is None and text is None:
        text = subject
        html = f"<p>{subject}</p>"

    # --- Delivery mode redirect (protection preview) ---
    original_to = to
    actual_to = to
    subject_final = subject
    if cfg.delivery_mode == DELIVERY_MODE_TEST and cfg.test_redirect_to:
        actual_to = cfg.test_redirect_to
        subject_final = f"[TEST - Destinatario originale: {original_to}] {subject}"

    # --- Build log ---
    now = datetime.now(timezone.utc)
    payload_hash = compute_payload_hash(actual_to, subject_final, html or "", text or "")
    log = EmailLogV2(
        id=new_id(),
        tenant_id=tenant_id,
        to=actual_to,
        original_to=original_to,
        subject=subject_final,
        template=template,
        template_version=template_version,
        delivery_mode=cfg.delivery_mode,
        status=EMAIL_STATUS_QUEUED,
        provider=cfg.provider_name,
        attempt_count=0,
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
        stored_html=html,
        stored_text=text,
        reply_to=reply_to or sender.get("reply_to") or cfg.reply_to,
        created_at=now,
        updated_at=now,
    )
    doc = to_mongo(log.model_dump(by_alias=True))
    doc["event_type"] = event_type or template
    doc.update({"delivery_status": DELIVERY_QUEUED, "from_email": sender.get("from_email"), "from_name": sender.get("from_name"),
                "sender_mode": sender.get("sender_mode"), "attachments": [{"filename": a.get("filename"), "pdf_id": a.get("pdf_id")} for a in (attachments or [])],
                "customer_id": customer_id, "entity_type": entity_type, "entity_id": entity_id, "delivery_events": []})
    await db.email_logs.insert_one(doc)

    if not attempt_send_now:
        return from_mongo(doc)

    result = await _attempt_send(log_id=log.id)
    return result


async def _attempt_send(log_id: str) -> Dict[str, Any]:
    """Try to send a queued/retrying email. Updates the log with status + attempt_count."""
    db = get_db()
    cfg = get_mail_config()
    doc = await db.email_logs.find_one({"_id": log_id})
    if not doc:
        return {"ok": False, "error": "log_not_found"}
    log_doc = from_mongo(doc)

    # Nessun provider configurato => configuration_required, visibile all'Admin (mai fallback silenzioso a mock)
    if not cfg.is_configured:
        await db.email_logs.update_one(
            {"_id": log_id},
            {"$set": {
                "status": EMAIL_STATUS_CONFIG_REQUIRED,
                "delivery_status": DELIVERY_FAILED,
                "error": "RESEND_CONFIGURATION=BLOCKED_BY_CONFIGURATION: RESEND_API_KEY non impostata",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        logger.warning("email provider not configured — log id=%s parked", log_id)
        d2 = await db.email_logs.find_one({"_id": log_id})
        return from_mongo(d2)

    now = datetime.now(timezone.utc)
    attempt = int(log_doc.get("attempt_count") or 0) + 1
    await db.email_logs.update_one(
        {"_id": log_id},
        {"$set": {
            "status": EMAIL_STATUS_SENDING,
            "attempt_count": attempt,
            "last_attempt_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }},
    )
    permanent = False
    try:
        if cfg.provider_name == "resend":
            srv_resp, provider_message_id = await _resend_deliver(log_doc)
        else:
            srv_resp, provider_message_id = await _smtp_deliver(
                cfg,
                to=log_doc["to"],
                subject=log_doc["subject"],
                html=log_doc.get("stored_html") or "",
                text=log_doc.get("stored_text") or "",
                reply_to=log_doc.get("reply_to"),
            )
        final_status = EMAIL_STATUS_TEST_INTERCEPTED if (
            log_doc.get("delivery_mode") == DELIVERY_MODE_TEST and log_doc.get("to") != log_doc.get("original_to")
        ) else EMAIL_STATUS_SENT
        await db.email_logs.update_one(
            {"_id": log_id},
            {"$set": {
                "status": final_status,
                "delivery_status": DELIVERY_SENT,  # accettato dal provider, NON delivered (webhook)
                "provider": cfg.provider_name,
                "provider_message_id": provider_message_id,
                "smtp_response": srv_resp,
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "next_retry_at": None,
                "error": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, "$push": {"delivery_events": {"type": "provider_accepted", "at": datetime.now(timezone.utc).isoformat(), "provider_message_id": provider_message_id}}},
        )
        logger.info("email sent id=%s to=%s status=%s", log_id, log_doc["to"], final_status)
    except Exception as e:  # noqa: BLE001
        permanent = isinstance(e, resend_provider.ResendError) and not e.is_temporary
        max_attempts = int(log_doc.get("max_attempts") or 3)
        will_retry = attempt < max_attempts and not permanent
        next_retry = None
        if will_retry:
            backoff = RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)]
            next_retry = (datetime.now(timezone.utc) + timedelta(seconds=backoff)).isoformat()
        # Sanitize error to avoid leaking password (never present in aiosmtplib exception str usually,
        # but be safe: never echo cfg.smtp_password in msg)
        err_msg = str(e)[:500]
        if cfg.smtp_password and cfg.smtp_password in err_msg:
            err_msg = err_msg.replace(cfg.smtp_password, "***REDACTED***")
        await db.email_logs.update_one(
            {"_id": log_id},
            {"$set": {
                "status": EMAIL_STATUS_RETRYING if will_retry else EMAIL_STATUS_FAILED,
                "delivery_status": "failed",
                "error_code": type(e).__name__,
                "error": err_msg,
                "next_retry_at": next_retry,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        logger.warning("email attempt %s/%s failed id=%s err=%s next=%s",
                       attempt, max_attempts, log_id, err_msg, next_retry)
    d2 = await db.email_logs.find_one({"_id": log_id})
    return from_mongo(d2)


# ---------------------------------------------------------------------------
# Retry background loop
# ---------------------------------------------------------------------------
_retry_task: Optional[asyncio.Task] = None
_retry_stop = False


async def _retry_worker():
    logger.info("email retry worker started")
    while not _retry_stop:
        try:
            db = get_db()
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor = db.email_logs.find({
                "status": EMAIL_STATUS_RETRYING,
                "next_retry_at": {"$lte": now_iso},
            }).limit(20)
            pending = await cursor.to_list(20)
            for d in pending:
                await _attempt_send(d["_id"])
        except Exception as e:  # noqa: BLE001
            logger.exception("retry worker iteration failed: %s", e)
        await asyncio.sleep(15)


def start_retry_worker():
    global _retry_task, _retry_stop
    if _retry_task and not _retry_task.done():
        return
    _retry_stop = False
    _retry_task = asyncio.create_task(_retry_worker())


def stop_retry_worker():
    global _retry_stop
    _retry_stop = True


async def manual_retry(log_id: str) -> Dict[str, Any]:
    """Force a retry attempt for a specific failed/retrying email."""
    db = get_db()
    doc = await db.email_logs.find_one({"_id": log_id})
    if not doc:
        return {"ok": False, "error": "not_found"}
    if doc.get("status") in (EMAIL_STATUS_SENT, EMAIL_STATUS_TEST_INTERCEPTED):
        return {"ok": True, "already_sent": True, "log": from_mongo(doc)}
    await db.email_logs.update_one(
        {"_id": log_id},
        {"$set": {"attempt_count": 0, "max_attempts": max(3, int(doc.get("attempt_count") or 0) + 3)}},
    )
    return await _attempt_send(log_id=log_id)
