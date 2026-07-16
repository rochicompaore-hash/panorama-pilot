"""M3.3.5 + M16 — Business Intelligence dashboards (real-time aggregation).

All endpoints strictly enforce tenant isolation.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends
from app.db import get_db
from app.deps import require_permission

router = APIRouter(prefix="/bi", tags=["business-intelligence"])


def _now(): return datetime.now(timezone.utc)


@router.get("/quotes/kpi")
async def quotes_kpi(period_days: int = 90,
                      user: dict = Depends(require_permission("quotes.view"))):
    """M3.3.5 — KPI preventivi."""
    db = get_db()
    tenant = user["tenant_id"]
    since = (_now() - timedelta(days=period_days)).isoformat()
    q_base = {"tenant_id": tenant, "deleted_at": None, "created_at": {"$gte": since}}

    counts: Dict[str, int] = {}
    for st in ["draft", "to_approve", "approved", "sent", "viewed", "negotiating",
                "accepted", "signed", "rejected", "change_requested", "converted", "expired", "cancelled"]:
        counts[st] = await db.quotes.count_documents({**q_base, "quote_status": st})

    total_created = await db.quotes.count_documents(q_base)

    # Aggregate totals for various states
    async def _sum_total(match: dict) -> float:
        pipeline = [{"$match": match}, {"$group": {"_id": None, "total": {"$sum": "$total"}}}]
        res = await db.quotes.aggregate(pipeline).to_list(1)
        return round(res[0]["total"], 2) if res else 0.0

    value_created = await _sum_total(q_base)
    value_signed = await _sum_total({**q_base, "quote_status": {"$in": ["signed", "converted"]}})
    value_sent = await _sum_total({**q_base, "quote_status": {"$in": ["sent", "viewed", "negotiating"]}})

    # Conversion: signed / sent
    total_sent = counts.get("sent", 0) + counts.get("viewed", 0) + counts.get("negotiating", 0) + \
                 counts.get("accepted", 0) + counts.get("signed", 0) + counts.get("rejected", 0) + \
                 counts.get("change_requested", 0) + counts.get("converted", 0)
    signed_total = counts.get("signed", 0) + counts.get("converted", 0)
    conversion_rate = round(signed_total / total_sent * 100, 1) if total_sent else 0

    # Weighted pipeline: 20% for sent, 40% for viewed, 60% for negotiating, 100% for signed
    weights = {"sent": 0.2, "viewed": 0.4, "negotiating": 0.6, "accepted": 0.9, "signed": 1.0, "converted": 1.0}
    weighted_value = 0.0
    for st, w in weights.items():
        s = await _sum_total({**q_base, "quote_status": st})
        weighted_value += s * w

    # Avg time to first view (viewed_at - sent at proxy)
    times_open = []
    async for q in db.quotes.find({**q_base, "viewed_at": {"$ne": None}}, {"created_at": 1, "viewed_at": 1}):
        try:
            c = q.get("created_at"); v = q.get("viewed_at")
            if isinstance(c, str): c = datetime.fromisoformat(c.replace("Z", "+00:00"))
            if isinstance(v, str): v = datetime.fromisoformat(v.replace("Z", "+00:00"))
            times_open.append((v - c).total_seconds() / 3600.0)
        except Exception:
            continue
    avg_hours_to_open = round(sum(times_open) / len(times_open), 1) if times_open else 0

    # Avg time to sign
    times_sign = []
    async for q in db.quotes.find({**q_base, "signed_at": {"$ne": None}}, {"created_at": 1, "signed_at": 1}):
        try:
            c = q.get("created_at"); s = q.get("signed_at")
            if isinstance(c, str): c = datetime.fromisoformat(c.replace("Z", "+00:00"))
            if isinstance(s, str): s = datetime.fromisoformat(s.replace("Z", "+00:00"))
            times_sign.append((s - c).total_seconds() / 3600.0)
        except Exception:
            continue
    avg_hours_to_sign = round(sum(times_sign) / len(times_sign), 1) if times_sign else 0

    # Quotes never viewed
    never_viewed = await db.quotes.count_documents({**q_base, "quote_status": "sent", "viewed_at": None})
    # Quotes expiring in next 7 days
    exp_from = _now().isoformat()
    exp_to = (_now() + timedelta(days=7)).isoformat()
    expiring = await db.quotes.count_documents({**q_base, "valid_until": {"$gte": exp_from, "$lte": exp_to},
                                                 "quote_status": {"$in": ["sent", "viewed", "negotiating"]}})

    # Rejection reasons
    rejection_reasons = []
    pipeline = [{"$match": {"tenant_id": tenant, "kind": "rejection", "deleted_at": None,
                             "created_at": {"$gte": since}}},
                {"$group": {"_id": "$reason_code", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}]
    async for row in db.customer_requests.aggregate(pipeline):
        rejection_reasons.append({"reason_code": row["_id"] or "not_specified", "count": row["count"]})

    return {
        "period_days": period_days,
        "counts_by_status": counts,
        "total_created": total_created,
        "value_created": value_created,
        "value_signed": value_signed,
        "value_sent_active": value_sent,
        "weighted_pipeline_value": round(weighted_value, 2),
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
