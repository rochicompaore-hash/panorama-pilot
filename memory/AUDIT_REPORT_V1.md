# Panorama Pilot — AUDIT TECNICO COMPLETO v1
**Data**: Feb 2026  
**Autore**: Agent — audit pre-unificazione architetturale (opzione D2:b)  
**Ambito**: 17 sezioni richieste. Solo analisi statica + fix Critical/High.  
**Rollback tag**: `pre-audit-v1-2026-02`  
**Scope**: PanoramaPilot tenant (`ae9168f6-d96e-4c5d-bb33-25acbb9a8410`) — production data isolato

---

## Sezione 1 · Mappa file coinvolti

### Backend — file autorevoli e loro responsabilità

| Percorso | Responsabilità | Collezioni lette | Collezioni scritte | Endpoint | Stato |
|---|---|---|---|---|---|
| `app/routers/parametric.py` | CRUD engine parametrico legacy | `profile_systems, profiles, colors, color_categories, glass_types, hardware_kits, accessories, item_pricelists, price_matrices, bom_templates, pricing_mode_configs` | idem | `/api/parametric/*` | **LEGACY / disconnesso** dal preventivo |
| `app/routers/catalog.py` | Area catalogo (Opzione A) | `products, item_pricelists, color_categories, production_config, catalog_code_mappings` | `products, catalog_code_mappings, production_config` | `/api/catalog/*` | **ATTIVO** (motore commercial_perimeter) |
| `app/routers/quote_structure.py` | Motore commerciale integrato Fase 1 | `quotes, products, item_pricelists, color_categories, glass_recipes, production_config` | `quotes` | `/api/quote-structure/*` | **ATTIVO** — usa `commercial_perimeter` |
| `app/routers/quotes.py` | CRUD preventivo classico | `quotes, pricelists, price_rules, discount_thresholds, quote_signatures, sequences, contracts` | idem | `/api/quotes/*` | ATTIVO |
| `app/routers/pricing_hub.py` | Pricing Hub (regola per categoria) | `pricing_method_configs, item_pricelists, price_matrices, bom_templates` | `pricing_method_configs` | `/api/pricing-hub/*` | ATTIVO |
| `app/routers/pricing.py` | Pricelists commerciali generici | `pricelists, price_rules, products` | idem | `/api/pricing/*` | LEGACY (usato solo da price_snapshot) |
| `app/routers/contracts.py` | Contratti | `contracts, quotes, quote_signatures, opening_products` | idem | `/api/contracts/*` | ATTIVO |
| `app/services/recipes/commercial_perimeter.py` | Motore commerciale (calcolo prezzo) | — | — | — | ATTIVO, deterministico, snapshot-hash |
| `app/services/recipes/finestra_1a.py` | Motore ricetta 1-anta 5103+12130 | — | — | — | ATTIVO |
| `app/services/recipes/glass_engine.py` | Formule vetro strutturate | `glass_recipes` | `glass_recipes` (seed) | — | ATTIVO |
| `app/services/perimeter_assembler.py` | Assemblatore input motore | (via `catalog_service`) | — | — | ATTIVO |
| `app/services/catalog_service.py` | Lookup catalogo + prezzi + config | `products, item_pricelists, color_categories, production_config, catalog_code_mappings` | `production_config, catalog_code_mappings` | — | ATTIVO |
| `app/services/parametric_engine.py` | Legacy BOM engine (technical_cut_list) | — | — | — | ATTIVO ma non collegato al preventivo |
| `app/services/bom_engine_v2.py` | Wrapper resolve_bom + origine listino | `bom_templates, profile_systems, item_pricelists, profiles, glass_types, hardware_kits, accessories` | — | — | ATTIVO (technical/production only) |
| `app/services/formula.py` | Parser AST sicuro | — | — | — | ATTIVO, no eval |
| `app/services/formula_security.py` | Guard import-time no-eval | — | — | — | ATTIVO |

### Frontend — pagine coinvolte

| File | Endpoint chiamati | Stato | Note |
|---|---|---|---|
| `ParametricAdminPage.jsx` | `/api/parametric/*` (11 sezioni CRUD) | **DISCONNESSO** | Non alimenta il motore commercial_perimeter |
| `ProductSimulatorPage.jsx` | `/api/catalog/products/{id}/simulate` | ATTIVO | Prova sul motore |
| `PricingHubPage.jsx` | `/api/pricing-hub/*` | ATTIVO | Config per categoria |
| `PricelistImporterPage.jsx` | `/api/importer/*` | ATTIVO | Upload XLS/CSV |
| `QuoteStructurePage.jsx` | `/api/quote-structure/*` | ATTIVO | Editor legacy 5-step |
| `QuoteEditorPage.jsx` | `/api/quotes/*` (legacy manual price) | **LEGACY** | Marcato read-only |

