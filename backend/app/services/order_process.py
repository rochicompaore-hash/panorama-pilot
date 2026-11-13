"""One current task per sales order; handoff and history commit in one Mongo write."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from app import deps

AREAS = {
    "sales": "Commerciale", "administration": "Amministrazione",
    "coordination": "Coordinamento", "technical": "Ufficio tecnico",
    "purchasing": "Acquisti", "warehouse": "Magazzino",
    "installation": "Posa", "documents": "Documentazione",
}
# The order of these steps is part of the versioned procedure, not a UI preference.
STEPS = [
    ("contract", "sales", "Consegna contratto e allegati", "sales_orders.edit", "contract", "draft"),
    ("admin_survey", "administration", "Nulla osta al rilievo", "admin.payments.edit", "admin_survey", "confirmed"),
    ("survey_schedule", "coordination", "Fissa il rilievo", "surveys.assign", None, "confirmed"),
    ("survey", "technical", "Esegui il rilievo e consegna il fascicolo", "surveys.measure", None, "confirmed"),
    ("technical", "technical", "Verifica misure, varianti e revisione", "surveys.validate", "technical", "confirmed"),
    ("admin_order", "administration", "Autorizza la copertura dell’ordine", "admin.payments.edit", "admin_order", "technically_validated"),
    ("purchase", "purchasing", "Invia l’ordine con revisione identificata", "purchase_orders.edit", None, "waiting_materials"),
    ("supplier_confirmation", "purchasing", "Verifica conferma fornitore e data prevista", "purchase_orders.edit", None, "in_production"),
    ("materials", "warehouse", "Verifica tutte le righe, accessori e integrità", "logistics.edit", "materials", "completed"),
    ("admin_install", "administration", "Verifica condizioni contrattuali per la posa", "admin.payments.edit", "admin_install", "completed"),
    ("resources", "coordination", "Conferma posa, caposquadra, mezzi e accessi", "installation.edit", "resources", "ready_for_installation"),
    ("installation", "installation", "Esegui posa e registra rapporto e riserve", "installation.edit", None, "installed"),
    ("acceptance", "installation", "Concludi collaudo e completamenti", "installation.edit", "acceptance", "installed"),
    ("documents", "documents", "Raccogli la documentazione finale", "sales_orders.edit", "documents", "installed"),
    ("admin_close", "administration", "Verifica e chiudi la commessa", "admin.payments.edit", "admin_close", "closed"),
]
STEPS = [dict(zip(("key", "area", "label", "permission", "check", "order_status"), values)) for values in STEPS]
BY_KEY = {step["key"]: step for step in STEPS}
REVISION = "order-handoffs-v1"


async def permits(user, permission):
    if user.get("is_superadmin") or user.get("is_platform_owner"):
        return True
    keys = await deps.get_permission_keys_for_user(user)
    return "*" in keys or permission in keys


async def qualified_user(db, tenant_id, user_id, step):
    if not user_id:
        return None
    user = await db.users.find_one({"_id": user_id, "tenant_id": tenant_id, "deleted_at": None, "is_active": {"$ne": False}})
    if user and await permits(user, "sales_orders.view") and await permits(user, step["permission"]):
        return user
    return None


async def make_task(db, tenant_id, key, now=None):
    now = now or datetime.now(timezone.utc)
    step = BY_KEY[key]
    route = await db.order_process_routes.find_one({"_id": f"{tenant_id}:{key}", "tenant_id": tenant_id}) or {}
    owner = await qualified_user(db, tenant_id, route.get("owner_id"), step)
    hours = route.get("target_hours")
    return {"id": str(uuid4()), "step": key, "area": step["area"], "label": step["label"],
            "status": "pending", "owner_id": owner["_id"] if owner else None,
            "created_at": now.isoformat(), "due_at": (now + timedelta(hours=hours)).isoformat() if hours else None,
            "accepted_at": None, "block": ""}


def task_fields(task):
    return {"operational_enabled": True, "operational_process": {"revision": REVISION, "task": task},
            "operational_owner_id": task.get("owner_id"), "operational_next_action": task["label"],
            "operational_due_at": task.get("due_at"), "operational_block": task.get("block", "")}


def required_before(key):
    return [step["check"] for step in STEPS[:list(BY_KEY).index(key)] if step["check"]]


def rewind_fields(order, key, task):
    """Invalidate only dependent checks. History remains append-only."""
    index = list(BY_KEY).index(key)
    updates = task_fields(task)
    updates["order_status"] = STEPS[index - 1]["order_status"] if index else "draft"
    for step in STEPS[index:]:
        if step["check"]:
            updates[f"operational_checks.{step['check']}.satisfied"] = False
    return updates
