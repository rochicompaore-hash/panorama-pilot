"""Commercial Packages — Enerhia Operating Core (Master Plan Packages V1).

BASE / ADVANCED / PREMIUM. Ogni pacchetto ha:
- proprio multiplier commerciale (NEEDS_PO_CONFIGURATION di default)
- proprie policy (origine, garanzia, posa, trasporto, piattaforma, smaltimento, ENEA, pulizia, Verisure)
- propri servizi inclusi / esclusi
- proprie regole di sconto

Il production_cost NON cambia con il pacchetto (§1). Solo il layer commerciale.
Servizi INCLUDED → customer_increment=0, internal_direct_cost>0 (§17).
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import get_db
from app.deps import require_permission

router = APIRouter(prefix="/commercial-packages", tags=["Commercial Packages"])


# =====================================================================
# SEED — Enerhia BASE / ADVANCED / PREMIUM (NEEDS_PO_CONFIGURATION su multiplier)
# =====================================================================
SEED_PACKAGES = [
    {
        "code": "BASE",
        "name": "Base",
        "description": "Pacchetto essenziale orientato alla convenienza.",
        "commercial_multiplier": None,   # NEEDS_PO_CONFIGURATION §25/§48
        "delivery_min_days": 120, "delivery_max_days": 180,  # 4-6 mesi
        "warranty_months": 24,
        "product_origin_policy": "FOREIGN_PREFERRED_OR_ALLOWED",
        "installation_policy": "INCLUDED",
        "installation_certification": None,
        "site_transport_policy": "INCLUDED",
        "floor_transport_policy": "EXCLUDED",
        "floor_transport_max_included_floor": None,
        "platform_policy": "EXCLUDED",
        "platform_max_included_floor": None,
        "platform_available_below_max_floor": False,
        "disposal_policy": "EXCLUDED",
        "enea_policy": "EXCLUDED",
        "final_cleaning_policy": "EXCLUDED",
        "priority_support_policy": "EXCLUDED",
        "security_partner_policy": "EXCLUDED",
        "security_partner_display_value": None,
        "included_services": [],
        "excluded_services": ["FLOOR_TRANSPORT", "DISPOSAL", "ENEA", "FINAL_CLEANING", "PRIORITY_SUPPORT", "VERISURE"],
        "compatible_categories": ["FINESTRE", "PORTE_INTERNE", "PORTE_BLINDATE"],
        "display_order": 10,
        "positioning_text": "Prodotto d'ingresso con posa inclusa.",
    },
    {
        "code": "ADVANCED",
        "name": "Advanced",
        "description": "Pacchetto completo, fornitura tendenzialmente italiana, gestione ampia dell'intervento.",
        "commercial_multiplier": None,
        "delivery_min_days": 90, "delivery_max_days": 120,
        "warranty_months": 120,
        "product_origin_policy": "ITALIAN_PREFERRED_EQUIVALENT_FOREIGN_ALLOWED",
        "installation_policy": "INCLUDED",
        "installation_certification": None,
        "site_transport_policy": "INCLUDED",
        "floor_transport_policy": "INCLUDED_UP_TO_LIMIT",
        "floor_transport_max_included_floor": 3,
        "platform_policy": "EXCLUDED",
        "platform_max_included_floor": None,
        "platform_available_below_max_floor": False,
        "disposal_policy": "INCLUDED",
        "enea_policy": "INCLUDED_BASIC",
        "final_cleaning_policy": "EXCLUDED",
        "priority_support_policy": "EXCLUDED",
        "security_partner_policy": "DISCOUNT",   # §10 Verisure benefit/sconto
        "security_partner_display_value": None,   # NEEDS_PO_CONFIGURATION valore sconto
        "included_services": ["INSTALLATION", "SITE_TRANSPORT", "FLOOR_TRANSPORT_UP_TO_3", "DISPOSAL", "ENEA_BASIC", "VERISURE_DISCOUNT"],
        "excluded_services": ["PLATFORM", "FINAL_CLEANING", "PRIORITY_SUPPORT"],
        "compatible_categories": ["FINESTRE", "PORTE_INTERNE", "PORTE_BLINDATE"],
        "display_order": 20,
        "positioning_text": "Fornitura italiana, tempi 90-120 giorni, benefit Verisure.",
    },
    {
        "code": "PREMIUM",
        "name": "Premium",
        "description": "Servizio chiavi in mano, fornitura 100% italiana, gestione protetta del cantiere.",
        "commercial_multiplier": None,
        "delivery_min_days": 30, "delivery_max_days": 30,
        "warranty_months": 180,
        "product_origin_policy": "ITALY_ONLY",
        "installation_policy": "INCLUDED",
        "installation_certification": "BGL",
        "site_transport_policy": "INCLUDED",
        "floor_transport_policy": "INCLUDED",
        "floor_transport_max_included_floor": None,
        "platform_policy": "INCLUDED_UP_TO_LIMIT",
        "platform_max_included_floor": 6,
        "platform_available_below_max_floor": True,   # §14 disponibile anche ai piani inferiori
        "platform_usage_reason": "PROTECTED_WINDOW_HANDLING",
        "disposal_policy": "INCLUDED",
        "enea_policy": "INCLUDED_ASSURED",
        "final_cleaning_policy": "INCLUDED",
        "priority_support_policy": "INCLUDED",
        "security_partner_policy": "FULL_PACKAGE",
        "security_partner_display_value": 299.0,   # §16 valore commerciale Verisure
        "included_services": ["INSTALLATION_BGL", "SITE_TRANSPORT", "FLOOR_TRANSPORT", "PLATFORM_UP_TO_6", "DISPOSAL", "ENEA_ASSURED", "FINAL_CLEANING", "PRIORITY_SUPPORT", "VERISURE_FULL"],
        "excluded_services": [],
        "compatible_categories": ["FINESTRE", "PORTE_INTERNE", "PORTE_BLINDATE"],
        "display_order": 30,
        "positioning_text": "Certificazione BGL, piattaforma inclusa, 15 anni garanzia, Verisure completo.",
    },
]


async def _ensure_seed(db, tenant_id: str) -> None:
    n = await db.commercial_packages.count_documents({"tenant_id": tenant_id, "deleted_at": None})
    if n:
        return
    now = datetime.now(timezone.utc).isoformat()
    for p in SEED_PACKAGES:
        await db.commercial_packages.insert_one({
            "_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            **p,
            "status": "ACTIVE",
            "valid_from": None, "valid_to": None,
            "discount_policy": None,   # PackageDiscountPolicy — configurable §33
            "minimum_contribution_margin_pct": None,   # §34
            "version": 1,
            "created_at": now, "updated_at": now,
            "deleted_at": None,
        })


class PackageUpdate(BaseModel):
    commercial_multiplier: Optional[float] = None
    delivery_min_days: Optional[int] = None
    delivery_max_days: Optional[int] = None
    warranty_months: Optional[int] = None
    security_partner_display_value: Optional[float] = None
    floor_transport_max_included_floor: Optional[int] = None
    platform_max_included_floor: Optional[int] = None
    minimum_contribution_margin_pct: Optional[float] = None
    positioning_text: Optional[str] = None
    status: Optional[str] = None


@router.get("")
async def list_packages(user: dict = Depends(require_permission("pricing_admin.manage"))):
    db = get_db()
    await _ensure_seed(db, user["tenant_id"])
    items = []
    async for d in db.commercial_packages.find(
        {"tenant_id": user["tenant_id"], "deleted_at": None}
    ).sort("display_order", 1):
        d["id"] = d.pop("_id")
        d["multiplier_status"] = "CONFIGURED" if d.get("commercial_multiplier") else "NEEDS_PO_CONFIGURATION"
        items.append(d)
    return {"items": items, "total": len(items)}


@router.get("/{pid}")
async def get_package(pid: str, user: dict = Depends(require_permission("pricing_admin.manage"))):
    db = get_db()
    doc = await db.commercial_packages.find_one({"_id": pid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Pacchetto non trovato")
    doc["id"] = doc.pop("_id")
    return doc


@router.patch("/{pid}")
async def update_package(pid: str, payload: PackageUpdate,
                          user: dict = Depends(require_permission("pricing_admin.manage"))):
    db = get_db()
    doc = await db.commercial_packages.find_one({"_id": pid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Pacchetto non trovato")
    upd = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    upd["updated_by"] = user.get("email") or user["id"]
    await db.commercial_packages.update_one({"_id": pid}, {"$set": upd, "$inc": {"version": 1}})
    return {"ok": True}


# =====================================================================
# SIMULATOR — comparazione 3 pacchetti su stesso production_cost (§24)
# =====================================================================
class SimulatorRequest(BaseModel):
    production_cost: float = Field(..., ge=0)
    included_services_internal_cost_map: Dict[str, float] = Field(default_factory=dict)
    # es. {"BASE": 30, "ADVANCED": 180, "PREMIUM": 450} — direct cost dei servizi inclusi per pacchetto
    withholding_applicable: bool = False


@router.post("/simulate")
async def simulate_packages(payload: SimulatorRequest,
                             user: dict = Depends(require_permission("pricing_admin.manage"))):
    """Confronta contribution margin dei 3 pacchetti per stesso production_cost.
    Se un multiplier non è configurato, il pacchetto ritorna
    `multiplier_status: NEEDS_PO_CONFIGURATION` e i calcoli sono null."""
    from app.routers.margin_control import (
        _compute_snapshot, _get_or_seed_rules, _get_or_seed_targets,
        FinancialSnapshotRequest,
    )
    db = get_db()
    await _ensure_seed(db, user["tenant_id"])
    rules = await _get_or_seed_rules(db, user["tenant_id"])
    targets = await _get_or_seed_targets(db, user["tenant_id"])

    packages: List[Dict[str, Any]] = []
    async for pkg in db.commercial_packages.find(
        {"tenant_id": user["tenant_id"], "deleted_at": None, "status": "ACTIVE"}
    ).sort("display_order", 1):
        code = pkg["code"]
        mult = pkg.get("commercial_multiplier")
        if mult is None:
            packages.append({
                "package_code": code,
                "package_name": pkg["name"],
                "multiplier_status": "NEEDS_PO_CONFIGURATION",
                "note": "Configurare commercial_multiplier via /api/commercial-packages/{id} prima di simulare.",
            })
            continue
        included_cost = float(payload.included_services_internal_cost_map.get(code, 0))
        req = FinancialSnapshotRequest(
            production_cost=payload.production_cost,
            commercial_multiplier=mult,
            installation_sale_price=0,      # incluso nel multiplier del pacchetto
            installation_internal_reference=included_cost,   # costo interno dei servizi inclusi
            withholding_applicable=payload.withholding_applicable,
        )
        snap = _compute_snapshot(req, rules, targets)
        packages.append({
            "package_code": code,
            "package_name": pkg["name"],
            "multiplier_status": "CONFIGURED",
            "multiplier": mult,
            "included_services_direct_cost": included_cost,
            "sale_price": snap["base_product_sale_price"],
            "customer_price_net_vat": snap["customer_price_net_vat"],
            "commission": snap["commercial_commission"],
            "contribution_margin_amount": snap["contribution_margin_amount"],
            "contribution_margin_pct": snap["contribution_margin_pct"],
            "withholding_cash_effect": snap["withholding_cash_effect"],
            "expected_available_cash": snap["expected_available_cash"],
            "margin_status": snap["margin_status"],
        })
    return {"production_cost": payload.production_cost, "packages": packages}
