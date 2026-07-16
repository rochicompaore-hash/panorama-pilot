"""Seed default Infissi Express pricelist, rules, and product catalog (M3.2)."""
from __future__ import annotations
import logging
from app.db import get_db
from app.models import new_id
from app.models_quote import Pricelist
from app.models_pricing import PriceRuleV2, ProductCatalog
from app.mongo_utils import to_mongo

logger = logging.getLogger("seed_pricing")


DEFAULT_PRICELIST_KEY = "IE_DEFAULT_2026"

# Rules based on Infissi Express business specs. Each rule references product_config keys:
#   color_kind: ivory_mass | film_ext_only | film_both_same | film_int_only | film_diff
#   external_finish: standard | film | metallic | wood
#   material: pvc | aluminum | wood
INFISSI_RULES = [
    # Color rules on window base
    {
        "code": "COLOR_IVORY_MASS", "name": "Avorio in massa (+8%)",
        "category": "color", "priority": 100, "cumulative": False,
        "conditions": [{"field": "color_kind", "op": "eq", "value": "ivory_mass"}],
        "formula": "8", "effect_type": "pct",
    },
    {
        "code": "COLOR_FILM_EXT_WHITE_INT", "name": "Pellicolato esterno / bianco interno (+14,5%)",
        "category": "color", "priority": 100, "cumulative": False,
        "conditions": [{"field": "color_kind", "op": "eq", "value": "film_ext_only"}],
        "formula": "14.5", "effect_type": "pct",
    },
    {
        "code": "COLOR_FILM_BOTH_SAME", "name": "Pellicolato entrambi i lati (+16%)",
        "category": "color", "priority": 100, "cumulative": False,
        "conditions": [{"field": "color_kind", "op": "eq", "value": "film_both_same"}],
        "formula": "16", "effect_type": "pct",
    },
    {
        "code": "COLOR_FILM_INT_ONLY", "name": "Pellicolato solo interno (+16%)",
        "category": "color", "priority": 100, "cumulative": False,
        "conditions": [{"field": "color_kind", "op": "eq", "value": "film_int_only"}],
        "formula": "16", "effect_type": "pct",
    },
    {
        "code": "COLOR_FILM_DIFF_PCT", "name": "Pellicolato differente due lati (+22%)",
        "category": "color", "priority": 100, "cumulative": True,
        "conditions": [{"field": "color_kind", "op": "eq", "value": "film_diff"}],
        "formula": "22", "effect_type": "pct",
    },
    {
        "code": "COLOR_FILM_DIFF_FIXED", "name": "Supplemento pellicolatura differente (+€ 150)",
        "category": "color", "priority": 101, "cumulative": True,
        "conditions": [{"field": "color_kind", "op": "eq", "value": "film_diff"}],
        "formula": "150", "effect_type": "fixed",
    },
    # Roller (tapparelle) rules - only when product_key indicates roller
    {
        "code": "ROLLER_COLOR_RAL", "name": "Colore RAL tapparella (+8%)",
        "category": "roller", "priority": 110,
        "conditions": [
            {"field": "category", "op": "eq", "value": "roller"},
            {"field": "color_finish", "op": "eq", "value": "ral"},
        ],
        "formula": "8", "effect_type": "pct",
    },
    {
        "code": "ROLLER_FINISH_WOOD_METAL", "name": "Finitura legno/metallizzata tapparella (+30%)",
        "category": "roller", "priority": 111,
        "conditions": [
            {"field": "category", "op": "eq", "value": "roller"},
            {"field": "color_finish", "op": "in", "value": ["wood", "metallic"]},
        ],
        "formula": "30", "effect_type": "pct",
    },
    {
        "code": "ROLLER_ATTACHED_DISCOUNT", "name": "Sconto tapparella abbinata a serramento (-30%)",
        "category": "discount", "priority": 200,
        "conditions": [
            {"field": "category", "op": "eq", "value": "roller"},
            {"field": "attached_to_window", "op": "truthy", "value": True},
        ],
        "formula": "-30", "effect_type": "pct",
    },
    # Motorization surcharge (roller kit)
    {
        "code": "ROLLER_MOTOR_MECHANICAL", "name": "Motore meccanico (+€ 180)",
        "category": "roller", "priority": 120,
        "conditions": [{"field": "motorization", "op": "eq", "value": "mechanical"}],
        "formula": "180", "effect_type": "fixed",
    },
    {
        "code": "ROLLER_MOTOR_RADIO", "name": "Motore radio + telecomando (+€ 260)",
        "category": "roller", "priority": 121,
        "conditions": [{"field": "motorization", "op": "eq", "value": "radio"}],
        "formula": "260", "effect_type": "fixed",
    },
]


