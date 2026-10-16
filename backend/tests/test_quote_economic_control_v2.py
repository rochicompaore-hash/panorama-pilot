"""QUOTE ECONOMIC CONTROL V2 — IVA breakdown/eligibility, admin discount authority, competitor analyzer (golden)."""
from __future__ import annotations

import os
import uuid

import pytest
import requests

from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"


def _login(e, p):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": e, "password": p}, timeout=15); assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def comm():
    return _login("commercial_test@infissiexpress.com", "CommTest!2026")


def _quote(admin, lines):
    tag = uuid.uuid4().hex[:6]
    c = admin.post(f"{BASE}/customers", json={"customer_type": "private", "first_name": "Econ", "last_name": f"V2{tag}", "email": f"econ_{tag}@x.it", "phone": "3331234567",
                                            "tax_code": "RSSMRA80A01H501U", "address": {"street": "Via Roma 1", "city": "Milano", "zip_code": "20100", "province": "MI"}}, timeout=15).json()
    q = admin.post(f"{BASE}/quotes", json={"customer_id": c["id"], "title": f"ECON V2 {tag}", "site_address": {"street": "Via C 1", "city": "Monza", "zip_code": "20900", "province": "MB"}}, timeout=15).json()
    for ln in lines:
        r = admin.post(f"{BASE}/quotes/{q['id']}/lines", json=ln, timeout=15); assert r.status_code in (200, 201), r.text
    return q["id"]


def _get(s, qid):
    return s.get(f"{BASE}/quotes/{qid}", timeout=15).json()


def _line(desc, cat, price, cost, qty=1):
    return {"description": desc, "category": cat, "quantity": qty, "base_price": price, "internal_cost": cost, "technical_snapshot": {"total_internal_cost": cost * qty}}


VALID_DOSSIER = {"vat_reason": "RISTRUTTURAZIONE_ABITAZIONE", "customer_declaration": True, "documentation_status": "COMPLETE", "vat_eligibility_status": "VALIDATED"}


class TestVAT:
    def test_22_default(self, admin):
        qid = _quote(admin, [_line("Prodotto", "window", 10000, 4000)])
        q = _get(admin, qid)
        assert q["vat_regime_applied"] == "VAT_ORDINARY" and q["vat_amount"] == 2200 and q["total"] == 12200
        assert q["vat_breakdown"] == [{"rate": 0.22, "rate_pct": 22, "taxable": 10000.0, "tax": 2200.0}]

    @pytest.mark.parametrize("regime,vat,total", [("VAT_ELIGIBLE_10", 1000, 11000), ("VAT_ELIGIBLE_4", 400, 10400)])
    def test_reduced_only_with_validated_dossier(self, admin, regime, vat, total):
        qid = _quote(admin, [_line("Prodotto", "window", 10000, 4000)])
        # richiesta senza documentazione → DOCUMENTATION_INCOMPLETE, resta 22%
        r = admin.patch(f"{BASE}/quotes/{qid}/fiscal-dossier", json={"requested_regime": regime}, timeout=15)
        assert r.status_code == 200 and r.json()["vat_regime"] == "VAT_DOCUMENTATION_INCOMPLETE" and r.json()["vat_amount"] == 2200
        # documentazione completa ma non validata → REVIEW_REQUIRED, resta 22%
        r = admin.patch(f"{BASE}/quotes/{qid}/fiscal-dossier", json={"customer_declaration": True, "documentation_status": "COMPLETE"}, timeout=15)
        assert r.json()["vat_regime"] == "VAT_REVIEW_REQUIRED" and r.json()["vat_amount"] == 2200
        # validazione (permesso fiscale) → agevolata; tax_deduction_requested resta FALSE (test A: IVA indipendente dalla detrazione)
        r = admin.patch(f"{BASE}/quotes/{qid}/fiscal-dossier", json={"vat_eligibility_status": "VALIDATED"}, timeout=15)
        assert r.json()["vat_regime"] == regime and r.json()["vat_amount"] == vat and r.json()["total"] == total
        q = _get(admin, qid); assert not q.get("tax_deduction_requested") and q["total"] == total  # save/reload

    def test_mixed_10_22(self, admin):
        qid = _quote(admin, [_line("Posa", "installation", 8000, 3000), _line("Finestra", "window", 2000, 800)])
        r = admin.patch(f"{BASE}/quotes/{qid}/fiscal-dossier", json={"requested_regime": "VAT_MIXED_10_22", **VALID_DOSSIER}, timeout=15)
        assert r.status_code == 200, r.text
        bd = {b["rate_pct"]: b for b in r.json()["vat_breakdown"]}
        assert bd[10]["taxable"] == 8000 and bd[10]["tax"] == 800 and bd[22]["taxable"] == 2000 and bd[22]["tax"] == 440
        assert r.json()["vat_amount"] == 1240 and r.json()["total"] == 11240
        pdf = admin.post(f"{BASE}/quotes/{qid}/pdf/preview", json={}, timeout=60)
        assert pdf.status_code in (200, 503)  # 503 solo se engine PDF non disponibile (deploy senza pango)

    def test_ecobonus_does_not_enable_reduced_vat(self, admin):
        qid = _quote(admin, [_line("Prodotto", "window", 10000, 4000)])
        admin.patch(f"{BASE}/quotes/{qid}", json={"tax_deduction_requested": True, "enea_practice_code": "ENEA_STANDARD"}, timeout=15)
        q = _get(admin, qid)
        assert q["vat_regime_applied"] == "VAT_ORDINARY" and all(b["rate"] == 0.22 for b in q["vat_breakdown"])

    def test_commercial_cannot_validate(self, admin, comm):
        qid = _quote(admin, [_line("Prodotto", "window", 10000, 4000)])
        r = comm.patch(f"{BASE}/quotes/{qid}/fiscal-dossier", json={"requested_regime": "VAT_ELIGIBLE_10", "vat_eligibility_status": "VALIDATED"}, timeout=15)
        assert r.status_code == 403


