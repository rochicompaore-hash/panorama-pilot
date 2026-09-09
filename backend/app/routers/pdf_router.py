"""PDF templates, clauses, and quote PDF generation (M3.3.2)."""
from __future__ import annotations
import base64
import io
from datetime import datetime, timezone
from typing import Optional, List, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Header, Response
from fastapi.responses import StreamingResponse
from app.db import get_db
from app.deps import require_permission, get_client_ip, get_permission_keys_for_user
from app.models import new_id
from app.models_pdf import (
    Clause, ClauseCreate, ClauseUpdate,
    QuoteTemplate, QuoteTemplateCreate, QuoteTemplateUpdate,
    QuotePdf, GeneratePdfRequest, InvalidatePdfRequest,
    PdfValidationError, PdfGenerationResult,
    PaymentTermsSchema, PaymentInstallment,
    TemplateStyle, TemplateSection,
)
from app.mongo_utils import to_mongo, from_mongo
from app.services.audit import record_audit
from app.services.timeline import record_activity
from app.services.concurrency import update_with_version, get_if_match_version, user_has_permission
from app.services.pdf_renderer import (
    build_snapshot, render_quote_pdf, compute_snapshot_hash, compute_pdf_hash,
    validate_quote_for_definitive, safe_filename,
)

router = APIRouter(tags=["pdf"])


# =========================================================
# CLAUSES
# =========================================================
@router.get("/general-terms/current")
async def general_terms_current(user: dict = Depends(require_permission("quotes.view"))):
    """Risorsa canonica GENERAL_TERMS_VERSION corrente + summary derivato (msg 782 §3, §7)."""
    from app.services.general_terms_canonical import get_canonical
    from app.services.general_terms import build_summary
    return {"canonical": get_canonical(), "summary": build_summary()}


@router.get("/general-terms/{version}")
async def general_terms_by_version(version: str, user: dict = Depends(require_permission("quotes.view"))):
    from app.services.general_terms_canonical import get_canonical
    try:
        return get_canonical(version)
    except KeyError:
        raise HTTPException(404, f"GENERAL_TERMS_VERSION sconosciuta: {version}")



@router.get("/clauses")
async def list_clauses(
    category: Optional[str] = None, active: Optional[bool] = None,
    user: dict = Depends(require_permission("quotes.view")),
):
    db = get_db()
    q: dict = {"tenant_id": user["tenant_id"], "deleted_at": None}
    if category: q["category"] = category
    if active is not None: q["active"] = active
    docs = await db.clauses.find(q).sort([("category", 1), ("order_index", 1)]).to_list(500)
    return {"items": [from_mongo(d) for d in docs]}


@router.get("/clauses/{cid}")
async def get_clause(cid: str, user: dict = Depends(require_permission("quotes.view"))):
    db = get_db()
    d = await db.clauses.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not d: raise HTTPException(status_code=404, detail="Clausola non trovata")
    return from_mongo(d)


@router.post("/clauses")
async def create_clause(body: ClauseCreate, request: Request, user: dict = Depends(require_permission("quotes.manage_clauses"))):
    db = get_db()
    if await db.clauses.find_one({"tenant_id": user["tenant_id"], "code": body.code, "deleted_at": None}):
        raise HTTPException(status_code=400, detail="Codice clausola già esistente")
    c = Clause(id=new_id(), tenant_id=user["tenant_id"], **body.model_dump(),
               created_by=user["id"], updated_by=user["id"])
    await db.clauses.insert_one(to_mongo(c.model_dump(by_alias=True)))
    await record_audit(action="clauses.create", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="clause", entity_id=c.id, after=body.model_dump())
    return from_mongo(await db.clauses.find_one({"_id": c.id}))


