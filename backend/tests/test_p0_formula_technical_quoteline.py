"""Regression test for BUG P0 — Multi-Category FORMULA_TECHNICAL quote line at 0 €.

Root cause: frontend read wrong commercial_snapshot fields
(`customer_price`/`customer_price_total`/`sale_price` do not exist).
The authoritative field is ``commercial_snapshot.final_unit_price`` (and its
alias ``unit_sale_price``).

Backend fail-closed guard: POST /api/quotes/{qid}/lines rejects lines with
``source=MULTI_CATEGORY_V1`` + ``pricing_model=FORMULA_TECHNICAL`` + ``base_price<=0``.
"""
from __future__ import annotations

import os

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001"
ADMIN_EMAIL = "admin@infissiexpress.com"
ADMIN_PASSWORD = "Admin!2025"


def _login() -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _get_first_quote_id(headers) -> str:
    r = requests.get(f"{BASE_URL}/api/quotes?limit=1", headers=headers, timeout=20).json()
    items = r.get("items") or []
    if not items:
        pytest.skip("Nessun preventivo di test disponibile nel tenant.")
    return items[0]["id"]


def _get_proevolution_id(headers) -> str:
    r = requests.get(
        f"{BASE_URL}/api/multi-cat/products?category_code=FINESTRE",
        headers=headers,
        timeout=20,
    ).json()
    cands = [p for p in r.get("items", []) if p.get("key") == "PROEVOLUTION"]
    if not cands:
        pytest.skip("Prodotto PROEVOLUTION non classificato — seed richiesto.")
    return cands[0]["id"]


@pytest.fixture(scope="module")
def headers():
    return {"Authorization": f"Bearer {_login()}"}


