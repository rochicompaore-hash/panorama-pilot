"""Contracts router — Ciclo di vita completo: draft → ready_for_review →
ready_for_signature → sent → viewed → signing → signed → (rejected|expired|cancelled|superseded).

Genera contratto da preventivo accettato con snapshot immutabile.
Firma elettronica semplice (canvas + optional OTP + hash + audit trail).
Dopo firma: contratto immutabile, ogni modifica richiede una variante.
"""
from __future__ import annotations
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field

from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.mongo_utils import from_mongo, to_mongo
from app.models import new_id
from app.services.audit import record_audit
from app.services.timeline import record_activity
from app.services.contract_pdf import render_contract_pdf, store_contract_pdf, get_signed_url
from app.services.signature_provider import list_providers as list_sign_providers
from app.services.otp import create_otp as otp_create, verify_otp as otp_verify, mask_email
from app.services.email import send_email as email_send
from app.services.contracts_helpers import (
    load_quote_or_400, assert_no_active_contract, next_contract_number,
    build_contract_snapshot, compute_snapshot_hash, build_signature_hash,
    load_valid_signing_token, verify_public_otp,
    presign_errors, build_signed_snapshot, CUSTOMER_EDITABLE_KEYS, SITE_EDITABLE_KEYS,
)
from app.config import settings
import secrets
from fastapi.responses import Response, StreamingResponse

router = APIRouter(prefix="/contracts", tags=["contracts"])


VALID_STATES = [
    "draft", "ready_for_review", "ready_for_signature",
    "sent", "viewed", "signing", "signed",
    "rejected", "expired", "cancelled", "superseded",
]

# Transizioni permesse (from → allowed_to)
STATE_TRANSITIONS = {
    "draft": ["ready_for_review", "cancelled"],
    "ready_for_review": ["ready_for_signature", "draft", "cancelled"],
    "ready_for_signature": ["sent", "cancelled"],
    "sent": ["viewed", "signing", "expired", "cancelled"],
    "viewed": ["signing", "expired", "cancelled"],
    "signing": ["signed", "rejected", "expired"],
    "signed": ["superseded"],   # solo variante può superseders
    "rejected": ["draft"],
    "expired": ["draft"],
    "cancelled": [],
    "superseded": [],
}


class GenerateFromQuoteRequest(BaseModel):
    quote_id: str
    include_snapshot: bool = True
    payment_terms: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None


class TransitionRequest(BaseModel):
    to_state: str
    reason: Optional[str] = None


class SignRequest(BaseModel):
    signer_name: str
    signer_email: Optional[str] = None
    signature_data_url: str        # base64 PNG from canvas
    accept_terms: bool = True
    otp_code: Optional[str] = None


class SendForSignatureRequest(BaseModel):
    to_email: str
    channel: str = "email"    # future: whatsapp
    expires_hours: int = 168  # 7 giorni default
    message: Optional[str] = None


# =====================================================================
# msg 803 — ACCEPTED QUOTE → CONTRACT V1
# =====================================================================
ACTIVE_CONTRACT_FILTER = {"contract_status": {"$nin": ["cancelled", "superseded", "rejected"]}}


class PartiesPatch(BaseModel):
    customer: Dict[str, Any] = Field(default_factory=dict)
    site: Dict[str, Any] = Field(default_factory=dict)
    sync_customer: bool = False


class ContractPatch(BaseModel):
    notes: Optional[str] = None


def _assert_not_signed(doc: dict) -> None:
    if doc.get("contract_status") in ("signed", "superseded") or doc.get("lifecycle_status") == "ACTIVE":
        raise HTTPException(409, {"code": "CONTRACT_SIGNED_IMMUTABLE", "message": "Contratto firmato: usa Addendum o Revisione."})


def _raise_if_presign_blocked(doc: dict) -> None:
    errs = presign_errors(doc)
    if errs:
        raise HTTPException(400, {"code": "PRESIGN_CHECK_FAILED", "errors": errs,
                                  "message": "Dati obbligatori mancanti: " + ", ".join(errs)})


@router.get("/by-quote/{qid}")
async def contract_by_quote(qid: str, user: dict = Depends(require_permission("contracts.view"))):
    db = get_db()
    doc = await db.contracts.find_one({"tenant_id": user["tenant_id"], "quote_id": qid, "deleted_at": None, **ACTIVE_CONTRACT_FILTER},
                                      sort=[("created_at", -1)])
    if not doc:
        raise HTTPException(404, "Nessun contratto attivo per questo preventivo")
    return from_mongo(doc)


@router.get("/{cid}/presign-check")
async def contract_presign_check(cid: str, user: dict = Depends(require_permission("contracts.view"))):
    db = get_db()
    doc = await db.contracts.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Contratto non trovato")
    errs = presign_errors(doc)
    return {"contract_id": cid, "ok": not errs, "errors": errs, "general_terms_version": doc.get("general_terms_version")}


