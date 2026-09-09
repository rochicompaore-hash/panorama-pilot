"""P0 msg 625 — QUOTE VISUALS + WINDOW/CASSONETTO COLOR ENGINE (golden tests).

Copre §18 (window color), §19 (cassonetto), §20 (visual parity UI/PDF), §3 (snapshot congelato),
§22 blocker (003 surcharge, bicolore perso, codice sconosciuto con fallback, save/reload cambia visual).
"""
from __future__ import annotations

import os
import pytest
import requests

from app.services.color_engine import (
    resolve_cassonetto_family, resolve_color_classification, window_foil_surcharge_applicable,
)
from app.services.visual_spec import render_svg, build_visual
from app.services.pdf_renderer import build_snapshot
from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
WINDOW_PID = "8e1cafd0-9707-47c7-8939-b97c9a404021"
CASS_PID = "dc5ac292-692f-4aa9-8065-83bd7664928c"


# ---------------- unit: color engine ----------------
# COLOR INPUT V2 (msg 631): 003 WHITE_MASS · 100/110/154/096/048/964 STANDARD · altro SPECIAL
@pytest.mark.parametrize("code,cls", [("003", "WHITE_MASS"), ("100", "STANDARD"), ("110", "STANDARD"), ("154", "STANDARD"), ("096", "STANDARD"),
                                      ("048", "STANDARD"), ("964", "STANDARD"), ("019", "SPECIAL"), ("402", "SPECIAL"), ("7016", "SPECIAL"),
                                      ("RAL7016", "SPECIAL"), ("xyz123", "SPECIAL"), (" 096 ", "STANDARD")])
def test_color_classification(code, cls):
    assert resolve_color_classification(code) == cls


@pytest.mark.parametrize("code,fam", [("003", "BIANCO_MASSA"), ("110", "STANDARD"), ("048", "STANDARD"), ("964", "STANDARD"),
                                      ("019", "NON_STANDARD"), ("777", "NON_STANDARD"), ("RAL7016", "NON_STANDARD")])
def test_cassonetto_family_mapping(code, fam):
    assert resolve_cassonetto_family(code) == fam  # SPECIAL -> griglia NON_STANDARD esistente


@pytest.mark.parametrize("code", ["", None, "  "])
def test_cassonetto_missing_code_fail_closed(code):
    with pytest.raises(ValueError):
        resolve_cassonetto_family(code)


def test_window_foil_policy():
    assert window_foil_surcharge_applicable("MASS_COLOR", "MASS_COLOR") is False
    assert window_foil_surcharge_applicable("MASS_COLOR", "STANDARD") is True
    assert window_foil_surcharge_applicable("STANDARD", "STANDARD") is True
    with pytest.raises(ValueError):
        window_foil_surcharge_applicable("MASS_COLOR", "SPECIAL")


def test_render_svg_deterministic_and_view_colors():
    spec = dict(product_type="WINDOW", width_mm=1200, height_mm=1400, quantity=1, sash_count=2, opening_configuration="ANTA_RIBALTA",
                hinge_side="DX", glass_type="DOUBLE_SATIN", interior_color_code="003", interior_color_hex="#F5F5F0",
                exterior_color_code="110", exterior_color_hex="#B87333")
    a, b = render_svg(spec, "INTERIOR"), render_svg(spec, "INTERIOR")
    assert a == b and "#F5F5F0" in a and "#B87333" not in a
    ext = render_svg(spec, "EXTERIOR")
    assert "#B87333" in ext and "VISTA ESTERNA" in ext
    assert "satin-" in a  # vetro satinato -> pattern
    v = build_visual(spec)
    assert v["is_bicolor"] is True and v["svg_interior"] != v["svg_exterior"]


# ---------------- API ----------------
@pytest.fixture(scope="module")
def tok():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    r.raise_for_status()
    d = r.json()
    return d.get("access_token") or d.get("token")


def _cfg_window(tok, ci, ce, mode="BICOLOR", sashes=2, glass="DOUBLE_STANDARD"):
    body = {"technical_inputs": {"product_key": "PROEVOLUTION", "window_type": "WINDOW", "number_of_sashes": sashes, "width_mm": 1200,
                                 "height_mm": 1400, "color_internal": ci, "color_external": ce, "color_mode": mode, "glass_type": glass,
                                 "quantity": 1, "opening_configuration": "ANTA_RIBALTA", "hinge_side": "DX"}}
    r = requests.post(f"{BASE_URL}/api/multi-cat/products/{WINDOW_PID}/configure", json=body, headers={"Authorization": f"Bearer {tok}"})
    r.raise_for_status()
    return r.json()


