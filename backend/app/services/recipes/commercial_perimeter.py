"""Recipe: commercial_perimeter — modalità di preventivazione predefinita.

Sostituisce la logica basata su lista-di-taglio per la determinazione del
prezzo commerciale. Il motore technical_cut_list resta disponibile per la
produzione (lista pezzi, taglio barre, ottimizzatore sfrido).

Punti chiave della spec approvata:
- external_perimeter_ml = 2*(L_m + H_m)
- sash_perimeter_ml = external_perimeter + 2*H_m*max(n_sashes-1, 0)
- Meeting-stile solo per n_sashes > 1: meeting_stile_ml = H_m * (n_sashes-1)
- Finestra fissa: solo telaio + rinforzo + fermavetro (no anta/scambio)
- Vetro sempre al m² con formula strutturata/custom per (prodotto, n_ante)
- Sfrido configurabile per componente: cost = ml * price * (1 + waste_pct/100)
- Nessun fallback silenzioso a zero: MISSING_* espliciti bloccanti
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

RECIPE_CODE = "commercial_perimeter"
FORMULA_VERSION = "1.0.0"


MISSING_ERROR_CODES = {
    "P_FRAME": "MISSING_FRAME_PRICE",
    "P_FRAME_REINFORCEMENT": "MISSING_FRAME_REINFORCEMENT_PRICE",
    "P_SASH": "MISSING_SASH_PRICE",
    "P_SASH_REINFORCEMENT": "MISSING_SASH_REINFORCEMENT_PRICE",
    "P_GLAZING_BEAD": "MISSING_GLAZING_BEAD_PRICE",
    "P_MEETING_STILE": "MISSING_MEETING_STILE_PRICE",
    "P_MEETING_STILE_REINFORCEMENT": "MISSING_MEETING_STILE_REINFORCEMENT_PRICE",
    "P_GLASS": "MISSING_GLASS_PRICE",
    "GLASS_RECIPE": "MISSING_GLASS_RECIPE",
    "MIN_GLASS_SQM": "MISSING_GLASS_MINIMUM",
    "P_HARDWARE": "MISSING_HARDWARE_PRICE",
    "HOURLY_COST": "MISSING_HOURLY_COST",
    "PRODUCTION_TIME": "MISSING_PRODUCTION_TIME",
    "MARGIN": "MISSING_MARGIN",
    "P_INSTALLATION": "MISSING_INSTALLATION_PRICE",
    "COMPONENT_COLOR": "MISSING_COMPONENT_COLOR_PRICE",
}


@dataclass
class PerimeterInput:
    L_mm: int
    H_mm: int
    number_of_sashes: int
    window_type: str = "apribile"   # "apribile" | "fissa"
    hardware_not_required: bool = False  # solo per fissa

    # Prices per component (€/ml). None = missing.
    P_FRAME: Optional[Decimal] = None
    P_FRAME_REINFORCEMENT: Optional[Decimal] = None
    P_SASH: Optional[Decimal] = None
    P_SASH_REINFORCEMENT: Optional[Decimal] = None
    P_GLAZING_BEAD: Optional[Decimal] = None
    P_MEETING_STILE: Optional[Decimal] = None
    P_MEETING_STILE_REINFORCEMENT: Optional[Decimal] = None

    # Waste percentages (%). Default 0 (no scrap surcharge).
    WASTE_FRAME: Decimal = Decimal("0")
    WASTE_FRAME_REINFORCEMENT: Decimal = Decimal("0")
    WASTE_SASH: Decimal = Decimal("0")
    WASTE_SASH_REINFORCEMENT: Decimal = Decimal("0")
    WASTE_GLAZING_BEAD: Decimal = Decimal("0")
    WASTE_MEETING_STILE: Decimal = Decimal("0")

    # Glass
    glass_recipe_resolved: bool = False   # True se il resolver ha trovato una ricetta valida
    glass_width_mm: Optional[int] = None
    glass_height_mm: Optional[int] = None
    glass_quantity: int = 0
    P_GLASS_SQM: Optional[Decimal] = None
    MIN_GLASS_SQM: Optional[Decimal] = None

    # Hardware
    P_HARDWARE: Optional[Decimal] = None   # € (fisso) — se hardware_not_required=True può essere None

    # Additional / Premium
    additional_material_cost: Decimal = Decimal("0")
    additional_declared_zero: bool = False
    is_color_premium: bool = False
    premium_pct: Decimal = Decimal("6")
    premium_pvc_share_extra: Decimal = Decimal("0")  # quota di additional considerata PVC

    # Production
    hourly_cost: Optional[Decimal] = None
    production_time_minutes: Optional[Decimal] = None
    margin_pct: Optional[Decimal] = None

    # Services
    installation_cost: Decimal = Decimal("0")
    installation_declared_zero: bool = False
    transport_cost: Decimal = Decimal("0")
    disposal_cost: Decimal = Decimal("0")
    accessory_cost: Decimal = Decimal("0")

    discount_amount: Decimal = Decimal("0")

    # Metadata
    product_id: Optional[str] = None
    product_key: Optional[str] = None
    color_code: str = ""
    pricelist_version: Optional[str] = None
    glass_code: Optional[str] = None


@dataclass
class PerimeterResult:
    pricing_status: str = "ok"   # "ok" | "incomplete" | "invalid_geometry"
    blocking_errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Perimetri
    external_perimeter_ml: Optional[Decimal] = None
    sash_perimeter_ml: Optional[Decimal] = None
    meeting_stile_ml: Optional[Decimal] = None

    # Consumi per componente (ml) — con sfrido applicato
    ml_consumption: Dict[str, Decimal] = field(default_factory=dict)
    ml_consumption_net: Dict[str, Decimal] = field(default_factory=dict)
    waste_percentages: Dict[str, Decimal] = field(default_factory=dict)

    # Costi
    unit_prices: Dict[str, Decimal] = field(default_factory=dict)
    component_costs: Dict[str, Decimal] = field(default_factory=dict)
    profile_cost: Optional[Decimal] = None
    glass_dimensions: Optional[Dict[str, Any]] = None
    glass_area_sqm: Optional[Decimal] = None
    glass_billable_sqm: Optional[Decimal] = None
    glass_cost: Optional[Decimal] = None
    hardware_cost: Optional[Decimal] = None
    additional_material_cost: Optional[Decimal] = None
    premium_surcharge: Optional[Decimal] = None
    materials_cost: Optional[Decimal] = None
    labor_cost: Optional[Decimal] = None
    production_cost: Optional[Decimal] = None
    service_cost: Optional[Decimal] = None
    total_internal_cost: Optional[Decimal] = None
    margin_pct: Optional[Decimal] = None
    sale_price_before_discount: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    sale_price: Optional[Decimal] = None

    recipe_code: str = RECIPE_CODE
    formula_version: str = FORMULA_VERSION
    computed_at: Optional[str] = None
    snapshot_hash: Optional[str] = None
    inputs_echo: Dict[str, Any] = field(default_factory=dict)


def _D(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _validate_geometry(inp: PerimeterInput) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    if inp.L_mm <= 0:
        errors.append({"code": "INVALID_GEOMETRY", "check": "L_mm", "value": inp.L_mm,
                       "message": "Larghezza deve essere > 0"})
    if inp.H_mm <= 0:
        errors.append({"code": "INVALID_GEOMETRY", "check": "H_mm", "value": inp.H_mm,
                       "message": "Altezza deve essere > 0"})
    if inp.number_of_sashes < 0:
        errors.append({"code": "INVALID_GEOMETRY", "check": "number_of_sashes",
                       "value": inp.number_of_sashes,
                       "message": "Numero ante non può essere negativo"})
    if inp.window_type not in ("apribile", "fissa"):
        errors.append({"code": "INVALID_GEOMETRY", "check": "window_type",
                       "value": inp.window_type,
                       "message": "window_type deve essere 'apribile' o 'fissa'"})
    return errors


def _collect_missing(inp: PerimeterInput) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []

    def _need(name: str, value):
        if value is None:
            errors.append({
                "code": MISSING_ERROR_CODES[name],
                "variable": name,
                "message": f"Valore obbligatorio mancante: {name}",
            })

    # Profili
    _need("P_FRAME", inp.P_FRAME)
    _need("P_FRAME_REINFORCEMENT", inp.P_FRAME_REINFORCEMENT)
    _need("P_GLAZING_BEAD", inp.P_GLAZING_BEAD)

    if inp.window_type == "apribile":
        _need("P_SASH", inp.P_SASH)
        _need("P_SASH_REINFORCEMENT", inp.P_SASH_REINFORCEMENT)
        if inp.number_of_sashes > 1:
            _need("P_MEETING_STILE", inp.P_MEETING_STILE)
            _need("P_MEETING_STILE_REINFORCEMENT", inp.P_MEETING_STILE_REINFORCEMENT)

    # Vetro
    if not inp.glass_recipe_resolved:
        errors.append({"code": MISSING_ERROR_CODES["GLASS_RECIPE"],
                       "variable": "glass_recipe",
                       "message": "Formula vetro non definita per questa combinazione prodotto/ante"})
    else:
        _need("P_GLASS", inp.P_GLASS_SQM)
        _need("MIN_GLASS_SQM", inp.MIN_GLASS_SQM)

    # Ferramenta (obbligatoria per apribile, opzionale per fissa con hardware_not_required)
    if inp.window_type == "apribile" or not inp.hardware_not_required:
        _need("P_HARDWARE", inp.P_HARDWARE)

    # Produzione
    _need("HOURLY_COST", inp.hourly_cost)
    _need("PRODUCTION_TIME", inp.production_time_minutes)
    _need("MARGIN", inp.margin_pct)

    return errors


def compute_perimeter(inp: PerimeterInput) -> PerimeterResult:
    """Motore commercial_perimeter — pricing_status ∈ {ok, incomplete, invalid_geometry}."""
    r = PerimeterResult(computed_at=datetime.now(timezone.utc).isoformat())

    # (a) Validate geometry FIRST
    geo = _validate_geometry(inp)
    if geo:
        r.pricing_status = "invalid_geometry"
        r.blocking_errors = geo
        r.inputs_echo = _echo(inp)
        return r

    # (b) Perimetri (sempre calcolabili)
    L_m = Decimal(inp.L_mm) / Decimal(1000)
    H_m = Decimal(inp.H_mm) / Decimal(1000)
    ext = Decimal(2) * (L_m + H_m)
    r.external_perimeter_ml = ext
    extra_sashes = max(inp.number_of_sashes - 1, 0)
    sash_perim = ext + Decimal(2) * H_m * Decimal(extra_sashes)
    r.sash_perimeter_ml = sash_perim
    ms_ml = H_m * Decimal(extra_sashes)
    r.meeting_stile_ml = ms_ml

    # (c) Missing check
    missing = _collect_missing(inp)
    if missing:
        r.pricing_status = "incomplete"
        r.blocking_errors = missing

    # Additional cost check (parallelo al C_ALTRI del 1a)
    if not inp.additional_declared_zero and inp.additional_material_cost is None:
        r.pricing_status = "incomplete"
        r.blocking_errors.append({
            "code": "MISSING_ADDITIONAL_COMPONENTS_COST",
            "variable": "additional_material_cost",
            "message": "Impostare il valore o marcare additional_declared_zero=true",
        })
    if not inp.installation_declared_zero and inp.installation_cost is None:
        r.pricing_status = "incomplete"
        r.blocking_errors.append({
            "code": MISSING_ERROR_CODES["P_INSTALLATION"],
            "variable": "installation_cost",
            "message": "Impostare il costo di montaggio o marcare installation_declared_zero=true",
        })

    # (d) Cut list / ml consumption — calcolabile anche in incomplete
    net_ml: Dict[str, Decimal] = {}
    waste: Dict[str, Decimal] = {}

    net_ml["telaio"] = ext
    waste["telaio"] = inp.WASTE_FRAME
    net_ml["rinforzo_telaio"] = ext
    waste["rinforzo_telaio"] = inp.WASTE_FRAME_REINFORCEMENT
    net_ml["fermavetro"] = sash_perim if inp.window_type == "apribile" else ext
    waste["fermavetro"] = inp.WASTE_GLAZING_BEAD

    if inp.window_type == "apribile":
        net_ml["anta"] = sash_perim
        waste["anta"] = inp.WASTE_SASH
        net_ml["rinforzo_anta"] = sash_perim
        waste["rinforzo_anta"] = inp.WASTE_SASH_REINFORCEMENT
        if extra_sashes > 0:
            net_ml["scambio_battuta"] = ms_ml
            waste["scambio_battuta"] = inp.WASTE_MEETING_STILE
            net_ml["rinforzo_scambio_battuta"] = ms_ml
            waste["rinforzo_scambio_battuta"] = inp.WASTE_MEETING_STILE

    r.ml_consumption_net = net_ml
    r.waste_percentages = waste
    r.ml_consumption = {
        k: v * (Decimal(1) + waste.get(k, Decimal("0")) / Decimal(100))
        for k, v in net_ml.items()
    }

    # (e) Glass dimensions (se ricetta risolta)
    if inp.glass_recipe_resolved and inp.glass_width_mm and inp.glass_height_mm and inp.glass_quantity > 0:
        gw = Decimal(inp.glass_width_mm)
        gh = Decimal(inp.glass_height_mm)
        area_real = (gw * gh) / Decimal(1_000_000)
        r.glass_area_sqm = area_real
        r.glass_dimensions = {
            "width_mm": inp.glass_width_mm,
            "height_mm": inp.glass_height_mm,
            "quantity": inp.glass_quantity,
        }
        if inp.MIN_GLASS_SQM is not None:
            r.glass_billable_sqm = max(area_real, _D(inp.MIN_GLASS_SQM))

    # If missing anything, stop before cost math
    if r.pricing_status != "ok":
        r.inputs_echo = _echo(inp)
        return r

    # (f) Costi profili con sfrido
    P_FRAME = _D(inp.P_FRAME)
    P_FRAME_R = _D(inp.P_FRAME_REINFORCEMENT)
    P_GB = _D(inp.P_GLAZING_BEAD)
    P_SASH = _D(inp.P_SASH) if inp.window_type == "apribile" else Decimal("0")
    P_SASH_R = _D(inp.P_SASH_REINFORCEMENT) if inp.window_type == "apribile" else Decimal("0")
    P_MS = _D(inp.P_MEETING_STILE) if extra_sashes > 0 and inp.window_type == "apribile" else Decimal("0")
    P_MS_R = _D(inp.P_MEETING_STILE_REINFORCEMENT) if extra_sashes > 0 and inp.window_type == "apribile" else Decimal("0")

    frame_cost = r.ml_consumption["telaio"] * P_FRAME
    frame_reinf_cost = r.ml_consumption["rinforzo_telaio"] * P_FRAME_R
    glazing_bead_cost = r.ml_consumption["fermavetro"] * P_GB
    sash_cost = r.ml_consumption.get("anta", Decimal("0")) * P_SASH
    sash_reinf_cost = r.ml_consumption.get("rinforzo_anta", Decimal("0")) * P_SASH_R
    ms_cost = r.ml_consumption.get("scambio_battuta", Decimal("0")) * P_MS
    ms_reinf_cost = r.ml_consumption.get("rinforzo_scambio_battuta", Decimal("0")) * P_MS_R

    profile_cost = (frame_cost + frame_reinf_cost + glazing_bead_cost
                    + sash_cost + sash_reinf_cost + ms_cost + ms_reinf_cost)
    r.profile_cost = profile_cost

    # (g) Glass cost
    glass_cost = r.glass_billable_sqm * Decimal(inp.glass_quantity) * _D(inp.P_GLASS_SQM)
    r.glass_cost = glass_cost

    # (h) Hardware
    hardware_cost = _D(inp.P_HARDWARE) if inp.P_HARDWARE is not None else Decimal("0")
    r.hardware_cost = hardware_cost

    # (i) Additional + Premium (+6% PVC-only)
    additional = _D(inp.additional_material_cost) if inp.additional_material_cost is not None else Decimal("0")
    r.additional_material_cost = additional
    pvc_base = frame_cost + sash_cost + glazing_bead_cost + ms_cost \
               + (additional * (inp.premium_pvc_share_extra or Decimal("0")))
    if inp.is_color_premium:
        premium = pvc_base * (inp.premium_pct or Decimal("6")) / Decimal("100")
    else:
        premium = Decimal("0")
    r.premium_surcharge = premium

    # (j) Materials total
    materials_cost = profile_cost + glass_cost + hardware_cost + additional + premium
    r.materials_cost = materials_cost

    # (k) Labour
    labor_cost = (_D(inp.production_time_minutes) / Decimal("60")) * _D(inp.hourly_cost)
    r.labor_cost = labor_cost

    # (l) Production
    production_cost = materials_cost + labor_cost
    r.production_cost = production_cost

    # (m) Services
    # BUG-16 FIX (audit v1) — se installation/transport/disposal/accessory sono None (declared_zero=True),
    # coerce a Decimal("0") per evitare TypeError. Il check semantico "declared_zero" è già stato fatto sopra.
    def _z(v):
        d = _D(v)
        return d if d is not None else Decimal("0")
    service_cost = (_z(inp.installation_cost) + _z(inp.transport_cost)
                    + _z(inp.disposal_cost) + _z(inp.accessory_cost))
    r.service_cost = service_cost

    total_internal = production_cost + service_cost
    r.total_internal_cost = total_internal

    # (n) Margin + Discount
    margin_pct = _D(inp.margin_pct)
    r.margin_pct = margin_pct
    sale_before = total_internal * (Decimal(1) + margin_pct / Decimal(100))
    r.sale_price_before_discount = sale_before
    discount = _D(inp.discount_amount) or Decimal("0")
    r.discount = discount
    r.sale_price = sale_before - discount

    # (o) Component breakdown
    r.component_costs = {
        "frame_cost": frame_cost,
        "frame_reinforcement_cost": frame_reinf_cost,
        "sash_cost": sash_cost,
        "sash_reinforcement_cost": sash_reinf_cost,
        "glazing_bead_cost": glazing_bead_cost,
        "meeting_stile_cost": ms_cost,
        "meeting_stile_reinforcement_cost": ms_reinf_cost,
        "glass_cost": glass_cost,
        "hardware_cost": hardware_cost,
        "additional_material_cost": additional,
        "premium_surcharge": premium,
    }
    r.unit_prices = {
        "P_FRAME": P_FRAME, "P_FRAME_REINFORCEMENT": P_FRAME_R,
        "P_SASH": P_SASH, "P_SASH_REINFORCEMENT": P_SASH_R,
        "P_GLAZING_BEAD": P_GB,
        "P_MEETING_STILE": P_MS, "P_MEETING_STILE_REINFORCEMENT": P_MS_R,
        "P_GLASS_SQM": _D(inp.P_GLASS_SQM),
        "P_HARDWARE": _D(inp.P_HARDWARE) if inp.P_HARDWARE else Decimal("0"),
        "HOURLY_COST": _D(inp.hourly_cost),
        "PRODUCTION_TIME_MINUTES": _D(inp.production_time_minutes),
    }
    r.inputs_echo = _echo(inp)
    r.snapshot_hash = _compute_hash(r)
    return r


def _echo(inp: PerimeterInput) -> Dict[str, Any]:
    return {
        "L_mm": inp.L_mm, "H_mm": inp.H_mm,
        "number_of_sashes": inp.number_of_sashes,
        "window_type": inp.window_type,
        "color_code": inp.color_code, "is_color_premium": inp.is_color_premium,
        "product_key": inp.product_key, "product_id": inp.product_id,
        "glass_code": inp.glass_code,
        "pricelist_version": inp.pricelist_version,
        "recipe_code": RECIPE_CODE, "formula_version": FORMULA_VERSION,
    }


def _compute_hash(r: PerimeterResult) -> str:
    payload = {
        "recipe": RECIPE_CODE, "formula_version": FORMULA_VERSION,
        "inputs": r.inputs_echo,
        "perimeters": {
            "external": str(r.external_perimeter_ml),
            "sash": str(r.sash_perimeter_ml),
            "meeting_stile": str(r.meeting_stile_ml),
        },
        "ml": {k: str(v) for k, v in r.ml_consumption.items()},
        "glass_bill_sqm": str(r.glass_billable_sqm),
        "unit_prices": {k: str(v) for k, v in r.unit_prices.items()},
        "component_costs": {k: str(v) for k, v in r.component_costs.items()},
        "materials": str(r.materials_cost),
        "labor": str(r.labor_cost),
        "production": str(r.production_cost),
        "services": str(r.service_cost),
        "total_internal": str(r.total_internal_cost),
        "margin_pct": str(r.margin_pct),
        "sale_before": str(r.sale_price_before_discount),
        "discount": str(r.discount),
        "sale": str(r.sale_price),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def display_dict(r: PerimeterResult) -> Dict[str, Any]:
    def money(v): return float(_round_money(v)) if v is not None else None
    def num(v):
        if v is None: return None
        try: return float(v)
        except (TypeError, ValueError): return None
    return {
        "pricing_status": r.pricing_status,
        "blocking_errors": r.blocking_errors,
        "warnings": r.warnings,
        "external_perimeter_ml": num(r.external_perimeter_ml),
        "sash_perimeter_ml": num(r.sash_perimeter_ml),
        "meeting_stile_ml": num(r.meeting_stile_ml),
        "ml_consumption": {k: float(v) for k, v in r.ml_consumption.items()},
        "ml_consumption_net": {k: float(v) for k, v in r.ml_consumption_net.items()},
        "waste_percentages": {k: float(v) for k, v in r.waste_percentages.items()},
        "unit_prices": {k: float(v) for k, v in r.unit_prices.items()},
        "component_costs": {k: money(v) for k, v in r.component_costs.items()},
        "profile_cost": money(r.profile_cost),
        "glass_dimensions": r.glass_dimensions,
        "glass_area_sqm": num(r.glass_area_sqm),
        "glass_billable_sqm": num(r.glass_billable_sqm),
        "glass_cost": money(r.glass_cost),
        "hardware_cost": money(r.hardware_cost),
        "additional_material_cost": money(r.additional_material_cost),
        "premium_surcharge": money(r.premium_surcharge),
        "materials_cost": money(r.materials_cost),
        "labor_cost": money(r.labor_cost),
        "production_cost": money(r.production_cost),
        "service_cost": money(r.service_cost),
        "total_internal_cost": money(r.total_internal_cost),
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
