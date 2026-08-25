"""Margin Engine V1 — Commission bands + Financial Snapshot.

Consumes existing authoritative pricing snapshots on QuoteLine
(``technical_snapshot`` / ``simple_snapshot``). It NEVER recomputes
product pricing — that responsibility stays in ``pricing_v3`` and
``multi_category_pricing`` (§25 msg 392).

Policy (msg 392):
    PRE_COMMISSION_MARGIN = (NET_REVENUE - SUPPLY - INSTALL - OTHER) / NET_REVENUE * 100
    Band:  >=30 OTTIMO 15% · >=20 BUONO 10% · >=15 SUFFICIENTE 8% · >=8 SCARSO 5% · <8 CRITICO AUTHORIZATION_REQUIRED
    COMMISSION_BASE = NET_REVENUE_EX_VAT (fatturato imponibile)
    COMMISSION_GROSS = COMMISSION_BASE * COMMISSION_RATE  (only if band != CRITICO)
    FINAL_COMPANY_CONTRIBUTION = PRE_COMMISSION_CONTRIBUTION - COMMISSION_GROSS
    FINAL_COMPANY_MARGIN       = FINAL_COMPANY_CONTRIBUTION / NET_REVENUE * 100

CRITICO does NOT set commission_rate=0. It flags
``commission_status="AUTHORIZATION_REQUIRED"`` and leaves
``commission_rate=None`` / ``commission_gross=None``.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

MARGIN_POLICY_VERSION = "margin_policy_v1_2026_02"
COMMISSION_POLICY_VERSION = "commission_policy_v1_2026_02"
COMMISSION_BASE_POLICY = "NET_REVENUE_EX_VAT"

# Categories that count as installation service (msg 392 §7).
INSTALLATION_CATEGORIES = {"installation", "posa", "montaggio", "montaggi_posa"}
# Categories that count as OTHER_DIRECT_COSTS (not supply, not install).
OTHER_DIRECT_CATEGORIES = {"disposal", "smaltimento", "accessory", "accessori", "extra", "servizi"}


# ---------------------------------------------------------------------------
# Rounding — presentation only; internal math keeps full precision
# ---------------------------------------------------------------------------
def _r2(x: Optional[float]) -> Optional[float]:
    if x is None:
        return None
    return round(float(x) + 1e-9, 2)


def _r4(x: Optional[float]) -> Optional[float]:
    """4-decimal rounding for percentages (display formats 2 dp)."""
    if x is None:
        return None
    return round(float(x) + 1e-9, 4)


# ---------------------------------------------------------------------------
# Commission bands — pure function, no side effect
# ---------------------------------------------------------------------------
def resolve_band(margin_pct: Optional[float]) -> Tuple[str, Optional[float], str]:
    """Return (band_code, commission_rate_fraction, commission_status).

    ``commission_rate_fraction`` is None for CRITICO (§15 msg 392).
    """
    if margin_pct is None:
        return ("UNKNOWN", None, "NO_DATA")
    m = float(margin_pct)
    if m >= 30.0:
        return ("OTTIMO", 0.15, "OK")
    if m >= 20.0:
        return ("BUONO", 0.10, "OK")
    if m >= 15.0:
        return ("SUFFICIENTE", 0.08, "OK")
    if m >= 8.0:
        return ("SCARSO", 0.05, "OK")
    return ("CRITICO", None, "AUTHORIZATION_REQUIRED")


# ---------------------------------------------------------------------------
# Cost extraction per line (§6/§7)
# ---------------------------------------------------------------------------
def _line_qty(line: Dict[str, Any]) -> float:
    return float(line.get("quantity") or 0)


def _extract_line_cost(line: Dict[str, Any]) -> float:
    """Extract the internal/purchase cost for a single line.

    Priority chain (§6 msg 392) — consume authoritative snapshots:
      1) technical_snapshot.total_internal_cost  (FORMULA_TECHNICAL)
      2) simple_snapshot.purchase_total_cost     (already qty-multiplied)
      3) simple_snapshot.purchase_cost_per_item  * qty  (AREA_by_color: tapparelle/zanzariere)
      4) simple_snapshot.internal_production_cost_per_item * qty  (GRID: cassonetti)
      5) line.internal_cost * qty                (legacy fallback / manual services)
    Returns 0.0 if no cost data is available (transparent, not blocking).
    """
    qty = _line_qty(line)

    ts = line.get("technical_snapshot") or {}
    if isinstance(ts, dict):
        tic = ts.get("total_internal_cost")
        if tic is not None:
            # pricing_v3 total_internal_cost is per-line (already sized).
            # But in most snapshots it's per-item so multiply by qty when a
            # ``per_item`` flag isn't explicitly set. pricing_v3 v3 stores per unit.
            return float(tic) * qty

    ss = line.get("simple_snapshot") or {}
    if isinstance(ss, dict):
        ptc = ss.get("purchase_total_cost")
        if ptc is not None:
            return float(ptc)  # already qty-multiplied
        pcpi = ss.get("purchase_cost_per_item")
        if pcpi is not None:
            return float(pcpi) * qty
        ipc = ss.get("internal_production_cost_per_item")
        if ipc is not None:
            return float(ipc) * qty

    return float(line.get("internal_cost") or 0) * qty


def _line_bucket(line: Dict[str, Any]) -> str:
    """Return one of: 'SUPPLY' | 'INSTALLATION' | 'OTHER'.

    Uses the ``category`` field (§7). Legacy quote lines always have a category.
    """
    cat = str(line.get("category") or "").lower().strip()
    if cat in INSTALLATION_CATEGORIES:
        return "INSTALLATION"
    if cat in OTHER_DIRECT_CATEGORIES:
        return "OTHER"
    return "SUPPLY"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def aggregate_costs_from_lines(lines: Iterable[Dict[str, Any]]) -> Dict[str, float]:
    """Aggregate SUPPLY_COST, INSTALLATION_COST, OTHER_DIRECT_COSTS from lines.

    NEVER recomputes prices — only reads snapshots + legacy ``internal_cost``.
    """
    supply = 0.0
    install = 0.0
    other = 0.0
    for l in lines or []:
        c = _extract_line_cost(l)
        bucket = _line_bucket(l)
        if bucket == "INSTALLATION":
            install += c
        elif bucket == "OTHER":
            other += c
        else:
            supply += c
    return {
        "supply_cost": _r2(supply) or 0.0,
        "installation_cost": _r2(install) or 0.0,
        "other_direct_costs": _r2(other) or 0.0,
    }


def compute_financial_snapshot(quote: Dict[str, Any]) -> Dict[str, Any]:
    """Build the ``financial_snapshot`` for a quote document.

    Contract (§16 msg 392): 17 fields, all present (may be None for CRITICO or empty quotes).
    Amounts rounded to 2 decimals for presentation; % rounded to 4dp.
    """
    lines = quote.get("lines") or []
    subtotal = float(quote.get("subtotal") or quote.get("taxable_amount") or 0)  # NET_REVENUE_EX_VAT
    vat = float(quote.get("vat_amount") or 0)
    total = float(quote.get("total") or (subtotal + vat))

    costs = aggregate_costs_from_lines(lines)
    supply = float(costs["supply_cost"])
    install = float(costs["installation_cost"])
    other = float(costs["other_direct_costs"])

    net_revenue = subtotal  # policy §4 msg 392
    pre_commission_contribution = net_revenue - supply - install - other
    pre_commission_margin = (pre_commission_contribution / net_revenue * 100.0) if net_revenue > 0 else None

    band, rate, status = resolve_band(pre_commission_margin)

    commission_base = net_revenue  # §4
    commission_gross = _r2(commission_base * rate) if rate is not None else None
    final_company_contribution = _r2(pre_commission_contribution - (commission_gross or 0.0)) if rate is not None else None
    final_company_margin = None
    if final_company_contribution is not None and net_revenue > 0:
        final_company_margin = _r4(final_company_contribution / net_revenue * 100.0)

    return {
        "gross_contract_value": _r2(total),
        "net_revenue_ex_vat": _r2(net_revenue),
        "supply_cost": _r2(supply),
        "installation_cost": _r2(install),
        "other_direct_costs": _r2(other),
        "pre_commission_contribution": _r2(pre_commission_contribution),
        "pre_commission_margin": _r4(pre_commission_margin),
        "margin_band": band,
        "commission_base_policy": COMMISSION_BASE_POLICY,
        "commission_base": _r2(commission_base),
        "commission_rate": rate,  # fraction (0.15 = 15%) or None
        "commission_gross": commission_gross,
        "commission_status": status,
        "final_company_contribution": final_company_contribution,
        "final_company_margin": final_company_margin,  # % or None
        "margin_policy_version": MARGIN_POLICY_VERSION,
        "commission_policy_version": COMMISSION_POLICY_VERSION,
    }


# ---------------------------------------------------------------------------
# RBAC redaction (§11 / §20 msg 392)
# ---------------------------------------------------------------------------
# Commercial-safe field set: margin %, band, commission %, commission €, net revenue,
# status. Nothing else — no costs, no company contribution, no policy versions.
COMMERCIAL_SAFE_KEYS = {
    "net_revenue_ex_vat",
    "pre_commission_margin",
    "margin_band",
    "commission_rate",
    "commission_gross",
    "commission_status",
    # policy version is a public string, useful for UI legend
    "commission_policy_version",
}


def redact_financial_snapshot_for_role(snapshot: Optional[Dict[str, Any]], is_admin: bool) -> Optional[Dict[str, Any]]:
    """Return a copy of the snapshot filtered per role.

    Admin (``quotes.view_costs`` or ``quotes.view_margins`` or ``*``): full snapshot.
    Otherwise: only the commercial-safe subset.
    """
    if snapshot is None:
        return None
    if is_admin:
        return dict(snapshot)
    return {k: snapshot.get(k) for k in COMMERCIAL_SAFE_KEYS}


# ---------------------------------------------------------------------------
# PDF/Contract guard (§19 msg 392) — never leak margin data to customer docs
# ---------------------------------------------------------------------------
PDF_FORBIDDEN_TOP_LEVEL = (
    "financial_snapshot",
    "internal_cost", "margin_abs", "margin_pct", "cost_price",
)
PDF_FORBIDDEN_LINE_KEYS = (
    "internal_cost", "margin", "margin_abs", "margin_pct", "cost_price",
    "technical_snapshot",  # contains total_internal_cost, components, glass_cost, ...
    "financial_snapshot",
    # pricing_snapshot may embed technical_snapshot — strip too
    "pricing_snapshot",
)


def strip_margin_from_pdf_payload(quote_snap: Dict[str, Any]) -> Dict[str, Any]:
    """Remove all margin/cost/commission data from a quote payload destined
    to a customer document (PDF preventivo, contratto, link pubblico).
    """
    out = {k: v for k, v in quote_snap.items() if k not in PDF_FORBIDDEN_TOP_LEVEL}
    if "lines" in out:
        out["lines"] = [
            {k: v for k, v in l.items() if k not in PDF_FORBIDDEN_LINE_KEYS}
            for l in (out["lines"] or [])
        ]
    return out
