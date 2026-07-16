"""Pricing engine v2.1 (M3.2 + scope semantics).

Explicit rule scoping to prevent ambiguity in quantity/scope multiplication:

  scope=unit  (default) — Rule applies to per-piece unit price BEFORE qty multiplication.
                          - pct: percentage of running unit price
                          - fixed: added once per piece (unless once_per_line=True)
                          - set: overrides unit price
                          If `once_per_line=True` and effect_type=fixed:
                            the amount is added just ONCE to the line total,
                            not multiplied by quantity.

  scope=line  — Rule applies to the line subtotal AFTER quantity multiplication.
                Applied only once per line (e.g., setup fee €150 per line).
                - pct: percentage of the running line subtotal
                - fixed: added once to line subtotal
                - set: overrides line subtotal

  scope=opening / scope=quote — reserved for cross-line aggregation.
                                Currently ignored at line-level preview;
                                will be handled by quote-totals engine.

Rules are applied in ascending priority order. Within same priority,
by created_at then id for determinism.

Rule application transparency: each breakdown entry includes:
  - step: base|rule|discount|quantity|vat
  - scope: unit|line|opening|quote
  - unit_before, unit_after, line_before, line_after (when applicable)
  - amount: the € impact at the level where it was applied
"""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

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


def _static_ctx(width_mm, height_mm, quantity, product_config, sqm, billable_sqm, perim, min_billable_sqm, internal_cost):
    return {
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
    warnings: List[str] = []
    breakdown: List[Dict[str, Any]] = []

    base_price = Decimal(str((product or {}).get("base_price") or product_config.get("base_price") or 0))
    base_type = ((product or {}).get("base_type")) or product_config.get("base_type") or "sqm"
    min_billable_sqm = Decimal(str((product or {}).get("min_billable_sqm") or product_config.get("min_billable_sqm") or 0))
    qty_dec = Decimal(str(quantity or 0))

    sqm = _sqm(width_mm, height_mm)
    perim = _perimeter(width_mm, height_mm)
    billable_sqm = max(sqm, min_billable_sqm)

    # Unit base (per piece)
    if base_type == "sqm":
        unit_base = base_price * billable_sqm
    elif base_type == "linear_m":
        unit_base = base_price * perim
    else:
        unit_base = base_price

    unit_running = unit_base  # per-piece running total during scope=unit rules
    line_running = Decimal("0")  # populated after quantity multiplication

    breakdown.append({
        "step": "base",
        "scope": "unit",
        "label": f"Base {base_type} · unitario",
        "code": "BASE",
        "base_price": float(money(base_price)),
        "quantity_factor": float(money(billable_sqm if base_type == "sqm" else (perim if base_type == "linear_m" else 1))),
        "unit_before": 0.0,
        "unit_after": float(money(unit_base)),
        "amount": float(money(unit_base)),
        "result": float(money(unit_base)),
        "note": f"{money(base_price)}€ × {money(billable_sqm) if base_type == 'sqm' else (money(perim) if base_type == 'linear_m' else 1)} = {money(unit_base)}€/pz",
    })

    # Sort rules deterministically
    sorted_rules = sorted(
        [r for r in rules if r.get("active", True)],
        key=lambda r: (int(r.get("priority") or 100), str(r.get("created_at") or ""), str(r.get("_id") or r.get("id") or "")),
    )

    static_ctx = _static_ctx(width_mm, height_mm, quantity, product_config, sqm, billable_sqm, perim, min_billable_sqm, internal_cost)

    # --- Pass 1: scope=unit rules (before quantity) ---
    unit_scope_fixed_once = []  # rules with scope=unit + once_per_line: applied to line, not per unit
    for r in sorted_rules:
        scope = (r.get("application_scope") or "unit")
        if scope != "unit":
            continue
        conds = r.get("conditions") or []
        if not evaluate_conditions(conds, product_config):
            continue
        # once_per_line + fixed → defer to line pass
        if r.get("once_per_line") and r.get("effect_type") == "fixed":
            unit_scope_fixed_once.append(r)
            continue
        formula = r.get("formula") or "0"
        ctx = {**static_ctx, "base_price": float(unit_running)}
        try:
            value = eval_formula(formula, ctx)
        except FormulaError as e:
            warnings.append(f"Regola {r.get('code')}: {e}")
            continue
        effect_type = r.get("effect_type", "fixed")
        prev_unit = unit_running
        if effect_type == "pct":
            add = (unit_running * value) / Decimal(100)
            unit_running = unit_running + add
            breakdown.append(_bd_pct(r, "unit", prev_unit, value, add, unit_running, per_piece=True))
        elif effect_type == "fixed":
            unit_running = unit_running + value
            breakdown.append(_bd_fixed(r, "unit", prev_unit, value, unit_running, per_piece=True))
        elif effect_type == "set":
            unit_running = value
            breakdown.append(_bd_set(r, "unit", prev_unit, value, unit_running, per_piece=True))

    unit_final = money(max(unit_running, Decimal("0")))
    # Quantity multiplication step
    line_running = unit_final * qty_dec
    breakdown.append({
        "step": "quantity",
        "scope": "line",
        "label": f"Moltiplicazione per quantità",
        "code": "QTY",
        "unit_after": float(unit_final),
        "quantity_factor": float(qty_dec),
        "line_before": 0.0,
        "line_after": float(money(line_running)),
        "amount": float(money(line_running)),
        "result": float(money(line_running)),
        "note": f"{unit_final}€/pz × {qty_dec}pz = {money(line_running)}€ linea",
    })

    # --- Pass 2: scope=unit + once_per_line=true fixed rules (applied to line once) ---
    for r in unit_scope_fixed_once:
        formula = r.get("formula") or "0"
        ctx = {**static_ctx, "base_price": float(line_running / qty_dec) if qty_dec > 0 else 0.0}
        try:
            value = eval_formula(formula, ctx)
        except FormulaError as e:
            warnings.append(f"Regola {r.get('code')}: {e}")
            continue
        prev_line = line_running
        line_running = line_running + value
        breakdown.append(_bd_fixed(r, "line", prev_line, value, line_running, per_piece=False, once=True))

    # --- Pass 3: scope=line rules (applied to line total, once) ---
    for r in sorted_rules:
        scope = (r.get("application_scope") or "unit")
        if scope != "line":
            continue
        conds = r.get("conditions") or []
        if not evaluate_conditions(conds, product_config):
            continue
        formula = r.get("formula") or "0"
        ctx = {**static_ctx, "base_price": float(line_running)}
        try:
            value = eval_formula(formula, ctx)
        except FormulaError as e:
            warnings.append(f"Regola {r.get('code')}: {e}")
            continue
        effect_type = r.get("effect_type", "fixed")
        prev_line = line_running
        if effect_type == "pct":
            add = (line_running * value) / Decimal(100)
            line_running = line_running + add
            breakdown.append(_bd_pct(r, "line", prev_line, value, add, line_running, per_piece=False))
        elif effect_type == "fixed":
            line_running = line_running + value
            breakdown.append(_bd_fixed(r, "line", prev_line, value, line_running, per_piece=False))
        elif effect_type == "set":
            line_running = value
            breakdown.append(_bd_set(r, "line", prev_line, value, line_running, per_piece=False))

    # Discount (always line-level, after rules)
    disc_pct = Decimal(str(discount_pct or 0))
    disc_amt = Decimal(str(discount_amount or 0))
    if disc_pct > 0:
        d = line_running * disc_pct / Decimal(100)
        prev = line_running
        line_running = line_running - d
        breakdown.append({
            "step": "discount", "scope": "line", "code": "DISCOUNT_PCT",
            "label": f"Sconto {disc_pct}%",
            "line_before": float(money(prev)), "line_after": float(money(line_running)),
            "percentage": float(money(disc_pct, 4)), "amount": float(money(-d)),
            "result": float(money(line_running)),
        })
    if disc_amt > 0:
        prev = line_running
        line_running = line_running - disc_amt
        breakdown.append({
            "step": "discount", "scope": "line", "code": "DISCOUNT_FIXED",
            "label": f"Sconto € {disc_amt}",
            "line_before": float(money(prev)), "line_after": float(money(line_running)),
            "amount": float(money(-disc_amt)),
            "result": float(money(line_running)),
        })

    subtotal = money(max(line_running, Decimal("0")))
    vat = money(subtotal * Decimal(str(vat_rate)))
    total = money(subtotal + vat)

    # Recompute unit_price_final (informational) as subtotal / qty when qty > 0
    effective_unit = money(subtotal / qty_dec) if qty_dec > 0 else Decimal("0")

    resp = {
        "request_id": request_id,
        "computed_at": datetime.now(timezone.utc),
        "pricelist_id": pricelist_id,
        "pricelist_name": pricelist_name,
        "width_mm": width_mm,
        "height_mm": height_mm,
        "quantity": float(qty_dec),
        "sqm": float(money(sqm, 4)),
        "billable_sqm": float(money(billable_sqm, 4)),
        "perimeter_m": float(money(perim, 4)),
        "base_price": float(money(base_price)),
        "unit_price_pre_qty": float(unit_final),   # per-piece final BEFORE line-scope rules
        "unit_price_final": float(effective_unit),  # per-piece effective AFTER all rules & discount
        "subtotal_line": float(subtotal),
        "vat_amount": float(vat),
        "total_line": float(total),
        "discount_pct": float(disc_pct),
        "discount_amount": float(disc_amt),
        "breakdown": breakdown,
        "warnings": warnings,
    }
    if can_see_costs:
        ic_total = money(Decimal(str(internal_cost or 0)) * qty_dec)
        margin = money(subtotal - ic_total)
        margin_pct = float((margin / subtotal * Decimal(100)).quantize(Decimal("0.01"))) if subtotal > 0 else 0.0
        resp["internal_cost"] = float(ic_total)
        resp["margin_abs"] = float(margin)
        resp["margin_pct"] = margin_pct
    return resp


def _bd_pct(r, scope, prev, pct, add, after, per_piece):
    label = r.get("name") or r.get("code")
    return {
        "step": "rule", "scope": scope, "code": r.get("code"),
        "category": r.get("category"),
        "label": label + (" · per pezzo" if per_piece else " · su linea"),
        "rule": {"formula": r.get("formula"), "priority": r.get("priority"), "scope": scope},
        "unit_before" if per_piece else "line_before": float(money(prev)),
        "unit_after" if per_piece else "line_after": float(money(after)),
        "base_of_calc": float(money(prev)),
        "percentage": float(money(pct, 4)),
        "amount": float(money(add)),
        "result": float(money(after)),
        "effect_type": "pct",
        "per_piece": per_piece,
    }


def _bd_fixed(r, scope, prev, amount, after, per_piece, once=False):
    label = r.get("name") or r.get("code")
    suffix = " · una volta per linea" if (once or not per_piece) else " · per pezzo"
    return {
        "step": "rule", "scope": scope, "code": r.get("code"),
        "category": r.get("category"),
        "label": label + suffix,
        "rule": {"formula": r.get("formula"), "priority": r.get("priority"), "scope": scope, "once_per_line": once},
        "unit_before" if per_piece and not once else "line_before": float(money(prev)),
        "unit_after" if per_piece and not once else "line_after": float(money(after)),
        "fixed_amount": float(money(amount)),
        "amount": float(money(amount)),
        "result": float(money(after)),
        "effect_type": "fixed",
        "per_piece": per_piece and not once,
    }


def _bd_set(r, scope, prev, value, after, per_piece):
    return {
        "step": "rule", "scope": scope, "code": r.get("code"),
        "category": r.get("category"),
        "label": (r.get("name") or r.get("code")) + " · sovrascrittura",
        "rule": {"formula": r.get("formula"), "priority": r.get("priority"), "scope": scope},
        "amount": float(money(value - prev)),
        "result": float(money(after)),
        "effect_type": "set",
        "per_piece": per_piece,
    }
