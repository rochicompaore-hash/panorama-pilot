"""Idempotent seed for the Opzione A (catalog + 1-anta recipe) go-live.

Runs at startup after the base `run_seed`:
- ensures factory-wide code auto-mappings (5103/5105/12130/7379 → categoria)
- seeds ProEvolution + ProEvolution Restauro products (per tenant with an admin)
- seeds `catalog.*` and `pricing_admin.*` permissions on the admin/superadmin roles

Nothing here mutates existing quotes, contracts or signatures.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.db import get_db
from app.services.catalog_service import seed_factory_code_mappings

logger = logging.getLogger("seed_catalog")


CATALOG_PERMISSIONS = [
    "catalog.view", "catalog.manage", "catalog.publish",
    "catalog.import", "catalog.delete",
    "pricing_admin.view", "pricing_admin.manage",
    "pricing_admin.publish", "pricing_admin.view_costs",
]


# --------------------------------------------------------------------
# Products
# --------------------------------------------------------------------
PRO_EVOLUTION_COMPONENTS: List[Dict[str, Any]] = [
    {"category": "telaio",           "code": "5103",  "required": True,
     "color_dependent": True, "price_depends_on_color": True,
     "applies_to": ["finestra_1a", "finestra_2a"], "priority": 10},
    {"category": "anta_standard",    "code": "12130", "required": True,
     "color_dependent": True, "price_depends_on_color": True,
     "applies_to": ["finestra_1a", "finestra_2a"], "priority": 20},
    {"category": "scambio_battuta",  "code": "7379",  "required": False,
     "color_dependent": True, "price_depends_on_color": True,
     "applies_to": ["finestra_2a"], "priority": 30},
    {"category": "fermavetro",       "code": "FV-STD","required": True,
     "color_dependent": True, "price_depends_on_color": True,
     "applies_to": ["finestra_1a", "finestra_2a"], "priority": 40},
    {"category": "rinforzo_telaio",  "code": "RT-STD","required": True,
     "color_dependent": False, "price_depends_on_color": False,
     "applies_to": ["finestra_1a", "finestra_2a"], "priority": 50},
    {"category": "rinforzo_anta",    "code": "RA-STD","required": True,
     "color_dependent": False, "price_depends_on_color": False,
     "applies_to": ["finestra_1a", "finestra_2a"], "priority": 60},
    {"category": "rinforzo_scambio", "code": "RS-STD","required": False,
     "color_dependent": False, "price_depends_on_color": False,
     "applies_to": ["finestra_2a"], "priority": 70},
]

PRO_EVOLUTION_RESTAURO_COMPONENTS: List[Dict[str, Any]] = [
    dict(c, code="5105") if c["category"] == "telaio" else dict(c)
    for c in PRO_EVOLUTION_COMPONENTS
]


PRODUCTS_TO_SEED = [
    {
        "key": "PROEVOLUTION",
        "name": "ProEvolution",
        "category": "window",
        "description": "Sistema Premier-Elegant — telaio 5103 + anta 12130",
        "components": PRO_EVOLUTION_COMPONENTS,
        "lifecycle_status": "active",
        "profile_system": "Premier-Elegant",
        "compatible_type_infissi": ["finestra_1a", "finestra_2a"],
    },
    {
        "key": "PROEVOLUTION_RESTAURO",
        "name": "ProEvolution Restauro",
        "category": "window",
        "description": "Sistema Premier-Elegant Restauro — telaio 5105 + anta 12130",
        "components": PRO_EVOLUTION_RESTAURO_COMPONENTS,
        "lifecycle_status": "active",
        "profile_system": "Premier-Elegant Restauro",
        "compatible_type_infissi": ["finestra_1a", "finestra_2a"],
    },
]


async def _ensure_permissions() -> None:
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    # Add missing permission catalog entries (idempotent)
    from app.permissions import PERMISSION_CATALOG
    keys = {p[0] for p in PERMISSION_CATALOG}
    for key in CATALOG_PERMISSIONS:
        if key not in keys:
            logger.warning("Permission %s not present in PERMISSION_CATALOG", key)
        await db.permissions.update_one(
            {"key": key},
            {"$set": {"key": key, "updated_at": now}, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
    # Grant to superadmin/admin roles (all tenants)
    async for role in db.roles.find({
        "name": {"$in": ["SuperAdmin", "super_admin", "admin", "Admin"]},
    }):
        current = set(role.get("permissions") or [])
        new_perms = current.union(CATALOG_PERMISSIONS)
        if new_perms != current:
            await db.roles.update_one(
                {"_id": role["_id"]},
                {"$set": {"permissions": sorted(new_perms), "updated_at": now}},
            )
            logger.info("Granted catalog perms to role %s (tenant=%s)",
                        role.get("name"), role.get("tenant_id"))


async def _seed_products_for_tenant(tenant_id: str) -> int:
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for p in PRODUCTS_TO_SEED:
        existing = await db.products.find_one({
            "tenant_id": tenant_id, "key": p["key"], "deleted_at": None,
        })
        if existing:
            # Refresh components + lifecycle_status idempotently, but leave the
            # existing name/description if the operator has customised them.
            await db.products.update_one({"_id": existing["_id"]}, {"$set": {
                "components": p["components"],
                "lifecycle_status": p.get("lifecycle_status", "active"),
                "profile_system": p.get("profile_system"),
                "compatible_type_infissi": p.get("compatible_type_infissi", []),
                "updated_at": now, "updated_by": "system:catalog_seed",
            }})
            continue
        from app.models import new_id
        doc = {
            "_id": new_id(), "tenant_id": tenant_id,
            "key": p["key"], "name": p["name"],
            "category": p["category"], "description": p["description"],
            "components": p["components"],
            "lifecycle_status": p.get("lifecycle_status", "draft"),
            "profile_system": p.get("profile_system"),
            "compatible_type_infissi": p.get("compatible_type_infissi", []),
            "base_price": 0.0, "base_type": "sqm",
            "active": True, "order_index": 0,
            "created_at": now, "updated_at": now,
            "created_by": "system:catalog_seed", "updated_by": "system:catalog_seed",
            "deleted_at": None, "version": 1,
        }
        await db.products.insert_one(doc)
        inserted += 1
        logger.info("Seeded product %s for tenant %s", p["key"], tenant_id)
    return inserted


async def run_catalog_seed() -> None:
    """Entrypoint invoked at startup."""
    db = get_db()
    inserted_mappings = await seed_factory_code_mappings()
    if inserted_mappings:
        logger.info("Seeded %d factory code mappings", inserted_mappings)

    await _ensure_permissions()

    # Products for every tenant that has at least one admin/superadmin
    tenant_ids = await db.users.distinct("tenant_id", {"deleted_at": None, "tenant_id": {"$ne": None}})
    for tid in tenant_ids:
        try:
            await _seed_products_for_tenant(tid)
        except Exception as e:  # noqa: BLE001
            logger.exception("Catalog seed failed for tenant %s: %s", tid, e)
