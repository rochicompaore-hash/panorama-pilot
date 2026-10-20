"""Seed 3 draft quotes (discount-admin, discount-commercial, vat) for iteration 50 UI testing."""
import os, uuid, json, requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN = ("admin@infissiexpress.com", "R!J0m34OlNsVtZjvqmVC")
WINDOW = {"description": "Finestra PVC", "category": "window", "quantity": 1, "base_price": 1000.0, "internal_cost": 400.0,
          "technical_snapshot": {"total_internal_cost": 400.0}, "width_mm": 1200, "height_mm": 1400}


def login(e, p):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": e, "password": p}, timeout=20)
    r.raise_for_status()
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


def mk(s, title):
    tag = uuid.uuid4().hex[:6]
    rc = s.post(f"{BASE_URL}/api/customers", json={"customer_type": "private", "first_name": "TEST_UI", "last_name": f"It50{tag}",
               "email": f"it50_{tag}@x.it", "phone": "3331234567", "tax_code": "RSSMRA80A01H501U",
               "address": {"street": "Via Roma 1", "city": "Milano", "zip_code": "20100", "province": "MI"}}, timeout=20)
    rc.raise_for_status()
    rq = s.post(f"{BASE_URL}/api/quotes", json={"customer_id": rc.json()["id"], "title": f"TEST_{title} {tag}",
               "site_address": {"street": "Via Cantiere 9", "city": "Monza", "zip_code": "20900", "province": "MB"}}, timeout=20)
    rq.raise_for_status()
    qid = rq.json()["id"]
    s.post(f"{BASE_URL}/api/quotes/{qid}/lines", json=WINDOW, timeout=20).raise_for_status()
    return qid


if __name__ == "__main__":
    a = login(*ADMIN)
    print(json.dumps({"disc_admin": mk(a, "DISC_ADMIN"), "disc_comm": mk(a, "DISC_COMM"), "vat": mk(a, "VAT")}))
