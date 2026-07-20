"""Parametric Quoting Engine — Data Models (Milestone M6.PAR).

Copre:
- ProfileSystem (sistema profilo) — dimensioni tecniche versionabili
- Profile (profilo singolo) — telaio/anta/montante/traverso/fermavetro/…
- ColorCategory (categoria colore) — logica scarto/sovrapprezzo
- Color (colore specifico) — RAL/finitura/anima
- GlassType (vetro)
- HardwareKit (ferramenta)
- Accessory (cassonetto/zanzariera/davanzale/…)
- ItemPricelist / ItemPricelistEntry — listini versionati vendita/costo
- PriceMatrix (matrice L×H) — modalità A
- BomTemplate + BomComponent — distinta base parametrica versionata
- PricingModeConfig — configurazione modalità A/B/C con priorità
- ColorScrapPolicy — policy dettagliata riuso residui Cat.3
- CuttingList / CuttingListBar / Cut — piano di taglio esecutivo
- BarOptimizationRun — audit algoritmo (FFD/BFD)
- ScrapStock — barre residue riutilizzabili (per policy)
- ParametricSnapshot — snapshot canonico input+output per rigenerazione

Convenzioni:
- Tutte le entità sono `tenant_id`-scoped tramite BaseDoc.
- Nessun eval(): tutte le formule usano il parser AST sicuro.
- Prezzi/Costi autoritativi vengono dai listini versionati.
- I template BOM sono versionati; ordini emessi ne conservano snapshot immutabile.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Any, Dict, Literal
from pydantic import BaseModel, Field
from app.models import BaseDoc, new_id


# =====================================================================
# 1. PROFILE SYSTEM — sistema profilo (PVC 70mm, Alluminio taglio termico, …)
# =====================================================================
class ProfileSystemTech(BaseModel):
    """Parametri tecnici versionabili del sistema. Usati come default nelle formule BOM
    (non hardcoded nelle formule stringa)."""
    frame_width_mm: float = 70.0            # larghezza telaio
    sash_width_mm: float = 78.0             # larghezza anta
    central_node_mm: float = 108.0          # nodo centrale (2 ante che si incontrano)
    rebate_mm: float = 20.0                 # battuta
    glass_clearance_mm: float = 4.0         # gioco vetro
    glass_deduction_mm: float = 60.0        # detrazione vetro rispetto al foro
    weld_allowance_mm: float = 0.0          # maggiorazione saldatura
    kerf_mm: float = 3.0                    # larghezza lama (default per il sistema)
    bar_length_mm: int = 6500               # lunghezza barra standard
    bar_head_offcut_mm: float = 50.0        # testa non usabile
    bar_tail_offcut_mm: float = 50.0        # coda non usabile
    min_reusable_scrap_mm: float = 400.0    # sfrido minimo riutilizzabile
    max_sash_weight_kg: float = 80.0        # limite peso anta
    max_width_mm: int = 2400
    max_height_mm: int = 2800
    tolerances: Dict[str, float] = Field(default_factory=dict)  # es. {"length_cut": 0.5}
    glass_compat: List[str] = Field(default_factory=list)       # id GlassType compatibili
    hardware_compat: List[str] = Field(default_factory=list)    # id HardwareKit compatibili


class ProfileSystem(BaseDoc):
    code: str
    name: str
    material: Literal["pvc", "alu", "wood", "alu_wood", "alu_pvc"] = "pvc"
    series: Optional[str] = None
    description: Optional[str] = None
    tech: ProfileSystemTech = Field(default_factory=ProfileSystemTech)
    # Versionamento
    version: int = 1
    parent_version_id: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    ps_status: Literal["draft", "active", "archived"] = "active"
    is_demo: bool = False
    active: bool = True


class ProfileSystemCreate(BaseModel):
    code: str
    name: str
    material: str = "pvc"
    series: Optional[str] = None
    description: Optional[str] = None
    tech: Optional[ProfileSystemTech] = None


class ProfileSystemUpdate(BaseModel):
    name: Optional[str] = None
    material: Optional[str] = None
    series: Optional[str] = None
    description: Optional[str] = None
    tech: Optional[ProfileSystemTech] = None
    ps_status: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    active: Optional[bool] = None


# =====================================================================
# 2. PROFILE — profilo singolo (telaio/anta/montante/…)
# =====================================================================
ProfileRole = Literal[
    "frame", "sash", "mullion", "transom",
    "glazing_bead", "coupling", "extension",
    "reinforcement_frame", "reinforcement_sash",
    "threshold", "sill_int", "sill_ext",
]


class Profile(BaseDoc):
    system_id: str
    code: str
    name: str
    role: ProfileRole
    bar_length_mm: Optional[int] = None   # override sul sistema
    weight_per_m_kg: float = 0.0
    section_desc: Optional[str] = None
    color_category_default_id: Optional[str] = None
    # Prezzo indicativo (autoritativo → ItemPricelistEntry). Solo comodità UI.
    indicative_price_per_m: float = 0.0
    indicative_cost_per_m: float = 0.0
    supplier_id: Optional[str] = None
    supplier_code: Optional[str] = None
    is_cutting_relevant: bool = True
    is_demo: bool = False
    active: bool = True


class ProfileCreate(BaseModel):
    system_id: str
    code: str
    name: str
    role: str
    bar_length_mm: Optional[int] = None
    weight_per_m_kg: float = 0.0
    color_category_default_id: Optional[str] = None
    indicative_price_per_m: float = 0.0
    indicative_cost_per_m: float = 0.0
    supplier_id: Optional[str] = None
    supplier_code: Optional[str] = None


class ProfileUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    bar_length_mm: Optional[int] = None
    weight_per_m_kg: Optional[float] = None
    color_category_default_id: Optional[str] = None
    indicative_price_per_m: Optional[float] = None
    indicative_cost_per_m: Optional[float] = None
    supplier_id: Optional[str] = None
    supplier_code: Optional[str] = None
    active: Optional[bool] = None


# =====================================================================
# 3. COLOR CATEGORY & COLOR
# =====================================================================
ScrapMode = Literal["global_reuse", "order_reuse", "order_full_cost"]
ScrapReusePolicy = Literal[
    "same_color_same_profile_only",
    "same_color_any_compatible_profile",
    "generic_stock",
    "non_reusable",
    "manual_approval",
]


class ColorCategory(BaseDoc):
    code: str                             # CAT1|CAT2|CAT3 (o custom)
    name: str
    scrap_mode: ScrapMode = "global_reuse"
    surcharge_pct: float = 0.0
    surcharge_fixed: float = 0.0
    lead_time_days: int = 0
    # Policy riuso residuo per questa categoria (default in base a scrap_mode)
    scrap_reuse_policy: ScrapReusePolicy = "same_color_any_compatible_profile"
    # Se true: cliente paga barra intera (Cat.3 classica)
    charges_whole_bar: bool = False
    requires_approval: bool = False
    notes: Optional[str] = None
    is_demo: bool = False
    active: bool = True
    # Opzione A — colore Premium: attiva +6% PVC-only nel motore parametrico
    is_premium: bool = False


class ColorCategoryCreate(BaseModel):
    code: str
    name: str
    scrap_mode: str = "global_reuse"
    surcharge_pct: float = 0.0
    surcharge_fixed: float = 0.0
    lead_time_days: int = 0
    scrap_reuse_policy: str = "same_color_any_compatible_profile"
    charges_whole_bar: bool = False
    requires_approval: bool = False
    notes: Optional[str] = None


class ColorCategoryUpdate(BaseModel):
    name: Optional[str] = None
    scrap_mode: Optional[str] = None
    surcharge_pct: Optional[float] = None
    surcharge_fixed: Optional[float] = None
    lead_time_days: Optional[int] = None
    scrap_reuse_policy: Optional[str] = None
    charges_whole_bar: Optional[bool] = None
    requires_approval: Optional[bool] = None
    notes: Optional[str] = None
    active: Optional[bool] = None
    is_premium: Optional[bool] = None


class Color(BaseDoc):
    code: str
    name: str
    category_id: str
    external_finish: Optional[str] = None      # es. "liscio", "goffrato", "spazzolato"
    internal_finish: Optional[str] = None
    external_color: Optional[str] = None       # RAL/nome
    internal_color: Optional[str] = None
    core_color: Optional[str] = None           # anima
    ral_code: Optional[str] = None
    is_demo: bool = False
    active: bool = True


class ColorCreate(BaseModel):
    code: str
    name: str
    category_id: str
    external_finish: Optional[str] = None
    internal_finish: Optional[str] = None
    external_color: Optional[str] = None
    internal_color: Optional[str] = None
    core_color: Optional[str] = None
    ral_code: Optional[str] = None


class ColorUpdate(BaseModel):
    name: Optional[str] = None
    category_id: Optional[str] = None
    external_finish: Optional[str] = None
    internal_finish: Optional[str] = None
    external_color: Optional[str] = None
    internal_color: Optional[str] = None
    core_color: Optional[str] = None
    ral_code: Optional[str] = None
    active: Optional[bool] = None


# =====================================================================
# 4. GLASS TYPE / HARDWARE KIT / ACCESSORY
# =====================================================================
class GlassType(BaseDoc):
    code: str
    name: str
    composition: Optional[str] = None     # es. "4-16-4 argon"
    thickness_mm: float = 24.0
    u_value: Optional[float] = None
    weight_per_sqm_kg: float = 25.0
    indicative_sqm_price: float = 0.0
    indicative_sqm_cost: float = 0.0
    is_demo: bool = False
    active: bool = True


class GlassTypeCreate(BaseModel):
    code: str
    name: str
    composition: Optional[str] = None
    thickness_mm: float = 24.0
    u_value: Optional[float] = None
    weight_per_sqm_kg: float = 25.0
    indicative_sqm_price: float = 0.0
    indicative_sqm_cost: float = 0.0


class GlassTypeUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    composition: Optional[str] = None
    thickness_mm: Optional[float] = None
    u_value: Optional[float] = None
    weight_per_sqm_kg: Optional[float] = None
    indicative_sqm_price: Optional[float] = None
    indicative_sqm_cost: Optional[float] = None
    active: Optional[bool] = None


HardwareKitType = Literal[
    "fixed", "single_sash", "double_sash",
    "tilt_turn", "tilt_only", "sliding", "lift_slide",
]


class HardwareKit(BaseDoc):
    code: str
    name: str
    kit_type: HardwareKitType = "tilt_turn"
    supplier: Optional[str] = None
    weight_kg: float = 0.0
    indicative_price: float = 0.0
    indicative_cost: float = 0.0
    is_demo: bool = False
    active: bool = True


class HardwareKitCreate(BaseModel):
    code: str
    name: str
    kit_type: str = "tilt_turn"
    supplier: Optional[str] = None
    weight_kg: float = 0.0
    indicative_price: float = 0.0
    indicative_cost: float = 0.0


class HardwareKitUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    kit_type: Optional[str] = None
    supplier: Optional[str] = None
    weight_kg: Optional[float] = None
    indicative_price: Optional[float] = None
    indicative_cost: Optional[float] = None
    active: Optional[bool] = None


AccessoryUnitType = Literal["piece", "linear_m", "sqm", "kg"]


class Accessory(BaseDoc):
    code: str
    name: str
    kind: str = "generic"      # box, screen, sill, seal, threshold, screw, consumable, …
    unit_type: AccessoryUnitType = "piece"
    indicative_price: float = 0.0
    indicative_cost: float = 0.0
    is_demo: bool = False
    active: bool = True


class AccessoryCreate(BaseModel):
    code: str
    name: str
    kind: str = "generic"
    unit_type: str = "piece"
    indicative_price: float = 0.0
    indicative_cost: float = 0.0


class AccessoryUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    kind: Optional[str] = None
    unit_type: Optional[str] = None
    indicative_price: Optional[float] = None
    indicative_cost: Optional[float] = None
    active: Optional[bool] = None


# =====================================================================
# 5. ITEM PRICELIST — listini versionati vendita/costo
# =====================================================================
ItemPricelistKind = Literal["sell", "cost"]
ItemRefType = Literal["profile", "glass", "hardware", "accessory", "labor"]


class ItemPricelistEntry(BaseModel):
    """Riga listino applicabile. Un'anagrafica può avere più righe attive
    (per scaglioni, colore, fornitore, …)."""
    ref_type: ItemRefType
    ref_id: str
    color_id: Optional[str] = None          # se il prezzo dipende dal colore
    supplier_id: Optional[str] = None
    unit: str = "piece"                     # piece|linear_m|sqm|kg|hour
    unit_price: float = 0.0
    currency: str = "EUR"
    min_qty: float = 0.0
    tier_break_qty: Optional[float] = None   # scaglione successivo
    tier_price: Optional[float] = None
    profile_system_id: Optional[str] = None  # se prezzo per sistema
    notes: Optional[str] = None


class ItemPricelist(BaseDoc):
    code: str
    name: str
    kind: ItemPricelistKind = "sell"
    currency: str = "EUR"
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    ipl_status: Literal["draft", "active", "archived"] = "active"
    priority: int = 100
    parent_version_id: Optional[str] = None
    version: int = 1
    entries: List[ItemPricelistEntry] = Field(default_factory=list)
    is_demo: bool = False


class ItemPricelistCreate(BaseModel):
    code: str
    name: str
    kind: str = "sell"
    currency: str = "EUR"
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    priority: int = 100
    entries: List[ItemPricelistEntry] = Field(default_factory=list)


class ItemPricelistUpdate(BaseModel):
    name: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    ipl_status: Optional[str] = None
    priority: Optional[int] = None
    entries: Optional[List[ItemPricelistEntry]] = None


# =====================================================================
# 6. PRICE MATRIX — Modalità A (matrice L×H)
# =====================================================================
InterpolationMode = Literal["nearest_up", "nearest", "linear"]


class PriceMatrixCell(BaseModel):
    """Cella matrice. Convenzione: (width_mm, height_mm) → price."""
    width_mm: int
    height_mm: int
    price: float


class PriceMatrix(BaseDoc):
    code: str
    name: str
    product_key: str                          # es. "window_1_leaf"
    profile_system_id: Optional[str] = None
    color_category_id: Optional[str] = None
    glass_type_id: Optional[str] = None
    hardware_kit_id: Optional[str] = None
    widths_mm: List[int] = Field(default_factory=list)   # asse L
    heights_mm: List[int] = Field(default_factory=list)  # asse H
    cells: List[PriceMatrixCell] = Field(default_factory=list)  # sparse ok
    interpolation: InterpolationMode = "nearest_up"
    allow_extrapolation: bool = False
    oversize_surcharge_pct: float = 0.0
    min_width_mm: Optional[int] = None
    max_width_mm: Optional[int] = None
    min_height_mm: Optional[int] = None
    max_height_mm: Optional[int] = None
    unit: str = "piece"
    currency: str = "EUR"
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    pm_status: Literal["draft", "active", "archived"] = "active"
    version: int = 1
    parent_version_id: Optional[str] = None
    is_demo: bool = False


class PriceMatrixCreate(BaseModel):
    code: str
    name: str
    product_key: str
    profile_system_id: Optional[str] = None
    color_category_id: Optional[str] = None
    glass_type_id: Optional[str] = None
    hardware_kit_id: Optional[str] = None
    widths_mm: List[int] = Field(default_factory=list)
    heights_mm: List[int] = Field(default_factory=list)
    cells: List[PriceMatrixCell] = Field(default_factory=list)
    interpolation: str = "nearest_up"
    allow_extrapolation: bool = False
    oversize_surcharge_pct: float = 0.0


class PriceMatrixUpdate(BaseModel):
    name: Optional[str] = None
    profile_system_id: Optional[str] = None
    color_category_id: Optional[str] = None
    glass_type_id: Optional[str] = None
    hardware_kit_id: Optional[str] = None
    widths_mm: Optional[List[int]] = None
    heights_mm: Optional[List[int]] = None
    cells: Optional[List[PriceMatrixCell]] = None
    interpolation: Optional[str] = None
    allow_extrapolation: Optional[bool] = None
    oversize_surcharge_pct: Optional[float] = None
    pm_status: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None


# =====================================================================
# 7. BOM TEMPLATE — distinta parametrica versionata
# =====================================================================
ComponentType = Literal[
    "profile", "glass", "hardware", "accessory",
    "seal", "screw", "consumable", "packaging",
    "outsourced_process", "machine_time", "labor",
]
ApplicationScope = Literal["per_piece", "per_line", "per_opening", "per_quote"]
RoundingRule = Literal["none", "up", "down", "nearest", "nearest_5", "nearest_10"]


class BomComponent(BaseModel):
    """Riga distinta parametrica. Numeric formulas ⇒ parser AST sicuro.
    Condizione di applicabilità ⇒ motore condizioni (non stringa arbitraria)."""
    id: str = Field(default_factory=new_id)
    sequence: int = 0
    component_type: ComponentType
    ref_id: Optional[str] = None                          # id Profile/Glass/Hardware/Accessory
    role: Optional[str] = None                            # frame_top|frame_bottom|sash_left|glass_a|…
    quantity_formula: str = "1"
    length_formula: Optional[str] = None                  # per profile — mm
    width_formula: Optional[str] = None                   # per glass — mm
    height_formula: Optional[str] = None                  # per glass — mm
    area_formula: Optional[str] = None                    # per glass alt.
    weight_formula: Optional[str] = None
    condition: List[Dict[str, Any]] = Field(default_factory=list)  # condition engine
    unit_of_measure: str = "piece"
    waste_pct: float = 0.0                                # scarto tecnico %
    scrap_fixed_mm_per_cut: float = 0.0                   # sfrido fisso mm per taglio (profili)
    scrap_fixed_per_piece: float = 0.0                    # sfrido fisso per pezzo (qualsiasi UM)
    rounding_rule: RoundingRule = "none"
    minimum_quantity: float = 0.0                         # min quantità (tecnica)
    minimum_billable_qty: float = 0.0                     # min FATTURABILE (commerciale)
    consumption_mode: Literal["proportional", "full_bar"] = "proportional"
    bar_rounding: bool = False                            # arrotondamento alla barra intera (default OFF)
    application_scope: ApplicationScope = "per_piece"
    is_optional: bool = False
    is_customer_visible: bool = True
    is_cost_relevant: bool = True
    is_cutting_relevant: bool = True
    notes: Optional[str] = None
    description_override: Optional[str] = None            # descrizione ad-hoc
    # Origine ricetta (per UI visuale — non usato in eval)
    recipe_code: Optional[str] = None
    recipe_params: Dict[str, Any] = Field(default_factory=dict)
    # Override colore (raro): forza uno specifico ColorCategory su questo componente
    color_category_id_override: Optional[str] = None


class BomTemplate(BaseDoc):
    code: str
    name: str
    product_key: str                          # window_1_leaf | window_2_leaves | door_1_leaf | fixed | tilt_turn | …
    profile_system_id: str
    hardware_kit_default_id: Optional[str] = None
    glass_type_default_id: Optional[str] = None
    color_category_default_id: Optional[str] = None
    # Livello commerciale vs produttivo
    level: Literal["commercial", "production"] = "commercial"
    components: List[BomComponent] = Field(default_factory=list)
    # Versioning
    version: int = 1
    parent_version_id: Optional[str] = None
    bom_status: Literal["draft", "active", "scheduled", "archived"] = "active"
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    formula_schema_version: int = 1
    compatibility_rules: List[Dict[str, Any]] = Field(default_factory=list)
    technical_notes: Optional[str] = None
    is_demo: bool = False


class BomTemplateCreate(BaseModel):
    code: str
    name: str
    product_key: str
    profile_system_id: str
    hardware_kit_default_id: Optional[str] = None
    glass_type_default_id: Optional[str] = None
    color_category_default_id: Optional[str] = None
    level: str = "commercial"
    components: List[BomComponent] = Field(default_factory=list)
    technical_notes: Optional[str] = None


class BomTemplateUpdate(BaseModel):
    name: Optional[str] = None
    product_key: Optional[str] = None
    profile_system_id: Optional[str] = None
    hardware_kit_default_id: Optional[str] = None
    glass_type_default_id: Optional[str] = None
    color_category_default_id: Optional[str] = None
    level: Optional[str] = None
    components: Optional[List[BomComponent]] = None
    bom_status: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    technical_notes: Optional[str] = None


# =====================================================================
# 8. PRICING MODE CONFIG — priorità: riga → prodotto → tenant
# =====================================================================
PricingModeCode = Literal["A_table", "B_bom", "C_hybrid"]


class PricingModeConfig(BaseDoc):
    """Definizione preferenze modalità pricing. Scope determina l'ambito."""
    scope: Literal["tenant", "profile_system", "product", "quote_line"]
    scope_ref_id: Optional[str] = None        # profile_system_id | product_key | quote_line_id
    product_key: Optional[str] = None
    mode: PricingModeCode = "C_hybrid"
    # Modalità A → matrice
    price_matrix_id: Optional[str] = None
    # Modalità B/C → bom
    bom_template_id: Optional[str] = None
    # Modalità B/C → listini
    sell_pricelist_id: Optional[str] = None
    cost_pricelist_id: Optional[str] = None
    # Formula prezzo B (configurabile; NO formula rigida hardcoded)
    b_price_formula: Optional[str] = None
    b_markup_pct: float = 30.0
    b_indirect_pct: float = 8.0
    # Metadati
    notes: Optional[str] = None
    active: bool = True
    is_demo: bool = False


