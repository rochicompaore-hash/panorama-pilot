"""Installation Mode + Standard Service Resolver V1 (msg 393).

Contract:
  * ``installation_mode`` a livello Quote:
      - ``SUPPLY_ONLY``            → nessun servizio automatico
      - ``SUPPLY_AND_INSTALLATION`` → resolver attivo
  * ``dismantling_mode`` (INCLUDED / EXCLUDED / NOT_APPLICABLE)
  * ``disposal_mode``    (INCLUDED / EXCLUDED / NOT_APPLICABLE)

Deterministic resolver:
  * Per ogni QuoteLine, in base a ``category_code``, ``pricing_model`` e alla
    ``configuration_snapshot`` (o ``product_config``), produce
    ``automatic_services[]`` con precedenza esatta (§5 msg 393).

§25 msg 393: NON modifica formule prodotto. Il servizio è aggiunto separatamente.
§14 msg 393: product multiplier NON tocca la posa.

Semantica costi (§16 msg 393):
  * ``internal_cost`` = ``simple_services.internal_reference_price`` (interpretazione
    Enerhia V1: proxy del costo aziendale interno per la posa; documentato in
    /app/memory/QUOTE_INSTALLATION_MODE_V1.md).
  * ``customer_sale_price`` = prezzo verso il cliente.

Fail-closed:
  * Se un DISPOSAL è ``INCLUDED`` ma il servizio ha ``pricing_status=NEEDS_PO_PRICING``
    → ``MISSING_DISPOSAL_PRICING`` (§8 msg 393).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

SERVICE_POLICY_VERSION = "installation_v1_2026_02"

INSTALLATION_MODES = {"SUPPLY_ONLY", "SUPPLY_AND_INSTALLATION"}
POLICY_MODES = {"INCLUDED", "EXCLUDED", "NOT_APPLICABLE"}
UNDERLIGHT_TYPES = {"NONE", "SINGLE", "DOUBLE"}


# ---------------------------------------------------------------------------
# Deterministic mapping — approved by PO (msg 393 §1-§5, §11-§14)
# ---------------------------------------------------------------------------
def resolve_window_install_code(config: Dict[str, Any]) -> Optional[str]:
    """Return the installation service code for a FORMULA_TECHNICAL window/door.

    Priority (§5 msg 393): underlight DOUBLE → SINGLE → SLIDING → FIXED →
    VASISTAS → 4 ante → 3 ante → 1/2 ante.
    """
    ul = (config.get("underlight_type") or "NONE").upper()
    if ul == "DOUBLE":
        return "INSTALL_WINDOW_UNDERLIGHT_DOUBLE"
    if ul == "SINGLE":
        return "INSTALL_WINDOW_UNDERLIGHT"

    wt = (config.get("window_type") or "").upper()
    if wt == "SLIDING" or wt == "SLIDING_DOOR_WINDOW":
        return "INSTALL_SLIDING"
    if wt == "FIXED":
        return "INSTALL_FIXED_WINDOW"
    if wt == "VASISTAS" or wt == "VASISTAS_ONLY_1_SASH":
        return "INSTALL_VASISTAS"

    n = int(config.get("number_of_sashes") or 0)
    if n >= 4:
        return "INSTALL_WINDOW_4_SASH"
    if n == 3:
        return "INSTALL_WINDOW_3_SASH"
    if n in (1, 2):
        return "INSTALL_WINDOW_1_2_SASH"
    # Fallback deterministico su 1/2 ante (le finestre standard)
    return "INSTALL_WINDOW_1_2_SASH"


# Cassonetto: doppio se width/height indicano una configurazione doppia oppure
# se ``config.assembly_type == "DOUBLE"``. Default SINGLE.
def resolve_cassonetto_install_code(config: Dict[str, Any]) -> str:
    at = (config.get("assembly_type") or "").upper()
    if at == "DOUBLE":
        return "INSTALL_ROLLER_BOX_DOUBLE"
    return "INSTALL_ROLLER_BOX_SINGLE"


def resolve_mosquito_install_code(config: Dict[str, Any]) -> str:
    at = (config.get("assembly_type") or "").upper()
    if at == "DOUBLE":
        return "INSTALL_MOSQUITO_DOUBLE"
    return "INSTALL_MOSQUITO"


CATEGORY_INSTALL_CODES: Dict[str, str] = {
    "TAPPARELLE": "INSTALL_ROLLER_KIT",
    "PERSIANE_SCURI": "INSTALL_SHUTTER_1_2_SASH",
    "PERSIANE": "INSTALL_SHUTTER_1_2_SASH",
    "PORTE_BLINDATE": "INSTALL_ARMORED_DOOR",
    "PORTE_INTERNE": "INSTALL_INTERIOR_DOOR_HINGED",
}

# Smontaggio per categoria/intervento SOSTITUZIONE (§11 msg 393)
DISMANTLING_CODES: Dict[str, str] = {
    "FINESTRE": "REMOVE_WINDOW",
    "PORTEFINESTRE": "REMOVE_WINDOW",
    "ZANZARIERE": "REMOVE_MOSQUITO",
    "TAPPARELLE": "REMOVE_ROLLER_KIT",
    "PERSIANE_SCURI": "REMOVE_SHUTTER",
    "PERSIANE": "REMOVE_SHUTTER",
    "CASSONETTI": "REMOVE_ROLLER_BOX",
    "PORTE_BLINDATE": "REMOVE_ARMORED_DOOR",
}

# Smaltimento per categoria — anagrafiche seedate con NEEDS_PO_PRICING (§7-§8)
DISPOSAL_CODES: Dict[str, str] = {
    "FINESTRE": "DISPOSAL_WINDOW",
    "PORTEFINESTRE": "DISPOSAL_WINDOW",
    "ZANZARIERE": "DISPOSAL_MOSQUITO",
    "TAPPARELLE": "DISPOSAL_ROLLER_KIT",
    "PERSIANE_SCURI": "DISPOSAL_SHUTTER",
    "PERSIANE": "DISPOSAL_SHUTTER",
    "CASSONETTI": "DISPOSAL_ROLLER_BOX",
}

DISPOSAL_SEEDS = [
    ("DISPOSAL_WINDOW",      "Smaltimento infissi"),
    ("DISPOSAL_ROLLER_BOX",  "Smaltimento cassonetti"),
    ("DISPOSAL_ROLLER_KIT",  "Smaltimento kit tapparelle"),
    ("DISPOSAL_SHUTTER",     "Smaltimento persiane"),
    ("DISPOSAL_MOSQUITO",    "Smaltimento zanzariere"),
]


def resolve_install_code_for_line(line: Dict[str, Any]) -> Optional[str]:
    """Deterministic dispatch: return the standard POSA service code for a line.

    - FORMULA_TECHNICAL → window/door service (with underlight priority).
    - GRID (cassonetti)  → INSTALL_ROLLER_BOX_SINGLE / DOUBLE.
    - AREA + category ZANZARIERE → INSTALL_MOSQUITO(_DOUBLE).
    - AREA + category TAPPARELLE → INSTALL_ROLLER_KIT.
    - Others by CATEGORY_INSTALL_CODES.
    Returns None if the line is a service/accessory (no auto-install).
    """
    cat = str(line.get("category_code") or "").upper()
    model = str(line.get("pricing_model") or "").upper()
    cfg = line.get("configuration_snapshot") or line.get("product_config") or {}

    # Services/accessories NEVER get an auto-install child (§7 msg 393).
    if cat in ("SERVIZI", "MONTAGGI_POSA", "ACCESSORI"):
        return None
    # Legacy quote lines without category_code — fall back to the simpler
    # category enum on the QuoteLine ("window"/"roller"/"screen"/...).
    if not cat:
        cat_legacy = str(line.get("category") or "").lower()
        if cat_legacy in ("installation", "posa", "disposal", "smaltimento",
                          "accessory", "accessori", "extra"):
            return None

    if model == "FORMULA_TECHNICAL":
        return resolve_window_install_code(cfg)
    if model == "GRID" or cat == "CASSONETTI":
        return resolve_cassonetto_install_code(cfg)
    if cat == "ZANZARIERE":
        return resolve_mosquito_install_code(cfg)
    if cat in CATEGORY_INSTALL_CODES:
        return CATEGORY_INSTALL_CODES[cat]
    return None


def resolve_dismantling_code_for_line(line: Dict[str, Any]) -> Optional[str]:
    cat = str(line.get("category_code") or "").upper()
    return DISMANTLING_CODES.get(cat)


def resolve_disposal_code_for_line(line: Dict[str, Any]) -> Optional[str]:
    cat = str(line.get("category_code") or "").upper()
    return DISPOSAL_CODES.get(cat)


# ---------------------------------------------------------------------------
# Service materialization — reads simple_services collection
# ---------------------------------------------------------------------------
async def _find_service(db, tenant_id: str, code: str) -> Optional[Dict[str, Any]]:
    return await db.simple_services.find_one({
        "tenant_id": tenant_id, "code": code, "deleted_at": None,
    })


def _materialize(service_doc: Dict[str, Any], service_type: str, quantity: float,
                 is_auto: bool = True) -> Dict[str, Any]:
    """Freeze a snapshot subdocument of an automatic/manual service on a QuoteLine."""
    qty = max(float(quantity or 1), 1.0)
    unit_sale = service_doc.get("customer_sale_price")
    unit_cost = service_doc.get("internal_reference_price")
    total_sale = round(float(unit_sale or 0) * qty + 1e-9, 2) if unit_sale is not None else None
    total_cost = round(float(unit_cost or 0) * qty + 1e-9, 2) if unit_cost is not None else None
    pricing_status = service_doc.get("status") or "ACTIVE"
    return {
        "id": str(uuid.uuid4()),
        "automatic": is_auto,
        "service_id": service_doc.get("_id"),
        "service_code": service_doc.get("code"),
        "service_name": service_doc.get("name"),
        "service_category": service_doc.get("category"),
        "service_type": service_type,  # POSA | SMONTAGGIO | SMALTIMENTO | MOTORIZZAZIONE | ACCESSORIO
        "pricing_unit": service_doc.get("pricing_unit"),
        "quantity": qty,
        "unit_sale_price": unit_sale,
        "unit_internal_reference_price": unit_cost,
        "sale_price_total": total_sale,
        "internal_cost_total": total_cost,
        "pricing_status": pricing_status,
        "service_policy_version": SERVICE_POLICY_VERSION,
    }


PROFILING_SALE_PER_ML = 8.00
PROFILING_POLICY_VERSION = "profiling_8_eur_ml_v1_msg402"
PROFILING_CATEGORIES = {"FINESTRE", "PORTEFINESTRE"}


def build_profiling_service(line: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """PROFILATURA (msg 402 §4-§5): perimeter_ml = 2×(L+H)/1000 · 8,00 €/ml · × qty (per finestra/portafinestra).
    Costo interno: NEEDS_PO_COSTING (non inventato) → internal_cost_total=None."""
    cat = str(line.get("category_code") or "").upper()
    if cat not in PROFILING_CATEGORIES or str(line.get("pricing_model") or "").upper() != "FORMULA_TECHNICAL":
        return None
    cfg = line.get("configuration_snapshot") or line.get("product_config") or {}
    w = float(cfg.get("width_mm") or line.get("width_mm") or 0)
    h = float(cfg.get("height_mm") or line.get("height_mm") or 0)
    if w <= 0 or h <= 0:
        return None
    qty = max(float(line.get("quantity") or 1), 1.0)
    perimeter_ml = round(2 * (w + h) / 1000.0 + 1e-9, 3)
    unit_sale = round(perimeter_ml * PROFILING_SALE_PER_ML + 1e-9, 2)
    return {
        "id": str(uuid.uuid4()), "automatic": True, "service_id": None,
        "service_code": "PROFILING", "service_name": f"Profilatura {perimeter_ml:.2f} ml × {PROFILING_SALE_PER_ML:.2f} €/ml",
        "service_category": "PROFILATURA", "service_type": "PROFILATURA", "pricing_unit": "PER_ITEM",
        "perimeter_ml": perimeter_ml, "sale_price_per_ml": PROFILING_SALE_PER_ML,
        "quantity": qty, "unit_sale_price": unit_sale, "unit_internal_reference_price": None,
        "sale_price_total": round(unit_sale * qty + 1e-9, 2), "internal_cost_total": None,
        "internal_cost_status": "NEEDS_PO_COSTING",
        "pricing_status": "ACTIVE", "service_policy_version": PROFILING_POLICY_VERSION,
    }


async def resolve_line_services(
    db,
    tenant_id: str,
    line: Dict[str, Any],
    installation_mode: str,
    dismantling_mode: str = "EXCLUDED",
    disposal_mode: str = "EXCLUDED",
    intervention_type: str = "new",
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Return ``(automatic_services, blocking_errors)`` for a single QuoteLine.

    Idempotent and deterministic — same inputs → same output.
    """
    services: List[Dict[str, Any]] = []
    errors: List[str] = []
    qty = float(line.get("quantity") or 1)

    if installation_mode != "SUPPLY_AND_INSTALLATION":
        return services, errors

    # ---- POSA principale ----
    install_code = resolve_install_code_for_line(line)
    if install_code:
        svc = await _find_service(db, tenant_id, install_code)
        if not svc:
            errors.append(f"MISSING_SERVICE:{install_code}")
        elif svc.get("customer_sale_price") is None or svc.get("internal_reference_price") is None:
            errors.append(f"NEEDS_PO_PRICING:{install_code}")
        else:
            services.append(_materialize(svc, "POSA", qty, is_auto=True))

    # ---- SMONTAGGIO — msg 399 §8: si applica ad ogni prodotto su misura
    # quando dismantling_mode=INCLUDED, indipendentemente dall'intervention_type.
    # La quantità del servizio segue la quantità della QuoteLine (§3, §5).
    if dismantling_mode == "INCLUDED":
        dcode = resolve_dismantling_code_for_line(line)
        if dcode:
            svc = await _find_service(db, tenant_id, dcode)
            if not svc:
                errors.append(f"MISSING_SERVICE:{dcode}")
            elif svc.get("customer_sale_price") is None or svc.get("internal_reference_price") is None:
                errors.append(f"NEEDS_PO_PRICING:{dcode}")
            else:
                services.append(_materialize(svc, "SMONTAGGIO", qty, is_auto=True))

    # ---- SMALTIMENTO (§7-§8) ----
    if disposal_mode == "INCLUDED":
        dcode = resolve_disposal_code_for_line(line)
        if dcode:
            svc = await _find_service(db, tenant_id, dcode)
            if not svc:
                errors.append(f"MISSING_DISPOSAL_PRICING:{dcode}")
            elif svc.get("customer_sale_price") is None or svc.get("internal_reference_price") is None \
                 or svc.get("status") == "NEEDS_PO_PRICING":
                # Fail-closed §8: mai smaltimento a 0
                errors.append(f"MISSING_DISPOSAL_PRICING:{dcode}")
            else:
                services.append(_materialize(svc, "SMALTIMENTO", qty, is_auto=True))
    return services, errors


