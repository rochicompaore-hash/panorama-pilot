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
    customer = await get_db().customers.find_one({"_id": body.customer_id, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not customer:
        raise HTTPException(422, "Seleziona un cliente della stessa azienda")
    so = SalesOrder(
        id=new_id(),
        customer_id=body.customer_id, contract_id=body.contract_id, quote_id=body.quote_id,
        survey_id=body.survey_id, site_address=body.site_address, notes=body.notes,
        priority=body.priority, lines=body.lines,
    )
    _recalc_totals(so)
    from app.services import order_process as process
    task = await process.make_task(get_db(), user["tenant_id"], "contract")
    for key, value in process.task_fields(task).items():
        setattr(so, key, value)
    so.operational_history = [{"at": datetime.now(timezone.utc).isoformat(), "actor_id": user["id"],
        "event": "process.started", "details": {"to_task": task, "evidence": "Commessa creata con attività commerciale"}}]
    doc = await create_doc(collection="sales_orders", model_instance=so, user=user,
                            entity_type="sales_order", ip=get_client_ip(request),
                            set_number=True, number_key="sales_order", number_prefix="ORD-")
    await record_activity(tenant_id=user["tenant_id"], type="sales_order_created",
                          subject=f"Ordine cliente {doc.get('number')} creato",
                          customer_id=body.customer_id, quote_id=body.quote_id,
                          user_id=user["id"], user_email=user["email"])
    return doc


class SalesOrderPatch(BaseModel):
    expected_version: Optional[int] = None
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
    updates = body.model_dump(exclude_none=True, exclude={"expected_version"})
    if body.lines is not None:
        # recalc totals
        so = SalesOrder(**{**existing, "lines": [ln.model_dump() for ln in body.lines]})
        _recalc_totals(so)
        updates["lines"] = [ln.model_dump() for ln in body.lines]
        updates.update({"subtotal": so.subtotal, "vat_amount": so.vat_amount, "total": so.total})
    if existing.get("operational_enabled"):
        from app.routers.operational_control import write_order, assert_version
        if body.expected_version is None:
            raise HTTPException(409, "Versione richiesta per modificare una commessa gestita dal centro operativo")
        assert_version(existing, body.expected_version)
        details = None
        if body.lines is not None or body.site_address is not None:
            for key in ("contract", "technical", "admin_order", "materials", "admin_install", "resources", "acceptance", "documents", "admin_close"):
                updates["operational_checks." + key + ".satisfied"] = False
            if existing.get("operational_process"):
                from app.services import order_process as process
                task = await process.make_task(db, user["tenant_id"], "contract")
                updates.update(process.rewind_fields(existing, "contract", task))
                details = {"from_task": existing["operational_process"]["task"], "to_task": task,
                    "evidence": "Righe o indirizzo modificati: nuova verifica del fascicolo"}
        return await write_order(oid, user, body.expected_version, updates, "order.revised", details)
    return await update_doc(collection="sales_orders", doc_id=oid, updates=updates, user=user,
                             entity_type="sales_order", ip=get_client_ip(request))


class StatusChange(BaseModel):
    order_status: str
    reason: Optional[str] = None
    expected_version: Optional[int] = None


@router.post("/{oid}/status")
async def change_status(oid: str, body: StatusChange, request: Request,
                         user: dict = Depends(require_permission("sales_orders.edit"))):
    db = get_db()
    existing = await db.sales_orders.find_one({"_id": oid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not existing: raise HTTPException(status_code=404, detail="Ordine non trovato")
    if existing.get("operational_process"):
        raise HTTPException(409, "Completa l’attività assegnata: la procedura determina il passaggio di reparto")
    enforce_status_transition(existing.get("order_status", "draft"), body.order_status, ORDER_FLOW)
    updates = {"order_status": body.order_status}
    if existing.get("operational_enabled"):
        from app.services.operational_control import missing_checks
        from app.routers.operational_control import write_order, assert_version
        if body.expected_version is None:
            raise HTTPException(409, "Ricarica la commessa: versione richiesta")
        assert_version(existing, body.expected_version)
        missing = missing_checks(existing, body.order_status)
        if missing:
            raise HTTPException(409, {"message": "Passaggio bloccato", "missing": missing})
        if body.order_status == "cancelled" and len((body.reason or "").strip()) < 5:
            raise HTTPException(422, "Indica il motivo dell’annullamento")
        updates["operational_transition_reason"] = body.reason
        return await write_order(oid, user, body.expected_version, updates, "status." + body.order_status)
    return await update_doc(collection="sales_orders", doc_id=oid, updates=updates, user=user,
                             entity_type="sales_order", ip=get_client_ip(request))


@router.delete("/{oid}")
async def delete_order(oid: str, request: Request,
                        user: dict = Depends(require_permission("sales_orders.delete"))):
    existing = await get_doc(collection="sales_orders", doc_id=oid, tenant_id=user["tenant_id"])
    if existing.get("operational_process"):
        raise HTTPException(409, "Le commesse con storico di reparto si annullano con un motivo; non si eliminano")
    return await soft_delete_doc(collection="sales_orders", doc_id=oid, user=user,
                                   entity_type="sales_order", ip=get_client_ip(request))
