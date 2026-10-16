"""DELIVERY LEAD TIME POLICY (PO direttiva IVA+TEMPI) — classe canonica per codice colore catalogo, mai per nome.
STANDARD_60: BIANCO (003), BIANCO EFFETTO LEGNO (100), NOCE base (154), CILIEGIO base (110). Tutto il resto: STANDARD_90.
Bicolore: regola più restrittiva. Commessa: elemento con lead time maggiore."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

DELIVERY_LEAD_POLICY_VERSION = "delivery_lead_time_v1_2026_09"
DELIVERY_CLASS_DAYS = {"STANDARD_60": 60, "STANDARD_90": 90}
# Codice catalogo → delivery_class (proprietà canonica, replicata su product_colors.delivery_class)
DELIVERY_CLASS_BY_CODE: Dict[str, str] = {
    "003": "STANDARD_60", "WHITE_MASS": "STANDARD_60",        # BIANCO (massa)
    "100": "STANDARD_60", "WHITE_WOOD": "STANDARD_60",        # BIANCO EFFETTO LEGNO (pellicolato)
    "154": "STANDARD_60", "WALNUT": "STANDARD_60",            # NOCE pellicolato base
    "110": "STANDARD_60", "CHERRY": "STANDARD_60",            # CILIEGIO pellicolato base
}
DELIVERY_CLASS_SEMANTIC = {"003": "WHITE", "WHITE_MASS": "WHITE", "100": "WHITE_WOOD_EFFECT", "WHITE_WOOD": "WHITE_WOOD_EFFECT",
                           "154": "WALNUT_BASE", "WALNUT": "WALNUT_BASE", "110": "CHERRY_BASE", "CHERRY": "CHERRY_BASE"}
COLORED_PRODUCT_TYPES = {"WINDOW", "DOOR_WINDOW", "ROLLER_BOX", "SHUTTER", "ROLLER_SHUTTER", "MOSQUITO_NET"}


def color_delivery_class(code: Optional[str]) -> str:
    c = ("" if code is None else str(code)).strip().upper()
    return DELIVERY_CLASS_BY_CODE.get(c, "STANDARD_90")


def line_lead_time(line: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Riga prodotto → {days, class, colors}. None per righe senza configurazione colore (servizi, extra)."""
    spec = ((line.get("visual_spec") or {}).get("spec")) or {}
    codes: List[str] = []
    if spec.get("product_type") in COLORED_PRODUCT_TYPES:
        for k in ("interior_color_code", "exterior_color_code"):
            if spec.get(k):
                codes.append(str(spec[k]))
        rb = spec.get("roller_box_color") or {}
        if rb.get("code"):
            codes.append(str(rb["code"]))
    if not codes:
        return None
    classes = [color_delivery_class(c) for c in codes]
    cls = "STANDARD_90" if "STANDARD_90" in classes else "STANDARD_60"  # bicolore → più restrittiva
    return {"line_id": line.get("id"), "description": line.get("description"), "delivery_class": cls, "days": DELIVERY_CLASS_DAYS[cls],
            "colors": [{"code": c.upper(), "delivery_class": k, "semantic": DELIVERY_CLASS_SEMANTIC.get(c.upper())} for c, k in zip(codes, classes)]}


def compute_quote_lead_time(lines: List[Dict[str, Any]]) -> Dict[str, Any]:
    items = [x for x in (line_lead_time(l) for l in lines or []) if x]
    if not items:
        return {"delivery_lead_time_days": None, "delivery_lead_time_class": None, "delivery_lead_time_mixed": False, "delivery_lead_time_items": [],
                "delivery_lead_policy_version": DELIVERY_LEAD_POLICY_VERSION}
    days = max(i["days"] for i in items)
    mixed = len({i["days"] for i in items}) > 1
    return {"delivery_lead_time_days": days, "delivery_lead_time_class": "STANDARD_60" if days == 60 else "STANDARD_90", "delivery_lead_time_mixed": mixed,
            "delivery_lead_time_items": items, "delivery_lead_policy_version": DELIVERY_LEAD_POLICY_VERSION,
            "delivery_customer_text": lead_time_customer_text(days, mixed)}


def lead_time_customer_text(days: int, mixed: bool) -> str:
    base = f"Consegna entro {days} giorni dall'ordine e dal rilievo tecnico definitivo."
    return base + (" Tempo commessa determinato dalla configurazione con lead time maggiore." if mixed else "")
