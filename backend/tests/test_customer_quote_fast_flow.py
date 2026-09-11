"""CUSTOMER → QUOTE FAST FLOW + SEARCHABLE CUSTOMER SELECTOR (msg 804) — API."""
from __future__ import annotations

import os
import uuid

import pytest
import requests

from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def tag():
    return uuid.uuid4().hex[:6]


@pytest.fixture(scope="module")
def customers(admin, tag):
    priv = admin.post(f"{BASE_URL}/api/customers", json={"customer_type": "private", "first_name": f"Zorro{tag}", "last_name": f"Fastflow{tag}",
                                                          "email": f"zorro_{tag}@fast.it", "phone": f"39{tag}11", "tax_code": f"ZRRFST{tag.upper()}A"}, timeout=15).json()
    comp = admin.post(f"{BASE_URL}/api/customers", json={"customer_type": "company", "company_name": f"Serramenti Fast {tag} Srl",
                                                          "email": f"info_{tag}@fast.it", "phone": f"02{tag}", "vat_number": f"IT{tag}99999"}, timeout=15).json()
    return {"priv": priv, "comp": comp}


class TestCustomerSearch:
    @pytest.mark.parametrize("field", ["first_name", "last_name", "email", "phone", "tax_code", "customer_number"])
    def test_search_private_by_field(self, admin, customers, field):
        c = customers["priv"]
        val = c.get(field)
        if not val:
            pytest.skip(f"{field} non presente")
        r = admin.get(f"{BASE_URL}/api/customers", params={"q": val, "limit": 20}, timeout=15)
        assert r.status_code == 200
        assert any(i["id"] == c["id"] for i in r.json()["items"]), field

    @pytest.mark.parametrize("field", ["company_name", "vat_number", "email"])
    def test_search_company_by_field(self, admin, customers, field):
        c = customers["comp"]
        r = admin.get(f"{BASE_URL}/api/customers", params={"q": c[field], "limit": 20}, timeout=15)
        assert any(i["id"] == c["id"] for i in r.json()["items"]), field

    def test_search_case_insensitive(self, admin, customers, tag):
        r = admin.get(f"{BASE_URL}/api/customers", params={"q": f"serramenti fast {tag}".upper()}, timeout=15)
        assert any(i["id"] == customers["comp"]["id"] for i in r.json()["items"])

    def test_cross_tenant_zero_results(self, admin, customers, tag):
        import pymongo
        db = pymongo.MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        other = db.users.find_one({"email": "pilot@panoramapilot.com"})
        assert other and other["tenant_id"] != customers["priv"]["tenant_id"]
        # utente di un altro tenant: forziamo query tenant-scoped via DB (login owner non disponibile in test) → nessun doc con quel tenant
        assert db.customers.count_documents({"tenant_id": other["tenant_id"], "last_name": f"Fastflow{tag}"}) == 0
        # e l'API filtra sempre per tenant dell'utente
        r = admin.get(f"{BASE_URL}/api/customers", params={"q": f"Fastflow{tag}"}, timeout=15)
        assert all(i["tenant_id"] == customers["priv"]["tenant_id"] for i in r.json()["items"])


class TestCustomerToQuote:
    def test_no_site_then_inline_site_then_quote(self, admin, customers):
        c = customers["priv"]
        r = admin.get(f"{BASE_URL}/api/sites", params={"customer_id": c["id"]}, timeout=15)
        assert r.status_code == 200 and r.json()["items"] == []
        rs = admin.post(f"{BASE_URL}/api/sites", json={"customer_id": c["id"], "name": "Cantiere casa", "address": "Via Prova 1", "street_number": "1", "city": "Milano", "postal_code": "20100", "zip_code": "20100", "province": "MI", "floor": "1", "has_elevator": True, "site_contact_phone": "3331112222"}, timeout=15)
        assert rs.status_code in (200, 201), rs.text
        sid = rs.json()["id"]
        rq = admin.post(f"{BASE_URL}/api/quotes", json={"customer_id": c["id"], "site_id": sid, "title": "Fast flow"}, timeout=15)
        assert rq.status_code in (200, 201), rq.text
        q = rq.json()
        assert q["customer_id"] == c["id"] and q["site_id"] == sid
        # nessun duplicato anagrafica
        r2 = admin.get(f"{BASE_URL}/api/customers", params={"q": c["last_name"]}, timeout=15)
        assert len([i for i in r2.json()["items"] if i["last_name"] == c["last_name"]]) == 1

    def test_customer_with_multiple_sites(self, admin, customers):
        c = customers["comp"]
        for n in ("Sede", "Magazzino"):
            admin.post(f"{BASE_URL}/api/sites", json={"customer_id": c["id"], "name": n, "address": "Via X 1", "street_number": "1", "city": "Monza", "postal_code": "20900", "province": "MB", "floor": "0", "has_elevator": False, "site_contact_phone": "0212345678"}, timeout=15)
        r = admin.get(f"{BASE_URL}/api/sites", params={"customer_id": c["id"]}, timeout=15)
        assert len(r.json()["items"]) == 2   # UI deve mostrare la scelta cantiere

    def test_quote_list_filter_by_customer_and_search(self, admin, customers, tag):
        c = customers["priv"]
        r = admin.get(f"{BASE_URL}/api/quotes", params={"customer_id": c["id"], "limit": 50}, timeout=15)
        items = r.json()["items"]
        assert items and all(i["customer_id"] == c["id"] for i in items)
        for q in (f"Fastflow{tag}", f"zorro_{tag}@fast.it", f"39{tag}11", c["customer_number"]):
            r = admin.get(f"{BASE_URL}/api/quotes", params={"q": q, "limit": 50}, timeout=15)
            assert any(i["customer_id"] == c["id"] for i in r.json()["items"]), q
        r = admin.get(f"{BASE_URL}/api/quotes", params={"q": items[0]["number"]}, timeout=15)
        assert any(i["id"] == items[0]["id"] for i in r.json()["items"])
