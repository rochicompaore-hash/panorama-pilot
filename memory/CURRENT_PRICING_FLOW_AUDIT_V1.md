# CURRENT_PRICING_FLOW_AUDIT_V1

**Data:** 2026-08-07  
**Modalità:** SOLO ANALISI — nessuna modifica al codice, nessun seed, nessuna migrazione  
**Ambito:** Come Panorama Pilot (Infissi Express Cloud) calcola OGGI un prezzo, con evidenze dirette dal codice e dai dati.

---

## 0. TL;DR — Verdetto finale

**Classificazione architetturale: C — ARCHITETTURA TRANSITORIA CON COMPONENTI LEGACY**

Il preventivatore commerciale utilizza **un solo motore attivo** (`commercial_perimeter`), che è **coerente e produce snapshot con hash**. Ma:

- Non è ancora la nuova architettura target (mancano `ProfileSystemResolver`, `BomResolver`, `TechnicalCostResolver`, `CommercialPricingService`)
- Coesistono **8 servizi/moduli pricing** nel codice, di cui solo 1 nel flusso operativo commerciale
- Le **fonti dati sono duplicate** tra Sistema A (usato) e Sistema B parametric (non collegato)
- Le **formule Excel V1_3** (soglia ribassata, scambio battuta, montante, traverso, pellicolato +10%) **NON sono implementate**
- Il costo tecnico è calcolato con approccio **perimetrale + sfrido + waste_pct**, non tramite BOM ricette reali

**Il preventivo produce un prezzo, ma non è ancora un vero costo industriale — è una semplificazione perimetrale.**

---

## 1. Caso reale tracciato: ProEvolution 900×1500, 1 anta, bianco, doppio vetro

### 1.1 Percorsi che possono produrre un prezzo — mappa completa

| # | Route frontend | Componente | Endpoint chiamato | Servizio backend | Motore | Attivo commercialmente? |
|---|---|---|---|---|---|---|
| 1 | `/quote-structure` (Catalogo prodotti) | `QuoteStructurePage.jsx` → `addProduct()` | `POST /api/quote-structure/openings/{id}/products` | `quote_structure.py::add_product` | **Nessun motore** — accetta `unit_price` manuale | ✅ (percorso attuale della UI ma NON usa il motore) |
| 2 | `/quote-structure` compute-and-add | *(non presente nella UI attuale)* | `POST /api/quote-structure/{quote_id}/openings/{opening_id}/products/compute-and-add` | `quote_structure.py::compute_and_add_product` → `perimeter_assembler.run_perimeter_simulation` | **`commercial_perimeter`** | ✅ Esiste ma UI non lo chiama |
| 3 | `/product-simulator` | `ProductSimulatorPage.jsx` → `runSimulation()` | `POST /api/catalog/products/{pid}/simulate` | `catalog.py::simulate_product` → `perimeter_assembler.run_perimeter_simulation` | **`commercial_perimeter`** (default) o `technical_cut_list` (legacy) | ✅ Tool tecnico |
| 4 | `/quote-structure/products/{line_id}/recompute` | *(bottone recompute nella UI)* | `POST /api/quote-structure/products/{line_id}/recompute` | `quote_structure.py::recompute` → stesso motore | **`commercial_perimeter`** | ✅ |
| 5 | Motore preventivi legacy | `QuoteEditorPage.jsx` (esistente ma legacy) | `POST /api/quotes/{id}/lines` | `quotes.py` + `services/pricing.py::compute_line` + `services/pricing_v2.py::compute_line_v2` | **`compute_line`** (surcharges/discounts su `base_price`) | ⚠️ Legacy, ancora chiamato dai preventivi vecchi |
| 6 | `/pricing-hub` | `PricingHubPage.jsx` | `POST /api/pricing-hub/simulate` | `pricing_hub.py::simulate` | Metodi **A/B/C/D/E/F/G/H** (per_sqm, tabular, per_piece, per_linear, bom, hybrid, formula, manual) | ⚠️ Sperimentale, non chiamato dal preventivatore serramenti |
| 7 | `/parametric/*` | `ParametricConfiguratorPage.jsx` + `ParametricAdminPage.jsx` | `POST /api/parametric/preview` | `parametric.py::preview` → `services/pricing_modes.compute_parametric_preview` → `parametric_engine.resolve_bom` | **`parametric_engine`** | ⚠️ Isolato — NESSUN preventivo lo chiama |

### 1.2 Percorso ATTUALE reale (E2E dalla UI del preventivatore attuale)

Il file `QuoteStructurePage.jsx` (linea 108-135) mostra che oggi la UI usa il vecchio `POST /api/quote-structure/openings/{id}/products` con `unit_price` **inserito manualmente**:

```js
// QuoteStructurePage.jsx, linea 110-123
await api.post(`/quote-structure/openings/${addProdCtx.opening_id}/products`, {
  role: prodForm.role,
  product_type_code: prodForm.product_type_code || null,
  description: prodForm.description,
  configuration: {...},
  dimension_source: "inherited",
  unit_price: Number(prodForm.unit_price || 0),   // ← PREZZO MANUALE
});
```

**Conseguenza operativa:** oggi il flusso commerciale in UI **NON invoca il motore commercial_perimeter**. Il commerciale inserisce a mano il prezzo.  
Il motore esiste (`compute-and-add`), è funzionante (verificato in iter40, 3/3 test verdi, sale_price=356.29€), ma **non ha ancora un'interfaccia**.

---

## 2. Formula reale eseguita OGGI (commercial_perimeter v1.0.0)

Per ProEvolution 900×1500, 1 anta, BIANCO, doppio vetro standard, `installation_declared_zero=true`, `other_components_declared_zero=true`. Riferimento diretto: `services/recipes/commercial_perimeter.py::compute_perimeter`.

### 2.1 Passi calcolati dal motore

