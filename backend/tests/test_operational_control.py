"""Offline domain and API regression tests; never contact customer services."""
import os
for key, value in {"MONGO_URL": "mongodb://localhost:27017", "DB_NAME": "test_operations", "JWT_SECRET": "test-secret-not-for-production", "ADMIN_EMAIL": "admin@example.test", "ADMIN_PASSWORD": "test-only-password", "APP_ENV": "test"}.items():
    os.environ.setdefault(key, value)

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient
from app import deps
from app.routers import operational_control as ops, sales_orders, service_tickets
from app.services import ops_common, audit
from app.services.operational_control import CHECKS, missing_checks, ticket_clock, safe_csv

NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)


def ready_order():
    return {"_id": "order-1", "tenant_id": "tenant-a", "version": 1, "deleted_at": None,
            "number": "ORD-001", "customer_id": "customer-1", "order_status": "draft",
            "operational_enabled": True, "operational_owner_id": "owner-1", "operational_next_action": "Completare verifica",
            "operational_due_at": (NOW + timedelta(days=1)).isoformat(),
            "operational_checks": {k: {"satisfied": True, "evidence": "documento verificato"} for k in CHECKS}}


def test_financing_approval_is_not_signature_or_disbursement():
    order = {**ready_order(), "payment_mode": "financed", "financing_status": "approved"}
    assert missing_checks(order, "confirmed")
    order["financing_status"] = "signed"
    assert not missing_checks(order, "confirmed")
    order["operational_checks"]["admin_order"]["satisfied"] = False
    assert missing_checks(order, "ready_for_production")


def test_materials_and_open_residuals_block_installation_and_closure():
    order = ready_order()
    order["operational_checks"]["materials"]["satisfied"] = False
    assert missing_checks(order, "ready_for_installation")
    order["operational_checks"]["materials"]["satisfied"] = True
    order["operational_residuals"] = 1
    assert missing_checks(order, "closed")
    order["operational_residuals"] = 0
    assert not missing_checks(order, "closed")


@pytest.mark.parametrize("state", ["waiting_material", "waiting_customer", "scheduled"])
def test_waiting_does_not_reset_service_deadline(state):
    ticket = {"priority": "red", "first_reported_at": NOW.isoformat(), "updated_at": (NOW + timedelta(days=5)).isoformat(), "ticket_status": state}
    clock = ticket_clock(ticket, NOW + timedelta(days=3))
    assert clock["due_at"] == (NOW + timedelta(hours=48)).isoformat()
    assert clock["overdue"]


def test_escalation_preserves_origin_and_earliest_deadline():
    ticket = {"priority": "green", "created_at": (NOW - timedelta(days=20)).isoformat()}
    clock = ticket_clock(ticket, NOW, "red")
    assert clock["due_at"] == (NOW + timedelta(hours=48)).isoformat()
    assert clock["first_reported_at"] == ticket["created_at"]
    ticket.update(priority="red", service_due_at=clock["due_at"])
    assert ticket_clock(ticket, NOW + timedelta(hours=1))["due_at"] == clock["due_at"]
    assert ticket_clock(ticket, NOW + timedelta(hours=1), "red")["due_at"] == clock["due_at"]
    assert ticket_clock(ticket, NOW, "green")["due_at"] == clock["due_at"]


def test_missing_origin_is_visible_and_not_invented():
    assert ticket_clock({"updated_at": NOW.isoformat()}, NOW)["missing_origin"]


@pytest.mark.parametrize("value", ["=HYPERLINK(1)", " +1", "@sum(1)", "-2", "\tformula"])
def test_csv_formula_injection_is_neutralized(value):
    assert safe_csv(value).startswith("'")


@pytest.fixture
def environment(monkeypatch):
    db = AsyncMongoMockClient()["operations"]
    user = {"id": "operator-1", "tenant_id": "tenant-a", "email": "operator@example.test", "permissions": ["*"]}
    for module in (ops, sales_orders, service_tickets, ops_common, audit, deps):
        monkeypatch.setattr(module, "get_db", lambda: db)
    async def permissions(current):
        return current["permissions"]
    monkeypatch.setattr(deps, "get_permission_keys_for_user", permissions)
    monkeypatch.setattr(ops, "get_permission_keys_for_user", permissions)
    app = FastAPI()
    app.dependency_overrides[deps.get_current_user] = lambda: user
    for router in (ops.router, sales_orders.router, service_tickets.router):
        app.include_router(router, prefix="/api")
    return db, user, app


