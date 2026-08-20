"""Main FastAPI application entrypoint for Infissi Express Cloud.

Imports are grouped by domain for readability. Every router is registered under
the `/api` prefix so it is reachable through the Kubernetes ingress.
"""
from __future__ import annotations

# ------------------------------------------------------------------------------
# Environment bootstrap — must run BEFORE any `app.*` import that reads config.
# ------------------------------------------------------------------------------
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

# ------------------------------------------------------------------------------
# Third-party
# ------------------------------------------------------------------------------
import logging
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

# ------------------------------------------------------------------------------
# Core app (config / db / seed)
# ------------------------------------------------------------------------------
from app.config import settings
from app.db import get_db, close_db
from app.seed import run_seed

# ------------------------------------------------------------------------------
# Router imports — grouped by domain
# ------------------------------------------------------------------------------
# Foundations: auth / users / roles / core meta
from app.routers.auth import router as auth_router
from app.routers.users import router as users_router
from app.routers.roles import roles_router, permissions_router
from app.routers.company import router as company_router
from app.routers.audit import router as audit_router
from app.routers.notifications import router as notifications_router
from app.routers.attachments import router as attachments_router
from app.routers.sequences import router as sequences_router
from app.routers.search import router as search_router
from app.routers.sessions import router as sessions_router
from app.routers.dashboard import router as dashboard_router
from app.routers.email_logs import router as email_logs_router
from app.routers.onboarding import router as onboarding_router
from app.routers.debug import router as debug_router

# CRM
from app.routers.pipelines import router as pipelines_router
from app.routers.leads import router as leads_router
from app.routers.customers import router as customers_router
from app.routers.customer_timeline import router as customer_timeline_router
from app.routers.contacts import router as contacts_router
from app.routers.simple_services import router as simple_services_router
from app.routers.margin_control import router as margin_control_router
from app.routers.commercial_packages import router as commercial_packages_router
from app.routers.activities import router as activities_router
from app.routers.tasks import router as tasks_router
from app.routers.appointments import router as appointments_router
from app.routers.sales import goals_router, commissions_router
from app.routers.dashboards_crm import router as dashboards_crm_router

# Quoting & Contracts
from app.routers.quotes import router as quotes_router
from app.routers.contracts import router as contracts_router
from app.routers.pricing import router as pricing_router
from app.routers.pricing_hub import router as pricing_hub_router
from app.routers.quote_structure import router as quote_structure_router
from app.routers.geometry import router as geometry_router
from app.routers.parametric import router as parametric_router
from app.routers.importer import router as importer_router
from app.routers.pdf_router import router as pdf_router
from app.routers.pricing_v3 import router as pricing_v3_router
from app.routers.tech_config import router as tech_config_router
from app.routers.sites import router as sites_router

# Ops & Production (M4–M8)
from app.routers.surveys import router as surveys_router
from app.routers.sales_orders import router as sales_orders_router
from app.routers.purchasing import (
    suppliers_router, splist_router, po_router as purchase_orders_router,
    gr_router as goods_receipts_router,
)
from app.routers.inventory import (
    items_router, loc_router as stock_locations_router,
    mv_router as stock_router, inv_router as inventory_counts_router,
)
from app.routers.production import (
    bom_router, prod_router as production_orders_router,
    cut_router as cutting_lists_router, ph_router as production_phases_router,
)
from app.routers.qc import qc_router, nc_router
from app.routers.logistics import (
    fg_router, sh_router as shipments_router, crew_router as install_crews_router,
    plan_router as install_plans_router, rep_router as install_reports_router,
)
from app.routers.service_tickets import router as service_tickets_router
from app.routers.workflow import (
    router as workflow_router,
    public_router as workflow_public_router,
    customer_router as customer_portal_router,
)
from app.routers.ops_workflow import (
    router as ops_workflow_router,
    public_leads_router as public_leads_router,
)

# Finance / BI / SaaS platform
from app.routers.admin_finance import pp_router, p_router, inv_router as invoices_router
from app.routers.bi import router as bi_router
from app.routers.ai_cfo import router as ai_cfo_router
from app.routers.treasury import router as treasury_router
from app.routers.legal_entities import router as legal_entities_router
from app.routers.saas_platform import router as saas_platform_router
from app.routers.management_control import router as management_control_router
from app.routers.intercompany import router as intercompany_router
from app.routers.product_catalog import router as product_catalog_router
from app.routers.catalog import router as catalog_admin_router
from app.routers.email_settings import router as email_settings_router

# Public / Landing
from app.routers.public import (
    admin_router as public_admin_router,
    public_router as public_router_open,
)
from app.routers.landing import public_site_router, platform_site_router


# ------------------------------------------------------------------------------
# App setup
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("infissi")

app = FastAPI(title="Infissi Express Cloud API", version="1.0.0-M1")
api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"service": "Infissi Express Cloud API", "version": app.version, "milestone": "M1"}


@api.get("/health")
async def health():
    db = get_db()
    try:
        await db.command("ping")
        return {"status": "ok"}
    except Exception as e:  # noqa: BLE001 — surfaced verbatim in health payload
        return {"status": "error", "detail": str(e)}


