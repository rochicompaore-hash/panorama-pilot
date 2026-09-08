"""LOTTO 1 (msg 402) — MODIFICA riga con recompute backend autoritativo.

§37: finestra 1200×1500 qty1 → 1300×1600 qty2 → vetro/tecnico/sale/posa/smontaggio/totali/margine ricalcolati.
"""
from __future__ import annotations
import os
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"]}, timeout=20)
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


def _product(admin, cat, key):
    items = admin.get(f"{BASE_URL}/api/multi-cat/products?category_code={cat}", timeout=20).json()["items"]
    return [p for p in items if p["key"] == key][0]


def _quote(admin, **flags):
    cust = admin.get(f"{BASE_URL}/api/customers?limit=1", timeout=20).json()
    cid = (cust.get("items") or cust)[0]["id"]
    qid = admin.post(f"{BASE_URL}/api/quotes", json={"title": "TEST LOTTO1", "customer_id": cid}, timeout=20).json()["id"]
    r = admin.patch(f"{BASE_URL}/api/quotes/{qid}", json=flags, timeout=20)
    assert r.status_code == 200, r.text
    return qid


def _window_payload(pid, w, h, qty, glass):
    cfg = {"product_key": "PROEVOLUTION", "window_type": "WINDOW", "number_of_sashes": 1, "width_mm": w, "height_mm": h,
           "color_internal": "WHITE_MASS", "color_external": "WHITE_MASS", "glass_type": glass, "quantity": qty}
    return {"category": "finestre", "product_key": "PROEVOLUTION", "quantity": qty, "base_price": 1, "unit_price_final": 1,
            "subtotal_line": 1, "description": "Finestra", "source": "MULTI_CATEGORY_V1", "category_code": "FINESTRE",
            "product_id": pid, "product_code": "PROEVOLUTION", "pricing_model": "FORMULA_TECHNICAL",
            "width_mm": w, "height_mm": h, "configuration_snapshot": cfg}


