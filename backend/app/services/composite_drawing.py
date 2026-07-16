"""Composite drawing: render an entire opening with all its products layered.

Layers (bottom → top):
  0. Nicchia muraria (wall opening)
  1. Cassonetto (top)
  2. Serramento (frame + glass)
  3. Simboli aperture
  4. Persiana o scuro (esterno, sovrapposto)
  5. Tapparella (telo esterno)
  6. Zanzariera (indicatore)
  7. Quote esterne + etichetta prodotti
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional
import hashlib
from app.services.svg_advanced import render_composition as render_frame
from app.models_product_types import WindowComposition, WindowModule


def _fmt(n: float) -> str:
    return str(int(round(n))) if abs(n - round(n)) < 0.01 else f"{n:.1f}"


def render_opening_composite(
    opening: Dict[str, Any],
    products: List[Dict[str, Any]],
    *,
    scale_to_max_px: float = 620.0,
) -> tuple[str, str]:
    """Ritorna (svg, hash). `opening` deve contenere width_mm/height_mm."""
    W = int(opening.get("width_mm") or 1200)
    H = int(opening.get("height_mm") or 1400)
    # scala proporzionale
    scale = min(scale_to_max_px / max(1, W), scale_to_max_px / max(1, H))
    body_w = W * scale
    body_h = H * scale
    margin = 100
    legend_h = 80
    viewW = int(body_w + margin * 2 + 40)
    viewH = int(body_h + margin * 2 + legend_h + 100)   # extra for box + labels
    x0 = margin; y0 = margin + 40                        # y0 shifted for box
    frame = "#0F1720"; glass = "#E8F1F7"; accent = "#D42027"
    dim = "#6B7280"

    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {viewW} {viewH}" '
        f'width="100%" preserveAspectRatio="xMidYMid meet" '
        f'style="max-width:100%;background:#FAFAFA;font-family:Georgia,serif" '
        f'data-composite="1">'
    )
    parts.append(
        '<defs>'
        '<marker id="a" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">'
        f'<path d="M0,0 L8,4 L0,8 z" fill="{dim}"/></marker>'
        '<pattern id="rollerpat" x="0" y="0" width="6" height="8" patternUnits="userSpaceOnUse">'
        '<rect width="6" height="8" fill="#94A3B8"/>'
        '<line x1="0" y1="0" x2="6" y2="0" stroke="#64748B" stroke-width="1"/></pattern>'
        '<pattern id="shutterpat" x="0" y="0" width="4" height="10" patternUnits="userSpaceOnUse">'
        '<rect width="4" height="10" fill="#B45309"/>'
        '<line x1="0" y1="0" x2="4" y2="0" stroke="#78350F" stroke-width="1"/></pattern>'
        '</defs>'
    )

    # Individua prodotti per ruolo
    by_role: Dict[str, List[Dict[str, Any]]] = {}
    for p in products:
        r = p.get("role") or "primary_frame"
        by_role.setdefault(r, []).append(p)

    box_products = by_role.get("box", [])
    box_h_px = 24 if box_products else 0

    # 1) NICCHIA MURARIA (contorno tratteggiato)
    parts.append(
        f'<rect x="{_fmt(x0 - 20)}" y="{_fmt(y0 - 20)}" width="{_fmt(body_w + 40)}" height="{_fmt(body_h + 40 + box_h_px)}" '
        f'fill="none" stroke="#94A3B8" stroke-width="1.5" stroke-dasharray="6 4" rx="4"/>'
    )
    parts.append(
        f'<text x="{_fmt(x0 - 20)}" y="{_fmt(y0 - 26)}" font-size="10" fill="#94A3B8">Nicchia {W}×{H}mm</text>'
    )

    # 2) CASSONETTO (top) — solo se presente
    if box_products:
        parts.append(
            f'<rect x="{_fmt(x0)}" y="{_fmt(y0 - box_h_px)}" width="{_fmt(body_w)}" height="{_fmt(box_h_px)}" '
            f'fill="#CBD5E1" stroke="{frame}" stroke-width="2"/>'
        )
        label = box_products[0].get("description") or "Cassonetto"
        parts.append(
            f'<text x="{_fmt(x0 + body_w / 2)}" y="{_fmt(y0 - box_h_px / 2 + 4)}" text-anchor="middle" '
            f'font-size="11" fill="#334155">{label[:30]}</text>'
        )

    # 3) SERRAMENTO PRINCIPALE
    frame_p = None
    if by_role.get("primary_frame"):
        frame_p = by_role["primary_frame"][0]
    if frame_p:
        # Usa render_frame per generare il serramento e lo inserisce come simbolo
        config = frame_p.get("configuration") or {}
        num_modules = int(config.get("num_modules") or 2)
        modules = config.get("modules") or [
            {"index": i, "kind": "battente_ribalta",
             "hinges_side": "left" if i % 2 == 0 else "right",
             "is_fixed": False, "width_ratio": 1}
            for i in range(num_modules)
        ]
        # Semplice: disegna i moduli inline (per evitare svg nested)
        ft = max(4, min(body_w, body_h) * 0.025)
        parts.append(
            f'<rect x="{_fmt(x0)}" y="{_fmt(y0)}" width="{_fmt(body_w)}" height="{_fmt(body_h)}" '
            f'fill="{glass}" stroke="{frame}" stroke-width="{_fmt(ft)}"/>'
        )
        total_ratio = sum(m.get("width_ratio", 1) for m in modules) or 1
        cur_x = x0
        for m in modules:
            mw = body_w * (m.get("width_ratio", 1) / total_ratio)
            kind = m.get("kind", "battente")
            is_fixed = m.get("is_fixed") or kind in ("fixed", "fisso_laterale", "fisso_centrale")
            # sub-frame
            parts.append(
                f'<rect x="{_fmt(cur_x)}" y="{_fmt(y0)}" width="{_fmt(mw)}" height="{_fmt(body_h)}" '
                f'fill="none" stroke="{frame}" stroke-width="{_fmt(ft * 0.6)}"/>'
            )
            cx = cur_x + mw / 2; cy = y0 + body_h / 2
            if is_fixed:
                parts.append(
                    f'<line x1="{_fmt(cur_x)}" y1="{_fmt(y0)}" x2="{_fmt(cur_x + mw)}" y2="{_fmt(y0 + body_h)}" '
                    f'stroke="#94A3B8" stroke-width="1" stroke-dasharray="4 3"/>'
                )
                parts.append(
                    f'<text x="{_fmt(cx)}" y="{_fmt(cy)}" text-anchor="middle" font-size="9" '
                    f'fill="#94A3B8" font-style="italic">FISSO</text>'
                )
            elif kind == "battente":
                hinge = m.get("hinges_side", "left")
                if hinge == "right":
                    parts.append(
                        f'<polyline points="{_fmt(cur_x)},{_fmt(cy)} {_fmt(cur_x + mw)},{_fmt(y0)} {_fmt(cur_x + mw)},{_fmt(y0 + body_h)} {_fmt(cur_x)},{_fmt(cy)}" '
                        f'fill="none" stroke="{accent}" stroke-width="1.5"/>'
                    )
                else:
                    parts.append(
                        f'<polyline points="{_fmt(cur_x + mw)},{_fmt(cy)} {_fmt(cur_x)},{_fmt(y0)} {_fmt(cur_x)},{_fmt(y0 + body_h)} {_fmt(cur_x + mw)},{_fmt(cy)}" '
                        f'fill="none" stroke="{accent}" stroke-width="1.5"/>'
                    )
            elif kind in ("ribalta", "vasistas"):
                parts.append(
                    f'<polyline points="{_fmt(cur_x)},{_fmt(y0)} {_fmt(cur_x + mw)},{_fmt(y0)} {_fmt(cx)},{_fmt(y0 + body_h)} {_fmt(cur_x)},{_fmt(y0)}" '
                    f'fill="none" stroke="{accent}" stroke-width="1.5"/>'
                )
            elif kind == "battente_ribalta":
                hinge = m.get("hinges_side", "left")
                if hinge == "right":
                    parts.append(
                        f'<polyline points="{_fmt(cur_x)},{_fmt(cy)} {_fmt(cur_x + mw)},{_fmt(y0)} {_fmt(cur_x + mw)},{_fmt(y0 + body_h)} {_fmt(cur_x)},{_fmt(cy)}" '
                        f'fill="none" stroke="{accent}" stroke-width="1.5"/>'
                    )
                else:
                    parts.append(
                        f'<polyline points="{_fmt(cur_x + mw)},{_fmt(cy)} {_fmt(cur_x)},{_fmt(y0)} {_fmt(cur_x)},{_fmt(y0 + body_h)} {_fmt(cur_x + mw)},{_fmt(cy)}" '
                        f'fill="none" stroke="{accent}" stroke-width="1.5"/>'
                    )
                parts.append(
                    f'<polyline points="{_fmt(cur_x)},{_fmt(y0)} {_fmt(cur_x + mw)},{_fmt(y0)} {_fmt(cx)},{_fmt(y0 + body_h)}" '
                    f'fill="none" stroke="{accent}" stroke-width="0.8" stroke-dasharray="3 3"/>'
                )
            elif kind in ("scorrevole", "alzante", "traslante"):
                parts.append(
                    f'<line x1="{_fmt(cur_x + mw * 0.15)}" y1="{_fmt(cy)}" x2="{_fmt(cur_x + mw * 0.85)}" y2="{_fmt(cy)}" '
                    f'stroke="{accent}" stroke-width="1.5" marker-start="url(#a)" marker-end="url(#a)"/>'
                )
            cur_x += mw

    # 4) PERSIANA / SCURO (esterno, disegnato "aperto" ai lati come cornice supplementare tratteggiata)
    for sh in by_role.get("shading", []):
        stype = sh.get("product_type_code") or sh.get("product_type") or ""
        if stype == "shutter":
            # persiana: pattern lamellare sui lati
            side_w = 18
            parts.append(
                f'<rect x="{_fmt(x0 - side_w - 2)}" y="{_fmt(y0)}" width="{_fmt(side_w)}" height="{_fmt(body_h)}" '
                f'fill="url(#shutterpat)" stroke="#78350F" stroke-width="1"/>'
            )
            parts.append(
                f'<rect x="{_fmt(x0 + body_w + 2)}" y="{_fmt(y0)}" width="{_fmt(side_w)}" height="{_fmt(body_h)}" '
                f'fill="url(#shutterpat)" stroke="#78350F" stroke-width="1"/>'
            )
        elif stype == "obscurant":
            # scuro: pannelli pieni ai lati
            side_w = 14
            parts.append(
                f'<rect x="{_fmt(x0 - side_w - 2)}" y="{_fmt(y0)}" width="{_fmt(side_w)}" height="{_fmt(body_h)}" '
                f'fill="#78350F" stroke="#1F2937"/>'
            )
            parts.append(
                f'<rect x="{_fmt(x0 + body_w + 2)}" y="{_fmt(y0)}" width="{_fmt(side_w)}" height="{_fmt(body_h)}" '
                f'fill="#78350F" stroke="#1F2937"/>'
            )
        elif stype == "roller_shutter":
            # tapparella: telo che scende dal cassonetto (mezza altezza per non coprire)
            telo_h = body_h * 0.35
            parts.append(
                f'<rect x="{_fmt(x0)}" y="{_fmt(y0)}" width="{_fmt(body_w)}" height="{_fmt(telo_h)}" '
                f'fill="url(#rollerpat)" opacity="0.9"/>'
            )
            parts.append(
                f'<text x="{_fmt(x0 + body_w / 2)}" y="{_fmt(y0 + telo_h + 12)}" text-anchor="middle" '
                f'font-size="9" fill="#64748B">↕ Tapparella</text>'
            )

    # 5) ZANZARIERA (icona in angolo)
    if by_role.get("insect_screen"):
        icon_x = x0 + body_w - 30
        icon_y = y0 + 8
        parts.append(
            f'<rect x="{_fmt(icon_x)}" y="{_fmt(icon_y)}" width="24" height="24" '
            f'fill="none" stroke="#10B981" stroke-width="1"/>'
        )
        # griglia
        for i in range(1, 4):
            parts.append(
                f'<line x1="{_fmt(icon_x + i * 6)}" y1="{_fmt(icon_y)}" x2="{_fmt(icon_x + i * 6)}" y2="{_fmt(icon_y + 24)}" '
                f'stroke="#10B981" stroke-width="0.5"/>'
                f'<line x1="{_fmt(icon_x)}" y1="{_fmt(icon_y + i * 6)}" x2="{_fmt(icon_x + 24)}" y2="{_fmt(icon_y + i * 6)}" '
                f'stroke="#10B981" stroke-width="0.5"/>'
            )
        parts.append(
            f'<text x="{_fmt(icon_x + 12)}" y="{_fmt(icon_y + 40)}" text-anchor="middle" '
            f'font-size="8" fill="#10B981">Zanzariera</text>'
        )

    # 6) QUOTE
    dy = y0 + body_h + 24
    parts.append(
        f'<line x1="{_fmt(x0)}" y1="{_fmt(dy)}" x2="{_fmt(x0 + body_w)}" y2="{_fmt(dy)}" '
        f'stroke="{dim}" stroke-width="1" marker-start="url(#a)" marker-end="url(#a)"/>'
    )
    parts.append(
        f'<text x="{_fmt(x0 + body_w / 2)}" y="{_fmt(dy + 15)}" text-anchor="middle" '
        f'font-size="12" fill="{dim}">{W} mm</text>'
    )
    dx = x0 + body_w + 24
    parts.append(
        f'<line x1="{_fmt(dx)}" y1="{_fmt(y0)}" x2="{_fmt(dx)}" y2="{_fmt(y0 + body_h)}" '
        f'stroke="{dim}" stroke-width="1" marker-start="url(#a)" marker-end="url(#a)"/>'
    )
    parts.append(
        f'<text x="{_fmt(dx + 5)}" y="{_fmt(y0 + body_h / 2)}" text-anchor="start" '
        f'font-size="12" fill="{dim}" transform="rotate(90,{_fmt(dx + 5)},{_fmt(y0 + body_h / 2)})">{H} mm</text>'
    )

    # 7) LEGENDA PRODOTTI
    ly = y0 + body_h + 55
    role_names = {
        "primary_frame": "Serramento", "shading": "Oscurante", "insect_screen": "Zanzariera",
        "box": "Cassonetto", "counter_frame": "Controtelaio", "accessory": "Accessorio",
        "installation": "Montaggio", "dismount": "Smontaggio", "disposal": "Smaltimento",
    }
    lx = x0
    for prod in products:
        r = prod.get("role") or "primary_frame"
        label = role_names.get(r, r)
        parts.append(
            f'<circle cx="{_fmt(lx + 5)}" cy="{_fmt(ly + 5)}" r="4" fill="{accent}"/>'
        )
        parts.append(
            f'<text x="{_fmt(lx + 14)}" y="{_fmt(ly + 8)}" font-size="10" fill="#334155">{label}</text>'
        )
        lx += len(label) * 6 + 30
        if lx > viewW - 100:
            lx = x0; ly += 16

    # Watermark
    parts.append(
        f'<text x="{_fmt(viewW / 2)}" y="{_fmt(viewH / 2)}" text-anchor="middle" font-size="16" '
        f'fill="rgba(148,163,184,0.15)" transform="rotate(-30 {_fmt(viewW / 2)} {_fmt(viewH / 2)})" '
        f'font-style="italic">Rappresentazione illustrativa preventiva</text>'
    )
    parts.append('</svg>')
    svg = "".join(parts)
    h = hashlib.sha256(svg.encode()).hexdigest()[:32]
    return svg, h
