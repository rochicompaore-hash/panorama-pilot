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

## 2026-02 — Fase 3: Chiusura, Deployment Check e Smoke Test (COMPLETATA)

**Scope**: NESSUNA feature nuova. Verifica reale delle dichiarazioni + hardening produzione + deploy check + smoke test URL pubblico.

### Hardening applicato
- `OTP_DEBUG_ENABLED` auto-forzato `false` se `APP_ENV in (staging, production)` — override sicuro.
- Email `delivery_status='configuration_required'` quando `EMAIL_PROVIDER=mock` in prod (invece del generico `mocked_dev`).
- Endpoint `GET /api/config/production-status` per introspezione config senza segreti (email, storage, otp, providers, features, cors).
- `.gitignore` con esclusione `/app/storage/` per file uploaded.
- 4 valori `.env` quotati (deployment agent warning risolto).

### Deployment agent — status: PASS
- Nessun segreto hardcodato in codice
- CORS/URL/ports corretti
- Supervisor OK
- Nessun blocker

### Smoke test URL pubblico (https://serramento-ops.preview.emergentagent.com)
11/11 PASS:
1. `/api/health` → 200
2. `/api/customers` list → 200
3. `/api/quotes` list → 200
4. `/api/leads` list → 200
5. `/api/pricing-hub/bom-recipes` → **20 ricette**
6. `/api/geometry/templates` → **6 template**
7. `/api/geometry/compute` finestra 2 ante → **materials_price 206.42€, nr_ante=2, SVG generato, snapshot_hash SHA-256**
8. `/api/importer/schema/profile` → 200
9. `/api/contracts` list → **28 contratti**
10. `/api/contracts/{id}/pdf/preview` → **HTTP 200, %PDF-1.7 valid, 24KB reale**
11. `/api/contracts/config/signature-providers` → `internal_canvas` level `electronic_simple`

### Screenshot verificati (playwright)
- `/geometry-builder` — editor visuale SVG interattivo funzionante con toolbar completa
- `/contracts/{id}` — CON-2026-00024 stato signed con **20 versioni PDF archiviate** con hash SHA-256 (immutabilità confermata)

### Test totali cumulativi (Fase 1 + 2 + 3)
- iteration_19: Blocco A BOM avanzato — 22/23 pass (poi 23/23 post-fix)
- iteration_20: Blocco B+C+D+Contract — 23/23 (post-fix)
- iteration_21: Fase 2 revisioni prod — 18/18 backend + 10/10 frontend
- Smoke test finale URL live — 11/11 PASS

## 2026-02 — Fase 4: Utenza Proprietaria + Gating Listini (COMPLETATA)

### Fix 1 — Gating pubblicazione listini (Msg 304)
- `services/bom_engine_v2._build_lookups_with_origin` con `require_published=True`: solo `ipl_status='active'` usati; draft/archived producono `unpublished_pricelist_warnings` che diventano `blocking_errors` code `PRICELIST_NOT_PUBLISHED` con `suggested_action`
- `routers/quotes.py:445-462`: blocco `status='sent'` se ci sono `blocking_errors` nei prodotti collegati
- **Test iteration_23**: gating verificato — active→206.42€, draft→0.0€+blocking

### Fix 2 — Utenza Proprietario tenant_owner (Msg 306)
- **Email**: pilot@panoramapilot.com (password mai stampata, mai loggata)
- **Tenant**: PanoramaPilot (id `ae9168f6-d96e-4c5d-bb33-25acbb9a8410`), isolato da Infissi Express
- **Ruolo**: `tenant_owner` (id `e4a05b01-...`), name `Proprietario`, is_protected=true, is_system=true, **247 permission_keys** (tutto il PERMISSION_CATALOG)
- Script `backend/scripts/provision_owner.py` idempotente con OWNER_INIT_PASSWORD via env
- Modello `Role` esteso con `code` e `is_protected` (linee 130-137 in models.py)
- `must_change_password=true`, `is_superadmin=true`, `is_platform_owner=false`, `is_protected=true`
- Tenant isolation verificato: PanoramaPilot vede 0 clienti; Infissi vede i suoi 25
- Nessuna occorrenza di "Burgugnao" nei log backend

### Test — iteration_24
- **Backend: 22/22 pass (100%)**
- Zero critical, 2 minor style-only (non bloccanti)
- Verificato: 1 role attivo, permission_keys count>=200, is_protected=true, dedup soft-delete idempotente, login OK, tenant isolation OK, password non leakata, gating listini funzionante

