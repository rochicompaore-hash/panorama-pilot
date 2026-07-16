"""Legal Entities router — Multi-company base (Enerhia, Auxer, ...).

Ogni utente non-superadmin/platform-owner ha accesso solo alle legal entities
di cui è membro (LegalEntityMembership) oppure a tutte se ha role admin_azienda/super_admin.
"""
from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import get_db
from app.deps import get_current_user, require_permission, get_client_ip
from app.services.ops_common import list_docs, update_doc, soft_delete_doc
from app.mongo_utils import to_mongo, from_mongo
from app.models import utcnow, new_id
from app.models_multi_company import (
    LegalEntity, LegalEntityCreate, LegalEntityUpdate,
    LegalEntityMembership,
)


router = APIRouter(prefix="/legal-entities", tags=["Multi-Company"])


REQUIRED_FISCAL_FIELDS = ["vat_number", "tax_code", "pec"]


def _refresh_missing(le: dict) -> dict:
    missing = [f for f in REQUIRED_FISCAL_FIELDS if not le.get(f)]
    le["missing_fields"] = missing
    le["fiscal_operations_blocked"] = len(missing) > 0
    if not missing and le.get("le_status") == "to_complete":
        le["le_status"] = "active"
    return le


async def get_user_legal_entity_ids(user: dict) -> Optional[List[str]]:
    """Ritorna gli id LE di cui l'utente è membro. None → accesso a tutti."""
    if user.get("is_superadmin") or user.get("is_platform_owner"):
        return None
    # Admin tenant → accesso a tutti
    db = get_db()
    roles = await db.roles.find({"_id": {"$in": user.get("role_ids") or []}}).to_list(50)
    role_names = [r.get("name") for r in roles]
    if any(n in ("Super Admin", "Admin Azienda") for n in role_names):
        return None
    memberships = await db.legal_entity_memberships.find(
        {"tenant_id": user["tenant_id"], "user_id": user["id"],
         "active": True, "deleted_at": None}
    ).to_list(50)
    return [m["legal_entity_id"] for m in memberships]


async def user_can_access_entity(user: dict, legal_entity_id: str) -> bool:
    ids = await get_user_legal_entity_ids(user)
    return ids is None or legal_entity_id in ids


@router.get("")
async def list_entities(user: dict = Depends(require_permission("company.view"))):
    scoped = await get_user_legal_entity_ids(user)
    filters = {}
    if scoped is not None:
        filters["_id"] = {"$in": scoped}
    db = get_db()
    query = {"tenant_id": user["tenant_id"], "deleted_at": None, **filters}
    docs = await db.legal_entities.find(query).sort([("code", 1)]).to_list(50)
    return {"items": [_refresh_missing(from_mongo(d)) for d in docs]}


@router.post("")
async def create_entity(payload: LegalEntityCreate, request: Request,
                         user: dict = Depends(require_permission("company.edit"))):
    inst = LegalEntity(**payload.model_dump(), tenant_id=user["tenant_id"])
    inst.created_by = user["id"]; inst.updated_by = user["id"]
    inst.missing_fields = REQUIRED_FISCAL_FIELDS.copy()
    inst.fiscal_operations_blocked = True
    inst.le_status = "to_complete"
    db = get_db()
    await db.legal_entities.insert_one(to_mongo(inst.model_dump(by_alias=True)))
    return inst.model_dump()


