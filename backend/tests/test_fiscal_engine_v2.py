"""FISCAL ENGINE V2 — matrice test §30 (questionario dinamico, beni significativi, mista automatica, restauro, sola fornitura, IVA 4, no 104 auto, dichiarazione, pending→22, audit, rule versioning)."""
from __future__ import annotations

import pytest

from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD
from tests.test_fase_a_preventivatore import BASE_URL, _login, _mk_quote, WINDOW
from app.services import fiscal_engine as fe

RULE = fe.DEFAULT_RULE_VERSION
LINES = [{"category": "window", "subtotal_line": 7000}, {"category": "installation", "subtotal_line": 2000}, {"category": "shutter", "subtotal_line": 1000}]
BASE_ANS = {"customer_tax_profile": "PRIVATE", "residential_use": "YES", "building_permit": "CILA"}


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


def test_A_22_no_questionnaire():
    ev = fe.evaluate("VAT_ORDINARY", {}, LINES, 10000, {}, RULE)
    assert ev["outcome"] == "STANDARD_22" and ev["pending_questions"] == []


def test_B_dynamic_questions():
    assert fe.next_questions("VAT_ELIGIBLE_10", {}) == ["customer_tax_profile", "residential_use", "intervention_type", "building_permit"]
    assert "supply_and_install" in fe.next_questions("VAT_ELIGIBLE_10", {"intervention_type": "ORDINARY_MAINTENANCE"})
    assert "formally_classified" in fe.next_questions("VAT_ELIGIBLE_10", {"intervention_type": "BUILDING_RENOVATION"})
    assert "vat4_reason" in fe.next_questions("VAT_ELIGIBLE_4", {}) and "barrier_contract_object" not in fe.next_questions("VAT_ELIGIBLE_4", {})
    assert "barrier_technical_doc" in fe.next_questions("VAT_ELIGIBLE_4", {"vat4_reason": "ARCHITECTURAL_BARRIERS", "barrier_contract_object": "YES"})


def test_CD_significant_goods_mixed_auto():
    sg = fe.significant_goods_split(LINES, 10000, RULE)
    # bene significativo 7000 (infisso) · altro 3000 (posa + tapparella AUTONOMA) → 10% su 3000+3000, 22% su 1000
    assert sg["value_of_significant_good"] == 7000 and sg["other_service_and_goods_value"] == 3000 and sg["taxable_10"] == 6000 and sg["taxable_22"] == 4000
    assert fe.line_relation({"category": "shutter"}, RULE) == "AUTONOMOUS" and fe.line_relation({"category": "box"}, RULE) == "INTEGRATED" and fe.line_relation({"category": "xyz"}, RULE) == "NEEDS_REVIEW"
    ans = {**BASE_ANS, "intervention_type": "EXTRAORDINARY_MAINTENANCE", "supply_and_install": "YES"}
    ev = fe.evaluate("VAT_ELIGIBLE_10", ans, LINES, 10000, {}, RULE)
    assert ev["eligible_outcome"] == "ELIGIBLE_MIXED_10_22" and ev["regime"] == "VAT_MIXED_10_22" and ev["outcome"] == "NEEDS_DOCUMENTATION"  # J: docs mancanti → pending
    assert "dichiarazione cliente" in ev["missing_requirements"] and ev["mixed_split"]["taxable_22"] == 4000
    # K: dossier completo (dichiarazione firmata + documenti) → esito eleggibile
    dossier = {"declaration": {"status": "SIGNED"}, "documents": [{"doc_type": d} for d in ("IDENTITY_DOCUMENT", "CADASTRAL_DATA", "CILA")]}
    ev = fe.evaluate("VAT_ELIGIBLE_10", ans, LINES, 10000, dossier, RULE)
    assert ev["outcome"] == "ELIGIBLE_MIXED_10_22" and ev["missing_requirements"] == []
    # fornitura+posa NO → nessun 10% automatico
    ev = fe.evaluate("VAT_ELIGIBLE_10", {**ans, "supply_and_install": "NO"}, LINES, 10000, dossier, RULE)
    assert ev["outcome"] == "NEEDS_FISCAL_REVIEW"
    # immobile non abitativo → NOT_ELIGIBLE
    assert fe.evaluate("VAT_ELIGIBLE_10", {**ans, "residential_use": "NO"}, LINES, 10000, dossier, RULE)["outcome"] == "NOT_ELIGIBLE"
    assert fe.evaluate("VAT_ELIGIBLE_10", {**ans, "residential_use": "UNKNOWN"}, LINES, 10000, dossier, RULE)["outcome"] == "NEEDS_FISCAL_REVIEW"


