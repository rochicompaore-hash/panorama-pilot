# Real Catalog Pricing V1 (F1)

**Data**: 20 Ago 2026 · **Direttiva**: "P0 — COMPLETAMENTO REALE PREVENTIVATORE"
**Deliverable §29** · **Scope**: F1 (Real Catalog Data) — F2/F3/F4 in coda.

Stato al termine di F1:
- `FINESTRE_REAL_CATALOG` = **BACKEND_READY + UI_IMPLEMENTED + MANUAL_E2E_PENDING**
- `ZANZARIERE_REAL_CATALOG` = **BACKEND_READY + UI_IMPLEMENTED + MANUAL_E2E_PENDING**
- `TAPPARELLE_REAL_CATALOG` = **BACKEND_READY + UI_IMPLEMENTED + MANUAL_E2E_PENDING**
- `CASSONETTI_REAL_CATALOG` = **BACKEND_READY + UI_IMPLEMENTED + MANUAL_E2E_PENDING**
- `COLORS_PVC_ANAGRAPHIC_V1` = **ANAGRAPHIC_READY; AUTO_003_RULE=NOT_IMPLEMENTED** (backlog F2)
- `POSITION_TECHNICAL_DATA_V1` = NOT_STARTED (F2)
- `VISUAL_CONFIGURATOR_V1` = NOT_STARTED (F3)
- `QUOTE_PDF_V2` = NOT_STARTED (F4)
- `M5` = BLOCKED

---

## 1. Gerarchia FINESTRE (§1-2)

- Categoria **`FINESTRE`** = unica per il flusso commerciale.
- `PORTEFINESTRE` = **soft-deleted** (`active=false`) — invisibile nel nuovo preventivatore, preservata per audit/storico. Nessun hard delete.
- Il `MultiCategoryConfiguratorDialog` chiede **TIPO SERRAMENTO** all'interno della configurazione ProEvolution: `WINDOW` / `DOOR_WINDOW`. Il payload passa a `POST /api/pricing/compute` che routa alla ricetta tecnica corretta.

---

## 2. Anagrafica Colori PVC (§9-11)

Collection: `product_colors` (unica anagrafica, multi-dominio di prezzo — §6 direttiva mapping).

Campi chiave:
- `code`, `name`, `ral_reference`, `finish_type` (descrittivo)
- `pvc_color_category` ∈ `MASS_COLOR / STANDARD / SPECIAL / NEEDS_PO_MAPPING`
- `cassonetti_price_family` ∈ `BIANCO_MASSA / STANDARD / NON_STANDARD / NEEDS_PO_MAPPING`
- `visual_hex` (usato da F3 renderer)

13 colori seedati e verificati:

| code | nome                        | RAL   | pvc_category  | cassonetti_family |
|------|-----------------------------|-------|---------------|-------------------|
| 003  | BIANCO MASSA                | 9016  | `MASS_COLOR`  | `BIANCO_MASSA`    |
| 100  | BIANCO CLASSICO             | 9016  | `STANDARD`    | `STANDARD`        |
| 096  | CREMA                       | 9001  | `STANDARD`    | `STANDARD`        |
| 694  | CEDRO SBIANCATO             | —     | `STANDARD`    | `STANDARD`        |
| 110  | CILIEGIO / GOLDEN OAK       | —     | `STANDARD`    | `STANDARD`        |
| 154  | NOCE                        | —     | `STANDARD`    | `STANDARD`        |
| 048  | GRIGIO ANTRACITE LISCIO     | 7016  | `STANDARD`    | `STANDARD`        |
| 019  | BIANCO CALDO                | 9010  | `SPECIAL`     | `NON_STANDARD`    |
| 145  | QUERCIA IRLANDESE           | —     | `SPECIAL`     | `NON_STANDARD`    |
| 146  | CILIEGIO RUSTICO            | —     | `SPECIAL`     | `NON_STANDARD`    |
| 109  | WINCHESTER                  | —     | `SPECIAL`     | `NON_STANDARD`    |
| 402  | DOUGLAS                     | —     | `SPECIAL`     | `NON_STANDARD`    |
| 663  | NOCE SORRENTO BALSAMICO     | —     | `SPECIAL`     | `NON_STANDARD`    |

