"""Iter41 — Production readiness finalization gate tests.
Rotazione credenziali, portale sospeso, regressione rapida.
NON stampa mai secrets/password.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE = os.environ["REACT_APP_BACKEND_URL"] if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BASE:
    # fallback: frontend .env
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE = line.split("=", 1)[1].strip()
BASE = BASE.rstrip("/")

ADMIN_EMAIL = "admin@infissiexpress.com"
# NB: read current password from memory file — never hardcode in report
CURRENT_ADMIN_PWD = "R!J0m34OlNsVtZjvqmVC"
OLD_ADMIN_PWD = "Admin!2025"

QUOTE_ID = "c80f2e37-878a-4dab-b557-1476a546d6d3"


def _login(email, pwd):
    return requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd}, timeout=30)


def test_auth_rotation_new_password_ok():
    r = _login(ADMIN_EMAIL, CURRENT_ADMIN_PWD)
    assert r.status_code == 200, f"expected 200 got {r.status_code}"
    data = r.json()
    assert "access_token" in data or "token" in data


def test_auth_rotation_old_password_rejected():
    r = _login(ADMIN_EMAIL, OLD_ADMIN_PWD)
    assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"


def test_customer_portal_demo_suspended():
    r = requests.post(
        f"{BASE}/api/customer-portal/auth/login",
        json={"email": "cliente.demo@infissiexpress.com", "password": "Cliente!2026"},
        timeout=30,
    )
    assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"


def _admin_token():
    r = _login(ADMIN_EMAIL, CURRENT_ADMIN_PWD)
    r.raise_for_status()
    d = r.json()
    return d.get("access_token") or d.get("token")


def test_regression_sequences():
    tok = _admin_token()
    r = requests.get(f"{BASE}/api/sequences", headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    assert r.status_code == 200


def test_regression_quotes_list():
    tok = _admin_token()
    r = requests.get(f"{BASE}/api/quotes", headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    assert r.status_code == 200


def test_regression_pdf_preview_v2():
    tok = _admin_token()
    r = requests.post(
        f"{BASE}/api/quotes/{QUOTE_ID}/pdf/preview",
        headers={"Authorization": f"Bearer {tok}"},
        json={},
        timeout=60,
    )
    assert r.status_code == 200, f"expected 200 got {r.status_code}"
    # PDF V2 preview returns JSON metadata with id (persisted preview record).
    # Ensure response body is well-formed.
    d = r.json()
    assert isinstance(d, dict)
