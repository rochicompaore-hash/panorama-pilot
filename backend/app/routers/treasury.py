"""M7.TREASURY router + service inline — tesoreria intelligente."""
from __future__ import annotations
import hashlib
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request
from app.db import get_db
from app.deps import get_current_user, require_permission, require_any_permission, get_client_ip
from app.services.ops_common import create_doc, get_doc, list_docs, update_doc, soft_delete_doc, next_number
from app.services.workflow_engine import log_timeline_event
from app.services.audit import record_audit
from app.mongo_utils import to_mongo, from_mongo
from app.models import new_id, utcnow
from app.models_treasury import (
    TaxDeductionRate,
    BankAccount, BankAccountCreate,
    VirtualFund, VirtualFundCreate, VirtualFundUpdate,
    PaymentReceived, PaymentReceivedCreate,
    BankStatementImport, BankMovement,
    VATEntry, VATClosing,
    F24Payment,
    SuggestedTransfer,
    AllocationPolicy, AllocationRun,
    AICFOInsight, TreasuryAlert, TreasuryScenario,
    WithholdingCalcRequest, WithholdingCalcResponse,
    TreasuryCloseMonthRequest, AICFORunRequest,
)


router = APIRouter(prefix="/treasury", tags=["Treasury M7"])


# ---------------- CORE FORMULAS ----------------
def compute_withholding(req: WithholdingCalcRequest) -> WithholdingCalcResponse:
    gross = float(req.gross_amount)
    vat_rate = float(req.conventional_vat_rate)
    w_rate = float(req.withholding_rate)
    method = req.method
    if method == "gross_minus_vat":
        base = gross / (1 + vat_rate / 100.0)
        vat_amt = gross - base
        formula = "base = gross / (1 + vat_rate); withholding = base * rate"
    elif method == "gross_direct":
        base = gross
        vat_amt = 0.0
        formula = "withholding = gross * rate"
    else:
        base = gross / (1 + vat_rate / 100.0)
        vat_amt = gross - base
        formula = "custom (default gross_minus_vat)"
    w_amt = round(base * w_rate / 100.0, 2)
    credit = round(gross - w_amt, 2)
    return WithholdingCalcResponse(
        gross_amount=round(gross, 2),
        withholding_base=round(base, 2),
        conventional_vat_amount=round(vat_amt, 2),
        withholding_rate=w_rate, withholding_amount=w_amt,
        expected_bank_credit=credit, method=method, formula=formula,
        notes="La ritenuta bancaria è credito fiscale da riconciliare, NON è un costo definitivo. "
              "I calcoli sono gestionali: verifica sempre con il consulente fiscale.",
    )


# ---------------- WITHHOLDING CALCULATOR ----------------
@router.post("/withholding/calculate")
async def calc_withholding(payload: WithholdingCalcRequest, user: dict = Depends(require_permission("treasury.view"))):
    return compute_withholding(payload).model_dump()


# ---------------- BANK ACCOUNTS ----------------
@router.get("/bank-accounts")
async def list_bank(user: dict = Depends(require_permission("treasury.view"))):
    return await list_docs(collection="bank_accounts", tenant_id=user["tenant_id"], limit=100)


@router.post("/bank-accounts")
async def create_bank(payload: BankAccountCreate, user: dict = Depends(require_permission("treasury.manage"))):
    iban_hash = hashlib.sha256((payload.iban_masked or "").encode()).hexdigest()[:24]
    inst = BankAccount(**payload.model_dump(), iban_hash=iban_hash)
    return await create_doc(collection="bank_accounts", model_instance=inst, user=user,
                             entity_type="bank_account", ip="")


# ---------------- VIRTUAL FUNDS ----------------
@router.get("/funds")
async def list_funds(user: dict = Depends(require_permission("funds.view"))):
    return await list_docs(collection="virtual_funds", tenant_id=user["tenant_id"],
                            sort=[("priority", 1)], limit=100)


@router.post("/funds")
async def create_fund(payload: VirtualFundCreate, user: dict = Depends(require_permission("funds.configure"))):
    inst = VirtualFund(**payload.model_dump())
    return await create_doc(collection="virtual_funds", model_instance=inst, user=user,
                             entity_type="virtual_fund", ip="")


