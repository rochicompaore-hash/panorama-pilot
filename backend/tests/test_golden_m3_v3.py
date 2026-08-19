"""Golden Test M3 — Enerhia Operating Core.

Verifica riga-per-riga il motore Unified Pricing v3 per il caso di riferimento:
  ProEvolution · WINDOW · 1 sash · 1200×1400 · WHITE_MASS · DOUBLE_STANDARD · qty=1

Come richiesto dal Master Plan (sez. Milestone 3):
- NON forzare il risultato
- Deve emergere dalle componenti corrette
- Confrontare riga-per-riga e mostrare il delta vs Excel

Riferimento target: total production cost ≈ 310.56 € (approssimativo, non canonico).
Il test NON fallisce se il totale differisce; produce solo un report dettagliato.
Verifica invece le regole ufficiali:
- Hardware = 60 € (WINDOW 1 sash)
- Glass = 76 €/m² × billable
- Labor = 0.75 h × 180 €/h = 135 €
- Foil surcharge = 0 (WHITE_MASS)
"""
from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from typing import Any, Dict

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


load_dotenv()

TENANT_ID = "5e353147-2416-4ef7-aa3f-3e0007435c42"


def _get_db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client, client[os.environ["DB_NAME"]]


async def _compute(db, *, width_mm=1200, height_mm=1400) -> Dict[str, Any]:
    from app.services.pricing_v3.orchestrator import compute_pricing
    from app.services.pricing_v3.models import PricingRequest

    req = PricingRequest(
        tenant_id=TENANT_ID,
        product_key="PROEVOLUTION",
        window_type="WINDOW",
        number_of_sashes=1,
        width_mm=width_mm,
        height_mm=height_mm,
        glass_type="DOUBLE_STANDARD",
        color_internal="WHITE_MASS",
        color_external="WHITE_MASS",
        quantity=1,
    )
    result = await compute_pricing(req, db=db)
    # Convert PricingResult to dict-like access
    return {
        "pricing_status": result.pricing_status,
        "blocking_errors": result.blocking_errors,
        "technical_snapshot": result.technical_snapshot,
        "commercial_snapshot": result.commercial_snapshot,
    }


def test_gt_real_window_1sash_1200x1400():
    """Golden test GT-REAL riga-per-riga vs Excel target ≈ 310.56 €."""
    async def _run():
        client, db = _get_db()
        try:
            result = await _compute(db)
            return result
        finally:
            client.close()
    result = asyncio.run(_run())

    assert result["pricing_status"] == "ok", result.get("blocking_errors")
    tech = result["technical_snapshot"]

    print("\n=== GT-REAL: ProEvolution WINDOW 1 sash 1200×1400 DOUBLE_STANDARD ===")
    print(f"{'Component':<25} {'qty':>10} {'unit €':>8} {'total €':>10}")
    for c in tech["components"]:
        print(f"  {c['role']:<23} {c['quantity_value']:>10} {c['unit_cost']:>8} {c['total_cost']:>10}")

    print(f"\n  {'MATERIAL COST':<23} {'':>10} {'':>8} {tech['material_cost']:>10}")
    print(f"  {'GLASS COST':<23} {'':>10} {'':>8} {tech['glass_cost']:>10}"
          f"  (dims={tech['glass_dimensions']})")
    print(f"  {'HARDWARE COST':<23} {'':>10} {'':>8} {tech['hardware_cost']:>10}")
    print(f"  {'LABOR COST':<23} {tech['production_time_hours']!s:>10} "
          f"{tech['hourly_workshop_cost']!s:>8} {tech['labor_cost']:>10}")
    print(f"  {'FOIL SURCHARGE':<23} {'':>10} {'':>8} {tech['foil_surcharge']:>10}")
    print(f"  {'='*60}")
    print(f"  {'TOTAL INTERNAL':<23} {'':>10} {'':>8} {tech['total_internal_cost']:>10}")
    print(f"  {'EXCEL TARGET (approx)':<23} {'':>10} {'':>8} {'310.56':>10}")

    delta = Decimal(str(tech['total_internal_cost'])) - Decimal("310.56")
    print(f"  {'DELTA (v3 - Excel)':<23} {'':>10} {'':>8} {delta:>10}")

    # Verifiche ufficiali (BR-05, BR-07, BR-08)
    assert Decimal(str(tech["hardware_cost"])) == Decimal("60"), \
        f"Hardware deve essere 60 € (WINDOW 1 sash), trovato {tech['hardware_cost']}"
    assert Decimal(str(tech["hourly_workshop_cost"])) == Decimal("180"), \
        f"Workshop cost deve essere 180 €/h, trovato {tech['hourly_workshop_cost']}"
    assert Decimal(str(tech["production_time_hours"])) == Decimal("0.75"), \
        f"Tempo produzione WINDOW_1_SASH deve essere 0.75 h, trovato {tech['production_time_hours']}"
    assert Decimal(str(tech["labor_cost"])) == Decimal("135"), \
        f"Labor cost = 0.75 × 180 = 135, trovato {tech['labor_cost']}"
    assert Decimal(str(tech["foil_surcharge"])) == 0, \
        f"WHITE_MASS non attiva pellicolato, trovato {tech['foil_surcharge']}"

    # Verifica glass_price 76 €/m² e min 0.5m²
    gd = tech["glass_dimensions"]
    assert gd["min_billable_sqm"] == 0.5, f"Min billable deve essere 0.5, trovato {gd['min_billable_sqm']}"
    expected_glass = Decimal("1.186836") * Decimal("76")
    assert abs(Decimal(str(tech["glass_cost"])) - expected_glass) < Decimal("0.01"), \
        f"Glass cost atteso ≈ {expected_glass}, trovato {tech['glass_cost']}"


def test_hardware_60_not_76():
    """Non deve essere più utilizzato il vecchio valore 76 € per hardware WINDOW 1 sash."""
    async def _run():
        client, db = _get_db()
        try:
            return await _compute(db)
        finally:
            client.close()
    result = asyncio.run(_run())
    tech = result["technical_snapshot"]
    hw = Decimal(str(tech["hardware_cost"]))
    assert hw != Decimal("76"), "Vecchio hardware 76 € rilevato: motore non aggiornato."
    assert hw == Decimal("60"), f"Hardware atteso 60 €, trovato {hw}"


def test_glass_min_billable_applied():
    """Verifica che il min 0.5 m² per pannello sia applicato quando l'area reale < 0.5."""
    async def _run():
        client, db = _get_db()
        try:
            return await _compute(db, width_mm=600, height_mm=700)
        finally:
            client.close()
    result = asyncio.run(_run())
    tech = result["technical_snapshot"]
    gd = tech["glass_dimensions"]
    assert gd["real_area_sqm"] < 0.5, gd["real_area_sqm"]
    assert gd["billable_area_sqm"] == 0.5, \
        f"Billable deve essere 0.5 (minimo), trovato {gd['billable_area_sqm']}"
    assert Decimal(str(tech["glass_cost"])) == Decimal("38.0"), tech["glass_cost"]
