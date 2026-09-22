"""Pricing gap audit — chiama il backend (source of truth) per ogni prodotto/configurazione rappresentativa."""
import os, json, sys, requests
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
s = requests.Session()
r = s.post(f"{BASE}/auth/login", json={"email": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"]}); r.raise_for_status()
s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"

prods = s.get(f"{BASE}/multi-cat/products?include_test_fixtures=true").json()
prods = prods.get("items") if isinstance(prods, dict) else prods
rows = []

def cfg(pid, body):
    return s.post(f"{BASE}/multi-cat/products/{pid}/configure", json=body).json()

def status_of(res):
    st = res.get("pricing_status")
    if st != "ok":
        return f"DISABLED_FAIL_CLOSED({st}:{(res.get('errors') or res.get('error') or res.get('reason') or '')})"[:120]
    ss = res.get("simple_snapshot") or {}
    cs = res.get("commercial_snapshot") or {}
    ts = res.get("technical_snapshot") or {}
    sale = cs.get("unit_sale_price") or ss.get("unit_price_final") or ss.get("sale_price_per_item") or cs.get("sale_price_total")
    cost = ts.get("total_internal_cost") or ss.get("purchase_cost_per_item") or ss.get("internal_production_cost_per_item") or ss.get("purchase_total_cost")
    if not sale or float(sale) <= 0:
        return "MISSING_SALE_PRICE"
    if cost is None:
        return f"MISSING_INTERNAL_COST sale={sale}"
    return f"OK sale={round(float(sale),2)} cost={round(float(cost),2)}"

for p in prods:
    pid = p["id"]; pm = p.get("pricing_model"); name = p.get("name"); cat = p.get("category_code")
    variants = []
    if pm == "FORMULA_TECHNICAL":
        for wt, n in [("WINDOW", 1), ("WINDOW", 2), ("WINDOW", 3), ("WINDOW", 4), ("DOOR_WINDOW", 1), ("DOOR_WINDOW", 2), ("SLIDING_DOOR_WINDOW", 2), ("VASISTAS_ONLY", 1)]:
            for glass in ["DOUBLE_STANDARD", "TRIPLE_SATIN"]:
                for col in ["WHITE_MASS", "003", "100", "019"]:
                    if glass != "DOUBLE_STANDARD" and col != "WHITE_MASS":
                        continue
                    variants.append((f"{wt} {n} ante {glass} col={col}", {"technical_inputs": {"window_type": wt, "number_of_sashes": n, "width_mm": 1200, "height_mm": 1400 if wt == "WINDOW" else 2200,
                                                                                               "glass_type": glass, "color_internal": col, "color_external": col, "quantity": 1}}))
    elif pm == "GRID":
        for fam, col in [("BIANCO_MASSA", "003"), ("STANDARD", "100"), ("NON_STANDARD", "019")]:
            for depth in [163, 326, 489, 652]:
                for ceil in ["SI", "NO"]:
                    variants.append((f"grid fam={fam} col={col} 1200x250 depth={depth} cielino={ceil}", {"simple_inputs": {"width_mm": 1200, "height_mm": 250, "quantity": 1, "options": {"depth_mm": depth, "ceiling_liner": ceil, "color_code": col}}}))
    elif pm in ("AREA", "AREA_PURCHASE_MULTIPLIER"):
        pc = s.get(f"{BASE}/multi-cat/products/{pid}").json().get("pricing_config") or {}
        table = pc.get("purchase_cost_table_per_m2") or {}
        dom = pc.get("color_domain")
        cmap = pc.get("color_map") or {}
        keys = list(table.keys()) or [None]
        for k in keys:
            if dom == "ZANZARIERE":
                code = {"BASE": "ZC_BASE_DEFAULT", "WOOD_EFFECT": "ZC_WOOD_DEFAULT", "MARBLE": "ZC_MARBLE_DEFAULT", "SPECIAL": "ZC_SPECIAL_DEFAULT"}.get(k, k)
            elif dom == "INTERNAL_MAP":
                code = next((c for c, cat in cmap.items() if cat == k), k)
            else:
                code = k
            for orient in ([False, True] if pm == "AREA_PURCHASE_MULTIPLIER" else [False]):
                variants.append((f"{k or 'unit'} color={code}{' orientabile' if orient else ''} 1200x1400", {"simple_inputs": {"width_mm": 1200, "height_mm": 1400, "quantity": 1, "options": {"color_code": code, "color_category": k, "orientable": orient}}}))
    else:
        variants.append(("default", {"simple_inputs": {"width_mm": 1000, "height_mm": 1000, "linear_meters": 2, "quantity": 1}}))
    for label, body in variants:
        try:
            res = cfg(pid, body)
            st = status_of(res)
        except Exception as e:
            st = f"ERROR {e}"
        rows.append((cat, name, pm, p.get("classification_status"), label, st))

for r_ in rows:
    print(" | ".join(str(x) for x in r_))
json.dump(rows, open("/app/memory/pricing_audit_rows.json", "w"), indent=0)
