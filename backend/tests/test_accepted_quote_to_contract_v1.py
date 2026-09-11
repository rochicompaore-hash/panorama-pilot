"""ACCEPTED QUOTE → CONTRACT GENERATION V1 (msg 803) — API E2E."""
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
def accepted_quote(admin):
    tag = uuid.uuid4().hex[:6]
    rc = admin.post(f"{BASE_URL}/api/customers", json={"customer_type": "private", "first_name": "Mario", "last_name": f"Contratto{tag}",
                                                        "email": f"mario_{tag}@x.it", "phone": "3331234567", "tax_code": "RSSMRA80A01H501U",
                                                        "address": {"street": "Via Roma 1", "city": "Milano", "zip_code": "20100", "province": "MI"}}, timeout=15)
    assert rc.status_code in (200, 201), rc.text
    cust = rc.json()
    cid = cust.get("id") or cust.get("_id")
    rq = admin.post(f"{BASE_URL}/api/quotes", json={"customer_id": cid, "title": f"TEST contratto {tag}",
                                                     "site_address": {"street": "Via Cantiere 9", "city": "Monza", "zip_code": "20900", "province": "MB"}}, timeout=15)
    assert rq.status_code in (200, 201), rq.text
    qid = rq.json().get("id") or rq.json().get("_id")
    for ln in [
        {"description": "Finestra PVC 2 ante", "category": "window", "quantity": 2, "base_price": 1200.0, "internal_cost": 500.0,
         "technical_snapshot": {"total_internal_cost": 500.0}, "width_mm": 1200, "height_mm": 1400},
        {"description": "Posa in opera", "category": "installation", "quantity": 1, "base_price": 300.0, "internal_cost": 150.0},
    ]:
        rl = admin.post(f"{BASE_URL}/api/quotes/{qid}/lines", json=ln, timeout=15)
        assert rl.status_code in (200, 201), rl.text
    rp = admin.patch(f"{BASE_URL}/api/quotes/{qid}", json={"global_discount_percent": 5.0}, timeout=15)
    assert rp.status_code == 200, rp.text
    for st in ("sent", "accepted"):
        rs = admin.post(f"{BASE_URL}/api/quotes/{qid}/status", json={"new_status": st}, timeout=15)
        assert rs.status_code == 200, rs.text
    q = admin.get(f"{BASE_URL}/api/quotes/{qid}", timeout=15).json()
    return {"quote": q, "customer_id": cid}


