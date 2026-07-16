"""Geometry Engine — Adapter: albero geometrico → input BOM.

Principio: NON è un secondo motore di calcolo. Attraversa il `GeometryTree`,
calcola dimensioni concrete di ogni componente usando `DimensionRuleSet`
versionato + `ProfileSystem.tech` come DEFAULT parameters, poi delega al
motore BOM esistente (`resolve_bom_full`) per prezzi/costi/warning.

Output è LO STESSO formato di `resolve_bom_full` + campi extra:
  - geometry_summary (misure di ogni elemento: telaio_top/bot/left/right,
    ante[], vetri[], montanti[], traversi[]) con formula/detrazione applicata
  - svg (rappresentazione grafica coerente con la geometria)
  - snapshot_hash (include geometry + rules + listini)
  - dimensional_verification (pannello verifica tecnica)
"""
from __future__ import annotations
import hashlib
import json
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.db import get_db
from app.services.bom_engine_v2 import resolve_bom_full


# ---------------------------------------------------------------------------
# Helpers geometria — risoluzione ricorsiva albero → celle terminali
# ---------------------------------------------------------------------------

def _resolve_children_sizes(children: List[Dict[str, Any]], total: float) -> List[float]:
    """Dato una lista di child con size_value/size_unit, calcola sizes assolute
    che sommano a `total`."""
    # 1) separa in {mm, pct, auto}
    mm_total = 0.0
    pct_total = 0.0
    auto_count = 0
    sizes: List[Optional[float]] = []
    for c in children:
        unit = c.get("size_unit", "auto")
        val = c.get("size_value")
        if unit == "mm" and val:
            sizes.append(float(val))
            mm_total += float(val)
        elif unit == "pct" and val:
            sizes.append(None)  # placeholder
            pct_total += float(val)
        else:
            sizes.append(None)
            auto_count += 1
    remaining = max(total - mm_total, 0.0)
    # % applicate su remaining
    pct_alloc = 0.0
    for i, c in enumerate(children):
        if c.get("size_unit") == "pct":
            v = (remaining * (float(c.get("size_value", 0)) / 100.0))
            sizes[i] = v
            pct_alloc += v
    # auto → resto suddiviso equamente
    auto_remaining = max(remaining - pct_alloc, 0.0)
    per_auto = (auto_remaining / auto_count) if auto_count > 0 else 0.0
    for i, s in enumerate(sizes):
        if s is None:
            sizes[i] = per_auto
    return [max(s or 0.0, 0.0) for s in sizes]


def _walk_tree(node: Dict[str, Any], parent_width: float, parent_height: float,
                out_modules: List[Dict[str, Any]], depth: int = 0):
    """Attraversa l'albero e produce lista di moduli terminali con dimensioni assolute.
    parent_width/height sono la BOUNDING BOX del contenitore corrente (mm)."""
    kind = node.get("kind")
    if kind in ("root", "cell"):
        # Se ha un module inline (kind cell con children di 1 module oppure module_type direttamente)
        if kind == "root":
            # root ha typicallly 1 child (split o cell)
            for ch in node.get("children") or []:
                _walk_tree(ch, parent_width, parent_height, out_modules, depth + 1)
            return
        # cell → deve contenere un module (child o inline)
        module_children = [c for c in (node.get("children") or []) if c.get("kind") == "module"]
        if module_children:
            for m in module_children:
                _walk_tree(m, parent_width, parent_height, out_modules, depth + 1)
        elif node.get("module_type"):
            # cell con module inline
            out_modules.append({
                "node_id": node.get("id"),
                "module_type": node.get("module_type"),
                "opening_side": node.get("module_opening_side"),
                "handle_side": node.get("module_handle_side"),
                "hardware_kit_id": node.get("hardware_kit_id"),
                "glass_type_id": node.get("glass_type_id"),
                "color_id": node.get("color_id"),
                "inner_transoms": node.get("inner_transoms", 0),
                "inner_mullions": node.get("inner_mullions", 0),
                "width_mm": parent_width,
                "height_mm": parent_height,
                "label": node.get("label"),
            })
        return
    if kind == "split":
        direction = node.get("direction", "vertical")
        ch = node.get("children") or []
        if direction == "vertical":
            # divide larghezza
            sizes = _resolve_children_sizes(ch, parent_width)
            for child, w in zip(ch, sizes):
                _walk_tree(child, w, parent_height, out_modules, depth + 1)
        else:
            sizes = _resolve_children_sizes(ch, parent_height)
            for child, h in zip(ch, sizes):
                _walk_tree(child, parent_width, h, out_modules, depth + 1)
        return
    if kind == "module":
        out_modules.append({
            "node_id": node.get("id"),
            "module_type": node.get("module_type"),
            "opening_side": node.get("module_opening_side"),
            "handle_side": node.get("module_handle_side"),
            "hardware_kit_id": node.get("hardware_kit_id"),
            "glass_type_id": node.get("glass_type_id"),
            "color_id": node.get("color_id"),
            "inner_transoms": node.get("inner_transoms", 0),
            "inner_mullions": node.get("inner_mullions", 0),
            "width_mm": parent_width,
            "height_mm": parent_height,
            "label": node.get("label"),
        })


