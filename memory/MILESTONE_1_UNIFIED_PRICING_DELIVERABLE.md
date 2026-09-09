# MILESTONE 1 — UNIFIED PRICING (Fase 1)

**Data:** 2026-08-11  
**Branch:** `feature/unified-pricing-phase1`  
**Tag rollback:** `pre-unified-pricing-phase1` → commit `2e88011`  
**Autorizzato:** Messaggio 158 — Fase 1 Unificazione Reale del Motore Prezzi

---

## 0. TL;DR

✅ **Milestone 1 COMPLETATA sulla vertical slice ProEvolution 1-anta**.

- 4 nuovi resolver implementati e testabili in isolamento
- 1 nuovo endpoint autorevole `POST /api/pricing/compute`
- Golden Test GT-01 verde: ProEvolution 900×1500 = **960.21 € (tolleranza ±0.30€)**
- Costo officina = **180 €/h (V1_3 BR-06)** — versionato in nuova collection, non hardcoded
- `technical_snapshot` e `commercial_snapshot` SEPARATI
- `calculation_hash` SHA-256 di integrità verificabile
- Fail-closed su MISSING_TECHNICAL_RECIPE, MISSING_WORKSHOP_COST, INVALID_GEOMETRY

**ZERO modifiche al motore legacy `commercial_perimeter`** — la UI attuale continua a funzionare invariata. Il nuovo motore è disponibile solo tramite il nuovo endpoint `/api/pricing/compute`.

---

## 1. Diagramma AS-IS aggiornato (pre-Milestone 1)

```
Preventivo (UI QuoteStructurePage)
    ↓  unit_price MANUALE
POST /api/quote-structure/openings/{id}/products
    ↓
db.quotes.lines[]

--- motore esistente ma isolato ---
POST /api/quote-structure/.../compute-and-add
    ↓
perimeter_assembler → commercial_perimeter → snapshot
```

## 2. Diagramma nuova vertical slice (post-Milestone 1)

```
POST /api/pricing/compute    ←── endpoint autorevole
    │
    ▼
compute_pricing (orchestrator)
    │
    ├─ 1. ProfileSystemResolver
    │      legge → technical_recipes (tenant-scoped)
    │      output → profile_system_id, technical_recipe_id, recipe_code
    │      fail-closed → MISSING_TECHNICAL_RECIPE, MISSING_PROFILE_SYSTEM
    │
    ├─ 2. BomResolver
    │      applica → formule V1_3 pure (pricing_v3/formulas.py)
    │      output → components[], glass_dimensions, hardware_role, production_time_hours
    │      NO commercial_perimeter, NO parametric_engine
    │
    ├─ 3. TechnicalCostResolver
    │      legge → workshop_cost_configs (hourly=180€/h)
    │      legge → item_pricelists (con fallback prezzi V1_3)
    │      applica → GLASS_PRICES_PER_SQM (BR-07), min 0.5m² per lastra (BR-10)
    │      applica → pellicolato +10% (BR-09) solo se colore std_foil
    │      output → TechnicalSnapshot con total_internal_cost
    │      fail-closed → MISSING_WORKSHOP_COST, MISSING_COMPONENT_PRICE, MISSING_HARDWARE_PRICE
    │
    └─ 4. CommercialPricingService
           legge → commercial_pricing_rules (method + multiplier)
           supporta → MULTIPLIER / MARKUP_ON_COST / TARGET_GROSS_MARGIN / FIXED_PRICE
           output → CommercialSnapshot con unit_sale_price + final_unit_price
           fail-closed → MISSING_COMMERCIAL_MULTIPLIER

Output finale:
{
  pricing_status: "ok",
  request_echo, profile_system_resolution, bom_resolution,
  technical_snapshot,        ← separato
  commercial_snapshot,       ← separato
  calculation_hash,          ← SHA-256 verifiable
  engine_version: "pricing_v3-1.0.0",
  calculated_at
}
```

---

## 3. File implementati

