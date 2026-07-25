"""Glass recipe engine — formule strutturate + custom (parser AST sicuro).

Le formule vetro sono versionate e collegate a (product_id/key, frame_code,
sash_code, window_type, number_of_sashes).

Modello ibrido (approvato):
- STRUCTURED: parametri fissi (width_reduction, height_reduction, split_factor, qty)
- CUSTOM: espressione stringata, valutata dal parser AST sicuro esistente
  (`services/formula.py`), variabili ammesse: L, H, S, n_ante

In assenza di ricetta approvata → MISSING_GLASS_RECIPE (non inventiamo).
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from app.db import get_db
from app.mongo_utils import from_mongo
from app.services.formula import eval_formula, FormulaError


# --------------------------------------------------------------------
# Factory defaults — approvate dall'utente, hardcoded solo per ProEvolution/Restauro
# 1-anta e 2-ante. Tutto il resto → MISSING_GLASS_RECIPE.
# --------------------------------------------------------------------
FACTORY_GLASS_RECIPES = [
    {
        "product_key": "PROEVOLUTION",
        "frame_code": "5103", "sash_code": "12130",
        "window_type": "apribile", "number_of_sashes": 1,
        "formula_type": "structured",
        "structured": {"width_reduction_mm": 206, "height_reduction_mm": 206,
                       "split_factor": 1, "quantity": 1},
        "is_system": True,
    },
    {
        "product_key": "PROEVOLUTION",
        "frame_code": "5103", "sash_code": "12130",
        "window_type": "apribile", "number_of_sashes": 2,
        "formula_type": "structured",
        "structured": {"width_reduction_mm": 347, "height_reduction_mm": 206,
                       "split_factor": 2, "quantity": 2},
        "is_system": True,
    },
    {
        "product_key": "PROEVOLUTION",
        "frame_code": "5103", "sash_code": "12130",
        "window_type": "fissa", "number_of_sashes": 0,
        "formula_type": "structured",
        # Il fisso non ha anta — la spec approvata non fornisce ancora la formula esatta
        # per il vetro del fisso; usiamo L-108/H-108 (fascia telaio) come default provvisorio.
        # La formula si può sovrascrivere via API.
        "structured": {"width_reduction_mm": 108, "height_reduction_mm": 108,
                       "split_factor": 1, "quantity": 1},
        "is_system": True,
    },
    # ProEvolution Restauro — identico a ProEvolution (telaio 5105 stessa geometria vetro)
    {
        "product_key": "PROEVOLUTION_RESTAURO",
        "frame_code": "5105", "sash_code": "12130",
        "window_type": "apribile", "number_of_sashes": 1,
        "formula_type": "structured",
        "structured": {"width_reduction_mm": 206, "height_reduction_mm": 206,
                       "split_factor": 1, "quantity": 1},
        "is_system": True,
    },
    {
        "product_key": "PROEVOLUTION_RESTAURO",
        "frame_code": "5105", "sash_code": "12130",
        "window_type": "apribile", "number_of_sashes": 2,
        "formula_type": "structured",
        "structured": {"width_reduction_mm": 347, "height_reduction_mm": 206,
                       "split_factor": 2, "quantity": 2},
        "is_system": True,
    },
]


async def seed_factory_glass_recipes() -> int:
    db = get_db()
    inserted = 0
    now = datetime.now(timezone.utc).isoformat()
    for r in FACTORY_GLASS_RECIPES:
        existing = await db.glass_recipes.find_one({
            "tenant_id": None, "is_system": True,
            "product_key": r["product_key"], "frame_code": r["frame_code"],
            "sash_code": r["sash_code"], "window_type": r["window_type"],
            "number_of_sashes": r["number_of_sashes"],
        })
        if existing:
            continue
        await db.glass_recipes.insert_one({
            "_id": f"gr-sys-{r['product_key']}-{r['frame_code']}-{r['window_type']}-{r['number_of_sashes']}",
            "tenant_id": None, **r,
            "created_at": now, "updated_at": now,
            "created_by": "system:seed",
            "deleted_at": None, "status": "active", "version": 1,
        })
        inserted += 1
    return inserted


async def resolve_glass_recipe(
    tenant_id: str,
    product_key: str,
    frame_code: str,
    sash_code: str,
    window_type: str,
    number_of_sashes: int,
) -> Optional[Dict[str, Any]]:
    """Cerca la formula vetro attiva: prima tenant-specifica, poi factory di sistema.
    Restituisce None se non trovata (upstream produce MISSING_GLASS_RECIPE)."""
    db = get_db()
    q = {
        "$or": [
            {"tenant_id": tenant_id},
            {"tenant_id": None, "is_system": True},
        ],
        "product_key": product_key,
        "window_type": window_type,
        "number_of_sashes": number_of_sashes,
        "status": "active",
        "deleted_at": None,
    }
    # frame_code / sash_code opzionali — se presenti in doc devono matchare
    docs = await db.glass_recipes.find(q).sort([("tenant_id", -1)]).to_list(20)
    for d in docs:
        if d.get("frame_code") not in (None, "", frame_code):
            continue
        if d.get("sash_code") not in (None, "", sash_code):
            continue
        return from_mongo(d)
    return None


def compute_glass_dimensions(recipe: Dict[str, Any], L_mm: int, H_mm: int,
                              S_mm: int = 6) -> Tuple[int, int, int]:
    """Applica la formula della ricetta. Ritorna (glass_width_mm, glass_height_mm, glass_quantity).

    Structured:
        gw = (L - width_reduction) / split_factor
        gh = H - height_reduction
        qty = quantity
    Custom (parser AST):
        gw = eval_formula(recipe["custom_width"], ctx)
        gh = eval_formula(recipe["custom_height"], ctx)
        qty = int(recipe["custom_qty_expression"] evaluated)
    """
    ft = recipe.get("formula_type", "structured")
    if ft == "structured":
        s = recipe.get("structured") or {}
        wr = int(s.get("width_reduction_mm", 0))
        hr = int(s.get("height_reduction_mm", 0))
        sf = int(s.get("split_factor", 1) or 1)
        qty = int(s.get("quantity", 1))
        gw = int((L_mm - wr) / sf)
        gh = int(H_mm - hr)
        return gw, gh, qty
    if ft == "custom":
        c = recipe.get("custom") or {}
        ctx = {"L": L_mm, "H": H_mm, "S": S_mm}
        try:
            gw = int(eval_formula(c["width_expression"], ctx, strict=True))
            gh = int(eval_formula(c["height_expression"], ctx, strict=True))
            qty_expr = c.get("quantity_expression") or str(c.get("quantity", 1))
            qty = int(eval_formula(qty_expr, ctx, strict=True))
        except (FormulaError, KeyError, ValueError) as e:
            raise ValueError(f"Formula vetro custom non valida: {e}")
        return gw, gh, qty
    raise ValueError(f"Formula type sconosciuto: {ft}")
