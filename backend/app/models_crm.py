"""CRM domain models for M2 (leads, customers, contacts, pipelines, activities, tasks, appointments, goals, commissions, whatsapp)."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field, EmailStr
from app.models import BaseDoc, utcnow, new_id


# ---------- Pipeline ----------
class PipelineStage(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    order: int = 0
    color: str = "#71717A"
    probability_default: int = 20  # 0-100
    is_won: bool = False
    is_lost: bool = False


class Pipeline(BaseDoc):
    name: str
    description: Optional[str] = None
    stages: List[PipelineStage] = Field(default_factory=list)
    is_default: bool = False


class PipelineCreate(BaseModel):
    name: str
    description: Optional[str] = None
    stages: Optional[List[PipelineStage]] = None


class PipelineUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    stages: Optional[List[PipelineStage]] = None
    is_default: Optional[bool] = None


# ---------- Lead ----------
class LeadAddress(BaseModel):
    street: Optional[str] = None
    city: Optional[str] = None
    zip_code: Optional[str] = None
    province: Optional[str] = None
    country: str = "IT"


class Lead(BaseDoc):
    # Identity
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    # Contact
    email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    address: LeadAddress = Field(default_factory=LeadAddress)
    # Origin
    source: Optional[str] = None  # website, referral, cold, event, other
    source_detail: Optional[str] = None
    # Pipeline
    pipeline_id: Optional[str] = None
    stage_id: Optional[str] = None
    probability: int = 20  # 0-100
    estimated_value: float = 0.0
    currency: str = "EUR"
    # Assignment
    assigned_to: Optional[str] = None  # user_id (commerciale)
    # Sales intelligence
    next_action_at: Optional[datetime] = None
    next_action_note: Optional[str] = None
    last_activity_at: Optional[datetime] = None
    last_contact_at: Optional[datetime] = None
    # State
    lifecycle: str = "lead"  # lead | customer (after conversion)
    customer_id: Optional[str] = None  # set when converted
    won_at: Optional[datetime] = None
    lost_at: Optional[datetime] = None
    lost_reason: Optional[str] = None
    # Tags & notes
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    # Product interest (freeform in M2, structured in M3)
    interested_products: List[str] = Field(default_factory=list)


class LeadCreate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    address: Optional[LeadAddress] = None
    source: Optional[str] = None
    source_detail: Optional[str] = None
    pipeline_id: Optional[str] = None
    stage_id: Optional[str] = None
    estimated_value: float = 0.0
    assigned_to: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    interested_products: List[str] = Field(default_factory=list)


class LeadUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    address: Optional[LeadAddress] = None
    source: Optional[str] = None
    source_detail: Optional[str] = None
    pipeline_id: Optional[str] = None
    stage_id: Optional[str] = None
    probability: Optional[int] = None
    estimated_value: Optional[float] = None
    assigned_to: Optional[str] = None
    next_action_at: Optional[datetime] = None
    next_action_note: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    interested_products: Optional[List[str]] = None


# ---------- Customer ----------
# Enerhia Operating Core — Milestone 1 Part 2
# customer_type valori canonici: PRIVATE | COMPANY | TO_CONFIRM
# Retro-compat: valori legacy "private" e "business" sono mappati in lettura ma
# il primo edit deve forzare la ri-classificazione.


class ContactPerson(BaseModel):
    """Referente aziendale (per COMPANY)."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class Customer(BaseDoc):
    # Progressivo per tenant, atomico, non riutilizzabile
    customer_number: Optional[str] = None
    # Classificazione anagrafica
    customer_type: str = "TO_CONFIRM"  # PRIVATE | COMPANY | TO_CONFIRM
    # Persona (PRIVATE)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    # Azienda (COMPANY)
    company_name: Optional[str] = None
    contact_person: ContactPerson = Field(default_factory=ContactPerson)
    # Contatti
    email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    pec: Optional[str] = None
    sdi_code: Optional[str] = None
    # Indirizzi
    address: LeadAddress = Field(default_factory=LeadAddress)          # residenza / sede legale
    billing_address: Optional[LeadAddress] = None
    # Dati fiscali
    vat_number: Optional[str] = None
    tax_code: Optional[str] = None
    # Assegnazioni / meta
    assigned_to: Optional[str] = None
    origin_lead_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    total_value: float = 0.0  # computed field, updated by orders


