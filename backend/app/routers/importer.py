"""Pricelist Importer Router — Wizard XLS/CSV completo.

Flusso:
  POST /api/importer/upload           — upload + parse (multipart)
  POST /api/importer/jobs/{id}/map    — set column mappings + validate
  GET  /api/importer/jobs/{id}/preview — preview 200 righe normalizzate
  POST /api/importer/jobs/{id}/publish — pubblica su target_pricelist_id (draft→active)
  POST /api/importer/jobs/{id}/rollback — rollback pubblicazione (ripristina snapshot)
  POST /api/importer/jobs/{id}/cancel  — annulla job non pubblicato
  GET  /api/importer/jobs             — lista job
  GET  /api/importer/jobs/{id}        — dettaglio
"""
from __future__ import annotations
import io
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, Query
from pydantic import BaseModel, Field

from app.db import get_db
from app.deps import require_permission, get_client_ip
from app.mongo_utils import from_mongo, to_mongo
from app.models_geometry import ImportJob, ImportColumnMapping, ImportError
from app.services.audit import record_audit
from app.services.importer_service import (
    parse_file, compute_file_hash, load_sheet, apply_mapping,
    validate_rows, rows_to_pricelist_entries, build_idempotency_key,
    MAX_FILE_MB, MAX_ROWS, PREVIEW_LIMIT,
)

router = APIRouter(prefix="/importer", tags=["importer"])


VALID_ENTITY_TYPES = [
    "profile", "reinforcement", "glazing_bead", "glass_type", "hardware_kit",
    "accessory", "labor", "price_matrix", "surcharge", "min_billable",
    "component_association",
]


# =====================================================================
# 1) UPLOAD + PARSE
# =====================================================================
@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    entity_type: str = Form(...),
    target_pricelist_id: Optional[str] = Form(None),
    supplier_id: Optional[str] = Form(None),
    profile_system_id: Optional[str] = Form(None),
    color_id: Optional[str] = Form(None),
    user: dict = Depends(require_permission("pricelists.manage")),
):
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(400, f"entity_type non valido. Ammessi: {VALID_ENTITY_TYPES}")
    data = await file.read()
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(413, f"File troppo grande: max {MAX_FILE_MB}MB")

    file_hash = compute_file_hash(data)
    db = get_db()

    # Idempotenza: già importato con stesso hash+target?
    idem_key = build_idempotency_key(user["tenant_id"], entity_type, file_hash, target_pricelist_id)
    existing = await db.import_jobs.find_one({
        "tenant_id": user["tenant_id"], "file_hash": file_hash,
        "entity_type": entity_type, "target_pricelist_id": target_pricelist_id,
        "im_status": {"$in": ["published", "draft", "preview_ready"]},
        "deleted_at": None,
    })
    if existing:
        return {
            **from_mongo(existing),
            "warning": "Stesso file già importato — restituisco il job esistente (idempotenza)",
        }

    parsed = parse_file(file.filename, data)
    if parsed.get("error"):
        raise HTTPException(400, parsed["error"])

    job = ImportJob(
        tenant_id=user["tenant_id"],
        entity_type=entity_type,
        filename=file.filename,
        file_hash=file_hash,
        file_size_bytes=len(data),
        sheet_names=parsed["sheet_names"],
        selected_sheet=parsed["first_sheet"],
        total_rows=parsed["total_rows_per_sheet"].get(parsed["first_sheet"], 0),
        detected_headers=parsed["detected_headers"],
        preview_sample=parsed["preview"][:PREVIEW_LIMIT],
        target_pricelist_id=target_pricelist_id,
        supplier_id=supplier_id,
        profile_system_id=profile_system_id,
        color_id=color_id,
        im_status="parsed",
        notes=f"idem_key={idem_key[:16]}",
        created_by=user["id"],
    )
    # persist raw file bytes as base64 in memory temp store (avoid heavy object storage in v1)
    # NB: in produzione va salvato in object storage.
    doc = to_mongo(job.model_dump(by_alias=True))
    # attach raw bytes hex-encoded per rollback (LIMITATO: solo se < 25MB)
    doc["_raw_b64_len"] = len(data)
    await db.import_jobs.insert_one(doc)
    await record_audit(action="importer.upload", tenant_id=user["tenant_id"],
                        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
                        entity_type="import_job", entity_id=job.id,
                        after={"filename": file.filename, "entity_type": entity_type,
                                "file_hash": file_hash, "rows": job.total_rows})
    # store bytes in a separate collection for rollback (avoid stuffing main doc)
    await db.import_job_blobs.insert_one({
        "_id": job.id, "tenant_id": user["tenant_id"], "data_b64": data.hex(),
    })
    return from_mongo(doc)


