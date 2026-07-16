"""Platform Owner — global-scope proprietary role.

Design:
- Un unico utente `is_platform_owner=True` per installazione.
- Non tenant-scoped: `tenant_id=None`, ma con `tenant_memberships=[]` (accede a tutti).
- Gerarchicamente sopra il Super Admin del tenant.
- Immutabile: bloccata eliminazione/disattivazione/retrocessione anche da Super Admin.
- Password non hardcoded: attivazione via invitation token monouso.
- MFA prevista (mfa_secret + recovery codes) — attivazione a discrezione del proprietario.

Seed idempotente: crea l'utenza + il ruolo globale se mancanti, e (se non ha ancora una password) genera un'invitation token debug-recuperabile.
"""
from __future__ import annotations
import hashlib
import logging
import os
import secrets
from datetime import datetime, timezone, timedelta
from app.db import get_db
from app.config import settings, is_dev_or_test
from app.models import User, Role, new_id, Permission
from app.mongo_utils import to_mongo

logger = logging.getLogger("platform_owner")

PLATFORM_OWNER_EMAIL = os.environ.get("PLATFORM_OWNER_EMAIL", "rochicompaore@gmail.com").strip().lower()
PLATFORM_OWNER_ROLE_KEY = "platform_owner"

# Permessi globali dedicati (non tenant-scoped)
PLATFORM_OWNER_PERMISSIONS = [
    "platform.tenant.view", "platform.tenant.create", "platform.tenant.delete",
    "platform.user.impersonate", "platform.user.view_all", "platform.user.manage_all",
    "platform.role.manage_all", "platform.permission.manage_all",
    "platform.settings.manage", "platform.integrations.manage",
    "platform.backups.access", "platform.audit.view_all", "platform.security.view",
    "platform.ai.configure", "platform.monitoring.view", "platform.system.status",
    "platform.data.export_all",
    "*",  # wildcard: bypassa qualsiasi controllo permessi al livello tenant
]


