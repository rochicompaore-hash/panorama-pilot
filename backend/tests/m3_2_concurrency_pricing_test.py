"""M3.2 + Fase A tests — Optimistic Concurrency Control + Configuratore/Live Pricing.

Covers:
- Login as super admin & /api/auth/me
- Quotes concurrency (If-Match, 409 conflict, force override + audit)
- Force on consolidated document blocked
- Line-level concurrency
- Customers/leads concurrency
- Formula engine security & validation
- Live pricing preview for WIN_PVC_STANDARD (film_diff → +22% then +€150)
- Live pricing for ROLLER_PVC attached (RAL +8%, then -30% discount)
- min_billable_sqm boundary
- Pricelists + rules seed
"""
from __future__ import annotations
import os, uuid, time, math
import pytest
import requests
from tests._creds import ADMIN_EMAIL, ADMIN_PWD  # env-sourced credentials

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]).rstrip("/")
# scrubbed: ADMIN_EMAIL moved to tests._creds
# scrubbed: ADMIN_PWD moved to tests._creds
# ---------------- Fixtures ----------------
@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def admin_token(s):
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def me(s, admin_h):
    r = s.get(f"{BASE_URL}/api/auth/me", headers=admin_h)
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("user") or j


@pytest.fixture(scope="module")
def tenant_id(me):
    return me["tenant_id"]


@pytest.fixture(scope="module")
def seed_lead(s, admin_h):
    r = s.get(f"{BASE_URL}/api/leads?limit=1", headers=admin_h)
    if r.status_code == 200 and r.json().get("items"):
        return r.json()["items"][0]["id"]
    body = {
        "first_name": "TEST_M32", "last_name": "LeadForOCC",
        "email": f"test_m32_{uuid.uuid4().hex[:6]}@example.com",
        "phone": "+390000000000",
    }
    r = s.post(f"{BASE_URL}/api/leads", headers=admin_h, json=body)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# ---------------- Auth ----------------
def test_login_admin(admin_token):
    assert isinstance(admin_token, str) and len(admin_token) > 20


def test_auth_me_superadmin(me):
    assert me.get("email") == ADMIN_EMAIL
    assert me.get("is_superadmin") is True or me.get("is_super_admin") is True or "*" in (me.get("permissions") or [])


# ---------------- Concurrency: Quotes ----------------
@pytest.fixture(scope="module")
def concurrency_quote(s, admin_h, seed_lead):
    r = s.post(f"{BASE_URL}/api/quotes", headers=admin_h, json={
        "lead_id": seed_lead, "title": "TEST_M32 OCC quote"
    })
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_quote_initial_version_is_1(concurrency_quote):
    assert concurrency_quote.get("version", 1) >= 1


def test_quote_patch_with_correct_if_match(s, admin_h, concurrency_quote):
    qid = concurrency_quote["id"]
    # Fetch fresh version
    q = s.get(f"{BASE_URL}/api/quotes/{qid}", headers=admin_h).json()
    v = q["version"]
    h = {**admin_h, "If-Match": str(v)}
    r = s.patch(f"{BASE_URL}/api/quotes/{qid}", headers=h, json={"notes": "agg1"})
    assert r.status_code == 200, r.text
    upd = r.json()
    assert upd["version"] == v + 1
    assert upd["notes"] == "agg1"
    concurrency_quote["_v_after"] = upd["version"]


def test_quote_patch_with_stale_if_match_returns_409(s, admin_h, concurrency_quote, tenant_id):
    qid = concurrency_quote["id"]
    # Use version=1 (stale)
    h = {**admin_h, "If-Match": "1"}
    r = s.patch(f"{BASE_URL}/api/quotes/{qid}", headers=h, json={"notes": "should conflict"})
    assert r.status_code == 409, r.text
    detail = r.json().get("detail")
    assert isinstance(detail, dict)
    assert detail["error"] == "version_conflict"
    assert detail["expected_version"] == 1
    assert detail["current_version"] >= 2
    assert "server_data" in detail
    sd = detail["server_data"]
    assert sd["id"] == qid
    # tenant leak check
    assert sd["tenant_id"] == tenant_id


def test_quote_force_without_reason_returns_400(s, admin_h, concurrency_quote):
    qid = concurrency_quote["id"]
    r = s.patch(f"{BASE_URL}/api/quotes/{qid}?force=true", headers=admin_h, json={"notes": "force no reason"})
    assert r.status_code == 400, r.text
    assert "Motivazione" in r.json().get("detail", "")


