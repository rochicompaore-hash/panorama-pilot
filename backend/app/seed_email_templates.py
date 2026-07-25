"""Seed 11 canonical system email templates (tenant_id=None, is_system=true).

Idempotent: safe to run on every startup. Existing per-tenant customisations
(tenant_id != null) are never overwritten.
"""
from __future__ import annotations
from datetime import datetime, timezone
from app.db import get_db
from app.models import new_id


# Base HTML wrapper — inline style, mail-client safe
def _wrap(inner_html: str) -> str:
    return f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:600px;margin:0 auto;padding:24px;color:#111827;background:#ffffff">
{inner_html}
<hr style="border:none;border-top:1px solid #E4E4E7;margin:32px 0 12px" />
<p style="font-size:12px;color:#71717A;margin:0">{{{{ brand_name }}}} — Questa è una comunicazione automatica.</p>
</div>"""


TEMPLATES: list[dict] = [
    {
        "code": "USER_INVITATION",
        "description": "Invito nuovo utente ad accedere alla piattaforma",
        "subject": "Sei stato invitato in {{ company_name | default(brand_name) }}",
        "html_body": _wrap("""
<h2 style="margin:0 0 12px;color:#0F1720">Benvenuto in {{ company_name | default(brand_name) }}</h2>
<p>Ciao {{ first_name | default('') }}, sei stato invitato ad accedere a <b>{{ brand_name }}</b>.</p>
<p>Imposta la tua password cliccando il pulsante qui sotto. Il link è valido {{ expire_hours | default(72) }} ore.</p>
<p style="margin:24px 0"><a href="{{ invite_url }}" style="background:#09090B;color:#ffffff;padding:12px 24px;text-decoration:none;border-radius:6px;display:inline-block;font-weight:600">Imposta password</a></p>
<p style="font-size:13px;color:#52525B">Se il pulsante non funziona, copia questo link nel browser:<br /><span style="color:#0F1720">{{ invite_url }}</span></p>
"""),
        "text_body": """Benvenuto in {{ company_name | default(brand_name) }}

Ciao {{ first_name | default('') }}, sei stato invitato ad accedere a {{ brand_name }}.

Imposta la tua password al seguente link (valido {{ expire_hours | default(72) }} ore):
{{ invite_url }}
""",
    },
    {
        "code": "PASSWORD_RESET",
        "description": "Recupero password",
        "subject": "Recupero password — {{ brand_name }}",
        "html_body": _wrap("""
<h2 style="margin:0 0 12px;color:#0F1720">Recupero password</h2>
<p>Hai richiesto il recupero password su <b>{{ brand_name }}</b>.</p>
<p style="margin:24px 0"><a href="{{ reset_url }}" style="background:#D9381E;color:#ffffff;padding:12px 24px;text-decoration:none;border-radius:6px;display:inline-block;font-weight:600">Reimposta password</a></p>
<p style="font-size:13px;color:#52525B">Il link scade tra {{ expire_minutes | default(30) }} minuti. Se non hai fatto tu la richiesta, ignora questa email.</p>
"""),
        "text_body": """Recupero password

Hai richiesto il recupero password su {{ brand_name }}.

Segui il link (valido {{ expire_minutes | default(30) }} minuti):
{{ reset_url }}

Se non hai richiesto questa email, ignorala.
""",
    },
    {
        "code": "QUOTE_SENT",
        "description": "Invio preventivo al cliente",
        "subject": "Preventivo {{ quote_number }} — {{ company_name | default(brand_name) }}",
        "html_body": _wrap("""