@router.patch("/{cid}")
async def patch_contract(cid: str, body: Dict[str, Any], request: Request,
                         user: dict = Depends(require_permission("contracts.create"))):
    """REVISION GUARD (msg 803 §7): qualsiasi campo economico/commerciale → CONTRACT_REVISION_REQUIRED. Solo `notes` ammesso."""
    db = get_db()
    doc = await db.contracts.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Contratto non trovato")
    _assert_not_signed(doc)
    forbidden = [k for k in body.keys() if k != "notes"]
    if forbidden:
        raise HTTPException(409, {"code": "CONTRACT_REVISION_REQUIRED", "fields": forbidden,
                                  "message": "Prodotti, quantità, prezzi, sconti, IVA e condizioni economiche non sono modificabili: crea una REVISIONE del preventivo."})
    now = datetime.now(timezone.utc)
    await db.contracts.update_one({"_id": cid}, {"$set": {"notes": body.get("notes"), "updated_at": now, "updated_by": user["id"]}})
    return {"ok": True}


@router.patch("/{cid}/parties")
async def patch_contract_parties(cid: str, body: PartiesPatch, request: Request,
                                 user: dict = Depends(require_permission("contracts.create"))):
    """Correzione dati formali cliente/cantiere PRIMA della firma (msg 803 §5-§6) con audit old/new e sync anagrafica opzionale."""
    db = get_db()
    doc = await db.contracts.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Contratto non trovato")
    _assert_not_signed(doc)
    bad = [k for k in body.customer if k not in CUSTOMER_EDITABLE_KEYS] + [k for k in body.site if k not in SITE_EDITABLE_KEYS]
    if bad:
        raise HTTPException(409, {"code": "CONTRACT_REVISION_REQUIRED", "fields": bad,
                                  "message": "Campo non modificabile nel contratto: richiede revisione."})
    snap = dict(doc.get("quote_snapshot") or {})
    cust = dict(snap.get("customer") or {})
    site = dict(snap.get("site") or {})
    now = datetime.now(timezone.utc)
    changes = []
    for k, v in body.customer.items():
        if cust.get(k) != v:
            changes.append({"scope": "customer", "field": k, "old_value": cust.get(k), "new_value": v,
                            "changed_by": user["id"], "changed_by_email": user["email"], "changed_at": now.isoformat(),
                            "synced_to_customer": body.sync_customer})
            cust[k] = v
    for k, v in body.site.items():
        if site.get(k) != v:
            changes.append({"scope": "site", "field": k, "old_value": site.get(k), "new_value": v,
                            "changed_by": user["id"], "changed_by_email": user["email"], "changed_at": now.isoformat(),
                            "synced_to_customer": False})
            site[k] = v
    if not changes:
        return {"ok": True, "changes": []}
    snap["customer"] = cust
    snap["site"] = site
    await db.contracts.update_one({"_id": cid}, {"$set": {"quote_snapshot": snap, "updated_at": now, "updated_by": user["id"]},
                                                 "$push": {"party_changes": {"$each": changes}}})
    synced = False
    if body.sync_customer and doc.get("customer_id") and body.customer:
        cust_patch = {k: v for k, v in body.customer.items() if k in CUSTOMER_EDITABLE_KEYS}
        before = await db.customers.find_one({"_id": doc["customer_id"], "tenant_id": user["tenant_id"]}, {k: 1 for k in cust_patch})
        r = await db.customers.update_one({"_id": doc["customer_id"], "tenant_id": user["tenant_id"], "deleted_at": None},
                                          {"$set": {**cust_patch, "updated_at": now.isoformat(), "updated_by": user["id"]}})
        synced = r.matched_count == 1
        if synced:
            await record_audit(action="customers.update.from_contract", tenant_id=user["tenant_id"], user_id=user["id"],
                               user_email=user["email"], ip=get_client_ip(request), entity_type="customer", entity_id=doc["customer_id"],
                               before={k: (before or {}).get(k) for k in cust_patch}, after=cust_patch)
    await record_audit(action="contracts.parties.update", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request), entity_type="contract", entity_id=cid,
                       before={c["field"]: c["old_value"] for c in changes}, after={c["field"]: c["new_value"] for c in changes})
    return {"ok": True, "changes": changes, "customer_synced": synced, "presign_errors": presign_errors({**doc, "quote_snapshot": snap})}


