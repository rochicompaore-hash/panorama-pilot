"""Installation Mode + Standard Service Resolver V1 tests (msg 393)."""
from __future__ import annotations

import pytest

from app.services.service_resolver import (
    resolve_window_install_code,
    resolve_cassonetto_install_code,
    resolve_mosquito_install_code,
    resolve_install_code_for_line,
    resolve_disposal_code_for_line,
    bucket_for_service_type,
    compute_services_totals,
    CATEGORY_INSTALL_CODES,
    DISMANTLING_CODES,
    DISPOSAL_CODES,
    SERVICE_POLICY_VERSION,
    INSTALLATION_MODES,
    POLICY_MODES,
)
from app.services.margin_engine import (
    aggregate_costs_from_lines,
    compute_financial_snapshot,
)


class TestWindowResolver:
    """§1-§5 msg 393 — priorità deterministica finestra/porta."""

    @pytest.mark.parametrize("cfg,expected", [
        # Underlight prende precedenza su tutto
        ({"underlight_type": "DOUBLE", "window_type": "WINDOW", "number_of_sashes": 4}, "INSTALL_WINDOW_UNDERLIGHT_DOUBLE"),
        ({"underlight_type": "SINGLE", "window_type": "SLIDING"}, "INSTALL_WINDOW_UNDERLIGHT"),
        # Window type
        ({"window_type": "SLIDING", "number_of_sashes": 2}, "INSTALL_SLIDING"),
        ({"window_type": "FIXED"}, "INSTALL_FIXED_WINDOW"),
        ({"window_type": "VASISTAS"}, "INSTALL_VASISTAS"),
        # By sash count
        ({"window_type": "WINDOW", "number_of_sashes": 1}, "INSTALL_WINDOW_1_2_SASH"),
        ({"window_type": "WINDOW", "number_of_sashes": 2}, "INSTALL_WINDOW_1_2_SASH"),
        ({"window_type": "DOOR_WINDOW", "number_of_sashes": 3}, "INSTALL_WINDOW_3_SASH"),
        ({"window_type": "WINDOW", "number_of_sashes": 4}, "INSTALL_WINDOW_4_SASH"),
        # Underlight NONE explicit = same as absent
        ({"underlight_type": "NONE", "window_type": "WINDOW", "number_of_sashes": 3}, "INSTALL_WINDOW_3_SASH"),
    ])
    def test_priority(self, cfg, expected):
        assert resolve_window_install_code(cfg) == expected

    def test_backward_compat_underlight_absent(self):
        # Field assente → NONE (§2 msg 393)
        assert resolve_window_install_code({"window_type": "WINDOW", "number_of_sashes": 2}) == "INSTALL_WINDOW_1_2_SASH"


class TestCategoryResolver:
    def test_cassonetto_single(self):
        assert resolve_cassonetto_install_code({}) == "INSTALL_ROLLER_BOX_SINGLE"

    def test_cassonetto_double(self):
        assert resolve_cassonetto_install_code({"assembly_type": "DOUBLE"}) == "INSTALL_ROLLER_BOX_DOUBLE"

    def test_mosquito_single(self):
        assert resolve_mosquito_install_code({}) == "INSTALL_MOSQUITO"

    def test_mosquito_double(self):
        assert resolve_mosquito_install_code({"assembly_type": "DOUBLE"}) == "INSTALL_MOSQUITO_DOUBLE"

    @pytest.mark.parametrize("cat,expected", [
        ("TAPPARELLE", "INSTALL_ROLLER_KIT"),
        ("PERSIANE_SCURI", "INSTALL_SHUTTER_1_2_SASH"),
        ("PORTE_BLINDATE", "INSTALL_ARMORED_DOOR"),
        ("PORTE_INTERNE", "INSTALL_INTERIOR_DOOR_HINGED"),
    ])
    def test_by_category(self, cat, expected):
        line = {"category_code": cat, "pricing_model": "AREA", "configuration_snapshot": {}}
        assert resolve_install_code_for_line(line) == expected


class TestNoInstallForServices:
    """§7 msg 393 — servizi/accessori NON generano auto-install ricorsivo."""

    @pytest.mark.parametrize("cat", ["SERVIZI", "MONTAGGI_POSA", "ACCESSORI"])
    def test_service_lines_no_install(self, cat):
        line = {"category_code": cat, "pricing_model": "PER_ITEM"}
        assert resolve_install_code_for_line(line) is None

    def test_legacy_installation_line_no_recurse(self):
        line = {"category": "installation", "pricing_model": "PER_ITEM"}
        assert resolve_install_code_for_line(line) is None


