"""Company (tenant) management."""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from app.db import get_db
from app.deps import require_permission, get_current_user, get_client_ip
from app.models import CompanyUpdate
from app.mongo_utils import from_mongo
from app.services.audit import record_audit

router = APIRouter(prefix="/company", tags=["company"])


@router.get("")
async def get_company(user: dict = Depends(require_permission("company.view"))):
    db = get_db()
    doc = await db.companies.find_one({"_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Azienda non trovata")
    return from_mongo(doc)


@router.patch("")
async def update_company(
    body: CompanyUpdate, request: Request,
    user: dict = Depends(require_permission("company.edit")),
):
    db = get_db()
    doc = await db.companies.find_one({"_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Azienda non trovata")
    update: dict = {"updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user["id"]}
    payload = body.model_dump(exclude_unset=True)
    if "settings" in payload and payload["settings"] is not None:
        payload["settings"] = body.settings.model_dump()
    update.update(payload)
    await db.companies.update_one({"_id": user["tenant_id"]}, {"$set": update})
    # Version history
    await db.entity_versions.insert_one({
        "_id": __import__("uuid").uuid4().hex,
        "entity_type": "company", "entity_id": user["tenant_id"],
        "version": (doc.get("version", 1) + 1),
        "snapshot": {k: v for k, v in {**doc, **update}.items() if k != "_id"},
        "changed_by": user["id"], "created_at": datetime.now(timezone.utc).isoformat(),
    })
    await db.companies.update_one({"_id": user["tenant_id"]}, {"$inc": {"version": 1}})
    await record_audit(
        action="company.update", tenant_id=user["tenant_id"],
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="company", entity_id=user["tenant_id"],
        before={k: doc.get(k) for k in payload}, after=payload,
    )
    return from_mongo(await db.companies.find_one({"_id": user["tenant_id"]}))
