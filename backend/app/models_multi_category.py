"""Multi-Category Quote Configurator — Data Models (V1).

Modelli additivi per il nuovo preventivatore multi-categoria approvato dal PO.

Vincoli chiave:
  * `category` != `pricing_model` (una categoria può contenere prodotti con
    pricing_model differenti).
  * Nessuna migrazione automatica dei prodotti legacy: un prodotto senza
    `pricing_model` viene marcato `legacy=True` / `new_quote_enabled=False` /
    `classification_status="TO_CONFIRM"` e NON compare nel nuovo flusso.
  * Fail-closed: un prodotto attivo nel nuovo flusso DEVE avere `pricing_model`
    valorizzato altrimenti il resolver risponde `MISSING_PRICING_MODEL`.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models import BaseDoc, new_id


# ---------------------------------------------------------------------------
# Pricing Models (enum autorevole)
# ---------------------------------------------------------------------------
class PricingModel(str, Enum):
    """Pricing models supportati dal nuovo configuratore.

    - FORMULA_TECHNICAL      -> `POST /api/pricing/compute` (motore autorevole).
    - AREA                   -> real_area x unit_price con optional minimum billable.
    - LINEAR_METER           -> lunghezza x prezzo/ml con optional minimum.
    - PER_ITEM               -> quantità x unit_sale_price.
    - FIXED_PRICE            -> prezzo fisso indipendente da dimensioni/qty.
    - FIXED_PLUS_VARIABLE    -> quota fissa + quota variabile (per dimensione o qty).
    - TIERED                 -> scaglioni (definiti in pricing_config.tiers[]).
    - MANUAL_REVIEW_REQUIRED -> il commerciale NON assegna prezzi; workflow autorizzativo futuro.
    """

    FORMULA_TECHNICAL = "FORMULA_TECHNICAL"
    AREA = "AREA"
    LINEAR_METER = "LINEAR_METER"
    PER_ITEM = "PER_ITEM"
    FIXED_PRICE = "FIXED_PRICE"
    FIXED_PLUS_VARIABLE = "FIXED_PLUS_VARIABLE"
    TIERED = "TIERED"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    GRID = "GRID"


VALID_PRICING_MODELS = {m.value for m in PricingModel}


# ---------------------------------------------------------------------------
# Product Category (data-driven, non hardcoded frontend)
# ---------------------------------------------------------------------------
class ProductCategory(BaseDoc):
    """Categoria commerciale del catalogo (data-driven, tenant-scoped)."""

    code: str  # FINESTRE, PORTEFINESTRE, ZANZARIERE, ...
    label: str
    description: Optional[str] = None
    display_order: int = 0
    icon: Optional[str] = None  # nome icona lucide/phosphor o url
    active: bool = True


class ProductCategoryCreate(BaseModel):
    code: str
    label: str
    description: Optional[str] = None
    display_order: int = 0
    icon: Optional[str] = None
    active: bool = True


class ProductCategoryUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    display_order: Optional[int] = None
    icon: Optional[str] = None
    active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Simple Pricing Request/Response
# ---------------------------------------------------------------------------
class SimplePricingInputs(BaseModel):
    """Input per il Simple Pricing Engine (AREA/LINEAR/ITEM/FIXED/...)."""

    width_mm: Optional[float] = None
    height_mm: Optional[float] = None
    linear_meters: Optional[float] = None
    quantity: float = 1.0
    variant: Optional[str] = None
    options: Dict[str, Any] = Field(default_factory=dict)


class ConfigureRequest(BaseModel):
    """Payload di `POST /api/products/{product_id}/configure`.

    Il resolver decide dove instradare in base al `pricing_model` del prodotto:
      * FORMULA_TECHNICAL   -> `technical_inputs` obbligatori.
      * altri modelli       -> `simple_inputs` obbligatori (con i campi previsti).
    """

    technical_inputs: Optional[Dict[str, Any]] = None
    simple_inputs: Optional[SimplePricingInputs] = None
    # Contesto commerciale opzionale (per applicazione multiplier pacchetto)
    commercial_package_code: Optional[str] = None


class ConfigureResponse(BaseModel):
    """Risposta del resolver.

    - `pricing_status`: ok | incomplete | missing_pricing_model | legacy_disabled |
                        manual_review_required | invalid_inputs.
    - `pricing_model`: modello effettivamente applicato.
    - `technical_snapshot` / `commercial_snapshot` / `simple_snapshot`:
        popolati in modo condizionale in base al modello.
    """

    pricing_status: str
    pricing_model: Optional[str] = None
    engine_version: str = "multi_cat_v1"
    calculated_at: Optional[str] = None
    product: Dict[str, Any] = Field(default_factory=dict)
    category: Dict[str, Any] = Field(default_factory=dict)
    inputs_echo: Dict[str, Any] = Field(default_factory=dict)
    # Snapshots
    technical_snapshot: Optional[Dict[str, Any]] = None
    commercial_snapshot: Optional[Dict[str, Any]] = None
    simple_snapshot: Optional[Dict[str, Any]] = None
    calculation_hash: Optional[str] = None
    blocking_errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Nuovi campi additivi per ProductCatalog (documentati; l'implementazione è
# in `models_pricing.py` extension via patch, ma questa è la reference).
# ---------------------------------------------------------------------------
PRODUCT_CATALOG_MULTI_CAT_FIELDS = {
    "pricing_model": "Optional[PricingModel]",  # None se prodotto legacy non classificato
    "pricing_config": "Dict[str, Any]",  # {unit_price, min_billable, tiers, recipe_id...}
    "category_id": "Optional[str]",  # FK -> product_categories._id
    "category_code": "Optional[str]",  # denormalizzato per performance
    "subcategory": "Optional[str]",
    "line": "Optional[str]",  # es. ProEvolution, ProEvolution Restauro
    "sale_unit": "Optional[str]",  # m2 | ml | pz | forfait
    "minimum_billable_quantity": "Optional[float]",
    "compatible_packages": "List[str]",  # es. ['BASE', 'ADVANCED', 'PREMIUM']
    "compatible_services": "List[str]",  # id/code simple_services suggeriti
    "technical_recipe_id": "Optional[str]",
    "configurator_schema": "Optional[Dict[str, Any]]",
    "legacy": "bool",  # True per prodotti pre-multi-cat
    "new_quote_enabled": "bool",  # False per legacy o TO_CONFIRM
    "classification_status": "str",  # CLASSIFIED | TO_CONFIRM | LEGACY_ONLY
}
