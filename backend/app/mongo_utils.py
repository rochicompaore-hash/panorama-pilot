"""Mongo helpers: serialize/deserialize documents with UUID _id and ISO dates."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, Optional


def to_mongo(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert model dump (by_alias=True) to a Mongo-storable dict.
    Datetimes are converted to ISO strings.
    """
    out = {}
    for k, v in doc.items():
        out[k] = _serialize(v)
    return out


def _serialize(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _serialize(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_serialize(x) for x in v]
    return v


def from_mongo(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if doc is None:
        return None
    d = dict(doc)
    # map _id -> id for pydantic alias handling
    if "_id" in d:
        d.setdefault("id", d["_id"])
        d.pop("_id", None)
    return d
