"""4 Resolver della nuova architettura pricing.

Ogni resolver ha responsabilità netta e non ne conosce altre:
- ProfileSystemResolver: quale sistema profilo + quale ricetta tecnica per il prodotto
- BomResolver: quali componenti + quantità (formule V1_3)
- TechnicalCostResolver: costo industriale (materiali + manodopera)
- CommercialPricingService: prezzo vendita da regola commerciale
"""
from __future__ import annotations
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.db import get_db
from .models import (
    PricingRequest, ProfileSystemResolution, BomResolution, BomComponent,
    TechnicalSnapshot, CommercialSnapshot,
)
from .errors import PricingError
from .formulas import (
    frame_ml_1sash, frame_reinforcement_ml_1sash,
    sash_ml_1sash, sash_reinforcement_ml_1sash,
    glass_dimensions_1sash, glass_real_area_sqm, glass_billable_area_sqm,
    recipe_code, production_time_hours_for,
    glass_price_per_sqm, V1_3_COMPONENT_PRICES,
    PVC_ELIGIBLE_ROLES, is_foil_surcharge_applicable, STANDARD_FOIL_SURCHARGE_PERCENT,
)


# =====================================================================
# 1. ProfileSystemResolver
# =====================================================================
class ProfileSystemResolver:
    """Determina profile_system + technical_recipe per il prodotto configurato.

    Legge dalla collection `technical_recipes` (Sistema B target, non products).
    Non calcola prezzi, non applica moltiplicatori, non conosce sconti né IVA.

    Fail-closed:
      MISSING_PROFILE_SYSTEM
      MISSING_TECHNICAL_RECIPE
      INVALID_PRODUCT_CONFIGURATION
    """

    def __init__(self, db):
        self.db = db

    async def resolve(self, req: PricingRequest) -> ProfileSystemResolution:
        if req.width_mm <= 0 or req.height_mm <= 0:
            raise PricingError(
                "INVALID_GEOMETRY",
                configuration={"width_mm": req.width_mm, "height_mm": req.height_mm},
                hint="Configurazione tecnica → Prodotto",
            )

        rc = recipe_code(req.window_type, req.number_of_sashes)

        # Cerca ricetta tecnica: prima per tenant, poi wildcard "*"
        recipe = await self.db.technical_recipes.find_one({
            "$or": [
                {"tenant_id": req.tenant_id},
                {"tenant_id": "*"},
            ],
            "product_key": req.product_key,
            "recipe_code": rc,
            "deleted_at": None,
        }, sort=[("tenant_id", -1)])   # preferisci tenant-specific su wildcard

        if not recipe:
            raise PricingError(
                "MISSING_TECHNICAL_RECIPE",
                configuration={"product_key": req.product_key, "recipe_code": rc},
                hint=f"Configurazione tecnica → Ricette → aggiungi {req.product_key}:{rc}",
            )

        if not recipe.get("profile_system_id"):
            raise PricingError(
                "MISSING_PROFILE_SYSTEM",
                configuration={"recipe_id": recipe.get("_id")},
                hint="Configurazione tecnica → Ricetta senza profile_system_id",
            )

        return ProfileSystemResolution(
            profile_system_id=recipe["profile_system_id"],
            profile_system_code=recipe.get("profile_system_code", ""),
            profile_system_version=int(recipe.get("profile_system_version", 1)),
            technical_recipe_id=recipe["_id"],
            technical_recipe_version=int(recipe.get("version", 1)),
            recipe_code=rc,
        )


