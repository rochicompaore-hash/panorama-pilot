"""M10..M12 — Finished goods, shipments, installation planning, installation reports."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models import new_id
from app.models_ops import (
    FinishedGoodPack, Shipment, InstallationCrew, InstallationPlan, InstallationReport,
)
from app.services.ops_common import (create_doc, get_doc, list_docs, update_doc, soft_delete_doc,
                                       enforce_status_transition)
from app.services.timeline import record_activity

# -------- Finished goods packs --------
fg_router = APIRouter(prefix="/finished-good-packs", tags=["finished-goods"])


class FGCreate(BaseModel):
    sales_order_id: str
    production_order_id: Optional[str] = None
    items: List[dict] = []
    location_id: Optional[str] = None


@fg_router.post("")
async def create_pack(body: FGCreate, request: Request,
                       user: dict = Depends(require_permission("logistics.edit"))):
    p = FinishedGoodPack(id=new_id(), **body.model_dump())
    return await create_doc(collection="finished_good_packs", model_instance=p, user=user,
                             entity_type="finished_good_pack", ip=get_client_ip(request),
                             set_number=True, number_key="finished_pack", number_prefix="PF-")


@fg_router.get("")
async def list_packs(sales_order_id: Optional[str] = None,
                      user: dict = Depends(require_permission("logistics.view"))):
    return await list_docs(collection="finished_good_packs", tenant_id=user["tenant_id"],
                            filters={"sales_order_id": sales_order_id},
                            sort=[("created_at", -1)], limit=200)


# -------- Shipments --------
sh_router = APIRouter(prefix="/shipments", tags=["shipments"])

SH_FLOW = {
    "draft": {"loaded", "cancelled"},
    "loaded": {"in_transit", "cancelled"},
    "in_transit": {"delivered", "failed"},
    "delivered": set(),
    "failed": {"in_transit", "cancelled"},
    "cancelled": set(),
}


class ShipmentCreate(BaseModel):
    sales_order_id: Optional[str] = None
    packs: List[str] = []
    driver_name: Optional[str] = None
    vehicle_plate: Optional[str] = None
    departure_at: Optional[datetime] = None


@sh_router.post("")
async def create_ship(body: ShipmentCreate, request: Request,
                       user: dict = Depends(require_permission("logistics.edit"))):
    s = Shipment(id=new_id(), **body.model_dump())
    return await create_doc(collection="shipments", model_instance=s, user=user,
                             entity_type="shipment", ip=get_client_ip(request),
                             set_number=True, number_key="shipment", number_prefix="DDT-")


@sh_router.get("")
async def list_shipments(shipment_status: Optional[str] = None, skip: int = 0, limit: int = 50,
                          user: dict = Depends(require_permission("logistics.view"))):
    return await list_docs(collection="shipments", tenant_id=user["tenant_id"],
                            filters={"shipment_status": shipment_status},
                            sort=[("number_int", -1)], skip=skip, limit=limit)


class ShipStatus(BaseModel):
    shipment_status: str
    signed_by: Optional[str] = None


@sh_router.post("/{sid}/status")
async def ship_status(sid: str, body: ShipStatus, request: Request,
                       user: dict = Depends(require_permission("logistics.edit"))):
    db = get_db()
    existing = await db.shipments.find_one({"_id": sid, "tenant_id": user["tenant_id"]})
    if not existing: raise HTTPException(status_code=404, detail="Spedizione non trovata")
    enforce_status_transition(existing.get("shipment_status", "draft"), body.shipment_status, SH_FLOW)
    updates = {"shipment_status": body.shipment_status}
    if body.shipment_status == "delivered":
        updates["arrival_at"] = datetime.now(timezone.utc).isoformat()
        if body.signed_by: updates["signed_by"] = body.signed_by
    return await update_doc(collection="shipments", doc_id=sid, updates=updates, user=user,
                             entity_type="shipment", ip=get_client_ip(request))


# -------- Installation crews --------
crew_router = APIRouter(prefix="/installation-crews", tags=["installation-crews"])


class CrewCreate(BaseModel):
    name: str
    members: List[str] = []
    skills: List[str] = []
    equipment_notes: Optional[str] = None


@crew_router.get("")
async def list_crews(user: dict = Depends(require_permission("installation.view"))):
    return await list_docs(collection="installation_crews", tenant_id=user["tenant_id"],
                            filters={"is_active": True}, sort=[("name", 1)], limit=100)


@crew_router.post("")
async def create_crew(body: CrewCreate, request: Request,
                       user: dict = Depends(require_permission("installation.edit"))):
    c = InstallationCrew(id=new_id(), **body.model_dump())
    return await create_doc(collection="installation_crews", model_instance=c, user=user,
                             entity_type="installation_crew", ip=get_client_ip(request))


@crew_router.patch("/{cid}")
async def patch_crew(cid: str, body: dict, request: Request,
                      user: dict = Depends(require_permission("installation.edit"))):
    return await update_doc(collection="installation_crews", doc_id=cid, updates=body, user=user,
                             entity_type="installation_crew", ip=get_client_ip(request))


# -------- Installation plans --------
plan_router = APIRouter(prefix="/installation-plans", tags=["installation-plans"])

PLAN_FLOW = {
    "draft": {"proposed", "cancelled"},
    "proposed": {"customer_confirmed", "postponed", "cancelled"},
    "customer_confirmed": {"scheduled", "postponed", "cancelled"},
    "scheduled": {"in_progress", "postponed", "blocked_customer", "blocked_materials", "blocked_weather", "cancelled"},
    "in_progress": {"completed", "blocked_customer", "blocked_materials", "blocked_weather"},
    "completed": set(),
    "postponed": {"proposed", "scheduled", "cancelled"},
    "blocked_customer": {"scheduled", "cancelled"},
    "blocked_materials": {"scheduled", "cancelled"},
    "blocked_weather": {"scheduled", "cancelled"},
    "cancelled": set(),
}


class PlanCreate(BaseModel):
    sales_order_id: str
    customer_id: Optional[str] = None
    crew_id: Optional[str] = None
    scheduled_date: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    estimated_duration_h: Optional[float] = None
    equipment_needed: List[str] = []
    site_address: Optional[dict] = None
    notes: Optional[str] = None


@plan_router.get("")
async def list_plans(plan_status: Optional[str] = None, crew_id: Optional[str] = None,
                      skip: int = 0, limit: int = 50,
                      user: dict = Depends(require_permission("installation.view"))):
    return await list_docs(collection="installation_plans", tenant_id=user["tenant_id"],
                            filters={"plan_status": plan_status, "crew_id": crew_id},
                            sort=[("scheduled_date", 1)], skip=skip, limit=limit)


@plan_router.post("")
async def create_plan(body: PlanCreate, request: Request,
                       user: dict = Depends(require_permission("installation.edit"))):
    p = InstallationPlan(id=new_id(), **body.model_dump())
    return await create_doc(collection="installation_plans", model_instance=p, user=user,
                             entity_type="installation_plan", ip=get_client_ip(request),
                             set_number=True, number_key="installation_plan", number_prefix="POS-")


@plan_router.patch("/{pid}")
async def patch_plan(pid: str, body: dict, request: Request,
                      user: dict = Depends(require_permission("installation.edit"))):
    return await update_doc(collection="installation_plans", doc_id=pid, updates=body, user=user,
                             entity_type="installation_plan", ip=get_client_ip(request))


class PlanStatus(BaseModel):
    plan_status: str
    reason: Optional[str] = None


@plan_router.post("/{pid}/status")
async def plan_status_change(pid: str, body: PlanStatus, request: Request,
                              user: dict = Depends(require_permission("installation.edit"))):
    db = get_db()
    existing = await db.installation_plans.find_one({"_id": pid, "tenant_id": user["tenant_id"]})
    if not existing: raise HTTPException(status_code=404, detail="Pianificazione non trovata")
    enforce_status_transition(existing.get("plan_status", "draft"), body.plan_status, PLAN_FLOW)
    updates = {"plan_status": body.plan_status}
    if body.plan_status == "customer_confirmed":
        updates["customer_confirmed_at"] = datetime.now(timezone.utc).isoformat()
    return await update_doc(collection="installation_plans", doc_id=pid, updates=updates, user=user,
                             entity_type="installation_plan", ip=get_client_ip(request))


# -------- Installation reports --------
rep_router = APIRouter(prefix="/installation-reports", tags=["installation-reports"])


class ReportCreate(BaseModel):
    installation_plan_id: str
    check_in_at: Optional[datetime] = None
    lead_installer_id: Optional[str] = None


@rep_router.post("")
async def create_report(body: ReportCreate, request: Request,
                         user: dict = Depends(require_permission("installation.edit"))):
    db = get_db()
    plan = await db.installation_plans.find_one({"_id": body.installation_plan_id, "tenant_id": user["tenant_id"]})
    if not plan: raise HTTPException(status_code=400, detail="Pianificazione non trovata")
    r = InstallationReport(id=new_id(),
        installation_plan_id=body.installation_plan_id,
        sales_order_id=plan.get("sales_order_id"), customer_id=plan.get("customer_id"),
        check_in_at=body.check_in_at, lead_installer_id=body.lead_installer_id)
    return await create_doc(collection="installation_reports", model_instance=r, user=user,
                             entity_type="installation_report", ip=get_client_ip(request))


@rep_router.patch("/{rid}")
async def patch_report(rid: str, body: dict, request: Request,
                        user: dict = Depends(require_permission("installation.edit"))):
    return await update_doc(collection="installation_reports", doc_id=rid, updates=body, user=user,
                             entity_type="installation_report", ip=get_client_ip(request))


@rep_router.get("")
async def list_reports(installation_plan_id: Optional[str] = None,
                        user: dict = Depends(require_permission("installation.view"))):
    return await list_docs(collection="installation_reports", tenant_id=user["tenant_id"],
                            filters={"installation_plan_id": installation_plan_id},
                            sort=[("created_at", -1)], limit=100)


class ReportSubmit(BaseModel):
    outcome: str  # completed | partial | postponed | issue | material_missing | damage | service_needed
    customer_signer_name: Optional[str] = None
    customer_signature_hash: Optional[str] = None
    crew_signer_name: Optional[str] = None
    crew_signature_hash: Optional[str] = None


@rep_router.post("/{rid}/submit")
async def submit_report(rid: str, body: ReportSubmit, request: Request,
                         user: dict = Depends(require_permission("installation.edit"))):
    updates = {
        "outcome": body.outcome,
        "report_status": "submitted",
        "check_out_at": datetime.now(timezone.utc).isoformat(),
        "customer_signer_name": body.customer_signer_name,
        "customer_signature_hash": body.customer_signature_hash,
        "crew_signer_name": body.crew_signer_name,
        "crew_signature_hash": body.crew_signature_hash,
    }
    doc = await update_doc(collection="installation_reports", doc_id=rid, updates=updates, user=user,
                             entity_type="installation_report", ip=get_client_ip(request))
    # If completed, advance plan
    if body.outcome == "completed":
        db = get_db()
        await db.installation_plans.update_one(
            {"_id": doc["installation_plan_id"], "tenant_id": user["tenant_id"]},
            {"$set": {"plan_status": "completed", "updated_at": datetime.now(timezone.utc).isoformat()}})
        # Advance sales order to installed
        if doc.get("sales_order_id"):
            await db.sales_orders.update_one(
                {"_id": doc["sales_order_id"], "tenant_id": user["tenant_id"], "order_status": {"$in": ["ready_for_installation", "in_production", "completed"]}},
                {"$set": {"order_status": "installed", "updated_at": datetime.now(timezone.utc).isoformat()}})
        await record_activity(
            tenant_id=user["tenant_id"], type="installation_completed",
            subject=f"Posa completata (piano {doc.get('installation_plan_id')})",
            customer_id=doc.get("customer_id"),
            user_id=user["id"], user_email=user["email"])
    return doc
