"""QUOTE ECONOMIC CONTROL V2 — Fiscal Dossier (VAT eligibility) + Competitor Quote Analyzer (simulate/save/apply)."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models import new_id
from app.mongo_utils import from_mongo
from app.routers.quotes import _financial_totals_patch, _get_perms, _is_frozen, ADMIN_MASTER_MARKER
from app.services.audit import record_audit
from app.services.concurrency import user_has_permission
from app.services.margin_engine import MARGIN_FLOOR_PERCENT, redact_financial_snapshot_for_role
from app.services.vat_engine import resolve_vat_regime, REQUESTABLE

router = APIRouter(prefix="/quotes", tags=["quote-economic-control"])
COMMERCIAL_CAP = 30.0


class FiscalDossierPatch(BaseModel):
    requested_regime: Optional[str] = None
    vat_reason: Optional[str] = None
    customer_declaration: Optional[bool] = None
    documentation_status: Optional[str] = None   # MISSING | PARTIAL | COMPLETE
    vat_eligibility_status: Optional[str] = None  # PENDING | VALIDATED | REJECTED (solo quotes.vat_validate)
    notes: Optional[str] = None


class CompetitorInput(BaseModel):
    competitor_price: float = Field(gt=0)
    vat_included: str = "UNKNOWN"          # YES | NO | UNKNOWN
    competitor_vat_rate: Optional[str] = None  # 4 | 10 | 22 | MIXED | UNKNOWN
    competitor_name: Optional[str] = None
    notes: Optional[str] = None
    quote_date: Optional[str] = None
    attachment_id: Optional[str] = None
    competitor_scope: Dict[str, Any] = Field(default_factory=dict)  # {products: bool|None, installation:..., dismantling:..., accessories:..., services:..., financing:..., delivery_days:..., warranty:...}


async def _load(db, qid, user):
    doc = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Preventivo non trovato")
    return doc


@router.patch("/{qid}/fiscal-dossier")
async def patch_fiscal_dossier(qid: str, body: FiscalDossierPatch, request: Request, user: dict = Depends(require_permission("quotes.edit"))):
    db = get_db()
    doc = await _load(db, qid, user)
    if _is_frozen(doc):
        raise HTTPException(409, "Preventivo accettato: regime IVA congelato")
    perms = await _get_perms(user)
    dossier = dict(doc.get("fiscal_dossier") or {})
    upd = body.model_dump(exclude_none=True)
    if "vat_eligibility_status" in upd and not user_has_permission(user, perms, "quotes.vat_validate"):
        raise HTTPException(403, {"code": "VAT_VALIDATION_FORBIDDEN", "message": "La validazione IVA agevolata richiede autorizzazione fiscale"})
    if "requested_regime" in upd and upd["requested_regime"] not in REQUESTABLE:
        raise HTTPException(400, {"code": "VAT_REGIME_INVALID", "allowed": list(REQUESTABLE)})
    if "requested_regime" in upd and upd["requested_regime"] != dossier.get("requested_regime") and "vat_eligibility_status" not in upd:
        dossier["vat_eligibility_status"] = "PENDING"  # cambio richiesta → nuova review
    dossier.update(upd)
    dossier["updated_at"] = datetime.now(timezone.utc).isoformat()
    dossier["updated_by"] = user["id"]
    reg = resolve_vat_regime(dossier)
    patch = _financial_totals_patch(doc.get("lines") or [], {**doc, "fiscal_dossier": dossier, "vat_regime": reg["vat_regime"]})
    await db.quotes.update_one({"_id": qid}, {"$set": {"fiscal_dossier": dossier, **reg, **patch, "updated_at": datetime.now(timezone.utc).isoformat()}, "$inc": {"version": 1}})
    await record_audit(action="quotes.fiscal_dossier.update", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"],
                       ip=get_client_ip(request), entity_type="quote", entity_id=qid, before={"vat_regime": doc.get("vat_regime")}, after=reg)
    return {"fiscal_dossier": dossier, **reg, "vat_breakdown": patch.get("vat_breakdown"), "vat_amount": patch.get("vat_amount"), "total": patch.get("total")}


# ---------------------------------------------------------------------------
# Competitor analyzer
# ---------------------------------------------------------------------------
def _our_gross_rate(doc: dict) -> Optional[float]:
    bd = doc.get("vat_breakdown") or []
    if len(bd) == 1:
        return float(bd[0]["rate"])
    return None  # misto → nessuna aliquota singola


def _normalize_competitor(body: CompetitorInput, our_rate: Optional[float]) -> Dict[str, Any]:
    p = float(body.competitor_price)
    rate_map = {"4": 0.04, "10": 0.10, "22": 0.22}
    crate = rate_map.get(str(body.competitor_vat_rate)) if body.competitor_vat_rate else None
    if body.vat_included == "NO":
        net = p
        gross = round(p * (1 + crate), 2) if crate is not None else None
        comp = "FULL" if gross is not None else "PARTIAL"
    elif body.vat_included == "YES":
        gross = p
        net = round(p / (1 + crate), 2) if crate is not None else None
        comp = "FULL" if net is not None else "GROSS_ONLY"
    else:
        net, gross, comp = None, None, "UNKNOWN"
    return {"competitor_net": net, "competitor_gross": gross, "vat_comparability": comp,
            "vat_note": None if comp == "FULL" else "Confronto economico non completamente omogeneo: IVA del preventivo concorrente non conosciuta."}


def _simulate(doc: dict, body: CompetitorInput, perms: set, user: dict) -> Dict[str, Any]:
    fs = doc.get("financial_snapshot") or {}
    our_net = float(doc.get("subtotal") or 0)
    our_gross = float(doc.get("total") or 0)
    commercial = float(doc.get("commercial_subtotal") or our_net)
    pay_pct = float(doc.get("automatic_discount_percent") or 0)
    norm = _normalize_competitor(body, _our_gross_rate(doc))
    max_disc = fs.get("max_discount_available_percent")
    min_net = fs.get("minimum_sustainable_net_price")
    vat_ratio = (our_gross / our_net) if our_net > 0 else 1.0
    out = {**norm, "our_net": our_net, "our_gross": our_gross, "commercial_subtotal": commercial,
           "minimum_sustainable_net_price": min_net, "minimum_sustainable_gross_price": None if min_net is None else round(min_net * vat_ratio, 2),
           "max_sustainable_discount_percent": max_disc, "target_net": None,
           "gross_difference_eur": None if norm["competitor_gross"] is None else round(our_gross - norm["competitor_gross"], 2)}
    target_net = norm["competitor_net"]
    if target_net is None and norm["competitor_gross"] is not None and our_net > 0:
        target_net = round(norm["competitor_gross"] / vat_ratio, 2)  # stesso trattamento IVA nostro (esplicitato)
        out["target_basis"] = "COMPETITOR_GROSS_AT_OUR_VAT"
    if target_net is None:
        out.update({"feasible": None, "authority": "UNKNOWN", "reason": "COMPETITOR_VAT_UNKNOWN"})
        return out
    out["target_net"] = target_net
    diff = round(our_net - target_net, 2)
    out.update({"price_difference_eur": diff, "price_difference_percent": round(diff / our_net * 100, 2) if our_net else None})
    # sconto effettivo esatto (monetario) sul valore commerciale, tenendo conto del payment discount moltiplicativo
    req_eff = max(0.0, (commercial - target_net) / commercial * 100) if commercial > 0 else 0.0
    req_commercial = max(0.0, (1 - (target_net / commercial) / max(1e-9, 1 - pay_pct / 100)) * 100) if commercial > 0 else 0.0
    out.update({"required_effective_discount_percent": round(req_eff, 4), "required_commercial_discount_percent": round(req_commercial, 4)})
    # snapshot al target: sconto in € esatto → Margin Engine
    amount = round(commercial - target_net / max(1e-9, 1 - pay_pct / 100), 2)
    sim_patch = _financial_totals_patch(doc.get("lines") or [], {**doc, "global_discount_type": "AMOUNT", "global_discount_value": max(0.0, amount), "promo_code": None})
    sfs = sim_patch.get("financial_snapshot") or {}
    post_margin = sfs.get("post_margin_percent")
    feasible = post_margin is not None and post_margin > MARGIN_FLOOR_PERCENT + 1e-9 and sfs.get("discount_status") != "BLOCKED"
    if diff < 0:
        authority, reason = "NOT_NEEDED", "OUR_PRICE_ALREADY_LOWER"
    elif not feasible:
        authority, reason = "BLOCKED", "BELOW_MARGIN_FLOOR"
    elif req_eff > COMMERCIAL_CAP:
        authority, reason = ("ADMIN_AUTHORIZED" if user_has_permission(user, perms, "quotes.override_discount_cap") else "ADMIN_APPROVAL_REQUIRED"), "OVER_COMMERCIAL_CAP"
    else:
        authority, reason = "COMMERCIAL_AUTHORIZED", "WITHIN_CAP"
    gap = None if feasible or min_net is None else round(min_net - target_net, 2)
    out.update({"feasible": feasible, "authority": authority, "reason": reason, "uncoverable_gap_eur": gap,
                "commission_if_matched": sfs.get("actual_commission_rate"), "discount_status_if_matched": sfs.get("discount_status"),
                "target_total_gross": sim_patch.get("total"), "simulated_snapshot": redact_financial_snapshot_for_role(sfs, ADMIN_MASTER_MARKER in perms),
                "scope_comparability": _scope(doc, body.competitor_scope)})
    return out


def _scope(doc: dict, comp: Dict[str, Any]) -> Dict[str, Any]:
    lines = doc.get("lines") or []
    svc = [s for l in lines for s in (l.get("automatic_services") or []) + (l.get("manual_extra_services") or [])]
    ours = {"products": bool(lines), "installation": doc.get("installation_mode") == "SUPPLY_AND_INSTALLATION" or any(str(l.get("category")) == "installation" for l in lines),
            "dismantling": doc.get("dismantling_mode") == "INCLUDED" or any(s.get("service_type") == "SMONTAGGIO" for s in svc),
            "accessories": any(str(l.get("category_code") or l.get("category")).upper() in ("ACCESSORI", "ACCESSORY") for l in lines),
            "services": bool(svc) or bool(doc.get("enea_practice_code")), "financing": bool(doc.get("financing_mode")),
            "delivery_days": doc.get("delivery_customer_text"), "warranty": doc.get("warranty_months")}
    rows, unknown, mismatch = [], 0, 0
    for k, ov in ours.items():
        cv = comp.get(k, None)
        if cv is None:
            unknown += 1
        elif isinstance(ov, bool) and bool(cv) != ov:
            mismatch += 1
        rows.append({"parameter": k, "ours": ov, "competitor": cv if cv is not None else "NON_DISPONIBILE", "match": None if cv is None else (bool(cv) == ov if isinstance(ov, bool) else None)})
    status = "UNKNOWN" if unknown == len(ours) else ("FULL" if mismatch == 0 and unknown == 0 else "PARTIAL")
    return {"status": status, "rows": rows, "note": None if status == "FULL" else "Il prezzo può essere inferiore ma l'offerta potrebbe non essere equivalente."}


@router.post("/{qid}/competitor/simulate")
async def competitor_simulate(qid: str, body: CompetitorInput, user: dict = Depends(require_permission("quotes.view"))):
    db = get_db()
    doc = await _load(db, qid, user)
    return _simulate(doc, body, await _get_perms(user), user)


@router.post("/{qid}/competitor")
async def competitor_save(qid: str, body: CompetitorInput, request: Request, user: dict = Depends(require_permission("quotes.edit"))):
    db = get_db()
    doc = await _load(db, qid, user)
    sim = _simulate(doc, body, await _get_perms(user), user)
    now = datetime.now(timezone.utc).isoformat()
    rec = {"_id": new_id(), "tenant_id": user["tenant_id"], "quote_id": qid, "competitor_name": body.competitor_name, "competitor_price": body.competitor_price,
           "vat_known": body.vat_included != "UNKNOWN", "vat_included": body.vat_included, "vat_rate": body.competitor_vat_rate,
           "gross_or_net": "GROSS" if body.vat_included == "YES" else ("NET" if body.vat_included == "NO" else "UNKNOWN"),
           "quote_date": body.quote_date, "notes": body.notes, "attachment_id": body.attachment_id, "competitor_scope": body.competitor_scope,
           "created_by": user["id"], "created_at": now, "deleted_at": None,
           "simulation_snapshot": {"our_price_at_comparison": sim["our_net"], "our_gross_at_comparison": sim["our_gross"], "competitor_price_normalized": sim.get("target_net"),
                                   "required_discount": sim.get("required_effective_discount_percent"), "max_sustainable_discount": sim.get("max_sustainable_discount_percent"),
                                   "minimum_sustainable_price": sim.get("minimum_sustainable_net_price"), "post_margin": (sim.get("simulated_snapshot") or {}).get("post_margin_percent"),
                                   "feasible": sim.get("feasible"), "authority": sim.get("authority"), "vat_comparability": sim.get("vat_comparability"),
                                   "scope_comparability": (sim.get("scope_comparability") or {}).get("status")},
           "decision": "SIMULATION_ONLY", "decision_by": None, "decision_at": None}
    await db.competitor_quotes.insert_one(rec)
    await record_audit(action="quotes.competitor.saved", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
                       entity_type="quote", entity_id=qid, after={"competitor_quote_id": rec["_id"], "competitor_price": body.competitor_price})
    return {**from_mongo(rec), "simulation": sim}


@router.get("/{qid}/competitor")
async def competitor_list(qid: str, user: dict = Depends(require_permission("quotes.view"))):
    db = get_db()
    await _load(db, qid, user)
    items = await db.competitor_quotes.find({"tenant_id": user["tenant_id"], "quote_id": qid, "deleted_at": None}).sort("created_at", -1).to_list(50)
    perms = await _get_perms(user)
    if ADMIN_MASTER_MARKER not in perms:
        for it in items:
            (it.get("simulation_snapshot") or {}).pop("post_margin", None)
    return {"items": [from_mongo(i) for i in items]}


@router.post("/{qid}/competitor/{cid}/apply")
async def competitor_apply(qid: str, cid: str, request: Request, user: dict = Depends(require_permission("quotes.apply_discount"))):
    """APPLICA PREZZO TARGET: sconto in € esatto (NEGOTIATED_TARGET) → il Margin Engine ricalcola. Nessuna modifica a listini/righe."""
    db = get_db()
    doc = await _load(db, qid, user)
    if _is_frozen(doc):
        raise HTTPException(409, "Preventivo accettato: non modificabile")
    rec = await db.competitor_quotes.find_one({"_id": cid, "tenant_id": user["tenant_id"], "quote_id": qid, "deleted_at": None})
    if not rec:
        raise HTTPException(404, "Confronto concorrente non trovato")
    perms = await _get_perms(user)
    body = CompetitorInput(competitor_price=rec["competitor_price"], vat_included=rec.get("vat_included") or "UNKNOWN", competitor_vat_rate=rec.get("vat_rate"), competitor_scope=rec.get("competitor_scope") or {})
    sim = _simulate(doc, body, perms, user)
    if sim.get("target_net") is None:
        raise HTTPException(400, {"code": "COMPETITOR_VAT_UNKNOWN", "message": "Prezzo target non determinabile: IVA concorrente non nota"})
    if sim["authority"] == "BLOCKED":
        raise HTTPException(400, {"code": "DISCOUNT_BLOCKED_MARGIN_FLOOR", "message": "Prezzo non economicamente sostenibile.", "minimum_sustainable_net_price": sim.get("minimum_sustainable_net_price")})
    if sim["authority"] == "ADMIN_APPROVAL_REQUIRED":
        raise HTTPException(403, {"code": "ADMIN_APPROVAL_REQUIRED", "message": "Sconto oltre 30%: richiede autorizzazione amministrativa"})
    if sim["authority"] == "NOT_NEEDED":
        raise HTTPException(400, {"code": "TARGET_ABOVE_CURRENT", "message": "Il prezzo target è superiore al prezzo attuale"})
    commercial = float(doc.get("commercial_subtotal") or doc.get("subtotal") or 0)
    pay_pct = float(doc.get("automatic_discount_percent") or 0)
    amount = round(commercial - sim["target_net"] / max(1e-9, 1 - pay_pct / 100), 2)
    fields = {"promo_code": None, "promo_code_description": None, "global_discount_type": "AMOUNT", "global_discount_value": amount,
              "global_discount_source": "NEGOTIATED_TARGET", "negotiated_target_net_price": sim["target_net"], "negotiated_from_competitor_quote_id": cid}
    patch = _financial_totals_patch(doc.get("lines") or [], {**doc, **fields})
    now = datetime.now(timezone.utc).isoformat()
    await db.quotes.update_one({"_id": qid}, {"$set": {**fields, **patch, "updated_at": now, "updated_by": user["id"]}, "$inc": {"version": 1}})
    await db.competitor_quotes.update_one({"_id": cid}, {"$set": {"decision": "TARGET_APPLIED", "decision_by": user["id"], "decision_at": now, "applied_discount_amount": amount}})
    await record_audit(action="quotes.competitor.target_applied", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
                       entity_type="quote", entity_id=qid, before={"subtotal": doc.get("subtotal")}, after={"subtotal": patch.get("subtotal"), "discount_amount": amount, "authority": sim["authority"]})
    return {"ok": True, "subtotal": patch.get("subtotal"), "total": patch.get("total"), "discount_amount": amount, "authority": sim["authority"],
            "financial_snapshot": redact_financial_snapshot_for_role(patch.get("financial_snapshot") or {}, ADMIN_MASTER_MARKER in perms)}
