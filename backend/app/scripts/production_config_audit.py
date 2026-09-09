"""Production config audit — SOLO configurativo. Stampa CONFIGURED / MISSING / INVALID, MAI i valori.

Uso: python -m app.scripts.production_config_audit [--target production]
"""
from __future__ import annotations
import os
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
TARGET = "production" if "--target" in sys.argv and "production" in sys.argv else os.environ.get("APP_ENV", "development")


def _url_ok(v: str, schemes) -> bool:
    try:
        u = urlparse(v)
        return u.scheme in schemes and bool(u.netloc)
    except Exception:
        return False


def check(name: str, required: bool, validator=None, note: str = ""):
    v = os.environ.get(name, "")
    if not v:
        return name, ("MISSING" if required else "NOT_CONFIGURED (optional)"), note
    if validator and not validator(v):
        return name, "INVALID", note
    return name, "CONFIGURED", note


prod = TARGET in ("production", "prod", "staging", "stage")
email_provider = (os.environ.get("EMAIL_PROVIDER") or "").lower()
smtp_mode = bool(os.environ.get("MAIL_HOST"))

rows = [
    # database
    check("MONGO_URL", True, lambda v: _url_ok(v, ("mongodb", "mongodb+srv"))),
    check("DB_NAME", True),
    # redis (rate limiting OTP/firma: fail-closed in prod)
    check("REDIS_URL", prod, lambda v: _url_ok(v, ("redis", "rediss")) and ("127.0.0.1" not in v and "localhost" not in v if prod else True),
          "prod: managed Redis (rediss:// consigliato), mai localhost"),
    # auth
    check("JWT_SECRET", True, lambda v: len(v) >= 32 and v not in ("changeme", "secret"), ">=32 char"),
    check("ADMIN_EMAIL", True, lambda v: "@" in v),
    check("ADMIN_PASSWORD", True, lambda v: len(v) >= 12, ">=12 char, diversa da ogni credenziale riportata in chat/report"),
    check("ACCESS_TOKEN_EXPIRE_MINUTES", False), check("REFRESH_TOKEN_EXPIRE_DAYS", False),
    check("MAX_FAILED_LOGIN_ATTEMPTS", False), check("LOGIN_LOCK_MINUTES", False),
    # urls / cors
    check("APP_BASE_URL", True, lambda v: _url_ok(v, ("https",)) if prod else _url_ok(v, ("http", "https")), "prod: https"),
    check("CORS_ORIGINS", True, lambda v: (v != "*") if prod else True, "prod: origini esplicite, non '*'"),
    # email (OTP firma pubblica dipende da email reale)
    check("EMAIL_PROVIDER", True, lambda v: v.lower() != "mock" if prod else True, "prod: smtp|resend (mock vietato)"),
    check("MAIL_DELIVERY_MODE", True, lambda v: v.lower() == "live" if prod else True, "prod: live (test = redirect destinatari)"),
    check("MAIL_PASSWORD", prod and (smtp_mode and email_provider != "resend"), None, "SMTP auth (Emergent Secret)"),
    check("RESEND_API_KEY", prod and email_provider == "resend", None, "se EMAIL_PROVIDER=resend"),
    check("MAIL_HOST", prod and email_provider not in ("resend",), None), check("MAIL_FROM", prod),
    # otp
    check("OTP_DEBUG_ENABLED", True, lambda v: v.lower() in ("false", "0", "no") if prod else True, "prod: false (mai OTP in risposta)"),
    check("OTP_TTL_SECONDS", False), check("OTP_LENGTH", False),
    # storage / pdf
    check("STORAGE_PROVIDER", True),
    check("STORAGE_LOCAL_PATH", (os.environ.get("STORAGE_PROVIDER") or "local").lower() == "local"),
    check("S3_BUCKET", (os.environ.get("STORAGE_PROVIDER") or "").lower() in ("s3", "object_storage")),
    # google auth (Emergent managed) / llm
    check("EMERGENT_LLM_KEY", False, None, "Google Sign-In managed / LLM"),
    # env flags
    check("APP_ENV", True, lambda v: v.lower() in ("production", "prod", "staging") if prod else True, "prod: production"),
    check("RELEASE_STAGE", False), check("DEMO_SEED_ENABLED", True, lambda v: v.lower() in ("false", "0") if prod else True, "prod: false"),
    check("TEST_DATA_ENABLED", True, lambda v: v.lower() in ("false", "0") if prod else True, "prod: false"),
    check("DEMO_MODE", False, lambda v: v.lower() in ("false", "0") if prod else True, "prod: false"),
    check("TEST_LIMITED_EMAIL", False, lambda v: not prod, "prod: NON deve esistere"),
]

fonts_ok = all(os.path.exists(os.path.join(os.path.dirname(__file__), "..", "templates", "fonts", f)) for f in ("Roboto-Regular.ttf", "Roboto-Bold.ttf"))
rows.append(("PDF_FONTS_ROBOTO", "CONFIGURED" if fonts_ok else "MISSING", "app/templates/fonts vendorizzati"))

fail = False
print(f"PRODUCTION CONFIG AUDIT — target={TARGET}")
for name, status, note in rows:
    flag = "" if status.startswith("CONFIGURED") or "optional" in status else "  <-- STOP"
    if flag:
        fail = True
    print(f"  {name:32s} {status:26s} {note}{flag}")
print("RESULT:", "FAIL" if fail else "PASS")
sys.exit(1 if fail else 0)