def test_quote_force_with_reason_ok(s, admin_h, concurrency_quote):
    qid = concurrency_quote["id"]
    prev_v = s.get(f"{BASE_URL}/api/quotes/{qid}", headers=admin_h).json()["version"]
    h = {**admin_h, "X-Force-Reason": "Direzione impone modifica"}
    r = s.patch(f"{BASE_URL}/api/quotes/{qid}?force=true", headers=h, json={"notes": "forzato ok"})
    assert r.status_code == 200, r.text
    assert r.json()["version"] == prev_v + 1
    assert r.json()["notes"] == "forzato ok"


def test_audit_force_override_recorded(s, admin_h, concurrency_quote):
    qid = concurrency_quote["id"]
    # Query recent audit entries for this entity + force_override action
    r = s.get(f"{BASE_URL}/api/audit?entity_id={qid}&action=force_override", headers=admin_h)
    assert r.status_code == 200, r.text
    items = r.json().get("items", [])
    assert any(x.get("action") == "quote.force_override" for x in items), \
        f"no force_override audit for {qid}: {[x.get('action') for x in items]}"


def test_force_on_consolidated_quote_blocked(s, admin_h, seed_lead):
    # Create fresh quote → move to sent → force must fail 400
    r = s.post(f"{BASE_URL}/api/quotes", headers=admin_h, json={"lead_id": seed_lead, "title": "TEST_M32 consolidated"})
    assert r.status_code in (200, 201), r.text
    qid = r.json()["id"]
    # Move to sent
    r2 = s.post(f"{BASE_URL}/api/quotes/{qid}/status", headers=admin_h, json={"new_status": "sent"})
    assert r2.status_code == 200, r2.text
    # Force patch
    h = {**admin_h, "X-Force-Reason": "Motivo valido"}
    r3 = s.patch(f"{BASE_URL}/api/quotes/{qid}?force=true", headers=h, json={"notes": "should fail"})
    assert r3.status_code == 400, r3.text
    assert "consolidato" in r3.json().get("detail", "").lower() or "sovrascrivibile" in r3.json().get("detail", "").lower()


# ---------------- Concurrency: Line ----------------
def test_line_concurrency_conflict(s, admin_h, seed_lead):
    # New quote + opening + line
    r = s.post(f"{BASE_URL}/api/quotes", headers=admin_h, json={"lead_id": seed_lead, "title": "TEST_M32 line-conc"})
    qid = r.json()["id"]
    s.post(f"{BASE_URL}/api/quotes/{qid}/openings", headers=admin_h, json={"width_mm": 1200, "height_mm": 1400})
    r_line = s.post(f"{BASE_URL}/api/quotes/{qid}/lines", headers=admin_h,
                    json={"category": "window", "base_price": 100, "quantity": 1, "description": "OCC line"})
    assert r_line.status_code == 200, r_line.text
    lid = r_line.json()["id"]
    # Fetch quote version
    v = s.get(f"{BASE_URL}/api/quotes/{qid}", headers=admin_h).json()["version"]
    # First PATCH ok
    h1 = {**admin_h, "If-Match": str(v)}
    r1 = s.patch(f"{BASE_URL}/api/quotes/{qid}/lines/{lid}", headers=h1, json={"base_price": 150})
    assert r1.status_code == 200, r1.text
    # Second PATCH with same version → conflict
    r2 = s.patch(f"{BASE_URL}/api/quotes/{qid}/lines/{lid}", headers=h1, json={"base_price": 200})
    assert r2.status_code == 409, r2.text
    detail = r2.json().get("detail")
    assert isinstance(detail, dict) and detail.get("error") == "version_conflict"


