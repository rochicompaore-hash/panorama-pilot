"""Operational event timestamps: real handlers with in-memory persistence doubles.

Router imports substitute database/auth providers, so these tests cannot initialize
a Mongo client, load runtime credentials, or execute a real authenticated request.
"""
from __future__ import annotations

import asyncio
import importlib
import sys
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models_ops import sales_order_event_timestamps


OCCURRED_AT = datetime(2026, 10, 23, 10, 30, tzinfo=timezone.utc)
USER = {"id": "test-user", "tenant_id": "test-tenant", "email": "operator@example.invalid"}


@pytest.mark.parametrize("current,target,field", [
    ("in_production", "completed", "goods_ready_at"),
    ("ready_for_installation", "installed", "installed_at"),
    ("completed", "installed", "installed_at"),
    ("in_production", "installed", "installed_at"),
])
def test_observed_operational_transition_records_only_its_event(current, target, field):
    assert sales_order_event_timestamps({"order_status": current}, target, OCCURRED_AT) == {
        field: OCCURRED_AT.isoformat()
    }


@pytest.mark.parametrize("current,target", [
    ("completed", "ready_for_installation"), ("completed", "completed"),
    ("installed", "installed"), ("installed", "closed"), ("draft", "confirmed"),
])
def test_later_or_repeated_transition_does_not_backfill_historical_dates(current, target):
    assert sales_order_event_timestamps({"order_status": current}, target, OCCURRED_AT) == {}


@pytest.mark.parametrize("field,current,target", [
    ("goods_ready_at", "in_production", "completed"),
    ("installed_at", "ready_for_installation", "installed"),
])
def test_existing_event_timestamp_is_preserved(field, current, target):
    existing = {"order_status": current, field: "2026-10-20T09:00:00+00:00"}
    assert sales_order_event_timestamps(existing, target, OCCURRED_AT) == {}
    assert existing[field] == "2026-10-20T09:00:00+00:00"


@pytest.fixture(scope="module")
def operation_routes():
    def unavailable_db():
        raise AssertionError("Every persistence call must use a local test double")

    async def unavailable_auth():
        raise AssertionError("These are isolated handler tests, not live authentication")

    db_module = ModuleType("app.db")
    db_module.get_db = unavailable_db
    deps_module = ModuleType("app.deps")
    deps_module.require_permission = lambda permission: unavailable_auth
    deps_module.get_client_ip = lambda request: None
    patcher = pytest.MonkeyPatch()
    patcher.setitem(sys.modules, "app.db", db_module)
    patcher.setitem(sys.modules, "app.deps", deps_module)
    try:
        yield (importlib.import_module("app.routers.sales_orders"),
               importlib.import_module("app.routers.logistics"))
    finally:
        patcher.undo()


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return OCCURRED_AT


@pytest.mark.parametrize("current,target,expected_field", [
    ("in_production", "completed", "goods_ready_at"),
    ("ready_for_installation", "installed", "installed_at"),
    ("completed", "ready_for_installation", None),
    ("completed", "completed", None),
])
def test_status_handler_persists_timestamps_only_for_a_new_event(
    operation_routes, monkeypatch, current, target, expected_field
):
    sales, _ = operation_routes
    db = SimpleNamespace(sales_orders=SimpleNamespace(find_one=AsyncMock(return_value={
        "_id": "order", "order_status": current,
    })))
    update = AsyncMock(return_value={"id": "order"})
    monkeypatch.setattr(sales, "get_db", lambda: db)
    monkeypatch.setattr(sales, "update_doc", update)
    monkeypatch.setattr(sales, "datetime", FixedClock)
    asyncio.run(sales.change_status("order", sales.StatusChange(order_status=target), None, USER))
    changes = update.await_args.kwargs["updates"]
    expected = {"order_status": target}
    if expected_field:
        expected[expected_field] = OCCURRED_AT.isoformat()
    assert changes == expected
    assert db.sales_orders.find_one.await_args.args[0]["tenant_id"] == USER["tenant_id"]


