"""Management Control router — costi fissi, personale, scadenziario, budget, break-even, simulator."""
from __future__ import annotations
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import get_db
from app.deps import get_current_user, require_permission
from app.mongo_utils import to_mongo, from_mongo
from app.models import utcnow
from app.services.ops_common import create_doc, list_docs, update_doc, soft_delete_doc
from app.services.module_gating import require_module
from app.services.breakeven import compute_budget_outputs, PRESET_SCENARIOS
from app.services.consolidation import compute_consolidation
from app.models_control import (
    FixedCost, FixedCostCreate, FixedCostUpdate,
    PersonnelCost, PersonnelCostCreate, PersonnelCostUpdate,
    ManagementAccount, Payable, PayableCreate, PayableUpdate, Receivable,
    BudgetScenario, BudgetScenarioCreate, BudgetInputs, BudgetOutputs,
    BudgetSimulationRequest, Investment,
)
from app.routers.legal_entities import get_user_legal_entity_ids


router = APIRouter(prefix="/control", tags=["Management Control"])


def _monthly_amount(amount: float, recurrence: str) -> float:
    if recurrence == "monthly": return amount
    if recurrence == "quarterly": return amount / 3.0
    if recurrence == "yearly": return amount / 12.0
    if recurrence == "one_off": return 0.0
    return amount


def _monthly_personnel(p: PersonnelCost) -> float:
    monthly_gross = p.ral_yearly / 12.0 if p.ral_yearly else p.monthly_gross
    charges = monthly_gross * (p.social_charges_pct / 100.0)
    return round(monthly_gross + charges + p.monthly_indirect, 2)


async def _entity_filter(user: dict, legal_entity_id: Optional[str] = None) -> Dict[str, Any]:
    scope = await get_user_legal_entity_ids(user)
    if legal_entity_id:
        if scope is not None and legal_entity_id not in scope:
            raise HTTPException(403, "Nessun accesso a questa società")
        return {"legal_entity_id": legal_entity_id}
    if scope is not None:
        return {"legal_entity_id": {"$in": scope}}
    return {}


# ============================================================
# FIXED COSTS
# ============================================================
@router.get("/fixed-costs")
async def list_fixed(legal_entity_id: Optional[str] = None,
                     user: dict = Depends(require_module("management_control"))):
    filters = await _entity_filter(user, legal_entity_id)
    return await list_docs(collection="fixed_costs", tenant_id=user["tenant_id"],
                            filters=filters, sort=[("category", 1), ("label", 1)], limit=300)


@router.post("/fixed-costs")
async def create_fixed(payload: FixedCostCreate,
                        user: dict = Depends(require_module("management_control", write=True))):
    d = payload.model_dump()
    amount_monthly = _monthly_amount(d["amount_raw"], d.get("recurrence", "monthly"))
    inst = FixedCost(**d, amount_monthly=amount_monthly)
    return await create_doc(collection="fixed_costs", model_instance=inst,
                             user=user, entity_type="fixed_cost", ip="")


@router.patch("/fixed-costs/{fid}")
async def update_fixed(fid: str, payload: FixedCostUpdate,
                        user: dict = Depends(require_module("management_control", write=True))):
    updates = payload.model_dump(exclude_unset=True)
    if "amount_raw" in updates or "recurrence" in updates:
        db = get_db()
        prev = await db.fixed_costs.find_one({"_id": fid, "tenant_id": user["tenant_id"]})
        if prev:
            raw = updates.get("amount_raw", prev.get("amount_raw", 0))
            rec = updates.get("recurrence", prev.get("recurrence", "monthly"))
            updates["amount_monthly"] = _monthly_amount(raw, rec)
    return await update_doc(collection="fixed_costs", doc_id=fid, updates=updates,
                             user=user, entity_type="fixed_cost", ip="")


@router.delete("/fixed-costs/{fid}")
async def delete_fixed(fid: str, user: dict = Depends(require_module("management_control", write=True))):
    return await soft_delete_doc(collection="fixed_costs", doc_id=fid, user=user,
                                  entity_type="fixed_cost", ip="")


# ============================================================
# PERSONNEL COSTS
# ============================================================
@router.get("/personnel-costs")
async def list_personnel(legal_entity_id: Optional[str] = None,
                          user: dict = Depends(require_module("management_control"))):
    filters = await _entity_filter(user, legal_entity_id)
    return await list_docs(collection="personnel_costs", tenant_id=user["tenant_id"],
                            filters=filters, sort=[("department", 1), ("full_name", 1)], limit=300)


