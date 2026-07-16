"""Quote structure router: Environment → Opening → Products + compatibility + drawing + migration."""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.mongo_utils import to_mongo, from_mongo
from app.models import utcnow, new_id
from app.services.quote_structure import (
    check_compatibility, resolve_dimensions, DEFAULT_RULES,
)
from app.services.composite_drawing import render_opening_composite
from app.models_quote_structure import (
    QuoteEnvironment, OpeningCreatePayload, OpeningProductAddPayload,
    CompatibilityCheckRequest, CompatibilityCheckResponse,
    DimensionResolveRequest, DimensionResolveResponse,
    ProductCompatibilityRule, DimensionFormula,
    ProductRole, OpeningDimensions,
)


router = APIRouter(prefix="/quote-structure", tags=["Quote Structure"])


async def _get_quote(db, tenant_id: str, quote_id: str):
    q = await db.quotes.find_one({"_id": quote_id, "tenant_id": tenant_id, "deleted_at": None})
    if not q: raise HTTPException(404, "Preventivo non trovato")
    return q


# ============================================================
# ENVIRONMENTS
# ============================================================
@router.get("/{quote_id}/environments")
async def list_environments(quote_id: str, user: dict = Depends(require_permission("quotes.view"))):
    db = get_db()
    q = await _get_quote(db, user["tenant_id"], quote_id)
    envs = q.get("environments") or []
    return {"items": envs}


@router.post("/{quote_id}/environments")
async def create_environment(quote_id: str, payload: dict,
                              user: dict = Depends(require_permission("quotes.edit"))):
    db = get_db()
    q = await _get_quote(db, user["tenant_id"], quote_id)
    env = QuoteEnvironment(
        name=payload.get("name", "Ambiente"),
        kind=payload.get("kind", "other"),
        floor=payload.get("floor"),
        notes=payload.get("notes"),
        sort_order=len(q.get("environments") or []),
    )
    envs = list(q.get("environments") or []) + [env.model_dump()]
    await db.quotes.update_one({"_id": quote_id},
        {"$set": {"environments": envs, "updated_at": utcnow().isoformat()},
         "$inc": {"version": 1}})
    return env.model_dump()


@router.patch("/{quote_id}/environments/{env_id}")
async def update_environment(quote_id: str, env_id: str, payload: dict,
                              user: dict = Depends(require_permission("quotes.edit"))):
    db = get_db()
    q = await _get_quote(db, user["tenant_id"], quote_id)
    envs = list(q.get("environments") or [])
    for e in envs:
        if e.get("id") == env_id:
            e.update({k: v for k, v in payload.items() if k in {"name", "kind", "floor", "notes", "sort_order"}})
            break
    await db.quotes.update_one({"_id": quote_id}, {"$set": {"environments": envs}})
    return {"ok": True}


@router.delete("/{quote_id}/environments/{env_id}")
async def delete_environment(quote_id: str, env_id: str,
                              user: dict = Depends(require_permission("quotes.edit"))):
    db = get_db()
    q = await _get_quote(db, user["tenant_id"], quote_id)
    # Verifica non ci siano openings associati
    openings = q.get("openings") or []
    with_env = [o for o in openings if o.get("environment_id") == env_id]
    if with_env:
        raise HTTPException(400, f"Non puoi eliminare l'ambiente: contiene {len(with_env)} vani. Spostali o eliminali prima.")
    envs = [e for e in (q.get("environments") or []) if e.get("id") != env_id]
    await db.quotes.update_one({"_id": quote_id}, {"$set": {"environments": envs}})
    return {"ok": True}