class CustomerCreate(BaseModel):
    customer_type: str = "PRIVATE"  # PRIVATE | COMPANY
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    contact_person: Optional[ContactPerson] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    pec: Optional[str] = None
    sdi_code: Optional[str] = None
    address: Optional[LeadAddress] = None
    billing_address: Optional[LeadAddress] = None
    vat_number: Optional[str] = None
    tax_code: Optional[str] = None
    assigned_to: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class CustomerUpdate(BaseModel):
    customer_type: Optional[str] = None  # PRIVATE | COMPANY (TO_CONFIRM non accettato in update)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    contact_person: Optional[ContactPerson] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    pec: Optional[str] = None
    sdi_code: Optional[str] = None
    address: Optional[LeadAddress] = None
    billing_address: Optional[LeadAddress] = None
    vat_number: Optional[str] = None
    tax_code: Optional[str] = None
    assigned_to: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None


class LeadConvertRequest(BaseModel):
    customer_type: str = "private"


# ---------- Contact ----------
class Contact(BaseDoc):
    first_name: str
    last_name: Optional[str] = None
    role: Optional[str] = None  # job title/role
    email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    notes: Optional[str] = None
    # Polymorphic linking
    customer_id: Optional[str] = None
    lead_id: Optional[str] = None
    is_primary: bool = False