# ---------------------------------------------------------------------------
# Verifica dimensionale — per ogni modulo produce dettaglio detrazioni
# ---------------------------------------------------------------------------

def _apply_dimension_rules(
    modules: List[Dict[str, Any]],
    tech: Dict[str, Any],
    rule_set: Optional[Dict[str, Any]],
    outer_L: float, outer_H: float,
) -> Dict[str, Any]:
    """Applica le regole dimensionali e produce:
      - dimension_verification (per ogni elemento: iniziale, detrazione, formula, risultato)
      - aggregated_stats (nr_ante, nr_moduli_fissi, nr_transoms, nr_mullions, area_glass_sqm)
    """
    frame_w = float(tech.get("frame_width_mm", 70))
    central_node = float(tech.get("central_node_mm", 108))
    glass_ded = float(tech.get("glass_deduction_mm", 60))
    kerf = float(tech.get("kerf_mm", 3))

    # Rules per element (semplificato: prendiamo la prima matchante)
    rules_by_element: Dict[str, Dict[str, Any]] = {}
    if rule_set:
        for r in rule_set.get("rules") or []:
            el = r.get("element")
            if el and el not in rules_by_element:
                rules_by_element[el] = r

    verification: List[Dict[str, Any]] = []

    # 1) TELAIO ESTERNO
    for side, dim in [("frame_top", outer_L), ("frame_bottom", outer_L),
                      ("frame_left", outer_H), ("frame_right", outer_H)]:
        rule = rules_by_element.get(side)
        formula = "L (o H) esterno"
        result = dim
        if rule:
            formula = f"{dim} + {rule.get('delta_start_mm', 0)} + {rule.get('delta_end_mm', 0)}"
            result = dim + float(rule.get("delta_start_mm", 0)) + float(rule.get("delta_end_mm", 0))
        verification.append({
            "element": side,
            "input_mm": dim,
            "formula": formula,
            "rule_id": rule.get("id") if rule else None,
            "result_mm": round(result, 1),
            "notes": "misura esterna" if not rule else "detrazione applicata",
        })

    # Luce telaio (dimensioni interne)
    inner_L = outer_L - frame_w * 2
    inner_H = outer_H - frame_w * 2
    verification.append({
        "element": "frame_inner_light",
        "input_mm": outer_L,
        "formula": f"L - frame_width × 2 = {outer_L} - {frame_w*2}",
        "rule_id": None,
        "result_mm": round(inner_L, 1),
        "notes": "luce interna telaio",
    })
    verification.append({
        "element": "frame_inner_light_H",
        "input_mm": outer_H,
        "formula": f"H - frame_width × 2 = {outer_H} - {frame_w*2}",
        "rule_id": None,
        "result_mm": round(inner_H, 1),
        "notes": "luce interna telaio (altezza)",
    })

    # 2) MODULI
    ante_moduli = [m for m in modules if (m.get("module_type") or "").startswith("sash")]
    fixed_moduli = [m for m in modules if (m.get("module_type") or "") in ("fixed", "glass_fixed", "panel", "top_light", "bottom_light", "side_light")]
    nr_ante = len(ante_moduli)
    nr_fissi = len(fixed_moduli)
    total_glass_sqm = 0.0

    for i, m in enumerate(modules):
        mtype = m.get("module_type")
        cell_L = float(m.get("width_mm", 0))
        cell_H = float(m.get("height_mm", 0))
        label = m.get("label") or f"Modulo {i+1}"

        # Se è anta → sottrai battute/nodo per luce anta
        if (mtype or "").startswith("sash"):
            sash_rule = rules_by_element.get("sash_frame")
            delta = float(sash_rule.get("delta_start_mm", 0)) + float(sash_rule.get("delta_end_mm", 0)) if sash_rule else 0
            sash_w = cell_L + delta
            sash_h = cell_H + delta
            verification.append({
                "element": f"sash_frame[{i}]",
                "input_mm": cell_L,
                "formula": f"cell_L + delta ({delta})",
                "rule_id": sash_rule.get("id") if sash_rule else None,
                "result_mm": round(sash_w, 1),
                "notes": f"{label} (anta)",
            })
            # vetro su anta
            glass_rule = rules_by_element.get("glass_on_sash")
            g_delta = float(glass_rule.get("delta_start_mm", 0)) + float(glass_rule.get("delta_end_mm", 0)) if glass_rule else -glass_ded
            glass_w = sash_w + g_delta
            glass_h = sash_h + g_delta
            glass_sqm = max(0.0, glass_w * glass_h / 1_000_000)
            total_glass_sqm += glass_sqm
            verification.append({
                "element": f"glass_on_sash[{i}]",
                "input_mm": sash_w,
                "formula": f"sash + delta ({g_delta})",
                "rule_id": glass_rule.get("id") if glass_rule else None,
                "result_mm": round(glass_w, 1),
                "result_mm_h": round(glass_h, 1),
                "area_sqm": round(glass_sqm, 3),
                "notes": f"vetro anta {label}",
            })
        elif (mtype or "") in ("fixed", "glass_fixed", "top_light", "bottom_light", "side_light"):
            # vetro su fisso
            glass_rule = rules_by_element.get("glass_on_fixed")
            g_delta = float(glass_rule.get("delta_start_mm", 0)) + float(glass_rule.get("delta_end_mm", 0)) if glass_rule else -glass_ded
            glass_w = cell_L + g_delta
            glass_h = cell_H + g_delta
            glass_sqm = max(0.0, glass_w * glass_h / 1_000_000)
            total_glass_sqm += glass_sqm
            verification.append({
                "element": f"glass_on_fixed[{i}]",
                "input_mm": cell_L,
                "formula": f"cell + delta ({g_delta})",
                "rule_id": glass_rule.get("id") if glass_rule else None,
                "result_mm": round(glass_w, 1),
                "result_mm_h": round(glass_h, 1),
                "area_sqm": round(glass_sqm, 3),
                "notes": f"vetro fisso {label}",
            })
        elif mtype == "panel":
            verification.append({
                "element": f"panel[{i}]",
                "input_mm": cell_L,
                "formula": "pannello — nessuna detrazione vetro",
                "rule_id": None,
                "result_mm": round(cell_L, 1),
                "notes": label,
            })

    aggregated = {
        "nr_ante": nr_ante,
        "nr_fissi": nr_fissi,
        "nr_moduli_totali": nr_ante + nr_fissi,
        "total_glass_sqm": round(total_glass_sqm, 3),
        "frame_width_mm": frame_w,
        "central_node_mm": central_node,
        "glass_deduction_mm": glass_ded,
    }
    return {"verification": verification, "aggregated": aggregated}


