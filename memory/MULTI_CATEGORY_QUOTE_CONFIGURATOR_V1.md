# Multi-Category Quote Configurator V1

**Deliverable §39** — Correzione P0 UX Preventivatore. Sostituisce il vecchio
`ConfiguratorDialog` (dropdown misto €/m²) con un flusso multi-categoria
data-driven e motore prezzo differenziato per prodotto.

Data implementazione: 20 Ago 2026

---

## 🚀 F1 REAL CATALOG PRICING V1 — CONSEGNATO (20 Ago 2026)

**Vedi documento completo**: `/app/memory/REAL_CATALOG_PRICING_V1.md`

Sintesi F1:
- **Gerarchia FINESTRE unica** (PORTEFINESTRE soft-deleted, TIPO SERRAMENTO chiesto dentro il configuratore)
- **13 colori PVC** in `product_colors` con doppia classificazione (`pvc_color_category` + `cassonetti_price_family`)
- **5 zanzariere reali** con `pricing_model=AREA` + `purchase_cost_table` × ×3
- **Tapparella reale** con 3 varianti colore (RAL/LEGNO/RAFFAELLO, min 1.50 m²/pz, no ×3)
- **Cassonetti** con nuovo `pricing_model=GRID` importato dal workbook ufficiale (4.464 celle, no ×3, no ricostruzione)
- **ColorPicker data-driven** con hex swatch (F3 ready)
- **Fail-closed** su dimensioni fuori griglia + colori senza mapping
- **34/34 pytest verdi**

**Backlog per F2/F3/F4** (STOP prima del ricollaudo manuale PO):
- F2: `POSITION_TECHNICAL_DATA_V1` (sash_count, opening_per_sash[], handle_model+color, hinge_cover_color, trim_configuration, regola 003 BIANCO MASSA auto)
- F3: `VISUAL_CONFIGURATOR_V1` (SVG deterministico doppia vista interna/esterna, renderer per zanzariere/tapparelle/cassonetti)
- F4: `QUOTE_PDF_V2` + `CONTRACT_PDF_V2` + readiness check `MISSING_QUOTE_CONFIGURATION`


---

## 🚨 REAL QUOTE INTEGRATION BUG P0 — HOTFIX (20 Ago 2026)

**Sintomo verificato in produzione (PRV-2026-01716)**:
`FINESTRE → ProEvolution → 1200×1400` aggiunto al preventivo con
`PREZZO = 0 €`, `SUBTOTALE = 0 €`, `TOTALE = 0 €`.

### Root cause

**API contract mismatch tra `pricing_v3.commercial_snapshot` e il frontend.**

Il motore autorevole `POST /api/pricing/compute` restituisce:
```json
"commercial_snapshot": {
  "pricing_method": "MULTIPLIER",
  "multiplier": 3.0,
  "unit_sale_price": 1016.7,
  "final_unit_price": 1016.7,   ← AUTHORITATIVE
  "discount": 0.0
}
```

Il frontend `MultiCategoryConfiguratorDialog.submit()` cercava invece:
```js
preview.commercial_snapshot?.customer_price
  ?? preview.commercial_snapshot?.customer_price_total
  ?? preview.commercial_snapshot?.sale_price
  ?? 0;    // ← FALLBACK 0 raggiunto sempre
```

Tutti e tre i field cercati **non esistono** in `pricing_v3`. Fallback `?? 0`
propagato in `base_price=0` nel payload `POST /api/quotes/{id}/lines`, quindi
`compute_line()` calcolava `unit_price_final=0, subtotal_line=0`.

### Affected fields

| Layer | Field errato (FE) | Field autorevole (BE) |
|-------|-------------------|-----------------------|
| Configure response | `commercial_snapshot.customer_price` | `commercial_snapshot.final_unit_price` |
| Configure response | `commercial_snapshot.customer_price_total` | `commercial_snapshot.final_unit_price * qty` |
| Configure response | `commercial_snapshot.sale_price` | `commercial_snapshot.unit_sale_price` (alias) |
| Configure response | `commercial_snapshot.unit_price` | `commercial_snapshot.final_unit_price` |
| Redaction RBAC | `production_cost` (non esiste) | `total_internal_cost` (nome vero) |

### Fix applicati

