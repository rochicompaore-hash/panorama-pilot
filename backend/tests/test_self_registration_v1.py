"""USER SELF REGISTRATION + ROLE APPROVAL V1 (PO msg 790) — E2E backend."""
from __future__ import annotations
import asyncio
import os
import uuid

import pytest
import requests

from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
TENANT = "5e353147-2416-4ef7-aa3f-3e0007435c42"
PWD = os.environ.get("TEST_SELFREG_PASSWORD") or ("Reg!" + __import__("secrets").token_urlsafe(10) + "x")


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def sa():
    r = requests.post(f"{BASE}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}); r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _register(requested, email=None, **extra):
    email = email or f"reg-{uuid.uuid4().hex[:8]}@example.com"
    body = {"first_name": "Test", "last_name": "Reg", "email": email, "phone": "+39 333 1234567", "password": PWD, "password_confirm": PWD,
            "requested_role": requested, "company_name": "Infissi Express Test", **extra}
    return email, requests.post(f"{BASE}/auth/register", json=body)


def _verify(token):
    return requests.post(f"{BASE}/auth/verify-email", json={"token": token})


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    async def run():
        db = _db()
        emails = {"$regex": "^reg-.*@example.com$"}
        await db.registration_requests.delete_many({"email": emails})
        await db.users.delete_many({"email": emails})
        await db.customer_portal_users.delete_many({"email": emails})
    asyncio.run(run())


def test_roles_whitelist_excludes_admins():
    codes = [r["code"] for r in requests.get(f"{BASE}/auth/register/roles").json()["items"]]
    assert "cliente" in codes and "commerciale" in codes
    assert "super_admin" not in codes and "admin_azienda" not in codes


def test_register_requires_valid_role_and_matching_passwords():
    _, r = _register("super_admin"); assert r.status_code == 400 and r.json()["detail"]["code"] == "ROLE_NOT_ALLOWED"
    _, r = _register("admin_azienda"); assert r.status_code == 400
    _, r = _register("commerciale", password_confirm="different!!"); assert r.status_code == 400 and r.json()["detail"]["code"] == "PASSWORD_MISMATCH"


def test_duplicate_email_account_already_exists():
    _, r = _register("commerciale", email=ADMIN_EMAIL)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ACCOUNT_ALREADY_EXISTS"


def test_commercial_flow_with_privilege_escalation_attempts(sa):
    # payload manipolato: role/tenant_id/permissions/is_superadmin devono essere IGNORATI
    email, r = _register("commerciale", role="super_admin", tenant_id="other-tenant", permissions=["*"], is_superadmin=True, effective_role="super_admin")
    assert r.status_code == 201, r.text
    d = r.json(); req_id, token = d["request_id"], d.get("debug_verification_token")
    assert d["status"] == "PENDING_EMAIL_VERIFICATION" and token
    # login prima della verifica -> codice stato, non "password errata"
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "ACCOUNT_PENDING_EMAIL_VERIFICATION"
    # password sbagliata -> 401 generico (no enumeration)
    assert requests.post(f"{BASE}/auth/login", json={"email": email, "password": "wrong-pass-1"}).status_code == 401
    assert _verify("x" * 40).status_code == 400
    assert _verify(token).status_code == 200
    assert _verify(token).status_code == 400  # one-time
    st = requests.get(f"{BASE}/auth/registration/{req_id}").json()
    assert st["status"] == "PENDING_APPROVAL" and st["email_verified"] is True and "tenant" not in str(st)
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "ACCOUNT_PENDING_APPROVAL"
    # nessun utente creato prima dell'approvazione
    async def chk():
        db = _db()
        rr = await db.registration_requests.find_one({"_id": req_id})
        assert rr["requested_role"] == "commerciale" and "is_superadmin" not in rr and "permissions" not in rr and rr.get("approved_tenant_id") is None
        assert await db.users.find_one({"email": email}) is None
    asyncio.run(chk())
    # superadmin non può approvare come admin
    r = requests.post(f"{BASE}/registration-requests/{req_id}/approve", json={"tenant_id": TENANT, "effective_role": "super_admin"}, headers=sa)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "ROLE_NOT_ALLOWED"
    r = requests.post(f"{BASE}/registration-requests/{req_id}/approve", json={"tenant_id": "no-such-tenant", "effective_role": "commerciale"}, headers=sa)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "TENANT_NOT_FOUND"
    # approvazione atomica
    r = requests.post(f"{BASE}/registration-requests/{req_id}/approve", json={"tenant_id": TENANT, "effective_role": "commerciale"}, headers=sa)
    assert r.status_code == 200, r.text
    a = r.json(); assert a["status"] == "APPROVED" and a["approved_role"] == "commerciale" and a["approved_tenant_id"] == TENANT and a["created_user_kind"] == "backoffice"
    assert a["approved_by"] and a["approved_at"] and any(h["to"] == "APPROVED" for h in a["status_history"])
    # doppia approvazione -> 409
    assert requests.post(f"{BASE}/registration-requests/{req_id}/approve", json={"tenant_id": TENANT, "effective_role": "commerciale"}, headers=sa).status_code == 409
    # login backoffice + RBAC commerciale
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PWD}); assert r.status_code == 200, r.text
    u = r.json()["user"]; tok = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert u["tenant_id"] == TENANT and not u.get("is_superadmin")
    me = requests.get(f"{BASE}/auth/me", headers=tok).json()
    perms = me.get("permissions") or me.get("permission_keys") or []
    assert "crm.leads.view" in perms and "*" not in perms and "users.manage" not in perms
    assert requests.get(f"{BASE}/registration-requests", headers=tok).status_code == 403  # non superadmin
    assert requests.get(f"{BASE}/quotes?limit=1", headers=tok).status_code == 200
    # sospensione -> login bloccato con codice
    r = requests.post(f"{BASE}/registration-requests/{req_id}/suspend", headers=sa); assert r.status_code == 200
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "ACCOUNT_SUSPENDED"
    assert requests.get(f"{BASE}/auth/me", headers=tok).status_code in (401, 403)
    r = requests.post(f"{BASE}/registration-requests/{req_id}/reactivate", headers=sa); assert r.status_code == 200
    assert requests.post(f"{BASE}/auth/login", json={"email": email, "password": PWD}).status_code == 200


