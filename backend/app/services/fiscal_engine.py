"""FISCAL ENGINE V2 — IVA agevolata: questionario guidato ADE-based, Significant Goods (DM 29/12/1999), esito determinato dal backend.
Regola assoluta: finché il dossier non è VALIDATED → APPLIED_VAT = 22% (fallback) · requested_vat tracciata · esito mai deciso dal commerciale."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

FISCAL_ENGINE_VERSION = "fiscal_engine_v2_2026_11"
OUTCOMES = ("STANDARD_22", "ELIGIBLE_10_FULL", "ELIGIBLE_MIXED_10_22", "ELIGIBLE_4", "NOT_ELIGIBLE", "NEEDS_DOCUMENTATION", "NEEDS_FISCAL_REVIEW")
OUTCOME_REGIME = {"ELIGIBLE_10_FULL": "VAT_ELIGIBLE_10", "ELIGIBLE_MIXED_10_22": "VAT_MIXED_10_22", "ELIGIBLE_4": "VAT_ELIGIBLE_4"}
DECLARATION_STATES = ("NOT_GENERATED", "WAITING_CUSTOMER", "SIGNED", "VALIDATED", "REJECTED")
DEFAULT_RULE_VERSION = {
    "_id": "VAT_RULES_IT_2026_01", "code": "VAT_RULES_IT_2026_01", "effective_from": "2026-01-01", "effective_to": None, "status": "ACTIVE",
    "legal_references": [
        {"ref": "DPR 633/1972 — Tabella A, parte II (n. 41-ter) e parte III (n. 127-quaterdecies, 127-terdecies)", "topic": "Aliquote 4% / 10% interventi edilizi"},
        {"ref": "Legge 488/1999 art. 7 c.1 lett. b) + DM 29/12/1999", "topic": "Beni significativi — manutenzione ordinaria/straordinaria su immobili a prevalente destinazione abitativa"},
        {"ref": "Agenzia delle Entrate — Guida 'Ristrutturazioni edilizie: le agevolazioni fiscali' (IVA agevolata)", "topic": "Prassi ADE"},
        {"ref": "Circolare AdE 15/E/2018", "topic": "Beni significativi: parti staccate e autonomia funzionale"},
        {"ref": "DPR 633/1972 Tab. A parte II n. 41-ter", "topic": "IVA 4% opere per il superamento/eliminazione barriere architettoniche"},
    ],
    "significant_goods": ["window", "door", "infisso", "serramento", "porta", "finestra", "portafinestra"],
    "note": "Le reference sono visibili ad Admin/Fiscal. Aggiornabili senza modificare il codice.",
}
# SIGNIFICANT_GOOD_RELATION per categoria riga (mai hardcodare tutto come parte dell'infisso)
RELATION_BY_CATEGORY = {"window": "SIGNIFICANT", "door": "SIGNIFICANT", "infisso": "SIGNIFICANT", "serramento": "SIGNIFICANT", "portafinestra": "SIGNIFICANT",
                        "box": "INTEGRATED", "cassonetto": "INTEGRATED", "sill": "INTEGRATED", "trim": "INTEGRATED",
                        "shutter": "AUTONOMOUS", "roller": "AUTONOMOUS", "persian": "AUTONOMOUS", "screen": "AUTONOMOUS", "zanzariera": "AUTONOMOUS", "tapparella": "AUTONOMOUS", "motor": "AUTONOMOUS", "accessory": "AUTONOMOUS",
                        "installation": "NOT_APPLICABLE", "disposal": "NOT_APPLICABLE", "extra": "NOT_APPLICABLE", "service": "NOT_APPLICABLE", "services": "NOT_APPLICABLE", "logistics": "NOT_APPLICABLE", "enea": "NOT_APPLICABLE", "dismantling": "NOT_APPLICABLE"}
MAINTENANCE = ("ORDINARY_MAINTENANCE", "EXTRAORDINARY_MAINTENANCE")
RESTORATION = ("RESTORATION_CONSERVATIVE", "BUILDING_RENOVATION")

QUESTIONS: Dict[str, Dict[str, Any]] = {
    "customer_tax_profile": {"text": "Chi è il committente?", "options": [("PRIVATE", "Privato"), ("CONDOMINIUM", "Condominio"), ("BUSINESS", "Impresa / Professionista"), ("PUBLIC_ENTITY", "Ente"), ("OTHER", "Altro")]},
    "residential_use": {"text": "L'immobile oggetto dell'intervento è a prevalente destinazione abitativa?", "options": [("YES", "Sì"), ("NO", "No"), ("UNKNOWN", "Non so")],
                        "extra_fields": ["property_address", "cadastral_data", "property_type", "condominium_name"]},
    "intervention_type": {"text": "Quale intervento viene eseguito?", "options": [("ORDINARY_MAINTENANCE", "A. Manutenzione ordinaria"), ("EXTRAORDINARY_MAINTENANCE", "B. Manutenzione straordinaria"), ("RESTORATION_CONSERVATIVE", "C. Restauro e risanamento conservativo"),
                                                                           ("BUILDING_RENOVATION", "D. Ristrutturazione edilizia"), ("NEW_CONSTRUCTION", "E. Nuova costruzione"), ("ARCHITECTURAL_BARRIERS", "F. Eliminazione / superamento barriere architettoniche"),
                                                                           ("SUPPLY_ONLY", "G. Sola fornitura di serramenti"), ("UNKNOWN", "H. Non so / da verificare")], "required": True},
    "building_permit": {"text": "L'intervento dispone di un titolo, comunicazione o documentazione edilizia?", "options": [("CILA", "CILA"), ("SCIA", "SCIA"), ("BUILDING_PERMIT", "Permesso di costruire"), ("OTHER", "Altro"), ("NONE_REQUIRED", "Nessun titolo necessario"), ("UNKNOWN", "Non so")],
                        "upload": True, "note": "CILA/SCIA/Permesso sono documentazione del dossier: NON determinano da soli l'aliquota."},
    "supply_and_install": {"text": "Infissi Express fornisce anche i serramenti nell'ambito dello stesso contratto di fornitura e posa?", "options": [("YES", "Sì"), ("NO", "No")]},
    "formally_classified": {"text": "L'intervento è formalmente classificato come tale nella documentazione disponibile?", "options": [("YES", "Sì"), ("NO", "No"), ("TO_VERIFY", "Da verificare")], "upload": True},
    "supply_for_qualified_work": {"text": "Gli infissi sono destinati ad un intervento di restauro, risanamento conservativo o ristrutturazione edilizia qualificato?", "options": [("YES", "Sì"), ("NO", "No"), ("UNKNOWN", "Non so")], "upload": True},
    "vat4_reason": {"text": "Qual è il presupposto per la richiesta IVA 4%?", "options": [("ARCHITECTURAL_BARRIERS", "A. Opere direttamente finalizzate all'eliminazione/superamento delle barriere architettoniche"), ("CONSTRUCTION_4", "B. Costruzione / intervento edilizio con specifica agevolazione IVA 4%"), ("OTHER", "C. Altro"), ("UNKNOWN", "D. Non so")]},
    "barrier_contract_object": {"text": "Il contratto ha direttamente ad oggetto la realizzazione di opere finalizzate al superamento o eliminazione delle barriere architettoniche?", "options": [("YES", "Sì"), ("NO", "No")]},
    "barrier_technical_doc": {"text": "È disponibile documentazione tecnica che descrive l'intervento?", "options": [("YES", "Sì — carica"), ("NO", "No")], "upload": True},
    "disability_104": {"text": "Nel dossier è presente una condizione di disabilità / Legge 104 (informazione di contesto: NON determina da sola l'IVA 4%)?", "options": [("YES", "Sì"), ("NO", "No")]},
    "construction_new": {"text": "Si tratta di nuova costruzione?", "options": [("YES", "Sì"), ("NO", "No")]},
    "construction_contract_kind": {"text": "L'agevolazione richiesta riguarda un contratto di appalto oppure una fornitura?", "options": [("CONTRACT_WORK", "Appalto"), ("SUPPLY", "Fornitura")]},
    "construction_declaration": {"text": "Esiste dichiarazione del committente sui requisiti dell'agevolazione?", "options": [("YES", "Sì"), ("NO", "No")], "upload": True},
}


def next_questions(requested: str, answers: Dict[str, Any]) -> List[str]:
    """Flusso dinamico: solo le domande necessarie in funzione delle risposte (mai 30 domande insieme)."""
    a = answers or {}
    seq = ["customer_tax_profile", "residential_use", "intervention_type", "building_permit"]
    it = a.get("intervention_type")
    if it in MAINTENANCE:
        seq.append("supply_and_install")
    elif it in RESTORATION:
        seq.append("formally_classified")
    elif it == "SUPPLY_ONLY":
        seq.append("supply_for_qualified_work")
    if requested == "VAT_ELIGIBLE_4":
        seq.append("vat4_reason")
        r = a.get("vat4_reason")
        if r == "ARCHITECTURAL_BARRIERS":
            seq += ["barrier_contract_object"]
            if a.get("barrier_contract_object") == "YES":
                seq += ["barrier_technical_doc", "disability_104"]
        elif r == "CONSTRUCTION_4":
            seq += ["construction_new", "construction_contract_kind", "construction_declaration"]
    return seq


def pending_questions(requested: str, answers: Dict[str, Any]) -> List[str]:
    return [q for q in next_questions(requested, answers) if (answers or {}).get(q) in (None, "")]


# ---------------- Significant Goods Engine (DM 29/12/1999) ----------------
def line_relation(line: Dict[str, Any], rule: Dict[str, Any]) -> str:
    cat = str(line.get("category") or line.get("category_code") or "").lower()
    if line.get("significant_good_relation") in ("SIGNIFICANT", "AUTONOMOUS", "INTEGRATED", "NOT_APPLICABLE", "NEEDS_REVIEW"):
        return line["significant_good_relation"]
    if cat in (rule.get("significant_goods") or []):
        return "SIGNIFICANT"
    return RELATION_BY_CATEGORY.get(cat, "NEEDS_REVIEW")


def significant_goods_split(lines: List[Dict[str, Any]], net_total: float, rule: Dict[str, Any]) -> Dict[str, Any]:
    """VALUE_OF_SIGNIFICANT_GOOD (infissi + componenti INTEGRATED) vs OTHER (posa, servizi, beni AUTONOMI). 10% su other + bene significativo fino a concorrenza
    della differenza (totale − bene significativo); eccedenza del bene significativo al 22%."""
    gross = sum(float(l.get("subtotal_line") or 0) for l in lines) or 0.0
    factor = (net_total / gross) if gross > 0 else 0.0
    sig, other, review = 0.0, 0.0, []
    for l in lines:
        v = float(l.get("subtotal_line") or 0) * factor
        rel = line_relation(l, rule)
        if rel in ("SIGNIFICANT", "INTEGRATED"):
            sig += v
        elif rel == "NEEDS_REVIEW":
            review.append(l.get("description") or l.get("category"))
            sig += v  # prudenziale: trattato come bene significativo finché non classificato
        else:
            other += v
    cap = max(0.0, net_total - sig)
    sig_10 = min(sig, cap)
    sig_22 = max(0.0, sig - sig_10)
    return {"method": "DM_29_12_1999", "value_of_significant_good": round(sig, 2), "other_service_and_goods_value": round(other, 2), "taxable_10": round(other + sig_10, 2), "taxable_22": round(sig_22, 2),
            "significant_good_at_10": round(sig_10, 2), "significant_good_at_22": round(sig_22, 2), "needs_review_lines": review, "rule_version": rule.get("code")}


# ---------------- evaluation ----------------
def _docs_for(requested: str, a: Dict[str, Any], outcome_branch: str) -> List[str]:
    docs = ["CUSTOMER_DECLARATION", "IDENTITY_DOCUMENT"]
    if a.get("cadastral_data"):
        pass
    else:
        docs.append("CADASTRAL_DATA")
    bp = a.get("building_permit")
    if bp in ("CILA", "SCIA", "BUILDING_PERMIT", "OTHER"):
        docs.append(bp if bp != "OTHER" else "BUILDING_DOCUMENTATION")
    if outcome_branch in ("RESTORATION", "SUPPLY_QUALIFIED"):
        docs.append("BUILDING_DOCUMENTATION")
    if outcome_branch == "BARRIERS":
        docs += ["TECHNICAL_REPORT", "BARRIER_DOCUMENTATION"]
    if outcome_branch == "CONSTRUCTION_4":
        docs += ["BUILDING_PERMIT", "COMMITTENT_DECLARATION_4"]
    return list(dict.fromkeys(docs))


def evaluate(requested: str, answers: Dict[str, Any], lines: List[Dict[str, Any]], net_total: float, dossier: Dict[str, Any], rule: Dict[str, Any]) -> Dict[str, Any]:
    a = answers or {}
    checks: List[Dict[str, Any]] = []
    missing: List[str] = []
    branch, outcome, basis = None, None, None
    mixed = None

    def ck(label, ok, info=None):
        checks.append({"label": label, "ok": ok, "info": info})

    if requested in (None, "", "VAT_ORDINARY"):
        return {"outcome": "STANDARD_22", "regime": "VAT_ORDINARY", "checks": [], "missing_requirements": [], "required_documents": [], "legal_basis": "Aliquota ordinaria", "pending_questions": [], "rule_version": rule.get("code"), "engine_version": FISCAL_ENGINE_VERSION}
    pending = pending_questions(requested, a)
    if requested == "VAT_REVIEW_REQUIRED":
        outcome, basis = "NEEDS_FISCAL_REVIEW", "Richiesta revisione fiscale esplicita"
    if a.get("residential_use") == "UNKNOWN":
        ck("Immobile a prevalente destinazione abitativa", False, "NON SO → revisione fiscale")
        outcome, basis = "NEEDS_FISCAL_REVIEW", "Destinazione immobile non determinata"
    elif a.get("residential_use"):
        ck("Immobile abitativo", a["residential_use"] == "YES")
    it = a.get("intervention_type")
    if it:
        ck(f"Intervento: {dict((k, v) for k, v in QUESTIONS['intervention_type']['options']).get(it, it)}", it not in ("UNKNOWN",))
    if requested in ("VAT_ELIGIBLE_10", "VAT_MIXED_10_22") and outcome is None and not pending:
        if a.get("residential_use") == "NO" and it in MAINTENANCE:
            outcome, basis = "NOT_ELIGIBLE", "Manutenzione su immobile non abitativo: IVA 10% non applicabile (Tab. A parte III)"
        elif it in MAINTENANCE:
            branch = "MAINTENANCE"
            if a.get("supply_and_install") == "YES":
                ck("Fornitura + posa nello stesso contratto", True)
                mixed = significant_goods_split(lines, net_total, rule)
                ck("Beni significativi (infissi) — Significant Goods Engine", True, f"bene significativo {mixed['value_of_significant_good']} € · 10% su {mixed['taxable_10']} € · 22% su {mixed['taxable_22']} €")
                outcome, basis = ("ELIGIBLE_MIXED_10_22" if mixed["taxable_22"] > 0 else "ELIGIBLE_10_FULL"), "L. 488/1999 art. 7 + DM 29/12/1999 — beni significativi su manutenzione immobile abitativo"
                if mixed["needs_review_lines"]:
                    outcome, basis = "NEEDS_FISCAL_REVIEW", basis + " · componenti con SIGNIFICANT_GOOD_RELATION = NEEDS_REVIEW"
            else:
                ck("Fornitura + posa nello stesso contratto", False, "sola cessione: IVA 10% non automatica sui serramenti")
                outcome, basis = "NEEDS_FISCAL_REVIEW", "Cessione serramenti senza posa nello stesso contratto: parte agevolabile da valutare"
        elif it in RESTORATION:
            branch = "RESTORATION"
            fc = a.get("formally_classified")
            ck("Intervento formalmente classificato (restauro/ristrutturazione)", fc == "YES")
            if fc == "YES":
                outcome, basis = "ELIGIBLE_10_FULL", "DPR 633/1972 Tab. A parte III n. 127-quaterdecies — appalto restauro/risanamento/ristrutturazione (no disciplina beni significativi)"
            elif fc == "NO":
                outcome, basis = "NOT_ELIGIBLE", "Intervento non qualificato come restauro/ristrutturazione"
            else:
                outcome, basis = "NEEDS_FISCAL_REVIEW", "Classificazione formale da verificare"
        elif it == "SUPPLY_ONLY":
            branch = "SUPPLY_QUALIFIED"
            q = a.get("supply_for_qualified_work")
            ck("Fornitura destinata a intervento qualificato", q == "YES")
            if q == "YES":
                outcome, basis = "ELIGIBLE_10_FULL", "Tab. A parte III n. 127-terdecies — beni forniti per interventi di recupero qualificati (dichiarazione + documentazione)"
            elif q == "NO":
                outcome, basis = "NOT_ELIGIBLE", "Sola fornitura per manutenzione semplice: IVA 10% non applicabile"
            else:
                outcome, basis = "NEEDS_FISCAL_REVIEW", "Destinazione della fornitura da verificare"
        else:
            outcome, basis = "NEEDS_FISCAL_REVIEW", "Intervento non riconducibile a un ramo IVA 10% automatico"
    if requested == "VAT_ELIGIBLE_4" and outcome is None and not pending:
        r = a.get("vat4_reason")
        if r == "ARCHITECTURAL_BARRIERS":
            branch = "BARRIERS"
            obj = a.get("barrier_contract_object")
            ck("Contratto con oggetto diretto opere barriere architettoniche", obj == "YES")
            if obj != "YES":
                outcome, basis = "NOT_ELIGIBLE", "IVA 4% barriere: il contratto non ha direttamente ad oggetto le opere agevolate"
            else:
                ck("Documentazione tecnica dell'intervento", a.get("barrier_technical_doc") == "YES")
                if a.get("disability_104") == "YES":
                    ck("Legge 104 presente (contesto, non sufficiente da sola)", True)
                outcome, basis = "ELIGIBLE_4", "DPR 633/1972 Tab. A parte II n. 41-ter — opere per superamento/eliminazione barriere architettoniche (validazione fiscale richiesta)"
        elif r == "CONSTRUCTION_4":
            branch = "CONSTRUCTION_4"
            outcome, basis = "NEEDS_FISCAL_REVIEW", "IVA 4% edilizia: NEEDS_FISCAL_VALIDATION finché la causale normativa esatta non è validata (no 'prima casa = 4%')"
        else:
            outcome, basis = "NEEDS_FISCAL_REVIEW", "Presupposto IVA 4% non determinato"
    if outcome is None:
        outcome, basis = "NEEDS_DOCUMENTATION", "Questionario incompleto"
    # documenti dinamici + dichiarazione
    docs = _docs_for(requested, a, branch or "") if outcome in ("ELIGIBLE_10_FULL", "ELIGIBLE_MIXED_10_22", "ELIGIBLE_4", "NEEDS_DOCUMENTATION", "NEEDS_FISCAL_REVIEW") else []
    have = {d.get("doc_type") for d in (dossier.get("documents") or [])}
    decl = (dossier.get("declaration") or {}).get("status") or "NOT_GENERATED"
    if pending:
        missing.append("classificazione intervento / risposte questionario")
    if docs and "CUSTOMER_DECLARATION" in docs:
        ck("Dichiarazione cliente firmata", decl in ("SIGNED", "VALIDATED"))
        if decl not in ("SIGNED", "VALIDATED"):
            missing.append("dichiarazione cliente" + ("" if decl == "NOT_GENERATED" else f" ({decl})"))
    for d in docs:
        if d != "CUSTOMER_DECLARATION" and d not in have:
            missing.append({"CADASTRAL_DATA": "dati catastali", "IDENTITY_DOCUMENT": "documento identità", "CILA": "CILA", "SCIA": "SCIA", "BUILDING_PERMIT": "permesso di costruire", "BUILDING_DOCUMENTATION": "documento edilizio",
                            "TECHNICAL_REPORT": "relazione tecnica", "BARRIER_DOCUMENTATION": "documentazione barriere architettoniche", "COMMITTENT_DECLARATION_4": "dichiarazione committente IVA 4%"}.get(d, d))
    if mixed and mixed["needs_review_lines"]:
        missing.append("valore beni significativi (componenti da classificare)")
    ck("Dossier completo", not missing)
    if outcome in ("ELIGIBLE_10_FULL", "ELIGIBLE_MIXED_10_22", "ELIGIBLE_4") and missing:
        final = "NEEDS_DOCUMENTATION"
    else:
        final = outcome
    return {"outcome": final, "eligible_outcome": outcome, "regime": OUTCOME_REGIME.get(outcome, "VAT_ORDINARY"), "checks": checks, "missing_requirements": missing, "required_documents": docs,
            "legal_basis": basis, "pending_questions": pending, "mixed_split": mixed, "branch": branch, "rule_version": rule.get("code"), "engine_version": FISCAL_ENGINE_VERSION,
            "evaluated_at": datetime.now(timezone.utc).isoformat(), "applied_vat_until_validation": "22%"}


def declaration_text(customer: Dict[str, Any], answers: Dict[str, Any], requested: str, evaluation: Dict[str, Any], quote_number: Optional[str]) -> str:
    name = " ".join(x for x in (customer.get("first_name"), customer.get("last_name")) if x) or customer.get("company_name") or "—"
    labels = {k: dict(v["options"]) for k, v in QUESTIONS.items()}
    rate = {"VAT_ELIGIBLE_10": "10%", "VAT_MIXED_10_22": "10% / 22%", "VAT_ELIGIBLE_4": "4%"}.get(requested, "agevolata")
    return (f"DICHIARAZIONE PER L'APPLICAZIONE DELL'IVA AGEVOLATA — Preventivo {quote_number or ''}\n\n"
            f"Il/La sottoscritto/a {name}, codice fiscale/P.IVA {customer.get('tax_code') or customer.get('vat_number') or '—'}, in qualità di {labels['customer_tax_profile'].get(answers.get('customer_tax_profile'), '—')}, "
            f"con riferimento all'immobile sito in {answers.get('property_address') or (customer.get('address') or {}).get('street') or '—'}"
            f"{(' (dati catastali: ' + str(answers.get('cadastral_data')) + ')') if answers.get('cadastral_data') else ''}, "
            f"a prevalente destinazione abitativa: {labels['residential_use'].get(answers.get('residential_use'), '—')},\n"
            f"DICHIARA che l'intervento oggetto del contratto è: {labels['intervention_type'].get(answers.get('intervention_type'), '—')}; "
            f"titolo/documentazione edilizia: {labels['building_permit'].get(answers.get('building_permit'), '—')}; "
            f"presupposto IVA richiesto: aliquota {rate}" + (f" — {labels['vat4_reason'].get(answers.get('vat4_reason'))}" if answers.get("vat4_reason") else "") +
            f".\nBase normativa di riferimento valutata: {evaluation.get('legal_basis') or '—'} (regole {evaluation.get('rule_version')}).\n\n"
            "Il cliente assume la responsabilità per la veridicità e completezza delle informazioni fornite e si impegna a comunicare tempestivamente ogni variazione. "
            "La società applica il regime IVA secondo la normativa vigente e le verifiche di propria competenza; l'aliquota agevolata viene applicata solo ad esito della validazione fiscale del dossier.")
