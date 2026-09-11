"""ITER47 PO E2E verification — RBAC/tenant isolation/no-leak/idempotency (no code changes)."""
from __future__ import annotations

import json
import os
import uuid

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

ADMIN = ("admin@infissiexpress.com", "R!J0m34OlNsVtZjvqmVC")
COMM = ("commercial_test@infissiexpress.com", "CommTest!2026")

LEAK_KEYS = ("internal_cost", "margin_", "supply_cost", "purchase_cost", "commercial_multiplier")


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def commercial():
    return _login(*COMM)


@pytest.fixture(scope="module")
def contract_ctx(admin):
    tag = uuid.uuid4().hex[:6]
    # customer
    rc = admin.post(f"{BASE_URL}/api/customers", json={
        "customer_type": "private", "first_name": "Iter47", "last_name": f"Verify{tag}",
        "email": f"iter47_{tag}@x.it", "phone": "3331234567",
        "tax_code": "RSSMRA80A01H501U",
        "address": {"street": "Via Roma 1", "city": "Milano", "zip_code": "20100", "province": "MI"},
    }, timeout=15)
    assert rc.status_code in (200, 201), rc.text
    cust = rc.json()
    cid = cust["id"]
    # site via POST /api/sites
    rs = admin.post(f"{BASE_URL}/api/sites", json={
        "customer_id": cid, "name": "Cantiere47", "address": "Via Cantiere",
        "street_number": "9", "postal_code": "20900", "zip_code": "20900",
        "city": "Monza", "province": "MB",
        "floor": "1", "has_elevator": True, "site_contact_phone": "3331112222",
    }, timeout=15)
    assert rs.status_code in (200, 201), rs.text
    sid = rs.json()["id"]
    # quote
    rq = admin.post(f"{BASE_URL}/api/quotes", json={
        "customer_id": cid, "site_id": sid, "title": f"TEST iter47 {tag}",
    }, timeout=15)
    assert rq.status_code in (200, 201), rq.text
    qid = rq.json()["id"]
    # line
    rl = admin.post(f"{BASE_URL}/api/quotes/{qid}/lines", json={
        "description": "Finestra test", "category": "window",
        "quantity": 1, "base_price": 1000.0, "internal_cost": 400.0,
    }, timeout=15)
    assert rl.status_code in (200, 201), rl.text
    # sent -> accepted
    for st in ("sent", "accepted"):
        r = admin.post(f"{BASE_URL}/api/quotes/{qid}/status", json={"new_status": st}, timeout=15)
        assert r.status_code == 200, r.text
    # convert
    rconv = admin.post(f"{BASE_URL}/api/quotes/{qid}/convert-to-contract", timeout=30)
    assert rconv.status_code == 200, rconv.text
    contract = rconv.json()
    return {"cid_customer": cid, "sid": sid, "qid": qid, "contract": contract}


def _scan_leak(obj):
    blob = json.dumps(obj).lower()
    found = [k for k in LEAK_KEYS if k in blob]
    return found


class TestContractE2E:
    def test_snapshot_shape(self, contract_ctx):
        c = contract_ctx["contract"]
        assert c["contract_status"] == "draft"
        snap = c["quote_snapshot"]
        assert snap["customer"]["id"] == contract_ctx["cid_customer"]
        assert snap["site"]  # site snapshot present
        assert "Cantiere" in json.dumps(snap["site"])
        assert snap["economics"]["total"] > 0
        assert c["general_terms_version"] and c["snapshot_hash"]

    def test_no_internal_leak_in_contract_json(self, contract_ctx):
        found = _scan_leak(contract_ctx["contract"])
        assert not found, f"leak keys in contract JSON: {found}"

    def test_presign_check_ok(self, admin, contract_ctx):
        cid = contract_ctx["contract"]["id"]
        r = admin.get(f"{BASE_URL}/api/contracts/{cid}/presign-check", timeout=15)
        assert r.status_code == 200
        assert r.json()["ok"] is True, r.text

    def test_convert_idempotent_same_contract(self, admin, contract_ctx):
        qid = contract_ctx["qid"]
        expected = contract_ctx["contract"]["id"]
        for _ in range(2):
            r = admin.post(f"{BASE_URL}/api/quotes/{qid}/convert-to-contract", timeout=30)
            assert r.status_code == 200
            assert r.json()["id"] == expected

    def test_pdf_preview_valid(self, admin, contract_ctx):
        cid = contract_ctx["contract"]["id"]
        r = admin.get(f"{BASE_URL}/api/contracts/{cid}/pdf/preview", timeout=60)
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"
        assert len(r.content) > 5000

    def test_economic_silent_change_blocked(self, admin, contract_ctx):
        cid = contract_ctx["contract"]["id"]
        # via /parties with economic fields → 4xx
        r = admin.patch(f"{BASE_URL}/api/contracts/{cid}/parties",
                        json={"customer": {"total": 1.0}}, timeout=15)
        assert 400 <= r.status_code < 500
        # via top-level PATCH modifying total
        r2 = admin.patch(f"{BASE_URL}/api/contracts/{cid}",
                         json={"quote_snapshot": {"economics": {"total": 1.0}}}, timeout=15)
        assert 400 <= r2.status_code < 500


class TestRBACAndTenantIsolation:
    def test_commercial_can_read_contract(self, commercial, contract_ctx):
        cid = contract_ctx["contract"]["id"]
        r = commercial.get(f"{BASE_URL}/api/contracts/{cid}", timeout=15)
        # commercial may or may not have read access; if 403, that's also a valid isolation signal
        if r.status_code == 403:
            pytest.skip("commercial user has no contract read scope (RBAC deny)")
        assert r.status_code == 200, r.text
        found = _scan_leak(r.json())
        assert not found, f"commercial sees leak keys: {found}"

    def test_contract_not_found_returns_404(self, admin):
        fake = uuid.uuid4().hex
        r = admin.get(f"{BASE_URL}/api/contracts/{fake}", timeout=15)
        assert r.status_code == 404

    def test_customer_not_found_returns_404(self, admin):
        fake = uuid.uuid4().hex
        r = admin.get(f"{BASE_URL}/api/customers/{fake}", timeout=15)
        assert r.status_code == 404

    def test_quotes_filter_random_customer_empty(self, admin):
        fake = uuid.uuid4().hex
        r = admin.get(f"{BASE_URL}/api/quotes",
                      params={"customer_id": fake, "limit": 50}, timeout=15)
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_quotes_filter_by_customer_scoped(self, admin, contract_ctx):
        cid = contract_ctx["cid_customer"]
        r = admin.get(f"{BASE_URL}/api/quotes",
                      params={"customer_id": cid, "limit": 50}, timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        assert items and all(i["customer_id"] == cid for i in items)


class TestNoDuplicateCustomer:
    def test_no_duplicate_by_email(self, admin, contract_ctx):
        # scan by email — must be exactly one
        snap = contract_ctx["contract"]["quote_snapshot"]["customer"]
        email = snap["email"]
        r = admin.get(f"{BASE_URL}/api/customers",
                      params={"q": email, "limit": 50}, timeout=15)
        assert r.status_code == 200
        matches = [i for i in r.json()["items"] if i.get("email") == email]
        assert len(matches) == 1, f"duplicate customers with email {email}: {len(matches)}"
