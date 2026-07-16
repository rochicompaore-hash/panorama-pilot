"""Public quote portal (M3.3.3) — token-based read-only access."""
from __future__ import annotations
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from collections import defaultdict, deque
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models import new_id
from app.models_public import (
    QuotePublicToken, PublicLinkCreate, PublicLinkRevoke, PublicAccessLog, PublicQuoteResponse,
)
from app.mongo_utils import to_mongo, from_mongo
from app.services.audit import record_audit
from app.services.timeline import record_activity
from app.routers.pdf_router import _fetch_pdf_bytes

# Admin-scoped operations
admin_router = APIRouter(tags=["public-links"])
# Public unauthenticated portal
public_router = APIRouter(prefix="/public", tags=["public-portal"])


# ---------- utils ----------
def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _hash_ip(ip: Optional[str]) -> Optional[str]:
    if not ip: return None
    return hashlib.sha256(f"iph:{ip}".encode()).hexdigest()[:16]


def _generate_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hash). Raw returned ONCE to the caller."""
    raw = secrets.token_urlsafe(32)  # 43 chars, 256 bits entropy
    return raw, _hash_token(raw)


# ---------- rate limit (in-memory token bucket per IP + token) ----------
_RATE: dict[str, deque] = defaultdict(deque)
RATE_WINDOW_SEC = 60
RATE_LIMIT_PER_MIN = 30


def _check_rate(key: str) -> bool:
    now = time.time()
    q = _RATE[key]
    while q and (now - q[0]) > RATE_WINDOW_SEC:
        q.popleft()
    if len(q) >= RATE_LIMIT_PER_MIN:
        return False
    q.append(now)
    return True


# ---------- Admin: create/list/revoke/regenerate ----------
@admin_router.get("/quotes/{qid}/public-links")
async def list_links(qid: str, user: dict = Depends(require_permission("quotes.public_link.view"))):
    db = get_db()
    docs = await db.quote_public_tokens.find(
        {"quote_id": qid, "tenant_id": user["tenant_id"]},
        {"metadata.raw_token_once": 0},  # never expose even old raw tokens if any leaked
    ).sort("created_at", -1).to_list(50)
    items = []
    for d in docs:
        m = from_mongo(d)
        m.pop("token_hash", None)  # never return the hash either
        items.append(m)
    return {"items": items}


@admin_router.post("/quotes/{qid}/public-links")
async def create_link(qid: str, body: PublicLinkCreate, request: Request,
                      user: dict = Depends(require_permission("quotes.public_link.create"))):
    db = get_db()
    quote = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not quote: raise HTTPException(status_code=404, detail="Preventivo non trovato")

    # Must have a definitive PDF, not invalidated
    pdf = await db.quote_pdfs.find_one({
        "quote_id": qid, "tenant_id": user["tenant_id"],
        "kind": "definitive", "invalidated_at": None,
    }, sort=[("generated_at", -1)])
    if not pdf:
        raise HTTPException(status_code=400, detail="Nessun PDF definitivo disponibile. Emetti prima il PDF.")
    if quote.get("quote_status") in ("cancelled", "rejected"):
        raise HTTPException(status_code=400, detail="Preventivo annullato: link pubblico non consentito")
    if not quote.get("is_current", True):
        raise HTTPException(status_code=400, detail="Revisione superata: creare link sulla revisione corrente")

    # Idempotency: if active token exists for same pdf+snapshot, return it (without raw!)
    existing = await db.quote_public_tokens.find_one({
        "tenant_id": user["tenant_id"], "quote_id": qid,
        "quote_pdf_id": pdf["_id"], "snapshot_hash": pdf["snapshot_hash"],
        "status": "active",
    })
    if existing:
        exp = existing.get("expires_at")
        if exp and datetime.fromisoformat(exp.replace("Z", "+00:00")) > datetime.now(timezone.utc):
            return {
                "id": str(existing["_id"]), "quote_id": qid,
                "status": "active", "expires_at": existing.get("expires_at"),
                "idempotent_hit": True,
                "raw_token": None,  # cannot re-emit raw for existing token
                "portal_url": None,
                "message": "Token attivo già esistente. Usa 'Rigenera' per ottenerne uno nuovo.",
            }

    # Determine expiry
    now = datetime.now(timezone.utc)
    if body.expires_at:
        expires_at = body.expires_at
    else:
        days = body.validity_days if body.validity_days is not None else 30
        expires_at = now + timedelta(days=days)

    # Generate token
    raw, h = _generate_token()
    tok = QuotePublicToken(
        id=new_id(), tenant_id=user["tenant_id"],
        quote_id=qid, quote_number=quote.get("number"),
        quote_revision=quote.get("revision_label") or f"R{int(quote.get('revision',0)):02d}",
        quote_pdf_id=pdf["_id"], snapshot_hash=pdf["snapshot_hash"],
        token_hash=h, status="active", expires_at=expires_at,
        maximum_accesses=body.maximum_accesses,
        requires_otp=body.requires_otp,
        allowed_actions=body.allowed_actions or ["view", "download"],
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
        "raw_token": raw,  # shown ONCE
        "portal_url": f"/p/{raw}",  # relative — frontend prefixes host
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
    """Revoke all active tokens for this quote, then create a new one."""
    db = get_db()
    await db.quote_public_tokens.update_many(
        {"quote_id": qid, "tenant_id": user["tenant_id"], "status": "active"},
        {"$set": {"status": "revoked", "revoked_at": datetime.now(timezone.utc).isoformat(),
                  "revoked_by": user["id"], "revocation_reason": "regenerated"}},
    )
    return await create_link(qid, body, request, user)  # reuse


# ---------- Public unauthenticated portal ----------
async def _resolve_token(token: str, request: Request, log_event: str = "link_opened"):
    """Look up token, validate status/expiry, log access, return (tok_doc, quote, pdf).

    Never reveals whether the token/quote exists or not — always same 404 message.
    """
    db = get_db()
    ip = None
    try:
        xff = request.headers.get("x-forwarded-for")
        ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else None)
    except Exception:
        ip = None
    ua = request.headers.get("user-agent", "")[:200]
    ip_hash = _hash_ip(ip)
    rate_key = f"{ip}|{token[:8]}"

    async def _log(event: str, result: str = "ok", reason: str = None, quote_id: str = None, revision: str = None, token_id: str = None):
        await db.public_access_log.insert_one({
            "_id": new_id(),
            "tenant_id": None,  # populated when tok is resolved
            "token_id": token_id,
            "quote_id": quote_id,
            "quote_revision": revision,
            "event": event, "result": result, "reason": reason,
            "ip_hash": ip_hash, "user_agent": ua,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    if not _check_rate(rate_key):
        await _log("rate_limited", result="denied", reason="ip+token_rate_exceeded")
        raise HTTPException(status_code=429, detail="Troppi tentativi. Riprova tra qualche minuto.")

    h = _hash_token(token)
    tok = await db.quote_public_tokens.find_one({"token_hash": h})
    if not tok:
        await _log("token_invalid", result="denied", reason="not_found")
        raise HTTPException(status_code=404, detail="Il collegamento non è valido o non è più disponibile.")

    if tok["status"] == "revoked":
        await _log("token_revoked", result="denied", reason=tok.get("revocation_reason"), quote_id=tok["quote_id"], token_id=tok["_id"])
        raise HTTPException(status_code=404, detail="Il collegamento non è valido o non è più disponibile.")
    if tok["status"] == "invalidated":
        await _log("token_invalid", result="denied", reason="superseded", quote_id=tok["quote_id"], token_id=tok["_id"])
        raise HTTPException(status_code=410, detail="Questa revisione è stata sostituita da una versione più recente.")

    # Expiry
    now = datetime.now(timezone.utc)
    exp = tok.get("expires_at")
    if exp:
        exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00")) if isinstance(exp, str) else exp
        if exp_dt < now:
            await _log("token_expired", result="denied", quote_id=tok["quote_id"], token_id=tok["_id"])
            await db.quote_public_tokens.update_one({"_id": tok["_id"]}, {"$set": {"status": "expired"}})
            raise HTTPException(status_code=410, detail="Il collegamento è scaduto. Contatta il tuo consulente per ricevere un nuovo accesso.")

    # Max accesses
    if tok.get("maximum_accesses") and tok.get("access_count", 0) >= tok["maximum_accesses"]:
        await _log("token_expired", result="denied", reason="max_accesses", quote_id=tok["quote_id"], token_id=tok["_id"])
        raise HTTPException(status_code=410, detail="Il collegamento non è più disponibile.")

    # Load quote & pdf
    quote = await db.quotes.find_one({"_id": tok["quote_id"], "tenant_id": tok["tenant_id"], "deleted_at": None})
    if not quote:
        await _log("token_invalid", result="denied", reason="quote_missing", token_id=tok["_id"])
        raise HTTPException(status_code=404, detail="Il collegamento non è valido o non è più disponibile.")
    if quote.get("quote_status") in ("cancelled",):
        await _log("token_invalid", result="denied", reason="quote_cancelled", token_id=tok["_id"], quote_id=quote["_id"])
        raise HTTPException(status_code=410, detail="Il preventivo non è più disponibile.")

    pdf = await db.quote_pdfs.find_one({"_id": tok["quote_pdf_id"], "tenant_id": tok["tenant_id"]})
    if not pdf or pdf.get("invalidated_at"):
        await _log("token_invalid", result="denied", reason="pdf_invalidated", token_id=tok["_id"], quote_id=quote["_id"])
        raise HTTPException(status_code=410, detail="Il preventivo non è più disponibile.")

    # Update access counters idempotently for view event
    await db.quote_public_tokens.update_one(
        {"_id": tok["_id"]},
        {"$set": {"last_access_at": now.isoformat()},
         "$inc": {"access_count": 1}},
    )
    # First-view: bump quote status from sent → viewed (idempotent)
    if quote.get("quote_status") == "sent":
        await db.quotes.update_one({"_id": quote["_id"]}, {"$set": {"quote_status": "viewed", "viewed_at": now.isoformat()}, "$inc": {"version": 1}})
        await record_activity(
            tenant_id=tok["tenant_id"], type="quote_viewed_by_customer",
            subject=f"Preventivo {quote.get('number')} visualizzato dal cliente",
            quote_id=quote["_id"], user_id=None, user_email=None,
            meta={"token_id": tok["_id"], "ip_hash": ip_hash},
        )
    await _log(log_event, quote_id=quote["_id"], revision=tok["quote_revision"], token_id=tok["_id"])
    # Set tenant_id on the log we just wrote
    await db.public_access_log.update_many({"token_id": tok["_id"], "tenant_id": None}, {"$set": {"tenant_id": tok["tenant_id"]}})

    return tok, quote, pdf


def _security_headers() -> dict:
    return {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "X-Robots-Tag": "noindex, nofollow, noarchive, nosnippet",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "SAMEORIGIN",
    }


@public_router.get("/quotes/{token}")
async def public_get_quote(token: str, request: Request, response: Response):
    tok, quote, pdf = await _resolve_token(token, request, log_event="quote_viewed")
    db = get_db()
    company = await db.companies.find_one({"_id": tok["tenant_id"]})
    company = company or {}
    snapshot = pdf.get("snapshot", {})
    snap_q = snapshot.get("quote", {})
    snap_c = snapshot.get("company", {})

    # Determine expired / superseded
    is_expired = False
    vu_raw = snap_q.get("valid_until")
    if vu_raw:
        try:
            if isinstance(vu_raw, str):
                s = vu_raw.replace("Z", "+00:00")
                vu = datetime.fromisoformat(s)
            else:
                vu = vu_raw
            # Normalize to timezone-aware (assume UTC if naive)
            if vu.tzinfo is None:
                vu = vu.replace(tzinfo=timezone.utc)
            is_expired = vu < datetime.now(timezone.utc)
        except Exception:
            pass
    is_superseded = not (quote.get("is_current", True))
    watermark = pdf.get("watermark") or ("SUPERATO" if is_superseded else None)

    def _iso(v):
        if v is None: return None
        if hasattr(v, "isoformat"): return v.isoformat()
        return str(v)

    # Payment terms display
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
        quote_status=quote.get("quote_status"),
        payment_terms_display=payment_display,
        allowed_actions=[a for a in (tok.get("allowed_actions") or []) if a in ("view", "download")],
        watermark=watermark,
        has_pdf=True,
    )
    for k, v in _security_headers().items(): response.headers[k] = v
    return resp


@public_router.get("/quotes/{token}/pdf")
async def public_get_pdf(token: str, request: Request):
    tok, quote, pdf = await _resolve_token(token, request, log_event="pdf_downloaded")
    if "download" not in (tok.get("allowed_actions") or []):
        raise HTTPException(status_code=403, detail="Download non consentito per questo link")
    try:
        pdf_bytes = await _fetch_pdf_bytes(pdf)
    except HTTPException as e:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail="Documento temporaneamente non disponibile")
    headers = _security_headers()
    headers["Content-Disposition"] = f'inline; filename="{pdf.get("filename","preventivo.pdf")}"'
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


# ---------- Automatic invalidation hook on new revision ----------
async def invalidate_tokens_for_previous_revisions(tenant_id: str, quote_id: str, exclude_pdf_id: Optional[str] = None):
    """Call after creating a new revision → invalidates active tokens for old revisions."""
    db = get_db()
    q = {"tenant_id": tenant_id, "quote_id": quote_id, "status": "active"}
    if exclude_pdf_id:
        q["quote_pdf_id"] = {"$ne": exclude_pdf_id}
    now = datetime.now(timezone.utc).isoformat()
    await db.quote_public_tokens.update_many(q, {"$set": {"status": "invalidated", "revoked_at": now,
                                                            "revocation_reason": "superseded_by_new_revision"}})


# ---------- Access logs (admin) ----------
@admin_router.get("/quotes/{qid}/public-access-logs")
async def get_access_logs(qid: str, limit: int = 50,
                          user: dict = Depends(require_permission("quotes.public_access_logs.view"))):
    db = get_db()
    docs = await db.public_access_log.find(
        {"quote_id": qid, "tenant_id": user["tenant_id"]}
    ).sort("created_at", -1).limit(min(limit, 200)).to_list(limit)
    return {"items": [from_mongo(d) for d in docs]}
