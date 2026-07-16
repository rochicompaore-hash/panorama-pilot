"""Seed initial data: permissions, roles, super admin user, default company."""
from __future__ import annotations
import logging
import os
from datetime import datetime, timezone
from app.db import get_db
from app.config import settings
from app.permissions import PERMISSION_CATALOG, PREDEFINED_ROLES
from app.security import hash_password, verify_password
from app.models import Permission, Role, User, Company, Sequence, new_id
from app.mongo_utils import to_mongo

logger = logging.getLogger("seed")


async def ensure_indexes():
    db = get_db()
    await db.users.create_index("email", unique=True)
    await db.users.create_index([("tenant_id", 1)])
    await db.companies.create_index("name")
    await db.roles.create_index([("tenant_id", 1), ("name", 1)])
    await db.permissions.create_index("key", unique=True)
    await db.sessions.create_index([("user_id", 1)])
    await db.sessions.create_index("refresh_token_hash")
    await db.sessions.create_index("expires_at")
    await db.password_reset_tokens.create_index("token_hash", unique=True)
    await db.password_reset_tokens.create_index("expires_at")
    await db.invitations.create_index("token_hash", unique=True)
    await db.invitations.create_index("email")
    await db.audit_logs.create_index([("tenant_id", 1), ("created_at", -1)])
    await db.audit_logs.create_index([("user_id", 1), ("created_at", -1)])
    await db.audit_logs.create_index("action")
    await db.notifications.create_index([("user_id", 1), ("created_at", -1)])
    await db.attachments.create_index([("tenant_id", 1), ("entity_type", 1), ("entity_id", 1)])
    await db.sequences.create_index([("tenant_id", 1), ("key", 1)], unique=True)
    await db.entity_versions.create_index([("entity_type", 1), ("entity_id", 1)])
    await db.email_logs.create_index("created_at")
    await db.login_attempts.create_index("identifier")
    await db.login_attempts.create_index("expires_at")
    # CRM indexes
    await db.pipelines.create_index([("tenant_id", 1), ("is_default", 1)])
    await db.leads.create_index([("tenant_id", 1), ("stage_id", 1)])
    await db.leads.create_index([("tenant_id", 1), ("assigned_to", 1)])
    await db.leads.create_index([("tenant_id", 1), ("lifecycle", 1)])
    await db.customers.create_index([("tenant_id", 1)])
    await db.contacts.create_index([("tenant_id", 1), ("customer_id", 1)])
    await db.contacts.create_index([("tenant_id", 1), ("lead_id", 1)])
    await db.activities.create_index([("tenant_id", 1), ("lead_id", 1), ("occurred_at", -1)])
    await db.activities.create_index([("tenant_id", 1), ("customer_id", 1), ("occurred_at", -1)])
    await db.activities.create_index([("tenant_id", 1), ("type", 1)])
    await db.tasks.create_index([("tenant_id", 1), ("assigned_to", 1), ("task_status", 1)])
    await db.tasks.create_index([("tenant_id", 1), ("due_at", 1)])
    await db.appointments.create_index([("tenant_id", 1), ("start_at", 1)])
    await db.appointments.create_index([("tenant_id", 1), ("attendees", 1)])
    await db.goals.create_index([("tenant_id", 1), ("user_id", 1), ("period_start", -1)])
    await db.commission_rules.create_index([("tenant_id", 1)])
    await db.whatsapp_logs.create_index([("tenant_id", 1), ("created_at", -1)])
    # M3 indexes
    await db.quotes.create_index([("tenant_id", 1), ("number_int", -1)])
    await db.quotes.create_index([("tenant_id", 1), ("quote_status", 1)])
    await db.quotes.create_index([("tenant_id", 1), ("lead_id", 1)])
    await db.quotes.create_index([("tenant_id", 1), ("customer_id", 1)])
    await db.quotes.create_index([("tenant_id", 1), ("assigned_to", 1)])
    await db.contracts.create_index([("tenant_id", 1), ("number_int", -1)])
    await db.contracts.create_index([("tenant_id", 1), ("quote_id", 1)])
    await db.pricelists.create_index([("tenant_id", 1)])
    await db.price_rules.create_index([("tenant_id", 1), ("product_key", 1)])
    await db.discount_thresholds.create_index([("tenant_id", 1)])
    await db.products.create_index([("tenant_id", 1), ("key", 1)])


async def seed_permissions():
    db = get_db()
    for key, module, action, desc in PERMISSION_CATALOG:
        existing = await db.permissions.find_one({"key": key})
        if existing:
            continue
        p = Permission(id=new_id(), key=key, module=module, action=action, description=desc)
        await db.permissions.insert_one(to_mongo(p.model_dump(by_alias=True)))


async def seed_default_company() -> str:
    db = get_db()
    existing = await db.companies.find_one({"deleted_at": None})
    if existing:
        return existing["_id"]
    c = Company(id=new_id(), name=settings.ADMIN_COMPANY_NAME, legal_name=settings.ADMIN_COMPANY_NAME)
    c.tenant_id = c.id  # self-reference (company IS the tenant)
    await db.companies.insert_one(to_mongo(c.model_dump(by_alias=True)))
    return c.id