# ============================================================
# OPENINGS (VANI)
# ============================================================
@router.post("/openings")
async def create_opening(payload: OpeningCreatePayload,
                          user: dict = Depends(require_permission("quotes.edit"))):
    """Crea un vano; se environment_name specificato crea anche l'ambiente."""
    db = get_db()
    q = await _get_quote(db, user["tenant_id"], payload.quote_id)
    envs = list(q.get("environments") or [])
    env_id = payload.environment_id
    if not env_id and payload.environment_name:
        env = QuoteEnvironment(name=payload.environment_name, kind=payload.environment_kind,  # type: ignore
                                 sort_order=len(envs))
        envs.append(env.model_dump())
        env_id = env.id
    # opening auto-number
    openings = list(q.get("openings") or [])
    same_env = [o for o in openings if o.get("environment_id") == env_id]
    opening_number = payload.opening_number or (len(same_env) + 1)
    env_name = next((e["name"] for e in envs if e.get("id") == env_id), "")
    display = payload.display_name or f"{env_name} — Vano {opening_number}"
    new_opening = {
        "id": new_id(),
        "environment_id": env_id,
        "opening_number": opening_number,
        "code": f"V{opening_number:02d}",
        "display_name": display,
        "room": env_name,
        "width_mm": payload.dimensions.width_mm,
        "height_mm": payload.dimensions.height_mm,
        "depth_mm": payload.dimensions.depth_mm,
        "sill_height_mm": payload.dimensions.sill_height_mm,
        "hole_type": payload.dimensions.hole_type,
        "shape": payload.dimensions.shape,
        "installation_type": payload.dimensions.installation_position,
        "notes": payload.notes,
        "photos": [],
        "quantity": 1,
        "opening_status": "draft",
        "order_index": len(openings),
    }
    openings.append(new_opening)
    await db.quotes.update_one({"_id": payload.quote_id},
        {"$set": {"environments": envs, "openings": openings,
                   "updated_at": utcnow().isoformat()},
         "$inc": {"version": 1}})
    return new_opening


@router.patch("/openings/{opening_id}")
async def update_opening(opening_id: str, payload: dict,
                          user: dict = Depends(require_permission("quotes.edit"))):
    db = get_db()
    q = await db.quotes.find_one({"tenant_id": user["tenant_id"], "openings.id": opening_id, "deleted_at": None})
    if not q: raise HTTPException(404, "Vano non trovato")
    openings = list(q.get("openings") or [])
    for o in openings:
        if o["id"] == opening_id:
            for k in ["display_name", "environment_id", "width_mm", "height_mm", "depth_mm",
                       "sill_height_mm", "hole_type", "shape", "installation_type", "notes", "opening_number"]:
                if k in payload: o[k] = payload[k]
    await db.quotes.update_one({"_id": q["_id"]}, {"$set": {"openings": openings}})
    return {"ok": True}


@router.post("/openings/{opening_id}/duplicate")
async def duplicate_opening(opening_id: str,
                             user: dict = Depends(require_permission("quotes.edit"))):
    db = get_db()
    q = await db.quotes.find_one({"tenant_id": user["tenant_id"], "openings.id": opening_id, "deleted_at": None})
    if not q: raise HTTPException(404, "Vano non trovato")
    openings = list(q.get("openings") or [])
    lines = list(q.get("lines") or [])
    src = next((o for o in openings if o["id"] == opening_id), None)
    if not src: raise HTTPException(404)
    new_op = dict(src); new_op["id"] = new_id()
    same_env = [o for o in openings if o.get("environment_id") == new_op.get("environment_id")]
    new_op["opening_number"] = len(same_env) + 1
    new_op["code"] = f"V{new_op['opening_number']:02d}"
    new_op["display_name"] = f"{src.get('display_name', 'Vano')} (copia)"
    openings.append(new_op)
    # duplica lines
    for l in [l for l in lines if l.get("opening_id") == opening_id]:
        new_line = dict(l); new_line["id"] = new_id(); new_line["opening_id"] = new_op["id"]
        lines.append(new_line)
    await db.quotes.update_one({"_id": q["_id"]}, {"$set": {"openings": openings, "lines": lines}})
    return new_op


