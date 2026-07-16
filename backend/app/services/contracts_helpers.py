"""Helpers to keep `routers/contracts.py` methods small and focused.
Behaviour-preserving extractions from `generate_from_quote` and `public_sign`.
"""
from __future__ import annotations
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from fastapi import HTTPException

from app.mongo_utils import from_mongo


ALLOWED_QUOTE_STATUSES = ("sent", "accepted", "won", "active", "approved")


async def load_quote_or_400(db, tenant_id: str, quote_id: str) -> dict:
    quote = await db.quotes.find_one(
        {"_id": quote_id, "tenant_id": tenant_id, "deleted_at": None}
    )
    if not quote:
        raise HTTPException(404, "Preventivo non trovato")
    if quote.get("status") not in ALLOWED_QUOTE_STATUSES:
        raise HTTPException(
            400,
            f"Preventivo in stato {quote.get('status')}: deve essere sent/accepted/active",
        )
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
        }},
        upsert=True, return_document=True,
    )
    n = seq_doc.get("current", 1)
    padding = seq_doc.get("padding", 5)
    year = datetime.now(timezone.utc).year
    number = f"CT-{year}-{str(n).zfill(padding)}"
    return number, n, padding


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
    clauses = quote.get("clauses") or []

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quote_id": quote_id,
        "quote_number": quote.get("number"),
        "quote_revision": quote.get("revision", 0),
        "quote_totals": {
            "subtotal": quote.get("subtotal"), "discount": quote.get("discount"),
            "tax": quote.get("tax"), "total": quote.get("total"),
            "materials_cost": quote.get("materials_cost"),
            "margin": quote.get("margin"),
        },
        "environments": [from_mongo(e) for e in environments],
        "openings": [from_mongo(o) for o in openings],
        "products": [from_mongo(p) for p in opening_products],
        "company": {
            "name": company.get("name"), "vat": company.get("vat"),
            "address": company.get("address"), "email": company.get("email"),
            "phone": company.get("phone"), "logo_url": company.get("logo_url"),
        },
        "customer": from_mongo(customer) if customer else {},
        "clauses": clauses,
        "payment_terms": payment_terms,
        "_products_count": len(opening_products),
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
