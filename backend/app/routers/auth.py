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
    return UserPublic(**{k: user.get(k) for k in UserPublic.model_fields.keys()})


async def _check_brute_force(db, identifier: str) -> None:
    doc = await db.login_attempts.find_one({"identifier": identifier})
    if not doc:
        return
    lu = doc.get("locked_until")
    if lu:
        if isinstance(lu, str):
            lu = datetime.fromisoformat(lu)
        if lu > datetime.now(timezone.utc):
            wait_s = int((lu - datetime.now(timezone.utc)).total_seconds())
            raise HTTPException(
                status_code=429,
                detail=f"Troppi tentativi. Riprova tra {max(wait_s, 1)}s.",
            )


async def _record_failed(db, identifier: str) -> None:
    now = datetime.now(timezone.utc)
    doc = await db.login_attempts.find_one({"identifier": identifier})
    attempts = (doc or {}).get("attempts", 0) + 1
    update = {"identifier": identifier, "attempts": attempts, "last_at": now.isoformat()}
    if attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
        update["locked_until"] = (now + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)).isoformat()
        update["attempts"] = 0
    await db.login_attempts.update_one(
        {"identifier": identifier}, {"$set": update}, upsert=True,
    )


async def _clear_failed(db, identifier: str) -> None:
    await db.login_attempts.delete_one({"identifier": identifier})


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request, response: Response):
    db = get_db()
    ip = get_client_ip(request)
    email = body.email.lower().strip()
    identifier = f"{ip}:{email}"

    await _check_brute_force(db, identifier)

    user_doc = await db.users.find_one({"email": email, "deleted_at": None})
    if not user_doc or not user_doc.get("is_active", True) or not user_doc.get("password_hash"):
        await _record_failed(db, identifier)
        await record_audit(
            action="auth.login_failed", tenant_id=user_doc.get("tenant_id") if user_doc else None,
            user_email=email, ip=ip, user_agent=request.headers.get("user-agent"),
            meta={"reason": "user_not_found_or_inactive"},
        )
        raise HTTPException(status_code=401, detail="Credenziali non valide")

    if not verify_password(body.password, user_doc["password_hash"]):
        await _record_failed(db, identifier)
        await record_audit(
            action="auth.login_failed", tenant_id=user_doc.get("tenant_id"),
            user_id=user_doc["_id"], user_email=email, ip=ip,
            user_agent=request.headers.get("user-agent"),
            meta={"reason": "bad_password"},
        )
        raise HTTPException(status_code=401, detail="Credenziali non valide")

    await _clear_failed(db, identifier)

    # Create session with refresh token
    session_id = new_id()
    refresh = create_refresh_token(user_doc["_id"], user_doc["tenant_id"], session_id)
    access = create_access_token(user_doc["_id"], user_doc["tenant_id"], user_doc.get("is_superadmin", False))
    session = SessionModel(
        id=session_id,
        tenant_id=user_doc["tenant_id"],
        user_id=user_doc["_id"],
        refresh_token_hash=hash_token(refresh),
        ip=ip,
        user_agent=request.headers.get("user-agent"),
        device_info=request.headers.get("user-agent"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    await db.sessions.insert_one(to_mongo(session.model_dump(by_alias=True)))
    await db.users.update_one(
        {"_id": user_doc["_id"]},
        {"$set": {"last_login_at": datetime.now(timezone.utc).isoformat()}},
    )
    await record_audit(
        action="auth.login", tenant_id=user_doc["tenant_id"],
        user_id=user_doc["_id"], user_email=email, ip=ip,
        user_agent=request.headers.get("user-agent"),
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


@router.post("/accept-invitation")
async def accept_invitation(body: AcceptInvitationRequest, request: Request):
    db = get_db()
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="La password deve avere almeno 8 caratteri")
    th = hash_token(body.token)
    inv = await db.invitations.find_one({"token_hash": th})
    if not inv or inv.get("accepted_at"):
        raise HTTPException(status_code=400, detail="Invito non valido o già utilizzato")
    exp = inv["expires_at"]
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invito scaduto")

    email = inv["email"].lower().strip()
    existing = await db.users.find_one({"email": email})
    if existing:
        # link existing user: update password & activate
        await db.users.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "password_hash": hash_password(body.password),
                "role_ids": inv.get("role_ids", []),
                "is_active": True,
                "must_change_password": False,
                "first_name": body.first_name or existing.get("first_name"),
                "last_name": body.last_name or existing.get("last_name"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        user_id = existing["_id"]
    else:
        from app.models import User
        u = User(
            id=new_id(),
            tenant_id=inv["tenant_id"],
            email=email,
            password_hash=hash_password(body.password),
            role_ids=inv.get("role_ids", []),
            first_name=body.first_name,
            last_name=body.last_name,
            is_active=True,
            must_change_password=False,
        )
        await db.users.insert_one(to_mongo(u.model_dump(by_alias=True)))
        user_id = u.id
    await db.invitations.update_one(
        {"_id": inv["_id"]},
        {"$set": {"accepted_at": datetime.now(timezone.utc).isoformat(),
                   "consumed_at": datetime.now(timezone.utc).isoformat()},
         "$unset": {"debug_raw_token": ""}},
    )
    # Platform owner activation: revoke any pre-existing sessions for security
    if inv.get("kind") == "platform_owner_activation":
        await db.sessions.update_many(
            {"user_id": user_id},
            {"$set": {"revoked_at": datetime.now(timezone.utc).isoformat()}},
        )
    await record_audit(
        action="auth.invitation_accepted", tenant_id=inv["tenant_id"],
        user_id=user_id, user_email=email, ip=get_client_ip(request),
    )
    return {"ok": True}