class TestDiscountAuthority:
    def test_admin_dynamic_cap_and_floor(self, admin, comm):
        # ricavo 10000, costo 4000 → max sostenibile ≈ 52.9% → admin step min(40, 52) = 40 (tetto rigido PO); commerciale cap 30
        qid = _quote(admin, [_line("Prodotto", "window", 10000, 4000)])
        fa = admin.get(f"{BASE}/quotes/{qid}/financial-snapshot", timeout=15).json()
        assert fa["can_override_discount_cap"] is True and fa["financial_snapshot"]["max_admin_discount_step_percent"] == 40
        fc = comm.get(f"{BASE}/quotes/{qid}/financial-snapshot", timeout=15).json()
        assert fc["can_override_discount_cap"] is False and "max_admin_discount_step_percent" not in fc["financial_snapshot"]
        assert comm.patch(f"{BASE}/quotes/{qid}", json={"global_discount_percent": 34}, timeout=15).status_code == 403
        assert admin.patch(f"{BASE}/quotes/{qid}", json={"global_discount_percent": 34}, timeout=15).status_code == 200
        r = admin.patch(f"{BASE}/quotes/{qid}", json={"global_discount_percent": 41}, timeout=15)  # oltre tetto 40% → bloccato anche per admin
        assert r.status_code == 403 and r.json()["detail"]["code"] == "ADMIN_DISCOUNT_CAP_EXCEEDED"