---

## Sezione 2 · Duplicazioni identificate

**Stato DB corrente (PanoramaPilot tenant)**:
```
profile_systems: 1
profiles: 7
item_pricelists: 3
products: 11
glass_recipes: 6
production_config: 2
color_categories: 4
catalog_code_mappings: 4
bom_templates: 16
quotes: 355
```

**Collezioni `parametric_*` inizialmente sospettate**: NON esistono. Il router `parametric.py` scrive su `profile_systems`, `profiles`, etc. (nomi puliti). Solo il **prefisso `/api/parametric/*` del router** ha creato confusione nel piano di unificazione.

| Concetto | Fonte "A" | Fonte "B" | Duplicazione reale? | Rischio |
|---|---|---|---|---|
| Sistema profilo | `profile_systems` (router parametric) | `products.components[]` (router catalog) | **PARZIALE**: schema diverso, dati diversi (parametric ha `tech.*`, catalog ha `applies_to`) | ALTO — pagina "Sistemi e formule profili" non alimenta il motore |
| Prezzo per colore | `item_pricelists.entries[]` (unificato) | `products.default_hardware_kit.price` | Solo per hardware kit fallback | BASSO |
| Categorie colore | `color_categories.is_premium` (una sola collezione) | — | Nessuna duplicazione fisica | OK |
| Formule vetro | `glass_recipes` (unica) | — | Nessuna duplicazione | OK |
| Prodotti | `products` (unica) | — | Nessuna duplicazione | OK |
| Config produzione | `production_config` (unica per tenant) | 2 doc trovati per PanoramaPilot | **DUPLICATO REALE** | MEDIO — `find_one` prende il primo, non deterministico |

**Fonte prevalente scelta dal codice**:
- **Motore commerciale** (`commercial_perimeter`): legge `products` + `item_pricelists.entries[]` + `color_categories.is_premium` + `glass_recipes` + `production_config`
- **Router parametric** (frontend `ParametricAdminPage`): scrive su `profile_systems`, `profiles`, `bom_templates` che NESSUN endpoint del motore commerciale legge.

**Sistema autorevole per il motore commerciale** = **B** (products + item_pricelists + glass_recipes).
**Sistema autorevole per il technical_cut_list** = **A** (profile_systems + bom_templates via `bom_engine_v2`).

**Divergenza attuale**: `products.components[].code = "5103"` e `profiles.code = "5103"` **NON hanno FK** e possono divergere silenziosamente.

---

## Sezione 3 · Verifica query

### Query critiche verificate

**catalog_service.py:123-135** — `resolve_component_prices`:
```python
pl_query = {"tenant_id": tenant_id, "deleted_at": None, "$and": [{"$or":[{"active":True},{"pl_status":"active"}]}]}
pl = await db.item_pricelists.find_one(pl_query)
```
- ✅ Tenant filter OK
- ✅ Soft-delete OK
- ❌ **NO ORDERING** per version/updated_at → se 2 listini attivi → non deterministico
- ❌ **NO valid_from/valid_to** → listini scaduti restano attivi
- ✅ Currently 0 tenant ha >1 listino attivo (verificato)

**catalog_service.py:36-50** — `get_production_config`:
- ❌ Ritorna `default_glass_price_per_sqm=76.0` e `default_glass_min_sqm=0.50` come **valori inventati** silent se config manca
- ❌ Ritorna anche in caso `exists=False` — l'assembler userà 76€/m² anche se il tenant non l'ha configurato

**quotes.py:449-462** — Guard "sent":
```python
blocked_products = await db.opening_products.find({...blocking_errors: {"$exists": True, "$ne": []}}, ...)
if blocked_products: raise HTTPException(...)
```
- ❌ **BUG CRITICO**: cerca in collezione `opening_products` che NON contiene mai i dati del preventivo (le linee sono in `quotes.lines[]`). Il guard **non blocca mai** l'invio di preventivi con `pricing_status != ok`.

