"""Pricing Sustainability API — /api/sustainability (settings per LE/anno/mese, registry costi fissi, valutazione preventivo, simulatore)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.routers.quotes import _get_perms, ADMIN_MASTER_MARKER
from app.services import sustainability_engine as eng
from app.services.audit import record_audit

router = APIRouter(prefix="/sustainability", tags=["sustainability"])


class SettingsBody(BaseModel):
    legal_entity_id: Optional[str] = None
    year: Optional[int] = None
    month: Optional[int] = Field(None, ge=1, le=12)
    annual_fixed_cost_target: Optional[float] = Field(None, ge=0)
    structure_coverage_target_date: Optional[str] = None
    expected_monthly_jobs: Optional[float] = Field(None, ge=0)
    expected_monthly_revenue: Optional[float] = Field(None, ge=0)
    target_monthly_revenue: Optional[float] = Field(None, ge=0)
    target_monthly_contribution: Optional[float] = Field(None, ge=0)
    target_profit: Optional[float] = Field(None, ge=0)
    planning_mode: Optional[str] = None
    current_close_rate: Optional[float] = Field(None, ge=0, le=100)
    expected_close_rate: Optional[float] = Field(None, ge=0, le=100)
    average_contribution_pct: Optional[float] = Field(None, ge=0, le=100)


class SimulateBody(BaseModel):
    legal_entity_id: Optional[str] = None
    annual_fixed_costs: Optional[float] = Field(None, ge=0)
    coverage_months: Optional[int] = Field(None, ge=1, le=36)
    expected_monthly_jobs: Optional[float] = Field(None, ge=0)
    expected_monthly_revenue: Optional[float] = Field(None, ge=0)
    average_ticket: Optional[float] = Field(None, ge=0)
    average_contribution_pct: Optional[float] = Field(None, ge=0, le=100)
    close_rate: Optional[float] = Field(None, ge=0, le=100)
    target_profit: Optional[float] = Field(None, ge=0)


def _le(v):
    return None if v in (None, "", "all", "GROUP") else v


@router.get("/overview")
async def overview(legal_entity_id: Optional[str] = None, user: dict = Depends(require_permission("treasury.view"))):
    return await eng.overview(get_db(), user["tenant_id"], legal_entity_id)


@router.get("/fixed-costs")
async def fixed_costs(legal_entity_id: Optional[str] = None, user: dict = Depends(require_permission("treasury.view"))):
    return await eng.fixed_cost_registry(get_db(), user["tenant_id"], _le(legal_entity_id))


@router.put("/settings")
async def put_settings(body: SettingsBody, request: Request, user: dict = Depends(require_permission("treasury.manage"))):
    db = get_db()
    now = datetime.now(timezone.utc)
    le, year, month = _le(body.legal_entity_id), body.year or now.year, body.month or now.month
    if body.planning_mode and body.planning_mode not in eng.PLANNING_MODES:
        raise HTTPException(400, {"code": "PLANNING_MODE_INVALID", "allowed": list(eng.PLANNING_MODES)})
    upd = {k: v for k, v in body.model_dump(exclude_unset=True).items() if k not in ("legal_entity_id", "year", "month")}
    await db.pricing_sustainability_settings.update_one({"_id": eng.settings_id(user["tenant_id"], le, year, month)},
                                                        {"$set": {**upd, "tenant_id": user["tenant_id"], "legal_entity_id": le or "GROUP", "year": year, "month": month, "updated_at": now.isoformat(), "updated_by": user["id"]}}, upsert=True)
    await record_audit(action="sustainability.settings_update", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="pricing_sustainability_settings", entity_id=f"{le or 'GROUP'}:{year}:{month}", after=upd)
    return await eng.overview(db, user["tenant_id"], le)


@router.get("/quote/{qid}")
async def quote_sustainability(qid: str, discount_percent: Optional[float] = None, user: dict = Depends(require_permission("quotes.view"))):
    """ADMIN ONLY: box SOSTENIBILITÀ COMMESSA. Il commerciale riceve solo indicatori autorizzati (stato semaforo senza importi)."""
    db = get_db()
    q = await db.quotes.find_one({"_id": qid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not q:
        raise HTTPException(404, "Preventivo non trovato")
    ov = await eng.overview(db, user["tenant_id"], q.get("legal_entity_id"))
    ev = eng.evaluate_quote(q, ov["plan"])
    perms = await _get_perms(user)
    if ADMIN_MASTER_MARKER not in perms:
        return {"status": ev["status"], "direct_margin_ok": ev["direct_margin_ok"], "status_meaning": "MARGINE OK" if ev["direct_margin_ok"] else "APPROVAZIONE RICHIESTA", "is_admin_view": False}
    out = {**ev, "is_admin_view": True, "fixed_cost_reconciliation": ov["fixed_cost_registry"]["reconciliation_status"]}
    if discount_percent is not None:
        out["discount_impact"] = eng.discount_impact(q, ov["plan"], float(discount_percent))
    return out


@router.post("/simulate")
async def simulate(body: SimulateBody, user: dict = Depends(require_permission("treasury.view"))):
    ov = await eng.overview(get_db(), user["tenant_id"], body.legal_entity_id)
    plan, s = ov["plan"], ov["settings"]
    afc = body.annual_fixed_costs if body.annual_fixed_costs is not None else plan.get("annual_fixed_cost_target")
    if afc is None:
        raise HTTPException(400, {"code": "FIXED_COSTS_MISSING", "message": "PRICING SUSTAINABILITY = INCOMPLETE: nessun costo fisso registrato"})
    return eng.simulate(annual_fixed_costs=float(afc), coverage_months=body.coverage_months or plan["months_remaining"], expected_monthly_jobs=body.expected_monthly_jobs or s.get("expected_monthly_jobs"),
                        expected_monthly_revenue=body.expected_monthly_revenue or s.get("expected_monthly_revenue"), average_ticket=body.average_ticket,
                        average_contribution_pct=body.average_contribution_pct if body.average_contribution_pct is not None else (s.get("average_contribution_pct") or 27.0),
                        close_rate=body.close_rate if body.close_rate is not None else s.get("current_close_rate"), target_profit=float(body.target_profit if body.target_profit is not None else (s.get("target_profit") or 0)),
                        secured_ytd=float(ov["secured"]["secured_ytd"] or 0))


class DemoBody(BaseModel):
    is_demo: bool = True
    ids: Optional[list] = None  # None → tutti i costi fissi + personale della tenant


@router.post("/fixed-costs/mark-demo")
async def mark_demo(body: DemoBody, request: Request, user: dict = Depends(require_permission("treasury.manage"))):
    """FIXED COST DATA GATE: marca demo_data=true/false (mai cancellazione automatica). Senza ids → tutta la tenant."""
    db = get_db()
    flt = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if body.ids:
        flt["_id"] = {"$in": body.ids}
    upd = {"$set": {"is_demo": body.is_demo, "updated_at": datetime.now(timezone.utc).isoformat()}}
    r1 = await db.fixed_costs.update_many(flt, upd)
    r2 = await db.personnel_costs.update_many(flt, upd)
    await record_audit(action="sustainability.mark_demo", tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"], ip=get_client_ip(request), entity_type="fixed_costs", entity_id="bulk", after={"is_demo": body.is_demo, "ids": body.ids, "fixed": r1.modified_count, "personnel": r2.modified_count})
    return {"fixed_costs_updated": r1.modified_count, "personnel_costs_updated": r2.modified_count, "registry": {k: v for k, v in (await eng.fixed_cost_registry(db, user["tenant_id"], None)).items() if k != "items"}}
