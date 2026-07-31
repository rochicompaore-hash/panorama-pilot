"""AUDIT v1 · Sez 20 · Validazione economica esplicita.

Per ogni test del motore economico mostra:
- input
- quantità calcolate
- unità di misura
- prezzo unitario
- versione del listino
- formula applicata
- costo componente
- costo materiali
- costo manodopera
- costi servizi
- costo interno totale
- margine
- sconto
- prezzo finale

Verifica che:
    sale_price = total_internal_cost * (1 + margin_percentage / 100) - discount

Nota terminologica (P0 audit):
Il campo del sistema si chiama `margin_pct` MA la formula è markup-on-cost:
    sale_before_discount = total_internal * (1 + margin_pct/100)
Non è un "margine sul prezzo di vendita" (sarebbe = internal / (1 - margin/100)).
È un **markup percentuale sul costo interno**. Il campo dovrebbe essere rinominato
`markup_pct` per correttezza terminologica — documentato come tech-debt.
"""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP

import pytest


def test_sez20_economic_validation_shows_all_fields_full_apribile():
    """Verifica esplicita di TUTTI i campi economici per finestra 1 anta apribile."""
    from app.services.recipes.commercial_perimeter import compute_perimeter, PerimeterInput

    # ---- INPUT ESPLICITO (P6: nessun valore inventato) ----
    inp = PerimeterInput(
        L_mm=900, H_mm=1500,
        number_of_sashes=1, window_type="apribile",
        color_code="BIANCO", is_color_premium=False,
        # Prezzi componenti (€/ml)
        P_FRAME=Decimal("6.50"),
        P_FRAME_REINFORCEMENT=Decimal("2.80"),
        P_SASH=Decimal("7.20"),
        P_SASH_REINFORCEMENT=Decimal("3.20"),
        P_GLAZING_BEAD=Decimal("1.10"),
        P_MEETING_STILE=Decimal("8.50"),
        P_MEETING_STILE_REINFORCEMENT=Decimal("3.40"),
        # Sfrido (%) — default 0 (nessuna maggiorazione)
        WASTE_FRAME=Decimal("0"), WASTE_FRAME_REINFORCEMENT=Decimal("0"),
        WASTE_SASH=Decimal("0"), WASTE_SASH_REINFORCEMENT=Decimal("0"),
        WASTE_GLAZING_BEAD=Decimal("0"), WASTE_MEETING_STILE=Decimal("0"),
        # Vetro
        glass_recipe_resolved=True,
        glass_width_mm=694, glass_height_mm=1294, glass_quantity=1,
        P_GLASS_SQM=Decimal("76.00"), MIN_GLASS_SQM=Decimal("0.50"),
        # Ferramenta
        P_HARDWARE=Decimal("45.00"),
        # Altri componenti (dichiarati zero)
        additional_material_cost=Decimal("0"),
        additional_declared_zero=True,
        # Manodopera
        hourly_cost=Decimal("30.00"),
        production_time_minutes=Decimal("30"),
        # Servizi
        installation_cost=Decimal("50.00"),
        transport_cost=Decimal("15.00"),
        disposal_cost=Decimal("0"),
        accessory_cost=Decimal("0"),
        installation_declared_zero=False,
        # Margine/sconto
        margin_pct=Decimal("40"),  # NOTA: è markup sul costo (vedi docstring)
        discount_amount=Decimal("0"),
        premium_pct=Decimal("6"),
    )
    r = compute_perimeter(inp)
    assert r.pricing_status == "ok", f"Errori: {r.blocking_errors}"

    # ---- QUANTITÀ CALCOLATE ----
    L_m, H_m = Decimal("0.9"), Decimal("1.5")
    ext = 2 * (L_m + H_m)  # 4.8 m
    assert r.external_perimeter_ml == ext, f"external_perimeter atteso {ext}, ottenuto {r.external_perimeter_ml}"
    assert r.sash_perimeter_ml == ext  # 1 anta, no meeting stile
    # Meeting stile: 0 con 1 anta
    assert r.meeting_stile_ml == Decimal("0")

    # ---- VETRO ----
    # area = (694 * 1294) / 1_000_000 = 0.898036 m²
    # billable = max(0.898036, 0.50) = 0.898036
    area = Decimal("694") * Decimal("1294") / Decimal("1_000_000")
    assert r.glass_billable_sqm == area
    # glass_cost = 0.898036 * 1 * 76 = 68.25
    expected_glass = area * Decimal("1") * Decimal("76")
    assert r.component_costs["glass_cost"] == expected_glass, (
        f"glass_cost {r.component_costs['glass_cost']} != atteso {expected_glass}"
    )

    # ---- BREAKDOWN COMPONENTI (verifica presenza + non-zero per apribile) ----
    for key in ("frame_cost", "frame_reinforcement_cost", "sash_cost",
                 "sash_reinforcement_cost", "glazing_bead_cost", "glass_cost",
                 "hardware_cost", "meeting_stile_cost", "meeting_stile_reinforcement_cost"):
        assert key in r.component_costs, f"chiave mancante: {key}"
    # 1-anta apribile → meeting_stile non conteggiato (0 ml)
    assert r.component_costs["meeting_stile_cost"] == Decimal("0")
    # Ferramenta = 45 (fisso)
    assert r.component_costs["hardware_cost"] == Decimal("45.00")

    # ---- MANODOPERA ----
    # 30 min / 60 * 30 €/h = 15 €
    assert r.labor_cost == Decimal("15.00") or r.labor_cost == Decimal("15"), (
        f"labor_cost atteso 15, ottenuto {r.labor_cost}"
    )

    # ---- SERVIZI ----
    # 50 install + 15 transport + 0 disposal + 0 accessory = 65
    assert r.service_cost == Decimal("65") or r.service_cost == Decimal("65.00"), (
        f"service_cost atteso 65, ottenuto {r.service_cost}"
    )

    # ---- MARGINE / MARKUP ----
    # NB: `margin_pct=40` interpretato come markup sul costo:
    #     sale_before = internal * (1 + 40/100) = internal * 1.4
    assert r.margin_pct == Decimal("40")

    # ---- VERIFICA FORMULA VENDITA ----
    # sale_before_discount = total_internal_cost * (1 + margin_pct/100)
    expected_sale_before = r.total_internal_cost * (Decimal("1") + Decimal("40") / Decimal("100"))
    assert r.sale_price_before_discount == expected_sale_before

    # sale_price = sale_before - discount
    assert r.sale_price == expected_sale_before - Decimal("0")

    # ---- SNAPSHOT HASH DETERMINISTICO ----
    r2 = compute_perimeter(inp)
    # Il motore espone `snapshot_hash` sul PerimeterResult
    assert r.snapshot_hash is not None, "snapshot_hash non generato"
    assert r.snapshot_hash == r2.snapshot_hash, (
        f"snapshot_hash NON deterministico: {r.snapshot_hash} vs {r2.snapshot_hash}"
    )
    # Doppia verifica: costi identici su chiamate ripetute
    assert r.sale_price == r2.sale_price
    assert r.total_internal_cost == r2.total_internal_cost
    assert r.component_costs == r2.component_costs

    # ---- STAMPA REPORT ECONOMICO (per audit trail visibile) ----
    print("\n" + "=" * 70)
    print("SEZ 20 · VALIDAZIONE ECONOMICA — Finestra 1 anta apribile 900×1500")
    print("=" * 70)
    print(f"INPUT:")
    print(f"  Dimensioni: {inp.L_mm}×{inp.H_mm} mm | ante: {inp.number_of_sashes}")
    print(f"  Colore: {inp.color_code} | premium: {inp.is_color_premium}")
    print()
    print(f"QUANTITÀ CALCOLATE:")
    print(f"  Perimetro esterno: {r.external_perimeter_ml} ml")
    print(f"  Perimetro anta:    {r.sash_perimeter_ml} ml")
    print(f"  Meeting stile:     {r.meeting_stile_ml} ml")
    print(f"  Vetro:             {r.glass_billable_sqm} m² × {inp.glass_quantity}")
    print()
    print(f"COMPONENTI (€):")
    total_materials = Decimal("0")
    for k, v in r.component_costs.items():
        v_q = v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        print(f"  {k:35s} {v_q:>10}")
        total_materials += v
    print(f"  {'MATERIALS_TOTAL':35s} {total_materials.quantize(Decimal('0.01')):>10}")
    print()
    print(f"LAVORAZIONE / SERVIZI (€):")
    print(f"  labor_cost:        {r.labor_cost.quantize(Decimal('0.01'))}")
    print(f"  service_cost:      {r.service_cost.quantize(Decimal('0.01'))}")
    print(f"  production_cost:   {r.production_cost.quantize(Decimal('0.01'))}")
    print()
    print(f"RISULTATO ECONOMICO (€):")
    print(f"  total_internal_cost:       {r.total_internal_cost.quantize(Decimal('0.01'))}")
    print(f"  margin_pct (markup):       {r.margin_pct}%")
    print(f"  sale_price_before_discount:{r.sale_price_before_discount.quantize(Decimal('0.01'))}")
    print(f"  discount:                  {r.discount}")
    print(f"  SALE_PRICE (finale):       {r.sale_price.quantize(Decimal('0.01'))}")
    print()
    print(f"SNAPSHOT HASH: {r.snapshot_hash}")
    print(f"SNAPSHOT DETERMINISTICO: sale_price stabile su chiamate ripetute")
    print("=" * 70)


