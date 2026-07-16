"""M5 — Sales orders."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models import new_id
from app.models_ops import SalesOrder, SalesOrderLine
from app.mongo_utils import to_mongo, from_mongo
from app.services.timeline import record_activity
from app.services.ops_common import (
    create_doc, get_doc, list_docs, update_doc, soft_delete_doc,
    enforce_status_transition,
)

router = APIRouter(prefix="/sales-orders", tags=["sales-orders"])

ORDER_FLOW = {
    "draft": {"confirmed", "cancelled"},
    "confirmed": {"technically_validated", "cancelled"},
    "technically_validated": {"waiting_materials", "ready_for_production", "cancelled"},
    "waiting_materials": {"ready_for_production", "cancelled"},
    "ready_for_production": {"in_production", "cancelled"},
    "in_production": {"completed", "cancelled"},
    "completed": {"ready_for_installation", "cancelled"},
    "ready_for_installation": {"installed", "cancelled"},
    "installed": {"closed"},
    "closed": set(),
    "cancelled": set(),
}


class SalesOrderCreate(BaseModel):
    customer_id: str
    contract_id: Optional[str] = None
    quote_id: Optional[str] = None
    survey_id: Optional[str] = None
    site_address: Optional[dict] = None
    lines: List[SalesOrderLine] = []
    notes: Optional[str] = None
    priority: int = 3


def _recalc_totals(order: SalesOrder):
    subtotal = sum((ln.line_subtotal or (ln.unit_price * ln.quantity)) for ln in order.lines)
    vat = sum(((ln.line_subtotal or (ln.unit_price * ln.quantity)) * (ln.vat_rate or 0) / 100) for ln in order.lines)
    order.subtotal = round(subtotal, 2)
    order.vat_amount = round(vat, 2)
    order.total = round(subtotal + vat, 2)


@router.get("")
async def list_orders(q: Optional[str] = None, customer_id: Optional[str] = None,
                       order_status: Optional[str] = None, skip: int = 0,
                       limit: int = Query(50, le=200),
                       user: dict = Depends(require_permission("sales_orders.view"))):
    return await list_docs(collection="sales_orders", tenant_id=user["tenant_id"],
                            filters={"customer_id": customer_id, "order_status": order_status},
                            search_fields=["number"], q=q,
                            sort=[("number_int", -1)], skip=skip, limit=limit)


@router.get("/{oid}")
async def get_order(oid: str, user: dict = Depends(require_permission("sales_orders.view"))):
    return await get_doc(collection="sales_orders", doc_id=oid, tenant_id=user["tenant_id"])


@router.post("")
async def create_order(body: SalesOrderCreate, request: Request,
                        user: dict = Depends(require_permission("sales_orders.create"))):
    so = SalesOrder(
        id=new_id(),
        customer_id=body.customer_id, contract_id=body.contract_id, quote_id=body.quote_id,
        survey_id=body.survey_id, site_address=body.site_address, notes=body.notes,
        priority=body.priority, lines=body.lines,
    )
    _recalc_totals(so)
    doc = await create_doc(collection="sales_orders", model_instance=so, user=user,
                            entity_type="sales_order", ip=get_client_ip(request),
                            set_number=True, number_key="sales_order", number_prefix="ORD-")
    await record_activity(tenant_id=user["tenant_id"], type="sales_order_created",
                          subject=f"Ordine cliente {doc.get('number')} creato",
                          customer_id=body.customer_id, quote_id=body.quote_id,
                          user_id=user["id"], user_email=user["email"])
    return doc


class SalesOrderPatch(BaseModel):
    lines: Optional[List[SalesOrderLine]] = None
    priority: Optional[int] = None
    expected_ready_date: Optional[str] = None
    expected_installation_date: Optional[str] = None
    notes: Optional[str] = None
    site_address: Optional[dict] = None


@router.patch("/{oid}")
async def patch_order(oid: str, body: SalesOrderPatch, request: Request,
                      user: dict = Depends(require_permission("sales_orders.edit"))):
    db = get_db()
    existing = await db.sales_orders.find_one({"_id": oid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not existing: raise HTTPException(status_code=404, detail="Ordine non trovato")
    if existing.get("order_status") in ("installed", "closed", "cancelled"):
        raise HTTPException(status_code=400, detail="Ordine chiuso: non modificabile")
    updates = body.model_dump(exclude_none=True)
    if body.lines is not None:
        # recalc totals
        so = SalesOrder(**{**existing, "lines": [ln.model_dump() for ln in body.lines]})
        _recalc_totals(so)
        updates["lines"] = [ln.model_dump() for ln in body.lines]
        updates.update({"subtotal": so.subtotal, "vat_amount": so.vat_amount, "total": so.total})
    return await update_doc(collection="sales_orders", doc_id=oid, updates=updates, user=user,
                             entity_type="sales_order", ip=get_client_ip(request))


class StatusChange(BaseModel):
    order_status: str
    reason: Optional[str] = None


@router.post("/{oid}/status")
async def change_status(oid: str, body: StatusChange, request: Request,
                         user: dict = Depends(require_permission("sales_orders.edit"))):
    db = get_db()
    existing = await db.sales_orders.find_one({"_id": oid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not existing: raise HTTPException(status_code=404, detail="Ordine non trovato")
    enforce_status_transition(existing.get("order_status", "draft"), body.order_status, ORDER_FLOW)
    updates = {"order_status": body.order_status}
    return await update_doc(collection="sales_orders", doc_id=oid, updates=updates, user=user,
                             entity_type="sales_order", ip=get_client_ip(request))


@router.delete("/{oid}")
async def delete_order(oid: str, request: Request,
                        user: dict = Depends(require_permission("sales_orders.delete"))):
    return await soft_delete_doc(collection="sales_orders", doc_id=oid, user=user,
                                   entity_type="sales_order", ip=get_client_ip(request))