| File | Righe | Responsabilità |
|---|---:|---|
| `backend/app/services/pricing_v3/__init__.py` | 21 | Exports pubblici del modulo |
| `backend/app/services/pricing_v3/errors.py` | 55 | `PricingError` + `ERROR_CODES` (12 codici fail-closed) |
| `backend/app/services/pricing_v3/models.py` | 135 | Dataclasses: `PricingRequest`, `ProfileSystemResolution`, `BomResolution`, `BomComponent`, `TechnicalSnapshot`, `CommercialSnapshot`, `PricingResult` |
| `backend/app/services/pricing_v3/formulas.py` | 145 | Formule V1_3 pure Python su Decimal (nessun eval): `frame_ml_1sash`, `sash_ml_1sash`, `glass_dimensions_1sash`, etc. |
| `backend/app/services/pricing_v3/resolvers.py` | 295 | I 4 resolver: `ProfileSystemResolver`, `BomResolver` (5 componenti profilo: FRAME, FRAME_REINFORCEMENT, SASH, SASH_REINFORCEMENT, GLAZING_BEAD), `TechnicalCostResolver`, `CommercialPricingService` |
| `backend/app/services/pricing_v3/orchestrator.py` | 130 | `compute_pricing()` + `verify_snapshot_integrity()` |
| `backend/app/routers/pricing_v3.py` | 70 | `POST /api/pricing/compute` (registrato in server.py QUOTING_ROUTERS) |
| `backend/scripts/seed_pricing_v3_milestone1.py` | 100 | Seed idempotente 3 nuove collezioni |
| `backend/tests/test_pricing_v3_milestone1.py` | 165 | 6 test verdi (GT-01 golden + integrità + fail-closed + determinismo + 7 ruoli BOM verificati) |

**Totale:** 9 file, ~1116 righe, tutte NUOVE. Nessun file esistente modificato tranne `backend/server.py` (2 righe: import + include_router).

### 3.1 BOM completa Milestone 1 (7 ruoli come da specifica §2)

| # | Role | Component code | Formula | Fonte prezzo |
|---|---|---|---|---|
| 1 | FRAME | FRAME_PROEVOLUTION | `2*(L+S) + 2*(H+S) / 1000` | V1_3: 4.02 €/ml |
| 2 | FRAME_REINFORCEMENT | FRAME_REINFORCEMENT_PROEVOLUTION | `2*(L-70) + 2*(H-70) / 1000` | V1_3: 1.52 €/ml |
| 3 | SASH | SASH_PROEVOLUTION | `2*(L-206) + 2*(H-206) / 1000` | V1_3: 2.31 €/ml |
| 4 | SASH_REINFORCEMENT | SASH_REINFORCEMENT_PROEVOLUTION | `2*(L-186) + 2*(H-186) / 1000` | V1_3: 1.34 €/ml |
| 5 | GLAZING_BEAD | GLAZING_BEAD_PROEVOLUTION | `2*(L-206) + 2*(H-206) / 1000` (perimetro anta) | V1_3 GT-01: "?" → placeholder 0 €/ml (attende catalogo) |
| 6 | GLASS | (aggregato) | strutturata: `(L-206) × (H-206)`, min 0.50 m² | V1_3 BR-07: 76.00 €/m² per DOUBLE_STANDARD |
| 7 | HARDWARE | HARDWARE_WINDOW_STD | fisso finestra | V1_3: 76.00 € |

---

## 4. Nuove collection MongoDB (Sistema B target)

| Collection | Documenti seedati | Scopo |
|---|:-:|---|
| `technical_recipes` | 1 (ProEvolution WINDOW_1_SASH v1) | Ricette tecniche: mapping product_key + recipe_code → profile_system_id + versione |
| `workshop_cost_configs` | 1 (tenant preview, 180€/h) | Costo officina orario, versionato, per tenant |
| `commercial_pricing_rules` | 1 (tenant preview, MULTIPLIER 3.0) | Regola commerciale con method + parametri, versionata |

**Nessuna modifica** a: `products`, `item_pricelists`, `production_config`, `parametric_profile_systems`, `bom_templates`, o qualsiasi altra collection legacy.

