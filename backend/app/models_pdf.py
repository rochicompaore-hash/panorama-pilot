"""M3.3.2 — PDF templates, clauses, PDF snapshots, payment terms."""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field
from app.models import BaseDoc


# ---------- Clause library ----------
CLAUSE_CATEGORIES = [
    "misure", "posa", "opere_murarie", "smaltimento", "elettricita",
    "accessibilita", "ponteggi", "tempistiche", "pagamenti", "garanzia",
    "detrazioni", "immagini", "variazioni", "annullamento", "privacy",
    "generale",
]


class Clause(BaseDoc):
    code: str  # e.g., CL_MISURE_INDICATIVE
    title: str
    text: str
    category: str = "generale"
    language: str = "it"
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    # Applicability
    product_keys: List[str] = Field(default_factory=list)  # empty = all products
    apply_conditions: List[Dict[str, Any]] = Field(default_factory=list)
    mandatory: bool = False
    order_index: int = 100
    # State
    active: bool = True
    # Versioning: modifying a clause creates a new version doc (append-only history via `clause_versions`)


class ClauseCreate(BaseModel):
    code: str
    title: str
    text: str
    category: str = "generale"
    language: str = "it"
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    product_keys: List[str] = Field(default_factory=list)
    apply_conditions: List[Dict[str, Any]] = Field(default_factory=list)
    mandatory: bool = False
    order_index: int = 100


class ClauseUpdate(BaseModel):
    title: Optional[str] = None
    text: Optional[str] = None
    category: Optional[str] = None
    language: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    product_keys: Optional[List[str]] = None
    apply_conditions: Optional[List[Dict[str, Any]]] = None
    mandatory: Optional[bool] = None
    order_index: Optional[int] = None
    active: Optional[bool] = None


# ---------- Payment terms schema ----------
class PaymentInstallment(BaseModel):
    trigger: str  # signature | survey | goods_ready | before_installation | on_completion | fixed_date
    percent: float = 0.0
    amount: float = 0.0
    days_offset: int = 0
    note: Optional[str] = None


class PaymentTermsSchema(BaseModel):
    """Structured payment terms embedded in quotes and templates."""
    kind: str = "installments"  # installments | financing | cash
    installments: List[PaymentInstallment] = Field(default_factory=list)
    financing: Optional[Dict[str, Any]] = None  # {institute, rate, installments_count, ...}
    display_note: Optional[str] = None  # e.g., "Saldo dovuto ad avviso merce pronta"


# ---------- Template ----------
class TemplateSection(BaseModel):
    """A section in the PDF template — configurable order and visibility."""
    key: str  # cover | summary | openings | economic_summary | conditions | signature
    title: Optional[str] = None
    visible: bool = True
    order_index: int = 0
    settings: Dict[str, Any] = Field(default_factory=dict)  # e.g., "show_prices_per_line", "show_images"


class TemplateStyle(BaseModel):
    primary_color: str = "#0F1720"
    secondary_color: str = "#D42027"
    font_family: str = "Inter"
    logo_width_mm: int = 40
    logo_position: str = "left"  # left | center | right
    page_margins_mm: Dict[str, int] = Field(default_factory=lambda: {"top": 15, "right": 15, "bottom": 20, "left": 15})


class QuoteTemplate(BaseDoc):
    code: str  # slug
    name: str
    language: str = "it"
    is_default: bool = False
    is_active: bool = True
    draft: bool = False
    activated_at: Optional[datetime] = None
    deactivated_at: Optional[datetime] = None
    # Config
    style: TemplateStyle = Field(default_factory=TemplateStyle)
    sections: List[TemplateSection] = Field(default_factory=list)
    # Header/footer/text blocks
    header_html: Optional[str] = None
    footer_html: Optional[str] = None
    intro_text: Optional[str] = None
    validity_days: int = 30
    default_payment_terms: PaymentTermsSchema = Field(default_factory=PaymentTermsSchema)
    warranty_months: int = 24
    delivery_days_min: int = 30
    delivery_days_max: int = 45
    # Fixed disclaimers (configurable)
    measures_disclaimer: str = (
        "Le misure riportate nel presente preventivo sono indicative e non costituiscono "
        "misure esecutive o definitive. Le misure finali saranno rilevate e validate dal "
        "tecnico incaricato prima dell'ordine e dell'avvio della produzione."
    )
    images_disclaimer: str = (
        "Immagini a scopo illustrativo. Colori, proporzioni e dettagli possono differire "
        "dal prodotto effettivamente fornito."
    )
    privacy_notice: Optional[str] = None
    # Linked clauses (by code) — mandatory ones cannot be removed by user without permission
    mandatory_clause_codes: List[str] = Field(default_factory=list)
    optional_clause_codes: List[str] = Field(default_factory=list)
    # Which company fields to show
    show_fields: Dict[str, bool] = Field(default_factory=lambda: {
        "vat_number": True, "tax_code": True, "rea": True, "share_capital": False,
        "sdi_code": True, "pec": True, "iban": True, "bank_name": True,
        "signature": True, "stamp": True, "certifications": True,
    })
    show_prices_mode: str = "per_line"  # per_line | per_opening | total_only


