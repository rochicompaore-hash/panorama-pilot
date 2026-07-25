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
        keys = all_perm_keys if cfg["permissions"] == "*" else list(cfg["permissions"])
        # For "*" roles we store the wildcard as a marker so admin can bypass ALL future perms.
        if cfg["permissions"] == "*":
            keys = ["*"]
        if existing:
            # Idempotent refresh: keep system roles in sync with the latest permission catalog.
            if existing.get("is_system"):
                await db.roles.update_one({"_id": existing["_id"]},
                    {"$set": {"permission_keys": keys, "description": cfg["description"]}})
            role_ids[slug] = existing["_id"]
            continue
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
    from app.platform_owner import PLATFORM_OWNER_EMAIL
    content = f"""# Test Credentials — Infissi Express Cloud

## Platform Owner (proprietario globale, MFA-ready, attivazione via invito)
- Email: `{PLATFORM_OWNER_EMAIL}`
- Password: **NON hardcoded** — via invito monouso
- Ruolo: `platform_owner` (globale, tenant_id=null)
- Flag: `is_platform_owner=true`, `is_protected=true`
- Recupero invito (dev/test only): `GET /api/debug/platform-owner-invite`
- Rigenera invito: `POST /api/debug/platform-owner-invite/regenerate`
- Non eliminabile, non disattivabile, non retrocessibile.

## Super Admin (test tenant Infissi Express)
- Email: `{settings.ADMIN_EMAIL}`
- Password: `{settings.ADMIN_PASSWORD}`
- Role: Super Admin (tenant-scoped)

## Auth endpoints (`/api/auth`)
- `POST /login` — body `{{email, password}}`
- `POST /accept-invitation` — body `{{token, password, first_name?, last_name?}}`
- `POST /logout`, `/logout-all`, `/refresh`
- `GET  /me`
- `POST /change-password`, `/forgot-password`, `/reset-password`

## App URL
- Frontend base: `REACT_APP_BACKEND_URL` (dev preview URL).

## M3.3.4 — Firma Elettronica Semplice
- Redis: `redis://127.0.0.1:6379/0` (supervisord `redis`)
- APP_ENV=development → OTP debug attivo (`GET /api/debug/otp/{{request_id}}`)
- Fail-closed in staging/prod se Redis non disponibile.
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
    # Gate demo data behind DEMO_SEED_ENABLED (release_stage=first_operational_release → False)
    from app.config import is_demo_mode
    demo = is_demo_mode()
    logger.info("Demo seed mode: %s (release_stage=%s)", demo, settings.RELEASE_STAGE)
    # Seed pricing defaults (M3.2) — OPERATIONAL (currency, tax rates, categories)
    from app.seed_pricing import run_pricing_seed
    await run_pricing_seed(company_id)
    # Seed PDF templates + clauses (M3.3.2) — OPERATIONAL (templates, no demo data)
    from app.seed_pdf import run_pdf_seed
    await run_pdf_seed(company_id)
    # Seed Parametric Engine demo data — DEMO only
    if demo:
        try:
            from app.seed_parametric import seed_parametric_demo
            pdemo = await seed_parametric_demo(company_id)
            logger.info("Parametric demo seed: %s", pdemo.get("ok"))
        except Exception as e:
            logger.warning("Parametric demo seed issue (non-fatal): %s", e)
    else:
        logger.info("Parametric demo seed SKIPPED (demo_seed_enabled=false)")
    # Seed M7 extensions — modules/plans (OPERATIONAL) vs product_catalog+management_demo (DEMO)
    try:
        from app.seed_extensions import seed_multi_company_and_saas
        # multi-company + SaaS modules/plans are OPERATIONAL config (users need them to subscribe)
        await seed_multi_company_and_saas(company_id)
        if demo:
            from app.seed_extensions import seed_product_catalog, seed_management_demo
            await seed_product_catalog(company_id)
            await seed_management_demo(company_id)
            logger.info("M7 extensions seed OK (demo data included)")
        else:
            logger.info("M7 extensions: only SaaS modules seeded, DEMO data skipped")
    except Exception as e:
        logger.warning("M7 extensions seed issue (non-fatal): %s", e)
    # Platform Owner (globale, sopra Super Admin del tenant) — OPERATIONAL
    from app.platform_owner import run_platform_owner_seed
    po = await run_platform_owner_seed()
    logger.info("Platform Owner seed: user_id=%s already_active=%s inv=%s",
                po.get("user_id"), po.get("already_active"), po.get("invitation_token_id"))
    # Tenant Admin (Infissi Express) — via invito — OPERATIONAL (default tenant user)
    from app.tenant_admin_seed import ensure_tenant_admin_invite
    ta = await ensure_tenant_admin_invite(company_id)
    logger.info("Tenant Admin seed: user_id=%s already_active=%s inv=%s",
                ta.get("user_id"), ta.get("already_active"), ta.get("invitation_id"))
    # Indexes (stabilization)
    from app.services.indexes import ensure_indexes as _ensure_indexes
    try:
        await _ensure_indexes()
    except Exception as e:
        logger.warning("Index creation issue (non-fatal): %s", e)
    await write_test_credentials()
    logger.info("Seed completed. Company=%s demo=%s", company_id, demo)
