"""M3.3.4 — OTP generation / verification.

Security:
- OTP is never stored in plain text. We keep sha256(salt + otp).
- Debug (plain) copy is only kept when APP_ENV is dev/test AND OTP_DEBUG_ENABLED.
- A new OTP for the same token supersedes any pending prior OTP.
"""
from __future__ import annotations
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from app.config import settings, is_dev_or_test
from app.db import get_db
from app.models import new_id
from app.models_signature import QuoteOtpRequest
from app.mongo_utils import to_mongo, from_mongo


def _hash_email(email: str) -> str:
    return hashlib.sha256((email or "").strip().lower().encode()).hexdigest()[:24]


def mask_email(email: str) -> str:
    """Return a friendly masked version like a***@example.com (never leaks full identity)."""
    e = (email or "").strip()
    if "@" not in e:
        return "***"
    local, domain = e.split("@", 1)
    if not local:
        return f"***@{domain}"
    if len(local) <= 2:
        return f"{local[0]}***@{domain}"
    return f"{local[0]}***{local[-1]}@{domain}"


def _generate_code() -> str:
    n = max(4, min(int(settings.OTP_LENGTH), 8))
    # secrets.randbelow ensures uniform distribution
    return f"{secrets.randbelow(10**n):0{n}d}"


def _hash_otp(salt: str, code: str) -> str:
    return hashlib.sha256(f"{salt}|{code}".encode()).hexdigest()


async def create_otp(
    *, token_id: str, quote_id: str, email: str,
    ip_hash: Optional[str] = None, user_agent: Optional[str] = None,
) -> Tuple[QuoteOtpRequest, str]:
    """Generate a new OTP, invalidate previous pending ones for this token, persist.

    Returns (persisted QuoteOtpRequest, raw_code). The raw_code is used ONLY for
    the mock delivery / debug-endpoint; NEVER returned to the public caller.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    # Invalidate any pending OTPs for the same token (idempotency: newer wins)
    await db.quote_otp_requests.update_many(
        {"token_id": token_id, "status": "pending"},
        {"$set": {"status": "superseded", "updated_at": now.isoformat()}},
    )
    code = _generate_code()
    salt = secrets.token_urlsafe(16)
    otp_hash = _hash_otp(salt, code)
    debug_plain = code if (is_dev_or_test() and settings.OTP_DEBUG_ENABLED) else None
    req = QuoteOtpRequest(
        id=new_id(),
        tenant_id=None,  # populated by caller once we resolve token
        token_id=token_id,
        quote_id=quote_id,
        channel="email",
        recipient_hash=_hash_email(email),
        recipient_masked=mask_email(email),
        otp_hash=otp_hash,
        otp_salt=salt,
        expires_at=now + timedelta(seconds=settings.OTP_TTL_SECONDS),
        attempts=0,
        max_attempts=settings.RATE_LIMIT_OTP_VERIFY_MAX_ATTEMPTS,
        status="pending",
        ip_hash=ip_hash,
        user_agent=(user_agent or "")[:200],
        debug_code_plain=debug_plain,
    )
    return req, code


async def verify_otp(request_id: str, code: str) -> Tuple[bool, str, Optional[dict]]:
    """Try to verify code against pending OTP.

    Returns (ok, reason, otp_doc). Reasons: ok | not_found | expired | too_many_attempts | invalid_code
    Increments attempts on failure. On success sets status=verified.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = await db.quote_otp_requests.find_one({"_id": request_id})
    if not doc:
        return False, "not_found", None
    if doc.get("status") != "pending":
        return False, "not_found", doc
    # Expiry
    exp = doc.get("expires_at")
    if isinstance(exp, str):
        try:
            exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
        except Exception:
            exp_dt = None
    else:
        exp_dt = exp
    if exp_dt and exp_dt < now:
        await db.quote_otp_requests.update_one({"_id": request_id}, {"$set": {"status": "expired", "updated_at": now.isoformat()}})
        return False, "expired", doc
    # Attempts
    max_attempts = int(doc.get("max_attempts") or settings.RATE_LIMIT_OTP_VERIFY_MAX_ATTEMPTS)
    if int(doc.get("attempts") or 0) >= max_attempts:
        await db.quote_otp_requests.update_one({"_id": request_id}, {"$set": {"status": "failed", "updated_at": now.isoformat()}})
        return False, "too_many_attempts", doc
    # Compare
    expected = doc.get("otp_hash")
    salt = doc.get("otp_salt") or ""
    provided = _hash_otp(salt, (code or "").strip())
    if not hmac.compare_digest(expected, provided):
        new_attempts = int(doc.get("attempts") or 0) + 1
        update = {"attempts": new_attempts, "updated_at": now.isoformat()}
        if new_attempts >= max_attempts:
            update["status"] = "failed"
        await db.quote_otp_requests.update_one({"_id": request_id}, {"$set": update})
        return False, "invalid_code", {**doc, **update}
    # Success
    await db.quote_otp_requests.update_one(
        {"_id": request_id},
        {"$set": {"status": "verified", "verified_at": now.isoformat(), "updated_at": now.isoformat()},
         "$unset": {"debug_code_plain": ""}},
    )
    return True, "ok", doc


async def build_and_send(*, tenant_id: str, token_id: str, quote_id: str, email: str,
                          ip_hash: Optional[str], user_agent: Optional[str],
                          quote_number: str, company_name: str) -> QuoteOtpRequest:
    """Persist a new OTP and send it via the (mock) email provider.

    Delivery failures are logged but do NOT reveal internal state to the public caller.
    """
    from app.db import get_db
    from app.services.email import send_email
    db = get_db()
    req, raw_code = await create_otp(token_id=token_id, quote_id=quote_id, email=email,
                                     ip_hash=ip_hash, user_agent=user_agent)
    req.tenant_id = tenant_id
    doc = to_mongo(req.model_dump(by_alias=True))
    await db.quote_otp_requests.insert_one(doc)
    # Send email
    subject = f"Codice di verifica per il preventivo {quote_number}"
    ttl_min = max(1, settings.OTP_TTL_SECONDS // 60)
    text = (
        f"Il tuo codice di verifica per il preventivo {quote_number} è:\n\n"
        f"    {raw_code}\n\n"
        f"Valido {ttl_min} minuti. Non condividere questo codice con nessuno.\n"
        f"Se non hai richiesto questa verifica, ignora questa email.\n"
    )
    html = f"""<div style='font-family:system-ui,sans-serif'>
      <h2 style='margin:0 0 8px 0'>Codice di verifica</h2>
      <p>Per confermare l'accettazione del preventivo <b>{quote_number}</b> di {company_name},
         inserisci il codice qui sotto:</p>
      <div style='font-size:28px;font-weight:900;letter-spacing:6px;padding:14px 20px;background:#0F1720;color:#fff;display:inline-block;font-family:ui-monospace,Consolas,monospace'>{raw_code}</div>
      <p style='color:#71717A;font-size:12px;margin-top:16px'>Valido {ttl_min} minuti. Non condividere questo codice.</p>
    </div>"""
    try:
        await send_email(to=email, subject=subject, template="quote_otp", html=html, text=text)
    except Exception:
        # Non-blocking; provider itself never raises (see services/email.py)
        pass
    return req