**Nota critica**: 003 e 100 hanno lo stesso RAL 9016 ma famiglie prezzo diverse — la mappatura è **esplicita**, mai inferita.

Endpoint:
- `GET /api/product-colors[?active=true&pvc_color_category=X&cassonetti_price_family=Y]`
- `GET /api/product-colors/{id}`
- `POST /api/product-colors` (admin)
- `PATCH /api/product-colors/{id}` (admin)

**Regola 003 BIANCO MASSA** (§11): quando il serramento è pellicolato solo esterno + interno bianco, il codice interno tecnico va forzato a `003`. **BACKLOG F2** (richiede configurazione tecnica posizione).

---

## 3. Zanzariere Reali (§19-27)

Rimosso dal catalogo commerciale: `TEST_ZANZARIERA_AREA_130` (`active=false`, `new_quote_enabled=false`).

5 modelli reali seedati con `pricing_model=AREA` e `color_domain=ZANZARIERE`:

| code       | min m² | purchase €/m² BASE | WOOD_EFFECT | MARBLE  | SPECIAL |
|------------|--------|--------------------|-------------|---------|---------|
| SWITCH_5   | 2.00   | 57.20              | 74.36       | 62.92   | 62.92   |
| SKAT       | 1.50   | 57.00              | 78.62       | 57.00   | 57.00   |
| UNIKLAT    | 2.00   | 29.04              | 40.66       | 31.94   | 31.94   |
| UNIKVER    | 1.50   | 21.56              | 30.18       | 23.72   | 23.72   |
| UNIKCAT    | 1.50   | 23.32              | 32.65       | 25.65   | 25.65   |

**Formula (§25 direttiva)**:
```
real_area = width_mm/1000 * height_mm/1000
billable_area = max(real_area, minimum_billable_area_m2)  # PER PEZZO
purchase_cost_per_item = billable_area * purchase_cost_table[color_category]
sale_price_per_item = purchase_cost_per_item * 3.00       # multiplier
sale_price_total = sale_price_per_item * quantity          # §3 minimo per pezzo
```

**Acceptance §21 UNIKVER 800×800 BASE** → `sale_price_total = 97.02 €` ✅ (`billable=1.50 m² × 21.56 × 3`).

**Colori zanzariere** (collection separata `zanzariere_colors` — §7-8 direttiva mapping):
- Placeholder `ZC_BASE_DEFAULT / ZC_WOOD_DEFAULT / ZC_MARBLE_DEFAULT / ZC_SPECIAL_DEFAULT` per collaudo.
- Cartella reale **TO_CONFIRM** dal PO (§8: non inventare catalogo colori).
- Endpoint: `GET /api/zanzariere-colors`.

**Posa (§27)**: separata via `simple_services` (MONTAGGIO ZANZARIERE `internal 70 / sale 90`, MONTAGGIO ZANZARIERA DOPPIA `140/165`). NO ×3.

---

## 4. Tapparelle Reali (§34-38)

Prodotto: `TAPPARELLA_STANDARD` (`pricing_model=AREA`, `color_domain=INTERNAL_MAP`).

`pricing_config`:
```
{
  "sale_price_table_per_m2": {"RAL": 35.00, "LEGNO": 40.00, "RAFFAELLO": 45.00},
  "minimum_billable_area_m2": 1.50,
  "color_map": {"RAL_STANDARD": "RAL", "WOOD_EFFECT": "LEGNO", "RAFFAELLO": "RAFFAELLO"},
  "direct_product_cost_status": "NEEDS_PO_CONFIGURATION"     # §38
}
```