| Passaggio | Formula reale nel codice | Input | Risultato |
|---|---|---|---|
| **Perimetro esterno** (`external_perimeter_ml`) | `2 * (L/1000 + H/1000)` | L=900, H=1500 | 4.8 ml |
| **Perimetro anta** (`sash_perimeter_ml`) | `ext + 2 * H_m * (n_sashes-1)` | n_sashes=1 | 4.8 ml (nessuna aggiunta) |
| **Meeting stile ml** | `H_m * (n_sashes-1)` | n_sashes=1 | 0.0 ml |
| **Consumo ml (con waste)** | `net_ml * (1 + waste_pct/100)` | waste=5% (da product.components) | telaio: 5.04 ml (con listino test-motor: 4.8 * 1.05) |
| **Telaio** (`frame_cost`) | `ml_consumption["telaio"] * P_FRAME` | 5.04 * 8.50 €/ml | 42.84 € (o 40.80 se waste=0) |
| **Rinforzo telaio** | `ml_consumption["rinforzo_telaio"] * P_FRAME_REINFORCEMENT` | 4.8 * 3.10 (waste 0%) | 14.88 € |
| **Anta** | `ml_consumption["anta"] * P_SASH` | 4.8 * 9.20 (waste 5% → 5.04*9.20) | 46.37 € |
| **Rinforzo anta** | `ml_consumption["rinforzo_anta"] * P_SASH_REINFORCEMENT` | 4.8 * 3.30 | 15.84 € |
| **Fermavetro** | `ml_consumption["fermavetro"] * P_GLAZING_BEAD` | 4.8 * 2.20 | 10.56 € |
| **Scambio battuta** | *(solo se n_sashes > 1)* | n_sashes=1 → NON APPLICATO | 0.0 € |
| **Vetro area** | `(gw * gh) / 1_000_000` | gw=694mm, gh=1294mm (glass_recipe strutturata) | 0.898036 m² |
| **Vetro fatturabile** | `max(area_real, MIN_GLASS_SQM)` | max(0.898, 0.5) | 0.898036 m² |
| **Costo vetro** | `billable_sqm * quantity * P_GLASS_SQM` | 0.898 * 1 * 76 | 68.25 € |
| **Ferramenta** | `P_HARDWARE` (valore fisso, non €/ml) | 45.00 € | 45.00 € |
| **Additional cost** | *(dichiarato zero)* | declared_zero=true | 0.00 € |
| **Premium PVC (+6%)** | `pvc_base * premium_pct/100` (SOLO se `is_color_premium=True`) | Bianco = non premium | 0.00 € |
| **Materiali totali** | `profile_cost + glass_cost + hardware_cost + additional + premium` | 126.24 + 68.25 + 45 + 0 + 0 | **239.49 €** |
| **Manodopera** | `(production_time_minutes / 60) * hourly_cost` | (30 / 60) * 30 | **15.00 €** |
| **Costo produzione** | `materials_cost + labor_cost` | 239.49 + 15 | **254.49 €** |
| **Servizi** | `installation + transport + disposal + accessory` | tutti 0 (declared_zero) | 0.00 € |
| **Costo interno totale** | `production_cost + service_cost` | 254.49 + 0 | **254.49 €** |
| **Sale price before discount** | `total_internal * (1 + margin_pct/100)` | 254.49 * 1.40 | **356.29 €** |
| **Discount** | `discount_amount` | 0 | 0.00 € |
| **Sale price** | `sale_before - discount` | 356.29 - 0 | **356.29 €** |

### 2.2 Componenti NON calcolati oggi dal motore (per questo caso)

| Componente | Presente nel V1_3 | Nel motore attuale | Nota |
|---|---|---|---|
| Scambio battuta (`h × 5.5`) | ✅ | ⚠️ Come €/ml, non come formula V1_3 | Attivo solo per n_sashes>1 |
| Soglia ribassata (`h × 29.5 + 7.49`) | ✅ | ❌ **NON CALCOLATO DAL MOTORE ATTUALE** | Nessuna variabile input |
| Montante fisso (`h × 7.51 × q`) | ✅ | ❌ **NON CALCOLATO DAL MOTORE ATTUALE** | Non esiste input `mullion_count` |
| Traverso (`w × 7.50 × q`) | ✅ | ❌ **NON CALCOLATO DAL MOTORE ATTUALE** | Non esiste input `transom_count` |
| Pellicolato +10% (solo profili PVC eleggibili) | ✅ | ⚠️ Applica +6% (premium_pvc_surcharge_pct) su `pvc_base` che include telaio+anta+fermavetro+scambio | Percentuale diversa e scope diverso |
| Rinforzo scambio | ✅ | ✅ | OK |
| Colore interno vs esterno separati | ⚠️ | ❌ **NON GESTITO** | Un solo `color_code` |

---

## 3. Confronto con formule aziendali approvate (V1_3 + Golden Test)

| Regola | Formula approvata (V1_3) | Formula attuale | Uguale? | Gravità |
|---|---|---|---|---|
| Telaio | `ml_consumption × price €/ml × (1 + waste_%)` | idem | ✅ Sì | — |
| Rinforzo telaio | `ext_perimeter × price €/ml` | idem | ✅ Sì | — |
| Anta | `sash_perimeter × price €/ml × (1 + waste_%)` | idem | ✅ Sì | — |
| Rinforzo anta | `sash_perimeter × price €/ml` | idem | ✅ Sì | — |
| Fermavetro | `sash_perimeter (apribile) OR ext (fissa) × price` | idem | ✅ Sì | — |
| **Vetro** | `max(real_area, 0.50) × price €/m² × quantity` (DOUBLE_STANDARD=76 €/m²) | `max(area, MIN_GLASS_SQM) × quantity × P_GLASS_SQM` | ✅ Sì (con seed P0 76€/0.50m²) | — |
| **Scambio battuta** | `height_mm/1000 × 5.50` (importo fisso €/pz) | `ml_consumption × price €/ml` (dal listino) | ⚠️ Formula diversa | **HIGH** |
| **Soglia ribassata (1 anta)** | `height_mm/1000 × 29.50 + 7.49` | ❌ NON CALCOLATA | ❌ No | **CRITICAL** |
| **Soglia ribassata (2 ante)** | `height_mm/1000 × 29.50 + 9.84` | ❌ NON CALCOLATA | ❌ No | **CRITICAL** |
| **Montante fisso** | `height_mm/1000 × 7.51 × q` | ❌ NON CALCOLATO | ❌ No | **HIGH** |
| **Traverso** | `width_mm/1000 × 7.50 × q` | ❌ NON CALCOLATO | ❌ No | **HIGH** |
| **Costo officina (hourly)** | `180 €/h` (V1_3) | `30 €/h` (production_config seed) | ⚠️ Valore diverso | **CRITICAL** (deviazione 6×) |
| Manodopera | `(production_time_min/60) × hourly_cost` | idem | ✅ Sì | — |
| **Pellicolato +10%** | `+10%` solo su profili PVC eleggibili | `+6%` (`premium_pvc_surcharge_pct`) su `pvc_base` | ⚠️ Valore e scope diversi | **HIGH** |
| Colore int/est separati | ✅ Richiesto | ❌ Un solo `color_code` | ❌ No | **MEDIUM** |
| **Moltiplicatore commerciale** | `commercial_multiplier` da configurazione | `margin_pct` (default 40%) come formula `× (1 + margin/100)` | ⚠️ Terminologia: markup vs margin (documentato in audit v1 sez 20) | **MEDIUM** |
| Sconto | `sale_before - discount` | idem | ✅ Sì | — |
| Ricetta 3-ante telaio unico | Attesa dal cliente | `MISSING_TECHNICAL_RECIPE` fail-closed | ⚠️ Fail-closed corretto | **HIGH** (BR-03 aperta) |

