"""USER SELF REGISTRATION + ROLE APPROVAL V1 (PO msg 790).

Principio: l'utente RICHIEDE un ruolo (requested_role); solo un Superadmin assegna tenant + ruolo effettivo.
Nessun tenant_id/role/permissions dal frontend è autoritativo. Riusa hashing/JWT/lockout/audit esistenti.
Flusso: REGISTER -> PENDING_EMAIL_VERIFICATION -> PENDING_APPROVAL -> APPROVED | REJECTED | SUSPENDED.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.config import settings
from app.db import get_db
from app.deps import get_client_ip, get_current_user
from app.permissions import PREDEFINED_ROLES
from app.security import hash_password, verify_password
from app.services.audit import record_audit
from app.services.email import send_email

router = APIRouter(tags=["registration"])

# Ruoli richiedibili pubblicamente: solo ruoli RBAC canonici, MAI super_admin / admin_azienda.
SELF_REGISTRABLE_ROLES = ["cliente", "commerciale", "tecnico_rilievo", "produzione", "magazzino", "posatore", "amministrazione", "viewer"]
FORBIDDEN_EFFECTIVE_ROLES = {"super_admin", "admin_azienda"}
STATUSES = ("PENDING_EMAIL_VERIFICATION", "PENDING_APPROVAL", "APPROVED", "REJECTED", "SUSPENDED")
VERIFY_TTL_HOURS = 48


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _public(r: dict) -> Dict[str, Any]:
    return {
        "id": r["_id"], "email": r["email"], "first_name": r["first_name"], "last_name": r["last_name"], "phone": r.get("phone"),
        "company_name": r.get("company_name"), "requested_role": r["requested_role"], "status": r["status"],
        "registered_at": r["registered_at"], "email_verified": bool(r.get("email_verified_at")), "email_verified_at": r.get("email_verified_at"),
        "approved_role": r.get("approved_role"), "approved_tenant_id": r.get("approved_tenant_id"), "approved_by": r.get("approved_by"),
        "approved_at": r.get("approved_at"), "rejected_by": r.get("rejected_by"), "rejected_at": r.get("rejected_at"),
        "rejection_reason_internal": r.get("rejection_reason_internal"), "created_user_id": r.get("created_user_id"),
        "created_user_kind": r.get("created_user_kind"), "linked_customer_id": r.get("linked_customer_id"),
        "status_history": r.get("status_history") or [],
    }


async def _set_status(db, req_id: str, new_status: str, by: Optional[str], extra: Optional[dict] = None, expect: Optional[List[str]] = None):
    """Transizione di stato atomica (filtro su stato atteso) + history immutabile."""
    q: dict = {"_id": req_id}
    if expect:
        q["status"] = {"$in": expect}
    upd = {"$set": {"status": new_status, "updated_at": _now(), **(extra or {})},
           "$push": {"status_history": {"to": new_status, "by": by, "at": _now()}}}
    doc = await db.registration_requests.find_one_and_update(q, upd, return_document=True)
    if not doc:
        raise HTTPException(409, {"code": "INVALID_STATE_TRANSITION", "message": "Stato richiesta non compatibile con l'operazione."})
    return doc


def _btn(href: str, label: str) -> str:
    return (f'<p style="margin:24px 0"><a href="{href}" style="background:#12a16b;color:#fff;padding:12px 22px;border-radius:4px;'
            f'text-decoration:none;font-weight:600;font-family:Roboto,Arial,sans-serif">{label}</a></p>')


def _wrap(title: str, body_html: str) -> str:
    return (f'<div style="font-family:Roboto,Arial,sans-serif;color:#1f2937;max-width:560px"><h2 style="margin:0 0 12px">{title}</h2>'
            f'{body_html}<p style="color:#6b7280;font-size:12px;margin-top:28px">Panorama Pilot · messaggio automatico</p></div>')


async def _send_verification_email(db, r: dict, token: str) -> str:
    """Invia (o reinvia) l'email di verifica; ritorna lo status del log (mai 'sent' finto)."""
    link = f"{settings.APP_BASE_URL.rstrip('/')}/verify-email?token={token}"
    html = _wrap("Verifica il tuo indirizzo email",
                 f"<p>Ciao {r['first_name']},</p><p>hai richiesto l'accesso a Panorama Pilot. Conferma il tuo indirizzo email per proseguire: "
                 f"dopo la verifica la richiesta sarà esaminata dall'amministratore.</p>{_btn(link, 'Verifica email')}"
                 f"<p style=\"font-size:12px;color:#6b7280\">Il link scade tra {VERIFY_TTL_HOURS} ore. Se non hai richiesto tu l'accesso, ignora questo messaggio.</p>")
    from app.services.email_service import enqueue_email
    try:
        res = await enqueue_email(to=r["email"], subject="Verifica il tuo indirizzo email | Panorama Pilot", template="registration_verify",
                                  html=html, text=f"Verifica il tuo indirizzo email (valido {VERIFY_TTL_HOURS} ore): {link}",
                                  idempotency_key=f"reg-verify:{r['_id']}:{_h(token)[:12]}", event_type="REGISTRATION_VERIFY_EMAIL")
        status = res.get("status") or "failed"
    except Exception:
        status = "failed"
    ok = status in ("sent", "test_intercepted")
    await db.registration_requests.update_one({"_id": r["_id"]}, {"$set": {
        "verification_email_status": "SENT" if ok else "EMAIL_SEND_FAILED", "verification_email_last_at": _now()},
        "$inc": {"verification_email_count": 1}})
    return status


