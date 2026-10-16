"""Helpers to keep `routers/contracts.py` methods small and focused.
Behaviour-preserving extractions from `generate_from_quote` and `public_sign`.
"""
from __future__ import annotations
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from fastapi import HTTPException

from app.mongo_utils import from_mongo


ALLOWED_QUOTE_STATUSES = ("accepted", "approved", "signed")


async def load_quote_or_400(db, tenant_id: str, quote_id: str) -> dict:
    quote = await db.quotes.find_one(
        {"_id": quote_id, "tenant_id": tenant_id, "deleted_at": None}
    )
    if not quote:
        raise HTTPException(404, "Preventivo non trovato")
    st = quote.get("quote_status") or quote.get("status")
    if st not in ALLOWED_QUOTE_STATUSES:
        raise HTTPException(400, f"Preventivo in stato {st}: deve essere accepted/approved")
    return quote


async def assert_no_active_contract(db, tenant_id: str, quote_id: str) -> None:
    existing = await db.contracts.find_one({
        "tenant_id": tenant_id, "quote_id": quote_id,
        "contract_status": {"$nin": ["cancelled", "superseded", "rejected"]},
        "deleted_at": None,
    })
    if existing:
        raise HTTPException(
            400,
            f"Contratto già esistente per questo preventivo (id: {existing['_id']})",
        )


async def next_contract_number(db, tenant_id: str) -> tuple[str, int, int]:
    """Reserve next contract number. Returns (number, current, padding)."""
    seq_doc = await db.sequences.find_one_and_update(
        {"tenant_id": tenant_id, "type": "contract"},
        {"$inc": {"current": 1}, "$setOnInsert": {
            "tenant_id": tenant_id, "type": "contract",
            "prefix": "CT-", "padding": 5,
            "key": "contract_number_ct", "label": "Contratti (CT-)", "deleted_at": None,
        }},
        upsert=True, return_document=True,
    )
    n = seq_doc.get("current", 1)
    padding = seq_doc.get("padding", 5)
    year = datetime.now(timezone.utc).year
    number = f"CT-{year}-{str(n).zfill(padding)}"
    return number, n, padding


_FORBIDDEN_LINE_KEYS = ("internal_cost", "margin", "margin_abs", "margin_pct", "cost_price",
                        "technical_snapshot", "financial_snapshot", "pricing_snapshot", "simple_snapshot", "commercial_snapshot",
                        "position_internal_cost_total", "standard_services_internal_cost_total", "internal_cost_total",
                        "unit_internal_reference_price", "internal_cost_status")


def strip_internal(obj):
    """Rimozione ricorsiva di ogni chiave interna (costi/margini) dai payload customer-facing."""
    if isinstance(obj, dict):
        return {k: strip_internal(v) for k, v in obj.items()
                if k not in _FORBIDDEN_LINE_KEYS and "internal_cost" not in k and "purchase_cost" not in k and "commission" not in k}
    if isinstance(obj, list):
        return [strip_internal(x) for x in obj]
    return obj


def vat_regime_from_breakdown(vat_breakdown: list) -> Dict[str, Any]:
    rates = sorted({int(round(float(b.get("rate") or 0) * 100)) for b in vat_breakdown if float(b.get("taxable") or 0) > 0})
    if not rates:
        rates = [22]
    code = str(rates[0]) if len(rates) == 1 else "MISTA " + "/".join(str(r) for r in rates)
    return {"code": code, "rates": rates, "reduced": any(r < 22 for r in rates),
            "declaration_required": any(r < 22 for r in rates)}


