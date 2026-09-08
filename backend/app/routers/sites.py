"""Sites (Cantieri) — Milestone 1 Enerhia Operating Core.

Cantiere = immobile di intervento associato a un customer_id.
Un cliente può avere più cantieri. Riutilizzati in preventivo/rilievo/produzione/posa.

Non-distruttivo verso Customer esistente: nuova collection `sites` separata.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db import get_db
from app.deps import require_permission


router = APIRouter(prefix="/sites", tags=["Cantieri"])


PROPERTY_TYPES = {"APPARTAMENTO", "CASA_SINGOLA", "BIFAMILIARE", "CONDOMINIO",
                  "ATTIVITA_COMMERCIALE", "ALTRO"}



SITE_REQUIRED_ERRORS = {
    "SITE_ADDRESS_REQUIRED": ("address", "street_number", "postal_code", "city", "province"),
    "SITE_FLOOR_REQUIRED": ("floor",),
    "SITE_ELEVATOR_REQUIRED": ("has_elevator",),
    "SITE_PHONE_REQUIRED": ("site_contact_phone",),
}


def site_missing_codes(data: dict) -> list:
    """msg 402 Lotto 2 — dati obbligatori cantiere (indirizzo completo, piano, ascensore, telefono)."""
    codes = []
    for code, fields in SITE_REQUIRED_ERRORS.items():
        for f in fields:
            v = data.get(f)
            if v is None or (isinstance(v, str) and not v.strip()):
                codes.append(code)
                break
    return codes


def _assert_site_complete(data: dict):
    codes = site_missing_codes(data)
    if codes:
        raise HTTPException(400, detail={"code": codes[0], "codes": codes,
                                         "message": "Dati cantiere obbligatori mancanti: " + ", ".join(codes)})


class SiteCreate(BaseModel):
    customer_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=200)
    address: Optional[str] = None
    street_number: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    country: Optional[str] = "IT"
    floor: Optional[str] = None
    has_elevator: Optional[bool] = None
    property_type: Optional[str] = None
    accessibility_notes: Optional[str] = None
    unloading_notes: Optional[str] = None
    logistics_notes: Optional[str] = None
    site_contact_name: Optional[str] = None
    site_contact_phone: Optional[str] = None


class SiteUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    street_number: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    country: Optional[str] = None
    floor: Optional[str] = None
    has_elevator: Optional[bool] = None
    property_type: Optional[str] = None
    accessibility_notes: Optional[str] = None
    unloading_notes: Optional[str] = None
    logistics_notes: Optional[str] = None
    site_contact_name: Optional[str] = None
    site_contact_phone: Optional[str] = None


async def _next_site_number(db, tenant_id: str) -> str:
    """CANT-YYYY-NNNNN progressivo per tenant."""
    year = datetime.now(timezone.utc).year
    cnt = await db.sites.count_documents({"tenant_id": tenant_id})
    return f"CANT-{year}-{(cnt + 1):05d}"


@router.get("")
async def list_sites(customer_id: Optional[str] = Query(None),
                     q: Optional[str] = Query(None),
                     user: dict = Depends(require_permission("crm.customers.view"))):
    db = get_db()
    query: Dict[str, Any] = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if customer_id:
        query["customer_id"] = customer_id
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"city": {"$regex": q, "$options": "i"}},
            {"site_number": {"$regex": q, "$options": "i"}},
        ]
    items = []
    async for d in db.sites.find(query).sort("created_at", -1).limit(200):
        d["id"] = d.pop("_id")
        items.append(d)
    return {"items": items, "total": len(items)}


@router.post("", status_code=201)
async def create_site(payload: SiteCreate,
                       user: dict = Depends(require_permission("crm.customers.edit"))):
    if payload.property_type and payload.property_type not in PROPERTY_TYPES:
        raise HTTPException(400, f"property_type must be one of {PROPERTY_TYPES}")
    _assert_site_complete(payload.model_dump())
    db = get_db()
    # Verifica customer esiste e appartiene al tenant
    cust = await db.customers.find_one({"_id": payload.customer_id,
                                          "tenant_id": user["tenant_id"], "deleted_at": None})
    if not cust:
        raise HTTPException(404, "Customer not found or tenant mismatch")
    now = datetime.now(timezone.utc).isoformat()
    sid = str(uuid.uuid4())
    site_number = await _next_site_number(db, user["tenant_id"])
    doc = {
        "_id": sid, "tenant_id": user["tenant_id"], "site_number": site_number,
        **payload.model_dump(exclude_unset=False),
        "created_at": now, "created_by": user.get("email") or user["id"],
        "updated_at": now, "deleted_at": None,
    }
    await db.sites.insert_one(doc)
    doc["id"] = doc.pop("_id")
    # Timeline system event sul cliente
    try:
        from app.routers.customer_timeline import _record_system_event
        await _record_system_event(db, tenant_id=user["tenant_id"], customer_id=payload.customer_id,
                                    user=user, site_id=doc["id"],
                                    title=f"Cantiere {site_number} creato",
                                    body=f"{payload.name}" + (f" · {payload.city}" if payload.city else ""))
    except Exception:
        pass
    return doc


@router.get("/{site_id}")
async def get_site(site_id: str,
                    user: dict = Depends(require_permission("crm.customers.view"))):
    db = get_db()
    d = await db.sites.find_one({"_id": site_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not d:
        raise HTTPException(404, "Site not found")
    d["id"] = d.pop("_id")
    return d


@router.patch("/{site_id}")
async def update_site(site_id: str, payload: SiteUpdate,
                       user: dict = Depends(require_permission("crm.customers.edit"))):
    if payload.property_type and payload.property_type not in PROPERTY_TYPES:
        raise HTTPException(400, f"property_type must be one of {PROPERTY_TYPES}")
    db = get_db()
    changes = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    _existing = await db.sites.find_one({"_id": site_id, "tenant_id": user["tenant_id"], "deleted_at": None}) or {}
    _assert_site_complete({**_existing, **changes})
    if not changes:
        raise HTTPException(400, "No changes")
    changes["updated_at"] = datetime.now(timezone.utc).isoformat()
    changes["updated_by"] = user.get("email") or user["id"]
    r = await db.sites.update_one(
        {"_id": site_id, "tenant_id": user["tenant_id"], "deleted_at": None},
        {"$set": changes},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Site not found")
    d = await db.sites.find_one({"_id": site_id})
    d["id"] = d.pop("_id")
    return d


@router.delete("/{site_id}")
async def delete_site(site_id: str,
                       user: dict = Depends(require_permission("crm.customers.edit"))):
    db = get_db()
    r = await db.sites.update_one(
        {"_id": site_id, "tenant_id": user["tenant_id"], "deleted_at": None},
        {"$set": {"deleted_at": datetime.now(timezone.utc).isoformat(),
                   "deleted_by": user.get("email") or user["id"]}},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Site not found")
    return {"ok": True}
