"""M4 — Rilievo tecnico (surveys)."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models import new_id
from app.models_ops import Survey, SurveyOpening
from app.mongo_utils import to_mongo, from_mongo
from app.services.audit import record_audit
from app.services.timeline import record_activity
from app.services.ops_common import (
    create_doc, get_doc, list_docs, update_doc, soft_delete_doc,
    enforce_status_transition, next_number,
)

router = APIRouter(prefix="/surveys", tags=["surveys"])

SURVEY_FLOW = {
    "draft": {"scheduled", "cancelled"},
    "scheduled": {"in_progress", "cancelled"},
    "in_progress": {"completed", "cancelled"},
    "completed": {"approved", "rejected", "in_progress"},
    "approved": {"converted"},  # → sales_order
    "rejected": {"in_progress"},  # allow rework
    "converted": set(),
    "cancelled": set(),
}


class SurveyCreate(BaseModel):
    customer_id: str
    quote_id: Optional[str] = None
    contract_id: Optional[str] = None
    lead_id: Optional[str] = None
    site_address: Optional[dict] = None
    technician_id: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    notes: Optional[str] = None


@router.get("")
async def list_surveys(q: Optional[str] = None, customer_id: Optional[str] = None,
                       survey_status: Optional[str] = None, technician_id: Optional[str] = None,
                       skip: int = 0, limit: int = Query(50, le=200),
                       user: dict = Depends(require_permission("surveys.view"))):
    return await list_docs(
        collection="surveys", tenant_id=user["tenant_id"],
        filters={"customer_id": customer_id, "survey_status": survey_status, "technician_id": technician_id},
        search_fields=["number"], q=q,
        sort=[("scheduled_at", -1), ("created_at", -1)], skip=skip, limit=limit,
    )


@router.get("/{sid}")
async def get_survey(sid: str, user: dict = Depends(require_permission("surveys.view"))):
    return await get_doc(collection="surveys", doc_id=sid, tenant_id=user["tenant_id"])


@router.post("")
async def create_survey(body: SurveyCreate, request: Request,
                         user: dict = Depends(require_permission("surveys.create"))):
    # If quote_id given, prefill openings from quote for comparison
    db = get_db()
    openings: List[SurveyOpening] = []
    if body.quote_id:
        q = await db.quotes.find_one({"_id": body.quote_id, "tenant_id": user["tenant_id"]})
        if q:
            for op in q.get("openings", []):
                for ln in (op.get("lines") or []):
                    dims = ln.get("dimensions") or {}
                    openings.append(SurveyOpening(
                        ref=op.get("ref") or "V1",
                        location=op.get("location"),
                        quote_width_mm=dims.get("width_mm"),
                        quote_height_mm=dims.get("height_mm"),
                    ))
                    break  # one line preview per opening
    s = Survey(
        id=new_id(),
        customer_id=body.customer_id,
        quote_id=body.quote_id, contract_id=body.contract_id, lead_id=body.lead_id,
        site_address=body.site_address, technician_id=body.technician_id,
        scheduled_at=body.scheduled_at, notes=body.notes,
        survey_status="scheduled" if body.scheduled_at else "draft",
        openings=openings,
    )
    doc = await create_doc(collection="surveys", model_instance=s, user=user, entity_type="survey",
                            ip=get_client_ip(request), set_number=True,
                            number_key="survey", number_prefix="RIL-")
    await record_activity(tenant_id=user["tenant_id"], type="survey_created",
                          subject=f"Rilievo {doc.get('number')} creato",
                          customer_id=body.customer_id, quote_id=body.quote_id,
                          user_id=user["id"], user_email=user["email"])
    return doc


class SurveyPatch(BaseModel):
    technician_id: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    openings: Optional[List[SurveyOpening]] = None
    notes: Optional[str] = None
    variance_reason: Optional[str] = None
    variance_total: Optional[float] = None
    site_address: Optional[dict] = None


@router.patch("/{sid}")
async def patch_survey(sid: str, body: SurveyPatch, request: Request,
                       user: dict = Depends(require_permission("surveys.edit"))):
    db = get_db()
    existing = await db.surveys.find_one({"_id": sid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not existing: raise HTTPException(status_code=404, detail="Rilievo non trovato")
    if existing.get("is_locked"):
        raise HTTPException(status_code=400, detail="Rilievo bloccato: le misure sono state approvate")
    updates = body.model_dump(exclude_none=True)
    if body.openings is not None:
        updates["openings"] = [op.model_dump() for op in body.openings]
    return await update_doc(collection="surveys", doc_id=sid, updates=updates, user=user,
                             entity_type="survey", ip=get_client_ip(request))


class StatusChange(BaseModel):
    survey_status: str
    reason: Optional[str] = None


@router.post("/{sid}/status")
async def change_status(sid: str, body: StatusChange, request: Request,
                         user: dict = Depends(require_permission("surveys.edit"))):
    db = get_db()
    existing = await db.surveys.find_one({"_id": sid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not existing: raise HTTPException(status_code=404, detail="Rilievo non trovato")
    enforce_status_transition(existing.get("survey_status", "draft"), body.survey_status, SURVEY_FLOW)
    updates = {"survey_status": body.survey_status}
    if body.survey_status == "approved":
        updates["approved_at"] = datetime.now(timezone.utc).isoformat()
        updates["approved_by"] = user["id"]
        updates["is_locked"] = True
    return await update_doc(collection="surveys", doc_id=sid, updates=updates, user=user,
                             entity_type="survey", ip=get_client_ip(request))


@router.post("/{sid}/customer-approval")
async def customer_approval(sid: str, request: Request,
                             signer_name: str, signature_hash: Optional[str] = None,
                             user: dict = Depends(require_permission("surveys.edit"))):
    updates = {
        "customer_approved_at": datetime.now(timezone.utc).isoformat(),
        "customer_signer_name": signer_name,
        "customer_signature_hash": signature_hash,
    }
    return await update_doc(collection="surveys", doc_id=sid, updates=updates, user=user,
                             entity_type="survey", ip=get_client_ip(request))


@router.delete("/{sid}")
async def delete_survey(sid: str, request: Request,
                         user: dict = Depends(require_permission("surveys.delete"))):
    return await soft_delete_doc(collection="surveys", doc_id=sid, user=user, entity_type="survey",
                                   ip=get_client_ip(request), block_if_field="is_locked")


@router.get("/{sid}/compare-quote")
async def compare_with_quote(sid: str, user: dict = Depends(require_permission("surveys.view"))):
    """Return an explicit diff between measured openings and their quote-time snapshot."""
    survey = await get_doc(collection="surveys", doc_id=sid, tenant_id=user["tenant_id"])
    diff = []
    for op in survey.get("openings", []):
        dw = (op.get("measured_width_mm") or 0) - (op.get("quote_width_mm") or 0)
        dh = (op.get("measured_height_mm") or 0) - (op.get("quote_height_mm") or 0)
        diff.append({
            "ref": op.get("ref"),
            "location": op.get("location"),
            "quote": {"w": op.get("quote_width_mm"), "h": op.get("quote_height_mm")},
            "measured": {"w": op.get("measured_width_mm"), "h": op.get("measured_height_mm")},
            "delta_mm": {"w": dw, "h": dh},
            "has_variance": abs(dw) > 5 or abs(dh) > 5,
        })
    return {"survey_id": sid, "openings": diff}
