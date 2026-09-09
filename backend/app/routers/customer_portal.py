"""CUSTOMER PORTAL CORE V1 (PO msg 406/627) — auth separata (aud=customer_portal) + isolation server-side.

Riuso: security.hash/verify, quotes/contracts/quote_pdfs/service_tickets, QuoteLine.visual_spec.
Regole: ogni query filtra {tenant_id, customer_id}; ID sconosciuti -> 404; solo dati customer-safe.
"""
from __future__ import annotations
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

from app.config import settings
from app.db import get_db
from app.deps import require_permission
from app.security import hash_password, verify_password

router = APIRouter(prefix="/customer-portal", tags=["Customer Portal"])
admin_router = APIRouter(prefix="/admin/customer-portal", tags=["Customer Portal Admin"])

AUD = "customer_portal"
MAX_ATTEMPTS, LOCK_MINUTES = 5, 15
CUSTOMER_STATUS_LABELS = {
    "accepted": ("CONTRATTO_ACCETTATO", "Preventivo accettato — in attesa di avvio ordine"),
    "converted": ("ORDINE_CONFERMATO", "Ordine confermato"),
}
# Chiavi che NON devono mai uscire verso il cliente
_LEAK_KEYS = {"internal_cost", "margin", "margin_abs", "margin_pct", "cost_price", "technical_snapshot", "financial_snapshot",
              "pricing_snapshot", "commercial_snapshot", "simple_snapshot", "supply_cost", "commission", "commission_rate",
              "notes_internal", "internal_reference_price", "pre_commission_margin", "standard_services_internal_cost_total",
              "position_internal_cost_total", "automatic_services", "manual_extra_services", "previous_snapshots"}


def _now():
    return datetime.now(timezone.utc)


def _norm_email(e: str) -> str:
    return (e or "").strip().lower()


def _public_user(u: dict) -> dict:
    return {"id": u["_id"], "email": u["email"], "first_name": u.get("first_name"), "last_name": u.get("last_name"),
            "status": u.get("status"), "customer_id": u.get("customer_id"), "fiscal_code": u.get("fiscal_code"),
            "created_at": u.get("created_at"), "last_login_at": u.get("last_login_at")}


def _token(user: dict, ttl_minutes: int = 60) -> str:
    payload = {"sub": user["_id"], "tenant_id": user["tenant_id"], "customer_id": user.get("customer_id"), "aud": AUD,
               "type": "access", "jti": secrets.token_urlsafe(12), "iat": _now(), "exp": _now() + timedelta(minutes=ttl_minutes)}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


async def get_current_customer(request: Request) -> dict:
    token = request.cookies.get("cp_access_token")
    auth = request.headers.get("Authorization", "")
    if not token and auth.lower().startswith("bearer "):
        token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Non autenticato")
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM], audience=AUD)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token scaduto")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token non valido")  # include token dipendenti (aud mancante)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Tipo di token non valido")
    u = await get_db().customer_portal_users.find_one({"_id": payload["sub"], "deleted_at": None})
    if not u or u.get("status") != "AUTHORIZED" or not u.get("customer_id"):
        raise HTTPException(status_code=403, detail="Account cliente non autorizzato")
    return u


# --------------------------------------------------------------------------- AUTH
class RegisterBody(BaseModel):
    tenant_id: str
    email: EmailStr
    password: str = Field(min_length=8)
    first_name: str
    last_name: str
    phone: Optional[str] = None
    fiscal_code: Optional[str] = None


class LoginBody(BaseModel):
    email: EmailStr
    password: str


@router.post("/auth/register", status_code=201)
async def cp_register(body: RegisterBody):
    db = get_db()
    email = _norm_email(body.email)
    if await db.customer_portal_users.find_one({"tenant_id": body.tenant_id, "email": email, "deleted_at": None}):
        raise HTTPException(status_code=409, detail="Email già registrata")
    doc = {"_id": str(uuid4()), "tenant_id": body.tenant_id, "customer_id": None, "email": email, "phone": body.phone,
           "first_name": body.first_name.strip(), "last_name": body.last_name.strip(),
           "fiscal_code": (body.fiscal_code or "").strip().upper() or None, "password_hash": hash_password(body.password),
           "status": "PENDING_AUTHORIZATION", "created_at": _now().isoformat(), "deleted_at": None}
    await db.customer_portal_users.insert_one(doc)
    return {"status": "PENDING_AUTHORIZATION", "message": "Registrazione ricevuta: l'accesso sarà attivato dopo la verifica da parte dell'azienda."}


