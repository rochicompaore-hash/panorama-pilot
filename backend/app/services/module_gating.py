"""Module gating: middleware per bloccare endpoint se modulo SaaS non attivo.

Uso:
    @require_module("treasury")
    async def endpoint(user: dict = Depends(...)):
        ...

Comportamento:
- active/trial → read+write
- grace_period → read+write con avviso
- read_only → solo GET
- suspended/expired/disabled → blocca

I dati NON vengono mai eliminati alla disattivazione.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Callable, Optional
from fastapi import Depends, HTTPException, Request, status

from app.db import get_db
from app.deps import get_current_user
from app.mongo_utils import from_mongo
from app.models_saas import (
    ModuleGateResult, MODULE_CODES, EntitlementState,
)


DEFAULT_STATE_FOR_PLATFORM_OWNER = "active"


async def get_tenant_entitlement(tenant_id: str) -> Optional[dict]:
    db = get_db()
    ent = await db.tenant_entitlements.find_one(
        {"tenant_id": tenant_id, "deleted_at": None},
        sort=[("created_at", -1)],
    )
    return from_mongo(ent) if ent else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def evaluate_module(tenant_id: str, module_code: str) -> ModuleGateResult:
    """Determina lo stato attuale di un modulo per il tenant.

    Regole:
    - Se non c'è entitlement: modulo considerato 'active' (backward-compat con tenant esistenti).
    - Se plan_snapshot_module_codes contiene il modulo → default 'active'.
    - Se module_states ha un override → prevale.
    - Se expires_at superato → 'expired'.
    - Se grace_until >= now → 'grace_period'.
    """
    ent = await get_tenant_entitlement(tenant_id)
    if not ent:
        return ModuleGateResult(module_code=module_code, state="active",
                                allow_read=True, allow_write=True)
    override = (ent.get("module_states") or {}).get(module_code)
    included = (ent.get("plan_snapshot_module_codes") or [])
    state: EntitlementState = "active"
    if override:
        state = override  # type: ignore
    elif module_code not in included:
        state = "disabled"
    # Verifica scadenza
    expires = (ent.get("module_expires_at") or {}).get(module_code)
    grace = (ent.get("module_grace_until") or {}).get(module_code)
    now = _now().isoformat()
    if expires and expires < now:
        state = "expired"
        if grace and grace >= now:
            state = "grace_period"
    # Trial
    trial_ends = ent.get("trial_ends_at")
    if state == "trial" and trial_ends and str(trial_ends) < now:
        state = "expired"
    # Sospeso a livello tenant
    if ent.get("suspended_at"):
        state = "suspended"
    # Mappa comportamento
    if state in ("active", "trial", "grace_period"):
        return ModuleGateResult(module_code=module_code, state=state,
                                allow_read=True, allow_write=True,
                                message="grace_period" if state == "grace_period" else None)
    if state == "read_only":
        return ModuleGateResult(module_code=module_code, state="read_only",
                                allow_read=True, allow_write=False,
                                message="Modulo in sola lettura")
    # suspended, expired, disabled
    return ModuleGateResult(module_code=module_code, state=state,
                            allow_read=False, allow_write=False,
                            message=f"Modulo {module_code} non attivo ({state})")


def require_module(module_code: str, write: bool = False) -> Callable:
    """Dependency FastAPI per gating modulo."""
    async def dep(request: Request, user: dict = Depends(get_current_user)) -> dict:
        # Platform owner / superadmin bypass
        if user.get("is_platform_owner") or user.get("is_superadmin"):
            return user
        result = await evaluate_module(user["tenant_id"], module_code)
        method = request.method.upper()
        needs_write = write or method in ("POST", "PUT", "PATCH", "DELETE")
        if needs_write and not result.allow_write:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "module_not_active",
                    "module": module_code,
                    "state": result.state,
                    "message": result.message or f"Modulo {module_code} non attivo",
                },
            )
        if not needs_write and not result.allow_read:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "module_not_active",
                    "module": module_code,
                    "state": result.state,
                    "message": result.message or f"Modulo {module_code} non attivo",
                },
            )
        return user
    return dep


async def resolve_module_dependencies(module_code: str, included_codes: list[str]) -> list[str]:
    """Ritorna elenco dipendenze mancanti per attivare un modulo."""
    db = get_db()
    deps = await db.module_dependencies.find({"module_code": module_code, "deleted_at": None}).to_list(50)
    missing = []
    for d in deps:
        required = d.get("requires_module")
        if required and required not in included_codes:
            missing.append(required)
    return missing
