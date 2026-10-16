"""Resend webhooks — /api/email-webhooks/resend. Firma Svix verificata, idempotente (svix-id), replay-safe, tenant-safe.
Mappa email.sent/delivered/delivery_delayed/bounced/failed/complained → delivery_status + timeline cliente + task su bounce."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from app.db import get_db
from app.models import new_id
from app.services import resend_provider
from app.services.audit import record_audit
from app.services.timeline import record_activity

router = APIRouter(prefix="/email-webhooks", tags=["email-webhooks"])
logger = logging.getLogger("email_webhooks")

EVENT_MAP = {"email.sent": "provider_accepted", "email.delivered": "delivered", "email.delivery_delayed": "deferred",
             "email.bounced": "bounced", "email.failed": "failed", "email.complained": "complained"}
STATUS_LABEL = {"provider_accepted": "INVIATA", "delivered": "CONSEGNATA", "deferred": "IN RITARDO", "bounced": "BOUNCE", "failed": "ERRORE", "complained": "SEGNALATA SPAM"}
_RANK = {"queued": 0, "provider_accepted": 1, "deferred": 2, "delivered": 3, "bounced": 3, "failed": 3, "complained": 4}


def _safe_reason(ev_type: str, data: Dict[str, Any]) -> Optional[str]:
    if ev_type == "email.bounced":
        b = data.get("bounce") or {}
        sub = str(b.get("subType") or b.get("type") or "").lower()
        if "suppressed" in sub or "onaccountsuppressionlist" in sub:
            return "indirizzo in lista di soppressione del provider"
        if "general" in sub or "noemail" in sub or "permanent" in str(b.get("type") or "").lower():
            return "indirizzo destinatario non valido"
        return "rifiutato dal server del destinatario"
    if ev_type == "email.failed":
        return "provider rejected"
    if ev_type == "email.complained":
        return "segnalata come spam dal destinatario"
    return None


async def _open_bounce_task(db, log: Dict[str, Any], reason: str):
    if not log.get("tenant_id"):
        return
    now = datetime.now(timezone.utc)
    exists = await db.tasks.find_one({"tenant_id": log["tenant_id"], "email_log_id": log["_id"], "deleted_at": None})
    if exists:
        return
    await db.tasks.insert_one({"_id": new_id(), "tenant_id": log["tenant_id"], "title": "VERIFICA EMAIL CLIENTE", "priority": "high", "task_status": "open",
                              "description": f"Email non consegnata a {log.get('original_to')} ({reason}). Verificare l'indirizzo del cliente. Rif. {log.get('entity_type') or ''} {log.get('entity_id') or ''}".strip(),
                              "assigned_to": log.get("created_by") or log.get("requested_by"), "customer_id": log.get("customer_id"), "lead_id": None,
                              "email_log_id": log["_id"], "task_type": "CUSTOMER_EMAIL_DELIVERY_PROBLEM", "status": "active", "deleted_at": None,
                              "created_at": now, "updated_at": now})
    if log.get("customer_id"):
        await db.customers.update_one({"_id": log["customer_id"], "tenant_id": log["tenant_id"]},
                                      {"$set": {"email_status": "NEEDS_VERIFICATION", "email_status_reason": reason, "email_status_at": now.isoformat()}})


async def apply_provider_event(db, *, ev_type: str, provider_message_id: str, data: Dict[str, Any], event_id: str, occurred_at: Optional[str]) -> Dict[str, Any]:
    """Applica un evento provider a un email_log. Idempotente per event_id. Usato dal webhook e dai test."""
    status = EVENT_MAP.get(ev_type)
    if not status:
        return {"ok": True, "ignored": ev_type}
    dup = await db.email_webhook_events.find_one({"_id": event_id})
    if dup:
        return {"ok": True, "duplicate": True}
    now = datetime.now(timezone.utc).isoformat()
    log = await db.email_logs.find_one({"provider_message_id": provider_message_id})
    await db.email_webhook_events.insert_one({"_id": event_id, "type": ev_type, "provider_message_id": provider_message_id, "received_at": now,
                                              "occurred_at": occurred_at, "email_log_id": (log or {}).get("_id"), "tenant_id": (log or {}).get("tenant_id"), "matched": bool(log)})
    if not log:
        logger.warning("webhook %s per message_id sconosciuto", ev_type)
        return {"ok": True, "matched": False}
    reason = _safe_reason(ev_type, data)
    upd: Dict[str, Any] = {"updated_at": now}
    if _RANK.get(status, 0) >= _RANK.get(log.get("delivery_status") or "queued", 0):
        upd["delivery_status"] = status
        if status == "delivered":
            upd["delivered_at"] = occurred_at or now
        if status in ("bounced", "failed"):
            upd["status"] = status
            upd["error"] = reason
            upd["next_retry_at"] = None
        if status == "complained":
            upd["complained_at"] = occurred_at or now
    await db.email_logs.update_one({"_id": log["_id"]}, {"$set": upd, "$push": {"delivery_events": {"type": status, "at": occurred_at or now, "event_id": event_id, "reason": reason}}})
    if log.get("tenant_id") and status != "provider_accepted":
        await record_activity(tenant_id=log["tenant_id"], type=f"email_{status}", subject=f"Email {STATUS_LABEL.get(status, status)}: {log.get('subject')}",
                              body=(f"A: {log.get('original_to')} · Da: {log.get('from_name') or ''} <{log.get('from_email') or ''}> · Stato: {status.upper()}" + (f" · Motivo: {reason}" if reason else "")),
                              customer_id=log.get("customer_id"), quote_id=log.get("entity_id") if log.get("entity_type") == "quote" else None,
                              meta={"email_log_id": log["_id"], "delivery_status": status, "provider": "resend", "entity_type": log.get("entity_type"), "entity_id": log.get("entity_id"), "reason": reason})
    if status in ("bounced", "failed", "complained"):
        await _open_bounce_task(db, log, reason or status)
    await record_audit(action=f"email.webhook.{status}", tenant_id=log.get("tenant_id"), user_id=None, user_email="webhook@resend", ip=None,
                       entity_type="email_log", entity_id=log["_id"], after={"event": ev_type, "delivery_status": status, "reason": reason})
    return {"ok": True, "matched": True, "delivery_status": status}


@router.post("/resend")
async def resend_webhook(request: Request):
    raw = await request.body()
    h = request.headers
    if not resend_provider.webhook_configured():
        raise HTTPException(503, {"code": "RESEND_WEBHOOK_SECRET_MISSING"})
    if not resend_provider.verify_webhook(raw, h.get("svix-id", ""), h.get("svix-timestamp", ""), h.get("svix-signature", "")):
        raise HTTPException(400, {"code": "WEBHOOK_SIGNATURE_INVALID"})
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(400, {"code": "WEBHOOK_PAYLOAD_INVALID"})
    data = payload.get("data") or {}
    return await apply_provider_event(get_db(), ev_type=str(payload.get("type") or ""), provider_message_id=str(data.get("email_id") or ""),
                                      data=data, event_id=h.get("svix-id", new_id()), occurred_at=payload.get("created_at"))