def test_sez20_terminology_markup_vs_margin_documented():
    """Il campo `margin_pct` si comporta come markup sul costo, NON margine sul ricavo.

    - Markup sul costo:   sale = cost * (1 + m/100)     → margin_pct=40 → sale = cost*1.4
    - Margine sul ricavo: sale = cost / (1 - m/100)     → margin_pct=40 → sale = cost/0.6

    Questo test rende esplicito il comportamento attuale e ne fissa la semantica
    fino a decisione contraria dell'utente (rinomina in `markup_pct`).
    """
    from decimal import Decimal
    from app.services.recipes.commercial_perimeter import compute_perimeter, PerimeterInput

    inp = PerimeterInput(
        L_mm=900, H_mm=1500, number_of_sashes=1, window_type="apribile",
        color_code="BIANCO", is_color_premium=False,
        P_FRAME=Decimal("10"), P_FRAME_REINFORCEMENT=Decimal("0"),
        P_SASH=Decimal("0"), P_SASH_REINFORCEMENT=Decimal("0"),
        P_GLAZING_BEAD=Decimal("0"), P_MEETING_STILE=Decimal("0"),
        P_MEETING_STILE_REINFORCEMENT=Decimal("0"),
        WASTE_FRAME=Decimal("0"), WASTE_FRAME_REINFORCEMENT=Decimal("0"),
        WASTE_SASH=Decimal("0"), WASTE_SASH_REINFORCEMENT=Decimal("0"),
        WASTE_GLAZING_BEAD=Decimal("0"), WASTE_MEETING_STILE=Decimal("0"),
        glass_recipe_resolved=False,
        glass_width_mm=0, glass_height_mm=0, glass_quantity=0,
        P_GLASS_SQM=Decimal("0"), MIN_GLASS_SQM=Decimal("0"),
        P_HARDWARE=Decimal("100"),
        additional_material_cost=Decimal("0"), additional_declared_zero=True,
        hourly_cost=Decimal("0"), production_time_minutes=Decimal("0"),
        installation_cost=Decimal("0"), transport_cost=Decimal("0"),
        disposal_cost=Decimal("0"), accessory_cost=Decimal("0"),
        installation_declared_zero=True,
        margin_pct=Decimal("40"), discount_amount=Decimal("0"),
        premium_pct=Decimal("6"),
    )
    r = compute_perimeter(inp)
    # Solo per verifica semantica
    if r.pricing_status == "ok":
        cost = r.total_internal_cost
        # Comportamento markup-on-cost (attuale)
        expected_markup = cost * Decimal("1.4")
        assert r.sale_price_before_discount == expected_markup, (
            "Il sistema applica markup sul costo, non margine sul ricavo. "
            "Se vuoi cambiare la semantica, aprire ticket dedicato."
        )
