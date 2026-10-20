"""Management Control models — costi fissi, personale, scadenziario, budget, forecast."""
from __future__ import annotations
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from app.models import BaseDoc


# =============================================================
# FIXED COSTS
# =============================================================
FixedCostCategory = Literal[
    "rent", "utilities", "insurance", "software", "licenses",
    "vehicles", "leasing", "consulting", "marketing", "training",
    "banking", "office_supplies", "cleaning", "security", "other",
]

FixedCostRecurrence = Literal["monthly", "quarterly", "yearly", "one_off"]


class FixedCost(BaseDoc):
    label: str
    category: FixedCostCategory = "other"
    supplier: Optional[str] = None
    amount_monthly: float = 0.0        # amount normalizzato mensilmente
    amount_raw: float = 0.0
    recurrence: FixedCostRecurrence = "monthly"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    vat_rate: float = 22.0
    cost_center: Optional[str] = None
    legal_entity_id: Optional[str] = None
    business_unit: Optional[str] = None
    active: bool = True
    is_demo: bool = False
    notes: Optional[str] = None
    cost_class: Optional[str] = None  # FIXED_STRUCTURE_COST | DIRECT_JOB_COST | SEMI_VARIABLE_COST | CASH_ONLY_FINANCIAL_COST
    fixed_component: Optional[float] = None
    fixed_component_pct: Optional[float] = None


class FixedCostCreate(BaseModel):
    label: str
    category: str = "other"
    supplier: Optional[str] = None
    amount_raw: float
    recurrence: str = "monthly"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    vat_rate: float = 22.0
    legal_entity_id: Optional[str] = None
    cost_center: Optional[str] = None
    cost_class: Optional[str] = None  # FIXED_STRUCTURE_COST | DIRECT_JOB_COST | SEMI_VARIABLE_COST | CASH_ONLY_FINANCIAL_COST
    fixed_component: Optional[float] = None
    fixed_component_pct: Optional[float] = None


class FixedCostUpdate(BaseModel):
    label: Optional[str] = None
    category: Optional[str] = None
    supplier: Optional[str] = None
    amount_raw: Optional[float] = None
    recurrence: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    vat_rate: Optional[float] = None
    cost_center: Optional[str] = None
    active: Optional[bool] = None
    cost_class: Optional[str] = None  # FIXED_STRUCTURE_COST | DIRECT_JOB_COST | SEMI_VARIABLE_COST | CASH_ONLY_FINANCIAL_COST
    fixed_component: Optional[float] = None
    fixed_component_pct: Optional[float] = None


# =============================================================
# PERSONNEL COSTS
# =============================================================
PersonnelContract = Literal[
    "employee_indeterminate", "employee_determinate", "apprentice",
    "internship", "collaborator", "consultant", "external",
]


class PersonnelCost(BaseDoc):
    employee_ref: Optional[str] = None  # id user o esterno
    full_name: str
    role: Optional[str] = None
    department: Optional[str] = None
    contract_kind: PersonnelContract = "employee_indeterminate"
    ral_yearly: float = 0.0                # RAL (retribuzione lorda annua)
    monthly_gross: float = 0.0
    social_charges_pct: float = 30.0        # contributi ~30% media
    monthly_indirect: float = 0.0           # TFR/tredicesima ecc mensilizzati
    monthly_total_cost: float = 0.0         # calcolato
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    cost_center: Optional[str] = None
    legal_entity_id: Optional[str] = None
    active: bool = True
    is_demo: bool = False
    notes: Optional[str] = None
    employee_cost_mode: Optional[str] = "ALL_IN_COMPANY_COST"  # ALL_IN_COMPANY_COST | PAYROLL_ONLY | MANUAL_BREAKDOWN
    employer_charges_monthly: Optional[float] = None


class PersonnelCostCreate(BaseModel):
    full_name: str
    role: Optional[str] = None
    department: Optional[str] = None
    contract_kind: str = "employee_indeterminate"
    ral_yearly: float = 0.0
    social_charges_pct: float = 30.0
    monthly_indirect: float = 0.0
    start_date: Optional[date] = None
    legal_entity_id: Optional[str] = None
    cost_center: Optional[str] = None
    employee_cost_mode: Optional[str] = "ALL_IN_COMPANY_COST"  # ALL_IN_COMPANY_COST | PAYROLL_ONLY | MANUAL_BREAKDOWN
    employer_charges_monthly: Optional[float] = None


class PersonnelCostUpdate(BaseModel):
    role: Optional[str] = None
    department: Optional[str] = None
    ral_yearly: Optional[float] = None
    social_charges_pct: Optional[float] = None
    monthly_indirect: Optional[float] = None
    end_date: Optional[date] = None
    active: Optional[bool] = None
    employee_cost_mode: Optional[str] = "ALL_IN_COMPANY_COST"  # ALL_IN_COMPANY_COST | PAYROLL_ONLY | MANUAL_BREAKDOWN
    employer_charges_monthly: Optional[float] = None


# =============================================================
# MANAGEMENT CHART OF ACCOUNTS
# =============================================================
AccountKind = Literal[
    "revenue", "variable_cost", "personnel_cost", "fixed_cost",
    "financial_income", "financial_cost", "tax",
    "investment", "extraordinary",
]


class ManagementAccount(BaseDoc):
    code: str
    label: str
    kind: AccountKind
    parent_code: Optional[str] = None
    is_leaf: bool = True
    sort_order: int = 100
    active: bool = True
    is_demo: bool = False


# =============================================================
# PAYABLES / RECEIVABLES (Scadenziario)
# =============================================================
PayableStatus = Literal[
    "planned", "issued", "due", "overdue",
    "partially_paid", "paid", "disputed", "cancelled",
]


