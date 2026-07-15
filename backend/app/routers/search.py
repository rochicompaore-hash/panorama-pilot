"""Global search across pilot collections."""
from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from app.db import get_db
from app.deps import require_permission
from app.mongo_utils import from_mongo

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def global_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, le=50),
    user: dict = Depends(require_permission("search.global")),
):
    db = get_db()
    tenant = user["tenant_id"]
    rx = {"$regex": q, "$options": "i"}
    results: list[dict] = []

    # Users
    users = await db.users.find(
        {"tenant_id": tenant, "deleted_at": None,
         "$or": [{"email": rx}, {"first_name": rx}, {"last_name": rx}]}
    ).limit(limit).to_list(limit)
    for u in users:
        results.append({
            "collection": "users", "type": "Utente",
            "id": u["_id"],
            "title": f'{u.get("first_name","")} {u.get("last_name","")}'.strip() or u["email"],
            "subtitle": u["email"],
            "link": f'/users/{u["_id"]}',
        })

    # Roles
    roles = await db.roles.find(
        {"tenant_id": tenant, "deleted_at": None,
         "$or": [{"name": rx}, {"description": rx}]}
    ).limit(limit).to_list(limit)
    for r in roles:
        results.append({
            "collection": "roles", "type": "Ruolo",
            "id": r["_id"],
            "title": r.get("name"),
            "subtitle": r.get("description") or "",
            "link": f'/roles/{r["_id"]}',
        })

    # Attachments
    atts = await db.attachments.find(
        {"tenant_id": tenant, "deleted_at": None,
         "$or": [{"filename": rx}, {"description": rx}, {"tags": rx}]}
    ).limit(limit).to_list(limit)
    for a in atts:
        results.append({
            "collection": "attachments", "type": "Allegato",
            "id": a["_id"],
            "title": a.get("filename"),
            "subtitle": a.get("entity_type", ""),
            "link": f'/attachments?highlight={a["_id"]}',
        })

    # Sequences
    seqs = await db.sequences.find(
        {"tenant_id": tenant, "deleted_at": None,
         "$or": [{"key": rx}, {"label": rx}, {"prefix": rx}]}
    ).limit(limit).to_list(limit)
    for s in seqs:
        results.append({
            "collection": "sequences", "type": "Numerazione",
            "id": s["_id"],
            "title": s.get("label"),
            "subtitle": s.get("key"),
            "link": "/settings/sequences",
        })

    # Audit (recent match on action)
    audits = await db.audit_logs.find(
        {"tenant_id": tenant,
         "$or": [{"action": rx}, {"user_email": rx}, {"entity_type": rx}]}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    for a in audits:
        results.append({
            "collection": "audit", "type": "Audit",
            "id": a["_id"],
            "title": a.get("action"),
            "subtitle": a.get("user_email") or "",
            "link": "/audit",
        })

    return {"query": q, "results": results, "total": len(results)}
