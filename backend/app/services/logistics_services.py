"""LOGISTICS SERVICES (PO patch): TRASPORTO IN CANTIERE (configurabile), TRASPORTO AL PIANO 2°-5° (800/500), GRU (1700/1400).
Prezzo cliente scontabile/azzerabile; costo interno MAI toccato dallo sconto; servizio azzerato resta in commessa (OMAGGIO)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

LOGISTICS_POLICY_VERSION = "logistics_services_v1_2026_10"
LOGISTICS_CATEGORY = "logistics"
FLOOR_HANDLING_MIN_FLOOR, FLOOR_HANDLING_MAX_FLOOR = 2, 5
ZERO_REASONS = ("omaggio commerciale", "trattativa cliente", "recupero disservizio", "autorizzazione direzione", "altro")
CATALOG_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "SITE_TRANSPORT": {"name": "Trasporto in cantiere", "customer_sale_price": None, "internal_reference_price": None, "status": "PRICING_RULE_TO_DEFINE",
                       "notes": "Servizio distinto e configurabile (PO patch logistica). Prezzo/costo da definire dall'Admin."},
    "FLOOR_HANDLING": {"name": "Trasporto al piano (dal 2° al 5° piano)", "customer_sale_price": 800.0, "internal_reference_price": 500.0, "status": "ACTIVE",
                       "notes": "PO: sale_price_base=800, internal_cost=500. Auto quando il cantiere è al piano 2-5."},
    "CRANE": {"name": "Gru", "customer_sale_price": 1700.0, "internal_reference_price": 1400.0, "status": "ACTIVE", "notes": "PO: sale_price_base=1700, internal_cost=1400."},
}


async def ensure_catalog(db, tenant_id: str) -> Dict[str, dict]:
    """Garantisce i 3 servizi in simple_services (categoria LOGISTICA, FIXED, discountable/zeroable). Idempotente; non sovrascrive prezzi già configurati."""
    from datetime import datetime, timezone
    from app.models import new_id
    out = {}
    for code, d in CATALOG_DEFAULTS.items():
        doc = await db.simple_services.find_one({"tenant_id": tenant_id, "code": code, "deleted_at": None})
        if not doc:
            doc = {"_id": new_id(), "tenant_id": tenant_id, "code": code, "category": "LOGISTICA", "pricing_unit": "FIXED", "vat_pct": 22, "description": "",
                   "discountable": True, "zeroable": True, "version": 1, "deleted_at": None, "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": None, **d}
            await db.simple_services.insert_one(doc)
        elif "discountable" not in doc:
            await db.simple_services.update_one({"_id": doc["_id"]}, {"$set": {"discountable": True, "zeroable": True}})
            doc.update({"discountable": True, "zeroable": True})
        out[code] = doc
    return out


def materialize(code: str, svc: dict, *, auto: bool, required: bool) -> Dict[str, Any]:
    std = svc.get("customer_sale_price")
    return {"code": code, "label": svc.get("name"), "service_id": svc.get("_id"), "standard_price": std, "customer_price": std, "internal_cost": svc.get("internal_reference_price"),
            "discountable": svc.get("discountable", True), "zeroable": svc.get("zeroable", True), "pricing_status": svc.get("status") or "ACTIVE",
            "auto": auto, "required": required, "removed_by_user": False, "price_history": [], "policy_version": LOGISTICS_POLICY_VERSION}


def site_floor_index(site: Optional[dict]) -> Optional[int]:
    if not site:
        return None
    raw = str(site.get("floor") or "").strip().lower()
    if raw in ("", "t", "pt", "terra", "piano terra", "0", "rialzato"):
        return 0
    digits = "".join(ch for ch in raw if ch.isdigit())
    return int(digits) if digits else None


def sync_auto(items: List[dict], catalog: Dict[str, dict], site: Optional[dict]) -> List[dict]:
    """FLOOR_HANDLING auto-aggiunto se piano 2..5 (required=True). Non duplica; rispetta la rimozione manuale solo se non required."""
    items = [dict(i) for i in items or []]
    floor = site_floor_index(site)
    need_fh = floor is not None and FLOOR_HANDLING_MIN_FLOOR <= floor <= FLOOR_HANDLING_MAX_FLOOR
    existing = {i["code"]: i for i in items}
    if need_fh:
        if "FLOOR_HANDLING" not in existing and "FLOOR_HANDLING" in catalog:
            items.append(materialize("FLOOR_HANDLING", catalog["FLOOR_HANDLING"], auto=True, required=True))
        elif "FLOOR_HANDLING" in existing:
            existing["FLOOR_HANDLING"]["required"] = True
    else:
        items = [i for i in items if not (i["code"] == "FLOOR_HANDLING" and i.get("auto") and not i.get("price_history"))]
        for i in items:
            if i["code"] == "FLOOR_HANDLING":
                i["required"] = False
    return items


def pseudo_lines(items: List[dict]) -> List[dict]:
    """Righe sintetiche per totali/IVA/margine (MAI salvate in quote.lines). Ricavo = prezzo cliente finale; costo = costo interno invariato."""
    out = []
    for i in items or []:
        if i.get("customer_price") is None:
            continue  # prezzo non configurato → non concorre ai totali (fail-closed sui prezzi mancanti)
        price = float(i["customer_price"])
        out.append({"id": f"logistics:{i['code']}", "category": LOGISTICS_CATEGORY, "category_code": LOGISTICS_CATEGORY, "description": i.get("label"), "quantity": 1,
                    "base_price": price, "unit_price": price, "subtotal_line": price, "line_total": price, "vat_rate": 0.22, "vat_class": "SERVICE",
                    "internal_cost": float(i.get("internal_cost") or 0), "logistics_code": i["code"], "is_logistics": True})
    return out


def discounted_base(items: List[dict]) -> float:
    """Base già scontata a livello servizio (SERVICE_LINE_DISCOUNT) → esclusa dal GLOBAL_QUOTE_DISCOUNT per evitare doppio sconto."""
    return round(sum(float(i["customer_price"]) for i in items or [] if i.get("customer_price") is not None and i.get("standard_price") is not None and float(i["customer_price"]) < float(i["standard_price"])), 2)


def customer_view(items: List[dict], is_admin: bool) -> List[dict]:
    out = []
    for i in items or []:
        v = {k: val for k, val in i.items() if k != "internal_cost" or is_admin}
        v["is_free"] = i.get("customer_price") is not None and float(i["customer_price"]) == 0
        v["has_service_discount"] = i.get("customer_price") is not None and i.get("standard_price") is not None and float(i["customer_price"]) < float(i["standard_price"])
        if not is_admin:
            v["price_history"] = [{k: h.get(k) for k in ("at", "user_email", "old_price", "new_price", "reason")} for h in i.get("price_history") or []]
        out.append(v)
    return out
