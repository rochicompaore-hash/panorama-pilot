"""1D Bar Nesting / Cutting Stock — FFD + BFD + comparison.

Input: lista di tagli richiesti { profile_id, color_category_id, length_mm, quantity, ... }
Output: lista di barre, ciascuna con: cuts, used_mm, waste_mm, reusable_scrap_mm, efficiency_pct.

Regole:
- Ogni taglio "consuma" length_mm + kerf_mm (larghezza lama sottrae materiale).
- head_offcut_mm e tail_offcut_mm sono aree non usabili per barra.
- Un residuo ≥ min_reusable_scrap_mm viene marcato come scrap riutilizzabile (non waste).
- Compatibilità aggregazione: stesso profile_id + stesso color_category_id + stesso bar_length_mm
  (color_id/lot/finish possono restringere ulteriormente, gestito dal chiamante).
- respect_order_isolation=true → non aggregare cuts di ordini diversi (Cat.2/Cat.3 tipico).

Algoritmi:
- FFD (First Fit Decreasing): ordina i tagli in ordine decrescente, li assegna alla PRIMA barra
  in cui entrano; se nessuna, apre una nuova barra.
- BFD (Best Fit Decreasing): assegna alla barra con MENO spazio residuo che ancora consenta il taglio.

auto_best: esegue entrambi e ritorna il risultato con efficienza superiore
           (a parità di barre, minor waste).
"""
from __future__ import annotations
import time
from typing import Any, Dict, List, Optional, Tuple


def _group_key(cut: Dict[str, Any]) -> Tuple:
    return (
        cut.get("profile_id"),
        cut.get("color_category_id"),
        cut.get("color_id"),
        cut.get("lot") or None,
        cut.get("bar_length_mm") or None,
    )