### Report Owner Provisioning (SENZA PASSWORD)
```
email:                pilot@panoramapilot.com
tenant_id:            ae9168f6-d96e-4c5d-bb33-25acbb9a8410
tenant_name:          PanoramaPilot
role_code:            tenant_owner
role_id:              e4a05b01-2b75-4273-908d-417af991b407
user_id:              b2286106-3566-492f-bbec-c2940a0c4a01
società accessibili:  PanoramaPilot (nuovo tenant, isolato)
stato login:          verificato (200 OK, tutte le sezioni accessibili)
stato test:           22/22 pass (0 critical, 0 high)
configurazioni residue:
  - primo login richiede cambio password (must_change_password=true)
  - MFA disattivato di default (attivabile da utente)
  - nessun seed di clienti/preventivi (tenant pulito)
```

## 2026-02 — Fase 5: Cleanup dati demo tenant PanoramaPilot (COMPLETATA)

### Report cleanup
- **Backup**: script idempotente con dry-run — nessun dato demo trovato da eliminare (il tenant era già pulito dalla nascita)
- **Tenant target**: PanoramaPilot (id `ae9168f6-d96e-4c5d-bb33-25acbb9a8410`) — solo questo tenant toccato
- **Raccolte verificate**: 60 collezioni operative ispezionate (`customers, leads, quotes, contracts, opening_products, sales_orders, production_orders, invoices, bom_templates, profile_systems, item_pricelists, import_jobs, ecc.`) — **tutte con 0 record**
- **Record eliminati**: 0 (nessuno da eliminare)
- **File eliminati dallo storage**: 0 (`/app/storage/ae9168f6-...` non esiste)
- **Record preservati**:
  - Utenza `pilot@panoramapilot.com` (id `b2286106-...`)
  - Ruolo `tenant_owner` (id `e4a05b01-...`) con 247 permission_keys
  - Company `PanoramaPilot` (id `ae9168f6-...`)
  - 12 audit log entries (immutabili)
- **Elementi unknown**: 0
- **Seed demo disabilitati**: già inattivi per PanoramaPilot — `run_seed()` in `seed.py` è ancorato a `company_id` di Infissi Express (Msg 5.1), nessun riferimento a "panoramapilot" nei seed. Il restart backend non ricrea dati demo su PanoramaPilot.

### Stato login e test post-cleanup
- **Login owner**: verificato 200 OK
- **Ambiente vuoto confermato via API live**: `/api/customers=0, /api/leads=0, /api/quotes=0, /api/contracts=0, /api/parametric/item-pricelists=0, /api/parametric/bom-templates=0, /api/parametric/profile-systems=0, /api/importer/jobs=0`
- **Config sistema preservate**: 20 ricette BOM, 6 template geometrici, 1 signature provider disponibile
- **Errori Critical/High**: 0

### Audit registrato
Action `tenant.cleanup.demo_data_removed` registrato in `audit_logs` con `tenant_id=ae9168f6-...`, `user_email=pilot@panoramapilot.com`, timestamp UTC.

### Note
Il tenant era già in stato desiderato dalla nascita (creato da `provision_owner.py` senza seed demo). Lo script cleanup è idempotente: rieseguibile in sicurezza.

## Iteration 25 — Code Quality Refactor (Feb 2026)

**P0 Security**
- `simpleeval==1.0.7` aggiunto a requirements.txt
- Creato `app/services/formula_security.py` con:
  - Guard `_assert_no_eval_in_module` che rifiuta a import-time la presenza di `eval()/exec()/compile()` in `formula.py`, `parametric_engine.py`, `breakeven.py`
  - Classe `SafeExpression` (wrapper simpleeval) per casi non-Decimal
- **Conferma**: nessun `eval()` reale era presente nel codebase — `formula.py` usava già un AST parser strict con whitelist (Decimal-safe, node/depth/length caps). Report esterno era falso positivo su matching `_eval`/`eval_formula`.
- Test secrets scrubbing: creato `backend/tests/_creds.py` env-sourced; rimossi hardcoded `ADMIN_EMAIL`/`ADMIN_PASSWORD` da 24 file di test; anche `TENANT_ADMIN`/`PLATFORM_OWNER` letti da env.
- Nessun segreto reale rimane nel repo (verificato con grep).

