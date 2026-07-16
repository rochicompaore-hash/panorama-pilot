"""Router parametrico — profile_systems, profiles, colors, categories, glass, hardware,
accessories, bom_templates, price_matrices, pricing_mode_configs, item_pricelists,
cutting_lists, scrap_stock, preview, nesting, svg.

Segue le convenzioni dei router M4..M17 (ops_common) con tenant isolation obbligatoria.
"""
from __future__ import annotations
from typing import Optional, List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from app.db import get_db
from app.deps import get_current_user, require_permission, require_any_permission, get_client_ip
from app.services.ops_common import create_doc, get_doc, list_docs, update_doc, soft_delete_doc
from app.services.audit import record_audit
from app.mongo_utils import to_mongo, from_mongo
from app.models import new_id
from app.models_parametric import (
    ProfileSystem, ProfileSystemCreate, ProfileSystemUpdate,
    Profile, ProfileCreate, ProfileUpdate,
    ColorCategory, ColorCategoryCreate, ColorCategoryUpdate,
    Color, ColorCreate, ColorUpdate,
    GlassType, GlassTypeCreate, GlassTypeUpdate,
    HardwareKit, HardwareKitCreate, HardwareKitUpdate,
    Accessory, AccessoryCreate, AccessoryUpdate,
    ItemPricelist, ItemPricelistCreate, ItemPricelistUpdate,
    PriceMatrix, PriceMatrixCreate, PriceMatrixUpdate,
    BomTemplate, BomTemplateCreate, BomTemplateUpdate,
    PricingModeConfig, PricingModeConfigCreate, PricingModeConfigUpdate,
    PricingModeOverrideRequest,
    ParametricPreviewRequest, ParametricPreviewResponse,
    NestingRequest, SvgDrawingRequest,
    ScrapStock, CuttingList, CuttingListCreate,
    BarOptimizationRun, ParametricSnapshot,
)
from app.services.pricing_modes import compute_parametric_preview
from app.services.nesting import optimize as nesting_optimize, compare_algorithms as nesting_compare
from app.services.svg_drawing import draw_window, sanitize_svg
from app.services.parametric_engine import resolve_bom
from app.services.formula import validate_formula, eval_formula, FormulaError
from app.services.color_scrap import apply_scrap_policy


router = APIRouter(prefix="/parametric", tags=["Parametric Engine"])


# ---------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------
def _has_perm(user: dict, perm: str) -> bool:
    if user.get("is_superadmin") or user.get("is_platform_owner"):
        return True
    return perm in (user.get("_perms") or [])


# ---------------------------------------------------------------------
# PROFILE SYSTEMS
# ---------------------------------------------------------------------
@router.get("/profile-systems")
async def list_profile_systems(
    q: Optional[str] = None, skip: int = 0, limit: int = 100,
    active_only: bool = True,
    user: dict = Depends(require_permission("products.view")),
):
    filters = {}
    if active_only:
        filters["active"] = True
    return await list_docs(
        collection="profile_systems", tenant_id=user["tenant_id"],
        filters=filters, search_fields=["code", "name", "series"], q=q,
        sort=[("code", 1)], skip=skip, limit=limit,
    )


@router.post("/profile-systems")
async def create_profile_system(
    payload: ProfileSystemCreate, request: Request,
    user: dict = Depends(require_permission("products.manage")),
):
    instance = ProfileSystem(**payload.model_dump())
    return await create_doc(
        collection="profile_systems", model_instance=instance, user=user,
        entity_type="profile_system", ip=get_client_ip(request),
    )


@router.get("/profile-systems/{item_id}")
async def get_profile_system(item_id: str, user: dict = Depends(require_permission("products.view"))):
    return await get_doc(collection="profile_systems", doc_id=item_id, tenant_id=user["tenant_id"])


@router.patch("/profile-systems/{item_id}")
async def update_profile_system(
    item_id: str, payload: ProfileSystemUpdate, request: Request,
    user: dict = Depends(require_permission("products.manage")),
):
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    return await update_doc(
        collection="profile_systems", doc_id=item_id, updates=updates,
        user=user, entity_type="profile_system", ip=get_client_ip(request),
    )


