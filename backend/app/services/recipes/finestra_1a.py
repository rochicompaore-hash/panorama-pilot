"""Recipe: Finestra a 1 anta — sistema Premier-Elegant (telaio 5103 / anta 12130).

Formule esatte come da specifica approvata (paragrafi 3-13). Nessun eval(),
nessun fallback silenzioso a zero, nessuna arrotondazione dei calcoli intermedi.

Test di riferimento: L=900, H=1500, S=6 → risultati attesi documentati nella
suite `tests/test_finestra_1a_recipe.py`.
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

RECIPE_CODE = "finestra_1a_5103_12130"
FORMULA_VERSION = "1.0.0"


# =====================================================================
# Errori bloccanti
# =====================================================================
MISSING_ERROR_CODES = {
    "P_5103": "MISSING_FRAME_PRICE",
    "P_12130": "MISSING_SASH_PRICE",
    "P_RINFORZO_TELAIO": "MISSING_FRAME_REINFORCEMENT_PRICE",
    "P_RINFORZO_ANTA": "MISSING_SASH_REINFORCEMENT_PRICE",
    "P_FERMAVETRO": "MISSING_GLAZING_BEAD_PRICE",
    "P_VETRO": "MISSING_GLASS_PRICE",
    "MQ_MINIMO_VETRO": "MISSING_GLASS_MINIMUM",
    "P_FERRAMENTA": "MISSING_HARDWARE_PRICE",
    "COSTO_ORARIO": "MISSING_HOURLY_COST",
    "TEMPO_PRODUZIONE_MINUTI": "MISSING_PRODUCTION_TIME",
    "MARGINE_PERCENTUALE": "MISSING_MARGIN",
    "C_ALTRI": "MISSING_ADDITIONAL_COMPONENTS_COST",
}


# =====================================================================
# Data classes
# =====================================================================
@dataclass
class FinestraAInput:
    L: int
    H: int
    S: int = 6

    # Prezzi materiali (€/ml) — obbligatori
    P_5103: Optional[Decimal] = None
    P_12130: Optional[Decimal] = None
    P_RINFORZO_TELAIO: Optional[Decimal] = None
    P_RINFORZO_ANTA: Optional[Decimal] = None
    P_FERMAVETRO: Optional[Decimal] = None
    P_VETRO: Optional[Decimal] = None  # €/m²
    MQ_MINIMO_VETRO: Optional[Decimal] = None  # m² minimo fatturabile

    # Kit ferramenta e altri
    P_FERRAMENTA: Optional[Decimal] = None
    C_ALTRI: Optional[Decimal] = None
    C_ALTRI_declared_zero: bool = False  # deve essere True se il valore è esplicitamente 0

    # Manodopera
    COSTO_ORARIO: Optional[Decimal] = None
    TEMPO_PRODUZIONE_MINUTI: Optional[Decimal] = None

    # Prezzo di vendita
    MARGINE_PERCENTUALE: Optional[Decimal] = None
    SCONTO_AUTORIZZATO: Decimal = Decimal("0")

    # Colore Premium: +6% su PVC-only (telaio + anta + fermavetro + altri_pvc)
    is_color_premium: bool = False
    premium_pct: Decimal = Decimal("6")
    # C_ALTRI_pvc: quale porzione dei "altri componenti" è PVC. Default: 0 (accessori non-PVC).
    C_ALTRI_pvc_share: Decimal = Decimal("0")

    # Metadata
    color_code: str = ""
    product_id: Optional[str] = None
    product_key: Optional[str] = None
    pricelist_version: Optional[str] = None


@dataclass
class CutListItem:
    component: str
    formula_orizzontale: str
    formula_verticale: str
    len_orizzontale_mm: int
    len_verticale_mm: int
    qty_orizzontale: int = 2
    qty_verticale: int = 2

    @property
    def total_mm(self) -> int:
        return self.qty_orizzontale * self.len_orizzontale_mm + \
               self.qty_verticale * self.len_verticale_mm

    @property
    def total_ml(self) -> Decimal:
        return (Decimal(self.total_mm) / Decimal(1000))


@dataclass
class FinestraAResult:
    pricing_status: str  # "ok" | "incomplete" | "invalid_geometry"
    blocking_errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    cut_list: List[CutListItem] = field(default_factory=list)
    ml_consumption: Dict[str, Decimal] = field(default_factory=dict)
    glass_real_sqm: Optional[Decimal] = None
    glass_billable_sqm: Optional[Decimal] = None

    unit_prices: Dict[str, Decimal] = field(default_factory=dict)
    component_costs: Dict[str, Decimal] = field(default_factory=dict)
    materials_cost: Optional[Decimal] = None
    premium_surcharge: Optional[Decimal] = None
    labor_cost: Optional[Decimal] = None
    production_cost: Optional[Decimal] = None
    margin_pct: Optional[Decimal] = None
    sale_price_before_discount: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    sale_price: Optional[Decimal] = None

    formula_version: str = FORMULA_VERSION
    recipe_code: str = RECIPE_CODE
    computed_at: Optional[str] = None
    snapshot_hash: Optional[str] = None
    inputs_echo: Dict[str, Any] = field(default_factory=dict)


# =====================================================================
# Helpers
# =====================================================================
def _D(value: Any) -> Optional[Decimal]:
    """Convert to Decimal without silent zero coercion. None stays None."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _validate_geometry(inp: FinestraAInput) -> List[Dict[str, Any]]:
    """Return list of blocking errors for invalid geometry. Empty list = OK."""
    L, H, S = inp.L, inp.H, inp.S
    errors: List[Dict[str, Any]] = []

    def _err(check: str, value: int, threshold: str) -> Dict[str, Any]:
        return {
            "code": "INVALID_GEOMETRY",
            "check": check,
            "value_mm": value,
            "threshold": threshold,
            "message": f"Dimensione non compatibile: {check} = {value}, richiesto {threshold}",
        }

    if L <= 206:
        errors.append(_err("L", L, "> 206"))
    if H <= 206:
        errors.append(_err("H", H, "> 206"))
    if L - 108 <= 0:
        errors.append(_err("L-108", L - 108, "> 0"))
    if H - 108 <= 0:
        errors.append(_err("H-108", H - 108, "> 0"))
    if L - 70 + S <= 0:
        errors.append(_err("L-70+S", L - 70 + S, "> 0"))
    if H - 70 + S <= 0:
        errors.append(_err("H-70+S", H - 70 + S, "> 0"))
    if L - 186 <= 0:
        errors.append(_err("L-186", L - 186, "> 0"))
    if H - 186 <= 0:
        errors.append(_err("H-186", H - 186, "> 0"))
    return errors


