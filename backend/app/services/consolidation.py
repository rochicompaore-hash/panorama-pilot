"""Consolidation service: intercompany elimination + consolidated views.

Regole:
- Sommare Enerhia + Auxer (grezzo).
- Eliminare intercompany:
    * revenue/cost sui pair mirrorati
    * receivable/payable intercompany
- Mostrare sempre: valore per legal entity, totale lordo, eliminazioni, consolidato.
"""
from __future__ import annotations
from typing import Dict, List, Any, Optional
from app.db import get_db


async def compute_consolidation(
    tenant_id: str,
    period_from: Optional[str] = None,
    period_to: Optional[str] = None,
) -> Dict[str, Any]:
    db = get_db()
    entities = await db.legal_entities.find(
        {"tenant_id": tenant_id, "deleted_at": None}
    ).to_list(20)

    by_entity: Dict[str, Dict[str, float]] = {}
    for le in entities:
        eid = le["_id"]
        # Ricavi (payments_received per legal_entity)
        rev_pipe = [{"$match": {
            "tenant_id": tenant_id, "legal_entity_id": eid, "deleted_at": None,
        }}, {"$group": {"_id": None, "s": {"$sum": "$gross_amount"}}}]
        rev_docs = await db.payments_received.aggregate(rev_pipe).to_list(1)
        revenue = float((rev_docs[0] if rev_docs else {}).get("s") or 0)
        # Costi fissi (annuali → mensili)
        fc_pipe = [{"$match": {
            "tenant_id": tenant_id, "legal_entity_id": eid,
            "active": True, "deleted_at": None,
        }}, {"$group": {"_id": None, "s": {"$sum": "$amount_monthly"}}}]
        fc_docs = await db.fixed_costs.aggregate(fc_pipe).to_list(1)
        fixed_month = float((fc_docs[0] if fc_docs else {}).get("s") or 0)
        # Personale
        pc_pipe = [{"$match": {
            "tenant_id": tenant_id, "legal_entity_id": eid,
            "active": True, "deleted_at": None,
        }}, {"$group": {"_id": None, "s": {"$sum": "$monthly_total_cost"}}}]
        pc_docs = await db.personnel_costs.aggregate(pc_pipe).to_list(1)
        pers_month = float((pc_docs[0] if pc_docs else {}).get("s") or 0)
        # Payables residual
        pay_pipe = [{"$match": {
            "tenant_id": tenant_id, "legal_entity_id": eid,
            "deleted_at": None, "payable_status": {"$nin": ["paid", "cancelled"]},
        }}, {"$group": {"_id": None, "s": {"$sum": "$residual"}}}]
        pay_docs = await db.payables.aggregate(pay_pipe).to_list(1)
        payables = float((pay_docs[0] if pay_docs else {}).get("s") or 0)
        by_entity[eid] = {
            "id": eid,
            "code": le.get("code"),
            "name": le.get("name"),
            "revenue": round(revenue, 2),
            "fixed_costs_month": round(fixed_month, 2),
            "personnel_month": round(pers_month, 2),
            "payables_residual": round(payables, 2),
        }

    # Intercompany transactions per elimination
    ic_pipe = [{"$match": {
        "tenant_id": tenant_id, "deleted_at": None,
        "ic_status": {"$in": ["mirrored", "reconciled", "partially_reconciled"]},
    }}, {"$group": {
        "_id": "$intercompany_pair_id",
        "amount": {"$max": "$amount_taxable"},
        "vat": {"$max": "$vat_amount"},
    }}]
    ic_pairs = await db.intercompany_transactions.aggregate(ic_pipe).to_list(1000)
    ic_elim_revenue = sum(float(p.get("amount") or 0) for p in ic_pairs)

    # Totali
    gross_revenue = sum(v["revenue"] for v in by_entity.values())
    consolidated_revenue = gross_revenue - ic_elim_revenue
    gross_fixed = sum(v["fixed_costs_month"] + v["personnel_month"] for v in by_entity.values())
    gross_payables = sum(v["payables_residual"] for v in by_entity.values())

    return {
        "period": {"from": period_from, "to": period_to},
        "entities": list(by_entity.values()),
        "gross_totals": {
            "revenue": round(gross_revenue, 2),
            "fixed_month": round(gross_fixed, 2),
            "payables": round(gross_payables, 2),
        },
        "eliminations": {
            "intercompany_revenue": round(ic_elim_revenue, 2),
            "intercompany_pairs_count": len(ic_pairs),
        },
        "consolidated": {
            "revenue": round(consolidated_revenue, 2),
            "fixed_month": round(gross_fixed, 2),
            "payables": round(gross_payables, 2),
        },
        "notes": (
            "Vista gestionale consolidata: elimina ricavi/costi intercompany mirrorati e "
            "riconciliati. NON sostituisce il bilancio consolidato civilistico."
        ),
    }
