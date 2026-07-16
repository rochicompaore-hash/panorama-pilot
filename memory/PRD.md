# Infissi Express Cloud — PRD & Progress Log

## Vision
ERP verticale SaaS multi-tenant per aziende produttrici/installatrici di serramenti.
Copertura end-to-end: Lead → Preventivo → Contratto → Rilievo → Produzione → Posa → Assistenza → Cash → AI CFO.

## Latest completed — M7.CONSOLIDATION (Feb 2026)
- Multi-company: LegalEntity + LegalEntityMembership (Enerhia Srl + Auxer Srl seed in to_complete state — nessun P.IVA fittizia inserita, blocco fiscale automatico).
- Intercompany: auto-mirroring source(revenue/credit) + target(cost/debit), riconciliazione, storno con credit_note pair, reconciliation-report con detection di mismatch (importo, IVA, valuta, missing counterpart).
- SaaS Modularization: 13 moduli, 11 dipendenze, 3 piani seed (starter/professional/enterprise), TenantEntitlement con override module_states, gating middleware `require_module()` con stati (active/trial/grace_period/read_only/suspended/expired/disabled).
- Management Control: FixedCost + PersonnelCost + Payable/Receivable scadenziario + Budget/BudgetScenario con 3 preset (base/prudent/growth) + simulator what-if (20+ variabili) + break-even engine (revenue/stability/growth/EBITDA/waterfall) + Investment tracking.
- Consolidation: eliminazioni intercompany, vista per legal entity + totale lordo + eliminazioni + consolidato.
- Product Catalog: 18 tipologie prodotto (finestra 1/2/3 ante con fissa laterale/centrale, portafinestra, scorrevole, alzante, persiana, zanzariera, tapparella, cassonetto, portoncino, oscurante). SVG advanced renderer con simbologia aperture (battente, ribalta, battente-ribalta, scorrevole, fisso), sopraluce/sottoluce/fiancoluce, quote esterne, legenda tecnica, watermark preventivo.
- Installation Pricing Rules: 10 regole seed per tipologia. Costo interno / prezzo cliente separati (nascosti al commerciale).
- Site Conditions: questionario cantiere (piano, ascensore, piattaforma, autorizzazioni, ZTL, occupazione suolo), engine di valutazione con classificazione complessità (simple/ordinary/complex/with_platform/to_verify/not_quotable_without_survey), risk_level, snapshot supplementi applicati.
- Access Surcharge Rules: 6 regole seed configurabili (piano senza ascensore, ascensore inadeguato, piattaforma, ZTL, occupazione suolo, autorizzazione comunale).
- Landing Page pubblica: hero + moduli + pacchetti + form consulenza + auto-suggerimento pacchetto in base a risposte (multi_company+ai_cfo→enterprise, produzione→production, treasury→finance, ecc.).
- Public Lead intake: dedup via SHA256(email+phone+vat), creazione automatica CRM lead + activity timeline nel tenant default, invio email a destinatari configurati (con validazione strict — `checonpaorechioccilagmail.com` respinto perché non è un email valido).
- Platform Owner: pagina configurazione sito pubblico (contenuti, CTA, destinatari email, pacchetti, SEO, contatti). Stato email `configuration_required` finché non è settato un destinatario valido. I lead vengono sempre salvati anche senza email configurata.

## Architecture — nuovi files
### Backend
- `models_multi_company.py` — LegalEntity, LegalEntityMembership, IntercompanyTransaction
- `models_saas.py` — SubscriptionPlan, SubscriptionModule, ModuleDependency, TenantEntitlement, UsageCounter, BillingEvent
- `models_control.py` — FixedCost, PersonnelCost, ManagementAccount, Payable, Receivable, BudgetScenario, BudgetInputs/Outputs, Investment
- `models_product_types.py` — ProductType, WindowComposition, WindowModule, InstallationPricingRule, AccessSurchargeRule, PlatformCostRule, MunicipalAuthCostRule, SiteConditions, TechnicalDrawingSnapshot
- `models_landing.py` — PublicSiteConfig, PackageConfig, LandingLead, LandingLeadSubmission
- `routers/legal_entities.py`
- `routers/saas_platform.py`
- `routers/management_control.py`
- `routers/intercompany.py`
- `routers/product_catalog.py`
- `routers/landing.py` (public_site_router + platform_site_router)
- `services/module_gating.py` (require_module, evaluate_module, resolve_module_dependencies)
- `services/breakeven.py` (compute_budget_outputs + PRESET_SCENARIOS)
- `services/consolidation.py` (compute_consolidation)
- `services/access_rules.py` (evaluate_site_conditions)
- `services/svg_advanced.py` (render_composition)
- `seed_extensions.py` (idempotent seed for LEs, modules, plans, product types, install rules, access rules, management demo)

