"""BOM Recipe Engine — Ricette parametriche pronte all'uso.

Ogni ricetta è un preset visuale che l'admin sceglie dall'UI (senza scrivere
formule AST a mano). La ricetta produce automaticamente:
  - quantity_formula, length_formula, width_formula, height_formula
  - condition (motore condizioni)
  - component_type, unit_of_measure di default

Le formule generate rispettano il parser AST safe di `services.formula` (nessun eval).

Convenzioni variabili:
  L, H          = larghezza/altezza foro (mm)
  nr_ante       = numero ante mobili
  nr_traversi   = numero traversi orizzontali intermedi
  nr_montanti   = numero montanti verticali intermedi
  nr_fissi      = numero specchiature/fisso
  frame_width, sash_width, central_node, rebate, glass_deduction, glazing_bead_clearance
                = parametri sistema profilo (ProfileSystemTech)

Le "ricette" (18) coprono i casi reali per serramenti standard e ampia parte dei
componenti non standard. Ricette avanzate (condizionale, formula libera) sono
disponibili come fallback per utenti tecnici autorizzati.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Definizione ricette (metadata + compiler)
# ---------------------------------------------------------------------------

RECIPE_CATALOG: List[Dict[str, Any]] = [
    # -- Profili perimetrali ------------------------------------------------
    {
        "code": "PERIMETRO_TELAIO",
        "name": "Perimetro telaio",
        "category": "profile",
        "description": "4 tagli sul perimetro del foro (2 orizzontali + 2 verticali).",
        "component_type": "profile",
        "default_unit": "linear_m",
        "params_schema": [
            {"key": "role", "label": "Ruolo", "type": "select",
             "options": ["frame"], "default": "frame"},
            {"key": "adjustment_mm", "label": "Correzione totale (mm)", "type": "number",
             "default": 0, "help": "Somma/sottrai mm alla lunghezza (installation gap, etc.)"},
        ],
    },
    {
        "code": "PERIMETRO_ANTA",
        "name": "Perimetro anta",
        "category": "profile",
        "description": "4 profili anta per ogni anta mobile (larghezza = (L - central_node*(nr_ante-1)) / nr_ante).",
        "component_type": "profile",
        "default_unit": "linear_m",
        "params_schema": [
            {"key": "role", "label": "Ruolo", "type": "select",
             "options": ["sash"], "default": "sash"},
        ],
    },
    {
        "code": "PERIMETRO_SPECCHIATURA",
        "name": "Perimetro specchiatura (fisso)",
        "category": "profile",
        "description": "Perimetro fissi/specchiature interne (usa nr_fissi).",
        "component_type": "profile",
        "default_unit": "linear_m",
        "params_schema": [
            {"key": "role", "label": "Ruolo", "type": "select",
             "options": ["sash", "glazing_bead"], "default": "sash"},
        ],
    },
    {
        "code": "SUPERFICIE_VETRO",
        "name": "Superficie vetro",
        "category": "glass",
        "description": "Area vetro = (W_anta - glass_deduction) × (H_anta - glass_deduction) × nr_ante.",
        "component_type": "glass",
        "default_unit": "sqm",
        "params_schema": [
            {"key": "per_leaf", "label": "Un vetro per anta", "type": "boolean", "default": True},
        ],
    },
    # -- Profili interni intermedi -----------------------------------------
    {
        "code": "MONTANTE_VERTICALE",
        "name": "Montante verticale",
        "category": "profile",
        "description": "Montanti verticali intermedi (nr_montanti pezzi, lunghezza = H).",
        "component_type": "profile",
        "default_unit": "linear_m",
        "params_schema": [
            {"key": "role", "label": "Ruolo", "type": "select",
             "options": ["mullion"], "default": "mullion"},
        ],
    },
    {
        "code": "TRAVERSO_ORIZZONTALE",
        "name": "Traverso orizzontale",
        "category": "profile",
        "description": "Traversi orizzontali intermedi (nr_traversi pezzi, lunghezza = L).",
        "component_type": "profile",
        "default_unit": "linear_m",
        "params_schema": [
            {"key": "role", "label": "Ruolo", "type": "select",
             "options": ["transom"], "default": "transom"},
        ],
    },
    {
        "code": "SCAMBIO_BATTUTA",
        "name": "Scambio di battuta (2 ante centrali)",
        "category": "profile",
        "description": "Profilo di scambio verticale tra due ante centrali (1 pz, lunghezza = H).",
        "component_type": "profile",
        "default_unit": "linear_m",
        "params_schema": [],
    },
    # -- Rinforzi ----------------------------------------------------------
    {
        "code": "RINFORZO_TELAIO",
        "name": "Rinforzo telaio",
        "category": "profile",
        "description": "Barra di rinforzo interna al telaio (perimetro completo).",
        "component_type": "profile",
        "default_unit": "linear_m",
        "params_schema": [
            {"key": "role", "label": "Ruolo", "type": "select",
             "options": ["reinforcement_frame"], "default": "reinforcement_frame"},
        ],
    },
    {
        "code": "RINFORZO_ANTA",
        "name": "Rinforzo anta",
        "category": "profile",
        "description": "Barra di rinforzo interna alle ante (perimetro anta).",
        "component_type": "profile",
        "default_unit": "linear_m",
        "params_schema": [
            {"key": "role", "label": "Ruolo", "type": "select",
             "options": ["reinforcement_sash"], "default": "reinforcement_sash"},
        ],
    },
    # -- Fermavetro & Guarnizioni ------------------------------------------
    {
        "code": "FERMAVETRO",
        "name": "Fermavetro perimetrale",
        "category": "profile",
        "description": "Fermavetro perimetrale al vetro (4 lati × nr_vetri).",
        "component_type": "profile",
        "default_unit": "linear_m",
        "params_schema": [],
    },
    {
        "code": "GUARNIZIONE",
        "name": "Guarnizione",
        "category": "profile",
        "description": "Guarnizione lineare (perimetro telaio o anta).",
        "component_type": "seal",
        "default_unit": "linear_m",
        "params_schema": [
            {"key": "target", "label": "Applicazione", "type": "select",
             "options": ["frame", "sash", "glazing"], "default": "sash"},
        ],
    },
    # -- Componenti a quantità semplice -----------------------------------
    {
        "code": "COMPONENTE_PER_ANTA",
        "name": "Componente per anta (n × nr_ante)",
        "category": "hardware",
        "description": "Componente che si moltiplica per numero ante (es. maniglie, cerniere).",
        "component_type": "hardware",
        "default_unit": "piece",
        "params_schema": [
            {"key": "multiplier", "label": "Molt. per anta", "type": "number", "default": 1},
        ],
    },
    {
        "code": "COMPONENTE_PER_MODULO",
        "name": "Componente per modulo (n × moduli)",
        "category": "hardware",
        "description": "Componente moltiplicato per moduli totali (nr_ante + nr_fissi).",
        "component_type": "hardware",
        "default_unit": "piece",
        "params_schema": [
            {"key": "multiplier", "label": "Molt. per modulo", "type": "number", "default": 1},
        ],
    },
    {
        "code": "COMPONENTE_A_PEZZO",
        "name": "Componente a pezzo (quantità fissa)",
        "category": "hardware",
        "description": "Quantità fissa per serramento (es. 1 kit ferramenta).",
        "component_type": "hardware",
        "default_unit": "piece",
        "params_schema": [
            {"key": "quantity", "label": "Quantità", "type": "number", "default": 1},
        ],
    },
    {
        "code": "COMPONENTE_CONDIZIONALE",
        "name": "Componente condizionale",
        "category": "hardware",
        "description": "Applicato solo se una condizione è vera (es. nr_ante >= 2).",
        "component_type": "hardware",
        "default_unit": "piece",
        "params_schema": [
            {"key": "field", "label": "Campo", "type": "select",
             "options": ["nr_ante", "nr_traversi", "nr_montanti", "nr_fissi",
                          "width_mm", "height_mm", "hardware_kit_id"],
             "default": "nr_ante"},
            {"key": "op", "label": "Operatore", "type": "select",
             "options": ["eq", "neq", "gt", "gte", "lt", "lte", "in", "exists"],
             "default": "gte"},
            {"key": "value", "label": "Valore", "type": "text", "default": "2"},
            {"key": "quantity", "label": "Quantità se vera", "type": "number", "default": 1},
        ],
    },
    # -- Lavorazioni --------------------------------------------------------
    {
        "code": "LAVORAZIONE_PER_SERRAMENTO",
        "name": "Lavorazione per serramento",
        "category": "labor",
        "description": "Costo lavorazione fisso per unità di serramento.",
        "component_type": "labor",
        "default_unit": "piece",
        "params_schema": [
            {"key": "quantity", "label": "Quantità (h/pz)", "type": "number", "default": 1},
        ],
    },
    {
        "code": "LAVORAZIONE_PER_ANTA",
        "name": "Lavorazione per anta",
        "category": "labor",
        "description": "Costo lavorazione moltiplicato per numero ante.",
        "component_type": "labor",
        "default_unit": "piece",
        "params_schema": [
            {"key": "quantity_per_leaf", "label": "Quantità per anta", "type": "number", "default": 1},
        ],
    },
    {
        "code": "LAVORAZIONE_PER_TAGLIO",
        "name": "Lavorazione per taglio",
        "category": "labor",
        "description": "Costo lavorazione per numero tagli (dipende dai profili perimetrali/interni).",
        "component_type": "labor",
        "default_unit": "piece",
        "params_schema": [
            {"key": "quantity_per_cut", "label": "Quantità per taglio", "type": "number", "default": 1},
        ],
    },
    {
        "code": "LAVORAZIONE_PER_SUPERFICIE",
        "name": "Lavorazione per superficie",
        "category": "labor",
        "description": "Costo lavorazione al m² del foro.",
        "component_type": "labor",
        "default_unit": "sqm",
        "params_schema": [
            {"key": "rate_per_sqm", "label": "Quantità al m²", "type": "number", "default": 1},
        ],
    },
    # -- Formula libera (fallback) -----------------------------------------
    {
        "code": "FORMULA_LIBERA",
        "name": "Formula libera (utente tecnico)",
        "category": "advanced",
        "description": "L'admin scrive formule AST direttamente (nessuna preset).",
        "component_type": "profile",
        "default_unit": "linear_m",
        "requires_permission": "products.manage",
        "params_schema": [
            {"key": "quantity_formula", "label": "Formula quantità", "type": "text", "default": "1"},
            {"key": "length_formula", "label": "Formula lunghezza (mm)", "type": "text", "default": ""},
            {"key": "area_formula", "label": "Formula area (m²)", "type": "text", "default": ""},
        ],
    },
]


def list_recipes() -> List[Dict[str, Any]]:
    """Ritorna il catalogo ricette (metadata solo). Sicuro per l'API pubblica."""
    return RECIPE_CATALOG