class PricingModeConfigCreate(BaseModel):
    scope: str
    scope_ref_id: Optional[str] = None
    product_key: Optional[str] = None
    mode: str = "C_hybrid"
    price_matrix_id: Optional[str] = None
    bom_template_id: Optional[str] = None
    sell_pricelist_id: Optional[str] = None
    cost_pricelist_id: Optional[str] = None
    b_price_formula: Optional[str] = None
    b_markup_pct: float = 30.0
    b_indirect_pct: float = 8.0
    notes: Optional[str] = None


class PricingModeConfigUpdate(BaseModel):
    mode: Optional[str] = None
    price_matrix_id: Optional[str] = None
    bom_template_id: Optional[str] = None
    sell_pricelist_id: Optional[str] = None
    cost_pricelist_id: Optional[str] = None
    b_price_formula: Optional[str] = None
    b_markup_pct: Optional[float] = None
    b_indirect_pct: Optional[float] = None
    active: Optional[bool] = None
    notes: Optional[str] = None


class PricingModeOverrideRequest(BaseModel):
    quote_line_id: str
    new_mode: PricingModeCode
    reason: str
    price_matrix_id: Optional[str] = None
    bom_template_id: Optional[str] = None


# =====================================================================
# 9. SCRAP STOCK — barre residue riutilizzabili
# =====================================================================
ScrapStatus = Literal["available", "reserved", "consumed", "scrapped"]


