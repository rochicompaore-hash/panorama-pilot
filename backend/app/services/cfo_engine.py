"""CFO CASH & REVENUE CONTROL TOWER V1 — financial truth engine (backend source of truth).

Principi PO: VENDUTO ≠ FATTURATO ≠ INCASSATO · nessun doppio conteggio (CASH_RECEIPTS_CANONICAL, EXPECTED vs PAYABLE) ·
legacy total=0 esclusi · saldo banca non certificato = INCOMPLETE · rate senza data = UNSCHEDULED (fuori calendario) ·
intercompany eliminato per coppia riconciliata · IVA esclusa dai ricavi economici · ACTUAL e FORECAST sempre distinti.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

CFO_ENGINE_VERSION = "cfo_engine_v1_2026_10"
GROUP = "GROUP"
UNASSIGNED = "UNASSIGNED"
OUTFLOW_CATEGORIES = ("FORNITORI", "STIPENDI", "AFFITTI", "LEASING", "MARKETING", "ENERGIA", "IMPOSTE", "ASSICURAZIONI", "SOFTWARE", "LOGISTICA", "POSA", "PRODUZIONE", "ALTRO")
_FIXED_CAT = {"rent": "AFFITTI", "insurance": "ASSICURAZIONI", "software": "SOFTWARE", "utilities": "ENERGIA", "consulting": "ALTRO", "marketing": "MARKETING",
              "leasing": "LEASING", "logistics": "LOGISTICA", "tax": "IMPOSTE", "energy": "ENERGIA"}
_PAYABLE_CAT = {"invoice": "FORNITORI", "supplier_invoice": "FORNITORI", "f24": "IMPOSTE", "tax": "IMPOSTE", "payroll": "STIPENDI", "rent": "AFFITTI", "leasing": "LEASING"}
AGING_BUCKETS = (("1-7", 1, 7), ("8-30", 8, 30), ("31-60", 31, 60), ("61-90", 61, 90), (">90", 91, 10 ** 6))
VF_CLASS = {"vat": "RESERVED_CASH", "contingency": "RESERVED_CASH", "investments": "VIRTUAL_ALLOCATION"}
GOODS_READY_STATUSES = {"completed", "ready_for_installation", "installed", "closed"}
INSTALLED_STATUSES = {"installed", "closed"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _d(v) -> Optional[date]:
    if not v:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _f(v) -> float:
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _le_match(item_le: Optional[str], le: Optional[str]) -> bool:
    return le in (None, GROUP) or (item_le or UNASSIGNED) == le


def _month_bounds(today: date):
    start = today.replace(day=1)
    nxt = (start + timedelta(days=32)).replace(day=1)
    return start, nxt - timedelta(days=1)


def settings_id(tenant_id: str, le: Optional[str]) -> str:
    return f"{tenant_id}:{le or GROUP}"


DEFAULT_SETTINGS = {"monthly_revenue_target": None, "annual_revenue_target": None, "monthly_collection_target": None, "minimum_cash_reserve": None}


async def load_settings(db, tenant_id: str, le: Optional[str]) -> Dict[str, Any]:
    doc = await db.cfo_settings.find_one({"_id": settings_id(tenant_id, le)}) or {}
    return {**DEFAULT_SETTINGS, **{k: doc.get(k) for k in DEFAULT_SETTINGS if k in doc}, "legal_entity_id": le or GROUP, "configured": bool(doc)}


# ---------------------------------------------------------------------------
# A. canonical sources
# ---------------------------------------------------------------------------
async def _plans(db, tenant_id: str) -> List[dict]:
    return await db.payment_plans.find({"tenant_id": tenant_id, "deleted_at": None}).to_list(5000)


async def _contracts(db, tenant_id: str) -> Dict[str, dict]:
    docs = await db.contracts.find({"tenant_id": tenant_id, "deleted_at": None}, {"quote_snapshot.lines": 0, "signed_snapshot": 0, "signature_data_url": 0}).to_list(5000)
    return {c["_id"]: c for c in docs}


def contract_economics(c: dict) -> Dict[str, Any]:
    """Importi del contratto: economic/signed snapshot → quote_snapshot. total=0 → LEGACY_ECONOMIC_DATA_INCOMPLETE (escluso dai KPI)."""
    eco = c.get("economic_snapshot") or {}
    qs = c.get("quote_snapshot") or {}
    total = _f(eco.get("total") or qs.get("total"))
    net = _f(eco.get("subtotal") or qs.get("subtotal"))
    return {"total": total, "net": net, "complete": total > 0, "flag": None if total > 0 else "LEGACY_ECONOMIC_DATA_INCOMPLETE"}


async def cash_receipts_canonical(db, tenant_id: str, contracts: Dict[str, dict], plans: List[dict]) -> Dict[str, Any]:
    """CASH_RECEIPTS_CANONICAL: payments + payments_received deduplicati per event_key (plan/contratto, rata, importo, giorno)."""
    plan_by_id = {p["_id"]: p for p in plans}
    plan_by_contract = {p["contract_id"]: p for p in plans if p.get("contract_id")}
    out: List[dict] = []
    seen: Dict[str, dict] = {}
    dups = 0
    for p in await db.payments.find({"tenant_id": tenant_id, "deleted_at": None}).to_list(10000):
        plan = plan_by_id.get(p.get("payment_plan_id")) or {}
        contract = contracts.get(plan.get("contract_id") or "") or {}
        dt = _d(p.get("received_at"))
        key = f"{plan.get('contract_id') or p.get('payment_plan_id')}|{p.get('installment_ref') or ''}|{_f(p.get('amount'))}|{dt}"
        rec = {"id": p["_id"], "source": "payments", "event_key": key, "amount": _f(p.get("amount")), "date": dt, "customer_id": p.get("customer_id"),
               "contract_id": plan.get("contract_id"), "payment_plan_id": p.get("payment_plan_id"), "installment_ref": p.get("installment_ref"),
               "legal_entity_id": plan.get("legal_entity_id") or contract.get("legal_entity_id")}
        seen[key] = rec
        out.append(rec)
    for r in await db.payments_received.find({"tenant_id": tenant_id, "deleted_at": None}).to_list(10000):
        dt = _d(r.get("payment_date") or r.get("value_date"))
        amount = _f(r.get("actual_bank_credit") or r.get("expected_bank_credit") or r.get("gross_amount"))
        gross = _f(r.get("gross_amount"))
        plan = plan_by_contract.get(r.get("contract_id") or "") or {}
        key = f"{r.get('contract_id') or r.get('invoice_id') or r['_id']}|{r.get('installment_ref') or ''}|{gross}|{dt}"
        if key in seen:
            dups += 1
            seen[key]["also_in"] = "payments_received"
            continue
        contract = contracts.get(r.get("contract_id") or "") or {}
        rec = {"id": r["_id"], "source": "payments_received", "event_key": key, "amount": amount, "gross_amount": gross, "date": dt, "customer_id": r.get("customer_id"),
               "contract_id": r.get("contract_id"), "payment_plan_id": plan.get("_id"), "installment_ref": r.get("installment_ref"), "bank_account_id": r.get("bank_account_id"),
               "legal_entity_id": plan.get("legal_entity_id") or contract.get("legal_entity_id")}
        seen[key] = rec
        out.append(rec)
    return {"receipts": out, "deduplicated_events": dups}


async def expected_collections(db, tenant_id: str, contracts: Dict[str, dict], plans: List[dict], today: date) -> List[dict]:
    """Rate aperte dei payment_plans. Stato: SCHEDULED | OVERDUE | TRIGGER_PENDING | UNSCHEDULED (mai date fittizie)."""
    orders = {o["_id"]: o for o in await db.sales_orders.find({"tenant_id": tenant_id, "deleted_at": None}, {"order_status": 1, "contract_id": 1, "updated_at": 1}).to_list(5000)}
    order_by_contract = {o.get("contract_id"): o for o in orders.values() if o.get("contract_id")}
    out = []
    for p in plans:
        contract = contracts.get(p.get("contract_id") or "") or {}
        order = orders.get(p.get("sales_order_id") or "") or order_by_contract.get(p.get("contract_id") or "") or {}
        le = p.get("legal_entity_id") or contract.get("legal_entity_id")
        linked = bool(p.get("contract_id") or p.get("sales_order_id"))
        for inst in p.get("installments") or []:
            if (inst.get("installment_status") or "pending") == "paid":
                continue
            residual = round(_f(inst.get("amount")) - _f(inst.get("paid_amount")), 2)
            if residual <= 0:
                continue
            trig = str(inst.get("trigger") or "").lower()
            due = _d(inst.get("due_date"))
            status, basis = "UNSCHEDULED", None
            if due:
                status, basis = ("OVERDUE" if due < today else "SCHEDULED"), "DUE_DATE_KNOWN"
            elif trig in ("signature", "order", "contract_signed") and contract.get("signed_at"):
                due, basis = _d(contract["signed_at"]), "EVENT_CONTRACT_SIGNED"
                status = "OVERDUE" if due < today else "SCHEDULED"
            elif trig in ("goods_ready", "apm"):
                if order.get("order_status") in GOODS_READY_STATUSES:
                    due, basis, status = _d(order.get("updated_at")) or today, "EVENT_GOODS_READY", "SCHEDULED"
                    status = "OVERDUE" if due < today else "SCHEDULED"
                else:
                    status, basis = "TRIGGER_PENDING", "GOODS_READY_NOT_OCCURRED"
            elif trig in ("installation", "installation_completed", "installed"):
                if order.get("order_status") in INSTALLED_STATUSES:
                    due, basis = _d(order.get("updated_at")) or today, "EVENT_INSTALLATION_COMPLETED"
                    status = "OVERDUE" if due < today else "SCHEDULED"
                else:
                    status, basis = "TRIGGER_PENDING", "INSTALLATION_NOT_OCCURRED"
            elif trig:
                status, basis = "TRIGGER_PENDING", f"TRIGGER_{trig.upper()}_PENDING"
            out.append({"payment_plan_id": p["_id"], "contract_id": p.get("contract_id"), "sales_order_id": p.get("sales_order_id"), "customer_id": p.get("customer_id"),
                        "installment_ref": inst.get("ref"), "label": inst.get("label"), "trigger": trig or None, "amount": residual, "due_date": due.isoformat() if due else None,
                        "days_overdue": (today - due).days if (due and due < today) else 0, "status": status, "date_basis": basis, "legal_entity_id": le, "linked": linked,
                        "contract_number": contract.get("number")})
    return out


async def expected_outflows(db, tenant_id: str, today: date, horizon_days: int = 120) -> Dict[str, Any]:
    """EXPECTED_OUTFLOWS: payables aperti + ricorrenti (fissi/personale) generati per mese con riconciliazione contro payable esistenti + F24.
    Purchase orders: PURCHASE_COMMITTED separato (mai uscita finanziaria automatica)."""
    end = today + timedelta(days=horizon_days)
    out, unscheduled, uncategorized, reconciled = [], [], 0, 0
    payables = await db.payables.find({"tenant_id": tenant_id, "deleted_at": None, "payable_status": {"$nin": ["paid", "cancelled"]}}).to_list(5000)
    pay_index = defaultdict(float)
    for pb in payables:
        residual = _f(pb.get("residual") if pb.get("residual") is not None else _f(pb.get("amount_gross")) - _f(pb.get("amount_paid")))
        if residual <= 0:
            continue
        cat = pb.get("category") or _PAYABLE_CAT.get(str(pb.get("doc_kind") or "").lower())
        if not cat:
            cat, uncategorized = "ALTRO", uncategorized + 1
        due = _d(pb.get("due_date"))
        item = {"id": pb["_id"], "source": "payable", "label": pb.get("label"), "supplier": pb.get("creditor"), "category": cat, "amount": residual, "due_date": due.isoformat() if due else None,
                "status": ("OVERDUE" if due and due < today else ("SCHEDULED" if due else "UNSCHEDULED")), "days_overdue": (today - due).days if (due and due < today) else 0,
                "legal_entity_id": pb.get("legal_entity_id"), "intercompany_pair_id": pb.get("linked_intercompany_pair_id"), "doc_ref": pb.get("doc_ref")}
        (out if due else unscheduled).append(item)
        if due:
            pay_index[(str(pb.get("label") or "").strip().lower(), due.year, due.month)] += residual
    for f24 in await db.f24.find({"tenant_id": tenant_id, "deleted_at": None, "f24_status": {"$nin": ["paid", "cancelled"]}}).to_list(1000):
        due = _d(f24.get("due_date"))
        item = {"id": f24["_id"], "source": "f24", "label": f24.get("label") or "F24", "supplier": "Erario", "category": "IMPOSTE", "amount": _f(f24.get("amount") or f24.get("total")),
                "due_date": due.isoformat() if due else None, "status": ("OVERDUE" if due and due < today else ("SCHEDULED" if due else "UNSCHEDULED")),
                "days_overdue": (today - due).days if (due and due < today) else 0, "legal_entity_id": f24.get("legal_entity_id"), "intercompany_pair_id": None}
        if item["amount"] > 0:
            (out if due else unscheduled).append(item)
    fixed = await db.fixed_costs.find({"tenant_id": tenant_id, "deleted_at": None, "active": {"$ne": False}}).to_list(2000)
    personnel = await db.personnel_costs.find({"tenant_id": tenant_id, "deleted_at": None, "active": {"$ne": False}}).to_list(2000)
    monthly_fixed = round(sum(_f(f.get("amount_monthly")) for f in fixed), 2)
    monthly_personnel = round(sum(_f(p.get("monthly_total_cost")) for p in personnel), 2)
    cur = today.replace(day=1)
    while cur <= end:
        for f in fixed:
            amt = _f(f.get("amount_monthly"))
            if amt <= 0 or (f.get("start_date") and _d(f["start_date"]) and _d(f["start_date"]) > cur) or (f.get("end_date") and _d(f["end_date"]) and _d(f["end_date"]) < cur):
                continue
            due = cur.replace(day=min(5, 28))
            if due < today:
                continue
            key = (str(f.get("label") or "").strip().lower(), due.year, due.month)
            if pay_index.get(key):
                reconciled += 1
                continue  # già rappresentato da un payable reale → nessun doppio conteggio
            out.append({"id": f"fixed:{f['_id']}:{due.isoformat()}", "source": "fixed_cost", "label": f.get("label"), "supplier": f.get("supplier"), "category": _FIXED_CAT.get(str(f.get("category") or "").lower(), "ALTRO"),
                        "amount": amt, "due_date": due.isoformat(), "status": "SCHEDULED", "days_overdue": 0, "legal_entity_id": f.get("legal_entity_id"), "intercompany_pair_id": None, "recurring": True})
        pay_day = cur.replace(day=27)
        if monthly_personnel > 0 and pay_day >= today:
            by_le = defaultdict(float)
            for p in personnel:
                by_le[p.get("legal_entity_id")] += _f(p.get("monthly_total_cost"))
            for le, amt in by_le.items():
                if pay_index.get(("stipendi", pay_day.year, pay_day.month)):
                    reconciled += 1
                    continue
                out.append({"id": f"payroll:{le or UNASSIGNED}:{pay_day.isoformat()}", "source": "personnel_cost", "label": "Stipendi e oneri", "supplier": None, "category": "STIPENDI",
                            "amount": round(amt, 2), "due_date": pay_day.isoformat(), "status": "SCHEDULED", "days_overdue": 0, "legal_entity_id": le, "intercompany_pair_id": None, "recurring": True})
        cur = (cur + timedelta(days=32)).replace(day=1)
    committed = []
    for po in await db.purchase_orders.find({"tenant_id": tenant_id, "deleted_at": None, "po_status": {"$nin": ["cancelled", "closed", "paid"]}}).to_list(2000):
        committed.append({"id": po["_id"], "number": po.get("number"), "supplier": po.get("supplier_name"), "amount": _f(po.get("total")), "status": "PURCHASE_COMMITTED",
                          "due_date": po.get("payment_due_date"), "forecastable": bool(po.get("payment_due_date") and po.get("payment_terms"))})
    return {"items": out, "unscheduled": unscheduled, "purchase_committed": committed, "uncategorized_payables": uncategorized, "reconciled_recurring": reconciled,
            "monthly_fixed_costs": monthly_fixed, "monthly_personnel_costs": monthly_personnel}


async def cash_position(db, tenant_id: str, le: Optional[str]) -> Dict[str, Any]:
    """Solo saldi CERTIFICATI (certified_balance + certified_at). Saldo 0 non certificato = BANK_BALANCE_NOT_CONFIGURED. Virtual funds mai sommati."""
    accounts = await db.bank_accounts.find({"tenant_id": tenant_id, "deleted_at": None, "active": {"$ne": False}, "is_virtual": {"$ne": True}}).to_list(200)
    rows, total, as_of, missing = [], 0.0, None, 0
    for a in accounts:
        if not _le_match(a.get("legal_entity_id"), le):
            continue
        cert = a.get("certified_balance")
        cert_at = _d(a.get("certified_at"))
        ok = cert is not None and cert_at is not None
        rows.append({"id": a["_id"], "label": a.get("label"), "bank_name": a.get("bank_name"), "legal_entity_id": a.get("legal_entity_id"), "certified_balance": cert,
                     "certified_at": cert_at.isoformat() if cert_at else None, "status": "CERTIFIED" if ok else "BANK_BALANCE_NOT_CONFIGURED"})
        if ok:
            total += _f(cert)
            as_of = cert_at if as_of is None or cert_at < as_of else as_of
        else:
            missing += 1
    funds = [{"id": f["_id"], "code": f.get("code"), "label": f.get("label"), "classification": f.get("cash_classification") or VF_CLASS.get(str(f.get("code") or "").lower(), "OTHER"), "balance": f.get("balance")}
             for f in await db.virtual_funds.find({"tenant_id": tenant_id, "deleted_at": None}).to_list(50)]
    status = "COMPLETE" if rows and missing == 0 else ("PARTIAL" if total and missing else "INCOMPLETE")
    return {"status": status, "available_cash": round(total, 2) if status != "INCOMPLETE" else None, "as_of": as_of.isoformat() if as_of else None, "accounts": rows,
            "accounts_not_configured": missing, "virtual_funds": funds, "virtual_funds_note": "Fondi virtuali classificati, mai sommati alla cassa reale (solo REAL_CASH potrebbe esserlo)."}


# ---------------------------------------------------------------------------
# E. revenue / margin
# ---------------------------------------------------------------------------
async def revenue_block(db, tenant_id: str, le: Optional[str], today: date, contracts: Dict[str, dict], settings: Dict[str, Any]) -> Dict[str, Any]:
    ms, me = _month_bounds(today)
    ys = today.replace(month=1, day=1)
    inv = [i for i in await db.invoices.find({"tenant_id": tenant_id, "deleted_at": None, "invoice_status": {"$nin": ["draft", "cancelled"]}}).to_list(10000) if _le_match(i.get("legal_entity_id"), le)]
    def _sum(pred):
        return round(sum(_f(i.get("subtotal")) * (-1 if i.get("invoice_status") == "credit_note" else 1) for i in inv if pred(_d(i.get("issue_date")))), 2)
    invoiced_today, invoiced_month, invoiced_ytd = _sum(lambda d: d == today), _sum(lambda d: d and ms <= d <= me), _sum(lambda d: d and d >= ys)
    sold_month, sold_ytd, legacy, sold_items = 0.0, 0.0, 0, 0
    forecast_month = 0.0
    for c in contracts.values():
        if c.get("contract_status") != "signed" or not _le_match(c.get("legal_entity_id"), le):
            continue
        eco = contract_economics(c)
        if not eco["complete"]:
            legacy += 1
            continue
        sd = _d(c.get("signed_at"))
        sold_items += 1
        if sd and sd >= ys:
            sold_ytd += eco["net"]
        if sd and ms <= sd <= me:
            sold_month += eco["net"]
        if not c.get("invoiced_amount") and sd and sd >= ms - timedelta(days=90):
            forecast_month += eco["net"]  # venduto economicamente valido non ancora fatturato → FORECAST (mai ACTUAL)
    target_m = settings.get("monthly_revenue_target")
    return {"invoiced": {"today": invoiced_today, "month": invoiced_month, "ytd": invoiced_ytd, "invoice_count": len(inv),
                         "data_status": "OK" if inv else "NO_INVOICE_DATA_AVAILABLE", "basis": "ACTUAL — documenti fiscali emessi, imponibile netto IVA"},
            "sold": {"month": round(sold_month, 2), "ytd": round(sold_ytd, 2), "contracts_complete": sold_items, "contracts_legacy_excluded": legacy,
                     "legacy_flag": "LEGACY_ECONOMIC_DATA_INCOMPLETE" if legacy else None, "basis": "contratti firmati economicamente validi (imponibile)"},
            "target": {"monthly_revenue_target": target_m, "annual_revenue_target": settings.get("annual_revenue_target"),
                       "percent_reached": round(invoiced_month / target_m * 100, 1) if target_m else None, "missing_to_target": round(target_m - invoiced_month, 2) if target_m else None},
            "forecast_month": {"actual_invoiced": invoiced_month, "forecast_from_sold_not_invoiced": round(forecast_month, 2), "total_forecast": round(invoiced_month + forecast_month, 2), "kind": "FORECAST"}}


async def margin_block(db, tenant_id: str) -> Dict[str, Any]:
    """Margine medio ponderato SOLO su record ECONOMICALLY_COMPLETE (financial_snapshot COMPLETE, costi presenti)."""
    cur = db.quotes.find({"tenant_id": tenant_id, "deleted_at": None, "quote_status": {"$in": ["accepted", "converted"]}, "financial_snapshot.financial_snapshot_status": "COMPLETE"},
                         {"subtotal": 1, "financial_snapshot.post_margin_percent": 1, "financial_snapshot.total_internal_cost": 1})
    rev, cost, n = 0.0, 0.0, 0
    async for q in cur:
        fs = q.get("financial_snapshot") or {}
        s = _f(q.get("subtotal"))
        pm = fs.get("post_margin_percent")
        if s <= 0 or pm is None:
            continue
        rev += s
        cost += s * (1 - float(pm) / 100)
        n += 1
    ratio = round((rev - cost) / rev, 4) if rev > 0 else None
    return {"weighted_contribution_margin_ratio": ratio, "weighted_margin_percent": round(ratio * 100, 1) if ratio is not None else None, "margin_sample_size": n,
            "status": "OK" if n >= 5 else ("LOW_SAMPLE" if n else "NOT_AVAILABLE")}


# ---------------------------------------------------------------------------
# D. cash engine
# ---------------------------------------------------------------------------
def _ic_eliminate(items: List[dict], le: Optional[str], ic_pairs_reconciled: set) -> (List[dict], float):
    if le not in (None, GROUP):
        return items, 0.0
    kept, elim = [], 0.0
    for it in items:
        if it.get("intercompany_pair_id") and it["intercompany_pair_id"] in ic_pairs_reconciled:
            elim += it["amount"]
        else:
            kept.append(it)
    return kept, round(elim, 2)


async def reconciled_ic_pairs(db, tenant_id: str) -> Dict[str, Any]:
    """Coppia riconciliata = pair_id con entrambi i lati (source+target) presenti. Solo queste vengono eliminate nella GROUP VIEW."""
    sides = defaultdict(set)
    async for t in db.intercompany_transactions.find({"tenant_id": tenant_id, "deleted_at": None}, {"intercompany_pair_id": 1, "side": 1}):
        sides[t.get("intercompany_pair_id")].add(t.get("side"))
    rec = {k for k, v in sides.items() if {"source", "target"} <= v}
    return {"pairs": rec, "reconciled": len(rec), "unreconciled": len(sides) - len(rec)}


def build_calendar(opening: Optional[float], as_of: Optional[date], today: date, receipts: List[dict], payments_actual: List[dict], coll: List[dict], outf: List[dict]) -> Dict[str, Any]:
    """OPENING + actual (dopo as_of) + scheduled − actual payments − scheduled outflows = forecast closing. Solo movimenti con data attendibile."""
    def within(d: Optional[str], upto: date):
        dd = _d(d)
        return dd is not None and dd <= upto
    actual_in = sum(r["amount"] for r in receipts if as_of and r["date"] and r["date"] > as_of)
    actual_out = sum(p["amount"] for p in payments_actual if as_of and p["date"] and p["date"] > as_of)
    base = (opening + actual_in - actual_out) if opening is not None else None
    horizons = {}
    for lab, days in (("today", 0), ("7d", 7), ("14d", 14), ("30d", 30), ("60d", 60), ("90d", 90)):
        upto = today + timedelta(days=days)
        inflow = round(sum(c["amount"] for c in coll if c["status"] in ("SCHEDULED", "OVERDUE") and within(c["due_date"], upto)), 2)
        outflow = round(sum(o["amount"] for o in outf if within(o["due_date"], upto)), 2)
        horizons[lab] = {"inflows": inflow, "outflows": outflow, "net": round(inflow - outflow, 2), "forecast_closing_cash": round(base + inflow - outflow, 2) if base is not None else None}
    weeks, run, gap_week = [], base, None
    for w in range(13):
        ws, we = today + timedelta(days=7 * w), today + timedelta(days=7 * w + 6)
        inflow = round(sum(c["amount"] for c in coll if c["status"] in ("SCHEDULED", "OVERDUE") and _d(c["due_date"]) and ws <= _d(c["due_date"]) <= we), 2)
        outflow = round(sum(o["amount"] for o in outf if _d(o["due_date"]) and ws <= _d(o["due_date"]) <= we), 2)
        closing = round(run + inflow - outflow, 2) if run is not None else None
        if closing is not None and closing < 0 and gap_week is None:
            gap_week = f"W{w + 1}"
        weeks.append({"week": f"W{w + 1}", "start": ws.isoformat(), "end": we.isoformat(), "opening": run, "inflows": inflow, "outflows": outflow, "closing": closing, "cash_gap": closing is not None and closing < 0})
        run = closing
    return {"opening_cash": opening, "as_of": as_of.isoformat() if as_of else None, "actual_collections_since_as_of": round(actual_in, 2), "actual_payments_since_as_of": round(actual_out, 2),
            "current_cash_estimate": round(base, 2) if base is not None else None, "horizons": horizons, "weeks": weeks, "first_cash_gap_week": gap_week,
            "status": "COMPLETE" if base is not None else "INCOMPLETE"}


def aging(items: List[dict], today: date) -> Dict[str, Any]:
    buckets = {b[0]: 0.0 for b in AGING_BUCKETS}
    total = 0.0
    for it in items:
        d = it.get("days_overdue") or 0
        if d <= 0:
            continue
        total += it["amount"]
        for lab, lo, hi in AGING_BUCKETS:
            if lo <= d <= hi:
                buckets[lab] += it["amount"]
                break
    return {"total_overdue": round(total, 2), "buckets": {k: round(v, 2) for k, v in buckets.items()}}


def receivables_by_customer(coll: List[dict], receipts: List[dict], customers: Dict[str, dict], today: date) -> List[dict]:
    by = defaultdict(lambda: {"due": 0.0, "overdue": 0.0, "pending": 0.0, "unscheduled": 0.0, "max_days_overdue": 0, "next_due": None, "contracts": set()})
    for c in coll:
        b = by[c.get("customer_id")]
        if c["status"] == "OVERDUE":
            b["overdue"] += c["amount"]; b["due"] += c["amount"]; b["max_days_overdue"] = max(b["max_days_overdue"], c["days_overdue"])
        elif c["status"] == "SCHEDULED":
            b["due"] += c["amount"]
            if b["next_due"] is None or c["due_date"] < b["next_due"]:
                b["next_due"] = c["due_date"]
        elif c["status"] == "TRIGGER_PENDING":
            b["pending"] += c["amount"]
        else:
            b["unscheduled"] += c["amount"]
        if c.get("contract_number"):
            b["contracts"].add(c["contract_number"])
    paid = defaultdict(float)
    for r in receipts:
        paid[r.get("customer_id")] += r["amount"]
    rows = []
    for cid, b in by.items():
        cu = customers.get(cid) or {}
        name = " ".join(x for x in (cu.get("first_name"), cu.get("last_name")) if x) or cu.get("company_name") or cu.get("name") or "Cliente"
        residual = round(b["due"] + b["pending"] + b["unscheduled"], 2)
        if b["overdue"] > 0:
            status = "SCADUTO" if paid[cid] <= 0 else "PARZIALMENTE INCASSATO"
        elif b["next_due"] and _d(b["next_due"]) <= today + timedelta(days=7):
            status = "IN SCADENZA"
        else:
            status = "DA INCASSARE"
        rows.append({"customer_id": cid, "customer_name": name, "collected": round(paid[cid], 2), "residual": residual, "due_scheduled": round(b["due"], 2), "overdue": round(b["overdue"], 2),
                     "trigger_pending": round(b["pending"], 2), "unscheduled": round(b["unscheduled"], 2), "days_overdue": b["max_days_overdue"], "next_due": b["next_due"], "status": status,
                     "contracts": sorted(b["contracts"])})
    rows.sort(key=lambda r: (-r["overdue"], -r["residual"]))
    return rows


# ---------------------------------------------------------------------------
# F. overview (single engine)
# ---------------------------------------------------------------------------
async def overview(db, tenant_id: str, le: Optional[str] = None, today: Optional[date] = None) -> Dict[str, Any]:
    today = today or datetime.now(timezone.utc).date()
    le = None if le in (None, "", "all", GROUP) else le
    settings = await load_settings(db, tenant_id, le)
    contracts = await _contracts(db, tenant_id)
    plans = await _plans(db, tenant_id)
    ic = await reconciled_ic_pairs(db, tenant_id)
    canon = await cash_receipts_canonical(db, tenant_id, contracts, plans)
    receipts = [r for r in canon["receipts"] if _le_match(r.get("legal_entity_id"), le)]
    coll_all = [c for c in await expected_collections(db, tenant_id, contracts, plans, today) if _le_match(c.get("legal_entity_id"), le)]
    outf_raw = await expected_outflows(db, tenant_id, today)
    outf_items = [o for o in outf_raw["items"] if _le_match(o.get("legal_entity_id"), le)]
    outf_items, ic_elim_out = _ic_eliminate(outf_items, le, ic["pairs"])
    unsched_out = [o for o in outf_raw["unscheduled"] if _le_match(o.get("legal_entity_id"), le)]
    cash = await cash_position(db, tenant_id, le)
    paid_payables = [{"amount": _f(p.get("amount_paid")), "date": _d(p.get("paid_at") or p.get("updated_at"))} for p in
                     await db.payables.find({"tenant_id": tenant_id, "deleted_at": None, "payable_status": "paid"}).to_list(5000) if _le_match(p.get("legal_entity_id"), le)]
    ms, me = _month_bounds(today)
    collected_month = round(sum(r["amount"] for r in receipts if r["date"] and ms <= r["date"] <= me), 2)
    collected_ytd = round(sum(r["amount"] for r in receipts if r["date"] and r["date"] >= today.replace(month=1, day=1)), 2)
    paid_month = round(sum(p["amount"] for p in paid_payables if p["date"] and ms <= p["date"] <= me), 2)
    revenue = await revenue_block(db, tenant_id, le, today, contracts, settings)
    margin = await margin_block(db, tenant_id)
    as_of = _d(cash.get("as_of"))
    calendar = build_calendar(cash.get("available_cash"), as_of, today, receipts, paid_payables, coll_all, outf_items)
    h30 = calendar["horizons"]["30d"]
    reserve = _f(settings.get("minimum_cash_reserve")) if settings.get("minimum_cash_reserve") is not None else None
    avail = calendar.get("current_cash_estimate")
    gap_30 = None if avail is None else round(max(0.0, h30["outflows"] + (reserve or 0) - avail - h30["inflows"]), 2)
    min_req = None if avail is None else round(h30["outflows"] + (reserve or 0) - h30["inflows"], 2)
    safety = None if avail is None else round(avail + h30["inflows"] - h30["outflows"] - (reserve or 0), 2)
    cash_safety_status = None if avail is None else ("BELOW_RESERVE" if reserve is not None and (avail + h30["inflows"] - h30["outflows"]) < reserve else ("AT_RISK" if (avail + h30["inflows"] - h30["outflows"]) < 0 else "SAFE"))
    monthly_structure = round(outf_raw["monthly_fixed_costs"] + outf_raw["monthly_personnel_costs"], 2)
    be_rev = round(monthly_structure / margin["weighted_contribution_margin_ratio"], 2) if margin["weighted_contribution_margin_ratio"] else None
    customers = {c["_id"]: c for c in await db.customers.find({"tenant_id": tenant_id, "deleted_at": None}, {"first_name": 1, "last_name": 1, "company_name": 1, "name": 1}).to_list(10000)}
    ar_rows = receivables_by_customer(coll_all, receipts, customers, today)
    ar_aging = aging([c for c in coll_all if c["status"] == "OVERDUE"], today)
    ap_aging = aging([o for o in outf_items if o["status"] == "OVERDUE"], today)
    def _due_within(items, days):
        return round(sum(i["amount"] for i in items if i["status"] in ("SCHEDULED", "OVERDUE") and _d(i["due_date"]) and _d(i["due_date"]) <= today + timedelta(days=days)), 2)
    supplier_due = {"overdue": ap_aging["total_overdue"], "7d": _due_within([o for o in outf_items if o["source"] in ("payable", "f24")], 7), "30d": _due_within([o for o in outf_items if o["source"] in ("payable", "f24")], 30), "60d": _due_within([o for o in outf_items if o["source"] in ("payable", "f24")], 60)}
    inv_total = revenue["invoiced"]["ytd"]
    conversion = round(collected_ytd / inv_total * 100, 1) if inv_total > 0 else None
    dso = None
    if revenue["invoiced"]["invoice_count"] > 0 and inv_total > 0:
        ar_open = sum(r["due_scheduled"] for r in ar_rows)
        dso = round(ar_open / inv_total * (today - today.replace(month=1, day=1)).days, 0) if ar_open else 0
    outf_month = round(sum(o["amount"] for o in outf_items if _d(o["due_date"]) and ms <= _d(o["due_date"]) <= me), 2)
    coll_month_sched = round(sum(c["amount"] for c in coll_all if c["status"] in ("SCHEDULED", "OVERDUE") and _d(c["due_date"]) and _d(c["due_date"]) <= me), 2)
    unsched_in = round(sum(c["amount"] for c in coll_all if c["status"] in ("UNSCHEDULED", "TRIGGER_PENDING")), 2)
    forecast_month = {"revenue": revenue["forecast_month"], "collections": {"actual": collected_month, "scheduled_to_month_end": coll_month_sched, "total_forecast": round(collected_month + coll_month_sched, 2), "kind": "FORECAST"},
                      "outflows": {"actual_paid": paid_month, "scheduled_to_month_end": outf_month, "total_forecast": round(paid_month + outf_month, 2), "kind": "FORECAST"},
                      "cash": {"forecast_month_end": round(avail + coll_month_sched - outf_month, 2) if avail is not None else None, "kind": "FORECAST", "status": calendar["status"]}}
    dq = [
        {"area": "FATTURATO", "ok": revenue["invoiced"]["invoice_count"] > 0, "message": "OK" if revenue["invoiced"]["invoice_count"] else "NO INVOICE DATA AVAILABLE"},
        {"area": "CASSA", "ok": cash["status"] == "COMPLETE", "message": "OK" if cash["status"] == "COMPLETE" else f"BANK BALANCE NOT CONFIGURED ({cash['accounts_not_configured']} conti)"},
        {"area": "EXPECTED COLLECTIONS", "ok": not any(c["status"] in ("UNSCHEDULED", "TRIGGER_PENDING") for c in coll_all),
         "message": f"{sum(1 for c in coll_all if c['status']=='UNSCHEDULED')} INSTALLMENTS UNSCHEDULED · {sum(1 for c in coll_all if c['status']=='TRIGGER_PENDING')} TRIGGER PENDING · {sum(1 for c in coll_all if not c['linked'])} piani non collegati a contratto/ordine"},
        {"area": "MARGINE", "ok": margin["status"] == "OK", "message": f"{margin['margin_sample_size']} COMPLETE ORDERS"},
        {"area": "USCITE", "ok": outf_raw["uncategorized_payables"] == 0 and not unsched_out, "message": f"{outf_raw['uncategorized_payables']} PAYABLES UNCATEGORIZED · {len(unsched_out)} senza scadenza · {outf_raw['reconciled_recurring']} ricorrenti riconciliati con payable"},
        {"area": "VENDUTO", "ok": revenue["sold"]["contracts_legacy_excluded"] == 0, "message": f"{revenue['sold']['contracts_legacy_excluded']} contratti LEGACY_ECONOMIC_DATA_INCOMPLETE esclusi"},
        {"area": "INCASSI", "ok": True, "message": f"{len(receipts)} incassi canonici · {canon['deduplicated_events']} eventi deduplicati"},
        {"area": "INTERCOMPANY", "ok": ic["unreconciled"] == 0, "message": f"{ic['reconciled']} coppie riconciliate (eliminate in GROUP) · {ic['unreconciled']} non riconciliate"},
        {"area": "TARGET", "ok": settings["configured"], "message": "OK" if settings["configured"] else "MANUAL CONFIGURATION REQUIRED (target, riserva minima)"},
    ]
    alerts, actions = _alerts_actions(today, calendar, gap_30, reserve, ar_rows, outf_items, revenue, forecast_month, cash)
    from app.services import sustainability_engine as sus  # stessa verità: registry costi fissi + contribution engine + settings
    structure = await sus.overview(db, tenant_id, le, today)
    dq.append({"area": "COSTI FISSI", "ok": structure["fixed_cost_registry"]["reconciliation_status"] == "COMPLETE",
               "message": f"registry {structure['fixed_cost_registry']['annual_total']} € vs PO reference {sus.PO_REFERENCE_ANNUAL_FIXED_COST} € → FIXED_COST_RECONCILIATION = {structure['fixed_cost_registry']['reconciliation_status']}"})
    dq.append({"area": "PRICING SUSTAINABILITY", "ok": structure["plan"]["data_quality"] == "COMPLETE", "message": f"{structure['plan']['data_quality']}" + (f" (mancano: {', '.join(structure['plan']['missing'])})" if structure["plan"]["missing"] else "")})
    return {"engine_version": CFO_ENGINE_VERSION, "today": today.isoformat(), "legal_entity_id": le or GROUP, "settings": settings,
            "kpi_row1": {"invoiced_month": revenue["invoiced"]["month"], "invoiced_status": revenue["invoiced"]["data_status"], "collected_month": collected_month, "paid_month": paid_month,
                         "available_cash": avail, "cash_status": calendar["status"], "sold_month": revenue["sold"]["month"]},
            "kpi_row2": {"revenue_target": revenue["target"], "collection_target": {"monthly_collection_target": settings.get("monthly_collection_target"), "actual": collected_month,
                                                                                    "percent_reached": round(collected_month / settings["monthly_collection_target"] * 100, 1) if settings.get("monthly_collection_target") else None},
                         "cash_gap_30d": gap_30, "minimum_cash_requirement_30d": min_req, "forecast_cash_month_end": forecast_month["cash"]["forecast_month_end"]},
            "kpi_row3": {"break_even_revenue_monthly": be_rev, "monthly_structure_costs": monthly_structure, "margin": margin, "distance_to_break_even": round(be_rev - revenue["invoiced"]["month"], 2) if be_rev is not None else None,
                         "minimum_cash_reserve": reserve, "margin_of_safety_cash_30d": safety, "cash_safety_status": cash_safety_status,
                         "note": "Break-even fatturato (struttura/margine) e fabbisogno di cassa sono indicatori diversi"},
            "cash_calendar": calendar["horizons"], "weeks_13": calendar["weeks"], "first_cash_gap_week": calendar["first_cash_gap_week"], "cash_position": cash,
            "cash_flow_status": calendar["status"], "unscheduled_inflows": unsched_in, "unscheduled_outflows": round(sum(o["amount"] for o in unsched_out), 2),
            "receivables": {"rows": ar_rows[:50], "total_residual": round(sum(r["residual"] for r in ar_rows), 2), "total_due_scheduled": round(sum(r["due_scheduled"] for r in ar_rows), 2), "aging": ar_aging},
            "payables": {"supplier_due": supplier_due, "aging": ap_aging, "items_30d": sorted([o for o in outf_items if _d(o["due_date"]) and _d(o["due_date"]) <= today + timedelta(days=30)], key=lambda o: o["due_date"])[:50],
                         "unscheduled": unsched_out[:50], "purchase_committed": outf_raw["purchase_committed"][:50], "intercompany_eliminated": ic_elim_out},
            "collections_30d": sorted([c for c in coll_all if c["status"] in ("SCHEDULED", "OVERDUE") and _d(c["due_date"]) and _d(c["due_date"]) <= today + timedelta(days=30)], key=lambda c: c["due_date"])[:50],
            "collections_pending": [c for c in coll_all if c["status"] in ("TRIGGER_PENDING", "UNSCHEDULED")][:50],
            "revenue": revenue, "collected_ytd": collected_ytd, "cash_conversion_percent": conversion, "dso": dso if dso is not None else "NOT_AVAILABLE",
            "forecast_month_end": forecast_month, "data_quality": dq, "alerts": alerts, "next_actions": actions, "structure_coverage": structure["plan"], "fixed_cost_registry": structure["fixed_cost_registry"],
            "email_go_live": "BLOCKED_BY_SECRET"}


def _alerts_actions(today, calendar, gap_30, reserve, ar_rows, outf_items, revenue, forecast_month, cash):
    alerts, actions = [], []
    fmt = lambda v: f"€{v:,.0f}".replace(",", ".")
    for lab, days in (("7d", 7), ("30d", 30)):
        h = calendar["horizons"][lab]
        if h["forecast_closing_cash"] is not None and h["forecast_closing_cash"] < 0:
            alerts.append({"code": f"CASH_GAP_IN_{days}_DAYS", "severity": "critical", "message": f"Saldo previsto a {days} giorni: {fmt(h['forecast_closing_cash'])}"})
    if gap_30 and gap_30 > 0:
        actions.append({"code": "CASH_GAP_30D", "message": f"Servono almeno {fmt(gap_30)} di ulteriori incassi entro 30 giorni per mantenere la cassa ≥ riserva minima ({fmt(reserve or 0)})."})
    for r in ar_rows[:3]:
        if r["overdue"] > 0:
            alerts.append({"code": "LARGE_CUSTOMER_PAYMENT_OVERDUE", "severity": "high", "message": f"{r['customer_name']}: {fmt(r['overdue'])} scaduto da {r['days_overdue']} gg"})
            actions.append({"code": "RECOVER_RECEIVABLE", "customer_id": r["customer_id"], "message": f"Recuperare {fmt(r['overdue'])} credito {r['customer_name']} ({r['days_overdue']} gg di ritardo)"})
    for o in sorted([o for o in outf_items if o["source"] in ("payable", "f24") and _d(o["due_date"]) and _d(o["due_date"]) <= today + timedelta(days=7)], key=lambda o: -o["amount"])[:3]:
        code = "TAX_PAYMENT_DUE" if o["category"] == "IMPOSTE" else "SUPPLIER_PAYMENT_DUE"
        alerts.append({"code": code, "severity": "medium", "message": f"{o['label']}: {fmt(o['amount'])} in scadenza il {o['due_date']}"})
        actions.append({"code": code, "message": f"Pagamento {o['label']} {fmt(o['amount'])} tra {(_d(o['due_date']) - today).days} gg"})
    payroll = [o for o in outf_items if o["category"] == "STIPENDI" and _d(o["due_date"]) and _d(o["due_date"]) <= today + timedelta(days=30)]
    if payroll and calendar["horizons"]["30d"]["forecast_closing_cash"] is not None and calendar["horizons"]["30d"]["forecast_closing_cash"] < sum(p["amount"] for p in payroll):
        alerts.append({"code": "PAYROLL_COVERAGE_RISK", "severity": "high", "message": f"Copertura stipendi a rischio: {fmt(sum(p['amount'] for p in payroll))} entro 30 gg"})
    if calendar["first_cash_gap_week"]:
        wk = next(w for w in calendar["weeks"] if w["week"] == calendar["first_cash_gap_week"])
        actions.append({"code": "FIRST_CASH_GAP", "message": f"Nella settimana {wk['week']} (dal {wk['start']}) il saldo previsto scende a {fmt(wk['closing'])}."})
    t = revenue["target"]
    if t.get("missing_to_target") and t["missing_to_target"] > 0:
        actions.append({"code": "REVENUE_BELOW_TARGET", "message": f"Fatturato mese sotto target di {fmt(t['missing_to_target'])} ({t['percent_reached']}% raggiunto)."})
    if cash["status"] != "COMPLETE":
        actions.append({"code": "CONFIGURE_BANK_BALANCE", "message": "Certificare il saldo banca (saldo, data, conto, legal entity): CASH FORECAST = INCOMPLETE."})
    if revenue["invoiced"]["invoice_count"] == 0:
        actions.append({"code": "NO_INVOICE_DATA", "message": "Nessuna fattura registrata: FATTURATO ACTUAL = €0 con DATA STATUS = NO INVOICE DATA AVAILABLE."})
    return alerts, actions


def simulate(*, revenue: float, collection_pct: float, margin_pct: float, collection_days: int, monthly_structure: float, available_cash: Optional[float], scheduled_outflows: float, reserve: float) -> Dict[str, Any]:
    collected = round(revenue * collection_pct / 100, 2)
    result = round(revenue * margin_pct / 100 - monthly_structure, 2)
    be = round(monthly_structure / (margin_pct / 100), 2) if margin_pct > 0 else None
    cash_fc = None if available_cash is None else round(available_cash + collected - scheduled_outflows, 2)
    gap = None if cash_fc is None else round(max(0.0, reserve - cash_fc), 2)
    return {"revenue": revenue, "collected_expected": collected, "collection_days": collection_days, "operating_result": result, "break_even_revenue": be,
            "distance_to_break_even": round(be - revenue, 2) if be is not None else None, "forecast_cash": cash_fc, "cash_gap_vs_reserve": gap, "kind": "SIMULATION"}