# ---------------------------------------------------------------------------
# SVG rendering (semplice ma coerente con l'albero)
# ---------------------------------------------------------------------------

def _render_svg(tree: Dict[str, Any], modules: List[Dict[str, Any]]) -> str:
    """Rende SVG del serramento coerente con l'albero. Colori diversi per anta/fisso."""
    L = tree.get("outer_width_mm", 1200)
    H = tree.get("outer_height_mm", 1400)
    # scala per fit 400x400
    scale = min(400 / L, 400 / H)
    svg_w = int(L * scale) + 20
    svg_h = int(H * scale) + 20
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<style>.frame{fill:#e6e6e6;stroke:#333;stroke-width:2}.sash{fill:#c8e8ff;stroke:#0066cc;stroke-width:1.5}.fixed{fill:#f0f8e6;stroke:#3a8a3a;stroke-width:1.5}.glass{fill:#e0f0ff;fill-opacity:0.6}.label{font:11px sans-serif;fill:#333}</style>',
        f'<rect x="10" y="10" width="{int(L*scale)}" height="{int(H*scale)}" class="frame"/>',
    ]
    # posizione moduli — approssimata dal walk
    # Per semplicità: layout a griglia dei moduli in ordine di walk
    # (per un vero placement servirebbe il tracking coordinate durante walk; ok per v1)
    n = len(modules)
    if n > 0:
        # rilevo se root è split verticale/orizzontale primario
        root = tree.get("root", {})
        first_split = root
        if root.get("kind") == "root" and root.get("children"):
            first_split = root["children"][0]
        direction = first_split.get("direction", "vertical") if first_split.get("kind") == "split" else "vertical"

        if direction == "vertical":
            x = 10
            for m in modules:
                w = m.get("width_mm", L / n) * scale
                cls = "sash" if (m.get("module_type") or "").startswith("sash") else "fixed"
                parts.append(f'<rect x="{int(x)}" y="10" width="{int(w)}" height="{int(H*scale)}" class="{cls}"/>')
                # vetro interno
                parts.append(f'<rect x="{int(x+10)}" y="20" width="{max(int(w-20),1)}" height="{max(int(H*scale-20),1)}" class="glass"/>')
                if m.get("label"):
                    parts.append(f'<text x="{int(x+w/2)}" y="{int(H*scale/2)}" text-anchor="middle" class="label">{m["label"][:16]}</text>')
                x += w
        else:
            y = 10
            for m in modules:
                h = m.get("height_mm", H / n) * scale
                cls = "sash" if (m.get("module_type") or "").startswith("sash") else "fixed"
                parts.append(f'<rect x="10" y="{int(y)}" width="{int(L*scale)}" height="{int(h)}" class="{cls}"/>')
                parts.append(f'<rect x="20" y="{int(y+10)}" width="{max(int(L*scale-20),1)}" height="{max(int(h-20),1)}" class="glass"/>')
                if m.get("label"):
                    parts.append(f'<text x="{int(L*scale/2)}" y="{int(y+h/2)}" text-anchor="middle" class="label">{m["label"][:16]}</text>')
                y += h
    parts.append('</svg>')
    return "".join(parts)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def compute_geometry(
    *,
    tenant_id: str,
    geometry: Dict[str, Any],
    bom_template_id: str,
    sell_pricelist_id: Optional[str] = None,
    cost_pricelist_id: Optional[str] = None,
    include_costs: bool = True,
    include_svg: bool = True,
) -> Dict[str, Any]:
    """Compute completo: geometry → dimensioni → BOM → prezzo → SVG → snapshot."""
    db = get_db()
    ps = await db.profile_systems.find_one({
        "_id": geometry.get("profile_system_id"),
        "tenant_id": tenant_id, "deleted_at": None,
    })
    if not ps:
        return {
            "errors": ["Sistema profilo geometria non trovato"],
            "components": [], "geometry_summary": {}, "svg": None,
        }
    tech = ps.get("tech") or {}

    # Regole dimensionali versionate
    rule_set = None
    if geometry.get("dimension_rule_set_id"):
        rule_set = await db.dimension_rule_sets.find_one({
            "_id": geometry["dimension_rule_set_id"],
            "tenant_id": tenant_id, "deleted_at": None,
        })
    else:
        # Cerca default per il profile_system
        rule_set = await db.dimension_rule_sets.find_one({
            "tenant_id": tenant_id, "profile_system_id": geometry["profile_system_id"],
            "is_default": True, "rs_status": "active", "deleted_at": None,
        })

    # 1) Attraversa albero → lista moduli con dimensioni concrete
    modules: List[Dict[str, Any]] = []
    outer_L = float(geometry.get("outer_width_mm", 0))
    outer_H = float(geometry.get("outer_height_mm", 0))
    root = geometry.get("root") or {}
    # Il root ha children? Assumiamo root come contenitore, walk i figli
    if root.get("children"):
        for ch in root["children"]:
            _walk_tree(ch, outer_L - 2 * float(tech.get("frame_width_mm", 70)),
                       outer_H - 2 * float(tech.get("frame_width_mm", 70)),
                       modules)
    elif root.get("module_type"):
        modules.append({
            "node_id": root.get("id"), "module_type": root["module_type"],
            "width_mm": outer_L - 2 * float(tech.get("frame_width_mm", 70)),
            "height_mm": outer_H - 2 * float(tech.get("frame_width_mm", 70)),
            "label": root.get("label"),
        })

    # 2) Applica regole dimensionali → verification report + aggregated
    dim_report = _apply_dimension_rules(modules, tech, rule_set, outer_L, outer_H)
    agg = dim_report["aggregated"]

    # 3) Costruisce params per resolve_bom_full (motore BOM esistente)
    # Convenzione: mappiamo aggregati sui parametri classici del BOM (compat retro)
    bom_params = {
        "width_mm": int(outer_L),
        "height_mm": int(outer_H),
        "nr_ante": agg["nr_ante"],
        "nr_fissi": agg["nr_fissi"],
        "nr_traversi": sum(int(m.get("inner_transoms", 0)) for m in modules),
        "nr_montanti": sum(int(m.get("inner_mullions", 0)) for m in modules),
        "color_category_id": geometry.get("color_category_id"),
        "color_id": geometry.get("color_id"),
        # primo hardware_kit trovato tra i moduli sash
        "hardware_kit_id": next(
            (m.get("hardware_kit_id") for m in modules
             if (m.get("module_type") or "").startswith("sash") and m.get("hardware_kit_id")),
            None,
        ),
        "glass_type_id": next(
            (m.get("glass_type_id") for m in modules if m.get("glass_type_id")),
            None,
        ),
    }

    # 4) Delega al motore BOM esistente (NESSUN secondo motore)
    bom_result = await resolve_bom_full(
        tenant_id=tenant_id,
        bom_template_id=bom_template_id,
        params=bom_params,
        sell_pricelist_id=sell_pricelist_id,
        cost_pricelist_id=cost_pricelist_id if include_costs else None,
        include_costs=include_costs,
    )

    # 5) SVG
    svg = _render_svg(geometry, modules) if include_svg else None

    # 6) Snapshot hash esteso (geometria + regole + BOM snapshot + listini)
    snap = {
        "geometry": geometry,
        "profile_system_version": ps.get("version"),
        "dimension_rule_set_id": (rule_set or {}).get("_id"),
        "dimension_rule_set_version": (rule_set or {}).get("version"),
        "bom_template_id": bom_template_id,
        "bom_snapshot_hash": bom_result.get("snapshot_hash"),
        "sell_pricelist_id": sell_pricelist_id,
        "cost_pricelist_id": cost_pricelist_id,
        "outer_width_mm": outer_L,
        "outer_height_mm": outer_H,
    }
    snap_j = json.dumps(snap, sort_keys=True, default=str, separators=(",", ":"))
    snapshot_hash = hashlib.sha256(snap_j.encode("utf-8")).hexdigest()

    return {
        **bom_result,
        "geometry_summary": {
            "outer_width_mm": outer_L,
            "outer_height_mm": outer_H,
            "modules": modules,
            "aggregated": agg,
            "dimension_verification": dim_report["verification"],
            "dimension_rule_set_id": (rule_set or {}).get("_id"),
            "dimension_rule_set_version": (rule_set or {}).get("version"),
            "profile_system_id": ps.get("_id"),
            "profile_system_version": ps.get("version"),
        },
        "svg": svg,
        "geometry_snapshot_hash": snapshot_hash,
    }