class ContactCreate(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    notes: Optional[str] = None
    customer_id: Optional[str] = None
    lead_id: Optional[str] = None
    is_primary: bool = False


class ContactUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    notes: Optional[str] = None
    customer_id: Optional[str] = None
    lead_id: Optional[str] = None
    is_primary: Optional[bool] = None


# ---------- Activity (Timeline central entity) ----------
class Activity(BaseDoc):
    type: str  # lead_created | note | call | email | whatsapp | appointment_scheduled | appointment_done | task_created | task_done | stage_changed | conversion | quote_created | order_created | ...
    subject: str
    body: Optional[str] = None
    direction: Optional[str] = None  # in | out
    outcome: Optional[str] = None  # answered | no_answer | callback | busy | ...
    duration_seconds: Optional[int] = None
    occurred_at: datetime = Field(default_factory=utcnow)
    # relations
    lead_id: Optional[str] = None
    customer_id: Optional[str] = None
    contact_id: Optional[str] = None
    quote_id: Optional[str] = None
    order_id: Optional[str] = None
    # workflow
    assigned_to: Optional[str] = None
    completed_at: Optional[datetime] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class ActivityCreate(BaseModel):
    type: str
    subject: str
    body: Optional[str] = None
    direction: Optional[str] = None
    outcome: Optional[str] = None
    duration_seconds: Optional[int] = None
    occurred_at: Optional[datetime] = None
    lead_id: Optional[str] = None
    customer_id: Optional[str] = None
    contact_id: Optional[str] = None
    quote_id: Optional[str] = None
    order_id: Optional[str] = None
    assigned_to: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


# ---------- Task ----------
class Task(BaseDoc):
    title: str
    description: Optional[str] = None
    due_at: Optional[datetime] = None
    priority: str = "normal"  # low | normal | high | urgent
    task_status: str = "open"  # open | in_progress | done | cancelled
    assigned_to: Optional[str] = None
    lead_id: Optional[str] = None
    customer_id: Optional[str] = None
    completed_at: Optional[datetime] = None


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    due_at: Optional[datetime] = None
    priority: str = "normal"
    assigned_to: Optional[str] = None
    lead_id: Optional[str] = None
    customer_id: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_at: Optional[datetime] = None
    priority: Optional[str] = None
    task_status: Optional[str] = None
    assigned_to: Optional[str] = None


# ---------- Appointment ----------
class Appointment(BaseDoc):
    title: str
    description: Optional[str] = None
    start_at: datetime
    end_at: datetime
    location: Optional[str] = None
    attendees: List[str] = Field(default_factory=list)  # user_ids
    lead_id: Optional[str] = None
    customer_id: Optional[str] = None
    contact_id: Optional[str] = None
    appointment_type: str = "meeting"  # meeting | call | survey | install | other
    appointment_status: str = "scheduled"  # scheduled | done | cancelled | no_show
    reminder_minutes: int = 30
    color: str = "#D9381E"


class AppointmentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    start_at: datetime
    end_at: datetime
    location: Optional[str] = None
    attendees: List[str] = Field(default_factory=list)
    lead_id: Optional[str] = None
    customer_id: Optional[str] = None
    contact_id: Optional[str] = None
    appointment_type: str = "meeting"
    reminder_minutes: int = 30


class AppointmentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    location: Optional[str] = None
    attendees: Optional[List[str]] = None
    appointment_type: Optional[str] = None
    appointment_status: Optional[str] = None
    reminder_minutes: Optional[int] = None


# ---------- Goal ----------
class Goal(BaseDoc):
    user_id: str
    period_type: str = "month"  # month | quarter | year
    period_start: datetime
    period_end: datetime
    metric: str = "revenue"  # revenue | leads | deals_won | appointments
    target_value: float
    achieved_value: float = 0.0


class GoalCreate(BaseModel):
    user_id: str
    period_type: str = "month"
    period_start: datetime
    period_end: datetime
    metric: str = "revenue"
    target_value: float


class GoalUpdate(BaseModel):
    target_value: Optional[float] = None
    achieved_value: Optional[float] = None


# ---------- Commission ----------
class CommissionRule(BaseDoc):
    name: str
    user_id: Optional[str] = None  # null = applies to any user (or role_id in the future)
    role_id: Optional[str] = None
    base: str = "margin"  # margin | revenue
    percentage: float = 5.0  # 0-100
    threshold_min: float = 0.0  # min value to apply
    active: bool = True


class CommissionRuleCreate(BaseModel):
    name: str
    user_id: Optional[str] = None
    role_id: Optional[str] = None
    base: str = "margin"
    percentage: float = 5.0
    threshold_min: float = 0.0


# ---------- WhatsApp / Comms send request ----------
class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str
    lead_id: Optional[str] = None
    customer_id: Optional[str] = None
    contact_id: Optional[str] = None


class SendWhatsAppRequest(BaseModel):
    to: str
    body: Optional[str] = None
    template_id: Optional[str] = None
    template_variables: Optional[Dict[str, Any]] = None
    subject: Optional[str] = None
    lead_id: Optional[str] = None
    customer_id: Optional[str] = None
    contact_id: Optional[str] = None


class LogCallRequest(BaseModel):
    to: Optional[str] = None
    direction: str = "out"  # in | out
    outcome: str = "answered"  # answered | no_answer | callback | busy
    duration_seconds: int = 0
    subject: str = "Telefonata"
    notes: Optional[str] = None
    lead_id: Optional[str] = None
    customer_id: Optional[str] = None
    contact_id: Optional[str] = None


# ---------- Onboarding ----------
class OnboardingState(BaseModel):
    step: int = 0
    completed: bool = False
    completed_at: Optional[datetime] = None
    data: Dict[str, Any] = Field(default_factory=dict)


class OnboardingStepCompany(BaseModel):
    name: str
    legal_name: Optional[str] = None
    vat_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    zip_code: Optional[str] = None
    province: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class OnboardingStepLogo(BaseModel):
    logo_url: Optional[str] = None


class OnboardingStepSequences(BaseModel):
    quote_prefix: str = "PRV-"
    quote_padding: int = 5
    order_prefix: str = "ORD-"
    order_padding: int = 5
    year_reset: bool = True


class OnboardingStepInvite(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role_slug: Optional[str] = "commerciale"


class OnboardingStepFirstLead(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    estimated_value: float = 0.0
    source: str = "onboarding"