def _collect_missing(inp: FinestraAInput) -> List[Dict[str, Any]]:
    """Enumerate MISSING_* blocking errors before computing costs."""
    errors: List[Dict[str, Any]] = []
    required = {
        "P_5103": inp.P_5103, "P_12130": inp.P_12130,
        "P_RINFORZO_TELAIO": inp.P_RINFORZO_TELAIO,
        "P_RINFORZO_ANTA": inp.P_RINFORZO_ANTA,
        "P_FERMAVETRO": inp.P_FERMAVETRO,
        "P_VETRO": inp.P_VETRO,
        "MQ_MINIMO_VETRO": inp.MQ_MINIMO_VETRO,
        "P_FERRAMENTA": inp.P_FERRAMENTA,
        "COSTO_ORARIO": inp.COSTO_ORARIO,
        "TEMPO_PRODUZIONE_MINUTI": inp.TEMPO_PRODUZIONE_MINUTI,
        "MARGINE_PERCENTUALE": inp.MARGINE_PERCENTUALE,
    }
    for name, value in required.items():
        if value is None:
            errors.append({
                "code": MISSING_ERROR_CODES[name],
                "variable": name,
                "message": f"Prezzo/parametro obbligatorio mancante: {name}",
            })
    # C_ALTRI: se non dichiarato esplicitamente a 0, deve avere un valore
    if inp.C_ALTRI is None and not inp.C_ALTRI_declared_zero:
        errors.append({
            "code": MISSING_ERROR_CODES["C_ALTRI"],
            "variable": "C_ALTRI",
            "message": (
                "Costo altri componenti non specificato. "
                "Impostare esplicitamente il valore oppure marcare "
                "`other_components_declared_zero=true`."
            ),
        })
    return errors


# =====================================================================
# Cut list computation
# =====================================================================
def _build_cut_list(L: int, H: int, S: int) -> List[CutListItem]:
    """Build the cut-list per specifica (paragrafi 3-7)."""
    return [
        # Telaio 5103
        CutListItem(
            component="telaio_5103",
            formula_orizzontale="L + S", formula_verticale="H + S",
            len_orizzontale_mm=L + S, len_verticale_mm=H + S,
        ),
        # Rinforzo telaio
        CutListItem(
            component="rinforzo_telaio",
            formula_orizzontale="L - 108", formula_verticale="H - 108",
            len_orizzontale_mm=L - 108, len_verticale_mm=H - 108,
        ),
        # Anta 12130
        CutListItem(
            component="anta_12130",
            formula_orizzontale="L - 70 + S", formula_verticale="H - 70 + S",
            len_orizzontale_mm=L - 70 + S, len_verticale_mm=H - 70 + S,
        ),
        # Rinforzo anta
        CutListItem(
            component="rinforzo_anta",
            formula_orizzontale="L - 206", formula_verticale="H - 206",
            len_orizzontale_mm=L - 206, len_verticale_mm=H - 206,
        ),
        # Fermavetro (taglio 45°)
        CutListItem(
            component="fermavetro",
            formula_orizzontale="L - 186", formula_verticale="H - 186",
            len_orizzontale_mm=L - 186, len_verticale_mm=H - 186,
        ),
    ]


