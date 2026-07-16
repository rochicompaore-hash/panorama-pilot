"""Quotes router (M3.1) — CRUD, openings, lines, status changes, revisions, approvals, conversion to contract."""
from __future__ import annotations
import copy
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Header
from pydantic import BaseModel
from app.db import get_db
from app.deps import require_permission, require_any_permission, get_client_ip, get_permission_keys_for_user
from app.models import new_id
from app.models_quote import (
    Quote, QuoteCreate, QuoteUpdate, QuoteLine, QuoteLineCreate, QuoteLineUpdate,
    QuoteOpening, QuoteOpeningCreate, QuoteOpeningUpdate, QuoteStatusChange, QuoteApprovalDecision,
    Contract,
)
from app.models_crm import LeadAddress
from app.mongo_utils import to_mongo, from_mongo
from app.services.audit import record_audit
from app.services.timeline import record_activity
from app.services.pricing import compute_line, compute_quote_totals
from app.services.concurrency import (
    update_with_version, get_if_match_version, user_has_permission,
    ConflictError, CONSOLIDATED_QUOTE_STATUSES,
)

router = APIRouter(prefix="/quotes", tags=["quotes"])

STATUS_FLOW = {
    "draft": {"to_complete", "to_approve", "sent", "cancelled"},
    "to_complete": {"draft", "to_approve", "sent", "cancelled"},
    "to_approve": {"approved", "rejected", "cancelled"},
    "approved": {"sent", "cancelled"},
    "sent": {"viewed", "negotiating", "accepted", "rejected", "expired", "cancelled"},
    "viewed": {"negotiating", "accepted", "rejected", "expired", "cancelled"},
    "negotiating": {"accepted", "rejected", "expired", "cancelled"},
    "accepted": {"converted"},
    "rejected": set(),
    "expired": set(),
    "cancelled": set(),
    "converted": set(),
    "superseded": set(),
}


async def _next_quote_number(tenant_id: str) -> tuple[str, int]:
    """Atomically increments sequence 'quote' and returns (formatted, int)."""
    db = get_db()
    now = datetime.now(timezone.utc)
    seq = await db.sequences.find_one({"tenant_id": tenant_id, "key": "quote"})
    if not seq:
        raise HTTPException(status_code=500, detail="Numerazione 'quote' non configurata")
    year = now.year
    if seq.get("year_reset") and seq.get("current_year") != year:
        await db.sequences.update_one({"_id": seq["_id"]}, {"$set": {"current_number": max(seq.get("current_number", 0), 0), "current_year": year}})
    updated = await db.sequences.find_one_and_update(
        {"_id": seq["_id"], "tenant_id": tenant_id},
        {"$inc": {"current_number": 1}, "$set": {"current_year": year, "updated_at": now.isoformat()}},
        return_document=True,
    )
    n = updated["current_number"]
    padded = str(n).zfill(updated.get("padding", 5))
    year_part = f"{year}-" if updated.get("year_reset") else ""
    formatted = f"{updated.get('prefix','PREV-')}{year_part}{padded}"
    return formatted, n


def _recompute(quote: dict) -> dict:
    lines = [compute_line(dict(l)) for l in (quote.get("lines") or [])]
    quote["lines"] = lines
    totals = compute_quote_totals(lines)
    quote.update(totals)
    return quote


def _strip_costs_if_needed(doc: dict, perms: set) -> dict:
    d = dict(doc)
    if "*" not in perms and "quotes.view_costs" not in perms and "quotes.view_margins" not in perms:
        for k in ("internal_cost", "margin_abs", "margin_pct"):
            d[k] = None
        d["lines"] = [{**l, "internal_cost": None, "margin": None} for l in (d.get("lines") or [])]
    return d


async def _get_perms(user: dict) -> set:
    perms = set(await get_permission_keys_for_user(user))
    if user.get("is_superadmin"):
        perms.add("*")
    return perms


async def _get_thresholds(tenant_id: str) -> list:
    db = get_db()
    docs = await db.discount_thresholds.find({"tenant_id": tenant_id, "deleted_at": None}).to_list(100)
    return docs