def build_economic_snapshot(quote: dict) -> Dict[str, Any]:
    """Termini economici del preventivo accettato — mai ricostruiti dal catalogo corrente (msg 782 §13-§16)."""
    from app.services.pdf_renderer import _compute_vat_breakdown, _services_included, _build_visual_schemes
    lines = quote.get("lines") or []
    breakdown = _compute_vat_breakdown(lines, float(quote.get("subtotal") or 0))
    discount_total = float(quote.get("global_discount_amount") or 0) + float(quote.get("payment_discount_amount") or 0)
    return {
        "lines": [strip_internal(l) for l in lines],
        "visual_schemes": _build_visual_schemes(quote),
        "services_included": _services_included(quote),
        "commercial_subtotal": quote.get("commercial_subtotal") or 0,
        "global_discount_amount": quote.get("global_discount_amount") or 0,
        "global_discount_value": quote.get("global_discount_value") or 0,
        "payment_discount_amount": quote.get("payment_discount_amount") or 0,
        "delivery_surcharge_amount": quote.get("delivery_surcharge_amount") or 0,
        "discount_total": round(discount_total, 2),
        "subtotal": quote.get("subtotal") or 0,
        "vat_amount": quote.get("vat_amount") or 0,
        "total": quote.get("total") or 0,
        "vat_breakdown": quote.get("vat_breakdown") or breakdown,
        "vat_regime": vat_regime_from_breakdown(quote.get("vat_breakdown") or breakdown),
        # PO §7: il contratto eredita il regime IVA del preventivo (nessuna nuova scelta in fase contratto)
        "vat_mode": quote.get("vat_regime_applied") or quote.get("vat_regime") or "VAT_ORDINARY",
        "vat_rate": (quote.get("vat_breakdown") or [{}])[0].get("rate") if len(quote.get("vat_breakdown") or []) == 1 else None,
        "vat_reason": quote.get("vat_regime_reason"),
        "fiscal_validation_status": (quote.get("fiscal_dossier") or {}).get("vat_eligibility_status") or ("NOT_REQUIRED" if (quote.get("vat_regime") or "VAT_ORDINARY") == "VAT_ORDINARY" else "PENDING"),
        "fiscal_dossier": {k: (quote.get("fiscal_dossier") or {}).get(k) for k in ("requested_regime", "documentation_status", "customer_declaration", "vat_eligibility_status")},
        "delivery_lead_time_days": quote.get("delivery_lead_time_days"),
        "delivery_lead_time_class": quote.get("delivery_lead_time_class"),
        "delivery_lead_time_mixed": bool(quote.get("delivery_lead_time_mixed")),
        "payment_terms": {
            "code": quote.get("payment_terms_code") or quote.get("payment_terms"),
            "label": quote.get("payment_terms_label"),
            "schedule": quote.get("payment_schedule") or [],
            "financing_mode": quote.get("financing_mode"),
        },
        "delivery_mode": quote.get("delivery_mode"),
        "delivery_customer_text": quote.get("delivery_customer_text"),
        "installation_mode": quote.get("installation_mode"),
        "dismantling_mode": quote.get("dismantling_mode"),
        "disposal_mode": quote.get("disposal_mode"),
        "tax_deduction_requested": bool(quote.get("tax_deduction_requested")),
        "enea_practice_code": quote.get("enea_practice_code"),
    }


async def frozen_general_terms_for_contract(db, quote: dict) -> Dict[str, Any]:
    """Testo canonico integrale della GENERAL_TERMS_VERSION congelata sul preventivo (fallback: corrente)."""
    from app.services.general_terms import resolve_general_terms_for_quote
    from app.services.general_terms_canonical import get_canonical
    summary = await resolve_general_terms_for_quote(db, quote)
    canon = get_canonical(summary.get("version"))
    latest_pdf = await db.quote_pdfs.find_one(
        {"quote_id": quote["_id"], "tenant_id": quote["tenant_id"], "deleted_at": None},
        sort=[("generated_at", -1)],
    )
    return {**canon, "summary_snapshot_id": summary.get("id"), "summary_version": summary.get("summary_version"),
            "quote_snapshot_id": latest_pdf["_id"] if latest_pdf else None}


async def build_contract_snapshot(db, tenant_id: str, quote: dict,
                                  payment_terms: Dict[str, Any]) -> dict:
    """Assemble the immutable snapshot of a quote used for contract generation."""
    quote_id = quote["_id"]
    company = await db.companies.find_one(
        {"tenant_id": tenant_id, "deleted_at": None}
    ) or {}
    customer = None
    if quote.get("customer_id"):
        customer = await db.customers.find_one(
            {"_id": quote["customer_id"], "tenant_id": tenant_id}
        )
    environments = await db.quote_environments.find({
        "tenant_id": tenant_id, "quote_id": quote_id, "deleted_at": None,
    }).to_list(500)
    openings = await db.quote_openings.find({
        "tenant_id": tenant_id, "quote_id": quote_id, "deleted_at": None,
    }).to_list(500)
    opening_products = await db.opening_products.find({
        "tenant_id": tenant_id, "quote_id": quote_id, "deleted_at": None,
    }).to_list(2000)
    site = None
    if quote.get("site_id"):
        site = await db.sites.find_one({"_id": quote["site_id"], "tenant_id": tenant_id})
    clauses = quote.get("clauses") or []
    general_terms = await frozen_general_terms_for_contract(db, quote)
    economics = build_economic_snapshot(quote)
    payment_terms = payment_terms or economics["payment_terms"]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quote_id": quote_id,
        "quote_number": quote.get("number"),
        "quote_revision": quote.get("revision", 0),
        "quote_revision_id": f"{quote_id}#R{int(quote.get('revision') or 0):02d}",
        "quote_snapshot_id": general_terms.get("quote_snapshot_id"),
        "accepted_at": quote.get("accepted_at"),
        "general_terms": general_terms,
        "general_terms_version": general_terms["version"],
        "general_terms_hash": general_terms["general_terms_hash"],
        "general_terms_snapshot_id": general_terms.get("summary_snapshot_id"),
        "economics": economics,
        "quote_totals": {
            "subtotal": economics["subtotal"], "discount": economics["discount_total"],
            "tax": economics["vat_amount"], "total": economics["total"],
        },
        "environments": [from_mongo(e) for e in environments],
        "openings": [from_mongo(o) for o in openings],
        "products": [strip_internal(from_mongo(p)) for p in opening_products],
        "company": {
            "name": company.get("name"), "vat": company.get("vat"),
            "address": company.get("address"), "email": company.get("email"),
            "phone": company.get("phone"), "logo_url": company.get("logo_url"),
        },
        "customer": customer_party_snapshot(from_mongo(customer) if customer else (quote.get("customer_snapshot") or {})),
        "site": site_party_snapshot(from_mongo(site) if site else None, quote),
        "site_address": quote.get("site_address") or quote.get("site_snapshot"),
        "quote_summary": quote_summary(quote),
        "clauses": clauses,
        "payment_terms": payment_terms,
        "_products_count": len(opening_products),
    }


