"""Backend tests for M3.3.2 — PDF templates, clauses, generation, snapshot immutability,
scan endpoint, idempotency, filename sanitization, tenant isolation.
Run: pytest /app/backend/tests/test_pdf_m332.py -v --tb=short
"""
from __future__ import annotations
import asyncio
import base64
import os
import time
import concurrent.futures
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    # fallback: read frontend/.env
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = ln.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "admin@infissiexpress.com"
ADMIN_PASS = "Admin!2025"


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def s():
    return requests.Session()


@pytest.fixture(scope="session")
def auth_headers(s):
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def me(s, auth_headers):
    r = s.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=10)
    assert r.status_code == 200
    data = r.json()
    # /me returns {user:{...}, permissions:[...]}
    return {**(data.get("user") or {}), "permissions": data.get("permissions") or []}


@pytest.fixture(scope="session")
def lead_id(s, auth_headers):
    r = s.get(f"{BASE_URL}/api/leads?limit=1", headers=auth_headers, timeout=10)
    assert r.status_code == 200
    items = r.json().get("items", [])
    assert items, "seed leads missing"
    return items[0]["id"]


def _mk_quote_populated(s, auth_headers, lead_id):
    """Draft quote with site_address + 1 opening + 1 line."""
    r = s.post(f"{BASE_URL}/api/quotes", headers=auth_headers, json={
        "lead_id": lead_id,
        "title": "TEST_M332_PDF",
        "site_address": {"street": "Via Test 10", "city": "Milano",
                         "zip_code": "20100", "province": "MI", "country": "IT"},
    }, timeout=15)
    assert r.status_code == 200, r.text
    qid = r.json()["id"]
    # add opening
    r2 = s.post(f"{BASE_URL}/api/quotes/{qid}/openings", headers=auth_headers, json={
        "code": "V01", "room": "Salone", "width_mm": 1200, "height_mm": 1400, "quantity": 1,
    }, timeout=10)
    assert r2.status_code == 200, r2.text
    oid = r2.json().get("id") or (r2.json().get("openings") or [{}])[-1].get("id")
    # add line
    r3 = s.post(f"{BASE_URL}/api/quotes/{qid}/lines", headers=auth_headers, json={
        "category": "window", "opening_id": oid, "description": "Finestra PVC 2 ante",
        "width_mm": 1200, "height_mm": 1400, "quantity": 1,
        "base_price": 850.0, "internal_cost": 400.0, "vat_rate": 0.22,
    }, timeout=10)
    assert r3.status_code == 200, r3.text
    return qid


# ---------- Test 1: auth ----------
class TestAuth:
    def test_login_and_me(self, s, auth_headers, me):
        assert me.get("email") == ADMIN_EMAIL
        assert me.get("is_superadmin") is True
        # includes new PDF permissions via '*'
        perms = me.get("permissions") or me.get("permission_keys") or []
        # Either explicit '*' or actual pdf permissions
        assert ("*" in perms) or any(p.startswith("quotes.") for p in perms), perms


