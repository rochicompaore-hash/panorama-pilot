"""M5 — Suppliers + Supplier price lists + Purchase orders + Goods receipts."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models import new_id
from app.models_ops import (
    Supplier, SupplierPriceList, SupplierPriceEntry,
    PurchaseOrder, PurchaseOrderLine, GoodsReceipt, PurchaseNonConformity,
)
from app.mongo_utils import to_mongo, from_mongo
from app.services.ops_common import (
    create_doc, get_doc, list_docs, update_doc, soft_delete_doc,
    enforce_status_transition,
)

# ------------------- Suppliers -------------------
suppliers_router = APIRouter(prefix="/suppliers", tags=["suppliers"])


class SupplierCreate(BaseModel):
    name: str
    vat_number: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    payment_terms: Optional[str] = None
    default_delivery_lead_days: int = 15
    categories: List[str] = []
    is_preferred: bool = False
    notes: Optional[str] = None


@suppliers_router.get("")
async def list_suppliers(q: Optional[str] = None, category: Optional[str] = None,
                          skip: int = 0, limit: int = Query(100, le=500),
                          user: dict = Depends(require_permission("suppliers.view"))):
    filters = {"categories": category} if category else None
    return await list_docs(collection="suppliers", tenant_id=user["tenant_id"],
                            filters=filters, search_fields=["name", "vat_number", "email"], q=q,
                            sort=[("is_preferred", -1), ("name", 1)], skip=skip, limit=limit)


@suppliers_router.get("/{sid}")
async def get_supplier(sid: str, user: dict = Depends(require_permission("suppliers.view"))):
    return await get_doc(collection="suppliers", doc_id=sid, tenant_id=user["tenant_id"])


@suppliers_router.post("")
async def create_supplier(body: SupplierCreate, request: Request,
                           user: dict = Depends(require_permission("suppliers.create"))):
    s = Supplier(id=new_id(), **body.model_dump())
    return await create_doc(collection="suppliers", model_instance=s, user=user,
                             entity_type="supplier", ip=get_client_ip(request))


@suppliers_router.patch("/{sid}")
async def patch_supplier(sid: str, body: dict, request: Request,
                          user: dict = Depends(require_permission("suppliers.edit"))):
    allowed = ["name", "vat_number", "email", "phone", "address", "city", "payment_terms",
               "default_delivery_lead_days", "categories", "is_preferred", "notes",
               "quality_rating"]
    return await update_doc(collection="suppliers", doc_id=sid, updates=body, user=user,
                             entity_type="supplier", ip=get_client_ip(request), allowed_fields=allowed)


@suppliers_router.delete("/{sid}")
async def delete_supplier(sid: str, request: Request,
                           user: dict = Depends(require_permission("suppliers.delete"))):
    return await soft_delete_doc(collection="suppliers", doc_id=sid, user=user,
                                   entity_type="supplier", ip=get_client_ip(request))


# ------------------- Supplier price lists -------------------
splist_router = APIRouter(prefix="/supplier-price-lists", tags=["supplier-price-lists"])


class SupplierPriceListCreate(BaseModel):
    supplier_id: str
    name: str
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    entries: List[SupplierPriceEntry] = []
    is_active: bool = True


@splist_router.get("")
async def list_price_lists(supplier_id: Optional[str] = None, skip: int = 0, limit: int = 50,
                            user: dict = Depends(require_permission("suppliers.view"))):
    return await list_docs(collection="supplier_price_lists", tenant_id=user["tenant_id"],
                            filters={"supplier_id": supplier_id},
                            sort=[("valid_from", -1)], skip=skip, limit=limit)


@splist_router.post("")
async def create_price_list(body: SupplierPriceListCreate, request: Request,
                             user: dict = Depends(require_permission("suppliers.edit"))):
    p = SupplierPriceList(id=new_id(), **body.model_dump())
    return await create_doc(collection="supplier_price_lists", model_instance=p, user=user,
                             entity_type="supplier_price_list", ip=get_client_ip(request))


@splist_router.patch("/{pid}")
async def patch_price_list(pid: str, body: dict, request: Request,
                            user: dict = Depends(require_permission("suppliers.edit"))):
    return await update_doc(collection="supplier_price_lists", doc_id=pid, updates=body,
                             user=user, entity_type="supplier_price_list", ip=get_client_ip(request))


# ------------------- Purchase orders -------------------
po_router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])

PO_FLOW = {
    "draft": {"requested", "cancelled"},
    "requested": {"approved", "cancelled"},
    "approved": {"sent", "cancelled"},
    "sent": {"partially_received", "received", "delayed", "disputed", "cancelled"},
    "partially_received": {"received", "delayed", "disputed", "cancelled"},
    "received": {"disputed"},
    "delayed": {"partially_received", "received", "cancelled"},
    "disputed": {"received", "cancelled"},
    "cancelled": set(),
}


class PurchaseOrderCreate(BaseModel):
    supplier_id: str
    lines: List[PurchaseOrderLine] = []
    expected_delivery: Optional[str] = None
    linked_sales_orders: List[str] = []
    notes: Optional[str] = None


def _recalc_po(po: PurchaseOrder):
    st = sum(ln.line_subtotal or (ln.quantity * ln.unit_price) for ln in po.lines)
    po.subtotal = round(st, 2)
    po.vat_amount = round(st * 0.22, 2)  # default 22% aggregate
    po.total = round(po.subtotal + po.vat_amount, 2)


@po_router.get("")
async def list_pos(q: Optional[str] = None, supplier_id: Optional[str] = None,
                    po_status: Optional[str] = None, skip: int = 0, limit: int = Query(50, le=200),
                    user: dict = Depends(require_permission("purchase_orders.view"))):
    return await list_docs(collection="purchase_orders", tenant_id=user["tenant_id"],
                            filters={"supplier_id": supplier_id, "po_status": po_status},
                            search_fields=["number"], q=q,
                            sort=[("number_int", -1)], skip=skip, limit=limit)


@po_router.get("/{pid}")
async def get_po(pid: str, user: dict = Depends(require_permission("purchase_orders.view"))):
    return await get_doc(collection="purchase_orders", doc_id=pid, tenant_id=user["tenant_id"])


@po_router.post("")
async def create_po(body: PurchaseOrderCreate, request: Request,
                     user: dict = Depends(require_permission("purchase_orders.create"))):
    db = get_db()
    sup = await db.suppliers.find_one({"_id": body.supplier_id, "tenant_id": user["tenant_id"]})
    if not sup: raise HTTPException(status_code=400, detail="Fornitore non trovato")
    p = PurchaseOrder(id=new_id(), supplier_id=body.supplier_id, supplier_name=sup.get("name"),
                       lines=body.lines, linked_sales_orders=body.linked_sales_orders,
                       expected_delivery=body.expected_delivery, notes=body.notes)
    _recalc_po(p)
    return await create_doc(collection="purchase_orders", model_instance=p, user=user,
                             entity_type="purchase_order", ip=get_client_ip(request),
                             set_number=True, number_key="purchase_order", number_prefix="OFR-")


class POPatch(BaseModel):
    lines: Optional[List[PurchaseOrderLine]] = None
    expected_delivery: Optional[str] = None
    notes: Optional[str] = None


@po_router.patch("/{pid}")
async def patch_po(pid: str, body: POPatch, request: Request,
                    user: dict = Depends(require_permission("purchase_orders.edit"))):
    db = get_db()
    existing = await db.purchase_orders.find_one({"_id": pid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not existing: raise HTTPException(status_code=404, detail="Ordine fornitore non trovato")
    if existing.get("po_status") in ("received", "cancelled"):
        raise HTTPException(status_code=400, detail="Ordine chiuso: non modificabile")
    updates = body.model_dump(exclude_none=True)
    if body.lines is not None:
        po = PurchaseOrder(**{**existing, "lines": [ln.model_dump() for ln in body.lines]})
        _recalc_po(po)
        updates["lines"] = [ln.model_dump() for ln in body.lines]
        updates.update({"subtotal": po.subtotal, "vat_amount": po.vat_amount, "total": po.total})
    return await update_doc(collection="purchase_orders", doc_id=pid, updates=updates, user=user,
                             entity_type="purchase_order", ip=get_client_ip(request))


class POStatusChange(BaseModel):
    po_status: str


@po_router.post("/{pid}/status")
async def po_change_status(pid: str, body: POStatusChange, request: Request,
                            user: dict = Depends(require_permission("purchase_orders.edit"))):
    db = get_db()
    existing = await db.purchase_orders.find_one({"_id": pid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not existing: raise HTTPException(status_code=404, detail="OF non trovato")
    enforce_status_transition(existing.get("po_status", "draft"), body.po_status, PO_FLOW)
    return await update_doc(collection="purchase_orders", doc_id=pid, updates={"po_status": body.po_status},
                             user=user, entity_type="purchase_order", ip=get_client_ip(request))


# ------------------- Goods receipts -------------------
gr_router = APIRouter(prefix="/goods-receipts", tags=["goods-receipts"])


class GRCreate(BaseModel):
    purchase_order_id: str
    lines: List[dict] = []
    has_non_conformity: bool = False
    notes: Optional[str] = None


@gr_router.get("")
async def list_grs(purchase_order_id: Optional[str] = None, skip: int = 0, limit: int = 50,
                    user: dict = Depends(require_permission("purchase_orders.view"))):
    return await list_docs(collection="goods_receipts", tenant_id=user["tenant_id"],
                            filters={"purchase_order_id": purchase_order_id},
                            sort=[("received_at", -1)], skip=skip, limit=limit)


@gr_router.post("")
async def create_gr(body: GRCreate, request: Request,
                     user: dict = Depends(require_permission("purchase_orders.edit"))):
    db = get_db()
    po = await db.purchase_orders.find_one({"_id": body.purchase_order_id, "tenant_id": user["tenant_id"]})
    if not po: raise HTTPException(status_code=400, detail="OF non trovato")
    gr = GoodsReceipt(id=new_id(), purchase_order_id=body.purchase_order_id,
                       supplier_id=po["supplier_id"], received_by=user["id"],
                       lines=body.lines, has_non_conformity=body.has_non_conformity, notes=body.notes)
    doc = await create_doc(collection="goods_receipts", model_instance=gr, user=user,
                             entity_type="goods_receipt", ip=get_client_ip(request),
                             set_number=True, number_key="goods_receipt", number_prefix="RIC-")
    # Update PO: bump received_qty on each line and status
    for ln in body.lines:
        for po_line in po.get("lines", []):
            if po_line.get("item_code") == ln.get("item_code"):
                po_line["received_qty"] = (po_line.get("received_qty") or 0) + (ln.get("qty_received") or 0)
    fully = all((l.get("received_qty") or 0) >= (l.get("quantity") or 0) for l in po.get("lines", []))
    new_status = "received" if fully else "partially_received"
    await db.purchase_orders.update_one({"_id": po["_id"]},
        {"$set": {"lines": po["lines"], "po_status": new_status,
                  "actual_delivery": datetime.now(timezone.utc).date().isoformat() if fully else None,
                  "updated_at": datetime.now(timezone.utc).isoformat()}})
    return doc


class NCCreate(BaseModel):
    goods_receipt_id: str
    item_code: str
    qty_affected: float
    kind: str
    severity: str = "minor"
    action: Optional[str] = None
    notes: Optional[str] = None


@gr_router.post("/non-conformities")
async def create_nc(body: NCCreate, request: Request,
                     user: dict = Depends(require_permission("purchase_orders.edit"))):
    db = get_db()
    gr = await db.goods_receipts.find_one({"_id": body.goods_receipt_id, "tenant_id": user["tenant_id"]})
    if not gr: raise HTTPException(status_code=400, detail="Ricevimento non trovato")
    nc = PurchaseNonConformity(id=new_id(), goods_receipt_id=body.goods_receipt_id,
                                purchase_order_id=gr["purchase_order_id"], supplier_id=gr["supplier_id"],
                                item_code=body.item_code, qty_affected=body.qty_affected,
                                kind=body.kind, severity=body.severity, action=body.action, notes=body.notes)
    return await create_doc(collection="purchase_non_conformities", model_instance=nc, user=user,
                             entity_type="purchase_non_conformity", ip=get_client_ip(request))
