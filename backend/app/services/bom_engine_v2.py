"""BOM Engine v2 — Wrapper attorno a `parametric_engine.resolve_bom` che aggiunge:

- Lookup code/description/notes per ogni componente (profili, vetri, ferramenta, accessori)
- Origine del listino applicato per prezzo/costo (id, name, version)
- Aggregazione totali per tipologia (profili, vetri, ferramenta, lavorazioni, altro)
- Contesto formule esteso (variabili disponibili)
- Snapshot canonico dei parametri di input per audit/riproducibilità

Non modifica `resolve_bom` per non rompere consumatori esistenti; espone
`resolve_bom_full` come funzione async coordinatrice.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.db import get_db
from app.services.formula import money
from app.services.parametric_engine import resolve_bom


# ---------------------------------------------------------------------------
# Lookup anagrafiche (code, description)
# ---------------------------------------------------------------------------

_ANAGRAPH_COLLECTIONS = {
    "profile": "profiles",
    "glass": "glass_types",
    "hardware": "hardware_kits",
    "accessory": "accessories",
    # seal/screw/consumable/packaging/labor/machine_time/outsourced_process → nessuna anagrafica dedicata
}


async def _preload_anagraph(tenant_id: str, refs: List[Tuple[str, str]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Preload anagraphs in bulk to avoid N+1. Returns {(ref_type, ref_id): doc}."""
    db = get_db()
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    by_col: Dict[str, List[str]] = {}
    for rt, rid in refs:
        col = _ANAGRAPH_COLLECTIONS.get(rt)
        if col and rid:
            by_col.setdefault(col, []).append(rid)
    for col, ids in by_col.items():
        cursor = db[col].find({"_id": {"$in": list(set(ids))}, "tenant_id": tenant_id, "deleted_at": None})
        docs = await cursor.to_list(len(ids) * 2)
        # inverse map — need to know ref_type for this col
        rt = next((k for k, v in _ANAGRAPH_COLLECTIONS.items() if v == col), None)
        for d in docs:
            if rt:
                out[(rt, d.get("_id"))] = d
    return out


