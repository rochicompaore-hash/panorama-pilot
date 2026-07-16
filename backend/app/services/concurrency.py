"""Optimistic Concurrency Control service.

Every operational entity has an integer `version` field (default 1).
Updates must supply the client-side version. Mongo update filter includes
`{_id, version: expected_version}` and increments `$inc: {version: 1}`.
If the modified_count is 0 → conflict → raise ConflictError → 409 with server data.

Force override:
- Requires `records.force_override` permission
- Requires non-empty reason
- Not allowed on entities marked "consolidated" (sent/accepted/signed/converted quotes, signed contracts)
- Always recorded in audit_log with kind="force_override"
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Optional, Iterable
from fastapi import HTTPException, Request, Header, Depends
from app.db import get_db
from app.mongo_utils import from_mongo
from app.services.audit import record_audit


CONSOLIDATED_QUOTE_STATUSES = {"sent", "viewed", "negotiating", "accepted", "converted", "superseded", "rejected", "expired"}
CONSOLIDATED_CONTRACT_STATUSES = {"signed", "cancelled"}


class ConflictError(HTTPException):
    def __init__(self, current_doc: dict, entity_type: str, expected_version: int):
        payload = {
            "error": "version_conflict",
            "entity_type": entity_type,
            "expected_version": expected_version,
            "current_version": current_doc.get("version", 1),
            "updated_by": current_doc.get("updated_by"),
            "updated_at": current_doc.get("updated_at"),
            "server_data": current_doc,
        }
        super().__init__(status_code=409, detail=payload)


def get_if_match_version(if_match: Optional[str] = Header(default=None, alias="If-Match")) -> Optional[int]:
    """Extract version from If-Match header. Value is stripped and coerced to int.
    Optional — routes may also accept `expected_version` in body.
    """
    if if_match is None or if_match == "":
        return None
    try:
        v = if_match.strip().strip('"').strip("W/").strip('"')
        return int(v)
    except Exception:
        raise HTTPException(status_code=400, detail="Header If-Match non valido, atteso numero intero")


def _is_consolidated(entity_type: str, doc: dict) -> bool:
    if entity_type == "quote":
        return doc.get("quote_status") in CONSOLIDATED_QUOTE_STATUSES
    if entity_type == "contract":
        return doc.get("contract_status") in CONSOLIDATED_CONTRACT_STATUSES
    return False


async def update_with_version(
    *,
    collection: str,
    entity_id: str,
    tenant_id: str,
    entity_type: str,
    expected_version: Optional[int],
    set_fields: dict,
    user: dict,
    request: Optional[Request] = None,
    force_override: bool = False,
    override_reason: Optional[str] = None,
    allow_consolidated: bool = False,
    extra_query: Optional[dict] = None,
) -> dict:
    """Perform an atomic version-checked update.

    If `expected_version` is None → best-effort update (compat with old clients),
    but WITHOUT version filter, so lost updates possible. New frontend always sends version.

    On force_override:
    - Requires `records.force_override` permission (checked by caller)
    - Requires non-empty override_reason
    - Skips version filter but records audit entry
    - Blocked if entity is consolidated (unless allow_consolidated=True)

    Returns the fresh document dict from Mongo (after update).
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    set_fields["updated_at"] = now
    set_fields["updated_by"] = user["id"]

    base_query = {"_id": entity_id, "tenant_id": tenant_id, "deleted_at": None}
    if extra_query:
        base_query.update(extra_query)

    current = await db[collection].find_one(base_query)
    if not current:
        raise HTTPException(status_code=404, detail=f"{entity_type} non trovato")

    if force_override:
        if not override_reason or not override_reason.strip():
            raise HTTPException(status_code=400, detail="Motivazione obbligatoria per override")
        if not allow_consolidated and _is_consolidated(entity_type, current):
            raise HTTPException(
                status_code=400,
                detail="Documento consolidato non sovrascrivibile — creare una nuova revisione",
            )
        # Skip version filter; record audit
        result = await db[collection].update_one(
            base_query,
            {"$set": set_fields, "$inc": {"version": 1}},
        )
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail=f"{entity_type} non trovato")
        await record_audit(
            action=f"{entity_type}.force_override",
            tenant_id=tenant_id, user_id=user["id"], user_email=user["email"],
            ip=(request and _ip(request)) or None,
            entity_type=entity_type, entity_id=entity_id,
            before={"version": current.get("version"), "data": {k: current.get(k) for k in set_fields.keys() if k not in ("updated_at", "updated_by")}},
            after={"version": current.get("version", 1) + 1, "data": {k: v for k, v in set_fields.items() if k not in ("updated_at", "updated_by")}},
            meta={"kind": "force_override", "reason": override_reason},
        )
        return from_mongo(await db[collection].find_one({"_id": entity_id}))

    # Normal path with version check
    if expected_version is not None:
        if _is_consolidated(entity_type, current) and not allow_consolidated:
            raise HTTPException(
                status_code=400,
                detail=f"Documento in stato consolidato non modificabile — creare una nuova revisione",
            )
        result = await db[collection].update_one(
            {**base_query, "version": expected_version},
            {"$set": set_fields, "$inc": {"version": 1}},
        )
        if result.modified_count == 0:
            # Re-fetch to detect conflict vs. status change vs. not found
            latest = await db[collection].find_one({"_id": entity_id, "tenant_id": tenant_id})
            if not latest:
                raise HTTPException(status_code=404, detail=f"{entity_type} non trovato")
            if latest.get("version") != expected_version:
                raise ConflictError(from_mongo(latest), entity_type, expected_version)
            raise HTTPException(status_code=409, detail="Aggiornamento fallito")
    else:
        # Legacy fallback: no version check (still records audit)
        if not allow_consolidated and _is_consolidated(entity_type, current):
            raise HTTPException(status_code=400, detail="Documento consolidato non modificabile")
        await db[collection].update_one(
            base_query,
            {"$set": set_fields, "$inc": {"version": 1}},
        )

    return from_mongo(await db[collection].find_one({"_id": entity_id}))


def _ip(request: Request) -> Optional[str]:
    try:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        return request.client.host if request.client else None
    except Exception:
        return None


def user_has_permission(user: dict, perms: Iterable[str], key: str) -> bool:
    if user.get("is_superadmin"):
        return True
    ps = set(perms)
    return "*" in ps or key in ps
