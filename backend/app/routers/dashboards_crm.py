"""Role-specific dashboards."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from app.db import get_db
from app.deps import require_permission, require_any_permission, get_current_user, get_permission_keys_for_user
from app.mongo_utils import from_mongo

router = APIRouter(prefix="/dashboard-crm", tags=["dashboards"])


def _month_range():
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start.isoformat(), now.isoformat()


@router.get("/variant")
async def variant(user: dict = Depends(get_current_user)):
    """Return which dashboard variant is best for this user based on permissions."""
    perms = set(await get_permission_keys_for_user(user))
    is_admin = user.get("is_superadmin") or "*" in perms
    variant = "core"
    if is_admin:
        variant = "direction"
    elif "crm.leads.view" in perms:
        variant = "sales"
    elif "workflow.change_status" in perms and "crm.leads.view" not in perms:
        variant = "production"
    return {"variant": variant, "is_admin": is_admin}


@router.get("/sales")
async def sales_dashboard(user: dict = Depends(require_permission("crm.leads.view"))):
    db = get_db()
    tenant = user["tenant_id"]
    now = datetime.now(timezone.utc)
    start_month, _ = _month_range()

    my_leads_open = await db.leads.count_documents({"tenant_id": tenant, "assigned_to": user["id"], "lifecycle": "lead", "deleted_at": None, "won_at": None, "lost_at": None})
    my_leads_won_month = await db.leads.count_documents({"tenant_id": tenant, "assigned_to": user["id"], "won_at": {"$gte": start_month}})
    my_appointments_today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    my_appointments_today_end = (now.replace(hour=23, minute=59, second=59)).isoformat()
    my_appointments_today = await db.appointments.count_documents({
        "tenant_id": tenant, "attendees": user["id"], "deleted_at": None,
        "start_at": {"$gte": my_appointments_today_start, "$lte": my_appointments_today_end},
    })
    my_tasks_open = await db.tasks.count_documents({"tenant_id": tenant, "assigned_to": user["id"], "task_status": {"$ne": "done"}, "deleted_at": None})
    overdue_tasks = await db.tasks.count_documents({
        "tenant_id": tenant, "assigned_to": user["id"], "task_status": {"$ne": "done"},
        "due_at": {"$lt": now.isoformat()}, "deleted_at": None,
    })

    # potential value of open pipeline (weighted)
    open_leads = await db.leads.find({"tenant_id": tenant, "assigned_to": user["id"], "lifecycle": "lead",
                                       "deleted_at": None, "won_at": None, "lost_at": None}).to_list(500)
    weighted_value = sum((l.get("estimated_value", 0) or 0) * ((l.get("probability", 0) or 0) / 100) for l in open_leads)
    total_potential = sum((l.get("estimated_value", 0) or 0) for l in open_leads)

    # my goals (current month)
    my_goals = await db.goals.find({"tenant_id": tenant, "user_id": user["id"],
                                     "period_start": {"$lte": now.isoformat()},
                                     "period_end": {"$gte": now.isoformat()}}).to_list(20)

    # recent activities (my)
    recent = await db.activities.find({"tenant_id": tenant, "created_by": user["id"]}).sort("occurred_at", -1).limit(8).to_list(8)

    # next actions: leads assigned to me that need contact soon
    todo = await db.leads.find({"tenant_id": tenant, "assigned_to": user["id"], "lifecycle": "lead",
                                 "deleted_at": None, "won_at": None, "lost_at": None}).sort("last_activity_at", 1).limit(6).to_list(6)

    return {
        "variant": "sales",
        "counters": {
            "leads_open": my_leads_open,
            "leads_won_month": my_leads_won_month,
            "appointments_today": my_appointments_today,
            "tasks_open": my_tasks_open,
            "tasks_overdue": overdue_tasks,
            "weighted_pipeline_value": round(weighted_value, 2),
            "potential_pipeline_value": round(total_potential, 2),
        },
        "goals": [from_mongo(g) for g in my_goals],
        "recent_activities": [from_mongo(a) for a in recent],
        "next_actions": [from_mongo(l) for l in todo],
    }


@router.get("/direction")
async def direction_dashboard(user: dict = Depends(require_any_permission("crm.leads.view", "financials.view", "audit.view"))):
    db = get_db()
    tenant = user["tenant_id"]
    now = datetime.now(timezone.utc)
    start_month, _ = _month_range()
    start_7d = (now - timedelta(days=7)).isoformat()

    total_leads = await db.leads.count_documents({"tenant_id": tenant, "deleted_at": None})
    open_leads = await db.leads.count_documents({"tenant_id": tenant, "lifecycle": "lead", "deleted_at": None, "won_at": None, "lost_at": None})
    won_month = await db.leads.count_documents({"tenant_id": tenant, "won_at": {"$gte": start_month}})
    lost_month = await db.leads.count_documents({"tenant_id": tenant, "lost_at": {"$gte": start_month}})
    customers_total = await db.customers.count_documents({"tenant_id": tenant, "deleted_at": None})
    activities_7d = await db.activities.count_documents({"tenant_id": tenant, "occurred_at": {"$gte": start_7d}, "deleted_at": None})

    conv_rate = 0.0
    if (won_month + lost_month) > 0:
        conv_rate = round(100.0 * won_month / (won_month + lost_month), 1)

    # Sum of estimated values (open pipeline + wins this month)
    open_leads_docs = await db.leads.find({"tenant_id": tenant, "lifecycle": "lead",
                                            "deleted_at": None, "won_at": None, "lost_at": None}).to_list(1000)
    open_value = sum((l.get("estimated_value", 0) or 0) for l in open_leads_docs)
    weighted_value = sum((l.get("estimated_value", 0) or 0) * ((l.get("probability", 0) or 0) / 100) for l in open_leads_docs)
    won_month_docs = await db.leads.find({"tenant_id": tenant, "won_at": {"$gte": start_month}}).to_list(1000)
    won_value_month = sum((l.get("estimated_value", 0) or 0) for l in won_month_docs)

    # Top performers this month
    pipeline_agg = list(await db.leads.aggregate([
        {"$match": {"tenant_id": tenant, "won_at": {"$gte": start_month}}},
        {"$group": {"_id": "$assigned_to", "count": {"$sum": 1}, "value": {"$sum": "$estimated_value"}}},
        {"$sort": {"value": -1}}, {"$limit": 5},
    ]).to_list(5))
    user_ids = [p["_id"] for p in pipeline_agg if p.get("_id")]
    users = await db.users.find({"_id": {"$in": user_ids}}).to_list(len(user_ids)) if user_ids else []
    umap = {u["_id"]: u for u in users}
    top_performers = [{
        "user_id": p["_id"],
        "name": f'{umap.get(p["_id"],{}).get("first_name","")} {umap.get(p["_id"],{}).get("last_name","")}'.strip() or (umap.get(p["_id"],{}) or {}).get("email"),
        "won_count": p["count"], "won_value": round(p["value"], 2),
    } for p in pipeline_agg]

    # Stage breakdown from default pipeline
    default_pipe = await db.pipelines.find_one({"tenant_id": tenant, "is_default": True, "deleted_at": None})
    stage_breakdown = []
    if default_pipe:
        for s in default_pipe.get("stages", []):
            cnt = await db.leads.count_documents({"tenant_id": tenant, "pipeline_id": default_pipe["_id"], "stage_id": s["id"], "deleted_at": None})
            stage_breakdown.append({"stage": s["name"], "color": s.get("color"), "count": cnt})

    return {
        "variant": "direction",
        "counters": {
            "total_leads": total_leads, "open_leads": open_leads,
            "customers_total": customers_total,
            "won_month": won_month, "lost_month": lost_month,
            "conversion_rate_month": conv_rate,
            "activities_7d": activities_7d,
            "open_pipeline_value": round(open_value, 2),
            "weighted_pipeline_value": round(weighted_value, 2),
            "won_value_month": round(won_value_month, 2),
        },
        "top_performers": top_performers,
        "stage_breakdown": stage_breakdown,
    }


@router.get("/production")
async def production_dashboard(user: dict = Depends(get_current_user)):
    """Placeholder for M6 - counts basic for now."""
    db = get_db()
    tenant = user["tenant_id"]
    orders_placeholder = 0  # will be filled in M5+
    return {
        "variant": "production",
        "counters": {
            "orders_open": orders_placeholder, "delays": 0, "missing_materials": 0,
            "in_progress": 0,
        },
        "message": "Modulo produzione disponibile dalla Milestone 6",
    }


@router.get("/installer")
async def installer_dashboard(user: dict = Depends(get_current_user)):
    """Placeholder for M8. Shows today's appointments for current user."""
    db = get_db()
    tenant = user["tenant_id"]
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    day_end = now.replace(hour=23, minute=59, second=59).isoformat()
    today = await db.appointments.find({
        "tenant_id": tenant, "attendees": user["id"],
        "start_at": {"$gte": day_start, "$lte": day_end}, "deleted_at": None,
    }).sort("start_at", 1).to_list(30)
    return {
        "variant": "installer",
        "appointments_today": [from_mongo(a) for a in today],
        "counters": {"appointments_today": len(today)},
        "message": "Modulo posa completo dalla Milestone 8",
    }
