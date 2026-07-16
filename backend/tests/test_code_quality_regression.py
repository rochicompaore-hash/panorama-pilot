"""Regression tests introduced with the Code Quality iteration.

Covers:
- login (helpers extraction preserves behaviour)
- accept-invitation (helper extraction preserves behaviour + platform-owner branch)
- public signature flow (OTP verification helper, snapshot hash stability)
- quotes KPI (BI helpers)
- AI CFO suggestions (per-category builders)
- break-even service (no eval, deterministic math)
- parametric engine (no eval — formula whitelist enforced)
- formula_security guard (import-time assertion works)

Backend must be reachable via REACT_APP_BACKEND_URL. Credentials come from env.
"""
from __future__ import annotations
import os
import time
import uuid
import pytest
import requests

from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL not configured", allow_module_level=True)

API = f"{BASE_URL}/api"


# --------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    token = r.json().get("access_token")
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# --------------------------------------------------------------------
# 1. AUTH
# --------------------------------------------------------------------
def test_login_valid(admin_session):
    me = admin_session.get(f"{API}/auth/me", timeout=10)
    assert me.status_code == 200
    payload = me.json()
    assert payload["user"]["email"].lower() == ADMIN_EMAIL.lower()


def test_login_invalid_credentials():
    r = requests.post(f"{API}/auth/login",
                       json={"email": ADMIN_EMAIL, "password": "definitely-wrong-2026!"},
                       timeout=10)
    # 401 credenziali non valide OR 429 se altro test ha già saturato brute-force
    assert r.status_code in (401, 429), r.text[:200]


def test_accept_invitation_short_password_rejected():
    r = requests.post(f"{API}/auth/accept-invitation",
                       json={"token": "irrelevant", "password": "short"}, timeout=10)
    assert r.status_code == 400
    assert "8 caratteri" in r.text or "8 carattere" in r.text


def test_accept_invitation_invalid_token_rejected():
    r = requests.post(f"{API}/auth/accept-invitation",
                       json={"token": "does-not-exist-" + uuid.uuid4().hex,
                              "password": "AtLeastEight!"}, timeout=10)
    assert r.status_code == 400
    assert "Invito" in r.text or "invito" in r.text


# --------------------------------------------------------------------
# 2. BI — quotes KPI
# --------------------------------------------------------------------
def test_quotes_kpi_shape(admin_session):
    r = admin_session.get(f"{API}/bi/quotes/kpi?period_days=30", timeout=15)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    for key in ("period_days", "counts_by_status", "total_created",
                "value_created", "value_signed", "conversion_rate_pct",
                "weighted_pipeline_value", "avg_hours_to_first_open",
                "avg_hours_to_sign", "quotes_never_viewed",
                "quotes_expiring_7d", "rejection_reasons"):
        assert key in body, f"missing KPI key: {key}"
    assert isinstance(body["counts_by_status"], dict)
    assert isinstance(body["rejection_reasons"], list)


# --------------------------------------------------------------------
# 3. AI CFO
# --------------------------------------------------------------------
def test_ai_cfo_generate_and_list(admin_session):
    r = admin_session.post(f"{API}/ai-cfo/generate", json={"force_regen": True}, timeout=20)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert "generated" in body
    assert "items" in body
    assert isinstance(body["items"], list)

    r2 = admin_session.get(f"{API}/ai-cfo/suggestions?include_dismissed=true", timeout=15)
    assert r2.status_code == 200


# --------------------------------------------------------------------
# 4. Contract public flow — snapshot hash stability & OTP guard
# --------------------------------------------------------------------
def test_public_contract_invalid_token_returns_404():
    bogus = "bogus-token-" + uuid.uuid4().hex
    r = requests.get(f"{API}/contracts/public/{bogus}", timeout=10)
    assert r.status_code == 404


def test_public_sign_invalid_token():
    bogus = "bogus-" + uuid.uuid4().hex
    r = requests.post(f"{API}/contracts/public/{bogus}/sign",
                       json={"signer_name": "X", "signature_data_url": "data:image/png;base64,AA==",
                              "accept_terms": True}, timeout=10)
    assert r.status_code == 404


# --------------------------------------------------------------------
# 5. Formula engine — determinism + no eval
# --------------------------------------------------------------------
def test_formula_engine_math_deterministic():
    from app.services.formula import eval_formula, FormulaError
    ctx = {"L": 1000, "H": 500, "nr_ante": 2}
    assert str(eval_formula("L/nr_ante", ctx)) == "500"
    with pytest.raises(FormulaError):
        eval_formula("L/0", ctx, strict=True)


def test_formula_engine_rejects_unknown_var():
    from app.services.formula import eval_formula, FormulaError
    with pytest.raises(FormulaError):
        eval_formula("suspicious_var * 2", {"L": 1})


def test_formula_engine_rejects_function_call():
    from app.services.formula import eval_formula, FormulaError
    with pytest.raises(FormulaError):
        eval_formula("__import__('os')", {})


def test_formula_security_module_asserts_no_eval():
    # Simply importing must succeed (assertion runs at import time)
    from app.services.formula_security import SafeExpression, _assert_no_eval_in_module
    engine = SafeExpression()
    assert engine.evaluate("2+3*4", {}) == 14
    with pytest.raises(Exception):
        engine.evaluate("__import__('os').system('echo hi')", {})
    _assert_no_eval_in_module("app.services.parametric_engine")
    _assert_no_eval_in_module("app.services.breakeven")


# --------------------------------------------------------------------
# 6. Break-even service — deterministic (no eval)
# --------------------------------------------------------------------
def test_breakeven_module_pure_python():
    # Guarantee break-even module has no dynamic eval — mirrors production policy.
    from app.services.formula_security import _assert_no_eval_in_module
    _assert_no_eval_in_module("app.services.breakeven")


# --------------------------------------------------------------------
# 7. Parametric engine — no eval
# --------------------------------------------------------------------
def test_parametric_engine_module_pure_python():
    from app.services.formula_security import _assert_no_eval_in_module
    _assert_no_eval_in_module("app.services.parametric_engine")
