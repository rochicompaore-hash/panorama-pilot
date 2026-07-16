"""Extended pricing models (M3.2): pricelist versioning, rules with formulas, product configurations."""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field
from app.models import BaseDoc, new_id


class PricelistCreate(BaseModel):
    name: str
    description: Optional[str] = None
    currency: str = "EUR"
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    priority: int = 100
    is_default: bool = False


class PricelistUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    currency: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    priority: Optional[int] = None
    is_default: Optional[bool] = None


class RuleCondition(BaseModel):
    field: str
    op: str = "eq"  # eq|neq|in|nin|exists|truthy|falsy|gte|lte
    value: Any = None


class PriceRuleV2(BaseDoc):
    """Enhanced price rule with declarative conditions + safe formula."""
    pricelist_id: str
    code: str  # unique key like COLOR_IVORY_MASS, COLOR_FILM_DIFF, ROLLER_BASE
    name: str
    description: Optional[str] = None
    category: str = "generic"  # base | color | glass | hardware | roller | screen | shutter | box | sill | discount | installation
    conditions: List[RuleCondition] = Field(default_factory=list)
    # Formula that computes the impact. Must return a number.
    # For percentage rules: formula returns percentage (e.g., 8 for +8%). Set effect_type='pct'.
    # For fixed rules: formula returns amount in EUR. Set effect_type='fixed'.
    # For override rules: formula returns unit price. Set effect_type='set'.
    formula: str = "0"
    effect_type: str = "fixed"  # pct | fixed | set
    effect_target: str = "unit_price"  # unit_price | subtotal
    # ---- Explicit application scope (v2.1) ----
    # unit  = applied to per-piece price before quantity multiplication (default)
    # line  = applied ONCE to the line subtotal (after quantity)
    # opening = applied ONCE per opening (aggregate of lines linked to same opening)
    # quote = applied ONCE to the quote total (quote-wide surcharges/discounts)
    application_scope: str = "unit"
    # For explicit control regardless of scope:
    apply_before_quantity: bool = True   # meaningful only when scope=unit
    once_per_line: bool = False          # if true, fixed rules apply once even when scope=unit
    priority: int = 100  # applied in ascending order
    cumulative: bool = True
    active: bool = True
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    # audit
    version_note: Optional[str] = None


class PriceRuleV2Create(BaseModel):
    pricelist_id: str
    code: str
    name: str
    description: Optional[str] = None
    category: str = "generic"
    conditions: List[RuleCondition] = Field(default_factory=list)
    formula: str = "0"
    effect_type: str = "fixed"
    effect_target: str = "unit_price"
    application_scope: str = "unit"
    apply_before_quantity: bool = True
    once_per_line: bool = False
    priority: int = 100
    cumulative: bool = True
    active: bool = True


class PriceRuleV2Update(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    conditions: Optional[List[RuleCondition]] = None
    formula: Optional[str] = None
    effect_type: Optional[str] = None
    effect_target: Optional[str] = None
    application_scope: Optional[str] = None
    apply_before_quantity: Optional[bool] = None
    once_per_line: Optional[bool] = None
    priority: Optional[int] = None
    cumulative: Optional[bool] = None
    active: Optional[bool] = None
    version_note: Optional[str] = None


class PricelistSnapshot(BaseDoc):
    """Immutable snapshot of a pricelist + rules taken at quote send time."""
    pricelist_id: str
    pricelist_name: str
    rules: List[Dict[str, Any]] = Field(default_factory=list)
    quote_id: Optional[str] = None
    reason: str = "quote_sent"


class ConfiguratorPreviewRequest(BaseModel):
    """Live pricing preview request."""
    product_key: str
    product_config: Dict[str, Any] = Field(default_factory=dict)
    width_mm: Optional[int] = None
    height_mm: Optional[int] = None
    quantity: float = 1.0
    pricelist_id: Optional[str] = None
    # Optional client-side idempotency key
    request_id: Optional[str] = None
    # Optional override discount from operator
    discount_pct: float = 0.0
    discount_amount: float = 0.0
    # Optional VAT
    vat_rate: float = 0.22
    # Optional internal cost (only used if user has view_costs)
    internal_cost: float = 0.0


class ConfiguratorPreviewResponse(BaseModel):
    request_id: Optional[str] = None
    computed_at: datetime
    pricelist_id: Optional[str] = None
    pricelist_name: Optional[str] = None
    width_mm: Optional[int] = None
    height_mm: Optional[int] = None
    quantity: float
    sqm: float
    billable_sqm: float
    perimeter_m: float
    base_price: float
    unit_price_pre_qty: float = 0.0
    unit_price_final: float
    subtotal_line: float
    vat_amount: float
    total_line: float
    discount_pct: float
    discount_amount: float
    # detail breakdown (rule-by-rule)
    breakdown: List[Dict[str, Any]] = Field(default_factory=list)
    # cost/margin — populated only if permitted
    internal_cost: Optional[float] = None
    margin_abs: Optional[float] = None
    margin_pct: Optional[float] = None
    warnings: List[str] = Field(default_factory=list)


class ProductCatalog(BaseDoc):
    """Catalog entry for configurator products."""
    key: str
    name: str
    category: str  # window | shutter | roller | roller_kit | box | screen | persian | glass | hardware | sill | trim | accessory | installation
    description: Optional[str] = None
    base_price: float = 0.0
    base_type: str = "sqm"  # sqm | piece | linear_m
    min_billable_sqm: float = 0.0
    default_config: Dict[str, Any] = Field(default_factory=dict)
    # Configurator schema — steps rendered in the UI
    config_schema: Dict[str, Any] = Field(default_factory=dict)
    image_url: Optional[str] = None
    active: bool = True
    order_index: int = 0


class ProductCatalogCreate(BaseModel):
    key: str
    name: str
    category: str
    description: Optional[str] = None
    base_price: float = 0.0
    base_type: str = "sqm"
    min_billable_sqm: float = 0.0
    default_config: Dict[str, Any] = Field(default_factory=dict)
    config_schema: Dict[str, Any] = Field(default_factory=dict)
    order_index: int = 0


class ProductCatalogUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    base_price: Optional[float] = None
    base_type: Optional[str] = None
    min_billable_sqm: Optional[float] = None
    default_config: Optional[Dict[str, Any]] = None
    config_schema: Optional[Dict[str, Any]] = None
    active: Optional[bool] = None
    order_index: Optional[int] = None


class ForceOverrideRequest(BaseModel):
    """Payload for force-override endpoints. Reason mandatory."""
    reason: str
    data: Dict[str, Any] = Field(default_factory=dict)
