"""M7 — BOM + Production orders + Cutting lists + Phase logs."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models import new_id
from app.models_ops import (BOM, BOMComponent, ProductionOrder, CuttingList, CuttingPiece,
                             BarOptimization, ProductionPhaseLog)
from app.mongo_utils import to_mongo, from_mongo
from app.services.ops_common import (create_doc, get_doc, list_docs, update_doc, soft_delete_doc,
                                       enforce_status_transition)

# -------------- BOM --------------
bom_router = APIRouter(prefix="/boms", tags=["boms"])


class BOMCreate(BaseModel):
    product_type_key: str
    label: str
    components: List[BOMComponent] = []
    is_active: bool = True
    notes: Optional[str] = None


@bom_router.get("")
async def list_boms(product_type_key: Optional[str] = None,
                     user: dict = Depends(require_permission("production.view"))):
    return await list_docs(collection="boms", tenant_id=user["tenant_id"],
                            filters={"product_type_key": product_type_key, "is_active": True},
                            sort=[("label", 1)], limit=200)


@bom_router.post("")
async def create_bom(body: BOMCreate, request: Request,
                      user: dict = Depends(require_permission("production.edit"))):
    b = BOM(id=new_id(), **body.model_dump())
    return await create_doc(collection="boms", model_instance=b, user=user,
                             entity_type="bom", ip=get_client_ip(request))


@bom_router.patch("/{bid}")
async def patch_bom(bid: str, body: dict, request: Request,
                     user: dict = Depends(require_permission("production.edit"))):
    # Every edit bumps BOM version — handled by update_doc via $inc { version: 1 }.
    # Do NOT set version in body (would conflict with $inc in the same MongoDB update).
    db = get_db()
    existing = await db.boms.find_one({"_id": bid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not existing: raise HTTPException(status_code=404, detail="BOM non trovato")
    body.pop("version", None)  # never allow caller-supplied version
    return await update_doc(collection="boms", doc_id=bid, updates=body, user=user,
                             entity_type="bom", ip=get_client_ip(request))


# -------------- Production orders --------------
prod_router = APIRouter(prefix="/production-orders", tags=["production-orders"])

PROD_FLOW = {
    "waiting_validation": {"waiting_materials", "scheduled", "released", "blocked", "cancelled"},
    "waiting_materials": {"scheduled", "released", "blocked", "cancelled"},
    "scheduled": {"released", "in_progress", "cancelled"},
    "released": {"in_progress", "paused", "cancelled"},
    "in_progress": {"paused", "quality_control", "blocked", "cancelled"},
    "paused": {"in_progress", "cancelled"},
    "blocked": {"in_progress", "cancelled"},
    "quality_control": {"completed", "in_progress"},  # if fail → back to production
    "completed": {"packed"},
    "packed": {"ready_for_dispatch"},
    "ready_for_dispatch": set(),
    "cancelled": set(),
}


class ProdOrderCreate(BaseModel):
    sales_order_id: str
    customer_id: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    priority: int = 3
    lines: List[Dict[str, Any]] = []
    notes: Optional[str] = None


@prod_router.get("")
async def list_prod(prod_status: Optional[str] = None, sales_order_id: Optional[str] = None,
                     skip: int = 0, limit: int = Query(50, le=200),
                     user: dict = Depends(require_permission("production.view"))):
    return await list_docs(collection="production_orders", tenant_id=user["tenant_id"],
                            filters={"prod_status": prod_status, "sales_order_id": sales_order_id},
                            search_fields=["number"],
                            sort=[("priority", 1), ("number_int", -1)], skip=skip, limit=limit)


@prod_router.get("/{pid}")
async def get_prod(pid: str, user: dict = Depends(require_permission("production.view"))):
    return await get_doc(collection="production_orders", doc_id=pid, tenant_id=user["tenant_id"])


@prod_router.post("")
async def create_prod(body: ProdOrderCreate, request: Request,
                       user: dict = Depends(require_permission("production.edit"))):
    p = ProductionOrder(id=new_id(), **body.model_dump())
    return await create_doc(collection="production_orders", model_instance=p, user=user,
                             entity_type="production_order", ip=get_client_ip(request),
                             set_number=True, number_key="production_order", number_prefix="OPR-")


class ProdStatus(BaseModel):
    prod_status: str
    reason: Optional[str] = None


@prod_router.post("/{pid}/status")
async def prod_status(pid: str, body: ProdStatus, request: Request,
                       user: dict = Depends(require_permission("production.edit"))):
    db = get_db()
    existing = await db.production_orders.find_one({"_id": pid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not existing: raise HTTPException(status_code=404, detail="Ordine produzione non trovato")
    enforce_status_transition(existing.get("prod_status", "waiting_validation"), body.prod_status, PROD_FLOW)
    updates = {"prod_status": body.prod_status}
    if body.prod_status == "in_progress" and not existing.get("started_at"):
        updates["started_at"] = datetime.now(timezone.utc).isoformat()
    if body.prod_status == "completed":
        updates["completed_at"] = datetime.now(timezone.utc).isoformat()
    return await update_doc(collection="production_orders", doc_id=pid, updates=updates, user=user,
                             entity_type="production_order", ip=get_client_ip(request))


# -------------- Cutting list + bar optimization --------------
class CuttingListCreate(BaseModel):
    production_order_id: str
    pieces: List[CuttingPiece] = []


def _optimize_first_fit_decreasing(pieces_by_profile: Dict[str, List[float]],
                                    bar_length_mm: float, kerf_mm: float = 3) -> List[BarOptimization]:
    """Simple 1D cutting-stock heuristic (First-Fit Decreasing) per profile."""
    results = []
    for profile, lens in pieces_by_profile.items():
        sorted_lens = sorted(lens, reverse=True)
        bars: List[List[float]] = []  # each bar is a list of piece lengths
        for L in sorted_lens:
            placed = False
            for b in bars:
                used = sum(b) + kerf_mm * (len(b))
                if used + L <= bar_length_mm:
                    b.append(L)
                    placed = True
                    break
            if not placed:
                if L > bar_length_mm:
                    continue  # piece too long — skip (would need larger bar)
                bars.append([L])
        total_used = sum(sum(b) for b in bars)
        total_length = len(bars) * bar_length_mm
        yield_pct = round((total_used / total_length) * 100, 2) if total_length else 0
        scrap = total_length - total_used
        results.append(BarOptimization(
            profile_code=profile, bar_length_mm=bar_length_mm,
            bars_used=len(bars), total_scrap_mm=round(scrap, 2),
            yield_percent=yield_pct, layout=bars,
        ))
    return results


cut_router = APIRouter(prefix="/cutting-lists", tags=["cutting-lists"])


@cut_router.post("")
async def create_cutting_list(body: CuttingListCreate, request: Request,
                                bar_length_mm: float = 6500, kerf_mm: float = 3,
                                user: dict = Depends(require_permission("production.edit"))):
    grouped: Dict[str, List[float]] = {}
    for p in body.pieces:
        grouped.setdefault(p.profile_code, [])
        for _ in range(max(1, p.quantity)):
            grouped[p.profile_code].append(p.length_mm)
    opts = _optimize_first_fit_decreasing(grouped, bar_length_mm=bar_length_mm, kerf_mm=kerf_mm)
    total_bars = sum(o.bars_used for o in opts)
    avg_yield = round(sum(o.yield_percent for o in opts) / len(opts), 2) if opts else 0
    cl = CuttingList(id=new_id(), production_order_id=body.production_order_id,
                      pieces=body.pieces, optimizations=opts,
                      total_bars_used=total_bars, total_yield_percent=avg_yield)
    return await create_doc(collection="cutting_lists", model_instance=cl, user=user,
                             entity_type="cutting_list", ip=get_client_ip(request))


@cut_router.get("")
async def list_cutting_lists(production_order_id: Optional[str] = None,
                              user: dict = Depends(require_permission("production.view"))):
    return await list_docs(collection="cutting_lists", tenant_id=user["tenant_id"],
                            filters={"production_order_id": production_order_id},
                            sort=[("created_at", -1)], limit=100)


# -------------- Phase logs --------------
ph_router = APIRouter(prefix="/production-phases", tags=["production-phases"])


class PhaseLogCreate(BaseModel):
    production_order_id: str
    phase: str
    operator_id: Optional[str] = None
    machine: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    expected_minutes: Optional[float] = None
    actual_minutes: Optional[float] = None
    quantity_ok: int = 0
    quantity_scrap: int = 0
    quantity_rework: int = 0
    stop_reason: Optional[str] = None
    notes: Optional[str] = None


@ph_router.post("")
async def log_phase(body: PhaseLogCreate, request: Request,
                     user: dict = Depends(require_permission("production.edit"))):
    ph = ProductionPhaseLog(id=new_id(), **body.model_dump())
    return await create_doc(collection="production_phase_logs", model_instance=ph, user=user,
                             entity_type="production_phase_log", ip=get_client_ip(request))


@ph_router.get("")
async def list_phases(production_order_id: Optional[str] = None,
                       user: dict = Depends(require_permission("production.view"))):
    return await list_docs(collection="production_phase_logs", tenant_id=user["tenant_id"],
                            filters={"production_order_id": production_order_id},
                            sort=[("created_at", -1)], limit=200)


@prod_router.get("/dashboard/kpi")
async def prod_kpi(user: dict = Depends(require_permission("production.view"))):
    db = get_db()
    tenant = user["tenant_id"]
    counts = {}
    for status in PROD_FLOW.keys():
        counts[status] = await db.production_orders.count_documents(
            {"tenant_id": tenant, "prod_status": status, "deleted_at": None})
    # in-progress + waiting_materials focus
    return {"counts_by_status": counts,
            "wip": counts.get("in_progress", 0) + counts.get("released", 0),
            "blocked": counts.get("blocked", 0) + counts.get("waiting_materials", 0),
            "completed_today": await db.production_orders.count_documents({
                "tenant_id": tenant, "prod_status": "completed",
                "completed_at": {"$gte": datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()}
            }),
    }