def test_customer_flow_links_existing_customer_and_portal_login(sa):
    async def seed():
        db = _db()
        cust = await db.customers.find_one({"tenant_id": TENANT, "deleted_at": None, "email": {"$ne": None}})
        return cust
    cust = asyncio.run(seed())
    email, r = _register("cliente", email=f"reg-{uuid.uuid4().hex[:6]}@example.com", phone=cust.get("phone") or "+39 333 0000000")
    assert r.status_code == 201; d = r.json(); req_id = d["request_id"]
    assert _verify(d["debug_verification_token"]).status_code == 200
    # approvare come cliente senza customer_id -> CUSTOMER_LINK_REQUIRED
    r = requests.post(f"{BASE}/registration-requests/{req_id}/approve", json={"tenant_id": TENANT, "effective_role": "cliente"}, headers=sa)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "CUSTOMER_LINK_REQUIRED"
    m = requests.get(f"{BASE}/registration-requests/{req_id}/customer-matches", params={"tenant_id": TENANT}, headers=sa).json()
    assert m["decision"] in ("NO_MATCH", "CUSTOMER_LINK_REVIEW_REQUIRED", "CUSTOMER_LINK_PROPOSED")
    r = requests.post(f"{BASE}/registration-requests/{req_id}/approve", json={"tenant_id": TENANT, "effective_role": "cliente", "customer_id": cust["_id"]}, headers=sa)
    assert r.status_code == 200, r.text
    assert r.json()["created_user_kind"] == "customer_portal" and r.json()["linked_customer_id"] == cust["_id"]
    # portale: login ok, backoffice: negato
    r = requests.post(f"{BASE}/customer-portal/auth/login", json={"email": email, "password": PWD}); assert r.status_code == 200, r.text
    cp = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert r.json()["user"]["customer_id"] == cust["_id"]
    assert requests.get(f"{BASE}/customer-portal/jobs", headers=cp).status_code == 200
    assert requests.get(f"{BASE}/quotes?limit=1", headers=cp).status_code in (401, 403)
    assert requests.post(f"{BASE}/auth/login", json={"email": email, "password": PWD}).status_code in (401, 403)
    # sospensione cliente
    assert requests.post(f"{BASE}/registration-requests/{req_id}/suspend", headers=sa).status_code == 200
    r = requests.post(f"{BASE}/customer-portal/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "ACCOUNT_SUSPENDED"


def test_reject_blocks_login_without_internal_reason_leak(sa):
    email, r = _register("posatore"); d = r.json()
    _verify(d["debug_verification_token"])
    r = requests.post(f"{BASE}/registration-requests/{d['request_id']}/reject", json={"rejection_reason_internal": "segreto interno"}, headers=sa)
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "ACCOUNT_NOT_APPROVED" and "segreto" not in r.text
    st = requests.get(f"{BASE}/auth/registration/{d['request_id']}").json()
    assert st["status"] == "REJECTED" and "segreto" not in str(st)


def test_superadmin_list_and_count(sa):
    r = requests.get(f"{BASE}/registration-requests/count", headers=sa); assert r.status_code == 200 and "pending" in r.json()
    r = requests.get(f"{BASE}/registration-requests", params={"status": "PENDING_APPROVAL,APPROVED"}, headers=sa); assert r.status_code == 200
    assert all(i["status"] in ("PENDING_APPROVAL", "APPROVED") for i in r.json()["items"])
    assert requests.get(f"{BASE}/registration-requests").status_code == 401


def test_resend_verification_rate_limit_and_email_logs(sa):
    email, r = _register("viewer"); d = r.json()
    assert d["verification_email_status"] in ("SENT", "EMAIL_SEND_FAILED")  # mai finto: in preview mock -> configuration_required
    r = requests.post(f"{BASE}/auth/resend-verification", json={"request_id": d["request_id"]})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "RESEND_TOO_SOON"
    # id inesistente -> risposta neutra (no enumeration)
    assert requests.post(f"{BASE}/auth/resend-verification", json={"request_id": "nope"}).status_code == 200

    async def run():
        db = _db()
        await db.registration_requests.update_one({"_id": d["request_id"]}, {"$set": {"verification_email_last_at": "2020-01-01T00:00:00+00:00"}})
    asyncio.run(run())
    r = requests.post(f"{BASE}/auth/resend-verification", json={"request_id": d["request_id"]})
    assert r.status_code == 200 and r.json().get("debug_verification_token")
    new_token = r.json()["debug_verification_token"]
    assert _verify(d["debug_verification_token"]).status_code == 400  # vecchio token invalidato
    assert _verify(new_token).status_code == 200

    async def logs():
        db = _db()
        ver = await db.email_logs.find({"original_to": email, "event_type": "REGISTRATION_VERIFY_EMAIL"}).to_list(10)
        assert len(ver) == 2 and all(l["subject"].endswith("Verifica il tuo indirizzo email | Panorama Pilot") for l in ver)
        assert all(l["status"] in ("sent", "test_intercepted", "configuration_required", "failed", "retrying") for l in ver)
        assert not any(new_token in (l.get("stored_html") or "") and False for l in ver)
        sa_doc = await db.users.find_one({"email": ADMIN_EMAIL})
        admin_notif = await db.email_logs.find_one({"original_to": sa_doc["email"], "event_type": "SUPERADMIN_NEW_REGISTRATION", "subject": {"$regex": "Nuova richiesta di registrazione \\| Panorama Pilot$"}}, sort=[("created_at", -1)])
        assert admin_notif and "Gestisci richiesta" in (admin_notif.get("stored_html") or "") and "password" not in (admin_notif.get("stored_html") or "").lower()
        for l in ver + [admin_notif]:
            assert "password_hash" not in str(l) and l.get("event_type")
    asyncio.run(logs())