class TestReconfigureWindow:
    def test_edit_size_qty_glass_recomputes_everything(self, admin):
        pid = _product(admin, "FINESTRE", "PROEVOLUTION")["id"]
        qid = _quote(admin, installation_mode="SUPPLY_AND_INSTALLATION", dismantling_mode="INCLUDED")
        r = admin.post(f"{BASE_URL}/api/quotes/{qid}/lines", json=_window_payload(pid, 1200, 1500, 1, "DOUBLE_STANDARD"), timeout=30)
        assert r.status_code == 200, r.text
        l1 = r.json()
        assert l1["unit_price_final"] > 1 and l1["internal_cost"] > 0   # client price ignored → authoritative
        svc1 = {s["service_code"]: s for s in l1["automatic_services"]}
        assert svc1["INSTALL_WINDOW_1_2_SASH"]["quantity"] == 1 and svc1["REMOVE_WINDOW"]["quantity"] == 1
        q1 = admin.get(f"{BASE_URL}/api/quotes/{qid}", timeout=20).json()

        r = admin.put(f"{BASE_URL}/api/quotes/{qid}/lines/{l1['id']}/reconfigure", json=_window_payload(pid, 1300, 1600, 2, "TRIPLE_SATIN"), timeout=30)
        assert r.status_code == 200, r.text
        l2 = r.json()
        assert l2["id"] == l1["id"] and l2["order_index"] == l1["order_index"]      # line identity preserved
        assert l2["width_mm"] == 1300 and l2["height_mm"] == 1600 and l2["quantity"] == 2
        assert l2["configuration_snapshot"]["glass_type"] == "TRIPLE_SATIN" and l2["pricing_snapshot"]["inputs_echo"]["technical_inputs"]["glass_type"] == "TRIPLE_SATIN"
        assert float(l2["technical_snapshot"]["glass_cost"]) > float(l1["technical_snapshot"]["glass_cost"])
        assert l2["unit_price_final"] > l1["unit_price_final"]                          # vetro + misure → prezzo ↑
        assert l2["internal_cost"] > l1["internal_cost"]
        svc_total2 = sum(s["sale_price_total"] for s in l2["automatic_services"])
        assert abs(l2["subtotal_line"] - (l2["unit_price_final"] * 2 + svc_total2)) < 0.02
        svc2 = {s["service_code"]: s for s in l2["automatic_services"]}
        assert svc2["INSTALL_WINDOW_1_2_SASH"]["quantity"] == 2 and svc2["INSTALL_WINDOW_1_2_SASH"]["sale_price_total"] == 300
        assert svc2["REMOVE_WINDOW"]["quantity"] == 2
        assert len(l2["previous_snapshots"]) == 1 and l2["previous_snapshots"][0]["width_mm"] == 1200

        q2 = admin.get(f"{BASE_URL}/api/quotes/{qid}", timeout=20).json()
        assert len(q2["lines"]) == 1                                                  # nessuna riga scollegata
        assert q2["subtotal"] > q1["subtotal"] and q2["total"] > q1["total"]
        fs1, fs2 = q1["financial_snapshot"], q2["financial_snapshot"]
        assert fs2["supply_cost"] > fs1["supply_cost"]
        assert fs2["installation_cost"] == 2 * fs1["installation_cost"]
        assert fs2["other_direct_costs"] == 2 * fs1["other_direct_costs"]
        assert fs2["tachometer_value"] is not None and fs2["tachometer_value"] == fs2["final_company_margin"]

    def test_reconfigure_fail_closed_on_invalid(self, admin):
        cass = _product(admin, "CASSONETTI", "CASSONETTO_STD")
        qid = _quote(admin, installation_mode="SUPPLY_ONLY")
        cfg = {"width_mm": 500, "height_mm": 250, "depth_mm": 163, "ceiling_liner": "SI", "color_code": "003", "quantity": 1}
        pay = {"category": "cassonetti", "product_key": "CASSONETTO_STD", "quantity": 1, "base_price": 329.01, "unit_price_final": 329.01,
               "subtotal_line": 329.01, "description": "Cass", "source": "MULTI_CATEGORY_V1", "category_code": "CASSONETTI",
               "product_id": cass["id"], "product_code": "CASSONETTO_STD", "pricing_model": "GRID", "width_mm": 500, "height_mm": 250,
               "configuration_snapshot": cfg}
        l = admin.post(f"{BASE_URL}/api/quotes/{qid}/lines", json=pay, timeout=20).json()
        assert l["unit_price_final"] == 329.01
        bad = {**pay, "width_mm": 550, "configuration_snapshot": {**cfg, "width_mm": 550}}
        r = admin.put(f"{BASE_URL}/api/quotes/{qid}/lines/{l['id']}/reconfigure", json=bad, timeout=20)
        assert r.status_code == 400 and r.json()["detail"]["code"] == "PRICING_NOT_OK"
        ok = {**pay, "quantity": 3, "width_mm": 700, "configuration_snapshot": {**cfg, "width_mm": 700, "depth_mm": 326, "quantity": 3}}
        l2 = admin.put(f"{BASE_URL}/api/quotes/{qid}/lines/{l['id']}/reconfigure", json=ok, timeout=20).json()
        assert l2["unit_price_final"] == 276.13 and l2["quantity"] == 3 and abs(l2["subtotal_line"] - 828.39) < 0.01
        assert abs(l2["internal_cost"] - 110.45) < 0.01

    def test_accepted_quote_is_frozen(self, admin):
        # any accepted quote in DB
        qs = admin.get(f"{BASE_URL}/api/quotes?limit=200", timeout=20).json()
        acc = [q for q in (qs.get("items") or qs) if q.get("quote_status") == "accepted" and (q.get("lines") or [])]
        if not acc:
            pytest.skip("nessun preventivo accepted con righe")
        q = admin.get(f"{BASE_URL}/api/quotes/{acc[0]['id']}", timeout=20).json()
        lid = q["lines"][0]["id"]
        r = admin.put(f"{BASE_URL}/api/quotes/{q['id']}/lines/{lid}/reconfigure", json={"category": "x", "quantity": 1, "base_price": 1}, timeout=20)
        assert r.status_code in (400, 409, 423)
