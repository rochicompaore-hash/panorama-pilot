"""Product types + composition + site conditions + installation pricing.

Estensione preventivatore: catalogo tipologie configurabili, composizione
serramento (ante, sopraluce, sottoluce, fiancoluce), listini montaggio,
questionario cantiere (piano, ascensore, piattaforma, autorizzazioni).
"""
from __future__ import annotations
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from app.models import BaseDoc, new_id


# =============================================================
# PRODUCT TYPES (catalogo tipologie configurabili)
# =============================================================
ProductFamily = Literal[
    "window", "french_door", "fixed", "sliding", "lift_slide",
    "translating_sliding", "shutter", "screen", "roller_shutter",
    "roller_box", "entrance_door", "obscurant", "multi_product", "accessory",
]


class ProductType(BaseDoc):
    code: str
    label: str
    family: ProductFamily = "window"
    description: Optional[str] = None
    default_num_modules: int = 1
    supports_sopraluce: bool = False
    supports_sottoluce: bool = False
    supports_fiancoluce: bool = False
    supports_traversi: bool = True
    supports_montanti: bool = True
    supports_fixed_at_side: bool = False       # es. 3 ante con fissa laterale/centrale
    supports_configurations: List[str] = Field(default_factory=list)  # es. ["battente","ribalta","battente_ribalta","scorrevole","fisso"]
    icon: Optional[str] = None
    sort_order: int = 100
    # Regole prezzo/posa collegate (ItemPricelist / InstallationPricingRule)
    default_installation_rule_id: Optional[str] = None
    active: bool = True
    is_demo: bool = False


class ProductTypeCreate(BaseModel):
    code: str
    label: str
    family: str = "window"
    description: Optional[str] = None
    supports_sopraluce: bool = False
    supports_sottoluce: bool = False
    supports_fiancoluce: bool = False
    supports_fixed_at_side: bool = False
    supports_configurations: List[str] = Field(default_factory=list)


class ProductTypeUpdate(BaseModel):
    label: Optional[str] = None
    family: Optional[str] = None
    description: Optional[str] = None
    supports_sopraluce: Optional[bool] = None
    supports_sottoluce: Optional[bool] = None
    supports_fiancoluce: Optional[bool] = None
    supports_fixed_at_side: Optional[bool] = None
    supports_configurations: Optional[List[str]] = None
    active: Optional[bool] = None


# =============================================================
# WINDOW COMPOSITION
# =============================================================
ModuleKind = Literal["fixed", "battente", "ribalta", "battente_ribalta",
                     "scorrevole", "alzante", "traslante", "vasistas",
                     "fisso_laterale", "fisso_centrale"]

HingesSide = Literal["left", "right", "top", "bottom", "none"]


class WindowModule(BaseModel):
    """Modulo del serramento (una singola anta o riquadro fisso)."""
    id: str = Field(default_factory=new_id)
    index: int = 0                    # posizione da sinistra
    kind: ModuleKind = "battente"
    width_ratio: float = 1.0          # peso proporzionale per calcolo largh.
    is_openable: bool = True
    hinges_side: HingesSide = "left"
    is_fixed: bool = False
    label: Optional[str] = None


class WindowComposition(BaseModel):
    """Composizione del serramento — snapshot immutabile a livello riga."""
    product_type_code: str
    total_width_mm: int
    total_height_mm: int
    num_modules: int = 1
    modules: List[WindowModule] = Field(default_factory=list)
    # Elementi accessori
    has_sopraluce: bool = False
    sopraluce_height_mm: int = 0
    sopraluce_openable: bool = False
    has_sottoluce: bool = False
    sottoluce_height_mm: int = 0
    has_fiancoluce_left: bool = False
    fiancoluce_left_width_mm: int = 0
    has_fiancoluce_right: bool = False
    fiancoluce_right_width_mm: int = 0
    num_traversi_horizontal: int = 0
    num_montanti_vertical: int = 0
    # Preview visibility flags
    show_dimensions_on_drawing: bool = True
    show_opening_symbols: bool = True
    show_technical_legend: bool = True