class ScrapStock(BaseDoc):
    profile_id: str
    system_id: str
    color_id: Optional[str] = None
    color_category_id: Optional[str] = None
    length_mm: float
    lot: Optional[str] = None
    source_order_id: Optional[str] = None
    source_bar_id: Optional[str] = None
    original_cost: float = 0.0            # costo industriale della barra sorgente
    charged_cost: float = 0.0             # costo già addebitato al cliente originale
    residual_book_value: float = 0.0      # valore residuo per magazzino
    scrap_status: ScrapStatus = "available"
    location: Optional[str] = None
    last_used_at: Optional[datetime] = None
    is_demo: bool = False


# =====================================================================
# 10. CUTTING LIST — piano di taglio esecutivo
# =====================================================================
class Cut(BaseModel):
    id: str = Field(default_factory=new_id)
    length_mm: float
    profile_id: str
    role: Optional[str] = None
    angle_a: float = 45.0        # taglio a un'estremità
    angle_b: float = 45.0        # taglio all'altra estremità
    orientation: Literal["straight", "mitre", "square"] = "mitre"
    from_quote_id: Optional[str] = None
    from_line_id: Optional[str] = None
    from_order_id: Optional[str] = None
    from_opening_id: Optional[str] = None
    bom_component_id: Optional[str] = None
    sequence: int = 0
    label: Optional[str] = None
    tolerance_mm: float = 0.5
    cut_status: Literal["planned", "cut", "consumed"] = "planned"