class TestBucketMapping:
    """§22 msg 393 — POSA/MOTORIZZAZIONE → INSTALLATION_COST, altri → OTHER."""

    def test_posa_installation(self):
        assert bucket_for_service_type("POSA") == "INSTALLATION"

    def test_motorizzazione_installation(self):
        assert bucket_for_service_type("MOTORIZZAZIONE") == "INSTALLATION"

    def test_smontaggio_other(self):
        assert bucket_for_service_type("SMONTAGGIO") == "OTHER"

    def test_smaltimento_other(self):
        assert bucket_for_service_type("SMALTIMENTO") == "OTHER"


class TestServicesTotals:
    def test_sum_automatic_and_manual(self):
        auto = [{"sale_price_total": 150.0, "internal_cost_total": 130.0}]
        manual = [{"sale_price_total": 50.0, "internal_cost_total": 30.0}]
        t = compute_services_totals(auto, manual)
        assert t["standard_services_sale_total"] == 200.0
        assert t["standard_services_internal_cost_total"] == 160.0


class TestMarginEngineWiring:
    """§22 msg 393 — Installation Mode alimenta correttamente il Margin Engine."""

    def test_installation_cost_from_line_services(self):
        # Product cost 800, POSA service cost 130 → SUPPLY=800, INSTALLATION=130
        lines = [{
            "category": "window", "category_code": "FINESTRE", "quantity": 1,
            "technical_snapshot": {"total_internal_cost": 800.0},
            "automatic_services": [{
                "service_type": "POSA",
                "sale_price_total": 150.0, "internal_cost_total": 130.0,
            }],
        }]
        c = aggregate_costs_from_lines(lines)
        assert c["supply_cost"] == 800.0
        assert c["installation_cost"] == 130.0
        assert c["other_direct_costs"] == 0.0

    def test_disposal_goes_to_other(self):
        lines = [{
            "category": "window", "category_code": "FINESTRE", "quantity": 1,
            "technical_snapshot": {"total_internal_cost": 800.0},
            "automatic_services": [
                {"service_type": "POSA", "internal_cost_total": 130.0, "sale_price_total": 150.0},
                {"service_type": "SMALTIMENTO", "internal_cost_total": 20.0, "sale_price_total": 40.0},
                {"service_type": "SMONTAGGIO", "internal_cost_total": 20.0, "sale_price_total": 40.0},
            ],
        }]
        c = aggregate_costs_from_lines(lines)
        assert c["installation_cost"] == 130.0
        assert c["other_direct_costs"] == 40.0  # smaltimento 20 + smontaggio 20

    def test_e2e_financial_snapshot(self):
        # WINDOW 1250 sale (cost 800) + POSA 150 sale (cost 130) = 1400 rev, 930 cost
        # margin = (1400-800-130)/1400 = 33.57% → OTTIMO
        quote = {
            "subtotal": 1400.0, "total": 1708.0,
            "lines": [{
                "category": "window", "category_code": "FINESTRE", "quantity": 1,
                "technical_snapshot": {"total_internal_cost": 800.0},
                "automatic_services": [{
                    "service_type": "POSA",
                    "sale_price_total": 150.0, "internal_cost_total": 130.0,
                }],
            }],
        }
        fs = compute_financial_snapshot(quote)
        assert fs["supply_cost"] == 800.0
        assert fs["installation_cost"] == 130.0
        assert fs["margin_band"] == "OTTIMO"
        assert fs["commission_rate"] == 0.15


class TestPolicyEnums:
    def test_installation_modes(self):
        assert INSTALLATION_MODES == {"SUPPLY_ONLY", "SUPPLY_AND_INSTALLATION"}

    def test_policy_modes(self):
        assert POLICY_MODES == {"INCLUDED", "EXCLUDED", "NOT_APPLICABLE"}

    def test_policy_version_documented(self):
        assert SERVICE_POLICY_VERSION == "installation_v1_2026_02"


class TestDispatchTables:
    """Guardia sui mapping esposti — modifica intenzionale richiede aggiornamento test."""

    def test_dismantling_covers_5_categories(self):
        for cat in ("FINESTRE", "PORTEFINESTRE", "ZANZARIERE", "TAPPARELLE",
                    "PERSIANE_SCURI", "CASSONETTI"):
            assert cat in DISMANTLING_CODES

    def test_disposal_covers_5_categories(self):
        for cat in ("FINESTRE", "ZANZARIERE", "TAPPARELLE", "PERSIANE_SCURI", "CASSONETTI"):
            assert cat in DISPOSAL_CODES

    def test_disposal_code_lookup(self):
        assert resolve_disposal_code_for_line({"category_code": "FINESTRE"}) == "DISPOSAL_WINDOW"
        assert resolve_disposal_code_for_line({"category_code": "TAPPARELLE"}) == "DISPOSAL_ROLLER_KIT"
