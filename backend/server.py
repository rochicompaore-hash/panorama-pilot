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
