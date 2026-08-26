"""P0 msg 395 + 396 + ENEA safety guard — regression permanenti."""
from __future__ import annotations

import pytest

from app.services.margin_engine import (
    compute_financial_snapshot,
    resolve_band,
    DEFAULT_WITHHOLDING_RATE,
    COMMERCIAL_SAFE_KEYS,
    redact_financial_snapshot_for_role,
)


# =====================================================================
# msg 395 §13 — Ritenuta d'acconto ha influenza sulla fascia
# =====================================================================
class TestWithholdingBandFlip:

    def _quote(self, withholding: bool):
        # NET=10000 SUPPLY=5000 INSTALL=1000 OTHER=0
        return {
            "subtotal": 10_000.0, "total": 12_200.0,
            "withholding_applicable": withholding,
            "lines": [
                {"category": "window", "quantity": 1,
                 "technical_snapshot": {"total_internal_cost": 5_000.0}},
                {"category": "installation", "quantity": 1, "internal_cost": 1_000.0},
            ],
        }

    def test_without_withholding_ottimo(self):
        """Senza ritenuta: margine 40% → OTTIMO 15% (§13)."""
        fs = compute_financial_snapshot(self._quote(False))
        assert fs["withholding_applicable"] is False
        assert fs["withholding_cost"] == 0.0
        assert fs["pre_commission_margin"] == 40.0
        assert fs["margin_band"] == "OTTIMO"
        assert fs["commission_rate"] == 0.15

    def test_with_withholding_flips_to_buono(self):
        """Con ritenuta 11%: margine 29% → BUONO 10% (§5 esempio)."""
        fs = compute_financial_snapshot(self._quote(True))
        assert fs["withholding_applicable"] is True
        assert fs["withholding_rate"] == 0.11
        assert fs["withholding_cost"] == 1_100.0
        assert fs["pre_commission_margin"] == 29.0
        assert fs["margin_band"] == "BUONO"
        assert fs["commission_rate"] == 0.10
        # COMMISSION_BASE resta net_revenue (§6)
        assert fs["commission_gross"] == 1_000.0


# =====================================================================
# msg 396 §11 — Tachometer = FINAL_COMPANY_MARGIN (post-commissione)
# =====================================================================
class TestTachometerFinalCompanyMargin:

    def test_msg396_example_exact(self):
        """§5/§11 msg 396 — NET=10000 SUPPLY=4000 INSTALL=1000 WH=1100
           PRE=39% → OTTIMO 15% → COMM=1500 → FINAL=2400 (24%).
           Tachometer DEVE mostrare 24%, NON 39%."""
        quote = {
            "subtotal": 10_000.0, "total": 12_200.0,
            "withholding_applicable": True,
            "lines": [
                {"category": "window", "quantity": 1,
                 "technical_snapshot": {"total_internal_cost": 4_000.0}},
                {"category": "installation", "quantity": 1, "internal_cost": 1_000.0},
            ],
        }
        fs = compute_financial_snapshot(quote)
        # Commission engine input (§12) = PRE_COMMISSION_MARGIN
        assert fs["pre_commission_margin"] == 39.0
        assert fs["commission_rate"] == 0.15
        assert fs["commission_gross"] == 1_500.0
        # Tachometer authoritative output (§4/§13)
        assert fs["final_company_contribution"] == 2_400.0
        assert fs["final_company_margin"] == 24.0
        assert fs["tachometer_value"] == 24.0
        # tachometer_value MUST equal final_company_margin (§13)
        assert fs["tachometer_value"] == fs["final_company_margin"]
        assert fs["tachometer_value"] != fs["pre_commission_margin"]


