"""CUSTOMER EMAIL NOTIFICATIONS V1 (PO msg 794) — routing/recipient/idempotency/isolation su provider MOCK."""
from __future__ import annotations
import asyncio
import os
import uuid

import pytest
import requests

from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
TENANT = "5e353147-2416-4ef7-aa3f-3e0007435c42"


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def h():
    r = requests.post(f"{BASE}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}); r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def customers():
    """Due clienti TEST con email distinte (A, B) — nessun cliente reale."""
    async def run():
        db = _db()
        ids = []
        for tag in ("a", "b"):
            cid = str(uuid.uuid4())
            await db.customers.insert_one({"_id": cid, "tenant_id": TENANT, "first_name": f"Cust{tag.upper()}", "last_name": "Test", "email": f"reg-cust{tag}-{cid[:6]}@example.com",
                                           "phone": "+39 333 0000000", "customer_type": "private", "status": "active", "deleted_at": None, "created_at": "2026-01-01T00:00:00+00:00"})
            ids.append(cid)
        return ids
    ids = asyncio.run(run())
    yield ids
    async def clean():
        db = _db()
        await db.customers.delete_many({"_id": {"$in": ids}})
        await db.quotes.delete_many({"customer_id": {"$in": ids}})
        await db.service_tickets.delete_many({"customer_id": {"$in": ids}})
        await db.sites.delete_many({"customer_id": {"$in": ids}})
        await db.email_logs.delete_many({"customer_id": {"$in": ids}})
    asyncio.run(clean())


def _logs(customer_id, event_type):
    async def run():
        return await _db().email_logs.find({"customer_id": customer_id, "event_type": event_type}).to_list(50)
    return asyncio.run(run())


def test_support_status_change_emails_customer_but_internal_patch_does_not(h, customers):
    ca, cb = customers
    r = requests.post(f"{BASE}/service-tickets", json={"customer_id": ca, "subject": "Finestra non chiude", "description": "test", "priority": "normal"}, headers=h)
    assert r.status_code in (200, 201), r.text
    tid = r.json()["id"]
    # PATCH con note interne -> ZERO email
    r = requests.patch(f"{BASE}/service-tickets/{tid}", json={"internal_notes": "nota interna riservata", "notes": "commento operatore"}, headers=h)
    assert r.status_code == 200, r.text
    assert _logs(ca, "SUPPORT_UPDATED") == []
    # cambio stato customer-facing -> 1 email al cliente A (mai B), brand tenant, nessun dato interno
    r = requests.post(f"{BASE}/service-tickets/{tid}/status", json={"ticket_status": "triaged"}, headers=h)
    assert r.status_code == 200, r.text
    logs = _logs(ca, "SUPPORT_UPDATED")
    assert len(logs) == 1 and logs[0]["original_to"].startswith("reg-custa-") and logs[0]["entity_id"] == tid and logs[0]["tenant_id"] == TENANT
    assert "Infissi Express" in logs[0]["subject"] and "nota interna" not in (logs[0].get("stored_html") or "")
    assert logs[0]["status"] in ("sent", "test_intercepted", "configuration_required")  # MOCK: mai 'delivered'
    assert _logs(cb, "SUPPORT_UPDATED") == []
    # stesso evento riprocessato (stesso stato) -> idempotente: nessuna seconda email
    requests.post(f"{BASE}/service-tickets/{tid}/status", json={"ticket_status": "triaged"}, headers=h)
    assert len(_logs(ca, "SUPPORT_UPDATED")) == 1


def test_quote_document_and_order_status_emails(h, customers):
    ca, cb = customers
    site = requests.post(f"{BASE}/sites", json={"name": "Cantiere email", "address": "Via Roma", "street_number": "10", "postal_code": "20100", "city": "Milano",
                                              "province": "MI", "floor": "1", "has_elevator": True, "site_contact_phone": "3331234567", "customer_id": ca}, headers=h).json()
    q = requests.post(f"{BASE}/quotes", json={"title": "Email events", "customer_id": ca, "site_id": site["id"]}, headers=h).json(); qid = q["id"]
    op = requests.post(f"{BASE}/quotes/{qid}/openings", json={"code": "V1", "room": "Cucina", "width_mm": 1200, "height_mm": 1400}, headers=h).json()
    cfg = {"window_type": "WINDOW", "number_of_sashes": 2, "width_mm": 1200, "height_mm": 1400, "color_mode": "WHITE_MASS", "color_internal": "003", "color_external": "003",
           "color_internal_name": "BIANCO MASSA", "color_external_name": "BIANCO MASSA", "glass_type": "DOUBLE_SATIN", "opening_configuration": "ANTA_RIBALTA", "quantity": 1}
    line = {"opening_id": op["id"], "category": "finestre", "product_key": "PROEVOLUTION", "quantity": 1, "width_mm": 1200, "height_mm": 1400, "base_price": 1, "unit_price_final": 1,
            "subtotal_line": 1, "description": "ProEvolution", "source": "MULTI_CATEGORY_V1", "category_code": "FINESTRE", "product_id": "8e1cafd0-9707-47c7-8939-b97c9a404021",
            "product_code": "PROEVOLUTION", "pricing_model": "FORMULA_TECHNICAL", "configuration_snapshot": cfg}
    assert requests.post(f"{BASE}/quotes/{qid}/lines", json=line, headers=h).status_code == 200
    requests.patch(f"{BASE}/quotes/{qid}", json={"installation_mode": "SUPPLY_AND_INSTALLATION", "dismantling_mode": "INCLUDED", "disposal_mode": "EXCLUDED", "payment_terms": "DEPOSIT_50_BALANCE_50"}, headers=h)
    # DOCUMENT_AVAILABLE: PDF definitivo (preview NON notifica)
    assert requests.post(f"{BASE}/quotes/{qid}/pdf/preview", json={}, headers=h).status_code == 200
    assert _logs(ca, "DOCUMENT_AVAILABLE") == []
    r = requests.post(f"{BASE}/quotes/{qid}/pdf/generate", json={}, headers=h); assert r.status_code == 200, r.text
    logs = _logs(ca, "DOCUMENT_AVAILABLE")
    assert len(logs) == 1 and logs[0]["entity_type"] == "quote_pdf" and "Nuovo documento disponibile" in logs[0]["subject"]
    assert "customer-portal" in (logs[0].get("stored_html") or "") and "supply_cost" not in (logs[0].get("stored_html") or "").lower() and "margin_pct" not in (logs[0].get("stored_html") or "")
    requests.post(f"{BASE}/quotes/{qid}/pdf/generate", json={}, headers=h)  # idempotent hit -> nessuna nuova email
    assert len(_logs(ca, "DOCUMENT_AVAILABLE")) == 1
    # ORDER_STATUS_CHANGED: solo stati customer-facing (sent NO, accepted SI)
    assert requests.post(f"{BASE}/quotes/{qid}/status", json={"new_status": "sent"}, headers=h).status_code == 200
    assert _logs(ca, "ORDER_STATUS_CHANGED") == []
    assert requests.post(f"{BASE}/quotes/{qid}/status", json={"new_status": "accepted"}, headers=h).status_code == 200
    logs = _logs(ca, "ORDER_STATUS_CHANGED")
    assert len(logs) == 1 and "Preventivo accettato" in logs[0]["subject"] and logs[0]["original_to"].startswith("reg-custa-")
    assert _logs(cb, "ORDER_STATUS_CHANGED") == [] and _logs(cb, "DOCUMENT_AVAILABLE") == []
    # CONTRACT_AVAILABLE: send-for-signature -> destinatario risolto server-side (NON quello del body)
    c = requests.post(f"{BASE}/contracts/generate-from-quote", json={"quote_id": qid}, headers=h).json(); cid = c["id"]
    for st in ("ready_for_review", "ready_for_signature"):
        assert requests.post(f"{BASE}/contracts/{cid}/transition", json={"to_state": st}, headers=h).status_code == 200
    r = requests.post(f"{BASE}/contracts/{cid}/send-for-signature", json={"to_email": "attacker@example.com"}, headers=h); assert r.status_code == 200, r.text
    logs = _logs(ca, "CONTRACT_AVAILABLE")
    assert len(logs) == 1 and logs[0]["original_to"].startswith("reg-custa-") and "attacker" not in logs[0]["original_to"]
    assert r.json()["signing_token"][:12] in (logs[0].get("stored_html") or "") and "Visualizza documento" in logs[0]["stored_html"]
    for l in logs:
        assert "password" not in str(l).lower() or "password_hash" not in str(l)
    async def _del():
        await _db().contracts.delete_one({"_id": cid})
    asyncio.run(_del())
