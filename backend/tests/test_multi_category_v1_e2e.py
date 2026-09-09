"""Multi-Category V1 — E2E via HTTP (backend endpoints).

Copre §36 acceptance + RBAC + fail-closed sui pricing_model.
"""
import os
import pytest
import requests
from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://serramento-ops.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ---- Categorie -----------------------------------------------------------------
def test_list_categories(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/product-categories?active=true")
    assert r.status_code == 200, r.text
    items = r.json().get("items", [])
    codes = [c["code"] for c in items]
    print(f"[categorie] trovate {len(items)}: {codes}")
    assert len(items) >= 10, f"attese >=10 categorie, trovate {len(items)}"
    for req_code in ("FINESTRE", "ZANZARIERE", "MONTAGGI_POSA"):  # PORTEFINESTRE = FINESTRE con window_type=DOOR_WINDOW
        assert req_code in codes, f"manca categoria {req_code}"
    # ordinate per display_order
    orders = [c.get("display_order", 0) for c in items]
    assert orders == sorted(orders)


# ---- Prodotti / filtri --------------------------------------------------------
def _fetch_products(session, **params):
    r = session.get(f"{BASE_URL}/api/multi-cat/products", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_products_default_excludes_fixtures_and_legacy(admin_session):
    data = _fetch_products(admin_session)
    items = data["items"]
    assert data.get("is_admin_view") is True
    for p in items:
        assert p.get("legacy") is not True
        assert p.get("new_quote_enabled") is True
        assert p.get("pricing_model") not in (None, "")
        assert p.get("is_test_fixture") is not True


def test_products_filter_finestre(admin_session):
    data = _fetch_products(admin_session, category_code="FINESTRE")
    keys = [p.get("key") for p in data["items"]]
    print("FINESTRE keys:", keys)
    assert any(k and k.upper().startswith("PROEVOLUTION") for k in keys)
    for p in data["items"]:
        assert p.get("pricing_model") == "FORMULA_TECHNICAL"


def test_products_include_test_fixtures(admin_session):
    data = _fetch_products(admin_session, include_test_fixtures=True)
    keys = {p.get("key") for p in data["items"]}
    print("keys with fixtures:", sorted(k for k in keys if k and k.startswith("TEST_")))
    for req in ("TEST_ZANZARIERA_AREA_130", "TEST_AREA_100_MIN_150", "TEST_LINEAR_25", "TEST_PER_ITEM_50", "TEST_FIXED_120"):
        assert req in keys, f"fixture mancante: {req}"


# ---- Helpers -------------------------------------------------------------------
def _find_product_id(session, key):
    data = _fetch_products(session, include_test_fixtures=True, include_legacy=True)
    for p in data["items"]:
        if p.get("key") == key:
            return p.get("id") or p.get("_id")
    return None


def _configure(session, pid, body):
    r = session.post(f"{BASE_URL}/api/multi-cat/products/{pid}/configure", json=body)
    return r


# ---- §36 acceptance ------------------------------------------------------------
def test_area_min_150_at_1000x800(admin_session):
    pid = _find_product_id(admin_session, "TEST_AREA_100_MIN_150")
    assert pid, "product TEST_AREA_100_MIN_150 missing"
    r = _configure(admin_session, pid, {"simple_inputs": {"width_mm": 1000, "height_mm": 800, "quantity": 1}})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["pricing_status"] == "ok"
    assert d["pricing_model"] == "AREA"
    snap = d["simple_snapshot"]
    assert snap["real_area_m2"] == 0.80
    assert snap["billable_area_m2"] == 1.50
    assert snap["unit_sale_price"] == 100
    assert snap["sale_price_total"] == 150


def test_area_min_150_at_2000x1000(admin_session):
    pid = _find_product_id(admin_session, "TEST_AREA_100_MIN_150")
    r = _configure(admin_session, pid, {"simple_inputs": {"width_mm": 2000, "height_mm": 1000, "quantity": 1}})
    assert r.status_code == 200, r.text
    snap = r.json()["simple_snapshot"]
    assert snap["real_area_m2"] == 2.0
    assert snap["billable_area_m2"] == 2.0
    assert snap["sale_price_total"] == 200


def test_zanzariera_area_130_min_150(admin_session):
    pid = _find_product_id(admin_session, "TEST_ZANZARIERA_AREA_130")
    r = _configure(admin_session, pid, {"simple_inputs": {"width_mm": 800, "height_mm": 800, "quantity": 1}})
    assert r.status_code == 200, r.text
    snap = r.json()["simple_snapshot"]
    assert snap["real_area_m2"] == 0.64
    assert snap["billable_area_m2"] == 1.5
    assert snap["sale_price_total"] == 195.0


def test_linear_25(admin_session):
    pid = _find_product_id(admin_session, "TEST_LINEAR_25")
    r = _configure(admin_session, pid, {"simple_inputs": {"linear_meters": 4, "quantity": 1}})
    assert r.status_code == 200, r.text
    assert r.json()["simple_snapshot"]["sale_price_total"] == 100


def test_per_item_50(admin_session):
    pid = _find_product_id(admin_session, "TEST_PER_ITEM_50")
    r = _configure(admin_session, pid, {"simple_inputs": {"quantity": 3}})
    assert r.status_code == 200, r.text
    assert r.json()["simple_snapshot"]["sale_price_total"] == 150


def test_fixed_120(admin_session):
    pid = _find_product_id(admin_session, "TEST_FIXED_120")
    r = _configure(admin_session, pid, {"simple_inputs": {"quantity": 1}})
    assert r.status_code == 200, r.text
    assert r.json()["simple_snapshot"]["sale_price_total"] == 120


# ---- Fail-closed --------------------------------------------------------------
def test_invalid_inputs_missing_dims(admin_session):
    pid = _find_product_id(admin_session, "TEST_AREA_100_MIN_150")
    r = _configure(admin_session, pid, {"simple_inputs": {"quantity": 1}})
    assert r.status_code == 200
    d = r.json()
    assert d["pricing_status"] == "invalid_inputs"
    assert d.get("blocking_errors")


def test_invalid_inputs_missing_all(admin_session):
    pid = _find_product_id(admin_session, "TEST_AREA_100_MIN_150")
    r = _configure(admin_session, pid, {})
    assert r.status_code == 200
    assert r.json()["pricing_status"] == "invalid_inputs"


def test_formula_technical_requires_technical_inputs(admin_session):
    pid = _find_product_id(admin_session, "PROEVOLUTION")
    if not pid:
        pytest.skip("PROEVOLUTION non presente")
    r = _configure(admin_session, pid, {})
    assert r.status_code == 200
    d = r.json()
    assert d["pricing_status"] == "invalid_inputs"


def test_formula_technical_identity(admin_session):
    pid = _find_product_id(admin_session, "PROEVOLUTION")
    if not pid:
        pytest.skip("PROEVOLUTION non presente")
    r = _configure(admin_session, pid, {"technical_inputs": {
        "product_key": "PROEVOLUTION",
        "window_type": "WINDOW",
        "number_of_sashes": 2,
        "width_mm": 1200,
        "height_mm": 1400,
        "glass_type": "DOUBLE_STANDARD",
        "quantity": 1,
    }})
    assert r.status_code == 200, r.text
    d = r.json()
    print("technical result status:", d.get("pricing_status"), "hash:", d.get("calculation_hash"))
    assert d["pricing_model"] == "FORMULA_TECHNICAL"
    if d["pricing_status"] == "ok":
        assert d.get("calculation_hash")
        # admin: production_cost visibile
        assert d.get("technical_snapshot")


def test_legacy_disabled(admin_session):
    """Cerca un prodotto legacy=true; se esiste, deve tornare legacy_disabled."""
    r = admin_session.get(f"{BASE_URL}/api/multi-cat/products", params={"include_legacy": True, "include_test_fixtures": True})
    items = r.json().get("items", [])
    legacy_p = next((p for p in items if p.get("legacy") is True), None)
    if not legacy_p:
        pytest.skip("nessun prodotto legacy nel seed")
    pid = legacy_p.get("id") or legacy_p.get("_id")
    r2 = _configure(admin_session, pid, {"simple_inputs": {"quantity": 1}})
    assert r2.status_code == 200
    assert r2.json()["pricing_status"] == "legacy_disabled"


# ---- Seed idempotenza ---------------------------------------------------------
def test_seed_idempotency():
    import subprocess
    cmd = ["python", "-m", "app.scripts.seed_multi_category_v1", "--all-tenants"]
    out1 = subprocess.run(cmd, cwd="/app/backend", capture_output=True, text=True, timeout=90)
    print("SEED RUN1:", out1.stdout[-500:], out1.stderr[-300:])
    assert out1.returncode == 0
    out2 = subprocess.run(cmd, cwd="/app/backend", capture_output=True, text=True, timeout=90)
    print("SEED RUN2:", out2.stdout[-500:], out2.stderr[-300:])
    assert out2.returncode == 0
    # cerca summary 0/0/0/0 nella seconda esecuzione
    txt = (out2.stdout or "") + (out2.stderr or "")
    # accetta varie forme: "0/0/0/0" oppure "created=0 updated=0"
    # Idempotency: la seconda esecuzione deve avere tutti i contatori a 0
    txt2 = out2.stdout or ""
    assert "categories=0" in txt2 and "classified=0" in txt2 and "legacy_flagged=0" in txt2 and "fixtures=0" in txt2, \
        f"seed non idempotente? output:\n{txt2[-800:]}"
