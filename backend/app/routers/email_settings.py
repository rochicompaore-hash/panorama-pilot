"""Email admin router — settings viewer, test-send, template CRUD, DNS check.

Endpoints (all prefixed by /api/email-settings):
  GET  /                     -> current SMTP config (NO password)
  POST /test                 -> send a rate-limited test email
  GET  /dns-check            -> SPF/DKIM/DMARC check for the mail_from domain
  GET  /templates            -> list system + tenant templates
  GET  /templates/{code}     -> single template
  PATCH /templates/{code}    -> update (creates tenant override if system)
  POST /templates/{code}/reset -> delete tenant override (revert to system)
"""
from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field, EmailStr

from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.mongo_utils import to_mongo, from_mongo
from app.models import new_id
from app.services.audit import record_audit
from app.services.email_config import get_public_config, get_mail_config
from app.services.email_service import enqueue_email
from app.services.email_dns import check_domain
from app.models_email import (
    EMAIL_TEMPLATE_CODES, EmailTemplateDoc, EmailTemplateUpdate, TestEmailRequest,
)


router = APIRouter(prefix="/email-settings", tags=["email"])

# In-memory rate limiter for test-send: max 5 requests / 5 min / user
_test_send_hits: Dict[str, list] = {}
TEST_SEND_WINDOW_SEC = 300
TEST_SEND_MAX = 5


def _rate_limit_test(user_id: str) -> None:
    now = time.time()
    hits = [t for t in _test_send_hits.get(user_id, []) if now - t < TEST_SEND_WINDOW_SEC]
    if len(hits) >= TEST_SEND_MAX:
        raise HTTPException(status_code=429, detail=(
            f"Troppi invii di test. Max {TEST_SEND_MAX} ogni {TEST_SEND_WINDOW_SEC // 60} minuti."
        ))
    hits.append(now)
    _test_send_hits[user_id] = hits


# ---------------------------------------------------------------------------
# GET / — public config viewer (safe, no password)
# ---------------------------------------------------------------------------
@router.get("")
async def get_settings(user: dict = Depends(require_permission("email.view_settings"))):
    return get_public_config()


# ---------------------------------------------------------------------------
# POST /test — invia email di test
# ---------------------------------------------------------------------------
@router.post("/test")
async def send_test(
    body: TestEmailRequest, request: Request,
    user: dict = Depends(require_permission("email.send_test")),
):
    _rate_limit_test(user["id"])
    tenant_id = user.get("tenant_id")
    ctx = dict(body.context_override or {})
    ctx.setdefault("first_name", user.get("first_name", "Test"))
    ctx.setdefault("invite_url", f"{get_mail_config().app_base_url}/accept-invitation?token=TEST-TOKEN")
    ctx.setdefault("reset_url", f"{get_mail_config().app_base_url}/reset-password?token=TEST-TOKEN")
    ctx.setdefault("customer_name", "Cliente Test")
    ctx.setdefault("quote_number", "Q-TEST-0001")
    ctx.setdefault("contract_number", "CON-TEST-0001")
    ctx.setdefault("company_name", "Panorama Pilot")
    ctx.setdefault("signature_url", f"{get_mail_config().app_base_url}/public/contract/TEST-TOKEN")
    ctx.setdefault("expires_at", "31/12/2026")
    ctx.setdefault("signed_at", "01/02/2026")

    result = await enqueue_email(
        to=body.to,
        template=body.template or "USER_INVITATION",
        context=ctx,
        tenant_id=tenant_id,
        idempotency_key=None,  # test emails always send
    )
    await record_audit(
        action="email.test_send", tenant_id=tenant_id,
        user_id=user["id"], user_email=user.get("email"),
        ip=get_client_ip(request),
        entity_type="email_log", entity_id=result.get("id"),
        after={"to": body.to, "template": body.template, "status": result.get("status")},
    )
    # Never expose stored_html/stored_text or password — only public status
    return {
        "id": result.get("id"),
        "status": result.get("status"),
        "provider": result.get("provider"),
        "delivery_mode": result.get("delivery_mode"),
        "actual_to": result.get("to"),
        "original_to": result.get("original_to"),
        "error": result.get("error"),
        "attempt_count": result.get("attempt_count"),
        "sent_at": result.get("sent_at") or result.get("updated_at") or result.get("created_at"),
        "provider_message_id": result.get("provider_message_id") or result.get("message_id"),
        # accettazione provider ≠ consegna: DELIVERED solo con webhook provider (non configurato)
        "delivery_status": result.get("delivery_status"),
    }


# ---------------------------------------------------------------------------
# GET /dns-check — SPF/DKIM/DMARC check for the mail_from domain
# ---------------------------------------------------------------------------
@router.get("/dns-check")
async def dns_check(
    domain: Optional[str] = Query(None),
    user: dict = Depends(require_permission("email.view_settings")),
):
    cfg = get_mail_config()
    mail_domain = domain or (cfg.mail_from.split("@", 1)[1] if "@" in cfg.mail_from else "")
    if not mail_domain:
        raise HTTPException(status_code=400, detail="Nessun dominio disponibile per DNS check")
    result = await check_domain(mail_domain)
    return result