class QuoteTemplateCreate(BaseModel):
    code: str
    name: str
    language: str = "it"
    is_default: bool = False
    style: TemplateStyle = Field(default_factory=TemplateStyle)
    sections: List[TemplateSection] = Field(default_factory=list)
    intro_text: Optional[str] = None
    validity_days: int = 30
    warranty_months: int = 24
    delivery_days_min: int = 30
    delivery_days_max: int = 45
    default_payment_terms: PaymentTermsSchema = Field(default_factory=PaymentTermsSchema)
    mandatory_clause_codes: List[str] = Field(default_factory=list)
    optional_clause_codes: List[str] = Field(default_factory=list)
    show_prices_mode: str = "per_line"


class QuoteTemplateUpdate(BaseModel):
    name: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    draft: Optional[bool] = None
    style: Optional[TemplateStyle] = None
    sections: Optional[List[TemplateSection]] = None
    header_html: Optional[str] = None
    footer_html: Optional[str] = None
    intro_text: Optional[str] = None
    validity_days: Optional[int] = None
    warranty_months: Optional[int] = None
    delivery_days_min: Optional[int] = None
    delivery_days_max: Optional[int] = None
    default_payment_terms: Optional[PaymentTermsSchema] = None
    measures_disclaimer: Optional[str] = None
    images_disclaimer: Optional[str] = None
    privacy_notice: Optional[str] = None
    mandatory_clause_codes: Optional[List[str]] = None
    optional_clause_codes: Optional[List[str]] = None
    show_fields: Optional[Dict[str, bool]] = None
    show_prices_mode: Optional[str] = None


# ---------- Quote PDF snapshot ----------
class QuotePdf(BaseDoc):
    """Represents a generated PDF (preview or definitive) tied to a specific quote revision.

    For a given (quote_id, quote_version) generating the definitive PDF is IDEMPOTENT:
    - If a definitive PDF with the same snapshot_hash exists, return the existing one.
    - New generation only when the snapshot_hash changes (i.e., a new revision was created).
    """
    quote_id: str
    quote_number: str
    quote_revision: str
    quote_version_snapshot: int
    template_id: str
    template_version: int
    kind: str = "preview"  # preview | definitive | signed | cancelled | superseded
    watermark: Optional[str] = None  # BOZZA | FAC-SIMILE | ANNULLATO | SUPERATO
    snapshot_hash: str  # sha256 of the immutable snapshot payload
    pdf_hash: str  # sha256 of the PDF bytes
    filename: str
    storage_key: Optional[str] = None  # if archived
    size_bytes: int = 0
    mime_type: str = "application/pdf"
    # Immutable snapshot contents (what the PDF was generated FROM)
    snapshot: Dict[str, Any] = Field(default_factory=dict)
    # Metadata
    generated_by: str
    generated_at: datetime
    invalidated_at: Optional[datetime] = None
    invalidated_by: Optional[str] = None
    invalidation_reason: Optional[str] = None


# ---------- Validation gate ----------
class PdfValidationError(BaseModel):
    field: str
    code: str
    message: str


class PdfGenerationResult(BaseModel):
    id: str
    kind: str
    filename: str
    snapshot_hash: str
    pdf_hash: str
    size_bytes: int
    generated_at: datetime
    validation_errors: List[PdfValidationError] = Field(default_factory=list)


class GeneratePdfRequest(BaseModel):
    template_id: Optional[str] = None
    kind: str = "preview"  # preview | definitive
    payment_terms_override: Optional[PaymentTermsSchema] = None
    include_clause_codes: Optional[List[str]] = None  # additional optional clauses
    exclude_clause_codes: Optional[List[str]] = None
    force: bool = False  # ignore validation warnings (still not errors)


class InvalidatePdfRequest(BaseModel):
    reason: str
