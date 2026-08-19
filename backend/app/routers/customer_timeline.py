"""Customer Timeline router — Enerhia Operating Core (Milestone 1 Part 2).

Cronologia di eventi strutturata per un cliente (e opzionalmente cantiere).

Modello:
- CALL / FOLLOW_UP / COMMERCIAL_NOTE / TECHNICAL_NOTE / ADMIN_NOTE /
  INSTALLATION_NOTE / SUPPORT_NOTE / SYSTEM_EVENT
- channel opzionale (PHONE / EMAIL / WHATSAPP / IN_PERSON / SYSTEM / OTHER)
- event_source: MANUAL o SYSTEM. Gli eventi SYSTEM sono read-only e vengono
  creati esclusivamente dal backend.

RBAC: ogni utente autenticato del tenant che possieda ``crm.customers.view`` sul
cliente in oggetto può leggere; ``crm.customers.edit`` per creare eventi MANUAL.
La stessa dipendenza è già ereditata da customers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db import get_db
from app.deps import require_permission


router = APIRouter(prefix="/customers", tags=["Timeline"])


CATEGORIES = {
    "CALL", "FOLLOW_UP", "COMMERCIAL_NOTE", "TECHNICAL_NOTE",
    "ADMIN_NOTE", "INSTALLATION_NOTE", "SUPPORT_NOTE", "SYSTEM_EVENT",
}

CHANNELS = {"PHONE", "EMAIL", "WHATSAPP", "IN_PERSON", "SYSTEM", "OTHER"}

VISIBILITY = {"INTERNAL", "SHARED"}  # SHARED = visibile anche a ruoli allargati (posatori, etc.)


class TimelineEventCreate(BaseModel):
    category: str = Field(..., min_length=1)
    channel: Optional[str] = None
    title: Optional[str] = None
    body: str = Field(..., min_length=1, max_length=4000)
    site_id: Optional[str] = None
    visibility: str = "INTERNAL"


async def _record_system_event(db, *, tenant_id: str, customer_id: str, user: Dict[str, Any],
                                title: str, body: str, site_id: Optional[str] = None) -> None:
    """Inserisce un evento SYSTEM read-only. Usato dai router (crea cliente,
    crea cantiere, crea preventivo, ecc.). Non solleva errori: se qualcosa va
    storto la timeline non blocca il flusso principale."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "site_id": site_id,
            "category": "SYSTEM_EVENT",
            "channel": "SYSTEM",
            "title": title,
            "body": body,
            "created_by_user_id": user.get("id"),
            "created_by_name": user.get("full_name") or user.get("email"),
            "created_by_role": (user.get("role") or "system").lower(),
            "created_at": now,
            "visibility": "INTERNAL",
            "event_source": "SYSTEM",
            "deleted_at": None,
        }
        await db.customer_timeline.insert_one(doc)
    except Exception:
        # Timeline non deve mai bloccare l'operazione principale
        pass


@router.get("/{customer_id}/timeline")
async def list_timeline(
    customer_id: str,
    site_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(200, le=500),
    user: dict = Depends(require_permission("crm.customers.view")),
):
    db = get_db()
    cust = await db.customers.find_one({"_id": customer_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not cust:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    query: Dict[str, Any] = {
        "tenant_id": user["tenant_id"],
        "customer_id": customer_id,
        "deleted_at": None,
    }
    if site_id:
        query["site_id"] = site_id
    if category:
        query["category"] = category
    items: List[Dict[str, Any]] = []
    async for d in db.customer_timeline.find(query).sort("created_at", -1).limit(limit):
        d["id"] = d.pop("_id")
        items.append(d)
    return {"items": items, "total": len(items)}


@router.post("/{customer_id}/timeline", status_code=201)
async def create_timeline_event(
    customer_id: str,
    payload: TimelineEventCreate,
    user: dict = Depends(require_permission("crm.customers.edit")),
):
    if payload.category not in CATEGORIES:
        raise HTTPException(400, {"code": "INVALID_CATEGORY",
                                    "message": f"category must be one of {sorted(CATEGORIES)}"})
    if payload.category == "SYSTEM_EVENT":
        raise HTTPException(400, {"code": "SYSTEM_EVENT_READONLY",
                                    "message": "Gli eventi SYSTEM sono generati automaticamente."})
    if payload.channel and payload.channel not in CHANNELS:
        raise HTTPException(400, {"code": "INVALID_CHANNEL",
                                    "message": f"channel must be one of {sorted(CHANNELS)}"})
    if payload.visibility not in VISIBILITY:
        raise HTTPException(400, {"code": "INVALID_VISIBILITY",
                                    "message": f"visibility must be one of {sorted(VISIBILITY)}"})

    db = get_db()
    cust = await db.customers.find_one({"_id": customer_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not cust:
        raise HTTPException(404, "Cliente non trovato")
    if payload.site_id:
        site = await db.sites.find_one({"_id": payload.site_id, "tenant_id": user["tenant_id"],
                                          "customer_id": customer_id, "deleted_at": None})
        if not site:
            raise HTTPException(400, "site_id non valido per il cliente indicato")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "_id": str(uuid.uuid4()),
        "tenant_id": user["tenant_id"],
        "customer_id": customer_id,
        "site_id": payload.site_id,
        "category": payload.category,
        "channel": payload.channel,
        "title": payload.title,
        "body": payload.body,
        "created_by_user_id": user.get("id"),
        "created_by_name": user.get("full_name") or user.get("email"),
        "created_by_role": (user.get("role") or "").lower() or None,
        "created_at": now,
        "visibility": payload.visibility,
        "event_source": "MANUAL",
        "deleted_at": None,
    }
    await db.customer_timeline.insert_one(doc)
    doc["id"] = doc.pop("_id")
    return doc


@router.delete("/{customer_id}/timeline/{event_id}")
async def delete_timeline_event(
    customer_id: str,
    event_id: str,
    user: dict = Depends(require_permission("crm.customers.edit")),
):
    db = get_db()
    ev = await db.customer_timeline.find_one({
        "_id": event_id, "tenant_id": user["tenant_id"],
        "customer_id": customer_id, "deleted_at": None,
    })
    if not ev:
        raise HTTPException(404, "Evento non trovato")
    if ev.get("event_source") == "SYSTEM":
        raise HTTPException(400, {"code": "SYSTEM_EVENT_READONLY",
                                    "message": "Gli eventi SYSTEM non possono essere eliminati."})
    if ev.get("created_by_user_id") != user.get("id"):
        # solo l'autore o admin possono cancellare
        role = (user.get("role") or "").lower()
        if role not in {"admin", "owner", "superadmin"}:
            raise HTTPException(403, "Solo l'autore o un admin può eliminare l'evento")
    await db.customer_timeline.update_one(
        {"_id": event_id},
        {"$set": {"deleted_at": datetime.now(timezone.utc).isoformat(),
                   "deleted_by": user.get("email") or user.get("id")}},
    )
    return {"ok": True}
