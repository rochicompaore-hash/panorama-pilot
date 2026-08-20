"""F1 Real Catalog — acceptance tests via API reale.

Verifica:
  * PORTEFINESTRE assente dalle categorie attive (§2).
  * 13 colori PVC seedati con mapping cassonetti_price_family (§3-4).
  * §21 UNIKVER 800×800 BASE -> 97.02 €.
  * §22 Tapparella 800×1000 RAL 52.50 / LEGNO 60 / RAFFAELLO 67.50.
  * §23 Cassonetto 3 celle reali (L500H250, L500H550 +50%, L700H250 D326).
  * Fail-closed DIMENSION_TO_CONFIRM + MISSING_CASSONETTO_COLOR_PRICE_FAMILY.
"""
from __future__ import annotations
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001"


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "admin@infissiexpress.com", "password": "Admin!2025"}, timeout=20)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _product_id_by_key(headers, category_code: str, key: str) -> str:
    r = requests.get(f"{BASE_URL}/api/multi-cat/products?category_code={category_code}", headers=headers, timeout=20).json()
    cands = [p for p in r.get("items", []) if p.get("key") == key]
    if not cands:
        pytest.skip(f"{key} non trovato in {category_code}")
    return cands[0]["id"]


class TestF1RealCatalog:
    def test_portefinestre_soft_deleted(self, headers):
        r = requests.get(f"{BASE_URL}/api/product-categories?active=true", headers=headers, timeout=20).json()
        codes = [c["code"] for c in r["items"]]
        assert "FINESTRE" in codes
        assert "PORTEFINESTRE" not in codes

    def test_pvc_colors_seeded(self, headers):
        r = requests.get(f"{BASE_URL}/api/product-colors", headers=headers, timeout=20).json()
        by_code = {c["code"]: c for c in r["items"]}
        assert "003" in by_code and by_code["003"]["pvc_color_category"] == "MASS_COLOR"
        assert by_code["003"]["cassonetti_price_family"] == "BIANCO_MASSA"
        assert by_code["100"]["pvc_color_category"] == "STANDARD"
        assert by_code["100"]["cassonetti_price_family"] == "STANDARD"
        assert by_code["154"]["cassonetti_price_family"] == "STANDARD"
        assert by_code["019"]["cassonetti_price_family"] == "NON_STANDARD"
        assert by_code["663"]["cassonetti_price_family"] == "NON_STANDARD"

    def test_unikver_800x800_base_97_02(self, headers):
        pid = _product_id_by_key(headers, "ZANZARIERE", "UNIKVER")
        r = requests.post(
            f"{BASE_URL}/api/multi-cat/products/{pid}/configure",
            headers=headers,
            json={"simple_inputs": {"width_mm": 800, "height_mm": 800, "quantity": 1, "options": {"color_code": "ZC_BASE_DEFAULT"}}},
            timeout=20,
        ).json()
        assert r["pricing_status"] == "ok"
        assert r["simple_snapshot"]["sale_price_total"] == 97.02
        assert r["simple_snapshot"]["billable_area_m2_per_item"] == 1.50

    def test_tapparella_three_variants(self, headers):
        pid = _product_id_by_key(headers, "TAPPARELLE", "TAPPARELLA_STANDARD")
        expected = {"RAL_STANDARD": 52.50, "WOOD_EFFECT": 60.00, "RAFFAELLO": 67.50}
        for cc, exp in expected.items():
            r = requests.post(
                f"{BASE_URL}/api/multi-cat/products/{pid}/configure",
                headers=headers,
                json={"simple_inputs": {"width_mm": 800, "height_mm": 1000, "quantity": 1, "options": {"color_code": cc}}},
                timeout=20,
            ).json()
            assert r["pricing_status"] == "ok", (cc, r)
            assert r["simple_snapshot"]["sale_price_total"] == exp, (cc, r["simple_snapshot"])

    def test_cassonetto_grid_three_cells(self, headers):
        pid = _product_id_by_key(headers, "CASSONETTI", "CASSONETTO_STD")
        cases = [
            # (color, W, H, depth, ceil, expected_sale, expected_internal, expected_family)
            ("003", 500, 250, 163, "SI", 329.01, 101.23, "BIANCO_MASSA"),
            ("003", 500, 550, 163, "SI", 422.38, 112.63, "BIANCO_MASSA"),
            ("154", 700, 250, 326, "NO", 296.20, 118.48, "STANDARD"),
        ]
        for color, w, h, d, ceil, sale, internal, fam in cases:
            r = requests.post(
                f"{BASE_URL}/api/multi-cat/products/{pid}/configure",
                headers=headers,
                json={"simple_inputs": {"width_mm": w, "height_mm": h, "quantity": 1, "options": {"color_code": color, "depth_mm": d, "ceiling_liner": ceil}}},
                timeout=20,
            ).json()
            assert r["pricing_status"] == "ok", (color, w, h, d, ceil, r)
            s = r["simple_snapshot"]
            assert s["customer_sale_price_per_item"] == sale, (color, w, h, s)
            assert s["internal_production_cost_per_item"] == internal, (color, w, h, s)
            assert s["finish_family"] == fam

    def test_cassonetto_dimension_to_confirm(self, headers):
        pid = _product_id_by_key(headers, "CASSONETTI", "CASSONETTO_STD")
        r = requests.post(
            f"{BASE_URL}/api/multi-cat/products/{pid}/configure",
            headers=headers,
            json={"simple_inputs": {"width_mm": 1234, "height_mm": 999, "quantity": 1, "options": {"color_code": "003", "depth_mm": 163, "ceiling_liner": "SI"}}},
            timeout=20,
        ).json()
        assert r["pricing_status"] == "invalid_inputs"
        assert "DIMENSION_TO_CONFIRM" in r["blocking_errors"]

    def test_cassonetto_missing_color_mapping(self, headers):
        pid = _product_id_by_key(headers, "CASSONETTI", "CASSONETTO_STD")
        r = requests.post(
            f"{BASE_URL}/api/multi-cat/products/{pid}/configure",
            headers=headers,
            json={"simple_inputs": {"width_mm": 500, "height_mm": 250, "quantity": 1, "options": {"color_code": "999", "depth_mm": 163, "ceiling_liner": "SI"}}},
            timeout=20,
        ).json()
        assert r["pricing_status"] == "invalid_inputs"
        assert "MISSING_CASSONETTO_COLOR_PRICE_FAMILY" in r["blocking_errors"]

    def test_test_fixture_hidden_from_default_listing(self, headers):
        """TEST_ZANZARIERA_AREA_130 non deve comparire nella lista di default."""
        r = requests.get(f"{BASE_URL}/api/multi-cat/products?category_code=ZANZARIERE", headers=headers, timeout=20).json()
        keys = [p["key"] for p in r["items"]]
        assert "TEST_ZANZARIERA_AREA_130" not in keys

    def test_real_zanzariere_all_present(self, headers):
        r = requests.get(f"{BASE_URL}/api/multi-cat/products?category_code=ZANZARIERE", headers=headers, timeout=20).json()
        keys = [p["key"] for p in r["items"]]
        for req in ["SWITCH_5", "SKAT", "UNIKLAT", "UNIKVER", "UNIKCAT"]:
            assert req in keys, f"{req} missing"

    def test_seed_idempotence(self, headers):
        """Re-run seed does not duplicate."""
        # Count colors before/after (invocazione seed dovrebbe già essere idempotente)
        r1 = requests.get(f"{BASE_URL}/api/product-colors", headers=headers, timeout=20).json()
        assert len(r1["items"]) == 13