# =====================================================================
# 2) SET MAPPING + VALIDATE
# =====================================================================
class MappingBody(BaseModel):
    selected_sheet: Optional[str] = None
    header_row_index: int = 0
    mappings: List[ImportColumnMapping]


@router.post("/jobs/{jid}/map")
async def set_mapping(jid: str, body: MappingBody, request: Request,
                        user: dict = Depends(require_permission("pricelists.manage"))):
    db = get_db()
    job = await db.import_jobs.find_one({
        "_id": jid, "tenant_id": user["tenant_id"], "deleted_at": None,
    })
    if not job:
        raise HTTPException(404, "Job non trovato")
    if job.get("im_status") in ("published", "rolled_back", "cancelled"):
        raise HTTPException(400, f"Job in stato {job['im_status']}: non modificabile")

    # Load raw
    blob = await db.import_job_blobs.find_one({"_id": jid, "tenant_id": user["tenant_id"]})
    if not blob:
        raise HTTPException(500, "Blob dati non trovato")
    data = bytes.fromhex(blob["data_b64"])
    sheet = body.selected_sheet or job.get("selected_sheet")
    df = load_sheet(data, job["filename"], sheet)
    rows, mapping_errors = apply_mapping(df, [m.model_dump() for m in body.mappings])
    val_errors, dup = validate_rows(job["entity_type"], rows)
    all_errors = mapping_errors + val_errors
    preview = rows[:PREVIEW_LIMIT]
    patch = {
        "selected_sheet": sheet,
        "header_row_index": body.header_row_index,
        "mappings": [m.model_dump() for m in body.mappings],
        "validation_errors": all_errors[:1000],   # cap
        "duplicate_count": dup,
        "valid_rows": len(rows) - len([e for e in all_errors if e.get("severity") == "error"]),
        "preview_sample": preview,
        "total_rows": len(df),
        "im_status": "preview_ready" if not any(e.get("severity") == "error" for e in all_errors) else "validated",
        "updated_at": datetime.now(timezone.utc),
        "updated_by": user["id"],
    }
    await db.import_jobs.update_one({"_id": jid}, {"$set": patch})
    await record_audit(action="importer.map", tenant_id=user["tenant_id"],
                        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
                        entity_type="import_job", entity_id=jid,
                        after={"mappings_n": len(body.mappings), "errors_n": len(all_errors),
                                "valid_rows": patch["valid_rows"]})
    updated = await db.import_jobs.find_one({"_id": jid})
    return from_mongo(updated)


# =====================================================================
# 3) PREVIEW (già in preview_sample post-mapping)
# =====================================================================
@router.get("/jobs/{jid}/preview")
async def get_preview(jid: str, user: dict = Depends(require_permission("pricelists.view"))):
    db = get_db()
    job = await db.import_jobs.find_one({
        "_id": jid, "tenant_id": user["tenant_id"], "deleted_at": None,
    })
    if not job:
        raise HTTPException(404, "Job non trovato")
    return {
        "sheet_names": job.get("sheet_names"),
        "selected_sheet": job.get("selected_sheet"),
        "detected_headers": job.get("detected_headers"),
        "mappings": job.get("mappings") or [],
        "preview": job.get("preview_sample") or [],
        "total_rows": job.get("total_rows", 0),
        "valid_rows": job.get("valid_rows", 0),
        "duplicate_count": job.get("duplicate_count", 0),
        "errors": job.get("validation_errors") or [],
        "status": job.get("im_status"),
    }


