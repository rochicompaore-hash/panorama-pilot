"""Workflow router — Abaco tecnico, Ordine esecutivo, Production release check,
Customer tracking timeline, Variance."""
from __future__ import annotations
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from app.db import get_db
from app.deps import get_current_user, require_permission, require_any_permission, get_client_ip
from app.services.ops_common import create_doc, get_doc, list_docs, update_doc, soft_delete_doc, next_number
from app.services.workflow_engine import (
    production_release_check, ensure_survey_from_contract,
    ensure_technical_schedule_from_survey, create_executive_order_from_signed_ts,
    log_timeline_event, resolve_customer_status, canonical_hash,
    DEFAULT_CUSTOMER_STATUS_MAP,
)
from app.services.audit import record_audit
from app.mongo_utils import to_mongo, from_mongo
from app.models import new_id, utcnow
from app.models_workflow import (
    TechnicalSchedule, TechnicalScheduleCreate, TechnicalScheduleUpdate,
    TechnicalScheduleStatusChange, TechnicalScheduleSendRequest,
    TechnicalScheduleSignPayload, TechnicalScheduleItem,
    ExecutiveOrder, ProductionReleaseCheckResult, ProductionReleaseCheckRequest,
    ProductionReleaseOverrideRequest, CustomerStatusMapping,
    Variance, VarianceLine,
)


router = APIRouter(prefix="/workflow", tags=["Workflow E2E"])


# ---------------------------------------------------------------------
# TECHNICAL SCHEDULE (ABACO)
# ---------------------------------------------------------------------
@router.get("/technical-schedules")
async def list_ts(
    contract_id: Optional[str] = None, survey_id: Optional[str] = None,
    ts_status: Optional[str] = None, is_current: Optional[bool] = None,
    skip: int = 0, limit: int = 50,
    user: dict = Depends(require_permission("surveys.view")),
):
    filters = {}
    if contract_id: filters["contract_id"] = contract_id
    if survey_id: filters["survey_id"] = survey_id
    if ts_status: filters["ts_status"] = ts_status
    if is_current is not None: filters["is_current"] = is_current
    return await list_docs(
        collection="technical_schedules", tenant_id=user["tenant_id"], filters=filters,
        sort=[("number_int", -1), ("created_at", -1)], skip=skip, limit=limit,
    )


@router.get("/technical-schedules/{ts_id}")
async def get_ts(ts_id: str, user: dict = Depends(require_permission("surveys.view"))):
    return await get_doc(collection="technical_schedules", doc_id=ts_id, tenant_id=user["tenant_id"])


@router.post("/technical-schedules/from-survey/{survey_id}")
async def create_ts_from_survey(
    survey_id: str, request: Request,
    user: dict = Depends(require_permission("surveys.edit")),
):
    """Crea l'Abaco (draft) copiando dalla Survey. Idempotente."""
    ts_id = await ensure_technical_schedule_from_survey(
        tenant_id=user["tenant_id"], survey_id=survey_id, actor_id=user["id"],
    )
    if not ts_id:
        raise HTTPException(status_code=404, detail="Survey non trovata")
    await record_audit(
        action="ts.create_from_survey", tenant_id=user["tenant_id"], user_id=user["id"],
        user_email=user["email"], ip=get_client_ip(request),
        entity_type="technical_schedule", entity_id=ts_id, meta={"survey_id": survey_id},
    )
    return await get_doc(collection="technical_schedules", doc_id=ts_id, tenant_id=user["tenant_id"])


