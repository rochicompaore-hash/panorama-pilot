"""Legacy contracts regression (PO msg 782): contratti generati prima della SoT (senza
quote_snapshot.general_terms) devono:
- rispondere 200 su GET /api/contracts/{cid}/pdf/preview (fallback canonico corrente)
- rispondere con status 'CONTRACT_TERMS_SOURCE_MISSING' su terms-verify
"""
from __future__ import annotations

import os
import pytest
import requests

from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def h():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    r.raise_for_status()
    d = r.json()
    return {"Authorization": f"Bearer {d.get('access_token') or d.get('token')}"}


def _find_legacy_contract(h):
    """Find a truly legacy contract without quote_snapshot.general_terms (fully legacy pre-SoT)."""
    r = requests.get(f"{BASE_URL}/api/contracts?limit=100", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    items = data.get("items") if isinstance(data, dict) else data
    for c in items or []:
        detail = requests.get(f"{BASE_URL}/api/contracts/{c['id']}", headers=h).json()
        qs_gt = ((detail.get("quote_snapshot") or {}).get("general_terms"))
        if not qs_gt:
            return detail
    return None


def test_legacy_contract_pdf_fallback_ok(h):
    legacy = _find_legacy_contract(h)
    if not legacy:
        pytest.skip("No legacy contract without general_terms_version found in DB")
    r = requests.get(f"{BASE_URL}/api/contracts/{legacy['id']}/pdf/preview", headers=h)
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("application/pdf"), r.headers


def test_legacy_contract_terms_verify_reports_missing_source(h):
    legacy = _find_legacy_contract(h)
    if not legacy:
        pytest.skip("No legacy contract without general_terms_version found in DB")
    r = requests.get(f"{BASE_URL}/api/contracts/{legacy['id']}/terms-verify", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "CONTRACT_TERMS_SOURCE_MISSING", data