@api.get("/config/production-status")
async def production_status():
    """Deploy report — NON expose segreti, solo booleani/label."""
    # Local imports avoid heavy config lookups at module load time.
    from app.config import is_prod_like
    from app.services.signature_provider import list_providers as _lp

    from app.services.email_config import get_mail_config as _emc
    _mail_cfg = _emc()
    email_configured = _mail_cfg.is_configured
    s3_configured = settings.STORAGE_PROVIDER == "s3" and bool(settings.S3_BUCKET)
    otp_status = "safe"
    if settings.OTP_DEBUG_ENABLED:
        otp_status = "configuration_required" if is_prod_like() else "dev_only"
    return {
        "app_env": settings.APP_ENV,
        "release_stage": settings.RELEASE_STAGE,
        "demo_mode": settings.DEMO_SEED_ENABLED,
        "test_data_enabled": settings.TEST_DATA_ENABLED,
        "is_prod_like": is_prod_like(),
        "otp": {
            "debug_enabled": settings.OTP_DEBUG_ENABLED,
            "ttl_seconds": settings.OTP_TTL_SECONDS,
            "rate_limit_max_per_window": settings.RATE_LIMIT_OTP_REQUEST_MAX,
            "rate_limit_window_sec": settings.RATE_LIMIT_OTP_REQUEST_WINDOW_SEC,
            "status": otp_status,
        },
        "email": {
            "provider": _mail_cfg.provider_name,
            "configured": email_configured,
            "status": "configured" if email_configured else "configuration_required",
            "from": _mail_cfg.mail_from if email_configured else None,
            "delivery_mode": _mail_cfg.delivery_mode,
            "test_redirect_to": _mail_cfg.test_redirect_to,
        },
        "storage": {
            "provider": settings.STORAGE_PROVIDER,
            "s3_configured": s3_configured,
            "status": "s3" if s3_configured else "local_persistent",
            "local_path": settings.STORAGE_LOCAL_PATH if settings.STORAGE_PROVIDER != "s3" else None,
        },
        "signature_providers": _lp(),
        "cors_origins": "restricted" if settings.CORS_ORIGINS not in ("*", "") else "permissive",
        "jwt": {
            "access_ttl_min": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
            "refresh_ttl_days": settings.REFRESH_TOKEN_EXPIRE_DAYS,
        },
        "features": {
            "geometry_engine": True, "importer": True, "bom_recipes": True,
            "contract_pdf": True, "otp_real": True, "signature_electronic_simple": True,
        },
    }


# ------------------------------------------------------------------------------
# Mount routers — ordered by domain for readability
# ------------------------------------------------------------------------------
FOUNDATION_ROUTERS = [
    auth_router, users_router, roles_router, permissions_router, company_router,
    audit_router, notifications_router, attachments_router, sequences_router,
    search_router, sessions_router, dashboard_router, email_logs_router,
    email_settings_router,
    onboarding_router, debug_router,
]
CRM_ROUTERS = [
    pipelines_router, leads_router, customers_router, customer_timeline_router, contacts_router,
    sites_router,   # Milestone 1 Enerhia — Cantieri
    activities_router, tasks_router, appointments_router,
    goals_router, commissions_router, dashboards_crm_router,
]
QUOTING_ROUTERS = [
    quotes_router, contracts_router, pricing_router, pricing_hub_router,
    quote_structure_router, geometry_router, parametric_router, importer_router,
    pdf_router,
    pricing_v3_router,   # Milestone 1 — endpoint autorevole POST /api/pricing/compute
    tech_config_router,  # Milestone A — Configurazione tecnica amministrabile
    simple_services_router,  # Milestone 2.14 — Servizi e prezzi semplici (dual pricing)
    margin_control_router,   # Margin & Cash Flow Control
    commercial_packages_router,  # Commercial Packages V1 (BASE/ADVANCED/PREMIUM)
]
OPS_ROUTERS = [
    surveys_router, sales_orders_router,
    suppliers_router, splist_router, purchase_orders_router, goods_receipts_router,
    items_router, stock_locations_router, stock_router, inventory_counts_router,
    bom_router, production_orders_router, cutting_lists_router, production_phases_router,
    qc_router, nc_router,
    fg_router, shipments_router, install_crews_router,
    install_plans_router, install_reports_router,
    service_tickets_router,
    workflow_router, workflow_public_router, customer_portal_router,
    ops_workflow_router, public_leads_router,
]
FINANCE_BI_ROUTERS = [
    pp_router, p_router, invoices_router,
    bi_router, ai_cfo_router,
    treasury_router, legal_entities_router,
    saas_platform_router, management_control_router, intercompany_router,
    product_catalog_router,
    catalog_admin_router,
]
PUBLIC_ROUTERS = [
    public_admin_router, public_router_open,
    public_site_router, platform_site_router,
]

for _group in (FOUNDATION_ROUTERS, CRM_ROUTERS, QUOTING_ROUTERS,
               OPS_ROUTERS, FINANCE_BI_ROUTERS, PUBLIC_ROUTERS):
    for _r in _group:
        api.include_router(_r)

app.include_router(api)


# ------------------------------------------------------------------------------
# CORS
# ------------------------------------------------------------------------------
_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
if _origins == ["*"]:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ------------------------------------------------------------------------------
# Lifecycle
# ------------------------------------------------------------------------------
@app.on_event("startup")
async def _startup():
    logger.info("Starting Infissi Express Cloud API")
    await run_seed()
    # Opzione A — catalog seed (idempotent)
    try:
        from app.seed_catalog import run_catalog_seed
        await run_catalog_seed()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Catalog seed failed: %s", exc)
    # Email templates seed + retry worker
    try:
        from app.seed_email_templates import run_email_templates_seed
        seed_report = await run_email_templates_seed()
        logger.info("email templates seed: %s", seed_report)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Email templates seed failed: %s", exc)
    try:
        from app.services.email_service import start_retry_worker
        start_retry_worker()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Email retry worker start failed: %s", exc)


@app.on_event("shutdown")
async def _shutdown():
    try:
        from app.services.email_service import stop_retry_worker
        stop_retry_worker()
    except Exception:  # noqa: BLE001
        pass
    await close_db()
