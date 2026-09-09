"""VisualSpec canonico + renderer SVG deterministico (P0 msg 625).

PRODUCT CONFIGURATION -> VISUAL_SPEC -> SVG (UI + PDF).
Un'unica source of truth: la UI e il PDF consumano lo stesso VisualSpec e lo stesso SVG
generato qui. Nessuna AI, nessuna risorsa esterna, nessun raster.
"""
from __future__ import annotations
import hashlib
from typing import Any, Dict, Optional
from xml.sax.saxutils import escape

VISUAL_SPEC_VERSION = "1.0"
VISUAL_PRODUCT_TYPES = ("WINDOW", "DOOR_WINDOW", "ROLLER_BOX", "SHUTTER", "ROLLER_SHUTTER", "MOSQUITO_NET")

_CATEGORY_TO_TYPE = {
    "FINESTRE": "WINDOW", "PORTEFINESTRE": "DOOR_WINDOW", "SCORREVOLI": "WINDOW",
    "CASSONETTI": "ROLLER_BOX", "PERSIANE_SCURI": "SHUTTER", "TAPPARELLE": "ROLLER_SHUTTER",
    "ZANZARIERE": "MOSQUITO_NET",
}
_NEUTRAL_HEX = {"RAL": "#B0B0B0", "RAL_STANDARD": "#B0B0B0", "WOOD_EFFECT": "#8B5A2B", "SPECIAL_RAFFAELLO": "#7A3E2E",
                "RAFFAELLO": "#7A3E2E", "BASE": "#C8C8C8", "MARBLE": "#D8D0C0", "SPECIAL": "#9A8F7F"}


