"""Modelli dati per il nuovo motore pricing.

- PricingRequest: input dell'endpoint /api/pricing/compute
- ProfileSystemResolution: output di ProfileSystemResolver
- BomResolution: output di BomResolver (lista componenti + quantità)
- TechnicalSnapshot: output di TechnicalCostResolver (costo industriale)
- CommercialSnapshot: output di CommercialPricingService (prezzo vendita)
- PricingResult: aggregato finale con hash di integrità
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from typing import Any, Dict, List, Optional


@dataclass
class PricingRequest:
    """Input dell'endpoint POST /api/pricing/compute."""
    tenant_id: str
    product_key: str           # es. "PROEVOLUTION"
    window_type: str           # "WINDOW" | "DOOR_WINDOW" | "SLIDING"
    number_of_sashes: int
    width_mm: int
    height_mm: int
    color_internal: str = "WHITE_MASS"
    color_external: str = "WHITE_MASS"
    glass_type: str = "DOUBLE_STANDARD"
    quantity: int = 1
    weld_allowance_mm: int = 3
    # override opzionali per test
    override_multiplier: Optional[float] = None


@dataclass
class ProfileSystemResolution:
    """Output di ProfileSystemResolver."""
    profile_system_id: str
    profile_system_code: str
    profile_system_version: int
    technical_recipe_id: str
    technical_recipe_version: int
    recipe_code: str           # es. "PROEVOLUTION:WINDOW_1_SASH"


@dataclass
class BomComponent:
    """Singolo componente risolto dalla BOM."""
    role: str                          # FRAME, FRAME_REINFORCEMENT, SASH, ...
    component_code: str                # es. "5103"
    quantity_formula: str              # es. "2*(L+S) + 2*(H+S)"
    quantity_value: Decimal            # risultato del calcolo formula (unità: ml o m² o pz)
    unit_of_measure: str               # "ml" | "sqm" | "piece"
    unit_cost: Optional[Decimal] = None
    total_cost: Optional[Decimal] = None
    waste_pct: Decimal = Decimal("0")
    is_pvc_eligible: bool = False      # per pellicolato +10%
    notes: Optional[str] = None


@dataclass
class BomResolution:
    """Output di BomResolver."""
    components: List[BomComponent] = field(default_factory=list)
    glass_dimensions: Optional[Dict[str, Any]] = None   # {width_mm, height_mm, quantity, real_area, billable_area}
    hardware_role: Optional[str] = None                 # es. "WINDOW_STD"
    production_time_hours: Optional[Decimal] = None     # ore, non minuti


@dataclass
class TechnicalSnapshot:
    """Output di TechnicalCostResolver — costo industriale."""
    profile_system_id: str
    profile_system_version: int
    technical_recipe_id: str
    technical_recipe_version: int
    hourly_workshop_cost: Decimal
    production_time_hours: Decimal
    components: List[Dict[str, Any]] = field(default_factory=list)  # snapshot di ogni BomComponent
    glass_dimensions: Optional[Dict[str, Any]] = None
    material_cost: Decimal = Decimal("0")   # profili + rinforzi + fermavetro (no vetro, no ferramenta)
    glass_cost: Decimal = Decimal("0")
    hardware_cost: Decimal = Decimal("0")
    additional_technical_costs: Decimal = Decimal("0")
    labor_cost: Decimal = Decimal("0")
    foil_surcharge: Decimal = Decimal("0")  # pellicolato +10% su PVC eleggibili (Fase 1B)
    total_internal_cost: Decimal = Decimal("0")


@dataclass
class CommercialSnapshot:
    """Output di CommercialPricingService — prezzo vendita."""
    pricing_method: str = "MULTIPLIER"     # MULTIPLIER | MARKUP_ON_COST | TARGET_GROSS_MARGIN | FIXED_PRICE
    multiplier: Optional[Decimal] = None
    markup_pct: Optional[Decimal] = None
    gross_margin_pct: Optional[Decimal] = None
    fixed_price: Optional[Decimal] = None
    rule_version: Optional[int] = None
    discount: Decimal = Decimal("0")
    promotions: List[Dict[str, Any]] = field(default_factory=list)
    unit_sale_price: Decimal = Decimal("0")       # prima dello sconto
    final_unit_price: Decimal = Decimal("0")      # dopo lo sconto


@dataclass
class PricingResult:
    """Aggregato finale dell'endpoint /api/pricing/compute."""
    pricing_status: str = "ok"                # "ok" | "incomplete" | "invalid_geometry"
    blocking_errors: List[Dict[str, Any]] = field(default_factory=list)
    request_echo: Dict[str, Any] = field(default_factory=dict)
    profile_system_resolution: Optional[Dict[str, Any]] = None
    bom_resolution: Optional[Dict[str, Any]] = None
    technical_snapshot: Optional[Dict[str, Any]] = None
    commercial_snapshot: Optional[Dict[str, Any]] = None
    calculation_hash: Optional[str] = None
    calculated_at: Optional[str] = None
    engine_version: str = "pricing_v3-1.0.0"

    @property
    def unit_sale_price(self) -> Decimal:
        if self.commercial_snapshot:
            return Decimal(str(self.commercial_snapshot.get("final_unit_price", "0")))
        return Decimal("0")

    @property
    def technical_internal_cost(self) -> Decimal:
        if self.technical_snapshot:
            return Decimal(str(self.technical_snapshot.get("total_internal_cost", "0")))
        return Decimal("0")
