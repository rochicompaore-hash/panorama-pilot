"""Landing router — public submit + platform owner config.

Endpoints pubblici (no auth):
- GET /public-site/config → configurazione pubblica sanitizzata
- POST /public-site/leads → submit landing form

Endpoints autenticati (Platform Owner):
- GET/PATCH /platform/site-config
- GET /platform/site-config/leads
"""
from __future__ import annotations
import hashlib
import re
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import get_db
from app.deps import get_current_user, get_client_ip
from app.mongo_utils import to_mongo, from_mongo
from app.models import utcnow, new_id
from app.models_landing import (
    PublicSiteConfig, PublicSiteConfigUpdate,
    LandingLead, LandingLeadSubmission, PackageConfig,
)


public_site_router = APIRouter(prefix="/public-site", tags=["Public Landing"])
platform_site_router = APIRouter(prefix="/platform/site-config", tags=["Platform Site Config"])


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _valid_email(x: str) -> bool:
    return bool(x and EMAIL_RE.match(x.strip()))


def _require_platform_owner(user: dict):
    if not (user.get("is_platform_owner") or user.get("is_superadmin")):
        raise HTTPException(403, "Solo Platform Owner")


async def _get_or_create_config() -> dict:
    db = get_db()
    doc = await db.public_site_configs.find_one({"deleted_at": None}, sort=[("created_at", -1)])
    if doc:
        return from_mongo(doc)
    # Default config with recommended packages
    default_packages = [
        PackageConfig(code="starter", name="Starter", sort_order=10,
                       description="Ideale per iniziare — CRM base + preventivi essenziali.",
                       included_module_codes=["core_crm", "quotes_contracts"],
                       max_users=3, max_storage_mb=500, max_legal_entities=1, trial_days=14),
        PackageConfig(code="sales", name="Sales", sort_order=20,
                       description="Ciclo commerciale completo — CRM, preventivatore, contratti e firme.",
                       included_module_codes=["core_crm", "quotes_contracts",
                                              "technical_abaco", "omnichannel"],
                       max_users=5, max_storage_mb=2000, badge="Popolare"),
        PackageConfig(code="operations", name="Operations", sort_order=30,
                       description="Rilievo, abaco, posa, tracking cliente e assistenza.",
                       included_module_codes=["core_crm", "quotes_contracts",
                                              "technical_abaco", "installation_logistics", "service"],
                       max_users=8),
        PackageConfig(code="production", name="Production", sort_order=40,
                       description="BOM, lista di taglio, produzione, magazzino, qualità.",
                       included_module_codes=["core_crm", "quotes_contracts",
                                              "technical_abaco", "production", "warehouse"],
                       max_users=15),
        PackageConfig(code="finance", name="Finance", sort_order=50,
                       description="Amministrazione, tesoreria, cash flow, IVA, break-even.",
                       included_module_codes=["administration", "treasury", "management_control"],
                       max_users=5),
        PackageConfig(code="enterprise", name="Enterprise", sort_order=60,
                       description="Tutti i moduli + AI CFO + Multi-company + Omnicanale.",
                       included_module_codes=["core_crm", "quotes_contracts", "technical_abaco",
                                              "production", "warehouse", "installation_logistics",
                                              "service", "administration", "treasury",
                                              "management_control", "ai_cfo", "multi_company",
                                              "omnichannel"],
                       max_users=100, max_legal_entities=5,
                       badge="Completo"),
    ]
    default = PublicSiteConfig(
        packages=default_packages,
        public_module_codes=[
            "core_crm", "quotes_contracts", "technical_abaco",
            "production", "warehouse", "installation_logistics",
            "service", "administration", "treasury",
            "management_control", "ai_cfo", "multi_company", "omnichannel",
        ],
        seo_title="Software Gestionale per Serramentisti | Panorama Pilot",
        seo_description=("Panorama Pilot è il software gestionale per aziende di serramenti: CRM, preventivi, "
                          "contratti, cantieri, clienti, documenti e gestione della commessa in un'unica piattaforma."),
        email_status="configuration_required",
        email_status_note="Configurare i destinatari email prima di attivare le notifiche di lead.",
        is_published=True, published_at=utcnow(),
    )
    doc_write = to_mongo(default.model_dump(by_alias=True))
    await db.public_site_configs.insert_one(doc_write)
    return default.model_dump()


