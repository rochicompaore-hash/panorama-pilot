"""Commission engine + Profitability calculator.

Regole di default:
- Fascia 1 <10%: gettone (flat_fee) + pending_configuration se non definito
- Fascia 2 10-15%: 5%
- Fascia 3 >15%: 10% (o 5% se maggior sconto)
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from app.db import get_db
from app.mongo_utils import to_mongo
from app.models import new_id, utcnow
from app.models_commissions import (
    ProfitabilityBreakdown, DiscountClassification,
    CommissionEntry, CommissionPlan, ProfitabilityTier,
)


DEFAULT_TIERS: List[Dict[str, Any]] = [
    {"label": "Fascia 1 (<10%)", "min_pct": None, "max_pct": 10.0, "max_exclusive": True,
     "commission_pct": None, "flat_fee": None, "pending_configuration": True, "requires_approval": True},
    {"label": "Fascia 2 (10-15%)", "min_pct": 10.0, "max_pct": 15.0,
     "commission_pct": 5.0, "flat_fee": None, "max_pct_with_major_discount": 5.0},
    {"label": "Fascia 3 (>15%)", "min_pct": 15.0, "min_exclusive": True, "max_pct": None,
     "commission_pct": 10.0, "flat_fee": None, "max_pct_with_major_discount": 5.0},
]


def match_tier(tiers: List[Dict[str, Any]], profitability_pct: Optional[float]) -> Optional[Dict[str, Any]]:
    if profitability_pct is None:
        return None
    p = float(profitability_pct)
    for t in tiers:
        min_p = t.get("min_pct")
        max_p = t.get("max_pct")
        min_excl = t.get("min_exclusive")
        max_excl = t.get("max_exclusive")
        if min_p is not None:
            if min_excl and not (p > min_p): continue
            if not min_excl and not (p >= min_p): continue
        if max_p is not None:
            if max_excl and not (p < max_p): continue
            if not max_excl and not (p <= max_p): continue
        return t
    return None


def compute_commission(
    *,
    base_amount: float,
    profitability_pct: Optional[float],
    plan: Dict[str, Any],
    major_discount: bool = False,
) -> Dict[str, Any]:
    """Ritorna {amount, tier_label, commission_pct, flat_fee, major_discount_applied,
                 pending_configuration, warnings, approval_required, entry_status}."""
    tiers = plan.get("tiers") or DEFAULT_TIERS
    tier = match_tier(tiers, profitability_pct)
    warnings: List[str] = []
    if tier is None:
        return {
            "amount": 0.0, "tier_label": None, "commission_pct": None, "flat_fee": None,
            "major_discount_applied": False, "pending_configuration": False,
            "warnings": ["Redditività non valutabile o nessuna fascia matching"],
            "approval_required": True, "entry_status": "estimated",
        }
    label = tier.get("label")
    pct = tier.get("commission_pct")
    flat = tier.get("flat_fee")
    max_with_ms = tier.get("max_pct_with_major_discount") or plan.get("major_discount_max_pct") or 5.0
    pending = bool(tier.get("pending_configuration"))
    approval = bool(tier.get("requires_approval"))

    if major_discount and pct is not None and pct > max_with_ms:
        warnings.append(
            f"Maggior sconto: commissione limitata al {max_with_ms}% (era {pct}%)."
        )
        pct = max_with_ms

    amount = 0.0
    if pct is not None:
        amount = base_amount * pct / 100.0
    elif flat is not None:
        amount = float(flat)
    elif pending:
        warnings.append("Valore gettone non configurato — commissione in pending_configuration.")
        amount = 0.0
    entry_status = "pending_configuration" if pending and flat is None else "estimated"
    return {
        "amount": round(amount, 2), "tier_label": label,
        "commission_pct": pct, "flat_fee": flat,
        "major_discount_applied": major_discount and pct is not None,
        "pending_configuration": pending and flat is None,
        "warnings": warnings, "approval_required": approval or pending,
        "entry_status": entry_status,
    }


def _detect_major_discount(quote_or_contract: Dict[str, Any]) -> bool:
    """Guarda se c'è almeno una discount_classification kind ∈ {major, exceptional}."""
    # Riga preventivo o riepilogo
    lines = (quote_or_contract.get("lines") or [])
    for l in lines:
        dc = l.get("discount_classification") or {}
        if dc.get("kind") in ("major", "exceptional"):
            return True
        if dc.get("affects_commission"):
            return True
    header_dc = quote_or_contract.get("discount_classification") or {}
    if header_dc.get("kind") in ("major", "exceptional") or header_dc.get("affects_commission"):
        return True
    return False