**Acceptance §22 800×1000** → `real=0.80, billable=1.50 m²`:
- RAL 35 → **52,50 €** ✅
- LEGNO 40 → **60,00 €** ✅
- RAFFAELLO 45 → **67,50 €** ✅

**Costo interno**: `NEEDS_PO_CONFIGURATION` (§38). Il preventivo funziona; Margin Control segnalerà `DIRECT_PRODUCT_COST_NOT_CONFIGURED`.

---

## 5. Cassonetti — Pricing Model GRID (§28-33)

Prodotto: `CASSONETTO_STD` (`pricing_model=GRID`, `color_domain=PVC`).

**Import da workbook ufficiale** `listino_completo_con_costi.xlsx`:
- File JSON pre-processato: `/app/backend/app/data/cassonetti_grid_2026.json`
- Grid: 3 famiglie × 8 sotto-griglie (4 depth × 2 ceiling) × 186 dimensioni = **4.464 celle prezzo**
- Ogni cella contiene `{internal, sale}` (dal costo prod. + dal listino vendita).

**Chiavi lookup**: `(width_mm, height_mm, depth_mm ∈ {163,326,489,652}, ceiling_liner ∈ {SI,NO}, finish_family)`.

**Mapping colore → finish_family**: risolto dal `color_code` selezionato tramite
`product_colors.cassonetti_price_family` (mapping esplicito, §13 direttiva mapping).

**Vincoli chiave**:
- **§14 NO ×3** sui cassonetti. `customer_sale_price` letto dal file è definitivo.
- **§15 Nessuna ricostruzione da formula**: il file vince.
  - Verificato: L500 H550 D163 c/ciel BIANCO_MASSA = **422,38 €** (il file applica il +50% correttamente per H>500 AND L<700).
  - `pricing_formula_metadata` conservata come audit (multiplier 2.5, surcharge 30/50).
- **§16 Fail-closed**:
  - Dimensione fuori griglia → `DIMENSION_TO_CONFIRM` (NO interpolazione, NO nearest).
  - Colore `NEEDS_PO_MAPPING` → `MISSING_CASSONETTO_COLOR_PRICE_FAMILY`.

**Acceptance §23 (3 celle reali verificate via pytest)**:

| L | H | Depth | Ceiling | Colore | Family | Sale | Internal |
|---|---|-------|---------|--------|--------|------|----------|
| 500 | 250 | 163 | c/ciel | 003 | BIANCO_MASSA | **329,01 €** | 101,23 € |
| 500 | 550 | 163 | c/ciel | 003 | BIANCO_MASSA | **422,38 €** | 112,63 € |
| 700 | 250 | 326 | s/ciel | 154 | STANDARD | **296,20 €** | 118,48 € |

---

## 6. Frontend — MultiCategoryConfiguratorDialog

Estensioni F1:
- **ColorPicker** data-driven per AREA (Zanzariere via `/api/zanzariere-colors`, PVC via `/api/product-colors`, Tapparelle via `INTERNAL_MAP` embedded) e per GRID (colori PVC).
- Nuovo renderer **`cfg-grid`** con: L, H, `depth_mm` (163/326/489/652), `ceiling_liner` (SI/NO), quantità + ColorPicker.
- **TIPO SERRAMENTO** in `cfg-technical`: `WINDOW` / `DOOR_WINDOW` come primo campo (§1-2).
- Preview esteso: `preview-area-detail` (con `color_price_category`, `purchase_cost/m²` admin-only), `preview-grid-detail` (dimensioni, famiglia, sale + internal admin-only).

---

## 7. RBAC (§24)

Endpoint `POST /api/multi-cat/products/{pid}/configure`:
- Commercial (`products.view`): riceve `sale_price_total` / `customer_sale_price_per_item` / `unit_sale_price_per_m2`.
- Admin (permessi `*` o `products.manage` / `quotes.view_costs` / `quotes.view_margins`): riceve anche `purchase_unit_cost_per_m2` / `purchase_cost_per_item` / `internal_production_cost_per_item` / `commercial_multiplier`.

