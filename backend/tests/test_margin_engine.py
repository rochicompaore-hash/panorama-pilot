"""MARGIN ENGINE V1 — Backend tests (msg 392).

Coverage:
  * resolve_band: 8 boundary cases (§3) + <8% CRITICO
  * compute_financial_snapshot: 2 golden cases (§23/§24) + edge cases
  * aggregate_costs_from_lines: reads authoritative snapshots (§6/§7)
  * redact_financial_snapshot_for_role: RBAC (§11 / §20)
  * strip_margin_from_pdf_payload: PDF/contract guard (§19)
"""
from __future__ import annotations

import pytest

from app.services.margin_engine import (
    resolve_band,
    aggregate_costs_from_lines,
    compute_financial_snapshot,
    redact_financial_snapshot_for_role,
    strip_margin_from_pdf_payload,
    COMMERCIAL_SAFE_KEYS,
    COMMISSION_BASE_POLICY,
)


class TestResolveBand:
    """§3 msg 392 — boundary tests OBBLIGATORI (esatti)."""

    @pytest.mark.parametrize("m,expected_band,expected_rate,expected_status", [
        (30.00, "OTTIMO",      0.15, "OK"),
        (29.99, "BUONO",       0.10, "OK"),
        (20.00, "BUONO",       0.10, "OK"),
        (19.99, "SUFFICIENTE", 0.08, "OK"),
        (15.00, "SUFFICIENTE", 0.08, "OK"),
        (14.99, "SCARSO",      0.05, "OK"),
        ( 8.00, "SCARSO",      0.05, "OK"),
        ( 7.99, "CRITICO",     None, "AUTHORIZATION_REQUIRED"),
    ])
    def test_boundary(self, m, expected_band, expected_rate, expected_status):
        band, rate, status = resolve_band(m)
        assert band == expected_band
        assert rate == expected_rate
        assert status == expected_status

    def test_negative_margin_still_critico(self):
        band, rate, status = resolve_band(-5.0)
        assert band == "CRITICO"
        assert rate is None  # §15: NON forzare 0
        assert status == "AUTHORIZATION_REQUIRED"

    def test_none_margin(self):
        band, rate, status = resolve_band(None)
        assert band == "UNKNOWN"
        assert rate is None
        assert status == "NO_DATA"

    def test_high_margin_capped_at_ottimo(self):
        band, rate, status = resolve_band(85.0)
        assert band == "OTTIMO"
        assert rate == 0.15


class TestAggregateCosts:
    """§6 msg 392 — motore CONSUMER dei snapshot esistenti."""

    def test_technical_snapshot_supply(self):
        lines = [{
            "category": "window",
            "quantity": 2,
            "technical_snapshot": {"total_internal_cost": 300.0},
        }]
        costs = aggregate_costs_from_lines(lines)
        assert costs["supply_cost"] == 600.0  # 300 * 2
        assert costs["installation_cost"] == 0.0
        assert costs["other_direct_costs"] == 0.0

    def test_simple_snapshot_area_by_color(self):
        # Tapparelle path: purchase_cost_per_item exists
        lines = [{
            "category": "roller",
            "quantity": 3,
            "simple_snapshot": {"purchase_cost_per_item": 58.80},
        }]
        costs = aggregate_costs_from_lines(lines)
        assert costs["supply_cost"] == 176.40  # 58.80 * 3

    def test_simple_snapshot_grid(self):
        lines = [{
            "category": "box",
            "quantity": 1,
            "simple_snapshot": {"internal_production_cost_per_item": 250.0},
        }]
        costs = aggregate_costs_from_lines(lines)
        assert costs["supply_cost"] == 250.0

    def test_installation_bucket(self):
        lines = [{"category": "installation", "quantity": 1, "internal_cost": 200.0}]
        costs = aggregate_costs_from_lines(lines)
        assert costs["installation_cost"] == 200.0
        assert costs["supply_cost"] == 0.0

    def test_other_direct_bucket(self):
        lines = [
            {"category": "disposal", "quantity": 1, "internal_cost": 50.0},
            {"category": "accessory", "quantity": 2, "internal_cost": 20.0},
        ]
        costs = aggregate_costs_from_lines(lines)
        assert costs["other_direct_costs"] == 90.0  # 50 + 20*2

    def test_purchase_total_cost_precedence(self):
        # purchase_total_cost is already qty-multiplied, must NOT double-multiply
        lines = [{
            "category": "screen",
            "quantity": 5,
            "simple_snapshot": {
                "purchase_total_cost": 100.0,     # authoritative aggregated
                "purchase_cost_per_item": 999.99, # decoy — must NOT be used
            },
        }]
        costs = aggregate_costs_from_lines(lines)
        assert costs["supply_cost"] == 100.0  # NOT 500

    def test_empty_lines(self):
        costs = aggregate_costs_from_lines([])
        assert costs == {"supply_cost": 0.0, "installation_cost": 0.0, "other_direct_costs": 0.0}


