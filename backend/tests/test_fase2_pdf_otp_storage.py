"""Fase 2 Testing — PDF endpoints, OTP reale, Storage import, Signature Provider registry.

Copre:
- PDF preview/generate/list/download + versioning immutabile
- Permessi contracts.download (403 senza permesso)
- OTP request-otp reale (no code in prod, rate limit 3/5min)
- Signature providers registry (electronic_simple only)
- Importer object_storage con storage_key
- Regressione geometry/BOM/state machine
"""
import io
import os
import re
import time
import hashlib
import pytest
import requests
from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD  # env-sourced credentials

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://serramento-ops.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
# scrubbed: ADMIN_EMAIL moved to tests._creds
# scrubbed: ADMIN_PASSWORD moved to tests._creds
TEST_CONTRACT_ID = "899c4115-d4be-41a3-8d57-b1cdfb488754"


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# -----------------------------------------------------------------------------
# PDF endpoints
# -----------------------------------------------------------------------------
class TestPdfEndpoints:
    def test_pdf_preview_returns_pdf(self, admin_headers):
        r = requests.get(f"{API}/contracts/{TEST_CONTRACT_ID}/pdf/preview", headers=admin_headers, timeout=30)
        assert r.status_code == 200, f"Expected 200, got {r.status_code} {r.text[:200]}"
        assert r.headers.get("content-type", "").startswith("application/pdf")
        body = r.content
        assert body[:8].startswith(b"%PDF-1."), f"Expected PDF magic bytes, got: {body[:20]!r}"
        assert len(body) > 5000, f"PDF suspiciously small: {len(body)} bytes"

    def test_pdf_generate_creates_new_version(self, admin_headers):
        # Get current versions
        r_before = requests.get(f"{API}/contracts/{TEST_CONTRACT_ID}/pdf/list", headers=admin_headers, timeout=15)
        assert r_before.status_code == 200
        v_before = len(r_before.json().get("versions") or [])
        # Generate new
        r_gen = requests.post(f"{API}/contracts/{TEST_CONTRACT_ID}/pdf/generate", headers=admin_headers, timeout=30)
        assert r_gen.status_code == 200, f"generate failed: {r_gen.status_code} {r_gen.text[:200]}"
        data = r_gen.json()
        for k in ("version", "hash", "size_bytes", "storage_key", "kind", "filename"):
            assert k in data, f"missing key {k} in {data}"
        assert data["kind"] in ("draft", "signed", "preview")
        assert data["size_bytes"] > 1000
        assert re.fullmatch(r"[0-9a-f]{64}", data["hash"]), f"invalid sha256 hash: {data['hash']}"
        # Verify version incremented
        r_after = requests.get(f"{API}/contracts/{TEST_CONTRACT_ID}/pdf/list", headers=admin_headers, timeout=15)
        v_after = len(r_after.json().get("versions") or [])
        assert v_after == v_before + 1, f"version count did not increase: {v_before} -> {v_after}"
        # Store version+hash for download test
        TestPdfEndpoints._last_version = data["version"]
        TestPdfEndpoints._last_hash = data["hash"]

    def test_pdf_generate_immutable_no_overwrite(self, admin_headers):
        # Two consecutive generates should create two different versions
        r1 = requests.post(f"{API}/contracts/{TEST_CONTRACT_ID}/pdf/generate", headers=admin_headers, timeout=30)
        r2 = requests.post(f"{API}/contracts/{TEST_CONTRACT_ID}/pdf/generate", headers=admin_headers, timeout=30)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["version"] != r2.json()["version"]
        assert r1.json()["storage_key"] != r2.json()["storage_key"]

    def test_pdf_list_returns_versions(self, admin_headers):
        r = requests.get(f"{API}/contracts/{TEST_CONTRACT_ID}/pdf/list", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "versions" in data
        assert isinstance(data["versions"], list)
        assert len(data["versions"]) > 0
        v = data["versions"][-1]
        for k in ("version", "hash", "storage_key", "kind", "size_bytes"):
            assert k in v, f"missing {k} in version doc"

    def test_pdf_download_matches_list_hash(self, admin_headers):
        r_list = requests.get(f"{API}/contracts/{TEST_CONTRACT_ID}/pdf/list", headers=admin_headers, timeout=15)
        versions = r_list.json()["versions"]
        assert len(versions) > 0
        latest = versions[-1]
        version_num = latest["version"]
        expected_hash = latest["hash"]
        r_dl = requests.get(f"{API}/contracts/{TEST_CONTRACT_ID}/pdf/download/{version_num}",
                             headers=admin_headers, timeout=30)
        assert r_dl.status_code == 200
        assert r_dl.headers.get("content-type", "").startswith("application/pdf")
        actual_hash = hashlib.sha256(r_dl.content).hexdigest()
        assert actual_hash == expected_hash, f"hash mismatch: {actual_hash} != {expected_hash}"
        assert r_dl.content[:8].startswith(b"%PDF-1.")

    def test_pdf_download_missing_version_404(self, admin_headers):
        r = requests.get(f"{API}/contracts/{TEST_CONTRACT_ID}/pdf/download/99999",
                          headers=admin_headers, timeout=15)
        assert r.status_code == 404


# -----------------------------------------------------------------------------
# PDF Permissions
# -----------------------------------------------------------------------------
class TestPdfPermissions:
    def test_no_auth_401(self):
        r = requests.get(f"{API}/contracts/{TEST_CONTRACT_ID}/pdf/preview", timeout=10)
        assert r.status_code in (401, 403), f"Expected 401/403 without auth, got {r.status_code}"

    def test_no_permission_user_403(self, admin_headers):
        """Create a user without contracts.download and verify 403 on generate/download.
        Marked xfail if user creation not permitted in this env."""
        # Try to create a limited role
        role_payload = {"name": "TEST_no_download", "permissions": ["contracts.view"]}
        r_role = requests.post(f"{API}/roles", json=role_payload, headers=admin_headers, timeout=10)
        if r_role.status_code not in (200, 201):
            pytest.skip(f"cannot create role: {r_role.status_code} {r_role.text[:200]}")
        role = r_role.json()
        role_id = role.get("id") or role.get("_id")
        # Create user with ephemeral password from env-driven helper
        from tests._creds import ephemeral_password
        _test_user_pw = ephemeral_password("NoDown")
        user_payload = {
            "email": "TEST_nodown@example.com", "password": _test_user_pw,
            "first_name": "No", "last_name": "Download",
            "role_ids": [role_id] if role_id else [],
        }
        r_user = requests.post(f"{API}/users", json=user_payload, headers=admin_headers, timeout=10)
        if r_user.status_code not in (200, 201):
            # Try login existing
            pass
        # Login as this user
        r_login = requests.post(f"{API}/auth/login",
                                  json={"email": user_payload["email"], "password": user_payload["password"]},
                                  timeout=10)
        if r_login.status_code != 200:
            pytest.skip(f"cannot login limited user: {r_login.status_code} {r_login.text[:200]}")
        limited_token = r_login.json()["access_token"]
        limited_headers = {"Authorization": f"Bearer {limited_token}"}
        # Preview (contracts.view) should work
        r_prev = requests.get(f"{API}/contracts/{TEST_CONTRACT_ID}/pdf/preview", headers=limited_headers, timeout=15)
        # Generate should be forbidden
        r_gen = requests.post(f"{API}/contracts/{TEST_CONTRACT_ID}/pdf/generate", headers=limited_headers, timeout=15)
        assert r_gen.status_code == 403, f"Expected 403 for user without contracts.download, got {r_gen.status_code}"
        # Cleanup: user + role
        try:
            if r_user.status_code in (200, 201):
                uid = r_user.json().get("id") or r_user.json().get("_id")
                if uid:
                    requests.delete(f"{API}/users/{uid}", headers=admin_headers, timeout=10)
            if role_id:
                requests.delete(f"{API}/roles/{role_id}", headers=admin_headers, timeout=10)
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Signature Providers Registry
# -----------------------------------------------------------------------------
class TestSignatureProviders:
    def test_registry_lists_internal_canvas(self, admin_headers):
        r = requests.get(f"{API}/contracts/config/signature-providers", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        items = data["items"]
        names = [i["name"] for i in items]
        assert "internal_canvas" in names
        internal = next(i for i in items if i["name"] == "internal_canvas")
        assert internal["level"] == "electronic_simple", f"WRONG level: {internal['level']}"
        assert internal["configured"] is True

    def test_no_advanced_or_qualified_claim(self, admin_headers):
        r = requests.get(f"{API}/contracts/config/signature-providers", headers=admin_headers, timeout=10)
        items = r.json()["items"]
        # Non deve esistere alcun provider dichiarato configured=true con level FEA/FEQ
        for i in items:
            if i["level"] in ("electronic_advanced", "electronic_qualified"):
                assert i["configured"] is False, \
                    f"Provider {i['name']} dichiarato configured con level {i['level']} — VIETATO in prod"
            # Never use words 'qualificata'/'digitale' in provider name for internal
            if i["name"] == "internal_canvas":
                assert "qualif" not in i.get("description", "").lower().split("richiede")[0]


# -----------------------------------------------------------------------------
# OTP reale
# -----------------------------------------------------------------------------
class TestOtpReal:
    @pytest.fixture(scope="class")
    def signing_token(self, admin_headers):
        """Crea un contratto + token di firma per test OTP."""
        r = requests.get(f"{API}/contracts?limit=50", headers=admin_headers, timeout=10)
        payload = r.json()
        contracts = payload.get("items") if isinstance(payload, dict) else payload
        target = None
        for c in (contracts or []):
            if c.get("contract_status") in ("ready_for_signature", "draft", "ready_for_review"):
                target = c
                break
        if not target:
            pytest.skip("Nessun contratto disponibile per test OTP")
        cid = target.get("id") or target.get("_id")
        # Ensure ready_for_signature
        for state in ("ready_for_review", "ready_for_signature"):
            requests.post(f"{API}/contracts/{cid}/transition",
                          json={"to_state": state}, headers=admin_headers, timeout=10)
        # Create signing token via send-for-signature
        r_tok = requests.post(f"{API}/contracts/{cid}/send-for-signature",
                                json={"to_email": "otp-test@example.com",
                                      "channel": "email", "expires_hours": 24,
                                      "message": "Test OTP"},
                                headers=admin_headers, timeout=10)
        if r_tok.status_code not in (200, 201):
            pytest.skip(f"cannot create signing token: {r_tok.status_code} {r_tok.text[:200]}")
        return r_tok.json().get("signing_token")

    def test_request_otp_returns_masked_no_code_in_prod(self, signing_token):
        r = requests.post(f"{API}/contracts/public/{signing_token}/request-otp", timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        data = r.json()
        assert data.get("ok") is True
        assert "request_id" in data
        assert data.get("expires_in_seconds", 0) > 0
        assert "recipient_masked" in data
        # masked email should contain @ but not the full local-part
        masked = data["recipient_masked"]
        assert "@" in masked
        assert "*" in masked or len(masked.split("@")[0]) <= 4
        # delivery_status contain expected keywords
        ds = data.get("delivery_status", "")
        assert any(k in ds for k in ("sent:", "mocked_dev", "delivery_failed")), f"unexpected delivery_status: {ds}"
        # debug_code solo se OTP_DEBUG_ENABLED (dev)
        # NON deve mai esserci un campo 'otp_code' (raw)
        assert "otp_code" not in data
        assert "code" not in data or data.get("code") is None

    def test_otp_rate_limit(self, signing_token):
        """4 request in <5 min → 429 after 3rd."""
        codes = []
        for i in range(4):
            r = requests.post(f"{API}/contracts/public/{signing_token}/request-otp", timeout=15)
            codes.append(r.status_code)
            time.sleep(0.3)
        # First 3 → 200 (usually), 4th → 429
        assert codes[3] == 429, f"expected 429 on 4th request, got codes: {codes}"

    def test_otp_verify_without_request_id_dev_fallback(self, signing_token):
        """In dev con OTP_DEBUG_ENABLED, 123456 senza request_id potrebbe funzionare come fallback.
        In prod deve dare errore. Verifica solo che il sign endpoint rifiuti 123456 SENZA request_id in modo controllato."""
        # We can't easily reset rate limit; just test the error path
        r_sign = requests.post(f"{API}/contracts/public/{signing_token}/sign",
                                json={"signer_name": "Test", "signature_data_url": "data:image/png;base64,iVBOR",
                                        "accept_terms": True, "otp_code": "999999"},
                                timeout=15)
        # Con codice sbagliato senza request_id, in dev con OTP_DEBUG_ENABLED fallirà anche il fallback
        # (123456 non è passato). Basta verificare che non firmi.
        assert r_sign.status_code in (400, 404, 410), f"expected error, got {r_sign.status_code}: {r_sign.text[:200]}"


# -----------------------------------------------------------------------------
# Importer object storage
# -----------------------------------------------------------------------------
class TestImporterStorage:
    def test_upload_creates_storage_key(self, admin_headers):
        csv_data = "code,description,price\nTEST_SKU1,Test Item,100.00\nTEST_SKU2,Second Item,50.00\n"
        files = {"file": ("test_fase2.csv", io.BytesIO(csv_data.encode()), "text/csv")}
        data = {"entity_type": "accessory"}
        r = requests.post(f"{API}/importer/upload", files=files, data=data, headers=admin_headers, timeout=20)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:200]}"
        job = r.json()
        job_id = job.get("job_id") or job.get("id") or job.get("_id")
        assert job_id, f"no job_id in response: {job}"
        # Fetch job doc to verify storage_key
        r_job = requests.get(f"{API}/importer/jobs/{job_id}", headers=admin_headers, timeout=10)
        assert r_job.status_code == 200
        job_doc = r_job.json()
        # storage_key should be present when LocalStorageProvider is active (STORAGE_PROVIDER=emergent/local)
        storage_key = job_doc.get("storage_key")
        # LocalStorageProvider default → storage_key non-null. Se s3 non config, potrebbe usare mongo blob fallback.
        assert storage_key is not None or job_doc.get("file_hash") is not None, \
            f"Né storage_key né file_hash presenti in job doc: {list(job_doc.keys())}"


# -----------------------------------------------------------------------------
# Regressione: geometry, BOM, state machine
# -----------------------------------------------------------------------------
class TestRegressionGeometry:
    def test_geometry_templates(self, admin_headers):
        r = requests.get(f"{API}/geometry/templates", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        items = data.get("items") if isinstance(data, dict) else data
        assert len(items) >= 6, f"expected >=6 templates, got {len(items)}"

    def test_geometry_compute_2ante(self, admin_headers):
        # Get templates to pick 2-ante
        r_tpl = requests.get(f"{API}/geometry/templates", headers=admin_headers, timeout=10)
        tpls_list = r_tpl.json().get("items") or []
        tpl_2ante = next((t for t in tpls_list if "2ANTE" in (t.get("code") or "").upper()
                          or "2 ante" in (t.get("name") or "").lower()), None)
        if not tpl_2ante:
            pytest.skip("no 2-ante template found")
        # Build geometry from default_tree — API expects root wrapper
        default_tree = tpl_2ante.get("default_tree") or {}
        # Get first profile system
        r_ps = requests.get(f"{API}/parametric/profile-systems", headers=admin_headers, timeout=10)
        systems = r_ps.json().get("items") if isinstance(r_ps.json(), dict) else r_ps.json()
        assert systems, "no profile-systems available"
        profile_id = systems[0].get("id") or systems[0].get("_id")
        geometry_payload = {
            "outer_width_mm": 1200,
            "outer_height_mm": 1400,
            "profile_system_id": profile_id,
            "root": default_tree,
        }
        # Try candidate bom_template_ids
        r_bom = requests.get(f"{API}/parametric/bom-templates", headers=admin_headers, timeout=10)
        recipes = r_bom.json().get("items") if isinstance(r_bom.json(), dict) else r_bom.json()
        bom_2a = next((b for b in recipes if "WIN-2A" in (b.get("code") or "")), None)
        bom_id = (bom_2a or {}).get("id") or (bom_2a or {}).get("_id")
        payload = {
            "geometry": geometry_payload,
            "bom_template_id": bom_id,
            "sell_pricelist_id": "4db4b91f-22c9-422b-aa7f-e235967b6698",
            "include_svg": True,
            "include_costs": False,
        }
        r = requests.post(f"{API}/geometry/compute", json=payload, headers=admin_headers, timeout=30)
        # Anche 200 con blocking_errors è accettabile per la regressione: verifica solo lo shape
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        data = r.json()
        # geometry_summary presente
        assert "geometry_summary" in data or "aggregated" in data or "components" in data, \
            f"unexpected response shape: keys={list(data.keys())[:20]}"
        # SVG must be present
        assert data.get("svg") is not None, "svg missing"


class TestRegressionBOM:
    def test_bom_recipes_list(self, admin_headers):
        r = requests.get(f"{API}/pricing-hub/bom-recipes", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        items = data.get("items") if isinstance(data, dict) else data
        assert len(items) >= 20, f"expected >=20 recipes, got {len(items)}"

    def test_bom_simulate_win_2a(self, admin_headers):
        r_bom = requests.get(f"{API}/parametric/bom-templates", headers=admin_headers, timeout=10)
        recipes = r_bom.json().get("items") if isinstance(r_bom.json(), dict) else r_bom.json()
        bom_2a = next((b for b in recipes if "WIN-2A" in (b.get("code") or "")), None)
        assert bom_2a is not None, f"BOM-WIN-2A not found. Available: {[b.get('code') for b in recipes]}"
        bom_id = bom_2a.get("id") or bom_2a.get("_id")
        r = requests.post(f"{API}/pricing-hub/bom-simulate",
                            json={"bom_template_id": bom_id, "width_mm": 1200, "height_mm": 1400, "nr_ante": 2},
                            headers=admin_headers, timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        data = r.json()
        components = data.get("components") or []
        assert len(components) >= 10, f"expected >=10 components, got {len(components)}"
        assert "snapshot_hash" in data


class TestRegressionStateMachine:
    def test_signed_contract_immutable(self, admin_headers):
        """Il contratto firmato non deve accettare transizioni ulteriori."""
        r = requests.post(f"{API}/contracts/{TEST_CONTRACT_ID}/transition",
                            json={"to_state": "ready_for_review"}, headers=admin_headers, timeout=10)
        # signed → deve essere rifiutato
        assert r.status_code in (400, 409, 422), \
            f"expected 4xx on signed contract transition, got {r.status_code}: {r.text[:200]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
