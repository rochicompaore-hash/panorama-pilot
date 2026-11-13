"""Evidence-based operating checks on existing sales orders; no duplicate ledger."""
from datetime import datetime, timedelta, timezone

CHECKS = {
    "contract": ("Contratto e allegati verificati", "sales_orders.edit"),
    "admin_survey": ("Nulla osta amministrativo al rilievo", "admin.payments.edit"),
    "technical": ("Rilievo e revisione tecnica validati", "surveys.validate"),
    "admin_order": ("Copertura e nulla osta all’ordine verificati", "admin.payments.edit"),
    "materials": ("Tutte le righe e gli accessori integri e utilizzabili", "logistics.edit"),
    "admin_install": ("Condizioni contrattuali per la posa verificate", "admin.payments.edit"),
    "resources": ("Squadra, mezzi e accessi confermati", "installation.edit"),
    "acceptance": ("Collaudo e completamenti conclusi", "installation.edit"),
    "documents": ("Documentazione finale completa", "sales_orders.edit"),
    "admin_close": ("Chiusura amministrativa verificata", "admin.payments.edit"),
}
STATES = {
    "draft": "Apertura commessa", "confirmed": "Rilievo da completare",
    "technically_validated": "Ordine validato", "waiting_materials": "Attesa materiali",
    "ready_for_production": "Fornitura autorizzata", "in_production": "Fornitura in corso",
    "completed": "Fornitura completata", "ready_for_installation": "Posa confermata",
    "installed": "Posa eseguita / completamenti", "closed": "Commessa chiusa", "cancelled": "Annullata",
}
BASE = ["contract", "admin_survey"]
TECH = BASE + ["technical", "admin_order"]
INSTALL = TECH + ["materials", "admin_install", "resources"]
REQUIRED = {
    "confirmed": BASE, "technically_validated": TECH, "waiting_materials": TECH,
    "ready_for_production": TECH, "in_production": TECH, "completed": TECH,
    "ready_for_installation": INSTALL, "installed": INSTALL,
    "closed": INSTALL + ["acceptance", "documents", "admin_close"],
}
FINANCE_STATES = ["none", "submitted", "review", "approved", "signed", "liquidation_requested", "disbursed"]
FINANCE_LABELS = ["Non prevista", "Inviata", "In valutazione", "Approvata", "Sottoscritta", "Liquidazione richiesta", "Erogata"]
PRIORITIES = {"red": 2, "orange": 15, "green": 30}
LEGACY_PRIORITY = {"urgent": "red", "high": "orange", "normal": "orange", "low": "green"}


def as_datetime(value):
    if not value:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def missing_checks(order, target):
    if not order.get("operational_enabled") or target == "cancelled":
        return []
    checks = order.get("operational_checks") or {}
    missing = [CHECKS[k][0] for k in REQUIRED.get(target, []) if not checks.get(k, {}).get("satisfied")]
    if target != "draft":
        if not order.get("operational_owner_id"):
            missing.append("Responsabile della commessa")
        if order.get("operational_block"):
            missing.append("Blocco aperto: " + order["operational_block"])
    if target not in ("closed", "draft"):
        if not order.get("operational_next_action") or not as_datetime(order.get("operational_due_at")):
            missing.append("Prossima azione e scadenza")
    if order.get("payment_mode") == "financed" and target in REQUIRED:
        if order.get("financing_status") not in ("signed", "liquidation_requested", "disbursed"):
            missing.append("Finanziamento effettivamente approvato e sottoscritto")
    if target == "closed" and order.get("operational_residuals", 0):
        missing.append("Completamenti ancora aperti")
    return missing


def order_summary(order, now=None):
    now = now or datetime.now(timezone.utc)
    due = as_datetime(order.get("operational_due_at"))
    terminal = order.get("order_status") in ("closed", "cancelled")
    return {
        "managed": bool(order.get("operational_enabled")),
        "overdue": bool(due and due < now and not terminal),
        "unassigned": not bool(order.get("operational_owner_id")) and not terminal,
        "blocked": bool(order.get("operational_block")) and not terminal,
        "stage_label": STATES.get(order.get("order_status"), order.get("order_status", "draft")),
        "invalidated": missing_checks(order, order.get("order_status", "draft")),
    }


def ticket_clock(ticket, now=None, new_priority=None):
    now = now or datetime.now(timezone.utc)
    priority = new_priority or ticket.get("priority", "normal")
    color = LEGACY_PRIORITY.get(priority, priority)
    if color not in PRIORITIES:
        color = "orange"
    first = as_datetime(ticket.get("first_reported_at")) or as_datetime(ticket.get("created_at"))
    if first is None:
        return {"color": color, "first_reported_at": None, "due_at": None, "overdue": False, "missing_origin": True}
    baseline = first + timedelta(days=PRIORITIES[color])
    old_color = LEGACY_PRIORITY.get(ticket.get("priority", "normal"), ticket.get("priority", "orange"))
    previous = as_datetime(ticket.get("service_due_at"))
    changing_color = new_priority and color != old_color
    if changing_color and old_color in PRIORITIES:
        previous = previous or first + timedelta(days=PRIORITIES[old_color])
        if color == "red" and old_color != "red":
            baseline = now + timedelta(hours=48)
    # Reclassification never postpones a previous deadline. Waiting states do not stop the clock.
    due = (min(previous, baseline) if changing_color else previous) if previous else baseline
    terminal = ticket.get("ticket_status") in ("resolved", "closed", "rejected")
    return {"color": color, "first_reported_at": first.isoformat(), "due_at": due.isoformat(),
            "overdue": due < now and not terminal, "missing_origin": False}


def safe_csv(value):
    value = "" if value is None else str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")) else value
