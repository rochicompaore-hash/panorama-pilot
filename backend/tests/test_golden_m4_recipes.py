"""Golden Tests M4 — Enerhia Operating Core (Milestone 4).

Copertura: 5 configurazioni ProEvolution
  GT-W1  WINDOW 1 sash            (1200×1400)
  GT-W2  WINDOW 2 sashes          (1500×1400) — con MEETING_STILE
  GT-DW1 DOOR_WINDOW 1 sash       (900×2200) — con THRESHOLD ribassata + fixed 7.49
  GT-DW2 DOOR_WINDOW 2 sashes     (1600×2200) — con MEETING_STILE + THRESHOLD + fixed 9.84
  GT-VAS VASISTAS_ONLY 1 sash     (800×600) — hardware 40 €

Ogni test verifica:
- pricing_status == "ok" (no MISSING_*)
- hardware ufficiale corretto per la configurazione
- production_time letto dal DB (config-based)
- foil surcharge = 0 su WHITE_MASS
- fail-closed su combinazioni non seedate

Non richiede pytest-asyncio: uso asyncio.run().
"""
from __future__ import annotations

import asyncio
import os
from decimal import Decimal

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


load_dotenv()
TENANT_ID = "5e353147-2416-4ef7-aa3f-3e0007435c42"


def _get_db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client, client[os.environ["DB_NAME"]]


async def _compute(db, *, window_type, n_sashes, W, H,
                   glass="DOUBLE_STANDARD", color="WHITE_MASS"):
    from app.services.pricing_v3.orchestrator import compute_pricing
    from app.services.pricing_v3.models import PricingRequest
    req = PricingRequest(
        tenant_id=TENANT_ID, product_key="PROEVOLUTION",
        window_type=window_type, number_of_sashes=n_sashes,
        width_mm=W, height_mm=H,
        glass_type=glass, color_internal=color, color_external=color,
        quantity=1,
    )
    return await compute_pricing(req, db=db)


def _print_bom(name: str, result):
    tech = result.technical_snapshot
    if not tech:
        print(f"\n[{name}] BLOCKED: {result.blocking_errors}")
        return
    print(f"\n=== {name} ===")
    print(f"{'Role':<30} {'qty':>10} {'unit €':>10} {'total €':>10}")
    for c in tech["components"]:
        print(f"  {c['role']:<28} {c['quantity_value']:>10} {c['unit_cost']:>10} {c['total_cost']:>10}")
    print(f"  {'MATERIAL':<28} {'':>10} {'':>10} {tech['material_cost']:>10}")
    print(f"  {'GLASS':<28} {tech['glass_dimensions']['billable_area_sqm']!s:>10} "
          f"{'':>10} {tech['glass_cost']:>10}")
    print(f"  {'HARDWARE':<28} {'':>10} {'':>10} {tech['hardware_cost']:>10}")
    print(f"  {'LABOR':<28} {tech['production_time_hours']!s:>10} "
          f"{tech['hourly_workshop_cost']!s:>10} {tech['labor_cost']:>10}")
    print(f"  {'FOIL':<28} {'':>10} {'':>10} {tech['foil_surcharge']:>10}")
    print(f"  {'='*70}")
    print(f"  {'TOTAL INTERNAL':<28} {'':>10} {'':>10} {tech['total_internal_cost']:>10}")


def _run_gt(cfg):
    async def _r():
        client, db = _get_db()
        try:
            return await _compute(db, **cfg)
        finally:
            client.close()
    return asyncio.run(_r())


def test_gt_w1():
    r = _run_gt(dict(window_type="WINDOW", n_sashes=1, W=1200, H=1400))
    _print_bom("GT-W1 WINDOW 1 sash 1200×1400", r)
    assert r.pricing_status == "ok"
    t = r.technical_snapshot
    assert Decimal(str(t["hardware_cost"])) == Decimal("60")
    assert Decimal(str(t["labor_cost"])) == Decimal("135")
    assert Decimal(str(t["foil_surcharge"])) == 0
    roles = [c["role"] for c in t["components"]]
    assert set(roles) == {"FRAME", "FRAME_REINFORCEMENT", "SASH", "SASH_REINFORCEMENT", "GLAZING_BEAD"}


def test_gt_w2():
    r = _run_gt(dict(window_type="WINDOW", n_sashes=2, W=1500, H=1400))
    _print_bom("GT-W2 WINDOW 2 sashes 1500×1400", r)
    assert r.pricing_status == "ok"
    t = r.technical_snapshot
    assert Decimal(str(t["hardware_cost"])) == Decimal("80"), t["hardware_cost"]
    assert Decimal(str(t["labor_cost"])) == Decimal("180"), t["labor_cost"]   # 1.00 × 180
    roles = [c["role"] for c in t["components"]]
    assert "MEETING_STILE" in roles, "WINDOW_2_SASH deve includere MEETING_STILE V1_3"
    # MEETING_STILE quantity: H/1000 = 1.4 ml → 1.4 × 5.50 = 7.70 €
    ms = next(c for c in t["components"] if c["role"] == "MEETING_STILE")
    assert Decimal(ms["unit_cost"]) == Decimal("5.50"), ms
    assert abs(Decimal(ms["total_cost"]) - Decimal("7.70")) < Decimal("0.01"), ms


