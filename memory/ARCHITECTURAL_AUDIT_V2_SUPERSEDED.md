# Panorama Pilot — AUDIT ARCHITETTURALE VINCOLANTE v2
**Data**: Feb 2026 · Iter 32  
**Ambito**: verificare se oggi esiste UNA sola architettura, o più fonti autorevoli in conflitto  
**Metodologia**: read-only. Grep evidence sui 3 motori + 2 modelli + 2 router + DB.  
**Rispetto vincoli**: sez 22 STOP audit-v1 attiva. Zero implementazione. Solo diagnosi + piano.

---

## 🎯 VERDETTO IMMEDIATO

**Esiste una singola fonte autorevole?** **NO.**

Esistono **DUE FONTI AUTOREVOLI PARALLELE** che coesistono nello stesso database, con **schemi diversi, semantiche diverse, ma alcune collezioni CONDIVISE senza contratto formale**:

| Fonte A — "Catalog" (motore commerciale) | Fonte B — "Parametric" (motore tecnico legacy) |
|---|---|
| `products` (models_catalog) | `profile_systems` (models_parametric) |
| `products.components[]` — codice+categoria+applies_to inline | `profiles` — code+role+system_id |
| `catalog_code_mappings` | `bom_templates` — formule quantity/length/width/height |
| `glass_recipes` (schema semplificato structured/custom) | (nessun equivalente) |
| `production_config` | `pricing_mode_configs` (schema differente per pricing) |
| **letta da**: `perimeter_assembler.py` → `commercial_perimeter.py` | **letta da**: `bom_engine_v2.py` → `parametric_engine.resolve_bom` |
| **USATA dal preventivo ATTIVO** (Fase 1 audit v1) | **NON USATA dal preventivo** — solo `/parametric/preview` che salva `parametric_snapshots` isolate |

**Collezioni CONDIVISE tra i due motori** (senza FK, senza contratto):
- `item_pricelists` — entries schema **DIVERGE**: Fonte A legge `entries[].code` (stringa libera che DEVE combaciare con `products.components[].code`), Fonte B legge `entries[].ref_type + ref_id` (FK verso `profiles/glass_types/hardware_kits/accessories`)
- `color_categories` — condivisa, schema compatibile, uso identico
- `colors` — usata solo da Fonte B (Fonte A usa stringa `color_code` libera)

**Duplicazioni identiche ma su collezioni diverse**: NO — sono duplicazioni **concettuali** (stesso dominio "sistema profilo/profilo/componente") ma con schemi diversi. È peggio di una duplicazione fisica: **due modelli mentali coesistono nel codice**.

---

## 2 · MAPPA COMPLETA DEL SISTEMA

Legenda stato: **AUTOREVOLE** = fonte reale usata dal motore attivo. **LEGACY** = design vecchio ancora nel codice. **DUPLICATO** = concetto già presente in altra collezione. **ORFANO** = doc scritti ma mai letti. **NON UTILIZZATO** = collezione vuota o endpoint scollegato.

