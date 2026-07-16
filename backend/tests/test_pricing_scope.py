"""Backend economic tests for M3.2 pricing engine scope semantics.

Verifies:
  - qty=1 / qty=2 / qty=5 don't double-multiply fixed rules
  - scope=unit rules multiply with qty
  - scope=line rules apply ONCE regardless of qty
  - once_per_line=true fixed rules apply ONCE even when scope=unit
"""
import pytest
from decimal import Decimal
from app.services.pricing_v2 import compute_preview


@pytest.fixture
def product():
    return {"base_price": 480.0, "base_type": "sqm", "min_billable_sqm": 1.0}


@pytest.fixture
def rules_film_diff():
    return [
        {
            "code": "COLOR_FILM_DIFF_PCT",
            "conditions": [{"field": "color_kind", "op": "eq", "value": "film_diff"}],
            "formula": "22", "effect_type": "pct", "priority": 100,
            "application_scope": "unit", "active": True,
        },
        {
            "code": "COLOR_FILM_DIFF_FIXED",
            "conditions": [{"field": "color_kind", "op": "eq", "value": "film_diff"}],
            "formula": "150", "effect_type": "fixed", "priority": 101,
            "application_scope": "line", "active": True,
        },
    ]


def _run(product, rules, qty, config=None):
    return compute_preview(
        product=product, rules=rules,
        product_config=config or {"color_kind": "film_diff"},
        width_mm=1200, height_mm=1400, quantity=qty,
        discount_pct=0, discount_amount=0, vat_rate=0.22,
        internal_cost=0, can_see_costs=False,
        pricelist_id="pl1", pricelist_name="TEST",
    )


def test_qty1_no_double_multiplication(product, rules_film_diff):
    r = _run(product, rules_film_diff, 1)
    assert r["unit_price_pre_qty"] == pytest.approx(983.81, abs=0.01)  # 806.40 + 22%
    assert r["subtotal_line"] == pytest.approx(1133.81, abs=0.01)  # 983.81 + 150 (line once)


def test_qty2_fixed_once_per_line(product, rules_film_diff):
    r = _run(product, rules_film_diff, 2)
    assert r["unit_price_pre_qty"] == pytest.approx(983.81, abs=0.01)
    # 983.81 * 2 = 1967.62 + 150 (ONCE) = 2117.62 — NOT 2267.62 (which would be fixed×2)
    assert r["subtotal_line"] == pytest.approx(2117.62, abs=0.01)
    assert r["unit_price_final"] == pytest.approx(1058.81, abs=0.01)  # 2117.62 / 2


def test_qty5_fixed_still_once(product, rules_film_diff):
    r = _run(product, rules_film_diff, 5)
    # 983.81 * 5 = 4919.05 + 150 = 5069.05
    assert r["subtotal_line"] == pytest.approx(5069.05, abs=0.01)


def test_scope_unit_pct_multiplies_with_qty(product, rules_film_diff):
    """Pct rules at scope=unit affect per-piece price then multiply by qty."""
    r1 = _run(product, rules_film_diff, 1)
    r2 = _run(product, rules_film_diff, 2)
    # 22% surcharge in r1 is 177.41; in r2 the same per-piece surcharge contributes 177.41*2
    # via multiplication step, not via re-applied rule.
    pct_r1 = next(b for b in r1["breakdown"] if b["code"] == "COLOR_FILM_DIFF_PCT")["amount"]
    pct_r2 = next(b for b in r2["breakdown"] if b["code"] == "COLOR_FILM_DIFF_PCT")["amount"]
    assert pct_r1 == pytest.approx(pct_r2)  # same UNIT-level amount
    # But subtotal differs: (983.81 - 806.40) contributes to both, then × qty.
    assert r2["subtotal_line"] - 150 == pytest.approx((r1["subtotal_line"] - 150) * 2, abs=0.01)


def test_scope_line_fixed_once_regardless_qty(product, rules_film_diff):
    for qty in (1, 2, 3, 5, 10):
        r = _run(product, rules_film_diff, qty)
        fixed_line = next(b for b in r["breakdown"] if b["code"] == "COLOR_FILM_DIFF_FIXED")
        assert fixed_line["amount"] == pytest.approx(150.0, abs=0.01), f"failed qty={qty}"
        assert fixed_line["scope"] == "line"


def test_no_rules_match_no_surcharge(product, rules_film_diff):
    r = _run(product, rules_film_diff, 2, config={"color_kind": "standard"})
    # Only base 806.40 * 2
    assert r["subtotal_line"] == pytest.approx(1612.80, abs=0.01)
    # No color rules in breakdown
    assert not any(b["code"].startswith("COLOR_FILM_DIFF") for b in r["breakdown"])


def test_once_per_line_flag_on_unit_scope(product):
    """A rule with scope=unit but once_per_line=true should apply ONCE."""
    rules = [{
        "code": "SETUP_FEE", "conditions": [],
        "formula": "50", "effect_type": "fixed", "priority": 100,
        "application_scope": "unit", "once_per_line": True, "active": True,
    }]
    r = _run(product, rules, 3, config={})
    fee = next(b for b in r["breakdown"] if b["code"] == "SETUP_FEE")
    assert fee["amount"] == pytest.approx(50.0)
    assert fee["scope"] == "line"  # deferred to line pass
    # base * 3 + 50 = 806.40*3 + 50 = 2469.20
    assert r["subtotal_line"] == pytest.approx(2469.20, abs=0.01)


def test_billable_minimum_applied(product):
    """When sqm < min_billable_sqm, billable takes min."""
    p = {**product, "min_billable_sqm": 2.0}
    rules = []
    r = _run(p, rules, 1, config={})
    # sqm = 1.68, but billable = 2.0 → 480*2 = 960
    assert r["billable_sqm"] == pytest.approx(2.0, abs=0.001)
    assert r["subtotal_line"] == pytest.approx(960.0, abs=0.01)


def test_priority_deterministic_order():
    """Rules with same priority sort by created_at then id → deterministic."""
    product = {"base_price": 100.0, "base_type": "piece", "min_billable_sqm": 0}
    rules = [
        {"code": "A", "conditions": [], "formula": "10", "effect_type": "pct", "priority": 100,
         "application_scope": "unit", "active": True, "_id": "aaa", "created_at": "2026-01-01"},
        {"code": "B", "conditions": [], "formula": "5", "effect_type": "pct", "priority": 100,
         "application_scope": "unit", "active": True, "_id": "bbb", "created_at": "2026-01-02"},
    ]
    r = _run(product, rules, 1, config={})
    # A applied first (+10% = 110), then B (+5% on 110 = 5.5) → 115.5
    assert r["subtotal_line"] == pytest.approx(115.5, abs=0.01)


def test_line_scope_pct_on_line_total(product):
    """scope=line pct applies AFTER quantity multiplication."""
    rules = [{
        "code": "LINE_DISC", "conditions": [], "formula": "10",
        "effect_type": "pct", "priority": 200,
        "application_scope": "line", "active": True,
    }]
    r = _run(product, rules, 3, config={})
    # base 806.40 * 3 = 2419.20, then +10% = 2661.12
    assert r["subtotal_line"] == pytest.approx(2661.12, abs=0.01)
