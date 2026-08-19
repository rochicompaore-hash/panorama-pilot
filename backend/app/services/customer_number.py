"""Customer number generator — Enerhia Operating Core (Milestone 1 Part 2).

Progressivo continuo per tenant nel formato ``CLI-000001``:
- univoco
- atomico (find_one_and_update con $inc)
- non riutilizzabile dopo cancellazione/archiviazione (il contatore non torna indietro)
- indipendente dall'utente che crea il cliente
- **niente reset annuale**
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

SEQUENCE_KEY = "customer"
SEQUENCE_PREFIX = "CLI-"
SEQUENCE_PADDING = 6


def _format(number: int) -> str:
    return f"{SEQUENCE_PREFIX}{str(number).zfill(SEQUENCE_PADDING)}"


async def _ensure_sequence(db, tenant_id: str) -> Dict[str, Any]:
    seq = await db.sequences.find_one({"tenant_id": tenant_id, "key": SEQUENCE_KEY})
    if seq:
        return seq
    import uuid
    now = datetime.now(timezone.utc)
    doc = {
        "_id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "key": SEQUENCE_KEY,
        "label": "Clienti",
        "prefix": SEQUENCE_PREFIX,
        "suffix": "",
        "padding": SEQUENCE_PADDING,
        "current_number": 0,
        "year_reset": False,
        "current_year": None,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
        "status": "active",
        "version": 1,
    }
    try:
        await db.sequences.insert_one(doc)
    except Exception:
        # race: recupera il documento creato in parallelo
        pass
    return await db.sequences.find_one({"tenant_id": tenant_id, "key": SEQUENCE_KEY})


async def next_customer_number(db, tenant_id: str) -> str:
    """Ottiene atomicamente il prossimo customer_number per il tenant."""
    await _ensure_sequence(db, tenant_id)
    updated = await db.sequences.find_one_and_update(
        {"tenant_id": tenant_id, "key": SEQUENCE_KEY},
        {"$inc": {"current_number": 1},
         "$set": {"updated_at": datetime.now(timezone.utc)}},
        return_document=True,
    )
    return _format(updated["current_number"])
