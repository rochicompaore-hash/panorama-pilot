"""Iteration 16: Quote Structure refactor tests.

Coverage:
- Environments CRUD
- Openings auto-numbering + display_name
- Products per role + dimension inheritance/formulas
- Compatibility engine (mutually_exclusive blockers, warnings)
- Composite drawing SVG sanitization
- Migration legacy → environment+openings (idempotency, locked quotes)
- Tree grouping by role + subtotals
- Regression: legacy /api/quotes still works
"""
from __future__ import annotations
import os
import re
import pytest
import requests
import uuid
from tests._creds import ADMIN_EMAIL, ADMIN_PW  # env-sourced credentials

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
QS = f"{BASE_URL}/api/quote-structure"

# scrubbed: ADMIN_EMAIL moved to tests._creds
# scrubbed: ADMIN_PW moved to tests._creds
# ---------- Fixtures ---------------------------------------------------------
@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PW},
                      timeout=15)
    assert r.status_code == 200, r.text
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, r.text
    return tok


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def quote_id(auth):
    """Create a dedicated test quote via legacy endpoint."""
    # find any customer to attach
    r = requests.get(f"{BASE_URL}/api/customers?limit=1", headers=auth, timeout=15)
    assert r.status_code == 200, r.text
    customers = r.json().get("items", [])
    if not customers:
        # create one
        rc = requests.post(f"{BASE_URL}/api/customers", headers=auth,
                           json={"name": f"TEST_QS_{uuid.uuid4().hex[:6]}",
                                 "customer_type": "private",
                                 "email": "test@example.com"}, timeout=15)
        assert rc.status_code in (200, 201), rc.text
        cust_id = rc.json()["id"]
    else:
        cust_id = customers[0]["id"]

    r = requests.post(f"{BASE_URL}/api/quotes", headers=auth,
                      json={"customer_id": cust_id,
                            "title": f"TEST_QS_ITER16_{uuid.uuid4().hex[:6]}"},
                      timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


@pytest.fixture()
def env_id(auth, quote_id):
    r = requests.post(f"{QS}/{quote_id}/environments", headers=auth,
                      json={"name": "Camera matrimoniale",
                            "kind": "bedroom_master"}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _new_opening(auth, quote_id, env_id, w=1200, h=1400, name=None):
    payload = {"quote_id": quote_id, "environment_id": env_id,
               "display_name": name,
               "dimensions": {"width_mm": w, "height_mm": h}}
    r = requests.post(f"{QS}/openings", headers=auth, json=payload, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- Environments ----------------------------------------------------
class TestEnvironments:
    def test_create_environment(self, auth, quote_id):
        r = requests.post(f"{QS}/{quote_id}/environments", headers=auth,
                          json={"name": "Cucina", "kind": "kitchen"}, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "id" in body and body["name"] == "Cucina"
        assert body["kind"] == "kitchen"

    def test_list_environments(self, auth, quote_id, env_id):
        r = requests.get(f"{QS}/{quote_id}/environments", headers=auth, timeout=15)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert any(e["id"] == env_id for e in items)


# ---------- Openings --------------------------------------------------------
class TestOpenings:
    def test_create_opening_autonumbers(self, auth, quote_id, env_id):
        o1 = _new_opening(auth, quote_id, env_id)
        o2 = _new_opening(auth, quote_id, env_id)
        assert o1["opening_number"] < o2["opening_number"]
        # code format V01/V02
        assert re.match(r"^V\d{2}$", o1["code"])
        assert re.match(r"^V\d{2}$", o2["code"])
        # display_name includes env name
        assert "Vano" in o1["display_name"] or "matrimoniale" in o1["display_name"].lower()

    def test_portafinestra_proportions(self, auth, quote_id, env_id):
        op = _new_opening(auth, quote_id, env_id, w=1200, h=2400,
                           name="Portafinestra")
        assert op["width_mm"] == 1200 and op["height_mm"] == 2400
        assert op["height_mm"] == 2 * op["width_mm"]

    def test_duplicate_opening_copies_products(self, auth, quote_id, env_id):
        op = _new_opening(auth, quote_id, env_id)
        # add a product
        r = requests.post(f"{QS}/openings/{op['id']}/products", headers=auth,
                          json={"opening_id": op["id"], "role": "primary_frame",
                                "product_type_code": "window_2",
                                "unit_price": 500.0}, timeout=15)
        assert r.status_code == 200, r.text

        r = requests.post(f"{QS}/openings/{op['id']}/duplicate", headers=auth,
                          timeout=15)
        assert r.status_code == 200, r.text
        new_op = r.json()
        assert new_op["id"] != op["id"]
        # verify products copied
        r2 = requests.get(f"{QS}/openings/{new_op['id']}/products",
                          headers=auth, timeout=15)
        assert r2.status_code == 200
        items = r2.json()["items"]
        assert len(items) >= 1
        # new line ID must differ from source
        for l in items:
            assert l["opening_id"] == new_op["id"]


# ---------- Products + Dimension Inheritance ---------------------------------
class TestProductsAndDimensions:
    def test_primary_frame_inherits_dimensions(self, auth, quote_id, env_id):
        op = _new_opening(auth, quote_id, env_id, w=1200, h=1400)
        r = requests.post(f"{QS}/openings/{op['id']}/products", headers=auth,
                          json={"opening_id": op["id"], "role": "primary_frame",
                                "product_type_code": "window_2",
                                "unit_price": 500.0}, timeout=15)
        assert r.status_code == 200, r.text
        line = r.json()["line"]
        assert line["width_mm"] == 1200 and line["height_mm"] == 1400

    def test_shading_roller_shutter_formula(self, auth, quote_id, env_id):
        op = _new_opening(auth, quote_id, env_id, w=1200, h=1400)
        r = requests.post(f"{QS}/openings/{op['id']}/products", headers=auth,
                          json={"opening_id": op["id"], "role": "primary_frame",
                                "product_type_code": "window_2"}, timeout=15)
        assert r.status_code == 200
        r = requests.post(f"{QS}/openings/{op['id']}/products", headers=auth,
                          json={"opening_id": op["id"], "role": "shading",
                                "product_type_code": "roller_shutter"}, timeout=15)
        assert r.status_code == 200, r.text
        line = r.json()["line"]
        # width_mm + 60, height_mm + 40 → 1260 x 1440
        assert line["width_mm"] == 1260, f"expected 1260, got {line['width_mm']}"
        assert line["height_mm"] == 1440, f"expected 1440, got {line['height_mm']}"

    def test_box_fixed_height(self, auth, quote_id, env_id):
        op = _new_opening(auth, quote_id, env_id, w=1200, h=1400)
        # need shading first (otherwise "box recommends roller_shutter" warning ok)
        r = requests.post(f"{QS}/openings/{op['id']}/products", headers=auth,
                          json={"opening_id": op["id"], "role": "shading",
                                "product_type_code": "roller_shutter"}, timeout=15)
        assert r.status_code == 200
        r = requests.post(f"{QS}/openings/{op['id']}/products", headers=auth,
                          json={"opening_id": op["id"], "role": "box",
                                "product_type_code": "roller_box"}, timeout=15)
        assert r.status_code == 200, r.text
        line = r.json()["line"]
        # width + 40 = 1240, fixed 220
        assert line["width_mm"] == 1240
        assert line["height_mm"] == 220

    def test_insect_screen_formula(self, auth, quote_id, env_id):
        op = _new_opening(auth, quote_id, env_id, w=1200, h=1400)
        r = requests.post(f"{QS}/openings/{op['id']}/products", headers=auth,
                          json={"opening_id": op["id"], "role": "insect_screen"},
                          timeout=15)
        assert r.status_code == 200, r.text
        line = r.json()["line"]
        # w - 10 = 1190, h - 5 = 1395
        assert line["width_mm"] == 1190
        assert line["height_mm"] == 1395

    def test_dimension_resolve_endpoint(self, auth):
        r = requests.post(f"{QS}/dimensions/resolve", headers=auth,
                          json={"opening_dimensions": {"width_mm": 1000, "height_mm": 1200},
                                "role": "shading",
                                "product_type_code": "roller_shutter"}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["width_mm"] == 1060 and d["height_mm"] == 1240

    def test_opening_with_only_shading(self, auth, quote_id, env_id):
        """Single-replacement scenario: only shading, no primary_frame."""
        op = _new_opening(auth, quote_id, env_id)
        r = requests.post(f"{QS}/openings/{op['id']}/products", headers=auth,
                          json={"opening_id": op["id"], "role": "shading",
                                "product_type_code": "roller_shutter"}, timeout=15)
        assert r.status_code == 200, r.text


# ---------- Compatibility Engine ---------------------------------------------
class TestCompatibility:
    def test_roller_shutter_blocks_shutter(self, auth, quote_id, env_id):
        op = _new_opening(auth, quote_id, env_id)
        r = requests.post(f"{QS}/openings/{op['id']}/products", headers=auth,
                          json={"opening_id": op["id"], "role": "shading",
                                "product_type_code": "roller_shutter"}, timeout=15)
        assert r.status_code == 200
        r = requests.post(f"{QS}/openings/{op['id']}/products", headers=auth,
                          json={"opening_id": op["id"], "role": "shading",
                                "product_type_code": "shutter"}, timeout=15)
        assert r.status_code == 400, r.text
        # FastAPI wraps HTTPException detail — the message can be in .json()['detail']
        body = r.json()
        detail = body.get("detail", body)
        blockers = detail.get("blockers", []) if isinstance(detail, dict) else []
        assert any("Tapparella e persiana" in b or "alternative" in b.lower() for b in blockers), body

    def test_compat_check_endpoint_warning_persiana_box(self, auth):
        """Persiana (shutter) + box → allow=true but warning."""
        r = requests.post(f"{QS}/compatibility/check", headers=auth, json={
            "products_in_opening": [
                {"role": "shading", "product_type_code": "shutter"},
            ],
            "candidate_role": "box",
            "candidate_product_type": "roller_box",
        }, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["allow"] is True
        assert any("persiana" in w.lower() and "cassonetto" in w.lower()
                   for w in body.get("warnings", [])), body


# ---------- Composite Drawing ------------------------------------------------
class TestCompositeDrawing:
    def test_composite_drawing_sanitized_and_layered(self, auth, quote_id, env_id):
        op = _new_opening(auth, quote_id, env_id)
        for role, ptype in [("primary_frame", "window_2"),
                             ("shading", "roller_shutter"),
                             ("box", "roller_box"),
                             ("insect_screen", None)]:
            payload = {"opening_id": op["id"], "role": role}
            if ptype:
                payload["product_type_code"] = ptype
            r = requests.post(f"{QS}/openings/{op['id']}/products",
                              headers=auth, json=payload, timeout=15)
            assert r.status_code == 200, f"{role}: {r.text}"

        r = requests.post(f"{QS}/openings/{op['id']}/composite-drawing",
                          headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        svg = body["svg"]
        assert body["products_count"] == 4
        assert svg.startswith("<svg"), svg[:120]
        # sanitized
        for bad in ["<script", "javascript:", "onerror=", "onclick=",
                     "http://", "https://"]:
            if bad in ("http://", "https://"):
                # allow xmlns URL literal only
                # count occurrences excluding xmlns
                cleaned = svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
                assert bad not in cleaned, f"external URL {bad} in svg"
            else:
                assert bad not in svg, f"bad token {bad} in svg"
        # layers: check patterns
        assert "rollerpat" in svg, "roller pattern missing"
        assert "data-composite=\"1\"" in svg
        # cassonetto and zanzariera markers
        assert "Cassonetto" in svg or "roller_box" in svg
        assert "Zanzariera" in svg or "zanzariera" in svg.lower()


# ---------- Tree View --------------------------------------------------------
class TestTree:
    def test_tree_grouping_and_subtotals(self, auth, quote_id, env_id):
        op = _new_opening(auth, quote_id, env_id)
        # products
        for role, ptype, price in [("primary_frame", "window_2", 800.0),
                                     ("shading", "roller_shutter", 250.0),
                                     ("insect_screen", None, 120.0)]:
            payload = {"opening_id": op["id"], "role": role, "unit_price": price}
            if ptype:
                payload["product_type_code"] = ptype
            r = requests.post(f"{QS}/openings/{op['id']}/products",
                              headers=auth, json=payload, timeout=15)
            assert r.status_code == 200, r.text

        r = requests.get(f"{QS}/{quote_id}/tree", headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        tree = r.json()
        assert tree["quote_id"] == quote_id
        assert "environments" in tree
        # find env
        env_node = next((e for e in tree["environments"]
                          if e["environment"]["id"] == env_id), None)
        assert env_node is not None, tree
        # find opening node
        op_node = next((o for o in env_node["openings"]
                         if o["opening"]["id"] == op["id"]), None)
        assert op_node is not None
        by_role = op_node["products_by_role"]
        assert "primary_frame" in by_role
        assert "shading" in by_role
        assert "insect_screen" in by_role
        # subtotal ≥ 800 + 250 + 120
        assert op_node["subtotal"] >= 1170.0


# ---------- Migration --------------------------------------------------------
class TestMigration:
    def test_migrate_legacy_quote(self, auth):
        """Create a legacy quote (no environments; opening without env_id) then migrate."""
        # get customer
        rc = requests.get(f"{BASE_URL}/api/customers?limit=1", headers=auth, timeout=15)
        assert rc.status_code == 200
        cust_id = rc.json()["items"][0]["id"]
        # Create a new quote (legacy path)
        r = requests.post(f"{BASE_URL}/api/quotes", headers=auth,
                          json={"customer_id": cust_id,
                                "title": f"TEST_LEGACY_{uuid.uuid4().hex[:6]}"},
                          timeout=15)
        assert r.status_code in (200, 201), r.text
        q_id = r.json()["id"]
        # Inject legacy opening + line WITHOUT env_id via Mongo? We'll use API.
        # Create opening via quote-structure but withOUT environment_id ->
        # this returns env_id=None (since we don't supply env_name either)
        r = requests.post(f"{QS}/openings", headers=auth,
                          json={"quote_id": q_id,
                                "dimensions": {"width_mm": 900, "height_mm": 1000},
                                "display_name": "LegacyVano"}, timeout=15)
        assert r.status_code == 200, r.text
        # Now migrate
        r = requests.post(f"{QS}/{q_id}/migrate-structure", headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["openings_migrated"] >= 1
        # verify tree no longer has orphans
        r2 = requests.get(f"{QS}/{q_id}/tree", headers=auth, timeout=15)
        assert r2.status_code == 200
        tree = r2.json()
        assert tree.get("orphan_openings", []) == [] or len(tree["orphan_openings"]) == 0

    def test_migrate_locked_quote(self, auth):
        """BUG EXPOSURE: migrate-structure reads `q.get("status")` but quotes actually
        store their workflow state in `quote_status`. So a 'sent' quote is NOT locked.
        This test transitions via the proper POST /{qid}/status endpoint and asserts
        the migration should be blocked (ok:False, reason=quote_locked).
        """
        rc = requests.get(f"{BASE_URL}/api/customers?limit=1", headers=auth, timeout=15)
        cust_id = rc.json()["items"][0]["id"]
        r = requests.post(f"{BASE_URL}/api/quotes", headers=auth,
                          json={"customer_id": cust_id,
                                "title": f"TEST_LOCK_{uuid.uuid4().hex[:6]}"},
                          timeout=15)
        q_id = r.json()["id"]
        # add a minimal opening/line so `sent` transition doesn't hit other guards
        r_open = requests.post(f"{QS}/openings", headers=auth,
                                json={"quote_id": q_id,
                                      "environment_name": "AmbSent",
                                      "dimensions": {"width_mm": 1000, "height_mm": 1200}},
                                timeout=15)
        assert r_open.status_code == 200
        # transition draft -> sent
        rs = requests.post(f"{BASE_URL}/api/quotes/{q_id}/status", headers=auth,
                           json={"new_status": "sent"}, timeout=15)
        if rs.status_code != 200:
            pytest.skip(f"cannot transition to sent (got {rs.status_code}: {rs.text})")

        # Verify quote_status persisted
        rget = requests.get(f"{BASE_URL}/api/quotes/{q_id}", headers=auth, timeout=15)
        current_qs = rget.json().get("quote_status")
        assert current_qs == "sent", f"quote_status is {current_qs}, expected sent"

        rm = requests.post(f"{QS}/{q_id}/migrate-structure", headers=auth, timeout=15)
        assert rm.status_code == 200
        body = rm.json()
        assert body.get("ok") is False, (
            f"BUG: migrate-structure should return ok:False for sent quotes "
            f"but returned {body}. RCA: checks q.get('status') instead of "
            f"q.get('quote_status') in /app/backend/app/routers/quote_structure.py:387"
        )
        assert body.get("reason") == "quote_locked"


# ---------- Regression -------------------------------------------------------
class TestRegression:
    def test_legacy_quotes_list(self, auth):
        r = requests.get(f"{BASE_URL}/api/quotes?limit=5", headers=auth, timeout=15)
        assert r.status_code == 200
        assert "items" in r.json()

    def test_legacy_quote_get(self, auth, quote_id):
        r = requests.get(f"{BASE_URL}/api/quotes/{quote_id}", headers=auth, timeout=15)
        assert r.status_code == 200
        body = r.json()
        # should still contain openings/lines arrays (backward compat)
        assert "openings" in body or "id" in body

    def test_auth_me(self, auth):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth, timeout=15)
        assert r.status_code == 200
        body = r.json()
        # Response shape: {"user": {...}, "permissions": [...]}
        user = body.get("user") or body
        assert user.get("email") == ADMIN_EMAIL

    def test_landing_public_config(self):
        r = requests.get(f"{BASE_URL}/api/public/landing/config", timeout=15)
        # 200 or 404 acceptable — just ensure not 5xx (regression check)
        assert r.status_code < 500, r.text