class CuttingListBar(BaseModel):
    id: str = Field(default_factory=new_id)
    profile_id: str
    color_id: Optional[str] = None
    color_category_id: Optional[str] = None
    bar_length_mm: int
    kerf_mm: float = 3.0
    head_offcut_mm: float = 50.0
    tail_offcut_mm: float = 50.0
    cuts: List[Cut] = Field(default_factory=list)
    used_mm: float = 0.0
    waste_mm: float = 0.0
    reusable_scrap_mm: float = 0.0
    efficiency_pct: float = 0.0
    cost_bar: float = 0.0           # costo industriale della barra
    cost_charged: float = 0.0       # costo che verrà addebitato (Cat.3=intera, altri=proporzionale)
    scrap_stock_id: Optional[str] = None  # residuo generato (se >= min_reusable_scrap_mm)


CuttingScope = Literal["single_order", "multi_order_batch", "quote_preliminary"]


class CuttingList(BaseDoc):
    code: str
    scope: CuttingScope = "single_order"
    source_production_order_ids: List[str] = Field(default_factory=list)
    source_sales_order_ids: List[str] = Field(default_factory=list)
    source_quote_ids: List[str] = Field(default_factory=list)  # tracciabilità
    is_executive: bool = False   # false = preliminare/preventivo
    bars: List[CuttingListBar] = Field(default_factory=list)
    algorithm: Literal["ffd", "bfd", "auto_best"] = "auto_best"
    total_bars: int = 0
    total_cuts: int = 0
    total_waste_mm: float = 0.0
    total_reusable_scrap_mm: float = 0.0
    efficiency_pct: float = 0.0
    total_cost: float = 0.0
    total_cost_charged: float = 0.0
    warnings: List[str] = Field(default_factory=list)
    cl_status: Literal["draft", "confirmed", "in_progress", "completed", "cancelled"] = "draft"


