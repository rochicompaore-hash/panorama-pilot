"""CFO CASH & REVENUE CONTROL TOWER V1 — Definition of Done tests (dedup, legacy excluded, cash incomplete, unscheduled, IC, VAT excluded)."""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from app.services import cfo_engine as eng

TENANT = "5e353147-2416-4ef7-aa3f-3e0007435c42"
TODAY = date(2026, 10, 16)


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def admin():
    from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD
    from tests.test_quote_economic_control_v2 import _login
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


def test_contract_economics_legacy_excluded():
    assert eng.contract_economics({"quote_snapshot": {"total": 0}})["flag"] == "LEGACY_ECONOMIC_DATA_INCOMPLETE"
    e = eng.contract_economics({"economic_snapshot": {"total": 12200, "subtotal": 10000}})
    assert e["complete"] and e["net"] == 10000  # IVA esclusa dai ricavi economici


def test_calendar_incomplete_without_certified_cash():
    cal = eng.build_calendar(None, None, TODAY, [], [], [{"amount": 100, "status": "SCHEDULED", "due_date": "2026-10-20"}], [])
    assert cal["status"] == "INCOMPLETE" and cal["horizons"]["7d"]["forecast_closing_cash"] is None and cal["horizons"]["7d"]["inflows"] == 100


def test_calendar_unscheduled_excluded_and_gap_week():
    coll = [{"amount": 1000, "status": "SCHEDULED", "due_date": "2026-10-20"}, {"amount": 9999, "status": "TRIGGER_PENDING", "due_date": None}, {"amount": 5000, "status": "UNSCHEDULED", "due_date": None}]
    outf = [{"amount": 4000, "due_date": "2026-10-28"}]
    cal = eng.build_calendar(2000.0, TODAY - timedelta(days=1), TODAY, [{"amount": 500, "date": TODAY}], [], coll, outf)
    assert cal["current_cash_estimate"] == 2500 and cal["horizons"]["30d"]["inflows"] == 1000
    assert cal["horizons"]["30d"]["forecast_closing_cash"] == -500 and cal["first_cash_gap_week"] == "W2"


def test_aging_on_amount_due_minus_paid():
    a = eng.aging([{"amount": 100, "days_overdue": 3}, {"amount": 200, "days_overdue": 45}, {"amount": 50, "days_overdue": 0}], TODAY)
    assert a["total_overdue"] == 300 and a["buckets"]["1-7"] == 100 and a["buckets"]["31-60"] == 200


def test_simulate():
    s = eng.simulate(revenue=300000, collection_pct=80, margin_pct=27, collection_days=30, monthly_structure=91366.67, available_cash=20000, scheduled_outflows=90000, reserve=50000)
    assert s["collected_expected"] == 240000 and s["break_even_revenue"] == round(91366.67 / 0.27, 2) and s["forecast_cash"] == 170000 and s["cash_gap_vs_reserve"] == 0


