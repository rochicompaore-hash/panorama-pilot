"""CONTRACT SOURCE OF TRUTH (PO msg 782) — GENERAL_TERMS canonico, summary derivato, invarianza contratto,
parità economica preventivo→contratto, freeze su ACCEPTED, sezione approvazione clausole onerose."""
from __future__ import annotations

import asyncio
import os

import fitz
import pytest
import requests

from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD
from app.services.general_terms import SUMMARY_V1, GENERAL_TERMS_SUMMARY_VERSION, build_summary
from app.services.general_terms_canonical import (
    ARTICLES, CLAUSE_APPROVAL, GENERAL_TERMS_VERSION, canonical_hash, canonical_terms_text, get_canonical,
)

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
WINDOW_PID = "8e1cafd0-9707-47c7-8939-b97c9a404021"

PO_ARTICLE_ORDER = ["1", "2", "2-bis", "3", "3-bis", "3-ter", "3-quater", "4", "4-bis", "5", "5-bis", "6", "7", "8", "9", "10",
                    "11", "11-bis", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23", "24"]


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def h():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    r.raise_for_status()
    d = r.json()
    return {"Authorization": f"Bearer {d.get('access_token') or d.get('token')}"}


@pytest.fixture(scope="module")
def flow(h):
    """GT V1 -> CREATE QUOTE -> ACCEPT -> GENERATE CONTRACT."""
    cust = requests.get(f"{BASE_URL}/api/customers?limit=1", headers=h).json()
    cid = (cust.get("items") or cust)[0]["id"]
    q = requests.post(f"{BASE_URL}/api/quotes", json={"title": "Contract SoT", "customer_id": cid}, headers=h).json()
    qid = q["id"]
    op = requests.post(f"{BASE_URL}/api/quotes/{qid}/openings", json={"code": "V1", "room": "Cucina", "width_mm": 1200, "height_mm": 1400}, headers=h).json()
    cfg = {"window_type": "WINDOW", "number_of_sashes": 2, "width_mm": 1200, "height_mm": 1400, "color_mode": "BICOLOR", "color_internal": "003", "color_internal_name": "BIANCO MASSA", "color_external": "154", "color_external_name": "NOCE",
           "glass_type": "DOUBLE_SATIN", "opening_configuration": "ANTA_RIBALTA", "quantity": 1}
    line = {"opening_id": op["id"], "category": "finestre", "product_key": "PROEVOLUTION", "quantity": 1, "width_mm": 1200, "height_mm": 1400,
            "base_price": 1, "unit_price_final": 1, "subtotal_line": 1, "description": "ProEvolution 2 ante", "source": "MULTI_CATEGORY_V1",
            "category_code": "FINESTRE", "product_id": WINDOW_PID, "product_code": "PROEVOLUTION", "pricing_model": "FORMULA_TECHNICAL", "configuration_snapshot": cfg}
    assert requests.post(f"{BASE_URL}/api/quotes/{qid}/lines", json=line, headers=h).status_code == 200
    assert requests.patch(f"{BASE_URL}/api/quotes/{qid}", json={"payment_terms": "DEPOSIT_50_BALANCE_50", "global_discount_percent": 5}, headers=h).status_code == 200
    r = requests.post(f"{BASE_URL}/api/quotes/{qid}/pdf/preview", json={}, headers=h)
    assert r.status_code == 200, r.text
    quote_pdf = requests.get(f"{BASE_URL}/api/quote-pdfs/{r.json()['id']}/download", headers=h).content
    for st in ("sent", "accepted"):
        r = requests.post(f"{BASE_URL}/api/quotes/{qid}/status", json={"new_status": st}, headers=h)
        assert r.status_code == 200, r.text
    accepted = requests.get(f"{BASE_URL}/api/quotes/{qid}", headers=h).json()
    r = requests.post(f"{BASE_URL}/api/contracts/generate-from-quote", json={"quote_id": qid}, headers=h)
    assert r.status_code == 200, r.text
    contract = r.json()
    pdf = requests.get(f"{BASE_URL}/api/contracts/{contract['id']}/pdf/preview", headers=h)
    assert pdf.status_code == 200, pdf.text
    yield {"qid": qid, "quote": accepted, "contract": contract, "pdf": pdf.content, "quote_pdf": quote_pdf}
    asyncio.run(_cleanup(qid, contract["id"]))


async def _cleanup(qid, cid):
    db = _db()
    await db.contracts.delete_one({"_id": cid})
    await db.quotes.delete_one({"_id": qid})


def _txt(pdf):
    return "".join(p.get_text() for p in fitz.open(stream=pdf, filetype="pdf")).replace("\n", " ")


# ---------------- CONTRACT_SOURCE_IMPORTED ----------------
def test_canonical_structure_matches_official_document():
    canon = get_canonical()
    assert canon["version"] == GENERAL_TERMS_VERSION and canon["articles_count"] == 31
    assert [a["number"] for a in canon["articles"]] == PO_ARTICLE_ORDER  # NON rinumerare
    assert canon["general_terms_hash"] == canonical_hash(canon["full_text"]) and len(canon["general_terms_hash"]) == 64
    assert canon["effective_from"] and canon["source_document"]
    for a in ARTICLES:
        assert a["title"].strip() and len(a["text"]) > 40
    titles = {a["number"]: a["title"] for a in ARTICLES}
    assert titles["16"] == "ESCLUSIONE DEL DIRITTO DI RECESSO" and titles["21"] == "CONTROVERSIE – FORO COMPETENTE"
    assert "Foro di Lecco" in next(a["text"] for a in ARTICLES if a["number"] == "21")


def test_clause_approval_section_preserved():
    assert "1341 e 1342" in CLAUSE_APPROVAL["text"] and "1341 e 1342" in CLAUSE_APPROVAL["second_approval_text"]
    numbers = {a["number"] for a in ARTICLES}
    assert set(CLAUSE_APPROVAL["article_numbers"]) <= numbers and len(CLAUSE_APPROVAL["article_numbers"]) == 23
    canon = get_canonical()
    assert len(canon["signature_points"]) == 6 and any(s["label"] == "Sigla" for s in canon["signature_points"])


def test_unknown_version_fail_closed(h):
    with pytest.raises(KeyError):
        get_canonical("GT-DOES-NOT-EXIST")
    assert requests.get(f"{BASE_URL}/api/general-terms/GT-DOES-NOT-EXIST", headers=h).status_code == 404
    r = requests.get(f"{BASE_URL}/api/general-terms/current", headers=h)
    assert r.status_code == 200 and r.json()["canonical"]["general_terms_hash"] == r.json()["summary"]["general_terms_hash"]


# ---------------- QUOTE_SUMMARY_FROM_CONTRACT / SUMMARY CONSISTENCY ----------------
def test_summary_consistency_every_point_has_contract_source():
    s = build_summary()
    numbers = {a["number"] for a in ARTICLES}
    assert s["summary_version"] == GENERAL_TERMS_SUMMARY_VERSION and s["version"] == GENERAL_TERMS_VERSION
    assert len(s["sections"]) == len(SUMMARY_V1) == 14 and s["missing_sources"] == []
    for sec in s["sections"]:
        assert sec["source_articles"] and set(sec["source_articles"]) <= numbers and sec["source_titles"], sec["key"]
    assert "prevale esclusivamente il testo integrale" in s["info_notice"]


def test_quote_pdf_shows_summary_not_contract(flow):
    txt = _txt(flow["quote_pdf"]).replace(" ", "")
    assert "CONDIZIONICONTRATTUALI—INSINTESI" in txt and GENERAL_TERMS_VERSION in txt
    assert "nonmodifica,sostituiscenéintegra" in txt
    assert "APPROVAZIONESPECIFICADICLAUSOLEONEROSE" not in txt  # il preventivo riassume, non crea il contratto
    assert "Articolo3-quater" not in txt


# ---------------- CONTRACT_EXACT_TERMS (INVARIANCE) ----------------
def test_contract_invariance_identical_text(flow, h):
    c = flow["contract"]
    gt = c["quote_snapshot"]["general_terms"]
    canon = get_canonical(GENERAL_TERMS_VERSION)
    extracted = canonical_terms_text(gt["articles"], gt["clause_approval"])
    assert extracted == canon["full_text"]  # IDENTICO, non semanticamente simile
    assert c["general_terms_version"] == GENERAL_TERMS_VERSION and c["general_terms_hash"] == canon["general_terms_hash"]
    v = requests.get(f"{BASE_URL}/api/contracts/{c['id']}/terms-verify", headers=h).json()
    assert v["identical"] is True and v["status"] == "IDENTICAL" and v["articles_count"] == 31


def test_contract_pdf_contains_full_terms_and_signatures(flow):
    txt = _txt(flow["pdf"]).replace(" ", "")
    for a in ARTICLES:
        assert f"Articolo{a['number']}–{a['title']}".replace(" ", "") in txt, a["number"]
    for needle in ["APPROVAZIONESPECIFICADICLAUSOLEONEROSE", "1341e1342", "Firmaperesteso", "Sigla", "ForodiLecco", GENERAL_TERMS_VERSION,
                   "CONSENSOALTRATTAMENTODEIDATIPERSONALI", "MODULODIPROPOSTAD'ACQUISTO", "TOTALEOFFERTA", "BONIFICOPARLANTEPERDETRAZIONEFISCALE"]:
        assert needle in txt, needle
    assert txt.count("Firmaperesteso") >= 5


# ---------------- QUOTE_CONTRACT_ECONOMIC_PARITY ----------------
def test_economic_parity_quote_vs_contract(flow):
    q, c = flow["quote"], flow["contract"]
    eco = c["quote_snapshot"]["economics"]
    assert eco["total"] == q["total"] and eco["subtotal"] == q["subtotal"] and eco["vat_amount"] == q["vat_amount"]
    assert eco["global_discount_amount"] == q["global_discount_amount"]
    assert eco["payment_terms"]["code"] == (q.get("payment_terms_code") or q.get("payment_terms"))
    assert eco["payment_terms"]["schedule"] == (q.get("payment_schedule") or [])
    assert len(eco["lines"]) == len(q["lines"]) and eco["lines"][0]["configuration_snapshot"]["color_internal"] == "003"
    assert eco["vat_regime"]["code"] == "22" and eco["vat_breakdown"]
    assert c["quote_snapshot"]["quote_totals"]["total"] == q["total"]
    for k in ("internal_cost", "margin", "financial_snapshot", "pricing_snapshot"):
        assert k not in eco["lines"][0]
    txt = _txt(flow["pdf"]).replace(" ", "")
    assert f"{q['total']:.2f}€" in txt


# ---------------- ACCEPTED_FREEZE ----------------
def test_accepted_freeze_and_versioning_fields(flow):
    q, c = flow["quote"], flow["contract"]
    assert q["quote_status"] == "accepted" and q["general_terms_version"] == GENERAL_TERMS_VERSION and q["general_terms_snapshot_id"]
    assert c["general_terms_snapshot_id"] == q["general_terms_snapshot_id"]
    for k in ("general_terms_version", "general_terms_hash", "general_terms_snapshot_id", "quote_revision_id", "quote_snapshot_id", "accepted_at"):
        assert c.get(k), k
    assert c["quote_revision_id"].endswith("#R00") and c["accepted_at"] == q["accepted_at"]

    async def run():
        db = _db()
        # Il riferimento GT del preventivo accettato non cambia anche se il DB snapshot viene toccato
        await db.quotes.update_one({"_id": q["id"]}, {"$set": {"quote_status": "accepted"}})
        from app.services.general_terms import resolve_general_terms_for_quote
        fresh = await db.quotes.find_one({"_id": q["id"]})
        frozen = await resolve_general_terms_for_quote(db, {**fresh, "id": fresh["_id"]})
        assert frozen["frozen"] is True and frozen["id"] == q["general_terms_snapshot_id"]
    asyncio.run(run())
