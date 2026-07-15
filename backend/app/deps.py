"""FastAPI dependencies: authentication, RBAC, request context."""
from __future__ import annotations
from typing import Optional, Callable, List
from fastapi import Depends, HTTPException, Request, status
import jwt
from app.security import decode_token
from app.db import get_db
from app.mongo_utils import from_mongo


def get_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _extract_token(request: Request) -> Optional[str]:
    token = request.cookies.get("access_token")
    if token:
        return token
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]
    return None


async def get_current_user(request: Request) -> dict:
    token = await _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Non autenticato")
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token scaduto")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token non valido")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Tipo di token non valido")
    db = get_db()
    user = await db.users.find_one({"_id": payload["sub"], "deleted_at": None})
    if not user:
        raise HTTPException(status_code=401, detail="Utente non trovato")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Utente disattivato")
    user = from_mongo(user)
    user.pop("password_hash", None)
    return user


async def get_permission_keys_for_user(user: dict) -> List[str]:
    """Return effective permission keys for a user (union of role perms)."""
    if user.get("is_superadmin"):
        return ["*"]
    db = get_db()
    role_ids = user.get("role_ids") or []
    if not role_ids:
        return []
    roles = await db.roles.find({"_id": {"$in": role_ids}, "deleted_at": None}).to_list(100)
    keys: set[str] = set()
    for r in roles:
        for k in r.get("permission_keys") or []:
            keys.add(k)
    return sorted(keys)


def require_permission(*required: str) -> Callable:
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if user.get("is_superadmin"):
            return user
        perms = await get_permission_keys_for_user(user)
        pset = set(perms)
        if "*" in pset:
            return user
        for r in required:
            if r not in pset:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permesso mancante: {r}",
                )
        return user
    return dep


def require_any_permission(*required: str) -> Callable:
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if user.get("is_superadmin"):
            return user
        perms = await get_permission_keys_for_user(user)
        pset = set(perms)
        if "*" in pset:
            return user
        if any(r in pset for r in required):
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permesso mancante (uno tra): {', '.join(required)}",
        )
    return dep