CUSTOMER_PARTY_KEYS = ("id", "customer_type", "first_name", "last_name", "company_name", "tax_code", "vat_number",
                       "email", "phone", "mobile", "address", "billing_address", "sdi_code", "pec", "legal_representative",
                       "customer_number", "code")
SITE_PARTY_KEYS = ("id", "site_number", "name", "street", "address", "city", "zip_code", "province", "country", "floor",
                   "notes_customer_safe", "access_notes")
# Chiavi formali modificabili in bozza (msg 803 §5). Tutto il resto → CONTRACT_REVISION_REQUIRED (§7).
CUSTOMER_EDITABLE_KEYS = ("first_name", "last_name", "company_name", "tax_code", "vat_number", "email", "phone", "mobile",
                          "address", "billing_address", "sdi_code", "pec", "legal_representative")
SITE_EDITABLE_KEYS = ("name", "street", "address", "city", "zip_code", "province", "country", "floor", "notes_customer_safe")


def customer_party_snapshot(c: Dict[str, Any]) -> Dict[str, Any]:
    return {k: c.get(k) for k in CUSTOMER_PARTY_KEYS if c.get(k) is not None}


def site_party_snapshot(site: Optional[Dict[str, Any]], quote: Dict[str, Any]) -> Dict[str, Any]:
    if site:
        return {k: site.get(k) for k in SITE_PARTY_KEYS if site.get(k) is not None}
    sa = quote.get("site_address") or quote.get("site_snapshot") or {}
    return {k: sa.get(k) for k in SITE_PARTY_KEYS if isinstance(sa, dict) and sa.get(k) is not None}


def quote_summary(quote: Dict[str, Any]) -> Dict[str, Any]:
    """Riepilogo leggibile prodotti + servizi del preventivo accettato (msg 803 §2/§11) — nessun dato interno."""
    items = []
    for l in quote.get("lines") or []:
        cfg = l.get("configuration_snapshot") or l.get("product_config") or {}
        items.append({
            "description": l.get("description"), "category": l.get("category"), "quantity": l.get("quantity"),
            "width_mm": l.get("width_mm"), "height_mm": l.get("height_mm"), "product_code": l.get("product_code"),
            "configuration": {k: v for k, v in cfg.items() if not any(x in str(k) for x in ("cost", "internal", "multiplier"))},
            "unit_price_final": l.get("unit_price_final"), "subtotal_line": l.get("subtotal_line"),
            "services": [{"service_code": s.get("service_code"), "service_type": s.get("service_type"), "label": s.get("label") or s.get("description"),
                          "quantity": s.get("quantity"), "sale_price_total": s.get("sale_price_total")}
                         for s in (l.get("automatic_services") or []) + (l.get("manual_extra_services") or [])],
            "enea_practice": bool(l.get("enea_practice")),
        })
    return {"items": items, "installation_mode": quote.get("installation_mode"), "dismantling_mode": quote.get("dismantling_mode"),
            "disposal_mode": quote.get("disposal_mode"), "enea_practice_code": quote.get("enea_practice_code"),
            "delivery_mode": quote.get("delivery_mode"), "delivery_customer_text": quote.get("delivery_customer_text"),
            "valid_until": quote.get("valid_until"), "customer_notes": quote.get("customer_notes") or quote.get("notes_customer")}


