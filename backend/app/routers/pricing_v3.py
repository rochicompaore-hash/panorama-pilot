"""Router endpoint autorevole `POST /api/pricing/compute`.

Orchestratore unico che invoca ProfileSystemResolver -> BomResolver ->
TechnicalCostResolver -> CommercialPricingService.

Solo endpoint. Nessuna logica di business.
"""
from __future__ import annotations
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps import get_current_user
from app.services.pricing_v3 import PricingRequest, compute_pricing


router = APIRouter(prefix="/pricing", tags=["Pricing Engine v3"])


class PricingComputeBody(BaseModel):
    product_key: str = Field(..., description="Es. PROEVOLUTION")
    window_type: str = Field("WINDOW", description="WINDOW | DOOR_WINDOW | SLIDING")
    number_of_sashes: int = Field(1, ge=0)
    width_mm: int = Field(..., gt=0)
    height_mm: int = Field(..., gt=0)
    color_internal: str = Field("WHITE_MASS")
    color_external: str = Field("WHITE_MASS")
    glass_type: str = Field("DOUBLE_STANDARD")
    quantity: int = Field(1, ge=1)
    weld_allowance_mm: int = Field(3, ge=0)
    override_multiplier: Optional[float] = None


@router.post("/compute")
async def compute(payload: PricingComputeBody, user: dict = Depends(get_current_user)):
    """Endpoint autorevole. Ritorna PricingResult con:
      - pricing_status: ok | incomplete | invalid_geometry
      - technical_snapshot / commercial_snapshot / calculation_hash
      - request_echo, profile_system_resolution, bom_resolution
    """
    req = PricingRequest(
        tenant_id=user["tenant_id"],
        product_key=payload.product_key.upper(),
        window_type=payload.window_type.upper(),
        number_of_sashes=payload.number_of_sashes,
        width_mm=payload.width_mm,
        height_mm=payload.height_mm,
        color_internal=payload.color_internal.upper(),
        color_external=payload.color_external.upper(),
        glass_type=payload.glass_type.upper(),
        quantity=payload.quantity,
        weld_allowance_mm=payload.weld_allowance_mm,
        override_multiplier=payload.override_multiplier,
    )
    result = await compute_pricing(req)
    # Serializza dataclass a dict per JSONResponse
    return {
        "pricing_status": result.pricing_status,
        "blocking_errors": result.blocking_errors,
        "engine_version": result.engine_version,
        "calculated_at": result.calculated_at,
        "request_echo": result.request_echo,
        "profile_system_resolution": result.profile_system_resolution,
        "bom_resolution": result.bom_resolution,
        "technical_snapshot": result.technical_snapshot,
        "commercial_snapshot": result.commercial_snapshot,
        "calculation_hash": result.calculation_hash,
    }