Redaction applicata a `technical_snapshot` (già in V1) e ora estesa via UI condizionale (`canSeeCosts` flag).

---

## 8. Versionamento (§25)

Ogni pricing_config include `pricing_version`:
- `zanzariere_2026_08`
- `tapparelle_2026_08`
- `cassonetti_grid_2026_08` (contiene `source_file`)

Il `pricing_snapshot` della QuoteLine registra la versione al momento dell'aggiunta.

---

## 9. Test acceptance (§28)

- `tests/test_multi_category_pricing.py` — 19 unit sul motore Simple + Resolver
- `tests/test_p0_formula_technical_quoteline.py` — 5 regression bug P0
- `tests/test_f1_real_catalog.py` — **10 acceptance F1** (categorie / colori / UNIKVER §21 / tapparelle §22 / cassonetti §23 / fail-closed / fixture nascoste / idempotenza)

**Totale**: **34/34 pytest verdi**.

**Testing UI**: consegnato al tuo ricollaudo manuale (§28 richiede E2E anche via UI, non solo API).

---

## 10. Known limitations / carry-over per F2-F4

| item | fase | note |
|------|------|------|
| Regola 003 BIANCO MASSA auto per solo-esterno-pellicolato (§11) | F2 | richiede `outside_foil` / `inside_display_color` fields nella configurazione tecnica ProEvolution |
| Ante configurabili (§4-5 direttiva finale) — sash_count, opening_per_sash[] | F2 | `configuration_snapshot` esteso |
| Maniglia + colore, copricerniere, coprifilatura (§6-8) | F2 | estensione `configuration_snapshot` |
| Doppia vista interna/esterna renderer SVG (§12-17) | F3 | SVG deterministico con `visual_hex` da anagrafica |
| Renderer prodotti non-serramento (§18) | F3 | schema/immagine coerente per Zanzariere/Tapparelle/Cassonetti/Persiane/Porte |
| PDF Preventivo v2 (§40-55) | F4 | tutti i campi tecnici + doppia immagine + package_snapshot |
| PDF Contratto allegato tecnico (§56-57) | F4 | congelato dallo snapshot |
| Readiness check `MISSING_QUOTE_CONFIGURATION` (§58) | F4 | pre-PDF validation |
| Cartella colori zanzariere reale (§8 direttiva mapping) | TO_CONFIRM | attendo cartella reale — ora placeholder ZC_*_DEFAULT |
| Costo interno tapparelle | TO_CONFIRM | Margin Control segnalerà `DIRECT_PRODUCT_COST_NOT_CONFIGURED` |

---

## 11. File modificati/creati (F1)

**Backend**:
- `app/models_colors.py` — `ProductColor`, `ZanzarieraColor` (nuovo)
- `app/models_multi_category.py` — enum esteso con `GRID`
- `app/services/multi_category_pricing.py` — `compute_area_by_color`, `compute_grid`, resolver routing
- `app/routers/product_colors.py` — router `/product-colors` + `/zanzariere-colors` (nuovo)
- `app/scripts/seed_real_catalog_v1.py` — seed idempotente F1 (nuovo)
- `app/data/cassonetti_grid_2026.json` — griglia importata da Excel (nuovo, 392 KB)
- `server.py` — registrazione router
- `tests/test_f1_real_catalog.py` — 10 acceptance test (nuovo)

**Frontend**:
- `src/components/app/MultiCategoryConfiguratorDialog.jsx` — ColorPicker, `cfg-grid`, TIPO SERRAMENTO, preview esteso

---

## 12. STOP §30

**Fine F1. Non procedere con F2/F3/F4 prima del ricollaudo manuale del PO.**

Il PO collauderà:
- FINESTRE → ProEvolution → TIPO WINDOW / DOOR_WINDOW
- ZANZARIERE → 5 modelli reali
- TAPPARELLE → RAL / LEGNO / RAFFAELLO
- CASSONETTI → griglia reale (dimensioni + depth + ceiling + colore)