@router.patch("/funds/{fid}")
async def update_fund(fid: str, payload: VirtualFundUpdate, user: dict = Depends(require_permission("funds.configure"))):
    return await update_doc(collection="virtual_funds", doc_id=fid,
                             updates=payload.model_dump(exclude_unset=True), user=user,
                             entity_type="virtual_fund", ip="")


# ---------------- PAYMENTS RECEIVED (con withholding) ----------------
@router.get("/payments-received")
async def list_payments(user: dict = Depends(require_permission("treasury.view")), limit: int = 100):
    return await list_docs(collection="payments_received", tenant_id=user["tenant_id"],
                            sort=[("payment_date", -1)], limit=limit)


@router.post("/payments-received")
async def register_payment(payload: PaymentReceivedCreate, request: Request,
                            user: dict = Depends(require_permission("treasury.manage"))):
    d = payload.model_dump()
    # Calcola withholding se abilitato
    wb = 0.0; wa = 0.0; expected = d["gross_amount"]
    if d.get("withholding_enabled") and d.get("withholding_rate", 0) > 0:
        w = compute_withholding(WithholdingCalcRequest(
            gross_amount=d["gross_amount"],
            conventional_vat_rate=d.get("conventional_vat_rate", 22.0),
            withholding_rate=d["withholding_rate"],
            method=d.get("withholding_calc_method", "gross_minus_vat"),
        ))
        wb = w.withholding_base; wa = w.withholding_amount; expected = w.expected_bank_credit
    inst = PaymentReceived(
        tenant_id=user["tenant_id"], **d,
        withholding_base=wb, withholding_amount=wa, expected_bank_credit=expected,
        recon_status="received_unreconciled",
    )
    db = get_db()
    doc = to_mongo(inst.model_dump(by_alias=True))
    await db.payments_received.insert_one(doc)
    # Log timeline
    await log_timeline_event(
        tenant_id=user["tenant_id"], domain="payment", event_type="payment.received",
        ref_id=inst.id, contract_id=inst.contract_id, customer_id=inst.customer_id,
        actor_id=user["id"], is_customer_visible=True,
        customer_label="Pagamento ricevuto", customer_stage=None,
        payload={"gross": inst.gross_amount, "expected_credit": expected},
    )
    # Trigger allocation calc + VAT reserve (fire-and-forget style)
    try:
        await run_allocation_for_payment(tenant_id=user["tenant_id"], payment=inst.model_dump())
    except Exception:
        pass
    return inst.model_dump()


# ---------------- ALLOCATION POLICY ----------------
@router.get("/allocation-policy")
async def get_policy(user: dict = Depends(require_permission("funds.view"))):
    db = get_db()
    doc = await db.allocation_policies.find_one({"tenant_id": user["tenant_id"], "active": True, "deleted_at": None},
                                                  sort=[("version", -1)])
    if not doc:
        # Default
        return {
            "active": True, "version": 0, "formula": AllocationPolicy.model_fields["formula"].default,
            "lines": [
                {"fund_code": "vat", "pct": 0, "priority": 10, "kind": "auto_iva"},
                {"fund_code": "contingency", "pct": 15, "priority": 20},
                {"fund_code": "investments", "pct": 15, "priority": 30},
                {"fund_code": "urgent", "pct": 10, "priority": 40},
                {"fund_code": "free_liquidity", "pct": None, "priority": 100, "residual": True},
            ],
        }
    return from_mongo(doc)


@router.post("/allocation-policy")
async def upsert_policy(payload: dict, user: dict = Depends(require_permission("funds.configure"))):
    db = get_db()
    prev = await db.allocation_policies.find_one({"tenant_id": user["tenant_id"], "active": True, "deleted_at": None})
    version = (prev.get("version") if prev else 0) + 1
    inst = AllocationPolicy(tenant_id=user["tenant_id"], version=version,
                             parent_version_id=(prev or {}).get("_id"),
                             valid_from=utcnow(), active=True,
                             lines=payload.get("lines") or [],
                             formula=payload.get("formula") or AllocationPolicy.model_fields["formula"].default,
                             notes=payload.get("notes"))
    if prev:
        await db.allocation_policies.update_one({"_id": prev["_id"]}, {"$set": {"active": False, "valid_to": utcnow().isoformat()}})
    doc = to_mongo(inst.model_dump(by_alias=True))
    await db.allocation_policies.insert_one(doc)
    return inst.model_dump()