async def _ensure_payment_plan(db, doc: dict, when: datetime) -> None:
    """CFO V1 §11: contratto firmato → payment_plan collegato (contract_id, order_id, customer_id, legal_entity_id) dalle condizioni contrattuali.
    Idempotente. Nessun piano per contratti senza importi (LEGACY_ECONOMIC_DATA_INCOMPLETE)."""
    from app.models import new_id
    eco = doc.get("economic_snapshot") or {}
    qs = doc.get("quote_snapshot") or {}
    total = float(eco.get("total") or qs.get("total") or 0)
    if total <= 0 or await db.payment_plans.find_one({"tenant_id": doc["tenant_id"], "contract_id": doc["_id"], "deleted_at": None}):
        return
    schedule = ((eco.get("payment_terms") or {}).get("schedule")) or qs.get("payment_schedule") or [{"step": "ORDER", "percent": 50, "label": "Acconto alla firma"}, {"step": "GOODS_READY", "percent": 50, "label": "Saldo ad avviso merce pronta"}]
    trig = {"ORDER": "signature", "GOODS_READY": "goods_ready", "TECHNICAL_SURVEY": "technical_survey", "FINANCING": "financing", "INSTALLATION": "installation"}
    inst, acc = [], 0.0
    for i, st in enumerate(schedule):
        pct = st.get("percent")
        amt = round(total * float(pct) / 100, 2) if pct is not None else None
        if i == len(schedule) - 1 and amt is not None:
            amt = round(total - acc, 2)
        acc += amt or 0
        t = trig.get(str(st.get("step") or "").upper(), str(st.get("step") or "").lower())
        inst.append({"ref": f"I{i + 1}", "label": st.get("label"), "trigger": t, "percent": pct, "amount": amt, "due_date": when.date().isoformat() if t == "signature" else None,
                     "paid_amount": 0, "paid_at": None, "payment_method": None, "installment_status": "pending" if amt is not None else "amount_to_define", "reminder_sent_at": None})
    order = await db.sales_orders.find_one({"tenant_id": doc["tenant_id"], "contract_id": doc["_id"], "deleted_at": None}, {"_id": 1})
    await db.payment_plans.insert_one({"_id": new_id(), "tenant_id": doc["tenant_id"], "contract_id": doc["_id"], "sales_order_id": (order or {}).get("_id"), "customer_id": doc.get("customer_id"),
                                       "legal_entity_id": doc.get("legal_entity_id"), "total_amount": total, "currency": "EUR", "installments": inst, "outstanding_amount": total, "paid_amount": 0,
                                       "plan_status": "active", "source": "CONTRACT_SIGNED", "status": "active", "deleted_at": None, "version": 1, "created_at": when, "updated_at": when, "created_by": None, "updated_by": None})


async def _activate_signed_contract(db, doc: dict, when: datetime) -> None:
    """Post-firma (msg 803 §12-§13-§15): freeze snapshot, CONTRACT ACTIVE, evento CONTRACT_AVAILABLE per il Customer Portal."""
    frozen = build_signed_snapshot(doc, when)
    await db.contracts.update_one({"_id": doc["_id"]}, {"$set": {"signed_snapshot": frozen, "lifecycle_status": "ACTIVE", "active_at": when}})
    await _ensure_payment_plan(db, doc, when)
    from app.services.customer_email_events import notify_customer_event
    await notify_customer_event(
        db, tenant_id=doc["tenant_id"], customer_id=doc.get("customer_id"), event_type="CONTRACT_AVAILABLE",
        entity_type="contract", entity_id=doc["_id"], title="Il tuo contratto firmato è disponibile",
        body=f"Il contratto {doc.get('number')} è stato firmato ed è disponibile nella tua area cliente.",
        cta_label="Apri area cliente", cta_path="/customer-portal", dedupe_suffix="signed")


# =====================================================================
# LIST + GET
# =====================================================================
@router.get("")
async def list_contracts(
    q: Optional[str] = None, customer_id: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = Query(100, le=500), skip: int = 0,
    user: dict = Depends(require_permission("contracts.view")),
):
    db = get_db()
    query: Dict[str, Any] = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if customer_id: query["customer_id"] = customer_id
    if state: query["contract_status"] = state
    if q: query["$or"] = [{"number": {"$regex": q, "$options": "i"}}]
    total = await db.contracts.count_documents(query)
    docs = await db.contracts.find(query).sort([("created_at", -1)]).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": [from_mongo(d) for d in docs]}


@router.get("/{cid}")
async def get_contract(cid: str, user: dict = Depends(require_permission("contracts.view"))):
    db = get_db()
    doc = await db.contracts.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Contratto non trovato")
    return from_mongo(doc)


