"""Golden Tests — Margin Control & Cash Flow (Master Plan §41-§44)."""
from __future__ import annotations

from decimal import Decimal

from app.routers.margin_control import (
    FinancialSnapshotRequest,
    _compute_snapshot,
    DEFAULT_COMMISSION_RATE, DEFAULT_COMMISSION_DIVISOR,
    DEFAULT_WITHHOLDING_RATE, DEFAULT_WITHHOLDING_DIVISOR,
    DEFAULT_MULTIPLIER,
)


DEFAULT_RULES = {
    "commission_rate": float(DEFAULT_COMMISSION_RATE),
    "commission_divisor": float(DEFAULT_COMMISSION_DIVISOR),
    "withholding_rate": float(DEFAULT_WITHHOLDING_RATE),
    "withholding_divisor": float(DEFAULT_WITHHOLDING_DIVISOR),
    "default_commercial_multiplier": float(DEFAULT_MULTIPLIER),
    "status_thresholds": {"green_over_target_pct": 5, "yellow_below_target_pct": 5, "orange_below_min_pct": 0},
}

# Targets configurati per test §44
TARGETS_CONFIGURED = {
    "monthly_fixed_costs": 60000,
    "emergency_fund_target": 180000, "emergency_fund_current": 60000, "emergency_fund_months_to_target": 12,
    "investment_fund_annual_target": 120000, "investment_fund_current_allocated": 0, "investment_fund_months_remaining": 12,
    "monthly_profit_target": 20000,
    "monthly_revenue_target": 300000,
}
TARGETS_NOT_CONFIGURED = {
    "monthly_fixed_costs": None, "emergency_fund_target": None,
    "investment_fund_annual_target": None, "monthly_profit_target": None,
    "monthly_revenue_target": None,
    "emergency_fund_current": None, "emergency_fund_months_to_target": None,
    "investment_fund_current_allocated": None, "investment_fund_months_remaining": None,
}


def test_gt_base_numeric_no_withholding_no_discount():
    """Master Plan §41. Production=1000, mult=3, install_sale=150, install_ref=130."""
    req = FinancialSnapshotRequest(
        production_cost=1000,
        commercial_multiplier=3.0,
        installation_sale_price=150,
        installation_internal_reference=130,
    )
    s = _compute_snapshot(req, DEFAULT_RULES, TARGETS_NOT_CONFIGURED)
    # Base sale price = 1000 × 3 = 3000
    assert s["base_product_sale_price"] == 3000.00
    # Customer price net vat = 3000 + 150 - 0 = 3150
    assert s["customer_price_net_vat"] == 3150.00
    # Commissione = 3150 / 1.17 × 0.10 ≈ 269.23
    assert abs(s["commercial_commission"] - 269.23) < 0.01
    # Contribution margin = 3150 - 1000 - 130 - commission = 3150 - 1130 - 269.23 = 1750.77
    assert abs(s["contribution_margin_amount"] - 1750.77) < 0.02
    # Withholding non applicabile → cash effect = 0
    assert s["withholding_cash_effect"] == 0.00
    # Available cash = contribution (no withholding)
    assert s["expected_available_cash"] == s["contribution_margin_amount"]


def test_gt_with_discount_10pct():
    """§42 — sconto 10% deve ridurre commissione + contribution + cash. Production invariato."""
    req = FinancialSnapshotRequest(
        production_cost=1000, commercial_multiplier=3.0,
        installation_sale_price=150, installation_internal_reference=130,
        discount_amount=315,   # 10% di 3150
    )
    s = _compute_snapshot(req, DEFAULT_RULES, TARGETS_NOT_CONFIGURED)
    # production_cost INVARIATO (§42)
    assert s["production_cost"] == 1000.00
    # net_vat = 3150 - 315 = 2835
    assert s["customer_price_net_vat"] == 2835.00
    # Commissione = 2835 / 1.17 × 0.10 ≈ 242.31
    assert abs(s["commercial_commission"] - 242.31) < 0.01


