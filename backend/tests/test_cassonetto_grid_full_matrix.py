"""CASSONETTI — FULL MATRIX VALIDATION (PO msg 401 §1-§11).

Source of truth: ``backend/data/listino_completo_con_costi.xlsx``.
Verifica CELL-BY-CELL (4.464 sale + 4.464 cost) su tre livelli:
  workbook == app/data/cassonetti_grid_2026.json == DB product.pricing_config.grid == engine compute_grid
"""
from __future__ import annotations

import asyncio, json, os
from pathlib import Path

import pytest
import requests

from app.models_multi_category import SimplePricingInputs
from app.services.multi_category_pricing import SimplePricingEngine

BACKEND = Path(__file__).resolve().parents[1]
WORKBOOK = BACKEND / "data" / "listino_completo_con_costi.xlsx"
GRID_JSON = BACKEND / "app" / "data" / "cassonetti_grid_2026.json"
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

FAMILY_SHEETS = {
    "BIANCO_MASSA": ("Bianco massa", "Costo prod. Bianco"),
    "STANDARD": ("Pellicolato standard", "Costo prod. Std"),
    "NON_STANDARD": ("Pellicolato no-std", "Costo prod. No-std"),
}
COLS = ["163_c", "163_nc", "326_c", "326_nc", "489_c", "489_nc", "652_c", "652_nc"]
WIDTHS = list(range(500, 3501, 100))
HEIGHTS = [250, 350, 450, 550, 650, 750]


def _read_sheet(ws):
    out = {c: {} for c in COLS}
    for row in ws.iter_rows(min_row=5, values_only=True):
        if not isinstance(row[0], (int, float)) or not isinstance(row[1], (int, float)):
            continue
        for i, c in enumerate(COLS):
            if row[2 + i] is not None:
                out[c][f"{int(row[0])}x{int(row[1])}"] = round(float(row[2 + i]), 2)
    return out


@pytest.fixture(scope="module")
def workbook():
    import openpyxl
    if not WORKBOOK.exists():
        pytest.fail(f"Workbook autoritativo mancante: {WORKBOOK}")
    wb = openpyxl.load_workbook(WORKBOOK, data_only=True)
    return {fam: (_read_sheet(wb[s]), _read_sheet(wb[c])) for fam, (s, c) in FAMILY_SHEETS.items()}


@pytest.fixture(scope="module")
def grid_json():
    return json.loads(GRID_JSON.read_text())


@pytest.fixture(scope="module")
def db_products():
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _load():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        return await db.products.find({"key": "CASSONETTO_STD", "pricing_model": "GRID", "deleted_at": None}).to_list(50)
    return asyncio.run(_load())


def _iter_cells():
    for fam in FAMILY_SHEETS:
        for col in COLS:
            for w in WIDTHS:
                for h in HEIGHTS:
                    yield fam, col, f"{w}x{h}"


class TestWorkbookIntegrity:
    def test_workbook_has_4464_sale_and_cost_cells(self, workbook):
        sale = cost = 0
        for fam, (s, c) in workbook.items():
            for col in COLS:
                sale += len(s[col]); cost += len(c[col])
        assert sale == 4464 and cost == 4464

    def test_workbook_no_zero_or_inverted_cells(self, workbook):
        bad = [(fam, col, k) for fam, col, k in _iter_cells()
               if workbook[fam][0][col][k] <= 0 or workbook[fam][1][col][k] <= 0
               or workbook[fam][0][col][k] <= workbook[fam][1][col][k]]
        assert bad == []


class TestJsonMatchesWorkbook:
    def test_json_cells_match_workbook(self, workbook, grid_json):
        g = grid_json["grid"]
        sale_mismatch, cost_mismatch, missing = [], [], []
        for fam, col, k in _iter_cells():
            cell = g.get(fam, {}).get(col, {}).get(k)
            if not cell:
                missing.append((fam, col, k)); continue
            if abs(cell["sale"] - workbook[fam][0][col][k]) > 0.005:
                sale_mismatch.append((fam, col, k, cell["sale"], workbook[fam][0][col][k]))
            if abs(cell["internal"] - workbook[fam][1][col][k]) > 0.005:
                cost_mismatch.append((fam, col, k, cell["internal"], workbook[fam][1][col][k]))
        assert missing == [] and sale_mismatch == [] and cost_mismatch == []
        total = sum(len(g[f][c]) for f in g for c in g[f])
        assert total == 4464


