"""CASH CONVERSION & DEBT COVERAGE ENGINE V1 — PO checklist (DEMO_COST_EXCLUSION, RECONCILIATION, BANK GATE, ORDER_TO_CASH, GOODS_TRIGGER, RECEIVABLE_STATES,
DEBT_LADDER, CASH 7/30/90, 13_WEEK, LOWEST_CASH_POINT, CASH_GAP, RUNWAY, JOB_CASH_POSITION, PEAK_CASH_EXPOSURE, CASH_TERMS_SIMULATOR, NO_FALSE_LIQUIDITY, NO_DOUBLE_COUNTING)."""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from app.services import cash_engine as ce
from app.services import cfo_engine as eng
from app.services import sustainability_engine as sus

TENANT = "5e353147-2416-4ef7-aa3f-3e0007435c42"
TODAY = date(2026, 11, 10)


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def admin():
    from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD
    from tests.test_quote_economic_control_v2 import _login
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


def _coll(amount, status, due=None, expected=None):
    return {"amount": amount, "status": status, "due_date": due, "expected_date": expected, "customer_id": "c", "days_overdue": 0}


def test_no_false_liquidity_only_scheduled_non_past_collections_in_forecast():
    coll = [_coll(100000, "UNSCHEDULED"), _coll(12000, "TRIGGER_EXPECTED", expected="2026-11-20"), _coll(5000, "SCHEDULED", due="2026-11-12"), _coll(3000, "OVERDUE", due="2026-11-01")]
    outf = [{"amount": 18000, "due_date": "2026-11-14", "category": "STIPENDI"}]
    h = ce.horizons(2000.0, TODAY, coll, outf)
    assert h["7d"]["expected_collections"] == 5000 and h["7d"]["trigger_expected_collections"] == 0
    assert h["30d"]["trigger_expected_collections"] == 12000 and h["30d"]["expected_collections"] == 5000
    assert h["7d"]["projected_cash"] == 2000 + 5000 - 18000 == -11000
    q = ce.receivable_quality(coll, TODAY)
    assert q["total_receivables"] == 120000 and q["collectible_7d"] == 5000 and q["not_yet_monetizable"] == 112000
    assert eng.forecast_exclusions(coll, TODAY)["overdue_receivables"] == 3000


def test_cash_gap_operating_vs_safety_reserve_not_configured():
    h = {"expected_collections": 12000, "mandatory_outflows": 27000}
    g = ce.cash_gap(3000.0, h, None)
    assert g["operating_cash_position"] == -12000 and g["operating_cash_gap"] == 12000 and g["safety_cash_gap"] == "NOT_AVAILABLE" and g["reserve_status"] == "NOT_CONFIGURED"
    g2 = ce.cash_gap(3000.0, h, 5000.0)
    assert g2["safety_cash_gap"] == 17000
    assert ce.cash_gap(None, h, None)["status"] == "INCOMPLETE"  # BANK_BALANCE_DATA_GATE


def test_lowest_cash_point_runway_coverage_ladder_13w():
    coll = [_coll(10000, "SCHEDULED", due="2026-11-25")]
    outf = [{"amount": 8000, "due_date": "2026-11-14", "category": "STIPENDI"}, {"amount": 15000, "due_date": "2026-11-28", "category": "FORNITORI"}, {"amount": 2000, "due_date": "2026-12-20", "category": "MARKETING", "priority": "DISCRETIONARY"}]
    p = ce.daily_projection(3000.0, TODAY, coll, outf)
    assert p["lowest_cash_point"] == {"date": "2026-12-20", "amount": -12000.0} and p["first_negative_date"] == "2026-11-14"
    r = ce.cash_runway(3000.0, TODAY, outf)
    assert r["days"] == 4 and r["exhaustion_date"] == "2026-11-14"
    lad = ce.debt_ladder(outf, TODAY)
    assert lad["7d"]["total"] == 8000 and lad["30d"]["total"] == 23000 and lad["60d"]["total"] == 25000 and lad["60d"]["by_priority"]["DISCRETIONARY"] == 2000 and lad["30d"]["mandatory"] == 23000
    h = ce.horizons(3000.0, TODAY, coll, outf)
    cov = ce.liquidity_coverage(3000.0, h["30d"])
    assert cov["available"] == 13000 and cov["mandatory_outflows_30d"] == 23000 and cov["status"] == "CRITICAL" and cov["debt_coverage_gap"] == 10000
    assert h["90d"]["projected_cash"] == 3000 + 10000 - 25000 and "13w" in h
    assert ce.horizons(None, TODAY, coll, outf)["7d"]["projected_cash"] is None


