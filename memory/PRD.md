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
