"""PRICING SUSTAINABILITY ENGINE V1 — costi fissi come parte del controllo prezzi.
Verità unica: CONTRIBUTION = margin_engine.post_margin_amount (ricavo netto IVA − tutti i costi diretti incl. commissione/ritenuta);
FIXED COSTS = registry `fixed_costs` (CFO → COSTI FISSI); SETTINGS = pricing_sustainability_settings. Nessuna modifica automatica ai prezzi."""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.margin_engine import MARGIN_FLOOR_PERCENT, compute_financial_snapshot

PO_REFERENCE_ANNUAL_FIXED_COST = 506627.60
PLANNING_MODES = ("JOB_COUNT_MODE", "REVENUE_VOLUME_MODE", "HYBRID_MODE")
SCENARIO_PRESETS = {"CONSERVATIVE": {"expected_monthly_jobs": 15, "expected_monthly_revenue": 150000}, "BASE": {"expected_monthly_jobs": 25, "expected_monthly_revenue": 250000},
                    "AGGRESSIVE": {"expected_monthly_jobs": 35, "expected_monthly_revenue": 350000}}
# COST CLASSIFICATION (PO): 4 classi economiche. Solo FIXED_STRUCTURE_COST alimenta lo Structural Coverage Engine.
COST_CLASSES = ("FIXED_STRUCTURE_COST", "DIRECT_JOB_COST", "SEMI_VARIABLE_COST", "CASH_ONLY_FINANCIAL_COST")
_CLASS_BY_CATEGORY = {"rent": "FIXED_STRUCTURE_COST", "insurance": "FIXED_STRUCTURE_COST", "software": "FIXED_STRUCTURE_COST", "consulting": "FIXED_STRUCTURE_COST", "leasing": "FIXED_STRUCTURE_COST",
                      "admin": "FIXED_STRUCTURE_COST", "administration": "FIXED_STRUCTURE_COST", "marketing": "FIXED_STRUCTURE_COST", "telephony": "FIXED_STRUCTURE_COST", "overhead": "FIXED_STRUCTURE_COST", "personnel": "FIXED_STRUCTURE_COST",
                      "utilities": "SEMI_VARIABLE_COST", "energy": "SEMI_VARIABLE_COST", "fuel": "SEMI_VARIABLE_COST", "advertising": "SEMI_VARIABLE_COST", "maintenance": "SEMI_VARIABLE_COST", "outsourcing": "SEMI_VARIABLE_COST", "overtime": "SEMI_VARIABLE_COST",
                      "tax": "CASH_ONLY_FINANCIAL_COST", "f24": "CASH_ONLY_FINANCIAL_COST", "financing": "CASH_ONLY_FINANCIAL_COST", "interest": "CASH_ONLY_FINANCIAL_COST", "debt": "CASH_ONLY_FINANCIAL_COST", "loan": "CASH_ONLY_FINANCIAL_COST",
                      "consumables": "DIRECT_JOB_COST", "logistics": "DIRECT_JOB_COST", "installation": "DIRECT_JOB_COST", "dismantling": "DIRECT_JOB_COST", "crane": "DIRECT_JOB_COST", "transport": "DIRECT_JOB_COST"}
EMPLOYEE_COST_MODES = ("ALL_IN_COMPANY_COST", "PAYROLL_ONLY", "MANUAL_BREAKDOWN")


def classify_cost(doc: dict) -> str:
    return doc.get("cost_class") if doc.get("cost_class") in COST_CLASSES else _CLASS_BY_CATEGORY.get(str(doc.get("category") or "").lower(), "FIXED_STRUCTURE_COST")


def structural_monthly(doc: dict, monthly: float) -> float:
    """Quota mensile che entra nello Structural Coverage: FIXED 100%; SEMI_VARIABLE solo fixed_component configurato; DIRECT/CASH_ONLY 0."""
    cls = classify_cost(doc)
    if cls == "FIXED_STRUCTURE_COST":
        return monthly
    if cls == "SEMI_VARIABLE_COST":
        if doc.get("fixed_component") is not None:
            return float(doc["fixed_component"])
        if doc.get("fixed_component_pct") is not None:
            return monthly * float(doc["fixed_component_pct"]) / 100
    return 0.0