@router.delete("/profile-systems/{item_id}")
async def delete_profile_system(item_id: str, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await soft_delete_doc(collection="profile_systems", doc_id=item_id, user=user,
                                  entity_type="profile_system", ip=get_client_ip(request))


# ---------------------------------------------------------------------
# PROFILES
# ---------------------------------------------------------------------
@router.get("/profiles")
async def list_profiles(
    q: Optional[str] = None, system_id: Optional[str] = None, role: Optional[str] = None,
    skip: int = 0, limit: int = 200, active_only: bool = True,
    user: dict = Depends(require_permission("products.view")),
):
    filters = {}
    if system_id: filters["system_id"] = system_id
    if role: filters["role"] = role
    if active_only: filters["active"] = True
    return await list_docs(collection="profiles", tenant_id=user["tenant_id"], filters=filters,
                            search_fields=["code", "name", "supplier_code"], q=q,
                            sort=[("role", 1), ("code", 1)], skip=skip, limit=limit)


@router.post("/profiles")
async def create_profile(payload: ProfileCreate, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await create_doc(collection="profiles", model_instance=Profile(**payload.model_dump()),
                             user=user, entity_type="profile", ip=get_client_ip(request))


@router.get("/profiles/{item_id}")
async def get_profile(item_id: str, user: dict = Depends(require_permission("products.view"))):
    return await get_doc(collection="profiles", doc_id=item_id, tenant_id=user["tenant_id"])


@router.patch("/profiles/{item_id}")
async def update_profile(item_id: str, payload: ProfileUpdate, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await update_doc(collection="profiles", doc_id=item_id,
                             updates=payload.model_dump(exclude_unset=True), user=user,
                             entity_type="profile", ip=get_client_ip(request))


@router.delete("/profiles/{item_id}")
async def delete_profile(item_id: str, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await soft_delete_doc(collection="profiles", doc_id=item_id, user=user,
                                  entity_type="profile", ip=get_client_ip(request))


# ---------------------------------------------------------------------
# COLOR CATEGORIES + COLORS
# ---------------------------------------------------------------------
@router.get("/color-categories")
async def list_color_categories(q: Optional[str] = None, user: dict = Depends(require_permission("products.view"))):
    return await list_docs(collection="color_categories", tenant_id=user["tenant_id"],
                            search_fields=["code", "name"], q=q, sort=[("code", 1)], limit=200)


@router.post("/color-categories")
async def create_color_category(payload: ColorCategoryCreate, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await create_doc(collection="color_categories", model_instance=ColorCategory(**payload.model_dump()),
                             user=user, entity_type="color_category", ip=get_client_ip(request))


@router.patch("/color-categories/{item_id}")
async def update_color_category(item_id: str, payload: ColorCategoryUpdate, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await update_doc(collection="color_categories", doc_id=item_id,
                             updates=payload.model_dump(exclude_unset=True), user=user,
                             entity_type="color_category", ip=get_client_ip(request))


@router.delete("/color-categories/{item_id}")
async def delete_color_category(item_id: str, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await soft_delete_doc(collection="color_categories", doc_id=item_id, user=user,
                                  entity_type="color_category", ip=get_client_ip(request))


@router.get("/colors")
async def list_colors(q: Optional[str] = None, category_id: Optional[str] = None,
                       user: dict = Depends(require_permission("products.view"))):
    filters = {}
    if category_id: filters["category_id"] = category_id
    return await list_docs(collection="colors", tenant_id=user["tenant_id"], filters=filters,
                            search_fields=["code", "name", "ral_code"], q=q, sort=[("code", 1)], limit=500)


@router.post("/colors")
async def create_color(payload: ColorCreate, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await create_doc(collection="colors", model_instance=Color(**payload.model_dump()),
                             user=user, entity_type="color", ip=get_client_ip(request))


@router.patch("/colors/{item_id}")
async def update_color(item_id: str, payload: ColorUpdate, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await update_doc(collection="colors", doc_id=item_id,
                             updates=payload.model_dump(exclude_unset=True), user=user,
                             entity_type="color", ip=get_client_ip(request))


@router.delete("/colors/{item_id}")
async def delete_color(item_id: str, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await soft_delete_doc(collection="colors", doc_id=item_id, user=user,
                                  entity_type="color", ip=get_client_ip(request))


# ---------------------------------------------------------------------
# GLASS / HARDWARE / ACCESSORY
# ---------------------------------------------------------------------
@router.get("/glass-types")
async def list_glass(q: Optional[str] = None, user: dict = Depends(require_permission("products.view"))):
    return await list_docs(collection="glass_types", tenant_id=user["tenant_id"],
                            search_fields=["code", "name", "composition"], q=q, limit=500, sort=[("code", 1)])


@router.post("/glass-types")
async def create_glass(payload: GlassTypeCreate, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await create_doc(collection="glass_types", model_instance=GlassType(**payload.model_dump()),
                             user=user, entity_type="glass_type", ip=get_client_ip(request))


@router.patch("/glass-types/{item_id}")
async def update_glass(item_id: str, payload: GlassTypeUpdate, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await update_doc(collection="glass_types", doc_id=item_id,
                             updates=payload.model_dump(exclude_unset=True), user=user,
                             entity_type="glass_type", ip=get_client_ip(request))


@router.delete("/glass-types/{item_id}")
async def delete_glass(item_id: str, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await soft_delete_doc(collection="glass_types", doc_id=item_id, user=user,
                                  entity_type="glass_type", ip=get_client_ip(request))


@router.get("/hardware-kits")
async def list_hardware(q: Optional[str] = None, user: dict = Depends(require_permission("products.view"))):
    return await list_docs(collection="hardware_kits", tenant_id=user["tenant_id"],
                            search_fields=["code", "name", "supplier"], q=q, limit=500, sort=[("code", 1)])


@router.post("/hardware-kits")
async def create_hardware(payload: HardwareKitCreate, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await create_doc(collection="hardware_kits", model_instance=HardwareKit(**payload.model_dump()),
                             user=user, entity_type="hardware_kit", ip=get_client_ip(request))


@router.patch("/hardware-kits/{item_id}")
async def update_hardware(item_id: str, payload: HardwareKitUpdate, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await update_doc(collection="hardware_kits", doc_id=item_id,
                             updates=payload.model_dump(exclude_unset=True), user=user,
                             entity_type="hardware_kit", ip=get_client_ip(request))


@router.delete("/hardware-kits/{item_id}")
async def delete_hardware(item_id: str, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await soft_delete_doc(collection="hardware_kits", doc_id=item_id, user=user,
                                  entity_type="hardware_kit", ip=get_client_ip(request))


@router.get("/accessories")
async def list_accessories(q: Optional[str] = None, kind: Optional[str] = None,
                            user: dict = Depends(require_permission("products.view"))):
    filters = {}
    if kind: filters["kind"] = kind
    return await list_docs(collection="accessories", tenant_id=user["tenant_id"], filters=filters,
                            search_fields=["code", "name"], q=q, limit=500, sort=[("code", 1)])


@router.post("/accessories")
async def create_accessory(payload: AccessoryCreate, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await create_doc(collection="accessories", model_instance=Accessory(**payload.model_dump()),
                             user=user, entity_type="accessory", ip=get_client_ip(request))


@router.patch("/accessories/{item_id}")
async def update_accessory(item_id: str, payload: AccessoryUpdate, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await update_doc(collection="accessories", doc_id=item_id,
                             updates=payload.model_dump(exclude_unset=True), user=user,
                             entity_type="accessory", ip=get_client_ip(request))


@router.delete("/accessories/{item_id}")
async def delete_accessory(item_id: str, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await soft_delete_doc(collection="accessories", doc_id=item_id, user=user,
                                  entity_type="accessory", ip=get_client_ip(request))


# ---------------------------------------------------------------------
# ITEM PRICELISTS (listini vendita/costo)
# ---------------------------------------------------------------------
@router.get("/item-pricelists")
async def list_item_pricelists(kind: Optional[str] = None, q: Optional[str] = None,
                                user: dict = Depends(require_permission("pricelists.view"))):
    filters = {}
    if kind: filters["kind"] = kind
    return await list_docs(collection="item_pricelists", tenant_id=user["tenant_id"], filters=filters,
                            search_fields=["code", "name"], q=q, sort=[("code", 1)], limit=200)


@router.post("/item-pricelists")
async def create_item_pricelist(payload: ItemPricelistCreate, request: Request,
                                 user: dict = Depends(require_permission("pricelists.manage"))):
    return await create_doc(collection="item_pricelists", model_instance=ItemPricelist(**payload.model_dump()),
                             user=user, entity_type="item_pricelist", ip=get_client_ip(request))


@router.get("/item-pricelists/{item_id}")
async def get_item_pricelist(item_id: str, user: dict = Depends(require_permission("pricelists.view"))):
    return await get_doc(collection="item_pricelists", doc_id=item_id, tenant_id=user["tenant_id"])


@router.patch("/item-pricelists/{item_id}")
async def update_item_pricelist(item_id: str, payload: ItemPricelistUpdate, request: Request,
                                 user: dict = Depends(require_permission("pricelists.manage"))):
    return await update_doc(collection="item_pricelists", doc_id=item_id,
                             updates=payload.model_dump(exclude_unset=True), user=user,
                             entity_type="item_pricelist", ip=get_client_ip(request))


@router.delete("/item-pricelists/{item_id}")
async def delete_item_pricelist(item_id: str, request: Request, user: dict = Depends(require_permission("pricelists.manage"))):
    return await soft_delete_doc(collection="item_pricelists", doc_id=item_id, user=user,
                                  entity_type="item_pricelist", ip=get_client_ip(request))


# ---------------------------------------------------------------------
# PRICE MATRICES
# ---------------------------------------------------------------------
@router.get("/price-matrices")
async def list_price_matrices(q: Optional[str] = None, product_key: Optional[str] = None,
                               user: dict = Depends(require_permission("pricelists.view"))):
    filters = {}
    if product_key: filters["product_key"] = product_key
    return await list_docs(collection="price_matrices", tenant_id=user["tenant_id"], filters=filters,
                            search_fields=["code", "name", "product_key"], q=q, sort=[("code", 1)], limit=200)


@router.post("/price-matrices")
async def create_price_matrix(payload: PriceMatrixCreate, request: Request,
                               user: dict = Depends(require_permission("pricelists.manage"))):
    return await create_doc(collection="price_matrices", model_instance=PriceMatrix(**payload.model_dump()),
                             user=user, entity_type="price_matrix", ip=get_client_ip(request))


@router.get("/price-matrices/{item_id}")
async def get_price_matrix(item_id: str, user: dict = Depends(require_permission("pricelists.view"))):
    return await get_doc(collection="price_matrices", doc_id=item_id, tenant_id=user["tenant_id"])


@router.patch("/price-matrices/{item_id}")
async def update_price_matrix(item_id: str, payload: PriceMatrixUpdate, request: Request,
                               user: dict = Depends(require_permission("pricelists.manage"))):
    return await update_doc(collection="price_matrices", doc_id=item_id,
                             updates=payload.model_dump(exclude_unset=True), user=user,
                             entity_type="price_matrix", ip=get_client_ip(request))


@router.delete("/price-matrices/{item_id}")
async def delete_price_matrix(item_id: str, request: Request, user: dict = Depends(require_permission("pricelists.manage"))):
    return await soft_delete_doc(collection="price_matrices", doc_id=item_id, user=user,
                                  entity_type="price_matrix", ip=get_client_ip(request))


# ---------------------------------------------------------------------
# BOM TEMPLATES
# ---------------------------------------------------------------------
@router.get("/bom-templates")
async def list_bom_templates(q: Optional[str] = None, product_key: Optional[str] = None,
                              profile_system_id: Optional[str] = None,
                              level: Optional[str] = None,
                              user: dict = Depends(require_permission("products.view"))):
    filters = {}
    if product_key: filters["product_key"] = product_key
    if profile_system_id: filters["profile_system_id"] = profile_system_id
    if level: filters["level"] = level
    return await list_docs(collection="bom_templates", tenant_id=user["tenant_id"], filters=filters,
                            search_fields=["code", "name", "product_key"], q=q, sort=[("code", 1)], limit=200)


@router.post("/bom-templates")
async def create_bom_template(payload: BomTemplateCreate, request: Request,
                                user: dict = Depends(require_permission("products.manage"))):
    return await create_doc(collection="bom_templates", model_instance=BomTemplate(**payload.model_dump()),
                             user=user, entity_type="bom_template", ip=get_client_ip(request))


@router.get("/bom-templates/{item_id}")
async def get_bom_template(item_id: str, user: dict = Depends(require_permission("products.view"))):
    return await get_doc(collection="bom_templates", doc_id=item_id, tenant_id=user["tenant_id"])


@router.patch("/bom-templates/{item_id}")
async def update_bom_template(item_id: str, payload: BomTemplateUpdate, request: Request,
                                user: dict = Depends(require_permission("products.manage"))):
    return await update_doc(collection="bom_templates", doc_id=item_id,
                             updates=payload.model_dump(exclude_unset=True), user=user,
                             entity_type="bom_template", ip=get_client_ip(request))


@router.delete("/bom-templates/{item_id}")
async def delete_bom_template(item_id: str, request: Request, user: dict = Depends(require_permission("products.manage"))):
    return await soft_delete_doc(collection="bom_templates", doc_id=item_id, user=user,
                                  entity_type="bom_template", ip=get_client_ip(request))


@router.post("/bom-templates/{item_id}/duplicate-as-new-version")
async def duplicate_bom_new_version(item_id: str, request: Request, user: dict = Depends(require_permission("products.manage"))):
    src = await get_doc(collection="bom_templates", doc_id=item_id, tenant_id=user["tenant_id"])
    new_doc = {**src, "parent_version_id": src["id"], "version": src.get("version", 1) + 1,
               "bom_status": "draft", "id": new_id(), "created_at": None, "updated_at": None}
    new_doc.pop("id", None)
    instance = BomTemplate(**{k: v for k, v in new_doc.items()
                              if k in BomTemplate.model_fields})
    return await create_doc(collection="bom_templates", model_instance=instance, user=user,
                             entity_type="bom_template", ip=get_client_ip(request))


# ---------------------------------------------------------------------
# FORMULA VALIDATION
# ---------------------------------------------------------------------
@router.post("/formula/validate")
async def validate_formula_endpoint(payload: dict, user: dict = Depends(get_current_user)):
    """Valida una formula stringa contro il parser AST. Non richiede permessi speciali."""
    expr = payload.get("formula") or ""
    ok, err = validate_formula(expr)
    return {"ok": ok, "error": err}


@router.post("/formula/test")
async def test_formula_endpoint(payload: dict, user: dict = Depends(get_current_user)):
    """Testa una formula contro un contesto sample.
    Passa `strict=true` nel payload per abilitare DIV_ZERO/INFINITE bloccanti (BOM engine)."""
    expr = payload.get("formula") or ""
    ctx = payload.get("context") or {"L": 1200, "H": 1400, "nr_ante": 2, "kerf": 3}
    strict = bool(payload.get("strict", False))
    try:
        result = eval_formula(expr, ctx, strict=strict)
        return {"ok": True, "result": float(result)}
    except FormulaError as e:
        return {"ok": False, "error": str(e), "code": e.code,
                "severity": e.severity, "meta": e.meta}


# ---------------------------------------------------------------------
# PRICING MODE CONFIG
# ---------------------------------------------------------------------
@router.get("/pricing-modes")
async def list_pricing_mode_configs(scope: Optional[str] = None,
                                     user: dict = Depends(require_any_permission("pricing.mode.view", "pricelists.view"))):
    filters = {}
    if scope: filters["scope"] = scope
    return await list_docs(collection="pricing_mode_configs", tenant_id=user["tenant_id"], filters=filters,
                            search_fields=["scope_ref_id", "product_key"], sort=[("scope", 1)], limit=200)


@router.post("/pricing-modes")
async def create_pricing_mode_config(payload: PricingModeConfigCreate, request: Request,
                                      user: dict = Depends(require_permission("pricing.mode.manage_defaults"))):
    return await create_doc(collection="pricing_mode_configs",
                             model_instance=PricingModeConfig(**payload.model_dump()),
                             user=user, entity_type="pricing_mode_config", ip=get_client_ip(request))


@router.patch("/pricing-modes/{item_id}")
async def update_pricing_mode_config(item_id: str, payload: PricingModeConfigUpdate, request: Request,
                                      user: dict = Depends(require_permission("pricing.mode.manage_defaults"))):
    return await update_doc(collection="pricing_mode_configs", doc_id=item_id,
                             updates=payload.model_dump(exclude_unset=True), user=user,
                             entity_type="pricing_mode_config", ip=get_client_ip(request))


@router.delete("/pricing-modes/{item_id}")
async def delete_pricing_mode_config(item_id: str, request: Request,
                                      user: dict = Depends(require_permission("pricing.mode.manage_defaults"))):
    return await soft_delete_doc(collection="pricing_mode_configs", doc_id=item_id, user=user,
                                  entity_type="pricing_mode_config", ip=get_client_ip(request))


# ---------------------------------------------------------------------
# PARAMETRIC PREVIEW (heart of the engine)
# ---------------------------------------------------------------------
@router.post("/preview")
async def parametric_preview(
    payload: ParametricPreviewRequest, request: Request,
    user: dict = Depends(get_current_user),
):
    """Calcola preview parametrica. Occulta costi/margine se l'utente non ha `quotes.view_costs`.
    L'override modalità richiede `pricing.mode.override`."""
    db = get_db()
    # Calcola permessi rilevanti
    perms = set()
    if not (user.get("is_superadmin") or user.get("is_platform_owner")):
        role_ids = user.get("role_ids") or []
        roles = await db.roles.find({"_id": {"$in": role_ids}, "deleted_at": None}).to_list(100)
        for r in roles:
            for k in (r.get("permission_keys") or []):
                perms.add(k)
    can_override = "*" in perms or "pricing.mode.override" in perms or user.get("is_superadmin") or user.get("is_platform_owner")
    can_see_costs = ("*" in perms or "quotes.view_costs" in perms or "financials.view" in perms
                     or user.get("is_superadmin") or user.get("is_platform_owner"))
    result = await compute_parametric_preview(
        tenant_id=user["tenant_id"],
        req=payload.model_dump(),
        can_override_mode=can_override,
        can_see_costs=can_see_costs,
    )
    # Snapshot solo se non ci sono errori
    if not result.get("errors"):
        snap = ParametricSnapshot(
            tenant_id=user["tenant_id"],
            input_canonical=payload.model_dump(),
            input_hash=result.get("input_hash"),
            output=result,
            output_hash=result.get("output_hash"),
            engine_version=result.get("engine_version"),
            bom_template_id=payload.bom_template_id,
            price_matrix_id=payload.price_matrix_id,
            pricing_mode=result.get("mode_used"),
            warnings=result.get("warnings") or [],
            runtime_ms=result.get("runtime_ms", 0),
        )
        await db.parametric_snapshots.insert_one(to_mongo(snap.model_dump(by_alias=True)))
    # Audit se override
    if payload.mode_override and payload.override_reason:
        await record_audit(
            action="pricing.mode.override", tenant_id=user["tenant_id"], user_id=user["id"],
            user_email=user["email"], ip=get_client_ip(request), entity_type="pricing_mode",
            entity_id=None, meta={"reason": payload.override_reason, "new_mode": payload.mode_override},
        )
    return result


# ---------------------------------------------------------------------
# NESTING (1D)
# ---------------------------------------------------------------------
@router.post("/nesting/run")
async def run_nesting(payload: NestingRequest, request: Request,
                       user: dict = Depends(require_permission("production.edit"))):
    """Esegue nesting su una lista di tagli. Non salva la cutting_list.
    Per salvarla, chiamare /cutting-lists con `source_*` popolati."""
    if not payload.cuts:
        raise HTTPException(status_code=400, detail="Lista tagli vuota")
    # profile_defaults dai profile system
    db = get_db()
    profile_ids = list({c.profile_id for c in payload.cuts})
    profiles = await db.profiles.find({"_id": {"$in": profile_ids}, "tenant_id": user["tenant_id"]}).to_list(500)
    prof_map = {p["_id"]: p for p in profiles}
    system_ids = list({p.get("system_id") for p in profiles if p.get("system_id")})
    systems = await db.profile_systems.find({"_id": {"$in": system_ids}, "tenant_id": user["tenant_id"]}).to_list(50)
    sys_map = {s["_id"]: s for s in systems}
    profile_defaults = {}
    default_bar = 6500
    default_kerf = 3.0
    for pid, p in prof_map.items():
        sys = sys_map.get(p.get("system_id")) or {}
        tech = sys.get("tech") or {}
        bar_len = p.get("bar_length_mm") or tech.get("bar_length_mm", 6500)
        kerf = tech.get("kerf_mm", 3.0)
        head = tech.get("bar_head_offcut_mm", 50.0)
        tail = tech.get("bar_tail_offcut_mm", 50.0)
        min_reuse = tech.get("min_reusable_scrap_mm", 400.0)
        profile_defaults[(pid, None, None)] = {
            "bar_length_mm": bar_len, "kerf_mm": kerf,
            "head_offcut_mm": head, "tail_offcut_mm": tail,
            "min_reusable_mm": min_reuse,
        }
    if systems:
        default_bar = systems[0].get("tech", {}).get("bar_length_mm", 6500)
        default_kerf = systems[0].get("tech", {}).get("kerf_mm", 3.0)
    cuts = [c.model_dump() for c in payload.cuts]
    try:
        result = nesting_optimize(
            cuts, algorithm=payload.algorithm, profile_defaults=profile_defaults,
            default_bar_length_mm=default_bar, default_kerf_mm=default_kerf,
            respect_order_isolation=payload.respect_order_isolation,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Log run
    run = BarOptimizationRun(
        tenant_id=user["tenant_id"], algorithm=payload.algorithm,
        input_data={"cuts_count": len(cuts), "algorithm": payload.algorithm},
        output_summary={
            "total_bars": result["total_bars"],
            "efficiency_pct": result["efficiency_pct"],
            "total_waste_mm": result["total_waste_mm"],
        },
        runtime_ms=result.get("runtime_ms", 0),
        warnings=result.get("warnings") or [],
    )
    db = get_db()
    await db.bar_optimization_runs.insert_one(to_mongo(run.model_dump(by_alias=True)))
    return result


@router.post("/nesting/compare")
async def compare_nesting(payload: NestingRequest, user: dict = Depends(require_permission("production.edit"))):
    """Confronta FFD vs BFD."""
    if not payload.cuts:
        raise HTTPException(status_code=400, detail="Lista tagli vuota")
    cuts = [c.model_dump() for c in payload.cuts]
    return nesting_compare(cuts, algorithm="ffd")


# ---------------------------------------------------------------------
# CUTTING LISTS
# ---------------------------------------------------------------------
@router.get("/cutting-lists")
async def list_cutting_lists(user: dict = Depends(require_permission("production.view")), skip: int = 0, limit: int = 100):
    return await list_docs(collection="cutting_lists", tenant_id=user["tenant_id"],
                            sort=[("created_at", -1)], skip=skip, limit=limit)


@router.get("/cutting-lists/{item_id}")
async def get_cutting_list(item_id: str, user: dict = Depends(require_permission("production.view"))):
    return await get_doc(collection="cutting_lists", doc_id=item_id, tenant_id=user["tenant_id"])


@router.post("/cutting-lists/from-nesting")
async def cutting_list_from_nesting(
    payload: dict, request: Request,
    user: dict = Depends(require_permission("production.edit")),
):
    """Crea una CuttingList persistente a partire da un output di nesting/run.
    payload: {code?, scope, is_executive, algorithm, bars: [...], source_production_order_ids: [...]}"""
    cl = CuttingList(
        tenant_id=user["tenant_id"],
        code=payload.get("code") or f"CL-{new_id()[:8].upper()}",
        scope=payload.get("scope") or "single_order",
        is_executive=bool(payload.get("is_executive")),
        algorithm=payload.get("algorithm") or "auto_best",
        source_production_order_ids=payload.get("source_production_order_ids") or [],
        source_sales_order_ids=payload.get("source_sales_order_ids") or [],
        bars=payload.get("bars") or [],
        total_bars=len(payload.get("bars") or []),
        total_cuts=sum(len(b.get("cuts") or []) for b in (payload.get("bars") or [])),
        total_waste_mm=payload.get("total_waste_mm", 0.0),
        total_reusable_scrap_mm=payload.get("total_reusable_scrap_mm", 0.0),
        efficiency_pct=payload.get("efficiency_pct", 0.0),
        warnings=payload.get("warnings") or [],
    )
    return await create_doc(collection="cutting_lists", model_instance=cl, user=user,
                             entity_type="cutting_list", ip=get_client_ip(request))


# ---------------------------------------------------------------------
# SCRAP STOCK
# ---------------------------------------------------------------------
@router.get("/scrap-stock")
async def list_scrap(profile_id: Optional[str] = None, color_id: Optional[str] = None,
                      scrap_status: Optional[str] = "available",
                      user: dict = Depends(require_permission("items.view"))):
    filters = {}
    if profile_id: filters["profile_id"] = profile_id
    if color_id: filters["color_id"] = color_id
    if scrap_status: filters["scrap_status"] = scrap_status
    return await list_docs(collection="scrap_stock", tenant_id=user["tenant_id"], filters=filters,
                            sort=[("length_mm", -1)], limit=500)


# ---------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------
@router.post("/svg")
async def generate_svg(payload: SvgDrawingRequest, user: dict = Depends(get_current_user)):
    svg_raw = draw_window(
        product_key=payload.product_key,
        width_mm=payload.width_mm, height_mm=payload.height_mm,
        nr_ante=payload.nr_ante, nr_traversi=payload.nr_traversi,
        nr_montanti=payload.nr_montanti,
        show_dimensions=payload.show_dimensions,
        show_opening_arrows=payload.show_opening_arrows,
        scale=payload.scale,
    )
    return {"svg": sanitize_svg(svg_raw)}


# ---------------------------------------------------------------------
# BOM RESOLVE (dry-run senza pricing)
# ---------------------------------------------------------------------
@router.post("/bom/resolve")
async def bom_resolve_endpoint(payload: dict, user: dict = Depends(require_permission("products.view"))):
    """Risolve una BOM per parametri dati. Utile per debug/preview tecnica."""
    tenant_id = user["tenant_id"]
    bom_id = payload.get("bom_template_id")
    if not bom_id:
        raise HTTPException(status_code=400, detail="bom_template_id richiesto")
    db = get_db()
    bom = await db.bom_templates.find_one({"_id": bom_id, "tenant_id": tenant_id, "deleted_at": None})
    if not bom:
        raise HTTPException(status_code=404, detail="BOM template non trovato")
    ps = await db.profile_systems.find_one({"_id": bom.get("profile_system_id"), "tenant_id": tenant_id})
    result = resolve_bom(bom_template=bom, profile_system=ps or {},
                         params=payload.get("params") or {})
    return result


# ---------------------------------------------------------------------
# DEMO / SEED HELPERS
# ---------------------------------------------------------------------
@router.get("/demo/status")
async def demo_status(user: dict = Depends(get_current_user)):
    db = get_db()
    counts = {}
    for col in ["profile_systems", "profiles", "color_categories", "colors", "glass_types",
                "hardware_kits", "accessories", "bom_templates", "price_matrices",
                "pricing_mode_configs", "item_pricelists"]:
        counts[col] = await db[col].count_documents({"tenant_id": user["tenant_id"], "is_demo": True, "deleted_at": None})
    return {"is_demo_present": any(v > 0 for v in counts.values()), "counts": counts}
