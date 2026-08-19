"""Margin Control & Cash Flow — Enerhia Operating Core (Milestone Margin Control).

Modulo per il controllo economico-finanziario del preventivo.

Separazione rigorosa dei concetti:
- **PRODUCTION_COST**: solo BOM tecnica (mai include posa/commissione/ritenuta/fissi)
- **BASE_PRODUCT_SALE_PRICE**: production_cost × commercial_multiplier (default 3.00)
- **CUSTOMER_PRICE**: sale + posa + servizi + extra − sconto (netto IVA)
- **COMMERCIAL_COMMISSION**: costo diretto della vendita
  Formula Enerhia: `CUSTOMER_PRICE / 1.17 × 0.10`  (divisor+rate configurabili)
- **CONTRIBUTION_MARGIN**: net_revenue − costi diretti (commissione inclusa, **ritenuta esclusa**)
- **WITHHOLDING_CASH_EFFECT**: solo effetto cassa. **Non è costo economico**.
  Formula Enerhia: `CUSTOMER_PRICE / 1.22 × 0.11`  (applicable=YES/NO)
- **AVAILABLE_CASH**: contribution − withholding
- **REQUIRED_MONTHLY_CONTRIBUTION**: fissi + emergency + investment + profit target
- **MINIMUM_SUSTAINABLE_PRICE**: variable_costs / (1 − required_margin_rate)
- **DISCOUNT_ROOM**: list_price − minimum_sustainable_price
- **MARGIN_STATUS**: GREEN / YELLOW / ORANGE / RED (soglie configurabili)

Business rules Enerhia (configurabili, non hardcoded nel codice):
- commission_divisor = 1.17, commission_rate = 0.10
- withholding_divisor = 1.22, withholding_rate = 0.11
- default multiplier commerciale = 3.00

Costi fissi / emergency / investment / profit / revenue target restano
`NEEDS_PO_CONFIGURATION` finché l'Admin non li inserisce.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import get_db
from app.deps import require_permission


router = APIRouter(prefix="/margin-control", tags=["Margin Control"])


# =====================================================================
# DEFAULTS Enerhia (configurabili, non hardcoded)
# =====================================================================
DEFAULT_COMMISSION_RATE = Decimal("0.10")
DEFAULT_COMMISSION_DIVISOR = Decimal("1.17")
DEFAULT_WITHHOLDING_RATE = Decimal("0.11")
DEFAULT_WITHHOLDING_DIVISOR = Decimal("1.22")
DEFAULT_MULTIPLIER = Decimal("3.00")
DEFAULT_VAT_PCT = Decimal("22.00")

# Soglie semaforo di default (configurabili) — Master Plan §26
DEFAULT_STATUS_THRESHOLDS = {
    # % margine di contribuzione rispetto a required_margin_rate
    "green_over_target_pct":   Decimal("5"),   # +5% sopra target → GREEN
    "yellow_below_target_pct": Decimal("5"),   # entro -5% del target → YELLOW
    "orange_below_min_pct":    Decimal("0"),   # sopra minimum ma sotto target → ORANGE
    # sotto minimum sustainable → RED
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _q2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# =====================================================================
# CONFIG: business rules (commission / withholding)
# =====================================================================
class RulesPayload(BaseModel):
    commission_rate: Optional[float] = None
    commission_divisor: Optional[float] = None
    withholding_rate: Optional[float] = None
    withholding_divisor: Optional[float] = None
    default_commercial_multiplier: Optional[float] = None


async def _get_or_seed_rules(db, tenant_id: str) -> dict:
    doc = await db.margin_control_rules.find_one({"tenant_id": tenant_id, "deleted_at": None})
    if doc:
        return doc
    now = _now()
    doc = {
        "_id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "commission_rate": float(DEFAULT_COMMISSION_RATE),
        "commission_divisor": float(DEFAULT_COMMISSION_DIVISOR),
        "withholding_rate": float(DEFAULT_WITHHOLDING_RATE),
        "withholding_divisor": float(DEFAULT_WITHHOLDING_DIVISOR),
        "default_commercial_multiplier": float(DEFAULT_MULTIPLIER),
        "status_thresholds": {k: float(v) for k, v in DEFAULT_STATUS_THRESHOLDS.items()},
        "version": 1,
        "created_at": now, "updated_at": now, "deleted_at": None,
    }
    await db.margin_control_rules.insert_one(doc)
    return doc


@router.get("/rules")
async def get_rules(user: dict = Depends(require_permission("pricing_admin.manage"))):
    db = get_db()
    r = await _get_or_seed_rules(db, user["tenant_id"])
    return {k: v for k, v in r.items() if not k.startswith("_")}


@router.put("/rules")
async def update_rules(payload: RulesPayload,
                        user: dict = Depends(require_permission("pricing_admin.manage"))):
    db = get_db()
    r = await _get_or_seed_rules(db, user["tenant_id"])
    upd = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not upd:
        return {"ok": True, "no_changes": True}
    upd["updated_at"] = _now()
    upd["updated_by"] = user.get("email") or user["id"]
    await db.margin_control_rules.update_one({"_id": r["_id"]}, {"$set": upd, "$inc": {"version": 1}})
    return {"ok": True}


# =====================================================================
# TARGET AZIENDALI (fissi / emergency / investment / profit / revenue)
# =====================================================================
class CompanyTargetsPayload(BaseModel):
    monthly_fixed_costs: Optional[float] = None
    fixed_costs_breakdown: Optional[Dict[str, float]] = None  # rent, employees, utilities…
    emergency_fund_target: Optional[float] = None
    emergency_fund_current: Optional[float] = None
    emergency_fund_months_to_target: Optional[int] = None
    investment_fund_annual_target: Optional[float] = None
    investment_fund_current_allocated: Optional[float] = None
    investment_fund_months_remaining: Optional[int] = None
    monthly_profit_target: Optional[float] = None
    monthly_revenue_target: Optional[float] = None


async def _get_or_seed_targets(db, tenant_id: str) -> dict:
    doc = await db.margin_control_targets.find_one({"tenant_id": tenant_id, "deleted_at": None})
    if doc:
        return doc
    now = _now()
    # NON seedare valori: NEEDS_PO_CONFIGURATION (§45)
    doc = {
        "_id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "monthly_fixed_costs": None,
        "fixed_costs_breakdown": {},
        "emergency_fund_target": None,
        "emergency_fund_current": None,
        "emergency_fund_months_to_target": None,
        "investment_fund_annual_target": None,
        "investment_fund_current_allocated": None,
        "investment_fund_months_remaining": None,
        "monthly_profit_target": None,
        "monthly_revenue_target": None,
        "policy_status": "NEEDS_PO_CONFIGURATION",
        "version": 1,
        "created_at": now, "updated_at": now, "deleted_at": None,
    }
    await db.margin_control_targets.insert_one(doc)
    return doc


@router.get("/targets")
async def get_targets(user: dict = Depends(require_permission("pricing_admin.manage"))):
    db = get_db()
    t = await _get_or_seed_targets(db, user["tenant_id"])
    # Add derived values
    out = {k: v for k, v in t.items() if not k.startswith("_")}
    out.update(_derive_targets(t))
    return out


@router.put("/targets")
async def update_targets(payload: CompanyTargetsPayload,
                          user: dict = Depends(require_permission("pricing_admin.manage"))):
    db = get_db()
    t = await _get_or_seed_targets(db, user["tenant_id"])
    upd = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    upd["updated_at"] = _now()
    upd["updated_by"] = user.get("email") or user["id"]
    # Se tutti i target principali sono valorizzati, cambia status
    fully = all(
        (upd.get(k, t.get(k)) is not None)
        for k in ("monthly_fixed_costs", "monthly_revenue_target",
                    "emergency_fund_target", "investment_fund_annual_target",
                    "monthly_profit_target")
    )
    if fully:
        upd["policy_status"] = "CONFIGURED"
    await db.margin_control_targets.update_one({"_id": t["_id"]}, {"$set": upd, "$inc": {"version": 1}})
    return {"ok": True}


def _derive_targets(t: dict) -> dict:
    """Calcola valori derivati (fabbisogno mensile, required margin rate)."""
    out: Dict[str, Any] = {}
    fixed = t.get("monthly_fixed_costs")
    profit = t.get("monthly_profit_target")
    revenue = t.get("monthly_revenue_target")
    em_target = t.get("emergency_fund_target")
    em_current = t.get("emergency_fund_current") or 0
    em_months = t.get("emergency_fund_months_to_target")
    inv_target = t.get("investment_fund_annual_target")
    inv_current = t.get("investment_fund_current_allocated") or 0
    inv_months = t.get("investment_fund_months_remaining")

    if em_target is not None and em_months:
        remaining = max(float(em_target) - float(em_current), 0.0)
        out["monthly_emergency_allocation"] = round(remaining / em_months, 2)
    else:
        out["monthly_emergency_allocation"] = None

    if inv_target is not None and inv_months:
        remaining_i = max(float(inv_target) - float(inv_current), 0.0)
        out["monthly_investment_allocation"] = round(remaining_i / inv_months, 2)
    else:
        out["monthly_investment_allocation"] = None

    req = 0.0
    parts = []
    if fixed is not None: parts.append(float(fixed))
    if out["monthly_emergency_allocation"] is not None: parts.append(out["monthly_emergency_allocation"])
    if out["monthly_investment_allocation"] is not None: parts.append(out["monthly_investment_allocation"])
    if profit is not None: parts.append(float(profit))
    req = sum(parts) if parts else None
    out["required_monthly_contribution"] = round(req, 2) if req is not None else None

    if req is not None and revenue and float(revenue) > 0:
        out["required_margin_rate_pct"] = round(req / float(revenue) * 100, 4)
        out["required_margin_rate"] = round(req / float(revenue), 6)
    else:
        out["required_margin_rate_pct"] = None
        out["required_margin_rate"] = None
    return out


# =====================================================================
# FINANCIAL SNAPSHOT — cuore del modulo
# =====================================================================
class FinancialSnapshotRequest(BaseModel):
    # Input costi/prezzo (già calcolati dal motore pricing_v3 + servizi)
    production_cost: float = Field(..., ge=0)
    commercial_multiplier: Optional[float] = None      # default: da rules
    # Se il chiamante fornisce direttamente il base_product_sale_price, quel valore ha precedenza
    base_product_sale_price: Optional[float] = None
    # Servizi/posa (sale prices — customer_sale_price dei simple_services)
    installation_sale_price: float = 0.0
    installation_internal_reference: float = 0.0        # per contribution margin
    services_sale_price: float = 0.0
    services_internal_cost: float = 0.0
    other_direct_costs: float = 0.0                     # trasporti, esterni, extra
    logistics_direct_cost: float = 0.0
    external_services_cost: float = 0.0
    # Sconti (in EUR, applicati sul totale netto IVA)
    discount_amount: float = 0.0
    # IVA & ritenuta
    vat_pct: Optional[float] = None                     # default 22
    withholding_applicable: bool = False


class FinancialSnapshot(BaseModel):
    # Prezzi
    production_cost: float
    commercial_multiplier: float
    base_product_sale_price: float
    installation_sale_price: float
    services_sale_price: float
    gross_customer_price_pre_discount: float
    discount_amount: float
    customer_price_net_vat: float
    vat_pct: float
    vat_amount: float
    customer_price_gross: float
    # Commissione (business rule Enerhia)
    commission_rate: float
    commission_divisor: float
    commercial_commission: float
    # Contribution margin (economic view)
    installation_internal_reference: float
    services_internal_cost: float
    other_direct_costs: float
    contribution_margin_amount: float
    contribution_margin_pct: float
    # Cash flow view (withholding)
    withholding_applicable: bool
    withholding_rate: float
    withholding_divisor: float
    withholding_cash_effect: float
    withholding_receivable: float
    expected_available_cash: float
    # Minimum sustainable / discount room
    required_margin_rate: Optional[float]
    minimum_sustainable_price: Optional[float]
    discount_room_amount: Optional[float]
    max_theoretical_discount_pct: Optional[float]
    # Status semaforo
    margin_status: str   # GREEN / YELLOW / ORANGE / RED / POLICY_NOT_CONFIGURED
    margin_status_reason: str


def _compute_snapshot(req: FinancialSnapshotRequest, rules: dict, targets: dict) -> Dict[str, Any]:
    """Motore di calcolo. NON tocca il DB. Ritorna dict pronto per la serializzazione."""
    PC = Decimal(str(req.production_cost))
    mult = Decimal(str(req.commercial_multiplier)) if req.commercial_multiplier is not None \
        else Decimal(str(rules.get("default_commercial_multiplier", DEFAULT_MULTIPLIER)))

    if req.base_product_sale_price is not None:
        BPS = Decimal(str(req.base_product_sale_price))
    else:
        BPS = PC * mult

    install_sale = Decimal(str(req.installation_sale_price))
    services_sale = Decimal(str(req.services_sale_price))
    discount = Decimal(str(req.discount_amount))

    gross_pre = BPS + install_sale + services_sale
    net_vat = gross_pre - discount              # customer_price_net_vat
    vat_pct = Decimal(str(req.vat_pct if req.vat_pct is not None else DEFAULT_VAT_PCT))
    vat_amount = net_vat * vat_pct / Decimal("100")
    gross = net_vat + vat_amount

    # Commissione (business rule Enerhia): CUSTOMER_PRICE / 1.17 × 0.10
    # Interpretazione operativa: "CUSTOMER_PRICE" = customer_price_net_vat
    commission_rate = Decimal(str(rules.get("commission_rate", DEFAULT_COMMISSION_RATE)))
    commission_divisor = Decimal(str(rules.get("commission_divisor", DEFAULT_COMMISSION_DIVISOR)))
    commission = (net_vat / commission_divisor) * commission_rate if net_vat > 0 else Decimal("0")

    # Contribution margin (economic view, withholding ESCLUSA)
    install_ref = Decimal(str(req.installation_internal_reference))
    services_int = Decimal(str(req.services_internal_cost))
    other_direct = Decimal(str(req.other_direct_costs))
    logistics = Decimal(str(req.logistics_direct_cost))
    external = Decimal(str(req.external_services_cost))

    net_revenue = net_vat   # ricavo netto IVA (base per calcolo margine)
    contribution = (net_revenue - PC - install_ref - services_int
                     - other_direct - logistics - external - commission)
    contribution_pct = (contribution / net_revenue * Decimal("100")) if net_revenue > 0 else Decimal("0")

    # Cash flow view (withholding)
    wh_rate = Decimal(str(rules.get("withholding_rate", DEFAULT_WITHHOLDING_RATE)))
    wh_divisor = Decimal(str(rules.get("withholding_divisor", DEFAULT_WITHHOLDING_DIVISOR)))
    if req.withholding_applicable and net_vat > 0:
        wh_effect = (net_vat / wh_divisor) * wh_rate
    else:
        wh_effect = Decimal("0")
    # Available cash: contribution ridotto del cash effect della ritenuta
    # ma la ritenuta NON è costo economico (§10), è credito recuperabile
    available_cash = contribution - wh_effect
    wh_receivable = wh_effect   # tax credit (recuperabile futuro)

    # Minimum sustainable price
    req_margin_rate: Optional[Decimal] = None
    min_sustainable: Optional[Decimal] = None
    discount_room: Optional[Decimal] = None
    max_disc_pct: Optional[Decimal] = None

    targets_derived = _derive_targets(targets)
    if targets_derived.get("required_margin_rate") is not None:
        req_margin_rate = Decimal(str(targets_derived["required_margin_rate"]))
        # variable_costs = PC + install_ref + services_int + other_direct + logistics + external + commission
        var_costs = (PC + install_ref + services_int + other_direct + logistics + external + commission)
        # min_sustainable = var / (1 − required_margin_rate)  ma commission dipende da net_vat…
        # Approssimazione (Master Plan §22): non-recursive
        if req_margin_rate < Decimal("1"):
            min_sustainable = var_costs / (Decimal("1") - req_margin_rate)
            list_price = gross_pre
            discount_room = list_price - min_sustainable
            if list_price > 0:
                max_disc_pct = (discount_room / list_price) * Decimal("100")

    # Margin status (semaforo)
    status, reason = _compute_status(contribution_pct, req_margin_rate, rules.get("status_thresholds", {}))

    return {
        "production_cost": float(_q2(PC)),
        "commercial_multiplier": float(mult),
        "base_product_sale_price": float(_q2(BPS)),
        "installation_sale_price": float(_q2(install_sale)),
        "services_sale_price": float(_q2(services_sale)),
        "gross_customer_price_pre_discount": float(_q2(gross_pre)),
        "discount_amount": float(_q2(discount)),
        "customer_price_net_vat": float(_q2(net_vat)),
        "vat_pct": float(vat_pct),
        "vat_amount": float(_q2(vat_amount)),
        "customer_price_gross": float(_q2(gross)),
        "commission_rate": float(commission_rate),
        "commission_divisor": float(commission_divisor),
        "commercial_commission": float(_q2(commission)),
        "installation_internal_reference": float(_q2(install_ref)),
        "services_internal_cost": float(_q2(services_int)),
        "other_direct_costs": float(_q2(other_direct + logistics + external)),
        "contribution_margin_amount": float(_q2(contribution)),
        "contribution_margin_pct": float(_q2(contribution_pct)),
        "withholding_applicable": bool(req.withholding_applicable),
        "withholding_rate": float(wh_rate),
        "withholding_divisor": float(wh_divisor),
        "withholding_cash_effect": float(_q2(wh_effect)),
        "withholding_receivable": float(_q2(wh_receivable)),
        "expected_available_cash": float(_q2(available_cash)),
        "required_margin_rate": float(req_margin_rate) if req_margin_rate is not None else None,
        "minimum_sustainable_price": float(_q2(min_sustainable)) if min_sustainable is not None else None,
        "discount_room_amount": float(_q2(discount_room)) if discount_room is not None else None,
        "max_theoretical_discount_pct": float(_q2(max_disc_pct)) if max_disc_pct is not None else None,
        "margin_status": status,
        "margin_status_reason": reason,
    }


def _compute_status(contribution_pct: Decimal, required_rate: Optional[Decimal],
                     thresholds: Dict[str, Any]) -> tuple[str, str]:
    if required_rate is None:
        return "POLICY_NOT_CONFIGURED", "Costi fissi / target aziendali non ancora configurati (NEEDS_PO_CONFIGURATION)."
    required_pct = required_rate * Decimal("100")
    green_over = Decimal(str(thresholds.get("green_over_target_pct", DEFAULT_STATUS_THRESHOLDS["green_over_target_pct"])))
    yellow_below = Decimal(str(thresholds.get("yellow_below_target_pct", DEFAULT_STATUS_THRESHOLDS["yellow_below_target_pct"])))

    if contribution_pct < 0:
        return "RED", f"Margine negativo ({contribution_pct:.2f}%) — sotto prezzo minimo sostenibile."
    if contribution_pct >= required_pct + green_over:
        return "GREEN", f"Margine {contribution_pct:.2f}% ≥ target {required_pct:.2f}% + {green_over}%."
    if contribution_pct >= required_pct - yellow_below:
        return "YELLOW", f"Margine {contribution_pct:.2f}% vicino al target {required_pct:.2f}%."
    if contribution_pct >= 0:
        return "ORANGE", f"Margine {contribution_pct:.2f}% sotto target {required_pct:.2f}% — override autorizzabile."
    return "RED", "Margine insostenibile."


@router.post("/compute-snapshot")
async def compute_financial_snapshot(
    payload: FinancialSnapshotRequest,
    user: dict = Depends(require_permission("quotes.view")),
):
    """Calcola il financial snapshot per una configurazione. Non persiste."""
    db = get_db()
    rules = await _get_or_seed_rules(db, user["tenant_id"])
    targets = await _get_or_seed_targets(db, user["tenant_id"])
    return _compute_snapshot(payload, rules, targets)


@router.get("/company-dashboard")
async def company_dashboard(user: dict = Depends(require_permission("pricing_admin.manage"))):
    """Dashboard mensile: target aziendali + derived allocations. §36 Master Plan."""
    db = get_db()
    t = await _get_or_seed_targets(db, user["tenant_id"])
    r = await _get_or_seed_rules(db, user["tenant_id"])
    derived = _derive_targets(t)
    return {
        "targets": {k: v for k, v in t.items() if not k.startswith("_")},
        "derived": derived,
        "rules": {
            "commission_rate": r["commission_rate"],
            "commission_divisor": r["commission_divisor"],
            "withholding_rate": r["withholding_rate"],
            "withholding_divisor": r["withholding_divisor"],
            "default_commercial_multiplier": r["default_commercial_multiplier"],
        },
        "policy_status": t.get("policy_status", "NEEDS_PO_CONFIGURATION"),
    }