<h2 style="margin:0 0 12px;color:#0F1720">Preventivo {{ quote_number }}</h2>
<p>Gentile {{ customer_name | default('cliente') }},</p>
<p>Le inviamo il preventivo <b>{{ quote_number }}</b>{% if total %} di importo <b>€ {{ total }}</b>{% endif %}.</p>
{% if quote_url %}<p style="margin:24px 0"><a href="{{ quote_url }}" style="background:#0F1720;color:#ffffff;padding:12px 24px;text-decoration:none;border-radius:6px;display:inline-block;font-weight:600">Visualizza preventivo</a></p>{% endif %}
<p>{{ message | default('Restiamo a disposizione per qualsiasi chiarimento.') }}</p>
<p style="margin-top:24px">Cordiali saluti,<br /><b>{{ company_name | default(brand_name) }}</b></p>
"""),
        "text_body": """Preventivo {{ quote_number }}

Gentile {{ customer_name | default('cliente') }},

Le inviamo il preventivo {{ quote_number }}{% if total %} di importo € {{ total }}{% endif %}.

{% if quote_url %}Visualizzi il preventivo: {{ quote_url }}{% endif %}

{{ message | default('Restiamo a disposizione per chiarimenti.') }}

{{ company_name | default(brand_name) }}
""",
    },
    {
        "code": "CONTRACT_SIGNATURE_REQUEST",
        "description": "Richiesta firma contratto",
        "subject": "Firma contratto {{ contract_number }} — {{ company_name | default(brand_name) }}",
        "html_body": _wrap("""
<h2 style="margin:0 0 12px;color:#0F1720">Contratto {{ contract_number }} pronto per la firma</h2>
<p>Gentile {{ customer_name | default('cliente') }},</p>
<p>Il contratto <b>{{ contract_number }}</b> è pronto per la firma elettronica.</p>
<p style="margin:24px 0"><a href="{{ signature_url }}" style="background:#059669;color:#ffffff;padding:12px 24px;text-decoration:none;border-radius:6px;display:inline-block;font-weight:600">Firma il contratto</a></p>
<p style="font-size:13px;color:#52525B">Il link scade {% if expires_at %}il <b>{{ expires_at }}</b>{% else %}tra 7 giorni{% endif %}. Assicurati di completare la firma entro tale data.</p>
"""),
        "text_body": """Contratto {{ contract_number }} pronto per la firma

Gentile {{ customer_name | default('cliente') }},

Il contratto {{ contract_number }} è pronto per la firma elettronica.

Firma qui: {{ signature_url }}

Il link scade {% if expires_at %}il {{ expires_at }}{% else %}tra 7 giorni{% endif %}.
""",
    },
    {
        "code": "CONTRACT_SIGNED",
        "description": "Conferma contratto firmato",
        "subject": "Contratto {{ contract_number }} firmato — {{ brand_name }}",
        "html_body": _wrap("""
<h2 style="margin:0 0 12px;color:#059669">Contratto firmato con successo</h2>
<p>Il contratto <b>{{ contract_number }}</b> è stato firmato in data <b>{{ signed_at | default('') }}</b>.</p>
{% if pdf_url %}<p style="margin:24px 0"><a href="{{ pdf_url }}" style="background:#0F1720;color:#ffffff;padding:12px 24px;text-decoration:none;border-radius:6px;display:inline-block;font-weight:600">Scarica PDF firmato</a></p>{% endif %}
<p style="font-size:13px;color:#52525B">Hash firma: <code style="background:#F4F4F5;padding:2px 6px;border-radius:3px">{{ signature_hash | default('—') | truncate(24, True) }}</code></p>
<p>Grazie per averci scelto.</p>
"""),
        "text_body": """Contratto firmato

Il contratto {{ contract_number }} è stato firmato in data {{ signed_at | default('') }}.

{% if pdf_url %}Scarica PDF firmato: {{ pdf_url }}{% endif %}

Hash firma: {{ signature_hash | default('—') }}
""",
    },
    {
        "code": "NEW_LEAD_NOTIFICATION",
        "description": "Notifica nuovo lead ricevuto dal sito",
        "subject": "Nuovo lead: {{ lead_name | default(lead_company | default('')) }}",
        "html_body": _wrap("""
