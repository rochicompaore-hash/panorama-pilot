"""M4..M17 — Operational ERP models.

Design principles:
- Every entity extends BaseDoc (id UUID, tenant_id, created_at, updated_at, version, soft delete).
- Money is stored as `Decimal128`-style plain floats for arithmetic (converted from Decimal on write).
  When precision matters, `Decimal` is used server-side in the service layer.
- Every operational entity has status transitions guarded by an explicit whitelist.
- No PII, secrets, or margins are exposed in these DTOs; margins/costs are opt-in fields
  filtered by RBAC in the router layer.
"""
from __future__ import annotations
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from app.models import BaseDoc, new_id


# ==============================================================================
# M4 — SURVEYS (Rilievo tecnico)
# ==============================================================================
class SurveyOpening(BaseModel):
    """Vano rilevato — misure definitive che sostituiscono quelle indicative del preventivo."""
    ref: str  # V1, V2, ...
    location: Optional[str] = None  # es. "Camera da letto"
    # Preventivo (measurements at quote time — snapshot)
    quote_width_mm: Optional[float] = None
    quote_height_mm: Optional[float] = None
    # Rilievo definitivo
    measured_width_mm: Optional[float] = None
    measured_height_mm: Optional[float] = None
    frame_width_mm: Optional[float] = None
    frame_height_mm: Optional[float] = None
    shoulders_mm: Optional[float] = None  # spalle
    lintel_mm: Optional[float] = None  # architrave
    sill_mm: Optional[float] = None  # davanzale
    threshold_mm: Optional[float] = None  # soglia
    shutter_box_mm: Optional[float] = None  # cassonetto
    guides_mm: Optional[float] = None
    masonry_type: Optional[str] = None  # muratura tradizionale, laterizio, cemento armato, gasbeton, cartongesso...
    subframe_present: bool = False
    subframe_note: Optional[str] = None
    trim_present: bool = False
    opening_direction: Optional[str] = None  # dx / sx / interna / esterna / anta-ribalta
    floor: Optional[str] = None
    elevator: bool = False
    platform_needed: bool = False
    scaffolding_needed: bool = False
    masonry_works: Optional[str] = None
    systems_impact: Optional[str] = None  # tende, allarmi, elettricità...
    accessibility_note: Optional[str] = None
    notes: Optional[str] = None
    photos: List[str] = Field(default_factory=list)  # attachment ids
    critical_issues: List[str] = Field(default_factory=list)
    # Variance & delta
    variance_amount: Optional[float] = None  # differenza economica derivata


class Survey(BaseDoc):
    number: Optional[str] = None
    number_int: Optional[int] = None
    quote_id: Optional[str] = None
    contract_id: Optional[str] = None
    customer_id: str
    lead_id: Optional[str] = None
    site_address: Optional[Dict[str, Any]] = None
    technician_id: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    customer_approved_at: Optional[datetime] = None
    customer_signer_name: Optional[str] = None
    customer_signature_hash: Optional[str] = None
    technician_signature_hash: Optional[str] = None
    openings: List[SurveyOpening] = Field(default_factory=list)
    variance_total: float = 0.0
    variance_reason: Optional[str] = None
    survey_status: str = "draft"  # draft|scheduled|in_progress|completed|approved|rejected|converted|cancelled
    is_locked: bool = False  # once approved, cannot change without new revision
    notes: Optional[str] = None
    attachments: List[str] = Field(default_factory=list)


# ==============================================================================
# M5 — SALES ORDERS & PURCHASING
# ==============================================================================
class SalesOrderLine(BaseModel):
    ref: str
    product_type_key: Optional[str] = None
    description: str
    quantity: float = 1
    unit_price: float = 0
    line_subtotal: float = 0
    vat_rate: float = 22
    survey_opening_ref: Optional[str] = None
    bom_ref: Optional[str] = None  # link to BOM version


