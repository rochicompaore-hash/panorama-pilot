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
