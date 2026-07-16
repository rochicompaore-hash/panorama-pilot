"""Users management: list, get, create+invite, update, deactivate, unlock, reset password."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from app.config import settings
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models import (
    User, UserCreate, UserUpdate, UserPublic, Invitation, new_id,
)
from app.mongo_utils import to_mongo, from_mongo
from app.security import generate_secure_token, hash_token, hash_password
from app.services.audit import record_audit
from app.services.email import send_email, render_invitation

router = APIRouter(prefix="/users", tags=["users"])


def _public(u: dict) -> dict:
    d = from_mongo(u)
    d.pop("password_hash", None)
    return {k: d.get(k) for k in UserPublic.model_fields.keys()}


@router.get("")
async def list_users(
    q: Optional[str] = None,
    limit: int = Query(100, le=500),
    skip: int = 0,
    include_inactive: bool = True,
    user: dict = Depends(require_permission("users.view")),
):
    db = get_db()
    query: dict = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if not include_inactive:
        query["is_active"] = True
    if q:
        query["$or"] = [
            {"email": {"$regex": q, "$options": "i"}},
            {"first_name": {"$regex": q, "$options": "i"}},
            {"last_name": {"$regex": q, "$options": "i"}},
        ]
    total = await db.users.count_documents(query)
    docs = await db.users.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": [_public(d) for d in docs]}


@router.get("/{user_id}")
async def get_user(user_id: str, user: dict = Depends(require_permission("users.view"))):
    db = get_db()
    doc = await db.users.find_one({"_id": user_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    return _public(doc)


@router.post("")
async def create_user(
    body: UserCreate, request: Request,
    user: dict = Depends(require_permission("users.create")),
):
    db = get_db()
    email = body.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email già registrata")

    # Validate roles belong to tenant
    if body.role_ids:
        count = await db.roles.count_documents({"_id": {"$in": body.role_ids}, "tenant_id": user["tenant_id"]})
        if count != len(body.role_ids):
            raise HTTPException(status_code=400, detail="Ruoli non validi")

    u = User(
        id=new_id(),
        tenant_id=user["tenant_id"],
        email=email,
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        role_ids=body.role_ids,
        is_active=True,
        must_change_password=True,
        password_hash=None,  # will be set at invitation acceptance
        created_by=user["id"], updated_by=user["id"],
    )
    await db.users.insert_one(to_mongo(u.model_dump(by_alias=True)))

    # Create invitation & send email
    invite_url = None
    if body.send_invitation:
        raw = generate_secure_token(48)
        inv = Invitation(
            id=new_id(),
            tenant_id=user["tenant_id"],
            email=email,
            role_ids=body.role_ids,
            token_hash=hash_token(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.INVITATION_EXPIRE_HOURS),
            invited_by=user["id"],
            created_by=user["id"], updated_by=user["id"],
        )
        await db.invitations.insert_one(to_mongo(inv.model_dump(by_alias=True)))
        invite_url = f"{settings.APP_BASE_URL}/accept-invitation?token={raw}"

        company = await db.companies.find_one({"_id": user["tenant_id"]})
        cname = (company or {}).get("name", "Infissi Express Cloud")
        subject, html, text = render_invitation(cname, invite_url)
        await send_email(email, subject, "invitation", html, text)

    await record_audit(
        action="users.create", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"],
        ip=get_client_ip(request), entity_type="user", entity_id=u.id,
        after={"email": email, "role_ids": body.role_ids},
    )
    result = _public(await db.users.find_one({"_id": u.id}))
    result["invitation_url"] = invite_url  # useful in dev
    return result


@router.patch("/{user_id}")
async def update_user(
    user_id: str, body: UserUpdate, request: Request,
    user: dict = Depends(require_permission("users.edit")),
):
    db = get_db()
    doc = await db.users.find_one({"_id": user_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        # Also lookup globally — platform owner is tenant_id=None
        doc = await db.users.find_one({"_id": user_id, "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Utente non trovato")

    # Platform Owner protection: only the owner can modify themselves
    from app.platform_owner import assert_can_modify_user
    if doc.get("is_platform_owner") or doc.get("is_protected"):
        await assert_can_modify_user(user_id, user, action="update")
        # Additional guardrails: block dangerous fields
        if body.is_active is False:
            raise HTTPException(status_code=403, detail="L'utenza proprietaria non può essere disattivata")
        if body.role_ids is not None:
            # Ensure platform_owner role remains
            from app.platform_owner import PLATFORM_OWNER_ROLE_KEY
            po_role = await db.roles.find_one({"name": PLATFORM_OWNER_ROLE_KEY, "tenant_id": None})
            if po_role and po_role["_id"] not in (body.role_ids or []):
                raise HTTPException(status_code=403,
                    detail="Il ruolo Platform Owner non può essere rimosso dall'utenza proprietaria")

    if body.role_ids is not None:
        if body.role_ids:
            # Roles can be tenant-scoped OR global (platform owner role)
            count = await db.roles.count_documents({"_id": {"$in": body.role_ids},
                "$or": [{"tenant_id": user["tenant_id"]}, {"tenant_id": None}]})
            if count != len(body.role_ids):
                raise HTTPException(status_code=400, detail="Ruoli non validi")

    update: dict = {"updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user["id"]}
    for k in ("first_name", "last_name", "phone", "role_ids", "is_active"):
        v = getattr(body, k)
        if v is not None:
            update[k] = v
    await db.users.update_one({"_id": user_id}, {"$set": update})
    await record_audit(
        action="users.update", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="user", entity_id=user_id,
        before={k: doc.get(k) for k in update if k in doc},
        after=update,
    )
    return _public(await db.users.find_one({"_id": user_id}))


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: str, request: Request,
    user: dict = Depends(require_permission("users.delete")),
):
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Non puoi disattivare te stesso")
    db = get_db()
    doc = await db.users.find_one({"_id": user_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        doc = await db.users.find_one({"_id": user_id, "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    if doc.get("is_platform_owner") or doc.get("is_protected"):
        raise HTTPException(status_code=403, detail="L'utenza proprietaria della piattaforma non può essere eliminata o disattivata")
    now = datetime.now(timezone.utc).isoformat()
    await db.users.update_one(
        {"_id": user_id},
        {"$set": {"is_active": False, "deleted_at": now, "updated_at": now, "updated_by": user["id"]}},
    )
    await db.sessions.update_many(
        {"user_id": user_id, "revoked_at": None},
        {"$set": {"revoked_at": now}},
    )
    await record_audit(
        action="users.deactivate", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="user", entity_id=user_id,
    )
    return {"ok": True}


@router.post("/{user_id}/resend-invitation")
async def resend_invitation(
    user_id: str, request: Request,
    user: dict = Depends(require_permission("users.manage")),
):
    db = get_db()
    doc = await db.users.find_one({"_id": user_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    raw = generate_secure_token(48)
    inv = Invitation(
        id=new_id(),
        tenant_id=user["tenant_id"],
        email=doc["email"],
        role_ids=doc.get("role_ids", []),
        token_hash=hash_token(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.INVITATION_EXPIRE_HOURS),
        invited_by=user["id"],
        created_by=user["id"], updated_by=user["id"],
    )
    await db.invitations.insert_one(to_mongo(inv.model_dump(by_alias=True)))
    invite_url = f"{settings.APP_BASE_URL}/accept-invitation?token={raw}"
    company = await db.companies.find_one({"_id": user["tenant_id"]})
    cname = (company or {}).get("name", "Infissi Express Cloud")
    subject, html, text = render_invitation(cname, invite_url)
    await send_email(doc["email"], subject, "invitation", html, text)
    await record_audit(
        action="users.resend_invitation", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="user", entity_id=user_id,
    )
    return {"ok": True, "invitation_url": invite_url}


@router.post("/{user_id}/unlock")
async def unlock_user(
    user_id: str, request: Request,
    user: dict = Depends(require_permission("users.manage")),
):
    db = get_db()
    doc = await db.users.find_one({"_id": user_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    await db.users.update_one(
        {"_id": user_id},
        {"$set": {"locked_until": None, "failed_login_attempts": 0}},
    )
    await db.login_attempts.delete_many({"identifier": {"$regex": f":{doc['email']}$"}})
    await record_audit(
        action="users.unlock", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="user", entity_id=user_id,
    )
    return {"ok": True}
