"""Color Scrap Policy — logica finanziaria residui per Categoria colore.

Categoria 1 (global_reuse) — residuo riusabile globalmente. Il costo viene ripartito
    tra i tagli in proporzione all'utilizzo. Il residuo va in magazzino "generico".

Categoria 2 (order_reuse) — residuo riusabile solo entro lo stesso ordine.
    Costo ripartito nell'ordine.

Categoria 3 (order_full_cost) — cliente paga la BARRA INTERA.
    Residuo va in magazzino (per riuso futuro), ma il costo era già coperto.
    Il valore residuo di magazzino è > 0 se riutilizzabile, ma il "costo netto"
    per l'azienda è 0 (già ammortizzato).

Ogni policy determina:
- cost_attribution: come attribuire il costo di ogni barra ai tagli (proporzionale | intero)
- create_scrap_stock: se creare un ScrapStock per il residuo
- residual_book_value: valore contabile del residuo (originale, zero, o parziale)
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional


def apply_scrap_policy(
    bar: Dict[str, Any],
    color_category: Dict[str, Any],
    *,
    cost_per_bar: float,
) -> Dict[str, Any]:
    """Restituisce dict con:
        - cost_charged_total: costo attribuito ai tagli (€, cumulato)
        - cost_charged_by_cut: mappa cut_id → € attribuito
        - create_scrap_stock: bool
        - scrap_original_cost: costo industriale del residuo (informativo)
        - scrap_charged_cost: costo già addebitato al cliente originale
        - scrap_residual_book_value: valore contabile residuo
        - reuse_policy: policy riuso residuo
        - notes: descrizione umana della logica applicata
    """
    scrap_mode = (color_category or {}).get("scrap_mode", "global_reuse")
    charges_whole_bar = bool((color_category or {}).get("charges_whole_bar")) or scrap_mode == "order_full_cost"
    reuse_policy = (color_category or {}).get("scrap_reuse_policy", "same_color_any_compatible_profile")
    usable_mm = float(bar.get("usable_mm") or 0)
    used_mm = float(bar.get("used_mm") or 0)
    reusable_mm = float(bar.get("reusable_scrap_mm") or 0)
    waste_mm = float(bar.get("waste_mm") or 0)
    cuts = bar.get("cuts") or []

    cost_by_cut: Dict[str, float] = {}
    if charges_whole_bar:
        # Cat.3: cliente paga la barra intera. Ripartizione tra i tagli in proporzione a lunghezza.
        # (Se la barra è single-order, alla fine il totale è sempre = cost_per_bar.)
        total_len = sum(float(c["length_mm"]) for c in cuts) or used_mm or 1.0
        for c in cuts:
            cid = c.get("id") or c.get("bom_component_id") or "cut"
            share = float(c["length_mm"]) / total_len
            cost_by_cut[cid] = round(cost_per_bar * share, 2)
        cost_charged_total = round(cost_per_bar, 2)
        # Il residuo è già stato pagato → valore contabile residuo = 0 (o parziale se policy)
        scrap_book_value = 0.0
        note = (
            f"Cat.3 (order_full_cost): cliente paga barra intera €{cost_per_bar}. "
            f"Residuo {reusable_mm}mm già ammortizzato, magazzino con costo netto 0."
        )
        return {
            "cost_charged_total": cost_charged_total,
            "cost_charged_by_cut": cost_by_cut,
            "create_scrap_stock": reusable_mm > 0 and reuse_policy != "non_reusable",
            "scrap_original_cost": round(cost_per_bar * (reusable_mm / usable_mm) if usable_mm > 0 else 0, 2),
            "scrap_charged_cost": round(cost_per_bar * (reusable_mm / usable_mm) if usable_mm > 0 else 0, 2),
            "scrap_residual_book_value": scrap_book_value,
            "reuse_policy": reuse_policy,
            "notes": note,
        }
    # Cat.1 / Cat.2: costo proporzionale all'utilizzo
    ratio_used = (used_mm / usable_mm) if usable_mm > 0 else 0
    cost_charged_total = round(cost_per_bar * ratio_used, 2)
    total_len = sum(float(c["length_mm"]) for c in cuts) or used_mm or 1.0
    for c in cuts:
        cid = c.get("id") or c.get("bom_component_id") or "cut"
        share = float(c["length_mm"]) / total_len
        cost_by_cut[cid] = round(cost_charged_total * share, 2)
    # Residuo: valore contabile = costo industriale della porzione residua
    scrap_original = round(cost_per_bar * (reusable_mm / usable_mm) if usable_mm > 0 else 0, 2)
    scrap_book_value = scrap_original  # non ancora addebitato
    if scrap_mode == "order_reuse":
        note = (
            f"Cat.2 (order_reuse): costo ripartito proporzionalmente. "
            f"Residuo {reusable_mm}mm riutilizzabile solo nello stesso ordine."
        )
    else:
        note = (
            f"Cat.1 (global_reuse): costo ripartito proporzionalmente. "
            f"Residuo {reusable_mm}mm entra in magazzino generico compatibile."
        )
    return {
        "cost_charged_total": cost_charged_total,
        "cost_charged_by_cut": cost_by_cut,
        "create_scrap_stock": reusable_mm > 0 and reuse_policy != "non_reusable",
        "scrap_original_cost": scrap_original,
        "scrap_charged_cost": 0.0,           # cliente non ha ancora pagato per il residuo
        "scrap_residual_book_value": scrap_book_value,
        "reuse_policy": reuse_policy,
        "notes": note,
    }