def personnel_company_cost(p: dict) -> Dict[str, Any]:
    """Costo azienda personale: ALL_IN → valore PO già omnicomprensivo (nessun onere aggiunto). PAYROLL_ONLY/MANUAL → oneri SOLO se inseriti esplicitamente."""
    mode = p.get("employee_cost_mode") if p.get("employee_cost_mode") in EMPLOYEE_COST_MODES else "ALL_IN_COMPANY_COST"
    base = float(p.get("monthly_total_cost") or 0)
    charges = float(p.get("employer_charges_monthly") or 0) if mode != "ALL_IN_COMPANY_COST" else 0.0
    return {"mode": mode, "monthly_company_cost": base + charges, "charges_added": charges}


_RECURRENCE_MONTHS = {"monthly": 1, "bimonthly": 2, "quarterly": 3, "semiannual": 6, "annual": 12, "yearly": 12}


def _r2(v):
    return None if v is None else round(float(v), 2)


# ---------------- 1. FIXED COST SOURCE OF TRUTH ----------------
async def fixed_cost_registry(db, tenant_id: str, le: Optional[str] = None) -> Dict[str, Any]:
    docs = await db.fixed_costs.find({"tenant_id": tenant_id, "deleted_at": None}).to_list(2000)
    items, monthly, by_class = [], 0.0, {c: 0.0 for c in COST_CLASSES}
    for f in docs:
        if le and (f.get("legal_entity_id") or None) not in (le, None):
            continue
        active = f.get("active", True) and f.get("status", "active") != "inactive"
        m = float(f.get("amount_monthly") or 0)
        if not m and f.get("amount_raw"):
            m = float(f["amount_raw"]) / _RECURRENCE_MONTHS.get(str(f.get("recurrence") or "monthly").lower(), 1)
        cls = classify_cost(f)
        sm = structural_monthly(f, m)
        items.append({"id": f["_id"], "label": f.get("label"), "category": f.get("category"), "cost_class": cls, "legal_entity_id": f.get("legal_entity_id"), "supplier": f.get("supplier"), "amount_raw": f.get("amount_raw"),
                      "recurrence": f.get("recurrence"), "monthly_equivalent": _r2(m), "structural_monthly": _r2(sm), "annual_equivalent": _r2(m * 12), "start_date": f.get("start_date"), "end_date": f.get("end_date"),
                      "source": "fixed_costs" if not f.get("is_demo") else "fixed_costs(demo)", "budget": f.get("budget"), "actual": f.get("actual"), "notes": f.get("notes"), "status": "active" if active else "inactive"})
        if active:
            by_class[cls] = by_class.get(cls, 0.0) + m
            monthly += sm
    # STRUCTURAL COSTS include il personale di struttura (registry personnel_costs) — stessa fonte usata dal CFO (no doppio conteggio: payroll non è in fixed_costs)
    for p in await db.personnel_costs.find({"tenant_id": tenant_id, "deleted_at": None, "active": {"$ne": False}}).to_list(2000):
        if le and (p.get("legal_entity_id") or None) not in (le, None):
            continue
        pc = personnel_company_cost(p)
        m = pc["monthly_company_cost"]
        items.append({"id": p["_id"], "label": p.get("role") or p.get("label") or p.get("full_name") or "Personale struttura", "category": "PERSONALE_STRUTTURA", "cost_class": "FIXED_STRUCTURE_COST", "employee_cost_mode": pc["mode"],
                      "legal_entity_id": p.get("legal_entity_id"), "supplier": None, "amount_raw": m, "recurrence": "monthly", "monthly_equivalent": _r2(m), "structural_monthly": _r2(m), "annual_equivalent": _r2(m * 12), "source": "personnel_costs", "status": "active"})
        by_class["FIXED_STRUCTURE_COST"] += m
        monthly += m
    annual = _r2(monthly * 12)
    diff = _r2(annual - PO_REFERENCE_ANNUAL_FIXED_COST)
    return {"items": items, "count": len(items), "monthly_total": _r2(monthly), "annual_total": annual, "po_reference_annual": PO_REFERENCE_ANNUAL_FIXED_COST,
            "monthly_by_class": {k: _r2(v) for k, v in by_class.items()}, "structural_basis": "FIXED_STRUCTURE_COST + fixed_component dei SEMI_VARIABLE; DIRECT_JOB_COST → Margin Engine commessa; CASH_ONLY → solo cash flow",
            "reconciliation_diff": diff, "reconciliation_status": "COMPLETE" if abs(diff) < 1.0 else "INCOMPLETE", "demo_items": sum(1 for f in docs if f.get("is_demo"))}


