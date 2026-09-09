"""Condizioni Generali — In sintesi (PO msg 626 §11-§14) con versioning e snapshot congelato.

Source of truth: testo sintetico V1 approvato dal PO + collection `clauses` (contratto ufficiale in sistema).
Le clausole legalmente sensibili (recesso, penali, foro, forza maggiore, risoluzione, perdita acconto,
limitazioni responsabilità, garanzia temporale) vengono incluse SOLO se esiste testualmente una clausola
ufficiale in `clauses`; altrimenti sono marcate CONTRACT_TERMS_SOURCE_MISSING e NON vengono completate.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

GENERAL_TERMS_VERSION = "GT-2026.09-V1"
ACCEPTED_STATES = ("accepted", "converted", "superseded")

CLOSING_NOTE = ("Il presente riepilogo ha finalità informativa e non sostituisce le Condizioni Generali di Contratto, "
                "che costituiscono parte integrante della documentazione contrattuale.")

# Sezioni approvate PO (msg 626 §12). `clause_codes` = clausole ufficiali a supporto (se presenti in sistema).
SECTIONS_V1: List[Dict[str, Any]] = [
    {"key": "oggetto", "title": "Oggetto della fornitura", "clause_codes": [],
     "text": "La fornitura comprende esclusivamente i prodotti e i servizi indicati nel preventivo e nei relativi allegati. Configurazioni, quantità, colori, vetri, accessori, posa, smontaggio, smaltimento e servizi accessori sono quelli espressamente indicati nel documento."},
    {"key": "misure", "title": "Misure e rilievo tecnico", "clause_codes": ["CL_MISURE_INDICATIVE"],
     "text": "Le misure raccolte in fase commerciale sono indicative. Quando previsto, le misure esecutive vengono definite mediante rilievo tecnico effettuato successivamente alla conferma dell'ordine. Eventuali differenze tecniche rilevate devono essere valutate prima dell'avvio della produzione."},
    {"key": "varianti", "title": "Varianti", "clause_codes": ["CL_VARIAZIONI", "CL_OPERE_MURARIE"],
     "text": "Qualora il rilievo tecnico evidenzi la necessità di modificare misure, configurazioni, accessori, opere o soluzioni tecniche, eventuali variazioni economiche o tecniche devono essere comunicate e approvate prima di procedere."},
    {"key": "pagamenti", "title": "Pagamenti", "clause_codes": ["CL_PAGAMENTI_50_50"],
     "text": "Si applicano esclusivamente le condizioni di pagamento indicate nel presente preventivo/contratto. Per la modalità standard: 50% alla firma/conferma dell'ordine, 50% all'avviso di merce pronta. Le modalità alternative valgono solo se espressamente selezionate nel documento."},
    {"key": "finanziamento", "title": "Finanziamento", "clause_codes": [],
     "text": "Quando viene richiesto un finanziamento, l'approvazione è di competenza dell'istituto finanziario. La richiesta o l'invio della pratica non equivale ad approvazione. L'avvio dell'ordine segue le condizioni previste dalla pratica e dal contratto."},
    {"key": "produzione", "title": "Produzione", "clause_codes": [],
     "text": "L'ordine viene rilasciato alla produzione/fornitore solo dopo il completamento dei controlli economici e tecnici previsti. La configurazione definitiva è quella risultante dalla revisione approvata e dal rilievo tecnico ove previsto."},
    {"key": "tempi", "title": "Tempi", "clause_codes": [],
     "text": "I tempi indicati nel preventivo sono tempistiche previsionali collegate alla configurazione acquistata. Le date di produzione, merce pronta e montaggio vengono successivamente confermate secondo lo stato reale della commessa."},
    {"key": "merce_pronta", "title": "Merce pronta", "clause_codes": [],
     "text": "La commessa viene considerata \"merce pronta\" quando i prodotti e i componenti necessari risultano disponibili secondo il processo di controllo aziendale. L'azienda comunica al cliente l'importo eventualmente ancora dovuto e le modalità di pagamento previste."},
    {"key": "montaggio", "title": "Montaggio", "clause_codes": ["CL_POSA_STANDARD", "CL_ACCESSIBILITA"],
     "text": "Quando la posa è compresa, la programmazione viene effettuata dopo la disponibilità della merce e il rispetto delle condizioni economiche previste dal contratto. Il cliente deve garantire l'accessibilità del cantiere e comunicare eventuali vincoli rilevanti per l'intervento."},
    {"key": "prodotti", "title": "Prodotti e configurazioni", "clause_codes": ["CL_IMMAGINI"],
     "text": "Colori, vetri, aperture, dimensioni, accessori e finiture sono quelli riportati nella configurazione approvata. Prima della produzione le caratteristiche definitive devono risultare validate."},
    {"key": "garanzia", "title": "Garanzia e assistenza", "clause_codes": ["CL_GARANZIA_24"],
     "text": "Garanzia e assistenza sono gestite secondo le condizioni applicabili al prodotto, alla posa e al contratto. In caso di segnalazione l'azienda verifica la natura e la causa del problema prima di stabilire se l'intervento rientra in garanzia."},
    {"key": "enea", "title": "ENEA / Detrazioni", "clause_codes": ["CL_DETRAZIONI"],
     "text": "Quando acquistata, la pratica ENEA viene gestita secondo il servizio selezionato: ENEA STANDARD oppure ENEA ASSICURATA. L'accesso a eventuali benefici fiscali resta subordinato ai requisiti e alla documentazione applicabili."},
    {"key": "documentazione", "title": "Documentazione", "clause_codes": [],
     "text": "Il cliente può ricevere, quando applicabili: preventivo, contratto, rilievo tecnico, documentazione prodotto, certificazioni, manuale uso e manutenzione, documentazione ENEA, documenti di collaudo."},
    {"key": "modifiche", "title": "Modifiche dopo la conferma", "clause_codes": ["CL_VARIAZIONI"],
     "text": "Qualunque modifica richiesta dopo l'approvazione della configurazione deve essere valutata tecnicamente ed economicamente. Se necessario: nuova revisione e approvazione cliente prima dell'esecuzione."},
]

# Temi legalmente sensibili (§13): inclusi SOLO con testo ufficiale presente in `clauses`.
SENSITIVE_TOPICS: Dict[str, Dict[str, Any]] = {
    "recesso": {"title": "Annullamento e recesso", "clause_codes": ["CL_ANNULLAMENTO"]},
    "garanzia_temporale": {"title": "Durata della garanzia", "clause_codes": ["CL_GARANZIA_24"]},
    "penali": {"title": "Penali", "clause_codes": ["CL_PENALI"]},
    "foro_competente": {"title": "Foro competente", "clause_codes": ["CL_FORO"]},
    "forza_maggiore": {"title": "Forza maggiore", "clause_codes": ["CL_FORZA_MAGGIORE"]},
    "risoluzione": {"title": "Risoluzione", "clause_codes": ["CL_RISOLUZIONE"]},
    "perdita_acconto": {"title": "Acconto", "clause_codes": ["CL_ACCONTO"]},
    "limitazioni_responsabilita": {"title": "Limitazioni di responsabilità", "clause_codes": ["CL_RESPONSABILITA"]},
}


async def build_general_terms(db, tenant_id: str) -> Dict[str, Any]:
    """Compone la sintesi corrente a partire dal testo V1 + clausole ufficiali presenti nel sistema."""
    clauses: Dict[str, dict] = {}
    async for c in db.clauses.find({"tenant_id": tenant_id, "deleted_at": None}, {"code": 1, "title": 1, "text": 1, "version": 1}):
        clauses[c.get("code")] = c
    sections = []
    for s in SECTIONS_V1:
        supported = [c for c in s["clause_codes"] if c in clauses]
        sections.append({"key": s["key"], "title": s["title"], "text": s["text"], "source_clause_codes": supported})
    legal_sections, missing = [], []
    for topic, meta in SENSITIVE_TOPICS.items():
        found = [clauses[c] for c in meta["clause_codes"] if c in clauses]
        if found:
            legal_sections.append({"key": topic, "title": found[0].get("title") or meta["title"],
                                   "text": found[0].get("text"), "source_clause_codes": [f.get("code") for f in found]})
        else:
            missing.append({"topic": topic, "status": "CONTRACT_TERMS_SOURCE_MISSING"})
    content = {"version": GENERAL_TERMS_VERSION, "sections": sections, "legal_sections": legal_sections,
               "missing_sources": missing, "closing_note": CLOSING_NOTE}
    content["content_hash"] = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return content


async def resolve_general_terms_for_quote(db, quote: dict) -> Dict[str, Any]:
    """DRAFT: versione corrente (snapshot upsert per hash, aggiornata sul preventivo).
    ACCEPTED/CONVERTED/SUPERSEDED: snapshot congelato — mai ricalcolato."""
    tenant_id = quote["tenant_id"]
    if (quote.get("quote_status") or "").lower() in ACCEPTED_STATES and quote.get("general_terms_snapshot_id"):
        frozen = await db.general_terms_snapshots.find_one({"_id": quote["general_terms_snapshot_id"]})
        if frozen:
            frozen["id"] = frozen.pop("_id")
            frozen["frozen"] = True
            return frozen
    content = await build_general_terms(db, tenant_id)
    existing = await db.general_terms_snapshots.find_one({"tenant_id": tenant_id, "content_hash": content["content_hash"]})
    if existing:
        snap_id = existing["_id"]
    else:
        snap_id = str(uuid4())
        await db.general_terms_snapshots.insert_one({"_id": snap_id, "tenant_id": tenant_id,
                                                     "created_at": datetime.now(timezone.utc).isoformat(), **content})
    qid = quote.get("id") or quote.get("_id")
    if quote.get("general_terms_snapshot_id") != snap_id or quote.get("general_terms_version") != content["version"]:
        await db.quotes.update_one({"_id": qid}, {"$set": {"general_terms_version": content["version"], "general_terms_snapshot_id": snap_id}})
        quote["general_terms_version"], quote["general_terms_snapshot_id"] = content["version"], snap_id
    return {"id": snap_id, "frozen": False, **content}
