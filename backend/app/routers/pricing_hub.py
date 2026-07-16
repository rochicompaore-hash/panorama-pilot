"""Pricing method configuration per product category + price simulator.

Metodi A-G:
  A. per_sqm     — Prezzo al metro quadrato
  B. tabular     — Matrice larghezza × altezza (price_matrices)
  C. per_piece   — Prezzo a pezzo
  D. per_linear  — Prezzo al metro lineare
  E. bom         — Distinta tecnica (BOM)
  F. hybrid      — Combinazione (finestra: profili+vetro+ferramenta+lavorazioni)
  G. formula     — Formula personalizzata (services.formula strict)
  H. manual_temporarily — Fallback (con motivazione)
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from app.db import get_db
from app.deps import require_permission
from app.mongo_utils import to_mongo, from_mongo
from app.models import BaseDoc, utcnow
from app.services.formula import eval_formula, FormulaError, strict_mode, validate_formula
from app.services.bom_recipes import list_recipes, get_recipe, compile_recipe
from app.services.bom_engine_v2 import resolve_bom_full


PricingMethod = Literal[
    "per_sqm", "tabular", "per_piece", "per_linear",
    "bom", "hybrid", "formula", "manual_temporarily",
]


class PricingMethodConfig(BaseDoc):
    """Metodo di calcolo per categoria prodotto."""
    category_code: str            # es. "roller_shutter", "window", "screen"
    label: str
    method: PricingMethod
    unit: Optional[str] = None    # €/m², €/pz, €/ml
    listino_ref: Optional[str] = None
    price_matrix_ref: Optional[str] = None
    bom_template_ref: Optional[str] = None
    formula_expr: Optional[str] = None
    minimum_billable_sqm: float = 0.0
    minimum_billable_price: float = 0.0
    maximum_billable_sqm: float = 0.0
    rounding_step: float = 0.01
    color_surcharge_pct: float = 0.0
    urgent_surcharge_pct: float = 0.0
    default_vat: float = 22.0
    manual_reason_required: bool = False
    manual_reason: Optional[str] = None
    version: int = 1
    published: bool = False
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    active: bool = True
    notes: Optional[str] = None


class PriceSimulateRequest(BaseModel):
    category_code: str
    width_mm: Optional[int] = None
    height_mm: Optional[int] = None
    quantity: float = 1.0
    linear_m: Optional[float] = None
    color_surcharge: bool = False
    urgent: bool = False
    manual_override_price: Optional[float] = None
    manual_override_reason: Optional[str] = None
    formula_vars: Dict[str, Any] = Field(default_factory=dict)


class PriceSimulateResponse(BaseModel):
    method: str
    unit_price_base: float = 0.0
    quantity_used: float = 1.0
    surface_real_sqm: float = 0.0
    surface_billable_sqm: float = 0.0
    linear_m_used: float = 0.0
    subtotal_before_surcharges: float = 0.0
    color_surcharge_amount: float = 0.0
    urgent_surcharge_amount: float = 0.0
    total_net: float = 0.0
    total_gross: float = 0.0
    vat_rate: float = 22.0
    detail: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


router = APIRouter(prefix="/pricing-hub", tags=["Pricing Hub"])


@router.get("/methods")
async def list_methods(user: dict = Depends(require_permission("pricelists.view"))):
    db = get_db()
    docs = await db.pricing_method_configs.find(
        {"tenant_id": user["tenant_id"], "deleted_at": None}
    ).sort([("category_code", 1)]).to_list(200)
    return {"items": [from_mongo(d) for d in docs]}


@router.post("/methods")
async def create_method(payload: dict, user: dict = Depends(require_permission("pricelists.manage"))):
    db = get_db()
    inst = PricingMethodConfig(tenant_id=user["tenant_id"], **payload)
    await db.pricing_method_configs.insert_one(to_mongo(inst.model_dump(by_alias=True)))
    return inst.model_dump()


@router.patch("/methods/{mid}")
async def update_method(mid: str, payload: dict, user: dict = Depends(require_permission("pricelists.manage"))):
    db = get_db()
    updates = {k: v for k, v in payload.items() if k != "id" and not k.startswith("_")}
    updates["updated_at"] = utcnow().isoformat()
    updates["updated_by"] = user["id"]
    await db.pricing_method_configs.update_one({"_id": mid, "tenant_id": user["tenant_id"]},
        {"$set": updates, "$inc": {"version": 1}})
    d = await db.pricing_method_configs.find_one({"_id": mid})
    return from_mongo(d)


@router.post("/methods/{mid}/publish")
async def publish_method(mid: str, user: dict = Depends(require_permission("pricelists.manage"))):
    db = get_db()
    m = await db.pricing_method_configs.find_one({"_id": mid, "tenant_id": user["tenant_id"]})
    if not m: raise HTTPException(404)
    # Validation before publish
    errors = []
    if m.get("method") == "formula" and not m.get("formula_expr"):
        errors.append("Formula mancante")
    if m.get("method") == "tabular" and not m.get("price_matrix_ref"):
        errors.append("Matrice tabellare mancante")
    if m.get("method") == "manual_temporarily" and not m.get("manual_reason"):
        errors.append("Motivazione obbligatoria per calcolo manuale temporaneo")
    if errors:
        raise HTTPException(400, {"errors": errors})
    await db.pricing_method_configs.update_one({"_id": mid},
        {"$set": {"published": True, "updated_at": utcnow().isoformat()}})
    return {"ok": True}


@router.post("/simulate", response_model=PriceSimulateResponse)
async def simulate_price(payload: PriceSimulateRequest,
                          user: dict = Depends(require_permission("pricelists.view"))):
    db = get_db()
    cfg = await db.pricing_method_configs.find_one({
        "tenant_id": user["tenant_id"], "category_code": payload.category_code,
        "active": True, "deleted_at": None,
    })
    if not cfg:
        raise HTTPException(404, f"Nessuna configurazione per '{payload.category_code}'")

    method = cfg.get("method")
    resp = PriceSimulateResponse(method=method, vat_rate=cfg.get("default_vat", 22.0))

    # Manual override
    if payload.manual_override_price is not None:
        if not payload.manual_override_reason:
            resp.errors.append("Override manuale richiede motivazione")
            return resp
        resp.method = "manual_override"
        resp.total_net = payload.manual_override_price * payload.quantity
        resp.detail["manual_reason"] = payload.manual_override_reason
        resp.total_gross = resp.total_net * (1 + resp.vat_rate/100.0)
        return resp

    # A) per_sqm
    if method == "per_sqm":
        if not (payload.width_mm and payload.height_mm):
            resp.errors.append("Larghezza/altezza mancanti")
            return resp
        w_m = payload.width_mm / 1000.0; h_m = payload.height_mm / 1000.0
        surface = round(w_m * h_m, 4)
        min_sqm = float(cfg.get("minimum_billable_sqm") or 0)
        billable = max(surface, min_sqm)
        # Prezzo unitario da listino (semplice: preso da cfg via listino_ref? qui usiamo formula_expr come €/m²)
        price_per_sqm = float(cfg.get("formula_expr") or 0) if cfg.get("formula_expr") else 0
        # Fallback: prova a prendere item_pricelists collegato
        if not price_per_sqm and cfg.get("listino_ref"):
            item = await db.item_pricelists.find_one({"_id": cfg["listino_ref"], "deleted_at": None})
            if item: price_per_sqm = float(item.get("sale_price") or 0)
        resp.unit_price_base = price_per_sqm
        resp.surface_real_sqm = surface
        resp.surface_billable_sqm = billable
        resp.quantity_used = payload.quantity
        resp.subtotal_before_surcharges = round(billable * price_per_sqm * payload.quantity, 2)
        if surface < min_sqm:
            resp.warnings.append(f"Superficie reale {surface} m² < min fatturabile {min_sqm} m²")

    # C) per_piece
    elif method == "per_piece":
        item = None
        if cfg.get("listino_ref"):
            item = await db.item_pricelists.find_one({"_id": cfg["listino_ref"], "deleted_at": None})
        base_price = float((item or {}).get("sale_price") or cfg.get("formula_expr") or 0)
        resp.unit_price_base = base_price
        resp.quantity_used = payload.quantity
        resp.subtotal_before_surcharges = round(base_price * payload.quantity, 2)

    # D) per_linear
    elif method == "per_linear":
        if not payload.linear_m:
            resp.errors.append("Metri lineari mancanti")
            return resp
        item = None
        if cfg.get("listino_ref"):
            item = await db.item_pricelists.find_one({"_id": cfg["listino_ref"], "deleted_at": None})
        base = float((item or {}).get("sale_price") or 0)
        resp.unit_price_base = base
        resp.linear_m_used = payload.linear_m
        resp.subtotal_before_surcharges = round(base * payload.linear_m * payload.quantity, 2)

    # B) tabular
    elif method == "tabular":
        if not (payload.width_mm and payload.height_mm and cfg.get("price_matrix_ref")):
            resp.errors.append("Matrice tabellare o dimensioni mancanti")
            return resp
        matrix = await db.price_matrices.find_one({"_id": cfg["price_matrix_ref"], "deleted_at": None})
        if not matrix:
            resp.errors.append("Matrice non trovata")
            return resp
        # trova la cella >= alle dimensioni (arrotondamento fascia superiore)
        cells = matrix.get("cells") or []
        best = None
        for c in cells:
            wc = c.get("width_max_mm") or c.get("width_mm") or 0
            hc = c.get("height_max_mm") or c.get("height_mm") or 0
            if wc >= payload.width_mm and hc >= payload.height_mm:
                if not best or (wc * hc) < (best.get("width_max_mm", 9e9) * best.get("height_max_mm", 9e9)):
                    best = c
        if not best:
            resp.errors.append("Nessuna cella tabellare valida per le misure")
            return resp
        resp.unit_price_base = float(best.get("price") or 0)
        resp.subtotal_before_surcharges = round(resp.unit_price_base * payload.quantity, 2)
        resp.detail["matrix_cell"] = best

    # G) formula
    elif method == "formula":
        expr = cfg.get("formula_expr")
        if not expr:
            resp.errors.append("Formula mancante")
            return resp
        ctx = dict(payload.formula_vars)
        if payload.width_mm: ctx["W"] = payload.width_mm; ctx["L"] = payload.width_mm/1000
        if payload.height_mm: ctx["H"] = payload.height_mm; ctx["A"] = payload.height_mm/1000
        try:
            with strict_mode():
                val = float(eval_formula(expr, ctx))
        except FormulaError as e:
            resp.errors.append(f"Errore formula: {e}")
            return resp
        resp.unit_price_base = val
        resp.subtotal_before_surcharges = round(val * payload.quantity, 2)

    # E/F) bom / hybrid — placeholder che usa listino
    elif method in ("bom", "hybrid"):
        # In modalità semplificata: somma dei costi BOM se presente template
        if cfg.get("bom_template_ref"):
            tpl = await db.bom_templates.find_one({"_id": cfg["bom_template_ref"], "deleted_at": None})
            if tpl:
                total = 0.0
                for row in tpl.get("rows") or []:
                    total += float(row.get("total_price") or row.get("unit_price") or 0)
                resp.unit_price_base = total
                resp.subtotal_before_surcharges = round(total * payload.quantity, 2)
                resp.detail["bom_rows_count"] = len(tpl.get("rows") or [])
            else:
                resp.warnings.append("BOM template non trovato — implementazione minima")
        else:
            resp.warnings.append("BOM/hybrid: implementazione minima. Usa 'manual_temporarily' come fallback.")

    elif method == "manual_temporarily":
        if payload.manual_override_price is None:
            resp.errors.append("Metodo manuale temporaneo richiede prezzo manuale")
            return resp
        resp.unit_price_base = payload.manual_override_price
        resp.subtotal_before_surcharges = payload.manual_override_price * payload.quantity

    else:
        resp.errors.append(f"Metodo '{method}' non implementato")
        return resp

    # Maggiorazioni
    sub = resp.subtotal_before_surcharges
    color_pct = float(cfg.get("color_surcharge_pct") or 0)
    urgent_pct = float(cfg.get("urgent_surcharge_pct") or 0)
    if payload.color_surcharge and color_pct:
        resp.color_surcharge_amount = round(sub * color_pct / 100.0, 2)
    if payload.urgent and urgent_pct:
        resp.urgent_surcharge_amount = round(sub * urgent_pct / 100.0, 2)
    net = sub + resp.color_surcharge_amount + resp.urgent_surcharge_amount
    # Minimum price
    min_price = float(cfg.get("minimum_billable_price") or 0)
    if net < min_price and min_price:
        resp.warnings.append(f"Applicato prezzo minimo {min_price} (calcolato {net})")
        net = min_price
    resp.total_net = round(net, 2)
    resp.total_gross = round(net * (1 + resp.vat_rate/100.0), 2)
    return resp


# Default seed: 1 config per categoria comune
DEFAULT_METHODS = [
    {"category_code": "window", "label": "Finestra", "method": "hybrid", "notes": "Da configurare con BOM template"},
    {"category_code": "french_door", "label": "Portafinestra", "method": "hybrid"},
    {"category_code": "fixed", "label": "Fisso", "method": "hybrid"},
    {"category_code": "sliding", "label": "Scorrevole", "method": "hybrid"},
    {"category_code": "entrance_door", "label": "Portoncino", "method": "per_piece"},
    {"category_code": "shutter", "label": "Persiana", "method": "per_sqm", "minimum_billable_sqm": 1.5},
    {"category_code": "obscurant", "label": "Scuro", "method": "per_sqm", "minimum_billable_sqm": 1.5},
    {"category_code": "roller_shutter", "label": "Tapparella", "method": "per_sqm",
     "minimum_billable_sqm": 1.75, "formula_expr": "96", "unit": "€/m²"},
    {"category_code": "screen", "label": "Zanzariera", "method": "per_sqm",
     "minimum_billable_sqm": 1.5, "formula_expr": "78", "unit": "€/m²"},
    {"category_code": "roller_box", "label": "Cassonetto", "method": "per_linear", "unit": "€/ml"},
    {"category_code": "glass", "label": "Vetro", "method": "per_sqm"},
    {"category_code": "accessory", "label": "Accessorio", "method": "per_piece"},
    {"category_code": "installation", "label": "Montaggio", "method": "per_piece"},
    {"category_code": "dismount", "label": "Smontaggio", "method": "per_piece"},
    {"category_code": "disposal", "label": "Smaltimento", "method": "per_piece"},
]


@router.post("/seed-defaults")
async def seed_defaults(user: dict = Depends(require_permission("pricelists.manage"))):
    db = get_db()
    created = 0
    for d in DEFAULT_METHODS:
        exists = await db.pricing_method_configs.find_one({
            "tenant_id": user["tenant_id"], "category_code": d["category_code"], "deleted_at": None
        })
        if exists: continue
        inst = PricingMethodConfig(tenant_id=user["tenant_id"], **d)
        await db.pricing_method_configs.insert_one(to_mongo(inst.model_dump(by_alias=True)))
        created += 1
    return {"ok": True, "created": created, "total": len(DEFAULT_METHODS)}


# =====================================================================
# BOM RECIPES — motore ricette visuale (Blocco A)
# =====================================================================

class BomRecipeCompileRequest(BaseModel):
    """Richiesta compilazione ricetta → BomComponent parziale."""
    recipe_code: str
    params: Dict[str, Any] = Field(default_factory=dict)


class BomSimulateRequest(BaseModel):
    """Simulatore BOM: dato un template + parametri → output esteso.
    Se sell_pricelist_id/cost_pricelist_id assenti, prezzi/costi risulteranno 0
    e verrà emesso un warning per riga (utile per debug tecnico)."""
    bom_template_id: str
    width_mm: int
    height_mm: int
    nr_ante: int = 1
    nr_traversi: int = 0
    nr_montanti: int = 0
    nr_fissi: int = 0
    color_category_id: Optional[str] = None
    color_id: Optional[str] = None
    glass_type_id: Optional[str] = None
    hardware_kit_id: Optional[str] = None
    sell_pricelist_id: Optional[str] = None
    cost_pricelist_id: Optional[str] = None
    include_costs: bool = True
    extra_params: Dict[str, Any] = Field(default_factory=dict)


@router.get("/bom-recipes")
async def bom_recipes_list(user: dict = Depends(require_permission("bom_templates.view"))):
    """Catalogo ricette disponibili (metadata). Filtra quelle che richiedono
    permessi elevati (es. FORMULA_LIBERA) in base al ruolo dell'utente."""
    recipes = list_recipes()
    can_advanced = (user.get("is_superadmin") or user.get("is_platform_owner")
                    or "products.manage" in (user.get("_perms") or []))
    if not can_advanced:
        recipes = [r for r in recipes if not r.get("requires_permission")]
    return {"items": recipes, "count": len(recipes)}


