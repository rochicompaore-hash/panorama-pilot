"""Pricing Modes Engine — A (tabella), B (BOM), C (ibrida).

Risoluzione modalità (priorità DECRESCENTE):
  1. line override (con permesso pricing.mode.override)
  2. product-level config (product_key)
  3. profile_system-level config
  4. tenant-level config
Se nessuna disponibile → errore esplicito.

Modalità:
- A_table  → prezzo = matrix.lookup(w, h); costo opzionale (BOM se disponibile)
- B_bom    → prezzo = materials_price + lavorazioni + indiretti + margine; costo = materials_cost
- C_hybrid → prezzo = matrix.lookup(w, h); costo = BOM materials_cost + lavorazioni

Snapshot: ogni preview produce un ParametricSnapshot con hash canonici degli input.
"""
from __future__ import annotations
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple, List
from decimal import Decimal

from app.db import get_db
from app.services.formula import eval_formula, FormulaError, money
from app.services.matrix_lookup import lookup_price as matrix_lookup
from app.services.parametric_engine import resolve_bom, collect_cutting_inputs, build_formula_context
from app.services.svg_drawing import draw_window, sanitize_svg
from app.services.nesting import optimize as nesting_optimize
from app.services.color_scrap import apply_scrap_policy


ENGINE_VERSION = "1.0.0"


def canonical_hash(payload: Dict[str, Any]) -> str:
    j = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(j.encode("utf-8")).hexdigest()


async def _resolve_pricing_mode(
    *,
    tenant_id: str,
    product_key: str,
    profile_system_id: Optional[str],
    line_override_mode: Optional[str] = None,
    can_override: bool = False,
) -> Dict[str, Any]:
    """Ritorna {mode, source, config_id, config}. Solleva ValueError se nessuna disponibile."""
    db = get_db()
    # 1. Line override
    if line_override_mode:
        if not can_override:
            raise PermissionError("Permesso mancante: pricing.mode.override")
        return {"mode": line_override_mode, "source": "quote_line", "config_id": None, "config": None}
    # 2. Product-level
    doc = await db.pricing_mode_configs.find_one({
        "tenant_id": tenant_id, "scope": "product", "product_key": product_key,
        "active": True, "deleted_at": None,
    })
    if doc:
        return {"mode": doc["mode"], "source": "product", "config_id": doc["_id"], "config": doc}
    # 3. Profile system
    if profile_system_id:
        doc = await db.pricing_mode_configs.find_one({
            "tenant_id": tenant_id, "scope": "profile_system", "scope_ref_id": profile_system_id,
            "active": True, "deleted_at": None,
        })
        if doc:
            return {"mode": doc["mode"], "source": "profile_system", "config_id": doc["_id"], "config": doc}
    # 4. Tenant-level
    doc = await db.pricing_mode_configs.find_one({
        "tenant_id": tenant_id, "scope": "tenant", "active": True, "deleted_at": None,
    })
    if doc:
        return {"mode": doc["mode"], "source": "tenant", "config_id": doc["_id"], "config": doc}
    raise ValueError(
        "Nessuna modalità di pricing configurata. Configura almeno una `pricing_mode_configs` "
        "a livello tenant (Admin → Preventivatore → Modalità)."
    )


