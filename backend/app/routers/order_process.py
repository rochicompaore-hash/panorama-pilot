"""Department inbox backed by the current task on the original sales order."""
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, AwareDatetime
from app.deps import require_permission
from app.services import order_process as process
from app.services.operational_control import CHECKS
from app.mongo_utils import from_mongo
from . import operational_control as control

router = APIRouter(prefix="/process", tags=["Order handoffs"])


class Route(control.Command):
    owner_id: str = Field(min_length=1, max_length=100)
    target_hours: int = Field(ge=1, le=2160)


class Assign(control.Command):
    owner_id: str = Field(min_length=1, max_length=100)
    due_at: AwareDatetime
    reason: str = Field(min_length=5, max_length=2000)


class Action(control.Command):
    action: Literal["accept", "complete", "block", "resume", "return", "cancel"]
    evidence: str = Field(default="", max_length=2000)
    target_step: str | None = None
    residuals: int | None = Field(default=None, ge=0, le=10000)


async def manager(user):
    if not await process.permits(user, "workflow.assign"):
        raise HTTPException(403, "Permesso mancante: workflow.assign")


@router.get("/schema")
async def schema(user=Depends(require_permission("sales_orders.view"))):
    db = control.get_db()
    users = await db.users.find({"tenant_id": user["tenant_id"], "deleted_at": None, "is_active": {"$ne": False}}).to_list(1000)
    candidates = {}
    for person in users:
        if await process.permits(person, "sales_orders.view"):
            candidates[person["_id"]] = {"name": person.get("full_name") or person.get("name") or person["_id"],
                "steps": [s["key"] for s in process.STEPS if await process.permits(person, s["permission"])]}
    routes = await db.order_process_routes.find({"tenant_id": user["tenant_id"]}, {"history": 0}).to_list(100)
    return {"areas": process.AREAS, "steps": process.STEPS, "candidates": candidates,
            "routes": {r["step"]: from_mongo(r) for r in routes}, "can_assign": await process.permits(user, "workflow.assign"),
            "user_id": user["id"], "allowed_steps": [s["key"] for s in process.STEPS if await process.permits(user, s["permission"])]}


@router.put("/routes/{step}")
async def set_route(step: str, body: Route, user=Depends(require_permission("sales_orders.view", "workflow.assign"))):
    db = control.get_db()
    if step not in process.BY_KEY or not await process.qualified_user(db, user["tenant_id"], body.owner_id, process.BY_KEY[step]):
        raise HTTPException(422, "Incaricato non attivo o privo dei permessi per questa attività")
    key = f"{user['tenant_id']}:{step}"
    now = datetime.now(timezone.utc).isoformat()
    updates = {"step": step, "owner_id": body.owner_id, "target_hours": body.target_hours, "updated_by": user["id"], "updated_at": now}
    if body.version == 0:
        from pymongo.errors import DuplicateKeyError
        try:
            await db.order_process_routes.insert_one({"_id": key, "tenant_id": user["tenant_id"], "version": 1, **updates,
                "history": [{**updates, "version": 1}]})
        except DuplicateKeyError:
            raise HTTPException(409, "Configurazione modificata: ricarica")
    else:
        result = await db.order_process_routes.update_one({"_id": key, "tenant_id": user["tenant_id"], "version": body.version},
            {"$set": updates, "$inc": {"version": 1}, "$push": {"history": {**updates, "version": body.version + 1}}})
        if not result.modified_count:
            raise HTTPException(409, "Configurazione modificata: ricarica")
    return {"version": body.version + 1, **updates}


@router.get("/inbox")
async def inbox(area: str = "", mine: bool = False, attention: bool = False, skip: int = Query(0, ge=0),
                limit: int = Query(50, ge=1, le=200), user=Depends(require_permission("sales_orders.view"))):
    query = {"tenant_id": user["tenant_id"], "deleted_at": None, "order_status": {"$nin": ["closed", "cancelled"]},
             "operational_process.task": {"$exists": True}}
    prefix = "operational_process.task."
    if area:
        if area not in process.AREAS:
            raise HTTPException(422, "Reparto sconosciuto")
        query[prefix + "area"] = area
    if mine:
        query[prefix + "owner_id"] = user["id"]
    if attention:
        query["$or"] = [{prefix + "owner_id": None}, {prefix + "due_at": None}, {prefix + "status": "blocked"},
                         {prefix + "due_at": {"$lt": datetime.now(timezone.utc).isoformat()}}]
    db = control.get_db()
    rows = await db.sales_orders.find(query, {"operational_history": 0}).sort([("operational_due_at", 1), ("_id", 1)]).skip(skip).limit(limit).to_list(limit)
    names = await control.customer_names(rows, user["tenant_id"])
    return {"items": [{"id": r["_id"], "number": r.get("number"), "customer_name": names.get(r.get("customer_id"), ""),
                       "version": r.get("version", 0), "task": r["operational_process"]["task"]} for r in rows],
            "total": await db.sales_orders.count_documents(query)}


@router.post("/orders/{oid}/start")
async def start(oid: str, body: control.Command, user=Depends(require_permission("sales_orders.view", "workflow.assign"))):
    order = await control.load_order(oid, user)
    control.assert_version(order, body.version)
    if order.get("operational_process"):
        raise HTTPException(409, "Procedura già avviata")
    task = await process.make_task(control.get_db(), user["tenant_id"], "contract")
    return await control.write_order(oid, user, body.version, process.rewind_fields(order, "contract", task),
        "process.started", {"to_task": task,
            "previous_plan": {k: order.get(k) for k in ("order_status", "operational_owner_id", "operational_next_action", "operational_due_at", "operational_block")},
            "evidence": "Avvio dal controllo del fascicolo; nessun passaggio pregresso attestato automaticamente"})