@router.get("")
async def list_quotes(
    q: Optional[str] = None,
    status: Optional[str] = None,
    lead_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    assigned_to: Optional[str] = None,
    only_current: bool = True,
    limit: int = Query(100, le=500),
    skip: int = 0,
    user: dict = Depends(require_permission("quotes.view")),
):
    db = get_db()
    query: dict = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if only_current:
        query["is_current"] = True
    if status: query["quote_status"] = status
    if lead_id: query["lead_id"] = lead_id
    if customer_id: query["customer_id"] = customer_id
    if assigned_to: query["assigned_to"] = assigned_to
    if q:
        query["$or"] = [
            {"number": {"$regex": q, "$options": "i"}},
            {"title": {"$regex": q, "$options": "i"}},
            {"notes": {"$regex": q, "$options": "i"}},
        ]
    total = await db.quotes.count_documents(query)
    docs = await db.quotes.find(query).sort([("number_int", -1), ("created_at", -1)]).skip(skip).limit(limit).to_list(limit)
    perms = await _get_perms(user)
    return {"total": total, "items": [_strip_costs_if_needed(from_mongo(d), perms) for d in docs]}


@router.get("/{qid}")
async def get_quote(qid: str, user: dict = Depends(require_permission("quotes.view"))):
    db = get_db()
    doc = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc: raise HTTPException(status_code=404, detail="Preventivo non trovato")
    perms = await _get_perms(user)
    return _strip_costs_if_needed(from_mongo(doc), perms)


@router.post("")
async def create_quote(body: QuoteCreate, request: Request, user: dict = Depends(require_permission("quotes.create"))):
    db = get_db()
    if not body.lead_id and not body.customer_id:
        raise HTTPException(status_code=400, detail="Specificare almeno un lead o un cliente")
    # Validate refs belong to tenant
    if body.lead_id:
        lead = await db.leads.find_one({"_id": body.lead_id, "tenant_id": user["tenant_id"], "deleted_at": None})
        if not lead: raise HTTPException(status_code=400, detail="Lead non valido")
    if body.customer_id:
        cust = await db.customers.find_one({"_id": body.customer_id, "tenant_id": user["tenant_id"], "deleted_at": None})
        if not cust: raise HTTPException(status_code=400, detail="Cliente non valido")

    number, n_int = await _next_quote_number(user["tenant_id"])
    q = Quote(
        id=new_id(), tenant_id=user["tenant_id"],
        number=f"{number}-R00", number_int=n_int, revision=0, revision_label="R00",
        lead_id=body.lead_id, customer_id=body.customer_id, contact_id=body.contact_id,
        assigned_to=body.assigned_to or user["id"],
        site_address=body.site_address or LeadAddress(),
        title=body.title or f"Preventivo {number}",
        intervention_type=body.intervention_type,
        payment_terms=body.payment_terms, valid_until=body.valid_until,
        notes=body.notes,
        disclaimer="Le misure riportate nel presente preventivo sono indicative e non costituiscono misure esecutive o oggetto definitivo del contratto. Le misure definitive saranno rilevate e validate dal tecnico incaricato prima dell'ordine o dell'avvio della produzione.",
        created_by=user["id"], updated_by=user["id"],
    )
    doc = to_mongo(q.model_dump(by_alias=True))
    await db.quotes.insert_one(doc)
    await record_audit(action="quotes.create", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="quote", entity_id=q.id, after={"number": q.number})
    await record_activity(tenant_id=user["tenant_id"], type="quote_created",
                          subject=f"Preventivo {q.number} creato",
                          lead_id=q.lead_id, customer_id=q.customer_id, quote_id=q.id,
                          user_id=user["id"], user_email=user["email"])
    perms = await _get_perms(user)
    return _strip_costs_if_needed(from_mongo(await db.quotes.find_one({"_id": q.id})), perms)


def _assert_editable(doc: dict):
    if doc.get("quote_status") in ("accepted", "converted", "superseded", "rejected", "cancelled", "expired"):
        raise HTTPException(status_code=400, detail=f"Preventivo in stato '{doc.get('quote_status')}' non modificabile")


