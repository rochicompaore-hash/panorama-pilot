"""Tenant Email Settings router — /api/tenant-email (mittente per tenant, dominio custom via Resend, DMARC check)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.services import resend_provider
from app.services.audit import record_audit
from app.services.email_dns import check_domain
from app.services.tenant_email import (SENDER_MODES, apply_provider_domain, get_settings, public_view, resolve_sender, slugify)

router = APIRouter(prefix="/tenant-email", tags=["tenant-email"])
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9-]+\.)+[a-z]{2,}$")


class SettingsPatch(BaseModel):
    sender_mode: Optional[str] = None
    from_name: Optional[str] = Field(None, max_length=80)
    managed_local_part: Optional[str] = Field(None, max_length=40)
    custom_from_local_part: Optional[str] = Field(None, max_length=40)
    reply_to: Optional[str] = None
    support_email: Optional[str] = None
    sales_email: Optional[str] = None
    signature: Optional[str] = Field(None, max_length=2000)


class DomainCreate(BaseModel):
    domain: str


async def _view(db, tenant_id):
    return public_view(await get_settings(db, tenant_id), await resolve_sender(db, tenant_id))


@router.get("/settings")
async def get_tenant_settings(user: dict = Depends(require_permission("email.view_settings"))):
    return await _view(get_db(), user["tenant_id"])


@router.patch("/settings")
async def patch_tenant_settings(body: SettingsPatch, request: Request, user: dict = Depends(require_permission("email.manage_settings"))):
    db = get_db()
    s = await get_settings(db, user["tenant_id"])
    upd = body.model_dump(exclude_unset=True)
    if "sender_mode" in upd and upd["sender_mode"] not in SENDER_MODES:
        raise HTTPException(400, {"code": "SENDER_MODE_INVALID", "allowed": list(SENDER_MODES)})
    if upd.get("sender_mode") == "CUSTOM_VERIFIED_DOMAIN" and s.get("domain_status") != "VERIFIED":
        raise HTTPException(400, {"code": "DOMAIN_NOT_VERIFIED", "message": "Il dominio personalizzato deve essere VERIFIED prima di poter essere usato come mittente"})
    for k in ("reply_to", "support_email", "sales_email"):
        if upd.get(k) and not _EMAIL_RE.match(upd[k]):
            raise HTTPException(400, {"code": "EMAIL_INVALID", "field": k})
    for k in ("managed_local_part", "custom_from_local_part"):
        if upd.get(k):
            upd[k] = slugify(upd[k])
    s.update(upd)
    s["updated_at"] = datetime.now(timezone.utc).isoformat()
    s["updated_by"] = user["id"]
    await db.tenant_email_settings.replace_one({"_id": user["tenant_id"]}, s, upsert=True)
    await record_audit(action="tenant_email.settings_update", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"],
                       ip=get_client_ip(request), entity_type="tenant_email_settings", entity_id=user["tenant_id"], after={"fields": list(upd.keys())})
    return await _view(db, user["tenant_id"])


@router.post("/domain")
async def create_custom_domain(body: DomainCreate, request: Request, user: dict = Depends(require_permission("email.manage_settings"))):
    db = get_db()
    domain = body.domain.strip().lower()
    if not _DOMAIN_RE.match(domain):
        raise HTTPException(400, {"code": "DOMAIN_INVALID"})
    other = await db.tenant_email_settings.find_one({"custom_domain": domain, "tenant_id": {"$ne": user["tenant_id"]}})
    if other:
        raise HTTPException(409, {"code": "DOMAIN_ALREADY_CLAIMED", "message": "Dominio già registrato da un altro tenant"})
    if not resend_provider.is_configured():
        raise HTTPException(503, {"code": "RESEND_CONFIGURATION", "status": "BLOCKED_BY_SECRET"})
    s = await get_settings(db, user["tenant_id"])
    try:
        d = await resend_provider.create_domain(domain)
    except resend_provider.ResendError as e:
        raise HTTPException(502, {"code": "PROVIDER_DOMAIN_ERROR", "message": e.message})
    s["custom_domain"] = domain
    apply_provider_domain(s, d)
    s["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.tenant_email_settings.replace_one({"_id": user["tenant_id"]}, s, upsert=True)
    await record_audit(action="tenant_email.domain_create", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"],
                       ip=get_client_ip(request), entity_type="tenant_email_settings", entity_id=user["tenant_id"], after={"domain": domain, "status": s["domain_status"]})
    return await _view(db, user["tenant_id"])


@router.post("/domain/verify")
async def verify_custom_domain(request: Request, user: dict = Depends(require_permission("email.manage_settings"))):
    db = get_db()
    s = await get_settings(db, user["tenant_id"])
    if not s.get("provider_domain_id"):
        raise HTTPException(400, {"code": "DOMAIN_NOT_CONFIGURED"})
    if not resend_provider.is_configured():
        raise HTTPException(503, {"code": "RESEND_CONFIGURATION", "status": "BLOCKED_BY_SECRET"})
    try:
        await resend_provider.verify_domain(s["provider_domain_id"])
        d = await resend_provider.get_domain(s["provider_domain_id"])
    except resend_provider.ResendError as e:
        raise HTTPException(502, {"code": "PROVIDER_DOMAIN_ERROR", "message": e.message})
    before = s.get("domain_status")
    apply_provider_domain(s, d)
    dmarc = await check_domain(s["custom_domain"])
    s["dmarc_status"] = "CONFIGURED" if (dmarc.get("dmarc") or {}).get("found") else "MISSING"
    s["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.tenant_email_settings.replace_one({"_id": user["tenant_id"]}, s, upsert=True)
    await record_audit(action="tenant_email.domain_verify", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"],
                       ip=get_client_ip(request), entity_type="tenant_email_settings", entity_id=user["tenant_id"], before={"status": before}, after={"status": s["domain_status"]})
    return await _view(db, user["tenant_id"])


@router.delete("/domain")
async def remove_custom_domain(request: Request, user: dict = Depends(require_permission("email.manage_settings"))):
    db = get_db()
    s = await get_settings(db, user["tenant_id"])
    s.update({"custom_domain": None, "domain_status": "NOT_CONFIGURED", "provider_domain_id": None, "verified_at": None, "dns_records": [],
              "sender_mode": "PANORAMA_MANAGED", "dmarc_status": "MISSING", "updated_at": datetime.now(timezone.utc).isoformat()})
    await db.tenant_email_settings.replace_one({"_id": user["tenant_id"]}, s, upsert=True)
    await record_audit(action="tenant_email.domain_remove", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"],
                       ip=get_client_ip(request), entity_type="tenant_email_settings", entity_id=user["tenant_id"])
    return await _view(db, user["tenant_id"])
