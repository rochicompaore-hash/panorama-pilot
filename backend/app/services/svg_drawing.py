"""Safe SVG drawing generator per serramenti.

Genera SVG server-side utilizzando SOLO elementi whitelist:
  rect, line, path, polygon, polyline, text, g, defs, marker, title, desc, style

VIETATI: script, iframe, foreignObject, event handlers (onXxx), href esterni, url() esterni.

Il generatore NON accetta stringhe utente: costruisce l'SVG programmaticamente da
parametri numerici e stringhe validate.
"""
from __future__ import annotations
import re
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape as xml_escape

_SAFE_TEXT_RE = re.compile(r"[^\w\s\-\.\+°%,/]")


def _safe_text(s: str, max_len: int = 100) -> str:
    if not s:
        return ""
    s = str(s)[:max_len]
    s = _SAFE_TEXT_RE.sub(" ", s)
    return xml_escape(s)


def _fmt(n: float) -> str:
    if abs(n - round(n)) < 1e-6:
        return str(int(round(n)))
    return f"{n:.2f}"


def draw_window(
    *,
    product_key: str,
    width_mm: int,
    height_mm: int,
    nr_ante: int = 1,
    nr_traversi: int = 0,
    nr_montanti: int = 0,
    show_dimensions: bool = True,
    show_opening_arrows: bool = True,
    frame_color: str = "#0F1720",
    glass_color: str = "#E8F1F7",
    accent_color: str = "#D42027",
    dim_color: str = "#666666",
    frame_thickness: int = 70,
    scale: float = 1.0,
) -> str:
    """Ritorna una stringa SVG rappresentativa (schematica) del serramento."""
    # Viewport: aggiungiamo margine per quote esterne
    margin = 90 if show_dimensions else 30
    scale_factor = min(600.0 / width_mm, 600.0 / height_mm) * scale
    view_w = int(width_mm * scale_factor + margin * 2)
    view_h = int(height_mm * scale_factor + margin * 2)
    x0 = margin
    y0 = margin
    W = width_mm * scale_factor
    H = height_mm * scale_factor
    ft = max(6, int(frame_thickness * scale_factor))  # spessore telaio in px
    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {view_w} {view_h}" '
        f'width="100%" preserveAspectRatio="xMidYMid meet" '
        f'style="max-width:100%;background:#FAFAFA;font-family:Georgia,serif" '
        f'data-parametric-svg="1" data-product="{_safe_text(product_key, 40)}">'
    )
    # Definitions (marker frecce)
    parts.append(
        '<defs><marker id="arr" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">'
        f'<path d="M0,0 L8,4 L0,8 z" fill="{dim_color}"/></marker></defs>'
    )
    parts.append(f'<title>{_safe_text(product_key)} {width_mm}x{height_mm}mm</title>')
    # TELAIO esterno
    parts.append(
        f'<rect x="{x0}" y="{y0}" width="{_fmt(W)}" height="{_fmt(H)}" '
        f'fill="none" stroke="{frame_color}" stroke-width="{ft}"/>'
    )
    # AREA VETRO interna
    inner_x = x0 + ft
    inner_y = y0 + ft
    inner_w = W - 2 * ft
    inner_h = H - 2 * ft
    parts.append(
        f'<rect x="{_fmt(inner_x)}" y="{_fmt(inner_y)}" width="{_fmt(inner_w)}" height="{_fmt(inner_h)}" '
        f'fill="{glass_color}" stroke="{frame_color}" stroke-width="1"/>'
    )
    # MONTANTI/ANTE
    n_ante = max(1, int(nr_ante))
    if n_ante > 1:
        # divisioni verticali (montanti tra ante)
        seg = inner_w / n_ante
        for i in range(1, n_ante):
            xm = inner_x + i * seg
            parts.append(
                f'<line x1="{_fmt(xm)}" y1="{_fmt(inner_y)}" x2="{_fmt(xm)}" y2="{_fmt(inner_y + inner_h)}" '
                f'stroke="{frame_color}" stroke-width="{max(3, int(ft*0.6))}"/>'
            )
    n_tras = max(0, int(nr_traversi))
    if n_tras > 0:
        seg = inner_h / (n_tras + 1)
        for i in range(1, n_tras + 1):
            ym = inner_y + i * seg
            parts.append(
                f'<line x1="{_fmt(inner_x)}" y1="{_fmt(ym)}" x2="{_fmt(inner_x + inner_w)}" y2="{_fmt(ym)}" '
                f'stroke="{frame_color}" stroke-width="{max(3, int(ft*0.6))}"/>'
            )
    # FRECCE APERTURA (schema): triangolo diagonale su ogni anta
    if show_opening_arrows and n_ante >= 1 and product_key not in ("fixed", "window_fixed"):
        seg = inner_w / n_ante
        for i in range(n_ante):
            x_left = inner_x + i * seg
            x_right = x_left + seg
            # apertura tipica: cerniere alternate (dx/sx)
            if i % 2 == 0:
                # cerniera a sinistra → apre a destra
                parts.append(
                    f'<polyline points="{_fmt(x_left)},{_fmt(inner_y)} {_fmt(x_right)},{_fmt(inner_y + inner_h/2)} {_fmt(x_left)},{_fmt(inner_y + inner_h)}" '
                    f'fill="none" stroke="{accent_color}" stroke-width="1.5" stroke-dasharray="4 3"/>'
                )
            else:
                parts.append(
                    f'<polyline points="{_fmt(x_right)},{_fmt(inner_y)} {_fmt(x_left)},{_fmt(inner_y + inner_h/2)} {_fmt(x_right)},{_fmt(inner_y + inner_h)}" '
                    f'fill="none" stroke="{accent_color}" stroke-width="1.5" stroke-dasharray="4 3"/>'
                )
    # QUOTE
    if show_dimensions:
        # Quota larghezza (sotto)
        dy = y0 + H + 35
        parts.append(
            f'<line x1="{x0}" y1="{_fmt(dy)}" x2="{_fmt(x0 + W)}" y2="{_fmt(dy)}" '
            f'stroke="{dim_color}" stroke-width="1" marker-start="url(#arr)" marker-end="url(#arr)"/>'
        )
        parts.append(
            f'<text x="{_fmt(x0 + W/2)}" y="{_fmt(dy + 18)}" text-anchor="middle" '
            f'font-size="14" fill="{dim_color}">{width_mm} mm</text>'
        )
        # Quota altezza (destra)
        dx = x0 + W + 35
        parts.append(
            f'<line x1="{_fmt(dx)}" y1="{y0}" x2="{_fmt(dx)}" y2="{_fmt(y0 + H)}" '
            f'stroke="{dim_color}" stroke-width="1" marker-start="url(#arr)" marker-end="url(#arr)"/>'
        )
        parts.append(
            f'<text x="{_fmt(dx + 8)}" y="{_fmt(y0 + H/2)}" text-anchor="start" '
            f'font-size="14" fill="{dim_color}" transform="rotate(90,{_fmt(dx + 8)},{_fmt(y0 + H/2)})">{height_mm} mm</text>'
        )
    parts.append('</svg>')
    return "".join(parts)