# ---------------- settings ----------------
DEFAULT_SETTINGS = {"annual_fixed_cost_target": None, "structure_coverage_target_date": None, "expected_monthly_jobs": None, "expected_monthly_revenue": None,
                    "target_monthly_revenue": None, "target_monthly_contribution": None, "target_profit": None, "planning_mode": "HYBRID_MODE", "current_close_rate": None, "expected_close_rate": None}


def settings_id(tenant_id: str, le: Optional[str], year: int, month: int) -> str:
    return f"{tenant_id}:{le or 'GROUP'}:{year}:{month:02d}"


async def load_settings(db, tenant_id: str, le: Optional[str], year: int, month: int) -> Dict[str, Any]:
    doc = await db.pricing_sustainability_settings.find_one({"_id": settings_id(tenant_id, le, year, month)})
    if not doc:  # fallback: ultimo mese configurato della stessa entity (il piano non si resetta da solo)
        doc = await db.pricing_sustainability_settings.find_one({"tenant_id": tenant_id, "legal_entity_id": le or "GROUP", "year": year}, sort=[("month", -1)])
    out = {**DEFAULT_SETTINGS, **{k: (doc or {}).get(k) for k in DEFAULT_SETTINGS if doc and k in doc}}
    out.update({"legal_entity_id": le or "GROUP", "year": year, "month": month, "configured": bool(doc), "inherited_from_month": (doc or {}).get("month") if doc and doc.get("month") != month else None})
    return out


# ---------------- 2. CONTRIBUTION SOURCE OF TRUTH ----------------
def quote_contribution(quote: dict) -> Dict[str, Any]:
    fs = quote.get("financial_snapshot") or {}
    if fs.get("post_margin_amount") is None:
        fs = compute_financial_snapshot(quote)
    net = float(fs.get("net_revenue_ex_vat") or quote.get("subtotal") or 0)
    contrib = fs.get("post_margin_amount")
    direct = _r2(net - float(contrib)) if contrib is not None else None
    return {"net_revenue_ex_vat": _r2(net), "direct_costs": direct, "contribution_margin_amount": _r2(contrib), "contribution_margin_percent": fs.get("post_margin_percent"),
            "direct_margin_ok": fs.get("post_margin_percent") is not None and float(fs["post_margin_percent"]) > MARGIN_FLOOR_PERCENT, "complete": contrib is not None and net > 0}


async def secured_contribution(db, tenant_id: str, le: Optional[str], year: int) -> Dict[str, Any]:
    """SECURED = contratti firmati nell'anno con quote economicamente completa. FORECAST = preventivi aperti (mai conteggiati come acquisito)."""
    by_month: Dict[int, float] = {}
    total, n, legacy = 0.0, 0, 0
    async for c in db.contracts.find({"tenant_id": tenant_id, "deleted_at": None, "contract_status": "signed"}, {"quote_id": 1, "signed_at": 1, "legal_entity_id": 1}):
        if le and (c.get("legal_entity_id") or None) not in (le, None):
            continue
        sd = c.get("signed_at")
        try:
            d = datetime.fromisoformat(str(sd).replace("Z", "+00:00")).date() if sd else None
        except ValueError:
            d = None
        if not d or d.year != year:
            continue
        q = await db.quotes.find_one({"_id": c.get("quote_id")}, {"financial_snapshot": 1, "subtotal": 1, "lines": 1, "logistics_services": 1}) if c.get("quote_id") else None
        qc = quote_contribution(q) if q else None
        if not qc or not qc["complete"]:
            legacy += 1
            continue
        total += qc["contribution_margin_amount"]
        by_month[d.month] = by_month.get(d.month, 0.0) + qc["contribution_margin_amount"]
        n += 1
    pipeline = 0.0
    async for q in db.quotes.find({"tenant_id": tenant_id, "deleted_at": None, "quote_status": {"$in": ["sent", "approved", "negotiation"]}, "financial_snapshot.post_margin_amount": {"$ne": None}}, {"financial_snapshot.post_margin_amount": 1}):
        pipeline += float(q["financial_snapshot"]["post_margin_amount"] or 0)
    return {"secured_ytd": _r2(total), "secured_by_month": {str(k): _r2(v) for k, v in sorted(by_month.items())}, "signed_contracts_counted": n, "legacy_excluded": legacy, "forecast_pipeline_contribution": _r2(pipeline)}