@router.patch("/clauses/{cid}")
async def update_clause(
    cid: str, body: ClauseUpdate, request: Request,
    expected_version: Optional[int] = Depends(get_if_match_version),
    user: dict = Depends(require_permission("quotes.manage_clauses")),
):
    payload = body.model_dump(exclude_unset=True)
    db = get_db()
    # Save previous version to append-only history (models change tracker)
    prev = await db.clauses.find_one({"_id": cid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if prev:
        await db.clause_versions.insert_one({
            "_id": new_id(), "tenant_id": user["tenant_id"], "clause_id": cid,
            "version": prev.get("version", 1),
            "snapshot": {k: v for k, v in prev.items() if k not in ("_id",)},
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "archived_by": user["id"],
        })
    updated = await update_with_version(
        collection="clauses", entity_id=cid, tenant_id=user["tenant_id"],
        entity_type="clause", expected_version=expected_version,
        set_fields=payload, user=user, request=request,
    )
    await record_audit(action="clauses.update", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="clause", entity_id=cid, after=payload)
    return updated


@router.delete("/clauses/{cid}")
async def delete_clause(cid: str, request: Request, user: dict = Depends(require_permission("quotes.manage_clauses"))):
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    r = await db.clauses.update_one({"_id": cid, "tenant_id": user["tenant_id"]}, {"$set": {"deleted_at": now}, "$inc": {"version": 1}})
    if r.modified_count == 0: raise HTTPException(status_code=404, detail="Clausola non trovata")
    return {"ok": True}


# =========================================================
# TEMPLATES
# =========================================================
@router.get("/quote-templates")
async def list_templates(user: dict = Depends(require_permission("quotes.view"))):
    db = get_db()
    docs = await db.quote_templates.find({"tenant_id": user["tenant_id"], "deleted_at": None}).to_list(200)
    return {"items": [from_mongo(d) for d in docs]}


@router.get("/quote-templates/{tid}")
async def get_template(tid: str, user: dict = Depends(require_permission("quotes.view"))):
    db = get_db()
    d = await db.quote_templates.find_one({"_id": tid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not d: raise HTTPException(status_code=404, detail="Template non trovato")
    return from_mongo(d)


@router.post("/quote-templates")
async def create_template(body: QuoteTemplateCreate, request: Request, user: dict = Depends(require_permission("quotes.manage_templates"))):
    db = get_db()
    if await db.quote_templates.find_one({"tenant_id": user["tenant_id"], "code": body.code, "deleted_at": None}):
        raise HTTPException(status_code=400, detail="Codice template già esistente")
    t = QuoteTemplate(id=new_id(), tenant_id=user["tenant_id"], **body.model_dump(),
                      created_by=user["id"], updated_by=user["id"],
                      activated_at=datetime.now(timezone.utc))
    await db.quote_templates.insert_one(to_mongo(t.model_dump(by_alias=True)))
    if t.is_default:
        await db.quote_templates.update_many({"tenant_id": user["tenant_id"], "_id": {"$ne": t.id}}, {"$set": {"is_default": False}})
    await record_audit(action="quote_templates.create", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="quote_template", entity_id=t.id, after=body.model_dump())
    return from_mongo(await db.quote_templates.find_one({"_id": t.id}))


@router.patch("/quote-templates/{tid}")
async def update_template(
    tid: str, body: QuoteTemplateUpdate, request: Request,
    expected_version: Optional[int] = Depends(get_if_match_version),
    user: dict = Depends(require_permission("quotes.manage_templates")),
):
    payload = body.model_dump(exclude_unset=True)
    db = get_db()
    # Save previous version for immutability
    prev = await db.quote_templates.find_one({"_id": tid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if prev:
        await db.quote_template_versions.insert_one({
            "_id": new_id(), "tenant_id": user["tenant_id"], "template_id": tid,
            "version": prev.get("version", 1),
            "snapshot": {k: v for k, v in prev.items() if k not in ("_id",)},
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "archived_by": user["id"],
        })
    updated = await update_with_version(
        collection="quote_templates", entity_id=tid, tenant_id=user["tenant_id"],
        entity_type="quote_template", expected_version=expected_version,
        set_fields=payload, user=user, request=request,
    )
    if body.is_default:
        await db.quote_templates.update_many({"tenant_id": user["tenant_id"], "_id": {"$ne": tid}}, {"$set": {"is_default": False}})
    await record_audit(action="quote_templates.update", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="quote_template", entity_id=tid, after=payload)
    return updated


# =========================================================
# PDF GENERATION
# =========================================================
async def _resolve_template(tenant_id: str, template_id: Optional[str]) -> Optional[dict]:
    db = get_db()
    q = {"tenant_id": tenant_id, "deleted_at": None}
    if template_id:
        q["_id"] = template_id
    else:
        q["is_default"] = True
    t = await db.quote_templates.find_one(q)
    if not t and not template_id:
        t = await db.quote_templates.find_one({"tenant_id": tenant_id, "deleted_at": None})
    return from_mongo(t) if t else None


async def _resolve_clauses(tenant_id: str, template: dict, extra_codes: Optional[List[str]] = None,
                           exclude_codes: Optional[List[str]] = None) -> List[dict]:
    db = get_db()
    codes = set(template.get("mandatory_clause_codes") or []) | set(template.get("optional_clause_codes") or [])
    if extra_codes: codes |= set(extra_codes)
    if exclude_codes:
        # Cannot exclude mandatory ones
        mand = set(template.get("mandatory_clause_codes") or [])
        codes -= (set(exclude_codes) - mand)
    if not codes:
        return []
    docs = await db.clauses.find({"tenant_id": tenant_id, "code": {"$in": list(codes)}, "deleted_at": None, "active": True}).to_list(200)
    return [from_mongo(d) for d in docs]


async def _resolve_company(tenant_id: str) -> dict:
    db = get_db()
    c = await db.companies.find_one({"_id": tenant_id})
    return from_mongo(c) if c else {}


async def _resolve_quote_full(tenant_id: str, quote_id: str) -> Optional[dict]:
    db = get_db()
    q = await db.quotes.find_one({"_id": quote_id, "tenant_id": tenant_id, "deleted_at": None})
    if not q: return None
    q = from_mongo(q)
    # Attach customer snapshot
    if q.get("customer_id"):
        cust = await db.customers.find_one({"_id": q["customer_id"]})
        if cust: q["customer_snapshot"] = {
            "name": cust.get("name") or cust.get("display_name") or cust.get("company_name")
                    or f"{cust.get('first_name') or ''} {cust.get('last_name') or ''}".strip() or None,
            "vat_number": cust.get("vat_number"),
            "tax_code": cust.get("tax_code"), "email": cust.get("email"),
            "phone": cust.get("phone") or cust.get("mobile"),
        }
    elif q.get("lead_id"):
        lead = await db.leads.find_one({"_id": q["lead_id"]})
        if lead: q["customer_snapshot"] = {
            "name": lead.get("name") or f"{lead.get('first_name','')} {lead.get('last_name','')}".strip(),
            "email": lead.get("email"), "phone": lead.get("phone"),
        }
    # Site (cantiere) full data — PDF V2 header
    if q.get("site_id"):
        site = await db.sites.find_one({"_id": q["site_id"]})
        if site:
            q["site_snapshot"] = {k: site.get(k) for k in ("name", "address", "street_number", "postal_code", "city", "province", "floor", "has_elevator", "site_contact_phone")}
    # Sales rep
    if q.get("sales_rep_id"):
        u = await db.users.find_one({"_id": q["sales_rep_id"]})
        if u: q["sales_rep_snapshot"] = {
            "name": f"{u.get('first_name','')} {u.get('last_name','')}".strip() or u.get("email"),
            "email": u.get("email"), "phone": u.get("phone"),
        }
    return q


@router.get("/quotes/{qid}/pdfs")
async def list_quote_pdfs(qid: str, user: dict = Depends(require_permission("quotes.view"))):
    db = get_db()
    # Project out heavy fields — return metadata only
    docs = await db.quote_pdfs.find(
        {"quote_id": qid, "tenant_id": user["tenant_id"]},
        {"pdf_base64": 0, "snapshot": 0},
    ).sort("generated_at", -1).to_list(50)
    items = []
    for d in docs:
        m = from_mongo(d)
        m.pop("_id", None)  # from_mongo maps _id→id; drop the residual _id
        items.append(m)
    return {"items": items}


@router.post("/quotes/{qid}/pdf/preview")
async def preview_pdf(
    qid: str, body: GeneratePdfRequest, request: Request,
    user: dict = Depends(require_permission("quotes.preview_pdf")),
):
    """Draft/preview PDF with BOZZA watermark. Does NOT persist a definitive record.
    Persists a `preview` record for traceability."""
    return await _generate_pdf(qid, body, request, user, is_preview=True)


@router.post("/quotes/{qid}/pdf/generate")
async def generate_definitive_pdf(
    qid: str, body: GeneratePdfRequest, request: Request,
    user: dict = Depends(require_permission("quotes.generate_pdf")),
):
    """Definitive PDF emission. Validates + freezes snapshot + idempotent per snapshot_hash."""
    return await _generate_pdf(qid, body, request, user, is_preview=False)


async def _generate_pdf(qid: str, body: GeneratePdfRequest, request: Request, user: dict, is_preview: bool):
    db = get_db()
    quote = await _resolve_quote_full(user["tenant_id"], qid)
    if not quote: raise HTTPException(status_code=404, detail="Preventivo non trovato")

    template = await _resolve_template(user["tenant_id"], body.template_id)
    if not template:
        raise HTTPException(status_code=400, detail="Nessun template configurato. Crearne uno prima di generare il PDF.")

    company = await _resolve_company(user["tenant_id"])

    # Validation gate (definitive only)
    validation_errors: List[dict] = []
    if not is_preview:
        validation_errors = validate_quote_for_definitive(quote, company, template)
        if validation_errors and not body.force:
            raise HTTPException(status_code=400, detail={
                "error": "validation_failed",
                "message": "Il preventivo non è pronto per l'emissione definitiva. Correggere i problemi elencati.",
                "errors": validation_errors,
            })

    # Resolve clauses
    clauses = await _resolve_clauses(user["tenant_id"], template, body.include_clause_codes, body.exclude_clause_codes)

    # Payment terms: quote override → template default
    if body.payment_terms_override:
        pt = body.payment_terms_override.model_dump()
    elif quote.get("payment_terms_schema"):
        pt = quote["payment_terms_schema"]
    else:
        pt = (template.get("default_payment_terms") or {})

    # Condizioni Generali — In sintesi (versionate; congelate su ACCEPTED)
    from app.services.general_terms import resolve_general_terms_for_quote
    general_terms = await resolve_general_terms_for_quote(db, quote)

    # Build snapshot
    snapshot = build_snapshot(
        quote=quote, company=company, template=template, clauses=clauses,
        payment_terms=pt, kind="preview" if is_preview else "definitive", general_terms=general_terms,
    )
    snapshot_hash = compute_snapshot_hash(snapshot)

    # Idempotency: check existing PDFs
    watermark = None
    kind = "preview" if is_preview else "definitive"
    if is_preview:
        watermark = "BOZZA"
    else:
        # If quote has newer revisions, this one may be superseded already
        if not quote.get("is_current", True):
            watermark = "SUPERATO"

    # Check for existing definitive with same snapshot_hash
    if not is_preview:
        existing = await db.quote_pdfs.find_one({
            "quote_id": qid, "tenant_id": user["tenant_id"], "kind": "definitive",
            "snapshot_hash": snapshot_hash, "invalidated_at": None,
        })
        if existing:
            # Idempotent: return existing
            return {
                "id": existing["_id"], "kind": existing["kind"],
                "filename": existing["filename"], "snapshot_hash": existing["snapshot_hash"],
                "pdf_hash": existing["pdf_hash"], "size_bytes": existing["size_bytes"],
                "generated_at": existing["generated_at"], "validation_errors": [],
                "idempotent_hit": True,
            }

    # Render
    try:
        pdf_bytes = render_quote_pdf(snapshot, watermark=watermark)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore rendering PDF: {e}")
    pdf_hash = compute_pdf_hash(pdf_bytes)

    # Filename
    cust_label = (snapshot.get("quote", {}).get("customer") or {}).get("name") or "Cliente"
    # Filename — dedupe if quote number already contains revision label
    quote_num = quote.get("number") or qid
    rev_label = quote.get("revision_label") or f"R{int(quote.get('revision', 0)):02d}"
    if rev_label and rev_label in quote_num:
        filename_parts = ("Preventivo",
                          (snapshot.get("company", {}).get("commercial_name") or snapshot.get("company", {}).get("name") or "Azienda"),
                          quote_num, cust_label)
    else:
        filename_parts = ("Preventivo",
                          (snapshot.get("company", {}).get("commercial_name") or snapshot.get("company", {}).get("name") or "Azienda"),
                          quote_num, rev_label, cust_label)
    filename = safe_filename(*filename_parts, ext="pdf")

    now = datetime.now(timezone.utc)
    pdf_id = new_id()
    # Try to store in object storage; fall back to inline base64 on failure
    from app.services import object_storage
    storage_key = None
    storage_provider = "inline"
    pdf_base64_field = None
    try:
        if object_storage.is_available():
            rev_label = quote.get("revision_label") or f"R{int(quote.get('revision', 0)):02d}"
            storage_key = object_storage.build_pdf_path(user["tenant_id"], qid, rev_label, pdf_id)
            object_storage.put_pdf(storage_key, pdf_bytes)
            storage_provider = "emergent"
        else:
            pdf_base64_field = base64.b64encode(pdf_bytes).decode("ascii")
    except Exception as ex:
        # Fallback to inline
        storage_key = None
        storage_provider = "inline"
        pdf_base64_field = base64.b64encode(pdf_bytes).decode("ascii")

    pdf_doc = {
        "_id": pdf_id,
        "tenant_id": user["tenant_id"],
        "quote_id": qid,
        "quote_number": quote.get("number"),
        "quote_revision": quote.get("revision_label") or f"R{int(quote.get('revision',0)):02d}",
        "quote_version_snapshot": quote.get("version", 1),
        "template_id": template.get("id") or template.get("_id"),
        "template_version": template.get("version", 1),
        "kind": kind,
        "watermark": watermark,
        "snapshot_hash": snapshot_hash,
        "pdf_hash": pdf_hash,
        "filename": filename,
        "storage_provider": storage_provider,
        "storage_key": storage_key,
        "size_bytes": len(pdf_bytes),
        "mime_type": "application/pdf",
        "snapshot": snapshot,
        "pdf_base64": pdf_base64_field,  # None when in object storage
        "generated_by": user["id"],
        "generated_at": now.isoformat(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "version": 1,
        "deleted_at": None,
    }
    try:
        await db.quote_pdfs.insert_one(pdf_doc)
    except Exception as ex:
        # Race with parallel emission — fetch the winning doc
        if "duplicate key" in str(ex).lower() or "E11000" in str(ex):
            winner = await db.quote_pdfs.find_one({
                "tenant_id": user["tenant_id"], "quote_id": qid,
                "snapshot_hash": snapshot_hash, "kind": kind, "invalidated_at": None,
            })
            if winner:
                return {
                    "id": winner["_id"], "kind": winner["kind"],
                    "filename": winner["filename"], "snapshot_hash": winner["snapshot_hash"],
                    "pdf_hash": winner["pdf_hash"], "size_bytes": winner["size_bytes"],
                    "generated_at": winner["generated_at"], "validation_errors": [],
                    "idempotent_hit": True,
                }
        raise

    # For definitive: update quote to reference latest_pdf_id + timeline
    if not is_preview:
        await db.quotes.update_one(
            {"_id": qid, "tenant_id": user["tenant_id"]},
            {"$set": {"latest_pdf_id": pdf_doc["_id"], "latest_pdf_hash": pdf_hash,
                      "latest_pdf_at": now.isoformat(), "updated_at": now.isoformat(),
                      "updated_by": user["id"]},
             "$inc": {"version": 1}},
        )
        await record_activity(
            tenant_id=user["tenant_id"], type="pdf_generated",
            subject=f"PDF definitivo emesso: {quote.get('number')}",
            quote_id=qid, user_id=user["id"], user_email=user["email"],
            meta={"pdf_id": pdf_doc["_id"], "hash": pdf_hash, "filename": filename},
        )

    await record_audit(
        action=f"quote_pdfs.{'preview' if is_preview else 'generate'}",
        tenant_id=user["tenant_id"], user_id=user["id"], user_email=user["email"],
        ip=get_client_ip(request), entity_type="quote_pdf", entity_id=pdf_doc["_id"],
        after={"quote_id": qid, "snapshot_hash": snapshot_hash, "pdf_hash": pdf_hash, "kind": kind},
    )

    return {
        "id": pdf_doc["_id"], "kind": kind, "filename": filename,
        "snapshot_hash": snapshot_hash, "pdf_hash": pdf_hash,
        "size_bytes": pdf_doc["size_bytes"], "generated_at": now.isoformat(),
        "validation_errors": validation_errors,
    }


@router.get("/quote-pdfs/{pid}/snapshot")
async def get_pdf_snapshot(pid: str, user: dict = Depends(require_permission("quotes.view"))):
    """Snapshot immutabile del PDF (audit interno: verifica assenza dati interni, parità visual)."""
    d = await get_db().quote_pdfs.find_one({"_id": pid, "tenant_id": user["tenant_id"]}, {"pdf_base64": 0})
    if not d:
        raise HTTPException(status_code=404, detail="PDF non trovato")
    return {"id": d["_id"], "kind": d.get("kind"), "snapshot_hash": d.get("snapshot_hash"), "snapshot": d.get("snapshot")}


@router.get("/quote-pdfs/{pid}/download")
async def download_pdf(pid: str, user: dict = Depends(require_permission("quotes.download_pdf"))):
    db = get_db()
    d = await db.quote_pdfs.find_one({"_id": pid, "tenant_id": user["tenant_id"]})
    if not d: raise HTTPException(status_code=404, detail="PDF non trovato")
    pdf_bytes = await _fetch_pdf_bytes(d)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{d.get("filename", "preventivo.pdf")}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def _fetch_pdf_bytes(d: dict) -> bytes:
    """Resolve PDF bytes: object storage first, inline base64 fallback."""
    from app.services import object_storage
    if d.get("storage_provider") == "emergent" and d.get("storage_key"):
        try:
            return object_storage.get_pdf(d["storage_key"])
        except Exception as ex:
            # Fallback if storage temporarily unavailable
            if d.get("pdf_base64"):
                return base64.b64decode(d["pdf_base64"])
            raise HTTPException(status_code=503, detail=f"Storage non disponibile: {ex}")
    b64 = d.get("pdf_base64")
    if not b64:
        raise HTTPException(status_code=410, detail="Contenuto PDF non più archiviato")
    return base64.b64decode(b64)


@router.get("/quote-pdfs/{pid}")
async def get_pdf_meta(pid: str, user: dict = Depends(require_permission("quotes.view"))):
    db = get_db()
    d = await db.quote_pdfs.find_one({"_id": pid, "tenant_id": user["tenant_id"]})
    if not d: raise HTTPException(status_code=404, detail="PDF non trovato")
    meta = from_mongo(d)
    meta.pop("pdf_base64", None)
    meta.pop("snapshot", None)  # heavy — separate endpoint if needed
    return meta


@router.post("/quote-pdfs/{pid}/invalidate")
async def invalidate_pdf(
    pid: str, body: InvalidatePdfRequest, request: Request,
    user: dict = Depends(require_permission("quotes.invalidate_pdf")),
):
    db = get_db()
    if not body.reason or not body.reason.strip():
        raise HTTPException(status_code=400, detail="Motivazione obbligatoria")
    d = await db.quote_pdfs.find_one({"_id": pid, "tenant_id": user["tenant_id"]})
    if not d: raise HTTPException(status_code=404, detail="PDF non trovato")
    if d.get("invalidated_at"):
        raise HTTPException(status_code=400, detail="PDF già annullato")
    now = datetime.now(timezone.utc).isoformat()
    await db.quote_pdfs.update_one({"_id": pid}, {"$set": {"invalidated_at": now, "invalidated_by": user["id"], "invalidation_reason": body.reason, "kind": "cancelled"}})
    await record_audit(action="quote_pdfs.invalidate", tenant_id=user["tenant_id"], user_id=user["id"],
                       user_email=user["email"], ip=get_client_ip(request),
                       entity_type="quote_pdf", entity_id=pid, after={"reason": body.reason})
    return {"ok": True}


# =========================================================
# SCAN SCRIPT (M3.3.2 bonus): flag quotes affected by pre-fix pricing bug
# =========================================================
@router.get("/quotes/scan/pricing-scope-bug")
async def scan_pricing_bug(user: dict = Depends(require_permission("quotes.view"))):
    """Read-only scan for quotes possibly affected by the pre-fix double-multiplication
    of fixed rules (COLOR_FILM_DIFF_FIXED, ROLLER_MOTOR_MECHANICAL, ROLLER_MOTOR_RADIO)
    with quantity > 1. Returns a report grouping by status. Does NOT modify data.
    """
    db = get_db()
    FIX_CODES = {"COLOR_FILM_DIFF_FIXED", "ROLLER_MOTOR_MECHANICAL", "ROLLER_MOTOR_RADIO"}
    quotes = await db.quotes.find({"tenant_id": user["tenant_id"], "deleted_at": None}).to_list(5000)
    report = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "total_scanned": len(quotes),
        "affected_by_status": {"draft": [], "sent": [], "accepted": [], "converted": [], "signed": [], "other": []},
        "total_diff_estimate": 0.0,
    }
    for q in quotes:
        lines = q.get("lines") or []
        cand = []
        for l in lines:
            qty = float(l.get("quantity") or 0)
            if qty <= 1:
                continue
            cfg = l.get("product_config") or {}
            hits = []
            if cfg.get("color_kind") == "film_diff":
                hits.append("COLOR_FILM_DIFF_FIXED")
            if cfg.get("motorization") == "mechanical":
                hits.append("ROLLER_MOTOR_MECHANICAL")
            if cfg.get("motorization") == "radio":
                hits.append("ROLLER_MOTOR_RADIO")
            if hits:
                # Estimated over-charge: fixed_amount × (qty - 1) per hit rule
                over_charge = 0.0
                if "COLOR_FILM_DIFF_FIXED" in hits: over_charge += 150.0 * (qty - 1)
                if "ROLLER_MOTOR_MECHANICAL" in hits: over_charge += 180.0 * (qty - 1)
                if "ROLLER_MOTOR_RADIO" in hits: over_charge += 260.0 * (qty - 1)
                cand.append({
                    "line_id": l.get("id"), "quantity": qty, "rules_hit": hits,
                    "over_charge_estimate": over_charge,
                    "description": l.get("description"),
                })
        if cand:
            status = q.get("quote_status", "other")
            key = status if status in report["affected_by_status"] else "other"
            report["affected_by_status"][key].append({
                "quote_id": q["_id"], "number": q.get("number"),
                "revision": q.get("revision_label"), "status": status,
                "created_at": q.get("created_at"),
                "customer_id": q.get("customer_id") or q.get("lead_id"),
                "total": q.get("total"),
                "lines_affected": cand,
                "total_over_charge_estimate": sum(c["over_charge_estimate"] for c in cand),
                "pdf_emitted": bool(q.get("latest_pdf_id")),
                "contract_id": q.get("contract_id"),
                "recommended_action": (
                    "Correzione controllata (auto-recompute allowed)" if status in ("draft", "to_complete") else
                    "Creare nuova revisione con audit"
                ),
            })
            report["total_diff_estimate"] += sum(c["over_charge_estimate"] for c in cand)
    report["total_diff_estimate"] = round(report["total_diff_estimate"], 2)
    return report
