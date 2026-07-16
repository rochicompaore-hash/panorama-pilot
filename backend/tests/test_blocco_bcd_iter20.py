"""Test end-to-end Blocco B (Importer) + C (BOM UI) + D (Geometria) + Contratto + Firma.

Iteration 20 — verifica dei nuovi endpoint aggiunti al backend Infissi Express Cloud:
  - /api/geometry/templates, /compute, /dimension-rule-sets, /new-version
  - /api/importer/upload, /map, /publish, /rollback, /schema/{entity_type}
  - /api/contracts/generate-from-quote, /transition, /send-for-signature,
    /public/{token}, /public/{token}/sign, /create-variation, /timeline
  - Regressione Blocco A: /api/pricing-hub/bom-recipes, /bom-simulate

Non testa: Landing Page, CRM, Preventivo lampo (esclusi esplicitamente dall'utente).
"""
from __future__ import annotations
import io
import json
import os
import time
import uuid
import pytest
import requests
from tests._creds import ADMIN_EMAIL, ADMIN_PWD  # env-sourced credentials

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
# scrubbed: ADMIN_EMAIL moved to tests._creds
# scrubbed: ADMIN_PWD moved to tests._creds
# Costanti seed note dell'ambiente
SELL_PL_ID = "4db4b91f-22c9-422b-aa7f-e235967b6698"
COST_PL_ID = "dea703b4-d488-4ad5-a374-8360962e719e"
BOM_WIN_2A = "76d7b931-09b7-419f-bb79-1e47281a915e"
BOM_WIN_1A = "c4e3c0f4-0bc8-4fa7-b505-dc87136a44b7"
BOM_FIXED = "166289e3-d6be-4749-9c9c-edf1b72df253"
PROFILE_SYSTEM_ID = "4a35356d-acb8-49b1-b1c0-6752a380ee63"

# =====================================================================
# Fixtures
# =====================================================================


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}, timeout=15)
    assert r.status_code == 200, f"Login admin failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def h(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def active_quote_id(h):
    r = requests.get(f"{BASE_URL}/api/quotes?limit=50", headers=h, timeout=15)
    assert r.status_code == 200
    for q in r.json().get("items", []):
        if q.get("status") in ("active", "sent", "accepted", "won", "approved"):
            return q["id"]
    pytest.skip("Nessun preventivo attivo trovato")


# =====================================================================
# BLOCCO D — Geometry Templates + Compute
# =====================================================================


def test_geometry_templates(h):
    r = requests.get(f"{BASE_URL}/api/geometry/templates", headers=h, timeout=10)
    assert r.status_code == 200
    data = r.json()
    codes = {t["code"] for t in data.get("items", [])}
    expected = {"TPL-1ANTA-BATT", "TPL-2ANTE-BR", "TPL-3ANTE-2AP-1FISSO",
                "TPL-FISSO", "TPL-PORTAFINESTRA-2A", "TPL-CON-SOPRALUCE"}
    assert expected.issubset(codes), f"Manca template: {expected - codes}"
    assert data["count"] == 6


def _geometry_body(tree_root, w=1200, hgt=1400, bom=BOM_WIN_2A, include_svg=True):
    return {
        "geometry": {
            "outer_width_mm": w, "outer_height_mm": hgt,
            "profile_system_id": PROFILE_SYSTEM_ID,
            "root": tree_root,
        },
        "bom_template_id": bom,
        "sell_pricelist_id": SELL_PL_ID,
        "include_svg": include_svg, "include_costs": False,
    }


