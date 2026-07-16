"""M7.TREASURY — Tesoreria intelligente + IVA + Ritenute + F24 + AI CFO enhanced.

Le elaborazioni fiscali sono spiegabili/riconciliabili/approvabili.
NON sostituisce commercialista/revisore. Ogni output cita fonte dato.
"""
from __future__ import annotations
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from app.models import BaseDoc


# ============================================================================
# TAX DEDUCTION CONFIG (bonus ristrutturazione, ecobonus, ...)
# ============================================================================
TaxDeductionType = Literal[
    "restructuring_bonus", "ecobonus", "barriers_removal_bonus",
    "other_incentive", "none",
]


class TaxDeductionRate(BaseDoc):
    """Aliquota fiscale versionata con fonte normativa."""
    deduction_type: TaxDeductionType
    label: str
    deduction_rate: float             # es. 50%, 65%, 75%
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    legal_reference: Optional[str] = None
    source_note: Optional[str] = None
    version: int = 1
    parent_version_id: Optional[str] = None
    active: bool = True
    is_demo: bool = False
    # Ritenuta bancaria applicabile per default (es. 11% cess. crediti)
    default_bank_withholding_rate: float = 0.0
    conventional_vat_rate: float = 22.0
    withholding_calculation_method: Literal["gross_minus_vat", "gross_direct", "custom"] = "gross_minus_vat"


class BuildingTaxData(BaseModel):
    cadastral_id: Optional[str] = None
    address: Optional[str] = None
    zone: Optional[str] = None
    year_built: Optional[int] = None
    energy_class_before: Optional[str] = None
    energy_class_after: Optional[str] = None


# ============================================================================
# BANK ACCOUNTS + VIRTUAL FUNDS
# ============================================================================
BankAccountKind = Literal[
    "operational", "vat", "investments", "contingency", "urgent",
    "taxes", "salaries", "suppliers", "reserve", "card", "cash",
]


class BankAccount(BaseDoc):
    code: str
    label: str
    bank_name: str
    iban_masked: str            # solo ultime 4 cifre
    iban_hash: Optional[str] = None  # sha256 per ricerca sicura
    holder: str
    currency: str = "EUR"
    kind: BankAccountKind = "operational"
    is_virtual: bool = False
    contabile_balance: float = 0.0
    available_balance: float = 0.0
    imported_balance: float = 0.0
    last_sync_at: Optional[datetime] = None
    company_name: Optional[str] = None
    active: bool = True
    is_demo: bool = False
    notes: Optional[str] = None


class BankAccountCreate(BaseModel):
    code: str
    label: str
    bank_name: str
    iban_masked: str
    holder: str
    kind: BankAccountKind = "operational"
    is_virtual: bool = False
    currency: str = "EUR"


class VirtualFund(BaseDoc):
    """Fondo virtuale (IVA, imprevisti, investimenti, urgenze, imposte, ...)."""
    code: str
    label: str
    fund_kind: Literal[
        "vat", "tax_credits_withholding", "contingency", "investments", "urgent",
        "taxes", "salaries", "suppliers", "free_liquidity", "custom",
    ]
    target_pct: float = 0.0          # percentuale target sulla base allocabile
    target_amount: Optional[float] = None
    current_balance: float = 0.0
    linked_bank_account_id: Optional[str] = None
    priority: int = 100              # ordine di allocazione
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    active: bool = True
    is_demo: bool = False
    notes: Optional[str] = None


class VirtualFundCreate(BaseModel):
    code: str
    label: str
    fund_kind: str
    target_pct: float = 0.0
    target_amount: Optional[float] = None
    linked_bank_account_id: Optional[str] = None
    priority: int = 100


class VirtualFundUpdate(BaseModel):
    label: Optional[str] = None
    target_pct: Optional[float] = None
    target_amount: Optional[float] = None
    linked_bank_account_id: Optional[str] = None
    priority: Optional[int] = None
    active: Optional[bool] = None


# ============================================================================
# PAYMENT RECEIVED (incasso da cliente)
# ============================================================================
PaymentReconStatus = Literal[
    "expected", "received_unreconciled", "partially_reconciled",
    "reconciled", "withholding_mismatch", "amount_mismatch",
    "cancelled", "refunded",
]


class PaymentReceived(BaseDoc):
    contract_id: Optional[str] = None
    invoice_id: Optional[str] = None
    installment_ref: Optional[str] = None
    kind: Literal["deposit", "balance", "milestone", "refund"] = "deposit"
    gross_amount: float                              # importo lordo dal cliente
    conventional_vat_rate: float = 22.0              # per calcolo scorporo (ritenuta)
    withholding_enabled: bool = False
    withholding_rate: float = 0.0
    withholding_calc_method: str = "gross_minus_vat"
    # Calcoli derivati
    withholding_base: float = 0.0
    withholding_amount: float = 0.0
    expected_bank_credit: float = 0.0
    actual_bank_credit: Optional[float] = None
    # Meta
    payment_date: datetime
    value_date: Optional[datetime] = None
    method: Literal["bank_transfer", "special_bank_transfer", "card", "cash", "check", "other"] = "bank_transfer"
    bank_account_id: Optional[str] = None
    tx_reference: Optional[str] = None
    document_id: Optional[str] = None
    customer_id: Optional[str] = None
    recon_status: PaymentReconStatus = "expected"
    reconciled_movement_id: Optional[str] = None
    notes: Optional[str] = None