# =====================================================================
# GENERATE FROM QUOTE — snapshot immutabile
# =====================================================================
@router.post("/generate-from-quote")
async def generate_from_quote(body: GenerateFromQuoteRequest, request: Request,
                                user: dict = Depends(require_permission("contracts.generate"))):
    db = get_db()
    tenant_id = user["tenant_id"]
    quote = await load_quote_or_400(db, tenant_id, body.quote_id)
    existing = await db.contracts.find_one({"tenant_id": tenant_id, "quote_id": body.quote_id, "deleted_at": None, **ACTIVE_CONTRACT_FILTER})
    if existing:
        return from_mongo(existing)   # msg 803 §1 — nessun duplicato: APRI CONTRATTO

    number, seq_n, _ = await next_contract_number(db, tenant_id)
    snapshot = await build_contract_snapshot(db, tenant_id, quote, body.payment_terms)
    snap_hash = compute_snapshot_hash(
        body.quote_id, number, quote.get("total"), snapshot.pop("_products_count", 0),
    )
    snapshot["snapshot_hash"] = snap_hash

    now = datetime.now(timezone.utc)
    contract_id = new_id()
    doc = {
        "_id": contract_id,
        "tenant_id": tenant_id,
        "number": number, "number_int": seq_n,
        "quote_id": body.quote_id,
        "quote_revision": quote.get("revision", 0),
        "customer_id": quote.get("customer_id"),
        "quote_snapshot": snapshot,
        "snapshot_hash": snap_hash,
        "general_terms_version": snapshot["general_terms_version"],
        "general_terms_hash": snapshot["general_terms_hash"],
        "general_terms_snapshot_id": snapshot.get("general_terms_snapshot_id"),
        "quote_revision_id": snapshot["quote_revision_id"],
        "quote_snapshot_id": snapshot.get("quote_snapshot_id"),
        "accepted_at": snapshot.get("accepted_at"),
        "contract_status": "draft",
        "state_history": [{
            "state": "draft", "at": now.isoformat(),
            "by": user["id"], "by_email": user["email"],
        }],
        "notes": body.notes,
        "created_at": now, "created_by": user["id"],
        "updated_at": now, "updated_by": user["id"],
        "deleted_at": None,
    }
    await db.contracts.insert_one(doc)
    await db.quotes.update_one({"_id": body.quote_id}, {"$set": {"contract_id": contract_id, "updated_at": now.isoformat()}})
    await record_audit(
        action="contracts.generate", tenant_id=tenant_id,
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="contract", entity_id=contract_id,
        after={"quote_id": body.quote_id, "number": number, "snapshot_hash": snap_hash},
    )
    await record_activity(
        tenant_id=tenant_id, type="contract_generated",
        subject=f"Contratto {number} generato da preventivo {quote.get('number')}",
        customer_id=quote.get("customer_id"),
        user_id=user["id"], user_email=user["email"],
        meta={"contract_id": contract_id},
    )
    return from_mongo(doc)


# =====================================================================
# STATE TRANSITIONS
# =====================================================================
def _validate_transition(current: str, target: str) -> None:
    if current not in VALID_STATES:
        raise HTTPException(400, f"Stato corrente sconosciuto: {current}")
    if target not in VALID_STATES:
        raise HTTPException(400, f"Stato target sconosciuto: {target}")
    if target not in STATE_TRANSITIONS.get(current, []):
        raise HTTPException(400, f"Transizione non permessa: {current} → {target}. "
                                    f"Permesse: {STATE_TRANSITIONS.get(current)}")


@router.post("/{cid}/transition")
async def transition(cid: str, body: TransitionRequest, request: Request,
                       user: dict = Depends(require_permission("contracts.create"))):
    db = get_db()
    doc = await db.contracts.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Contratto non trovato")
    current = doc.get("contract_status", "draft")
    _validate_transition(current, body.to_state)
    if body.to_state == "ready_for_signature":
        _raise_if_presign_blocked(doc)
    # Signed è immutabile — blocca modifiche
    if current == "signed" and body.to_state != "superseded":
        raise HTTPException(400, "Contratto firmato: solo variante può superarlo")
    now = datetime.now(timezone.utc)
    history_entry = {
        "state": body.to_state, "from_state": current, "at": now.isoformat(),
        "by": user["id"], "by_email": user["email"], "reason": body.reason,
    }
    await db.contracts.update_one({"_id": cid}, {
        "$set": {"contract_status": body.to_state, "updated_at": now, "updated_by": user["id"]},
        "$push": {"state_history": history_entry},
    })
    await record_audit(action=f"contracts.transition.{body.to_state}",
                        tenant_id=user["tenant_id"], user_id=user["id"],
                        user_email=user["email"], ip=get_client_ip(request),
                        entity_type="contract", entity_id=cid,
                        before={"status": current}, after={"status": body.to_state})
    return {"ok": True, "from": current, "to": body.to_state}