<h2 style="margin:0 0 12px;color:#0F1720">Nuova richiesta di consulenza</h2>
<table style="border-collapse:collapse;width:100%;font-size:14px">
<tr><td style="padding:6px 0;color:#71717A">Nome</td><td style="padding:6px 0"><b>{{ lead_name | default('—') }}</b></td></tr>
<tr><td style="padding:6px 0;color:#71717A">Azienda</td><td style="padding:6px 0">{{ lead_company | default('—') }}</td></tr>
<tr><td style="padding:6px 0;color:#71717A">Email</td><td style="padding:6px 0"><a href="mailto:{{ lead_email }}">{{ lead_email | default('—') }}</a></td></tr>
<tr><td style="padding:6px 0;color:#71717A">Telefono</td><td style="padding:6px 0">{{ lead_phone | default('—') }}</td></tr>
<tr><td style="padding:6px 0;color:#71717A">Volume</td><td style="padding:6px 0">{{ revenue_range | default('—') }}</td></tr>
<tr><td style="padding:6px 0;color:#71717A">Pacchetto suggerito</td><td style="padding:6px 0">{{ suggested_package | default('—') }}</td></tr>
</table>
{% if notes %}<p style="margin-top:16px;padding:12px;background:#F4F4F5;border-radius:6px"><b>Note:</b><br />{{ notes }}</p>{% endif %}
{% if crm_lead_id %}<p style="font-size:13px;color:#52525B">CRM Lead ID: {{ crm_lead_id }}</p>{% endif %}
"""),
        "text_body": """Nuova richiesta di consulenza

Nome: {{ lead_name | default('—') }}
Azienda: {{ lead_company | default('—') }}
Email: {{ lead_email | default('—') }}
Telefono: {{ lead_phone | default('—') }}
Volume: {{ revenue_range | default('—') }}
Pacchetto suggerito: {{ suggested_package | default('—') }}
{% if notes %}Note: {{ notes }}{% endif %}
{% if crm_lead_id %}CRM Lead ID: {{ crm_lead_id }}{% endif %}
""",
    },
    {
        "code": "PAYMENT_REMINDER",
        "description": "Promemoria scadenza pagamento",
        "subject": "Promemoria pagamento {{ invoice_number }} — {{ company_name | default(brand_name) }}",
        "html_body": _wrap("""
<h2 style="margin:0 0 12px;color:#0F1720">Promemoria pagamento</h2>
<p>Gentile {{ customer_name | default('cliente') }},</p>
<p>La fattura <b>{{ invoice_number }}</b> di importo <b>€ {{ amount | default('—') }}</b> risulta {% if days_overdue %}in ritardo di <b>{{ days_overdue }} giorni</b>{% else %}in scadenza il <b>{{ due_date | default('') }}</b>{% endif %}.</p>
{% if payment_url %}<p style="margin:24px 0"><a href="{{ payment_url }}" style="background:#0F1720;color:#ffffff;padding:12px 24px;text-decoration:none;border-radius:6px;display:inline-block;font-weight:600">Paga ora</a></p>{% endif %}
<p>{{ message | default('La preghiamo di provvedere al pagamento nel più breve tempo possibile.') }}</p>
<p style="margin-top:24px">Cordiali saluti,<br /><b>{{ company_name | default(brand_name) }}</b></p>
"""),
        "text_body": """Promemoria pagamento

Gentile {{ customer_name | default('cliente') }},

La fattura {{ invoice_number }} di importo € {{ amount | default('—') }} risulta {% if days_overdue %}in ritardo di {{ days_overdue }} giorni{% else %}in scadenza il {{ due_date | default('') }}{% endif %}.

{% if payment_url %}Paga ora: {{ payment_url }}{% endif %}

{{ company_name | default(brand_name) }}
""",
    },
    {
        "code": "ORDER_STATUS_UPDATE",
        "description": "Aggiornamento stato ordine di produzione",
        "subject": "Ordine {{ order_number }} — {{ new_status | default('aggiornamento') }}",
        "html_body": _wrap("""