**Riepilogo gravità:**
- **CRITICAL: 3** (soglia ribassata 1-anta, soglia 2-ante, hourly_cost=30 vs 180)
- **HIGH: 5** (scambio, montante, traverso, pellicolato, BR-03)
- **MEDIUM: 2** (colore int/est, markup/margin terminologia)

---

## 4. Inventario motori di pricing esistenti nel codice

| Motore/Servizio | File | Chiamato da | Cosa calcola | Attivo commercialmente? | Duplicato di |
|---|---|---|---|---|---|
| **`commercial_perimeter`** | `services/recipes/commercial_perimeter.py` | `perimeter_assembler`, `catalog.simulate_product`, `quote_structure.compute_and_add`, `recompute` | Prezzo commerciale perimetrale con sfrido, glass_recipe, margin | ✅ **SÌ — motore attivo** | — |
| **`perimeter_assembler`** | `services/perimeter_assembler.py` | Come sopra | Assembla `PerimeterInput` da product + color + pricelist + config + glass_recipe | ✅ Wrapper del motore attivo | — |
| **`finestra_1a` (legacy)** | `services/recipes/finestra_1a.py` | `catalog.simulate_product` (se `pricing_mode="technical_cut_list"`) | Motore 1-anta legacy con `technical_cut_list` | ⚠️ Retro-compat, non usato oggi | Precursore di `commercial_perimeter` |
| **`glass_engine`** | `services/recipes/glass_engine.py` | `perimeter_assembler` | Risolve `glass_recipe` (formule strutturate/custom per dimensioni vetro) | ✅ Sotto-modulo attivo | — |
| **`pricing.py` (legacy)** | `services/pricing.py::compute_line` | `quotes.py` (endpoint preventivi vecchi) | Compute per `base_price + surcharges% + discount` | ⚠️ Attivo per preventivi legacy | Pre-motor era |
| **`pricing_v2.py` (M3.2 legacy)** | `services/pricing_v2.py::compute_line_v2` | `quotes.py` (endpoint preventivi vecchi) | Rules-based con scope unit/line, formula AST | ⚠️ Attivo per preventivi legacy che hanno regole | Sovrapposto a `pricing.py` |
| **`parametric_engine`** | `services/parametric_engine.py::resolve_bom` | `parametric.py`, `pricing_modes`, `bom_engine_v2` | Risolve BOM parametrica: legge `BomTemplate` + formule AST, ritorna componenti + costi | ⚠️ **PRESENTE MA NON NEL FLUSSO OPERATIVO** commerciale | — (era il candidato Sistema B) |
| **`bom_engine_v2`** | `services/bom_engine_v2.py::resolve_bom_full` | `pricing_hub.py::simulate` (metodo BOM/hybrid) | Wrapper attorno `parametric_engine` + preload anagraphs profiles/glass/hardware + aggregazione | ⚠️ Attivo solo tramite `/pricing-hub` | Estensione di `parametric_engine` |
| **`bom_recipes`** | `services/bom_recipes.py` | `parametric_engine`, `pricing_hub.py` | 18 ricette parametric (PERIMETRO_TELAIO, MONTANTE_VERTICALE, ecc.) | ⚠️ Definite ma non collegate al motore commerciale | Alternativa a `commercial_perimeter` |
| **`commission_engine`** | `services/commission_engine.py` | Endpoint provvigioni | Calcolo provvigioni CRM (non serramenti) | ✅ Attivo (dominio diverso) | — |
| **`pricing_modes.compute_parametric_preview`** | `services/pricing_modes.py` | `parametric.py::preview` | Preview parametric usando BOM template | ⚠️ Isolato | Duplicato di `bom_engine_v2` |

### 4.1 Servizi target (nuova architettura) — VERIFICA

| Servizio target | Esiste? | File | Usato dal preventivatore? | Completo? |
|---|:-:|---|:-:|:-:|
| `ProfileSystemResolver` | ❌ No | *(non presente)* | — | — |
| `BomResolver` | ❌ No | *(non presente)* | — | — |
| `TechnicalCostResolver` | ❌ No | *(non presente)* | — | — |
| `CommercialPricingService` | ❌ No | *(non presente)* | — | — |

**Verifica grep:**
```
$ grep -rn "TechnicalCostResolver|ProfileSystemResolver|BomResolver|CommercialPricingService" /app/backend/ /app/frontend/
(nessun match)
```

**Architettura effettivamente operativa oggi:**

```
QuoteStructurePage (UI)
    ↓  (unit_price MANUALE)
POST /api/quote-structure/openings/{id}/products
    ↓
quote_structure.py::add_product
    ↓
db.quotes.lines[] con base_price fornito

--- percorso motore, esistente ma NON usato dalla UI ---
POST /api/quote-structure/{id}/openings/{oid}/products/compute-and-add
    ↓
perimeter_assembler.run_perimeter_simulation
    ↓
catalog_service.load_product / resolve_component_prices / get_production_config
    ↓  (legge da products.components + item_pricelists.entries)
commercial_perimeter.compute_perimeter
    ↓
snapshot con hash → db.quotes.lines[].pricing_snapshot
```

---

## 5. Fonti dati ridondanti (Sistema A vs Sistema B)

| Concetto | Collection A (usata) | Collection B (non usata) | Collection C | Fonte realmente letta oggi | Ridondanza |
|---|---|---|---|---|---|
| Sistema profilo | `products.system` (stringa libera) | `parametric_profile_systems` (schema strutturato) | — | **A** | 🔴 **RIDONDANZA PERICOLOSA** |
| Telaio (codice) | `products.components[].code` (es. "5103") | `profiles` (anagrafica con dimensions, weight) | `catalog_code_mappings` | **A** | 🔴 **RIDONDANZA PERICOLOSA** |
| Anta | `products.components[]` categoria=`anta_standard` | `profiles` categoria=sash | — | **A** | 🔴 |
| Fermavetro | `products.components[]` categoria=`fermavetro` | `profiles` categoria=glazing_bead | — | **A** | 🔴 |
| Prezzo profilo €/ml | `item_pricelists.entries[]` schema `{code, color_code, unit_price}` (catalog) | `item_pricelists.entries[]` schema `{ref_type, ref_id, unit_price}` (parametric) | — | **A (catalog schema)** | 🟠 **TEMPORANEA DA MIGRAZIONE** — stessa collection, schema diverso |
| Vetro (ricette) | `glass_recipes` (structured/custom) | `glass_types` | — | **A** | 🟠 TEMPORANEA |
| Ferramenta | `products.default_hardware_kit.price` | `hardware_kits` (anagrafica parametric) | — | **A** | 🔴 |
| Colore | `color_categories` (`is_premium`) | `colors` (parametric) | — | **A + B** parzialmente | 🟠 |
| Costo orario | `production_config.hourly_cost` | *(nessun altro)* | — | **A** | ✅ NECESSARIA |
| Moltiplicatore/margin | `production_config.default_margin_pct` | `pricing_mode_configs` (parametric) | — | **A** | 🟠 |
| Additional/pellicolato % | `production_config.premium_pvc_surcharge_pct` | — | — | **A** | ✅ NECESSARIA |
| BOM ricette | *(hardcoded in `commercial_perimeter`)* | `bom_templates` + `bom_recipes.RECIPE_CATALOG` | — | **A (hardcoded)** | 🔴 **RIDONDANZA PERICOLOSA** |

