"""Isolated regression tests for cash forecasts; no HTTP, MongoDB, or credentials.

Amounts and dates below are synthetic business examples. Provider mocks in the
composition test supply records only; the real forecast engines do the arithmetic.
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import cash_engine as cash
from app.services import cfo_engine as cfo
from app.services import sustainability_engine as sustainability


TODAY = date(2026, 10, 23)


def day(offset):
    return (TODAY + timedelta(days=offset)).isoformat()


def receivable(amount, status, due=None, *, expected=None):
    return {
        "amount": amount, "status": status, "due_date": due,
        "expected_date": expected, "customer_id": "synthetic-customer",
        "contract_id": "synthetic-contract", "contract_number": "TEST-001",
        "payment_plan_id": "synthetic-plan", "installment_ref": status,
        "days_overdue": 0, "linked": True, "legal_entity_id": "TEST-ENTITY",
        "date_basis": "DUE_DATE_KNOWN",
    }


def payable(amount, due, **extra):
    return {"id": f"synthetic-{amount}", "label": "Synthetic payable", "amount": amount,
            "due_date": due, "category": "FORNITORI", "source": "payable",
            "status": "SCHEDULED", "days_overdue": 0,
            "legal_entity_id": "TEST-ENTITY", **extra}


class Rows:
    """Read-only records for the few Mongo cursor methods used in these tests."""

    def __init__(self, rows):
        self.rows = rows

    def find(self, *args, **kwargs):
        return self

    async def to_list(self, limit):
        return self.rows[:limit]


def test_overdue_claim_is_not_cash_but_remains_collectible_debt():
    claims = [
        receivable(100000, "UNSCHEDULED"),
        receivable(12000, "TRIGGER_EXPECTED", expected=day(10)),
        receivable(5000, "SCHEDULED", day(2)),
        receivable(3000, "OVERDUE", day(-9)),
    ]
    obligations = [payable(18000, day(4))]
    horizon = cash.horizons(2000, TODAY, claims, obligations)
    series = cash.daily_projection(2000, TODAY, claims, obligations)["series"]
    calendar = cfo.build_calendar(2000, TODAY, TODAY, [], [], claims, obligations)
    quality = cash.receivable_quality(claims, TODAY)
    priority = cash.collection_priority(claims, {}, TODAY)

    assert horizon["7d"]["expected_collections"] == 5000
    assert horizon["7d"]["projected_cash"] == -11000
    assert calendar["horizons"]["7d"]["forecast_closing_cash"] == -11000
    assert series[0]["inflows"] == 0
    assert series[7]["projected_cash"] == -11000
    assert quality["total_receivables"] == 120000
    assert quality["collectible_7d"] == 5000
    # Keep the legacy category total distinct from all forecast exclusions.
    assert quality["not_yet_monetizable"] == 112000
    assert priority[0]["status"] == "OVERDUE"
    assert priority[0]["amount"] == 3000
    assert cfo.forecast_exclusions(claims, TODAY)["overdue_receivables"] == 3000
    assert cfo.forecast_exclusions(claims, TODAY)["total"] == 115000


@pytest.mark.parametrize("status,due", [
    ("DUE", None), ("DUE", ""), ("DUE", "not-a-date"),
    ("SCHEDULED", "2026-02-30"), ("SCHEDULED", day(-1)),
    ("DUE", day(-1)), ("OVERDUE", day(2)),
    ("DISPUTED", day(2)), ("UNSCHEDULED", day(2)),
])
def test_unreliable_claim_cannot_enter_any_forecast(status, due):
    claims = [receivable(9999, status, due)]
    projection = cash.daily_projection(700, TODAY, claims, [])
    horizon = cash.horizons(700, TODAY, claims, [])
    calendar = cfo.build_calendar(700, TODAY, TODAY, [], [], claims, [])
    stress = cash.stress_scenario(700, TODAY, claims, [])

    assert all(row["inflows"] == 0 and row["projected_cash"] == 700 for row in projection["series"])
    assert all(row["expected_collections"] == 0 for row in horizon.values())
    assert all(row["inflows"] == 0 and row["closing"] == 700 for row in calendar["weeks"])
    assert stress["cash_7d"] == stress["cash_30d"] == 700
    assert cash.receivable_quality(claims, TODAY)["collectible_30d"] == 0
    assert cfo.forecast_exclusions(claims, TODAY)["total"] == 9999


def test_forecast_exclusions_partition_claims_without_double_counting():
    claims = [
        receivable(10, "OVERDUE", day(-1)),
        receivable(20, "DUE", day(-1)),
        receivable(30, "SCHEDULED", "invalid"),
        receivable(40, "DISPUTED", day(-5)),
        receivable(50, "TRIGGER_EXPECTED", expected=day(-3)),
        receivable(60, "OTHER_STATUS", day(1)),
        receivable(70, "SCHEDULED", day(2)),
    ]
    excluded = cfo.forecast_exclusions(claims, TODAY)
    assert {key: excluded[key] for key in (
        "overdue_receivables", "undated_receivables", "disputed_receivables",
        "trigger_expected_receivables", "other_receivables", "total", "count"
    )} == {
        "overdue_receivables": 30, "undated_receivables": 30,
        "disputed_receivables": 40, "trigger_expected_receivables": 50,
        "other_receivables": 60, "total": 210, "count": 6,
    }
    assert excluded["total"] + cash.horizons(0, TODAY, claims, [])["30d"]["expected_collections"] == 280


def test_13_weeks_daily_and_horizons_share_one_inclusive_end_date():
    claims = [receivable(100, "DUE", day(0)), receivable(200, "SCHEDULED", day(7)),
              receivable(300, "SCHEDULED", day(90)), receivable(9999, "SCHEDULED", day(91))]
    obligations = [payable(50, day(-2)), payable(70, day(90)), payable(9999, day(91))]
    projection = cash.daily_projection(1000, TODAY, claims, obligations)["series"]
    horizon = cash.horizons(1000, TODAY, claims, obligations)
    weeks = cfo.build_calendar(1000, TODAY, TODAY, [], [], claims, obligations)["weeks"]

    assert len(projection) == 91 and len(weeks) == 13
    assert projection[-1]["date"] == weeks[-1]["end"] == day(90)
    assert horizon["today"]["projected_cash"] == 1050
    assert horizon["7d"]["expected_collections"] == 300
    assert projection[-1]["projected_cash"] == weeks[-1]["closing"] == 1480
    assert horizon["13w"]["projected_cash"] == horizon["90d"]["projected_cash"] == 1480
    assert sum(row["inflows"] for row in projection) == sum(row["inflows"] for row in weeks) == 600
    assert sum(row["outflows"] for row in projection) == sum(row["outflows"] for row in weeks) == 120


def test_overdue_payable_remains_an_immediate_requirement_everywhere():
    obligations = [payable(1500, day(-4), status="OVERDUE"), payable(100, day(3))]
    projection = cash.daily_projection(1000, TODAY, [], obligations)
    horizon = cash.horizons(1000, TODAY, [], obligations)
    calendar = cfo.build_calendar(1000, TODAY, TODAY, [], [], [], obligations)
    assert projection["series"][0]["outflows"] == 1500
    assert projection["first_negative_date"] == day(0)
    assert horizon["today"]["projected_cash"] == -500
    assert calendar["weeks"][0]["outflows"] == 1600
    assert calendar["weeks"][0]["closing"] == -600
    assert calendar["first_cash_gap_week"] == "W1"
    assert cash.cash_runway(1000, TODAY, obligations)["days"] == 0


@pytest.mark.parametrize("due", [None, "", "invalid", "2026-02-30"])
def test_unknown_outflow_date_does_not_crash_or_create_a_calendar_date(due):
    obligations = [payable(9999, due)]
    assert cash.daily_projection(100, TODAY, [], obligations)["series"][0]["projected_cash"] == 100
    assert cash.horizons(100, TODAY, [], obligations)["30d"]["expected_outflows"] == 0
    assert cash.cash_runway(100, TODAY, obligations)["days"] == 365
    assert cfo.build_calendar(100, TODAY, TODAY, [], [], [], obligations)["weeks"][0]["closing"] == 100


def test_actual_movements_only_update_cash_after_certification_and_through_today():
    as_of = TODAY - timedelta(days=2)
    receipts = [{"amount": 100, "date": TODAY - timedelta(days=3)},
                {"amount": 200, "date": as_of}, {"amount": 500, "date": TODAY},
                {"amount": 9000, "date": TODAY + timedelta(days=1)}]
    payments = [{"amount": 50, "date": TODAY}, {"amount": 8000, "date": TODAY + timedelta(days=1)}]
    calendar = cfo.build_calendar(1000, as_of, TODAY, receipts, payments, [], [])
    assert calendar["opening_cash"] == 1000
    assert calendar["actual_collections_since_as_of"] == 500
    assert calendar["actual_payments_since_as_of"] == 50
    assert calendar["current_cash_estimate"] == 1450
    assert calendar["horizons"]["today"]["forecast_closing_cash"] == 1450


@pytest.mark.parametrize("opening,as_of", [
    (None, TODAY), (1000, None), (1000, "invalid"), (1000, TODAY + timedelta(days=1))
])
def test_uncertified_or_future_certification_never_becomes_zero_cash(opening, as_of):
    claims = [receivable(500, "SCHEDULED", day(1))]
    calendar = cfo.build_calendar(opening, as_of, TODAY, [], [], claims, [])
    assert calendar["status"] == "INCOMPLETE"
    assert calendar["current_cash_estimate"] is None
    assert calendar["horizons"]["7d"]["inflows"] == 500
    assert calendar["horizons"]["7d"]["forecast_closing_cash"] is None
    assert calendar["weeks"][0]["closing"] is None


def test_certified_zero_is_valid_and_not_confused_with_missing_cash():
    calendar = cfo.build_calendar(0, TODAY, TODAY, [], [], [], [])
    assert calendar["status"] == "COMPLETE"
    assert calendar["current_cash_estimate"] == 0
    assert cash.horizons(None, TODAY, [], [])["today"]["projected_cash"] is None


@pytest.mark.parametrize("certified_amount", [0, 2000])
def test_an_unconfigured_account_keeps_cash_partial_even_if_other_balance_is_zero(certified_amount):
    db = SimpleNamespace(bank_accounts=Rows([
        {"_id": "certified", "certified_balance": certified_amount, "certified_at": day(0)},
        {"_id": "not-certified", "balance": 99999},
    ]), virtual_funds=Rows([]))
    position = asyncio.run(cfo.cash_position(db, "tenant", None))
    assert position["status"] == "PARTIAL"
    assert position["available_cash"] == certified_amount
    assert position["accounts_not_configured"] == 1


def test_different_account_certification_dates_block_an_unreconciled_combined_forecast():
    db = SimpleNamespace(bank_accounts=Rows([
        {"_id": "older", "certified_balance": 1000, "certified_at": day(-2)},
        {"_id": "newer", "certified_balance": 2000, "certified_at": day(0)},
    ]), virtual_funds=Rows([]))
    position = asyncio.run(cfo.cash_position(db, "tenant", None))
    assert position["status"] == "COMPLETE", "Both individual accounts are certified"
    assert position["available_cash"] == 3000
    assert position["certification_dates"] == [day(-2), day(0)]
    assert position["forecast_block_reason"] == "MIXED_CERTIFICATION_DATES"
    assert position["forecast_block_message"]


def test_stress_delays_only_eligible_collections_and_never_resurrects_overdue():
    claims = [receivable(200, "DUE", day(0)), receivable(300, "SCHEDULED", day(1)),
              receivable(9000, "OVERDUE", day(-1))]
    obligations = [payable(750, day(3))]
    stress = cash.stress_scenario(1000, TODAY, claims, obligations, delay_days=7)
    assert cash.horizons(1000, TODAY, claims, obligations)["7d"]["projected_cash"] == 750
    assert stress["cash_7d"] == 450
    assert stress["cash_30d"] == 750
    assert stress["lowest_cash_point"]["amount"] == 250


def test_past_trigger_is_not_carried_forward_and_future_trigger_stays_separate():
    claims = [receivable(1000, "SCHEDULED", day(2)),
              receivable(10000, "TRIGGER_EXPECTED", expected=day(-1)),
              receivable(2000, "TRIGGER_EXPECTED", expected=day(1))]
    horizon = cash.horizons(500, TODAY, claims, [])
    assert horizon["today"]["trigger_expected_collections"] == 0
    assert horizon["7d"]["expected_collections"] == 1000
    assert horizon["7d"]["trigger_expected_collections"] == 2000
    assert horizon["7d"]["projected_cash"] == 1500
    assert horizon["7d"]["projected_cash_with_triggers"] == 3500


@pytest.mark.parametrize("trigger,order_status,event_field", [
    ("goods_ready", "completed", "goods_ready_at"),
    ("installation", "installed", "installed_at"),
])
@pytest.mark.parametrize("event_date,expected_status,eligible", [
    (None, "UNSCHEDULED", False), ("invalid", "UNSCHEDULED", False),
    (day(0), "DUE", True), (day(-1), "DUE", False),
])
def test_operational_trigger_needs_its_own_reliable_event_date(
    trigger, order_status, event_field, event_date, expected_status, eligible
):
    order = {"_id": "order", "contract_id": "contract", "order_status": order_status,
             "updated_at": day(0), event_field: event_date}
    db = SimpleNamespace(sales_orders=Rows([order]))
    plan = {"_id": "plan", "contract_id": "contract", "customer_id": "customer",
            "installments": [{"ref": "I1", "trigger": trigger, "amount": 1000, "paid_amount": 250}]}
    rows = asyncio.run(cfo.expected_collections(db, "tenant", {}, [plan], TODAY))
    assert len(rows) == 1 and rows[0]["amount"] == 750
    assert rows[0]["status"] == expected_status
    assert rows[0]["forecast_eligible"] is eligible
    assert cash.horizons(0, TODAY, rows, [])["7d"]["expected_collections"] == (750 if eligible else 0)
    if event_date in (None, "invalid"):
        assert rows[0]["due_date"] is None, "updated_at must not be used as a collection date"


def test_invalid_explicit_due_date_does_not_fall_back_to_an_event():
    db = SimpleNamespace(sales_orders=Rows([
        {"_id": "order", "contract_id": "contract", "order_status": "completed", "goods_ready_at": day(0)}
    ]))
    plan = {"_id": "plan", "contract_id": "contract", "installments": [
        {"ref": "I1", "trigger": "goods_ready", "due_date": "invalid", "amount": 1000}
    ]}
    row = asyncio.run(cfo.expected_collections(db, "tenant", {}, [plan], TODAY))[0]
    assert row["status"] == "UNSCHEDULED" and row["due_date"] is None
    assert row["date_basis"] == "INVALID_DUE_DATE" and row["forecast_eligible"] is False


@pytest.mark.parametrize("cash_mode", ["COMPLETE", "PARTIAL", "MIXED_DATES"])
def test_cfo_and_command_center_share_base_monthly_forecast_and_exclusions(monkeypatch, cash_mode):
    claims = [receivable(3000, "OVERDUE", day(-4)), receivable(5000, "SCHEDULED", day(2)),
              receivable(100000, "UNSCHEDULED"), receivable(12000, "TRIGGER_EXPECTED", expected=day(10))]
    obligations = [payable(1000, day(-1), status="OVERDUE", days_overdue=1), payable(18000, day(4))]
    receipts = [{"amount": 500, "date": TODAY, "legal_entity_id": "TEST-ENTITY"},
                {"amount": 90000, "date": TODAY + timedelta(days=1), "legal_entity_id": "TEST-ENTITY"}]
    db = SimpleNamespace(payables=Rows([
        {"amount_paid": 100, "paid_at": day(0), "legal_entity_id": "TEST-ENTITY"},
        {"amount_paid": 10000, "paid_at": day(1), "legal_entity_id": "TEST-ENTITY"},
    ]), customers=Rows([]))
    structure = {"fixed_cost_registry": {"annual_total": 0, "demo_annual_total": 0, "reconciliation_status": "COMPLETE"},
                 "plan": {"kpi_status": "COMPLETE", "structure_coverage_percent": 0,
                          "secured_contribution_ytd": 0, "structure_residual": 0,
                          "data_quality": "COMPLETE", "missing": []}}
    providers = {
        "load_settings": {**cfo.DEFAULT_SETTINGS, "configured": True},
        "_contracts": {}, "_plans": [],
        "reconciled_ic_pairs": {"pairs": set(), "reconciled": 0, "unreconciled": 0},
        "cash_receipts_canonical": {"receipts": receipts, "deduplicated_events": 0},
        "expected_collections": claims,
        "expected_outflows": {"items": obligations, "unscheduled": [], "monthly_fixed_costs": 0,
                              "monthly_personnel_costs": 0, "uncategorized_payables": 0,
                              "reconciled_recurring": 0, "purchase_committed": [], "payroll_cash_components_mismatch": []},
        "cash_position": {"available_cash": 2000, "as_of": day(-2),
                          "status": "PARTIAL" if cash_mode == "PARTIAL" else "COMPLETE",
                          "accounts_not_configured": int(cash_mode == "PARTIAL"),
                          "forecast_block_reason": "MIXED_CERTIFICATION_DATES" if cash_mode == "MIXED_DATES" else None,
                          "forecast_block_message": "Certify accounts on one date" if cash_mode == "MIXED_DATES" else None},
        "revenue_block": {"invoiced": {"month": 0, "ytd": 0, "invoice_count": 0, "data_status": "NO_INVOICE_DATA_AVAILABLE"},
                          "sold": {"month": 0, "contracts_legacy_excluded": 0}, "target": {}, "forecast_month": {}},
        "margin_block": {"weighted_contribution_margin_ratio": None, "status": "OK", "margin_sample_size": 0},
    }
    for name, result in providers.items():
        monkeypatch.setattr(cfo, name, AsyncMock(return_value=result))
    monkeypatch.setattr(sustainability, "overview", AsyncMock(return_value=structure))
    monkeypatch.setattr(cash, "job_cash_positions", AsyncMock(return_value={
        "rows": [], "soon": [], "cash_absorbed_by_open_jobs": 0,
    }))

    center = asyncio.run(cash.command_center(db, "tenant", "TEST-ENTITY", TODAY))
    tower = asyncio.run(cfo.overview(db, "tenant", "TEST-ENTITY", TODAY))
    assert center["situation_today"]["certified_cash"] == tower["kpi_row1"]["certified_cash"] == 2000
    expected_base = 2400 if cash_mode == "COMPLETE" else None
    expected_forecast = -11600 if cash_mode == "COMPLETE" else None
    assert center["situation_today"]["current_cash_estimate"] == tower["kpi_row1"]["current_cash_estimate"] == expected_base
    assert center["horizons"]["30d"]["projected_cash"] == tower["cash_calendar"]["30d"]["forecast_closing_cash"] == expected_forecast
    assert center["weeks_13"] == tower["weeks_13"]
    assert center["forecast_exclusions"] == tower["forecast_exclusions"]
    assert tower["forecast_month_end"]["collections"]["scheduled_to_month_end"] == 5000
    assert tower["forecast_month_end"]["collections"]["actual"] == 500
    assert tower["forecast_month_end"]["outflows"]["actual_paid"] == 100
    assert tower["forecast_month_end"]["cash"]["forecast_month_end"] == expected_forecast
    assert tower["payables"]["supplier_due"]["7d"] == 19000
    assert tower["receivables"]["total_residual"] == center["receivable_quality"]["total_receivables"] == 120000
    assert tower["receivables"]["rows"][0]["overdue"] == 3000
    if cash_mode == "MIXED_DATES":
        assert center["situation_today"]["cash_status"] == tower["cash_flow_status"] == "INCOMPLETE"
        assert center["situation_today"]["forecast_block_reason"] == "MIXED_CERTIFICATION_DATES"
        assert any(action["code"] == "MIXED_CERTIFICATION_DATES" for action in center["next_actions"])
        assert any(action["code"] == "MIXED_CERTIFICATION_DATES" for action in tower["next_actions"])