def test_gt_with_withholding():
    """§9 withholding = customer_price / 1.22 × 0.11. Deve ridurre available_cash MA non contribution."""
    req_no_wh = FinancialSnapshotRequest(
        production_cost=1000, commercial_multiplier=3.0,
        installation_sale_price=150, installation_internal_reference=130,
        withholding_applicable=False,
    )
    req_wh = FinancialSnapshotRequest(
        production_cost=1000, commercial_multiplier=3.0,
        installation_sale_price=150, installation_internal_reference=130,
        withholding_applicable=True,
    )
    s_no = _compute_snapshot(req_no_wh, DEFAULT_RULES, TARGETS_NOT_CONFIGURED)
    s_wh = _compute_snapshot(req_wh, DEFAULT_RULES, TARGETS_NOT_CONFIGURED)

    # Contribution margin IDENTICA (§43: ritenuta NON è costo economico)
    assert s_no["contribution_margin_amount"] == s_wh["contribution_margin_amount"]

    # Withholding = 3150 / 1.22 × 0.11 ≈ 284.02
    assert abs(s_wh["withholding_cash_effect"] - 284.02) < 0.01
    assert s_no["withholding_cash_effect"] == 0.00

    # Available cash con ritenuta = contribution - withholding
    assert abs(s_no["expected_available_cash"] - s_wh["expected_available_cash"] - s_wh["withholding_cash_effect"]) < 0.01

    # Withholding receivable = credito da recuperare
    assert s_wh["withholding_receivable"] == s_wh["withholding_cash_effect"]


def test_gt_targets_math_44():
    """§44 — matematica dei target aziendali."""
    from app.routers.margin_control import _derive_targets
    d = _derive_targets(TARGETS_CONFIGURED)
    # emergency: (180-60)/12 = 10
    assert d["monthly_emergency_allocation"] == 10000
    # investment: 120/12 = 10
    assert d["monthly_investment_allocation"] == 10000
    # required contribution = 60 + 10 + 10 + 20 = 100
    assert d["required_monthly_contribution"] == 100000
    # required margin = 100/300 = 33.333%
    assert abs(d["required_margin_rate_pct"] - 33.3333) < 0.01


def test_gt_margin_status_thresholds():
    """Semaforo GREEN/YELLOW/ORANGE/RED."""
    # Con target configurati → required_margin_rate calcolato
    req = FinancialSnapshotRequest(
        production_cost=1000, commercial_multiplier=3.0,
        installation_sale_price=150, installation_internal_reference=130,
    )
    s = _compute_snapshot(req, DEFAULT_RULES, TARGETS_CONFIGURED)
    # Contribution ≈ 1750.77 su net_revenue 3150 → 55.58% >> 33.33% + 5% → GREEN
    assert s["margin_status"] == "GREEN", (s["margin_status"], s["contribution_margin_pct"])

    # Costruisco un caso ORANGE (margine positivo sotto target)
    req_low = FinancialSnapshotRequest(
        production_cost=1900, commercial_multiplier=3.0,   # base = 5700
        installation_sale_price=150, installation_internal_reference=130,
        discount_amount=3400,  # net = 2450
    )
    s2 = _compute_snapshot(req_low, DEFAULT_RULES, TARGETS_CONFIGURED)
    assert s2["margin_status"] in ("ORANGE", "YELLOW", "RED"), s2


def test_gt_policy_not_configured():
    """Senza target → status POLICY_NOT_CONFIGURED (§48: non blocca preventivo)."""
    req = FinancialSnapshotRequest(production_cost=1000, commercial_multiplier=3.0,
                                    installation_sale_price=150, installation_internal_reference=130)
    s = _compute_snapshot(req, DEFAULT_RULES, TARGETS_NOT_CONFIGURED)
    assert s["margin_status"] == "POLICY_NOT_CONFIGURED"
    assert s["minimum_sustainable_price"] is None
    assert s["discount_room_amount"] is None
    # Ma il calcolo procede comunque
    assert s["contribution_margin_amount"] > 0


def test_gt_production_cost_untouched_by_all_adjustments():
    """§10, §22, §42: production_cost NON cambia per sconto/commissione/ritenuta."""
    base = FinancialSnapshotRequest(production_cost=1000, commercial_multiplier=3.0)
    s1 = _compute_snapshot(base, DEFAULT_RULES, TARGETS_NOT_CONFIGURED)
    for kwargs in [
        {"discount_amount": 500},
        {"withholding_applicable": True},
        {"discount_amount": 200, "withholding_applicable": True},
        {"other_direct_costs": 100},
    ]:
        s = _compute_snapshot(FinancialSnapshotRequest(production_cost=1000, commercial_multiplier=3.0, **kwargs),
                                DEFAULT_RULES, TARGETS_NOT_CONFIGURED)
        assert s["production_cost"] == 1000.00, (kwargs, s["production_cost"])
