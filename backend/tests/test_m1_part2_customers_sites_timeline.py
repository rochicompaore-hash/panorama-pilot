"""Milestone 1 Part 2 — Customers + Sites + Timeline + Quotes bound to sites.

Covers all backend requirements from the E1 review request:
  - customer_type PRIVATE/COMPANY/TO_CONFIRM (with legacy retro-compat)
  - customer_number progressive CLI-000###
  - validation errors PRIVATE_REQUIRES_NAME / COMPANY_REQUIRES_NAME
  - PATCH legacy without customer_type → CUSTOMER_TYPE_REQUIRED
  - Sites create → SYSTEM_EVENT in timeline
  - Timeline POST rules (CALL ok, SYSTEM_EVENT rejected, invalid category rejected)
  - Quotes create with site_id validation
"""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@infissiexpress.com"
ADMIN_PASS = "Admin!2025"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    assert tok, f"No token in response: {data}"
    return tok


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------------- CUSTOMER creation ----------------------

def _extract_code(resp):
    try:
        j = resp.json()
        d = j.get("detail")
        if isinstance(d, dict):
            return d.get("code")
        return d
    except Exception:
        return None


class TestCustomerCreation:
    def test_create_private_customer_with_number(self, h):
        ts = int(time.time())
        payload = {
            "customer_type": "PRIVATE",
            "first_name": f"TESTMario{ts}",
            "last_name": "Rossi",
            "email": f"test.mario.{ts}@example.com",
            "phone": "3331234567",
        }
        r = requests.post(f"{API}/customers", json=payload, headers=h, timeout=15)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert d["customer_type"] == "PRIVATE"
        assert d.get("customer_number", "").startswith("CLI-"), d
        assert len(d["customer_number"]) == len("CLI-000001")
        # Store for later
        pytest.private_customer_id = d["id"]
        pytest.private_customer_number = d["customer_number"]

    def test_create_company_customer_progressive(self, h):
        ts = int(time.time())
        payload = {
            "customer_type": "COMPANY",
            "company_name": f"TEST Acme Srl {ts}",
            "vat_number": "01234567890",
            "email": f"acme.{ts}@example.com",
            "contact_person": {
                "first_name": "Luigi",
                "last_name": "Verdi",
                "role": "Referente",
                "phone": "3339998888",
                "email": f"luigi.{ts}@example.com",
            },
        }
        r = requests.post(f"{API}/customers", json=payload, headers=h, timeout=15)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert d["customer_type"] == "COMPANY"
        num1 = pytest.private_customer_number
        num2 = d["customer_number"]
        assert num2.startswith("CLI-")
        # progressive strictly greater
        assert int(num2.split("-")[1]) == int(num1.split("-")[1]) + 1, (num1, num2)
        pytest.company_customer_id = d["id"]

    def test_private_missing_name_400(self, h):
        r = requests.post(f"{API}/customers",
                          json={"customer_type": "PRIVATE", "last_name": "SoloCognome"},
                          headers=h, timeout=15)
        assert r.status_code == 400
        assert _extract_code(r) == "PRIVATE_REQUIRES_NAME", r.text

    def test_company_missing_name_400(self, h):
        r = requests.post(f"{API}/customers",
                          json={"customer_type": "COMPANY"},
                          headers=h, timeout=15)
        assert r.status_code == 400
        assert _extract_code(r) == "COMPANY_REQUIRES_NAME", r.text


class TestCustomerList:
    def test_list_normalizes_customer_type(self, h):
        r = requests.get(f"{API}/customers?limit=200", headers=h, timeout=15)
        assert r.status_code == 200
        items = r.json().get("items", [])
        for it in items:
            assert it.get("customer_type") in {"PRIVATE", "COMPANY", "TO_CONFIRM"}, it


