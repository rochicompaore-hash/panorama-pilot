"""Backup pre-deploy — export JSON compresso di tutte le collection + manifest (release/build id, migration state, config keys).

Nessun secret nel manifest (solo NOMI delle variabili configurate). Uso:
  python -m app.scripts.backup_pre_deploy            -> /app/backups/<timestamp>/
  python -m app.scripts.backup_pre_deploy --restore /app/backups/<timestamp>   (ripristino: drop+insert per collection)
"""
from __future__ import annotations
import asyncio
import gzip
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from bson import json_util
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
ROOT = os.environ.get("BACKUP_ROOT", "/app/backups")
SECRET_HINTS = ("PASSWORD", "SECRET", "KEY", "TOKEN", "URL")


def _git(*args):
    try:
        return subprocess.check_output(["git", *args], cwd="/app", stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


async def backup():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = os.path.join(ROOT, ts)
    os.makedirs(out, exist_ok=True)
    counts = {}
    for name in sorted(await db.list_collection_names()):
        docs = await db[name].find({}).to_list(None)
        counts[name] = len(docs)
        with gzip.open(os.path.join(out, f"{name}.json.gz"), "wt", encoding="utf-8") as f:
            f.write(json_util.dumps(docs))
    migrations = await db.migrations.find({}, {"_id": 0}).sort("applied_at", -1).to_list(50) if "migrations" in counts else []
    manifest = {
        "timestamp": ts, "db_name": os.environ["DB_NAME"],
        "release": {"git_commit": _git("rev-parse", "HEAD"), "git_short": _git("rev-parse", "--short", "HEAD"), "branch": _git("rev-parse", "--abbrev-ref", "HEAD")},
        "migration_state": migrations,
        "general_terms_version": (await db.general_terms_snapshots.find_one({}, sort=[("created_at", -1)]) or {}).get("version"),
        "collections": counts,
        "config_keys_configured": sorted(k for k, v in os.environ.items() if v and (k.isupper()) and not k.startswith(("LC_", "XDG", "LS_", "PS1"))),
        "note": "Nessun valore di secret incluso. Restore: python -m app.scripts.backup_pre_deploy --restore <dir>",
    }
    with open(os.path.join(out, "MANIFEST.json"), "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    print(f"BACKUP OK -> {out}  collections={len(counts)} docs={sum(counts.values())} release={manifest['release']['git_short']}")
    return out


async def restore(path: str):
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    for fn in sorted(os.listdir(path)):
        if not fn.endswith(".json.gz"):
            continue
        name = fn[:-8]
        with gzip.open(os.path.join(path, fn), "rt", encoding="utf-8") as f:
            docs = json_util.loads(f.read())
        await db[name].drop()
        if docs:
            await db[name].insert_many(docs)
        print(f"restored {name}: {len(docs)}")
    print("RESTORE OK")


if __name__ == "__main__":
    if "--restore" in sys.argv:
        asyncio.run(restore(sys.argv[sys.argv.index("--restore") + 1]))
    else:
        asyncio.run(backup())
