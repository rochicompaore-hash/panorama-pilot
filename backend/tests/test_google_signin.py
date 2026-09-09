"""Tests for Emergent-managed Google sign-in wiring + classic login regression."""
import os
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://serramento-ops.preview.emergentagent.com').rstrip('/')


# --- Google session exchange (fail-closed) ---
def test_google_session_invalid_returns_401():
    r = requests.post(f"{BASE_URL}/api/auth/google/session", json={"session_id": "invalid"}, timeout=20)
    assert r.status_code == 401, r.text
    body = r.json()
    assert body.get("detail") == "Sessione Google non valida o scaduta"


def test_google_session_missing_body_returns_422():
    r = requests.post(f"{BASE_URL}/api/auth/google/session", json={}, timeout=20)
    assert r.status_code == 422, r.text


# --- Classic login regression ---
def test_classic_login_and_me():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "admin@infissiexpress.com", "password": "Admin!2025"},
                      timeout=20)
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token")
    assert tok and isinstance(tok, str)
    me = requests.get(f"{BASE_URL}/api/auth/me",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=20)
    assert me.status_code == 200, me.text
    body = me.json()
    email = body.get("email") or body.get("user", {}).get("email")
    assert email == "admin@infissiexpress.com"