def test_stress_scenario_delays_collections():
    coll = [_coll(10000, "SCHEDULED", due="2026-11-12")]
    outf = [{"amount": 8000, "due_date": "2026-11-14", "category": "STIPENDI"}]
    base = ce.horizons(1000.0, TODAY, coll, outf)["7d"]["projected_cash"]
    st = ce.stress_scenario(1000.0, TODAY, coll, outf, delay_days=7)
    assert base == 3000 and st["cash_7d"] == -7000 and st["kind"] == "SCENARIO"


def test_cash_terms_simulator_and_peak_exposure():
    s = ce.simulate_terms(gross_total=24400, net_total=20000, direct_costs=12000, splits=ce.TERMS_PRESETS["50/50"], lead_days=60, today=TODAY)
    assert s["deposit_received"] == 12200 and s["peak_cash_exposure"] == 0 and s["cash_positive_step"] == "ORDER" and s["exposure_level"] == "LOW"
    s = ce.simulate_terms(gross_total=24400, net_total=20000, direct_costs=12000, splits=ce.TERMS_PRESETS["30/70"], lead_days=60, today=TODAY)
    assert s["deposit_received"] == 7320 and s["peak_cash_exposure"] == 4680 and s["cash_positive_step"] == "GOODS_READY" and s["cash_positive_date"] == (TODAY + timedelta(days=60)).isoformat()
    assert s["exposure_level"] == "MEDIUM"
    s = ce.simulate_terms(gross_total=24400, net_total=20000, direct_costs=12000, splits=ce.TERMS_PRESETS["50/40/10"], lead_days=90, today=TODAY)
    assert s["splits"][2]["step"] == "INSTALLATION" and s["splits"][2]["day"] == 105
    assert ce.simulate_terms(gross_total=1000, net_total=800, direct_costs=None, splits=ce.TERMS_PRESETS["50/50"], lead_days=None)["peak_cash_exposure"] is None


def test_priority_classification_and_confidence():
    assert eng.priority_of({"category": "STIPENDI"}) == "CRITICAL" and eng.priority_of({"category": "F24"}) == "CRITICAL"
    assert eng.priority_of({"category": "FORNITORI"}) == "IMPORTANT" and eng.priority_of({"category": "MARKETING"}) == "DEFERRABLE"
    assert eng.priority_of({"category": "MARKETING", "priority": "DISCRETIONARY"}) == "DISCRETIONARY"
    assert eng.confidence_of("ACTUAL") == "CONFIRMED" and eng.confidence_of("DUE") == "HIGH" and eng.confidence_of("TRIGGER_EXPECTED") == "MEDIUM" and eng.confidence_of("OVERDUE", 45) == "LOW"