# =====================================================================
# Main engine
# =====================================================================
def compute_finestra_1a(inp: FinestraAInput) -> FinestraAResult:
    """Compute a full 1-anta window BOM + costing. Deterministic + snapshot-hashed.

    Returns FinestraAResult with pricing_status in {"ok","incomplete","invalid_geometry"}.
    Never raises on missing data — errors surface as blocking_errors list. This
    ensures the router can persist a draft without a partial success.
    """
    result = FinestraAResult(pricing_status="ok", computed_at=datetime.now(timezone.utc).isoformat())

    # (a) Validate geometry FIRST
    geo_errors = _validate_geometry(inp)
    if geo_errors:
        result.pricing_status = "invalid_geometry"
        result.blocking_errors = geo_errors
        result.inputs_echo = {"L": inp.L, "H": inp.H, "S": inp.S, "color_code": inp.color_code}
        return result

    # (b) Check missing prices/parameters
    missing = _collect_missing(inp)
    if missing:
        result.pricing_status = "incomplete"
        result.blocking_errors = missing

    # (c) Cut list — always computed (even when incomplete, useful for preview)
    cut_list = _build_cut_list(inp.L, inp.H, inp.S)
    result.cut_list = cut_list
    result.ml_consumption = {c.component: c.total_ml for c in cut_list}

    # (d) Vetro — geometria sempre calcolabile
    L_vetro = Decimal(inp.L - 206)
    H_vetro = Decimal(inp.H - 206)
    mq_real = (L_vetro * H_vetro) / Decimal(1_000_000)
    result.glass_real_sqm = mq_real
    mq_min = _D(inp.MQ_MINIMO_VETRO) if inp.MQ_MINIMO_VETRO is not None else None
    if mq_min is not None:
        result.glass_billable_sqm = max(mq_real, mq_min)

    # If missing anything, stop before cost math to avoid silent zeros
    if result.pricing_status != "ok":
        result.inputs_echo = _echo(inp)
        return result

    # (e) Costs — every branch below reads confirmed non-None inputs
    p5103 = _D(inp.P_5103)
    p12130 = _D(inp.P_12130)
    prinf_t = _D(inp.P_RINFORZO_TELAIO)
    prinf_a = _D(inp.P_RINFORZO_ANTA)
    p_fv = _D(inp.P_FERMAVETRO)
    p_vetro = _D(inp.P_VETRO)
    p_ferr = _D(inp.P_FERRAMENTA)
    c_altri = _D(inp.C_ALTRI) if inp.C_ALTRI is not None else Decimal("0")

    ml_telaio = result.ml_consumption["telaio_5103"]
    ml_rinf_t = result.ml_consumption["rinforzo_telaio"]
    ml_anta = result.ml_consumption["anta_12130"]
    ml_rinf_a = result.ml_consumption["rinforzo_anta"]
    ml_fv = result.ml_consumption["fermavetro"]

    C_5103 = ml_telaio * p5103
    C_12130 = ml_anta * p12130
    C_RINFORZO_TELAIO = ml_rinf_t * prinf_t
    C_RINFORZO_ANTA = ml_rinf_a * prinf_a
    C_FERMAVETRO = ml_fv * p_fv
    C_VETRO = result.glass_billable_sqm * p_vetro

    # (f) Premium PVC surcharge (only on PVC components)
    c_altri_pvc = c_altri * (inp.C_ALTRI_pvc_share or Decimal("0"))
    C_PVC_BASE = C_5103 + C_12130 + C_FERMAVETRO + c_altri_pvc
    if inp.is_color_premium:
        premium_pct = inp.premium_pct or Decimal("6")
        premium = C_PVC_BASE * premium_pct / Decimal("100")
    else:
        premium = Decimal("0")
    result.premium_surcharge = premium

    # (g) Total materials
    materials = (
        C_5103 + C_RINFORZO_TELAIO + C_12130 + C_RINFORZO_ANTA
        + C_FERMAVETRO + C_VETRO + p_ferr + c_altri + premium
    )
    result.materials_cost = materials

    # (h) Labor
    hourly = _D(inp.COSTO_ORARIO)
    minutes = _D(inp.TEMPO_PRODUZIONE_MINUTI)
    labor = (minutes / Decimal("60")) * hourly
    result.labor_cost = labor

    # (i) Production + margin + sale
    production = materials + labor
    result.production_cost = production

    margin_pct = _D(inp.MARGINE_PERCENTUALE)
    result.margin_pct = margin_pct
    sale_before = production * (Decimal("1") + margin_pct / Decimal("100"))
    result.sale_price_before_discount = sale_before

    discount = _D(inp.SCONTO_AUTORIZZATO) or Decimal("0")
    result.discount = discount
    result.sale_price = sale_before - discount

    # (j) Component costs (breakdown)
    result.component_costs = {
        "frame_cost": C_5103,
        "frame_reinforcement_cost": C_RINFORZO_TELAIO,
        "sash_cost": C_12130,
        "sash_reinforcement_cost": C_RINFORZO_ANTA,
        "glazing_bead_cost": C_FERMAVETRO,
        "glass_cost": C_VETRO,
        "hardware_cost": p_ferr,
        "additional_components_cost": c_altri,
        "premium_pvc_surcharge": premium,
    }
    result.unit_prices = {
        "P_5103": p5103, "P_12130": p12130,
        "P_RINFORZO_TELAIO": prinf_t, "P_RINFORZO_ANTA": prinf_a,
        "P_FERMAVETRO": p_fv, "P_VETRO": p_vetro,
        "P_FERRAMENTA": p_ferr,
        "COSTO_ORARIO": hourly, "TEMPO_PRODUZIONE_MINUTI": minutes,
    }
    result.inputs_echo = _echo(inp)
    result.snapshot_hash = _compute_hash(result)
    return result