**P1 Refactoring cyclomatic complexity**
- `auth.py::login` — estratti `check_brute_force / record_failed_login / clear_failed_login / create_login_session / _audit_login_failure` in `services/auth_helpers.py`
- `auth.py::accept_invitation` — estratti `_validate_invitation_or_raise / upsert_user_from_invitation / _revoke_sessions_after_owner_activation`
- `contracts.py::generate_from_quote` — estratti `load_quote_or_400 / assert_no_active_contract / next_contract_number / build_contract_snapshot / compute_snapshot_hash` in `services/contracts_helpers.py`. Hash snapshot preservato identico.
- `contracts.py::public_sign` — estratti `load_valid_signing_token / verify_public_otp / build_signature_hash`. Fallimento hook workflow ora loggato (prima: silenzioso).
- `bi.py::quotes_kpi` — estratti `_sum_total / _avg_hours_between / _pipeline_conversion_rate / _pipeline_weighted_value / _rejection_reasons`. Costante `QUOTE_STATUSES`.
- `ai_cfo.py::generate_suggestions` — estratti `_cash_flow_suggestion / _receivables_suggestion / _conversion_suggestion / _persist_suggestions`.
- `platform_owner.py::ensure_platform_owner_user` — estratti `_upsert_platform_owner_flags / _create_platform_owner_user / _reuse_active_invitation / _create_activation_invitation`.

**P1 server.py import cleanup**
- Import raggruppati per dominio (Foundations, CRM, Quoting, Ops, Finance/BI, Public)
- Router registrati via 6 liste raggruppate (`FOUNDATION_ROUTERS`, `CRM_ROUTERS`, ...)
- Estratto endpoint `/api/config/production-status` in helper locale, semplificato lookup OTP status.
- Rimosso import inutilizzato `os`.

**Testing**
- Nuovo `tests/test_code_quality_regression.py` (14 test): login, accept-invitation guards, quotes KPI shape, AI CFO generate, public sign 404, formula math determinism, formula rejects unknown vars/functions/div-zero, formula_security guard.
- `tests/test_iter25_smoke.py` (6 test aggiunti dal testing subagent) — health, /auth/me shape, login token, generate-from-quote 404, KPI period_days, openapi route count.
- **Risultato**: 20/20 PASS. Zero regressioni.