# =====================================================================
# ENEA safety guard (msg 395 §3-§5)
# =====================================================================
class TestEneaSafetyGuard:

    def _quote_with_enea(self, enea=True, missing_cost=True):
        q = {
            "subtotal": 10_100.0, "total": 12_322.0,
            "lines": [
                {"category": "window", "quantity": 1,
                 "technical_snapshot": {"total_internal_cost": 5_000.0}},
                {"category": "installation", "quantity": 1, "internal_cost": 1_000.0},
            ],
        }
        if enea:
            q["lines"].append({
                "id": "enea-standard", "category": "extra",
                "category_code": "ENEA_PRACTICE",
                "quantity": 1, "base_price": 100.0, "subtotal_line": 100.0,
                "enea_practice": True,
                "internal_cost": None if missing_cost else 30.0,
                "simple_snapshot": {"internal_cost_status": "NEEDS_PO_COSTING" if missing_cost else "ACTIVE"},
            })
        return q

    def test_enea_missing_cost_marks_incomplete(self):
        fs = compute_financial_snapshot(self._quote_with_enea(enea=True, missing_cost=True))
        assert fs["financial_snapshot_status"] == "INCOMPLETE"
        assert "MISSING_INTERNAL_COST_ENEA" in fs["financial_snapshot_errors"]
        assert fs["commission_status"] == "NEEDS_COST_CONFIGURATION"

    def test_no_enea_snapshot_complete(self):
        fs = compute_financial_snapshot(self._quote_with_enea(enea=False))
        assert fs["financial_snapshot_status"] == "COMPLETE"
        assert fs["financial_snapshot_errors"] == []

    def test_enea_with_configured_cost_complete(self):
        fs = compute_financial_snapshot(self._quote_with_enea(enea=True, missing_cost=False))
        assert fs["financial_snapshot_status"] == "COMPLETE"


# =====================================================================
# RBAC: tachometer_value visibile al Commerciale, pre_commission_margin NO
# =====================================================================
class TestRBACTachometerVisibility:

    def test_commerciale_sees_tachometer_not_pre_commission(self):
        fs = compute_financial_snapshot({
            "subtotal": 10_000.0, "total": 10_000.0,
            "withholding_applicable": True,
            "lines": [
                {"category": "window", "quantity": 1,
                 "technical_snapshot": {"total_internal_cost": 4_000.0}},
                {"category": "installation", "quantity": 1, "internal_cost": 1_000.0},
            ],
        })
        red = redact_financial_snapshot_for_role(fs, is_admin=False)
        assert "tachometer_value" in red
        assert red["tachometer_value"] == fs["final_company_margin"]
        assert "pre_commission_margin" not in red  # commerciale non vede il valore tecnico
        assert "supply_cost" not in red
        assert "installation_cost" not in red
        assert "withholding_cost" not in red

    def test_admin_sees_all_breakdown(self):
        fs = compute_financial_snapshot({
            "subtotal": 10_000.0, "total": 10_000.0,
            "withholding_applicable": True,
            "lines": [{"category": "window", "quantity": 1, "internal_cost": 4_000.0}],
        })
        red = redact_financial_snapshot_for_role(fs, is_admin=True)
        for k in ("supply_cost", "installation_cost", "withholding_cost",
                  "pre_commission_margin", "final_company_margin", "tachometer_value"):
            assert k in red, f"admin should see {k}"


# =====================================================================
# msg 396 §14 — WITHHOLDING è bucket separato (non entra in SUPPLY o INSTALL)
# =====================================================================
class TestWithholdingSeparateBucket:

    def test_withholding_not_in_supply(self):
        fs = compute_financial_snapshot({
            "subtotal": 10_000.0, "total": 10_000.0,
            "withholding_applicable": True,
            "lines": [{"category": "window", "quantity": 1,
                       "technical_snapshot": {"total_internal_cost": 5_000.0}}],
        })
        assert fs["supply_cost"] == 5_000.0  # non 6100
        assert fs["withholding_cost"] == 1_100.0

    def test_policy_versions_advertised(self):
        fs = compute_financial_snapshot({
            "subtotal": 10_000.0, "total": 10_000.0,
            "withholding_applicable": True,
            "lines": [{"category": "window", "quantity": 1, "internal_cost": 4000.0}],
        })
        assert fs["margin_policy_version"] == "margin_policy_v2_2026_02"
        assert fs["withholding_policy_version"] == "withholding_policy_v1_2026_02"


class TestDefaults:
    def test_default_withholding_rate(self):
        assert DEFAULT_WITHHOLDING_RATE == 0.11
