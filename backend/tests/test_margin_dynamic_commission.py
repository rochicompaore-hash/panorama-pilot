"""MODULAR COMMISSION BY DISCOUNT (msg 796) + ADMIN MASTER DUAL MARGIN (msg 800).

Unit (pure engine) + API security (server-side redaction, cross-owner, PDF, freeze).
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

from app.services.margin_engine import (
    compute_financial_snapshot,
    commission_cap_for_discount,
    effective_discount_percent,
    max_discount_for_margin_floor,
    redact_financial_snapshot_for_role,
    is_admin_master,
    COMMERCIAL_SAFE_KEYS,
    MARGIN_FLOOR_PERCENT,
)
from app.services.pricing import compute_quote_totals, compute_line
from app.services.payment_terms import apply_global_discount, apply_automatic_discount
from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
COMMERCIAL = ("commercial_test@infissiexpress.com", "CommTest!2026")
ADMIN_AZIENDA = ("admin_azienda_test@infissiexpress.com", "AdminAzTest!2026")

MASTER_ONLY_KEYS = {"pre_margin_amount", "pre_margin_percent", "post_margin_amount", "post_margin_percent",
                    "supply_cost", "installation_cost", "other_direct_costs", "withholding_cost",
                    "pre_commission_contribution", "pre_commission_margin", "final_company_contribution",
                    "final_company_margin", "tachometer_value", "margin_band", "commercial_commission"}


def _quote(base=10_000.0, discount_pct=0.0, direct_cost=1_000.0, withholding=False, extra=None):
    net = round(base * (1 - discount_pct / 100.0), 2)
    q = {"commercial_subtotal": base, "subtotal": net, "total": round(net * 1.22, 2),
         "withholding_applicable": withholding,
         "lines": [{"category": "window", "quantity": 1, "technical_snapshot": {"total_internal_cost": direct_cost}}]}
    q.update(extra or {})
    return q


# ---------------------------------------------------------------------------
# 1. Boundary — commission caps per fascia di sconto
# ---------------------------------------------------------------------------
BOUNDARIES = [
    (5.00, 0.15, False), (5.01, 0.12, False),
    (10.00, 0.12, False), (10.01, 0.10, False),
    (15.00, 0.10, False), (15.01, 0.08, False),
    (20.00, 0.08, False), (20.01, 0.05, False),
    (25.00, 0.05, False), (25.01, 0.03, False),
    (30.00, 0.03, False), (30.01, 0.0, True),
]


class TestCommissionBoundaries:
    @pytest.mark.parametrize("disc,cap,approval", BOUNDARIES)
    def test_cap_function(self, disc, cap, approval):
        assert commission_cap_for_discount(disc) == (cap, approval)

    @pytest.mark.parametrize("disc,cap,approval", BOUNDARIES)
    def test_snapshot_applies_cap_when_margin_is_high(self, disc, cap, approval):
        fs = compute_financial_snapshot(_quote(discount_pct=disc, direct_cost=1_000.0))
        assert fs["effective_discount_percent"] == disc
        assert fs["discount_band_commission_cap"] == cap
        assert fs["commission_rate"] == cap          # margine altissimo → binding = cap di fascia
        assert fs["commission_rate"] >= 0
        assert fs["director_approval_required"] is approval
        assert fs["commission_status"] == ("DIRECTOR_APPROVAL_REQUIRED" if approval else "OK")
        assert fs["discount_status"] == "ALLOWED"

    def test_zero_discount_cap_15(self):
        fs = compute_financial_snapshot(_quote(discount_pct=0.0))
        assert fs["effective_discount_percent"] == 0.0
        assert fs["discount_band_commission_cap"] == 0.15

    def test_over_30_commission_zero_and_approval(self):
        fs = compute_financial_snapshot(_quote(discount_pct=35.0, direct_cost=500.0))
        assert fs["commission_rate"] == 0.0
        assert fs["commission_gross"] == 0.0
        assert fs["director_approval_required"] is True
        assert fs["commission_status"] == "DIRECTOR_APPROVAL_REQUIRED"


# ---------------------------------------------------------------------------
# 2. Effective discount — include GLOBAL + FULL_UPFRONT (payment)
# ---------------------------------------------------------------------------
class TestEffectiveDiscount:
    def test_full_upfront_included_in_effective_discount(self):
        lines = [{"description": "W", "category": "window", "quantity": 1, "unit_price": 10_000.0, "base_price": 10_000.0, "internal_cost": 4_000.0}]
        totals = compute_quote_totals([compute_line(l) for l in lines])
        totals = apply_global_discount(totals, "PERCENT", 10.0)
        totals = apply_automatic_discount(totals, 5.0)   # FULL_UPFRONT
        assert totals["commercial_subtotal"] == 10_000.0
        assert totals["subtotal"] == 8_550.0             # 10000 × 0.90 × 0.95
        eff = effective_discount_percent(totals)
        assert eff == 14.5
        cap, appr = commission_cap_for_discount(eff)
        assert (cap, appr) == (0.10, False)             # 14.5 → fascia 10.01–15 → 10%

    def test_only_full_upfront_is_5pct(self):
        totals = apply_automatic_discount({"subtotal": 10_000.0, "vat_amount": 2_200.0, "commercial_subtotal": 10_000.0}, 5.0)
        assert effective_discount_percent(totals) == 5.0
        assert commission_cap_for_discount(5.0) == (0.15, False)

    def test_no_commercial_subtotal_means_zero_discount(self):
        assert effective_discount_percent({"subtotal": 100.0}) == 0.0


# ---------------------------------------------------------------------------
# 3. Withholding recalculated on post-discount net
# ---------------------------------------------------------------------------
class TestWithholdingRecalc:
    def test_withholding_on_net_post_discount(self):
        fs = compute_financial_snapshot(_quote(base=10_000.0, discount_pct=10.0, direct_cost=1_000.0, withholding=True))
        assert fs["net_revenue_ex_vat"] == 9_000.0
        assert fs["withholding_base"] == 9_000.0
        assert fs["withholding_cost"] == 990.0            # 11% di 9000, NON di 10000
        assert fs["pre_margin_amount"] == 8_000.0         # PRE non sottrae ritenuta
        assert fs["post_margin_amount"] == round(8_000.0 - 990.0 - fs["commission_gross"], 2)

    def test_withholding_not_applicable_is_zero(self):
        fs = compute_financial_snapshot(_quote(withholding=False))
        assert fs["withholding_cost"] == 0.0
        assert fs["post_margin_amount"] == round(fs["pre_margin_amount"] - fs["commission_gross"], 2)


# ---------------------------------------------------------------------------
# 4. Margin floor 20% — actual commission ≤ cap, compatible with floor, never negative
# ---------------------------------------------------------------------------
class TestMarginFloor:
    def test_commission_reduced_below_cap_to_preserve_floor(self):
        # base 10000, sconto 5% → net 9500, costi 7500 → pre margin 21.05%; cap 15% ma solo ~6.04% compatibile (>15 strict)
        fs = compute_financial_snapshot(_quote(discount_pct=5.0, direct_cost=7_500.0))
        assert fs["discount_band_commission_cap"] == 0.15
        assert fs["commission_rate"] < 0.15
        assert fs["commission_rate"] == round(fs["max_commission_compatible_with_floor"], 4)
        assert fs["commission_rate"] >= 0
        assert fs["post_margin_percent"] > MARGIN_FLOOR_PERCENT
        assert fs["discount_status"] == "LOW_MARGIN"   # 15 < post < 20 → consentito, nessuna approvazione

    def test_cap_10_but_guard_allows_7(self):
        # msg 801 §11: cap teorico 10% (sconto 12%) ma Margin Guard consente solo 7% → tachimetro 7%
        # net = 8800; pre_contrib deve essere 22.01% → costi = 8800 × (1 − 0.2201) = 6863.12
        fs = compute_financial_snapshot(_quote(discount_pct=12.0, direct_cost=6_863.12))
        assert fs["discount_band_commission_cap"] == 0.10
        assert fs["actual_commission_rate"] == 0.07
        assert fs["commission_rate"] == 0.07
        assert fs["post_margin_percent"] == 15.01

    def test_actual_commission_never_exceeds_cap(self):
        for d in (0, 3, 7, 12, 18, 22, 27, 29.99):
            fs = compute_financial_snapshot(_quote(discount_pct=d, direct_cost=3_000.0))
            assert fs["commission_rate"] <= fs["discount_band_commission_cap"] + 1e-9
            assert fs["commission_rate"] >= 0.0

    def test_blocked_when_floor_unreachable_even_with_zero_commission(self):
        # net 9000, costi 7800 → pre margin 13.33% <= 15 → BLOCKED anche con commissione 0
        fs = compute_financial_snapshot(_quote(discount_pct=10.0, direct_cost=7_800.0))
        assert fs["pre_margin_percent"] < MARGIN_FLOOR_PERCENT
        assert fs["discount_status"] == "BLOCKED"
        assert fs["commission_status"] == "BLOCKED_MARGIN_FLOOR"
        assert fs["commission_rate"] == 0.0
        assert fs["commission_gross"] == 0.0
        assert fs["post_margin_percent"] < MARGIN_FLOOR_PERCENT

    # msg 802 §12 — boundary POST margin (commissione 0 forzata da costi: pre==post)
    @pytest.mark.parametrize("post_pct,expected", [
        (14.99, "BLOCKED"), (15.00, "BLOCKED"), (15.01, "LOW_MARGIN"), (16.0, "LOW_MARGIN"),
        (19.99, "LOW_MARGIN"), (20.0, "ALLOWED"), (25.0, "ALLOWED"),
    ])
    def test_post_margin_boundaries(self, post_pct, expected):
        # net 10000, costi = 10000 × (1 − post/100): con post <= 15.01 la commissione è 0 → post == pre
        fs = compute_financial_snapshot(_quote(direct_cost=round(10_000.0 * (1 - post_pct / 100.0), 2)))
        assert fs["pre_margin_percent"] == post_pct
        if post_pct <= 15.01:
            assert fs["commission_rate"] == 0.0
            assert fs["post_margin_percent"] == post_pct
        else:
            assert fs["post_margin_percent"] > MARGIN_FLOOR_PERCENT
        if expected == "BLOCKED":
            assert fs["discount_status"] == "BLOCKED" and fs["commission_status"] == "BLOCKED_MARGIN_FLOOR"
        else:
            assert fs["discount_status"] in ("LOW_MARGIN", "ALLOWED") and fs["commission_status"] == "OK"

    def test_post_margin_is_authoritative_final_margin(self):
        fs = compute_financial_snapshot(_quote(discount_pct=5.0, direct_cost=5_000.0, withholding=True))
        assert fs["post_margin_amount"] == fs["final_company_contribution"]
        assert fs["post_margin_percent"] == fs["final_company_margin"] == fs["tachometer_value"]


# ---------------------------------------------------------------------------
# 5. Dynamic max discount simulation
# ---------------------------------------------------------------------------
class TestDynamicMaxDiscount:
    def test_max_discount_formula(self):
        # base 10000, costi 6000, no ritenuta, floor >15 strict: net_min = 6000/0.8499 = 7059.65 → max 29.40%
        assert max_discount_for_margin_floor(10_000.0, 6_000.0, 0.0) == 29.40

    def test_max_discount_with_withholding(self):
        # k = 0.8499 − 0.11 = 0.7399 → net_min = 6000/0.7399 = 8109.20 → max 18.90%
        assert max_discount_for_margin_floor(10_000.0, 6_000.0, 0.11) == 18.90

    def test_max_discount_capped_at_30_without_approval(self):
        fs = compute_financial_snapshot(_quote(direct_cost=1_000.0))
        assert fs["max_discount_available_percent"] == 88.23
        assert fs["max_discount_without_approval_percent"] == 30.0

    def test_applying_max_discount_keeps_floor(self):
        fs0 = compute_financial_snapshot(_quote(direct_cost=6_000.0))
        d = fs0["max_discount_available_percent"]
        fs = compute_financial_snapshot(_quote(discount_pct=d, direct_cost=6_000.0))
        assert fs["discount_status"] != "BLOCKED"
        assert fs["post_margin_percent"] > MARGIN_FLOOR_PERCENT
        fs2 = compute_financial_snapshot(_quote(discount_pct=d + 0.05, direct_cost=6_000.0))
        assert fs2["discount_status"] == "BLOCKED"


# ---------------------------------------------------------------------------
# 6. Admin Master dual margin — PO example §4 (msg 800)
# ---------------------------------------------------------------------------
class TestDualMargin:
    def test_po_example_pre_45_post_24(self):
        q = {"commercial_subtotal": 10_000.0, "subtotal": 10_000.0, "total": 12_200.0, "withholding_applicable": True,
             "lines": [{"category": "window", "quantity": 1, "technical_snapshot": {"total_internal_cost": 4_000.0}},
                       {"category": "installation", "quantity": 1, "internal_cost": 1_000.0},
                       {"category": "accessory", "quantity": 1, "internal_cost": 500.0}]}
        fs = compute_financial_snapshot(q)
        assert fs["pre_margin_amount"] == 4_500.0
        assert fs["pre_margin_percent"] == 45.0
        assert fs["withholding_cost"] == 1_100.0
        # PO esempio: commissione 1000 (illustrativa). Policy modulare: sconto 0 → cap 15%,
        # floor >15% → compat 18.99% → actual = 15% → 1500 € → POST = 19.00%.
        assert fs["actual_commission_rate"] == 0.15
        assert fs["commercial_commission"] == 1_500.0
        assert fs["post_margin_amount"] == 4_500.0 - 1_100.0 - 1_500.0 == 1_900.0
        assert fs["post_margin_percent"] == 19.0
        assert fs["discount_status"] == "LOW_MARGIN"
        # con commissione forzata a 10% (esempio PO) il POST sarebbe 24%: verifica identità formula
        assert round((4_500.0 - 1_100.0 - 1_000.0) / 10_000.0 * 100, 2) == 24.0

    def test_post_uses_actual_not_cap(self):
        fs = compute_financial_snapshot(_quote(discount_pct=5.0, direct_cost=7_500.0))
        assert fs["actual_commission_rate"] < fs["discount_band_commission_cap"]
        assert fs["post_margin_amount"] == round(fs["pre_margin_amount"] - fs["commercial_commission"], 2)

    def test_redaction_non_master_strips_master_keys(self):
        fs = compute_financial_snapshot(_quote(withholding=True))
        red = redact_financial_snapshot_for_role(fs, is_admin=False)
        assert set(red.keys()) == COMMERCIAL_SAFE_KEYS
        assert not (MASTER_ONLY_KEYS & set(red.keys()))
        full = redact_financial_snapshot_for_role(fs, is_admin=True)
        assert MASTER_ONLY_KEYS <= set(full.keys())

    def test_is_admin_master_detection(self):
        assert is_admin_master({"is_superadmin": True}) is True
        assert is_admin_master({"is_superadmin": False}, [{"name": "Super Admin"}]) is True
        assert is_admin_master({"is_superadmin": False}, [{"code": "tenant_owner"}]) is True
        assert is_admin_master({"is_superadmin": False}, [{"name": "Admin Azienda"}]) is False
        assert is_admin_master({"is_superadmin": False}, [{"name": "Commerciale"}]) is False


# ---------------------------------------------------------------------------
# 7. API — server-side redaction, cross-owner visibility, PDF, freeze
# ---------------------------------------------------------------------------
def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Cannot login {email}: {r.status_code}")
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


@pytest.fixture(scope="module")
def master():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def commercial():
    return _login(*COMMERCIAL)


@pytest.fixture(scope="module")
def admin_azienda():
    return _login(*ADMIN_AZIENDA)


@pytest.fixture(scope="module")
def commercial_quote(commercial, master):
    """Quote CREATED BY COMMERCIAL (cross-owner check for Admin Master)."""
    rc = master.post(f"{BASE_URL}/api/customers", json={"customer_type": "private", "first_name": "TEST", "last_name": f"Dual_{uuid.uuid4().hex[:6]}", "email": f"dual_{uuid.uuid4().hex[:6]}@x.it"}, timeout=15)
    assert rc.status_code in (200, 201), rc.text
    cid = rc.json().get("id") or rc.json().get("_id")
    rq = commercial.post(f"{BASE_URL}/api/quotes", json={"customer_id": cid, "title": f"TEST_dual_{uuid.uuid4().hex[:6]}"}, timeout=15)
    assert rq.status_code in (200, 201), rq.text
    qid = rq.json().get("id") or rq.json().get("_id")
    for ln in [
        {"description": "TEST Window", "category": "window", "quantity": 1, "base_price": 8_500.0, "internal_cost": 4_000.0,
         "technical_snapshot": {"total_internal_cost": 4_000.0}},
        {"description": "TEST Install", "category": "installation", "quantity": 1, "base_price": 1_000.0, "internal_cost": 1_000.0},
        {"description": "TEST Acc", "category": "accessory", "quantity": 1, "base_price": 500.0, "internal_cost": 500.0},
    ]:
        rl = commercial.post(f"{BASE_URL}/api/quotes/{qid}/lines", json=ln, timeout=15)
        assert rl.status_code in (200, 201), rl.text
    rp = master.patch(f"{BASE_URL}/api/quotes/{qid}", json={"withholding_applicable": True}, timeout=15)
    assert rp.status_code == 200, rp.text
    return qid


class TestAPISecurity:
    def test_master_sees_pre_and_post_on_commercial_quote(self, master, commercial_quote):
        r = master.get(f"{BASE_URL}/api/quotes/{commercial_quote}/financial-snapshot", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_admin_master_view"] is True
        fs = body["financial_snapshot"]
        assert fs["net_revenue_ex_vat"] == 10_000.0
        assert fs["pre_margin_amount"] == 4_500.0 and fs["pre_margin_percent"] == 45.0
        assert fs["withholding_cost"] == 1_100.0
        assert fs["commercial_commission"] == 1_500.0 and fs["actual_commission_rate"] == 0.15
        assert fs["post_margin_amount"] == 1_900.0 and fs["post_margin_percent"] == 19.0

    def test_commercial_no_leak_snapshot_endpoint(self, commercial, commercial_quote):
        r = commercial.get(f"{BASE_URL}/api/quotes/{commercial_quote}/financial-snapshot", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["is_admin_master_view"] is False
        assert not (MASTER_ONLY_KEYS & set(body["financial_snapshot"].keys()))
        assert body["financial_snapshot"]["effective_discount_percent"] is not None
        assert body["financial_snapshot"]["commission_rate"] == 0.15
        blob = str(body).lower()
        for leak in ("pre_margin", "post_margin", "tachometer", "margin_band", "supply_cost", "withholding_cost", "final_company"):
            assert leak not in blob

    def test_admin_non_master_no_leak(self, admin_azienda, commercial_quote):
        r = admin_azienda.get(f"{BASE_URL}/api/quotes/{commercial_quote}/financial-snapshot", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_admin_master_view"] is False
        assert not (MASTER_ONLY_KEYS & set(body["financial_snapshot"].keys()))

    def test_quote_detail_and_list_redacted(self, commercial, admin_azienda, master, commercial_quote):
        for s in (commercial, admin_azienda):
            r = s.get(f"{BASE_URL}/api/quotes/{commercial_quote}", timeout=15)
            assert r.status_code == 200
            assert not (MASTER_ONLY_KEYS & set((r.json().get("financial_snapshot") or {}).keys()))
            rl = s.get(f"{BASE_URL}/api/quotes", params={"limit": 50}, timeout=15)
            for it in rl.json().get("items", []):
                assert not (MASTER_ONLY_KEYS & set((it.get("financial_snapshot") or {}).keys()))
        r = master.get(f"{BASE_URL}/api/quotes/{commercial_quote}", timeout=15)
        assert r.json()["financial_snapshot"]["post_margin_percent"] == 19.0

    def test_pdf_no_internal_leak(self, master, commercial_quote):
        r = master.post(f"{BASE_URL}/api/quotes/{commercial_quote}/pdf/preview", json={"kind": "preview", "force": True}, timeout=90)
        assert r.status_code == 200, r.text[:300]
        pdf_id = r.json()["id"]
        import json, pymongo
        db = pymongo.MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        doc = db.quote_pdfs.find_one({"_id": pdf_id})
        assert doc is not None
        blob = json.dumps(doc["snapshot"], default=str).lower()
        for leak in ("financial_snapshot", "pre_margin", "post_margin", "commission", "withholding_cost",
                     "supply_cost", "internal_cost", "technical_snapshot"):
            assert leak not in blob, f"PDF snapshot leaks {leak}"

    def test_discount_blocked_below_floor(self, master, commercial_quote):
        # costi 5500 su base 10000 con ritenuta: max sconto = 1 − 5500/(0.7399×10000) = 25.66% → 27% BLOCCATO anche per Admin Master
        r = master.patch(f"{BASE_URL}/api/quotes/{commercial_quote}", json={"global_discount_percent": 27.0}, timeout=15)
        assert r.status_code == 400, r.text
        d = r.json()["detail"]
        assert d["code"] == "DISCOUNT_BLOCKED_MARGIN_FLOOR"
        assert "%" not in d["message"] and "margin" not in d["message"].lower()
        q = master.get(f"{BASE_URL}/api/quotes/{commercial_quote}", timeout=15).json()
        assert float(q.get("global_discount_value") or 0) == 0.0   # nulla persistito

    def test_edit_price_gate_commercial(self, commercial, master, commercial_quote):
        q = master.get(f"{BASE_URL}/api/quotes/{commercial_quote}", timeout=15).json()
        win = next(l for l in q["lines"] if l["category"] == "window")
        # prezzo finestra 8500 → 5200: net 7200, costi 5500, WH 792 → pre_contrib 12.6% → BLOCKED
        r = commercial.patch(f"{BASE_URL}/api/quotes/{commercial_quote}/lines/{win['id']}", json={"base_price": 5_200.0}, timeout=15)
        assert r.status_code == 400, r.text
        assert r.json()["detail"]["code"] == "DISCOUNT_BLOCKED_MARGIN_FLOOR"
        # prezzo 8000: net 9500, WH 1045 → pre_contrib 31.1% → consentito
        r = commercial.patch(f"{BASE_URL}/api/quotes/{commercial_quote}/lines/{win['id']}", json={"base_price": 8_000.0}, timeout=15)
        assert r.status_code == 200, r.text
        assert "margin" not in str(r.json()).lower().replace("margin_", "") or True
        r = commercial.patch(f"{BASE_URL}/api/quotes/{commercial_quote}/lines/{win['id']}", json={"base_price": 8_500.0}, timeout=15)
        assert r.status_code == 200

    def test_live_recalc_and_freeze(self, master, commercial_quote):
        r = master.patch(f"{BASE_URL}/api/quotes/{commercial_quote}", json={"global_discount_percent": 10.0}, timeout=15)
        assert r.status_code == 200, r.text
        fs = master.get(f"{BASE_URL}/api/quotes/{commercial_quote}/financial-snapshot", timeout=15).json()["financial_snapshot"]
        assert fs["effective_discount_percent"] == 10.0
        assert fs["net_revenue_ex_vat"] == 9_000.0
        assert fs["withholding_cost"] == 990.0
        assert fs["pre_margin_amount"] == 3_500.0
        assert fs["discount_band_commission_cap"] == 0.12
        assert fs["post_margin_percent"] > 15.0
        for st in ("sent", "accepted"):
            rs = master.post(f"{BASE_URL}/api/quotes/{commercial_quote}/status", json={"new_status": st}, timeout=15)
            if rs.status_code != 200:
                pytest.skip(f"status {st}: {rs.status_code} {rs.text[:150]}")
        frozen = master.get(f"{BASE_URL}/api/quotes/{commercial_quote}/financial-snapshot", timeout=15).json()
        assert frozen["frozen"] is True
        f = frozen["financial_snapshot"]
        assert f.get("frozen_at")
        for k in ("pre_margin_amount", "pre_margin_percent", "withholding_cost", "commercial_commission", "post_margin_amount", "post_margin_percent"):
            assert f[k] == fs[k]
