"""Permission catalog for Infissi Express Cloud.
Format: module.action  (e.g. users.create)
"""

PERMISSION_CATALOG = [
    # Users
    ("users.view", "Utenti", "view", "Visualizza elenco utenti"),
    ("users.create", "Utenti", "create", "Crea utenti e inviti"),
    ("users.edit", "Utenti", "edit", "Modifica utenti"),
    ("users.delete", "Utenti", "delete", "Disattiva utenti"),
    ("users.manage", "Utenti", "manage_users", "Gestione avanzata utenti (reset, sblocco)"),
    # Roles
    ("roles.view", "Ruoli", "view", "Visualizza ruoli"),
    ("roles.manage", "Ruoli", "manage_roles", "Crea/Modifica/Elimina ruoli e permessi"),
    # Company
    ("company.view", "Azienda", "view", "Visualizza dati azienda"),
    ("company.edit", "Azienda", "edit", "Modifica dati azienda e configurazioni"),
    # Audit
    ("audit.view", "Audit", "view_audit", "Consulta audit log"),
    ("audit.export", "Audit", "export", "Esporta audit log"),
    # Attachments
    ("attachments.view", "Allegati", "view", "Visualizza allegati"),
    ("attachments.create", "Allegati", "create", "Carica allegati"),
    ("attachments.download", "Allegati", "download_attachments", "Scarica allegati"),
    ("attachments.delete", "Allegati", "delete", "Elimina allegati"),
    # Sequences
    ("sequences.view", "Numerazioni", "view", "Visualizza numerazioni"),
    ("sequences.manage", "Numerazioni", "edit", "Gestisce numerazioni"),
    # Notifications
    ("notifications.view", "Notifiche", "view", "Visualizza notifiche"),
    # Dashboard
    ("dashboard.view", "Dashboard", "view", "Visualizza dashboard"),
    # Search
    ("search.global", "Ricerca", "view", "Utilizza ricerca globale"),
    # Financials
    ("financials.view", "Economici", "view_financials", "Visualizza dati economici"),
    ("margins.view", "Margini", "view_margins", "Visualizza margini"),
    # Sessions
    ("sessions.view", "Sessioni", "view", "Visualizza sessioni attive"),
    ("sessions.revoke", "Sessioni", "manage_users", "Revoca sessioni"),
    # Approve / Assign / State (future ERP-wide)
    ("workflow.approve", "Workflow", "approve", "Approva documenti"),
    ("workflow.assign", "Workflow", "assign", "Assegna incarichi"),
    ("workflow.change_status", "Workflow", "change_status", "Modifica stato documenti"),
    ("workflow.export", "Workflow", "export", "Esporta dati"),
    # CRM - Leads
    ("crm.leads.view", "CRM Lead", "view", "Visualizza lead"),
    ("crm.leads.create", "CRM Lead", "create", "Crea lead"),
    ("crm.leads.edit", "CRM Lead", "edit", "Modifica lead"),
    ("crm.leads.delete", "CRM Lead", "delete", "Elimina lead"),
    ("crm.leads.assign", "CRM Lead", "assign", "Assegna lead ad un commerciale"),
    ("crm.leads.convert", "CRM Lead", "approve", "Converti lead in cliente"),
    # CRM - Customers
    ("crm.customers.view", "CRM Clienti", "view", "Visualizza clienti"),
    ("crm.customers.create", "CRM Clienti", "create", "Crea clienti"),
    ("crm.customers.edit", "CRM Clienti", "edit", "Modifica clienti"),
    ("crm.customers.delete", "CRM Clienti", "delete", "Elimina clienti"),
    # CRM - Contacts
    ("crm.contacts.view", "CRM Contatti", "view", "Visualizza contatti"),
    ("crm.contacts.manage", "CRM Contatti", "edit", "Gestisce contatti"),
    # CRM - Pipelines
    ("crm.pipelines.view", "CRM Pipeline", "view", "Visualizza pipeline"),
    ("crm.pipelines.manage", "CRM Pipeline", "edit", "Gestisce pipeline"),
    # CRM - Activities / Timeline
    ("crm.activities.view", "CRM Timeline", "view", "Visualizza timeline attività"),
    ("crm.activities.create", "CRM Timeline", "create", "Registra attività"),
    # CRM - Comms
    ("crm.comms.email", "Comunicazioni", "create", "Invia email"),
    ("crm.comms.whatsapp", "Comunicazioni", "create", "Invia WhatsApp"),
    ("crm.comms.call", "Comunicazioni", "create", "Registra telefonata"),
    # CRM - Tasks
    ("crm.tasks.view", "Task", "view", "Visualizza task"),
    ("crm.tasks.manage", "Task", "edit", "Gestisce task"),
    # CRM - Appointments
    ("crm.appointments.view", "Appuntamenti", "view", "Visualizza appuntamenti"),
    ("crm.appointments.manage", "Appuntamenti", "edit", "Gestisce appuntamenti"),
    # CRM - Sales targets
    ("crm.goals.view", "Obiettivi", "view", "Visualizza obiettivi"),
    ("crm.goals.manage", "Obiettivi", "edit", "Gestisce obiettivi"),
    ("crm.commissions.view", "Provvigioni", "view", "Visualizza provvigioni"),
    ("crm.commissions.manage", "Provvigioni", "edit", "Gestisce provvigioni"),
    # Onboarding
    ("onboarding.access", "Onboarding", "view", "Accesso wizard onboarding"),
    # Quotes (M3)
    ("quotes.view", "Preventivi", "view", "Visualizza preventivi"),
    ("quotes.create", "Preventivi", "create", "Crea preventivi"),
    ("quotes.edit", "Preventivi", "edit", "Modifica preventivi"),
    ("quotes.delete", "Preventivi", "delete", "Elimina preventivi"),
    ("quotes.send", "Preventivi", "create", "Invia preventivi"),
    ("quotes.approve", "Preventivi", "approve", "Approva preventivi"),
    ("quotes.export", "Preventivi", "export", "Esporta preventivi"),
    ("quotes.view_costs", "Preventivi", "view_financials", "Visualizza costi interni preventivi"),
    ("quotes.view_margins", "Preventivi", "view_margins", "Visualizza marginalità preventivi"),
    ("quotes.edit_prices", "Preventivi", "edit", "Modifica prezzi manualmente"),
    ("quotes.apply_discount", "Preventivi", "edit", "Applica sconti"),
    ("quotes.override_discount", "Preventivi", "approve", "Sconto oltre soglia (bypass approvazione)"),
    ("quotes.convert_contract", "Preventivi", "approve", "Converte preventivo in contratto"),
    # Pricelists
    ("pricelists.view", "Listini", "view", "Visualizza listini"),
    ("pricelists.manage", "Listini", "edit", "Gestisce listini e regole prezzo"),
    # Products
    ("products.view", "Prodotti", "view", "Visualizza catalogo prodotti"),
    ("products.manage", "Prodotti", "edit", "Gestisce catalogo prodotti"),
    # Contracts
    ("contracts.view", "Contratti", "view", "Visualizza contratti"),
    ("contracts.create", "Contratti", "create", "Crea contratti"),
    ("contracts.sign", "Contratti", "approve", "Firma contratti"),
    ("contracts.cancel", "Contratti", "delete", "Annulla contratti"),
    # Records governance / concurrency
    ("records.force_override", "Record", "approve", "Sovrascrittura forzata con motivazione (bypass concorrenza)"),
    # PDF & Templates (M3.3.2)
    ("quotes.preview_pdf", "Preventivi", "view", "Anteprima PDF bozza"),
    ("quotes.generate_pdf", "Preventivi", "approve", "Emette PDF definitivo con snapshot immutabile"),
    ("quotes.download_pdf", "Preventivi", "view", "Scarica PDF definitivo"),
    ("quotes.invalidate_pdf", "Preventivi", "approve", "Annulla PDF definitivo"),
    ("quotes.manage_templates", "Preventivi", "create", "Gestisce template PDF preventivi"),
    ("quotes.manage_clauses", "Preventivi", "create", "Gestisce libreria clausole contrattuali"),
    # Public links (M3.3.3)
    ("quotes.public_link.create", "Preventivi", "create", "Crea link pubblico read-only"),
    ("quotes.public_link.view", "Preventivi", "view", "Visualizza link pubblici emessi"),
    ("quotes.public_link.revoke", "Preventivi", "approve", "Revoca link pubblico con motivazione"),
    ("quotes.public_link.regenerate", "Preventivi", "approve", "Rigenera link pubblico (revoca+crea)"),
    ("quotes.public_link.configure", "Preventivi", "create", "Configura durata/OTP/max accessi"),
    ("quotes.public_access_logs.view", "Preventivi", "view", "Visualizza log accessi portale pubblico"),
    # Public portal actions (M3.3.4)
    ("quotes.public_action.review", "Preventivi", "view", "Visualizza azioni cliente dal portale (richieste modifica, rifiuti)"),
    ("quotes.public_action.take_over", "Preventivi", "edit", "Prendi in carico richieste cliente dal portale"),
    ("quotes.public_action.close", "Preventivi", "approve", "Chiudi richieste cliente dal portale"),
    ("quotes.reopen", "Preventivi", "approve", "Riapri preventivo rifiutato"),
    # OTP debug (M3.3.4) — dev/test only
    ("debug.otp.read", "Debug", "view", "Legge OTP mock in ambiente dev/test"),
    # M4 — Rilievo tecnico
    ("surveys.view", "Rilievo", "view", "Visualizza rilievi tecnici"),
    ("surveys.create", "Rilievo", "create", "Crea rilievi tecnici"),
    ("surveys.edit", "Rilievo", "edit", "Modifica rilievi tecnici"),
    ("surveys.delete", "Rilievo", "delete", "Elimina rilievi tecnici"),
    # M5 — Sales orders / Purchasing
    ("sales_orders.view", "Ordini cliente", "view", "Visualizza ordini cliente"),
    ("sales_orders.create", "Ordini cliente", "create", "Crea ordini cliente"),
    ("sales_orders.edit", "Ordini cliente", "edit", "Modifica ordini cliente"),
    ("sales_orders.delete", "Ordini cliente", "delete", "Elimina ordini cliente"),
    ("suppliers.view", "Fornitori", "view", "Visualizza fornitori"),
    ("suppliers.create", "Fornitori", "create", "Crea fornitori"),
    ("suppliers.edit", "Fornitori", "edit", "Modifica fornitori"),
    ("suppliers.delete", "Fornitori", "delete", "Elimina fornitori"),
    ("purchase_orders.view", "Ordini fornitore", "view", "Visualizza ordini fornitore"),
    ("purchase_orders.create", "Ordini fornitore", "create", "Crea ordini fornitore"),
    ("purchase_orders.edit", "Ordini fornitore", "edit", "Modifica ordini fornitore"),
    # M6 — Magazzino
    ("items.view", "Magazzino", "view", "Visualizza articoli e giacenze"),
    ("items.create", "Magazzino", "create", "Crea articoli"),
    ("items.edit", "Magazzino", "edit", "Modifica articoli, movimenti, inventari"),
    ("items.delete", "Magazzino", "delete", "Elimina articoli"),
    # M7-M8 — Produzione
    ("production.view", "Produzione", "view", "Visualizza produzione"),
    ("production.edit", "Produzione", "edit", "Gestisce produzione, BOM, tagli"),
    # M9 — QC
    ("qc.view", "Qualità", "view", "Visualizza controlli qualità"),
    ("qc.edit", "Qualità", "edit", "Registra controlli qualità e non conformità"),
    # M10-M12 — Logistica/Posa
    ("logistics.view", "Logistica", "view", "Visualizza logistica e spedizioni"),
    ("logistics.edit", "Logistica", "edit", "Gestisce logistica"),
    ("installation.view", "Posa", "view", "Visualizza pianificazione posa"),
    ("installation.edit", "Posa", "edit", "Pianifica e registra posa"),
    # M13 — Assistenza
    ("service.view", "Assistenza", "view", "Visualizza ticket assistenza"),
    ("service.create", "Assistenza", "create", "Apre ticket assistenza"),
    ("service.edit", "Assistenza", "edit", "Gestisce ticket assistenza"),
    # M14 — Amministrazione
    ("admin.payments.view", "Amministrazione", "view", "Visualizza piani pagamenti"),
    ("admin.payments.edit", "Amministrazione", "edit", "Gestisce pagamenti e piani"),
    ("admin.invoices.view", "Amministrazione", "view", "Visualizza fatture"),
    ("admin.invoices.edit", "Amministrazione", "edit", "Gestisce fatture"),
    # M16 — BI
    ("bi.direction.view", "BI Direzione", "view", "Visualizza dashboard direzione"),
    # M17 — AI CFO
    ("ai_cfo.view", "AI CFO", "view", "Visualizza suggerimenti AI CFO"),
    ("ai_cfo.generate", "AI CFO", "edit", "Rigenera suggerimenti AI CFO"),
    # Parametric Engine (M6.PAR) — BOM parametrica, matrici, modalità pricing A/B/C
    ("pricing.mode.view", "Pricing Modalità", "view", "Visualizza modalità pricing applicata"),
    ("pricing.mode.override", "Pricing Modalità", "approve", "Override modalità sulla riga (con motivazione)"),
    ("pricing.mode.manage_defaults", "Pricing Modalità", "edit", "Gestisce default modalità (tenant/prodotto/sistema)"),
    ("pricing.mode.view_cost_basis", "Pricing Modalità", "view_financials", "Visualizza base di costo (BOM/listino costo)"),
    ("parametric.bom.view", "BOM Parametrica", "view", "Visualizza template BOM parametrici"),
    ("parametric.bom.manage", "BOM Parametrica", "edit", "Gestisce template BOM e formule"),
    ("parametric.matrix.view", "Matrici Prezzo", "view", "Visualizza matrici prezzi"),
    ("parametric.matrix.manage", "Matrici Prezzo", "edit", "Gestisce matrici prezzi"),
    ("parametric.color.manage", "Categorie Colore", "edit", "Gestisce categorie colore e policy residui"),
    ("parametric.nesting.run", "Nesting 1D", "edit", "Esegue algoritmi FFD/BFD"),
    ("parametric.svg.generate", "Disegno SVG", "view", "Genera disegni SVG parametrici"),
    # M6.WORKFLOW — flusso end-to-end preventivo → abaco → produzione → cliente
    ("contracts.generate", "Contratti", "edit", "Genera contratto da preventivo accettato"),
    ("contracts.send", "Contratti", "edit", "Invia contratto al cliente"),
    ("contracts.view_signed", "Contratti", "view", "Visualizza contratto firmato"),
    ("surveys.manage", "Rilievo tecnico", "edit", "Gestisce campagna rilievi"),
    ("surveys.validate", "Rilievo tecnico", "approve", "Valida rilievo tecnico completato"),
    ("surveys.measure", "Rilievo tecnico", "edit", "Modifica misure tecniche definitive"),
    ("surveys.assign", "Rilievo tecnico", "edit", "Assegna rilievo a tecnico"),
    ("surveys.generate_schedule", "Rilievo tecnico", "edit", "Genera abaco tecnico dal rilievo"),
    ("surveys.send_to_customer", "Rilievo tecnico", "edit", "Invia abaco al cliente"),
    ("surveys.override_locked", "Rilievo tecnico", "approve", "Override rilievo bloccato"),
    ("surveys.view_variances", "Rilievo tecnico", "view", "Visualizza differenze quote/rilievo"),
    ("technical_schedules.create", "Abaco tecnico", "create", "Crea abaco tecnico"),
    ("technical_schedules.edit", "Abaco tecnico", "edit", "Modifica abaco"),
    ("technical_schedules.approve", "Abaco tecnico", "approve", "Approva abaco internamente"),
    ("technical_schedules.send", "Abaco tecnico", "edit", "Invia abaco al cliente"),
    ("technical_schedules.sign", "Abaco tecnico", "approve", "Firma abaco (interna, non FES)"),
    ("technical_schedules.release", "Abaco tecnico", "approve", "Rilascia abaco alla produzione"),
    ("production.release", "Produzione", "approve", "Esegue release check produzione"),
    ("production.override_release", "Produzione", "approve", "Override manuale release produzione"),
    ("customer_portal.manage_tracking", "Portale cliente", "edit", "Gestisce dati tracking cliente"),
    ("customer_portal.manage_visibility", "Portale cliente", "edit", "Gestisce mapping stato cliente"),
    # M6.OPS — handoff, commissioni, redditività, lead intake, inbox
    ("dashboard.view", "Dashboard", "view", "Visualizza dashboard aziendale"),
    ("profitability.view", "Redditività", "view_financials", "Visualizza redditività commesse"),
    ("profitability.view_breakdown", "Redditività", "view_financials", "Visualizza breakdown costi per redditività"),
    ("profitability.configure", "Redditività", "edit", "Configura formula/soglie redditività"),
    ("profitability.override", "Redditività", "approve", "Override soglie redditività"),
    ("commission.view_own", "Commissioni", "view", "Visualizza proprie commissioni"),
    ("commission.view_team", "Commissioni", "view", "Visualizza commissioni del team"),
    ("commission.manage", "Commissioni", "edit", "Gestisce piani/regole commissionali"),
    ("commission.approve", "Commissioni", "approve", "Approva/rifiuta fatture commissioni"),
    ("commission.invoice", "Commissioni", "edit", "Carica fatture commissioni proprie"),
    ("commission.pay", "Commissioni", "approve", "Registra pagamento fatture commissioni"),
    ("handoff.view", "Passaggi", "view", "Visualizza pratiche in passaggio"),
    ("handoff.reassign", "Passaggi", "edit", "Riassegna handoff con motivazione"),
    ("leads.webhook.manage", "Lead Intake", "edit", "Gestisce configurazioni webhook lead"),
]

