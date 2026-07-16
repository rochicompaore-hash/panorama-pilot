"""M3.3.3 + M3.3.4 — Public quote portal.

Endpoints
=========
Admin (authenticated):
    POST   /quotes/{qid}/public-links
    GET    /quotes/{qid}/public-links
    POST   /quotes/{qid}/public-links/{tid}/revoke
    POST   /quotes/{qid}/public-links/regenerate
    GET    /quotes/{qid}/public-access-logs
    GET    /quotes/{qid}/customer-requests               (M3.3.4)
    POST   /customer-requests/{rid}/take                 (M3.3.4)
    POST   /customer-requests/{rid}/close                (M3.3.4)
    POST   /quotes/{qid}/reopen                          (M3.3.4)

Public (unauthenticated):
    GET    /public/quotes/{token}                        (view metadata)
    GET    /public/quotes/{token}/pdf                    (download original PDF)
    GET    /public/quotes/{token}/signed-pdf             (download signed PDF)  (M3.3.4)
    POST   /public/quotes/{token}/request-otp            (M3.3.4)
    POST   /public/quotes/{token}/verify-otp             (M3.3.4)
    POST   /public/quotes/{token}/sign                   (M3.3.4)
    POST   /public/quotes/{token}/request-changes        (M3.3.4)
    POST   /public/quotes/{token}/reject                 (M3.3.4)
"""
from __future__ import annotations
import base64
import hashlib
import io
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header
from app.config import settings, is_dev_or_test, is_prod_like
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models import new_id
from app.models_public import (
    QuotePublicToken, PublicLinkCreate, PublicLinkRevoke, PublicAccessLog, PublicQuoteResponse,
)
from app.models_signature import (
    PublicOtpRequestBody, PublicOtpVerifyBody, PublicSignatureSubmit,
    PublicRequestChangesBody, PublicRejectBody, QuoteSignature, CustomerRequest,
    CustomerRequestTake, CustomerRequestClose,
)
from app.mongo_utils import to_mongo, from_mongo
from app.services.audit import record_audit
from app.services.timeline import record_activity
from app.services.rate_limiter import (
    get_limiter, hkey, limiter_ready_for_sensitive, RateLimiterProvider,
)
from app.services import otp as otp_svc
from app.services import signature as sig_svc
from app.services import object_storage
from app.routers.pdf_router import _fetch_pdf_bytes

admin_router = APIRouter(tags=["public-links"])
public_router = APIRouter(prefix="/public", tags=["public-portal"])


# ==========================================================================
# Utilities
# ==========================================================================
def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _hash_ip(ip: Optional[str]) -> Optional[str]:
    if not ip: return None
    return hashlib.sha256(f"iph:{ip}".encode()).hexdigest()[:16]


def _generate_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, _hash_token(raw)


def _client_ip(request: Request) -> Optional[str]:
    try:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        return request.client.host if request.client else None
    except Exception:
        return None


def _security_headers() -> dict:
    return {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "X-Robots-Tag": "noindex, nofollow, noarchive, nosnippet",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "SAMEORIGIN",
    }