def test_window_003_003_no_surcharge(tok):
    d = _cfg_window(tok, "003", "003", "WHITE_MASS")
    assert d["pricing_status"] == "ok"
    assert float(d["technical_snapshot"]["foil_surcharge"]) == 0
    s = d["visual"]["spec"]
    assert s["interior_color_code"] == s["exterior_color_code"] == "003" and d["visual"]["is_bicolor"] is False


def test_window_003_110_white_in_foil_out(tok):
    base = _cfg_window(tok, "003", "003", "WHITE_MASS")
    d = _cfg_window(tok, "003", "110", "WHITE_IN_FOIL_OUT")
    assert d["pricing_status"] == "ok"
    assert float(d["technical_snapshot"]["foil_surcharge"]) > 0
    assert d["commercial_snapshot"]["final_unit_price"] > base["commercial_snapshot"]["final_unit_price"]
    s = d["visual"]["spec"]
    assert (s["interior_color_code"], s["exterior_color_code"]) == ("003", "110")
    assert s["interior_color_hex"] in d["visual"]["svg_interior"] and s["exterior_color_hex"] in d["visual"]["svg_exterior"]


def test_window_110_110_single_surcharge(tok):
    one = _cfg_window(tok, "003", "110", "WHITE_IN_FOIL_OUT")
    two = _cfg_window(tok, "110", "110", "FOIL_BOTH_SAME")
    assert two["pricing_status"] == "ok"
    assert float(two["technical_snapshot"]["foil_surcharge"]) == float(one["technical_snapshot"]["foil_surcharge"])  # nessun doppio surcharge
    assert two["visual"]["is_bicolor"] is False and two["visual"]["svg_interior"].count("#B87333") > 0


def test_window_110_154_bicolor(tok):
    d = _cfg_window(tok, "110", "154", "BICOLOR")
    assert d["pricing_status"] == "ok" and d["visual"]["is_bicolor"] is True
    s = d["visual"]["spec"]
    assert (s["interior_color_code"], s["exterior_color_code"]) == ("110", "154")


def test_window_special_fail_closed_needs_po_pricing(tok):
    for ext in ("019", "999", "7016"):  # SPECIAL (anche codici nuovi): NEEDS_PO_PRICING, mai UNKNOWN_COLOR_CODE
        d = _cfg_window(tok, "003", ext)
        assert d["pricing_status"] != "ok" and any("NEEDS_PO_PRICING" in e for e in d["blocking_errors"]), d["blocking_errors"]
        assert not any("UNKNOWN_COLOR_CODE" in e for e in d["blocking_errors"])


def test_window_free_name_and_leading_zero(tok):
    body = {"technical_inputs": {"product_key": "PROEVOLUTION", "window_type": "WINDOW", "number_of_sashes": 2, "width_mm": 1200, "height_mm": 1400,
                                 "color_internal": "003", "color_internal_name": "Bianco massa", "color_external": "096", "color_external_name": "Rovere personalizzato",
                                 "color_mode": "WHITE_IN_FOIL_OUT", "glass_type": "DOUBLE_STANDARD", "quantity": 1}}
    d = requests.post(f"{BASE_URL}/api/multi-cat/products/{WINDOW_PID}/configure", json=body, headers={"Authorization": f"Bearer {tok}"}).json()
    assert d["pricing_status"] == "ok" and float(d["technical_snapshot"]["foil_surcharge"]) > 0  # STANDARD dal codice, non dal nome
    s = d["visual"]["spec"]
    assert s["exterior_color_code"] == "096" and s["exterior_color_name"] == "Rovere personalizzato" and s["exterior_color_classification"] == "STANDARD"


def _cfg_cass(tok, code):
    body = {"simple_inputs": {"width_mm": 1200, "height_mm": 250, "quantity": 1, "options": {"color_code": code, "depth_mm": 163, "ceiling_liner": "SI"}}}
    r = requests.post(f"{BASE_URL}/api/multi-cat/products/{CASS_PID}/configure", json=body, headers={"Authorization": f"Bearer {tok}"})
    r.raise_for_status()
    return r.json()