# Predefined roles with permissions
PREDEFINED_ROLES = {
    "super_admin": {
        "name": "Super Admin",
        "description": "Amministratore di sistema con accesso completo (cross-tenant)",
        "is_system": True,
        "permissions": "*",  # all
    },
    "admin_azienda": {
        "name": "Admin Azienda",
        "description": "Amministratore dell'azienda con controllo completo del tenant",
        "is_system": True,
        "permissions": "*",
    },
    "commerciale": {
        "name": "Commerciale",
        "description": "Ruolo commerciale (CRM completo, preventivi in M3)",
        "is_system": True,
        "permissions": [
            "dashboard.view", "notifications.view", "search.global",
            "attachments.view", "attachments.create", "attachments.download",
            "financials.view", "workflow.assign", "workflow.change_status",
            "crm.leads.view", "crm.leads.create", "crm.leads.edit", "crm.leads.assign", "crm.leads.convert",
            "crm.customers.view", "crm.customers.create", "crm.customers.edit",
            "crm.contacts.view", "crm.contacts.manage",
            "crm.pipelines.view",
            "crm.activities.view", "crm.activities.create",
            "crm.comms.email", "crm.comms.whatsapp", "crm.comms.call",
            "crm.tasks.view", "crm.tasks.manage",
            "crm.appointments.view", "crm.appointments.manage",
            "crm.goals.view", "crm.commissions.view",
            "onboarding.access",
            "quotes.view", "quotes.create", "quotes.edit", "quotes.send", "quotes.apply_discount",
            "quotes.convert_contract",
            "pricelists.view", "products.view",
            "contracts.view", "contracts.create",
        ],
    },
    "tecnico_rilievo": {
        "name": "Tecnico Rilievo",
        "description": "Tecnico rilevatore misure",
        "is_system": True,
        "permissions": [
            "dashboard.view", "notifications.view", "search.global",
            "attachments.view", "attachments.create", "attachments.download",
        ],
    },
    "produzione": {
        "name": "Produzione",
        "description": "Operatore/responsabile produzione",
        "is_system": True,
        "permissions": [
            "dashboard.view", "notifications.view", "search.global",
            "attachments.view", "attachments.download",
            "workflow.change_status",
        ],
    },
    "magazzino": {
        "name": "Magazzino",
        "description": "Gestione magazzino",
        "is_system": True,
        "permissions": [
            "dashboard.view", "notifications.view", "search.global",
            "attachments.view", "attachments.download",
        ],
    },
    "posatore": {
        "name": "Posatore",
        "description": "Squadra posa",
        "is_system": True,
        "permissions": [
            "dashboard.view", "notifications.view",
            "attachments.view", "attachments.create", "attachments.download",
        ],
    },
    "amministrazione": {
        "name": "Amministrazione",
        "description": "Contabilità e amministrazione",
        "is_system": True,
        "permissions": [
            "dashboard.view", "notifications.view", "search.global",
            "attachments.view", "attachments.create", "attachments.download",
            "financials.view", "margins.view", "audit.view", "workflow.export",
        ],
    },
    "cliente": {
        "name": "Cliente",
        "description": "Cliente finale (portale futuro)",
        "is_system": True,
        "permissions": [
            "dashboard.view", "notifications.view",
            "attachments.view", "attachments.download",
        ],
    },
    "viewer": {
        "name": "Viewer",
        "description": "Sola lettura",
        "is_system": True,
        "permissions": [
            "dashboard.view", "notifications.view", "search.global",
            "attachments.view", "users.view", "roles.view", "company.view",
            "audit.view", "sequences.view",
        ],
    },
}