# ============================================================
# PUBLIC (no auth)
# ============================================================
@public_site_router.get("/config")
async def public_get_config():
    """Config pubblica sanitizzata (nessuna email destinatari)."""
    cfg = await _get_or_create_config()
    return {
        "product_name": cfg.get("product_name"),
        "logo_url": cfg.get("logo_url"),
        "hero_title": cfg.get("hero_title"),
        "hero_subtitle": cfg.get("hero_subtitle"),
        "cta_primary_text": cfg.get("cta_primary_text"),
        "cta_primary_subtitle": cfg.get("cta_primary_subtitle"),
        "cta_secondary_text": cfg.get("cta_secondary_text"),
        "lead_form_mode": cfg.get("lead_form_mode"),
        "commercial_phone": cfg.get("commercial_phone"),
        "commercial_whatsapp": cfg.get("commercial_whatsapp"),
        "company_address": cfg.get("company_address"),
        "privacy_policy_url": cfg.get("privacy_policy_url"),
        "cookie_policy_url": cfg.get("cookie_policy_url"),
        "terms_url": cfg.get("terms_url"),
        "social_links": cfg.get("social_links") or {},
        "public_module_codes": cfg.get("public_module_codes") or [],
        "packages": cfg.get("packages") or [],
        "seo_title": cfg.get("seo_title"),
        "seo_description": cfg.get("seo_description"),
        "seo_og_image": cfg.get("seo_og_image"),
        "is_published": cfg.get("is_published", True),
    }


def _suggest_package(sub: LandingLeadSubmission) -> tuple[str, str]:
    """Suggerisce un pacchetto in base alle risposte."""
    m = set(sub.interested_module_codes or [])
    has_prod = sub.has_internal_production is True or any(
        x in m for x in ("production", "warehouse")
    )
    has_finance = any(x in m for x in ("treasury", "management_control", "ai_cfo"))
    if "multi_company" in m or (sub.num_employees or 0) > 30 or "ai_cfo" in m:
        return "enterprise", "Struttura articolata e moduli finanziari richiesti"
    if has_prod:
        return "production", "Presenza di produzione interna e/o interesse a magazzino/lista di taglio"
    if has_finance:
        return "finance", "Focus su tesoreria, break-even e controllo di gestione"
    if any(x in m for x in ("technical_abaco", "installation_logistics", "service")):
        return "operations", "Rilievo, posa e assistenza richiesti"
    if any(x in m for x in ("core_crm", "quotes_contracts")):
        return "sales", "Interesse su CRM, preventivi e contratti"
    return "starter", "Configurazione iniziale consigliata"


def _dedup_key(email: str, phone: Optional[str], vat: Optional[str]) -> str:
    parts = [email.lower().strip()]
    if phone: parts.append(re.sub(r"\D", "", phone))
    if vat: parts.append(vat.upper().strip())
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