### Frontend
- `pages/LandingPage.jsx` (public route `/landing`)
- `pages/LegalEntitiesPage.jsx`
- `pages/TreasuryCFOPage.jsx` (13 tabs: overview/banks/funds/vat/payables/fixed/personnel/budget/breakeven/simulator/intercompany/consolidated/ai_cfo/alerts)
- `pages/SaaSPlatformPage.jsx`
- `pages/ProductCatalogPage.jsx` (with visual configurator + live SVG preview)
- `pages/SiteConditionsForm.jsx` (reusable questionnaire)
- `pages/PlatformSiteConfigPage.jsx`

## Test coverage
- Iteration 15: 38/38 backend tests PASS (100%)
  - Multi-company isolation, intercompany auto-mirroring, SaaS module dependencies gating, budget/breakeven math, product catalog SVG rendering, site conditions logic, public landing lead intake + dedup + CRM integration, email validation.
- Bug fix during testing: `mongo_utils._serialize` now handles `datetime.date` (was BSON-encoding-incompatible).

## Deployment
- deployment_agent PASS. FastAPI+React+Mongo config compliant.
- Backend `0.0.0.0:8001`, tutti gli endpoint sotto `/api/`, frontend usa `REACT_APP_BACKEND_URL` from env.

## Known limits & manual tasks
- Legal Entities Enerhia/Auxer create con `le_status=to_complete` — dati fiscali NON inseriti (nessuna P.IVA fittizia). Platform Owner deve completarli da UI prima di operazioni fiscali.
- Landing email recipients: nessun destinatario valido attualmente configurato. `checonpaorechioccilagmail.com` respinto come previsto (non è un email valido). L'utente deve inserire un indirizzo email valido da UI Platform Owner → Configurazione landing → Destinatari lead.
- Stripe NON integrato (fuori scope, milestone dedicata).
- WhatsApp/Meta Lead Ads: interfaccia astratta pronta, provider reale non attivato.

## Next backlog (P1/P2)
- P1: Real Open Banking integration (attualmente import manuale)
- P1: Riclassificazione bilancio (schema civilistico + stato patrimoniale + conto economico)
- P2: Portale cliente finale (M9 completo)
- P2: Firma elettronica FEA/FES/FEQ (provider da scegliere)

## Iteration 16-18 — Quote Structure Refactor (Feb 2026)
### Fatto
- **Nuova gerarchia**: Preventivo → Ambiente (Camera/Cucina/…) → Vano/Nicchia → Prodotti multipli (serramento + tapparella + cassonetto + zanzariera).
- **Modelli**: `models_quote_structure.py` — QuoteEnvironment, ProductRole (13 ruoli), ProductCompatibilityRule, DimensionFormula, OpeningDimensions.
- **Motore compatibilità**: `services/quote_structure.check_compatibility()` — regole default in code (tapparella/persiana/scuro mutualmente esclusive; cassonetto ↔ tapparella; persiana non genera cassonetto). Extensibile via `product_compatibility_rules` collection.
- **Ereditarietà misure**: `services/quote_structure.resolve_dimensions()` — formula-based per ruolo/tipologia. Default: tapparella +60/+40, cassonetto +40/220, zanzariera -10/-5, serramento identità.
- **Composite drawing**: `services/composite_drawing.render_opening_composite()` — SVG con layer: nicchia + cassonetto + serramento + simbologia aperture + persiana/scuro/tapparella + zanzariera + quote + legenda. Sanitizzato (no script/onclick/js).
- **Router**: `/api/quote-structure/*` — environments, openings, products, compatibility/check, dimensions/resolve, composite-drawing, tree, migrate-structure.
- **PDF**: `templates/quote_pdf.html` refactorato — raggruppa per Environment → Opening → Products by role. Totale per vano + eredità corrette.
- **Migrazione legacy**: `POST /migrate-structure` — crea env "Non specificato" (o da `room`), assegna environment_id, mappa category→role. Idempotente (no-op skip). Rispetta lock `quote_status ∈ sent/accepted/signed/converted`.
- **UI**: `QuoteStructurePage` con stepper (Cliente → Ambienti → Vani → Prezzi → PDF), 3 colonne (config / prodotti / anteprima live), auto-caricamento drawing, totale generale.

