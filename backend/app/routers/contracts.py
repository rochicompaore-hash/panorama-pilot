"""Contracts router (minimal M3.1) — list + get + sign (electronic signature FES)."""
from __future__ import annotations
import hashlib
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.mongo_utils import from_mongo
from app.services.audit import record_audit
from app.services.timeline import record_activity

router = APIRouter(prefix="/contracts", tags=["contracts"])


class SignRequest(BaseModel):
    signer_name: str
    signature_data_url: str  # base64 PNG from canvas
    accept_terms: bool = True


@router.get("")
async def list_contracts(
    q: Optional[str] = None, customer_id: Optional[str] = None,
    limit: int = Query(100, le=500), skip: int = 0,
    user: dict = Depends(require_permission("contracts.view")),
):
    db = get_db()
    query: dict = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if customer_id: query["customer_id"] = customer_id
    if q: query["$or"] = [{"number": {"$regex": q, "$options": "i"}}]
    total = await db.contracts.count_documents(query)
    docs = await db.contracts.find(query).sort([("number_int", -1)]).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": [from_mongo(d) for d in docs]}


@router.get("/{cid}")
async def get_contract(cid: str, user: dict = Depends(require_permission("contracts.view"))):
    db = get_db()
    doc = await db.contracts.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc: raise HTTPException(status_code=404, detail="Contratto non trovato")
    return from_mongo(doc)


@router.post("/{cid}/sign")
async def sign_contract(cid: str, body: SignRequest, request: Request, user: dict = Depends(require_permission("contracts.sign"))):
    db = get_db()
    doc = await db.contracts.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc: raise HTTPException(status_code=404, detail="Contratto non trovato")
    if doc.get("contract_status") == "signed":
        raise HTTPException(status_code=400, detail="Contratto già firmato")
    if not body.accept_terms:
        raise HTTPException(status_code=400, detail="Accettazione condizioni obbligatoria")
    now = datetime.now(timezone.utc)
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    payload = f"{cid}|{body.signer_name}|{ip}|{ua}|{now.isoformat()}|{doc.get('number')}"
    signature_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    await db.contracts.update_one({"_id": cid}, {"$set": {
        "contract_status": "signed",
        "signed_at": now.isoformat(),
        "signed_by_name": body.signer_name,
        "signed_ip": ip,
        "signed_ua": ua,
        "signature_data_url": body.signature_data_url,
        "signature_hash": signature_hash,
        "updated_at": now.isoformat(),
        "updated_by": user["id"],
    }})
    await record_audit(action="contracts.sign", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=ip,
                       entity_type="contract", entity_id=cid, after={"signer": body.signer_name, "hash": signature_hash})
    await record_activity(tenant_id=user["tenant_id"], type="contract_signed",
                          subject=f"Contratto {doc.get('number')} firmato da {body.signer_name}",
                          customer_id=doc.get("customer_id"),
                          user_id=user["id"], user_email=user["email"],
                          meta={"signature_hash": signature_hash})
    # Hook workflow: crea Survey to_schedule (idempotente) + log timeline
    try:
        from app.services.workflow_engine import ensure_survey_from_contract, log_timeline_event
        # Fetch updated doc (with signed status)
        updated = await db.contracts.find_one({"_id": cid, "tenant_id": user["tenant_id"]})
        survey_id = await ensure_survey_from_contract(
            tenant_id=user["tenant_id"], contract=updated, actor_id=user["id"],
        )
        await log_timeline_event(
            tenant_id=user["tenant_id"], domain="contract", event_type="contract.signed",
            ref_id=cid, contract_id=cid, customer_id=doc.get("customer_id"),
            quote_id=doc.get("quote_id"), survey_id=survey_id,
            source="user", actor_id=user["id"], actor_email=user["email"],
            new_status="signed", is_customer_visible=True,
            customer_label="Contratto firmato", customer_stage="contract_signed",
        )
    except Exception as e:
        # Non fatale
        import logging
        logging.getLogger("infissi.contracts").warning("Post-sign workflow hook failed: %s", e)
    return {"ok": True, "signature_hash": signature_hash}


@router.post("/{cid}/cancel")
async def cancel_contract(cid: str, request: Request, user: dict = Depends(require_permission("contracts.cancel"))):
    db = get_db()
    doc = await db.contracts.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc: raise HTTPException(status_code=404, detail="Contratto non trovato")
    if doc.get("contract_status") == "signed":
        raise HTTPException(status_code=400, detail="Contratto firmato non annullabile")
    now = datetime.now(timezone.utc).isoformat()
    await db.contracts.update_one({"_id": cid}, {"$set": {"contract_status": "cancelled", "updated_at": now, "updated_by": user["id"]}})
    await record_audit(action="contracts.cancel", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="contract", entity_id=cid)
    return {"ok": True}