# =============================================================
# INSTALLATION PRICING RULE
# =============================================================
InstallationUnit = Literal["per_piece", "per_sqm", "per_linear_m", "per_kg", "per_hour"]


class InstallationPricingRule(BaseDoc):
    """Regole economiche montaggio/smontaggio per tipologia."""
    code: str
    label: str
    product_type_code: Optional[str] = None   # se None: applicabile a più tipologie
    product_family: Optional[str] = None
    # Montaggio
    install_unit: InstallationUnit = "per_piece"
    install_internal_cost: float = 0.0
    install_customer_price: float = 0.0
    install_standard_time_min: float = 60.0
    install_crew_size: int = 2
    hourly_crew_cost: float = 0.0
    # Smontaggio
    dismount_internal_cost: float = 0.0
    dismount_customer_price: float = 0.0
    # Smaltimento
    disposal_cost: float = 0.0
    disposal_price: float = 0.0
    # Trasporto
    transport_cost: float = 0.0
    transport_price: float = 0.0
    # Movimentazione / opere accessorie
    handling_cost: float = 0.0
    protection_cost: float = 0.0
    masonry_cost: float = 0.0
    restoration_cost: float = 0.0
    sealing_cost: float = 0.0
    finishing_cost: float = 0.0
    minimum_billable: float = 0.0
    vat_rate: float = 22.0
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    version: int = 1
    active: bool = True
    is_demo: bool = False


class InstallationPricingRuleCreate(BaseModel):
    code: str
    label: str
    product_type_code: Optional[str] = None
    product_family: Optional[str] = None
    install_unit: str = "per_piece"
    install_internal_cost: float = 0.0
    install_customer_price: float = 0.0
    dismount_internal_cost: float = 0.0
    dismount_customer_price: float = 0.0
    disposal_cost: float = 0.0
    transport_cost: float = 0.0


# =============================================================
# ACCESS SURCHARGE RULES (piano, ascensore, piattaforma, ecc.)
# =============================================================
AccessRuleTrigger = Literal[
    "floor_no_elevator", "floor_with_elevator", "elevator_inadequate",
    "platform_required", "ztl", "occupation_permit",
    "municipal_authorization", "heavy_moving", "long_transport",
    "multiple_installers", "crane_required",
]

AccessRuleKind = Literal["fixed", "pct", "per_floor", "per_hour",
                          "per_day", "per_piece", "per_kg", "per_km",
                          "actual_cost"]


class AccessSurchargeRule(BaseDoc):
    code: str
    label: str
    trigger: AccessRuleTrigger
    condition: Dict[str, Any] = Field(default_factory=dict)   # es. {"min_floor": 2}
    surcharge_kind: AccessRuleKind = "fixed"
    amount: float = 0.0
    cost_internal: float = 0.0        # costo azienda (non mostrato al cliente)
    active: bool = True
    is_demo: bool = False
    notes: Optional[str] = None


# =============================================================
# PLATFORM AND AUTHORIZATION COSTS
# =============================================================
PlatformStatus = Literal["not_needed", "optional", "required",
                         "site_inspection_needed", "impossible_verify"]


class PlatformCostRule(BaseDoc):
    code: str
    label: str
    rental_cost_day: float = 0.0
    rental_price_day: float = 0.0
    half_day_cost: float = 0.0
    transport_cost: float = 0.0
    operator_cost: float = 0.0
    authorization_cost: float = 0.0
    occupation_cost: float = 0.0
    deposit_required: float = 0.0
    urgency_surcharge_pct: float = 0.0
    max_work_height_m: float = 0.0
    active: bool = True


AuthorizationStatus = Literal["not_needed", "needed_verify",
                              "needed_managed_by_customer",
                              "needed_managed_by_company",
                              "obtained"]


class MunicipalAuthCostRule(BaseDoc):
    code: str
    label: str
    admin_practice_cost: float = 0.0
    municipal_rights_cost: float = 0.0
    public_soil_occupation_cost: float = 0.0
    stamp_duty_cost: float = 0.0
    technician_cost: float = 0.0
    signage_cost: float = 0.0
    barrier_cost: float = 0.0
    traffic_mgmt_cost: float = 0.0
    accessory_cost: float = 0.0
    active: bool = True