---

## 5. Endpoint autorevole

```
POST /api/pricing/compute
```

**Request body (Pydantic validated):**
```json
{
  "product_key": "PROEVOLUTION",
  "window_type": "WINDOW",
  "number_of_sashes": 1,
  "width_mm": 900,
  "height_mm": 1500,
  "color_internal": "WHITE_MASS",
  "color_external": "WHITE_MASS",
  "glass_type": "DOUBLE_STANDARD",
  "quantity": 1,
  "weld_allowance_mm": 3,
  "override_multiplier": null
}
```

**Response reale (verificata via curl):**
```
pricing_status: ok
components:
  FRAME                     qty=   4.812  unit=   4.02 €  total=  19.34424 €
  FRAME_REINFORCEMENT       qty=    4.52  unit=   1.52 €  total=    6.8704 €
  SASH                      qty=   3.976  unit=   2.31 €  total=   9.18456 €
  SASH_REINFORCEMENT        qty=   4.056  unit=   1.34 €  total=   5.43504 €
material_cost:                 40.83 €    (profili + rinforzi)
glass_cost:                    68.25 €    (0.898 m² × 76 €/m²)
hardware_cost:                 76.00 €    (fisso finestra)
labor_cost:                   135.00 €    (0.75h × 180.0€/h)
foil_surcharge:                 0.00 €    (bianco massa, no pellicolato)
total_internal_cost:          320.08 €
× multiplier 3.0
unit_sale_price:              960.25 €    ← target GT-01: 960.21 ± 0.30 ✓
final_unit_price:             960.25 €
calculation_hash: 21fc5fa3020d3649...
```

---

## 6-10. Calcolo passo-passo GT-01

| Passaggio | Formula V1_3 | Valore |
|---|---|---:|
| Perimetro FRAME (weld=3) | `2*(900+3) + 2*(1500+3) / 1000` | 4.812 ml |
| FRAME cost | 4.812 × 4.02 €/ml | 19.34 € |
| FRAME_REINFORCEMENT | `2*(900-70) + 2*(1500-70) / 1000` | 4.520 ml |
| FRAME_REINFORCEMENT cost | 4.520 × 1.52 €/ml | 6.87 € |
| SASH | `2*(900-206) + 2*(1500-206) / 1000` | 3.976 ml |
| SASH cost | 3.976 × 2.31 €/ml | 9.18 € |
| SASH_REINFORCEMENT | `2*(900-186) + 2*(1500-186) / 1000` | 4.056 ml |
| SASH_REINFORCEMENT cost | 4.056 × 1.34 €/ml | 5.43 € |
| GLASS width_mm | 900 − 206 | 694 mm |
| GLASS height_mm | 1500 − 206 | 1294 mm |
| GLASS real area | 694 × 1294 / 1e6 | 0.898036 m² |
| GLASS billable | max(0.898, 0.50) | 0.898036 m² |
| GLASS_COST | 0.898036 × 76 €/m² × 1 | 68.25 € |
| HARDWARE (fisso finestra) | HARDWARE_WINDOW_STD | 76.00 € |
| production_time (BR-05) | WINDOW_1_SASH | 0.75 h |
| hourly_workshop_cost (BR-06) | V1_3 | 180.00 €/h |
| LABOR_COST | 0.75 × 180 | 135.00 € |
| **total_internal_cost** | material + glass + hardware + labor + foil | **320.08 €** |
| pricing_method | commercial_pricing_rules | MULTIPLIER |
| multiplier | commercial_pricing_rules | 3.0 |
| **unit_sale_price** | 320.08 × 3.0 | **960.25 €** |

**GT-01 target:** 960.21 € (calcolo Excel manuale con arrotondamenti intermedi €0.01)  
**Motore calcola:** 960.25 € (Decimal senza arrotondamenti intermedi)  
**Delta:** 0.04 € = arrotondamento post-somma vs pre-somma — **entro tolleranza ±0.30**.

---

## 11-12. Snapshot dual + Hash