# =====================================================================
# SEND FOR SIGNATURE — genera link pubblico + set stato "sent"
# =====================================================================
@router.post("/{cid}/send-for-signature")
async def send_for_signature(cid: str, body: SendForSignatureRequest, request: Request,
                                user: dict = Depends(require_permission("contracts.send"))):
    db = get_db()
    doc = await db.contracts.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Contratto non trovato")
    current = doc.get("contract_status")
    if current not in ("ready_for_signature", "sent", "viewed", "rejected"):
        raise HTTPException(400, f"Impossibile inviare da stato {current}")
    _raise_if_presign_blocked(doc)

    # Genera token di firma sicuro
    now = datetime.now(timezone.utc)
    token = new_id() + hashlib.sha256(f"{cid}|{now.isoformat()}".encode()).hexdigest()[:16]
    expires_at = now + timedelta(hours=body.expires_hours)
    await db.contract_signing_tokens.insert_one({
        "_id": token, "tenant_id": user["tenant_id"], "contract_id": cid,
        "to_email": body.to_email, "channel": body.channel,
        "expires_at": expires_at, "message": body.message,
        "sent_at": now, "sent_by": user["id"], "consumed": False,
    })
    await db.contracts.update_one({"_id": cid}, {"$set": {
        "contract_status": "sent" if current != "sent" else current,
        "sent_at": now, "signing_link_expires_at": expires_at,
        "signing_to_email": body.to_email,
        "updated_at": now, "updated_by": user["id"],
    }, "$push": {"state_history": {
        "state": "sent", "at": now.isoformat(), "by": user["id"],
        "reason": f"Inviato a {body.to_email}",
    }}})
    await record_audit(action="contracts.send", tenant_id=user["tenant_id"],
                        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
                        entity_type="contract", entity_id=cid,
                        after={"to": body.to_email, "expires_at": expires_at.isoformat()})
    # CONTRACT_AVAILABLE (msg 794): email al cliente della commessa via servizio centrale; destinatario risolto server-side.
    from app.services.customer_email_events import notify_customer_event
    email_log_id = await notify_customer_event(
        db, tenant_id=user["tenant_id"], customer_id=doc.get("customer_id"), event_type="CONTRACT_AVAILABLE", entity_type="contract", entity_id=cid,
        title="Il tuo contratto è pronto per la firma", body=f"Il contratto {doc.get('number')} è disponibile per la revisione e la firma elettronica. "
        f"Il link è personale e scade il {expires_at.strftime('%d/%m/%Y')}.", cta_label="Visualizza documento", cta_path=f"/contract-sign/{token}", dedupe_suffix=token[:12])
    return {"ok": True, "signing_token": token, "expires_at": expires_at.isoformat(), "email_log_id": email_log_id,
             "signing_url": f"/contract-sign/{token}"}


# =====================================================================
# PUBLIC — Accesso al contratto via token (per firma) — no auth, tracked
# =====================================================================
@router.get("/public/{token}")
async def public_view_contract(token: str, request: Request):
    db = get_db()
    tk = await db.contract_signing_tokens.find_one({"_id": token, "consumed": False})
    if not tk:
        raise HTTPException(404, "Token firma non valido o già consumato")
    if tk.get("expires_at"):
        exp = tk["expires_at"]
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(410, "Token scaduto")
    doc = await db.contracts.find_one({
        "_id": tk["contract_id"], "tenant_id": tk["tenant_id"], "deleted_at": None,
    })
    if not doc:
        raise HTTPException(404, "Contratto non trovato")
    # Marca viewed
    if doc.get("contract_status") == "sent":
        now = datetime.now(timezone.utc)
        await db.contracts.update_one({"_id": doc["_id"]}, {"$set": {
            "contract_status": "viewed", "viewed_at": now,
        }, "$push": {"state_history": {
            "state": "viewed", "at": now.isoformat(),
            "by_ip": get_client_ip(request), "by": None,
        }}})
    return {
        "contract": from_mongo(doc),
        "signer_email": tk.get("to_email"),
        "expires_at": tk.get("expires_at").isoformat() if tk.get("expires_at") else None,
    }


@router.post("/public/{token}/request-otp")
async def public_request_otp(token: str, request: Request):
    """Genera OTP reale (random hashato + scadenza + max tentativi) e invia
    tramite provider email configurato. Se provider non configurato in prod:
    ritorna `configuration_required=true`."""
    db = get_db()
    tk = await db.contract_signing_tokens.find_one({"_id": token, "consumed": False})
    if not tk:
        raise HTTPException(404, "Token non valido")
    contract = await db.contracts.find_one({"_id": tk["contract_id"]})
    if not contract:
        raise HTTPException(404, "Contratto non trovato")
    # Rate limit: max N OTP in finestra 5 min
    from datetime import timedelta as _td
    since = datetime.now(timezone.utc) - _td(minutes=5)
    recent = await db.quote_otp_requests.count_documents({
        "token_id": token, "created_at": {"$gt": since}
    })
    if recent >= 3:
        raise HTTPException(429, "Troppe richieste OTP — riprova tra qualche minuto")

    req, raw_code = await otp_create(
        token_id=token, quote_id=contract.get("quote_id") or contract["_id"],
        email=tk["to_email"], user_agent=request.headers.get("user-agent"),
    )
    req_doc = req.model_dump(by_alias=True)
    req_doc["tenant_id"] = tk["tenant_id"]
    req_doc["created_at"] = datetime.now(timezone.utc)
    await db.quote_otp_requests.insert_one(req_doc)
    # Prova invio email (se provider configurato)
    from app.config import settings as _s, is_prod_like as _prod
    if _s.EMAIL_PROVIDER == "mock" or not _s.RESEND_API_KEY:
        email_status = "configuration_required" if _prod() else "mocked_dev"
    else:
        email_status = "mocked_dev"
    try:
        subj = f"Codice OTP firma contratto {contract.get('number')}"
        html = f"<p>Il tuo codice OTP è: <b style='font-size:24px'>{raw_code}</b></p><p>Scade in {settings.OTP_TTL_SECONDS//60} minuti.</p>"
        text = f"OTP: {raw_code} (scade in {settings.OTP_TTL_SECONDS//60} min)"
        eid = await email_send(to=tk["to_email"], subject=subj, template="contract_otp",
                                 html=html, text=text)
        email_status = f"sent:{eid}"
    except Exception as e:
        email_status = f"delivery_failed:{type(e).__name__}"
    debug_code = req.debug_code_plain  # solo in dev con OTP_DEBUG_ENABLED
    return {
        "ok": True, "request_id": req.id, "otp_id": req.id,
        "expires_in_seconds": settings.OTP_TTL_SECONDS,
        "delivery_status": email_status, "recipient_masked": mask_email(tk["to_email"]),
        **({"debug_code": debug_code} if debug_code else {}),
    }


