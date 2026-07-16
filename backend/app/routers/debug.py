"""M3.3.4 — Debug endpoint to retrieve OTP mock codes.

STRICTLY dev/test only, and additionally guarded by permission `debug.otp.read`.
Every read is audit-logged. Codes disappear from DB after successful verification.
"""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from app.config import is_dev_or_test
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.services.audit import record_audit

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/otp/{request_id}")
async def read_otp_debug(request_id: str, request: Request,
                         user: dict = Depends(require_permission("debug.otp.read"))):
    """Return the mock OTP code for a pending request.

    Requires:
    - APP_ENV in {development, test}
    - Permission `debug.otp.read`
    - The OTP request still has a `debug_code_plain` field (dev-only, cleared on success)
    """
    if not is_dev_or_test():
        raise HTTPException(status_code=404, detail="Not found")
    db = get_db()
    doc = await db.quote_otp_requests.find_one({"_id": request_id})
    if not doc:
        raise HTTPException(status_code=404, detail="OTP request non trovata")
    code = doc.get("debug_code_plain")
    if not code:
        raise HTTPException(status_code=410, detail="OTP non più disponibile (già verificato o scaduto)")
    await record_audit(
        action="debug.otp.read",
        tenant_id=doc.get("tenant_id"),
        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
        entity_type="quote_otp_request", entity_id=request_id,
        after={"channel": doc.get("channel"), "quote_id": doc.get("quote_id")},
    )
    return {
        "request_id": request_id,
        "code": code,
        "channel": doc.get("channel"),
        "quote_id": doc.get("quote_id"),
        "recipient_masked": doc.get("recipient_masked"),
        "expires_at": doc.get("expires_at"),
        "status": doc.get("status"),
    }
