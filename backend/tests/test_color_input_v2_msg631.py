"""COLOR INPUT V2 (msg 631) — code+name flow for windows/cassonetti and PDF text.

Covers requested matrix in review:
- WINDOW: X in [100,110,154,096,048,964] STANDARD, code preserved (096 stays '096'), name preserved, foil>0
- WINDOW: X in [019,402,7016,RAL7016] SPECIAL → NEEDS_PO_PRICING never UNKNOWN_COLOR_CODE
- WINDOW: X='003' → foil_surcharge==0; X='' → COLOR_CODE_REQUIRED
- CASSONETTO: 003→BIANCO_MASSA; 110/964→STANDARD; 019/777/RAL7016→NON_STANDARD price>0; ''→MISSING_COLOR_CODE
- PDF text: contains '096 — Rovere personalizzato' and '003 — Bianco massa'/BIANCO MASSA,
  MUST NOT contain 'STANDARD', 'SPECIAL', 'WHITE_MASS', '+10%'
"""
from __future__ import annotations

import io
import os
import re

import pytest
import requests

from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
WINDOW_PID = "8e1cafd0-9707-47c7-8939-b97c9a404021"
CASS_PID = "dc5ac292-692f-4aa9-8065-83bd7664928c"


@pytest.fixture(scope="module")
def tok():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    r.raise_for_status()
    d = r.json()
    return d.get("access_token") or d.get("token")


@pytest.fixture(scope="module")
def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------------- WINDOW: STANDARD matrix ----------------
def _configure_window(auth, ce, cename="Nome libero", ci="003", ciname="Bianco massa", mode="WHITE_IN_FOIL_OUT"):
    body = {"technical_inputs": {
        "product_key": "PROEVOLUTION", "window_type": "WINDOW", "number_of_sashes": 2,
        "width_mm": 1200, "height_mm": 1400,
        "glass_type": "DOUBLE_STANDARD", "quantity": 1,
        "color_internal": ci, "color_internal_name": ciname,
        "color_external": ce, "color_external_name": cename,
        "color_mode": mode,
    }}
    r = requests.post(f"{BASE_URL}/api/multi-cat/products/{WINDOW_PID}/configure", json=body, headers=auth)
    r.raise_for_status()
    return r.json()


@pytest.mark.parametrize("code", ["100", "110", "154", "096", "048", "964"])
def test_window_standard_codes_surcharge_and_preservation(auth, code):
    d = _configure_window(auth, code, cename="Nome libero")
    assert d["pricing_status"] == "ok", d.get("blocking_errors")
    assert float(d["technical_snapshot"]["foil_surcharge"]) > 0
    s = d["visual"]["spec"]
    # code preserved as string (096 stays '096')
    assert s["exterior_color_code"] == code, f"expected {code!r}, got {s['exterior_color_code']!r}"
    assert s["exterior_color_name"] == "Nome libero"
    assert s["exterior_color_classification"] == "STANDARD"


def test_window_003_no_surcharge(auth):
    d = _configure_window(auth, "003", cename="Bianco massa", mode="WHITE_MASS")
    assert d["pricing_status"] == "ok"
    assert float(d["technical_snapshot"]["foil_surcharge"]) == 0


@pytest.mark.parametrize("code", ["019", "402", "7016", "RAL7016"])
def test_window_special_needs_po_pricing_never_unknown(auth, code):
    d = _configure_window(auth, code, cename="Grigio antracite")
    errs = " ".join(d.get("blocking_errors") or [])
    assert d["pricing_status"] != "ok", errs
    assert "NEEDS_PO_PRICING" in errs, errs
    assert "UNKNOWN_COLOR_CODE" not in errs, errs


def test_window_missing_external_code_required(auth):
    d = _configure_window(auth, "", cename="Ignored")
    errs = " ".join(d.get("blocking_errors") or [])
    assert d["pricing_status"] == "incomplete" and d.get("technical_snapshot") is None
    assert "COLOR_CODE_REQUIRED" in errs, errs


def test_window_missing_external_name_required(auth):
    d = _configure_window(auth, "096", cename="")
    errs = " ".join(d.get("blocking_errors") or [])
    assert d["pricing_status"] == "incomplete" and "COLOR_NAME_REQUIRED" in errs, errs


def test_window_bicolor_missing_internal_code_required(auth):
    d = _configure_window(auth, "154", cename="Noce", ci="", ciname="", mode="BICOLOR")
    errs = " ".join(d.get("blocking_errors") or [])
    assert d["pricing_status"] == "incomplete" and "COLOR_CODE_REQUIRED" in errs and "internal" in errs, errs


# ---------------- CASSONETTO matrix ----------------
def _configure_cass(auth, color_code, color_name="X"):
    body = {"simple_inputs": {"width_mm": 1200, "height_mm": 250, "quantity": 1,
                              "options": {"color_code": color_code, "color_name": color_name,
                                          "depth_mm": 163, "ceiling_liner": "SI"}}}
    r = requests.post(f"{BASE_URL}/api/multi-cat/products/{CASS_PID}/configure", json=body, headers=auth)
    r.raise_for_status()
    return r.json()


@pytest.mark.parametrize("code,fam", [("003", "BIANCO_MASSA"), ("110", "STANDARD"), ("964", "STANDARD"),
                                       ("019", "NON_STANDARD"), ("777", "NON_STANDARD"), ("RAL7016", "NON_STANDARD")])
