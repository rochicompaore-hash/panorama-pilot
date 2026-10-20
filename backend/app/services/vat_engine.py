"""VAT Engine V2 — regime determinato dal backend via Fiscal Dossier (mai dal commerciale)."""
from __future__ import annotations

from typing import Any, Dict, List

VAT_REGIMES = ("VAT_ORDINARY", "VAT_ELIGIBLE_4", "VAT_ELIGIBLE_10", "VAT_MIXED_10_22", "VAT_REVIEW_REQUIRED", "VAT_DOCUMENTATION_INCOMPLETE")
REGIME_RATES = {"VAT_ORDINARY": 0.22, "VAT_ELIGIBLE_4": 0.04, "VAT_ELIGIBLE_10": 0.10}
REQUESTABLE = ("VAT_ORDINARY", "VAT_ELIGIBLE_4", "VAT_ELIGIBLE_10", "VAT_MIXED_10_22", "VAT_REVIEW_REQUIRED")
# Selettore IVA (PO): opzioni visibili al commerciale → requested_regime
VAT_SELECTOR_OPTIONS = [
    {"value": "VAT_ORDINARY", "label": "IVA 22% ORDINARIA", "default": True},
    {"value": "VAT_ELIGIBLE_10", "label": "IVA 10% AGEVOLATA"},
    {"value": "VAT_ELIGIBLE_4", "label": "IVA 4% AGEVOLATA"},
    {"value": "VAT_MIXED_10_22", "label": "IVA MISTA 10% / 22%"},
    {"value": "VAT_REVIEW_REQUIRED", "label": "DA VERIFICARE"},
]
VAT_MODE_LABELS = {"VAT_ORDINARY": "IVA 22% ordinaria", "VAT_ELIGIBLE_10": "IVA 10% agevolata", "VAT_ELIGIBLE_4": "IVA 4% agevolata",
                   "VAT_MIXED_10_22": "IVA mista 10% / 22% (beni significativi)", "VAT_REVIEW_REQUIRED": "IVA da verificare — applicata 22% ordinaria",
                   "VAT_DOCUMENTATION_INCOMPLETE": "IVA agevolata — documentazione da completare — applicata 22% ordinaria"}
SERVICE_CATEGORIES = {"installation", "service", "services", "servizi", "posa", "smontaggio", "enea", "dismantling", "disposal", "logistics"}
VAT_POLICY_VERSION = "vat_engine_v2_2026_09"


def resolve_vat_regime(dossier: Dict[str, Any] | None) -> Dict[str, Any]:
    """Dossier → regime effettivo. Agevolata SOLO se eligibility VALIDATED + documentazione COMPLETE + dichiarazione cliente."""
    d = dossier or {}
    requested = d.get("requested_regime") or "VAT_ORDINARY"
    if requested not in REQUESTABLE:
        requested = "VAT_ORDINARY"
    if requested == "VAT_ORDINARY":
        return {"vat_regime": "VAT_ORDINARY", "vat_regime_reason": "DEFAULT_22"}
    if requested == "VAT_REVIEW_REQUIRED":
        return {"vat_regime": "VAT_REVIEW_REQUIRED", "vat_regime_reason": "REQUESTED_REVIEW", "applied_fallback": "VAT_ORDINARY"}
    ev = d.get("evaluation") or {}
    if ev.get("outcome") == "NOT_ELIGIBLE":
        return {"vat_regime": "VAT_ORDINARY", "vat_regime_reason": "FISCAL_ENGINE_NOT_ELIGIBLE", "applied_fallback": "VAT_ORDINARY"}
    if d.get("documentation_status") != "COMPLETE" or not d.get("customer_declaration"):
        return {"vat_regime": "VAT_DOCUMENTATION_INCOMPLETE", "vat_regime_reason": "DOCUMENTATION_OR_DECLARATION_MISSING", "applied_fallback": "VAT_ORDINARY"}
    if d.get("vat_eligibility_status") != "VALIDATED":
        return {"vat_regime": "VAT_REVIEW_REQUIRED", "vat_regime_reason": "ELIGIBILITY_NOT_VALIDATED", "applied_fallback": "VAT_ORDINARY"}
    # Fiscal Engine V2: l'aliquota finale è l'ESITO del motore (es. richiesta 10% → MISTA 10/22 per beni significativi), mai scelta libera
    final = ev.get("regime") if ev.get("eligible_outcome") in ("ELIGIBLE_10_FULL", "ELIGIBLE_MIXED_10_22", "ELIGIBLE_4") else requested
    return {"vat_regime": final, "vat_regime_reason": d.get("vat_reason") or ev.get("legal_basis") or "VALIDATED"}


def line_vat_rate(line: Dict[str, Any], regime: str) -> float:
    if regime in REGIME_RATES:
        return REGIME_RATES[regime]
    if regime == "VAT_MIXED_10_22":
        cat = str(line.get("category") or line.get("category_code") or "").lower()
        return 0.10 if cat in SERVICE_CATEGORIES or line.get("vat_class") == "SERVICE" else 0.22
    return 0.22


def apply_vat(totals: Dict[str, Any], lines: List[Dict[str, Any]], regime: str, mixed_split: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Ricalcola IVA per aliquota sull'imponibile finale (dopo sconti), ripartendo gli sconti pro-quota. Backend = source of truth.
    VAT_MIXED_10_22 con mixed_split (Significant Goods Engine, DM 29/12/1999) → ripartizione 10/22 calcolata dal Fiscal Engine."""
    effective = regime if regime in REGIME_RATES or regime == "VAT_MIXED_10_22" else "VAT_ORDINARY"
    gross_base = sum(float(l.get("subtotal_line") or 0) for l in lines)
    net = float(totals.get("subtotal") or 0)
    factor = (net / gross_base) if gross_base > 0 else 0.0
    by_rate: Dict[float, float] = {}
    if effective == "VAT_MIXED_10_22" and mixed_split and mixed_split.get("taxable_10") is not None:
        ref = float(mixed_split.get("taxable_10") or 0) + float(mixed_split.get("taxable_22") or 0)
        k = (net / ref) if ref > 0 else 0.0
        by_rate = {0.10: float(mixed_split["taxable_10"]) * k, 0.22: float(mixed_split["taxable_22"]) * k}
        lines = []
    for l in lines:
        r = line_vat_rate(l, effective)
        by_rate[r] = by_rate.get(r, 0.0) + float(l.get("subtotal_line") or 0) * factor
    breakdown = []
    vat_total = 0.0
    for r in sorted(by_rate):
        taxable = round(by_rate[r], 2)
        tax = round(taxable * r, 2)
        vat_total += tax
        breakdown.append({"rate": r, "rate_pct": round(r * 100), "taxable": taxable, "tax": tax})
    out = dict(totals)
    out.update({"vat_breakdown": breakdown, "vat_amount": round(vat_total, 2), "total": round(net + vat_total, 2),
                "vat_regime_applied": effective, "vat_policy_version": VAT_POLICY_VERSION})
    return out
