"""PO patch — TRASPORTO AL PIANO / GRU: prezzo cliente scontabile/azzerabile, costo interno invariato, margine finale, floor, audit, RBAC."""
from __future__ import annotations

import uuid

import pytest

from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD
from tests.test_quote_economic_control_v2 import _login, _quote, _get, _line, BASE


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def comm():
    return _login("commercial_test@infissiexpress.com", "CommTest!2026")


def _logistics(s, qid):
    return s.get(f"{BASE}/quotes/{qid}/logistics", timeout=15).json()


def _price(s, qid, code, price, reason=None):
    return s.patch(f"{BASE}/quotes/{qid}/logistics/{code}/price", json={"customer_price": price, "reason": reason}, timeout=15)


def _snap(s, qid):
    return s.get(f"{BASE}/quotes/{qid}/financial-snapshot", timeout=15).json()["financial_snapshot"]


def _cost(fs):
    return round(float(fs.get("supply_cost") or 0) + float(fs.get("installation_cost") or 0) + float(fs.get("other_direct_costs") or 0), 2)


def _site(admin, floor):
    tag = uuid.uuid4().hex[:6]
    cust = admin.post(f"{BASE}/customers", json={"customer_type": "private", "first_name": "Logi", "last_name": f"P{tag}", "email": f"logi_{tag}@x.it", "phone": "3331234567",
                                                 "tax_code": "RSSMRA80A01H501U", "address": {"street": "Via Roma 1", "city": "Milano", "zip_code": "20100", "province": "MI"}}, timeout=15).json()["id"]
    r = admin.post(f"{BASE}/sites", json={"customer_id": cust, "name": f"Cantiere test piano {floor}", "address": "Via Test", "street_number": "1", "postal_code": "20100", "city": "Milano", "province": "MI",
                                         "floor": str(floor), "has_elevator": False, "property_type": "APPARTAMENTO", "site_contact_phone": "+39 333 0000000", "site_contact_name": "Test"}, timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"], cust


class TestCatalogAndAuto:
    def test_catalog_800_500_1700_1400(self, admin):
        qid = _quote(admin, [_line("P", "window", 10000, 4000)])
        cat = {c["code"]: c for c in _logistics(admin, qid)["catalog"]}
        assert cat["FLOOR_HANDLING"]["standard_price"] == 800 and cat["FLOOR_HANDLING"]["internal_cost"] == 500
        assert cat["CRANE"]["standard_price"] == 1700 and cat["CRANE"]["internal_cost"] == 1400
        assert cat["SITE_TRANSPORT"]["pricing_status"] == "PRICING_RULE_TO_DEFINE"
        r = admin.post(f"{BASE}/quotes/{qid}/logistics", json={"code": "SITE_TRANSPORT"}, timeout=15)
        assert r.status_code == 400 and r.json()["detail"]["code"] == "PRICING_RULE_TO_DEFINE"  # nessun prezzo inventato

    def test_floor_handling_auto_on_floor_3(self, admin):
        site_id, cust = _site(admin, 3)
        q = admin.post(f"{BASE}/quotes", json={"customer_id": cust, "site_id": site_id, "title": "Logistica piano 3"}, timeout=15)
        assert q.status_code in (200, 201), q.text
        qid = q.json()["id"]
        assert admin.post(f"{BASE}/quotes/{qid}/lines", json=_line("P", "window", 10000, 4000), timeout=15).status_code in (200, 201)
        items = {i["code"]: i for i in _logistics(admin, qid)["items"]}
        assert items["FLOOR_HANDLING"]["auto"] and items["FLOOR_HANDLING"]["required"] and items["FLOOR_HANDLING"]["customer_price"] == 800
        q = _get(admin, qid)
        assert q["subtotal"] == 10800 and q["total"] == round(10800 * 1.22, 2)
        r = admin.delete(f"{BASE}/quotes/{qid}/logistics/FLOOR_HANDLING", timeout=15)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "SERVICE_REQUIRED"  # resta in commessa


class TestDiscountZeroMargin:
    def test_floor_handling_discount_and_zero_internal_cost_preserved(self, admin):
        qid = _quote(admin, [_line("P", "window", 10000, 4000)])
        assert admin.post(f"{BASE}/quotes/{qid}/logistics", json={"code": "FLOOR_HANDLING"}, timeout=15).status_code == 200
        fs0 = _snap(admin, qid)
        assert _cost(fs0) == 4500 and _get(admin, qid)["subtotal"] == 10800
        assert _price(admin, qid, "FLOOR_HANDLING", 600).status_code == 200
        q = _get(admin, qid); fs = _snap(admin, qid)
        assert q["subtotal"] == 10600 and _cost(fs) == 4500  # costo invariato, contribuzione +100
        r = _price(admin, qid, "FLOOR_HANDLING", 0)
        assert r.status_code == 400 and r.json()["detail"]["code"] == "ZERO_REASON_REQUIRED"
        r = _price(admin, qid, "FLOOR_HANDLING", 0, "omaggio commerciale")
        assert r.status_code == 200
        item = next(i for i in r.json()["items"] if i["code"] == "FLOOR_HANDLING")
        assert item["is_free"] and item["internal_cost"] == 500 and item["price_history"][-1]["reason"] == "omaggio commerciale" and item["price_history"][-1]["user_email"]
        q = _get(admin, qid); fs = _snap(admin, qid)
        assert q["subtotal"] == 10000 and _cost(fs) == 4500  # ricavo 0, costo commessa 500 → contribuzione −500
        assert fs["post_margin_percent"] < fs0["post_margin_percent"]
        assert len(q["logistics_services"]) == 1  # servizio azzerato NON rimosso
        assert _price(admin, qid, "FLOOR_HANDLING", 900).status_code == 400

    def test_crane_discount_zero(self, admin):
        qid = _quote(admin, [_line("P", "window", 10000, 4000)])
        admin.post(f"{BASE}/quotes/{qid}/logistics", json={"code": "CRANE"}, timeout=15)
        assert _get(admin, qid)["subtotal"] == 11700 and _cost(_snap(admin, qid)) == 5400
        assert _price(admin, qid, "CRANE", 1200).status_code == 200 and _get(admin, qid)["subtotal"] == 11200
        assert _price(admin, qid, "CRANE", 0, "trattativa cliente").status_code == 200
        assert _get(admin, qid)["subtotal"] == 10000 and _cost(_snap(admin, qid)) == 5400

    def test_margin_floor_gate_blocks_zero(self, admin):
        # ricavo 2000 costo 1600 (margine 20%) + GRU 1700/1400: azzerare la gru porta il margine sotto il 15% → BLOCCATO (anche admin)
        qid = _quote(admin, [_line("P", "window", 2000, 1600)])
        admin.post(f"{BASE}/quotes/{qid}/logistics", json={"code": "CRANE"}, timeout=15)
        r = _price(admin, qid, "CRANE", 0, "autorizzazione direzione")
        assert r.status_code == 400 and r.json()["detail"]["code"] == "DISCOUNT_BLOCKED_MARGIN_FLOOR"
        assert _get(admin, qid)["subtotal"] == 3700  # nessun salvataggio

    def test_no_double_discount_with_global(self, admin):
        qid = _quote(admin, [_line("P", "window", 10000, 4000)])
        admin.post(f"{BASE}/quotes/{qid}/logistics", json={"code": "FLOOR_HANDLING"}, timeout=15)
        _price(admin, qid, "FLOOR_HANDLING", 600)
        admin.patch(f"{BASE}/quotes/{qid}", json={"global_discount_percent": 10}, timeout=15)
        q = _get(admin, qid)
        assert q["global_discount_amount"] == 1000 and q["subtotal"] == 9600  # 10% solo su 10000, non sui 600 già scontati a riga


class TestRbacAndPdf:
    def test_commercial_no_internal_cost(self, admin, comm):
        qid = _quote(admin, [_line("P", "window", 10000, 4000)])
        admin.post(f"{BASE}/quotes/{qid}/logistics", json={"code": "CRANE"}, timeout=15)
        v = _logistics(comm, qid)
        assert v["is_admin_view"] is False and all("internal_cost" not in i for i in v["items"]) and all("internal_cost" not in c for c in v["catalog"])
        assert _price(comm, qid, "CRANE", 1200).status_code == 200  # commerciale può scontare il prezzo cliente

    def test_pdf_shows_omaggio_without_internal_cost(self, admin):
        qid = _quote(admin, [_line("P", "window", 10000, 4000)])
        admin.post(f"{BASE}/quotes/{qid}/logistics", json={"code": "FLOOR_HANDLING"}, timeout=15)
        _price(admin, qid, "FLOOR_HANDLING", 0, "omaggio commerciale")
        g = admin.post(f"{BASE}/quotes/{qid}/pdf/generate", json={"force": True}, timeout=60)
        if g.status_code == 503:
            pytest.skip("PDF engine non disponibile")
        assert g.status_code == 200, g.text
        from app.services.pdf_renderer import _env
        import asyncio, os, re
        from motor.motor_asyncio import AsyncIOMotorClient
        async def html():
            db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
            pdf = await db.quote_pdfs.find_one({"quote_id": qid}, sort=[("generated_at", -1)])
            snap = pdf["snapshot"]
            return re.sub(r"<[^>]+>", " ", _env.get_template("quote_pdf.html").render(snap=snap, q=snap.get("quote") or snap, **{k: v for k, v in snap.items() if k != "quote"}))
        txt = asyncio.run(html())
        assert "OMAGGIO" in txt and "TRASPORTO AL PIANO" in txt and "500" not in txt.split("Riepilogo economico")[-1][:400]
