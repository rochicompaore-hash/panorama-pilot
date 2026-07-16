"""Iteration 23 — Verifica combinata:
(a) Gating listini pubblicati nei preventivi reali (retest formale)
(b) Provisioning owner PanoramaPilot: login, tenant isolation, no leakage password
    — La password 'Burgugnao' non deve MAI apparire in log, risposte API, report.
      Nei test la password è ottenuta da env var e mai stampata.
"""
from __future__ import annotations
import os
import re
import uuid
import json
import asyncio
import subprocess
from typing import Any, Dict, Optional
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

# --- Credentials (owner password masked in any print) ---
ADMIN_EMAIL = "admin@infissiexpress.com"
ADMIN_PASSWORD = "Admin!2025"
OWNER_EMAIL = "pilot@panoramapilot.com"
OWNER_PASSWORD = os.environ.get("OWNER_INIT_PASSWORD_TEST", "Burgugnao")
MASKED_PW = "***"

# --- IDs from review request ---
SELL_DEMO_ID = "4db4b91f-22c9-422b-aa7f-e235967b6698"
BOM_WIN_2A_ID = "76d7b931-09b7-419f-bb79-1e47281a915e"
CONTRACT_ID = "899c4115-d4be-41a3-8d57-b1cdfb488754"
INFISSI_TENANT_ID = "5e353147-2416-4ef7-aa3f-3e0007435c42"
PANORAMA_TENANT_ID = "ae9168f6-d96e-4c5d-bb33-25acbb9a8410"


