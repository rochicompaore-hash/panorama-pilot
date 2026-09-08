"""STEP 0 — WITHHOLDING COST nel Margin Engine (PO msg 400 STEP 0.3 GOLDEN — test permanente).

NET 10.000 · SUPPLY 4.000 · INSTALL 1.000 · OTHER 0 · WITHHOLDING 11% = 1.100
PRE_CONTRIBUTION 3.900 → PRE_MARGIN 39% → 15% → 1.500 → FINAL 2.400 → 24% → tachometer 24.
"""
from __future__ import annotations

import pytest

from app.services.margin_engine import compute_financial_snapshot, resolve_band


def _quote(withholding: bool):
    return {
        "subtotal": 10000.0, "vat_amount": 2200.0, "total": 12200.0,
        "withholding_applicable": withholding, "withholding_rate": 0.11,
        "lines": [
            {"category": "window", "quantity": 1, "internal_cost": 4000.0},
            {"category": "installation", "quantity": 1, "internal_cost": 1000.0},
        ],
    }


class TestWithholdingGolden:
    def test_golden_with_withholding(self):
        fs = compute_financial_snapshot(_quote(True))
        assert fs["net_revenue_ex_vat"] == 10000.0
        assert fs["supply_cost"] == 4000.0 and fs["installation_cost"] == 1000.0 and fs["other_direct_costs"] == 0.0
        assert fs["withholding_applicable"] is True and fs["withholding_cost"] == 1100.0
        assert fs["pre_commission_contribution"] == 3900.0
        assert fs["pre_commission_margin"] == 39.0
        assert fs["commission_rate"] == 0.15 and fs["commission_gross"] == 1500.0
        assert fs["final_company_contribution"] == 2400.0
        assert fs["final_company_margin"] == 24.0
        assert fs["tachometer_value"] == 24.0

    def test_withholding_really_changes_margins(self):
        with_wh = compute_financial_snapshot(_quote(True))
        without = compute_financial_snapshot(_quote(False))
        assert without["withholding_cost"] == 0.0 and without["pre_commission_contribution"] == 5000.0
        assert without["pre_commission_margin"] == 50.0 and without["final_company_margin"] == 35.0
        assert with_wh["pre_commission_margin"] < without["pre_commission_margin"]
        assert with_wh["final_company_margin"] < without["final_company_margin"]

    def test_no_withholding_when_not_applicable(self):
        fs = compute_financial_snapshot(_quote(False))
        assert fs["withholding_applicable"] is False
        assert fs["withholding_cost"] == 0.0 and fs["withholding_rate"] is None


class TestCommissionBoundaries:
    @pytest.mark.parametrize("margin,rate,status", [
        (30.01, 0.15, "OK"), (30.00, 0.10, "OK"), (20.00, 0.10, "OK"), (19.99, 0.08, "OK"),
        (15.00, 0.08, "OK"), (14.99, 0.05, "OK"), (8.00, 0.05, "OK"), (7.99, None, "AUTHORIZATION_REQUIRED"),
    ])
    def test_boundaries(self, margin, rate, status):
        _, r, s = resolve_band(margin)
        assert r == rate and s == status