async def run_allocation_for_payment(*, tenant_id: str, payment: Dict[str, Any]) -> Dict[str, Any]:
    """Calcola la base allocabile e le ripartizioni. NON esegue trasferimenti."""
    db = get_db()
    policy = await db.allocation_policies.find_one({"tenant_id": tenant_id, "active": True, "deleted_at": None},
                                                     sort=[("version", -1)])
    lines = (policy or {}).get("lines") or [
        {"fund_code": "vat", "pct": 0, "priority": 10, "kind": "auto_iva"},
        {"fund_code": "contingency", "pct": 15, "priority": 20},
        {"fund_code": "investments", "pct": 15, "priority": 30},
        {"fund_code": "urgent", "pct": 10, "priority": 40},
        {"fund_code": "free_liquidity", "pct": None, "priority": 100, "residual": True},
    ]
    bank_credit = float(payment.get("expected_bank_credit") or payment.get("gross_amount") or 0)
    # IVA da accantonare = conventional_vat_amount * 22%/122 * gross → semplificato:
    gross = float(payment.get("gross_amount") or 0)
    vat_rate = float(payment.get("conventional_vat_rate") or 22)
    vat_reserve = round(gross - gross / (1 + vat_rate / 100), 2)  # IVA scorporata
    withholding_reserved = float(payment.get("withholding_amount") or 0)
    base_allocabile = max(0.0, bank_credit - vat_reserve)  # semplificato (senza altri fondi vincolati)
    allocations = []
    remaining = base_allocabile
    cumulative = 0.0
    for line in sorted(lines, key=lambda x: x.get("priority", 100)):
        code = line.get("fund_code")
        pct = line.get("pct")
        if line.get("residual") or pct is None:
            amt = remaining
        else:
            amt = round(base_allocabile * float(pct) / 100.0, 2)
            amt = min(amt, remaining)
        allocations.append({"fund_code": code, "amount": amt, "pct": pct, "priority": line.get("priority", 100)})
        remaining -= amt
        cumulative += amt
        # Update fund balance (virtual bookkeeping)
        if code and code != "free_liquidity":
            await db.virtual_funds.update_one(
                {"tenant_id": tenant_id, "code": code, "deleted_at": None},
                {"$inc": {"current_balance": amt}},
            )
    run = AllocationRun(
        tenant_id=tenant_id, policy_id=(policy or {}).get("_id"),
        policy_version=(policy or {}).get("version", 0),
        triggered_by="payment", payment_id=payment.get("id"),
        inputs={"gross": gross, "vat_rate": vat_rate, "bank_credit": bank_credit,
                 "vat_reserve": vat_reserve, "withholding_reserved": withholding_reserved},
        base_allocabile=base_allocabile,
        allocations=allocations,
        residual_free_liquidity=max(0.0, remaining),
    )
    await db.allocation_runs.insert_one(to_mongo(run.model_dump(by_alias=True)))
    # Update fund VAT
    if vat_reserve > 0:
        await db.virtual_funds.update_one(
            {"tenant_id": tenant_id, "code": "vat", "deleted_at": None},
            {"$inc": {"current_balance": vat_reserve}}, upsert=False,
        )
    return run.model_dump()


@router.get("/allocation-runs")
async def list_allocation_runs(user: dict = Depends(require_permission("funds.view")), limit: int = 50):
    return await list_docs(collection="allocation_runs", tenant_id=user["tenant_id"],
                            sort=[("computed_at", -1)], limit=limit)