class PaymentReceivedCreate(BaseModel):
    contract_id: Optional[str] = None
    invoice_id: Optional[str] = None
    installment_ref: Optional[str] = None
    kind: str = "deposit"
    gross_amount: float
    conventional_vat_rate: float = 22.0
    withholding_enabled: bool = False
    withholding_rate: float = 0.0
    payment_date: datetime
    value_date: Optional[datetime] = None
    method: str = "bank_transfer"
    bank_account_id: Optional[str] = None
    tx_reference: Optional[str] = None
    customer_id: Optional[str] = None
    notes: Optional[str] = None


# ============================================================================
# BANK STATEMENT IMPORT + MOVEMENTS
# ============================================================================
class BankStatementImport(BaseDoc):
    bank_account_id: str
    filename: str
    format: Literal["csv", "xlsx", "cbi", "cbi2", "camt053", "other"] = "csv"
    imported_by: Optional[str] = None
    rows_total: int = 0
    rows_imported: int = 0
    rows_duplicate: int = 0
    rows_error: int = 0
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    hash_source: Optional[str] = None
    imp_status: Literal["pending", "imported", "approved", "rejected"] = "pending"
    errors: List[Dict[str, Any]] = Field(default_factory=list)


class BankMovement(BaseDoc):
    bank_account_id: str
    import_id: Optional[str] = None
    op_date: date
    value_date: Optional[date] = None
    amount: float                        # segno: positivo=entrata, negativo=uscita
    description: str
    counterpart: Optional[str] = None
    counterpart_iban_masked: Optional[str] = None
    reference: Optional[str] = None       # CRO/TRN
    balance_after: Optional[float] = None
    bank_name: Optional[str] = None
    dedup_hash: str
    category: Optional[str] = None
    linked_document_kind: Optional[str] = None
    linked_document_id: Optional[str] = None
    linked_payment_id: Optional[str] = None
    recon_status: Literal[
        "unreconciled", "auto_match", "manual_match", "partial", "excluded"
    ] = "unreconciled"
    match_score: Optional[float] = None


# ============================================================================
# VAT LEDGER + CLOSINGS
# ============================================================================
VATEntryKind = Literal[
    "sales", "purchases", "sales_credit_note", "purchases_credit_note",
    "adjustment", "carry_forward", "advance_payment", "payment",
]


class VATEntry(BaseDoc):
    period: str                  # es. "2026-06" o "2026-Q2"
    kind: VATEntryKind
    document_ref: Optional[str] = None
    document_kind: Optional[str] = None   # invoice | credit_note | manual
    taxable_amount: float = 0.0
    vat_amount: float = 0.0
    vat_rate: float = 22.0
    detrattable: bool = True
    detrattability_pct: float = 100.0
    is_deferred: bool = False       # IVA sospesa
    is_exigible: bool = True
    reason: Optional[str] = None
    entered_by: Optional[str] = None


class VATClosing(BaseDoc):
    period: str
    prior_credit: float = 0.0
    sales_vat_exigible: float = 0.0
    purchases_vat_detrattable: float = 0.0
    net_vat: float = 0.0             # exigible - detrattable
    payments: float = 0.0
    advance_payment: float = 0.0
    adjustments: float = 0.0
    balance: float = 0.0             # netto da versare / credito riportato
    is_credit: bool = False
    closing_status: Literal["draft", "in_review", "closed", "reopened"] = "draft"
    closed_at: Optional[datetime] = None
    closed_by: Optional[str] = None
    approver_id: Optional[str] = None
    notes: Optional[str] = None
    formula_used: Optional[str] = None
    source_entry_ids: List[str] = Field(default_factory=list)


# ============================================================================
# F24 / TAX PAYMENT
# ============================================================================
class F24Payment(BaseDoc):
    period: str
    tribute_code: str
    tribute_label: Optional[str] = None
    amount_debit: float = 0.0
    amount_credit_used: float = 0.0
    net_amount: float = 0.0
    due_date: date
    paid_date: Optional[date] = None
    receipt_id: Optional[str] = None    # attachment id ricevuta
    consultant_ref: Optional[str] = None
    f24_status: Literal[
        "planned", "generated", "sent", "paid", "receipt_missing",
        "inconsistent", "cancelled"
    ] = "planned"
    consistency_flags: List[str] = Field(default_factory=list)
    professional_verification_required: bool = True
    notes: Optional[str] = None


