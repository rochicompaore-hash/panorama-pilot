"""M14 — Payment plans, payments, invoices."""
from __future__ import annotations
from datetime import datetime, timezone, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models import new_id
from app.models_ops import PaymentPlan, PaymentInstallment, Payment, Invoice
from app.mongo_utils import to_mongo, from_mongo
from app.services.ops_common import create_doc, get_doc, list_docs, update_doc

pp_router = APIRouter(prefix="/payment-plans", tags=["payment-plans"])
p_router = APIRouter(prefix="/payments", tags=["payments"])
inv_router = APIRouter(prefix="/invoices", tags=["invoices"])


def _q(x: float) -> float:
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class PaymentPlanCreate(BaseModel):
    customer_id: str
    total_amount: float
    contract_id: Optional[str] = None
    sales_order_id: Optional[str] = None
    installments: List[PaymentInstallment] = []


@pp_router.post("")
async def create_plan(body: PaymentPlanCreate, request: Request,
                      user: dict = Depends(require_permission("admin.payments.edit"))):
    # If no installments provided, seed with default 50/50
    inst = body.installments
    if not inst:
        inst = [
            PaymentInstallment(ref="I1", label="Acconto alla firma", trigger="signature",
                               percent=50, amount=_q(body.total_amount * 0.5)),
            PaymentInstallment(ref="I2", label="Saldo ad avviso merce pronta", trigger="goods_ready",
                               percent=50, amount=_q(body.total_amount * 0.5)),
        ]
    plan = PaymentPlan(id=new_id(), customer_id=body.customer_id, total_amount=_q(body.total_amount),
                       contract_id=body.contract_id, sales_order_id=body.sales_order_id,
                       installments=inst, outstanding_amount=_q(body.total_amount))
    return await create_doc(collection="payment_plans", model_instance=plan, user=user,
                             entity_type="payment_plan", ip=get_client_ip(request))


@pp_router.get("")
async def list_plans(customer_id: Optional[str] = None, contract_id: Optional[str] = None,
                     skip: int = 0, limit: int = Query(50, le=200),
                     user: dict = Depends(require_permission("admin.payments.view"))):
    return await list_docs(collection="payment_plans", tenant_id=user["tenant_id"],
                            filters={"customer_id": customer_id, "contract_id": contract_id},
                            sort=[("created_at", -1)], skip=skip, limit=limit)


@pp_router.get("/{pid}")
async def get_plan(pid: str, user: dict = Depends(require_permission("admin.payments.view"))):
    return await get_doc(collection="payment_plans", doc_id=pid, tenant_id=user["tenant_id"])


class PaymentCreate(BaseModel):
    payment_plan_id: str
    amount: float
    method: Optional[str] = None
    reference: Optional[str] = None
    installment_ref: Optional[str] = None
    received_at: Optional[datetime] = None
    notes: Optional[str] = None


@p_router.post("")
async def create_payment(body: PaymentCreate, request: Request,
                          user: dict = Depends(require_permission("admin.payments.edit"))):
    db = get_db()
    plan = await db.payment_plans.find_one({"_id": body.payment_plan_id, "tenant_id": user["tenant_id"]})
    if not plan: raise HTTPException(status_code=400, detail="Piano pagamenti non trovato")
    p = Payment(id=new_id(), payment_plan_id=body.payment_plan_id,
                 customer_id=plan["customer_id"], installment_ref=body.installment_ref,
                 amount=_q(body.amount), method=body.method, reference=body.reference,
                 received_at=body.received_at or datetime.now(timezone.utc), notes=body.notes)
    doc = await create_doc(collection="payments", model_instance=p, user=user,
                            entity_type="payment", ip=get_client_ip(request))
    # Update plan
    total_paid = plan.get("paid_amount", 0) + _q(body.amount)
    outstanding = _q(plan["total_amount"] - total_paid)
    # Update matching installment
    inst_list = plan.get("installments", [])
    if body.installment_ref:
        for i in inst_list:
            if i.get("ref") == body.installment_ref:
                i["paid_amount"] = _q((i.get("paid_amount") or 0) + body.amount)
                i["paid_at"] = (body.received_at or datetime.now(timezone.utc)).isoformat()
                i["payment_method"] = body.method
                if i["paid_amount"] >= (i.get("amount") or 0) - 0.01:
                    i["installment_status"] = "paid"
                else:
                    i["installment_status"] = "partial"
                break
    plan_status = "closed" if outstanding <= 0.01 else "active"
    await db.payment_plans.update_one({"_id": plan["_id"]},
        {"$set": {"paid_amount": total_paid, "outstanding_amount": outstanding,
                  "plan_status": plan_status, "installments": inst_list,
                  "updated_at": datetime.now(timezone.utc).isoformat()}})
    return doc


