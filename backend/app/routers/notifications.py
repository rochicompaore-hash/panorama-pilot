"""Notifications - list, mark as read."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from app.db import get_db
from app.deps import get_current_user, require_permission
from app.models import Notification, new_id
from app.mongo_utils import to_mongo, from_mongo

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationCreate(BaseModel):
    user_id: str
    type: str = "info"
    title: str
    body: Optional[str] = None
    link: Optional[str] = None


@router.get("")
async def list_notifications(
    only_unread: bool = False,
    limit: int = Query(50, le=200),
    user: dict = Depends(get_current_user),
):
    db = get_db()
    query = {"user_id": user["id"], "deleted_at": None}
    if only_unread:
        query["read_at"] = None
    docs = await db.notifications.find(query).sort("created_at", -1).limit(limit).to_list(limit)
    unread = await db.notifications.count_documents({"user_id": user["id"], "read_at": None, "deleted_at": None})
    return {"unread": unread, "items": [from_mongo(d) for d in docs]}


@router.post("/{nid}/read")
async def mark_read(nid: str, user: dict = Depends(get_current_user)):
    db = get_db()
    r = await db.notifications.update_one(
        {"_id": nid, "user_id": user["id"]},
        {"$set": {"read_at": datetime.now(timezone.utc).isoformat()}},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notifica non trovata")
    return {"ok": True}


@router.post("/read-all")
async def mark_all_read(user: dict = Depends(get_current_user)):
    db = get_db()
    await db.notifications.update_many(
        {"user_id": user["id"], "read_at": None},
        {"$set": {"read_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True}


@router.post("")
async def create_notification(
    body: NotificationCreate,
    user: dict = Depends(require_permission("users.manage")),
):
    """Internal utility - admins create notifications for users of their tenant."""
    db = get_db()
    target = await db.users.find_one({"_id": body.user_id, "tenant_id": user["tenant_id"]})
    if not target:
        raise HTTPException(status_code=404, detail="Utente destinatario non trovato")
    n = Notification(
        id=new_id(),
        tenant_id=user["tenant_id"],
        user_id=body.user_id,
        type=body.type, title=body.title, body=body.body, link=body.link,
        created_by=user["id"], updated_by=user["id"],
    )
    await db.notifications.insert_one(to_mongo(n.model_dump(by_alias=True)))
    return from_mongo(await db.notifications.find_one({"_id": n.id}))
