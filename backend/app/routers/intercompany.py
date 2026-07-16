"""Intercompany transactions router — auto-mirroring + riconciliazione."""
from __future__ import annotations
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException

from app.db import get_db
from app.deps import get_current_user, require_permission
from app.mongo_utils import to_mongo, from_mongo
from app.models import utcnow, new_id
from app.services.module_gating import require_module
from app.models_multi_company import (
    IntercompanyTransaction, IntercompanyCreate, IntercompanyReconcileRequest,
    IntercompanyStatus,
)
from app.routers.legal_entities import get_user_legal_entity_ids


router = APIRouter(prefix="/intercompany", tags=["Intercompany"])


async def _check_entity_access(user: dict, source_id: str, target_id: str):
    scope = await get_user_legal_entity_ids(user)
    if scope is None:
        return
    if source_id not in scope and target_id not in scope:
        raise HTTPException(403, "Nessun accesso a nessuna delle due società")


def _compute_vat(amount_taxable: float, vat_rate: float) -> tuple[float, float]:
    vat = round(amount_taxable * (vat_rate / 100.0), 2)
    gross = round(amount_taxable + vat, 2)
    return vat, gross


@router.get("")
async def list_intercompany(status: Optional[str] = None,
                            legal_entity_id: Optional[str] = None,
                            user: dict = Depends(require_module("multi_company"))):
    db = get_db()
    q: Dict[str, Any] = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if status: q["ic_status"] = status
    if legal_entity_id:
        q["$or"] = [{"source_legal_entity_id": legal_entity_id},
                    {"target_legal_entity_id": legal_entity_id}]
    docs = await db.intercompany_transactions.find(q).sort([("created_at", -1)]).limit(300).to_list(300)
    return {"items": [from_mongo(d) for d in docs], "total": len(docs)}


@router.post("")
async def create_intercompany(payload: IntercompanyCreate,
                               user: dict = Depends(require_module("multi_company", write=True))):
    """Crea la coppia mirrorata (source + target) in modo atomico."""
    if payload.source_legal_entity_id == payload.target_legal_entity_id:
        raise HTTPException(400, "Le due società non possono coincidere")
    await _check_entity_access(user, payload.source_legal_entity_id, payload.target_legal_entity_id)
    db = get_db()
    # Verifica esistenza LE
    for eid in [payload.source_legal_entity_id, payload.target_legal_entity_id]:
        le = await db.legal_entities.find_one({"_id": eid, "tenant_id": user["tenant_id"], "deleted_at": None})
        if not le:
            raise HTTPException(404, f"Legal entity {eid} non trovata")
        if le.get("fiscal_operations_blocked"):
            raise HTTPException(400,
                f"Società '{le.get('name')}' ha dati fiscali incompleti: {le.get('missing_fields')}. "
                f"Completa i dati prima di registrare operazioni intercompany.")
    pair_id = new_id()
    vat_amt, gross = _compute_vat(payload.amount_taxable, payload.vat_rate)
    common = dict(
        tenant_id=user["tenant_id"],
        intercompany_pair_id=pair_id,
        source_legal_entity_id=payload.source_legal_entity_id,
        target_legal_entity_id=payload.target_legal_entity_id,
        doc_kind=payload.doc_kind, doc_ref=payload.doc_ref, doc_date=payload.doc_date,
        amount_gross=gross, amount_taxable=payload.amount_taxable,
        vat_amount=vat_amt, vat_rate=payload.vat_rate, currency=payload.currency,
        due_date=payload.due_date, reason=payload.reason,
        attachments=payload.attachments,
        ic_status="mirrored",
        created_by=user["id"], updated_by=user["id"],
    )
    source = IntercompanyTransaction(
        side="source",
        self_legal_entity_id=payload.source_legal_entity_id,
        counterparty_legal_entity_id=payload.target_legal_entity_id,
        debit_credit="credit", revenue_or_cost="revenue",
        **common,
    )
    target = IntercompanyTransaction(
        side="target",
        self_legal_entity_id=payload.target_legal_entity_id,
        counterparty_legal_entity_id=payload.source_legal_entity_id,
        debit_credit="debit", revenue_or_cost="cost",
        **common,
    )
    await db.intercompany_transactions.insert_one(to_mongo(source.model_dump(by_alias=True)))
    await db.intercompany_transactions.insert_one(to_mongo(target.model_dump(by_alias=True)))
    # Crea receivable/payable collegati
    from app.models_control import Payable, Receivable
    if payload.due_date:
        rec = Receivable(
            tenant_id=user["tenant_id"], label=f"IC {payload.doc_ref or ''}".strip(),
            debtor=payload.target_legal_entity_id, doc_ref=payload.doc_ref,
            doc_date=payload.doc_date, due_date=payload.due_date,
            amount_gross=gross, residual=gross,
            legal_entity_id=payload.source_legal_entity_id,
            linked_intercompany_pair_id=pair_id, r_status="issued",
        )
        pay = Payable(
            tenant_id=user["tenant_id"], label=f"IC {payload.doc_ref or ''}".strip(),
            creditor=payload.source_legal_entity_id, doc_ref=payload.doc_ref,
            doc_date=payload.doc_date, due_date=payload.due_date,
            amount_gross=gross, residual=gross,
            legal_entity_id=payload.target_legal_entity_id,
            linked_intercompany_pair_id=pair_id, payable_status="issued",
        )
        await db.receivables.insert_one(to_mongo(rec.model_dump(by_alias=True)))
        await db.payables.insert_one(to_mongo(pay.model_dump(by_alias=True)))
    return {"pair_id": pair_id, "source": source.model_dump(), "target": target.model_dump()}


