"""Unit tests — Multi-Category Simple Pricing Engine + Resolver.

Verifica:
  * AREA con minimum_billable (§36 acceptance: 100€/m² min 1.50, 1000×800 -> 150€).
  * LINEAR_METER, PER_ITEM, FIXED_PRICE, FIXED_PLUS_VARIABLE, TIERED.
  * Resolver fail-closed: legacy_disabled, missing_pricing_model,
    manual_review_required, invalid_inputs.
"""
from __future__ import annotations

import asyncio

import pytest

from app.models_multi_category import ConfigureRequest, SimplePricingInputs
from app.services.multi_category_pricing import (
    SimplePricingEngine,
    resolve_and_compute,
)


# ---------------------------------------------------------------------------
# SimplePricingEngine
# ---------------------------------------------------------------------------
class TestAreaEngine:
    def test_area_with_minimum_billable_below_threshold(self):
        """§36 acceptance: 100€/m² min 1.50, 1000×800 -> 150€."""
        product = {
            "pricing_model": "AREA",
            "pricing_config": {"unit_sale_price": 100.0},
            "minimum_billable_quantity": 1.50,
        }
        inputs = SimplePricingInputs(width_mm=1000, height_mm=800, quantity=1)
        out = SimplePricingEngine.compute_area(product, inputs)
        assert out["real_area_m2"] == 0.80
        assert out["billable_area_m2"] == 1.50
        assert out["sale_price_total"] == 150.0

    def test_area_above_minimum(self):
        """2000×1000 -> real=2.0, billable=2.0."""
        product = {
            "pricing_model": "AREA",
            "pricing_config": {"unit_sale_price": 100.0},
            "minimum_billable_quantity": 1.50,
        }
        inputs = SimplePricingInputs(width_mm=2000, height_mm=1000, quantity=1)
        out = SimplePricingEngine.compute_area(product, inputs)
        assert out["real_area_m2"] == 2.0
        assert out["billable_area_m2"] == 2.0
        assert out["sale_price_total"] == 200.0

    def test_zanzariera_fixture_130(self):
        """130€/m² min 1.50 con dimensioni 800×800 -> 195€."""
        product = {
            "pricing_model": "AREA",
            "pricing_config": {"unit_sale_price": 130.0},
            "minimum_billable_quantity": 1.50,
        }
        inputs = SimplePricingInputs(width_mm=800, height_mm=800, quantity=1)
        out = SimplePricingEngine.compute_area(product, inputs)
        assert out["billable_area_m2"] == 1.50
        assert out["sale_price_total"] == 195.0

    def test_area_missing_unit_price(self):
        product = {"pricing_model": "AREA", "pricing_config": {}}
        inputs = SimplePricingInputs(width_mm=1000, height_mm=1000)
        with pytest.raises(ValueError, match="MISSING_UNIT_SALE_PRICE"):
            SimplePricingEngine.compute_area(product, inputs)

    def test_area_invalid_dimensions(self):
        product = {"pricing_model": "AREA", "pricing_config": {"unit_sale_price": 100.0}}
        inputs = SimplePricingInputs(width_mm=0, height_mm=1000)
        with pytest.raises(ValueError, match="INVALID_DIMENSIONS"):
            SimplePricingEngine.compute_area(product, inputs)

    def test_area_multiple_quantity(self):
        product = {"pricing_model": "AREA", "pricing_config": {"unit_sale_price": 100.0}}
        inputs = SimplePricingInputs(width_mm=1000, height_mm=1000, quantity=3)
        out = SimplePricingEngine.compute_area(product, inputs)
        # real=1.0, unit_price_final=100, qty=3 -> 300
        assert out["real_area_m2"] == 1.0
        assert out["sale_price_total"] == 300.0


class TestLinearEngine:
    def test_linear_basic(self):
        product = {"pricing_model": "LINEAR_METER", "pricing_config": {"unit_sale_price": 25.0}}
        inputs = SimplePricingInputs(linear_meters=4, quantity=1)
        out = SimplePricingEngine.compute_linear(product, inputs)
        assert out["billable_linear_meters"] == 4
        assert out["sale_price_total"] == 100.0

    def test_linear_minimum(self):
        product = {
            "pricing_model": "LINEAR_METER",
            "pricing_config": {"unit_sale_price": 25.0},
            "minimum_billable_quantity": 2.0,
        }
        inputs = SimplePricingInputs(linear_meters=1.2, quantity=1)
        out = SimplePricingEngine.compute_linear(product, inputs)
        assert out["billable_linear_meters"] == 2.0
        assert out["sale_price_total"] == 50.0


