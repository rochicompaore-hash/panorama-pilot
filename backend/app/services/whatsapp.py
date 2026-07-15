"""WhatsApp provider abstraction. Mock in dev + Twilio stub for production."""
from __future__ import annotations
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from app.config import settings
from app.db import get_db
from app.models import new_id

logger = logging.getLogger("whatsapp")


class WhatsAppProvider:
    name = "abstract"

    async def _deliver(self, to: str, body: Optional[str], template_id: Optional[str],
                       template_variables: Optional[Dict[str, Any]], subject: Optional[str]) -> Optional[str]:
        raise NotImplementedError


class MockWhatsAppProvider(WhatsAppProvider):
    name = "mock"

    async def _deliver(self, to, body, template_id, template_variables, subject) -> Optional[str]:
        logger.info("========== [MOCK WHATSAPP] ==========")
        logger.info("To: %s", to)
        logger.info("Subject: %s", subject)
        logger.info("Template: %s Variables: %s", template_id, template_variables)
        logger.info("Body:\n%s", body)
        logger.info("=====================================")
        return f"mock_{new_id()[:12]}"


class TwilioWhatsAppProvider(WhatsAppProvider):
    """Production stub. Requires TWILIO_* env vars and `twilio` package."""
    name = "twilio"

    def __init__(self):
        sid = os.environ.get("TWILIO_ACCOUNT_SID")
        tok = os.environ.get("TWILIO_AUTH_TOKEN")
        self.from_ = os.environ.get("TWILIO_WHATSAPP_FROM")
        if not (sid and tok and self.from_):
            raise RuntimeError("Twilio credentials not configured")
        try:
            from twilio.rest import Client  # type: ignore
        except ImportError as e:
            raise RuntimeError("twilio package not installed") from e
        self.client = Client(sid, tok)

    async def _deliver(self, to, body, template_id, template_variables, subject) -> Optional[str]:
        import json
        to_addr = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
        params: Dict[str, Any] = {"from_": self.from_, "to": to_addr}
        if template_id:
            params["content_sid"] = template_id
            if template_variables:
                params["content_variables"] = json.dumps(template_variables)
        elif body:
            params["body"] = body
        else:
            raise ValueError("Either body or template_id must be provided")
        msg = self.client.messages.create(**params)
        return msg.sid


_provider_instance: Optional[WhatsAppProvider] = None


def get_whatsapp_provider() -> WhatsAppProvider:
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance
    prov = os.environ.get("WHATSAPP_PROVIDER", "mock")
    if prov == "twilio":
        _provider_instance = TwilioWhatsAppProvider()
    else:
        _provider_instance = MockWhatsAppProvider()
    return _provider_instance


async def send_whatsapp(*, tenant_id: str, to: str, body: Optional[str] = None,
                       template_id: Optional[str] = None,
                       template_variables: Optional[Dict[str, Any]] = None,
                       subject: Optional[str] = None,
                       user_id: Optional[str] = None) -> Dict[str, Any]:
    """Send a WhatsApp message via configured provider. Never raises."""
    db = get_db()
    log_id = new_id()
    now = datetime.now(timezone.utc)
    log_doc = {
        "_id": log_id,
        "tenant_id": tenant_id,
        "to": to,
        "subject": subject,
        "body": body,
        "template_id": template_id,
        "template_variables": template_variables,
        "status": "queued",
        "error": None,
        "provider": os.environ.get("WHATSAPP_PROVIDER", "mock"),
        "provider_message_id": None,
        "direction": "out",
        "created_by": user_id,
        "created_at": now.isoformat(),
    }
    await db.whatsapp_logs.insert_one(log_doc)
    result = {"log_id": log_id, "status": "queued", "error": None, "provider_message_id": None}
    try:
        prov = get_whatsapp_provider()
        pmid = await prov._deliver(to=to, body=body, template_id=template_id,
                                   template_variables=template_variables, subject=subject)
        await db.whatsapp_logs.update_one({"_id": log_id},
                                          {"$set": {"status": "sent", "provider_message_id": pmid, "sent_at": datetime.now(timezone.utc).isoformat()}})
        result["status"] = "sent"
        result["provider_message_id"] = pmid
    except Exception as e:  # noqa: BLE001
        logger.exception("WhatsApp delivery failed to %s", to)
        await db.whatsapp_logs.update_one({"_id": log_id},
                                          {"$set": {"status": "failed", "error": str(e)[:500]}})
        result["status"] = "failed"
        result["error"] = str(e)
    return result
