"""Audit log service - append-only."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from app.db import get_db
from app.models import AuditLog, new_id


async def record_audit(
    *,
    action: str,
    tenant_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    db = get_db()
    log = AuditLog(
        id=new_id(),
        tenant_id=tenant_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        user_email=user_email,
        ip=ip,
        user_agent=user_agent,
        before=_sanitize(before),
        after=_sanitize(after),
        meta=meta,
    )
    doc = log.model_dump(by_alias=True)
    _iso_dates(doc)
    await db.audit_logs.insert_one(doc)


def _sanitize(d: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if d is None:
        return None
    SENSITIVE = {"password", "password_hash", "token", "refresh_token_hash", "token_hash"}
    return {k: ("***" if k in SENSITIVE else v) for k, v in d.items()}


def _iso_dates(d: Dict[str, Any]) -> None:
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = v.isoformat()
