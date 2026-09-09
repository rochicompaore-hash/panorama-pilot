"""Backend spot-checks referenced by the P0 visuals frontend test iteration."""
import os
import re
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://serramento-ops.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@infissiexpress.com"
ADMIN_PW = "Admin!2025"

QUOTE_ID = "540b194f-798b-4b36-a129-60addcd689a5"
CASSONETTO_PID = "dc5ac292-692f-4aa9-8065-83bd7664928c"
WINDOW_PID = "8e1cafd0-9707-47c7-8939-b97c9a404021"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}"}


def _win_payload(ci, ce):
    return {
        "technical_inputs": {
            "product_key": "PROEVOLUTION",
            "window_type": "WINDOW",
            "number_of_sashes": 2,
            "width_mm": 1200,
            "height_mm": 1400,
            "glass_type": "DOUBLE_STANDARD",
            "quantity": 1,
            "color_internal": ci,
            "color_external": ce,
        }
    }


def test_window_003_003_no_surcharge(H):
    r = requests.post(f"{BASE}/api/multi-cat/products/{WINDOW_PID}/configure", json=_win_payload("003", "003"), headers=H, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("pricing_status") == "ok"
    fs = d.get("technical_snapshot", {}).get("foil_surcharge")
    assert (fs or 0) == 0, f"expected 0 foil, got {fs}"


def test_window_003_110_foil(H):
    r = requests.post(f"{BASE}/api/multi-cat/products/{WINDOW_PID}/configure", json=_win_payload("003", "110"), headers=H, timeout=30)
    d = r.json()
    fs = d.get("technical_snapshot", {}).get("foil_surcharge") or 0
    assert fs > 0, d
    assert d.get("visual", {}).get("is_bicolor") is False


def test_window_110_110_single_surcharge(H):
    r1 = requests.post(f"{BASE}/api/multi-cat/products/{WINDOW_PID}/configure", json=_win_payload("003", "110"), headers=H, timeout=30).json()
    r2 = requests.post(f"{BASE}/api/multi-cat/products/{WINDOW_PID}/configure", json=_win_payload("110", "110"), headers=H, timeout=30).json()
    assert (r1["technical_snapshot"].get("foil_surcharge") or 0) == (r2["technical_snapshot"].get("foil_surcharge") or 0)


def test_window_110_154_bicolor(H):
    r = requests.post(f"{BASE}/api/multi-cat/products/{WINDOW_PID}/configure", json=_win_payload("110", "154"), headers=H, timeout=30)
    d = r.json()
    assert d.get("visual", {}).get("is_bicolor") is True


def test_window_003_019_needs_po(H):
    r = requests.post(f"{BASE}/api/multi-cat/products/{WINDOW_PID}/configure", json=_win_payload("003", "019"), headers=H, timeout=30)
    d = r.json()
    blocks = d.get("blocking_errors") or []
    joined = " ".join([str(b) for b in blocks])
    assert "NEEDS_PO_PRICING" in joined, blocks


def test_window_003_999_unknown(H):
    r = requests.post(f"{BASE}/api/multi-cat/products/{WINDOW_PID}/configure", json=_win_payload("003", "999"), headers=H, timeout=30)
    d = r.json()
    joined = " ".join([str(b) for b in (d.get("blocking_errors") or [])])
    assert "UNKNOWN_COLOR_CODE" in joined, d


def _cas_payload(cc):
    return {"simple_inputs": {"options": {"color_code": cc}, "quantity": 1}}


@pytest.mark.parametrize("cc,fam", [("003", "BIANCO_MASSA"), ("110", "STANDARD"), ("019", "NON_STANDARD")])
def test_cassonetto_family(H, cc, fam):
    r = requests.post(f"{BASE}/api/multi-cat/products/{CASSONETTO_PID}/configure", json=_cas_payload(cc), headers=H, timeout=30)
    d = r.json()
    assert d.get("pricing_status") == "ok", d
    got = d.get("simple_snapshot", {}).get("finish_family")
    assert got == fam, f"cc={cc} expected {fam} got {got}"


def test_cassonetto_unmapped_999(H):
    r = requests.post(f"{BASE}/api/multi-cat/products/{CASSONETTO_PID}/configure", json=_cas_payload("999"), headers=H, timeout=30)
    d = r.json()
    assert d.get("pricing_status") == "invalid_inputs", d
    joined = " ".join([str(b) for b in (d.get("blocking_errors") or [])])
    assert "CASSONETTO_COLOR_FAMILY_UNMAPPED" in joined, d


def test_pdf_preview_contains_schemi(H):
    r = requests.post(f"{BASE}/api/quotes/{QUOTE_ID}/pdf/preview", json={}, headers=H, timeout=60)
    assert r.status_code == 200, r.text
    pid = r.json().get("id") or r.json().get("pdf_id") or r.json().get("preview_id")
    assert pid, r.json()
    r2 = requests.get(f"{BASE}/api/quote-pdfs/{pid}/download", headers=H, timeout=60)
    assert r2.status_code == 200
    assert r2.content[:4] == b"%PDF"
    try:
        from pypdf import PdfReader
        import io
        text = "\n".join([(p.extract_text() or "") for p in PdfReader(io.BytesIO(r2.content)).pages])
    except Exception:
        text = r2.content.decode("latin-1", errors="ignore")
    assert "Schemi prodotti" in text, "missing Schemi prodotti section"
    assert "Colore interno" in text, "missing 'Colore interno' label"
    assert "BIANCO_MASSA" not in text, "internal family leaked in PDF"
    assert "NON_STANDARD" not in text, "internal family leaked in PDF"
