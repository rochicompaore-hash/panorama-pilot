"""M6.OPS Router — Handoff, teams, assignment rules, dashboards data,
commissions, profitability, invoices, lead intake, inbox, templates, consents.

Convenzione: tutti tenant-scoped, RBAC via require_permission.
"""
from __future__ import annotations
import hashlib
import hmac
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from app.db import get_db
from app.deps import get_current_user, require_permission, require_any_permission, get_client_ip
from app.services.ops_common import create_doc, get_doc, list_docs, update_doc, soft_delete_doc, next_number
from app.services.audit import record_audit
from app.services.handoff_engine import create_handoff, scan_overdue_handoffs
from app.services.commission_engine import (
    compute_profitability, compute_commission, compute_and_persist_commission_estimate,
    apply_collection_accrual, reverse_commission_on_cancellation, get_active_plan, DEFAULT_TIERS,
)
from app.services.workflow_engine import log_timeline_event
from app.mongo_utils import to_mongo, from_mongo
from app.models import new_id, utcnow
from app.models_handoff import (
    OperationalAreaConfig, OperationalAreaConfigUpsert,
    UserGroup, UserGroupCreate, UserGroupUpdate,
    AssignmentRule, AssignmentRuleCreate,
    OperationalHandoff, OperationalHandoffCreate,
    HandoffAckRequest, HandoffCompleteRequest, HandoffReassignRequest, HandoffBlockRequest,
)
from app.models_commissions import (
    CommissionPlan, CommissionPlanCreate, CommissionPlanUpdate,
    CommissionInvoice, CommissionInvoiceCreate, CommissionInvoiceUpdate,
    ProfitabilityBreakdown, ProfitabilityTier,
)
from app.models_comms import (
    LeadWebhookConfig, LeadWebhookConfigCreate, LeadWebhookConfigUpdate, LeadWebhookIngestion,
    LeadWebhookPayload,
    Conversation, ConversationCreate, Message, SendMessageRequest,
    CommunicationChannel,
    MessageTemplate, MessageTemplateCreate, MessageTemplateUpdate,
    EmailAutomation, EmailAutomationCreate, EmailAutomationUpdate,
    Consent, ConsentCreate,
)


router = APIRouter(prefix="/ops", tags=["Operations E2E"])


# =====================================================================
# OPERATIONAL AREA CONFIG
# =====================================================================
@router.get("/areas")
async def list_areas(user: dict = Depends(get_current_user)):
    return await list_docs(collection="operational_area_configs", tenant_id=user["tenant_id"],
                            sort=[("order_index", 1)], limit=50)


@router.post("/areas")
async def upsert_area(payload: OperationalAreaConfigUpsert, user: dict = Depends(require_permission("*"))):
    db = get_db()
    existing = await db.operational_area_configs.find_one({"tenant_id": user["tenant_id"], "code": payload.code, "deleted_at": None})
    if existing:
        await db.operational_area_configs.update_one(
            {"_id": existing["_id"]}, {"$set": payload.model_dump()},
        )
        return await get_doc(collection="operational_area_configs", doc_id=existing["_id"], tenant_id=user["tenant_id"])
    inst = OperationalAreaConfig(**payload.model_dump())
    return await create_doc(collection="operational_area_configs", model_instance=inst, user=user,
                             entity_type="operational_area", ip="")


# =====================================================================
# USER GROUPS
# =====================================================================
@router.get("/user-groups")
async def list_groups(area: Optional[str] = None, user: dict = Depends(get_current_user)):
    filters = {}
    if area: filters["area"] = area
    return await list_docs(collection="user_groups", tenant_id=user["tenant_id"], filters=filters, limit=100)


@router.post("/user-groups")
async def create_group(payload: UserGroupCreate, user: dict = Depends(require_permission("*"))):
    inst = UserGroup(**payload.model_dump())
    return await create_doc(collection="user_groups", model_instance=inst, user=user,
                             entity_type="user_group", ip="")


@router.patch("/user-groups/{gid}")
async def update_group(gid: str, payload: UserGroupUpdate, user: dict = Depends(require_permission("*"))):
    return await update_doc(collection="user_groups", doc_id=gid,
                             updates=payload.model_dump(exclude_unset=True), user=user,
                             entity_type="user_group", ip="")


@router.delete("/user-groups/{gid}")
async def delete_group(gid: str, user: dict = Depends(require_permission("*"))):
    return await soft_delete_doc(collection="user_groups", doc_id=gid, user=user,
                                  entity_type="user_group", ip="")