| Entità | Backend files | Frontend | Modello | Collezione | Endpoint CRUD | Chi scrive | Chi legge | Motore | Schermata | STATO |
|---|---|---|---|---|---|---|---|---|---|---|
| **Sistemi profilo** | `models_parametric.ProfileSystem`, `routers/parametric.py:58-107` | `ParametricAdminPage.jsx` | `ProfileSystem` | `profile_systems` | `/api/parametric/profile-systems` | ParametricAdminPage (di fatto solo lettura, no create UI) | `bom_engine_v2._build_lookups`, `resolve_bom_full` | **technical_cut_list** | `/parametric/admin` | LEGACY / disconnesso motore commerciale |
| **Profili** | `models_parametric.Profile`, `routers/parametric.py:112-149` | `ParametricAdminPage.jsx` | `Profile` | `profiles` | `/api/parametric/profiles` | idem | `bom_engine_v2._preload_anagraph`, `nesting/run` | **technical_cut_list** | `/parametric/admin` | LEGACY |
| **Componenti prodotto (unificato)** | `models_catalog.ProductComponentAssoc`, `routers/catalog.py` | `ProductCatalogPage.jsx`, `ProductSimulatorPage.jsx` | inline in `products.components[]` | `products` | `/api/catalog/*`, `/api/products/*` | Catalogo UI | `perimeter_assembler.get_component_code`, `commercial_perimeter` | **commercial_perimeter** | `/products`, `/product-simulator` | **AUTOREVOLE** |
| **Codici articolo** | `models_catalog.CatalogCodeMapping` | (importer) | `CatalogCodeMapping` | `catalog_code_mappings` | `/api/catalog/code-mappings` | Importer + admin | `catalog_service` (mappe categoria) | **commercial_perimeter** | `/importer` | AUTOREVOLE (system-wide seeded) |
| **Listini** | `models_parametric.ItemPricelist`, `routers/parametric.py:291-323` | `PricelistsPage.jsx`, `ParametricAdminPage.jsx`, `PricingHubPage.jsx` | `ItemPricelist` | `item_pricelists` | `/api/parametric/item-pricelists`, `/api/pricing-hub/*` | Pricelist UI + importer | **BOTH**: `catalog_service.resolve_component_prices` (matching per `entries[].code`) AND `bom_engine_v2._build_lookups_with_origin` (matching per `entries[].ref_type+ref_id`) | **BOTH** | `/pricelists`, `/parametric/admin`, `/pricing-hub` | **DUPLICATO SEMANTICO** — schema entries diverso per motore |
| **Formule** | `models_parametric.BomComponent.formula_*` | `ParametricAdminPage.jsx` | `BomComponent` | `bom_templates.components[]` | `/api/parametric/bom-templates` | ParametricAdminPage (lettura) | `parametric_engine.resolve_bom` via `_f()` | **technical_cut_list only** | `/parametric/admin` | LEGACY — mai lette da `commercial_perimeter` |
| **Vetri (schema tipo)** | `models_parametric.GlassType` | `ParametricAdminPage.jsx` | `GlassType` | `glass_types` | `/api/parametric/glass-types` | (nessuna UI create) | `bom_engine_v2._preload_anagraph` | technical_cut_list | `/parametric/admin` | LEGACY / ORFANO |
| **Ricette vetro (formule)** | Seed system, `services/recipes/glass_engine.py` | (nessuna) | schema flat structured/custom | `glass_recipes` | (nessuno CRUD user) | Seed factory + tenant admin (nessuna UI) | `perimeter_assembler.resolve_glass_recipe` | **commercial_perimeter** | (nessuna) | **AUTOREVOLE** — MA NESSUNA UI per gestirle |
| **Ferramenta** | `models_parametric.HardwareKit` | `ParametricAdminPage.jsx` | `HardwareKit` | `hardware_kits` | `/api/parametric/hardware-kits` | idem | `bom_engine_v2._preload_anagraph` | technical_cut_list | `/parametric/admin` | LEGACY / ORFANO — motore commerciale usa `products.default_hardware_kit` o `body.hardware_kit_price` |
| **Accessori** | `models_parametric.Accessory` | `ParametricAdminPage.jsx` | `Accessory` | `accessories` | `/api/parametric/accessories` | idem | `bom_engine_v2._preload_anagraph` | technical_cut_list | `/parametric/admin` | LEGACY / ORFANO |
| **Colori** | `models_parametric.Color` | `ParametricAdminPage.jsx` | `Color` | `colors` | `/api/parametric/colors` | idem | (nessuno nel motore commerciale) | technical_cut_list only | `/parametric/admin` | ORFANO per motore attivo — commercial usa solo la stringa libera `body.color_code` |
| **Categorie colore** | `models_parametric.ColorCategory` (con `is_premium`) | `ParametricAdminPage.jsx` | `ColorCategory` | `color_categories` | `/api/parametric/color-categories` | idem | `catalog_service.get_color_is_premium` (per +6% PVC) **E** `bom_engine_v2` (indirect) | **BOTH** | `/parametric/admin` | **CONDIVISA** — l'unica entità Fonte B davvero letta dal motore commerciale |
| **Config produzione** | `models_catalog.ProductionConfig` | `PricingHubPage.jsx`, `ProductCatalogPage.jsx` | `ProductionConfig` | `production_config` | `/api/catalog/production-config` | Admin UI | `perimeter_assembler` (hourly, prod_time, glass_price, glass_min, premium_pct, bar_lengths) | **commercial_perimeter** | `/pricing-hub` (parziale) | **AUTOREVOLE** — con **BUG-15** duplicato residuo su PanoramaPilot |
| **Prodotti** | `models_catalog` (extension) + `models_pricing.ProductCatalog` legacy | `ProductCatalogPage.jsx` | `ProductCatalog` + inline components | `products` | `/api/catalog/products`, `/api/product-catalog/*` | Admin UI | `perimeter_assembler.load_product` | commercial_perimeter | `/products`, `/product-catalog` | **AUTOREVOLE** |
| **Preventivi** | `models_quote`, `routers/quotes.py`, `quote_structure.py` | `QuotesPage.jsx`, `QuoteStructurePage.jsx`, `QuoteEditorPage.jsx` | `Quote` + inline `lines[]` | `quotes` | `/api/quotes/*`, `/api/quote-structure/*` | Frontend preventivatore | Ovunque | **commercial_perimeter** via `compute-and-add` (Fase 1) | `/quotes` | **AUTOREVOLE** |
| **Pricing snapshot** | inline in `quotes.lines[].pricing_snapshot` | (viewer nel preventivatore) | dict frozen | (embedded) | (no CRUD diretto) | motore | preventivo/contratto | commercial_perimeter | (embedded) | **AUTOREVOLE** — hash deterministico verificato |
| **Snapshot parametrico** | `ParametricSnapshot` | (nessuno) | `ParametricSnapshot` | `parametric_snapshots` | (auto insert in `/preview`) | `/parametric/preview` | (nessuno) | technical_cut_list | (nessuna UI) | **ORFANO** — scritti ma mai riletti dal preventivo |
| **Contratti** | `models_contracts`, `routers/contracts.py` | `ContractsPage.jsx`, `ContractViewerPage.jsx` | `Contract` | `contracts` | `/api/contracts/*` | Da quote via `create-from-quote` | ContractViewer, PDF | (deriva da quote snapshot) | `/contracts` | **AUTOREVOLE** — snapshot immutabile ereditato |
| **Lista taglio** | `models_parametric.CuttingList` + services | (nessuna UI attiva significativa) | `CuttingList` | `cutting_lists` | `/api/parametric/cutting-lists/*` | `parametric/nesting/run` + `/from-nesting` | (esporto PDF? verificare) | technical_cut_list | (assente/legacy) | LEGACY — non collegata al preventivo commerciale |
| **BOM v2 output** | `services/bom_engine_v2.resolve_bom_full` | (nessuna) | dict on-the-fly | (nessuna persistenza) | (chiamato da `pricing_modes.py`) | `parametric/preview` | idem | technical_cut_list | (nessuna) | LEGACY / IN CORSO DI USO — via /pricing-hub |
| **Price matrices** | `models_parametric.PriceMatrix` | `ParametricAdminPage.jsx` (?) | `PriceMatrix` | `price_matrices` | `/api/parametric/price-matrices` | (nessuna UI create nel frontend visto) | `pricing_modes.py` modalità A | (Modalità A pricing) | `/pricing-hub` | LEGACY / potenzialmente ORFANO |
| **Pricing mode configs** | `models_parametric.PricingModeConfig` | `PricingHubPage.jsx` | `PricingModeConfig` | `pricing_mode_configs` | `/api/parametric/pricing-modes` | Admin | `pricing_modes.compute_parametric_preview` | technical/mode-A | `/pricing-hub` | LEGACY convivente |

---

## 3 · FLOW COMPLETO DEI DATI

### Flow A — Prezzo componente telaio 5103 (motore commerciale ATTIVO)

