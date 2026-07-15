"""Appointments (calendar)."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from app.db import get_db
from app.deps import require_permission
from app.models_crm import Appointment, AppointmentCreate, AppointmentUpdate
from app.models import new_id
from app.mongo_utils import to_mongo, from_mongo
from app.services.timeline import record_activity

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("")
async def list_appointments(
    from_date: Optional[str] = None, to_date: Optional[str] = None,
    lead_id: Optional[str] = None, customer_id: Optional[str] = None,
    mine: bool = False,
    user: dict = Depends(require_permission("crm.appointments.view")),
):
    db = get_db()
    query: dict = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if from_date or to_date:
        rng: dict = {}
        if from_date: rng["$gte"] = from_date
        if to_date: rng["$lte"] = to_date
        query["start_at"] = rng
    if lead_id: query["lead_id"] = lead_id
    if customer_id: query["customer_id"] = customer_id
    if mine:
        query["attendees"] = user["id"]
    docs = await db.appointments.find(query).sort("start_at", 1).limit(500).to_list(500)
    return {"items": [from_mongo(d) for d in docs]}


@router.post("")
async def create_appointment(body: AppointmentCreate, request: Request,
                             user: dict = Depends(require_permission("crm.appointments.manage"))):
    db = get_db()
    if body.end_at < body.start_at:
        raise HTTPException(status_code=400, detail="end_at deve essere >= start_at")
    a = Appointment(
        id=new_id(), tenant_id=user["tenant_id"],
        title=body.title, description=body.description,
        start_at=body.start_at, end_at=body.end_at,
        location=body.location, attendees=body.attendees or [user["id"]],
        lead_id=body.lead_id, customer_id=body.customer_id, contact_id=body.contact_id,
        appointment_type=body.appointment_type, reminder_minutes=body.reminder_minutes,
        created_by=user["id"], updated_by=user["id"],
    )
    await db.appointments.insert_one(to_mongo(a.model_dump(by_alias=True)))
    await record_activity(
        tenant_id=user["tenant_id"], type="appointment_scheduled",
        subject=f"Appuntamento: {a.title}", body=a.description,
        occurred_at=a.start_at,
        lead_id=a.lead_id, customer_id=a.customer_id, contact_id=a.contact_id,
        user_id=user["id"], user_email=user["email"],
        meta={"appointment_id": a.id, "location": a.location},
    )
    return from_mongo(await db.appointments.find_one({"_id": a.id}))


@router.patch("/{aid}")
async def update_appointment(aid: str, body: AppointmentUpdate,
                             user: dict = Depends(require_permission("crm.appointments.manage"))):
    db = get_db()
    doc = await db.appointments.find_one({"_id": aid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Appuntamento non trovato")
    payload = body.model_dump(exclude_unset=True)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload["updated_by"] = user["id"]
    old_status = doc.get("appointment_status")
    new_status = payload.get("appointment_status")
    await db.appointments.update_one({"_id": aid}, {"$set": payload})
    if new_status == "done" and old_status != "done":
        await record_activity(
            tenant_id=user["tenant_id"], type="appointment_done",
            subject=f"Appuntamento svolto: {doc.get('title')}",
            lead_id=doc.get("lead_id"), customer_id=doc.get("customer_id"), contact_id=doc.get("contact_id"),
            user_id=user["id"], user_email=user["email"], meta={"appointment_id": aid},
        )
    return from_mongo(await db.appointments.find_one({"_id": aid}))


@router.delete("/{aid}")
async def delete_appointment(aid: str, user: dict = Depends(require_permission("crm.appointments.manage"))):
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.appointments.update_one({"_id": aid, "tenant_id": user["tenant_id"]},
                                     {"$set": {"deleted_at": now, "appointment_status": "cancelled"}})
    return {"ok": True}
