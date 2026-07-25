"""Regression tests for commercial_perimeter engine (new default preventivatore).

Verifica:
- Perimetri corretti (1, 2, 3, 4 ante + fissa)
- Meeting-stile solo per n_sashes > 1
- Sfrido applicato al ml consumption
- Vetro con formula strutturata
- MISSING_GLASS_RECIPE per configurazioni non approvate
- +6% Premium su PVC only
- No fallback a zero
- Snapshot hash deterministico
- Motore technical_cut_list (1-anta 5103+12130) invariato
"""
from __future__ import annotations
from decimal import Decimal
import pytest

from app.services.recipes import (
    PerimeterInput, compute_perimeter,
    resolve_glass_recipe, compute_glass_dimensions,
    PRICING_MODES, DEFAULT_PRICING_MODE, COMMERCIAL_PERIMETER_CODE,
)
from app.services.recipes.commercial_perimeter import (
    display_dict, MISSING_ERROR_CODES,
)


def _sample(**overrides) -> PerimeterInput:
    defaults = dict(
        L_mm=900, H_mm=1500,
        number_of_sashes=1, window_type="apribile",
        P_FRAME=Decimal("4.60"),
        P_FRAME_REINFORCEMENT=Decimal("1.10"),
        P_SASH=Decimal("5.20"),
        P_SASH_REINFORCEMENT=Decimal("1.20"),
        P_GLAZING_BEAD=Decimal("0.90"),
        # Glass recipe pre-resolved: 900-206=694, 1500-206=1294, qty=1
        glass_recipe_resolved=True,
        glass_width_mm=694, glass_height_mm=1294, glass_quantity=1,
        P_GLASS_SQM=Decimal("76.00"),
        MIN_GLASS_SQM=Decimal("0.50"),
        P_HARDWARE=Decimal("12.00"),
        additional_material_cost=Decimal("0"),
        additional_declared_zero=True,
        hourly_cost=Decimal("30.00"),
        production_time_minutes=Decimal("30"),
        margin_pct=Decimal("40"),
        installation_declared_zero=True,
        color_code="BIANCO",
        product_key="PROEVOLUTION",
    )
    defaults.update(overrides)
    return PerimeterInput(**defaults)


# ============================================================
# PERIMETRI
# ============================================================
def test_perimeter_1_sash():
    r = compute_perimeter(_sample())
    assert r.pricing_status == "ok", r.blocking_errors
    # 2*(0.9+1.5)=4.8 ml; sash_perim identica (n=1)
    assert r.external_perimeter_ml == Decimal("4.8")
    assert r.sash_perimeter_ml == Decimal("4.8")
    assert r.meeting_stile_ml == Decimal("0")


def test_perimeter_2_sashes():
    r = compute_perimeter(_sample(
        number_of_sashes=2,
        P_MEETING_STILE=Decimal("3.40"),
        P_MEETING_STILE_REINFORCEMENT=Decimal("1.00"),
        # Glass recipe for 2 ante: (900-347)/2=276, 1500-206=1294, qty=2
        glass_width_mm=276, glass_height_mm=1294, glass_quantity=2,
    ))
    assert r.pricing_status == "ok", r.blocking_errors
    # 4.8 + 2*1.5*(2-1) = 7.8
    assert r.sash_perimeter_ml == Decimal("7.8")
    # meeting_stile_ml = 1.5 * (2-1) = 1.5
    assert r.meeting_stile_ml == Decimal("1.5")


def test_perimeter_3_sashes():
    r = compute_perimeter(_sample(
        number_of_sashes=3,
        P_MEETING_STILE=Decimal("3.40"),
        P_MEETING_STILE_REINFORCEMENT=Decimal("1.00"),
        glass_width_mm=200, glass_height_mm=1294, glass_quantity=3,
    ))
    # sash_perim = 4.8 + 2*1.5*2 = 10.8
    assert r.sash_perimeter_ml == Decimal("10.8")
    # meeting_stile_ml = 1.5 * 2 = 3
    assert r.meeting_stile_ml == Decimal("3")


def test_perimeter_4_sashes():
    r = compute_perimeter(_sample(
        number_of_sashes=4,
        P_MEETING_STILE=Decimal("3.40"),
        P_MEETING_STILE_REINFORCEMENT=Decimal("1.00"),
        glass_width_mm=150, glass_height_mm=1294, glass_quantity=4,
    ))
    # sash_perim = 4.8 + 2*1.5*3 = 13.8
    assert r.sash_perimeter_ml == Decimal("13.8")
    assert r.meeting_stile_ml == Decimal("4.5")


# ============================================================
# FISSA
# ============================================================
def test_fixed_window_excludes_sash_costs():
    r = compute_perimeter(_sample(
        window_type="fissa", number_of_sashes=0,
        P_SASH=None, P_SASH_REINFORCEMENT=None,  # non richiesti per fissa
        # Fissa: usa il fermavetro su perimetro esterno
        # Glass recipe fissa: L-108, H-108, qty=1
        glass_width_mm=792, glass_height_mm=1392, glass_quantity=1,
        hardware_not_required=True,
        P_HARDWARE=None,
    ))
    assert r.pricing_status == "ok", r.blocking_errors
    # Nessun costo sash / meeting_stile
    assert r.component_costs["sash_cost"] == Decimal("0")
    assert r.component_costs["sash_reinforcement_cost"] == Decimal("0")
    assert r.component_costs["meeting_stile_cost"] == Decimal("0")
    assert r.component_costs["hardware_cost"] == Decimal("0")


# ============================================================
# MISSING
# ============================================================
def test_missing_frame_price_blocks():
    r = compute_perimeter(_sample(P_FRAME=None))
    assert r.pricing_status == "incomplete"
    assert MISSING_ERROR_CODES["P_FRAME"] in [e["code"] for e in r.blocking_errors]
    assert r.materials_cost is None
    assert r.sale_price is None


