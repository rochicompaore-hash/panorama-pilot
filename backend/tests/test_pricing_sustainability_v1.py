"""PRICING SUSTAINABILITY ENGINE V1 — test minimi PO §47 (A–L)."""
from __future__ import annotations

from datetime import date

import pytest

from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD
from tests.test_quote_economic_control_v2 import _login, _quote, _get, _line, BASE
from app.services import sustainability_engine as eng

TODAY = date(2026, 10, 20)
REG = {"annual_total": 720000.0, "monthly_total": 60000.0}


def _plan(jobs=20, rev=200000, secured=0.0, mode="HYBRID_MODE", target_month=60000):
    s = {**eng.DEFAULT_SETTINGS, "expected_monthly_jobs": jobs, "expected_monthly_revenue": rev, "planning_mode": mode, "target_monthly_contribution": target_month}
    return eng.planning_model(s, REG, {"secured_ytd": secured, "secured_by_month": {"10": 42000.0}}, TODAY)


def _quote_doc(net, direct):
    return {"subtotal": net, "lines": [{"category": "window", "quantity": 1, "subtotal_line": net, "line_total": net, "internal_cost": direct}], "commercial_commission_rate": None}


def _contrib(net, direct):
    return eng.quote_contribution(_quote_doc(net, direct))["contribution_margin_amount"]  # post_margin (commissione = costo diretto)


class TestPlanning:
    def test_A_jobs_changes_contribution_per_job(self):
        assert _plan(jobs=10)["required_structure_contribution_per_job"] == 6000 and _plan(jobs=20)["required_structure_contribution_per_job"] == 3000 and _plan(jobs=30)["required_structure_contribution_per_job"] == 2000
        assert _plan(jobs=30)["monthly_structure_coverage_target"] == 60000  # più commesse NON riducono il costo fisso totale

    def test_B_C_D_revenue_changes_rate(self):
        assert _plan(rev=200000)["required_structure_margin_rate_percent"] == 30 and _plan(rev=300000)["required_structure_margin_rate_percent"] == 20 and _plan(rev=400000)["required_structure_margin_rate_percent"] == 15
        assert _plan(rev=100000)["required_structure_margin_rate_percent"] == 60  # meno volume → burden aumenta

    def test_I_annual_coverage_cumulative_and_monthly_adaptation(self):
        s = {**eng.DEFAULT_SETTINGS, "structure_coverage_target_date": "2026-12-31"}
        p = eng.planning_model(s, REG, {"secured_ytd": 540000.0, "secured_by_month": {}}, TODAY)
        assert p["structure_coverage_percent"] == 75 and p["structure_residual"] == 180000 and p["months_remaining"] == 3 and p["monthly_structure_coverage_target"] == 60000
        p2 = eng.planning_model(s, REG, {"secured_ytd": 600000.0, "secured_by_month": {}}, TODAY)
        assert p2["monthly_structure_coverage_target"] == 40000  # mese sopra target → fabbisogno residuo inferiore
        p3 = eng.planning_model({**s, "target_profit": 200000}, REG, {"secured_ytd": 720000.0, "secured_by_month": {}}, TODAY)
        assert p3["phase"] == "PROFIT_GENERATION_PHASE" and p3["total_contribution_target"] == 920000 and p3["profit_target_remaining"] == 200000 and p3["forecast_coverage_date"] == "COVERED"

    def test_J_fixed_cost_change_changes_sustainability(self):
        s = {**eng.DEFAULT_SETTINGS, "expected_monthly_jobs": 20}
        low = eng.planning_model(s, {"annual_total": 360000.0}, {"secured_ytd": 0, "secured_by_month": {}}, TODAY)
        high = eng.planning_model(s, {"annual_total": 720000.0}, {"secured_ytd": 0, "secured_by_month": {}}, TODAY)
        assert high["required_structure_contribution_per_job"] == 2 * low["required_structure_contribution_per_job"]

    def test_data_quality_incomplete(self):
        p = eng.planning_model(dict(eng.DEFAULT_SETTINGS), {"annual_total": None}, {"secured_ytd": 0, "secured_by_month": {}}, TODAY)
        assert p["data_quality"] == "INCOMPLETE" and "fixed_costs" in p["missing"]
        # DATA GATE: registro reale non riconciliato → base provvisoria PO reference, KPI PROVISIONAL
        p = eng.planning_model(dict(eng.DEFAULT_SETTINGS), {"annual_total": 0, "reconciliation_status": "INCOMPLETE"}, {"secured_ytd": 0, "secured_by_month": {}}, TODAY)
        assert p["provisional"] is True and p["kpi_status"] == "PROVISIONAL / DATA_INCOMPLETE" and p["annual_fixed_cost_target"] == eng.PO_REFERENCE_ANNUAL_FIXED_COST