class CuttingListCreate(BaseModel):
    scope: str = "single_order"
    source_production_order_ids: List[str] = Field(default_factory=list)
    source_sales_order_ids: List[str] = Field(default_factory=list)
    algorithm: str = "auto_best"
    is_executive: bool = False


# =====================================================================
# 11. BAR OPTIMIZATION RUN — audit algoritmo
# =====================================================================
class BarOptimizationRun(BaseDoc):
    algorithm: Literal["ffd", "bfd", "auto_best"]
    input_hash: Optional[str] = None
    output_hash: Optional[str] = None
    input_data: Dict[str, Any] = Field(default_factory=dict)
    output_summary: Dict[str, Any] = Field(default_factory=dict)
    runtime_ms: int = 0
    warnings: List[str] = Field(default_factory=list)
    cutting_list_id: Optional[str] = None
    engine_version: str = "1.0.0"


# =====================================================================
# 12. PARAMETRIC SNAPSHOT — canonicalizzazione input/output
# =====================================================================
class ParametricSnapshot(BaseDoc):
    quote_id: Optional[str] = None
    quote_line_id: Optional[str] = None
    order_id: Optional[str] = None
    input_canonical: Dict[str, Any] = Field(default_factory=dict)
    input_hash: Optional[str] = None
    output: Dict[str, Any] = Field(default_factory=dict)
    output_hash: Optional[str] = None
    engine_version: str = "1.0.0"
    formula_schema_version: int = 1
    bom_template_id: Optional[str] = None
    bom_version: int = 1
    price_matrix_id: Optional[str] = None
    price_matrix_version: Optional[int] = None
    pricing_mode: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    runtime_ms: int = 0