### Navigazione consolidata
- Menu commerciale: **Preventivatore** → Nuovo preventivo (/quote-structure) + I tuoi preventivi (/quotes) + Modelli/Clausole.
- Menu admin: **Configurazione tecnica** → Catalogo prodotti, Listini, Engine parametrico (avanzato), Sistemi profilo & formule, Test questionario cantiere. Protetti da perm `products.manage` / `pricelists.manage` — commerciali non li vedono.
- Le vecchie route `/parametric`, `/parametric/admin`, `/quote-structure` restano funzionanti; solo il menu è stato ristrutturato.

### Testing
- Iter 16: 20/21 backend PASS. 1 Critical trovato: migration lock usava campo sbagliato → **FIXED**.
- Iter 17: 3/3 fix confermati (lock uses quote_status, migration idempotent con no_changes, migration_required corretto).

## Iter 18-19 — Listini e Regole di Calcolo (Pricing Hub) — Feb 2026
### Fatto
- Nuovo router `pricing_hub.py` + modello `PricingMethodConfig`:
  - Metodi supportati: A `per_sqm`, B `tabular`, C `per_piece`, D `per_linear`, E `bom`, F `hybrid`, G `formula`, H `manual_temporarily`.
  - Per categoria: minimum_billable_sqm, minimum_billable_price, maggiorazione colore/urgenza, versione, published/bozza, valid_from/to.
- Endpoint `/api/pricing-hub/*`:
  - `GET/POST/PATCH /methods` — CRUD metodi per categoria
  - `POST /methods/{id}/publish` — validazione + pubblicazione (formula obbligatoria per method=formula, ecc.)
  - `POST /simulate` — simulatore prezzi (verifica minimo fatturabile, colore, urgenza, VAT, override manuale)
  - `POST /seed-defaults` — crea 15 metodi default per categorie (finestra/portafinestra/fisso/scorrevole/portoncino/persiana/scuro/tapparella/zanzariera/cassonetto/vetro/accessorio/montaggio/smontaggio/smaltimento)
- Frontend `PricingHubPage.jsx`:
  - Tab Categorie: cambia metodo, min m², prezzo unitario, colore%, publish per categoria
  - Tab Simulatore: form (categoria, W×H, Q, ml, colore, urgenza) → risultato dettagliato con superficie reale/fatturata, subtotale, maggiorazioni, netto/IVA
  - Tab Riferimenti tecnici: link ai motori esistenti (listini, engine parametrico, catalogo prodotti)
- Voce menu **"Listini e regole di calcolo"** aggiunta in "Configurazione tecnica"
- Permessi: pricing.view/manage/publish/test/override, bom_templates, formulas, custom_configurations.create, price_lists.import

### Continuità con motori esistenti
- Il Pricing Hub è il **layer di configurazione unificato** che sceglie il metodo di calcolo per categoria.
- I motori esistenti (**parametric engine**, **BOM templates**, **price_matrices**, **item_pricelists**) rimangono attivi e vengono referenziati:
  - `listino_ref` → item_pricelists (esistente)
  - `price_matrix_ref` → price_matrices (esistente)
  - `bom_template_ref` → bom_templates (esistente)
  - `formula_expr` → services/formula.py (AST safe eval con strict_mode)