class TestLegacyCustomer:
    def test_patch_legacy_without_customer_type_400(self, h):
        # Insert legacy directly into DB via a helper endpoint? Not available.
        # Emulate by creating a customer whose customer_type in DB is missing.
        # We do it via a direct Mongo write since we can't reach it here — skip if not possible.
        # Instead, use a legacy-style customer_type via API? Not permitted (create requires PRIVATE/COMPANY).
        # We insert via pymongo directly.
        try:
            from pymongo import MongoClient
        except ImportError:
            pytest.skip("pymongo not available")
        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME")
        if not mongo_url or not db_name:
            pytest.skip("MONGO_URL/DB_NAME missing")
        client = MongoClient(mongo_url)
        db = client[db_name]
        # Find tenant of admin
        u = db.users.find_one({"email": ADMIN_EMAIL})
        assert u
        tenant_id = u["tenant_id"]
        import uuid
        from datetime import datetime, timezone
        cid = str(uuid.uuid4())
        db.customers.insert_one({
            "_id": cid,
            "tenant_id": tenant_id,
            "first_name": None,
            "last_name": None,
            "company_name": "TEST Legacy Co",
            "email": "legacy@example.com",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "deleted_at": None,
            "version": 1,
            # NO customer_type -> legacy
        })
        pytest.legacy_customer_id = cid
        # PATCH without customer_type
        r = requests.patch(f"{API}/customers/{cid}", json={"phone": "0011223344"},
                           headers=h, timeout=15)
        assert r.status_code == 400, r.text
        assert _extract_code(r) == "CUSTOMER_TYPE_REQUIRED", r.text

    def test_patch_legacy_set_private_ok(self, h):
        cid = getattr(pytest, "legacy_customer_id", None)
        if not cid:
            pytest.skip("no legacy customer")
        payload = {
            "customer_type": "PRIVATE",
            "first_name": "TESTLegacy",
            "last_name": "Fixed",
        }
        r = requests.patch(f"{API}/customers/{cid}", json=payload, headers=h, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("customer_type") == "PRIVATE"


# ---------------------- SITES + TIMELINE ----------------------

class TestSitesAndTimeline:
    def test_create_site_generates_system_event(self, h):
        cid = pytest.private_customer_id
        payload = {
            "customer_id": cid,
            "name": "TEST Abitazione principale",
            "address": "via Roma",
            "street_number": "12",
            "postal_code": "20100",
            "city": "Milano",
            "province": "MI",
            "floor": "3",
            "has_elevator": True,
            "site_contact_phone": "3331234567",  # msg 402 Lotto 2: obbligatorio
            "property_type": "APPARTAMENTO",
        }
        r = requests.post(f"{API}/sites", json=payload, headers=h, timeout=15)
        assert r.status_code in (200, 201), r.text
        sd = r.json()
        assert sd.get("site_number", "").startswith("CANT-")
        pytest.site_id = sd["id"]
        # timeline
        tr = requests.get(f"{API}/customers/{cid}/timeline", headers=h, timeout=15)
        assert tr.status_code == 200
        items = tr.json().get("items", [])
        sys_events = [x for x in items if x.get("category") == "SYSTEM_EVENT" and x.get("site_id") == sd["id"]]
        assert sys_events, f"No SYSTEM_EVENT for site: {items}"

    def test_post_timeline_manual_call(self, h):
        cid = pytest.private_customer_id
        r = requests.post(f"{API}/customers/{cid}/timeline",
                          json={"category": "CALL", "channel": "PHONE", "body": "TEST Cliente richiama venerdì"},
                          headers=h, timeout=15)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert d["category"] == "CALL"
        assert d["event_source"] == "MANUAL"

    def test_post_timeline_system_readonly(self, h):
        cid = pytest.private_customer_id
        r = requests.post(f"{API}/customers/{cid}/timeline",
                          json={"category": "SYSTEM_EVENT", "body": "hack"},
                          headers=h, timeout=15)
        assert r.status_code == 400
        assert _extract_code(r) == "SYSTEM_EVENT_READONLY", r.text

    def test_post_timeline_invalid_category(self, h):
        cid = pytest.private_customer_id
        r = requests.post(f"{API}/customers/{cid}/timeline",
                          json={"category": "BOGUS_XX", "body": "x"},
                          headers=h, timeout=15)
        assert r.status_code == 400
        assert _extract_code(r) == "INVALID_CATEGORY", r.text


# ---------------------- QUOTES with site binding ----------------------

class TestQuotesWithSite:
    def test_create_quote_with_valid_site(self, h):
        cid = pytest.private_customer_id
        sid = pytest.site_id
        r = requests.post(f"{API}/quotes",
                          json={"customer_id": cid, "site_id": sid, "title": "TEST Preventivo M1"},
                          headers=h, timeout=15)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert d.get("site_id") == sid
        pytest.quote_id = d["id"]

    def test_create_quote_site_not_owned_by_customer(self, h):
        # site belongs to private customer; try binding to company customer
        cid = pytest.company_customer_id
        sid = pytest.site_id
        r = requests.post(f"{API}/quotes",
                          json={"customer_id": cid, "site_id": sid, "title": "TEST wrong site"},
                          headers=h, timeout=15)
        assert r.status_code == 400
        assert "Cantiere non valido" in (r.json().get("detail") or ""), r.text

    def test_create_quote_site_without_customer(self, h):
        sid = pytest.site_id
        r = requests.post(f"{API}/quotes",
                          json={"site_id": sid, "title": "TEST no cust"},
                          headers=h, timeout=15)
        assert r.status_code == 400


# ---------------------- Cleanup ----------------------

def test_zz_cleanup(h):
    """Soft-delete test customers created."""
    for attr in ("private_customer_id", "company_customer_id", "legacy_customer_id"):
        cid = getattr(pytest, attr, None)
        if cid:
            try:
                requests.delete(f"{API}/customers/{cid}", headers=h, timeout=10)
            except Exception:
                pass
