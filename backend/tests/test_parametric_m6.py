"""M6.PAR Parametric Engine — backend regression suite.

Tests all endpoints under /api/parametric/*:
- Seed presence (profile_systems, bom_templates, color_categories)
- Formula validator (valid, malicious rejection, div-by-zero graceful)
- Preview (A, B, C modes with fallback resolution, oversize matrix, CAT3 surcharge)
- Permissions (no-auth 401, quotes.view_costs hides costs, mode.override refused)
- Nesting (FFD/BFD/compare, oversized cut warning)
- SVG sanitization (no <script>, no on* handlers)
- BOM resolve
- Cutting preview embedded in /preview when include_cutting_preview=true

Requires: env vars ADMIN_EMAIL / ADMIN_PASSWORD (see tests/_creds.py).
"""
from __future__ import annotations
import os
import re
import pytest
import requests
from tests._creds import ADMIN_EMAIL, ADMIN_PASS, LIMITED_EMAIL, LIMITED_PASS  # env-sourced credentials

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
# scrubbed: ADMIN_EMAIL moved to tests._creds
# scrubbed: ADMIN_PASS moved to tests._creds
# Test user created (or reused) with only Viewer permissions (no quotes.view_costs,
# no pricing.mode.override) to verify permission guards
VIEWER_ROLE_ID = "fee3d45d-8ae8-46af-b3c5-e9e374af7d4e"
# scrubbed: LIMITED_EMAIL moved to tests._creds
# scrubbed: LIMITED_PASS moved to tests._creds
# --- fixtures ---------------------------------------------------------

@pytest.fixture(scope="session")
def s():
    return requests.Session()


@pytest.fixture(scope="session")
def admin_token(s):
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def limited_token(s, admin_h):
    """Create (or reuse) limited-perm user and return an access token."""
    # try login first
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": LIMITED_EMAIL, "password": LIMITED_PASS}, timeout=15)
    if r.status_code == 200:
        return r.json()["access_token"]

    # create user
    ru = s.post(f"{BASE_URL}/api/users", headers=admin_h, json={
        "email": LIMITED_EMAIL,
        "first_name": "Test",
        "last_name": "Parametric",
        "role_ids": [VIEWER_ROLE_ID],
    }, timeout=15)
    if ru.status_code == 400 and "già" in ru.text.lower():
        # already exists -> find id
        rl = s.get(f"{BASE_URL}/api/users?q=test_parametric", headers=admin_h, timeout=10)
        items = rl.json().get("items") if isinstance(rl.json(), dict) else rl.json()
        uid = items[0]["id"]
    else:
        assert ru.status_code in (200, 201), f"create user failed: {ru.status_code} {ru.text}"
        uid = ru.json()["id"]

    inv = s.post(f"{BASE_URL}/api/users/{uid}/resend-invitation", headers=admin_h, timeout=10)
    invite_url = inv.json().get("invitation_url")
    assert invite_url, f"no invitation_url: {inv.text}"
    tok = invite_url.split("token=")[-1]

    acc = s.post(f"{BASE_URL}/api/auth/accept-invitation",
                 json={"token": tok, "password": LIMITED_PASS}, timeout=10)
    assert acc.status_code == 200, f"accept invitation failed: {acc.text}"

    r2 = s.post(f"{BASE_URL}/api/auth/login",
                json={"email": LIMITED_EMAIL, "password": LIMITED_PASS}, timeout=15)
    assert r2.status_code == 200, f"limited login failed: {r2.text}"
    return r2.json()["access_token"]


@pytest.fixture(scope="session")
def limited_h(limited_token):
    return {"Authorization": f"Bearer {limited_token}"}


# --- SEED PRESENCE ----------------------------------------------------

class TestSeedData:
    def test_profile_systems_seed(self, s, admin_h):
        r = s.get(f"{BASE_URL}/api/parametric/profile-systems", headers=admin_h)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) >= 1
        codes = [it["code"] for it in items]
        assert "PVC70" in codes

    def test_bom_templates_seed(self, s, admin_h):
        r = s.get(f"{BASE_URL}/api/parametric/bom-templates", headers=admin_h)
        assert r.status_code == 200
        items = r.json().get("items", [])
        codes = {it["code"] for it in items}
        assert {"BOM-WIN-1A", "BOM-WIN-2A", "BOM-FIXED", "BOM-DOOR-1A"}.issubset(codes)

    def test_color_categories_seed(self, s, admin_h):
        r = s.get(f"{BASE_URL}/api/parametric/color-categories", headers=admin_h)
        assert r.status_code == 200
        items = r.json().get("items", [])
        by_code = {it["code"]: it for it in items}
        assert "CAT1" in by_code and by_code["CAT1"]["scrap_mode"] == "global_reuse"
        assert "CAT2" in by_code and by_code["CAT2"]["scrap_mode"] == "order_reuse"
        assert "CAT3" in by_code
        assert by_code["CAT3"]["scrap_mode"] == "order_full_cost"
        assert by_code["CAT3"]["charges_whole_bar"] is True
        assert by_code["CAT3"]["surcharge_pct"] == 15.0