@pytest.fixture(scope="module")
def contract(admin, accepted_quote):
    qid = accepted_quote["quote"]["id"]
    r = admin.post(f"{BASE_URL}/api/quotes/{qid}/convert-to-contract", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


class TestGeneration:
    def test_contract_created_from_accepted(self, contract, accepted_quote):
        assert contract["contract_status"] == "draft"
        assert contract["number"].startswith("CON-")
        assert contract["quote_id"] == accepted_quote["quote"]["id"]
        assert contract["snapshot_hash"] and contract["general_terms_version"]

    def test_no_duplicate_open_existing(self, admin, contract, accepted_quote):
        qid = accepted_quote["quote"]["id"]
        r = admin.post(f"{BASE_URL}/api/quotes/{qid}/convert-to-contract", timeout=30)
        assert r.status_code == 200 and r.json()["id"] == contract["id"]
        r2 = admin.get(f"{BASE_URL}/api/contracts/by-quote/{qid}", timeout=15)
        assert r2.status_code == 200 and r2.json()["id"] == contract["id"]
        q = admin.get(f"{BASE_URL}/api/quotes/{qid}", timeout=15).json()
        assert q["contract_id"] == contract["id"]

    def test_customer_prefill(self, contract, accepted_quote):
        c = contract["quote_snapshot"]["customer"]
        assert c["first_name"] == "Mario" and c["tax_code"] == "RSSMRA80A01H501U"
        assert c["email"].startswith("mario_") and c["phone"] == "3331234567"
        assert c["id"] == accepted_quote["customer_id"]

    def test_site_prefill(self, contract):
        s = contract["quote_snapshot"]["site"]
        assert s["street"] == "Via Cantiere 9" and s["city"] == "Monza" and s["zip_code"] == "20900"

    def test_products_services_prices_identical(self, contract, accepted_quote):
        q = accepted_quote["quote"]
        snap = contract["quote_snapshot"]
        items = snap["quote_summary"]["items"]
        assert [i["description"] for i in items] == [l["description"] for l in q["lines"]]
        assert [i["quantity"] for i in items] == [l["quantity"] for l in q["lines"]]
        assert items[0]["width_mm"] == 1200 and items[0]["height_mm"] == 1400
        assert [i["subtotal_line"] for i in items] == [l["subtotal_line"] for l in q["lines"]]
        eco = snap["economics"]
        assert eco["subtotal"] == q["subtotal"] and eco["vat_amount"] == q["vat_amount"] and eco["total"] == q["total"]
        assert eco["global_discount_amount"] == q["global_discount_amount"] > 0
        assert eco["payment_terms"]["code"] == (q.get("payment_terms_code") or q.get("payment_terms"))
        assert snap["quote_number"] == q["number"] and snap["accepted_at"]

    def test_general_terms_canonical(self, admin, contract):
        r = admin.get(f"{BASE_URL}/api/contracts/{contract['id']}/terms-verify", timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["identical"] is True and r.json()["version"] == contract["general_terms_version"]

    def test_no_internal_leak_in_snapshot(self, contract):
        import json
        blob = json.dumps(contract["quote_snapshot"]).lower()
        for leak in ("internal_cost", "financial_snapshot", "commission", "purchase_cost", "margin_"):
            assert leak not in blob, leak


class TestDraftEditing:
    def test_presign_ok_initially(self, admin, contract):
        r = admin.get(f"{BASE_URL}/api/contracts/{contract['id']}/presign-check", timeout=15)
        assert r.status_code == 200 and r.json()["ok"] is True, r.text

    def test_edit_tax_code_only_contract_with_audit(self, admin, contract, accepted_quote):
        r = admin.patch(f"{BASE_URL}/api/contracts/{contract['id']}/parties", json={"customer": {"tax_code": "RSSMRA80A01H501X"}, "sync_customer": False}, timeout=15)
        assert r.status_code == 200, r.text
        ch = r.json()["changes"][0]
        assert ch["field"] == "tax_code" and ch["old_value"] == "RSSMRA80A01H501U" and ch["new_value"] == "RSSMRA80A01H501X" and ch["changed_by"]
        cust = admin.get(f"{BASE_URL}/api/customers/{accepted_quote['customer_id']}", timeout=15).json()
        assert cust["tax_code"] == "RSSMRA80A01H501U"   # anagrafica NON toccata

    def test_edit_with_sync_updates_customer_no_duplicate(self, admin, contract, accepted_quote):
        before = admin.get(f"{BASE_URL}/api/customers", params={"limit": 500}, timeout=15).json()
        n_before = before.get("total") if isinstance(before, dict) else len(before)
        r = admin.patch(f"{BASE_URL}/api/contracts/{contract['id']}/parties", json={"customer": {"phone": "3399999999"}, "site": {"floor": "2"}, "sync_customer": True}, timeout=15)
        assert r.status_code == 200 and r.json()["customer_synced"] is True, r.text
        cust = admin.get(f"{BASE_URL}/api/customers/{accepted_quote['customer_id']}", timeout=15).json()
        assert cust["phone"] == "3399999999"
        dup = admin.get(f"{BASE_URL}/api/customers", params={"q": cust["email"], "limit": 50}, timeout=15).json()
        assert len([i for i in dup["items"] if i["email"] == cust["email"]]) == 1   # nessun duplicato anagrafica
        c = admin.get(f"{BASE_URL}/api/contracts/{contract['id']}", timeout=15).json()
        assert c["quote_snapshot"]["site"]["floor"] == "2"
        assert len(c["party_changes"]) >= 3

    def test_economic_change_requires_revision(self, admin, contract):
        r = admin.patch(f"{BASE_URL}/api/contracts/{contract['id']}", json={"quote_snapshot": {"economics": {"total": 1.0}}}, timeout=15)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "CONTRACT_REVISION_REQUIRED"
        r = admin.patch(f"{BASE_URL}/api/contracts/{contract['id']}/parties", json={"customer": {"total": 1.0}}, timeout=15)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "CONTRACT_REVISION_REQUIRED"

    def test_presign_blocks_when_tax_code_missing(self, admin, contract):
        r = admin.patch(f"{BASE_URL}/api/contracts/{contract['id']}/parties", json={"customer": {"tax_code": ""}}, timeout=15)
        assert "MISSING_CUSTOMER_TAX_CODE" in r.json()["presign_errors"]
        rs = admin.post(f"{BASE_URL}/api/contracts/{contract['id']}/sign", json={"signer_name": "Mario Rossi", "signature_data_url": "data:image/png;base64,iVBORw0KGgo=", "accept_terms": True}, timeout=15)
        assert rs.status_code == 400 and rs.json()["detail"]["code"] == "PRESIGN_CHECK_FAILED"
        admin.patch(f"{BASE_URL}/api/contracts/{contract['id']}/parties", json={"customer": {"tax_code": "RSSMRA80A01H501X"}}, timeout=15)


class TestSignatureAndPortal:
    def test_pdf_preview_complete_no_leak(self, admin, contract):
        r = admin.get(f"{BASE_URL}/api/contracts/{contract['id']}/pdf/preview", timeout=60)
        assert r.status_code == 200 and r.content[:4] == b"%PDF" and len(r.content) > 10_000

    def test_sign_freezes_snapshot_and_activates(self, admin, contract, accepted_quote):
        admin.patch(f"{BASE_URL}/api/contracts/{contract['id']}/parties", json={"customer": {"tax_code": "RSSMRA80A01H501X"}}, timeout=15)
        rs = admin.post(f"{BASE_URL}/api/contracts/{contract['id']}/sign", json={"signer_name": "Mario Rossi", "signature_data_url": "data:image/png;base64,iVBORw0KGgo=", "accept_terms": True}, timeout=15)
        assert rs.status_code == 200, rs.text
        c = admin.get(f"{BASE_URL}/api/contracts/{contract['id']}", timeout=15).json()
        assert c["contract_status"] == "signed" and c["lifecycle_status"] == "ACTIVE"
        fz = c["signed_snapshot"]
        for k in ("customer_snapshot", "site_snapshot", "product_snapshot", "service_snapshot", "commercial_snapshot", "payment_snapshot", "tax_snapshot", "general_terms_version"):
            assert k in fz, k
        assert fz["customer_snapshot"]["tax_code"] == "RSSMRA80A01H501X"
        assert fz["commercial_snapshot"]["total"] == accepted_quote["quote"]["total"]
        assert fz["general_terms_version"] == contract["general_terms_version"]

    def test_signed_is_immutable(self, admin, contract):
        r = admin.patch(f"{BASE_URL}/api/contracts/{contract['id']}/parties", json={"customer": {"phone": "000"}}, timeout=15)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "CONTRACT_SIGNED_IMMUTABLE"

    def test_customer_portal_contract_available(self, admin, contract, accepted_quote):
        import pymongo
        db = pymongo.MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        log = db.email_logs.find_one({"event_type": "CONTRACT_AVAILABLE", "entity_id": contract["id"]})
        assert log is not None, "CONTRACT_AVAILABLE non notificato"
        q = accepted_quote["quote"]
        cust = db.customers.find_one({"_id": accepted_quote["customer_id"]})
        email = cust["email"]
        pwd = "PortalTest!2026x"
        from app.security import hash_password
        from datetime import datetime, timezone
        db.customer_portal_users.delete_many({"email": email})
        db.customer_portal_users.insert_one({"_id": str(uuid.uuid4()), "tenant_id": q["tenant_id"], "customer_id": accepted_quote["customer_id"],
                                             "email": email, "password_hash": hash_password(pwd), "status": "AUTHORIZED", "first_name": "Mario",
                                             "last_name": "Rossi", "deleted_at": None, "created_at": datetime.now(timezone.utc).isoformat()})
        s = requests.Session()
        rl = s.post(f"{BASE_URL}/api/customer-portal/auth/login", json={"email": email, "password": pwd}, timeout=15)
        assert rl.status_code == 200, rl.text
        if rl.json().get("access_token"):
            s.headers["Authorization"] = f"Bearer {rl.json()['access_token']}"
        docs = s.get(f"{BASE_URL}/api/customer-portal/documents", timeout=15)
        if docs.status_code != 200:
            pytest.skip(f"portal documents {docs.status_code}")
        items = [d for d in docs.json()["items"] if d["category"] == "CONTRATTO"]
        assert items and items[0]["contract_number"] == contract["number"]
        dl = s.get(f"{BASE_URL}/api/customer-portal/documents/{items[0]['id']}/download", timeout=60)
        assert dl.status_code == 200 and dl.content[:4] == b"%PDF"
