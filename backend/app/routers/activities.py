"""Activities / Timeline router + comms (call, email, whatsapp)."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models_crm import (
    ActivityCreate, SendEmailRequest, SendWhatsAppRequest, LogCallRequest,
)
from app.mongo_utils import from_mongo
from app.services.audit import record_audit
from app.services.timeline import record_activity
from app.services.email import send_email
from app.services.whatsapp import send_whatsapp

router = APIRouter(prefix="/activities", tags=["activities"])


@router.get("")
async def list_activities(
    lead_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    contact_id: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = Query(100, le=500),
    skip: int = 0,
    user: dict = Depends(require_permission("crm.activities.view")),
):
    db = get_db()
    query: dict = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if lead_id: query["lead_id"] = lead_id
    if customer_id: query["customer_id"] = customer_id
    if contact_id: query["contact_id"] = contact_id
    if type: query["type"] = type
    total = await db.activities.count_documents(query)
    docs = await db.activities.find(query).sort("occurred_at", -1).skip(skip).limit(limit).to_list(limit)
    # Enrich with user email
    user_ids = list({d.get("created_by") for d in docs if d.get("created_by")})
    users = await db.users.find({"_id": {"$in": user_ids}}).to_list(len(user_ids)) if user_ids else []
    umap = {u["_id"]: u for u in users}
    items = []
    for d in docs:
        d = from_mongo(d)
        u = umap.get(d.get("created_by"))
        d["_by_email"] = u["email"] if u else None
        d["_by_name"] = f'{u.get("first_name","")} {u.get("last_name","")}'.strip() if u else None
        items.append(d)
    return {"total": total, "items": items}


@router.post("")
async def create_activity(
    body: ActivityCreate, request: Request,
    user: dict = Depends(require_permission("crm.activities.create")),
):
    aid = await record_activity(
        tenant_id=user["tenant_id"], type=body.type, subject=body.subject, body=body.body,
        direction=body.direction, outcome=body.outcome, duration_seconds=body.duration_seconds,
        occurred_at=body.occurred_at, lead_id=body.lead_id, customer_id=body.customer_id,
        contact_id=body.contact_id, quote_id=body.quote_id, order_id=body.order_id,
        assigned_to=body.assigned_to, user_id=user["id"], user_email=user["email"], meta=body.meta,
    )
    await record_audit(action="crm.activities.create", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="activity", entity_id=aid, after={"type": body.type, "subject": body.subject})
    db = get_db()
    return from_mongo(await db.activities.find_one({"_id": aid}))


# ---- Comms ----
@router.post("/log-call")
async def log_call(body: LogCallRequest, request: Request, user: dict = Depends(require_permission("crm.comms.call"))):
    aid = await record_activity(
        tenant_id=user["tenant_id"], type="call",
        subject=body.subject, body=body.notes, direction=body.direction, outcome=body.outcome,
        duration_seconds=body.duration_seconds, lead_id=body.lead_id,
        customer_id=body.customer_id, contact_id=body.contact_id,
        user_id=user["id"], user_email=user["email"],
        meta={"phone": body.to},
    )
    db = get_db()
    return from_mongo(await db.activities.find_one({"_id": aid}))


@router.post("/send-email")
async def send_email_action(body: SendEmailRequest, request: Request, user: dict = Depends(require_permission("crm.comms.email"))):
    log_id = await send_email(body.to, body.subject, "crm_email",
                              f"<div>{body.body.replace(chr(10), '<br>')}</div>",
                              body.body)
    aid = await record_activity(
        tenant_id=user["tenant_id"], type="email",
        subject=f"Email inviata: {body.subject}", body=body.body,
        direction="out", lead_id=body.lead_id, customer_id=body.customer_id, contact_id=body.contact_id,
        user_id=user["id"], user_email=user["email"],
        meta={"to": body.to, "email_log_id": log_id},
    )
    db = get_db()
    return {"activity": from_mongo(await db.activities.find_one({"_id": aid})), "email_log_id": log_id}


@router.post("/send-whatsapp")
async def send_whatsapp_action(body: SendWhatsAppRequest, request: Request, user: dict = Depends(require_permission("crm.comms.whatsapp"))):
    result = await send_whatsapp(
        tenant_id=user["tenant_id"], to=body.to, body=body.body,
        template_id=body.template_id, template_variables=body.template_variables,
        subject=body.subject, user_id=user["id"],
    )
    aid = await record_activity(
        tenant_id=user["tenant_id"], type="whatsapp",
        subject=f"WhatsApp inviato a {body.to}",
        body=body.body or f"Template: {body.template_id}",
        direction="out", lead_id=body.lead_id, customer_id=body.customer_id, contact_id=body.contact_id,
        user_id=user["id"], user_email=user["email"],
        meta={"to": body.to, "whatsapp_log_id": result.get("log_id"), "status": result.get("status")},
    )
    db = get_db()
    return {"activity": from_mongo(await db.activities.find_one({"_id": aid})), "whatsapp": result}


@router.get("/whatsapp-logs")
async def whatsapp_logs(limit: int = Query(50, le=200), skip: int = 0, user: dict = Depends(require_permission("audit.view"))):
    db = get_db()
    q = {"tenant_id": user["tenant_id"]}
    total = await db.whatsapp_logs.count_documents(q)
    docs = await db.whatsapp_logs.find(q).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": [from_mongo(d) for d in docs]}