# ============================================================
# PRODOTTI NEL VANO
# ============================================================
@router.post("/openings/{opening_id}/products")
async def add_product_to_opening(opening_id: str, payload: OpeningProductAddPayload,
                                  user: dict = Depends(require_permission("quotes.edit"))):
    """Aggiunge un prodotto (con ruolo) allo stesso opening_id."""
    db = get_db()
    q = await db.quotes.find_one({"tenant_id": user["tenant_id"], "openings.id": opening_id, "deleted_at": None})
    if not q: raise HTTPException(404, "Vano non trovato")

    # Check compatibility con prodotti già presenti
    lines = list(q.get("lines") or [])
    existing = [l for l in lines if l.get("opening_id") == opening_id]
    check = await check_compatibility(user["tenant_id"], CompatibilityCheckRequest(
        opening_id=opening_id,
        products_in_opening=[{"role": l.get("role"), "product_type_code": l.get("product_key")} for l in existing],
        candidate_role=payload.role, candidate_product_type=payload.product_type_code,
    ))
    if not check.allow:
        raise HTTPException(400, {"code": "incompatible", "blockers": check.blockers,
                                     "warnings": check.warnings})

    # Risolvi dimensioni
    opening = next(o for o in q["openings"] if o["id"] == opening_id)
    if payload.dimension_source == "inherited" and not (payload.dimensions.get("width_mm")):
        dim_req = DimensionResolveRequest(
            opening_dimensions=OpeningDimensions(
                width_mm=opening.get("width_mm"), height_mm=opening.get("height_mm"),
                depth_mm=opening.get("depth_mm"), sill_height_mm=opening.get("sill_height_mm"),
            ),
            role=payload.role, product_type_code=payload.product_type_code,
        )
        resolved = await resolve_dimensions(user["tenant_id"], dim_req)
        w = resolved.width_mm; h = resolved.height_mm; d = resolved.depth_mm
        source = resolved.source; formula_id = resolved.formula_id
    else:
        w = payload.dimensions.get("width_mm") or opening.get("width_mm")
        h = payload.dimensions.get("height_mm") or opening.get("height_mm")
        d = payload.dimensions.get("depth_mm")
        source = payload.dimension_source; formula_id = payload.dimension_formula_id

    new_line = {
        "id": new_id(),
        "opening_id": opening_id,
        "role": payload.role,
        "category": payload.category or payload.role,
        "product_key": payload.product_type_code,
        "product_config": payload.configuration or {},
        "description": payload.description or "",
        "width_mm": w, "height_mm": h,
        "quantity": payload.quantity,
        "base_price": payload.unit_price or 0.0,
        "unit_price_final": payload.unit_price or 0.0,
        "subtotal_line": (payload.unit_price or 0.0) * payload.quantity,
        "dimension_source": source,
        "dimension_formula_id": formula_id,
        "override_reason": payload.override_reason,
        "vat_rate": 0.22,
        "order_index": len(existing),
    }
    lines.append(new_line)
    await db.quotes.update_one({"_id": q["_id"]}, {"$set": {"lines": lines}})
    return {"line": new_line, "compatibility_warnings": check.warnings}


@router.get("/openings/{opening_id}/products")
async def list_opening_products(opening_id: str,
                                 user: dict = Depends(require_permission("quotes.view"))):
    db = get_db()
    q = await db.quotes.find_one({"tenant_id": user["tenant_id"], "openings.id": opening_id, "deleted_at": None})
    if not q: raise HTTPException(404)
    lines = [l for l in (q.get("lines") or []) if l.get("opening_id") == opening_id]
    subtotal = sum(float(l.get("subtotal_line") or 0) for l in lines)
    return {"items": lines, "opening_subtotal": round(subtotal, 2)}


