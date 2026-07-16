"""M6.COMMS — Lead intake webhooks, omnichannel inbox, WhatsApp/Meta/email providers,
message templates, consents management."""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from app.models import BaseDoc, new_id


# ============================================================================
# LEAD WEBHOOK CONFIG
# ============================================================================
LeadSource = Literal[
    "landing_page", "website_form", "meta_lead_ads", "facebook_form",
    "instagram_form", "google_ads", "whatsapp", "chatbot", "csv_import",
    "api", "manual", "referral", "phone_call", "other",
]


class LeadWebhookConfig(BaseDoc):
    source: LeadSource
    name: str
    slug: str                          # es. "landing-porte-2026" — usato in URL
    secret_key_hash: Optional[str] = None
    signature_algorithm: Literal["hmac_sha256", "verify_token", "none"] = "hmac_sha256"
    verify_token: Optional[str] = None   # per Meta webhook verification
    campaign: Optional[str] = None
    form_id: Optional[str] = None
    field_mapping: Dict[str, str] = Field(default_factory=dict)  # payload_key → lead_field
    consent_marketing_default: bool = False
    consent_contact_required: bool = True
    dedup_strategy: Literal["strict", "loose", "none"] = "strict"
    autoassign_area: Optional[str] = "lead_generation"
    active: bool = True
    is_demo: bool = False
    last_received_at: Optional[datetime] = None
    total_received: int = 0
    total_duplicates: int = 0
    total_errors: int = 0


class LeadWebhookConfigCreate(BaseModel):
    source: LeadSource
    name: str
    slug: str
    signature_algorithm: str = "hmac_sha256"
    verify_token: Optional[str] = None
    campaign: Optional[str] = None
    form_id: Optional[str] = None
    field_mapping: Dict[str, str] = Field(default_factory=dict)
    consent_marketing_default: bool = False
    autoassign_area: str = "lead_generation"


class LeadWebhookConfigUpdate(BaseModel):
    name: Optional[str] = None
    campaign: Optional[str] = None
    form_id: Optional[str] = None
    field_mapping: Optional[Dict[str, str]] = None
    consent_marketing_default: Optional[bool] = None
    autoassign_area: Optional[str] = None
    active: Optional[bool] = None


class LeadWebhookIngestion(BaseDoc):
    """Log di ogni ingestion (audit + retry + dead-letter)."""
    config_id: str
    source: LeadSource
    signature_ok: bool = False
    dedup_key: Optional[str] = None
    dedup_hit: bool = False
    lead_id: Optional[str] = None
    payload_raw: Dict[str, Any] = Field(default_factory=dict)
    payload_hash: Optional[str] = None
    processed: bool = False
    error: Optional[str] = None
    retry_count: int = 0
    ingested_at: datetime = Field(default_factory=lambda: datetime.now())


# ============================================================================
# OMNICHANNEL COMMS
# ============================================================================
ChannelKind = Literal["whatsapp", "email", "messenger", "instagram_dm", "web_chat", "sms"]


class CommunicationChannel(BaseDoc):
    kind: ChannelKind
    name: str
    provider: str = "mock"                 # mock | twilio | meta | resend | ...
    phone_number: Optional[str] = None
    email_from: Optional[str] = None
    external_account_id: Optional[str] = None
    credentials_ref: Optional[str] = None  # riferimento a env/secret name
    active: bool = True
    is_demo: bool = False
    default_group_id: Optional[str] = None


class Conversation(BaseDoc):
    channel_id: str
    channel_kind: ChannelKind
    external_thread_id: Optional[str] = None
    customer_id: Optional[str] = None
    lead_id: Optional[str] = None
    contact_id: Optional[str] = None
    quote_id: Optional[str] = None
    contract_id: Optional[str] = None
    service_ticket_id: Optional[str] = None
    subject: Optional[str] = None
    external_participant: Optional[str] = None   # numero/email/username esterno
    external_display_name: Optional[str] = None
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None
    unread_count: int = 0
    assigned_user_id: Optional[str] = None
    assigned_group_id: Optional[str] = None
    conv_status: Literal["open", "pending", "closed", "archived"] = "open"


class ConversationCreate(BaseModel):
    channel_id: str
    external_participant: str
    customer_id: Optional[str] = None
    lead_id: Optional[str] = None
    subject: Optional[str] = None


class Message(BaseDoc):
    conversation_id: str
    channel_id: str
    direction: Literal["inbound", "outbound", "internal_note"]
    body: str
    external_message_id: Optional[str] = None
    template_id: Optional[str] = None
    template_variables: Dict[str, Any] = Field(default_factory=dict)
    attachments: List[Dict[str, Any]] = Field(default_factory=list)
    sent_by: Optional[str] = None
    msg_status: Literal["queued", "sent", "delivered", "read", "failed"] = "queued"
    error: Optional[str] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None


