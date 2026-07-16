"""Advanced SVG drawing engine per serramenti — supporta:
- moduli con posizione, tipologia, apertura
- ante fisse (laterali/centrali)
- sopraluce / sottoluce / fiancoluce
- traversi orizzontali + montanti verticali
- simbologia aperture (battente, ribalta, battente-ribalta, scorrevole)
- quote esterne + watermark preventivo
- legenda tecnica

Sicuro: SVG generato programmaticamente, senza input arbitrari raw.
"""
from __future__ import annotations
import hashlib
import re
from typing import List
from xml.sax.saxutils import escape as xml_escape
from app.models_product_types import WindowComposition, WindowModule


_SAFE_TEXT_RE = re.compile(r"[^\w\s\-\.\+°%,/']")


def _safe(s: str, max_len: int = 100) -> str:
    if not s: return ""
    s = str(s)[:max_len]
    return xml_escape(_SAFE_TEXT_RE.sub(" ", s))


def _fmt(n: float) -> str:
    if abs(n - round(n)) < 1e-6:
        return str(int(round(n)))
    return f"{n:.2f}"


def _draw_module(x: float, y: float, w: float, h: float,
                 mod: WindowModule, colors: dict,
                 show_symbols: bool) -> List[str]:
    """Disegna un singolo modulo con la simbologia aperture."""
    frame = colors["frame"]
    glass = colors["glass"]
    accent = colors["accent"]
    parts = []
    ft = max(4, min(w, h) * 0.06)
    # Riquadro anta/fisso
    parts.append(
        f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(w)}" height="{_fmt(h)}" '
        f'fill="{glass}" stroke="{frame}" stroke-width="{_fmt(ft)}"/>'
    )
    # Etichetta piccola in basso
    if mod.label:
        parts.append(
            f'<text x="{_fmt(x + 4)}" y="{_fmt(y + h - 4)}" font-size="9" fill="#6B7280">{_safe(mod.label, 20)}</text>'
        )
    if not show_symbols:
        return parts
    kind = mod.kind
    cx = x + w / 2; cy = y + h / 2
    # FISSO
    if mod.is_fixed or kind == "fixed":
        parts.append(
            f'<line x1="{_fmt(x)}" y1="{_fmt(y)}" x2="{_fmt(x + w)}" y2="{_fmt(y + h)}" '
            f'stroke="#94A3B8" stroke-width="1" stroke-dasharray="4 3"/>'
        )
        parts.append(
            f'<text x="{_fmt(cx)}" y="{_fmt(cy)}" text-anchor="middle" dominant-baseline="middle" '
            f'font-size="10" fill="#94A3B8" font-style="italic">FISSO</text>'
        )
        return parts
    # BATTENTE
    if kind == "battente":
        hinge = mod.hinges_side
        if hinge == "right":
            # apre verso sinistra → triangolo hinge lato destro
            parts.append(
                f'<polyline points="{_fmt(x)},{_fmt(cy)} {_fmt(x + w)},{_fmt(y)} {_fmt(x + w)},{_fmt(y + h)} {_fmt(x)},{_fmt(cy)}" '
                f'fill="none" stroke="{accent}" stroke-width="1.5"/>'
            )
        else:
            parts.append(
                f'<polyline points="{_fmt(x + w)},{_fmt(cy)} {_fmt(x)},{_fmt(y)} {_fmt(x)},{_fmt(y + h)} {_fmt(x + w)},{_fmt(cy)}" '
                f'fill="none" stroke="{accent}" stroke-width="1.5"/>'
            )
    # RIBALTA (vasistas): triangolo con vertice in basso
    elif kind in ("ribalta", "vasistas"):
        parts.append(
            f'<polyline points="{_fmt(x)},{_fmt(y)} {_fmt(x + w)},{_fmt(y)} {_fmt(cx)},{_fmt(y + h)} {_fmt(x)},{_fmt(y)}" '
            f'fill="none" stroke="{accent}" stroke-width="1.5"/>'
        )
    # BATTENTE-RIBALTA: combinazione
    elif kind == "battente_ribalta":
        hinge = mod.hinges_side
        # battente
        if hinge == "right":
            parts.append(
                f'<polyline points="{_fmt(x)},{_fmt(cy)} {_fmt(x + w)},{_fmt(y)} {_fmt(x + w)},{_fmt(y + h)} {_fmt(x)},{_fmt(cy)}" '
                f'fill="none" stroke="{accent}" stroke-width="1.5"/>'
            )
        else:
            parts.append(
                f'<polyline points="{_fmt(x + w)},{_fmt(cy)} {_fmt(x)},{_fmt(y)} {_fmt(x)},{_fmt(y + h)} {_fmt(x + w)},{_fmt(cy)}" '
                f'fill="none" stroke="{accent}" stroke-width="1.5"/>'
            )
        # ribalta sottostante
        parts.append(
            f'<polyline points="{_fmt(x)},{_fmt(y)} {_fmt(x + w)},{_fmt(y)} {_fmt(cx)},{_fmt(y + h)} {_fmt(x)},{_fmt(y)}" '
            f'fill="none" stroke="{accent}" stroke-width="1" stroke-dasharray="3 3"/>'
        )
    # SCORREVOLE: frecce orizzontali
    elif kind in ("scorrevole", "alzante", "traslante"):
        parts.append(
            f'<line x1="{_fmt(x + w * 0.15)}" y1="{_fmt(cy)}" x2="{_fmt(x + w * 0.85)}" y2="{_fmt(cy)}" '
            f'stroke="{accent}" stroke-width="1.5"/>'
        )
        # doppia freccia
        parts.append(
            f'<polyline points="{_fmt(x + w * 0.20)},{_fmt(cy - 4)} {_fmt(x + w * 0.15)},{_fmt(cy)} {_fmt(x + w * 0.20)},{_fmt(cy + 4)}" '
            f'fill="none" stroke="{accent}" stroke-width="1.5"/>'
        )
        parts.append(
            f'<polyline points="{_fmt(x + w * 0.80)},{_fmt(cy - 4)} {_fmt(x + w * 0.85)},{_fmt(cy)} {_fmt(x + w * 0.80)},{_fmt(cy + 4)}" '
            f'fill="none" stroke="{accent}" stroke-width="1.5"/>'
        )
    return parts


