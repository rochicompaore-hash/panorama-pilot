"""Payment terms policy (PO msg 402 Lotto 5) — menu strutturato + sconto automatico.

FULL_UPFRONT → automatic_discount_percent = 5. Le altre modalità: 0.
Finanziamento: solo scelta WITH_DEPOSIT / WITHOUT_DEPOSIT (TAN/TAEG/rate = BACKLOG).
"""
from __future__ import annotations
from typing import Any, Dict, Optional

PAYMENT_POLICY_VERSION = "payment_terms_v1_msg402"
DEFAULT_PAYMENT_TERMS = "DEPOSIT_50_BALANCE_50"

PAYMENT_POLICIES: Dict[str, Dict[str, Any]] = {
    "DEPOSIT_50_BALANCE_50": {
        "label": "50% acconto all'ordine · 50% avviso merce pronta",
        "schedule": [{"step": "ORDER", "percent": 50, "label": "Acconto all'ordine"},
                     {"step": "GOODS_READY", "percent": 50, "label": "Avviso merce pronta"}],
        "automatic_discount_percent": 0.0, "financing_mode": None,
    },
    "FULL_UPFRONT": {
        "label": "100% all'ordine (sconto automatico 5%)",
        "schedule": [{"step": "ORDER", "percent": 100, "label": "Pagamento all'ordine"}],
        "automatic_discount_percent": 5.0, "financing_mode": None,
    },
    "DEPOSIT_30_SURVEY_20_BALANCE_50": {
        "label": "30% acconto · 20% dopo rilievo tecnico · 50% avviso merce pronta",
        "schedule": [{"step": "ORDER", "percent": 30, "label": "Acconto all'ordine"},
                     {"step": "TECHNICAL_SURVEY", "percent": 20, "label": "Dopo rilievo tecnico"},
                     {"step": "GOODS_READY", "percent": 50, "label": "Avviso merce pronta"}],
        "automatic_discount_percent": 0.0, "financing_mode": None,
    },
    "FINANCING_WITHOUT_DEPOSIT": {
        "label": "Finanziamento senza acconto",
        "schedule": [{"step": "FINANCING", "percent": 100, "label": "Finanziamento (istituto)"}],
        "automatic_discount_percent": 0.0, "financing_mode": "WITHOUT_DEPOSIT",
    },
    "FINANCING_WITH_DEPOSIT": {
        "label": "Finanziamento con acconto",
        "schedule": [{"step": "ORDER", "percent": None, "label": "Acconto all'ordine (importo da definire)"},
                     {"step": "FINANCING", "percent": None, "label": "Saldo tramite finanziamento"}],
        "automatic_discount_percent": 0.0, "financing_mode": "WITH_DEPOSIT",
    },
}


def resolve_payment_terms(code: Optional[str]) -> Dict[str, Any]:
    """Ritorna i campi snapshot per il preventivo. Codice sconosciuto → ValueError (fail-closed)."""
    c = (code or DEFAULT_PAYMENT_TERMS).upper()
    pol = PAYMENT_POLICIES.get(c)
    if not pol:
        raise ValueError(f"PAYMENT_TERMS_INVALID:{c}")
    return {
        "payment_terms": c,
        "payment_terms_code": c,
        "payment_terms_label": pol["label"],
        "payment_schedule": pol["schedule"],
        "automatic_discount_percent": float(pol["automatic_discount_percent"]),
        "financing_mode": pol["financing_mode"],
        "payment_policy_version": PAYMENT_POLICY_VERSION,
    }


def apply_automatic_discount(totals: Dict[str, Any], discount_percent: float) -> Dict[str, Any]:
    """Applica lo sconto automatico (pagamento) su subtotal/IVA/totale — visibile, mai nascosto."""
    pct = float(discount_percent or 0)
    gross_subtotal = float(totals.get("subtotal") or 0)
    if pct <= 0 or gross_subtotal <= 0:
        return {**totals, "payment_discount_amount": 0.0, "subtotal_before_payment_discount": round(gross_subtotal, 2)}
    factor = 1.0 - pct / 100.0
    discount_amount = round(gross_subtotal * pct / 100.0, 2)
    subtotal = round(gross_subtotal - discount_amount, 2)
    vat = round(float(totals.get("vat_amount") or 0) * factor, 2)
    out = dict(totals)
    out.update({
        "subtotal_before_payment_discount": round(gross_subtotal, 2),
        "payment_discount_amount": discount_amount,
        "total_discounts": round(float(totals.get("total_discounts") or 0) + discount_amount, 2),
        "subtotal": subtotal, "taxable_amount": subtotal, "vat_amount": vat,
        "total": round(subtotal + vat, 2),
        "margin_abs": round(subtotal - float(totals.get("internal_cost") or 0), 2),
    })
    out["margin_pct"] = round(out["margin_abs"] / subtotal * 100, 2) if subtotal > 0 else 0
    return out
