"""PO directive IVA SELEZIONABILE + TEMPI DI CONSEGNA — backend tests."""
from __future__ import annotations

import pytest

from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD
from tests.test_quote_economic_control_v2 import _login, _quote, _get, _line, VALID_DOSSIER, BASE
from app.services.delivery_lead_time import color_delivery_class, compute_quote_lead_time

WINDOW_PID = "8e1cafd0-9707-47c7-8939-b97c9a404021"


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


def _window_line(ci, ce, mode="BICOLOR"):
    return {"description": f"Finestra {ci}/{ce}", "category": "window", "quantity": 1, "product_id": WINDOW_PID, "pricing_model": "FORMULA_TECHNICAL",
            "configuration_snapshot": {"product_key": "PROEVOLUTION", "window_type": "WINDOW", "number_of_sashes": 2, "width_mm": 1200, "height_mm": 1400,
                                       "glass_type": "DOUBLE_STANDARD", "color_internal": ci, "color_internal_name": f"C{ci}", "color_external": ce, "color_external_name": f"C{ce}", "color_mode": mode}}


def _vat(s, qid, regime, **extra):
    return s.patch(f"{BASE}/quotes/{qid}/fiscal-dossier", json={"requested_regime": regime, **extra}, timeout=15)


class TestVatSelector:
    def test_options_and_default_22(self, admin):
        o = admin.get(f"{BASE}/quotes/vat-options", timeout=15).json()
        assert [x["value"] for x in o["options"]] == ["VAT_ORDINARY", "VAT_ELIGIBLE_10", "VAT_ELIGIBLE_4", "VAT_MIXED_10_22", "VAT_REVIEW_REQUIRED"]
        qid = _quote(admin, [_line("P", "window", 10000, 4000)])
        q = _get(admin, qid)
        assert q["vat_regime"] == "VAT_ORDINARY" and q["vat_amount"] == 2200 and q["total"] == 12200

    @pytest.mark.parametrize("regime,vat,total", [("VAT_ELIGIBLE_10", 1000, 11000), ("VAT_ELIGIBLE_4", 400, 10400)])
    def test_reduced_requires_dossier_then_applies(self, admin, regime, vat, total):
        qid = _quote(admin, [_line("P", "window", 10000, 4000)])
        r = _vat(admin, qid, regime)  # senza requisiti → documentazione da completare, resta 22%
        assert r.status_code == 200 and r.json()["vat_regime"] == "VAT_DOCUMENTATION_INCOMPLETE"
        q = _get(admin, qid)
        assert q["vat_amount"] == 2200 and q["fiscal_dossier"]["vat_eligibility_status"] == "PENDING"
        assert _vat(admin, qid, regime, **VALID_DOSSIER).status_code == 200
        q = _get(admin, qid)
        assert q["vat_regime"] == regime and q["vat_amount"] == vat and q["total"] == total

    def test_review_required_option(self, admin):
        qid = _quote(admin, [_line("P", "window", 10000, 4000)])
        assert _vat(admin, qid, "VAT_REVIEW_REQUIRED").json()["vat_regime"] == "VAT_REVIEW_REQUIRED"
        q = _get(admin, qid)
        assert q["vat_amount"] == 2200

    def test_mixed_after_discount_and_contract_parity(self, admin):
        qid = _quote(admin, [_line("Prodotto", "window", 8000, 3000), _line("Posa", "installation", 2000, 800)])
        assert _vat(admin, qid, "VAT_MIXED_10_22", **VALID_DOSSIER).status_code == 200
        assert admin.patch(f"{BASE}/quotes/{qid}", json={"global_discount_percent": 20}, timeout=15).status_code == 200
        q = _get(admin, qid)
        bd = {b["rate_pct"]: b for b in q["vat_breakdown"]}
        assert q["subtotal"] == 8000 and bd[10]["taxable"] == 1600 and bd[22]["taxable"] == 6400 and q["vat_amount"] == 1568
        from app.services.contracts_helpers import build_economic_snapshot
        eco = build_economic_snapshot(q)
        assert eco["vat_mode"] == "VAT_MIXED_10_22" and eco["fiscal_validation_status"] == "VALIDATED" and eco["vat_amount"] == 1568
        assert eco["vat_regime"]["code"] == "MISTA 10/22"


class TestDeliveryLeadTime:
    @pytest.mark.parametrize("code,cls", [("003", "STANDARD_60"), ("100", "STANDARD_60"), ("154", "STANDARD_60"), ("110", "STANDARD_60"),
                                          ("048", "STANDARD_90"), ("096", "STANDARD_90"), ("964", "STANDARD_90"), ("RAL7016", "STANDARD_90")])
    def test_class_by_code(self, code, cls):
        assert color_delivery_class(code) == cls

    def _spec_line(self, ci, ce):
        return {"id": f"{ci}-{ce}", "visual_spec": {"spec": {"product_type": "WINDOW", "interior_color_code": ci, "exterior_color_code": ce}}}

    @pytest.mark.parametrize("ci,ce,days", [("003", "003", 60), ("154", "154", 60), ("110", "110", 60), ("100", "100", 60), ("003", "154", 60),
                                            ("003", "110", 60), ("003", "048", 90), ("154", "145", 90), ("964", "964", 90)])
    def test_bicolor_max_rule(self, ci, ce, days):
        assert compute_quote_lead_time([self._spec_line(ci, ce)])["delivery_lead_time_days"] == days

    def test_order_max_lead_time(self):
        lt = compute_quote_lead_time([self._spec_line("003", "003")] * 5 + [self._spec_line("003", "048")])
        assert lt["delivery_lead_time_days"] == 90 and lt["delivery_lead_time_mixed"] is True
        assert "lead time maggiore" in lt["delivery_customer_text"]
        assert compute_quote_lead_time([{"id": "svc", "category": "installation"}])["delivery_lead_time_days"] is None

    def test_quote_e2e_lead_time(self, admin):
        qid = _quote(admin, [_window_line("003", "003", "WHITE_MASS")])
        q = _get(admin, qid)
        assert q["lines"][0].get("visual_spec"), "visual_spec mancante: configurazione non prezzata"
        assert q["delivery_lead_time_days"] == 60 and "entro 60 giorni" in q["delivery_customer_text"].lower()
        r = admin.post(f"{BASE}/quotes/{qid}/lines", json=_window_line("003", "048"), timeout=20)
        assert r.status_code in (200, 201), r.text
        q = _get(admin, qid)
        assert q["delivery_lead_time_days"] == 90 and q["delivery_lead_time_mixed"] is True

    def test_catalog_delivery_class(self, admin):
        cols = admin.get(f"{BASE}/product-colors", timeout=15).json()
        items = cols if isinstance(cols, list) else cols.get("items", [])
        by = {c["code"]: c.get("delivery_class") for c in items}
        assert by.get("003") == "STANDARD_60" and by.get("154") == "STANDARD_60" and by.get("048") == "STANDARD_90"