@router.post("/auth/login")
async def cp_login(body: LoginBody, request: Request, response: Response):
    db = get_db()
    email = _norm_email(body.email)
    ident = f"cp:acct:{email}"
    att = await db.login_attempts.find_one({"identifier": ident})
    if att and att.get("count", 0) >= MAX_ATTEMPTS and att.get("locked_until") and att["locked_until"] > _now().isoformat():
        raise HTTPException(status_code=429, detail="Troppi tentativi. Riprova tra 15 minuti.")
    u = await db.customer_portal_users.find_one({"email": email, "deleted_at": None})
    if not u or not verify_password(body.password, u.get("password_hash") or ""):
        count = (att or {}).get("count", 0) + 1
        await db.login_attempts.update_one({"identifier": ident}, {"$set": {"count": count, "locked_until": (_now() + timedelta(minutes=LOCK_MINUTES)).isoformat() if count >= MAX_ATTEMPTS else None}}, upsert=True)
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    if u.get("status") != "AUTHORIZED" or not u.get("customer_id"):
        raise HTTPException(status_code=403, detail={"code": u.get("status"), "message": "Account in attesa di autorizzazione da parte dell'azienda."})
    await db.login_attempts.delete_one({"identifier": ident})
    await db.customer_portal_users.update_one({"_id": u["_id"]}, {"$set": {"last_login_at": _now().isoformat()}})
    tok = _token(u)
    response.set_cookie("cp_access_token", tok, httponly=True, secure=True, samesite="none", max_age=3600, path="/")
    return {"access_token": tok, "token_type": "bearer", "user": _public_user(u)}


@router.post("/auth/logout")
async def cp_logout(response: Response):
    response.delete_cookie("cp_access_token", path="/")
    return {"ok": True}


@router.get("/auth/me")
async def cp_me(u: dict = Depends(get_current_customer)):
    return _public_user(u)


@router.post("/auth/forgot")
async def cp_forgot(body: Dict[str, str]):
    db = get_db()
    u = await db.customer_portal_users.find_one({"email": _norm_email(body.get("email", "")), "deleted_at": None})
    if u:
        tok = secrets.token_urlsafe(32)
        await db.password_reset_tokens.insert_one({"_id": str(uuid4()), "token": tok, "user_id": u["_id"], "scope": AUD, "used": False,
                                                   "expires_at": _now() + timedelta(hours=1)})
        import logging
        logging.getLogger(__name__).info(f"[customer-portal] reset link token for {u['email']}: {tok}")
    return {"ok": True}


@router.post("/auth/reset")
async def cp_reset(body: Dict[str, str]):
    db = get_db()
    t = await db.password_reset_tokens.find_one({"token": body.get("token"), "scope": AUD, "used": False})
    if not t or t["expires_at"] < _now():
        raise HTTPException(status_code=400, detail="Token non valido o scaduto")
    if len(body.get("password") or "") < 8:
        raise HTTPException(status_code=400, detail="Password troppo corta (min 8)")
    await db.customer_portal_users.update_one({"_id": t["user_id"]}, {"$set": {"password_hash": hash_password(body["password"])}})
    await db.password_reset_tokens.update_one({"_id": t["_id"]}, {"$set": {"used": True}})
    return {"ok": True}


# --------------------------------------------------------------------------- ADMIN (dipendenti)
class AdminCreateBody(BaseModel):
    customer_id: str
    email: EmailStr
    password: str = Field(min_length=8)
    first_name: str = ""
    last_name: str = ""


@admin_router.get("/users")
async def admin_list(user: dict = Depends(require_permission("customers.view"))):
    docs = await get_db().customer_portal_users.find({"tenant_id": user["tenant_id"], "deleted_at": None}).sort("created_at", -1).to_list(500)
    return {"items": [_public_user(d) for d in docs]}


@admin_router.post("/users", status_code=201)
async def admin_create(body: AdminCreateBody, user: dict = Depends(require_permission("customers.edit"))):
    """Crea e autorizza direttamente un accesso cliente collegato a un customer del tenant (matching manuale, mai automatico)."""
    db = get_db()
    if not await db.customers.find_one({"_id": body.customer_id, "tenant_id": user["tenant_id"]}):
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    email = _norm_email(body.email)
    if await db.customer_portal_users.find_one({"tenant_id": user["tenant_id"], "email": email, "deleted_at": None}):
        raise HTTPException(status_code=409, detail="Email già registrata")
    doc = {"_id": str(uuid4()), "tenant_id": user["tenant_id"], "customer_id": body.customer_id, "email": email,
           "first_name": body.first_name, "last_name": body.last_name, "password_hash": hash_password(body.password),
           "status": "AUTHORIZED", "invited_by": user["id"], "created_at": _now().isoformat(), "deleted_at": None}
    await db.customer_portal_users.insert_one(doc)
    return _public_user(doc)


