"""M17 — AI CFO: prudent, data-only, explainable suggestions.

Rules:
- Every suggestion cites its data sources, computed metrics, period, confidence.
- No free-text hallucinations — this module DOES NOT call an LLM.
  All outputs are computed by rule-based analytics over real tenant data.
- AI CFO can PROPOSE but never AUTO-EXECUTE (payments, price changes, approvals).
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.db import get_db
from app.deps import require_permission
from app.models_ops import AICFOSuggestion
from app.models import new_id
from app.mongo_utils import to_mongo, from_mongo

router = APIRouter(prefix="/ai-cfo", tags=["ai-cfo"])


def _now() -> datetime: return datetime.now(timezone.utc)
def _today() -> date: return _now().date()


async def _cash_flow_next30(tenant: str, db) -> Dict[str, Any]:
    """Predict expected inflows next 30 days from installments with due_date."""
    end = (_today() + timedelta(days=30)).isoformat()
    today = _today().isoformat()
    expected_in = 0.0
    overdue_amount = 0.0
    async for pl in db.payment_plans.find({"tenant_id": tenant, "plan_status": "active"}):
        for inst in pl.get("installments", []):
            if inst.get("installment_status") == "paid": continue
            due = inst.get("due_date")
            outstanding = (inst.get("amount") or 0) - (inst.get("paid_amount") or 0)
            if not due:
                continue
            due_str = str(due)
            if due_str <= end and due_str >= today:
                expected_in += outstanding
            elif due_str < today:
                overdue_amount += outstanding
    return {"expected_in_next_30d": round(expected_in, 2), "current_overdue": round(overdue_amount, 2)}


async def _receivables_at_risk(tenant: str, db) -> Dict[str, Any]:
    """Customers with overdue installments > 30 days."""
    thirty_days_ago = (_today() - timedelta(days=30)).isoformat()
    risky_customers = []
    async for pl in db.payment_plans.find({"tenant_id": tenant, "plan_status": "active", "outstanding_amount": {"$gt": 0}}):
        for inst in pl.get("installments", []):
            due = inst.get("due_date")
            if due and str(due) <= thirty_days_ago and inst.get("installment_status") != "paid":
                risky_customers.append({"customer_id": pl.get("customer_id"),
                                         "plan_id": pl.get("_id"),
                                         "overdue_amount": (inst.get("amount") or 0) - (inst.get("paid_amount") or 0),
                                         "due_date": due})
                break
    return {"count": len(risky_customers), "customers": risky_customers[:10]}


async def _quotes_conversion(tenant: str, db) -> Dict[str, Any]:
    """Rolling 90d quote conversion trend + suggestion if declining."""
    since_90 = (_now() - timedelta(days=90)).isoformat()
    since_180 = (_now() - timedelta(days=180)).isoformat()
    def_signed = {"quote_status": {"$in": ["signed", "converted"]}, "deleted_at": None, "tenant_id": tenant}
    def_sent = {"quote_status": {"$nin": ["draft", "to_approve"]}, "deleted_at": None, "tenant_id": tenant}
    def _add(dst, k, v): dst[k] = v
    s90 = await db.quotes.count_documents({**def_signed, "created_at": {"$gte": since_90}})
    t90 = await db.quotes.count_documents({**def_sent, "created_at": {"$gte": since_90}})
    s180 = await db.quotes.count_documents({**def_signed, "created_at": {"$gte": since_180, "$lt": since_90}})
    t180 = await db.quotes.count_documents({**def_sent, "created_at": {"$gte": since_180, "$lt": since_90}})
    r90 = round(s90 / t90 * 100, 1) if t90 else 0
    r180 = round(s180 / t180 * 100, 1) if t180 else 0
    return {"conversion_last_90d": r90, "conversion_prev_90d": r180, "delta_pp": round(r90 - r180, 1)}


class GenerateBody(BaseModel):
    force_regen: bool = False


@router.post("/generate")
async def generate_suggestions(body: GenerateBody,
                                user: dict = Depends(require_permission("ai_cfo.generate"))):
    db = get_db()
    tenant = user["tenant_id"]
    now = _now()

    # Compute base metrics
    cash = await _cash_flow_next30(tenant, db)
    recv = await _receivables_at_risk(tenant, db)
    conv = await _quotes_conversion(tenant, db)

    suggestions: List[AICFOSuggestion] = []

    # 1. Cash flow next 30 days
    if cash["expected_in_next_30d"] > 0 or cash["current_overdue"] > 0:
        s = AICFOSuggestion(
            id=new_id(), tenant_id=tenant,
            period_from=_today(), period_to=_today() + timedelta(days=30),
            category="cash_flow",
            title=f"Incassi previsti nei prossimi 30 giorni: € {cash['expected_in_next_30d']:.0f}",
            body=(f"In base alle rate configurate, si prevedono incassi per €{cash['expected_in_next_30d']:.2f}. "
                  f"Sono già in stato scaduto €{cash['current_overdue']:.2f}. "
                  f"Fonte: piano pagamenti attivi con due_date valorizzato."),
            action_suggested="Verifica gli scaduti; invia solleciti sui piani con importo residuo > 0.",
            confidence=0.85, risk_level="medium" if cash["current_overdue"] > 0 else "low",
            data_sources=["payment_plans", "payments"],
            computed_metrics=cash, generated_at=now,
        )
        suggestions.append(s)

    # 2. Receivables at risk
    if recv["count"] > 0:
        s = AICFOSuggestion(
            id=new_id(), tenant_id=tenant,
            period_from=_today() - timedelta(days=90), period_to=_today(),
            category="receivables",
            title=f"{recv['count']} cliente/i con scaduti > 30 giorni",
            body=("Individuati clienti con rate scadute da oltre 30 giorni e piano pagamenti ancora attivo. "
                  "Fonte: piani pagamenti con installments.due_date < oggi - 30gg e installment_status != 'paid'."),
            action_suggested="Contatta i clienti evidenziati; considera piani di rientro o azioni di recupero.",
            confidence=0.9, risk_level="high",
            data_sources=["payment_plans"], computed_metrics=recv, generated_at=now,
        )
        suggestions.append(s)

    # 3. Quotes conversion
    if conv["delta_pp"] < -5:
        s = AICFOSuggestion(
            id=new_id(), tenant_id=tenant,
            period_from=_today() - timedelta(days=180), period_to=_today(),
            category="risk",
            title=f"Calo del tasso di conversione preventivi ({conv['delta_pp']} punti percentuali)",
            body=(f"Il tasso di conversione degli ultimi 90 giorni è {conv['conversion_last_90d']}%, "
                  f"contro {conv['conversion_prev_90d']}% dei 90 giorni precedenti. "
                  f"Fonte: aggregazione preventivi con quote_status."),
            action_suggested="Analizza i motivi di rifiuto recenti e verifica listini/margini con la Direzione Commerciale.",
            confidence=0.7, risk_level="medium",
            data_sources=["quotes"], computed_metrics=conv, generated_at=now,
        )
        suggestions.append(s)

    # Persist
    if not body.force_regen:
        # Invalidate previous non-dismissed
        await db.ai_cfo_suggestions.update_many(
            {"tenant_id": tenant, "is_dismissed": False},
            {"$set": {"is_dismissed": True, "dismissed_at": now.isoformat(),
                       "dismissed_by": "system_regeneration"}},
        )
    for s in suggestions:
        s.tenant_id = tenant
        s.created_by = user["id"]; s.updated_by = user["id"]
        await db.ai_cfo_suggestions.insert_one(to_mongo(s.model_dump(by_alias=True)))

    return {"generated": len(suggestions), "items": [from_mongo(await db.ai_cfo_suggestions.find_one({"_id": s.id})) for s in suggestions]}


@router.get("/suggestions")
async def list_suggestions(include_dismissed: bool = False,
                            user: dict = Depends(require_permission("ai_cfo.view"))):
    db = get_db()
    q: Dict[str, Any] = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if not include_dismissed: q["is_dismissed"] = False
    docs = await db.ai_cfo_suggestions.find(q).sort("generated_at", -1).limit(50).to_list(50)
    return {"items": [from_mongo(d) for d in docs]}


@router.post("/suggestions/{sid}/dismiss")
async def dismiss_suggestion(sid: str,
                              user: dict = Depends(require_permission("ai_cfo.view"))):
    db = get_db()
    r = await db.ai_cfo_suggestions.update_one(
        {"_id": sid, "tenant_id": user["tenant_id"]},
        {"$set": {"is_dismissed": True,
                   "dismissed_at": datetime.now(timezone.utc).isoformat(),
                   "dismissed_by": user["id"]}},
    )
    if r.modified_count == 0:
        return {"ok": False}
    return {"ok": True}