@p_router.get("")
async def list_payments(customer_id: Optional[str] = None, payment_plan_id: Optional[str] = None,
                         skip: int = 0, limit: int = 50,
                         user: dict = Depends(require_permission("admin.payments.view"))):
    return await list_docs(collection="payments", tenant_id=user["tenant_id"],
                            filters={"customer_id": customer_id, "payment_plan_id": payment_plan_id},
                            sort=[("received_at", -1)], skip=skip, limit=limit)


class InvoiceCreate(BaseModel):
    customer_id: str
    contract_id: Optional[str] = None
    sales_order_id: Optional[str] = None
    issue_date: date
    due_date: Optional[date] = None
    subtotal: float = 0
    vat_amount: float = 0
    total: float = 0
    lines: List[dict] = []


@inv_router.post("")
async def create_invoice(body: InvoiceCreate, request: Request,
                          user: dict = Depends(require_permission("admin.invoices.edit"))):
    i = Invoice(id=new_id(), **body.model_dump())
    return await create_doc(collection="invoices", model_instance=i, user=user,
                             entity_type="invoice", ip=get_client_ip(request),
                             set_number=True, number_key="invoice", number_prefix="FT-")


@inv_router.get("")
async def list_invoices(customer_id: Optional[str] = None, invoice_status: Optional[str] = None,
                         skip: int = 0, limit: int = Query(50, le=200),
                         user: dict = Depends(require_permission("admin.invoices.view"))):
    return await list_docs(collection="invoices", tenant_id=user["tenant_id"],
                            filters={"customer_id": customer_id, "invoice_status": invoice_status},
                            sort=[("number_int", -1)], skip=skip, limit=limit)


@inv_router.get("/{iid}")
async def get_invoice(iid: str, user: dict = Depends(require_permission("admin.invoices.view"))):
    return await get_doc(collection="invoices", doc_id=iid, tenant_id=user["tenant_id"])


@inv_router.get("/dashboard/kpi")
async def admin_kpi(user: dict = Depends(require_permission("admin.payments.view"))):
    db = get_db()
    tenant = user["tenant_id"]
    total_outstanding = 0.0
    total_paid = 0.0
    total_amount = 0.0
    async for pl in db.payment_plans.find({"tenant_id": tenant, "status": {"$ne": "deleted"}, "deleted_at": None}):
        total_outstanding += pl.get("outstanding_amount", 0) or 0
        total_paid += pl.get("paid_amount", 0) or 0
        total_amount += pl.get("total_amount", 0) or 0
    today = datetime.now(timezone.utc).date().isoformat()
    overdue = 0
    async for pl in db.payment_plans.find({"tenant_id": tenant, "outstanding_amount": {"$gt": 0}}):
        for inst in (pl.get("installments") or []):
            due = inst.get("due_date")
            if due and str(due) < today and inst.get("installment_status") != "paid":
                overdue += (inst.get("amount") or 0) - (inst.get("paid_amount") or 0)
    return {"total_amount": _q(total_amount), "total_paid": _q(total_paid),
             "total_outstanding": _q(total_outstanding), "total_overdue": _q(overdue)}
