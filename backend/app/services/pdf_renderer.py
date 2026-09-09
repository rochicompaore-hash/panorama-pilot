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


def _services_included(quote: dict) -> List[dict]:
    """Solo servizi realmente inclusi (PO msg 626 §8). Nessun servizio dichiarato se escluso."""
    out: List[dict] = []
    if quote.get("installation_mode") == "SUPPLY_AND_INSTALLATION":
        out.append({"code": "INSTALLATION", "label": "Posa in opera"})
    if quote.get("dismantling_mode") == "INCLUDED":
        out.append({"code": "DISMANTLING", "label": "Smontaggio serramenti esistenti"})
    if quote.get("disposal_mode") == "INCLUDED":
        out.append({"code": "DISPOSAL", "label": "Smaltimento materiali di risulta"})
    enea = quote.get("enea_practice_code")
    if enea == "ENEA_STANDARD":
        out.append({"code": "ENEA_STANDARD", "label": "Pratica ENEA Standard"})
    elif enea == "ENEA_INSURED":
        out.append({"code": "ENEA_INSURED", "label": "Pratica ENEA Assicurata"})
    seen = {o["code"] for o in out}
    for l in quote.get("lines") or []:
        for svc in l.get("automatic_services") or []:
            t = (svc.get("service_type") or "").upper()
            if t == "PROFILATURA" and "PROFILING" not in seen:
                out.append({"code": "PROFILING", "label": "Profilatura perimetrale"}); seen.add("PROFILING")
        for svc in l.get("manual_extra_services") or []:
            code = f"EXTRA:{svc.get('service_code') or svc.get('service_name')}"
            if code not in seen and svc.get("service_name"):
                out.append({"code": code, "label": svc["service_name"]}); seen.add(code)
    return out


def build_snapshot(*, quote: dict, company: dict, template: dict, clauses: List[dict],
                   payment_terms: dict, kind: str = "definitive", general_terms: Optional[dict] = None) -> dict:
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
    # Quote subset — strip internal cost/margin + margin engine snapshots (§19 msg 392).
    # Never leak: financial_snapshot, technical_snapshot (contains total_internal_cost,
    # components, glass_cost...), pricing_snapshot (contains technical_snapshot too),
    # nor any margin/commission field. Applies at both quote and line level.
    _FORBIDDEN_LINE_KEYS = (
        "internal_cost", "margin", "margin_abs", "margin_pct", "cost_price",
        "technical_snapshot", "financial_snapshot", "pricing_snapshot",
    )
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
        "site": quote.get("site_snapshot"),
        "sales_rep": quote.get("sales_rep_snapshot") or {"name": quote.get("sales_rep_name")},
        "openings": quote.get("openings") or [],
        "environments": quote.get("environments") or [],
        "lines": [
            {k: v for k, v in l.items() if k not in _FORBIDDEN_LINE_KEYS}
            for l in (quote.get("lines") or [])
        ],
        "subtotal": quote.get("subtotal"),
        # msg 402 — payment terms / delivery policy / sconto pagamento (solo dati cliente, nessun dato interno)
        "commercial_subtotal": quote.get("commercial_subtotal") or 0,
        "global_discount_amount": quote.get("global_discount_amount") or 0,
        "global_discount_label": ("Sconto promozionale" if quote.get("promo_code") else f"Sconto {float(quote.get('global_discount_value') or 0):g}%") if (quote.get("global_discount_amount") or 0) > 0 else None,
        "payment_terms_code": quote.get("payment_terms_code"),
        "payment_terms_label": quote.get("payment_terms_label"),
        "payment_schedule": quote.get("payment_schedule") or [],
        "automatic_discount_percent": quote.get("automatic_discount_percent") or 0,
        "payment_discount_amount": quote.get("payment_discount_amount") or 0,
        "subtotal_before_payment_discount": quote.get("subtotal_before_payment_discount") or 0,
        "financing_mode": quote.get("financing_mode"),
        "delivery_mode": quote.get("delivery_mode"),
        "delivery_customer_text": quote.get("delivery_customer_text"),
        "delivery_surcharge_percent": quote.get("delivery_surcharge_percent") or 0,
        "delivery_surcharge_amount": quote.get("delivery_surcharge_amount") or 0,
        "installation_mode": quote.get("installation_mode"),
        "dismantling_mode": quote.get("dismantling_mode"),
        "vat_amount": quote.get("vat_amount"),
        "total": quote.get("total"),
        "vat_breakdown": _compute_vat_breakdown(quote.get("lines") or [], float(quote.get("subtotal") or 0)),
        "notes": quote.get("notes"),
        "version": quote.get("version"),
        "visual_schemes": _build_visual_schemes(quote),
        "services_included": _services_included(quote),
        "delivery_label": ("Consegna standard" if (quote.get("delivery_mode") or "STANDARD") == "STANDARD" else "Consegna accelerata"),
        "general_terms_version": (general_terms or {}).get("version"),
        "general_terms_snapshot_id": (general_terms or {}).get("id"),
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
        "general_terms": general_terms,
    }