# Products (categories) for the catalog
INFISSI_PRODUCTS = [
    {
        "key": "WIN_PVC_STANDARD", "name": "Finestra PVC serie standard",
        "category": "window", "base_price": 480.0, "base_type": "sqm", "min_billable_sqm": 1.0,
        "default_config": {"material": "pvc", "leaves": 1, "opening_type": "vasistas", "glass_type": "double_low_e", "color_kind": "standard", "hardware_line": "standard"},
        "config_schema": {
            "steps": [
                {"key": "material", "label": "Materiale telaio", "type": "single", "options": [
                    {"value": "pvc", "label": "PVC"}, {"value": "aluminum", "label": "Alluminio"}, {"value": "wood", "label": "Legno"},
                ]},
                {"key": "opening_type", "label": "Tipologia apertura", "type": "single", "options": [
                    {"value": "vasistas", "label": "Vasistas"},
                    {"value": "single", "label": "Anta singola"},
                    {"value": "double", "label": "Doppia anta"},
                    {"value": "sliding", "label": "Scorrevole"},
                    {"value": "tilt_turn", "label": "Anta-ribalta"},
                ]},
                {"key": "leaves", "label": "N° ante", "type": "number", "min": 1, "max": 6, "default": 1},
                {"key": "color_kind", "label": "Colorazione", "type": "single", "options": [
                    {"value": "standard", "label": "Bianco standard"},
                    {"value": "ivory_mass", "label": "Avorio in massa (+8%)"},
                    {"value": "film_ext_only", "label": "Pellicolato ext / bianco int (+14,5%)"},
                    {"value": "film_both_same", "label": "Pellicolato entrambi i lati (+16%)"},
                    {"value": "film_int_only", "label": "Pellicolato solo interno (+16%)"},
                    {"value": "film_diff", "label": "Pellicolato differente (+22% +€150)"},
                ]},
                {"key": "glass_type", "label": "Tipo vetro", "type": "single", "options": [
                    {"value": "single", "label": "Vetro singolo"},
                    {"value": "double_low_e", "label": "Doppio basso-emissivo"},
                    {"value": "triple_low_e", "label": "Triplo basso-emissivo"},
                    {"value": "acoustic", "label": "Acustico"},
                    {"value": "safety_44", "label": "Stratificato 44.1"},
                ]},
                {"key": "hardware_line", "label": "Ferramenta", "type": "single", "options": [
                    {"value": "standard", "label": "Standard"},
                    {"value": "silent", "label": "Silenziata"},
                    {"value": "anti_burglary_rc2", "label": "Antieffrazione RC2"},
                ]},
                {"key": "installation", "label": "Posa", "type": "single", "options": [
                    {"value": "included", "label": "Inclusa in opera"},
                    {"value": "extra", "label": "Extra (fornitura sola)"},
                ]},
            ],
        },
        "order_index": 10,
    },
    {
        "key": "WIN_ALU_THERMAL", "name": "Finestra Alluminio taglio termico",
        "category": "window", "base_price": 650.0, "base_type": "sqm", "min_billable_sqm": 1.0,
        "default_config": {"material": "aluminum", "leaves": 1, "glass_type": "double_low_e"},
        "config_schema": {"steps": []},  # simplified — same schema as PVC actually
        "order_index": 20,
    },
    {
        "key": "ROLLER_PVC", "name": "Tapparella PVC",
        "category": "roller", "base_price": 96.0, "base_type": "sqm", "min_billable_sqm": 1.75,
        "default_config": {"category": "roller", "color_finish": "standard", "motorization": "none", "attached_to_window": True},
        "config_schema": {
            "steps": [
                {"key": "kit", "label": "Composizione kit", "type": "single", "options": [
                    {"value": "cloth_only", "label": "Solo telo"},
                    {"value": "base", "label": "Kit base (telo + rullo)"},
                    {"value": "complete", "label": "Kit completo (telo + rullo + cassonetto)"},
                ]},
                {"key": "color_finish", "label": "Finitura", "type": "single", "options": [
                    {"value": "standard", "label": "Standard bianco"},
                    {"value": "ral", "label": "Colorata RAL (+8%)"},
                    {"value": "wood", "label": "Effetto legno (+30%)"},
                    {"value": "metallic", "label": "Metallizzata (+30%)"},
                ]},
                {"key": "motorization", "label": "Motorizzazione", "type": "single", "options": [
                    {"value": "none", "label": "Nessuna (manuale corda/avvolgitore)"},
                    {"value": "mechanical", "label": "Motore meccanico (+€180)"},
                    {"value": "radio", "label": "Motore radio + telecomando (+€260)"},
                ]},
                {"key": "controls", "label": "Comandi elettrici", "type": "multi", "options": [
                    {"value": "remote", "label": "Telecomando aggiuntivo"},
                    {"value": "sensor_sun", "label": "Sensore sole"},
                    {"value": "sensor_wind", "label": "Sensore vento"},
                    {"value": "wall_switch", "label": "Predisposizione parete"},
                ]},
                {"key": "attached_to_window", "label": "Abbinata a serramento", "type": "boolean"},
            ],
        },
        "order_index": 30,
    },
    {
        "key": "SCREEN_ROLLER", "name": "Zanzariera avvolgibile",
        "category": "screen", "base_price": 130.0, "base_type": "sqm", "min_billable_sqm": 1.0,
        "default_config": {"screen_type": "roller_side"},
        "config_schema": {
            "steps": [
                {"key": "screen_type", "label": "Tipo zanzariera", "type": "single", "options": [
                    {"value": "roller_side", "label": "Avvolgibile laterale"},
                    {"value": "roller_top", "label": "Avvolgibile verticale"},
                    {"value": "plisse", "label": "Plissettata"},
                    {"value": "fixed", "label": "Fissa"},
                ]},
                {"key": "color_finish", "label": "Colore profilo", "type": "single", "options": [
                    {"value": "standard", "label": "Standard bianco"},
                    {"value": "ral", "label": "Colorato RAL"},
                ]},
            ],
        },
        "order_index": 40,
    },
    {
        "key": "SHUTTER_PVC", "name": "Persiana / Scuro PVC",
        "category": "shutter", "base_price": 220.0, "base_type": "sqm", "min_billable_sqm": 1.5,
        "default_config": {"shutter_type": "louvered"},
        "config_schema": {
            "steps": [
                {"key": "shutter_type", "label": "Tipo", "type": "single", "options": [
                    {"value": "louvered", "label": "Persiana a stecche"},
                    {"value": "solid", "label": "Scuro pieno"},
                ]},
                {"key": "leaves", "label": "N° ante", "type": "number", "min": 1, "max": 4, "default": 2},
            ],
        },
        "order_index": 50,
    },
    {
        "key": "BOX_STANDARD", "name": "Cassonetto",
        "category": "box", "base_price": 55.0, "base_type": "linear_m",
        "default_config": {"box_type": "coibented"},
        "config_schema": {"steps": []},
        "order_index": 60,
    },
]