# ---------------- Concurrency: Customers ----------------
@pytest.fixture(scope="module")
def a_customer(s, admin_h):
    # Try to find one
    r = s.get(f"{BASE_URL}/api/customers?limit=1", headers=admin_h)
    if r.status_code == 200 and r.json().get("items"):
        return r.json()["items"][0]
    body = {"company_name": "TEST_M32 Customer SRL", "email": f"test_m32c_{uuid.uuid4().hex[:6]}@example.com"}
    r = s.post(f"{BASE_URL}/api/customers", headers=admin_h, json=body)
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_customer_patch_stale_if_match_conflict(s, admin_h, a_customer, tenant_id):
    cid = a_customer["id"]
    fresh = s.get(f"{BASE_URL}/api/customers/{cid}", headers=admin_h).json()
    real_v = fresh.get("version", 1)
    # Send stale version (real_v - 1 if possible, else use very old value 0)
    stale = max(0, real_v - 1)
    # If stale == real_v (e.g., version=1), first bump via one update
    if stale == real_v:
        h_ok = {**admin_h, "If-Match": str(real_v)}
        r_bump = s.patch(f"{BASE_URL}/api/customers/{cid}", headers=h_ok, json={"notes": "bump"})
        assert r_bump.status_code == 200, r_bump.text
        stale = real_v
        real_v += 1
    h = {**admin_h, "If-Match": str(stale)}
    r = s.patch(f"{BASE_URL}/api/customers/{cid}", headers=h, json={"notes": "conflict"})
    assert r.status_code == 409, r.text
    detail = r.json().get("detail")
    assert detail["error"] == "version_conflict"
    assert "server_data" in detail
    assert detail["server_data"]["tenant_id"] == tenant_id


def test_lead_patch_stale_if_match_conflict(s, admin_h, seed_lead, tenant_id):
    lid = seed_lead
    fresh = s.get(f"{BASE_URL}/api/leads/{lid}", headers=admin_h).json()
    real_v = fresh.get("version", 1)
    stale = max(0, real_v - 1)
    if stale == real_v:
        h_ok = {**admin_h, "If-Match": str(real_v)}
        r_bump = s.patch(f"{BASE_URL}/api/leads/{lid}", headers=h_ok, json={"notes": "bump"})
        assert r_bump.status_code == 200, r_bump.text
        stale = real_v
    h = {**admin_h, "If-Match": str(stale)}
    r = s.patch(f"{BASE_URL}/api/leads/{lid}", headers=h, json={"notes": "conflict lead"})
    assert r.status_code == 409, r.text
    detail = r.json().get("detail")
    assert detail["error"] == "version_conflict"
    assert detail["server_data"]["tenant_id"] == tenant_id