class SalesOrder(BaseDoc):
    number: Optional[str] = None
    number_int: Optional[int] = None
    quote_id: Optional[str] = None
    contract_id: Optional[str] = None
    survey_id: Optional[str] = None
    customer_id: str
    site_address: Optional[Dict[str, Any]] = None
    lines: List[SalesOrderLine] = Field(default_factory=list)
    subtotal: float = 0
    vat_amount: float = 0
    total: float = 0
    order_status: str = "draft"
    # ^ draft|confirmed|technically_validated|waiting_materials|ready_for_production|
    #   in_production|completed|ready_for_installation|installed|closed|cancelled
    expected_ready_date: Optional[date] = None
    expected_installation_date: Optional[date] = None
    priority: int = 3  # 1 (high) .. 5
    notes: Optional[str] = None


class Supplier(BaseDoc):
    name: str
    vat_number: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: str = "IT"
    payment_terms: Optional[str] = None  # es. "30gg data fattura"
    default_delivery_lead_days: int = 15
    quality_rating: int = 3  # 1..5
    is_preferred: bool = False
    notes: Optional[str] = None
    categories: List[str] = Field(default_factory=list)  # profili, ferramenta, vetro, accessori...


class SupplierPriceEntry(BaseModel):
    item_code: str
    unit_price: float
    currency: str = "EUR"
    min_qty: float = 1
    lead_time_days: Optional[int] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    notes: Optional[str] = None


class SupplierPriceList(BaseDoc):
    supplier_id: str
    name: str
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    entries: List[SupplierPriceEntry] = Field(default_factory=list)
    is_active: bool = True


class PurchaseOrderLine(BaseModel):
    item_code: str
    description: str
    quantity: float
    unit_price: float
    line_subtotal: float
    delivery_date: Optional[date] = None
    sales_order_id: Optional[str] = None
    received_qty: float = 0


class PurchaseOrder(BaseDoc):
    number: Optional[str] = None
    number_int: Optional[int] = None
    supplier_id: str
    supplier_name: Optional[str] = None
    lines: List[PurchaseOrderLine] = Field(default_factory=list)
    subtotal: float = 0
    vat_amount: float = 0
    total: float = 0
    po_status: str = "draft"
    # ^ draft|requested|approved|sent|partially_received|received|delayed|disputed|cancelled
    expected_delivery: Optional[date] = None
    actual_delivery: Optional[date] = None
    linked_sales_orders: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class GoodsReceipt(BaseDoc):
    """DDT ingresso — ricevimento merci da ordine fornitore."""
    number: Optional[str] = None
    number_int: Optional[int] = None
    purchase_order_id: str
    supplier_id: str
    received_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    received_by: Optional[str] = None
    lines: List[Dict[str, Any]] = Field(default_factory=list)  # {item_code, qty_received, qty_expected, lot, notes}
    has_non_conformity: bool = False
    notes: Optional[str] = None


class PurchaseNonConformity(BaseDoc):
    goods_receipt_id: str
    purchase_order_id: str
    supplier_id: str
    item_code: str
    qty_affected: float
    kind: str  # damaged | wrong_item | wrong_quantity | quality_issue | other
    severity: str = "minor"  # minor | major | critical
    action: Optional[str] = None  # return | rework | accept_with_discount | refuse
    resolved_at: Optional[datetime] = None
    notes: Optional[str] = None


# ==============================================================================
# M6 — INVENTORY (Magazzino)
# ==============================================================================
class Item(BaseDoc):
    code: str  # unique per tenant
    name: str
    description: Optional[str] = None
    category: Optional[str] = None  # profilo, ferramenta, vetro, ...
    unit_of_measure: str = "pz"  # pz, m, m², kg
    default_supplier_id: Optional[str] = None
    min_stock: float = 0
    reorder_qty: float = 0
    is_bar: bool = False  # true for barre profilo
    bar_length_mm: Optional[float] = None
    profile_color_ext: Optional[str] = None
    profile_color_int: Optional[str] = None
    profile_core: Optional[str] = None
    profile_film: Optional[str] = None
    profile_finish: Optional[str] = None
    barcode: Optional[str] = None
    price_last_purchase: Optional[float] = None
    notes: Optional[str] = None


class StockLocation(BaseDoc):
    code: str
    name: str
    kind: str = "warehouse"  # warehouse|production|ready|reject


class StockLevel(BaseDoc):
    """Aggregated available/committed/on_order per item+location."""
    item_id: str
    item_code: str
    location_id: str
    qty_on_hand: float = 0
    qty_committed: float = 0
    qty_on_order: float = 0
    qty_available: float = 0  # = on_hand - committed
    updated_at_movement: Optional[datetime] = None


