"""Seed dati demo per l'Engine Parametrico.

Tutti i documenti sono marcati `is_demo=True` per essere:
- esclusi da KPI reali;
- sostituibili tramite import;
- eliminabili/disattivabili con un solo comando.

Contenuto:
- Sistema profilo PVC 70mm
- Profili: telaio, anta, montante, traverso, fermavetro
- Categorie colore 1/2/3
- Colori esempio
- Vetri: doppio e triplo
- Ferramenta: standard e anta-ribalta
- BOM templates: finestra 1 anta, finestra 2 ante, fisso, portafinestra 1 anta
- Price matrix: finestra 1 anta e 2 ante
- Item pricelists: sell e cost (default)
- Pricing mode config a livello tenant (C_hybrid)

Idempotente: non duplica se `code` già presente.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List
from datetime import datetime, timezone
from app.db import get_db
from app.mongo_utils import to_mongo
from app.models_parametric import (
    ProfileSystem, ProfileSystemTech,
    Profile, ColorCategory, Color, GlassType, HardwareKit, Accessory,
    ItemPricelist, ItemPricelistEntry,
    PriceMatrix, PriceMatrixCell,
    BomTemplate, BomComponent,
    PricingModeConfig,
)
from app.models import new_id

logger = logging.getLogger("infissi.seed_parametric")


async def _upsert(collection: str, tenant_id: str, code: str, instance) -> str:
    db = get_db()
    existing = await db[collection].find_one({"tenant_id": tenant_id, "code": code, "deleted_at": None})
    if existing:
        return existing["_id"]
    instance.tenant_id = tenant_id
    doc = to_mongo(instance.model_dump(by_alias=True))
    await db[collection].insert_one(doc)
    return instance.id


async def _upsert_by_scope(collection: str, tenant_id: str, filters: Dict[str, Any], instance) -> str:
    db = get_db()
    q = {"tenant_id": tenant_id, "deleted_at": None, **filters}
    existing = await db[collection].find_one(q)
    if existing:
        return existing["_id"]
    instance.tenant_id = tenant_id
    doc = to_mongo(instance.model_dump(by_alias=True))
    await db[collection].insert_one(doc)
    return instance.id


async def seed_parametric_demo(tenant_id: str) -> Dict[str, Any]:
    """Crea seed demo idempotente. Ritorna riepilogo id creati/esistenti."""
    logger.info(f"[parametric] Seed demo per tenant={tenant_id}")
    db = get_db()

    # ---------- Profile System PVC 70mm ----------
    ps_pvc = ProfileSystem(
        code="PVC70", name="PVC 70mm 5 camere",
        material="pvc", series="Confort 70",
        description="Sistema PVC 5 camere, spessore 70mm — dati DEMO",
        is_demo=True,
        tech=ProfileSystemTech(
            frame_width_mm=70, sash_width_mm=78, central_node_mm=108,
            rebate_mm=20, glass_clearance_mm=4, glass_deduction_mm=60,
            weld_allowance_mm=0, kerf_mm=3, bar_length_mm=6500,
            bar_head_offcut_mm=50, bar_tail_offcut_mm=50,
            min_reusable_scrap_mm=400, max_sash_weight_kg=80,
            max_width_mm=2400, max_height_mm=2800,
        ),
    )
    ps_id = await _upsert("profile_systems", tenant_id, "PVC70", ps_pvc)

    # ---------- Profiles ----------
    profiles_seed = [
        ("PROF-FRAME-70", "Telaio 70mm", "frame", 15.0, 12.0, 2.2),
        ("PROF-SASH-78",  "Anta 78mm",   "sash",  17.5, 14.0, 2.5),
        ("PROF-MULL-95",  "Montante centrale 95mm", "mullion", 20.0, 16.0, 3.0),
        ("PROF-TRAN-85",  "Traverso 85mm", "transom", 18.5, 14.5, 2.7),
        ("PROF-BEAD-25",  "Fermavetro 25mm", "glazing_bead", 5.5, 4.0, 0.4),
        ("PROF-REINF-F",  "Rinforzo telaio in acciaio", "reinforcement_frame", 12.0, 9.5, 1.8),
        ("PROF-REINF-S",  "Rinforzo anta in acciaio",   "reinforcement_sash",  13.0, 10.0, 1.9),
    ]
    profile_ids: Dict[str, str] = {}
    for code, name, role, price_m, cost_m, weight_m in profiles_seed:
        pf = Profile(
            system_id=ps_id, code=code, name=name, role=role,
            indicative_price_per_m=price_m, indicative_cost_per_m=cost_m,
            weight_per_m_kg=weight_m, is_demo=True,
        )
        profile_ids[role] = await _upsert("profiles", tenant_id, code, pf)

    # ---------- Color Categories ----------
    cat1 = ColorCategory(code="CAT1", name="Cat.1 Standard bianco",
                          scrap_mode="global_reuse", surcharge_pct=0, surcharge_fixed=0,
                          scrap_reuse_policy="same_color_any_compatible_profile",
                          charges_whole_bar=False, is_demo=True,
                          notes="Colore di serie a magazzino. Sfrido riutilizzabile globalmente.")
    cat2 = ColorCategory(code="CAT2", name="Cat.2 Speciale (no rincaro)",
                          scrap_mode="order_reuse", surcharge_pct=0, surcharge_fixed=0,
                          scrap_reuse_policy="same_color_same_profile_only",
                          charges_whole_bar=False, lead_time_days=15, is_demo=True,
                          notes="Colore speciale senza sovrapprezzo commerciale. Sfrido usabile solo nello stesso ordine.")
    cat3 = ColorCategory(code="CAT3", name="Cat.3 Speciale (rincaro/barra intera)",
                          scrap_mode="order_full_cost", surcharge_pct=15, surcharge_fixed=0,
                          scrap_reuse_policy="same_color_same_profile_only",
                          charges_whole_bar=True, requires_approval=True, lead_time_days=25, is_demo=True,
                          notes="Cliente paga barra intera. Residuo in magazzino con costo netto zero.")
    cat1_id = await _upsert("color_categories", tenant_id, "CAT1", cat1)
    cat2_id = await _upsert("color_categories", tenant_id, "CAT2", cat2)
    cat3_id = await _upsert("color_categories", tenant_id, "CAT3", cat3)

    # ---------- Colors ----------
    for code, name, cid, ral in [
        ("BIANCO", "Bianco RAL 9016", cat1_id, "9016"),
        ("NOCE-INT-BIANCO-EST", "Noce int. / Bianco est.", cat2_id, ""),
        ("RAL7016-STRUTT", "RAL 7016 antracite strutturato", cat3_id, "7016"),
    ]:
        c = Color(code=code, name=name, category_id=cid, ral_code=ral, is_demo=True)
        await _upsert("colors", tenant_id, code, c)

    # ---------- Glass Types ----------
    for code, name, comp, thk, sqm_price, sqm_cost, uv in [
        ("GL-4-16-4", "Doppio 4/16/4 argon", "4-16-4 Ar Low-E", 24, 55, 35, 1.1),
        ("GL-4-14-4-14-4", "Triplo 4/14/4/14/4 argon", "4-14-4-14-4 Ar Low-E", 40, 95, 68, 0.6),
        ("GL-STRAT", "Stratificato acustico 33.1+16+44.1", "Ac 33.1-16-44.1", 34, 130, 92, 1.0),
    ]:
        g = GlassType(code=code, name=name, composition=comp, thickness_mm=thk,
                       indicative_sqm_price=sqm_price, indicative_sqm_cost=sqm_cost, u_value=uv,
                       is_demo=True)
        await _upsert("glass_types", tenant_id, code, g)

    # ---------- Hardware Kits ----------
    for code, name, kt, price, cost in [
        ("HW-FIXED",     "Nessuna ferramenta (fisso)", "fixed", 0, 0),
        ("HW-1ANTA",     "Ferramenta 1 anta standard", "single_sash", 45, 25),
        ("HW-1ANTA-AR",  "Ferramenta 1 anta anta-ribalta", "tilt_turn", 78, 42),
        ("HW-2ANTE",     "Ferramenta 2 ante", "double_sash", 105, 55),
        ("HW-SCORR",     "Ferramenta scorrevole 2 ante", "sliding", 210, 115),
    ]:
        h = HardwareKit(code=code, name=name, kit_type=kt,
                         indicative_price=price, indicative_cost=cost, is_demo=True)
        await _upsert("hardware_kits", tenant_id, code, h)

    # ---------- Accessories ----------
    for code, name, kind, unit, price, cost in [
        ("SEAL-EPDM", "Guarnizione EPDM", "seal", "linear_m", 1.5, 0.9),
        ("SILL-30",   "Davanzale 30cm", "sill", "linear_m", 22, 15),
        ("SCREW-STD", "Vite standard", "screw", "piece", 0.10, 0.05),
    ]:
        a = Accessory(code=code, name=name, kind=kind, unit_type=unit,
                       indicative_price=price, indicative_cost=cost, is_demo=True)
        await _upsert("accessories", tenant_id, code, a)

    # ---------- Item Pricelists (sell + cost) ----------
    prof_frame_id = profile_ids.get("frame")
    prof_sash_id = profile_ids.get("sash")
    prof_mull_id = profile_ids.get("mullion")
    prof_tran_id = profile_ids.get("transom")
    prof_bead_id = profile_ids.get("glazing_bead")

    def _entry(rt, rid, unit, price):
        return ItemPricelistEntry(ref_type=rt, ref_id=rid, unit=unit, unit_price=price)

    sell_pl = ItemPricelist(
        code="SELL-DEMO", name="Listino vendita DEMO", kind="sell",
        entries=[
            _entry("profile", prof_frame_id, "linear_m", 15.0),
            _entry("profile", prof_sash_id,  "linear_m", 17.5),
            _entry("profile", prof_mull_id,  "linear_m", 20.0),
            _entry("profile", prof_tran_id,  "linear_m", 18.5),
            _entry("profile", prof_bead_id,  "linear_m", 5.5),
        ],
        is_demo=True,
    )
    cost_pl = ItemPricelist(
        code="COST-DEMO", name="Listino costo DEMO", kind="cost",
        entries=[
            _entry("profile", prof_frame_id, "linear_m", 12.0),
            _entry("profile", prof_sash_id,  "linear_m", 14.0),
            _entry("profile", prof_mull_id,  "linear_m", 16.0),
            _entry("profile", prof_tran_id,  "linear_m", 14.5),
            _entry("profile", prof_bead_id,  "linear_m", 4.0),
        ],
        is_demo=True,
    )
    sell_pl_id = await _upsert("item_pricelists", tenant_id, "SELL-DEMO", sell_pl)
    cost_pl_id = await _upsert("item_pricelists", tenant_id, "COST-DEMO", cost_pl)

    # ---------- BOM Templates ----------
    # Convenzione formule (parametrico secondo tech del sistema):
    #  - Traversa telaio orizzontale: L - 2*frame_width
    #  - Montante telaio verticale:   H - 2*frame_width
    #  - Traversa anta orizzontale:   L/nr_ante - 2*sash_width - central_node*(nr_ante-1)/nr_ante
    #  - Vetro: L - glass_deduction; H - glass_deduction
    #
    # NB: usiamo variabili disponibili nel parser AST (formula.py già esteso).

    def _bom_1_anta():
        return BomTemplate(
            code="BOM-WIN-1A", name="Finestra 1 anta",
            product_key="window_1_leaf", profile_system_id=ps_id,
            hardware_kit_default_id=None,  # sovrascritto in preview via HW-1ANTA
            glass_type_default_id=None,
            color_category_default_id=cat1_id, level="commercial",
            is_demo=True,
            components=[
                BomComponent(sequence=10, component_type="profile", ref_id=prof_frame_id,
                              role="frame_top", quantity_formula="1", length_formula="L",
                              unit_of_measure="linear_m", waste_pct=2, is_cutting_relevant=True),
                BomComponent(sequence=11, component_type="profile", ref_id=prof_frame_id,
                              role="frame_bottom", quantity_formula="1", length_formula="L",
                              unit_of_measure="linear_m", waste_pct=2, is_cutting_relevant=True),
                BomComponent(sequence=12, component_type="profile", ref_id=prof_frame_id,
                              role="frame_left", quantity_formula="1", length_formula="H",
                              unit_of_measure="linear_m", waste_pct=2, is_cutting_relevant=True),
                BomComponent(sequence=13, component_type="profile", ref_id=prof_frame_id,
                              role="frame_right", quantity_formula="1", length_formula="H",
                              unit_of_measure="linear_m", waste_pct=2, is_cutting_relevant=True),
                # Anta
                BomComponent(sequence=20, component_type="profile", ref_id=prof_sash_id,
                              role="sash_top", quantity_formula="1",
                              length_formula="L - 2*frame_width - 2*sash_clearance",
                              unit_of_measure="linear_m", waste_pct=2),
                BomComponent(sequence=21, component_type="profile", ref_id=prof_sash_id,
                              role="sash_bottom", quantity_formula="1",
                              length_formula="L - 2*frame_width - 2*sash_clearance",
                              unit_of_measure="linear_m", waste_pct=2),
                BomComponent(sequence=22, component_type="profile", ref_id=prof_sash_id,
                              role="sash_left", quantity_formula="1",
                              length_formula="H - 2*frame_width - 2*sash_clearance",
                              unit_of_measure="linear_m", waste_pct=2),
                BomComponent(sequence=23, component_type="profile", ref_id=prof_sash_id,
                              role="sash_right", quantity_formula="1",
                              length_formula="H - 2*frame_width - 2*sash_clearance",
                              unit_of_measure="linear_m", waste_pct=2),
                # Vetro (per anta)
                BomComponent(sequence=30, component_type="glass", ref_id=None,
                              role="glass_a", quantity_formula="1",
                              width_formula="L - 2*frame_width - 2*sash_width - glass_deduction",
                              height_formula="H - 2*frame_width - 2*sash_width - glass_deduction",
                              unit_of_measure="sqm", waste_pct=0, is_cutting_relevant=False),
                # Ferramenta
                BomComponent(sequence=40, component_type="hardware", ref_id=None,
                              role="hardware_kit", quantity_formula="1",
                              unit_of_measure="piece", waste_pct=0, is_cutting_relevant=False),
            ],
        )

    def _bom_2_ante():
        return BomTemplate(
            code="BOM-WIN-2A", name="Finestra 2 ante",
            product_key="window_2_leaves", profile_system_id=ps_id,
            color_category_default_id=cat1_id, level="commercial", is_demo=True,
            components=[
                BomComponent(sequence=10, component_type="profile", ref_id=prof_frame_id,
                              role="frame_top", quantity_formula="1", length_formula="L", unit_of_measure="linear_m", waste_pct=2),
                BomComponent(sequence=11, component_type="profile", ref_id=prof_frame_id,
                              role="frame_bottom", quantity_formula="1", length_formula="L", unit_of_measure="linear_m", waste_pct=2),
                BomComponent(sequence=12, component_type="profile", ref_id=prof_frame_id,
                              role="frame_left", quantity_formula="1", length_formula="H", unit_of_measure="linear_m", waste_pct=2),
                BomComponent(sequence=13, component_type="profile", ref_id=prof_frame_id,
                              role="frame_right", quantity_formula="1", length_formula="H", unit_of_measure="linear_m", waste_pct=2),
                # 2 ante
                BomComponent(sequence=20, component_type="profile", ref_id=prof_sash_id, role="sash_top",
                              quantity_formula="2",
                              length_formula="(L - 2*frame_width - central_node) / 2 - 2*sash_clearance",
                              unit_of_measure="linear_m", waste_pct=2),
                BomComponent(sequence=21, component_type="profile", ref_id=prof_sash_id, role="sash_bottom",
                              quantity_formula="2",
                              length_formula="(L - 2*frame_width - central_node) / 2 - 2*sash_clearance",
                              unit_of_measure="linear_m", waste_pct=2),
                BomComponent(sequence=22, component_type="profile", ref_id=prof_sash_id, role="sash_left",
                              quantity_formula="2",
                              length_formula="H - 2*frame_width - 2*sash_clearance",
                              unit_of_measure="linear_m", waste_pct=2),
                BomComponent(sequence=23, component_type="profile", ref_id=prof_sash_id, role="sash_right",
                              quantity_formula="2",
                              length_formula="H - 2*frame_width - 2*sash_clearance",
                              unit_of_measure="linear_m", waste_pct=2),
                # Vetro 2 pezzi
                BomComponent(sequence=30, component_type="glass", ref_id=None, role="glass_a", quantity_formula="2",
                              width_formula="(L - 2*frame_width - central_node)/2 - 2*sash_width - glass_deduction",
                              height_formula="H - 2*frame_width - 2*sash_width - glass_deduction",
                              unit_of_measure="sqm", is_cutting_relevant=False),
                # Ferramenta
                BomComponent(sequence=40, component_type="hardware", ref_id=None, role="hardware_kit",
                              quantity_formula="1", unit_of_measure="piece", is_cutting_relevant=False),
            ],
        )

    def _bom_fisso():
        return BomTemplate(
            code="BOM-FIXED", name="Fisso (no anta)",
            product_key="window_fixed", profile_system_id=ps_id,
            color_category_default_id=cat1_id, level="commercial", is_demo=True,
            components=[
                BomComponent(sequence=10, component_type="profile", ref_id=prof_frame_id, role="frame_top",
                              quantity_formula="1", length_formula="L", unit_of_measure="linear_m", waste_pct=2),
                BomComponent(sequence=11, component_type="profile", ref_id=prof_frame_id, role="frame_bottom",
                              quantity_formula="1", length_formula="L", unit_of_measure="linear_m", waste_pct=2),
                BomComponent(sequence=12, component_type="profile", ref_id=prof_frame_id, role="frame_left",
                              quantity_formula="1", length_formula="H", unit_of_measure="linear_m", waste_pct=2),
                BomComponent(sequence=13, component_type="profile", ref_id=prof_frame_id, role="frame_right",
                              quantity_formula="1", length_formula="H", unit_of_measure="linear_m", waste_pct=2),
                BomComponent(sequence=30, component_type="glass", ref_id=None, role="glass_a", quantity_formula="1",
                              width_formula="L - 2*frame_width - glass_deduction",
                              height_formula="H - 2*frame_width - glass_deduction",
                              unit_of_measure="sqm", is_cutting_relevant=False),
            ],
        )

    def _bom_pf_1_anta():
        b = _bom_1_anta()
        b.code = "BOM-DOOR-1A"
        b.name = "Portafinestra 1 anta"
        b.product_key = "door_1_leaf"
        return b

    bom_1a_id = await _upsert("bom_templates", tenant_id, "BOM-WIN-1A", _bom_1_anta())
    bom_2a_id = await _upsert("bom_templates", tenant_id, "BOM-WIN-2A", _bom_2_ante())
    bom_fx_id = await _upsert("bom_templates", tenant_id, "BOM-FIXED", _bom_fisso())
    bom_pf_id = await _upsert("bom_templates", tenant_id, "BOM-DOOR-1A", _bom_pf_1_anta())

    # BOM di test per verifica DIV_ZERO su nr_ante: contiene "L / nr_ante" esplicito
    def _bom_test_div():
        return BomTemplate(
            code="BOM-DIVTEST", name="Test formula L/nr_ante",
            product_key="window_multi_ante_test", profile_system_id=ps_id,
            color_category_default_id=cat1_id, level="commercial", is_demo=True,
            technical_notes="TEST ONLY: formula 'L / nr_ante' — verifica errore DIV_ZERO con nr_ante=0",
            components=[
                BomComponent(sequence=10, component_type="profile", ref_id=prof_frame_id,
                              role="frame_top", quantity_formula="nr_ante",
                              length_formula="L / nr_ante", unit_of_measure="linear_m", waste_pct=2),
            ],
        )
    await _upsert("bom_templates", tenant_id, "BOM-DIVTEST", _bom_test_div())

    # ---------- Price Matrix (Finestra 1 anta) ----------
    widths = [800, 1000, 1200, 1400, 1600]
    heights = [1000, 1200, 1400, 1600, 1800, 2000]
    base = 220.0
    cells = []
    for w in widths:
        for h in heights:
            # prezzo semplificato: base + k * area
            p = base + 0.00028 * w * h
            cells.append(PriceMatrixCell(width_mm=w, height_mm=h, price=round(p, 2)))
    matrix_1a = PriceMatrix(
        code="MAT-WIN-1A", name="Matrice Finestra 1 anta PVC70",
        product_key="window_1_leaf",
        profile_system_id=ps_id, color_category_id=cat1_id,
        widths_mm=widths, heights_mm=heights, cells=cells,
        interpolation="nearest_up", allow_extrapolation=False,
        oversize_surcharge_pct=15, is_demo=True,
    )
    matrix_1a_id = await _upsert("price_matrices", tenant_id, "MAT-WIN-1A", matrix_1a)

    cells2 = []
    for w in widths:
        for h in heights:
            p = base * 1.6 + 0.00034 * w * h
            cells2.append(PriceMatrixCell(width_mm=w, height_mm=h, price=round(p, 2)))
    matrix_2a = PriceMatrix(
        code="MAT-WIN-2A", name="Matrice Finestra 2 ante PVC70",
        product_key="window_2_leaves",
        profile_system_id=ps_id, color_category_id=cat1_id,
        widths_mm=widths, heights_mm=heights, cells=cells2,
        interpolation="nearest_up", allow_extrapolation=False,
        oversize_surcharge_pct=15, is_demo=True,
    )
    matrix_2a_id = await _upsert("price_matrices", tenant_id, "MAT-WIN-2A", matrix_2a)

    # ---------- Pricing Mode Config (tenant → C_hybrid) ----------
    tenant_mode = PricingModeConfig(
        scope="tenant", mode="C_hybrid",
        price_matrix_id=matrix_1a_id, bom_template_id=bom_1a_id,
        sell_pricelist_id=sell_pl_id, cost_pricelist_id=cost_pl_id,
        b_markup_pct=30, b_indirect_pct=8, is_demo=True,
        notes="Default DEMO: C ibrida — prezzo dalla matrice, costo dalla BOM.",
    )
    tenant_mode_id = await _upsert_by_scope("pricing_mode_configs", tenant_id,
                                             {"scope": "tenant"}, tenant_mode)

    # Product-level per finestra 2 ante (usa matrice 2 ante e BOM 2 ante)
    product_mode_2a = PricingModeConfig(
        scope="product", product_key="window_2_leaves", mode="C_hybrid",
        price_matrix_id=matrix_2a_id, bom_template_id=bom_2a_id,
        sell_pricelist_id=sell_pl_id, cost_pricelist_id=cost_pl_id,
        b_markup_pct=32, b_indirect_pct=8, is_demo=True,
    )
    await _upsert_by_scope("pricing_mode_configs", tenant_id,
                            {"scope": "product", "product_key": "window_2_leaves"}, product_mode_2a)

    # Product-level fisso
    product_mode_fx = PricingModeConfig(
        scope="product", product_key="window_fixed", mode="B_bom",
        bom_template_id=bom_fx_id,
        sell_pricelist_id=sell_pl_id, cost_pricelist_id=cost_pl_id,
        b_markup_pct=28, b_indirect_pct=8, is_demo=True,
    )
    await _upsert_by_scope("pricing_mode_configs", tenant_id,
                            {"scope": "product", "product_key": "window_fixed"}, product_mode_fx)

    # Product-level portafinestra
    product_mode_pf = PricingModeConfig(
        scope="product", product_key="door_1_leaf", mode="B_bom",
        bom_template_id=bom_pf_id,
        sell_pricelist_id=sell_pl_id, cost_pricelist_id=cost_pl_id,
        b_markup_pct=32, b_indirect_pct=8, is_demo=True,
    )
    await _upsert_by_scope("pricing_mode_configs", tenant_id,
                            {"scope": "product", "product_key": "door_1_leaf"}, product_mode_pf)

    return {
        "ok": True,
        "profile_system_id": ps_id,
        "bom_ids": {"1a": bom_1a_id, "2a": bom_2a_id, "fixed": bom_fx_id, "door_1a": bom_pf_id},
        "matrix_ids": {"1a": matrix_1a_id, "2a": matrix_2a_id},
        "pricing_tenant_mode_id": tenant_mode_id,
        "cat_ids": {"1": cat1_id, "2": cat2_id, "3": cat3_id},
    }
