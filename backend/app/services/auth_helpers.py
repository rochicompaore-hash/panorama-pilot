"""Small helpers to keep `routers/auth.py::login` and `accept_invitation` under
control both in complexity and readability.

No behavioural changes: extracted logic is identical to the original inlined code.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from app.security import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    hash_token,
)
from app.models import (
    User, UserPublic, Session as SessionModel, new_id,
)
from app.mongo_utils import to_mongo, from_mongo


def to_public_user(user: dict) -> UserPublic:
    """Project mongo user doc → UserPublic model."""
    return UserPublic(**{k: user.get(k) for k in UserPublic.model_fields.keys()})


async def check_brute_force(db, identifier: str, settings) -> Optional[int]:
    """Return wait-seconds if user is currently locked out, else None."""
    doc = await db.login_attempts.find_one({"identifier": identifier})
    if not doc:
        return None
    lu = doc.get("locked_until")
    if not lu:
        return None
    if isinstance(lu, str):
        lu = datetime.fromisoformat(lu)
    now = datetime.now(timezone.utc)
    if lu > now:
        return max(int((lu - now).total_seconds()), 1)
    return None


async def record_failed_login(db, identifier: str, settings) -> None:
    now = datetime.now(timezone.utc)
    doc = await db.login_attempts.find_one({"identifier": identifier})
    attempts = (doc or {}).get("attempts", 0) + 1
    update = {"identifier": identifier, "attempts": attempts, "last_at": now.isoformat()}
    if attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
        update["locked_until"] = (
            now + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
        ).isoformat()
        update["attempts"] = 0
    await db.login_attempts.update_one(
        {"identifier": identifier}, {"$set": update}, upsert=True,
    )


async def clear_failed_login(db, identifier: str) -> None:
    await db.login_attempts.delete_one({"identifier": identifier})


async def create_login_session(db, user_doc: dict, ip: str, user_agent: str | None,
                               settings) -> tuple[str, str]:
    """Persist a new session and return (access_token, refresh_token)."""
    session_id = new_id()
    refresh = create_refresh_token(user_doc["_id"], user_doc["tenant_id"], session_id)
    access = create_access_token(
        user_doc["_id"], user_doc["tenant_id"], user_doc.get("is_superadmin", False),
    )
    session = SessionModel(
        id=session_id,
        tenant_id=user_doc["tenant_id"],
        user_id=user_doc["_id"],
        refresh_token_hash=hash_token(refresh),
        ip=ip,
        user_agent=user_agent,
        device_info=user_agent,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    await db.sessions.insert_one(to_mongo(session.model_dump(by_alias=True)))
    await db.users.update_one(
        {"_id": user_doc["_id"]},
        {"$set": {"last_login_at": datetime.now(timezone.utc).isoformat()}},
    )
    return access, refresh


async def upsert_user_from_invitation(db, inv: dict, password: str,
                                      first_name: str | None, last_name: str | None) -> str:
    """Create the user attached to the invitation (or update the existing one).
    Returns the user_id. Never returns silently on error — callers rely on the id.
    """
    email = inv["email"].lower().strip()
    existing = await db.users.find_one({"email": email})
    now_iso = datetime.now(timezone.utc).isoformat()
    if existing:
        await db.users.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "password_hash": hash_password(password),
                "role_ids": inv.get("role_ids", []),
                "is_active": True,
                "must_change_password": False,
                "first_name": first_name or existing.get("first_name"),
                "last_name": last_name or existing.get("last_name"),
                "updated_at": now_iso,
            }},
        )
        return existing["_id"]
    u = User(
        id=new_id(),
        tenant_id=inv["tenant_id"],
        email=email,
        password_hash=hash_password(password),
        role_ids=inv.get("role_ids", []),
        first_name=first_name,
        last_name=last_name,
        is_active=True,
        must_change_password=False,
    )
    await db.users.insert_one(to_mongo(u.model_dump(by_alias=True)))
    return u.id