# ---------------- 3. PLANNING MODEL ----------------
def planning_model(settings: Dict[str, Any], registry: Dict[str, Any], secured: Dict[str, Any], today: date) -> Dict[str, Any]:
    annual_target = settings.get("annual_fixed_cost_target") or registry["annual_total"] or None
    profit = float(settings.get("target_profit") or 0)
    secured_ytd = float(secured.get("secured_ytd") or 0)
    cover_by = None
    if settings.get("structure_coverage_target_date"):
        try:
            cover_by = date.fromisoformat(str(settings["structure_coverage_target_date"])[:10])
        except ValueError:
            cover_by = None
    year_end = date(today.year, 12, 31)
    horizon_end = cover_by or year_end
    months_remaining = max(1, (horizon_end.year - today.year) * 12 + horizon_end.month - today.month + 1)
    residual = None if annual_target is None else max(0.0, float(annual_target) - secured_ytd)
    # fabbisogno mensile struttura: residuo annuo / mesi rimanenti al target di copertura (gennaio sopra target → febbraio parte con residuo inferiore)
    monthly_target = None if residual is None else _r2(residual / months_remaining)
    if settings.get("target_monthly_contribution"):
        monthly_target = float(settings["target_monthly_contribution"])
    jobs, rev = settings.get("expected_monthly_jobs"), settings.get("expected_monthly_revenue")
    per_job = _r2(monthly_target / float(jobs)) if monthly_target is not None and jobs else None
    rate = _r2(monthly_target / float(rev) * 100) if monthly_target is not None and rev else None
    phase = "PROFIT_GENERATION_PHASE" if (annual_target is not None and secured_ytd >= float(annual_target)) else "STRUCTURE_COVERAGE_PHASE"
    coverage_pct = _r2(min(100.0, secured_ytd / float(annual_target) * 100)) if annual_target else None
    # forecast data copertura: ritmo medio mensile secured YTD
    months_elapsed = max(1, today.month)
    pace = secured_ytd / months_elapsed
    forecast_cov = None
    if residual is not None and residual > 0 and pace > 0:
        m_needed = math.ceil(residual / pace)
        y, m = today.year + (today.month + m_needed - 1) // 12, (today.month + m_needed - 1) % 12 + 1
        forecast_cov = date(y, m, 1).isoformat()
    elif residual == 0:
        forecast_cov = "COVERED"
    missing = [k for k, v in (("fixed_costs", annual_target), ("expected_monthly_jobs", jobs), ("expected_monthly_revenue", rev)) if not v]
    return {"planning_mode": settings.get("planning_mode") or "HYBRID_MODE", "annual_fixed_cost_target": _r2(annual_target), "annual_target_profit": _r2(profit), "total_contribution_target": _r2((annual_target or 0) + profit) if annual_target else None,
            "secured_contribution_ytd": _r2(secured_ytd), "structure_coverage_percent": coverage_pct, "structure_residual": _r2(residual), "profit_target_remaining": _r2(max(0.0, (annual_target or 0) + profit - secured_ytd)) if annual_target else None,
            "phase": phase, "coverage_target_date": horizon_end.isoformat(), "months_remaining": months_remaining, "monthly_structure_coverage_target": monthly_target,
            "expected_monthly_jobs": jobs, "expected_monthly_revenue": rev, "required_structure_contribution_per_job": per_job, "required_structure_margin_rate_percent": rate,
            "forecast_coverage_date": forecast_cov, "data_quality": "COMPLETE" if not missing else "INCOMPLETE", "missing": missing,
            "monthly": {"target_contribution_month": monthly_target, "actual_contribution_month": _r2(secured.get("secured_by_month", {}).get(str(today.month), 0.0)),
                        "month_gap": _r2(float(secured.get("secured_by_month", {}).get(str(today.month), 0.0)) - monthly_target) if monthly_target is not None else None, "cumulative_coverage": _r2(secured_ytd)}}