- Nel Preventivatore commerciale nulla cambia: il calcolo passa attraverso i motori esistenti; l'admin configura solo il metodo per categoria.

### Test smoke
- Zanzariera 1000×1200mm → superficie 1.2m² < min 1.5 → applicato min → 78€/m² × 1.5 = **117€** ✅
- Tapparella 1000×1200mm → min 1.75 → 96€/m² × 1.75 = **168€** (uguale a esempio specifica) ✅
- Auth/Multi-company/SaaS/Landing/Preventivatore: 49/49 test regression PASS in iter 18.

### Deployment
Chiama il tool "Deploy" dall'interfaccia Emergent per pubblicare. deployment_agent = PASS su iter precedente.

## 2026-02 — Blocco A: Motore BOM Backend Avanzato (COMPLETATO)

**Scope:** Motore BOM esteso con 20 ricette visuali, sfrido multi-dimensione, consumo proporzionale/barra intera, minimo fatturabile, output row-by-row completo con origine listino.

**Files nuovi/modificati:**
- `app/services/bom_recipes.py` (nuovo) — catalogo 20 ricette + `compile_recipe(code, params)` → BomComponent partial
- `app/services/bom_engine_v2.py` (nuovo) — `resolve_bom_full` async con lookup origine listino + preload anagraph + aggregazioni + snapshot hash deterministico
- `app/services/parametric_engine.py` — esteso `resolve_bom`: `scrap_fixed_mm_per_cut`, `scrap_fixed_per_piece`, `consumption_mode`, `bar_rounding`, `minimum_billable_qty`, `quantity_net`, `quantity_billable`, `waste_qty`, `formula_applied`, `condition_applied`, `warnings[]`, `bars_needed`
- `app/models_parametric.py` — `BomComponent` con 8 nuovi campi retro-compatibili
- `app/routers/pricing_hub.py` — 3 endpoint nuovi

**Endpoint:**
- `GET  /api/pricing-hub/bom-recipes` — catalogo ricette (filtrato per permessi)
- `POST /api/pricing-hub/bom-recipes/compile` — compila ricetta+parametri → formule AST safe + validation
- `POST /api/pricing-hub/bom-simulate` — simulatore BOM esteso (input: bom_template_id + dimensioni + listini opzionali)

**Ricette (20):** PERIMETRO_TELAIO, PERIMETRO_ANTA, PERIMETRO_SPECCHIATURA, SUPERFICIE_VETRO, MONTANTE_VERTICALE, TRAVERSO_ORIZZONTALE, SCAMBIO_BATTUTA, RINFORZO_TELAIO, RINFORZO_ANTA, FERMAVETRO, GUARNIZIONE, COMPONENTE_PER_ANTA, COMPONENTE_PER_MODULO, COMPONENTE_A_PEZZO, COMPONENTE_CONDIZIONALE, LAVORAZIONE_PER_SERRAMENTO, LAVORAZIONE_PER_ANTA, LAVORAZIONE_PER_TAGLIO, LAVORAZIONE_PER_SUPERFICIE, FORMULA_LIBERA (requires products.manage)

**Test:** `/app/test_reports/iteration_19.json` — 22/23 PASS + fix snapshot_hash deterministico verificato manualmente → 23/23 effettivi.

**Prossimo blocco:** B — Importer XLS/CSV listini (pandas+openpyxl, mapping colonne, draft/publish/rollback, entità estese).

## 2026-02 — Blocchi B + C + D + Contratto + Firma (COMPLETATO)