**Legenda:** 🔴 CRITICAL · 🟠 MEDIUM/TEMPORANEA · 🟢 NECESSARIA

**Duplicati alto rischio:** 6 concetti hanno due fonti dati parallele (Sistema A operativo, Sistema B parametric non collegato).

---

## 6. Audit delle route UI

| Route | Funzione reale | Dati scritti | Influenza preventivo? | Ridondante? | Raccomandazione |
|---|---|---|---|---|---|
| `/quote-structure` | Editor preventivo (Ambienti → Vani → Prodotti). Attualmente accetta `unit_price` MANUALE. **UI PRESENTE, PRICING NON COLLEGATO al motore commercial_perimeter** | `quotes.lines[]`, `quotes.openings[]`, `quotes.environments[]` | ✅ Sì (scrive linee) | ⚠️ Duplica `/quotes/:id` (QuoteEditor legacy) | **Migrare la UI a chiamare `/compute-and-add` invece di `/openings/{id}/products`** |
| `/product-simulator` | Simulatore tecnico (debug del motore) | Nessuna scrittura (solo GET/POST simulate) | ⚠️ Indiretta (mostra risultato commercial_perimeter) | ⚠️ Duplica logicamente `compute-and-add` | Mantenere come strumento tecnico ristretto ad admin |
| `/pricing-hub` | Configurazione metodi A-G per categoria prodotto (`pricing_method_configs`) + simulatore metodi semplici | `pricing_method_configs` | ❌ **NO — non chiamato dal preventivatore serramenti** | ⚠️ Nessuno lo consulta | Mantenere per prodotti semplici (tapparelle, servizi), separare da motore serramenti |
| `/pricelists` | CRUD listini (catalogo `item_pricelists`) | `item_pricelists.entries[]` (schema A) | ✅ Sì (motore legge da qui) | ⚠️ Interfaccia grezza | Integrare in "Configurazione tecnica → Componenti" |
| `/pricelist-importer` | Import XLS/CSV di listini profili | `item_pricelists.entries[]` (schema A) | ✅ Sì | ⚠️ Feature azione amministrativa | Nascondere dalla sidebar (fatto in iter40) |
| `/parametric` | Configuratore parametric (BomTemplate preview) | Nessuna scrittura durante preview | ❌ **NO — completamente isolato** | 🔴 Duplica motore commerciale ma diverso schema | Marcare esplicitamente come "engine legacy, non collegato" o hidden |
| `/parametric/admin` | CRUD `parametric_profile_systems`, `profiles`, `bom_templates`, `glass_types`, `hardware_kits`, `accessories`, `item_pricelists` (schema B) | Collezioni parametric | ❌ **NO** — dati non letti dal motore | 🔴 **RIDONDANZA PERICOLOSA** — l'utente pensa di configurare il preventivo, invece configura un sistema isolato | Nascondere dalla sidebar (fatto in iter40) + banner "SISTEMA NON COLLEGATO" |

---

## 7. Verifica `/quote-structure`

**File:** `frontend/src/pages/QuoteStructurePage.jsx`

| Elemento | Valore |
|---|---|
| Da dove carica le categorie | `GET /api/product-catalog/types` (`ProductType` collection) — categorie=`window`, `french_door`, ecc. |
| Da dove carica le linee | ❌ Non esiste concetto di "linea prodotto" nella UI. `product_type_code` è unico dropdown |
| Da dove carica i prodotti | ❌ **Non carica una lista di prodotti selezionabili**. Il dropdown è `product_type_code` (tipologia), non `product_id` |
| Quale `product_id` viene selezionato | ❌ **Nessuno** — la UI usa `product_type_code`, non `product_id` |
| Quale configurazione invia | `{role, product_type_code, description, configuration:{num_modules,modules[]}, dimension_source, unit_price}` |
| Quale endpoint usa per il calcolo | **NESSUN CALCOLO** — chiama `POST /api/quote-structure/openings/{id}/products` che accetta `unit_price` manuale |
| Riceve un `sale_price`? | ❌ No — il commerciale inserisce a mano il prezzo |
| Come aggiunge il prodotto al preventivo | Chiamata diretta con `unit_price` fornito dall'utente |
| Quale snapshot salva | Nessun snapshot con hash — solo il campo `unit_price` |

**Verdetto:** `UI PRESENTE, PRICING NON COLLEGATO`

Il motore `compute-and-add` esiste (verificato in iter40, test verdi, prezzo 356.29€), ma nessuna interfaccia lo chiama. La UI attuale del preventivatore continua a operare col vecchio flusso a `unit_price` manuale.

---

## 8. Verifica `/product-simulator`

**File:** `frontend/src/pages/ProductSimulatorPage.jsx` → `POST /api/catalog/products/{pid}/simulate`

| Elemento | Valore |
|---|---|
| Motore chiamato | `commercial_perimeter` (default) via `perimeter_assembler.run_perimeter_simulation` |
| Collection lette | `products`, `item_pricelists` (schema A), `production_config`, `color_categories`, `glass_recipes` |
| Genera importi? | ✅ Sì, se il tenant ha listino + `production_config` popolati (verificato in iter40, seed P0) |
| Usa seed? | ⚠️ In preview usa il seed `test-motor-pricelist-01` per il prodotto demo `test-motor-product-proevolution` |
| Usa listini veri? | ✅ Sì per prodotti reali (ProEvolution id `8e1cafd0-...`) usa `Listino Standard Infissi Express 2026` — che aveva `entries=[]` fino a iter40 |
| Usa le formule Excel V1_3? | ❌ **NO** — soglia ribassata, montante, traverso, pellicolato +10% NON implementati |
| Risultato identico al preventivatore? | ⚠️ **Se** il preventivatore usasse `compute-and-add`, sarebbero identici (stesso `perimeter_assembler`). Oggi la UI usa `unit_price` manuale → **valori diversi possibili** |