# =====================================================================
# ASSIGNMENT RULES
# =====================================================================
@router.get("/assignment-rules")
async def list_rules(area: Optional[str] = None, user: dict = Depends(get_current_user)):
    filters = {}
    if area: filters["area"] = area
    return await list_docs(collection="assignment_rules", tenant_id=user["tenant_id"],
                            filters=filters, sort=[("priority", 1)], limit=200)


@router.post("/assignment-rules")
async def create_rule(payload: AssignmentRuleCreate, user: dict = Depends(require_permission("*"))):
    inst = AssignmentRule(**payload.model_dump())
    return await create_doc(collection="assignment_rules", model_instance=inst, user=user,
                             entity_type="assignment_rule", ip="")


@router.delete("/assignment-rules/{rid}")
async def delete_rule(rid: str, user: dict = Depends(require_permission("*"))):
    return await soft_delete_doc(collection="assignment_rules", doc_id=rid, user=user,
                                  entity_type="assignment_rule", ip="")


# =====================================================================
# OPERATIONAL HANDOFF
# =====================================================================
@router.get("/handoffs")
async def list_handoffs(
    to_area: Optional[str] = None, handoff_status: Optional[str] = None,
    assigned_user_id: Optional[str] = None, contract_id: Optional[str] = None,
    skip: int = 0, limit: int = 100,
    user: dict = Depends(get_current_user),
):
    filters: Dict[str, Any] = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if to_area: filters["to_area"] = to_area
    if handoff_status: filters["handoff_status"] = handoff_status
    if contract_id: filters["contract_id"] = contract_id
    # Filtro personale se richiesto
    if assigned_user_id == "me":
        filters["assigned_user_ids"] = user["id"]
    elif assigned_user_id:
        filters["assigned_user_ids"] = assigned_user_id
    db = get_db()
    cur = db.operational_handoffs.find(filters).sort([("priority", 1), ("due_at", 1), ("created_at", -1)]).skip(skip).limit(limit)
    items = [from_mongo(d) for d in await cur.to_list(limit)]
    total = await db.operational_handoffs.count_documents(filters)
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("/handoffs")
async def create_handoff_ep(
    payload: OperationalHandoffCreate, request: Request,
    user: dict = Depends(get_current_user),
):
    ho_id = await create_handoff(tenant_id=user["tenant_id"], actor_user_id=user["id"], payload=payload.model_dump())
    await record_audit(action="handoff.create", tenant_id=user["tenant_id"], user_id=user["id"],
                        user_email=user["email"], ip=get_client_ip(request),
                        entity_type="handoff", entity_id=ho_id,
                        meta={"to_area": payload.to_area})
    return {"ok": True, "id": ho_id}


