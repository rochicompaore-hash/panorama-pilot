"""M3.3.5 + M16 — Business Intelligence dashboards (real-time aggregation).

All endpoints strictly enforce tenant isolation.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from fastapi import APIRouter, Depends
from app.db import get_db
from app.deps import require_permission

router = APIRouter(prefix="/bi", tags=["business-intelligence"])


def _now(): return datetime.now(timezone.utc)


# --------------------------------------------------------------------
# Small helpers — keep quotes_kpi below linear & readable
# --------------------------------------------------------------------
QUOTE_STATUSES: Tuple[str, ...] = (
    "draft", "to_approve", "approved", "sent", "viewed", "negotiating",
    "accepted", "signed", "rejected", "change_requested", "converted",
    "expired", "cancelled",
)


async def _sum_total(db, match: dict) -> float:
    pipeline = [{"$match": match}, {"$group": {"_id": None, "total": {"$sum": "$total"}}}]
    res = await db.quotes.aggregate(pipeline).to_list(1)
    return round(res[0]["total"], 2) if res else 0.0


async def _avg_hours_between(db, q_base: dict, from_field: str, to_field: str) -> float:
    hours: List[float] = []
    async for q in db.quotes.find(
        {**q_base, to_field: {"$ne": None}},
        {from_field: 1, to_field: 1},
    ):
        c = q.get(from_field)
        v = q.get(to_field)
        if isinstance(c, str):
            try:
                c = datetime.fromisoformat(c.replace("Z", "+00:00"))
            except ValueError:
                continue
        if isinstance(v, str):
            try:
                v = datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                continue
        if not c or not v:
            continue
        hours.append((v - c).total_seconds() / 3600.0)
    return round(sum(hours) / len(hours), 1) if hours else 0.0


def _pipeline_conversion_rate(counts: Dict[str, int]) -> float:
    total_sent = sum(
        counts.get(k, 0) for k in
        ("sent", "viewed", "negotiating", "accepted", "signed",
         "rejected", "change_requested", "converted")
    )
    signed_total = counts.get("signed", 0) + counts.get("converted", 0)
    return round(signed_total / total_sent * 100, 1) if total_sent else 0.0


async def _pipeline_weighted_value(db, q_base: dict) -> float:
    weights = {"sent": 0.2, "viewed": 0.4, "negotiating": 0.6,
               "accepted": 0.9, "signed": 1.0, "converted": 1.0}
    total = 0.0
    for st, w in weights.items():
        s = await _sum_total(db, {**q_base, "quote_status": st})
        total += s * w
    return round(total, 2)


async def _rejection_reasons(db, tenant: str, since_iso: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    pipeline = [
        {"$match": {"tenant_id": tenant, "kind": "rejection",
                     "deleted_at": None, "created_at": {"$gte": since_iso}}},
        {"$group": {"_id": "$reason_code", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    async for row in db.customer_requests.aggregate(pipeline):
        out.append({"reason_code": row["_id"] or "not_specified", "count": row["count"]})
    return out


@router.get("/quotes/kpi")
async def quotes_kpi(period_days: int = 90,
                      user: dict = Depends(require_permission("quotes.view"))):
    """M3.3.5 — KPI preventivi."""
    db = get_db()
    tenant = user["tenant_id"]
    since = (_now() - timedelta(days=period_days)).isoformat()
    q_base = {"tenant_id": tenant, "deleted_at": None, "created_at": {"$gte": since}}

    counts: Dict[str, int] = {}
    for st in QUOTE_STATUSES:
        counts[st] = await db.quotes.count_documents({**q_base, "quote_status": st})

    total_created = await db.quotes.count_documents(q_base)
    value_created = await _sum_total(db, q_base)
    value_signed = await _sum_total(
        db, {**q_base, "quote_status": {"$in": ["signed", "converted"]}}
    )
    value_sent = await _sum_total(
        db, {**q_base, "quote_status": {"$in": ["sent", "viewed", "negotiating"]}}
    )
    conversion_rate = _pipeline_conversion_rate(counts)
    weighted_value = await _pipeline_weighted_value(db, q_base)
    avg_hours_to_open = await _avg_hours_between(db, q_base, "created_at", "viewed_at")
    avg_hours_to_sign = await _avg_hours_between(db, q_base, "created_at", "signed_at")

    never_viewed = await db.quotes.count_documents(
        {**q_base, "quote_status": "sent", "viewed_at": None}
    )
    exp_from = _now().isoformat()
    exp_to = (_now() + timedelta(days=7)).isoformat()
    expiring = await db.quotes.count_documents({
        **q_base, "valid_until": {"$gte": exp_from, "$lte": exp_to},
        "quote_status": {"$in": ["sent", "viewed", "negotiating"]},
    })
    rejection_reasons = await _rejection_reasons(db, tenant, since)

    return {
        "period_days": period_days,
        "counts_by_status": counts,
        "total_created": total_created,
        "value_created": value_created,
        "value_signed": value_signed,
        "value_sent_active": value_sent,
        "weighted_pipeline_value": weighted_value,
        "conversion_rate_pct": conversion_rate,
        "avg_hours_to_first_open": avg_hours_to_open,
        "avg_hours_to_sign": avg_hours_to_sign,
        "quotes_never_viewed": never_viewed,
        "quotes_expiring_7d": expiring,
        "rejection_reasons": rejection_reasons,
    }


@router.get("/direction/kpi")
async def direction_kpi(user: dict = Depends(require_permission("bi.direction.view"))):
    db = get_db()
    tenant = user["tenant_id"]
    return {
        "leads_total": await db.leads.count_documents({"tenant_id": tenant, "deleted_at": None}),
        "customers_total": await db.customers.count_documents({"tenant_id": tenant, "deleted_at": None}),
        "quotes_open": await db.quotes.count_documents({"tenant_id": tenant, "deleted_at": None,
            "quote_status": {"$in": ["sent", "viewed", "negotiating", "accepted"]}}),
        "quotes_signed": await db.quotes.count_documents({"tenant_id": tenant, "deleted_at": None,
            "quote_status": {"$in": ["signed", "converted"]}}),
        "contracts_active": await db.contracts.count_documents({"tenant_id": tenant, "deleted_at": None}),
        "sales_orders_open": await db.sales_orders.count_documents({"tenant_id": tenant, "deleted_at": None,
            "order_status": {"$nin": ["closed", "cancelled"]}}),
        "production_orders_wip": await db.production_orders.count_documents({"tenant_id": tenant,
            "prod_status": {"$in": ["in_progress", "released", "waiting_materials", "scheduled"]}}),
        "installations_scheduled": await db.installation_plans.count_documents({"tenant_id": tenant,
            "plan_status": {"$in": ["proposed", "customer_confirmed", "scheduled"]}}),
        "service_tickets_open": await db.service_tickets.count_documents({"tenant_id": tenant,
            "ticket_status": {"$nin": ["closed", "rejected"]}}),
    }