@router.patch("/{qid}")
async def update_quote(
    qid: str, body: QuoteUpdate, request: Request,
    expected_version: Optional[int] = Depends(get_if_match_version),
    force: bool = False,
    force_reason: Optional[str] = Header(default=None, alias="X-Force-Reason"),
    user: dict = Depends(require_permission("quotes.edit")),
):
    payload = body.model_dump(exclude_unset=True)
    if "site_address" in payload and payload["site_address"] is not None:
        payload["site_address"] = payload["site_address"] if isinstance(payload["site_address"], dict) else payload["site_address"].model_dump()

    # Force override permission check
    if force:
        perms = await _get_perms(user)
        if not user_has_permission(user, perms, "records.force_override"):
            raise HTTPException(status_code=403, detail="Permesso 'records.force_override' mancante")

    updated = await update_with_version(
        collection="quotes", entity_id=qid, tenant_id=user["tenant_id"],
        entity_type="quote", expected_version=expected_version,
        set_fields=payload, user=user, request=request,
        force_override=force, override_reason=force_reason,
    )
    await record_audit(action="quotes.update", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="quote", entity_id=qid, after=payload)
    perms = await _get_perms(user)
    return _strip_costs_if_needed(updated, perms)


# --------- Autosave endpoint (M3.3.1) ---------
class AutosaveRequest(BaseModel):
    """Autosave payload — accepts arbitrary quote-level draft fields.

    Only applied when quote is in draft/to_complete/to_approve state.
    Rejects mutation of consolidated states with 400.
    Uses optimistic concurrency (version).
    Returns fresh {version, updated_at} so client can chain the next save.
    """
    version: int
    fields: dict
    request_id: Optional[str] = None


@router.post("/{qid}/autosave")
async def autosave_quote(
    qid: str, body: AutosaveRequest, request: Request,
    user: dict = Depends(require_permission("quotes.edit")),
):
    """Debounced autosave. Draft-only. Returns 409 on version mismatch.

    Accepted fields (whitelist to prevent misuse):
      title, notes, payment_terms, delivery_days, warranty_months,
      valid_until, discount_pct_global, internal_notes, site_address, description
    """
    ALLOWED = {
        "title", "notes", "payment_terms", "delivery_days", "warranty_months",
        "valid_until", "discount_pct_global", "internal_notes", "site_address",
        "description",
    }
    payload = {k: v for k, v in (body.fields or {}).items() if k in ALLOWED}
    if not payload:
        raise HTTPException(status_code=400, detail="Nessun campo autosalvabile")
    if "site_address" in payload and payload["site_address"] is not None and not isinstance(payload["site_address"], dict):
        payload["site_address"] = payload["site_address"].model_dump() if hasattr(payload["site_address"], "model_dump") else payload["site_address"]
    try:
        updated = await update_with_version(
            collection="quotes", entity_id=qid, tenant_id=user["tenant_id"],
            entity_type="quote", expected_version=body.version,
            set_fields=payload, user=user, request=request,
        )
    except HTTPException as e:
        raise
    # Return minimal payload for autosave — avoid heavy quote body
    return {
        "ok": True,
        "id": qid,
        "version": updated.get("version"),
        "updated_at": updated.get("updated_at"),
        "request_id": body.request_id,
        "autosaved_fields": list(payload.keys()),
    }


@router.delete("/{qid}")
async def delete_quote(qid: str, request: Request, user: dict = Depends(require_permission("quotes.delete"))):
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    doc = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc: raise HTTPException(status_code=404, detail="Preventivo non trovato")
    await db.quotes.update_one({"_id": qid}, {"$set": {"deleted_at": now, "updated_at": now, "updated_by": user["id"]}})
    await record_audit(action="quotes.delete", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="quote", entity_id=qid)
    return {"ok": True}


# ----- Openings -----
@router.post("/{qid}/openings")
async def add_opening(qid: str, body: QuoteOpeningCreate, request: Request, user: dict = Depends(require_permission("quotes.edit"))):
    db = get_db()
    doc = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc: raise HTTPException(status_code=404, detail="Preventivo non trovato")
    _assert_editable(doc)
    op = QuoteOpening(**body.model_dump())
    openings = doc.get("openings") or []
    if not op.code:
        op.code = f"V{len(openings) + 1:02d}"
    openings.append(op.model_dump())
    await db.quotes.update_one({"_id": qid}, {"$set": {"openings": openings, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user["id"]}, "$inc": {"version": 1}})
    await record_audit(action="quotes.opening_add", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="quote", entity_id=qid, after={"opening": op.code})
    return op.model_dump()


