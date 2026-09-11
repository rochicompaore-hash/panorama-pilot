"""Workflow orchestrator + production release check + timeline logger.

Fornisce funzioni di alto livello per le transizioni cross-modulo:
  - on_quote_accepted → genera Contract (idempotente)
  - on_contract_signed → crea Survey to_schedule (idempotente)
  - on_survey_completed → helper per creare Abaco (draft) da Survey
  - on_technical_schedule_signed → esegue production_release_check + crea ExecutiveOrder
  - log_timeline_event → centralized logger di TimelineEvent

Ogni funzione è idempotente e safe da chiamare più volte.
"""
from __future__ import annotations
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.db import get_db
from app.mongo_utils import to_mongo, from_mongo
from app.models import new_id, utcnow
from app.models_workflow import (
    TimelineEvent, TechnicalSchedule, TechnicalScheduleItem,
    ExecutiveOrder, ExecutiveOrderLine, ProductionReleaseCheckResult,
)

logger = logging.getLogger("infissi.workflow")


# ---------------------------------------------------------------------
# TIMELINE
# ---------------------------------------------------------------------
async def log_timeline_event(
    *,
    tenant_id: str,
    domain: str,
    event_type: str,
    ref_id: Optional[str] = None,
    quote_id: Optional[str] = None,
    contract_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    survey_id: Optional[str] = None,
    technical_schedule_id: Optional[str] = None,
    executive_order_id: Optional[str] = None,
    old_status: Optional[str] = None,
    new_status: Optional[str] = None,
    actor_id: Optional[str] = None,
    actor_email: Optional[str] = None,
    source: str = "system",
    is_customer_visible: bool = False,
    customer_label: Optional[str] = None,
    customer_stage: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    ip_hash: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Optional[str]:
    """Registra un evento nella timeline unificata. Idempotente su (domain, event_type, ref_id, new_status)."""
    db = get_db()
    dedup_key = f"{tenant_id}:{domain}:{event_type}:{ref_id or ''}:{new_status or ''}:{customer_id or ''}"
    dedup_hash = hashlib.sha256(dedup_key.encode()).hexdigest()[:24]
    existing = await db.timeline_events.find_one({
        "tenant_id": tenant_id, "dedup_hash": dedup_hash, "deleted_at": None,
    })
    if existing:
        return existing["_id"]
    ev = TimelineEvent(
        tenant_id=tenant_id,
        domain=domain, event_type=event_type, ref_id=ref_id,
        quote_id=quote_id, contract_id=contract_id, customer_id=customer_id,
        survey_id=survey_id, technical_schedule_id=technical_schedule_id,
        executive_order_id=executive_order_id,
        old_status=old_status, new_status=new_status,
        actor_id=actor_id, actor_email=actor_email, source=source,
        is_customer_visible=is_customer_visible,
        customer_label=customer_label, customer_stage=customer_stage,
        ip_hash=ip_hash, request_id=request_id,
        payload=payload or {},
    )
    doc = to_mongo(ev.model_dump(by_alias=True))
    doc["dedup_hash"] = dedup_hash
    await db.timeline_events.insert_one(doc)
    return ev.id


# ---------------------------------------------------------------------
# PRODUCTION RELEASE CHECK
# ---------------------------------------------------------------------
async def production_release_check(*, tenant_id: str, contract_id: str, checked_by: str) -> ProductionReleaseCheckResult:
    """Controllo centrale: verifica che TUTTE le precondizioni siano soddisfatte per
    rilasciare in produzione. Ritorna un oggetto strutturato non un booleano.
    """
    db = get_db()
    blocking: List[str] = []
    warnings: List[str] = []
    src = {}

    contract = await db.contracts.find_one({"_id": contract_id, "tenant_id": tenant_id, "deleted_at": None})
    if not contract:
        return ProductionReleaseCheckResult(
            eligible=False,
            blocking_reasons=["Contratto non trovato"],
            warnings=[], checked_at=utcnow(), checked_by=checked_by,
            source_versions={}, contract_id=contract_id,
        )
    src["contract_version"] = contract.get("version", 1)
    contract_status = contract.get("contract_status")
    if contract_status != "signed":
        blocking.append(f"Contratto non firmato (stato: {contract_status})")

    # Acconto (se richiesto in payment_terms). Non blocca se non definito.
    payment_terms = contract.get("quote_snapshot", {}).get("payment_terms") or ""
    if isinstance(payment_terms, dict):   # snapshot contrattuale V1 (msg 803): {code,label,schedule}
        payment_terms = " ".join(str(payment_terms.get(k) or "") for k in ("code", "label"))
    if "50%" in payment_terms.lower() or "acconto" in payment_terms.lower():
        # Verifica pagamento acconto in `payments`
        acconto_paid = await db.payments.count_documents({
            "tenant_id": tenant_id, "contract_id": contract_id,
            "payment_status": {"$in": ["confirmed", "settled"]},
            "deleted_at": None,
        })
        if acconto_paid == 0:
            warnings.append("Acconto non risulta ancora incassato (verificare)")

    # Survey
    survey = await db.surveys.find_one({
        "tenant_id": tenant_id, "contract_id": contract_id,
        "deleted_at": None,
    })
    survey_status = None
    survey_id = None
    if survey:
        survey_status = survey.get("survey_status")
        survey_id = survey["_id"]
        src["survey_version"] = survey.get("version", 1)
        if survey_status not in ("approved", "completed"):
            blocking.append(f"Rilievo non completato/validato (stato: {survey_status})")
    else:
        blocking.append("Rilievo tecnico non ancora creato")

    # Technical schedule (abaco)
    ts = await db.technical_schedules.find_one({
        "tenant_id": tenant_id, "contract_id": contract_id,
        "is_current": True, "deleted_at": None,
    })
    ts_status = None
    ts_id = None
    if ts:
        ts_status = ts.get("ts_status")
        ts_id = ts["_id"]
        src["technical_schedule_version"] = ts.get("version", 1)
        if ts_status not in ("signed", "released_to_production"):
            blocking.append(f"Abaco tecnico non firmato (stato: {ts_status})")
        # Errori bloccanti su singoli item
        item_errors = 0
        for it in ts.get("items") or []:
            if it.get("blocking_errors"):
                item_errors += len(it.get("blocking_errors"))
        if item_errors > 0:
            blocking.append(f"Abaco contiene {item_errors} errori tecnici bloccanti sui vani")
    else:
        blocking.append("Abaco tecnico non ancora creato")

    # Change requests aperte (varianti pending)
    open_changes = 0
    if ts_id:
        open_changes = await db.variances.count_documents({
            "tenant_id": tenant_id, "contract_id": contract_id,
            "variance_status": {"$in": ["draft", "sent", "customer_viewed"]},
            "deleted_at": None,
        })
        if open_changes > 0:
            blocking.append(f"{open_changes} varianti aperte non ancora accettate/firmate")

    # Ordine esecutivo (potrebbe non esistere ancora ma è OK)
    executive_order_id = None
    if ts_id:
        eo = await db.executive_orders.find_one({
            "tenant_id": tenant_id, "contract_id": contract_id,
            "technical_schedule_id": ts_id, "deleted_at": None,
        })
        if eo:
            executive_order_id = eo["_id"]
            src["executive_order_version"] = eo.get("version", 1)

    return ProductionReleaseCheckResult(
        eligible=(len(blocking) == 0),
        blocking_reasons=blocking, warnings=warnings,
        checked_at=utcnow(), checked_by=checked_by,
        source_versions=src,
        contract_id=contract_id, contract_status=contract_status,
        survey_id=survey_id, survey_status=survey_status,
        technical_schedule_id=ts_id, technical_schedule_status=ts_status,
        open_change_requests=open_changes,
        executive_order_id=executive_order_id,
    )


# ---------------------------------------------------------------------
# ORCHESTRATION HOOKS
# ---------------------------------------------------------------------
async def ensure_survey_from_contract(*, tenant_id: str, contract: Dict[str, Any], actor_id: Optional[str] = None) -> Optional[str]:
    """Idempotente: crea Survey to_schedule se non esiste. Ritorna survey_id."""
    db = get_db()
    contract_id = contract["_id"] if "_id" in contract else contract.get("id")
    # Evento timeline contract.signed (idempotente) — visibile al cliente come "Contratto firmato"
    if contract.get("contract_status") == "signed" and not await db.timeline_events.find_one(
            {"tenant_id": tenant_id, "contract_id": contract_id, "event_type": "contract.signed"}):
        await log_timeline_event(
            tenant_id=tenant_id, domain="contract", event_type="contract.signed", ref_id=contract_id,
            contract_id=contract_id, quote_id=contract.get("quote_id"), customer_id=contract.get("customer_id"),
            new_status="signed", actor_id=actor_id, source="system", is_customer_visible=True,
            customer_label="Contratto firmato", customer_stage="contract_signed",
        )
    existing = await db.surveys.find_one({
        "tenant_id": tenant_id, "contract_id": contract_id, "deleted_at": None,
    })
    if existing:
        return existing["_id"]
    # Copia base dal contract snapshot
    snap = contract.get("quote_snapshot") or {}
    site_addr = snap.get("site_address") or {}
    customer_id = contract.get("customer_id")
    # Costruzione openings preventive
    quote_openings = snap.get("openings") or []
    quote_lines = snap.get("lines") or []
    ops = []
    for qo in quote_openings:
        # Trova prime linee legate al vano per stimare misure
        related = [ql for ql in quote_lines if ql.get("opening_id") == qo.get("id")]
        first = related[0] if related else {}
        ops.append({
            "ref": qo.get("code") or f"V{len(ops)+1}",
            "location": qo.get("room"),
            "quote_width_mm": qo.get("width_mm") or first.get("width_mm"),
            "quote_height_mm": qo.get("height_mm") or first.get("height_mm"),
            "measured_width_mm": None,
            "measured_height_mm": None,
        })

    from app.models_ops import Survey
    survey = Survey(
        tenant_id=tenant_id,
        contract_id=contract_id,
        quote_id=contract.get("quote_id"),
        customer_id=customer_id,
        site_address=site_addr,
        survey_status="draft",   # to_schedule verrà impostato quando è definita una data
        openings=ops,
    )
    doc = to_mongo(survey.model_dump(by_alias=True))
    await db.surveys.insert_one(doc)
    await log_timeline_event(
        tenant_id=tenant_id, domain="survey", event_type="survey.created",
        ref_id=survey.id, contract_id=contract_id, customer_id=customer_id,
        actor_id=actor_id, source="system", is_customer_visible=True,
        customer_label="Rilievo tecnico da programmare",
        customer_stage="survey_scheduled",
        new_status="draft",
    )
    return survey.id


async def ensure_technical_schedule_from_survey(*, tenant_id: str, survey_id: str, actor_id: str) -> Optional[str]:
    """Idempotente: crea Abaco (TechnicalSchedule) draft copiando le misure rilevate dalla survey."""
    db = get_db()
    survey = await db.surveys.find_one({"_id": survey_id, "tenant_id": tenant_id, "deleted_at": None})
    if not survey:
        return None
    existing = await db.technical_schedules.find_one({
        "tenant_id": tenant_id, "survey_id": survey_id, "is_current": True, "deleted_at": None,
    })
    if existing:
        return existing["_id"]
    # Verifica contract firmato
    contract_id = survey.get("contract_id")
    contract = await db.contracts.find_one({"_id": contract_id, "tenant_id": tenant_id}) if contract_id else None
    quote_id = survey.get("quote_id") or (contract or {}).get("quote_id")
    quote = await db.quotes.find_one({"_id": quote_id, "tenant_id": tenant_id}) if quote_id else None
    quote_revision = (quote or {}).get("revision", 0)

    items: List[Dict[str, Any]] = []
    for op in survey.get("openings") or []:
        # usa misure rilevate se presenti, altrimenti quote
        w = op.get("measured_width_mm") or op.get("quote_width_mm") or 1000
        h = op.get("measured_height_mm") or op.get("quote_height_mm") or 1200
        item = TechnicalScheduleItem(
            ref=op.get("ref") or f"V{len(items)+1}",
            room=op.get("location"),
            product_key="window_1_leaf",
            final_width_mm=int(w),
            final_height_mm=int(h),
            nr_ante=1,
            profile_system_id="",   # da compilare in review tecnica
            survey_opening_ref=op.get("ref"),
        ).model_dump()
        items.append(item)

    ts = TechnicalSchedule(
        tenant_id=tenant_id,
        quote_id=quote_id or "",
        quote_revision=quote_revision,
        contract_id=contract_id or "",
        survey_id=survey_id,
        customer_id=survey.get("customer_id"),
        site_address=survey.get("site_address"),
        items=[TechnicalScheduleItem(**i) for i in items],
        ts_status="draft",
    )
    # Numerazione progressiva
    from app.services.ops_common import next_number
    number, number_int = await next_number(tenant_id, "technical_schedule", prefix="ABACO")
    ts.number = number
    ts.number_int = number_int
    doc = to_mongo(ts.model_dump(by_alias=True))
    await db.technical_schedules.insert_one(doc)
    await log_timeline_event(
        tenant_id=tenant_id, domain="technical_schedule", event_type="ts.created",
        ref_id=ts.id, contract_id=contract_id, customer_id=survey.get("customer_id"),
        survey_id=survey_id, actor_id=actor_id, source="system",
        new_status="draft",
    )
    return ts.id


def canonical_hash(payload: Dict[str, Any]) -> str:
    j = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(j.encode()).hexdigest()


async def create_executive_order_from_signed_ts(
    *, tenant_id: str, technical_schedule_id: str, actor_id: str,
) -> Optional[str]:
    """Crea idempotentemente l'ExecutiveOrder da un Abaco firmato.
    Snapshot immutabili: contract + technical_schedule.
    """
    db = get_db()
    ts = await db.technical_schedules.find_one({
        "_id": technical_schedule_id, "tenant_id": tenant_id, "deleted_at": None,
    })
    if not ts or ts.get("ts_status") not in ("signed", "released_to_production"):
        return None
    existing = await db.executive_orders.find_one({
        "tenant_id": tenant_id, "technical_schedule_id": technical_schedule_id,
        "deleted_at": None,
    })
    if existing:
        return existing["_id"]

    contract = await db.contracts.find_one({"_id": ts.get("contract_id"), "tenant_id": tenant_id})
    # Numerazione
    from app.services.ops_common import next_number
    number, number_int = await next_number(tenant_id, "executive_order", prefix="OE")

    lines: List[ExecutiveOrderLine] = []
    for it in ts.get("items") or []:
        lines.append(ExecutiveOrderLine(
            ref=it.get("ref"),
            room=it.get("room"),
            product_key=it.get("product_key"),
            typology=it.get("typology"),
            final_width_mm=it.get("final_width_mm"),
            final_height_mm=it.get("final_height_mm"),
            nr_ante=it.get("nr_ante", 1),
            profile_system_id=it.get("profile_system_id"),
            internal_color_id=it.get("internal_color_id"),
            external_color_id=it.get("external_color_id"),
            glass_type_id=it.get("glass_type_id"),
            hardware_kit_id=it.get("hardware_kit_id"),
            accessories=it.get("accessories") or [],
            svg_drawing=it.get("svg_drawing"),
            productive_bom_snapshot=it.get("parametric_snapshot") or {},
            ts_item_id=it.get("id"),
            survey_opening_ref=it.get("survey_opening_ref"),
            quote_line_id=it.get("quote_line_id"),
        ))
    eo = ExecutiveOrder(
        tenant_id=tenant_id,
        number=number, number_int=number_int,
        quote_id=ts.get("quote_id") or "",
        contract_id=ts.get("contract_id"),
        survey_id=ts.get("survey_id"),
        technical_schedule_id=technical_schedule_id,
        technical_schedule_version=ts.get("version", 1),
        customer_id=ts.get("customer_id"),
        site_address=ts.get("site_address"),
        lines=lines,
        contract_snapshot={"id": (contract or {}).get("_id"),
                            "number": (contract or {}).get("number"),
                            "signed_at": (contract or {}).get("signed_at"),
                            "quote_snapshot": (contract or {}).get("quote_snapshot", {})},
        technical_schedule_snapshot={"id": ts["_id"], "number": ts.get("number"),
                                       "version": ts.get("version"), "signed_at": ts.get("signed_at"),
                                       "snapshot_hash": ts.get("snapshot_hash")},
        eo_status="created",
        released_at=utcnow(), released_by=actor_id,
    )
    doc = to_mongo(eo.model_dump(by_alias=True))
    await db.executive_orders.insert_one(doc)
    # Aggiorna TS con executive_order_id + stato released
    await db.technical_schedules.update_one(
        {"_id": technical_schedule_id, "tenant_id": tenant_id},
        {"$set": {"executive_order_id": eo.id, "ts_status": "released_to_production",
                   "released_at": utcnow().isoformat(), "released_by": actor_id}},
    )
    await log_timeline_event(
        tenant_id=tenant_id, domain="executive_order", event_type="executive_order.created",
        ref_id=eo.id, contract_id=ts.get("contract_id"), customer_id=ts.get("customer_id"),
        survey_id=ts.get("survey_id"), technical_schedule_id=technical_schedule_id,
        executive_order_id=eo.id, actor_id=actor_id, source="system",
        is_customer_visible=True, customer_label="Ordine confermato",
        customer_stage="order_confirmed", new_status="created",
    )
    return eo.id


# ---------------------------------------------------------------------
# CUSTOMER STATUS MAPPING (default)
# ---------------------------------------------------------------------
DEFAULT_CUSTOMER_STATUS_MAP: Dict[str, Dict[str, Any]] = {
    "contract:signed": {"label": "Contratto firmato", "stage": "contract_signed", "order": 10},
    "survey:draft": {"label": "Rilievo tecnico da programmare", "stage": "survey_scheduled", "order": 20},
    "survey:scheduled": {"label": "Rilievo tecnico programmato", "stage": "survey_scheduled", "order": 21},
    "survey:completed": {"label": "Rilievo completato", "stage": "survey_completed", "order": 30},
    "survey:approved": {"label": "Rilievo validato", "stage": "survey_completed", "order": 31},
    "technical_schedule:sent_to_customer": {"label": "Abaco tecnico inviato", "stage": "schedule_sent", "order": 40},
    "technical_schedule:signed": {"label": "Abaco tecnico approvato", "stage": "schedule_approved", "order": 50},
    "executive_order:created": {"label": "Ordine confermato", "stage": "order_confirmed", "order": 60},
    "purchase_order:sent": {"label": "Materiali in approvvigionamento", "stage": "materials_procurement", "order": 70},
    "production:awaiting_materials": {"label": "Materiali in approvvigionamento", "stage": "materials_procurement", "order": 71},
    "production:scheduled": {"label": "Produzione programmata", "stage": "production_scheduled", "order": 80},
    "production:cutting": {"label": "Produzione in corso", "stage": "in_production", "order": 90},
    "production:machining": {"label": "Produzione in corso", "stage": "in_production", "order": 91},
    "production:welding": {"label": "Produzione in corso", "stage": "in_production", "order": 92},
    "production:assembly": {"label": "Produzione in corso", "stage": "in_production", "order": 93},
    "production:hardware_installation": {"label": "Produzione in corso", "stage": "in_production", "order": 94},
    "production:glazing": {"label": "Produzione in corso", "stage": "in_production", "order": 95},
    "production:quality_control": {"label": "Controllo qualità", "stage": "quality_control", "order": 100},
    "production:packaging": {"label": "Preparazione consegna", "stage": "delivery_prep", "order": 110},
    "production:completed": {"label": "Prodotto completato", "stage": "product_completed", "order": 120},
    "production:ready_for_delivery": {"label": "Preparazione consegna", "stage": "delivery_prep", "order": 121},
    "installation:scheduled": {"label": "Posa programmata", "stage": "installation_scheduled", "order": 130},
    "installation:completed": {"label": "Installazione completata", "stage": "installation_completed", "order": 140},
    "final_check:passed": {"label": "Collaudo superato", "stage": "final_check", "order": 150},
    "warranty:active": {"label": "Garanzia attiva", "stage": "warranty_active", "order": 160},
}


async def resolve_customer_status(*, tenant_id: str, key: str) -> Dict[str, Any]:
    """Ritorna il mapping cliente per una chiave interna. Fallback al default map."""
    db = get_db()
    doc = await db.customer_status_mappings.find_one({
        "tenant_id": tenant_id, "key": key, "deleted_at": None,
    })
    if doc:
        return {"label": doc.get("customer_label"), "stage": doc.get("customer_stage"),
                "order": doc.get("order_index", 0), "is_public": doc.get("is_public", True)}
    dm = DEFAULT_CUSTOMER_STATUS_MAP.get(key)
    if dm:
        return {"label": dm["label"], "stage": dm["stage"], "order": dm.get("order", 0), "is_public": True}
    return {"label": None, "stage": None, "order": 0, "is_public": False}