def test_E_restoration_full_10_no_significant_goods():
    dossier = {"declaration": {"status": "SIGNED"}, "documents": [{"doc_type": d} for d in ("IDENTITY_DOCUMENT", "CADASTRAL_DATA", "CILA", "BUILDING_DOCUMENTATION")]}
    ev = fe.evaluate("VAT_ELIGIBLE_10", {**BASE_ANS, "intervention_type": "BUILDING_RENOVATION", "formally_classified": "YES"}, LINES, 10000, dossier, RULE)
    assert ev["outcome"] == "ELIGIBLE_10_FULL" and ev["mixed_split"] is None
    assert fe.evaluate("VAT_ELIGIBLE_10", {**BASE_ANS, "intervention_type": "BUILDING_RENOVATION", "formally_classified": "TO_VERIFY"}, LINES, 10000, dossier, RULE)["outcome"] == "NEEDS_FISCAL_REVIEW"


def test_F_supply_only_control():
    dossier = {"declaration": {"status": "SIGNED"}, "documents": [{"doc_type": d} for d in ("IDENTITY_DOCUMENT", "CADASTRAL_DATA", "CILA", "BUILDING_DOCUMENTATION")]}
    assert fe.evaluate("VAT_ELIGIBLE_10", {**BASE_ANS, "intervention_type": "SUPPLY_ONLY", "supply_for_qualified_work": "NO"}, LINES, 10000, dossier, RULE)["outcome"] == "NOT_ELIGIBLE"
    assert fe.evaluate("VAT_ELIGIBLE_10", {**BASE_ANS, "intervention_type": "SUPPLY_ONLY", "supply_for_qualified_work": "YES"}, LINES, 10000, dossier, RULE)["outcome"] == "ELIGIBLE_10_FULL"


def test_GHI_vat4_flows():
    ans = {**BASE_ANS, "intervention_type": "ARCHITECTURAL_BARRIERS"}
    assert fe.evaluate("VAT_ELIGIBLE_4", ans, LINES, 10000, {}, RULE)["pending_questions"] == ["vat4_reason"]
    # H: solo Legge 104 (barriere ma contratto non ha ad oggetto le opere) → NOT ELIGIBLE
    assert fe.evaluate("VAT_ELIGIBLE_4", {**ans, "vat4_reason": "ARCHITECTURAL_BARRIERS", "barrier_contract_object": "NO", "disability_104": "YES"}, LINES, 10000, {}, RULE)["outcome"] == "NOT_ELIGIBLE"
    # I: appalto specifico + dossier completo → ELIGIBLE_4 (validazione fiscale richiesta)
    full = {**ans, "vat4_reason": "ARCHITECTURAL_BARRIERS", "barrier_contract_object": "YES", "barrier_technical_doc": "YES", "disability_104": "YES"}
    ev = fe.evaluate("VAT_ELIGIBLE_4", full, LINES, 10000, {}, RULE)
    assert ev["eligible_outcome"] == "ELIGIBLE_4" and ev["outcome"] == "NEEDS_DOCUMENTATION" and "TECHNICAL_REPORT" in ev["required_documents"]
    dossier = {"declaration": {"status": "SIGNED"}, "documents": [{"doc_type": d} for d in ("IDENTITY_DOCUMENT", "CADASTRAL_DATA", "CILA", "TECHNICAL_REPORT", "BARRIER_DOCUMENTATION")]}
    assert fe.evaluate("VAT_ELIGIBLE_4", full, LINES, 10000, dossier, RULE)["outcome"] == "ELIGIBLE_4"
    # costruzione 4% → sempre revisione fiscale (no 'prima casa = 4%')
    assert fe.evaluate("VAT_ELIGIBLE_4", {**ans, "vat4_reason": "CONSTRUCTION_4", "construction_new": "YES", "construction_contract_kind": "SUPPLY", "construction_declaration": "NO"}, LINES, 10000, dossier, RULE)["outcome"] == "NEEDS_FISCAL_REVIEW"