def _shade(hex_color: str, factor: float) -> str:
    h = (hex_color or "#CCCCCC").lstrip("#")
    if len(h) != 6:
        h = "CCCCCC"
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (max(0, min(255, int(c * factor))) for c in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


def _is_light(hex_color: str) -> bool:
    h = (hex_color or "#CCCCCC").lstrip("#")
    if len(h) != 6:
        return True
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (0.299 * r + 0.587 * g + 0.114 * b) > 160


# ---------------------------------------------------------------------------
# VisualSpec builder
# ---------------------------------------------------------------------------
async def build_visual_spec(db, tenant_id: str, product: Dict[str, Any], category: Optional[Dict[str, Any]],
                            cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Costruisce il VisualSpec canonico a partire dalla configurazione salvata/inviata.

    Ritorna None se il prodotto non è rappresentabile (servizi, accessori, forfait).
    Legge SOLO ciò che è realmente configurato: nessun elemento inventato.
    """
    cat_code = (category or {}).get("code") or product.get("category_code") or ""
    model = product.get("pricing_model")
    ptype = _CATEGORY_TO_TYPE.get(cat_code)
    if model == "FORMULA_TECHNICAL":
        ptype = "DOOR_WINDOW" if str(cfg.get("window_type") or "WINDOW").upper() == "DOOR_WINDOW" else "WINDOW"
    elif model == "GRID":
        ptype = "ROLLER_BOX"
    elif model == "AREA_PURCHASE_MULTIPLIER":
        ptype = "SHUTTER"
    if ptype not in VISUAL_PRODUCT_TYPES:
        return None

    def _int(v, default=0):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default

    spec: Dict[str, Any] = {
        "spec_version": VISUAL_SPEC_VERSION,
        "product_type": ptype,
        "product_name": product.get("name"),
        "width_mm": _int(cfg.get("width_mm")),
        "height_mm": _int(cfg.get("height_mm")),
        "quantity": _int(cfg.get("quantity"), 1) or 1,
        "sash_count": None, "opening_configuration": None, "hinge_side": None, "glass_type": None,
        "interior_color_code": None, "interior_color_name": None, "interior_color_hex": None,
        "exterior_color_code": None, "exterior_color_name": None, "exterior_color_hex": None,
        "color_mode": None,
        "transom": False, "toplight": False, "underlight": False,
        "roller_box": False, "roller_box_dimensions": None, "roller_box_color": None,
        "shutter": False, "roller_shutter": False, "mosquito_net": False,
    }

    if ptype in ("WINDOW", "DOOR_WINDOW"):
        from app.services.color_engine import resolve_window_color
        spec["sash_count"] = max(1, min(4, _int(cfg.get("number_of_sashes"), 1)))
        spec["opening_configuration"] = str(cfg.get("opening_configuration") or "BATTENTE").upper()
        spec["hinge_side"] = str(cfg.get("hinge_side") or "DX").upper()
        spec["glass_type"] = str(cfg.get("glass_type") or "DOUBLE_STANDARD").upper()
        spec["color_mode"] = cfg.get("color_mode")
        for side, key in (("interior", "color_internal"), ("exterior", "color_external")):
            code = cfg.get(key)
            if code:
                try:
                    c = await resolve_window_color(db, tenant_id, str(code), cfg.get(f"{key}_name"))
                    spec[f"{side}_color_code"], spec[f"{side}_color_name"], spec[f"{side}_color_hex"] = c["code"], c["name"], c["hex"]
                    spec[f"{side}_color_classification"] = c["classification"]  # congelato con la riga (msg 631 §23-24)
                except ValueError:
                    spec[f"{side}_color_code"] = str(code)
    elif ptype == "ROLLER_BOX":
        spec["roller_box"] = True
        spec["roller_box_dimensions"] = {
            "width_mm": spec["width_mm"], "height_mm": spec["height_mm"],
            "depth_mm": _int(cfg.get("depth_mm")), "ceiling_liner": str(cfg.get("ceiling_liner") or "SI").upper(),
        }
        code = cfg.get("color_code")
        if code:
            from app.services.color_engine import normalize_color_code, resolve_color_classification
            nc = normalize_color_code(code)
            doc = await db.product_colors.find_one({"tenant_id": tenant_id, "code": nc, "deleted_at": None})
            spec["roller_box_color"] = {"code": nc, "name": (cfg.get("color_name") or "").strip() or (doc or {}).get("name") or nc,
                                        "hex": (doc or {}).get("visual_hex"), "classification": resolve_color_classification(nc)}
    else:
        flag = {"SHUTTER": "shutter", "ROLLER_SHUTTER": "roller_shutter", "MOSQUITO_NET": "mosquito_net"}[ptype]
        spec[flag] = True
        code = cfg.get("color_code")
        hex_ = None
        name = None
        if code:
            if ptype == "MOSQUITO_NET":
                doc = await db.zanzariere_colors.find_one({"tenant_id": tenant_id, "code": str(code), "deleted_at": None})
                hex_, name = (doc or {}).get("visual_hex"), (doc or {}).get("name")
            hex_ = hex_ or _NEUTRAL_HEX.get(str(code).upper()) or "#B0B0B0"
        spec["exterior_color_code"] = str(code) if code else None
        spec["exterior_color_name"] = name or (str(code) if code else None)
        spec["exterior_color_hex"] = hex_
        spec["interior_color_code"], spec["interior_color_name"], spec["interior_color_hex"] = spec["exterior_color_code"], spec["exterior_color_name"], hex_
        if ptype == "SHUTTER":
            spec["orientable"] = bool(cfg.get("orientable"))
    return spec


def build_visual(spec: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """VisualSpec -> payload completo consumato da UI e PDF (spec + svg per vista)."""
    if not spec:
        return None
    bicolor = spec["product_type"] in ("WINDOW", "DOOR_WINDOW") and bool(spec.get("interior_color_code")) \
        and spec.get("interior_color_code") != spec.get("exterior_color_code")
    return {
        "spec": spec,
        "is_bicolor": bicolor,
        "svg_exterior": render_svg(spec, "EXTERIOR"),
        "svg_interior": render_svg(spec, "INTERIOR"),
    }


# ---------------------------------------------------------------------------
# SVG renderer (deterministico)
# ---------------------------------------------------------------------------
_CANVAS = 240
_PAD_L, _PAD_T, _PAD_R, _PAD_B = 34, 22, 14, 30


def _fit(w_mm: int, h_mm: int):
    box_w = _CANVAS - _PAD_L - _PAD_R
    box_h = _CANVAS - _PAD_T - _PAD_B
    w_mm = max(1, w_mm or 1000)
    h_mm = max(1, h_mm or 1000)
    k = min(box_w / w_mm, box_h / h_mm)
    w, h = w_mm * k, h_mm * k
    x = _PAD_L + (box_w - w) / 2
    y = _PAD_T + (box_h - h) / 2
    return x, y, w, h


def _labels(spec, x, y, w, h, view_label: Optional[str]) -> str:
    out = []
    fs = 'font-family="Helvetica, Arial, sans-serif"'
    if spec.get("width_mm"):
        out.append(f'<text x="{x + w / 2:.1f}" y="{_CANVAS - 10}" {fs} font-size="9" text-anchor="middle" fill="#374151">L {spec["width_mm"]} mm</text>')
        out.append(f'<line x1="{x:.1f}" y1="{_CANVAS - 20}" x2="{x + w:.1f}" y2="{_CANVAS - 20}" stroke="#9CA3AF" stroke-width="0.6"/>')
    if spec.get("height_mm"):
        out.append(f'<text transform="translate(12 {y + h / 2:.1f}) rotate(-90)" {fs} font-size="9" text-anchor="middle" fill="#374151">H {spec["height_mm"]} mm</text>')
        out.append(f'<line x1="22" y1="{y:.1f}" x2="22" y2="{y + h:.1f}" stroke="#9CA3AF" stroke-width="0.6"/>')
    if view_label:
        out.append(f'<text x="{_PAD_L}" y="13" {fs} font-size="8" font-weight="bold" letter-spacing="1" fill="#6B7280">{view_label}</text>')
    if (spec.get("quantity") or 1) > 1:
        out.append(f'<text x="{_CANVAS - 8}" y="13" {fs} font-size="9" font-weight="bold" text-anchor="end" fill="#111827">× {spec["quantity"]}</text>')
    return "".join(out)


def _glass(uid: str, gx, gy, gw, gh, glass_type: str) -> str:
    satin = "SATIN" in (glass_type or "")
    if satin:
        return (f'<rect x="{gx:.1f}" y="{gy:.1f}" width="{gw:.1f}" height="{gh:.1f}" fill="#E6ECF0"/>'
                f'<rect x="{gx:.1f}" y="{gy:.1f}" width="{gw:.1f}" height="{gh:.1f}" fill="url(#satin-{uid})"/>')
    x1, y1 = gx + gw * 0.15, gy + gh * 0.85
    return (f'<rect x="{gx:.1f}" y="{gy:.1f}" width="{gw:.1f}" height="{gh:.1f}" fill="#D6EBF5"/>'
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{gx + gw * 0.55:.1f}" y2="{gy + gh * 0.15:.1f}" stroke="#FFFFFF" stroke-width="1.2" opacity="0.8"/>'
            f'<line x1="{x1 + gw * 0.12:.1f}" y1="{y1:.1f}" x2="{gx + gw * 0.67:.1f}" y2="{gy + gh * 0.15:.1f}" stroke="#FFFFFF" stroke-width="0.6" opacity="0.8"/>')


def _opening_symbol(sx, sy, sw, sh, hinge_left: bool, tilt: bool) -> str:
    st = 'fill="none" stroke="#1F2937" stroke-width="0.8" stroke-dasharray="3 2"'
    hx = sx if hinge_left else sx + sw
    tip_x = sx + sw if hinge_left else sx
    out = [f'<polyline points="{hx:.1f},{sy:.1f} {tip_x:.1f},{sy + sh / 2:.1f} {hx:.1f},{sy + sh:.1f}" {st}/>']
    if tilt:
        out.append(f'<polyline points="{sx:.1f},{sy + sh:.1f} {sx + sw / 2:.1f},{sy:.1f} {sx + sw:.1f},{sy + sh:.1f}" {st}/>')
    return "".join(out)


def _render_window(spec, view: str, uid: str) -> str:
    x, y, w, h = _fit(spec["width_mm"], spec["height_mm"])
    interior = view == "INTERIOR"
    hex_ = (spec.get("interior_color_hex") if interior else spec.get("exterior_color_hex")) or "#E5E7EB"  # neutro se HEX assente
    stroke = _shade(hex_, 0.55) if _is_light(hex_) else _shade(hex_, 1.6)
    n = spec.get("sash_count") or 1
    f = max(4.0, min(w, h) * 0.055)
    parts = [f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{hex_}" stroke="{stroke}" stroke-width="0.9"/>']
    opening = spec.get("opening_configuration") or "BATTENTE"
    tilt = opening == "ANTA_RIBALTA"
    fixed = opening in ("FISSA", "FIXED")
    hinge_dx = (spec.get("hinge_side") or "DX") == "DX"
    inner_w = w - 2 * f
    sash_w = inner_w / n
    for i in range(n):
        sx, sy, sw, sh = x + f + i * sash_w, y + f, sash_w, h - 2 * f
        s = max(3.0, f * 0.8)
        parts.append(f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{sw:.1f}" height="{sh:.1f}" fill="{hex_}" stroke="{stroke}" stroke-width="0.7"/>')
        bottom_rail = s * (2.2 if spec["product_type"] == "DOOR_WINDOW" else 1.0)
        gx, gy, gw, gh = sx + s, sy + s, sw - 2 * s, sh - s - bottom_rail
        parts.append(_glass(uid, gx, gy, gw, gh, spec.get("glass_type") or ""))
        parts.append(f'<rect x="{gx:.1f}" y="{gy:.1f}" width="{gw:.1f}" height="{gh:.1f}" fill="none" stroke="{stroke}" stroke-width="0.5"/>')
        if not fixed:
            if n == 1:
                hinge_left_int = not hinge_dx
            else:
                hinge_left_int = i < n / 2
            hinge_left = hinge_left_int if interior else not hinge_left_int
            parts.append(_opening_symbol(gx, gy, gw, gh, hinge_left, tilt))
            if interior:
                hx = gx + gw - 3 if hinge_left else gx - s + 1
                parts.append(f'<rect x="{hx:.1f}" y="{gy + gh / 2 - 6:.1f}" width="2.2" height="12" rx="0.8" fill="#4B5563"/>')
    view_label = "VISTA INTERNA" if interior else "VISTA ESTERNA"
    return "".join(parts) + _labels(spec, x, y, w, h, view_label)


def _render_roller_box(spec, uid: str) -> str:
    d = spec.get("roller_box_dimensions") or {}
    depth = d.get("depth_mm") or 0
    color = (spec.get("roller_box_color") or {})
    hex_ = color.get("hex") or "#E5E7EB"
    stroke = _shade(hex_, 0.55) if _is_light(hex_) else _shade(hex_, 1.6)
    w_mm, h_mm = spec["width_mm"] or 500, spec["height_mm"] or 250
    # riserva spazio per la faccia laterale (profondità) a destra
    depth_ratio = min(0.6, depth / max(w_mm, 1)) if depth else 0
    x, y, w, h = _fit(int(w_mm * (1 + depth_ratio * 0.6)), int(h_mm * (1 + depth_ratio * 0.5)))
    fw = w / (1 + depth_ratio * 0.6)
    fh = h / (1 + depth_ratio * 0.5)
    dx, dy = w - fw, h - fh
    fx, fy = x, y + dy
    parts = []
    if depth:
        parts.append(f'<polygon points="{fx:.1f},{fy:.1f} {fx + dx:.1f},{y:.1f} {fx + fw + dx:.1f},{y:.1f} {fx + fw:.1f},{fy:.1f}" fill="{_shade(hex_, 0.92)}" stroke="{stroke}" stroke-width="0.7"/>')
        parts.append(f'<polygon points="{fx + fw:.1f},{fy:.1f} {fx + fw + dx:.1f},{y:.1f} {fx + fw + dx:.1f},{y + fh:.1f} {fx + fw:.1f},{fy + fh:.1f}" fill="{_shade(hex_, 0.8)}" stroke="{stroke}" stroke-width="0.7"/>')
    parts.append(f'<rect x="{fx:.1f}" y="{fy:.1f}" width="{fw:.1f}" height="{fh:.1f}" fill="{hex_}" stroke="{stroke}" stroke-width="0.9"/>')
    # sportello di ispezione (linea frontale)
    parts.append(f'<line x1="{fx + 4:.1f}" y1="{fy + fh * 0.62:.1f}" x2="{fx + fw - 4:.1f}" y2="{fy + fh * 0.62:.1f}" stroke="{stroke}" stroke-width="0.6" stroke-dasharray="2 2"/>')
    if (d.get("ceiling_liner") or "SI") == "SI":
        parts.append(f'<rect x="{fx:.1f}" y="{fy + fh - 4:.1f}" width="{fw:.1f}" height="4" fill="{_shade(hex_, 0.88)}" stroke="{stroke}" stroke-width="0.5"/>')
        parts.append(f'<text x="{fx + fw / 2:.1f}" y="{fy + fh + 9:.1f}" font-family="Helvetica, Arial, sans-serif" font-size="7" text-anchor="middle" fill="#6B7280">cielino</text>')
    fs = 'font-family="Helvetica, Arial, sans-serif"'
    if depth:
        parts.append(f'<text x="{fx + fw + dx / 2 + 2:.1f}" y="{y + fh + dy + 12:.1f}" {fs} font-size="8" text-anchor="middle" fill="#374151">P {depth}</text>')
    lbl = _labels(spec, fx, fy, fw, fh, "CASSONETTO")
    return "".join(parts) + lbl


def _render_slatted(spec, uid: str, kind: str) -> str:
    x, y, w, h = _fit(spec["width_mm"], spec["height_mm"])
    hex_ = spec.get("exterior_color_hex") or "#B0B0B0"
    stroke = _shade(hex_, 0.55) if _is_light(hex_) else _shade(hex_, 1.6)
    parts = [f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{hex_}" stroke="{stroke}" stroke-width="0.9"/>']
    if kind == "SHUTTER":
        f = max(4.0, min(w, h) * 0.06)
        parts.append(f'<rect x="{x + f:.1f}" y="{y + f:.1f}" width="{w - 2 * f:.1f}" height="{h - 2 * f:.1f}" fill="{_shade(hex_, 0.95)}" stroke="{stroke}" stroke-width="0.5"/>')
        step = 9.0
        yy = y + f + step
        orient = spec.get("orientable")
        while yy < y + h - f - 2:
            if orient:
                parts.append(f'<line x1="{x + f + 2:.1f}" y1="{yy:.1f}" x2="{x + w - f - 2:.1f}" y2="{yy - 3:.1f}" stroke="{stroke}" stroke-width="1.1"/>')
            else:
                parts.append(f'<line x1="{x + f + 2:.1f}" y1="{yy:.1f}" x2="{x + w - f - 2:.1f}" y2="{yy:.1f}" stroke="{stroke}" stroke-width="1.1"/>')
            yy += step
        label = "PERSIANA" + (" · ORIENTABILE" if orient else "")
    elif kind == "ROLLER_SHUTTER":
        yy = y + 7
        while yy < y + h - 2:
            parts.append(f'<line x1="{x:.1f}" y1="{yy:.1f}" x2="{x + w:.1f}" y2="{yy:.1f}" stroke="{stroke}" stroke-width="0.7"/>')
            yy += 7
        label = "TAPPARELLA"
    else:
        f = max(3.0, min(w, h) * 0.04)
        parts.append(f'<rect x="{x + f:.1f}" y="{y + f:.1f}" width="{w - 2 * f:.1f}" height="{h - 2 * f:.1f}" fill="url(#mesh-{uid})" stroke="{stroke}" stroke-width="0.5"/>')
        label = "ZANZARIERA"
    return "".join(parts) + _labels(spec, x, y, w, h, label)


def render_svg(spec: Dict[str, Any], view: str = "EXTERIOR") -> str:
    """Rende il VisualSpec in SVG. Stesso spec + stessa vista -> stesso SVG (deterministico)."""
    uid = hashlib.sha1(f"{view}|{sorted(spec.items(), key=lambda kv: kv[0])!r}".encode()).hexdigest()[:8]
    ptype = spec.get("product_type")
    if ptype in ("WINDOW", "DOOR_WINDOW"):
        body = _render_window(spec, view, uid)
    elif ptype == "ROLLER_BOX":
        body = _render_roller_box(spec, uid)
    elif ptype in ("SHUTTER", "ROLLER_SHUTTER", "MOSQUITO_NET"):
        body = _render_slatted(spec, uid, ptype)
    else:
        return ""
    defs = (
        f'<defs><pattern id="satin-{uid}" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        f'<line x1="0" y1="0" x2="0" y2="4" stroke="#FFFFFF" stroke-width="1.6"/></pattern>'
        f'<pattern id="mesh-{uid}" width="3" height="3" patternUnits="userSpaceOnUse">'
        f'<rect width="3" height="3" fill="#F3F4F6"/><path d="M0 0H3M0 0V3" stroke="#9CA3AF" stroke-width="0.35"/></pattern></defs>'
    )
    title = escape(f"{spec.get('product_name') or ptype} {spec.get('width_mm')}x{spec.get('height_mm')} mm")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_CANVAS} {_CANVAS}" width="{_CANVAS}" height="{_CANVAS}" '
            f'role="img" data-visual-spec-version="{VISUAL_SPEC_VERSION}" data-view="{view}"><title>{title}</title>{defs}{body}</svg>')