1. **Frontend `MultiCategoryConfiguratorDialog.jsx`**:
   - `submit()`: legge `final_unit_price` / `unit_sale_price` come prime scelte.
     Se `unit<=0` o `total<=0` **non aggiunge la riga** e mostra
     `COMMERCIAL_PRICING_NOT_CONFIGURED` (fail-closed §6/§8).
   - `PricingPreviewCard`: stesso set di field; se mancano mostra badge
     `COMMERCIAL_PRICING_NOT_CONFIGURED` invece di "0 €".
   - Dettaglio FORMULA_TECHNICAL: mostra `multiplier` e `final_unit_price`.

2. **Backend `POST /api/quotes/{qid}/lines`**:
   - Guard fail-closed lato server: righe con
     `source=MULTI_CATEGORY_V1` + `pricing_model=FORMULA_TECHNICAL` +
     `base_price<=0` **vengono rifiutate con HTTP 400**
     `COMMERCIAL_PRICING_NOT_CONFIGURED`.
   - Zero € non è mai un valore ammesso per FORMULA_TECHNICAL (§6/§8).

3. **RBAC redaction `POST /api/multi-cat/products/{pid}/configure`**:
   - Corretta la lista di redaction per non-admin. Ora rimuove i field
     effettivi di `pricing_v3`: `total_internal_cost`, `material_cost`,
     `glass_cost`, `hardware_cost`, `labor_cost`, `foil_surcharge`,
     `additional_technical_costs`, `hourly_workshop_cost`,
     `production_time_hours`, `components`, `glass_dimensions`
     (+ alias legacy). Il commerciale NON riceve costi interni.

### API Contract autorevole (nuovo standard)

Per **FORMULA_TECHNICAL**:
```
POST /api/multi-cat/products/{pid}/configure
  -> commercial_snapshot.final_unit_price          -> unit di riga
     commercial_snapshot.unit_sale_price   (alias) -> stesso valore
     commercial_snapshot.multiplier                -> es. 3.0
     technical_snapshot.total_internal_cost        -> production_cost (ADMIN only)
     calculation_hash                              -> stesso di /api/pricing/compute
```

Per **AREA / LINEAR / PER_ITEM / FIXED / FIXED_PLUS_VARIABLE / TIERED**:
```
  -> simple_snapshot.unit_price_final              -> unit di riga
     simple_snapshot.sale_price_total              -> subtotale (unit × qty)
     simple_snapshot.billable_* / real_*           -> dettaglio dimensionale
```

### Before / After

| item | before | after |
|------|--------|-------|
| ProEvolution 1200×1400 add-to-quote | `unit_price_final=0`, `subtotal_line=0`, `total=0` | `unit_price_final=1016.70`, `subtotal_line=1016.70`, `total>0` ✅ |
| Add con base_price=0 (bug) | riga creata a 0 € | HTTP 400 `COMMERCIAL_PRICING_NOT_CONFIGURED` ✅ |
| Preview senza field commerciale | mostra "0 €" | badge `COMMERCIAL_PRICING_NOT_CONFIGURED` ✅ |
| Commerciale riceveva `total_internal_cost`? | Sì (redaction su nome sbagliato) | No (redaction su field reali) ✅ |
| §3 Identità motore `pricing_v3` vs `multi-cat` | Non verificato in test | Verificato via `calculation_hash` identico ✅ |
| AREA §36 regression 100€/m² min1.50 1000×800 | 150 € | 150 € ✅ |

### E2E evidence (verified via curl + pytest 20/8/2026)

```
=== §3 IDENTITÀ MOTORE ===
pricing_v3 hash    = dd0d34d7c52df302da89707a5e2515c17f07979a34896eee24d683407b52dcfc
multi-cat hash     = dd0d34d7c52df302da89707a5e2515c17f07979a34896eee24d683407b52dcfc
IDENTITY: PASS

=== CONFIGURE + ADD-LINE ===
FROM CONFIGURE: unit=1016.7, multiplier=3.0, production_cost=338.9
LINE OK: subtotal_line=1016.7 unit_price_final=1016.7

=== FAIL-CLOSED ===
POST /lines base_price=0 -> HTTP 400 COMMERCIAL_PRICING_NOT_CONFIGURED

=== REGRESSION AREA §36 ===
AREA 1000x800 min1.50: sale_price_total=150.0 (atteso 150.0)
```

Test regression: `tests/test_p0_formula_technical_quoteline.py` **5/5 PASS**.
Test unit precedenti: `tests/test_multi_category_pricing.py` **19/19 PASS**.

### Known issue non toccato (§14)