**Confronto tre percorsi per lo stesso input** (ProEvolution 900×1500 BIANCO):

| Sorgente | Prezzo | Snapshot | Note |
|---|---:|:-:|---|
| `SIMULATOR_PRICE` (`/api/catalog/products/{pid}/simulate`) | **356.29 €** | ✅ hash `a9ae792b...` | Motore `commercial_perimeter` v1.0.0 |
| `QUOTE_STRUCTURE_PRICE` (compute-and-add) | **356.29 €** (identico) | ✅ hash identico | Stesso motore, stesso input |
| `QUOTE_PRICE` (UI attuale che usa `unit_price` manuale) | **Variabile** — dipende da quanto scrive il commerciale | ❌ Nessun snapshot | Prezzo non tracciato |

---

## 9. Verifica `/pricing-hub`

**File:** `backend/app/routers/pricing_hub.py`

**Cosa calcola oggi:**
Metodi disponibili:
- **A. `per_sqm`** — Prezzo al metro quadrato con minimo fatturabile
- **B. `tabular`** — Matrice larghezza × altezza (`price_matrices`)
- **C. `per_piece`** — Prezzo a pezzo
- **D. `per_linear`** — Prezzo al metro lineare
- **E. `bom`** — Distinta parametrica (chiama `bom_engine_v2.resolve_bom_full`)
- **F. `hybrid`** — Combinazione (finestra: profili+vetro+ferramenta+lavorazioni) tramite parametric
- **G. `formula`** — Formula personalizzata (parser AST safe)
- **H. `manual_temporarily`** — Fallback con motivazione

**Sovrapposizione col motore serramenti:**
- I metodi E/F usano `parametric_engine.resolve_bom` → **DIVERSO** dal motore commerciale `commercial_perimeter`
- I metodi A/B/C/D sono per prodotti semplici (tapparelle, cassonetti, servizi)
- **Nessun preventivo serramento reale usa `/pricing-hub`** — verificato: `quote_structure::compute_and_add` chiama solo `perimeter_assembler`, non `pricing_hub`

**Risultato reale oggi:**
- `motore tecnico → prodotti complessi`: **PARZIALE** — è `commercial_perimeter`, non `pricing_hub`
- `pricing hub → prodotti semplici`: **CONFIGURATO ma non collegato** — nessun preventivo lo invoca ancora
- Rimane come strumento di configurazione futura per prodotti non-serramento

---

## 10. Verifica `/pricelists`

**File:** `frontend/src/pages/PricelistsPage.jsx` + backend `routers/parametric.py` (per `item_pricelists`)

**Cosa contiene:**
- `item_pricelists` collection ha **2 schemi coesistenti**:
  - **Schema A (catalog/importer)**: `entries[] = {code, color_code, unit_price, description, unit}` — usato da `commercial_perimeter` (verified in iter40)
  - **Schema B (parametric)**: `entries[] = {ref_type, ref_id, color_id, supplier_id, unit_price}` — usato da `parametric_engine`/`bom_engine_v2`

**Chi li legge:**
- Motore commerciale (`resolve_component_prices` in `catalog_service.py`): schema A per matching `code` + `color_code`
- Motore parametric (`bom_engine_v2._build_lookups_with_origin`): schema B per matching `ref_type`+`ref_id`

**Prezzi tecnici o commerciali:**
- Sono **prezzi di acquisto/costo €/ml** dei profili → tecnici (fonte del costo interno)

**Duplicati vs Sistema B:**
- ✅ **Sì**: stesso listino può avere entries in due schemi diversi. Vince chi legge — nessun cross-check.

**Necessari?**
- Sì, ma **il formato va unificato** (backlog Fase 1 unificazione)

---

## 11. Verifica `/pricelist-importer`

**File:** `frontend/src/pages/PricelistImporterPage.jsx` + `services/importer_service.py`

| Elemento | Valore |
|---|---|
| Cosa importa | File XLS/CSV con listini profili (colonne: code, description, color, unit_price) |
| In quale collection | `item_pricelists.entries[]` **schema A** (catalog) |
| Chi usa i dati importati | `commercial_perimeter` tramite `resolve_component_prices` |
| Può sovrascrivere dati | ⚠️ Sì — la UI sostituisce le entries |
| Collegato al motore attuale | ✅ Sì, direttamente |
| Serve nella nuova architettura | ✅ Sì, ma da migrare a "Configurazione tecnica → Componenti → Importa listino" (backlog) |

---

## 12. Verifica `/parametric`

**File:** `frontend/src/pages/ParametricConfiguratorPage.jsx` + `ParametricAdminPage.jsx`

**Contenuto:**
- Sistemi profilo (`parametric_profile_systems`) con parametri tecnici (frame_width, glass_deduction, kerf_mm, bar_length_mm, weld_allowance_mm)
- Profili (`profiles`) con anagrafica (weight, dimensions)
- Ricette BOM (`bom_templates`) con formule AST safe (services/formula)
- Vetri (`glass_types`), Ferramenta (`hardware_kits`), Accessori (`accessories`)
- Listini schema B
- Preview endpoint: `POST /api/parametric/preview` → chiama `services.pricing_modes.compute_parametric_preview` → `parametric_engine.resolve_bom`

**Servizi che leggono i dati parametric:**
- `parametric_engine.resolve_bom` — usato SOLO da `parametric.preview` e `pricing_hub` (metodi E/F)
- **Nessun preventivo commerciale reale** invoca questi servizi

**Domanda diretta:**
> **PARAMETRIC È OGGI PARTE DEL CALCOLO DEL PREVENTIVO: NO**

Evidenza:
```python
# quote_structure.py::compute_and_add_product (linea 425)
from app.services.perimeter_assembler import run_perimeter_simulation
sim_body = _build_simulate_request(payload)
snapshot = await run_perimeter_simulation(user["tenant_id"], sim_body)
```
`perimeter_assembler` → `commercial_perimeter` → NON tocca `parametric_engine`.

**Il modulo parametric è progettato, funzionante, con 18 ricette, formule AST safe — ma è un'isola non connessa.**

---

## 13. Fonte del costo tecnico — Risposta netta

> **Domanda: Oggi Panorama Pilot calcola prima un costo tecnico reale di produzione e successivamente applica un moltiplicatore commerciale?**
>
> **Risposta: PARZIALMENTE**

**Cosa è reale nel costo tecnico attuale:**
- ✅ Perimetro esterno (formule geometriche corrette)
- ✅ Consumo ml per componente (net + sfrido/waste_pct)
- ✅ Costo materiali profili (€/ml da listino attivo)
- ✅ Area vetro con formula strutturata (glass_recipe) + minimo fatturabile
- ✅ Manodopera (production_time × hourly_cost)
- ✅ Snapshot con hash per idempotenza