**quote_structure.py:104** — Guard demo:
```python
if p.get("is_demo") is True or p.get("environment_scope") == "test":
    raise HTTPException(...)
```
- ✅ OK

**bom_engine_v2.py:80-99** — `_build_lookups_with_origin`:
- ✅ Tenant filter OK
- ✅ Require `ipl_status='active'` OK (bloccante con PRICELIST_NOT_PUBLISHED)

---

## Sezione 4 · Verifica motore `commercial_perimeter`

**Formule verificate**:
```
external_perimeter_ml = 2*(L_m + H_m)                    ✅ commercial_perimeter.py:247
sash_perimeter_ml = external + 2*H*max(n-1,0)             ✅ line 250
meeting_stile_ml = H_m * (n-1)                            ✅ line 252 (solo n>1)
```

**Componenti verificati**:
- ✅ Telaio (line 334) — SÌ presente su fisso e apribile
- ✅ Rinforzo telaio (line 335) — SÌ
- ✅ Anta (line 337) — SOLO se `window_type=="apribile"`
- ✅ Rinforzo anta (line 338) — idem
- ✅ Fermavetro (line 336) — SÌ (usa `sash_perim` per apribile, `ext` per fissa)
- ✅ Scambio battuta (line 339) — SOLO se `extra_sashes > 0 && apribile`
- ✅ Rinforzo scambio (line 340) — idem
- ✅ Vetro con `min_billable_sqm` (line 317-318)
- ✅ +6% Premium solo su PVC (line 357-362): frame + sash + glazing_bead + meeting_stile + additional*share
- ✅ Manodopera = time_min/60 * hourly (line 370)
- ✅ Margine come % su total_internal_cost (line 388)
- ✅ Sconto come importo assoluto (line 390-392)

**Fissa vs apribile** (line 285-297):
- ✅ Fermavetro fisso usa `ext` (line 285)
- ✅ Anta/rinforzo/scambio saltati per fissa

**Nessun `or 0` silent** su valori bloccanti — pattern `_D(x) if x is not None else Decimal("0")` (safe).

**Snapshot hash deterministico** (line 436-461): esclude timestamp `computed_at`, include tutti gli input+output significativi.

**Verdetto**: motore commerciale **CORRETTO** per la ricetta implementata. Nessun bug critico nella math core.

---

## Sezione 5 · Verifica motore `technical_cut_list` / BOM engine

**File**: `services/parametric_engine.py` + `bom_engine_v2.py`

- ✅ Formule via `eval_formula` con `strict=True` (line 169)
- ✅ Div/0 solleva `FormulaError` bloccante (line 158-163 di formula.py)
- ✅ `CUT_TOO_LONG` bloccante (parametric_engine.py:211-222)
- ✅ Scarto (waste_pct, scrap_fixed_mm_per_cut, scrap_fixed_per_piece) — 3 tipi supportati
- ✅ Bar rounding (barra intera imputata) — configurabile
- ✅ Sfrido e residui minimi (min_reusable_scrap_mm) tramite `nesting.py`

**Anomalia**: `parametric.py:693` chiama `resolve_bom` **senza tenant_id** nel signature — ma tenant è già filtrato nella query precedente (`bom_templates.find_one`) → NO tenant leak. OK.

**Componenti mancanti**: il technical_cut_list **NON** verifica di usare gli stessi codici anagrafica del motore commerciale. Un componente `code="5103"` in `products.components[]` potrebbe non esistere in `profiles.code` — non c'è integrity constraint. Rischio per il fix architetturale.

---

## Sezione 6 · Formule vetro

**Ricette DB** (glass_recipes count = 6):
- ProEvolution 1 anta apribile → `wr=206, hr=206, split=1, qty=1` ✅
- ProEvolution 2 ante apribile → `wr=347, hr=206, split=2, qty=2` ✅
- ProEvolution fissa → `wr=108, hr=108, split=1, qty=1` (default provvisorio dichiarato)
- ProEvolution Restauro 1a, 2a — identiche

**Duplicati**: 0 verificati (query aggregazione — nessun `product_key+window_type+n_sashes+tenant_id` duplicato).

**Formule 3 e 4 ante**: **ASSENTI** — le richieste 3-ante/4-ante ritornerebbero `MISSING_GLASS_RECIPE` (comportamento corretto per P2).