# ============================================================================
# SUGGESTED FUND TRANSFER (proposte, no esecuzione automatica)
# ============================================================================
class SuggestedTransfer(BaseDoc):
    from_account_id: str
    to_account_id: str
    amount: float
    rule_code: Optional[str] = None
    rule_label: Optional[str] = None
    priority: int = 100
    due_at: Optional[datetime] = None
    reason: str
    data_sources: List[Dict[str, Any]] = Field(default_factory=list)
    balance_before: Optional[float] = None
    balance_after_expected: Optional[float] = None
    risk_if_skipped: Optional[str] = None
    st_status: Literal[
        "suggested", "approved", "rejected", "scheduled",
        "executed", "reconciled", "cancelled",
    ] = "suggested"
    approver_id: Optional[str] = None
    approved_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    executed_by: Optional[str] = None
    execution_ref: Optional[str] = None    # nessuna esecuzione automatica


# ============================================================================
# ALLOCATION POLICY (fondi %)
# ============================================================================
class AllocationPolicy(BaseDoc):
    version: int = 1
    parent_version_id: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    active: bool = True
    # Fondi in ordine di priorità
    lines: List[Dict[str, Any]] = Field(default_factory=list)
    # Ogni riga: {fund_code, pct, min_amount, max_amount, priority}
    formula: str = (
        "base_allocabile = accredito_bancario_effettivo - iva_da_accantonare "
        "- imposte_o_ritenute_non_disponibili - pagamenti_diretti_imminenti - fondi_gia_vincolati"
    )
    notes: Optional[str] = None
    is_demo: bool = False


class AllocationRun(BaseDoc):
    policy_id: str
    policy_version: int = 1
    triggered_by: Literal["payment", "manual", "schedule"] = "payment"
    payment_id: Optional[str] = None
    inputs: Dict[str, Any] = Field(default_factory=dict)
    base_allocabile: float = 0.0
    allocations: List[Dict[str, Any]] = Field(default_factory=list)
    # Ogni allocazione: {fund_code, amount, pct, cumulative}
    residual_free_liquidity: float = 0.0
    computed_at: datetime = Field(default_factory=lambda: datetime.now())


# ============================================================================
# AI CFO ENHANCED
# ============================================================================
class AICFOInsight(BaseDoc):
    """Suggerimento AI con fonti + confidenza + missing_data."""
    kind: Literal[
        "transfer_suggestion", "vat_reserve_increase", "investment_reduction",
        "supplier_renegotiation", "customer_dunning", "cost_variance_alert",
        "cash_runway_alert", "f24_upcoming", "withholding_pending",
        "credit_utilization", "duplicate_payment_check", "anomaly",
    ]
    title: str
    body: str
    period_analyzed: Optional[str] = None
    company_name: Optional[str] = None
    data_sources: List[Dict[str, Any]] = Field(default_factory=list)
    missing_data: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    formula: Optional[str] = None
    confidence: float = 0.5                     # 0..1
    risk_level: Literal["info", "low", "medium", "high", "critical"] = "info"
    impact_estimate: Optional[float] = None
    requires_approval: bool = False
    is_dismissed: bool = False
    dismissed_at: Optional[datetime] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now())
    linked_entity_kind: Optional[str] = None
    linked_entity_id: Optional[str] = None
    suggested_actions: List[Dict[str, Any]] = Field(default_factory=list)


# ============================================================================
# ALERTS
# ============================================================================
class TreasuryAlert(BaseDoc):
    code: str                            # es. VAT_UNCOVERED, LOW_OPERATIONAL
    title: str
    body: str
    severity: Literal["info", "low", "medium", "high", "critical"] = "medium"
    ref_kind: Optional[str] = None
    ref_id: Optional[str] = None
    is_resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    data_sources: List[Dict[str, Any]] = Field(default_factory=list)


# ============================================================================
# SIMULATION / SCENARIO
# ============================================================================
class TreasuryScenario(BaseDoc):
    label: str
    scenario_kind: Literal["base", "prudent", "stress", "growth", "investment", "cost_reduction"] = "base"
    horizon_months: int = 12
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    formula_used: Optional[str] = None
    computed_at: datetime = Field(default_factory=lambda: datetime.now())


# ============================================================================
# WITHHOLDING CALCULATOR REQUEST
# ============================================================================
class WithholdingCalcRequest(BaseModel):
    gross_amount: float
    conventional_vat_rate: float = 22.0
    withholding_rate: float = 11.0
    method: Literal["gross_minus_vat", "gross_direct", "custom"] = "gross_minus_vat"


class WithholdingCalcResponse(BaseModel):
    gross_amount: float
    withholding_base: float
    conventional_vat_amount: float
    withholding_rate: float
    withholding_amount: float
    expected_bank_credit: float
    method: str
    formula: str
    notes: str


class TreasuryCloseMonthRequest(BaseModel):
    period: str
    notes: Optional[str] = None


class AICFORunRequest(BaseModel):
    period: Optional[str] = None
    scope: Literal["all", "vat", "cash", "costs", "customers", "suppliers"] = "all"
    kinds: Optional[List[str]] = None