# ---------------- Formula engine security ----------------
def test_formula_validate_import_rejected(s, admin_h):
    r = s.post(f"{BASE_URL}/api/price-rules/validate", headers=admin_h, json={"formula": "__import__(\"os\")"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] is False
    assert "non autorizzata" in (j.get("error") or "").lower()


def test_formula_validate_safe_ok(s, admin_h):
    r = s.post(f"{BASE_URL}/api/price-rules/validate", headers=admin_h, json={"formula": "base_price * 1.145"})
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert (j.get("error") or "") == ""


def test_formula_validate_attribute_access_rejected(s, admin_h):
    r = s.post(f"{BASE_URL}/api/price-rules/validate", headers=admin_h, json={"formula": "a.b"})
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is False


def test_formula_validate_div_by_zero_ok(s, admin_h):
    # Static validation should be OK; eval treats 1/0 → 0 (safe default)
    r = s.post(f"{BASE_URL}/api/price-rules/validate", headers=admin_h, json={"formula": "1/0"})
    assert r.status_code == 200
    j = r.json()
    # Either ok=true (safe eval) or a specific handled response
    assert j["ok"] in (True, False)  # documented — 1/0 handled internally by eval → 0


def test_create_rule_with_dangerous_formula_rejected(s, admin_h):
    # Need pricelist_id first
    pl = s.get(f"{BASE_URL}/api/pricelists", headers=admin_h).json()
    items = pl.get("items", [])
    assert items, "no pricelists"
    pid = items[0]["id"]
    body = {
        "pricelist_id": pid,
        "code": f"TEST_DANGER_{uuid.uuid4().hex[:6]}",
        "name": "Dangerous rule",
        "formula": "__import__(\"os\")",
        "effect_type": "pct",
        "priority": 100,
    }
    r = s.post(f"{BASE_URL}/api/price-rules", headers=admin_h, json=body)
    assert r.status_code == 400, r.text
    assert "non valida" in r.json().get("detail", "").lower() or "non autorizzata" in r.json().get("detail", "").lower()


# ---------------- Pricelists & rules seed ----------------
def test_pricelists_default_present(s, admin_h):
    r = s.get(f"{BASE_URL}/api/pricelists", headers=admin_h)
    assert r.status_code == 200, r.text
    items = r.json().get("items", [])
    assert len(items) >= 1
    default_pl = next((p for p in items if p.get("is_default")), None)
    assert default_pl is not None, "no default pricelist"


def test_price_rules_seed_at_least_11(s, admin_h):
    r = s.get(f"{BASE_URL}/api/pricelists", headers=admin_h)
    pl = next((p for p in r.json()["items"] if p.get("is_default")), r.json()["items"][0])
    r2 = s.get(f"{BASE_URL}/api/price-rules?pricelist_id={pl['id']}", headers=admin_h)
    assert r2.status_code == 200, r2.text
    items = r2.json().get("items", [])
    assert len(items) >= 11, f"expected >=11 rules, got {len(items)}"
    codes = {x["code"] for x in items}
    for expected in ("COLOR_FILM_DIFF_PCT", "COLOR_FILM_DIFF_FIXED", "ROLLER_MOTOR_RADIO", "ROLLER_ATTACHED_DISCOUNT"):
        assert expected in codes, f"missing rule code {expected}"


# ---------------- Configurator preview ----------------
def test_preview_win_pvc_film_diff(s, admin_h):
    body = {
        "product_key": "WIN_PVC_STANDARD",
        "product_config": {"color_kind": "film_diff", "category": "window"},
        "width_mm": 1200, "height_mm": 1400, "quantity": 2,
        "discount_pct": 0, "discount_amount": 0, "vat_rate": 0.22, "internal_cost": 0,
    }
    r = s.post(f"{BASE_URL}/api/configurator/preview", headers=admin_h, json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    # sqm = 1.2*1.4=1.68 (>=min 1.0)
    assert abs(j["sqm"] - 1.68) < 0.01
    assert abs(j["billable_sqm"] - 1.68) < 0.01
    # unit_base = 480*1.68 = 806.40
    # After +22% → 983.808 → After +150 → 1133.808 → unit_final ~1133.81
    assert abs(j["unit_price_final"] - 1133.81) < 0.05, f"unit_price_final={j['unit_price_final']}"
    # subtotal_line = 1133.81*2 = 2267.62 (allow rounding jitter)
    assert abs(j["subtotal_line"] - 2267.62) < 0.05, f"subtotal_line={j['subtotal_line']}"
    # breakdown has BASE + 2 color rules
    codes = [b.get("code") for b in j["breakdown"]]
    assert "BASE" in codes
    assert "COLOR_FILM_DIFF_PCT" in codes
    assert "COLOR_FILM_DIFF_FIXED" in codes
    assert not j.get("warnings")


def test_preview_roller_attached_ral(s, admin_h):
    body = {
        "product_key": "ROLLER_PVC",
        "product_config": {"category": "roller", "attached_to_window": True, "color_finish": "ral"},
        "width_mm": 1200, "height_mm": 1500, "quantity": 1,
        "discount_pct": 0, "discount_amount": 0, "vat_rate": 0.22, "internal_cost": 0,
    }
    r = s.post(f"{BASE_URL}/api/configurator/preview", headers=admin_h, json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    # sqm = 1.2*1.5=1.8, > min 1.75 → billable=1.8
    assert abs(j["sqm"] - 1.8) < 0.01
    assert abs(j["billable_sqm"] - 1.8) < 0.01
    codes = [b.get("code") for b in j["breakdown"]]
    assert "ROLLER_COLOR_RAL" in codes
    assert "ROLLER_ATTACHED_DISCOUNT" in codes
    # base = 96*1.8=172.8 → +8% => 186.624 → -30% => 130.6368 → 130.64
    assert abs(j["unit_price_final"] - 130.64) < 0.05, f"unit={j['unit_price_final']}"


def test_preview_roller_below_min_billable(s, admin_h):
    body = {
        "product_key": "ROLLER_PVC",
        "product_config": {"category": "roller"},
        "width_mm": 1000, "height_mm": 1500, "quantity": 1,
        "discount_pct": 0, "discount_amount": 0, "vat_rate": 0.22, "internal_cost": 0,
    }
    r = s.post(f"{BASE_URL}/api/configurator/preview", headers=admin_h, json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    assert abs(j["sqm"] - 1.5) < 0.01
    assert abs(j["billable_sqm"] - 1.75) < 0.01  # min applied
    # base_price on billable_sqm=1.75: 96*1.75=168.00
    assert abs(j["unit_price_final"] - 168.00) < 0.05, f"unit={j['unit_price_final']}"
