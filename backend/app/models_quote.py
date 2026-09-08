"""Quote/Preventivo domain models (M3)."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field
from app.models import BaseDoc, new_id, utcnow
from app.models_crm import LeadAddress


class QuoteLine(BaseModel):
    id: str = Field(default_factory=new_id)
    opening_id: Optional[str] = None
    order_index: int = 0
    category: str  # window|shutter|roller|persian|screen|box|sill|trim|accessory|installation|disposal|extra
    product_key: Optional[str] = None
    product_config: Dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    image_url: Optional[str] = None
    width_mm: Optional[int] = None
    height_mm: Optional[int] = None
    quantity: float = 1.0
    base_price: float = 0.0
    surcharges: List[Dict[str, Any]] = Field(default_factory=list)
    discount_pct: float = 0.0
    discount_amount: float = 0.0
    unit_price_final: float = 0.0
    subtotal_line: float = 0.0
    internal_cost: float = 0.0
    margin: float = 0.0
    vat_rate: float = 0.22
    # --- Multi-Category V1 additive fields (default None per righe legacy) ---
    source: Optional[str] = None  # es. "MULTI_CATEGORY_V1" per nuove righe
    category_id: Optional[str] = None
    category_code: Optional[str] = None
    product_id: Optional[str] = None
    product_code: Optional[str] = None
    pricing_model: Optional[str] = None
    configuration_snapshot: Optional[Dict[str, Any]] = None
    pricing_snapshot: Optional[Dict[str, Any]] = None
    technical_snapshot: Optional[Dict[str, Any]] = None
    commercial_snapshot: Optional[Dict[str, Any]] = None
    simple_snapshot: Optional[Dict[str, Any]] = None
    financial_snapshot: Optional[Dict[str, Any]] = None
    previous_snapshots: List[Dict[str, Any]] = Field(default_factory=list)
    # --- Installation Mode V1 (msg 393) ---
    automatic_services: List[Dict[str, Any]] = Field(default_factory=list)
    manual_extra_services: List[Dict[str, Any]] = Field(default_factory=list)
    standard_services_sale_total: float = 0.0
    standard_services_internal_cost_total: float = 0.0
    position_sale_total: float = 0.0
    position_internal_cost_total: float = 0.0
    service_policy_version: Optional[str] = None
    # ENEA hidden line marker (msg 395 §4)
    enea_practice: bool = False


class QuoteOpening(BaseModel):
    id: str = Field(default_factory=new_id)
    code: str = ""
    floor: Optional[str] = None
    room: Optional[str] = None
    description: Optional[str] = None
    width_mm: Optional[int] = None
    height_mm: Optional[int] = None
    quantity: int = 1
    photos: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    accessibility: Optional[str] = None
    wall_type: Optional[str] = None
    installation_type: Optional[str] = None
    opening_status: str = "draft"
    order_index: int = 0


class Approval(BaseModel):
    required: bool = False
    status: str = "none"  # none | pending | approved | rejected
    requested_by: Optional[str] = None
    requested_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    decided_at: Optional[datetime] = None
    reason: Optional[str] = None
    reason_response: Optional[str] = None


class Quote(BaseDoc):
    number: Optional[str] = None  # formatted (e.g. PREV-2026-01350)
    number_int: Optional[int] = None  # integer part for sorting
    revision: int = 0  # R00
    revision_label: str = "R00"
    parent_quote_id: Optional[str] = None
    is_current: bool = True

    # linking
    lead_id: Optional[str] = None
    customer_id: Optional[str] = None
    site_id: Optional[str] = None
    contact_id: Optional[str] = None
    assigned_to: Optional[str] = None
    site_address: LeadAddress = Field(default_factory=LeadAddress)

    # info
    title: Optional[str] = None
    intervention_type: str = "new"  # new | renovation | replacement
    tax_practice: Optional[str] = None  # es. bonus 50%, ecobonus, etc.
    payment_terms: Optional[str] = None
    # msg 402 Lotto 5 — payment terms snapshot
    payment_terms_code: Optional[str] = None
    payment_terms_label: Optional[str] = None
    payment_schedule: List[Dict[str, Any]] = Field(default_factory=list)
    automatic_discount_percent: float = 0.0
    financing_mode: Optional[str] = None
    payment_policy_version: Optional[str] = None
    payment_discount_amount: float = 0.0
    subtotal_before_payment_discount: float = 0.0
    # msg 402 Lotto 9 — delivery policy snapshot
    delivery_mode: str = "STANDARD"
    delivery_label: Optional[str] = None
    estimated_delivery_min_days: Optional[int] = None
    estimated_delivery_max_days: Optional[int] = None
    delivery_customer_text: Optional[str] = None
    delivery_surcharge_percent: float = 0.0
    delivery_surcharge_amount: float = 0.0
    express_days_status: Optional[str] = None
    delivery_policy_version: Optional[str] = None
    valid_until: Optional[datetime] = None

    # content
    openings: List[QuoteOpening] = Field(default_factory=list)
    lines: List[QuoteLine] = Field(default_factory=list)

    # pricing
    subtotal: float = 0.0
    total_discounts: float = 0.0
    total_surcharges: float = 0.0
    taxable_amount: float = 0.0
    vat_amount: float = 0.0
    total: float = 0.0
    internal_cost: float = 0.0
    margin_abs: float = 0.0
    margin_pct: float = 0.0

    # snapshot at send/approval
    price_snapshot: Dict[str, Any] = Field(default_factory=dict)

    # workflow
    quote_status: str = "draft"
    approval: Approval = Field(default_factory=Approval)
    probability: int = 20
    next_action_at: Optional[datetime] = None
    next_action_note: Optional[str] = None

    # send/tracking
    sent_at: Optional[datetime] = None
    sent_by: Optional[str] = None
    sent_to: Optional[str] = None
    sent_channel: Optional[str] = None  # email | whatsapp | link | print
    viewed_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    converted_at: Optional[datetime] = None
    contract_id: Optional[str] = None

    # notes
    notes: Optional[str] = None
    notes_internal: Optional[str] = None
    disclaimer: Optional[str] = None
    pdf_storage_key: Optional[str] = None

    # --- Installation Mode V1 (msg 393) ---
    installation_mode: Optional[str] = None   # SUPPLY_ONLY | SUPPLY_AND_INSTALLATION
    dismantling_mode: str = "EXCLUDED"        # INCLUDED | EXCLUDED | NOT_APPLICABLE
    disposal_mode: str = "EXCLUDED"           # INCLUDED | EXCLUDED | NOT_APPLICABLE

    # --- Withholding + ENEA (msg 395/397) ---
    # ⇐ msg 397: withholding non è più una scelta autonoma.
    # Deriva da tax_deduction_requested (single source of truth).
    tax_deduction_requested: bool = False
    withholding_applicable: bool = False
    withholding_rate: float = 0.11
    enea_practice_code: Optional[str] = None


class QuoteCreate(BaseModel):
    lead_id: Optional[str] = None
    customer_id: Optional[str] = None
    site_id: Optional[str] = None
    contact_id: Optional[str] = None
    title: Optional[str] = None
    intervention_type: str = "new"
    site_address: Optional[LeadAddress] = None
    valid_until: Optional[datetime] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None
    assigned_to: Optional[str] = None


class QuoteUpdate(BaseModel):
    title: Optional[str] = None
    delivery_mode: Optional[str] = None
    intervention_type: Optional[str] = None
    tax_practice: Optional[str] = None
    payment_terms: Optional[str] = None
    valid_until: Optional[datetime] = None
    site_address: Optional[LeadAddress] = None
    probability: Optional[int] = None
    notes: Optional[str] = None
    notes_internal: Optional[str] = None
    next_action_at: Optional[datetime] = None
    next_action_note: Optional[str] = None
    # --- Installation Mode V1 (msg 393) ---
    installation_mode: Optional[str] = None
    dismantling_mode: Optional[str] = None
    disposal_mode: Optional[str] = None
    # --- Withholding + ENEA (msg 395/397) ---
    tax_deduction_requested: Optional[bool] = None
    withholding_applicable: Optional[bool] = None
    withholding_rate: Optional[float] = None
    enea_practice_code: Optional[str] = None


class QuoteLineCreate(BaseModel):
    opening_id: Optional[str] = None
    category: str
    product_key: Optional[str] = None
    product_config: Dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    width_mm: Optional[int] = None
    height_mm: Optional[int] = None
    quantity: float = 1.0
    base_price: float = 0.0
    surcharges: List[Dict[str, Any]] = Field(default_factory=list)
    discount_pct: float = 0.0
    discount_amount: float = 0.0
    internal_cost: float = 0.0
    vat_rate: float = 0.22
    # Multi-Category V1 additive
    source: Optional[str] = None
    category_id: Optional[str] = None
    category_code: Optional[str] = None
    product_id: Optional[str] = None
    product_code: Optional[str] = None
    pricing_model: Optional[str] = None
    configuration_snapshot: Optional[Dict[str, Any]] = None
    pricing_snapshot: Optional[Dict[str, Any]] = None
    technical_snapshot: Optional[Dict[str, Any]] = None
    commercial_snapshot: Optional[Dict[str, Any]] = None
    financial_snapshot: Optional[Dict[str, Any]] = None
    unit_price_final: Optional[float] = None
    subtotal_line: Optional[float] = None


class QuoteLineUpdate(BaseModel):
    opening_id: Optional[str] = None
    category: Optional[str] = None
    product_key: Optional[str] = None
    product_config: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    width_mm: Optional[int] = None
    height_mm: Optional[int] = None
    quantity: Optional[float] = None
    base_price: Optional[float] = None
    surcharges: Optional[List[Dict[str, Any]]] = None
    discount_pct: Optional[float] = None
    discount_amount: Optional[float] = None
    internal_cost: Optional[float] = None
    vat_rate: Optional[float] = None
    order_index: Optional[int] = None


class QuoteOpeningCreate(BaseModel):
    code: str = ""
    floor: Optional[str] = None
    room: Optional[str] = None
    description: Optional[str] = None
    width_mm: Optional[int] = None
    height_mm: Optional[int] = None
    quantity: int = 1
    notes: Optional[str] = None
    accessibility: Optional[str] = None
    wall_type: Optional[str] = None
    installation_type: Optional[str] = None
    order_index: int = 0


class QuoteOpeningUpdate(BaseModel):
    code: Optional[str] = None
    floor: Optional[str] = None
    room: Optional[str] = None
    description: Optional[str] = None
    width_mm: Optional[int] = None
    height_mm: Optional[int] = None
    quantity: Optional[int] = None
    notes: Optional[str] = None
    accessibility: Optional[str] = None
    wall_type: Optional[str] = None
    installation_type: Optional[str] = None
    opening_status: Optional[str] = None
    order_index: Optional[int] = None


class QuoteStatusChange(BaseModel):
    new_status: str
    reason: Optional[str] = None


class QuoteApprovalDecision(BaseModel):
    approved: bool
    reason: Optional[str] = None


# ---------- Pricelist / Rules ----------
class PriceRuleTier(BaseModel):
    from_qty: float = 0
    to_qty: Optional[float] = None
    price: Optional[float] = None
    pct: Optional[float] = None


class PriceRule(BaseDoc):
    pricelist_id: Optional[str] = None
    product_key: str
    name: str
    description: Optional[str] = None
    base_type: str = "piece"  # piece | sqm | linear_m | hourly | fixed
    base_price: float = 0.0
    min_billable_sqm: float = 0.0
    tiers: List[PriceRuleTier] = Field(default_factory=list)
    # surcharge/discount config
    surcharge_type: Optional[str] = None  # pct | fixed
    surcharge_amount: float = 0.0
    surcharge_condition: Optional[str] = None  # freeform key (color:ivory, film:two_sides_different)
    rounding_rule: Optional[str] = None  # nearest_1, nearest_5, nearest_10
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    priority: int = 100
    active: bool = True


class PriceRuleCreate(BaseModel):
    pricelist_id: Optional[str] = None
    product_key: str
    name: str
    description: Optional[str] = None
    base_type: str = "piece"
    base_price: float = 0.0
    min_billable_sqm: float = 0.0
    surcharge_type: Optional[str] = None
    surcharge_amount: float = 0.0
    surcharge_condition: Optional[str] = None
    rounding_rule: Optional[str] = None
    priority: int = 100
    active: bool = True


class Pricelist(BaseDoc):
    name: str
    description: Optional[str] = None
    currency: str = "EUR"
    is_default: bool = False
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    priority: int = 100


class DiscountThreshold(BaseDoc):
    role_id: Optional[str] = None
    role_slug: Optional[str] = None  # commerciale|admin_azienda|super_admin
    max_discount_pct: float = 0.0
    requires_approval_by_role_slug: Optional[str] = None


class Product(BaseDoc):
    """Catalog product for configurators (windows series, glass types, colors etc.)."""
    key: str
    name: str
    category: str
    description: Optional[str] = None
    config_schema: Dict[str, Any] = Field(default_factory=dict)
    base_price: float = 0.0
    image_url: Optional[str] = None
    active: bool = True


class Contract(BaseDoc):
    number: Optional[str] = None
    number_int: Optional[int] = None
    quote_id: str
    quote_revision: int = 0
    customer_id: Optional[str] = None
    # snapshots
    quote_snapshot: Dict[str, Any] = Field(default_factory=dict)
    # workflow
    contract_status: str = "draft"  # draft | signed | cancelled
    signed_at: Optional[datetime] = None
    signed_by_name: Optional[str] = None
    signed_ip: Optional[str] = None
    signed_ua: Optional[str] = None
    signature_data_url: Optional[str] = None
    signature_hash: Optional[str] = None
    pdf_storage_key: Optional[str] = None