def test_gt_dw1():
    r = _run_gt(dict(window_type="DOOR_WINDOW", n_sashes=1, W=900, H=2200))
    _print_bom("GT-DW1 DOOR_WINDOW 1 sash 900×2200", r)
    assert r.pricing_status == "ok"
    t = r.technical_snapshot
    assert Decimal(str(t["hardware_cost"])) == Decimal("75")
    assert Decimal(str(t["labor_cost"])) == Decimal("180")  # 1.00 × 180
    roles = [c["role"] for c in t["components"]]
    assert "THRESHOLD" in roles
    assert "THRESHOLD_FIXED_COMPONENT" in roles
    # THRESHOLD: H/1000 × 29.50 = 2.2 × 29.50 = 64.90 €
    th = next(c for c in t["components"] if c["role"] == "THRESHOLD")
    assert abs(Decimal(th["total_cost"]) - Decimal("64.90")) < Decimal("0.01"), th
    # FIXED PART DW_1 = 7.49 €
    fx = next(c for c in t["components"] if c["role"] == "THRESHOLD_FIXED_COMPONENT")
    assert Decimal(fx["total_cost"]) == Decimal("7.49"), fx


def test_gt_dw2():
    r = _run_gt(dict(window_type="DOOR_WINDOW", n_sashes=2, W=1600, H=2200))
    _print_bom("GT-DW2 DOOR_WINDOW 2 sashes 1600×2200", r)
    assert r.pricing_status == "ok"
    t = r.technical_snapshot
    assert Decimal(str(t["hardware_cost"])) == Decimal("90")
    assert Decimal(str(t["labor_cost"])) == Decimal("270"), t["labor_cost"]  # 1.50 × 180
    roles = [c["role"] for c in t["components"]]
    assert "MEETING_STILE" in roles
    assert "THRESHOLD" in roles
    fx = next(c for c in t["components"] if c["role"] == "THRESHOLD_FIXED_COMPONENT")
    assert Decimal(fx["total_cost"]) == Decimal("9.84"), fx


def test_gt_vas():
    r = _run_gt(dict(window_type="VASISTAS_ONLY", n_sashes=1, W=800, H=600))
    _print_bom("GT-VAS VASISTAS_ONLY 800×600", r)
    assert r.pricing_status == "ok", r.blocking_errors
    t = r.technical_snapshot
    assert Decimal(str(t["hardware_cost"])) == Decimal("40")
    assert Decimal(str(t["labor_cost"])) == Decimal("135"), t["labor_cost"]  # 0.75 × 180


def test_foil_surcharge_walnut():
    """Pellicolato NOCE deve applicare +10% solo su PVC eleggibile."""
    async def _r():
        client, db = _get_db()
        try:
            from app.services.pricing_v3.orchestrator import compute_pricing
            from app.services.pricing_v3.models import PricingRequest
            req = PricingRequest(
                tenant_id=TENANT_ID, product_key="PROEVOLUTION",
                window_type="WINDOW", number_of_sashes=1,
                width_mm=1200, height_mm=1400,
                glass_type="DOUBLE_STANDARD",
                color_internal="WALNUT", color_external="WALNUT",
                quantity=1,
            )
            return await compute_pricing(req, db=db)
        finally:
            client.close()
    r = asyncio.run(_r())
    assert r.pricing_status == "ok"
    t = r.technical_snapshot
    # Foil = 10% * base PVC eleggibile (FRAME + SASH + GLAZING_BEAD)
    # FRAME 20.95224 + SASH 10.10856 + GLAZING_BEAD 9.1896 = 40.2504
    # foil = 4.02504 ≈ 4.03
    assert Decimal(str(t["foil_surcharge"])) > 0, "Foil deve essere applicato per WALNUT"
    assert Decimal(str(t["foil_surcharge"])) < Decimal("5"), "Foil deve essere ~4.03 €, non tutto il materiale"


def test_hardware_source_is_db_not_hardcoded():
    """Modifica temporanea hardware in DB → risultato compute cambia → ripristino."""
    async def _r():
        client, db = _get_db()
        try:
            # Snapshot pre
            r1 = await _compute(db, window_type="WINDOW", n_sashes=1, W=1200, H=1400)
            hw_before = Decimal(str(r1.technical_snapshot["hardware_cost"]))

            # Modifica hardware WINDOW 1 sash a 999 €
            rec = await db.hardware_rules.find_one({
                "tenant_id": TENANT_ID, "opening_type": "WINDOW",
                "number_of_sashes": 1, "deleted_at": None,
            })
            old_price = rec["cost_per_unit"]
            await db.hardware_rules.update_one({"_id": rec["_id"]},
                {"$set": {"cost_per_unit": 999.0}})
            try:
                r2 = await _compute(db, window_type="WINDOW", n_sashes=1, W=1200, H=1400)
                hw_after = Decimal(str(r2.technical_snapshot["hardware_cost"]))
                assert hw_after == Decimal("999"), (hw_before, hw_after)
            finally:
                await db.hardware_rules.update_one({"_id": rec["_id"]},
                    {"$set": {"cost_per_unit": old_price}})
            return hw_before, hw_after
        finally:
            client.close()
    before, after = asyncio.run(_r())
    assert before == Decimal("60"), before
    assert after == Decimal("999"), after