async def _write_access_log(*, db, tenant_id: Optional[str], token_id: Optional[str], quote_id: Optional[str],
                             quote_revision: Optional[str], event: str, result: str = "ok",
                             reason: Optional[str] = None, ip_hash: Optional[str] = None,
                             user_agent: Optional[str] = None):
    await db.public_access_log.insert_one({
        "_id": new_id(),
        "tenant_id": tenant_id,
        "token_id": token_id,
        "quote_id": quote_id,
        "quote_revision": quote_revision,
        "event": event, "result": result, "reason": reason,
        "ip_hash": ip_hash, "user_agent": user_agent,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


# ==========================================================================
# Admin: link CRUD
# ==========================================================================
@admin_router.get("/quotes/{qid}/public-links")
async def list_links(qid: str, user: dict = Depends(require_permission("quotes.public_link.view"))):
    db = get_db()
    docs = await db.quote_public_tokens.find(
        {"quote_id": qid, "tenant_id": user["tenant_id"]},
        {"metadata.raw_token_once": 0},
    ).sort("created_at", -1).to_list(50)
    items = []
    for d in docs:
        m = from_mongo(d); m.pop("token_hash", None); items.append(m)
    return {"items": items}


@admin_router.post("/quotes/{qid}/public-links")
async def create_link(qid: str, body: PublicLinkCreate, request: Request,
                      user: dict = Depends(require_permission("quotes.public_link.create"))):
    db = get_db()
    quote = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not quote: raise HTTPException(status_code=404, detail="Preventivo non trovato")
    pdf = await db.quote_pdfs.find_one({
        "quote_id": qid, "tenant_id": user["tenant_id"],
        "kind": "definitive", "invalidated_at": None,
    }, sort=[("generated_at", -1)])
    if not pdf: raise HTTPException(status_code=400, detail="Nessun PDF definitivo disponibile. Emetti prima il PDF.")
    if quote.get("quote_status") in ("cancelled", "rejected"):
        raise HTTPException(status_code=400, detail="Preventivo annullato: link pubblico non consentito")
    if not quote.get("is_current", True):
        raise HTTPException(status_code=400, detail="Revisione superata: creare link sulla revisione corrente")

    existing = await db.quote_public_tokens.find_one({
        "tenant_id": user["tenant_id"], "quote_id": qid,
        "quote_pdf_id": pdf["_id"], "snapshot_hash": pdf["snapshot_hash"],
        "status": "active",
    })
    if existing:
        exp = existing.get("expires_at")
        if exp and datetime.fromisoformat(exp.replace("Z", "+00:00")) > datetime.now(timezone.utc):
            return {
                "id": str(existing["_id"]), "quote_id": qid, "status": "active",
                "expires_at": existing.get("expires_at"),
                "idempotent_hit": True, "raw_token": None, "portal_url": None,
                "message": "Token attivo già esistente. Usa 'Rigenera' per ottenerne uno nuovo.",
            }

    now = datetime.now(timezone.utc)
    if body.expires_at: expires_at = body.expires_at
    else:
        days = body.validity_days if body.validity_days is not None else 30
        expires_at = now + timedelta(days=days)

    raw, h = _generate_token()
    tok = QuotePublicToken(
        id=new_id(), tenant_id=user["tenant_id"],
        quote_id=qid, quote_number=quote.get("number"),
        quote_revision=quote.get("revision_label") or f"R{int(quote.get('revision',0)):02d}",
        quote_pdf_id=pdf["_id"], snapshot_hash=pdf["snapshot_hash"],
        token_hash=h, status="active", expires_at=expires_at,
        maximum_accesses=body.maximum_accesses,
        requires_otp=body.requires_otp,
        allowed_actions=body.allowed_actions or ["view", "download", "sign", "request_changes", "reject"],
        created_by=user["id"], updated_by=user["id"],
    )
    await db.quote_public_tokens.insert_one(to_mongo(tok.model_dump(by_alias=True)))
    await record_audit(action="quotes.public_link.create", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="quote_public_token", entity_id=tok.id,
                       after={"quote_id": qid, "expires_at": expires_at.isoformat()})
    return {
        "id": tok.id, "quote_id": qid, "status": "active",
        "expires_at": expires_at.isoformat(),
        "raw_token": raw, "portal_url": f"/p/{raw}",
        "idempotent_hit": False,
    }


@admin_router.post("/quotes/{qid}/public-links/{tid}/revoke")
async def revoke_link(qid: str, tid: str, body: PublicLinkRevoke, request: Request,
                      user: dict = Depends(require_permission("quotes.public_link.revoke"))):
    if not body.reason or not body.reason.strip():
        raise HTTPException(status_code=400, detail="Motivazione obbligatoria")
    db = get_db()
    r = await db.quote_public_tokens.update_one(
        {"_id": tid, "quote_id": qid, "tenant_id": user["tenant_id"], "status": "active"},
        {"$set": {"status": "revoked", "revoked_at": datetime.now(timezone.utc).isoformat(),
                  "revoked_by": user["id"], "revocation_reason": body.reason,
                  "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user["id"]},
         "$inc": {"version": 1}},
    )
    if r.modified_count == 0: raise HTTPException(status_code=404, detail="Link non trovato o già revocato")
    await record_audit(action="quotes.public_link.revoke", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="quote_public_token", entity_id=tid, after={"reason": body.reason})
    return {"ok": True}


@admin_router.post("/quotes/{qid}/public-links/regenerate")
async def regenerate_link(qid: str, body: PublicLinkCreate, request: Request,
                          user: dict = Depends(require_permission("quotes.public_link.regenerate"))):
    db = get_db()
    await db.quote_public_tokens.update_many(
        {"quote_id": qid, "tenant_id": user["tenant_id"], "status": "active"},
        {"$set": {"status": "revoked", "revoked_at": datetime.now(timezone.utc).isoformat(),
                  "revoked_by": user["id"], "revocation_reason": "regenerated"}},
    )
    return await create_link(qid, body, request, user)


@admin_router.get("/quotes/{qid}/public-access-logs")
async def get_access_logs(qid: str, limit: int = 50,
                          user: dict = Depends(require_permission("quotes.public_access_logs.view"))):
    db = get_db()
    docs = await db.public_access_log.find(
        {"quote_id": qid, "tenant_id": user["tenant_id"]}
    ).sort("created_at", -1).limit(min(limit, 200)).to_list(limit)
    return {"items": [from_mongo(d) for d in docs]}


# ==========================================================================
# Token resolver (used by all public endpoints)
# ==========================================================================
async def _apply_rate_limit(request: Request, scope: str, limit: int, window_sec: int,
                             ident_parts: List[str], sensitive: bool = False):
    """Apply Redis-backed rate limit. In prod, fail-closed if limiter is not ready and scope is sensitive."""
    limiter: RateLimiterProvider = await get_limiter()
    if sensitive:
        ok = await limiter_ready_for_sensitive()
        if not ok:
            raise HTTPException(
                status_code=503,
                detail={"error": "service_unavailable",
                        "message": "Servizio temporaneamente non disponibile. Riprova più tardi."},
                headers={"Retry-After": "60"},
            )
    if not limiter.ready:
        # Non-sensitive scope in prod: allow degraded operation only if enabled
        if is_prod_like() and not settings.DEGRADED_PUBLIC_VIEW_ALLOWED:
            raise HTTPException(status_code=503, detail="Servizio temporaneamente non disponibile",
                                headers={"Retry-After": "60"})
        return
    ident_hash = hkey(*ident_parts)
    try:
        allowed, retry, count = await limiter.check_and_incr(scope, ident_hash, limit, window_sec)
    except Exception:
        if sensitive and is_prod_like():
            raise HTTPException(status_code=503, detail="Servizio temporaneamente non disponibile",
                                headers={"Retry-After": "60"})
        return
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "scope": scope,
                    "message": "Troppi tentativi. Riprova tra qualche istante."},
            headers={"Retry-After": str(max(retry, 1))},
        )


async def _resolve_token_soft(token: str, request: Request):
    """Lookup token, return (tok, quote, pdf) without touching access counters.

    Used by action endpoints (sign/otp/etc) where we don't want to bump the view counter.
    Applies token existence + status + expiry checks and raises HTTPException on failure.
    """
    db = get_db()
    ip = _client_ip(request)
    ua = request.headers.get("user-agent", "")[:200]
    ip_hash = _hash_ip(ip)

    h = _hash_token(token)
    tok = await db.quote_public_tokens.find_one({"token_hash": h})
    if not tok:
        await _write_access_log(db=db, tenant_id=None, token_id=None, quote_id=None, quote_revision=None,
                                event="token_invalid", result="denied", reason="not_found",
                                ip_hash=ip_hash, user_agent=ua)
        raise HTTPException(status_code=404, detail="Il collegamento non è valido o non è più disponibile.")

    if tok["status"] == "revoked":
        raise HTTPException(status_code=404, detail="Il collegamento non è valido o non è più disponibile.")
    if tok["status"] == "invalidated":
        raise HTTPException(status_code=410, detail="Questa revisione è stata sostituita da una versione più recente.")
    now = datetime.now(timezone.utc)
    exp = tok.get("expires_at")
    if exp:
        exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00")) if isinstance(exp, str) else exp
        if exp_dt < now:
            await db.quote_public_tokens.update_one({"_id": tok["_id"]}, {"$set": {"status": "expired"}})
            raise HTTPException(status_code=410, detail="Il collegamento è scaduto.")

    quote = await db.quotes.find_one({"_id": tok["quote_id"], "tenant_id": tok["tenant_id"], "deleted_at": None})
    if not quote:
        raise HTTPException(status_code=404, detail="Il collegamento non è valido o non è più disponibile.")
    pdf = await db.quote_pdfs.find_one({"_id": tok["quote_pdf_id"], "tenant_id": tok["tenant_id"]})
    if not pdf or pdf.get("invalidated_at"):
        raise HTTPException(status_code=410, detail="Il preventivo non è più disponibile.")
    return tok, quote, pdf, ip_hash, ua


async def _resolve_token_view(token: str, request: Request, log_event: str = "quote_viewed"):
    """Lookup and bump access counters; write structured access log entry."""
    db = get_db()
    ip = _client_ip(request); ua = request.headers.get("user-agent", "")[:200]
    ip_hash = _hash_ip(ip)

    # Global rate limit: link_open
    await _apply_rate_limit(request, "link_open",
                            settings.RATE_LIMIT_LINK_OPEN_PER_MIN, 60,
                            [ip or "-", token[:16]])
    tok, quote, pdf, ip_hash, ua = await _resolve_token_soft(token, request)

    if tok.get("maximum_accesses") and tok.get("access_count", 0) >= tok["maximum_accesses"]:
        await _write_access_log(db=db, tenant_id=tok["tenant_id"], token_id=tok["_id"],
                                quote_id=tok["quote_id"], quote_revision=tok["quote_revision"],
                                event="token_expired", result="denied", reason="max_accesses",
                                ip_hash=ip_hash, user_agent=ua)
        raise HTTPException(status_code=410, detail="Il collegamento non è più disponibile.")

    now = datetime.now(timezone.utc)
    await db.quote_public_tokens.update_one(
        {"_id": tok["_id"]},
        {"$set": {"last_access_at": now.isoformat()}, "$inc": {"access_count": 1}},
    )
    if quote.get("quote_status") == "sent":
        await db.quotes.update_one({"_id": quote["_id"]},
            {"$set": {"quote_status": "viewed", "viewed_at": now.isoformat()}, "$inc": {"version": 1}})
        await record_activity(
            tenant_id=tok["tenant_id"], type="quote_viewed_by_customer",
            subject=f"Preventivo {quote.get('number')} visualizzato dal cliente",
            quote_id=quote["_id"], user_id=None, user_email=None,
            meta={"token_id": tok["_id"], "ip_hash": ip_hash},
        )
    await _write_access_log(db=db, tenant_id=tok["tenant_id"], token_id=tok["_id"],
                            quote_id=quote["_id"], quote_revision=tok["quote_revision"],
                            event=log_event, ip_hash=ip_hash, user_agent=ua)
    return tok, quote, pdf, ip_hash, ua


# ==========================================================================
# Public: view / download
# ==========================================================================
@public_router.get("/quotes/{token}")
async def public_get_quote(token: str, request: Request, response: Response):
    tok, quote, pdf, ip_hash, ua = await _resolve_token_view(token, request, log_event="quote_viewed")
    db = get_db()
    company = await db.companies.find_one({"_id": tok["tenant_id"]}) or {}
    snapshot = pdf.get("snapshot", {}) or {}
    snap_q = snapshot.get("quote", {}) or {}
    snap_c = snapshot.get("company", {}) or {}

    is_expired = False
    vu_raw = snap_q.get("valid_until")
    if vu_raw:
        try:
            if isinstance(vu_raw, str):
                vu = datetime.fromisoformat(vu_raw.replace("Z", "+00:00"))
            else:
                vu = vu_raw
            if vu.tzinfo is None: vu = vu.replace(tzinfo=timezone.utc)
            is_expired = vu < datetime.now(timezone.utc)
        except Exception:
            pass
    is_superseded = not (quote.get("is_current", True))
    watermark = pdf.get("watermark") or ("SUPERATO" if is_superseded else None)

    def _iso(v):
        if v is None: return None
        if hasattr(v, "isoformat"): return v.isoformat()
        return str(v)

    pt = snapshot.get("payment_terms") or {}
    parts = []
    for inst in (pt.get("installments") or []):
        seg = ""
        if inst.get("percent"): seg = f"{int(inst['percent'])}% "
        elif inst.get("amount"): seg = f"€ {inst['amount']:.2f} "
        seg += {"signature": "alla firma", "survey": "al rilievo", "goods_ready": "ad avviso merce pronta",
                "before_installation": "prima della posa", "on_completion": "a saldo a fine lavori",
                "fixed_date": "entro data fissa"}.get(inst.get("trigger"), "")
        parts.append(seg.strip())
    payment_display = " · ".join(parts) or None

    # Derived allowed actions from token + quote state
    q_status = quote.get("quote_status")
    token_actions = set(tok.get("allowed_actions") or [])
    actions_out = ["view"]
    if "download" in token_actions:
        actions_out.append("download")
    # signed-pdf download only if signed
    if quote.get("latest_signed_pdf_id"):
        actions_out.append("download_signed")
    # modifying actions ONLY when quote is still "open" for signature
    if q_status not in ("signed", "change_requested", "rejected", "cancelled") and not is_superseded and not is_expired:
        if "sign" in token_actions: actions_out.append("sign")
        if "request_changes" in token_actions: actions_out.append("request_changes")
        if "reject" in token_actions: actions_out.append("reject")

    signature_ready = await limiter_ready_for_sensitive() and not is_expired and not is_superseded
    if not signature_ready:
        actions_out = [a for a in actions_out if a not in ("sign", "request_changes", "reject")]

    resp = PublicQuoteResponse(
        company_name=snap_c.get("commercial_name") or snap_c.get("name") or company.get("commercial_name") or company.get("name") or "",
        company_logo_url=snap_c.get("logo_url"),
        company_phone=snap_c.get("phone") or company.get("phone"),
        company_email=snap_c.get("email") or company.get("email"),
        company_website=snap_c.get("website") or company.get("website"),
        primary_color=snap_c.get("primary_color") or "#0F1720",
        secondary_color=snap_c.get("secondary_color") or "#D42027",
        quote_number=snap_q.get("number") or quote.get("number"),
        quote_revision=snap_q.get("revision_label") or tok["quote_revision"],
        title=snap_q.get("title"),
        issue_date=_iso(snap_q.get("issue_date")),
        valid_until=_iso(snap_q.get("valid_until")),
        is_expired=is_expired,
        is_superseded=is_superseded,
        customer_name=(snap_q.get("customer") or {}).get("name"),
        site_address=snap_q.get("site_address"),
        sales_rep_name=(snap_q.get("sales_rep") or {}).get("name"),
        sales_rep_email=(snap_q.get("sales_rep") or {}).get("email"),
        sales_rep_phone=(snap_q.get("sales_rep") or {}).get("phone"),
        intro_text=(snapshot.get("template") or {}).get("intro_text"),
        subtotal=float(snap_q.get("subtotal") or 0),
        vat_amount=float(snap_q.get("vat_amount") or 0),
        total=float(snap_q.get("total") or 0),
        quote_status=q_status,
        payment_terms_display=payment_display,
        allowed_actions=actions_out,
        watermark=watermark,
        has_pdf=True,
    )
    for k, v in _security_headers().items(): response.headers[k] = v
    return resp


@public_router.get("/quotes/{token}/pdf")
async def public_get_pdf(token: str, request: Request):
    # Additional per-scope rate limit
    ip = _client_ip(request)
    await _apply_rate_limit(request, "pdf_download",
                            settings.RATE_LIMIT_PDF_DOWNLOAD_PER_MIN, 60,
                            [ip or "-", token[:16]])
    tok, quote, pdf, ip_hash, ua = await _resolve_token_view(token, request, log_event="pdf_downloaded")
    if "download" not in (tok.get("allowed_actions") or []):
        raise HTTPException(status_code=403, detail="Download non consentito per questo link")
    try:
        pdf_bytes = await _fetch_pdf_bytes(pdf)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Documento temporaneamente non disponibile")
    headers = _security_headers()
    headers["Content-Disposition"] = f'inline; filename="{pdf.get("filename","preventivo.pdf")}"'
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@public_router.get("/quotes/{token}/signed-pdf")
async def public_get_signed_pdf(token: str, request: Request):
    """Download the signed PDF (once signature is completed)."""
    ip = _client_ip(request)
    await _apply_rate_limit(request, "pdf_download",
                            settings.RATE_LIMIT_PDF_DOWNLOAD_PER_MIN, 60,
                            [ip or "-", token[:16]])
    tok, quote, pdf, ip_hash, ua = await _resolve_token_soft(token, request)
    signed_pdf_id = quote.get("latest_signed_pdf_id")
    if not signed_pdf_id:
        raise HTTPException(status_code=404, detail="Documento firmato non disponibile.")
    db = get_db()
    spdf = await db.quote_pdfs.find_one({"_id": signed_pdf_id, "tenant_id": tok["tenant_id"]})
    if not spdf or spdf.get("invalidated_at"):
        raise HTTPException(status_code=404, detail="Documento firmato non disponibile.")
    try:
        pdf_bytes = await _fetch_pdf_bytes(spdf)
    except Exception:
        raise HTTPException(status_code=503, detail="Documento temporaneamente non disponibile")
    await _write_access_log(db=db, tenant_id=tok["tenant_id"], token_id=tok["_id"],
                            quote_id=quote["_id"], quote_revision=tok["quote_revision"],
                            event="signed_pdf_downloaded", ip_hash=ip_hash, user_agent=ua)
    headers = _security_headers()
    headers["Content-Disposition"] = f'inline; filename="{spdf.get("filename","preventivo_firmato.pdf")}"'
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


# ==========================================================================
# Public: OTP request / verify
# ==========================================================================
async def _ensure_quote_open_for_signing(quote: dict, tok: dict):
    if not tok or not quote:
        raise HTTPException(status_code=404, detail="Il collegamento non è valido o non è più disponibile.")
    if not quote.get("is_current", True):
        raise HTTPException(status_code=410, detail="Questa revisione non è più disponibile.")
    q_status = quote.get("quote_status")
    if q_status in ("signed", "rejected", "change_requested", "cancelled"):
        raise HTTPException(status_code=409, detail={"error": "quote_not_open", "state": q_status,
                                                      "message": "Il preventivo non è più modificabile dal cliente."})
    # Expiry check
    vu = quote.get("valid_until")
    if vu:
        try:
            if isinstance(vu, str):
                vu_dt = datetime.fromisoformat(vu.replace("Z", "+00:00"))
            else:
                vu_dt = vu
            if vu_dt.tzinfo is None:
                vu_dt = vu_dt.replace(tzinfo=timezone.utc)
            if vu_dt < datetime.now(timezone.utc):
                raise HTTPException(status_code=410, detail={"error": "quote_expired",
                                                              "message": "Il preventivo è scaduto. Contatta il tuo consulente per un aggiornamento."})
        except HTTPException:
            raise
        except Exception:
            pass
    for act in ("sign", "request_changes", "reject"):
        if act in (tok.get("allowed_actions") or []):
            return
    raise HTTPException(status_code=403, detail="Azione non consentita")


def _mask_phone(p: Optional[str]) -> Optional[str]:
    if not p: return None
    digits = "".join(ch for ch in p if ch.isdigit())
    if len(digits) < 4: return "***"
    return f"***{digits[-3:]}"


@public_router.post("/quotes/{token}/request-otp")
async def request_otp(token: str, body: PublicOtpRequestBody, request: Request):
    tok, quote, pdf, ip_hash, ua = await _resolve_token_soft(token, request)
    await _ensure_quote_open_for_signing(quote, tok)
    # Sensitive scope → fail-closed if Redis unavailable in prod
    if not await limiter_ready_for_sensitive():
        raise HTTPException(status_code=503, detail={
            "error": "service_unavailable",
            "message": "Servizio firma temporaneamente non disponibile."},
            headers={"Retry-After": "60"})
    ip = _client_ip(request)
    # 1) Cooldown 60s between requests per token
    limiter = await get_limiter()
    cool_hash = hkey("cooldown", tok["_id"])
    remaining = await limiter.get_lock_ttl("otp_cooldown", cool_hash)
    if remaining > 0:
        raise HTTPException(status_code=429,
                            detail={"error": "cooldown", "message": f"Attendere {remaining}s prima di richiedere un nuovo codice."},
                            headers={"Retry-After": str(remaining)})
    # 2) Window: max N requests per 10 min (per token+recipient)
    email_low = (body.email or "").strip().lower()
    if "@" not in email_low:
        raise HTTPException(status_code=400, detail="Email non valida")
    ident_hash = hkey(tok["_id"], email_low)
    await _apply_rate_limit(request, "otp_request",
                            settings.RATE_LIMIT_OTP_REQUEST_MAX,
                            settings.RATE_LIMIT_OTP_REQUEST_WINDOW_SEC,
                            [tok["_id"], email_low], sensitive=True)
    # 3) Daily cap per token
    await _apply_rate_limit(request, "otp_request_daily",
                            settings.RATE_LIMIT_OTP_REQUEST_DAILY_MAX, 86400,
                            [tok["_id"]], sensitive=True)
    # Set cooldown lock
    await limiter.set_lock("otp_cooldown", cool_hash, settings.RATE_LIMIT_OTP_REQUEST_COOLDOWN_SEC)

    # Company for email context
    db = get_db()
    company = await db.companies.find_one({"_id": tok["tenant_id"]}) or {}
    company_name = company.get("commercial_name") or company.get("name") or "Infissi Express"
    req = await otp_svc.build_and_send(
        tenant_id=tok["tenant_id"], token_id=tok["_id"], quote_id=quote["_id"], email=email_low,
        ip_hash=ip_hash, user_agent=ua,
        quote_number=quote.get("number") or "", company_name=company_name,
    )
    await _write_access_log(db=db, tenant_id=tok["tenant_id"], token_id=tok["_id"],
                            quote_id=quote["_id"], quote_revision=tok["quote_revision"],
                            event="otp_requested", ip_hash=ip_hash, user_agent=ua)
    return {
        "request_id": req.id,
        "recipient_masked": req.recipient_masked,
        "expires_in_seconds": settings.OTP_TTL_SECONDS,
        "max_attempts": settings.RATE_LIMIT_OTP_VERIFY_MAX_ATTEMPTS,
    }


@public_router.post("/quotes/{token}/verify-otp")
async def verify_otp(token: str, body: PublicOtpVerifyBody, request: Request):
    tok, quote, pdf, ip_hash, ua = await _resolve_token_soft(token, request)
    await _ensure_quote_open_for_signing(quote, tok)
    if not await limiter_ready_for_sensitive():
        raise HTTPException(status_code=503, detail="Servizio firma temporaneamente non disponibile",
                            headers={"Retry-After": "60"})
    # Daily fail cap
    limiter = await get_limiter()
    fail_ident = hkey("verify_fail", tok["_id"])
    fail_count = await limiter.get_count("otp_verify_daily_fail", fail_ident)
    if fail_count >= settings.RATE_LIMIT_OTP_VERIFY_DAILY_MAX_FAIL:
        raise HTTPException(status_code=429, detail="Troppi tentativi falliti. Riprova domani.",
                            headers={"Retry-After": "3600"})

    ok, reason, doc = await otp_svc.verify_otp(body.request_id, body.code)
    db = get_db()
    if not ok:
        # increment daily fail counter (24h window)
        await limiter.check_and_incr("otp_verify_daily_fail", fail_ident,
                                     settings.RATE_LIMIT_OTP_VERIFY_DAILY_MAX_FAIL + 5, 86400)
        await _write_access_log(db=db, tenant_id=tok["tenant_id"], token_id=tok["_id"],
                                quote_id=quote["_id"], quote_revision=tok["quote_revision"],
                                event="otp_failed", result="denied", reason=reason,
                                ip_hash=ip_hash, user_agent=ua)
        map_ = {
            "not_found": (404, "Richiesta OTP non trovata"),
            "expired": (410, "Il codice è scaduto. Richiedine uno nuovo."),
            "too_many_attempts": (429, "Troppi tentativi. Richiedi un nuovo codice."),
            "invalid_code": (400, "Codice non valido."),
        }
        status_code, msg = map_.get(reason, (400, "Verifica non riuscita"))
        raise HTTPException(status_code=status_code, detail={"error": reason, "message": msg})
    await _write_access_log(db=db, tenant_id=tok["tenant_id"], token_id=tok["_id"],
                            quote_id=quote["_id"], quote_revision=tok["quote_revision"],
                            event="otp_verified", ip_hash=ip_hash, user_agent=ua)
    return {"ok": True, "request_id": body.request_id, "verified_at": datetime.now(timezone.utc).isoformat()}


# ==========================================================================
# Public: sign
# ==========================================================================
@public_router.post("/quotes/{token}/sign")
async def sign_quote(token: str, body: PublicSignatureSubmit, request: Request):
    tok, quote, pdf, ip_hash, ua = await _resolve_token_soft(token, request)
    await _ensure_quote_open_for_signing(quote, tok)
    if "sign" not in (tok.get("allowed_actions") or []):
        raise HTTPException(status_code=403, detail="Firma non consentita per questo link")
    if not await limiter_ready_for_sensitive():
        raise HTTPException(status_code=503, detail="Servizio firma temporaneamente non disponibile",
                            headers={"Retry-After": "60"})
    # Per-hour rate limit
    await _apply_rate_limit(request, "sign",
                            settings.RATE_LIMIT_SIGN_PER_HOUR, 3600,
                            [tok["_id"]], sensitive=True)

    # Consent checks (all must be true)
    for f in ("accept_terms", "accept_privacy", "accept_payment_terms", "consent_electronic_sign"):
        if not getattr(body, f, False):
            raise HTTPException(status_code=400, detail={"error": "consents_missing", "field": f,
                                                          "message": "È necessario accettare tutte le dichiarazioni per firmare."})

    # Idempotency lock: prevent double click producing two signatures
    limiter = await get_limiter()
    idem_hash = hkey("sign_idem", tok["_id"])
    got_lock = await limiter.set_lock("sign_idem", idem_hash, 30)
    if not got_lock:
        raise HTTPException(status_code=409, detail={"error": "in_progress",
                                                      "message": "Firma in corso. Attendere qualche secondo."})

    db = get_db()

    # Verify OTP: must match request_id + code, and belong to this token, and be in `verified` status OR still valid now
    otp_doc = await db.quote_otp_requests.find_one({"_id": body.otp_request_id, "token_id": tok["_id"]})
    if not otp_doc:
        raise HTTPException(status_code=400, detail={"error": "otp_missing", "message": "OTP non trovato o non valido."})
    if otp_doc.get("status") != "verified":
        # Attempt to verify inline
        ok, reason, _ = await otp_svc.verify_otp(body.otp_request_id, body.otp_code)
        if not ok:
            raise HTTPException(status_code=400, detail={"error": "otp_invalid", "message": "OTP non valido o scaduto."})
        otp_doc = await db.quote_otp_requests.find_one({"_id": body.otp_request_id})

    # Idempotency: if signature already exists for this token → return existing
    existing_sig = await db.quote_signatures.find_one({
        "token_id": tok["_id"], "quote_id": quote["_id"], "tenant_id": tok["tenant_id"],
        "deleted_at": None,
    })
    if existing_sig:
        return {
            "ok": True, "already_signed": True,
            "evidence_id": existing_sig.get("evidence_id_short"),
            "signed_pdf_id": existing_sig.get("signed_pdf_id"),
        }

    # Decode signature image
    try:
        img_bytes = sig_svc.parse_signature_data_url(body.signature.data_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "invalid_signature",
                                                      "message": f"Firma non valida: {e}"})
    image_hash = hashlib.sha256(img_bytes).hexdigest()

    # Build consents
    consents = {
        "accept_terms": bool(body.accept_terms),
        "accept_privacy": bool(body.accept_privacy),
        "accept_payment_terms": bool(body.accept_payment_terms),
        "consent_electronic_sign": bool(body.consent_electronic_sign),
    }
    # Clauses version hash from snapshot
    snapshot = pdf.get("snapshot", {}) or {}
    clauses = snapshot.get("clauses") or []
    clauses_hash = sig_svc.clauses_version_digest(clauses)

    signed_at = datetime.now(timezone.utc)
    # Build evidence payload
    signer = {
        "first_name": body.first_name.strip(),
        "last_name": body.last_name.strip(),
        "email_hash": otp_doc.get("recipient_hash"),
        "fiscal_role": body.fiscal_role,
        "company_represented": body.company_represented,
    }
    sig_meta = {
        "image_hash": image_hash,
        "stroke_count": body.signature.stroke_count,
        "canvas_width": body.signature.canvas_width,
        "canvas_height": body.signature.canvas_height,
        "duration_ms": body.signature.total_duration_ms,
    }
    payload = sig_svc.canonical_payload(
        quote=quote, pdf=pdf, token=tok, otp=otp_doc, signer=signer,
        consents=consents, signature_meta=sig_meta,
        ip_hash=ip_hash, user_agent=ua,
        clauses_version_hash=clauses_hash, signed_at=signed_at,
    )
    evidence_hash = sig_svc.compute_evidence_hash(payload)
    short_id = evidence_hash[:8].upper()

    # Persist signature doc
    sig_doc = QuoteSignature(
        id=new_id(),
        tenant_id=tok["tenant_id"],
        quote_id=quote["_id"], quote_number=quote.get("number"),
        quote_revision=tok["quote_revision"],
        quote_pdf_id=pdf["_id"], snapshot_hash=pdf["snapshot_hash"],
        token_id=tok["_id"], otp_request_id=otp_doc["_id"],
        signer_first_name=body.first_name.strip(),
        signer_last_name=body.last_name.strip(),
        signer_email_hash=otp_doc.get("recipient_hash") or "",
        signer_email_masked=otp_doc.get("recipient_masked") or "",
        signer_fiscal_role=body.fiscal_role,
        signer_company_represented=body.company_represented,
        signature_image_hash=image_hash,
        signature_stroke_count=body.signature.stroke_count,
        signature_capture_duration_ms=body.signature.total_duration_ms,
        consents=consents, clauses_version_hash=clauses_hash,
        evidence_hash=evidence_hash, evidence_payload=payload,
        evidence_id_short=short_id,
        ip_hash=ip_hash, user_agent=ua,
        signed_at_utc=signed_at,
        signed_at_local_display=sig_svc.local_display(signed_at),
        signature_type="FES",
    )

    # Render signed PDF (base + signature page)
    signature_data_url = body.signature.data_url  # kept only in PDF, not stored
    sig_render_ctx = sig_svc.build_signature_context(
        sig_doc=sig_doc.model_dump(), evidence_payload=payload,
        evidence_hash=evidence_hash, signed_at_utc=signed_at,
        signature_data_url=signature_data_url,
    )
    evidence_ctx = {
        "evidence_hash": evidence_hash,
        "short_id": short_id,
        "original_pdf_hash": pdf.get("pdf_hash"),
        "snapshot_hash": pdf.get("snapshot_hash"),
    }
    try:
        signed_bytes = sig_svc.render_signed_pdf(
            base_snapshot=snapshot, base_watermark=None,
            signature=sig_render_ctx, evidence=evidence_ctx,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore rendering PDF firmato: {e}")
    signed_pdf_hash = hashlib.sha256(signed_bytes).hexdigest()

    # Persist signed PDF as a new quote_pdfs record (kind=signed) — original never touched
    signed_pdf_id = new_id()
    storage_key = None; storage_provider = "inline"; pdf_base64_field = None
    try:
        if object_storage.is_available():
            storage_key = object_storage.build_pdf_path(tok["tenant_id"], quote["_id"],
                                                        f"{tok['quote_revision']}-signed", signed_pdf_id)
            object_storage.put_pdf(storage_key, signed_bytes)
            storage_provider = "emergent"
        else:
            pdf_base64_field = base64.b64encode(signed_bytes).decode("ascii")
    except Exception:
        pdf_base64_field = base64.b64encode(signed_bytes).decode("ascii")
        storage_provider = "inline"; storage_key = None

    signed_pdf_doc = {
        "_id": signed_pdf_id,
        "tenant_id": tok["tenant_id"],
        "quote_id": quote["_id"],
        "quote_number": quote.get("number"),
        "quote_revision": tok["quote_revision"],
        "quote_version_snapshot": quote.get("version", 1),
        "template_id": pdf.get("template_id"),
        "template_version": pdf.get("template_version"),
        "kind": "signed",
        "watermark": None,
        "snapshot_hash": pdf.get("snapshot_hash"),
        "pdf_hash": signed_pdf_hash,
        "filename": f"Preventivo_firmato_{(quote.get('number') or 'X').replace('/', '_')}_{short_id}.pdf",
        "storage_provider": storage_provider,
        "storage_key": storage_key,
        "size_bytes": len(signed_bytes),
        "mime_type": "application/pdf",
        "snapshot": snapshot,
        "pdf_base64": pdf_base64_field,
        "generated_by": None,
        "generated_at": signed_at.isoformat(),
        "created_at": signed_at.isoformat(),
        "updated_at": signed_at.isoformat(),
        "version": 1,
        "deleted_at": None,
        "signature_id": sig_doc.id,
    }
    await db.quote_pdfs.insert_one(signed_pdf_doc)

    # Optionally persist signature PNG in object storage (separate key)
    sig_storage_key = None
    # NOTE: skipped for now — image_hash suffices as evidence; the PNG is
    # embedded in the signed PDF (which is stored).

    # Finalize signature doc
    sig_doc.signed_pdf_id = signed_pdf_id
    sig_doc.signed_pdf_hash = signed_pdf_hash
    sig_doc.signature_storage_key = sig_storage_key
    await db.quote_signatures.insert_one(to_mongo(sig_doc.model_dump(by_alias=True)))

    # Update quote status → signed and lock modifying actions
    new_allowed_actions = ["view", "download", "download_signed"]
    await db.quotes.update_one(
        {"_id": quote["_id"], "tenant_id": tok["tenant_id"]},
        {"$set": {
            "quote_status": "signed",
            "signed_at": signed_at.isoformat(),
            "signed_by_name": f"{sig_doc.signer_first_name} {sig_doc.signer_last_name}".strip(),
            "signed_ip_hash": ip_hash,
            "latest_signed_pdf_id": signed_pdf_id,
            "latest_signed_pdf_hash": signed_pdf_hash,
            "latest_signature_id": sig_doc.id,
            "updated_at": signed_at.isoformat(),
         }, "$inc": {"version": 1}},
    )
    # Update token allowed actions, mark as consumed for modifying actions
    await db.quote_public_tokens.update_one(
        {"_id": tok["_id"]},
        {"$set": {"allowed_actions": new_allowed_actions,
                  "status": "active",  # remain active for read-only downloads
                  "signature_id": sig_doc.id,
                  "signed_at": signed_at.isoformat()}},
    )
    # Invalidate all other pending OTPs for this token
    await db.quote_otp_requests.update_many(
        {"token_id": tok["_id"], "status": "pending"},
        {"$set": {"status": "superseded"}},
    )
    # Record activity + audit
    await record_activity(
        tenant_id=tok["tenant_id"], type="quote_signed",
        subject=f"Preventivo {quote.get('number')} firmato dal cliente",
        quote_id=quote["_id"], user_id=None, user_email=None,
        meta={"signature_id": sig_doc.id, "evidence_id": short_id,
              "signer_name": f"{sig_doc.signer_first_name} {sig_doc.signer_last_name}".strip(),
              "signed_pdf_id": signed_pdf_id},
    )
    await record_audit(
        action="quotes.public.sign",
        tenant_id=tok["tenant_id"], user_id=None, user_email=None, ip=None,
        entity_type="quote_signature", entity_id=sig_doc.id,
        after={"quote_id": quote["_id"], "evidence_id": short_id, "signed_pdf_id": signed_pdf_id},
    )
    # Notify sales rep
    await _notify_sales_rep(db=db, tenant_id=tok["tenant_id"], quote=quote, kind="signed",
                            title=f"Preventivo {quote.get('number')} firmato",
                            body=f"Firmato da {sig_doc.signer_first_name} {sig_doc.signer_last_name} (Evidence {short_id})",
                            link=f"/quotes/{quote['_id']}")
    await _write_access_log(db=db, tenant_id=tok["tenant_id"], token_id=tok["_id"],
                            quote_id=quote["_id"], quote_revision=tok["quote_revision"],
                            event="signature_completed", ip_hash=ip_hash, user_agent=ua)
    return {
        "ok": True,
        "evidence_id": short_id,
        "signed_pdf_id": signed_pdf_id,
        "signed_at": signed_at.isoformat(),
        "message": "Firma acquisita. Il documento firmato è disponibile per il download.",
    }


# ==========================================================================
# Public: reject / request-changes
# ==========================================================================
@public_router.post("/quotes/{token}/request-changes")
async def public_request_changes(token: str, body: PublicRequestChangesBody, request: Request):
    tok, quote, pdf, ip_hash, ua = await _resolve_token_soft(token, request)
    await _ensure_quote_open_for_signing(quote, tok)
    if "request_changes" not in (tok.get("allowed_actions") or []):
        raise HTTPException(status_code=403, detail="Azione non consentita")
    if not await limiter_ready_for_sensitive():
        raise HTTPException(status_code=503, detail="Servizio temporaneamente non disponibile",
                            headers={"Retry-After": "60"})
    # per-hour rate limit shared with sign
    await _apply_rate_limit(request, "sign",
                            settings.RATE_LIMIT_SIGN_PER_HOUR, 3600,
                            [tok["_id"]], sensitive=True)
    db = get_db()
    now = datetime.now(timezone.utc)
    cr = CustomerRequest(
        id=new_id(),
        tenant_id=tok["tenant_id"],
        quote_id=quote["_id"], quote_number=quote.get("number"),
        quote_revision=tok["quote_revision"],
        token_id=tok["_id"], kind="change_request",
        reason=body.reason, notes=body.notes,
        contact_email_hash=(hashlib.sha256((body.contact_email or "").strip().lower().encode()).hexdigest()[:24]
                            if body.contact_email else None),
        contact_phone_masked=_mask_phone(body.contact_phone),
        preferred_callback=body.preferred_callback,
        ip_hash=ip_hash, user_agent=ua, request_status="open",
    )
    await db.customer_requests.insert_one(to_mongo(cr.model_dump(by_alias=True)))
    # Lock token to read-only
    new_actions = ["view", "download"]
    await db.quote_public_tokens.update_one(
        {"_id": tok["_id"]},
        {"$set": {"allowed_actions": new_actions}},
    )
    # Update quote status
    await db.quotes.update_one(
        {"_id": quote["_id"], "tenant_id": tok["tenant_id"]},
        {"$set": {"quote_status": "change_requested",
                  "change_requested_at": now.isoformat(),
                  "updated_at": now.isoformat()},
         "$inc": {"version": 1}},
    )
    await record_activity(
        tenant_id=tok["tenant_id"], type="quote_change_requested",
        subject=f"Cliente richiede modifica al preventivo {quote.get('number')}",
        body=body.reason, quote_id=quote["_id"],
        meta={"request_id": cr.id, "notes": body.notes, "contact": body.preferred_callback},
    )
    await record_audit(
        action="quotes.public.request_changes",
        tenant_id=tok["tenant_id"], entity_type="quote", entity_id=quote["_id"],
        after={"request_id": cr.id, "reason": body.reason},
    )
    await _notify_sales_rep(db=db, tenant_id=tok["tenant_id"], quote=quote, kind="change_requested",
                            title=f"Modifica richiesta sul preventivo {quote.get('number')}",
                            body=(body.reason or "")[:300],
                            link=f"/quotes/{quote['_id']}")
    await _write_access_log(db=db, tenant_id=tok["tenant_id"], token_id=tok["_id"],
                            quote_id=quote["_id"], quote_revision=tok["quote_revision"],
                            event="change_requested", ip_hash=ip_hash, user_agent=ua)
    return {"ok": True, "request_id": cr.id,
            "message": "Richiesta inviata. Il tuo consulente prenderà contatto a breve."}


@public_router.post("/quotes/{token}/reject")
async def public_reject(token: str, body: PublicRejectBody, request: Request):
    tok, quote, pdf, ip_hash, ua = await _resolve_token_soft(token, request)
    await _ensure_quote_open_for_signing(quote, tok)
    if "reject" not in (tok.get("allowed_actions") or []):
        raise HTTPException(status_code=403, detail="Azione non consentita")
    if not await limiter_ready_for_sensitive():
        raise HTTPException(status_code=503, detail="Servizio temporaneamente non disponibile",
                            headers={"Retry-After": "60"})
    await _apply_rate_limit(request, "sign",
                            settings.RATE_LIMIT_SIGN_PER_HOUR, 3600,
                            [tok["_id"]], sensitive=True)
    db = get_db()
    now = datetime.now(timezone.utc)
    cr = CustomerRequest(
        id=new_id(),
        tenant_id=tok["tenant_id"],
        quote_id=quote["_id"], quote_number=quote.get("number"),
        quote_revision=tok["quote_revision"],
        token_id=tok["_id"], kind="rejection",
        reason_code=body.reason_code, notes=body.notes,
        ip_hash=ip_hash, user_agent=ua, request_status="open",
    )
    await db.customer_requests.insert_one(to_mongo(cr.model_dump(by_alias=True)))
    new_actions = ["view", "download"]
    await db.quote_public_tokens.update_one(
        {"_id": tok["_id"]},
        {"$set": {"allowed_actions": new_actions}},
    )
    await db.quotes.update_one(
        {"_id": quote["_id"], "tenant_id": tok["tenant_id"]},
        {"$set": {"quote_status": "rejected",
                  "rejected_at": now.isoformat(),
                  "rejection_reason_code": body.reason_code,
                  "updated_at": now.isoformat()},
         "$inc": {"version": 1}},
    )
    await record_activity(
        tenant_id=tok["tenant_id"], type="quote_rejected_by_customer",
        subject=f"Preventivo {quote.get('number')} rifiutato dal cliente",
        body=body.notes, quote_id=quote["_id"],
        meta={"request_id": cr.id, "reason_code": body.reason_code},
    )
    await record_audit(
        action="quotes.public.reject",
        tenant_id=tok["tenant_id"], entity_type="quote", entity_id=quote["_id"],
        after={"request_id": cr.id, "reason_code": body.reason_code},
    )
    await _notify_sales_rep(db=db, tenant_id=tok["tenant_id"], quote=quote, kind="rejected",
                            title=f"Preventivo {quote.get('number')} rifiutato",
                            body=(body.notes or "")[:300],
                            link=f"/quotes/{quote['_id']}")
    await _write_access_log(db=db, tenant_id=tok["tenant_id"], token_id=tok["_id"],
                            quote_id=quote["_id"], quote_revision=tok["quote_revision"],
                            event="rejected", ip_hash=ip_hash, user_agent=ua)
    return {"ok": True, "request_id": cr.id,
            "message": "Rifiuto registrato. Grazie per la comunicazione."}


# ==========================================================================
# Admin: customer-requests management (M3.3.4)
# ==========================================================================
@admin_router.get("/quotes/{qid}/customer-requests")
async def list_customer_requests(qid: str,
                                  user: dict = Depends(require_permission("quotes.public_action.review"))):
    db = get_db()
    docs = await db.customer_requests.find(
        {"quote_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None}
    ).sort("created_at", -1).to_list(200)
    return {"items": [from_mongo(d) for d in docs]}


@admin_router.post("/customer-requests/{rid}/take")
async def take_customer_request(rid: str, body: CustomerRequestTake, request: Request,
                                 user: dict = Depends(require_permission("quotes.public_action.take_over"))):
    db = get_db()
    d = await db.customer_requests.find_one({"_id": rid, "tenant_id": user["tenant_id"]})
    if not d: raise HTTPException(status_code=404, detail="Richiesta non trovata")
    if d.get("request_status") in ("closed", "superseded"):
        raise HTTPException(status_code=400, detail="Richiesta già chiusa")
    now = datetime.now(timezone.utc).isoformat()
    await db.customer_requests.update_one(
        {"_id": rid},
        {"$set": {"request_status": "in_progress", "taken_over_by": user["id"],
                  "resolution_notes": body.notes, "updated_at": now, "updated_by": user["id"]}},
    )
    await record_audit(action="customer_requests.take", tenant_id=user["tenant_id"],
                       user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
                       entity_type="customer_request", entity_id=rid, after={"notes": body.notes})
    return {"ok": True}


@admin_router.post("/customer-requests/{rid}/close")
async def close_customer_request(rid: str, body: CustomerRequestClose, request: Request,
                                  user: dict = Depends(require_permission("quotes.public_action.close"))):
    if body.resolution not in ("closed_no_revision", "new_revision_created", "withdrawn"):
        raise HTTPException(status_code=400, detail="Risoluzione non valida")
    db = get_db()
    d = await db.customer_requests.find_one({"_id": rid, "tenant_id": user["tenant_id"]})
    if not d: raise HTTPException(status_code=404, detail="Richiesta non trovata")
    now = datetime.now(timezone.utc).isoformat()
    await db.customer_requests.update_one(
        {"_id": rid},
        {"$set": {"request_status": "closed", "resolution": body.resolution,
                  "resolution_notes": body.resolution_notes,
                  "resolved_at": now, "resolved_by": user["id"],
                  "updated_at": now, "updated_by": user["id"]}},
    )
    await record_audit(action="customer_requests.close", tenant_id=user["tenant_id"],
                       user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
                       entity_type="customer_request", entity_id=rid,
                       after={"resolution": body.resolution, "notes": body.resolution_notes})
    return {"ok": True}


@admin_router.post("/quotes/{qid}/reopen")
async def reopen_quote(qid: str, request: Request,
                       user: dict = Depends(require_permission("quotes.reopen"))):
    db = get_db()
    d = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not d: raise HTTPException(status_code=404, detail="Preventivo non trovato")
    if d.get("quote_status") not in ("rejected", "change_requested"):
        raise HTTPException(status_code=400, detail="Solo preventivi rifiutati o con modifica richiesta possono essere riaperti")
    now = datetime.now(timezone.utc).isoformat()
    await db.quotes.update_one(
        {"_id": qid, "tenant_id": user["tenant_id"]},
        {"$set": {"quote_status": "sent", "reopened_at": now, "updated_at": now, "updated_by": user["id"]},
         "$inc": {"version": 1}},
    )
    await record_activity(
        tenant_id=user["tenant_id"], type="quote_reopened",
        subject=f"Preventivo {d.get('number')} riaperto",
        quote_id=qid, user_id=user["id"], user_email=user["email"],
    )
    await record_audit(action="quotes.reopen", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="quote", entity_id=qid, after={"from_status": d.get("quote_status")})
    return {"ok": True}


# ==========================================================================
# Automatic invalidation hook on new revision (used by quotes router)
# ==========================================================================
async def invalidate_tokens_for_previous_revisions(tenant_id: str, quote_id: str, exclude_pdf_id: Optional[str] = None):
    db = get_db()
    q = {"tenant_id": tenant_id, "quote_id": quote_id, "status": "active"}
    if exclude_pdf_id:
        q["quote_pdf_id"] = {"$ne": exclude_pdf_id}
    now = datetime.now(timezone.utc).isoformat()
    await db.quote_public_tokens.update_many(q, {"$set": {"status": "invalidated", "revoked_at": now,
                                                            "revocation_reason": "superseded_by_new_revision"}})


# ==========================================================================
# Sales-rep notification helper
# ==========================================================================
async def _notify_sales_rep(*, db, tenant_id: str, quote: dict, kind: str,
                             title: str, body: str, link: Optional[str]):
    """Create in-app notification for the sales rep AND (best-effort) email if provider real."""
    rep_id = quote.get("sales_rep_id")
    if not rep_id:
        return
    now = datetime.now(timezone.utc).isoformat()
    await db.notifications.insert_one({
        "_id": new_id(),
        "tenant_id": tenant_id,
        "user_id": rep_id,
        "type": "info",
        "title": title, "body": body, "link": link,
        "read_at": None, "created_at": now, "updated_at": now,
        "deleted_at": None, "version": 1,
        "meta": {"kind": kind, "quote_id": quote.get("_id")},
    })
    # Best-effort email — mock provider in dev, real in prod
    try:
        from app.services.email import send_email
        rep = await db.users.find_one({"_id": rep_id, "tenant_id": tenant_id})
        if rep and rep.get("email"):
            html = f"<div style='font-family:system-ui,sans-serif'><h3>{title}</h3><p>{body}</p></div>"
            await send_email(to=rep["email"], subject=title,
                             template=f"portal_{kind}", html=html, text=f"{title}\n\n{body}")
    except Exception:
        pass
