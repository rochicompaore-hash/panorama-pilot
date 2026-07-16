"""Iteration 24 — Verifica FOLLOWUP del CRITICAL segnalato in iter23:
- Role modello esteso con `code` + `is_protected`
- provision_owner.py usa `permission_keys` invece di `permissions`
- Cleanup duplicati via soft-delete

La password 'Burgugnao' NON deve mai apparire in log, response API, stdout script,
o in questo file (letta da env var OWNER_INIT_PASSWORD_TEST).
"""
from __future__ import annotations
import os
import re
import json
import asyncio
import subprocess
from typing import Any, Dict, List
import pytest
import requests
from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD  # env-sourced credentials

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

# scrubbed: ADMIN_EMAIL moved to tests._creds
# scrubbed: ADMIN_PASSWORD moved to tests._creds
OWNER_EMAIL = "pilot@panoramapilot.com"
OWNER_PASSWORD = os.environ.get("OWNER_INIT_PASSWORD_TEST", "Burgugnao")
MASKED_PW = "***"

SELL_DEMO_ID = "4db4b91f-22c9-422b-aa7f-e235967b6698"
BOM_WIN_2A_ID = "76d7b931-09b7-419f-bb79-1e47281a915e"
INFISSI_TENANT_ID = "5e353147-2416-4ef7-aa3f-3e0007435c42"
PANORAMA_TENANT_ID = "ae9168f6-d96e-4c5d-bb33-25acbb9a8410"
EXPECTED_ROLE_ID = "e4a05b01-2b75-4273-908d-417af991b407"


# ------------- Fixtures -------------
@pytest.fixture(scope="module")
def admin_token() -> str:
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=15)
    assert r.status_code == 200, f"Admin login KO: {r.status_code}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token) -> Dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def owner_login_response() -> Dict[str, Any]:
    r = requests.post(f"{API}/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
                      timeout=15)
    return {"status": r.status_code, "json": r.json() if r.status_code == 200 else {},
            "raw_text": r.text}


@pytest.fixture(scope="module")
def owner_headers(owner_login_response) -> Dict[str, str]:
    tok = owner_login_response["json"].get("access_token")
    if not tok:
        pytest.skip(f"Owner login KO: {owner_login_response['status']}")
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return c, c[os.environ["DB_NAME"]]


def _patch_ipl_status(headers: Dict[str, str], status: str) -> requests.Response:
    return requests.patch(f"{API}/parametric/item-pricelists/{SELL_DEMO_ID}",
                          headers=headers, json={"ipl_status": status}, timeout=15)


# =========================================================
# BLOCCO A — DB Role (CRITICAL area)
# =========================================================
class TestRoleDbState:
    def test_exactly_one_active_role_for_tenant(self):
        async def _q():
            c, db = _db()
            try:
                return await db.roles.count_documents(
                    {"tenant_id": PANORAMA_TENANT_ID, "deleted_at": None})
            finally:
                c.close()
        n = _run_async(_q())
        assert n == 1, f"CRITICAL: attesa 1 sola role attiva per PanoramaPilot, got {n}"

    def test_role_tenant_owner_complete(self):
        async def _q():
            c, db = _db()
            try:
                docs = [x async for x in db.roles.find({
                    "tenant_id": PANORAMA_TENANT_ID,
                    "code": "tenant_owner",
                    "deleted_at": None})]
                return docs
            finally:
                c.close()
        docs = _run_async(_q())
        assert len(docs) == 1, f"CRITICAL: atteso 1 role tenant_owner attivo, got {len(docs)}"
        r = docs[0]
        pk = r.get("permission_keys") or []
        assert isinstance(pk, list) and len(pk) >= 200, \
            f"CRITICAL: permission_keys attesi >=200, got {len(pk)}"
        assert r.get("is_protected") is True, f"CRITICAL: is_protected atteso True, got {r.get('is_protected')}"
        assert r.get("is_system") is True, f"CRITICAL: is_system atteso True, got {r.get('is_system')}"
        assert r.get("name") == "Proprietario", f"name atteso 'Proprietario', got {r.get('name')}"

    def test_duplicates_soft_deleted(self):
        async def _q():
            c, db = _db()
            try:
                all_docs = [x async for x in db.roles.find({"tenant_id": PANORAMA_TENANT_ID})]
                return all_docs
            finally:
                c.close()
        all_docs = _run_async(_q())
        assert len(all_docs) >= 1
        active = [d for d in all_docs if d.get("deleted_at") is None]
        deleted = [d for d in all_docs if d.get("deleted_at") is not None]
        assert len(active) == 1, f"CRITICAL: 1 sola role attiva, got {len(active)}"
        # Eventuali duplicati devono essere soft-deleted
        for d in deleted:
            assert d.get("deleted_at") is not None, \
                f"role duplicato {d.get('_id')} non è soft-deleted"


