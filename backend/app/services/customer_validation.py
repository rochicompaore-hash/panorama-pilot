"""Customer validation utilities — Enerhia Operating Core (Milestone 1 Part 2).

Regole di validazione condivise usate da customers/quotes/contracts.

- ``normalize_customer_type`` converte i valori legacy (``private``/``business``)
  nella nuova enum (``PRIVATE``/``COMPANY``/``TO_CONFIRM``).
- ``validate_customer_type_on_create`` valida i campi minimi in creazione:
  PRIVATE → nome + cognome, COMPANY → ragione sociale.
- ``validate_customer_type_on_update`` blocca l'invio di ``TO_CONFIRM`` in edit
  (il primo edit di un cliente legacy deve classificarlo).
- ``validate_customer_contract_readiness`` è il gate ``MISSING_CUSTOMER_TAX_CODE``
  invocato **solo** al momento di generare il contratto. NON viene invocato in
  fase di creazione lead/preventivo.

Nota: la funzione è isolata e riutilizzabile. Nessuna dipendenza da router
specifici: può essere collegata in futuro nel modulo Contratti (milestone
successiva) senza toccare l'anagrafica.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException

CUSTOMER_TYPE_PRIVATE = "PRIVATE"
CUSTOMER_TYPE_COMPANY = "COMPANY"
CUSTOMER_TYPE_TO_CONFIRM = "TO_CONFIRM"
VALID_CUSTOMER_TYPES = {CUSTOMER_TYPE_PRIVATE, CUSTOMER_TYPE_COMPANY, CUSTOMER_TYPE_TO_CONFIRM}


def normalize_customer_type(raw: Optional[str]) -> str:
    """Traduce i valori legacy nell'enum corrente."""
    if not raw:
        return CUSTOMER_TYPE_TO_CONFIRM
    v = raw.strip().upper()
    if v in {"PRIVATE", "PRIVATO"}:
        return CUSTOMER_TYPE_PRIVATE
    if v in {"COMPANY", "BUSINESS", "AZIENDA"}:
        return CUSTOMER_TYPE_COMPANY
    if v in {"TO_CONFIRM", "PENDING"}:
        return CUSTOMER_TYPE_TO_CONFIRM
    return CUSTOMER_TYPE_TO_CONFIRM


def validate_customer_type_on_create(customer_type: str, first_name: Optional[str],
                                     last_name: Optional[str],
                                     company_name: Optional[str]) -> str:
    """Valida i campi minimi al POST /customers. Ritorna il tipo normalizzato."""
    ct = normalize_customer_type(customer_type)
    if ct == CUSTOMER_TYPE_TO_CONFIRM:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "CUSTOMER_TYPE_REQUIRED",
                "message": "Selezionare PRIVATE o COMPANY per creare un nuovo cliente.",
            },
        )
    if ct == CUSTOMER_TYPE_PRIVATE:
        if not (first_name and last_name):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "PRIVATE_REQUIRES_NAME",
                    "message": "Nome e Cognome sono obbligatori per un cliente PRIVATO.",
                },
            )
    if ct == CUSTOMER_TYPE_COMPANY:
        if not company_name:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "COMPANY_REQUIRES_NAME",
                    "message": "Ragione sociale obbligatoria per un cliente AZIENDA.",
                },
            )
    return ct


def validate_customer_type_on_update(new_type: Optional[str], current_doc: Dict[str, Any],
                                     payload: Dict[str, Any]) -> Optional[str]:
    """Valida customer_type in PATCH. Se il cliente è legacy (TO_CONFIRM), la
    prima modifica DEVE fornire un tipo valido diverso da TO_CONFIRM."""
    current_type = normalize_customer_type(current_doc.get("customer_type"))
    target_type = normalize_customer_type(new_type) if new_type else current_type

    # Cliente legacy: primo edit obbligato a classificare
    if current_type == CUSTOMER_TYPE_TO_CONFIRM and target_type == CUSTOMER_TYPE_TO_CONFIRM:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "CUSTOMER_TYPE_REQUIRED",
                "message": "Selezionare PRIVATE o COMPANY per completare l'anagrafica cliente.",
            },
        )
    if new_type and normalize_customer_type(new_type) == CUSTOMER_TYPE_TO_CONFIRM:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "CUSTOMER_TYPE_INVALID_UPDATE",
                "message": "Non è possibile impostare customer_type=TO_CONFIRM.",
            },
        )

    # Se cambia il tipo, verificare che i dati minimi siano coerenti
    if target_type == CUSTOMER_TYPE_PRIVATE:
        first = payload.get("first_name", current_doc.get("first_name"))
        last = payload.get("last_name", current_doc.get("last_name"))
        if not (first and last):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "PRIVATE_REQUIRES_NAME",
                    "message": "Nome e Cognome obbligatori per PRIVATE.",
                },
            )
    if target_type == CUSTOMER_TYPE_COMPANY:
        company = payload.get("company_name", current_doc.get("company_name"))
        if not company:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "COMPANY_REQUIRES_NAME",
                    "message": "Ragione sociale obbligatoria per COMPANY.",
                },
            )
    return target_type


def validate_customer_contract_readiness(customer: Dict[str, Any]) -> None:
    """Gate applicato al passaggio Quote → Contract.

    Rifiuta con ``MISSING_CUSTOMER_TAX_CODE`` se il cliente non ha i dati
    fiscali minimi richiesti per la generazione del contratto:
    - PRIVATE  → tax_code obbligatorio
    - COMPANY  → vat_number obbligatorio (fallback tax_code se P.IVA mancante)
    - TO_CONFIRM → richiede prima la classificazione.

    Da collegare nel router Contracts (fase 2 milestone Contratto). Non è
    invocata in fase di creazione lead/preventivo/PDF preventivo.
    """
    ct = normalize_customer_type(customer.get("customer_type"))
    if ct == CUSTOMER_TYPE_TO_CONFIRM:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "CUSTOMER_TYPE_REQUIRED",
                "message": "Classificare il cliente (PRIVATO/AZIENDA) prima di generare il contratto.",
            },
        )
    if ct == CUSTOMER_TYPE_PRIVATE and not customer.get("tax_code"):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MISSING_CUSTOMER_TAX_CODE",
                "message": "Codice fiscale obbligatorio per generare il contratto (cliente PRIVATO).",
            },
        )
    if ct == CUSTOMER_TYPE_COMPANY:
        if not (customer.get("vat_number") or customer.get("tax_code")):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "MISSING_CUSTOMER_TAX_CODE",
                    "message": "P.IVA (o codice fiscale) obbligatoria per generare il contratto (cliente AZIENDA).",
                },
            )
