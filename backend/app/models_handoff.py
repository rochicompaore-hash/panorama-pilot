"""M6.OPS — Operational handoff, teams, assignment rules, SLA, dashboards data model."""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from app.models import BaseDoc, new_id


# ============================================================================
# OPERATIONAL AREA CONFIG
# ============================================================================
OperationalArea = Literal[
    "lead_generation", "sales", "administration",
    "technical_survey", "technical_approval", "production",
    "installation", "final_check", "assistance",
]


class OperationalAreaConfig(BaseDoc):
    """Configurazione area operativa per tenant."""
    code: OperationalArea
    label: str
    active: bool = True
    order_index: int = 0
    sla_ack_minutes: int = 60          # tempo massimo di presa in carico
    sla_complete_minutes: int = 1440   # tempo massimo di lavorazione
    escalation_user_id: Optional[str] = None
    escalation_group_id: Optional[str] = None
    working_hours: Dict[str, Any] = Field(default_factory=dict)
    default_group_id: Optional[str] = None
    notification_channels: List[str] = Field(default_factory=lambda: ["in_app", "email"])
    reminder_before_minutes: int = 30
    is_demo: bool = False


class OperationalAreaConfigUpsert(BaseModel):
    code: str
    label: str
    active: bool = True
    order_index: int = 0
    sla_ack_minutes: int = 60
    sla_complete_minutes: int = 1440
    escalation_user_id: Optional[str] = None
    escalation_group_id: Optional[str] = None
    default_group_id: Optional[str] = None
    notification_channels: List[str] = Field(default_factory=lambda: ["in_app", "email"])
    reminder_before_minutes: int = 30


# ============================================================================
# USER GROUP (team)
# ============================================================================
class UserGroup(BaseDoc):
    code: str
    name: str
    area: OperationalArea
    leader_user_id: Optional[str] = None
    member_user_ids: List[str] = Field(default_factory=list)
    substitute_user_ids: List[str] = Field(default_factory=list)
    # Regole competenza
    provinces: List[str] = Field(default_factory=list)      # zone competenza
    zip_prefixes: List[str] = Field(default_factory=list)
    site_id: Optional[str] = None
    product_keys: List[str] = Field(default_factory=list)
    assignment_strategy: Literal["round_robin", "least_load", "manual", "leader_first"] = "round_robin"
    working_hours: Dict[str, Any] = Field(default_factory=dict)
    active: bool = True
    notification_channels: List[str] = Field(default_factory=lambda: ["in_app", "email"])
    is_demo: bool = False


class UserGroupCreate(BaseModel):
    code: str
    name: str
    area: str
    leader_user_id: Optional[str] = None
    member_user_ids: List[str] = Field(default_factory=list)
    substitute_user_ids: List[str] = Field(default_factory=list)
    provinces: List[str] = Field(default_factory=list)
    zip_prefixes: List[str] = Field(default_factory=list)
    product_keys: List[str] = Field(default_factory=list)
    assignment_strategy: str = "round_robin"


class UserGroupUpdate(BaseModel):
    name: Optional[str] = None
    leader_user_id: Optional[str] = None
    member_user_ids: Optional[List[str]] = None
    substitute_user_ids: Optional[List[str]] = None
    provinces: Optional[List[str]] = None
    zip_prefixes: Optional[List[str]] = None
    product_keys: Optional[List[str]] = None
    assignment_strategy: Optional[str] = None
    active: Optional[bool] = None


# ============================================================================
# ASSIGNMENT RULE
# ============================================================================
class AssignmentRule(BaseDoc):
    name: str
    area: OperationalArea
    priority: int = 100           # più basso = valutato prima
    # Filtri
    match_provinces: List[str] = Field(default_factory=list)
    match_zip_prefixes: List[str] = Field(default_factory=list)
    match_product_keys: List[str] = Field(default_factory=list)
    match_source: List[str] = Field(default_factory=list)   # lead sources
    match_priority: List[str] = Field(default_factory=list)  # low|normal|high|urgent
    # Azione
    target_group_id: Optional[str] = None
    target_user_id: Optional[str] = None
    fallback_group_id: Optional[str] = None
    active: bool = True
    is_demo: bool = False


class AssignmentRuleCreate(BaseModel):
    name: str
    area: str
    priority: int = 100
    match_provinces: List[str] = Field(default_factory=list)
    match_zip_prefixes: List[str] = Field(default_factory=list)
    match_product_keys: List[str] = Field(default_factory=list)
    match_source: List[str] = Field(default_factory=list)
    target_group_id: Optional[str] = None
    target_user_id: Optional[str] = None
    fallback_group_id: Optional[str] = None


# ============================================================================
# OPERATIONAL HANDOFF
# ============================================================================
HandoffStatus = Literal[
    "pending", "notified", "acknowledged", "in_progress",
    "blocked", "completed", "reassigned", "overdue", "cancelled",
]


class OperationalHandoff(BaseDoc):
    customer_id: Optional[str] = None
    lead_id: Optional[str] = None
    quote_id: Optional[str] = None
    contract_id: Optional[str] = None
    survey_id: Optional[str] = None
    technical_schedule_id: Optional[str] = None
    executive_order_id: Optional[str] = None
    production_order_id: Optional[str] = None
    installation_id: Optional[str] = None
    service_ticket_id: Optional[str] = None
    from_area: Optional[OperationalArea] = None
    to_area: OperationalArea
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    reason: Optional[str] = None
    assigned_group_id: Optional[str] = None
    assigned_user_ids: List[str] = Field(default_factory=list)
    transferred_by: Optional[str] = None
    transferred_at: datetime = Field(default_factory=lambda: datetime.now())
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    notes: Optional[str] = None
    handoff_status: HandoffStatus = "pending"
    notification_sent_at: Optional[datetime] = None
    notification_status: Literal["pending", "sent", "failed", "partial"] = "pending"
    timeline_event_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    # Reminders sent
    reminders_sent_count: int = 0
    last_reminder_at: Optional[datetime] = None
    # Meta
    subject_label: Optional[str] = None
    action_required: Optional[str] = None


class OperationalHandoffCreate(BaseModel):
    to_area: OperationalArea
    contract_id: Optional[str] = None
    lead_id: Optional[str] = None
    quote_id: Optional[str] = None
    customer_id: Optional[str] = None
    survey_id: Optional[str] = None
    technical_schedule_id: Optional[str] = None
    from_area: Optional[OperationalArea] = None
    reason: Optional[str] = None
    priority: str = "normal"
    due_at: Optional[datetime] = None
    assigned_group_id: Optional[str] = None
    assigned_user_ids: List[str] = Field(default_factory=list)
    idempotency_key: Optional[str] = None
    subject_label: Optional[str] = None
    action_required: Optional[str] = None


class HandoffAckRequest(BaseModel):
    handoff_id: str
    note: Optional[str] = None


class HandoffCompleteRequest(BaseModel):
    handoff_id: str
    note: Optional[str] = None
    result: Optional[str] = None


class HandoffReassignRequest(BaseModel):
    handoff_id: str
    reason: str
    new_group_id: Optional[str] = None
    new_user_ids: List[str] = Field(default_factory=list)


class HandoffBlockRequest(BaseModel):
    handoff_id: str
    reason: str
