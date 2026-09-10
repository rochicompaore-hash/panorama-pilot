"""CUSTOMER EMAIL NOTIFICATIONS V1 (PO msg 794) — collega eventi cliente GIÀ esistenti al servizio email centrale.

Regole: recipient risolto server-side (customer_portal_users AUTHORIZED → customers.email), mai dal frontend;
tenant/customer ownership verificata; branding tenant (Company Settings); idempotency per evento; il fallimento SMTP
non blocca l'operazione business (EMAIL_SEND_FAILED nel log, retry gestito dal servizio email).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.config import settings
from app.services.email import send_email

logger = logging.getLogger("customer_email_events")

# quote_status -> evento customer-facing (Customer Timeline mapping già esistente in customer_portal.CUSTOMER_STATUS_LABELS)
ORDER_STATUS_EVENTS = {
    "accepted": ("ORDER_STATUS_CHANGED", "Preventivo accettato", "Abbiamo registrato l'accettazione del tuo preventivo: la commessa è in attesa di avvio ordine."),
    "converted": ("ORDER_STATUS_CHANGED", "Ordine confermato", "Il tuo ordine è stato confermato. Seguirai gli avanzamenti nella tua area cliente."),
}


async def _resolve_recipient(db, tenant_id: str, customer_id: str) -> Optional[str]:
    cust = await db.customers.find_one({"_id": customer_id, "tenant_id": tenant_id, "deleted_at": None}, {"email": 1})
    if not cust:
        return None  # ownership non verificata → nessun invio
    pu = await db.customer_portal_users.find_one({"tenant_id": tenant_id, "customer_id": customer_id, "status": "AUTHORIZED", "deleted_at": None}, {"email": 1})
    return (pu or {}).get("email") or cust.get("email")


async def _brand(db, tenant_id: str) -> Dict[str, Any]:
    c = await db.companies.find_one({"_id": tenant_id}, {"name": 1, "legal_name": 1, "email": 1, "phone": 1}) or {}
    return {"name": c.get("name") or c.get("legal_name") or "La tua azienda", "email": c.get("email"), "phone": c.get("phone")}


async def notify_customer_event(db, *, tenant_id: str, customer_id: Optional[str], event_type: str, entity_type: str, entity_id: str,
                                title: str, body: str, cta_label: str = "Accedi alla tua area cliente", cta_path: str = "/customer-portal",
                                dedupe_suffix: str = "") -> Optional[str]:
    """Ritorna l'id del log email (o None se nessun destinatario). Non solleva mai: l'evento business non deve essere perso."""
    if not customer_id:
        return None
    try:
        to = await _resolve_recipient(db, tenant_id, customer_id)
        if not to:
            logger.info("customer event %s %s/%s: nessun destinatario", event_type, entity_type, entity_id)
            return None
        brand = await _brand(db, tenant_id)
        cust = await db.customers.find_one({"_id": customer_id}, {"first_name": 1, "last_name": 1, "company_name": 1})
        name = (cust or {}).get("first_name") or (cust or {}).get("company_name") or ""
        link = f"{settings.APP_BASE_URL.rstrip('/')}{cta_path}"
        html = (f'<div style="font-family:Roboto,Arial,sans-serif;color:#1f2937;max-width:560px"><div style="font-weight:700;color:#12a16b;margin-bottom:8px">{brand["name"]}</div>'
                f'<h2 style="margin:0 0 12px">{title}</h2><p>Gentile {name},</p><p>{body}</p>'
                f'<p style="margin:24px 0"><a href="{link}" style="background:#12a16b;color:#fff;padding:12px 22px;border-radius:4px;text-decoration:none;font-weight:600">{cta_label}</a></p>'
                f'<p style="color:#6b7280;font-size:12px">{brand["name"]}{" · " + brand["email"] if brand.get("email") else ""}{" · " + brand["phone"] if brand.get("phone") else ""}</p></div>')
        key = f"cust:{event_type}:{entity_type}:{entity_id}{(':' + dedupe_suffix) if dedupe_suffix else ''}"
        log_id = await send_email(to=to, subject=f"{title} | {brand['name']}", template=f"customer_{event_type.lower()}", html=html,
                                  text=f"{title}\n\nGentile {name},\n{body}\n\n{cta_label}: {link}\n\n{brand['name']}",
                                  tenant_id=tenant_id, idempotency_key=key, event_type=event_type)
        if log_id:
            await db.email_logs.update_one({"_id": log_id}, {"$set": {"customer_id": customer_id, "entity_type": entity_type, "entity_id": entity_id}})
        return log_id or None
    except Exception as ex:  # mai bloccare l'operazione business
        logger.warning("customer event email failed %s %s/%s: %s", event_type, entity_type, entity_id, ex)
        return None
