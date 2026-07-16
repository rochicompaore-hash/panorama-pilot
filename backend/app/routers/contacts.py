"""Contacts router."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Header
from app.db import get_db
from app.deps import require_permission, get_client_ip, get_permission_keys_for_user
from app.models_crm import Contact, ContactCreate, ContactUpdate
from app.models import new_id
from app.mongo_utils import to_mongo, from_mongo
from app.services.audit import record_audit
from app.services.concurrency import update_with_version, get_if_match_version, user_has_permission

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("")
async def list_contacts(
    q: Optional[str] = None, customer_id: Optional[str] = None, lead_id: Optional[str] = None,
    limit: int = Query(100, le=500), skip: int = 0,
    user: dict = Depends(require_permission("crm.contacts.view")),
):
    db = get_db()
    query: dict = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if customer_id:
        query["customer_id"] = customer_id
    if lead_id:
        query["lead_id"] = lead_id
    if q:
        query["$or"] = [
            {"first_name": {"$regex": q, "$options": "i"}},
            {"last_name": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
            {"phone": {"$regex": q, "$options": "i"}},
            {"role": {"$regex": q, "$options": "i"}},
        ]
    total = await db.contacts.count_documents(query)
    docs = await db.contacts.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": [from_mongo(d) for d in docs]}


@router.post("")
async def create_contact(
    body: ContactCreate, request: Request,
    user: dict = Depends(require_permission("crm.contacts.manage")),
):
    db = get_db()
    c = Contact(
        id=new_id(), tenant_id=user["tenant_id"],
        first_name=body.first_name, last_name=body.last_name, role=body.role,
        email=body.email, phone=body.phone, whatsapp=body.whatsapp, notes=body.notes,
        customer_id=body.customer_id, lead_id=body.lead_id, is_primary=body.is_primary,
        created_by=user["id"], updated_by=user["id"],
    )
    await db.contacts.insert_one(to_mongo(c.model_dump(by_alias=True)))
    await record_audit(action="crm.contacts.create", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="contact", entity_id=c.id, after=body.model_dump())
    return from_mongo(await db.contacts.find_one({"_id": c.id}))


@router.patch("/{cid}")
async def update_contact(
    cid: str, body: ContactUpdate, request: Request,
    expected_version: Optional[int] = Depends(get_if_match_version),
    force: bool = False,
    force_reason: Optional[str] = Header(default=None, alias="X-Force-Reason"),
    user: dict = Depends(require_permission("crm.contacts.manage")),
):
    payload = body.model_dump(exclude_unset=True)
    if force:
        perms = set(await get_permission_keys_for_user(user))
        if not user_has_permission(user, perms, "records.force_override"):
            raise HTTPException(status_code=403, detail="Permesso 'records.force_override' mancante")
    updated = await update_with_version(
        collection="contacts", entity_id=cid, tenant_id=user["tenant_id"],
        entity_type="contact", expected_version=expected_version,
        set_fields=payload, user=user, request=request,
        force_override=force, override_reason=force_reason, allow_consolidated=True,
    )
    await record_audit(action="crm.contacts.update", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="contact", entity_id=cid, after=payload)
    return updated


@router.delete("/{cid}")
async def delete_contact(
    cid: str, request: Request,
    user: dict = Depends(require_permission("crm.contacts.manage")),
):
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.contacts.update_one({"_id": cid, "tenant_id": user["tenant_id"]},
                                  {"$set": {"deleted_at": now, "updated_at": now, "updated_by": user["id"]}})
    return {"ok": True}
