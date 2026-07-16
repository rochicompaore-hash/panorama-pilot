"""Signature Provider Adapter — Interfaccia standard per provider firma.

Fase 2: definiamo l'interfaccia; Namirial/InfoCert/Aruba/... vanno agganciati
in configurazione azienda. In assenza di provider configurato, il sistema
usa Firma Elettronica Semplice via canvas (già implementata).

Convenzione:
  - `electronic_simple` (ES): default, canvas + IP + UA + hash. NO qualified.
  - `electronic_advanced` (FEA): richiede provider esterno configurato.
  - `electronic_qualified` (FEQ): richiede provider qualificato AgID configurato.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


SignatureLevel = str  # "electronic_simple" | "electronic_advanced" | "electronic_qualified"


@dataclass
class SignerRequest:
    email: str
    name: str
    role: str = "customer"
    order: int = 1                    # per firma sequenziale
    require_otp: bool = False
    require_id_verification: bool = False


@dataclass
class SignatureEnvelope:
    """Pratica di firma esterna."""
    provider: str
    external_id: Optional[str]
    signers: List[SignerRequest]
    status: str = "created"            # created | sent | in_progress | completed | rejected | expired
    document_key: Optional[str] = None
    signed_document_key: Optional[str] = None
    audit_trail_key: Optional[str] = None
    metadata: Dict[str, Any] = None


class SignatureProvider(ABC):
    """Interfaccia standard. Implementazioni concrete (Namirial, InfoCert, Aruba)
    vanno aggiunte in `signature_providers/` una alla volta con test.
    """
    level: SignatureLevel = "electronic_simple"
    provider_name: str = "generic"

    @abstractmethod
    async def create_envelope(self, *, contract_id: str, tenant_id: str,
                                 document_pdf: bytes, signers: List[SignerRequest],
                                 metadata: Dict[str, Any]) -> SignatureEnvelope:
        ...

    @abstractmethod
    async def send_for_signature(self, envelope: SignatureEnvelope) -> SignatureEnvelope:
        ...

    @abstractmethod
    async def poll_status(self, envelope: SignatureEnvelope) -> SignatureEnvelope:
        ...

    @abstractmethod
    async def download_signed(self, envelope: SignatureEnvelope) -> Optional[bytes]:
        ...

    @abstractmethod
    async def download_audit(self, envelope: SignatureEnvelope) -> Optional[bytes]:
        ...


class InternalSimpleProvider(SignatureProvider):
    """Firma elettronica semplice interna (canvas). Non chiamare mai FEA/FEQ.
    Implementata già nel router `contracts.py` — questa classe esiste solo per uniformare l'interfaccia."""
    level = "electronic_simple"
    provider_name = "internal_canvas"

    async def create_envelope(self, **kwargs):
        return SignatureEnvelope(provider=self.provider_name, external_id=None,
                                     signers=kwargs.get("signers") or [],
                                     status="created",
                                     metadata={"note": "handled internally via /contracts/public/{token}/sign"})

    async def send_for_signature(self, envelope):
        envelope.status = "sent"
        return envelope

    async def poll_status(self, envelope):
        return envelope

    async def download_signed(self, envelope):
        return None  # gestito dal PDF renderer contract con watermark FIRMATO

    async def download_audit(self, envelope):
        return None  # gestito da contracts.timeline endpoint


# -------------------------------------------------------------------------
# Registry & Factory
# -------------------------------------------------------------------------
_registered: Dict[str, SignatureProvider] = {
    "internal_canvas": InternalSimpleProvider(),
}


def register_provider(name: str, provider: SignatureProvider) -> None:
    _registered[name] = provider


def get_provider(name: str = "internal_canvas") -> SignatureProvider:
    if name not in _registered:
        raise ValueError(f"Signature provider '{name}' non registrato. Disponibili: {list(_registered)}")
    return _registered[name]


def list_providers() -> List[Dict[str, Any]]:
    """Ritorna metadata provider registrati per UI configurazione."""
    return [
        {
            "name": p.provider_name,
            "level": p.level,
            "configured": _is_configured(p),
            "description": _description(p),
        }
        for p in _registered.values()
    ]


def _is_configured(p: SignatureProvider) -> bool:
    # Internal è sempre "configured"; esterni richiederanno config credenziali
    return p.provider_name == "internal_canvas"


def _description(p: SignatureProvider) -> str:
    if p.level == "electronic_simple":
        return "Firma elettronica semplice — canvas grafico + audit trail (IP, UA, hash SHA-256, timestamp)"
    if p.level == "electronic_advanced":
        return "Firma elettronica avanzata (FEA) — richiede provider esterno configurato"
    if p.level == "electronic_qualified":
        return "Firma elettronica qualificata (FEQ) AgID — richiede provider qualificato + SPID/CIE del firmatario"
    return "Provider firma esterno"