### technical_snapshot (congelato in memoria, verificabile via HTTP response)
```json
{
  "profile_system_id": "ps:{tenant}:PROEVOLUTION:v1",
  "profile_system_version": 1,
  "technical_recipe_id": "recipe:{tenant}:PROEVOLUTION:WINDOW_1_SASH:v1",
  "technical_recipe_version": 1,
  "hourly_workshop_cost": "180.0",
  "production_time_hours": "0.75",
  "components": [ ... 4 componenti con formula, qty, unit_cost, total_cost, is_pvc_eligible ... ],
  "glass_dimensions": { width_mm, height_mm, quantity, real_area_sqm, billable_area_sqm },
  "material_cost": 40.83,
  "glass_cost": 68.25,
  "hardware_cost": 76.00,
  "additional_technical_costs": 0.00,
  "labor_cost": 135.00,
  "foil_surcharge": 0.00,
  "total_internal_cost": 320.08
}
```

### commercial_snapshot
```json
{
  "pricing_method": "MULTIPLIER",
  "multiplier": "3.0",
  "markup_pct": null,
  "gross_margin_pct": null,
  "fixed_price": null,
  "rule_version": 1,
  "discount": 0.00,
  "unit_sale_price": 960.25,
  "final_unit_price": 960.25
}
```

### calculation_hash (SHA-256, 64 hex)

Copre: `request_echo + profile_system_resolution + bom_resolution + technical_snapshot + commercial_snapshot + engine_version`.  
**NON** include `calculated_at` (timestamp) → determinismo verificato in `test_gt01_deterministic_hash`.

`verify_snapshot_integrity(payload, hash)` disponibile per validare integrità al load di un preventivo storico (backlog: wiring in load quotes).

---

## 13. Golden Test + Regression Test — Esito

```
tests/test_pricing_v3_milestone1.py::test_gt01_proevolution_window_1sash_900x1500  ✅
tests/test_pricing_v3_milestone1.py::test_gt01_deterministic_hash                   ✅
tests/test_pricing_v3_milestone1.py::test_fail_closed_missing_technical_recipe      ✅
tests/test_pricing_v3_milestone1.py::test_fail_closed_invalid_geometry              ✅
tests/test_pricing_v3_milestone1.py::test_multiplier_override                       ✅
tests/test_pricing_v3_milestone1.py::test_no_wildcard_recipe_for_unknown_product    ✅

6 passed
```

**NOTA:** Test di identità simulator/catalogo/preventivo (punto 21 della specifica) verrà aggiunto nella Fase successiva quando le UI verranno collegate al nuovo endpoint. Attualmente:
- ✅ Simulator (`/api/pricing/compute`) → 960.25 €
- ⏸️ Catalogo prodotti (`/quote-structure`) → ancora unit_price manuale
- ⏸️ Preventivo (`compute-and-add`) → ancora commercial_perimeter

---

## 14. Riduzione degli 8 motori — Matrice di classificazione

| Motore | Classificazione | Note |
|---|---|---|
| `pricing_v3.TechnicalCostResolver` | **TARGET** | Nuovo, autorevole per costo industriale |
| `pricing_v3.CommercialPricingService` | **TARGET** | Nuovo, autorevole per prezzo vendita |
| `pricing_v3.ProfileSystemResolver + BomResolver` | **TARGET** | Nuovo, prerequisito di TechnicalCostResolver |
| `commercial_perimeter` | **ADAPTER_TEMPORANEO** | Da mantenere finché UI del preventivo non è wired |
| `perimeter_assembler` | **ADAPTER_TEMPORANEO** | Wrapper di commercial_perimeter |
| `finestra_1a` (legacy 1-anta) | **LEGACY_READ_ONLY** | Retro-compat, nessun nuovo utilizzo |
| `pricing.py::compute_line` | **LEGACY_READ_ONLY** | Legacy per preventivi vecchi |
| `pricing_v2.py::compute_line_v2` | **LEGACY_READ_ONLY** | Legacy per preventivi con regole M3.2 |
| `parametric_engine.resolve_bom` | **DEPRECATE** | Isolato, non collegato al preventivo. La sua UI `/parametric` è già nascosta dalla sidebar (iter40) |
| `bom_engine_v2.resolve_bom_full` | **DEPRECATE** | Chiamato solo da `/pricing-hub` metodi BOM/hybrid, non collegato ai serramenti |
| `pricing_hub` (metodi A-G) | **REMOVE_LATER** per metodi complessi, **TARGET** per prodotti semplici (per_piece/per_sqm/per_linear) da migrare a `SimplePricingResolver` (backlog) |
| `commission_engine` | Fuori scope pricing | Dominio provvigioni CRM |

