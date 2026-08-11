"""Unified Pricing Phase 1 — vertical slice ProEvolution 1-anta.

Architettura target:
  ProfileSystemResolver -> BomResolver -> TechnicalCostResolver -> CommercialPricingService

Ogni resolver ha una responsabilità netta:
  - ProfileSystemResolver: quale sistema profilo + quale ricetta tecnica
  - BomResolver: quali componenti e in che quantità (formule V1_3)
  - TechnicalCostResolver: costo industriale totale (materiali + manodopera)
  - CommercialPricingService: applicazione moltiplicatore commerciale
"""
from .models import (
    PricingRequest, PricingResult,
    ProfileSystemResolution, BomResolution, TechnicalSnapshot, CommercialSnapshot,
    BomComponent,
)
from .errors import PricingError, ERROR_CODES
from .orchestrator import compute_pricing

__all__ = [
    "PricingRequest", "PricingResult",
    "ProfileSystemResolution", "BomResolution", "TechnicalSnapshot", "CommercialSnapshot",
    "BomComponent", "PricingError", "ERROR_CODES",
    "compute_pricing",
]