- **Vano V1 con L/H vuoti** mentre la riga ha `1200×1400`. Documentato: le
  dimensioni ora vivono in `QuoteLine.width_mm/height_mm`, mentre
  `QuoteOpening.width_mm/height_mm` restano opzionali. Serve decidere quale è
  la source-of-truth definitiva (position/configured product vs opening logico).
  **Fuori scope hotfix P0**, aggiunto ai TO_CONFIRM.

### Stato ufficiale post-hotfix

- `CATEGORY_SELECTION_UI` = PASS
- `PRODUCT_SELECTION_UI` = PASS
- `SIMPLE_PRICING_ENGINE` = E2E_READY
- `AREA_MINIMUM_BILLABLE` = PASS
- `FORMULA_TECHNICAL_CONFIGURATION` = PASS
- `FORMULA_TECHNICAL_PRICING_COMPUTE` = PASS (identità motore verificata)
- `FORMULA_TECHNICAL_TO_QUOTELINE` = **FIXED** (backend curl PASS; **richiede tuo collaudo manuale UI**)
- `QUOTE_TOTAL_RECOMPUTE` = **FIXED** (verified via `_recompute`)
- `MULTI_CATEGORY_CONFIGURATOR` = PARTIAL (in attesa di ricollaudo UI)
- `CATALOG_REAL_DATA` = PARTIAL
- `M5` = BLOCKED (mancano Package/Services/Discount/Margin wiring UI)


---

## 1. Obiettivo e criterio d'accettazione

Sostituire il vecchio flusso
```
[Configuratore prodotto] -> Dropdown misto (ProEvolution, Tapparella, ...) -> €/m²
```
con
```
[Aggiungi al preventivo]
  -> STEP 1: CATEGORIA (data-driven)
  -> STEP 2: PRODOTTO / LINEA
  -> STEP 3: CONFIGURAZIONE (specifica per pricing_model)
  -> BACKEND compute -> PREZZO
```

Il **motore di calcolo** dipende dal prodotto (via `pricing_model`):
`FORMULA_TECHNICAL` | `AREA` | `LINEAR_METER` | `PER_ITEM` | `FIXED_PRICE`
| `FIXED_PLUS_VARIABLE` | `TIERED` | `MANUAL_REVIEW_REQUIRED`.

**§36 acceptance verificato**: prodotto AREA a 100 €/m² con `minimum_billable=1.50`,
dimensioni 1000×800 mm → `real_area=0.80m²`, `billable=1.50m²`, `sale=150€`.

---

## 2. Categorie iniziali (§5)

Tutte create in `product_categories` per ogni tenant (idempotente).

| code            | label             | order |
|-----------------|-------------------|-------|
| FINESTRE        | Finestre          | 10    |
| PORTEFINESTRE   | Portefinestre     | 20    |
| SCORREVOLI      | Scorrevoli        | 30    |
| ZANZARIERE      | Zanzariere        | 40    |
| TAPPARELLE      | Tapparelle        | 50    |
| CASSONETTI      | Cassonetti        | 60    |
| PERSIANE_SCURI  | Persiane / Scuri  | 70    |
| PORTE_INTERNE   | Porte interne     | 80    |
| PORTE_BLINDATE  | Porte blindate    | 90    |
| ACCESSORI       | Accessori         | 100   |
| SERVIZI         | Servizi           | 110   |
| MONTAGGI_POSA   | Montaggi / Posa   | 120   |

**Categoria != pricing_model**: la stessa categoria può ospitare prodotti con
`pricing_model` differenti (§28).

---

## 3. Catalog hierarchy — Product Model esteso

`ProductCatalog` è stato esteso in modo **additivo** (`models_pricing.py`).
Nuovi campi:

| campo                        | tipo                | scopo |
|------------------------------|---------------------|-------|
| `pricing_model`              | `Optional[str]`     | enum autorevole (fail-closed se null) |
| `pricing_config`             | `Dict[str, Any]`    | unit_price / min_billable / tiers / recipe_id |
| `category_id`, `category_code` | `Optional[str]`   | FK verso `product_categories` |
| `subcategory`, `line`        | `Optional[str]`     | gerarchia commerciale |
| `sale_unit`                  | `Optional[str]`     | m2 / ml / pz / forfait |
| `minimum_billable_quantity`  | `Optional[float]`   | minimo fatturabile |
| `compatible_packages`        | `List[str]`         | BASE/ADVANCED/PREMIUM |
| `compatible_services`        | `List[str]`         | simple_services suggeriti |
| `technical_recipe_id`        | `Optional[str]`     | link motore tecnico (nascosto ai commerciali) |
| `configurator_schema`        | `Optional[Dict]`    | schema data-driven futuro |
| `legacy`                     | `bool`              | prodotto pre-multi-cat |
| `new_quote_enabled`          | `bool`              | se compare nel nuovo flusso |
| `classification_status`      | `str`               | CLASSIFIED / TO_CONFIRM / LEGACY_ONLY / TEST_FIXTURE |
| `is_test_fixture`            | `bool`              | fixture di collaudo (nascosto default) |

