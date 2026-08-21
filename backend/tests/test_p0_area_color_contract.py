"""P0 REGRESSION — Canonical contract of SimplePricingEngine.compute_area_by_color.

Bug (msg 391): Tapparelle/Zanzariere returned ``sale_price_per_item`` only,
NOT ``unit_price_final``, so the frontend read chain
``unit_price_final ?? final_unit_price ?? unit_sale_price``
resolved to null and rendered ``COMMERCIAL_PRICING_NOT_CONFIGURED``
even though the backend calculation was correct.

Contract (§6 PO — canonical): every simple engine MUST expose
``unit_price_final`` (per billed unit) and ``sale_price_total`` (line total).

Reference values (msg 391 §4-5):
    TAPPARELLA 1200×1400 RAL       -> 176.40 €
    TAPPARELLA 1200×1400 LEGNO     -> 201.60 €
    TAPPARELLA 1200×1400 RAFFAELLO -> 226.80 €
    UNIKVER    800×800  BASE       ->  97.02 €  (min 1.50 m² applicato)
"""
from __future__ import annotations

import pytest

from app.models_multi_category import PricingModel, SimplePricingInputs
from app.services.multi_category_pricing import SimplePricingEngine


TAPPARELLA_PRODUCT = {
    "key": "TAPPARELLA_STANDARD",
    "category_code": "TAPPARELLE",
    "pricing_model": PricingModel.AREA.value,
    "sale_unit": "m2",
    "pricing_config": {
        "purchase_cost_table_per_m2": {"RAL": 35.0, "LEGNO": 40.0, "RAFFAELLO": 45.0},
        "commercial_multiplier": 3.0,
        "minimum_billable_area_m2": 1.5,
        "color_domain": "INTERNAL_MAP",
        "color_map": {"RAL_STANDARD": "RAL", "WOOD_EFFECT": "LEGNO", "RAFFAELLO": "RAFFAELLO"},
        "pricing_version": "tapparelle_2026_08_v2_x3",
    },
}

UNIKVER_PRODUCT = {
    "key": "UNIKVER",
    "category_code": "ZANZARIERE",
    "pricing_model": PricingModel.AREA.value,
    "sale_unit": "m2",
    "pricing_config": {
        "purchase_cost_table_per_m2": {"BASE": 21.56, "WOOD_EFFECT": 30.18, "MARBLE": 23.72, "SPECIAL": 23.72},
        "commercial_multiplier": 3.0,
        "minimum_billable_area_m2": 1.5,
        "color_domain": "ZANZARIERE",
        "pricing_version": "zanzariere_2026_08_v2_x3",
    },
}


def _compute_tap(color_code: str, w: int = 1200, h: int = 1400, qty: int = 1):
    inputs = SimplePricingInputs(width_mm=w, height_mm=h, quantity=qty, options={"color_code": color_code})
    color_lookup = TAPPARELLA_PRODUCT["pricing_config"]["color_map"]
    return SimplePricingEngine.compute_area_by_color(TAPPARELLA_PRODUCT, inputs, color_lookup)


def _compute_uv(color_code: str = "ZC_BASE_DEFAULT", w: int = 800, h: int = 800, qty: int = 1):
    inputs = SimplePricingInputs(width_mm=w, height_mm=h, quantity=qty, options={"color_code": color_code})
    color_lookup = {"ZC_BASE_DEFAULT": "BASE", "ZC_WOOD_DEFAULT": "WOOD_EFFECT", "ZC_MARBLE_DEFAULT": "MARBLE"}
    return SimplePricingEngine.compute_area_by_color(UNIKVER_PRODUCT, inputs, color_lookup)


class TestCanonicalContract:
    """The snapshot MUST expose the canonical fields the frontend reads."""

    def test_unit_price_final_present_tapparella(self):
        snap = _compute_tap("RAL_STANDARD")
        assert "unit_price_final" in snap, "MISSING canonical field: unit_price_final"
        assert snap["unit_price_final"] is not None
        assert snap["unit_price_final"] > 0

    def test_unit_price_final_present_zanzariera(self):
        snap = _compute_uv()
        assert "unit_price_final" in snap
        assert snap["unit_price_final"] is not None
        assert snap["unit_price_final"] > 0

    def test_unit_price_final_equals_sale_price_per_item(self):
        """Since billed unit == item, the two MUST agree exactly."""
        snap = _compute_tap("WOOD_EFFECT")
        assert snap["unit_price_final"] == snap["sale_price_per_item"]

    def test_sale_price_total_present(self):
        snap = _compute_tap("RAL_STANDARD", qty=3)
        assert snap["sale_price_total"] == snap["unit_price_final"] * 3


class TestExpectedValues:
    """Msg 391 §4-5 — verified reference values."""

    @pytest.mark.parametrize("color,expected", [
        ("RAL_STANDARD", 176.40),
        ("WOOD_EFFECT",  201.60),
        ("RAFFAELLO",    226.80),
    ])
    def test_tapparella_1200x1400(self, color, expected):
        snap = _compute_tap(color)
        assert snap["unit_price_final"] == expected, f"{color}: got {snap['unit_price_final']} expected {expected}"
        assert snap["sale_price_total"] == expected

    def test_unikver_800x800_base(self):
        # real 0.64, min 1.5 -> billable 1.5 * 21.56 = 32.34 * 3 = 97.02
        snap = _compute_uv()
        assert snap["unit_price_final"] == 97.02
        assert snap["sale_price_total"] == 97.02
        assert snap["billable_area_m2_per_item"] == 1.5