@pytest.mark.parametrize("code,fam", [("003", "BIANCO_MASSA"), ("110", "STANDARD"), ("019", "NON_STANDARD"), ("777", "NON_STANDARD")])
def test_cassonetto_live_price_family(tok, code, fam):
    d = _cfg_cass(tok, code)
    assert d["pricing_status"] == "ok" and d["simple_snapshot"]["finish_family"] == fam
    assert "foil_surcharge" not in (d.get("simple_snapshot") or {})  # nessun surcharge finestra
    spec = d["visual"]["spec"]
    assert spec["product_type"] == "ROLLER_BOX" and spec["roller_box_color"]["code"] == code
    assert spec["roller_box_dimensions"]["depth_mm"] == 163


def test_cassonetto_missing_code_blocked(tok):
    d = _cfg_cass(tok, "")
    assert d["pricing_status"] != "ok" and "MISSING_COLOR_CODE" in " ".join(d["blocking_errors"])


# ---------------- save / reload / modify / pdf parity ----------------
@pytest.fixture(scope="module")
def quote(tok):
    h = {"Authorization": f"Bearer {tok}"}
    cust = requests.get(f"{BASE_URL}/api/customers?limit=1", headers=h).json()
    cid = (cust.get("items") or cust)[0]["id"]
    r = requests.post(f"{BASE_URL}/api/quotes", json={"title": "P0-625 VISUAL PARITY", "customer_id": cid}, headers=h)
    r.raise_for_status()
    return r.json()


def _line_payload(cfg, pid, model, cat, key):
    return {"category": cat.lower(), "product_key": key, "quantity": 1, "width_mm": cfg["width_mm"], "height_mm": cfg["height_mm"],
            "base_price": 1, "unit_price_final": 1, "subtotal_line": 1, "description": f"{key} test", "source": "MULTI_CATEGORY_V1",
            "category_code": cat, "product_id": pid, "product_code": key, "pricing_model": model, "configuration_snapshot": cfg}