class TestPerItemEngine:
    def test_per_item(self):
        product = {"pricing_model": "PER_ITEM", "pricing_config": {"unit_sale_price": 50.0}}
        inputs = SimplePricingInputs(quantity=3)
        out = SimplePricingEngine.compute_per_item(product, inputs)
        assert out["sale_price_total"] == 150.0

    def test_per_item_invalid_qty(self):
        product = {"pricing_model": "PER_ITEM", "pricing_config": {"unit_sale_price": 50.0}}
        inputs = SimplePricingInputs(quantity=0)
        with pytest.raises(ValueError, match="INVALID_QUANTITY"):
            SimplePricingEngine.compute_per_item(product, inputs)


class TestFixedPriceEngine:
    def test_fixed(self):
        product = {"pricing_model": "FIXED_PRICE", "pricing_config": {"fixed_sale_price": 120.0}}
        inputs = SimplePricingInputs(quantity=1)
        out = SimplePricingEngine.compute_fixed_price(product, inputs)
        assert out["sale_price_total"] == 120.0


class TestFixedPlusVariable:
    def test_fpv_by_quantity(self):
        product = {
            "pricing_model": "FIXED_PLUS_VARIABLE",
            "pricing_config": {"fixed_component": 50.0, "variable_unit_price": 10.0, "variable_basis": "quantity"},
        }
        inputs = SimplePricingInputs(quantity=4)
        out = SimplePricingEngine.compute_fixed_plus_variable(product, inputs)
        # variable = 10*4=40, unit=50+40=90, qty=4 -> 360
        assert out["variable_component"] == 40.0
        assert out["unit_price_final"] == 90.0
        assert out["sale_price_total"] == 360.0


class TestTiered:
    def test_tiered_by_quantity(self):
        product = {
            "pricing_model": "TIERED",
            "pricing_config": {
                "tier_basis": "quantity",
                "tiers": [
                    {"up_to": 10, "unit_sale_price": 100.0},
                    {"up_to": 50, "unit_sale_price": 90.0},
                    {"up_to": None, "unit_sale_price": 80.0},
                ],
            },
        }
        inputs = SimplePricingInputs(quantity=30)
        out = SimplePricingEngine.compute_tiered(product, inputs)
        # basis_value=30 -> tier 90.0, line_total=90*30=2700, qty=30 -> 81000
        assert out["tier_selected"]["unit_sale_price"] == 90.0


# ---------------------------------------------------------------------------
# Resolver fail-closed
# ---------------------------------------------------------------------------
class TestResolver:
    def _run(self, product, req, tenant_id="test-tenant", category=None):
        return asyncio.run(resolve_and_compute(product, category, req, tenant_id))

    def test_legacy_disabled(self):
        product = {"key": "OLD", "name": "Old", "legacy": True, "new_quote_enabled": False, "pricing_model": None}
        req = ConfigureRequest(simple_inputs=SimplePricingInputs(quantity=1))
        r = self._run(product, req)
        assert r.pricing_status == "legacy_disabled"

    def test_missing_pricing_model(self):
        product = {"key": "X", "name": "X", "new_quote_enabled": True, "pricing_model": None}
        req = ConfigureRequest(simple_inputs=SimplePricingInputs(quantity=1))
        r = self._run(product, req)
        assert r.pricing_status == "missing_pricing_model"

    def test_manual_review_required(self):
        product = {"key": "MRR", "name": "MRR", "new_quote_enabled": True, "pricing_model": "MANUAL_REVIEW_REQUIRED"}
        req = ConfigureRequest(simple_inputs=SimplePricingInputs(quantity=1))
        r = self._run(product, req)
        assert r.pricing_status == "manual_review_required"

    def test_area_ok(self):
        product = {
            "key": "TEST_AREA",
            "name": "Test",
            "new_quote_enabled": True,
            "legacy": False,
            "pricing_model": "AREA",
            "pricing_config": {"unit_sale_price": 100.0},
            "minimum_billable_quantity": 1.5,
        }
        req = ConfigureRequest(simple_inputs=SimplePricingInputs(width_mm=1000, height_mm=800, quantity=1))
        r = self._run(product, req)
        assert r.pricing_status == "ok"
        assert r.pricing_model == "AREA"
        assert r.simple_snapshot["sale_price_total"] == 150.0

    def test_area_missing_inputs(self):
        product = {
            "key": "TEST_AREA",
            "name": "Test",
            "new_quote_enabled": True,
            "pricing_model": "AREA",
            "pricing_config": {"unit_sale_price": 100.0},
        }
        req = ConfigureRequest(simple_inputs=None)
        r = self._run(product, req)
        assert r.pricing_status == "invalid_inputs"

    def test_technical_requires_technical_inputs(self):
        product = {
            "key": "PROEVOLUTION",
            "name": "ProEvolution",
            "new_quote_enabled": True,
            "pricing_model": "FORMULA_TECHNICAL",
        }
        req = ConfigureRequest(simple_inputs=SimplePricingInputs(quantity=1))  # no technical_inputs
        r = self._run(product, req)
        assert r.pricing_status == "invalid_inputs"