@admin_router.post("/users/{uid}/authorize")
async def admin_authorize(uid: str, body: Dict[str, str], user: dict = Depends(require_permission("customers.edit"))):
    db = get_db()
    if not await db.customers.find_one({"_id": body.get("customer_id"), "tenant_id": user["tenant_id"]}):
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    r = await db.customer_portal_users.update_one({"_id": uid, "tenant_id": user["tenant_id"]},
                                                  {"$set": {"customer_id": body["customer_id"], "status": "AUTHORIZED", "authorized_by": user["id"], "authorized_at": _now().isoformat()}})
    if not r.matched_count:
        raise HTTPException(status_code=404, detail="Utente portale non trovato")
    return {"ok": True}


@admin_router.post("/users/{uid}/suspend")
async def admin_suspend(uid: str, user: dict = Depends(require_permission("customers.edit"))):
    r = await get_db().customer_portal_users.update_one({"_id": uid, "tenant_id": user["tenant_id"]}, {"$set": {"status": "SUSPENDED"}})
    if not r.matched_count:
        raise HTTPException(status_code=404, detail="Utente portale non trovato")
    return {"ok": True}


# --------------------------------------------------------------------------- CUSTOMER DATA (read-only)
def _safe_line(l: dict) -> dict:
    vs = l.get("visual_spec") or {}
    spec = vs.get("spec") or {}
    return {"id": l.get("id"), "description": l.get("description"), "quantity": l.get("quantity"), "width_mm": l.get("width_mm"),
            "height_mm": l.get("height_mm"), "opening_id": l.get("opening_id"), "category": l.get("category"),
            "unit_price_final": l.get("unit_price_final"), "subtotal_line": l.get("subtotal_line"),
            "visual_spec": {"spec": spec, "is_bicolor": vs.get("is_bicolor"), "svg_interior": vs.get("svg_interior"), "svg_exterior": vs.get("svg_exterior")} if vs.get("svg_exterior") else None}


def _timeline(q: dict, contract: Optional[dict], survey: Optional[dict]) -> List[dict]:
    steps = [{"key": "CONTRATTO", "label": "Preventivo accettato / contratto", "done": True, "at": q.get("accepted_at") or (contract or {}).get("signed_at")}]
    steps.append({"key": "ACCONTO", "label": "Acconto", "done": bool(q.get("deposit_paid_at")), "at": q.get("deposit_paid_at")})
    if survey is not None:
        steps.append({"key": "RILIEVO", "label": "Rilievo tecnico", "done": survey.get("survey_status") == "completed", "at": survey.get("scheduled_at")})
    steps.append({"key": "ORDINE", "label": "Ordine confermato", "done": q.get("quote_status") == "converted", "at": q.get("converted_at")})
    steps.append({"key": "PRODUZIONE", "label": "Produzione", "done": False, "at": None})
    steps.append({"key": "MERCE_PRONTA", "label": "Merce pronta", "done": False, "at": None})
    if q.get("installation_mode") == "SUPPLY_AND_INSTALLATION":
        steps.append({"key": "MONTAGGIO", "label": "Montaggio", "done": False, "at": None})
    if q.get("enea_practice_code"):
        steps.append({"key": "ENEA", "label": "Pratica ENEA", "done": False, "at": None})
    return steps


async def _job_view(db, u: dict, q: dict, full: bool) -> dict:
    contract = await db.contracts.find_one({"quote_id": q["_id"], "tenant_id": u["tenant_id"], "deleted_at": None})
    survey = await db.surveys.find_one({"quote_id": q["_id"], "tenant_id": u["tenant_id"], "deleted_at": None})
    status_code, status_label = CUSTOMER_STATUS_LABELS.get(q.get("quote_status"), ("IN_CORSO", "In corso"))
    site = q.get("site_address") or {}
    out = {"id": q["_id"], "number": q.get("number"), "title": q.get("title"), "contract_number": (contract or {}).get("number"),
           "quote_status": q.get("quote_status"), "customer_status": status_code, "customer_status_label": status_label,
           "total": q.get("total"), "created_at": q.get("created_at"), "accepted_at": q.get("accepted_at"),
           "site": {k: site.get(k) for k in ("street", "city", "zip_code", "province")} if site else None,
           "installation_mode": q.get("installation_mode"), "enea_practice_code": q.get("enea_practice_code"),
           "payment_terms_label": q.get("payment_terms_label"), "lines_count": len(q.get("lines") or [])}
    if full:
        out["openings"] = [{"id": o.get("id"), "code": o.get("code"), "room": o.get("room"), "description": o.get("description")} for o in q.get("openings") or []]
        out["lines"] = [_safe_line(l) for l in q.get("lines") or [] if not l.get("enea_practice")]
        out["timeline"] = _timeline(q, contract, survey)
        out["payment_schedule"] = q.get("payment_schedule") or []
    return out


