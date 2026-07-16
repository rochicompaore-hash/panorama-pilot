"""Seed default quote template + core clauses (M3.3.2)."""
from __future__ import annotations
from datetime import datetime, timezone
from app.db import get_db
from app.models import new_id
from app.models_pdf import (
    QuoteTemplate, Clause, TemplateSection, TemplateStyle,
    PaymentTermsSchema, PaymentInstallment,
)
from app.mongo_utils import to_mongo


DEFAULT_TEMPLATE_CODE = "IE_STANDARD_2026"


DEFAULT_SECTIONS = [
    {"key": "cover", "title": "Copertina", "visible": True, "order_index": 10, "settings": {}},
    {"key": "summary", "title": "Riepilogo iniziale", "visible": True, "order_index": 20, "settings": {}},
    {"key": "openings", "title": "Dettaglio prodotti per vano", "visible": True, "order_index": 30, "settings": {"show_prices_per_line": True, "show_images": True}},
    {"key": "economic_summary", "title": "Riepilogo economico", "visible": True, "order_index": 40, "settings": {}},
    {"key": "payment_terms", "title": "Condizioni di pagamento", "visible": True, "order_index": 50, "settings": {}},
    {"key": "clauses", "title": "Condizioni contrattuali", "visible": True, "order_index": 60, "settings": {}},
    {"key": "disclaimers", "title": "Avvertenze", "visible": True, "order_index": 70, "settings": {}},
    {"key": "signature", "title": "Firma per accettazione", "visible": True, "order_index": 80, "settings": {}},
]


DEFAULT_CLAUSES = [
    {
        "code": "CL_MISURE_INDICATIVE", "title": "Misure indicative",
        "category": "misure", "mandatory": True, "order_index": 10,
        "text": (
            "Le misure riportate nel presente preventivo sono indicative e non costituiscono "
            "misure esecutive o definitive. Le misure finali saranno rilevate e validate dal "
            "tecnico incaricato prima dell'ordine e dell'avvio della produzione. Eventuali "
            "differenze potranno comportare l'adeguamento del preventivo, previa comunicazione al Cliente."
        ),
    },
    {
        "code": "CL_POSA_STANDARD", "title": "Posa in opera",
        "category": "posa", "mandatory": True, "order_index": 20,
        "text": (
            "La posa in opera è compresa nel prezzo salvo diversa indicazione in offerta. "
            "Comprende lo smontaggio dei serramenti esistenti, il montaggio dei nuovi, "
            "la sigillatura interna ed esterna, la pulizia dell'area di lavoro. "
            "Non sono incluse opere murarie, tinteggiature, ripristini di rivestimenti, davanzali, "
            "opere elettriche o idrauliche salvo esplicito riferimento in offerta."
        ),
    },
    {
        "code": "CL_OPERE_MURARIE", "title": "Opere murarie",
        "category": "opere_murarie", "mandatory": False, "order_index": 30,
        "text": (
            "Eventuali opere murarie di adeguamento vano, ripristino intonaci, tinteggiatura, "
            "sostituzione di davanzali in muratura o marmo sono escluse dal presente preventivo, "
            "salvo diversa indicazione. Rimangono a carico del Cliente o soggette a offerta separata."
        ),
    },
    {
        "code": "CL_SMALTIMENTO", "title": "Smaltimento",
        "category": "smaltimento", "mandatory": False, "order_index": 40,
        "text": (
            "Lo smaltimento dei serramenti sostituiti secondo la normativa vigente è compreso, "
            "salvo differente indicazione. Materiali contenenti amianto, piombo o sostanze pericolose "
            "richiedono intervento specialistico separato."
        ),
    },
    {
        "code": "CL_ACCESSIBILITA", "title": "Accessibilità del cantiere",
        "category": "accessibilita", "mandatory": True, "order_index": 50,
        "text": (
            "Il Cliente garantisce l'accessibilità del cantiere nei giorni concordati, con spazi liberi "
            "per manovre di montaggio, disponibilità di corrente elettrica 220V e servizi igienici. "
            "L'eventuale utilizzo di piattaforme aeree, ponteggi o gru richiesto per l'installazione, "
            "se non incluso in offerta, sarà a carico del Cliente."
        ),
    },
    {
        "code": "CL_PAGAMENTI_50_50", "title": "Condizioni di pagamento (50/50)",
        "category": "pagamenti", "mandatory": True, "order_index": 60,
        "text": (
            "Salvo diversa indicazione in offerta: 50% acconto alla firma dell'ordine, "
            "50% a saldo ad avviso merce pronta prima della posa. "
            "I pagamenti dovranno pervenire a mezzo bonifico bancario sui riferimenti indicati in fattura."
        ),
    },
    {
        "code": "CL_GARANZIA_24", "title": "Garanzia",
        "category": "garanzia", "mandatory": True, "order_index": 70,
        "text": (
            "I prodotti forniti sono coperti da garanzia di 24 mesi ai sensi della normativa vigente, "
            "decorrenti dalla data di consegna. La garanzia non copre danni derivanti da uso improprio, "
            "manutenzione non conforme, agenti atmosferici estremi, alterazioni da terzi. "
            "Componenti motorizzati e ferramenta hanno garanzia secondo i termini del produttore."
        ),
    },
    {
        "code": "CL_DETRAZIONI", "title": "Detrazioni fiscali",
        "category": "detrazioni", "mandatory": False, "order_index": 80,
        "text": (
            "Il Cliente è responsabile della verifica dei requisiti per l'accesso alle detrazioni "
            "fiscali applicabili (ecobonus, bonus casa, superbonus, sconto in fattura o cessione del credito). "
            "L'Azienda potrà fornire la documentazione tecnica di supporto ma non è responsabile "
            "del riconoscimento fiscale, che dipende dalla completezza documentale del beneficiario."
        ),
    },
    {
        "code": "CL_VARIAZIONI", "title": "Variazioni in corso d'opera",
        "category": "variazioni", "mandatory": True, "order_index": 90,
        "text": (
            "Eventuali variazioni richieste dopo la firma dell'ordine potranno comportare "
            "adeguamenti di prezzo e tempi, previa formalizzazione in una revisione del contratto. "
            "Variazioni non concordate per iscritto non sono vincolanti."
        ),
    },
    {
        "code": "CL_ANNULLAMENTO", "title": "Annullamento e recesso",
        "category": "annullamento", "mandatory": False, "order_index": 100,
        "text": (
            "Ai sensi del Codice del Consumo, il Cliente consumatore ha diritto di recedere entro 14 giorni "
            "dalla firma. Trascorso tale termine, l'annullamento comporta il riconoscimento all'Azienda "
            "dei costi sostenuti (progettazione, materiali già ordinati, rilievi). "
            "L'annullamento a lavori in corso è soggetto a valutazione degli stati di avanzamento."
        ),
    },
    {
        "code": "CL_IMMAGINI", "title": "Immagini illustrative",
        "category": "immagini", "mandatory": True, "order_index": 110,
        "text": (
            "Le immagini presenti nel preventivo hanno scopo puramente illustrativo. "
            "Colori, finiture, proporzioni e dettagli possono differire dal prodotto effettivamente fornito. "
            "Fanno fede le specifiche tecniche descritte per ogni prodotto."
        ),
    },
    {
        "code": "CL_PRIVACY", "title": "Trattamento dati personali",
        "category": "privacy", "mandatory": True, "order_index": 120,
        "text": (
            "I dati personali del Cliente sono trattati ai sensi del Reg. UE 2016/679 (GDPR) "
            "per finalità di gestione contrattuale, fatturazione e obblighi di legge. "
            "Titolare del trattamento è l'Azienda indicata in intestazione. "
            "Il Cliente potrà esercitare i propri diritti scrivendo agli indirizzi indicati."
        ),
    },
]


