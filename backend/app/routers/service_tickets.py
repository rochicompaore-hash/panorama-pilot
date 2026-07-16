"""M13 — Service tickets (assistenza)."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models import new_id
from app.models_ops import ServiceTicket
from app.services.ops_common import (create_doc, get_doc, list_docs, update_doc, soft_delete_doc,
                                       enforce_status_transition)

router = APIRouter(prefix="/service-tickets", tags=["service-tickets"])

TICKET_FLOW = {
    "opened": {"triaged", "rejected", "closed"},
    "triaged": {"waiting_customer", "waiting_material", "scheduled", "in_progress", "rejected", "closed"},
    "waiting_customer": {"triaged", "scheduled", "in_progress", "closed"},
    "waiting_material": {"triaged", "scheduled", "in_progress", "closed"},
    "scheduled": {"in_progress", "waiting_customer", "waiting_material", "closed"},
    "in_progress": {"resolved", "waiting_customer", "waiting_material", "closed"},
    "resolved": {"closed", "in_progress"},
    "closed": set(),
    "rejected": set(),
}


class TicketCreate(BaseModel):
    customer_id: str
    sales_order_id: Optional[str] = None
    installation_plan_id: Optional[str] = None
    product_ref: Optional[str] = None
    opening_ref: Optional[str] = None
    subject: str
    description: Optional[str] = None
    priority: str = "normal"
    warranty_scope: Optional[str] = None


@router.get("")
async def list_tickets(q: Optional[str] = None, customer_id: Optional[str] = None,
                       ticket_status: Optional[str] = None, priority: Optional[str] = None,
                       skip: int = 0, limit: int = Query(50, le=200),
                       user: dict = Depends(require_permission("service.view"))):
    return await list_docs(collection="service_tickets", tenant_id=user["tenant_id"],
                            filters={"customer_id": customer_id, "ticket_status": ticket_status, "priority": priority},
                            search_fields=["number", "subject"], q=q,
                            sort=[("priority", -1), ("created_at", -1)], skip=skip, limit=limit)


@router.get("/{tid}")
async def get_ticket(tid: str, user: dict = Depends(require_permission("service.view"))):
    return await get_doc(collection="service_tickets", doc_id=tid, tenant_id=user["tenant_id"])


@router.post("")
async def create_ticket(body: TicketCreate, request: Request,
                        user: dict = Depends(require_permission("service.create"))):
    t = ServiceTicket(id=new_id(), **body.model_dump())
    return await create_doc(collection="service_tickets", model_instance=t, user=user,
                             entity_type="service_ticket", ip=get_client_ip(request),
                             set_number=True, number_key="service_ticket", number_prefix="ASS-")


@router.patch("/{tid}")
async def patch_ticket(tid: str, body: dict, request: Request,
                       user: dict = Depends(require_permission("service.edit"))):
    return await update_doc(collection="service_tickets", doc_id=tid, updates=body, user=user,
                             entity_type="service_ticket", ip=get_client_ip(request))


class TicketStatus(BaseModel):
    ticket_status: str
    resolution: Optional[str] = None


@router.post("/{tid}/status")
async def change_status(tid: str, body: TicketStatus, request: Request,
                         user: dict = Depends(require_permission("service.edit"))):
    db = get_db()
    existing = await db.service_tickets.find_one({"_id": tid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not existing: raise HTTPException(status_code=404, detail="Ticket non trovato")
    enforce_status_transition(existing.get("ticket_status", "opened"), body.ticket_status, TICKET_FLOW)
    updates = {"ticket_status": body.ticket_status}
    if body.ticket_status in ("resolved", "closed"):
        updates["resolved_at"] = datetime.now(timezone.utc).isoformat()
    return await update_doc(collection="service_tickets", doc_id=tid, updates=updates, user=user,
                             entity_type="service_ticket", ip=get_client_ip(request))


@router.get("/dashboard/kpi")
async def ticket_kpi(user: dict = Depends(require_permission("service.view"))):
    db = get_db()
    tenant = user["tenant_id"]
    counts = {}
    for st in TICKET_FLOW.keys():
        counts[st] = await db.service_tickets.count_documents({"tenant_id": tenant, "ticket_status": st, "deleted_at": None})
    open_count = sum(counts.get(s, 0) for s in ("opened", "triaged", "waiting_customer", "waiting_material", "scheduled", "in_progress"))
    return {"counts_by_status": counts, "open_count": open_count, "closed_count": counts.get("closed", 0)}
