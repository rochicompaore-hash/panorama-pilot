"""Workflow domain models — Abaco tecnico, Ordine esecutivo, Production release check,
Customer tracking mapping, Timeline unificata.

Segue le convenzioni: BaseDoc tenant-scoped, versioning append-only,
snapshot canonici, audit obbligatorio.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from app.models import BaseDoc, new_id


# ============================================================================
# TECHNICAL SCHEDULE — Abaco tecnico definitivo
# ============================================================================
class TechnicalScheduleItem(BaseModel):
    """Riga abaco: 1 vano/serramento."""
    id: str = Field(default_factory=new_id)
    ref: str  # V1, V2, ...
    room: Optional[str] = None
    position: Optional[str] = None
    product_key: str
    typology: Optional[str] = None  # 1anta, 2ante, fisso, portafinestra, scorrevole…
    # Misure DEFINITIVE (rilievo validato)
    final_width_mm: int
    final_height_mm: int
    nr_ante: int = 1
    nr_traversi: int = 0
    opening_direction: Optional[str] = None  # dx | sx | ribalta | scorrevole
    opening_sense: Optional[str] = None       # interna | esterna
    # Configurazione definitiva
    profile_system_id: str
    internal_color_id: Optional[str] = None
    external_color_id: Optional[str] = None
    glass_type_id: Optional[str] = None
    hardware_kit_id: Optional[str] = None
    threshold: Optional[str] = None
    shutter_box: Optional[str] = None
    darkening: Optional[str] = None            # oscurante
    insect_screen: Optional[bool] = False       # zanzariera
    accessories: List[Dict[str, Any]] = Field(default_factory=list)
    technical_notes: Optional[str] = None
    additional_works: Optional[str] = None      # opere accessorie
    # Riferimenti
    survey_opening_ref: Optional[str] = None
    quote_line_id: Optional[str] = None
    # Snapshot preview parametrica (BOM commerciale + SVG)
    parametric_snapshot: Dict[str, Any] = Field(default_factory=dict)
    svg_drawing: Optional[str] = None
    photos: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    blocking_errors: List[Dict[str, Any]] = Field(default_factory=list)
    validation_status: Literal["draft", "validated", "signed", "released"] = "draft"


TechnicalScheduleStatus = Literal[
    "draft", "in_technical_review", "approved_internally",
    "sent_to_customer", "viewed", "change_requested",
    "awaiting_signature", "signed", "superseded", "cancelled", "released_to_production",
]


class TechnicalSchedule(BaseDoc):
    number: Optional[str] = None
    number_int: Optional[int] = None
    version: int = 1
    revision_label: str = "V01"
    parent_version_id: Optional[str] = None
    is_current: bool = True
    superseded_by_id: Optional[str] = None
    # Riferimenti al workflow
    quote_id: str
    quote_revision: int = 0
    contract_id: str
    survey_id: str
    customer_id: str
    site_address: Optional[Dict[str, Any]] = None
    # Contenuto
    items: List[TechnicalScheduleItem] = Field(default_factory=list)
    # Workflow
    ts_status: TechnicalScheduleStatus = "draft"
    # Approvazione interna
    approved_internally_at: Optional[datetime] = None
    approved_internally_by: Optional[str] = None
    technical_supervisor_id: Optional[str] = None
    # Invio cliente
    sent_to_customer_at: Optional[datetime] = None
    sent_via: Optional[str] = None
    public_token_id: Optional[str] = None
    viewed_at: Optional[datetime] = None
    # Cliente
    customer_change_request: Optional[str] = None
    customer_change_requested_at: Optional[datetime] = None
    # Firma (FES)
    signed_at: Optional[datetime] = None
    signed_by_name: Optional[str] = None
    signed_email: Optional[str] = None
    signed_ip_hash: Optional[str] = None
    signed_user_agent: Optional[str] = None
    signature_hash: Optional[str] = None
    evidence_id: Optional[str] = None
    original_pdf_key: Optional[str] = None
    signed_pdf_key: Optional[str] = None
    # Release
    released_at: Optional[datetime] = None
    released_by: Optional[str] = None
    executive_order_id: Optional[str] = None
    # Snapshot canonico
    snapshot_hash: Optional[str] = None
    notes: Optional[str] = None


class TechnicalScheduleCreate(BaseModel):
    survey_id: str
    contract_id: Optional[str] = None
    items: Optional[List[TechnicalScheduleItem]] = None
    notes: Optional[str] = None


class TechnicalScheduleUpdate(BaseModel):
    items: Optional[List[TechnicalScheduleItem]] = None
    notes: Optional[str] = None
    technical_supervisor_id: Optional[str] = None


class TechnicalScheduleStatusChange(BaseModel):
    new_status: TechnicalScheduleStatus
    reason: Optional[str] = None


class TechnicalScheduleSendRequest(BaseModel):
    channel: Literal["email", "whatsapp", "link"] = "link"
    require_otp: bool = True
    message: Optional[str] = None


class TechnicalScheduleSignPayload(BaseModel):
    """FES signature per abaco."""
    signer_name: str
    signer_email: str
    otp_code: Optional[str] = None
    signature_data_url: str  # canvas base64 png
    consent_all_openings_verified: bool
    consent_measurements_verified: bool
    consent_colors_glass_openings_verified: bool
    consent_supersedes_preview: bool
    consent_authorize_production: bool
    consent_accept_variances_if_any: bool
    accepted_terms_version: Optional[str] = None


# ============================================================================
# EXECUTIVE ORDER — Ordine esecutivo (post firma abaco)
# ============================================================================
class ExecutiveOrderLine(BaseModel):
    id: str = Field(default_factory=new_id)
    ref: str
    room: Optional[str] = None
    product_key: str
    typology: Optional[str] = None
    final_width_mm: int
    final_height_mm: int
    nr_ante: int = 1
    profile_system_id: str
    internal_color_id: Optional[str] = None
    external_color_id: Optional[str] = None
    glass_type_id: Optional[str] = None
    hardware_kit_id: Optional[str] = None
    accessories: List[Dict[str, Any]] = Field(default_factory=list)
    productive_bom_snapshot: Dict[str, Any] = Field(default_factory=dict)
    svg_drawing: Optional[str] = None
    quantity: int = 1
    technical_notes: Optional[str] = None
    ts_item_id: Optional[str] = None  # link a TechnicalScheduleItem
    survey_opening_ref: Optional[str] = None
    quote_line_id: Optional[str] = None


class ExecutiveOrder(BaseDoc):
    number: Optional[str] = None
    number_int: Optional[int] = None
    quote_id: str
    contract_id: str
    survey_id: str
    technical_schedule_id: str
    technical_schedule_version: int
    customer_id: str
    site_address: Optional[Dict[str, Any]] = None
    lines: List[ExecutiveOrderLine] = Field(default_factory=list)
    # Riferimenti snapshot immutabili
    contract_snapshot: Dict[str, Any] = Field(default_factory=dict)
    technical_schedule_snapshot: Dict[str, Any] = Field(default_factory=dict)
    formula_schema_version: int = 1
    engine_version: str = "1.0.0"
    # Stato
    eo_status: Literal[
        "created", "materials_check", "materials_ordered",
        "in_production", "quality_control", "packaging", "ready_for_delivery",
        "delivered", "installed", "closed", "cancelled"
    ] = "created"
    # Collegamenti produzione
    production_order_ids: List[str] = Field(default_factory=list)
    purchase_order_ids: List[str] = Field(default_factory=list)
    executive_cutting_list_id: Optional[str] = None
    productive_bom_versions: Dict[str, int] = Field(default_factory=dict)
    # Audit
    released_at: Optional[datetime] = None
    released_by: Optional[str] = None


# ============================================================================
# PRODUCTION RELEASE CHECK — controllo centrale abilitazione produzione
# ============================================================================
class ProductionReleaseCheckResult(BaseModel):
    eligible: bool
    blocking_reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    checked_at: datetime
    checked_by: str
    source_versions: Dict[str, Any] = Field(default_factory=dict)
    # Riferimenti verificati
    contract_id: Optional[str] = None
    contract_status: Optional[str] = None
    survey_id: Optional[str] = None
    survey_status: Optional[str] = None
    technical_schedule_id: Optional[str] = None
    technical_schedule_status: Optional[str] = None
    open_change_requests: int = 0
    executive_order_id: Optional[str] = None


class ProductionReleaseOverrideRequest(BaseModel):
    """Override manuale con doppia approvazione."""
    contract_id: str
    reason: str
    second_approver_user_id: str
    force: bool = False


# ============================================================================
# CUSTOMER STATUS MAPPING — mapping stato interno → stato visibile cliente
# ============================================================================
class CustomerStatusMapping(BaseDoc):
    """Mapping configurabile per tenant tra stati interni e stati mostrati al cliente.
    Convenzione key: `{domain}:{internal_status}` es. `production:cutting`, `contract:signed`.
    """
    key: str
    customer_label: str
    customer_stage: Literal[
        "contract_signed", "survey_scheduled", "survey_completed",
        "schedule_sent", "schedule_approved",
        "order_confirmed", "materials_procurement",
        "production_scheduled", "in_production", "quality_control",
        "product_completed", "delivery_prep",
        "installation_scheduled", "installation_completed",
        "final_check", "warranty_active", "service_available",
    ]
    is_public: bool = True
    order_index: int = 0
    description: Optional[str] = None
    is_demo: bool = False


class CustomerStatusMappingCreate(BaseModel):
    key: str
    customer_label: str
    customer_stage: str
    is_public: bool = True
    order_index: int = 0


class CustomerStatusMappingUpdate(BaseModel):
    customer_label: Optional[str] = None
    customer_stage: Optional[str] = None
    is_public: Optional[bool] = None
    order_index: Optional[int] = None


# ============================================================================
# UNIFIED TIMELINE — evento generico visibile a cliente/interno
# ============================================================================
class TimelineEvent(BaseDoc):
    """Evento della timeline unificata cliente/interno.
    Campi minimi conformi al requisito §27.
    """
    domain: Literal[
        "lead", "quote", "contract", "survey", "technical_schedule",
        "executive_order", "purchase_order", "production", "quality_control",
        "logistics", "installation", "final_check", "payment", "service", "warranty",
        "handoff", "commission",
    ]
    event_type: str                 # es. "quote.sent", "contract.signed", "abaco.signed"
    ref_id: Optional[str] = None    # id dell'entità di dominio
    quote_id: Optional[str] = None
    contract_id: Optional[str] = None
    customer_id: Optional[str] = None
    survey_id: Optional[str] = None
    technical_schedule_id: Optional[str] = None
    executive_order_id: Optional[str] = None
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    document_id: Optional[str] = None
    document_kind: Optional[str] = None   # pdf | evidence | attachment
    actor_id: Optional[str] = None
    actor_email: Optional[str] = None
    source: Literal["system", "user", "customer", "webhook", "scheduler"] = "system"
    is_customer_visible: bool = False
    customer_label: Optional[str] = None
    customer_stage: Optional[str] = None
    ip_hash: Optional[str] = None
    request_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# VARIANCE / CHANGE ORDER — variante economica generata da rilievo
# ============================================================================
class VarianceLine(BaseModel):
    ref: str
    description: str
    delta_price: float = 0.0
    delta_cost: float = 0.0
    kind: Literal[
        "no_impact", "technical_only", "economic",
        "requires_internal_approval", "requires_customer_approval",
        "not_producible", "contract_variant_required",
    ]
    old_config: Dict[str, Any] = Field(default_factory=dict)
    new_config: Dict[str, Any] = Field(default_factory=dict)


class Variance(BaseDoc):
    number: Optional[str] = None
    number_int: Optional[int] = None
    quote_id: str
    contract_id: str
    survey_id: Optional[str] = None
    technical_schedule_id: Optional[str] = None
    customer_id: str
    lines: List[VarianceLine] = Field(default_factory=list)
    total_delta_price: float = 0.0
    total_delta_cost: float = 0.0
    variance_status: Literal[
        "draft", "sent", "customer_viewed", "accepted", "rejected", "signed", "cancelled",
    ] = "draft"
    reason: Optional[str] = None
    customer_signature_hash: Optional[str] = None
    signed_at: Optional[datetime] = None
    signed_pdf_key: Optional[str] = None


class ProductionReleaseCheckRequest(BaseModel):
    contract_id: str
