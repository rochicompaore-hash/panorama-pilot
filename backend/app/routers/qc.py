"""M9 — QC checks + Non-conformities."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models import new_id
from app.models_ops import QCCheck, QCChecklistItem, NonConformity
from app.services.ops_common import create_doc, get_doc, list_docs, update_doc

qc_router = APIRouter(prefix="/qc-checks", tags=["qc-checks"])
nc_router = APIRouter(prefix="/non-conformities", tags=["non-conformities"])

DEFAULT_FINAL_CHECKS = [
    ("dimensions", "Dimensioni corrette"),
    ("squareness", "Squadratura"),
    ("welding", "Saldature"),
    ("cleaning", "Pulizia"),
    ("hardware", "Ferramenta"),
    ("opening", "Aperture / chiusure"),
    ("glass", "Vetro"),
    ("gaskets", "Guarnizioni"),
    ("aesthetics", "Estetica"),
    ("color", "Colore conforme"),
    ("accessories", "Accessori"),
    ("labeling", "Etichettatura"),
    ("packaging", "Imballaggio"),
    ("order_conformity", "Conformità ordine"),
]


class QCCreate(BaseModel):
    production_order_id: str
    stage: str = "final"


@qc_router.post("")
async def create_check(body: QCCreate, request: Request,
                        user: dict = Depends(require_permission("qc.edit"))):
    items = [QCChecklistItem(code=c, label=l, required=True) for c, l in DEFAULT_FINAL_CHECKS]
    q = QCCheck(id=new_id(), production_order_id=body.production_order_id, stage=body.stage, items=items)
    return await create_doc(collection="qc_checks", model_instance=q, user=user,
                             entity_type="qc_check", ip=get_client_ip(request))


class QCUpdate(BaseModel):
    items: List[QCChecklistItem]
    notes: Optional[str] = None
    passed: Optional[bool] = None


@qc_router.patch("/{qid}")
async def update_check(qid: str, body: QCUpdate, request: Request,
                        user: dict = Depends(require_permission("qc.edit"))):
    all_pass = all(i.passed is True for i in body.items if i.required)
    updates = {
        "items": [i.model_dump() for i in body.items],
        "notes": body.notes,
        "checked_by": user["id"],
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "passed": body.passed if body.passed is not None else all_pass,
    }
    return await update_doc(collection="qc_checks", doc_id=qid, updates=updates, user=user,
                             entity_type="qc_check", ip=get_client_ip(request))


@qc_router.get("")
async def list_checks(production_order_id: Optional[str] = None,
                       user: dict = Depends(require_permission("qc.view"))):
    return await list_docs(collection="qc_checks", tenant_id=user["tenant_id"],
                            filters={"production_order_id": production_order_id},
                            sort=[("created_at", -1)], limit=200)


class NCCreate(BaseModel):
    kind: str
    severity: str = "minor"
    phase: Optional[str] = None
    production_order_id: Optional[str] = None
    sales_order_id: Optional[str] = None
    supplier_id: Optional[str] = None
    item_code: Optional[str] = None
    cause: Optional[str] = None
    action: Optional[str] = None
    cost: Optional[float] = None
    notes: Optional[str] = None


@nc_router.post("")
async def create_nc(body: NCCreate, request: Request,
                     user: dict = Depends(require_permission("qc.edit"))):
    nc = NonConformity(id=new_id(), **body.model_dump())
    return await create_doc(collection="non_conformities", model_instance=nc, user=user,
                             entity_type="non_conformity", ip=get_client_ip(request))


@nc_router.get("")
async def list_ncs(kind: Optional[str] = None, severity: Optional[str] = None,
                    resolved: Optional[bool] = None,
                    skip: int = 0, limit: int = Query(50, le=200),
                    user: dict = Depends(require_permission("qc.view"))):
    filters = {"kind": kind, "severity": severity}
    if resolved is not None:
        filters["resolved_at"] = {"$ne": None} if resolved else None
    return await list_docs(collection="non_conformities", tenant_id=user["tenant_id"],
                            filters=filters, sort=[("created_at", -1)], skip=skip, limit=limit)


@nc_router.post("/{nid}/resolve")
async def resolve_nc(nid: str, request: Request, resolution: str,
                      user: dict = Depends(require_permission("qc.edit"))):
    return await update_doc(collection="non_conformities", doc_id=nid,
                             updates={"resolution": resolution,
                                       "resolved_at": datetime.now(timezone.utc).isoformat()},
                             user=user, entity_type="non_conformity", ip=get_client_ip(request))


@qc_router.get("/dashboard/kpi")
async def qc_kpi(user: dict = Depends(require_permission("qc.view"))):
    db = get_db()
    tenant = user["tenant_id"]
    total_checks = await db.qc_checks.count_documents({"tenant_id": tenant, "deleted_at": None})
    passed = await db.qc_checks.count_documents({"tenant_id": tenant, "passed": True, "deleted_at": None})
    failed = await db.qc_checks.count_documents({"tenant_id": tenant, "passed": False, "deleted_at": None})
    open_nc = await db.non_conformities.count_documents({"tenant_id": tenant, "resolved_at": None, "deleted_at": None})
    total_nc = await db.non_conformities.count_documents({"tenant_id": tenant, "deleted_at": None})
    return {"total_checks": total_checks, "passed": passed, "failed": failed,
            "pass_rate": round(passed / total_checks * 100, 1) if total_checks else 0,
            "open_non_conformities": open_nc, "total_non_conformities": total_nc}