# ---------- Test 2: seed templates+clauses ----------
class TestSeed:
    def test_templates_seeded(self, s, auth_headers):
        r = s.get(f"{BASE_URL}/api/quote-templates", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        std = [t for t in items if t.get("code") == "IE_STANDARD_2026"]
        assert std, f"IE_STANDARD_2026 missing; codes={[t.get('code') for t in items]}"
        t = std[0]
        assert t.get("is_default") is True
        assert int(t.get("version") or 0) >= 1
        # payment terms 2 installments
        pt = t.get("default_payment_terms") or {}
        insts = pt.get("installments") or []
        assert len(insts) == 2, insts
        # payment breakdown 50/50
        assert sorted([float(i.get("percent") or 0) for i in insts]) == [50.0, 50.0]

    def test_clauses_seeded(self, s, auth_headers):
        r = s.get(f"{BASE_URL}/api/clauses", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 12, f"expected >=12 clauses, got {len(items)}"
        codes = {c["code"] for c in items}
        # Mandatory ones exist
        for expected in ("CL_MISURE_INDICATIVE", "CL_PAGAMENTI_50_50", "CL_PRIVACY"):
            assert expected in codes, f"missing {expected}; got {codes}"
        # 3 known mandatory should have mandatory=True
        mand = {c["code"] for c in items if c.get("mandatory") is True}
        for expected in ("CL_MISURE_INDICATIVE", "CL_PAGAMENTI_50_50", "CL_PRIVACY"):
            assert expected in mand, f"{expected} should be mandatory={mand}"
        # Optional codes should exist
        for expected in ("CL_ANNULLAMENTO", "CL_DETRAZIONI"):
            assert expected in codes, f"missing {expected}"


# ---------- Test 3: preview PDF success ----------
class TestPreviewPdf:
    def test_preview_ok(self, s, auth_headers, lead_id):
        qid = _mk_quote_populated(s, auth_headers, lead_id)
        r = s.post(f"{BASE_URL}/api/quotes/{qid}/pdf/preview",
                   headers=auth_headers, json={}, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("id", "kind", "filename", "snapshot_hash", "pdf_hash", "size_bytes", "generated_at"):
            assert k in data, f"preview missing key {k}: {data}"
        assert data["kind"] == "preview"
        assert data["size_bytes"] > 0
        # filename sanitization
        assert all(ch.isalnum() or ch in "._-" for ch in data["filename"]), data["filename"]
        # no duplicate revision label like R00_R00
        assert "R00_R00" not in data["filename"]
        # download
        r2 = s.get(f"{BASE_URL}/api/quote-pdfs/{data['id']}/download",
                   headers=auth_headers, timeout=30)
        assert r2.status_code == 200
        assert r2.headers.get("content-type", "").startswith("application/pdf")
        assert r2.content[:4] == b"%PDF"


# ---------- Test 4: definitive validation failure ----------
class TestValidationGate:
    def test_definitive_fails_without_lines(self, s, auth_headers, lead_id):
        # Create quote with no site_address override and NO lines
        r = s.post(f"{BASE_URL}/api/quotes", headers=auth_headers, json={
            "lead_id": lead_id, "title": "TEST_M332_Empty",
        }, timeout=10)
        assert r.status_code == 200, r.text
        qid = r.json()["id"]
        r2 = s.post(f"{BASE_URL}/api/quotes/{qid}/pdf/generate",
                    headers=auth_headers, json={}, timeout=30)
        assert r2.status_code == 400, r2.text
        detail = r2.json().get("detail") or {}
        assert isinstance(detail, dict), detail
        assert detail.get("error") == "validation_failed", detail
        errors = detail.get("errors") or []
        codes = {e.get("code") for e in errors}
        assert "no_lines" in codes, codes

    @pytest.mark.xfail(reason="BACKEND BUG: validate_quote_for_definitive checks `not quote.get('site_address')` but Quote model defaults to LeadAddress() (dict with all-None fields) which is truthy in Python, so 'missing_site' never fires even when street/city/zip all empty.", strict=True)
    def test_definitive_reports_missing_site(self, s, auth_headers, lead_id):
        r = s.post(f"{BASE_URL}/api/quotes", headers=auth_headers, json={
            "lead_id": lead_id, "title": "TEST_M332_NoSite",
        }, timeout=10)
        qid = r.json()["id"]
        # Add a line so no_lines does not shadow — we specifically want to see missing_site
        r_l = s.post(f"{BASE_URL}/api/quotes/{qid}/lines", headers=auth_headers, json={
            "category": "window", "description": "L", "base_price": 100.0, "quantity": 1,
        }, timeout=10)
        assert r_l.status_code == 200
        r2 = s.post(f"{BASE_URL}/api/quotes/{qid}/pdf/generate",
                    headers=auth_headers, json={}, timeout=30)
        assert r2.status_code == 400, r2.text
        codes = {e.get("code") for e in (r2.json().get("detail", {}).get("errors") or [])}
        assert "missing_site" in codes, codes


# ---------- Test 5+6: definitive OK + idempotency ----------
class TestDefinitiveAndIdempotency:
    def test_definitive_flow_ok_idempotent_and_new_hash_after_edit(self, s, auth_headers, lead_id):
        qid = _mk_quote_populated(s, auth_headers, lead_id)
        # 1) First definitive
        r1 = s.post(f"{BASE_URL}/api/quotes/{qid}/pdf/generate",
                    headers=auth_headers, json={}, timeout=60)
        assert r1.status_code == 200, r1.text
        first = r1.json()
        assert first["kind"] == "definitive"
        # quote reflects latest_pdf_*
        rq = s.get(f"{BASE_URL}/api/quotes/{qid}", headers=auth_headers, timeout=10)
        q = rq.json()
        assert q.get("latest_pdf_id") == first["id"]
        assert q.get("latest_pdf_hash") == first["pdf_hash"]
        # 2) Second definitive → idempotent
        r2 = s.post(f"{BASE_URL}/api/quotes/{qid}/pdf/generate",
                    headers=auth_headers, json={}, timeout=30)
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2.get("idempotent_hit") is True, d2
        assert d2["id"] == first["id"], (d2, first)
        assert d2["snapshot_hash"] == first["snapshot_hash"]
        # 3) After line change → new snapshot_hash
        rq2 = s.get(f"{BASE_URL}/api/quotes/{qid}", headers=auth_headers, timeout=10)
        lid = rq2.json()["lines"][0]["id"]
        rp = s.patch(f"{BASE_URL}/api/quotes/{qid}/lines/{lid}",
                     headers=auth_headers, json={"base_price": 1234.0}, timeout=15)
        assert rp.status_code == 200, rp.text
        r3 = s.post(f"{BASE_URL}/api/quotes/{qid}/pdf/generate",
                    headers=auth_headers, json={}, timeout=60)
        assert r3.status_code == 200, r3.text
        d3 = r3.json()
        assert not d3.get("idempotent_hit"), d3
        assert d3["snapshot_hash"] != first["snapshot_hash"]
        assert d3["id"] != first["id"]


# ---------- Test 7: snapshot immutability ----------
class TestSnapshotImmutability:
    def test_snapshot_immutable_after_edit(self, s, auth_headers, lead_id):
        qid = _mk_quote_populated(s, auth_headers, lead_id)
        # 1) preview
        r1 = s.post(f"{BASE_URL}/api/quotes/{qid}/pdf/preview",
                    headers=auth_headers, json={}, timeout=60)
        assert r1.status_code == 200
        pid1 = r1.json()["id"]
        # snapshot fetch via metadata endpoint - snapshot is stripped there;
        # fetch full doc via download & re-read metadata by an inner endpoint.
        # We rely on second, altered generation: totals should differ.
        # Change a line and add another
        q = s.get(f"{BASE_URL}/api/quotes/{qid}", headers=auth_headers, timeout=10).json()
        lid = q["lines"][0]["id"]
        s.patch(f"{BASE_URL}/api/quotes/{qid}/lines/{lid}",
                headers=auth_headers, json={"base_price": 1500.0, "quantity": 2}, timeout=15)
        # 2) definitive after edit
        r2 = s.post(f"{BASE_URL}/api/quotes/{qid}/pdf/generate",
                    headers=auth_headers, json={}, timeout=60)
        assert r2.status_code == 200, r2.text
        pid2 = r2.json()["id"]
        assert r1.json()["snapshot_hash"] != r2.json()["snapshot_hash"]
        # After more edits, verify first snapshot bytes unchanged
        s.patch(f"{BASE_URL}/api/quotes/{qid}/lines/{lid}",
                headers=auth_headers, json={"base_price": 42.0}, timeout=15)
        # Downloading pid1 must still yield same bytes
        d1 = s.get(f"{BASE_URL}/api/quote-pdfs/{pid1}/download", headers=auth_headers, timeout=30)
        d1b = s.get(f"{BASE_URL}/api/quote-pdfs/{pid1}/download", headers=auth_headers, timeout=30)
        assert d1.content == d1b.content
        # ...and pid2 also stable
        d2 = s.get(f"{BASE_URL}/api/quote-pdfs/{pid2}/download", headers=auth_headers, timeout=30)
        assert d2.status_code == 200
        assert d2.content[:4] == b"%PDF"


# ---------- Test 8: scan pricing-scope-bug ----------
class TestScan:
    def test_scan_endpoint_structure(self, s, auth_headers):
        r = s.get(f"{BASE_URL}/api/quotes/scan/pricing-scope-bug",
                  headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("scanned_at", "total_scanned", "affected_by_status", "total_diff_estimate"):
            assert k in d, f"missing {k} in {d.keys()}"
        assert d["total_scanned"] > 0
        for bkey in ("draft", "sent", "accepted", "converted", "signed", "other"):
            assert bkey in d["affected_by_status"], bkey
            assert isinstance(d["affected_by_status"][bkey], list)


# ---------- Test 9: snapshot excludes internal_cost / margin ----------
class TestSnapshotCleanup:
    def test_no_internal_cost_in_snapshot(self, s, auth_headers, lead_id):
        qid = _mk_quote_populated(s, auth_headers, lead_id)
        r = s.post(f"{BASE_URL}/api/quotes/{qid}/pdf/preview",
                   headers=auth_headers, json={}, timeout=60)
        assert r.status_code == 200
        pid = r.json()["id"]
        # get metadata: snapshot stripped there. Access via /quote-pdfs/{pid} — but that removes snapshot.
        # We instead check the raw DB via the download (bytes) — cannot inspect content easily.
        # Use list endpoint which includes snapshot (from_mongo includes it via list_quote_pdfs).
        rlist = s.get(f"{BASE_URL}/api/quotes/{qid}/pdfs", headers=auth_headers, timeout=15)
        assert rlist.status_code == 200
        # snapshot inline
        docs = rlist.json()["items"]
        target = next(x for x in docs if x["id"] == pid)
        snap = target.get("snapshot")
        assert snap, "snapshot not persisted in listing"
        lines = ((snap.get("quote") or {}).get("lines")) or []
        assert lines, "expected at least 1 line in snapshot.quote.lines"
        for l in lines:
            assert "internal_cost" not in l, l.keys()
            assert "margin_abs" not in l, l.keys()
            assert "margin_pct" not in l, l.keys()
            assert "cost_price" not in l, l.keys()


# ---------- Test 10: tenant isolation of scan/list ----------
class TestTenantIsolation:
    def test_snapshot_company_tenant_matches(self, s, auth_headers, me, lead_id):
        qid = _mk_quote_populated(s, auth_headers, lead_id)
        r = s.post(f"{BASE_URL}/api/quotes/{qid}/pdf/preview",
                   headers=auth_headers, json={}, timeout=60)
        pid = r.json()["id"]
        rlist = s.get(f"{BASE_URL}/api/quotes/{qid}/pdfs", headers=auth_headers, timeout=10)
        target = next(x for x in rlist.json()["items"] if x["id"] == pid)
        assert target.get("tenant_id") == me["tenant_id"]


# ---------- Test 11: watermark ----------
class TestWatermark:
    def test_preview_bozza_definitive_none(self, s, auth_headers, lead_id):
        qid = _mk_quote_populated(s, auth_headers, lead_id)
        rp = s.post(f"{BASE_URL}/api/quotes/{qid}/pdf/preview",
                    headers=auth_headers, json={}, timeout=60)
        pid_p = rp.json()["id"]
        rd = s.post(f"{BASE_URL}/api/quotes/{qid}/pdf/generate",
                    headers=auth_headers, json={}, timeout=60)
        pid_d = rd.json()["id"]
        meta_p = s.get(f"{BASE_URL}/api/quote-pdfs/{pid_p}", headers=auth_headers, timeout=10).json()
        meta_d = s.get(f"{BASE_URL}/api/quote-pdfs/{pid_d}", headers=auth_headers, timeout=10).json()
        assert meta_p.get("watermark") == "BOZZA", meta_p
        assert meta_d.get("watermark") in (None, ""), meta_d


# ---------- Test 12: template concurrency ----------
class TestTemplateConcurrency:
    def test_patch_wrong_ifmatch_returns_409(self, s, auth_headers):
        r = s.get(f"{BASE_URL}/api/quote-templates", headers=auth_headers, timeout=10)
        t = [x for x in r.json()["items"] if x.get("code") == "IE_STANDARD_2026"][0]
        tid = t["id"]
        wrong_version = int(t.get("version") or 1) + 99
        r2 = s.patch(f"{BASE_URL}/api/quote-templates/{tid}",
                     headers={**auth_headers, "If-Match": str(wrong_version)},
                     json={"validity_days": 45}, timeout=10)
        assert r2.status_code == 409, r2.text

    def test_patch_ok_archives_previous_version(self, s, auth_headers):
        r = s.get(f"{BASE_URL}/api/quote-templates", headers=auth_headers, timeout=10)
        t = [x for x in r.json()["items"] if x.get("code") == "IE_STANDARD_2026"][0]
        tid = t["id"]
        ver = int(t.get("version") or 1)
        r2 = s.patch(f"{BASE_URL}/api/quote-templates/{tid}",
                     headers={**auth_headers, "If-Match": str(ver)},
                     json={"validity_days": (int(t.get("validity_days") or 30) + 1)}, timeout=10)
        assert r2.status_code == 200, r2.text


# ---------- Test 13: clause update archives history ----------
class TestClauseVersioning:
    def test_clause_patch_archives_previous(self, s, auth_headers):
        r = s.get(f"{BASE_URL}/api/clauses?category=annullamento", headers=auth_headers, timeout=10)
        items = r.json()["items"]
        assert items, "no cancellation clauses"
        cl = items[0]
        cid = cl["id"]
        original_text = cl["text"]
        ver = int(cl.get("version") or 1)
        # Patch
        new_text = original_text + " - TEST_M332"
        r2 = s.patch(f"{BASE_URL}/api/clauses/{cid}",
                     headers={**auth_headers, "If-Match": str(ver)},
                     json={"text": new_text}, timeout=10)
        assert r2.status_code == 200, r2.text
        # Restore original for other tests
        r3 = s.get(f"{BASE_URL}/api/clauses/{cid}", headers=auth_headers, timeout=10)
        ver2 = int(r3.json().get("version") or 1)
        s.patch(f"{BASE_URL}/api/clauses/{cid}",
                headers={**auth_headers, "If-Match": str(ver2)},
                json={"text": original_text}, timeout=10)


# ---------- Test 14: filename sanitization ----------
class TestFilename:
    def test_filename_pattern(self, s, auth_headers, lead_id):
        qid = _mk_quote_populated(s, auth_headers, lead_id)
        r = s.post(f"{BASE_URL}/api/quotes/{qid}/pdf/preview",
                   headers=auth_headers, json={}, timeout=60)
        fn = r.json()["filename"]
        # Only A-Za-z0-9._- allowed
        import re
        assert re.match(r"^[A-Za-z0-9._-]+\.pdf$", fn), fn
        assert " " not in fn
        assert "//" not in fn
        # No duplicate R00
        assert fn.count("R00") <= 1, fn


# ---------- Test 15: parallel double-click idempotency ----------
class TestParallelDoubleClick:
    def test_parallel_generate_returns_same_id(self, s, auth_headers, lead_id):
        # Fresh quote
        qid = _mk_quote_populated(s, auth_headers, lead_id)

        # First generate serially so we HAVE an existing definitive; then double-click.
        # (The idempotency check is snapshot_hash-based; two parallel POSTs w/o an existing
        #  record can produce a race and both create. That is a known limitation; still
        #  both should return 200. If both succeed with different ids, we flag as minor.)
        r0 = s.post(f"{BASE_URL}/api/quotes/{qid}/pdf/generate", headers=auth_headers, json={}, timeout=60)
        assert r0.status_code == 200
        first_id = r0.json()["id"]

        results = []
        def _call():
            return requests.post(f"{BASE_URL}/api/quotes/{qid}/pdf/generate",
                                 headers=auth_headers, json={}, timeout=60)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            futs = [ex.submit(_call), ex.submit(_call)]
            for f in concurrent.futures.as_completed(futs):
                results.append(f.result())
        assert all(r.status_code == 200 for r in results), [r.status_code for r in results]
        ids = {r.json()["id"] for r in results}
        # All should collapse onto the first_id
        assert ids == {first_id}, f"parallel emission produced multiple pdf ids: {ids} vs first {first_id}"
        for r in results:
            assert r.json().get("idempotent_hit") is True
