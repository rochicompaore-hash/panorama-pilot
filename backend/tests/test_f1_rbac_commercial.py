"""RBAC tests — Commercial user MUST NOT receive internal/purchase/multiplier fields.

Prerequisito: utente ``commercial_test@infissiexpress.com`` / ``CommTest!2026`` con
ruolo "Commerciale" (nessun permesso `*`, `products.manage`, `quotes.view_costs`,
`quotes.view_margins`).
"""
from __future__ import annotations
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001"
COMM_EMAIL = "commercial_test@infissiexpress.com"
COMM_PW = "CommTest!2026"

LEAK_SIMPLE = [
    "internal_production_cost_per_item", "purchase_unit_cost_per_m2",
    "purchase_cost_per_item", "purchase_total_cost", "commercial_multiplier",
    "margin", "contribution_margin", "internal_reference_price",
]
LEAK_TECHNICAL = [
    "total_internal_cost", "material_cost", "glass_cost", "hardware_cost",
    "labor_cost", "foil_surcharge", "additional_technical_costs",
    "hourly_workshop_cost", "production_time_hours",
    "production_cost", "internal_cost",
]


@pytest.fixture(scope="module")
def comm_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": COMM_EMAIL, "password": COMM_PW}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"Commercial test user non disponibile: {r.text}")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _pid(headers, category_code, key):
    r = requests.get(f"{BASE_URL}/api/multi-cat/products?category_code={category_code}", headers=headers, timeout=20).json()
    return [p["id"] for p in r["items"] if p["key"] == key][0]


class TestRBACCommercial:
    def test_no_admin_permissions(self, comm_headers):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=comm_headers, timeout=20).json()
        perms = r.get("permissions", [])
        for banned in ("*", "products.manage", "quotes.view_costs", "quotes.view_margins"):
            assert banned not in perms

    def test_list_products_no_admin_view(self, comm_headers):
        r = requests.get(f"{BASE_URL}/api/multi-cat/products?category_code=CASSONETTI", headers=comm_headers, timeout=20).json()
        assert r.get("is_admin_view") is False

    def test_list_cassonetto_grid_redacted(self, comm_headers):
        r = requests.get(f"{BASE_URL}/api/multi-cat/products?category_code=CASSONETTI", headers=comm_headers, timeout=20).json()
        prod = [p for p in r["items"] if p["key"] == "CASSONETTO_STD"][0]
        cell = prod["pricing_config"]["grid"]["BIANCO_MASSA"]["163_c"]["500x250"]
        assert "internal" not in cell
        assert "sale" in cell
        # pricing_formula_metadata + purchase_cost_table non devono comparire
        for banned_key in ("pricing_formula_metadata", "purchase_cost_table_per_m2"):
            assert banned_key not in prod["pricing_config"]

    def test_cassonetto_configure_no_leak(self, comm_headers):
        pid = _pid(comm_headers, "CASSONETTI", "CASSONETTO_STD")
        r = requests.post(f"{BASE_URL}/api/multi-cat/products/{pid}/configure", headers=comm_headers,
                          json={"simple_inputs": {"width_mm": 500, "height_mm": 250, "quantity": 1, "options": {"color_code": "003", "depth_mm": 163, "ceiling_liner": "SI"}}},
                          timeout=20).json()
        s = r["simple_snapshot"]
        for f in LEAK_SIMPLE:
            assert f not in s, f"LEAK: {f} in simple_snapshot"
        assert s["customer_sale_price_per_item"] == 329.01

    def test_zanzariera_configure_no_leak(self, comm_headers):
        pid = _pid(comm_headers, "ZANZARIERE", "UNIKVER")
        r = requests.post(f"{BASE_URL}/api/multi-cat/products/{pid}/configure", headers=comm_headers,
                          json={"simple_inputs": {"width_mm": 800, "height_mm": 800, "quantity": 1, "options": {"color_code": "ZC_BASE_DEFAULT"}}},
                          timeout=20).json()
        s = r["simple_snapshot"]
        for f in LEAK_SIMPLE:
            assert f not in s, f"LEAK: {f} in simple_snapshot"
        assert s["sale_price_total"] == 97.02

    def test_tapparella_x3_no_leak(self, comm_headers):
        pid = _pid(comm_headers, "TAPPARELLE", "TAPPARELLA_STANDARD")
        r = requests.post(f"{BASE_URL}/api/multi-cat/products/{pid}/configure", headers=comm_headers,
                          json={"simple_inputs": {"width_mm": 800, "height_mm": 1000, "quantity": 1, "options": {"color_code": "RAL_STANDARD"}}},
                          timeout=20).json()
        s = r["simple_snapshot"]
        for f in LEAK_SIMPLE:
            assert f not in s, f"LEAK: {f}"
        # Nuova policy ×3: RAL 35 -> 105 €/m² -> 1.50 × 105 = 157.50
        assert s["sale_price_total"] == 157.50

    def test_proevolution_technical_redacted(self, comm_headers):
        pid = _pid(comm_headers, "FINESTRE", "PROEVOLUTION")
        r = requests.post(f"{BASE_URL}/api/multi-cat/products/{pid}/configure", headers=comm_headers,
                          json={"technical_inputs": {"product_key": "PROEVOLUTION", "window_type": "WINDOW", "number_of_sashes": 1, "width_mm": 1200, "height_mm": 1400, "color_internal": "WHITE_MASS", "color_external": "WHITE_MASS", "glass_type": "DOUBLE_STANDARD", "quantity": 1}},
                          timeout=20).json()
        ts = r.get("technical_snapshot") or {}
        for f in LEAK_TECHNICAL:
            assert f not in ts, f"LEAK technical: {f}"
        # Commerciale visibile
        assert r["commercial_snapshot"]["final_unit_price"] == 1016.70
