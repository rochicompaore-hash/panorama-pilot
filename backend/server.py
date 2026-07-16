"""Main FastAPI application entrypoint for Infissi Express Cloud (M1)."""
from __future__ import annotations
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

import os
import logging
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import get_db, close_db
from app.seed import run_seed

# Routers
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
from app.routers.pipelines import router as pipelines_router
from app.routers.leads import router as leads_router
from app.routers.customers import router as customers_router
from app.routers.contacts import router as contacts_router
from app.routers.activities import router as activities_router
from app.routers.tasks import router as tasks_router
from app.routers.appointments import router as appointments_router
from app.routers.sales import goals_router, commissions_router
from app.routers.dashboards_crm import router as dashboards_crm_router
from app.routers.quotes import router as quotes_router
from app.routers.contracts import router as contracts_router
from app.routers.pricing import router as pricing_router
from app.routers.pdf_router import router as pdf_router
from app.routers.public import admin_router as public_admin_router, public_router as public_router_open
from app.routers.debug import router as debug_router
# M4..M17 — Operational ERP routers
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
from app.routers.admin_finance import pp_router, p_router, inv_router as invoices_router
from app.routers.bi import router as bi_router
from app.routers.ai_cfo import router as ai_cfo_router
from app.routers.parametric import router as parametric_router
from app.routers.workflow import router as workflow_router, public_router as workflow_public_router, customer_router as customer_portal_router
from app.routers.ops_workflow import router as ops_workflow_router, public_leads_router as public_leads_router
from app.routers.treasury import router as treasury_router
from app.routers.legal_entities import router as legal_entities_router
from app.routers.saas_platform import router as saas_platform_router
from app.routers.management_control import router as management_control_router
from app.routers.intercompany import router as intercompany_router
from app.routers.product_catalog import router as product_catalog_router
from app.routers.landing import public_site_router, platform_site_router
from app.routers.quote_structure import router as quote_structure_router
from app.routers.pricing_hub import router as pricing_hub_router
from app.routers.geometry import router as geometry_router
from app.routers.importer import router as importer_router

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
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@api.get("/config/production-status")
async def production_status():
    """Stato configurazioni per report deploy. NON espone segreti — solo booleani/labels."""
    from app.config import settings, is_prod_like
    from app.services.signature_provider import list_providers as _lp
    email_configured = bool(settings.RESEND_API_KEY) and settings.EMAIL_PROVIDER != "mock"
    s3_configured = settings.STORAGE_PROVIDER == "s3" and bool(settings.S3_BUCKET)
    providers = _lp()
    return {
        "app_env": settings.APP_ENV,
        "is_prod_like": is_prod_like(),
        "otp": {
            "debug_enabled": settings.OTP_DEBUG_ENABLED,
            "ttl_seconds": settings.OTP_TTL_SECONDS,
            "rate_limit_max_per_window": settings.RATE_LIMIT_OTP_REQUEST_MAX,
            "rate_limit_window_sec": settings.RATE_LIMIT_OTP_REQUEST_WINDOW_SEC,
            "status": "safe" if not settings.OTP_DEBUG_ENABLED else ("configuration_required" if is_prod_like() else "dev_only"),
        },
        "email": {
            "provider": settings.EMAIL_PROVIDER,
            "configured": email_configured,
            "status": "configured" if email_configured else "configuration_required",
            "from": settings.EMAIL_FROM if email_configured else None,
        },
        "storage": {
            "provider": settings.STORAGE_PROVIDER,
            "s3_configured": s3_configured,
            "status": "s3" if s3_configured else "local_persistent",
            "local_path": settings.STORAGE_LOCAL_PATH if settings.STORAGE_PROVIDER != "s3" else None,
        },
        "signature_providers": providers,
        "cors_origins": "restricted" if settings.CORS_ORIGINS not in ("*", "") else "permissive",
        "jwt": {"access_ttl_min": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
                 "refresh_ttl_days": settings.REFRESH_TOKEN_EXPIRE_DAYS},
        "features": {
            "geometry_engine": True, "importer": True, "bom_recipes": True,
            "contract_pdf": True, "otp_real": True, "signature_electronic_simple": True,
        },
    }


# Mount domain routers under /api
api.include_router(auth_router)
api.include_router(users_router)
api.include_router(roles_router)
api.include_router(permissions_router)
api.include_router(company_router)
api.include_router(audit_router)
api.include_router(notifications_router)
api.include_router(attachments_router)
api.include_router(sequences_router)
api.include_router(search_router)
api.include_router(sessions_router)
api.include_router(dashboard_router)
api.include_router(email_logs_router)
api.include_router(onboarding_router)
api.include_router(pipelines_router)
api.include_router(leads_router)
api.include_router(customers_router)
api.include_router(contacts_router)
api.include_router(activities_router)
api.include_router(tasks_router)
api.include_router(appointments_router)
api.include_router(goals_router)
api.include_router(commissions_router)
api.include_router(dashboards_crm_router)
api.include_router(quotes_router)
api.include_router(contracts_router)
api.include_router(pricing_router)
api.include_router(pdf_router)
api.include_router(public_admin_router)
api.include_router(public_router_open)
api.include_router(debug_router)
# M4..M17 register
api.include_router(surveys_router)
api.include_router(sales_orders_router)
api.include_router(suppliers_router)
api.include_router(splist_router)
api.include_router(purchase_orders_router)
api.include_router(goods_receipts_router)
api.include_router(items_router)
api.include_router(stock_locations_router)
api.include_router(stock_router)
api.include_router(inventory_counts_router)
api.include_router(bom_router)
api.include_router(production_orders_router)
api.include_router(cutting_lists_router)
api.include_router(production_phases_router)
api.include_router(qc_router)
api.include_router(nc_router)
api.include_router(fg_router)
api.include_router(shipments_router)
api.include_router(install_crews_router)
api.include_router(install_plans_router)
api.include_router(install_reports_router)
api.include_router(service_tickets_router)
api.include_router(pp_router)
api.include_router(p_router)
api.include_router(invoices_router)
api.include_router(bi_router)
api.include_router(ai_cfo_router)
api.include_router(parametric_router)
api.include_router(workflow_router)
api.include_router(workflow_public_router)
api.include_router(customer_portal_router)
api.include_router(ops_workflow_router)
api.include_router(public_leads_router)
api.include_router(treasury_router)
api.include_router(legal_entities_router)
api.include_router(saas_platform_router)
api.include_router(management_control_router)
api.include_router(intercompany_router)
api.include_router(product_catalog_router)
api.include_router(public_site_router)
api.include_router(platform_site_router)
api.include_router(quote_structure_router)
api.include_router(pricing_hub_router)
api.include_router(geometry_router)
api.include_router(importer_router)

app.include_router(api)

# CORS
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
# Special case: when CORS_ORIGINS == "*", browsers reject credentialed requests. Use regex allow-all.
if origins == ["*"]:
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
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.on_event("startup")
async def _startup():
    logger.info("Starting Infissi Express Cloud API")
    await run_seed()


@app.on_event("shutdown")
async def _shutdown():
    await close_db()
