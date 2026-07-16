"""Quote structure service: compatibility engine + dimension inheritance + composite drawing."""
from __future__ import annotations
from typing import Dict, List, Any, Optional, Tuple
from app.db import get_db
from app.mongo_utils import from_mongo
from app.services.formula import eval_formula, FormulaError
from app.models_quote_structure import (
    CompatibilityCheckRequest, CompatibilityCheckResponse,
    DimensionResolveRequest, DimensionResolveResponse,
    OpeningDimensions,
)


# =========================================================
# DEFAULT COMPATIBILITY RULES (fallback if no DB rules)
# =========================================================
DEFAULT_RULES: List[Dict[str, Any]] = [
    # shading types mutually exclusive
    {"principal_role": "shading", "principal_product_type": "roller_shutter",
     "related_role": "shading", "related_product_type": "shutter",
     "relation": "mutually_exclusive", "hard": True,
     "message": "Tapparella e persiana sono normalmente alternative"},
    {"principal_role": "shading", "principal_product_type": "roller_shutter",
     "related_role": "shading", "related_product_type": "obscurant",
     "relation": "mutually_exclusive", "hard": True,
     "message": "Tapparella e scuro sono normalmente alternativi"},
    {"principal_role": "shading", "principal_product_type": "shutter",
     "related_role": "shading", "related_product_type": "obscurant",
     "relation": "mutually_exclusive", "hard": True,
     "message": "Persiana e scuro sono normalmente alternativi"},
    # box requires roller_shutter
    {"principal_role": "box", "related_role": "shading",
     "related_product_type": "roller_shutter",
     "relation": "recommends", "hard": False,
     "message": "Il cassonetto è tipicamente associato alla tapparella"},
    # persiana/scuro do NOT generate cassonetto
    {"principal_role": "shading", "principal_product_type": "shutter",
     "related_role": "box", "relation": "incompatible", "hard": False,
     "message": "Una persiana non richiede automaticamente un cassonetto"},
]


async def _load_rules(tenant_id: str) -> List[Dict[str, Any]]:
    db = get_db()
    docs = await db.product_compatibility_rules.find(
        {"tenant_id": tenant_id, "active": True, "deleted_at": None}
    ).sort([("priority", -1)]).to_list(500)
    if docs:
        return [from_mongo(d) for d in docs]
    return DEFAULT_RULES


def _matches(rule: Dict[str, Any], role: str, ptype: Optional[str], side: str) -> bool:
    """side = 'principal' or 'related'"""
    rule_role = rule.get(f"{side}_role")
    rule_type = rule.get(f"{side}_product_type")
    if rule_role != role:
        return False
    if rule_type and rule_type != ptype:
        return False
    return True


async def check_compatibility(
    tenant_id: str, req: CompatibilityCheckRequest
) -> CompatibilityCheckResponse:
    rules = await _load_rules(tenant_id)
    warnings: List[str] = []
    blockers: List[str] = []
    matched: List[Dict[str, Any]] = []
    existing = req.products_in_opening or []
    cand_role = req.candidate_role
    cand_type = req.candidate_product_type

    for exist in existing:
        e_role = exist.get("role")
        e_type = exist.get("product_type_code") or exist.get("product_type")
        if not e_role: continue
        for rule in rules:
            # check both directions
            m1 = _matches(rule, e_role, e_type, "principal") and _matches(rule, cand_role, cand_type, "related")
            m2 = _matches(rule, cand_role, cand_type, "principal") and _matches(rule, e_role, e_type, "related")
            if not (m1 or m2):
                continue
            rel = rule.get("relation")
            hard = rule.get("hard", True)
            msg = rule.get("message") or f"{cand_role} vs {e_role}: {rel}"
            matched.append({
                "rule_id": rule.get("id"),
                "principal": f"{e_role}/{e_type}",
                "candidate": f"{cand_role}/{cand_type}",
                "relation": rel, "hard": hard, "message": msg,
            })
            if rel in ("incompatible", "mutually_exclusive"):
                (blockers if hard else warnings).append(msg)
            elif rel == "requires":
                # candidate requires related — se non presente warning
                pass
            elif rel == "recommends":
                warnings.append(msg)
            elif rel == "verify":
                warnings.append(msg)
    return CompatibilityCheckResponse(
        allow=len(blockers) == 0,
        warnings=warnings, blockers=blockers, matched_rules=matched,
    )