def _echo(inp: FinestraAInput) -> Dict[str, Any]:
    return {
        "L": inp.L, "H": inp.H, "S": inp.S,
        "color_code": inp.color_code, "is_color_premium": inp.is_color_premium,
        "product_key": inp.product_key, "product_id": inp.product_id,
        "pricelist_version": inp.pricelist_version,
        "recipe_code": RECIPE_CODE, "formula_version": FORMULA_VERSION,
    }


def _compute_hash(r: FinestraAResult) -> str:
    """Deterministic snapshot hash — used to prove pricing outcome.
    NOT the same field as `quote.snapshot_hash` (which stays untouched).
    """
    payload = {
        "recipe": RECIPE_CODE, "formula_version": FORMULA_VERSION,
        "inputs": r.inputs_echo,
        "ml": {k: str(v) for k, v in r.ml_consumption.items()},
        "mq_real": str(r.glass_real_sqm),
        "mq_bill": str(r.glass_billable_sqm),
        "unit_prices": {k: str(v) for k, v in r.unit_prices.items()},
        "component_costs": {k: str(v) for k, v in r.component_costs.items()},
        "materials": str(r.materials_cost),
        "labor": str(r.labor_cost),
        "production": str(r.production_cost),
        "margin_pct": str(r.margin_pct),
        "sale_before": str(r.sale_price_before_discount),
        "discount": str(r.discount),
        "sale": str(r.sale_price),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


# =====================================================================
# Display helpers (safe rounding — only for viewing, never for chained math)
# =====================================================================
def display_dict(r: FinestraAResult) -> Dict[str, Any]:
    """Return a JSON-safe dict with only display-level 2-decimal rounding on
    aggregate totals. Intermediate values remain full-precision in the raw result.
    """
    def money(v: Optional[Decimal]) -> Optional[float]:
        return float(_round_money(v)) if v is not None else None

    def num(v: Optional[Decimal]) -> Optional[float]:
        return float(v) if v is not None else None

    return {
        "pricing_status": r.pricing_status,
        "blocking_errors": r.blocking_errors,
        "warnings": r.warnings,
        "cut_list": [asdict(c) | {
            "total_mm": c.total_mm, "total_ml": float(c.total_ml),
        } for c in r.cut_list],
        "ml_consumption": {k: float(v) for k, v in r.ml_consumption.items()},
        "glass_real_sqm": num(r.glass_real_sqm),
        "glass_billable_sqm": num(r.glass_billable_sqm),
        "unit_prices": {k: float(v) for k, v in r.unit_prices.items()},
        "component_costs": {k: money(v) for k, v in r.component_costs.items()},
        "materials_cost": money(r.materials_cost),
        "premium_surcharge": money(r.premium_surcharge),
        "labor_cost": money(r.labor_cost),
        "production_cost": money(r.production_cost),
        "margin_pct": num(r.margin_pct),
        "sale_price_before_discount": money(r.sale_price_before_discount),
        "discount": money(r.discount),
        "sale_price": money(r.sale_price),
        "recipe_code": r.recipe_code,
        "formula_version": r.formula_version,
        "computed_at": r.computed_at,
        "snapshot_hash": r.snapshot_hash,
        "inputs_echo": r.inputs_echo,
    }