@router.post("/personnel-costs")
async def create_personnel(payload: PersonnelCostCreate,
                            user: dict = Depends(require_module("management_control", write=True))):
    d = payload.model_dump()
    monthly_gross = (d.get("ral_yearly") or 0) / 12.0
    social = monthly_gross * ((d.get("social_charges_pct") or 30) / 100.0)
    total = round(monthly_gross + social + (d.get("monthly_indirect") or 0), 2)
    inst = PersonnelCost(**d, monthly_gross=round(monthly_gross, 2),
                          monthly_total_cost=total)
    return await create_doc(collection="personnel_costs", model_instance=inst,
                             user=user, entity_type="personnel_cost", ip="")


@router.patch("/personnel-costs/{pid}")
async def update_personnel(pid: str, payload: PersonnelCostUpdate,
                            user: dict = Depends(require_module("management_control", write=True))):
    updates = payload.model_dump(exclude_unset=True)
    db = get_db()
    prev = await db.personnel_costs.find_one({"_id": pid, "tenant_id": user["tenant_id"]})
    if prev:
        ral = updates.get("ral_yearly", prev.get("ral_yearly", 0))
        sc = updates.get("social_charges_pct", prev.get("social_charges_pct", 30))
        mi = updates.get("monthly_indirect", prev.get("monthly_indirect", 0))
        monthly_gross = ral / 12.0
        total = round(monthly_gross + monthly_gross * sc / 100.0 + mi, 2)
        updates["monthly_gross"] = round(monthly_gross, 2)
        updates["monthly_total_cost"] = total
    return await update_doc(collection="personnel_costs", doc_id=pid, updates=updates,
                             user=user, entity_type="personnel_cost", ip="")


@router.delete("/personnel-costs/{pid}")
async def delete_personnel(pid: str, user: dict = Depends(require_module("management_control", write=True))):
    return await soft_delete_doc(collection="personnel_costs", doc_id=pid, user=user,
                                  entity_type="personnel_cost", ip="")


# ============================================================
# MANAGEMENT CHART OF ACCOUNTS
# ============================================================
@router.get("/accounts")
async def list_accounts(user: dict = Depends(require_module("management_control"))):
    return await list_docs(collection="management_accounts", tenant_id=user["tenant_id"],
                            sort=[("kind", 1), ("sort_order", 1)], limit=500)


@router.post("/accounts")
async def create_account(payload: dict,
                          user: dict = Depends(require_module("management_control", write=True))):
    inst = ManagementAccount(tenant_id=user["tenant_id"], **payload)
    return await create_doc(collection="management_accounts", model_instance=inst,
                             user=user, entity_type="management_account", ip="")


# ============================================================
# PAYABLES / RECEIVABLES (Scadenziario)
# ============================================================
@router.get("/payables")
async def list_payables(status: Optional[str] = None,
                         legal_entity_id: Optional[str] = None,
                         user: dict = Depends(require_module("management_control"))):
    filters = await _entity_filter(user, legal_entity_id)
    if status: filters["payable_status"] = status
    return await list_docs(collection="payables", tenant_id=user["tenant_id"],
                            filters=filters, sort=[("due_date", 1)], limit=500)


@router.post("/payables")
async def create_payable(payload: PayableCreate,
                          user: dict = Depends(require_module("management_control", write=True))):
    d = payload.model_dump()
    inst = Payable(**d, residual=d["amount_gross"], payable_status="planned")
    return await create_doc(collection="payables", model_instance=inst,
                             user=user, entity_type="payable", ip="")


@router.patch("/payables/{pid}")
async def update_payable(pid: str, payload: PayableUpdate,
                          user: dict = Depends(require_module("management_control", write=True))):
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("priority") and updates["priority"] not in ("CRITICAL", "IMPORTANT", "DEFERRABLE", "DISCRETIONARY"):
        raise HTTPException(400, {"code": "PRIORITY_INVALID"})
    if "due_date" in updates and updates["due_date"]:
        updates["due_date"] = updates["due_date"].isoformat()
    return await update_doc(collection="payables", doc_id=pid, updates=updates,
                             user=user, entity_type="payable", ip="")