_ALLOWED_TAGS = {"svg", "g", "defs", "marker", "rect", "line", "path", "polygon",
                 "polyline", "text", "title", "desc", "style", "circle", "ellipse"}
_FORBIDDEN_ATTR_RE = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)
_URL_RE = re.compile(r"(?:href|xlink:href)\s*=\s*\"([^\"]+)\"", re.IGNORECASE)


def sanitize_svg(svg: str) -> str:
    """Rimuove eventuali attributi/elementi non consentiti (difesa in profondità)."""
    if not svg:
        return ""
    # Rimuovi script/iframe/foreignObject
    for tag in ("script", "iframe", "foreignObject", "object", "embed"):
        svg = re.sub(rf"<{tag}\b[\s\S]*?</{tag}>", "", svg, flags=re.IGNORECASE)
        svg = re.sub(rf"<{tag}\b[^>]*/>", "", svg, flags=re.IGNORECASE)
    # Rimuovi event handlers on*=""
    svg = _FORBIDDEN_ATTR_RE.sub(" ", svg)
    # Blocca href esterni (mantieni solo #id / url(#…))
    def _clean_href(m):
        v = m.group(1)
        if v.startswith("#"):
            return m.group(0)
        return ""
    svg = _URL_RE.sub(_clean_href, svg)
    # javascript: url
    svg = re.sub(r"javascript:", "blocked:", svg, flags=re.IGNORECASE)
    return svg