class SendMessageRequest(BaseModel):
    conversation_id: str
    body: str
    template_id: Optional[str] = None
    template_variables: Dict[str, Any] = Field(default_factory=dict)
    attachments: List[Dict[str, Any]] = Field(default_factory=list)


# ============================================================================
# TEMPLATES
# ============================================================================
class MessageTemplate(BaseDoc):
    code: str
    name: str
    kind: Literal["email", "whatsapp", "sms", "notification"]
    language: str = "it"
    subject: Optional[str] = None       # solo per email
    body: str
    variables: List[str] = Field(default_factory=list)
    version: int = 1
    approved: bool = False
    external_provider_template_id: Optional[str] = None   # es. WhatsApp template approvato
    fallback_template_id: Optional[str] = None
    active: bool = True
    is_demo: bool = False


class MessageTemplateCreate(BaseModel):
    code: str
    name: str
    kind: str
    language: str = "it"
    subject: Optional[str] = None
    body: str
    variables: List[str] = Field(default_factory=list)
    external_provider_template_id: Optional[str] = None


class MessageTemplateUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    variables: Optional[List[str]] = None
    approved: Optional[bool] = None
    active: Optional[bool] = None


# ============================================================================
# EMAIL AUTOMATION
# ============================================================================
AutomationTrigger = Literal[
    "lead.created", "appointment.scheduled", "appointment.reminder",
    "quote.sent", "quote.viewed", "quote.not_viewed_48h", "quote.change_requested",
    "contract.ready", "contract.signed",
    "survey.scheduled", "schedule.ready", "schedule.signed",
    "payment.requested", "payment.received",
    "production.started", "production.completed",
    "installation.scheduled", "installation.completed",
    "warranty.activated", "service.opened", "review.request",
]


class EmailAutomation(BaseDoc):
    code: str
    name: str
    trigger: AutomationTrigger
    conditions: List[Dict[str, Any]] = Field(default_factory=list)
    delay_minutes: int = 0
    template_id: str
    recipients_kind: Literal["customer", "sales_rep", "assigned_user", "group", "custom"] = "customer"
    recipients_custom: List[str] = Field(default_factory=list)
    from_channel_id: Optional[str] = None
    active: bool = True
    is_demo: bool = False
    dedup_window_hours: int = 24
    total_sent: int = 0
    last_sent_at: Optional[datetime] = None


class EmailAutomationCreate(BaseModel):
    code: str
    name: str
    trigger: AutomationTrigger
    template_id: str
    recipients_kind: str = "customer"
    delay_minutes: int = 0
    conditions: List[Dict[str, Any]] = Field(default_factory=list)


class EmailAutomationUpdate(BaseModel):
    name: Optional[str] = None
    template_id: Optional[str] = None
    recipients_kind: Optional[str] = None
    delay_minutes: Optional[int] = None
    conditions: Optional[List[Dict[str, Any]]] = None
    active: Optional[bool] = None


# ============================================================================
# CONSENTS
# ============================================================================
ConsentKind = Literal[
    "contact", "marketing", "whatsapp", "email",
    "profiling", "terms", "privacy_policy",
]


class Consent(BaseDoc):
    customer_id: Optional[str] = None
    lead_id: Optional[str] = None
    kind: ConsentKind
    granted: bool = False
    source: Optional[str] = None
    version: Optional[str] = None
    text_snapshot: Optional[str] = None
    ip_hash: Optional[str] = None
    revoked_at: Optional[datetime] = None
    revoke_reason: Optional[str] = None


class ConsentCreate(BaseModel):
    customer_id: Optional[str] = None
    lead_id: Optional[str] = None
    kind: ConsentKind
    granted: bool = True
    source: Optional[str] = None
    version: Optional[str] = None


# ============================================================================
# LEAD WEBHOOK PAYLOAD (generic)
# ============================================================================
class LeadWebhookPayload(BaseModel):
    """Payload generico normalizzato accettato dal webhook.
    I campi extra sono ammessi ma ignorati.
    """
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    zip_code: Optional[str] = None
    product_of_interest: Optional[str] = None
    message: Optional[str] = None
    campaign: Optional[str] = None
    ad_id: Optional[str] = None
    form_id: Optional[str] = None
    social_profile_id: Optional[str] = None
    consent_marketing: Optional[bool] = None
    consent_contact: Optional[bool] = None
    raw_extra: Dict[str, Any] = Field(default_factory=dict)