# ---------------- VAT LEDGER ----------------
@router.get("/vat/entries")
async def list_vat_entries(period: Optional[str] = None,
                           user: dict = Depends(require_permission("vat.view"))):
    filters = {}
    if period: filters["period"] = period
    return await list_docs(collection="vat_entries", tenant_id=user["tenant_id"], filters=filters,
                            sort=[("created_at", -1)], limit=200)


@router.post("/vat/entries")
async def create_vat_entry(payload: dict, user: dict = Depends(require_permission("vat.manage"))):
    inst = VATEntry(tenant_id=user["tenant_id"], **payload)
    return await create_doc(collection="vat_entries", model_instance=inst, user=user,
                             entity_type="vat_entry", ip="")


@router.get("/vat/closings")
async def list_vat_closings(user: dict = Depends(require_permission("vat.view"))):
    return await list_docs(collection="vat_closings", tenant_id=user["tenant_id"],
                            sort=[("period", -1)], limit=50)


@router.post("/vat/close-period")
async def close_vat_period(payload: TreasuryCloseMonthRequest,
                            user: dict = Depends(require_permission("vat.close_period"))):
    db = get_db()
    already = await db.vat_closings.find_one({"tenant_id": user["tenant_id"], "period": payload.period,
                                                "closing_status": "closed", "deleted_at": None})
    if already:
        raise HTTPException(status_code=409, detail=f"Periodo {payload.period} già chiuso — usa rettifica")
    # Aggregazione entries
    pipe = [{"$match": {"tenant_id": user["tenant_id"], "period": payload.period, "deleted_at": None}}]
    pipe += [{"$group": {"_id": "$kind", "vat": {"$sum": "$vat_amount"}, "tax": {"$sum": "$taxable_amount"}}}]
    rows = await db.vat_entries.aggregate(pipe).to_list(100)
    sales = 0.0; purchases = 0.0
    for r in rows:
        if r["_id"] == "sales": sales += float(r["vat"])
        elif r["_id"] == "purchases": purchases += float(r["vat"])
        elif r["_id"] == "sales_credit_note": sales -= float(r["vat"])
        elif r["_id"] == "purchases_credit_note": purchases -= float(r["vat"])
    net = sales - purchases
    closing = VATClosing(
        tenant_id=user["tenant_id"], period=payload.period,
        sales_vat_exigible=round(sales, 2), purchases_vat_detrattable=round(purchases, 2),
        net_vat=round(net, 2), balance=round(net, 2), is_credit=(net < 0),
        closing_status="closed", closed_at=utcnow(), closed_by=user["id"],
        formula_used="net_vat = sales_vat_exigible - purchases_vat_detrattable",
        notes=payload.notes,
    )
    doc = to_mongo(closing.model_dump(by_alias=True))
    await db.vat_closings.insert_one(doc)
    return closing.model_dump()


# ---------------- F24 ----------------
@router.get("/f24")
async def list_f24(user: dict = Depends(require_permission("tax_payments.view")), limit: int = 100):
    return await list_docs(collection="f24_payments", tenant_id=user["tenant_id"],
                            sort=[("due_date", -1)], limit=limit)


@router.post("/f24")
async def create_f24(payload: dict, user: dict = Depends(require_permission("tax_payments.manage"))):
    inst = F24Payment(tenant_id=user["tenant_id"], **payload)
    return await create_doc(collection="f24_payments", model_instance=inst, user=user,
                             entity_type="f24_payment", ip="")


# ---------------- SUGGESTED TRANSFERS (no exec auto) ----------------
@router.get("/transfers")
async def list_transfers(user: dict = Depends(require_permission("treasury.view")),
                          st_status: Optional[str] = None, limit: int = 100):
    filters = {}
    if st_status: filters["st_status"] = st_status
    return await list_docs(collection="suggested_transfers", tenant_id=user["tenant_id"],
                            filters=filters, sort=[("priority", 1), ("created_at", -1)], limit=limit)


@router.post("/transfers/suggest")
async def suggest_transfer(payload: dict, user: dict = Depends(require_permission("treasury.manage"))):
    inst = SuggestedTransfer(tenant_id=user["tenant_id"], **payload)
    return await create_doc(collection="suggested_transfers", model_instance=inst, user=user,
                             entity_type="suggested_transfer", ip="")