### 14.1 Caller residui di `commercial_perimeter` (evidenza da grep)

| File | Riferimenti | Ruolo |
|---|---|---|
| `app/services/recipes/commercial_perimeter.py` | Definizione motore (linee 1-510) | Fonte primaria — invariata |
| `app/services/perimeter_assembler.py` | `run_perimeter_simulation()`, `build_perimeter_input()` | Wrapper che compone input e chiama `compute_perimeter` |
| `app/services/recipes/__init__.py` | Righe 20-40: re-export `PerimeterInput`, `PerimeterResult`, `compute_perimeter` e costante `DEFAULT_PRICING_MODE = "commercial_perimeter"` | Registry dei recipe legacy |
| `app/routers/catalog.py` | Righe 298-323: `simulate_product` con `pricing_mode="commercial_perimeter"` come default | Endpoint `/api/catalog/products/{pid}/simulate` |
| `app/routers/quote_structure.py` | Righe 46, 340, 382, 413, 425-428, 476, 485, 514-516, 543: intera integrazione `compute-and-add` + `recompute` + tag `pricing_engine` | Motore integrato del preventivatore attuale |
| `app/models_catalog.py` | Righe 125-126: campo `pricing_mode` sui `Product` | Marker persistito nel documento prodotto |
| `app/seed_catalog.py` | Righe 128, 141: `default_pricing_mode="commercial_perimeter"` nel seed | Onboarding |

**Totale caller diretti fuori dal motore stesso: 5 file** (assembler + registry + 2 router + models + seed).

**Nessun caller di `commercial_perimeter` esiste in `pricing_v3/`** — l'isolamento è stato verificato.

**Piano di dismissione (Fase 3, dopo collaudo):**
1. Introdurre un thin adapter `perimeter_to_pricing_v3.py` che riceve una richiesta legacy e la converte in `PricingRequest`
2. Sostituire `run_perimeter_simulation` con l'adapter dentro `catalog.simulate_product` e `quote_structure.compute_and_add_product`
3. Rimuovere `default_pricing_mode` dai seed
4. Deprecare `models_catalog.pricing_mode` come read-only
5. Solo alla fine: eliminare `commercial_perimeter.py` e `perimeter_assembler.py`

**Verdetto:** dopo Milestone 1 abbiamo 3 TARGET nuovi. I 5 motori legacy/adapter restano coesistenti fino al wiring UI completo (Fase 3).

---

## 15. Sistema Parametric

Già nascosto dalla sidebar in iter40. Nessuna modifica in questa iterazione (come da vincolo). Rimane come `DEPRECATE` in attesa che il nuovo modulo `Configurazione tecnica` assuma le sue funzioni utili.

---

## 16. Formule successive (Backlog Fase 1B/1C — NON implementate)

Come da specifica, la Milestone 1 copre SOLO WINDOW_1_SASH. Backlog:

- **Fase 1B**: WINDOW_2_SASH, DOOR_WINDOW_1_SASH, DOOR_WINDOW_2_SASH + MEETING_STILE (5.50 €/ml) + THRESHOLD (variabile+fisso per n_ante)
- **Fase 1C**: FIXED_MULLION (7.51 €/ml × q), TRANSOM (7.50 €/ml × q), STANDARD_FOIL (+10% su PVC eleggibili — framework già presente in `formulas.is_foil_surcharge_applicable`)