# =====================================================================
# 13. PARAMETRIC PREVIEW REQUEST
# =====================================================================
class ParametricPreviewRequest(BaseModel):
    """Richiesta di preview parametrica. Se `quote_line_id` è fornito, la modalità viene
    risolta con priorità: line override → product → profile_system → tenant."""
    product_key: str
    width_mm: int
    height_mm: int
    quantity: float = 1.0
    profile_system_id: Optional[str] = None
    bom_template_id: Optional[str] = None
    price_matrix_id: Optional[str] = None
    color_category_id: Optional[str] = None
    color_id: Optional[str] = None
    glass_type_id: Optional[str] = None
    hardware_kit_id: Optional[str] = None
    nr_ante: int = 1
    nr_traversi: int = 0
    nr_montanti: int = 0
    nr_fissi: int = 0
    extra_params: Dict[str, Any] = Field(default_factory=dict)
    accessories: List[Dict[str, Any]] = Field(default_factory=list)  # [{ref_id, qty}]
    discount_pct: float = 0.0
    discount_amount: float = 0.0
    vat_rate: float = 0.22
    mode_override: Optional[PricingModeCode] = None  # richiede permesso lato server
    override_reason: Optional[str] = None
    include_svg: bool = True
    include_cutting_preview: bool = False


class ParametricPreviewResponse(BaseModel):
    engine_version: str = "1.0.0"
    mode_used: PricingModeCode
    mode_source: str                              # tenant|profile_system|product|quote_line
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    # dimensioni
    width_mm: int
    height_mm: int
    sqm: float
    perimeter_m: float
    # pricing
    unit_price: float = 0.0
    subtotal: float = 0.0
    vat_amount: float = 0.0
    total: float = 0.0
    unit_cost: float = 0.0
    total_cost: float = 0.0
    margin_abs: float = 0.0
    margin_pct: float = 0.0
    # dettagli
    bom_resolved: List[Dict[str, Any]] = Field(default_factory=list)
    cutting_preview: Optional[Dict[str, Any]] = None
    price_breakdown: List[Dict[str, Any]] = Field(default_factory=list)
    svg: Optional[str] = None
    input_hash: Optional[str] = None
    output_hash: Optional[str] = None


# =====================================================================
# 14. NESTING REQUEST
# =====================================================================
class NestingCut(BaseModel):
    profile_id: str
    color_id: Optional[str] = None
    color_category_id: Optional[str] = None
    length_mm: float
    quantity: int = 1
    bom_component_id: Optional[str] = None
    from_order_id: Optional[str] = None
    from_line_id: Optional[str] = None
    from_opening_id: Optional[str] = None
    role: Optional[str] = None
    label: Optional[str] = None


class NestingRequest(BaseModel):
    cuts: List[NestingCut]
    algorithm: Literal["ffd", "bfd", "auto_best"] = "auto_best"
    respect_order_isolation: bool = False  # true → non aggregare tra ordini diversi
    scope: CuttingScope = "single_order"
    source_production_order_ids: List[str] = Field(default_factory=list)
    source_sales_order_ids: List[str] = Field(default_factory=list)


class SvgDrawingRequest(BaseModel):
    product_key: str
    width_mm: int
    height_mm: int
    nr_ante: int = 1
    nr_traversi: int = 0
    nr_montanti: int = 0
    color_category_id: Optional[str] = None
    show_dimensions: bool = True
    show_opening_arrows: bool = True
    scale: float = 1.0