def test_order_to_cash_goods_trigger_states_and_job_position():
    async def run():
        db = _db()
        tag = uuid.uuid4().hex[:8]
        cid, pid, cust, soid, qid = f"ctr-{tag}", f"plan-{tag}", f"cust-{tag}", f"so-{tag}", f"q-{tag}"
        now = datetime.now(timezone.utc)
        signed = (TODAY - timedelta(days=20)).isoformat()
        await db.quotes.insert_one({"_id": qid, "tenant_id": TENANT, "deleted_at": None, "subtotal": 20000, "total": 24400, "quote_status": "converted",
                                    "financial_snapshot": {"post_margin_amount": 6000, "post_margin_percent": 30, "net_revenue_ex_vat": 20000, "financial_snapshot_status": "COMPLETE"}})
        await db.contracts.insert_one({"_id": cid, "tenant_id": TENANT, "deleted_at": None, "contract_status": "signed", "signed_at": signed, "number": f"CON-T-{tag}", "quote_id": qid,
                                       "economic_snapshot": {"total": 24400, "subtotal": 20000}, "customer_id": cust, "legal_entity_id": "LE-CASH"})
        await db.payment_plans.insert_one({"_id": pid, "tenant_id": TENANT, "deleted_at": None, "contract_id": cid, "customer_id": cust, "legal_entity_id": "LE-CASH", "total_amount": 24400,
                                           "installments": [{"ref": "I1", "trigger": "signature", "amount": 12200, "paid_amount": 12200, "installment_status": "paid"},
                                                            {"ref": "I2", "trigger": "goods_ready", "amount": 12200, "paid_amount": 0, "installment_status": "pending"}]})
        await db.payments.insert_one({"_id": f"pay-{tag}", "tenant_id": TENANT, "deleted_at": None, "payment_plan_id": pid, "customer_id": cust, "installment_ref": "I1", "amount": 12200, "received_at": now})
        await db.payables.insert_one({"_id": f"pb-{tag}", "tenant_id": TENANT, "deleted_at": None, "label": "Fornitore serramenti", "creditor": "Prod SRL", "due_date": (TODAY + timedelta(days=5)).isoformat(),
                                      "amount_gross": 12000, "amount_paid": 12000, "residual": 0, "payable_status": "paid", "job_ref": cid, "legal_entity_id": "LE-CASH", "category": "FORNITORI"})
        await db.sales_orders.insert_one({"_id": soid, "tenant_id": TENANT, "deleted_at": None, "contract_id": cid, "customer_id": cust, "order_status": "in_production", "updated_at": now.isoformat()})
        try:
            contracts = await eng._contracts(db, TENANT)
            plans = await eng._plans(db, TENANT)
            mine = lambda rows: [c for c in rows if c["payment_plan_id"] == pid]
            # GOODS_ORDERED/IN_PRODUCTION senza data → UNSCHEDULED (nessun cash inflow automatico)
            c = mine(await eng.expected_collections(db, TENANT, contracts, plans, TODAY))[0]
            assert c["status"] == "UNSCHEDULED" and c["due_date"] is None and c["certain"] is False and c["date_basis"] == "GOODS_READY_NOT_OCCURRED"
            # GOODS_EXPECTED date → TRIGGER_EXPECTED (expected_date, mai due_date)
            await db.sales_orders.update_one({"_id": soid}, {"$set": {"expected_ready_date": (TODAY + timedelta(days=10)).isoformat()}})
            c = mine(await eng.expected_collections(db, TENANT, contracts, plans, TODAY))[0]
            assert c["status"] == "TRIGGER_EXPECTED" and c["due_date"] is None and c["expected_date"] == (TODAY + timedelta(days=10)).isoformat() and c["confidence"] == "MEDIUM"
            cc = await ce.command_center(db, TENANT, "LE-CASH", TODAY)
            assert cc["horizons"]["30d"]["trigger_expected_collections"] == 12200 and cc["horizons"]["30d"]["expected_collections"] == 0  # NO FALSE LIQUIDITY
            job = next(j for j in cc["jobs"]["rows"] if j["contract_id"] == cid)
            assert job["order_value"] == 24400 and job["collected"] == 12200 and job["to_collect"] == 12200 and job["supplier_paid"] == 12000 and job["cash_position"] == 200
            assert job["direct_costs_expected"] == 14000 and job["peak_cash_exposure"] == 1800 and job["next_cash_event"]["status"] == "TRIGGER_EXPECTED"
            assert any(r["status"] == "TRIGGER_EXPECTED" and "MERCE IN ARRIVO" in r["reason"] for r in cc["collection_priority"])
            assert cc["situation_today"]["cash_status"] == "INCOMPLETE" and cc["situation_today"]["cash_today"] is None and cc["situation_today"]["cash_gap_30d"]["status"] == "INCOMPLETE"
            # GOODS_READY → saldo DUE (trigger avvenuto, dentro grace) → entra nel forecast certo
            await db.sales_orders.update_one({"_id": soid}, {"$set": {"order_status": "completed", "goods_ready_at": TODAY.isoformat()}})
            c = mine(await eng.expected_collections(db, TENANT, contracts, plans, TODAY))[0]
            assert c["status"] == "DUE" and c["date_basis"] == "EVENT_GOODS_READY" and c["certain"] and c["confidence"] == "HIGH"
            cc = await ce.command_center(db, TENANT, "LE-CASH", TODAY)
            assert cc["horizons"]["7d"]["expected_collections"] == 12200 and cc["receivable_quality"]["by_status"]["DUE"] == 12200
            # oltre grace → OVERDUE
            c = mine(await eng.expected_collections(db, TENANT, contracts, plans, TODAY + timedelta(days=10)))[0]
            assert c["status"] == "OVERDUE" and c["days_overdue"] == 10
            # pagamento → ACTUAL (rata chiusa) → nessun credito residuo
            await db.payment_plans.update_one({"_id": pid}, {"$set": {"installments.1.paid_amount": 12200, "installments.1.installment_status": "paid"}})
            plans = await eng._plans(db, TENANT)
            assert mine(await eng.expected_collections(db, TENANT, contracts, plans, TODAY)) == []
        finally:
            for col, _id in (("contracts", cid), ("payment_plans", pid), ("payments", f"pay-{tag}"), ("sales_orders", soid), ("payables", f"pb-{tag}"), ("quotes", qid)):
                await db[col].delete_one({"_id": _id})
    asyncio.run(run())