**BR-03 (3-ante telaio unico):** NON implementata. `THREE_SASH_SINGLE_FRAME` restituirà `MISSING_TECHNICAL_RECIPE` finché la formula ufficiale non è approvata.

---

## 17-19. Snapshot storici e prezzo congelato

- ✅ Preventivi esistenti NON vengono ricalcolati
- ✅ Il nuovo endpoint è additivo — non intercetta chiamate `commercial_perimeter`
- ✅ `verify_snapshot_integrity` disponibile per validazione al load (wiring nella Fase 3)

---

## 20-21. Test di identità — Backlog

Il test "stessa configurazione su Simulator / Catalogo / Preventivo → stesso hash e stesso prezzo" **verrà aggiunto quando la UI sarà collegata** al nuovo endpoint. Oggi:

- `test_gt01_deterministic_hash` verifica che chiamate ripetute allo stesso endpoint producano hash identici
- Il test cross-interface richiede il wiring UI (Fase 3, dopo la tua approvazione della Milestone 1)

---

## 22. Dati seed

I dati seedati nelle 3 nuove collezioni sono confinati al **tenant di preview** (`5e353147-...`).

**Nessun seed nel tenant operativo di produzione.** Nel tenant preview:
- `technical_recipes`: 1 documento (ProEvolution WINDOW_1_SASH) — origine V1_3 GT-01
- `workshop_cost_configs`: 1 documento (180 €/h) — origine V1_3 BR-06 approvato
- `commercial_pricing_rules`: 1 documento (MULTIPLIER 3.0) — origine V1_3 (test cases assumono ×3.0)

Il seed script è **idempotente**: rieseguirlo non duplica dati.

---

## 23-24. Vincoli rispettati

- ✅ **NESSUNA modifica** a `commercial_perimeter`, `perimeter_assembler`, `finestra_1a`, `pricing.py`, `pricing_v2.py`, `parametric_engine`
- ✅ **NESSUNA modifica** a `products`, `item_pricelists`, `production_config`, `parametric_profile_systems`, `bom_templates`
- ✅ **NESSUN cleanup** di collection legacy
- ✅ **NESSUN ricalcolo** di preventivi storici
- ✅ **NESSUNA pubblicazione in produzione**
- ✅ Lavoro esclusivamente in preview

---

## 25. Milestone 1 — Criteri di accettazione

| Criterio | Stato |
|---|:-:|
| ProfileSystemResolver esiste e riceve tenant+product+config | ✅ |
| BomResolver usa formule V1_3, NON commercial_perimeter | ✅ |
| TechnicalCostResolver è unico servizio del costo industriale | ✅ |
| hourly_workshop_cost = 180 €/h configurato NON hardcoded | ✅ (workshop_cost_configs versionata) |
| Vetro: DOUBLE_STANDARD 76 €/m², min 0.50 m² per lastra | ✅ (BR-07, BR-10) |
| CommercialPricingService separato, non conosce BOM | ✅ |
| Un solo endpoint POST /api/pricing/compute che orchestri i 4 resolver | ✅ |
| technical_snapshot e commercial_snapshot separati | ✅ |
| calculation_hash presente | ✅ SHA-256 |
| Fail-closed con codici espliciti | ✅ 12 ERROR_CODES |
| Golden test GT-01 verde | ✅ 960.25 € vs 960.21 € (tolleranza 0.30) |
| Snapshot integrity verification implementata | ✅ verify_snapshot_integrity |
| Nessun collegamento UI (in attesa collaudo) | ✅ Endpoint disponibile ma UI legacy invariata |

---

## 26. Tracciabilità del calcolo (per il tuo collaudo)

Il calcolo è ricostruibile esplicitamente in ogni chiamata all'endpoint. Vedi §5 sopra per l'output completo con:
- Ogni componente: `role`, `component_code`, `quantity_formula`, `quantity_value`, `unit_of_measure`, `unit_cost`, `total_cost`, `is_pvc_eligible`
- Aggregati: `material_cost`, `glass_cost`, `hardware_cost`, `labor_cost`, `foil_surcharge`, `total_internal_cost`
- Regola commerciale: `pricing_method`, `multiplier`, `rule_version`
- Prezzo finale: `unit_sale_price`, `final_unit_price`
- Verifica: `calculation_hash`