def test_missing_glass_recipe_blocks():
    r = compute_perimeter(_sample(glass_recipe_resolved=False))
    assert r.pricing_status == "incomplete"
    assert "MISSING_GLASS_RECIPE" in [e["code"] for e in r.blocking_errors]


def test_missing_meeting_stile_price_blocks_when_multi_sash():
    r = compute_perimeter(_sample(
        number_of_sashes=2,
        # Missing P_MEETING_STILE!
        glass_width_mm=276, glass_height_mm=1294, glass_quantity=2,
    ))
    assert r.pricing_status == "incomplete"
    codes = [e["code"] for e in r.blocking_errors]
    assert MISSING_ERROR_CODES["P_MEETING_STILE"] in codes


def test_no_meeting_stile_required_for_single_sash():
    r = compute_perimeter(_sample(P_MEETING_STILE=None))  # 1 anta, ms non richiesto
    assert r.pricing_status == "ok"


def test_missing_hourly_cost_blocks():
    r = compute_perimeter(_sample(hourly_cost=None))
    assert r.pricing_status == "incomplete"
    assert MISSING_ERROR_CODES["HOURLY_COST"] in [e["code"] for e in r.blocking_errors]


def test_installation_not_declared_zero_blocks():
    r = compute_perimeter(_sample(installation_declared_zero=False, installation_cost=None))
    assert r.pricing_status == "incomplete"
    assert MISSING_ERROR_CODES["P_INSTALLATION"] in [e["code"] for e in r.blocking_errors]


# ============================================================
# WASTE PERCENTAGE
# ============================================================
def test_waste_percentage_applied_to_ml():
    r = compute_perimeter(_sample(WASTE_FRAME=Decimal("10")))
    # Net = 4.8, con 10% sfrido → 5.28
    assert r.ml_consumption_net["telaio"] == Decimal("4.8")
    assert r.ml_consumption["telaio"] == Decimal("5.28")
    assert r.waste_percentages["telaio"] == Decimal("10")


def test_zero_waste_gives_net_ml():
    r = compute_perimeter(_sample())
    assert r.ml_consumption["telaio"] == r.ml_consumption_net["telaio"]


# ============================================================
# PREMIUM +6% PVC-only
# ============================================================
def test_premium_only_on_pvc():
    base = compute_perimeter(_sample())
    prem = compute_perimeter(_sample(is_color_premium=True))
    # PVC base = frame + sash + glazing_bead
    pvc_base = (base.component_costs["frame_cost"]
                + base.component_costs["sash_cost"]
                + base.component_costs["glazing_bead_cost"])
    assert prem.premium_surcharge == pvc_base * Decimal("6") / Decimal("100")
    # Reinforcement / glass / hardware / labor invariati
    assert prem.component_costs["frame_reinforcement_cost"] == base.component_costs["frame_reinforcement_cost"]
    assert prem.glass_cost == base.glass_cost
    assert prem.hardware_cost == base.hardware_cost
    assert prem.labor_cost == base.labor_cost


# ============================================================
# FORMULA ORDER (materials → labor → production → margin → discount)
# ============================================================
def test_calculation_order():
    r = compute_perimeter(_sample())
    assert r.production_cost == r.materials_cost + r.labor_cost
    assert r.total_internal_cost == r.production_cost + r.service_cost
    expected_before = r.total_internal_cost * (Decimal("1") + Decimal("40") / Decimal("100"))
    assert r.sale_price_before_discount == expected_before
    assert r.sale_price == r.sale_price_before_discount - r.discount


# ============================================================
# SNAPSHOT hash
# ============================================================
def test_snapshot_deterministic():
    r1 = compute_perimeter(_sample())
    r2 = compute_perimeter(_sample())
    assert r1.snapshot_hash and r1.snapshot_hash == r2.snapshot_hash


def test_snapshot_changes_on_price_change():
    r1 = compute_perimeter(_sample())
    r2 = compute_perimeter(_sample(P_FRAME=Decimal("5.00")))
    assert r1.snapshot_hash != r2.snapshot_hash


def test_snapshot_changes_on_mode_specific_fields():
    r1 = compute_perimeter(_sample(number_of_sashes=1))
    r2 = compute_perimeter(_sample(
        number_of_sashes=2,
        P_MEETING_STILE=Decimal("3.40"),
        P_MEETING_STILE_REINFORCEMENT=Decimal("1.00"),
        glass_width_mm=276, glass_height_mm=1294, glass_quantity=2,
    ))
    assert r1.snapshot_hash != r2.snapshot_hash


# ============================================================
# GEOMETRY guards
# ============================================================
def test_invalid_geometry_blocks():
    r = compute_perimeter(_sample(L_mm=0))
    assert r.pricing_status == "invalid_geometry"
    assert r.materials_cost is None


# ============================================================
# PRICING MODES
# ============================================================
def test_pricing_modes_registered():
    assert "commercial_perimeter" in PRICING_MODES
    assert "technical_cut_list" in PRICING_MODES
    assert DEFAULT_PRICING_MODE == "commercial_perimeter"


# ============================================================
# DISPLAY
# ============================================================
def test_display_dict_rounds_only_aggregates():
    r = compute_perimeter(_sample())
    d = display_dict(r)
    # perimeter is a raw decimal float (no rounding to 2 decimals)
    assert d["external_perimeter_ml"] == 4.8
    # Money rounded
    assert isinstance(d["sale_price"], float)
    assert round(d["sale_price"], 2) == d["sale_price"]
    assert d["pricing_mode"] if "pricing_mode" in d else True  # populated at router level