def test_demo_cost_exclusion_and_cash_profile_no_double_counting():
    async def run():
        db = _db()
        tag = uuid.uuid4().hex[:8]
        ids = [f"fc-demo-{tag}", f"fc-real-{tag}", f"pc-{tag}"]
        await db.fixed_costs.insert_one({"_id": ids[0], "tenant_id": TENANT, "deleted_at": None, "active": True, "is_demo": True, "label": f"Demo {tag}", "category": "rent", "amount_monthly": 50000, "amount_raw": 50000, "recurrence": "monthly", "legal_entity_id": "LE-CASH"})
        await db.fixed_costs.insert_one({"_id": ids[1], "tenant_id": TENANT, "deleted_at": None, "active": True, "is_demo": False, "label": f"Assicurazione {tag}", "category": "insurance", "amount_monthly": 440, "amount_raw": 5280, "recurrence": "annual",
                                         "legal_entity_id": "LE-CASH", "cash_schedule": {"recurrence": "annual", "due_month": 3, "due_day": 15}})
        await db.personnel_costs.insert_one({"_id": ids[2], "tenant_id": TENANT, "deleted_at": None, "active": True, "is_demo": False, "full_name": f"Dip {tag}", "monthly_total_cost": 4000, "employee_cost_mode": "ALL_IN_COMPANY_COST", "legal_entity_id": "LE-CASH",
                                             "cash_components": [{"label": "NET_SALARY", "amount": 2600, "due_day": 27}, {"label": "F24", "amount": 1400, "due_day": 16, "month_offset": 1}]})
        try:
            reg = await sus.fixed_cost_registry(db, TENANT, "LE-CASH")
            assert reg["real_annual_total"] == 5280 + 48000 and reg["demo_annual_total"] >= 600000 and reg["reconciliation_status"] == "INCOMPLETE" and reg["kpi_status"].startswith("PROVISIONAL")
            assert reg["reconciliation_percent"] == round(53280 / sus.PO_REFERENCE_ANNUAL_FIXED_COST * 100, 2)
            ov = await sus.overview(db, TENANT, "LE-CASH", TODAY)
            assert ov["plan"]["provisional"] is True and ov["plan"]["fixed_cost_basis"] == "PO_REFERENCE_PROVISIONAL" and ov["plan"]["annual_fixed_cost_target"] == sus.PO_REFERENCE_ANNUAL_FIXED_COST
            out = await eng.expected_outflows(db, TENANT, date(2026, 3, 1), horizon_days=120)
            items = [o for o in out["items"] if o.get("legal_entity_id") == "LE-CASH"]
            assert not any(o["label"] == f"Demo {tag}" for o in items), "DEMO escluso dal cash flow"
            ins = [o for o in items if o["label"] == f"Assicurazione {tag}"]
            assert len(ins) == 1 and ins[0]["amount"] == 5280 and ins[0]["due_date"] == "2026-03-15" and ins[0]["economic_monthly"] == 440  # economic 440/mese, cash 5.280 a marzo
            pay = [o for o in items if o["source"] == "personnel_cost" and o["due_date"].startswith("2026-04")]
            assert sorted(o["amount"] for o in pay) == [1400, 2600] and sum(o["amount"] for o in pay) == 4000  # SUM(CASH_COMPONENTS) == ALL-IN, mai 4000 + contributi
            assert out["monthly_personnel_costs"] >= 4000 and out["payroll_cash_components_mismatch"] == []
        finally:
            await db.fixed_costs.delete_many({"_id": {"$in": ids}})
            await db.personnel_costs.delete_many({"_id": {"$in": ids}})
    asyncio.run(run())


