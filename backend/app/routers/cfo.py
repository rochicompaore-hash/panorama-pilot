"""CFO Control Tower API — /api/cfo (unico engine: app.services.cfo_engine)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.services import cfo_engine as eng
from app.services import cash_engine as cash
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


class TermsBody(BaseModel):
    preset: Optional[str] = None  # 50/50 | 40/60 | 30/70 | 50/40/10 | CUSTOM
    splits: Optional[List[Dict[str, Any]]] = None  # [{"step": "ORDER", "percent": 30}, ...] somma 100
    lead_days: Optional[int] = Field(None, ge=0, le=365)


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


@router.get("/cash-command-center")
async def cash_command_center(legal_entity_id: Optional[str] = None, user: dict = Depends(require_permission("treasury.view"))):
    return await cash.command_center(get_db(), user["tenant_id"], legal_entity_id)


async def _admin_quote(qid: str, user: dict) -> dict:
    from app.routers.quotes import _get_perms, ADMIN_MASTER_MARKER
    db = get_db()
    q = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not q:
        raise HTTPException(404, "Preventivo non trovato")
    if ADMIN_MASTER_MARKER not in await _get_perms(user):
        raise HTTPException(403, {"code": "ADMIN_MASTER_ONLY", "message": "Esposizione cash visibile solo ad Admin Master"})
    return q


@router.get("/quote/{qid}/cash-exposure")
async def quote_cash_exposure(qid: str, user: dict = Depends(require_permission("quotes.view"))):
    q = await _admin_quote(qid, user)
    return {**cash.quote_cash_exposure(q), "presets": list(cash.TERMS_PRESETS.keys()) + ["CUSTOM"]}


@router.post("/quote/{qid}/cash-terms-simulate")
async def quote_cash_terms_simulate(qid: str, body: TermsBody, user: dict = Depends(require_permission("quotes.view"))):
    from app.services.sustainability_engine import quote_contribution
    q = await _admin_quote(qid, user)
    if body.preset and body.preset != "CUSTOM":
        if body.preset not in cash.TERMS_PRESETS:
            raise HTTPException(400, {"code": "PRESET_INVALID", "allowed": list(cash.TERMS_PRESETS.keys()) + ["CUSTOM"]})
        splits = cash.TERMS_PRESETS[body.preset]
    else:
        splits = [(str(s.get("step") or "ORDER").upper(), float(s.get("percent") or 0)) for s in (body.splits or [])]
        if not splits or abs(sum(p for _, p in splits) - 100) > 0.01:
            raise HTTPException(400, {"code": "SPLITS_INVALID", "message": "La somma delle percentuali deve essere 100"})
    qc = quote_contribution(q)
    gross = eng._f(q.get("total")) or round(eng._f(qc["net_revenue_ex_vat"]) * 1.22, 2)
    return {**cash.simulate_terms(gross_total=gross, net_total=qc["net_revenue_ex_vat"], direct_costs=qc["direct_costs"] if qc["complete"] else None, splits=splits,
                                  lead_days=body.lead_days if body.lead_days is not None else q.get("delivery_lead_time_days")), "preset": body.preset or "CUSTOM"}
