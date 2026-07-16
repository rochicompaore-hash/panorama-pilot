"""Parametric BOM Engine — risolve una BOM parametrica in una BOM concreta.

Input:
  - BomTemplate + set di parametri (L, H, nr_ante, color_category_id, glass_id, hardware_id, …)
Output:
  - Lista di componenti concreti con: quantità, lunghezza, area, peso, unità
  - Aggregato di costi (dal listino costo)
  - Preview lista taglio preliminare (opzionale)

Design:
- Nessun eval(): usa services/formula.eval_formula (parser AST).
- Condizioni di applicabilità: usa services/conditions.evaluate_conditions.
- Rounding: applicabile per componente (`rounding_rule`).
- Scarto tecnico waste_pct: applicato alla quantità/lunghezza post-formula.
"""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP, ROUND_UP, ROUND_DOWN
from typing import Dict, Any, List, Optional, Tuple

from app.services.formula import eval_formula, FormulaError, money, _STRICT
from app.services.conditions import evaluate_conditions


def build_formula_context(
    *,
    width_mm: int,
    height_mm: int,
    nr_ante: int = 1,
    nr_traversi: int = 0,
    nr_montanti: int = 0,
    nr_fissi: int = 0,
    nr_vetri: int = 0,
    ps_tech: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
    component_index: int = 0,
) -> Dict[str, Any]:
    """Costruisce il contesto variabili per il parser formule.
    Legenda:
      L, H, width_mm, height_mm  → dimensioni foro (mm)
      area                        → area in m² (foro)
      perimeter                   → perimetro in m (foro)
      frame_width, frame_depth, … → parametri sistema profilo
    """
    tech = ps_tech or {}
    L = float(width_mm or 0)
    H = float(height_mm or 0)
    area = (L / 1000.0) * (H / 1000.0) if L > 0 and H > 0 else 0.0
    perimeter = ((L + H) * 2.0) / 1000.0 if L > 0 and H > 0 else 0.0
    ctx: Dict[str, Any] = {
        "L": L, "H": H, "width_mm": L, "height_mm": H,
        "width": L / 1000.0, "height": H / 1000.0,
        "area": area, "sqm": area, "billable_area": area, "min_billable_sqm": 0.0,
        "perimeter": perimeter, "linear_meters": perimeter,
        "quantity": 1.0, "leaves": float(nr_ante), "weight": 0.0,
        "base_price": 0.0, "base_cost": 0.0,
        # contatori
        "nr_ante": float(nr_ante or 0),
        "nr_traversi": float(nr_traversi or 0),
        "nr_montanti": float(nr_montanti or 0),
        "nr_fissi": float(nr_fissi or 0),
        "nr_vetri": float(nr_vetri or 0),
        # taglio
        "kerf": float(tech.get("kerf_mm", 3.0)),
        "bar_length": float(tech.get("bar_length_mm", 6500)),
        # sistema profilo
        "frame_width": float(tech.get("frame_width_mm", 70.0)),
        "frame_depth": float(tech.get("frame_depth_mm", 70.0)),
        "sash_width": float(tech.get("sash_width_mm", 78.0)),
        "sash_depth": float(tech.get("sash_depth_mm", 78.0)),
        "central_node": float(tech.get("central_node_mm", 108.0)),
        "rebate": float(tech.get("rebate_mm", 20.0)),
        "glass_clearance": float(tech.get("glass_clearance_mm", 4.0)),
        "glass_deduction": float(tech.get("glass_deduction_mm", 60.0)),
        "weld_allowance": float(tech.get("weld_allowance_mm", 0.0)),
        "glazing_bead_clearance": float(tech.get("glazing_bead_clearance_mm", 2.0)),
        "frame_clearance": float(tech.get("frame_clearance_mm", 6.0)),
        "sash_clearance": float(tech.get("sash_clearance_mm", 4.0)),
        "overlap": float(tech.get("overlap_mm", 8.0)),
        "threshold_height": float(tech.get("threshold_height_mm", 0.0)),
        "mullion_offset": float(tech.get("mullion_offset_mm", 0.0)),
        "transom_offset": float(tech.get("transom_offset_mm", 0.0)),
        "coupling_gap": float(tech.get("coupling_gap_mm", 0.0)),
        "installation_gap": float(tech.get("installation_gap_mm", 10.0)),
        "profile_length_adjustment": float(tech.get("profile_length_adjustment_mm", 0.0)),
        # derived (default 0, calcolabili tramite formule)
        "glass_width": 0.0, "glass_height": 0.0, "glass_area": 0.0, "glass_weight": 0.0,
        "profile_weight": 0.0, "total_weight": 0.0,
        "component_index": float(component_index),
    }
    if extra:
        ctx.update({k: (float(v) if isinstance(v, (int, float, Decimal)) else v)
                    for k, v in extra.items()
                    if isinstance(v, (int, float, Decimal))})
    return ctx