class PublicSignRequest(BaseModel):
    signer_name: str
    signature_data_url: str
    accept_terms: bool = True
    otp_code: Optional[str] = None
    otp_request_id: Optional[str] = None


@router.post("/public/{token}/sign")
async def public_sign(token: str, body: PublicSignRequest, request: Request):
    db = get_db()
    tk = await load_valid_signing_token(db, token)
    if not body.accept_terms:
        raise HTTPException(400, "Accettazione condizioni obbligatoria")
    otp_used = False
    if body.otp_code:
        otp_used = await verify_public_otp(db, body.otp_request_id, body.otp_code)

    doc = await db.contracts.find_one({
        "_id": tk["contract_id"], "tenant_id": tk["tenant_id"], "deleted_at": None,
    })
    if not doc:
        raise HTTPException(404, "Contratto non trovato")
    if doc.get("contract_status") == "signed":
        raise HTTPException(400, "Contratto già firmato")
    _raise_if_presign_blocked(doc)

    now = datetime.now(timezone.utc)
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    signature_hash = build_signature_hash(doc["_id"], body.signer_name, ip, ua, now, doc)
    signature_type = "electronic_simple_otp" if otp_used else "electronic_simple"

    await db.contracts.update_one({"_id": doc["_id"]}, {"$set": {
        "contract_status": "signed",
        "signed_at": now,
        "signed_by_name": body.signer_name,
        "signed_by_email": tk.get("to_email"),
        "signed_ip": ip, "signed_ua": ua,
        "signature_data_url": body.signature_data_url,
        "signature_hash": signature_hash,
        "signature_type": signature_type,
        "updated_at": now,
    }, "$push": {"state_history": {
        "state": "signed", "at": now.isoformat(),
        "by_name": body.signer_name, "by_email": tk.get("to_email"),
        "by_ip": ip, "signature_hash": signature_hash,
    }}})
    await db.contract_signing_tokens.update_one({"_id": token}, {"$set": {
        "consumed": True, "consumed_at": now,
    }})
    await _activate_signed_contract(db, doc, now)
    await record_audit(action="contracts.sign.public", tenant_id=tk["tenant_id"],
                        user_id=None, user_email=tk.get("to_email"), ip=ip,
                        entity_type="contract", entity_id=doc["_id"],
                        after={"signer": body.signer_name, "hash": signature_hash,
                                "otp": otp_used})
    # Hook workflow → create Survey (isolato: fallimenti hook NON annullano la firma)
    try:
        from app.services.workflow_engine import ensure_survey_from_contract
        updated = await db.contracts.find_one({"_id": doc["_id"]})
        await ensure_survey_from_contract(
            tenant_id=tk["tenant_id"], contract=updated, actor_id=None,
        )
    except Exception:
        # Log but do not fail signature (workflow is idempotent, will re-run)
        import logging
        logging.getLogger("contracts").exception("survey hook failed after public sign")
    return {"ok": True, "signature_hash": signature_hash,
             "signature_type": signature_type}


# =====================================================================
# INTERNAL SIGN — via authenticated user (fallback)
# =====================================================================
@router.post("/{cid}/sign")
async def sign_contract_internal(cid: str, body: SignRequest, request: Request,
                                    user: dict = Depends(require_permission("contracts.sign"))):
    db = get_db()
    doc = await db.contracts.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Contratto non trovato")
    if doc.get("contract_status") == "signed":
        raise HTTPException(400, "Contratto già firmato")
    if not body.accept_terms:
        raise HTTPException(400, "Accettazione condizioni obbligatoria")
    _raise_if_presign_blocked(doc)
    now = datetime.now(timezone.utc)
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    payload = f"{cid}|{body.signer_name}|{ip}|{ua}|{now.isoformat()}|{doc.get('number')}|{doc.get('snapshot_hash')}"
    signature_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    await db.contracts.update_one({"_id": cid}, {"$set": {
        "contract_status": "signed",
        "signed_at": now,
        "signed_by_name": body.signer_name, "signed_by_email": body.signer_email,
        "signed_ip": ip, "signed_ua": ua,
        "signature_data_url": body.signature_data_url,
        "signature_hash": signature_hash,
        "signature_type": "electronic_simple",
        "updated_at": now, "updated_by": user["id"],
    }, "$push": {"state_history": {
        "state": "signed", "at": now.isoformat(),
        "by": user["id"], "by_email": user["email"],
        "signature_hash": signature_hash,
    }}})
    await _activate_signed_contract(db, doc, now)
    await record_audit(action="contracts.sign", tenant_id=user["tenant_id"],
                        user_id=user["id"], user_email=user["email"], ip=ip,
                        entity_type="contract", entity_id=cid,
                        after={"signer": body.signer_name, "hash": signature_hash})
    # Post-sign workflow hook
    try:
        from app.services.workflow_engine import ensure_survey_from_contract
        updated = await db.contracts.find_one({"_id": cid})
        await ensure_survey_from_contract(
            tenant_id=user["tenant_id"], contract=updated, actor_id=user["id"],
        )
    except Exception:
        pass
    return {"ok": True, "signature_hash": signature_hash}


