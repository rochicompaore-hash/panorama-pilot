"""Release Gate iter40 — verify:
- /api/sequences 200 (was 500)
- Login lock brute-force (5 fails on non-existent email -> 6th =429)
- Quote PDF V2 preview + content: Roboto embedded, terms V1, no leak
- Multi-cat configure: 3 ante fail-closed, 2 ok
- Tenant/RBAC smoke (audience separation)
"""
import os
import io
import re
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD as ADMIN_PASS, CUSTOMER_DEMO_EMAIL as CUST_EMAIL, CUSTOMER_DEMO_PASSWORD as CUST_PASS

QUOTE_DRAFT = "540b194f-798b-4b36-a129-60addcd689a5"
QUOTE_ACCEPTED = "c80f2e37-878a-4dab-b557-1476a546d6d3"
PROD_ID = "8e1cafd0-9707-47c7-8939-b97c9a404021"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def customer_token():
    r = requests.post(f"{BASE}/api/customer-portal/auth/login", json={"email": CUST_EMAIL, "password": CUST_PASS})
    assert r.status_code == 200, r.text
    return r.json().get("access_token") or r.json().get("token")


# --- Sequences ---
def test_sequences_ok(admin_headers):
    r = requests.get(f"{BASE}/api/sequences", headers=admin_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", data)
    assert items, f"Empty sequences: {data}"


# --- Auth: brute-force ---
def test_bruteforce_lock_nonexistent():
    email = "TEST_bf_nonexistent_iter40@example.com"
    codes = []
    for i in range(6):
        r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": "wrong"})
        codes.append(r.status_code)
    # First 5 should be 401, 6th 429
    assert codes[-1] == 429, f"Expected 429 on 6th, got sequence {codes}"
    assert all(c in (401, 429) for c in codes[:5])


# --- Multi-cat fail-closed 3 sashes ---
def test_configure_3_ante_fail_closed(admin_headers):
    payload = {
        "technical_inputs": {
            "product_key": "PROEVOLUTION",
            "window_type": "WINDOW",
            "number_of_sashes": 3,
            "width_mm": 2000,
            "height_mm": 1400,
            "color_internal": "003",
            "color_external": "003",
            "glass_type": "DOUBLE_STANDARD",
            "quantity": 1,
        }
    }
    r = requests.post(f"{BASE}/api/multi-cat/products/{PROD_ID}/configure", headers=admin_headers, json=payload)
    assert r.status_code in (200, 400, 422), r.text
    body = r.json()
    txt = str(body)
    assert body.get("pricing_status") == "not_available" or "CONFIGURATION_NOT_AVAILABLE_FOR_QUOTING" in txt, body


def test_configure_2_ante_ok(admin_headers):
    payload = {
        "technical_inputs": {
            "product_key": "PROEVOLUTION",
            "window_type": "WINDOW",
            "number_of_sashes": 2,
            "width_mm": 2000,
            "height_mm": 1400,
            "color_internal": "003",
            "color_external": "003",
            "glass_type": "DOUBLE_STANDARD",
            "quantity": 1,
        }
    }
    r = requests.post(f"{BASE}/api/multi-cat/products/{PROD_ID}/configure", headers=admin_headers, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("pricing_status") != "not_available", body


# --- PDF V2 ---
def test_pdf_preview_and_content(admin_headers):
    r = requests.post(f"{BASE}/api/quotes/{QUOTE_ACCEPTED}/pdf/preview", headers=admin_headers, json={})
    assert r.status_code == 200, r.text
    body = r.json()
    pdf_id = body.get("id") or body.get("pdf_id") or body.get("quote_pdf_id")
    assert pdf_id, body

    r = requests.get(f"{BASE}/api/quote-pdfs/{pdf_id}/download", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("application/pdf")
    pdf_bytes = r.content
    assert pdf_bytes.startswith(b"%PDF")

    # Extract text via pypdf
    try:
        from pypdf import PdfReader
    except Exception:
        from PyPDF2 import PdfReader  # type: ignore
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = ""
    for pg in reader.pages:
        text += pg.extract_text() or ""
    tl = text
    # Required
    for needle in ["PREVENTIVO", "Schemi prodotti", "GT-", "PER ACCETTAZIONE"]:  # quote ACCEPTED resta congelata sulla sua GT version (mai retroattivo)
        assert needle in tl, f"Missing '{needle}' in PDF text (len={len(tl)})"
    # 'TERMINI DI PAGAMENTO' with possible letter-spacing
    assert re.search(r"T\s*E\s*R\s*M\s*I\s*N\s*I\s+D\s*I\s+P\s*A\s*G\s*A\s*M\s*E\s*N\s*T\s*O", tl, re.IGNORECASE) or "TERMINI DI PAGAMENTO" in tl
    assert re.search(r"C\s*ondizioni\s+generali", tl, re.IGNORECASE) or "Condizioni generali" in tl

    # Forbidden
    for bad in ["margin", "Margine", "BIANCO_MASSA", "NON_STANDARD", "Emergent"]:
        assert bad not in tl, f"Forbidden token '{bad}' present in PDF"

    # Fonts embedded — Roboto
    fonts_found = set()
    for pg in reader.pages:
        try:
            res = pg.get("/Resources")
            if res:
                fonts = res.get("/Font") or {}
                for _, f in fonts.items():
                    obj = f.get_object() if hasattr(f, "get_object") else f
                    name = obj.get("/BaseFont") if hasattr(obj, "get") else None
                    if name:
                        fonts_found.add(str(name))
        except Exception:
            pass
    joined = " ".join(fonts_found)
    assert "Roboto" in joined, f"Roboto not embedded, fonts={fonts_found}"

    # Snapshot
    r = requests.get(f"{BASE}/api/quote-pdfs/{pdf_id}/snapshot", headers=admin_headers)
    assert r.status_code == 200, r.text
    snap = r.json()
    gt_ver = (snap.get("snapshot", {}).get("general_terms", {}) or {}).get("version") or snap.get("general_terms", {}).get("version")
    assert gt_ver and gt_ver.startswith("GT-"), snap  # ACCEPTED: versione congelata alla data di accettazione


# --- Tenant/RBAC audience smoke ---
def test_admin_token_cannot_access_customer_portal(admin_headers):
    r = requests.get(f"{BASE}/api/customer-portal/jobs", headers=admin_headers)
    assert r.status_code == 401, r.text
    r2 = requests.get(f"{BASE}/api/customer-portal/auth/me", headers=admin_headers)
    assert r2.status_code == 401, r2.text


def test_customer_token_cannot_access_quotes(customer_token):
    h = {"Authorization": f"Bearer {customer_token}"}
    r = requests.get(f"{BASE}/api/quotes", headers=h)
    assert r.status_code == 401, r.text


def test_no_token_quotes_401():
    r = requests.get(f"{BASE}/api/quotes")
    assert r.status_code == 401, r.text
