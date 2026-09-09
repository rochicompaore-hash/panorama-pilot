"""Auth endpoints: login, logout, refresh, me, forgot/reset, invitation, change-password."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from app.config import settings
from app.db import get_db
from app.deps import get_current_user, get_client_ip, get_permission_keys_for_user
from app.security import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    decode_token, generate_secure_token, hash_token,
)
from app.models import (
    LoginRequest, LoginResponse, UserPublic, Session as SessionModel,
    ForgotPasswordRequest, ResetPasswordRequest, PasswordResetToken,
    ChangePasswordRequest, AcceptInvitationRequest, new_id, utcnow,
)
from app.mongo_utils import to_mongo, from_mongo
from app.services.audit import record_audit
from app.services.email import send_email, render_password_reset
from app.services.auth_helpers import (
    to_public_user, check_brute_force, record_failed_login, clear_failed_login,
    create_login_session, upsert_user_from_invitation,
)
import jwt

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    response.set_cookie(
        "access_token", access, httponly=True, secure=False, samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, path="/",
    )
    response.set_cookie(
        "refresh_token", refresh, httponly=True, secure=False, samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


def _to_public(user: dict) -> UserPublic:
    return to_public_user(user)


async def _audit_login_failure(db, email: str, ip: str, user_agent: str | None,
                                user_doc: dict | None, reason: str) -> None:
    await record_audit(
        action="auth.login_failed",
        tenant_id=(user_doc or {}).get("tenant_id"),
        user_id=(user_doc or {}).get("_id"),
        user_email=email, ip=ip, user_agent=user_agent,
        meta={"reason": reason},
    )


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request, response: Response):
    db = get_db()
    ip = get_client_ip(request)
    email = body.email.lower().strip()
    # Lock per account (email) e non per IP: gli IP di ingresso variano (proxy/ingress) e un attaccante
    # con IP rotanti aggirerebbe il lock. L'IP resta tracciato nell'audit.
    identifier = f"acct:{email}"
    ua = request.headers.get("user-agent")

    wait = await check_brute_force(db, identifier, settings)
    if wait is not None:
        raise HTTPException(
            status_code=429,
            detail=f"Troppi tentativi. Riprova tra {wait}s.",
        )

    user_doc = await db.users.find_one({"email": email, "deleted_at": None})
    is_valid_user = bool(
        user_doc and user_doc.get("is_active", True) and user_doc.get("password_hash")
    )
    if not is_valid_user:
        await record_failed_login(db, identifier, settings)
        await _audit_login_failure(db, email, ip, ua, user_doc, "user_not_found_or_inactive")
        raise HTTPException(status_code=401, detail="Credenziali non valide")

    if not verify_password(body.password, user_doc["password_hash"]):
        await record_failed_login(db, identifier, settings)
        await _audit_login_failure(db, email, ip, ua, user_doc, "bad_password")
        raise HTTPException(status_code=401, detail="Credenziali non valide")

    await clear_failed_login(db, identifier)
    access, refresh = await create_login_session(db, user_doc, ip, ua, settings)
    await record_audit(
        action="auth.login", tenant_id=user_doc["tenant_id"],
        user_id=user_doc["_id"], user_email=email, ip=ip, user_agent=ua,
    )

    _set_auth_cookies(response, access, refresh)
    user_doc = from_mongo(user_doc)
    return LoginResponse(
        access_token=access, refresh_token=refresh,
        user=_to_public(user_doc),
        must_change_password=user_doc.get("must_change_password", False),
    )


class RefreshRequest(BaseModel):
    refresh_token: Optional[str] = None


@router.post("/refresh")
async def refresh_token(body: RefreshRequest, request: Request, response: Response):
    db = get_db()
    token = request.cookies.get("refresh_token") or body.refresh_token
    if not token:
        raise HTTPException(status_code=401, detail="Refresh token mancante")
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token scaduto")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Refresh token non valido")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Tipo token non valido")
    session = await db.sessions.find_one({"_id": payload.get("sid")})
    if not session or session.get("revoked_at"):
        raise HTTPException(status_code=401, detail="Sessione revocata")
    if session.get("refresh_token_hash") != hash_token(token):
        # Token reuse detected → revoke all sessions of user
        await db.sessions.update_many(
            {"user_id": payload["sub"], "revoked_at": None},
            {"$set": {"revoked_at": datetime.now(timezone.utc).isoformat()}},
        )
        await record_audit(
            action="auth.refresh_reuse_detected", tenant_id=payload.get("tenant_id"),
            user_id=payload["sub"], meta={"reason": "token_reuse"},
        )
        raise HTTPException(status_code=401, detail="Token compromesso: sessione revocata")

    user = await db.users.find_one({"_id": payload["sub"], "deleted_at": None})
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="Utente non attivo")

    # Rotate refresh token
    new_refresh = create_refresh_token(user["_id"], user["tenant_id"], session["_id"])
    new_access = create_access_token(user["_id"], user["tenant_id"], user.get("is_superadmin", False))
    await db.sessions.update_one(
        {"_id": session["_id"]},
        {"$set": {
            "refresh_token_hash": hash_token(new_refresh),
            "last_used_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    _set_auth_cookies(response, new_access, new_refresh)
    return {"access_token": new_access, "refresh_token": new_refresh, "token_type": "bearer"}


@router.post("/logout")
async def logout(request: Request, response: Response, user: dict = Depends(get_current_user)):
    db = get_db()
    token = request.cookies.get("refresh_token")
    if token:
        try:
            payload = decode_token(token)
            await db.sessions.update_one(
                {"_id": payload.get("sid")},
                {"$set": {"revoked_at": datetime.now(timezone.utc).isoformat()}},
            )
        except Exception:
            pass
    _clear_auth_cookies(response)
    await record_audit(
        action="auth.logout", tenant_id=user.get("tenant_id"),
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
    )
    return {"ok": True}


@router.post("/logout-all")
async def logout_all(request: Request, response: Response, user: dict = Depends(get_current_user)):
    db = get_db()
    await db.sessions.update_many(
        {"user_id": user["id"], "revoked_at": None},
        {"$set": {"revoked_at": datetime.now(timezone.utc).isoformat()}},
    )
    _clear_auth_cookies(response)
    await record_audit(
        action="auth.logout_all", tenant_id=user.get("tenant_id"),
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
    )
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    perms = await get_permission_keys_for_user(user)
    return {
        "user": _to_public(user).model_dump(),
        "permissions": perms,
    }


@router.post("/change-password")
async def change_password(body: ChangePasswordRequest, request: Request, user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await db.users.find_one({"_id": user["id"]})
    if not doc or not verify_password(body.current_password, doc.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Password attuale non corretta")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="La nuova password deve avere almeno 8 caratteri")
    await db.users.update_one(
        {"_id": user["id"]},
        {"$set": {
            "password_hash": hash_password(body.new_password),
            "must_change_password": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    # revoke all other sessions
    await db.sessions.update_many(
        {"user_id": user["id"], "revoked_at": None},
        {"$set": {"revoked_at": datetime.now(timezone.utc).isoformat()}},
    )
    await record_audit(
        action="auth.password_changed", tenant_id=user.get("tenant_id"),
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
    )
    return {"ok": True}


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, request: Request):
    db = get_db()
    email = body.email.lower().strip()
    user = await db.users.find_one({"email": email, "deleted_at": None})
    # Always return ok to prevent user enumeration
    if user:
        raw = generate_secure_token(48)
        prt = PasswordResetToken(
            id=new_id(),
            tenant_id=user["tenant_id"],
            user_id=user["_id"],
            token_hash=hash_token(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES),
        )
        await db.password_reset_tokens.insert_one(to_mongo(prt.model_dump(by_alias=True)))
        reset_url = f"{settings.APP_BASE_URL}/reset-password?token={raw}"
        subject, html, text = render_password_reset(reset_url)
        await send_email(email, subject, "password_reset", html, text)
        await record_audit(
            action="auth.password_reset_requested", tenant_id=user["tenant_id"],
            user_id=user["_id"], user_email=email, ip=get_client_ip(request),
        )
    return {"ok": True}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, request: Request):
    db = get_db()
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="La nuova password deve avere almeno 8 caratteri")
    th = hash_token(body.token)
    doc = await db.password_reset_tokens.find_one({"token_hash": th})
    if not doc or doc.get("used_at"):
        raise HTTPException(status_code=400, detail="Token non valido o già utilizzato")
    exp = doc["expires_at"]
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token scaduto")
    user = await db.users.find_one({"_id": doc["user_id"], "deleted_at": None})
    if not user:
        raise HTTPException(status_code=400, detail="Utente non trovato")
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "password_hash": hash_password(body.new_password),
            "must_change_password": False,
            "failed_login_attempts": 0,
            "locked_until": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    await db.password_reset_tokens.update_one(
        {"_id": doc["_id"]},
        {"$set": {"used_at": datetime.now(timezone.utc).isoformat()}},
    )
    # revoke all sessions
    await db.sessions.update_many(
        {"user_id": user["_id"], "revoked_at": None},
        {"$set": {"revoked_at": datetime.now(timezone.utc).isoformat()}},
    )
    await record_audit(
        action="auth.password_reset_completed", tenant_id=user["tenant_id"],
        user_id=user["_id"], user_email=user["email"], ip=get_client_ip(request),
    )
    return {"ok": True}


def _validate_invitation_or_raise(inv: dict | None) -> None:
    """Return None if the invitation is fresh & unused; raise 400 otherwise."""
    if not inv or inv.get("accepted_at"):
        raise HTTPException(status_code=400, detail="Invito non valido o già utilizzato")
    exp = inv["expires_at"]
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invito scaduto")


async def _revoke_sessions_after_owner_activation(db, inv: dict, user_id: str) -> None:
    if inv.get("kind") != "platform_owner_activation":
        return
    await db.sessions.update_many(
        {"user_id": user_id},
        {"$set": {"revoked_at": datetime.now(timezone.utc).isoformat()}},
    )


@router.post("/accept-invitation")
async def accept_invitation(body: AcceptInvitationRequest, request: Request):
    db = get_db()
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="La password deve avere almeno 8 caratteri")
    inv = await db.invitations.find_one({"token_hash": hash_token(body.token)})
    _validate_invitation_or_raise(inv)

    user_id = await upsert_user_from_invitation(
        db, inv, body.password, body.first_name, body.last_name,
    )
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.invitations.update_one(
        {"_id": inv["_id"]},
        {"$set": {"accepted_at": now_iso, "consumed_at": now_iso},
         "$unset": {"debug_raw_token": ""}},
    )
    await _revoke_sessions_after_owner_activation(db, inv, user_id)
    await record_audit(
        action="auth.invitation_accepted", tenant_id=inv["tenant_id"],
        user_id=user_id, user_email=inv["email"].lower().strip(),
        ip=get_client_ip(request),
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Emergent-managed Google sign-in (msg 405)
# REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
# Il redirect è deciso dal frontend con window.location.origin; qui si scambia solo il session_id.
# Policy fail-closed: l'identità Google deve corrispondere a un utente app esistente (email o
# google_login_emails) — nessun auto-provisioning in un tenant (RBAC / tenant isolation).
# ---------------------------------------------------------------------------
EMERGENT_SESSION_DATA_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"


class GoogleSessionRequest(BaseModel):
    session_id: str


@router.post("/google/session", response_model=LoginResponse)
async def google_session_exchange(body: GoogleSessionRequest, request: Request, response: Response):
    import httpx
    db = get_db()
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(EMERGENT_SESSION_DATA_URL, headers={"X-Session-ID": body.session_id})
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Servizio di autenticazione Google non raggiungibile")
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Sessione Google non valida o scaduta")
    data = r.json()
    email = (data.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(status_code=401, detail="Identità Google priva di email")

    user_doc = await db.users.find_one({
        "deleted_at": None,
        "$or": [{"email": email}, {"google_login_emails": email}],
    })
    if not user_doc or not user_doc.get("is_active", True):
        await _audit_login_failure(db, email, ip, ua, user_doc, "google_account_not_linked")
        raise HTTPException(status_code=403, detail={
            "code": "GOOGLE_ACCOUNT_NOT_LINKED",
            "message": "Questo account Google non è collegato a nessun utente della piattaforma. Chiedi all'amministratore di collegarlo.",
        })

    now = datetime.now(timezone.utc)
    await db.user_sessions.insert_one({
        "_id": f"gs_{now.timestamp():.0f}_{user_doc['_id'][:8]}",
        "user_id": user_doc["_id"], "tenant_id": user_doc["tenant_id"],
        "provider": "google_emergent", "google_sub": data.get("id"), "google_email": email,
        "session_token": data.get("session_token"),
        "expires_at": now + timedelta(days=7), "created_at": now, "ip": ip, "user_agent": ua,
    })
    await db.users.update_one({"_id": user_doc["_id"]}, {"$set": {
        "google_last_login_at": now.isoformat(), "google_picture": data.get("picture"),
    }})
    access, refresh = await create_login_session(db, user_doc, ip, ua, settings)
    await record_audit(action="auth.login_google", tenant_id=user_doc["tenant_id"], user_id=user_doc["_id"],
                       user_email=user_doc["email"], ip=ip, user_agent=ua, after={"google_email": email})
    _set_auth_cookies(response, access, refresh)
    if data.get("session_token"):
        response.set_cookie("session_token", data["session_token"], httponly=True, secure=True,
                            samesite="none", path="/", max_age=7 * 24 * 3600)
    user_doc = from_mongo(user_doc)
    return LoginResponse(access_token=access, refresh_token=refresh, user=_to_public(user_doc),
                         must_change_password=False)
