"""Regression tests for the 1-anta window recipe (Opzione A).

Reference case from the specification (paragraph 14):
  L = 900, H = 1500, S = 6
  P_5103 = 4.60 €/ml, P_12130 = 5.20 €/ml
  P_RINFORZO_TELAIO = 1.10 €/ml, P_RINFORZO_ANTA = 1.20 €/ml
  P_FERMAVETRO = 0.90 €/ml, P_VETRO = 76.00 €/m²
  MQ_MINIMO_VETRO = 0.50 m², P_FERRAMENTA = 12.00 €
  C_ALTRI = 5.00 €, COSTO_ORARIO = 30.00 €/h, TEMPO_PRODUZIONE_MINUTI = 30
  MARGINE_PERCENTUALE = 40%, SCONTO_AUTORIZZATO = 0

The GEOMETRY numbers in the spec are exact and MUST match — we assert
them without rounding tolerance.
"""
from __future__ import annotations
from decimal import Decimal
import pytest

from app.services.recipes import compute_finestra_1a, FinestraAInput, FINESTRA_1A_CODE
from app.services.recipes.finestra_1a import (
    display_dict, MISSING_ERROR_CODES,
)


# --------------------------------------------------------------------
# GEOMETRY tests — 900 × 1500 as per spec
# --------------------------------------------------------------------
def _sample_input(**overrides) -> FinestraAInput:
    defaults = dict(
        L=900, H=1500, S=6,
        P_5103=Decimal("4.60"), P_12130=Decimal("5.20"),
        P_RINFORZO_TELAIO=Decimal("1.10"), P_RINFORZO_ANTA=Decimal("1.20"),
        P_FERMAVETRO=Decimal("0.90"), P_VETRO=Decimal("76.00"),
        MQ_MINIMO_VETRO=Decimal("0.50"),
        P_FERRAMENTA=Decimal("12.00"),
        C_ALTRI=Decimal("5.00"),
        COSTO_ORARIO=Decimal("30.00"),
        TEMPO_PRODUZIONE_MINUTI=Decimal("30"),
        MARGINE_PERCENTUALE=Decimal("40"),
        color_code="BIANCO",
    )
    defaults.update(overrides)
    return FinestraAInput(**defaults)


def test_geometry_expected_900_1500():
    r = compute_finestra_1a(_sample_input())
    assert r.pricing_status == "ok", r.blocking_errors
    # Telaio: 2×906 + 2×1506 = 4824 mm = 4.824 ml
    tel = next(c for c in r.cut_list if c.component == "telaio_5103")
    assert (tel.len_orizzontale_mm, tel.len_verticale_mm) == (906, 1506)
    assert tel.total_mm == 4824
    assert r.ml_consumption["telaio_5103"] == Decimal("4.824")
    # Rinforzo telaio: 2×792 + 2×1392 = 4368
    rt = next(c for c in r.cut_list if c.component == "rinforzo_telaio")
    assert (rt.len_orizzontale_mm, rt.len_verticale_mm) == (792, 1392)
    assert rt.total_mm == 4368
    # Anta: 2×836 + 2×1436 = 4544
    an = next(c for c in r.cut_list if c.component == "anta_12130")
    assert (an.len_orizzontale_mm, an.len_verticale_mm) == (836, 1436)
    assert an.total_mm == 4544
    # Rinforzo anta: 2×694 + 2×1294 = 3976
    ra = next(c for c in r.cut_list if c.component == "rinforzo_anta")
    assert (ra.len_orizzontale_mm, ra.len_verticale_mm) == (694, 1294)
    assert ra.total_mm == 3976
    # Fermavetro: 2×714 + 2×1314 = 4056
    fv = next(c for c in r.cut_list if c.component == "fermavetro")
    assert (fv.len_orizzontale_mm, fv.len_verticale_mm) == (714, 1314)
    assert fv.total_mm == 4056


def test_glass_billable_matches_spec():
    r = compute_finestra_1a(_sample_input())
    # L_vetro=694, H_vetro=1294 → 898036 mm² → 0.898036 m²
    assert r.glass_real_sqm == Decimal("0.898036")
    assert r.glass_billable_sqm == Decimal("0.898036")  # > 0.50 min
    # Cost = 0.898036 × 76.00 = 68.250736 (unrounded intermediary)
    assert r.component_costs["glass_cost"] == Decimal("68.250736")


def test_glass_minimum_kicks_in_for_small_windows():
    small = _sample_input(L=400, H=400)  # >206 OK, but glass area (194×194)=37636/1e6 = 0.037636
    r = compute_finestra_1a(small)
    assert r.pricing_status == "ok"
    assert r.glass_real_sqm == Decimal("0.037636")
    assert r.glass_billable_sqm == Decimal("0.50")


# --------------------------------------------------------------------
# COSTS — must never fallback to zero
# --------------------------------------------------------------------
def test_missing_frame_price_blocks():
    r = compute_finestra_1a(_sample_input(P_5103=None))
    assert r.pricing_status == "incomplete"
    codes = [e["code"] for e in r.blocking_errors]
    assert MISSING_ERROR_CODES["P_5103"] in codes
    assert r.materials_cost is None  # must not silently compute with 0
    assert r.sale_price is None