# =============================================================
# SITE CONDITIONS QUESTIONNAIRE (per preventivo)
# =============================================================
FloorLevel = Literal["basement", "ground", "raised", "1st", "2nd", "3rd",
                     "higher", "custom", "independent_house"]

AccessComplexity = Literal["simple", "ordinary", "complex", "with_platform",
                            "to_verify", "not_quotable_without_survey"]


class SiteConditions(BaseModel):
    """Questionario accessibilità cantiere — snapshot immutabile a livello quote."""
    floor_level: FloorLevel = "ground"
    floor_number_custom: Optional[int] = None
    has_elevator: bool = False
    elevator_adequate_size: bool = True
    access_from_stairs: bool = False
    stairs_width_cm: Optional[float] = None
    parking_distance_m: Optional[float] = None
    truck_access: bool = True
    ztl_zone: bool = False
    ztl_permit_needed: bool = False
    public_soil_occupation_needed: bool = False
    municipal_authorization: AuthorizationStatus = "not_needed"
    authorization_managed_by: Literal["customer", "company", "tbd"] = "tbd"
    platform_status: PlatformStatus = "not_needed"
    platform_positionable: Optional[bool] = None
    working_height_m: Optional[float] = None
    scaffolding_needed: bool = False
    crane_needed: bool = False
    movement_difficulty: Literal["easy", "medium", "hard"] = "easy"
    glass_dismount_for_transport: bool = False
    has_courtyard: bool = False
    has_balcony: bool = False
    obstacles: Optional[str] = None
    photos: List[str] = Field(default_factory=list)   # attachment ids
    notes: Optional[str] = None
    # Esito calcolato
    access_complexity: AccessComplexity = "simple"
    risk_level: Literal["low", "medium", "high", "critical"] = "low"
    warnings: List[str] = Field(default_factory=list)
    requires_site_inspection: bool = False
    requires_approval: bool = False
    installation_notes: Optional[str] = None
    # Costi calcolati (snapshot)
    surcharges_snapshot: List[Dict[str, Any]] = Field(default_factory=list)
    total_surcharge_customer: float = 0.0
    total_surcharge_internal_cost: float = 0.0


class SiteConditionsEvaluateRequest(BaseModel):
    conditions: SiteConditions
    product_types: List[str] = Field(default_factory=list)
    num_pieces: int = 1
    total_sqm: float = 0.0


class SiteConditionsEvaluateResponse(BaseModel):
    conditions: SiteConditions
    surcharges_applied: List[Dict[str, Any]] = Field(default_factory=list)
    total_customer: float = 0.0
    total_internal_cost: float = 0.0
    margin: float = 0.0
    warnings: List[str] = Field(default_factory=list)
    is_quotable: bool = True


# =============================================================
# TECHNICAL DRAWING REQUEST + STORAGE
# =============================================================
class TechnicalDrawingRequest(BaseModel):
    composition: WindowComposition
    scale: float = 1.0
    show_dimensions: bool = True
    show_opening_symbols: bool = True
    show_legend: bool = True
    color_frame: Optional[str] = None
    color_glass: Optional[str] = None
    include_watermark: bool = True
    watermark_text: Optional[str] = "Rappresentazione illustrativa preventiva"


class TechnicalDrawingSnapshot(BaseDoc):
    """Snapshot di un disegno generato (per audit / rigenerazione)."""
    quote_id: Optional[str] = None
    quote_line_id: Optional[str] = None
    opening_id: Optional[str] = None
    context: Literal["quote_preview", "quote_pdf", "contract", "customer_portal",
                     "technical_schedule", "abaco_definitive"] = "quote_pdf"
    composition: Dict[str, Any] = Field(default_factory=dict)
    svg: str
    svg_hash: str
    renderer_version: str = "2.0.0"
    generated_at: datetime = Field(default_factory=datetime.now)
