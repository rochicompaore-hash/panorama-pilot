"""AUDIT V1 · Cleanup production_config duplicates.

Rimuove i doc `production_config` duplicati per tenant, MANTENENDO il record
con `updated_at` più recente (fallback: `created_at`, poi `_id` lessicografico).

**Modalità default: DRY-RUN**. Nessuna modifica al DB. Stampa report:
    | tenant_id | count | keeping_id | discarding_ids | reason |

Per eseguire realmente la cancellazione:
    python3 scripts/cleanup_production_config_duplicates.py --apply

Prerequisiti prima dell'attivazione unique index (BUG-15 audit v1):
1. Eseguire in DRY-RUN e verificare che il record `keeping_id` sia quello atteso
2. Eventualmente specificare `--prefer-id <id>` per forzare un id specifico
3. Solo dopo esecuzione reale, l'unique index `ux_production_config_tenant` può
   essere attivato senza conflitto (già definito in app/services/indexes.py)

Uso in produzione (dopo re-deploy dei fix audit):
    ssh <prod-host>
    cd /app/backend
    python3 scripts/cleanup_production_config_duplicates.py           # dry-run
    python3 scripts/cleanup_production_config_duplicates.py --apply   # apply

Rollback: nessun rollback automatico. Prima dell'apply consigliato mongo dump:
    mongodump --uri="$MONGO_URL" --db="$DB_NAME" --collection=production_config
"""
from __future__ import annotations
import argparse
import asyncio
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# Load env se eseguito standalone
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

from motor.motor_asyncio import AsyncIOMotorClient


def _dt(v: Any) -> str:
    """Formatta datetime per la stampa."""
    if v is None:
        return "-"
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


def _score_doc(doc: Dict[str, Any]) -> tuple:
    """Ritorna una chiave di ordinamento: più alto = più recente = KEEP.

    Priorità:
      1. updated_at (se presente)
      2. created_at (se presente)
      3. _id lessicografico (stabile)
    """
    return (
        doc.get("updated_at") or datetime.min.replace(tzinfo=None),
        doc.get("created_at") or datetime.min.replace(tzinfo=None),
        str(doc.get("_id", "")),
    )


async def find_duplicates(db) -> List[Dict[str, Any]]:
    """Aggrega per tenant_id e ritorna solo quelli con n>1."""
    pipeline = [
        {"$group": {
            "_id": "$tenant_id",
            "count": {"$sum": 1},
            "docs": {"$push": "$$ROOT"},
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": -1}},
    ]
    return await db.production_config.aggregate(pipeline).to_list(1000)


async def resolve_plan(dup_groups: List[Dict[str, Any]],
                       prefer_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Per ogni gruppo determina keep_id e discard_ids."""
    plan: List[Dict[str, Any]] = []
    for group in dup_groups:
        tenant_id = group["_id"]
        docs = group["docs"]
        # Ordina docs: più recente = ultimo
        ordered = sorted(docs, key=_score_doc)
        keep = ordered[-1]  # più recente
        reason = "most_recent_updated_at"
        if prefer_id:
            forced = next((d for d in docs if d.get("_id") == prefer_id), None)
            if forced:
                keep = forced
                reason = f"forced_by_--prefer-id={prefer_id}"
        discard = [d for d in docs if d.get("_id") != keep.get("_id")]
        plan.append({
            "tenant_id": tenant_id,
            "count": group["count"],
            "keeping_id": keep.get("_id"),
            "keeping_updated_at": _dt(keep.get("updated_at")),
            "keeping_created_at": _dt(keep.get("created_at")),
            "discarding": [{
                "id": d.get("_id"),
                "updated_at": _dt(d.get("updated_at")),
                "created_at": _dt(d.get("created_at")),
            } for d in discard],
            "reason": reason,
        })
    return plan


def print_report(plan: List[Dict[str, Any]], apply: bool) -> None:
    mode = "APPLY" if apply else "DRY-RUN"
    total_tenants = len(plan)
    total_to_delete = sum(len(p["discarding"]) for p in plan)
    print("=" * 78)
    print(f"CLEANUP production_config DUPLICATES · {mode}")
    print("=" * 78)
    print(f"Tenant con duplicati: {total_tenants}")
    print(f"Documenti da eliminare (totale): {total_to_delete}")
    print()
    for i, p in enumerate(plan, 1):
        print(f"[{i}/{total_tenants}] tenant={p['tenant_id']}  count={p['count']}")
        print(f"  KEEP    id={p['keeping_id']}")
        print(f"          updated_at={p['keeping_updated_at']}  created_at={p['keeping_created_at']}")
        print(f"          reason={p['reason']}")
        for d in p["discarding"]:
            print(f"  DELETE  id={d['id']}  updated_at={d['updated_at']}  created_at={d['created_at']}")
        print()
    print("=" * 78)
    if apply:
        print("MODE=APPLY — cancellazione eseguita.")
    else:
        print("MODE=DRY-RUN — nessuna modifica. Rilancia con --apply per eseguire.")
    print("=" * 78)


async def execute_delete(db, plan: List[Dict[str, Any]]) -> int:
    """Esegue le cancellazioni. Ritorna il numero totale eliminato."""
    total = 0
    for p in plan:
        ids_to_delete = [d["id"] for d in p["discarding"]]
        if not ids_to_delete:
            continue
        res = await db.production_config.delete_many({"_id": {"$in": ids_to_delete}})
        total += res.deleted_count
    return total


async def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup production_config duplicates per tenant.")
    parser.add_argument("--apply", action="store_true",
                         help="Esegui davvero la cancellazione (default: dry-run).")
    parser.add_argument("--prefer-id", type=str, default=None,
                         help="Forza un id specifico come 'keep' (utile per override manuale).")
    parser.add_argument("--tenant-id", type=str, default=None,
                         help="Limita l'operazione a un solo tenant (safety).")
    args = parser.parse_args()

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("ERRORE: MONGO_URL e DB_NAME devono essere presenti in env", file=sys.stderr)
        return 2

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    dup_groups = await find_duplicates(db)
    if args.tenant_id:
        dup_groups = [g for g in dup_groups if g["_id"] == args.tenant_id]
    if not dup_groups:
        print("Nessun duplicato trovato. Nulla da fare.")
        return 0

    plan = await resolve_plan(dup_groups, prefer_id=args.prefer_id)
    print_report(plan, apply=args.apply)

    if args.apply:
        deleted = await execute_delete(db, plan)
        print(f"\n✅ Eliminati {deleted} documenti.")
        # Verifica no-duplicati residui
        residual = await find_duplicates(db)
        if residual:
            print(f"⚠️  ATTENZIONE: {len(residual)} tenant hanno ancora duplicati. Rilancia lo script.")
            return 3
        print("✅ Nessun duplicato residuo. Puoi attivare l'unique index in sicurezza.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
