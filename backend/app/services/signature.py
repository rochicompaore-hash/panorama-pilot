"""M3.3.4 — Electronic Simple Signature (FES) service.

Responsibilities:
- Build the canonical evidence payload (sorted, deterministic JSON).
- Compute the evidence hash (sha256 of canonical bytes).
- Render the stamped PDF: base definitive PDF + last "Accettazione e firma" page.
- Store signature image + signed PDF in object storage (fallback: inline base64).

Design notes:
- We NEVER mutate the original definitive PDF or its snapshot.
- The evidence payload references (by hash) the original PDF and its snapshot.
- Signed PDF is a NEW quote_pdfs record with kind="signed".
"""
from __future__ import annotations
import base64
import hashlib
import io
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML
from pypdf import PdfReader, PdfWriter

from app.config import settings
from app.services.pdf_renderer import (
    TEMPLATE_DIR, _fmt_currency as _cur, _fmt_date as _dt, compute_pdf_hash,
    render_quote_pdf,
)

logger = logging.getLogger("signature")

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)
_env.filters["cur"] = _cur
_env.filters["dt"] = _dt


ROME = ZoneInfo("Europe/Rome")


def _short_id(hex_hash: str) -> str:
    return hex_hash[:8].upper()


def canonical_payload(*,
    quote: dict, pdf: dict, token: dict, otp: dict, signer: dict,
    consents: Dict[str, bool], signature_meta: Dict[str, Any],
    ip_hash: Optional[str], user_agent: Optional[str],
    clauses_version_hash: Optional[str], signed_at: datetime,
) -> Dict[str, Any]:
    """Return the canonical payload used to compute the evidence hash.

    All keys are sorted at serialization time. Everything critical to the signed
    outcome must be here — but personal data (email, ip) only in HASHED form.
    """
    return {
        "issuer": settings.SIGNATURE_EVIDENCE_ISSUER,
        "signature_type": "FES",
        "schema_version": 1,
        "quote": {
            "id": quote.get("_id") or quote.get("id"),
            "tenant_id": quote.get("tenant_id"),
            "number": quote.get("number"),
            "revision": quote.get("revision_label") or quote.get("revision"),
            "version": quote.get("version"),
        },
        "original_pdf": {
            "id": pdf.get("_id") or pdf.get("id"),
            "pdf_hash": pdf.get("pdf_hash"),
            "snapshot_hash": pdf.get("snapshot_hash"),
            "size_bytes": pdf.get("size_bytes"),
            "filename": pdf.get("filename"),
        },
        "public_token": {
            "id": token.get("_id") or token.get("id"),
            "hash_ref": token.get("token_hash", "")[:32],  # abridged reference; never full
        },
        "otp": {
            "request_id": otp.get("_id") or otp.get("id"),
            "recipient_hash": otp.get("recipient_hash"),
            "verified_at": _iso(otp.get("verified_at")),
            "channel": otp.get("channel"),
        },
        "signer": {
            "first_name": signer.get("first_name"),
            "last_name": signer.get("last_name"),
            "email_hash": signer.get("email_hash"),
            "fiscal_role": signer.get("fiscal_role"),
            "company_represented": signer.get("company_represented"),
        },
        "consents": consents,
        "clauses_version_hash": clauses_version_hash,
        "signature_capture": {
            "image_hash": signature_meta.get("image_hash"),
            "stroke_count": signature_meta.get("stroke_count"),
            "canvas_width": signature_meta.get("canvas_width"),
            "canvas_height": signature_meta.get("canvas_height"),
            "duration_ms": signature_meta.get("duration_ms"),
        },
        "context": {
            "ip_hash": ip_hash,
            "user_agent_hash": hashlib.sha256((user_agent or "").encode()).hexdigest()[:24] if user_agent else None,
        },
        "signed_at_utc": _iso(signed_at),
    }


def _iso(v):
    if v is None: return None
    if isinstance(v, str): return v
    if isinstance(v, datetime): return v.astimezone(timezone.utc).isoformat()
    return str(v)


def compute_evidence_hash(payload: Dict[str, Any]) -> str:
    """Deterministic sha256 of the canonical JSON payload."""
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