<h2 style="margin:0 0 12px;color:#0F1720">Aggiornamento ordine</h2>
<p>Gentile {{ customer_name | default('cliente') }},</p>
<p>L'ordine <b>{{ order_number }}</b> è passato allo stato <b style="color:#0F1720">{{ new_status | default('—') }}</b>{% if changed_at %} in data {{ changed_at }}{% endif %}.</p>
{% if estimated_completion %}<p>Data prevista di completamento: <b>{{ estimated_completion }}</b></p>{% endif %}
{% if order_url %}<p style="margin:24px 0"><a href="{{ order_url }}" style="background:#0F1720;color:#ffffff;padding:12px 24px;text-decoration:none;border-radius:6px;display:inline-block;font-weight:600">Vedi stato ordine</a></p>{% endif %}
"""),
        "text_body": """Aggiornamento ordine

Gentile {{ customer_name | default('cliente') }},

L'ordine {{ order_number }} è passato allo stato: {{ new_status | default('—') }}{% if changed_at %} in data {{ changed_at }}{% endif %}.

{% if estimated_completion %}Data prevista di completamento: {{ estimated_completion }}{% endif %}
{% if order_url %}Vedi stato ordine: {{ order_url }}{% endif %}
""",
    },
    {
        "code": "SUPPORT_TICKET_UPDATE",
        "description": "Aggiornamento ticket di assistenza",
        "subject": "Ticket {{ ticket_number }} — {{ update_type | default('aggiornamento') }}",
        "html_body": _wrap("""
<h2 style="margin:0 0 12px;color:#0F1720">Ticket #{{ ticket_number }}</h2>
<p>Gentile {{ customer_name | default('cliente') }},</p>
<p>Il ticket <b>{{ ticket_number }}</b> — <i>{{ ticket_title | default('') }}</i> — ha ricevuto un aggiornamento:</p>
<p style="padding:12px;background:#F4F4F5;border-left:3px solid #0F1720;border-radius:0 6px 6px 0">{{ update_message | default('') }}</p>
{% if new_status %}<p>Nuovo stato: <b>{{ new_status }}</b></p>{% endif %}
{% if ticket_url %}<p style="margin:24px 0"><a href="{{ ticket_url }}" style="background:#0F1720;color:#ffffff;padding:12px 24px;text-decoration:none;border-radius:6px;display:inline-block;font-weight:600">Vedi ticket</a></p>{% endif %}
"""),
        "text_body": """Ticket #{{ ticket_number }}

Gentile {{ customer_name | default('cliente') }},

Il ticket {{ ticket_number }} — {{ ticket_title | default('') }} — ha un aggiornamento:

{{ update_message | default('') }}

{% if new_status %}Nuovo stato: {{ new_status }}{% endif %}
{% if ticket_url %}Vedi ticket: {{ ticket_url }}{% endif %}
""",
    },
    {
        "code": "AI_CFO_ALERT",
        "description": "Alert dal modulo AI CFO (cash-flow, margini, scadenze)",
        "subject": "AI CFO — {{ alert_title | default('nuovo alert') }}",
        "html_body": _wrap("""
<h2 style="margin:0 0 12px;color:#D9381E">⚠ Alert AI CFO</h2>
<p><b>{{ alert_title | default('Attenzione') }}</b></p>
<p>{{ alert_message | default('') }}</p>
{% if severity %}<p>Gravità: <b style="text-transform:uppercase">{{ severity }}</b></p>{% endif %}
{% if metrics %}<table style="border-collapse:collapse;width:100%;font-size:14px;margin-top:12px">
{% for k, v in metrics.items() %}<tr><td style="padding:6px 0;color:#71717A">{{ k }}</td><td style="padding:6px 0"><b>{{ v }}</b></td></tr>{% endfor %}
</table>{% endif %}
{% if action_url %}<p style="margin:24px 0"><a href="{{ action_url }}" style="background:#D9381E;color:#ffffff;padding:12px 24px;text-decoration:none;border-radius:6px;display:inline-block;font-weight:600">Rivedi in AI CFO</a></p>{% endif %}
"""),
        "text_body": """AI CFO — Alert

