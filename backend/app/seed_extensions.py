"""Seed multi-company + SaaS + product catalog demo data.

Idempotente: verifica esistenza prima di inserire.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from app.db import get_db
from app.mongo_utils import to_mongo
from app.models import utcnow, new_id
from app.models_multi_company import LegalEntity
from app.models_saas import (
    SubscriptionModule, ModuleDependency, SubscriptionPlan, TenantEntitlement,
    MODULE_CODES,
)
from app.models_product_types import (
    ProductType, InstallationPricingRule, AccessSurchargeRule,
    PlatformCostRule, MunicipalAuthCostRule,
)


LEGAL_ENTITIES_SEED = [
    {"code": "ENERHIA", "name": "Enerhia Srl", "legal_form": "SRL",
     "is_default": True, "notes": "Società principale — produzione infissi"},
    {"code": "AUXER", "name": "Auxer Srl", "legal_form": "SRL",
     "is_default": False, "notes": "Società accessoria — servizi collegati"},
]


MODULES_SEED = [
    ("core_crm", "Core CRM", "CRM base (lead, clienti, contatti)", "core"),
    ("quotes_contracts", "Preventivi e Contratti", "Preventivi, listini, contratti, firma", "commercial"),
    ("technical_abaco", "Tecnico e Abaco", "Rilievo, abaco tecnico, distinte", "technical"),
    ("production", "Produzione", "Ordini di produzione, tagli, tracciabilità", "operations"),
    ("warehouse", "Magazzino", "Articoli, giacenze, movimenti, inventari", "operations"),
    ("installation_logistics", "Posa e Logistica", "Pianificazione posa, spedizioni", "operations"),
    ("service", "Assistenza", "Ticket post-vendita, garanzie", "postsales"),
    ("administration", "Amministrazione", "Fatture, pagamenti, incassi", "finance"),
    ("treasury", "Tesoreria", "Banche, fondi, IVA, F24, ritenute", "finance"),
    ("management_control", "Controllo di Gestione", "Costi fissi, personale, budget, break-even", "finance"),
    ("ai_cfo", "AI CFO", "Suggerimenti finanziari data-driven", "finance"),
    ("multi_company", "Multi-company", "Gestione più legal entities + consolidamento", "governance"),
    ("omnichannel", "Omnicanale", "WhatsApp, email, webhook lead", "commercial"),
]


DEPENDENCIES_SEED = [
    ("quotes_contracts", "core_crm"),
    ("technical_abaco", "quotes_contracts"),
    ("production", "technical_abaco"),
    ("installation_logistics", "quotes_contracts"),
    ("treasury", "administration"),
    ("management_control", "administration"),
    ("ai_cfo", "treasury"),
    ("ai_cfo", "management_control"),
    ("multi_company", "treasury"),
    ("multi_company", "management_control"),
    ("omnichannel", "core_crm"),
]


PLANS_SEED = [
    {"code": "starter", "name": "Starter",
     "tier": "starter",
     "included_module_codes": ["core_crm", "quotes_contracts"],
     "max_users": 3, "max_storage_mb": 500, "max_legal_entities": 1,
     "trial_days": 14, "is_demo": True, "is_default": False,
     "notes": "Piano iniziale — modificabile"},
    {"code": "professional", "name": "Professional",
     "tier": "professional",
     "included_module_codes": ["core_crm", "quotes_contracts", "technical_abaco",
                                "installation_logistics", "administration", "omnichannel"],
     "max_users": 10, "max_storage_mb": 5000, "max_legal_entities": 1,
     "trial_days": 30, "is_demo": True, "is_default": True,
     "notes": "Piano intermedio — modificabile"},
    {"code": "enterprise", "name": "Enterprise",
     "tier": "enterprise",
     "included_module_codes": list(MODULE_CODES),
     "max_users": 100, "max_storage_mb": 50000, "max_legal_entities": 5,
     "trial_days": 30, "is_demo": True, "is_default": False,
     "notes": "Piano completo — modificabile"},
]


PRODUCT_TYPES_SEED = [
    ("window_1", "Finestra 1 anta", "window", ["battente", "ribalta", "battente_ribalta"], False),
    ("window_2", "Finestra 2 ante", "window", ["battente", "ribalta", "battente_ribalta"], False),
    ("window_3", "Finestra 3 ante (con fissa)", "window", ["battente", "battente_ribalta", "fisso"], True),
    ("window_sopraluce", "Finestra con sopraluce", "window", ["battente", "battente_ribalta"], False),
    ("window_sottoluce", "Finestra con sottoluce", "window", ["battente"], False),
    ("window_fiancoluce", "Finestra con fiancoluce", "window", ["battente"], False),
    ("french_door", "Portafinestra", "french_door", ["battente", "battente_ribalta"], False),
    ("french_door_soprl", "Portafinestra con sopraluce", "french_door", ["battente"], False),
    ("fixed", "Fisso", "fixed", ["fisso"], False),
    ("sliding", "Scorrevole", "sliding", ["scorrevole"], False),
    ("lift_slide", "Alzante scorrevole", "lift_slide", ["alzante"], False),
    ("translating_sliding", "Scorrevole traslante", "translating_sliding", ["traslante"], False),
    ("shutter", "Persiana", "shutter", ["battente"], False),
    ("screen", "Zanzariera", "screen", ["battente", "scorrevole"], False),
    ("roller_shutter", "Tapparella", "roller_shutter", ["scorrevole"], False),
    ("roller_box", "Cassonetto", "roller_box", ["fisso"], False),
    ("entrance_door", "Portoncino", "entrance_door", ["battente"], False),
    ("obscurant", "Oscurante", "obscurant", ["battente", "fisso"], False),
]


ACCESS_RULES_SEED = [
    {"code": "floor_no_elev", "label": "Piano senza ascensore",
     "trigger": "floor_no_elevator", "surcharge_kind": "per_floor",
     "amount": 50.0, "cost_internal": 30.0,
     "notes": "Supplemento per piano quando non c'è ascensore"},
    {"code": "elev_inad", "label": "Ascensore non adeguato",
     "trigger": "elevator_inadequate", "surcharge_kind": "fixed",
     "amount": 120.0, "cost_internal": 80.0,
     "notes": "Ascensore presente ma non idoneo al trasporto"},
    {"code": "platform_req", "label": "Piattaforma aerea richiesta",
     "trigger": "platform_required", "surcharge_kind": "fixed",
     "amount": 400.0, "cost_internal": 250.0,
     "notes": "Base — vedi PlatformCostRule per dettaglio"},
    {"code": "ztl_permit", "label": "ZTL con permesso",
     "trigger": "ztl", "surcharge_kind": "fixed",
     "amount": 60.0, "cost_internal": 30.0},
    {"code": "occ_soil", "label": "Occupazione suolo pubblico",
     "trigger": "occupation_permit", "surcharge_kind": "fixed",
     "amount": 150.0, "cost_internal": 90.0,
     "notes": "Diritti + pratica"},
    {"code": "muni_auth", "label": "Autorizzazione comunale (azienda)",
     "trigger": "municipal_authorization", "surcharge_kind": "fixed",
     "amount": 250.0, "cost_internal": 150.0,
     "notes": "Se gestita da azienda"},
]


INSTALL_RULES_SEED = [
    ("inst_window", "Posa finestra", "window_1", "window", "per_piece", 180.0, 280.0),
    ("inst_window_2", "Posa finestra 2 ante", "window_2", "window", "per_piece", 220.0, 340.0),
    ("inst_french_door", "Posa portafinestra", "french_door", "french_door", "per_piece", 240.0, 380.0),
    ("inst_sliding", "Posa scorrevole", "sliding", "sliding", "per_sqm", 100.0, 160.0),
    ("inst_lift_slide", "Posa alzante scorrevole", "lift_slide", "lift_slide", "per_sqm", 150.0, 240.0),
    ("inst_shutter", "Posa persiana", "shutter", "shutter", "per_piece", 90.0, 150.0),
    ("inst_screen", "Posa zanzariera", "screen", "screen", "per_piece", 50.0, 90.0),
    ("inst_roller", "Posa tapparella", "roller_shutter", "roller_shutter", "per_sqm", 60.0, 110.0),
    ("inst_roller_box", "Posa cassonetto", "roller_box", "roller_box", "per_linear_m", 80.0, 140.0),
    ("inst_entrance", "Posa portoncino", "entrance_door", "entrance_door", "per_piece", 260.0, 420.0),
]


async def seed_multi_company_and_saas(default_company_id: str):
    db = get_db()
    tenant_id = default_company_id  # main tenant

    # ----- Legal Entities -----
    for le_data in LEGAL_ENTITIES_SEED:
        existing = await db.legal_entities.find_one({"tenant_id": tenant_id, "code": le_data["code"], "deleted_at": None})
        if existing: continue
        le = LegalEntity(
            tenant_id=tenant_id, code=le_data["code"], name=le_data["name"],
            legal_form=le_data.get("legal_form"),
            is_default=le_data.get("is_default", False),
            le_status="to_complete",
            missing_fields=["vat_number", "tax_code", "pec"],
            fiscal_operations_blocked=True,
            is_demo=True, notes=le_data.get("notes"),
        )
        await db.legal_entities.insert_one(to_mongo(le.model_dump(by_alias=True)))

    # ----- SaaS Modules -----
    for code, label, desc, cat in MODULES_SEED:
        existing = await db.subscription_modules.find_one({"code": code, "deleted_at": None})
        if existing: continue
        m = SubscriptionModule(code=code, label=label, description=desc, category=cat)
        await db.subscription_modules.insert_one(to_mongo(m.model_dump(by_alias=True)))

    # ----- Dependencies -----
    for mod, req in DEPENDENCIES_SEED:
        existing = await db.module_dependencies.find_one({"module_code": mod, "requires_module": req, "deleted_at": None})
        if existing: continue
        d = ModuleDependency(module_code=mod, requires_module=req, hard=True)
        await db.module_dependencies.insert_one(to_mongo(d.model_dump(by_alias=True)))

    # ----- Plans -----
    for p in PLANS_SEED:
        existing = await db.subscription_plans.find_one({"code": p["code"], "deleted_at": None})
        if existing: continue
        plan = SubscriptionPlan(**p)
        await db.subscription_plans.insert_one(to_mongo(plan.model_dump(by_alias=True)))

    # ----- Default Entitlement (Enterprise) for main tenant -----
    existing_ent = await db.tenant_entitlements.find_one({"tenant_id": tenant_id, "deleted_at": None})
    if not existing_ent:
        ent_plan = await db.subscription_plans.find_one({"code": "enterprise", "deleted_at": None})
        included = list(ent_plan.get("included_module_codes")) if ent_plan else list(MODULE_CODES)
        ent = TenantEntitlement(
            tenant_id=tenant_id, plan_id=ent_plan["_id"] if ent_plan else None,
            plan_code="enterprise", plan_snapshot_module_codes=included,
            module_states={m: "active" for m in included},
        )
        await db.tenant_entitlements.insert_one(to_mongo(ent.model_dump(by_alias=True)))


async def seed_product_catalog(default_company_id: str):
    db = get_db()
    tenant_id = default_company_id
    # Product types
    for i, (code, label, family, configs, supports_fixed_side) in enumerate(PRODUCT_TYPES_SEED):
        existing = await db.product_types.find_one({"tenant_id": tenant_id, "code": code, "deleted_at": None})
        if existing: continue
        pt = ProductType(
            tenant_id=tenant_id, code=code, label=label, family=family,  # type: ignore
            supports_configurations=configs,
            supports_sopraluce=("sopraluce" in code or code.endswith("_soprl")),
            supports_sottoluce=("sottoluce" in code),
            supports_fiancoluce=("fiancoluce" in code),
            supports_fixed_at_side=supports_fixed_side,
            sort_order=(i + 1) * 10, is_demo=True,
        )
        await db.product_types.insert_one(to_mongo(pt.model_dump(by_alias=True)))
    # Install rules
    for code, label, ptype, family, unit, ic, cp in INSTALL_RULES_SEED:
        existing = await db.installation_pricing_rules.find_one({"tenant_id": tenant_id, "code": code, "deleted_at": None})
        if existing: continue
        r = InstallationPricingRule(
            tenant_id=tenant_id, code=code, label=label,
            product_type_code=ptype, product_family=family,  # type: ignore
            install_unit=unit,  # type: ignore
            install_internal_cost=ic, install_customer_price=cp,
            dismount_internal_cost=ic * 0.4, dismount_customer_price=cp * 0.4,
            disposal_cost=15.0, disposal_price=25.0,
            hourly_crew_cost=35.0,
            is_demo=True,
        )
        await db.installation_pricing_rules.insert_one(to_mongo(r.model_dump(by_alias=True)))
    # Access surcharge rules
    for rd in ACCESS_RULES_SEED:
        existing = await db.access_surcharge_rules.find_one({"tenant_id": tenant_id, "code": rd["code"], "deleted_at": None})
        if existing: continue
        r = AccessSurchargeRule(tenant_id=tenant_id, is_demo=True, **rd)
        await db.access_surcharge_rules.insert_one(to_mongo(r.model_dump(by_alias=True)))
    # Platform cost + municipal auth (default single rule)
    if not await db.platform_cost_rules.find_one({"tenant_id": tenant_id, "code": "default", "deleted_at": None}):
        pc = PlatformCostRule(
            tenant_id=tenant_id, code="default", label="Piattaforma standard",
            rental_cost_day=250.0, rental_price_day=380.0, half_day_cost=160.0,
            transport_cost=100.0, operator_cost=180.0, authorization_cost=80.0,
            occupation_cost=50.0, deposit_required=0.0, urgency_surcharge_pct=15.0,
            max_work_height_m=15.0,
        )
        await db.platform_cost_rules.insert_one(to_mongo(pc.model_dump(by_alias=True)))
    if not await db.municipal_auth_cost_rules.find_one({"tenant_id": tenant_id, "code": "default", "deleted_at": None}):
        ma = MunicipalAuthCostRule(
            tenant_id=tenant_id, code="default", label="Autorizzazione standard",
            admin_practice_cost=120.0, municipal_rights_cost=60.0,
            public_soil_occupation_cost=100.0, stamp_duty_cost=16.0,
            technician_cost=150.0, signage_cost=40.0, barrier_cost=60.0,
        )
        await db.municipal_auth_cost_rules.insert_one(to_mongo(ma.model_dump(by_alias=True)))


async def seed_management_demo(default_company_id: str):
    """Alcuni costi fissi/personale demo (marcati is_demo)."""
    db = get_db()
    tenant_id = default_company_id
    from app.models_control import FixedCost, PersonnelCost
    demo_fixed = [
        ("Affitto capannone", "rent", 2500.0, "monthly"),
        ("Bollette luce", "utilities", 800.0, "monthly"),
        ("Assicurazione R.C.", "insurance", 3000.0, "yearly"),
        ("Software gestionale", "software", 150.0, "monthly"),
        ("Consulente commercialista", "consulting", 400.0, "monthly"),
    ]
    for label, cat, amt, rec in demo_fixed:
        existing = await db.fixed_costs.find_one({"tenant_id": tenant_id, "label": label, "deleted_at": None})
        if existing: continue
        monthly = amt if rec == "monthly" else (amt / 12 if rec == "yearly" else amt / 3)
        fc = FixedCost(tenant_id=tenant_id, label=label, category=cat, amount_raw=amt,  # type: ignore
                        recurrence=rec, amount_monthly=round(monthly, 2), is_demo=True)  # type: ignore
        await db.fixed_costs.insert_one(to_mongo(fc.model_dump(by_alias=True)))
    demo_personnel = [
        ("Rossi Mario", "Produzione", "produzione", 32000.0),
        ("Bianchi Anna", "Amministrazione", "amministrazione", 30000.0),
        ("Verdi Luca", "Commerciale", "commerciale", 42000.0),
    ]
    for name, role, dept, ral in demo_personnel:
        existing = await db.personnel_costs.find_one({"tenant_id": tenant_id, "full_name": name, "deleted_at": None})
        if existing: continue
        monthly_gross = ral / 12
        total = round(monthly_gross * 1.30, 2)  # ~30% oneri
        pc = PersonnelCost(tenant_id=tenant_id, full_name=name, role=role, department=dept,
                            ral_yearly=ral, monthly_gross=round(monthly_gross, 2),
                            monthly_total_cost=total, is_demo=True)
        await db.personnel_costs.insert_one(to_mongo(pc.model_dump(by_alias=True)))
