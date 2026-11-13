"""Operational control uses the existing tenant-scoped sales_orders collection."""
import csv
import io
import json
import re
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime
from app.db import get_db
from app.deps import require_permission, get_permission_keys_for_user
from app.mongo_utils import from_mongo
from app.services.operational_control import CHECKS, STATES, FINANCE_STATES, FINANCE_LABELS, missing_checks, order_summary, safe_csv

router = APIRouter(prefix="/operations", tags=["Operational control"])


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version: int = Field(ge=0)


class Plan(Command):
    owner_id: str = Field(min_length=1, max_length=100)
    next_action: str = Field(min_length=1, max_length=500)
    due_at: AwareDatetime
    block: str = Field(default="", max_length=1000)
    residuals: int = Field(default=0, ge=0, le=10000)


class Check(Command):
    key: str
    satisfied: bool
    evidence: str = Field(min_length=5, max_length=2000)


class Finance(Command):
    payment_mode: Literal["standard", "financed"]
    financing_status: Literal["none", "submitted", "review", "approved", "signed", "liquidation_requested", "disbursed"]
    evidence: str = Field(min_length=5, max_length=2000)


async def can(user, permission):
    if user.get("is_superadmin") or user.get("is_platform_owner"):
        return True
    permissions = await get_permission_keys_for_user(user)
    return "*" in permissions or permission in permissions