async def seed_default_pricelist(tenant_id: str) -> str:
    db = get_db()
    existing = await db.pricelists.find_one({"tenant_id": tenant_id, "is_default": True, "deleted_at": None})
    if existing:
        return existing["_id"]
    pl = Pricelist(
        id=new_id(), tenant_id=tenant_id, name="Listino Standard Infissi Express 2026",
        description="Listino di default con regole Infissi Express",
        currency="EUR", is_default=True, priority=100,
    )
    await db.pricelists.insert_one(to_mongo(pl.model_dump(by_alias=True)))
    return pl.id


async def seed_default_rules(tenant_id: str, pricelist_id: str):
    db = get_db()
    for rule in INFISSI_RULES:
        existing = await db.price_rules.find_one({"tenant_id": tenant_id, "code": rule["code"], "deleted_at": None})
        if existing:
            continue
        r = PriceRuleV2(
            id=new_id(), tenant_id=tenant_id, pricelist_id=pricelist_id,
            code=rule["code"], name=rule["name"], category=rule.get("category", "generic"),
            conditions=rule.get("conditions", []),
            formula=rule["formula"], effect_type=rule["effect_type"],
            priority=rule.get("priority", 100), cumulative=rule.get("cumulative", True), active=True,
        )
        await db.price_rules.insert_one(to_mongo(r.model_dump(by_alias=True)))


async def seed_default_products(tenant_id: str):
    db = get_db()
    for prod in INFISSI_PRODUCTS:
        existing = await db.products.find_one({"tenant_id": tenant_id, "key": prod["key"], "deleted_at": None})
        if existing:
            continue
        p = ProductCatalog(
            id=new_id(), tenant_id=tenant_id, **prod, active=True,
        )
        await db.products.insert_one(to_mongo(p.model_dump(by_alias=True)))


async def run_pricing_seed(tenant_id: str):
    pid = await seed_default_pricelist(tenant_id)
    await seed_default_rules(tenant_id, pid)
    await seed_default_products(tenant_id)
    logger.info("Pricing seed complete for tenant %s (pricelist=%s)", tenant_id, pid)