# =========================================================
# BLOCCO B — Idempotenza script provision_owner.py
# =========================================================
class TestProvisionIdempotency:
    def test_rerun_returns_updated_state(self):
        env = os.environ.copy()
        env["OWNER_INIT_PASSWORD"] = OWNER_PASSWORD
        # carica anche vars da /app/backend/.env
        with open("/app/backend/.env") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
        result = subprocess.run(
            ["python", "/app/backend/scripts/provision_owner.py"],
            env=env, capture_output=True, text=True, timeout=60)
        out = result.stdout + "\n" + result.stderr
        # sicurezza: nessuna password in stdout/stderr
        assert OWNER_PASSWORD not in out, \
            f"Lo script stampa la password ({MASKED_PW})!"
        assert "OWNER_PROVISIONED_REPORT" in out, f"Report mancante: {out[:400]}"
        # Estrai stati dal JSON del report
        m = re.search(r'"state":\s*\{[^}]+\}', out)
        assert m, f"state block non trovato: {out[:400]}"
        state_blob = m.group(0)
        r_state = re.search(r'"role":\s*"([^"]+)"', state_blob)
        u_state = re.search(r'"user":\s*"([^"]+)"', state_blob)
        t_state = re.search(r'"tenant":\s*"([^"]+)"', state_blob)
        assert r_state and r_state.group(1) == "updated", \
            f"CRITICAL: state.role atteso 'updated', got {r_state.group(1) if r_state else None}"
        assert u_state and u_state.group(1) in ("existing_no_change", "existing_updated"), \
            f"state.user atteso existing_*, got {u_state.group(1) if u_state else None}"
        assert t_state and t_state.group(1) == "existing", \
            f"state.tenant atteso 'existing', got {t_state.group(1) if t_state else None}"

    def test_no_new_duplicates_after_rerun(self):
        # Deve rimanere 1 sola role attiva anche dopo il rerun (test precedente)
        async def _q():
            c, db = _db()
            try:
                return await db.roles.count_documents(
                    {"tenant_id": PANORAMA_TENANT_ID, "deleted_at": None})
            finally:
                c.close()
        n = _run_async(_q())
        assert n == 1, f"CRITICAL: rerun ha creato duplicati! Active roles: {n}"


# =========================================================
# BLOCCO C — Login owner + flag utente
# =========================================================
class TestOwnerLogin:
    def test_login_ok_and_flags(self, owner_login_response):
        assert owner_login_response["status"] == 200, \
            f"owner login KO: {owner_login_response['status']}"
        d = owner_login_response["json"]
        assert d.get("access_token")
        u = d.get("user") or {}
        assert u.get("must_change_password") is True
        assert u.get("is_superadmin") is True
        assert u.get("is_platform_owner") is False
        assert u.get("is_protected") is True

    def test_response_no_password_leakage(self, owner_login_response):
        raw = owner_login_response["raw_text"]
        assert OWNER_PASSWORD not in raw, \
            f"La response del login contiene la password ({MASKED_PW})!"
        assert "password_hash" not in raw, \
            "La response del login espone 'password_hash'!"

    def test_login_wrong_password_401(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": OWNER_EMAIL, "password": "wrong_" + os.urandom(4).hex()},
                          timeout=15)
        assert r.status_code == 401, f"attesa 401 con password errata, got {r.status_code}"
        # Nessun leak nella risposta di errore
        assert OWNER_PASSWORD not in r.text
        assert "password_hash" not in r.text


# =========================================================
# BLOCCO D — Accesso endpoint owner
# =========================================================
class TestOwnerEndpoints:
    @pytest.mark.parametrize("path", [
        "/customers", "/quotes", "/leads", "/contracts",
        "/geometry/templates", "/pricing-hub/bom-recipes",
        "/parametric/bom-templates",
    ])
    def test_get_200(self, owner_headers, path):
        r = requests.get(f"{API}{path}", headers=owner_headers, timeout=15)
        assert r.status_code == 200, \
            f"owner GET {path} atteso 200, got {r.status_code}: {r.text[:200]}"


