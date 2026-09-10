"""Public site config + public landing lead intake.

- PublicSiteConfig: tenant/global config (nome prodotto, logo, CTA, email destinatari, ...)
- LandingLead: richiesta consulenza dalla landing pubblica
- Endpoint pubblici (senza auth) per submit form
- Endpoint autenticati per config e visualizzazione lead
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, EmailStr
from app.models import BaseDoc


CTAText = Literal["Diventa cliente", "Richiedi una consulenza", "Scopri la piattaforma", "Richiedi una demo"]


class PackageConfig(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    included_module_codes: List[str] = Field(default_factory=list)
    max_users: Optional[int] = None
    max_legal_entities: Optional[int] = None
    max_storage_mb: Optional[int] = None
    price_visible: bool = False
    price_monthly: Optional[float] = None
    trial_days: int = 14
    badge: Optional[str] = None
    sort_order: int = 100
    is_public: bool = True


class PublicSiteConfig(BaseDoc):
    """Configurazione del sito pubblico (landing + login area)."""
    product_name: str = "Panorama Pilot"
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    hero_title: str = "Gestisci tutta la tua azienda di serramenti in un unico sistema"
    hero_subtitle: str = ("Lead, preventivi, contratti, rilievi, produzione, montaggio, "
                          "assistenza, tesoreria e controllo di gestione: tutto collegato e tracciato.")
    hero_description: Optional[str] = None
    cta_primary_text: str = "Richiedi una consulenza"
    cta_primary_subtitle: str = ("Raccontaci come lavori oggi e ti mostreremo i moduli "
                                  "più adatti alla tua azienda.")
    cta_secondary_text: str = "Accedi"
    lead_form_mode: Literal["popup", "page"] = "popup"
    # Destinatari email
    lead_notification_recipients: List[str] = Field(default_factory=list)
    email_status: Literal["configured", "configuration_required"] = "configuration_required"
    email_status_note: Optional[str] = None
    email_sender: Optional[str] = None
    # Contatti azienda
    commercial_phone: Optional[str] = None
    commercial_whatsapp: Optional[str] = None
    company_address: Optional[str] = None
    # Legali
    privacy_policy_url: Optional[str] = None
    cookie_policy_url: Optional[str] = None
    terms_url: Optional[str] = None
    # Social
    social_links: Dict[str, str] = Field(default_factory=dict)
    # Moduli/pacchetti pubblici
    public_module_codes: List[str] = Field(default_factory=list)
    packages: List[PackageConfig] = Field(default_factory=list)
    # SEO
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    seo_og_image: Optional[str] = None
    # Analytics
    analytics_config: Dict[str, Any] = Field(default_factory=dict)
    # Publication
    is_published: bool = True
    published_at: Optional[datetime] = None
    domain: Optional[str] = None


class PublicSiteConfigUpdate(BaseModel):
    product_name: Optional[str] = None
    logo_url: Optional[str] = None
    hero_title: Optional[str] = None
    hero_subtitle: Optional[str] = None
    cta_primary_text: Optional[str] = None
    cta_primary_subtitle: Optional[str] = None
    lead_form_mode: Optional[str] = None
    lead_notification_recipients: Optional[List[str]] = None
    email_sender: Optional[str] = None
    commercial_phone: Optional[str] = None
    commercial_whatsapp: Optional[str] = None
    company_address: Optional[str] = None
    privacy_policy_url: Optional[str] = None
    cookie_policy_url: Optional[str] = None
    terms_url: Optional[str] = None
    social_links: Optional[Dict[str, str]] = None
    public_module_codes: Optional[List[str]] = None
    packages: Optional[List[PackageConfig]] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    seo_og_image: Optional[str] = None
    analytics_config: Optional[Dict[str, Any]] = None
    is_published: Optional[bool] = None
    domain: Optional[str] = None


class LandingLeadSubmission(BaseModel):
    # Contatto
    first_name: str
    last_name: str
    role: Optional[str] = None
    email: EmailStr
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    # Azienda
    company_name: str
    legal_name: Optional[str] = None
    vat_number: Optional[str] = None
    tax_code: Optional[str] = None
    website: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    region: Optional[str] = None
    country: str = "IT"
    operational_area: Optional[str] = None
    # Struttura
    num_collaborators: Optional[int] = None
    num_employees: Optional[int] = None
    num_sales: Optional[int] = None
    num_installers: Optional[int] = None
    has_internal_production: Optional[bool] = None
    revenue_range: Optional[str] = None
    quotes_per_month: Optional[int] = None
    orders_per_month: Optional[int] = None
    current_software: Optional[str] = None
    main_problems: Optional[str] = None
    goals: Optional[str] = None
    # Moduli
    interested_module_codes: List[str] = Field(default_factory=list)
    # Consenso
    privacy_consent: bool
    marketing_consent: bool = False
    contact_availability: Optional[str] = None
    notes: Optional[str] = None
    # UTM/tracking
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    referrer: Optional[str] = None


class LandingLead(BaseDoc):
    """Lead ricevuto dalla landing pubblica — persistito con dedup + suggerimento pacchetto."""
    # (tutti i campi di LandingLeadSubmission ma flat)
    first_name: str
    last_name: str
    role: Optional[str] = None
    email: str
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    company_name: str
    legal_name: Optional[str] = None
    vat_number: Optional[str] = None
    tax_code: Optional[str] = None
    website: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    region: Optional[str] = None
    country: str = "IT"
    operational_area: Optional[str] = None
    num_collaborators: Optional[int] = None
    num_employees: Optional[int] = None
    num_sales: Optional[int] = None
    num_installers: Optional[int] = None
    has_internal_production: Optional[bool] = None
    revenue_range: Optional[str] = None
    quotes_per_month: Optional[int] = None
    orders_per_month: Optional[int] = None
    current_software: Optional[str] = None
    main_problems: Optional[str] = None
    goals: Optional[str] = None
    interested_module_codes: List[str] = Field(default_factory=list)
    privacy_consent: bool = False
    marketing_consent: bool = False
    contact_availability: Optional[str] = None
    notes: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    referrer: Optional[str] = None
    # Elaborazione
    suggested_package_code: Optional[str] = None
    suggestion_reason: Optional[str] = None
    crm_lead_id: Optional[str] = None
    dedup_key: Optional[str] = None
    ll_status: Literal["received", "notified", "converted", "duplicate", "spam"] = "received"
    email_notification_status: Literal["not_sent", "sent", "pending_configuration", "failed"] = "not_sent"
    source: str = "public_landing_page"
