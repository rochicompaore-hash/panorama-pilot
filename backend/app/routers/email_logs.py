"""Email logs viewer (admin)."""
from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from app.db import get_db
from app.deps import require_permission
from app.mongo_utils import from_mongo

router = APIRouter(prefix="/email-logs", tags=["email-logs"])


@router.get("")
async def list_logs(
    limit: int = Query(50, le=200),
    skip: int = 0,
    user: dict = Depends(require_permission("audit.view")),
):
    db = get_db()
    total = await db.email_logs.count_documents({})
    docs = await db.email_logs.find({}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": [from_mongo(d) for d in docs]}