# ============================================================
# COMPATIBILITY & DIMENSIONS
# ============================================================
@router.post("/compatibility/check", response_model=CompatibilityCheckResponse)
async def compat_check(payload: CompatibilityCheckRequest,
                        user: dict = Depends(require_permission("quotes.view"))):
    return await check_compatibility(user["tenant_id"], payload)


@router.get("/compatibility/rules")
async def list_compat_rules(user: dict = Depends(require_permission("pricelists.view"))):
    db = get_db()
    docs = await db.product_compatibility_rules.find(
        {"tenant_id": user["tenant_id"], "deleted_at": None}
    ).sort([("priority", -1)]).to_list(200)
    if not docs:
        return {"items": DEFAULT_RULES, "is_defaults": True}
    return {"items": [from_mongo(d) for d in docs], "is_defaults": False}


@router.post("/compatibility/rules")
async def create_compat_rule(payload: dict,
                              user: dict = Depends(require_permission("pricelists.manage"))):
    db = get_db()
    inst = ProductCompatibilityRule(tenant_id=user["tenant_id"], **payload)
    await db.product_compatibility_rules.insert_one(to_mongo(inst.model_dump(by_alias=True)))
    return inst.model_dump()


@router.post("/dimensions/resolve", response_model=DimensionResolveResponse)
async def dims_resolve(payload: DimensionResolveRequest,
                        user: dict = Depends(require_permission("quotes.view"))):
    return await resolve_dimensions(user["tenant_id"], payload)


@router.get("/dimensions/formulas")
async def list_formulas(user: dict = Depends(require_permission("pricelists.view"))):
    db = get_db()
    docs = await db.dimension_formulas.find(
        {"tenant_id": user["tenant_id"], "deleted_at": None}
    ).sort([("role", 1)]).to_list(200)
    return {"items": [from_mongo(d) for d in docs]}


@router.post("/dimensions/formulas")
async def create_formula(payload: dict,
                          user: dict = Depends(require_permission("pricelists.manage"))):
    db = get_db()
    inst = DimensionFormula(tenant_id=user["tenant_id"], **payload)
    await db.dimension_formulas.insert_one(to_mongo(inst.model_dump(by_alias=True)))
    return inst.model_dump()


# ============================================================
# COMPOSITE DRAWING
# ============================================================
@router.post("/openings/{opening_id}/composite-drawing")
async def composite_drawing(opening_id: str,
                             user: dict = Depends(require_permission("quotes.view"))):
    db = get_db()
    q = await db.quotes.find_one({"tenant_id": user["tenant_id"], "openings.id": opening_id, "deleted_at": None})
    if not q: raise HTTPException(404)
    opening = next(o for o in q["openings"] if o["id"] == opening_id)
    products = [l for l in (q.get("lines") or []) if l.get("opening_id") == opening_id]
    svg, h = render_opening_composite(opening, products)
    return {"svg": svg, "hash": h, "products_count": len(products)}


# ============================================================
# TREE VIEW (full structure)
# ============================================================
@router.get("/{quote_id}/tree")
async def quote_tree(quote_id: str, user: dict = Depends(require_permission("quotes.view"))):
    db = get_db()
    q = await _get_quote(db, user["tenant_id"], quote_id)
    envs = q.get("environments") or []
    openings = q.get("openings") or []
    lines = q.get("lines") or []
    # Se ci sono openings senza environment_id → migration needed
    orphan_openings = [o for o in openings if not o.get("environment_id")]
    tree = []
    for env in sorted(envs, key=lambda e: e.get("sort_order", 0)):
        env_openings = [o for o in openings if o.get("environment_id") == env["id"]]
        env_openings.sort(key=lambda x: x.get("opening_number") or 0)
        env_total = 0.0
        opening_nodes = []
        for op in env_openings:
            op_lines = [l for l in lines if l.get("opening_id") == op["id"]]
            op_total = sum(float(l.get("subtotal_line") or 0) for l in op_lines)
            env_total += op_total
            opening_nodes.append({
                "opening": op, "products": op_lines, "subtotal": round(op_total, 2),
                "products_by_role": _group_by_role(op_lines),
            })
        tree.append({"environment": env, "openings": opening_nodes, "subtotal": round(env_total, 2)})
    return {
        "quote_id": quote_id,
        "environments": tree,
        "orphan_openings": orphan_openings,
        "migration_required": len(orphan_openings) > 0 and len(envs) > 0,
    }