class Payable(BaseDoc):
    """Scadenziario debiti (fornitori, personale, F24, ...)."""
    label: str
    creditor: str
    doc_kind: Literal["invoice", "salary", "tax_f24", "loan", "leasing", "other"] = "invoice"
    doc_ref: Optional[str] = None
    doc_date: Optional[date] = None
    due_date: date
    amount_gross: float
    amount_paid: float = 0.0
    residual: float = 0.0
    currency: str = "EUR"
    vat_rate: float = 22.0
    legal_entity_id: Optional[str] = None
    cost_center: Optional[str] = None
    payable_status: PayableStatus = "planned"
    linked_intercompany_pair_id: Optional[str] = None
    notes: Optional[str] = None


class PayableCreate(BaseModel):
    label: str
    creditor: str
    doc_kind: str = "invoice"
    doc_ref: Optional[str] = None
    doc_date: Optional[date] = None
    due_date: date
    amount_gross: float
    currency: str = "EUR"
    vat_rate: float = 22.0
    legal_entity_id: Optional[str] = None
    cost_center: Optional[str] = None
    notes: Optional[str] = None


class Receivable(BaseDoc):
    """Scadenziario crediti (clienti, intercompany, ...)."""
    label: str
    debtor: str
    doc_ref: Optional[str] = None
    doc_date: Optional[date] = None
    due_date: date
    amount_gross: float
    amount_collected: float = 0.0
    residual: float = 0.0
    currency: str = "EUR"
    legal_entity_id: Optional[str] = None
    r_status: Literal["planned", "issued", "due", "overdue",
                       "partially_collected", "collected", "disputed"] = "planned"
    linked_intercompany_pair_id: Optional[str] = None
    notes: Optional[str] = None


# =============================================================
# BUDGET & FORECAST
# =============================================================
BudgetScenarioKind = Literal["base", "prudent", "growth", "custom"]


class BudgetInputs(BaseModel):
    """Variabili modificabili del simulatore."""
    yearly_revenue: float = 0.0
    average_ticket: float = 0.0
    close_rate_pct: float = 25.0
    n_leads: int = 0
    n_appointments: int = 0
    price_pct_change: float = 0.0        # aumento prezzi
    material_cost_pct: float = 40.0
    installation_cost_pct: float = 8.0
    personnel_cost_yearly: float = 0.0
    fixed_costs_yearly: float = 0.0
    energy_yearly: float = 0.0
    marketing_yearly: float = 0.0
    investments_yearly: float = 0.0
    new_hires_cost_yearly: float = 0.0
    leasing_yearly: float = 0.0
    collection_days: int = 60
    payment_days: int = 60
    vat_rate: float = 22.0
    tax_rate: float = 27.0
    fund_pct_vat: float = 20.0
    fund_pct_contingency: float = 10.0
    fund_pct_investments: float = 10.0
    fund_pct_urgent: float = 5.0
    production_capacity_pct: float = 100.0
    target_profit: float = 0.0


class BudgetOutputs(BaseModel):
    forecast_revenue: float = 0.0
    variable_costs: float = 0.0
    contribution_margin: float = 0.0
    contribution_margin_pct: float = 0.0
    total_fixed_costs: float = 0.0
    ebitda: float = 0.0
    break_even_revenue: float = 0.0
    stability_revenue: float = 0.0        # per coprire target minimo
    growth_revenue: float = 0.0           # per finanziare investimenti
    cash_flow_yearly: float = 0.0
    liquidity_min: float = 0.0
    cash_runway_months: float = 0.0
    financial_need: float = 0.0
    contracts_needed: int = 0
    appointments_needed: int = 0
    leads_needed: int = 0
    windows_needed: int = 0
    capacity_used_pct: float = 0.0
    break_even_date: Optional[str] = None   # "YYYY-MM"
    roi_pct: float = 0.0
    payback_months: float = 0.0
    waterfall: List[Dict[str, Any]] = Field(default_factory=list)


class BudgetScenario(BaseDoc):
    """Scenario di budget/simulazione."""
    label: str
    year: int
    scenario_kind: BudgetScenarioKind = "base"
    legal_entity_id: Optional[str] = None
    is_consolidated: bool = False
    inputs: BudgetInputs = Field(default_factory=BudgetInputs)
    outputs: BudgetOutputs = Field(default_factory=BudgetOutputs)
    approved: bool = False
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    promoted_to_forecast: bool = False
    parent_scenario_id: Optional[str] = None
    notes: Optional[str] = None
    is_demo: bool = False


class BudgetScenarioCreate(BaseModel):
    label: str
    year: int
    scenario_kind: str = "base"
    legal_entity_id: Optional[str] = None
    inputs: BudgetInputs = Field(default_factory=BudgetInputs)
    notes: Optional[str] = None


class BudgetSimulationRequest(BaseModel):
    label: Optional[str] = "Simulazione"
    year: int
    legal_entity_id: Optional[str] = None
    inputs: BudgetInputs
    save_as_scenario: bool = False
    scenario_kind: str = "custom"


# =============================================================
# INVESTMENT
# =============================================================
class Investment(BaseDoc):
    label: str
    category: Literal["machinery", "vehicle", "software", "building", "office",
                       "training", "marketing_asset", "other"] = "machinery"
    amount: float
    start_date: date
    depreciation_years: int = 5
    monthly_depreciation: float = 0.0     # calcolato
    legal_entity_id: Optional[str] = None
    expected_return: Optional[float] = None
    payback_months: Optional[float] = None
    notes: Optional[str] = None
    active: bool = True