@router.patch("/{qid}/openings/{oid}")
async def update_opening(
    qid: str, oid: str, body: QuoteOpeningUpdate, request: Request,
    expected_version: Optional[int] = Depends(get_if_match_version),
    user: dict = Depends(require_permission("quotes.edit")),
):
    db = get_db()
    doc = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc: raise HTTPException(status_code=404, detail="Preventivo non trovato")
    _assert_editable(doc)
    openings = doc.get("openings") or []
    updated = False
    for i, op in enumerate(openings):
        if op["id"] == oid:
            for k, v in body.model_dump(exclude_unset=True).items():
                op[k] = v
            openings[i] = op
            updated = True
            break
    if not updated: raise HTTPException(status_code=404, detail="Vano non trovato")
    now = datetime.now(timezone.utc).isoformat()
    # Version-checked update on parent quote
    filter_q = {"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None}
    if expected_version is not None:
        filter_q["version"] = expected_version
    result = await db.quotes.update_one(filter_q, {"$set": {"openings": openings, "updated_at": now, "updated_by": user["id"]}, "$inc": {"version": 1}})
    if result.modified_count == 0:
        latest = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"]})
        if latest and expected_version is not None and latest.get("version") != expected_version:
            raise ConflictError(from_mongo(latest), "quote", expected_version)
        raise HTTPException(status_code=409, detail="Aggiornamento vano fallito")
    return {"ok": True}


@router.delete("/{qid}/openings/{oid}")
async def delete_opening(qid: str, oid: str, user: dict = Depends(require_permission("quotes.edit"))):
    db = get_db()
    doc = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc: raise HTTPException(status_code=404, detail="Preventivo non trovato")
    _assert_editable(doc)
    openings = [o for o in (doc.get("openings") or []) if o["id"] != oid]
    lines = [l for l in (doc.get("lines") or []) if l.get("opening_id") != oid]
    q = _recompute({"lines": lines, "openings": openings})
    await db.quotes.update_one({"_id": qid}, {"$set": {"openings": q["openings"], "lines": q["lines"], "subtotal": q["subtotal"], "vat_amount": q["vat_amount"], "total": q["total"], "internal_cost": q["internal_cost"], "margin_abs": q["margin_abs"], "margin_pct": q["margin_pct"], "taxable_amount": q["taxable_amount"], "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user["id"]}, "$inc": {"version": 1}})
    return {"ok": True}


# ----- Lines -----
@router.post("/{qid}/lines")
async def add_line(qid: str, body: QuoteLineCreate, request: Request, user: dict = Depends(require_permission("quotes.edit"))):
    db = get_db()
    doc = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc: raise HTTPException(status_code=404, detail="Preventivo non trovato")
    _assert_editable(doc)
    line_data = body.model_dump()
    # Auto-fill dimensions from opening if not set
    if line_data.get("opening_id") and (not line_data.get("width_mm") or not line_data.get("height_mm")):
        op = next((o for o in doc.get("openings", []) if o["id"] == line_data["opening_id"]), None)
        if op:
            line_data["width_mm"] = line_data.get("width_mm") or op.get("width_mm")
            line_data["height_mm"] = line_data.get("height_mm") or op.get("height_mm")
    ql = QuoteLine(**line_data)
    lines = doc.get("lines") or []
    ql.order_index = len(lines)
    lines.append(compute_line(ql.model_dump()))
    totals = compute_quote_totals(lines)
    await db.quotes.update_one({"_id": qid}, {"$set": {"lines": lines, **totals, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user["id"]}, "$inc": {"version": 1}})
    await record_audit(action="quotes.line_add", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="quote", entity_id=qid, after={"category": ql.category, "price": ql.base_price})
    return lines[-1]


@router.patch("/{qid}/lines/{lid}")
async def update_line(
    qid: str, lid: str, body: QuoteLineUpdate, request: Request,
    expected_version: Optional[int] = Depends(get_if_match_version),
    user: dict = Depends(require_permission("quotes.edit")),
):
    db = get_db()
    doc = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc: raise HTTPException(status_code=404, detail="Preventivo non trovato")
    _assert_editable(doc)
    lines = doc.get("lines") or []
    idx = next((i for i, l in enumerate(lines) if l["id"] == lid), None)
    if idx is None: raise HTTPException(status_code=404, detail="Riga non trovata")

    # Discount governance
    perms = await _get_perms(user)
    payload = body.model_dump(exclude_unset=True)
    if "discount_pct" in payload:
        new_pct = float(payload["discount_pct"] or 0)
        thresholds = await _get_thresholds(user["tenant_id"])
        user_role_ids = user.get("role_ids") or []
        max_allowed = 0.0
        for th in thresholds:
            if th.get("role_id") in user_role_ids:
                max_allowed = max(max_allowed, float(th.get("max_discount_pct", 0)))
        if user.get("is_superadmin") or "*" in perms:
            max_allowed = 100.0
        if new_pct > max_allowed and "quotes.override_discount" not in perms and not user.get("is_superadmin"):
            payload["_needs_approval"] = True
        if new_pct > 0 and "quotes.apply_discount" not in perms and not user.get("is_superadmin"):
            raise HTTPException(status_code=403, detail="Permesso 'quotes.apply_discount' mancante")

    needs_approval = payload.pop("_needs_approval", False)
    for k, v in payload.items():
        lines[idx][k] = v
    lines[idx] = compute_line(lines[idx])
    totals = compute_quote_totals(lines)
    update = {"lines": lines, **totals, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user["id"]}
    if needs_approval and doc.get("quote_status") in ("draft", "to_complete"):
        update["quote_status"] = "to_approve"
        update["approval"] = {"required": True, "status": "pending", "requested_by": user["id"], "requested_at": datetime.now(timezone.utc).isoformat(), "reason": f"Sconto {payload.get('discount_pct')}% oltre soglia"}

    filter_q = {"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None}
    if expected_version is not None:
        filter_q["version"] = expected_version
    result = await db.quotes.update_one(filter_q, {"$set": update, "$inc": {"version": 1}})
    if result.modified_count == 0:
        latest = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"]})
        if latest and expected_version is not None and latest.get("version") != expected_version:
            raise ConflictError(from_mongo(latest), "quote", expected_version)
        raise HTTPException(status_code=409, detail="Aggiornamento riga fallito")
    return lines[idx]


@router.delete("/{qid}/lines/{lid}")
async def delete_line(qid: str, lid: str, user: dict = Depends(require_permission("quotes.edit"))):
    db = get_db()
    doc = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc: raise HTTPException(status_code=404, detail="Preventivo non trovato")
    _assert_editable(doc)
    lines = [l for l in (doc.get("lines") or []) if l["id"] != lid]
    totals = compute_quote_totals(lines)
    await db.quotes.update_one({"_id": qid}, {"$set": {"lines": lines, **totals, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user["id"]}, "$inc": {"version": 1}})
    return {"ok": True}


# ----- Status transitions -----
@router.post("/{qid}/status")
async def change_status(qid: str, body: QuoteStatusChange, request: Request, user: dict = Depends(require_permission("quotes.edit"))):
    db = get_db()
    doc = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc: raise HTTPException(status_code=404, detail="Preventivo non trovato")
    current = doc.get("quote_status", "draft")
    new = body.new_status
    if new not in STATUS_FLOW.get(current, set()) and new != current:
        raise HTTPException(status_code=400, detail=f"Transizione non consentita: {current} → {new}")
    if new == "sent" and doc.get("approval", {}).get("status") == "pending":
        raise HTTPException(status_code=400, detail="Preventivo in attesa di approvazione")

    # Blocca invio se ci sono errori bloccanti sui prodotti collegati
    if new == "sent":
        blocked_products = await db.opening_products.find({
            "tenant_id": user["tenant_id"], "quote_id": qid, "deleted_at": None,
            "$or": [
                {"blocking_errors": {"$exists": True, "$ne": []}},
                {"last_compute.blocking_errors": {"$exists": True, "$ne": []}},
            ],
        }, {"_id": 1, "blocking_errors": 1}).to_list(50)
        if blocked_products:
            raise HTTPException(
                status_code=400,
                detail=f"Preventivo non inviabile: {len(blocked_products)} prodotto/i con errori bloccanti "
                        f"(prezzi mancanti o listini non pubblicati). Correggi prima dell'invio."
            )

    now = datetime.now(timezone.utc).isoformat()
    update = {"quote_status": new, "updated_at": now, "updated_by": user["id"]}
    if new == "sent":
        update["sent_at"] = now
        update["sent_by"] = user["id"]
        # Freeze price snapshot on send — includes pricelist + rules snapshot for reproducibility
        pl = await db.pricelists.find_one({"tenant_id": user["tenant_id"], "is_default": True, "deleted_at": None})
        rules_snap: list = []
        pl_snap: dict = {}
        if pl:
            pl_snap = {"id": pl["_id"], "name": pl.get("name"), "currency": pl.get("currency", "EUR"), "version": pl.get("version", 1)}
            rules_snap = await db.price_rules.find({"tenant_id": user["tenant_id"], "pricelist_id": pl["_id"], "deleted_at": None, "active": True}).sort("priority", 1).to_list(1000)
        update["price_snapshot"] = {
            "lines": doc.get("lines", []),
            "totals": {k: doc.get(k) for k in ("subtotal", "vat_amount", "total", "internal_cost", "margin_abs")},
            "pricelist": pl_snap,
            "rules": [from_mongo(r) for r in rules_snap],
            "frozen_at": now,
            "frozen_by": user["id"],
        }
    elif new == "viewed":
        update["viewed_at"] = now
    elif new == "accepted":
        update["accepted_at"] = now
    elif new == "rejected":
        update["rejected_at"] = now
    elif new == "cancelled":
        update["cancelled_at"] = now
    elif new == "expired":
        update["expired_at"] = now

    await db.quotes.update_one({"_id": qid}, {"$set": update})
    await record_audit(action=f"quotes.status_change", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="quote", entity_id=qid, before={"status": current}, after={"status": new, "reason": body.reason})
    await record_activity(tenant_id=user["tenant_id"], type=f"quote_{new}",
                          subject=f"Preventivo {doc.get('number')}: {new}",
                          body=body.reason,
                          lead_id=doc.get("lead_id"), customer_id=doc.get("customer_id"), quote_id=qid,
                          user_id=user["id"], user_email=user["email"])
    return {"ok": True, "new_status": new}


@router.post("/{qid}/approve")
async def approve_quote(qid: str, body: QuoteApprovalDecision, request: Request, user: dict = Depends(require_permission("quotes.approve"))):
    db = get_db()
    doc = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc: raise HTTPException(status_code=404, detail="Preventivo non trovato")
    if doc.get("approval", {}).get("status") != "pending":
        raise HTTPException(status_code=400, detail="Nessuna richiesta di approvazione pendente")
    if not body.reason:
        raise HTTPException(status_code=400, detail="Motivazione obbligatoria")
    now = datetime.now(timezone.utc).isoformat()
    approval = doc.get("approval", {})
    approval.update({"status": "approved" if body.approved else "rejected", "approved_by": user["id"], "decided_at": now, "reason_response": body.reason})
    new_status = "approved" if body.approved else "to_complete"
    await db.quotes.update_one({"_id": qid}, {"$set": {"approval": approval, "quote_status": new_status, "updated_at": now, "updated_by": user["id"]}})
    await record_audit(action="quotes.approval_decision", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="quote", entity_id=qid, after={"approved": body.approved, "reason": body.reason})
    await record_activity(tenant_id=user["tenant_id"], type="quote_approved" if body.approved else "quote_approval_rejected",
                          subject=f"Preventivo {doc.get('number')} {'approvato' if body.approved else 'rifiutato'}",
                          body=body.reason, lead_id=doc.get("lead_id"), customer_id=doc.get("customer_id"), quote_id=qid,
                          user_id=user["id"], user_email=user["email"])
    return {"ok": True}


# ----- Revisions -----
@router.post("/{qid}/revise")
async def create_revision(qid: str, request: Request, user: dict = Depends(require_permission("quotes.edit"))):
    """Create a new revision. Marks parent as superseded."""
    db = get_db()
    parent = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not parent: raise HTTPException(status_code=404, detail="Preventivo non trovato")
    if not parent.get("is_current"): raise HTTPException(status_code=400, detail="Revisione già esistente per questo preventivo")

    new_rev = int(parent.get("revision", 0)) + 1
    rev_label = f"R{new_rev:02d}"
    number_base = (parent.get("number") or "").split("-R")[0]
    new_q = copy.deepcopy(parent)
    new_q["_id"] = new_id()
    new_q["id"] = new_q["_id"]
    new_q["parent_quote_id"] = parent["_id"]
    new_q["revision"] = new_rev
    new_q["revision_label"] = rev_label
    new_q["number"] = f"{number_base}-{rev_label}"
    new_q["quote_status"] = "draft"
    new_q["is_current"] = True
    new_q["price_snapshot"] = {}
    new_q["sent_at"] = None
    new_q["viewed_at"] = None
    new_q["accepted_at"] = None
    new_q["rejected_at"] = None
    new_q["created_at"] = datetime.now(timezone.utc).isoformat()
    new_q["updated_at"] = new_q["created_at"]
    new_q["created_by"] = user["id"]
    new_q["updated_by"] = user["id"]
    new_q["contract_id"] = None
    # Fresh IDs for lines/openings to allow independent edit
    for l in (new_q.get("lines") or []):
        l["id"] = new_id()
    id_map = {}
    for o in (new_q.get("openings") or []):
        old = o["id"]; o["id"] = new_id(); id_map[old] = o["id"]
    for l in (new_q.get("lines") or []):
        if l.get("opening_id") in id_map:
            l["opening_id"] = id_map[l["opening_id"]]
    await db.quotes.insert_one(new_q)
    # Mark parent superseded (but keep readable)
    await db.quotes.update_one({"_id": parent["_id"]}, {"$set": {"is_current": False, "quote_status": "superseded", "updated_at": new_q["updated_at"], "updated_by": user["id"]}})
    # Invalidate any active public tokens for the previous revision (M3.3.3)
    from app.routers.public import invalidate_tokens_for_previous_revisions
    await invalidate_tokens_for_previous_revisions(user["tenant_id"], parent["_id"])
    await record_audit(action="quotes.revision_create", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="quote", entity_id=new_q["_id"], after={"revision": rev_label, "parent": parent["_id"]})
    await record_activity(tenant_id=user["tenant_id"], type="quote_revision_created",
                          subject=f"Nuova revisione {new_q['number']}",
                          lead_id=parent.get("lead_id"), customer_id=parent.get("customer_id"), quote_id=new_q["_id"],
                          user_id=user["id"], user_email=user["email"])
    perms = await _get_perms(user)
    return _strip_costs_if_needed(from_mongo(await db.quotes.find_one({"_id": new_q["_id"]})), perms)


@router.get("/{qid}/history")
async def revision_history(qid: str, user: dict = Depends(require_permission("quotes.view"))):
    db = get_db()
    root = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"]})
    if not root: raise HTTPException(status_code=404, detail="Preventivo non trovato")
    # Walk up to root
    cur = root
    while cur.get("parent_quote_id"):
        p = await db.quotes.find_one({"_id": cur["parent_quote_id"], "tenant_id": user["tenant_id"]})
        if not p: break
        cur = p
    # Now collect all in family
    number_base = (cur.get("number") or "").split("-R")[0]
    fam = await db.quotes.find({"tenant_id": user["tenant_id"], "number": {"$regex": f"^{number_base}-R"}}).sort("revision", 1).to_list(50)
    return {"items": [{"id": q["_id"], "number": q.get("number"), "revision": q.get("revision"), "quote_status": q.get("quote_status"), "total": q.get("total"), "is_current": q.get("is_current"), "created_at": q.get("created_at")} for q in fam]}


# ----- Convert to contract -----
@router.post("/{qid}/convert-to-contract")
async def convert_to_contract(qid: str, request: Request, user: dict = Depends(require_permission("quotes.convert_contract"))):
    db = get_db()
    doc = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc: raise HTTPException(status_code=404, detail="Preventivo non trovato")
    # M3.3.6 — Idempotency: if already converted, return existing contract
    if doc.get("contract_id"):
        existing = await db.contracts.find_one({"_id": doc["contract_id"], "tenant_id": user["tenant_id"]})
        if existing:
            return from_mongo(existing)
        # else fall through — dangling reference, allow new
    # Contract can be created from: quote signed by customer (M3.3.4) OR internally accepted/approved.
    allowed_source_status = {"signed", "accepted", "approved"}
    if doc.get("quote_status") not in allowed_source_status:
        raise HTTPException(status_code=400,
            detail=f"Il preventivo deve avere quote_status in {sorted(allowed_source_status)} (attuale: {doc.get('quote_status')})")
    if not doc.get("is_current", True):
        raise HTTPException(status_code=400, detail="Revisione superata: non convertibile")
    # If signed, require a signature evidence record
    signature_ref = None
    if doc.get("quote_status") == "signed":
        sig = await db.quote_signatures.find_one({"quote_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
        if not sig:
            raise HTTPException(status_code=400, detail="Firma non trovata per il preventivo firmato")
        signature_ref = {"signature_id": sig["_id"], "evidence_id": sig.get("evidence_id_short"),
                         "signed_pdf_id": sig.get("signed_pdf_id"), "evidence_hash": sig.get("evidence_hash")}

    # Contract number from sequence
    seq = await db.sequences.find_one({"tenant_id": user["tenant_id"], "key": "contract"})
    if not seq:
        # Auto-create sequence
        from app.models import Sequence
        s = Sequence(id=new_id(), tenant_id=user["tenant_id"], key="contract", label="Contratti", prefix="CON-", padding=5, year_reset=True, created_by=user["id"], updated_by=user["id"])
        await db.sequences.insert_one(to_mongo(s.model_dump(by_alias=True)))
        seq = await db.sequences.find_one({"tenant_id": user["tenant_id"], "key": "contract"})
    updated = await db.sequences.find_one_and_update({"_id": seq["_id"]}, {"$inc": {"current_number": 1}, "$set": {"current_year": datetime.now(timezone.utc).year}}, return_document=True)
    n = updated["current_number"]
    padded = str(n).zfill(updated.get("padding", 5))
    year_part = f"{datetime.now(timezone.utc).year}-" if updated.get("year_reset") else ""
    number = f"{updated.get('prefix','CON-')}{year_part}{padded}"

    c = Contract(
        id=new_id(), tenant_id=user["tenant_id"],
        number=number, number_int=n,
        quote_id=qid, quote_revision=doc.get("revision", 0),
        customer_id=doc.get("customer_id"),
        quote_snapshot={"lines": doc.get("lines", []), "openings": doc.get("openings", []), "totals": {k: doc.get(k) for k in ("subtotal", "vat_amount", "total")}, "site_address": doc.get("site_address"), "customer_id": doc.get("customer_id"), "quote_number": doc.get("number"), "payment_terms": doc.get("payment_terms"), "signature_ref": signature_ref},
        created_by=user["id"], updated_by=user["id"],
    )
    await db.contracts.insert_one(to_mongo(c.model_dump(by_alias=True)))
    now = datetime.now(timezone.utc).isoformat()
    await db.quotes.update_one({"_id": qid}, {"$set": {"contract_id": c.id, "quote_status": "converted", "converted_at": now, "updated_at": now, "updated_by": user["id"]}})
    await record_audit(action="quotes.convert_contract", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="quote", entity_id=qid, after={"contract_id": c.id, "contract_number": number})
    await record_activity(tenant_id=user["tenant_id"], type="contract_created",
                          subject=f"Contratto {number} generato da preventivo {doc.get('number')}",
                          lead_id=doc.get("lead_id"), customer_id=doc.get("customer_id"), quote_id=qid,
                          user_id=user["id"], user_email=user["email"])
    return from_mongo(await db.contracts.find_one({"_id": c.id}))
