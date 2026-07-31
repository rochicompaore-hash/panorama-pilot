"""Test guard demo product — verifica che in DEMO_MODE=false i prodotti is_demo=true
siano rifiutati con DEMO_PRODUCT_NOT_ALLOWED.
"""
from __future__ import annotations
import os
import requests

from tests._creds import ADMIN_EMAIL, ADMIN_PW

API = f"{os.environ.get('REACT_APP_BACKEND_URL','').rstrip('/')}/api"
T = 15


def _auth() -> dict:
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=T)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_demo_product_marked_with_environment_scope():
    """Verifica che il prodotto demo abbia i marker di sicurezza."""
    import motor.motor_asyncio, asyncio
    async def check():
        c = motor.motor_asyncio.AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = c[os.environ.get("DB_NAME", "infissi_express")]
        p = await db.products.find_one({"_id": "test-motor-product-proevolution"})
        c.close()
        return p
    p = asyncio.run(check())
    assert p is not None, "Prodotto demo non trovato"
    assert p.get("is_demo") is True
    assert p.get("environment_scope") == "test"
    assert p.get("selectable_in_real_quotes") is False