async def seed_roles(tenant_id: str) -> dict:
    """Create predefined roles for the tenant. Returns dict slug->role_id."""
    db = get_db()
    all_perm_keys = [k for (k, *_rest) in PERMISSION_CATALOG]
    role_ids: dict[str, str] = {}
    for slug, cfg in PREDEFINED_ROLES.items():
        existing = await db.roles.find_one({"tenant_id": tenant_id, "name": cfg["name"]})
        if existing:
            role_ids[slug] = existing["_id"]
            continue
        keys = all_perm_keys if cfg["permissions"] == "*" else list(cfg["permissions"])
        r = Role(
            id=new_id(),
            tenant_id=tenant_id,
            name=cfg["name"],
            description=cfg["description"],
            permission_keys=keys,
            is_system=cfg["is_system"],
        )
        await db.roles.insert_one(to_mongo(r.model_dump(by_alias=True)))
        role_ids[slug] = r.id
    return role_ids


async def seed_sequences(tenant_id: str):
    db = get_db()
    defaults = [
        ("quote", "Preventivi", "PREV-", 5, True),
        ("contract", "Contratti", "CON-", 5, True),
        ("order", "Ordini", "ORD-", 5, True),
        ("purchase_order", "Ordini Fornitore", "POR-", 5, True),
        ("ddt", "DDT", "DDT-", 5, True),
        ("invoice", "Fatture", "FAT-", 5, True),
    ]
    for key, label, prefix, padding, year_reset in defaults:
        existing = await db.sequences.find_one({"tenant_id": tenant_id, "key": key})
        starting = 1349 if key == "quote" else 0
        if existing:
            # Ensure "quote" sequence current_number >= 1349 so first next-call yields 1350
            if key == "quote" and (existing.get("current_number") or 0) < 1349:
                await db.sequences.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"current_number": 1349, "prefix": "PREV-"}},
                )
            continue
        s = Sequence(
            id=new_id(), tenant_id=tenant_id, key=key, label=label,
            prefix=prefix, padding=padding, year_reset=year_reset, current_number=starting,
        )
        await db.sequences.insert_one(to_mongo(s.model_dump(by_alias=True)))


async def seed_super_admin(tenant_id: str, super_admin_role_id: str) -> str:
    db = get_db()
    email = settings.ADMIN_EMAIL.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        # keep password in sync with env if changed
        if not verify_password(settings.ADMIN_PASSWORD, existing.get("password_hash", "")):
            await db.users.update_one(
                {"_id": existing["_id"]},
                {"$set": {"password_hash": hash_password(settings.ADMIN_PASSWORD)}},
            )
        return existing["_id"]
    u = User(
        id=new_id(),
        tenant_id=tenant_id,
        email=email,
        password_hash=hash_password(settings.ADMIN_PASSWORD),
        first_name="Super",
        last_name="Admin",
        role_ids=[super_admin_role_id],
        is_superadmin=True,
        is_active=True,
        must_change_password=False,
    )
    await db.users.insert_one(to_mongo(u.model_dump(by_alias=True)))
    return u.id


async def write_test_credentials():
    """Write admin credentials to /app/memory/test_credentials.md for testing agents."""
    os.makedirs("/app/memory", exist_ok=True)
    content = f"""# Test Credentials — Infissi Express Cloud (M1)

## Super Admin
- Email: `{settings.ADMIN_EMAIL}`
- Password: `{settings.ADMIN_PASSWORD}`
- Role: Super Admin (accesso completo, cross-tenant)

## Auth endpoints (backend, tutti prefissati con `/api/auth`)
- `POST /api/auth/login` — body `{{email, password}}` → returns tokens + user; sets httpOnly cookies
- `POST /api/auth/logout` — invalidates current session
- `POST /api/auth/logout-all` — invalidates all sessions of the user
- `POST /api/auth/refresh` — reads refresh_token cookie / body, issues new access token
- `GET  /api/auth/me` — current user + permission keys
- `POST /api/auth/change-password` — body `{{current_password, new_password}}`
- `POST /api/auth/forgot-password` — body `{{email}}`
- `POST /api/auth/reset-password` — body `{{token, new_password}}`
- `POST /api/auth/accept-invitation` — body `{{token, password, first_name?, last_name?}}`

## App URL
- Frontend base: read from `REACT_APP_BACKEND_URL` (dev preview URL).
"""
    with open("/app/memory/test_credentials.md", "w") as f:
        f.write(content)


async def run_seed():
    await ensure_indexes()
    await seed_permissions()
    company_id = await seed_default_company()
    roles = await seed_roles(company_id)
    await seed_sequences(company_id)
    await seed_super_admin(company_id, roles["super_admin"])
    # Seed default pipeline (M2)
    from app.routers.pipelines import seed_default_pipeline
    await seed_default_pipeline(company_id)
    # Seed pricing defaults (M3.2)
    from app.seed_pricing import run_pricing_seed
    await run_pricing_seed(company_id)
    # Seed PDF templates + clauses (M3.3.2)
    from app.seed_pdf import run_pdf_seed
    await run_pdf_seed(company_id)
    await write_test_credentials()
    logger.info("Seed completed. Company=%s", company_id)
