"""Simple Services router — Enerhia Operating Core (Milestone 2.14).

Servizi semplici (posa, smontaggi, motorizzazioni, coprifili, imbotti, ...)
con **dual pricing**:

- ``internal_reference_price`` : valore economico interno per calcolare lo
  spazio di sconto disponibile. **Visibile solo agli utenti con permesso
  ``pricing_admin.manage`` o ``pricelists.manage_internal_ref``.**
- ``customer_sale_price`` : prezzo standard proposto al cliente. **È il valore
  che appare nel preventivo e nel PDF.**

Il commerciale vede sempre ``customer_sale_price``. NON vede
``internal_reference_price``.

Discount guard: se in una futura quote line si tenta di portare il prezzo
sotto ``internal_reference_price``, il backend richiede il permesso
``pricing.override_below_reference`` + audit trail (``AUTHORIZED_PRICE_OVERRIDE``).
Qui esponiamo il servizio con tutti i campi filtrati; il gate finale sarà
applicato quando si collegherà il preventivo commerciale al motore.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import get_db
from app.deps import require_permission, get_permission_keys_for_user
from app.services.concurrency import user_has_permission


router = APIRouter(prefix="/simple-services", tags=["Simple Services"])


PRICING_UNITS = {
    "PER_ITEM",           # a serramento / a pezzo
    "PER_INTERVENTION",   # a intervento
    "PER_LINEAR_METER",   # €/ml
    "PER_SQUARE_METER",   # €/m²
    "PER_HOUR",           # ora
    "FIXED",              # forfait unico
    "VARIABLE",           # calcolato da regola (VARIABLE_LOGISTIC_SERVICE)
}

STATUSES = {"ACTIVE", "DRAFT", "PRICING_RULE_TO_DEFINE", "ARCHIVED"}


class SimpleServiceCreate(BaseModel):
    code: Optional[str] = None                  # slug tecnico opzionale
    name: str = Field(..., min_length=2, max_length=200)
    category: str = Field(..., min_length=1, max_length=80)  # POSA / SMONTAGGIO / LOGISTICA / MOTORIZZAZIONE / CASSONETTO / ACCESSORIO
    description: Optional[str] = ""
    pricing_unit: str = "PER_ITEM"
    internal_reference_price: Optional[float] = None
    customer_sale_price: Optional[float] = None
    vat_pct: float = 22.0
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    status: str = "ACTIVE"
    quantity_rule: Optional[str] = None
    suggested_for_recipes: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class SimpleServiceUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    pricing_unit: Optional[str] = None
    internal_reference_price: Optional[float] = None
    customer_sale_price: Optional[float] = None
    vat_pct: Optional[float] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    status: Optional[str] = None
    quantity_rule: Optional[str] = None
    suggested_for_recipes: Optional[List[str]] = None
    notes: Optional[str] = None


# ==============================================================
# SEED — Listino Enerhia posa/servizi (ufficiale)
# ==============================================================
# Ogni riga: (code, name, category, internal_reference_price, customer_sale_price,
#            pricing_unit, notes, suggested_for_recipes)
SEED_ENERHIA_SERVICES = [
    # --- MONTAGGI ---
    ("INSTALL_WINDOW_1_2_SASH", "Montaggio infissi 1/2 ante", "POSA",
        130, 150, "PER_ITEM",
        "Comprensivo di materiali di consumo (viti, silicone, schiuma).",
        ["WINDOW_1_SASH", "WINDOW_2_SASH"]),
    ("INSTALL_WINDOW_3_SASH", "Montaggio infissi 3 ante", "POSA",
        195, 215, "PER_ITEM", "Comprensivo di materiali di consumo.", ["WINDOW_3_SASH"]),
    ("INSTALL_WINDOW_4_SASH", "Montaggio infissi 4 ante", "POSA",
        260, 280, "PER_ITEM", "Comprensivo di materiali di consumo.", ["WINDOW_4_SASH"]),
    ("INSTALL_WINDOW_UNDERLIGHT", "Montaggio infisso con sottoluce", "POSA",
        200, 220, "PER_ITEM", "Comprensivo di materiali di consumo.", []),
    ("INSTALL_WINDOW_UNDERLIGHT_DOUBLE", "Montaggio infisso con sottoluce doppio", "POSA",
        500, 600, "PER_ITEM", "Comprensivo di materiali di consumo.", []),
    ("INSTALL_VASISTAS", "Montaggio infisso vasistas", "POSA",
        200, 250, "PER_ITEM", "Comprensivo di materiali di consumo.", ["VASISTAS_ONLY_1_SASH"]),
    ("INSTALL_FIXED_WINDOW", "Montaggio infisso fisso", "POSA",
        500, 650, "PER_ITEM", "Comprensivo di materiali di consumo.", []),
    ("INSTALL_SLIDING", "Montaggio infisso scorrevole", "POSA",
        500, 650, "PER_ITEM", "Comprensivo di materiali di consumo.",
        ["SLIDING_DOOR_WINDOW"]),
    ("INSTALL_PVC_ENTRY_DOOR", "Montaggio portone ingresso PVC", "POSA",
        250, 320, "PER_ITEM", "Comprensivo di materiali di consumo.", []),
    ("INSTALL_INTERIOR_DOOR_HINGED", "Montaggio porte interne battenti", "POSA",
        80, 110, "PER_ITEM", "Comprensivo di materiali di consumo.", []),
    ("INSTALL_INTERIOR_DOOR_SLIDING", "Montaggio porte interne scorrevoli", "POSA",
        100, 130, "PER_ITEM", "Comprensivo di materiali di consumo.", []),
    ("INSTALL_ARMORED_DOOR", "Montaggio portone blindato", "POSA",
        300, 450, "PER_ITEM", "Comprensivo di materiali di consumo.", []),
    ("INSTALL_ROLLER_BOX_SINGLE", "Montaggio cassonetto singolo", "POSA",
        70, 90, "PER_ITEM", "Comprensivo di materiali di consumo.", []),
    ("INSTALL_ROLLER_BOX_DOUBLE", "Montaggio cassonetto doppio", "POSA",
        140, 160, "PER_ITEM", "Comprensivo di materiali di consumo.", []),
    ("INSTALL_METAL_COVER", "Montaggio lamiere", "POSA",
        15, 30, "PER_ITEM", "", []),
    ("INSTALL_SHUTTER_1_2_SASH", "Montaggio persiana 1/2 ante", "POSA",
        130, 150, "PER_ITEM", "Comprensivo di materiali di consumo.", []),
    ("INSTALL_ROLLER_KIT", "Montaggio kit tapparelle", "POSA",
        100, 120, "PER_ITEM", "Comprensivo di materiali di consumo.", []),
    ("INSTALL_ROLLER_KIT_PROTRUDING", "Montaggio kit tapparelle con apparecchio a sporgere", "POSA",
        130, 150, "PER_ITEM", "Comprensivo di materiali di consumo.", []),
    ("INSTALL_MOTOR", "Motorizzazione", "MOTORIZZAZIONE",
        80, 110, "PER_ITEM", "", []),
    ("INSTALL_MOTOR_VASISTAS", "Motorizzazione vasistas", "MOTORIZZAZIONE",
        100, 120, "PER_ITEM", "", []),
    ("INSTALL_MOSQUITO", "Montaggio zanzariere", "POSA",
        70, 90, "PER_ITEM", "Comprensivo di materiali di consumo.", []),
    ("INSTALL_MOSQUITO_DOUBLE", "Montaggio zanzariera doppia", "POSA",
        140, 165, "PER_ITEM", "Comprensivo di materiali di consumo.", []),
    ("REPAIR_ACCESSORIES", "Sostituzione solo accessori (corda/passacinghia/molle)",
        "ACCESSORIO", 15, 30, "PER_ITEM",
        "Unità esatta da confermare (PER_INTERVENTION vs PER_ITEM) — NEEDS_PO_CONFIRMATION.", []),
    ("REPAIR_ROLLER_KIT", "Sostituzione solo kit cassonetto completo",
        "ACCESSORIO", 40, 60, "PER_ITEM",
        "Rullo, cuscinetto, puleggia, molla, corda, passacinghia.", []),
    ("COPRIFILI", "Coprifili (solo per lavori incompleti)", "ACCESSORIO",
        15, 25, "PER_ITEM", "", []),
    ("IMBOTTI", "Imbotti in lamiera o PVC", "ACCESSORIO",
        35, 50, "PER_ITEM", "", []),
    # --- SMONTAGGI ---
    ("REMOVE_WINDOW", "Smontaggio infissi", "SMONTAGGIO",
        20, 40, "PER_ITEM", "", []),
    ("REMOVE_ROLLER_BOX", "Smontaggio cassonetti", "SMONTAGGIO",
        20, 40, "PER_ITEM", "", []),
    ("REMOVE_ROLLER_KIT", "Smontaggio kit tapparelle", "SMONTAGGIO",
        20, 40, "PER_ITEM", "", []),
    ("REMOVE_SHUTTER", "Smontaggio persiane", "SMONTAGGIO",
        20, 40, "PER_ITEM", "", []),
    ("REMOVE_MOSQUITO", "Smontaggio zanzariera", "SMONTAGGIO",
        20, 40, "PER_ITEM", "", []),
    ("REMOVE_ARMORED_DOOR", "Smontaggio portone blindato", "SMONTAGGIO",
        30, 60, "PER_ITEM", "", []),
    # --- LOGISTICA (regola da definire) ---
    ("LOGISTICS_LOADING", "Carico / Trasporto / Scarico / Smistamento", "LOGISTICA",
        None, None, "VARIABLE",
        "Costo calcolato in base a quantità/distanza/lavoro necessario. "
        "PRICING_RULE_TO_DEFINE fino a nuova business rule.", []),
    ("LOGISTICS_RETURN_OLD", "Consegna materiale vecchio presso magazzini", "LOGISTICA",
        None, None, "VARIABLE",
        "Regola da definire dopo conferma tariffe.", []),
]


async def _ensure_seed(db, tenant_id: str) -> None:
    n = await db.simple_services.count_documents({"tenant_id": tenant_id, "deleted_at": None})
    if n:
        return
    now = datetime.now(timezone.utc).isoformat()
    for code, name, cat, iref, csale, unit, notes, suggested in SEED_ENERHIA_SERVICES:
        status = "PRICING_RULE_TO_DEFINE" if (iref is None or csale is None) else "ACTIVE"
        await db.simple_services.insert_one({
            "_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "code": code,
            "name": name,
            "category": cat,
            "description": "",
            "pricing_unit": unit,
            "internal_reference_price": iref,
            "customer_sale_price": csale,
            "vat_pct": 22.0,
            "valid_from": None,
            "valid_to": None,
            "status": status,
            "quantity_rule": None,
            "suggested_for_recipes": suggested,
            "notes": notes,
            "version": 1,
            "active": True,
            "created_at": now, "updated_at": now,
            "deleted_at": None,
        })


def _can_see_internal(user: dict, perms: set) -> bool:
    """Chi può vedere l'internal_reference_price:
    - Super Admin / Admin (bypass * o role admin)
    - Permesso pricing_admin.manage
    - Permesso pricelists.manage (owner listini)
    """
    return (user_has_permission(user, perms, "pricing_admin.manage")
            or user_has_permission(user, perms, "pricelists.manage")
            or user_has_permission(user, perms, "*"))


def _serialize(doc: dict, can_see_internal: bool) -> dict:
    out = {
        "id": doc["_id"],
        "code": doc.get("code"),
        "name": doc.get("name"),
        "category": doc.get("category"),
        "description": doc.get("description", ""),
        "pricing_unit": doc.get("pricing_unit"),
        "customer_sale_price": doc.get("customer_sale_price"),
        "vat_pct": doc.get("vat_pct", 22.0),
        "valid_from": doc.get("valid_from"),
        "valid_to": doc.get("valid_to"),
        "status": doc.get("status"),
        "quantity_rule": doc.get("quantity_rule"),
        "suggested_for_recipes": doc.get("suggested_for_recipes", []),
        "notes": doc.get("notes"),
        "version": doc.get("version", 1),
    }
    if can_see_internal:
        out["internal_reference_price"] = doc.get("internal_reference_price")
        # spazio di sconto: differenza tra prezzo vendita e riferimento interno
        cs = doc.get("customer_sale_price")
        ir = doc.get("internal_reference_price")
        if cs is not None and ir is not None:
            out["discount_room"] = round(float(cs) - float(ir), 2)
        else:
            out["discount_room"] = None
    return out


# ==============================================================
# API endpoints
# ==============================================================
@router.get("")
async def list_services(
    q: Optional[str] = None,
    category: Optional[str] = None,
    user: dict = Depends(require_permission("pricelists.view")),
):
    db = get_db()
    await _ensure_seed(db, user["tenant_id"])
    perms = set(await get_permission_keys_for_user(user))
    can_see_internal = _can_see_internal(user, perms)

    query: Dict[str, Any] = {"tenant_id": user["tenant_id"], "deleted_at": None, "active": True}
    if category:
        query["category"] = category
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"code": {"$regex": q, "$options": "i"}},
            {"category": {"$regex": q, "$options": "i"}},
        ]
    items: List[dict] = []
    async for d in db.simple_services.find(query).sort([("category", 1), ("name", 1)]):
        items.append(_serialize(d, can_see_internal))
    return {
        "items": items,
        "total": len(items),
        "user_can_see_internal_price": can_see_internal,
    }


@router.get("/{sid}")
async def get_service(sid: str,
                       user: dict = Depends(require_permission("pricelists.view"))):
    db = get_db()
    doc = await db.simple_services.find_one({
        "_id": sid, "tenant_id": user["tenant_id"], "deleted_at": None,
    })
    if not doc:
        raise HTTPException(404, "Servizio non trovato")
    perms = set(await get_permission_keys_for_user(user))
    return _serialize(doc, _can_see_internal(user, perms))


@router.post("")
async def create_service(
    payload: SimpleServiceCreate,
    user: dict = Depends(require_permission("pricelists.manage")),
):
    db = get_db()
    if payload.pricing_unit not in PRICING_UNITS:
        raise HTTPException(400, {"code": "INVALID_PRICING_UNIT",
                                     "message": f"pricing_unit deve essere una di {sorted(PRICING_UNITS)}"})
    if payload.status not in STATUSES:
        raise HTTPException(400, {"code": "INVALID_STATUS",
                                     "message": f"status deve essere una di {sorted(STATUSES)}"})
    now = datetime.now(timezone.utc).isoformat()
    _id = str(uuid.uuid4())
    await db.simple_services.insert_one({
        "_id": _id,
        "tenant_id": user["tenant_id"],
        "code": payload.code or _id[:8].upper(),
        "name": payload.name,
        "category": payload.category,
        "description": payload.description or "",
        "pricing_unit": payload.pricing_unit,
        "internal_reference_price": payload.internal_reference_price,
        "customer_sale_price": payload.customer_sale_price,
        "vat_pct": payload.vat_pct,
        "valid_from": payload.valid_from,
        "valid_to": payload.valid_to,
        "status": payload.status,
        "quantity_rule": payload.quantity_rule,
        "suggested_for_recipes": payload.suggested_for_recipes or [],
        "notes": payload.notes,
        "version": 1,
        "active": True,
        "created_at": now, "updated_at": now,
        "created_by": user.get("email") or user["id"],
        "deleted_at": None,
    })
    perms = set(await get_permission_keys_for_user(user))
    doc = await db.simple_services.find_one({"_id": _id})
    return _serialize(doc, _can_see_internal(user, perms))


@router.patch("/{sid}")
async def update_service(
    sid: str,
    payload: SimpleServiceUpdate,
    user: dict = Depends(require_permission("pricelists.manage")),
):
    db = get_db()
    doc = await db.simple_services.find_one({"_id": sid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Servizio non trovato")

    upd = payload.model_dump(exclude_unset=True)
    if "pricing_unit" in upd and upd["pricing_unit"] not in PRICING_UNITS:
        raise HTTPException(400, "pricing_unit non valida")
    if "status" in upd and upd["status"] not in STATUSES:
        raise HTTPException(400, "status non valido")

    # Un utente senza permesso pricing_admin non può toccare internal_reference_price
    perms = set(await get_permission_keys_for_user(user))
    if "internal_reference_price" in upd and not _can_see_internal(user, perms):
        raise HTTPException(403, {"code": "INTERNAL_PRICE_HIDDEN",
                                     "message": "Permesso mancante per modificare il prezzo interno di riferimento."})

    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    upd["updated_by"] = user.get("email") or user["id"]
    await db.simple_services.update_one({"_id": sid}, {"$set": upd, "$inc": {"version": 1}})
    doc2 = await db.simple_services.find_one({"_id": sid})
    return _serialize(doc2, _can_see_internal(user, perms))


@router.delete("/{sid}")
async def delete_service(
    sid: str,
    user: dict = Depends(require_permission("pricelists.manage")),
):
    db = get_db()
    doc = await db.simple_services.find_one({"_id": sid, "tenant_id": user["tenant_id"], "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Servizio non trovato")
    await db.simple_services.update_one({"_id": sid}, {"$set": {
        "deleted_at": datetime.now(timezone.utc).isoformat(),
        "active": False,
        "status": "ARCHIVED",
    }})
    return {"ok": True}


# ==============================================================
# DISCOUNT GUARD helper (per uso futuro nel motore preventivo)
# ==============================================================
class DiscountGuardRequest(BaseModel):
    service_id: str
    quantity: float = 1.0
    discount_amount: float = 0.0    # sconto in EUR
    discount_pct: float = 0.0        # sconto in %


@router.post("/discount-guard")
async def evaluate_discount_guard(
    payload: DiscountGuardRequest,
    user: dict = Depends(require_permission("quotes.apply_discount")),
):
    """Valuta se uno sconto porta sotto il prezzo interno di riferimento.

    Ritorna:
      list_price, discount, net_sale_price,
      internal_reference_price (solo se can_see_internal),
      remaining_discount_room,
      override_required (bool) → se True, richiede permesso
        `pricing.override_below_reference` e audit `AUTHORIZED_PRICE_OVERRIDE`.
    """
    db = get_db()
    svc = await db.simple_services.find_one({"_id": payload.service_id,
                                                "tenant_id": user["tenant_id"],
                                                "deleted_at": None})
    if not svc:
        raise HTTPException(404, "Servizio non trovato")

    perms = set(await get_permission_keys_for_user(user))
    list_price = float(svc.get("customer_sale_price") or 0)
    iref = svc.get("internal_reference_price")
    qty = float(payload.quantity or 1)

    # Applica sconto: preferisci pct se >0, altrimenti amount
    disc_amount = float(payload.discount_amount or 0)
    if payload.discount_pct and payload.discount_pct > 0:
        disc_amount = list_price * (payload.discount_pct / 100.0)

    net_unit = max(list_price - disc_amount, 0.0)

    room = None
    override_required = False
    if iref is not None:
        room = round(net_unit - float(iref), 2)
        if net_unit < float(iref):
            override_required = True

    result: Dict[str, Any] = {
        "service_id": svc["_id"],
        "service_name": svc.get("name"),
        "list_price": round(list_price, 2),
        "quantity": qty,
        "discount": round(disc_amount, 2),
        "net_sale_price_unit": round(net_unit, 2),
        "net_sale_price_total": round(net_unit * qty, 2),
        "override_required": override_required,
    }
    if _can_see_internal(user, perms):
        result["internal_reference_price"] = iref
        result["remaining_discount_room"] = room
    return result