---

## 4. Pricing Models supportati (§13)

| model                      | motore                                | require |
|----------------------------|---------------------------------------|---------|
| `FORMULA_TECHNICAL`        | `POST /api/pricing/compute` (esistente, autorevole) | `technical_inputs` |
| `AREA`                     | SimplePricingEngine.compute_area      | `width_mm`, `height_mm`, `pricing_config.unit_sale_price`, opz. `minimum_billable_quantity` |
| `LINEAR_METER`             | SimplePricingEngine.compute_linear    | `linear_meters`, `unit_sale_price`, opz. `minimum_billable_quantity` |
| `PER_ITEM`                 | SimplePricingEngine.compute_per_item  | `quantity`, `unit_sale_price` |
| `FIXED_PRICE`              | SimplePricingEngine.compute_fixed_price | `fixed_sale_price` |
| `FIXED_PLUS_VARIABLE`      | compute_fixed_plus_variable           | `fixed_component`, `variable_unit_price`, `variable_basis` |
| `TIERED`                   | compute_tiered                        | `tiers[]`, `tier_basis` |
| `MANUAL_REVIEW_REQUIRED`   | nessun prezzo (§22)                   | — |

### Formule chiave

**AREA (§9)**:
```
real_area_m2   = (width_mm / 1000) * (height_mm / 1000)
billable_area  = max(real_area_m2, minimum_billable_area_m2)
sale_price     = billable_area * unit_sale_price * quantity
```

**LINEAR**: analogo su `linear_meters`.

**FIXED_PLUS_VARIABLE**: `unit_price = fixed_component + variable_unit_price * basis`,
poi `sale_price = unit_price * quantity`.

---

## 5. Authoritative Pricing Route (§7 — vincolo architetturale)

`FORMULA_TECHNICAL` NON crea un secondo motore. Instrada al motore tecnico
già autorevole:

```
POST /api/multi-cat/products/{id}/configure
  |
  +--> FORMULA_TECHNICAL --> POST /api/pricing/compute (pricing_v3)
  |                          -> production_cost, commercial_snapshot, calculation_hash
  |
  +--> AREA / LINEAR / ITEM / FIXED / ... --> SimplePricingEngine (nuovo, semplice)
  |
  +--> MANUAL_REVIEW_REQUIRED --> risposta "manual_review_required" (no price)
  |
  +--> pricing_model=null OR legacy=true OR new_quote_enabled=false --> fail-closed
```

**Test di identità (§30)**: la stessa configurazione ProEvolution eseguita da
`/multi-cat/products/{pid}/configure` e da `/pricing/compute` deve produrre
lo stesso `technical_snapshot.production_cost` e `calculation_hash`.

---

## 6. Migration Strategy (§2, §3)

**NO migrazione automatica cieca `base_type -> pricing_model`.**

Il seed idempotente esegue in ordine:

1. **Categorie**: upsert per tenant.
2. **Classificazione esplicita**: SOLO i prodotti con `key ∈ TECH_PRODUCT_KEYS_TO_CLASSIFY`
   (attualmente `PROEVOLUTION`, `PROEVOLUTION_RESTAURO`) → `pricing_model=FORMULA_TECHNICAL`.
   Se il prodotto non esiste, viene skippato — NON creato.
3. **Legacy flag**: prodotti attivi senza `pricing_model` vengono marchiati
   `legacy=true`, `new_quote_enabled=false`, `classification_status=TO_CONFIRM`.
   Restano leggibili per preventivi storici, NON compaiono nel nuovo configuratore.
4. **Test fixtures**: 5 prodotti marcati `is_test_fixture=true`,
   `classification_status=TEST_FIXTURE`. Nascosti di default; visibili con
   `include_test_fixtures=true` (admin only).

Script: `python -m app.scripts.seed_multi_category_v1 --all-tenants [--dry-run]`.

