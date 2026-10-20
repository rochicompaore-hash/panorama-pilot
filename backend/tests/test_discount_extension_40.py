"""PO ESTENSIONE SCONTI PREVENTIVATORE >30% — matrice test §13 (range 0–40, commerciale 31–40 SAVABLE+APPROVAL, admin diretto, hard cap 40, floor 15%, IVA e commissione ricalcolate, audit trail)."""
from __future__ import annotations

import pytest

from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD
from tests.test_fase_a_preventivatore import BASE_URL, _login, _mk_quote, _fs, WINDOW

COMM_EMAIL, COMM_PASSWORD = "commercial_test@infissiexpress.com", "CommTest!2026"
LOW_MARGIN_LINE = {**WINDOW, "base_price": 1000.0, "internal_cost": 780.0, "technical_snapshot": {"total_internal_cost": 780.0}}


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def commercial():
    return _login(COMM_EMAIL, COMM_PASSWORD)


@pytest.fixture()
def qid(admin):
    return _mk_quote(admin, [WINDOW])


def _patch(sess, qid, pct, reason=None):
    body = {"global_discount_percent": pct}
    if reason:
        body["discount_reason"] = reason
    return sess.patch(f"{BASE_URL}/api/quotes/{qid}", json=body, timeout=15)


def _get(sess, qid):
    return sess.get(f"{BASE_URL}/api/quotes/{qid}", timeout=15).json()


@pytest.mark.parametrize("pct", [29, 30])
def test_commercial_up_to_30_pass(commercial, qid, pct):
    r = _patch(commercial, qid, pct)
    assert r.status_code == 200 and r.json()["global_discount_value"] == pct and not r.json().get("discount_approval_status"), r.text


@pytest.mark.parametrize("pct", [31, 35, 40])
def test_commercial_31_40_savable_approval_required(commercial, admin, qid, pct):
    r = _patch(commercial, qid, pct, "trattativa strategica")
    assert r.status_code == 200, r.text
    q = r.json()
    assert q["global_discount_value"] == pct and q["discount_approval_status"] == "DISCOUNT_APPROVAL_REQUIRED"
    da = _get(admin, qid)["discount_approval"]
    assert da["requested_discount"] == pct and da["requested_by"] and da["requested_at"] and da["reason"] == "trattativa strategica" and "margin_before" in da and "margin_after" in da
    # non finalizzabile finché pending
    r = commercial.post(f"{BASE_URL}/api/quotes/{qid}/status", json={"new_status": "sent"}, timeout=15)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "DISCOUNT_APPROVAL_PENDING"


def test_41_blocked_for_everyone(commercial, admin, qid):
    assert _patch(commercial, qid, 41, "altro").status_code == 403
    r = _patch(admin, qid, 41, "altro")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "ADMIN_DISCOUNT_CAP_EXCEEDED"


@pytest.mark.parametrize("pct", [35, 40])
def test_admin_direct_35_40_pass(admin, qid, pct):
    r = _patch(admin, qid, pct, "promozione autorizzata")
    assert r.status_code == 200 and r.json()["discount_approval_status"] == "APPROVED" and r.json()["discount_approval"]["auto_approved_admin_master"] is True, r.text
    fs = _fs(admin, qid)
    assert fs["post_margin_percent"] > 15 and fs["discount_status"] != "BLOCKED"


def test_margin_floor_blocks_35_even_admin(admin):
    qid = _mk_quote(admin, [LOW_MARGIN_LINE])
    r = _patch(admin, qid, 35, "competitor")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "DISCOUNT_BLOCKED_MARGIN_FLOOR", r.text
    assert _get(admin, qid)["global_discount_value"] in (0, None)  # nulla persistito


def test_vat_after_discount_and_commission_recalculation(admin, qid):
    q0 = _get(admin, qid)
    fs0 = _fs(admin, qid)
    r = _patch(admin, qid, 35, "volume commessa")
    assert r.status_code == 200, r.text
    q1 = r.json()
    fs1 = _fs(admin, qid)
    # sconto sull'imponibile, IVA ricalcolata sul nuovo imponibile (mai scontata direttamente)
    assert q1["subtotal"] < q0["subtotal"] and q1["vat_amount"] < q0["vat_amount"]
    assert abs(q1["vat_amount"] - round(q1["subtotal"] * 0.22, 2)) < 0.05 and abs(q1["total"] - (q1["subtotal"] + q1["vat_amount"])) < 0.05
    # commissione ricalcolata con la policy esistente: >30% → fascia 0
    assert fs1["effective_discount_percent"] >= 35 and fs1["actual_commission_rate"] == 0 and fs0["actual_commission_rate"] >= fs1["actual_commission_rate"]
    assert fs1["post_margin_percent"] < fs0["post_margin_percent"] and fs1["post_margin_percent"] > 15


def test_approval_workflow_approve_and_reject_audit_trail(commercial, admin, qid):
    assert _patch(commercial, qid, 10).status_code == 200
    r = _patch(commercial, qid, 33, "recupero cliente")
    assert r.status_code == 200
    # commerciale non può approvare
    r = commercial.post(f"{BASE_URL}/api/quotes/{qid}/discount-approval/approve", json={}, timeout=15)
    assert r.status_code == 403
    r = admin.post(f"{BASE_URL}/api/quotes/{qid}/discount-approval/reject", json={"note": "troppo"}, timeout=15)
    assert r.status_code == 200, r.text
    q = r.json()
    assert q["discount_approval_status"] == "REJECTED" and q["global_discount_value"] == 10 and q["discount_approval"]["rejected_by"] and q["discount_approval"]["rejected_at"]
    r = _patch(commercial, qid, 36, "competitor")
    assert r.status_code == 200
    r = admin.post(f"{BASE_URL}/api/quotes/{qid}/discount-approval/approve", json={"note": "ok direzione"}, timeout=15)
    assert r.status_code == 200, r.text
    q = r.json()
    assert q["discount_approval_status"] == "APPROVED" and q["global_discount_value"] == 36 and q["discount_approval"]["approved_by"] and q["discount_approval"]["approved_at"]
    assert admin.post(f"{BASE_URL}/api/quotes/{qid}/discount-approval/approve", json={}, timeout=15).status_code == 400
    audit = admin.get(f"{BASE_URL}/api/audit", params={"entity_id": qid, "limit": 50}, timeout=15)
    if audit.status_code == 200:
        rows = audit.json() if isinstance(audit.json(), list) else audit.json().get("items", [])
        assert any(a.get("action") in ("quote.discount_approve", "quote.discount_reject") for a in rows)
