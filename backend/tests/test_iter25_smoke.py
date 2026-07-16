"""Iter 25 smoke — code-quality refactor regressions.
Covers requested items not already in test_code_quality_regression.py:
- /api/health, routes count (>= ~500)
- /api/auth/me shape for admin
- /api/contracts/generate-from-quote 404 branch (bogus quote id)
- /api/bi/quotes/kpi extra sanity (period_days respected)
"""
from __future__ import annotations
import os
import uuid
import pytest
import requests

from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text[:300]
    token = r.json().get("access_token")
    assert token, "no access_token"
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def test_health_ok():
    r = requests.get(f"{API}/health", timeout=10)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_auth_me_admin_shape(admin_session):
    r = admin_session.get(f"{API}/auth/me", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "user" in body
    assert body["user"]["email"].lower() == ADMIN_EMAIL.lower()
    # Permissions returned somewhere in payload
    assert "permissions" in body or "permission_keys" in body or "permissions" in body.get("user", {})


def test_login_response_shape(admin_session):
    # Fresh explicit login (not via fixture) to check tokens shape
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    # refresh cookie may be httpOnly; if present in body accept, else pass
    assert "user" in body


def test_contracts_generate_from_quote_404_on_bogus_id(admin_session):
    bogus = "quote_" + uuid.uuid4().hex
    r = admin_session.post(f"{API}/contracts/generate-from-quote",
                           json={"quote_id": bogus}, timeout=15)
    assert r.status_code in (400, 404), r.text[:300]  # helper must guard


def test_openapi_route_count():
    # openapi.json is served by FastAPI but not proxied via ingress (frontend
    # SPA catches unknown paths). Query the backend directly on localhost.
    r = requests.get("http://localhost:8001/openapi.json", timeout=20)
    assert r.status_code == 200
    spec = r.json()
    paths = spec.get("paths", {})
    n_ops = sum(len([m for m in ops if m.lower() in
                     ("get", "post", "put", "delete", "patch")])
                for ops in paths.values())
    # refactor spec said ~565, expect no regressions below ~550
    assert n_ops >= 550, f"unexpectedly few operations: {n_ops}"


def test_quotes_kpi_period_days(admin_session):
    r = admin_session.get(f"{API}/bi/quotes/kpi?period_days=7", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body.get("period_days") == 7
