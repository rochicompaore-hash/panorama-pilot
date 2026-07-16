"""Break-even + budget/what-if simulator engine.

Formule gestionali documentate. NO eval().
"""
from __future__ import annotations
from typing import List, Dict, Any
from app.models_control import BudgetInputs, BudgetOutputs


def compute_budget_outputs(inputs: BudgetInputs, *, monthly_capacity_windows: int = 40) -> BudgetOutputs:
    """Calcolo canonico degli output di un budget/scenario.

    Formule:
    - forecast_revenue = yearly_revenue * (1 + price_pct_change/100)
    - variable_costs = revenue * (material_cost_pct + installation_cost_pct)/100
    - contribution_margin = revenue - variable_costs
    - total_fixed_costs = personnel + fixed + energy + marketing + new_hires + leasing
    - ebitda = contribution_margin - total_fixed_costs
    - break_even_revenue = total_fixed_costs / (contribution_margin_pct)
    - stability_revenue = (fixed_costs + target_profit + fondi) / margin_pct
    - growth_revenue = stability + investments
    - cash_flow = ebitda - taxes - investments  (semplificato)
    - contracts_needed = revenue / average_ticket
    - leads_needed = contracts / close_rate
    """
    revenue = float(inputs.yearly_revenue) * (1 + float(inputs.price_pct_change) / 100.0)
    var_pct = (float(inputs.material_cost_pct) + float(inputs.installation_cost_pct)) / 100.0
    var_costs = revenue * var_pct
    contribution = revenue - var_costs
    contribution_pct = (contribution / revenue * 100.0) if revenue > 0 else 0.0

    fixed_yearly = (
        float(inputs.personnel_cost_yearly)
        + float(inputs.fixed_costs_yearly)
        + float(inputs.energy_yearly)
        + float(inputs.marketing_yearly)
        + float(inputs.new_hires_cost_yearly)
        + float(inputs.leasing_yearly)
    )
    ebitda = contribution - fixed_yearly

    # Fondi accantonati (sul ricavo)
    fund_total_pct = (
        float(inputs.fund_pct_vat) + float(inputs.fund_pct_contingency)
        + float(inputs.fund_pct_investments) + float(inputs.fund_pct_urgent)
    ) / 100.0
    fund_amount = revenue * fund_total_pct

    # Break-even
    if contribution_pct > 0:
        break_even = fixed_yearly / (contribution_pct / 100.0)
        stability = (fixed_yearly + float(inputs.target_profit) + fund_amount) / (contribution_pct / 100.0)
        growth = stability + float(inputs.investments_yearly)
    else:
        break_even = 0.0
        stability = 0.0
        growth = 0.0

    # Contratti / lead
    avg_ticket = max(1.0, float(inputs.average_ticket))
    contracts_needed = int(round(revenue / avg_ticket)) if avg_ticket > 0 else 0
    close_rate = max(0.01, float(inputs.close_rate_pct) / 100.0)
    appointments_needed = int(round(contracts_needed / close_rate)) if close_rate > 0 else 0
    leads_needed = int(round(appointments_needed / max(0.05, close_rate)))
    windows_needed = int(round(revenue / max(1.0, avg_ticket / 4)))  # euristico

    # Capacità produttiva
    yearly_capacity = monthly_capacity_windows * 12
    capacity_used_pct = (windows_needed / yearly_capacity * 100.0) if yearly_capacity > 0 else 0.0

    # Cash flow (semplificato)
    tax = max(0.0, ebitda) * float(inputs.tax_rate) / 100.0
    cash_flow = ebitda - tax - float(inputs.investments_yearly)

    # Liquidità minima consigliata = 2 mesi di costi fissi
    liquidity_min = fixed_yearly / 12.0 * 2.0
    monthly_burn = fixed_yearly / 12.0
    runway = (liquidity_min / monthly_burn) if monthly_burn > 0 else 0.0
    financial_need = max(0.0, -cash_flow)

    # Break-even month
    if contribution_pct > 0 and revenue > 0:
        monthly_be_rev = break_even / 12.0
        monthly_rev = revenue / 12.0
        month_index = int(round(monthly_be_rev / max(1.0, monthly_rev)))
        month_index = min(12, max(1, month_index))
        break_even_date = f"M{month_index:02d}"
    else:
        break_even_date = None

    # ROI / Payback su investimenti
    if float(inputs.investments_yearly) > 0 and ebitda > 0:
        roi = ebitda / float(inputs.investments_yearly) * 100.0
        payback = float(inputs.investments_yearly) / (ebitda / 12.0) if ebitda > 0 else 0.0
    else:
        roi = 0.0
        payback = 0.0

    # Waterfall break-even
    waterfall = [
        {"label": "Fatturato", "value": round(revenue, 2), "kind": "start"},
        {"label": "Costi variabili", "value": round(-var_costs, 2), "kind": "negative"},
        {"label": "Margine di contribuzione", "value": round(contribution, 2), "kind": "subtotal"},
        {"label": "Costi fissi", "value": round(-fixed_yearly, 2), "kind": "negative"},
        {"label": "EBITDA gestionale", "value": round(ebitda, 2), "kind": "subtotal"},
        {"label": "Fondi accantonati", "value": round(-fund_amount, 2), "kind": "negative"},
        {"label": "Investimenti", "value": round(-float(inputs.investments_yearly), 2), "kind": "negative"},
        {"label": "Utile obiettivo", "value": round(float(inputs.target_profit), 2), "kind": "target"},
    ]

    return BudgetOutputs(
        forecast_revenue=round(revenue, 2),
        variable_costs=round(var_costs, 2),
        contribution_margin=round(contribution, 2),
        contribution_margin_pct=round(contribution_pct, 2),
        total_fixed_costs=round(fixed_yearly, 2),
        ebitda=round(ebitda, 2),
        break_even_revenue=round(break_even, 2),
        stability_revenue=round(stability, 2),
        growth_revenue=round(growth, 2),
        cash_flow_yearly=round(cash_flow, 2),
        liquidity_min=round(liquidity_min, 2),
        cash_runway_months=round(runway, 2),
        financial_need=round(financial_need, 2),
        contracts_needed=contracts_needed,
        appointments_needed=appointments_needed,
        leads_needed=leads_needed,
        windows_needed=windows_needed,
        capacity_used_pct=round(capacity_used_pct, 2),
        break_even_date=break_even_date,
        roi_pct=round(roi, 2),
        payback_months=round(payback, 2),
        waterfall=waterfall,
    )


PRESET_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "base": {
        "yearly_revenue": 800000, "average_ticket": 6500, "close_rate_pct": 25,
        "material_cost_pct": 42, "installation_cost_pct": 8,
        "personnel_cost_yearly": 180000, "fixed_costs_yearly": 90000,
        "energy_yearly": 12000, "marketing_yearly": 20000,
        "investments_yearly": 15000, "target_profit": 60000,
    },
    "prudent": {
        "yearly_revenue": 650000, "average_ticket": 6500, "close_rate_pct": 20,
        "material_cost_pct": 45, "installation_cost_pct": 9,
        "personnel_cost_yearly": 180000, "fixed_costs_yearly": 95000,
        "energy_yearly": 14000, "marketing_yearly": 15000,
        "investments_yearly": 5000, "target_profit": 30000,
    },
    "growth": {
        "yearly_revenue": 1100000, "average_ticket": 7200, "close_rate_pct": 28,
        "material_cost_pct": 40, "installation_cost_pct": 8,
        "personnel_cost_yearly": 230000, "fixed_costs_yearly": 100000,
        "energy_yearly": 14000, "marketing_yearly": 40000,
        "investments_yearly": 60000, "new_hires_cost_yearly": 40000,
        "target_profit": 120000,
    },
}
