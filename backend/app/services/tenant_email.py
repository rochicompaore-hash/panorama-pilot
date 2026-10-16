"""TENANT EMAIL SETTINGS — sender_mode PANORAMA_MANAGED | CUSTOM_VERIFIED_DOMAIN. Provider: RESEND.
Il mittente è risolto server-side (gerarchia: dominio custom VERIFIED → managed sender Panorama). Mai spoofing: il FROM
custom è usato SOLO se domain_status == VERIFIED. CUSTOM SMTP per tenant = NOT_IN_SCOPE (campo `provider` predisposto)."""
from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict

from app.services import resend_provider

SENDER_MODES = ("PANORAMA_MANAGED", "CUSTOM_VERIFIED_DOMAIN")
DOMAIN_STATUSES = ("NOT_CONFIGURED", "PENDING_VERIFICATION", "VERIFIED", "FAILED", "SUSPENDED")
_RESEND_STATUS_MAP = {"not_started": "PENDING_VERIFICATION", "pending": "PENDING_VERIFICATION", "verified": "VERIFIED",
                      "failed": "FAILED", "temporary_failure": "PENDING_VERIFICATION"}


def managed_domain() -> str:
    return os.environ.get("PANORAMA_MANAGED_DOMAIN", "").strip().lower()


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s[:40] or "tenant"


def default_settings(tenant_id: str) -> Dict[str, Any]:
    return {"_id": tenant_id, "tenant_id": tenant_id, "provider": "RESEND", "sender_mode": "PANORAMA_MANAGED",
            "from_name": None, "managed_local_part": None, "custom_from_local_part": "preventivi", "reply_to": None,
            "support_email": None, "sales_email": None, "signature": None, "custom_domain": None,
            "domain_status": "NOT_CONFIGURED", "provider_domain_id": None, "verified_at": None, "dns_records": [],
            "dmarc_status": "MISSING", "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": None}


async def get_settings(db, tenant_id: str) -> Dict[str, Any]:
    doc = await db.tenant_email_settings.find_one({"_id": tenant_id})
    return doc or default_settings(tenant_id)


async def company_brand(db, tenant_id: str) -> Dict[str, Any]:
    c = await db.companies.find_one({"_id": tenant_id}) or {}
    return {"name": c.get("commercial_name") or c.get("name") or c.get("legal_name") or "La tua azienda",
            "legal_name": c.get("legal_name") or c.get("name"), "email": c.get("email"), "phone": c.get("phone"),
            "website": c.get("website"), "logo_url": c.get("logo_url"), "address": c.get("address"), "city": c.get("city")}


async def resolve_sender(db, tenant_id: str) -> Dict[str, Any]:
    """Gerarchia §L: 1) CUSTOM VERIFIED DOMAIN  2) PANORAMA MANAGED SENDER. Mai bloccare per dominio non configurato."""
    s = await get_settings(db, tenant_id)
    brand = await company_brand(db, tenant_id)
    from_name = s.get("from_name") or brand["name"]
    reply_to = s.get("reply_to") or brand.get("email")
    if s.get("sender_mode") == "CUSTOM_VERIFIED_DOMAIN" and s.get("domain_status") == "VERIFIED" and s.get("custom_domain"):
        return {"sender_mode": "CUSTOM_VERIFIED_DOMAIN", "from_name": from_name, "reply_to": reply_to,
                "from_email": f"{s.get('custom_from_local_part') or 'preventivi'}@{s['custom_domain']}", "domain": s["custom_domain"], "domain_status": "VERIFIED"}
    md = managed_domain()
    local = s.get("managed_local_part") or slugify(brand["name"])
    return {"sender_mode": "PANORAMA_MANAGED", "from_name": from_name, "reply_to": reply_to,
            "from_email": f"{local}@{md}" if md else None, "domain": md or None,
            "domain_status": "VERIFIED" if md else "NOT_CONFIGURED", "fallback_applied": s.get("sender_mode") == "CUSTOM_VERIFIED_DOMAIN"}


def public_view(s: Dict[str, Any], sender: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in s.items() if k != "_id"}
    out["effective_sender"] = sender
    out["managed_domain"] = managed_domain() or None
    out["provider_configured"] = resend_provider.is_configured()
    out["webhook_configured"] = resend_provider.webhook_configured()
    out["custom_smtp_per_tenant"] = "NOT_IN_SCOPE"
    return out


def apply_provider_domain(s: Dict[str, Any], d: Dict[str, Any]) -> Dict[str, Any]:
    """Normalizza risposta Resend domain → settings (records SPF/DKIM + status)."""
    status = _RESEND_STATUS_MAP.get(str(d.get("status") or "").lower(), "PENDING_VERIFICATION")
    records = [{"record": r.get("record"), "type": r.get("type"), "name": r.get("name"), "value": r.get("value"),
                "ttl": r.get("ttl"), "priority": r.get("priority"), "status": r.get("status")} for r in (d.get("records") or [])]
    s.update({"provider_domain_id": d.get("id"), "domain_status": status, "dns_records": records,
              "verified_at": datetime.now(timezone.utc).isoformat() if status == "VERIFIED" and not s.get("verified_at") else s.get("verified_at")})
    if status != "VERIFIED":
        s["verified_at"] = None
    return s