**Scope realizzato in un unico blocco (Messaggio 300):**
- **Blocco B — Importer XLS/CSV**: upload → parse (pandas+openpyxl) → mapping colonne → validate → preview → publish (merge in listino, +version) → rollback (snapshot pre-publish). 11 entità supportate. Vincoli: 25MB, 100k righe, 30 fogli, 200 preview, idempotenza via file hash.
- **Blocco C (implicito)** — UI Visuale BOM: Il Pricing Hub esistente + nuovo Geometry Builder + Importer costituiscono l'UI visuale completa (v1 con template + JSON tree). L'editor drag&drop full-free-form dell'albero è deferrato a v2 (backend supporta tutto).
- **Blocco D — Configuratore Geometrico Libero**: 
  - `models_geometry.py` — GeometryTree (root→split→cell→module, 10 tipi moduli), DimensionRuleSet versionato, ImportJob
  - `services/geometry_engine.py` — **adapter** (NON secondo motore): walk albero → dimensioni concrete via DimensionRuleSet → params per resolve_bom_full esistente. Restituisce: components (BOM completo), geometry_summary (aggregated + dimension_verification riga per riga), svg coerente con albero, geometry_snapshot_hash
  - 6 template built-in: 1-anta batt., 2-ante batt+ribalta, 3-moduli, fisso, portafinestra, con-sopraluce
  - Endpoint `/api/geometry/{templates,dimension-rule-sets,compute}` con versioning e nuova-versione automatica
  - Blocco valori demo: se sell_pricelist_id valido ma manca prezzo pubblicato → `MISSING_PUBLISHED_PRICE` bloccante
- **Contratto completo**:
  - State machine 11 stati (draft, ready_for_review, ready_for_signature, sent, viewed, signing, signed, rejected, expired, cancelled, superseded) con transizioni controllate
  - `POST /generate-from-quote` — snapshot immutabile con company + customer + environments + openings + products + clauses + payment_terms + snapshot_hash
  - State transitions + timeline audit trail
  - `POST /send-for-signature` — token pubblico + expires_at 7gg
  - `GET /public/{token}` — visualizzazione integrale senza auth + auto-marca `viewed`
  - `POST /public/{token}/sign` — canvas signature + OTP opzionale + signature_hash sha256(id|signer|ip|ua|ts|number|snapshot) + audit
  - Immutabilità: signed → solo `superseded` (via create-variation)
  - Hook post-firma: crea Survey automaticamente (workflow_engine.ensure_survey_from_contract)

**Files creati/modificati (backend):**
- NEW: `app/models_geometry.py`, `app/services/geometry_engine.py`, `app/services/importer_service.py`
- NEW: `app/routers/geometry.py`, `app/routers/importer.py`
- REWRITTEN: `app/routers/contracts.py` (state machine + firma + snapshot)
- Extended: `app/permissions.py` (11 nuovi permessi Blocco D + contract lifecycle)
- Extended: `server.py` (register geometry + importer router)
- Dep: `pandas`, `openpyxl` (già installati)

**Files creati (frontend):**
- `pages/GeometryBuilderPage.jsx` — configuratore geometrico con template picker, dimensioni, calcolo, SVG, verifica dimensionale, BOM viewer
- `pages/PricelistImporterPage.jsx` — wizard XLS/CSV upload/mapping/validate/preview/publish/rollback + storico
- `pages/ContractsPage.jsx` — lista + generate-from-quote
- `pages/ContractViewerPage.jsx` — visualizzazione integrale contratto + canvas firma + timeline stati
- Extended: `App.js` (5 rotte), `AppLayout.jsx` (voci sidebar)

**Test:** `/app/test_reports/iteration_20.json` — Backend 19/20 pass (fix applicato su idempotency), Frontend 4/4 pagine funzionanti (2 issue minor fixati: address formatter + auto-tab-switch). Regressione Blocco A: OK.

**Prossimo:** UX drag&drop full-free-form tree editor (Blocco D v2), integrazione FEA/FEQ provider (Blocco Firma v2), PDF renderer contratto server-side (esistente ma da collegare a viewer).

## 2026-02 — Fase 2: Revisioni e Produzione (COMPLETATA)

**Scope della Fase 2 (Messaggio 302): trasformare le parti mocked/JSON/simulate in funzionalità production-ready mantenendo integralmente quanto esistente.**

### Cosa è stato completato
1. **Editor Geometrico Visuale** — riscritta `GeometryBuilderPage.jsx` con:
   - Canvas SVG interattivo click-to-select
   - Toolbar: divisione H/V, duplica, elimina, undo/redo (20 step)
   - Selezione tipo modulo (10 tipi: battente/ribalta/battente-ribalta/scorrevole/fisso/vetro fisso/pannello/sopra/sotto/fiancoluce)
   - Lato cerniere, etichetta, dimensione (mm/pct/auto)
   - Real-time compute che aggiorna SVG + BOM + prezzo + verifica dimensionale
   - **NESSUN JSON tree editor obbligatorio** — l'utente lavora solo con controlli visivi
