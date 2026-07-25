"""Catalog & production models — added for Opzione A (motore 1-anta + area catalogo).

Design principle: additive-only. We do NOT modify the existing `ProductCatalog`
schema in `models_pricing.py` (used by live product editors), but we add:

* `ProductionConfig` — tenant-wide administrative values (hourly cost,
  standard production time, default margin). Protected: only `pricing_admin.manage`.
* `CatalogCodeMapping` — auto-mapping table (source code → component category)
  used during importer wizard to pre-classify rows.
* Component-association pydantic helpers used by the recipe engine when reading
  the extended `products` doc (new fields stored inline via update payload).
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from app.models import BaseDoc


# =====================================================================
# Component categories — canonical taxonomy for products
# =====================================================================
ComponentCategory = Literal[
    "telaio", "anta_standard", "anta_portoncino", "scambio_battuta",
    "rinforzo_telaio", "rinforzo_anta", "rinforzo_scambio",
    "fermavetro", "traverso", "montante",
    "soglia", "gocciolatoio",
    "vetro", "ferramenta", "accessori",
]
ALL_COMPONENT_CATEGORIES = list(ComponentCategory.__args__)


ProductLifecycle = Literal["draft", "validated", "active", "superseded", "archived"]


class ProductComponentAssoc(BaseModel):
    """Association product ↔ component (subdocument of products)."""
    category: str  # ComponentCategory
    code: str
    required: bool = True
    color_dependent: bool = False
    price_depends_on_color: bool = False
    formula_qty: Optional[str] = None
    formula_cut: Optional[str] = None
    applies_to: List[str] = Field(default_factory=list)  # ["finestra_1a", "finestra_2a", ...]
    priority: int = 100
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    notes: Optional[str] = None


# =====================================================================
# Production config — protected tenant-wide settings
# =====================================================================
class ProductionConfig(BaseDoc):
    """Tenant-wide production configuration for cost & margin computation."""
    hourly_cost: Optional[float] = None                  # €/h — MISSING_HOURLY_COST if None
    production_time_default_minutes: Optional[float] = None  # minutes — MISSING_PRODUCTION_TIME
    default_margin_pct: Optional[float] = None           # % — MISSING_MARGIN
    default_glass_price_per_sqm: float = 76.0            # €/m² default doppio-vetro base
    default_glass_min_sqm: float = 0.50                  # m² minimo fatturabile per unità
    premium_pvc_surcharge_pct: float = 6.0               # +6% su PVC per colori Premium
    default_bar_length_pvc_mm: int = 6500                # 6.5 m barre PVC
    default_bar_length_reinforcement_mm: int = 6000      # 6 m barre acciaio


class ProductionConfigUpdate(BaseModel):
    hourly_cost: Optional[float] = None
    production_time_default_minutes: Optional[float] = None
    default_margin_pct: Optional[float] = None
    default_glass_price_per_sqm: Optional[float] = None
    default_glass_min_sqm: Optional[float] = None
    premium_pvc_surcharge_pct: Optional[float] = None
    default_bar_length_pvc_mm: Optional[int] = None
    default_bar_length_reinforcement_mm: Optional[int] = None


# =====================================================================
# Code auto-mapping — used by importer to pre-classify unknown codes
# =====================================================================
class CatalogCodeMapping(BaseDoc):
    """Maps a raw code (from supplier pricelist) → canonical component category."""
    code: str
    component_category: str  # ComponentCategory
    material: Literal["PVC", "acciaio", "vetro", "ferramenta", "altro"] = "PVC"
    description: Optional[str] = None
    is_system: bool = False  # true for factory-seeded mappings


class CatalogCodeMappingCreate(BaseModel):
    code: str
    component_category: str
    material: str = "PVC"
    description: Optional[str] = None


class CatalogCodeMappingUpdate(BaseModel):
    component_category: Optional[str] = None
    material: Optional[str] = None
    description: Optional[str] = None


# =====================================================================
# Product simulation — API contract
# =====================================================================
class ProductSimulateRequest(BaseModel):
    product_id: Optional[str] = None    # if provided, load components from product
    product_key: Optional[str] = None   # or resolve by key
    width_mm: int                       # L (mm)
    height_mm: int                      # H (mm)
    weld_allowance_mm: int = 6          # S (mm)
    color_code: str                     # required — never blank
    is_color_premium: bool = False      # applies +6% PVC-only
    glass_price_per_sqm: Optional[float] = None   # override; else from ProductionConfig
    glass_min_sqm: Optional[float] = None
    hardware_kit_price: Optional[float] = None    # €, per kit
    other_components_cost: Optional[float] = None # € — MUST be explicitly provided (not silently 0)
    other_components_declared_zero: bool = False  # explicit "no altri componenti"
    quote_line_type: Literal["finestra_1a"] = "finestra_1a"
    discount_amount: float = 0.0
    override_margin_pct: Optional[float] = None
    override_hourly_cost: Optional[float] = None
    override_production_time_min: Optional[float] = None

    # --- commercial_perimeter (NEW default) ---
    pricing_mode: Optional[str] = None  # "commercial_perimeter" (default) | "technical_cut_list"
    window_type: Literal["apribile", "fissa"] = "apribile"
    number_of_sashes: int = 1
    hardware_not_required: bool = False   # solo per fissa
    glass_code: Optional[str] = None      # riferimento vetro selezionato
    # Servizi (opzionale, mai autofill 0)
    installation_cost: Optional[float] = None
    installation_declared_zero: bool = False
    transport_cost: float = 0.0
    disposal_cost: float = 0.0
    accessory_cost: float = 0.0


class ProductSimulateBlockingError(BaseModel):
    code: str
    message: str
    context: Dict[str, Any] = Field(default_factory=dict)