def test_api_command_center_and_quote_cash(admin):
    from tests.test_quote_economic_control_v2 import BASE
    cc = admin.get(f"{BASE}/cfo/cash-command-center", timeout=60).json()
    s = cc["situation_today"]
    for k in ("cash_today", "collections_7d", "outflows_7d", "cash_gap_7d", "collections_30d", "outflows_30d", "cash_gap_30d", "total_receivables", "collectible_30d", "debt_position_30d", "lowest_cash_point", "runway", "liquidity_coverage"):
        assert k in s
    assert set(cc["horizons"]) == {"today", "3d", "7d", "14d", "30d", "60d", "90d", "13w"} and len(cc["weeks_13"]) == 13 and len(cc["daily_projection"]) == 91
    assert set(cc["debt"]["ladder"]) == {"7d", "14d", "30d", "60d", "90d"} and "NO_FALSE_LIQUIDITY" in cc["principles"] and cc["email_module"] == "BLOCKED_BY_CONFIGURATION"
    assert "by_status" in cc["receivable_quality"] and isinstance(cc["next_actions"], list) and "net_working_capital" in cc["working_capital"]
    reg = admin.get(f"{BASE}/sustainability/fixed-costs", timeout=30).json()
    assert reg["demo_items"] >= 1 and reg["real_annual_total"] <= reg["po_reference_annual"] and "reconciliation_percent" in reg
    q = admin.get(f"{BASE}/quotes", params={"limit": 5}, timeout=30).json()
    rows = q.get("items") or q
    qid = next((r["id"] for r in rows if r.get("subtotal")), rows[0]["id"])
    r = admin.get(f"{BASE}/cfo/quote/{qid}/cash-exposure", timeout=30)
    assert r.status_code == 200 and "peak_cash_exposure" in r.json() and r.json()["presets"][-1] == "CUSTOM"
    r = admin.post(f"{BASE}/cfo/quote/{qid}/cash-terms-simulate", json={"preset": "30/70"}, timeout=30)
    assert r.status_code == 200 and r.json()["splits"][0]["percent"] == 30 and r.json()["preset"] == "30/70"
    r = admin.post(f"{BASE}/cfo/quote/{qid}/cash-terms-simulate", json={"preset": "CUSTOM", "splits": [{"step": "ORDER", "percent": 20}, {"step": "GOODS_READY", "percent": 70}]}, timeout=30)
    assert r.status_code == 400
    r = admin.post(f"{BASE}/sustainability/fixed-costs/mark-demo", json={"is_demo": True, "ids": ["nonexistent"]}, timeout=30)
    assert r.status_code == 200 and r.json()["fixed_costs_updated"] == 0
