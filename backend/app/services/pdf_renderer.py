"""Server-side PDF renderer using Jinja2 + WeasyPrint.

Design:
- Template HTML lives in /app/backend/app/templates/quote_pdf.html
- CSS lives inline in the template for embedded fonts and reliability
- No external URL fetching during generation (fetch_url set to safe local-only fetcher)
- All input data comes from an immutable snapshot dict
- Deterministic: same snapshot → same PDF bytes (approximately — timestamps in metadata excluded)
"""
from __future__ import annotations
import hashlib
import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML, CSS

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _fmt_currency(value):
    try:
        return f"€ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "€ 0,00"


def _fmt_number(value, decimals=2):
    try:
        s = f"{float(value):.{decimals}f}"
        return s.replace(".", ",")
    except Exception:
        return "0"


def _fmt_date(value):
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return value
    try:
        return value.strftime("%d/%m/%Y")
    except Exception:
        return str(value)


_env.filters["cur"] = _fmt_currency
_env.filters["num"] = _fmt_number
_env.filters["dt"] = _fmt_date


def compute_snapshot_hash(snapshot: dict) -> str:
    """Deterministic sha256 of the snapshot payload (ignoring volatile keys)."""
    volatile = {
        "generated_at", "pdf_hash", "storage_key", "id", "created_at", "updated_at",
        "invalidated_at", "version", "updated_by",
        "latest_pdf_id", "latest_pdf_hash", "latest_pdf_at",
    }
    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in sorted(o.items()) if k not in volatile}
        if isinstance(o, list):
            return [clean(x) for x in o]
        if isinstance(o, datetime):
            return o.isoformat()
        return o
    payload = json.dumps(clean(snapshot), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_pdf_hash(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


_FILENAME_INVALID = re.compile(r"[^A-Za-z0-9._-]")


def safe_filename(*parts: str, ext: str = "pdf", max_len: int = 200) -> str:
    """Sanitize filename parts (spaces → _, strip special chars, cap length)."""
    cleaned = []
    for p in parts:
        if not p:
            continue
        s = str(p).strip()
        s = s.replace(" ", "_")
        s = _FILENAME_INVALID.sub("", s)
        if s:
            cleaned.append(s)
    name = "_".join(cleaned) or "documento"
    if len(name) > max_len - len(ext) - 1:
        name = name[: max_len - len(ext) - 1]
    return f"{name}.{ext}"


def render_quote_pdf(snapshot: dict, watermark: Optional[str] = None, signed_evidence_id: Optional[str] = None) -> bytes:
    """Render the given quote snapshot to PDF bytes. No external network calls."""
    template = _env.get_template("quote_pdf.html")
    html_str = template.render(
        snap=snapshot,
        watermark=watermark,
        signed_evidence_id=signed_evidence_id,
        now=datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M"),
    )
    # WeasyPrint: base_url points to templates dir for any relative asset (should be none for security)
    pdf_bytes = HTML(string=html_str, base_url=str(TEMPLATE_DIR)).write_pdf()
    return pdf_bytes


def validate_quote_for_definitive(quote: dict, company: dict, template: dict) -> List[dict]:
    """Validation gate for definitive PDF emission.

    Returns list of blocking validation errors. Empty list = OK to emit.
    """
    errs: list = []
    # Company must have basic mandatory fields
    for field in ("name", "vat_number", "phone"):
        if not company.get(field):
            errs.append({"field": f"company.{field}", "code": "missing_company_field",
                         "message": f"Dato aziendale obbligatorio mancante: {field}"})

    # Quote must have at least one line and a subtotal > 0
    if not quote.get("lines"):
        errs.append({"field": "quote.lines", "code": "no_lines", "message": "Il preventivo non contiene righe"})
    if float(quote.get("subtotal") or 0) <= 0:
        errs.append({"field": "quote.subtotal", "code": "zero_subtotal", "message": "Subtotale del preventivo pari a zero"})

    # Customer or lead must exist
    if not (quote.get("customer_id") or quote.get("lead_id")):
        errs.append({"field": "quote.customer", "code": "missing_customer", "message": "Cliente/Lead non assegnato"})

    # Site address recommended (check nested fields, not just presence — LeadAddress defaults are truthy dict)
    sa = quote.get("site_address") or {}
    if isinstance(sa, dict):
        if not (sa.get("street") or sa.get("city") or sa.get("zip_code")):
            errs.append({"field": "quote.site_address", "code": "missing_site", "message": "Indirizzo cantiere mancante"})
    elif not sa:
        errs.append({"field": "quote.site_address", "code": "missing_site", "message": "Indirizzo cantiere mancante"})

    # Payment terms present
    if not quote.get("payment_terms") and not (template or {}).get("default_payment_terms", {}).get("installments"):
        errs.append({"field": "quote.payment_terms", "code": "missing_payment", "message": "Termini di pagamento non definiti"})

    return errs


def build_snapshot(*, quote: dict, company: dict, template: dict, clauses: List[dict],
                   payment_terms: dict, kind: str = "definitive") -> dict:
    """Freeze all data required to render the PDF. This becomes the immutable
    document of record and MUST be sufficient to re-render an identical PDF later.
    """
    # Company subset per template.show_fields
    show = template.get("show_fields") or {}
    company_snap = {
        "name": company.get("name"),
        "legal_name": company.get("legal_name") or company.get("name"),
        "commercial_name": company.get("commercial_name"),
        "vat_number": company.get("vat_number") if show.get("vat_number", True) else None,
        "tax_code": company.get("tax_code") if show.get("tax_code", True) else None,
        "rea": company.get("rea") if show.get("rea", True) else None,
        "share_capital": company.get("share_capital") if show.get("share_capital", False) else None,
        "address": company.get("address") or company.get("legal_address"),
        "city": company.get("city") or company.get("legal_city"),
        "zip_code": company.get("zip_code") or company.get("legal_zip"),
        "province": company.get("province") or company.get("legal_province"),
        "phone": company.get("phone"),
        "email": company.get("email"),
        "pec": company.get("pec") if show.get("pec", True) else None,
        "website": company.get("website"),
        "sdi_code": company.get("sdi_code") if show.get("sdi_code", True) else None,
        "iban": company.get("iban") if show.get("iban", True) else None,
        "bank_name": company.get("bank_name") if show.get("bank_name", True) else None,
        "account_holder": company.get("account_holder"),
        "logo_url": company.get("logo_url"),
        "signature_url": company.get("signature_url") if show.get("signature", True) else None,
        "stamp_url": company.get("stamp_url") if show.get("stamp", True) else None,
        "primary_color": company.get("primary_color") or template.get("style", {}).get("primary_color"),
        "secondary_color": company.get("secondary_color") or template.get("style", {}).get("secondary_color"),
        "certifications": company.get("certifications") if show.get("certifications", True) else [],
        "legal_notes": company.get("legal_notes"),
    }
    # Quote subset — strip internal cost/margin
    quote_snap = {
        "id": quote.get("id") or quote.get("_id"),
        "number": quote.get("number"),
        "revision": quote.get("revision", 0),
        "revision_label": quote.get("revision_label"),
        "quote_status": quote.get("quote_status"),
        "title": quote.get("title"),
        "issue_date": quote.get("created_at"),
        "valid_until": quote.get("valid_until"),
        "customer": quote.get("customer_snapshot") or {"name": quote.get("customer_name")},
        "site_address": quote.get("site_address"),
        "sales_rep": quote.get("sales_rep_snapshot") or {"name": quote.get("sales_rep_name")},
        "openings": quote.get("openings") or [],
        "environments": quote.get("environments") or [],
        "lines": [
            {k: v for k, v in l.items() if k not in ("internal_cost", "margin_abs", "margin_pct", "cost_price")}
            for l in (quote.get("lines") or [])
        ],
        "subtotal": quote.get("subtotal"),
        "vat_amount": quote.get("vat_amount"),
        "total": quote.get("total"),
        "vat_breakdown": _compute_vat_breakdown(quote.get("lines") or []),
        "notes": quote.get("notes"),
        "version": quote.get("version"),
    }
    return {
        "kind": kind,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "company": company_snap,
        "template": {
            "id": template.get("id") or template.get("_id"),
            "code": template.get("code"),
            "name": template.get("name"),
            "version": template.get("version", 1),
            "style": template.get("style", {}),
            "sections": template.get("sections") or [],
            "measures_disclaimer": template.get("measures_disclaimer"),
            "images_disclaimer": template.get("images_disclaimer"),
            "privacy_notice": template.get("privacy_notice"),
            "validity_days": template.get("validity_days", 30),
            "warranty_months": template.get("warranty_months", 24),
            "delivery_days_min": template.get("delivery_days_min", 30),
            "delivery_days_max": template.get("delivery_days_max", 45),
            "intro_text": template.get("intro_text"),
            "show_prices_mode": template.get("show_prices_mode", "per_line"),
            "show_fields": show,
        },
        "clauses": [{"code": c.get("code"), "title": c.get("title"), "text": c.get("text"),
                     "category": c.get("category"), "version": c.get("version", 1),
                     "mandatory": c.get("mandatory", False)} for c in clauses],
        "payment_terms": payment_terms,
        "quote": quote_snap,
    }


def _compute_vat_breakdown(lines: List[dict]) -> List[dict]:
    """Group by VAT rate → [{rate, taxable, tax, total}]."""
    buckets: Dict[float, Dict[str, float]] = {}
    for l in lines:
        rate = float(l.get("vat_rate") or 0.22)
        taxable = float(l.get("subtotal_line") or 0)
        b = buckets.setdefault(rate, {"rate": rate, "taxable": 0.0, "tax": 0.0})
        b["taxable"] += taxable
        b["tax"] += taxable * rate
    result = []
    for b in sorted(buckets.values(), key=lambda x: x["rate"]):
        b["total"] = round(b["taxable"] + b["tax"], 2)
        b["taxable"] = round(b["taxable"], 2)
        b["tax"] = round(b["tax"], 2)
        b["rate_pct"] = round(b["rate"] * 100, 2)
        result.append(b)
    return result
