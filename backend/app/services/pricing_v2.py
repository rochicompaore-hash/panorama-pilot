"""Pricing engine v2 (M3.2).

Evaluates a product configuration against a versioned pricelist to produce:
  - unit_price_final (after rule stack)
  - breakdown (per-rule contribution for transparency)
  - subtotal, vat, total

Rule application:
  1. Sort active rules by priority (ascending).
  2. For each rule, evaluate declarative conditions against product_config.
  3. If match, evaluate the numeric formula with current context (dimensions, running price, etc.).
  4. Apply the effect: pct on running price / fixed add / set (override unit price).

Deterministic order is critical → priority + created_at tiebreaker.
"""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.services.formula import eval_formula, money, FormulaError
from app.services.conditions import evaluate_conditions


def _sqm(width_mm: int | None, height_mm: int | None) -> Decimal:
    w = Decimal(width_mm or 0) / Decimal(1000)
    h = Decimal(height_mm or 0) / Decimal(1000)
    if w <= 0 or h <= 0:
        return Decimal("0")
    return w * h


def _perimeter(width_mm: int | None, height_mm: int | None) -> Decimal:
    w = Decimal(width_mm or 0) / Decimal(1000)
    h = Decimal(height_mm or 0) / Decimal(1000)
    return (w + h) * 2