{{ alert_title | default('Attenzione') }}

{{ alert_message | default('') }}

{% if severity %}Gravità: {{ severity | upper }}{% endif %}
{% if action_url %}Vedi dettagli: {{ action_url }}{% endif %}
""",
    },
    {
        "code": "DAILY_SUMMARY",
        "description": "Riepilogo giornaliero attività",
        "subject": "Riepilogo giornaliero — {{ report_date | default('oggi') }}",
        "html_body": _wrap("""
<h2 style="margin:0 0 12px;color:#0F1720">Riepilogo del {{ report_date | default('') }}</h2>
<p>Ciao {{ user_first_name | default('') }}, ecco il riepilogo giornaliero.</p>
<table style="border-collapse:collapse;width:100%;font-size:14px;margin-top:12px">
<tr><td style="padding:8px 0;border-bottom:1px solid #E4E4E7;color:#71717A">Nuovi lead</td><td style="padding:8px 0;border-bottom:1px solid #E4E4E7;text-align:right"><b>{{ new_leads | default(0) }}</b></td></tr>
<tr><td style="padding:8px 0;border-bottom:1px solid #E4E4E7;color:#71717A">Preventivi inviati</td><td style="padding:8px 0;border-bottom:1px solid #E4E4E7;text-align:right"><b>{{ quotes_sent | default(0) }}</b></td></tr>
<tr><td style="padding:8px 0;border-bottom:1px solid #E4E4E7;color:#71717A">Contratti firmati</td><td style="padding:8px 0;border-bottom:1px solid #E4E4E7;text-align:right"><b>{{ contracts_signed | default(0) }}</b></td></tr>
<tr><td style="padding:8px 0;border-bottom:1px solid #E4E4E7;color:#71717A">Fatturato oggi</td><td style="padding:8px 0;border-bottom:1px solid #E4E4E7;text-align:right"><b>€ {{ revenue_today | default('0') }}</b></td></tr>
<tr><td style="padding:8px 0;color:#71717A">Scadenze pendenti</td><td style="padding:8px 0;text-align:right"><b>{{ pending_deadlines | default(0) }}</b></td></tr>
</table>
{% if dashboard_url %}<p style="margin:24px 0"><a href="{{ dashboard_url }}" style="background:#0F1720;color:#ffffff;padding:12px 24px;text-decoration:none;border-radius:6px;display:inline-block;font-weight:600">Apri dashboard</a></p>{% endif %}
"""),
        "text_body": """Riepilogo del {{ report_date | default('') }}

Ciao {{ user_first_name | default('') }},

- Nuovi lead: {{ new_leads | default(0) }}
- Preventivi inviati: {{ quotes_sent | default(0) }}
- Contratti firmati: {{ contracts_signed | default(0) }}
- Fatturato oggi: € {{ revenue_today | default('0') }}
- Scadenze pendenti: {{ pending_deadlines | default(0) }}

{% if dashboard_url %}Apri dashboard: {{ dashboard_url }}{% endif %}
""",
    },
]


async def run_email_templates_seed() -> dict:
    """Seed system email templates (tenant_id=None, is_system=True). Idempotent.

    Per-tenant custom templates (tenant_id != None) are NEVER touched.
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    skipped = 0
    for t in TEMPLATES:
        existing = await db.email_templates.find_one({
            "tenant_id": None, "is_system": True, "code": t["code"], "deleted_at": None,
        })
        if existing:
            skipped += 1
            continue
        doc = {
            "_id": new_id(),
            "tenant_id": None,
            "code": t["code"],
            "subject": t["subject"],
            "html_body": t["html_body"],
            "text_body": t["text_body"],
            "description": t.get("description", ""),
            "version": 1,
            "is_system": True,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
            "created_by": "system:seed",
        }
        await db.email_templates.insert_one(doc)
        inserted += 1
    return {"inserted": inserted, "skipped": skipped, "total": len(TEMPLATES)}
