"""Orchestratore della nuova architettura pricing.

Riceve una PricingRequest, invoca i 4 resolver in sequenza, produce PricingResult
con technical_snapshot + commercial_snapshot + calculation_hash.

NON contiene logica di calcolo — solo orchestrazione + hash + serializzazione.
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict

from app.db import get_db
from .models import PricingRequest, PricingResult
from .errors import PricingError
from .resolvers import (
    ProfileSystemResolver, BomResolver, TechnicalCostResolver, CommercialPricingService,
)


def _serialize(obj: Any) -> Any:
    """Serializza dataclass/Decimal per JSON."""
    if isinstance(obj, Decimal):
        return str(obj)
    if hasattr(obj, "__dict__"):
        return {k: _serialize(v) for k, v in vars(obj).items()}
    if isinstance(obj, list):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


def _round2(d: Decimal) -> float:
    """Arrotonda a 2 decimali per display JSON."""
    return float(d.quantize(Decimal("0.01")))


def _compute_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


async def compute_pricing(req: PricingRequest, db=None) -> PricingResult:
    """Orchestratore. Restituisce PricingResult (mai lancia PricingError — cattura e la mette in blocking_errors)."""
    if db is None:
        db = get_db()
    result = PricingResult(
        request_echo={
            "tenant_id": req.tenant_id,
            "product_key": req.product_key,
            "window_type": req.window_type,
            "number_of_sashes": req.number_of_sashes,
            "width_mm": req.width_mm,
            "height_mm": req.height_mm,
            "color_internal": req.color_internal,
            "color_external": req.color_external,
            "glass_type": req.glass_type,
            "quantity": req.quantity,
            "weld_allowance_mm": req.weld_allowance_mm,
        },
        calculated_at=datetime.now(timezone.utc).isoformat(),
    )

    try:
        # Step 1 — Profile system + technical recipe
        ps = await ProfileSystemResolver(db).resolve(req)
        result.profile_system_resolution = _serialize(ps)

        # Step 2 — BOM
        bom = await BomResolver(db).resolve(req, ps)
        result.bom_resolution = {
            "components": [_serialize(c) for c in bom.components],
            "glass_dimensions": bom.glass_dimensions,
            "hardware_role": bom.hardware_role,
            "production_time_hours": str(bom.production_time_hours) if bom.production_time_hours else None,
        }

        # Step 3 — Technical cost
        tech = await TechnicalCostResolver(db).resolve(req, ps, bom)
        result.technical_snapshot = {
            "profile_system_id": tech.profile_system_id,
            "profile_system_version": tech.profile_system_version,
            "technical_recipe_id": tech.technical_recipe_id,
            "technical_recipe_version": tech.technical_recipe_version,
            "hourly_workshop_cost": str(tech.hourly_workshop_cost),
            "production_time_hours": str(tech.production_time_hours),
            "components": tech.components,
            "glass_dimensions": tech.glass_dimensions,
            "material_cost": _round2(tech.material_cost),
            "glass_cost": _round2(tech.glass_cost),
            "hardware_cost": _round2(tech.hardware_cost),
            "additional_technical_costs": _round2(tech.additional_technical_costs),
            "labor_cost": _round2(tech.labor_cost),
            "foil_surcharge": _round2(tech.foil_surcharge),
            "total_internal_cost": _round2(tech.total_internal_cost),
        }

        # Step 4 — Commercial pricing
        com = await CommercialPricingService(db).apply(req, tech)
        result.commercial_snapshot = {
            "pricing_method": com.pricing_method,
            "multiplier": str(com.multiplier) if com.multiplier is not None else None,
            "markup_pct": str(com.markup_pct) if com.markup_pct is not None else None,
            "gross_margin_pct": str(com.gross_margin_pct) if com.gross_margin_pct is not None else None,
            "fixed_price": str(com.fixed_price) if com.fixed_price is not None else None,
            "rule_version": com.rule_version,
            "discount": _round2(com.discount),
            "unit_sale_price": _round2(com.unit_sale_price),
            "final_unit_price": _round2(com.final_unit_price),
        }

        # Hash di integrità: copre tutti i dati di calcolo
        result.calculation_hash = _compute_hash({
            "request": result.request_echo,
            "profile_system": result.profile_system_resolution,
            "bom": result.bom_resolution,
            "technical": result.technical_snapshot,
            "commercial": result.commercial_snapshot,
            "engine_version": result.engine_version,
        })

        if com.final_unit_price <= 0:
            result.pricing_status = "incomplete"
            result.blocking_errors.append({
                "code": "COMPUTED_ZERO",
                "message": "Motore ha prodotto prezzo zero — configurazione anomala.",
            })

    except PricingError as e:
        result.pricing_status = "incomplete"
        result.blocking_errors.append(e.to_dict())

    return result


def verify_snapshot_integrity(snapshot: Dict[str, Any], expected_hash: str) -> bool:
    """Ricalcola l'hash del payload e verifica l'integrità.

    Uso: alla lettura di un preventivo storico, prima di mostrare il prezzo.
    """
    computed = _compute_hash({
        "request": snapshot.get("request_echo") or snapshot.get("request", {}),
        "profile_system": snapshot.get("profile_system_resolution"),
        "bom": snapshot.get("bom_resolution"),
        "technical": snapshot.get("technical_snapshot"),
        "commercial": snapshot.get("commercial_snapshot"),
        "engine_version": snapshot.get("engine_version", "pricing_v3-1.0.0"),
    })
    return computed == expected_hash
