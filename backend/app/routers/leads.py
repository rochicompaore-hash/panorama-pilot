"""Leads router - core CRM entity with timeline + intelligence."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models_crm import Lead, LeadCreate, LeadUpdate, LeadConvertRequest, Customer, LeadAddress
from app.models import new_id
from app.mongo_utils import to_mongo, from_mongo
from app.services.audit import record_audit
from app.services.timeline import record_activity, compute_lead_intelligence
from app.routers.pipelines import seed_default_pipeline

router = APIRouter(prefix="/leads", tags=["leads"])


async def _get_stages_map(tenant_id: str, pipeline_id: Optional[str] = None) -> dict:
    db = get_db()
    q = {"tenant_id": tenant_id, "deleted_at": None}
    if pipeline_id:
        q["_id"] = pipeline_id
    else:
        q["is_default"] = True
    pipe = await db.pipelines.find_one(q)
    if not pipe:
        return {}
    return {s["id"]: s for s in (pipe.get("stages") or [])}


@router.get("")
async def list_leads(
    q: Optional[str] = None,
    assigned_to: Optional[str] = None,
    stage_id: Optional[str] = None,
    lifecycle: Optional[str] = None,
    limit: int = Query(100, le=500),
    skip: int = 0,
    user: dict = Depends(require_permission("crm.leads.view")),
):
    db = get_db()
    query: dict = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if lifecycle:
        query["lifecycle"] = lifecycle
    if assigned_to:
        query["assigned_to"] = assigned_to
    if stage_id:
        query["stage_id"] = stage_id
    if q:
        query["$or"] = [
            {"first_name": {"$regex": q, "$options": "i"}},
            {"last_name": {"$regex": q, "$options": "i"}},
            {"company_name": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
            {"phone": {"$regex": q, "$options": "i"}},
            {"tags": {"$regex": q, "$options": "i"}},
        ]
    total = await db.leads.count_documents(query)
    docs = await db.leads.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    stages_map = await _get_stages_map(user["tenant_id"])
    items = []
    for d in docs:
        d = from_mongo(d)
        d["intelligence"] = compute_lead_intelligence(d, stages_map)
        items.append(d)
    return {"total": total, "items": items}


@router.get("/kanban")
async def kanban(
    pipeline_id: Optional[str] = None,
    assigned_to: Optional[str] = None,
    user: dict = Depends(require_permission("crm.leads.view")),
):
    db = get_db()
    if not pipeline_id:
        pid = await seed_default_pipeline(user["tenant_id"])
        pipeline_id = pid
    pipe = await db.pipelines.find_one({"_id": pipeline_id, "tenant_id": user["tenant_id"]})
    if not pipe:
        raise HTTPException(status_code=404, detail="Pipeline non trovata")
    stages_map = {s["id"]: s for s in (pipe.get("stages") or [])}
    q: dict = {"tenant_id": user["tenant_id"], "deleted_at": None, "pipeline_id": pipeline_id, "lifecycle": "lead"}
    if assigned_to:
        q["assigned_to"] = assigned_to
    docs = await db.leads.find(q).sort("updated_at", -1).limit(500).to_list(500)
    columns: dict = {s["id"]: {"stage": s, "leads": []} for s in (pipe.get("stages") or [])}
    for d in docs:
        d = from_mongo(d)
        d["intelligence"] = compute_lead_intelligence(d, stages_map)
        sid = d.get("stage_id")
        if sid not in columns:
            # unassigned → drop in first stage
            first = pipe["stages"][0]["id"] if pipe.get("stages") else None
            if first:
                columns[first]["leads"].append(d)
        else:
            columns[sid]["leads"].append(d)
    return {"pipeline": from_mongo(pipe), "columns": list(columns.values())}


@router.get("/{lid}")
async def get_lead(lid: str, user: dict = Depends(require_permission("crm.leads.view"))):
    db = get_db()
    doc = await db.leads.find_one({"_id": lid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Lead non trovato")
    d = from_mongo(doc)
    stages_map = await _get_stages_map(user["tenant_id"], d.get("pipeline_id"))
    d["intelligence"] = compute_lead_intelligence(d, stages_map)
    return d


@router.post("")
async def create_lead(
    body: LeadCreate, request: Request,
    user: dict = Depends(require_permission("crm.leads.create")),
):
    db = get_db()
    pipeline_id = body.pipeline_id
    stage_id = body.stage_id
    if not pipeline_id:
        pipeline_id = await seed_default_pipeline(user["tenant_id"])
    pipe = await db.pipelines.find_one({"_id": pipeline_id, "tenant_id": user["tenant_id"]})
    if not pipe:
        raise HTTPException(status_code=400, detail="Pipeline non valida")
    if not stage_id and pipe.get("stages"):
        stage_id = pipe["stages"][0]["id"]
    stage = next((s for s in pipe.get("stages", []) if s["id"] == stage_id), None)
    probability = stage["probability_default"] if stage else 20

    lead = Lead(
        id=new_id(), tenant_id=user["tenant_id"],
        first_name=body.first_name, last_name=body.last_name,
        company_name=body.company_name, email=body.email,
        phone=body.phone, whatsapp=body.whatsapp,
        address=body.address or LeadAddress(),
        source=body.source, source_detail=body.source_detail,
        pipeline_id=pipeline_id, stage_id=stage_id, probability=probability,
        estimated_value=body.estimated_value, assigned_to=body.assigned_to or user["id"],
        tags=body.tags, notes=body.notes, interested_products=body.interested_products,
        created_by=user["id"], updated_by=user["id"],
    )
    await db.leads.insert_one(to_mongo(lead.model_dump(by_alias=True)))
    display = f"{lead.first_name or ''} {lead.last_name or ''}".strip() or lead.company_name or lead.email or "Nuovo lead"
    await record_activity(
        tenant_id=user["tenant_id"], type="lead_created",
        subject=f"Lead creato: {display}",
        lead_id=lead.id, user_id=user["id"], user_email=user["email"],
        meta={"source": body.source},
    )
    await record_audit(action="crm.leads.create", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="lead", entity_id=lead.id,
                       after={"name": display, "estimated_value": body.estimated_value})
    return from_mongo(await db.leads.find_one({"_id": lead.id}))


@router.patch("/{lid}")
async def update_lead(
    lid: str, body: LeadUpdate, request: Request,
    user: dict = Depends(require_permission("crm.leads.edit")),
):
    db = get_db()
    doc = await db.leads.find_one({"_id": lid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Lead non trovato")
    payload = body.model_dump(exclude_unset=True)
    if "address" in payload and payload["address"] is not None:
        payload["address"] = payload["address"] if isinstance(payload["address"], dict) else payload["address"].model_dump()
    old_stage = doc.get("stage_id")
    new_stage = payload.get("stage_id")
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload["updated_by"] = user["id"]

    # Handle stage change → record activity + update won/lost
    stages_map = await _get_stages_map(user["tenant_id"], doc.get("pipeline_id"))
    if new_stage and new_stage != old_stage and new_stage in stages_map:
        s = stages_map[new_stage]
        if s.get("is_won"):
            payload["won_at"] = datetime.now(timezone.utc).isoformat()
        if s.get("is_lost"):
            payload["lost_at"] = datetime.now(timezone.utc).isoformat()
        if "probability" not in payload:
            payload["probability"] = s.get("probability_default", 20)

    await db.leads.update_one({"_id": lid}, {"$set": payload})

    if new_stage and new_stage != old_stage:
        old_name = (stages_map.get(old_stage) or {}).get("name", "—")
        new_name = (stages_map.get(new_stage) or {}).get("name", "—")
        await record_activity(
            tenant_id=user["tenant_id"], type="stage_changed",
            subject=f"Stato: {old_name} → {new_name}",
            lead_id=lid, user_id=user["id"], user_email=user["email"],
            meta={"from": old_stage, "to": new_stage},
        )

    await record_audit(action="crm.leads.update", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="lead", entity_id=lid, after=payload)
    d = from_mongo(await db.leads.find_one({"_id": lid}))
    d["intelligence"] = compute_lead_intelligence(d, stages_map)
    return d


@router.delete("/{lid}")
async def delete_lead(
    lid: str, request: Request,
    user: dict = Depends(require_permission("crm.leads.delete")),
):
    db = get_db()
    doc = await db.leads.find_one({"_id": lid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Lead non trovato")
    now = datetime.now(timezone.utc).isoformat()
    await db.leads.update_one({"_id": lid}, {"$set": {"deleted_at": now, "updated_at": now, "updated_by": user["id"]}})
    await record_audit(action="crm.leads.delete", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="lead", entity_id=lid)
    return {"ok": True}


@router.post("/{lid}/convert")
async def convert_lead(
    lid: str, body: LeadConvertRequest, request: Request,
    user: dict = Depends(require_permission("crm.leads.convert")),
):
    db = get_db()
    doc = await db.leads.find_one({"_id": lid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Lead non trovato")
    if doc.get("customer_id"):
        raise HTTPException(status_code=400, detail="Lead già convertito")
    customer = Customer(
        id=new_id(), tenant_id=user["tenant_id"],
        first_name=doc.get("first_name"), last_name=doc.get("last_name"),
        company_name=doc.get("company_name"), email=doc.get("email"),
        phone=doc.get("phone"), whatsapp=doc.get("whatsapp"),
        address=LeadAddress(**(doc.get("address") or {})),
        customer_type=body.customer_type,
        assigned_to=doc.get("assigned_to"),
        origin_lead_id=lid,
        tags=doc.get("tags", []),
        created_by=user["id"], updated_by=user["id"],
    )
    await db.customers.insert_one(to_mongo(customer.model_dump(by_alias=True)))
    now = datetime.now(timezone.utc).isoformat()
    await db.leads.update_one({"_id": lid}, {"$set": {
        "customer_id": customer.id,
        "lifecycle": "customer",
        "won_at": now,
        "updated_at": now,
        "updated_by": user["id"],
    }})
    await record_activity(
        tenant_id=user["tenant_id"], type="conversion",
        subject="Lead convertito in cliente",
        lead_id=lid, customer_id=customer.id,
        user_id=user["id"], user_email=user["email"],
    )
    await record_audit(action="crm.leads.convert", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="lead", entity_id=lid, after={"customer_id": customer.id})
    return from_mongo(await db.customers.find_one({"_id": customer.id}))
