"""MongoDB indexes for stabilization — created at startup, idempotent.

Aggiunge indici mirati per performance + tenant isolation su collezioni core
+ nuove collezioni M4-M17. `create_index` è idempotente: MongoDB skippa se esiste.
"""
from __future__ import annotations
import logging
from app.db import get_db

logger = logging.getLogger("indexes")


async def ensure_indexes():
    db = get_db()

    # ---------- Auth / core ----------
    # Skip email index — pre-existing under different name; safe.
    await db.users.create_index([("tenant_id", 1), ("is_active", 1)], name="ix_users_tenant_active")
    await db.sessions.create_index([("user_id", 1), ("revoked_at", 1)], name="ix_sessions_user")
    await db.sessions.create_index([("refresh_hash", 1)], name="ix_sessions_refresh")
    await db.invitations.create_index([("token_hash", 1)], name="ix_invitations_token")
    await db.invitations.create_index([("email", 1), ("kind", 1)], name="ix_invitations_email_kind")
    await db.roles.create_index([("tenant_id", 1), ("name", 1)], name="ix_roles_tenant_name")
    await db.audit_logs.create_index([("tenant_id", 1), ("created_at", -1)], name="ix_audit_tenant_created")
    await db.audit_logs.create_index([("entity_type", 1), ("entity_id", 1)], name="ix_audit_entity")

    # ---------- CRM ----------
    await db.leads.create_index([("tenant_id", 1), ("created_at", -1)], name="ix_leads_tenant_created")
    await db.leads.create_index([("tenant_id", 1), ("status", 1)], name="ix_leads_tenant_status")
    await db.customers.create_index([("tenant_id", 1), ("email", 1)], name="ix_customers_tenant_email")
    await db.customers.create_index([("tenant_id", 1), ("deleted_at", 1)], name="ix_customers_tenant_deleted")
    await db.contacts.create_index([("tenant_id", 1), ("customer_id", 1)], name="ix_contacts_tenant_customer")
    await db.activities.create_index([("tenant_id", 1), ("created_at", -1)], name="ix_activities_tenant_created")
    await db.activities.create_index([("customer_id", 1), ("created_at", -1)], name="ix_activities_customer_created")
    await db.tasks.create_index([("tenant_id", 1), ("assigned_to", 1), ("status", 1)], name="ix_tasks_tenant_owner")

    # ---------- Quotes / pricing ----------
    await db.quotes.create_index([("tenant_id", 1), ("number_int", -1)], name="ix_quotes_tenant_num")
    await db.quotes.create_index([("tenant_id", 1), ("customer_id", 1)], name="ix_quotes_tenant_customer")
    await db.quotes.create_index([("tenant_id", 1), ("quote_status", 1), ("created_at", -1)], name="ix_quotes_tenant_status")
    await db.quotes.create_index([("tenant_id", 1), ("is_current", 1)], name="ix_quotes_current")
    await db.quote_pdfs.create_index([("tenant_id", 1), ("quote_id", 1), ("generated_at", -1)], name="ix_quote_pdfs_quote")
    await db.quote_public_tokens.create_index([("token_hash", 1)], unique=True, name="ux_public_tokens_hash")
    await db.quote_public_tokens.create_index([("tenant_id", 1), ("quote_id", 1), ("status", 1)], name="ix_public_tokens_quote")
    await db.quote_signatures.create_index([("tenant_id", 1), ("quote_id", 1)], name="ix_signatures_quote")
    await db.quote_otp_requests.create_index([("token_id", 1), ("status", 1)], name="ix_otp_token_status")
    await db.public_access_log.create_index([("tenant_id", 1), ("quote_id", 1), ("created_at", -1)], name="ix_access_log_quote")
    await db.customer_requests.create_index([("tenant_id", 1), ("quote_id", 1), ("kind", 1)], name="ix_customer_requests")

    # ---------- Operations M4..M14 ----------
    for coll in ("surveys", "sales_orders", "purchase_orders", "goods_receipts",
                 "boms", "production_orders", "cutting_lists",
                 "qc_checks", "non_conformities",
                 "shipments", "finished_good_packs",
                 "installation_plans", "installation_reports",
                 "service_tickets", "payment_plans", "payments", "invoices",
                 "suppliers", "supplier_price_lists",
                 "attachments"):
        await db[coll].create_index([("tenant_id", 1), ("created_at", -1)], name=f"ix_{coll}_tenant_created")
        await db[coll].create_index([("tenant_id", 1), ("deleted_at", 1)], name=f"ix_{coll}_tenant_deleted")

    # ---------- Items / stock (M6) ----------
    await db.items.create_index([("tenant_id", 1), ("code", 1)], unique=True, sparse=True, name="ux_items_tenant_code")
    await db.items.create_index([("tenant_id", 1), ("category", 1)], name="ix_items_tenant_cat")
    await db.stock_levels.create_index([("tenant_id", 1), ("item_id", 1), ("location_id", 1)], unique=True, name="ux_stock_levels")
    await db.stock_movements.create_index([("tenant_id", 1), ("item_id", 1), ("created_at", -1)], name="ix_stock_movements_item")

    # ---------- Number sequences ----------
    await db.sequences.create_index([("tenant_id", 1), ("key", 1)], unique=True, name="ux_sequences")

    # ---------- AI CFO ----------
    await db.ai_cfo_suggestions.create_index([("tenant_id", 1), ("is_dismissed", 1), ("generated_at", -1)], name="ix_aicfo_active")

    logger.info("MongoDB indexes ensured.")
