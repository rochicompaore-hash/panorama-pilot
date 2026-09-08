"""Delivery policy (PO msg 402 Lotto 9) — tempi automatici + maggiorazione EXPRESS +20%.

STANDARD: oltre 90 giorni (salvo policy prodotto/pacchetto specifica configurata).
EXPRESS: +20% sulla base commerciale (righe prodotto/servizi, esclusi ENEA); giorni = NEEDS_PO_CONFIRMATION.
"""
from __future__ import annotations
from typing import Any, Dict, Optional

DELIVERY_POLICY_VERSION = "delivery_policy_v1_msg402"
EXPRESS_SURCHARGE_PERCENT = 20.0

DELIVERY_MODES: Dict[str, Dict[str, Any]] = {
    "STANDARD": {
        "label": "Consegna standard",
        "estimated_delivery_min_days": 90, "estimated_delivery_max_days": None,
        "customer_text": "Oltre 90 giorni dall'ordine e dal rilievo tecnico definitivo, salvo diversa tempistica indicata per prodotto o pacchetto.",
        "surcharge_percent": 0.0, "express_days_status": None,
    },
    "EXPRESS": {
        "label": "Consegna accelerata (+20%)",
        "estimated_delivery_min_days": None, "estimated_delivery_max_days": None,
        "customer_text": "Consegna accelerata: tempistica da confermare per iscritto al momento dell'ordine.",
        "surcharge_percent": EXPRESS_SURCHARGE_PERCENT, "express_days_status": "NEEDS_PO_CONFIRMATION",
        # PO msg 403 §6: senza giorni definiti la modalità NON è acquistabile dal cliente (fail-closed)
        "customer_ready": False, "not_ready_code": "EXPRESS_DELIVERY_NOT_READY_FOR_CUSTOMER_USE",
    },
}


def resolve_delivery(mode: Optional[str]) -> Dict[str, Any]:
    m = (mode or "STANDARD").upper()
    pol = DELIVERY_MODES.get(m)
    if not pol:
        raise ValueError(f"DELIVERY_MODE_INVALID:{m}")
    if pol.get("customer_ready") is False:
        raise ValueError(pol["not_ready_code"])
    return {
        "delivery_mode": m,
        "delivery_label": pol["label"],
        "estimated_delivery_min_days": pol["estimated_delivery_min_days"],
        "estimated_delivery_max_days": pol["estimated_delivery_max_days"],
        "delivery_customer_text": pol["customer_text"],
        "delivery_surcharge_percent": float(pol["surcharge_percent"]),
        "express_days_status": pol["express_days_status"],
        "delivery_policy_version": DELIVERY_POLICY_VERSION,
    }


def express_surcharge_base(lines: list) -> float:
    """Base commerciale: righe prodotto + servizi, escluse pratiche ENEA."""
    return round(sum(float(l.get("subtotal_line") or 0) for l in lines if not l.get("enea_practice")), 2)


def apply_delivery_surcharge(totals: Dict[str, Any], lines: list, surcharge_percent: float) -> Dict[str, Any]:
    pct = float(surcharge_percent or 0)
    if pct <= 0:
        return {**totals, "delivery_surcharge_amount": 0.0}
    base = express_surcharge_base(lines)
    amount = round(base * pct / 100.0, 2)
    gross_subtotal = float(totals.get("subtotal") or 0)
    if gross_subtotal <= 0 or amount <= 0:
        return {**totals, "delivery_surcharge_amount": 0.0}
    # IVA: la maggiorazione segue l'aliquota media delle righe base (proporzionale)
    vat_ratio = float(totals.get("vat_amount") or 0) / gross_subtotal
    out = dict(totals)
    out["delivery_surcharge_amount"] = amount
    out["subtotal"] = round(gross_subtotal + amount, 2)
    out["taxable_amount"] = out["subtotal"]
    out["vat_amount"] = round(float(totals.get("vat_amount") or 0) + amount * vat_ratio, 2)
    out["total"] = round(out["subtotal"] + out["vat_amount"], 2)
    out["margin_abs"] = round(out["subtotal"] - float(totals.get("internal_cost") or 0), 2)
    out["margin_pct"] = round(out["margin_abs"] / out["subtotal"] * 100, 2) if out["subtotal"] > 0 else 0
    return out
