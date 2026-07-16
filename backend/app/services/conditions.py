"""Declarative condition engine for price rules.

Rules apply based on `conditions` (list of match specs) against a `product_config`
context. This is deliberately separated from the numeric formula engine to avoid
mixing arbitrary string equality with arithmetic.

Condition schema:
  { "field": "external_finish", "op": "eq"|"neq"|"in"|"nin"|"exists", "value": ... }

All conditions in a rule must match (AND). To express OR, use multiple rules with
different priorities.

Fields supported (dot-notation on product_config):
  external_finish, internal_finish, color_kind, film_mode, glass_type, series,
  material, hardware_line, has_roller, roller_type, motorization, screen_type,
  shutter_type, box_type, sill, opening_type, product_key, category
"""
from __future__ import annotations
from typing import Any, Dict, List


def _get(cfg: Dict[str, Any], path: str) -> Any:
    cur: Any = cfg
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def evaluate_conditions(conditions: List[Dict[str, Any]], config: Dict[str, Any]) -> bool:
    """Return True if ALL conditions match (AND)."""
    if not conditions:
        return True
    for c in conditions:
        field = c.get("field")
        op = (c.get("op") or "eq").lower()
        val = c.get("value")
        actual = _get(config, field) if field else None
        if op == "eq":
            if actual != val: return False
        elif op == "neq":
            if actual == val: return False
        elif op == "in":
            if not isinstance(val, list): return False
            if actual not in val: return False
        elif op == "nin":
            if isinstance(val, list) and actual in val: return False
        elif op == "exists":
            has = actual is not None and actual != ""
            if bool(val) != bool(has): return False
        elif op == "truthy":
            if not actual: return False
        elif op == "falsy":
            if actual: return False
        elif op == "gte":
            try:
                if float(actual or 0) < float(val or 0): return False
            except Exception:
                return False
        elif op == "lte":
            try:
                if float(actual or 0) > float(val or 0): return False
            except Exception:
                return False
        else:
            return False
    return True