class TestFormulaTechnicalContract:
    """Verifica il contract /api/pricing/compute e /api/multi-cat/*/configure."""

    def test_pricing_v3_returns_final_unit_price(self, headers):
        payload = {
            "product_key": "PROEVOLUTION",
            "window_type": "WINDOW",
            "number_of_sashes": 1,
            "width_mm": 1200,
            "height_mm": 1400,
            "color_internal": "WHITE_MASS",
            "color_external": "WHITE_MASS",
            "glass_type": "DOUBLE_STANDARD",
            "quantity": 1,
        }
        r = requests.post(
            f"{BASE_URL}/api/pricing/compute",
            headers=headers,
            json=payload,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["pricing_status"] == "ok"
        cs = d.get("commercial_snapshot") or {}
        # Contract: final_unit_price è l'AUTHORITATIVE field.
        assert "final_unit_price" in cs, f"MISSING final_unit_price. Got keys: {list(cs.keys())}"
        assert cs["final_unit_price"] > 0
        # Legacy alias
        assert cs.get("unit_sale_price") == cs["final_unit_price"]
        ts = d.get("technical_snapshot") or {}
        assert ts.get("total_internal_cost", 0) > 0

    def test_multi_cat_configure_same_hash_as_pricing_v3(self, headers):
        """§3 identità motore: stesso calculation_hash tra i due endpoint."""
        pid = _get_proevolution_id(headers)
        payload_v3 = {
            "product_key": "PROEVOLUTION",
            "window_type": "WINDOW",
            "number_of_sashes": 1,
            "width_mm": 1200,
            "height_mm": 1400,
            "color_internal": "WHITE_MASS",
            "color_external": "WHITE_MASS",
            "glass_type": "DOUBLE_STANDARD",
            "quantity": 1,
        }
        r1 = requests.post(f"{BASE_URL}/api/pricing/compute", headers=headers, json=payload_v3, timeout=30).json()
        r2 = requests.post(
            f"{BASE_URL}/api/multi-cat/products/{pid}/configure",
            headers=headers,
            json={"technical_inputs": payload_v3},
            timeout=30,
        ).json()
        assert r1["calculation_hash"] == r2["calculation_hash"], "Motore duplicato — hash divergente!"

    def test_add_line_with_correct_price_persists_total(self, headers):
        """Configure -> add-line -> subtotal_line != 0 e quote total aggiornato."""
        qid = _get_first_quote_id(headers)
        pid = _get_proevolution_id(headers)
        cfg = requests.post(
            f"{BASE_URL}/api/multi-cat/products/{pid}/configure",
            headers=headers,
            json={
                "technical_inputs": {
                    "product_key": "PROEVOLUTION",
                    "window_type": "WINDOW",
                    "number_of_sashes": 1,
                    "width_mm": 1200,
                    "height_mm": 1400,
                    "color_internal": "WHITE_MASS",
                    "color_external": "WHITE_MASS",
                    "glass_type": "DOUBLE_STANDARD",
                    "quantity": 1,
                }
            },
            timeout=30,
        ).json()
        unit = cfg["commercial_snapshot"]["final_unit_price"]
        assert unit > 0

        add_body = {
            "category": "finestre",
            "product_key": "PROEVOLUTION",
            "product_id": pid,
            "description": "TEST regression P0 ProEvolution 1200x1400",
            "width_mm": 1200,
            "height_mm": 1400,
            "quantity": 1,
            "base_price": unit,
            "unit_price_final": unit,
            "subtotal_line": unit,
            "source": "MULTI_CATEGORY_V1",
            "category_code": "FINESTRE",
            "product_code": "PROEVOLUTION",
            "pricing_model": "FORMULA_TECHNICAL",
            "vat_rate": 0.22,
        }
        r = requests.post(f"{BASE_URL}/api/quotes/{qid}/lines", headers=headers, json=add_body, timeout=20)
        assert r.status_code == 200, r.text
        line = r.json()
        try:
            assert line["subtotal_line"] == unit
            assert line["unit_price_final"] == unit
            # Assert quote total contains this line
            q = requests.get(f"{BASE_URL}/api/quotes/{qid}", headers=headers, timeout=20).json()
            assert q["subtotal"] >= unit
            assert q["total"] > 0
        finally:
            # Cleanup
            requests.delete(f"{BASE_URL}/api/quotes/{qid}/lines/{line['id']}", headers=headers, timeout=10)

    def test_add_line_zero_price_is_rejected(self, headers):
        """Fail-closed §6/§8: FORMULA_TECHNICAL con base_price=0 → 400 COMMERCIAL_PRICING_NOT_CONFIGURED."""
        qid = _get_first_quote_id(headers)
        pid = _get_proevolution_id(headers)
        body = {
            "category": "finestre",
            "product_key": "PROEVOLUTION",
            "product_id": pid,
            "description": "TEST P0 must be rejected",
            "quantity": 1,
            "base_price": 0,
            "unit_price_final": 0,
            "source": "MULTI_CATEGORY_V1",
            "pricing_model": "FORMULA_TECHNICAL",
            "vat_rate": 0.22,
        }
        r = requests.post(f"{BASE_URL}/api/quotes/{qid}/lines", headers=headers, json=body, timeout=20)
        assert r.status_code == 400
        detail = r.json().get("detail", {})
        assert isinstance(detail, dict)
        assert detail.get("code") == "COMMERCIAL_PRICING_NOT_CONFIGURED"

    def test_simple_pricing_area_regression(self, headers):
        """§16 regression: AREA con min_billable non deve regredire."""
        r = requests.get(
            f"{BASE_URL}/api/multi-cat/products?category_code=ZANZARIERE&include_test_fixtures=true",
            headers=headers,
            timeout=20,
        ).json()
        cands = [p for p in r.get("items", []) if p.get("key") == "TEST_AREA_100_MIN_150"]
        if not cands:
            pytest.skip("Fixture TEST_AREA_100_MIN_150 non seedata.")
        pid = cands[0]["id"]
        res = requests.post(
            f"{BASE_URL}/api/multi-cat/products/{pid}/configure",
            headers=headers,
            json={"simple_inputs": {"width_mm": 1000, "height_mm": 800, "quantity": 1}},
            timeout=20,
        ).json()
        assert res["pricing_status"] == "ok"
        assert res["simple_snapshot"]["sale_price_total"] == 150.0
