"""Router — Multi-Category Configurator.

Endpoint:
  * ``GET  /api/multi-cat/products``           -> catalogo filtrato per il nuovo flusso.
  * ``POST /api/multi-cat/products/{pid}/configure`` -> resolver di pricing (fail-closed).

RBAC:
  * ``COMMERCIAL`` (permesso ``products.view``): NON riceve production_cost /
    internal_reference_price / component internal costs. Response filtrata.
  * ``ADMIN`` con permesso ``quotes.view_costs`` (o equivalente) riceve dettagli
    tecnici e costi interni.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_db
from app.deps import require_permission, get_permission_keys_for_user
from app.models_multi_category import ConfigureRequest, ConfigureResponse
from app.mongo_utils import from_mongo
from app.services.multi_category_pricing import resolve_and_compute


router = APIRouter(prefix="/multi-cat", tags=["multi-category-catalog"])


# ---------------------------------------------------------------------------
# Product listing (data-driven, filtrabile per categoria)
# ---------------------------------------------------------------------------
@router.get("/products")
async def list_products_for_new_quote(
    category_id: Optional[str] = Query(None),
    category_code: Optional[str] = Query(None),
    include_legacy: bool = Query(False, description="ADMIN only. Se true include prodotti legacy/non-classificati."),
    include_test_fixtures: bool = Query(False, description="ADMIN only. Se true include prodotti marcati is_test_fixture."),
    user: dict = Depends(require_permission("products.view")),
):
    """Ritorna solo i prodotti abilitati al nuovo flusso, filtrati per categoria.

    Default: ``new_quote_enabled=True`` + ``legacy!=True`` + ``pricing_model`` presente
    + ``is_test_fixture!=True`` (esclude fixture di collaudo).
    """
    db = get_db()
    perms = await get_permission_keys_for_user(user)
    is_admin = "*" in perms or "products.manage" in perms or "quotes.view_costs" in perms or "quotes.view_margins" in perms

    q: dict = {"tenant_id": user["tenant_id"], "deleted_at": None, "active": True}
    if category_id:
        q["category_id"] = category_id
    if category_code:
        q["category_code"] = category_code.upper()
    if not (include_legacy and is_admin):
        q["new_quote_enabled"] = True
        q["legacy"] = {"$ne": True}
        q["pricing_model"] = {"$ne": None}
    if not (include_test_fixtures and is_admin):
        q["is_test_fixture"] = {"$ne": True}

    docs = await db.products.find(q).sort([("order_index", 1), ("name", 1)]).to_list(500)
    items = [from_mongo(d) for d in docs]

    # Redaction per non-admin: nasconde campi economici interni
    if not is_admin:
        for it in items:
            _redact_product_for_commercial(it)
    return {"items": items, "is_admin_view": is_admin}


def _redact_product_for_commercial(it: dict) -> dict:
    """Rimuove costi interni/purchase/multiplier dal prodotto (RBAC commerciale)."""
    cfg = it.get("pricing_config") or {}
    if isinstance(cfg, dict):
        for k in ("internal_reference_price", "production_cost_seed", "internal_cost", "cost_config",
                  "purchase_cost_table_per_m2", "commercial_multiplier",
                  "orientable_surcharge_per_m2",
                  "pricing_formula_metadata"):
            cfg.pop(k, None)
        # GRID: rimuove i costi interni dalla griglia (redige cella {internal,sale} -> {sale})
        grid = cfg.get("grid")
        if isinstance(grid, dict):
            redacted_grid = {}
            for family, subgrids in grid.items():
                redacted_grid[family] = {}
                for depth_ceil, cells in (subgrids or {}).items():
                    redacted_grid[family][depth_ceil] = {}
                    for dim_key, cell in (cells or {}).items():
                        if isinstance(cell, dict):
                            redacted_grid[family][depth_ceil][dim_key] = {"sale": cell.get("sale")}
            cfg["grid"] = redacted_grid
    it.pop("technical_recipe_id", None)
    return it


@router.get("/products/{pid}")
async def get_product_for_new_quote(pid: str, user: dict = Depends(require_permission("products.view"))):
    db = get_db()
    d = await db.products.find_one({"_id": pid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not d:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    perms = await get_permission_keys_for_user(user)
    is_admin = "*" in perms or "products.manage" in perms or "quotes.view_costs" in perms or "quotes.view_margins" in perms
    out = from_mongo(d)
    if not is_admin:
        _redact_product_for_commercial(out)
    return out


# ---------------------------------------------------------------------------
# Configure — resolver (fail-closed)
# ---------------------------------------------------------------------------
@router.post("/products/{pid}/configure", response_model=ConfigureResponse)
async def configure_product(
    pid: str,
    body: ConfigureRequest,
    user: dict = Depends(require_permission("products.view")),
):
    """Instrada al motore corretto in base al ``pricing_model``.

    Vedi ``app.services.multi_category_pricing.resolve_and_compute`` per la logica.
    """
    db = get_db()
    product = await db.products.find_one({"_id": pid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not product:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    product_dict = from_mongo(product)

    category = None
    if product_dict.get("category_id"):
        cdoc = await db.product_categories.find_one({"_id": product_dict["category_id"], "tenant_id": user["tenant_id"], "deleted_at": None})
        if cdoc:
            category = from_mongo(cdoc)

    result = await resolve_and_compute(product_dict, category, body, tenant_id=user["tenant_id"])

    # Redaction per non-admin: nasconde production_cost/component-costs dai technical_snapshot.
    # NOTA: i field name reali di pricing_v3 sono `total_internal_cost` (= production_cost),
    # `material_cost`, `glass_cost`, `hardware_cost`, `labor_cost`, `foil_surcharge`,
    # `additional_technical_costs`, `hourly_workshop_cost`, `production_time_hours`,
    # `components` (BOM dettagliato).
    perms = await get_permission_keys_for_user(user)
    is_admin = "*" in perms or "products.manage" in perms or "quotes.view_costs" in perms or "quotes.view_margins" in perms
    if not is_admin and result.technical_snapshot:
        ts = dict(result.technical_snapshot)
        for k in (
            "total_internal_cost", "material_cost", "glass_cost", "hardware_cost",
            "labor_cost", "foil_surcharge", "additional_technical_costs",
            "hourly_workshop_cost", "production_time_hours",
            "components", "glass_dimensions",
            # legacy aliases (safety)
            "production_cost", "components_cost", "internal_cost", "frame_cost",
            "sash_cost", "cost_breakdown",
        ):
            ts.pop(k, None)
        result.technical_snapshot = ts
    # Redaction simple_snapshot per non-admin (§5 direttiva RBAC F1):
    # nasconde purchase_cost, internal_production_cost, commercial_multiplier, margin.
    if not is_admin and result.simple_snapshot:
        ss = dict(result.simple_snapshot)
        for k in (
            "purchase_unit_cost_per_m2", "purchase_cost_per_item", "purchase_total_cost",
            "internal_production_cost_per_item", "internal_reference_price",
            "commercial_multiplier", "margin", "contribution_margin",
            # AREA_PURCHASE_MULTIPLIER (persiane) purchase-side fields
            "purchase_rate_per_m2", "effective_purchase_rate", "orientable_surcharge_per_m2",
            # safety legacy
            "internal_cost", "production_cost",
        ):
            ss.pop(k, None)
        result.simple_snapshot = ss
    # Redaction list_products pricing_config per non-admin (già filtrata su list route,
    # ma il configure ritorna anche pricing_config indirettamente in inputs_echo — non
    # contiene però i costi; safety check sul pricing_config del prodotto non applicabile qui)

    return result
