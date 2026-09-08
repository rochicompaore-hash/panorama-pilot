"""PERSIANE — pricing golden tests (PO msg 401 §12-§23, §35).

Model AREA_PURCHASE_MULTIPLIER:
  billable = max(L×H/1e6, 1.30) PER PEZZO · rate = purchase(cat) [+99 se orientabile] · sale = billable×rate×2.5
Posa (150 €) e smontaggio (40 €/pz) separati — MAI dentro il ×2.5.
"""
from __future__ import annotations

import os
import pytest
import requests

from app.models_multi_category import SimplePricingInputs
from app.services.multi_category_pricing import SimplePricingEngine

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

PRODUCT = {
    "pricing_model": "AREA_PURCHASE_MULTIPLIER",
    "minimum_billable_quantity": 1.30,
    "pricing_config": {
        "purchase_cost_table_per_m2": {"RAL": 285.00, "WOOD": 299.00, "SPECIAL": 350.00},
        "minimum_billable_area_m2": 1.30,
        "commercial_multiplier": 2.5,
        "orientable_surcharge_per_m2": 99.00,
        "color_map": {"RAL": "RAL", "WOOD_EFFECT": "WOOD", "SPECIAL_RAFFAELLO": "SPECIAL"},
    },
}


def _calc(w, h, color, orientable, qty=1, product=PRODUCT):
    return SimplePricingEngine.compute_area_purchase_multiplier(
        product, SimplePricingInputs(width_mm=w, height_mm=h, quantity=qty, options={"color_code": color, "orientable": orientable}))


class TestSaleRatePerM2:
    @pytest.mark.parametrize("color,orientable,rate", [
        ("RAL", False, 712.50), ("WOOD_EFFECT", False, 747.50), ("SPECIAL_RAFFAELLO", False, 875.00),
        ("RAL", True, 960.00), ("WOOD_EFFECT", True, 995.00), ("SPECIAL_RAFFAELLO", True, 1122.50),
    ])
    def test_unit_sale_rate(self, color, orientable, rate):
        assert _calc(2000, 2000, color, orientable)["unit_sale_price_per_m2"] == rate


class TestMinimumGolden:
    @pytest.mark.parametrize("color,orientable,expected", [
        ("RAL", False, 926.25), ("WOOD_EFFECT", False, 971.75), ("SPECIAL_RAFFAELLO", False, 1137.50),
        ("RAL", True, 1248.00), ("WOOD_EFFECT", True, 1293.50), ("SPECIAL_RAFFAELLO", True, 1459.25),
    ])
    def test_minimum_130(self, color, orientable, expected):
        s = _calc(800, 1000, color, orientable)   # 0.80 m² < 1.30
        assert s["real_area_m2"] == 0.8 and s["billable_area_m2"] == 1.3
        assert s["unit_price_final"] == expected and s["sale_price_total"] == expected

    def test_minimum_applied_per_unit_not_aggregate(self):
        s = _calc(800, 1000, "RAL", False, qty=3)
        assert s["billable_area_m2_per_item"] == 1.3
        assert s["unit_price_final"] == 926.25
        assert s["sale_price_total"] == round(926.25 * 3, 2)
        assert s["purchase_total_cost"] == round(1.3 * 285 * 3, 2)


class TestGolden1200x1500:
    @pytest.mark.parametrize("color,orientable,expected", [
        ("RAL", False, 1282.50), ("WOOD_EFFECT", False, 1345.50), ("SPECIAL_RAFFAELLO", False, 1575.00),
        ("RAL", True, 1728.00), ("WOOD_EFFECT", True, 1791.00), ("SPECIAL_RAFFAELLO", True, 2020.50),
    ])
    def test_1200x1500(self, color, orientable, expected):
        s = _calc(1200, 1500, color, orientable)
        assert s["real_area_m2"] == 1.8 and s["billable_area_m2"] == 1.8
        assert s["unit_price_final"] == expected

    def test_snapshot_contract(self):
        s = _calc(1200, 1500, "RAL", True)
        for k in ("real_area_m2", "billable_area_m2", "color_price_category", "purchase_rate_per_m2", "orientable",
                  "orientable_surcharge_per_m2", "effective_purchase_rate", "purchase_total_cost", "commercial_multiplier",
                  "unit_price_final", "sale_price_total"):
            assert k in s
        assert s["purchase_rate_per_m2"] == 285 and s["effective_purchase_rate"] == 384 and s["commercial_multiplier"] == 2.5
        assert s["purchase_total_cost"] == 691.2