# =====================================================================
# 4) PUBLISH
# =====================================================================
@router.post("/jobs/{jid}/publish")
async def publish_job(jid: str, request: Request,
                        user: dict = Depends(require_permission("pricelists.manage"))):
    db = get_db()
    job = await db.import_jobs.find_one({
        "_id": jid, "tenant_id": user["tenant_id"], "deleted_at": None,
    })
    if not job:
        raise HTTPException(404, "Job non trovato")
    if job.get("im_status") == "published":
        raise HTTPException(400, "Job già pubblicato")
    if any(e.get("severity") == "error" for e in job.get("validation_errors") or []):
        raise HTTPException(400, "Ci sono errori bloccanti — impossibile pubblicare")

    target_pl_id = job.get("target_pricelist_id")
    if not target_pl_id:
        raise HTTPException(400, "target_pricelist_id mancante")

    pl = await db.item_pricelists.find_one({
        "_id": target_pl_id, "tenant_id": user["tenant_id"], "deleted_at": None,
    })
    if not pl:
        raise HTTPException(404, "Listino target non trovato")

    # Snapshot pre-publish per rollback
    snapshot_entries = pl.get("entries") or []
    snapshot_version = pl.get("version", 1)
    await db.pricelist_import_snapshots.insert_one({
        "_id": f"snap-{jid}",
        "tenant_id": user["tenant_id"],
        "import_job_id": jid, "pricelist_id": target_pl_id,
        "entries_backup": snapshot_entries,
        "version_backup": snapshot_version,
        "created_at": datetime.now(timezone.utc),
    })

    # Ricomponi righe da mapping + valida di nuovo
    blob = await db.import_job_blobs.find_one({"_id": jid, "tenant_id": user["tenant_id"]})
    if not blob:
        raise HTTPException(500, "Blob dati non trovato")
    data = bytes.fromhex(blob["data_b64"])
    df = load_sheet(data, job["filename"], job.get("selected_sheet"))
    rows, _ = apply_mapping(df, job.get("mappings") or [])
    new_entries = rows_to_pricelist_entries(
        job["entity_type"], rows,
        supplier_id=job.get("supplier_id"),
        profile_system_id=job.get("profile_system_id"),
        default_color_id=job.get("color_id"),
    )

    # Modalità: append vs replace? V1: MERGE per code — se già presente aggiorna, altrimenti append
    merged = list(snapshot_entries)
    by_code = {e.get("code"): i for i, e in enumerate(merged) if e.get("code")}
    added = 0
    updated = 0
    for ne in new_entries:
        c = ne.get("code")
        if c and c in by_code:
            merged[by_code[c]] = {**merged[by_code[c]], **ne}
            updated += 1
        else:
            merged.append(ne)
            added += 1

    await db.item_pricelists.update_one({"_id": target_pl_id}, {"$set": {
        "entries": merged,
        "version": snapshot_version + 1,
        "updated_at": datetime.now(timezone.utc),
        "updated_by": user["id"],
    }})
    now = datetime.now(timezone.utc)
    await db.import_jobs.update_one({"_id": jid}, {"$set": {
        "im_status": "published",
        "published_at": now, "published_by": user["id"],
        "rollback_snapshot_key": f"snap-{jid}",
        "updated_at": now, "updated_by": user["id"],
    }})
    await record_audit(action="importer.publish", tenant_id=user["tenant_id"],
                        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
                        entity_type="import_job", entity_id=jid,
                        after={"pricelist_id": target_pl_id,
                                "added": added, "updated": updated,
                                "new_version": snapshot_version + 1})
    return {"ok": True, "added": added, "updated": updated,
             "pricelist_id": target_pl_id, "new_version": snapshot_version + 1}


# =====================================================================
# 5) ROLLBACK
# =====================================================================
@router.post("/jobs/{jid}/rollback")
async def rollback_job(jid: str, request: Request,
                         user: dict = Depends(require_permission("pricelists.manage"))):
    db = get_db()
    job = await db.import_jobs.find_one({
        "_id": jid, "tenant_id": user["tenant_id"], "deleted_at": None,
    })
    if not job:
        raise HTTPException(404, "Job non trovato")
    if job.get("im_status") != "published":
        raise HTTPException(400, "Rollback possibile solo su job pubblicato")

    snap_key = job.get("rollback_snapshot_key") or f"snap-{jid}"
    snap = await db.pricelist_import_snapshots.find_one({
        "_id": snap_key, "tenant_id": user["tenant_id"],
    })
    if not snap:
        raise HTTPException(404, "Snapshot rollback non trovato")

    await db.item_pricelists.update_one({"_id": snap["pricelist_id"]}, {"$set": {
        "entries": snap.get("entries_backup") or [],
        "version": snap.get("version_backup", 1),
        "updated_at": datetime.now(timezone.utc),
        "updated_by": user["id"],
    }})
    now = datetime.now(timezone.utc)
    await db.import_jobs.update_one({"_id": jid}, {"$set": {
        "im_status": "rolled_back",
        "rolled_back_at": now, "rolled_back_by": user["id"],
        "updated_at": now,
    }})
    await record_audit(action="importer.rollback", tenant_id=user["tenant_id"],
                        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
                        entity_type="import_job", entity_id=jid,
                        after={"pricelist_id": snap["pricelist_id"]})
    return {"ok": True, "restored_pricelist": snap["pricelist_id"]}


# =====================================================================
# 6) CANCEL (job non pubblicato)
# =====================================================================
@router.post("/jobs/{jid}/cancel")
async def cancel_job(jid: str, request: Request,
                       user: dict = Depends(require_permission("pricelists.manage"))):
    db = get_db()
    job = await db.import_jobs.find_one({
        "_id": jid, "tenant_id": user["tenant_id"], "deleted_at": None,
    })
    if not job:
        raise HTTPException(404, "Job non trovato")
    if job.get("im_status") == "published":
        raise HTTPException(400, "Non annullabile: usa rollback")
    await db.import_jobs.update_one({"_id": jid}, {"$set": {
        "im_status": "cancelled",
        "updated_at": datetime.now(timezone.utc), "updated_by": user["id"],
    }})
    await record_audit(action="importer.cancel", tenant_id=user["tenant_id"],
                        user_id=user["id"], user_email=user["email"], ip=get_client_ip(request),
                        entity_type="import_job", entity_id=jid)
    return {"ok": True}