class TestQuoteEvaluation:
    def test_G_green_E_orange_F_red(self):
        plan = _plan(jobs=20, rev=200000)  # per job 3000, rate 30%
        c = _contrib(10000, 4000)
        g = eng.evaluate_quote(_quote_doc(10000, 4000), plan)   # contribution ≥ max(3000, 3000)
        assert g["status"] == "GREEN" and g["contribution_margin_amount"] == c and c >= 3000 and g["sustainability_gap"] == round(c - 3000, 2) and g["required_structure_contribution"] == 3000
        o = eng.evaluate_quote(_quote_doc(10000, 7800), plan)   # diretto >15% ok, contribution < 3000
        assert o["status"] == "ORANGE" and o["direct_margin_ok"] and o["sustainability_gap"] < 0
        r = eng.evaluate_quote(_quote_doc(10000, 8600), plan)   # 14% → RED
        assert r["status"] == "RED"

    def test_hybrid_shows_both_and_prices(self):
        plan = _plan(jobs=20, rev=200000)
        e = eng.evaluate_quote(_quote_doc(10000, 7000), plan)
        assert e["required_by_job_count"] == 3000 and e["required_by_revenue_volume"] == 3000 and e["hybrid_delta"] == 0
        d = e["direct_costs"]
        assert e["prices"]["direct_minimum_sustainable_price"] == round(d / 0.85, 2) and e["prices"]["structural_target_price"] == round(d + 3000, 2)
        big = eng.evaluate_quote(_quote_doc(30000, 20000), plan)
        assert big["required_by_revenue_volume"] == 9000 and big["required_by_job_count"] == 3000 and big["required_structure_contribution"] == 9000  # no divisione cieca per commesse

    def test_L_vat_excluded_and_if_accepted(self):
        plan = _plan(jobs=20, rev=200000)
        e = eng.evaluate_quote({**_quote_doc(10000, 4000), "total": 12200, "vat_amount": 2200}, plan)
        c = e["contribution_margin_amount"]
        assert e["net_revenue_ex_vat"] == 10000 and e["if_accepted"]["already_secured"] == 42000 and e["if_accepted"]["new_total"] == round(42000 + c, 2) and e["if_accepted"]["remaining"] == round(18000 - c, 2)

    def test_H_discount_impact(self):
        plan = _plan(jobs=20, rev=200000)
        d = eng.discount_impact(_quote_doc(10000, 4000), plan, 20)
        assert d["contribution_delta"] < 0 and d["before"]["status"] == "GREEN" and d["after"]["contribution_margin_amount"] == _contrib(8000, 4000)


class TestSimulator:
    def test_scenarios_and_volume_rule(self):
        assert eng.jobs_scenarios(60000)[0]["required_contribution_per_job"] == 6000
        assert eng.revenue_scenarios(60000)[2]["required_structure_percent"] == 30
        a = eng.simulate(annual_fixed_costs=720000, coverage_months=12, expected_monthly_jobs=20, expected_monthly_revenue=200000, average_ticket=None, average_contribution_pct=30, close_rate=25)
        b = eng.simulate(annual_fixed_costs=720000, coverage_months=12, expected_monthly_jobs=30, expected_monthly_revenue=300000, average_ticket=None, average_contribution_pct=10, close_rate=25)
        assert a["required_contribution_per_job"] == 3000 and a["required_structure_percent"] == 30 and a["expected_contribution_month"] == 60000
        assert b["required_contribution_per_job"] == 2000 and b["required_structure_percent"] == 20 and b["expected_contribution_month"] == 30000 < a["expected_contribution_month"]  # §34
        assert a["break_even_revenue_month"] == 200000 and a["required_pipeline"] == a["required_signed_contracts"] * 4