@router.post("/payables/{pid}/pay")
async def pay_payable(pid: str, payload: dict,
                       user: dict = Depends(require_module("management_control", write=True))):
    db = get_db()
    prev = await db.payables.find_one({"_id": pid, "tenant_id": user["tenant_id"]})
    if not prev:
        raise HTTPException(404, "Debito non trovato")
    amount = float(payload.get("amount", 0))
    paid_new = float(prev.get("amount_paid") or 0) + amount
    residual = max(0.0, float(prev.get("amount_gross") or 0) - paid_new)
    status = "partially_paid" if residual > 0 else "paid"
    await db.payables.update_one({"_id": pid},
        {"$set": {"amount_paid": paid_new, "residual": residual, "paid_at": utcnow().isoformat(),
                   "payable_status": status, "updated_at": utcnow().isoformat()}})
    return from_mongo(await db.payables.find_one({"_id": pid}))


# ============================================================
# BUDGET SCENARIOS + WHAT-IF SIMULATOR
# ============================================================
@router.get("/budget/preset-scenarios")
async def preset_scenarios(user: dict = Depends(require_module("management_control"))):
    """Ritorna i tre scenari predefiniti (Base, Prudente, Crescita)."""
    return PRESET_SCENARIOS


@router.get("/budget/scenarios")
async def list_scenarios(year: Optional[int] = None,
                          legal_entity_id: Optional[str] = None,
                          user: dict = Depends(require_module("management_control"))):
    filters = await _entity_filter(user, legal_entity_id)
    if year: filters["year"] = year
    return await list_docs(collection="budget_scenarios", tenant_id=user["tenant_id"],
                            filters=filters, sort=[("year", -1), ("created_at", -1)], limit=100)


@router.post("/budget/scenarios")
async def create_scenario(payload: BudgetScenarioCreate,
                           user: dict = Depends(require_module("management_control", write=True))):
    d = payload.model_dump()
    outputs = compute_budget_outputs(BudgetInputs(**d["inputs"]))
    inst = BudgetScenario(**d, outputs=outputs)
    return await create_doc(collection="budget_scenarios", model_instance=inst,
                             user=user, entity_type="budget_scenario", ip="")


@router.post("/budget/simulate")
async def simulate(payload: BudgetSimulationRequest,
                    user: dict = Depends(require_module("management_control"))):
    """Simulatore what-if. Non salva sul budget approvato senza save_as_scenario=True."""
    outputs = compute_budget_outputs(payload.inputs)
    if payload.save_as_scenario:
        inst = BudgetScenario(
            tenant_id=user["tenant_id"],
            label=payload.label or "Simulazione custom",
            year=payload.year,
            scenario_kind=payload.scenario_kind or "custom",
            legal_entity_id=payload.legal_entity_id,
            inputs=payload.inputs, outputs=outputs,
            created_by=user["id"], updated_by=user["id"],
        )
        db = get_db()
        await db.budget_scenarios.insert_one(to_mongo(inst.model_dump(by_alias=True)))
        return {"outputs": outputs.model_dump(), "scenario_id": inst.id, "saved": True}
    return {"outputs": outputs.model_dump(), "saved": False}


@router.post("/budget/scenarios/{sid}/approve")
async def approve_scenario(sid: str,
                            user: dict = Depends(require_module("management_control", write=True))):
    db = get_db()
    await db.budget_scenarios.update_one({"_id": sid, "tenant_id": user["tenant_id"]},
        {"$set": {"approved": True, "approved_at": utcnow().isoformat(),
                   "approved_by": user["id"]}})
    return {"ok": True}


@router.post("/budget/scenarios/{sid}/promote-forecast")
async def promote_forecast(sid: str,
                            user: dict = Depends(require_module("management_control", write=True))):
    db = get_db()
    await db.budget_scenarios.update_one({"_id": sid, "tenant_id": user["tenant_id"]},
        {"$set": {"promoted_to_forecast": True}})
    return {"ok": True}


