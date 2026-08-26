"""Price engine — computes line prices, applies rules, freezes snapshots."""
from __future__ import annotations
import math
from typing import Dict, Any, List, Tuple


def _round(amount: float, rule: str | None) -> float:
    if not rule:
        return round(amount, 2)
    if rule == "nearest_1":
        return math.floor(amount + 0.5)
    if rule == "nearest_5":
        return round(amount / 5) * 5
    if rule == "nearest_10":
        return round(amount / 10) * 10
    return round(amount, 2)


def compute_line(line: dict, rules: List[dict] | None = None) -> dict:
    """Compute derived pricing for a quote_line dict. Mutates and returns the line.
    
    Pipeline:
    1) base = base_price * quantity_factor (depending on base_type when known)
    2) apply surcharges (list of {type: pct|fixed, amount, label})
    3) subtract discount_pct then discount_amount
    4) round
    """
    qty = float(line.get("quantity") or 0)
    base = float(line.get("base_price") or 0)
    # Base can be per piece (default). If future base_type is set, multiply factors
    width = (line.get("width_mm") or 0) / 1000.0
    height = (line.get("height_mm") or 0) / 1000.0
    sqm = max(width * height, 0.0)

    base_type = line.get("base_type") or "piece"
    if base_type == "sqm":
        min_sqm = float(line.get("min_billable_sqm") or 0)
        billable = max(sqm, min_sqm)
        unit_base = base * billable
    elif base_type == "linear_m":
        unit_base = base * max(width + height, 0)
    else:
        unit_base = base

    # Surcharges: list of {type: 'pct'|'fixed', amount, label, condition_key}
    surcharges = line.get("surcharges") or []
    running_unit = unit_base
    total_surcharge = 0.0
    for s in surcharges:
        stype = s.get("type", "pct")
        amt = float(s.get("amount") or 0)
        if stype == "pct":
            add = running_unit * (amt / 100.0)
        else:
            add = amt
        running_unit += add
        total_surcharge += add

    # Discount pct then fixed
    dpct = float(line.get("discount_pct") or 0)
    if dpct:
        running_unit *= (1 - dpct / 100.0)
    damt = float(line.get("discount_amount") or 0)
    if damt:
        running_unit -= damt

    unit_final = max(running_unit, 0.0)
    product_subtotal = _round(unit_final * qty, line.get("rounding_rule"))

    # Installation Mode V1 (msg 393 §4): la POSITION può contenere
    # automatic_services[] + manual_extra_services[]. Il subtotal_line della
    # QuoteLine include l'aggregato dei servizi standard (fatturato + IVA).
    auto_svc = line.get("automatic_services") or []
    manual_svc = line.get("manual_extra_services") or []
    svc_sale = sum(float(s.get("sale_price_total") or 0) for s in auto_svc + manual_svc)
    svc_cost = sum(float(s.get("internal_cost_total") or 0) for s in auto_svc + manual_svc)
    line["standard_services_sale_total"] = round(svc_sale + 1e-9, 2)
    line["standard_services_internal_cost_total"] = round(svc_cost + 1e-9, 2)

    subtotal = round(product_subtotal + svc_sale + 1e-9, 2)
    line["unit_price_final"] = round(unit_final, 2)
    line["subtotal_line"] = subtotal
    line["position_sale_total"] = subtotal
    line["position_internal_cost_total"] = round(float(line.get("internal_cost") or 0) * qty + svc_cost + 1e-9, 2)
    line["margin"] = round(subtotal - (float(line.get("internal_cost") or 0) * qty) - svc_cost, 2)
    return line


def compute_quote_totals(lines: List[dict]) -> dict:
    """Aggregate totals across all lines."""
    subtotal = 0.0
    surcharges_total = 0.0
    discounts_total = 0.0
    vat_total = 0.0
    total = 0.0
    internal_cost_total = 0.0
    # Group VAT
    by_vat: dict[float, float] = {}
    for l in lines:
        sub = float(l.get("subtotal_line") or 0)
        vat_rate = float(l.get("vat_rate") or 0.22)
        by_vat[vat_rate] = by_vat.get(vat_rate, 0.0) + sub
        subtotal += sub
        internal_cost_total += float(l.get("internal_cost") or 0) * float(l.get("quantity") or 0)

    for rate, base in by_vat.items():
        vat_total += base * rate

    total = subtotal + vat_total
    margin_abs = subtotal - internal_cost_total
    margin_pct = (margin_abs / subtotal * 100) if subtotal > 0 else 0

    return {
        "subtotal": round(subtotal, 2),
        "total_surcharges": round(surcharges_total, 2),
        "total_discounts": round(discounts_total, 2),
        "taxable_amount": round(subtotal, 2),
        "vat_amount": round(vat_total, 2),
        "total": round(total, 2),
        "internal_cost": round(internal_cost_total, 2),
        "margin_abs": round(margin_abs, 2),
        "margin_pct": round(margin_pct, 2),
    }


def apply_color_surcharges(base_price: float, color_config: Dict[str, Any]) -> Tuple[float, List[Dict[str, Any]]]:
    """Apply Infissi Express default color rules. Returns (adjusted, surcharge_list)."""
    surcharges = []
    price = base_price
    kind = color_config.get("kind")  # ivory_mass | film_ext_white_int | film_both | film_int_only | film_diff
    if kind == "ivory_mass":
        surcharges.append({"type": "pct", "amount": 8, "label": "Avorio in massa"})
        price *= 1.08
    elif kind == "film_ext_white_int":
        surcharges.append({"type": "pct", "amount": 14.5, "label": "Pellicolato esterno / bianco interno"})
        price *= 1.145
    elif kind == "film_both":
        surcharges.append({"type": "pct", "amount": 16, "label": "Pellicolato entrambi i lati"})
        price *= 1.16
    elif kind == "film_int_only":
        surcharges.append({"type": "pct", "amount": 16, "label": "Pellicolato solo interno"})
        price *= 1.16
    elif kind == "film_diff":
        surcharges.append({"type": "pct", "amount": 22, "label": "Pellicolato differente sui due lati"})
        surcharges.append({"type": "fixed", "amount": 150, "label": "Supplemento pellicolatura differente"})
        price = price * 1.22 + 150
    return round(price, 2), surcharges