def test_api_flow_pending_uses_22_then_validated_mixed(admin):
    qid = _mk_quote(admin, [{**WINDOW, "base_price": 7000.0}, {**WINDOW, "category": "installation", "description": "Posa", "base_price": 3000.0, "internal_cost": 1000.0, "technical_snapshot": {"total_internal_cost": 1000.0}}])
    q = admin.get(f"{BASE_URL}/api/quotes/{qid}", timeout=15).json()
    assert q["vat_regime"] == "VAT_ORDINARY" and admin.get(f"{BASE_URL}/api/quotes/{qid}/fiscal-questionnaire", timeout=15).json()["questionnaire_required"] is False
    r = admin.post(f"{BASE_URL}/api/quotes/{qid}/fiscal-questionnaire/answers", json={"requested_regime": "VAT_ELIGIBLE_10", "answers": {}}, timeout=15)
    assert r.status_code == 200
    qq = r.json()["questionnaire"]
    assert qq["questionnaire_required"] and qq["pending_questions"][0] == "customer_tax_profile" and r.json()["applied_vat"] == "VAT_ORDINARY"  # PENDING_USES_22
    ans = {"customer_tax_profile": "PRIVATE", "residential_use": "YES", "intervention_type": "EXTRAORDINARY_MAINTENANCE", "building_permit": "CILA", "supply_and_install": "YES", "cadastral_data": "Fg 12 part 345 sub 6"}
    r = admin.post(f"{BASE_URL}/api/quotes/{qid}/fiscal-questionnaire/answers", json={"answers": ans}, timeout=15).json()
    ev = r["fiscal_dossier"]["evaluation"]
    assert ev["outcome"] == "NEEDS_DOCUMENTATION" and ev["eligible_outcome"] == "ELIGIBLE_MIXED_10_22" and r["vat_regime"] == "VAT_DOCUMENTATION_INCOMPLETE" and r["applied_vat"] == "VAT_ORDINARY"
    assert "dichiarazione cliente" in ev["missing_requirements"]  # MISSING_REQUIREMENTS_VISIBLE
    assert admin.post(f"{BASE_URL}/api/quotes/{qid}/fiscal-dossier/declaration/sign", json={"signer_name": "Mario Rossi"}, timeout=15).status_code == 400
    r = admin.post(f"{BASE_URL}/api/quotes/{qid}/fiscal-dossier/declaration/generate", timeout=15).json()
    assert r["fiscal_dossier"]["declaration"]["status"] == "WAITING_CUSTOMER" and "responsabilità per la veridicità" in r["fiscal_dossier"]["declaration"]["text"] and "non ha più responsabilità" not in r["fiscal_dossier"]["declaration"]["text"]
    r = admin.post(f"{BASE_URL}/api/quotes/{qid}/fiscal-dossier/declaration/sign", json={"signer_name": "Mario Rossi", "channel": "IN_PRESENCE"}, timeout=15).json()
    assert r["fiscal_dossier"]["declaration"]["status"] == "SIGNED" and r["fiscal_dossier"]["customer_declaration"] is True
    # validazione negata finché mancano documenti
    assert admin.post(f"{BASE_URL}/api/quotes/{qid}/fiscal-dossier/validate", json={"decision": "VALIDATED"}, timeout=15).status_code == 400
    for d in ("IDENTITY_DOCUMENT", "CILA"):
        r = admin.post(f"{BASE_URL}/api/quotes/{qid}/fiscal-dossier/documents", json={"doc_type": d, "file_name": f"{d}.pdf"}, timeout=15).json()
    assert r["fiscal_dossier"]["evaluation"]["outcome"] == "ELIGIBLE_MIXED_10_22" and r["fiscal_dossier"]["documentation_status"] == "COMPLETE" and r["vat_regime"] == "VAT_REVIEW_REQUIRED"  # K re-evaluation; applicata ancora 22 finché non validata
    assert r["applied_vat"] == "VAT_ORDINARY"
    # contratto non silenzioso
    admin.post(f"{BASE_URL}/api/quotes/{qid}/status", json={"new_status": "sent"}, timeout=15)
    admin.post(f"{BASE_URL}/api/quotes/{qid}/status", json={"new_status": "accepted"}, timeout=15)
    rc = admin.post(f"{BASE_URL}/api/quotes/{qid}/convert-to-contract", timeout=30)
    assert rc.status_code == 409 and rc.json()["detail"]["code"] == "REDUCED_VAT_NOT_VALIDATED", rc.text
    r = admin.post(f"{BASE_URL}/api/quotes/{qid}/fiscal-dossier/validate", json={"decision": "VALIDATED", "reason": "dossier verificato"}, timeout=15)
    assert r.status_code == 200, r.text
    r = r.json()
    assert r["vat_regime"] == "VAT_MIXED_10_22" and r["applied_vat"] == "VAT_MIXED_10_22"  # richiesta 10% → esito MISTA dal motore
    rates = {b["rate_pct"]: b["taxable"] for b in r["vat_breakdown"]}
    assert set(rates) == {10, 22} and abs(rates[10] - 6000) < 1 and abs(rates[22] - 4000) < 1  # 7000 infisso, 3000 posa → 10% su 6000, 22% su 4000
    q = admin.get(f"{BASE_URL}/api/quotes/{qid}", timeout=15).json()
    assert abs(q["vat_amount"] - round(6000 * 0.10 + 4000 * 0.22, 2)) < 1 and q["fiscal_dossier"]["validated_by"] and q["fiscal_dossier"]["audit_trail"][-1]["action"] == "validation_validated"
    rule = admin.get(f"{BASE_URL}/api/quotes/vat-rules/active", timeout=15).json()
    assert rule["code"] == "VAT_RULES_IT_2026_01" and any("29/12/1999" in x["ref"] for x in rule["legal_references"])
