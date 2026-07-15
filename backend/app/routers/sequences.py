"""Sequences (numerazioni progressive)."""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models import Sequence, SequenceCreate, SequenceUpdate, new_id
from app.mongo_utils import to_mongo, from_mongo
from app.services.audit import record_audit

router = APIRouter(prefix="/sequences", tags=["sequences"])


def _format(seq: dict, number: int) -> str:
    padded = str(number).zfill(seq.get("padding", 5))
    year = seq.get("current_year")
    year_part = f"{year}/" if seq.get("year_reset") and year else ""
    return f"{seq.get('prefix', '')}{year_part}{padded}{seq.get('suffix', '')}"


@router.get("")
async def list_sequences(user: dict = Depends(require_permission("sequences.view"))):
    db = get_db()
    docs = await db.sequences.find(
        {"tenant_id": user["tenant_id"], "deleted_at": None}
    ).sort("key", 1).to_list(200)
    items = []
    for d in docs:
        d = from_mongo(d)
        d["preview"] = _format(d, (d.get("current_number") or 0) + 1)
        items.append(d)
    return {"items": items}


@router.post("")
async def create_sequence(
    body: SequenceCreate, request: Request,
    user: dict = Depends(require_permission("sequences.manage")),
):
    db = get_db()
    if await db.sequences.find_one({"tenant_id": user["tenant_id"], "key": body.key}):
        raise HTTPException(status_code=400, detail="Chiave numerazione già esistente")
    s = Sequence(
        id=new_id(), tenant_id=user["tenant_id"],
        key=body.key, label=body.label, prefix=body.prefix, suffix=body.suffix,
        padding=body.padding, year_reset=body.year_reset,
        created_by=user["id"], updated_by=user["id"],
    )
    await db.sequences.insert_one(to_mongo(s.model_dump(by_alias=True)))
    await record_audit(
        action="sequences.create", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="sequence", entity_id=s.id, after=body.model_dump(),
    )
    return from_mongo(await db.sequences.find_one({"_id": s.id}))


@router.patch("/{sid}")
async def update_sequence(
    sid: str, body: SequenceUpdate, request: Request,
    user: dict = Depends(require_permission("sequences.manage")),
):
    db = get_db()
    doc = await db.sequences.find_one({"_id": sid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Numerazione non trovata")
    update = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by"] = user["id"]
    await db.sequences.update_one({"_id": sid}, {"$set": update})
    await record_audit(
        action="sequences.update", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="sequence", entity_id=sid,
        before={k: doc.get(k) for k in update if k in doc}, after=update,
    )
    return from_mongo(await db.sequences.find_one({"_id": sid}))


@router.post("/{sid}/next")
async def next_number(
    sid: str, request: Request,
    user: dict = Depends(require_permission("sequences.view")),
):
    """Atomically get the next number for a sequence.
    This is the API for other modules to obtain a document number.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    year = now.year
    doc = await db.sequences.find_one({"_id": sid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Numerazione non trovata")
    # Year reset logic
    if doc.get("year_reset") and doc.get("current_year") != year:
        await db.sequences.update_one({"_id": sid}, {"$set": {"current_number": 0, "current_year": year}})
    updated = await db.sequences.find_one_and_update(
        {"_id": sid, "tenant_id": user["tenant_id"]},
        {"$inc": {"current_number": 1}, "$set": {"current_year": year, "updated_at": now.isoformat()}},
        return_document=True,
    )
    formatted = _format(updated, updated["current_number"])
    await record_audit(
        action="sequences.next", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="sequence", entity_id=sid, meta={"number": updated["current_number"], "formatted": formatted},
    )
    return {"number": updated["current_number"], "formatted": formatted}