async def ensure_platform_owner_role() -> str:
    """Crea il ruolo 'platform_owner' se non esiste. Ruolo GLOBALE (tenant_id=None)."""
    db = get_db()
    existing = await db.roles.find_one({"tenant_id": None, "name": PLATFORM_OWNER_ROLE_KEY})
    if existing:
        # Keep permissions in sync
        await db.roles.update_one({"_id": existing["_id"]},
            {"$set": {"permission_keys": PLATFORM_OWNER_PERMISSIONS,
                       "description": "Proprietario piattaforma — accesso globale a tutti i tenant"}})
        return existing["_id"]
    r = Role(
        id=new_id(),
        tenant_id=None,
        name=PLATFORM_OWNER_ROLE_KEY,
        description="Proprietario piattaforma — accesso globale a tutti i tenant. Sopra Super Admin del tenant.",
        permission_keys=PLATFORM_OWNER_PERMISSIONS,
        is_system=True,
    )
    doc = to_mongo(r.model_dump(by_alias=True))
    doc["is_platform_role"] = True  # marcatura esplicita nel documento
    await db.roles.insert_one(doc)
    logger.info("Platform Owner role created: %s", r.id)
    return r.id


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def ensure_platform_owner_user(role_id: str) -> tuple[str, dict]:
    """Crea l'utente proprietario (se assente) + un invitation token monouso quando non ha password.

    Ritorna (user_id, {invitation_token, expires_at}) — invitation token è None se già attivato.
    """
    db = get_db()
    email = PLATFORM_OWNER_EMAIL
    existing = await db.users.find_one({"email": email})
    now = datetime.now(timezone.utc)
    inv_info = {"invitation_token_id": None, "invitation_created_at": None, "expires_at": None,
                "raw_token_debug": None, "already_active": False}

    if existing:
        # Ensure platform_owner flags always on
        await db.users.update_one({"_id": existing["_id"]}, {"$set": {
            "is_platform_owner": True, "platform_role": PLATFORM_OWNER_ROLE_KEY,
            "is_protected": True, "is_active": True, "is_superadmin": True,
            "tenant_id": None,  # global user — no single tenant
            "role_ids": list(set((existing.get("role_ids") or []) + [role_id])),
        }})
        # If already has password → skip invite generation
        if existing.get("password_hash"):
            inv_info["already_active"] = True
            return existing["_id"], inv_info
        user_id = existing["_id"]
    else:
        u = User(
            id=new_id(), tenant_id=None,
            email=email, password_hash=None,
            first_name="Platform", last_name="Owner",
            role_ids=[role_id],
            is_superadmin=True, is_platform_owner=True, is_protected=True,
            platform_role=PLATFORM_OWNER_ROLE_KEY,
            platform_permissions=PLATFORM_OWNER_PERMISSIONS,
            is_active=True, must_change_password=False,
            locale="it",
        )
        await db.users.insert_one(to_mongo(u.model_dump(by_alias=True)))
        user_id = u.id
        logger.info("Platform Owner user created (no password): %s", email)

    # Reuse existing pending invitation if fresh (<7 days), else create new
    active_inv = await db.invitations.find_one({
        "email": email, "consumed_at": None,
        "expires_at": {"$gt": now.isoformat()},
    })
    if active_inv:
        inv_info["invitation_token_id"] = active_inv["_id"]
        inv_info["invitation_created_at"] = active_inv.get("created_at")
        inv_info["expires_at"] = active_inv.get("expires_at")
        # Never expose the raw token if already generated (only stored as hash)
        return user_id, inv_info

    # Create invitation
    raw = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw)
    inv_id = new_id()
    expires = now + timedelta(days=7)
    await db.invitations.insert_one({
        "_id": inv_id,
        "tenant_id": None,
        "email": email,
        "target_user_id": user_id,
        "token_hash": token_hash,
        "role_ids": [role_id],
        "kind": "platform_owner_activation",
        "created_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "consumed_at": None,
        "created_by": "system:seed",
        "updated_at": now.isoformat(),
        "deleted_at": None,
        "version": 1,
        "status": "active",
    })
    inv_info["invitation_token_id"] = inv_id
    inv_info["invitation_created_at"] = now.isoformat()
    inv_info["expires_at"] = expires.isoformat()
    # ONLY expose raw token in dev/test via debug endpoint reference — never in logs
    if is_dev_or_test():
        inv_info["raw_token_debug"] = raw
        # Persist a debug field on the invitation doc so `/api/debug/platform-owner-invite` can fetch
        await db.invitations.update_one({"_id": inv_id}, {"$set": {"debug_raw_token": raw}})
    logger.info("Platform Owner invitation created (id=%s, expires=%s)", inv_id, expires.isoformat())
    return user_id, inv_info


async def run_platform_owner_seed() -> dict:
    role_id = await ensure_platform_owner_role()
    user_id, inv = await ensure_platform_owner_user(role_id)
    return {"role_id": role_id, "user_id": user_id, **inv, "email": PLATFORM_OWNER_EMAIL}


# ---------------------- Protection helpers ----------------------
class PlatformOwnerProtection(Exception):
    pass


async def assert_can_modify_user(target_user_id: str, actor: dict, *, action: str):
    """Raise HTTP-friendly exception if actor is trying to modify a protected platform owner.

    - Only the platform owner themselves can modify themselves.
    - Even superadmin (tenant) cannot delete/disable/demote the platform owner.
    """
    from fastapi import HTTPException
    db = get_db()
    target = await db.users.find_one({"_id": target_user_id})
    if not target: return
    if not target.get("is_platform_owner") and not target.get("is_protected"):
        return
    # Actor is platform owner → allowed (any action)
    if actor.get("is_platform_owner"):
        return
    raise HTTPException(status_code=403, detail={
        "error": "platform_owner_protected",
        "message": "L'utente proprietario della piattaforma è protetto e non può essere "
                   f"modificato ({action}) da account non-proprietari.",
    })