class StockMovement(BaseDoc):
    """Immutable ledger of stock movements."""
    kind: str  # inbound | outbound | transfer | adjust | reserve | unreserve | scrap
    item_id: str
    item_code: str
    from_location_id: Optional[str] = None
    to_location_id: Optional[str] = None
    quantity: float
    lot: Optional[str] = None
    ref_type: Optional[str] = None  # purchase_order|sales_order|production_order|inventory
    ref_id: Optional[str] = None
    notes: Optional[str] = None
    # movements are append-only; never allow updates that change existing quantities


class InventoryCount(BaseDoc):
    number: Optional[str] = None
    location_id: str
    started_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    completed_at: Optional[datetime] = None
    lines: List[Dict[str, Any]] = Field(default_factory=list)  # {item_id, expected, counted, delta}
    is_closed: bool = False


# ==============================================================================
# M7 — PRODUCTION
# ==============================================================================
class BOMComponent(BaseModel):
    item_code: str
    description: Optional[str] = None
    quantity_formula: Optional[str] = None  # es. "w+h+80" — evaluated by safe formula engine
    fixed_quantity: Optional[float] = None
    scrap_percent: float = 0
    role: Optional[str] = None  # profilo, rinforzo, vetro, ferramenta, guarnizione, ...


class BOM(BaseDoc):
    """Distinta base versionata per un tipo prodotto."""
    product_type_key: str
    label: str
    version: int = 1  # explicit BOM version (independent from BaseDoc.version optimistic-lock)
    components: List[BOMComponent] = Field(default_factory=list)
    is_active: bool = True
    notes: Optional[str] = None


class CuttingPiece(BaseModel):
    profile_code: str
    length_mm: float
    quantity: int = 1
    labels: List[str] = Field(default_factory=list)  # es. ["V1-anta-sup"]


class BarOptimization(BaseModel):
    profile_code: str
    bar_length_mm: float
    bars_used: int = 0
    total_scrap_mm: float = 0
    yield_percent: float = 0
    layout: List[List[float]] = Field(default_factory=list)  # per-bar cut sequence


class ProductionOrder(BaseDoc):
    number: Optional[str] = None
    number_int: Optional[int] = None
    sales_order_id: str
    customer_id: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    prod_status: str = "waiting_validation"
    # ^ waiting_validation|waiting_materials|scheduled|released|in_progress|paused|
    #   blocked|quality_control|completed|packed|ready_for_dispatch
    priority: int = 3
    lines: List[Dict[str, Any]] = Field(default_factory=list)  # {bom_id, product_ref, quantity, cutting_list_id}
    material_requirements: List[Dict[str, Any]] = Field(default_factory=list)  # {item_code, qty}
    material_committed: bool = False
    notes: Optional[str] = None


class CuttingList(BaseDoc):
    production_order_id: str
    pieces: List[CuttingPiece] = Field(default_factory=list)
    optimizations: List[BarOptimization] = Field(default_factory=list)
    total_bars_used: int = 0
    total_yield_percent: float = 0
    generated_at: datetime = Field(default_factory=lambda: datetime.utcnow())


class ProductionPhaseLog(BaseDoc):
    """One log line per phase executed on a production order."""
    production_order_id: str
    phase: str  # validation | picking | cutting | reinforcement | welding | assembly |
                # hardware | glazing | qc | packing | dispatch | manual
    operator_id: Optional[str] = None
    machine: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    expected_minutes: Optional[float] = None
    actual_minutes: Optional[float] = None
    quantity_ok: int = 0
    quantity_scrap: int = 0
    quantity_rework: int = 0
    stop_reason: Optional[str] = None
    notes: Optional[str] = None
    photos: List[str] = Field(default_factory=list)


# ==============================================================================
# M9 — QC
# ==============================================================================
class QCChecklistItem(BaseModel):
    code: str
    label: str
    required: bool = True
    passed: Optional[bool] = None
    note: Optional[str] = None


