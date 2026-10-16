"""CFO Control Tower API — /api/cfo (unico engine: app.services.cfo_engine)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.services import cfo_engine as eng
from app.services.audit import record_audit

router = APIRouter(prefix="/cfo", tags=["cfo"])


class SettingsBody(BaseModel):
    legal_entity_id: Optional[str] = None
    monthly_revenue_target: Optional[float] = Field(None, ge=0)
    annual_revenue_target: Optional[float] = Field(None, ge=0)
    monthly_collection_target: Optional[float] = Field(None, ge=0)
    minimum_cash_reserve: Optional[float] = Field(None, ge=0)


class BankBalanceBody(BaseModel):
    bank_account_id: str
    balance: float
    as_of_date: str
    legal_entity_id: Optional[str] = None


class SimulateBody(BaseModel):
    legal_entity_id: Optional[str] = None
    revenue: float = Field(gt=0)
    collection_pct: float = Field(100, ge=0, le=100)
    margin_pct: Optional[float] = Field(None, ge=0, le=100)
    collection_days: int = Field(30, ge=0, le=365)


@router.get("/overview")
async def cfo_overview(legal_entity_id: Optional[str] = None, user: dict = Depends(require_permission("treasury.view"))):
    return await eng.overview(get_db(), user["tenant_id"], legal_entity_id)


@router.get("/settings")
async def get_settings(legal_entity_id: Optional[str] = None, user: dict = Depends(require_permission("treasury.view"))):
    return await eng.load_settings(get_db(), user["tenant_id"], None if legal_entity_id in (None, "", "all", eng.GROUP) else legal_entity_id)


@router.put("/settings")
async def put_settings(body: SettingsBody, request: Request, user: dict = Depends(require_permission("treasury.manage"))):
    db = get_db()
    le = None if body.legal_entity_id in (None, "", "all", eng.GROUP) else body.legal_entity_id
    upd = {k: v for k, v in body.model_dump(exclude_unset=True).items() if k != "legal_entity_id"}
    await db.cfo_settings.update_one({"_id": eng.settings_id(user["tenant_id"], le)}, {"$set": {**upd, "tenant_id": user["tenant_id"], "legal_entity_id": le or eng.GROUP,
                                                                                              "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user["id"]}}, upsert=True)
    await record_audit(action="cfo.settings_update", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="cfo_settings", entity_id=le or eng.GROUP, after=upd)
    return await eng.load_settings(db, user["tenant_id"], le)


@router.post("/bank-balance")
async def certify_bank_balance(body: BankBalanceBody, request: Request, user: dict = Depends(require_permission("treasury.manage"))):
    db = get_db()
    acc = await db.bank_accounts.find_one({"_id": body.bank_account_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not acc:
        raise HTTPException(404, "Conto non trovato")
    try:
        as_of = datetime.fromisoformat(body.as_of_date).date()
    except ValueError:
        raise HTTPException(400, {"code": "AS_OF_DATE_INVALID"})
    upd = {"certified_balance": round(body.balance, 2), "certified_at": as_of.isoformat(), "certified_by": user["id"], "updated_at": datetime.now(timezone.utc).isoformat()}
    if body.legal_entity_id:
        upd["legal_entity_id"] = body.legal_entity_id
    await db.bank_accounts.update_one({"_id": acc["_id"]}, {"$set": upd, "$push": {"balance_certifications": {"balance": upd["certified_balance"], "as_of": as_of.isoformat(), "by": user["id"], "at": upd["updated_at"]}}})
    await record_audit(action="cfo.bank_balance_certified", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="bank_account", entity_id=acc["_id"],
                       before={"certified_balance": acc.get("certified_balance"), "certified_at": acc.get("certified_at")}, after=upd)
    return await eng.cash_position(db, user["tenant_id"], None)


@router.post("/simulate")
async def cfo_simulate(body: SimulateBody, user: dict = Depends(require_permission("treasury.view"))):
    db = get_db()
    ov = await eng.overview(db, user["tenant_id"], body.legal_entity_id)
    margin_pct = body.margin_pct if body.margin_pct is not None else ov["kpi_row3"]["margin"]["weighted_margin_percent"]
    if margin_pct is None:
        raise HTTPException(400, {"code": "MARGIN_NOT_AVAILABLE", "message": "Indicare margin_pct: nessun margine reale disponibile"})
    return eng.simulate(revenue=body.revenue, collection_pct=body.collection_pct, margin_pct=margin_pct, collection_days=body.collection_days,
                        monthly_structure=ov["kpi_row3"]["monthly_structure_costs"], available_cash=ov["kpi_row1"]["available_cash"],
                        scheduled_outflows=ov["cash_calendar"]["30d"]["outflows"], reserve=ov["kpi_row3"]["minimum_cash_reserve"] or 0)