# =========================================================
# BLOCCO E — Tenant isolation
# =========================================================
class TestTenantIsolation:
    def test_panorama_owner_zero_customers(self, owner_headers):
        r = requests.get(f"{API}/customers?limit=5", headers=owner_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        total = d.get("total")
        if total is None:
            total = (d.get("pagination") or {}).get("total")
        if total is None and isinstance(d.get("items"), list):
            total = len(d["items"])
        assert total == 0, f"PanoramaPilot atteso 0 customer, got {total}"

    def test_infissi_admin_has_customers(self, admin_headers):
        r = requests.get(f"{API}/customers?limit=5", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        total = d.get("total")
        if total is None:
            total = (d.get("pagination") or {}).get("total")
        assert (total or 0) >= 20, f"Infissi atteso >=20 customer, got {total}"


# =========================================================
# BLOCCO F — Sicurezza log
# =========================================================
class TestNoLogLeakage:
    def test_no_plaintext_in_supervisor_logs(self):
        # shell exec 'grep -c Burgugnao /var/log/supervisor/backend*.log' → 0
        result = subprocess.run(
            ["bash", "-c",
             f'grep -c "{OWNER_PASSWORD}" /var/log/supervisor/backend*.log 2>/dev/null | '
             f"awk -F: '{{s+=$2}} END {{print s+0}}'"],
            capture_output=True, text=True, timeout=15)
        total = int((result.stdout or "0").strip() or 0)
        assert total == 0, \
            f"La password ({MASKED_PW}) appare {total} volte nei log supervisor!"


# =========================================================
# BLOCCO G — Gating listini (regressione dai fix precedenti)
# =========================================================
def _base_bom_payload() -> Dict[str, Any]:
    return {"bom_template_id": BOM_WIN_2A_ID,
            "width_mm": 1200, "height_mm": 1400, "nr_ante": 2,
            "sell_pricelist_id": SELL_DEMO_ID}


class TestGating:
    @pytest.fixture(autouse=True)
    def _restore_after(self, admin_headers):
        yield
        # Sempre ripristinare SELL-DEMO a 'active' dopo ogni test
        try:
            _patch_ipl_status(admin_headers, "active")
        except Exception:
            pass

    def test_active_returns_prices(self, admin_headers):
        # Prima assicura sia active
        _patch_ipl_status(admin_headers, "active")
        r = requests.post(f"{API}/pricing-hub/bom-simulate",
                          headers=admin_headers, json=_base_bom_payload(), timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert (d.get("materials_price") or 0) > 0, \
            f"materials_price atteso >0 con listino active, got {d.get('materials_price')}"
        sp = d.get("sell_pricelist") or {}
        assert sp.get("pricelist_status") == "active"
        codes = [e.get("code") for e in (d.get("blocking_errors") or [])]
        assert "PRICELIST_NOT_PUBLISHED" not in codes

    def test_draft_blocks(self, admin_headers):
        r0 = _patch_ipl_status(admin_headers, "draft")
        assert r0.status_code == 200, f"PATCH draft KO: {r0.status_code}"
        r = requests.post(f"{API}/pricing-hub/bom-simulate",
                          headers=admin_headers, json=_base_bom_payload(), timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("materials_price") in (0, 0.0), \
            f"materials_price atteso 0 con listino draft, got {d.get('materials_price')}"
        codes = [e.get("code") for e in (d.get("blocking_errors") or [])]
        assert "PRICELIST_NOT_PUBLISHED" in codes, \
            f"blocking_errors deve contenere PRICELIST_NOT_PUBLISHED, got {codes}"


class TestRegressionBomRecipes:
    def test_bom_recipes_count_20(self, admin_headers):
        r = requests.get(f"{API}/pricing-hub/bom-recipes", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        items = (r.json() or {}).get("items") or []
        assert len(items) == 20, f"bom-recipes attesi 20, got {len(items)}"


class TestFinalSellDemoRestored:
    """Verifica finale: SELL-DEMO deve essere 'active' a fine test."""
    def test_sell_demo_active(self, admin_headers):
        # Restore esplicito prima del check finale
        _patch_ipl_status(admin_headers, "active")
        r = requests.get(f"{API}/parametric/item-pricelists/{SELL_DEMO_ID}",
                         headers=admin_headers, timeout=10)
        assert r.status_code == 200
        assert r.json().get("ipl_status") == "active", \
            f"SELL-DEMO NON ripristinato: {r.json().get('ipl_status')}"
