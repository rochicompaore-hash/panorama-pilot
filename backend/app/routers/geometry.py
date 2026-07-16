"""Geometry Router — endpoint per configuratore geometrico libero.

Endpoint:
  GET  /api/geometry/templates           — libreria template (1-anta, 2-ante, fisso, ...)
  POST /api/geometry/compute             — geometry → BOM → prezzo → SVG → snapshot
  GET  /api/geometry/dimension-rule-sets — lista rule sets versionati
  POST /api/geometry/dimension-rule-sets — crea rule set
  PATCH .../{id}                          — nuova versione del rule set
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field

from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.mongo_utils import from_mongo, to_mongo
from app.models import new_id
from app.models_geometry import (
    GeometryComputeRequest, GeometryTemplate, DimensionRuleSet, DimensionRule,
    GeometryNode,
)
from app.services.audit import record_audit
from app.services.geometry_engine import compute_geometry


router = APIRouter(prefix="/geometry", tags=["geometry"])


# =====================================================================
# Templates predefiniti — libreria geometrie standard
# =====================================================================
BUILTIN_TEMPLATES: List[Dict[str, Any]] = [
    {
        "code": "TPL-1ANTA-BATT", "name": "1 anta battente", "category": "window",
        "description": "Finestra a 1 anta battente",
        "default_tree": {
            "id": "root", "kind": "root", "children": [
                {"id": "m1", "kind": "module", "module_type": "sash_hinged",
                  "module_opening_side": "left", "module_handle_side": "right"}
            ]
        },
    },
    {
        "code": "TPL-2ANTE-BR", "name": "2 ante (una battente-ribalta)", "category": "window",
        "description": "Finestra 2 ante, principale battente-ribalta, secondaria battente",
        "default_tree": {
            "id": "root", "kind": "root", "children": [
                {"id": "s1", "kind": "split", "direction": "vertical", "children": [
                    {"id": "m1", "kind": "cell", "size_unit": "auto", "children": [
                        {"id": "mod1", "kind": "module", "module_type": "sash_tilt_turn",
                          "module_handle_side": "right"}
                    ]},
                    {"id": "m2", "kind": "cell", "size_unit": "auto", "children": [
                        {"id": "mod2", "kind": "module", "module_type": "sash_hinged",
                          "module_handle_side": "left"}
                    ]},
                ]}
            ]
        },
    },
    {
        "code": "TPL-3ANTE-2AP-1FISSO", "name": "3 moduli (2 apribili + 1 fisso)",
        "category": "window",
        "default_tree": {
            "id": "root", "kind": "root", "children": [
                {"id": "s1", "kind": "split", "direction": "vertical", "children": [
                    {"id": "m1", "kind": "module", "module_type": "sash_hinged",
                      "module_handle_side": "right"},
                    {"id": "m2", "kind": "module", "module_type": "fixed"},
                    {"id": "m3", "kind": "module", "module_type": "sash_hinged",
                      "module_handle_side": "left"},
                ]}
            ]
        },
    },
    {
        "code": "TPL-FISSO", "name": "Vetrata fissa", "category": "window",
        "default_tree": {
            "id": "root", "kind": "root", "children": [
                {"id": "m1", "kind": "module", "module_type": "fixed"}
            ]
        },
    },
    {
        "code": "TPL-PORTAFINESTRA-2A", "name": "Portafinestra 2 ante", "category": "door",
        "default_tree": {
            "id": "root", "kind": "root", "children": [
                {"id": "s1", "kind": "split", "direction": "vertical", "children": [
                    {"id": "m1", "kind": "module", "module_type": "sash_tilt_turn",
                      "module_handle_side": "right"},
                    {"id": "m2", "kind": "module", "module_type": "sash_hinged",
                      "module_handle_side": "left"},
                ]}
            ]
        },
    },
    {
        "code": "TPL-CON-SOPRALUCE", "name": "Finestra con sopraluce", "category": "window",
        "default_tree": {
            "id": "root", "kind": "root", "children": [
                {"id": "s1", "kind": "split", "direction": "horizontal", "children": [
                    {"id": "top", "kind": "module", "module_type": "top_light",
                      "size_unit": "pct", "size_value": 30},
                    {"id": "main", "kind": "module", "module_type": "sash_tilt_turn",
                      "size_unit": "auto"},
                ]}
            ]
        },
    },
]


@router.get("/templates")
async def list_templates(user: dict = Depends(require_permission("quotes.view"))):
    return {"items": BUILTIN_TEMPLATES, "count": len(BUILTIN_TEMPLATES)}


# =====================================================================
# Dimension Rule Sets (versioned)
# =====================================================================
class DimensionRuleSetCreate(BaseModel):
    profile_system_id: str
    code: str
    name: str
    description: Optional[str] = None
    rules: List[Dict[str, Any]] = Field(default_factory=list)
    is_default: bool = False


class DimensionRuleSetPatch(BaseModel):
    """Genera una NUOVA versione (parent_version_id = current, version += 1)."""
    name: Optional[str] = None
    description: Optional[str] = None
    rules: Optional[List[Dict[str, Any]]] = None
    rs_status: Optional[str] = None
    is_default: Optional[bool] = None


@router.get("/dimension-rule-sets")
async def list_rule_sets(profile_system_id: Optional[str] = None,
                          user: dict = Depends(require_permission("products.view"))):
    db = get_db()
    q: Dict[str, Any] = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if profile_system_id:
        q["profile_system_id"] = profile_system_id
    docs = await db.dimension_rule_sets.find(q).sort([("version", -1)]).to_list(200)
    return {"items": [from_mongo(d) for d in docs], "total": len(docs)}


@router.post("/dimension-rule-sets")
async def create_rule_set(body: DimensionRuleSetCreate, request: Request,
                            user: dict = Depends(require_permission("products.manage"))):
    db = get_db()
    ps = await db.profile_systems.find_one({
        "_id": body.profile_system_id, "tenant_id": user["tenant_id"], "deleted_at": None,
    })
    if not ps:
        raise HTTPException(404, "Sistema profilo non trovato")
    # se is_default: rimuovi flag da altri
    if body.is_default:
        await db.dimension_rule_sets.update_many({
            "tenant_id": user["tenant_id"], "profile_system_id": body.profile_system_id,
            "is_default": True,
        }, {"$set": {"is_default": False}})
    doc = DimensionRuleSet(
        tenant_id=user["tenant_id"],
        profile_system_id=body.profile_system_id,
        code=body.code, name=body.name, description=body.description,
        rules=[DimensionRule(**r) for r in body.rules],
        version=1, rs_status="active", is_default=body.is_default,
        created_by=user["id"],
    )
    await db.dimension_rule_sets.insert_one(to_mongo(doc.model_dump(by_alias=True)))
    await record_audit(action="dimension_rule_set.create", tenant_id=user["tenant_id"],
                        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
                        entity_type="dimension_rule_set", entity_id=doc.id,
                        after=doc.model_dump())
    return from_mongo(doc.model_dump(by_alias=True))


@router.patch("/dimension-rule-sets/{rs_id}")
async def patch_rule_set(rs_id: str, body: DimensionRuleSetPatch, request: Request,
                          user: dict = Depends(require_permission("products.manage"))):
    """Modifica NON-versionante di campi non-critici (name/description/is_default/status).
    Per cambiare le rules usare POST /dimension-rule-sets/{id}/new-version.
    """
    db = get_db()
    doc = await db.dimension_rule_sets.find_one({
        "_id": rs_id, "tenant_id": user["tenant_id"], "deleted_at": None,
    })
    if not doc:
        raise HTTPException(404, "Rule set non trovato")
    if body.rules is not None:
        raise HTTPException(400, "Per modificare le regole usa /new-version (versioning obbligatorio)")
    patch: Dict[str, Any] = {}
    for f in ("name", "description", "rs_status", "is_default"):
        v = getattr(body, f)
        if v is not None:
            patch[f] = v
    if patch.get("is_default"):
        await db.dimension_rule_sets.update_many({
            "tenant_id": user["tenant_id"],
            "profile_system_id": doc["profile_system_id"],
            "is_default": True, "_id": {"$ne": rs_id},
        }, {"$set": {"is_default": False}})
    patch["updated_at"] = datetime.now(timezone.utc)
    patch["updated_by"] = user["id"]
    await db.dimension_rule_sets.update_one({"_id": rs_id}, {"$set": patch})
    await record_audit(action="dimension_rule_set.update", tenant_id=user["tenant_id"],
                        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
                        entity_type="dimension_rule_set", entity_id=rs_id, after=patch)
    updated = await db.dimension_rule_sets.find_one({"_id": rs_id})
    return from_mongo(updated)


@router.post("/dimension-rule-sets/{rs_id}/new-version")
async def new_version(rs_id: str, body: DimensionRuleSetPatch, request: Request,
                        user: dict = Depends(require_permission("products.manage"))):
    """Crea nuova versione del rule set: preserva `rs_id` come `parent_version_id`."""
    db = get_db()
    parent = await db.dimension_rule_sets.find_one({
        "_id": rs_id, "tenant_id": user["tenant_id"], "deleted_at": None,
    })
    if not parent:
        raise HTTPException(404, "Rule set non trovato")
    new_doc = DimensionRuleSet(
        tenant_id=user["tenant_id"],
        profile_system_id=parent["profile_system_id"],
        code=parent["code"],
        name=body.name or parent.get("name"),
        description=body.description or parent.get("description"),
        rules=[DimensionRule(**r) for r in (body.rules or parent.get("rules") or [])],
        version=int(parent.get("version", 1)) + 1,
        parent_version_id=rs_id,
        rs_status="active",
        is_default=parent.get("is_default", False),
        created_by=user["id"],
    )
    # Archivia il parent
    await db.dimension_rule_sets.update_one({"_id": rs_id}, {
        "$set": {"rs_status": "archived", "valid_to": datetime.now(timezone.utc),
                  "is_default": False}
    })
    await db.dimension_rule_sets.insert_one(to_mongo(new_doc.model_dump(by_alias=True)))
    await record_audit(action="dimension_rule_set.new_version", tenant_id=user["tenant_id"],
                        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
                        entity_type="dimension_rule_set", entity_id=new_doc.id,
                        before={"parent_id": rs_id, "parent_version": parent.get("version")},
                        after={"new_version": new_doc.version})
    return from_mongo(new_doc.model_dump(by_alias=True))


# =====================================================================
# Compute geometry — endpoint core
# =====================================================================
@router.post("/compute")
async def compute(body: GeometryComputeRequest,
                    user: dict = Depends(require_permission("quotes.view"))):
    can_see_costs = (user.get("is_superadmin") or user.get("is_platform_owner")
                     or "pricelists.manage" in (user.get("_perms") or [])
                     or "quotes.view_costs" in (user.get("_perms") or []))
    include_costs = body.include_costs and can_see_costs
    result = await compute_geometry(
        tenant_id=user["tenant_id"],
        geometry=body.geometry.model_dump(),
        bom_template_id=body.bom_template_id,
        sell_pricelist_id=body.sell_pricelist_id,
        cost_pricelist_id=body.cost_pricelist_id,
        include_costs=include_costs,
        include_svg=body.include_svg,
    )
    # Enforce: NO valori demo se manca listino → errore bloccante commerciale
    if body.sell_pricelist_id:
        missing = [c for c in (result.get("components") or [])
                    if (c.get("unit_price") or 0) == 0 and c.get("ref_id")]
        if missing:
            result.setdefault("blocking_errors", []).append({
                "code": "MISSING_PUBLISHED_PRICE",
                "message": f"Calcolo non completabile: manca il prezzo pubblicato di {len(missing)} componenti",
                "severity": "blocking",
                "missing_codes": [c.get("code") for c in missing[:20] if c.get("code")],
            })
            result["errors"] = result.get("errors") or []
            result["errors"].append(
                f"[MISSING_PUBLISHED_PRICE] Prezzo pubblicato mancante per {len(missing)} componenti"
            )
    if not include_costs:
        for c in result.get("components") or []:
            c["unit_cost"] = None
            c["line_cost"] = None
        result["materials_cost"] = None
        result["cost_redacted"] = True
    return result
