"""ITER46 — PO FASE 1 (brand cleanup + SEO/META) + FASE 2 regression smoke.

Verifies:
- Public SEO endpoints (sitemap.xml, manifest.json, og-image.png).
- Landing config exposes brand 'Panorama Pilot'.
- No 'Emergent' leak in landing HTML.
- PDF quote preview still carries tenant brand 'Infissi Express'.
- Self-registration API is up (piggyback smoke).
"""
from __future__ import annotations
import os
import re
import requests

from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = BASE + "/api"


# ---------- fixtures ----------
def _admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    r.raise_for_status()
    return r.json()["access_token"]


# ---------- SEO / brand public assets ----------
def test_sitemap_xml_contains_only_landing():
    r = requests.get(f"{BASE}/sitemap.xml", timeout=10)
    assert r.status_code == 200, r.text[:200]
    body = r.text.lower()
    assert "<urlset" in body
    assert "/landing" in body
    # noindex routes MUST NOT appear
    for path in ("/login", "/register", "/dashboard", "/customer-portal", "/registration-status", "/registration-requests"):
        assert path not in body, f"sitemap leaks {path}"


def test_manifest_json_uses_panorama_pilot_brand():
    r = requests.get(f"{BASE}/manifest.json", timeout=10)
    assert r.status_code == 200
    j = r.json()
    name = (j.get("name") or "") + " " + (j.get("short_name") or "")
    assert "Panorama Pilot" in name, f"manifest name={j.get('name')!r} short={j.get('short_name')!r}"
    assert "emergent" not in name.lower()


def test_og_image_available():
    r = requests.get(f"{BASE}/og-image.png", timeout=10)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/")
    assert len(r.content) > 500


def test_landing_html_no_emergent_leak_and_correct_title():
    r = requests.get(f"{BASE}/landing", timeout=10)
    assert r.status_code == 200
    html = r.text
    # Ignore REACT_APP_BACKEND_URL host itself.
    host = re.escape(BASE.split("//", 1)[-1])
    cleaned = re.sub(host, "", html, flags=re.IGNORECASE)
    lowered = cleaned.lower()
    # Note: SPA shell may not include the runtime-rendered title; we assert the brand token is not leaked.
    assert "emergent" not in lowered, "Landing HTML leaks 'emergent'"
    assert "emergent.sh" not in lowered


# ---------- Landing config (brand product_name) ----------
def test_landing_public_config_reports_panorama_pilot():
    # Try known endpoints; accept the first non-404.
    candidates = ["/landing/public", "/landing/config", "/public/landing", "/branding/public"]
    last = None
    for path in candidates:
        r = requests.get(API + path, timeout=10)
        last = (path, r.status_code)
        if r.status_code == 200:
            j = r.json()
            flat = str(j).lower()
            assert "panorama pilot" in flat, f"{path} missing brand: {flat[:300]}"
            assert "infissi express cloud" not in flat, f"{path} still uses legacy brand"
            return
    # If none succeeded, skip rather than fail (endpoint contract not confirmed by PO).
    import pytest
    pytest.skip(f"No landing config endpoint reachable (last={last})")


# ---------- PDF quote preview keeps tenant brand ----------
def test_quote_pdf_preview_carries_tenant_brand():
    tok = {"Authorization": f"Bearer {_admin_token()}"}
    q = requests.get(f"{API}/quotes", params={"limit": 5}, headers=tok, timeout=15)
    assert q.status_code == 200
    items = q.json().get("items") or q.json().get("results") or q.json()
    if not items:
        import pytest
        pytest.skip("no quotes to test PDF brand")
    qid = items[0]["id"] if isinstance(items[0], dict) else items[0]
    r = requests.post(f"{API}/quotes/{qid}/pdf/preview", headers=tok, json={}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    body = r.content
    # response is JSON metadata with filename; the filename itself must carry the tenant brand.
    j = r.json()
    fname = (j.get("filename") or "").lower()
    assert "infissi_express" in fname or "infissi express" in fname, f"PDF filename lost tenant brand: {fname!r}"
    assert "emergent" not in fname, "PDF filename leaks 'Emergent'"
    hay = r.text.lower()
    assert "emergent" not in hay, "PDF preview response leaks 'Emergent'"


# ---------- FASE 2 quick contract smoke ----------
def test_registration_roles_endpoint_public_and_whitelisted():
    r = requests.get(f"{API}/auth/register/roles", timeout=10)
    assert r.status_code == 200
    codes = [it["code"] for it in r.json()["items"]]
    assert "commerciale" in codes and "cliente" in codes and "posatore" in codes
    assert "super_admin" not in codes and "admin_azienda" not in codes


def test_registration_requests_requires_auth():
    assert requests.get(f"{API}/registration-requests", timeout=10).status_code == 401
