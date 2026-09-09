"""Multi-Category Pricing Engine.

Contiene:
  * ``SimplePricingEngine`` — per AREA / LINEAR_METER / PER_ITEM / FIXED_PRICE /
    FIXED_PLUS_VARIABLE / TIERED.
  * ``resolve_and_compute`` — resolver che, in base al ``pricing_model`` del
    prodotto, instrada al motore corretto:
      - FORMULA_TECHNICAL  -> ``app.services.pricing_v3.compute_pricing`` (motore
                              tecnico autorevole, NON duplicato).
      - altri modelli      -> ``SimplePricingEngine``.
      - MANUAL_REVIEW_REQUIRED -> nessun prezzo restituito (workflow futuro).

Fail-closed:
  * Prodotto senza ``pricing_model`` valido -> ``missing_pricing_model``.
  * Prodotto ``legacy=True`` o ``new_quote_enabled=False`` -> ``legacy_disabled``.
  * Inputs non validi per il modello -> ``invalid_inputs`` con dettaglio.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.models_multi_category import (
    PricingModel,
    VALID_PRICING_MODELS,
    ConfigureRequest,
    ConfigureResponse,
    SimplePricingInputs,
)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def _round2(x: float) -> float:
    return round(float(x) + 1e-9, 2)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_payload(payload: Dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _real_area_m2(width_mm: Optional[float], height_mm: Optional[float]) -> Optional[float]:
    if not width_mm or not height_mm:
        return None
    return round((float(width_mm) / 1000.0) * (float(height_mm) / 1000.0) + 1e-9, 4)


# ---------------------------------------------------------------------------
# Simple Pricing Engine
# ---------------------------------------------------------------------------
class SimplePricingEngine:
    """Motore semplice per pricing non-tecnici (backend-authoritative).

    Ogni metodo restituisce un dizionario ``simple_snapshot`` con i campi
    caratteristici del modello e ``sale_price_total`` finale.
    """

    @staticmethod
    def compute_area(product: Dict[str, Any], inputs: SimplePricingInputs) -> Dict[str, Any]:
        cfg = product.get("pricing_config") or {}
        unit_price = cfg.get("unit_sale_price")
        if unit_price is None:
            raise ValueError("MISSING_UNIT_SALE_PRICE")
        min_billable = product.get("minimum_billable_quantity") or cfg.get("minimum_billable_area_m2") or 0.0
        real_area = _real_area_m2(inputs.width_mm, inputs.height_mm)
        if real_area is None or real_area <= 0:
            raise ValueError("INVALID_DIMENSIONS")
        billable_area = max(real_area, float(min_billable)) if min_billable else real_area
        qty = max(float(inputs.quantity or 1), 1.0)
        unit_price_final = _round2(billable_area * float(unit_price))
        sale_price_total = _round2(unit_price_final * qty)
        return {
            "pricing_model": PricingModel.AREA.value,
            "width_mm": inputs.width_mm,
            "height_mm": inputs.height_mm,
            "real_area_m2": real_area,
            "minimum_billable_area_m2": float(min_billable) if min_billable else None,
            "billable_area_m2": billable_area,
            "unit_sale_price": float(unit_price),
            "unit_price_final": unit_price_final,
            "quantity": qty,
            "sale_price_total": sale_price_total,
            "sale_unit": "m2",
        }

    @staticmethod
    def compute_linear(product: Dict[str, Any], inputs: SimplePricingInputs) -> Dict[str, Any]:
        cfg = product.get("pricing_config") or {}
        unit_price = cfg.get("unit_sale_price")
        if unit_price is None:
            raise ValueError("MISSING_UNIT_SALE_PRICE")
        min_billable = product.get("minimum_billable_quantity") or cfg.get("minimum_billable_linear_meters") or 0.0
        ml = float(inputs.linear_meters or 0)
        if ml <= 0:
            raise ValueError("INVALID_LINEAR_METERS")
        billable_ml = max(ml, float(min_billable)) if min_billable else ml
        qty = max(float(inputs.quantity or 1), 1.0)
        unit_price_final = _round2(billable_ml * float(unit_price))
        sale_price_total = _round2(unit_price_final * qty)
        return {
            "pricing_model": PricingModel.LINEAR_METER.value,
            "linear_meters": ml,
            "minimum_billable_linear_meters": float(min_billable) if min_billable else None,
            "billable_linear_meters": billable_ml,
            "unit_sale_price": float(unit_price),
            "unit_price_final": unit_price_final,
            "quantity": qty,
            "sale_price_total": sale_price_total,
            "sale_unit": "ml",
        }

    @staticmethod
    def compute_per_item(product: Dict[str, Any], inputs: SimplePricingInputs) -> Dict[str, Any]:
        cfg = product.get("pricing_config") or {}
        unit_price = cfg.get("unit_sale_price")
        if unit_price is None:
            raise ValueError("MISSING_UNIT_SALE_PRICE")
        qty = float(inputs.quantity or 0)
        if qty <= 0:
            raise ValueError("INVALID_QUANTITY")
        sale_price_total = _round2(float(unit_price) * qty)
        return {
            "pricing_model": PricingModel.PER_ITEM.value,
            "unit_sale_price": float(unit_price),
            "unit_price_final": _round2(float(unit_price)),
            "quantity": qty,
            "sale_price_total": sale_price_total,
            "variant": inputs.variant,
            "sale_unit": "pz",
        }

    @staticmethod
    def compute_fixed_price(product: Dict[str, Any], inputs: SimplePricingInputs) -> Dict[str, Any]:
        cfg = product.get("pricing_config") or {}
        fixed = cfg.get("fixed_sale_price")
        if fixed is None:
            raise ValueError("MISSING_FIXED_SALE_PRICE")
        qty = max(float(inputs.quantity or 1), 1.0)
        sale_price_total = _round2(float(fixed) * qty)
        return {
            "pricing_model": PricingModel.FIXED_PRICE.value,
            "fixed_sale_price": float(fixed),
            "unit_price_final": _round2(float(fixed)),
            "quantity": qty,
            "sale_price_total": sale_price_total,
            "sale_unit": "forfait",
        }

    @staticmethod
    def compute_fixed_plus_variable(product: Dict[str, Any], inputs: SimplePricingInputs) -> Dict[str, Any]:
        cfg = product.get("pricing_config") or {}
        fixed = cfg.get("fixed_component")
        variable_unit = cfg.get("variable_unit_price")
        variable_basis = (cfg.get("variable_basis") or "quantity").lower()  # quantity | area | linear
        if fixed is None or variable_unit is None:
            raise ValueError("MISSING_FIXED_OR_VARIABLE_PRICE")

        basis_value = 0.0
        if variable_basis == "area":
            ra = _real_area_m2(inputs.width_mm, inputs.height_mm)
            if ra is None or ra <= 0:
                raise ValueError("INVALID_DIMENSIONS_FOR_VARIABLE_BASIS")
            basis_value = ra
        elif variable_basis == "linear":
            basis_value = float(inputs.linear_meters or 0)
            if basis_value <= 0:
                raise ValueError("INVALID_LINEAR_FOR_VARIABLE_BASIS")
        else:
            basis_value = float(inputs.quantity or 1)

        variable_component = _round2(float(variable_unit) * basis_value)
        qty = max(float(inputs.quantity or 1), 1.0)
        unit_price = _round2(float(fixed) + variable_component)
        sale_price_total = _round2(unit_price * qty)
        return {
            "pricing_model": PricingModel.FIXED_PLUS_VARIABLE.value,
            "fixed_component": float(fixed),
            "variable_unit_price": float(variable_unit),
            "variable_basis": variable_basis,
            "variable_basis_value": basis_value,
            "variable_component": variable_component,
            "unit_price_final": unit_price,
            "quantity": qty,
            "sale_price_total": sale_price_total,
            "sale_unit": product.get("sale_unit") or "pz",
        }

    @staticmethod
    def compute_tiered(product: Dict[str, Any], inputs: SimplePricingInputs) -> Dict[str, Any]:
        cfg = product.get("pricing_config") or {}
        tiers = cfg.get("tiers") or []
        if not tiers:
            raise ValueError("MISSING_TIERS")
        basis = (cfg.get("tier_basis") or "quantity").lower()  # quantity | area | linear
        basis_value = 0.0
        if basis == "area":
            ra = _real_area_m2(inputs.width_mm, inputs.height_mm)
            if ra is None or ra <= 0:
                raise ValueError("INVALID_DIMENSIONS_FOR_TIERED")
            basis_value = ra
        elif basis == "linear":
            basis_value = float(inputs.linear_meters or 0)
        else:
            basis_value = float(inputs.quantity or 1)

        # Selezione tier: primo tier con basis_value <= up_to (o l'ultimo se supera)
        selected = None
        for t in sorted(tiers, key=lambda x: (x.get("up_to") is None, x.get("up_to") or 1e18)):
            up = t.get("up_to")
            if up is None or basis_value <= float(up):
                selected = t
                break
        if selected is None:
            selected = tiers[-1]
        unit_price = selected.get("unit_sale_price")
        if unit_price is None:
            raise ValueError("MISSING_TIER_UNIT_PRICE")
        qty = max(float(inputs.quantity or 1), 1.0)
        line_total = _round2(float(unit_price) * basis_value)
        sale_price_total = _round2(line_total * qty)
        return {
            "pricing_model": PricingModel.TIERED.value,
            "tier_basis": basis,
            "tier_basis_value": basis_value,
            "tier_selected": selected,
            "unit_price_final": _round2(float(unit_price)),
            "quantity": qty,
            "sale_price_total": sale_price_total,
            "sale_unit": product.get("sale_unit") or basis,
        }

    # -------- dispatch --------
    @classmethod
    def compute(cls, product: Dict[str, Any], inputs: SimplePricingInputs) -> Dict[str, Any]:
        model = product.get("pricing_model")
        if model == PricingModel.AREA.value:
            return cls.compute_area(product, inputs)
        if model == PricingModel.LINEAR_METER.value:
            return cls.compute_linear(product, inputs)
        if model == PricingModel.PER_ITEM.value:
            return cls.compute_per_item(product, inputs)
        if model == PricingModel.FIXED_PRICE.value:
            return cls.compute_fixed_price(product, inputs)
        if model == PricingModel.FIXED_PLUS_VARIABLE.value:
            return cls.compute_fixed_plus_variable(product, inputs)
        if model == PricingModel.TIERED.value:
            return cls.compute_tiered(product, inputs)
        if model == "GRID":
            return cls.compute_grid(product, inputs)
        if model == PricingModel.AREA_PURCHASE_MULTIPLIER.value:
            return cls.compute_area_purchase_multiplier(product, inputs)
        raise ValueError(f"UNSUPPORTED_SIMPLE_MODEL:{model}")

    # -------- extended: AREA with color category table (Zanzariere/Tapparelle) --------
    @staticmethod
    def compute_area_by_color(product: Dict[str, Any], inputs: SimplePricingInputs, color_lookup: Dict[str, str]) -> Dict[str, Any]:
        """AREA con tabella prezzi per categoria colore.

        Args:
          product: pricing_config deve avere ``purchase_cost_table_per_m2`` (§20 zanzariere)
                    o ``sale_price_table_per_m2`` (§34 tapparelle).
          inputs: options.color_code obbligatorio.
          color_lookup: dict {color_code: price_category}.

        Vincolo §3 zanzariere: minimo per pezzo, MOLTIPLICAZIONE per quantity SOLO dopo
        avere calcolato il billable_area del singolo pezzo.
        """
        cfg = product.get("pricing_config") or {}
        color_code = (inputs.options or {}).get("color_code")
        if not color_code:
            raise ValueError("MISSING_COLOR_CODE")
        category = color_lookup.get(color_code)
        if not category or category == "NEEDS_PO_MAPPING":
            raise ValueError("MISSING_COLOR_PRICE_CATEGORY")

        real_area = _real_area_m2(inputs.width_mm, inputs.height_mm)
        if real_area is None or real_area <= 0:
            raise ValueError("INVALID_DIMENSIONS")
        min_bill = product.get("minimum_billable_quantity") or cfg.get("minimum_billable_area_m2") or 0.0
        billable_area = max(real_area, float(min_bill)) if min_bill else real_area
        qty = max(float(inputs.quantity or 1), 1.0)
        multiplier = float(cfg.get("commercial_multiplier") or 1.0)

        # Two supported price sources:
        purchase_tbl = cfg.get("purchase_cost_table_per_m2") or {}
        sale_tbl = cfg.get("sale_price_table_per_m2") or {}

        if purchase_tbl:
            purchase_unit_cost = purchase_tbl.get(category)
            if purchase_unit_cost is None:
                raise ValueError(f"MISSING_PURCHASE_PRICE_FOR_CATEGORY:{category}")
            purchase_cost_per_item = _round2(billable_area * float(purchase_unit_cost))
            sale_price_per_item = _round2(purchase_cost_per_item * multiplier)
            unit_sale_per_m2 = _round2(float(purchase_unit_cost) * multiplier)
        else:
            unit_sale = sale_tbl.get(category)
            if unit_sale is None:
                raise ValueError(f"MISSING_SALE_PRICE_FOR_CATEGORY:{category}")
            purchase_unit_cost = None
            purchase_cost_per_item = None
            sale_price_per_item = _round2(billable_area * float(unit_sale))
            unit_sale_per_m2 = float(unit_sale)

        sale_price_total = _round2(sale_price_per_item * qty)
        return {
            "pricing_model": PricingModel.AREA.value,
            "color_code": color_code,
            "color_price_category": category,
            "width_mm": inputs.width_mm,
            "height_mm": inputs.height_mm,
            "real_area_m2": real_area,
            "minimum_billable_area_m2": float(min_bill) if min_bill else None,
            "billable_area_m2_per_item": billable_area,
            "purchase_unit_cost_per_m2": purchase_unit_cost,
            "purchase_cost_per_item": purchase_cost_per_item,
            "commercial_multiplier": multiplier if purchase_tbl else None,
            "unit_sale_price_per_m2": unit_sale_per_m2,
            "sale_price_per_item": sale_price_per_item,
            # Canonical contract (§6 PO): every simple engine MUST expose
            # ``unit_price_final`` (per billed unit) and ``sale_price_total``.
            # Here billed unit == item, so unit_price_final == sale_price_per_item.
            "unit_price_final": sale_price_per_item,
            "quantity": qty,
            "sale_price_total": sale_price_total,
            "sale_unit": "m2",
            "pricing_version": cfg.get("pricing_version"),
        }

    # -------- GRID (cassonetti) --------
    @staticmethod
    def compute_grid(product: Dict[str, Any], inputs: SimplePricingInputs, finish_family: Optional[str] = None) -> Dict[str, Any]:
        """DIMENSIONAL_PRICE_GRID lookup for cassonetti (§29-33).

        Args:
          product.pricing_config = {
            grid_version, depths_mm[], grid: {family: {"{depth}_{ciel}": {"WxH": {internal, sale}}}}
          }
          inputs.options = {
            depth_mm ∈ {163,326,489,652},
            ceiling_liner ∈ {SI,NO},
            finish_family passed as arg (resolved from color_code by caller)
          }
        """
        cfg = product.get("pricing_config") or {}
        grid = cfg.get("grid") or {}
        opts = inputs.options or {}
        try:
            depth = int(round(float(opts.get("depth_mm") or 0)))
        except (TypeError, ValueError):
            raise ValueError("INVALID_DEPTH")
        ceiling_raw = opts.get("ceiling_liner")
        if ceiling_raw is None and "has_cielino" in opts:
            ceiling_raw = "SI" if opts.get("has_cielino") else "NO"
        ceiling = str(ceiling_raw or "").upper()
        try:
            w = int(round(float(inputs.width_mm or 0)))
            h = int(round(float(inputs.height_mm or 0)))
        except (TypeError, ValueError):
            raise ValueError("INVALID_DIMENSIONS")
        if depth not in (163, 326, 489, 652):
            raise ValueError("INVALID_DEPTH")
        if ceiling not in ("SI", "NO"):
            raise ValueError("INVALID_CEILING_LINER")
        if w <= 0 or h <= 0:
            raise ValueError("INVALID_DIMENSIONS")
        if not finish_family:
            raise ValueError("MISSING_CASSONETTO_COLOR_PRICE_FAMILY")
        if finish_family not in grid:
            raise ValueError(f"UNKNOWN_FINISH_FAMILY:{finish_family}")

        col_key = f"{depth}_{'c' if ceiling == 'SI' else 'nc'}"
        subgrid = grid[finish_family].get(col_key) or {}
        dim_key = f"{w}x{h}"
        cell = subgrid.get(dim_key)
        if not cell:
            # Fail-closed: nessuna interpolazione/nearest — la cella deve esistere.
            widths = sorted({int(k.split("x")[0]) for k in subgrid.keys()}) or []
            heights = sorted({int(k.split("x")[1]) for k in subgrid.keys()}) or []
            w_hint = f"L {widths[0]}-{widths[-1]} step 100" if widths else "L n/d"
            h_hint = f"H {'/'.join(str(x) for x in heights)}" if heights else "H n/d"
            raise ValueError(f"DIMENSION_TO_CONFIRM:{w}x{h} non in griglia ({w_hint}; {h_hint})")
        internal_cost = float(cell.get("internal") or 0)
        sale = float(cell.get("sale") or 0)
        if sale <= 0:
            raise ValueError("MISSING_CASSONETTO_SALE_PRICE")
        if internal_cost <= 0:
            raise ValueError("MISSING_CASSONETTO_INTERNAL_COST")
        qty = max(float(inputs.quantity or 1), 1.0)
        sale_price_total = _round2(sale * qty)
        return {
            "pricing_model": "GRID",
            "width_mm": w, "height_mm": h,
            "cassonetto_width_mm": w, "cassonetto_height_mm": h,
            "depth_mm": depth,
            "ceiling_liner": ceiling,
            "has_cielino": ceiling == "SI",
            "finish_family": finish_family,
            "price_family": finish_family,
            "color_code": opts.get("color_code"),
            "grid_key": f"{finish_family}/{col_key}/{dim_key}",
            "internal_production_cost_per_item": _round2(internal_cost),
            "customer_sale_price_per_item": _round2(sale),
            "unit_price_final": _round2(sale),
            "quantity": qty,
            "sale_price_total": sale_price_total,
            "sale_unit": "pz",
            "grid_version": cfg.get("grid_version"),
        }

    # -------- AREA_PURCHASE_MULTIPLIER (persiane) --------
    @staticmethod
    def compute_area_purchase_multiplier(product: Dict[str, Any], inputs: SimplePricingInputs) -> Dict[str, Any]:
        """PERSIANE: billable_area(min per pezzo) × (purchase_rate + orientable_surcharge) × multiplier.

        pricing_config = {
          purchase_cost_table_per_m2: {RAL, WOOD, SPECIAL},
          color_map: {color_code -> category},
          minimum_billable_area_m2, commercial_multiplier,
          orientable_surcharge_per_m2,
        }
        options = {color_code | color_category, orientable: bool}
        """
        cfg = product.get("pricing_config") or {}
        opts = inputs.options or {}
        table = cfg.get("purchase_cost_table_per_m2") or {}
        if not table:
            raise ValueError("MISSING_PURCHASE_RATE_TABLE")
        multiplier = cfg.get("commercial_multiplier")
        if multiplier is None or float(multiplier) <= 0:
            raise ValueError("MISSING_COMMERCIAL_MULTIPLIER")
        color_map = cfg.get("color_map") or {}
        color_code = opts.get("color_code")
        category = opts.get("color_category") or (color_map.get(color_code) if color_code else None)
        if not category:
            raise ValueError("MISSING_COLOR_PRICE_CATEGORY")
        base_rate = table.get(category)
        if base_rate is None:
            raise ValueError(f"MISSING_PURCHASE_PRICE_FOR_CATEGORY:{category}")
        if "orientable" not in opts or opts.get("orientable") is None:
            raise ValueError("MISSING_ORIENTABLE_STATE")
        orientable = bool(opts.get("orientable"))
        surcharge = float(cfg.get("orientable_surcharge_per_m2") or 0) if orientable else 0.0
        if orientable and surcharge <= 0:
            raise ValueError("MISSING_ORIENTABLE_SURCHARGE")

        real_area = _real_area_m2(inputs.width_mm, inputs.height_mm)
        if real_area is None or real_area <= 0:
            raise ValueError("INVALID_DIMENSIONS")
        min_bill = float(product.get("minimum_billable_quantity") or cfg.get("minimum_billable_area_m2") or 0.0)
        billable_area = max(real_area, min_bill) if min_bill else real_area
        qty = float(inputs.quantity or 0)
        if qty <= 0:
            raise ValueError("INVALID_QUANTITY")

        effective_rate = _round2(float(base_rate) + surcharge)
        purchase_per_item = _round2(billable_area * effective_rate)
        unit_price_final = _round2(purchase_per_item * float(multiplier))
        return {
            "pricing_model": PricingModel.AREA_PURCHASE_MULTIPLIER.value,
            "width_mm": inputs.width_mm,
            "height_mm": inputs.height_mm,
            "real_area_m2": real_area,
            "minimum_billable_area_m2": min_bill or None,
            "billable_area_m2": billable_area,
            "billable_area_m2_per_item": billable_area,
            "color_code": color_code,
            "color_price_category": category,
            "orientable": orientable,
            "orientable_surcharge_per_m2": surcharge if orientable else 0.0,
            "purchase_rate_per_m2": float(base_rate),
            "effective_purchase_rate": effective_rate,
            "purchase_cost_per_item": purchase_per_item,
            "purchase_total_cost": _round2(purchase_per_item * qty),
            "commercial_multiplier": float(multiplier),
            "unit_sale_price_per_m2": _round2(effective_rate * float(multiplier)),
            "sale_price_per_item": unit_price_final,
            "unit_price_final": unit_price_final,
            "quantity": qty,
            "sale_price_total": _round2(unit_price_final * qty),
            "sale_unit": "m2",
            "pricing_version": cfg.get("pricing_version"),
        }


# ---------------------------------------------------------------------------
# Resolver: decide dove instradare in base al pricing_model del prodotto
# ---------------------------------------------------------------------------
def _pack_product(product: Dict[str, Any]) -> Dict[str, Any]:
    """Slim public product info per la risposta."""
    return {
        "id": product.get("id") or product.get("_id"),
        "key": product.get("key"),
        "code": product.get("key"),
        "name": product.get("name"),
        "category_id": product.get("category_id"),
        "category_code": product.get("category_code"),
        "pricing_model": product.get("pricing_model"),
        "sale_unit": product.get("sale_unit"),
    }


async def quotable_configurations(db, tenant_id: str, product_key: str) -> Dict[str, List[int]]:
    """Configurazioni (window_type -> numero ante) realmente prezzabili con dati autoritativi:
    ricetta tecnica + regola ferramenta + tempo produzione tutti presenti. Nessuna invenzione (PO msg 627 §2-§4)."""
    pk = (product_key or "").upper()
    recipes = set()
    async for r in db.technical_recipes.find({"tenant_id": {"$in": [tenant_id, "*"]}, "product_key": pk, "active": True, "deleted_at": None}, {"recipe_code": 1}):
        recipes.add(r.get("recipe_code"))
    hw = set()
    async for h in db.hardware_rules.find({"active": True, "deleted_at": None}, {"opening_type": 1, "number_of_sashes": 1}):
        hw.add((h.get("opening_type"), h.get("number_of_sashes")))
    pt = set()
    async for t in db.production_time_configs.find({"active": True, "deleted_at": None}, {"recipe_code": 1}):
        pt.add(t.get("recipe_code"))
    out: Dict[str, List[int]] = {}
    for wt in ("WINDOW", "DOOR_WINDOW"):
        ok = [n for n in (1, 2, 3, 4) if f"{wt}_{n}_SASH" in recipes and f"{wt}_{n}_SASH" in pt and (wt, n) in hw]
        if ok:
            out[wt] = ok
    return out


async def resolve_and_compute(
    product: Dict[str, Any],
    category: Optional[Dict[str, Any]],
    req: ConfigureRequest,
    tenant_id: str,
) -> ConfigureResponse:
    """Resolver principale — fail-closed. Allega sempre il VisualSpec (P0 msg 625)."""
    resp = await _resolve_and_compute_core(product, category, req, tenant_id)
    from app.db import get_db
    from app.services.visual_spec import build_visual_spec, build_visual
    cfg: Dict[str, Any] = {}
    if req.technical_inputs:
        cfg = dict(req.technical_inputs)
    elif req.simple_inputs:
        si = req.simple_inputs
        cfg = {"width_mm": si.width_mm, "height_mm": si.height_mm, "quantity": si.quantity, **(si.options or {})}
    try:
        resp.visual = build_visual(await build_visual_spec(get_db(), tenant_id, product, category, cfg))
    except Exception as _ve:  # visual non deve mai bloccare il pricing
        import logging
        logging.getLogger(__name__).error(f"visual_spec build failed: {_ve}")
    return resp


async def _resolve_and_compute_core(
    product: Dict[str, Any],
    category: Optional[Dict[str, Any]],
    req: ConfigureRequest,
    tenant_id: str,
) -> ConfigureResponse:
    """Resolver principale — fail-closed.

    Args:
      product: doc prodotto (già letto dal router).
      category: doc categoria (opzionale, per contesto).
      req: input configurazione.
      tenant_id: tenant.
    """
    now = _iso_now()
    inputs_echo = req.model_dump(exclude_none=True)

    # --- Guard: legacy / disabled ---
    if product.get("legacy") or not product.get("new_quote_enabled", False):
        return ConfigureResponse(
            pricing_status="legacy_disabled",
            pricing_model=product.get("pricing_model"),
            calculated_at=now,
            product=_pack_product(product),
            category=category or {},
            inputs_echo=inputs_echo,
            blocking_errors=["Prodotto legacy o non abilitato al nuovo preventivatore."],
        )

    model = product.get("pricing_model")

    # --- Guard: missing/invalid pricing_model ---
    if not model or model not in VALID_PRICING_MODELS:
        return ConfigureResponse(
            pricing_status="missing_pricing_model",
            pricing_model=model,
            calculated_at=now,
            product=_pack_product(product),
            category=category or {},
            inputs_echo=inputs_echo,
            blocking_errors=["Il prodotto non ha un pricing_model valido configurato."],
        )

    # --- MANUAL_REVIEW_REQUIRED: nessun prezzo restituito ---
    if model == PricingModel.MANUAL_REVIEW_REQUIRED.value:
        return ConfigureResponse(
            pricing_status="manual_review_required",
            pricing_model=model,
            calculated_at=now,
            product=_pack_product(product),
            category=category or {},
            inputs_echo=inputs_echo,
            warnings=["Configurazione da verificare. Prezzo non assegnabile dal commerciale."],
        )

    # --- FORMULA_TECHNICAL: usa il motore autorevole (NO duplicazione) ---
    if model == PricingModel.FORMULA_TECHNICAL.value:
        if not req.technical_inputs:
            return ConfigureResponse(
                pricing_status="invalid_inputs",
                pricing_model=model,
                calculated_at=now,
                product=_pack_product(product),
                category=category or {},
                inputs_echo=inputs_echo,
                blocking_errors=["technical_inputs richiesti per FORMULA_TECHNICAL."],
            )
        from app.services.pricing_v3 import PricingRequest, compute_pricing

        ti = req.technical_inputs or {}
        # PO msg 627: una configurazione selezionabile DEVE essere prezzabile -> altrimenti FAIL CLOSED esplicito.
        from app.db import get_db as _gdb
        _wt = str(ti.get("window_type") or "WINDOW").upper()
        _n = int(ti.get("number_of_sashes") or 1)
        _q = await quotable_configurations(_gdb(), tenant_id, ti.get("product_key") or product.get("key") or "")
        if _n not in (_q.get(_wt) or []):
            return ConfigureResponse(
                pricing_status="not_available",
                pricing_model=model,
                calculated_at=now,
                product=_pack_product(product),
                category=category or {},
                inputs_echo=inputs_echo,
                blocking_errors=[f"CONFIGURATION_NOT_AVAILABLE_FOR_QUOTING: {_wt} {_n} ante non prezzabile (dati tecnici autoritativi assenti). Configurazioni disponibili: {_q}"],
            )
        # COLOR INPUT V2 fail-closed (PO msg 712/§4): codice o nome vuoto → mai prezzo, mai default silenzioso a WHITE_MASS.
        _mode = str(ti.get("color_mode") or "").upper()
        if _mode and _mode != "WHITE_MASS":
            _sides = [("external", "color_external", "color_external_name")]
            if _mode == "BICOLOR":
                _sides.append(("internal", "color_internal", "color_internal_name"))
            _cerrs = []
            for _side, _ck, _nk in _sides:
                if not str(ti.get(_ck) or "").strip():
                    _cerrs.append(f"COLOR_CODE_REQUIRED: codice colore {_side} obbligatorio")
                elif not str(ti.get(_nk) or "").strip():
                    _cerrs.append(f"COLOR_NAME_REQUIRED: nome colore {_side} obbligatorio")
            if _cerrs:
                return ConfigureResponse(
                    pricing_status="incomplete", pricing_model=model, calculated_at=now,
                    product=_pack_product(product), category=category or {}, inputs_echo=inputs_echo,
                    blocking_errors=_cerrs,
                )
        try:
            pr = PricingRequest(
                tenant_id=tenant_id,
                product_key=(ti.get("product_key") or product.get("key") or "").upper(),
                window_type=str(ti.get("window_type") or "WINDOW").upper(),
                number_of_sashes=int(ti.get("number_of_sashes") or 1),
                width_mm=int(ti.get("width_mm") or 0),
                height_mm=int(ti.get("height_mm") or 0),
                color_internal=str(ti.get("color_internal") or "WHITE_MASS").upper(),
                color_external=str(ti.get("color_external") or "WHITE_MASS").upper(),
                glass_type=str(ti.get("glass_type") or "DOUBLE_STANDARD").upper(),
                quantity=int(ti.get("quantity") or 1),
                weld_allowance_mm=int(ti.get("weld_allowance_mm") or 3),
                override_multiplier=ti.get("override_multiplier"),
            )
        except (TypeError, ValueError) as e:
            return ConfigureResponse(
                pricing_status="invalid_inputs",
                pricing_model=model,
                calculated_at=now,
                product=_pack_product(product),
                category=category or {},
                inputs_echo=inputs_echo,
                blocking_errors=[f"technical_inputs non validi: {e}"],
            )
        result = await compute_pricing(pr)
        # pricing_v3 restituisce errori strutturati (dict) — ConfigureResponse vuole stringhe.
        errs = []
        for e in (result.blocking_errors or []):
            if isinstance(e, dict):
                code = e.get("code") or "PRICING_ERROR"
                hint = e.get("hint") or e.get("message") or ""
                cfgd = e.get("configuration")
                errs.append((f"{code}: {hint}" if hint else code) + (f" [{cfgd}]" if cfgd else ""))
            else:
                errs.append(str(e))
        return ConfigureResponse(
            pricing_status=result.pricing_status,
            pricing_model=model,
            engine_version=f"technical:{result.engine_version}",
            calculated_at=result.calculated_at or now,
            product=_pack_product(product),
            category=category or {},
            inputs_echo=inputs_echo,
            technical_snapshot=result.technical_snapshot,
            commercial_snapshot=result.commercial_snapshot,
            calculation_hash=result.calculation_hash,
            blocking_errors=errs,
        )

    # --- Simple Pricing Engine per gli altri modelli ---
    if not req.simple_inputs:
        return ConfigureResponse(
            pricing_status="invalid_inputs",
            pricing_model=model,
            calculated_at=now,
            product=_pack_product(product),
            category=category or {},
            inputs_echo=inputs_echo,
            blocking_errors=["simple_inputs richiesti per questo pricing_model."],
        )
    try:
        # Router extension F1: AREA con tabella colori (Zanzariere/Tapparelle) e GRID (Cassonetti)
        pcfg = product.get("pricing_config") or {}
        has_color_table = bool(pcfg.get("purchase_cost_table_per_m2") or pcfg.get("sale_price_table_per_m2"))
        color_code = (req.simple_inputs.options or {}).get("color_code")

        if model == "GRID":
            # Cassonetti (P0 msg 625 §14): COLOR CODE -> PRICE FAMILY via mapping autoritativo rigido.
            # Nessun surcharge finestra, nessun fallback: codice non mappato -> CASSONETTO_COLOR_FAMILY_UNMAPPED.
            from app.services.color_engine import resolve_cassonetto_family
            finish_family = resolve_cassonetto_family(color_code)
            snap = SimplePricingEngine.compute_grid(product, req.simple_inputs, finish_family=finish_family)
        elif model == PricingModel.AREA_PURCHASE_MULTIPLIER.value:
            snap = SimplePricingEngine.compute_area_purchase_multiplier(product, req.simple_inputs)
        elif model == PricingModel.AREA.value and has_color_table and color_code:
            # Zanzariere: risolvi da zanzariere_colors. Tapparelle: risolvi da product.pricing_config.color_lookup
            from app.db import get_db
            db = get_db()
            color_domain = pcfg.get("color_domain") or "PVC"  # PVC | ZANZARIERE | INTERNAL_MAP
            lookup: dict = {}
            if color_domain == "ZANZARIERE":
                async for cdoc in db.zanzariere_colors.find({"tenant_id": tenant_id, "deleted_at": None, "active": True}):
                    lookup[cdoc.get("code")] = cdoc.get("price_category")
            elif color_domain == "INTERNAL_MAP":
                # product-embedded map for TAPPARELLE-like (RAL/LEGNO/RAFFAELLO)
                lookup = pcfg.get("color_map") or {}
            else:
                async for cdoc in db.product_colors.find({"tenant_id": tenant_id, "deleted_at": None, "active": True}):
                    lookup[cdoc.get("code")] = cdoc.get("pvc_color_category")
            snap = SimplePricingEngine.compute_area_by_color(product, req.simple_inputs, lookup)
        else:
            snap = SimplePricingEngine.compute(product, req.simple_inputs)
    except ValueError as e:
        return ConfigureResponse(
            pricing_status="invalid_inputs",
            pricing_model=model,
            calculated_at=now,
            product=_pack_product(product),
            category=category or {},
            inputs_echo=inputs_echo,
            blocking_errors=[str(e)],
        )

    calc_hash = _hash_payload({
        "product_id": product.get("id") or product.get("_id"),
        "pricing_model": model,
        "snap": snap,
    })
    return ConfigureResponse(
        pricing_status="ok",
        pricing_model=model,
        engine_version="simple_pricing_v1",
        calculated_at=now,
        product=_pack_product(product),
        category=category or {},
        inputs_echo=inputs_echo,
        simple_snapshot=snap,
        calculation_hash=calc_hash,
    )
