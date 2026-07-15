"""Audit log viewer."""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Query
from app.db import get_db
from app.deps import require_permission
from app.mongo_utils import from_mongo

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
async def list_audit(
    action: Optional[str] = None,
    user_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    q: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(50, le=200),
    user: dict = Depends(require_permission("audit.view")),
):
    db = get_db()
    query: dict = {"tenant_id": user["tenant_id"]}
    if action:
        query["action"] = {"$regex": action, "$options": "i"}
    if user_id:
        query["user_id"] = user_id
    if entity_type:
        query["entity_type"] = entity_type
    if entity_id:
        query["entity_id"] = entity_id
    if q:
        query["$or"] = [
            {"action": {"$regex": q, "$options": "i"}},
            {"user_email": {"$regex": q, "$options": "i"}},
            {"entity_type": {"$regex": q, "$options": "i"}},
        ]
    total = await db.audit_logs.count_documents(query)
    docs = await db.audit_logs.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": [from_mongo(d) for d in docs]}
