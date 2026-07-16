"""Shared pytest fixtures/config. Loads env from backend/.env and frontend/.env."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load backend env first (MONGO_URL, DB_NAME, JWT_SECRET, ...)
_backend_env = Path(__file__).parent.parent / ".env"
if _backend_env.exists():
    load_dotenv(_backend_env, override=False)

# Then frontend env — for REACT_APP_BACKEND_URL used by tests
_frontend_env = Path(__file__).parent.parent.parent / "frontend" / ".env"
if _frontend_env.exists():
    load_dotenv(_frontend_env, override=False)
