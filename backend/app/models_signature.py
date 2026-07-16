"""M3.3.4 — OTP + electronic signature models."""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field
from app.models import BaseDoc


# ---------- OTP ----------
class QuoteOtpRequest(BaseDoc):
    """A single OTP challenge. The OTP is never stored in plain-text: only its salted sha256 hash.

    A new OtpRequest for the same token invalidates the previous one (status=superseded).
    """
    token_id: str
    quote_id: str
    channel: str = "email"  # email|sms (future)
    recipient_hash: str  # sha256[:24] of recipient identifier (email lowercased)
    recipient_masked: str  # e.g., "a****@example.com"  (display only)
    otp_hash: str  # sha256(salt + otp)
    otp_salt: str
    expires_at: datetime
    attempts: int = 0
    max_attempts: int = 5
    status: str = "pending"  # pending|verified|expired|superseded|failed
    ip_hash: Optional[str] = None
    user_agent: Optional[str] = None
    verified_at: Optional[datetime] = None
    debug_code_plain: Optional[str] = None  # ONLY populated in dev/test — access requires perm


class PublicOtpRequestBody(BaseModel):
    email: EmailStr


class PublicOtpVerifyBody(BaseModel):
    request_id: str
    code: str


# ---------- Signature ----------
class SignatureCanvasPayload(BaseModel):
    """PNG data URL for the signature. Server validates size/type/mime."""
    data_url: str  # data:image/png;base64,....
    stroke_count: Optional[int] = None
    canvas_width: Optional[int] = None
    canvas_height: Optional[int] = None
    total_duration_ms: Optional[int] = None


class PublicSignatureSubmit(BaseModel):
    otp_request_id: str
    otp_code: str
    first_name: str
    last_name: str
    fiscal_role: Optional[str] = None  # e.g., "Titolare", "Legale rappresentante"
    company_represented: Optional[str] = None
    signature: SignatureCanvasPayload
    accept_terms: bool = False
    accept_privacy: bool = False
    accept_payment_terms: bool = False
    consent_electronic_sign: bool = False
    client_timestamp_ms: Optional[int] = None


class QuoteSignature(BaseDoc):
    """Persisted, immutable signature record. One per successful signing event.

    The signature IMAGE is stored in Object Storage; only a hash is kept in DB.
    """
    quote_id: str
    quote_number: str
    quote_revision: str
    quote_pdf_id: str  # original definitive
    snapshot_hash: str  # of the original PDF snapshot
    token_id: str
    otp_request_id: str
    # Signer identity
    signer_first_name: str
    signer_last_name: str
    signer_email_hash: str
    signer_email_masked: str
    signer_fiscal_role: Optional[str] = None
    signer_company_represented: Optional[str] = None
    # Signature capture
    signature_image_hash: str  # sha256 of the PNG bytes
    signature_storage_key: Optional[str] = None
    signature_stroke_count: Optional[int] = None
    signature_capture_duration_ms: Optional[int] = None
    # Acceptances
    consents: Dict[str, bool] = Field(default_factory=dict)
    clauses_version_hash: Optional[str] = None
    # Evidence
    evidence_hash: str  # sha256 of canonical JSON payload (see services/signature.canonical_payload)
    evidence_payload: Dict[str, Any] = Field(default_factory=dict)  # frozen canonical payload
    evidence_id_short: str  # first 8 hex chars of evidence_hash, uppercased — user-facing reference
    # Signed PDF
    signed_pdf_id: Optional[str] = None
    signed_pdf_hash: Optional[str] = None
    # Context
    ip_hash: Optional[str] = None
    user_agent: Optional[str] = None
    signed_at_utc: datetime
    signed_at_local_display: Optional[str] = None  # pre-formatted Europe/Rome
    signature_type: str = "FES"  # Firma Elettronica Semplice — advisory label only


# ---------- Portal actions: request-changes / reject ----------
class PublicRequestChangesBody(BaseModel):
    reason: str = Field(..., min_length=3, max_length=1000)
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    preferred_callback: Optional[str] = None  # ISO or free text
    notes: Optional[str] = None


class PublicRejectBody(BaseModel):
    reason_code: Optional[str] = None  # price|delivery|scope|other
    notes: Optional[str] = Field(None, max_length=2000)


class CustomerRequest(BaseDoc):
    """A structured customer-side request originating from the public portal."""
    quote_id: str
    quote_number: str
    quote_revision: str
    token_id: str
    kind: str  # change_request | rejection
    reason_code: Optional[str] = None
    reason: Optional[str] = None
    notes: Optional[str] = None
    contact_email_hash: Optional[str] = None
    contact_phone_masked: Optional[str] = None
    preferred_callback: Optional[str] = None
    ip_hash: Optional[str] = None
    user_agent: Optional[str] = None
    # Workflow
    request_status: str = "open"  # open|in_progress|closed|superseded
    taken_over_by: Optional[str] = None
    resolution: Optional[str] = None  # closed_no_revision|new_revision_created|withdrawn
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    resolved_by: Optional[str] = None


class CustomerRequestTake(BaseModel):
    notes: Optional[str] = None


class CustomerRequestClose(BaseModel):
    resolution: str  # closed_no_revision|new_revision_created|withdrawn
    resolution_notes: Optional[str] = None