@router.post("/bom-recipes/compile")
async def bom_recipes_compile(payload: BomRecipeCompileRequest,
                              user: dict = Depends(require_permission("bom_templates.view"))):
    """Compila una ricetta con i suoi parametri → BomComponent parziale.
    L'UI visuale usa questo endpoint per mostrare live le formule generate
    prima di salvarle nel template BOM.
    """
    recipe = get_recipe(payload.recipe_code)
    if not recipe:
        raise HTTPException(404, f"Ricetta '{payload.recipe_code}' non trovata")
    if recipe.get("requires_permission"):
        perm = recipe["requires_permission"]
        if not (user.get("is_superadmin") or user.get("is_platform_owner")
                or perm in (user.get("_perms") or [])):
            raise HTTPException(403, f"Ricetta '{payload.recipe_code}' richiede il permesso {perm}")
    try:
        compiled = compile_recipe(payload.recipe_code, payload.params or {})
    except ValueError as e:
        raise HTTPException(400, str(e))
    # Validazione formule generate (assicura AST safe)
    validation_errors: List[str] = []
    for field in ("quantity_formula", "length_formula", "width_formula",
                   "height_formula", "area_formula", "weight_formula"):
        expr = compiled.get(field)
        if not expr:
            continue
        ok, err = validate_formula(expr)
        if not ok:
            validation_errors.append(f"{field}: {err}")
    return {
        "recipe": recipe,
        "compiled": compiled,
        "validation_errors": validation_errors,
    }