async def _notify_superadmins_new_request(db, r: dict) -> None:
    """PENDING_APPROVAL -> notifica ai Superadmin attivi (dati admin-safe, nessun dato interno)."""
    link = f"{settings.APP_BASE_URL.rstrip('/')}/registration-requests"
    html = _wrap("Nuova richiesta di registrazione",
                 f"<p>Un nuovo utente ha verificato la propria email ed è in attesa di approvazione.</p>"
                 f"<ul><li><b>Nome:</b> {r['first_name']} {r['last_name']}</li><li><b>Ruolo richiesto:</b> {r['requested_role']}</li>"
                 f"<li><b>Azienda richiesta:</b> {r.get('company_name') or '—'}</li><li><b>Data richiesta:</b> {r['registered_at'][:16].replace('T', ' ')}</li></ul>"
                 f"{_btn(link, 'Gestisci richiesta')}")
    async for sa in db.users.find({"$or": [{"is_superadmin": True}, {"is_platform_owner": True}], "is_active": True, "deleted_at": None}, {"email": 1}):
        await send_email(to=sa["email"], subject="Nuova richiesta di registrazione | Panorama Pilot", template="registration_new_request_admin",
                         html=html, text=f"Nuova richiesta di registrazione: {r['first_name']} {r['last_name']} ({r['requested_role']}). Gestisci: {link}",
                         idempotency_key=f"reg-admin-notify:{r['_id']}:{sa['_id']}", event_type="SUPERADMIN_NEW_REGISTRATION")


def require_superadmin(user: dict = Depends(get_current_user)) -> dict:
    if not (user.get("is_superadmin") or user.get("is_platform_owner")):
        raise HTTPException(403, "Operazione riservata al Superadmin")
    return user


# --------------------------------------------------------------------------- PUBLIC
class RegisterBody(BaseModel):
    model_config = ConfigDict(extra="ignore")  # role / tenant_id / permissions inviati dal client vengono IGNORATI
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    phone: str = Field(min_length=5, max_length=40)
    password: str = Field(min_length=8, max_length=128)
    password_confirm: str
    requested_role: str
    company_name: Optional[str] = Field(default=None, max_length=160)


@router.get("/auth/register/roles")
async def register_roles():
    return {"items": [{"code": c, "name": PREDEFINED_ROLES[c]["name"], "description": PREDEFINED_ROLES[c]["description"]} for c in SELF_REGISTRABLE_ROLES]}


async def _email_taken(db, email: str) -> bool:
    if await db.users.find_one({"email": email, "deleted_at": None}):
        return True
    if await db.customer_portal_users.find_one({"email": email, "deleted_at": None}):
        return True
    return bool(await db.registration_requests.find_one({"email": email, "status": {"$ne": "REJECTED"}}))


