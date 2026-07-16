"""M4..M14 — Generic CRUD helpers with tenant isolation + audit + timeline.

Shared helpers used by every operational router. Keeps individual routers under
~200 lines and enforces uniform semantics: soft delete, optimistic concurrency
via version, next-number generation, list-with-filter, and structured audit.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Callable
from fastapi import HTTPException, Request
from app.db import get_db
from app.models import new_id, Sequence
from app.mongo_utils import to_mongo, from_mongo
from app.services.audit import record_audit


async def next_number(tenant_id: str, key: str, *, prefix: str, padding: int = 5, year_reset: bool = True) -> tuple[str, int]:
    """Atomically increment a sequence, creating it if missing. Returns (formatted, int)."""
    db = get_db()
    now = datetime.now(timezone.utc)
    seq = await db.sequences.find_one({"tenant_id": tenant_id, "key": key})
    if not seq:
        s = Sequence(id=new_id(), tenant_id=tenant_id, key=key, label=key.replace("_", " ").title(),
                     prefix=prefix, padding=padding, year_reset=year_reset)
        await db.sequences.insert_one(to_mongo(s.model_dump(by_alias=True)))
        seq = await db.sequences.find_one({"tenant_id": tenant_id, "key": key})
    year = now.year
    if seq.get("year_reset") and seq.get("current_year") != year:
        await db.sequences.update_one({"_id": seq["_id"]},
            {"$set": {"current_number": 0, "current_year": year}})
    updated = await db.sequences.find_one_and_update(
        {"_id": seq["_id"], "tenant_id": tenant_id},
        {"$inc": {"current_number": 1},
         "$set": {"current_year": year, "updated_at": now.isoformat()}},
        return_document=True,
    )
    n = updated["current_number"]
    padded = str(n).zfill(updated.get("padding", padding))
    year_part = f"{year}-" if updated.get("year_reset", year_reset) else ""
    return f"{updated.get('prefix', prefix)}{year_part}{padded}", n


async def create_doc(*, collection: str, model_instance, user: dict, entity_type: str,
                     ip: Optional[str], set_number: bool = False,
                     number_key: Optional[str] = None, number_prefix: Optional[str] = None) -> dict:
    db = get_db()
    if set_number and number_key and number_prefix:
        num, n_int = await next_number(user["tenant_id"], number_key, prefix=number_prefix)
        model_instance.number = num
        model_instance.number_int = n_int
    model_instance.tenant_id = user["tenant_id"]
    model_instance.created_by = user["id"]
    model_instance.updated_by = user["id"]
    doc = to_mongo(model_instance.model_dump(by_alias=True))
    await db[collection].insert_one(doc)
    await record_audit(action=f"{entity_type}.create", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=ip, entity_type=entity_type, entity_id=model_instance.id,
                       after={"number": getattr(model_instance, "number", None)})
    return from_mongo(await db[collection].find_one({"_id": model_instance.id}))


async def get_doc(*, collection: str, doc_id: str, tenant_id: str) -> dict:
    db = get_db()
    d = await db[collection].find_one({"_id": doc_id, "tenant_id": tenant_id, "deleted_at": None})
    if not d:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    return from_mongo(d)


async def list_docs(*, collection: str, tenant_id: str, filters: Optional[Dict[str, Any]] = None,
                     search_fields: Optional[List[str]] = None, q: Optional[str] = None,
                     sort: Optional[List[tuple]] = None, skip: int = 0, limit: int = 100,
                     project_out: Optional[List[str]] = None) -> Dict[str, Any]:
    db = get_db()
    query: Dict[str, Any] = {"tenant_id": tenant_id, "deleted_at": None}
    if filters:
        for k, v in filters.items():
            if v is not None: query[k] = v
    if q and search_fields:
        query["$or"] = [{f: {"$regex": q, "$options": "i"}} for f in search_fields]
    projection = None
    if project_out:
        projection = {p: 0 for p in project_out}
    total = await db[collection].count_documents(query)
    cursor = db[collection].find(query, projection)
    if sort: cursor = cursor.sort(sort)
    docs = await cursor.skip(skip).limit(min(limit, 500)).to_list(min(limit, 500))
    return {"total": total, "items": [from_mongo(d) for d in docs]}


async def update_doc(*, collection: str, doc_id: str, updates: Dict[str, Any], user: dict,
                     entity_type: str, ip: Optional[str], allowed_fields: Optional[List[str]] = None) -> dict:
    db = get_db()
    existing = await db[collection].find_one({"_id": doc_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not existing:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    if allowed_fields is not None:
        updates = {k: v for k, v in updates.items() if k in allowed_fields}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    updates["updated_by"] = user["id"]
    before = {k: existing.get(k) for k in updates.keys()}
    await db[collection].update_one({"_id": doc_id}, {"$set": updates, "$inc": {"version": 1}})
    await record_audit(action=f"{entity_type}.update", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=ip, entity_type=entity_type, entity_id=doc_id,
                       before=before, after=updates)
    return from_mongo(await db[collection].find_one({"_id": doc_id}))


async def soft_delete_doc(*, collection: str, doc_id: str, user: dict, entity_type: str,
                           ip: Optional[str], block_if_field: Optional[str] = None) -> dict:
    db = get_db()
    existing = await db[collection].find_one({"_id": doc_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not existing:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    if block_if_field and existing.get(block_if_field):
        raise HTTPException(status_code=400, detail=f"Non eliminabile: campo '{block_if_field}' popolato")
    now = datetime.now(timezone.utc).isoformat()
    await db[collection].update_one({"_id": doc_id},
        {"$set": {"deleted_at": now, "status": "deleted", "updated_at": now, "updated_by": user["id"]},
         "$inc": {"version": 1}})
    await record_audit(action=f"{entity_type}.delete", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=ip, entity_type=entity_type, entity_id=doc_id)
    return {"ok": True}


def enforce_status_transition(current: str, target: str, allowed_flow: Dict[str, set]):
    if target == current:
        return
    if target not in allowed_flow.get(current, set()):
        raise HTTPException(
            status_code=400,
            detail=f"Transizione non consentita da '{current}' a '{target}'. "
                   f"Ammesse: {sorted(list(allowed_flow.get(current, set())))}",
        )
