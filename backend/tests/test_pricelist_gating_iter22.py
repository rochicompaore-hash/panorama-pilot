"""Iteration 22 — Pricelist publication gating tests.

Verifica il vincolo di pubblicazione dei listini nei preventivi reali:
  - Solo listini con ipl_status='active' possono generare prezzi validi
  - Listini draft/archived → materials_price=0, blocking_errors PRICELIST_NOT_PUBLISHED
  - Snapshot completo (bom+versione+hash), snapshot_hash deterministico
  - Preventivo con opening_products bloccanti non può essere inviato ('sent')
  - Costi interni non visibili ai commerciali (redazione automatica)
  - Tenant isolation su item-pricelists
  - Regressioni: bom-recipes 20, geometry/templates 6, /contracts list, PDF preview
"""
from __future__ import annotations
import os
import copy
import uuid
from typing import Any, Dict, Optional
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@infissiexpress.com"
ADMIN_PASSWORD = "Admin!2025"

SELL_DEMO_ID = "4db4b91f-22c9-422b-aa7f-e235967b6698"
BOM_WIN_2A_ID = "76d7b931-09b7-419f-bb79-1e47281a915e"
CONTRACT_ID = "899c4115-d4be-41a3-8d57-b1cdfb488754"


# ---------- Fixtures ----------

@pytest.fixture(scope="module")
def admin_token() -> str:
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=15)
    assert r.status_code == 200, f"Login fallito: {r.status_code} {r.text}"
    tok = r.json().get("access_token")
    assert tok, "Nessun access_token restituito"
    return tok


