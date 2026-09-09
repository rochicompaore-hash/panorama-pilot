"""CONDIZIONI CONTRATTUALI — IN SINTESI (PO msg 782 §6-§8).

Il preventivo NON crea condizioni: mostra solo un riassunto informativo derivato dalla
GENERAL_TERMS_VERSION canonica (general_terms_canonical.py). Ogni punto è collegato agli
articoli sorgente (`source_articles`). Snapshot congelato su ACCEPTED (mai retroattivo).
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from app.services.general_terms_canonical import GENERAL_TERMS_VERSION, canonical_hash, get_canonical

GENERAL_TERMS_SUMMARY_VERSION = "GENERAL_TERMS_SUMMARY_V1"
ACCEPTED_STATES = ("accepted", "converted", "superseded")

SECTION_TITLE = "CONDIZIONI CONTRATTUALI — IN SINTESI"
INFO_NOTICE = ("Il seguente riepilogo ha finalità esclusivamente informativa e non modifica, sostituisce né integra le "
               "Condizioni Generali di Contratto. In caso di difformità, prevale esclusivamente il testo integrale delle "
               "Condizioni Generali allegate al contratto.")
CLOSING_NOTE = INFO_NOTICE

# Sintesi customer-friendly approvata dal PO (msg 782 §8) — ogni punto ha fonte contrattuale.
SUMMARY_V1: List[Dict[str, Any]] = [
    {"key": "fornitura", "title": "Fornitura e configurazione", "source_articles": ["1", "2", "2-bis"],
     "text": "La fornitura riguarda esclusivamente i prodotti e servizi riportati nel preventivo e nei relativi allegati. Le caratteristiche tecniche, dimensionali, prestazionali ed estetiche sono quelle approvate dal cliente."},
    {"key": "ordine_varianti", "title": "Ordine e varianti", "source_articles": ["3", "3-bis", "5-bis"],
     "text": "L'ordine viene confermato secondo quanto previsto dal contratto. Eventuali modifiche richieste successivamente devono essere valutate tecnicamente ed economicamente e, quando previsto, formalmente approvate prima di procedere."},
    {"key": "rilievo", "title": "Rilievo tecnico", "source_articles": ["3-quater", "5"],
     "text": "Quando previsto, il rilievo tecnico definitivo serve a verificare le misure e la corretta configurazione prima dell'avvio dell'ordine. Eventuali differenze rispetto alle informazioni preliminari sono gestite secondo quanto previsto dal contratto."},
    {"key": "prodotti_accessori", "title": "Prodotti e accessori", "source_articles": ["3-ter"],
     "text": "Sono compresi esclusivamente prodotti, accessori, cassonetti, tapparelle, zanzariere, persiane, servizi e lavorazioni espressamente indicati nel preventivo. Quanto non indicato non si considera automaticamente compreso."},
    {"key": "posa_cantiere", "title": "Posa e cantiere", "source_articles": ["4", "4-bis", "11", "11-bis"],
     "text": "Quando la posa è prevista, il cliente deve rendere il cantiere accessibile e nelle condizioni necessarie per l'esecuzione dei lavori. Eventuali opere o servizi non compresi nella fornitura restano disciplinati dal contratto."},
    {"key": "pagamenti", "title": "Pagamenti", "source_articles": ["6", "7", "9"],
     "text": "Si applicano le modalità di pagamento riportate nel preventivo/contratto sottoscritto. Gli avanzamenti della commessa sono subordinati alle condizioni economiche previste."},
    {"key": "merce_pronta", "title": "Merce pronta e montaggio", "source_articles": ["6", "10", "12"],
     "text": "Quando la commessa risulta pronta, il cliente viene informato secondo il processo previsto. Il montaggio viene programmato nel rispetto delle condizioni economiche, tecniche e organizzative applicabili."},
    {"key": "tempi", "title": "Tempi di consegna", "source_articles": ["3-quater", "12"],
     "text": "I tempi decorrono secondo le condizioni indicate nel contratto e dipendono dalla configurazione, dal rilievo tecnico, dalle condizioni economiche e dagli altri presupposti contrattualmente previsti."},
    {"key": "controllo", "title": "Controllo della fornitura", "source_articles": ["13", "17"],
     "text": "Alla consegna/installazione il cliente è tenuto a verificare la fornitura e a segnalare eventuali difformità secondo modalità e termini previsti dal contratto."},
    {"key": "garanzia", "title": "Garanzia", "source_articles": ["14"],
     "text": "La garanzia è regolata dalle condizioni riportate nel preventivo e nel contratto e, quando non diversamente previsto, dalla normativa applicabile. La copertura dipende anche dal corretto uso, dalla manutenzione e dalle condizioni previste dal contratto."},
    {"key": "modifiche_recesso", "title": "Modifiche e recesso", "source_articles": ["3", "3-bis", "15", "16"],
     "text": "Trattandosi di prodotti realizzati su misura e personalizzati, le eventuali richieste di modifica o scioglimento del contratto sono disciplinate dalle specifiche disposizioni contenute nelle Condizioni Generali."},
    {"key": "benefici_fiscali", "title": "Benefici fiscali / bonifico", "source_articles": ["8", "11", "22"],
     "text": "Quando il cliente intende usufruire di agevolazioni fiscali, deve rispettare le condizioni e gli adempimenti previsti dalla normativa applicabile e dal contratto."},
    {"key": "enea", "title": "Pratica ENEA", "source_articles": ["23"],
     "text": "Quando espressamente inclusa, la pratica ENEA costituisce un servizio accessorio alla fornitura e viene gestita secondo le condizioni contrattuali e il servizio acquistato."},
    {"key": "legge_foro", "title": "Legge e foro", "source_articles": ["20", "21"],
     "text": "Il contratto è regolato dalla legge italiana. Gli ulteriori aspetti, compresa la competenza territoriale, sono disciplinati dal testo integrale del contratto."},
]


def build_summary(version: str | None = None) -> Dict[str, Any]:
    """Sintesi derivata dalla versione canonica: fail-closed se un punto cita un articolo inesistente."""
    canon = get_canonical(version)
    numbers = {a["number"] for a in canon["articles"]}
    sections = []
    for s in SUMMARY_V1:
        missing = [n for n in s["source_articles"] if n not in numbers]
        if missing:
            raise ValueError(f"Summary '{s['key']}' cita articoli inesistenti: {missing}")
        sections.append({**s, "source_titles": [f"Art. {a['number']} — {a['title']}" for a in canon["articles"] if a["number"] in s["source_articles"]]})
    content = {
        "version": canon["version"],
        "summary_version": GENERAL_TERMS_SUMMARY_VERSION,
        "effective_from": canon["effective_from"],
        "general_terms_hash": canon["general_terms_hash"],
        "articles_count": canon["articles_count"],
        "section_title": SECTION_TITLE,
        "info_notice": INFO_NOTICE,
        "sections": sections,
        "legal_sections": [],
        "missing_sources": [],
        "closing_note": CLOSING_NOTE,
    }
    content["content_hash"] = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return content


async def build_general_terms(db, tenant_id: str) -> Dict[str, Any]:
    """Sintesi corrente (ONE CANONICAL SOURCE: nessuna dipendenza da `clauses`)."""
    return build_summary()


async def resolve_general_terms_for_quote(db, quote: dict) -> Dict[str, Any]:
    """DRAFT: versione corrente (snapshot upsert per hash).
    ACCEPTED/CONVERTED/SUPERSEDED: snapshot congelato — mai ricalcolato."""
    tenant_id = quote["tenant_id"]
    if (quote.get("quote_status") or "").lower() in ACCEPTED_STATES and quote.get("general_terms_snapshot_id"):
        frozen = await db.general_terms_snapshots.find_one({"_id": quote["general_terms_snapshot_id"]})
        if frozen:
            frozen["id"] = frozen.pop("_id")
            frozen["frozen"] = True
            return frozen
    content = build_summary()
    existing = await db.general_terms_snapshots.find_one({"tenant_id": tenant_id, "content_hash": content["content_hash"]})
    if existing:
        snap_id = existing["_id"]
    else:
        snap_id = str(uuid4())
        await db.general_terms_snapshots.insert_one({"_id": snap_id, "tenant_id": tenant_id,
                                                     "created_at": datetime.now(timezone.utc).isoformat(), **content})
    qid = quote.get("id") or quote.get("_id")
    if quote.get("general_terms_snapshot_id") != snap_id or quote.get("general_terms_version") != content["version"]:
        await db.quotes.update_one({"_id": qid}, {"$set": {"general_terms_version": content["version"], "general_terms_snapshot_id": snap_id,
                                                          "general_terms_hash": content["general_terms_hash"]}})
        quote["general_terms_version"], quote["general_terms_snapshot_id"] = content["version"], snap_id
    return {"id": snap_id, "frozen": False, **content}


__all__ = ["GENERAL_TERMS_VERSION", "GENERAL_TERMS_SUMMARY_VERSION", "SUMMARY_V1", "INFO_NOTICE", "SECTION_TITLE",
           "build_summary", "build_general_terms", "resolve_general_terms_for_quote", "canonical_hash"]
