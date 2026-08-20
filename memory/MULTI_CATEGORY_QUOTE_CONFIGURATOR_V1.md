# Multi-Category Quote Configurator V1

**Deliverable §39** — Correzione P0 UX Preventivatore. Sostituisce il vecchio
`ConfiguratorDialog` (dropdown misto €/m²) con un flusso multi-categoria
data-driven e motore prezzo differenziato per prodotto.

Data implementazione: 20 Ago 2026

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