**Cosa è semplificato o seedato:**
- ⚠️ Prezzi listino: seed P0 per collaudo, non prezzi reali del cliente
- ⚠️ `hourly_cost = 30 €/h` (seed) vs V1_3 `180 €/h` (deviazione 6×)
- ⚠️ Ferramenta come **valore fisso in €**, non calcolato da BOM
- ⚠️ Additional cost: campo opaco `additional_material_cost`, non decomposto
- ❌ Nessun BOM ricette reali (le ricette sono cablate nel codice di `commercial_perimeter`)
- ❌ Nessuna soglia ribassata, scambio battuta V1_3, montanti, traversi, pellicolato +10%
- ❌ Nessuna decomposizione tempi produzione per operazione (taglio, saldatura, ferramenta, imballo)

**Il moltiplicatore commerciale** viene applicato:
- `margin_pct = 40%` (dalla `production_config`)
- Formula: `sale_price_before_discount = total_internal_cost × (1 + margin_pct / 100)`
- **Terminologia confusa** (documentato in audit v1 sez 20): "margin_pct" è in realtà un **markup**, non un vero margine. Vero margin sarebbe `(sale - cost) / sale`.

---

## 14. Verifica del moltiplicatore

| Aspetto | Valore |
|---|---|
| Dove è memorizzato | `production_config.default_margin_pct` (collection `production_config`, tenant-scoped) |
| Per quale tenant | Uno per tenant, id = `pc-{tenant_id}` |
| Per quale prodotto | Applicato **globalmente** a tutti i prodotti del tenant (nessuna configurazione per prodotto/categoria) |
| Hardcoded | ❌ No (configurabile via `PATCH /api/catalog/production-config`) |
| Versionato | ❌ No (nessun `version` sui cambi) — updated_at/updated_by tracciato |
| Chi lo modifica | Permesso `pricing_admin.manage` (admin) |
| Servizio che lo legge | `perimeter_assembler.build_perimeter_input` → `cfg.get("default_margin_pct")` → passato a `commercial_perimeter.compute_perimeter` |
| Salvato nello snapshot? | ✅ Sì (`snapshot.margin_pct` = valore effettivo usato) |
| Valore effettivo ProEvolution 900×1500 | `40.0` (production_config.default_margin_pct) |
| Override possibili? | Sì: `body.override_margin_pct` a livello di singola simulate/compute-and-add |

**Nota terminologica:**
- Il campo si chiama `margin_pct` e nella UI viene descritto come "margine"
- La formula applicata è `total × (1 + margin/100)` → **è un markup**, non un margine
- Vero margine = `(sale - cost) / sale`
- Il vero moltiplicatore commerciale V1_3 (`commercial_multiplier`) NON esiste come campo dedicato

Non c'è distinzione codice `multiplier` vs `markup` vs `gross margin` — tutto è collassato su `margin_pct`.

---

## 15. Verifica degli snapshot

### `technical_snapshot` (contenente il costo tecnico)

- **Servizio produttore:** `commercial_perimeter.compute_perimeter` (dataclass `PerimeterResult` → `display_dict`)
- **Contenuto reale (verificato):**
  - `external_perimeter_ml`, `sash_perimeter_ml`, `meeting_stile_ml`
  - `ml_consumption`, `ml_consumption_net`, `waste_percentages`
  - `unit_prices` (`P_FRAME`, `P_SASH`, `P_GLAZING_BEAD`, `P_GLASS_SQM`, `P_HARDWARE`, `HOURLY_COST`, `PRODUCTION_TIME_MINUTES`)
  - `component_costs` (frame_cost, sash_cost, glazing_bead_cost, glass_cost, hardware_cost, additional, premium)
  - `profile_cost`, `glass_cost`, `hardware_cost`, `additional_material_cost`, `premium_surcharge`
  - `materials_cost`, `labor_cost`, `production_cost`, `service_cost`, `total_internal_cost`

### `commercial_snapshot` (regola commerciale applicata)

