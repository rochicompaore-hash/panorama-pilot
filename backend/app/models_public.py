"""M3.3.3 — Public read-only link for quotes."""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from app.models import BaseDoc


class QuotePublicToken(BaseDoc):
    """Cryptographically-random URL-safe token for public quote access.

    Token IS NEVER stored in DB — only `token_hash` (sha256).
    """
    quote_id: str
    quote_number: str
    quote_revision: str
    quote_pdf_id: str
    snapshot_hash: str
    token_hash: str
    status: str = "active"  # active | expired | revoked | invalidated | consumed | blocked
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    revoked_by: Optional[str] = None
    revocation_reason: Optional[str] = None
    last_access_at: Optional[datetime] = None
    access_count: int = 0
    maximum_accesses: Optional[int] = None
    requires_otp: bool = False
    allowed_actions: List[str] = Field(default_factory=lambda: ["view", "download"])
    invalidated_by_revision_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PublicLinkCreate(BaseModel):
    validity_days: Optional[int] = 30
    expires_at: Optional[datetime] = None
    requires_otp: bool = False
    maximum_accesses: Optional[int] = None
    allowed_actions: List[str] = Field(default_factory=lambda: ["view", "download", "sign", "request_changes", "reject"])


class PublicLinkRevoke(BaseModel):
    reason: str


class PublicAccessLog(BaseDoc):
    """Append-only log of public portal accesses."""
    token_id: str
    quote_id: str
    quote_revision: str
    event: str  # link_opened|quote_viewed|pdf_opened|pdf_downloaded|token_expired|token_revoked|token_invalid|rate_limited|otp_requested|otp_verified|otp_failed
    ip_hash: Optional[str] = None
    user_agent: Optional[str] = None
    result: str = "ok"  # ok | denied | error
    reason: Optional[str] = None
    request_id: Optional[str] = None


class PublicQuoteResponse(BaseModel):
    """Read-only DTO delivered to the public portal — NO internal identifiers."""
    company_name: str
    company_logo_url: Optional[str] = None
    company_phone: Optional[str] = None
    company_email: Optional[str] = None
    company_website: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    quote_number: str
    quote_revision: str
    title: Optional[str] = None
    issue_date: Optional[str] = None
    valid_until: Optional[str] = None
    is_expired: bool = False
    is_superseded: bool = False
    customer_name: Optional[str] = None
    site_address: Optional[Dict[str, Any]] = None
    sales_rep_name: Optional[str] = None
    sales_rep_email: Optional[str] = None
    sales_rep_phone: Optional[str] = None
    intro_text: Optional[str] = None
    subtotal: float = 0
    vat_amount: float = 0
    total: float = 0
    quote_status: Optional[str] = None
    payment_terms_display: Optional[str] = None
    allowed_actions: List[str] = Field(default_factory=list)
    watermark: Optional[str] = None
    has_pdf: bool = False
