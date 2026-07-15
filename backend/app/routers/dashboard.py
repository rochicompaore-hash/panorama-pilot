"""Dashboard summary endpoint."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from app.db import get_db
from app.deps import require_permission
from app.mongo_utils import from_mongo

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
async def summary(user: dict = Depends(require_permission("dashboard.view"))):
    db = get_db()
    tenant = user["tenant_id"]
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    users_total = await db.users.count_documents({"tenant_id": tenant, "deleted_at": None})
    users_active = await db.users.count_documents({"tenant_id": tenant, "deleted_at": None, "is_active": True})
    roles_total = await db.roles.count_documents({"tenant_id": tenant, "deleted_at": None})
    attachments_total = await db.attachments.count_documents({"tenant_id": tenant, "deleted_at": None})
    audit_recent = await db.audit_logs.count_documents({"tenant_id": tenant, "created_at": {"$gte": since}})
    sessions_active = await db.sessions.count_documents({"tenant_id": tenant, "revoked_at": None})
    notifications_unread = await db.notifications.count_documents({"user_id": user["id"], "read_at": None, "deleted_at": None})

    recent_audit = await db.audit_logs.find({"tenant_id": tenant}).sort("created_at", -1).limit(8).to_list(8)
    recent_users = await db.users.find({"tenant_id": tenant, "deleted_at": None}).sort("created_at", -1).limit(5).to_list(5)

    return {
        "counters": {
            "users_total": users_total, "users_active": users_active,
            "roles_total": roles_total, "attachments_total": attachments_total,
            "audit_last_7d": audit_recent, "sessions_active": sessions_active,
            "notifications_unread": notifications_unread,
        },
        "recent_audit": [from_mongo(d) for d in recent_audit],
        "recent_users": [
            {"id": u["_id"], "email": u["email"], "first_name": u.get("first_name"),
             "last_name": u.get("last_name"), "created_at": u.get("created_at"),
             "is_active": u.get("is_active", True)}
            for u in recent_users
        ],
    }