def presign_errors(contract: Dict[str, Any]) -> list:
    """PRE-FIRMA CHECK (msg 803 §18) — lista errori specifici; vuota = firmabile."""
    snap = contract.get("quote_snapshot") or {}
    cust = snap.get("customer") or {}
    site = snap.get("site") or {}
    eco = snap.get("economics") or {}
    errs = []
    is_company = str(cust.get("customer_type") or "").lower() in ("company", "business", "azienda")
    if is_company:
        if not cust.get("company_name"): errs.append("MISSING_CUSTOMER_COMPANY_NAME")
        if not cust.get("vat_number"): errs.append("MISSING_CUSTOMER_VAT_NUMBER")
    else:
        if not (cust.get("first_name") and cust.get("last_name")): errs.append("MISSING_CUSTOMER_NAME")
        if not cust.get("tax_code"): errs.append("MISSING_CUSTOMER_TAX_CODE")
    if not (cust.get("address") or cust.get("billing_address")): errs.append("MISSING_CUSTOMER_ADDRESS")
    if not (cust.get("email") or cust.get("phone") or cust.get("mobile")): errs.append("MISSING_CUSTOMER_CONTACT")
    if not (site.get("street") or site.get("address") or (isinstance(snap.get("site_address"), dict) and snap["site_address"].get("street"))):
        errs.append("MISSING_SITE_ADDRESS")
    if not (eco.get("lines") or snap.get("products")): errs.append("MISSING_PRODUCTS")
    if float(eco.get("total") or 0) <= 0: errs.append("MISSING_TOTAL")
    if eco.get("vat_amount") is None: errs.append("MISSING_VAT")
    if not ((eco.get("payment_terms") or {}).get("code") or (snap.get("payment_terms") or {}).get("code")): errs.append("MISSING_PAYMENT_TERMS")
    if not snap.get("general_terms_version"): errs.append("MISSING_GENERAL_TERMS_VERSION")
    return errs


def build_signed_snapshot(contract: Dict[str, Any], when: datetime) -> Dict[str, Any]:
    """Congelamento definitivo alla firma (msg 803 §12)."""
    snap = contract.get("quote_snapshot") or {}
    eco = snap.get("economics") or {}
    return {
        "frozen_at": when.isoformat(),
        "customer_snapshot": snap.get("customer") or {},
        "site_snapshot": snap.get("site") or snap.get("site_address") or {},
        "product_snapshot": (snap.get("quote_summary") or {}).get("items") or [],
        "service_snapshot": eco.get("services_included") or [],
        "commercial_snapshot": {k: eco.get(k) for k in ("commercial_subtotal", "global_discount_amount", "global_discount_value",
                                                        "payment_discount_amount", "delivery_surcharge_amount", "discount_total", "subtotal", "total")},
        "payment_snapshot": eco.get("payment_terms") or snap.get("payment_terms") or {},
        "tax_snapshot": {"vat_amount": eco.get("vat_amount"), "vat_breakdown": eco.get("vat_breakdown"), "vat_regime": eco.get("vat_regime"),
                         "tax_deduction_requested": eco.get("tax_deduction_requested")},
        "general_terms_version": snap.get("general_terms_version") or contract.get("general_terms_version"),
        "general_terms_hash": contract.get("general_terms_hash"),
        "snapshot_hash": contract.get("snapshot_hash"),
    }


def compute_snapshot_hash(quote_id: str, contract_number: str,
                          quote_total, products_count: int) -> str:
    payload = f"{quote_id}|{contract_number}|{quote_total}|{products_count}"
    return hashlib.sha256(payload.encode()).hexdigest()


def build_signature_hash(contract_id: str, signer_name: str, ip: str, ua: str,
                         when: datetime, contract: dict) -> str:
    payload = (
        f"{contract_id}|{signer_name}|{ip}|{ua}|{when.isoformat()}|"
        f"{contract.get('number')}|{contract.get('snapshot_hash')}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def load_valid_signing_token(db, token: str) -> dict:
    tk = await db.contract_signing_tokens.find_one(
        {"_id": token, "consumed": False}
    )
    if not tk:
        raise HTTPException(404, "Token non valido o già consumato")
    exp = tk.get("expires_at")
    if exp:
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(410, "Token scaduto")
    return tk


async def verify_public_otp(db, otp_request_id: Optional[str], otp_code: str) -> bool:
    """Verifica OTP via services.otp; raise HTTPException on failure.
    Returns True se OTP valido. Nessun fallback silenzioso.
    In dev/test permette il codice "123456" senza request_id.
    """
    from app.services.otp import verify_otp as otp_verify
    from app.config import is_dev_or_test

    if otp_request_id:
        ok, reason, _ = await otp_verify(request_id=otp_request_id, code=otp_code)
        if not ok:
            raise HTTPException(400, f"OTP non valido: {reason}")
        return True
    # Fallback dev only
    if is_dev_or_test() and otp_code == "123456":
        return True
    raise HTTPException(400, "OTP request_id mancante (necessario in produzione)")
