"""Pricelist Importer — parsing XLS/XLSX/CSV, mapping colonne, validazione,
preview, draft, publish, rollback.

Vincoli concordati:
  - max 25 MB
  - max 100.000 righe
  - max 30 fogli
  - preview 200 righe
  - async oltre 5.000 righe (in v1: sync ma con progresso)
  - idempotenza via hash file
  - rollback ripristina lo stato precedente del listino target
"""
from __future__ import annotations
import hashlib
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

MAX_FILE_MB = 25
MAX_ROWS = 100_000
MAX_SHEETS = 30
PREVIEW_LIMIT = 200
ASYNC_THRESHOLD = 5_000


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

def compute_file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_file(filename: str, data: bytes) -> Dict[str, Any]:
    """Parse XLSX/XLS/CSV in memoria, ritorna sheet_names + preview del primo foglio.

    Returns: {sheet_names, first_sheet, preview, total_rows_per_sheet, detected_headers, error}
    """
    size_mb = len(data) / (1024 * 1024)
    if size_mb > MAX_FILE_MB:
        return {"error": f"File troppo grande: {size_mb:.1f} MB > {MAX_FILE_MB} MB"}
    fn = filename.lower()
    try:
        if fn.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False, nrows=MAX_ROWS)
            sheets = {"CSV": df}
        elif fn.endswith((".xls", ".xlsx")):
            engine = "openpyxl" if fn.endswith(".xlsx") else None
            all_sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=str,
                                         keep_default_na=False, engine=engine)
            if len(all_sheets) > MAX_SHEETS:
                return {"error": f"Troppi fogli: {len(all_sheets)} > {MAX_SHEETS}"}
            sheets = all_sheets
        else:
            return {"error": "Formato non supportato (usa .csv/.xls/.xlsx)"}
    except Exception as e:
        return {"error": f"Errore parsing: {type(e).__name__}: {str(e)[:200]}"}

    sheet_names = list(sheets.keys())
    if not sheet_names:
        return {"error": "Nessun foglio trovato nel file"}
    total_rows: Dict[str, int] = {}
    for name, df in sheets.items():
        total_rows[name] = int(len(df))
        if total_rows[name] > MAX_ROWS:
            return {"error": f"Foglio '{name}' con {total_rows[name]} righe > {MAX_ROWS}"}

    first = sheet_names[0]
    df = sheets[first]
    return {
        "sheet_names": sheet_names,
        "first_sheet": first,
        "total_rows_per_sheet": total_rows,
        "detected_headers": [str(h) for h in df.columns.tolist()],
        "preview": df.head(PREVIEW_LIMIT).fillna("").to_dict(orient="records"),
    }


def load_sheet(data: bytes, filename: str, sheet_name: str) -> pd.DataFrame:
    fn = filename.lower()
    if fn.endswith(".csv"):
        return pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False)
    engine = "openpyxl" if fn.endswith(".xlsx") else None
    return pd.read_excel(io.BytesIO(data), sheet_name=sheet_name, dtype=str,
                          keep_default_na=False, engine=engine)


# ---------------------------------------------------------------------------
# Mapping + Normalization
# ---------------------------------------------------------------------------

def _apply_transform(value: str, transform: Optional[str]) -> Any:
    if value is None:
        return ""
    v = str(value)
    if transform == "lower":
        return v.lower()
    if transform == "upper":
        return v.upper()
    if transform == "trim":
        return v.strip()
    if transform in ("num", "float"):
        vv = v.replace(",", ".").replace(" ", "").strip()
        try:
            return float(vv) if vv else 0.0
        except ValueError:
            return None
    if transform == "int":
        vv = v.replace(",", "").replace(" ", "").strip()
        try:
            return int(float(vv)) if vv else 0
        except ValueError:
            return None
    return v.strip()


