"""QUOTE PDF PREMIUM V2 (PO msg 626) — design, general terms versioning/freeze, no internal leak, real render."""
from __future__ import annotations

import asyncio
import os

import fitz
import pytest
import requests

from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD
from app.services.general_terms import (
    GENERAL_TERMS_VERSION, SUMMARY_V1, build_general_terms, resolve_general_terms_for_quote,
)
from app.services.general_terms_canonical import get_canonical

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
WINDOW_PID = "8e1cafd0-9707-47c7-8939-b97c9a404021"
CASS_PID = "dc5ac292-692f-4aa9-8065-83bd7664928c"
INTERNAL_MARKERS = ["margin", "Margine", "supply_cost", "commission", "Commissione", "internal_cost", "Costo produzione",
                    "financial_snapshot", "BIANCO_MASSA", "NON_STANDARD", "Emergent", "tachometer"]


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def tok():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    r.raise_for_status()
    d = r.json()
    return d.get("access_token") or d.get("token")


def _line(cfg, pid, model, cat, key, opening_id, qty=1, desc="test"):
    return {"opening_id": opening_id, "category": cat.lower(), "product_key": key, "quantity": qty, "width_mm": cfg["width_mm"], "height_mm": cfg["height_mm"],
            "base_price": 1, "unit_price_final": 1, "subtotal_line": 1, "description": desc, "source": "MULTI_CATEGORY_V1",
            "category_code": cat, "product_id": pid, "product_code": key, "pricing_model": model, "configuration_snapshot": cfg}


@pytest.fixture(scope="module")
def scenario(tok):
    """Finestra bicolore + vetro satinato, cassonetto, posa, smontaggio, ENEA, sconto globale 10%, payment terms 50/50."""
    h = {"Authorization": f"Bearer {tok}"}
    cust = requests.get(f"{BASE_URL}/api/customers?limit=1", headers=h).json()
    cid = (cust.get("items") or cust)[0]["id"]
    site = requests.post(f"{BASE_URL}/api/sites", json={"name": "Cantiere PDF V2", "address": "Via Roma", "street_number": "10", "postal_code": "20100", "city": "Milano",
                                                          "province": "MI", "floor": "2", "has_elevator": True, "site_contact_phone": "3331234567", "customer_id": cid}, headers=h).json()
    q = requests.post(f"{BASE_URL}/api/quotes", json={"title": "PDF V2 scenario", "customer_id": cid, "site_id": site["id"]}, headers=h).json()
    qid = q["id"]
    op = requests.post(f"{BASE_URL}/api/quotes/{qid}/openings", json={"code": "V1", "room": "Soggiorno", "description": "Finestra soggiorno", "width_mm": 1250, "height_mm": 1450}, headers=h).json()
    wcfg = {"window_type": "WINDOW", "number_of_sashes": 2, "width_mm": 1200, "height_mm": 1400, "color_mode": "BICOLOR", "color_internal": "003", "color_internal_name": "BIANCO MASSA", "color_external": "154", "color_external_name": "NOCE",
            "glass_type": "DOUBLE_SATIN", "opening_configuration": "ANTA_RIBALTA", "quantity": 2}
    r = requests.post(f"{BASE_URL}/api/quotes/{qid}/lines", json=_line(wcfg, WINDOW_PID, "FORMULA_TECHNICAL", "FINESTRE", "PROEVOLUTION", op["id"], 2, "ProEvolution 2 ante"), headers=h)
    assert r.status_code == 200, r.text
    ccfg = {"width_mm": 1300, "height_mm": 250, "depth_mm": 163, "ceiling_liner": "SI", "color_code": "154", "quantity": 1}
    r = requests.post(f"{BASE_URL}/api/quotes/{qid}/lines", json=_line(ccfg, CASS_PID, "GRID", "CASSONETTI", "CASSONETTO_STD", op["id"], 1, "Cassonetto"), headers=h)
    assert r.status_code == 200, r.text
    r = requests.patch(f"{BASE_URL}/api/quotes/{qid}", json={"installation_mode": "SUPPLY_AND_INSTALLATION", "dismantling_mode": "INCLUDED", "disposal_mode": "EXCLUDED",
                                                              "payment_terms": "DEPOSIT_50_BALANCE_50", "global_discount_percent": 10,
                                                              "tax_deduction_requested": True, "enea_practice_code": "ENEA_STANDARD"}, headers=h)
    assert r.status_code == 200, r.text
    quote = requests.get(f"{BASE_URL}/api/quotes/{qid}", headers=h).json()
    r = requests.post(f"{BASE_URL}/api/quotes/{qid}/pdf/preview", json={}, headers=h)
    assert r.status_code == 200, r.text
    pdf = requests.get(f"{BASE_URL}/api/quote-pdfs/{r.json()['id']}/download", headers=h).content
    yield {"qid": qid, "quote": quote, "pdf": pdf, "h": h}
    requests.delete(f"{BASE_URL}/api/quotes/{qid}", headers=h)