def compute_preview(
    *,
    product: Optional[Dict[str, Any]],
    rules: List[Dict[str, Any]],
    product_config: Dict[str, Any],
    width_mm: Optional[int],
    height_mm: Optional[int],
    quantity: float,
    discount_pct: float,
    discount_amount: float,
    vat_rate: float,
    internal_cost: float,
    can_see_costs: bool,
    pricelist_id: Optional[str],
    pricelist_name: Optional[str],
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Main preview computation. Returns a dict serializable to ConfiguratorPreviewResponse."""
    warnings: List[str] = []
    breakdown: List[Dict[str, Any]] = []

    # Base
    base_price = Decimal(str((product or {}).get("base_price") or product_config.get("base_price") or 0))
    base_type = ((product or {}).get("base_type")) or product_config.get("base_type") or "sqm"
    min_billable_sqm = Decimal(str((product or {}).get("min_billable_sqm") or product_config.get("min_billable_sqm") or 0))

    sqm = _sqm(width_mm, height_mm)
    perim = _perimeter(width_mm, height_mm)
    billable_sqm = max(sqm, min_billable_sqm)

    # Compute unit base
    if base_type == "sqm":
        unit_base = base_price * billable_sqm
    elif base_type == "linear_m":
        unit_base = base_price * perim
    else:
        unit_base = base_price

    breakdown.append({
        "step": "base",
        "label": f"Base {base_type}",
        "base_price": float(money(base_price)),
        "quantity_factor": float(money(billable_sqm if base_type == "sqm" else (perim if base_type == "linear_m" else 1))),
        "result": float(money(unit_base)),
        "code": "BASE",
    })

    running = unit_base

    # Sort rules deterministically
    sorted_rules = sorted(
        [r for r in rules if r.get("active", True)],
        key=lambda r: (int(r.get("priority") or 100), str(r.get("created_at") or ""), str(r.get("_id") or r.get("id") or "")),
    )

    ctx_static = {
        "width": (width_mm or 0) / 1000,
        "height": (height_mm or 0) / 1000,
        "area": float(sqm),
        "sqm": float(sqm),
        "billable_area": float(billable_sqm),
        "min_billable_sqm": float(min_billable_sqm),
        "perimeter": float(perim),
        "linear_meters": float(perim),
        "quantity": float(quantity),
        "leaves": float(product_config.get("leaves") or 1),
        "weight": float(product_config.get("weight") or 0),
        "base_cost": float(internal_cost),
    }

    for r in sorted_rules:
        conds = r.get("conditions") or []
        if not evaluate_conditions(conds, product_config):
            continue
        formula = r.get("formula") or "0"
        ctx = {**ctx_static, "base_price": float(running)}
        try:
            value = eval_formula(formula, ctx)
        except FormulaError as e:
            warnings.append(f"Regola {r.get('code')}: {e}")
            continue

        effect_type = r.get("effect_type", "fixed")
        prev = running
        if effect_type == "pct":
            add = (running * value) / Decimal(100)
            running = running + add
            breakdown.append({
                "step": "rule",
                "label": r.get("name") or r.get("code"),
                "code": r.get("code"),
                "category": r.get("category"),
                "rule": {"formula": formula, "priority": r.get("priority")},
                "base_of_calc": float(money(prev)),
                "percentage": float(money(value, 4)),
                "amount": float(money(add)),
                "result": float(money(running)),
                "effect_type": "pct",
            })
        elif effect_type == "fixed":
            running = running + value
            breakdown.append({
                "step": "rule",
                "label": r.get("name") or r.get("code"),
                "code": r.get("code"),
                "category": r.get("category"),
                "rule": {"formula": formula, "priority": r.get("priority")},
                "base_of_calc": float(money(prev)),
                "fixed_amount": float(money(value)),
                "amount": float(money(value)),
                "result": float(money(running)),
                "effect_type": "fixed",
            })
        elif effect_type == "set":
            running = value
            breakdown.append({
                "step": "rule",
                "label": r.get("name") or r.get("code"),
                "code": r.get("code"),
                "category": r.get("category"),
                "rule": {"formula": formula, "priority": r.get("priority")},
                "base_of_calc": float(money(prev)),
                "amount": float(money(value - prev)),
                "result": float(money(running)),
                "effect_type": "set",
            })

    # Apply discount
    disc_pct = Decimal(str(discount_pct or 0))
    disc_amt = Decimal(str(discount_amount or 0))
    if disc_pct > 0:
        d = running * disc_pct / Decimal(100)
        breakdown.append({
            "step": "discount",
            "label": f"Sconto {disc_pct}%",
            "code": "DISCOUNT_PCT",
            "base_of_calc": float(money(running)),
            "percentage": float(money(disc_pct, 4)),
            "amount": float(money(-d)),
            "result": float(money(running - d)),
            "effect_type": "pct",
        })
        running = running - d
    if disc_amt > 0:
        breakdown.append({
            "step": "discount",
            "label": f"Sconto € {disc_amt}",
            "code": "DISCOUNT_FIXED",
            "amount": float(money(-disc_amt)),
            "result": float(money(running - disc_amt)),
            "effect_type": "fixed",
        })
        running = running - disc_amt

    unit_final = money(max(running, Decimal("0")))
    qty = Decimal(str(quantity or 0))
    subtotal = money(unit_final * qty)
    vat = money(subtotal * Decimal(str(vat_rate)))
    total = money(subtotal + vat)

    resp = {
        "request_id": request_id,
        "computed_at": datetime.now(timezone.utc),
        "pricelist_id": pricelist_id,
        "pricelist_name": pricelist_name,
        "width_mm": width_mm,
        "height_mm": height_mm,
        "quantity": float(qty),
        "sqm": float(money(sqm, 4)),
        "billable_sqm": float(money(billable_sqm, 4)),
        "perimeter_m": float(money(perim, 4)),
        "base_price": float(money(base_price)),
        "unit_price_final": float(unit_final),
        "subtotal_line": float(subtotal),
        "vat_amount": float(vat),
        "total_line": float(total),
        "discount_pct": float(disc_pct),
        "discount_amount": float(disc_amt),
        "breakdown": breakdown,
        "warnings": warnings,
    }
    if can_see_costs:
        ic_total = money(Decimal(str(internal_cost or 0)) * qty)
        margin = money(subtotal - ic_total)
        margin_pct = float((margin / subtotal * Decimal(100)).quantize(Decimal("0.01"))) if subtotal > 0 else 0.0
        resp["internal_cost"] = float(ic_total)
        resp["margin_abs"] = float(margin)
        resp["margin_pct"] = margin_pct
    return resp
