"""Handoff assignment engine + SLA + notification dispatch."""
from __future__ import annotations
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from app.db import get_db
from app.mongo_utils import to_mongo, from_mongo
from app.models import new_id, utcnow, Notification
from app.models_handoff import (
    OperationalHandoff, HandoffStatus, OperationalArea,
)
from app.services.workflow_engine import log_timeline_event

logger = logging.getLogger("infissi.handoff")


async def _select_users_for_group(tenant_id: str, group: Dict[str, Any]) -> List[str]:
    """Restituisce lista user_ids da notificare secondo strategia."""
    members = group.get("member_user_ids") or []
    subs = group.get("substitute_user_ids") or []
    leader = [group.get("leader_user_id")] if group.get("leader_user_id") else []
    strategy = group.get("assignment_strategy") or "round_robin"
    if strategy == "leader_first" and leader:
        return leader + [m for m in members if m not in leader]
    if strategy == "manual":
        return members[:1] if members else leader
    # round_robin: prendi il meno caricato (least_load semplificato)
    return members or leader or subs


async def resolve_assignment(
    *, tenant_id: str, to_area: str,
    province: Optional[str] = None, zip_code: Optional[str] = None,
    product_key: Optional[str] = None, source: Optional[str] = None,
    priority: str = "normal",
    preferred_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Trova gruppo + utenti da assegnare per una nuova pratica in `to_area`."""
    db = get_db()
    # 1. Cerca AssignmentRule matching priority ordinato
    filt = {"tenant_id": tenant_id, "area": to_area, "active": True, "deleted_at": None}
    rules = await db.assignment_rules.find(filt).sort("priority", 1).to_list(50)
    target_group_id: Optional[str] = None
    target_user_ids: List[str] = []
    for rule in rules:
        if rule.get("match_provinces") and province and province not in rule["match_provinces"]:
            continue
        if rule.get("match_zip_prefixes") and zip_code:
            if not any(zip_code.startswith(p) for p in rule["match_zip_prefixes"]):
                continue
        if rule.get("match_product_keys") and product_key and product_key not in rule["match_product_keys"]:
            continue
        if rule.get("match_source") and source and source not in rule["match_source"]:
            continue
        if rule.get("match_priority") and priority not in rule["match_priority"]:
            continue
        target_group_id = rule.get("target_group_id")
        if rule.get("target_user_id"):
            target_user_ids = [rule["target_user_id"]]
        break
    # 2. Fallback area default group
    if not target_group_id:
        area_cfg = await db.operational_area_configs.find_one({"tenant_id": tenant_id, "code": to_area})
        if area_cfg:
            target_group_id = area_cfg.get("default_group_id")
    if not target_group_id:
        # Prendi un qualunque gruppo attivo di quell'area
        grp = await db.user_groups.find_one({"tenant_id": tenant_id, "area": to_area, "active": True, "deleted_at": None})
        if grp:
            target_group_id = grp["_id"]
    if target_group_id and not target_user_ids:
        grp = await db.user_groups.find_one({"_id": target_group_id, "tenant_id": tenant_id})
        if grp:
            users = await _select_users_for_group(tenant_id, grp)
            target_user_ids = users
    if preferred_user_id and preferred_user_id not in target_user_ids:
        target_user_ids.insert(0, preferred_user_id)
    return {"group_id": target_group_id, "user_ids": target_user_ids or []}


async def create_handoff(
    *, tenant_id: str, actor_user_id: Optional[str], payload: Dict[str, Any],
) -> str:
    """Crea un OperationalHandoff con notifiche + timeline (idempotente su idempotency_key)."""
    db = get_db()
    idem = payload.get("idempotency_key")
    if idem:
        existing = await db.operational_handoffs.find_one({
            "tenant_id": tenant_id, "idempotency_key": idem, "deleted_at": None,
        })
        if existing:
            return existing["_id"]

    # Recupera provincia / product per assegnazione automatica
    province = None
    product_key = None
    source = None
    if payload.get("contract_id"):
        ctr = await db.contracts.find_one({"_id": payload["contract_id"], "tenant_id": tenant_id})
        if ctr:
            addr = (ctr.get("quote_snapshot") or {}).get("site_address") or {}
            province = addr.get("province")
    if payload.get("lead_id"):
        lead = await db.leads.find_one({"_id": payload["lead_id"], "tenant_id": tenant_id})
        if lead:
            addr = lead.get("address") or {}
            province = province or addr.get("province")
            source = lead.get("source")
    assigned_group_id = payload.get("assigned_group_id")
    assigned_user_ids = payload.get("assigned_user_ids") or []
    if not assigned_group_id and not assigned_user_ids:
        r = await resolve_assignment(
            tenant_id=tenant_id, to_area=payload["to_area"],
            province=province, product_key=product_key, source=source,
            priority=payload.get("priority", "normal"),
        )
        assigned_group_id = r["group_id"]
        assigned_user_ids = r["user_ids"]

    # Calcola due_at da SLA config
    due_at = payload.get("due_at")
    if not due_at:
        area_cfg = await db.operational_area_configs.find_one({"tenant_id": tenant_id, "code": payload["to_area"]})
        sla_min = (area_cfg or {}).get("sla_ack_minutes", 60)
        due_at = utcnow() + timedelta(minutes=int(sla_min))

    ho = OperationalHandoff(
        tenant_id=tenant_id,
        customer_id=payload.get("customer_id"),
        lead_id=payload.get("lead_id"),
        quote_id=payload.get("quote_id"),
        contract_id=payload.get("contract_id"),
        survey_id=payload.get("survey_id"),
        technical_schedule_id=payload.get("technical_schedule_id"),
        from_area=payload.get("from_area"),
        to_area=payload["to_area"],
        from_status=payload.get("from_status"),
        to_status=payload.get("to_status"),
        reason=payload.get("reason"),
        assigned_group_id=assigned_group_id,
        assigned_user_ids=assigned_user_ids,
        transferred_by=actor_user_id,
        transferred_at=utcnow(),
        due_at=due_at,
        priority=payload.get("priority", "normal"),
        notes=payload.get("notes"),
        handoff_status="pending",
        idempotency_key=idem,
        subject_label=payload.get("subject_label"),
        action_required=payload.get("action_required"),
    )
    doc = to_mongo(ho.model_dump(by_alias=True))
    await db.operational_handoffs.insert_one(doc)

    # Notifica ogni user assegnato (dedup per handoff+user+channel)
    channels_default = ["in_app", "email"]
    area_cfg = await db.operational_area_configs.find_one({"tenant_id": tenant_id, "code": payload["to_area"]})
    channels = (area_cfg or {}).get("notification_channels") or channels_default
    subject = payload.get("subject_label") or f"Nuova pratica in {payload['to_area']}"
    action = payload.get("action_required") or "Prendi in carico la pratica"
    body = (
        f"{subject} — passaggio da {payload.get('from_area') or 'sistema'} a {payload['to_area']}. "
        f"{action}. Scadenza: {due_at.strftime('%d/%m/%Y %H:%M') if isinstance(due_at, datetime) else due_at}."
    )
    link = None
    if ho.contract_id:
        link = f"/contracts/{ho.contract_id}"
    elif ho.quote_id:
        link = f"/quotes/{ho.quote_id}"
    elif ho.lead_id:
        link = f"/leads/{ho.lead_id}"

    sent_any = False
    for uid in assigned_user_ids:
        if "in_app" in channels:
            # Dedup by (handoff_id, user_id)
            dedup = f"handoff:{ho.id}:in_app:{uid}"
            dedup_hash = hashlib.sha256(dedup.encode()).hexdigest()[:24]
            already = await db.notifications.find_one({"tenant_id": tenant_id, "dedup_hash": dedup_hash})
            if not already:
                n = Notification(
                    tenant_id=tenant_id, user_id=uid, type="info",
                    title=subject, body=body, link=link,
                )
                nd = to_mongo(n.model_dump(by_alias=True))
                nd["dedup_hash"] = dedup_hash
                await db.notifications.insert_one(nd)
                sent_any = True

    # Timeline event
    ev_id = await log_timeline_event(
        tenant_id=tenant_id, domain="handoff", event_type=f"handoff.{payload['to_area']}",
        ref_id=ho.id, contract_id=ho.contract_id, customer_id=ho.customer_id,
        quote_id=ho.quote_id, survey_id=ho.survey_id,
        actor_id=actor_user_id, source="system",
        old_status=payload.get("from_status"), new_status=payload.get("to_status"),
        payload={"assigned_group_id": assigned_group_id, "user_count": len(assigned_user_ids)},
    )
    await db.operational_handoffs.update_one(
        {"_id": ho.id},
        {"$set": {
            "handoff_status": "notified" if sent_any else "pending",
            "notification_status": "sent" if sent_any else "pending",
            "notification_sent_at": utcnow().isoformat() if sent_any else None,
            "timeline_event_id": ev_id,
        }},
    )
    return ho.id


async def scan_overdue_handoffs(tenant_id: str) -> int:
    """Marca handoff scaduti come overdue. Ritorna quantità aggiornata."""
    db = get_db()
    now = utcnow()
    r = await db.operational_handoffs.update_many(
        {"tenant_id": tenant_id, "handoff_status": {"$in": ["pending", "notified"]},
         "due_at": {"$lt": now.isoformat()}, "deleted_at": None},
        {"$set": {"handoff_status": "overdue"}},
    )
    return r.modified_count