@router.post("/auth/register", status_code=201)
async def register(body: RegisterBody, request: Request):
    db = get_db()
    email = body.email.lower().strip()
    if body.password != body.password_confirm:
        raise HTTPException(400, {"code": "PASSWORD_MISMATCH", "message": "Le password non coincidono."})
    if body.requested_role not in SELF_REGISTRABLE_ROLES:
        raise HTTPException(400, {"code": "ROLE_NOT_ALLOWED", "message": "Ruolo non richiedibile tramite registrazione."})
    if await _email_taken(db, email):
        raise HTTPException(409, {"code": "ACCOUNT_ALREADY_EXISTS", "message": "Esiste già un account con questa email. Accedi o recupera la password."})
    token = secrets.token_urlsafe(32)
    req_id = str(uuid4())
    doc = {
        "_id": req_id, "email": email, "first_name": body.first_name.strip(), "last_name": body.last_name.strip(),
        "phone": body.phone.strip(), "company_name": (body.company_name or "").strip() or None,
        "requested_role": body.requested_role, "password_hash": hash_password(body.password),
        "status": "PENDING_EMAIL_VERIFICATION", "registered_at": _now(), "updated_at": _now(),
        "verification_token_hash": _h(token), "verification_expires_at": (datetime.now(timezone.utc) + timedelta(hours=VERIFY_TTL_HOURS)).isoformat(),
        "email_verified_at": None, "registered_ip": get_client_ip(request),
        "status_history": [{"to": "PENDING_EMAIL_VERIFICATION", "by": None, "at": _now()}],
    }
    await db.registration_requests.insert_one(doc)
    email_status = await _send_verification_email(db, doc, token)
    await record_audit(action="auth.register.requested", tenant_id=None, user_id=None, user_email=email, ip=doc["registered_ip"],
                       user_agent=request.headers.get("user-agent"), meta={"request_id": req_id, "requested_role": body.requested_role})
    email_ok = email_status in ("sent", "test_intercepted")
    out = {"request_id": req_id, "status": "PENDING_EMAIL_VERIFICATION", "verification_email_status": "SENT" if email_ok else "EMAIL_SEND_FAILED",
           "message": "Registrazione ricevuta. Conferma la tua email: riceverai una comunicazione quando il tuo account sarà stato verificato e approvato."
           if email_ok else "Registrazione ricevuta, ma l'invio dell'email di verifica non è riuscito. Puoi richiedere un nuovo invio."}
    if settings.OTP_DEBUG_ENABLED:
        out["debug_verification_token"] = token
    return out


class VerifyBody(BaseModel):
    token: str = Field(min_length=20, max_length=200)


@router.post("/auth/verify-email")
async def verify_email(body: VerifyBody):
    db = get_db()
    r = await db.registration_requests.find_one({"verification_token_hash": _h(body.token)})
    if not r or r["status"] != "PENDING_EMAIL_VERIFICATION":
        raise HTTPException(400, {"code": "VERIFICATION_TOKEN_INVALID", "message": "Link di verifica non valido o già utilizzato."})
    if r["verification_expires_at"] < _now():
        raise HTTPException(400, {"code": "VERIFICATION_TOKEN_EXPIRED", "message": "Link di verifica scaduto. Registrati nuovamente."})
    await _set_status(db, r["_id"], "PENDING_APPROVAL", None,
                      {"email_verified_at": _now(), "verification_token_hash": None}, expect=["PENDING_EMAIL_VERIFICATION"])
    await record_audit(action="auth.register.email_verified", tenant_id=None, user_id=None, user_email=r["email"], meta={"request_id": r["_id"]})
    await _notify_superadmins_new_request(db, r)
    return {"request_id": r["_id"], "status": "PENDING_APPROVAL",
            "message": "Email verificata. Il tuo account è in attesa di approvazione da parte dell'amministratore."}


class ResendBody(BaseModel):
    request_id: str


RESEND_MIN_INTERVAL_S = 60
RESEND_MAX_PER_DAY = 5


