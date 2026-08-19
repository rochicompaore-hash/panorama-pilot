"""Customers router — Enerhia Operating Core (Milestone 1 Part 2).

Cambiamenti rispetto alla versione precedente:
- `customer_type` = PRIVATE | COMPANY | TO_CONFIRM (con retro-compat via
  ``normalize_customer_type``).
- Ogni Customer ha un ``customer_number`` progressivo, atomico, per tenant
  (formato ``CLI-000001``). Assegnato automaticamente in POST /customers.
- Validazione condizionale in creazione/modifica (PRIVATE/COMPANY).
- I clienti legacy senza tipo restano visualizzabili come ``TO_CONFIRM`` ma
  al primo edit la classificazione è obbligatoria.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Header
from app.db import get_db
from app.deps import require_permission, get_client_ip, get_permission_keys_for_user
from app.models_crm import Customer, CustomerCreate, CustomerUpdate, LeadAddress, ContactPerson
from app.models import new_id
from app.mongo_utils import to_mongo, from_mongo
from app.services.audit import record_audit
from app.services.concurrency import update_with_version, get_if_match_version, user_has_permission
from app.services.customer_number import next_customer_number
from app.services.customer_validation import (
    normalize_customer_type,
    validate_customer_type_on_create,
    validate_customer_type_on_update,
)

router = APIRouter(prefix="/customers", tags=["customers"])


def _hydrate_customer(doc: dict) -> dict:
    """Applica retro-compat (customer_type legacy) in output."""
    d = from_mongo(doc)
    d["customer_type"] = normalize_customer_type(d.get("customer_type"))
    return d


@router.get("")
async def list_customers(
    q: Optional[str] = None, assigned_to: Optional[str] = None,
    customer_type: Optional[str] = None,
    limit: int = Query(100, le=500), skip: int = 0,
    user: dict = Depends(require_permission("crm.customers.view")),
):
    db = get_db()
    query: dict = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if assigned_to:
        query["assigned_to"] = assigned_to
    if customer_type:
        ct = normalize_customer_type(customer_type)
        # match sia il nuovo enum sia i valori legacy corrispondenti
        if ct == "PRIVATE":
            query["customer_type"] = {"$in": ["PRIVATE", "private"]}
        elif ct == "COMPANY":
            query["customer_type"] = {"$in": ["COMPANY", "business"]}
        elif ct == "TO_CONFIRM":
            query["$or"] = [
                {"customer_type": {"$exists": False}},
                {"customer_type": None},
                {"customer_type": ""},
                {"customer_type": "TO_CONFIRM"},
            ]
    if q:
        base_or = [
            {"customer_number": {"$regex": q, "$options": "i"}},
            {"first_name": {"$regex": q, "$options": "i"}},
            {"last_name": {"$regex": q, "$options": "i"}},
            {"company_name": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
            {"phone": {"$regex": q, "$options": "i"}},
            {"vat_number": {"$regex": q, "$options": "i"}},
            {"tax_code": {"$regex": q, "$options": "i"}},
        ]
        if "$or" in query:
            query = {"$and": [query, {"$or": base_or}]}
        else:
            query["$or"] = base_or
    total = await db.customers.count_documents(query)
    docs = await db.customers.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": [_hydrate_customer(d) for d in docs]}


@router.get("/{cid}")
async def get_customer(cid: str, user: dict = Depends(require_permission("crm.customers.view"))):
    db = get_db()
    doc = await db.customers.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    return _hydrate_customer(doc)


@router.post("")
async def create_customer(
    body: CustomerCreate, request: Request,
    user: dict = Depends(require_permission("crm.customers.create")),
):
    db = get_db()
    ct = validate_customer_type_on_create(
        body.customer_type, body.first_name, body.last_name, body.company_name,
    )
    number = await next_customer_number(db, user["tenant_id"])
    c = Customer(
        id=new_id(), tenant_id=user["tenant_id"],
        customer_number=number,
        customer_type=ct,
        first_name=body.first_name, last_name=body.last_name,
        company_name=body.company_name,
        contact_person=body.contact_person or ContactPerson(),
        email=body.email, phone=body.phone, whatsapp=body.whatsapp,
        pec=body.pec, sdi_code=body.sdi_code,
        address=body.address or LeadAddress(),
        billing_address=body.billing_address,
        vat_number=body.vat_number, tax_code=body.tax_code,
        assigned_to=body.assigned_to or user["id"],
        tags=body.tags, notes=body.notes,
        created_by=user["id"], updated_by=user["id"],
    )
    await db.customers.insert_one(to_mongo(c.model_dump(by_alias=True)))
    await record_audit(action="crm.customers.create", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="customer", entity_id=c.id,
                       after={"customer_number": number, "customer_type": ct})
    # Timeline system event
    try:
        from app.routers.customer_timeline import _record_system_event  # lazy import
        await _record_system_event(db, tenant_id=user["tenant_id"], customer_id=c.id,
                                    user=user, title="Cliente creato",
                                    body=f"Anagrafica {ct} creata con codice {number}.")
    except Exception:
        pass
    return _hydrate_customer(await db.customers.find_one({"_id": c.id}))


@router.patch("/{cid}")
async def update_customer(
    cid: str, body: CustomerUpdate, request: Request,
    expected_version: Optional[int] = Depends(get_if_match_version),
    force: bool = False,
    force_reason: Optional[str] = Header(default=None, alias="X-Force-Reason"),
    user: dict = Depends(require_permission("crm.customers.edit")),
):
    db = get_db()
    current = await db.customers.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not current:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    payload = body.model_dump(exclude_unset=True)

    # Validazione customer_type (obbligatoria per legacy TO_CONFIRM)
    target_type = validate_customer_type_on_update(
        payload.get("customer_type"), current, payload,
    )
    payload["customer_type"] = target_type

    for key in ("address", "billing_address", "contact_person"):
        if key in payload and payload[key] is not None:
            payload[key] = payload[key] if isinstance(payload[key], dict) else payload[key].model_dump()

    if force:
        perms = set(await get_permission_keys_for_user(user))
        if not user_has_permission(user, perms, "records.force_override"):
            raise HTTPException(status_code=403, detail="Permesso 'records.force_override' mancante")
    updated = await update_with_version(
        collection="customers", entity_id=cid, tenant_id=user["tenant_id"],
        entity_type="customer", expected_version=expected_version,
        set_fields=payload, user=user, request=request,
        force_override=force, override_reason=force_reason, allow_consolidated=True,
    )
    await record_audit(action="crm.customers.update", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="customer", entity_id=cid, after=payload)
    if updated and isinstance(updated, dict):
        updated["customer_type"] = normalize_customer_type(updated.get("customer_type"))
    return updated


@router.delete("/{cid}")
async def delete_customer(
    cid: str, request: Request,
    user: dict = Depends(require_permission("crm.customers.delete")),
):
    db = get_db()
    doc = await db.customers.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    now = datetime.now(timezone.utc).isoformat()
    await db.customers.update_one({"_id": cid}, {"$set": {"deleted_at": now, "updated_at": now, "updated_by": user["id"]}})
    await record_audit(action="crm.customers.delete", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="customer", entity_id=cid)
    return {"ok": True}