async def compute_profitability(
    *, tenant_id: str, contract_id: str,
) -> ProfitabilityBreakdown:
    """Calcola breakdown redditività. Se costi mancanti → costs_completeness=partial|missing."""
    db = get_db()
    ctr = await db.contracts.find_one({"_id": contract_id, "tenant_id": tenant_id, "deleted_at": None})
    if not ctr:
        return ProfitabilityBreakdown(contract_id=contract_id, costs_completeness="missing",
                                       blocking_reasons=["Contratto non trovato"])
    snap = ctr.get("quote_snapshot") or {}
    revenue_gross = float(snap.get("subtotal") or snap.get("total") or 0)
    # net = subtotal (dopo sconti applicati dalla logica quotes)
    revenue_net = float(snap.get("subtotal") or 0)
    # Aggreghiamo costi da bom_snapshot/parametric_snapshot per riga
    materials = 0.0
    labor = 0.0
    missing_categories: List[str] = []
    for line in (snap.get("lines") or []):
        bom = line.get("bom_snapshot") or line.get("parametric_snapshot") or {}
        mat = float(bom.get("materials_cost") or bom.get("unit_cost") or 0) * float(line.get("quantity", 1) or 1)
        materials += mat
        # labor cost approssimato = 10% del prezzo se non definito
        labor_cost = float(bom.get("labor_cost") or 0)
        labor += labor_cost * float(line.get("quantity", 1) or 1)
    installation = float(snap.get("installation_cost") or 0)
    transport = float(snap.get("transport_cost") or 0)
    external_processing = float(snap.get("external_processing_cost") or 0)
    if materials == 0:
        missing_categories.append("materiali")
    if labor == 0:
        missing_categories.append("manodopera")
    if installation == 0:
        missing_categories.append("posa")
    commissions_cost = float(snap.get("commissions_cost") or 0)
    variable_costs = materials + labor + installation + transport + external_processing + commissions_cost
    residual = revenue_net - variable_costs
    profitability = (residual / revenue_net * 100.0) if revenue_net > 0 else None
    completeness = "complete" if not missing_categories else ("partial" if len(missing_categories) < 3 else "missing")
    warnings: List[str] = []
    blocking: List[str] = []
    if completeness != "complete":
        warnings.append(f"Redditività non completamente verificabile: mancano {', '.join(missing_categories)}")
    if profitability is not None and profitability < 0:
        blocking.append("Redditività negativa — richiede doppia approvazione")
    return ProfitabilityBreakdown(
        contract_id=contract_id,
        revenue_gross=round(revenue_gross, 2),
        revenue_net=round(revenue_net, 2),
        variable_costs_total=round(variable_costs, 2),
        materials_cost=round(materials, 2),
        production_labor_cost=round(labor, 2),
        installation_cost=round(installation, 2),
        transport_cost=round(transport, 2),
        external_processing_cost=round(external_processing, 2),
        commissions_cost=round(commissions_cost, 2),
        residual_economic=round(residual, 2),
        profitability_pct=round(profitability, 2) if profitability is not None else None,
        costs_completeness=completeness,
        missing_cost_categories=missing_categories,
        warnings=warnings, blocking_reasons=blocking,
    )


async def get_active_plan(tenant_id: str, role: Optional[str] = None) -> Optional[Dict[str, Any]]:
    db = get_db()
    filt: Dict[str, Any] = {"tenant_id": tenant_id, "active": True, "deleted_at": None}
    if role:
        filt["role"] = role
    doc = await db.commission_plans.find_one(filt, sort=[("version", -1)])
    return doc