**BUG-06 [HIGH]** — `glass_engine.py:156` — `int((L_mm - wr) / sf)` usa **troncamento** (Python `int(3.7)=3`) invece di rounding. Es. 2 ante con L=1400, wr=347, sf=2 → `(1400-347)/2 = 526.5 → 526`. Perde 0.5mm silent. Deve usare `Decimal.quantize(ROUND_HALF_UP)` o esplicitare warning se scarto > 0.5mm.

**Custom formulas** (line 159-169): usano `eval_formula(..., strict=True)` — safe.

---

## Sezione 7 · Unità di misura

| Componente | Unità dichiarata | Verificato |
|---|---|---|
| Profilo (telaio, anta, ecc.) | €/ml | ✅ `catalog_service.resolve_component_prices` restituisce Decimal €/ml |
| Vetro | €/m² | ✅ `commercial_perimeter.py:347` |
| Ferramenta | € (fisso) | ✅ `commercial_perimeter.py:351` |
| Manodopera | €/h | ✅ line 370 |
| Servizi | € fisso | ✅ line 378-380 |

**Conversioni** in `commercial_perimeter`:
- ✅ mm→m: `Decimal(inp.L_mm) / Decimal(1000)` (linee 245-246)
- ✅ mm²→m²: `(gw * gh) / Decimal(1_000_000)` (line 310)
- ✅ min→h: `production_time_minutes / 60` (line 370)

**Precisione**:
- ✅ `Decimal` in tutti i calcoli intermedi
- ✅ `_round_money(quantize(0.01, ROUND_HALF_UP))` solo in `display_dict` (line 165-166)

**Nessun problema di unità rilevato.**

---

## Sezione 8 · Versionamento e immutabilità

**Snapshot pricing**:
- ✅ `quote_structure.py:477` — `pricing_snapshot` salvato integralmente in `quotes.lines[]`
- ✅ `pricing_snapshot_hash` deterministico via `commercial_perimeter._compute_hash`
- ✅ Timestamp `computed_at` **escluso** dall'hash (line 273 bom_engine_v2)

**Preventivi legacy** (sez. 17):
- ✅ `is_legacy_quote()` (quote_structure.py:38) — deterministico
- ✅ `_assert_not_legacy()` blocca mutations con 409 LEGACY_QUOTE_READ_ONLY

**Listini**:
- ⚠️ `item_pricelists` **NON versionato** con `valid_from/valid_to` obbligatori — solo `ipl_status='active'` binario
- ⚠️ Modifica in-place possibile (nessun trigger che crea nuova versione)

**Preventivi inviati**:
- ✅ `quote_status='sent'` → `_assert_editable` blocca modifiche (quotes.py:178-180)
- ✅ `price_snapshot` frozen su `sent` (quotes.py:476-483)
- ⚠️ ma `price_snapshot` legacy diverso da `pricing_snapshot` per singola line

**Contratti firmati**: ✅ `signed` è stato terminale, richiede `create-variation` per revisioni.

---

## Sezione 9 · Preventivi legacy

Verifica algoritmo `is_legacy_quote()`:
- ✅ `is_legacy=True` → legacy
- ✅ `pricing_engine≠"commercial_perimeter"` → legacy
- ✅ Nessuna line → non legacy (vuoto è ok)
- ✅ Almeno una line con `base_price>0` e `pricing_snapshot=None` → legacy
- ✅ Preventivi inviati/firmati/convertiti mantengono immutabilità via `_assert_editable` (quotes.py:179)

**Deterministico**: sì.  
**Protetto backend**: sì (409 su tutte le mutations).  
**Comportamento su empty**: preventivo vuoto NON marcato legacy (corretto — è una bozza nuova).

---

## Sezione 10 · Permessi (verificati sul catalogo)

| Permesso | Endpoint richiesti | Backend enforced |
|---|---|---|
| `catalog.view` | `/catalog/code-mappings`, `/catalog/products/{id}` | ✅ `require_permission("catalog.view")` |
| `catalog.manage` | POST/PATCH code-mappings, POST components | ✅ |
| `catalog.publish` | POST lifecycle | ✅ |
| `pricing_admin.view` | GET production-config | ✅ |
| `pricing_admin.manage` | PATCH production-config | ✅ |
| `pricing_admin.view_costs` | Visibilità costi interni in `/simulate` | ✅ (line 335-342 catalog.py) |
| `quotes.view_costs` | idem | ✅ |
| `quotes.edit_prices` | inserimento manuale `unit_price>0` | ✅ (`_guard_unit_price`) |
| `pricelists.view/manage` | `/parametric/item-pricelists`, `/parametric/price-matrices` | ✅ |
| `products.view/manage` | `/parametric/profile-systems`, `/parametric/profiles` | ✅ |