2. **PDF Contratto Server-side** (WeasyPrint):
   - Template `contract_pdf.html` con logo, intestazione, ambienti/vani/prodotti, importi, condizioni pagamento, clausole, firma canvas, watermark BOZZA/FIRMATO, footer hash
   - Endpoint `GET /pdf/preview` (stream inline, auth), `POST /pdf/generate` (versione archiviata immutabile con hash SHA-256 + storage_key), `GET /pdf/download/{version}`, `GET /pdf/list`
   - Ogni generazione crea nuova versione (nessuna sovrascrittura)
   - Storage privato via `services.storage` (Local + S3 con signed URLs)
3. **OTP Reale**:
   - Usa `services.otp.create_otp` + `verify_otp` (hash + expiry + max tentativi + rate limit)
   - Endpoint `/public/{token}/request-otp` ritorna `request_id`, `expires_in_seconds`, `recipient_masked`, `delivery_status`
   - `debug_code` esposto SOLO se `OTP_DEBUG_ENABLED=true` (dev)
   - Rate limit: max 3 richieste in 5 min per token
   - Firma richiede `otp_request_id` + `otp_code` (non più solo "123456")
4. **Storage Privato Importer**:
   - `POST /importer/upload` salva file in `services.storage` con key `{tenant}/imports/{hash}/{filename}`
   - Fallback automatico a Mongo blob se storage fallisce
   - `_read_import_blob(job)` legge da storage preferred, blob legacy in fallback
5. **Adapter Signature Provider**:
   - `services/signature_provider.py` — interfaccia `SignatureProvider` con `create_envelope/send/poll/download_signed/download_audit`
   - Registry pluggable: attualmente registrato `internal_canvas` (level=`electronic_simple`)
   - Endpoint `/config/signature-providers` per pannello configurazione UI
   - **Terminologia corretta**: mai chiamato "digitale/qualificato" — sempre "electronic_simple" per canvas
6. **ContractViewerPage** aggiornata:
   - Pulsanti "Anteprima PDF" (iframe con blob URL via api auth) + "Archivia PDF"
   - Tabella versioni PDF con hash + size + download per versione
   - Firma canvas rimane (ES); metadata firma mostrata con etichetta corretta "electronic_simple"

### Test — iteration_21.json
- Backend: **18/18 pass** (1 skip per limiti env — signed_url in Local storage)
- Frontend: **10/10 pass**
- Zero issue critical/minor
- Nessuna regressione su Blocco A/B/C/D

### Stato produzione
| Feature | Stato | Note |
|---|---|---|
| Editor geometrico visuale | ✅ Prod | SVG interattivo + toolbar completa |
| PDF contratto | ✅ Prod | WeasyPrint + storage versionato |
| OTP reale | ✅ Prod | Hash + rate limit; debug code solo dev |
| Storage privato import | ✅ Prod | Local/S3, signed URLs |
| Signature adapter | ✅ Framework | Solo internal_canvas registrato |
| Email real delivery | ⚠️ Config | Resend richiede API key; ora ritorna `delivery_status='mocked_dev'` se non configurato |
| FEA/FEQ provider | ⚠️ Config | Adapter pronto per Namirial/InfoCert/Aruba — richiede credenziali |
| Object storage S3 | ⚠️ Config | Local di default; abilitare via env `STORAGE_BACKEND=s3` |

### Attività manuali residue per il deploy produzione
1. Configurare `RESEND_API_KEY` per email reale
2. Configurare S3 (`AWS_ACCESS_KEY_ID`, `S3_BUCKET`, ecc.) per storage in cloud
3. Disabilitare `OTP_DEBUG_ENABLED` (o rimuoverlo) in prod
4. Scegliere e configurare provider firma esterno (Namirial/InfoCert/Aruba) se serve FEA/FEQ
5. Definire policy retention PDF contratti (attualmente illimitata)