@router.post("/budget/scenarios/{sid}/duplicate")
async def duplicate_scenario(sid: str, payload: dict,
                              user: dict = Depends(require_module("management_control", write=True))):
    db = get_db()
    src = await db.budget_scenarios.find_one({"_id": sid, "tenant_id": user["tenant_id"]})
    if not src:
        raise HTTPException(404, "Scenario non trovato")
    new_inst = BudgetScenario(
        tenant_id=user["tenant_id"],
        label=payload.get("label", (src.get("label") or "Copia") + " (copia)"),
        year=src.get("year"),
        scenario_kind=payload.get("scenario_kind", "custom"),
        legal_entity_id=src.get("legal_entity_id"),
        inputs=BudgetInputs(**(src.get("inputs") or {})),
        outputs=BudgetOutputs(**(src.get("outputs") or {})),
        parent_scenario_id=sid,
        created_by=user["id"], updated_by=user["id"],
    )
    await db.budget_scenarios.insert_one(to_mongo(new_inst.model_dump(by_alias=True)))
    return new_inst.model_dump()


# ============================================================
# BREAK-EVEN direct compute
# ============================================================
@router.post("/breakeven/compute")
async def breakeven_compute(payload: BudgetInputs,
                             user: dict = Depends(require_module("management_control"))):
    outputs = compute_budget_outputs(payload)
    return outputs.model_dump()


# ============================================================
# CONSOLIDATION
# ============================================================
@router.get("/consolidation")
async def consolidation(period_from: Optional[str] = None, period_to: Optional[str] = None,
                         user: dict = Depends(require_module("multi_company"))):
    return await compute_consolidation(user["tenant_id"], period_from, period_to)


# ============================================================
# INVESTMENTS
# ============================================================
@router.get("/investments")
async def list_investments(user: dict = Depends(require_module("management_control"))):
    return await list_docs(collection="investments", tenant_id=user["tenant_id"],
                            sort=[("start_date", -1)], limit=100)


@router.post("/investments")
async def create_investment(payload: dict,
                             user: dict = Depends(require_module("management_control", write=True))):
    amount = float(payload.get("amount", 0))
    years = int(payload.get("depreciation_years", 5)) or 5
    payload["monthly_depreciation"] = round(amount / (years * 12), 2) if amount and years else 0.0
    inst = Investment(tenant_id=user["tenant_id"], **payload)
    return await create_doc(collection="investments", model_instance=inst,
                             user=user, entity_type="investment", ip="")


# ============================================================
# CFO DASHBOARD (KPI aggregati)
# ============================================================
@router.get("/dashboard")
async def cfo_dashboard(legal_entity_id: Optional[str] = None,
                         user: dict = Depends(require_module("management_control"))):
    db = get_db()
    tid = user["tenant_id"]
    filters = await _entity_filter(user, legal_entity_id)
    base = {"tenant_id": tid, "deleted_at": None, **filters}
    # Aggregate
    fixed = await db.fixed_costs.aggregate([{"$match": {**base, "active": True}},
        {"$group": {"_id": "$category", "sum": {"$sum": "$amount_monthly"}}}]).to_list(50)
    personnel = await db.personnel_costs.aggregate([{"$match": {**base, "active": True}},
        {"$group": {"_id": "$department", "sum": {"$sum": "$monthly_total_cost"}}}]).to_list(50)
    payables = await db.payables.aggregate([{"$match": {**base,
        "payable_status": {"$nin": ["paid", "cancelled"]}}},
        {"$group": {"_id": "$payable_status", "sum": {"$sum": "$residual"},
                     "count": {"$sum": 1}}}]).to_list(50)
    scenarios = await db.budget_scenarios.find({**base}).sort([("created_at", -1)]).limit(3).to_list(3)
    total_fixed_month = sum(float(x["sum"]) for x in fixed)
    total_personnel_month = sum(float(x["sum"]) for x in personnel)
    total_payables = sum(float(x["sum"]) for x in payables)
    return {
        "fixed_by_category": [{"category": x["_id"], "monthly": round(float(x["sum"]), 2)} for x in fixed],
        "personnel_by_department": [{"department": x["_id"] or "Non assegnato",
                                        "monthly": round(float(x["sum"]), 2)} for x in personnel],
        "payables_by_status": [{"status": x["_id"], "residual": round(float(x["sum"]), 2),
                                  "count": x["count"]} for x in payables],
        "totals": {
            "fixed_month": round(total_fixed_month, 2),
            "personnel_month": round(total_personnel_month, 2),
            "structure_month": round(total_fixed_month + total_personnel_month, 2),
            "structure_year": round((total_fixed_month + total_personnel_month) * 12, 2),
            "payables_residual": round(total_payables, 2),
        },
        "recent_scenarios": [from_mongo(s) for s in scenarios],
    }