# =====================================================================
# 2. BomResolver
# =====================================================================
class BomResolver:
    """Trasforma (L, H, tipologia, n_ante, config) in componenti + quantità.

    Milestone 4 — Enerhia Operating Core:
    Supporta ora WINDOW_1_SASH, WINDOW_2_SASH, DOOR_WINDOW_1_SASH,
    DOOR_WINDOW_2_SASH, VASISTAS_ONLY_1_SASH.
    SLIDING_DOOR_WINDOW: solo hardware (formula geometrica in backlog).

    Formule V1_3 approvate:
      - MEETING_STILE     = H/1000 × 5.50 × qty         (SASH scambio battuta)
      - THRESHOLD DW_1    = H/1000 × 29.50 + 7.49        (soglia ribassata portafinestra 1 anta)
      - THRESHOLD DW_2    = H/1000 × 29.50 + 9.84        (soglia ribassata portafinestra 2 ante)
      - FIXED_MULLION     = H/1000 × 7.51 × qty
      - TRANSOM           = L/1000 × 7.50 × qty
      - FOIL SURCHARGE    = +10% su PVC eleggibile (FRAME/SASH/GLAZING_BEAD/MEETING_STILE/FIXED_MULLION/TRANSOM)
    """

    def __init__(self, db):
        self.db = db

    async def resolve(self, req: PricingRequest, ps: ProfileSystemResolution) -> BomResolution:
        rc = ps.recipe_code
        L, H, S = req.width_mm, req.height_mm, req.weld_allowance_mm
        n_sashes = int(req.number_of_sashes)

        supported = {
            "WINDOW_1_SASH", "WINDOW_2_SASH",
            "DOOR_WINDOW_1_SASH", "DOOR_WINDOW_2_SASH",
            "VASISTAS_ONLY_1_SASH",
        }
        if rc not in supported:
            raise PricingError(
                "MISSING_TECHNICAL_RECIPE",
                configuration={"recipe_code": rc},
                hint=f"M4 supporta {sorted(supported)}. {rc} nel backlog Fase 4B.",
            )

        components: List[BomComponent] = []

        # === Profili base (comuni a tutte le tipologie con anta) ===
        # FRAME (perimetro esterno)
        components.append(BomComponent(
            role="FRAME",
            component_code="FRAME_PROEVOLUTION",
            quantity_formula=f"2*(L+S) + 2*(H+S) [L={L},H={H},S={S}]",
            quantity_value=frame_ml_1sash(L, H, S),
            unit_of_measure="ml",
            is_pvc_eligible=True,
        ))
        components.append(BomComponent(
            role="FRAME_REINFORCEMENT",
            component_code="FRAME_REINFORCEMENT_PROEVOLUTION",
            quantity_formula=f"2*(L-70) + 2*(H-70) [L={L},H={H}]",
            quantity_value=frame_reinforcement_ml_1sash(L, H),
            unit_of_measure="ml",
            is_pvc_eligible=False,
        ))

        # === SASH / SASH_REINFO / GLAZING_BEAD ===
        # Per ricette con >1 anta, l'anta si sviluppa su n moduli. Modello semplificato:
        # sash_perimeter_total = n_sashes × perimetro anta 1-anta (approssimazione geometrica V1_3).
        sash_ml_per_sash = sash_ml_1sash(L // max(n_sashes, 1), H) if n_sashes >= 1 else Decimal(0)
        # Per WINDOW/DOOR_WINDOW N-ante V1_3 usa perimetro anta calcolato su singola larghezza modulo.
        # In assenza di formula ufficiale diversa, applichiamo il perimetro sash 1-anta standard.
        if rc.endswith("_1_SASH") or rc.endswith("_ONLY_1_SASH"):
            sash_qty = sash_ml_1sash(L, H)
            sash_reinfo_qty = sash_reinforcement_ml_1sash(L, H)
        else:
            # 2 ante: perimetro totale ante ≈ 2 × perimetro modulo(L/2, H)
            module_L = L // 2
            sash_qty = Decimal(2) * sash_ml_1sash(module_L, H)
            sash_reinfo_qty = Decimal(2) * sash_reinforcement_ml_1sash(module_L, H)

        components.append(BomComponent(
            role="SASH",
            component_code="SASH_PROEVOLUTION",
            quantity_formula=f"perimeter_sashes(n={n_sashes})",
            quantity_value=sash_qty,
            unit_of_measure="ml",
            is_pvc_eligible=True,
        ))
        components.append(BomComponent(
            role="SASH_REINFORCEMENT",
            component_code="SASH_REINFORCEMENT_PROEVOLUTION",
            quantity_formula=f"perimeter_sash_reinfo(n={n_sashes})",
            quantity_value=sash_reinfo_qty,
            unit_of_measure="ml",
            is_pvc_eligible=False,
        ))
        components.append(BomComponent(
            role="GLAZING_BEAD",
            component_code="GLAZING_BEAD_PROEVOLUTION",
            quantity_formula=f"sash_perimeter(n={n_sashes})",
            quantity_value=sash_qty,
            unit_of_measure="ml",
            is_pvc_eligible=True,
            notes="Placeholder 2.10 €/ml — NEEDS_PO_CONFIRMATION per listino Enerhia reale.",
        ))

        # === MEETING_STILE (solo n_sashes > 1) — V1_3: H/1000 × 5.50 ===
        if n_sashes > 1:
            ms_qty = Decimal(H) / Decimal(1000)   # ml (unit_cost 5.50 €/ml → letto da listino)
            components.append(BomComponent(
                role="MEETING_STILE",
                component_code="MEETING_STILE_PROEVOLUTION",
                quantity_formula=f"H/1000 [H={H}] × qty",
                quantity_value=ms_qty,
                unit_of_measure="ml",
                is_pvc_eligible=True,
            ))

        # === THRESHOLD (solo DOOR_WINDOW) — V1_3 soglia ribassata ===
        # DW_1: H/1000 × 29.50 + 7.49
        # DW_2: H/1000 × 29.50 + 9.84
        if rc.startswith("DOOR_WINDOW_"):
            variable = Decimal(H) / Decimal(1000)   # ml (unit_cost 29.50 €/ml)
            fixed_part = Decimal("7.49") if rc == "DOOR_WINDOW_1_SASH" else Decimal("9.84")
            components.append(BomComponent(
                role="THRESHOLD",
                component_code="REDUCED_THRESHOLD_PROEVOLUTION",
                quantity_formula=f"variable=H/1000, fixed={fixed_part} € [H={H}]",
                quantity_value=variable,
                unit_of_measure="ml",
                is_pvc_eligible=False,
                notes=f"Costo variabile H/1000 × unit_cost + costo fisso {fixed_part} €",
            ))
            components.append(BomComponent(
                role="THRESHOLD_FIXED_COMPONENT",
                component_code="REDUCED_THRESHOLD_FIXED_PROEVOLUTION",
                quantity_formula=f"fixed {fixed_part} €",
                quantity_value=Decimal(1),
                unit_of_measure="pz",
                is_pvc_eligible=False,
            ))

        # Vetro
        if rc == "VASISTAS_ONLY_1_SASH" or rc.endswith("_1_SASH"):
            gd = glass_dimensions_1sash(L, H)
            real = glass_real_area_sqm(gd["width_mm"], gd["height_mm"])
            billable = glass_billable_area_sqm(gd["width_mm"], gd["height_mm"])
            gd_out = {**gd, "real_area_sqm": float(real), "billable_area_sqm": float(billable)}
        else:
            # 2 ante: due lastre modulo(L/2)
            module_L = L // 2
            gd_single = glass_dimensions_1sash(module_L, H)
            real = glass_real_area_sqm(gd_single["width_mm"], gd_single["height_mm"])
            billable = glass_billable_area_sqm(gd_single["width_mm"], gd_single["height_mm"])
            gd_out = {
                "width_mm": gd_single["width_mm"],
                "height_mm": gd_single["height_mm"],
                "quantity": 2,
                "real_area_sqm": float(real * 2),
                "billable_area_sqm": float(billable * 2),
            }

        return BomResolution(
            components=components,
            glass_dimensions=gd_out,
            hardware_role=rc,   # useremo (window_type, n_sashes) nel TechnicalCostResolver
            production_time_hours=None,  # letto dal resolver via production_time_configs
        )


# =====================================================================
# 3. TechnicalCostResolver
# =====================================================================
class TechnicalCostResolver:
    """Costo industriale del serramento.

    Input: BOM risolta + prezzi listino + workshop_cost + configurazione colore.
    Output: TechnicalSnapshot con dettaglio completo.

    Fail-closed:
      MISSING_COMPONENT_PRICE
      MISSING_GLASS_PRICE
      MISSING_HARDWARE_PRICE
      MISSING_PRODUCTION_TIME
      MISSING_WORKSHOP_COST
    """

    def __init__(self, db):
        self.db = db

    async def _load_workshop_cost(self, tenant_id: str) -> Decimal:
        """Legge hourly_workshop_cost dalla nuova collection versionata."""
        doc = await self.db.workshop_cost_configs.find_one({
            "tenant_id": tenant_id, "active": True, "deleted_at": None,
        })
        if not doc or doc.get("hourly_workshop_cost") is None:
            raise PricingError(
                "MISSING_WORKSHOP_COST",
                configuration={"tenant_id": tenant_id},
                hint="Configurazione tecnica → Costo officina — imposta hourly_workshop_cost (V1_3: 180 €/h)",
            )
        return Decimal(str(doc["hourly_workshop_cost"]))

    async def _load_component_price(self, tenant_id: str, component_code: str,
                                      role: str) -> Decimal:
        """Cerca prezzo componente nel listino tecnico. Fallback: prezzi V1_3 di riferimento."""
        # 1) Listino tenant
        pl = await self.db.item_pricelists.find_one({
            "tenant_id": tenant_id, "active": True, "deleted_at": None,
        }, sort=[("version", -1)])
        if pl:
            for entry in (pl.get("entries") or []):
                if entry.get("code") == component_code:
                    p = entry.get("unit_price")
                    if p is not None:
                        return Decimal(str(p))
        # 2) Fallback V1_3 (riferimento normativo, non seed)
        v13 = V1_3_COMPONENT_PRICES.get(component_code)
        if v13 is not None:
            return v13
        raise PricingError(
            "MISSING_COMPONENT_PRICE",
            component_role=role,
            configuration={"component_code": component_code, "tenant_id": tenant_id},
            hint=f"Configurazione tecnica → Listino componenti — aggiungi {component_code}",
        )

    async def _load_glass_price(self, tenant_id: str, glass_type: str) -> Dict[str, Decimal]:
        """Legge prezzo vetro + min_billable_sqm dalla collection versionata.
        Fallback fail-closed su MISSING_GLASS_PRICE.
        """
        doc = await self.db.glass_price_configs.find_one({
            "tenant_id": tenant_id, "glass_type": glass_type,
            "active": True, "deleted_at": None,
        })
        if doc and doc.get("unit_price_per_sqm") is not None:
            return {
                "price": Decimal(str(doc["unit_price_per_sqm"])),
                "min_sqm": Decimal(str(doc.get("min_billable_sqm", "0.5"))),
                "version": int(doc.get("version", 1)),
            }
        # Fallback su costanti V1_3 (documentate ma NON hardcoded per il tenant)
        try:
            p = glass_price_per_sqm(glass_type)
            return {"price": p, "min_sqm": Decimal("0.5"), "version": 0}
        except KeyError:
            raise PricingError(
                "MISSING_GLASS_PRICE",
                component_role="GLASS",
                configuration={"glass_type": glass_type, "tenant_id": tenant_id},
                hint="Configurazione tecnica → Vetri — imposta il prezzo del vetro",
            )

    async def _load_hardware_price(self, tenant_id: str, opening_type: str,
                                     n_sashes: int) -> Dict[str, Decimal]:
        """Legge la regola ferramenta dalla collection versionata.
        Match esatto per (opening_type, number_of_sashes) o wildcard n_sashes=None
        (per SLIDING_DOOR_WINDOW che è per_sash).
        Fail-closed su MISSING_HARDWARE_RULE.
        """
        # 1) match esatto per anta
        doc = await self.db.hardware_rules.find_one({
            "tenant_id": tenant_id,
            "opening_type": opening_type,
            "number_of_sashes": n_sashes,
            "active": True, "deleted_at": None,
        })
        # 2) fallback su regola "per anta" (number_of_sashes=None)
        if not doc:
            doc = await self.db.hardware_rules.find_one({
                "tenant_id": tenant_id,
                "opening_type": opening_type,
                "number_of_sashes": None,
                "per_sash": True,
                "active": True, "deleted_at": None,
            })
        if not doc:
            raise PricingError(
                "MISSING_HARDWARE_RULE",
                component_role="HARDWARE",
                configuration={"opening_type": opening_type, "number_of_sashes": n_sashes,
                                "tenant_id": tenant_id},
                hint=(f"Configurazione tecnica → Ferramenta — aggiungi regola per "
                       f"{opening_type} con {n_sashes} anta/e"),
            )
        cost = Decimal(str(doc.get("cost_per_unit", 0)))
        per_sash = bool(doc.get("per_sash", False))
        total = cost * Decimal(n_sashes) if per_sash else cost
        return {
            "total": total,
            "unit_cost": cost,
            "per_sash": per_sash,
            "version": int(doc.get("version", 1)),
        }

    async def _load_production_time(self, tenant_id: str, recipe_code: str) -> Decimal:
        """Legge il tempo produzione dalla collection versionata.
        Fallback su costanti V1_3 documentate.
        Fail-closed su MISSING_PRODUCTION_TIME.
        """
        doc = await self.db.production_time_configs.find_one({
            "tenant_id": tenant_id, "recipe_code": recipe_code,
            "active": True, "deleted_at": None,
        })
        if doc and doc.get("hours") is not None:
            return Decimal(str(doc["hours"]))
        # Fallback: costanti V1_3
        from .formulas import PRODUCTION_TIME_HOURS
        v = PRODUCTION_TIME_HOURS.get(recipe_code)
        if v and v > 0:
            return v
        raise PricingError(
            "MISSING_PRODUCTION_TIME",
            configuration={"recipe_code": recipe_code, "tenant_id": tenant_id},
            hint=f"Configurazione tecnica → Tempi produzione — aggiungi {recipe_code}",
        )

    async def _foil_applicable(self, req: PricingRequest) -> bool:
        from app.services.color_engine import resolve_window_color, window_foil_surcharge_applicable
        cats = {}
        for side, code in (("internal", req.color_internal), ("external", req.color_external)):
            try:
                cats[side] = (await resolve_window_color(self.db, req.tenant_id, code))["category"]
            except ValueError:
                raise PricingError("UNKNOWN_COLOR_CODE", configuration={"side": side, "color_code": code},
                                   hint="Colore non presente nel catalogo product_colors — selezionare un codice valido (es. 003 BIANCO MASSA)")
        try:
            return window_foil_surcharge_applicable(cats["internal"], cats["external"])
        except ValueError:
            raise PricingError("NEEDS_PO_PRICING", configuration={"color_internal": req.color_internal, "color_external": req.color_external},
                               hint="Colore SPECIAL: nessuna policy economica V1 definita dal PO per il pellicolato speciale")

    async def resolve(self, req: PricingRequest, ps: ProfileSystemResolution,
                       bom: BomResolution) -> TechnicalSnapshot:
        # Tempo produzione (config-based, fail-closed)
        prod_hours = await self._load_production_time(req.tenant_id, ps.recipe_code)
        bom.production_time_hours = prod_hours

        hourly = await self._load_workshop_cost(req.tenant_id)

        # Materiali (profili + rinforzi + fermavetro)
        material_cost = Decimal("0")
        components_snapshot: List[Dict[str, Any]] = []
        foil_pvc_base = Decimal("0")   # base per pellicolato +10%

        for c in bom.components:
            # THRESHOLD_FIXED_COMPONENT è un valore fisso € (parte fissa soglia ribassata):
            #   DW_1: 7.49 €, DW_2: 9.84 €. Non richiede listino.
            if c.role == "THRESHOLD_FIXED_COMPONENT":
                # Recupera dal quantity_formula: già encoded il fixed_part nella notes precedente.
                # Convenzione: quantity_value=1, unit_cost = fixed_part
                # Determiniamo il fixed_part dal recipe code
                fixed_part = Decimal("7.49") if ps.recipe_code == "DOOR_WINDOW_1_SASH" else Decimal("9.84")
                price = fixed_part
                total = price   # qty=1 pz
                c.unit_cost = price
                c.total_cost = total
                material_cost += total
                components_snapshot.append({
                    "role": c.role,
                    "component_code": c.component_code,
                    "quantity_formula": c.quantity_formula,
                    "quantity_value": str(c.quantity_value),
                    "unit_of_measure": c.unit_of_measure,
                    "unit_cost": str(price),
                    "total_cost": str(total),
                    "waste_pct": str(c.waste_pct),
                    "is_pvc_eligible": c.is_pvc_eligible,
                })
                continue

            price = await self._load_component_price(req.tenant_id, c.component_code, c.role)
            total = c.quantity_value * price
            c.unit_cost = price
            c.total_cost = total
            material_cost += total
            if c.is_pvc_eligible:
                foil_pvc_base += total
            components_snapshot.append({
                "role": c.role,
                "component_code": c.component_code,
                "quantity_formula": c.quantity_formula,
                "quantity_value": str(c.quantity_value),
                "unit_of_measure": c.unit_of_measure,
                "unit_cost": str(price),
                "total_cost": str(total),
                "waste_pct": str(c.waste_pct),
                "is_pvc_eligible": c.is_pvc_eligible,
            })

        # Vetro (config-based)
        glass_cfg = await self._load_glass_price(req.tenant_id, req.glass_type)
        glass_price = glass_cfg["price"]
        min_sqm = glass_cfg["min_sqm"]
        gd = bom.glass_dimensions or {}
        # Ricalcolo billable con min dinamico
        real_sqm = Decimal(str(gd.get("real_area_sqm", 0)))
        billable = max(real_sqm, min_sqm)
        gd["min_billable_sqm"] = float(min_sqm)
        gd["billable_area_sqm"] = float(billable)
        glass_cost = billable * glass_price * Decimal(gd.get("quantity", 1))

        # Ferramenta (config-based)
        hw = await self._load_hardware_price(req.tenant_id, req.window_type, req.number_of_sashes)
        hardware_cost = hw["total"]

        # Manodopera
        labor_cost = bom.production_time_hours * hourly

        # Pellicolato +10% (P0 msg 625 §6-§10): codici catalogo product_colors.
        # 003 = BIANCO MASSA -> nessun surcharge. STANDARD -> +10% solo su base PVC eleggibile,
        # una sola volta anche se pellicolato due lati. SPECIAL -> NEEDS_PO_PRICING (fail closed).
        foil_surcharge = Decimal("0")
        if await self._foil_applicable(req):
            foil_surcharge = foil_pvc_base * (STANDARD_FOIL_SURCHARGE_PERCENT / Decimal("100"))

        total_internal = (material_cost + glass_cost + hardware_cost
                          + labor_cost + foil_surcharge)

        return TechnicalSnapshot(
            profile_system_id=ps.profile_system_id,
            profile_system_version=ps.profile_system_version,
            technical_recipe_id=ps.technical_recipe_id,
            technical_recipe_version=ps.technical_recipe_version,
            hourly_workshop_cost=hourly,
            production_time_hours=bom.production_time_hours,
            components=components_snapshot,
            glass_dimensions=gd,
            material_cost=material_cost,
            glass_cost=glass_cost,
            hardware_cost=hardware_cost,
            additional_technical_costs=Decimal("0"),
            labor_cost=labor_cost,
            foil_surcharge=foil_surcharge,
            total_internal_cost=total_internal,
        )


# =====================================================================
# 4. CommercialPricingService
# =====================================================================
class CommercialPricingService:
    """Applica la regola commerciale al costo tecnico.

    NON conosce telaio, anta, vetro, rinforzo, ferramenta, BOM.
    Riceve solo: technical_internal_cost + commercial_pricing_rule.

    Metodi supportati:
      - MULTIPLIER: sale = cost × multiplier
      - MARKUP_ON_COST: sale = cost × (1 + markup/100)
      - TARGET_GROSS_MARGIN: sale = cost / (1 - margin/100)
      - FIXED_PRICE: sale = fixed_price
    """

    def __init__(self, db):
        self.db = db

    async def _load_rule(self, tenant_id: str) -> Dict[str, Any]:
        doc = await self.db.commercial_pricing_rules.find_one({
            "tenant_id": tenant_id, "active": True, "deleted_at": None,
        }, sort=[("version", -1)])
        if not doc:
            raise PricingError(
                "MISSING_COMMERCIAL_MULTIPLIER",
                configuration={"tenant_id": tenant_id},
                hint="Configurazione tecnica → Regola commerciale — imposta il moltiplicatore",
            )
        return doc

    async def apply(self, req: PricingRequest, tech: TechnicalSnapshot) -> CommercialSnapshot:
        rule = await self._load_rule(req.tenant_id)
        method = rule.get("method", "MULTIPLIER").upper()
        cost = tech.total_internal_cost

        cs = CommercialSnapshot(pricing_method=method, rule_version=int(rule.get("version", 1)))

        if req.override_multiplier is not None:
            method = "MULTIPLIER"
            cs.pricing_method = "MULTIPLIER"
            cs.multiplier = Decimal(str(req.override_multiplier))
        elif method == "MULTIPLIER":
            m = rule.get("multiplier")
            if m is None:
                raise PricingError("MISSING_COMMERCIAL_MULTIPLIER",
                                    configuration={"method": method},
                                    hint="Regola commerciale senza campo `multiplier`")
            cs.multiplier = Decimal(str(m))
        elif method == "MARKUP_ON_COST":
            cs.markup_pct = Decimal(str(rule.get("markup_pct")))
        elif method == "TARGET_GROSS_MARGIN":
            cs.gross_margin_pct = Decimal(str(rule.get("gross_margin_pct")))
        elif method == "FIXED_PRICE":
            cs.fixed_price = Decimal(str(rule.get("fixed_price")))
        else:
            raise PricingError("INVALID_CONFIGURATION",
                                configuration={"method": method},
                                hint="Regola commerciale: metodo non supportato")

        # Calcolo
        if method == "MULTIPLIER":
            cs.unit_sale_price = cost * cs.multiplier
        elif method == "MARKUP_ON_COST":
            cs.unit_sale_price = cost * (Decimal(1) + cs.markup_pct / Decimal(100))
        elif method == "TARGET_GROSS_MARGIN":
            denom = Decimal(1) - cs.gross_margin_pct / Decimal(100)
            if denom <= 0:
                raise PricingError("INVALID_CONFIGURATION",
                                    configuration={"gross_margin_pct": str(cs.gross_margin_pct)},
                                    hint="gross_margin_pct >= 100 non valido")
            cs.unit_sale_price = cost / denom
        elif method == "FIXED_PRICE":
            cs.unit_sale_price = cs.fixed_price

        # Sconti/promozioni: Fase 1 non li supporta ancora (discount=0)
        cs.discount = Decimal("0")
        cs.final_unit_price = cs.unit_sale_price - cs.discount

        return cs