def test_cassonetto_family_and_price(auth, code, fam):
    d = _configure_cass(auth, code, "Nome")
    assert d["pricing_status"] == "ok", d.get("blocking_errors")
    assert d["simple_snapshot"]["finish_family"] == fam
    ss = d["simple_snapshot"]
    price = float(ss.get("unit_price_final") or ss.get("sale_price_total") or ss.get("customer_sale_price_per_item") or 0)
    assert price > 0, ss


def test_cassonetto_missing_code(auth):
    d = _configure_cass(auth, "", "X")
    errs = " ".join(d.get("blocking_errors") or [])
    assert d["pricing_status"] != "ok"
    assert "MISSING_COLOR_CODE" in errs, errs


# ---------------- PDF: text contains code — name, no internal labels ----------------
def _line_payload(cfg, pid, model, cat, key):
    return {"category": cat.lower(), "product_key": key, "quantity": 1,
            "width_mm": cfg["width_mm"], "height_mm": cfg["height_mm"],
            "base_price": 1, "unit_price_final": 1, "subtotal_line": 1,
            "description": f"{key} test", "source": "MULTI_CATEGORY_V1",
            "category_code": cat, "product_id": pid, "product_code": key,
            "pricing_model": model, "configuration_snapshot": cfg}


def test_pdf_shows_code_and_name_and_no_internal_labels(auth):
    cust = requests.get(f"{BASE_URL}/api/customers?limit=1", headers=auth).json()
    cid = (cust.get("items") or cust)[0]["id"]
    q = requests.post(f"{BASE_URL}/api/quotes",
                      json={"title": "MSG631 PDF PARITY", "customer_id": cid}, headers=auth).json()
    qid = q["id"]
    try:
        cfg = {"window_type": "WINDOW", "number_of_sashes": 2, "width_mm": 1200, "height_mm": 1400,
               "color_mode": "WHITE_IN_FOIL_OUT",
               "color_internal": "003", "color_internal_name": "Bianco massa",
               "color_external": "096", "color_external_name": "Rovere personalizzato",
               "glass_type": "DOUBLE_STANDARD", "quantity": 1}
        r = requests.post(f"{BASE_URL}/api/quotes/{qid}/lines",
                          json=_line_payload(cfg, WINDOW_PID, "FORMULA_TECHNICAL", "FINESTRE", "PROEVOLUTION"),
                          headers=auth)
        assert r.status_code == 200, r.text
        line = r.json()

        # snapshot round-trip
        got = requests.get(f"{BASE_URL}/api/quotes/{qid}", headers=auth).json()
        saved = next(x for x in got["lines"] if x["id"] == line["id"])
        assert saved["configuration_snapshot"]["color_external"] == "096"
        assert saved["visual_spec"]["spec"]["exterior_color_name"] == "Rovere personalizzato"

        # PDF preview -> download bytes via /api/quote-pdfs/{pid}/download
        prev = requests.post(f"{BASE_URL}/api/quotes/{qid}/pdf/preview", json={}, headers=auth)
        assert prev.status_code == 200, prev.text
        prev_data = prev.json()
        pid = prev_data.get("id")
        assert pid, prev_data
        dl = requests.get(f"{BASE_URL}/api/quote-pdfs/{pid}/download", headers=auth, allow_redirects=True)
        assert dl.status_code == 200, dl.text[:500]
        pdf_bytes = dl.content
        assert pdf_bytes[:4] == b"%PDF", f"not a PDF: {pdf_bytes[:16]!r}"

        # extract text
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader  # type: ignore
        text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf_bytes)).pages)
        norm = text.replace("\u2014", "—").replace("\u2013", "—").replace("-", "—") if False else text

        # allow either em-dash or hyphen variants of separator
        def _has(sub):
            return sub in text
        assert _has("096") and _has("Rovere personalizzato"), text[:2000]
        # separator between code and name (— preferred)
        assert re.search(r"096\s*[—\-–]\s*Rovere personalizzato", text), text[:2000]
        assert (re.search(r"003\s*[—\-–]\s*Bianco massa", text, re.IGNORECASE) or
                "BIANCO MASSA" in text.upper()), text[:2000]
        # internal price labels must NOT leak next to color info in customer PDF.
        # Strict check: these tokens (unique to internal classification) must never appear.
        for forbidden in ("SPECIAL", "WHITE_MASS", "+10%", "BIANCO_MASSA", "NON_STANDARD"):
            assert forbidden not in text, f"forbidden token {forbidden!r} found in PDF"
        # Word 'STANDARD' appears legitimately in the PDF ('CONSEGNA STANDARD', 'ENEA STANDARD');
        # ensure it never appears next to a color code line (i.e., as a classification tag).
        for m in re.finditer(r"(?:Colore\s+(?:interno|esterno)|Interno|Esterno)\s+\S+\s*[—\-–]\s*[^\n]{0,80}", text):
            frag = m.group(0)
            assert "STANDARD" not in frag.upper().replace("CONSEGNA STANDARD", "").replace("ENEA STANDARD", ""), \
                f"classification tag near color: {frag!r}"
    finally:
        requests.delete(f"{BASE_URL}/api/quotes/{qid}", headers=auth)
