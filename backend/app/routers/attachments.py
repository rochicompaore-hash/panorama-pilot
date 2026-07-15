"""Attachments: upload, list, download (signed for S3), delete (soft)."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, Query
from fastapi.responses import Response, RedirectResponse
from app.config import settings
from app.db import get_db
from app.deps import require_permission, require_any_permission, get_client_ip
from app.models import Attachment, new_id
from app.mongo_utils import to_mongo, from_mongo
from app.services.storage import get_storage, build_key, sanitize_filename
from app.services.audit import record_audit

router = APIRouter(prefix="/attachments", tags=["attachments"])

MAX_SIZE_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


@router.post("/upload")
async def upload_attachment(
    request: Request,
    file: UploadFile = File(...),
    entity_type: str = Form(...),
    entity_id: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    user: dict = Depends(require_permission("attachments.create")),
):
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="File vuoto")
    if len(data) > MAX_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=f"File troppo grande (max {settings.MAX_UPLOAD_SIZE_MB}MB)")
    try:
        key = build_key(user["tenant_id"], entity_type, entity_id or "general", file.filename or "file")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    storage = get_storage()
    storage.put(key, data, file.content_type or "application/octet-stream")

    att = Attachment(
        id=new_id(),
        tenant_id=user["tenant_id"],
        entity_type=entity_type, entity_id=entity_id,
        filename=sanitize_filename(file.filename or "file"),
        storage_key=key, size=len(data),
        mime_type=file.content_type or "application/octet-stream",
        uploaded_by=user["id"],
        tags=[t.strip() for t in (tags or "").split(",") if t.strip()],
        description=description,
        created_by=user["id"], updated_by=user["id"],
    )
    db = get_db()
    await db.attachments.insert_one(to_mongo(att.model_dump(by_alias=True)))
    await record_audit(
        action="attachments.upload", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="attachment", entity_id=att.id,
        after={"filename": att.filename, "size": att.size, "entity_type": entity_type},
    )
    return from_mongo(await db.attachments.find_one({"_id": att.id}))


@router.get("")
async def list_attachments(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    q: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(50, le=200),
    user: dict = Depends(require_permission("attachments.view")),
):
    db = get_db()
    query: dict = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if entity_type:
        query["entity_type"] = entity_type
    if entity_id:
        query["entity_id"] = entity_id
    if q:
        query["$or"] = [
            {"filename": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"tags": {"$regex": q, "$options": "i"}},
        ]
    total = await db.attachments.count_documents(query)
    docs = await db.attachments.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": [from_mongo(d) for d in docs]}


@router.get("/{aid}/download")
async def download_attachment(
    aid: str, request: Request,
    user: dict = Depends(require_permission("attachments.download")),
):
    db = get_db()
    doc = await db.attachments.find_one({"_id": aid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Allegato non trovato")
    storage = get_storage()
    await record_audit(
        action="attachments.download", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="attachment", entity_id=aid,
    )
    # If S3, use signed url
    signed = storage.signed_url(doc["storage_key"], expires=900)
    if signed:
        return RedirectResponse(signed)
    data = storage.get(doc["storage_key"])
    return Response(
        content=data,
        media_type=doc.get("mime_type", "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{doc["filename"]}"'},
    )


@router.delete("/{aid}")
async def delete_attachment(
    aid: str, request: Request,
    user: dict = Depends(require_permission("attachments.delete")),
):
    db = get_db()
    doc = await db.attachments.find_one({"_id": aid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Allegato non trovato")
    now = datetime.now(timezone.utc).isoformat()
    await db.attachments.update_one({"_id": aid}, {"$set": {"deleted_at": now, "updated_by": user["id"], "updated_at": now}})
    await record_audit(
        action="attachments.delete", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="attachment", entity_id=aid,
    )
    return {"ok": True}