@router.get("/pair/{pair_id}")
async def get_pair(pair_id: str, user: dict = Depends(require_module("multi_company"))):
    db = get_db()
    docs = await db.intercompany_transactions.find(
        {"tenant_id": user["tenant_id"], "intercompany_pair_id": pair_id, "deleted_at": None}
    ).to_list(2)
    if not docs:
        raise HTTPException(404, "Coppia non trovata")
    items = [from_mongo(d) for d in docs]
    # Verifica coerenza
    flags: List[str] = []
    if len(items) < 2:
        flags.append("missing_counterpart")
    else:
        a, b = items[0], items[1]
        if abs(a["amount_taxable"] - b["amount_taxable"]) > 0.01:
            flags.append("amount_mismatch")
        if abs(a["vat_amount"] - b["vat_amount"]) > 0.01:
            flags.append("vat_mismatch")
        if a["currency"] != b["currency"]:
            flags.append("currency_mismatch")
        if a.get("due_date") != b.get("due_date"):
            flags.append("due_date_mismatch")
    return {"items": items, "consistency_flags": flags, "coherent": len(flags) == 0}


@router.post("/reconcile")
async def reconcile(payload: IntercompanyReconcileRequest,
                    user: dict = Depends(require_module("multi_company", write=True))):
    db = get_db()
    pair = await db.intercompany_transactions.find(
        {"tenant_id": user["tenant_id"], "intercompany_pair_id": payload.pair_id, "deleted_at": None}
    ).to_list(2)
    if not pair:
        raise HTTPException(404, "Pair non trovato")
    action = payload.action
    new_status: Dict[str, str] = {
        "confirm": "reconciled", "dispute": "disputed",
        "cancel": "cancelled", "reverse": "reversed",
    }
    if action not in new_status:
        raise HTTPException(400, "Azione non valida")
    await db.intercompany_transactions.update_many(
        {"tenant_id": user["tenant_id"], "intercompany_pair_id": payload.pair_id},
        {"$set": {"ic_status": new_status[action], "updated_at": utcnow().isoformat(),
                   "updated_by": user["id"], "notes": payload.reason},
         "$inc": {"version": 1}},
    )
    if action == "reverse":
        # Storno: crea coppia inversa
        src = next((x for x in pair if x.get("side") == "source"), None)
        tgt = next((x for x in pair if x.get("side") == "target"), None)
        if src and tgt:
            new_pair = new_id()
            common = {
                "tenant_id": user["tenant_id"],
                "intercompany_pair_id": new_pair,
                "source_legal_entity_id": tgt["self_legal_entity_id"],
                "target_legal_entity_id": src["self_legal_entity_id"],
                "doc_kind": "credit_note",
                "doc_ref": (src.get("doc_ref") or "") + "-REV",
                "amount_gross": src["amount_gross"], "amount_taxable": src["amount_taxable"],
                "vat_amount": src["vat_amount"], "vat_rate": src["vat_rate"],
                "currency": src["currency"], "due_date": src.get("due_date"),
                "ic_status": "mirrored",
                "reversal_of_id": src["_id"],
                "reason": f"Storno di {src.get('doc_ref')}",
                "created_by": user["id"], "updated_by": user["id"],
            }
            r_src = IntercompanyTransaction(side="source",
                self_legal_entity_id=tgt["self_legal_entity_id"],
                counterparty_legal_entity_id=src["self_legal_entity_id"],
                debit_credit="credit", revenue_or_cost="revenue", **common)
            r_tgt = IntercompanyTransaction(side="target",
                self_legal_entity_id=src["self_legal_entity_id"],
                counterparty_legal_entity_id=tgt["self_legal_entity_id"],
                debit_credit="debit", revenue_or_cost="cost", **common)
            await db.intercompany_transactions.insert_one(to_mongo(r_src.model_dump(by_alias=True)))
            await db.intercompany_transactions.insert_one(to_mongo(r_tgt.model_dump(by_alias=True)))
    return {"ok": True, "new_status": new_status[action]}


@router.get("/reconciliation-report")
async def reconciliation_report(user: dict = Depends(require_module("multi_company"))):
    """Dashboard di riconciliazione: incoerenze / pair non riconciliati."""
    db = get_db()
    pipe = [
        {"$match": {"tenant_id": user["tenant_id"], "deleted_at": None}},
        {"$group": {
            "_id": "$intercompany_pair_id",
            "sides": {"$addToSet": "$side"},
            "amounts": {"$addToSet": "$amount_taxable"},
            "vats": {"$addToSet": "$vat_amount"},
            "statuses": {"$addToSet": "$ic_status"},
            "currencies": {"$addToSet": "$currency"},
            "count": {"$sum": 1},
        }},
    ]
    rows = await db.intercompany_transactions.aggregate(pipe).to_list(2000)
    issues = []
    total_pairs = 0
    mirrored = 0
    reconciled = 0
    for r in rows:
        total_pairs += 1
        pair_issues = []
        if len(r.get("sides") or []) < 2:
            pair_issues.append("missing_counterpart")
        if len(r.get("amounts") or []) > 1:
            pair_issues.append("amount_mismatch")
        if len(r.get("currencies") or []) > 1:
            pair_issues.append("currency_mismatch")
        if "reconciled" in (r.get("statuses") or []):
            reconciled += 1
        elif "mirrored" in (r.get("statuses") or []):
            mirrored += 1
        if pair_issues:
            issues.append({"pair_id": r["_id"], "flags": pair_issues})
    return {
        "total_pairs": total_pairs,
        "mirrored": mirrored,
        "reconciled": reconciled,
        "issues": issues[:100],
        "issue_count": len(issues),
    }
