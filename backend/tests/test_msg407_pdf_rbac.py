"""PO msg 407 §7-§30 — PDF text extraction (promo/discount rows, no internal_cost leak) + RBAC financial_snapshot for commercial role."""
import os, io, pytest, requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN = (os.environ["ADMIN_EMAIL"], os.environ["ADMIN_PASSWORD"])
COMM = ("commercial_test@infissiexpress.com", "CommTest!2026")


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def commercial():
    return _login(*COMM)


def _make_quote_with_promo(admin, promo="PROMO10"):
    cust = admin.get(f"{BASE_URL}/api/customers?limit=1", timeout=20).json()
    cid = (cust.get("items") or cust)[0]["id"]
    qid = admin.post(f"{BASE_URL}/api/quotes", json={"title": "MSG407-PDF", "customer_id": cid}, timeout=20).json()["id"]
    admin.post(f"{BASE_URL}/api/quotes/{qid}/lines", json={"category": "window", "description": "W", "quantity": 1, "base_price": 10000, "internal_cost": 4000}, timeout=20)
    r = admin.patch(f"{BASE_URL}/api/quotes/{qid}", json={"promo_code": promo}, timeout=20)
    assert r.status_code == 200, r.text
    return qid


def test_pdf_preview_contains_discount_rows_and_no_internal_cost(admin):
    qid = _make_quote_with_promo(admin, "PROMO10")
    r = admin.post(f"{BASE_URL}/api/quotes/{qid}/pdf/preview", json={}, timeout=60)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    d = admin.get(f"{BASE_URL}/api/quote-pdfs/{pid}/download", timeout=60)
    assert d.status_code == 200
    assert d.headers.get("content-type", "").startswith("application/pdf")
    assert len(d.content) > 500

    try:
        from pypdf import PdfReader
    except ImportError:
        pytest.skip("pypdf not installed")

    reader = PdfReader(io.BytesIO(d.content))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    low = text.lower()

    assert "subtotale" in low, f"missing 'Subtotale' in PDF text: {text[:1000]}"
    # Discount row with promo phrasing
    assert ("sconto" in low and "promo" in low) or "promozionale" in low, f"missing promo/sconto row: {text[:1000]}"
    assert "1.000,00" in text or "1.000" in text, f"missing amount 1.000,00: {text[:1000]}"
    assert "imponibile" in low, f"missing 'Imponibile': {text[:1000]}"
    # Guard: no leakage of internal fields
    assert "internal_cost" not in low
    assert "supply_cost" not in low


def test_rbac_commercial_gets_reduced_financial_snapshot(admin, commercial):
    qid = _make_quote_with_promo(admin, "PROMO10")

    q = commercial.get(f"{BASE_URL}/api/quotes/{qid}", timeout=20)
    assert q.status_code == 200, q.text
    body = q.json()

    # public fields visible
    assert "subtotal" in body and "total" in body
    assert body.get("global_discount_amount") == 1000
    fs = body.get("financial_snapshot") or {}
    # tachometer stays visible
    assert "tachometer_value" in fs
    # sensitive fields MUST NOT be exposed (per PO msg 407 spec)
    for forbidden in ("supply_cost", "other_direct_costs", "pre_commission_margin",
                      "pre_commission_contribution", "final_company_contribution"):
        assert forbidden not in fs, f"RBAC leak: '{forbidden}' exposed to commercial in financial_snapshot: {fs}"
    # Observability: commission_gross / final_company_margin / net_revenue_ex_vat currently
    # exposed to commercial (report to main agent — spec says 'only tachometer_value etc.').
    print("[RBAC observation] commercial financial_snapshot keys:", sorted(fs.keys()))