# ---------------------------------------------------------------------------
# Templates CRUD
# ---------------------------------------------------------------------------
@router.get("/templates")
async def list_templates(user: dict = Depends(require_permission("email.view_settings"))):
    db = get_db()
    tenant_id = user.get("tenant_id")
    # System + tenant custom (if any)
    q = {"$or": [
        {"tenant_id": None, "is_system": True, "deleted_at": None},
        {"tenant_id": tenant_id, "deleted_at": None},
    ]}
    docs = await db.email_templates.find(q).sort("code", 1).to_list(200)
    # Merge: tenant overrides system by code
    merged: Dict[str, dict] = {}
    for d in docs:
        f = from_mongo(d)
        code = f["code"]
        if code not in merged or f.get("tenant_id") == tenant_id:
            merged[code] = {
                "code": code,
                "subject": f["subject"],
                "html_body": f["html_body"],
                "text_body": f["text_body"],
                "description": f.get("description"),
                "version": f.get("version", 1),
                "is_system": f.get("is_system", False),
                "is_custom": f.get("tenant_id") == tenant_id,
                "is_active": f.get("is_active", True),
                "updated_at": f.get("updated_at"),
            }
    return {"total": len(merged), "items": [merged[c] for c in EMAIL_TEMPLATE_CODES if c in merged]}


@router.get("/templates/{code}")
async def get_template(code: str, user: dict = Depends(require_permission("email.view_settings"))):
    if code not in EMAIL_TEMPLATE_CODES:
        raise HTTPException(status_code=404, detail=f"Template sconosciuto: {code}")
    db = get_db()
    tenant_id = user.get("tenant_id")
    custom = await db.email_templates.find_one({
        "tenant_id": tenant_id, "code": code, "deleted_at": None,
    })
    system = await db.email_templates.find_one({
        "tenant_id": None, "is_system": True, "code": code, "deleted_at": None,
    })
    doc = from_mongo(custom or system)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Template non trovato: {code}")
    return {
        "code": doc["code"], "subject": doc["subject"],
        "html_body": doc["html_body"], "text_body": doc["text_body"],
        "description": doc.get("description"),
        "version": doc.get("version", 1),
        "is_system": doc.get("is_system", False),
        "is_custom": doc.get("tenant_id") == tenant_id,
        "is_active": doc.get("is_active", True),
    }


@router.patch("/templates/{code}")
async def update_template(
    code: str, body: EmailTemplateUpdate, request: Request,
    user: dict = Depends(require_permission("email.templates.manage")),
):
    if code not in EMAIL_TEMPLATE_CODES:
        raise HTTPException(status_code=404, detail=f"Template sconosciuto: {code}")
    db = get_db()
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Utente senza tenant — impossibile personalizzare")
    # Look up existing tenant override
    now = datetime.now(timezone.utc).isoformat()
    existing = await db.email_templates.find_one({
        "tenant_id": tenant_id, "code": code, "deleted_at": None,
    })
    system = await db.email_templates.find_one({
        "tenant_id": None, "is_system": True, "code": code, "deleted_at": None,
    })
    base = from_mongo(existing or system)
    if not base:
        raise HTTPException(status_code=500, detail=f"Template di sistema {code} mancante — riesegui seed")
    updates = body.model_dump(exclude_unset=True)
    subj = updates.get("subject", base["subject"])
    html = updates.get("html_body", base["html_body"])
    text = updates.get("text_body", base["text_body"])
    desc = updates.get("description", base.get("description"))
    if existing:
        new_version = int(existing.get("version", 1)) + 1
        await db.email_templates.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "subject": subj, "html_body": html, "text_body": text,
                "description": desc, "version": new_version, "updated_at": now,
                "updated_by": user["id"],
            }},
        )
        entity_id = existing["_id"]
    else:
        doc = {
            "_id": new_id(),
            "tenant_id": tenant_id,
            "code": code,
            "subject": subj, "html_body": html, "text_body": text,
            "description": desc, "version": 1,
            "is_system": False, "is_active": True,
            "created_at": now, "updated_at": now,
            "created_by": user["id"], "updated_by": user["id"],
            "deleted_at": None,
        }
        await db.email_templates.insert_one(doc)
        entity_id = doc["_id"]
    await record_audit(
        action="email.template_update", tenant_id=tenant_id,
        user_id=user["id"], user_email=user.get("email"),
        ip=get_client_ip(request),
        entity_type="email_template", entity_id=entity_id,
        after={"code": code, "fields_changed": list(updates.keys())},
    )
    return {"ok": True, "code": code, "template_id": entity_id}


@router.post("/templates/{code}/reset")
async def reset_template(
    code: str, request: Request,
    user: dict = Depends(require_permission("email.templates.manage")),
):
    """Delete the tenant override — revert to system template."""
    if code not in EMAIL_TEMPLATE_CODES:
        raise HTTPException(status_code=404, detail=f"Template sconosciuto: {code}")
    db = get_db()
    tenant_id = user.get("tenant_id")
    now = datetime.now(timezone.utc).isoformat()
    existing = await db.email_templates.find_one({
        "tenant_id": tenant_id, "code": code, "deleted_at": None,
    })
    if not existing:
        return {"ok": True, "reverted": False, "message": "Nessuna personalizzazione da rimuovere"}
    await db.email_templates.update_one(
        {"_id": existing["_id"]},
        {"$set": {"deleted_at": now, "updated_at": now, "updated_by": user["id"]}},
    )
    await record_audit(
        action="email.template_reset", tenant_id=tenant_id,
        user_id=user["id"], user_email=user.get("email"),
        ip=get_client_ip(request),
        entity_type="email_template", entity_id=existing["_id"],
        before={"code": code},
    )
    return {"ok": True, "reverted": True, "code": code}
