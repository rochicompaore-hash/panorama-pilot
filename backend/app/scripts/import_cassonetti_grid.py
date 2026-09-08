"""Importer autoritativo griglia CASSONETTI da ``listino_completo_con_costi.xlsx``.

SOURCE OF TRUTH = workbook (SALE GRID + COST GRID). Nessuna formula/multiplier a runtime.

    python -m app.scripts.import_cassonetti_grid --workbook backend/data/listino_completo_con_costi.xlsx
    python -m app.scripts.import_cassonetti_grid --apply-db        # upsert pricing_config su tutti i tenant

Output: ``app/data/cassonetti_grid_2026.json`` rigenerato + (opzionale) update DB.
"""
from __future__ import annotations

import argparse, asyncio, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

GRID_VERSION = "cassonetti_grid_2026_09_workbook"
DEFAULT_WORKBOOK = Path(__file__).resolve().parents[2] / "data" / "listino_completo_con_costi.xlsx"
OUT_JSON = Path(__file__).resolve().parents[1] / "data" / "cassonetti_grid_2026.json"

FAMILY_SHEETS = {
    "BIANCO_MASSA": ("Bianco massa", "Costo prod. Bianco"),
    "STANDARD": ("Pellicolato standard", "Costo prod. Std"),
    "NON_STANDARD": ("Pellicolato no-std", "Costo prod. No-std"),
}
COLUMN_KEYS = ["163_c", "163_nc", "326_c", "326_nc", "489_c", "489_nc", "652_c", "652_nc"]
WIDTHS = list(range(500, 3501, 100))          # 31
HEIGHTS = [250, 350, 450, 550, 650, 750]      # 6
DEPTHS = [163, 326, 489, 652]


def _read_sheet(ws) -> dict:
    out: dict = {c: {} for c in COLUMN_KEYS}
    for row in ws.iter_rows(min_row=5, values_only=True):
        if not isinstance(row[0], (int, float)) or not isinstance(row[1], (int, float)):
            continue
        w, h = int(row[0]), int(row[1])
        for i, col in enumerate(COLUMN_KEYS):
            v = row[2 + i]
            if v is None:
                continue
            out[col][f"{w}x{h}"] = round(float(v), 2)
    return out


def build_grid(workbook_path: Path) -> dict:
    import openpyxl
    wb = openpyxl.load_workbook(workbook_path, data_only=True)
    grid: dict = {}
    problems: list = []
    for fam, (sale_sheet, cost_sheet) in FAMILY_SHEETS.items():
        sales = _read_sheet(wb[sale_sheet])
        costs = _read_sheet(wb[cost_sheet])
        grid[fam] = {}
        for col in COLUMN_KEYS:
            grid[fam][col] = {}
            for w in WIDTHS:
                for h in HEIGHTS:
                    k = f"{w}x{h}"
                    s, c = sales[col].get(k), costs[col].get(k)
                    if s is None or c is None:
                        problems.append(f"{fam}/{col}/{k}: missing sale={s} cost={c}")
                        continue
                    if s <= 0 or c <= 0 or s <= c:
                        problems.append(f"{fam}/{col}/{k}: invalid sale={s} cost={c}")
                    grid[fam][col][k] = {"sale": s, "internal": c}
    return {
        "version": GRID_VERSION,
        "source_file": workbook_path.name,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "depths_mm": DEPTHS,
        "ceiling_liner_options": ["SI", "NO"],
        "widths_mm": WIDTHS,
        "heights_mm": HEIGHTS,
        "finish_families": list(FAMILY_SHEETS.keys()),
        "grid": grid,
        "_problems": problems,
    }


async def apply_db(grid_data: dict) -> int:
    from app.db import get_db, close_db
    db = get_db()
    cfg_patch = {
        "pricing_config.grid_version": grid_data["version"],
        "pricing_config.source_file": grid_data["source_file"],
        "pricing_config.imported_at": grid_data["imported_at"],
        "pricing_config.depths_mm": grid_data["depths_mm"],
        "pricing_config.ceiling_liner_options": grid_data["ceiling_liner_options"],
        "pricing_config.widths_mm": grid_data["widths_mm"],
        "pricing_config.heights_mm": grid_data["heights_mm"],
        "pricing_config.finish_families": grid_data["finish_families"],
        "pricing_config.grid": grid_data["grid"],
        "pricing_config.color_domain": "PVC",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    r = await db.products.update_many(
        {"key": "CASSONETTO_STD", "pricing_model": "GRID", "deleted_at": None},
        {"$set": cfg_patch, "$inc": {"version": 1}},
    )
    await close_db()
    return int(r.modified_count)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workbook", default=str(DEFAULT_WORKBOOK))
    p.add_argument("--apply-db", action="store_true")
    args = p.parse_args()
    data = build_grid(Path(args.workbook))
    problems = data.pop("_problems")
    n_cells = sum(len(cells) for fam in data["grid"].values() for cells in fam.values())
    print(f"cells={n_cells} (expected 4464) problems={len(problems)}")
    for pr in problems[:20]:
        print("  !", pr)
    if problems or n_cells != 4464:
        print("ABORT: workbook incompleto/invalid — nessun file scritto.")
        sys.exit(2)
    OUT_JSON.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f"written {OUT_JSON}")
    if args.apply_db:
        n = asyncio.run(apply_db(data))
        print(f"db products updated: {n}")


if __name__ == "__main__":
    main()