class QCCheck(BaseDoc):
    production_order_id: str
    stage: str = "final"  # inbound | in_process | final
    checked_by: Optional[str] = None
    checked_at: Optional[datetime] = None
    items: List[QCChecklistItem] = Field(default_factory=list)
    passed: Optional[bool] = None
    notes: Optional[str] = None


class NonConformity(BaseDoc):
    kind: str  # dimensional | aesthetic | welding | hardware | glazing | packaging | other
    severity: str = "minor"  # minor|major|critical
    phase: Optional[str] = None
    production_order_id: Optional[str] = None
    sales_order_id: Optional[str] = None
    supplier_id: Optional[str] = None
    item_code: Optional[str] = None
    cause: Optional[str] = None
    action: Optional[str] = None  # rework|scrap|accept|return
    cost: Optional[float] = None
    resolution: Optional[str] = None
    resolved_at: Optional[datetime] = None
    photos: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


# ==============================================================================
# M10 — FINISHED GOODS / SHIPMENTS
# ==============================================================================
class FinishedGoodItem(BaseModel):
    ref: str  # es. V1-a1
    label: Optional[str] = None
    weight_kg: Optional[float] = None
    dimensions_cm: Optional[str] = None
    barcode: Optional[str] = None
    qr_payload: Optional[str] = None


class FinishedGoodPack(BaseDoc):
    sales_order_id: str
    production_order_id: Optional[str] = None
    pack_number: Optional[str] = None
    items: List[FinishedGoodItem] = Field(default_factory=list)
    location_id: Optional[str] = None
    is_dispatched: bool = False
    dispatched_at: Optional[datetime] = None


class Shipment(BaseDoc):
    number: Optional[str] = None
    number_int: Optional[int] = None
    sales_order_id: Optional[str] = None
    packs: List[str] = Field(default_factory=list)  # FinishedGoodPack ids
    driver_name: Optional[str] = None
    vehicle_plate: Optional[str] = None
    departure_at: Optional[datetime] = None
    arrival_at: Optional[datetime] = None
    signed_by: Optional[str] = None
    proof_photos: List[str] = Field(default_factory=list)
    shipment_status: str = "draft"  # draft|loaded|in_transit|delivered|failed


# ==============================================================================
# M11 — INSTALLATION PLANNING
# ==============================================================================
class InstallationCrew(BaseDoc):
    name: str
    members: List[str] = Field(default_factory=list)  # user ids
    skills: List[str] = Field(default_factory=list)
    equipment_notes: Optional[str] = None
    is_active: bool = True


class InstallationPlan(BaseDoc):
    number: Optional[str] = None
    number_int: Optional[int] = None
    sales_order_id: str
    customer_id: Optional[str] = None
    site_address: Optional[Dict[str, Any]] = None
    crew_id: Optional[str] = None
    scheduled_date: Optional[date] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    estimated_duration_h: Optional[float] = None
    equipment_needed: List[str] = Field(default_factory=list)  # ponteggi, piattaforma, ...
    materials_confirmed: bool = False
    customer_confirmed_at: Optional[datetime] = None
    plan_status: str = "draft"
    # ^ draft|proposed|customer_confirmed|scheduled|in_progress|completed|
    #   postponed|cancelled|blocked_customer|blocked_materials|blocked_weather
    notes: Optional[str] = None


# ==============================================================================
# M12 — INSTALLATION REPORT
# ==============================================================================
class InstallationReport(BaseDoc):
    installation_plan_id: str
    sales_order_id: Optional[str] = None
    customer_id: Optional[str] = None
    check_in_at: Optional[datetime] = None
    check_out_at: Optional[datetime] = None
    lead_installer_id: Optional[str] = None
    photos_before: List[str] = Field(default_factory=list)
    photos_during: List[str] = Field(default_factory=list)
    photos_after: List[str] = Field(default_factory=list)
    products_installed: List[Dict[str, Any]] = Field(default_factory=list)  # {ref, done, note}
    extra_materials: List[Dict[str, Any]] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)
    variances: List[str] = Field(default_factory=list)
    cleanup_done: bool = False
    waste_disposal: Optional[str] = None
    regulations_ok: bool = False
    reservations: Optional[str] = None
    customer_notes: Optional[str] = None
    customer_signer_name: Optional[str] = None
    customer_signature_hash: Optional[str] = None
    crew_signer_name: Optional[str] = None
    crew_signature_hash: Optional[str] = None
    outcome: Optional[str] = None  # completed | partial | postponed | issue | material_missing | damage | service_needed
    report_status: str = "draft"  # draft|submitted|approved