def apply_mapping(df: pd.DataFrame, mappings: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Applica il mapping colonne → target fields. Ritorna (rows, errors)."""
    errors: List[Dict[str, Any]] = []
    rows: List[Dict[str, Any]] = []
    for idx, row in df.iterrows():
        r: Dict[str, Any] = {}
        for m in mappings:
            src = m.get("source_column")
            tgt = m.get("target_field")
            raw = row.get(src, "") if src in df.columns else ""
            val = _apply_transform(str(raw), m.get("transform"))
            if (val == "" or val is None) and m.get("default_if_empty") is not None:
                val = m["default_if_empty"]
            if m.get("required") and (val is None or val == ""):
                errors.append({
                    "row_index": int(idx), "column": src, "code": "REQUIRED_MISSING",
                    "message": f"Campo obbligatorio '{tgt}' vuoto", "severity": "error"
                })
            r[tgt] = val
        rows.append(r)
    return rows, errors


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

REQUIRED_BY_ENTITY = {
    "profile": ["code"],
    "reinforcement": ["code"],
    "glazing_bead": ["code"],
    "glass_type": ["code"],
    "hardware_kit": ["code"],
    "accessory": ["code"],
    "labor": ["code"],
    "price_matrix": ["code"],
    "surcharge": ["code"],
    "min_billable": ["code"],
    "component_association": ["code"],
}


def validate_rows(entity_type: str, rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """Ritorna (errors, duplicate_count)."""
    errors: List[Dict[str, Any]] = []
    required = REQUIRED_BY_ENTITY.get(entity_type, ["code"])
    seen_codes: Dict[str, int] = {}
    duplicates = 0
    for i, r in enumerate(rows):
        for f in required:
            if not r.get(f):
                errors.append({
                    "row_index": i, "column": f, "code": "REQUIRED_MISSING",
                    "message": f"Campo '{f}' obbligatorio mancante",
                    "severity": "error"
                })
        # unit_price se presente deve essere positivo
        up = r.get("unit_price")
        if up is not None and up != "":
            try:
                v = float(up)
                if v < 0:
                    errors.append({"row_index": i, "column": "unit_price",
                                    "code": "NEGATIVE_PRICE", "message": "Prezzo negativo",
                                    "severity": "error"})
            except (TypeError, ValueError):
                errors.append({"row_index": i, "column": "unit_price",
                                "code": "INVALID_NUMBER", "message": f"Prezzo non numerico: {up}",
                                "severity": "error"})
        # duplicati per code
        code = str(r.get("code") or "").strip()
        if code:
            if code in seen_codes:
                duplicates += 1
                errors.append({"row_index": i, "column": "code", "code": "DUPLICATE_ROW",
                                "message": f"Codice '{code}' duplicato (prima occorrenza riga {seen_codes[code]})",
                                "severity": "warning"})
            else:
                seen_codes[code] = i
    return errors, duplicates


def rows_to_pricelist_entries(entity_type: str, rows: List[Dict[str, Any]],
                                 supplier_id: Optional[str] = None,
                                 profile_system_id: Optional[str] = None,
                                 default_color_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Converte righe validate in ItemPricelistEntry-compatible dicts.

    Un import genera entries per un listino: le entries riferiscono item via `ref_type` + `ref_id`
    (o solo `code` che viene poi risolto in fase di publish contro l'anagrafica).
    In v1 usiamo `code` come identificatore soft (l'articolo deve esistere).
    """
    entries = []
    ref_type_map = {
        "profile": "profile", "reinforcement": "profile", "glazing_bead": "profile",
        "glass_type": "glass", "hardware_kit": "hardware",
        "accessory": "accessory", "labor": "labor",
    }
    ref_type = ref_type_map.get(entity_type, "accessory")
    for r in rows:
        code = str(r.get("code") or "").strip()
        if not code:
            continue
        # ref_id resolution deferred to publish; for now use code as tag
        entries.append({
            "ref_type": ref_type,
            "ref_id": r.get("ref_id"),   # if precomputed
            "code": code,
            "unit_price": float(r.get("unit_price") or 0),
            "unit": r.get("unit") or "piece",
            "color_id": r.get("color_id") or default_color_id,
            "supplier_id": supplier_id,
            "profile_system_id": profile_system_id,
            "min_billable_qty": float(r.get("min_billable_qty") or 0),
            "notes": r.get("notes"),
        })
    return entries


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def build_idempotency_key(tenant_id: str, entity_type: str, file_hash: str,
                            target_pricelist_id: Optional[str]) -> str:
    payload = f"{tenant_id}|{entity_type}|{file_hash}|{target_pricelist_id or ''}"
    return hashlib.sha256(payload.encode()).hexdigest()