**Prodotti legacy correnti**: 7 flaggati come `LEGACY` (tenant Infissi Express).
Nomi/codici sono preservati e mai riclassificati automaticamente.

---

## 7. Legacy Inventory & Caller Analysis (§18)

- **`/app/frontend/src/components/app/ConfiguratorDialog.jsx`** (LEGACY):
    - Conservato per storico (edit di righe legacy).
    - Rimosso dal `QuoteEditorPage.jsx` (import sostituito con
      `MultiCategoryConfiguratorDialog`).
    - **Altri caller residui**: grep `ConfiguratorDialog` mostra usage solo in
      `QuoteEditorPage.jsx` (già sostituito) — nessun caller commerciale residuo.
- **`/api/products` (router `pricing.py`)**: mantenuto per admin CRUD.
- **`/api/configurator/preview`** (motore preview legacy): mantenuto, non
  referenziato dal nuovo dialog.

---

## 8. Simple Services & Listino Posa (§12, §16, §17)

**Nessuna duplicazione** — `simple_services` è l'unica collection per
posa/montaggi/smontaggi/servizi. Contenuto già seedato con dual pricing
(`internal_reference_price` + `customer_sale_price`).

Chi vede cosa via API (§13, §31):
- **COMMERCIAL** riceve solo `customer_sale_price`.
- **ADMIN** con permesso `services.view_costs` riceve entrambi.

---

## 9. Categorie e Simple Services Mapping

I `simple_services` esistenti sono organizzati per `category` (POSA,
SMONTAGGIO, MOTORIZZAZIONE, ACCESSORIO, LOGISTICA). Nel nuovo flusso:
categoria commerciale `MONTAGGI_POSA` → simple_services `category=POSA`
(mapping applicativo, non hardcoded frontend). *(Wire-up del picker Servizi
sul preventivo sarà attività separata — fuori scope V1.)*

---

## 10. QuoteLine Snapshot (§14, §15, §16)

`QuoteLine` esteso in modo **additivo** con marker `source=MULTI_CATEGORY_V1`:

| campo aggiunto            | tipo                | scopo |
|---------------------------|---------------------|-------|
| `source`                  | `Optional[str]`     | "MULTI_CATEGORY_V1" per nuove righe |
| `category_id`, `category_code` | `Optional[str]` | |
| `product_id`, `product_code`   | `Optional[str]` | |
| `pricing_model`           | `Optional[str]`     | |
| `configuration_snapshot`  | `Optional[Dict]`    | width/height/qty/opts input |
| `pricing_snapshot`        | `Optional[Dict]`    | full response resolver |
| `technical_snapshot`      | `Optional[Dict]`    | popolato solo per FORMULA_TECHNICAL |
| `commercial_snapshot`     | `Optional[Dict]`    | popolato solo per FORMULA_TECHNICAL |
| `financial_snapshot`      | `Optional[Dict]`    | riservato margin control (post-integration) |

Righe legacy: tutti i nuovi campi `null` — nessuna rottura di storico.

---

## 11. RBAC (§25, §26)

Applicato lato **backend** (non solo frontend):

### `GET /api/multi-cat/products`
- COMMERCIAL riceve i prodotti ma con `pricing_config` filtrato
  (rimossi `internal_reference_price`, `production_cost_seed`, `internal_cost`,
  `cost_config`) e senza `technical_recipe_id`.
- ADMIN riceve tutto.

### `POST /api/multi-cat/products/{pid}/configure`
- Se non admin, il `technical_snapshot` risposta ha rimossi:
  `production_cost`, `components_cost`, `labor_cost`, `hardware_cost`,
  `glass_cost`, `frame_cost`, `sash_cost`, `cost_breakdown`, `internal_cost`.
- Commercial vede solo il `commercial_snapshot.customer_price` finale.

`is_admin` è vero se il permesso include `*` o
`products.manage`/`quotes.view_costs`/`quotes.view_margins`.

---

## 12. Endpoints introdotti

```
GET    /api/product-categories                 -> list (data-driven)
GET    /api/product-categories/{cid}
POST   /api/product-categories                 -> create (admin)
PATCH  /api/product-categories/{cid}           -> update (admin)
DELETE /api/product-categories/{cid}           -> soft delete (admin)

GET    /api/multi-cat/products                 -> catalog filtrato (RBAC)
       query: ?category_code=X&include_legacy=false&include_test_fixtures=false
GET    /api/multi-cat/products/{pid}           -> single product (RBAC)
POST   /api/multi-cat/products/{pid}/configure -> resolver + compute (RBAC)
```