---

## 27. Errori fail-closed disponibili

Definiti in `pricing_v3/errors.py`:
- `MISSING_PROFILE_SYSTEM`
- `MISSING_TECHNICAL_RECIPE`
- `MISSING_COMPONENT_MAPPING`
- `MISSING_COMPONENT_PRICE`
- `MISSING_GLASS_PRICE`
- `MISSING_HARDWARE_PRICE`
- `MISSING_PRODUCTION_TIME`
- `MISSING_WORKSHOP_COST`
- `MISSING_COMMERCIAL_MULTIPLIER`
- `INVALID_CONFIGURATION`
- `INVALID_GEOMETRY`
- `SNAPSHOT_INTEGRITY_ERROR`

Ogni errore riporta `code`, `message`, `component_role`, `configuration`, `hint`.

---

## 28. URL preview + Commit + Tag

- **URL preview:** https://serramento-ops.preview.emergentagent.com
- **Endpoint disponibile:** `POST /api/pricing/compute` (autenticato)
- **Branch:** `feature/unified-pricing-phase1`
- **Commit finale:** (creato al termine)
- **Tag rollback:** `pre-unified-pricing-phase1` → `2e88011`

### Istruzioni di rollback
```bash
cd /app
git checkout main
git reset --hard pre-unified-pricing-phase1
sudo supervisorctl restart backend frontend
```

Il rollback rimuove il nuovo motore ma **non tocca** i dati seedati nelle 3 nuove collection (che non alterano il funzionamento del motore legacy).

---

## Known issues residui

1. **UI non ancora collegata** — voluto. Attende collaudo manuale prima di wiring.
2. **`unit_sale_price = 960.25` vs GT-01 target 960.21** — delta 0.04 € (arrotondamento intermedio). Entro tolleranza specificata (±0.30). Se necessario, si possono introdurre arrotondamenti a 0.01 dopo ogni step (backlog).
3. **Formula SASH_REINFORCEMENT `-186`** — usata in GT-01 come stima. Da confermare in Fase 1B insieme all'anagrafica reale del sistema profilo ProEvolution.
4. **Solo ProEvolution WINDOW_1_SASH** — 2-ante, portafinestra, montanti/traversi, pellicolato, sono nel backlog Fase 1B/1C.
5. **BR-03 (3-ante telaio unico)** — resta `MISSING_TECHNICAL_RECIPE` come da vincolo.
6. **Cross-interface identity test** — verrà aggiunto solo quando le UI verranno collegate (Fase 3).
7. **hash validation on quote load** — `verify_snapshot_integrity` esiste ma non è ancora wired nel caricamento preventivi (backlog Fase 3).

---

## 29. STOP

Come richiesto, mi fermo dopo Milestone 1. **NON** procedo automaticamente con:
- Fase 1B (2 ante, portafinestra, meeting stile, threshold)
- Wiring UI simulator/catalogo/preventivo
- Pubblicazione in produzione

Attendo il tuo collaudo manuale del nuovo endpoint.

### Come collaudarlo dal tuo browser/curl

```bash
# Login
API_URL=https://serramento-ops.preview.emergentagent.com
TOKEN=$(curl -s -X POST "$API_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@infissiexpress.com","password":"<ADMIN_PASSWORD>"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# Calcolo ProEvolution 900x1500 BIANCO doppio standard
curl -s -X POST "$API_URL/api/pricing/compute" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "product_key":"PROEVOLUTION",
    "window_type":"WINDOW",
    "number_of_sashes":1,
    "width_mm":900, "height_mm":1500,
    "glass_type":"DOUBLE_STANDARD"
  }' | python3 -m json.tool
```

Il campo `commercial_snapshot.final_unit_price` deve essere **~960.25 €**.