@pytest.fixture(scope="module")
def admin_headers(admin_token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def me(admin_headers: Dict[str, str]) -> Dict[str, Any]:
    r = requests.get(f"{API}/auth/me", headers=admin_headers, timeout=10)
    assert r.status_code == 200
    return r.json()


# ---------- Helper ----------

def _base_bom_payload(sell_id: Optional[str] = SELL_DEMO_ID) -> Dict[str, Any]:
    return {
        "bom_template_id": BOM_WIN_2A_ID,
        "width_mm": 1200,
        "height_mm": 1400,
        "nr_ante": 2,
        "sell_pricelist_id": sell_id,
    }


def _patch_status(headers: Dict[str, str], status: str) -> None:
    r = requests.patch(f"{API}/parametric/item-pricelists/{SELL_DEMO_ID}",
                       headers=headers, json={"ipl_status": status}, timeout=15)
    assert r.status_code == 200, f"PATCH ipl_status={status} fallito: {r.status_code} {r.text}"
    got = r.json().get("ipl_status")
    assert got == status, f"Stato non aggiornato: expected={status} got={got}"


# ---------- Test: bom-simulate happy path (active) ----------

class TestBomSimulateActive:
    """SELL-DEMO in stato 'active' → prezzi validi, nessun blocco."""

    def test_active_returns_prices(self, admin_headers):
        r = requests.post(f"{API}/pricing-hub/bom-simulate",
                          headers=admin_headers, json=_base_bom_payload(),
                          timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        # Prezzi > 0
        assert (d.get("materials_price") or 0) > 0, \
            f"materials_price atteso >0, got {d.get('materials_price')}"
        # sell_pricelist meta include pricelist_status='active'
        sp = d.get("sell_pricelist") or {}
        assert sp.get("pricelist_status") == "active", \
            f"sell_pricelist.pricelist_status atteso 'active', got {sp}"
        assert sp.get("pricelist_id") == SELL_DEMO_ID
        # Nessun warning listino non pubblicato
        assert d.get("unpublished_pricelist_warnings") == [], \
            f"unpublished_pricelist_warnings deve essere vuoto, got {d.get('unpublished_pricelist_warnings')}"
        # Nessun blocking_error PRICELIST_NOT_PUBLISHED
        codes = [e.get("code") for e in (d.get("blocking_errors") or [])]
        assert "PRICELIST_NOT_PUBLISHED" not in codes, \
            f"Non ci devono essere blocking_errors PRICELIST_NOT_PUBLISHED, got {codes}"

    def test_snapshot_includes_pricelist_ids(self, admin_headers):
        r = requests.post(f"{API}/pricing-hub/bom-simulate",
                          headers=admin_headers, json=_base_bom_payload(),
                          timeout=20)
        assert r.status_code == 200
        snap = r.json().get("snapshot") or {}
        assert snap.get("sell_pricelist_id") == SELL_DEMO_ID
        # cost_pricelist_id chiave presente (None ammesso)
        assert "cost_pricelist_id" in snap
        # BOM + versione
        assert snap.get("bom_template_id") == BOM_WIN_2A_ID
        assert "bom_version" in snap
        assert "profile_system_id" in snap
        assert "profile_system_version" in snap

    def test_snapshot_hash_deterministic(self, admin_headers):
        payload = _base_bom_payload()
        r1 = requests.post(f"{API}/pricing-hub/bom-simulate",
                            headers=admin_headers, json=payload, timeout=20)
        r2 = requests.post(f"{API}/pricing-hub/bom-simulate",
                            headers=admin_headers, json=payload, timeout=20)
        assert r1.status_code == 200 and r2.status_code == 200
        h1 = r1.json().get("snapshot_hash")
        h2 = r2.json().get("snapshot_hash")
        assert h1 and h2 and h1 == h2, \
            f"snapshot_hash non deterministico: {h1} vs {h2}"


# ---------- Test: bom-simulate con listino draft/archived ----------

class TestBomSimulateUnpublished:
    """Listino in stato draft/archived → non utilizzabile, blocking error."""

    @pytest.fixture(autouse=True)
    def _restore_active(self, admin_headers):
        """Post-test: ripristina sempre SELL-DEMO a 'active' (safety)."""
        yield
        try:
            _patch_status(admin_headers, "active")
        except Exception:
            pass  # best-effort

    def _assert_blocked(self, d: Dict[str, Any], stato: str) -> None:
        assert d.get("materials_price") == 0 or d.get("materials_price") == 0.0, \
            f"materials_price deve essere 0 quando listino='{stato}', got {d.get('materials_price')}"
        assert d.get("sell_pricelist") is None, \
            f"sell_pricelist deve essere None (listino non pubblicato), got {d.get('sell_pricelist')}"
        codes = [e.get("code") for e in (d.get("blocking_errors") or [])]
        assert "PRICELIST_NOT_PUBLISHED" in codes, \
            f"blocking_errors deve contenere PRICELIST_NOT_PUBLISHED, got {codes}"
        assert d.get("unpublished_pricelist_warnings"), \
            "unpublished_pricelist_warnings non deve essere vuoto"
        # errors stringhe formattate
        errs = d.get("errors") or []
        assert any("[PRICELIST_NOT_PUBLISHED]" in e for e in errs), \
            f"errors deve contenere '[PRICELIST_NOT_PUBLISHED]', got {errs}"

    def test_draft_blocks_pricing(self, admin_headers):
        _patch_status(admin_headers, "draft")
        r = requests.post(f"{API}/pricing-hub/bom-simulate",
                          headers=admin_headers, json=_base_bom_payload(),
                          timeout=20)
        assert r.status_code == 200, r.text
        self._assert_blocked(r.json(), "draft")

    def test_archived_blocks_pricing(self, admin_headers):
        _patch_status(admin_headers, "archived")
        r = requests.post(f"{API}/pricing-hub/bom-simulate",
                          headers=admin_headers, json=_base_bom_payload(),
                          timeout=20)
        assert r.status_code == 200, r.text
        self._assert_blocked(r.json(), "archived")

    def test_geometry_compute_draft_blocks(self, admin_headers):
        """POST /api/geometry/compute con sell listino in draft →
        blocking_errors deve contenere PRICELIST_NOT_PUBLISHED (via resolve_bom_full)."""
        _patch_status(admin_headers, "draft")
        # Fetch profile_system_id dal BOM template per garantire coerenza
        bom_r = requests.get(f"{API}/parametric/bom-templates/{BOM_WIN_2A_ID}",
                              headers=admin_headers, timeout=10)
        if bom_r.status_code != 200:
            pytest.skip(f"bom-template non recuperabile: {bom_r.status_code}")
        profile_system_id = bom_r.json().get("profile_system_id")
        assert profile_system_id
        geometry = {
            "outer_width_mm": 1200, "outer_height_mm": 1400,
            "measurement_mode": "frame_outer",
            "profile_system_id": profile_system_id,
            "root": {
                "id": "root", "kind": "root",
                "children": [
                    {"id": "m1", "kind": "module",
                     "module_type": "sash_hinged",
                     "module_opening_side": "left",
                     "module_handle_side": "right"}
                ],
            },
        }
        payload = {
            "geometry": geometry,
            "bom_template_id": BOM_WIN_2A_ID,
            "sell_pricelist_id": SELL_DEMO_ID,
            "include_costs": False,
            "include_svg": False,
        }
        r = requests.post(f"{API}/geometry/compute",
                          headers=admin_headers, json=payload, timeout=25)
        # Accept both 200 with blocking_errors OR 400
        assert r.status_code in (200, 400), r.text
        if r.status_code == 200:
            d = r.json()
            codes = [e.get("code") for e in (d.get("blocking_errors") or [])]
            assert "PRICELIST_NOT_PUBLISHED" in codes, \
                f"geometry/compute deve segnalare PRICELIST_NOT_PUBLISHED con listino draft, got codes={codes}"


# ---------- Test: change_status 'sent' bloccato ----------

class TestQuoteSendBlocked:
    """Preventivo con opening_products con blocking_errors → non inviabile.

    Verifica statica (a livello di codice) del gate in quotes.py:445-462.
    Poi verifica funzionalmente creando un opening_product fittizio se possibile.
    """

    def test_code_guard_present(self):
        """Verifica che il codice di gating esista in quotes.py (safety net)."""
        with open("/app/backend/app/routers/quotes.py", "r") as f:
            src = f.read()
        assert 'new == "sent"' in src
        assert "blocking_errors" in src
        assert "Preventivo non inviabile" in src, \
            "Il messaggio 'Preventivo non inviabile' deve essere presente nel gate"

    def test_send_blocked_functional(self, admin_headers, me):
        """Crea un quote e un opening_product con blocking_errors direttamente in Mongo,
        poi verifica che il gate su /quotes/{id}/status con new_status='sent' torni 400.
        Motivazione: opening_products non ha endpoint HTTP di creazione diretta esposto.
        Cleanup deterministico alla fine per non alterare l'ambiente."""
        import asyncio
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError:
            pytest.skip("motor non disponibile")
        mongo_url = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
        db_name = os.environ.get("DB_NAME") or "infissi_express"

        tenant_id = (me.get("user") or {}).get("tenant_id") or me.get("tenant_id")
        assert tenant_id, "tenant_id assente da /auth/me"

        # Trova cliente esistente
        rc = requests.get(f"{API}/customers?limit=1", headers=admin_headers, timeout=10)
        if rc.status_code != 200:
            pytest.skip(f"customers list non disponibile: {rc.status_code}")
        clist = rc.json()
        cust_items = clist if isinstance(clist, list) else (clist.get("items") or [])
        if not cust_items:
            pytest.skip("Nessun customer disponibile per creare quote di test")
        cust_id = cust_items[0].get("id") or cust_items[0].get("_id")

        # Crea quote in draft via API
        rq = requests.post(f"{API}/quotes", headers=admin_headers, json={
            "customer_id": cust_id,
            "title": "TEST_ITER22_quote_send_blocked",
            "lines": [],
        }, timeout=15)
        if rq.status_code not in (200, 201):
            pytest.skip(f"POST /quotes non riuscito ({rq.status_code}): {rq.text[:200]}")
        qid = (rq.json().get("id") or rq.json().get("_id"))
        assert qid

        op_id = f"TEST_OP_{uuid.uuid4().hex[:8]}"

        async def _seed_and_cleanup():
            client = AsyncIOMotorClient(mongo_url)
            try:
                db = client[db_name]
                # 1) Inserisci opening_product con blocking_errors
                await db.opening_products.insert_one({
                    "_id": op_id,
                    "tenant_id": tenant_id,
                    "quote_id": qid,
                    "code": op_id,
                    "name": "TEST product w/ blocking error",
                    "quantity": 1,
                    "deleted_at": None,
                    "blocking_errors": [{
                        "code": "PRICELIST_NOT_PUBLISHED",
                        "message": "Test blocking error",
                        "severity": "blocking",
                    }],
                })
                return True
            finally:
                client.close()

        async def _cleanup():
            client = AsyncIOMotorClient(mongo_url)
            try:
                db = client[db_name]
                await db.opening_products.delete_one({"_id": op_id})
                await db.quotes.delete_one({"_id": qid})
            finally:
                client.close()

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_seed_and_cleanup())
            # 2) Tenta transizione a 'sent' → 400
            rs = requests.post(f"{API}/quotes/{qid}/status",
                                headers=admin_headers,
                                json={"new_status": "sent"}, timeout=15)
            assert rs.status_code == 400, \
                f"Attesa 400 su sent con prodotti bloccati, got {rs.status_code}: {rs.text}"
            try:
                detail = rs.json().get("detail", "")
            except Exception:
                detail = rs.text
            assert "Preventivo non inviabile" in detail, \
                f"Messaggio errore atteso, got: {detail}"
            assert "prodotto" in detail.lower(), \
                f"Messaggio deve menzionare 'prodotti', got: {detail}"
        finally:
            try:
                loop.run_until_complete(_cleanup())
            except Exception:
                pass
            loop.close()


# ---------- Test: costi interni non visibili ai commerciali ----------

class TestCostsRedactedForCommercial:
    """Utente senza permessi pricelists.manage/quotes.view_costs/pricing.mode.view_cost_basis
    → deve ricevere materials_cost=None, unit_cost=None, cost_redacted=True."""

    def test_code_gate_present(self):
        """Verifica gate statico nel pricing_hub.py (redazione costi)."""
        with open("/app/backend/app/routers/pricing_hub.py", "r") as f:
            src = f.read()
        assert "cost_redacted" in src
        assert "quotes.view_costs" in src
        assert "pricing.mode.view_cost_basis" in src
        assert 'c["unit_cost"] = None' in src or "unit_cost'] = None" in src

    def test_functional_redaction_with_low_perm_user(self, admin_headers):
        """Prova a creare un utente con solo quotes.view e verificare redazione.
        Usa il flusso completo di invitation (POST /users → invitation_url →
        POST /auth/accept-invitation con password).
        """
        # Prima verifica che l'admin (superadmin) NON è redatto
        r = requests.post(f"{API}/pricing-hub/bom-simulate",
                          headers=admin_headers, json=_base_bom_payload(),
                          timeout=20)
        assert r.status_code == 200
        d_admin = r.json()
        # Admin superadmin → cost_redacted assente o False
        assert not d_admin.get("cost_redacted"), \
            f"Superadmin non deve avere costi redatti, got cost_redacted={d_admin.get('cost_redacted')}"

        low_email = f"test_low_{uuid.uuid4().hex[:6]}@test.com"
        low_pw = "TestLow!2025"
        # Ruolo 'Commerciale' esistente (system role) — ha pricelists.view + quotes.view
        # ma NON ha pricelists.manage / quotes.view_costs / pricing.mode.view_cost_basis
        # → cost_redacted deve essere True
        COMMERCIALE_ROLE_ID = "c9015476-9167-48f9-a7e3-9cf594c78f9d"
        create_payload = {
            "email": low_email,
            "password": low_pw,   # ignorato lato server (usa invitation)
            "first_name": "Test",
            "last_name": "Low",
            "role_ids": [COMMERCIALE_ROLE_ID],
        }
        ru = requests.post(f"{API}/users", headers=admin_headers,
                            json=create_payload, timeout=15)
        if ru.status_code not in (200, 201):
            pytest.skip(f"Impossibile creare utente low-perm ({ru.status_code}): {ru.text[:200]}")
        created = ru.json()
        user_id = created.get("id") or created.get("_id")
        invite_url = created.get("invitation_url")
        if not invite_url or "token=" not in invite_url:
            pytest.skip(f"invitation_url mancante nella risposta: {created}")
        token = invite_url.split("token=")[1].split("&")[0]

        try:
            # Accept invitation
            ra = requests.post(f"{API}/auth/accept-invitation",
                                json={"token": token, "password": low_pw}, timeout=15)
            if ra.status_code != 200:
                pytest.skip(f"accept-invitation fallito: {ra.status_code} {ra.text[:200]}")
            # Login utente low-perm
            rl = requests.post(f"{API}/auth/login",
                                json={"email": low_email, "password": low_pw},
                                timeout=15)
            if rl.status_code != 200:
                pytest.skip(f"Login utente low-perm fallito: {rl.status_code} {rl.text[:200]}")
            low_tok = rl.json().get("access_token")
            low_headers = {"Authorization": f"Bearer {low_tok}",
                           "Content-Type": "application/json"}

            r = requests.post(f"{API}/pricing-hub/bom-simulate",
                                headers=low_headers, json=_base_bom_payload(),
                                timeout=20)
            # 403 accettabile se manca 'pricelists.view'
            if r.status_code == 403:
                pytest.skip("Utente low-perm bloccato al livello di router "
                            f"(manca pricelists.view): {r.text[:200]}")
            assert r.status_code == 200, r.text
            d = r.json()
            assert d.get("cost_redacted") is True, \
                f"cost_redacted atteso True per utente low-perm, got {d.get('cost_redacted')}"
            assert d.get("materials_cost") is None, \
                f"materials_cost atteso None, got {d.get('materials_cost')}"
            for c in (d.get("components") or []):
                assert c.get("unit_cost") is None, \
                    f"unit_cost atteso None nei componenti, got {c.get('unit_cost')} in {c.get('code')}"
            # cost_pricelist meta deve essere None
            assert d.get("cost_pricelist") is None, \
                f"cost_pricelist meta atteso None, got {d.get('cost_pricelist')}"
        finally:
            # cleanup: elimina utente di test
            try:
                requests.delete(f"{API}/users/{user_id}", headers=admin_headers, timeout=10)
            except Exception:
                pass


# ---------- Test: tenant isolation ----------

class TestTenantIsolation:
    """Un tenant non deve leggere item-pricelists di un altro tenant."""

    def test_cross_tenant_get_returns_404(self, admin_headers, me):
        """Simuliamo un id di listino che NON appartiene al tenant corrente.
        Usiamo un UUID casuale (non esistente in nessun tenant) → 404 atteso.
        Un id esistente ma di altro tenant darebbe anche 404 (get_doc filtra per tenant_id)."""
        # 1) UUID inesistente → 404
        fake_id = str(uuid.uuid4())
        r = requests.get(f"{API}/parametric/item-pricelists/{fake_id}",
                          headers=admin_headers, timeout=10)
        assert r.status_code == 404, \
            f"Attesa 404 per id inesistente, got {r.status_code}: {r.text[:200]}"

    def test_get_doc_filters_by_tenant(self):
        """Verifica statica: get_item_pricelist chiama get_doc con tenant_id=user['tenant_id']."""
        with open("/app/backend/app/routers/parametric.py", "r") as f:
            src = f.read()
        # Verifica che il getter usa tenant_id
        assert "get_doc(collection=\"item_pricelists\"" in src
        assert "tenant_id=user[\"tenant_id\"]" in src, \
            "get_item_pricelist non filtra per tenant_id"


# ---------- Test: regressioni ----------

class TestRegression:
    """Regressioni: nessuna funzionalità precedente rotta."""

    def test_bom_recipes_returns_20(self, admin_headers):
        r = requests.get(f"{API}/pricing-hub/bom-recipes",
                          headers=admin_headers, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        items = d.get("items") or []
        assert len(items) == 20, \
            f"bom-recipes deve tornare 20 ricette, got {len(items)}: codes={[i.get('code') for i in items[:25]]}"

    def test_geometry_templates_returns_6(self, admin_headers):
        r = requests.get(f"{API}/geometry/templates",
                          headers=admin_headers, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        items = d.get("items") if isinstance(d, dict) else d
        assert isinstance(items, list) and len(items) == 6, \
            f"geometry/templates deve tornare 6 template, got {len(items) if isinstance(items,list) else 'not-list'}"

    def test_contracts_list_200(self, admin_headers):
        r = requests.get(f"{API}/contracts", headers=admin_headers, timeout=10)
        assert r.status_code == 200, f"/contracts list KO: {r.status_code} {r.text[:200]}"

    def test_contract_pdf_preview_returns_pdf(self, admin_headers):
        r = requests.get(f"{API}/contracts/{CONTRACT_ID}/pdf/preview",
                          headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert r.headers.get("content-type", "").startswith("application/pdf"), \
            f"Content-type PDF atteso, got {r.headers.get('content-type')}"
        assert r.content[:5] == b"%PDF-", \
            f"Corpo PDF deve iniziare con '%PDF-', got {r.content[:10]}"


# ---------- Module teardown ----------

def teardown_module(module):
    """Safety net: ripristina SELL-DEMO a 'active' anche se qualcosa è andato storto."""
    try:
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                          timeout=15)
        if r.status_code != 200:
            return
        tok = r.json().get("access_token")
        headers = {"Authorization": f"Bearer {tok}",
                   "Content-Type": "application/json"}
        requests.patch(f"{API}/parametric/item-pricelists/{SELL_DEMO_ID}",
                        headers=headers, json={"ipl_status": "active"}, timeout=10)
    except Exception:
        pass
