"""Email logs viewer + retry — tenant-scoped."""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.db import get_db
from app.deps import require_permission, get_client_ip, require_any_permission
from app.mongo_utils import from_mongo
from app.services.audit import record_audit
from app.services.email_service import manual_retry

router = APIRouter(prefix="/email-logs", tags=["email-logs"])


def _scope_query(user: dict, extra: Optional[dict] = None) -> dict:
    q: dict = extra or {}
    if user.get("is_superadmin") or user.get("is_platform_owner"):
        return q
    tenant_id = user.get("tenant_id")
    q["tenant_id"] = tenant_id
    return q


@router.get("")
async def list_logs(
    limit: int = Query(50, le=200),
    skip: int = 0,
    status: Optional[str] = Query(None, description="Filter by status"),
    template: Optional[str] = Query(None),
    to: Optional[str] = Query(None, description="Filter by recipient (substring)"),
    user: dict = Depends(require_any_permission("email.view_logs", "audit.view")),
):
    db = get_db()
    q = _scope_query(user, {})
    if status:
        q["status"] = status
    if template:
        q["template"] = template
    if to:
        q["$or"] = [{"to": {"$regex": to, "$options": "i"}},
                    {"original_to": {"$regex": to, "$options": "i"}}]
    total = await db.email_logs.count_documents(q)
    docs = await db.email_logs.find(q).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    items = []
    for d in docs:
        f = from_mongo(d)
        # Redact stored html/text summary — never expose full body from list endpoint
        items.append({
            "id": f["id"],
            "tenant_id": f.get("tenant_id"),
            "to": f.get("to"),
            "original_to": f.get("original_to"),
            "subject": f.get("subject"),
            "template": f.get("template"),
            "template_version": f.get("template_version"),
            "status": f.get("status"),
            "provider": f.get("provider"),
            "delivery_mode": f.get("delivery_mode"),
            "attempt_count": f.get("attempt_count", 0),
            "max_attempts": f.get("max_attempts", 3),
            "next_retry_at": f.get("next_retry_at"),
            "last_attempt_at": f.get("last_attempt_at"),
            "sent_at": f.get("sent_at"),
            "error": f.get("error"),
            "created_at": f.get("created_at"),
            "idempotency_key": f.get("idempotency_key"),
        })
    # Aggregated status counts (respects tenant scope)
    pipeline = [{"$match": q}, {"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    agg = await db.email_logs.aggregate(pipeline).to_list(20)
    counts = {a["_id"] or "unknown": a["count"] for a in agg}
    return {"total": total, "items": items, "counts_by_status": counts}


@router.get("/{log_id}")
async def get_log(
    log_id: str,
    user: dict = Depends(require_any_permission("email.view_logs", "audit.view")),
):
    db = get_db()
    doc = await db.email_logs.find_one(_scope_query(user, {"_id": log_id}))
    if not doc:
        raise HTTPException(status_code=404, detail="Log email non trovato")
    f = from_mongo(doc)
    # Detail: include stored html/text (for retry preview) but NEVER any password
    return {
        **{k: f.get(k) for k in [
            "id", "tenant_id", "to", "original_to", "subject", "template",
            "template_version", "status", "provider", "delivery_mode",
            "attempt_count", "max_attempts", "next_retry_at", "last_attempt_at",
            "sent_at", "error", "error_code", "created_at", "idempotency_key", "smtp_response",
            "event_type", "delivery_status", "provider_message_id",
            "payload_hash", "reply_to",
        ]},
        "stored_html": f.get("stored_html"),
        "stored_text": f.get("stored_text"),
    }


@router.post("/{log_id}/retry")
async def retry_log(
    log_id: str, request: Request,
    user: dict = Depends(require_permission("email.retry")),
):
    db = get_db()
    doc = await db.email_logs.find_one(_scope_query(user, {"_id": log_id}))
    if not doc:
        raise HTTPException(status_code=404, detail="Log email non trovato")
    result = await manual_retry(log_id)
    await record_audit(
        action="email.retry", tenant_id=user.get("tenant_id"),
        user_id=user["id"], user_email=user.get("email"),
        ip=get_client_ip(request),
        entity_type="email_log", entity_id=log_id,
        after={"new_status": result.get("status")},
    )
    return {
        "id": result.get("id"),
        "status": result.get("status"),
        "attempt_count": result.get("attempt_count"),
        "error": result.get("error"),
    }