class TestApi:
    @pytest.fixture(scope="class")
    def admin(self):
        return _login(ADMIN_EMAIL, ADMIN_PASSWORD)

    def test_registry_settings_quote_box_rbac(self, admin):
        reg = admin.get(f"{BASE}/sustainability/fixed-costs", timeout=15).json()
        assert reg["po_reference_annual"] == 506627.60 and reg["reconciliation_status"] in ("COMPLETE", "INCOMPLETE") and reg["count"] > 0
        r = admin.put(f"{BASE}/sustainability/settings", json={"expected_monthly_jobs": 20, "expected_monthly_revenue": 200000, "planning_mode": "HYBRID_MODE", "target_monthly_contribution": 60000}, timeout=15)
        assert r.status_code == 200 and r.json()["plan"]["required_structure_contribution_per_job"] == 3000 and r.json()["plan"]["required_structure_margin_rate_percent"] == 30
        qid = _quote(admin, [_line("P", "window", 10000, 4000)])
        box = admin.get(f"{BASE}/sustainability/quote/{qid}", timeout=15).json()
        assert box["is_admin_view"] and box["status"] in ("GREEN", "ORANGE") and box["contribution_margin_amount"] > 0 and box["prices"]["structural_target_price"] is not None
        before = _get(admin, qid)["subtotal"]
        box2 = admin.get(f"{BASE}/sustainability/quote/{qid}", params={"discount_percent": 20}, timeout=15).json()
        assert box2["discount_impact"]["contribution_delta"] < 0 and _get(admin, qid)["subtotal"] == before  # NO_AUTOMATIC_PRICE_CHANGE
        comm = _login("commercial_test@infissiexpress.com", "CommTest!2026")
        cb = comm.get(f"{BASE}/sustainability/quote/{qid}", timeout=15).json()
        assert cb["is_admin_view"] is False and "contribution_margin_amount" not in cb and "prices" not in cb
        cfo = admin.get(f"{BASE}/cfo/overview", timeout=30).json()
        sus = admin.get(f"{BASE}/sustainability/overview", timeout=30).json()
        assert cfo["structure_coverage"]["secured_contribution_ytd"] == sus["plan"]["secured_contribution_ytd"]  # CFO_PRICING_PARITY
        sim = admin.post(f"{BASE}/sustainability/simulate", json={"expected_monthly_jobs": 25, "expected_monthly_revenue": 250000, "average_contribution_pct": 27}, timeout=30).json()
        assert sim["kind"] == "SIMULATION" and sim["required_contribution_per_job"] > 0


class TestCostClassification:
    def test_classes_and_structural_share(self):
        assert eng.classify_cost({"category": "rent"}) == "FIXED_STRUCTURE_COST" and eng.classify_cost({"category": "f24"}) == "CASH_ONLY_FINANCIAL_COST"
        assert eng.classify_cost({"category": "crane"}) == "DIRECT_JOB_COST" and eng.classify_cost({"category": "fuel"}) == "SEMI_VARIABLE_COST"
        assert eng.classify_cost({"category": "rent", "cost_class": "CASH_ONLY_FINANCIAL_COST"}) == "CASH_ONLY_FINANCIAL_COST"  # override manuale
        assert eng.structural_monthly({"category": "rent"}, 1000) == 1000 and eng.structural_monthly({"category": "f24"}, 1000) == 0 and eng.structural_monthly({"category": "crane"}, 1000) == 0
        assert eng.structural_monthly({"category": "energy"}, 1000) == 0 and eng.structural_monthly({"category": "energy", "fixed_component_pct": 40}, 1000) == 400 and eng.structural_monthly({"category": "energy", "fixed_component": 250}, 1000) == 250

    def test_employee_all_in_no_double_counting(self):
        assert eng.personnel_company_cost({"monthly_total_cost": 4000, "employer_charges_monthly": 1200})["monthly_company_cost"] == 4000  # default ALL_IN: oneri NON aggiunti
        assert eng.personnel_company_cost({"monthly_total_cost": 4000, "employee_cost_mode": "ALL_IN_COMPANY_COST", "employer_charges_monthly": 1200})["charges_added"] == 0
        assert eng.personnel_company_cost({"monthly_total_cost": 4000, "employee_cost_mode": "PAYROLL_ONLY", "employer_charges_monthly": 1200})["monthly_company_cost"] == 5200
        assert eng.personnel_company_cost({"monthly_total_cost": 4000, "employee_cost_mode": "PAYROLL_ONLY"})["monthly_company_cost"] == 4000  # nessuna % inventata

    def test_registry_api_by_class(self):
        admin = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
        reg = admin.get(f"{BASE}/sustainability/fixed-costs", timeout=15).json()
        assert set(reg["monthly_by_class"]) == set(eng.COST_CLASSES)
        assert all(i.get("cost_class") in eng.COST_CLASSES for i in reg["items"])
        assert reg["monthly_total"] == round(sum(i["structural_monthly"] for i in reg["items"] if i["status"] == "active" and not i["demo_data"]), 2)  # DEMO esclusi
