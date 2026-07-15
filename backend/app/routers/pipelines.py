"""Pipelines router + seed helper."""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.models_crm import Pipeline, PipelineStage, PipelineCreate, PipelineUpdate
from app.models import new_id
from app.mongo_utils import to_mongo, from_mongo
from app.services.audit import record_audit

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


DEFAULT_STAGES = [
    {"name": "Nuovo", "order": 0, "color": "#71717A", "probability_default": 10, "is_won": False, "is_lost": False},
    {"name": "Contattato", "order": 1, "color": "#3B82F6", "probability_default": 25, "is_won": False, "is_lost": False},
    {"name": "Qualificato", "order": 2, "color": "#8B5CF6", "probability_default": 45, "is_won": False, "is_lost": False},
    {"name": "Preventivo Inviato", "order": 3, "color": "#F59E0B", "probability_default": 65, "is_won": False, "is_lost": False},
    {"name": "Trattativa", "order": 4, "color": "#F97316", "probability_default": 80, "is_won": False, "is_lost": False},
    {"name": "Vinto", "order": 5, "color": "#10B981", "probability_default": 100, "is_won": True, "is_lost": False},
    {"name": "Perso", "order": 6, "color": "#EF4444", "probability_default": 0, "is_won": False, "is_lost": True},
]


async def seed_default_pipeline(tenant_id: str) -> str:
    db = get_db()
    existing = await db.pipelines.find_one({"tenant_id": tenant_id, "is_default": True, "deleted_at": None})
    if existing:
        return existing["_id"]
    stages = [PipelineStage(**s) for s in DEFAULT_STAGES]
    p = Pipeline(
        id=new_id(), tenant_id=tenant_id,
        name="Pipeline commerciale",
        description="Pipeline di vendita predefinita per infissi",
        stages=stages, is_default=True,
    )
    await db.pipelines.insert_one(to_mongo(p.model_dump(by_alias=True)))
    return p.id


@router.get("")
async def list_pipelines(user: dict = Depends(require_permission("crm.pipelines.view"))):
    db = get_db()
    docs = await db.pipelines.find({"tenant_id": user["tenant_id"], "deleted_at": None}).sort("name", 1).to_list(50)
    return {"items": [from_mongo(d) for d in docs]}


@router.get("/default")
async def get_default(user: dict = Depends(require_permission("crm.pipelines.view"))):
    db = get_db()
    doc = await db.pipelines.find_one({"tenant_id": user["tenant_id"], "is_default": True, "deleted_at": None})
    if not doc:
        pid = await seed_default_pipeline(user["tenant_id"])
        doc = await db.pipelines.find_one({"_id": pid})
    return from_mongo(doc)


@router.post("")
async def create_pipeline(
    body: PipelineCreate, request: Request,
    user: dict = Depends(require_permission("crm.pipelines.manage")),
):
    db = get_db()
    stages = body.stages or [PipelineStage(**s) for s in DEFAULT_STAGES]
    p = Pipeline(
        id=new_id(), tenant_id=user["tenant_id"],
        name=body.name, description=body.description, stages=stages,
        created_by=user["id"], updated_by=user["id"],
    )
    await db.pipelines.insert_one(to_mongo(p.model_dump(by_alias=True)))
    await record_audit(action="pipelines.create", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="pipeline", entity_id=p.id, after=body.model_dump())
    return from_mongo(await db.pipelines.find_one({"_id": p.id}))


@router.patch("/{pid}")
async def update_pipeline(
    pid: str, body: PipelineUpdate, request: Request,
    user: dict = Depends(require_permission("crm.pipelines.manage")),
):
    db = get_db()
    doc = await db.pipelines.find_one({"_id": pid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Pipeline non trovata")
    update = {}
    payload = body.model_dump(exclude_unset=True)
    if "stages" in payload and payload["stages"] is not None:
        payload["stages"] = [(s.model_dump() if hasattr(s, "model_dump") else s) for s in payload["stages"]]
    update.update(payload)
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by"] = user["id"]
    await db.pipelines.update_one({"_id": pid}, {"$set": update})
    await record_audit(action="pipelines.update", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="pipeline", entity_id=pid, after=payload)
    return from_mongo(await db.pipelines.find_one({"_id": pid}))