Tutti registrati in `server.py` sotto `/api`.

---

## 13. Seed behavior (§32)

`app/scripts/seed_multi_category_v1.py`:

- **Idempotente**: nessuna duplicazione, upsert su `(tenant_id, code)`.
- Supporta `--dry-run`, `--tenant-id`, `--all-tenants`.
- Non classifica prodotti ambigui automaticamente.
- Non tocca prodotti già `CLASSIFIED`.
- Non modifica `simple_services` (già seedati altrove).

Test fixtures create (§28 minimum_billable, §35 test A/B/C/D/E):
- `TEST_ZANZARIERA_AREA_130` (130€/m² min 1.50) — cat ZANZARIERE
- `TEST_AREA_100_MIN_150` (100€/m² min 1.50) — cat ZANZARIERE — **§36 target**
- `TEST_LINEAR_25` (25€/ml) — cat ACCESSORI
- `TEST_PER_ITEM_50` (50€/pz) — cat ACCESSORI
- `TEST_FIXED_120` (120€ forfait) — cat SERVIZI

Prodotti classificati come `FORMULA_TECHNICAL`:
- `PROEVOLUTION`, `PROEVOLUTION_RESTAURO` (solo se già esistenti).

---

## 14. Test fixtures e coverage (§35, §36)

- `/app/backend/tests/test_multi_category_pricing.py` — **19 test pytest PASS**:
  - `TestAreaEngine` (6 test — inclusi §36 e §11 zanzariera 130€/m²).
  - `TestLinearEngine`, `TestPerItemEngine`, `TestFixedPriceEngine`.
  - `TestFixedPlusVariable`, `TestTiered`.
  - `TestResolver` — fail-closed: legacy_disabled, missing_pricing_model,
    manual_review_required, invalid_inputs, area_ok, technical_requires_inputs.

E2E frontend + backend: consegnato al `testing_agent_v3_fork` (§27).

---

## 15. TO_CONFIRM / Known limitations

| item | status | note |
|------|--------|------|
| Wire-up Servizi/Posa nel wizard | TO_CONFIRM | fuori scope V1, si prevede STEP 4 (Servizi) post-config |
| Pacchetti (BASE/ADVANCED/PREMIUM) sul preventivo | TO_CONFIRM | integrazione con `commercial_packages` non parte del V1 |
| Editing di righe MULTI_CATEGORY_V1 | PARTIAL | il dialog riapre step 1; prefill completo (§31/§24) sarà rifinito nel test E2E |
| Prodotti legacy `TO_CONFIRM` | 7 items | richiedono classificazione esplicita del PO |
| Semantica `net_vat=3150` (Audit) | ORDINE 34 | NON toccato — flag per audit generale |

---

## 16. Non toccato (per direttiva PO §35)

- PDF, Contratti, Rilievi, Produzione, Magazzino.
- Google Auth / Audit (congelati durante questa iterazione).
- Motore tecnico esistente (`pricing_v3`) — solo riutilizzato, mai duplicato.
- `simple_services` — nessuna modifica, solo lettura.

---

## 17. File modificati/creati

**Backend**:
- `app/models_multi_category.py` (NEW)
- `app/models_pricing.py` (extended `ProductCatalog`)
- `app/models_quote.py` (extended `QuoteLine`, `QuoteLineCreate`)
- `app/services/multi_category_pricing.py` (NEW)
- `app/routers/product_categories.py` (NEW)
- `app/routers/multi_category_configurator.py` (NEW)
- `app/scripts/seed_multi_category_v1.py` (NEW)
- `app/scripts/__init__.py` (NEW empty init)
- `server.py` (register 2 new routers)
- `tests/test_multi_category_pricing.py` (NEW — 19 test)

**Frontend**:
- `src/components/app/MultiCategoryConfiguratorDialog.jsx` (NEW)
- `src/pages/QuoteEditorPage.jsx` (swap ConfiguratorDialog → MultiCategoryConfiguratorDialog, label "Aggiungi prodotto")

---

## 18. Post-implementazione — STOP (§40)

**Fermarsi per collaudo**. Non procedere con:
- Milestone 5 completo
- PDF/Contratti
- Google Auth/Audit (verranno riattivati dopo collaudo)

Testing: `testing_agent_v3_fork` (backend + frontend) sui casi §35 A→H e §36.
