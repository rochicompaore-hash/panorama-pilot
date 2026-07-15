"""StorageProvider abstract + Local (dev) + S3-compatible (prod).

Path pattern: {tenant_id}/{module}/{entity}/{uuid}_{safe_filename}
"""
from __future__ import annotations
import os
import re
import io
import uuid
from typing import Optional
from app.config import settings

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")

BLOCKED_EXT = {".exe", ".bat", ".sh", ".cmd", ".com", ".scr", ".msi", ".dll"}


def sanitize_filename(name: str) -> str:
    name = os.path.basename(name or "file")
    name = _SAFE_NAME.sub("_", name)
    if len(name) > 200:
        base, ext = os.path.splitext(name)
        name = base[:200 - len(ext)] + ext
    return name or "file"


def build_key(tenant_id: str, module: str, entity: str, filename: str) -> str:
    fn = sanitize_filename(filename)
    ext = os.path.splitext(fn)[1].lower()
    if ext in BLOCKED_EXT:
        raise ValueError(f"Estensione non consentita: {ext}")
    return f"{tenant_id}/{module}/{entity}/{uuid.uuid4()}_{fn}"


class StorageProvider:
    def put(self, key: str, data: bytes, content_type: str) -> None:
        raise NotImplementedError

    def get(self, key: str) -> bytes:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def signed_url(self, key: str, expires: int = 900) -> Optional[str]:
        return None


class LocalStorageProvider(StorageProvider):
    name = "local"

    def __init__(self):
        os.makedirs(settings.STORAGE_LOCAL_PATH, exist_ok=True)

    def _path(self, key: str) -> str:
        p = os.path.join(settings.STORAGE_LOCAL_PATH, key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def put(self, key: str, data: bytes, content_type: str) -> None:
        with open(self._path(key), "wb") as f:
            f.write(data)

    def get(self, key: str) -> bytes:
        with open(self._path(key), "rb") as f:
            return f.read()

    def delete(self, key: str) -> None:
        p = self._path(key)
        if os.path.exists(p):
            os.remove(p)


class S3StorageProvider(StorageProvider):
    name = "s3"

    def __init__(self):
        import boto3  # type: ignore
        self._s3 = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT or None,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
        )
        self._bucket = settings.S3_BUCKET

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        obj = self._s3.get_object(Bucket=self._bucket, Key=key)
        return obj["Body"].read()

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=key)

    def signed_url(self, key: str, expires: int = 900) -> Optional[str]:
        return self._s3.generate_presigned_url(
            "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=expires
        )


_provider: Optional[StorageProvider] = None


def get_storage() -> StorageProvider:
    global _provider
    if _provider is None:
        if settings.STORAGE_PROVIDER == "s3":
            _provider = S3StorageProvider()
        else:
            _provider = LocalStorageProvider()
    return _provider
