"""CUSTOMER PORTAL CORE V1 — Lotto 1 auth + isolation, Lotto 2 job view + visual, documenti, ticket."""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest
import requests
from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
WINDOW_PID = "8e1cafd0-9707-47c7-8939-b97c9a404021"
LEAK_KEYS = {"internal_cost", "margin", "technical_snapshot", "financial_snapshot", "pricing_snapshot", "commercial_snapshot",
             "simple_snapshot", "supply_cost", "commission", "notes_internal", "internal_reference_price", "pre_commission_margin", "automatic_services"}


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro_fn):
    """Esegue una coroutine-factory (db creato dentro il loop: motor richiede un event loop attivo)."""
    async def _w():
        return await coro_fn(_db())
    return asyncio.run(_w())


@pytest.fixture(scope="module")
def admin():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    d = r.json()
    return {"Authorization": f"Bearer {d.get('access_token') or d.get('token')}"}


def _mk_customer_with_job(admin, tag):
    c = requests.post(f"{BASE_URL}/api/customers", json={"first_name": f"CP{tag}", "last_name": "Test", "email": f"cp{tag}-{uuid.uuid4().hex[:6]}@test.it", "customer_type": "private"}, headers=admin)
    assert c.status_code in (200, 201), c.text
    cid = c.json()["id"]
    q = requests.post(f"{BASE_URL}/api/quotes", json={"title": f"Job {tag}", "customer_id": cid}, headers=admin).json()
    cfg = {"window_type": "WINDOW", "number_of_sashes": 2, "width_mm": 1200, "height_mm": 1400, "color_internal": "003", "color_external": "110",
           "glass_type": "DOUBLE_STANDARD", "opening_configuration": "ANTA_RIBALTA", "quantity": 1}
    r = requests.post(f"{BASE_URL}/api/quotes/{q['id']}/lines", json={"category": "finestre", "product_key": "PROEVOLUTION", "quantity": 1, "width_mm": 1200, "height_mm": 1400,
        "base_price": 1, "unit_price_final": 1, "subtotal_line": 1, "description": f"Finestra {tag}", "source": "MULTI_CATEGORY_V1", "category_code": "FINESTRE",
        "product_id": WINDOW_PID, "product_code": "PROEVOLUTION", "pricing_model": "FORMULA_TECHNICAL", "configuration_snapshot": cfg}, headers=admin)
    assert r.status_code == 200, r.text
    pdf = requests.post(f"{BASE_URL}/api/quotes/{q['id']}/pdf/generate", json={"force": True}, headers=admin)
    pdf_id = pdf.json().get("id") if pdf.status_code == 200 else None
    _run(lambda db: db.quotes.update_one({"_id": q["id"]}, {"$set": {"quote_status": "accepted"}}))
    return cid, q["id"], pdf_id


@pytest.fixture(scope="module")
def world(admin):
    a_cid, a_qid, a_pdf = _mk_customer_with_job(admin, "A")
    b_cid, b_qid, b_pdf = _mk_customer_with_job(admin, "B")
    users = {}
    for tag, cid in (("A", a_cid), ("B", b_cid)):
        email = f"portal-{tag.lower()}-{uuid.uuid4().hex[:6]}@test.it"
        r = requests.post(f"{BASE_URL}/api/admin/customer-portal/users", json={"customer_id": cid, "email": email, "password": "Cliente!2026", "first_name": tag}, headers=admin)
        assert r.status_code == 201, r.text
        lg = requests.post(f"{BASE_URL}/api/customer-portal/auth/login", json={"email": email, "password": "Cliente!2026"})
        assert lg.status_code == 200, lg.text
        users[tag] = {"h": {"Authorization": f"Bearer {lg.json()['access_token']}"}, "email": email}
    yield {"A": {**users["A"], "cid": a_cid, "qid": a_qid, "pdf": a_pdf}, "B": {**users["B"], "cid": b_cid, "qid": b_qid, "pdf": b_pdf}}
    for qid in (a_qid, b_qid):
        _run(lambda db: db.quotes.update_one({"_id": qid}, {"$set": {"quote_status": "draft"}}))
        requests.delete(f"{BASE_URL}/api/quotes/{qid}", headers=admin)