async def _get_profile_system(tenant_id: str, ps_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db.profile_systems.find_one({"_id": ps_id, "tenant_id": tenant_id, "deleted_at": None})


async def _get_bom_template(tenant_id: str, bom_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db.bom_templates.find_one({
        "_id": bom_id, "tenant_id": tenant_id, "deleted_at": None,
        "bom_status": {"$in": ["active", "scheduled"]},
    })


async def _get_matrix(tenant_id: str, matrix_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db.price_matrices.find_one({
        "_id": matrix_id, "tenant_id": tenant_id, "deleted_at": None,
        "pm_status": {"$in": ["active", "scheduled"]},
    })


async def _get_color_category(tenant_id: str, cc_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not cc_id:
        return None
    db = get_db()
    return await db.color_categories.find_one({"_id": cc_id, "tenant_id": tenant_id, "deleted_at": None})


async def _build_lookups(tenant_id: str, sell_pricelist_id: Optional[str], cost_pricelist_id: Optional[str]):
    db = get_db()
    sell_entries: List[Dict[str, Any]] = []
    cost_entries: List[Dict[str, Any]] = []
    if sell_pricelist_id:
        pl = await db.item_pricelists.find_one({"_id": sell_pricelist_id, "tenant_id": tenant_id, "deleted_at": None})
        if pl:
            sell_entries = pl.get("entries") or []
    if cost_pricelist_id:
        pl = await db.item_pricelists.find_one({"_id": cost_pricelist_id, "tenant_id": tenant_id, "deleted_at": None})
        if pl:
            cost_entries = pl.get("entries") or []

    def _match(entries, ref_type, ref_id, color_id, unit):
        candidates = [e for e in entries
                      if e.get("ref_type") == ref_type and e.get("ref_id") == ref_id]
        if not candidates:
            return 0.0
        # priorità: color match > senza color > tier default
        with_color = [e for e in candidates if e.get("color_id") == color_id]
        if with_color:
            return float(with_color[0].get("unit_price") or 0)
        no_color = [e for e in candidates if not e.get("color_id")]
        if no_color:
            return float(no_color[0].get("unit_price") or 0)
        return float(candidates[0].get("unit_price") or 0)

    return (
        (lambda rt, rid, cid, u: _match(sell_entries, rt, rid, cid, u)) if sell_entries else None,
        (lambda rt, rid, cid, u: _match(cost_entries, rt, rid, cid, u)) if cost_entries else None,
    )


async def compute_parametric_preview(
    *,
    tenant_id: str,
    req: Dict[str, Any],
    can_override_mode: bool = False,
    can_see_costs: bool = False,
) -> Dict[str, Any]:
    """Esegue il calcolo parametrico secondo la modalità risolta.
    `req` deve essere un dict compatibile con ParametricPreviewRequest.
    """
    t0 = time.time()
    warnings: List[str] = []
    errors: List[str] = []

    product_key = req["product_key"]
    width_mm = int(req["width_mm"])
    height_mm = int(req["height_mm"])
    qty = float(req.get("quantity") or 1.0)
    ps_id = req.get("profile_system_id")
    bom_id = req.get("bom_template_id")
    matrix_id = req.get("price_matrix_id")

    # Risolvi modalità
    try:
        resolved = await _resolve_pricing_mode(
            tenant_id=tenant_id, product_key=product_key,
            profile_system_id=ps_id,
            line_override_mode=req.get("mode_override"),
            can_override=can_override_mode,
        )
    except (ValueError, PermissionError) as e:
        return {
            "engine_version": ENGINE_VERSION, "errors": [str(e)],
            "mode_used": "A_table", "mode_source": "n/a",
            "width_mm": width_mm, "height_mm": height_mm,
            "sqm": (width_mm * height_mm) / 1e6, "perimeter_m": 0,
            "unit_price": 0, "subtotal": 0, "vat_amount": 0, "total": 0,
            "unit_cost": 0, "total_cost": 0, "margin_abs": 0, "margin_pct": 0,
            "bom_resolved": [], "price_breakdown": [],
            "warnings": [],
        }
    mode = resolved["mode"]
    mode_source = resolved["source"]
    cfg = resolved.get("config") or {}

    # Deduci id da config se non forniti nella richiesta
    bom_id = bom_id or cfg.get("bom_template_id")
    matrix_id = matrix_id or cfg.get("price_matrix_id")

    # Carica risorse
    ps = await _get_profile_system(tenant_id, ps_id) if ps_id else None
    bom = await _get_bom_template(tenant_id, bom_id) if bom_id else None
    matrix = await _get_matrix(tenant_id, matrix_id) if matrix_id else None
    color_category = await _get_color_category(tenant_id, req.get("color_category_id"))
    if not ps and bom:
        ps = await _get_profile_system(tenant_id, bom.get("profile_system_id"))

    sell_lookup, cost_lookup = await _build_lookups(
        tenant_id, cfg.get("sell_pricelist_id"), cfg.get("cost_pricelist_id"),
    )

    # BOM resolution (necessaria per B, C, e per costo di A se disponibile)
    bom_result = None
    if bom and ps:
        params = {
            "width_mm": width_mm, "height_mm": height_mm,
            "nr_ante": req.get("nr_ante", 1), "nr_traversi": req.get("nr_traversi", 0),
            "nr_montanti": req.get("nr_montanti", 0), "nr_fissi": req.get("nr_fissi", 0),
            "color_category_id": req.get("color_category_id"),
            "color_id": req.get("color_id"),
            "glass_type_id": req.get("glass_type_id") or bom.get("glass_type_default_id"),
            "hardware_kit_id": req.get("hardware_kit_id") or bom.get("hardware_kit_default_id"),
            **(req.get("extra_params") or {}),
        }
        bom_result = resolve_bom(
            bom_template=bom, profile_system=ps, params=params,
            lookup_price=sell_lookup, lookup_cost=cost_lookup,
        )
        warnings.extend(bom_result.get("warnings") or [])

    unit_price = 0.0
    unit_cost = 0.0
    breakdown: List[Dict[str, Any]] = []

    # Applica sovrapprezzo colore (Cat.3 rincaro commerciale)
    color_surcharge_pct = float((color_category or {}).get("surcharge_pct") or 0)
    color_surcharge_fixed = float((color_category or {}).get("surcharge_fixed") or 0)

    if mode == "A_table":
        if not matrix:
            errors.append("Modalità A richiede una matrice prezzi collegata")
        else:
            try:
                mr = matrix_lookup(matrix, width_mm, height_mm)
                unit_price = float(mr["price"])
                warnings.extend(mr.get("warnings") or [])
                breakdown.append({
                    "step": "matrix", "code": "MATRIX",
                    "label": f"Matrice prezzi {matrix.get('name')} · {mr['method']}",
                    "amount": unit_price, "result": unit_price,
                    "explanation": mr.get("explanation"),
                })
            except ValueError as e:
                errors.append(str(e))
        # costo (opzionale) via BOM se presente
        if bom_result:
            unit_cost = float(bom_result.get("materials_cost") or 0)

    elif mode == "B_bom":
        if not bom_result:
            errors.append("Modalità B richiede una BOM collegata")
        else:
            materials_cost = Decimal(str(bom_result.get("materials_cost") or 0))
            materials_price = Decimal(str(bom_result.get("materials_price") or 0))
            unit_cost = float(materials_cost)
            # Applica formula prezzo B configurabile
            b_formula = cfg.get("b_price_formula") or "costo_materiali + costi_indiretti + margine"
            indirect_pct = Decimal(str(cfg.get("b_indirect_pct") or 8))
            markup_pct = Decimal(str(cfg.get("b_markup_pct") or 30))
            # variabili disponibili in formula B: usiamo il parser AST con contesto specifico
            # per non deviare dalla scelta di sicurezza. Poiché formula.py non ammette
            # nomi arbitrari, calcoliamo il prezzo direttamente sui componenti.
            costi_lavorazioni = Decimal("0")  # da estendere con componenti labor
            for c in bom_result["components"]:
                if c.get("component_type") in ("labor", "machine_time", "outsourced_process"):
                    costi_lavorazioni += Decimal(str(c.get("line_cost", 0)))
            costi_indiretti = (materials_cost + costi_lavorazioni) * indirect_pct / Decimal(100)
            margine = (materials_cost + costi_lavorazioni + costi_indiretti) * markup_pct / Decimal(100)
            price = materials_cost + costi_lavorazioni + costi_indiretti + margine
            unit_price = float(money(price))
            breakdown.append({"step": "bom_cost", "label": "Costo materiali (BOM)", "amount": float(money(materials_cost))})
            if costi_lavorazioni > 0:
                breakdown.append({"step": "labor", "label": "Costo lavorazioni", "amount": float(money(costi_lavorazioni))})
            breakdown.append({"step": "indirect", "label": f"Costi indiretti ({indirect_pct}%)", "amount": float(money(costi_indiretti))})
            breakdown.append({"step": "margin", "label": f"Margine ({markup_pct}%)", "amount": float(money(margine))})
            breakdown.append({"step": "unit_price", "label": "Prezzo unitario", "amount": unit_price, "result": unit_price})

    elif mode == "C_hybrid":
        if not matrix:
            errors.append("Modalità C (ibrida) richiede una matrice prezzi per il prezzo di vendita")
        if not bom_result:
            warnings.append("Modalità C senza BOM: costo/margine non calcolabile")
        if matrix:
            try:
                mr = matrix_lookup(matrix, width_mm, height_mm)
                unit_price = float(mr["price"])
                warnings.extend(mr.get("warnings") or [])
                breakdown.append({
                    "step": "matrix", "label": f"Matrice prezzi · {mr['method']}",
                    "amount": unit_price, "result": unit_price,
                    "explanation": mr.get("explanation"),
                })
            except ValueError as e:
                errors.append(str(e))
        if bom_result:
            materials_cost = Decimal(str(bom_result.get("materials_cost") or 0))
            costi_lavorazioni = Decimal("0")
            for c in bom_result["components"]:
                if c.get("component_type") in ("labor", "machine_time", "outsourced_process"):
                    costi_lavorazioni += Decimal(str(c.get("line_cost", 0)))
            indirect_pct = Decimal(str(cfg.get("b_indirect_pct") or 8))
            costi_indiretti = (materials_cost + costi_lavorazioni) * indirect_pct / Decimal(100)
            unit_cost = float(money(materials_cost + costi_lavorazioni + costi_indiretti))
            breakdown.append({"step": "bom_cost", "label": "Costo BOM (mat.+lavor.+ind.)", "amount": unit_cost})

    # Sovrapprezzo colore commerciale
    if color_surcharge_pct > 0 or color_surcharge_fixed > 0:
        prev = unit_price
        unit_price = unit_price * (1 + color_surcharge_pct / 100) + color_surcharge_fixed
        breakdown.append({
            "step": "color_surcharge",
            "label": f"Sovrapprezzo colore ({(color_category or {}).get('name')}) +{color_surcharge_pct}% +€{color_surcharge_fixed}",
            "amount": round(unit_price - prev, 2),
            "result": round(unit_price, 2),
        })

    # Sconti
    disc_pct = float(req.get("discount_pct") or 0)
    disc_abs = float(req.get("discount_amount") or 0)
    subtotal = unit_price * qty
    if disc_pct > 0:
        d = subtotal * disc_pct / 100
        subtotal -= d
        breakdown.append({"step": "discount", "label": f"Sconto {disc_pct}%", "amount": -round(d, 2)})
    if disc_abs > 0:
        subtotal -= disc_abs
        breakdown.append({"step": "discount", "label": f"Sconto € {disc_abs}", "amount": -disc_abs})
    subtotal = max(subtotal, 0)
    vat_rate = float(req.get("vat_rate") or 0.22)
    vat = subtotal * vat_rate
    total = subtotal + vat
    total_cost = unit_cost * qty
    margin_abs = subtotal - total_cost
    margin_pct = (margin_abs / subtotal * 100) if subtotal > 0 else 0.0

    # SVG
    svg = None
    if req.get("include_svg", True):
        svg_raw = draw_window(
            product_key=product_key, width_mm=width_mm, height_mm=height_mm,
            nr_ante=req.get("nr_ante", 1), nr_traversi=req.get("nr_traversi", 0),
            nr_montanti=req.get("nr_montanti", 0),
            show_dimensions=True, show_opening_arrows=(product_key not in ("fixed", "window_fixed")),
        )
        svg = sanitize_svg(svg_raw)

    # Preview taglio (opzionale)
    cutting_preview = None
    if req.get("include_cutting_preview") and bom_result:
        cut_inputs = collect_cutting_inputs(bom_result)
        # Espandi per quantity riga
        for c in cut_inputs:
            c["quantity"] = int(c["quantity"] * max(1, int(qty)))
            c["from_order_id"] = None
        try:
            profile_defaults = {}
            if ps:
                tech = ps.get("tech") or {}
                bar_len = int(tech.get("bar_length_mm") or 6500)
                kerf = float(tech.get("kerf_mm") or 3.0)
                head = float(tech.get("bar_head_offcut_mm") or 50.0)
                tail = float(tech.get("bar_tail_offcut_mm") or 50.0)
                min_reuse = float(tech.get("min_reusable_scrap_mm") or 400.0)
                # Aggiungi default per ogni profile_id presente
                for c in cut_inputs:
                    profile_defaults[(c["profile_id"], c.get("color_category_id"), c.get("color_id"))] = {
                        "bar_length_mm": bar_len, "kerf_mm": kerf,
                        "head_offcut_mm": head, "tail_offcut_mm": tail,
                        "min_reusable_mm": min_reuse,
                    }
            cutting_preview = nesting_optimize(
                cut_inputs, algorithm="auto_best", profile_defaults=profile_defaults,
                default_bar_length_mm=int((ps or {}).get("tech", {}).get("bar_length_mm", 6500)),
                default_kerf_mm=float((ps or {}).get("tech", {}).get("kerf_mm", 3.0)),
                default_head_offcut_mm=float((ps or {}).get("tech", {}).get("bar_head_offcut_mm", 50.0)),
                default_tail_offcut_mm=float((ps or {}).get("tech", {}).get("bar_tail_offcut_mm", 50.0)),
                default_min_reusable_mm=float((ps or {}).get("tech", {}).get("min_reusable_scrap_mm", 400.0)),
            )
        except Exception as e:
            warnings.append(f"Preview taglio non disponibile: {e}")

    input_canonical = {
        "product_key": product_key, "width_mm": width_mm, "height_mm": height_mm,
        "quantity": qty, "profile_system_id": ps_id, "bom_template_id": bom_id,
        "price_matrix_id": matrix_id, "color_category_id": req.get("color_category_id"),
        "color_id": req.get("color_id"), "glass_type_id": req.get("glass_type_id"),
        "hardware_kit_id": req.get("hardware_kit_id"),
        "nr_ante": req.get("nr_ante", 1), "nr_traversi": req.get("nr_traversi", 0),
        "nr_montanti": req.get("nr_montanti", 0), "mode_used": mode,
        "bom_version": (bom or {}).get("version"),
        "matrix_version": (matrix or {}).get("version"),
        "engine_version": ENGINE_VERSION,
    }
    output = {
        "unit_price": round(unit_price, 2), "subtotal": round(subtotal, 2),
        "vat_amount": round(vat, 2), "total": round(total, 2),
        "unit_cost": round(unit_cost, 2), "total_cost": round(total_cost, 2),
        "margin_abs": round(margin_abs, 2),
        "margin_pct": round(margin_pct, 2),
    }

    response = {
        "engine_version": ENGINE_VERSION,
        "mode_used": mode, "mode_source": mode_source,
        "warnings": warnings, "errors": errors,
        "width_mm": width_mm, "height_mm": height_mm,
        "sqm": round((width_mm * height_mm) / 1e6, 4),
        "perimeter_m": round(((width_mm + height_mm) * 2) / 1000.0, 3),
        **output,
        "bom_resolved": (bom_result or {}).get("components") or [],
        "cutting_preview": cutting_preview,
        "price_breakdown": breakdown,
        "svg": svg,
        "input_hash": canonical_hash(input_canonical),
        "output_hash": canonical_hash(output),
        "runtime_ms": int((time.time() - t0) * 1000),
    }
    if not can_see_costs:
        # Occulta costi/margine se l'utente non ha il permesso
        response["unit_cost"] = 0.0
        response["total_cost"] = 0.0
        response["margin_abs"] = 0.0
        response["margin_pct"] = 0.0
    return response