def test_missing_hardware_price_blocks():
    r = compute_finestra_1a(_sample_input(P_FERRAMENTA=None))
    assert r.pricing_status == "incomplete"
    assert MISSING_ERROR_CODES["P_FERRAMENTA"] in [e["code"] for e in r.blocking_errors]


def test_missing_hourly_cost_blocks():
    r = compute_finestra_1a(_sample_input(COSTO_ORARIO=None))
    assert r.pricing_status == "incomplete"
    assert MISSING_ERROR_CODES["COSTO_ORARIO"] in [e["code"] for e in r.blocking_errors]


def test_missing_altri_not_declared_zero_blocks():
    r = compute_finestra_1a(_sample_input(C_ALTRI=None))
    assert r.pricing_status == "incomplete"
    assert MISSING_ERROR_CODES["C_ALTRI"] in [e["code"] for e in r.blocking_errors]


def test_altri_explicitly_declared_zero_ok():
    r = compute_finestra_1a(_sample_input(C_ALTRI=None, C_ALTRI_declared_zero=True))
    assert r.pricing_status == "ok"
    assert r.component_costs["additional_components_cost"] == Decimal("0")


# --------------------------------------------------------------------
# GEOMETRY guards
# --------------------------------------------------------------------
def test_invalid_geometry_blocks():
    r = compute_finestra_1a(_sample_input(L=200))   # L must be > 206
    assert r.pricing_status == "invalid_geometry"
    assert r.materials_cost is None
    checks = [e["check"] for e in r.blocking_errors]
    assert "L" in checks


def test_geometry_edge_case_slightly_above_min():
    r = compute_finestra_1a(_sample_input(L=207, H=207))
    # 207 > 206 OK; but 207-70+6 = 143 > 0 OK; 207-108=99>0 OK; 207-186=21>0 OK.
    assert r.pricing_status == "ok"


# --------------------------------------------------------------------
# PREMIUM COLOUR +6% PVC-only
# --------------------------------------------------------------------
def test_premium_surcharge_only_on_pvc():
    base = compute_finestra_1a(_sample_input(is_color_premium=False))
    prem = compute_finestra_1a(_sample_input(is_color_premium=True))

    # PVC base = C_5103 + C_12130 + C_FERMAVETRO (+ C_ALTRI_pvc_share=0)
    pvc_base = (base.component_costs["frame_cost"]
                + base.component_costs["sash_cost"]
                + base.component_costs["glazing_bead_cost"])
    expected_surcharge = pvc_base * Decimal("6") / Decimal("100")
    assert prem.premium_surcharge == expected_surcharge

    # Reinforcement / glass / hardware / labor MUST NOT change
    assert prem.component_costs["frame_reinforcement_cost"] == base.component_costs["frame_reinforcement_cost"]
    assert prem.component_costs["sash_reinforcement_cost"] == base.component_costs["sash_reinforcement_cost"]
    assert prem.component_costs["glass_cost"] == base.component_costs["glass_cost"]
    assert prem.component_costs["hardware_cost"] == base.component_costs["hardware_cost"]
    assert prem.labor_cost == base.labor_cost


# --------------------------------------------------------------------
# MARGIN applied after production_cost
# --------------------------------------------------------------------
def test_margin_applied_after_production():
    r = compute_finestra_1a(_sample_input())
    expected_prod = r.materials_cost + r.labor_cost
    assert r.production_cost == expected_prod
    expected_sale = expected_prod * (Decimal("1") + Decimal("40") / Decimal("100"))
    assert r.sale_price_before_discount == expected_sale


def test_snapshot_hash_deterministic():
    r1 = compute_finestra_1a(_sample_input())
    r2 = compute_finestra_1a(_sample_input())
    assert r1.snapshot_hash is not None
    assert r1.snapshot_hash == r2.snapshot_hash


def test_snapshot_hash_changes_when_price_changes():
    r1 = compute_finestra_1a(_sample_input())
    r2 = compute_finestra_1a(_sample_input(P_5103=Decimal("5.00")))
    assert r1.snapshot_hash != r2.snapshot_hash


# --------------------------------------------------------------------
# DISPLAY rounding — only aggregates
# --------------------------------------------------------------------
def test_display_dict_rounds_only_aggregates_and_hides_none():
    r = compute_finestra_1a(_sample_input())
    d = display_dict(r)
    # Aggregate: 2 decimals
    assert isinstance(d["sale_price"], float)
    assert round(d["sale_price"], 2) == d["sale_price"]
    # Intermediate glass area is NOT clamped to 2 decimals
    assert d["glass_real_sqm"] == 0.898036
    assert d["snapshot_hash"] == r.snapshot_hash


def test_recipe_code_constant():
    assert FINESTRA_1A_CODE == "finestra_1a_5103_12130"
