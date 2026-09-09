"""Color Engine — finestre PVC e cassonetti (P0 msg 625).

Due logiche completamente separate:
  - CASSONETTO: COLOR CODE -> PRICE FAMILY (mapping autoritativo rigido, fail-closed).
  - FINESTRA PVC: COLOR CODE -> categoria PVC (MASS_COLOR / STANDARD / SPECIAL) -> foil surcharge.
"""
from __future__ import annotations
from typing import Any, Dict, Optional

# --- COLOR INPUT V2 (msg 631): regola autoritativa unica per codice ---
#   003 -> WHITE_MASS · 100/110/154/096/048/964 -> STANDARD · qualsiasi altro codice valido -> SPECIAL
WHITE_MASS_CODE = "003"
STANDARD_COLOR_CODES = frozenset({"100", "110", "154", "096", "048", "964"})
# Codici semantici legacy (test golden / quote storiche): mantenuti solo lato backend.
_LEGACY_MASS = {"WHITE_MASS", WHITE_MASS_CODE}
_LEGACY_STANDARD_FOIL = {"WHITE_WOOD", "BLEACHED_CEDAR", "WALNUT", "GOLDEN_OAK", "CHERRY", "CREAM"}
WINDOW_COLOR_MODES = ("WHITE_MASS", "WHITE_IN_FOIL_OUT", "FOIL_BOTH_SAME", "BICOLOR")
# Cassonetto: classificazione commerciale -> PRICE FAMILY della griglia autoritativa esistente.
# SPECIAL usa la fascia NON_STANDARD già presente (stessa corrispondenza economica, nessuna griglia duplicata).
CASSONETTO_FAMILY_BY_CLASS = {"WHITE_MASS": "BIANCO_MASSA", "STANDARD": "STANDARD", "SPECIAL": "NON_STANDARD"}
CASSONETTO_FAMILIES = ("BIANCO_MASSA", "STANDARD", "NON_STANDARD")


def normalize_color_code(code: Optional[str]) -> str:
    """Codice come STRINGA: trim + uppercase, zeri iniziali preservati ('096' resta '096')."""
    c = ("" if code is None else str(code)).strip().upper()
    if not c:
        raise ValueError("COLOR_CODE_REQUIRED")
    return c


def resolve_color_classification(code: Optional[str]) -> str:
    c = normalize_color_code(code)
    if c in _LEGACY_MASS:
        return "WHITE_MASS"
    if c in STANDARD_COLOR_CODES or c in _LEGACY_STANDARD_FOIL:
        return "STANDARD"
    return "SPECIAL"


def resolve_cassonetto_family(color_code: Optional[str]) -> str:
    """Nessun fail per codice nuovo: SPECIAL -> griglia NON_STANDARD. Fail solo se il codice manca."""
    try:
        cls = resolve_color_classification(color_code)
    except ValueError:
        raise ValueError("MISSING_COLOR_CODE")
    return CASSONETTO_FAMILY_BY_CLASS[cls]


async def resolve_window_color(db, tenant_id: str, code: str, name: Optional[str] = None) -> Dict[str, Any]:
    """{code, name, hex, category}. category ∈ MASS_COLOR | STANDARD | SPECIAL (dal solo codice).
    hex opzionale (catalogo product_colors se presente, altrimenti None: mai inventato)."""
    c = normalize_color_code(code)
    cls = resolve_color_classification(c)
    if c == "WHITE_MASS":
        c = WHITE_MASS_CODE
    doc = await db.product_colors.find_one({"tenant_id": tenant_id, "code": c, "deleted_at": None})
    hex_ = (doc or {}).get("visual_hex") or ("#F5F5F0" if cls == "WHITE_MASS" else None)
    nm = (name or "").strip() or (doc or {}).get("name") or ("BIANCO MASSA" if cls == "WHITE_MASS" else c)
    return {"code": c, "name": nm, "hex": hex_, "category": "MASS_COLOR" if cls == "WHITE_MASS" else cls, "classification": cls}


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
