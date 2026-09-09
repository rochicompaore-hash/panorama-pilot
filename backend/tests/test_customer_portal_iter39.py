"""Customer Portal Core V1 — Security & flow tests (iter 39)"""
import os
import time
import uuid
import pytest
import requests
from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") + "/api"
CP = BASE + "/customer-portal"
ADMIN = (ADMIN_EMAIL, ADMIN_PASSWORD)
CLIENT = ("cliente.demo@infissiexpress.com", "Cliente!2026")
KNOWN_CUSTOMER_ID = "b3ca8a98-5792-4b6d-bda7-00d841fd830b"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE}/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def client_token():
    r = requests.post(f"{CP}/auth/login", json={"email": CLIENT[0], "password": CLIENT[1]})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# --- Audience isolation ---

def test_employee_token_rejected_on_customer_portal(admin_token):
    r = requests.get(f"{CP}/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 401, r.text


def test_customer_token_rejected_on_erp_quotes(client_token):
    r = requests.get(f"{BASE}/quotes", headers={"Authorization": f"Bearer {client_token}"})
    assert r.status_code == 401


def test_customer_token_rejected_on_erp_customers(client_token):
    r = requests.get(f"{BASE}/customers", headers={"Authorization": f"Bearer {client_token}"})
    assert r.status_code == 401


# --- Cross customer isolation ---

def test_customer_cannot_read_another_customer_job(admin_token, client_token):
    # Find an accepted/converted quote of DIFFERENT customer_id
    r = requests.get(f"{BASE}/quotes?status=accepted", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, r.text
    items = r.json().get("items") or r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    if isinstance(r.json(), dict):
        items = r.json().get("items", [])
    other = None
    for q in items:
        if q.get("customer_id") and q["customer_id"] != KNOWN_CUSTOMER_ID:
            other = q
            break
    if not other:
        # try converted
        r2 = requests.get(f"{BASE}/quotes?status=converted", headers={"Authorization": f"Bearer {admin_token}"})
        items2 = r2.json().get("items", []) if r2.status_code == 200 else []
        for q in items2:
            if q.get("customer_id") and q["customer_id"] != KNOWN_CUSTOMER_ID:
                other = q
                break
    if not other:
        pytest.skip("Nessuna quote di altro cliente disponibile per l'isolation test")
    qid = other.get("_id") or other.get("id")
    r3 = requests.get(f"{CP}/jobs/{qid}", headers={"Authorization": f"Bearer {client_token}"})
    assert r3.status_code == 404, f"Expected 404, got {r3.status_code}: {r3.text}"


# --- No leak keys ---

def test_own_job_no_leaked_keys(client_token):
    r = requests.get(f"{CP}/jobs", headers={"Authorization": f"Bearer {client_token}"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    jid = items[0]["id"]
    r2 = requests.get(f"{CP}/jobs/{jid}", headers={"Authorization": f"Bearer {client_token}"})
    assert r2.status_code == 200
    body_text = r2.text
    for k in ["margin", "internal_cost", "technical_snapshot", "pricing_snapshot",
              "commercial_snapshot", "financial_snapshot", "supply_cost", "commission", "automatic_services"]:
        assert f'"{k}"' not in body_text, f"Leak key found: {k}"


# --- Register + pending + rate limit ---

def test_register_pending_and_login_forbidden():
    email = f"TEST_pending_{uuid.uuid4().hex[:8]}@example.com"
    body = {"tenant_id": "5e353147-2416-4ef7-aa3f-3e0007435c42", "email": email,
            "password": "Password123!", "first_name": "Test", "last_name": "Pending"}
    r = requests.post(f"{CP}/auth/register", json=body)
    assert r.status_code == 201, r.text
    assert r.json().get("status") == "PENDING_AUTHORIZATION"
    r2 = requests.post(f"{CP}/auth/login", json={"email": email, "password": "Password123!"})
    assert r2.status_code == 403, r2.text


def test_rate_limit_after_5_failed():
    email = f"TEST_rl_{uuid.uuid4().hex[:8]}@example.com"
    codes = []
    for i in range(6):
        r = requests.post(f"{CP}/auth/login", json={"email": email, "password": "wrongwrong"})
        codes.append(r.status_code)
    assert codes[5] == 429, f"Expected 429 on 6th try, got sequence {codes}"