def _job_query(u: dict) -> dict:
    return {"tenant_id": u["tenant_id"], "customer_id": u["customer_id"], "deleted_at": None,
            "quote_status": {"$in": ["accepted", "converted"]}}


@router.get("/jobs")
async def cp_jobs(u: dict = Depends(get_current_customer)):
    db = get_db()
    docs = await db.quotes.find(_job_query(u)).sort("created_at", -1).to_list(200)
    return {"items": [await _job_view(db, u, q, False) for q in docs]}


@router.get("/jobs/{jid}")
async def cp_job(jid: str, u: dict = Depends(get_current_customer)):
    db = get_db()
    q = await db.quotes.find_one({"_id": jid, **_job_query(u)})
    if not q:
        raise HTTPException(status_code=404, detail="Commessa non trovata")
    return await _job_view(db, u, q, True)


@router.get("/documents")
async def cp_documents(job_id: Optional[str] = None, u: dict = Depends(get_current_customer)):
    db = get_db()
    jq = _job_query(u)
    if job_id:
        jq["_id"] = job_id
    job_ids = [q["_id"] async for q in db.quotes.find(jq, {"_id": 1})]
    items = []
    async for d in db.quote_pdfs.find({"tenant_id": u["tenant_id"], "quote_id": {"$in": job_ids}, "kind": "definitive", "invalidated_at": None}).sort("generated_at", -1):
        items.append({"id": d["_id"], "job_id": d["quote_id"], "category": "PREVENTIVO", "filename": d.get("filename"), "generated_at": d.get("generated_at"), "size_bytes": d.get("size_bytes")})
    return {"items": items}


@router.get("/documents/{pid}/download")
async def cp_document_download(pid: str, u: dict = Depends(get_current_customer)):
    db = get_db()
    d = await db.quote_pdfs.find_one({"_id": pid, "tenant_id": u["tenant_id"], "kind": "definitive"})
    if not d or not await db.quotes.find_one({"_id": d.get("quote_id"), **_job_query(u)}):
        raise HTTPException(status_code=404, detail="Documento non trovato")
    from app.routers.pdf_router import _fetch_pdf_bytes
    pdf = await _fetch_pdf_bytes(d)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{d.get("filename", "preventivo.pdf")}"', "Cache-Control": "private, no-store"})


class TicketBody(BaseModel):
    job_id: Optional[str] = None
    subject: str = Field(min_length=3)
    description: str = Field(min_length=3)


@router.get("/tickets")
async def cp_tickets(u: dict = Depends(get_current_customer)):
    docs = await get_db().service_tickets.find({"tenant_id": u["tenant_id"], "customer_id": u["customer_id"], "deleted_at": None}).sort("created_at", -1).to_list(200)
    return {"items": [{"id": t["_id"], "number": t.get("number"), "subject": t.get("subject"), "description": t.get("description"),
                       "ticket_status": t.get("ticket_status"), "created_at": t.get("created_at"), "scheduled_at": t.get("scheduled_at")} for t in docs]}


@router.post("/tickets", status_code=201)
async def cp_ticket_create(body: TicketBody, u: dict = Depends(get_current_customer)):
    db = get_db()
    if body.job_id and not await db.quotes.find_one({"_id": body.job_id, **_job_query(u)}):
        raise HTTPException(status_code=404, detail="Commessa non trovata")
    doc = {"_id": str(uuid4()), "tenant_id": u["tenant_id"], "customer_id": u["customer_id"], "quote_id": body.job_id, "subject": body.subject,
           "description": body.description, "priority": "normal", "ticket_status": "RICEVUTO", "source": "CUSTOMER_PORTAL",
           "created_by": f"customer:{u['_id']}", "created_at": _now().isoformat(), "updated_at": _now().isoformat(), "deleted_at": None, "version": 1}
    await db.service_tickets.insert_one(doc)
    return {"id": doc["_id"], "ticket_status": "RICEVUTO"}