@router.post("/transfers/{tid}/approve")
async def approve_transfer(tid: str, user: dict = Depends(require_permission("treasury.approve_transfers"))):
    db = get_db()
    await db.suggested_transfers.update_one(
        {"_id": tid, "tenant_id": user["tenant_id"]},
        {"$set": {"st_status": "approved", "approver_id": user["id"], "approved_at": utcnow().isoformat()}},
    )
    return {"ok": True}


@router.post("/transfers/{tid}/reject")
async def reject_transfer(tid: str, payload: dict, user: dict = Depends(require_permission("treasury.approve_transfers"))):
    db = get_db()
    await db.suggested_transfers.update_one(
        {"_id": tid, "tenant_id": user["tenant_id"]},
        {"$set": {"st_status": "rejected", "approver_id": user["id"]}},
    )
    return {"ok": True}


@router.post("/transfers/{tid}/mark-executed")
async def mark_executed(tid: str, payload: dict, user: dict = Depends(require_permission("treasury.approve_transfers"))):
    """Marca come eseguito MANUALMENTE (bonifico effettuato fuori dal sistema). NO esecuzione automatica."""
    db = get_db()
    await db.suggested_transfers.update_one(
        {"_id": tid, "tenant_id": user["tenant_id"], "st_status": "approved"},
        {"$set": {"st_status": "executed", "executed_at": utcnow().isoformat(),
                   "executed_by": user["id"], "execution_ref": payload.get("execution_ref")}},
    )
    return {"ok": True}


# ---------------- BANK STATEMENT IMPORT + RECONCILE ----------------
@router.post("/statements/import")
async def import_statement(payload: dict, user: dict = Depends(require_permission("treasury.import_statements"))):
    """Crea un import job. Il parsing effettivo del file è demandato al frontend/preview."""
    inst = BankStatementImport(
        tenant_id=user["tenant_id"],
        bank_account_id=payload["bank_account_id"],
        filename=payload.get("filename", "import.csv"),
        format=payload.get("format", "csv"),
        imported_by=user["id"], imp_status="pending",
    )
    doc = to_mongo(inst.model_dump(by_alias=True))
    db = get_db()
    await db.bank_statement_imports.insert_one(doc)
    # Movimenti forniti nel payload (rows)
    rows = payload.get("rows") or []
    imported = 0; duplicates = 0
    for r in rows:
        dedup_src = f"{payload['bank_account_id']}|{r.get('op_date')}|{r.get('amount')}|{r.get('reference') or ''}|{r.get('description', '')[:100]}"
        dedup_hash = hashlib.sha256(dedup_src.encode()).hexdigest()[:32]
        existing = await db.bank_movements.find_one({"tenant_id": user["tenant_id"], "dedup_hash": dedup_hash})
        if existing:
            duplicates += 1
            continue
        mov = BankMovement(
            tenant_id=user["tenant_id"], bank_account_id=payload["bank_account_id"],
            import_id=inst.id, op_date=r["op_date"], value_date=r.get("value_date"),
            amount=float(r["amount"]), description=r.get("description", ""),
            counterpart=r.get("counterpart"), reference=r.get("reference"),
            balance_after=r.get("balance_after"), bank_name=r.get("bank_name"),
            dedup_hash=dedup_hash,
        )
        await db.bank_movements.insert_one(to_mongo(mov.model_dump(by_alias=True)))
        imported += 1
    await db.bank_statement_imports.update_one(
        {"_id": inst.id}, {"$set": {"rows_total": len(rows), "rows_imported": imported,
                                       "rows_duplicate": duplicates, "imp_status": "imported"}},
    )
    return {"ok": True, "import_id": inst.id, "imported": imported, "duplicates": duplicates}


@router.get("/movements")
async def list_movements(bank_account_id: Optional[str] = None, recon_status: Optional[str] = None,
                          user: dict = Depends(require_permission("treasury.view")), limit: int = 200):
    filters = {}
    if bank_account_id: filters["bank_account_id"] = bank_account_id
    if recon_status: filters["recon_status"] = recon_status
    return await list_docs(collection="bank_movements", tenant_id=user["tenant_id"],
                            filters=filters, sort=[("op_date", -1)], limit=limit)