class TestGoldenScenarios:
    """§23-§24 msg 392 — 2 golden test verbatim."""

    def test_golden_23_ottimo(self):
        """NET=10000 SUPPLY=6000 INSTALL=1000 OTHER=0 → margin=30% OTTIMO commission=15%=1500 final=1500 15%."""
        quote = {
            "subtotal": 10_000.0,
            "vat_amount": 2_200.0,
            "total": 12_200.0,
            "lines": [
                {"category": "window", "quantity": 1, "technical_snapshot": {"total_internal_cost": 6_000.0}},
                {"category": "installation", "quantity": 1, "internal_cost": 1_000.0},
            ],
        }
        fs = compute_financial_snapshot(quote)
        assert fs["net_revenue_ex_vat"] == 10_000.0
        assert fs["supply_cost"] == 6_000.0
        assert fs["installation_cost"] == 1_000.0
        assert fs["other_direct_costs"] == 0.0
        assert fs["pre_commission_contribution"] == 3_000.0
        assert fs["pre_commission_margin"] == 30.0
        assert fs["margin_band"] == "OTTIMO"
        assert fs["commission_base_policy"] == "NET_REVENUE_EX_VAT"
        assert fs["commission_base"] == 10_000.0
        assert fs["commission_rate"] == 0.15
        assert fs["commission_gross"] == 1_500.0
        assert fs["commission_status"] == "OK"
        assert fs["final_company_contribution"] == 1_500.0
        assert fs["final_company_margin"] == 15.0

    def test_golden_24_buono(self):
        """NET=10000 SUPPLY=7000 INSTALL=500 OTHER=0 → margin=25% BUONO commission=10%=1000 final=1500 15%."""
        quote = {
            "subtotal": 10_000.0,
            "vat_amount": 2_200.0,
            "total": 12_200.0,
            "lines": [
                {"category": "window", "quantity": 1, "technical_snapshot": {"total_internal_cost": 7_000.0}},
                {"category": "installation", "quantity": 1, "internal_cost": 500.0},
            ],
        }
        fs = compute_financial_snapshot(quote)
        assert fs["pre_commission_margin"] == 25.0
        assert fs["margin_band"] == "BUONO"
        assert fs["commission_rate"] == 0.10
        assert fs["commission_gross"] == 1_000.0
        assert fs["final_company_contribution"] == 1_500.0
        assert fs["final_company_margin"] == 15.0

    def test_critico_no_commission_defined(self):
        """§15 — MARGIN<8% → commission_rate=None, status=AUTHORIZATION_REQUIRED."""
        quote = {"subtotal": 10_000.0, "vat_amount": 0.0, "total": 10_000.0, "lines": [
            {"category": "window", "quantity": 1, "technical_snapshot": {"total_internal_cost": 9_500.0}},
        ]}
        fs = compute_financial_snapshot(quote)
        assert fs["pre_commission_margin"] == 5.0
        assert fs["margin_band"] == "CRITICO"
        assert fs["commission_rate"] is None
        assert fs["commission_gross"] is None
        assert fs["commission_status"] == "AUTHORIZATION_REQUIRED"
        # §15 — NON inventare un final margin
        assert fs["final_company_contribution"] is None
        assert fs["final_company_margin"] is None

    def test_empty_quote(self):
        """No lines, no revenue → margin=None, band=UNKNOWN."""
        fs = compute_financial_snapshot({"subtotal": 0.0, "total": 0.0, "lines": []})
        assert fs["net_revenue_ex_vat"] == 0.0
        assert fs["pre_commission_margin"] is None
        assert fs["margin_band"] == "UNKNOWN"
        assert fs["commission_status"] == "NO_DATA"

    def test_live_recalc_band_flip(self):
        """§14 — un piccolo delta di sconto deve poter spostare la fascia."""
        base = {"subtotal": 10_000.0, "total": 10_000.0, "lines": [
            {"category": "window", "quantity": 1, "technical_snapshot": {"total_internal_cost": 6_999.0}},
        ]}
        fs = compute_financial_snapshot(base)
        # 30.01% -> OTTIMO 15%
        assert fs["margin_band"] == "OTTIMO"
        assert fs["commission_rate"] == 0.15
        # Applica sconto simulato: subtotal 9990 con stesso costo
        base["subtotal"] = 9_998.0
        fs2 = compute_financial_snapshot(base)
        # (9998-6999)/9998 = 29.996% -> BUONO
        assert fs2["margin_band"] == "BUONO"
        assert fs2["commission_rate"] == 0.10