class TestFailClosed:
    def test_missing_color(self):
        with pytest.raises(ValueError, match="MISSING_COLOR_PRICE_CATEGORY"):
            SimplePricingEngine.compute_area_purchase_multiplier(PRODUCT, SimplePricingInputs(width_mm=1200, height_mm=1500, options={"orientable": False}))

    def test_missing_orientable(self):
        with pytest.raises(ValueError, match="MISSING_ORIENTABLE_STATE"):
            SimplePricingEngine.compute_area_purchase_multiplier(PRODUCT, SimplePricingInputs(width_mm=1200, height_mm=1500, options={"color_code": "RAL"}))

    def test_missing_dimensions(self):
        with pytest.raises(ValueError, match="INVALID_DIMENSIONS"):
            _calc(0, 1500, "RAL", False)

    def test_missing_rate_table_or_multiplier(self):
        p = {**PRODUCT, "pricing_config": {**PRODUCT["pricing_config"], "purchase_cost_table_per_m2": {}}}
        with pytest.raises(ValueError, match="MISSING_PURCHASE_RATE_TABLE"):
            _calc(1200, 1500, "RAL", False, product=p)
        p = {**PRODUCT, "pricing_config": {**PRODUCT["pricing_config"], "commercial_multiplier": None}}
        with pytest.raises(ValueError, match="MISSING_COMMERCIAL_MULTIPLIER"):
            _calc(1200, 1500, "RAL", False, product=p)

    def test_never_zero(self):
        for color in ("RAL", "WOOD_EFFECT", "SPECIAL_RAFFAELLO"):
            for o in (False, True):
                assert _calc(300, 300, color, o)["unit_price_final"] > 0


# ---------------------------------------------------------------------------
# E2E API — quote line + posa + smontaggio + margin engine buckets
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"]}, timeout=20)
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


@pytest.fixture(scope="module")
def persiana(admin):
    items = admin.get(f"{BASE_URL}/api/multi-cat/products?category_code=PERSIANE_SCURI", timeout=20).json()["items"]
    prods = [p for p in items if p["key"] == "PERSIANA_STD"]
    assert prods, "PERSIANA_STD non seedata"
    return prods[0]


def _new_quote(admin, **extra):
    cust = admin.get(f"{BASE_URL}/api/customers?limit=1", timeout=20).json()
    cid = (cust.get("items") or cust)[0]["id"]
    r = admin.post(f"{BASE_URL}/api/quotes", json={"title": "TEST PERSIANE", "customer_id": cid}, timeout=20)
    assert r.status_code in (200, 201), r.text
    qid = r.json()["id"]
    if extra:
        r = admin.patch(f"{BASE_URL}/api/quotes/{qid}", json=extra, timeout=20)
        assert r.status_code == 200, r.text
    return qid


def _line_payload(persiana, w, h, color, orientable, qty, unit, total):
    cfg = {"width_mm": w, "height_mm": h, "quantity": qty, "color_code": color, "orientable": orientable, "__product_category": "PERSIANE_SCURI"}
    return {
        "category": "persiane_scuri", "product_key": "PERSIANA_STD", "product_config": cfg,
        "width_mm": w, "height_mm": h, "quantity": qty, "base_price": unit, "unit_price_final": unit,
        "subtotal_line": total, "description": "Persiana test", "source": "MULTI_CATEGORY_V1",
        "category_code": "PERSIANE_SCURI", "product_id": persiana["id"], "product_code": "PERSIANA_STD",
        "pricing_model": "AREA_PURCHASE_MULTIPLIER", "configuration_snapshot": cfg,
    }


