"""Resend provider — API client (send/domains) + Svix webhook signature verification.
Secrets solo da env: RESEND_API_KEY, RESEND_WEBHOOK_SECRET. Mai loggati, mai esposti."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Any, Dict, List, Optional

import httpx

RESEND_BASE_URL = "https://api.resend.com"
WEBHOOK_TOLERANCE_SEC = 300


class ResendError(RuntimeError):
    def __init__(self, status: int, message: str, name: Optional[str] = None):
        super().__init__(f"{status} {name or ''} {message}".strip())
        self.status, self.name, self.message = status, name, message

    @property
    def is_temporary(self) -> bool:
        return self.status in (408, 425, 429, 500, 502, 503, 504)


def api_key() -> str:
    return os.environ.get("RESEND_API_KEY", "").strip()


def webhook_secret() -> str:
    return os.environ.get("RESEND_WEBHOOK_SECRET", "").strip()


def is_configured() -> bool:
    return bool(api_key())


def webhook_configured() -> bool:
    return bool(webhook_secret())


async def _request(method: str, path: str, json: Optional[dict] = None, headers: Optional[dict] = None) -> Dict[str, Any]:
    h = {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json", **(headers or {})}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.request(method, f"{RESEND_BASE_URL}{path}", json=json, headers=h)
    if r.status_code >= 400:
        try:
            body = r.json()
        except Exception:  # noqa: BLE001
            body = {}
        raise ResendError(r.status_code, str(body.get("message") or r.text[:300]), body.get("name"))
    return r.json() if r.content else {}


async def send_email(*, from_email: str, from_name: str, to: str, subject: str, html: str, text: str,
                     reply_to: Optional[str] = None, attachments: Optional[List[Dict[str, Any]]] = None,
                     idempotency_key: Optional[str] = None, tags: Optional[Dict[str, str]] = None) -> str:
    """Ritorna il provider email id. attachments: [{filename, content(bytes)}]."""
    payload: Dict[str, Any] = {"from": f"{from_name} <{from_email}>" if from_name else from_email, "to": [to],
                               "subject": subject, "html": html, "text": text}
    if reply_to:
        payload["reply_to"] = reply_to
    if attachments:
        payload["attachments"] = [{"filename": a["filename"], "content": base64.b64encode(a["content"]).decode("ascii")} for a in attachments]
    if tags:
        payload["tags"] = [{"name": k, "value": _tag_value(v)} for k, v in tags.items()]
    headers = {"Idempotency-Key": idempotency_key[:256]} if idempotency_key else None
    data = await _request("POST", "/emails", json=payload, headers=headers)
    return str(data.get("id"))


def _tag_value(v: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(v))[:256]


async def create_domain(name: str, region: str = "eu-west-1") -> Dict[str, Any]:
    return await _request("POST", "/domains", json={"name": name, "region": region})


async def get_domain(domain_id: str) -> Dict[str, Any]:
    return await _request("GET", f"/domains/{domain_id}")


async def verify_domain(domain_id: str) -> Dict[str, Any]:
    return await _request("POST", f"/domains/{domain_id}/verify")


async def list_domains() -> List[Dict[str, Any]]:
    return (await _request("GET", "/domains")).get("data") or []


def verify_webhook(raw_body: bytes, svix_id: str, svix_timestamp: str, svix_signature: str) -> bool:
    """Svix scheme: HMAC-SHA256(base64decode(secret[len('whsec_'):]), f'{id}.{ts}.{body}') in base64, header 'v1,<sig> v1,<sig2>'."""
    secret = webhook_secret()
    if not (secret and svix_id and svix_timestamp and svix_signature):
        return False
    try:
        ts = int(svix_timestamp)
    except ValueError:
        return False
    if abs(time.time() - ts) > WEBHOOK_TOLERANCE_SEC:
        return False
    key = base64.b64decode(secret.split("_", 1)[1] if secret.startswith("whsec_") else secret)
    signed = f"{svix_id}.{svix_timestamp}.".encode() + raw_body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    for part in svix_signature.split(" "):
        if "," in part:
            version, sig = part.split(",", 1)
            if version == "v1" and hmac.compare_digest(sig, expected):
                return True
    return False
