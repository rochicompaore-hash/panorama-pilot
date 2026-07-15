"""Tasks router."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models_crm import Task, TaskCreate, TaskUpdate
from app.models import new_id
from app.mongo_utils import to_mongo, from_mongo
from app.services.audit import record_audit
from app.services.timeline import record_activity

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
async def list_tasks(
    assigned_to: Optional[str] = None, task_status: Optional[str] = None,
    lead_id: Optional[str] = None, customer_id: Optional[str] = None,
    mine: bool = False,
    limit: int = Query(200, le=500), skip: int = 0,
    user: dict = Depends(require_permission("crm.tasks.view")),
):
    db = get_db()
    query: dict = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if mine:
        query["assigned_to"] = user["id"]
    elif assigned_to:
        query["assigned_to"] = assigned_to
    if task_status:
        query["task_status"] = task_status
    if lead_id:
        query["lead_id"] = lead_id
    if customer_id:
        query["customer_id"] = customer_id
    total = await db.tasks.count_documents(query)
    docs = await db.tasks.find(query).sort([("due_at", 1), ("created_at", -1)]).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": [from_mongo(d) for d in docs]}


@router.post("")
async def create_task(body: TaskCreate, request: Request, user: dict = Depends(require_permission("crm.tasks.manage"))):
    db = get_db()
    t = Task(
        id=new_id(), tenant_id=user["tenant_id"],
        title=body.title, description=body.description, due_at=body.due_at,
        priority=body.priority, assigned_to=body.assigned_to or user["id"],
        lead_id=body.lead_id, customer_id=body.customer_id,
        created_by=user["id"], updated_by=user["id"],
    )
    await db.tasks.insert_one(to_mongo(t.model_dump(by_alias=True)))
    await record_activity(
        tenant_id=user["tenant_id"], type="task_created", subject=f"Task: {t.title}",
        lead_id=t.lead_id, customer_id=t.customer_id, user_id=user["id"], user_email=user["email"],
    )
    return from_mongo(await db.tasks.find_one({"_id": t.id}))


@router.patch("/{tid}")
async def update_task(tid: str, body: TaskUpdate, request: Request,
                      user: dict = Depends(require_permission("crm.tasks.manage"))):
    db = get_db()
    doc = await db.tasks.find_one({"_id": tid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Task non trovato")
    payload = body.model_dump(exclude_unset=True)
    if payload.get("task_status") == "done" and not doc.get("completed_at"):
        payload["completed_at"] = datetime.now(timezone.utc).isoformat()
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload["updated_by"] = user["id"]
    await db.tasks.update_one({"_id": tid}, {"$set": payload})
    if payload.get("task_status") == "done":
        await record_activity(
            tenant_id=user["tenant_id"], type="task_done", subject=f"Task completato: {doc.get('title')}",
            lead_id=doc.get("lead_id"), customer_id=doc.get("customer_id"),
            user_id=user["id"], user_email=user["email"],
        )
    return from_mongo(await db.tasks.find_one({"_id": tid}))


@router.delete("/{tid}")
async def delete_task(tid: str, user: dict = Depends(require_permission("crm.tasks.manage"))):
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.tasks.update_one({"_id": tid, "tenant_id": user["tenant_id"]},
                              {"$set": {"deleted_at": now, "updated_at": now, "updated_by": user["id"]}})
    return {"ok": True}
