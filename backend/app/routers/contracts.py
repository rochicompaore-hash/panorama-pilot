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
    quote = await db.quotes.find_one({
        "_id": body.quote_id, "tenant_id": user["tenant_id"], "deleted_at": None,
    })
    if not quote:
        raise HTTPException(404, "Preventivo non trovato")
    if quote.get("status") not in ("sent", "accepted", "won", "active", "approved"):
        raise HTTPException(400, f"Preventivo in stato {quote.get('status')}: deve essere sent/accepted/active")

    # Verifica: contratto già esistente per questo quote?
    existing = await db.contracts.find_one({
        "tenant_id": user["tenant_id"], "quote_id": body.quote_id,
        "contract_status": {"$nin": ["cancelled", "superseded", "rejected"]},
        "deleted_at": None,
    })
    if existing:
        raise HTTPException(400, f"Contratto già esistente per questo preventivo (id: {existing['_id']})")

    # Assembla snapshot
    company = await db.companies.find_one({"tenant_id": user["tenant_id"], "deleted_at": None}) or {}
    customer = None
    if quote.get("customer_id"):
        customer = await db.customers.find_one({"_id": quote["customer_id"], "tenant_id": user["tenant_id"]})

    # Environments + openings + products
    environments = await db.quote_environments.find({
        "tenant_id": user["tenant_id"], "quote_id": body.quote_id, "deleted_at": None,
    }).to_list(500)
    openings = await db.quote_openings.find({
        "tenant_id": user["tenant_id"], "quote_id": body.quote_id, "deleted_at": None,
    }).to_list(500)
    opening_products = await db.opening_products.find({
        "tenant_id": user["tenant_id"], "quote_id": body.quote_id, "deleted_at": None,
    }).to_list(2000)
    clauses = quote.get("clauses") or []

    # Sequence
    seq_doc = await db.sequences.find_one_and_update(
        {"tenant_id": user["tenant_id"], "type": "contract"},
        {"$inc": {"current": 1}, "$setOnInsert": {
            "tenant_id": user["tenant_id"], "type": "contract",
            "prefix": "CT-", "padding": 5,
        }},
        upsert=True, return_document=True,
    )
    n = seq_doc.get("current", 1)
    year = datetime.now(timezone.utc).year
    number = f"CT-{year}-{str(n).zfill(seq_doc.get('padding', 5))}"

    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quote_id": body.quote_id,
        "quote_number": quote.get("number"),
        "quote_revision": quote.get("revision", 0),
        "quote_totals": {
            "subtotal": quote.get("subtotal"), "discount": quote.get("discount"),
            "tax": quote.get("tax"), "total": quote.get("total"),
            "materials_cost": quote.get("materials_cost"),
            "margin": quote.get("margin"),
        },
        "environments": [from_mongo(e) for e in environments],
        "openings": [from_mongo(o) for o in openings],
        "products": [from_mongo(p) for p in opening_products],
        "company": {
            "name": company.get("name"), "vat": company.get("vat"),
            "address": company.get("address"), "email": company.get("email"),
            "phone": company.get("phone"), "logo_url": company.get("logo_url"),
        },
        "customer": from_mongo(customer) if customer else {},
        "clauses": clauses,
        "payment_terms": body.payment_terms,
    }
    snap_hash = hashlib.sha256(
        f"{body.quote_id}|{number}|{quote.get('total')}|{len(opening_products)}".encode()
    ).hexdigest()
    snapshot["snapshot_hash"] = snap_hash

    now = datetime.now(timezone.utc)
    contract_id = new_id()
    doc = {
        "_id": contract_id,
        "tenant_id": user["tenant_id"],
        "number": number, "number_int": n,
        "quote_id": body.quote_id,
        "quote_revision": quote.get("revision", 0),
        "customer_id": quote.get("customer_id"),
        "quote_snapshot": snapshot,
        "snapshot_hash": snap_hash,
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
    await record_audit(
        action="contracts.generate", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="contract", entity_id=contract_id,
        after={"quote_id": body.quote_id, "number": number, "snapshot_hash": snap_hash},
    )
    await record_activity(
        tenant_id=user["tenant_id"], type="contract_generated",
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
    # NB: invio email è mocked (dipende da servizio email) — in test l'endpoint public/firma è raggiungibile via token
    return {"ok": True, "signing_token": token, "expires_at": expires_at.isoformat(),
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
    tk = await db.contract_signing_tokens.find_one({"_id": token, "consumed": False})
    if not tk:
        raise HTTPException(404, "Token non valido o già consumato")
    if tk.get("expires_at"):
        exp = tk["expires_at"]
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(410, "Token scaduto")
    if not body.accept_terms:
        raise HTTPException(400, "Accettazione condizioni obbligatoria")
    if body.otp_code:
        # OTP reale via services.otp — request_id obbligatorio in prod, fallback dev accetta 123456 solo con OTP_DEBUG_ENABLED
        req_id = body.otp_request_id
        otp_ok = False
        if req_id:
            ok, reason, _ = await otp_verify(request_id=req_id, code=body.otp_code)
            otp_ok = ok
            if not ok:
                raise HTTPException(400, f"OTP non valido: {reason}")
        else:
            # Fallback dev only
            from app.config import is_dev_or_test
            if is_dev_or_test() and body.otp_code == "123456":
                otp_ok = True
            if not otp_ok:
                raise HTTPException(400, "OTP request_id mancante (necessario in produzione)")
    doc = await db.contracts.find_one({
        "_id": tk["contract_id"], "tenant_id": tk["tenant_id"], "deleted_at": None,
    })
    if not doc:
        raise HTTPException(404, "Contratto non trovato")
    if doc.get("contract_status") == "signed":
        raise HTTPException(400, "Contratto già firmato")
    now = datetime.now(timezone.utc)
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    payload = f"{doc['_id']}|{body.signer_name}|{ip}|{ua}|{now.isoformat()}|{doc.get('number')}|{doc.get('snapshot_hash')}"
    signature_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    await db.contracts.update_one({"_id": doc["_id"]}, {"$set": {
        "contract_status": "signed",
        "signed_at": now,
        "signed_by_name": body.signer_name,
        "signed_by_email": tk.get("to_email"),
        "signed_ip": ip, "signed_ua": ua,
        "signature_data_url": body.signature_data_url,
        "signature_hash": signature_hash,
        "signature_type": "electronic_simple_otp" if body.otp_code else "electronic_simple",
        "updated_at": now,
    }, "$push": {"state_history": {
        "state": "signed", "at": now.isoformat(),
        "by_name": body.signer_name, "by_email": tk.get("to_email"),
        "by_ip": ip, "signature_hash": signature_hash,
    }}})
    await db.contract_signing_tokens.update_one({"_id": token}, {"$set": {
        "consumed": True, "consumed_at": now,
    }})
    await record_audit(action="contracts.sign.public", tenant_id=tk["tenant_id"],
                        user_id=None, user_email=tk.get("to_email"), ip=ip,
                        entity_type="contract", entity_id=doc["_id"],
                        after={"signer": body.signer_name, "hash": signature_hash,
                                "otp": bool(body.otp_code)})
    # Hook workflow → create Survey
    try:
        from app.services.workflow_engine import ensure_survey_from_contract
        updated = await db.contracts.find_one({"_id": doc["_id"]})
        await ensure_survey_from_contract(
            tenant_id=tk["tenant_id"], contract=updated, actor_id=None,
        )
    except Exception:
        pass
    return {"ok": True, "signature_hash": signature_hash,
             "signature_type": "electronic_simple_otp" if body.otp_code else "electronic_simple"}


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
