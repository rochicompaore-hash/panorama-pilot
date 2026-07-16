"""Access surcharges engine: valuta condizioni cantiere ⇒ maggiorazioni.

Regole applicate:
- piano (senza ascensore → maggiorazione per piano)
- ascensore inadeguato → supplemento
- piattaforma necessaria → costo giornaliero
- autorizzazioni comunali → pratica + diritti
- occupazione suolo pubblico
- ZTL / permessi

Nessuna cifra è hardcoded, tutte le regole sono in DB (`access_surcharge_rules`).
"""
from __future__ import annotations
from typing import Dict, List, Any, Tuple
from app.db import get_db
from app.mongo_utils import from_mongo
from app.models_product_types import (
    SiteConditions, SiteConditionsEvaluateRequest, SiteConditionsEvaluateResponse,
    AccessComplexity,
)


def _floor_index(cond: SiteConditions) -> int:
    m = {"basement": -1, "ground": 0, "raised": 1, "1st": 1, "2nd": 2, "3rd": 3,
         "higher": 4, "independent_house": 0}
    if cond.floor_level == "custom":
        return int(cond.floor_number_custom or 0)
    return m.get(cond.floor_level, 0)


async def evaluate_site_conditions(
    tenant_id: str,
    req: SiteConditionsEvaluateRequest,
) -> SiteConditionsEvaluateResponse:
    db = get_db()
    cond = req.conditions
    rules = await db.access_surcharge_rules.find(
        {"tenant_id": tenant_id, "active": True, "deleted_at": None}
    ).to_list(200)
    rules = [from_mongo(r) for r in rules]

    warnings: List[str] = []
    applied: List[Dict[str, Any]] = []
    total_price = 0.0
    total_cost = 0.0
    floor_idx = _floor_index(cond)
    n_pieces = max(1, int(req.num_pieces))

    def _apply(rule: dict, base_qty: float = 1.0, note: str = ""):
        nonlocal total_price, total_cost
        kind = rule.get("surcharge_kind") or "fixed"
        amt = float(rule.get("amount") or 0)
        cost = float(rule.get("cost_internal") or 0)
        if kind == "fixed":
            p = amt; c = cost
        elif kind == "per_floor":
            p = amt * max(0, floor_idx); c = cost * max(0, floor_idx)
        elif kind == "per_piece":
            p = amt * n_pieces; c = cost * n_pieces
        elif kind == "pct":
            # applica su base preventivo (non calcolabile qui) → warning
            p = 0; c = 0
            warnings.append(f"Regola % '{rule.get('label')}' da applicare sul totale preventivo lato client")
        elif kind == "actual_cost":
            p = amt; c = amt
            warnings.append(f"Regola '{rule.get('label')}' a consuntivo (costo stimato)")
        else:
            p = amt * base_qty; c = cost * base_qty
        applied.append({
            "rule_id": rule.get("id"), "code": rule.get("code"), "label": rule.get("label"),
            "trigger": rule.get("trigger"), "kind": kind,
            "customer_price": round(p, 2), "internal_cost": round(c, 2),
            "note": note,
        })
        total_price += p
        total_cost += c

    # 1) Piano senza ascensore
    if floor_idx >= 1 and not cond.has_elevator:
        for r in rules:
            if r.get("trigger") == "floor_no_elevator":
                _apply(r, base_qty=floor_idx, note=f"Piano {floor_idx} senza ascensore")

    # 2) Ascensore inadeguato
    if cond.has_elevator and not cond.elevator_adequate_size:
        for r in rules:
            if r.get("trigger") == "elevator_inadequate":
                _apply(r, note="Ascensore non adeguato")

    # 3) Piattaforma
    if cond.platform_status == "required":
        for r in rules:
            if r.get("trigger") == "platform_required":
                _apply(r, note="Piattaforma aerea necessaria")
        if not cond.platform_positionable:
            warnings.append("Piattaforma richiesta ma posizionamento non confermato: sopralluogo consigliato")

    # 4) ZTL
    if cond.ztl_zone and cond.ztl_permit_needed:
        for r in rules:
            if r.get("trigger") == "ztl":
                _apply(r, note="ZTL con permesso")

    # 5) Occupazione suolo pubblico
    if cond.public_soil_occupation_needed:
        for r in rules:
            if r.get("trigger") == "occupation_permit":
                _apply(r, note="Occupazione suolo pubblico")

    # 6) Autorizzazione comunale (gestita dall'azienda)
    if cond.municipal_authorization != "not_needed":
        if cond.authorization_managed_by == "company":
            for r in rules:
                if r.get("trigger") == "municipal_authorization":
                    _apply(r, note="Autorizzazione comunale gestita da azienda")
        elif cond.municipal_authorization == "needed_verify":
            warnings.append("Autorizzazione comunale da verificare")

    # 7) Complessità e classificazione
    complexity: AccessComplexity = "simple"
    if cond.platform_status == "required":
        complexity = "with_platform"
    elif floor_idx >= 3 and not cond.has_elevator:
        complexity = "complex"
    elif floor_idx >= 1 and not cond.has_elevator:
        complexity = "ordinary"
    elif cond.crane_needed or cond.glass_dismount_for_transport:
        complexity = "complex"
    if cond.platform_status in ("site_inspection_needed", "impossible_verify"):
        complexity = "to_verify"
        warnings.append("Sopralluogo necessario per confermare piattaforma/accessibilità")
    if not cond.truck_access or (cond.movement_difficulty == "hard" and not cond.photos):
        complexity = "not_quotable_without_survey"
        warnings.append("Preventivo NON emettibile senza sopralluogo: accesso mezzo o difficoltà elevate")

    is_quotable = complexity != "not_quotable_without_survey"
    risk = "low"
    if complexity in ("complex", "with_platform"):
        risk = "high"
    elif complexity == "ordinary":
        risk = "medium"
    elif complexity == "not_quotable_without_survey":
        risk = "critical"

    # Snapshot delle regole applicate nella conditions
    cond.access_complexity = complexity
    cond.risk_level = risk  # type: ignore
    cond.warnings = warnings
    cond.requires_site_inspection = (complexity in ("to_verify", "not_quotable_without_survey")) or (
        cond.platform_status in ("site_inspection_needed", "impossible_verify")
    )
    cond.requires_approval = complexity in ("complex", "with_platform")
    cond.surcharges_snapshot = applied
    cond.total_surcharge_customer = round(total_price, 2)
    cond.total_surcharge_internal_cost = round(total_cost, 2)

    return SiteConditionsEvaluateResponse(
        conditions=cond,
        surcharges_applied=applied,
        total_customer=round(total_price, 2),
        total_internal_cost=round(total_cost, 2),
        margin=round(total_price - total_cost, 2),
        warnings=warnings,
        is_quotable=is_quotable,
    )