def _expand_quantities(cuts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for c in cuts:
        q = int(c.get("quantity") or 1)
        for i in range(q):
            oc = dict(c)
            oc["quantity"] = 1
            oc["_seq"] = i
            out.append(oc)
    return out


def _new_bar(profile_id, color_id, color_category_id, bar_length_mm, kerf_mm, head_off, tail_off, cost_bar) -> Dict[str, Any]:
    usable = bar_length_mm - head_off - tail_off
    return {
        "profile_id": profile_id,
        "color_id": color_id,
        "color_category_id": color_category_id,
        "bar_length_mm": bar_length_mm,
        "kerf_mm": kerf_mm,
        "head_offcut_mm": head_off,
        "tail_offcut_mm": tail_off,
        "usable_mm": usable,
        "remaining_mm": usable,
        "cuts": [],
        "used_mm": 0.0,
        "cost_bar": cost_bar,
    }


def _fits(bar: Dict[str, Any], length_mm: float) -> bool:
    # Ogni taglio successivo sottrae kerf (tranne il primo)
    kerf = bar["kerf_mm"] if bar["cuts"] else 0
    return (length_mm + kerf) <= bar["remaining_mm"] + 1e-6


def _place(bar: Dict[str, Any], cut: Dict[str, Any]) -> None:
    kerf = bar["kerf_mm"] if bar["cuts"] else 0
    length = float(cut["length_mm"])
    bar["cuts"].append(cut)
    bar["used_mm"] += length + kerf
    bar["remaining_mm"] -= (length + kerf)


def _finalize_bar(bar: Dict[str, Any], min_reusable: float) -> Dict[str, Any]:
    total_usable = bar["usable_mm"]
    used = bar["used_mm"]
    remaining = max(0.0, total_usable - used)
    reusable = remaining if remaining >= min_reusable else 0.0
    waste = remaining - reusable
    efficiency = round((used / total_usable) * 100, 2) if total_usable > 0 else 0.0
    bar["waste_mm"] = round(waste, 2)
    bar["reusable_scrap_mm"] = round(reusable, 2)
    bar["efficiency_pct"] = efficiency
    return bar


def _ffd(cuts: List[Dict[str, Any]], profile_meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    cuts_sorted = sorted(cuts, key=lambda c: -float(c["length_mm"]))
    bars: List[Dict[str, Any]] = []
    for c in cuts_sorted:
        placed = False
        for bar in bars:
            if _fits(bar, float(c["length_mm"])):
                _place(bar, c)
                placed = True
                break
        if not placed:
            bar = _new_bar(**profile_meta)
            if not _fits(bar, float(c["length_mm"])):
                # Taglio più lungo della barra: warning tramite eccezione
                raise ValueError(f"Taglio {c['length_mm']}mm > barra utile {bar['usable_mm']}mm (profile {c.get('profile_id')})")
            _place(bar, c)
            bars.append(bar)
    return bars


def _bfd(cuts: List[Dict[str, Any]], profile_meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    cuts_sorted = sorted(cuts, key=lambda c: -float(c["length_mm"]))
    bars: List[Dict[str, Any]] = []
    for c in cuts_sorted:
        best = None
        best_rem = None
        length = float(c["length_mm"])
        for bar in bars:
            if _fits(bar, length):
                kerf = bar["kerf_mm"] if bar["cuts"] else 0
                rem_after = bar["remaining_mm"] - (length + kerf)
                if best is None or rem_after < best_rem:
                    best = bar
                    best_rem = rem_after
        if best is not None:
            _place(best, c)
        else:
            bar = _new_bar(**profile_meta)
            if not _fits(bar, length):
                raise ValueError(f"Taglio {length}mm > barra utile {bar['usable_mm']}mm (profile {c.get('profile_id')})")
            _place(bar, c)
            bars.append(bar)
    return bars


def _summarize(bars: List[Dict[str, Any]], min_reusable: float) -> Dict[str, Any]:
    for b in bars:
        _finalize_bar(b, min_reusable)
    total_bars = len(bars)
    total_used = sum(b["used_mm"] for b in bars)
    total_waste = sum(b["waste_mm"] for b in bars)
    total_reusable = sum(b["reusable_scrap_mm"] for b in bars)
    total_usable = sum(b["usable_mm"] for b in bars)
    eff = round((total_used / total_usable) * 100, 2) if total_usable > 0 else 0.0
    total_cost = sum(b["cost_bar"] for b in bars)
    return {
        "bars": bars,
        "total_bars": total_bars,
        "total_used_mm": round(total_used, 2),
        "total_waste_mm": round(total_waste, 2),
        "total_reusable_scrap_mm": round(total_reusable, 2),
        "efficiency_pct": eff,
        "total_cost": round(total_cost, 2),
    }


def optimize(
    cuts: List[Dict[str, Any]],
    *,
    algorithm: str = "auto_best",
    profile_defaults: Optional[Dict[Tuple, Dict[str, Any]]] = None,
    default_bar_length_mm: int = 6500,
    default_kerf_mm: float = 3.0,
    default_head_offcut_mm: float = 50.0,
    default_tail_offcut_mm: float = 50.0,
    default_min_reusable_mm: float = 400.0,
    default_bar_cost: float = 0.0,
    respect_order_isolation: bool = False,
) -> Dict[str, Any]:
    """Esegue l'ottimizzazione 1D. Restituisce dict con bars aggregate per (profile, color, order)."""
    started = time.time()
    warnings: List[str] = []
    expanded = _expand_quantities(cuts)
    # Se richiesto: isola per ordine
    all_bars: List[Dict[str, Any]] = []
    used_algorithm = algorithm

    def _run(alg: str, group_cuts: List[Dict[str, Any]], meta: Dict[str, Any]) -> List[Dict[str, Any]]:
        if alg == "ffd":
            return _ffd(group_cuts, meta)
        if alg == "bfd":
            return _bfd(group_cuts, meta)
        # auto_best
        try:
            a = _summarize([b.copy() for b in _ffd(group_cuts, meta)], meta.get("min_reusable", default_min_reusable_mm))
            b = _summarize([b.copy() for b in _bfd(group_cuts, meta)], meta.get("min_reusable", default_min_reusable_mm))
            # scegli meno barre; tie-break: minor waste
            if b["total_bars"] < a["total_bars"] or (
                b["total_bars"] == a["total_bars"] and b["total_waste_mm"] < a["total_waste_mm"]
            ):
                return b["bars"]
            return a["bars"]
        except Exception:
            return _ffd(group_cuts, meta)

    # Raggruppa per compatibilità
    groups: Dict[Tuple, List[Dict[str, Any]]] = {}
    for c in expanded:
        gk = _group_key(c)
        if respect_order_isolation:
            gk = gk + (c.get("from_order_id"),)
        groups.setdefault(gk, []).append(c)

    min_reusable_per_bar = default_min_reusable_mm
    for gk, group in groups.items():
        pkey = (gk[0], gk[1], gk[2])  # profile_id, color_category_id, color_id
        pdef = (profile_defaults or {}).get(pkey) or {}
        bar_length = int(pdef.get("bar_length_mm") or gk[4] or default_bar_length_mm)
        kerf = float(pdef.get("kerf_mm") or default_kerf_mm)
        head = float(pdef.get("head_offcut_mm") or default_head_offcut_mm)
        tail = float(pdef.get("tail_offcut_mm") or default_tail_offcut_mm)
        min_reusable = float(pdef.get("min_reusable_mm") or default_min_reusable_mm)
        bar_cost = float(pdef.get("bar_cost") or default_bar_cost)
        meta = {
            "profile_id": gk[0], "color_id": gk[2], "color_category_id": gk[1],
            "bar_length_mm": bar_length, "kerf_mm": kerf,
            "head_off": head, "tail_off": tail, "cost_bar": bar_cost,
        }
        try:
            bars = _run(algorithm, group, meta)
            for bar in bars:
                bar.setdefault("kerf_mm", kerf)
                bar.setdefault("head_offcut_mm", head)
                bar.setdefault("tail_offcut_mm", tail)
                _finalize_bar(bar, min_reusable)
            all_bars.extend(bars)
        except ValueError as e:
            warnings.append(str(e))

    summary = _summarize(all_bars, min_reusable_per_bar)
    summary["algorithm"] = used_algorithm
    summary["runtime_ms"] = int((time.time() - started) * 1000)
    summary["warnings"] = warnings
    return summary


def compare_algorithms(cuts, **kwargs) -> Dict[str, Any]:
    """Confronta FFD e BFD. Utile per audit/UI."""
    ffd = optimize(cuts, **{**kwargs, "algorithm": "ffd"})
    bfd = optimize(cuts, **{**kwargs, "algorithm": "bfd"})
    winner = "ffd" if (ffd["total_bars"], ffd["total_waste_mm"]) <= (bfd["total_bars"], bfd["total_waste_mm"]) else "bfd"
    return {"ffd": ffd, "bfd": bfd, "winner": winner}