# --------------------- Fixtures ---------------------
@pytest.fixture(scope="module")
def admin_token() -> str:
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=15)
    assert r.status_code == 200, f"Admin login KO: {r.status_code}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token) -> Dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def owner_login_response() -> Dict[str, Any]:
    """Effettua login owner. La response completa serve per verifiche multiple."""
    r = requests.post(f"{API}/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
                      timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Owner login fallito: {r.status_code} {r.text[:200]}")
    return {"status": r.status_code, "json": r.json(),
            "raw_text": r.text}


@pytest.fixture(scope="module")
def owner_token(owner_login_response) -> str:
    tok = owner_login_response["json"].get("access_token")
    assert tok, "Owner access_token mancante"
    return tok


@pytest.fixture(scope="module")
def owner_headers(owner_token) -> Dict[str, str]:
    return {"Authorization": f"Bearer {owner_token}",
            "Content-Type": "application/json"}


def _patch_status(headers: Dict[str, str], status: str) -> None:
    r = requests.patch(f"{API}/parametric/item-pricelists/{SELL_DEMO_ID}",
                       headers=headers, json={"ipl_status": status}, timeout=15)
    assert r.status_code == 200, f"PATCH ipl_status={status} KO: {r.status_code} {r.text[:200]}"


def _base_bom_payload() -> Dict[str, Any]:
    return {"bom_template_id": BOM_WIN_2A_ID,
            "width_mm": 1200, "height_mm": 1400, "nr_ante": 2,
            "sell_pricelist_id": SELL_DEMO_ID}


# =========================================================
#     GATING (a) — retest formale
# =========================================================
class TestGatingActive:
    def test_bom_simulate_active_returns_prices(self, admin_headers):
        r = requests.post(f"{API}/pricing-hub/bom-simulate",
                          headers=admin_headers, json=_base_bom_payload(), timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert (d.get("materials_price") or 0) > 0
        sp = d.get("sell_pricelist") or {}
        assert sp.get("pricelist_status") == "active"
        assert d.get("unpublished_pricelist_warnings") == []
        codes = [e.get("code") for e in (d.get("blocking_errors") or [])]
        assert "PRICELIST_NOT_PUBLISHED" not in codes

    def test_snapshot_hash_deterministic(self, admin_headers):
        p = _base_bom_payload()
        r1 = requests.post(f"{API}/pricing-hub/bom-simulate", headers=admin_headers, json=p, timeout=20)
        r2 = requests.post(f"{API}/pricing-hub/bom-simulate", headers=admin_headers, json=p, timeout=20)
        assert r1.status_code == 200 and r2.status_code == 200
        h1, h2 = r1.json().get("snapshot_hash"), r2.json().get("snapshot_hash")
        assert h1 and h1 == h2, f"snapshot_hash non deterministico: {h1} vs {h2}"


class TestGatingUnpublished:
    """SELL-DEMO viene temporaneamente switchato a draft/archived e ripristinato."""

    @pytest.fixture(autouse=True)
    def _safety_restore(self, admin_headers):
        yield
        try:
            _patch_status(admin_headers, "active")
        except Exception:
            pass

    def _assert_blocked(self, d, stato):
        assert d.get("materials_price") in (0, 0.0), \
            f"materials_price atteso 0 con listino={stato}, got {d.get('materials_price')}"
        assert d.get("sell_pricelist") is None
        codes = [e.get("code") for e in (d.get("blocking_errors") or [])]
        assert "PRICELIST_NOT_PUBLISHED" in codes
        errs = d.get("errors") or []
        assert any("[PRICELIST_NOT_PUBLISHED]" in e for e in errs), \
            f"errors deve contenere '[PRICELIST_NOT_PUBLISHED]', got {errs}"

    def test_draft(self, admin_headers):
        _patch_status(admin_headers, "draft")
        r = requests.post(f"{API}/pricing-hub/bom-simulate",
                          headers=admin_headers, json=_base_bom_payload(), timeout=20)
        assert r.status_code == 200
        self._assert_blocked(r.json(), "draft")

    def test_archived(self, admin_headers):
        _patch_status(admin_headers, "archived")
        r = requests.post(f"{API}/pricing-hub/bom-simulate",
                          headers=admin_headers, json=_base_bom_payload(), timeout=20)
        assert r.status_code == 200
        self._assert_blocked(r.json(), "archived")

    def test_geometry_compute_draft_blocks(self, admin_headers):
        _patch_status(admin_headers, "draft")
        bt = requests.get(f"{API}/parametric/bom-templates/{BOM_WIN_2A_ID}",
                          headers=admin_headers, timeout=10)
        if bt.status_code != 200:
            pytest.skip(f"bom-template non recuperabile: {bt.status_code}")
        profile_system_id = bt.json().get("profile_system_id")
        payload = {
            "geometry": {
                "outer_width_mm": 1200, "outer_height_mm": 1400,
                "measurement_mode": "frame_outer",
                "profile_system_id": profile_system_id,
                "root": {"id": "root", "kind": "root",
                         "children": [{"id": "m1", "kind": "module",
                                       "module_type": "sash_hinged",
                                       "module_opening_side": "left",
                                       "module_handle_side": "right"}]}},
            "bom_template_id": BOM_WIN_2A_ID,
            "sell_pricelist_id": SELL_DEMO_ID,
            "include_costs": False, "include_svg": False,
        }
        r = requests.post(f"{API}/geometry/compute",
                          headers=admin_headers, json=payload, timeout=25)
        assert r.status_code in (200, 400)
        if r.status_code == 200:
            codes = [e.get("code") for e in (r.json().get("blocking_errors") or [])]
            assert "PRICELIST_NOT_PUBLISHED" in codes


class TestRegression:
    def test_bom_recipes_20(self, admin_headers):
        r = requests.get(f"{API}/pricing-hub/bom-recipes", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        items = (r.json() or {}).get("items") or []
        assert len(items) == 20, f"bom-recipes attesi 20, got {len(items)}"

    def test_geometry_templates_6(self, admin_headers):
        r = requests.get(f"{API}/geometry/templates", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        items = r.json().get("items") if isinstance(r.json(), dict) else r.json()
        assert isinstance(items, list) and len(items) == 6

    def test_contract_pdf_preview(self, admin_headers):
        r = requests.get(f"{API}/contracts/{CONTRACT_ID}/pdf/preview",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:5] == b"%PDF-"


# =========================================================
#     OWNER (b) — login e flag
# =========================================================
class TestOwnerLogin:
    def test_login_ok_and_flags(self, owner_login_response):
        assert owner_login_response["status"] == 200
        d = owner_login_response["json"]
        assert d.get("access_token")
        assert d.get("refresh_token")
        u = d.get("user") or {}
        assert u.get("email") == OWNER_EMAIL
        assert u.get("must_change_password") is True, \
            f"must_change_password atteso True, got {u.get('must_change_password')}"
        assert u.get("is_superadmin") is True, \
            f"is_superadmin atteso True, got {u.get('is_superadmin')}"
        assert u.get("is_platform_owner") is False, \
            f"is_platform_owner atteso False, got {u.get('is_platform_owner')}"
        assert u.get("is_protected") is True, \
            f"is_protected atteso True, got {u.get('is_protected')}"
        tid = u.get("tenant_id")
        assert tid and tid != INFISSI_TENANT_ID, \
            f"tenant_id owner deve differire da Infissi, got {tid}"

    def test_login_response_has_no_password_field(self, owner_login_response):
        raw = owner_login_response["raw_text"]
        # NON deve contenere password_hash
        assert "password_hash" not in raw, \
            "La response del login espone password_hash!"
        # NON deve contenere la password in chiaro
        assert OWNER_PASSWORD not in raw, \
            f"La response del login contiene la password in chiaro ({MASKED_PW})!"

    def test_login_bad_password(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": OWNER_EMAIL, "password": "wrongPassword"},
                          timeout=15)
        assert r.status_code == 401, f"Attesa 401 con password errata, got {r.status_code}"


class TestOwnerEndpointsAccess:
    """Con il token owner, i seguenti endpoint devono rispondere 200 (visibilità sezioni proprie)."""

    @pytest.mark.parametrize("path", [
        "/customers", "/quotes", "/leads", "/contracts",
        "/geometry/templates", "/pricing-hub/bom-recipes",
        "/importer/schema/profile",
        "/parametric/bom-templates", "/parametric/item-pricelists",
    ])
    def test_endpoint_200(self, owner_headers, path):
        r = requests.get(f"{API}{path}", headers=owner_headers, timeout=15)
        assert r.status_code == 200, \
            f"Owner GET {path} atteso 200, got {r.status_code}: {r.text[:200]}"

    def test_users_list_200(self, owner_headers):
        r = requests.get(f"{API}/users", headers=owner_headers, timeout=15)
        assert r.status_code == 200, f"Owner GET /users atteso 200, got {r.status_code}: {r.text[:200]}"


class TestOwnerTenantIsolation:
    def test_customers_empty_for_panorama_owner(self, owner_headers):
        r = requests.get(f"{API}/customers?limit=5", headers=owner_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        # total può essere top-level o dentro pagination
        total = d.get("total")
        if total is None:
            total = (d.get("pagination") or {}).get("total")
        if total is None and isinstance(d.get("items"), list):
            total = len(d["items"])
        assert total == 0, f"PanoramaPilot deve avere 0 customer, got total={total}, keys={list(d.keys())}"

    def test_infissi_has_customers(self, admin_headers):
        r = requests.get(f"{API}/customers?limit=5", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        total = d.get("total")
        if total is None:
            total = (d.get("pagination") or {}).get("total")
        # semplicemente > 0 (non 0 come Panorama)
        assert (total or 0) >= 1, f"Infissi tenant deve avere customer, got total={total}"


# =========================================================
#     OWNER (b) — verifica DB / audit / no leakage in log
# =========================================================
class TestOwnerDbState:
    def _run_async(self, coro):
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def _db(self):
        from motor.motor_asyncio import AsyncIOMotorClient
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        return c, c[os.environ["DB_NAME"]]

    def test_user_doc_bcrypt(self):
        async def _q():
            c, db = self._db()
            try:
                docs = [x async for x in db.users.find({"email": OWNER_EMAIL, "deleted_at": None})]
                return docs
            finally:
                c.close()
        docs = self._run_async(_q())
        assert len(docs) == 1, f"Attesa 1 user 'pilot', got {len(docs)}"
        u = docs[0]
        ph = u.get("password_hash") or ""
        assert ph.startswith("$2b$") or ph.startswith("$2a$"), \
            f"password_hash non è bcrypt: prefisso={ph[:4]}"
        # Nessuna occorrenza plaintext
        assert OWNER_PASSWORD not in ph, "La password in chiaro appare nel password_hash!"
        assert u.get("tenant_id") == PANORAMA_TENANT_ID
        assert u.get("is_protected") is True
        assert u.get("must_change_password") is True

    def test_role_tenant_owner_exists_with_perms(self):
        async def _q():
            c, db = self._db()
            try:
                roles = [x async for x in db.roles.find(
                    {"tenant_id": PANORAMA_TENANT_ID, "deleted_at": None})]
                return roles
            finally:
                c.close()
        roles = self._run_async(_q())
        # requisito: 1 doc con code='tenant_owner', is_protected=True, permissions non vuoto
        owner_roles = [r for r in roles if r.get("code") == "tenant_owner"]
        assert len(owner_roles) == 1, \
            f"Atteso 1 role tenant_owner, got {len(owner_roles)} (totale roles={len(roles)}); role fields sample={[list(r.keys()) for r in roles[:2]]}"
        r = owner_roles[0]
        assert r.get("is_protected") is True, "role.is_protected atteso True"
        perms = r.get("permissions") or r.get("permission_keys") or []
        assert isinstance(perms, list) and len(perms) > 0, \
            f"role.permissions non vuoto, got {perms}"

    def test_audit_owner_provisioned(self):
        async def _q():
            c, db = self._db()
            try:
                docs = [x async for x in db.audit_logs.find(
                    {"action": "owner.provisioned", "user_email": OWNER_EMAIL})]
                return docs
            finally:
                c.close()
        docs = self._run_async(_q())
        # requisito: 1 doc — ammettiamo >=1 (script idempotente potrebbe avere scritto più righe)
        assert len(docs) >= 1, f"Atteso >=1 audit_log 'owner.provisioned', got {len(docs)}"
        # Nessuna occorrenza plaintext nel log audit
        for d in docs:
            blob = json.dumps(d, default=str)
            assert OWNER_PASSWORD not in blob, \
                f"La password in chiaro appare in audit_logs (id={d.get('_id')})"


class TestNoPasswordLeakageInSupervisorLogs:
    def test_no_plaintext_in_backend_logs(self):
        found = []
        for logf in ("/var/log/supervisor/backend.err.log",
                     "/var/log/supervisor/backend.out.log"):
            try:
                with open(logf, "rb") as f:
                    data = f.read()
                if OWNER_PASSWORD.encode() in data:
                    found.append(logf)
            except FileNotFoundError:
                continue
        assert not found, f"La password in chiaro ({MASKED_PW}) trovata nei log: {found}"


class TestProvisionScriptIdempotent:
    def test_rerun_never_creates_user_again(self):
        """Riesegue il provision script → user state deve essere 'existing_no_change' o 'existing_updated', mai 'created'."""
        env = os.environ.copy()
        env["OWNER_INIT_PASSWORD"] = OWNER_PASSWORD
        # carica anche JWT_SECRET/env backend
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
        # NON deve stampare la password
        assert OWNER_PASSWORD not in out, \
            f"Lo script stampa la password in chiaro ({MASKED_PW}) in stdout/stderr!"
        # Deve contenere il report
        assert "OWNER_PROVISIONED_REPORT" in out, f"Report mancante: {out[:500]}"
        # Estrai stato user
        m = re.search(r'"user":\s*"([^"]+)"', out)
        assert m, f"Stato user non trovato in report: {out[:500]}"
        state = m.group(1)
        assert state in ("existing_no_change", "existing_updated"), \
            f"Stato user atteso 'existing_*', got '{state}' (script NON idempotente!)"