**Nessun ruolo può bypassare per URL diretto** — tutti gli endpoint hanno `Depends(require_permission(...))`.

**Tenant leak**: verificato — tutti gli endpoint filtrano su `tenant_id = user["tenant_id"]`. Il router `search.py` fa 8 lookup separati, ognuno con tenant filter.

**Assenti**: `profile_systems.publish`, `formulas.publish`, `pricelists.publish` — non ci sono state transition endpoint (solo `active/draft/archived` via update).

---

## Sezione 11 · Frontend "Sistemi e formule profili"

**File**: `ParametricAdminPage.jsx`

**Azioni implementate**:
- ✅ Caricamento (line 40-51) — GET `/parametric/{section}` per 11 sezioni
- ❌ Creazione — NESSUN pulsante "+ Nuovo"
- ❌ Modifica inline — NESSUNA
- ❌ Duplicazione — NESSUNA
- ❌ Salvataggio — pagina è **read-only lista**
- ❌ Pubblicazione — NESSUNA
- ❌ Simulazione — NESSUNA
- ✅ Refresh — presente
- ⚠️ Il badge "Dati DEMO presenti" appare ma non filtra
- ⚠️ Gestione errore: solo `toast.error("Errore caricamento")`, no error boundary

**Verdetto**: pagina architettonicamente rotta — non permette all'admin di fare nulla, solo visualizzare. Serve riscrittura completa (parte del piano di unificazione).

**Componenti controllati/non controllati**: N/A (nessun form).

**Race condition**: N/A (no concurrent operations).

**Il P0 bug segnalato dal Product Owner è confermato**: la pagina **non alimenta** il motore commerciale né `products`, né `item_pricelists`, ma solo le collezioni `profile_systems` / `profiles` che il motore commercial_perimeter **non legge mai**.

---

## Sezione 12 · Migrazioni e seed

**Seed attivi** (verifica in `server.py` + `seed_*.py`):
- ✅ `run_seed()` — Infissi Express Cloud demo (protetto da `DEMO_SEED_ENABLED=true`)
- ✅ `run_catalog_seed()` — ProEvolution + ProEvolution Restauro (idempotente, `is_system=True`)
- ✅ `seed_factory_code_mappings()` — 4 mapping (5103, 5105, 12130, 7379) system-wide
- ✅ `seed_factory_glass_recipes()` — 6 ricette system (`tenant_id=None`)
- ✅ `run_seed_extensions()` — LE, moduli SaaS, product types, install rules (idempotente)
- ✅ `seed_pdf_defaults()`, `seed_pricing_defaults()` — pricelist di default (con guard)

**Idempotenza verificata**: tutti i seed usano `find_one → skip if exists` pattern.

**demo_mode**:
- ✅ `DEMO_MODE=false` default in `.env`
- ✅ `quote_structure._guard_demo_product` blocca `is_demo=true` in preventivi reali
- ⚠️ **1 prodotto `is_demo=true` presente in DB** (seed test motore) — sarebbe correttamente bloccato

**Tenant PanoramaPilot**: nessun seed applica dati a questo tenant (seeds ancorati a Infissi Express `company_id`) — verificato.

---

## Sezione 13 · Performance (analisi statica)

**Indici mancanti** (verificato via `index_information()`):
```
item_pricelists:          NESSUN indice (solo _id)         ← BUG-04
glass_recipes:             NESSUN indice                     ← BUG-04
color_categories:          NESSUN indice                     ← BUG-04
profile_systems:           NESSUN indice                     ← BUG-04
catalog_code_mappings:     NESSUN indice                     ← BUG-04
production_config:         NESSUN indice                     ← BUG-04

quotes:                    ✅ 5 indici (tenant_id + campi vari)
products:                  ✅ tenant_id_1_key_1
```

**Query N+1 potenziali**:
- ✅ `bom_engine_v2._preload_anagraph` — batch lookup con `$in` (linee 46-53). OK.
- ⚠️ `search.py` — 8 collezioni interrogate in parallelo con `asyncio.gather` — OK.
- ⚠️ `catalog_service.resolve_component_prices` — itera `entries[]` sequenzialmente per ogni codice (O(kinds × entries)). Accettabile per <500 entries.

