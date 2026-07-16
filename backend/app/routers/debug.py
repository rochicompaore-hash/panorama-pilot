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


@router.get("/platform-owner-invite")
async def read_platform_owner_invite(request: Request,
                                       user: dict = Depends(require_permission("debug.otp.read"))):
    """Return the pending invitation URL for the Platform Owner (dev/test only).

    Auto-disabilitato in staging/production. Ogni consultazione viene audit-loggata.
    Se l'utenza è già stata attivata, ritorna 410. Se non esiste ancora un invito
    valido, il seed lo rigenera al prossimo restart o via /platform-owner-invite/regenerate.
    """
    if not is_dev_or_test():
        raise HTTPException(status_code=404, detail="Not found")
    db = get_db()
    from app.platform_owner import PLATFORM_OWNER_EMAIL
    po_user = await db.users.find_one({"email": PLATFORM_OWNER_EMAIL})
    if not po_user:
        raise HTTPException(status_code=404, detail="Utenza proprietaria non trovata")
    if po_user.get("password_hash"):
        raise HTTPException(status_code=410,
            detail={"error": "already_active", "message": "L'utenza proprietaria è già attivata"})
    inv = await db.invitations.find_one({
        "email": PLATFORM_OWNER_EMAIL, "consumed_at": None, "accepted_at": None,
        "kind": "platform_owner_activation",
    }, sort=[("created_at", -1)])
    if not inv:
        raise HTTPException(status_code=404, detail="Nessun invito attivo (riavvia il backend per rigenerare)")
    raw = inv.get("debug_raw_token")
    if not raw:
        raise HTTPException(status_code=410,
            detail={"error": "token_not_recoverable",
                     "message": "Il token in chiaro non è più recuperabile. Rigenera l'invito via /debug/platform-owner-invite/regenerate."})
    await record_audit(
        action="debug.platform_owner_invite.read",
        tenant_id=None, user_id=user["id"], user_email=user["email"],
        ip=get_client_ip(request),
        entity_type="invitation", entity_id=inv["_id"],
        after={"email": PLATFORM_OWNER_EMAIL, "expires_at": inv.get("expires_at")},
    )
    return {
        "email": PLATFORM_OWNER_EMAIL,
        "invitation_id": str(inv["_id"]),
        "raw_token": raw,
        "accept_url_path": f"/accept-invitation?token={raw}",
        "expires_at": inv.get("expires_at"),
        "instructions": "Naviga su /accept-invitation?token=... per impostare la password. Il link è monouso.",
    }


@router.post("/platform-owner-invite/regenerate")
async def regenerate_platform_owner_invite(request: Request,
                                             user: dict = Depends(require_permission("debug.otp.read"))):
    """Invalida gli inviti pendenti e ne genera uno nuovo. Solo dev/test.

    Usa questo endpoint se hai perso il precedente raw token.
    """
    if not is_dev_or_test():
        raise HTTPException(status_code=404, detail="Not found")
    db = get_db()
    from app.platform_owner import PLATFORM_OWNER_EMAIL, ensure_platform_owner_user, ensure_platform_owner_role
    po_user = await db.users.find_one({"email": PLATFORM_OWNER_EMAIL})
    if po_user and po_user.get("password_hash"):
        raise HTTPException(status_code=410, detail="L'utenza è già attivata")
    now = datetime.now(timezone.utc).isoformat()
    await db.invitations.update_many(
        {"email": PLATFORM_OWNER_EMAIL, "consumed_at": None},
        {"$set": {"consumed_at": now, "status": "revoked", "revocation_reason": "regenerated_by_debug"}},
    )
    role_id = await ensure_platform_owner_role()
    _, inv_info = await ensure_platform_owner_user(role_id)
    await record_audit(
        action="debug.platform_owner_invite.regenerate",
        tenant_id=None, user_id=user["id"], user_email=user["email"],
        ip=get_client_ip(request),
        entity_type="invitation", entity_id=inv_info.get("invitation_token_id"),
        after={"email": PLATFORM_OWNER_EMAIL, "expires_at": inv_info.get("expires_at")},
    )
    return {
        "email": PLATFORM_OWNER_EMAIL,
        "invitation_id": inv_info.get("invitation_token_id"),
        "raw_token": inv_info.get("raw_token_debug"),
        "accept_url_path": f"/accept-invitation?token={inv_info.get('raw_token_debug')}",
        "expires_at": inv_info.get("expires_at"),
    }