@router.patch("/technical-schedules/{ts_id}")
async def update_ts(
    ts_id: str, payload: TechnicalScheduleUpdate, request: Request,
    user: dict = Depends(require_permission("surveys.edit")),
):
    db = get_db()
    ts = await db.technical_schedules.find_one({"_id": ts_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not ts:
        raise HTTPException(status_code=404, detail="Abaco non trovato")
    if ts.get("ts_status") in ("signed", "released_to_production", "superseded"):
        raise HTTPException(status_code=409, detail="Abaco non modificabile in questo stato. Crea una nuova versione.")
    updates = payload.model_dump(exclude_unset=True)
    if "items" in updates and updates["items"] is not None:
        updates["items"] = [
            (i.model_dump() if hasattr(i, "model_dump") else i) for i in updates["items"]
        ]
    return await update_doc(
        collection="technical_schedules", doc_id=ts_id, updates=updates,
        user=user, entity_type="technical_schedule", ip=get_client_ip(request),
    )


@router.post("/technical-schedules/{ts_id}/status")
async def change_ts_status(
    ts_id: str, payload: TechnicalScheduleStatusChange, request: Request,
    user: dict = Depends(require_permission("surveys.edit")),
):
    db = get_db()
    ts = await db.technical_schedules.find_one({"_id": ts_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not ts:
        raise HTTPException(status_code=404, detail="Abaco non trovato")
    old = ts.get("ts_status")
    allowed = {
        "draft": {"in_technical_review", "cancelled"},
        "in_technical_review": {"draft", "approved_internally", "cancelled"},
        "approved_internally": {"sent_to_customer", "in_technical_review"},
        "sent_to_customer": {"viewed", "change_requested", "awaiting_signature"},
        "viewed": {"change_requested", "awaiting_signature"},
        "change_requested": {"draft", "in_technical_review"},
        "awaiting_signature": {"signed", "change_requested"},
    }
    if payload.new_status not in allowed.get(old, set()):
        raise HTTPException(status_code=409, detail=f"Transizione non ammessa: {old} → {payload.new_status}")
    now = utcnow()
    upd = {"ts_status": payload.new_status, "updated_at": now.isoformat()}
    if payload.new_status == "approved_internally":
        upd["approved_internally_at"] = now.isoformat()
        upd["approved_internally_by"] = user["id"]
    await db.technical_schedules.update_one({"_id": ts_id, "tenant_id": user["tenant_id"]}, {"$set": upd})
    await log_timeline_event(
        tenant_id=user["tenant_id"], domain="technical_schedule",
        event_type=f"ts.status.{payload.new_status}", ref_id=ts_id,
        contract_id=ts.get("contract_id"), customer_id=ts.get("customer_id"),
        survey_id=ts.get("survey_id"), technical_schedule_id=ts_id,
        actor_id=user["id"], actor_email=user["email"],
        old_status=old, new_status=payload.new_status,
        is_customer_visible=(payload.new_status in ("sent_to_customer", "signed")),
    )
    await record_audit(
        action=f"ts.status.{payload.new_status}", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="technical_schedule", entity_id=ts_id,
        meta={"reason": payload.reason, "old": old, "new": payload.new_status},
    )
    return await get_doc(collection="technical_schedules", doc_id=ts_id, tenant_id=user["tenant_id"])


@router.post("/technical-schedules/{ts_id}/send")
async def send_ts_to_customer(
    ts_id: str, payload: TechnicalScheduleSendRequest, request: Request,
    user: dict = Depends(require_permission("surveys.edit")),
):
    """Emette un token pubblico per l'abaco e cambia stato → sent_to_customer.
    Il cliente accede via /api/public/schedules/{token}.
    """
    db = get_db()
    ts = await db.technical_schedules.find_one({"_id": ts_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not ts:
        raise HTTPException(status_code=404, detail="Abaco non trovato")
    if ts.get("ts_status") not in ("approved_internally", "sent_to_customer", "viewed"):
        raise HTTPException(status_code=409, detail="Abaco non pronto all'invio (richiesto approved_internally)")
    # Snapshot hash canonico
    canon = {
        "items": ts.get("items"), "customer_id": ts.get("customer_id"),
        "contract_id": ts.get("contract_id"), "version": ts.get("version"),
    }
    snap_hash = canonical_hash(canon)
    # Public token
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires = utcnow() + timedelta(days=30)
    token_doc = {
        "_id": new_id(), "tenant_id": user["tenant_id"], "kind": "technical_schedule",
        "technical_schedule_id": ts_id, "contract_id": ts.get("contract_id"),
        "customer_id": ts.get("customer_id"),
        "token_hash": token_hash, "status": "active",
        "created_at": utcnow().isoformat(), "expires_at": expires.isoformat(),
        "requires_otp": bool(payload.require_otp),
        "snapshot_hash": snap_hash, "access_count": 0, "deleted_at": None,
    }
    await db.technical_schedule_tokens.insert_one(token_doc)
    # Aggiorna TS
    await db.technical_schedules.update_one(
        {"_id": ts_id, "tenant_id": user["tenant_id"]},
        {"$set": {
            "ts_status": "sent_to_customer",
            "sent_to_customer_at": utcnow().isoformat(),
            "sent_via": payload.channel,
            "public_token_id": token_doc["_id"],
            "snapshot_hash": snap_hash,
        }},
    )
    await log_timeline_event(
        tenant_id=user["tenant_id"], domain="technical_schedule",
        event_type="ts.sent_to_customer", ref_id=ts_id,
        contract_id=ts.get("contract_id"), customer_id=ts.get("customer_id"),
        technical_schedule_id=ts_id, actor_id=user["id"],
        old_status=ts.get("ts_status"), new_status="sent_to_customer",
        is_customer_visible=True, customer_label="Abaco tecnico inviato",
        customer_stage="schedule_sent",
    )
    return {"ok": True, "raw_token": raw, "expires_at": expires.isoformat(), "channel": payload.channel}


@router.post("/technical-schedules/{ts_id}/new-version")
async def new_ts_version(
    ts_id: str, request: Request,
    user: dict = Depends(require_permission("surveys.edit")),
):
    """Crea una nuova versione dell'Abaco (superseded quella precedente).
    Usato per gestire richieste di modifica post invio."""
    db = get_db()
    prev = await db.technical_schedules.find_one({"_id": ts_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not prev:
        raise HTTPException(status_code=404, detail="Abaco non trovato")
    if prev.get("ts_status") == "released_to_production":
        raise HTTPException(status_code=409, detail="Impossibile creare nuova versione: già rilasciato in produzione")
    new = dict(prev)
    new.pop("_id", None)
    new_v = int(prev.get("version", 1)) + 1
    new_id_ = new_id()
    new.update({
        "id": new_id_, "version": new_v,
        "revision_label": f"V{new_v:02d}",
        "parent_version_id": prev.get("_id") or prev.get("id"),
        "is_current": True, "ts_status": "draft",
        "signed_at": None, "signature_hash": None, "signed_pdf_key": None,
        "sent_to_customer_at": None, "public_token_id": None,
        "approved_internally_at": None, "approved_internally_by": None,
        "created_at": utcnow().isoformat(), "updated_at": utcnow().isoformat(),
        "deleted_at": None,
    })
    # Deprecate previous
    await db.technical_schedules.update_one(
        {"_id": ts_id, "tenant_id": user["tenant_id"]},
        {"$set": {"is_current": False, "ts_status": "superseded", "superseded_by_id": new_id_}},
    )
    # Numerazione: mantiene il progressive number ma incrementa version
    if not new.get("number"):
        num, num_int = await next_number(user["tenant_id"], "technical_schedule", prefix="ABACO")
        new["number"] = num
        new["number_int"] = num_int
    await db.technical_schedules.insert_one({**new, "_id": new_id_})
    await log_timeline_event(
        tenant_id=user["tenant_id"], domain="technical_schedule",
        event_type="ts.new_version", ref_id=new_id_,
        contract_id=prev.get("contract_id"), customer_id=prev.get("customer_id"),
        actor_id=user["id"], payload={"from_version": prev.get("version"), "to_version": new_v},
    )
    return {"ok": True, "new_id": new_id_, "version": new_v}


# ---------------------------------------------------------------------
# PUBLIC — Cliente vede/firma abaco
# ---------------------------------------------------------------------
public_router = APIRouter(prefix="/public/schedules", tags=["Public — Abaco"])


async def _resolve_ts_token(token: str) -> tuple[dict, dict]:
    db = get_db()
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    tok = await db.technical_schedule_tokens.find_one({
        "token_hash": token_hash, "deleted_at": None,
    })
    if not tok:
        raise HTTPException(status_code=404, detail="Link non disponibile")
    if tok["status"] != "active":
        raise HTTPException(status_code=410, detail="Link non più disponibile")
    if tok.get("expires_at") and datetime.fromisoformat(tok["expires_at"]) < utcnow():
        await db.technical_schedule_tokens.update_one({"_id": tok["_id"]}, {"$set": {"status": "expired"}})
        raise HTTPException(status_code=410, detail="Link scaduto")
    ts = await db.technical_schedules.find_one({
        "_id": tok["technical_schedule_id"], "tenant_id": tok["tenant_id"], "deleted_at": None,
    })
    if not ts:
        raise HTTPException(status_code=404, detail="Abaco non trovato")
    return tok, ts


@public_router.get("/{token}")
async def public_view_ts(token: str, request: Request):
    tok, ts = await _resolve_ts_token(token)
    db = get_db()
    await db.technical_schedule_tokens.update_one(
        {"_id": tok["_id"]},
        {"$inc": {"access_count": 1}, "$set": {"last_access_at": utcnow().isoformat()}},
    )
    if ts.get("ts_status") == "sent_to_customer":
        await db.technical_schedules.update_one(
            {"_id": ts["_id"]}, {"$set": {"ts_status": "viewed", "viewed_at": utcnow().isoformat()}},
        )
    # Sanitize response: nessun costo, nessun tenant, nessun id interno esposto in modo tale
    return {
        "schedule": {
            "number": ts.get("number"),
            "version": ts.get("version"),
            "revision_label": ts.get("revision_label"),
            "signed_at": ts.get("signed_at"),
            "ts_status": ts.get("ts_status"),
            "site_address": ts.get("site_address"),
            "items": [
                {k: v for k, v in it.items() if k not in ("blocking_errors",)}
                for it in (ts.get("items") or [])
            ],
        },
        "requires_otp": bool(tok.get("requires_otp")),
    }


@public_router.post("/{token}/sign")
async def public_sign_ts(token: str, payload: TechnicalScheduleSignPayload, request: Request):
    tok, ts = await _resolve_ts_token(token)
    db = get_db()
    if ts.get("ts_status") == "signed":
        raise HTTPException(status_code=409, detail="Abaco già firmato")
    if not all([
        payload.consent_all_openings_verified, payload.consent_measurements_verified,
        payload.consent_colors_glass_openings_verified, payload.consent_supersedes_preview,
        payload.consent_authorize_production, payload.consent_accept_variances_if_any,
    ]):
        raise HTTPException(status_code=400, detail="Tutte le conferme sono obbligatorie")
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")
    ip_hash = hashlib.sha256(f"iph:{ip}".encode()).hexdigest()[:16]
    # Evidence hash chain
    canon = {
        "ts_id": ts["_id"], "version": ts.get("version"),
        "snapshot_hash": ts.get("snapshot_hash"),
        "signer_name": payload.signer_name, "signer_email": payload.signer_email,
        "consents": {
            "all_openings_verified": payload.consent_all_openings_verified,
            "measurements_verified": payload.consent_measurements_verified,
            "colors_glass_openings_verified": payload.consent_colors_glass_openings_verified,
            "supersedes_preview": payload.consent_supersedes_preview,
            "authorize_production": payload.consent_authorize_production,
            "accept_variances_if_any": payload.consent_accept_variances_if_any,
        },
        "ip_hash": ip_hash, "ua": ua[:200],
        "signed_at": utcnow().isoformat(),
    }
    evidence_hash = canonical_hash(canon)
    evidence_id = new_id()
    # Salva evidence
    await db.technical_schedule_signatures.insert_one({
        "_id": evidence_id, "tenant_id": ts["tenant_id"],
        "technical_schedule_id": ts["_id"], "version": ts.get("version"),
        "signer_name": payload.signer_name, "signer_email": payload.signer_email,
        "signature_data_url": payload.signature_data_url[:100000],  # limita
        "evidence_hash": evidence_hash, "canonical": canon,
        "ip_hash": ip_hash, "user_agent": ua[:200],
        "signed_at": utcnow().isoformat(), "deleted_at": None,
    })
    await db.technical_schedules.update_one(
        {"_id": ts["_id"]},
        {"$set": {
            "ts_status": "signed", "signed_at": utcnow().isoformat(),
            "signed_by_name": payload.signer_name, "signed_email": payload.signer_email,
            "signature_hash": evidence_hash, "evidence_id": evidence_id,
            "signed_ip_hash": ip_hash, "signed_user_agent": ua[:200],
        }},
    )
    # Invalida token OTP
    await db.technical_schedule_tokens.update_one({"_id": tok["_id"]}, {"$set": {"status": "consumed"}})
    # Log timeline
    await log_timeline_event(
        tenant_id=ts["tenant_id"], domain="technical_schedule",
        event_type="ts.signed", ref_id=ts["_id"],
        contract_id=ts.get("contract_id"), customer_id=ts.get("customer_id"),
        survey_id=ts.get("survey_id"), technical_schedule_id=ts["_id"],
        source="customer", is_customer_visible=True,
        customer_label="Abaco tecnico approvato", customer_stage="schedule_approved",
        new_status="signed", ip_hash=ip_hash,
    )
    # Crea automaticamente Executive Order (idempotente)
    eo_id = await create_executive_order_from_signed_ts(
        tenant_id=ts["tenant_id"], technical_schedule_id=ts["_id"], actor_id="customer",
    )
    return {"ok": True, "evidence_id": evidence_id, "evidence_hash": evidence_hash, "executive_order_id": eo_id}


# ---------------------------------------------------------------------
# EXECUTIVE ORDERS
# ---------------------------------------------------------------------
@router.get("/executive-orders")
async def list_eo(
    contract_id: Optional[str] = None, eo_status: Optional[str] = None,
    skip: int = 0, limit: int = 50,
    user: dict = Depends(require_permission("sales.orders.view")),
):
    filters = {}
    if contract_id: filters["contract_id"] = contract_id
    if eo_status: filters["eo_status"] = eo_status
    return await list_docs(
        collection="executive_orders", tenant_id=user["tenant_id"], filters=filters,
        sort=[("number_int", -1)], skip=skip, limit=limit,
    )


@router.get("/executive-orders/{eo_id}")
async def get_eo(eo_id: str, user: dict = Depends(require_permission("sales.orders.view"))):
    return await get_doc(collection="executive_orders", doc_id=eo_id, tenant_id=user["tenant_id"])


# ---------------------------------------------------------------------
# PRODUCTION RELEASE CHECK
# ---------------------------------------------------------------------
@router.post("/production/release-check")
async def do_release_check(
    payload: ProductionReleaseCheckRequest, request: Request,
    user: dict = Depends(require_permission("production.release")),
):
    result = await production_release_check(
        tenant_id=user["tenant_id"], contract_id=payload.contract_id,
        checked_by=user["email"],
    )
    await record_audit(
        action="production.release_check", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="contract", entity_id=payload.contract_id,
        meta={"eligible": result.eligible,
                "blocking_reasons": result.blocking_reasons,
                "warnings": result.warnings},
    )
    return result.model_dump()


@router.post("/production/release-override")
async def release_override(
    payload: ProductionReleaseOverrideRequest, request: Request,
    user: dict = Depends(require_permission("production.override_release")),
):
    """Override manuale con doppia approvazione. Richiede l'approvatore secondario."""
    db = get_db()
    approver = await db.users.find_one({"_id": payload.second_approver_user_id, "tenant_id": user["tenant_id"]})
    if not approver:
        raise HTTPException(status_code=400, detail="Secondo approvatore non trovato")
    if approver["_id"] == user["id"]:
        raise HTTPException(status_code=400, detail="Il secondo approvatore deve essere un utente diverso")
    doc = {
        "_id": new_id(), "tenant_id": user["tenant_id"],
        "contract_id": payload.contract_id, "reason": payload.reason,
        "approver_1_id": user["id"], "approver_1_email": user["email"],
        "approver_2_id": approver["_id"], "approver_2_email": approver.get("email"),
        "created_at": utcnow().isoformat(), "deleted_at": None,
    }
    await db.production_release_overrides.insert_one(doc)
    await record_audit(
        action="production.release_override", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="contract", entity_id=payload.contract_id,
        meta={"reason": payload.reason, "second_approver_id": payload.second_approver_user_id},
    )
    return {"ok": True, "override_id": doc["_id"]}


# ---------------------------------------------------------------------
# TIMELINE
# ---------------------------------------------------------------------
@router.get("/timeline")
async def list_timeline(
    contract_id: Optional[str] = None, customer_id: Optional[str] = None,
    quote_id: Optional[str] = None, domain: Optional[str] = None,
    skip: int = 0, limit: int = 200,
    user: dict = Depends(get_current_user),
):
    """Timeline unificata (interna). L'utente vede eventi del suo tenant."""
    filters: dict = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if contract_id: filters["contract_id"] = contract_id
    if customer_id: filters["customer_id"] = customer_id
    if quote_id: filters["quote_id"] = quote_id
    if domain: filters["domain"] = domain
    db = get_db()
    cur = db.timeline_events.find(filters).sort("created_at", -1).skip(skip).limit(limit)
    items = [from_mongo(d) for d in await cur.to_list(limit)]
    total = await db.timeline_events.count_documents(filters)
    return {"items": items, "total": total, "skip": skip, "limit": limit}


# ---------------------------------------------------------------------
# CUSTOMER PORTAL — Tracking cliente (interno alla piattaforma stessa)
# ---------------------------------------------------------------------
customer_router = APIRouter(prefix="/customer-portal", tags=["Customer Portal"])


@customer_router.get("/orders/{contract_id}/tracking")
async def customer_tracking(contract_id: str, user: dict = Depends(get_current_user)):
    """Tracking pubblico dell'ordine per il cliente autenticato.
    Restituisce timeline filtrata (solo eventi customer-visible) con label sanitizzati.
    """
    db = get_db()
    # Verifica ownership: il customer_id dell'utente deve corrispondere al contratto
    contract = await db.contracts.find_one({
        "_id": contract_id, "tenant_id": user["tenant_id"], "deleted_at": None,
    })
    if not contract:
        raise HTTPException(status_code=404, detail="Ordine non disponibile")
    # Se l'utente è un cliente, restringi al proprio customer_id
    is_customer_user = user.get("kind") == "customer" or user.get("is_customer")
    if is_customer_user:
        if contract.get("customer_id") != user.get("customer_id"):
            raise HTTPException(status_code=404, detail="Ordine non disponibile")
    events = await db.timeline_events.find({
        "tenant_id": user["tenant_id"], "contract_id": contract_id,
        "is_customer_visible": True, "deleted_at": None,
    }).sort("created_at", 1).to_list(500)
    # Sanitize
    out = []
    for e in events:
        out.append({
            "date": e.get("created_at"),
            "domain": e.get("domain"),
            "event_type": e.get("event_type"),
            "label": e.get("customer_label"),
            "stage": e.get("customer_stage"),
            "status": e.get("new_status"),
        })
    return {
        "contract": {
            "number": contract.get("number"), "signed_at": contract.get("signed_at"),
            "contract_status": contract.get("contract_status"),
        },
        "timeline": out,
        "default_map": DEFAULT_CUSTOMER_STATUS_MAP,
    }


# ---------------------------------------------------------------------
# CUSTOMER STATUS MAPPING CRUD
# ---------------------------------------------------------------------
@router.get("/customer-status-mappings")
async def list_status_mappings(user: dict = Depends(require_permission("customer_portal.manage_visibility"))):
    return await list_docs(
        collection="customer_status_mappings", tenant_id=user["tenant_id"],
        sort=[("order_index", 1)], limit=200,
    )


@router.post("/customer-status-mappings")
async def create_status_mapping(payload: dict, user: dict = Depends(require_permission("customer_portal.manage_visibility"))):
    from app.models_workflow import CustomerStatusMappingCreate
    p = CustomerStatusMappingCreate(**payload)
    inst = CustomerStatusMapping(**p.model_dump())
    return await create_doc(collection="customer_status_mappings", model_instance=inst,
                             user=user, entity_type="customer_status_mapping", ip="")


# ---------------------------------------------------------------------
# VARIANCE (variante economica derivata dal rilievo)
# ---------------------------------------------------------------------
@router.get("/variances")
async def list_variances(
    contract_id: Optional[str] = None,
    user: dict = Depends(require_permission("quotes.view")),
):
    filters = {}
    if contract_id: filters["contract_id"] = contract_id
    return await list_docs(collection="variances", tenant_id=user["tenant_id"],
                            filters=filters, sort=[("created_at", -1)], limit=100)


@router.post("/variances")
async def create_variance(
    payload: dict, request: Request,
    user: dict = Depends(require_permission("quotes.edit")),
):
    v = Variance(tenant_id=user["tenant_id"], **payload)
    total_p = sum(l.delta_price for l in v.lines)
    total_c = sum(l.delta_cost for l in v.lines)
    v.total_delta_price = total_p
    v.total_delta_cost = total_c
    from app.services.ops_common import next_number
    n, ni = await next_number(user["tenant_id"], "variance", prefix="VAR")
    v.number = n; v.number_int = ni
    doc = to_mongo(v.model_dump(by_alias=True))
    db = get_db()
    await db.variances.insert_one(doc)
    return v.model_dump()
