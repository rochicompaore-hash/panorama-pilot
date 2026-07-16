"""SaaS Platform router: piani, moduli, entitlement, dipendenze, utilizzo."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException

from app.db import get_db
from app.deps import get_current_user, require_permission
from app.mongo_utils import to_mongo, from_mongo
from app.models import utcnow, new_id
from app.models_saas import (
    SubscriptionModule, ModuleDependency,
    SubscriptionPlan, SubscriptionPlanCreate,
    TenantEntitlement, TenantEntitlementUpdate,
    UsageCounter, BillingEvent, MODULE_CODES,
)
from app.services.module_gating import evaluate_module, resolve_module_dependencies


router = APIRouter(prefix="/platform/saas", tags=["SaaS Platform"])


def _require_platform_owner(user: dict):
    if not (user.get("is_platform_owner") or user.get("is_superadmin")):
        raise HTTPException(403, "Solo Platform Owner")


# ---------- MODULES ----------
@router.get("/modules")
async def list_modules(user: dict = Depends(get_current_user)):
    db = get_db()
    docs = await db.subscription_modules.find({"deleted_at": None}).sort([("category", 1), ("code", 1)]).to_list(50)
    return {"items": [from_mongo(d) for d in docs]}


@router.get("/dependencies")
async def list_dependencies(user: dict = Depends(get_current_user)):
    db = get_db()
    docs = await db.module_dependencies.find({"deleted_at": None}).to_list(100)
    return {"items": [from_mongo(d) for d in docs]}


# ---------- PLANS ----------
@router.get("/plans")
async def list_plans(user: dict = Depends(get_current_user)):
    db = get_db()
    docs = await db.subscription_plans.find({"deleted_at": None, "active": True}).sort([("tier", 1)]).to_list(50)
    return {"items": [from_mongo(d) for d in docs]}


@router.post("/plans")
async def create_plan(payload: SubscriptionPlanCreate, user: dict = Depends(get_current_user)):
    _require_platform_owner(user)
    db = get_db()
    exists = await db.subscription_plans.find_one({"code": payload.code, "deleted_at": None})
    if exists:
        raise HTTPException(409, f"Piano '{payload.code}' esiste già")
    inst = SubscriptionPlan(**payload.model_dump(), is_demo=False, created_by=user["id"], updated_by=user["id"])
    await db.subscription_plans.insert_one(to_mongo(inst.model_dump(by_alias=True)))
    return inst.model_dump()


@router.patch("/plans/{pid}")
async def update_plan(pid: str, payload: dict, user: dict = Depends(get_current_user)):
    _require_platform_owner(user)
    db = get_db()
    updates = {k: v for k, v in payload.items() if k in {
        "name", "description", "included_module_codes", "max_users", "max_storage_mb",
        "max_legal_entities", "max_quotes_per_month", "monthly_price", "yearly_price",
        "trial_days", "active", "notes"
    }}
    updates["updated_at"] = utcnow().isoformat()
    updates["updated_by"] = user["id"]
    await db.subscription_plans.update_one({"_id": pid}, {"$set": updates})
    return from_mongo(await db.subscription_plans.find_one({"_id": pid}))


# ---------- TENANT ENTITLEMENT ----------
@router.get("/entitlements/{tenant_id}")
async def get_entitlement(tenant_id: str, user: dict = Depends(get_current_user)):
    if not (user.get("is_platform_owner") or user.get("is_superadmin")) and user["tenant_id"] != tenant_id:
        raise HTTPException(403, "Non autorizzato")
    db = get_db()
    ent = await db.tenant_entitlements.find_one({"tenant_id": tenant_id, "deleted_at": None}, sort=[("created_at", -1)])
    if not ent:
        return None
    return from_mongo(ent)


@router.get("/entitlements")
async def list_all_entitlements(user: dict = Depends(get_current_user)):
    _require_platform_owner(user)
    db = get_db()
    docs = await db.tenant_entitlements.find({"deleted_at": None}).sort([("created_at", -1)]).to_list(200)
    return {"items": [from_mongo(d) for d in docs]}


@router.post("/entitlements/{tenant_id}/assign-plan")
async def assign_plan(tenant_id: str, payload: dict, user: dict = Depends(get_current_user)):
    _require_platform_owner(user)
    db = get_db()
    plan_id = payload.get("plan_id")
    plan = await db.subscription_plans.find_one({"_id": plan_id, "deleted_at": None})
    if not plan:
        raise HTTPException(404, "Piano non trovato")
    # Verifica dipendenze
    included = list(plan.get("included_module_codes") or [])
    for m in included:
        missing = await resolve_module_dependencies(m, included)
        if missing:
            raise HTTPException(400,
                f"Modulo '{m}' richiede: {missing}. Aggiungi le dipendenze al piano prima di assegnarlo.")
    # Chiudi entitlement precedente (soft)
    prev = await db.tenant_entitlements.find_one({"tenant_id": tenant_id, "deleted_at": None},
                                                   sort=[("created_at", -1)])
    if prev:
        await db.tenant_entitlements.update_one({"_id": prev["_id"]},
            {"$set": {"deleted_at": utcnow().isoformat()}})
    trial_ends = None
    if plan.get("trial_days"):
        trial_ends = utcnow() + timedelta(days=int(plan["trial_days"]))
    inst = TenantEntitlement(
        tenant_id=tenant_id, plan_id=plan["_id"], plan_code=plan.get("code"),
        plan_snapshot_module_codes=included,
        module_states={m: ("trial" if trial_ends else "active") for m in included},
        trial_started_at=utcnow() if trial_ends else None,
        trial_ends_at=trial_ends,
        created_by=user["id"], updated_by=user["id"],
    )
    await db.tenant_entitlements.insert_one(to_mongo(inst.model_dump(by_alias=True)))
    # Billing event
    ev = BillingEvent(tenant_id=tenant_id, event_kind="subscription_created",
                      amount=plan.get("monthly_price") or 0, provider="internal",
                      payload={"plan_id": plan["_id"], "plan_code": plan.get("code")})
    await db.billing_events.insert_one(to_mongo(ev.model_dump(by_alias=True)))
    return inst.model_dump()


@router.patch("/entitlements/{tenant_id}")
async def update_entitlement(tenant_id: str, payload: TenantEntitlementUpdate,
                              user: dict = Depends(get_current_user)):
    _require_platform_owner(user)
    db = get_db()
    ent = await db.tenant_entitlements.find_one({"tenant_id": tenant_id, "deleted_at": None},
                                                  sort=[("created_at", -1)])
    if not ent:
        raise HTTPException(404, "Entitlement non trovato")
    updates = payload.model_dump(exclude_unset=True)
    updates["updated_at"] = utcnow().isoformat()
    updates["updated_by"] = user["id"]
    await db.tenant_entitlements.update_one({"_id": ent["_id"]}, {"$set": updates})
    return from_mongo(await db.tenant_entitlements.find_one({"_id": ent["_id"]}))


@router.post("/entitlements/{tenant_id}/modules/{module_code}/state")
async def set_module_state(tenant_id: str, module_code: str, payload: dict,
                            user: dict = Depends(get_current_user)):
    _require_platform_owner(user)
    if module_code not in MODULE_CODES:
        raise HTTPException(400, f"Modulo sconosciuto: {module_code}")
    new_state = payload.get("state")
    allowed = {"active", "trial", "grace_period", "read_only", "suspended", "expired", "disabled"}
    if new_state not in allowed:
        raise HTTPException(400, f"Stato non valido. Ammessi: {sorted(allowed)}")
    db = get_db()
    ent = await db.tenant_entitlements.find_one({"tenant_id": tenant_id, "deleted_at": None},
                                                  sort=[("created_at", -1)])
    if not ent:
        raise HTTPException(404, "Entitlement non trovato")
    # Controllo dipendenze per attivazione
    if new_state in ("active", "trial", "grace_period"):
        included = list(ent.get("plan_snapshot_module_codes") or [])
        if module_code not in included:
            included = included + [module_code]
        missing = await resolve_module_dependencies(module_code, included)
        if missing:
            raise HTTPException(400,
                f"Impossibile attivare '{module_code}': mancano dipendenze {missing}. "
                f"Attiva prima le dipendenze o conferma con override.")
    states = dict(ent.get("module_states") or {})
    states[module_code] = new_state
    incl = list(ent.get("plan_snapshot_module_codes") or [])
    if new_state in ("active", "trial") and module_code not in incl:
        incl.append(module_code)
    await db.tenant_entitlements.update_one({"_id": ent["_id"]},
        {"$set": {"module_states": states, "plan_snapshot_module_codes": incl,
                   "updated_at": utcnow().isoformat(), "updated_by": user["id"]}})
    ev = BillingEvent(tenant_id=tenant_id,
                      event_kind="module_added" if new_state == "active" else "suspended",
                      payload={"module": module_code, "new_state": new_state})
    await db.billing_events.insert_one(to_mongo(ev.model_dump(by_alias=True)))
    return {"ok": True, "state": new_state}


@router.get("/me/entitlement")
async def my_entitlement(user: dict = Depends(get_current_user)):
    db = get_db()
    ent = await db.tenant_entitlements.find_one({"tenant_id": user["tenant_id"], "deleted_at": None},
                                                  sort=[("created_at", -1)])
    if not ent:
        return {"tenant_id": user["tenant_id"], "plan_snapshot_module_codes": MODULE_CODES,
                "module_states": {m: "active" for m in MODULE_CODES},
                "note": "Nessun entitlement esplicito: tutti i moduli attivi (default)."}
    # Enrich con status effettivo
    ent = from_mongo(ent)
    effective = {}
    for m in MODULE_CODES:
        r = await evaluate_module(user["tenant_id"], m)
        effective[m] = {"state": r.state, "allow_read": r.allow_read, "allow_write": r.allow_write}
    ent["effective_states"] = effective
    return ent


@router.get("/me/module/{module_code}/status")
async def module_status(module_code: str, user: dict = Depends(get_current_user)):
    if module_code not in MODULE_CODES:
        raise HTTPException(400, "Modulo sconosciuto")
    r = await evaluate_module(user["tenant_id"], module_code)
    return r.model_dump()


# ---------- USAGE ----------
@router.get("/me/usage")
async def my_usage(user: dict = Depends(get_current_user)):
    db = get_db()
    tid = user["tenant_id"]
    users_count = await db.users.count_documents({"tenant_id": tid, "is_active": True, "deleted_at": None})
    entities_count = await db.legal_entities.count_documents({"tenant_id": tid, "deleted_at": None})
    quotes_count = await db.quotes.count_documents({"tenant_id": tid, "deleted_at": None})
    return {
        "users": users_count,
        "legal_entities": entities_count,
        "quotes_total": quotes_count,
    }
