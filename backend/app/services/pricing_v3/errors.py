"""Fail-closed error codes per la nuova architettura pricing.

Ogni errore deve indicare: cosa manca, quale componente, quale configurazione,
dove correggerlo. Nessun fallback silenzioso a 0.
"""
from __future__ import annotations
from typing import Any, Dict, Optional


ERROR_CODES = {
    "MISSING_PROFILE_SYSTEM": "Sistema profilo non trovato per il prodotto",
    "MISSING_TECHNICAL_RECIPE": "Ricetta tecnica non definita per questa configurazione",
    "MISSING_COMPONENT_MAPPING": "Mapping componente mancante nella ricetta",
    "MISSING_COMPONENT_PRICE": "Prezzo componente mancante nel listino",
    "MISSING_GLASS_PRICE": "Prezzo vetro mancante",
    "MISSING_HARDWARE_PRICE": "Prezzo ferramenta mancante",
    "MISSING_PRODUCTION_TIME": "Tempo di produzione non configurato",
    "MISSING_WORKSHOP_COST": "hourly_workshop_cost non configurato per il tenant",
    "MISSING_COMMERCIAL_MULTIPLIER": "Regola commerciale non configurata",
    "INVALID_CONFIGURATION": "Configurazione prodotto non valida",
    "INVALID_GEOMETRY": "Larghezza o altezza non valide",
    "SNAPSHOT_INTEGRITY_ERROR": "Hash snapshot non coincide con i dati salvati",
    "COMPUTED_ZERO": "Motore ha prodotto prezzo zero — configurazione anomala",
    "UNKNOWN_COLOR_CODE": "Codice colore non presente nel catalogo product_colors",
    "NEEDS_PO_PRICING": "Policy economica non definita per questa configurazione colore (SPECIAL)",
}


class PricingError(Exception):
    """Errore fail-closed del nuovo motore pricing.

    Attributi:
      code: uno di ERROR_CODES
      component_role: es. "FRAME", "GLASS", "HARDWARE" (opzionale)
      configuration: dict con contesto (opzionale)
      hint: dove correggerlo nella UI amministrativa
    """
    def __init__(
        self,
        code: str,
        message: Optional[str] = None,
        component_role: Optional[str] = None,
        configuration: Optional[Dict[str, Any]] = None,
        hint: Optional[str] = None,
    ):
        self.code = code
        self.component_role = component_role
        self.configuration = configuration or {}
        self.hint = hint
        self.message = message or ERROR_CODES.get(code, code)
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "component_role": self.component_role,
            "configuration": self.configuration,
            "hint": self.hint,
        }