def _group_by_role(lines: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for l in lines:
        r = l.get("role") or "primary_frame"
        out.setdefault(r, []).append(l)
    return out


# ============================================================
# MIGRATION legacy → environments+openings
# ============================================================
@router.post("/{quote_id}/migrate-structure")
async def migrate_quote(quote_id: str,
                         user: dict = Depends(require_permission("quotes.edit"))):
    """Migra un preventivo legacy: crea Environment 'Non specificato' e
    collega tutti gli openings esistenti, senza modificare prezzi.

    Se un opening non ha `environment_id`, gli viene assegnato.
    """
    db = get_db()
    q = await _get_quote(db, user["tenant_id"], quote_id)
    envs = list(q.get("environments") or [])
    openings = list(q.get("openings") or [])
    lines = list(q.get("lines") or [])

    if q.get("status") in ("sent", "accepted", "signed", "converted"):
        # snapshot immutabile — non modificare
        return {"ok": False, "reason": "quote_locked",
                "message": "Preventivo già inviato/firmato: nessuna modifica automatica per preservare snapshot."}

    migrated_openings = 0
    review_flags: List[str] = []
    orphan_openings = [o for o in openings if not o.get("environment_id")]

    if orphan_openings:
        # Group by "room" field se presente, altrimenti "Non specificato"
        rooms: Dict[str, str] = {}
        for o in orphan_openings:
            key = (o.get("room") or o.get("floor") or "Non specificato").strip()
            if key not in rooms:
                new_env = QuoteEnvironment(name=key, kind="other", sort_order=len(envs))
                envs.append(new_env.model_dump())
                rooms[key] = new_env.id
            o["environment_id"] = rooms[key]
            migrated_openings += 1
        # Openings senza opening_number: assegna sequenziale per env
        per_env: Dict[str, int] = {}
        for o in openings:
            eid = o.get("environment_id")
            per_env.setdefault(eid, 0)
            per_env[eid] += 1
            if not o.get("opening_number"):
                o["opening_number"] = per_env[eid]
                o["code"] = f"V{per_env[eid]:02d}"
    # Product roles: line without role → default primary_frame
    updated_lines = 0
    for l in lines:
        if not l.get("role"):
            cat = (l.get("category") or "").lower()
            if cat in ("roller", "shutter"):
                l["role"] = "shading"
            elif cat in ("screen",):
                l["role"] = "insect_screen"
            elif cat == "box":
                l["role"] = "box"
            elif cat in ("installation", "montaggio"):
                l["role"] = "installation"
            elif cat in ("disposal", "smaltimento"):
                l["role"] = "disposal"
            elif cat in ("accessory", "sill", "trim"):
                l["role"] = "accessory"
            else:
                l["role"] = "primary_frame"
            updated_lines += 1
        if not l.get("opening_id"):
            review_flags.append(f"line {l.get('id')} senza opening_id — richiede revisione manuale")

    await db.quotes.update_one({"_id": quote_id},
        {"$set": {"environments": envs, "openings": openings, "lines": lines,
                   "structure_migrated_at": utcnow().isoformat(),
                   "updated_at": utcnow().isoformat()},
         "$inc": {"version": 1}})
    return {
        "ok": True,
        "environments_created": len([e for e in envs if e.get("id") in rooms.values()]) if orphan_openings else 0,
        "openings_migrated": migrated_openings,
        "lines_role_assigned": updated_lines,
        "review_flags": review_flags,
        "migration_review_required": len(review_flags) > 0,
    }