def _visual_details(spec: dict) -> str:
    pt = spec.get("product_type")
    parts = [f"L × H {spec.get('width_mm')}×{spec.get('height_mm')} mm", f"q.tà {spec.get('quantity') or 1}"]
    if pt in ("WINDOW", "DOOR_WINDOW"):
        n = spec.get("sash_count") or 1
        parts.append(f"{n} ant{'a' if n == 1 else 'e'}")
        oc = spec.get("opening_configuration")
        parts.append({"ANTA_RIBALTA": "anta-ribalta", "FISSA": "fissa", "FIXED": "fissa"}.get(oc, "battente"))
        gt = spec.get("glass_type") or ""
        parts.append(("vetro triplo" if "TRIPLE" in gt else "vetro doppio") + (" satinato" if "SATIN" in gt else ""))
        parts.append(f"interno {spec.get('interior_color_code')} {spec.get('interior_color_name') or ''}".strip())
        parts.append(f"esterno {spec.get('exterior_color_code')} {spec.get('exterior_color_name') or ''}".strip())
    elif pt == "ROLLER_BOX":
        d = spec.get("roller_box_dimensions") or {}
        if d.get("depth_mm"):
            parts.append(f"profondità {d['depth_mm']} mm")
        parts.append("con cielino" if d.get("ceiling_liner") == "SI" else "senza cielino")
        c = spec.get("roller_box_color") or {}
        if c.get("code"):
            parts.append(f"colore {c['code']} {c.get('name') or ''}".strip())
    else:
        if spec.get("exterior_color_code"):
            parts.append(f"colore {spec['exterior_color_code']}")
        if spec.get("orientable"):
            parts.append("lamelle orientabili")
    return " · ".join(parts)


def _build_visual_schemes(quote: dict) -> List[dict]:
    """Una visual grande per configurazione (dedup su spec identico), con elenco posizioni/vani."""
    openings = {o.get("id"): o for o in (quote.get("openings") or [])}
    schemes: Dict[str, dict] = {}
    for l in quote.get("lines") or []:
        vs = l.get("visual_spec") or {}
        spec = vs.get("spec")
        if not spec or not vs.get("svg_exterior"):
            continue
        key = json.dumps({k: v for k, v in spec.items() if k != "quantity"}, sort_keys=True)
        op = openings.get(l.get("opening_id")) or {}
        pos = op.get("code") or op.get("display_name") or "Riga aggiuntiva"
        if key not in schemes:
            schemes[key] = {
                "positions": [], "spec": spec, "description": l.get("description") or spec.get("product_name") or spec.get("product_type"),
                "product_type": spec.get("product_type"), "details": _visual_details(spec),
                "is_bicolor": bool(vs.get("is_bicolor")),
                "svg_exterior": vs.get("svg_exterior"), "svg_interior": vs.get("svg_interior"),
            }
        if pos not in schemes[key]["positions"]:
            schemes[key]["positions"].append(pos)
    return list(schemes.values())


def _compute_vat_breakdown(lines: List[dict], net_subtotal: float = 0.0) -> List[dict]:
    """Group by VAT rate → [{rate, taxable, tax, total}].
    Gli imponibili di riga vengono riproporzionati sull'imponibile netto (sconti globali/pagamento/consegna)
    così che IVA e totale del PDF coincidano con quote.vat_amount / quote.total."""
    gross = sum(float(l.get("subtotal_line") or 0) for l in lines)
    factor = (net_subtotal / gross) if (gross > 0 and net_subtotal > 0) else 1.0
    buckets: Dict[float, Dict[str, float]] = {}
    for l in lines:
        rate = float(l.get("vat_rate") or 0.22)
        taxable = float(l.get("subtotal_line") or 0) * factor
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
