"""Contract PDF service — reuses pdf_renderer (WeasyPrint) with contract template.

Genera due PDF:
  - **preview** (bozza, watermark "BOZZA") per revisione
  - **final** (firmato, watermark "FIRMATO") post-firma — immutabile, storage privato

Storage:
  - Usa `services.storage` (Local/S3 con signed URL)
  - Path: `contracts/{tenant}/{contract_id}/{kind}-{version}-{hash}.pdf`
  - Ogni PDF viene versionato (senza sovrascrivere)
"""
from __future__ import annotations
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from app.services.storage import get_storage, build_key

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)),
                    autoescape=select_autoescape(["html"]))


def render_contract_pdf(contract: Dict[str, Any], watermark: Optional[str] = None) -> bytes:
    """Render PDF contratto dai dati del contract + snapshot.

    Args:
        contract: doc contratto (con quote_snapshot dentro)
        watermark: None | "draft" | "signed"
    """
    snap = contract.get("quote_snapshot") or {}
    from app.services.general_terms_canonical import get_canonical
    gt = snap.get("general_terms") or get_canonical()
    economics = snap.get("economics") or {"vat_breakdown": [], "vat_regime": {"code": "22", "declaration_required": False}, "services_included": []}
    template = _env.get_template("contract_pdf.html")
    html_str = template.render(
        contract={
            "number": contract.get("number"),
            "version": contract.get("version", 1),
            "quote_number": snap.get("quote_number"),
            "contract_status": contract.get("contract_status"),
            "snapshot_hash": contract.get("snapshot_hash"),
            "signature_hash": contract.get("signature_hash"),
            "signature_type": contract.get("signature_type"),
            "signature_data_url": contract.get("signature_data_url"),
            "signed_at": contract.get("signed_at").isoformat() if contract.get("signed_at") else None,
            "signed_by_name": contract.get("signed_by_name"),
            "signed_by_email": contract.get("signed_by_email"),
            "signed_ip": contract.get("signed_ip"),
            "signed_ua": contract.get("signed_ua"),
        },
        snap=snap, gt=gt, economics=economics,
        lines=economics.get("lines") or [],
        company=snap.get("company") or {},
        customer=snap.get("customer") or {},
        quote={"site_address": (snap.get("customer") or {}).get("site_address") or snap.get("site_address")},
        environments=snap.get("environments") or [],
        products=snap.get("products") or [],
        payment_terms=(snap.get("payment_terms") if isinstance(snap.get("payment_terms"), dict) else {"description": snap.get("payment_terms")}) or {},
        totals=snap.get("quote_totals") or {},
        watermark=watermark,
        generated_at=datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC"),
    )
    pdf_bytes = HTML(string=html_str, base_url=str(TEMPLATE_DIR)).write_pdf()
    return pdf_bytes


def store_contract_pdf(tenant_id: str, contract_id: str, kind: str,
                        version: int, pdf_bytes: bytes) -> Dict[str, Any]:
    """Salva il PDF nello storage privato e ritorna metadata (key, hash, size)."""
    file_hash = hashlib.sha256(pdf_bytes).hexdigest()
    filename = f"{kind}-v{version}-{file_hash[:12]}.pdf"
    key = build_key(tenant_id, "contracts", contract_id, filename)
    storage = get_storage()
    storage.put(key, pdf_bytes, "application/pdf")
    return {
        "storage_key": key,
        "filename": filename,
        "hash": file_hash,
        "size_bytes": len(pdf_bytes),
        "kind": kind,
        "version": version,
        "generated_at": datetime.now(timezone.utc),
    }


def get_signed_url(key: str, expires_seconds: int = 900) -> Optional[str]:
    return get_storage().signed_url(key, expires_seconds)