async def seed_default_template(tenant_id: str) -> str:
    db = get_db()
    existing = await db.quote_templates.find_one({"tenant_id": tenant_id, "code": DEFAULT_TEMPLATE_CODE, "deleted_at": None})
    if existing:
        return existing["_id"]

    now = datetime.now(timezone.utc)
    mandatory_codes = [c["code"] for c in DEFAULT_CLAUSES if c.get("mandatory")]
    optional_codes = [c["code"] for c in DEFAULT_CLAUSES if not c.get("mandatory")]

    t = QuoteTemplate(
        id=new_id(), tenant_id=tenant_id,
        code=DEFAULT_TEMPLATE_CODE,
        name="Template Standard Infissi Express 2026",
        language="it", is_default=True, is_active=True, draft=False,
        activated_at=now,
        style=TemplateStyle(
            primary_color="#0F1720", secondary_color="#D42027",
            font_family="Inter", logo_width_mm=40, logo_position="left",
        ),
        sections=[TemplateSection(**s) for s in DEFAULT_SECTIONS],
        default_payment_terms=PaymentTermsSchema(
            kind="installments",
            installments=[
                PaymentInstallment(trigger="signature", percent=50.0, note="Acconto alla firma"),
                PaymentInstallment(trigger="goods_ready", percent=50.0, note="Saldo ad avviso merce pronta"),
            ],
            display_note="Il saldo è dovuto ad avviso merce pronta, prima dell'inizio della posa.",
        ),
        validity_days=30,
        warranty_months=24,
        delivery_days_min=30,
        delivery_days_max=45,
        mandatory_clause_codes=mandatory_codes,
        optional_clause_codes=optional_codes,
        intro_text=(
            "Gentile Cliente, siamo lieti di sottoporLe la seguente offerta per la fornitura e posa "
            "in opera di serramenti e complementi, redatta sulla base delle informazioni raccolte "
            "durante il sopralluogo commerciale. Le misure sono indicative e verranno confermate dal "
            "rilievo tecnico definitivo prima dell'ordine."
        ),
    )
    await db.quote_templates.insert_one(to_mongo(t.model_dump(by_alias=True)))
    return t.id


async def seed_default_clauses(tenant_id: str):
    db = get_db()
    for cl in DEFAULT_CLAUSES:
        existing = await db.clauses.find_one({"tenant_id": tenant_id, "code": cl["code"], "deleted_at": None})
        if existing:
            continue
        c = Clause(id=new_id(), tenant_id=tenant_id, language="it", active=True, **cl)
        await db.clauses.insert_one(to_mongo(c.model_dump(by_alias=True)))


async def run_pdf_seed(tenant_id: str):
    await seed_default_clauses(tenant_id)
    await seed_default_template(tenant_id)
