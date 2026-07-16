"""M6.COMM — Commission plans, rules, entries, adjustments, invoices, profitability."""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from app.models import BaseDoc, new_id


CommissionBase = Literal[
    "contract_taxable", "contract_collected", "margin_contribution",
    "net_after_discount", "product_value", "excluding_installation", "custom",
]


class ProfitabilityTier(BaseModel):
    """Fascia di redditività per determinare la commissione."""
    label: str = ""                    # es. "Fascia 1"
    min_pct: Optional[float] = None    # inclusive
    max_pct: Optional[float] = None    # inclusive; None = infinito
    min_exclusive: bool = False        # se true, "> min_pct"
    max_exclusive: bool = False
    commission_pct: Optional[float] = None   # % commissione
    flat_fee: Optional[float] = None         # gettone fisso
    max_pct_with_major_discount: Optional[float] = None  # override se maggior sconto
    requires_approval: bool = False
    pending_configuration: bool = False


class CommissionPlan(BaseDoc):
    code: str
    name: str
    role: Optional[str] = None         # es. "sales_rep"
    version: int = 1
    parent_version_id: Optional[str] = None
    active: bool = True
    is_demo: bool = False
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    base: CommissionBase = "contract_taxable"
    accrual_after_collected_pct: float = 50.0   # matura solo dopo x% incassato
    reverse_on_cancellation: bool = True
    reverse_on_credit_note: bool = True
    tiers: List[ProfitabilityTier] = Field(default_factory=list)
    major_discount_max_pct: Optional[float] = 5.0
    approve_threshold_min_profitability: float = -100.0  # se sotto → doppia approvazione
    exclude_lines_matching: List[str] = Field(default_factory=list)


class CommissionPlanCreate(BaseModel):
    code: str
    name: str
    role: Optional[str] = None
    base: CommissionBase = "contract_taxable"
    accrual_after_collected_pct: float = 50.0
    tiers: List[ProfitabilityTier] = Field(default_factory=list)
    major_discount_max_pct: Optional[float] = 5.0


class CommissionPlanUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    base: Optional[CommissionBase] = None
    accrual_after_collected_pct: Optional[float] = None
    tiers: Optional[List[ProfitabilityTier]] = None
    major_discount_max_pct: Optional[float] = None
    approve_threshold_min_profitability: Optional[float] = None


# ============================================================================
# COMMISSION ENTRY
# ============================================================================
CommissionEntryStatus = Literal[
    "estimated", "approved", "accrued", "invoiceable",
    "invoiced", "partially_paid", "paid",
    "suspended", "reversed", "cancelled", "pending_configuration",
]


class CommissionEntry(BaseDoc):
    plan_id: Optional[str] = None
    plan_version: int = 1
    contract_id: str
    quote_id: Optional[str] = None
    customer_id: Optional[str] = None
    sales_rep_id: str
    role: Optional[str] = None
    base_amount: float = 0.0
    base_kind: CommissionBase = "contract_taxable"
    profitability_pct: Optional[float] = None
    tier_label: Optional[str] = None
    commission_pct: Optional[float] = None
    flat_fee: Optional[float] = None
    computed_amount: float = 0.0
    major_discount_applied: bool = False
    entry_status: CommissionEntryStatus = "estimated"
    accrual_pct: float = 0.0            # % maturato (proporzionale all'incasso)
    accrued_amount: float = 0.0
    invoiced_amount: float = 0.0
    paid_amount: float = 0.0
    invoice_id: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    reason: Optional[str] = None
    approval_required: bool = False
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    parent_entry_id: Optional[str] = None   # per storni append-only


class CommissionAdjustment(BaseDoc):
    entry_id: str
    kind: Literal["credit", "debit", "reversal", "correction"]
    amount: float
    reason: str
    document_id: Optional[str] = None
    approver_id: Optional[str] = None
    approved_at: Optional[datetime] = None


# ============================================================================
# COMMISSION INVOICE
# ============================================================================
CommissionInvoiceStatus = Literal[
    "draft", "submitted", "under_review", "approved",
    "rejected", "scheduled_for_payment", "paid",
]


class CommissionInvoice(BaseDoc):
    number: Optional[str] = None
    sales_rep_id: str
    invoice_number: str
    invoice_date: datetime
    taxable_amount: float = 0.0
    vat_amount: float = 0.0
    total_amount: float = 0.0
    attachment_id: Optional[str] = None
    notes: Optional[str] = None
    entry_ids: List[str] = Field(default_factory=list)
    inv_status: CommissionInvoiceStatus = "draft"
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    rejection_reason: Optional[str] = None
    paid_at: Optional[datetime] = None
    payment_ref: Optional[str] = None


class CommissionInvoiceCreate(BaseModel):
    sales_rep_id: Optional[str] = None
    invoice_number: str
    invoice_date: datetime
    taxable_amount: float
    vat_amount: float
    total_amount: float
    attachment_id: Optional[str] = None
    notes: Optional[str] = None
    entry_ids: List[str] = Field(default_factory=list)


class CommissionInvoiceUpdate(BaseModel):
    invoice_number: Optional[str] = None
    invoice_date: Optional[datetime] = None
    taxable_amount: Optional[float] = None
    vat_amount: Optional[float] = None
    total_amount: Optional[float] = None
    attachment_id: Optional[str] = None
    notes: Optional[str] = None


# ============================================================================
# DISCOUNT CLASSIFICATION
# ============================================================================
DiscountKind = Literal["standard", "authorized", "major", "exceptional"]


class DiscountClassification(BaseModel):
    """Classificazione strutturata di uno sconto. Non testo libero."""
    kind: DiscountKind = "standard"
    percent: float = 0.0
    amount: float = 0.0
    threshold_exceeded_by_pct: float = 0.0
    reason: Optional[str] = None
    requested_by: Optional[str] = None
    approver_id: Optional[str] = None
    approved_at: Optional[datetime] = None
    affects_commission: bool = False           # se true → maggior sconto o oltre


# ============================================================================
# PROFITABILITY
# ============================================================================
class ProfitabilityBreakdown(BaseModel):
    """Dettaglio redditività per commessa."""
    contract_id: str
    revenue_gross: float = 0.0
    revenue_net: float = 0.0                # netto post sconti
    variable_costs_total: float = 0.0
    materials_cost: float = 0.0
    glass_cost: float = 0.0
    hardware_cost: float = 0.0
    accessories_cost: float = 0.0
    external_processing_cost: float = 0.0
    production_labor_cost: float = 0.0
    installation_cost: float = 0.0
    transport_cost: float = 0.0
    platform_cost: float = 0.0
    disposal_cost: float = 0.0
    commissions_cost: float = 0.0
    financial_cost: float = 0.0
    scrap_cost: float = 0.0
    rework_reserve: float = 0.0
    residual_economic: float = 0.0
    profitability_pct: Optional[float] = None
    profitability_after_commission_pct: Optional[float] = None
    costs_completeness: Literal["complete", "partial", "missing"] = "partial"
    missing_cost_categories: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)
    computed_at: datetime = Field(default_factory=lambda: datetime.now())
