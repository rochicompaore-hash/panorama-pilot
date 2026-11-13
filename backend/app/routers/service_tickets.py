"""M13 — Service tickets (assistenza)."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime
from typing import Literal
from app.services.operational_control import ticket_clock
from app.mongo_utils import from_mongo
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
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    customer_id: str
    sales_order_id: Optional[str] = None
    installation_plan_id: Optional[str] = None
    product_ref: Optional[str] = None
    opening_ref: Optional[str] = None
    subject: str
    description: Optional[str] = None
    priority: Literal["normal", "low", "high", "urgent", "red", "orange", "green"] = "orange"
    warranty_scope: Optional[str] = None
    first_reported_at: Optional[AwareDatetime] = None


@router.get("")
async def list_tickets(q: Optional[str] = None, customer_id: Optional[str] = None,
                       ticket_status: Optional[str] = None, priority: Optional[str] = None,
                       skip: int = 0, limit: int = Query(50, le=200),
                       user: dict = Depends(require_permission("service.view"))):
    result = await list_docs(collection="service_tickets", tenant_id=user["tenant_id"],
                            filters={"customer_id": customer_id, "ticket_status": ticket_status, "priority": priority},
                            search_fields=["number", "subject"], q=q,
                            sort=[("priority", -1), ("created_at", -1)], skip=skip, limit=limit)
    for item in result["items"]:
        item["service_clock"] = ticket_clock(item)
    return result


@router.get("/options")
async def ticket_options(user=Depends(require_permission("service.view"))):
    return {"transitions": {key: sorted(value) for key, value in TICKET_FLOW.items()},
            "labels": {"opened": "Aperta", "triaged": "Valutata", "waiting_customer": "Attesa cliente",
                       "waiting_material": "Attesa ricambio", "scheduled": "Pianificata", "in_progress": "In lavorazione",
                       "resolved": "Risolta", "closed": "Chiusa", "rejected": "Non accolta"}}


@router.get("/{tid}")
async def get_ticket(tid: str, user: dict = Depends(require_permission("service.view"))):
    ticket = await get_doc(collection="service_tickets", doc_id=tid, tenant_id=user["tenant_id"])
    return {**ticket, "service_clock": ticket_clock(ticket)}


@router.post("")
async def create_ticket(body: TicketCreate, request: Request,
                        user: dict = Depends(require_permission("service.create"))):
    db = get_db()
    customer = await db.customers.find_one({"_id": body.customer_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not customer:
        raise HTTPException(422, "Seleziona un cliente della stessa azienda")
    if body.sales_order_id:
        order = await db.sales_orders.find_one({"_id": body.sales_order_id, "customer_id": body.customer_id, "tenant_id": user["tenant_id"], "deleted_at": None})
        if not order:
            raise HTTPException(422, "Commessa non valida per questo cliente")
    now = datetime.now(timezone.utc)
    first = body.first_reported_at or now
    if first > now:
        raise HTTPException(422, "La prima segnalazione non può essere futura")
    clock = ticket_clock({"first_reported_at": first, "priority": body.priority})
    t = ServiceTicket(id=new_id(), **body.model_dump(exclude={"first_reported_at"}),
                      first_reported_at=first, service_due_at=clock["due_at"])
    return await create_doc(collection="service_tickets", model_instance=t, user=user,
                             entity_type="service_ticket", ip=get_client_ip(request),
                             set_number=True, number_key="service_ticket", number_prefix="ASS-")


class TicketPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version: int = Field(ge=0)
    priority: Optional[Literal["normal", "low", "high", "urgent", "red", "orange", "green"]] = None
    assigned_to: Optional[str] = None
    next_action: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = Field(default=None, max_length=10000)
    scheduled_at: Optional[AwareDatetime] = None
    warranty_scope: Optional[str] = None
    responsibility: Optional[str] = None
    photos: Optional[List[str]] = None
    parts_needed: Optional[List[dict]] = None


@router.patch("/{tid}")
async def patch_ticket(tid: str, body: TicketPatch, request: Request,
                       user: dict = Depends(require_permission("service.edit"))):
    db = get_db()
    existing = await db.service_tickets.find_one({"_id": tid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not existing:
        raise HTTPException(404, "Ticket non trovato")
    if body.version != existing.get("version", 0):
        raise HTTPException(409, "Ticket modificato. Ricarica prima di salvare.")
    if body.assigned_to:
        person = await db.users.find_one({"_id": body.assigned_to, "tenant_id": user["tenant_id"], "deleted_at": None, "is_active": {"$ne": False}})
        if not person:
            raise HTTPException(422, "Incaricato non valido")
    updates = body.model_dump(exclude_unset=True, exclude={"version"}, mode="json")
    if "priority" in updates and updates["priority"] is None:
        raise HTTPException(422, "Priorità obbligatoria")
    clock = ticket_clock(existing, new_priority=body.priority)
    updates.update(first_reported_at=clock["first_reported_at"], service_due_at=clock["due_at"],
                   updated_at=datetime.now(timezone.utc).isoformat(), updated_by=user["id"])
    query = {"_id": tid, "tenant_id": user["tenant_id"], "deleted_at": None, "version": body.version,
             "ticket_status": {"$nin": ["resolved", "closed", "rejected"]}}
    result = await db.service_tickets.find_one_and_update(query, {"$set": updates, "$inc": {"version": 1},
        "$push": {"service_history": {"actor_id": user["id"], "at": updates["updated_at"], "changes": updates.copy()}}}, return_document=True)
    if not result:
        raise HTTPException(409, "Ticket modificato o chiuso. Ricarica prima di salvare.")
    return {**from_mongo(result), "service_clock": ticket_clock(result)}


class TicketStatus(BaseModel):
    ticket_status: str
    resolution: Optional[str] = None
    expected_version: Optional[int] = None


@router.post("/{tid}/status")
async def change_status(tid: str, body: TicketStatus, request: Request,
                         user: dict = Depends(require_permission("service.edit"))):
    db = get_db()
    existing = await db.service_tickets.find_one({"_id": tid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not existing: raise HTTPException(status_code=404, detail="Ticket non trovato")
    enforce_status_transition(existing.get("ticket_status", "opened"), body.ticket_status, TICKET_FLOW)
    if body.ticket_status in ("resolved", "closed", "rejected") and len((body.resolution or "").strip()) < 5:
        raise HTTPException(422, "Registra un esito concreto prima di chiudere la richiesta")
    if body.expected_version is not None and body.expected_version != existing.get("version", 0):
        raise HTTPException(409, "Ticket modificato. Ricarica prima di cambiare stato.")
    updates = {"ticket_status": body.ticket_status}
    updates["resolution"] = body.resolution
    if body.ticket_status in ("resolved", "closed"):
        updates["resolved_at"] = datetime.now(timezone.utc).isoformat()
    now = datetime.now(timezone.utc).isoformat()
    updates.update(updated_at=now, updated_by=user["id"])
    result = await db.service_tickets.find_one_and_update(
        {"_id": tid, "tenant_id": user["tenant_id"], "deleted_at": None, "version": existing.get("version", 1)},
        {"$set": updates, "$inc": {"version": 1}, "$push": {"service_history": {
            "actor_id": user["id"], "at": now, "changes": updates.copy()}}}, return_document=True)
    if not result:
        raise HTTPException(409, "Ticket modificato. Ricarica prima di cambiare stato.")
    res = from_mongo(result)
    # SUPPORT_UPDATED: solo cambi di stato customer-facing (mai per PATCH/note interne)
    from app.services.customer_email_events import notify_customer_event
    await notify_customer_event(db, tenant_id=user["tenant_id"], customer_id=existing.get("customer_id"), event_type="SUPPORT_UPDATED",
                                entity_type="service_ticket", entity_id=tid, title="Aggiornamento sulla tua richiesta di assistenza",
                                body=f"La tua richiesta \"{existing.get('title') or existing.get('subject') or tid}\" è passata allo stato: {body.ticket_status}."
                                     + (f" Esito: {body.resolution}" if body.resolution and body.ticket_status in ("resolved", "closed") else ""),
                                cta_label="Visualizza richiesta", dedupe_suffix=body.ticket_status)
    return res


@router.get("/dashboard/kpi")
async def ticket_kpi(user: dict = Depends(require_permission("service.view"))):
    db = get_db()
    tenant = user["tenant_id"]
    counts = {}
    for st in TICKET_FLOW.keys():
        counts[st] = await db.service_tickets.count_documents({"tenant_id": tenant, "ticket_status": st, "deleted_at": None})
    open_count = sum(counts.get(s, 0) for s in ("opened", "triaged", "waiting_customer", "waiting_material", "scheduled", "in_progress"))
    return {"counts_by_status": counts, "open_count": open_count, "closed_count": counts.get("closed", 0)}