def test_receipts_dedup_and_expected_collections_trigger():
    async def run():
        db = _db()
        tag = uuid.uuid4().hex[:8]
        cid, pid, cust = f"ctr-{tag}", f"plan-{tag}", f"cust-{tag}"
        now = datetime.now(timezone.utc)
        await db.contracts.insert_one({"_id": cid, "tenant_id": TENANT, "deleted_at": None, "contract_status": "signed", "signed_at": now.isoformat(), "number": f"CON-T-{tag}",
                                       "economic_snapshot": {"total": 12200, "subtotal": 10000}, "customer_id": cust, "legal_entity_id": "LE-T"})
        await db.payment_plans.insert_one({"_id": pid, "tenant_id": TENANT, "deleted_at": None, "contract_id": cid, "customer_id": cust, "legal_entity_id": "LE-T", "total_amount": 12200,
                                           "installments": [{"ref": "I1", "trigger": "signature", "amount": 6100, "paid_amount": 6100, "installment_status": "paid"},
                                                            {"ref": "I2", "trigger": "goods_ready", "amount": 6100, "paid_amount": 0, "installment_status": "pending"}]})
        await db.payments.insert_one({"_id": f"pay-{tag}", "tenant_id": TENANT, "deleted_at": None, "payment_plan_id": pid, "customer_id": cust, "installment_ref": "I1", "amount": 6100, "received_at": now})
        await db.payments_received.insert_one({"_id": f"pr-{tag}", "tenant_id": TENANT, "deleted_at": None, "contract_id": cid, "installment_ref": "I1", "gross_amount": 6100, "payment_date": now.isoformat(), "customer_id": cust})
        try:
            contracts = await eng._contracts(db, TENANT)
            plans = await eng._plans(db, TENANT)
            canon = await eng.cash_receipts_canonical(db, TENANT, contracts, plans)
            mine = [r for r in canon["receipts"] if r.get("contract_id") == cid]
            assert len(mine) == 1 and canon["deduplicated_events"] >= 1, "stesso evento in due collection deve contare una volta"
            coll = [c for c in await eng.expected_collections(db, TENANT, contracts, plans, TODAY) if c["payment_plan_id"] == pid]
            assert len(coll) == 1 and coll[0]["status"] == "UNSCHEDULED" and coll[0]["due_date"] is None and coll[0]["amount"] == 6100  # goods_ready senza data attendibile
            await db.sales_orders.insert_one({"_id": f"so-{tag}", "tenant_id": TENANT, "deleted_at": None, "contract_id": cid, "order_status": "ready_for_installation", "updated_at": now.isoformat()})
            coll = [c for c in await eng.expected_collections(db, TENANT, contracts, plans, TODAY) if c["payment_plan_id"] == pid]
            assert coll[0]["status"] == "UNSCHEDULED" and coll[0]["date_basis"] == "GOODS_READY_DATE_UNAVAILABLE"
            await db.sales_orders.update_one({"_id": f"so-{tag}"}, {"$set": {"goods_ready_at": TODAY.isoformat()}})
            coll = [c for c in await eng.expected_collections(db, TENANT, contracts, plans, TODAY) if c["payment_plan_id"] == pid]
            assert coll[0]["status"] == "DUE" and coll[0]["date_basis"] == "EVENT_GOODS_READY"
            ov = await eng.overview(db, TENANT, "LE-T", TODAY)
            assert ov["kpi_row1"]["sold_month"] == 10000 and ov["revenue"]["sold"]["contracts_legacy_excluded"] == 0
            assert ov["kpi_row1"]["available_cash"] is None and ov["cash_flow_status"] == "INCOMPLETE"
            group = await eng.overview(db, TENANT, None, TODAY)
            assert group["revenue"]["sold"]["contracts_legacy_excluded"] >= 90 and group["payables"]["intercompany_eliminated"] > 0
        finally:
            for col, _id in (("contracts", cid), ("payment_plans", pid), ("payments", f"pay-{tag}"), ("payments_received", f"pr-{tag}"), ("sales_orders", f"so-{tag}")):
                await db[col].delete_one({"_id": _id})
    asyncio.run(run())


def test_api_overview_settings_and_bank_certification(admin):
    import requests
    from tests.test_quote_economic_control_v2 import BASE
    ov = admin.get(f"{BASE}/cfo/overview", timeout=30).json()
    assert ov["kpi_row1"]["invoiced_status"] == "NO_INVOICE_DATA_AVAILABLE" and ov["dso"] == "NOT_AVAILABLE"
    assert any(q["area"] == "VENDUTO" and "LEGACY" in q["message"] for q in ov["data_quality"])
    r = admin.put(f"{BASE}/cfo/settings", json={"legal_entity_id": "GROUP", "monthly_revenue_target": 300000, "minimum_cash_reserve": 50000, "monthly_collection_target": 200000}, timeout=15)
    assert r.status_code == 200 and r.json()["monthly_revenue_target"] == 300000
    ov = admin.get(f"{BASE}/cfo/overview", timeout=30).json()
    assert ov["kpi_row2"]["revenue_target"]["missing_to_target"] == 300000 and ov["kpi_row2"]["revenue_target"]["percent_reached"] == 0
    acc = ov["cash_position"]["accounts"][0]
    r = admin.post(f"{BASE}/cfo/bank-balance", json={"bank_account_id": acc["id"], "balance": 32540, "as_of_date": "2026-10-16"}, timeout=15)
    assert r.status_code == 200 and r.json()["status"] == "COMPLETE" and r.json()["available_cash"] == 32540
    ov = admin.get(f"{BASE}/cfo/overview", timeout=30).json()
    assert ov["cash_flow_status"] == "COMPLETE" and ov["kpi_row2"]["cash_gap_30d"] is not None and ov["kpi_row3"]["cash_safety_status"] in ("SAFE", "AT_RISK", "BELOW_RESERVE")
    sim = admin.post(f"{BASE}/cfo/simulate", json={"revenue": 300000, "collection_pct": 80}, timeout=30).json()
    assert sim["kind"] == "SIMULATION" and sim["break_even_revenue"] >= 0  # struttura reale = 0 finché i costi fissi demo non sono sostituiti
    assert requests.get(f"{BASE}/cfo/overview", timeout=15).status_code in (401, 403)