@public_site_router.post("/leads")
async def public_submit_lead(payload: LandingLeadSubmission, request: Request):
    if not payload.privacy_consent:
        raise HTTPException(400, "Consenso privacy obbligatorio")
    if not _valid_email(payload.email):
        raise HTTPException(400, "Email non valida")
    db = get_db()
    cfg = await _get_or_create_config()
    dkey = _dedup_key(payload.email, payload.phone, payload.vat_number)
    # Dedup
    existing = await db.landing_leads.find_one({"dedup_key": dkey, "deleted_at": None})
    if existing:
        return {
            "ok": True, "duplicate": True,
            "lead_id": str(existing["_id"]),
            "message": "Richiesta già ricevuta — un referente ti contatterà a breve.",
        }
    pkg_code, reason = _suggest_package(payload)
    d = payload.model_dump()
    lead = LandingLead(
        **d,
        dedup_key=dkey,
        suggested_package_code=pkg_code,
        suggestion_reason=reason,
    )
    await db.landing_leads.insert_one(to_mongo(lead.model_dump(by_alias=True)))

    # Crea/collega CRM lead nel tenant principale (default company)
    default_company = await db.companies.find_one({"deleted_at": None}, sort=[("created_at", 1)])
    if default_company:
        tid = default_company["_id"]
        # Duplicate check nel CRM
        crm_dupe = await db.leads.find_one({
            "tenant_id": tid, "deleted_at": None,
            "$or": [{"email": payload.email}, {"vat_number": payload.vat_number} if payload.vat_number else {"_id": "__none__"}]
        })
        if crm_dupe:
            crm_lead_id = crm_dupe["_id"]
        else:
            crm_lead_id = new_id()
            crm_doc = {
                "_id": crm_lead_id, "tenant_id": tid,
                "created_at": utcnow().isoformat(), "updated_at": utcnow().isoformat(),
                "created_by": None, "updated_by": None,
                "status": "new", "deleted_at": None, "version": 1,
                "source": "public_landing_page",
                "first_name": payload.first_name, "last_name": payload.last_name,
                "email": payload.email, "phone": payload.phone,
                "company_name": payload.company_name,
                "legal_name": payload.legal_name,
                "vat_number": payload.vat_number,
                "city": payload.city, "province": payload.province,
                "region": payload.region, "country": payload.country,
                "website": payload.website,
                "utm_source": payload.utm_source, "utm_medium": payload.utm_medium,
                "utm_campaign": payload.utm_campaign,
                "interested_modules": payload.interested_module_codes,
                "suggested_package_code": pkg_code,
                "landing_lead_id": lead.id,
                "notes": (payload.notes or "") + f"\n[Auto] Pacchetto suggerito: {pkg_code}. {reason}",
            }
            await db.leads.insert_one(crm_doc)
            # Timeline attività
            try:
                await db.activities.insert_one({
                    "_id": new_id(), "tenant_id": tid, "lead_id": crm_lead_id,
                    "kind": "note", "subject": "Richiesta consulenza dalla landing",
                    "body": f"Pacchetto suggerito: {pkg_code} — {reason}",
                    "created_at": utcnow().isoformat(), "updated_at": utcnow().isoformat(),
                    "status": "active", "version": 1, "deleted_at": None,
                })
            except Exception: pass
        await db.landing_leads.update_one({"_id": lead.id},
            {"$set": {"crm_lead_id": crm_lead_id, "ll_status": "notified"}})

    # Email notification
    recipients = cfg.get("lead_notification_recipients") or []
    valid_recipients = [e for e in recipients if _valid_email(e)]
    if not valid_recipients:
        # Log come pending
        await db.landing_leads.update_one({"_id": lead.id},
            {"$set": {"email_notification_status": "pending_configuration"}})
    else:
        try:
            from app.services.email import send_email
            body = (
                f"Nuova richiesta consulenza\n\n"
                f"Nome: {payload.first_name} {payload.last_name}\n"
                f"Azienda: {payload.company_name}\n"
                f"Email: {payload.email}\n"
                f"Telefono: {payload.phone or '—'}\n"
                f"Volume: {payload.revenue_range or '—'}\n"
                f"Dipendenti: {payload.num_employees or '—'}\n"
                f"Moduli: {', '.join(payload.interested_module_codes or []) or '—'}\n"
                f"Pacchetto suggerito: {pkg_code} ({reason})\n"
                f"Note: {payload.notes or '—'}\n"
                f"CRM Lead ID: {lead.model_dump().get('crm_lead_id') or '—'}"
            )
            for r in valid_recipients:
                await send_email(to=r, subject=f"Nuovo lead: {payload.company_name}",
                                    body=body, template="landing_lead")
            await db.landing_leads.update_one({"_id": lead.id},
                {"$set": {"email_notification_status": "sent"}})
        except Exception:
            await db.landing_leads.update_one({"_id": lead.id},
                {"$set": {"email_notification_status": "failed"}})

    return {
        "ok": True, "duplicate": False, "lead_id": lead.id,
        "suggested_package": pkg_code, "reason": reason,
        "message": ("Abbiamo ricevuto la tua richiesta. Un nostro referente ti contatterà "
                     "per comprendere le esigenze della tua azienda e mostrarti i moduli più adatti."),
    }


# ============================================================
# PLATFORM OWNER config
# ============================================================
@platform_site_router.get("")
async def platform_get_config(user: dict = Depends(get_current_user)):
    _require_platform_owner(user)
    cfg = await _get_or_create_config()
    return cfg


@platform_site_router.patch("")
async def platform_update_config(payload: PublicSiteConfigUpdate,
                                  user: dict = Depends(get_current_user)):
    _require_platform_owner(user)
    db = get_db()
    cfg = await _get_or_create_config()
    updates = payload.model_dump(exclude_unset=True)
    # Validate recipients
    if "lead_notification_recipients" in updates:
        recs = updates["lead_notification_recipients"] or []
        invalid = [e for e in recs if not _valid_email(e)]
        if invalid:
            raise HTTPException(400, f"Email non valide: {invalid}. Non verranno usati indirizzi non validi.")
        updates["email_status"] = "configured" if recs else "configuration_required"
    updates["updated_at"] = utcnow().isoformat()
    updates["updated_by"] = user["id"]
    if "packages" in updates and updates["packages"]:
        updates["packages"] = [PackageConfig(**p).model_dump() if not isinstance(p, dict)
                                else PackageConfig(**p).model_dump()
                                for p in updates["packages"]]
    await db.public_site_configs.update_one({"_id": cfg["id"]}, {"$set": updates, "$inc": {"version": 1}})
    doc = await db.public_site_configs.find_one({"_id": cfg["id"]})
    return from_mongo(doc)


@platform_site_router.get("/leads")
async def platform_list_leads(limit: int = 100, user: dict = Depends(get_current_user)):
    _require_platform_owner(user)
    db = get_db()
    docs = await db.landing_leads.find({"deleted_at": None}).sort([("created_at", -1)]).limit(limit).to_list(limit)
    return {"items": [from_mongo(d) for d in docs], "total": len(docs)}
