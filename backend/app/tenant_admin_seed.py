"""Tenant Super Admin invitation seed — creates a distinct admin user for the
Infissi Express tenant, WITHOUT hardcoded password. Invitation is monouso.

Idempotent: safe to call at every startup.
"""
from __future__ import annotations
import hashlib
import logging
import os
import secrets
from datetime import datetime, timezone, timedelta
from app.db import get_db
from app.config import is_dev_or_test
from app.models import User, new_id
from app.mongo_utils import to_mongo

logger = logging.getLogger("tenant_admin_seed")

TENANT_ADMIN_EMAIL = os.environ.get("TENANT_ADMIN_INVITE_EMAIL", "admin.tenant@infissiexpress.com").strip().lower()


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def ensure_tenant_admin_invite(company_id: str) -> dict:
    """Ensure a distinct Tenant Super Admin user exists (via invitation)."""
    db = get_db()
    now = datetime.now(timezone.utc)
    email = TENANT_ADMIN_EMAIL

    # Find Super Admin role for this tenant (Italian label used in seed)
    role = await db.roles.find_one({"tenant_id": company_id, "name": {"$in": ["Super Admin", "super_admin"]}})
    if not role:
        logger.warning("Super Admin role not found for tenant %s", company_id)
        return {"skipped": True, "reason": "role_not_found"}

    # Existing user?
    existing = await db.users.find_one({"email": email})
    if existing and existing.get("password_hash"):
        return {"user_id": existing["_id"], "email": email, "already_active": True,
                 "raw_token_debug": None, "invitation_id": None}

    if existing:
        user_id = existing["_id"]
        # Ensure fields
        await db.users.update_one({"_id": user_id}, {"$set": {
            "tenant_id": company_id, "role_ids": [role["_id"]],
            "is_superadmin": False,  # tenant-scoped only
            "is_platform_owner": False, "is_protected": False,
            "is_active": True,
        }})
    else:
        u = User(
            id=new_id(), tenant_id=company_id, email=email,
            password_hash=None, first_name="Tenant", last_name="Admin",
            role_ids=[role["_id"]],
            is_superadmin=False,  # scoped to tenant super_admin ROLE, not global superadmin flag
            is_platform_owner=False, is_protected=False,
            is_active=True, must_change_password=False, locale="it",
        )
        await db.users.insert_one(to_mongo(u.model_dump(by_alias=True)))
        user_id = u.id
        logger.info("Tenant Admin user created (no password): %s", email)

    # Fresh invitation?
    active_inv = await db.invitations.find_one({
        "email": email, "consumed_at": None, "accepted_at": None,
        "expires_at": {"$gt": now.isoformat()},
    })
    if active_inv:
        return {"user_id": user_id, "email": email, "already_active": False,
                 "invitation_id": active_inv["_id"], "expires_at": active_inv.get("expires_at"),
                 "raw_token_debug": active_inv.get("debug_raw_token")}

    raw = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw)
    inv_id = new_id()
    expires = now + timedelta(days=7)
    inv_doc = {
        "_id": inv_id, "tenant_id": company_id, "email": email,
        "target_user_id": user_id, "token_hash": token_hash,
        "role_ids": [role["_id"]], "kind": "tenant_admin_activation",
        "created_at": now.isoformat(), "expires_at": expires.isoformat(),
        "consumed_at": None, "accepted_at": None,
        "created_by": "system:seed", "updated_at": now.isoformat(),
        "deleted_at": None, "version": 1, "status": "active",
    }
    if is_dev_or_test():
        inv_doc["debug_raw_token"] = raw
    await db.invitations.insert_one(inv_doc)
    logger.info("Tenant Admin invitation created (id=%s)", inv_id)
    return {"user_id": user_id, "email": email, "already_active": False,
             "invitation_id": inv_id, "expires_at": expires.isoformat(),
             "raw_token_debug": raw if is_dev_or_test() else None}
