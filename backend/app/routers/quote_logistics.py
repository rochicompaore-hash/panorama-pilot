"""Quote logistics services API — /api/quotes/{qid}/logistics (trasporto cantiere / piano / gru; sconto e azzeramento prezzo cliente)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.routers.quotes import _financial_totals_patch, _raise_if_price_blocked, _get_perms, _is_frozen, ADMIN_MASTER_MARKER
from app.services.audit import record_audit
from app.services.logistics_services import (ZERO_REASONS, customer_view, ensure_catalog, materialize, sync_auto)
from app.services.timeline import record_activity

router = APIRouter(prefix="/quotes", tags=["quote-logistics"])


class AddBody(BaseModel):
    code: str


class PriceBody(BaseModel):
    customer_price: float = Field(ge=0)
    reason: Optional[str] = Field(None, max_length=300)


async def _load(db, qid, user):
    doc = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Preventivo non trovato")
    return doc


async def _synced(db, doc, user) -> list:
    catalog = await ensure_catalog(db, user["tenant_id"])
    site = await db.sites.find_one({"_id": doc.get("site_id"), "tenant_id": user["tenant_id"]}, {"floor": 1}) if doc.get("site_id") else None
    items = sync_auto(doc.get("logistics_services") or [], catalog, site)
    if items != (doc.get("logistics_services") or []) and not _is_frozen(doc):
        await _save(db, doc, items)
    return items


async def _save(db, doc, items):
    patch = _financial_totals_patch(doc.get("lines") or [], {**doc, "logistics_services": items})
    await db.quotes.update_one({"_id": doc["_id"]}, {"$set": {"logistics_services": items, **patch, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return patch


async def _view(db, doc, items, user):
    perms = await _get_perms(user)
    catalog = await ensure_catalog(db, user["tenant_id"])
    is_admin = ADMIN_MASTER_MARKER in perms
    site = await db.sites.find_one({"_id": doc.get("site_id"), "tenant_id": user["tenant_id"]}, {"floor": 1}) if doc.get("site_id") else None
    return {"items": customer_view(items, is_admin), "is_admin_view": is_admin, "site_floor": (site or {}).get("floor"), "zero_reasons": list(ZERO_REASONS),
            "catalog": [{"code": c, "label": d.get("name"), "standard_price": d.get("customer_sale_price"), "pricing_status": d.get("status"), **({"internal_cost": d.get("internal_reference_price")} if is_admin else {})} for c, d in catalog.items()]}


@router.get("/{qid}/logistics")
async def get_logistics(qid: str, user: dict = Depends(require_permission("quotes.view"))):
    db = get_db()
    doc = await _load(db, qid, user)
    return await _view(db, doc, await _synced(db, doc, user), user)


@router.post("/{qid}/logistics")
async def add_logistics(qid: str, body: AddBody, request: Request, user: dict = Depends(require_permission("quotes.edit"))):
    db = get_db()
    doc = await _load(db, qid, user)
    if _is_frozen(doc):
        raise HTTPException(409, {"code": "QUOTE_FROZEN"})
    catalog = await ensure_catalog(db, user["tenant_id"])
    code = body.code.upper()
    if code not in catalog:
        raise HTTPException(400, {"code": "LOGISTICS_CODE_INVALID", "allowed": list(catalog)})
    items = await _synced(db, doc, user)
    if any(i["code"] == code for i in items):
        raise HTTPException(409, {"code": "ALREADY_PRESENT"})
    if catalog[code].get("customer_sale_price") is None:
        raise HTTPException(400, {"code": "PRICING_RULE_TO_DEFINE", "message": f"{catalog[code].get('name')}: prezzo non configurato dall'Admin (nessun prezzo inventato)"})
    items.append(materialize(code, catalog[code], auto=False, required=False))
    patch = await _save(db, doc, items)
    _raise_if_price_blocked(patch.get("financial_snapshot") or {})
    await record_audit(action="quotes.logistics_add", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="quote", entity_id=qid, after={"code": code})
    return await _view(db, doc, items, user)


@router.delete("/{qid}/logistics/{code}")
async def remove_logistics(qid: str, code: str, request: Request, user: dict = Depends(require_permission("quotes.edit"))):
    db = get_db()
    doc = await _load(db, qid, user)
    if _is_frozen(doc):
        raise HTTPException(409, {"code": "QUOTE_FROZEN"})
    items = await _synced(db, doc, user)
    target = next((i for i in items if i["code"] == code.upper()), None)
    if not target:
        raise HTTPException(404, {"code": "NOT_PRESENT"})
    if target.get("required"):
        raise HTTPException(409, {"code": "SERVICE_REQUIRED", "message": "Servizio necessario per il cantiere: non rimuovibile. Usa AZZERA per concederlo in omaggio."})
    items = [i for i in items if i["code"] != code.upper()]
    await _save(db, doc, items)
    await record_audit(action="quotes.logistics_remove", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="quote", entity_id=qid, after={"code": code.upper()})
    return await _view(db, doc, items, user)


@router.patch("/{qid}/logistics/{code}/price")
async def set_logistics_price(qid: str, code: str, body: PriceBody, request: Request, user: dict = Depends(require_permission("quotes.apply_discount"))):
    """SERVICE_LINE_DISCOUNT: solo prezzo cliente (0..standard). Costo interno invariato. Simulazione margin floor PRIMA del salvataggio. Azzeramento richiede motivo."""
    db = get_db()
    doc = await _load(db, qid, user)
    if _is_frozen(doc):
        raise HTTPException(409, {"code": "QUOTE_FROZEN"})
    items = await _synced(db, doc, user)
    target = next((i for i in items if i["code"] == code.upper()), None)
    if not target:
        raise HTTPException(404, {"code": "NOT_PRESENT"})
    std = target.get("standard_price")
    if std is None:
        raise HTTPException(400, {"code": "PRICING_RULE_TO_DEFINE"})
    new = round(body.customer_price, 2)
    if new > float(std):
        raise HTTPException(400, {"code": "PRICE_ABOVE_STANDARD", "message": f"Il prezzo cliente non può superare lo standard ({std} €)"})
    if new < float(std) and not target.get("discountable", True):
        raise HTTPException(403, {"code": "NOT_DISCOUNTABLE"})
    if new == 0 and not target.get("zeroable", True):
        raise HTTPException(403, {"code": "NOT_ZEROABLE"})
    if new == 0 and not (body.reason or "").strip():
        raise HTTPException(400, {"code": "ZERO_REASON_REQUIRED", "message": "Motivo azzeramento obbligatorio", "reasons": list(ZERO_REASONS)})
    old = target.get("customer_price")
    now = datetime.now(timezone.utc).isoformat()
    target["customer_price"] = new
    target.setdefault("price_history", []).append({"at": now, "user_id": user["id"], "user_email": user["email"], "old_price": old, "new_price": new,
                                                   "reason": (body.reason or "").strip() or None, "kind": "ZEROED" if new == 0 else ("SERVICE_LINE_DISCOUNT" if new < float(std) else "RESTORED")})
    sim = _financial_totals_patch(doc.get("lines") or [], {**doc, "logistics_services": items})
    _raise_if_price_blocked(sim.get("financial_snapshot") or {})  # floor >15% anche per Admin Master, PRIMA del salvataggio
    await db.quotes.update_one({"_id": qid}, {"$set": {"logistics_services": items, **sim, "updated_at": now, "updated_by": user["id"]}})
    await record_audit(action="quotes.logistics_price", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="quote", entity_id=qid,
                       before={"code": code.upper(), "customer_price": old}, after={"customer_price": new, "reason": body.reason, "internal_cost_unchanged": True})
    await record_activity(tenant_id=user["tenant_id"], type="quote_logistics_price", subject=f"{target.get('label')}: prezzo cliente {old} → {new} €" + (" (OMAGGIO)" if new == 0 else ""),
                          body=f"Motivo: {body.reason}" if body.reason else None, customer_id=doc.get("customer_id"), quote_id=qid, user_id=user["id"], user_email=user["email"],
                          meta={"code": code.upper(), "old_price": old, "new_price": new, "reason": body.reason})
    return await _view(db, doc, items, user)
