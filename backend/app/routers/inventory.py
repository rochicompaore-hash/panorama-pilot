"""M6 — Inventory: items, stock locations, stock levels, movements, counts."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models import new_id
from app.models_ops import Item, StockLocation, StockLevel, StockMovement, InventoryCount
from app.mongo_utils import to_mongo, from_mongo
from app.services.ops_common import create_doc, get_doc, list_docs, update_doc, soft_delete_doc

# ------------------- Items -------------------
items_router = APIRouter(prefix="/items", tags=["items"])


class ItemCreate(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    unit_of_measure: str = "pz"
    default_supplier_id: Optional[str] = None
    min_stock: float = 0
    reorder_qty: float = 0
    is_bar: bool = False
    bar_length_mm: Optional[float] = None
    profile_color_ext: Optional[str] = None
    profile_color_int: Optional[str] = None
    profile_core: Optional[str] = None
    profile_film: Optional[str] = None
    profile_finish: Optional[str] = None
    barcode: Optional[str] = None


@items_router.get("")
async def list_items(q: Optional[str] = None, category: Optional[str] = None,
                      is_bar: Optional[bool] = None,
                      skip: int = 0, limit: int = Query(100, le=500),
                      user: dict = Depends(require_permission("items.view"))):
    return await list_docs(collection="items", tenant_id=user["tenant_id"],
                            filters={"category": category, "is_bar": is_bar},
                            search_fields=["code", "name", "barcode"], q=q,
                            sort=[("code", 1)], skip=skip, limit=limit)


@items_router.get("/{iid}")
async def get_item(iid: str, user: dict = Depends(require_permission("items.view"))):
    return await get_doc(collection="items", doc_id=iid, tenant_id=user["tenant_id"])


@items_router.post("")
async def create_item(body: ItemCreate, request: Request,
                       user: dict = Depends(require_permission("items.create"))):
    db = get_db()
    if await db.items.find_one({"tenant_id": user["tenant_id"], "code": body.code, "deleted_at": None}):
        raise HTTPException(status_code=400, detail=f"Codice articolo '{body.code}' già esistente")
    i = Item(id=new_id(), **body.model_dump())
    return await create_doc(collection="items", model_instance=i, user=user,
                             entity_type="item", ip=get_client_ip(request))


@items_router.patch("/{iid}")
async def patch_item(iid: str, body: dict, request: Request,
                      user: dict = Depends(require_permission("items.edit"))):
    return await update_doc(collection="items", doc_id=iid, updates=body, user=user,
                             entity_type="item", ip=get_client_ip(request))


@items_router.delete("/{iid}")
async def delete_item(iid: str, request: Request,
                       user: dict = Depends(require_permission("items.delete"))):
    return await soft_delete_doc(collection="items", doc_id=iid, user=user,
                                   entity_type="item", ip=get_client_ip(request))


# ------------------- Stock locations -------------------
loc_router = APIRouter(prefix="/stock-locations", tags=["stock-locations"])


class LocationCreate(BaseModel):
    code: str
    name: str
    kind: str = "warehouse"


@loc_router.get("")
async def list_locations(user: dict = Depends(require_permission("items.view"))):
    return await list_docs(collection="stock_locations", tenant_id=user["tenant_id"],
                            sort=[("code", 1)], limit=200)


@loc_router.post("")
async def create_location(body: LocationCreate, request: Request,
                           user: dict = Depends(require_permission("items.create"))):
    l = StockLocation(id=new_id(), **body.model_dump())
    return await create_doc(collection="stock_locations", model_instance=l, user=user,
                             entity_type="stock_location", ip=get_client_ip(request))


# ------------------- Stock movements + levels -------------------
mv_router = APIRouter(prefix="/stock", tags=["stock"])


class MovementCreate(BaseModel):
    kind: str  # inbound|outbound|transfer|adjust|reserve|unreserve|scrap
    item_id: str
    from_location_id: Optional[str] = None
    to_location_id: Optional[str] = None
    quantity: float
    lot: Optional[str] = None
    ref_type: Optional[str] = None
    ref_id: Optional[str] = None
    notes: Optional[str] = None


async def _apply_movement(db, tenant_id: str, mv: MovementCreate) -> Dict[str, Any]:
    """Adjust stock levels atomically-ish (best effort). Returns updated levels."""
    now = datetime.now(timezone.utc).isoformat()
    item = await db.items.find_one({"_id": mv.item_id, "tenant_id": tenant_id, "deleted_at": None})
    if not item: raise HTTPException(status_code=400, detail="Articolo non trovato")

    def _update_level(location_id, delta_on_hand, delta_committed):
        return db.stock_levels.find_one_and_update(
            {"tenant_id": tenant_id, "item_id": mv.item_id, "location_id": location_id},
            {"$inc": {"qty_on_hand": delta_on_hand, "qty_committed": delta_committed},
             "$set": {"item_code": item.get("code"), "updated_at_movement": now, "tenant_id": tenant_id,
                      "item_id": mv.item_id, "location_id": location_id, "updated_at": now},
             "$setOnInsert": {"_id": new_id(), "created_at": now, "version": 1, "deleted_at": None, "status": "active"}},
            upsert=True, return_document=True,
        )

    q = mv.quantity
    outputs = []
    if mv.kind == "inbound":
        if not mv.to_location_id: raise HTTPException(status_code=400, detail="to_location_id richiesto")
        r = await _update_level(mv.to_location_id, q, 0); outputs.append(r)
    elif mv.kind == "outbound" or mv.kind == "scrap":
        if not mv.from_location_id: raise HTTPException(status_code=400, detail="from_location_id richiesto")
        r = await _update_level(mv.from_location_id, -q, 0); outputs.append(r)
    elif mv.kind == "transfer":
        if not (mv.from_location_id and mv.to_location_id):
            raise HTTPException(status_code=400, detail="from_location_id e to_location_id richiesti")
        outputs.append(await _update_level(mv.from_location_id, -q, 0))
        outputs.append(await _update_level(mv.to_location_id, q, 0))
    elif mv.kind == "adjust":
        # quantity can be +/-
        if not mv.to_location_id: raise HTTPException(status_code=400, detail="to_location_id richiesto")
        outputs.append(await _update_level(mv.to_location_id, q, 0))
    elif mv.kind == "reserve":
        if not mv.from_location_id: raise HTTPException(status_code=400, detail="from_location_id richiesto")
        outputs.append(await _update_level(mv.from_location_id, 0, q))
    elif mv.kind == "unreserve":
        if not mv.from_location_id: raise HTTPException(status_code=400, detail="from_location_id richiesto")
        outputs.append(await _update_level(mv.from_location_id, 0, -q))
    else:
        raise HTTPException(status_code=400, detail=f"Tipo movimento sconosciuto: {mv.kind}")
    # Recompute qty_available
    for r in outputs:
        if r:
            avail = (r.get("qty_on_hand") or 0) - (r.get("qty_committed") or 0)
            await db.stock_levels.update_one({"_id": r["_id"]}, {"$set": {"qty_available": avail}})
    return {"item_code": item.get("code"), "levels_updated": len(outputs)}


@mv_router.post("/movements")
async def post_movement(body: MovementCreate, request: Request,
                         user: dict = Depends(require_permission("items.edit"))):
    db = get_db()
    item = await db.items.find_one({"_id": body.item_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not item: raise HTTPException(status_code=400, detail="Articolo non trovato")
    m = StockMovement(id=new_id(), item_code=item.get("code", ""), **body.model_dump())
    await create_doc(collection="stock_movements", model_instance=m, user=user,
                      entity_type="stock_movement", ip=get_client_ip(request))
    result = await _apply_movement(db, user["tenant_id"], body)
    return {"ok": True, "movement_id": m.id, **result}


@mv_router.get("/movements")
async def list_movements(item_id: Optional[str] = None, kind: Optional[str] = None,
                          skip: int = 0, limit: int = Query(50, le=500),
                          user: dict = Depends(require_permission("items.view"))):
    return await list_docs(collection="stock_movements", tenant_id=user["tenant_id"],
                            filters={"item_id": item_id, "kind": kind},
                            sort=[("created_at", -1)], skip=skip, limit=limit)


@mv_router.get("/levels")
async def list_levels(item_id: Optional[str] = None, location_id: Optional[str] = None,
                       under_min: bool = False,
                       user: dict = Depends(require_permission("items.view"))):
    db = get_db()
    query: Dict[str, Any] = {"tenant_id": user["tenant_id"]}
    if item_id: query["item_id"] = item_id
    if location_id: query["location_id"] = location_id
    docs = await db.stock_levels.find(query).limit(500).to_list(500)
    items = [from_mongo(d) for d in docs]
    if under_min:
        # join with items to get min_stock
        codes = {d.get("item_id") for d in items}
        items_map = {i["_id"]: i for i in await db.items.find(
            {"_id": {"$in": list(codes)}, "tenant_id": user["tenant_id"]}
        ).to_list(500)}
        items = [d for d in items if (d.get("qty_available") or 0) < (items_map.get(d.get("item_id"), {}).get("min_stock") or 0)]
    return {"items": items}


@mv_router.get("/dashboard")
async def stock_dashboard(user: dict = Depends(require_permission("items.view"))):
    db = get_db()
    tenant = user["tenant_id"]
    total_items = await db.items.count_documents({"tenant_id": tenant, "deleted_at": None})
    total_locations = await db.stock_locations.count_documents({"tenant_id": tenant, "deleted_at": None})
    total_committed = 0.0; total_on_hand = 0.0; total_available = 0.0
    async for lvl in db.stock_levels.find({"tenant_id": tenant}):
        total_on_hand += lvl.get("qty_on_hand") or 0
        total_committed += lvl.get("qty_committed") or 0
        total_available += lvl.get("qty_available") or 0
    # Under-min count
    under_min = 0
    async for i in db.items.find({"tenant_id": tenant, "deleted_at": None, "min_stock": {"$gt": 0}}):
        lvl = await db.stock_levels.find_one({"tenant_id": tenant, "item_id": i["_id"]})
        avail = (lvl or {}).get("qty_available") or 0
        if avail < (i.get("min_stock") or 0):
            under_min += 1
    return {
        "total_items": total_items,
        "total_locations": total_locations,
        "total_on_hand": round(total_on_hand, 2),
        "total_committed": round(total_committed, 2),
        "total_available": round(total_available, 2),
        "under_min_count": under_min,
    }


# ------------------- Inventory counts -------------------
inv_router = APIRouter(prefix="/inventory-counts", tags=["inventory-counts"])


class ICCreate(BaseModel):
    location_id: str


@inv_router.post("")
async def start_count(body: ICCreate, request: Request,
                       user: dict = Depends(require_permission("items.edit"))):
    ic = InventoryCount(id=new_id(), location_id=body.location_id, lines=[])
    return await create_doc(collection="inventory_counts", model_instance=ic, user=user,
                             entity_type="inventory_count", ip=get_client_ip(request),
                             set_number=True, number_key="inventory_count", number_prefix="INV-")


class ICLine(BaseModel):
    item_id: str
    counted: float


@inv_router.post("/{cid}/lines")
async def add_line(cid: str, body: ICLine, request: Request,
                    user: dict = Depends(require_permission("items.edit"))):
    db = get_db()
    ic = await db.inventory_counts.find_one({"_id": cid, "tenant_id": user["tenant_id"]})
    if not ic: raise HTTPException(status_code=404, detail="Conta non trovata")
    if ic.get("is_closed"): raise HTTPException(status_code=400, detail="Conta chiusa")
    lvl = await db.stock_levels.find_one({"tenant_id": user["tenant_id"], "item_id": body.item_id, "location_id": ic["location_id"]})
    expected = (lvl or {}).get("qty_on_hand") or 0
    line = {"item_id": body.item_id, "expected": expected, "counted": body.counted, "delta": body.counted - expected}
    await db.inventory_counts.update_one({"_id": cid}, {"$push": {"lines": line}})
    return {"ok": True, **line}


@inv_router.post("/{cid}/close")
async def close_count(cid: str, apply_adjustments: bool = True, request: Request = None,
                       user: dict = Depends(require_permission("items.edit"))):
    db = get_db()
    ic = await db.inventory_counts.find_one({"_id": cid, "tenant_id": user["tenant_id"]})
    if not ic: raise HTTPException(status_code=404, detail="Conta non trovata")
    now = datetime.now(timezone.utc).isoformat()
    if apply_adjustments:
        for ln in ic.get("lines", []):
            delta = ln.get("delta") or 0
            if delta != 0:
                await _apply_movement(db, user["tenant_id"],
                    MovementCreate(kind="adjust", item_id=ln["item_id"],
                                    to_location_id=ic["location_id"], quantity=delta,
                                    ref_type="inventory_count", ref_id=cid,
                                    notes="Rettifica inventario"))
    await db.inventory_counts.update_one({"_id": cid},
        {"$set": {"is_closed": True, "completed_at": now, "updated_at": now, "updated_by": user["id"]}})
    return {"ok": True}