@router.get("/{eid}")
async def get_entity(eid: str, user: dict = Depends(require_permission("company.view"))):
    if not await user_can_access_entity(user, eid):
        raise HTTPException(status_code=403, detail="Nessun accesso a questa società")
    db = get_db()
    d = await db.legal_entities.find_one({"_id": eid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not d:
        raise HTTPException(status_code=404, detail="Legal entity non trovata")
    return _refresh_missing(from_mongo(d))


@router.patch("/{eid}")
async def update_entity(eid: str, payload: LegalEntityUpdate, request: Request,
                         user: dict = Depends(require_permission("company.edit"))):
    if not await user_can_access_entity(user, eid):
        raise HTTPException(status_code=403, detail="Nessun accesso a questa società")
    db = get_db()
    prev = await db.legal_entities.find_one({"_id": eid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not prev:
        raise HTTPException(status_code=404, detail="Legal entity non trovata")
    updates = payload.model_dump(exclude_unset=True)
    # Snapshot fiscale se cambiano campi critici
    fiscal_changed = any(k in updates for k in REQUIRED_FISCAL_FIELDS + ["sdi_code", "vat_regime"])
    if fiscal_changed:
        updates["fiscal_version"] = (prev.get("fiscal_version") or 1) + 1
        updates["prev_fiscal_snapshot"] = {
            k: prev.get(k) for k in REQUIRED_FISCAL_FIELDS + ["sdi_code", "vat_regime", "vat_periodicity"]
        }
    updates["updated_at"] = utcnow().isoformat()
    updates["updated_by"] = user["id"]
    # Refresh missing
    merged = {**prev, **updates}
    refreshed = _refresh_missing(merged)
    updates["missing_fields"] = refreshed["missing_fields"]
    updates["fiscal_operations_blocked"] = refreshed["fiscal_operations_blocked"]
    if refreshed.get("le_status"):
        updates["le_status"] = refreshed["le_status"]
    await db.legal_entities.update_one({"_id": eid}, {"$set": updates, "$inc": {"version": 1}})
    return from_mongo(await db.legal_entities.find_one({"_id": eid}))


@router.delete("/{eid}")
async def delete_entity(eid: str, request: Request,
                         user: dict = Depends(require_permission("company.edit"))):
    return await soft_delete_doc(collection="legal_entities", doc_id=eid, user=user,
                                  entity_type="legal_entity", ip=get_client_ip(request))


# ---------- MEMBERSHIPS ----------
@router.get("/{eid}/memberships")
async def list_memberships(eid: str, user: dict = Depends(require_permission("users.view"))):
    db = get_db()
    docs = await db.legal_entity_memberships.find({
        "tenant_id": user["tenant_id"], "legal_entity_id": eid,
        "active": True, "deleted_at": None,
    }).to_list(200)
    return {"items": [from_mongo(d) for d in docs]}


@router.post("/{eid}/memberships")
async def create_membership(eid: str, payload: dict,
                             user: dict = Depends(require_permission("users.manage"))):
    db = get_db()
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(400, "user_id richiesto")
    existing = await db.legal_entity_memberships.find_one({
        "tenant_id": user["tenant_id"], "legal_entity_id": eid,
        "user_id": user_id, "active": True, "deleted_at": None,
    })
    if existing:
        return from_mongo(existing)
    inst = LegalEntityMembership(
        tenant_id=user["tenant_id"], legal_entity_id=eid, user_id=user_id,
        membership_role=payload.get("membership_role", "member"),
        granted_by=user["id"],
    )
    await db.legal_entity_memberships.insert_one(to_mongo(inst.model_dump(by_alias=True)))
    return inst.model_dump()


@router.delete("/{eid}/memberships/{mid}")
async def revoke_membership(eid: str, mid: str,
                             user: dict = Depends(require_permission("users.manage"))):
    db = get_db()
    await db.legal_entity_memberships.update_one(
        {"_id": mid, "tenant_id": user["tenant_id"]},
        {"$set": {"active": False, "revoked_at": utcnow().isoformat()}}
    )
    return {"ok": True}


@router.get("/me/scope")
async def my_scope(user: dict = Depends(get_current_user)):
    """Ritorna l'elenco delle legal entities accessibili all'utente corrente."""
    ids = await get_user_legal_entity_ids(user)
    db = get_db()
    query = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if ids is not None:
        query["_id"] = {"$in": ids}
    docs = await db.legal_entities.find(query).sort([("code", 1)]).to_list(20)
    return {
        "cross_company": ids is None,
        "items": [_refresh_missing(from_mongo(d)) for d in docs],
    }