async def _build_lookups_with_origin(
    tenant_id: str,
    sell_pricelist_id: Optional[str],
    cost_pricelist_id: Optional[str],
):
    """Come `pricing_modes._build_lookups` ma cattura l'origine (id, name, version)
    per ogni componente in un dict `origins` accessibile dopo il calcolo.

    Returns:
        (sell_lookup_fn, cost_lookup_fn, sell_meta, cost_meta, origins)
        Dove `origins[(ref_type, ref_id, color_id)] = {sell:{...}, cost:{...}}`
    """
    db = get_db()
    sell_pl: Optional[Dict[str, Any]] = None
    cost_pl: Optional[Dict[str, Any]] = None
    if sell_pricelist_id:
        sell_pl = await db.item_pricelists.find_one({
            "_id": sell_pricelist_id, "tenant_id": tenant_id, "deleted_at": None,
        })
    if cost_pricelist_id:
        cost_pl = await db.item_pricelists.find_one({
            "_id": cost_pricelist_id, "tenant_id": tenant_id, "deleted_at": None,
        })

    sell_entries: List[Dict[str, Any]] = (sell_pl or {}).get("entries") or []
    cost_entries: List[Dict[str, Any]] = (cost_pl or {}).get("entries") or []
    origins: Dict[Tuple[str, str, Optional[str]], Dict[str, Any]] = {}

    def _pick(entries: List[Dict[str, Any]], rt: str, rid: str, cid: Optional[str]):
        candidates = [e for e in entries
                      if e.get("ref_type") == rt and e.get("ref_id") == rid]
        if not candidates:
            return None
        with_color = [e for e in candidates if e.get("color_id") == cid]
        if with_color:
            return with_color[0]
        no_color = [e for e in candidates if not e.get("color_id")]
        if no_color:
            return no_color[0]
        return candidates[0]

    def make_lookup(entries: List[Dict[str, Any]], pl_doc: Optional[Dict[str, Any]], kind: str):
        if not entries:
            return None

        def _fn(rt, rid, cid, unit):
            entry = _pick(entries, rt, rid, cid)
            if not entry:
                return 0.0
            price = float(entry.get("unit_price") or 0)
            key = (rt, rid, cid)
            origins.setdefault(key, {})[kind] = {
                "pricelist_id": (pl_doc or {}).get("_id"),
                "pricelist_code": (pl_doc or {}).get("code"),
                "pricelist_name": (pl_doc or {}).get("name"),
                "pricelist_version": (pl_doc or {}).get("version"),
                "pricelist_status": (pl_doc or {}).get("ipl_status"),
                "unit": entry.get("unit"),
                "unit_price": price,
                "color_id": entry.get("color_id"),
                "supplier_id": entry.get("supplier_id"),
                "profile_system_id": entry.get("profile_system_id"),
            }
            return price

        return _fn

    sell_fn = make_lookup(sell_entries, sell_pl, "sell")
    cost_fn = make_lookup(cost_entries, cost_pl, "cost")

    sell_meta = {
        "pricelist_id": (sell_pl or {}).get("_id"),
        "pricelist_name": (sell_pl or {}).get("name"),
        "pricelist_version": (sell_pl or {}).get("version"),
    } if sell_pl else None
    cost_meta = {
        "pricelist_id": (cost_pl or {}).get("_id"),
        "pricelist_name": (cost_pl or {}).get("name"),
        "pricelist_version": (cost_pl or {}).get("version"),
    } if cost_pl else None

    return sell_fn, cost_fn, sell_meta, cost_meta, origins


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def resolve_bom_full(
    *,
    tenant_id: str,
    bom_template_id: str,
    params: Dict[str, Any],
    sell_pricelist_id: Optional[str] = None,
    cost_pricelist_id: Optional[str] = None,
    include_costs: bool = True,
) -> Dict[str, Any]:
    """Risolve una BOM con output esteso (codici, descrizioni, origine listino,
    aggregazioni, snapshot).

    Args:
        tenant_id: tenant scope
        bom_template_id: id del BomTemplate
        params: {width_mm, height_mm, nr_ante, nr_traversi, nr_montanti, nr_fissi,
                 color_category_id, color_id, glass_type_id, hardware_kit_id}
        sell_pricelist_id: listino prezzi vendita (opzionale)
        cost_pricelist_id: listino costo (opzionale, richiede include_costs=True)
        include_costs: se False, unit_cost e materials_cost non vengono valorizzati

    Returns:
        dict con: components (arricchiti), materials_cost, materials_price,
        totals_by_type, snapshot_hash, snapshot, warnings, blocking_errors,
        errors (formattati per UI).
    """
    db = get_db()
    bom = await db.bom_templates.find_one({
        "_id": bom_template_id, "tenant_id": tenant_id, "deleted_at": None,
    })
    if not bom:
        return {
            "errors": ["BOM template non trovato o disattivato"],
            "components": [], "materials_cost": 0, "materials_price": 0,
            "totals_by_type": {}, "warnings": [], "blocking_errors": [],
        }
    ps = await db.profile_systems.find_one({
        "_id": bom.get("profile_system_id"), "tenant_id": tenant_id, "deleted_at": None,
    })
    if not ps:
        return {
            "errors": ["Sistema profilo del BOM non trovato"],
            "components": [], "materials_cost": 0, "materials_price": 0,
            "totals_by_type": {}, "warnings": [], "blocking_errors": [],
        }

    # Costruisci lookup con cattura origine
    sell_fn, cost_fn, sell_meta, cost_meta, origins = await _build_lookups_with_origin(
        tenant_id, sell_pricelist_id, cost_pricelist_id if include_costs else None,
    )

    result = resolve_bom(
        bom_template=bom, profile_system=ps, params=params,
        lookup_price=sell_fn, lookup_cost=cost_fn,
    )

    # Preload anagraphs (code, description) per tutti i ref_id
    refs = [(c.get("component_type"), c.get("ref_id"))
            for c in result.get("components") or []
            if c.get("ref_id")]
    anagraphs = await _preload_anagraph(tenant_id, refs)

    # Arricchisce ogni componente con code, description, pricelist_origin
    for comp in result.get("components") or []:
        rt = comp.get("component_type")
        rid = comp.get("ref_id")
        cid = comp.get("color_id")
        doc = anagraphs.get((rt, rid)) if rid else None
        comp["code"] = (doc or {}).get("code")
        comp["description"] = (
            comp.get("description_override")
            or (doc or {}).get("name")
            or (doc or {}).get("code")
            or "-"
        )
        origin = origins.get((rt, rid, cid), {}) if rid else {}
        comp["pricelist_origin_sell"] = origin.get("sell")
        comp["pricelist_origin_cost"] = origin.get("cost")

    # Aggregazione totali per tipologia
    totals_by_type: Dict[str, Dict[str, float]] = {}
    for comp in result.get("components") or []:
        t = comp.get("component_type") or "other"
        agg = totals_by_type.setdefault(t, {"count": 0, "cost": 0.0, "price": 0.0})
        agg["count"] += 1
        agg["cost"] += float(comp.get("line_cost") or 0)
        agg["price"] += float(comp.get("line_price") or 0)
    # arrotonda
    for t, agg in totals_by_type.items():
        agg["cost"] = float(money(Decimal(str(agg["cost"]))))
        agg["price"] = float(money(Decimal(str(agg["price"]))))

    # Snapshot canonico (input) per audit
    snapshot = {
        "bom_template_id": bom_template_id,
        "bom_version": bom.get("version"),
        "profile_system_id": ps.get("_id"),
        "profile_system_version": ps.get("version"),
        "params": params,
        "sell_pricelist_id": sell_pricelist_id,
        "cost_pricelist_id": cost_pricelist_id,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    snap_j = json.dumps(snapshot, sort_keys=True, default=str, separators=(",", ":"))
    snapshot_hash = hashlib.sha256(snap_j.encode("utf-8")).hexdigest()

    # Formatta errori bloccanti in lista di stringhe (per UI concisa)
    errors_str = [
        f"[{e.get('code')}] {e.get('role') or e.get('field')} · {e.get('message')}"
        for e in (result.get("blocking_errors") or [])
    ]

    return {
        "bom_template_id": bom_template_id,
        "bom_template_code": bom.get("code"),
        "bom_template_name": bom.get("name"),
        "bom_version": bom.get("version"),
        "profile_system_id": ps.get("_id"),
        "profile_system_code": ps.get("code"),
        "profile_system_name": ps.get("name"),
        "sell_pricelist": sell_meta,
        "cost_pricelist": cost_meta if include_costs else None,
        "components": result.get("components") or [],
        "materials_cost": result.get("materials_cost", 0.0) if include_costs else 0.0,
        "materials_price": result.get("materials_price", 0.0),
        "totals_by_type": totals_by_type,
        "warnings": result.get("warnings") or [],
        "blocking_errors": result.get("blocking_errors") or [],
        "errors": errors_str,
        "snapshot": snapshot,
        "snapshot_hash": snapshot_hash,
    }