@router.put("/orders/{oid}/assignment")
async def assign(oid: str, body: Assign, user=Depends(require_permission("sales_orders.view", "workflow.assign"))):
    order = await control.load_order(oid, user)
    control.assert_version(order, body.version)
    before = (order.get("operational_process") or {}).get("task")
    if not before:
        raise HTTPException(409, "Avvia prima la procedura")
    if not await process.qualified_user(control.get_db(), user["tenant_id"], body.owner_id, process.BY_KEY[before["step"]]):
        raise HTTPException(422, "Incaricato non attivo o privo dei permessi per questa attività")
    task = {**before, "owner_id": body.owner_id, "due_at": body.due_at.astimezone(timezone.utc).isoformat()}
    if before.get("owner_id") != body.owner_id:
        task.update(accepted_at=None, status="blocked" if before["status"] == "blocked" else "pending")
    return await control.write_order(oid, user, body.version, process.task_fields(task), "process.assigned",
        {"from_task": before, "to_task": task, "evidence": body.reason})


@router.post("/orders/{oid}/action")
async def action(oid: str, body: Action, user=Depends(require_permission("sales_orders.view"))):
    order = await control.load_order(oid, user)
    control.assert_version(order, body.version)
    before = (order.get("operational_process") or {}).get("task")
    if not before:
        raise HTTPException(409, "Avvia prima la procedura")
    step = process.BY_KEY[before["step"]]
    now = datetime.now(timezone.utc).isoformat()
    task = {**before}
    updates = {}
    if body.action in ("return", "cancel"):
        await manager(user)
    elif before.get("owner_id") != user["id"] or not await process.permits(user, step["permission"]):
        raise HTTPException(403, "Solo l’incaricato con il permesso di reparto può lavorare questa attività")
    if body.action != "accept" and len(body.evidence.strip()) < 5:
        raise HTTPException(422, "Indica esito, documento/revisione o motivo (almeno 5 caratteri)")
    if body.action == "accept":
        if before["status"] != "pending" or not before.get("due_at"):
            raise HTTPException(409, "Attività non in attesa o scadenza da assegnare")
        task.update(status="in_progress", accepted_at=now)
    elif body.action == "block":
        if before["status"] != "in_progress":
            raise HTTPException(409, "Prendi prima in carico l’attività")
        task.update(status="blocked", block=body.evidence)
    elif body.action == "resume":
        if before["status"] != "blocked" or not before.get("due_at"):
            raise HTTPException(409, "Nessun blocco da risolvere o scadenza mancante")
        task.update(status="in_progress", block="", accepted_at=before.get("accepted_at") or now)
    elif body.action == "cancel":
        task.update(status="cancelled", completed_at=now)
        updates["order_status"] = "cancelled"
    elif body.action == "return":
        if body.target_step not in process.BY_KEY or list(process.BY_KEY).index(body.target_step) > list(process.BY_KEY).index(step["key"]):
            raise HTTPException(422, "Puoi rinviare solo alla stessa attività o a una precedente")
        task = await process.make_task(control.get_db(), user["tenant_id"], body.target_step)
        updates.update(process.rewind_fields(order, body.target_step, task))
    elif body.action == "complete":
        if before["status"] != "in_progress" or before.get("block"):
            raise HTTPException(409, "Attività non in carico o bloccata")
        missing = [CHECKS[k][0] for k in process.required_before(step["key"]) if not (order.get("operational_checks") or {}).get(k, {}).get("satisfied")]
        if step["key"] != "contract" and order.get("payment_mode") == "financed" and order.get("financing_status") not in ("signed", "liquidation_requested", "disbursed"):
            missing.append("Finanziamento approvato e sottoscritto")
        if missing:
            raise HTTPException(409, {"message": "Prerequisiti da riverificare", "missing": missing})
        if body.residuals is not None and step["key"] not in ("installation", "acceptance"):
            raise HTTPException(422, "I completamenti si registrano nella fase di posa/collaudo")
        residuals = body.residuals if body.residuals is not None else order.get("operational_residuals", 0)
        if step["key"] in ("acceptance", "documents", "admin_close") and residuals:
            raise HTTPException(409, "Completamenti ancora aperti: mantieni il lavoro nella commessa")
        if body.residuals is not None:
            updates["operational_residuals"] = residuals
        if step["check"]:
            updates[f"operational_checks.{step['check']}"] = {"satisfied": True, "evidence": body.evidence, "actor_id": user["id"], "at": now}
        updates["order_status"] = step["order_status"]
        index = list(process.BY_KEY).index(step["key"])
        if index + 1 < len(process.STEPS):
            task = await process.make_task(control.get_db(), user["tenant_id"], process.STEPS[index + 1]["key"])
        else:
            task.update(status="completed", completed_at=now)
    updates.update(process.task_fields(task))
    return await control.write_order(oid, user, body.version, updates, "process." + body.action,
        {"from_task": before, "to_task": task, "evidence": body.evidence,
         "completed_task": {**before, "status": "completed", "completed_at": now, "evidence": body.evidence} if body.action == "complete" else None})
