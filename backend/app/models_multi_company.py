"""Multi-company & intercompany models.

Nel tenant coesistono più `LegalEntity` (Enerhia Srl, Auxer Srl, ...).
Ogni record economico DEVE portare `legal_entity_id`.
"""
from __future__ import annotations
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from app.models import BaseDoc


LegalEntityStatus = Literal["to_complete", "active", "suspended", "archived"]


class LegalEntitySignatory(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    tax_code: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class LegalEntityAddress(BaseModel):
    kind: Literal["legal", "operational"] = "operational"
    label: Optional[str] = None
    street: Optional[str] = None
    zip: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    country: str = "IT"


class LegalEntity(BaseDoc):
    """Entità giuridica interna al tenant (Enerhia, Auxer, ...)."""
    code: str
    name: str
    legal_form: Optional[str] = None            # es. "SRL", "SPA", "SNC"
    vat_number: Optional[str] = None            # da completare
    tax_code: Optional[str] = None              # cod. fiscale
    sdi_code: Optional[str] = None
    pec: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    rea: Optional[str] = None
    share_capital: Optional[str] = None
    activity_start_date: Optional[date] = None
    # Regime IVA
    vat_regime: Optional[str] = None            # es. "ordinario", "forfettario"
    vat_periodicity: Optional[Literal["monthly", "quarterly", "annual"]] = None
    currency: str = "EUR"
    # Contabilità/fiscale
    default_iban: Optional[str] = None
    logo_url: Optional[str] = None
    # Multi-address
    addresses: List[LegalEntityAddress] = Field(default_factory=list)
    signatories: List[LegalEntitySignatory] = Field(default_factory=list)
    # Stato
    le_status: LegalEntityStatus = "to_complete"
    missing_fields: List[str] = Field(default_factory=list)
    fiscal_operations_blocked: bool = True     # true finché dati fiscali incompleti
    # Ruoli autorizzati (nomi ruolo)
    authorized_role_names: List[str] = Field(default_factory=list)
    # Meta
    is_demo: bool = False
    is_default: bool = False
    notes: Optional[str] = None
    # Versioning fiscale
    fiscal_version: int = 1
    prev_fiscal_snapshot: Optional[Dict[str, Any]] = None


class LegalEntityCreate(BaseModel):
    code: str
    name: str
    legal_form: Optional[str] = None
    notes: Optional[str] = None


class LegalEntityUpdate(BaseModel):
    name: Optional[str] = None
    legal_form: Optional[str] = None
    vat_number: Optional[str] = None
    tax_code: Optional[str] = None
    sdi_code: Optional[str] = None
    pec: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    rea: Optional[str] = None
    share_capital: Optional[str] = None
    activity_start_date: Optional[date] = None
    vat_regime: Optional[str] = None
    vat_periodicity: Optional[str] = None
    currency: Optional[str] = None
    default_iban: Optional[str] = None
    logo_url: Optional[str] = None
    addresses: Optional[List[LegalEntityAddress]] = None
    signatories: Optional[List[LegalEntitySignatory]] = None
    le_status: Optional[LegalEntityStatus] = None
    authorized_role_names: Optional[List[str]] = None
    notes: Optional[str] = None


class LegalEntityMembership(BaseDoc):
    """Accesso di un utente a una specifica legal entity."""
    user_id: str
    legal_entity_id: str
    membership_role: Literal["member", "manager", "admin"] = "member"
    granted_by: Optional[str] = None
    granted_at: datetime = Field(default_factory=datetime.now)
    revoked_at: Optional[datetime] = None
    active: bool = True


# ---------- INTERCOMPANY ----------
IntercompanyStatus = Literal[
    "draft", "pending_counterpart", "mirrored",
    "partially_reconciled", "reconciled", "disputed",
    "cancelled", "reversed",
]


class IntercompanyTransaction(BaseDoc):
    """Transazione fra due legal entities (mirroring automatico).

    Ogni operazione ha DUE record: uno lato source (attivo) uno lato target (passivo)
    accomunati da `intercompany_pair_id`.
    """
    intercompany_pair_id: str          # correla i due lati
    side: Literal["source", "target"]  # source = chi vende, target = chi acquista
    source_legal_entity_id: str
    target_legal_entity_id: str
    self_legal_entity_id: str          # id della "propria" legal entity in questo record
    counterparty_legal_entity_id: str  # id dell'altra
    # Documento origine
    doc_kind: Literal["invoice", "credit_note", "advance", "loan", "transfer", "service", "other"] = "invoice"
    doc_ref: Optional[str] = None
    doc_date: Optional[date] = None
    # Importi
    amount_gross: float = 0.0
    amount_taxable: float = 0.0
    vat_amount: float = 0.0
    vat_rate: float = 22.0
    currency: str = "EUR"
    # Contabile
    debit_credit: Literal["debit", "credit"] = "credit"  # source=credit, target=debit
    revenue_or_cost: Literal["revenue", "cost", "asset", "liability"] = "revenue"
    # Scadenza
    due_date: Optional[date] = None
    # Riconciliazione con pagamento
    payment_id: Optional[str] = None
    reconciled_at: Optional[datetime] = None
    ic_status: IntercompanyStatus = "draft"
    version: int = 1
    reason: Optional[str] = None
    consistency_flags: List[str] = Field(default_factory=list)
    attachments: List[str] = Field(default_factory=list)  # attachment ids
    # Storno / rettifica
    reversal_of_id: Optional[str] = None
    reversed_by_id: Optional[str] = None
    notes: Optional[str] = None


class IntercompanyCreate(BaseModel):
    source_legal_entity_id: str
    target_legal_entity_id: str
    doc_kind: str = "invoice"
    doc_ref: Optional[str] = None
    doc_date: Optional[date] = None
    amount_taxable: float
    vat_rate: float = 22.0
    currency: str = "EUR"
    due_date: Optional[date] = None
    reason: Optional[str] = None
    attachments: List[str] = Field(default_factory=list)


class IntercompanyReconcileRequest(BaseModel):
    pair_id: str
    action: Literal["confirm", "dispute", "cancel", "reverse"]
    reason: Optional[str] = None