```
UTENTE MODIFICA prezzo 5103 (color=BIANCO, price=6.50€/ml)
       │
       ▼ (via PricelistsPage o PricingHubPage)
POST /api/parametric/item-pricelists/{id}  → items_pricelists.entries[].code="5103", color_code="BIANCO", unit_price=6.50
       │
       ▼
COLLECTION: item_pricelists   (schema entry: {code, color_code, unit_price})   ← Fonte A schema
       │
       ▼ (preventivatore: POST /api/quote-structure/{qid}/openings/{oid}/products/compute-and-add)
services/perimeter_assembler.build_perimeter_input
       │
       ├── load_product(tenant, product_id)                       → products
       ├── get_component_code(product, "telaio", applies_to)      → products.components[]  → "5103"
       ├── resolve_component_prices(tenant, {"frame":"5103"}, "BIANCO")
       │         └── db.item_pricelists.find({active, pl_status:"active"})
       │                    .sort([version DESC, updated_at DESC])   (BUG-02 fix)
       │                    .entries[] filter code=="5103" AND color=="BIANCO"|""
       │                    → 6.50 €/ml
       ├── resolve_glass_recipe(tenant, product_key, frame, sash, window_type, n_sashes)  → glass_recipes
       ├── get_color_is_premium(tenant, "BIANCO")                  → color_categories.is_premium
       └── get_production_config(tenant)                          → production_config
       │
       ▼
services/recipes/commercial_perimeter.compute_perimeter(inp)
       │
       ├── external_perimeter = 2*(L+H)/1000
       ├── frame_cost = external * qty * P_FRAME(6.50) * (1+waste/100)
       └── returns PerimeterResult (breakdown completo)
       │
       ▼
quotes.lines[].pricing_snapshot = display_perimeter_dict(result)  ← IMMUTABILE
       │
       ▼
POST /api/contracts/from-quote  → contracts.pricing_snapshot = quote.pricing_snapshot (COPIA IMMUTABILE)
       │
       ▼
(lista taglio commerciale = ASSENTE. La lista taglio la genera SOLO il motore parametrico
 legacy, che legge da profile_systems/profiles/bom_templates — dati SCOLLEGATI dal motore
 commerciale che ha appena fatto il calcolo.)
```

**PROBLEMA FLOW A**: la "lista taglio commerciale" **non esiste**. Il commerciale_perimeter calcola prezzi ma non consuma barre. Se serve la lista di taglio in produzione, si deve passare al motore parametrico legacy che legge da collezioni completamente diverse (`profiles.system_id`, `bom_templates.components[].length_formula`) — non c'è coerenza forzata tra i due mondi.

### Flow B — Prezzo componente telaio 5103 (motore parametrico LEGACY)

```
UTENTE MODIFICA prezzo 5103 lato parametrico
       │
       ▼ (via ParametricAdminPage — ma la UI attualmente NON permette create/edit!)
POST /api/parametric/item-pricelists/{id}  → entries[].ref_type="profile", ref_id=<profile_id>, unit_price
       │
       ▼
COLLECTION: item_pricelists   (schema entry: {ref_type, ref_id, color_id, unit_price})   ← Fonte B schema
       │
       ▼
services/pricing_modes.compute_parametric_preview
       │
       ├── bom = bom_templates.find_one(bom_template_id)
       ├── ps  = profile_systems.find_one(bom.profile_system_id)
       └── bom_engine_v2._build_lookups_with_origin(sell_pricelist_id, ...)
                  └── db.item_pricelists.find_one({_id, ipl_status="active"})
                              .entries[] filter ref_type=="profile" AND ref_id=<X>
                              → 6.50 €/ml
       │
       ▼
parametric_engine.resolve_bom(bom_template, profile_system, params, lookup_price, lookup_cost)
       │
       ├── evaluate quantity_formula, length_formula per ogni component
       ├── apply waste, rounding, minimum_billable
       └── returns {components, materials_cost, materials_price, blocking_errors}
       │
       ▼
parametric_snapshots.insert(...)   ← MA NON collegata a quotes/contracts
       │
       ▼
(fine flow — nessun ponte verso preventivi commerciali reali)
```

**PROBLEMA FLOW B**: il risultato termina in `parametric_snapshots` che **nessun altro endpoint riutilizza**. È un ramo morto.

### Se lo STESSO entry-listino contiene sia `{code:"5103"}` (Fonte A) sia `{ref_type:"profile", ref_id:"..."}` (Fonte B):

- **Fonte A ignora** entries con `ref_type` (perché matcha su `code` stringa)
- **Fonte B ignora** entries con `code` senza `ref_id` (perché matcha su `ref_type+ref_id`)
- Risultato: **due mondi separati che condividono il container** ma **non i dati**.

---

## 4 · ANALISI /parametric/admin

**Endpoint chiamati** (grep in `ParametricAdminPage.jsx`):
- `GET /api/parametric/profile-systems`
- `GET /api/parametric/profiles`
- `GET /api/parametric/color-categories`
- `GET /api/parametric/colors`
- `GET /api/parametric/glass-types`
- `GET /api/parametric/hardware-kits`
- `GET /api/parametric/accessories`
- `GET /api/parametric/item-pricelists`
- `GET /api/parametric/price-matrices`
- `GET /api/parametric/bom-templates`
- `GET /api/parametric/pricing-modes`

**Collezioni MODIFICATE dall'UI**: **NESSUNA** (l'UI oggi è **read-only** — vedi audit v1 sez 11 conferma).

**Collezioni LETTE**: `profile_systems`, `profiles`, `color_categories`, `colors`, `glass_types`, `hardware_kits`, `accessories`, `item_pricelists`, `price_matrices`, `bom_templates`, `pricing_mode_configs`.

**Motori che usano quei dati**:
- `profile_systems`, `profiles`, `bom_templates` → **SOLO** `parametric_engine.resolve_bom` (technical_cut_list)
- `item_pricelists` → **BOTH** (con schemi entry DIVERSI — vedi §3)
- `color_categories` → **BOTH** (schema condiviso, uso identico su `is_premium`)
- `glass_types`, `hardware_kits`, `accessories` → SOLO Fonte B
- `colors` → SOLO Fonte B (Fonte A usa `color_code` stringa libera)
- `price_matrices`, `pricing_mode_configs` → SOLO Fonte B

### 🟥 RISPOSTA ALLA DOMANDA: **NO.**

**Dove il flusso si interrompe (evidenza sorgente)**:

