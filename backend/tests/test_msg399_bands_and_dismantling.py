"""Msg 399 — Nuove commission bands + Smontaggio per prodotto su misura."""
from __future__ import annotations

import pytest

from app.services.margin_engine import resolve_band


class TestBoundaryMsg399:
    """§boundary msg 399 — 30.00% ora è BUONO (non più OTTIMO)."""

    @pytest.mark.parametrize("m,expected_band,expected_rate", [
        (30.01, "OTTIMO", 0.15),
        (30.00, "BUONO", 0.10),    # ← msg 399: cambio semantica
        (29.99, "BUONO", 0.10),
        (20.00, "BUONO", 0.10),
        (19.99, "SUFFICIENTE", 0.08),
        (15.00, "SUFFICIENTE", 0.08),
        (14.99, "SCARSO", 0.05),
        ( 8.00, "SCARSO", 0.05),
        ( 7.99, "CRITICO", None),
    ])
    def test_boundary(self, m, expected_band, expected_rate):
        band, rate, _ = resolve_band(m)
        assert band == expected_band, f"{m}%: expected {expected_band}, got {band}"
        assert rate == expected_rate


class TestDismantlingPerUnit:
    """Msg 399 §3, §5, §16 — smontaggio segue qty QuoteLine."""

    def test_dismantling_qty_follows_line_qty(self):
        """Simulazione a livello di modello: materialize eredita qty QL."""
        from app.services.service_resolver import _materialize
        svc = {"_id": "svc1", "code": "REMOVE_ROLLER_KIT", "name": "Smont. kit",
               "category": "SMONTAGGIO", "pricing_unit": "PER_ITEM",
               "customer_sale_price": 40.0, "internal_reference_price": 20.0,
               "status": "ACTIVE"}
        # QL con qty=3 → REMOVE_ROLLER_KIT qty=3, totali *3
        m = _materialize(svc, "SMONTAGGIO", quantity=3, is_auto=True)
        assert m["quantity"] == 3
        assert m["sale_price_total"] == 120.0     # 3 × 40
        assert m["internal_cost_total"] == 60.0   # 3 × 20
        # Qty 1
        m1 = _materialize(svc, "SMONTAGGIO", quantity=1)
        assert m1["sale_price_total"] == 40.0