- **Servizio produttore:** stesso `commercial_perimeter` (non c'è separazione fisica in due snapshot)
- **Contenuto reale:**
  - `margin_pct`, `sale_price_before_discount`, `discount`, `sale_price`

### Verifica separazione dual-snapshot come da target architetturale
- ❌ **La separazione fisica `technical_snapshot` vs `commercial_snapshot` NON esiste**. È un unico blob `pricing_snapshot` con tutti i campi.
- ✅ La denominazione dei campi permette una lettura logica (tutto prima di `sale_price_before_discount` = tecnico; da `margin_pct` in poi = commerciale)

### Consistenza tra i tre percorsi

| Percorso | Formato snapshot |
|---|---|
| `/api/catalog/products/{pid}/simulate` | ✅ `PerimeterResult.display_dict` |
| `/api/quote-structure/.../compute-and-add` | ✅ Identico (salvato in `quotes.lines[].pricing_snapshot`) |
| `/api/quote-structure/products/{line_id}/recompute` | ✅ Identico |

**Divergenze:** nessuna tra i 3 percorsi che usano il motore. L'unica divergenza è vs la UI attuale che salva solo `unit_price` senza snapshot.

---

## 16. Verifica del prezzo congelato

**Test READ-ONLY (no modifiche al tenant):**

Il codice `compute_and_add_product` (quote_structure.py, linea 471-478) salva:
```python
new_line = {
  ...
  "base_price": round(unit_price_final, 2),           # freeze
  "unit_price_final": round(unit_price_final, 2),     # freeze
  "subtotal_line": round(unit_price_final * qty, 2),  # freeze
  "pricing_engine": "commercial_perimeter",           # snapshot metadata
  "pricing_snapshot": snapshot,                       # full snapshot con hash
  "pricing_snapshot_hash": snapshot.get("snapshot_hash"),  # SHA256
}
```

**Verifica congelamento su preventivi esistenti:**
Nel test iter40 (screenshot preventivatore) il preventivo `PRV-2026-01711-R00` mostra il totale **453.97€** salvato. Riapertura del preventivo carica `base_price` congelato senza ricalcolare.

**`recompute` esplicito:** l'endpoint `POST /api/quote-structure/products/{line_id}/recompute` ricalcola con la config CORRENTE del tenant, aggiornando `pricing_snapshot` e `unit_price_final`. È **opt-in** — non automatico.

**Verdetto:**
- ✅ **PREZZO CONGELATO** nel salvataggio: OK
- ✅ Snapshot con hash: OK
- ⚠️ Il valore hash **non è verificato al load** — il preventivo mostra `base_price` senza ricontrollare che sia coerente con `pricing_snapshot`. Se qualcuno modifica manualmente `base_price` in DB, la coerenza si rompe (nessun check attivo di integrità).
- ⚠️ **Nessun test** verifica esplicitamente che modificare `production_config` NON alteri preventivi vecchi. Sarebbe un test P0 mancante.

**Classificazione:** OK con **rischio MEDIUM** su integrità hash (backlog).

---

## 17. Versione architetturale realmente in uso

Come già verificato in §4.1:

| Servizio target | Esiste? | Usato dal preventivatore? | Completo? |
|---|:-:|:-:|:-:|
| `ProfileSystemResolver` | ❌ NO | — | — |
| `BomResolver` | ❌ NO | — | — |
| `TechnicalCostResolver` | ❌ NO | — | — |
| `CommercialPricingService` | ❌ NO | — | — |

**Architettura effettivamente operativa oggi:**

```
Preventivo (UI QuoteStructurePage)
    ↓  (unit_price MANUALE — bypassa il motore)
POST /api/quote-structure/openings/{id}/products
    ↓
db.quotes.lines[]  (senza snapshot)

--- oppure (percorso motore, esistente ma non nella UI attuale) ---
POST /api/quote-structure/{id}/openings/{oid}/products/compute-and-add
    ↓
perimeter_assembler.build_perimeter_input
    ↓ ↓ ↓ ↓
    ├─ products.components[]        (schema A, semplificato)
    ├─ item_pricelists.entries[]    (schema A, catalog importer)
    ├─ production_config            (glass_price, hourly_cost, margin_pct)
    ├─ color_categories             (is_premium)
    └─ glass_recipes                (structured formula)
    ↓
commercial_perimeter.compute_perimeter
    ↓
snapshot con hash → db.quotes.lines[].pricing_snapshot
```

---

## 18. Diagrammi AS-IS vs TO-BE

### 18.1 AS-IS (situazione attuale, 2026-08)

```
+-----------------------------+
|  UI /quote-structure        |  ← commerciale inserisce unit_price MANUALE
+-------------+---------------+
              |
              v
+-------------+---------------+
| POST /openings/{id}/products |   ← nessun motore invocato
+-------------+---------------+
              |
              v
       [ db.quotes.lines ]
        (senza snapshot)

  --- percorso motore (esistente ma UI non lo chiama) ---
+-----------------------------+
| /product-simulator (Admin)  |  ─┐
+-------------+---------------+   │
              |                   │
              v                   │
+-----------------------------+   │
| POST /simulate              |   │
| POST /compute-and-add       | <─┘
| POST /recompute             |
+-------------+---------------+
              |
              v
+-----------------------------+
| perimeter_assembler         |
+-------------+---------------+
              |
      +-------+-------+-------+-------+
      v       v       v       v       v
  products  item_    prod_   color_  glass_
  .comp    pricelist config  cats    recipes
  (A)       (A)      (A)     (A)     (A)
              |
              v
+-----------------------------+
| commercial_perimeter        |
| (formule 1-anta/2-ante,     |
|  waste, glass, margin)      |
+-------------+---------------+
              |
              v
      [ snapshot con hash ]
              |
              v
       [ db.quotes.lines ]

  --- percorsi legacy/isolati (non collegati al preventivo commerciale) ---

  /pricing-hub  →  pricing_hub.py::simulate  →  metodi A/B/C/D/E/F/G/H
                                                (E/F usano bom_engine_v2 → parametric)

  /parametric   →  parametric.py::preview     →  parametric_engine.resolve_bom
                                                 (usa bom_templates + AST formulas)
                                                 → NESSUN preventivo lo chiama

  QuoteEditor legacy (/quotes/:id)  →  quotes.py  →  pricing.py::compute_line
                                                     pricing_v2.py::compute_line_v2
                                                     (surcharges/discounts su base_price)
```

### 18.2 TO-BE (target da ARCHITECTURAL_AUDIT_V3.md)

```
+-----------------------------+
|  UI Configuratore Prodotto  |
+-------------+---------------+
              |
              v
+-----------------------------+
| ProfileSystemResolver       |
| (resolve profile_system_id  |
|  from product + tenant)     |
+-------------+---------------+
              |
              v
+-----------------------------+
| BomResolver                 |
| (resolve BOM from           |
|  profile_system + geometry) |
+-------------+---------------+
              |
              v
+-----------------------------+
| TechnicalCostResolver       |
| (compute REAL industrial    |
|  cost from BOM + labor +    |
|  overhead)                  |
+-------------+---------------+
              |
              v (technical_snapshot)
              |
+-----------------------------+
| CommercialPricingService    |
| (apply markup / commercial  |
|  multiplier + discounts)    |
+-------------+---------------+
              |
              v (commercial_snapshot)
              |
       [ Quote line con dual snapshot ]
```

**Nessuno dei 4 servizi TO-BE è presente nel codice attuale.**

---

## 19. Redundancy Score (0=nessuna, 4=critica)

| Area | Score | Motivazione |
|---|:-:|---|
| **Catalogo prodotti** | **3** | `products` (semplice, con components[]) vs `parametric_profile_systems` (parametric) — schemi paralleli |
| **Listini** | **3** | `item_pricelists` con 2 schemi coesistenti (catalog vs parametric) nella stessa collection |
| **Componenti profili** | **4** | `products.components[]` (codes) vs `profiles` (anagrafica) vs `catalog_code_mappings` — 3 fonti |
| **Formule** | **3** | Cablate in `commercial_perimeter` + presenti in `bom_templates` (parametric) + potenzialmente ridefinite in `pricing_hub` (metodo formula) |
| **Vetro** | **2** | `glass_recipes` (attivo) + `glass_types` (parametric non usato) |
| **Colori** | **2** | `color_categories` (attivo) + `colors` (parametric non usato) |
| **Ferramenta** | **3** | `products.default_hardware_kit` (attivo, valore fisso) + `hardware_kits` (parametric anagrafica) — nessun BOM ferramenta reale |
| **Motori pricing** | **4** | 8 servizi/moduli pricing coesistenti: commercial_perimeter (attivo), perimeter_assembler, finestra_1a (legacy), pricing (legacy quotes), pricing_v2 (legacy quotes), parametric_engine (isolato), bom_engine_v2 (via hub), pricing_modes (parametric wrapper) |
| **Simulatori** | **2** | product-simulator (via commercial_perimeter) + pricing_hub simulate (via bom_engine_v2 o formula) — non allineati |
| **Preventivatore** | **3** | UI attuale usa unit_price manuale mentre esiste il motore compute-and-add — due paradigmi coesistenti |
| **Snapshot** | **1** | Un solo snapshot format ma non separato tecnico/commerciale |
| **UI amministrativa** | **3** | /pricelists, /pricelist-importer, /parametric/admin, /pricing-hub, /product-catalog — 5 aree con sovrapposizioni |

**Score totale medio: 2.75 / 4** → livello **MODERATO-GRAVE**.

---

## 20. Verdetto finale — 10 domande

| # | Domanda | Risposta |
|---|---|---|
| 1 | Quanti motori calcolano oggi un prezzo? | **8 moduli** (commercial_perimeter, perimeter_assembler wrapper, finestra_1a legacy, pricing.py legacy, pricing_v2 legacy, parametric_engine, bom_engine_v2, pricing_modes) |
| 2 | Qual è quello realmente usato dal preventivatore? | **`commercial_perimeter`** via `perimeter_assembler` — attivato solo tramite `compute-and-add`/`recompute` che oggi la UI non chiama |
| 3 | Qual è quello usato dal simulatore? | **`commercial_perimeter`** (identico) |
| 4 | Sono lo stesso? | ✅ **SÌ** (simulatore e compute-and-add usano lo stesso `perimeter_assembler` → stesso snapshot con stesso hash a parità di input) |
| 5 | Quante fonti dati tecniche esistono? | **≥6** collezioni: `products`, `item_pricelists` (schema A), `parametric_profile_systems`, `profiles`, `bom_templates`, `item_pricelists` (schema B). Alcune usate, altre isolate |
| 6 | Qual è la fonte autorevole realmente usata oggi? | **Sistema A**: `products.components[]` + `item_pricelists.entries[]` (schema catalog) + `production_config` |
| 7 | Le formule V1_3 sono già in uso? | ❌ **NO** — nessuna delle formule Excel V1_3 (soglia ribassata, scambio battuta €5.50, montante, traverso, pellicolato +10%) è implementata. Solo il framework perimetrale + waste è in uso |
| 8 | Il preventivatore calcola oggi un vero costo industriale? | ⚠️ **PARZIALMENTE** — perimetro + ml + prezzi listino + manodopera SÌ; BOM reali, tempi per operazione, overhead, colori int/est separati NO |
| 9 | Quali pagine sono ridondanti? | `/pricelists` (nascosta), `/pricelist-importer` (nascosta), `/parametric` + `/parametric/admin` (nascoste), `/pricing-hub` (utile ma isolato dai serramenti), UI di `/quote-structure` (usa unit_price manuale invece del motore) |
| 10 | Siamo già nella nuova architettura oppure ancora nella versione transitoria? | **C — ARCHITETTURA TRANSITORIA CON COMPONENTI LEGACY** |

### Motivazione verdetto (C)

**Evidenze pro-C:**
- Il motore `commercial_perimeter` è un ponte tra il legacy `finestra_1a` e il target `TechnicalCostResolver`/`CommercialPricingService`
- Snapshot con hash è già presente (elemento della target architecture)
- Ma i 4 servizi target NON esistono
- 8 motori pricing coesistono; solo 1 nel flusso operativo commerciale
- 6+ collezioni con sovrapposizioni; una serie di UI legacy nascoste ma vive nel DB
- La UI attuale del preventivatore **bypassa il motore** salvando `unit_price` manuale
- Le formule V1_3 sono documentate ma non implementate

**Evidenze contro-D (perché non è "completamente legacy"):**
- Il nuovo motore `commercial_perimeter` esiste ed è testato (P0 verdi, sale_price=356.29€)
- Framework guard `MISSING_*` fail-closed è in produzione
- Guard `DEMO_PRODUCT_NOT_ALLOWED` e environment_scope sono attivi
- Test suite di regressione è presente (31 test audit_v1_regression + 3 P0)

**Evidenze contro-B (perché non è già parzialmente operativo nella target):**
- Nessuno dei 4 resolver target esiste come classe/modulo
- Non c'è separazione fisica `technical_snapshot` vs `commercial_snapshot`

---

## 21. Rischi principali

1. **UI-Motore disconnessa (P0)**  
   La UI attuale di `/quote-structure` non invoca il motore. Il commerciale inserisce prezzi manualmente. Il motore `compute-and-add` esiste ma nessuno lo chiama dal browser.

2. **Sistema B parametric completamente scollegato (P0)**  
   Un admin che apre `/parametric/admin` configura profili, ricette BOM e formule AST **credendo di configurare il preventivatore**. In realtà nessun dato letto lì entra nel motore commerciale. Rischio di dati errati salvati in buona fede.

3. **Doppio schema `item_pricelists` (P0)**  
   Stessa collection contiene entries schema A e schema B. L'importer scrive A, il parametric admin scrive B. Nessun cross-check.

4. **`hourly_cost` seedato a 30 vs V1_3 a 180 (CRITICAL)**  
   Deviazione 6×. La manodopera è sottostimata di 5/6 in ogni preventivo del tenant seedato.

5. **Formule V1_3 mancanti (HIGH)**  
   Soglia ribassata, montante, traverso, scambio battuta €5.5/pz, pellicolato +10% non applicate. Preventivi non riflettono le tariffe reali del cliente.

6. **Hash snapshot non verificato al load (MEDIUM)**  
   Il preventivo carica `base_price` senza validare che sia coerente con `pricing_snapshot_hash`. Alterazioni manuali del DB romperebbero l'integrità senza allarme.

7. **Terminologia margin vs markup (MEDIUM)**  
   Il campo `margin_pct` è in realtà un markup. La UI e la contabilità potrebbero interpretarlo come vero margine, con confusione sui report finanziari.

---

## 22. Conclusione

Panorama Pilot è in una **fase di transizione architetturale ben definita**:
- Il motore `commercial_perimeter` è **il futuro concreto** — funzionante, testato, con snapshot e hash
- Manca l'**ultimo miglio**: (a) collegare la UI del preventivatore al motore, (b) implementare le formule V1_3, (c) migrare Sistema B → A e chiudere il codice legacy

Il rischio maggiore è **cognitivo**: un utente vede 5+ aree amministrative simili senza sapere quale conta davvero. La sidebar iter40 ha già rimosso 4 route dalla vista (ma le route sono ancora accessibili via URL diretto per compat).

**Nessuna modifica al codice, nessun seed, nessuna migrazione eseguita in questa audit.** In attesa della tua approvazione per decidere se procedere con:
- **Opzione 1**: Collegare la UI `/quote-structure` al motore `compute-and-add` (piccolo, alto valore percepito)
- **Opzione 2**: Implementare le formule V1_3 mancanti nel motore attuale (medio, alto valore economico)
- **Opzione 3**: Fase 1 unificazione (grande, richiede design dei 4 resolver)

Attendo indicazioni.
