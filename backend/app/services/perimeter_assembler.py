"""Perimeter engine assembler — reads product+color+pricelist+glass_recipe+config,
assembles a PerimeterInput and runs compute_perimeter.

Kept as a service (not inlined in the router) so both simulate and quote-line
persistence can share the same logic and produce identical snapshots.
"""
from __future__ import annotations
from decimal import Decimal
from typing import Any, Dict, Optional

from fastapi import HTTPException

from app.services.recipes import (
    PerimeterInput, compute_perimeter,
    resolve_glass_recipe, compute_glass_dimensions,
)
from app.services.recipes.commercial_perimeter import display_dict as display_perimeter_dict
from app.services.catalog_service import (
    load_product, get_component_code, resolve_component_prices,
    get_color_is_premium, get_production_config,
)


def _dec(v):
    return Decimal(str(v)) if v is not None else None


async def build_perimeter_input(tenant_id: str, body) -> PerimeterInput:
    """Assemble a PerimeterInput from user body + database lookups.

    `body` is a `ProductSimulateRequest` — kept loose for reuse.
    """
    product = await load_product(tenant_id, body.product_id, body.product_key)
    if not product:
        raise HTTPException(404, "Prodotto non trovato")

    n_sashes = int(body.number_of_sashes or 1)
    window_type = body.window_type or "apribile"
    applies_to = "finestra_fissa" if window_type == "fissa" else f"finestra_{n_sashes}a"

    codes = {
        "frame":                get_component_code(product, "telaio", applies_to=applies_to) or
                                get_component_code(product, "telaio", applies_to="finestra_1a"),
        "sash":                 get_component_code(product, "anta_standard", applies_to=applies_to)
                                 if window_type == "apribile" else None,
        "glazing_bead":         get_component_code(product, "fermavetro", applies_to=applies_to) or
                                get_component_code(product, "fermavetro", applies_to="finestra_1a"),
        "reinforcement_frame":  get_component_code(product, "rinforzo_telaio", applies_to=applies_to) or
                                get_component_code(product, "rinforzo_telaio", applies_to="finestra_1a"),
        "reinforcement_sash":   get_component_code(product, "rinforzo_anta", applies_to=applies_to)
                                 if window_type == "apribile" else None,
    }
    if window_type == "apribile" and n_sashes > 1:
        codes["meeting_stile"] = get_component_code(product, "scambio_battuta", applies_to=applies_to) or \
                                  get_component_code(product, "scambio_battuta", applies_to="finestra_2a")
        codes["reinforcement_meeting_stile"] = get_component_code(product, "rinforzo_scambio", applies_to=applies_to) or \
                                                get_component_code(product, "rinforzo_scambio", applies_to="finestra_2a")

    codes = {k: v for k, v in codes.items() if v}
    prices, pricelist = await resolve_component_prices(tenant_id, codes, body.color_code)

    # Waste percentages — take from components[] `waste_percentage` field (default 0)
    def _waste(category: str) -> Decimal:
        for c in product.get("components", []):
            if c.get("category") == category:
                return Decimal(str(c.get("waste_percentage", 0)))
        return Decimal("0")

    # Glass recipe resolution
    frame_code = codes.get("frame")
    sash_code = codes.get("sash") or ""
    glass_recipe = await resolve_glass_recipe(
        tenant_id=tenant_id,
        product_key=product.get("key"),
        frame_code=frame_code or "",
        sash_code=sash_code,
        window_type=window_type,
        number_of_sashes=(0 if window_type == "fissa" else n_sashes),
    )

    glass_recipe_resolved = False
    gw = gh = None
    gq = 0
    if glass_recipe:
        try:
            gw, gh, gq = compute_glass_dimensions(
                glass_recipe, body.width_mm, body.height_mm, body.weld_allowance_mm,
            )
            glass_recipe_resolved = True
        except ValueError:
            glass_recipe_resolved = False

    # Colour premium check
    is_premium = body.is_color_premium
    if not is_premium:
        db_flag = await get_color_is_premium(tenant_id, body.color_code)
        if db_flag is True:
            is_premium = True

    # Production config
    cfg = await get_production_config(tenant_id)

    # Production time selection per number of sashes
    prod_time_field_map = {
        0: "fixed_window_time_minutes",
        1: "one_sash_time_minutes",
        2: "two_sash_time_minutes",
        3: "three_sash_time_minutes",
        4: "four_sash_time_minutes",
    }
    prod_time_key = prod_time_field_map.get(0 if window_type == "fissa" else n_sashes)
    prod_time_specific = cfg.get(prod_time_key) if prod_time_key else None
    prod_time = (body.override_production_time_min
                 or prod_time_specific
                 or cfg.get("production_time_default_minutes"))

    hardware_price = body.hardware_kit_price
    default_kit = product.get("default_hardware_kit") or {}
    if hardware_price is None:
        hardware_price = default_kit.get("price")

    glass_price = body.glass_price_per_sqm or cfg.get("default_glass_price_per_sqm")
    glass_min = body.glass_min_sqm or cfg.get("default_glass_min_sqm")

    other_cost = body.other_components_cost
    if other_cost is None and product.get("default_other_components_cost") is not None:
        other_cost = product["default_other_components_cost"]

    installation_cost = body.installation_cost
    if installation_cost is None and not body.installation_declared_zero:
        pass  # will surface MISSING_INSTALLATION_PRICE unless declared_zero

    inp = PerimeterInput(
        L_mm=body.width_mm, H_mm=body.height_mm,
        number_of_sashes=n_sashes,
        window_type=window_type,
        hardware_not_required=body.hardware_not_required,
        P_FRAME=_dec(prices.get("frame")),
        P_FRAME_REINFORCEMENT=_dec(prices.get("reinforcement_frame")),
        P_SASH=_dec(prices.get("sash")) if window_type == "apribile" else None,
        P_SASH_REINFORCEMENT=_dec(prices.get("reinforcement_sash")) if window_type == "apribile" else None,
        P_GLAZING_BEAD=_dec(prices.get("glazing_bead")),
        P_MEETING_STILE=_dec(prices.get("meeting_stile")) if n_sashes > 1 else None,
        P_MEETING_STILE_REINFORCEMENT=_dec(prices.get("reinforcement_meeting_stile")) if n_sashes > 1 else None,
        WASTE_FRAME=_waste("telaio"),
        WASTE_FRAME_REINFORCEMENT=_waste("rinforzo_telaio"),
        WASTE_SASH=_waste("anta_standard"),
        WASTE_SASH_REINFORCEMENT=_waste("rinforzo_anta"),
        WASTE_GLAZING_BEAD=_waste("fermavetro"),
        WASTE_MEETING_STILE=_waste("scambio_battuta"),
        glass_recipe_resolved=glass_recipe_resolved,
        glass_width_mm=gw, glass_height_mm=gh, glass_quantity=gq,
        P_GLASS_SQM=_dec(glass_price),
        MIN_GLASS_SQM=_dec(glass_min),
        P_HARDWARE=_dec(hardware_price),
        additional_material_cost=_dec(other_cost) if other_cost is not None else None,
        additional_declared_zero=body.other_components_declared_zero,
        is_color_premium=is_premium,
        premium_pct=_dec(cfg.get("premium_pvc_surcharge_pct")) or Decimal("6"),
        hourly_cost=_dec(body.override_hourly_cost or cfg.get("hourly_cost")),
        production_time_minutes=_dec(prod_time),
        margin_pct=_dec(body.override_margin_pct or cfg.get("default_margin_pct")),
        installation_cost=_dec(installation_cost) if installation_cost is not None else None,
        installation_declared_zero=body.installation_declared_zero,
        transport_cost=_dec(body.transport_cost) or Decimal("0"),
        disposal_cost=_dec(body.disposal_cost) or Decimal("0"),
        accessory_cost=_dec(body.accessory_cost) or Decimal("0"),
        discount_amount=_dec(body.discount_amount) or Decimal("0"),
        color_code=body.color_code,
        product_id=product.get("_id") or product.get("id"),
        product_key=product.get("key"),
        glass_code=body.glass_code,
        pricelist_version=(pricelist or {}).get("version") if pricelist else None,
    )
    return inp


async def run_perimeter_simulation(tenant_id: str, body) -> Dict[str, Any]:
    inp = await build_perimeter_input(tenant_id, body)
    result = compute_perimeter(inp)
    return display_perimeter_dict(result)