# ---------------- 4. SUSTAINABILITY ENGINE (per quote) ----------------
def evaluate_quote(quote: dict, plan: Dict[str, Any]) -> Dict[str, Any]:
    qc = quote_contribution(quote)
    net, contrib, direct = qc["net_revenue_ex_vat"], qc["contribution_margin_amount"], qc["direct_costs"]
    per_job, rate = plan.get("required_structure_contribution_per_job"), plan.get("required_structure_margin_rate_percent")
    req_job = per_job
    req_rev = _r2(net * rate / 100) if rate is not None else None
    mode = plan.get("planning_mode") or "HYBRID_MODE"
    required = req_job if mode == "JOB_COUNT_MODE" else (req_rev if mode == "REVENUE_VOLUME_MODE" else (max(x for x in (req_job, req_rev) if x is not None) if (req_job is not None or req_rev is not None) else None))
    gap = _r2(contrib - required) if (contrib is not None and required is not None) else None
    if not qc["complete"]:
        status = "INCOMPLETE"
    elif not qc["direct_margin_ok"]:
        status = "RED"
    elif required is None:
        status = "INCOMPLETE"
    else:
        status = "GREEN" if gap >= 0 else "ORANGE"
    # prezzi direzionali (mai applicati automaticamente)
    min_direct = _r2(direct / (1 - MARGIN_FLOOR_PERCENT / 100)) if direct is not None else None
    structural_target_price = _r2(direct + required) if (direct is not None and required is not None) else None
    if structural_target_price is not None and min_direct is not None and structural_target_price < min_direct:
        structural_target_price = min_direct
    monthly = plan.get("monthly") or {}
    secured_m = float(monthly.get("actual_contribution_month") or 0)
    target_m = monthly.get("target_contribution_month")
    return {**qc, "planning_mode": mode, "required_structure_contribution": required, "required_by_job_count": req_job, "required_by_revenue_volume": req_rev,
            "hybrid_delta": _r2(req_job - req_rev) if (req_job is not None and req_rev is not None) else None, "sustainability_gap": gap, "status": status,
            "status_meaning": {"GREEN": "Vendita coerente con il piano aziendale", "ORANGE": "MANAGEMENT WARNING: contribution positivo ma sotto il target strutturale (non blocca)", "RED": "Vendita non autorizzabile: margine diretto ≤ 15% (Margin Floor Gate)", "INCOMPLETE": "PRICING SUSTAINABILITY = INCOMPLETE: dati di piano/costi mancanti"}[status],
            "prices": {"current_customer_price": _r2(net), "direct_minimum_sustainable_price": min_direct, "structural_target_price": structural_target_price,
                       "price_increase_to_target": _r2(structural_target_price - net) if structural_target_price is not None else None},
            "expected_monthly_jobs": plan.get("expected_monthly_jobs"), "expected_monthly_revenue": plan.get("expected_monthly_revenue"), "structure_coverage_percent": plan.get("structure_coverage_percent"),
            "if_accepted": {"monthly_contribution_target": target_m, "already_secured": _r2(secured_m), "this_job_contribution": contrib, "new_total": _r2(secured_m + (contrib or 0)),
                            "remaining": _r2(target_m - secured_m - (contrib or 0)) if target_m is not None else None, "annual_coverage_after_percent": _r2(min(100.0, (float(plan.get("secured_contribution_ytd") or 0) + (contrib or 0)) / float(plan["annual_fixed_cost_target"]) * 100)) if plan.get("annual_fixed_cost_target") else None},
            "data_quality": plan.get("data_quality"), "missing": plan.get("missing")}


def discount_impact(quote: dict, plan: Dict[str, Any], candidate_pct: float) -> Dict[str, Any]:
    """Simula lo sconto globale sul preventivo: Δ contribution verso la copertura struttura (nessun salvataggio)."""
    base = evaluate_quote(quote, plan)
    sim = dict(quote)
    sim_sub = float(quote.get("commercial_subtotal") or quote.get("subtotal") or 0) * (1 - candidate_pct / 100)
    sim.update({"subtotal": sim_sub, "financial_snapshot": None})
    after = evaluate_quote(sim, plan)
    return {"discount_percent": candidate_pct, "before": {k: base[k] for k in ("contribution_margin_amount", "contribution_margin_percent", "sustainability_gap", "status")},
            "after": {k: after[k] for k in ("contribution_margin_amount", "contribution_margin_percent", "sustainability_gap", "status")},
            "contribution_delta": _r2((after["contribution_margin_amount"] or 0) - (base["contribution_margin_amount"] or 0)),
            "message": f"Con questo sconto la commessa contribuisce {abs(_r2((after['contribution_margin_amount'] or 0) - (base['contribution_margin_amount'] or 0))):,.2f} € in meno alla copertura struttura."}