class TestDbMatchesWorkbook:
    def test_db_grid_each_tenant_matches_workbook(self, workbook, db_products):
        assert db_products, "Nessun prodotto CASSONETTO_STD in DB"
        for prod in db_products:
            g = prod["pricing_config"]["grid"]
            keys = sum(len(g[f][c]) for f in g for c in g[f])
            assert keys == 4464, f"tenant {prod['tenant_id']}: {keys} celle"
            for fam, col, k in _iter_cells():
                cell = g[fam][col][k]
                assert abs(cell["sale"] - workbook[fam][0][col][k]) <= 0.005, (prod["tenant_id"], fam, col, k)
                assert abs(cell["internal"] - workbook[fam][1][col][k]) <= 0.005, (prod["tenant_id"], fam, col, k)

    def test_db_grid_version_is_workbook_import(self, db_products):
        for prod in db_products:
            assert prod["pricing_config"]["source_file"] == "listino_completo_con_costi.xlsx"
            assert "workbook" in prod["pricing_config"]["grid_version"]


class TestEngineMatchesWorkbook:
    def test_engine_lookup_every_cell(self, workbook, db_products):
        prod = db_products[0]
        n = 0
        for fam, col, k in _iter_cells():
            depth, ceil = col.split("_")
            w, h = k.split("x")
            snap = SimplePricingEngine.compute_grid(
                prod,
                SimplePricingInputs(width_mm=int(w), height_mm=int(h), quantity=1,
                                    options={"depth_mm": int(depth), "ceiling_liner": "SI" if ceil == "c" else "NO"}),
                finish_family=fam,
            )
            assert snap["customer_sale_price_per_item"] == workbook[fam][0][col][k]
            assert snap["internal_production_cost_per_item"] == workbook[fam][1][col][k]
            assert snap["unit_price_final"] == snap["customer_sale_price_per_item"]
            n += 1
        assert n == 4464

    def test_engine_fail_closed_out_of_grid(self, db_products):
        prod = db_products[0]
        for w, h in ((550, 250), (500, 300), (400, 250), (3600, 250), (500, 800)):
            with pytest.raises(ValueError) as ei:
                SimplePricingEngine.compute_grid(prod, SimplePricingInputs(width_mm=w, height_mm=h, options={"depth_mm": 163, "ceiling_liner": "SI"}), finish_family="BIANCO_MASSA")
            assert str(ei.value).startswith("DIMENSION_TO_CONFIRM")

    def test_engine_fail_closed_missing_family(self, db_products):
        prod = db_products[0]
        with pytest.raises(ValueError, match="MISSING_CASSONETTO_COLOR_PRICE_FAMILY"):
            SimplePricingEngine.compute_grid(prod, SimplePricingInputs(width_mm=500, height_mm=250, options={"depth_mm": 163, "ceiling_liner": "SI"}))


class TestGoldenViaApi:
    @pytest.fixture(scope="class")
    def admin(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"]}, timeout=20)
        assert r.status_code == 200, r.text
        s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        return s

    @pytest.fixture(scope="class")
    def pid(self, admin):
        items = admin.get(f"{BASE_URL}/api/multi-cat/products?category_code=CASSONETTI", timeout=20).json()["items"]
        return [p["id"] for p in items if p["key"] == "CASSONETTO_STD"][0]

    @pytest.mark.parametrize("w,h,depth,color,sale,cost", [
        (500, 250, 163, "003", 329.01, 101.23),   # C1
        (500, 550, 163, "003", 422.38, 112.63),   # C2
        (700, 250, 326, "003", 276.13, 110.45),   # C3 (110.45 — valore workbook corrente)
        (500, 250, 163, "100", 370.77, 114.08),   # STANDARD grid
        (500, 250, 163, "019", 399.78, 123.01),   # NON_STANDARD grid
    ])
    def test_golden(self, admin, pid, w, h, depth, color, sale, cost):
        r = admin.post(f"{BASE_URL}/api/multi-cat/products/{pid}/configure", json={"simple_inputs": {
            "width_mm": w, "height_mm": h, "quantity": 1,
            "options": {"color_code": color, "depth_mm": depth, "ceiling_liner": "SI"}}}, timeout=20)
        d = r.json()
        assert d["pricing_status"] == "ok", d.get("blocking_errors")
        s = d["simple_snapshot"]
        assert s["unit_price_final"] == sale and s["customer_sale_price_per_item"] == sale
        assert s["internal_production_cost_per_item"] == cost

    def test_unknown_color_fail_closed(self, admin, pid):
        d = admin.post(f"{BASE_URL}/api/multi-cat/products/{pid}/configure", json={"simple_inputs": {
            "width_mm": 500, "height_mm": 250, "quantity": 1,
            "options": {"color_code": "999", "depth_mm": 163, "ceiling_liner": "SI"}}}, timeout=20).json()
        assert d["pricing_status"] == "invalid_inputs"
        assert any("CASSONETTO_COLOR_FAMILY_UNMAPPED" in e for e in d["blocking_errors"])