@router.post("/reconcile/auto")
async def reconcile_auto(payload: dict, user: dict = Depends(require_permission("treasury.reconcile"))):
    """Match automatico movimenti ↔ payments_received con tolleranza importo/data."""
    db = get_db()
    tol_amount = float(payload.get("amount_tolerance", 1.0))
    tol_days = int(payload.get("date_tolerance_days", 3))
    matched = 0
    async for mov in db.bank_movements.find({
        "tenant_id": user["tenant_id"], "recon_status": "unreconciled",
        "amount": {"$gt": 0}, "deleted_at": None,
    }):
        # Ricerca pagamento coerente
        min_amt = mov["amount"] - tol_amount
        max_amt = mov["amount"] + tol_amount
        candidate = await db.payments_received.find_one({
            "tenant_id": user["tenant_id"], "recon_status": "received_unreconciled",
            "$or": [
                {"expected_bank_credit": {"$gte": min_amt, "$lte": max_amt}},
                {"gross_amount": {"$gte": min_amt, "$lte": max_amt}},
            ],
        })
        if candidate:
            await db.bank_movements.update_one({"_id": mov["_id"]},
                {"$set": {"recon_status": "auto_match", "linked_payment_id": candidate["_id"],
                           "match_score": 0.9}})
            await db.payments_received.update_one({"_id": candidate["_id"]},
                {"$set": {"recon_status": "reconciled", "reconciled_movement_id": mov["_id"],
                           "actual_bank_credit": mov["amount"]}})
            matched += 1
    return {"ok": True, "matched": matched}


# ---------------- DASHBOARD TREASURY ----------------
@router.get("/dashboard")
async def treasury_dashboard(user: dict = Depends(require_permission("treasury.view"))):
    db = get_db()
    tid = user["tenant_id"]
    # Bank
    accounts = await db.bank_accounts.find({"tenant_id": tid, "active": True, "deleted_at": None}).to_list(100)
    saldo_bank = sum(float(a.get("contabile_balance") or 0) for a in accounts)
    saldo_disp = sum(float(a.get("available_balance") or 0) for a in accounts)
    # Funds
    funds = await db.virtual_funds.find({"tenant_id": tid, "active": True, "deleted_at": None}).to_list(100)
    fondi_totale = sum(float(f.get("current_balance") or 0) for f in funds)
    fondo_iva = next((float(f.get("current_balance") or 0) for f in funds if f.get("code") == "vat"), 0.0)
    fondo_contingency = next((float(f.get("current_balance") or 0) for f in funds if f.get("code") == "contingency"), 0.0)
    fondo_urgent = next((float(f.get("current_balance") or 0) for f in funds if f.get("code") == "urgent"), 0.0)
    # VAT last closing
    last_vat = await db.vat_closings.find({"tenant_id": tid, "deleted_at": None}).sort("period", -1).limit(1).to_list(1)
    vat_last = last_vat[0] if last_vat else None
    # F24 upcoming
    f24_upcoming = await db.f24_payments.count_documents({
        "tenant_id": tid, "f24_status": {"$in": ["planned", "generated", "sent"]},
        "deleted_at": None,
    })
    # Withholding pending
    with_pending = await db.payments_received.count_documents({
        "tenant_id": tid, "withholding_enabled": True,
        "recon_status": {"$in": ["received_unreconciled", "withholding_mismatch"]},
        "deleted_at": None,
    })
    # Suggested transfers count
    sug = await db.suggested_transfers.count_documents({
        "tenant_id": tid, "st_status": "suggested", "deleted_at": None,
    })
    # Alerts
    alerts = await db.treasury_alerts.find({"tenant_id": tid, "is_resolved": False, "deleted_at": None}) \
        .sort("severity", -1).limit(20).to_list(20)
    return {
        "availability": {
            "bank_balance_total": round(saldo_bank, 2),
            "available_balance": round(saldo_disp, 2),
            "virtual_funds_total": round(fondi_totale, 2),
            "free_liquidity": round(saldo_disp - fondi_totale, 2),
        },
        "vat": {
            "vat_fund_balance": round(fondo_iva, 2),
            "last_closing_period": (vat_last or {}).get("period"),
            "last_closing_net_vat": (vat_last or {}).get("net_vat"),
            "last_closing_is_credit": (vat_last or {}).get("is_credit"),
        },
        "funds": {
            "contingency": round(fondo_contingency, 2),
            "urgent": round(fondo_urgent, 2),
            "iva": round(fondo_iva, 2),
            "total": round(fondi_totale, 2),
        },
        "alerts": [from_mongo(a) for a in alerts],
        "counters": {
            "f24_upcoming": f24_upcoming,
            "withholding_pending": with_pending,
            "suggested_transfers_open": sug,
        },
        "disclaimer": "Elaborazioni gestionali, NON sostitutive del commercialista. Verifica sempre con consulente fiscale.",
    }


