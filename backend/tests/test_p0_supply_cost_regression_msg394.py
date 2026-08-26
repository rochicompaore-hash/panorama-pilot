"""P0 SUPPLY_COST REGRESSION — Msg 394 §11-§18.

Il costo interno prodotto DEVE sempre alimentare SUPPLY_COST anche quando la
QuoteLine è arrivata via MultiCategoryConfigurator con payload RBAC-redacted.

Guardia strutturale (§4/§12 msg 394): se una linea prodotto ha
``internal_cost > 0`` o snapshot autoritativo, ``SUPPLY_COST`` aggregato
NON può essere 0.
"""
from __future__ import annotations

import pytest

from app.services.margin_engine import (
    aggregate_costs_from_lines,
    _extract_line_cost,
    compute_financial_snapshot,
)


class TestSupplyCostFromLegacyInternalCost:
    """§4 msg 394 — line.internal_cost * qty resta il fallback autoritativo."""

    def test_legacy_internal_cost_becomes_supply(self):
        lines = [{"category": "window", "quantity": 1, "internal_cost": 800.0}]
        c = aggregate_costs_from_lines(lines)
        assert c["supply_cost"] == 800.0

    def test_qty_multiplies(self):
        lines = [{"category": "window", "quantity": 3, "internal_cost": 800.0}]
        c = aggregate_costs_from_lines(lines)
        assert c["supply_cost"] == 2400.0


class TestSupplyCostFromSimpleSnapshot:
    """§2/§7/§8 msg 394 — Tapparelle/Zanzariere: purchase_cost_per_item * qty."""

    def test_tapparella_purchase_cost_per_item(self):
        lines = [{
            "category": "roller", "category_code": "TAPPARELLE",
            "pricing_model": "AREA", "quantity": 1,
            "simple_snapshot": {"purchase_cost_per_item": 58.80},
        }]
        c = aggregate_costs_from_lines(lines)
        assert c["supply_cost"] == 58.80

    def test_zanzariera_purchase_cost_per_item(self):
        lines = [{
            "category": "screen", "category_code": "ZANZARIERE",
            "pricing_model": "AREA", "quantity": 1,
            "simple_snapshot": {"purchase_cost_per_item": 32.34},
        }]
        c = aggregate_costs_from_lines(lines)
        assert c["supply_cost"] == 32.34


class TestSupplyCostFromTechnicalSnapshot:
    """§9 msg 394 — FORMULA_TECHNICAL: technical_snapshot.total_internal_cost."""

    def test_finestra_technical_cost(self):
        lines = [{
            "category_code": "FINESTRE", "pricing_model": "FORMULA_TECHNICAL",
            "quantity": 1,
            "technical_snapshot": {"total_internal_cost": 338.90},
        }]
        c = aggregate_costs_from_lines(lines)
        assert c["supply_cost"] == 338.90


class TestSupplyCostAdditiveWithServices:
    """§3/§5/§14/§15 msg 394 — INSTALLATION va aggiunta, non sostituisce."""

    def test_supply_and_install_are_separate(self):
        """Product cost 800 + POSA service cost 130 → SUPPLY=800 INSTALL=130."""
        lines = [{
            "category_code": "FINESTRE", "pricing_model": "FORMULA_TECHNICAL",
            "quantity": 1,
            "technical_snapshot": {"total_internal_cost": 800.0},
            "automatic_services": [{
                "service_type": "POSA",
                "sale_price_total": 150.0, "internal_cost_total": 130.0,
            }],
        }]
        c = aggregate_costs_from_lines(lines)
        assert c["supply_cost"] == 800.0  # ← NON diventa 0 né 930
        assert c["installation_cost"] == 130.0

    def test_multi_line_regression_msg394(self):
        """§13 msg 394 — Tapparella + posa: 58.80 supply + 100 install (non 158.80 install)."""
        lines = [{
            "category": "roller", "category_code": "TAPPARELLE",
            "pricing_model": "AREA", "quantity": 1,
            "simple_snapshot": {"purchase_cost_per_item": 58.80},
            "automatic_services": [{
                "service_type": "POSA",
                "sale_price_total": 120.0, "internal_cost_total": 100.0,
            }],
        }]
        c = aggregate_costs_from_lines(lines)
        assert c["supply_cost"] == 58.80  # ← product cost preserved
        assert c["installation_cost"] == 100.0

    def test_supply_only_mode_keeps_supply(self):
        """§14 msg 394 — SUPPLY_ONLY azzera INSTALL, MAI SUPPLY."""
        # SUPPLY_ONLY dopo lo switch mode = automatic_services vuoto
        lines = [{
            "category_code": "FINESTRE", "pricing_model": "FORMULA_TECHNICAL",
            "quantity": 1,
            "technical_snapshot": {"total_internal_cost": 800.0},
            "automatic_services": [],
        }]
        c = aggregate_costs_from_lines(lines)
        assert c["supply_cost"] == 800.0
        assert c["installation_cost"] == 0.0


class TestStructuralGuardSupplyNotLost:
    """§12 msg 394 — assert obbligatorio: se un prodotto ha costo>0, SUPPLY>0."""

    def test_supply_greater_than_zero_when_products_have_cost(self):
        # Un prodotto con costo > 0 non deve MAI dare SUPPLY=0
        lines = [{
            "category": "roller", "category_code": "TAPPARELLE",
            "pricing_model": "AREA", "quantity": 1,
            "simple_snapshot": {"purchase_cost_per_item": 58.80},
        }]
        c = aggregate_costs_from_lines(lines)
        assert c["supply_cost"] > 0, "SUPPLY_COST perso: prodotto con costo>0 aggrega 0€"

    def test_no_workaround_zero_products(self):
        # Se DAVVERO non c'è alcun costo, SUPPLY può essere 0 (transparency §2)
        lines = [{"category": "window", "quantity": 1, "internal_cost": 0.0}]
        c = aggregate_costs_from_lines(lines)
        assert c["supply_cost"] == 0.0


class TestE2EFinancialSnapshot:
    """§11 msg 394 — full E2E check con tutti i bucket."""

    def test_msg394_scenario(self):
        """§13 msg 394 — Tapparella (58.80 supply + 120 sale posa @ 100 cost)."""
        quote = {
            "subtotal": 296.40,  # 176.40 tapp + 120 posa
            "total": 361.61,     # + IVA 22%
            "lines": [{
                "category": "roller", "category_code": "TAPPARELLE",
                "pricing_model": "AREA", "quantity": 1,
                "simple_snapshot": {"purchase_cost_per_item": 58.80},
                "automatic_services": [{
                    "service_type": "POSA",
                    "sale_price_total": 120.0, "internal_cost_total": 100.0,
                }],
            }],
        }
        fs = compute_financial_snapshot(quote)
        assert fs["net_revenue_ex_vat"] == 296.40
        assert fs["supply_cost"] == 58.80
        assert fs["installation_cost"] == 100.0
        assert fs["other_direct_costs"] == 0.0
        # margin = (296.40 - 58.80 - 100) / 296.40 * 100 = 46.42%
        assert 46.0 <= fs["pre_commission_margin"] <= 47.0
        assert fs["margin_band"] == "OTTIMO"
