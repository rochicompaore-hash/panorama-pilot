"""Multi-Category Pricing Engine.

Contiene:
  * ``SimplePricingEngine`` — per AREA / LINEAR_METER / PER_ITEM / FIXED_PRICE /
    FIXED_PLUS_VARIABLE / TIERED.
  * ``resolve_and_compute`` — resolver che, in base al ``pricing_model`` del
    prodotto, instrada al motore corretto:
      - FORMULA_TECHNICAL  -> ``app.services.pricing_v3.compute_pricing`` (motore
                              tecnico autorevole, NON duplicato).
      - altri modelli      -> ``SimplePricingEngine``.
      - MANUAL_REVIEW_REQUIRED -> nessun prezzo restituito (workflow futuro).

Fail-closed:
  * Prodotto senza ``pricing_model`` valido -> ``missing_pricing_model``.
  * Prodotto ``legacy=True`` o ``new_quote_enabled=False`` -> ``legacy_disabled``.
  * Inputs non validi per il modello -> ``invalid_inputs`` con dettaglio.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from app.models_multi_category import (
    PricingModel,
    VALID_PRICING_MODELS,
    ConfigureRequest,
    ConfigureResponse,
    SimplePricingInputs,
)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def _round2(x: float) -> float:
    return round(float(x) + 1e-9, 2)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_payload(payload: Dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _real_area_m2(width_mm: Optional[float], height_mm: Optional[float]) -> Optional[float]:
    if not width_mm or not height_mm:
        return None
    return round((float(width_mm) / 1000.0) * (float(height_mm) / 1000.0) + 1e-9, 4)


# ---------------------------------------------------------------------------
# Simple Pricing Engine
# ---------------------------------------------------------------------------
class SimplePricingEngine:
    """Motore semplice per pricing non-tecnici (backend-authoritative).

    Ogni metodo restituisce un dizionario ``simple_snapshot`` con i campi
    caratteristici del modello e ``sale_price_total`` finale.
    """

    @staticmethod
    def compute_area(product: Dict[str, Any], inputs: SimplePricingInputs) -> Dict[str, Any]:
        cfg = product.get("pricing_config") or {}
        unit_price = cfg.get("unit_sale_price")
        if unit_price is None:
            raise ValueError("MISSING_UNIT_SALE_PRICE")
        min_billable = product.get("minimum_billable_quantity") or cfg.get("minimum_billable_area_m2") or 0.0
        real_area = _real_area_m2(inputs.width_mm, inputs.height_mm)
        if real_area is None or real_area <= 0:
            raise ValueError("INVALID_DIMENSIONS")
        billable_area = max(real_area, float(min_billable)) if min_billable else real_area
        qty = max(float(inputs.quantity or 1), 1.0)
        unit_price_final = _round2(billable_area * float(unit_price))
        sale_price_total = _round2(unit_price_final * qty)
        return {
            "pricing_model": PricingModel.AREA.value,
            "width_mm": inputs.width_mm,
            "height_mm": inputs.height_mm,
            "real_area_m2": real_area,
            "minimum_billable_area_m2": float(min_billable) if min_billable else None,
            "billable_area_m2": billable_area,
            "unit_sale_price": float(unit_price),
            "unit_price_final": unit_price_final,
            "quantity": qty,
            "sale_price_total": sale_price_total,
            "sale_unit": "m2",
        }

    @staticmethod
    def compute_linear(product: Dict[str, Any], inputs: SimplePricingInputs) -> Dict[str, Any]:
        cfg = product.get("pricing_config") or {}
        unit_price = cfg.get("unit_sale_price")
        if unit_price is None:
            raise ValueError("MISSING_UNIT_SALE_PRICE")
        min_billable = product.get("minimum_billable_quantity") or cfg.get("minimum_billable_linear_meters") or 0.0
        ml = float(inputs.linear_meters or 0)
        if ml <= 0:
            raise ValueError("INVALID_LINEAR_METERS")
        billable_ml = max(ml, float(min_billable)) if min_billable else ml
        qty = max(float(inputs.quantity or 1), 1.0)
        unit_price_final = _round2(billable_ml * float(unit_price))
        sale_price_total = _round2(unit_price_final * qty)
        return {
            "pricing_model": PricingModel.LINEAR_METER.value,
            "linear_meters": ml,
            "minimum_billable_linear_meters": float(min_billable) if min_billable else None,
            "billable_linear_meters": billable_ml,
            "unit_sale_price": float(unit_price),
            "unit_price_final": unit_price_final,
            "quantity": qty,
            "sale_price_total": sale_price_total,
            "sale_unit": "ml",
        }

    @staticmethod
    def compute_per_item(product: Dict[str, Any], inputs: SimplePricingInputs) -> Dict[str, Any]:
        cfg = product.get("pricing_config") or {}
        unit_price = cfg.get("unit_sale_price")
        if unit_price is None:
            raise ValueError("MISSING_UNIT_SALE_PRICE")
        qty = float(inputs.quantity or 0)
        if qty <= 0:
            raise ValueError("INVALID_QUANTITY")
        sale_price_total = _round2(float(unit_price) * qty)
        return {
            "pricing_model": PricingModel.PER_ITEM.value,
            "unit_sale_price": float(unit_price),
            "unit_price_final": _round2(float(unit_price)),
            "quantity": qty,
            "sale_price_total": sale_price_total,
            "variant": inputs.variant,
            "sale_unit": "pz",
        }

    @staticmethod
    def compute_fixed_price(product: Dict[str, Any], inputs: SimplePricingInputs) -> Dict[str, Any]:
        cfg = product.get("pricing_config") or {}
        fixed = cfg.get("fixed_sale_price")
        if fixed is None:
            raise ValueError("MISSING_FIXED_SALE_PRICE")
        qty = max(float(inputs.quantity or 1), 1.0)
        sale_price_total = _round2(float(fixed) * qty)
        return {
            "pricing_model": PricingModel.FIXED_PRICE.value,
            "fixed_sale_price": float(fixed),
            "unit_price_final": _round2(float(fixed)),
            "quantity": qty,
            "sale_price_total": sale_price_total,
            "sale_unit": "forfait",
        }

    @staticmethod
    def compute_fixed_plus_variable(product: Dict[str, Any], inputs: SimplePricingInputs) -> Dict[str, Any]:
        cfg = product.get("pricing_config") or {}
        fixed = cfg.get("fixed_component")
        variable_unit = cfg.get("variable_unit_price")
        variable_basis = (cfg.get("variable_basis") or "quantity").lower()  # quantity | area | linear
        if fixed is None or variable_unit is None:
            raise ValueError("MISSING_FIXED_OR_VARIABLE_PRICE")

        basis_value = 0.0
        if variable_basis == "area":
            ra = _real_area_m2(inputs.width_mm, inputs.height_mm)
            if ra is None or ra <= 0:
                raise ValueError("INVALID_DIMENSIONS_FOR_VARIABLE_BASIS")
            basis_value = ra
        elif variable_basis == "linear":
            basis_value = float(inputs.linear_meters or 0)
            if basis_value <= 0:
                raise ValueError("INVALID_LINEAR_FOR_VARIABLE_BASIS")
        else:
            basis_value = float(inputs.quantity or 1)

        variable_component = _round2(float(variable_unit) * basis_value)
        qty = max(float(inputs.quantity or 1), 1.0)
        unit_price = _round2(float(fixed) + variable_component)
        sale_price_total = _round2(unit_price * qty)
        return {
            "pricing_model": PricingModel.FIXED_PLUS_VARIABLE.value,
            "fixed_component": float(fixed),
            "variable_unit_price": float(variable_unit),
            "variable_basis": variable_basis,
            "variable_basis_value": basis_value,
            "variable_component": variable_component,
            "unit_price_final": unit_price,
            "quantity": qty,
            "sale_price_total": sale_price_total,
            "sale_unit": product.get("sale_unit") or "pz",
        }

    @staticmethod
    def compute_tiered(product: Dict[str, Any], inputs: SimplePricingInputs) -> Dict[str, Any]:
        cfg = product.get("pricing_config") or {}
        tiers = cfg.get("tiers") or []
        if not tiers:
            raise ValueError("MISSING_TIERS")
        basis = (cfg.get("tier_basis") or "quantity").lower()  # quantity | area | linear
        basis_value = 0.0
        if basis == "area":
            ra = _real_area_m2(inputs.width_mm, inputs.height_mm)
            if ra is None or ra <= 0:
                raise ValueError("INVALID_DIMENSIONS_FOR_TIERED")
            basis_value = ra
        elif basis == "linear":
            basis_value = float(inputs.linear_meters or 0)
        else:
            basis_value = float(inputs.quantity or 1)

        # Selezione tier: primo tier con basis_value <= up_to (o l'ultimo se supera)
        selected = None
        for t in sorted(tiers, key=lambda x: (x.get("up_to") is None, x.get("up_to") or 1e18)):
            up = t.get("up_to")
            if up is None or basis_value <= float(up):
                selected = t
                break
        if selected is None:
            selected = tiers[-1]
        unit_price = selected.get("unit_sale_price")
        if unit_price is None:
            raise ValueError("MISSING_TIER_UNIT_PRICE")
        qty = max(float(inputs.quantity or 1), 1.0)
        line_total = _round2(float(unit_price) * basis_value)
        sale_price_total = _round2(line_total * qty)
        return {
            "pricing_model": PricingModel.TIERED.value,
            "tier_basis": basis,
            "tier_basis_value": basis_value,
            "tier_selected": selected,
            "unit_price_final": _round2(float(unit_price)),
            "quantity": qty,
            "sale_price_total": sale_price_total,
            "sale_unit": product.get("sale_unit") or basis,
        }

    # -------- dispatch --------
    @classmethod
    def compute(cls, product: Dict[str, Any], inputs: SimplePricingInputs) -> Dict[str, Any]:
        model = product.get("pricing_model")
        if model == PricingModel.AREA.value:
            return cls.compute_area(product, inputs)
        if model == PricingModel.LINEAR_METER.value:
            return cls.compute_linear(product, inputs)
        if model == PricingModel.PER_ITEM.value:
            return cls.compute_per_item(product, inputs)
        if model == PricingModel.FIXED_PRICE.value:
            return cls.compute_fixed_price(product, inputs)
        if model == PricingModel.FIXED_PLUS_VARIABLE.value:
            return cls.compute_fixed_plus_variable(product, inputs)
        if model == PricingModel.TIERED.value:
            return cls.compute_tiered(product, inputs)
        raise ValueError(f"UNSUPPORTED_SIMPLE_MODEL:{model}")


# ---------------------------------------------------------------------------
# Resolver: decide dove instradare in base al pricing_model del prodotto
# ---------------------------------------------------------------------------
def _pack_product(product: Dict[str, Any]) -> Dict[str, Any]:
    """Slim public product info per la risposta."""
    return {
        "id": product.get("id") or product.get("_id"),
        "key": product.get("key"),
        "code": product.get("key"),
        "name": product.get("name"),
        "category_id": product.get("category_id"),
        "category_code": product.get("category_code"),
        "pricing_model": product.get("pricing_model"),
        "sale_unit": product.get("sale_unit"),
    }


async def resolve_and_compute(
    product: Dict[str, Any],
    category: Optional[Dict[str, Any]],
    req: ConfigureRequest,
    tenant_id: str,
) -> ConfigureResponse:
    """Resolver principale — fail-closed.

    Args:
      product: doc prodotto (già letto dal router).
      category: doc categoria (opzionale, per contesto).
      req: input configurazione.
      tenant_id: tenant.
    """
    now = _iso_now()
    inputs_echo = req.model_dump(exclude_none=True)

    # --- Guard: legacy / disabled ---
    if product.get("legacy") or not product.get("new_quote_enabled", False):
        return ConfigureResponse(
            pricing_status="legacy_disabled",
            pricing_model=product.get("pricing_model"),
            calculated_at=now,
            product=_pack_product(product),
            category=category or {},
            inputs_echo=inputs_echo,
            blocking_errors=["Prodotto legacy o non abilitato al nuovo preventivatore."],
        )

    model = product.get("pricing_model")

    # --- Guard: missing/invalid pricing_model ---
    if not model or model not in VALID_PRICING_MODELS:
        return ConfigureResponse(
            pricing_status="missing_pricing_model",
            pricing_model=model,
            calculated_at=now,
            product=_pack_product(product),
            category=category or {},
            inputs_echo=inputs_echo,
            blocking_errors=["Il prodotto non ha un pricing_model valido configurato."],
        )

    # --- MANUAL_REVIEW_REQUIRED: nessun prezzo restituito ---
    if model == PricingModel.MANUAL_REVIEW_REQUIRED.value:
        return ConfigureResponse(
            pricing_status="manual_review_required",
            pricing_model=model,
            calculated_at=now,
            product=_pack_product(product),
            category=category or {},
            inputs_echo=inputs_echo,
            warnings=["Configurazione da verificare. Prezzo non assegnabile dal commerciale."],
        )

    # --- FORMULA_TECHNICAL: usa il motore autorevole (NO duplicazione) ---
    if model == PricingModel.FORMULA_TECHNICAL.value:
        if not req.technical_inputs:
            return ConfigureResponse(
                pricing_status="invalid_inputs",
                pricing_model=model,
                calculated_at=now,
                product=_pack_product(product),
                category=category or {},
                inputs_echo=inputs_echo,
                blocking_errors=["technical_inputs richiesti per FORMULA_TECHNICAL."],
            )
        from app.services.pricing_v3 import PricingRequest, compute_pricing

        ti = req.technical_inputs or {}
        try:
            pr = PricingRequest(
                tenant_id=tenant_id,
                product_key=(ti.get("product_key") or product.get("key") or "").upper(),
                window_type=str(ti.get("window_type") or "WINDOW").upper(),
                number_of_sashes=int(ti.get("number_of_sashes") or 1),
                width_mm=int(ti.get("width_mm") or 0),
                height_mm=int(ti.get("height_mm") or 0),
                color_internal=str(ti.get("color_internal") or "WHITE_MASS").upper(),
                color_external=str(ti.get("color_external") or "WHITE_MASS").upper(),
                glass_type=str(ti.get("glass_type") or "DOUBLE_STANDARD").upper(),
                quantity=int(ti.get("quantity") or 1),
                weld_allowance_mm=int(ti.get("weld_allowance_mm") or 3),
                override_multiplier=ti.get("override_multiplier"),
            )
        except (TypeError, ValueError) as e:
            return ConfigureResponse(
                pricing_status="invalid_inputs",
                pricing_model=model,
                calculated_at=now,
                product=_pack_product(product),
                category=category or {},
                inputs_echo=inputs_echo,
                blocking_errors=[f"technical_inputs non validi: {e}"],
            )
        result = await compute_pricing(pr)
        return ConfigureResponse(
            pricing_status=result.pricing_status,
            pricing_model=model,
            engine_version=f"technical:{result.engine_version}",
            calculated_at=result.calculated_at or now,
            product=_pack_product(product),
            category=category or {},
            inputs_echo=inputs_echo,
            technical_snapshot=result.technical_snapshot,
            commercial_snapshot=result.commercial_snapshot,
            calculation_hash=result.calculation_hash,
            blocking_errors=result.blocking_errors or [],
        )

    # --- Simple Pricing Engine per gli altri modelli ---
    if not req.simple_inputs:
        return ConfigureResponse(
            pricing_status="invalid_inputs",
            pricing_model=model,
            calculated_at=now,
            product=_pack_product(product),
            category=category or {},
            inputs_echo=inputs_echo,
            blocking_errors=["simple_inputs richiesti per questo pricing_model."],
        )
    try:
        snap = SimplePricingEngine.compute(product, req.simple_inputs)
    except ValueError as e:
        return ConfigureResponse(
            pricing_status="invalid_inputs",
            pricing_model=model,
            calculated_at=now,
            product=_pack_product(product),
            category=category or {},
            inputs_echo=inputs_echo,
            blocking_errors=[str(e)],
        )

    calc_hash = _hash_payload({
        "product_id": product.get("id") or product.get("_id"),
        "pricing_model": model,
        "snap": snap,
    })
    return ConfigureResponse(
        pricing_status="ok",
        pricing_model=model,
        engine_version="simple_pricing_v1",
        calculated_at=now,
        product=_pack_product(product),
        category=category or {},
        inputs_echo=inputs_echo,
        simple_snapshot=snap,
        calculation_hash=calc_hash,
    )
