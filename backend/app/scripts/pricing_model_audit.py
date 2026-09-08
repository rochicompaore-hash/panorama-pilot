"""PRICING MODEL AUDIT — tutti i prodotti attivi ``new_quote_enabled=true`` (PO msg 401 §31).

    python -m app.scripts.pricing_model_audit [--tenant-id ID] [--markdown out.md]

Per ogni prodotto: pricing_model, cost_source, sale_rule, multiplier, minimum, color pricing,
installation resolver, internal cost / sale price disponibili, status.
"""
from __future__ import annotations

import argparse, asyncio, os, sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.models_multi_category import ConfigureRequest, SimplePricingInputs
from app.services.multi_category_pricing import resolve_and_compute
from app.services.service_resolver import resolve_install_code_for_line


def _probe_inputs(prod: dict) -> ConfigureRequest:
    m = prod.get("pricing_model")
    cfg = prod.get("pricing_config") or {}
    if m == "FORMULA_TECHNICAL":
        return ConfigureRequest(product_id=prod["_id"], technical_inputs={
            "product_key": prod["key"], "window_type": "WINDOW", "number_of_sashes": 1,
            "width_mm": 1200, "height_mm": 1400, "quantity": 1})
    opts: dict = {}
    if m == "GRID":
        opts = {"color_code": "003", "depth_mm": 163, "ceiling_liner": "SI"}
        return ConfigureRequest(product_id=prod["_id"], simple_inputs=SimplePricingInputs(width_mm=500, height_mm=250, quantity=1, options=opts))
    if m == "AREA_PURCHASE_MULTIPLIER":
        opts = {"color_code": next(iter((cfg.get("color_map") or {"RAL": 1}).keys())), "orientable": False}
    elif m == "AREA":
        dom = cfg.get("color_domain")
        if dom == "ZANZARIERE":
            opts = {"color_code": "ZC_BASE_DEFAULT"}
        elif dom == "INTERNAL_MAP":
            opts = {"color_code": next(iter((cfg.get("color_map") or {}).keys()), None)}
        elif cfg.get("purchase_cost_table_per_m2") or cfg.get("sale_price_table_per_m2"):
            opts = {"color_code": "003"}
    return ConfigureRequest(product_id=prod["_id"], simple_inputs=SimplePricingInputs(width_mm=1200, height_mm=1400, linear_meters=1.0, quantity=1, options=opts))


def _cost_from(resp) -> float | None:
    ts = resp.technical_snapshot or {}
    ss = resp.simple_snapshot or {}
    for src in (ts.get("total_internal_cost"), ss.get("purchase_total_cost"), ss.get("purchase_cost_per_item"), ss.get("internal_production_cost_per_item")):
        if src is not None:
            return float(src)
    return None


def _sale_from(resp) -> float | None:
    cs = resp.commercial_snapshot or {}
    ss = resp.simple_snapshot or {}
    for src in (ss.get("unit_price_final"), ss.get("sale_price_per_item"), cs.get("final_unit_price"), cs.get("unit_sale_price")):
        if src is not None:
            return float(src)
    return None


async def audit(tenant_id: str) -> list[dict]:
    from app.db import get_db
    db = get_db()
    rows = []
    q = {"tenant_id": tenant_id, "deleted_at": None, "active": True, "new_quote_enabled": True}
    async for prod in db.products.find(q).sort([("category_code", 1), ("key", 1)]):
        cfg = prod.get("pricing_config") or {}
        m = prod.get("pricing_model")
        cat = await db.product_categories.find_one({"_id": prod.get("category_id")}) if prod.get("category_id") else None
        resp = await resolve_and_compute(prod, cat or {}, _probe_inputs(prod), tenant_id)
        cost, sale = _cost_from(resp), _sale_from(resp)
        install = resolve_install_code_for_line({"category_code": prod.get("category_code"), "pricing_model": m, "configuration_snapshot": {"number_of_sashes": 1}})
        if m == "FORMULA_TECHNICAL":
            cost_source, sale_rule = "technical BOM (pricing_v3)", "technical_cost × package multiplier"
            mult = (resp.commercial_snapshot or {}).get("multiplier")
        elif m == "GRID":
            cost_source, sale_rule, mult = "grid cell internal (workbook)", "grid cell sale (workbook lookup)", None
        elif cfg.get("purchase_cost_table_per_m2"):
            cost_source, sale_rule, mult = "purchase €/m² per color category", "purchase × multiplier", cfg.get("commercial_multiplier")
        elif cfg.get("sale_price_table_per_m2"):
            cost_source, sale_rule, mult = "NONE", "sale €/m² table", None
        else:
            cost_source = "product.internal_reference_price" if cfg.get("internal_reference_price") else "NONE"
            sale_rule, mult = f"{m} unit_sale/fixed", None
        if resp.pricing_status != "ok":
            status = "FAIL_INVALID_PRICING_MODEL" if resp.pricing_status in ("missing_pricing_model", "legacy_disabled") else f"FAIL_UNTESTED:{resp.pricing_status}:{';'.join(resp.blocking_errors or [])}"
        elif sale is None or sale <= 0:
            status = "FAIL_MISSING_SALE_PRICE"
        elif prod.get("is_test_fixture"):
            status = "PASS_TEST_FIXTURE_ONLY" if cost is not None else "PASS_TEST_FIXTURE_ONLY (no cost — escluso dal catalogo commerciale)"
        elif cost is None or cost <= 0:
            status = "FAIL_MISSING_COST"
        else:
            status = "PASS"
        rows.append({
            "product_id": prod["_id"], "product_name": prod.get("name"), "key": prod.get("key"),
            "category": prod.get("category_code"), "pricing_model": m, "cost_source": cost_source,
            "sale_rule": sale_rule, "multiplier": mult,
            "minimum": prod.get("minimum_billable_quantity") or cfg.get("minimum_billable_area_m2"),
            "color_pricing": cfg.get("color_domain") or ("grid family" if m == "GRID" else "-"),
            "installation_resolver": install, "internal_cost_available": cost is not None and cost > 0,
            "sale_price_available": sale is not None and sale > 0, "probe_sale": sale, "probe_cost": cost,
            "is_test_fixture": bool(prod.get("is_test_fixture")), "status": status,
        })
    return rows


def to_markdown(rows: list[dict]) -> str:
    cols = ["product_id", "product_name", "category", "pricing_model", "cost_source", "sale_rule", "multiplier", "minimum",
            "color_pricing", "installation_resolver", "internal_cost_available", "sale_price_available", "status"]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(str(r.get(c)) for c in cols) + " |")
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tenant-id", default="5e353147-2416-4ef7-aa3f-3e0007435c42")
    p.add_argument("--markdown")
    args = p.parse_args()
    rows = asyncio.run(audit(args.tenant_id))
    md = to_markdown(rows)
    print(md)
    fails = [r for r in rows if r["status"].startswith("FAIL")]
    print(f"\nTOTAL={len(rows)} PASS={len(rows) - len(fails)} FAIL={len(fails)}")
    if args.markdown:
        Path(args.markdown).write_text(md + f"\n\nTOTAL={len(rows)} PASS={len(rows) - len(fails)} FAIL={len(fails)}\n")


if __name__ == "__main__":
    main()