class TestRBACRedaction:
    """§11 / §20 msg 392 — commercial vede solo margine/fascia/commissione."""

    def _sample_snapshot(self):
        return compute_financial_snapshot({
            "subtotal": 10_000.0, "total": 12_200.0, "lines": [
                {"category": "window", "quantity": 1, "technical_snapshot": {"total_internal_cost": 6_000.0}},
                {"category": "installation", "quantity": 1, "internal_cost": 1_000.0},
            ],
        })

    def test_admin_sees_full_breakdown(self):
        snap = self._sample_snapshot()
        red = redact_financial_snapshot_for_role(snap, is_admin=True)
        assert red == snap  # identity for admin
        assert "supply_cost" in red
        assert "final_company_margin" in red

    def test_commerciale_sees_only_safe_keys(self):
        snap = self._sample_snapshot()
        red = redact_financial_snapshot_for_role(snap, is_admin=False)
        assert set(red.keys()) == COMMERCIAL_SAFE_KEYS
        # Verified: no cost or margin breakdown leaks
        for forbidden in ("supply_cost", "installation_cost", "other_direct_costs",
                          "pre_commission_contribution", "pre_commission_margin",
                          "commission_base", "withholding_cost", "withholding_rate",
                          "final_company_contribution",
                          "margin_policy_version"):
            assert forbidden not in red, f"LEAK: {forbidden} exposed to Commerciale"

    def test_commerciale_sees_margin_and_commission(self):
        snap = self._sample_snapshot()
        red = redact_financial_snapshot_for_role(snap, is_admin=False)
        # msg 396 §6 — commerciale vede TACHOMETER (final_company_margin), non pre_commission
        assert red["tachometer_value"] == snap["final_company_margin"]
        assert red["margin_band"] == "OTTIMO"
        assert red["commission_rate"] == 0.15
        assert red["commission_gross"] == 1_500.0
        assert red["commission_status"] == "OK"
        assert red["net_revenue_ex_vat"] == 10_000.0

    def test_none_snapshot(self):
        assert redact_financial_snapshot_for_role(None, is_admin=True) is None
        assert redact_financial_snapshot_for_role(None, is_admin=False) is None


class TestPDFGuard:
    """§19 msg 392 — mai esportare margin/commission/costs nei documenti cliente."""

    def test_removes_financial_snapshot_top_level(self):
        payload = {
            "id": "q1", "total": 12000.0,
            "financial_snapshot": {"pre_commission_margin": 30.0, "commission_gross": 1500.0},
            "internal_cost": 7000.0, "margin_abs": 3000.0, "margin_pct": 30.0,
            "lines": [],
        }
        stripped = strip_margin_from_pdf_payload(payload)
        assert "financial_snapshot" not in stripped
        assert "internal_cost" not in stripped
        assert "margin_abs" not in stripped
        assert "margin_pct" not in stripped
        # allowed fields still there
        assert stripped["id"] == "q1"
        assert stripped["total"] == 12000.0

    def test_removes_technical_snapshot_from_lines(self):
        payload = {"lines": [{
            "id": "l1",
            "description": "Finestra",
            "unit_price_final": 800.0,
            "subtotal_line": 800.0,
            "technical_snapshot": {"total_internal_cost": 500.0, "components": [{"code": "PROF", "cost": 100}]},
            "pricing_snapshot": {"commercial_snapshot": {"final_unit_price": 800}},
            "internal_cost": 500.0,
            "margin": 300.0,
        }]}
        stripped = strip_margin_from_pdf_payload(payload)
        l = stripped["lines"][0]
        assert "technical_snapshot" not in l
        assert "pricing_snapshot" not in l
        assert "internal_cost" not in l
        assert "margin" not in l
        assert l["unit_price_final"] == 800.0
        assert l["description"] == "Finestra"


class TestPolicyVersioning:
    def test_snapshot_carries_policy_versions(self):
        fs = compute_financial_snapshot({"subtotal": 10_000.0, "total": 10_000.0, "lines": [
            {"category": "window", "quantity": 1, "technical_snapshot": {"total_internal_cost": 6_000.0}},
        ]})
        # msg 395 bump: v2 include ritenuta d'acconto
        assert fs["margin_policy_version"] == "margin_policy_v2_2026_02"
        assert fs["commission_policy_version"] == "commission_policy_v1_2026_02"
        assert fs["commission_base_policy"] == COMMISSION_BASE_POLICY == "NET_REVENUE_EX_VAT"