def test_pdf_render_fonts_pages(scenario):
    doc = fitz.open(stream=scenario["pdf"], filetype="pdf")
    assert len(doc) >= 4
    fonts = {f[3] for p in doc for f in p.get_fonts()}
    assert any("Roboto" in f for f in fonts), fonts
    assert any("Roboto-Bold" in f for f in fonts)
    # A4 portrait
    w, h = doc[0].rect.width, doc[0].rect.height
    assert 590 < w < 600 and 835 < h < 845


def _txt(pdf):
    import re
    raw = "".join(p.get_text() for p in fitz.open(stream=pdf, filetype="pdf"))
    # rimuove lo spacing tra lettere (letter-spacing delle label uppercase) e normalizza gli spazi
    return raw.replace("\n", " ")


def test_pdf_content_and_totals(scenario):
    q = scenario["quote"]
    txt = _txt(scenario["pdf"])
    for s in ["PREVENTIVO", q["number"], "CLIENTE", "CANTIERE", "Via Roma, 10", "20100 Milano (MI)", "TERMINI DI PAGAMENTO",
              "50%", "acconto all'ordine", "avviso merce pronta", "V1", "1200 × 1400 mm", "2 ante", "anta-ribalta", "doppio satinato",
              "003", "BIANCO MASSA", "154", "NOCE", "Cassonetto", "163 mm", "SERVIZI PREVISTI", "Posa in opera", "Smontaggio", "Pratica ENEA Standard",
              "TEMPI INDICATIVI", "giorni", "RIEPILOGO ECONOMICO", "Sconto 10%", "Imponibile", "IVA 22%", "TOTALE", "Schemi prodotti",
              "CONDIZIONI CONTRATTUALI — IN SINTESI", GENERAL_TERMS_VERSION, "non modifica, sostituisce né integra le Condizioni Generali",
              "PER ACCETTAZIONE", "Luogo e data", "Firma Cliente", "timbro e firma", "Infissi Express Enerhia Srl"]:
        assert s.replace(" ", "") in txt.replace(" ", ""), f"missing: {s}"
    compact = txt.replace(" ", "")
    assert "Smaltimento" not in compact.split("SERVIZIPREVISTI")[1].split("TEMPIINDICATIVI")[0]  # escluso -> non dichiarato
    def cur(v): return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    for v in (q["commercial_subtotal"], q["global_discount_amount"], q["subtotal"], q["vat_amount"], q["total"]):
        assert cur(v) in compact, (v, cur(v))


def test_pdf_no_internal_leak(scenario):
    txt = _txt(scenario["pdf"])
    for m in INTERNAL_MARKERS:
        assert m not in txt, m


def test_general_terms_summary_derived_from_canonical():
    """msg 782 §7/§20: summary collegato alla GENERAL_TERMS_VERSION, ogni punto con fonte contrattuale, nessuna clausola autonoma."""
    async def run():
        db = _db()
        tenant = (await db.quotes.find_one({}))["tenant_id"]
        return await build_general_terms(db, tenant)
    gt = asyncio.run(run())
    canon = get_canonical()
    assert gt["version"] == GENERAL_TERMS_VERSION == canon["version"] and len(gt["sections"]) == len(SUMMARY_V1) == 14
    assert gt["general_terms_hash"] == canon["general_terms_hash"] and gt["missing_sources"] == [] and gt["legal_sections"] == []
    numbers = {a["number"] for a in canon["articles"]}
    for s in gt["sections"]:
        assert s["source_articles"] and set(s["source_articles"]) <= numbers, s["key"]
    assert "non modifica, sostituisce né integra" in gt["info_notice"]


def test_general_terms_versioned_and_frozen_on_accepted(scenario):
    q = scenario["quote"]
    async def run():
        db = _db()
        fresh = await db.quotes.find_one({"_id": q["id"]})
        assert fresh["general_terms_version"] == GENERAL_TERMS_VERSION and fresh["general_terms_snapshot_id"]
        snap_id = fresh["general_terms_snapshot_id"]
        assert await db.general_terms_snapshots.find_one({"_id": snap_id})
        # ACCEPTED: congelato sullo snapshot originale anche se il documento in DB viene alterato
        await db.general_terms_snapshots.update_one({"_id": snap_id}, {"$set": {"frozen_marker": "V1-FROZEN"}})
        try:
            await db.quotes.update_one({"_id": q["id"]}, {"$set": {"quote_status": "accepted"}})
            acc = await db.quotes.find_one({"_id": q["id"]})
            frozen = await resolve_general_terms_for_quote(db, {**acc, "id": acc["_id"]})
            assert frozen["id"] == snap_id and frozen["frozen"] is True and frozen["frozen_marker"] == "V1-FROZEN"
            assert frozen["version"] == GENERAL_TERMS_VERSION
        finally:
            await db.general_terms_snapshots.update_one({"_id": snap_id}, {"$unset": {"frozen_marker": ""}})
            await db.quotes.update_one({"_id": q["id"]}, {"$set": {"quote_status": "draft"}})
    asyncio.run(run())