# =========================================================
# DIMENSION INHERITANCE
# =========================================================

# Regole di fallback (nessuna formula in DB): maggiorazioni tipiche
DEFAULT_FORMULAS: Dict[Tuple[str, Optional[str]], Dict[str, Any]] = {
    ("primary_frame", None): {"code": "frame_default", "width_expr": "width_mm", "height_expr": "height_mm"},
    ("shading", "roller_shutter"): {"code": "roller_default", "width_expr": "width_mm + 60", "height_expr": "height_mm + 40"},
    ("shading", "shutter"): {"code": "shutter_default", "width_expr": "width_mm + 20", "height_expr": "height_mm + 20"},
    ("shading", "obscurant"): {"code": "obscurant_default", "width_expr": "width_mm", "height_expr": "height_mm"},
    ("insect_screen", None): {"code": "screen_default", "width_expr": "width_mm - 10", "height_expr": "height_mm - 5"},
    ("box", None): {"code": "box_default", "width_expr": "width_mm + 40", "height_expr": "220"},
    ("counter_frame", None): {"code": "counter_default", "width_expr": "width_mm + 60", "height_expr": "height_mm + 40"},
}


async def resolve_dimensions(
    tenant_id: str, req: DimensionResolveRequest
) -> DimensionResolveResponse:
    """Calcola misure derivate per un ruolo dato il vano.

    Cerca DimensionFormula in DB (per role+product_type), altrimenti usa DEFAULT_FORMULAS.
    """
    if not req.opening_dimensions.width_mm or not req.opening_dimensions.height_mm:
        return DimensionResolveResponse(
            source="manual", detail="Misure del vano mancanti — inserimento manuale richiesto"
        )
    db = get_db()
    formula_doc = await db.dimension_formulas.find_one({
        "tenant_id": tenant_id, "active": True, "deleted_at": None,
        "role": req.role,
        "$or": [
            {"product_type_code": req.product_type_code},
            {"product_type_code": None},
        ],
    }, sort=[("product_type_code", -1)])  # prima quelli specifici
    if formula_doc:
        formula = from_mongo(formula_doc)
    else:
        formula = DEFAULT_FORMULAS.get(
            (req.role, req.product_type_code),
            DEFAULT_FORMULAS.get((req.role, None), {"code": "identity",
                                                     "width_expr": "width_mm",
                                                     "height_expr": "height_mm"}),
        )
    ctx = {
        "width_mm": req.opening_dimensions.width_mm,
        "height_mm": req.opening_dimensions.height_mm,
        "depth_mm": req.opening_dimensions.depth_mm or 0,
        "sill_height_mm": req.opening_dimensions.sill_height_mm or 0,
    }
    try:
        w = int(eval_formula(formula.get("width_expr", "width_mm"), ctx))
        h = int(eval_formula(formula.get("height_expr", "height_mm"), ctx))
        d = None
        if formula.get("depth_expr"):
            d = int(eval_formula(formula["depth_expr"], ctx))
    except FormulaError as e:
        return DimensionResolveResponse(
            source="manual", detail=f"Errore formula: {e}"
        )
    return DimensionResolveResponse(
        width_mm=w, height_mm=h, depth_mm=d,
        source="formula" if formula_doc else "inherited",
        formula_id=formula.get("id"),
        formula_code=formula.get("code"),
        detail=f"w={formula.get('width_expr')}, h={formula.get('height_expr')}",
    )
