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

    # ---------- Parametric Engine (M6.PAR) ----------
    for coll in ("profile_systems", "profiles", "color_categories", "colors",
                  "glass_types", "hardware_kits", "accessories",
                  "item_pricelists", "price_matrices", "bom_templates",
                  "pricing_mode_configs", "cutting_lists", "scrap_stock",
                  "bar_optimization_runs", "parametric_snapshots"):
        await db[coll].create_index([("tenant_id", 1), ("created_at", -1)], name=f"ix_{coll}_tenant_created")
        await db[coll].create_index([("tenant_id", 1), ("deleted_at", 1)], name=f"ix_{coll}_tenant_deleted")
    await db.profiles.create_index([("tenant_id", 1), ("system_id", 1), ("role", 1)], name="ix_profiles_sys_role")
    await db.bom_templates.create_index([("tenant_id", 1), ("product_key", 1), ("bom_status", 1)], name="ix_bom_product_status")
    await db.price_matrices.create_index([("tenant_id", 1), ("product_key", 1), ("pm_status", 1)], name="ix_matrix_product_status")
    await db.pricing_mode_configs.create_index([("tenant_id", 1), ("scope", 1), ("product_key", 1), ("scope_ref_id", 1)], name="ix_pricing_mode_scope")
    await db.scrap_stock.create_index([("tenant_id", 1), ("profile_id", 1), ("color_id", 1), ("scrap_status", 1)], name="ix_scrap_prof_col_st")

    # ---------- Workflow M6.WF ----------
    for coll in ("technical_schedules", "executive_orders", "timeline_events",
                  "customer_status_mappings", "variances",
                  "technical_schedule_tokens", "technical_schedule_signatures",
                  "production_release_overrides"):
        await db[coll].create_index([("tenant_id", 1), ("created_at", -1)], name=f"ix_{coll}_tenant_created")
    await db.technical_schedules.create_index([("tenant_id", 1), ("contract_id", 1), ("is_current", 1)], name="ix_ts_contract_current")
    await db.technical_schedules.create_index([("tenant_id", 1), ("survey_id", 1), ("is_current", 1)], name="ix_ts_survey_current")
    await db.executive_orders.create_index([("tenant_id", 1), ("technical_schedule_id", 1)], name="ix_eo_ts", unique=False)
    await db.timeline_events.create_index([("tenant_id", 1), ("contract_id", 1), ("created_at", -1)], name="ix_timeline_contract")
    await db.timeline_events.create_index([("tenant_id", 1), ("customer_id", 1), ("is_customer_visible", 1), ("created_at", -1)], name="ix_timeline_customer_visible")
    await db.timeline_events.create_index([("tenant_id", 1), ("dedup_hash", 1)], name="ix_timeline_dedup", unique=True, sparse=True)
    await db.technical_schedule_tokens.create_index([("token_hash", 1)], name="ix_ts_token_hash", unique=True)

    # ---------- M6.OPS ----------
    for coll in ("operational_area_configs", "user_groups", "assignment_rules",
                  "operational_handoffs", "commission_plans", "commission_entries",
                  "commission_adjustments", "commission_invoices",
                  "lead_webhook_configs", "lead_webhook_ingestions",
                  "communication_channels", "conversations", "messages",
                  "message_templates", "email_automations", "consents"):
        await db[coll].create_index([("tenant_id", 1), ("created_at", -1)], name=f"ix_{coll}_tenant_created")
    await db.operational_handoffs.create_index([("tenant_id", 1), ("assigned_user_ids", 1), ("handoff_status", 1)], name="ix_handoff_user_status")
    await db.operational_handoffs.create_index([("tenant_id", 1), ("idempotency_key", 1)], name="ix_handoff_idem", sparse=True, unique=True)
    await db.commission_entries.create_index([("tenant_id", 1), ("sales_rep_id", 1), ("entry_status", 1)], name="ix_comm_rep_status")
    await db.commission_entries.create_index([("tenant_id", 1), ("contract_id", 1)], name="ix_comm_contract")
    await db.lead_webhook_configs.create_index([("slug", 1)], name="ix_lead_wc_slug", unique=True, sparse=True)
    await db.leads.create_index([("tenant_id", 1), ("dedup_key", 1)], name="ix_leads_dedup", sparse=True)
    await db.notifications.create_index([("tenant_id", 1), ("dedup_hash", 1)], name="ix_notif_dedup", unique=True, sparse=True)
    await db.consents.create_index([("tenant_id", 1), ("customer_id", 1), ("kind", 1)], name="ix_consents_customer_kind")
    await db.conversations.create_index([("tenant_id", 1), ("channel_kind", 1), ("conv_status", 1)], name="ix_conv_status")

    # ---------- M7.TREASURY ----------
    for coll in ("bank_accounts", "virtual_funds", "payments_received", "bank_statement_imports",
                  "bank_movements", "vat_entries", "vat_closings", "f24_payments",
                  "suggested_transfers", "allocation_policies", "allocation_runs",
                  "ai_cfo_insights", "treasury_alerts", "treasury_scenarios",
                  "tax_deduction_rates"):
        await db[coll].create_index([("tenant_id", 1), ("created_at", -1)], name=f"ix_{coll}_tenant_created")
    await db.bank_movements.create_index([("tenant_id", 1), ("dedup_hash", 1)], name="ix_bmov_dedup", unique=True, sparse=True)
    await db.bank_movements.create_index([("tenant_id", 1), ("bank_account_id", 1), ("op_date", -1)], name="ix_bmov_acct_date")
    await db.vat_entries.create_index([("tenant_id", 1), ("period", 1), ("kind", 1)], name="ix_vat_period_kind")
    await db.vat_closings.create_index([("tenant_id", 1), ("period", 1)], name="ix_vat_closing_period", unique=True, sparse=True)
    await db.f24_payments.create_index([("tenant_id", 1), ("due_date", 1), ("f24_status", 1)], name="ix_f24_due_status")
    await db.payments_received.create_index([("tenant_id", 1), ("recon_status", 1), ("payment_date", -1)], name="ix_pay_recon_date")

    logger.info("MongoDB indexes ensured.")
