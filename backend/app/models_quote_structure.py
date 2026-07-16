"""Quote structure extension: Environment layer + Opening products + compatibility engine.

Backward compatible:
- Adds `QuoteEnvironment` embedded array to Quote.
- Adds `environment_id`, `derived_dimensions_config` to QuoteOpening (via patched dict).
- Adds `role`, `dimension_source`, `dimension_formula_id`, `inherit_from_opening` to QuoteLine.
- Adds ProductCompatibilityRule collection.
- Adds DimensionFormula collection.

Il concetto:
  Quote → Environment (Cucina, Camera matrimoniale) → Opening (Vano 1, Vano 2) →
  multiple Products (finestra + tapparella + cassonetto + zanzariera).
"""
from __future__ import annotations
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from app.models import BaseDoc, new_id


# =========================================================
# ROLES DEL PRODOTTO NEL VANO
# =========================================================
ProductRole = Literal[
    "primary_frame",     # serramento principale (finestra/portafinestra/scorrevole/fisso/…)
    "shading",           # oscurante principale (tapparella/persiana/scuro/tenda/frangisole)
    "insect_screen",     # zanzariera
    "box",               # cassonetto
    "counter_frame",     # controtelaio
    "sill",              # soglia/davanzale
    "trim",              # imbotti/coprifili
    "accessory",         # accessori generici
    "installation",      # montaggio
    "dismount",          # smontaggio
    "disposal",          # smaltimento
    "masonry",           # opere murarie
    "transport",         # trasporto
    "service",           # altro servizio
]


# =========================================================
# ENVIRONMENT (ambiente della casa)
# =========================================================
EnvironmentKind = Literal[
    "kitchen", "living_room", "bedroom_master", "bedroom_kid",
    "bathroom", "laundry", "study", "corridor", "attic",
    "garage", "cellar", "tavern", "office", "other",
]


class QuoteEnvironment(BaseModel):
    """Ambiente del preventivo — contenitore logico di più vani."""
    id: str = Field(default_factory=new_id)
    code: Optional[str] = None
    name: str
    kind: EnvironmentKind = "other"
    floor: Optional[str] = None
    notes: Optional[str] = None
    sort_order: int = 0
    photos: List[str] = Field(default_factory=list)


# =========================================================
# DIMENSION INHERITANCE
# =========================================================
DimensionSource = Literal[
    "manual",           # inserita a mano
    "inherited",        # ereditata dal vano
    "formula",          # calcolata da regola listino
    "override",         # override autorizzato (traccia motivazione)
]


class OpeningDimensions(BaseModel):
    """Misure principali del vano."""
    width_mm: Optional[int] = None
    height_mm: Optional[int] = None
    depth_mm: Optional[int] = None
    sill_height_mm: Optional[int] = None   # quota davanzale
    hole_type: Optional[str] = None         # es. "rettangolare", "ad arco"
    shape: Optional[str] = None
    installation_position: Optional[Literal["luce_finita", "telaio", "muro", "cassa_matta"]] = None


# =========================================================
# COMPATIBILITY RULES
# =========================================================
CompatibilityRelation = Literal[
    "compatible", "incompatible", "requires", "recommends",
    "verify", "mutually_exclusive",
]


class ProductCompatibilityRule(BaseDoc):
    """Motore compatibilità configurabile per prodotto/ruolo."""
    principal_role: ProductRole
    principal_product_type: Optional[str] = None   # es. "roller_shutter"
    related_role: ProductRole
    related_product_type: Optional[str] = None
    relation: CompatibilityRelation = "compatible"
    hard: bool = True                              # true = blocca, false = warning
    priority: int = 100
    message: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    active: bool = True
    is_demo: bool = False
    notes: Optional[str] = None


# =========================================================
# DIMENSION FORMULA (per ruolo/tipologia)
# =========================================================
class DimensionFormula(BaseDoc):
    """Formula per derivare le misure di un prodotto dal vano.

    Espressioni sicure valutate tramite services.formula (AST) —
    variabili disponibili: width_mm, height_mm, depth_mm, sill_height_mm.

    Esempi:
      tapparella width_expr:  width_mm + 60      (guide)
                  height_expr: height_mm + 40    (avvolgimento)
      cassonetto  width_expr:  width_mm + 40
                  height_expr: 220               (altezza fissa)
      zanzariera  width_expr:  width_mm - 10
                  height_expr: height_mm - 5
    """
    code: str
    label: str
    role: ProductRole
    product_type_code: Optional[str] = None
    width_expr: str = "width_mm"
    height_expr: str = "height_mm"
    depth_expr: Optional[str] = None
    min_billable_sqm: float = 0.0
    apply_when: Optional[Dict[str, Any]] = None
    version: int = 1
    active: bool = True
    is_demo: bool = False
    notes: Optional[str] = None


# =========================================================
# REQUESTS / RESPONSES
# =========================================================
class OpeningCreatePayload(BaseModel):
    quote_id: str
    environment_id: Optional[str] = None
    environment_name: Optional[str] = None       # se new environment
    environment_kind: str = "other"
    display_name: Optional[str] = None
    opening_number: Optional[int] = None
    dimensions: OpeningDimensions = Field(default_factory=OpeningDimensions)
    notes: Optional[str] = None


class OpeningProductAddPayload(BaseModel):
    opening_id: str
    role: ProductRole
    product_type_code: Optional[str] = None
    category: str = "window"                     # backward compat
    description: str = ""
    configuration: Dict[str, Any] = Field(default_factory=dict)
    dimensions: Dict[str, Any] = Field(default_factory=dict)
    dimension_source: DimensionSource = "inherited"
    dimension_formula_id: Optional[str] = None
    override_reason: Optional[str] = None
    quantity: float = 1.0
    unit_price: Optional[float] = None


class CompatibilityCheckRequest(BaseModel):
    opening_id: Optional[str] = None
    products_in_opening: List[Dict[str, Any]] = Field(default_factory=list)
    candidate_role: ProductRole
    candidate_product_type: Optional[str] = None


class CompatibilityCheckResponse(BaseModel):
    allow: bool = True
    warnings: List[str] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)
    matched_rules: List[Dict[str, Any]] = Field(default_factory=list)


class DimensionResolveRequest(BaseModel):
    opening_dimensions: OpeningDimensions
    role: ProductRole
    product_type_code: Optional[str] = None


class DimensionResolveResponse(BaseModel):
    width_mm: Optional[int] = None
    height_mm: Optional[int] = None
    depth_mm: Optional[int] = None
    source: DimensionSource
    formula_id: Optional[str] = None
    formula_code: Optional[str] = None
    detail: Optional[str] = None
