"""QUOTE EMAIL — invio reale del preventivo al cliente via provider (Resend) con PDF allegato.
Eventi distinti (PO §8): QUOTE_STATUS_CHANGED_TO_SENT ≠ QUOTE_EMAIL_SEND_REQUESTED / PROVIDER_ACCEPTED / DELIVERED / BOUNCED / FAILED.
Destinatario risolto server-side (customer.email), corpo da template tenant; il commerciale può solo aggiungere un messaggio (testo, escapato)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from html import escape
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.mongo_utils import from_mongo
from app.routers.quotes import _get_perms, ADMIN_MASTER_MARKER
from app.services.audit import record_audit
from app.services.email_config import get_mail_config
from app.services.email_service import enqueue_email, render_template
from app.services.tenant_email import company_brand, resolve_sender
from app.services.timeline import record_activity

router = APIRouter(prefix="/quotes", tags=["quote-email"])
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PUBLIC_LOG_KEYS = ("id", "status", "delivery_status", "provider", "original_to", "to", "from_email", "from_name", "subject", "attachments",
                   "sent_at", "delivered_at", "created_at", "updated_at", "error", "attempt_count", "next_retry_at", "delivery_events", "event_type", "requested_by_email")


class SendBody(BaseModel):
    pdf_id: Optional[str] = None
    message: Optional[str] = Field(None, max_length=1500)


def _fmt_eur(v: Any) -> str:
    return f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def _load(db, qid: str, user: dict) -> Dict[str, Any]:
    doc = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Preventivo non trovato")
    return doc


async def _resolve_pdf(db, quote: dict, pdf_id: Optional[str]) -> Optional[dict]:
    q = {"tenant_id": quote["tenant_id"], "quote_id": quote["_id"], "kind": "definitive", "invalidated_at": None}
    if pdf_id:
        q["_id"] = pdf_id
    return await db.quote_pdfs.find_one(q, {"pdf_base64": 0, "snapshot": 0}, sort=[("generated_at", -1)])


async def _compose(db, quote: dict, user: dict, message: Optional[str], pdf: Optional[dict]) -> Dict[str, Any]:
    cust = await db.customers.find_one({"_id": quote.get("customer_id"), "tenant_id": quote["tenant_id"], "deleted_at": None}) or {}
    to = (cust.get("email") or "").strip()
    brand = await company_brand(db, quote["tenant_id"])
    sender = await resolve_sender(db, quote["tenant_id"])
    name = " ".join(x for x in (cust.get("first_name"), cust.get("last_name")) if x) or cust.get("company_name") or cust.get("name") or "cliente"
    ctx = {"quote_number": quote.get("number"), "customer_name": escape(name), "total": _fmt_eur(quote.get("total")), "company_name": escape(brand["name"]),
           "brand_name": escape(brand["name"]),
           "company_phone": brand.get("phone"), "company_email": brand.get("email"), "company_website": brand.get("website"), "app_base_url": get_mail_config().app_base_url}
    if message and message.strip():
        ctx["message"] = escape(message.strip()).replace("\n", "<br />")
    subject, html, text, tv = await render_template("QUOTE_SENT", ctx, tenant_id=quote["tenant_id"])
    if message:
        text = text.replace(escape(message.strip()).replace("\n", "<br />"), message.strip())
    return {"to": to or None, "to_valid": bool(to and _EMAIL_RE.match(to)), "customer_id": cust.get("_id"), "customer_name": name, "sender": sender,
            "subject": subject, "html": html, "text": text, "template": "QUOTE_SENT", "template_version": tv,
            "attachments": [{"filename": pdf["filename"], "pdf_id": pdf["_id"], "size_bytes": pdf.get("size_bytes")}] if pdf else [],
            "provider": get_mail_config().provider_name, "provider_configured": get_mail_config().is_configured}


@router.get("/{qid}/email/preview")
async def preview_quote_email(qid: str, pdf_id: Optional[str] = None, message: Optional[str] = None, user: dict = Depends(require_permission("quotes.send"))):
    db = get_db()
    quote = await _load(db, qid, user)
    pdf = await _resolve_pdf(db, quote, pdf_id)
    c = await _compose(db, quote, user, message, pdf)
    c.pop("text", None)
    c["blockers"] = ([] if c["to_valid"] else ["CUSTOMER_EMAIL_MISSING_OR_INVALID"]) + ([] if pdf else ["DEFINITIVE_PDF_MISSING"]) + ([] if c["provider_configured"] else ["RESEND_CONFIGURATION=BLOCKED_BY_SECRET"])
    return c


@router.post("/{qid}/email/send")
async def send_quote_email(qid: str, body: SendBody, request: Request, user: dict = Depends(require_permission("quotes.send"))):
    db = get_db()
    quote = await _load(db, qid, user)
    if quote.get("quote_status") in ("cancelled", "superseded", "expired", "rejected"):
        raise HTTPException(409, {"code": "QUOTE_NOT_SENDABLE", "message": f"Stato {quote.get('quote_status')}: invio non consentito"})
    pdf = await _resolve_pdf(db, quote, body.pdf_id)
    if not pdf:
        raise HTTPException(400, {"code": "DEFINITIVE_PDF_MISSING", "message": "Genera il PDF definitivo prima dell'invio"})
    c = await _compose(db, quote, user, body.message, pdf)
    if not c["to_valid"]:
        raise HTTPException(400, {"code": "CUSTOMER_EMAIL_MISSING_OR_INVALID", "message": "Email cliente mancante o non valida"})
    now = datetime.now(timezone.utc).isoformat()
    await record_activity(tenant_id=quote["tenant_id"], type="quote_email_send_requested", subject=f"Richiesto invio email preventivo {quote.get('number')}",
                          body=f"A: {c['to']} · Da: {c['sender']['from_name']} <{c['sender']['from_email']}> · Allegato: {pdf['filename']}",
                          customer_id=quote.get("customer_id"), quote_id=qid, user_id=user["id"], user_email=user["email"],
                          meta={"event": "QUOTE_EMAIL_SEND_REQUESTED", "pdf_id": pdf["_id"]})
    log = await enqueue_email(to=c["to"], template="QUOTE_EMAIL", subject=c["subject"], html=c["html"], text=c["text"], tenant_id=quote["tenant_id"],
                              idempotency_key=f"quote_email:{qid}:{pdf['pdf_hash']}:{user['id']}:{now[:16]}", event_type="QUOTE_EMAIL",
                              attachments=[{"filename": pdf["filename"], "pdf_id": pdf["_id"]}], customer_id=quote.get("customer_id"), entity_type="quote", entity_id=qid)
    await db.email_logs.update_one({"_id": log["id"]}, {"$set": {"requested_by": user["id"], "requested_by_email": user["email"], "quote_number": quote.get("number")}})
    accepted = log.get("delivery_status") == "provider_accepted"
    ev = "QUOTE_EMAIL_PROVIDER_ACCEPTED" if accepted else ("QUOTE_EMAIL_FAILED" if log.get("status") in ("failed", "configuration_required") else "QUOTE_EMAIL_QUEUED")
    await record_activity(tenant_id=quote["tenant_id"], type=f"quote_email_{'provider_accepted' if accepted else ('failed' if ev == 'QUOTE_EMAIL_FAILED' else 'queued')}",
                          subject=f"Email preventivo {quote.get('number')}: {'INVIATA (accettata dal provider)' if accepted else ('ERRORE' if ev == 'QUOTE_EMAIL_FAILED' else 'IN CODA')}",
                          body=f"A: {c['to']} · Da: {c['sender']['from_name']} <{c['sender']['from_email']}> · Provider: {log.get('provider')} · Allegato: {pdf['filename']}" + (f" · Errore: {log.get('error')}" if log.get("error") else ""),
                          customer_id=quote.get("customer_id"), quote_id=qid, user_id=user["id"], user_email=user["email"],
                          meta={"event": ev, "email_log_id": log["id"], "delivery_status": log.get("delivery_status")})
    status_changed = False
    if accepted and quote.get("quote_status") in ("draft", "to_complete", "approved"):
        await db.quotes.update_one({"_id": qid}, {"$set": {"quote_status": "sent", "sent_at": now, "sent_by": user["id"], "updated_at": now, "updated_by": user["id"]}})
        await record_activity(tenant_id=quote["tenant_id"], type="quote_sent", subject=f"Preventivo {quote.get('number')}: sent", body="Stato aggiornato a seguito dell'invio email",
                              customer_id=quote.get("customer_id"), quote_id=qid, user_id=user["id"], user_email=user["email"], meta={"event": "QUOTE_STATUS_CHANGED_TO_SENT"})
        status_changed = True
    await db.quotes.update_one({"_id": qid}, {"$set": {"last_email_log_id": log["id"], "last_email_at": now}})
    await record_audit(action="quotes.email_send", tenant_id=quote["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
                       entity_type="quote", entity_id=qid, after={"email_log_id": log["id"], "to": c["to"], "status": log.get("status"), "delivery_status": log.get("delivery_status"), "pdf_id": pdf["_id"]})
    if log.get("status") == "configuration_required":
        raise HTTPException(503, {"code": "RESEND_CONFIGURATION", "status": "BLOCKED_BY_SECRET", "message": "Provider email non configurato: nessuna email inviata", "email_log_id": log["id"]})
    return {"ok": accepted, "email": _public(log, True), "quote_status_changed": status_changed, "event": ev}


def _public(log: dict, is_admin: bool) -> dict:
    out = {k: log.get(k) for k in PUBLIC_LOG_KEYS}
    if is_admin:
        out["provider_message_id"] = log.get("provider_message_id")
    return out


@router.get("/{qid}/emails")
async def list_quote_emails(qid: str, user: dict = Depends(require_permission("quotes.view"))):
    db = get_db()
    await _load(db, qid, user)
    perms = await _get_perms(user)
    items = await db.email_logs.find({"tenant_id": user["tenant_id"], "entity_type": "quote", "entity_id": qid}, {"stored_html": 0, "stored_text": 0}).sort("created_at", -1).to_list(50)
    return {"items": [_public(from_mongo(i), ADMIN_MASTER_MARKER in perms) for i in items]}
