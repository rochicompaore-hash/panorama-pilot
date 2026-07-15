"""Sessions management: view active sessions, revoke."""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from app.db import get_db
from app.deps import get_current_user, require_permission, get_client_ip
from app.mongo_utils import from_mongo
from app.services.audit import record_audit

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _strip(s: dict) -> dict:
    d = from_mongo(s)
    d.pop("refresh_token_hash", None)
    return d


@router.get("/mine")
async def my_sessions(user: dict = Depends(get_current_user)):
    db = get_db()
    docs = await db.sessions.find({"user_id": user["id"]}).sort("last_used_at", -1).to_list(100)
    return {"items": [_strip(d) for d in docs]}


@router.post("/{sid}/revoke")
async def revoke_session(sid: str, request: Request, user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await db.sessions.find_one({"_id": sid, "user_id": user["id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Sessione non trovata")
    if doc.get("revoked_at"):
        return {"ok": True}
    await db.sessions.update_one({"_id": sid}, {"$set": {"revoked_at": datetime.now(timezone.utc).isoformat()}})
    await record_audit(
        action="sessions.revoke", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="session", entity_id=sid,
    )
    return {"ok": True}


# admin: list all sessions in tenant
@router.get("")
async def list_sessions(user: dict = Depends(require_permission("sessions.view"))):
    db = get_db()
    docs = await db.sessions.find({"tenant_id": user["tenant_id"]}).sort("last_used_at", -1).to_list(200)
    return {"items": [_strip(d) for d in docs]}
