"""Pydantic models for Infissi Express Cloud (M1).

Design rules:
- Every document uses a UUID4 string as `id` (also stored as `_id` in Mongo)
- Every operational entity has: tenant_id, created_at, updated_at, created_by, updated_by, status, deleted_at, version
- No hardcoded ObjectId; we treat Mongo as a plain document store keyed by our own UUIDs.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Any, Dict, Literal
from pydantic import BaseModel, Field, EmailStr, ConfigDict


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BaseDoc(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    id: str = Field(default_factory=new_id, alias="_id")
    tenant_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    status: str = "active"
    deleted_at: Optional[datetime] = None
    version: int = 1


# ---------- Company ----------
class CompanySettings(BaseModel):
    locale: str = "it"
    currency: str = "EUR"
    timezone: str = "Europe/Rome"
    date_format: str = "DD/MM/YYYY"


class Company(BaseDoc):
    name: str
    legal_name: Optional[str] = None
    vat_number: Optional[str] = None
    tax_code: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    zip_code: Optional[str] = None
    province: Optional[str] = None
    country: str = "IT"
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    settings: CompanySettings = Field(default_factory=CompanySettings)


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    legal_name: Optional[str] = None
    vat_number: Optional[str] = None
    tax_code: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    zip_code: Optional[str] = None
    province: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    settings: Optional[CompanySettings] = None


# ---------- Permission & Role ----------
class Permission(BaseDoc):
    key: str
    module: str
    action: str
    description: str


class Role(BaseDoc):
    name: str
    description: Optional[str] = None
    permission_keys: List[str] = Field(default_factory=list)
    is_system: bool = False


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    permission_keys: List[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permission_keys: Optional[List[str]] = None


# ---------- User ----------
class User(BaseDoc):
    email: EmailStr
    password_hash: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    role_ids: List[str] = Field(default_factory=list)
    is_superadmin: bool = False
    must_change_password: bool = False
    is_active: bool = True
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    locale: str = "it"


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    role_ids: List[str] = []
    is_superadmin: bool = False
    is_active: bool = True
    must_change_password: bool = False
    last_login_at: Optional[datetime] = None
    tenant_id: Optional[str] = None
    created_at: Optional[datetime] = None


class UserCreate(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    role_ids: List[str] = Field(default_factory=list)
    send_invitation: bool = True


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    role_ids: Optional[List[str]] = None
    is_active: Optional[bool] = None


# ---------- Auth requests ----------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserPublic
    must_change_password: bool = False


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class AcceptInvitationRequest(BaseModel):
    token: str
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


# ---------- Session ----------
class Session(BaseDoc):
    user_id: str
    refresh_token_hash: str
    device_info: Optional[str] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    last_used_at: datetime = Field(default_factory=utcnow)


# ---------- Invitation / Password reset ----------
class Invitation(BaseDoc):
    email: EmailStr
    role_ids: List[str] = Field(default_factory=list)
    token_hash: str
    expires_at: datetime
    accepted_at: Optional[datetime] = None
    invited_by: Optional[str] = None


class PasswordResetToken(BaseDoc):
    user_id: str
    token_hash: str
    expires_at: datetime
    used_at: Optional[datetime] = None


# ---------- Audit ----------
class AuditLog(BaseDoc):
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None


# ---------- Notification ----------
class Notification(BaseDoc):
    user_id: str
    type: str = "info"  # info | success | warning | error
    title: str
    body: Optional[str] = None
    link: Optional[str] = None
    read_at: Optional[datetime] = None


# ---------- Attachment ----------
class Attachment(BaseDoc):
    entity_type: str
    entity_id: Optional[str] = None
    filename: str
    storage_key: str
    size: int
    mime_type: str
    uploaded_by: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    description: Optional[str] = None


# ---------- Sequence ----------
class Sequence(BaseDoc):
    key: str
    label: str
    prefix: str = ""
    suffix: str = ""
    padding: int = 5
    current_number: int = 0
    year_reset: bool = False
    current_year: Optional[int] = None


class SequenceCreate(BaseModel):
    key: str
    label: str
    prefix: str = ""
    suffix: str = ""
    padding: int = 5
    year_reset: bool = False


class SequenceUpdate(BaseModel):
    label: Optional[str] = None
    prefix: Optional[str] = None
    suffix: Optional[str] = None
    padding: Optional[int] = None
    year_reset: Optional[bool] = None
    current_number: Optional[int] = None


# ---------- Email log ----------
class EmailLog(BaseDoc):
    to: str
    subject: str
    template: str
    status: str  # queued | sent | failed
    error: Optional[str] = None
    sent_at: Optional[datetime] = None
    provider: str = "mock"