@router.post("/auth/resend-verification")
async def resend_verification(body: ResendBody, request: Request):
    """Reinvio email di verifica: per request_id (nessuna enumerazione email), rate-limited, token precedente invalidato."""
    db = get_db()
    r = await db.registration_requests.find_one({"_id": body.request_id})
    if not r or r["status"] != "PENDING_EMAIL_VERIFICATION":
        # risposta neutra: non rivela stato/esistenza
        return {"request_id": body.request_id, "status": "ACCEPTED", "message": "Se la richiesta è in attesa di verifica, riceverai una nuova email."}
    last = r.get("verification_email_last_at")
    if last and (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() < RESEND_MIN_INTERVAL_S:
        raise HTTPException(429, {"code": "RESEND_TOO_SOON", "message": f"Attendi almeno {RESEND_MIN_INTERVAL_S} secondi prima di un nuovo invio."})
    if int(r.get("verification_email_count") or 0) >= RESEND_MAX_PER_DAY + 1:
        raise HTTPException(429, {"code": "RESEND_LIMIT_REACHED", "message": "Limite di reinvii raggiunto. Contatta l'amministratore."})
    token = secrets.token_urlsafe(32)
    await db.registration_requests.update_one({"_id": r["_id"]}, {"$set": {
        "verification_token_hash": _h(token), "verification_expires_at": (datetime.now(timezone.utc) + timedelta(hours=VERIFY_TTL_HOURS)).isoformat()}})
    status = await _send_verification_email(db, r, token)
    await record_audit(action="auth.register.verification_resent", tenant_id=None, user_id=None, user_email=r["email"], ip=get_client_ip(request),
                       meta={"request_id": r["_id"], "email_status": status})
    out = {"request_id": r["_id"], "status": "ACCEPTED", "verification_email_status": "SENT" if status in ("sent", "test_intercepted") else "EMAIL_SEND_FAILED",
           "message": "Se la richiesta è in attesa di verifica, riceverai una nuova email."}
    if settings.OTP_DEBUG_ENABLED:
        out["debug_verification_token"] = token
    return out


@router.get("/auth/registration/{request_id}")
async def registration_status(request_id: str):
    """Solo lo stato della propria richiesta (id non enumerabile). Nessun dato tenant."""
    r = await get_db().registration_requests.find_one({"_id": request_id})
    if not r:
        raise HTTPException(404, "Richiesta non trovata")
    return {"request_id": r["_id"], "status": r["status"], "requested_role": r["requested_role"], "registered_at": r["registered_at"],
            "email_verified": bool(r.get("email_verified_at"))}


async def pending_login_block(db, email: str, password: str) -> Optional[dict]:
    """Usato dal login: se le credenziali corrispondono a una richiesta non attiva, ritorna il codice stato (mai 'password errata')."""
    r = await db.registration_requests.find_one({"email": email}, sort=[("registered_at", -1)])
    if not r or not verify_password(password, r.get("password_hash") or ""):
        return None
    code = {"PENDING_EMAIL_VERIFICATION": "ACCOUNT_PENDING_EMAIL_VERIFICATION", "PENDING_APPROVAL": "ACCOUNT_PENDING_APPROVAL",
            "REJECTED": "ACCOUNT_NOT_APPROVED", "SUSPENDED": "ACCOUNT_SUSPENDED"}.get(r["status"])
    if not code:
        return None
    msg = {"ACCOUNT_PENDING_EMAIL_VERIFICATION": "Conferma prima il tuo indirizzo email.",
           "ACCOUNT_PENDING_APPROVAL": "Il tuo account è in attesa di approvazione da parte dell'amministratore.",
           "ACCOUNT_NOT_APPROVED": "La richiesta di registrazione non è stata approvata.",
           "ACCOUNT_SUSPENDED": "Account sospeso. Contatta l'amministratore."}[code]
    return {"code": code, "message": msg, "request_id": r["_id"]}


# --------------------------------------------------------------------------- SUPERADMIN
@router.get("/registration-requests")
async def list_requests(status: Optional[str] = None, requested_role: Optional[str] = None, tenant_id: Optional[str] = None,
                        date_from: Optional[str] = None, date_to: Optional[str] = None, limit: int = Query(200, le=500),
                        user: dict = Depends(require_superadmin)):
    db = get_db()
    q: dict = {}
    if status:
        q["status"] = {"$in": [s for s in status.split(",") if s in STATUSES]}
    if requested_role:
        q["requested_role"] = requested_role
    if tenant_id:
        q["approved_tenant_id"] = tenant_id
    if date_from or date_to:
        q["registered_at"] = {**({"$gte": date_from} if date_from else {}), **({"$lte": date_to} if date_to else {})}
    items = [_public(r) async for r in db.registration_requests.find(q).sort("registered_at", -1).limit(limit)]
    return {"items": items, "total": len(items)}


@router.get("/registration-requests/count")
async def count_pending(user: dict = Depends(require_superadmin)):
    db = get_db()
    return {"pending": await db.registration_requests.count_documents({"status": "PENDING_APPROVAL"}),
            "pending_email": await db.registration_requests.count_documents({"status": "PENDING_EMAIL_VERIFICATION"})}


@router.get("/registration-requests/options")
async def approval_options(user: dict = Depends(require_superadmin)):
    db = get_db()
    tenants = [{"id": c["_id"], "name": c.get("name")} async for c in db.companies.find({"deleted_at": None}, {"name": 1}).sort("name", 1)]
    roles = [{"code": c, "name": v["name"]} for c, v in PREDEFINED_ROLES.items() if c not in FORBIDDEN_EFFECTIVE_ROLES]
    return {"tenants": tenants, "roles": roles}


@router.get("/registration-requests/{req_id}")
async def get_request(req_id: str, user: dict = Depends(require_superadmin)):
    r = await get_db().registration_requests.find_one({"_id": req_id})
    if not r:
        raise HTTPException(404, "Richiesta non trovata")
    return _public(r)


@router.get("/registration-requests/{req_id}/customer-matches")
async def customer_matches(req_id: str, tenant_id: str, user: dict = Depends(require_superadmin)):
    """Match su email / telefono / CF / PIVA: propone, NON approva. Ambiguo -> CUSTOMER_LINK_REVIEW_REQUIRED."""
    db = get_db()
    r = await db.registration_requests.find_one({"_id": req_id})
    if not r:
        raise HTTPException(404, "Richiesta non trovata")
    phone_digits = "".join(ch for ch in (r.get("phone") or "") if ch.isdigit())[-9:]
    ors: List[dict] = [{"email": r["email"]}]
    if phone_digits:
        ors.append({"phone": {"$regex": phone_digits + "$"}})
    if r.get("company_name"):
        ors.append({"company_name": {"$regex": f"^{r['company_name']}$", "$options": "i"}})
    matches = []
    async for c in db.customers.find({"tenant_id": tenant_id, "deleted_at": None, "$or": ors}).limit(20):
        fields = []
        if (c.get("email") or "").lower() == r["email"]:
            fields.append("email")
        if phone_digits and "".join(ch for ch in (c.get("phone") or "") if ch.isdigit()).endswith(phone_digits):
            fields.append("phone")
        if r.get("company_name") and (c.get("company_name") or "").lower() == r["company_name"].lower():
            fields.append("company_name")
        matches.append({"customer_id": c["_id"], "name": f"{c.get('first_name') or ''} {c.get('last_name') or ''}".strip() or c.get("company_name"),
                        "company_name": c.get("company_name"), "email": c.get("email"), "phone": c.get("phone"),
                        "tax_code": c.get("tax_code"), "vat_number": c.get("vat_number"), "match_fields": fields})
    strong = [m for m in matches if "email" in m["match_fields"]]
    if len(strong) == 1:
        decision = "CUSTOMER_LINK_PROPOSED"
    elif matches:
        decision = "CUSTOMER_LINK_REVIEW_REQUIRED"
    else:
        decision = "NO_MATCH"
    return {"decision": decision, "proposed_customer_id": strong[0]["customer_id"] if len(strong) == 1 else None, "matches": matches}


class ApproveBody(BaseModel):
    tenant_id: str
    effective_role: str
    customer_id: Optional[str] = None


@router.post("/registration-requests/{req_id}/approve")
async def approve(req_id: str, body: ApproveBody, request: Request, user: dict = Depends(require_superadmin)):
    db = get_db()
    if body.effective_role in FORBIDDEN_EFFECTIVE_ROLES or body.effective_role not in PREDEFINED_ROLES:
        raise HTTPException(400, {"code": "ROLE_NOT_ALLOWED", "message": "Ruolo effettivo non assegnabile da questa procedura."})
    tenant = await db.companies.find_one({"_id": body.tenant_id, "deleted_at": None})
    if not tenant:
        raise HTTPException(400, {"code": "TENANT_NOT_FOUND", "message": "Tenant non valido."})
    r = await db.registration_requests.find_one({"_id": req_id})
    if not r:
        raise HTTPException(404, "Richiesta non trovata")
    if r["status"] != "PENDING_APPROVAL":
        raise HTTPException(409, {"code": "INVALID_STATE_TRANSITION", "message": f"Richiesta in stato {r['status']}: approvabile solo da PENDING_APPROVAL (email verificata)."})
    if await db.users.find_one({"email": r["email"], "deleted_at": None}) or await db.customer_portal_users.find_one({"email": r["email"], "deleted_at": None}):
        raise HTTPException(409, {"code": "ACCOUNT_ALREADY_EXISTS", "message": "Esiste già un account con questa email."})

    now = _now()
    if body.effective_role == "cliente":
        if not body.customer_id:
            raise HTTPException(400, {"code": "CUSTOMER_LINK_REQUIRED", "message": "Per il ruolo Cliente è obbligatorio collegare una scheda cliente del tenant."})
        cust = await db.customers.find_one({"_id": body.customer_id, "tenant_id": body.tenant_id, "deleted_at": None})
        if not cust:
            raise HTTPException(400, {"code": "CUSTOMER_NOT_FOUND", "message": "Scheda cliente non trovata nel tenant selezionato."})
        new_user = {"_id": str(uuid4()), "tenant_id": body.tenant_id, "customer_id": body.customer_id, "email": r["email"], "phone": r.get("phone"),
                    "first_name": r["first_name"], "last_name": r["last_name"], "fiscal_code": cust.get("tax_code"),
                    "password_hash": r["password_hash"], "status": "AUTHORIZED", "authorized_by": user["id"], "authorized_at": now,
                    "created_at": now, "deleted_at": None, "registration_request_id": req_id}
        kind, coll = "customer_portal", db.customer_portal_users
    else:
        role_doc = await db.roles.find_one({"tenant_id": body.tenant_id, "name": PREDEFINED_ROLES[body.effective_role]["name"], "deleted_at": None})
        if not role_doc:
            raise HTTPException(400, {"code": "ROLE_NOT_FOUND_IN_TENANT", "message": "Ruolo non disponibile nel tenant selezionato."})
        new_user = {"_id": str(uuid4()), "tenant_id": body.tenant_id, "email": r["email"], "password_hash": r["password_hash"],
                    "first_name": r["first_name"], "last_name": r["last_name"], "phone": r.get("phone"), "role_ids": [role_doc["_id"]],
                    "is_superadmin": False, "is_platform_owner": False, "is_active": True, "must_change_password": False,
                    "email_verified_at": r.get("email_verified_at"), "created_at": now, "updated_at": now, "deleted_at": None,
                    "registration_request_id": req_id, "locale": "it"}
        kind, coll = "backoffice", db.users

    # Atomico: PENDING_APPROVAL -> APPROVED (tenant + ruolo + utente insieme); se l'insert fallisce si ripristina.
    approved = await _set_status(db, req_id, "APPROVED", user["id"], {
        "approved_role": body.effective_role, "approved_tenant_id": body.tenant_id, "approved_by": user["id"], "approved_at": now,
        "created_user_id": new_user["_id"], "created_user_kind": kind, "linked_customer_id": body.customer_id,
    }, expect=["PENDING_APPROVAL"])
    try:
        await coll.insert_one(new_user)
    except Exception:
        await db.registration_requests.update_one({"_id": req_id}, {"$set": {"status": "PENDING_APPROVAL", "created_user_id": None, "approved_at": None}})
        raise HTTPException(500, "Creazione utente fallita: richiesta ripristinata in PENDING_APPROVAL")
    await record_audit(action="auth.register.approved", tenant_id=body.tenant_id, user_id=user["id"], user_email=user.get("email"),
                       ip=get_client_ip(request), meta={"request_id": req_id, "requested_role": r["requested_role"], "approved_role": body.effective_role,
                                                        "created_user_id": new_user["_id"], "kind": kind, "customer_id": body.customer_id})
    login_url = f"{settings.APP_BASE_URL.rstrip('/')}/{'customer-portal' if kind == 'customer_portal' else 'login'}"
    await send_email(to=r["email"], subject="Il tuo account Panorama Pilot è stato approvato", template="registration_approved",
                     html=_wrap("Il tuo account Panorama Pilot è stato approvato", f"<p>Ciao {r['first_name']},</p><p>l'amministratore ha approvato la tua richiesta di accesso.</p>{_btn(login_url, 'Accedi a Panorama Pilot')}"),
                     text=f"Il tuo account Panorama Pilot è stato approvato. Accedi: {login_url}", tenant_id=body.tenant_id,
                     idempotency_key=f"reg-approved:{req_id}", event_type="ACCOUNT_APPROVED")
    return _public(approved)


class RejectBody(BaseModel):
    rejection_reason_internal: Optional[str] = Field(default=None, max_length=500)


@router.post("/registration-requests/{req_id}/reject")
async def reject(req_id: str, body: RejectBody, request: Request, user: dict = Depends(require_superadmin)):
    db = get_db()
    r = await _set_status(db, req_id, "REJECTED", user["id"], {"rejected_by": user["id"], "rejected_at": _now(),
                          "rejection_reason_internal": body.rejection_reason_internal}, expect=["PENDING_EMAIL_VERIFICATION", "PENDING_APPROVAL"])
    await record_audit(action="auth.register.rejected", tenant_id=None, user_id=user["id"], user_email=user.get("email"), ip=get_client_ip(request),
                       meta={"request_id": req_id, "has_internal_reason": bool(body.rejection_reason_internal)})
    await send_email(to=r["email"], subject="Panorama Pilot — esito richiesta di registrazione", template="registration_rejected",
                     html=_wrap("Esito richiesta di accesso", "<p>La tua richiesta di accesso non è stata approvata. Per informazioni contatta l'amministratore.</p>"),
                     text="La tua richiesta di accesso a Panorama Pilot non è stata approvata.", idempotency_key=f"reg-rejected:{req_id}", event_type="ACCOUNT_REJECTED")
    return _public(r)


@router.post("/registration-requests/{req_id}/suspend")
async def suspend(req_id: str, request: Request, user: dict = Depends(require_superadmin)):
    db = get_db()
    r = await _set_status(db, req_id, "SUSPENDED", user["id"], {"suspended_by": user["id"], "suspended_at": _now()}, expect=["APPROVED"])
    if r.get("created_user_kind") == "customer_portal":
        await db.customer_portal_users.update_one({"_id": r["created_user_id"]}, {"$set": {"status": "SUSPENDED"}})
    else:
        await db.users.update_one({"_id": r["created_user_id"]}, {"$set": {"is_active": False}})
        await db.sessions.update_many({"user_id": r["created_user_id"], "revoked_at": None}, {"$set": {"revoked_at": _now()}})
    await send_email(to=r["email"], subject="Il tuo account Panorama Pilot è stato sospeso", template="registration_suspended",
                     html=_wrap("Account sospeso", "<p>Il tuo account Panorama Pilot è stato sospeso. Per informazioni contatta l'amministratore.</p>"),
                     text="Il tuo account Panorama Pilot è stato sospeso. Contatta l'amministratore.", idempotency_key=f"reg-suspended:{req_id}:{r.get('suspended_at')}",
                     event_type="ACCOUNT_SUSPENDED")
    await record_audit(action="auth.register.suspended", tenant_id=r.get("approved_tenant_id"), user_id=user["id"], user_email=user.get("email"),
                       ip=get_client_ip(request), meta={"request_id": req_id, "created_user_id": r.get("created_user_id")})
    return _public(r)


@router.post("/registration-requests/{req_id}/reactivate")
async def reactivate(req_id: str, request: Request, user: dict = Depends(require_superadmin)):
    db = get_db()
    r = await _set_status(db, req_id, "APPROVED", user["id"], {"reactivated_by": user["id"], "reactivated_at": _now()}, expect=["SUSPENDED"])
    if r.get("created_user_kind") == "customer_portal":
        await db.customer_portal_users.update_one({"_id": r["created_user_id"]}, {"$set": {"status": "AUTHORIZED"}})
    else:
        await db.users.update_one({"_id": r["created_user_id"]}, {"$set": {"is_active": True}})
    await record_audit(action="auth.register.reactivated", tenant_id=r.get("approved_tenant_id"), user_id=user["id"], user_email=user.get("email"),
                       ip=get_client_ip(request), meta={"request_id": req_id})
    return _public(r)