class TestApiE2E:
    def test_configure_api_golden(self, admin, persiana):
        d = admin.post(f"{BASE_URL}/api/multi-cat/products/{persiana['id']}/configure", json={"simple_inputs": {
            "width_mm": 1200, "height_mm": 1500, "quantity": 1, "options": {"color_code": "RAL", "orientable": False}}}, timeout=20).json()
        assert d["pricing_status"] == "ok", d.get("blocking_errors")
        assert d["simple_snapshot"]["unit_price_final"] == 1282.50

    def test_supply_only_no_install(self, admin, persiana):
        qid = _new_quote(admin, installation_mode="SUPPLY_ONLY")
        r = admin.post(f"{BASE_URL}/api/quotes/{qid}/lines", json=_line_payload(persiana, 1200, 1500, "RAL", False, 1, 1282.5, 1282.5), timeout=20)
        assert r.status_code == 200, r.text
        line = r.json()
        assert line["unit_price_final"] == 1282.5 and line["subtotal_line"] == 1282.5
        assert abs(line["internal_cost"] - 513.0) < 0.01
        assert (line.get("automatic_services") or []) == []
        q = admin.get(f"{BASE_URL}/api/quotes/{qid}", timeout=20).json()
        fs = q["financial_snapshot"]
        assert fs["supply_cost"] == 513.0 and fs["installation_cost"] == 0 and fs["other_direct_costs"] == 0
        assert fs["net_revenue_ex_vat"] == 1282.5

    def test_supply_and_installation_with_dismantling_qty2(self, admin, persiana):
        qid = _new_quote(admin, installation_mode="SUPPLY_AND_INSTALLATION", dismantling_mode="INCLUDED")
        r = admin.post(f"{BASE_URL}/api/quotes/{qid}/lines", json=_line_payload(persiana, 1200, 1500, "RAL", True, 2, 1728.0, 3456.0), timeout=20)
        assert r.status_code == 200, r.text
        line = r.json()
        svcs = {s["service_code"]: s for s in line["automatic_services"]}
        assert "INSTALL_SHUTTER_1_2_SASH" in svcs and "REMOVE_SHUTTER" in svcs
        posa, rem = svcs["INSTALL_SHUTTER_1_2_SASH"], svcs["REMOVE_SHUTTER"]
        assert posa["quantity"] == 2 and posa["unit_sale_price"] == 150 and posa["sale_price_total"] == 300 and posa["internal_cost_total"] == 260
        assert rem["quantity"] == 2 and rem["unit_sale_price"] == 30 and rem["sale_price_total"] == 60 and rem["internal_cost_total"] == 40
        q = admin.get(f"{BASE_URL}/api/quotes/{qid}", timeout=20).json()
        fs = q["financial_snapshot"]
        assert abs(fs["supply_cost"] - 1382.4) < 0.01          # 691.20 × 2
        assert fs["installation_cost"] == 260.0                 # posa interno 130 × 2
        assert fs["other_direct_costs"] == 40.0                 # smontaggio interno 20 × 2
        assert abs(q["subtotal"] - (3456.0 + 300 + 60)) < 0.01  # prodotto + posa + smontaggio 30 €/pz (msg 402)

    def test_line_below_minimum_via_api(self, admin, persiana):
        qid = _new_quote(admin, installation_mode="SUPPLY_ONLY")
        r = admin.post(f"{BASE_URL}/api/quotes/{qid}/lines", json=_line_payload(persiana, 800, 1000, "WOOD_EFFECT", False, 1, 971.75, 971.75), timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["simple_snapshot"]["billable_area_m2"] == 1.3
        assert abs(r.json()["internal_cost"] - round(1.3 * 299, 2)) < 0.01
