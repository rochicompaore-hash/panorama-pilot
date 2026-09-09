"""
PRICING INTEGRITY AUDIT — msg401
Cassonetti GRID (fail-closed) + Persiane AREA_PURCHASE_MULTIPLIER
+ RBAC redaction (commercial) + FINESTRE PROEVOLUTION regression
"""
import os
import pytest
import requests
from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = (ADMIN_EMAIL, ADMIN_PASSWORD)
COMM = ("commercial_test@infissiexpress.com", "CommTest!2026")


def _login(email, pw):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def commercial_token():
    return _login(*COMM)


def _headers(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _get_product_id(tok, category_code, product_code):
    r = requests.get(
        f"{BASE}/multi-cat/products?category_code={category_code}",
        headers=_headers(tok),
        timeout=15,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    products = data if isinstance(data, list) else data.get("products") or data.get("items") or []
    for p in products:
        if p.get("key") == product_code or p.get("product_code") == product_code or p.get("code") == product_code or p.get("product_key") == product_code:
            return p.get("id") or p.get("_id") or p.get("product_id"), p
    pytest.fail(f"Product {product_code} not found in {category_code}: {products}")


# ---------------- CASSONETTI GRID ----------------

class TestCassonettoGrid:
    @pytest.fixture(scope="class")
    def prod(self, admin_token):
        pid, p = _get_product_id(admin_token, "CASSONETTI", "CASSONETTO_STD")
        return pid

    def _configure(self, tok, pid, w, h, d, ceiling, color):
        payload = {
            "simple_inputs": {
                "width_mm": w,
                "height_mm": h,
                "quantity": 1,
                "options": {
                    "depth_mm": d,
                    "ceiling_liner": ceiling,
                    "color_code": color,
                },
            }
        }
        return requests.post(
            f"{BASE}/multi-cat/products/{pid}/configure",
            json=payload,
            headers=_headers(tok),
            timeout=20,
        )

    def test_A_golden_500x250_163_SI_003(self, admin_token, prod):
        r = self._configure(admin_token, prod, 500, 250, 163, "SI", "003")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("pricing_status") == "ok", j
        snap = j.get("simple_snapshot") or j.get("commercial_snapshot") or {}
        price = snap.get("unit_price_final") or snap.get("final_unit_price")
        assert price is not None
        assert abs(float(price) - 329.01) < 0.05, f"Expected 329.01, got {price}"

    def test_golden_700x250_326_SI_003(self, admin_token, prod):
        r = self._configure(admin_token, prod, 700, 250, 326, "SI", "003")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["pricing_status"] == "ok"
        snap = j.get("simple_snapshot") or {}
        assert abs(float(snap["unit_price_final"]) - 276.13) < 0.05
        # admin-visible internal cost per item
        internal = snap.get("internal_production_cost_per_item") or snap.get("internal_production_cost")
        assert internal is not None, snap
        assert abs(float(internal) - 110.45) < 0.05, f"internal cost {internal}"

    def test_failclosed_dimension_to_confirm(self, admin_token, prod):
        # 550 width is between grid nodes → DIMENSION_TO_CONFIRM
        r = self._configure(admin_token, prod, 550, 250, 163, "SI", "003")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("pricing_status") in ("invalid_inputs", "invalid"), j
        errs = j.get("blocking_errors") or []
        assert errs and str(errs[0]).startswith("DIMENSION_TO_CONFIRM"), errs

    def test_failclosed_missing_color(self, admin_token, prod):
        r = self._configure(admin_token, prod, 500, 250, 163, "SI", "999")
        assert r.status_code == 200
        j = r.json()
        assert j.get("pricing_status") in ("invalid_inputs", "invalid")
        errs = j.get("blocking_errors") or []
        assert any(("CASSONETTO_COLOR_FAMILY_UNMAPPED" in str(e)) or ("MISSING_CASSONETTO_COLOR_PRICE_FAMILY" in str(e)) for e in errs), errs


# ---------------- PERSIANE AREA_PURCHASE_MULTIPLIER ----------------

class TestPersiane:
    @pytest.fixture(scope="class")
    def prod(self, admin_token):
        pid, _ = _get_product_id(admin_token, "PERSIANE_SCURI", "PERSIANA_STD")
        return pid

    def _configure(self, tok, pid, w, h, color, orientable, qty=1):
        payload = {
            "simple_inputs": {
                "width_mm": w,
                "height_mm": h,
                "quantity": qty,
                "options": {"color_code": color, "orientable": orientable},
            }
        }
        return requests.post(
            f"{BASE}/multi-cat/products/{pid}/configure",
            json=payload,
            headers=_headers(tok),
            timeout=20,
        )

    def test_F_ral_1200x1500_fisse(self, admin_token, prod):
        r = self._configure(admin_token, prod, 1200, 1500, "RAL", False)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["pricing_status"] == "ok"
        snap = j.get("simple_snapshot") or {}
        assert abs(float(snap["unit_price_final"]) - 1282.50) < 0.05, snap

    def test_G_ral_orientable(self, admin_token, prod):
        r = self._configure(admin_token, prod, 1200, 1500, "RAL", True)
        j = r.json()
        assert j["pricing_status"] == "ok"
        snap = j.get("simple_snapshot") or {}
        assert abs(float(snap["unit_price_final"]) - 1728.00) < 0.5, snap

    def test_H_minimum_area_per_piece(self, admin_token, prod):
        # 800x1000 = 0.8 m² < 1.3 → billed 1.3 m² per pz
        r = self._configure(admin_token, prod, 800, 1000, "RAL", False)
        j = r.json()
        assert j["pricing_status"] == "ok"
        snap = j.get("simple_snapshot") or {}
        assert abs(float(snap["unit_price_final"]) - 926.25) < 0.5, snap


# ---------------- RBAC — commercial redaction ----------------

class TestRBACCommercial:
    def test_configure_commercial_no_internal_leaks(self, commercial_token, admin_token):
        pid, _ = _get_product_id(admin_token, "PERSIANE_SCURI", "PERSIANA_STD")
        payload = {
            "simple_inputs": {
                "width_mm": 1200,
                "height_mm": 1500,
                "quantity": 1,
                "options": {"color_code": "RAL", "orientable": True},
            }
        }
        r = requests.post(
            f"{BASE}/multi-cat/products/{pid}/configure",
            json=payload,
            headers=_headers(commercial_token),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["pricing_status"] == "ok"
        snap = j.get("simple_snapshot") or {}
        assert abs(float(snap["unit_price_final"]) - 1728.00) < 0.5, snap
        forbidden = [
            "purchase_rate_per_m2",
            "effective_purchase_rate",
            "orientable_surcharge_per_m2",
            "purchase_cost_per_item",
            "purchase_total_cost",
            "commercial_multiplier",
        ]
        found = [k for k in forbidden if k in snap]
        assert not found, f"Commercial snap leaks: {found} -- snap={snap}"

    def test_product_detail_commercial_no_internal_pricing_config(self, commercial_token, admin_token):
        pid, _ = _get_product_id(admin_token, "PERSIANE_SCURI", "PERSIANA_STD")
        r = requests.get(
            f"{BASE}/multi-cat/products/{pid}",
            headers=_headers(commercial_token),
            timeout=15,
        )
        assert r.status_code == 200
        j = r.json()
        pc = j.get("pricing_config") or {}
        for k in ("purchase_cost_table_per_m2", "commercial_multiplier", "orientable_surcharge_per_m2"):
            assert k not in pc, f"Leak {k} in pricing_config: {pc}"

    def test_cassonetto_grid_commercial_no_internal(self, commercial_token, admin_token):
        pid, _ = _get_product_id(admin_token, "CASSONETTI", "CASSONETTO_STD")
        r = requests.get(
            f"{BASE}/multi-cat/products/{pid}",
            headers=_headers(commercial_token),
            timeout=15,
        )
        assert r.status_code == 200
        j = r.json()
        # Descend into grid table; verify cells have only 'sale'
        import json as _json
        blob = _json.dumps(j)
        assert '"internal"' not in blob, "Grid contains 'internal' key for commercial"


# ---------------- Quote line with automatic services (persiane + posa + smontaggio) ----------------

class TestPersianaQuoteAutomaticServices:
    def _make_quote(self, tok):
        c = requests.get(f"{BASE}/customers?limit=1", headers=_headers(tok), timeout=15)
        assert c.status_code == 200, c.text
        cd = c.json()
        customers = cd if isinstance(cd, list) else cd.get("items") or cd.get("customers") or []
        assert customers, cd
        cid = customers[0].get("id") or customers[0].get("_id")
        q = requests.post(
            f"{BASE}/quotes",
            json={"title": "TEST_msg401_persiana", "customer_id": cid},
            headers=_headers(tok),
            timeout=15,
        )
        assert q.status_code in (200, 201), q.text
        return q.json()["id"]

    def _add_line(self, tok, qid, install_mode, dismantle_mode):
        r = requests.patch(
            f"{BASE}/quotes/{qid}",
            json={"installation_mode": install_mode, "dismantling_mode": dismantle_mode},
            headers=_headers(tok),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        pid, _ = _get_product_id(tok, "PERSIANE_SCURI", "PERSIANA_STD")
        payload = {
            "category": "persiane_scuri",
            "product_key": "PERSIANA_STD",
            "product_config": {
                "width_mm": 1200,
                "height_mm": 1500,
                "quantity": 2,
                "color_code": "RAL",
                "orientable": True,
            },
            "width_mm": 1200,
            "height_mm": 1500,
            "quantity": 2,
            "base_price": 1728,
            "unit_price_final": 1728,
            "subtotal_line": 3456,
            "description": "Persiana",
            "source": "MULTI_CATEGORY_V1",
            "category_code": "PERSIANE_SCURI",
            "product_id": pid,
            "product_code": "PERSIANA_STD",
            "pricing_model": "AREA_PURCHASE_MULTIPLIER",
            "configuration_snapshot": {
                "width_mm": 1200,
                "height_mm": 1500,
                "quantity": 2,
                "color_code": "RAL",
                "orientable": True,
            },
        }
        return requests.post(
            f"{BASE}/quotes/{qid}/lines",
            json=payload,
            headers=_headers(tok),
            timeout=20,
        )

    def test_I_supply_and_installation_included_dismantle(self, admin_token):
        qid = self._make_quote(admin_token)
        r = self._add_line(admin_token, qid, "SUPPLY_AND_INSTALLATION", "INCLUDED")
        assert r.status_code in (200, 201), r.text
        line = r.json()
        aut = line.get("automatic_services") or []
        # find posa + smontaggio
        codes = {s.get("service_code") or s.get("code"): s for s in aut}
        assert "INSTALL_SHUTTER_1_2_SASH" in codes, aut
        assert "REMOVE_SHUTTER" in codes, aut
        posa = codes["INSTALL_SHUTTER_1_2_SASH"]
        smont = codes["REMOVE_SHUTTER"]
        assert int(posa.get("quantity") or posa.get("qty")) == 2
        assert abs(float(posa.get("unit_sale_price") or posa.get("unit_price") or 0) - 150) < 0.01
        assert abs(float(posa.get("sale_price_total") or posa.get("total") or 0) - 300) < 0.01
        assert int(smont.get("quantity") or smont.get("qty")) == 2
        assert abs(float(smont.get("unit_sale_price") or smont.get("unit_price") or 0) - 30) < 0.01
        assert abs(float(smont.get("sale_price_total") or smont.get("total") or 0) - 60) < 0.01

        internal = line.get("internal_cost")
        assert internal is not None and abs(float(internal) - 691.20) < 1.0, internal

        q = requests.get(f"{BASE}/quotes/{qid}", headers=_headers(admin_token), timeout=15).json()
        fs = q.get("financial_snapshot") or {}
        assert abs(float(fs.get("supply_cost") or 0) - 1382.40) < 1.0, fs
        assert abs(float(fs.get("installation_cost") or 0) - 260) < 1.0, fs
        assert abs(float(fs.get("other_direct_costs") or 0) - 40) < 1.0, fs
        subtotal = q.get("subtotal") or q.get("subtotal_amount") or (q.get("totals") or {}).get("subtotal")
        assert abs(float(subtotal) - 3816) < 1.0, subtotal

    def test_supply_only_no_automatic_services(self, admin_token):
        qid = self._make_quote(admin_token)
        r = self._add_line(admin_token, qid, "SUPPLY_ONLY", "INCLUDED")
        assert r.status_code in (200, 201), r.text
        line = r.json()
        aut = line.get("automatic_services") or []
        assert len(aut) == 0, aut
        q = requests.get(f"{BASE}/quotes/{qid}", headers=_headers(admin_token), timeout=15).json()
        fs = q.get("financial_snapshot") or {}
        assert abs(float(fs.get("installation_cost") or 0) - 0) < 0.01


# ---------------- FINESTRE PROEVOLUTION regression ----------------

class TestFinestreProevolution:
    def test_configure_no_500(self, admin_token):
        pid, _ = _get_product_id(admin_token, "FINESTRE", "PROEVOLUTION")
        payload = {
            "technical_inputs": {
                "product_key": "PROEVOLUTION",
                "window_type": "WINDOW",
                "number_of_sashes": 1,
                "width_mm": 1200,
                "height_mm": 1400,
                "color_internal": "WHITE_MASS",
                "color_external": "WHITE_MASS",
                "glass_type": "TRIPLE_SATIN",
                "quantity": 1,
            }
        }
        r = requests.post(
            f"{BASE}/multi-cat/products/{pid}/configure",
            json=payload,
            headers=_headers(admin_token),
            timeout=25,
        )
        assert r.status_code == 200, f"Got {r.status_code}: {r.text[:400]}"
        j = r.json()
        assert j.get("pricing_status") == "ok", j
        snap = j.get("commercial_snapshot") or j.get("simple_snapshot") or {}
        price = snap.get("final_unit_price") or snap.get("unit_price_final") or 0
        assert float(price) > 0, snap

    def test_restauro_not_in_commercial_catalog(self, commercial_token):
        r = requests.get(
            f"{BASE}/multi-cat/products?category_code=FINESTRE",
            headers=_headers(commercial_token),
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        products = data if isinstance(data, list) else data.get("products") or data.get("items") or []
        codes = [p.get("product_code") or p.get("code") for p in products]
        assert "PROEVOLUTION_RESTAURO" not in codes, codes