def get_recipe(code: str) -> Optional[Dict[str, Any]]:
    for r in RECIPE_CATALOG:
        if r["code"] == code:
            return r
    return None


# ---------------------------------------------------------------------------
# Compiler ricetta → BomComponent (partial)
# ---------------------------------------------------------------------------

def _fmt_num(v: Any) -> str:
    try:
        f = float(v)
        return f"{f:.6f}".rstrip("0").rstrip(".") or "0"
    except (TypeError, ValueError):
        return "0"


def compile_recipe(code: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Traduce una ricetta + i suoi parametri in una BomComponent parziale.

    Returns:
        dict con chiavi:
          component_type, unit_of_measure, role, quantity_formula,
          length_formula, width_formula, height_formula, area_formula,
          weight_formula, condition, recipe_code, recipe_params
    """
    recipe = get_recipe(code)
    if not recipe:
        raise ValueError(f"Ricetta sconosciuta: {code}")

    params = params or {}
    out: Dict[str, Any] = {
        "recipe_code": code,
        "recipe_params": dict(params),
        "component_type": recipe.get("component_type"),
        "unit_of_measure": recipe.get("default_unit"),
        "role": params.get("role"),
        "quantity_formula": "1",
        "length_formula": None,
        "width_formula": None,
        "height_formula": None,
        "area_formula": None,
        "weight_formula": None,
        "condition": [],
    }

    if code == "PERIMETRO_TELAIO":
        adj = _fmt_num(params.get("adjustment_mm", 0))
        out["role"] = params.get("role", "frame")
        # 2 lati orizzontali (L) + 2 lati verticali (H). Rappresentiamo come
        # 4 pezzi con lunghezza media? No: usiamo 1 pezzo con lunghezza totale =
        # perimetro in mm. Cutting list userà length_mm/quantity separatamente.
        # Convenzione: quantity=1 pezzo logico, length_mm = 2*(L+H).
        out["quantity_formula"] = "1"
        out["length_formula"] = f"2 * (L + H) + {adj}"
    elif code == "PERIMETRO_ANTA":
        out["role"] = params.get("role", "sash")
        # nr_ante ante, ognuna con perimetro = 2*(W_anta + H_anta)
        # W_anta = (L - central_node*(nr_ante-1)) / nr_ante
        # H_anta = H - frame_width*2  (semplificazione: no traversi)
        out["quantity_formula"] = "nr_ante"
        out["length_formula"] = (
            "2 * ((L - central_node * (nr_ante - 1)) / nr_ante + (H - frame_width * 2))"
        )
    elif code == "PERIMETRO_SPECCHIATURA":
        out["role"] = params.get("role", "sash")
        out["quantity_formula"] = "nr_fissi"
        out["length_formula"] = "2 * (L / max(nr_fissi, 1) + H - frame_width * 2)"
        # Condizione: applicato solo se ci sono specchiature
        out["condition"] = [{"field": "nr_fissi", "op": "gte", "value": 1}]
    elif code == "SUPERFICIE_VETRO":
        per_leaf = bool(params.get("per_leaf", True))
        if per_leaf:
            out["quantity_formula"] = "nr_ante"
            out["width_formula"] = (
                "(L - central_node * (nr_ante - 1)) / nr_ante - glass_deduction"
            )
            out["height_formula"] = "H - frame_width * 2 - glass_deduction"
        else:
            out["quantity_formula"] = "1"
            out["width_formula"] = "L - glass_deduction"
            out["height_formula"] = "H - glass_deduction"
    elif code == "MONTANTE_VERTICALE":
        out["role"] = params.get("role", "mullion")
        out["quantity_formula"] = "nr_montanti"
        out["length_formula"] = "H - frame_width * 2"
        out["condition"] = [{"field": "nr_montanti", "op": "gte", "value": 1}]
    elif code == "TRAVERSO_ORIZZONTALE":
        out["role"] = params.get("role", "transom")
        out["quantity_formula"] = "nr_traversi"
        out["length_formula"] = "L - frame_width * 2"
        out["condition"] = [{"field": "nr_traversi", "op": "gte", "value": 1}]
    elif code == "SCAMBIO_BATTUTA":
        out["quantity_formula"] = "1"
        out["length_formula"] = "H - frame_width * 2"
        out["condition"] = [{"field": "nr_ante", "op": "gte", "value": 2}]
    elif code == "RINFORZO_TELAIO":
        out["role"] = params.get("role", "reinforcement_frame")
        out["quantity_formula"] = "1"
        out["length_formula"] = "2 * (L + H)"
    elif code == "RINFORZO_ANTA":
        out["role"] = params.get("role", "reinforcement_sash")
        out["quantity_formula"] = "nr_ante"
        out["length_formula"] = (
            "2 * ((L - central_node * (nr_ante - 1)) / nr_ante + (H - frame_width * 2))"
        )
    elif code == "FERMAVETRO":
        # 4 lati per anta, lunghezza = perimetro vetro (glass_deduction)
        out["quantity_formula"] = "nr_ante"
        out["length_formula"] = (
            "2 * ((L - central_node * (nr_ante - 1)) / nr_ante - glass_deduction "
            "+ H - frame_width * 2 - glass_deduction)"
        )
    elif code == "GUARNIZIONE":
        target = params.get("target", "sash")
        out["quantity_formula"] = "1" if target == "frame" else "nr_ante"
        if target == "frame":
            out["length_formula"] = "2 * (L + H)"
        elif target == "glazing":
            out["length_formula"] = (
                "2 * ((L - central_node * (nr_ante - 1)) / nr_ante - glass_deduction "
                "+ H - frame_width * 2 - glass_deduction)"
            )
        else:  # sash
            out["length_formula"] = (
                "2 * ((L - central_node * (nr_ante - 1)) / nr_ante + (H - frame_width * 2))"
            )
    elif code == "COMPONENTE_PER_ANTA":
        mult = _fmt_num(params.get("multiplier", 1))
        out["quantity_formula"] = f"nr_ante * {mult}"
    elif code == "COMPONENTE_PER_MODULO":
        mult = _fmt_num(params.get("multiplier", 1))
        out["quantity_formula"] = f"(nr_ante + nr_fissi) * {mult}"
    elif code == "COMPONENTE_A_PEZZO":
        qty = _fmt_num(params.get("quantity", 1))
        out["quantity_formula"] = qty
    elif code == "COMPONENTE_CONDIZIONALE":
        field = params.get("field", "nr_ante")
        op = params.get("op", "gte")
        value = params.get("value", 2)
        qty = _fmt_num(params.get("quantity", 1))
        # Cast valore numerico se possibile
        try:
            value_cast: Any = float(value)
            if value_cast.is_integer():
                value_cast = int(value_cast)
        except (TypeError, ValueError):
            value_cast = value
        out["quantity_formula"] = qty
        out["condition"] = [{"field": field, "op": op, "value": value_cast}]
    elif code == "LAVORAZIONE_PER_SERRAMENTO":
        qty = _fmt_num(params.get("quantity", 1))
        out["quantity_formula"] = qty
    elif code == "LAVORAZIONE_PER_ANTA":
        rate = _fmt_num(params.get("quantity_per_leaf", 1))
        out["quantity_formula"] = f"nr_ante * {rate}"
    elif code == "LAVORAZIONE_PER_TAGLIO":
        # Numero tagli = 4 (perimetro telaio) + 4*nr_ante (ante) + nr_montanti + nr_traversi
        rate = _fmt_num(params.get("quantity_per_cut", 1))
        out["quantity_formula"] = (
            f"(4 + 4 * nr_ante + nr_montanti + nr_traversi) * {rate}"
        )
    elif code == "LAVORAZIONE_PER_SUPERFICIE":
        rate = _fmt_num(params.get("rate_per_sqm", 1))
        # area = (L * H) / 1000000  → ma nel contesto abbiamo già "area"
        out["quantity_formula"] = f"area * {rate}"
    elif code == "FORMULA_LIBERA":
        out["quantity_formula"] = str(params.get("quantity_formula", "1")).strip() or "1"
        lf = str(params.get("length_formula", "")).strip()
        af = str(params.get("area_formula", "")).strip()
        out["length_formula"] = lf or None
        out["area_formula"] = af or None
    else:
        raise ValueError(f"Ricetta non compilabile: {code}")

    # Human-readable string per audit / display (concatenazione formule attive)
    parts = []
    if out.get("quantity_formula"):
        parts.append(f"qty = {out['quantity_formula']}")
    if out.get("length_formula"):
        parts.append(f"len_mm = {out['length_formula']}")
    if out.get("width_formula"):
        parts.append(f"w_mm = {out['width_formula']}")
    if out.get("height_formula"):
        parts.append(f"h_mm = {out['height_formula']}")
    if out.get("area_formula"):
        parts.append(f"area_sqm = {out['area_formula']}")
    out["formula_applied"] = " ; ".join(parts)
    out["condition_applied"] = out.get("condition") or []
    return out
