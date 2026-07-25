"""Cleanup dati demo dal tenant PanoramaPilot — SOLO tenant PanoramaPilot.

Idempotente. Modalità dry_run per anteprima. Preserva:
- utente pilot@panoramapilot.com
- ruolo tenant_owner
- company PanoramaPilot
- audit_logs (immutabili)
- indici, permessi, configurazioni sistema
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient

TENANT_ID = "ae9168f6-d96e-4c5d-bb33-25acbb9a8410"
OWNER_EMAIL = "pilot@panoramapilot.com"
OWNER_ROLE_CODE = "tenant_owner"
TENANT_NAME = "PanoramaPilot"

# Collezioni da ispezionare per il tenant (operational data)
OPERATIONAL_COLLECTIONS = [
    "customers", "leads", "contacts", "activities",
    "quotes", "quote_environments", "quote_openings", "opening_products",
    "contracts", "contract_signing_tokens", "quote_otp_requests",
    "surveys", "sites", "openings",
    "sales_orders", "purchase_orders", "goods_receipts", "non_conformities",
    "items", "stock_locations", "stock_movements", "stock_lots", "inventories",
    "products", "bom_templates", "cutting_lists", "bar_optimizations",
    "production_orders", "production_phases", "qc_checks", "traceability_units",
    "finished_goods", "shipments", "installation_plans", "installation_reports",
    "service_tickets", "warranties",
    "invoices", "payments", "commissions", "cost_centers", "ai_cfo_suggestions",
    "attachments", "notifications",
    "item_pricelists", "profiles", "profile_systems", "colors", "color_categories",
    "glass_types", "hardware_kits", "accessories",
    "dimension_rule_sets", "geometry_templates",
    "import_jobs", "import_job_blobs", "pricelist_import_snapshots",
    "pricing_method_configs", "price_matrices",
    "intercompany_transactions", "legal_entities",
    "cash_flow_entries", "fixed_costs", "personnel_costs", "budgets",
    "tenant_module_overrides", "billing_events",
    "landing_leads",
    "opportunities", "pipelines",
    "documents", "tasks",
]

# Collezioni da PRESERVARE totalmente (configurazione sistema)
PRESERVE_ALWAYS = {
    "users",        # utente proprietario
    "roles",        # ruolo tenant_owner
    "companies",    # PanoramaPilot
    "audit_logs",   # audit immutabile
    "sequences",    # numerazioni progressive (config)
    "permissions",  # catalogo permessi (globale)
    "clause_templates", "pdf_templates",  # template documentali
    # First operational release — preserve tutto ciò che è OPERATIONAL (non demo):
    "products",                # ProEvolution + ProEvolution Restauro (seed_catalog)
    "catalog_code_mappings",   # mapping 5103/5105/12130/7379
    "production_config",       # configurazione produzione tenant
    "color_categories",        # anagrafica colori
    "glass_types",             # anagrafica vetri
    "hardware_kits",           # anagrafica kit ferramenta
    "profile_systems",         # sistemi profilo
    "profiles",                # anagrafica profili
    "bom_templates",           # ricette BOM
    "dimension_rule_sets",     # regole dimensionali approvate
    "price_rules_v2",          # regole prezzo attive
}


async def main():
    dry_run = "--apply" not in sys.argv
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "infissi_express")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print(f"=== CLEANUP TENANT '{TENANT_NAME}' (id={TENANT_ID}) ===")
    print(f"Mode: {'DRY-RUN (nessuna modifica)' if dry_run else 'APPLY (modifiche reali)'}")
    print()

    # Verifica tenant esiste
    company = await db.companies.find_one({"_id": TENANT_ID})
    if not company:
        # possibile che sia salvato con tenant_id != _id
        company = await db.companies.find_one({"tenant_id": TENANT_ID, "name": TENANT_NAME})
    print(f"Tenant company found: {bool(company)}")

    # Verifica utente proprietario
    owner = await db.users.find_one({"email": OWNER_EMAIL, "tenant_id": TENANT_ID})
    print(f"Owner user found: {bool(owner)} (id={owner.get('_id') if owner else '-'})")

    # Verifica ruolo tenant_owner
    role = await db.roles.find_one({"tenant_id": TENANT_ID, "code": OWNER_ROLE_CODE, "deleted_at": None})
    print(f"Role tenant_owner found: {bool(role)}")

    print()
    print("=== Conteggio dati operativi per collezione ===")
    report = {"tenant_id": TENANT_ID, "collections": {}, "deleted": {}, "preserved": {},
                "storage_files_removed": 0, "unknown_records": []}
    total_found = 0
    total_deleted = 0

    for coll in OPERATIONAL_COLLECTIONS:
        if coll in PRESERVE_ALWAYS:
            continue  # skip operational config collections
        try:
            count = await db[coll].count_documents({"tenant_id": TENANT_ID})
        except Exception:
            continue
        if count > 0:
            report["collections"][coll] = count
            total_found += count
            print(f"  {coll:35s} {count} record")
            if not dry_run:
                # Elimina SOLO record del tenant (hard delete per pulizia iniziale)
                res = await db[coll].delete_many({"tenant_id": TENANT_ID})
                report["deleted"][coll] = res.deleted_count
                total_deleted += res.deleted_count

    # Storage cleanup — file legati al tenant
    storage_root = "/app/storage"
    tenant_prefix = f"{storage_root}/{TENANT_ID}"
    if os.path.isdir(tenant_prefix):
        files_count = sum(len(fs) for _, _, fs in os.walk(tenant_prefix))
        print(f"\n  Storage locale prefix {tenant_prefix}: {files_count} file")
        report["storage_files_found"] = files_count
        if not dry_run and files_count > 0:
            import shutil
            shutil.rmtree(tenant_prefix)
            report["storage_files_removed"] = files_count

    # Preservati (report)
    report["preserved"] = {
        "user_id": owner.get("_id") if owner else None,
        "user_email": OWNER_EMAIL,
        "role_id": role.get("_id") if role else None,
        "role_code": OWNER_ROLE_CODE,
        "company_id": (company or {}).get("_id"),
        "audit_logs_kept": await db.audit_logs.count_documents({"tenant_id": TENANT_ID}),
    }

    print()
    print(f"=== SUMMARY ===")
    print(f"Total operational records found:   {total_found}")
    print(f"Total operational records deleted: {total_deleted if not dry_run else '(dry-run)'}")
    print(f"Files removed from storage:        {report.get('storage_files_removed', 0)}")
    print(f"Preserved: user, role, company, audit ({report['preserved']['audit_logs_kept']} log entries)")

    if not dry_run:
        # Audit finale della cleanup
        from app.models import new_id
        await db.audit_logs.insert_one({
            "_id": new_id(), "tenant_id": TENANT_ID,
            "user_id": (owner or {}).get("_id"), "user_email": OWNER_EMAIL,
            "action": "tenant.cleanup.demo_data_removed",
            "entity_type": "tenant", "entity_id": TENANT_ID,
            "before": {"total_records": total_found},
            "after": {"total_deleted": total_deleted,
                        "storage_files_removed": report.get("storage_files_removed", 0)},
            "ip": None, "user_agent": "system-script:cleanup_tenant_demo",
            "created_at": datetime.now(timezone.utc),
        })
        print(f"\n✓ Audit registrato: action=tenant.cleanup.demo_data_removed")

    import json
    print()
    print("REPORT_JSON:")
    print(json.dumps(report, indent=2, default=str))
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