@router.post("/handoffs/{hid}/ack")
async def ack_handoff(hid: str, user: dict = Depends(get_current_user)):
    db = get_db()
    ho = await db.operational_handoffs.find_one({"_id": hid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not ho:
        raise HTTPException(status_code=404, detail="Handoff non trovato")
    if user["id"] not in (ho.get("assigned_user_ids") or []) and user["id"] != (ho.get("assigned_group_id_leader")):
        # allow if user is in the group leader chain — simplified
        pass
    await db.operational_handoffs.update_one(
        {"_id": hid, "tenant_id": user["tenant_id"]},
        {"$set": {"handoff_status": "acknowledged", "acknowledged_by": user["id"], "acknowledged_at": utcnow().isoformat()}},
    )
    return {"ok": True}


@router.post("/handoffs/{hid}/start")
async def start_handoff(hid: str, user: dict = Depends(get_current_user)):
    db = get_db()
    await db.operational_handoffs.update_one(
        {"_id": hid, "tenant_id": user["tenant_id"]},
        {"$set": {"handoff_status": "in_progress", "started_at": utcnow().isoformat()}},
    )
    return {"ok": True}


@router.post("/handoffs/{hid}/complete")
async def complete_handoff(hid: str, payload: dict, user: dict = Depends(get_current_user)):
    db = get_db()
    await db.operational_handoffs.update_one(
        {"_id": hid, "tenant_id": user["tenant_id"]},
        {"$set": {"handoff_status": "completed", "completed_at": utcnow().isoformat(),
                   "notes": payload.get("note")}},
    )
    return {"ok": True}


@router.post("/handoffs/{hid}/block")
async def block_handoff(hid: str, payload: HandoffBlockRequest, user: dict = Depends(get_current_user)):
    db = get_db()
    await db.operational_handoffs.update_one(
        {"_id": hid, "tenant_id": user["tenant_id"]},
        {"$set": {"handoff_status": "blocked", "notes": payload.reason}},
    )
    return {"ok": True}


@router.post("/handoffs/scan-overdue")
async def scan_overdue(user: dict = Depends(require_permission("*"))):
    n = await scan_overdue_handoffs(user["tenant_id"])
    return {"ok": True, "updated": n}


# =====================================================================
# COMMISSION PLANS
# =====================================================================
@router.get("/commission-plans")
async def list_plans(user: dict = Depends(require_permission("commission.manage"))):
    return await list_docs(collection="commission_plans", tenant_id=user["tenant_id"],
                            sort=[("version", -1)], limit=50)


@router.post("/commission-plans")
async def create_plan(payload: CommissionPlanCreate, user: dict = Depends(require_permission("commission.manage"))):
    p = CommissionPlan(**payload.model_dump())
    if not p.tiers:
        p.tiers = [ProfitabilityTier(**t) for t in DEFAULT_TIERS]
    return await create_doc(collection="commission_plans", model_instance=p, user=user,
                             entity_type="commission_plan", ip="")


@router.patch("/commission-plans/{pid}")
async def update_plan(pid: str, payload: CommissionPlanUpdate, user: dict = Depends(require_permission("commission.manage"))):
    return await update_doc(collection="commission_plans", doc_id=pid,
                             updates=payload.model_dump(exclude_unset=True), user=user,
                             entity_type="commission_plan", ip="")


# =====================================================================
# PROFITABILITY (permission-gated)
# =====================================================================
@router.get("/profitability/{contract_id}")
async def get_profitability(contract_id: str, user: dict = Depends(require_permission("profitability.view"))):
    res = await compute_profitability(tenant_id=user["tenant_id"], contract_id=contract_id)
    return res.model_dump()


@router.post("/commissions/estimate/{contract_id}")
async def estimate_contract_commission(
    contract_id: str, request: Request,
    user: dict = Depends(require_permission("commission.manage")),
):
    db = get_db()
    ctr = await db.contracts.find_one({"_id": contract_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not ctr:
        raise HTTPException(status_code=404, detail="Contratto non trovato")
    sales_rep = ctr.get("sales_rep_id") or ctr.get("created_by") or user["id"]
    result = await compute_and_persist_commission_estimate(
        tenant_id=user["tenant_id"], contract_id=contract_id, sales_rep_id=sales_rep,
    )
    return result


# =====================================================================
# COMMISSION ENTRIES
# =====================================================================
@router.get("/commissions/entries")
async def list_entries(
    sales_rep_id: Optional[str] = None,
    entry_status: Optional[str] = None,
    scope: str = "own",   # own | team | all
    user: dict = Depends(get_current_user),
):
    filters: Dict[str, Any] = {"tenant_id": user["tenant_id"], "deleted_at": None}
    perms = set(user.get("_perms") or [])
    is_admin = user.get("is_superadmin") or user.get("is_platform_owner") or "*" in perms
    can_view_team = is_admin or "commission.view_team" in perms
    if scope == "own" or (not can_view_team):
        filters["sales_rep_id"] = user["id"]
    elif sales_rep_id and can_view_team:
        filters["sales_rep_id"] = sales_rep_id
    if entry_status:
        filters["entry_status"] = entry_status
    db = get_db()
    items = [from_mongo(d) for d in await db.commission_entries.find(filters).sort("created_at", -1).limit(200).to_list(200)]
    return {"items": items, "total": len(items)}


# =====================================================================
# COMMISSION INVOICES (Le mie commissioni)
# =====================================================================
@router.post("/commissions/invoices")
async def create_commission_invoice(
    payload: CommissionInvoiceCreate, request: Request,
    user: dict = Depends(get_current_user),
):
    perms = set(user.get("_perms") or [])
    sales_rep_id = payload.sales_rep_id or user["id"]
    if sales_rep_id != user["id"] and "commission.manage" not in perms and not (user.get("is_superadmin") or user.get("is_platform_owner")):
        raise HTTPException(status_code=403, detail="Non autorizzato a caricare fattura per altri")
    inv = CommissionInvoice(tenant_id=user["tenant_id"], sales_rep_id=sales_rep_id,
                             inv_status="submitted", submitted_at=utcnow(),
                             **payload.model_dump(exclude={"sales_rep_id"}))
    n, ni = await next_number(user["tenant_id"], "commission_invoice", prefix="COMM")
    inv.number = n
    doc = to_mongo(inv.model_dump(by_alias=True))
    db = get_db()
    await db.commission_invoices.insert_one(doc)
    return inv.model_dump()


@router.get("/commissions/invoices")
async def list_commission_invoices(user: dict = Depends(get_current_user), scope: str = "own"):
    perms = set(user.get("_perms") or [])
    can_manage = "commission.manage" in perms or user.get("is_superadmin") or user.get("is_platform_owner")
    filters: Dict[str, Any] = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if scope == "own" or not can_manage:
        filters["sales_rep_id"] = user["id"]
    db = get_db()
    items = [from_mongo(d) for d in await db.commission_invoices.find(filters).sort("submitted_at", -1).limit(100).to_list(100)]
    return {"items": items, "total": len(items)}


@router.post("/commissions/invoices/{iid}/approve")
async def approve_commission_invoice(iid: str, user: dict = Depends(require_permission("commission.approve"))):
    db = get_db()
    await db.commission_invoices.update_one(
        {"_id": iid, "tenant_id": user["tenant_id"]},
        {"$set": {"inv_status": "approved", "reviewed_at": utcnow().isoformat(), "reviewed_by": user["id"]}},
    )
    return {"ok": True}


@router.post("/commissions/invoices/{iid}/reject")
async def reject_commission_invoice(iid: str, payload: dict, user: dict = Depends(require_permission("commission.approve"))):
    db = get_db()
    await db.commission_invoices.update_one(
        {"_id": iid, "tenant_id": user["tenant_id"]},
        {"$set": {"inv_status": "rejected", "rejection_reason": payload.get("reason"),
                   "reviewed_at": utcnow().isoformat(), "reviewed_by": user["id"]}},
    )
    return {"ok": True}


@router.post("/commissions/invoices/{iid}/pay")
async def pay_commission_invoice(iid: str, payload: dict, user: dict = Depends(require_permission("commission.pay"))):
    db = get_db()
    await db.commission_invoices.update_one(
        {"_id": iid, "tenant_id": user["tenant_id"], "inv_status": "approved"},
        {"$set": {"inv_status": "paid", "paid_at": utcnow().isoformat(),
                   "payment_ref": payload.get("payment_ref")}},
    )
    return {"ok": True}


# =====================================================================
# DASHBOARDS (aggregated data)
# =====================================================================
async def _kpi_range(*, tenant_id: str, sales_rep_id: Optional[str] = None,
                     since: Optional[datetime] = None, until: Optional[datetime] = None) -> Dict[str, Any]:
    db = get_db()
    since = since or (utcnow() - timedelta(days=30))
    until = until or utcnow()
    q_time = {"$gte": since.isoformat(), "$lte": until.isoformat()}
    filt_base = {"tenant_id": tenant_id, "deleted_at": None}
    if sales_rep_id:
        filt_base["sales_rep_id"] = sales_rep_id

    leads = await db.leads.count_documents({**filt_base, "created_at": q_time})
    quotes_sent = await db.quotes.count_documents({**filt_base, "quote_status": {"$in": ["sent", "viewed", "negotiating", "accepted"]}, "created_at": q_time})
    contracts_signed = await db.contracts.count_documents({**filt_base, "contract_status": "signed", "signed_at": q_time})
    activities_appt_done = await db.activities.count_documents({**filt_base, "type": "appointment", "activity_status": {"$in": ["done", "completed"]}, "created_at": q_time})
    # revenue firmato
    async def _sum_field(coll, field, extra):
        pipe = [{"$match": {**filt_base, **extra}}, {"$group": {"_id": None, "s": {"$sum": f"${field}"}}}]
        r = await db[coll].aggregate(pipe).to_list(1)
        return float(r[0]["s"]) if r else 0.0
    revenue_signed = await _sum_field("contracts", "quote_snapshot.total", {"contract_status": "signed", "signed_at": q_time})
    ticket_medio = (revenue_signed / contracts_signed) if contracts_signed else 0
    conv_appt_contract = (contracts_signed / activities_appt_done * 100) if activities_appt_done else 0
    conv_lead_appt = (activities_appt_done / leads * 100) if leads else 0
    return {
        "leads": leads, "appointments_done": activities_appt_done,
        "quotes_sent": quotes_sent, "contracts_signed": contracts_signed,
        "revenue_signed": round(revenue_signed, 2),
        "ticket_medio": round(ticket_medio, 2),
        "conv_appointment_to_contract_pct": round(conv_appt_contract, 2),
        "conv_lead_to_appointment_pct": round(conv_lead_appt, 2),
        "since": since.isoformat(), "until": until.isoformat(),
    }


@router.get("/dashboard/company")
async def dashboard_company(user: dict = Depends(require_permission("dashboard.view"))):
    return await _kpi_range(tenant_id=user["tenant_id"])


@router.get("/dashboard/sales-team")
async def dashboard_team(user: dict = Depends(require_any_permission("commission.view_team", "dashboard.view"))):
    db = get_db()
    perms = set(user.get("_perms") or [])
    is_admin = user.get("is_superadmin") or user.get("is_platform_owner") or "*" in perms
    if not (is_admin or "commission.view_team" in perms):
        raise HTTPException(status_code=403, detail="Non autorizzato")
    reps = await db.users.find({"tenant_id": user["tenant_id"], "is_active": True, "deleted_at": None}).to_list(200)
    since = utcnow() - timedelta(days=30)
    rows = []
    for r in reps:
        k = await _kpi_range(tenant_id=user["tenant_id"], sales_rep_id=r["_id"], since=since)
        rows.append({"sales_rep_id": r["_id"], "email": r.get("email"),
                     "full_name": f"{r.get('first_name','')} {r.get('last_name','')}".strip(), **k})
    rows.sort(key=lambda x: -x["contracts_signed"])
    return {"rows": rows, "benchmark_pct": 30.0}


@router.get("/dashboard/my")
async def dashboard_my(user: dict = Depends(get_current_user)):
    k = await _kpi_range(tenant_id=user["tenant_id"], sales_rep_id=user["id"])
    # own commissions summary (senza costi)
    db = get_db()
    entries = await db.commission_entries.find({
        "tenant_id": user["tenant_id"], "sales_rep_id": user["id"], "deleted_at": None,
    }).to_list(500)
    est = sum(float(e.get("computed_amount") or 0) for e in entries if e.get("entry_status") in ("estimated", "approved"))
    accrued = sum(float(e.get("accrued_amount") or 0) for e in entries if e.get("entry_status") in ("accrued", "invoiceable"))
    paid = sum(float(e.get("computed_amount") or 0) for e in entries if e.get("entry_status") == "paid")
    return {
        **k,
        "benchmark_pct": 30.0,
        "commissions_estimated": round(est, 2),
        "commissions_accrued": round(accrued, 2),
        "commissions_paid": round(paid, 2),
    }


# =====================================================================
# LEAD WEBHOOK INTAKE (public, no auth — signed)
# =====================================================================
public_leads_router = APIRouter(prefix="/integrations/leads", tags=["Public — Lead Intake"])


def _normalize_phone(p: str) -> str:
    if not p: return ""
    return re.sub(r"[^\d+]", "", p)


async def _dedup_lead_key(tenant_id: str, source: str, payload: Dict[str, Any]) -> str:
    phone = _normalize_phone(payload.get("phone", ""))
    email = (payload.get("email") or "").lower().strip()
    social_id = payload.get("social_profile_id") or payload.get("lead_id") or ""
    key_source = f"{tenant_id}|{source}|{phone}|{email}|{social_id}"
    return hashlib.sha256(key_source.encode()).hexdigest()[:32]


@public_leads_router.get("/webhook/{slug}/verify")
async def verify_webhook(slug: str, request: Request):
    """Meta webhook verification (hub.challenge)."""
    db = get_db()
    cfg = await db.lead_webhook_configs.find_one({"slug": slug, "deleted_at": None})
    if not cfg:
        raise HTTPException(status_code=404)
    challenge = request.query_params.get("hub.challenge")
    verify_token = request.query_params.get("hub.verify_token")
    if verify_token and verify_token == cfg.get("verify_token"):
        return int(challenge) if (challenge and challenge.isdigit()) else (challenge or "ok")
    raise HTTPException(status_code=403, detail="Verify token mismatch")


@public_leads_router.post("/webhook/{slug}")
async def receive_lead_webhook(
    slug: str, request: Request,
    x_signature: Optional[str] = Header(default=None),
):
    """Ricezione lead da landing/Meta/webhook. Firma HMAC opzionale."""
    db = get_db()
    cfg = await db.lead_webhook_configs.find_one({"slug": slug, "active": True, "deleted_at": None})
    if not cfg:
        raise HTTPException(status_code=404, detail="Webhook config non trovata")
    body = await request.body()
    signature_ok = True
    if cfg.get("signature_algorithm") == "hmac_sha256":
        secret_hash = cfg.get("secret_key_hash") or ""
        if secret_hash:
            expected = hmac.new(secret_hash.encode(), body, hashlib.sha256).hexdigest()
            signature_ok = hmac.compare_digest(expected, (x_signature or "").lower())
            if not signature_ok:
                # Log anyway
                ing = LeadWebhookIngestion(
                    tenant_id=cfg["tenant_id"], config_id=cfg["_id"], source=cfg["source"],
                    signature_ok=False, payload_raw={}, error="Firma non valida", processed=False,
                )
                await db.lead_webhook_ingestions.insert_one(to_mongo(ing.model_dump(by_alias=True)))
                raise HTTPException(status_code=401, detail="Firma non valida")

    import json as _json
    try:
        payload = _json.loads(body.decode()) if body else {}
    except Exception:
        raise HTTPException(status_code=400, detail="Body JSON non valido")
    tenant_id = cfg["tenant_id"]

    # Apply mapping
    mapping = cfg.get("field_mapping") or {}
    def _mp(k, default=None):
        if k in mapping:
            return payload.get(mapping[k])
        return payload.get(k, default)
    normalized = {
        "first_name": _mp("first_name"), "last_name": _mp("last_name"),
        "full_name": _mp("full_name"),
        "phone": _mp("phone"), "email": _mp("email"),
        "city": _mp("city"), "province": _mp("province"), "zip_code": _mp("zip_code"),
        "product_of_interest": _mp("product_of_interest"),
        "message": _mp("message"), "campaign": _mp("campaign") or cfg.get("campaign"),
        "form_id": _mp("form_id") or cfg.get("form_id"),
        "social_profile_id": _mp("social_profile_id") or _mp("leadgen_id"),
        "consent_marketing": _mp("consent_marketing") if _mp("consent_marketing") is not None else cfg.get("consent_marketing_default"),
        "consent_contact": _mp("consent_contact", True),
    }
    dedup_key = await _dedup_lead_key(tenant_id, cfg["source"], normalized)
    payload_hash = hashlib.sha256(body).hexdigest()

    ing = LeadWebhookIngestion(
        tenant_id=tenant_id, config_id=cfg["_id"], source=cfg["source"],
        signature_ok=signature_ok, payload_raw=payload, payload_hash=payload_hash,
        dedup_key=dedup_key,
    )

    existing = await db.leads.find_one({"tenant_id": tenant_id, "dedup_key": dedup_key, "deleted_at": None})
    if existing:
        ing.dedup_hit = True
        ing.lead_id = existing["_id"]
        ing.processed = True
        # log timeline event
        await log_timeline_event(
            tenant_id=tenant_id, domain="lead", event_type="lead.duplicate_received",
            ref_id=existing["_id"], customer_id=existing.get("customer_id"),
            source="webhook", payload={"source": cfg["source"], "config": cfg["_id"]},
        )
        await db.lead_webhook_configs.update_one(
            {"_id": cfg["_id"]},
            {"$inc": {"total_received": 1, "total_duplicates": 1},
             "$set": {"last_received_at": utcnow().isoformat()}},
        )
        await db.lead_webhook_ingestions.insert_one(to_mongo(ing.model_dump(by_alias=True)))
        return {"ok": True, "duplicate": True, "lead_id": existing["_id"]}

    # Crea lead
    fn = normalized.get("first_name") or (normalized.get("full_name") or "").split(" ")[0]
    ln = normalized.get("last_name") or " ".join((normalized.get("full_name") or "").split(" ")[1:]) or None
    lead_doc = {
        "_id": new_id(), "tenant_id": tenant_id,
        "first_name": fn, "last_name": ln,
        "phone": _normalize_phone(normalized.get("phone", "")),
        "email": (normalized.get("email") or "").lower(),
        "address": {"city": normalized.get("city"), "province": normalized.get("province"),
                     "zip": normalized.get("zip_code")},
        "product_interest": normalized.get("product_of_interest"),
        "notes": normalized.get("message"),
        "source": cfg["source"], "campaign": normalized.get("campaign"),
        "form_id": normalized.get("form_id"), "ad_id": normalized.get("ad_id"),
        "social_profile_id": normalized.get("social_profile_id"),
        "dedup_key": dedup_key,
        "lead_status": "new",
        "created_at": utcnow().isoformat(), "updated_at": utcnow().isoformat(),
        "deleted_at": None,
    }
    await db.leads.insert_one(lead_doc)
    # Consents
    if normalized.get("consent_marketing"):
        c = Consent(tenant_id=tenant_id, lead_id=lead_doc["_id"], kind="marketing", granted=True,
                     source=cfg["source"])
        await db.consents.insert_one(to_mongo(c.model_dump(by_alias=True)))
    c = Consent(tenant_id=tenant_id, lead_id=lead_doc["_id"], kind="contact",
                 granted=bool(normalized.get("consent_contact", True)), source=cfg["source"])
    await db.consents.insert_one(to_mongo(c.model_dump(by_alias=True)))

    # Auto handoff a lead_generation
    ho_id = await create_handoff(
        tenant_id=tenant_id, actor_user_id=None,
        payload={
            "to_area": cfg.get("autoassign_area") or "lead_generation",
            "lead_id": lead_doc["_id"],
            "priority": "high",
            "subject_label": f"Nuovo lead: {fn} {ln or ''}".strip(),
            "action_required": "Contatto entro 15 minuti",
            "idempotency_key": f"lead:{lead_doc['_id']}:intake",
        },
    )
    ing.lead_id = lead_doc["_id"]
    ing.processed = True
    await db.lead_webhook_ingestions.insert_one(to_mongo(ing.model_dump(by_alias=True)))
    await db.lead_webhook_configs.update_one(
        {"_id": cfg["_id"]}, {"$inc": {"total_received": 1},
                              "$set": {"last_received_at": utcnow().isoformat()}},
    )
    await log_timeline_event(
        tenant_id=tenant_id, domain="lead", event_type="lead.created",
        ref_id=lead_doc["_id"], source="webhook",
        payload={"source": cfg["source"], "campaign": normalized.get("campaign")},
    )
    return {"ok": True, "lead_id": lead_doc["_id"], "handoff_id": ho_id}


# =====================================================================
# LEAD WEBHOOK CONFIGS (admin)
# =====================================================================
@router.get("/lead-webhooks")
async def list_webhook_configs(user: dict = Depends(require_permission("*"))):
    return await list_docs(collection="lead_webhook_configs", tenant_id=user["tenant_id"], limit=100)


@router.post("/lead-webhooks")
async def create_webhook_config(payload: LeadWebhookConfigCreate, user: dict = Depends(require_permission("*"))):
    inst = LeadWebhookConfig(**payload.model_dump())
    return await create_doc(collection="lead_webhook_configs", model_instance=inst, user=user,
                             entity_type="lead_webhook_config", ip="")


@router.get("/lead-webhook-ingestions")
async def list_webhook_ingestions(user: dict = Depends(require_permission("*")), limit: int = 100):
    return await list_docs(collection="lead_webhook_ingestions", tenant_id=user["tenant_id"],
                            sort=[("ingested_at", -1)], limit=limit)


# =====================================================================
# INBOX (conversations + messages)
# =====================================================================
@router.get("/inbox/conversations")
async def list_conversations(
    channel_kind: Optional[str] = None,
    assigned_user_id: Optional[str] = None,
    conv_status: Optional[str] = "open",
    user: dict = Depends(get_current_user), limit: int = 100,
):
    filters = {}
    if channel_kind: filters["channel_kind"] = channel_kind
    if conv_status: filters["conv_status"] = conv_status
    if assigned_user_id == "me":
        filters["assigned_user_id"] = user["id"]
    return await list_docs(collection="conversations", tenant_id=user["tenant_id"], filters=filters,
                            sort=[("last_message_at", -1)], limit=limit)


@router.get("/inbox/conversations/{cid}/messages")
async def list_messages(cid: str, user: dict = Depends(get_current_user), limit: int = 100):
    return await list_docs(collection="messages", tenant_id=user["tenant_id"],
                            filters={"conversation_id": cid}, sort=[("created_at", 1)], limit=limit)


@router.post("/inbox/send")
async def send_message(payload: SendMessageRequest, user: dict = Depends(get_current_user)):
    """Invia messaggio outbound. Provider: mock nel dev."""
    db = get_db()
    conv = await db.conversations.find_one({"_id": payload.conversation_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversazione non trovata")
    # Applicare template se richiesto
    body = payload.body
    if payload.template_id:
        tpl = await db.message_templates.find_one({"_id": payload.template_id, "tenant_id": user["tenant_id"]})
        if tpl:
            body = tpl.get("body") or body
            for k, v in (payload.template_variables or {}).items():
                body = body.replace(f"{{{{ {k} }}}}", str(v)).replace(f"{{{{{k}}}}}", str(v))
    msg = Message(
        tenant_id=user["tenant_id"], conversation_id=payload.conversation_id,
        channel_id=conv["channel_id"], direction="outbound",
        body=body[:8000], template_id=payload.template_id,
        template_variables=payload.template_variables,
        attachments=payload.attachments, sent_by=user["id"],
        msg_status="sent", sent_at=utcnow(),
    )
    await db.messages.insert_one(to_mongo(msg.model_dump(by_alias=True)))
    await db.conversations.update_one({"_id": conv["_id"]},
        {"$set": {"last_message_at": utcnow().isoformat(), "last_message_preview": body[:200]}},
    )
    return msg.model_dump()


# =====================================================================
# TEMPLATES
# =====================================================================
@router.get("/message-templates")
async def list_templates(kind: Optional[str] = None, user: dict = Depends(get_current_user)):
    filters = {}
    if kind: filters["kind"] = kind
    return await list_docs(collection="message_templates", tenant_id=user["tenant_id"], filters=filters, limit=100)


@router.post("/message-templates")
async def create_template(payload: MessageTemplateCreate, user: dict = Depends(require_permission("*"))):
    inst = MessageTemplate(**payload.model_dump())
    return await create_doc(collection="message_templates", model_instance=inst, user=user,
                             entity_type="message_template", ip="")


@router.patch("/message-templates/{tid}")
async def update_template(tid: str, payload: MessageTemplateUpdate, user: dict = Depends(require_permission("*"))):
    return await update_doc(collection="message_templates", doc_id=tid,
                             updates=payload.model_dump(exclude_unset=True), user=user,
                             entity_type="message_template", ip="")


# =====================================================================
# EMAIL AUTOMATIONS
# =====================================================================
@router.get("/email-automations")
async def list_automations(user: dict = Depends(get_current_user)):
    return await list_docs(collection="email_automations", tenant_id=user["tenant_id"], limit=100)


@router.post("/email-automations")
async def create_automation(payload: EmailAutomationCreate, user: dict = Depends(require_permission("*"))):
    inst = EmailAutomation(**payload.model_dump())
    return await create_doc(collection="email_automations", model_instance=inst, user=user,
                             entity_type="email_automation", ip="")


@router.patch("/email-automations/{aid}")
async def update_automation(aid: str, payload: EmailAutomationUpdate, user: dict = Depends(require_permission("*"))):
    return await update_doc(collection="email_automations", doc_id=aid,
                             updates=payload.model_dump(exclude_unset=True), user=user,
                             entity_type="email_automation", ip="")


# =====================================================================
# CONSENTS
# =====================================================================
@router.get("/consents")
async def list_consents(customer_id: Optional[str] = None, lead_id: Optional[str] = None,
                         user: dict = Depends(get_current_user)):
    filters = {}
    if customer_id: filters["customer_id"] = customer_id
    if lead_id: filters["lead_id"] = lead_id
    return await list_docs(collection="consents", tenant_id=user["tenant_id"],
                            filters=filters, sort=[("created_at", -1)], limit=200)


@router.post("/consents")
async def create_consent(payload: ConsentCreate, request: Request, user: dict = Depends(get_current_user)):
    inst = Consent(tenant_id=user["tenant_id"], **payload.model_dump())
    doc = to_mongo(inst.model_dump(by_alias=True))
    db = get_db()
    await db.consents.insert_one(doc)
    return inst.model_dump()


@router.post("/consents/{cid}/revoke")
async def revoke_consent(cid: str, payload: dict, user: dict = Depends(get_current_user)):
    db = get_db()
    await db.consents.update_one(
        {"_id": cid, "tenant_id": user["tenant_id"]},
        {"$set": {"granted": False, "revoked_at": utcnow().isoformat(),
                   "revoke_reason": payload.get("reason")}},
    )
    return {"ok": True}