1. **`profile_systems.tech.frame_width_mm`** viene letto da `parametric_engine.build_formula_context` (line 64-89 di `parametric_engine.py`). Ma **`perimeter_assembler.py`** (motore commerciale) **NON importa** né `parametric_engine` né i valori di `profile_systems.tech`. Vedi grep: `perimeter_assembler.py` importa `catalog_service` (che legge da `products/color_categories/production_config/item_pricelists/glass_recipes`), mai da `profile_systems`.

2. **`profiles.code = "5103"`** esiste come record in `profiles`. Ma `perimeter_assembler.get_component_code` legge da `products.components[]` (linee 42-58), mai da `profiles`. Non c'è FK tra `products.components[].code` e `profiles.code` — sono due liste indipendenti che **coincidono per convenzione** ma non per constraint.

3. **`bom_templates.components[].length_formula = "L + weld_allowance"`** viene eseguito da `parametric_engine._f()` (line 164-188). `commercial_perimeter` **non esegue formule utente** — usa formule cablate in `_compute_perimeters` (perimetro esterno = `2*(L+H)`, perimetro anta = `ext + 2H*(n-1)`) e non consulta mai `bom_templates`.

**Conclusione**: modificare una formula nel `bom_template` **non cambia** il prezzo del preventivo commerciale. Modificare `frame_width_mm` in `profile_systems.tech` **non cambia** il preventivo commerciale. Solo modificare `item_pricelists.entries[].code+unit_price+color_code` cambia il prezzo commerciale — MA `ParametricAdminPage` **non permette di farlo** (è read-only sull'UI).

---

## 5 · ANALISI MOTORE COMMERCIALE (`commercial_perimeter`)

Sorgente esatta letta (grep in `perimeter_assembler.py`):

| Voce | Collezione | Campo/percorso | Fallback | Priorità | Versionamento | Tenant scope |
|---|---|---|---|---|---|---|
| **Telaio** (`P_FRAME`) | `item_pricelists.entries[]` | `entries[?].code == products.components[category="telaio", applies_to=<n>a].code` AND `color_code IN {"", <color>}` | **nessuno** → MISSING_FRAME_PRICE | 1. exact color match  2. blank color entry | pricelist `version DESC, updated_at DESC` (BUG-02 fix) | tenant_id required |
| **Anta** (`P_SASH`) | `item_pricelists.entries[]` | `code == products.components[category="anta_standard"].code` | MISSING_SASH_PRICE | idem | idem | idem |
| **Rinforzo telaio** | `item_pricelists.entries[]` | `code == products.components[category="rinforzo_telaio"].code` | MISSING_FRAME_REINFORCEMENT_PRICE | is_reinforcement=True → colour-independent | idem | idem |
| **Rinforzo anta** | idem | `code == products.components[category="rinforzo_anta"].code` | MISSING_SASH_REINFORCEMENT_PRICE | idem | idem | idem |
| **Fermavetro** | `item_pricelists.entries[]` | `code == products.components[category="fermavetro"].code` | MISSING_GLAZING_BEAD_PRICE | 1. color 2. blank | idem | idem |
| **Scambio (meeting stile)** | `item_pricelists.entries[]` | `code == products.components[category="scambio_battuta"].code` | MISSING_MEETING_STILE_PRICE (solo se n_sashes>1) | idem | idem | idem |
| **Rinforzo scambio** | idem | `code == products.components[category="rinforzo_scambio"].code` | MISSING_MEETING_STILE_REINFORCEMENT_PRICE | is_reinforcement | idem | idem |
| **Vetro** (formula geometria) | `glass_recipes` | `product_key + window_type + number_of_sashes + status="active"` (tenant OR system-wide) | MISSING_GLASS_RECIPE | tenant-specific vince su system | recipe non versionata (solo status) | tenant OR None (system) |
| **Vetro** (prezzo €/m²) | `production_config` OR `body.glass_price_per_sqm` | `default_glass_price_per_sqm` | MISSING_GLASS_PRICE (dopo audit v1 BUG-03: NO silent default) | override body > production_config | production_config unique per tenant (BUG-15) | tenant |
| **Minimo fatturabile vetro** | `production_config` OR body | `default_glass_min_sqm` | MISSING_GLASS_MINIMUM (dopo BUG-03) | idem | idem | tenant |
| **Ferramenta** (`P_HARDWARE`) | `body.hardware_kit_price` OR `products.default_hardware_kit.price` | — | MISSING_HARDWARE_PRICE (a meno di `hardware_not_required=True`) | body override wins | inline nel product | tenant (via product) |
| **Manodopera oraria** | `production_config` OR body | `hourly_cost` | MISSING_HOURLY_COST | body override wins | tenant | tenant |
| **Tempo produzione** | `production_config` | `{fixed|one|two|three|four}_sash_time_minutes` OR `production_time_default_minutes` OR body override | MISSING_PRODUCTION_TIME | body override > sash-specific > default | tenant | tenant |
| **Margine** (markup) | `production_config` OR body | `default_margin_pct` | MISSING_MARGIN | body override wins | tenant | tenant |
| **Posa** (installation) | `body.installation_cost` | — | MISSING_INSTALLATION_PRICE se `installation_declared_zero=False` | body only, NO production_config default | — | — |
| **Trasporto** | `body.transport_cost` | — | default 0 (accettato senza flag) | body only | — | — |
| **Accessori** | `body.accessory_cost` | — | default 0 | body only | — | — |
| **Altri componenti** (`additional_material_cost`) | `body.other_components_cost` OR `products.default_other_components_cost` | — | MISSING_ADDITIONAL_COMPONENTS_COST se `other_components_declared_zero=False` | body override wins | inline in product | tenant |
| **Colore Premium (+6% PVC)** | `color_categories` | `is_premium` cercato tramite `body.color_code → matching category` OR body `is_color_premium` | default False | body override wins | — | tenant |
| **Sfrido componente** (`WASTE_*`) | `products.components[].waste_percentage` | inline | 0% (default silent — accettabile: significa "no sfrido") | — | inline product | tenant |
| **Lunghezza barra** | `production_config.default_bar_length_pvc_mm/reinforcement_mm` | — | tecnico standard (6500/6000) — default silent accettabile | — | tenant | tenant |
| **Sconto** | `body.discount_amount` | — | 0 | body only | — | — |

**Nessuno di questi legge da `profile_systems`, `profiles`, `bom_templates`, `pricing_mode_configs`, `price_matrices`, `glass_types`, `hardware_kits`, `accessories`, `colors`.**

---

## 6 · ANALISI MOTORE TECNICO (`technical_cut_list` / `parametric_engine`)

Sorgente esatta letta (grep in `parametric_engine.py` + `bom_engine_v2.py`):

| Voce | Collezione | Campo | Note |
|---|---|---|---|
| **Componenti (lista)** | `bom_templates.components[]` | `component_type, ref_id, role, quantity_formula, length_formula, width_formula, height_formula, area_formula, condition[], waste_pct, ...` | La lista è **definita nel BOM template** — non risalgono a `products` |
| **Codici articolo** | `profiles.code / glass_types.code / hardware_kits.code / accessories.code` | Via `_preload_anagraph` che fa lookup `ref_id → doc.code` | **Nessuna coerenza forzata** con `products.components[].code` |
| **Formule** | `bom_templates.components[].quantity_formula/length_formula/...` | Parser AST via `services/formula.eval_formula(strict=True)` | Diverse dalle formule cablate in `commercial_perimeter._compute_perimeters` |
| **Barre** (lunghezza usabile) | `profile_systems.tech.bar_length_mm - bar_head_offcut - bar_tail_offcut` | Sistema profilo determina | Fonte diversa da `production_config.default_bar_length_pvc_mm` |
| **Rinforzi** | `bom_templates.components[]` con `role="reinforcement_frame|sash"` | idem | Nessun link a `products.components[].category="rinforzo_*"` |
| **Saldature** (weld_allowance) | `profile_systems.tech.weld_allowance_mm` | context formula | Nessun link a `body.weld_allowance_mm` del motore commerciale (che pure lo prevede) |
| **Kerf** (larghezza lama) | `profile_systems.tech.kerf_mm` | Nesting engine | Non presente nel motore commerciale |
| **Sfridi** | `bom_templates.components[].waste_pct/scrap_fixed_mm_per_cut/scrap_fixed_per_piece` | Diverso da `products.components[].waste_percentage` del motore commerciale | Duplicazione concettuale |
| **Residui minimi riutilizzabili** | `profile_systems.tech.min_reusable_scrap_mm` | Nesting engine + `ScrapStock` | Concetto assente dal motore commerciale |
| **Ottimizzazione taglio (nesting)** | `services/nesting.py` (FFD/BFD) su `NestingCut[]` derivati da BOM resolved | — | Genera `CuttingList` — non collegata a quote lines commerciali |

**Il motore tecnico usa dati COMPLETAMENTE diversi dal motore commerciale**, tranne per la collezione `item_pricelists` (condivisa ma con schema entries diverso).

---

## 7 · ANALISI DUPLICAZIONI

| Duplicazione | Dove nasce | Perché esiste | Chi la usa | Criticità |
|---|---|---|---|---|
| **Sistema profilo** in `profile_systems.tech` vs **valori tecnici** cablati in `production_config` (bar_length, ecc.) | Design storico + audit v1 | Motore commerciale non voleva dipendere dal legacy parametric | Fonte B legge da `profile_systems.tech`, Fonte A da `production_config` | **HIGH** — se admin cambia `frame_width_mm` in ProfileSystem, il commerciale non se ne accorge |
| **Componente** in `products.components[]` (con `code`, `category`, `applies_to`) vs `profiles` (con `code`, `role`, `system_id`) | Fonte A additive-only, non toccò Fonte B | Doppio catalogo componenti | Fonte A → motore commerciale, Fonte B → motore tecnico | **CRITICAL** — divergenza silente possibile: la stessa "profilo 5103" può avere prezzo diverso a seconda del motore |
| **item_pricelists.entries[]** dual-schema | additive-only extension per motore commerciale | `entries[]` accetta entrambe le convenzioni | Fonte A filtra per `.code`, Fonte B per `.ref_type+ref_id` | **CRITICAL** — se un admin inserisce 2 entry per lo stesso "prezzo profilo 5103 bianco", una per Fonte A e una per Fonte B, e i prezzi divergono, i due motori restituiscono numeri diversi senza warning |
| **Formule quantità/lunghezza** in `bom_templates` vs formule cablate in `commercial_perimeter.py` | Design diverso: commerciale =  formule cablate spec-approvate; parametrico = formule libere user-defined | Motori diversi | Sono formule DIVERSE per definizione — ma dovrebbero fornire numeri coerenti sulla stessa geometria | **HIGH** — nessun test verifica coerenza dei perimetri computati dai due motori |
| **Sfrido** in `products.components[].waste_percentage` vs `bom_templates.components[].waste_pct` | Additive extension | Doppia semantica sfrido | Fonte A / Fonte B | **HIGH** — potenziali risultati diversi |
| **Ferramenta prezzo** in `products.default_hardware_kit.price` vs `hardware_kits.indicative_price` vs `item_pricelists.entries[ref_type=hardware]` | Design a strati | Multiple fallback | Motore commerciale usa il primo + body override; motore tecnico usa `item_pricelists` FK | **MEDIUM** |
| **Vetro dimensioni** in `glass_recipes` (Fonte A) vs `bom_templates.components[type="glass"].width_formula/height_formula/area_formula` (Fonte B) | Design storico | Due modi di calcolare l'area vetro | Fonte A structured/custom limitato, Fonte B formula libera | **HIGH** — divergenza numerica silente |
| **`production_config`** con 2 doc sul tenant PanoramaPilot | BUG-15 audit v1 | Doppia insert storica senza unique index | `get_production_config` fa `find_one` (non deterministico) | **HIGH** — script cleanup pronto |

---

## 8 · FONTE AUTOREVOLE PROPOSTA

Per ogni categoria, **UNA sola fonte** deve essere autorevole. Proposta (Opzione B ridotta):

| Categoria | Fonte autorevole proposta | Motivazione |
|---|---|---|
| **Sistema profilo** | `products` (estendere con `profile_system: {code, name, material, tech: {...}}` inline) | Il motore commerciale è già collegato a `products`. Portare i valori tecnici del sistema dentro il product elimina il salto tra le due fonti. |
| **Profili singoli / componenti** | `products.components[]` (unica lista) — arricchita con `code, category, applies_to[], role, waste_percentage, bar_length_override_mm, weight_per_m_kg, is_cutting_relevant` | Elimina `profiles`. Il motore tecnico legge la stessa lista con lookup per `code+category`. |
| **Listino** | `item_pricelists` con schema entry **UNIFICATO**: `{code, color_code, unit_price, unit, ref_type?}` — `ref_type` opzionale come tag, ma la chiave di join primaria è **sempre `code`** | Elimina divergenza schema. Un solo lookup per entrambi i motori. |
| **Formule vetro** | `glass_recipes` (già authorative per motore commerciale — estendere con `formula_type=custom` sicuro) | Elimina l'uso di `bom_templates.components[type="glass"].width_formula` |
| **Formule tecniche (BOM parametrica)** | `products.components[].formula_qty / formula_cut` + optional formula extension | Riutilizzare i campi già presenti in `ProductComponentAssoc` (models_catalog line 43-44) invece di `bom_templates.components[].quantity_formula` |
| **Configurazione produzione** | `production_config` (dopo cleanup BUG-15 + unique index) | Includere `bar_length_pvc_mm`, `bar_length_reinforcement_mm`, `kerf_mm`, `weld_allowance_mm`, `hourly_cost`, etc. Elimina duplicazione con `profile_systems.tech` |
| **Colori** | `color_code` come stringa libera + `color_categories.is_premium` (già condivisa) | Elimina collezione `colors` (usata solo da Fonte B) o mantienila come lookup UI ma NON come sorgente di prezzo |
| **Categorie colore** | `color_categories` (già condivisa) | Rimane. Aggiungere flag `charges_whole_bar` già presente ma non letto dal commerciale — deferito |
| **Ferramenta / Accessori / Vetro tipo** | come **sotto-tipo di `products`** (product.subtype="hardware|accessory|glass") OPPURE mantenere `hardware_kits/accessories/glass_types` MA leggibili tramite lo stesso resolver | Deferire scelta — impatta modello dati |

**Fonti da ELIMINARE dopo la migrazione**: `profile_systems`, `profiles`, `bom_templates`, `pricing_mode_configs`, `price_matrices`, `parametric_snapshots`, `bar_optimization_runs`. Solo dopo dry-run + snapshot verify.

**Fonti da MANTENERE ma ridurre**: `colors` (solo UI lookup), `hardware_kits/accessories/glass_types` (solo se non spostati in `products` come subtype).

---

## 9 · RESOLVER UNIFICATO (design)

```
┌──────────────────────────────────────────────────────────────────┐
│                      ProfileSystemResolver                         │
│  (unica funzione async che risolve TUTTO ciò che serve al motore) │
│                                                                    │
│  input:  tenant_id, product_id_or_key, color_code,                 │
│          window_type, number_of_sashes                             │
│                                                                    │
│  output: ResolvedContext {                                         │
│    product: Product (inline components + inline profile_system.tech)│
│    prices: {frame, sash, glazing_bead, meeting_stile,              │
│             reinforcement_frame, reinforcement_sash,               │
│             reinforcement_meeting_stile, hardware}                 │
│    color_category: {code, is_premium, scrap_mode}                  │
│    glass_recipe: {formula_type, structured|custom}                 │
│    glass_price: float, glass_min_sqm: float                        │
│    production_config: {hourly_cost, production_time_by_sashes,     │
│                        margin_pct, bar_length_pvc,                 │
│                        bar_length_reinforcement, premium_pct,      │
│                        kerf_mm, weld_allowance_mm}                 │
│    pricelist_version: str  ← per snapshot                          │
│    missing: List[str]      ← MISSING_* espliciti                   │
│  }                                                                 │
└──────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴────────────────┐
              ▼                                 ▼
    commercial_perimeter                technical_cut_list
    (letto già in Fase 1)               (nuovo wrapper: legge
                                         le STESSE prices+config+
                                         profile.tech DAL RESOLVER)
              │                                 │
              ▼                                 ▼
    quote.lines[].pricing_snapshot      cutting_lists[] (persistenza)
              │                                 │
              ▼                                 ▼
    contracts.pricing_snapshot          production orders
              │                                 │
              └──────────┐          ┌──────────┘
                         ▼          ▼
                    PDF (WeasyPrint templates)
```

**Regole di implementazione del resolver**:
1. **Un solo file**: `app/services/profile_system_resolver.py`
2. **Un solo Pydantic model** `ResolvedContext` che rappresenta tutto ciò che serve
3. **Nessuna chiamata a `parametric_engine`** dal motore commerciale (già così)
4. **Il motore tecnico** deve essere modificato per chiamare il resolver invece di leggere direttamente da `profile_systems`+`profiles`+`bom_templates`
5. **Test contract**: given(product_id, color, W, H, n_sashes) → same_prices_for_both_engines
6. **Nessun fallback silent**: ogni MISSING_* propagato ai blocking_errors

---

## 10 · NESSUN SISTEMA PARALLELO — vincoli confermati

Al termine della migrazione **NON esistono**:
- ✅ sincronizzazioni background job (che leggono da B e scrivono in A)
- ✅ mirror di collezioni
- ✅ export/import batch
- ✅ adapter temporanei runtime
- ✅ bridge classes
- ✅ doppie scritture (POST che aggiorna sia products che profiles)
- ✅ mapper di emergenza
- ✅ dati replicati

**Una sola verità. Tutti leggono quella tramite `ProfileSystemResolver`.**

---

## 11 · CLASSIFICAZIONE BUG

### 🔴 CRITICAL

| ID | Bug | Impatto | Rischio | Probabilità | Soluzione |
|---|---|---|---|---|---|
| **ARCH-01** | Due fonti autorevoli parallele (`products+item_pricelists` vs `profile_systems+profiles+bom_templates+item_pricelists`) | Ammin che aggiornano una fonte non aggiornano l'altra → preventivi con prezzi vecchi | Alto | 100% oggi | Migrazione a fonte unica (Opzione B ridotta) |
| **ARCH-02** | `item_pricelists.entries[]` schema dual — stesso container, due semantica di join | Prezzi divergenti tra motore commerciale e tecnico | Alto | Media (dipende da chi popola) | Unificare schema entry con `code` chiave primaria |
| **ARCH-03** | `ParametricAdminPage.jsx` scollegata dal motore commerciale | Admin che pensa di configurare il preventivo NON lo configura | Blocca operatività | 100% | Rewrite UI dopo migrazione (fuori scope audit) |

### 🟠 HIGH

| ID | Bug | Impatto | Soluzione |
|---|---|---|---|
| **ARCH-04** | Valori tecnici (`bar_length_mm`, `kerf_mm`, `weld_allowance_mm`) duplicati in `profile_systems.tech` vs `production_config` | Motori usano valori diversi | Consolidare in `production_config` (o in `products.profile_system.tech` inline) |
| **ARCH-05** | Sfrido duplicato: `products.components[].waste_percentage` vs `bom_templates.components[].waste_pct` | Risultati diversi | Consolidare in `products.components[]` |
| **ARCH-06** | Nessuna FK tra `products.components[].code` e `profiles.code` — divergenza silente | Errore commerciale non rilevabile automaticamente | Aggiungere validazione oppure eliminare `profiles` |
| **ARCH-07** | `parametric_snapshots` scritti ma mai riletti (collezione ORFANA) | Storage sprecato | Rimuovere dopo migrazione |
| **BUG-15** | `production_config` duplicato per PanoramaPilot | `find_one` non deterministico | Script `cleanup_production_config_duplicates.py` (già pronto) |

### 🟡 MEDIUM

| ID | Bug | Impatto | Soluzione |
|---|---|---|---|
| **ARCH-08** | `colors` collection scritta ma solo per lookup UI, prezzo motore commerciale usa stringa libera | Non-blocking ma confuso | Documentare come "lookup only" |
| **ARCH-09** | `price_matrices` collection presente ma solo Modalità A pricing legacy | Codice non usato in preventivo attivo | Rimuovere post-migrazione |
| **ARCH-10** | `pricing_mode_configs` scope tenant/product/quote_line può conflittare con `production_config` | Comportamento imprevedibile | Consolidare in un solo entry point config |
| **ARCH-11** | Nessuna UI per gestire `glass_recipes` autoritative (motore commerciale) | Admin non può correggere errori formule vetro | Aggiungere UI dopo migrazione |

### 🟢 LOW

- **ARCH-12** Molte librerie backend/frontend installate mai usate (vedi `AUDIT_PLUGINS_V1.md`) — pulizia bundle
- **ARCH-13** `default_hardware_kit` inline nel product vs `hardware_kits` collezione — deferire

---

## 12 · PIANO DI MIGRAZIONE

**Vincolo**: nessuna implementazione fino ad approvazione esplicita dell'utente su questo documento.

### Fase 0 — AUDIT (completata)
- **Deliverable**: questo documento (`ARCHITECTURAL_AUDIT_V2.md`)
- **Durata**: 3h (completata)
- **Rollback**: N/A
- **Rischi**: N/A (read-only)
- **Test**: N/A

### Fase 1 — Creazione modello unico
- **Deliverable**:
  - Estensione `ProductComponentAssoc` (models_catalog) con campi tecnici mancanti: `role`, `bar_length_override_mm`, `weight_per_m_kg`, `is_cutting_relevant`, `formula_qty`, `formula_length`, `formula_area`
  - Estensione `Product` con `profile_system_inline: {code, name, material, tech: {bar_length_pvc_mm, bar_length_reinforcement_mm, kerf_mm, weld_allowance_mm, min_reusable_scrap_mm, ...}}`
  - Estensione `ProductionConfig` con eventuali campi mancanti (kerf_mm, weld_allowance_default_mm)
  - Schema unificato `item_pricelists.entries[]` con documentazione: `{code REQUIRED, color_code, unit_price, unit, ref_type?, ref_id?}` — chiave di join sempre `code`
- **Durata**: 2 giorni
- **Rollback**: git revert modello (nessun dato ancora migrato)
- **Rischi**: BASSO (additive-only, non tocca dati esistenti)
- **Test**: unit test schema `product.profile_system_inline`

### Fase 2 — Migrazione dati (DRY-RUN → APPLY)
- **Deliverable**:
  - Script `migrate_parametric_to_products.py` (dry-run default): per ogni `profile_systems` popola `products[].profile_system_inline`
  - Script `migrate_profiles_to_components.py`: per ogni `profiles` cerca `products.components[]` con `code` corrispondente e copia i campi mancanti (role, weight_per_m_kg); se non esiste, crea entry
  - Script `unify_pricelist_entries.py`: per ogni `item_pricelists.entries[]` con `ref_type+ref_id` risolve il `code` dal profile referenziato e popola `entries[].code`
- **Durata**: 3 giorni
- **Rollback**: dump MongoDB **prima** dell'apply. Rollback = ripristino da dump
- **Rischi**: MEDIO-ALTO (modifica dati produzione)
- **Test**: dopo dry-run confrontare **counts before/after** + **checksum** per tenant

### Fase 3 — Implementazione `ProfileSystemResolver`
- **Deliverable**: `app/services/profile_system_resolver.py` con `resolve(tenant_id, product_id, color_code, window_type, n_sashes) -> ResolvedContext`
- **Durata**: 3 giorni
- **Rollback**: revert file
- **Rischi**: BASSO (nuovo file, non tocca esistenti finché non wire-in)
- **Test**: 20+ unit test scenari (product mancante, colore, listino, formule vetro, config incompleta)

### Fase 4 — Wire-in motore commerciale
- **Deliverable**: `perimeter_assembler.build_perimeter_input` refactor per usare `ProfileSystemResolver`
- **Durata**: 2 giorni
- **Rollback**: git revert (motore già funzionante come baseline)
- **Rischi**: MEDIO (potrebbe cambiare snapshot hash → dovrebbe rimanere identico se resolver produce stessi dati)
- **Test**: **contract test** — dato lo stesso input, il preventivo pre-refactor e post-refactor deve produrre lo stesso `sale_price` e lo stesso `pricing_snapshot_hash`

### Fase 5 — Wire-in motore tecnico
- **Deliverable**: `bom_engine_v2.resolve_bom_full` refactor per NON leggere più da `profile_systems`+`profiles`+`bom_templates.components[]` ma dal `ProfileSystemResolver`
- **Durata**: 3 giorni
- **Rollback**: git revert
- **Rischi**: MEDIO (formule utente-defined potrebbero non essere completamente rimappabili → identificare gap in Fase 0/1)
- **Test**: **contract test** — dato lo stesso input, la lista taglio pre/post refactor produce gli stessi tagli

### Fase 6 — Preventivatore
- **Deliverable**: nessuna modifica al preventivatore (motore già usa `perimeter_assembler` refactored)
- **Durata**: 0 (verifica solo)
- **Rischi**: BASSO
- **Test**: E2E preventivo completo lead→firma con snapshot check

### Fase 7 — Contratti
- **Deliverable**: nessuna modifica (contratto deriva da `quote.pricing_snapshot` immutabile — snapshot stesso pre/post)
- **Durata**: 0
- **Rischi**: BASSO
- **Test**: contratti generati pre-migration devono rimanere immutati

### Fase 8 — Pulizia legacy
- **Deliverable**:
  - Rimozione `parametric.py` endpoints per collezioni deprecate (profile_systems, profiles, bom_templates, price_matrices, pricing_mode_configs)
  - Rewrite `ParametricAdminPage` come `SystemFormulaPage` collegata a `products`
  - Drop collezioni `profile_systems`, `profiles`, `bom_templates`, `price_matrices`, `pricing_mode_configs`, `parametric_snapshots`, `bar_optimization_runs` (dopo verifica zero-referenze)
- **Durata**: 4 giorni (2 backend + 2 frontend)
- **Rollback**: git revert + ripristino da dump
- **Rischi**: ALTO (drop dati definitivo)
- **Test**: verifica che nessun endpoint attivo referenzi le collezioni droppate

### Totale
- **~17 giorni-uomo** (best case, senza imprevisti)
- **Ordine strettamente sequenziale**: Fase 1→2→3→4→5→6→7→8

---

## 13 · TEST DI ACCETTAZIONE FINALE (scenario obbligatorio)

Riprende sez 21 del prompt audit precedente + il nuovo scenario 15-step. Verde solo quando:

```
1.  admin crea sistema profilo "ProEvolution" (product.profile_system_inline)      ✅
2.  admin aggiunge componente "5103" categoria=telaio applies_to=finestra_1a      ✅
3.  admin aggiunge componente "12130" categoria=anta applies_to=finestra_1a       ✅
4.  admin aggiunge rinforzi 4133/4135                                             ✅
5.  admin aggiunge fermavetro                                                     ✅
6.  admin crea item_pricelist con entries per BIANCO (schema unificato)           ✅
7.  admin pubblica il listino (ipl_status=active)                                 ✅
8.  admin approva glass_recipe per (ProEvolution, 1-anta, apribile)               ✅
9.  admin imposta production_config (hourly, prod_time, margin, glass_price)      ✅
10. commercial_perimeter.compute → sale_price=X€, MISSING_*=[]                     ✅
11. technical_cut_list.resolve → cuts=[...] con codes match products.components[] ✅
12. crea preventivo → line con pricing_snapshot=snap1, hash=h1                    ✅
13. genera contratto → contract.pricing_snapshot == snap1, hash uguale            ✅
14. admin modifica prezzo entry BIANCO da 6.50 a 7.00, pubblica v2                ✅
15. il preventivo del punto 12 → sale_price INVARIATO, hash INVARIATO             ✅
16. nuovo preventivo con stesso input → sale_price nuovo (7.00 * perimetri), h2   ✅
```

Ogni step deve avere un **automated test** con evidence (assertion + response body).

**Solo dopo tutti i 16 step verdi il refactor è concluso.**

---

## 14 · REGOLE RISPETTATE

- ✅ Nessuna nuova funzionalità implementata in questa iterazione
- ✅ Nessuna modifica al frontend
- ✅ Nessuna modifica al wizard
- ✅ Nessuna modifica alla firma
- ✅ Nessun plugin aggiunto
- ✅ Nessun plugin rimosso
- ✅ Nessuna nuova pagina creata
- ✅ Nessuna nuova collection creata
- ✅ Nessun nuovo sistema creato
- ✅ Nessun refactoring estetico

---

## 15 · DELIVERABLE — quali sono e dove trovarli

| # | Deliverable | Location |
|---|---|---|
| 1 | Mappa completa del sistema | Questo file — §2 |
| 2 | Diagrammi dei flussi | §3 (Flow A + Flow B) |
| 3 | Duplicazioni trovate | §7 (con criticità) |
| 4 | Fonte autorevole proposta | §8 |
| 5 | Resolver unificato (design) | §9 |
| 6 | Bug classificati | §11 (CRITICAL/HIGH/MEDIUM/LOW) |
| 7 | Piano di migrazione | §12 (8 fasi con durata/rollback/rischi/test) |
| 8 | Rischi | §11 + §12 per fase |
| 9 | Rollback | §12 per fase + tag git `pre-audit-v1-2026-02` esistente + backup MongoDB pre-Fase 2 |
| 10 | Test di accettazione | §13 (16 step) |

---

## 🛑 STATO ATTUALE

**Nessuna implementazione è iniziata. Il documento è pronto per revisione.**

**Attende approvazione esplicita dell'utente per procedere con Fase 1.**

Se l'utente vuole aggiustamenti al piano (durate, ambito, ordine fasi), può richiederli qui prima dell'approvazione finale.

---

## Criterio di successo (ricordato)

Il sistema sarà considerato corretto **solo quando**:
- Esiste **UNA sola fonte autorevole** per ogni categoria (§8)
- Il motore commerciale (`commercial_perimeter`) e il motore tecnico (`technical_cut_list`) leggono **esclusivamente** da quella fonte tramite `ProfileSystemResolver` (§9)
- Nessuna duplicazione, sincronizzazione, adapter temporaneo (§10)
- Test di accettazione 16-step **tutti verdi** (§13)

**Documento chiuso.**
