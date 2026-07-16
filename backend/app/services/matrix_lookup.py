"""Price Matrix lookup — Modalità A.

Supporta:
- nearest_up: sceglie la prima cella (w', h') con w' >= w AND h' >= h  ⇒  prudente
- nearest: sceglie la cella con distanza euclidea minima
- linear: interpolazione bilineare sulle 4 celle adiacenti

Fuori matrice:
- allow_extrapolation=false → warning + fallback su cella massima + oversize_surcharge_pct
- allow_extrapolation=true  → nearest_up esteso oltre il massimo (uso in casi speciali)
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple


def _cell_map(cells: List[Dict[str, Any]]) -> Dict[Tuple[int, int], float]:
    return {(int(c["width_mm"]), int(c["height_mm"])): float(c["price"]) for c in cells}


def _find_next_up(sorted_values: List[int], target: int) -> Optional[int]:
    for v in sorted_values:
        if v >= target:
            return v
    return None


def _find_bracket(sorted_values: List[int], target: int) -> Tuple[Optional[int], Optional[int]]:
    """Ritorna (lower, upper): valori adiacenti che contengono target."""
    lower = None
    upper = None
    for v in sorted_values:
        if v <= target:
            lower = v
        if v >= target and upper is None:
            upper = v
    return lower, upper


def lookup_price(
    matrix: Dict[str, Any],
    width_mm: int,
    height_mm: int,
) -> Dict[str, Any]:
    """Ritorna dict con price, method, warnings, explanation.
    Solleva ValueError solo se la matrice è vuota."""
    widths = sorted({int(w) for w in matrix.get("widths_mm") or []})
    heights = sorted({int(h) for h in matrix.get("heights_mm") or []})
    cells = matrix.get("cells") or []
    if not widths or not heights or not cells:
        raise ValueError("Matrice prezzi vuota o non valida")
    cmap = _cell_map(cells)

    warnings: List[str] = []
    interpolation = matrix.get("interpolation", "nearest_up")
    max_w = max(widths)
    max_h = max(heights)
    min_w = min(widths)
    min_h = min(heights)
    over = float(matrix.get("oversize_surcharge_pct", 0) or 0)
    allow_extrap = bool(matrix.get("allow_extrapolation"))

    # Fuori scala
    oversize = False
    if width_mm > max_w or height_mm > max_h:
        oversize = True
        if not allow_extrap:
            warnings.append(f"Fuori matrice ({width_mm}x{height_mm}) — applicato max ({max_w}x{max_h}) + rincaro {over}%")

    if interpolation == "linear" and not oversize:
        lw, uw = _find_bracket(widths, width_mm)
        lh, uh = _find_bracket(heights, height_mm)
        if lw is None or uw is None or lh is None or uh is None:
            interpolation = "nearest_up"  # fallback
        else:
            p11 = cmap.get((lw, lh))
            p12 = cmap.get((lw, uh))
            p21 = cmap.get((uw, lh))
            p22 = cmap.get((uw, uh))
            if None in (p11, p12, p21, p22):
                interpolation = "nearest_up"
            else:
                # bilinear
                if uw == lw:
                    xr = 0.0
                else:
                    xr = (width_mm - lw) / (uw - lw)
                if uh == lh:
                    yr = 0.0
                else:
                    yr = (height_mm - lh) / (uh - lh)
                p = (
                    p11 * (1 - xr) * (1 - yr)
                    + p21 * xr * (1 - yr)
                    + p12 * (1 - xr) * yr
                    + p22 * xr * yr
                )
                return {
                    "price": round(p, 2),
                    "method": "linear",
                    "widths_used": [lw, uw],
                    "heights_used": [lh, uh],
                    "warnings": warnings,
                    "explanation": f"Interp. bilineare tra ({lw},{lh})={p11} ({uw},{lh})={p21} ({lw},{uh})={p12} ({uw},{uh})={p22}",
                }

    # nearest_up (default & fallback)
    tw = min(width_mm, max_w)
    th = min(height_mm, max_h)
    up_w = _find_next_up(widths, tw) or max_w
    up_h = _find_next_up(heights, th) or max_h
    price = cmap.get((up_w, up_h))
    if price is None:
        # cella mancante → prendi la più grande disponibile
        price = max(cmap.values())
        warnings.append(f"Cella ({up_w}, {up_h}) non trovata — usato prezzo massimo")
    if oversize:
        price = price * (1 + over / 100.0)
    if interpolation == "nearest":
        # più vicina (distanza rettilinea normalizzata)
        best = None
        best_d = None
        for (w, h), p in cmap.items():
            d = abs(w - width_mm) + abs(h - height_mm)
            if best_d is None or d < best_d:
                best_d = d
                best = (w, h, p)
        if best:
            return {
                "price": round(best[2] * (1 + over / 100.0 if oversize else 1), 2),
                "method": "nearest",
                "widths_used": [best[0]],
                "heights_used": [best[1]],
                "warnings": warnings,
                "explanation": f"Cella più vicina ({best[0]},{best[1]})={best[2]}",
            }
    return {
        "price": round(price, 2),
        "method": "nearest_up" + (" (oversize)" if oversize else ""),
        "widths_used": [up_w],
        "heights_used": [up_h],
        "warnings": warnings,
        "explanation": f"Nearest-up alla cella ({up_w},{up_h})",
    }