def render_composition(
    comp: WindowComposition,
    *,
    frame_color: str = "#0F1720",
    glass_color: str = "#E8F1F7",
    accent_color: str = "#D42027",
    dim_color: str = "#666666",
    show_dimensions: bool = True,
    show_symbols: bool = True,
    show_legend: bool = True,
    watermark: str = "Rappresentazione illustrativa preventiva",
) -> tuple[str, str]:
    """Genera l'SVG completo e ritorna (svg, sha256_hash)."""
    W_mm = int(comp.total_width_mm)
    H_mm = int(comp.total_height_mm)
    # Layout in px
    scale = min(560.0 / max(1, W_mm), 560.0 / max(1, H_mm))
    body_w = W_mm * scale
    body_h = H_mm * scale
    margin = 100 if show_dimensions else 40
    legend_h = 60 if show_legend else 0
    viewW = int(body_w + margin * 2)
    viewH = int(body_h + margin * 2 + legend_h)
    x0 = margin
    y0 = margin
    colors = {"frame": frame_color, "glass": glass_color, "accent": accent_color}

    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {viewW} {viewH}" '
        f'width="100%" preserveAspectRatio="xMidYMid meet" '
        f'style="max-width:100%;background:#FAFAFA;font-family:Georgia,serif" '
        f'data-parametric-svg="2" data-product="{_safe(comp.product_type_code, 40)}">'
    )
    parts.append(
        '<defs>'
        '<marker id="arr2" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">'
        f'<path d="M0,0 L8,4 L0,8 z" fill="{dim_color}"/></marker>'
        '</defs>'
    )
    parts.append(f'<title>{_safe(comp.product_type_code)} {W_mm}x{H_mm}mm</title>')
    parts.append(f'<desc>{_safe("Disegno tecnico serramento — rendering v2.0")}</desc>')

    # Watermark diagonale opzionale
    if watermark:
        parts.append(
            f'<text x="{viewW/2}" y="{viewH/2}" text-anchor="middle" font-size="20" '
            f'fill="rgba(148,163,184,0.18)" transform="rotate(-30 {viewW/2} {viewH/2})" '
            f'font-style="italic">{_safe(watermark, 80)}</text>'
        )

    # ==== TELAIO PRINCIPALE ====
    # Se ci sono sopraluce/sottoluce/fiancoluce sottraggo altezze/larghezze
    top_h = comp.sopraluce_height_mm * scale if comp.has_sopraluce else 0
    bot_h = comp.sottoluce_height_mm * scale if comp.has_sottoluce else 0
    left_w = comp.fiancoluce_left_width_mm * scale if comp.has_fiancoluce_left else 0
    right_w = comp.fiancoluce_right_width_mm * scale if comp.has_fiancoluce_right else 0

    core_x = x0 + left_w
    core_y = y0 + top_h
    core_w = body_w - left_w - right_w
    core_h = body_h - top_h - bot_h

    ft = max(6, min(body_w, body_h) * 0.02)

    # Perimetro totale
    parts.append(
        f'<rect x="{_fmt(x0)}" y="{_fmt(y0)}" width="{_fmt(body_w)}" height="{_fmt(body_h)}" '
        f'fill="none" stroke="{frame_color}" stroke-width="{_fmt(ft)}"/>'
    )

    # SOPRALUCE
    if comp.has_sopraluce and top_h > 0:
        parts.append(
            f'<rect x="{_fmt(x0)}" y="{_fmt(y0)}" width="{_fmt(body_w)}" height="{_fmt(top_h)}" '
            f'fill="{glass_color}" stroke="{frame_color}" stroke-width="{_fmt(ft*0.6)}"/>'
        )
        label = "SOPRALUCE APRIBILE" if comp.sopraluce_openable else "SOPRALUCE FISSO"
        parts.append(
            f'<text x="{_fmt(x0 + body_w/2)}" y="{_fmt(y0 + top_h/2)}" text-anchor="middle" '
            f'dominant-baseline="middle" font-size="10" fill="#6B7280">{label}</text>'
        )
    # SOTTOLUCE
    if comp.has_sottoluce and bot_h > 0:
        parts.append(
            f'<rect x="{_fmt(x0)}" y="{_fmt(y0 + body_h - bot_h)}" width="{_fmt(body_w)}" height="{_fmt(bot_h)}" '
            f'fill="{glass_color}" stroke="{frame_color}" stroke-width="{_fmt(ft*0.6)}"/>'
        )
        parts.append(
            f'<text x="{_fmt(x0 + body_w/2)}" y="{_fmt(y0 + body_h - bot_h/2)}" text-anchor="middle" '
            f'dominant-baseline="middle" font-size="10" fill="#6B7280">SOTTOLUCE</text>'
        )
    # FIANCOLUCE
    if comp.has_fiancoluce_left and left_w > 0:
        parts.append(
            f'<rect x="{_fmt(x0)}" y="{_fmt(core_y)}" width="{_fmt(left_w)}" height="{_fmt(core_h)}" '
            f'fill="{glass_color}" stroke="{frame_color}" stroke-width="{_fmt(ft*0.6)}"/>'
        )
        parts.append(
            f'<text x="{_fmt(x0 + left_w/2)}" y="{_fmt(core_y + core_h/2)}" '
            f'text-anchor="middle" dominant-baseline="middle" font-size="9" fill="#6B7280" '
            f'transform="rotate(-90 {_fmt(x0 + left_w/2)} {_fmt(core_y + core_h/2)})">FIANCOLUCE SX</text>'
        )
    if comp.has_fiancoluce_right and right_w > 0:
        parts.append(
            f'<rect x="{_fmt(x0 + body_w - right_w)}" y="{_fmt(core_y)}" width="{_fmt(right_w)}" '
            f'height="{_fmt(core_h)}" fill="{glass_color}" stroke="{frame_color}" stroke-width="{_fmt(ft*0.6)}"/>'
        )
        parts.append(
            f'<text x="{_fmt(x0 + body_w - right_w/2)}" y="{_fmt(core_y + core_h/2)}" '
            f'text-anchor="middle" dominant-baseline="middle" font-size="9" fill="#6B7280" '
            f'transform="rotate(-90 {_fmt(x0 + body_w - right_w/2)} {_fmt(core_y + core_h/2)})">FIANCOLUCE DX</text>'
        )

    # ==== MODULI (ante) ====
    modules = comp.modules if comp.modules else [
        WindowModule(index=i, kind="battente", hinges_side="left" if i % 2 == 0 else "right")
        for i in range(max(1, comp.num_modules))
    ]
    total_ratio = sum(m.width_ratio for m in modules) or 1
    cur_x = core_x
    for m in modules:
        mw = core_w * (m.width_ratio / total_ratio)
        parts.extend(_draw_module(cur_x, core_y, mw, core_h, m, colors, show_symbols))
        cur_x += mw

    # Traversi orizzontali (nella zona core)
    for i in range(1, comp.num_traversi_horizontal + 1):
        ym = core_y + core_h * i / (comp.num_traversi_horizontal + 1)
        parts.append(
            f'<line x1="{_fmt(core_x)}" y1="{_fmt(ym)}" x2="{_fmt(core_x + core_w)}" y2="{_fmt(ym)}" '
            f'stroke="{frame_color}" stroke-width="{_fmt(ft*0.5)}"/>'
        )

    # ==== QUOTE ====
    if show_dimensions:
        dy = y0 + body_h + 25
        parts.append(
            f'<line x1="{_fmt(x0)}" y1="{_fmt(dy)}" x2="{_fmt(x0 + body_w)}" y2="{_fmt(dy)}" '
            f'stroke="{dim_color}" stroke-width="1" marker-start="url(#arr2)" marker-end="url(#arr2)"/>'
        )
        parts.append(
            f'<text x="{_fmt(x0 + body_w/2)}" y="{_fmt(dy + 16)}" text-anchor="middle" '
            f'font-size="13" fill="{dim_color}">{W_mm} mm</text>'
        )
        dx = x0 + body_w + 25
        parts.append(
            f'<line x1="{_fmt(dx)}" y1="{_fmt(y0)}" x2="{_fmt(dx)}" y2="{_fmt(y0 + body_h)}" '
            f'stroke="{dim_color}" stroke-width="1" marker-start="url(#arr2)" marker-end="url(#arr2)"/>'
        )
        parts.append(
            f'<text x="{_fmt(dx + 6)}" y="{_fmt(y0 + body_h/2)}" text-anchor="start" '
            f'font-size="13" fill="{dim_color}" transform="rotate(90,{_fmt(dx + 6)},{_fmt(y0 + body_h/2)})">'
            f'{H_mm} mm</text>'
        )

    # ==== LEGENDA ====
    if show_legend:
        ly = viewH - legend_h + 10
        entries = [
            ("Battente", "polyline"),
            ("Ribalta", "vasistas"),
            ("Battente-Ribalta", "combo"),
            ("Scorrevole", "arrows"),
            ("Fisso", "diag"),
        ]
        lx = x0
        for label, kind in entries:
            parts.append(
                f'<rect x="{_fmt(lx)}" y="{_fmt(ly)}" width="26" height="26" '
                f'fill="{glass_color}" stroke="{frame_color}" stroke-width="1"/>'
            )
            if kind == "polyline":
                parts.append(
                    f'<polyline points="{_fmt(lx + 26)},{_fmt(ly + 13)} {_fmt(lx)},{_fmt(ly)} {_fmt(lx)},{_fmt(ly + 26)} {_fmt(lx + 26)},{_fmt(ly + 13)}" '
                    f'fill="none" stroke="{accent_color}" stroke-width="1.2"/>'
                )
            elif kind == "vasistas":
                parts.append(
                    f'<polyline points="{_fmt(lx)},{_fmt(ly)} {_fmt(lx + 26)},{_fmt(ly)} {_fmt(lx + 13)},{_fmt(ly + 26)} {_fmt(lx)},{_fmt(ly)}" '
                    f'fill="none" stroke="{accent_color}" stroke-width="1.2"/>'
                )
            elif kind == "combo":
                parts.append(
                    f'<polyline points="{_fmt(lx + 26)},{_fmt(ly + 13)} {_fmt(lx)},{_fmt(ly)} {_fmt(lx)},{_fmt(ly + 26)} {_fmt(lx + 26)},{_fmt(ly + 13)}" '
                    f'fill="none" stroke="{accent_color}" stroke-width="1.2"/>'
                )
                parts.append(
                    f'<polyline points="{_fmt(lx)},{_fmt(ly)} {_fmt(lx + 26)},{_fmt(ly)} {_fmt(lx + 13)},{_fmt(ly + 26)}" '
                    f'fill="none" stroke="{accent_color}" stroke-width="0.8" stroke-dasharray="2 2"/>'
                )
            elif kind == "arrows":
                parts.append(
                    f'<line x1="{_fmt(lx + 3)}" y1="{_fmt(ly + 13)}" x2="{_fmt(lx + 23)}" y2="{_fmt(ly + 13)}" '
                    f'stroke="{accent_color}" stroke-width="1.2" marker-start="url(#arr2)" marker-end="url(#arr2)"/>'
                )
            elif kind == "diag":
                parts.append(
                    f'<line x1="{_fmt(lx)}" y1="{_fmt(ly)}" x2="{_fmt(lx + 26)}" y2="{_fmt(ly + 26)}" '
                    f'stroke="#94A3B8" stroke-width="1" stroke-dasharray="3 2"/>'
                )
            parts.append(
                f'<text x="{_fmt(lx + 32)}" y="{_fmt(ly + 17)}" font-size="10" fill="#4B5563">{_safe(label)}</text>'
            )
            lx += 130

    parts.append('</svg>')
    svg = "".join(parts)
    h = hashlib.sha256(svg.encode()).hexdigest()[:32]
    return svg, h
