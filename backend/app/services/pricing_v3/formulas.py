"""Formule V1_3 approvate per la vertical slice ProEvolution.

Fonte: /app/memory/PRODUCTION_FORMULA_ANALYSIS_V1_3.md + ENERHIA_GOLDEN_TEST_CASES_V1.md

Nessun eval(). Formule espresse come funzioni pure Python su Decimal.
Ogni formula è associata a un `formula_code` versionato per audit.

Milestone 1: solo WINDOW_1_SASH (finestra 1 anta).
Fase 1B (successiva): WINDOW_2_SASH, DOOR_WINDOW_*, MEETING_STILE, THRESHOLD.
"""
from __future__ import annotations
from decimal import Decimal
from typing import Dict


# ---------------------------------------------------------------
# FORMULE PROEVOLUTION WINDOW_1_SASH (GT-01)
# ---------------------------------------------------------------

def frame_ml_1sash(L_mm: int, H_mm: int, S_mm: int = 3) -> Decimal:
    """FRAME (telaio): 2*(L+S) + 2*(H+S) / 1000, in ml.

    S = weld_allowance_mm (default 3mm).
    Formula GT-01: L=900,H=1500,S=3 → 4.812 ml
    """
    return (Decimal(2) * (Decimal(L_mm) + Decimal(S_mm)) +
            Decimal(2) * (Decimal(H_mm) + Decimal(S_mm))) / Decimal(1000)


def frame_reinforcement_ml_1sash(L_mm: int, H_mm: int) -> Decimal:
    """FRAME_REINFORCEMENT (rinforzo telaio): 2*(L-70) + 2*(H-70) / 1000, in ml.

    Offset -70 = spessore telaio PVC standard.
    GT-01: L=900,H=1500 → 4.520 ml
    """
    return (Decimal(2) * (Decimal(L_mm) - Decimal(70)) +
            Decimal(2) * (Decimal(H_mm) - Decimal(70))) / Decimal(1000)


def sash_ml_1sash(L_mm: int, H_mm: int) -> Decimal:
    """SASH (anta): 2*(L-206) + 2*(H-206) / 1000, in ml.

    Offset -206 = luce netta anta (telaio 70 + gioco 8 + anta 20 + rebate + ...).
    GT-01: L=900,H=1500 → 3.976 ml
    """
    return (Decimal(2) * (Decimal(L_mm) - Decimal(206)) +
            Decimal(2) * (Decimal(H_mm) - Decimal(206))) / Decimal(1000)


def sash_reinforcement_ml_1sash(L_mm: int, H_mm: int) -> Decimal:
    """SASH_REINFORCEMENT (rinforzo anta): 2*(L-186) + 2*(H-186) / 1000, in ml.

    Offset -186 = luce netta anta interno (dedotti solo rinforzo/anta senza rebate).
    GT-01: L=900,H=1500 → 4.056 ml
    """
    return (Decimal(2) * (Decimal(L_mm) - Decimal(186)) +
            Decimal(2) * (Decimal(H_mm) - Decimal(186))) / Decimal(1000)


def glass_dimensions_1sash(L_mm: int, H_mm: int) -> Dict[str, int]:
    """GLASS: lastra unica per finestra 1 anta.

    Formula strutturata: L-206 × H-206 (mm).
    GT-01: L=900,H=1500 → 694 × 1294 mm → 0.898036 m²
    """
    return {
        "width_mm": int(L_mm - 206),
        "height_mm": int(H_mm - 206),
        "quantity": 1,
    }


def glass_real_area_sqm(width_mm: int, height_mm: int) -> Decimal:
    """Area vetro reale in m²."""
    return (Decimal(width_mm) * Decimal(height_mm)) / Decimal(1_000_000)


def glass_billable_area_sqm(width_mm: int, height_mm: int,
                             min_billable_sqm: Decimal = Decimal("0.5")) -> Decimal:
    """Area vetro fatturabile: max(real, minimo per singola lastra).

    Regola BR-10 (V1_3): 0.50 m² per singola lastra.
    """
    real = glass_real_area_sqm(width_mm, height_mm)
    return max(real, min_billable_sqm)


# ---------------------------------------------------------------
# TEMPI PRODUZIONE (BR-05)
# ---------------------------------------------------------------

PRODUCTION_TIME_HOURS = {
    "WINDOW_1_SASH":       Decimal("0.75"),
    "WINDOW_2_SASH":       Decimal("1.00"),
    "WINDOW_3_SASH":       Decimal("2.30"),
    "DOOR_WINDOW_1_SASH":  Decimal("1.00"),
    "DOOR_WINDOW_2_SASH":  Decimal("1.50"),
    "DOOR_WINDOW_3_SASH":  Decimal("3.00"),
}


