"""Timeline / activity recorder. Never blocks main flow."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from app.db import get_db
from app.models_crm import Activity
from app.models import new_id
from app.mongo_utils import to_mongo


async def record_activity(
    *,
    tenant_id: str,
    type: str,
    subject: str,
    body: Optional[str] = None,
    direction: Optional[str] = None,
    outcome: Optional[str] = None,
    duration_seconds: Optional[int] = None,
    occurred_at: Optional[datetime] = None,
    lead_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    contact_id: Optional[str] = None,
    quote_id: Optional[str] = None,
    order_id: Optional[str] = None,
    assigned_to: Optional[str] = None,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> str:
    """Record an activity in the timeline. Returns activity id.
    Also bumps `last_activity_at` on the linked lead/customer.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    a = Activity(
        id=new_id(),
        tenant_id=tenant_id,
        type=type,
        subject=subject,
        body=body,
        direction=direction,
        outcome=outcome,
        duration_seconds=duration_seconds,
        occurred_at=occurred_at or now,
        lead_id=lead_id,
        customer_id=customer_id,
        contact_id=contact_id,
        quote_id=quote_id,
        order_id=order_id,
        assigned_to=assigned_to,
        created_by=user_id,
        updated_by=user_id,
        meta=meta or {},
    )
    doc = to_mongo(a.model_dump(by_alias=True))
    await db.activities.insert_one(doc)

    # Bump last_activity_at / last_contact_at on related lead / customer
    is_contact_event = type in ("call", "email", "whatsapp", "appointment_done")
    update = {"last_activity_at": now.isoformat()}
    if is_contact_event:
        update["last_contact_at"] = now.isoformat()

    if lead_id:
        await db.leads.update_one({"_id": lead_id, "tenant_id": tenant_id}, {"$set": update})
    if customer_id:
        await db.customers.update_one({"_id": customer_id, "tenant_id": tenant_id}, {"$set": update})
    return a.id


def suggest_next_action(lead: dict, stages_by_id: dict) -> dict:
    """Simple heuristics for next-action suggestion based on stage + last contact age."""
    stage = stages_by_id.get(lead.get("stage_id"))
    stage_name = (stage or {}).get("name", "").lower()
    now = datetime.now(timezone.utc)
    last_contact = lead.get("last_contact_at")
    if isinstance(last_contact, str):
        try:
            last_contact = datetime.fromisoformat(last_contact)
        except Exception:
            last_contact = None
    days_since = None
    if last_contact:
        days_since = (now - last_contact).days

    if lead.get("won_at") or lead.get("lost_at"):
        return {"action": "closed", "label": "Opportunità chiusa", "priority": "low", "days_since_contact": days_since}
    if not last_contact:
        return {"action": "first_call", "label": "Primo contatto entro 24 ore", "priority": "high", "days_since_contact": None}
    if days_since is not None and days_since > 14:
        return {"action": "reactivate", "label": f"Riattiva contatto (fermo da {days_since}g)", "priority": "high", "days_since_contact": days_since}
    if "nuovo" in stage_name:
        return {"action": "qualify", "label": "Qualifica il lead con una chiamata", "priority": "high", "days_since_contact": days_since}
    if "contattato" in stage_name:
        return {"action": "appointment", "label": "Fissa un appuntamento in cantiere", "priority": "high", "days_since_contact": days_since}
    if "qualificato" in stage_name or "trattativa" in stage_name:
        return {"action": "quote", "label": "Prepara/aggiorna il preventivo", "priority": "medium", "days_since_contact": days_since}
    if "preventivo" in stage_name:
        return {"action": "followup_quote", "label": "Follow-up sul preventivo inviato", "priority": "high", "days_since_contact": days_since}
    return {"action": "followup", "label": "Contatta il cliente", "priority": "medium", "days_since_contact": days_since}


def compute_lead_intelligence(lead: dict, stages_by_id: dict) -> dict:
    """Compute derived fields: days_since_contact, next_action_suggestion, probability_display."""
    next_action = suggest_next_action(lead, stages_by_id)
    stage = stages_by_id.get(lead.get("stage_id"))
    prob = lead.get("probability")
    if prob is None and stage:
        prob = stage.get("probability_default", 20)
    return {
        "next_action_suggestion": next_action,
        "probability_display": prob if prob is not None else 20,
        "days_since_contact": next_action.get("days_since_contact"),
    }