def test_editing_notes_does_not_manufacture_operational_dates(operation_routes, monkeypatch):
    sales, _ = operation_routes
    db = SimpleNamespace(sales_orders=SimpleNamespace(find_one=AsyncMock(return_value={
        "_id": "order", "order_status": "completed", "updated_at": "2026-10-01T09:00:00+00:00",
    })))
    update = AsyncMock(return_value={"id": "order"})
    monkeypatch.setattr(sales, "get_db", lambda: db)
    monkeypatch.setattr(sales, "update_doc", update)
    asyncio.run(sales.patch_order("order", sales.SalesOrderPatch(notes="Note aggiornate"), None, USER))
    assert update.await_args.kwargs["updates"] == {"notes": "Note aggiornate"}


@pytest.mark.parametrize("existing_installed_at", [None, "2026-10-20T09:00:00+00:00"])
def test_completed_installation_report_records_first_installation_and_preserves_existing_date(
    operation_routes, monkeypatch, existing_installed_at
):
    _, logistics = operation_routes
    existing = {"_id": "order", "order_status": "ready_for_installation", "installed_at": existing_installed_at}
    order_store = SimpleNamespace(find_one=AsyncMock(return_value=existing), update_one=AsyncMock())
    db = SimpleNamespace(sales_orders=order_store, installation_plans=SimpleNamespace(update_one=AsyncMock()))
    update = AsyncMock(return_value={"id": "report", "installation_plan_id": "plan", "sales_order_id": "order"})
    monkeypatch.setattr(logistics, "get_db", lambda: db)
    monkeypatch.setattr(logistics, "update_doc", update)
    monkeypatch.setattr(logistics, "record_activity", AsyncMock())
    monkeypatch.setattr(logistics, "datetime", FixedClock)
    asyncio.run(logistics.submit_report("report", logistics.ReportSubmit(outcome="completed"), None, USER))

    order_filter, mutation = order_store.update_one.await_args.args
    assert order_filter["tenant_id"] == USER["tenant_id"] and order_filter["deleted_at"] is None
    assert order_filter["order_status"]["$in"] == ["ready_for_installation", "in_production", "completed"]
    assert mutation["$set"]["order_status"] == "installed"
    if existing_installed_at is None:
        assert mutation["$set"]["installed_at"] == OCCURRED_AT.isoformat()
    else:
        assert "installed_at" not in mutation["$set"]
    assert update.await_args.kwargs["updates"]["check_out_at"] == OCCURRED_AT.isoformat()


def test_resubmitted_report_does_not_backfill_already_installed_order(operation_routes, monkeypatch):
    _, logistics = operation_routes
    order_store = SimpleNamespace(find_one=AsyncMock(return_value=None), update_one=AsyncMock())
    db = SimpleNamespace(sales_orders=order_store, installation_plans=SimpleNamespace(update_one=AsyncMock()))
    monkeypatch.setattr(logistics, "get_db", lambda: db)
    monkeypatch.setattr(logistics, "update_doc", AsyncMock(return_value={
        "id": "report", "installation_plan_id": "plan", "sales_order_id": "order",
    }))
    monkeypatch.setattr(logistics, "record_activity", AsyncMock())
    asyncio.run(logistics.submit_report("report", logistics.ReportSubmit(outcome="completed"), None, USER))
    order_store.update_one.assert_not_awaited()


def test_partial_report_does_not_mark_installation_completed(operation_routes, monkeypatch):
    _, logistics = operation_routes
    db_getter = AsyncMock(side_effect=AssertionError("No operational mutation is expected"))
    monkeypatch.setattr(logistics, "get_db", db_getter)
    monkeypatch.setattr(logistics, "update_doc", AsyncMock(return_value={"id": "report"}))
    asyncio.run(logistics.submit_report("report", logistics.ReportSubmit(outcome="partial"), None, USER))
    db_getter.assert_not_called()
