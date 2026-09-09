"""Color Engine — finestre PVC e cassonetti (P0 msg 625).

Due logiche completamente separate:
  - CASSONETTO: COLOR CODE -> PRICE FAMILY (mapping autoritativo rigido, fail-closed).
  - FINESTRA PVC: COLOR CODE -> categoria PVC (MASS_COLOR / STANDARD / SPECIAL) -> foil surcharge.
"""
from __future__ import annotations
from typing import Any, Dict, Optional

# --- CASSONETTO: mapping autoritativo PO (msg 625 §14) ---
CASSONETTO_COLOR_FAMILY: Dict[str, str] = {
    "003": "BIANCO_MASSA",
    "100": "STANDARD", "096": "STANDARD", "694": "STANDARD",
    "110": "STANDARD", "154": "STANDARD", "048": "STANDARD",
    "019": "NON_STANDARD", "145": "NON_STANDARD", "146": "NON_STANDARD",
    "109": "NON_STANDARD", "402": "NON_STANDARD", "663": "NON_STANDARD",
}
CASSONETTO_FAMILIES = ("BIANCO_MASSA", "STANDARD", "NON_STANDARD")


def resolve_cassonetto_family(color_code: Optional[str]) -> str:
    """Fail-closed: nessun fallback, nessuno STANDARD automatico."""
    if not color_code:
        raise ValueError("MISSING_COLOR_CODE")
    fam = CASSONETTO_COLOR_FAMILY.get(str(color_code).strip())
    if fam not in CASSONETTO_FAMILIES:
        raise ValueError(f"CASSONETTO_COLOR_FAMILY_UNMAPPED:{color_code}")
    return fam


# --- FINESTRE PVC ---
WINDOW_COLOR_MODES = ("WHITE_MASS", "WHITE_IN_FOIL_OUT", "FOIL_BOTH_SAME", "BICOLOR")
WHITE_MASS_CODE = "003"
# Codici semantici legacy (test golden / pricing_v3) mantenuti solo lato backend.
_LEGACY_MASS = {"WHITE_MASS", WHITE_MASS_CODE}
_LEGACY_STANDARD_FOIL = {"WHITE_WOOD", "BLEACHED_CEDAR", "WALNUT", "GOLDEN_OAK", "CHERRY", "CREAM"}


async def resolve_window_color(db, tenant_id: str, code: str) -> Dict[str, Any]:
    """Ritorna {code, name, hex, category} con category ∈ MASS_COLOR | STANDARD | SPECIAL.

    Raise ValueError('UNKNOWN_COLOR_CODE:<code>') se il codice non è in catalogo.
    """
    c = (code or "").strip().upper()
    if c in _LEGACY_MASS:
        doc = await db.product_colors.find_one({"tenant_id": tenant_id, "code": WHITE_MASS_CODE, "deleted_at": None})
        return {"code": WHITE_MASS_CODE, "name": (doc or {}).get("name") or "BIANCO MASSA",
                "hex": (doc or {}).get("visual_hex") or "#F5F5F0", "category": "MASS_COLOR"}
    if c in _LEGACY_STANDARD_FOIL:
        return {"code": c, "name": c, "hex": "#B87333", "category": "STANDARD"}
    doc = await db.product_colors.find_one({"tenant_id": tenant_id, "code": c, "deleted_at": None, "active": True})
    if not doc:
        raise ValueError(f"UNKNOWN_COLOR_CODE:{code}")
    cat = doc.get("pvc_color_category") or ("MASS_COLOR" if doc.get("mass_color") else "STANDARD")
    return {"code": doc["code"], "name": doc.get("name") or doc["code"], "hex": doc.get("visual_hex") or "#DDDDDD", "category": cat}


def window_foil_surcharge_applicable(cat_internal: str, cat_external: str) -> bool:
    """+10% pellicolato standard: applicabile se almeno un lato è STANDARD foil.

    MASS_COLOR (003) non è pellicola -> nessun surcharge.
    SPECIAL: nessuna policy economica V1 -> fail closed (NEEDS_PO_PRICING).
    Un solo surcharge anche se pellicolato su due lati.
    """
    cats = {cat_internal, cat_external}
    if "SPECIAL" in cats:
        raise ValueError("NEEDS_PO_PRICING_SPECIAL_FOIL")
    return "STANDARD" in cats