**Cache**: nessuna cache implementata per config produzione o pricelist (invalidazione complessa).

**Bundle frontend**: non verificato in questo audit (solo backend statico).

**Verdetto**: le query lente attese sotto carico sono su `item_pricelists.find_one()` + `entries[]` scan. Per 100k righe listino bisogna aggiungere indici in `entries` (query separata).

---

## Sezione 14 · Error handling

**Codici errore strutturati** (verificati):
- ✅ Motore commerciale ritorna `blocking_errors: [{code, variable, message}]`
- ✅ HTTPException con `detail={code, message, ...}` per 4xx bloccanti
- ✅ 409 LEGACY_QUOTE_READ_ONLY con `quote_id`
- ✅ 422 PRICING_INCOMPLETE con `blocking_errors`
- ✅ 403 MANUAL_PRICE_NOT_ALLOWED
- ✅ 403 DEMO_PRODUCT_NOT_ALLOWED

**Stack trace mai esposti**: verificato — solo `type(e).__name__: {e}` in un solo posto (quote_structure.py:432) — OK visibile all'admin ma non traccia file/riga sensibile.

**FormulaError**: campi `code, message, formula, severity, meta` — struttura completa (formula.py:112-116).

**Frontend**: mostra `e.response.data.detail` in maggior parte dei casi. Errori 422 con `blocking_errors: []` renderizzati come lista (verificato in `ProductSimulatorPage:177-189`).

**Uncatched exceptions**: 
- `contracts.py:458, 663` — `except Exception: pass` in signature workflow. Il primo (line 458) è per `record_activity` best-effort. Accettabile.
- `importer.py:41` — swallow su parse XLS (accettabile per format detection).
- **`services/rate_limiter.py:143, 152`** — swallow su Redis timeout con fallback in-memory. OK.

**Nessun `except: pass` critico rilevato.**

---

## SEZIONE 15 · BUG TROVATI (classificati)

### CRITICAL (blocca la vendita o l'integrità dati)

**BUG-01 [CRITICAL]** — `quotes.py:449-462` — Guard `sent` legge da collezione inesistente `opening_products`.  
**Impatto**: preventivi con `pricing_status='incomplete'` possono essere inviati al cliente. Viola P2 e §16.3 dell'architettura.  
**Fix**: leggere `q.lines[].pricing_snapshot.blocking_errors` inline.

**BUG-03 [CRITICAL]** — `catalog_service.py:24-33 + 36-50` — `DEFAULT_PROD_CFG` inventa `default_glass_price_per_sqm=76.0` e `default_glass_min_sqm=0.50` come **valori silent** se tenant non ha config.  
**Impatto**: motore calcola prezzi vetro con valori non configurati dall'utente. Viola P6 (nessun valore inventato) e §16.4 (nessuna sostituzione silent a zero → applicabile anche a valori inventati).  
**Fix**: rimuovere i default silent per glass_price/min_sqm. Deve emergere come MISSING_GLASS_PRICE / MISSING_GLASS_MINIMUM se tenant non l'ha impostato.

**BUG-14 [CRITICAL/ARCHITETTURALE]** — `ParametricAdminPage.jsx` disconnesso dal motore.  
**Impatto**: admin non può alimentare il preventivatore da UI.  
**Fix**: **NON in scope audit** — richiede opzione D2:b (unificazione).

### HIGH

**BUG-02 [HIGH]** — `catalog_service.py:123-135` — `resolve_component_prices` senza ordering deterministico su `item_pricelists.find_one()`.  
**Impatto**: se 2+ listini attivi coesistono (oggi 0, ma design fragile), prezzo non deterministico.  
**Fix**: ordinare per `version DESC, updated_at DESC`.

**BUG-04 [HIGH]** — Indici mancanti su 6 collezioni hot (item_pricelists, glass_recipes, color_categories, profile_systems, catalog_code_mappings, production_config).  
**Impatto**: full-scan multi-tenant sotto carico.  
**Fix**: creare indici composti `{tenant_id: 1, code: 1, deleted_at: 1}`.

**BUG-06 [HIGH]** — `glass_engine.py:156` — troncamento `int((L_mm - wr) / sf)` invece di ROUND_HALF_UP.  
**Impatto**: per 2-ante, dimensioni vetro perdono fino a 0.5mm silent.  
**Fix**: `Decimal.quantize(ROUND_HALF_UP)` con warning se resto > 0.5mm.

