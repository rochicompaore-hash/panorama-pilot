"""Emergent Object Storage — PDF-specific service.

- No presigned URLs — download only through authorized backend endpoints.
- Session-scoped storage_key initialized once.
- Path: {APP_PREFIX}/tenants/{tenant_id}/quotes/{quote_id}/{revision}/{pdf_id}.pdf
"""
from __future__ import annotations
import logging
import os
import time
from typing import Optional
import requests

logger = logging.getLogger("obj_storage")

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_PREFIX = os.environ.get("APP_STORAGE_PREFIX", "infissi-express")

_storage_key: Optional[str] = None


class StorageError(Exception):
    pass


def init_storage(force: bool = False) -> Optional[str]:
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    if not EMERGENT_KEY:
        return None
    try:
        resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=15)
        resp.raise_for_status()
        _storage_key = resp.json()["storage_key"]
        logger.info("Emergent object storage initialized")
        return _storage_key
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
        return None


def is_available() -> bool:
    return init_storage() is not None


def build_pdf_path(tenant_id: str, quote_id: str, revision: str, pdf_id: str) -> str:
    rev = (revision or "R00").replace("/", "_").replace(" ", "_")
    return f"{APP_PREFIX}/tenants/{tenant_id}/quotes/{quote_id}/{rev}/{pdf_id}.pdf"


def put_pdf(path: str, data: bytes) -> dict:
    key = init_storage()
    if not key:
        raise StorageError("storage_unavailable")
    for attempt in range(3):
        try:
            resp = requests.put(
                f"{STORAGE_URL}/objects/{path}",
                headers={"X-Storage-Key": key, "Content-Type": "application/pdf"},
                data=data, timeout=120,
            )
            if resp.status_code == 403:
                init_storage(force=True); key = _storage_key; continue
            if resp.status_code == 429:
                time.sleep(2 ** attempt); continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            if attempt == 2:
                raise StorageError(f"put_pdf_failed: {e}")
            time.sleep(2 ** attempt)
    raise StorageError("put_pdf_failed_max_retries")


def get_pdf(path: str) -> bytes:
    key = init_storage()
    if not key:
        raise StorageError("storage_unavailable")
    for attempt in range(3):
        try:
            resp = requests.get(
                f"{STORAGE_URL}/objects/{path}",
                headers={"X-Storage-Key": key}, timeout=60,
            )
            if resp.status_code == 403:
                init_storage(force=True); key = _storage_key; continue
            if resp.status_code == 429:
                time.sleep(2 ** attempt); continue
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as e:
            if attempt == 2:
                raise StorageError(f"get_pdf_failed: {e}")
            time.sleep(2 ** attempt)
    raise StorageError("get_pdf_failed_max_retries")