def test_register_pending_and_login_blocked():
    tenant = _run(lambda db: db.quotes.find_one({}))["tenant_id"]
    email = f"self-{uuid.uuid4().hex[:6]}@test.it"
    r = requests.post(f"{BASE_URL}/api/customer-portal/auth/register", json={"tenant_id": tenant, "email": email, "password": "Password!1", "first_name": "Self", "last_name": "Reg"})
    assert r.status_code == 201 and r.json()["status"] == "PENDING_AUTHORIZATION"
    r = requests.post(f"{BASE_URL}/api/customer-portal/auth/login", json={"email": email, "password": "Password!1"})
    assert r.status_code == 403  # mai accesso automatico senza autorizzazione azienda
    assert requests.post(f"{BASE_URL}/api/customer-portal/auth/login", json={"email": email, "password": "wrong"}).status_code == 401


def test_token_audiences_are_separated(admin, world):
    assert requests.get(f"{BASE_URL}/api/customer-portal/auth/me", headers=admin).status_code == 401  # token dipendente rifiutato
    assert requests.get(f"{BASE_URL}/api/quotes", headers=world["A"]["h"]).status_code == 401  # token cliente rifiutato lato ERP
    me = requests.get(f"{BASE_URL}/api/customer-portal/auth/me", headers=world["A"]["h"])
    assert me.status_code == 200 and me.json()["customer_id"] == world["A"]["cid"] and "password_hash" not in me.json()


def test_jobs_isolation_and_visual(world):
    A, B = world["A"], world["B"]
    jobs = requests.get(f"{BASE_URL}/api/customer-portal/jobs", headers=A["h"]).json()["items"]
    ids = {j["id"] for j in jobs}
    assert A["qid"] in ids and B["qid"] not in ids
    job = requests.get(f"{BASE_URL}/api/customer-portal/jobs/{A['qid']}", headers=A["h"]).json()
    assert job["lines"] and job["lines"][0]["visual_spec"]["svg_exterior"].startswith("<svg")
    assert job["lines"][0]["visual_spec"]["spec"]["interior_color_code"] == "003"
    assert job["timeline"][0]["done"] is True
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                assert k not in LEAK_KEYS, k
                walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(job)
    assert requests.get(f"{BASE_URL}/api/customer-portal/jobs/{B['qid']}", headers=A["h"]).status_code == 404
    assert requests.get(f"{BASE_URL}/api/customer-portal/jobs/{A['qid']}", headers=B["h"]).status_code == 404


def test_documents_isolation(world):
    A, B = world["A"], world["B"]
    docs = requests.get(f"{BASE_URL}/api/customer-portal/documents", headers=A["h"]).json()["items"]
    assert all(d["job_id"] == A["qid"] for d in docs)
    if A["pdf"]:
        assert any(d["id"] == A["pdf"] for d in docs)
        r = requests.get(f"{BASE_URL}/api/customer-portal/documents/{A['pdf']}/download", headers=A["h"])
        assert r.status_code == 200 and r.content[:4] == b"%PDF"
        assert requests.get(f"{BASE_URL}/api/customer-portal/documents/{A['pdf']}/download", headers=B["h"]).status_code == 404
    if B["pdf"]:
        assert requests.get(f"{BASE_URL}/api/customer-portal/documents/{B['pdf']}/download", headers=A["h"]).status_code == 404


def test_tickets(world):
    A, B = world["A"], world["B"]
    r = requests.post(f"{BASE_URL}/api/customer-portal/tickets", json={"job_id": A["qid"], "subject": "Maniglia", "description": "La maniglia è dura"}, headers=A["h"])
    assert r.status_code == 201 and r.json()["ticket_status"] == "RICEVUTO"
    assert requests.post(f"{BASE_URL}/api/customer-portal/tickets", json={"job_id": B["qid"], "subject": "Prova", "description": "Descrizione prova"}, headers=A["h"]).status_code == 404
    mine = requests.get(f"{BASE_URL}/api/customer-portal/tickets", headers=A["h"]).json()["items"]
    assert any(t["subject"] == "Maniglia" for t in mine)
    assert not any(t["subject"] == "Maniglia" for t in requests.get(f"{BASE_URL}/api/customer-portal/tickets", headers=B["h"]).json()["items"])