@router.post("/bom-simulate")
async def bom_simulate(payload: BomSimulateRequest,
                       user: dict = Depends(require_permission("pricelists.view"))):
    """Simulatore BOM esteso — output row-by-row con:
      componente, codice, descrizione, quantità netta, sfrido, quantità fatturata,
      unità, costo/prezzo unit., costo/prezzo tot., formula/ricetta, condizione,
      origine listino, versione, warning, errore bloccante.

    Restituisce anche aggregati per tipologia e uno snapshot hash per audit.
    """
    can_see_costs = (user.get("is_superadmin") or user.get("is_platform_owner")
                     or "pricelists.manage" in (user.get("_perms") or [])
                     or "quotes.view_costs" in (user.get("_perms") or [])
                     or "pricing.mode.view_cost_basis" in (user.get("_perms") or []))
    include_costs = payload.include_costs and can_see_costs
    params = {
        "width_mm": payload.width_mm, "height_mm": payload.height_mm,
        "nr_ante": payload.nr_ante, "nr_traversi": payload.nr_traversi,
        "nr_montanti": payload.nr_montanti, "nr_fissi": payload.nr_fissi,
        "color_category_id": payload.color_category_id,
        "color_id": payload.color_id,
        "glass_type_id": payload.glass_type_id,
        "hardware_kit_id": payload.hardware_kit_id,
        **(payload.extra_params or {}),
    }
    result = await resolve_bom_full(
        tenant_id=user["tenant_id"],
        bom_template_id=payload.bom_template_id,
        params=params,
        sell_pricelist_id=payload.sell_pricelist_id,
        cost_pricelist_id=payload.cost_pricelist_id,
        include_costs=include_costs,
    )
    # Se costi non visibili, redigi
    if not include_costs:
        for c in result.get("components") or []:
            c["unit_cost"] = None
            c["line_cost"] = None
            c["pricelist_origin_cost"] = None
        result["materials_cost"] = None
        result["cost_pricelist"] = None
        result["cost_redacted"] = True
    return result