# =====================================================================
# CANCEL — non firmato
# =====================================================================
@router.post("/{cid}/cancel")
async def cancel_contract(cid: str, request: Request,
                            user: dict = Depends(require_permission("contracts.cancel"))):
    db = get_db()
    doc = await db.contracts.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Contratto non trovato")
    if doc.get("contract_status") == "signed":
        raise HTTPException(400, "Contratto firmato: non annullabile — usa 'superseded' con nuova variante")
    now = datetime.now(timezone.utc)
    await db.contracts.update_one({"_id": cid}, {"$set": {
        "contract_status": "cancelled",
        "updated_at": now, "updated_by": user["id"],
    }, "$push": {"state_history": {
        "state": "cancelled", "at": now.isoformat(),
        "by": user["id"], "by_email": user["email"],
    }}})
    await record_audit(action="contracts.cancel", tenant_id=user["tenant_id"],
                        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
                        entity_type="contract", entity_id=cid)
    return {"ok": True}


# =====================================================================
# CREATE VARIATION — dopo firma: crea nuova versione del contratto
# =====================================================================
class CreateVariationRequest(BaseModel):
    new_quote_id: Optional[str] = None
    reason: str
    notes: Optional[str] = None


@router.post("/{cid}/create-variation")
async def create_variation(cid: str, body: CreateVariationRequest, request: Request,
                             user: dict = Depends(require_permission("contracts.create"))):
    db = get_db()
    parent = await db.contracts.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not parent:
        raise HTTPException(404, "Contratto non trovato")
    if parent.get("contract_status") not in ("signed", "sent", "viewed"):
        raise HTTPException(400, "Variante creabile solo su contratti firmati/inviati")

    quote_id = body.new_quote_id or parent.get("quote_id")
    quote = await db.quotes.find_one({"_id": quote_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not quote:
        raise HTTPException(404, "Preventivo per variante non trovato")

    # Sequence variante
    parent_number = parent.get("number", "CT-VAR")
    variation_index = int(parent.get("variation_index", 0)) + 1
    number = f"{parent_number}-V{variation_index}"

    now = datetime.now(timezone.utc)
    new_id_ = new_id()
    doc = {
        "_id": new_id_,
        "tenant_id": user["tenant_id"],
        "number": number,
        "quote_id": quote_id,
        "customer_id": parent.get("customer_id"),
        "parent_contract_id": cid,
        "variation_index": variation_index,
        "variation_reason": body.reason,
        "quote_snapshot": parent.get("quote_snapshot"),   # sarà rigenerato via PATCH
        "snapshot_hash": parent.get("snapshot_hash"),
        "contract_status": "draft",
        "notes": body.notes,
        "state_history": [{
            "state": "draft", "at": now.isoformat(),
            "by": user["id"], "by_email": user["email"],
            "reason": f"Variante di {parent_number}: {body.reason}",
        }],
        "created_at": now, "created_by": user["id"],
        "updated_at": now, "updated_by": user["id"],
        "deleted_at": None,
    }
    await db.contracts.insert_one(doc)
    # Marca parent come superseded se signed
    if parent.get("contract_status") == "signed":
        await db.contracts.update_one({"_id": cid}, {"$set": {
            "contract_status": "superseded", "superseded_by": new_id_,
            "updated_at": now,
        }, "$push": {"state_history": {
            "state": "superseded", "at": now.isoformat(),
            "by": user["id"], "reason": f"Sostituito da variante {number}",
        }}})
    await record_audit(action="contracts.create_variation", tenant_id=user["tenant_id"],
                        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
                        entity_type="contract", entity_id=new_id_,
                        after={"parent_id": cid, "variation_index": variation_index,
                                "reason": body.reason})
    return from_mongo(doc)


# =====================================================================
# AUDIT VIEW — timeline stati
# =====================================================================
@router.get("/{cid}/timeline")
async def contract_timeline(cid: str, user: dict = Depends(require_permission("contracts.view"))):
    db = get_db()
    doc = await db.contracts.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Contratto non trovato")
    return {
        "contract_id": cid,
        "current_state": doc.get("contract_status"),
        "state_history": doc.get("state_history") or [],
        "snapshot_hash": doc.get("snapshot_hash"),
        "signature_hash": doc.get("signature_hash"),
        "signed_at": doc.get("signed_at").isoformat() if doc.get("signed_at") else None,
    }


@router.get("/{cid}/terms-verify")
async def contract_terms_verify(cid: str, user: dict = Depends(require_permission("contracts.view"))):
    """INVARIANCE CHECK (msg 782 §19): il blocco condizioni del contratto deve essere IDENTICO alla versione canonica."""
    from app.services.general_terms_canonical import canonical_terms_text, canonical_hash, get_canonical
    db = get_db()
    doc = await db.contracts.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Contratto non trovato")
    gt = (doc.get("quote_snapshot") or {}).get("general_terms")
    if not gt:
        return {"contract_id": cid, "status": "CONTRACT_TERMS_SOURCE_MISSING", "identical": False}
    stored_text = canonical_terms_text(gt.get("articles") or [], gt.get("clause_approval") or {})
    try:
        canon = get_canonical(gt.get("version"))
    except KeyError:
        return {"contract_id": cid, "status": "UNKNOWN_VERSION", "version": gt.get("version"), "identical": False}
    identical = stored_text == canon["full_text"] and canonical_hash(stored_text) == doc.get("general_terms_hash") == canon["general_terms_hash"]
    return {"contract_id": cid, "version": gt.get("version"), "identical": identical,
            "status": "IDENTICAL" if identical else "DIVERGENT",
            "stored_hash": canonical_hash(stored_text), "canonical_hash": canon["general_terms_hash"],
            "articles_count": len(gt.get("articles") or []), "canonical_articles_count": canon["articles_count"]}


# =====================================================================
# PDF endpoints — anteprima, download, versionato + storage privato
# =====================================================================
@router.get("/{cid}/pdf/preview")
async def contract_pdf_preview(cid: str, user: dict = Depends(require_permission("contracts.view"))):
    """Anteprima PDF (bozza in draft; finale se firmato). Stream inline."""
    db = get_db()
    doc = await db.contracts.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Contratto non trovato")
    signed = doc.get("contract_status") == "signed"
    watermark = "signed" if signed else "draft"
    try:
        pdf_bytes = render_contract_pdf(doc, watermark=watermark)
    except Exception as e:
        raise HTTPException(500, f"Errore render PDF: {type(e).__name__}: {str(e)[:200]}")
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=contract-{doc.get('number')}-preview.pdf"},
    )


@router.post("/{cid}/pdf/generate")
async def contract_pdf_generate(cid: str, request: Request,
                                  user: dict = Depends(require_permission("contracts.download"))):
    """Genera e archivia una versione PDF nel storage privato.
    Ogni chiamata crea una nuova versione (NON sovrascrive)."""
    db = get_db()
    doc = await db.contracts.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Contratto non trovato")
    signed = doc.get("contract_status") == "signed"
    kind = "signed" if signed else "preview"
    watermark = "signed" if signed else "draft"
    pdf_bytes = render_contract_pdf(doc, watermark=watermark)
    existing = doc.get("pdf_versions") or []
    version = len(existing) + 1
    meta = store_contract_pdf(user["tenant_id"], cid, kind, version, pdf_bytes)
    await db.contracts.update_one({"_id": cid}, {"$push": {"pdf_versions": meta}})
    await record_audit(action=f"contracts.pdf.{kind}", tenant_id=user["tenant_id"],
                        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
                        entity_type="contract", entity_id=cid,
                        after={"kind": kind, "version": version, "hash": meta["hash"],
                                "size_bytes": meta["size_bytes"]})
    return {"ok": True, **meta}


@router.get("/{cid}/pdf/download/{version}")
async def contract_pdf_download(cid: str, version: int,
                                  user: dict = Depends(require_permission("contracts.download"))):
    db = get_db()
    doc = await db.contracts.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Contratto non trovato")
    versions = doc.get("pdf_versions") or []
    match = next((v for v in versions if int(v.get("version") or 0) == int(version)), None)
    if not match:
        raise HTTPException(404, f"Versione PDF {version} non trovata")
    from app.services.storage import get_storage
    try:
        data = get_storage().get(match["storage_key"])
    except Exception as e:
        raise HTTPException(500, f"Storage error: {e}")
    return Response(
        content=data, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={match.get('filename')}"},
    )


@router.get("/{cid}/pdf/list")
async def contract_pdf_list(cid: str, user: dict = Depends(require_permission("contracts.view"))):
    db = get_db()
    doc = await db.contracts.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Contratto non trovato")
    versions = doc.get("pdf_versions") or []
    # Signed URLs se disponibili
    out = []
    for v in versions:
        item = {**v}
        try:
            url = get_signed_url(v["storage_key"], 900)
            if url:
                item["signed_url"] = url
        except Exception:
            pass
        out.append(item)
    return {"contract_id": cid, "versions": out}


# =====================================================================
# Signature providers info (per UI configurazione)
# =====================================================================
@router.get("/config/signature-providers")
async def signature_providers(user: dict = Depends(require_permission("contracts.view"))):
    """Elenco provider firma registrati (per pannello configurazione).
    Ritorna: nome, level (electronic_simple/advanced/qualified), configured, description."""
    return {"items": list_sign_providers()}