async def seed(db):
    await db.sales_orders.insert_one(ready_order())
    await db.users.insert_one({"_id": "owner-1", "tenant_id": "tenant-a", "deleted_at": None, "is_active": True})


@pytest.mark.asyncio
async def test_legacy_status_endpoint_cannot_bypass_checks(environment):
    db, _, app = environment
    order = ready_order(); order["operational_checks"] = {}
    await db.sales_orders.insert_one(order)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/sales-orders/order-1/status", json={"order_status": "confirmed", "expected_version": 1})
        assert r.status_code == 409
        assert r.json()["detail"]["missing"]
    assert (await db.sales_orders.find_one({"_id": "order-1"}))["order_status"] == "draft"


@pytest.mark.asyncio
async def test_valid_transition_records_actor_and_rejects_stale_write(environment):
    db, _, app = environment; await seed(db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/sales-orders/order-1/status", json={"order_status": "confirmed", "expected_version": 1})
        assert r.status_code == 200, r.text
        assert r.json()["version"] == 2
        stale = await c.post("/api/operations/orders/order-1/checks", json={"key": "contract", "satisfied": False, "evidence": "revisione necessaria", "version": 1})
        assert stale.status_code == 409
    stored = await db.sales_orders.find_one({"_id": "order-1"})
    assert stored["operational_history"][0]["actor_id"] == "operator-1"
    assert stored["operational_checks"]["contract"]["satisfied"]


@pytest.mark.asyncio
async def test_other_tenant_is_not_readable_or_exported(environment):
    db, _, app = environment; await seed(db)
    other = {**ready_order(), "_id": "other-order", "tenant_id": "tenant-b", "number": "PRIVATE-OTHER"}
    await db.sales_orders.insert_one(other)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/api/operations/orders/other-order")).status_code == 404
        r = await c.get("/api/operations/export?format=json")
        assert r.status_code == 200
        assert len(r.json()) == 1 and "PRIVATE-OTHER" not in r.text


@pytest.mark.asyncio
async def test_department_permissions_enforced(environment):
    db, user, app = environment; await seed(db)
    user["permissions"] = ["sales_orders.view", "sales_orders.edit"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/operations/orders/order-1/checks", json={"key": "technical", "satisfied": True, "evidence": "documento tecnico", "version": 1})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_assignment_must_belong_to_same_tenant(environment):
    db, _, app = environment; await seed(db)
    await db.users.insert_one({"_id": "foreign", "tenant_id": "tenant-b", "is_active": True})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.put("/api/operations/orders/order-1/plan", json={"version": 1, "owner_id": "foreign", "next_action": "Controllare", "due_at": NOW.isoformat()})
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_finance_change_invalidates_prior_clearances(environment):
    db, _, app = environment; await seed(db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.put("/api/operations/orders/order-1/finance", json={"version": 1, "payment_mode": "financed", "financing_status": "signed", "evidence": "contratto finanziamento"})
        assert r.status_code == 200, r.text
        assert not r.json()["operational_checks"]["admin_survey"]["satisfied"]


@pytest.mark.asyncio
async def test_ticket_patch_cannot_overwrite_tenant_status_or_origin(environment):
    db, _, app = environment
    await db.service_tickets.insert_one({"_id": "ticket-1", "tenant_id": "tenant-a", "version": 1, "created_at": NOW.isoformat(), "priority": "red", "ticket_status": "waiting_material"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for field in ("tenant_id", "first_reported_at", "service_due_at", "ticket_status"):
            r = await c.patch("/api/service-tickets/ticket-1", json={"version": 1, field: "changed"})
            assert r.status_code == 422
        r = await c.patch("/api/service-tickets/ticket-1", json={"version": 1, "next_action": "Sollecitare ricambio"})
        assert r.status_code == 200, r.text
        assert r.json()["service_clock"]["due_at"] == (NOW + timedelta(hours=48)).isoformat()


@pytest.mark.asyncio
async def test_invalid_financing_state_and_naive_deadline_rejected(environment):
    db, _, app = environment; await seed(db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.put("/api/operations/orders/order-1/finance", json={"version": 1, "payment_mode": "standard", "financing_status": "disbursed", "evidence": "riscontro"})
        assert r.status_code == 422
        r = await c.put("/api/operations/orders/order-1/plan", json={"version": 1, "owner_id": "owner-1", "next_action": "Verificare", "due_at": "2026-11-14T10:00:00"})
        assert r.status_code == 422

@pytest.mark.asyncio
async def test_new_order_is_managed_and_customer_must_belong_to_tenant(environment, monkeypatch):
    db, _, app = environment
    monkeypatch.setattr(sales_orders, "record_activity", AsyncMock())
    await db.customers.insert_one({"_id": "own", "tenant_id": "tenant-a"})
    await db.customers.insert_one({"_id": "foreign", "tenant_id": "tenant-b"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.post("/api/sales-orders", json={"customer_id": "foreign"})).status_code == 422
        r = await c.post("/api/sales-orders", json={"customer_id": "own"})
        assert r.status_code == 200, r.text
        assert r.json()["operational_enabled"]
        assert missing_checks(r.json(), "confirmed")


@pytest.mark.asyncio
async def test_order_revision_invalidates_dependent_checks(environment):
    db, _, app = environment; await seed(db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch("/api/sales-orders/order-1", json={"expected_version": 1, "site_address": {"city": "Test"}})
        assert r.status_code == 200, r.text
        for key in ("contract", "technical", "admin_order", "materials", "admin_install", "resources", "acceptance", "documents", "admin_close"):
            assert not r.json()["operational_checks"][key]["satisfied"]
        assert r.json()["operational_checks"]["admin_survey"]["satisfied"]


@pytest.mark.asyncio
async def test_export_is_not_truncated_by_page_and_escapes_csv(environment):
    db, _, app = environment
    await db.sales_orders.insert_many([{**ready_order(), "_id": f"order-{i}", "operational_next_action": "=FORMULA()"} for i in range(121)])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        page = (await c.get("/api/operations/orders?limit=50")).json()
        assert len(page["items"]) == 50 and page["total"] == 121
        assert len((await c.get("/api/operations/export?format=json")).json()) == 121
        csv = await c.get("/api/operations/export?format=csv")
        assert csv.text.count("'=FORMULA()") == 121
        assert csv.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_ticket_creation_uses_actual_report_and_rejects_foreign_customer(environment):
    db, _, app = environment
    await db.customers.insert_one({"_id": "own", "tenant_id": "tenant-a"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        payload = {"customer_id": "own", "subject": "Richiesta di prova", "priority": "red", "first_reported_at": "2026-01-01T10:00:00Z"}
        r = await c.post("/api/service-tickets", json=payload)
        assert r.status_code == 200, r.text
        assert ticket_clock(r.json())["due_at"] == "2026-01-03T10:00:00+00:00"
        payload["customer_id"] = "foreign"
        assert (await c.post("/api/service-tickets", json=payload)).status_code == 422


@pytest.mark.asyncio
async def test_ticket_closure_requires_result_and_keeps_deadline(environment, monkeypatch):
    import sys
    from types import ModuleType
    notifications = ModuleType("app.services.customer_email_events")
    notifications.notify_customer_event = AsyncMock()
    monkeypatch.setitem(sys.modules, "app.services.customer_email_events", notifications)
    db, _, app = environment
    await db.service_tickets.insert_one({"_id": "ticket-1", "tenant_id": "tenant-a", "version": 1, "created_at": NOW.isoformat(), "priority": "orange", "ticket_status": "in_progress"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.post("/api/service-tickets/ticket-1/status", json={"ticket_status": "closed", "expected_version": 1})).status_code == 422
        r = await c.post("/api/service-tickets/ticket-1/status", json={"ticket_status": "closed", "expected_version": 1, "resolution": "Ricambio installato e prova conclusa"})
        assert r.status_code == 200, r.text
        assert r.json()["version"] == 2
        assert ticket_clock(r.json())["due_at"] == (NOW + timedelta(days=15)).isoformat()
        notifications.notify_customer_event.assert_awaited_once()

@pytest.mark.asyncio
async def test_role_permissions_do_not_cross_tenant(monkeypatch):
    db = AsyncMongoMockClient()["roles"]
    monkeypatch.setattr(deps, "get_db", lambda: db)
    await db.roles.insert_many([
        {"_id": "own-role", "tenant_id": "tenant-a", "permission_keys": ["sales_orders.view"]},
        {"_id": "other-role", "tenant_id": "tenant-b", "permission_keys": ["*"]},
    ])
    permissions = await deps.get_permission_keys_for_user({"tenant_id": "tenant-a", "role_ids": ["own-role", "other-role"]})
    assert permissions == ["sales_orders.view"]