# ---------------- AI CFO ENHANCED ----------------
@router.get("/ai-cfo/insights")
async def list_insights(user: dict = Depends(require_permission("ai_cfo.view")), limit: int = 50):
    return await list_docs(collection="ai_cfo_insights", tenant_id=user["tenant_id"],
                            sort=[("generated_at", -1)], limit=limit)


@router.post("/ai-cfo/run")
async def run_ai_cfo(payload: AICFORunRequest, user: dict = Depends(require_permission("ai_cfo.run"))):
    """Genera insight base con dati REALI (no invenzioni). Se dati mancano, missing_data popolato."""
    db = get_db()
    tid = user["tenant_id"]
    generated: List[Dict[str, Any]] = []
    # 1) Fondo IVA vs debito VAT stimato
    last_vat = await db.vat_closings.find_one({"tenant_id": tid, "deleted_at": None}, sort=[("period", -1)])
    iva_fund_doc = await db.virtual_funds.find_one({"tenant_id": tid, "code": "vat", "deleted_at": None})
    iva_fund = float((iva_fund_doc or {}).get("current_balance") or 0)
    if last_vat and last_vat.get("net_vat", 0) > iva_fund:
        insight = AICFOInsight(
            tenant_id=tid, kind="vat_reserve_increase",
            title="Fondo IVA sotto il debito stimato",
            body=f"Debito IVA stimato €{last_vat['net_vat']:.2f} > fondo attuale €{iva_fund:.2f}. Considera trasferimento.",
            period_analyzed=last_vat.get("period"),
            data_sources=[{"kind": "vat_closing", "id": last_vat["_id"], "period": last_vat["period"]},
                            {"kind": "virtual_fund", "code": "vat"}],
            formula="net_vat = sales_vat_exigible - purchases_vat_detrattable",
            confidence=0.9, risk_level="high", requires_approval=True,
            suggested_actions=[{"type": "transfer", "to_fund": "vat",
                                  "amount": round(last_vat["net_vat"] - iva_fund, 2)}],
        )
        await db.ai_cfo_insights.insert_one(to_mongo(insight.model_dump(by_alias=True)))
        generated.append(insight.model_dump())
    # 2) F24 in scadenza nei prossimi 15 giorni senza copertura
    horizon = utcnow() + timedelta(days=15)
    f24s = await db.f24_payments.find({
        "tenant_id": tid, "f24_status": {"$in": ["planned", "generated", "sent"]},
        "due_date": {"$lte": horizon.date().isoformat()}, "deleted_at": None,
    }).to_list(50)
    for f in f24s:
        insight = AICFOInsight(
            tenant_id=tid, kind="f24_upcoming",
            title=f"F24 {f.get('tribute_code')} in scadenza",
            body=f"Importo netto €{f.get('net_amount', 0):.2f} in scadenza il {f.get('due_date')}. Verifica copertura.",
            data_sources=[{"kind": "f24", "id": f["_id"]}],
            confidence=1.0, risk_level="high",
            missing_data=["Ricevuta pagamento"] if not f.get("receipt_id") else [],
        )
        await db.ai_cfo_insights.insert_one(to_mongo(insight.model_dump(by_alias=True)))
        generated.append(insight.model_dump())
    # 3) Withholding pending riconciliazione
    with_pending = await db.payments_received.count_documents({
        "tenant_id": tid, "withholding_enabled": True,
        "recon_status": {"$in": ["received_unreconciled", "withholding_mismatch"]},
        "deleted_at": None,
    })
    if with_pending > 0:
        insight = AICFOInsight(
            tenant_id=tid, kind="withholding_pending",
            title=f"{with_pending} ritenute bancarie da riconciliare",
            body=f"Ci sono {with_pending} pagamenti agevolati con ritenuta non ancora riconciliata. Verifica estratto conto.",
            data_sources=[{"kind": "payments_received_count", "value": with_pending}],
            confidence=0.85, risk_level="medium",
        )
        await db.ai_cfo_insights.insert_one(to_mongo(insight.model_dump(by_alias=True)))
        generated.append(insight.model_dump())
    return {"ok": True, "generated": len(generated), "insights": generated,
            "disclaimer": "Suggerimenti gestionali, NO esecuzione automatica di bonifici/F24."}