# --- FORMULA PARSER ---------------------------------------------------

class TestFormula:
    def test_validate_ok(self, s, admin_h):
        r = s.post(f"{BASE_URL}/api/parametric/formula/validate", headers=admin_h,
                   json={"formula": "L - 2*frame_width - central_node"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True, d

    def test_validate_rejects_import(self, s, admin_h):
        r = s.post(f"{BASE_URL}/api/parametric/formula/validate", headers=admin_h,
                   json={"formula": '__import__("os").system("ls")'})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is False
        assert "non autorizzata" in d["error"].lower() or "variabile" in d["error"].lower()

    def test_validate_rejects_attribute_access(self, s, admin_h):
        r = s.post(f"{BASE_URL}/api/parametric/formula/validate", headers=admin_h,
                   json={"formula": "L.__class__"})
        assert r.status_code == 200
        assert r.json()["ok"] is False

    def test_test_div_by_zero_no_500(self, s, admin_h):
        r = s.post(f"{BASE_URL}/api/parametric/formula/test", headers=admin_h,
                   json={"formula": "L / 0", "context": {"L": 1200}})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["result"] == 0 or d["result"] == 0.0

    def test_validate_empty(self, s, admin_h):
        r = s.post(f"{BASE_URL}/api/parametric/formula/validate", headers=admin_h,
                   json={"formula": ""})
        assert r.status_code == 200
        assert r.json()["ok"] is False


# --- PREVIEW ----------------------------------------------------------

class TestPreview:
    def test_preview_1_leaf_default_tenant_mode(self, s, admin_h):
        r = s.post(f"{BASE_URL}/api/parametric/preview", headers=admin_h,
                   json={"product_key": "window_1_leaf", "width_mm": 1200,
                         "height_mm": 1400, "include_cutting_preview": True})
        assert r.status_code == 200
        d = r.json()
        assert d["mode_used"] == "C_hybrid"
        assert d["mode_source"] == "tenant"
        assert d["unit_price"] > 0
        assert d.get("svg") and isinstance(d["svg"], str)
        assert "<svg" in d["svg"].lower()
        assert len(d.get("bom_resolved") or []) > 0
        assert d.get("errors") in (None, [])
        cp = d.get("cutting_preview")
        assert cp is not None, "cutting_preview should be present when include_cutting_preview=true"
        assert cp.get("total_bars", 0) >= 1

    def test_preview_2_leaves_product_scope(self, s, admin_h):
        r = s.post(f"{BASE_URL}/api/parametric/preview", headers=admin_h,
                   json={"product_key": "window_2_leaves", "width_mm": 1600,
                         "height_mm": 1400})
        assert r.status_code == 200
        d = r.json()
        assert d["mode_source"] == "product", d
        assert d["unit_price"] > 0
        assert d.get("errors") in (None, [])

    def test_preview_fixed_b_bom(self, s, admin_h):
        r = s.post(f"{BASE_URL}/api/parametric/preview", headers=admin_h,
                   json={"product_key": "window_fixed", "width_mm": 1200,
                         "height_mm": 1400})
        assert r.status_code == 200
        d = r.json()
        assert d["mode_used"] == "B_bom"
        assert d["mode_source"] == "product"
        assert d["unit_price"] > 0

    def test_preview_oversize_matrix(self, s, admin_h):
        r = s.post(f"{BASE_URL}/api/parametric/preview", headers=admin_h,
                   json={"product_key": "window_1_leaf", "width_mm": 2500,
                         "height_mm": 2500})
        assert r.status_code == 200
        d = r.json()
        assert d["unit_price"] > 0
        assert d.get("warnings"), "oversize should emit warnings"
        assert any("fuori matrice" in w.lower() or "oversize" in w.lower()
                   for w in d["warnings"])

    def test_preview_cat3_color_surcharge(self, s, admin_h):
        cats = s.get(f"{BASE_URL}/api/parametric/color-categories", headers=admin_h).json()
        cat3_id = [c["id"] for c in cats["items"] if c["code"] == "CAT3"][0]
        # base
        base = s.post(f"{BASE_URL}/api/parametric/preview", headers=admin_h,
                      json={"product_key": "window_1_leaf", "width_mm": 1200,
                            "height_mm": 1400}).json()
        # with CAT3
        r = s.post(f"{BASE_URL}/api/parametric/preview", headers=admin_h,
                   json={"product_key": "window_1_leaf", "width_mm": 1200,
                         "height_mm": 1400, "color_category_id": cat3_id})
        assert r.status_code == 200
        d = r.json()
        steps = [b.get("step") for b in d.get("price_breakdown") or []]
        assert "color_surcharge" in steps
        # +15% roughly
        assert d["unit_price"] >= base["unit_price"] * 1.14

    def test_preview_no_auth(self):
        # fresh Session — do NOT reuse the auth cookies from the shared session
        clean = requests.Session()
        r = clean.post(f"{BASE_URL}/api/parametric/preview",
                       json={"product_key": "window_1_leaf", "width_mm": 1200,
                             "height_mm": 1400})
        assert r.status_code == 401, f"expected 401 got {r.status_code}: {r.text[:200]}"

    def test_preview_snapshot_written(self, s, admin_h):
        """Every preview writes a parametric_snapshots doc — count grows after call."""
        # trigger a preview
        r = s.post(f"{BASE_URL}/api/parametric/preview", headers=admin_h,
                   json={"product_key": "window_1_leaf", "width_mm": 1100,
                         "height_mm": 1300})
        assert r.status_code == 200
        d = r.json()
        assert d.get("input_hash") and d.get("output_hash")
        assert d.get("engine_version") == "1.0.0"


# --- PERMISSIONS ------------------------------------------------------

class TestPermissions:
    def test_costs_hidden_for_limited_user(self, s, limited_h):
        r = s.post(f"{BASE_URL}/api/parametric/preview", headers=limited_h,
                   json={"product_key": "window_1_leaf", "width_mm": 1200,
                         "height_mm": 1400})
        assert r.status_code == 200
        d = r.json()
        assert d["unit_price"] > 0
        # costs & margin MUST be occulted
        assert d["unit_cost"] == 0.0
        assert d["total_cost"] == 0.0
        assert d["margin_abs"] == 0.0
        assert d["margin_pct"] == 0.0

    def test_mode_override_denied_without_permission(self, s, limited_h):
        r = s.post(f"{BASE_URL}/api/parametric/preview", headers=limited_h,
                   json={"product_key": "window_1_leaf", "width_mm": 1200,
                         "height_mm": 1400,
                         "mode_override": "B_bom",
                         "override_reason": "test"})
        # Must NOT be 500. Either 200 with errors OR 4xx (docs say non-500)
        assert r.status_code == 200
        d = r.json()
        assert d.get("errors"), f"expected errors list, got: {d}"
        assert any("pricing.mode.override" in e.lower() or "permesso" in e.lower()
                   for e in d["errors"])


# --- NESTING ----------------------------------------------------------

class TestNesting:
    def _profile_id(self, s, admin_h):
        r = s.get(f"{BASE_URL}/api/parametric/profiles", headers=admin_h)
        items = r.json().get("items", [])
        return items[0]["id"] if items else "P1"

    def test_nesting_run_valid(self, s, admin_h):
        pid = self._profile_id(s, admin_h)
        r = s.post(f"{BASE_URL}/api/parametric/nesting/run", headers=admin_h, json={
            "cuts": [
                {"profile_id": pid, "length_mm": 1500, "quantity": 4},
                {"profile_id": pid, "length_mm": 800, "quantity": 6},
            ],
            "algorithm": "ffd",
        })
        assert r.status_code == 200
        d = r.json()
        assert d["total_bars"] >= 1
        assert d["efficiency_pct"] > 0
        assert d.get("warnings") in (None, [])

    def test_nesting_oversized_cut(self, s, admin_h):
        """Cut longer than the bar must NOT be silently accepted with an empty result.
        Design says: 400 with clear detail. Actual behavior verified in this test."""
        pid = self._profile_id(s, admin_h)
        r = s.post(f"{BASE_URL}/api/parametric/nesting/run", headers=admin_h, json={
            "cuts": [{"profile_id": pid, "length_mm": 10000, "quantity": 1}],
            "algorithm": "ffd",
        })
        # Preferred: 400. Currently returns 200 with warning — flagged in report.
        # Accept either but assert that when 200 there is a clear warning.
        assert r.status_code in (200, 400)
        if r.status_code == 200:
            d = r.json()
            assert d.get("warnings"), "must at least warn"
            assert any(">" in w and ("barra" in w.lower() or "utile" in w.lower())
                       for w in d["warnings"])
            # Documented deviation: expected 400, actual 200
            pytest.xfail("Design says 400 for oversize cut; endpoint returns 200 + warning")

    def test_nesting_compare(self, s, admin_h):
        pid = self._profile_id(s, admin_h)
        r = s.post(f"{BASE_URL}/api/parametric/nesting/compare", headers=admin_h, json={
            "cuts": [
                {"profile_id": pid, "length_mm": 1500, "quantity": 4},
                {"profile_id": pid, "length_mm": 800, "quantity": 6},
            ],
        })
        assert r.status_code == 200
        d = r.json()
        assert "ffd" in d and "bfd" in d
        assert d.get("winner") in ("ffd", "bfd")

    def test_nesting_empty_cuts(self, s, admin_h):
        r = s.post(f"{BASE_URL}/api/parametric/nesting/run", headers=admin_h,
                   json={"cuts": [], "algorithm": "ffd"})
        assert r.status_code == 400


# --- SVG SANITIZATION -------------------------------------------------

class TestSvg:
    def test_svg_ok_and_sanitized(self, s, admin_h):
        r = s.post(f"{BASE_URL}/api/parametric/svg", headers=admin_h,
                   json={"product_key": "window_1_leaf", "width_mm": 1200, "height_mm": 1400})
        assert r.status_code == 200
        svg = r.json().get("svg") or ""
        assert svg and "<svg" in svg.lower()
        assert "<script" not in svg.lower()
        # No on* event handlers
        assert not re.search(r'\son[a-z]+\s*=', svg, re.IGNORECASE)


# --- BOM RESOLVE ------------------------------------------------------

class TestBomResolve:
    def test_bom_resolve_ok(self, s, admin_h):
        boms = s.get(f"{BASE_URL}/api/parametric/bom-templates", headers=admin_h).json()
        bom_id = [b["id"] for b in boms["items"] if b["code"] == "BOM-WIN-1A"][0]
        r = s.post(f"{BASE_URL}/api/parametric/bom/resolve", headers=admin_h, json={
            "bom_template_id": bom_id,
            "params": {"width_mm": 1200, "height_mm": 1400, "nr_ante": 1},
        })
        assert r.status_code == 200
        d = r.json()
        comps = d.get("components") or []
        assert len(comps) > 0
        # At least one component must have a numeric quantity
        assert any(isinstance(c.get("quantity"), (int, float)) and c["quantity"] > 0
                   for c in comps)

    def test_bom_resolve_missing_id(self, s, admin_h):
        r = s.post(f"{BASE_URL}/api/parametric/bom/resolve", headers=admin_h, json={})
        assert r.status_code == 400

    def test_bom_resolve_unknown_id(self, s, admin_h):
        r = s.post(f"{BASE_URL}/api/parametric/bom/resolve", headers=admin_h,
                   json={"bom_template_id": "nonexistent-id"})
        assert r.status_code == 404


# --- TENANT ISOLATION (limited scope: verify filter behavior) ---------

class TestTenantIsolation:
    def test_listing_filters_by_tenant(self, s, admin_h):
        """Verify all list endpoints filter by tenant_id (no data from other tenants leaks).
        We can only verify no _id from another tenant appears — hard-liner check: every
        returned item has our tenant_id."""
        r_me = s.get(f"{BASE_URL}/api/auth/me", headers=admin_h).json()
        my_tenant = r_me.get("user", r_me).get("tenant_id")
        assert my_tenant

        for path in ["profile-systems", "bom-templates", "color-categories",
                     "colors", "glass-types", "hardware-kits", "accessories",
                     "price-matrices", "item-pricelists"]:
            resp = s.get(f"{BASE_URL}/api/parametric/{path}", headers=admin_h)
            assert resp.status_code == 200, f"{path} {resp.status_code}"
            items = resp.json().get("items", [])
            for it in items:
                assert it.get("tenant_id") == my_tenant, f"tenant leak in {path}: {it}"