def recipe_code(window_type: str, n_sashes: int) -> str:
    """Costruisce il recipe_code dai parametri di configurazione."""
    wt = (window_type or "WINDOW").upper()
    # Casi speciali
    if wt == "VASISTAS_ONLY":
        return "VASISTAS_ONLY_1_SASH"
    if wt == "SLIDING_DOOR_WINDOW":
        return f"SLIDING_DOOR_WINDOW_{n_sashes}_SASH"
    if wt not in ("WINDOW", "DOOR_WINDOW"):
        return f"{wt}_{n_sashes}_SASH"
    return f"{wt}_{n_sashes}_SASH"


def production_time_hours_for(window_type: str, n_sashes: int) -> Decimal:
    """Ritorna il tempo di produzione in ORE (non minuti) per la configurazione."""
    key = recipe_code(window_type, n_sashes)
    return PRODUCTION_TIME_HOURS.get(key, Decimal("0"))


# ---------------------------------------------------------------
# LISTINO VETRO (BR-07)
# ---------------------------------------------------------------

GLASS_PRICES_PER_SQM = {
    "DOUBLE_STANDARD": Decimal("76.00"),
    "DOUBLE_SATIN":    Decimal("96.00"),
    "TRIPLE_STANDARD": Decimal("125.00"),
    "TRIPLE_SATIN":    Decimal("156.00"),  # PO msg 401 §27: 156.25 → 156.00
}


def glass_price_per_sqm(glass_type: str) -> Decimal:
    """Prezzo €/m² per tipo vetro (BR-07). Lancia KeyError se non presente."""
    return GLASS_PRICES_PER_SQM[glass_type]


# ---------------------------------------------------------------
# COMPONENTI RICETTA PROEVOLUTION WINDOW_1_SASH
# ---------------------------------------------------------------

# Prezzi unitari V1_3 (Preventivatore 4.0, sez. costi unitari)
V1_3_COMPONENT_PRICES = {
    "FRAME_PROEVOLUTION":              Decimal("4.02"),   # €/ml (telaio)
    "FRAME_REINFORCEMENT_PROEVOLUTION": Decimal("1.52"),  # €/ml
    "SASH_PROEVOLUTION":               Decimal("2.31"),   # €/ml
    "SASH_REINFORCEMENT_PROEVOLUTION": Decimal("1.34"),   # €/ml
    "GLAZING_BEAD_PROEVOLUTION":       Decimal("2.10"),   # €/ml — placeholder, NEEDS_PO_CONFIRMATION
    "MEETING_STILE_PROEVOLUTION":      Decimal("5.50"),   # €/ml (scambio battuta V1_3 BR-08)
    "REDUCED_THRESHOLD_PROEVOLUTION":  Decimal("29.50"),  # €/ml variabile (soglia ribassata)
    "REDUCED_THRESHOLD_FIXED_PROEVOLUTION": Decimal("1.00"),  # placeholder — usare THRESHOLD_FIXED_COMPONENT come pz × 7.49/9.84
    "FIXED_MULLION_PROEVOLUTION":      Decimal("7.51"),   # €/ml montante fisso
    "TRANSOM_PROEVOLUTION":            Decimal("7.50"),   # €/ml traverso
    # Legacy hardcoded HARDWARE ora obsoleti — usare `hardware_rules` (Milestone 2)
}


# Componenti PVC eleggibili al pellicolato +10% (BR-09)
PVC_ELIGIBLE_ROLES = {"FRAME", "SASH", "GLAZING_BEAD", "MEETING_STILE"}


# Colori pellicolati standard (BR-09)
STANDARD_FOIL_COLORS = {
    "WHITE_WOOD",      # bianco effetto legno
    "BLEACHED_CEDAR",  # cedro sbiancato
    "WALNUT",          # noce
    "GOLDEN_OAK",      # rovere dorato
    "CHERRY",          # ciliegio
    "CREAM",           # crema
}


def is_foil_surcharge_applicable(color_internal: str, color_external: str) -> bool:
    """Il +10% pellicolato si applica quando ALMENO uno tra interno/esterno è pellicolato standard.

    Include sia il caso pellicolato due lati sia pellicolato esterno + bianco massa interno.
    """
    ci = (color_internal or "").upper()
    ce = (color_external or "").upper()
    return ci in STANDARD_FOIL_COLORS or ce in STANDARD_FOIL_COLORS