# ---------------- simulatore strategico ----------------
def simulate(*, annual_fixed_costs: float, coverage_months: int, expected_monthly_jobs: Optional[float], expected_monthly_revenue: Optional[float], average_ticket: Optional[float],
             average_contribution_pct: Optional[float], close_rate: Optional[float], target_profit: float = 0.0, secured_ytd: float = 0.0) -> Dict[str, Any]:
    months = max(1, int(coverage_months))
    residual = max(0.0, annual_fixed_costs - secured_ytd)
    req_month = residual / months
    jobs = expected_monthly_jobs
    rev = expected_monthly_revenue or ((jobs or 0) * (average_ticket or 0) or None)
    if jobs is None and rev and average_ticket:
        jobs = rev / average_ticket
    ticket = average_ticket or ((rev / jobs) if (rev and jobs) else None)
    cm = (average_contribution_pct or 0) / 100
    exp_contrib = (rev or 0) * cm
    be_rev = req_month / cm if cm > 0 else None
    be_jobs = (be_rev / ticket) if (be_rev is not None and ticket) else None
    structure_pct = (req_month / rev * 100) if rev else None
    pace = exp_contrib
    cov_months = math.ceil(residual / pace) if pace > 0 and residual > 0 else (0 if residual == 0 else None)
    return {"required_contribution_per_month": _r2(req_month), "required_contribution_per_job": _r2(req_month / jobs) if jobs else None, "required_structure_percent": _r2(structure_pct),
            "break_even_revenue_month": _r2(be_rev), "break_even_jobs_month": _r2(be_jobs), "expected_contribution_month": _r2(exp_contrib), "expected_operating_result_month": _r2(exp_contrib - req_month),
            "required_signed_contracts": _r2(be_jobs), "required_pipeline": _r2(be_jobs / (close_rate / 100)) if (be_jobs is not None and close_rate) else None,
            "expected_structure_coverage_months": cov_months, "expected_profit_after_coverage": _r2(exp_contrib * months - residual - target_profit) if rev else None, "kind": "SIMULATION",
            "note": "Più fatturato non significa più sostenibilità: conta la contribution generata (es. 300k al 10% = 30k < 200k al 30% = 60k)."}


def jobs_scenarios(monthly_target: float, counts=(10, 15, 20, 25, 30, 40)) -> List[Dict[str, Any]]:
    return [{"expected_jobs": n, "required_contribution_per_job": _r2(monthly_target / n)} for n in counts]


def revenue_scenarios(monthly_target: float, revenues=(100000, 150000, 200000, 250000, 300000, 350000, 500000)) -> List[Dict[str, Any]]:
    return [{"expected_revenue": r, "required_structure_percent": _r2(monthly_target / r * 100)} for r in revenues]


async def overview(db, tenant_id: str, le: Optional[str], today: Optional[date] = None) -> Dict[str, Any]:
    today = today or datetime.now(timezone.utc).date()
    le = None if le in (None, "", "all", "GROUP") else le
    settings = await load_settings(db, tenant_id, le, today.year, today.month)
    registry = await fixed_cost_registry(db, tenant_id, le)
    secured = await secured_contribution(db, tenant_id, le, today.year)
    plan = planning_model(settings, registry, secured, today)
    mt = plan.get("monthly_structure_coverage_target") or 0
    return {"settings": settings, "fixed_cost_registry": {k: v for k, v in registry.items() if k != "items"}, "secured": secured, "plan": plan,
            "scenarios": {"by_jobs": jobs_scenarios(mt) if mt else [], "by_revenue": revenue_scenarios(mt) if mt else [],
                          "presets": {k: simulate(annual_fixed_costs=float(plan["annual_fixed_cost_target"] or 0), coverage_months=plan["months_remaining"], expected_monthly_jobs=v["expected_monthly_jobs"],
                                                  expected_monthly_revenue=v["expected_monthly_revenue"], average_ticket=None, average_contribution_pct=settings.get("average_contribution_pct") or 27.0,
                                                  close_rate=settings.get("current_close_rate"), target_profit=float(settings.get("target_profit") or 0), secured_ytd=float(secured["secured_ytd"])) for k, v in SCENARIO_PRESETS.items()} if plan.get("annual_fixed_cost_target") else {}},
            "principles": ["NO_AUTOMATIC_PRICE_CHANGE", "CONTRIBUTION_OVER_REVENUE", "SECURED_NOT_FORECAST", "VAT_EXCLUDED"]}