async def compute_and_persist_commission_estimate(
    *, tenant_id: str, contract_id: str, sales_rep_id: str,
) -> Dict[str, Any]:
    """Calcola e salva/aggiorna CommissionEntry (entry_status=estimated)."""
    db = get_db()
    plan = await get_active_plan(tenant_id)
    if not plan:
        # Piano di default in-memory
        plan = {"_id": None, "version": 1, "base": "contract_taxable",
                "tiers": DEFAULT_TIERS, "major_discount_max_pct": 5.0}

    profit = await compute_profitability(tenant_id=tenant_id, contract_id=contract_id)
    ctr = await db.contracts.find_one({"_id": contract_id, "tenant_id": tenant_id, "deleted_at": None})
    snap = (ctr or {}).get("quote_snapshot") or {}
    base_amount = float(snap.get("subtotal") or snap.get("total") or 0)
    major = _detect_major_discount(snap) or _detect_major_discount(ctr or {})
    comm = compute_commission(
        base_amount=base_amount, profitability_pct=profit.profitability_pct,
        plan=plan, major_discount=major,
    )
    # Upsert entry
    entry = await db.commission_entries.find_one({
        "tenant_id": tenant_id, "contract_id": contract_id,
        "sales_rep_id": sales_rep_id, "deleted_at": None,
        "entry_status": {"$in": ["estimated", "approved", "pending_configuration"]},
    })
    payload = {
        "plan_id": plan.get("_id"), "plan_version": plan.get("version", 1),
        "contract_id": contract_id, "customer_id": (ctr or {}).get("customer_id"),
        "quote_id": (ctr or {}).get("quote_id"),
        "sales_rep_id": sales_rep_id,
        "base_amount": base_amount, "base_kind": plan.get("base", "contract_taxable"),
        "profitability_pct": profit.profitability_pct,
        "tier_label": comm["tier_label"],
        "commission_pct": comm["commission_pct"], "flat_fee": comm["flat_fee"],
        "computed_amount": comm["amount"],
        "major_discount_applied": comm["major_discount_applied"],
        "entry_status": comm["entry_status"],
        "warnings": comm["warnings"],
        "approval_required": comm["approval_required"],
    }
    if entry:
        await db.commission_entries.update_one({"_id": entry["_id"]}, {"$set": payload})
        entry_id = entry["_id"]
    else:
        instance = CommissionEntry(tenant_id=tenant_id, **payload)
        doc = to_mongo(instance.model_dump(by_alias=True))
        await db.commission_entries.insert_one(doc)
        entry_id = instance.id
    return {"entry_id": entry_id, "profitability": profit.model_dump(), "commission": comm}


async def apply_collection_accrual(
    *, tenant_id: str, contract_id: str, collected_pct: float,
) -> int:
    """Aggiorna accrued_amount di tutte le entries del contratto in proporzione a collected_pct."""
    db = get_db()
    updated = 0
    async for e in db.commission_entries.find({
        "tenant_id": tenant_id, "contract_id": contract_id, "deleted_at": None,
    }):
        computed = float(e.get("computed_amount") or 0)
        # threshold configurato nel plan
        plan = await db.commission_plans.find_one({"_id": e.get("plan_id"), "tenant_id": tenant_id}) \
            if e.get("plan_id") else None
        threshold = float((plan or {}).get("accrual_after_collected_pct") or 50.0)
        if collected_pct >= threshold:
            accrual_pct = min(100.0, collected_pct)
            accrued = computed * accrual_pct / 100.0
            new_status = "invoiceable" if collected_pct >= 100 else "accrued"
            await db.commission_entries.update_one(
                {"_id": e["_id"]},
                {"$set": {"accrual_pct": accrual_pct, "accrued_amount": round(accrued, 2),
                          "entry_status": new_status}},
            )
            updated += 1
    return updated


async def reverse_commission_on_cancellation(
    *, tenant_id: str, contract_id: str, reason: str = "Contratto annullato",
) -> int:
    """Crea CommissionAdjustment append-only di storno."""
    from app.models_commissions import CommissionAdjustment
    db = get_db()
    n = 0
    async for e in db.commission_entries.find({
        "tenant_id": tenant_id, "contract_id": contract_id, "deleted_at": None,
        "entry_status": {"$in": ["estimated", "approved", "accrued", "invoiceable"]},
    }):
        adj = CommissionAdjustment(
            tenant_id=tenant_id, entry_id=e["_id"],
            kind="reversal", amount=-float(e.get("computed_amount") or 0),
            reason=reason,
        )
        await db.commission_adjustments.insert_one(to_mongo(adj.model_dump(by_alias=True)))
        await db.commission_entries.update_one(
            {"_id": e["_id"]}, {"$set": {"entry_status": "reversed"}},
        )
        n += 1
    return n
