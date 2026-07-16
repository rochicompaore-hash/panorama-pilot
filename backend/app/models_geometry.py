"""Geometry & Dimension Rules — modelli per configuratore geometrico libero,
regole dimensionali versionate e importazione listini.

Principio: NESSUN secondo motore di calcolo. Il `GeometryTree` è una sorgente
di verità che viene convertita in input per `resolve_bom_full` (motore BOM
esistente). Le detrazioni dimensionali sono nel `DimensionRuleSet` versionato,
non hardcoded.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from app.models import BaseDoc, new_id


# =====================================================================
# GEOMETRY TREE — albero root → split → cell → module
# =====================================================================
ModuleType = Literal[
    "fixed",              # fisso (vetro)
    "sash_hinged",        # anta battente
    "sash_tilt",          # anta ribalta (vasistas)
    "sash_tilt_turn",     # anta battente-ribalta
    "sash_sliding",       # anta scorrevole
    "panel",              # pannello (non vetro)
    "glass_fixed",        # solo vetro fisso (senza telaio anta)
    "top_light",          # sopraluce
    "bottom_light",       # sottoluce
    "side_light",         # fiancoluce
]

NodeKind = Literal["root", "split", "cell", "module"]
SplitDirection = Literal["horizontal", "vertical"]
SizeUnit = Literal["mm", "pct", "auto"]


class GeometryNode(BaseModel):
    """Nodo generico dell'albero geometria.

    - `kind=root`: contenitore radice con le misure esterne del serramento.
    - `kind=split`: divisione H o V, `children` con dimensioni relative.
    - `kind=cell`: cella singola, contiene un `module`.
    - `kind=module`: modulo terminale (fisso/anta/…).
    """
    id: str = Field(default_factory=new_id)
    kind: NodeKind
    # Per split: direction + children ratios
    direction: Optional[SplitDirection] = None
    # size: dimensione relativa nella dimensione del padre
    size_value: Optional[float] = None
    size_unit: SizeUnit = "auto"
    # Per module
    module_type: Optional[ModuleType] = None
    module_opening_side: Optional[Literal["left", "right", "top", "bottom", "center"]] = None
    module_handle_side: Optional[Literal["left", "right"]] = None
    hardware_kit_id: Optional[str] = None
    glass_type_id: Optional[str] = None
    color_id: Optional[str] = None
    # Traversi/montanti interni (per moduli complessi)
    inner_transoms: int = 0        # traversi interni al modulo
    inner_mullions: int = 0
    label: Optional[str] = None
    notes: Optional[str] = None
    children: List["GeometryNode"] = Field(default_factory=list)


GeometryNode.model_rebuild()


class GeometryTree(BaseModel):
    """Albero geometria completo. Persistito su OpeningProduct.geometry_tree
    o come documento standalone `window_geometries` per librerie."""
    id: str = Field(default_factory=new_id)
    # Misure esterne
    outer_width_mm: int
    outer_height_mm: int
    # Modalità misura
    measurement_mode: Literal["opening_hole", "finished_frame", "frame_outer"] = "frame_outer"
    # Sistema profilo (obbligatorio per detrazioni)
    profile_system_id: str
    # Set regole dimensionali applicato (versionato)
    dimension_rule_set_id: Optional[str] = None
    # Colore predefinito
    color_category_id: Optional[str] = None
    color_id: Optional[str] = None
    # Root node
    root: GeometryNode
    # Metadata
    version: int = 1
    template_code: Optional[str] = None
    notes: Optional[str] = None


# =====================================================================
# DIMENSION RULES — detrazioni versionate per sistema profilo
# =====================================================================
DimensionElement = Literal[
    "frame_top", "frame_bottom", "frame_left", "frame_right",
    "sash_frame",           # profilo anta (perimetro anta)
    "glass_on_sash",        # vetro montato su anta
    "glass_on_fixed",       # vetro su fisso
    "glazing_bead",         # fermavetro
    "seal_frame", "seal_sash", "seal_glass",
    "mullion_vertical", "transom_horizontal",
    "central_meeting_stile",  # scambio battuta
    "sill",                 # soglia
    "reinforcement_frame", "reinforcement_sash",
    "reinforcement_mullion", "reinforcement_transom",
]


class DimensionRule(BaseModel):
    """Singola regola dimensionale (detrazione/maggiorazione) per un elemento.

    Espressione AST-safe. Variabili disponibili nel contesto:
      - L, H (dimensioni contenitore in mm)
      - inner_L, inner_H (luce interna)
      - frame_width, sash_width, central_node, rebate, glass_deduction, weld_allowance
      - clearance_side, clearance_top, clearance_bottom
      - nr_ante, nr_moduli
    """
    id: str = Field(default_factory=new_id)
    element: DimensionElement
    # Formula da applicare (ritorna mm)
    length_formula: Optional[str] = None      # per profili (perimetro/segmento)
    width_formula: Optional[str] = None       # per vetro/pannello
    height_formula: Optional[str] = None      # per vetro/pannello
    # Detrazioni parametrizzate
    delta_start_mm: float = 0.0               # detrazione in testa (mm negativi = accorcia)
    delta_end_mm: float = 0.0
    # Scarto sfrido
    kerf_mm: Optional[float] = None
    weld_allowance_mm: Optional[float] = None
    condition: List[Dict[str, Any]] = Field(default_factory=list)
    notes: Optional[str] = None


class DimensionRuleSet(BaseDoc):
    """Set di regole dimensionali per un sistema profilo.

    Versionato: nuova versione = nuovo documento con `parent_version_id`.
    Nessuna modifica retroattiva a preventivi/contratti già firmati.
    """
    profile_system_id: str
    code: str
    name: str
    description: Optional[str] = None
    rules: List[DimensionRule] = Field(default_factory=list)
    # Versioning
    version: int = 1
    parent_version_id: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    rs_status: Literal["draft", "active", "archived"] = "active"
    is_default: bool = False
    is_demo: bool = False
    active: bool = True


# =====================================================================
# GEOMETRY REQUESTS / RESPONSES
# =====================================================================
class GeometryComputeRequest(BaseModel):
    """Compute richiesto per un albero geometrico + BOM template + listini."""
    geometry: GeometryTree
    bom_template_id: str
    sell_pricelist_id: Optional[str] = None
    cost_pricelist_id: Optional[str] = None
    include_costs: bool = True
    include_svg: bool = True


class GeometryTemplate(BaseDoc):
    """Template di geometria pre-costruito (finestra 1-anta, 2-ante, fisso, ecc.)."""
    code: str
    name: str
    category: Literal["window", "door", "sliding", "custom"] = "window"
    description: Optional[str] = None
    default_tree: GeometryNode
    preview_svg: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    is_demo: bool = False


# =====================================================================
# PRICELIST IMPORT — Wizard XLS/CSV
# =====================================================================
ImportEntityType = Literal[
    "profile", "reinforcement", "glazing_bead", "glass_type", "hardware_kit",
    "accessory", "labor", "price_matrix", "surcharge", "min_billable",
    "component_association",
]

ImportStatus = Literal[
    "uploaded", "parsed", "mapped", "validated", "preview_ready",
    "draft", "publishing", "published", "rolled_back", "failed", "cancelled",
]


class ImportColumnMapping(BaseModel):
    """Mapping da colonna XLS/CSV → campo target."""
    source_column: str
    target_field: str
    transform: Optional[Literal["lower", "upper", "trim", "num", "int", "float"]] = None
    default_if_empty: Optional[str] = None
    required: bool = False


class ImportError(BaseModel):
    row_index: int
    column: Optional[str] = None
    code: str
    message: str
    severity: Literal["error", "warning"] = "error"


class ImportJob(BaseDoc):
    """Job di importazione — traccia completa (idempotente via file_hash)."""
    entity_type: ImportEntityType
    filename: str
    file_hash: str
    file_size_bytes: int
    storage_key: Optional[str] = None       # object storage key
    # Parse
    sheet_names: List[str] = Field(default_factory=list)
    selected_sheet: Optional[str] = None
    total_rows: int = 0
    header_row_index: int = 0
    detected_headers: List[str] = Field(default_factory=list)
    # Mapping
    mappings: List[ImportColumnMapping] = Field(default_factory=list)
    # Target
    target_pricelist_id: Optional[str] = None
    target_pricelist_code: Optional[str] = None
    supplier_id: Optional[str] = None
    profile_system_id: Optional[str] = None
    color_id: Optional[str] = None
    # Preview
    preview_sample: List[Dict[str, Any]] = Field(default_factory=list)   # max 200 rows
    # Validation
    validation_errors: List[ImportError] = Field(default_factory=list)
    duplicate_count: int = 0
    valid_rows: int = 0
    # Stato
    im_status: ImportStatus = "uploaded"
    async_processing: bool = False
    progress_pct: float = 0.0
    # Publish/rollback
    published_at: Optional[datetime] = None
    published_by: Optional[str] = None
    rolled_back_at: Optional[datetime] = None
    rolled_back_by: Optional[str] = None
    rollback_snapshot_key: Optional[str] = None   # storage key del backup pre-publish
    # Notes
    notes: Optional[str] = None


# =====================================================================
# CONTRACT SNAPSHOT (esteso)
# =====================================================================
class ContractSnapshot(BaseModel):
    """Snapshot immutabile del contratto — congelato al momento della firma o
    dell'invio al cliente. Include geometria, BOM, prezzi, hash."""
    generated_at: datetime
    quote_id: str
    quote_number: Optional[str] = None
    quote_revision: int = 0
    quote_totals: Dict[str, Any] = Field(default_factory=dict)
    environments: List[Dict[str, Any]] = Field(default_factory=list)
    openings: List[Dict[str, Any]] = Field(default_factory=list)
    products: List[Dict[str, Any]] = Field(default_factory=list)  # con geometry + bom + svg
    company: Dict[str, Any] = Field(default_factory=dict)
    customer: Dict[str, Any] = Field(default_factory=dict)
    clauses: List[Dict[str, Any]] = Field(default_factory=list)
    payment_terms: Dict[str, Any] = Field(default_factory=dict)
    pricelists_used: List[Dict[str, Any]] = Field(default_factory=list)
    dimension_rule_sets_used: List[Dict[str, Any]] = Field(default_factory=list)
    snapshot_hash: str = ""