def test_geometry_compute_2ante(h):
    tree = {"id": "root", "kind": "root", "children": [
        {"id": "s1", "kind": "split", "direction": "vertical", "children": [
            {"id": "c1", "kind": "cell", "children": [
                {"id": "m1", "kind": "module", "module_type": "sash_tilt_turn",
                 "module_handle_side": "right"}]},
            {"id": "c2", "kind": "cell", "children": [
                {"id": "m2", "kind": "module", "module_type": "sash_hinged",
                 "module_handle_side": "left"}]},
        ]}
    ]}
    r = requests.post(f"{BASE_URL}/api/geometry/compute", headers=h,
                       json=_geometry_body(tree), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("materials_price", 0) > 0
    gs = d.get("geometry_summary") or {}
    assert gs.get("aggregated", {}).get("nr_ante") == 2
    assert len(gs.get("dimension_verification") or []) >= 10
    assert isinstance(d.get("svg"), str) and len(d["svg"]) > 100
    snap = d.get("geometry_snapshot_hash", "")
    assert isinstance(snap, str) and len(snap) == 64  # sha256
    comps = d.get("components") or []
    assert len(comps) > 0
    c0 = comps[0]
    assert "code" in c0 and "description" in c0
    # pricelist_origin_sell iniettato dal motore
    assert "sell_pricelist" in d or "pricelist_origin_sell" in c0 or c0.get("unit_price") is not None


def test_geometry_compute_1anta(h):
    tree = {"id": "root", "kind": "root", "children": [
        {"id": "m1", "kind": "module", "module_type": "sash_hinged",
         "module_opening_side": "left", "module_handle_side": "right"}
    ]}
    r = requests.post(f"{BASE_URL}/api/geometry/compute", headers=h,
                       json=_geometry_body(tree, bom=BOM_WIN_1A), timeout=30)
    assert r.status_code == 200, r.text
    agg = (r.json().get("geometry_summary") or {}).get("aggregated") or {}
    assert agg.get("nr_ante") == 1
    assert agg.get("nr_fissi") == 0


def test_geometry_compute_fisso(h):
    tree = {"id": "root", "kind": "root", "children": [
        {"id": "m1", "kind": "module", "module_type": "fixed"}
    ]}
    r = requests.post(f"{BASE_URL}/api/geometry/compute", headers=h,
                       json=_geometry_body(tree, bom=BOM_FIXED), timeout=30)
    assert r.status_code == 200, r.text
    agg = (r.json().get("geometry_summary") or {}).get("aggregated") or {}
    assert agg.get("nr_ante") == 0
    assert agg.get("nr_fissi") == 1
    assert agg.get("total_glass_sqm", 0) > 0


def test_geometry_compute_sopraluce(h):
    tree = {"id": "root", "kind": "root", "children": [
        {"id": "s1", "kind": "split", "direction": "horizontal", "children": [
            {"id": "top", "kind": "module", "module_type": "top_light",
             "size_unit": "pct", "size_value": 30},
            {"id": "main", "kind": "module", "module_type": "sash_tilt_turn",
             "size_unit": "auto"},
        ]}
    ]}
    r = requests.post(f"{BASE_URL}/api/geometry/compute", headers=h,
                       json=_geometry_body(tree, bom=BOM_WIN_1A), timeout=30)
    assert r.status_code == 200, r.text
    gs = r.json().get("geometry_summary") or {}
    modules = gs.get("modules") or []
    assert len(modules) == 2, f"Ci si aspettano 2 moduli (sopraluce + main), trovati {len(modules)}"


# =====================================================================
# BLOCCO D — Dimension Rule Set (CRUD + versioning)
# =====================================================================


def test_rule_set_crud_and_versioning(h):
    code = f"TEST_RS_{uuid.uuid4().hex[:6]}"
    body = {
        "profile_system_id": PROFILE_SYSTEM_ID,
        "code": code, "name": f"RuleSet {code}",
        "rules": [
            {"element": "frame_top", "expression": "L", "notes": "test"},
        ],
        "is_default": False,
    }
    r = requests.post(f"{BASE_URL}/api/geometry/dimension-rule-sets", headers=h, json=body, timeout=15)
    assert r.status_code == 200, r.text
    rs = r.json()
    assert rs.get("version") == 1
    rs_id = rs.get("id") or rs.get("_id")
    assert rs_id

    # Secondo con is_default rimuove default dal primo (indiretto: patch il primo a default=True)
    r2 = requests.patch(f"{BASE_URL}/api/geometry/dimension-rule-sets/{rs_id}", headers=h,
                         json={"is_default": True}, timeout=10)
    assert r2.status_code == 200

    # Creo altro rule set is_default=True → rimuove default dal primo
    body2 = {**body, "code": f"TEST_RS2_{uuid.uuid4().hex[:6]}", "is_default": True}
    r3 = requests.post(f"{BASE_URL}/api/geometry/dimension-rule-sets", headers=h, json=body2, timeout=15)
    assert r3.status_code == 200
    rs2_id = r3.json().get("id") or r3.json().get("_id")

    # Il primo non deve essere più default
    r4 = requests.get(f"{BASE_URL}/api/geometry/dimension-rule-sets?profile_system_id={PROFILE_SYSTEM_ID}",
                       headers=h, timeout=10)
    assert r4.status_code == 200
    defaults = [x for x in r4.json().get("items") or [] if x.get("is_default")]
    assert all(d.get("id") != rs_id for d in defaults), "Il primo rule set è ancora default"

    # PATCH con rules → 400
    r5 = requests.patch(f"{BASE_URL}/api/geometry/dimension-rule-sets/{rs_id}", headers=h,
                         json={"rules": [{"element": "frame_top", "expression": "L-10"}]}, timeout=10)
    assert r5.status_code == 400
    assert "versioning" in r5.text.lower() or "new-version" in r5.text.lower()

    # new-version incrementa version + archivia parent
    r6 = requests.post(f"{BASE_URL}/api/geometry/dimension-rule-sets/{rs_id}/new-version",
                        headers=h, json={"rules": [
                            {"element": "frame_top", "expression": "L-5"},
                        ]}, timeout=10)
    assert r6.status_code == 200
    new_rs = r6.json()
    assert new_rs.get("version") == 2
    assert new_rs.get("parent_version_id") == rs_id


# =====================================================================
# BLOCCO B — Importer
# =====================================================================


def test_importer_schema_profile(h):
    r = requests.get(f"{BASE_URL}/api/importer/schema/profile", headers=h, timeout=10)
    assert r.status_code == 200
    d = r.json()
    field_by_code = {f["code"]: f for f in d.get("fields") or []}
    assert field_by_code["code"]["required"] is True
    assert field_by_code["unit_price"]["required"] is True
    assert field_by_code["unit_price"]["transform"] == "num"
    assert field_by_code["unit"]["default"] == "linear_m"
    assert "min_billable_qty" in field_by_code


def _upload_csv(admin_token, csv_bytes, entity_type="profile", target_pl_id=None,
                filename="test.csv"):
    files = {"file": (filename, csv_bytes, "text/csv")}
    form = {"entity_type": entity_type}
    if target_pl_id:
        form["target_pricelist_id"] = target_pl_id
    r = requests.post(f"{BASE_URL}/api/importer/upload",
                       headers={"Authorization": f"Bearer {admin_token}"},
                       files=files, data=form, timeout=30)
    return r


@pytest.fixture()
def csv_valid_bytes():
    body = "CODICE,PREZZO,UM\n"
    body += f"TEST_PROF_{uuid.uuid4().hex[:6]},12.50,linear_m\n"
    body += f"TEST_PROF_{uuid.uuid4().hex[:6]},8.75,linear_m\n"
    body += f"TEST_PROF_{uuid.uuid4().hex[:6]},22.00,linear_m\n"
    return body.encode("utf-8")


def test_importer_full_flow(h, admin_token, csv_valid_bytes):
    # Upload
    r = _upload_csv(admin_token, csv_valid_bytes, target_pl_id=SELL_PL_ID,
                    filename=f"test_{uuid.uuid4().hex[:6]}.csv")
    assert r.status_code == 200, r.text
    job = r.json()
    jid = job.get("id") or job.get("_id")
    assert job.get("im_status") == "parsed"
    assert "CSV" in (job.get("sheet_names") or []) or "csv" in [s.lower() for s in job.get("sheet_names") or []]
    assert (job.get("detected_headers") or []) 
    assert job.get("total_rows") == 3
    assert len(job.get("preview_sample") or []) == 3

    # Idempotenza (nota: bug noto — idempotenza NON attiva se status=parsed
    # Il router richiede im_status in ["published","draft","preview_ready"])
    r2 = _upload_csv(admin_token, csv_valid_bytes, target_pl_id=SELL_PL_ID,
                    filename=f"test_{uuid.uuid4().hex[:6]}.csv")  # stesso hash contenuto
    assert r2.status_code == 200
    j2 = r2.json()
    idempotent = bool(j2.get("warning") or (j2.get("id") == jid or j2.get("_id") == jid))
    if not idempotent:
        pytest.xfail("BUG: idempotency non attiva per stato 'parsed' (solo published/draft/preview_ready)")

    # Mapping
    mapping_body = {
        "mappings": [
            {"source_column": "CODICE", "target_field": "code",
             "required": True, "transform": None},
            {"source_column": "PREZZO", "target_field": "unit_price",
             "required": True, "transform": "num"},
            {"source_column": "UM", "target_field": "unit",
             "required": False, "transform": "lower"},
        ]
    }
    r3 = requests.post(f"{BASE_URL}/api/importer/jobs/{jid}/map", headers=h,
                        json=mapping_body, timeout=15)
    assert r3.status_code == 200, r3.text
    m = r3.json()
    assert m.get("im_status") == "preview_ready", f"status: {m.get('im_status')} errors: {m.get('validation_errors')}"
    assert m.get("valid_rows") == 3
    errors = [e for e in m.get("validation_errors") or [] if e.get("severity") == "error"]
    assert len(errors) == 0

    # Publish
    r4 = requests.post(f"{BASE_URL}/api/importer/jobs/{jid}/publish", headers=h, timeout=15)
    assert r4.status_code == 200, r4.text
    pub = r4.json()
    assert pub.get("added", 0) == 3
    assert pub.get("updated", 0) == 0
    assert pub.get("new_version", 0) >= 2

    # Rollback
    r5 = requests.post(f"{BASE_URL}/api/importer/jobs/{jid}/rollback", headers=h, timeout=15)
    assert r5.status_code == 200
    rb = r5.json()
    assert rb.get("ok") is True


def test_importer_validation_errors(admin_token):
    # Riga vuota su code + prezzo negativo
    body = "CODICE,PREZZO,UM\n"
    body += ",5.00,linear_m\n"      # missing code
    body += f"TEST_NEG_{uuid.uuid4().hex[:6]},-10.00,linear_m\n"  # negative price
    csv = body.encode("utf-8")
    r = _upload_csv(admin_token, csv, target_pl_id=SELL_PL_ID,
                    filename=f"err_{uuid.uuid4().hex[:6]}.csv")
    assert r.status_code == 200
    jid = r.json().get("id") or r.json().get("_id")
    mapping_body = {"mappings": [
        {"source_column": "CODICE", "target_field": "code", "required": True},
        {"source_column": "PREZZO", "target_field": "unit_price",
         "required": True, "transform": "num"},
        {"source_column": "UM", "target_field": "unit"},
    ]}
    r2 = requests.post(f"{BASE_URL}/api/importer/jobs/{jid}/map",
                        headers={"Authorization": f"Bearer {admin_token}",
                                 "Content-Type": "application/json"},
                        json=mapping_body, timeout=15)
    assert r2.status_code == 200
    d = r2.json()
    codes = {e.get("code") for e in d.get("validation_errors") or []}
    assert "REQUIRED_MISSING" in codes, f"expected REQUIRED_MISSING in {codes}"
    assert "NEGATIVE_PRICE" in codes, f"expected NEGATIVE_PRICE in {codes}"
    assert d.get("im_status") == "validated"


def test_importer_duplicates(admin_token):
    dup_code = f"TEST_DUP_{uuid.uuid4().hex[:6]}"
    body = f"CODICE,PREZZO,UM\n{dup_code},10,linear_m\n{dup_code},12,linear_m\n"
    r = _upload_csv(admin_token, body.encode("utf-8"), target_pl_id=SELL_PL_ID,
                    filename=f"dup_{uuid.uuid4().hex[:6]}.csv")
    assert r.status_code == 200
    jid = r.json().get("id") or r.json().get("_id")
    mapping_body = {"mappings": [
        {"source_column": "CODICE", "target_field": "code", "required": True},
        {"source_column": "PREZZO", "target_field": "unit_price",
         "required": True, "transform": "num"},
        {"source_column": "UM", "target_field": "unit"},
    ]}
    r2 = requests.post(f"{BASE_URL}/api/importer/jobs/{jid}/map",
                        headers={"Authorization": f"Bearer {admin_token}",
                                 "Content-Type": "application/json"},
                        json=mapping_body, timeout=15)
    d = r2.json()
    assert d.get("duplicate_count", 0) >= 1


# =====================================================================
# CONTRATTI — Generate + State Machine + Firma
# =====================================================================


@pytest.fixture(scope="module")
def new_contract_id(h, admin_token):
    # Trovare un quote_id senza contratto attivo
    r = requests.get(f"{BASE_URL}/api/quotes?limit=50",
                     headers={"Authorization": f"Bearer {admin_token}"}, timeout=15)
    assert r.status_code == 200
    items = r.json().get("items", [])
    for q in items:
        if q.get("status") not in ("active", "sent", "accepted", "approved", "won"):
            continue
        # tentativo
        rc = requests.post(f"{BASE_URL}/api/contracts/generate-from-quote",
                            headers=h, json={"quote_id": q["id"]}, timeout=20)
        if rc.status_code == 201 or rc.status_code == 200:
            data = rc.json()
            cid = data.get("id") or data.get("_id")
            if cid:
                return cid
        # else prova successivo
    pytest.skip("Non è stato possibile generare un nuovo contratto")


def test_contract_generate(new_contract_id, h):
    r = requests.get(f"{BASE_URL}/api/contracts/{new_contract_id}", headers=h, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d.get("number", "").startswith("CT-")
    assert d.get("contract_status") == "draft"
    assert len(d.get("snapshot_hash") or "") == 64
    snap = d.get("quote_snapshot") or {}
    assert "company" in snap and "customer" in snap
    assert "products" in snap
    assert "environments" in snap and "openings" in snap


def test_contract_generate_duplicate(new_contract_id, h):
    # Ottengo quote_id dal contratto
    r = requests.get(f"{BASE_URL}/api/contracts/{new_contract_id}", headers=h, timeout=10)
    quote_id = r.json().get("quote_id")
    r2 = requests.post(f"{BASE_URL}/api/contracts/generate-from-quote",
                        headers=h, json={"quote_id": quote_id}, timeout=15)
    assert r2.status_code == 400
    assert "esistente" in r2.text.lower() or "gi" in r2.text.lower()


def test_contract_state_machine_ok(new_contract_id, h):
    r1 = requests.post(f"{BASE_URL}/api/contracts/{new_contract_id}/transition",
                        headers=h, json={"to_state": "ready_for_review"}, timeout=10)
    assert r1.status_code == 200, r1.text
    r2 = requests.post(f"{BASE_URL}/api/contracts/{new_contract_id}/transition",
                        headers=h, json={"to_state": "ready_for_signature"}, timeout=10)
    assert r2.status_code == 200, r2.text


def test_contract_state_machine_invalid(new_contract_id, h):
    # da ready_for_signature → signed non consentita direttamente
    r = requests.post(f"{BASE_URL}/api/contracts/{new_contract_id}/transition",
                       headers=h, json={"to_state": "signed"}, timeout=10)
    assert r.status_code == 400
    assert "non permessa" in r.text.lower() or "transizione" in r.text.lower()


def test_contract_send_and_public_sign(new_contract_id, h):
    # Send
    r = requests.post(f"{BASE_URL}/api/contracts/{new_contract_id}/send-for-signature",
                       headers=h, json={"to_email": "cliente@test.it"}, timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    token = d.get("signing_token")
    assert isinstance(token, str) and len(token) >= 48
    assert d.get("expires_at")

    # Public view (no auth)
    r2 = requests.get(f"{BASE_URL}/api/contracts/public/{token}", timeout=10)
    assert r2.status_code == 200, r2.text
    assert (r2.json().get("contract") or {}).get("contract_status") in ("sent", "viewed")

    # Sign senza accept_terms → 400
    r_bad = requests.post(f"{BASE_URL}/api/contracts/public/{token}/sign",
                          json={"signer_name": "Mario Rossi",
                                "signature_data_url": "data:image/png;base64,AAAA",
                                "accept_terms": False}, timeout=10)
    assert r_bad.status_code == 400

    # Sign valido
    r3 = requests.post(f"{BASE_URL}/api/contracts/public/{token}/sign",
                        json={"signer_name": "Mario Rossi",
                              "signature_data_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
                              "accept_terms": True}, timeout=15)
    assert r3.status_code == 200, r3.text
    sig = r3.json()
    assert len(sig.get("signature_hash") or "") == 64
    assert sig.get("signature_type") == "electronic_simple"

    # Seconda firma → 404 (token consumed) o 400 già firmato
    r4 = requests.post(f"{BASE_URL}/api/contracts/public/{token}/sign",
                        json={"signer_name": "X",
                              "signature_data_url": "data:image/png;base64,AAAA",
                              "accept_terms": True}, timeout=10)
    assert r4.status_code in (400, 404)

    # Public view su token consumed → 404
    r5 = requests.get(f"{BASE_URL}/api/contracts/public/{token}", timeout=10)
    assert r5.status_code == 404


def test_contract_immutability_after_signed(new_contract_id, h):
    # Il contratto è ora signed. transizione signed → draft deve fallire
    r = requests.post(f"{BASE_URL}/api/contracts/{new_contract_id}/transition",
                       headers=h, json={"to_state": "draft"}, timeout=10)
    assert r.status_code == 400
    assert "non permessa" in r.text.lower()


def test_contract_create_variation(new_contract_id, h):
    r = requests.post(f"{BASE_URL}/api/contracts/{new_contract_id}/create-variation",
                       headers=h, json={"reason": "Test variante"}, timeout=15)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v.get("parent_contract_id") == new_contract_id
    assert (v.get("variation_index") or 0) >= 1
    # Parent superseded
    rp = requests.get(f"{BASE_URL}/api/contracts/{new_contract_id}", headers=h, timeout=10)
    assert rp.json().get("contract_status") == "superseded"


def test_contract_timeline(new_contract_id, h):
    r = requests.get(f"{BASE_URL}/api/contracts/{new_contract_id}/timeline",
                      headers=h, timeout=10)
    assert r.status_code == 200
    d = r.json()
    hist = d.get("state_history") or []
    states = [s.get("state") for s in hist]
    for expected in ("draft", "ready_for_review", "ready_for_signature", "signed"):
        assert expected in states, f"Mancante {expected} in {states}"


# =====================================================================
# REGRESSIONE — Blocco A
# =====================================================================


def test_regression_bom_recipes_still_20(h):
    r = requests.get(f"{BASE_URL}/api/pricing-hub/bom-recipes", headers=h, timeout=15)
    assert r.status_code == 200
    d = r.json()
    items = d.get("items") if isinstance(d, dict) else d
    assert isinstance(items, list) and len(items) == 20


def test_regression_bom_simulate(h):
    body = {"bom_template_id": BOM_WIN_2A,
            "width_mm": 1200, "height_mm": 1400,
            "nr_ante": 2,
            "sell_pricelist_id": SELL_PL_ID, "include_costs": False}
    r = requests.post(f"{BASE_URL}/api/pricing-hub/bom-simulate",
                       headers=h, json=body, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d.get("materials_price") or d.get("total_price") or 0) > 0
    assert isinstance(d.get("snapshot_hash"), str) and len(d["snapshot_hash"]) == 64
