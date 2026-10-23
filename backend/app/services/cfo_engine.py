"""CFO CASH & REVENUE CONTROL TOWER V1 — financial truth engine (backend source of truth).

Principi PO: VENDUTO ≠ FATTURATO ≠ INCASSATO · nessun doppio conteggio (CASH_RECEIPTS_CANONICAL, EXPECTED vs PAYABLE) ·
legacy total=0 esclusi · saldo banca non certificato = INCOMPLETE · rate senza data = UNSCHEDULED (fuori calendario) ·
intercompany eliminato per coppia riconciliata · IVA esclusa dai ricavi economici · ACTUAL e FORECAST sempre distinti.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

CFO_ENGINE_VERSION = "cfo_engine_v1_2026_10_cash_reliability"
GROUP = "GROUP"
UNASSIGNED = "UNASSIGNED"
OUTFLOW_CATEGORIES = ("FORNITORI", "STIPENDI", "AFFITTI", "LEASING", "MARKETING", "ENERGIA", "IMPOSTE", "ASSICURAZIONI", "SOFTWARE", "LOGISTICA", "POSA", "PRODUZIONE", "ALTRO")
_FIXED_CAT = {"rent": "AFFITTI", "insurance": "ASSICURAZIONI", "software": "SOFTWARE", "utilities": "ENERGIA", "consulting": "ALTRO", "marketing": "MARKETING",
              "leasing": "LEASING", "logistics": "LOGISTICA", "tax": "IMPOSTE", "energy": "ENERGIA"}
_PAYABLE_CAT = {"invoice": "FORNITORI", "supplier_invoice": "FORNITORI", "f24": "IMPOSTE", "tax_f24": "IMPOSTE", "tax": "IMPOSTE", "payroll": "STIPENDI", "salary": "STIPENDI", "rent": "AFFITTI", "leasing": "LEASING", "loan": "FINANZIAMENTI"}
AGING_BUCKETS = (("1-7", 1, 7), ("8-30", 8, 30), ("31-60", 31, 60), ("61-90", 61, 90), (">90", 91, 10 ** 6))
VF_CLASS = {"vat": "RESERVED_CASH", "contingency": "RESERVED_CASH", "investments": "VIRTUAL_ALLOCATION"}
GOODS_READY_STATUSES = {"completed", "ready_for_installation", "installed", "closed"}
INSTALLED_STATUSES = {"installed", "closed"}
# Forecast eligibility also requires a valid, non-past due date. An overdue
# receivable remains an open receivable, never an assumed collection today.
CERTAIN_STATUSES = ("DUE", "SCHEDULED")
FORECAST_DAYS = 13 * 7
EVENT_GRACE_DAYS = 7
PRIORITIES = ("CRITICAL", "IMPORTANT", "DEFERRABLE", "DISCRETIONARY")
_PRIORITY_BY_CAT = {"STIPENDI": "CRITICAL", "IMPOSTE": "CRITICAL", "F24": "CRITICAL", "AFFITTI": "CRITICAL", "FORNITORI": "IMPORTANT", "LEASING": "IMPORTANT", "FINANZIAMENTI": "IMPORTANT",
                    "ASSICURAZIONI": "IMPORTANT", "ENERGIA": "IMPORTANT", "SOFTWARE": "IMPORTANT", "LOGISTICA": "IMPORTANT", "POSA": "IMPORTANT", "PRODUZIONE": "IMPORTANT", "MARKETING": "DEFERRABLE", "ALTRO": "IMPORTANT"}
_CASH_MONTHS = {"monthly": 1, "bimonthly": 2, "quarterly": 3, "semiannual": 6, "annual": 12, "yearly": 12}


def priority_of(item: dict) -> str:
    return item["priority"] if item.get("priority") in PRIORITIES else _PRIORITY_BY_CAT.get(item.get("category") or "", "IMPORTANT")


def confidence_of(status: str, days_overdue: int = 0) -> str:
    if status == "ACTUAL":
        return "CONFIRMED"
    if status in ("DUE", "SCHEDULED"):
        return "HIGH"
    if status == "OVERDUE":
        return "MEDIUM" if days_overdue <= 30 else "LOW"
    if status == "TRIGGER_EXPECTED":
        return "MEDIUM"
    return "LOW"


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
    except (TypeError, ValueError, OverflowError):
        return None


def _f(v) -> float:
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _le_match(item_le: Optional[str], le: Optional[str]) -> bool:
    return le in (None, GROUP) or (item_le or UNASSIGNED) == le


def collection_forecast_date(item: dict, today: date) -> Optional[date]:
    """A scheduled collection is forecastable only on its actual, non-past date."""
    due = _d(item.get("due_date"))
    return due if item.get("status") in CERTAIN_STATUSES and due is not None and due >= today else None


def collection_within(item: dict, today: date, upto: date) -> bool:
    due = collection_forecast_date(item, today)
    return due is not None and due <= upto


def outflow_forecast_date(item: dict, today: date) -> Optional[date]:
    """Overdue obligations remain an immediate cash requirement; unknown dates do not."""
    due = _d(item.get("due_date"))
    return max(today, due) if due is not None else None


def collection_exclusion_reason(item: dict, today: date) -> Optional[str]:
    if collection_forecast_date(item, today) is not None:
        return None
    status, due = item.get("status"), _d(item.get("due_date"))
    if status == "DISPUTED":
        return "DISPUTED"
    if status == "TRIGGER_EXPECTED":
        return "TRIGGER_EXPECTED"
    if status == "OVERDUE" or (due is not None and due < today):
        return "OVERDUE_RECEIVABLE"
    if due is None or status == "UNSCHEDULED":
        return "NO_RELIABLE_DATE"
    return "STATUS_NOT_FORECASTABLE"


def forecast_exclusions(coll: List[dict], today: date) -> Dict[str, Any]:
    """Partition excluded receivables once, including stale DUE/SCHEDULED dates."""
    fields = {"OVERDUE_RECEIVABLE": "overdue_receivables", "NO_RELIABLE_DATE": "undated_receivables",
              "TRIGGER_EXPECTED": "trigger_expected_receivables", "DISPUTED": "disputed_receivables",
              "STATUS_NOT_FORECASTABLE": "other_receivables"}
    amounts, count = {field: 0.0 for field in fields.values()}, 0
    for item in coll:
        reason = collection_exclusion_reason(item, today)
        if reason is not None:
            amounts[fields[reason]] += item["amount"]
            count += 1
    return {**{key: round(value, 2) for key, value in amounts.items()}, "total": round(sum(amounts.values()), 2), "count": count,
            "reason": "Gli scaduti restano crediti da recuperare e sono esclusi dalle entrate previste. Il forecast include solo DUE/SCHEDULED con scadenza valida da oggi; eventi attesi e rate senza data restano separati."}


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
    """ORDER TO CASH: rate aperte dei payment_plans classificate DUE | SCHEDULED | OVERDUE | TRIGGER_EXPECTED | UNSCHEDULED | DISPUTED.
    Eventi commessa (firma, merce pronta, posa) attivano le rate; expected_ready_date → TRIGGER_EXPECTED (mai due_date: fuori dal cash certo)."""
    orders = {o["_id"]: o for o in await db.sales_orders.find({"tenant_id": tenant_id, "deleted_at": None}, {"order_status": 1, "contract_id": 1, "updated_at": 1, "expected_ready_date": 1, "expected_installation_date": 1, "goods_ready_at": 1, "installed_at": 1}).to_list(5000)}
    order_by_contract = {o.get("contract_id"): o for o in orders.values() if o.get("contract_id")}
    out = []

    def _event(due: Optional[date]):
        if due is None:
            return "UNSCHEDULED"
        if due > today:
            return "SCHEDULED"
        return "OVERDUE" if (today - due).days > EVENT_GRACE_DAYS else "DUE"

    for p in plans:
        contract = contracts.get(p.get("contract_id") or "") or {}
        order = orders.get(p.get("sales_order_id") or "") or order_by_contract.get(p.get("contract_id") or "") or {}
        le = p.get("legal_entity_id") or contract.get("legal_entity_id")
        linked = bool(p.get("contract_id") or p.get("sales_order_id"))
        for inst in p.get("installments") or []:
            ist = inst.get("installment_status") or "pending"
            if ist in ("paid", "cancelled"):
                continue
            residual = round(_f(inst.get("amount")) - _f(inst.get("paid_amount")), 2)
            if residual <= 0:
                continue
            trig = str(inst.get("trigger") or "").lower()
            due = _d(inst.get("due_date"))
            expected = None
            status, basis = "UNSCHEDULED", "NO_RELIABLE_DATE"
            if ist == "disputed" or inst.get("disputed"):
                status, basis = "DISPUTED", "CUSTOMER_DISPUTE"
            elif due:
                status, basis = ("OVERDUE" if due < today else ("DUE" if due == today else "SCHEDULED")), "DUE_DATE_KNOWN"
            elif inst.get("due_date"):
                basis = "INVALID_DUE_DATE"
            elif trig in ("signature", "order", "contract_signed") and contract.get("signed_at"):
                due, basis = _d(contract["signed_at"]), "EVENT_CONTRACT_SIGNED"
                status = _event(due)
                if due is None:
                    basis = "CONTRACT_SIGNED_DATE_UNAVAILABLE"
            elif trig in ("goods_ready", "apm", "before_installation"):
                if order.get("order_status") in GOODS_READY_STATUSES:
                    due, basis = _d(order.get("goods_ready_at")), "EVENT_GOODS_READY"
                    status = _event(due)
                    if due is None:
                        basis = "GOODS_READY_DATE_UNAVAILABLE"
                elif _d(order.get("expected_ready_date")):
                    expected, status, basis = _d(order["expected_ready_date"]), "TRIGGER_EXPECTED", "GOODS_EXPECTED_DATE"
                else:
                    basis = "GOODS_READY_NOT_OCCURRED"
            elif trig in ("installation", "installation_completed", "installed", "on_completion"):
                if order.get("order_status") in INSTALLED_STATUSES:
                    due, basis = _d(order.get("installed_at")), "EVENT_INSTALLATION_COMPLETED"
                    status = _event(due)
                    if due is None:
                        basis = "INSTALLATION_DATE_UNAVAILABLE"
                elif _d(order.get("expected_installation_date")):
                    expected, status, basis = _d(order["expected_installation_date"]), "TRIGGER_EXPECTED", "INSTALLATION_EXPECTED_DATE"
                else:
                    basis = "INSTALLATION_NOT_OCCURRED"
            elif trig:
                basis = f"TRIGGER_{trig.upper()}_PENDING"
            days_over = (today - due).days if (due and due < today) else 0
            item = {"payment_plan_id": p["_id"], "contract_id": p.get("contract_id"), "sales_order_id": p.get("sales_order_id") or order.get("_id"), "customer_id": p.get("customer_id"),
                        "installment_ref": inst.get("ref"), "label": inst.get("label"), "trigger": trig or None, "amount": residual, "due_date": due.isoformat() if due else None,
                        "expected_date": expected.isoformat() if expected else None, "days_overdue": days_over, "status": status, "confidence": confidence_of(status, days_over), "date_basis": basis,
                        "legal_entity_id": le, "linked": linked, "contract_number": contract.get("number"), "order_status": order.get("order_status")}
            item["forecast_eligible"] = collection_forecast_date(item, today) is not None
            item["certain"] = item["forecast_eligible"]  # Existing API alias; eligibility is not a payment guarantee.
            item["forecast_exclusion_reason"] = collection_exclusion_reason(item, today)
            out.append(item)
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
                "legal_entity_id": pb.get("legal_entity_id"), "intercompany_pair_id": pb.get("linked_intercompany_pair_id"), "doc_ref": pb.get("doc_ref"), "job_ref": pb.get("job_ref"), "priority": pb.get("priority")}
        item["priority"] = priority_of(item)
        (out if due else unscheduled).append(item)
        if due:
            pay_index[(str(pb.get("label") or "").strip().lower(), due.year, due.month)] += residual
    for f24 in await db.f24.find({"tenant_id": tenant_id, "deleted_at": None, "f24_status": {"$nin": ["paid", "cancelled"]}}).to_list(1000):
        due = _d(f24.get("due_date"))
        item = {"id": f24["_id"], "source": "f24", "label": f24.get("label") or "F24", "supplier": "Erario", "category": "IMPOSTE", "amount": _f(f24.get("amount") or f24.get("total")),
                "due_date": due.isoformat() if due else None, "status": ("OVERDUE" if due and due < today else ("SCHEDULED" if due else "UNSCHEDULED")),
                "days_overdue": (today - due).days if (due and due < today) else 0, "legal_entity_id": f24.get("legal_entity_id"), "intercompany_pair_id": None, "priority": "CRITICAL"}
        if item["amount"] > 0:
            (out if due else unscheduled).append(item)
    fixed = await db.fixed_costs.find({"tenant_id": tenant_id, "deleted_at": None, "active": {"$ne": False}, "is_demo": {"$ne": True}}).to_list(2000)
    personnel = await db.personnel_costs.find({"tenant_id": tenant_id, "deleted_at": None, "active": {"$ne": False}, "is_demo": {"$ne": True}}).to_list(2000)
    monthly_fixed = round(sum(_f(f.get("amount_monthly")) for f in fixed), 2)
    monthly_personnel = round(sum(_f(p.get("monthly_total_cost")) for p in personnel), 2)
    payroll_mismatch = []
    cur = today.replace(day=1)
    while cur <= end:
        for f in fixed:
            amt = _f(f.get("amount_monthly"))
            if amt <= 0 or (f.get("start_date") and _d(f["start_date"]) and _d(f["start_date"]) > cur) or (f.get("end_date") and _d(f["end_date"]) and _d(f["end_date"]) < cur):
                continue
            cs = f.get("cash_schedule") or {}
            months = _CASH_MONTHS.get(str(cs.get("recurrence") or "monthly").lower(), 1)
            if months > 1:  # CASH PROFILE ≠ ECONOMIC: es. assicurazione 440 €/mese economico → 5.280 € cash a marzo
                due_month = int(cs.get("due_month") or 1)
                if (cur.month - due_month) % months != 0:
                    continue
                amt_cash = round(amt * months, 2)
            else:
                amt_cash = amt
            due = cur.replace(day=min(int(cs.get("due_day") or 5), 28))
            if due < today:
                continue
            key = (str(f.get("label") or "").strip().lower(), due.year, due.month)
            if pay_index.get(key):
                reconciled += 1
                continue  # già rappresentato da un payable reale → nessun doppio conteggio
            cat = _FIXED_CAT.get(str(f.get("category") or "").lower(), "ALTRO")
            out.append({"id": f"fixed:{f['_id']}:{due.isoformat()}", "source": "fixed_cost", "label": f.get("label"), "supplier": f.get("supplier"), "category": cat, "amount": amt_cash, "economic_monthly": amt,
                        "due_date": due.isoformat(), "status": "SCHEDULED", "days_overdue": 0, "legal_entity_id": f.get("legal_entity_id"), "intercompany_pair_id": None, "recurring": True, "priority": priority_of({"category": cat, "priority": f.get("priority")})})
        if monthly_personnel > 0:
            by_le = defaultdict(float)
            comps = []  # componenti cash esplicite (netto / F24 / altro) — SUM deve == costo ALL-IN, mai aggiunte sopra
            for p in personnel:
                total = _f(p.get("monthly_total_cost"))
                cc = p.get("cash_components") or []
                if cc and abs(sum(_f(c.get("amount")) for c in cc) - total) < 0.01:
                    for c in cc:
                        comps.append((p.get("legal_entity_id"), c))
                else:
                    if cc:
                        payroll_mismatch.append(p["_id"])
                    by_le[p.get("legal_entity_id")] += total
            pay_day = cur.replace(day=27)
            for le, amt in by_le.items():
                if pay_day < today:
                    continue
                if pay_index.get(("stipendi", pay_day.year, pay_day.month)):
                    reconciled += 1
                    continue
                out.append({"id": f"payroll:{le or UNASSIGNED}:{pay_day.isoformat()}", "source": "personnel_cost", "label": "Stipendi (costo azienda ALL-IN)", "supplier": None, "category": "STIPENDI",
                            "amount": round(amt, 2), "due_date": pay_day.isoformat(), "status": "SCHEDULED", "days_overdue": 0, "legal_entity_id": le, "intercompany_pair_id": None, "recurring": True, "priority": "CRITICAL"})
            for le, c in comps:
                off = int(c.get("month_offset") or 0)
                m0 = (cur + timedelta(days=32 * off)).replace(day=1) if off else cur
                due = m0.replace(day=min(int(c.get("due_day") or 27), 28))
                if due < today or due > end:
                    continue
                lab = str(c.get("label") or "ALTRO").upper()
                cat = "IMPOSTE" if lab in ("F24", "CONTRIBUTI", "CONTRIBUTION") else "STIPENDI"
                out.append({"id": f"payroll:{lab}:{le or UNASSIGNED}:{due.isoformat()}", "source": "personnel_cost", "label": f"Personale · {lab}", "supplier": None, "category": cat, "amount": _f(c.get("amount")),
                            "due_date": due.isoformat(), "status": "SCHEDULED", "days_overdue": 0, "legal_entity_id": le, "intercompany_pair_id": None, "recurring": True, "priority": "CRITICAL"})
        cur = (cur + timedelta(days=32)).replace(day=1)
    committed = []
    for po in await db.purchase_orders.find({"tenant_id": tenant_id, "deleted_at": None, "po_status": {"$nin": ["cancelled", "closed", "paid"]}}).to_list(2000):
        committed.append({"id": po["_id"], "number": po.get("number"), "supplier": po.get("supplier_name"), "amount": _f(po.get("total")), "status": "PURCHASE_COMMITTED",
                          "due_date": po.get("payment_due_date"), "forecastable": bool(po.get("payment_due_date") and po.get("payment_terms"))})
    for it in unscheduled:
        it.setdefault("priority", priority_of(it))
    return {"items": out, "unscheduled": unscheduled, "purchase_committed": committed, "uncategorized_payables": uncategorized, "reconciled_recurring": reconciled,
            "monthly_fixed_costs": monthly_fixed, "monthly_personnel_costs": monthly_personnel, "payroll_cash_components_mismatch": payroll_mismatch}


async def cash_position(db, tenant_id: str, le: Optional[str]) -> Dict[str, Any]:
    """Solo saldi CERTIFICATI (certified_balance + certified_at). Saldo 0 non certificato = BANK_BALANCE_NOT_CONFIGURED. Virtual funds mai sommati."""
    accounts = await db.bank_accounts.find({"tenant_id": tenant_id, "deleted_at": None, "active": {"$ne": False}, "is_virtual": {"$ne": True}}).to_list(200)
    rows, total, as_of, missing, dates = [], 0.0, None, 0, set()
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
            dates.add(cert_at.isoformat())
        else:
            missing += 1
    funds = [{"id": f["_id"], "code": f.get("code"), "label": f.get("label"), "classification": f.get("cash_classification") or VF_CLASS.get(str(f.get("code") or "").lower(), "OTHER"), "balance": f.get("balance")}
             for f in await db.virtual_funds.find({"tenant_id": tenant_id, "deleted_at": None}).to_list(50)]
    status = "COMPLETE" if rows and missing == 0 else ("PARTIAL" if len(rows) > missing else "INCOMPLETE")
    block_reason = "MIXED_CERTIFICATION_DATES" if len(dates) > 1 else None
    block_message = ("I conti hanno saldi certificati a date diverse. La stima aggregata è sospesa per evitare doppi conteggi: certificare i conti alla stessa data."
                     if block_reason else None)
    return {"status": status, "available_cash": round(total, 2) if status != "INCOMPLETE" else None, "as_of": as_of.isoformat() if as_of else None, "accounts": rows,
            "certification_dates": sorted(dates), "forecast_block_reason": block_reason, "forecast_block_message": block_message,
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
    """Certified opening + recorded movements through today, then dated future flows.

    The 13 weeks cover 91 calendar dates, from today through today + 90 inclusive.
    Overdue receivables are excluded; overdue obligations are due immediately.
    """
    as_of = _d(as_of)
    def since_certification(item: dict) -> bool:
        dt = _d(item.get("date"))
        return as_of is not None and dt is not None and as_of < dt <= today
    actual_in = sum(r["amount"] for r in receipts if since_certification(r))
    actual_out = sum(p["amount"] for p in payments_actual if since_certification(p))
    base = round(opening + actual_in - actual_out, 2) if opening is not None and as_of is not None and as_of <= today else None
    inflows_by, outflows_by = defaultdict(float), defaultdict(float)
    for item in coll:
        due = collection_forecast_date(item, today)
        if due is not None:
            inflows_by[due] += item["amount"]
    for item in outf:
        due = outflow_forecast_date(item, today)
        if due is not None:
            outflows_by[due] += item["amount"]
    horizons = {}
    for lab, days in (("today", 0), ("7d", 7), ("14d", 14), ("30d", 30), ("60d", 60), ("90d", 90)):
        upto = today + timedelta(days=days)
        inflow = round(sum(amount for due, amount in inflows_by.items() if due <= upto), 2)
        outflow = round(sum(amount for due, amount in outflows_by.items() if due <= upto), 2)
        horizons[lab] = {"inflows": inflow, "outflows": outflow, "net": round(inflow - outflow, 2), "forecast_closing_cash": round(base + inflow - outflow, 2) if base is not None else None}
    weeks, run, gap_week = [], base, None
    for w in range(FORECAST_DAYS // 7):
        ws, we = today + timedelta(days=7 * w), today + timedelta(days=7 * w + 6)
        inflow = round(sum(amount for due, amount in inflows_by.items() if ws <= due <= we), 2)
        outflow = round(sum(amount for due, amount in outflows_by.items() if ws <= due <= we), 2)
        closing = round(run + inflow - outflow, 2) if run is not None else None
        if closing is not None and closing < 0 and gap_week is None:
            gap_week = f"W{w + 1}"
        weeks.append({"week": f"W{w + 1}", "start": ws.isoformat(), "end": we.isoformat(), "opening": run, "inflows": inflow, "outflows": outflow, "closing": closing, "cash_gap": closing is not None and closing < 0})
        run = closing
    return {"opening_cash": opening, "as_of": as_of.isoformat() if as_of else None, "actual_collections_since_as_of": round(actual_in, 2), "actual_payments_since_as_of": round(actual_out, 2),
            "current_cash_estimate": round(base, 2) if base is not None else None, "horizons": horizons, "weeks": weeks, "first_cash_gap_week": gap_week,
            "forecast_exclusions": forecast_exclusions(coll, today),
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
        if collection_exclusion_reason(c, today) == "OVERDUE_RECEIVABLE":
            due = _d(c.get("due_date"))
            days_overdue = max(c.get("days_overdue") or 0, (today - due).days if due is not None and due < today else 0)
            b["overdue"] += c["amount"]; b["due"] += c["amount"]; b["max_days_overdue"] = max(b["max_days_overdue"], days_overdue)
        elif c["status"] in ("SCHEDULED", "DUE"):
            b["due"] += c["amount"]
            due = collection_forecast_date(c, today)
            if due is not None and (b["next_due"] is None or due.isoformat() < b["next_due"]):
                b["next_due"] = due.isoformat()
        elif c["status"] == "TRIGGER_EXPECTED":
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
    collected_month = round(sum(r["amount"] for r in receipts if r["date"] and ms <= r["date"] <= today), 2)
    collected_ytd = round(sum(r["amount"] for r in receipts if r["date"] and today.replace(month=1, day=1) <= r["date"] <= today), 2)
    paid_month = round(sum(p["amount"] for p in paid_payables if p["date"] and ms <= p["date"] <= today), 2)
    revenue = await revenue_block(db, tenant_id, le, today, contracts, settings)
    margin = await margin_block(db, tenant_id)
    as_of = _d(cash.get("as_of"))
    opening = cash.get("available_cash") if cash["status"] == "COMPLETE" and not cash.get("forecast_block_reason") else None
    calendar = build_calendar(opening, as_of, today, receipts, paid_payables, coll_all, outf_items)
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
    ar_aging = aging([c for c in coll_all if collection_exclusion_reason(c, today) == "OVERDUE_RECEIVABLE"], today)
    ap_aging = aging([o for o in outf_items if o["status"] == "OVERDUE"], today)
    def _due_within(items, days):
        # Open payables include overdue obligations regardless of receivable eligibility.
        return round(sum(i["amount"] for i in items if _d(i.get("due_date")) is not None and _d(i["due_date"]) <= today + timedelta(days=days)), 2)
    supplier_due = {"overdue": ap_aging["total_overdue"], "7d": _due_within([o for o in outf_items if o["source"] in ("payable", "f24")], 7), "30d": _due_within([o for o in outf_items if o["source"] in ("payable", "f24")], 30), "60d": _due_within([o for o in outf_items if o["source"] in ("payable", "f24")], 60)}
    inv_total = revenue["invoiced"]["ytd"]
    conversion = round(collected_ytd / inv_total * 100, 1) if inv_total > 0 else None
    dso = None
    if revenue["invoiced"]["invoice_count"] > 0 and inv_total > 0:
        ar_open = sum(r["due_scheduled"] for r in ar_rows)
        dso = round(ar_open / inv_total * (today - today.replace(month=1, day=1)).days, 0) if ar_open else 0
    outf_month = round(sum(o["amount"] for o in outf_items if outflow_forecast_date(o, today) is not None and outflow_forecast_date(o, today) <= me), 2)
    coll_month_sched = round(sum(c["amount"] for c in coll_all if collection_within(c, today, me)), 2)
    unsched_in = round(sum(c["amount"] for c in coll_all if c["status"] in ("UNSCHEDULED", "TRIGGER_EXPECTED", "DISPUTED")), 2)
    forecast_month = {"revenue": revenue["forecast_month"], "collections": {"actual": collected_month, "scheduled_to_month_end": coll_month_sched, "total_forecast": round(collected_month + coll_month_sched, 2), "kind": "FORECAST"},
                      "outflows": {"actual_paid": paid_month, "scheduled_to_month_end": outf_month, "total_forecast": round(paid_month + outf_month, 2), "kind": "FORECAST"},
                      "cash": {"forecast_month_end": round(avail + coll_month_sched - outf_month, 2) if avail is not None else None, "kind": "FORECAST", "status": calendar["status"]}}
    dq = [
        {"area": "FATTURATO", "ok": revenue["invoiced"]["invoice_count"] > 0, "message": "OK" if revenue["invoiced"]["invoice_count"] else "NO INVOICE DATA AVAILABLE"},
        {"area": "CASSA", "ok": calendar["status"] == "COMPLETE", "message": cash.get("forecast_block_message") or ("OK" if calendar["status"] == "COMPLETE" else f"BANK BALANCE NOT CONFIGURED ({cash['accounts_not_configured']} conti)")},
        {"area": "EXPECTED COLLECTIONS", "ok": not any(c["status"] in ("UNSCHEDULED", "TRIGGER_EXPECTED") for c in coll_all),
         "message": f"{sum(1 for c in coll_all if c['status']=='UNSCHEDULED')} INSTALLMENTS UNSCHEDULED · {sum(1 for c in coll_all if c['status']=='TRIGGER_EXPECTED')} TRIGGER EXPECTED · {sum(1 for c in coll_all if not c['linked'])} piani non collegati a contratto/ordine"},
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
               "message": f"registry REALE {structure['fixed_cost_registry']['annual_total']} € (demo esclusi {structure['fixed_cost_registry']['demo_annual_total']} €) vs PO reference {sus.PO_REFERENCE_ANNUAL_FIXED_COST} € → FIXED_COST_RECONCILIATION = {structure['fixed_cost_registry']['reconciliation_status']}"})
    dq.append({"area": "PRICING SUSTAINABILITY", "ok": structure["plan"]["data_quality"] == "COMPLETE", "message": f"{structure['plan']['data_quality']}" + (f" (mancano: {', '.join(structure['plan']['missing'])})" if structure["plan"]["missing"] else "")})
    return {"engine_version": CFO_ENGINE_VERSION, "today": today.isoformat(), "legal_entity_id": le or GROUP, "settings": settings,
            "kpi_row1": {"invoiced_month": revenue["invoiced"]["month"], "invoiced_status": revenue["invoiced"]["data_status"], "collected_month": collected_month, "paid_month": paid_month,
                         "available_cash": avail, "cash_status": calendar["status"], "sold_month": revenue["sold"]["month"],
                         "certified_cash": cash.get("available_cash"), "current_cash_estimate": avail, "cash_as_of": cash.get("as_of"),
                         "forecast_block_reason": cash.get("forecast_block_reason"), "forecast_block_message": cash.get("forecast_block_message"),
                         "actual_collections_since_as_of": calendar["actual_collections_since_as_of"], "actual_payments_since_as_of": calendar["actual_payments_since_as_of"]},
            "kpi_row2": {"revenue_target": revenue["target"], "collection_target": {"monthly_collection_target": settings.get("monthly_collection_target"), "actual": collected_month,
                                                                                    "percent_reached": round(collected_month / settings["monthly_collection_target"] * 100, 1) if settings.get("monthly_collection_target") else None},
                         "cash_gap_30d": gap_30, "minimum_cash_requirement_30d": min_req, "forecast_cash_month_end": forecast_month["cash"]["forecast_month_end"]},
            "kpi_row3": {"break_even_revenue_monthly": be_rev, "monthly_structure_costs": monthly_structure, "margin": margin, "distance_to_break_even": round(be_rev - revenue["invoiced"]["month"], 2) if be_rev is not None else None,
                         "minimum_cash_reserve": reserve, "margin_of_safety_cash_30d": safety, "cash_safety_status": cash_safety_status,
                         "note": "Break-even fatturato (struttura/margine) e fabbisogno di cassa sono indicatori diversi"},
            "cash_calendar": calendar["horizons"], "weeks_13": calendar["weeks"], "first_cash_gap_week": calendar["first_cash_gap_week"], "cash_position": cash,
            "forecast_exclusions": calendar["forecast_exclusions"],
            "cash_flow_status": calendar["status"], "unscheduled_inflows": unsched_in, "unscheduled_outflows": round(sum(o["amount"] for o in unsched_out), 2),
            "receivables": {"rows": ar_rows[:50], "total_residual": round(sum(r["residual"] for r in ar_rows), 2), "total_due_scheduled": round(sum(r["due_scheduled"] for r in ar_rows), 2), "aging": ar_aging},
            "payables": {"supplier_due": supplier_due, "aging": ap_aging, "items_30d": sorted([o for o in outf_items if _d(o["due_date"]) and _d(o["due_date"]) <= today + timedelta(days=30)], key=lambda o: o["due_date"])[:50],
                         "unscheduled": unsched_out[:50], "purchase_committed": outf_raw["purchase_committed"][:50], "intercompany_eliminated": ic_elim_out},
            "collections_30d": sorted([c for c in coll_all if collection_within(c, today, today + timedelta(days=30))], key=lambda c: c["due_date"])[:50],
            "collections_pending": [c for c in coll_all if c["status"] in ("TRIGGER_EXPECTED", "UNSCHEDULED", "DISPUTED")][:50],
            "revenue": revenue, "collected_ytd": collected_ytd, "cash_conversion_percent": conversion, "dso": dso if dso is not None else "NOT_AVAILABLE",
            "forecast_month_end": forecast_month, "data_quality": dq, "alerts": alerts, "next_actions": actions, "structure_coverage": structure["plan"], "fixed_cost_registry": structure["fixed_cost_registry"],
            "email_go_live": "BLOCKED_BY_CONFIGURATION"}


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
    if cash.get("forecast_block_reason"):
        actions.append({"code": cash["forecast_block_reason"], "message": cash["forecast_block_message"]})
    elif calendar["status"] != "COMPLETE":
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
