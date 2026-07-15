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
        "description": "Ruolo commerciale (preparato per moduli futuri CRM/preventivi)",
        "is_system": True,
        "permissions": [
            "dashboard.view", "notifications.view", "search.global",
            "attachments.view", "attachments.create", "attachments.download",
            "financials.view", "workflow.assign", "workflow.change_status",
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