async def load_order(oid, user):
    order = await get_db().sales_orders.find_one({"_id": oid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not order:
        raise HTTPException(404, "Commessa non trovata")
    return order


def assert_version(order, version):
    if version != order.get("version", 0):
        raise HTTPException(409, "Commessa modificata. Ricarica prima di salvare.")


async def write_order(oid, user, version, updates, event, details=None):
    now = datetime.now(timezone.utc).isoformat()
    query = {"_id": oid, "tenant_id": user["tenant_id"], "deleted_at": None,
             "order_status": {"$nin": ["closed", "cancelled"]}}
    if version == 0:
        query["$or"] = [{"version": 0}, {"version": {"$exists": False}}]
    else:
        query["version"] = version
    updates.update(updated_at=now, updated_by=user["id"])
    record = {"at": now, "actor_id": user["id"], "event": event, "changes": updates.copy()}
    if details:
        record["details"] = details
    result = await get_db().sales_orders.find_one_and_update(query, {
        "$set": updates, "$inc": {"version": 1},
        "$push": {"operational_history": record},
    }, return_document=True)
    if not result:
        raise HTTPException(409, "Commessa aggiornata da un altro utente o già chiusa. Ricarica prima di salvare.")
    return from_mongo(result)


@router.get("/schema")
async def schema(user=Depends(require_permission("sales_orders.view"))):
    from app.routers.sales_orders import ORDER_FLOW
    return {"checks": [{"key": key, "label": value[0], "permission": value[1], "can_edit": await can(user, value[1])} for key, value in CHECKS.items()],
            "states": STATES, "transitions": {k: sorted(v) for k, v in ORDER_FLOW.items()},
            "finance_states": dict(zip(FINANCE_STATES, FINANCE_LABELS)),
            "can_plan": await can(user, "sales_orders.edit"), "can_finance": await can(user, "admin.payments.edit")}


@router.get("/assignees")
async def assignees(user=Depends(require_permission("sales_orders.view"))):
    rows = await get_db().users.find({"tenant_id": user["tenant_id"], "deleted_at": None, "is_active": {"$ne": False}},
                                   {"_id": 1, "full_name": 1, "name": 1}).sort("full_name", 1).to_list(1000)
    return [{"id": row["_id"], "name": row.get("full_name") or row.get("name") or row["_id"]} for row in rows]


def filters(user, q, status):
    query = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if q:
        query["$or"] = [{key: {"$regex": re.escape(q), "$options": "i"}} for key in ("number", "operational_next_action", "operational_block")]
    if status:
        query["order_status"] = status
    return query


async def customer_names(rows, tenant_id):
    ids = list({row.get("customer_id") for row in rows if row.get("customer_id")})
    customers = await get_db().customers.find({"_id": {"$in": ids}, "tenant_id": tenant_id, "deleted_at": None},
        {"display_name": 1, "company_name": 1, "name": 1, "first_name": 1, "last_name": 1}).to_list(len(ids) or 1)
    return {c["_id"]: c.get("display_name") or c.get("company_name") or c.get("name") or
            " ".join(filter(None, [c.get("first_name"), c.get("last_name")])) for c in customers}


@router.get("/orders")
async def orders(q: str = Query("", max_length=200), status: str = "", skip: int = Query(0, ge=0),
                 limit: int = Query(50, ge=1, le=200), user=Depends(require_permission("sales_orders.view"))):
    db = get_db()
    query = filters(user, q, status)
    rows = await db.sales_orders.find(query, {"operational_history": 0}).sort([("created_at", -1), ("_id", 1)]).skip(skip).limit(limit).to_list(limit)
    names = await customer_names(rows, user["tenant_id"])
    return {"items": [{**from_mongo(row), "customer_name": names.get(row.get("customer_id"), ""), "control": order_summary(row)} for row in rows],
            "total": await db.sales_orders.count_documents(query), "skip": skip, "limit": limit}


@router.get("/export")
async def export_orders(format: Literal["csv", "json"] = "csv", q: str = Query("", max_length=200),
                        status: str = "", user=Depends(require_permission("sales_orders.view"))):
    cursor = get_db().sales_orders.find(filters(user, q, status)).sort("_id", 1)
    columns = ["id", "number", "customer_id", "order_status", "operational_owner_id", "operational_next_action",
               "operational_due_at", "operational_block", "operational_residuals", "payment_mode", "financing_status"]
    async def stream():
        if format == "json":
            yield '['
            first = True
            async for row in cursor:
                value = from_mongo(row)
                value.pop("tenant_id", None)
                yield ("" if first else ",") + json.dumps(value, ensure_ascii=False, default=str)
                first = False
            yield ']'
        else:
            yield '\ufeff'
            buffer = io.StringIO()
            writer = csv.writer(buffer, delimiter=';')
            writer.writerow(columns)
            yield buffer.getvalue()
            async for row in cursor:
                buffer.seek(0); buffer.truncate(0)
                writer.writerow([safe_csv(from_mongo(row).get(k)) for k in columns])
                yield buffer.getvalue()
    return StreamingResponse(stream(), media_type="application/json" if format == "json" else "text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="commesse.{format}"', "Cache-Control": "no-store"})


@router.get("/orders/{oid}")
async def detail(oid: str, user=Depends(require_permission("sales_orders.view"))):
    order = await load_order(oid, user)
    from app.routers.sales_orders import ORDER_FLOW
    result = from_mongo(order)
    result["control"] = order_summary(order)
    result["transitions"] = [{"status": target, "missing": missing_checks(order, target)} for target in sorted(ORDER_FLOW.get(order.get("order_status", "draft"), set()))]
    return result


@router.put("/orders/{oid}/plan")
async def plan(oid: str, body: Plan, user=Depends(require_permission("sales_orders.edit"))):
    order = await load_order(oid, user)
    assert_version(order, body.version)
    if order.get("operational_process"):
        raise HTTPException(409, "Usa l’assegnazione dell’attività: il passaggio di reparto è gestito dalla procedura")
    assignee = await get_db().users.find_one({"_id": body.owner_id, "tenant_id": user["tenant_id"], "deleted_at": None, "is_active": {"$ne": False}})
    if not assignee:
        raise HTTPException(422, "Seleziona un incaricato attivo della stessa azienda")
    if body.residuals != order.get("operational_residuals", 0) and not await can(user, "installation.edit"):
        raise HTTPException(403, "Permesso mancante: installation.edit per modificare i completamenti")
    return await write_order(oid, user, body.version, {
        "operational_enabled": True, "operational_owner_id": body.owner_id, "operational_next_action": body.next_action,
        "operational_due_at": body.due_at.astimezone(timezone.utc).isoformat(), "operational_block": body.block,
        "operational_residuals": body.residuals,
    }, "plan.updated")


@router.post("/orders/{oid}/checks")
async def check(oid: str, body: Check, user=Depends(require_permission("sales_orders.view"))):
    if body.key not in CHECKS:
        raise HTTPException(422, "Controllo sconosciuto")
    if not await can(user, CHECKS[body.key][1]):
        raise HTTPException(403, "Permesso mancante: " + CHECKS[body.key][1])
    order = await load_order(oid, user)
    assert_version(order, body.version)
    if order.get("operational_process"):
        raise HTTPException(409, "Il controllo si registra completando l’attività assegnata")
    if not order.get("operational_enabled"):
        raise HTTPException(409, "Assegna prima responsabile, prossima azione e scadenza")
    if body.satisfied and body.key == "admin_survey" and order.get("payment_mode") == "financed" and order.get("financing_status") not in ("signed", "liquidation_requested", "disbursed"):
        raise HTTPException(409, "Finanziamento da approvare e sottoscrivere prima del nulla osta al rilievo")
    return await write_order(oid, user, body.version, {"operational_checks." + body.key: {
        "satisfied": body.satisfied, "evidence": body.evidence, "actor_id": user["id"],
        "at": datetime.now(timezone.utc).isoformat(),
    }}, "check." + body.key)


@router.put("/orders/{oid}/finance")
async def finance(oid: str, body: Finance, user=Depends(require_permission("admin.payments.edit", "sales_orders.view"))):
    order = await load_order(oid, user)
    assert_version(order, body.version)
    if body.payment_mode == "standard" and body.financing_status != "none":
        raise HTTPException(422, "Nel pagamento ordinario lo stato finanziamento deve essere Non prevista")
    updates = {"payment_mode": body.payment_mode, "financing_status": body.financing_status, "finance_evidence": body.evidence}
    details = None
    if order.get("payment_mode", "standard") != body.payment_mode or order.get("financing_status", "none") != body.financing_status:
        for key in ("admin_survey", "admin_order", "admin_install", "admin_close"):
            updates["operational_checks." + key + ".satisfied"] = False
        if order.get("operational_process"):
            from app.services import order_process as process
            before = order["operational_process"]["task"]
            if list(process.BY_KEY).index(before["step"]) > 1:
                task = await process.make_task(get_db(), user["tenant_id"], "admin_survey")
                updates.update(process.rewind_fields(order, "admin_survey", task))
                details = {"from_task": before, "to_task": task, "evidence": "Condizioni finanziarie variate: nuova verifica dei nulla osta. " + body.evidence}
    return await write_order(oid, user, body.version, updates, "finance.updated", details)


from app.routers.order_process import router as process_router
router.include_router(process_router)