# ---------------------------------------------------------------------------
# Line-level totals — installed into QuoteLine snapshot
# ---------------------------------------------------------------------------
def compute_services_totals(automatic: List[Dict[str, Any]],
                            manual: Optional[List[Dict[str, Any]]] = None) -> Dict[str, float]:
    """Sum sale/internal-cost totals across automatic + manual services."""
    all_svc = list(automatic or []) + list(manual or [])
    sale = sum(float(s.get("sale_price_total") or 0) for s in all_svc)
    cost = sum(float(s.get("internal_cost_total") or 0) for s in all_svc)
    return {
        "standard_services_sale_total": round(sale + 1e-9, 2),
        "standard_services_internal_cost_total": round(cost + 1e-9, 2),
    }


def bucket_for_service_type(service_type: str) -> str:
    """Map a service_type to the margin_engine bucket.

    Returns one of ``INSTALLATION`` | ``OTHER`` for use by
    ``margin_engine._extract_line_cost``.
    """
    t = (service_type or "").upper()
    if t in ("POSA", "MOTORIZZAZIONE"):
        return "INSTALLATION"
    # SMONTAGGIO / SMALTIMENTO / ACCESSORIO → OTHER_DIRECT_COSTS
    return "OTHER"


# ---------------------------------------------------------------------------
# Seed 5 DISPOSAL_* placeholder services (msg 393 §7)
# ---------------------------------------------------------------------------
async def seed_disposal_services(db, tenant_id: str) -> int:
    """Idempotently seed the 5 DISPOSAL_* services with NEEDS_PO_PRICING.

    Returns the count of newly inserted docs.
    """
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for code, name in DISPOSAL_SEEDS:
        exists = await db.simple_services.find_one({
            "tenant_id": tenant_id, "code": code, "deleted_at": None,
        })
        if exists:
            continue
        await db.simple_services.insert_one({
            "_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "code": code,
            "name": name,
            "category": "SMALTIMENTO",
            "description": "Placeholder — prezzi da confermare dal PO prima dell'uso.",
            "pricing_unit": "PER_ITEM",
            "internal_reference_price": None,
            "customer_sale_price": None,
            "vat_pct": 22.0,
            "valid_from": None, "valid_to": None,
            "status": "NEEDS_PO_PRICING",
            "quantity_rule": None,
            "suggested_for_recipes": [],
            "notes": "V1 msg 393 §7 — seed placeholder. Impostare i prezzi prima di attivare disposal_mode=INCLUDED.",
            "version": 1, "active": True,
            "created_at": now, "updated_at": now, "deleted_at": None,
        })
        inserted += 1
    return inserted
