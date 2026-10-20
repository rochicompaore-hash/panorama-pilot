"""CASH CONVERSION & DEBT COVERAGE ENGINE V1 — Cash Command Center (backend source of truth).
Regole PO: TOTAL RECEIVABLES ≠ AVAILABLE LIQUIDITY · solo DUE/SCHEDULED/OVERDUE entrano nel forecast certo · TRIGGER_EXPECTED separato ·
cassa solo da saldi certificati · riserva non configurata → SAFETY GAP = NOT_AVAILABLE · nessuna azione automatica."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.services import cfo_engine as cfo
from app.services.cfo_engine import CERTAIN_STATUSES, PRIORITIES, _d, _f, _le_match, priority_of

CASH_ENGINE_VERSION = "cash_engine_v1_2026_11"
HORIZONS = (("today", 0), ("3d", 3), ("7d", 7), ("14d", 14), ("30d", 30), ("60d", 60), ("90d", 90), ("13w", 91))
LADDER = (("7d", 7), ("14d", 14), ("30d", 30), ("60d", 60), ("90d", 90))
MANDATORY = ("CRITICAL", "IMPORTANT")
TERMS_PRESETS = {"50/50": [("ORDER", 50), ("GOODS_READY", 50)], "40/60": [("ORDER", 40), ("GOODS_READY", 60)], "30/70": [("ORDER", 30), ("GOODS_READY", 70)],
                 "50/40/10": [("ORDER", 50), ("GOODS_READY", 40), ("INSTALLATION", 10)]}
STEP_DAYS = {"ORDER": 0, "SIGNATURE": 0, "TECHNICAL_SURVEY": 10, "SURVEY": 10, "GOODS_READY": None, "APM": None, "INSTALLATION": None, "ON_COMPLETION": None, "FINANCING": 30}
DEFAULT_LEAD_DAYS = 60
INSTALL_AFTER_READY_DAYS = 15
STATUS_COLOR = {"ACTUAL": "GREEN", "DUE": "GREEN", "SCHEDULED": "GREEN", "TRIGGER_EXPECTED": "YELLOW", "OVERDUE": "RED", "UNSCHEDULED": "GREY", "DISPUTED": "GREY"}


def _within(d, upto: date) -> bool:
    dd = _d(d)
    return dd is not None and dd <= upto


def _fmt(v) -> str:
    return "n/d" if v is None else f"€{v:,.0f}".replace(",", ".")


# ---------------------------------------------------------------------------
# forecast
# ---------------------------------------------------------------------------
def daily_projection(base: Optional[float], today: date, coll: List[dict], outf: List[dict], days: int = 91) -> Dict[str, Any]:
    """Serie giornaliera OPENING + incassi certi − uscite = PROJECTED. Overdue/scaduti conteggiati a oggi (incasso/pagamento atteso subito)."""
    inflow_by, outflow_by = defaultdict(float), defaultdict(float)
    for c in coll:
        if c["status"] in CERTAIN_STATUSES and c.get("due_date"):
            inflow_by[max(today, _d(c["due_date"]))] += c["amount"]
    for o in outf:
        if o.get("due_date"):
            outflow_by[max(today, _d(o["due_date"]))] += o["amount"]
    series, run, lowest, first_neg = [], base, None, None
    for i in range(days):
        d = today + timedelta(days=i)
        inflow, outflow = round(inflow_by.get(d, 0.0), 2), round(outflow_by.get(d, 0.0), 2)
        run = round(run + inflow - outflow, 2) if run is not None else None
        series.append({"date": d.isoformat(), "inflows": inflow, "outflows": outflow, "projected_cash": run})
        if run is not None:
            if lowest is None or run < lowest["amount"]:
                lowest = {"date": d.isoformat(), "amount": run}
            if run < 0 and first_neg is None:
                first_neg = d.isoformat()
    return {"series": series, "lowest_cash_point": lowest, "first_negative_date": first_neg, "status": "COMPLETE" if base is not None else "INCOMPLETE"}


def horizons(base: Optional[float], today: date, coll: List[dict], outf: List[dict]) -> Dict[str, Any]:
    out = {}
    for lab, days in HORIZONS:
        upto = today + timedelta(days=days)
        certain = round(sum(c["amount"] for c in coll if c["status"] in CERTAIN_STATUSES and _within(c["due_date"], upto)), 2)
        trig = round(sum(c["amount"] for c in coll if c["status"] == "TRIGGER_EXPECTED" and _within(c.get("expected_date"), upto)), 2)
        outflow = round(sum(o["amount"] for o in outf if _within(o["due_date"], upto)), 2)
        mandatory = round(sum(o["amount"] for o in outf if _within(o["due_date"], upto) and priority_of(o) in MANDATORY), 2)
        proj = round(base + certain - outflow, 2) if base is not None else None
        out[lab] = {"days": days, "opening_cash": base, "expected_collections": certain, "trigger_expected_collections": trig, "expected_outflows": outflow, "mandatory_outflows": mandatory,
                    "projected_cash": proj, "projected_cash_with_triggers": round(proj + trig, 2) if proj is not None else None,
                    "operating_cash_gap": round(min(0.0, proj), 2) if proj is not None else None}
    return out


def debt_ladder(outf: List[dict], today: date) -> Dict[str, Any]:
    out = {}
    for lab, days in LADDER:
        upto = today + timedelta(days=days)
        items = [o for o in outf if _within(o["due_date"], upto)]
        by_p = {p: round(sum(o["amount"] for o in items if priority_of(o) == p), 2) for p in PRIORITIES}
        by_cat = defaultdict(float)
        for o in items:
            by_cat[o.get("category") or "ALTRO"] += o["amount"]
        out[lab] = {"total": round(sum(o["amount"] for o in items), 2), "mandatory": round(by_p["CRITICAL"] + by_p["IMPORTANT"], 2), "by_priority": by_p, "by_category": {k: round(v, 2) for k, v in sorted(by_cat.items())}, "count": len(items)}
    return out


def cash_runway(base: Optional[float], today: date, outf: List[dict], days: int = 365) -> Dict[str, Any]:
    """Giorni sostenibili con le sole uscite previste e ZERO nuovi incassi."""
    if base is None:
        return {"days": None, "status": "INCOMPLETE"}
    run, by = base, defaultdict(float)
    for o in outf:
        if o.get("due_date"):
            by[max(today, _d(o["due_date"]))] += o["amount"]
    for i in range(days):
        run -= by.get(today + timedelta(days=i), 0.0)
        if run < 0:
            return {"days": i, "exhaustion_date": (today + timedelta(days=i)).isoformat(), "status": "LIMITED" if i > 30 else "CRITICAL"}
    return {"days": days, "exhaustion_date": None, "status": "OK", "note": f"> {days} giorni con le uscite previste"}


def liquidity_coverage(base: Optional[float], h30: Dict[str, Any]) -> Dict[str, Any]:
    if base is None:
        return {"ratio": None, "status": "INCOMPLETE", "available": None, "mandatory_outflows_30d": h30["mandatory_outflows"]}
    avail = round(base + h30["expected_collections"], 2)
    mand = h30["mandatory_outflows"]
    ratio = round(avail / mand, 3) if mand > 0 else None
    status = "NO_MANDATORY_OUTFLOWS" if ratio is None else ("SAFE" if ratio >= 1.2 else ("TIGHT" if ratio >= 1.0 else ("AT_RISK" if ratio >= 0.8 else "CRITICAL")))
    return {"ratio": ratio, "percent": round(ratio * 100, 1) if ratio is not None else None, "status": status, "available": avail, "mandatory_outflows_30d": mand,
            "debt_coverage_gap": round(max(0.0, mand - avail), 2)}


def cash_gap(base: Optional[float], h: Dict[str, Any], reserve: Optional[float]) -> Dict[str, Any]:
    """OPERATING = cassa + incassi certi − uscite obbligatorie. SAFETY = OPERATING − riserva (NOT_AVAILABLE se riserva non configurata)."""
    if base is None:
        return {"operating_cash_position": None, "operating_cash_gap": None, "safety_cash_gap": None, "reserve_status": "NOT_CONFIGURED" if reserve is None else "CONFIGURED", "status": "INCOMPLETE"}
    op = round(base + h["expected_collections"] - h["mandatory_outflows"], 2)
    out = {"operating_cash_position": op, "operating_cash_gap": round(abs(min(0.0, op)), 2), "status": "GAP" if op < 0 else "SURPLUS", "reserve": reserve}
    if reserve is None:
        out.update({"safety_cash_gap": "NOT_AVAILABLE", "reserve_status": "NOT_CONFIGURED", "reserve_message": "Riserva minima di sicurezza non configurata."})
    else:
        out.update({"safety_cash_gap": round(abs(min(0.0, op - reserve)), 2), "safety_cash_position": round(op - reserve, 2), "reserve_status": "CONFIGURED"})
    return out


def receivable_quality(coll: List[dict], today: date) -> Dict[str, Any]:
    by = {s: 0.0 for s in ("DUE", "OVERDUE", "SCHEDULED", "TRIGGER_EXPECTED", "UNSCHEDULED", "DISPUTED")}
    for c in coll:
        by[c["status"]] = by.get(c["status"], 0.0) + c["amount"]
    total = round(sum(by.values()), 2)
    c7 = round(sum(c["amount"] for c in coll if c["status"] in CERTAIN_STATUSES and _within(c["due_date"], today + timedelta(days=7))), 2)
    c30 = round(sum(c["amount"] for c in coll if c["status"] in CERTAIN_STATUSES and _within(c["due_date"], today + timedelta(days=30))), 2)
    return {"total_receivables": total, "by_status": {k: round(v, 2) for k, v in by.items()}, "collectible_7d": c7, "collectible_30d": c30,
            "not_yet_monetizable": round(by["TRIGGER_EXPECTED"] + by["UNSCHEDULED"] + by["DISPUTED"], 2), "colors": STATUS_COLOR,
            "rule": "TOTAL RECEIVABLES ≠ AVAILABLE LIQUIDITY — solo crediti con due_date o trigger operativo avvenuto entrano nel forecast."}


def collection_priority(coll: List[dict], customers: Dict[str, dict], today: date) -> List[dict]:
    """DA INCASSARE ORA: OVERDUE → DUE → GOODS READY (SCHEDULED a breve) → GOODS EXPECTED → importo."""
    rank = {"OVERDUE": 0, "DUE": 1, "SCHEDULED": 2, "TRIGGER_EXPECTED": 3, "UNSCHEDULED": 4, "DISPUTED": 5}
    rows = []
    for c in coll:
        cu = customers.get(c.get("customer_id")) or {}
        name = " ".join(x for x in (cu.get("first_name"), cu.get("last_name")) if x) or cu.get("company_name") or cu.get("name") or "Cliente"
        if c["status"] == "OVERDUE":
            why = f"SCADUTO da {c['days_overdue']} gg"
        elif c["status"] == "DUE":
            why = "DUE OGGI" if c.get("date_basis") == "DUE_DATE_KNOWN" else ("MERCE PRONTA" if "GOODS" in (c.get("date_basis") or "") else "ESIGIBILE")
        elif c["status"] == "SCHEDULED":
            why = f"scadenza {c['due_date']}" + (" · merce pronta" if "GOODS" in (c.get("date_basis") or "") else "")
        elif c["status"] == "TRIGGER_EXPECTED":
            why = f"MERCE IN ARRIVO {max(0, (_d(c['expected_date']) - today).days)} gg" if "GOODS" in (c.get("date_basis") or "") else f"posa prevista {c['expected_date']}"
        else:
            why = "senza data attendibile" if c["status"] == "UNSCHEDULED" else "CONTESTATO"
        rows.append({**c, "customer_name": name, "reason": why, "color": STATUS_COLOR[c["status"]], "rank": rank[c["status"]]})
    rows.sort(key=lambda r: (r["rank"], -(r.get("days_overdue") or 0), -r["amount"]))
    return rows


def stress_scenario(base: Optional[float], today: date, coll: List[dict], outf: List[dict], delay_days: int = 7) -> Dict[str, Any]:
    """SCENARIO CASSA VUOTA: no nuove vendite · incassi certi ritardati di N gg · saldi cliente TRIGGER_EXPECTED non incassati · uscite non rinviabili."""
    shifted = []
    for c in coll:
        if c["status"] in CERTAIN_STATUSES and c.get("due_date"):
            shifted.append({**c, "due_date": (max(today, _d(c["due_date"])) + timedelta(days=delay_days)).isoformat()})
    proj = daily_projection(base, today, shifted, outf)
    h = horizons(base, today, shifted, outf)
    return {"assumptions": ["NO_NEW_SALES", f"EXPECTED_COLLECTIONS_DELAY_{delay_days}_DAYS", "CUSTOMER_BALANCE_TRIGGER_NOT_PAID", "SUPPLIER_PAYMENTS_NOT_DEFERRED"],
            "cash_7d": h["7d"]["projected_cash"], "cash_30d": h["30d"]["projected_cash"], "cash_gap_30d": h["30d"]["operating_cash_gap"], "lowest_cash_point": proj["lowest_cash_point"], "first_negative_date": proj["first_negative_date"], "kind": "SCENARIO"}


# ---------------------------------------------------------------------------
# job cash position
# ---------------------------------------------------------------------------
def exposure_level(peak: Optional[float], net: float) -> Optional[str]:
    if peak is None:
        return None
    if peak <= 0:
        return "LOW"
    ratio = peak / net if net > 0 else 1
    return "HIGH" if (ratio >= 0.30 or peak > 8000) else ("MEDIUM" if ratio >= 0.15 else "LOW")


async def job_cash_positions(db, tenant_id: str, le: Optional[str], contracts: Dict[str, dict], receipts: List[dict], coll: List[dict], today: date) -> Dict[str, Any]:
    """Per commessa: VALORE ORDINE − INCASSATO − DA INCASSARE · PAGATO FORNITORI/COSTI DIRETTI · POSIZIONE CASH · PEAK CASH EXPOSURE."""
    from app.services.sustainability_engine import quote_contribution
    paid_by_job = defaultdict(float)
    async for pb in db.payables.find({"tenant_id": tenant_id, "deleted_at": None, "job_ref": {"$ne": None}}, {"job_ref": 1, "amount_paid": 1}):
        paid_by_job[pb["job_ref"]] += _f(pb.get("amount_paid"))
    orders = {}
    async for o in db.sales_orders.find({"tenant_id": tenant_id, "deleted_at": None, "contract_id": {"$ne": None}}, {"contract_id": 1, "order_status": 1, "expected_ready_date": 1, "number": 1}):
        orders[o["contract_id"]] = o
    async for po in db.purchase_orders.find({"tenant_id": tenant_id, "deleted_at": None, "po_status": "paid"}, {"linked_sales_orders": 1, "total": 1}):
        for so in po.get("linked_sales_orders") or []:
            paid_by_job[so] += _f(po.get("total"))
    rec_by, coll_by = defaultdict(float), defaultdict(list)
    for r in receipts:
        if r.get("contract_id"):
            rec_by[r["contract_id"]] += r["amount"]
    for c in coll:
        if c.get("contract_id"):
            coll_by[c["contract_id"]].append(c)
    qids = [c.get("quote_id") for c in contracts.values() if c.get("quote_id")]
    quotes = {q["_id"]: q for q in await db.quotes.find({"_id": {"$in": qids}}, {"financial_snapshot": 1, "subtotal": 1, "lines": 1, "logistics_services": 1, "payment_schedule": 1}).to_list(5000)} if qids else {}
    rows, absorbed = [], 0.0
    for cid, c in contracts.items():
        if c.get("contract_status") != "signed" or not _le_match(c.get("legal_entity_id"), le):
            continue
        eco = cfo.contract_economics(c)
        if not eco["complete"]:
            continue
        order = orders.get(cid) or {}
        if order.get("order_status") in ("closed", "cancelled"):
            continue
        q = quotes.get(c.get("quote_id") or "")
        qc = quote_contribution(q) if q else None
        direct = qc["direct_costs"] if qc and qc["complete"] else None
        collected = round(rec_by[cid], 2)
        paid = round(paid_by_job[cid] + paid_by_job[order.get("_id") or ""], 2)
        position = round(collected - paid, 2)
        open_items = coll_by[cid]
        to_collect = round(sum(x["amount"] for x in open_items), 2)
        nxt = sorted([x for x in open_items if x.get("due_date") or x.get("expected_date")], key=lambda x: (x.get("due_date") or x.get("expected_date")))
        nxt = nxt[0] if nxt else None
        peak = None if direct is None else round(max(0.0, direct - collected), 2)
        if position < 0:
            absorbed += -position
        rows.append({"contract_id": cid, "contract_number": c.get("number"), "customer_id": c.get("customer_id"), "order_status": order.get("order_status"), "order_number": order.get("number"),
                     "order_value": eco["total"], "net_value": eco["net"], "collected": collected, "to_collect": to_collect, "supplier_paid": paid, "direct_costs_expected": direct,
                     "direct_costs_unpaid": round(max(0.0, direct - paid), 2) if direct is not None else None, "cash_position": position,
                     "peak_cash_exposure": peak, "exposure_level": exposure_level(peak, eco["net"]),
                     "next_cash_event": nxt and {"status": nxt["status"], "amount": nxt["amount"], "date": nxt.get("due_date") or nxt.get("expected_date"), "label": nxt.get("label"), "basis": nxt.get("date_basis"), "color": STATUS_COLOR[nxt["status"]]},
                     "financially_negative_today": position < 0})
    rows.sort(key=lambda r: ((r["next_cash_event"] or {}).get("date") or "9999", -r["to_collect"]))
    return {"rows": rows, "count": len(rows), "cash_absorbed_by_open_jobs": round(absorbed, 2), "total_to_collect": round(sum(r["to_collect"] for r in rows), 2),
            "soon": [r for r in rows if r["next_cash_event"] and r["next_cash_event"]["date"] <= (today + timedelta(days=30)).isoformat()][:20]}


# ---------------------------------------------------------------------------
# quote: expected cash exposure + terms simulator
# ---------------------------------------------------------------------------
def _schedule_from_quote(q: dict) -> List[tuple]:
    sch = q.get("payment_schedule") or []
    out = [(str(s.get("step") or "ORDER").upper(), float(s["percent"])) for s in sch if s.get("percent") is not None]
    return out or TERMS_PRESETS["50/50"]


def simulate_terms(*, gross_total: float, net_total: float, direct_costs: Optional[float], splits: List[tuple], lead_days: Optional[int], today: Optional[date] = None) -> Dict[str, Any]:
    """Cliente paga il lordo per step; fornitori/costi diretti pagati entro merce pronta. PEAK = max(0, costi diretti − incassi cumulati prima della merce pronta)."""
    today = today or datetime.now(timezone.utc).date()
    lead = int(lead_days or DEFAULT_LEAD_DAYS)
    days_of = {**STEP_DAYS, "GOODS_READY": lead, "APM": lead, "INSTALLATION": lead + INSTALL_AFTER_READY_DAYS, "ON_COMPLETION": lead + INSTALL_AFTER_READY_DAYS}
    steps, cum = [], 0.0
    for step, pct in splits:
        amt = round(gross_total * pct / 100, 2)
        cum = round(cum + amt, 2)
        steps.append({"step": step, "percent": pct, "amount": amt, "cumulative": cum, "day": days_of.get(step, lead)})
    deposit = round(sum(s["amount"] for s in steps if s["day"] == 0), 2)
    before_ready = round(sum(s["amount"] for s in steps if s["day"] < lead), 2)
    peak = None if direct_costs is None else round(max(0.0, direct_costs - before_ready), 2)
    positive_day, positive_step = None, None
    if direct_costs is not None:
        for s in sorted(steps, key=lambda s: s["day"]):
            if s["cumulative"] >= direct_costs:
                positive_day, positive_step = s["day"], s["step"]
                break
    return {"splits": steps, "deposit_received": deposit, "collected_before_goods_ready": before_ready, "direct_costs": direct_costs, "peak_cash_exposure": peak,
            "exposure_level": exposure_level(peak, net_total), "cash_positive_day": positive_day, "cash_positive_step": positive_step,
            "cash_positive_date": (today + timedelta(days=positive_day)).isoformat() if positive_day is not None else None, "working_capital_requirement": peak, "lead_days": lead, "kind": "SIMULATION"}


def quote_cash_exposure(q: dict, today: Optional[date] = None) -> Dict[str, Any]:
    from app.services.sustainability_engine import quote_contribution
    qc = quote_contribution(q)
    gross = _f(q.get("total")) or round(_f(qc["net_revenue_ex_vat"]) * 1.22, 2)
    sim = simulate_terms(gross_total=gross, net_total=qc["net_revenue_ex_vat"], direct_costs=qc["direct_costs"] if qc["complete"] else None, splits=_schedule_from_quote(q), lead_days=q.get("delivery_lead_time_days"), today=today)
    return {**sim, "direct_margin_percent": qc["contribution_margin_percent"], "payment_terms": q.get("payment_terms_code") or q.get("payment_terms"), "gross_total": round(gross, 2), "kind": "EXPECTED"}


# ---------------------------------------------------------------------------
# next actions
# ---------------------------------------------------------------------------
def next_actions(h: Dict[str, Any], gap: Dict[str, Any], lowest: Optional[dict], prio: List[dict], outf: List[dict], jobs: Dict[str, Any], cash_status: str, today: date) -> List[dict]:
    acts = []
    if cash_status != "COMPLETE":
        acts.append({"code": "CONFIGURE_BANK_BALANCE", "severity": "critical", "message": "Certificare il saldo banca: senza saldo certificato CASH FORECAST = INCOMPLETE (saldo 0 non significa cassa 0)."})
    for lab in ("7d", "30d"):
        p = h[lab]["projected_cash"]
        if p is not None and p < 0:
            acts.append({"code": f"CASH_DEFICIT_{lab.upper()}", "severity": "critical", "message": f"Nei prossimi {h[lab]['days']} giorni è previsto un deficit di {_fmt(-p)}."})
            break
    if gap.get("reserve_status") == "NOT_CONFIGURED":
        acts.append({"code": "RESERVE_NOT_CONFIGURED", "severity": "medium", "message": "Riserva minima di sicurezza non configurata: SAFETY CASH GAP = NOT_AVAILABLE."})
    if lowest and lowest["amount"] < 0:
        acts.append({"code": "LOWEST_CASH_POINT", "severity": "critical", "message": f"Punto minimo di liquidità previsto il {lowest['date']}: {_fmt(lowest['amount'])}."})
    recoverable = [r for r in prio if r["status"] in ("OVERDUE", "DUE", "SCHEDULED", "TRIGGER_EXPECTED")][:3]
    if recoverable:
        acts.append({"code": "COLLECTION_PRIORITY", "severity": "high", "message": "Priorità recupero: " + " · ".join(f"{r['customer_name']} {_fmt(r['amount'])} ({r['reason']})" for r in recoverable),
                     "items": [{"customer_id": r["customer_id"], "customer_name": r["customer_name"], "amount": r["amount"], "status": r["status"], "reason": r["reason"]} for r in recoverable]})
    apm = [j for j in jobs["rows"] if j["next_cash_event"] and j["next_cash_event"]["status"] == "TRIGGER_EXPECTED"][:2]
    for j in apm:
        acts.append({"code": "ACCELERATE_APM", "severity": "medium", "message": f"Accelerare APM/merce pronta commessa {j['contract_number']}: sblocca {_fmt(j['next_cash_event']['amount'])} (previsto {j['next_cash_event']['date']})."})
    crit = sorted([o for o in outf if priority_of(o) == "CRITICAL" and _within(o["due_date"], today + timedelta(days=7))], key=lambda o: -o["amount"])[:2]
    for o in crit:
        acts.append({"code": "CRITICAL_PAYMENT_DUE", "severity": "high", "message": f"Uscita CRITICAL {o['label']} {_fmt(o['amount'])} il {o['due_date']}."})
    return acts


# ---------------------------------------------------------------------------
# command center
# ---------------------------------------------------------------------------
async def command_center(db, tenant_id: str, le: Optional[str] = None, today: Optional[date] = None) -> Dict[str, Any]:
    today = today or datetime.now(timezone.utc).date()
    le = None if le in (None, "", "all", cfo.GROUP) else le
    settings = await cfo.load_settings(db, tenant_id, le)
    contracts = await cfo._contracts(db, tenant_id)
    plans = await cfo._plans(db, tenant_id)
    ic = await cfo.reconciled_ic_pairs(db, tenant_id)
    canon = await cfo.cash_receipts_canonical(db, tenant_id, contracts, plans)
    receipts = [r for r in canon["receipts"] if _le_match(r.get("legal_entity_id"), le)]
    coll = [c for c in await cfo.expected_collections(db, tenant_id, contracts, plans, today) if _le_match(c.get("legal_entity_id"), le)]
    outf_raw = await cfo.expected_outflows(db, tenant_id, today)
    outf, _ = cfo._ic_eliminate([o for o in outf_raw["items"] if _le_match(o.get("legal_entity_id"), le)], le, ic["pairs"])
    unsched_out = [o for o in outf_raw["unscheduled"] if _le_match(o.get("legal_entity_id"), le)]
    cash = await cfo.cash_position(db, tenant_id, le)
    paid_payables = [{"amount": _f(p.get("amount_paid")), "date": _d(p.get("paid_at") or p.get("updated_at"))} for p in
                     await db.payables.find({"tenant_id": tenant_id, "deleted_at": None, "payable_status": "paid"}).to_list(5000) if _le_match(p.get("legal_entity_id"), le)]
    as_of = _d(cash.get("as_of"))
    opening = cash.get("available_cash")
    base = None
    if opening is not None:
        base = round(opening + sum(r["amount"] for r in receipts if as_of and r["date"] and r["date"] > as_of) - sum(p["amount"] for p in paid_payables if as_of and p["date"] and p["date"] > as_of), 2)
    reserve = _f(settings.get("minimum_cash_reserve")) if settings.get("minimum_cash_reserve") is not None else None
    h = horizons(base, today, coll, outf)
    proj = daily_projection(base, today, coll, outf)
    ladder = debt_ladder(outf, today)
    customers = {c["_id"]: c for c in await db.customers.find({"tenant_id": tenant_id, "deleted_at": None}, {"first_name": 1, "last_name": 1, "company_name": 1, "name": 1}).to_list(10000)}
    prio = collection_priority(coll, customers, today)
    jobs = await job_cash_positions(db, tenant_id, le, contracts, receipts, coll, today)
    quality = receivable_quality(coll, today)
    gap7, gap30 = cash_gap(base, h["7d"], reserve), cash_gap(base, h["30d"], reserve)
    cov = liquidity_coverage(base, h["30d"])
    payables_30 = ladder["30d"]["total"]
    cash_health = "INCOMPLETE" if base is None else ("CRITICAL" if (h["7d"]["projected_cash"] < 0 or cov["status"] == "CRITICAL") else ("AT_RISK" if (h["30d"]["projected_cash"] < 0 or cov["status"] == "AT_RISK") else ("TIGHT" if cov["status"] == "TIGHT" else "SAFE")))
    from app.services import sustainability_engine as sus
    structure = await sus.overview(db, tenant_id, le, today)
    nwc = {"customer_receivables": quality["total_receivables"], "work_in_progress_cash": jobs["cash_absorbed_by_open_jobs"], "supplier_payables": round(sum(o["amount"] for o in outf if o["source"] in ("payable",)) + sum(o["amount"] for o in unsched_out), 2)}
    nwc["net_working_capital"] = round(nwc["customer_receivables"] + nwc["work_in_progress_cash"] - nwc["supplier_payables"], 2)
    due_pay = sorted([o for o in outf if _within(o["due_date"], today + timedelta(days=30))], key=lambda o: (0 if priority_of(o) == "CRITICAL" else 1 if priority_of(o) == "IMPORTANT" else 2, o["due_date"]))
    return {"engine_version": CASH_ENGINE_VERSION, "today": today.isoformat(), "legal_entity_id": le or cfo.GROUP,
            "situation_today": {"cash_today": base, "cash_status": cash["status"], "cash_as_of": cash.get("as_of"), "accounts_not_configured": cash["accounts_not_configured"],
                                "bank_balance_message": None if cash["status"] == "COMPLETE" else "BANK_BALANCE_NOT_CONFIGURED — saldo 0 non certificato ≠ cassa 0",
                                "collections_7d": h["7d"]["expected_collections"], "outflows_7d": h["7d"]["expected_outflows"], "cash_gap_7d": gap7, "projected_cash_7d": h["7d"]["projected_cash"],
                                "collections_30d": h["30d"]["expected_collections"], "outflows_30d": h["30d"]["expected_outflows"], "projected_cash_30d": h["30d"]["projected_cash"], "cash_gap_30d": gap30,
                                "total_receivables": quality["total_receivables"], "collectible_7d": quality["collectible_7d"], "collectible_30d": quality["collectible_30d"], "debt_position_30d": payables_30,
                                "lowest_cash_point": proj["lowest_cash_point"], "first_negative_date": proj["first_negative_date"], "cash_health": cash_health, "runway": cash_runway(base, today, outf),
                                "liquidity_coverage": cov, "reserve": reserve, "reserve_status": "CONFIGURED" if reserve is not None else "NOT_CONFIGURED"},
            "horizons": h, "daily_projection": proj["series"], "weeks_13": cfo.build_calendar(opening, as_of, today, receipts, paid_payables, coll, outf)["weeks"],
            "receivable_quality": quality, "collection_priority": prio[:30],
            "debt": {"ladder": ladder, "due_30d": due_pay[:60], "unscheduled": unsched_out[:30], "unscheduled_total": round(sum(o["amount"] for o in unsched_out), 2), "priorities": list(PRIORITIES),
                     "categories": ["STIPENDI", "F24", "FORNITORI", "AFFITTI", "LEASING", "FINANZIAMENTI", "ASSICURAZIONI", "IMPOSTE", "ALTRO"], "payroll_cash_components_mismatch": outf_raw["payroll_cash_components_mismatch"]},
            "jobs": jobs, "working_capital": nwc, "stress_scenario": stress_scenario(base, today, coll, outf),
            "structure": {"annual_fixed_costs_real": structure["fixed_cost_registry"]["annual_total"], "kpi_status": structure["plan"]["kpi_status"], "structure_coverage_percent": structure["plan"]["structure_coverage_percent"],
                          "secured_contribution_ytd": structure["plan"]["secured_contribution_ytd"], "structure_residual": structure["plan"]["structure_residual"], "reconciliation": structure["fixed_cost_registry"]["reconciliation_status"],
                          "note": "STRUCTURE COVERED ≠ CASH SAFE"},
            "next_actions": next_actions(h, gap30, proj["lowest_cash_point"], prio, outf, jobs, cash["status"], today),
            "principles": ["NO_FALSE_LIQUIDITY", "RECEIVABLES_ARE_NOT_CASH", "CERTIFIED_CASH_ONLY", "TRIGGER_EXPECTED_SEPARATE", "NO_AUTOMATIC_EXECUTION"], "email_module": "BLOCKED_BY_CONFIGURATION"}
