"""Sales goals & commissions."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from app.db import get_db
from app.deps import require_permission
from app.models_crm import Goal, GoalCreate, GoalUpdate, CommissionRule, CommissionRuleCreate
from app.models import new_id
from app.mongo_utils import to_mongo, from_mongo

goals_router = APIRouter(prefix="/goals", tags=["goals"])
commissions_router = APIRouter(prefix="/commissions", tags=["commissions"])


# ---- Goals ----
@goals_router.get("")
async def list_goals(
    user_id: Optional[str] = None, mine: bool = False,
    user: dict = Depends(require_permission("crm.goals.view")),
):
    db = get_db()
    query: dict = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if mine:
        query["user_id"] = user["id"]
    elif user_id:
        query["user_id"] = user_id
    docs = await db.goals.find(query).sort("period_start", -1).limit(200).to_list(200)
    return {"items": [from_mongo(d) for d in docs]}


@goals_router.post("")
async def create_goal(body: GoalCreate, user: dict = Depends(require_permission("crm.goals.manage"))):
    db = get_db()
    g = Goal(
        id=new_id(), tenant_id=user["tenant_id"],
        user_id=body.user_id, period_type=body.period_type,
        period_start=body.period_start, period_end=body.period_end,
        metric=body.metric, target_value=body.target_value,
        created_by=user["id"], updated_by=user["id"],
    )
    await db.goals.insert_one(to_mongo(g.model_dump(by_alias=True)))
    return from_mongo(await db.goals.find_one({"_id": g.id}))


@goals_router.patch("/{gid}")
async def update_goal(gid: str, body: GoalUpdate, user: dict = Depends(require_permission("crm.goals.manage"))):
    db = get_db()
    payload = body.model_dump(exclude_unset=True)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload["updated_by"] = user["id"]
    await db.goals.update_one({"_id": gid, "tenant_id": user["tenant_id"]}, {"$set": payload})
    return from_mongo(await db.goals.find_one({"_id": gid}))


# ---- Commissions ----
@commissions_router.get("")
async def list_commissions(user: dict = Depends(require_permission("crm.commissions.view"))):
    db = get_db()
    docs = await db.commission_rules.find({"tenant_id": user["tenant_id"], "deleted_at": None}).sort("created_at", -1).to_list(200)
    return {"items": [from_mongo(d) for d in docs]}


@commissions_router.post("")
async def create_commission(body: CommissionRuleCreate, user: dict = Depends(require_permission("crm.commissions.manage"))):
    db = get_db()
    r = CommissionRule(
        id=new_id(), tenant_id=user["tenant_id"],
        name=body.name, user_id=body.user_id, role_id=body.role_id,
        base=body.base, percentage=body.percentage, threshold_min=body.threshold_min,
        created_by=user["id"], updated_by=user["id"],
    )
    await db.commission_rules.insert_one(to_mongo(r.model_dump(by_alias=True)))
    return from_mongo(await db.commission_rules.find_one({"_id": r.id}))