class TestCompetitor:
    def _sim(self, s, qid, price, **kw):
        r = s.post(f"{BASE}/quotes/{qid}/competitor/simulate", json={"competitor_price": price, "vat_included": "NO", "competitor_vat_rate": "22", **kw}, timeout=20)
        assert r.status_code == 200, r.text
        return r.json()

    def test_golden_1_2_3(self, admin):
        qid = _quote(admin, [_line("Prodotto", "window", 10000, 4000)])
        s1 = self._sim(admin, qid, 9500)
        assert s1["required_effective_discount_percent"] == 5 and s1["feasible"] is True and s1["authority"] == "COMMERCIAL_AUTHORIZED"
        s2 = self._sim(admin, qid, 8900)
        assert s2["required_effective_discount_percent"] == 11 and s2["feasible"] is True
        qid3 = _quote(admin, [_line("Prodotto", "window", 10000, 7000)])  # max sostenibile 17.63% → min 8237
        s3 = self._sim(admin, qid3, 6000)
        assert s3["feasible"] is False and s3["authority"] == "BLOCKED" and s3["minimum_sustainable_net_price"] == 8237.0
        assert s3["uncoverable_gap_eur"] == 2237.0 and s3["minimum_sustainable_gross_price"] == round(8237.0 * 1.22, 2)

    def test_exact_price_8735_not_rounded(self, admin):
        qid = _quote(admin, [_line("Prodotto", "window", 10000, 4000)])
        s = self._sim(admin, qid, 8735)
        assert s["target_net"] == 8735 and s["required_effective_discount_percent"] == 12.65
        saved = admin.post(f"{BASE}/quotes/{qid}/competitor", json={"competitor_price": 8735, "vat_included": "NO", "competitor_vat_rate": "22", "competitor_name": "Concorrente X"}, timeout=20).json()
        r = admin.post(f"{BASE}/quotes/{qid}/competitor/{saved['id']}/apply", timeout=20)
        assert r.status_code == 200 and r.json()["subtotal"] == 8735.0, r.text
        q = _get(admin, qid)
        assert q["subtotal"] == 8735.0 and q["global_discount_source"] == "NEGOTIATED_TARGET" and q["lines"][0]["base_price"] == 10000
        assert q["total"] == round(8735 * 1.22, 2)
        items = admin.get(f"{BASE}/quotes/{qid}/competitor", timeout=15).json()["items"]
        assert items[0]["decision"] == "TARGET_APPLIED"

    def test_golden_4_5_authority(self, admin, comm):
        qid = _quote(admin, [_line("Prodotto", "window", 10000, 4000)])
        # 34% sostenibile (max 52) → commerciale APPROVAL, admin autorizzato
        sc = self._sim(comm, qid, 6600); assert sc["authority"] == "ADMIN_APPROVAL_REQUIRED" and sc["feasible"] is True
        assert "supply_cost" not in sc["simulated_snapshot"] and "post_margin_percent" not in sc["simulated_snapshot"]
        saved = comm.post(f"{BASE}/quotes/{qid}/competitor", json={"competitor_price": 6600, "vat_included": "NO", "competitor_vat_rate": "22"}, timeout=20).json()
        assert comm.post(f"{BASE}/quotes/{qid}/competitor/{saved['id']}/apply", timeout=20).status_code == 403
        sa = self._sim(admin, qid, 6600); assert sa["authority"] == "ADMIN_AUTHORIZED" and "post_margin_percent" in sa["simulated_snapshot"]
        assert admin.post(f"{BASE}/quotes/{qid}/competitor/{saved['id']}/apply", timeout=20).status_code == 200
        # TEST 5: sotto floor → BLOCK per tutti
        qid2 = _quote(admin, [_line("Prodotto", "window", 10000, 7000)])
        s5 = self._sim(admin, qid2, 6600); assert s5["authority"] == "BLOCKED"
        saved2 = admin.post(f"{BASE}/quotes/{qid2}/competitor", json={"competitor_price": 6600, "vat_included": "NO", "competitor_vat_rate": "22"}, timeout=20).json()
        assert admin.post(f"{BASE}/quotes/{qid2}/competitor/{saved2['id']}/apply", timeout=20).status_code == 400

    def test_vat_unknown_not_invented(self, admin):
        qid = _quote(admin, [_line("Prodotto", "window", 10000, 4000)])
        r = admin.post(f"{BASE}/quotes/{qid}/competitor/simulate", json={"competitor_price": 9000, "vat_included": "UNKNOWN"}, timeout=20).json()
        assert r["vat_comparability"] == "UNKNOWN" and r["competitor_net"] is None and r["competitor_gross"] is None and r["feasible"] is None
        g = admin.post(f"{BASE}/quotes/{qid}/competitor/simulate", json={"competitor_price": 9000, "vat_included": "YES"}, timeout=20).json()
        assert g["vat_comparability"] == "GROSS_ONLY" and g["competitor_net"] is None and g["gross_difference_eur"] == round(12200 - 9000, 2)

    def test_scope_partial(self, admin):
        qid = _quote(admin, [_line("Finestra", "window", 10000, 4000)])
        admin.patch(f"{BASE}/quotes/{qid}", json={"installation_mode": "SUPPLY_AND_INSTALLATION", "dismantling_mode": "INCLUDED"}, timeout=15)
        s = self._sim(admin, qid, 9000, competitor_scope={"products": True, "installation": True, "dismantling": False})
        assert s["scope_comparability"]["status"] == "PARTIAL"
        assert self._sim(admin, qid, 9000)["scope_comparability"]["status"] == "UNKNOWN"