def _apply_rounding(value: float, rule: str) -> float:
    if rule == "up":
        return float(Decimal(str(value)).to_integral_value(rounding=ROUND_UP))
    if rule == "down":
        return float(Decimal(str(value)).to_integral_value(rounding=ROUND_DOWN))
    if rule == "nearest":
        return float(Decimal(str(value)).to_integral_value(rounding=ROUND_HALF_UP))
    if rule == "nearest_5":
        return float((Decimal(str(value)) / 5).to_integral_value(ROUND_HALF_UP) * 5)
    if rule == "nearest_10":
        return float((Decimal(str(value)) / 10).to_integral_value(ROUND_HALF_UP) * 10)
    return value


def resolve_bom(
    *,
    bom_template: Dict[str, Any],
    profile_system: Dict[str, Any],
    params: Dict[str, Any],
    lookup_price: Optional[callable] = None,
    lookup_cost: Optional[callable] = None,
) -> Dict[str, Any]:
    """Risolve un BomTemplate per un set di parametri.

    Args:
        bom_template: doc bom_templates
        profile_system: doc profile_systems
        params: {width_mm, height_mm, nr_ante, ..., color_category_id, glass_type_id, hardware_kit_id}
        lookup_price(ref_type, ref_id, color_id, unit) -> unit_price (sell)
        lookup_cost(ref_type, ref_id, color_id, unit) -> unit_cost

    Returns:
        {
          "components": [ { ...resolved... } ],
          "materials_cost": float,
          "materials_price": float,
          "warnings": [str],
        }
    """
    warnings: List[str] = []
    tech = (profile_system or {}).get("tech") or {}
    width_mm = int(params.get("width_mm") or 0)
    height_mm = int(params.get("height_mm") or 0)
    nr_ante = int(params.get("nr_ante") or 1)
    nr_traversi = int(params.get("nr_traversi") or 0)
    nr_montanti = int(params.get("nr_montanti") or 0)
    nr_fissi = int(params.get("nr_fissi") or 0)
    color_category_id = params.get("color_category_id") or bom_template.get("color_category_default_id")
    color_id = params.get("color_id")

    resolved: List[Dict[str, Any]] = []
    total_cost = Decimal("0")
    total_price = Decimal("0")
    blocking_errors: List[Dict[str, Any]] = []

    for idx, comp in enumerate(bom_template.get("components") or []):
        # Condizione di applicabilità
        conditions = comp.get("condition") or []
        if not evaluate_conditions(conditions, params):
            continue
        ctx = build_formula_context(
            width_mm=width_mm, height_mm=height_mm,
            nr_ante=nr_ante, nr_traversi=nr_traversi, nr_montanti=nr_montanti,
            nr_fissi=nr_fissi,
            ps_tech=tech, extra=params, component_index=idx,
        )

        def _f(field: str, expr: str | None, *, required: bool = False):
            """Evaluate a formula and record blocking error on failure."""
            if not expr:
                return None
            try:
                return float(eval_formula(expr, ctx, strict=True))
            except FormulaError as e:
                err = {
                    "code": e.code,
                    "message": str(e),
                    "formula": expr,
                    "component_id": comp.get("id"),
                    "component_type": comp.get("component_type"),
                    "role": comp.get("role") or comp.get("component_type"),
                    "field": field,
                    "severity": "blocking",
                    "suggested_action": (
                        "Verifica il valore di 'nr_ante' o del divisore nella formula" if e.code == "DIV_ZERO"
                        else "Verifica formula e variabili disponibili" if e.code in ("SYNTAX", "UNKNOWN_VAR")
                        else "Verifica limiti dimensionali/complessità" if e.code == "LIMIT"
                        else "Contatta l'amministratore del preventivatore"
                    ),
                }
                blocking_errors.append(err)
                return None

        qty = _f("quantity_formula", comp.get("quantity_formula") or "1")
        if qty is None:
            continue
        length_mm: Optional[float] = _f("length_formula", comp.get("length_formula"))
        width_c: Optional[float] = _f("width_formula", comp.get("width_formula"))
        height_c: Optional[float] = _f("height_formula", comp.get("height_formula"))
        area_sqm: Optional[float] = _f("area_formula", comp.get("area_formula"))
        if area_sqm is None and width_c and height_c:
            area_sqm = (width_c / 1000.0) * (height_c / 1000.0)
        weight_kg: Optional[float] = _f("weight_formula", comp.get("weight_formula"))

        # Se qualche formula rilevante del componente ha errore bloccante → salta il componente
        comp_had_error = any(e.get("component_id") == comp.get("id") for e in blocking_errors)
        if comp_had_error:
            continue

        # Verifica limite tecnico: taglio > barra utile
        _bar_len = float(tech.get("bar_length_mm", 6500))
        _head = float(tech.get("bar_head_offcut_mm", 50))
        _tail = float(tech.get("bar_tail_offcut_mm", 50))
        _usable = _bar_len - _head - _tail
        if length_mm and length_mm > _usable and comp.get("is_cutting_relevant", True):
            blocking_errors.append({
                "code": "CUT_TOO_LONG",
                "message": f"Taglio {length_mm:.0f}mm > barra utile {_usable:.0f}mm",
                "formula": comp.get("length_formula"),
                "component_id": comp.get("id"),
                "role": comp.get("role"),
                "field": "length_formula",
                "severity": "blocking",
                "suggested_action": "Aumenta bar_length_mm nel sistema profilo, oppure verifica dimensioni foro",
            })
            continue

        # === Sfrido: % + fisso mm/taglio + fisso per pezzo ===
        waste_pct = float(comp.get("waste_pct") or 0)
        scrap_fixed_mm_per_cut = float(comp.get("scrap_fixed_mm_per_cut") or 0)
        scrap_fixed_per_piece = float(comp.get("scrap_fixed_per_piece") or 0)
        consumption_mode = comp.get("consumption_mode") or "proportional"
        bar_rounding = bool(comp.get("bar_rounding") or False)

        # Quantità netta prima di qualsiasi scarto/rounding — utile per l'audit
        qty_net = float(qty)
        length_mm_net = float(length_mm) if length_mm is not None else None

        # 1) Scarto in mm per taglio (profili): estende la length_mm
        if length_mm is not None and scrap_fixed_mm_per_cut > 0:
            length_mm = length_mm + scrap_fixed_mm_per_cut
        # 2) Scarto % (già presente) — su qty e length
        qty = qty * (1.0 + waste_pct / 100.0)
        if length_mm is not None:
            length_mm = length_mm * (1.0 + waste_pct / 100.0)
        # 3) Scarto fisso per pezzo — aggiunto alla quantità
        if scrap_fixed_per_piece > 0:
            qty = qty + scrap_fixed_per_piece

        # 4) Rounding rule (up/down/nearest/…)
        qty = _apply_rounding(qty, comp.get("rounding_rule") or "none")

        # 5) Minimo tecnico
        min_q = float(comp.get("minimum_quantity") or 0)
        if min_q > 0 and qty < min_q:
            qty = min_q

        # 6) Minimo fatturabile per riga (commerciale)
        min_billable_qty = float(comp.get("minimum_billable_qty") or 0)
        # Sarà applicato più avanti su line_measure post-consumo

        # 7) Arrotondamento alla barra intera (opt-in) — per profili
        row_warnings: List[str] = []
        bars_needed = 0
        if bar_rounding and comp.get("component_type") == "profile" and length_mm and length_mm > 0:
            # Numero barre necessarie (arrotondamento up) per soddisfare qty pezzi × length_mm
            total_length_mm_needed = qty * length_mm
            bars_needed_float = total_length_mm_needed / max(_usable, 1)
            bars_needed = int(-(-bars_needed_float // 1))  # ceil
            row_warnings.append(
                f"Barra intera imputata: {bars_needed} barra/e da {_usable:.0f}mm utili"
            )

        # Prezzo/costo unitario (dai listini)
        unit_price = 0.0
        unit_cost = 0.0
        if lookup_price:
            unit_price = float(lookup_price(
                comp.get("component_type"), comp.get("ref_id"), color_id, comp.get("unit_of_measure"),
            ) or 0)
        if lookup_cost:
            unit_cost = float(lookup_cost(
                comp.get("component_type"), comp.get("ref_id"), color_id, comp.get("unit_of_measure"),
            ) or 0)

        # ==== Consumo: proporzionale vs barra intera imputata ====
        # line_measure = quantità × unità (m per profili, m² per vetro, pz altrimenti)
        # In "full_bar" (o bar_rounding=True) usiamo la barra intera come unità imputata.
        line_measure_net = float(qty_net)
        if comp.get("component_type") == "profile" and length_mm_net:
            line_measure_net = float(qty_net) * (length_mm_net / 1000.0)
        elif comp.get("component_type") == "glass" and area_sqm:
            line_measure_net = float(qty_net) * float(area_sqm)

        line_measure = qty
        if comp.get("component_type") == "profile" and length_mm:
            length_m = length_mm / 1000.0
            line_measure = qty * length_m
            if consumption_mode == "full_bar" or bar_rounding:
                # Il cliente paga barre intere: line_measure = bars × usable_m
                if not bars_needed:
                    total_length_mm_needed = qty * length_mm
                    bars_needed_float = total_length_mm_needed / max(_usable, 1)
                    bars_needed = int(-(-bars_needed_float // 1))
                line_measure = bars_needed * (_usable / 1000.0)
                row_warnings.append(
                    f"Modalità 'barra intera imputata': fatturati {bars_needed} × {_usable/1000:.2f}m"
                )
        elif comp.get("component_type") == "glass" and area_sqm:
            line_measure = qty * area_sqm

        # 8) Minimo fatturabile su line_measure
        if min_billable_qty > 0 and line_measure < min_billable_qty:
            row_warnings.append(
                f"Applicato minimo fatturabile: {line_measure:.3f} → {min_billable_qty}"
            )
            line_measure = min_billable_qty

        line_cost = Decimal(str(unit_cost)) * Decimal(str(line_measure))
        line_price = Decimal(str(unit_price)) * Decimal(str(line_measure))

        # Warning: prezzo/costo mancanti se ref_id presente
        if comp.get("ref_id") and lookup_price and unit_price == 0:
            row_warnings.append("Prezzo listino non trovato per questo componente")
        if comp.get("ref_id") and lookup_cost and unit_cost == 0:
            row_warnings.append("Costo listino non trovato per questo componente")

        if comp.get("is_cost_relevant", True):
            total_cost += line_cost
        total_price += line_price

        # Formula/condizione applicate (audit human-readable)
        formula_parts = []
        if comp.get("quantity_formula"):
            formula_parts.append(f"qty = {comp['quantity_formula']}")
        if comp.get("length_formula"):
            formula_parts.append(f"len_mm = {comp['length_formula']}")
        if comp.get("width_formula"):
            formula_parts.append(f"w_mm = {comp['width_formula']}")
        if comp.get("height_formula"):
            formula_parts.append(f"h_mm = {comp['height_formula']}")
        if comp.get("area_formula"):
            formula_parts.append(f"area_sqm = {comp['area_formula']}")
        formula_applied = " ; ".join(formula_parts)

        # Waste_qty (in unità pezzi o ml, come segnaposto)
        waste_qty = float(qty) - float(qty_net) if qty >= qty_net else 0.0

        resolved.append({
            "component_id": comp.get("id"),
            "sequence": comp.get("sequence", 0),
            "component_type": comp.get("component_type"),
            "ref_id": comp.get("ref_id"),
            "role": comp.get("role"),
            # Recipe metadata per audit / UI
            "recipe_code": comp.get("recipe_code"),
            "recipe_params": comp.get("recipe_params") or {},
            "description_override": comp.get("description_override"),
            # Quantities
            "quantity_net": float(money(Decimal(str(qty_net)), 3)),
            "quantity": float(money(Decimal(str(qty)), 3)),
            "waste_qty": float(money(Decimal(str(waste_qty)), 3)),
            "quantity_billable": float(money(Decimal(str(line_measure)), 4)),
            "bars_needed": bars_needed if bars_needed else None,
            "length_mm": float(money(Decimal(str(length_mm)), 1)) if length_mm is not None else None,
            "length_mm_net": float(money(Decimal(str(length_mm_net)), 1)) if length_mm_net is not None else None,
            "width_mm": float(money(Decimal(str(width_c)), 1)) if width_c is not None else None,
            "height_mm": float(money(Decimal(str(height_c)), 1)) if height_c is not None else None,
            "area_sqm": float(money(Decimal(str(area_sqm)), 4)) if area_sqm is not None else None,
            "weight_kg": float(money(Decimal(str(weight_kg)), 3)) if weight_kg is not None else None,
            "unit_of_measure": comp.get("unit_of_measure"),
            "unit_price": float(money(Decimal(str(unit_price)))),
            "unit_cost": float(money(Decimal(str(unit_cost)))),
            "line_measure": float(money(Decimal(str(line_measure)), 4)),
            "line_measure_net": float(money(Decimal(str(line_measure_net)), 4)),
            "line_price": float(money(line_price)),
            "line_cost": float(money(line_cost)),
            "waste_pct": waste_pct,
            "scrap_fixed_mm_per_cut": scrap_fixed_mm_per_cut,
            "scrap_fixed_per_piece": scrap_fixed_per_piece,
            "consumption_mode": consumption_mode,
            "bar_rounding": bar_rounding,
            "min_billable_qty": min_billable_qty,
            "formula_applied": formula_applied,
            "condition_applied": comp.get("condition") or [],
            "is_cutting_relevant": bool(comp.get("is_cutting_relevant", True)),
            "is_customer_visible": bool(comp.get("is_customer_visible", True)),
            "is_optional": bool(comp.get("is_optional", False)),
            "color_category_id": comp.get("color_category_id_override") or color_category_id,
            "color_id": color_id,
            "warnings": row_warnings,
        })

    return {
        "components": resolved,
        "materials_cost": float(money(total_cost)),
        "materials_price": float(money(total_price)),
        "warnings": warnings,
        "blocking_errors": blocking_errors,
    }


def collect_cutting_inputs(resolved_bom: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Estrae dai componenti risolti solo quelli rilevanti per il taglio (profile con lunghezza).
    Ogni entry: {profile_id, length_mm, quantity, role, color_category_id, color_id, bom_component_id}
    """
    out: List[Dict[str, Any]] = []
    for c in resolved_bom.get("components") or []:
        if c.get("component_type") != "profile":
            continue
        if not c.get("is_cutting_relevant", True):
            continue
        if not c.get("length_mm") or c.get("quantity", 0) <= 0:
            continue
        out.append({
            "profile_id": c.get("ref_id"),
            "length_mm": float(c["length_mm"]),
            "quantity": int(round(c["quantity"])) if c["quantity"] >= 1 else 1,
            "role": c.get("role"),
            "color_category_id": c.get("color_category_id"),
            "color_id": c.get("color_id"),
            "bom_component_id": c.get("component_id"),
        })
    return out
