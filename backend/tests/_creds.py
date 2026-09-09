"""Test credential fixtures — read exclusively from environment variables.

Do NOT hardcode passwords, tokens or API keys in test source files.
All secrets must come from `backend/.env` (already loaded by `conftest.py`)
or from CI environment variables.

Import at top of each test file:

    from tests._creds import ADMIN_EMAIL, ADMIN_PASSWORD

If a required variable is missing, tests fail fast with a clear error —
this is the desired behaviour: silent fallbacks hide misconfiguration.
"""
from __future__ import annotations
import os
import secrets as _secrets


def _require(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(
            f"Missing required environment variable '{name}' for tests. "
            "Set it in backend/.env or export it in the CI environment."
        )
    return v


def _optional(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


# --- Primary tenant admin (seed) ---
ADMIN_EMAIL: str = _require("ADMIN_EMAIL")
ADMIN_PASSWORD: str = _require("ADMIN_PASSWORD")

# Legacy aliases used by pre-existing test modules — DO NOT re-hardcode.
ADMIN_PWD = ADMIN_PASSWORD
ADMIN_PW = ADMIN_PASSWORD
ADMIN_PASS = ADMIN_PASSWORD

# Compatibility tuple used by `test_stabilization_rc1.py`
SUPER_ADMIN = (ADMIN_EMAIL, ADMIN_PASSWORD)

# --- Optional secondary admins used by the stabilization suite ---
# All must be provided via env. If absent, tests that need them are skipped.
TENANT_ADMIN_EMAIL: str | None = _optional("TENANT_ADMIN_EMAIL")
TENANT_ADMIN_PASSWORD: str | None = _optional("TENANT_ADMIN_PASSWORD")
TENANT_ADMIN: tuple[str, str] | None = (
    (TENANT_ADMIN_EMAIL, TENANT_ADMIN_PASSWORD)
    if TENANT_ADMIN_EMAIL and TENANT_ADMIN_PASSWORD else None
)

PLATFORM_OWNER_EMAIL: str | None = _optional("PLATFORM_OWNER_EMAIL")
PLATFORM_OWNER_PASSWORD: str | None = _optional("PLATFORM_OWNER_PASSWORD")
PLATFORM_OWNER_ID: str | None = _optional("PLATFORM_OWNER_ID")
PLATFORM_OWNER: tuple[str, str] | None = (
    (PLATFORM_OWNER_EMAIL, PLATFORM_OWNER_PASSWORD)
    if PLATFORM_OWNER_EMAIL and PLATFORM_OWNER_PASSWORD else None
)

# --- Ephemeral test users ---
# Passwords for test-only accounts are generated per session by default so no
# secret ever lands in the repo. Callers may override via TEST_LIMITED_PASSWORD
# in dev to keep a stable value across debug runs.
CUSTOMER_DEMO_EMAIL: str = _optional("TEST_CUSTOMER_DEMO_EMAIL", "cliente.demo@infissiexpress.com") or "cliente.demo@infissiexpress.com"
CUSTOMER_DEMO_PASSWORD: str | None = _optional("TEST_CUSTOMER_DEMO_PASSWORD")

LIMITED_EMAIL: str = _optional("TEST_LIMITED_EMAIL", "test_limited@example.com") or "test_limited@example.com"
LIMITED_PASS: str = _optional("TEST_LIMITED_PASSWORD") or ("T!" + _secrets.token_urlsafe(12))

# Generic ephemeral password helper for tests that spin up throwaway users.
def ephemeral_password(prefix: str = "T") -> str:
    return f"{prefix}!" + _secrets.token_urlsafe(12)


__all__ = [
    "ADMIN_EMAIL", "ADMIN_PASSWORD",
    "ADMIN_PWD", "ADMIN_PW", "ADMIN_PASS",
    "SUPER_ADMIN",
    "TENANT_ADMIN", "TENANT_ADMIN_EMAIL", "TENANT_ADMIN_PASSWORD",
    "PLATFORM_OWNER", "PLATFORM_OWNER_EMAIL", "PLATFORM_OWNER_PASSWORD", "PLATFORM_OWNER_ID",
    "LIMITED_EMAIL", "LIMITED_PASS",
    "ephemeral_password",
]