def test_save_reload_modify_pdf_parity(tok, quote):
    h = {"Authorization": f"Bearer {tok}"}
    qid = quote["id"]
    cfg = {"window_type": "WINDOW", "number_of_sashes": 2, "width_mm": 1200, "height_mm": 1400, "color_mode": "BICOLOR",
           "color_internal": "110", "color_external": "154", "glass_type": "DOUBLE_SATIN", "opening_configuration": "ANTA_RIBALTA", "hinge_side": "DX", "quantity": 1}
    r = requests.post(f"{BASE_URL}/api/quotes/{qid}/lines", json=_line_payload(cfg, WINDOW_PID, "FORMULA_TECHNICAL", "FINESTRE", "PROEVOLUTION"), headers=h)
    assert r.status_code == 200, r.text
    line = r.json()
    vs = line["visual_spec"]
    assert vs["is_bicolor"] is True and vs["spec"]["interior_color_code"] == "110" and vs["spec"]["exterior_color_code"] == "154"
    # bicolore NON salvato come monocolore
    assert line["configuration_snapshot"]["color_internal"] != line["configuration_snapshot"]["color_external"]

    # RELOAD: stesso visual
    q = requests.get(f"{BASE_URL}/api/quotes/{qid}", headers=h).json()
    saved = next(l for l in q["lines"] if l["id"] == line["id"])
    assert saved["visual_spec"] == vs

    # cassonetto 003
    ccfg = {"width_mm": 1200, "height_mm": 250, "depth_mm": 326, "ceiling_liner": "NO", "color_code": "003", "quantity": 1}
    r = requests.post(f"{BASE_URL}/api/quotes/{qid}/lines", json=_line_payload(ccfg, CASS_PID, "GRID", "CASSONETTI", "CASSONETTO_STD"), headers=h)
    assert r.status_code == 200, r.text
    cl = r.json()
    assert cl["simple_snapshot"]["finish_family"] == "BIANCO_MASSA"
    assert cl["visual_spec"]["spec"]["roller_box_dimensions"] == {"width_mm": 1200, "height_mm": 250, "depth_mm": 326, "ceiling_liner": "NO"}

    # cassonetto codice nuovo (SPECIAL) -> prezzato sulla griglia NON_STANDARD, leading zero preservato su save/reload
    sp = dict(ccfg, color_code="096", color_name="Rovere")
    r = requests.post(f"{BASE_URL}/api/quotes/{qid}/lines", json=_line_payload(sp, CASS_PID, "GRID", "CASSONETTI", "CASSONETTO_STD"), headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["configuration_snapshot"]["color_code"] == "096" and r.json()["visual_spec"]["spec"]["roller_box_color"] == {"code": "096", "name": "Rovere", "hex": r.json()["visual_spec"]["spec"]["roller_box_color"]["hex"], "classification": "STANDARD"}

    # MODIFY: 110/154 -> 003/110, 1 anta
    cfg2 = dict(cfg, color_mode="WHITE_IN_FOIL_OUT", color_internal="003", color_external="110", number_of_sashes=1)
    r = requests.put(f"{BASE_URL}/api/quotes/{qid}/lines/{line['id']}/reconfigure", json=_line_payload(cfg2, WINDOW_PID, "FORMULA_TECHNICAL", "FINESTRE", "PROEVOLUTION"), headers=h)
    assert r.status_code == 200, r.text
    mod = r.json()
    ms = mod["visual_spec"]["spec"]
    assert (ms["interior_color_code"], ms["exterior_color_code"], ms["sash_count"]) == ("003", "110", 1)
    assert mod["visual_spec"]["svg_exterior"] != vs["svg_exterior"]

    # PDF parity: lo snapshot PDF usa ESATTAMENTE il visual_spec della riga (stesso svg, stesso spec)
    q = requests.get(f"{BASE_URL}/api/quotes/{qid}", headers=h).json()
    snap = build_snapshot(quote=q, company={"name": "X"}, template={}, clauses=[], payment_terms={}, kind="preview")
    pdf_lines = {l["id"]: l for l in snap["quote"]["lines"]}
    for l in q["lines"]:
        if l.get("visual_spec"):
            assert pdf_lines[l["id"]]["visual_spec"] == l["visual_spec"]
            for k in ("width_mm", "height_mm", "sash_count", "glass_type", "interior_color_code", "exterior_color_code", "product_type"):
                assert pdf_lines[l["id"]]["visual_spec"]["spec"][k] == l["visual_spec"]["spec"][k]
    schemes = snap["quote"]["visual_schemes"]
    assert len(schemes) == 3  # una visual per configurazione, nessuna duplicazione
    assert {s["svg_exterior"] for s in schemes} == {l["visual_spec"]["svg_exterior"] for l in q["lines"] if l.get("visual_spec")}
    for s in schemes:
        assert "BIANCO_MASSA" not in s["details"] and "NON_STANDARD" not in s["details"]  # mai price family nel PDF cliente

    # PDF reale generato senza errori
    r = requests.post(f"{BASE_URL}/api/quotes/{qid}/pdf/preview", json={}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["size_bytes"] > 10000

    requests.delete(f"{BASE_URL}/api/quotes/{qid}", headers=h)


# ---------------- PO msg 627: 3/4 ante = DISABLED_FAIL_CLOSED (nessun dato ferramenta/ricetta autoritativo) ----------------
def test_quotable_configurations_exposed(tok):
    r = requests.get(f"{BASE_URL}/api/multi-cat/products/{WINDOW_PID}", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    q = r.json()["quotable_configurations"]
    assert q == {"WINDOW": [1, 2], "DOOR_WINDOW": [1, 2]}


@pytest.mark.parametrize("n", [3, 4])
def test_3_4_sash_fail_closed_api(tok, n):
    d = _cfg_window(tok, "003", "003", "WHITE_MASS", sashes=n)
    assert d["pricing_status"] == "not_available"
    assert "CONFIGURATION_NOT_AVAILABLE_FOR_QUOTING" in d["blocking_errors"][0]
    assert d.get("commercial_snapshot") is None
    h = {"Authorization": f"Bearer {tok}"}
    cust = requests.get(f"{BASE_URL}/api/customers?limit=1", headers=h).json()
    qid = requests.post(f"{BASE_URL}/api/quotes", json={"title": "3-4 SASH BLOCK", "customer_id": (cust.get("items") or cust)[0]["id"]}, headers=h).json()["id"]
    cfg = {"window_type": "WINDOW", "number_of_sashes": n, "width_mm": 2000, "height_mm": 1400, "color_internal": "003", "color_external": "003", "glass_type": "DOUBLE_STANDARD", "quantity": 1}
    r = requests.post(f"{BASE_URL}/api/quotes/{qid}/lines", json=_line_payload(cfg, WINDOW_PID, "FORMULA_TECHNICAL", "FINESTRE", "PROEVOLUTION"), headers=h)
    assert r.status_code == 400 and "CONFIGURATION_NOT_AVAILABLE_FOR_QUOTING" in r.text
    requests.delete(f"{BASE_URL}/api/quotes/{qid}", headers=h)