_PNG_DATAURL_RE = re.compile(r"^data:image/(png|jpeg);base64,(.+)$", re.IGNORECASE | re.DOTALL)


def parse_signature_data_url(data_url: str, max_bytes: int = 500_000) -> bytes:
    """Validate and decode a data URL to raw image bytes."""
    if not data_url or not isinstance(data_url, str):
        raise ValueError("empty_signature")
    m = _PNG_DATAURL_RE.match(data_url.strip())
    if not m:
        raise ValueError("invalid_signature_mime")
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except Exception:
        raise ValueError("invalid_signature_encoding")
    if len(raw) < 200:
        raise ValueError("signature_too_small")
    if len(raw) > max_bytes:
        raise ValueError("signature_too_large")
    return raw


def clauses_version_digest(clauses: List[dict]) -> str:
    """Deterministic digest of clauses list."""
    payload = [
        {"code": c.get("code"), "title": c.get("title"), "version": c.get("version"), "text": c.get("text")}
        for c in (clauses or [])
    ]
    payload.sort(key=lambda x: (x.get("code") or ""))
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def render_signed_pdf(
    *, base_snapshot: dict, base_watermark: Optional[str],
    signature: Dict[str, Any], evidence: Dict[str, Any],
) -> bytes:
    """Render the signed variant: original PDF (with footer stamp) + signature page appended.

    Strategy:
    1. Re-render the base quote PDF using the frozen snapshot, adding a discreet
       "Documento firmato elettronicamente — Evidence ID" footer to every page.
    2. Render the dedicated signature page separately (single page).
    3. Concatenate the two PDFs with pypdf. The original PDF stored in Object Storage
       is NEVER touched.
    """
    # 1) Base PDF with signed footer stamp
    base_bytes = render_quote_pdf(
        base_snapshot,
        watermark=base_watermark,
        signed_evidence_id=evidence.get("short_id"),
    )
    # 2) Signature page
    template = _env.get_template("quote_signed_pdf.html")
    html_str = template.render(
        snap=base_snapshot,
        watermark=None,  # never watermark the signature page itself
        signature=signature,
        evidence=evidence,
        now=datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M"),
    )
    sig_page_bytes = HTML(string=html_str, base_url=str(TEMPLATE_DIR)).write_pdf()
    # 3) Merge
    writer = PdfWriter()
    for reader_bytes in (base_bytes, sig_page_bytes):
        r = PdfReader(io.BytesIO(reader_bytes))
        for p in r.pages:
            writer.add_page(p)
    # Set some metadata
    writer.add_metadata({
        "/Title": f"{base_snapshot.get('quote', {}).get('number', '')} (firmato)",
        "/Producer": settings.SIGNATURE_EVIDENCE_ISSUER,
        "/Subject": f"Firmato elettronicamente - Evidence {evidence.get('short_id', '')}",
    })
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def local_display(dt_utc: datetime) -> str:
    try:
        return dt_utc.astimezone(ROME).strftime("%d/%m/%Y %H:%M (%Z)")
    except Exception:
        return dt_utc.strftime("%d/%m/%Y %H:%M UTC")


def build_signature_context(*, sig_doc: dict, evidence_payload: dict, evidence_hash: str, signed_at_utc: datetime,
                             signature_data_url: str) -> Dict[str, Any]:
    """Prepare the context dict passed to the signed-PDF template."""
    return {
        "signer_first_name": sig_doc["signer_first_name"],
        "signer_last_name": sig_doc["signer_last_name"],
        "signer_email_masked": sig_doc["signer_email_masked"],
        "signer_fiscal_role": sig_doc.get("signer_fiscal_role"),
        "signer_company_represented": sig_doc.get("signer_company_represented"),
        "signature_image_data_url": signature_data_url,
        "signed_at_utc": signed_at_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "signed_at_local": local_display(signed_at_utc),
        "signature_image_hash": sig_doc.get("signature_image_hash", ""),
        "clauses_version_hash": (sig_doc.get("clauses_version_hash") or "")[:16],
        "consents": sig_doc.get("consents", {}),
        "signature_type_label": "Firma Elettronica Semplice",
    }
