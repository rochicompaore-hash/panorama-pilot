"""Crea l'utenza Proprietario per PanoramaPilot.

Non stampa MAI la password. Idempotente: se l'utenza esiste già, aggiorna solo
i flag mancanti senza sovrascrivere la password.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "infissi_express")

from app.db import get_db, close_db
from app.security import hash_password
from app.models import User, Company, Role, new_id
from app.mongo_utils import to_mongo, from_mongo
from app.permissions import PERMISSION_CATALOG


TENANT_NAME = "PanoramaPilot"
TENANT_SLUG = "panoramapilot"
TENANT_DOMAIN = "panoramapilot.com"
OWNER_EMAIL = "pilot@panoramapilot.com"
OWNER_ROLE_CODE = "tenant_owner"
OWNER_ROLE_NAME = "Proprietario"


async def ensure_tenant(db):
    existing = await db.companies.find_one({
        "$or": [{"slug": TENANT_SLUG}, {"domain": TENANT_DOMAIN}, {"name": TENANT_NAME}],
        "deleted_at": None,
    })
    if existing:
        return existing["_id"], "existing"
    c = Company(
        id=new_id(), name=TENANT_NAME,
        legal_name="PanoramaPilot S.r.l.",
        vat_number=None, email=None, phone=None, address=None,
    )
    doc = to_mongo(c.model_dump(by_alias=True))
    doc["slug"] = TENANT_SLUG
    doc["domain"] = TENANT_DOMAIN
    doc["tenant_id"] = c.id
    doc["created_at"] = datetime.now(timezone.utc)
    doc["deleted_at"] = None
    await db.companies.insert_one(doc)
    return c.id, "created"


async def ensure_owner_role(db, tenant_id):
    existing = await db.roles.find_one({
        "tenant_id": tenant_id, "code": OWNER_ROLE_CODE, "deleted_at": None,
    })
    all_perm_codes = [p[0] for p in PERMISSION_CATALOG]
    tenant_perms = all_perm_codes   # tutti i permessi tenant-scoped (equivalente a "*")
    if existing:
        # aggiorna permessi in caso di nuovi permessi aggiunti al sistema
        await db.roles.update_one(
            {"_id": existing["_id"]},
            {"$set": {"permissions": tenant_perms, "is_protected": True,
                        "updated_at": datetime.now(timezone.utc)}},
        )
        return existing["_id"], "updated"
    r = Role(
        id=new_id(), tenant_id=tenant_id,
        code=OWNER_ROLE_CODE, name=OWNER_ROLE_NAME,
        description="Proprietario del tenant — controllo completo sulla propria azienda.",
        permissions=tenant_perms,
        is_protected=True, is_system=True,
    )
    doc = to_mongo(r.model_dump(by_alias=True))
    doc["created_at"] = datetime.now(timezone.utc)
    doc["deleted_at"] = None
    await db.roles.insert_one(doc)
    return r.id, "created"


async def ensure_owner_user(db, tenant_id, role_id, password_plain):
    existing = await db.users.find_one({"email": OWNER_EMAIL.lower()})
    if existing:
        patch = {}
        if not existing.get("role_ids") or role_id not in (existing.get("role_ids") or []):
            patch["role_ids"] = [role_id]
        if not existing.get("tenant_id"):
            patch["tenant_id"] = tenant_id
        if not existing.get("is_protected"):
            patch["is_protected"] = True
        if not existing.get("is_active"):
            patch["is_active"] = True
        if patch:
            patch["updated_at"] = datetime.now(timezone.utc)
            await db.users.update_one({"_id": existing["_id"]}, {"$set": patch})
        return existing["_id"], "existing_updated" if patch else "existing_no_change"
    u = User(
        id=new_id(), tenant_id=tenant_id,
        email=OWNER_EMAIL.lower(),
        password_hash=hash_password(password_plain),
        first_name="Proprietario",
        last_name="PanoramaPilot",
        role_ids=[role_id],
        is_superadmin=True,   # super admin del proprio tenant (NON platform owner)
        is_platform_owner=False,
        is_protected=True,
        is_active=True,
        must_change_password=True,   # forza cambio password al primo accesso
        mfa_enabled=False,
        locale="it",
    )
    doc = to_mongo(u.model_dump(by_alias=True))
    doc["created_at"] = datetime.now(timezone.utc)
    doc["deleted_at"] = None
    await db.users.insert_one(doc)
    return u.id, "created"


async def audit_entry(db, tenant_id, user_id, entity_type, entity_id, action, before=None, after=None):
    await db.audit_logs.insert_one({
        "_id": new_id(), "tenant_id": tenant_id,
        "user_id": user_id, "user_email": OWNER_EMAIL.lower(),
        "action": action, "entity_type": entity_type, "entity_id": entity_id,
        "before": before or {}, "after": after or {},
        "ip": None, "user_agent": "system-seed:owner",
        "created_at": datetime.now(timezone.utc),
    })


async def main():
    # La password viene letta da env var per non passarla mai in argv
    password = os.environ.get("OWNER_INIT_PASSWORD")
    if not password:
        raise SystemExit("ERROR: OWNER_INIT_PASSWORD non definita in env")

    # get_db() ritorna direttamente il DB motor (connessione lazy)
    db = get_db()
    try:
        tenant_id, t_state = await ensure_tenant(db)
        role_id, r_state = await ensure_owner_role(db, tenant_id)
        user_id, u_state = await ensure_owner_user(db, tenant_id, role_id, password)
        await audit_entry(db, tenant_id, user_id, "user", user_id, "owner.provisioned",
                            after={"role_code": OWNER_ROLE_CODE, "tenant_id": tenant_id,
                                    "state_user": u_state, "state_role": r_state, "state_tenant": t_state})
        report = {
            "email": OWNER_EMAIL,
            "tenant_id": tenant_id,
            "tenant_name": TENANT_NAME,
            "role_code": OWNER_ROLE_CODE,
            "role_id": role_id,
            "user_id": user_id,
            "state": {"tenant": t_state, "role": r_state, "user": u_state},
            "must_change_password": True,
            "mfa_enabled": False,
            "is_protected": True,
        }
        # NON stampare mai la password
        print("OWNER_PROVISIONED_REPORT:")
        import json
        print(json.dumps(report, indent=2, default=str))
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
