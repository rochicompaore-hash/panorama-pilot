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

MARGIN_POLICY_VERSION = "margin_policy_v2_2026_02"
COMMISSION_POLICY_VERSION = "commission_policy_v1_2026_02"
WITHHOLDING_POLICY_VERSION = "withholding_policy_v1_2026_02"
COMMISSION_BASE_POLICY = "NET_REVENUE_EX_VAT"
WITHHOLDING_BASE_POLICY = "NET_REVENUE_EX_VAT"
DEFAULT_WITHHOLDING_RATE = 0.11   # msg 395 §2 — 11% ritenuta d'acconto

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

    Msg 399 — nuove fasce commissionali definitive (boundary test §boundary):
      >30.00  → OTTIMO 15%
      20-30   → BUONO 10%
      15-19.99→ SUFFICIENTE 8%
      8-14.99 → SCARSO 5%
      <8      → CRITICO AUTHORIZATION_REQUIRED

    Il boundary 30.00 esatto → BUONO 10% (§boundary 30.00% → 10%).
    """
    if margin_pct is None:
        return ("UNKNOWN", None, "NO_DATA")
    m = float(margin_pct)
    if m > 30.0:
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
            return float(tic) * qty

    ss = line.get("simple_snapshot") or {}
    if isinstance(ss, dict):
        ptc = ss.get("purchase_total_cost")
        if ptc is not None:
            return float(ptc)
        pcpi = ss.get("purchase_cost_per_item")
        if pcpi is not None:
            return float(pcpi) * qty
        ipc = ss.get("internal_production_cost_per_item")
        if ipc is not None:
            return float(ipc) * qty

    return float(line.get("internal_cost") or 0) * qty


def _extract_line_services_split(line: Dict[str, Any]) -> Dict[str, float]:
    """Split automatic_services + manual_extra_services costs into
    INSTALLATION vs OTHER buckets (msg 393 §22 wiring to Margin Engine).

    - POSA / MOTORIZZAZIONE  → INSTALLATION
    - SMONTAGGIO / SMALTIMENTO / ACCESSORIO / *  → OTHER
    """
    install = 0.0
    other = 0.0
    for s in (line.get("automatic_services") or []) + (line.get("manual_extra_services") or []):
        t = str(s.get("service_type") or "").upper()
        c = float(s.get("internal_cost_total") or 0)
        if t in ("POSA", "MOTORIZZAZIONE"):
            install += c
        else:
            other += c
    return {"installation": install, "other": other}


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
    Installation Mode V1 (msg 393): also folds automatic_services[] +
    manual_extra_services[] into INSTALLATION (POSA/MOTORIZZAZIONE) or OTHER
    (SMONTAGGIO/SMALTIMENTO/…), on top of the product cost.
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
        # Split embedded services on the line (V1 auto-bundle)
        svc_split = _extract_line_services_split(l)
        install += svc_split["installation"]
        other += svc_split["other"]
    return {
        "supply_cost": _r2(supply) or 0.0,
        "installation_cost": _r2(install) or 0.0,
        "other_direct_costs": _r2(other) or 0.0,
    }


def compute_financial_snapshot(quote: Dict[str, Any]) -> Dict[str, Any]:
    """Build the ``financial_snapshot`` for a quote document.

    Msg 394-396 policy stack:
      * §3 (394) SUPPLY/INSTALL/OTHER buckets sempre separati.
      * §1-§5 (395) Ritenuta d'acconto sottratta prima della commissione se
        ``withholding_applicable=True``.
      * §4-§10 (396) Tachimetro visualizza FINAL_COMPANY_MARGIN (post-commissione)
        → esposto anche come ``tachometer_value``.
      * §4-§5 (post-supply-cost) ENEA safety: se manca internal cost su una
        pratica ENEA selezionata, ``commission_status=NEEDS_COST_CONFIGURATION``
        e ``financial_snapshot_status="INCOMPLETE"``.
    """
    lines = quote.get("lines") or []
    subtotal = float(quote.get("subtotal") or quote.get("taxable_amount") or 0)
    vat = float(quote.get("vat_amount") or 0)
    total = float(quote.get("total") or (subtotal + vat))

    costs = aggregate_costs_from_lines(lines)
    supply = float(costs["supply_cost"])
    install = float(costs["installation_cost"])
    other = float(costs["other_direct_costs"])
    net_revenue = subtotal

    # --- Withholding (msg 395) ---
    wh_applicable = bool(quote.get("withholding_applicable"))
    wh_rate = float(quote.get("withholding_rate") or DEFAULT_WITHHOLDING_RATE) if wh_applicable else 0.0
    wh_cost = _r2(net_revenue * wh_rate) if wh_applicable else 0.0

    # --- ENEA safety guard (msg 395 §3-§5) ---
    # Se esiste una riga con ``enea_practice=True`` e nessun internal cost
    # configurato ⇒ snapshot INCOMPLETE.
    enea_missing_cost = False
    for l in lines:
        if not l.get("enea_practice"):
            continue
        # ENEA line: internal_cost None or explicit NEEDS_PO_COSTING flag
        ss = l.get("simple_snapshot") or {}
        if (l.get("internal_cost") in (None, 0, 0.0)
                and ss.get("internal_cost_status") in (None, "NEEDS_PO_COSTING")):
            enea_missing_cost = True
            break

    pre_commission_contribution = net_revenue - supply - install - other - float(wh_cost or 0)
    pre_commission_margin = (pre_commission_contribution / net_revenue * 100.0) if net_revenue > 0 else None

    band, rate, status = resolve_band(pre_commission_margin)

    # Se ENEA cost mancante ⇒ commissione non definitiva (§5 msg 395).
    fs_status = "COMPLETE"
    fs_errors: List[str] = []
    if enea_missing_cost:
        fs_status = "INCOMPLETE"
        fs_errors.append("MISSING_INTERNAL_COST_ENEA")
        # non azzero la commission_rate ma la marchiamo come non finale
        if status == "OK":
            status = "NEEDS_COST_CONFIGURATION"
    # msg 402 — servizi automatici con costo interno non definito (es. PROFILATURA) ⇒ snapshot non definitivo
    svc_missing = sorted({str(sv.get("service_code")) for l in lines
                          for sv in (l.get("automatic_services") or []) + (l.get("manual_extra_services") or [])
                          if sv.get("internal_cost_status") == "NEEDS_PO_COSTING"})
    if svc_missing:
        fs_status = "INCOMPLETE"
        fs_errors.extend(f"MISSING_INTERNAL_COST_{c}" for c in svc_missing)
        if status == "OK":
            status = "NEEDS_COST_CONFIGURATION"

    commission_base = net_revenue
    commission_gross = _r2(commission_base * rate) if rate is not None else None
    final_company_contribution = _r2(pre_commission_contribution - (commission_gross or 0.0)) if rate is not None else None
    final_company_margin = None
    if final_company_contribution is not None and net_revenue > 0:
        final_company_margin = _r4(final_company_contribution / net_revenue * 100.0)

    # --- Tachometer value (msg 396 §4) ---
    # Il tachimetro DEVE mostrare esclusivamente FINAL_COMPANY_MARGIN.
    tachometer_value = final_company_margin

    return {
        "gross_contract_value": _r2(total),
        "net_revenue_ex_vat": _r2(net_revenue),
        "supply_cost": _r2(supply),
        "installation_cost": _r2(install),
        "other_direct_costs": _r2(other),
        # Withholding (msg 395)
        "withholding_applicable": wh_applicable,
        "withholding_base": _r2(net_revenue) if wh_applicable else None,
        "withholding_rate": wh_rate if wh_applicable else None,
        "withholding_cost": _r2(wh_cost) if wh_applicable else 0.0,
        "withholding_policy_version": WITHHOLDING_POLICY_VERSION if wh_applicable else None,
        # Margin + commission
        "pre_commission_contribution": _r2(pre_commission_contribution),
        "pre_commission_margin": _r4(pre_commission_margin),
        "margin_band": band,
        "commission_base_policy": COMMISSION_BASE_POLICY,
        "commission_base": _r2(commission_base),
        "commission_rate": rate,
        "commission_gross": commission_gross,
        "commission_status": status,
        "final_company_contribution": final_company_contribution,
        "final_company_margin": final_company_margin,
        # Tachometer authoritative value (msg 396 §4/§13)
        "tachometer_value": tachometer_value,
        # Financial snapshot completeness (msg 395 §5)
        "financial_snapshot_status": fs_status,
        "financial_snapshot_errors": fs_errors,
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
    # msg 396 §6 — commerciale vede TACHIMETRO (final_company_margin) e commissione
    "final_company_margin",
    "tachometer_value",
    "margin_band",
    "commission_rate",
    "commission_gross",
    "commission_status",
    # policy version + snapshot health hint
    "commission_policy_version",
    "financial_snapshot_status",
    "financial_snapshot_errors",
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