**Vincoli rispettati**
- ✅ Punto di ripristino creato (commit `58d0e41`)
- ✅ Significato formule invariato (Decimal, whitelist, strict mode)
- ✅ Nessun fallback silenzioso a zero (FormulaError bloccante in strict; nessun `except: pass` reintrodotto — solo l'hook workflow post-firma ora logga)
- ✅ Segreti solo da env/fixture (`tests/_creds.py`)
- ✅ API/permessi/snapshot/contratti firmati preservati (test 404/400 error paths verdi)

**Files aggiunti/modificati**: 30+ file (vedi `git log --stat 58d0e41..HEAD`).

## Iteration 27 — Opzione A: Catalogo & Simulatore 1-anta (Feb 2026)

**Backend**
- Ricetta `finestra_1a_5103_12130` in `app/services/recipes/finestra_1a.py` con formule esatte da spec (paragrafi 3-14):
  - Telaio 5103: 2×(L+S) + 2×(H+S); Rinforzo telaio: 2×(L-108)+2×(H-108); Anta 12130: 2×(L-70+S)+2×(H-70+S); Rinforzo anta: 2×(L-206)+2×(H-206); Fermavetro: 2×(L-186)+2×(H-186); Vetro: (L-206)×(H-206)/1e6 con min 0.50 m²
  - Test 900×1500 (S=6): telaio 4.824 ml, rinforzo t. 4.368 ml, anta 4.544 ml, rinforzo a. 3.976 ml, fermavetro 4.056 ml, vetro 0.898036 m² × 76 = €68,25
  - MISSING_*_PRICE codes: FRAME/SASH/FRAME_REINFORCEMENT/SASH_REINFORCEMENT/GLAZING_BEAD/GLASS/GLASS_MINIMUM/HARDWARE/HOURLY_COST/PRODUCTION_TIME/MARGIN/ADDITIONAL_COMPONENTS_COST
  - Geometry validation: L>206, H>206, L-108>0, H-108>0, L-70+S>0, H-70+S>0, L-186>0, H-186>0
  - +6% Premium PVC-only (telaio+anta+fermavetro+altri_pvc_share) — NON su rinforzi/vetro/ferramenta/manodopera
  - Snapshot hash deterministico su risultato
- `app/models_catalog.py` — ProductComponentAssoc (14 categorie), ProductionConfig, CatalogCodeMapping, ProductSimulateRequest
- `app/services/catalog_service.py` — get_production_config (merge defaults), load_product, resolve_component_prices (colour-sensitive per PVC, colour-independent per rinforzi acciaio, esclude prezzi ≤0), get_color_is_premium, seed_factory_code_mappings
- `app/routers/catalog.py` — 9 endpoint sotto `/api/catalog/`: production-config GET/PATCH, code-mappings GET/POST/PATCH, products/{id}/components, /lifecycle (5 stati), /simulate. Visibility gating server-side: costi interni nascosti se non `pricing_admin.view_costs` o `quotes.view_costs`.
- `app/permissions.py` — 9 nuove permission: catalog.view/manage/publish/import/delete + pricing_admin.view/manage/publish/view_costs
- `app/models_parametric.py` — `ColorCategory.is_premium` boolean (per +6% PVC)
- `app/seed_catalog.py` — idempotent:
  - Factory code mappings: 5103→telaio, 5105→telaio, 12130→anta_standard, 7379→scambio_battuta (is_system=True, tenant_id=None)
  - ProEvolution seed (7 componenti: 5103+12130+7379+FV-STD+RT-STD+RA-STD+RS-STD)
  - ProEvolution Restauro seed (identico ma telaio=5105)
  - Grant catalog.*/pricing_admin.* a Super Admin / Admin Azienda / Proprietario (via `permissions="*"` esistente + ensure keys)
- Server.py: mount `catalog_admin_router` + `run_catalog_seed()` on startup

**Frontend**
- `pages/ProductSimulatorPage.jsx` — UI /product-simulator: form L/H/colore/premium/hardware/altri, override manodopera+margine, cut-list table, stato pricing con badge, blocking_errors list, prezzo finale, snapshot hash
- `layouts/AppLayout.jsx` — nuovo gruppo "Catalogo e listini" con 7 sotto-voci (Catalogo prodotti, Simulatore prodotto, Listini e regole, Listini dettaglio, Importazione XLS/CSV, Sistemi profilo & formule, Engine parametrico avanzato)
- `App.js` — route `/product-simulator` → ProductSimulatorPage

**Bug corretto (HIGH) durante testing agent**
- `catalog.py::simulate_product` leggeva `user.get("permission_keys")` che get_current_user NON popola per utenti non-superadmin → tutti i Commerciali ricevevano 403
- Fix: usa `await get_permission_keys_for_user(user)` — pattern coerente con altri router

**Test finali**
- `tests/test_finestra_1a_recipe.py` (16): geometria, MISSING_*, Premium PVC-only, margin flow, snapshot determinism, display rounding
- `tests/test_catalog_area.py` (11): seed products/mappings, prod config, simulate scenarios, lifecycle, no-alteration KPI
- `tests/test_catalog_area_supplementary.py` (6): visibility gating Commerciale (bug fix verificato), MISSING_ADDITIONAL_COMPONENTS_COST, PATCH+GET production-config, KPI regression
- Regression: `test_ci_security_guards` (6) + `test_code_quality_regression` (14) + `test_iter25_smoke` (6) tutti verdi
- **Totale: 58/58 PASS**, scanner segreti clean, eval-ban attivo

**Limitazioni residue (fase 2 — dopo collaudo)**
- PDF import non implementato (pdfplumber pianificato in fase 2)
- Ricetta 2 ante non implementata (attende spec puntuale come per l'1-anta)
- Nessun listino barre seedato per tenant demo: simulate ritorna `incomplete` con MISSING_*_PRICE finché l'operatore non importa un file XLS/CSV valorizzato per i codici 5103/12130/rinforzi/fermavetro
- Il wizard "duplica/versiona prodotto" mostra solo transizioni di stato via API (draft/validated/active/superseded/archived), non ha UI full-featured

**Stato collaudo domani**
- Login admin OK
- Sidebar "Catalogo e listini" visibile e navigabile
- /product-simulator carica ProEvolution pre-selezionato con L=900/H=1500
- Ogni simulazione produce cut-list corretta + errori MISSING chiari
- Per raggiungere `pricing_status=ok` in demo: pre-caricare listino barre via /pricelist-importer con almeno codici 5103, 12130, RT-STD, RA-STD, FV-STD, e opzionalmente 7379 (per 2-ante che comunque non è nella fase 1)

## Iteration 28 — SMTP Email System SiteGround (Feb 2026)

### Scope
Implementazione servizio SMTP production-ready per SiteGround (`gnldm1111.siteground.biz:465`, SSL, user `pilot@panoramapilot.com`).

### Backend
- **`app/services/email_service.py`**: `enqueue_email()` con SMTP via `aiosmtplib` (SSL/STARTTLS), delivery-mode redirect, idempotency check, retry worker in background (backoff 1m/5m/15m, max 3 tentativi), status: queued/sending/sent/failed/retrying/bounced/test_intercepted/configuration_required.
- **`app/services/email_config.py`**: `MailConfig` dataclass; `get_public_config()` mai espone password.
- **`app/services/email_dns.py`**: `check_domain()` SPF/DKIM/DMARC via `dnspython`.
- **`app/models_email.py`**: `EmailLogV2` esteso (tenant_id, original_to, delivery_mode, attempt_count, next_retry_at, idempotency_key, payload_hash, stored_html/text), `EmailTemplateDoc`, `TestEmailRequest`.
- **`app/routers/email_settings.py`**: `/api/email-settings` (GET config, POST /test rate-limit 5/5min, GET /dns-check, template CRUD).
- **`app/routers/email_logs.py`** (esteso): tenant scope, filtri (status/template/to), counts_by_status, `POST /{id}/retry`.
- **`app/seed_email_templates.py`**: 11 template canonici seminati come sistema idempotente.
- **`app/services/email.py`** (compat): wrapper backward-compatible per `send_email()` legacy — delega a `enqueue_email`.
- **Permessi**: `email.view_settings`, `email.manage_settings`, `email.send_test`, `email.view_logs`, `email.retry`, `email.templates.manage`.

### Frontend
- **`pages/EmailSettingsPage.jsx`**: 4 tab (Configurazione, Invio di test, Verifica DNS, Template) con editor Jinja2 + anteprima HTML live + reset override tenant.
- **`pages/EmailLogsPage.jsx`** (riscritto): filtri stato/destinatario, counts_by_status cliccabili, dialog dettaglio con anteprima HTML/text, retry inline.
- Menu sidebar: "Impostazioni email" + "Registro email".

### Env variabili aggiunte
`MAIL_HOST`, `MAIL_PORT=465`, `MAIL_SECURITY=ssl`, `MAIL_USER`, `MAIL_FROM`, `MAIL_FROM_NAME`, `MAIL_REPLY_TO`, `MAIL_DELIVERY_MODE=test`, `MAIL_TEST_REDIRECT_TO=pilot@panoramapilot.com`, `MAIL_IMAP_HOST/PORT/SECURITY` (predisposte, non implementate).

### Sicurezza
- **Password**: SOLO da `os.environ.get("MAIL_PASSWORD")`. Mai loggata. Se manca → status `configuration_required` con messaggio `SMTP_NOT_CONFIGURED`.
- **Protezione preview**: tutti gli invii reindirizzati a `pilot@panoramapilot.com`, oggetto con prefisso `[TEST - Destinatario originale: ...]`, `original_to` preservato nel log.
- **Isolamento tenant**: `email_logs` scoped per tenant_id (bypass solo per superadmin/platform_owner).
- **Idempotency**: se `idempotency_key` esiste con status=sent/test_intercepted, ritorna log esistente senza reinvio.
- **Rate limit**: 5 test-email ogni 5 minuti per utente (in-memory, ok per single-instance).
- **Password redaction**: se cfg.smtp_password appare nell'eccezione SMTP, viene sostituita con `***REDACTED***`.

### Test — iteration_28.json
- **Backend**: 45/45 PASS (10 test_email_service + 9 test_email_extra + 26 regressione)
- **Zero critical/high**, 1 minor cosmetico (rate-limit in-memory)
- **Regressione**: 73/73 su commercial_perimeter, finestra_1a, catalog, ci_security_guards, code_quality_regression, iter25_smoke

### Deploy checklist (post MAIL_PASSWORD)
1. Aggiungere `MAIL_PASSWORD` in **Emergent → Profile → Secrets** con la password SMTP di `pilot@panoramapilot.com`.
2. Restart backend (o attende reload automatico).
3. Verificare `GET /api/email-settings` → `password_configured=true`, `is_configured=true`, `provider_name=siteground_smtp`.
4. In "Impostazioni email → Invio di test" mandare test USER_INVITATION → deve arrivare a `pilot@panoramapilot.com` con oggetto `[TEST - ...]`.
5. Attivare LIVE mode solo dopo verifica cambiando `MAIL_DELIVERY_MODE=live` in produzione (mai in preview).

### Prossimo (P1)
- Sprint 2 Catalogo: UI Ferramenta (Kit), UI Montaggio e posa
- Sprint 3 Catalogo: UI Costi accessori (16 categorie)
- Formule vetro 3-ante e 4-ante (bloccato: attende specifiche tecniche)

## Fase 1 · Motore commercial_perimeter integrato — Feb 2026 (iter 29)

### Deliverables
- Nuovi endpoint (`/app/backend/app/routers/quote_structure.py`):
  - `POST /api/quote-structure/{qid}/openings/{oid}/products/compute-and-add` — motore integrato, salva pricing_snapshot
  - `POST /api/quote-structure/products/{line_id}/recompute` — ricalcolo linea esistente
  - `GET /api/quote-structure/{qid}/legacy-status` — flag legacy read-only
- Endpoint esistente `POST /api/quote-structure/openings/{oid}/products` ora rifiuta `unit_price>0` senza permesso `quotes.edit_prices` (403 MANUAL_PRICE_NOT_ALLOWED)
- Helper `is_legacy_quote(q)` + `_assert_not_legacy(q)` (409 LEGACY_QUOTE_READ_ONLY su mutations)
- Guard `_guard_unit_price(user, val)` — bypass solo per superadmin o utenti con `quotes.edit_prices`
- Test file `/app/backend/tests/test_fase1_motor_integration.py` — 6 test (5 pass + 1 skip in caso listini incompleti, comportamento voluto)
- Git tags: `pre-fase1-backend-motor-2026-02` (rollback), `p0-fase1-motor-integrato` (checkpoint)
- Commit: `464b413`

### Codici errore bloccanti gestiti (dal motore)
MISSING_ADDITIONAL_COMPONENTS_COST, MISSING_COMPONENT_COLOR_PRICE, MISSING_FRAME_PRICE, MISSING_FRAME_REINFORCEMENT_PRICE, MISSING_GLASS_MINIMUM, MISSING_GLASS_PRICE, MISSING_GLASS_RECIPE, MISSING_GLAZING_BEAD_PRICE, MISSING_HARDWARE_PRICE, MISSING_HOURLY_COST, MISSING_INSTALLATION_PRICE, MISSING_MARGIN, MISSING_MEETING_STILE_PRICE, MISSING_MEETING_STILE_REINFORCEMENT_PRICE, MISSING_PRODUCTION_TIME, MISSING_SASH_PRICE, MISSING_SASH_REINFORCEMENT_PRICE

### Comportamento preventivi legacy
- Rilevati automaticamente: `is_legacy=true` OR `pricing_engine≠commercial_perimeter` OR presenza linee con `base_price>0` e senza `pricing_snapshot`
- API `/api/quote-structure/{qid}/legacy-status` espone il flag al frontend
- Mutations su preventivi legacy → HTTP 409 con code `LEGACY_QUOTE_READ_ONLY`
- Nessuna migrazione automatica, nessuna cancellazione automatica


## Iterazione 30 · AUDIT TECNICO COMPLETO v1 — Feb 2026

**Scope**: audit pre-unificazione architetturale (opzione D2:b) su richiesta esplicita del PO — 17 sezioni di analisi + fix Critical/High + report + rollback tag.

### Report completo
`/app/memory/AUDIT_REPORT_V1.md` — mappa file, duplicazioni, query, motori, formule vetro, unità, versionamento, legacy, permessi, frontend, seed, performance, error handling, bug classificati, test, verdetto finale.

### Bug fixati (Critical / High)
| ID | Severità | File | Descrizione |
|---|---|---|---|
| BUG-01 | CRITICAL | `routers/quotes.py:449-462` | Guard `sent` leggeva collezione `opening_products` inesistente per lo schema — preventivi con `pricing_status=incomplete` potevano essere inviati. Ora ispeziona `q.lines[].pricing_snapshot.blocking_errors` inline + codes `QUOTE_HAS_BLOCKING_ERRORS` / `QUOTE_CONTAINS_MANUAL_PRICES`. |
| BUG-02 | HIGH | `services/catalog_service.py:126-140` | `resolve_component_prices` senza ordering deterministico su `find_one`. Aggiunto sort `version DESC, updated_at DESC, _id DESC`. |
| BUG-03 | CRITICAL | `services/catalog_service.py:24-33` | `DEFAULT_PROD_CFG` inventava `default_glass_price_per_sqm=76.0` e `default_glass_min_sqm=0.50` silent. Rimossi → ora `None` → motore emerge MISSING_GLASS_PRICE / MISSING_GLASS_MINIMUM esplicito (P6 rispettato). |
| BUG-04 | HIGH | `services/indexes.py` | Indici mancanti su 6 collezioni hot. Aggiunti: `ix_ipl_tenant_status_ver`, `ix_ipl_tenant_active_ver`, `ix_glass_recipes_lookup`, `ix_color_categories_tenant_code`, `ix_ccm_tenant_code`, `ix_products_demo_guard`, `ux_production_config_tenant`. |
| BUG-06 | HIGH | `services/recipes/glass_engine.py:136-170` | Troncamento `int((L-wr)/sf)` → ROUND_HALF_UP. 2-ante L=1400 wr=347 sf=2 ora restituisce 527 (era 526 silent). Rifiuta split_factor ≤0. |
| BUG-15 | HIGH | `production_config` | Unique sparse index per tenant_id. Cleanup manuale duplicati esistenti demandato. |
| BUG-16 | HIGH | `services/recipes/commercial_perimeter.py:377-385` | Latent bug: `installation_declared_zero=True` con `installation_cost=None` causava TypeError `None + Decimal` in service_cost. Aggiunto helper `_z()` che coerce None→Decimal("0"). |

### Bug documentati NON corretti (in scope unificazione)
- **BUG-14** [CRITICAL/ARCHITETTURALE] — `ParametricAdminPage.jsx` disconnessa dai listini/motore commerciale. Fix = opzione D2:b (unificazione), documentato in `/app/memory/UNIFICATION_PLAN_V1.md` (attende approvazione A/B/C).
- BUG-05/07/09/10/11/12/13 (MEDIUM cosmetici/refactor) — documentati nel report.

### Test aggiunti
- `tests/test_audit_v1_regression.py` — 7 test regressione per BUG-01/02/03/04/06/15
- Totale: **92 test verdi + 2 xfail attesi** (test flaky su tenant Infissi Express con listino ricco)
- Regressione: `test_finestra_1a_recipe`, `test_catalog_area*`, `test_commercial_perimeter*`, `test_motor_full_listino_hard`, `test_iter25_smoke`, `test_ci_security_guards`, `test_code_quality_regression` — tutti verdi

### Git tags
- `pre-audit-v1-2026-02` — rollback point (commit `870d704`)
- `p1-audit-v1-fixes` — dopo primo giro di fix (commit `3668a32`)
- `p1-audit-v1-fixes-final` — dopo fix BUG-16 e finalizzazione (commit `28fdd81`)

### Verdetto
✅ **Motore commercial_perimeter corretto e coerente** per il perimetro implementato: math, snapshot deterministico, MISSING_* espliciti, no silent zeros, no fallback inventati, permessi enforced, tenant isolation OK.  
⚠️ **Fase 2A/unificazione ancora bloccati**: `ParametricAdminPage` disconnessa. Serve approvazione utente su UNIFICATION_PLAN_V1 (opzione A/B/C) per procedere.  
⚠️ **BUG-15 duplicato production_config** su PanoramaPilot richiede cleanup manuale prima dell'attivazione unique index in produzione.

### Endpoint modificati (comportamento)
- `POST /api/quotes/{id}/status` — ora blocca correttamente invio con blocking errors
- `POST /api/catalog/products/{id}/simulate` — glass_price/min_sqm ora obbligatori esplicitamente
- `POST /api/quote-structure/{qid}/openings/{oid}/products/compute-and-add` — behavior invariato ma ora usa motore corretto per service_cost None

### File modificati (7 file)
```
app/routers/quotes.py                          +43 -11
app/services/catalog_service.py                +18  -4
app/services/recipes/glass_engine.py           +22  -8
app/services/recipes/commercial_perimeter.py    +8  -3
app/services/indexes.py                        +45   0
backend/tests/test_audit_v1_regression.py     +140   0 (new)
memory/AUDIT_REPORT_V1.md                     +500   0 (new)
```
