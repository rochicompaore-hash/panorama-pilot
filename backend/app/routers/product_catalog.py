"""Product Types, Compositions, Installation Pricing, Site Conditions router."""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException

from app.db import get_db
from app.deps import require_permission, get_current_user
from app.mongo_utils import to_mongo, from_mongo
from app.models import utcnow, new_id
from app.services.ops_common import create_doc, list_docs, update_doc, soft_delete_doc
from app.services.svg_advanced import render_composition
from app.services.access_rules import evaluate_site_conditions
from app.models_product_types import (
    ProductType, ProductTypeCreate, ProductTypeUpdate,
    WindowComposition, WindowModule,
    InstallationPricingRule, InstallationPricingRuleCreate,
    AccessSurchargeRule, PlatformCostRule, MunicipalAuthCostRule,
    SiteConditionsEvaluateRequest, SiteConditionsEvaluateResponse,
    TechnicalDrawingRequest, TechnicalDrawingSnapshot,
    SiteConditions,
)


router = APIRouter(prefix="/product-catalog", tags=["Product Catalog"])


# ============================================================
# PRODUCT TYPES
# ============================================================
@router.get("/types")
async def list_types(user: dict = Depends(require_permission("products.view"))):
    return await list_docs(collection="product_types", tenant_id=user["tenant_id"],
                            sort=[("sort_order", 1), ("code", 1)], limit=200)


@router.post("/types")
async def create_type(payload: ProductTypeCreate,
                       user: dict = Depends(require_permission("products.manage"))):
    inst = ProductType(**payload.model_dump())
    return await create_doc(collection="product_types", model_instance=inst,
                             user=user, entity_type="product_type", ip="")


@router.patch("/types/{tid}")
async def update_type(tid: str, payload: ProductTypeUpdate,
                       user: dict = Depends(require_permission("products.manage"))):
    return await update_doc(collection="product_types", doc_id=tid,
                             updates=payload.model_dump(exclude_unset=True),
                             user=user, entity_type="product_type", ip="")


# ============================================================
# TECHNICAL DRAWING (SVG)
# ============================================================
@router.post("/drawing")
async def generate_drawing(payload: TechnicalDrawingRequest,
                            user: dict = Depends(require_permission("parametric.svg.generate"))):
    """Genera un SVG dalla composizione (server-side, sanitizzato)."""
    svg, h = render_composition(
        payload.composition,
        frame_color=payload.color_frame or "#0F1720",
        glass_color=payload.color_glass or "#E8F1F7",
        show_dimensions=payload.show_dimensions,
        show_symbols=payload.show_opening_symbols,
        show_legend=payload.show_legend,
        watermark=payload.watermark_text or "" if payload.include_watermark else "",
    )
    return {"svg": svg, "hash": h, "renderer_version": "2.0.0"}


@router.post("/drawing/snapshot")
async def save_drawing_snapshot(payload: dict,
                                 user: dict = Depends(require_permission("parametric.svg.generate"))):
    comp_data = payload.get("composition") or {}
    context = payload.get("context", "quote_pdf")
    svg, h = render_composition(
        WindowComposition(**comp_data),
        watermark="" if context in ("technical_schedule", "abaco_definitive") else
                    "Rappresentazione illustrativa preventiva",
    )
    snap = TechnicalDrawingSnapshot(
        tenant_id=user["tenant_id"],
        quote_id=payload.get("quote_id"),
        quote_line_id=payload.get("quote_line_id"),
        opening_id=payload.get("opening_id"),
        context=context,
        composition=comp_data, svg=svg, svg_hash=h,
        created_by=user["id"], updated_by=user["id"],
    )
    db = get_db()
    await db.technical_drawing_snapshots.insert_one(to_mongo(snap.model_dump(by_alias=True)))
    return snap.model_dump()


# ============================================================
# INSTALLATION PRICING RULES
# ============================================================
@router.get("/installation-rules")
async def list_install_rules(product_type_code: Optional[str] = None,
                              user: dict = Depends(require_permission("pricelists.view"))):
    filters = {}
    if product_type_code: filters["product_type_code"] = product_type_code
    return await list_docs(collection="installation_pricing_rules", tenant_id=user["tenant_id"],
                            filters=filters, sort=[("code", 1)], limit=200)


@router.post("/installation-rules")
async def create_install_rule(payload: InstallationPricingRuleCreate,
                               user: dict = Depends(require_permission("pricelists.manage"))):
    inst = InstallationPricingRule(**payload.model_dump())
    return await create_doc(collection="installation_pricing_rules", model_instance=inst,
                             user=user, entity_type="installation_pricing_rule", ip="")


@router.patch("/installation-rules/{rid}")
async def update_install_rule(rid: str, payload: dict,
                               user: dict = Depends(require_permission("pricelists.manage"))):
    updates = {k: v for k, v in payload.items() if not k.startswith("_")}
    return await update_doc(collection="installation_pricing_rules", doc_id=rid,
                             updates=updates, user=user,
                             entity_type="installation_pricing_rule", ip="")


# ============================================================
# ACCESS SURCHARGE RULES
# ============================================================
@router.get("/access-rules")
async def list_access_rules(user: dict = Depends(require_permission("pricelists.view"))):
    return await list_docs(collection="access_surcharge_rules", tenant_id=user["tenant_id"],
                            sort=[("trigger", 1)], limit=200)


@router.post("/access-rules")
async def create_access_rule(payload: dict,
                              user: dict = Depends(require_permission("pricelists.manage"))):
    inst = AccessSurchargeRule(**payload)
    return await create_doc(collection="access_surcharge_rules", model_instance=inst,
                             user=user, entity_type="access_surcharge_rule", ip="")


@router.patch("/access-rules/{rid}")
async def update_access_rule(rid: str, payload: dict,
                              user: dict = Depends(require_permission("pricelists.manage"))):
    return await update_doc(collection="access_surcharge_rules", doc_id=rid,
                             updates=payload, user=user,
                             entity_type="access_surcharge_rule", ip="")


# ============================================================
# SITE CONDITIONS EVALUATION
# ============================================================
@router.post("/site-conditions/evaluate", response_model=SiteConditionsEvaluateResponse)
async def evaluate_site(payload: SiteConditionsEvaluateRequest,
                         user: dict = Depends(require_permission("quotes.view"))):
    return await evaluate_site_conditions(user["tenant_id"], payload)


# ============================================================
# PLATFORM / AUTHORIZATION COST RULES
# ============================================================
@router.get("/platform-costs")
async def list_platform_costs(user: dict = Depends(require_permission("pricelists.view"))):
    return await list_docs(collection="platform_cost_rules", tenant_id=user["tenant_id"], limit=50)


@router.post("/platform-costs")
async def create_platform_cost(payload: dict,
                                user: dict = Depends(require_permission("pricelists.manage"))):
    inst = PlatformCostRule(**payload)
    return await create_doc(collection="platform_cost_rules", model_instance=inst,
                             user=user, entity_type="platform_cost_rule", ip="")


@router.get("/municipal-auth-costs")
async def list_muni_costs(user: dict = Depends(require_permission("pricelists.view"))):
    return await list_docs(collection="municipal_auth_cost_rules", tenant_id=user["tenant_id"], limit=50)


@router.post("/municipal-auth-costs")
async def create_muni_cost(payload: dict,
                            user: dict = Depends(require_permission("pricelists.manage"))):
    inst = MunicipalAuthCostRule(**payload)
    return await create_doc(collection="municipal_auth_cost_rules", model_instance=inst,
                             user=user, entity_type="municipal_auth_cost_rule", ip="")
