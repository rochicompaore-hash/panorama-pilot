"""SaaS Modularization models — piani, entitlement, dipendenze, limiti.

Nessuna integrazione Stripe: solo interfaccia BillingProvider astratta.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from app.models import BaseDoc


# I codici modulo ufficiali della piattaforma
MODULE_CODES = [
    "core_crm",
    "quotes_contracts",
    "technical_abaco",
    "production",
    "warehouse",
    "installation_logistics",
    "service",
    "administration",
    "treasury",
    "management_control",
    "ai_cfo",
    "multi_company",
    "omnichannel",
]

ModuleCode = Literal[
    "core_crm", "quotes_contracts", "technical_abaco", "production", "warehouse",
    "installation_logistics", "service", "administration", "treasury",
    "management_control", "ai_cfo", "multi_company", "omnichannel",
]

EntitlementState = Literal[
    "active", "trial", "grace_period", "read_only",
    "suspended", "expired", "disabled",
]


class SubscriptionModule(BaseDoc):
    """Modulo SaaS attivabile."""
    code: str                      # es. "treasury"
    label: str
    description: Optional[str] = None
    category: str = "core"
    icon: Optional[str] = None
    default_permissions: List[str] = Field(default_factory=list)
    active: bool = True


class ModuleDependency(BaseDoc):
    """Dipendenza: module X richiede Y."""
    module_code: str
    requires_module: str
    hard: bool = True              # true = blocca, false = solo warning
    notes: Optional[str] = None


class SubscriptionPlan(BaseDoc):
    """Piano commerciale (Starter, Professional, Enterprise, custom)."""
    code: str
    name: str
    description: Optional[str] = None
    tier: Literal["starter", "professional", "enterprise", "custom"] = "starter"
    included_module_codes: List[str] = Field(default_factory=list)
    max_users: Optional[int] = None
    max_storage_mb: Optional[int] = None
    max_legal_entities: Optional[int] = 1
    max_quotes_per_month: Optional[int] = None
    monthly_price: Optional[float] = None      # nessun prezzo hardcoded — configurabile
    yearly_price: Optional[float] = None
    currency: str = "EUR"
    is_demo: bool = True
    is_default: bool = False
    trial_days: int = 0
    active: bool = True
    notes: Optional[str] = None


class SubscriptionPlanCreate(BaseModel):
    code: str
    name: str
    tier: str = "starter"
    included_module_codes: List[str] = Field(default_factory=list)
    max_users: Optional[int] = None
    max_storage_mb: Optional[int] = None
    max_legal_entities: Optional[int] = 1
    monthly_price: Optional[float] = None
    trial_days: int = 0
    notes: Optional[str] = None


class TenantEntitlement(BaseDoc):
    """Entitlement corrente del tenant: quale piano + override per modulo."""
    plan_id: Optional[str] = None
    plan_code: Optional[str] = None
    plan_snapshot_module_codes: List[str] = Field(default_factory=list)
    # Override per-modulo (attivo/disattivo/read_only/scadenza)
    module_states: Dict[str, str] = Field(default_factory=dict)   # code -> EntitlementState
    module_expires_at: Dict[str, str] = Field(default_factory=dict)  # ISO datetime
    module_grace_until: Dict[str, str] = Field(default_factory=dict)
    max_users_override: Optional[int] = None
    max_storage_mb_override: Optional[int] = None
    max_legal_entities_override: Optional[int] = None
    trial_started_at: Optional[datetime] = None
    trial_ends_at: Optional[datetime] = None
    suspended_at: Optional[datetime] = None
    suspended_reason: Optional[str] = None
    notes: Optional[str] = None


class TenantEntitlementUpdate(BaseModel):
    plan_id: Optional[str] = None
    module_states: Optional[Dict[str, str]] = None
    module_expires_at: Optional[Dict[str, str]] = None
    max_users_override: Optional[int] = None
    max_storage_mb_override: Optional[int] = None
    max_legal_entities_override: Optional[int] = None
    trial_ends_at: Optional[datetime] = None
    notes: Optional[str] = None


class UsageCounter(BaseDoc):
    """Contatore utilizzo (numero utenti attivi, storage MB, quotes/mese)."""
    metric: Literal["users", "storage_mb", "quotes_month", "legal_entities"]
    value: float = 0.0
    period: Optional[str] = None      # es. "2026-02" per metriche mensili
    last_computed_at: datetime = Field(default_factory=datetime.now)


class BillingEvent(BaseDoc):
    """Evento billing (log; provider astratto)."""
    event_kind: Literal["subscription_created", "invoice_issued", "payment_received",
                        "plan_changed", "module_added", "module_removed",
                        "trial_started", "trial_ended", "suspended", "resumed"]
    amount: float = 0.0
    currency: str = "EUR"
    provider: str = "internal"
    provider_ref: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class ModuleGateResult(BaseModel):
    """Risultato del controllo modulo (usato dal middleware)."""
    module_code: str
    state: EntitlementState
    allow_read: bool = True
    allow_write: bool = True
    message: Optional[str] = None
    missing_dependencies: List[str] = Field(default_factory=list)
