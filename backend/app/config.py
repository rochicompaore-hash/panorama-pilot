import os

class Settings:
    MONGO_URL: str = os.environ["MONGO_URL"]
    DB_NAME: str = os.environ["DB_NAME"]
    JWT_SECRET: str = os.environ["JWT_SECRET"]
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    INVITATION_EXPIRE_HOURS: int = int(os.environ.get("INVITATION_EXPIRE_HOURS", "72"))
    PASSWORD_RESET_EXPIRE_MINUTES: int = int(os.environ.get("PASSWORD_RESET_EXPIRE_MINUTES", "30"))
    MAX_FAILED_LOGIN_ATTEMPTS: int = int(os.environ.get("MAX_FAILED_LOGIN_ATTEMPTS", "5"))
    LOGIN_LOCK_MINUTES: int = int(os.environ.get("LOGIN_LOCK_MINUTES", "15"))
    ADMIN_EMAIL: str = os.environ["ADMIN_EMAIL"]
    ADMIN_PASSWORD: str = os.environ["ADMIN_PASSWORD"]
    ADMIN_COMPANY_NAME: str = os.environ.get("ADMIN_COMPANY_NAME", "Infissi Express SRL")
    EMAIL_PROVIDER: str = os.environ.get("EMAIL_PROVIDER", "mock")
    RESEND_API_KEY: str = os.environ.get("RESEND_API_KEY", "")
    EMAIL_FROM: str = os.environ.get("EMAIL_FROM", "no-reply@infissiexpress.local")
    EMAIL_FROM_NAME: str = os.environ.get("EMAIL_FROM_NAME", "Infissi Express Cloud")
    # SMTP (SiteGround-ready). Password is NEVER stored/exposed by this class.
    MAIL_HOST: str = os.environ.get("MAIL_HOST", "")
    MAIL_PORT: int = int(os.environ.get("MAIL_PORT", "465") or "465")
    MAIL_SECURITY: str = os.environ.get("MAIL_SECURITY", "ssl")
    MAIL_USER: str = os.environ.get("MAIL_USER", "")
    MAIL_FROM: str = os.environ.get("MAIL_FROM", "")
    MAIL_FROM_NAME: str = os.environ.get("MAIL_FROM_NAME", "Infissi Express Cloud")
    MAIL_REPLY_TO: str = os.environ.get("MAIL_REPLY_TO", "")
    MAIL_DELIVERY_MODE: str = os.environ.get("MAIL_DELIVERY_MODE", "test").lower()
    MAIL_TEST_REDIRECT_TO: str = os.environ.get("MAIL_TEST_REDIRECT_TO", "")
    APP_BASE_URL: str = os.environ.get("APP_BASE_URL", "http://localhost:3000")
    STORAGE_PROVIDER: str = os.environ.get("STORAGE_PROVIDER", "local")
    STORAGE_LOCAL_PATH: str = os.environ.get("STORAGE_LOCAL_PATH", "/app/storage")
    S3_BUCKET: str = os.environ.get("S3_BUCKET", "")
    S3_ENDPOINT: str = os.environ.get("S3_ENDPOINT", "")
    S3_ACCESS_KEY: str = os.environ.get("S3_ACCESS_KEY", "")
    S3_SECRET_KEY: str = os.environ.get("S3_SECRET_KEY", "")
    S3_REGION: str = os.environ.get("S3_REGION", "eu-west-1")
    MAX_UPLOAD_SIZE_MB: int = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "25"))
    CORS_ORIGINS: str = os.environ.get("CORS_ORIGINS", "*")

    # M3.3.4 — Redis / rate limiter / OTP / signature
    APP_ENV: str = os.environ.get("APP_ENV", "development").lower()  # development|test|staging|production
    REDIS_URL: str = os.environ.get("REDIS_URL", "")
    DEGRADED_PUBLIC_VIEW_ALLOWED: bool = os.environ.get("DEGRADED_PUBLIC_VIEW_ALLOWED", "true").lower() == "true"
    # Rate limits
    RATE_LIMIT_LINK_OPEN_PER_MIN: int = int(os.environ.get("RATE_LIMIT_LINK_OPEN_PER_MIN", "30"))
    RATE_LIMIT_PDF_DOWNLOAD_PER_MIN: int = int(os.environ.get("RATE_LIMIT_PDF_DOWNLOAD_PER_MIN", "10"))
    RATE_LIMIT_OTP_REQUEST_WINDOW_SEC: int = int(os.environ.get("RATE_LIMIT_OTP_REQUEST_WINDOW_SEC", "600"))
    RATE_LIMIT_OTP_REQUEST_MAX: int = int(os.environ.get("RATE_LIMIT_OTP_REQUEST_MAX", "3"))
    RATE_LIMIT_OTP_REQUEST_COOLDOWN_SEC: int = int(os.environ.get("RATE_LIMIT_OTP_REQUEST_COOLDOWN_SEC", "60"))
    RATE_LIMIT_OTP_REQUEST_DAILY_MAX: int = int(os.environ.get("RATE_LIMIT_OTP_REQUEST_DAILY_MAX", "10"))
    RATE_LIMIT_OTP_VERIFY_MAX_ATTEMPTS: int = int(os.environ.get("RATE_LIMIT_OTP_VERIFY_MAX_ATTEMPTS", "5"))
    RATE_LIMIT_OTP_VERIFY_DAILY_MAX_FAIL: int = int(os.environ.get("RATE_LIMIT_OTP_VERIFY_DAILY_MAX_FAIL", "20"))
    RATE_LIMIT_SIGN_PER_HOUR: int = int(os.environ.get("RATE_LIMIT_SIGN_PER_HOUR", "5"))
    # OTP
    OTP_TTL_SECONDS: int = int(os.environ.get("OTP_TTL_SECONDS", "600"))
    OTP_LENGTH: int = int(os.environ.get("OTP_LENGTH", "6"))
    # OTP debug: espone il codice in chiaro nella risposta API. SOLO dev/test.
    # In produzione forzato a False anche se env dice true.
    _otp_debug_raw: bool = os.environ.get("OTP_DEBUG_ENABLED", "true").lower() == "true"
    _otp_debug_prod_safe: bool = _otp_debug_raw and os.environ.get("APP_ENV", "development").lower() not in ("staging", "stage", "production", "prod")
    OTP_DEBUG_ENABLED: bool = _otp_debug_prod_safe
    # Signature
    SIGNATURE_EVIDENCE_ISSUER: str = os.environ.get("SIGNATURE_EVIDENCE_ISSUER", "Infissi Express Cloud")

    # Release stage — controls demo data seeding
    RELEASE_STAGE: str = os.environ.get("RELEASE_STAGE", "development")  # development | first_operational_release | production
    DEMO_SEED_ENABLED: bool = os.environ.get("DEMO_SEED_ENABLED", "true").lower() == "true"
    TEST_DATA_ENABLED: bool = os.environ.get("TEST_DATA_ENABLED", "true").lower() == "true"

settings = Settings()

def is_dev_or_test() -> bool:
    return settings.APP_ENV in ("development", "dev", "test", "testing")


def is_prod_like() -> bool:
    return settings.APP_ENV in ("staging", "stage", "production", "prod")


def is_demo_mode() -> bool:
    """True only if demo data seeding is explicitly enabled AND stage allows it."""
    if settings.RELEASE_STAGE in ("first_operational_release", "production", "prod"):
        return False
    return settings.DEMO_SEED_ENABLED