**BUG-15 [HIGH]** — `production_config`: 2 documenti per tenant PanoramaPilot in DB (violation di unique per tenant_id).  
**Impatto**: `find_one` prende il primo ordinato per `_id` (non deterministico).  
**Fix**: creare unique index e deduplicare (mantenere il più recente `updated_at`).

### MEDIUM (documentati, NON corretti automaticamente)

- **BUG-05** `parametric.py:490-506` — `_perms` cache locale ma bypassabile — OK ma spaghetti
- **BUG-07** `catalog_service.py:149-166` — logica preferenza colore corretta ma difficile da leggere
- **BUG-09** `item_pricelists` — dual convention `active` boolean vs `pl_status='active'` — refactor pulizia
- **BUG-10** `quote_structure.duplicate_opening` non ricalcola snapshot_hash sulle line duplicate
- **BUG-11** `delete_environment` non ricalcola totali del preventivo
- **BUG-12** `is_legacy_quote` deterministico ma nessun campo `is_legacy` persistito → ricalcolato ogni volta
- **BUG-13** `glass_engine` recipe fissa: `hr=108, wr=108` è default provvisorio dichiarato — attende spec

### LOW (solo cosmetici)

- Nessun `data-testid` in alcuni componenti `ParametricAdminPage`
- Toast generici "Errore caricamento" senza dettaglio

---

## SEZIONE 16 · TEST OBBLIGATORI

Vedi `/app/backend/tests/test_audit_v1_regression.py` (creato in questo audit).

**Test aggiunti (BUG-01, BUG-03, BUG-04, BUG-06)**:
1. `test_send_quote_blocked_when_line_incomplete` — verifica BUG-01
2. `test_no_silent_default_glass_price` — verifica BUG-03
3. `test_hot_collections_have_tenant_indexes` — verifica BUG-04
4. `test_glass_engine_no_silent_truncation` — verifica BUG-06

**Test già esistenti (verifica passing)**:
- `test_finestra_1a_recipe.py` — 16 test
- `test_catalog_area.py` — 11 test
- `test_commercial_perimeter.py` — 7 test
- `test_motor_full_listino_hard.py` — 1 test hard
- Totale: 58/58 verdi ante-audit

---

## SEZIONE 17 · Report finale

### File modificati in Fase B fix
| File | Bug | Descrizione fix |
|---|---|---|
| `app/services/catalog_service.py` | BUG-02, BUG-03 | rimozione default silent + ordering deterministico |
| `app/routers/quotes.py` | BUG-01 | guard `sent` legge `q.lines[].pricing_snapshot` |
| `app/services/recipes/glass_engine.py` | BUG-06 | ROUND_HALF_UP + warning |
| `app/services/indexes.py` | BUG-04 | aggiunta 6 indici tenant-scoped |
| `backend/tests/test_audit_v1_regression.py` | — | 4 nuovi test regressione |

### Endpoint modificati
- `POST /api/quotes/{id}/status` (indirettamente — logica interna guard `sent`)

### Modelli modificati
Nessuno (solo comportamento).

### Migrazioni eseguite
Nessuna dato-migration. Solo indici DB.

### Dati demo
- 1 `is_demo=true` product già bloccato da guard — OK

### Rischi residui (post-fix)
1. **BUG-14 (unificazione)** rimane aperto — richiede piano D2:b
2. Listini senza `valid_from/valid_to` — accettato per ora (unificazione lo risolve)
3. **BUG-15 duplicato production_config** — solo cleanup manuale
4. Ricetta vetro fissa `wr=108, hr=108` — attende conferma spec

### Checkpoint iniziale
- Tag: `pre-audit-v1-2026-02` (commit precedente `870d704`)

### Commit finale
- Tag: `p1-audit-v1-fixes` (dopo tutti i fix + test verdi)

### Verdetto
**Il sistema NON è ancora corretto end-to-end perché**:
- BUG-14 (unificazione) blocca l'admin dal configurare componenti/formule via UI
- BUG-15 (production_config duplicato per PanoramaPilot) deve essere pulito

**Il sistema è corretto entro il perimetro commercial_perimeter già collegato**:
- Config → catalogo → prezzi → simulazione → snapshot → preventivo funziona per il tenant Infissi Express (dove i seed hanno alimentato tutto)
- Il tenant PanoramaPilot rimane pulito, in attesa del piano di unificazione

---

**Documento chiuso.**
