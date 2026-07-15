"""Roles & Permissions CRUD."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models import Role, RoleCreate, RoleUpdate, new_id
from app.mongo_utils import to_mongo, from_mongo
from app.services.audit import record_audit
from app.permissions import PERMISSION_CATALOG

roles_router = APIRouter(prefix="/roles", tags=["roles"])
permissions_router = APIRouter(prefix="/permissions", tags=["permissions"])


def _strip(d: dict) -> dict:
    d = from_mongo(d)
    return d


@permissions_router.get("")
async def list_permissions(user: dict = Depends(require_permission("roles.view"))):
    """Return permission catalog grouped by module."""
    modules: dict[str, list[dict]] = {}
    for key, module, action, desc in PERMISSION_CATALOG:
        modules.setdefault(module, []).append({
            "key": key, "module": module, "action": action, "description": desc,
        })
    return {"modules": [{"module": m, "permissions": items} for m, items in modules.items()]}


@roles_router.get("")
async def list_roles(user: dict = Depends(require_permission("roles.view"))):
    db = get_db()
    docs = await db.roles.find(
        {"tenant_id": user["tenant_id"], "deleted_at": None}
    ).sort("name", 1).to_list(500)
    return {"items": [_strip(d) for d in docs]}


@roles_router.get("/{role_id}")
async def get_role(role_id: str, user: dict = Depends(require_permission("roles.view"))):
    db = get_db()
    doc = await db.roles.find_one({"_id": role_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Ruolo non trovato")
    return _strip(doc)


@roles_router.post("")
async def create_role(
    body: RoleCreate, request: Request,
    user: dict = Depends(require_permission("roles.manage")),
):
    db = get_db()
    all_keys = {k for (k, *_r) in PERMISSION_CATALOG}
    bad = [k for k in body.permission_keys if k not in all_keys]
    if bad:
        raise HTTPException(status_code=400, detail=f"Permessi non validi: {bad}")
    r = Role(
        id=new_id(),
        tenant_id=user["tenant_id"],
        name=body.name,
        description=body.description,
        permission_keys=body.permission_keys,
        is_system=False,
        created_by=user["id"], updated_by=user["id"],
    )
    await db.roles.insert_one(to_mongo(r.model_dump(by_alias=True)))
    await record_audit(
        action="roles.create", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="role", entity_id=r.id, after=r.model_dump(by_alias=True),
    )
    return _strip(await db.roles.find_one({"_id": r.id}))


@roles_router.patch("/{role_id}")
async def update_role(
    role_id: str, body: RoleUpdate, request: Request,
    user: dict = Depends(require_permission("roles.manage")),
):
    db = get_db()
    doc = await db.roles.find_one({"_id": role_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Ruolo non trovato")
    if doc.get("is_system") and body.permission_keys is not None and doc["name"] in ("Super Admin", "Admin Azienda"):
        # protect system admin roles from having all perms removed
        if not body.permission_keys:
            raise HTTPException(status_code=400, detail="Non è consentito svuotare i permessi di un ruolo di sistema critico")

    if body.permission_keys is not None:
        all_keys = {k for (k, *_r) in PERMISSION_CATALOG}
        bad = [k for k in body.permission_keys if k not in all_keys]
        if bad:
            raise HTTPException(status_code=400, detail=f"Permessi non validi: {bad}")

    update: dict = {"updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user["id"]}
    for k in ("name", "description", "permission_keys"):
        v = getattr(body, k)
        if v is not None:
            update[k] = v
    await db.roles.update_one({"_id": role_id}, {"$set": update})
    await record_audit(
        action="roles.update", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="role", entity_id=role_id,
        before={k: doc.get(k) for k in update if k in doc}, after=update,
    )
    return _strip(await db.roles.find_one({"_id": role_id}))


@roles_router.delete("/{role_id}")
async def delete_role(
    role_id: str, request: Request,
    user: dict = Depends(require_permission("roles.manage")),
):
    db = get_db()
    doc = await db.roles.find_one({"_id": role_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Ruolo non trovato")
    if doc.get("is_system"):
        raise HTTPException(status_code=400, detail="Impossibile eliminare un ruolo di sistema")
    # Check users using it
    in_use = await db.users.count_documents({"role_ids": role_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if in_use > 0:
        raise HTTPException(status_code=400, detail=f"Ruolo in uso da {in_use} utenti")
    now = datetime.now(timezone.utc).isoformat()
    await db.roles.update_one({"_id": role_id}, {"$set": {"deleted_at": now, "updated_at": now, "updated_by": user["id"]}})
    await record_audit(
        action="roles.delete", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="role", entity_id=role_id,
    )
    return {"ok": True}