# ---------------- ALERTS ----------------
@router.get("/alerts")
async def list_alerts(user: dict = Depends(require_permission("treasury.view"))):
    return await list_docs(collection="treasury_alerts", tenant_id=user["tenant_id"],
                            filters={"is_resolved": False}, sort=[("severity", -1), ("created_at", -1)], limit=100)


@router.post("/alerts/{aid}/resolve")
async def resolve_alert(aid: str, user: dict = Depends(require_permission("treasury.manage"))):
    db = get_db()
    await db.treasury_alerts.update_one(
        {"_id": aid, "tenant_id": user["tenant_id"]},
        {"$set": {"is_resolved": True, "resolved_at": utcnow().isoformat(), "resolved_by": user["id"]}},
    )
    return {"ok": True}


# ---------------- SCENARIOS ----------------
@router.get("/scenarios")
async def list_scenarios(user: dict = Depends(require_permission("treasury.view"))):
    return await list_docs(collection="treasury_scenarios", tenant_id=user["tenant_id"],
                            sort=[("created_at", -1)], limit=50)


@router.post("/scenarios")
async def create_scenario(payload: dict, user: dict = Depends(require_permission("treasury.manage"))):
    scenario = TreasuryScenario(tenant_id=user["tenant_id"], **payload)
    # Calcolo semplice cash flow horizon
    horizon = int(scenario.horizon_months)
    incassi = float(scenario.inputs.get("monthly_income", 0))
    uscite = float(scenario.inputs.get("monthly_expenses", 0))
    saldo = float(scenario.inputs.get("initial_balance", 0))
    monthly = []
    min_bal = saldo
    for m in range(horizon):
        saldo += incassi - uscite
        monthly.append({"month": m + 1, "balance": round(saldo, 2)})
        if saldo < min_bal: min_bal = saldo
    scenario.outputs = {"final_balance": round(saldo, 2), "min_balance": round(min_bal, 2), "monthly": monthly}
    scenario.formula_used = "balance_m = balance_(m-1) + monthly_income - monthly_expenses"
    doc = to_mongo(scenario.model_dump(by_alias=True))
    db = get_db()
    await db.treasury_scenarios.insert_one(doc)
    return scenario.model_dump()


# ---------------- TAX DEDUCTION RATES ----------------
@router.get("/tax-deduction-rates")
async def list_tax_rates(user: dict = Depends(require_permission("treasury.view"))):
    return await list_docs(collection="tax_deduction_rates", tenant_id=user["tenant_id"],
                            sort=[("valid_from", -1)], limit=50)


@router.post("/tax-deduction-rates")
async def create_tax_rate(payload: dict, user: dict = Depends(require_permission("treasury.configure"))):
    inst = TaxDeductionRate(tenant_id=user["tenant_id"], **payload)
    return await create_doc(collection="tax_deduction_rates", model_instance=inst, user=user,
                             entity_type="tax_deduction_rate", ip="")
