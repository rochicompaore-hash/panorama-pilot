"""Onboarding wizard endpoints.
State lives in company.onboarding dict.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from app.config import settings
from app.db import get_db
from app.deps import get_current_user, require_permission, get_client_ip
from app.models import Invitation, new_id
from app.models_crm import (
    OnboardingStepCompany, OnboardingStepLogo, OnboardingStepSequences,
    OnboardingStepInvite, OnboardingStepFirstLead, Lead, LeadAddress,
)
from app.mongo_utils import to_mongo, from_mongo
from app.security import generate_secure_token, hash_token
from app.services.audit import record_audit
from app.services.email import send_email, render_invitation
from app.services.timeline import record_activity
from app.routers.pipelines import seed_default_pipeline

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/state")
async def get_state(user: dict = Depends(get_current_user)):
    db = get_db()
    company = await db.companies.find_one({"_id": user["tenant_id"]})
    ob = (company or {}).get("onboarding") or {"step": 0, "completed": False}
    return {"state": ob, "company_name": (company or {}).get("name")}


async def _set_state(tenant_id: str, step: int, completed: bool = False, extra: dict | None = None):
    db = get_db()
    update = {"onboarding.step": step, "onboarding.completed": completed}
    if completed:
        update["onboarding.completed_at"] = datetime.now(timezone.utc).isoformat()
    if extra:
        for k, v in extra.items():
            update[f"onboarding.data.{k}"] = v
    await db.companies.update_one({"_id": tenant_id}, {"$set": update})


@router.post("/step-company")
async def step_company(body: OnboardingStepCompany, request: Request,
                       user: dict = Depends(require_permission("company.edit"))):
    db = get_db()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    updates["updated_by"] = user["id"]
    await db.companies.update_one({"_id": user["tenant_id"]}, {"$set": updates})
    await _set_state(user["tenant_id"], step=1)
    await record_audit(action="onboarding.step_company", tenant_id=user["tenant_id"],
                       user_id=user["id"], user_email=user["email"], ip=get_client_ip(request))
    return {"ok": True, "next_step": 1}


@router.post("/step-logo")
async def step_logo(body: OnboardingStepLogo, request: Request,
                    user: dict = Depends(require_permission("company.edit"))):
    db = get_db()
    if body.logo_url:
        await db.companies.update_one({"_id": user["tenant_id"]}, {"$set": {"logo_url": body.logo_url}})
    await _set_state(user["tenant_id"], step=2)
    return {"ok": True, "next_step": 2}


@router.post("/step-sequences")
async def step_sequences(body: OnboardingStepSequences, request: Request,
                         user: dict = Depends(require_permission("sequences.manage"))):
    db = get_db()
    for key, prefix in [("quote", body.quote_prefix), ("order", body.order_prefix)]:
        await db.sequences.update_one(
            {"tenant_id": user["tenant_id"], "key": key},
            {"$set": {
                "prefix": prefix,
                "padding": body.quote_padding if key == "quote" else body.order_padding,
                "year_reset": body.year_reset,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": user["id"],
            }}, upsert=False,
        )
    await _set_state(user["tenant_id"], step=3)
    return {"ok": True, "next_step": 3}


@router.post("/step-invite")
async def step_invite(body: OnboardingStepInvite, request: Request,
                      user: dict = Depends(require_permission("users.create"))):
    db = get_db()
    email = body.email.lower().strip()
    # find role by slug (uses name mapping)
    from app.permissions import PREDEFINED_ROLES
    role_name = PREDEFINED_ROLES.get(body.role_slug or "commerciale", {}).get("name", "Commerciale")
    role = await db.roles.find_one({"tenant_id": user["tenant_id"], "name": role_name})
    role_ids = [role["_id"]] if role else []

    existing = await db.users.find_one({"email": email})
    if not existing:
        from app.models import User
        u = User(
            id=new_id(), tenant_id=user["tenant_id"], email=email,
            first_name=body.first_name, last_name=body.last_name,
            role_ids=role_ids, is_active=True, must_change_password=True,
            password_hash=None, created_by=user["id"], updated_by=user["id"],
        )
        await db.users.insert_one(to_mongo(u.model_dump(by_alias=True)))

    raw = generate_secure_token(48)
    inv = Invitation(
        id=new_id(), tenant_id=user["tenant_id"], email=email,
        role_ids=role_ids, token_hash=hash_token(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.INVITATION_EXPIRE_HOURS),
        invited_by=user["id"], created_by=user["id"], updated_by=user["id"],
    )
    await db.invitations.insert_one(to_mongo(inv.model_dump(by_alias=True)))
    invite_url = f"{settings.APP_BASE_URL}/accept-invitation?token={raw}"
    company = await db.companies.find_one({"_id": user["tenant_id"]})
    subject, html, text = render_invitation((company or {}).get("name") or "Infissi Express Cloud", invite_url)
    await send_email(email, subject, "invitation", html, text)
    await _set_state(user["tenant_id"], step=4, extra={"invited_email": email})
    return {"ok": True, "next_step": 4, "invitation_url": invite_url}


@router.post("/step-first-lead")
async def step_first_lead(body: OnboardingStepFirstLead, request: Request,
                          user: dict = Depends(require_permission("crm.leads.create"))):
    db = get_db()
    pipeline_id = await seed_default_pipeline(user["tenant_id"])
    pipe = await db.pipelines.find_one({"_id": pipeline_id})
    first_stage = pipe["stages"][0] if pipe.get("stages") else None
    lead = Lead(
        id=new_id(), tenant_id=user["tenant_id"],
        first_name=body.first_name, last_name=body.last_name,
        email=body.email, phone=body.phone,
        source=body.source, source_detail="Onboarding wizard",
        pipeline_id=pipeline_id,
        stage_id=first_stage["id"] if first_stage else None,
        probability=first_stage["probability_default"] if first_stage else 20,
        estimated_value=body.estimated_value,
        assigned_to=user["id"],
        address=LeadAddress(),
        tags=["onboarding-demo"],
        created_by=user["id"], updated_by=user["id"],
    )
    await db.leads.insert_one(to_mongo(lead.model_dump(by_alias=True)))
    display = f"{lead.first_name or ''} {lead.last_name or ''}".strip() or "Lead onboarding"
    await record_activity(
        tenant_id=user["tenant_id"], type="lead_created",
        subject=f"Primo lead di esempio: {display}",
        lead_id=lead.id, user_id=user["id"], user_email=user["email"],
        meta={"onboarding": True},
    )
    await _set_state(user["tenant_id"], step=5, extra={"first_lead_id": lead.id})
    return {"ok": True, "next_step": 5, "lead_id": lead.id}


@router.post("/complete")
async def complete_onboarding(user: dict = Depends(get_current_user)):
    await _set_state(user["tenant_id"], step=6, completed=True)
    await record_audit(action="onboarding.completed", tenant_id=user["tenant_id"],
                       user_id=user["id"], user_email=user["email"])
    return {"ok": True}


@router.post("/skip")
async def skip_onboarding(user: dict = Depends(get_current_user)):
    await _set_state(user["tenant_id"], step=6, completed=True)
    return {"ok": True}