# ==============================================================================
# M13 — SERVICE / TICKETS
# ==============================================================================
class ServiceTicket(BaseDoc):
    number: Optional[str] = None
    number_int: Optional[int] = None
    customer_id: str
    sales_order_id: Optional[str] = None
    installation_plan_id: Optional[str] = None
    product_ref: Optional[str] = None  # V1, ecc.
    opening_ref: Optional[str] = None
    subject: str
    description: Optional[str] = None
    priority: str = "normal"  # low|normal|high|urgent
    warranty_scope: Optional[str] = None  # product|glass|installation|hardware|out_of_warranty
    ticket_status: str = "opened"
    # ^ opened|triaged|waiting_customer|waiting_material|scheduled|in_progress|resolved|closed|rejected
    responsibility: Optional[str] = None  # company|supplier|customer|shared
    assigned_to: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    cost: Optional[float] = None
    photos: List[str] = Field(default_factory=list)
    parts_needed: List[Dict[str, Any]] = Field(default_factory=list)
    interventions: List[Dict[str, Any]] = Field(default_factory=list)
    review_rating: Optional[int] = None  # 1..5


# ==============================================================================
# M14 — ADMINISTRATION / PAYMENTS
# ==============================================================================
class PaymentInstallment(BaseModel):
    ref: str  # I1, I2...
    label: str
    trigger: str  # signature|survey|goods_ready|before_installation|on_completion|fixed_date
    percent: Optional[float] = None
    amount: Optional[float] = None
    due_date: Optional[date] = None
    paid_amount: float = 0
    paid_at: Optional[datetime] = None
    payment_method: Optional[str] = None
    installment_status: str = "pending"  # pending|partial|paid|overdue|cancelled
    reminder_sent_at: Optional[datetime] = None


class PaymentPlan(BaseDoc):
    """One plan per contract or sales_order. Amounts computed from total."""
    contract_id: Optional[str] = None
    sales_order_id: Optional[str] = None
    customer_id: str
    total_amount: float
    currency: str = "EUR"
    installments: List[PaymentInstallment] = Field(default_factory=list)
    outstanding_amount: float = 0
    paid_amount: float = 0
    plan_status: str = "active"  # active|closed|cancelled


class Payment(BaseDoc):
    """Actual receipt event."""
    payment_plan_id: str
    customer_id: str
    installment_ref: Optional[str] = None
    amount: float
    method: Optional[str] = None  # bonifico|contanti|assegno|carta|finanziamento
    reference: Optional[str] = None  # bank ref, cheque nr
    received_at: datetime
    notes: Optional[str] = None
    reconciled: bool = False


class Invoice(BaseDoc):
    number: Optional[str] = None
    number_int: Optional[int] = None
    customer_id: str
    contract_id: Optional[str] = None
    sales_order_id: Optional[str] = None
    issue_date: date
    due_date: Optional[date] = None
    subtotal: float = 0
    vat_amount: float = 0
    total: float = 0
    lines: List[Dict[str, Any]] = Field(default_factory=list)
    invoice_status: str = "draft"  # draft|issued|sent|paid|partially_paid|overdue|cancelled|credit_note
    paid_amount: float = 0
    linked_payments: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


# ==============================================================================
# M17 — AI CFO
# ==============================================================================
class AICFOSuggestion(BaseDoc):
    """Every suggestion cites data sources, period, and confidence."""
    period_from: date
    period_to: date
    category: str  # cash_flow|receivables|payables|margin|risk|anomaly|productivity|savings
    title: str
    body: str
    action_suggested: Optional[str] = None
    confidence: float = 0.5  # 0..1
    risk_level: str = "low"  # low|medium|high
    data_sources: List[str] = Field(default_factory=list)  # es. ["invoices", "payments"]
    computed_metrics: Dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    is_actionable: bool = True
    is_dismissed: bool = False
    dismissed_at: Optional[datetime] = None
    dismissed_by: Optional[str] = None