# =====================================================================
# 7) LIST + DETAIL
# =====================================================================
@router.get("/jobs")
async def list_jobs(entity_type: Optional[str] = None,
                     status: Optional[str] = None,
                     limit: int = Query(100, le=500), skip: int = 0,
                     user: dict = Depends(require_permission("pricelists.view"))):
    db = get_db()
    q: Dict[str, Any] = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if entity_type: q["entity_type"] = entity_type
    if status: q["im_status"] = status
    total = await db.import_jobs.count_documents(q)
    docs = await db.import_jobs.find(q, {"preview_sample": 0}).sort([("created_at", -1)]).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": [from_mongo(d) for d in docs]}


@router.get("/jobs/{jid}")
async def get_job(jid: str, user: dict = Depends(require_permission("pricelists.view"))):
    db = get_db()
    job = await db.import_jobs.find_one({
        "_id": jid, "tenant_id": user["tenant_id"], "deleted_at": None,
    })
    if not job:
        raise HTTPException(404, "Job non trovato")
    return from_mongo(job)


# =====================================================================
# Meta — schema campi target per ogni entity_type (aiuto UI mapping)
# =====================================================================
TARGET_FIELDS_BY_ENTITY = {
    "profile": [
        {"code": "code", "label": "Codice articolo", "required": True},
        {"code": "unit_price", "label": "Prezzo unitario (€/m)", "required": True, "transform": "num"},
        {"code": "unit", "label": "Unità (linear_m/piece)", "default": "linear_m"},
        {"code": "color_id", "label": "ID colore (opz.)"},
        {"code": "min_billable_qty", "label": "Minimo fatturabile", "transform": "num"},
        {"code": "notes", "label": "Note"},
    ],
    "glass_type": [
        {"code": "code", "label": "Codice vetro", "required": True},
        {"code": "unit_price", "label": "Prezzo €/m²", "required": True, "transform": "num"},
        {"code": "unit", "label": "Unità", "default": "sqm"},
        {"code": "min_billable_qty", "label": "Minimo fatturabile m²", "transform": "num"},
    ],
    "hardware_kit": [
        {"code": "code", "label": "Codice kit", "required": True},
        {"code": "unit_price", "label": "Prezzo €/kit", "required": True, "transform": "num"},
        {"code": "unit", "label": "Unità", "default": "piece"},
    ],
    "accessory": [
        {"code": "code", "label": "Codice", "required": True},
        {"code": "unit_price", "label": "Prezzo", "required": True, "transform": "num"},
        {"code": "unit", "label": "Unità", "default": "piece"},
    ],
    "labor": [
        {"code": "code", "label": "Codice lavorazione", "required": True},
        {"code": "unit_price", "label": "Costo/prezzo", "required": True, "transform": "num"},
        {"code": "unit", "label": "Unità (h/pz)", "default": "piece"},
    ],
    "reinforcement": [
        {"code": "code", "label": "Codice rinforzo", "required": True},
        {"code": "unit_price", "label": "€/m", "required": True, "transform": "num"},
        {"code": "unit", "label": "Unità", "default": "linear_m"},
    ],
    "glazing_bead": [
        {"code": "code", "label": "Codice fermavetro", "required": True},
        {"code": "unit_price", "label": "€/m", "required": True, "transform": "num"},
        {"code": "unit", "label": "Unità", "default": "linear_m"},
    ],
    "price_matrix": [
        {"code": "code", "label": "Codice matrice", "required": True},
        {"code": "unit_price", "label": "Prezzo cella", "required": True, "transform": "num"},
    ],
    "surcharge": [
        {"code": "code", "label": "Codice maggiorazione", "required": True},
        {"code": "unit_price", "label": "Valore", "required": True, "transform": "num"},
    ],
    "min_billable": [
        {"code": "code", "label": "Codice articolo", "required": True},
        {"code": "min_billable_qty", "label": "Minimo fatturabile", "required": True, "transform": "num"},
    ],
    "component_association": [
        {"code": "code", "label": "Codice principale", "required": True},
        {"code": "notes", "label": "Note associazione"},
    ],
}


@router.get("/schema/{entity_type}")
async def get_target_schema(entity_type: str,
                              user: dict = Depends(require_permission("pricelists.view"))):
    if entity_type not in TARGET_FIELDS_BY_ENTITY:
        raise HTTPException(404, f"Schema per '{entity_type}' non definito")
    return {"entity_type": entity_type, "fields": TARGET_FIELDS_BY_ENTITY[entity_type]}
