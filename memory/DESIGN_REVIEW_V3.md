# Panorama Pilot — DESIGN REVIEW V3 (completa, 4 livelli)
**Data**: Feb 2026 · Iter 34  
**Autore**: agent, review autonomo  
**Ambito**: revisione critica del prodotto come se dovesse essere distribuito a centinaia di aziende  
**Metodologia**: brutale onestà, no difesa retroattiva delle scelte. Evidence-based dai 3 audit precedenti (V1 fix Critical/High, V1 plugins, V3 architettura).  
**Rispetto vincoli**: zero implementazione, zero modifica codice.  
**Destinatario finale**: da sottoporre a un secondo modello indipendente per cross-validation.

---

## SOMMARIO ESECUTIVO (per lettore rapido)

**Verdetto**: Panorama Pilot è un ERP **funzionalmente ricco ma architetturalmente frammentato**. Ha 57 router backend, 53 pagine frontend, ~200 collezioni MongoDB, **7+ librerie installate mai usate**, **4 SDK AI mai attivate**, **2 fonti autorevoli di dati tecnici in conflitto** (Sistema A commerciale + Sistema B parametric), **2 wizard preventivo separati** (`QuoteStructurePage` + `QuoteEditorPage`) e **1 pagina admin critica non funzionante** (`ParametricAdminPage` read-only).

**Punti di forza reali**: motore commerciale (`commercial_perimeter`) matematicamente corretto e testato; snapshot deterministico con hash; multi-tenant isolation forte; ricco set di modelli Pydantic; test suite 96+ verdi.

**Lacune bloccanti per scalare**: nessun scheduler, nessun monitoring (Sentry assente), nessuna fatturazione elettronica SDI (obbligo legale IT), nessun WhatsApp Business, nessuna UI per configurare il preventivatore, terminologia `margin_pct` ambigua (è markup, non margine).

**Priorità reale ora**: **non aggiungere niente**. Consolidare Sistema B come fonte autorevole (V3), rimuovere le duplicazioni, attivare Sentry + Fatturazione Elettronica + WhatsApp, poi frontend rewrite.

---

## LIVELLO 1 — ANALISI DEL PRODOTTO

### 1.1 · Classificazione moduli (57 router + 53 pagine → 22 aree funzionali)

| Area funzionale | Router/pagina | Serve? | Intuitivo? | Ridondante? | Doppio dato? | Classificazione |
|---|---|---|---|---|---|---|
| **Auth + Ruoli** | `auth`, `users`, `roles`, `sessions`, `accept-invitation`, `forgot/reset-password`, `change-password` | Sì (obbligatorio) | Sì | No | No | **ESSENZIALE** |
| **CRM Lead→Cliente** | `leads`, `contacts`, `customers`, `activities`, `pipelines`, `tasks`, `sequences` | Sì | Parziale (troppi step) | Sì (leads vs contacts sovrapposti) | Sì | **ESSENZIALE** ma **DA CONSOLIDARE** |
| **Preventivatore v1 (legacy)** | `QuoteEditorPage.jsx`, `QuoteStructurePage.jsx`, `QuotesPage.jsx`, router `quotes`, `quote_structure` | Sì | **NO** (2 editor paralleli) | Sì (doppio wizard) | Sì | **DA RIFARE** (uno solo) |
| **Motore tecnico / parametric** | `parametric` router, `ParametricConfiguratorPage`, `ParametricAdminPage` | Sì (secondo V3) | **NO** (admin read-only) | Sì | Sì | **DA RIFARE** (V3 direzione) |
| **Catalogo prodotti** | `catalog`, `product_catalog`, `ProductCatalogPage`, `ProductSimulatorPage`, `PricingHubPage`, `PricelistsPage`, `PricelistImporterPage` | Sì | **NO** (5 pagine sovrapposte) | Sì | Sì | **DA CONSOLIDARE** (Sistema B unico) |
| **Sopralluogo + Rilievo** | `SiteConditionsForm`, `surveys`, `TechnicalSchedulesPage`, `geometry` | Sì | Sì | No | No | **IMPORTANTE** |
| **Contratti + Firma** | `contracts`, `ContractsPage`, `ContractViewerPage`, `signatures` | Sì | Sì (ma firma primitiva) | No | No | **ESSENZIALE** — firma DA RIFARE (audit v1) |
| **Produzione** | `production`, `logistics`, `qc`, `ops_workflow` | Sì | Parziale (lista taglio scollegata) | No | Sì (con motore parametric) | **IMPORTANTE** — DA COLLEGARE |
| **Assistenza / Service tickets** | `service_tickets`, `NotificationsPage` | Sì | Sì | No | No | **IMPORTANTE** |
| **Fatturazione / Sales** | `sales`, `sales_orders`, `admin_finance`, `treasury`, `TreasuryCFOPage`, `management_control` | Sì (per IT: SDI obbligatorio) | Parziale | Sì (treasury vs finance vs management overlap) | Sì | **DA RIFARE** (integrare SDI) |
| **BI/Dashboard** | `bi`, `dashboards_crm`, `dashboard`, `Dashboard.jsx`, `AiCfo` | Sì | Parziale | Sì (3+ dashboard) | No | **DA CONSOLIDARE** |
| **CFO AI** | `ai_cfo` | ? | ? | ? | ? | **LEGACY** — non usato in produzione (grep 0 attivazione LLM) |
| **Inventory / Purchasing** | `inventory`, `purchasing`, `intercompany` | Forse | Non verificato uso | ? | ? | **ACCESSORIO** — verificare adoption |
| **Multi-company / Legal entities** | `company`, `legal_entities`, `LegalEntitiesPage`, `intercompany` | Sì per gruppi | Sì | No | No | **IMPORTANTE** solo target enterprise |
| **Landing + Marketing** | `landing`, `LandingPage`, `saas_platform`, `SaaSPlatformPage`, `PlatformSiteConfigPage` | Sì (per SaaS pubblico) | Parziale | Sì (3 pagine marketing) | No | **ACCESSORIO** — DA CONSOLIDARE |
| **Attachments / File storage** | `attachments`, `AttachmentsPage` | Sì | Sì | No | No | **ESSENZIALE** |
| **Email** | `email_settings`, `email_logs`, `EmailSettingsPage`, `EmailLogsPage` | Sì (SMTP configurato) | Sì | No | No | **ESSENZIALE** |
| **Calendario / Appointments** | `appointments`, `CalendarPage`, `PublicSchedulePage` | Sì | Sì | No | No | **IMPORTANTE** |
| **Audit / Logging** | `audit`, `AuditPage` | Sì | Basic | No | No | **IMPORTANTE** — da estendere |
| **Ricerca globale** | `search`, `SearchPage` | Sì | **NO** (non instant) | No | No | **DA RIFARE** (cmdk + backend parallelo) |
| **Templates / Clauses** | `TemplatesPage`, `ClausesPage`, `sequences` | Sì per contratti | Sì | Sì (3 gestori template) | Sì | **DA CONSOLIDARE** |
| **WhatsApp** | `WhatsAppLogsPage` | Solo log, no integrazione attiva | — | — | — | **LEGACY** (grep 0 uso, va attivato) |
| **Debug / Health** | `debug`, `dashboard` | Solo dev | — | — | — | **ACCESSORIO** |
| **Onboarding wizard** | `OnboardingWizard`, `onboarding` router | Sì | Genericissimo | No | No | **DA RIFARE** |
| **Landing customer pages** | `public`, `PublicQuotePage`, `PublicSchedulePage` | Sì | Sì | No | No | **ESSENZIALE** |
| **Goals** | `GoalsPage` | ? | Non chiaro uso | ? | ? | **DA VERIFICARE ADOPTION** |
| **Sequences** | `SequencesPage`, `sequences` router | Marketing automation | Non usato in prod | No | No | **LEGACY** o **DA RIFARE** |
| **Chat interna** | `ChatPage` (?) | ? | ? | ? | ? | **DA VERIFICARE** |

### 1.2 · Verdetto Livello 1

**Su ~28 aree**:
- **ESSENZIALI** (7): auth, CRM, contratti, catalog, sopralluogo, attachments, email, public pages
- **DA CONSOLIDARE** (8): preventivatore, catalogo, template, dashboards, marketing pages, treasury/finance, CRM lead/contacts, ricerca
- **DA RIFARE** (5): parametric admin, firma, fatturazione (SDI), search, onboarding
- **LEGACY / DA VERIFICARE ADOPTION** (5): ai_cfo, WhatsAppLogs, goals, sequences, chat
- **ACCESSORI** (3): multi-company, purchasing/inventory, debug

**Problema chiave del prodotto**: **troppa dispersione**. Un titolare di 5 dipendenti si perde tra QuoteStructurePage, QuoteEditorPage, ParametricConfiguratorPage, PricingHubPage, PricelistsPage, ProductCatalogPage — sono **6 pagine per fare la stessa cosa**: preparare un preventivo.

---

## LIVELLO 2 — ANALISI ARCHITETTURALE

### 2.1 · Violazioni rilevate

| Principio | Violazione | Evidenza | Severità |
|---|---|---|---|
| **Single Source of Truth** | Due fonti autorevoli (Sistema A vs Sistema B) per componenti/formule/listini | Audit V3 §7 | 🔴 CRITICAL |
| **DRY** | `products.components[].waste_percentage` vs `bom_templates.components[].waste_pct` | V3 mapping §4 | 🟠 HIGH |
| **DRY** | Formule perimetro cablate in `commercial_perimeter.py` + formule libere in `bom_templates` | V3 §7 | 🔴 CRITICAL |
| **DRY** | 3 pagine treasury/finance/management_control con KPI sovrapposti | Livello 1 | 🟡 MEDIUM |
| **DDD** | Livello commerciale legge da collezioni tecniche (products.components) — mixa domini | V3 principio guida | 🔴 CRITICAL |
| **SOLID SRP** | `commercial_perimeter.compute_perimeter` fa: geometria + lookup prezzi + calcolo costo materiali + labor + servizi + markup + tassa. 8 responsabilità in una funzione. | commercial_perimeter.py:220-470 | 🟠 HIGH |
| **SOLID OCP** | Aggiungere un nuovo tipo di infisso (portoncino) richiede modifica hard-coded di `commercial_perimeter._compute_perimeters` invece di plug-in formula | commercial_perimeter.py | 🟠 HIGH |
| **SOLID ISP** | `PerimeterInput` dataclass ha 40+ campi opzionali — chi crea l'input deve conoscerli tutti | commercial_perimeter.py:48-110 | 🟡 MEDIUM |
| **Servizi troppo grandi** | `perimeter_assembler.build_perimeter_input` (150 righe, 15 chiamate DB, 8 rami condizionali) | perimeter_assembler.py | 🟠 HIGH |
| **Servizi troppo grandi** | `parametric_engine.resolve_bom` (280 righe, 30+ variabili locali, 12 rami condizionali) | parametric_engine.py:111-396 | 🟠 HIGH |
| **Codice morto** | `parametric_snapshots` collection scritta ma mai riletta | V3 §11 ARCH-07 | 🟡 MEDIUM |
| **Codice morto** | `price_matrices` collection e Modalità A pricing legacy | V3 §11 ARCH-09 | 🟡 MEDIUM |
| **Codice morto** | `bar_optimization_runs` collection audit ma mai consultata da UI | grep 0 UI usage | 🟢 LOW |
| **Dipendenze circolari** | Nessuna rilevata a livello di import (verificato con `grep -R import`) | — | ✅ OK |
| **Accoppiamento** | `perimeter_assembler` importa 5 servizi diretti — hard-coded dipendenze | perimeter_assembler.py:13-21 | 🟡 MEDIUM |
| **Terminologia ambigua** | `margin_pct` implementa markup-on-cost ma nome suggerisce gross_margin | audit v1 sez 20 | 🟠 HIGH |
| **Snapshot design** | `pricing_snapshot` monolitico (technical+commercial mescolati) → cambio moltiplicatore invalida hash anche se il costo è invariato | quote.lines[].pricing_snapshot | 🟠 HIGH — V3 lo risolve con doppio snapshot |

### 2.2 · Fonti autorevoli — stato attuale

Vedi V3 §1 dettagliato. Riepilogo: **NO single source of truth**. Due sistemi paralleli (A catalog + B parametric) condividono parzialmente `item_pricelists` con schemi diversi. Documentato in `ARCHITECTURAL_AUDIT_V3.md`.

### 2.3 · Estensibilità

- **Nuovo tipo prodotto (portoncino, scorrevole)** → richiede: nuova recipe cablata in `commercial_perimeter.py` + nuova BOM template + nuova entry in `catalog_code_mappings`. **3 punti di modifica invece di 1**.
- **Nuovo pricing method (leasing con rata)** → non supportato senza refactor.
- **Nuovo tenant con listini in valuta diversa** → `item_pricelists.currency` esiste ma non testato end-to-end.
- **API pubblica per partner** → assente (nessun `/api/public/v1/*` versioned).

---

## LIVELLO 3 — ANALISI UX PER RUOLO

### 3.1 · Commerciale (venditore)

**Flusso realistico**: entrare in showroom → creare lead → agendare sopralluogo → generare preventivo → mandare al cliente → firmarlo.

| Fase | Schermate attraversate | Click stimati | Dati re-inseriti | Punti critici |
|---|---|---|---|---|
| Lead da telefonata | LeadsPage → nuovo lead form | 8-12 | Nome, tel, email, note | Non c'è quick-capture, form troppo lungo |
| Trasformare in cliente | LeadDetailPage → converti | 3-5 | Zero (bene) | OK |
| Agendare sopralluogo | CalendarPage → nuovo appuntamento | 6-8 | Ripete indirizzo (già in lead) | **DOPPIO INSERIMENTO** |
| Fare preventivo | QuoteStructurePage OPPURE QuoteEditorPage OPPURE ProductSimulatorPage | 20-40 | Tanti (misure, colore, tipologia per ogni finestra) | **PAGINE MULTIPLE PARALLELE — CONFUSIONE** |
| Mandare PDF cliente | Da QuotesPage → download PDF | 3 | Zero | OK |
| Firma | PublicQuotePage (URL cliente) | 2-3 | Zero cliente-side | **Firma pad primitiva** (audit v1 lo denuncia) |

**Verdetto commerciale**: 45-70 click totali per un preventivo semplice. Un competitor tipo Preventivi.it lo fa in 15-20. **Troppo dispersivo**.

### 3.2 · Responsabile produzione

**Flusso**: ricevere ordine confermato → generare lista taglio → assegnare a macchine.

**Verdetto**: **flusso interrotto**. `commercial_perimeter` calcola prezzi ma non produce cutting list. Il motore `parametric_engine` produce cutting list ma legge da collezioni **scollegate** dal preventivo. → responsabile produzione **ricompila i dati manualmente**.

### 3.3 · Tecnico rilievo

**Flusso**: sopralluogo in casa → misurare → foto → aggiornare preventivo.

- `SiteConditionsForm` esiste
- `TechnicalSchedulesPage` esiste
- Ma **nessuna app mobile-first**, nessun offline mode, nessun voice-to-text sulle note
- Nessun scanner QR per identificare velocemente un ordine

**Verdetto**: **incompleto** per uso di campo.

### 3.4 · Amministrazione

**Flusso**: emettere fatture → riscuotere → gestire IVA.

- Nessuna integrazione SDI/Fatturazione Elettronica → **usa un altro software** per fatturare → doppio inserimento
- Nessun tracking pagamenti automatico (bancario)
- Treasury/finance/management_control 3 pagine sovrapposte

**Verdetto**: **inutilizzabile per fatturazione IT** senza SDI.

### 3.5 · Installatore (posatore)

**Flusso**: prendere in carico l'ordine → posa → firma consegna.

- Nessuna app mobile
- Nessun checklist collaudo (o solo generico in `qc`)
- Firma cliente per consegna → **non esiste** (esiste solo per contratto)

**Verdetto**: **non coperto**.

### 3.6 · Titolare / Amministratore

**Flusso**: vedere KPI, configurare listini, gestire team.

- Dashboard KPI: 3 pagine sovrapposte
- Configurare listini: `PricelistsPage` + `PricingHubPage` + `PricelistImporterPage` + `ParametricAdminPage` (read-only!) = **4 pagine per un compito**
- Team: `UsersPage` + `RolesPage` OK

**Verdetto**: **titolare confuso** — non sa quale pagina usare.

---

## LIVELLO 4 — ANALISI MODELLO DATI

### 4.1 · Entità per proprietà, congelamento, versionamento

| Entità | Owner | Chi legge | Congelata quando? | Versionata? | Problemi |
|---|---|---|---|---|---|
| `profile_systems` | Admin tecnico | Motori | Su publish (`ps_status=active`) | Sì (`version` field) | Non usato dal motore commerciale |
| `profiles` | Admin tecnico | Motore tecnico | No congelamento | No | Duplicazione con `products.components[]` |
| `bom_templates` | Admin tecnico | Motore tecnico | Su publish | Sì | Non usato dal motore commerciale |
| `item_pricelists` | Admin | Entrambi motori | Su publish | Sì | Schema dual |
| `glass_recipes` | Admin | Motore commerciale | Su publish (`status=active`) | No versione | Nessuna UI per gestirle |
| `production_config` | Admin | Motore commerciale | No | No | Duplicato per PanoramaPilot |
| `products` | Admin catalog | Motore commerciale | Su lifecycle | Sì | Duplicazione tecnica |
| `quotes` | Commerciale | Ovunque | Su `sent`/`signed` | No versione, snapshot lines | OK ma snapshot monolitico |
| `contracts` | Sistema | ContractViewer | Su `signed` | Sì (variations) | OK |
| `quote.lines[].pricing_snapshot` | Motore | Contratti | Alla creazione line | No | Snapshot mescolato (tech+commercial) |

**Nessun caso ha "una sola fonte autorevole" per il dominio "prezzo del componente 5103 in bianco"**.

### 4.2 · Cardinali su DB PanoramaPilot

```
profile_systems: 1        (seed)
profiles: 7               (seed)
item_pricelists: 3
products: 11
glass_recipes: 6
production_config: 2      ← BUG-15 duplicato
color_categories: 4
catalog_code_mappings: 4
bom_templates: 16
quotes: 355               ← dato reale operativo
```

I 355 quotes reali sono la **prova che il sistema funziona**, ma stanno tutti sul motore commerciale (Sistema A). Il Sistema B è dormiente eccetto seed.

---

## ANALISI FLUSSO AZIENDALE

```
Lead                          → leads (dato creato)
  ↓
Cliente                       → customers (ereditato: nome/tel/email/indirizzo, congelato al primo save)
  ↓
Sopralluogo                   → appointments + surveys + site_conditions (ereditato: cliente; dato creato: misure)
  ↓
Preventivo                    → quotes + quote_lines[] (ereditato: cliente, misure; dato creato: linee, snapshot)
  ↓ (invio + accettazione)
Contratto                     → contracts (ereditato: quote.pricing_snapshot COPIA IMMUTABILE)
  ↓
Rilievo definitivo            → surveys aggiornate (dato modificato: misure post-firma → RIVEDI PREVENTIVO?)
  ↓
Produzione                    → production_orders + cutting_lists (ereditato: bom da RE-CALCOLARE — flusso interrotto!)
  ↓
Lista di taglio               → cutting_lists (dato creato duplicato: qty componenti già in bom_templates)
  ↓
Magazzino                     → inventory (dato creato)
  ↓
Posa                          → NON COPERTO (nessuna app posatore)
  ↓
Collaudo                      → qc parziale
  ↓
Assistenza                    → service_tickets
```

**PROBLEMI**:
1. Rilievo definitivo può cambiare misure → il preventivo/contratto va aggiornato con nuovo snapshot **con variation** (già supportato via `create_variation` — OK)
2. **Passaggio Contratto → Produzione**: il contratto ha `pricing_snapshot` immutabile ma la produzione **rifà i calcoli tecnici** perché il motore tecnico legge da collezioni diverse. → **rischio disallineamento**
3. **Posa non tracciata**
4. **Assistenza non collegata al contratto originale** (verificare)

---

## ANALISI PREVENTIVATORE

**Il preventivatore è il cuore?** In teoria sì. In pratica: **è frammentato in 3 pagine**:
- `QuoteEditorPage.jsx` (legacy manual price)
- `QuoteStructurePage.jsx` (nuovo wizard 5-step con envs+openings)
- `ProductSimulatorPage.jsx` (simulate singolo prodotto)

**Passaggi inutili**:
- Wizard 5-step chiede dati che spesso sono già noti (colore, tipologia default per ambiente)
- Serve **1 preventivatore mobile-first** che copra 90% dei casi in 3 step

**Snapshot design**: monolitico, va splittato in `technical_snapshot + commercial_snapshot` (V3 §8).

**PDF**: WeasyPrint funziona ma template semplice. Nessun preview inline (viewer PDF assente).

---

## ANALISI MOTORI TECNICO E COMMERCIALE

### Motore tecnico (`parametric_engine`)
- Formule via parser AST sicuro ✅
- Nesting FFD/BFD implementato ✅
- Sfrido/waste/bar_rounding OK ✅
- **Problema**: non produce output riutilizzato dal preventivo commerciale
- **Costo ricostruibile**: sì, se BOM template completa. Ma **oggi le BOM sono seed** — non ci sono BOM utente reali

### Motore commerciale (`commercial_perimeter`)
- Formule cablate spec-approvate (ext_perimeter = 2*(L+H), sash_perim = ext + 2H*(n-1)) ✅
- Doppio precision Decimal ✅
- Snapshot hash deterministico ✅
- **Problema**: **calcola il costo tecnico ex-novo** (perimetro × prezzo × sfrido) invece di riceverlo dal motore tecnico
- **Il prezzo deriva SEMPRE dal costo tecnico?** → **NO** oggi. Deriva dal calcolo del motore commerciale che ricostruisce autonomamente il costo. V3 lo risolve invertendo la dipendenza.

**Markup/moltiplicatore/margine**: chiamati tutti generic-amente `margin_pct` con semantica markup-on-cost. Ambiguo (audit v1 sez 20).

---

## ANALISI SCHERMATE (53 pagine — top-line)

| Pagina | Verdetto | Azione |
|---|---|---|
| `Dashboard.jsx`, `Dashboard` (dashboards_crm), `TreasuryCFOPage` | 3 dashboard sovrapposti | **UNIRE** in 1 con tab |
| `PricelistsPage` + `PricingHubPage` + `PricelistImporterPage` + `ParametricAdminPage` | 4 pagine gestione prezzi | **RIFARE COME 1** (V3 §9) |
| `QuoteEditorPage` + `QuoteStructurePage` | 2 editor preventivo | **UNIRE** (eliminare QuoteEditorPage) |
| `ProductCatalogPage` + `ProductSimulatorPage` | 2 pagine catalogo | **UNIRE** |
| `LandingPage` + `SaaSPlatformPage` + `PlatformSiteConfigPage` | 3 pagine marketing | **UNIRE / SEMPLIFICARE** |
| `ParametricConfiguratorPage` vs `QuoteStructurePage` | Configuratore parallelo | **ELIMINARE** ParametricConfiguratorPage |
| `SearchPage` | Non è instant search | **RIPROGETTARE** (cmdk + backend parallelo) |
| `OnboardingWizard` | Troppo generico | **RIFARE** con tour joyride |
| `GoalsPage` | Non chiaro uso | **VERIFICARE ADOPTION** — se 0 usi, eliminare |
| `SequencesPage`, `WhatsAppLogsPage` | Legacy | **ATTIVARE** (WhatsApp) o eliminare |
| `AuditPage` | Utile ma basic | **ESTENDERE** con filtri avanzati |
| Tutte le altre | OK come baseline | Mantenere |

**Numero pagine ottimale post-refactor**: ~35 (da 53) → riduzione 34%.

---

## ANALISI DATABASE

### Duplicazioni / candidate elimination

| Collezione | Verdetto |
|---|---|
| `parametric_snapshots` | **ELIMINABILE** — scritti mai riletti |
| `bar_optimization_runs` | ELIMINABILE audit-only (o mantenere solo per debug) |
| `price_matrices` + `pricing_mode_configs` | **ELIMINABILI** in Modalità B/C definitiva |
| `colors` | Ridurre a lookup UI |
| `bom_templates level=commercial` | Deprecare — solo `level=production` |
| Legacy `pricelists` (vecchia collezione pre-item_pricelists) | Verificare uso, probabilmente ELIMINABILE |

### Indici mancanti
Vedi audit V1 BUG-04 — 6 collezioni hot senza indici. Fix già applicato.

### Versionamento
- OK per `profile_systems`, `bom_templates`, `item_pricelists`, `products`
- Assente per `glass_recipes`, `production_config`, `color_categories`

### Snapshot
- Presente su `quotes.lines[].pricing_snapshot` — ma monolitico (vedi V3 §8)

### Performance
- 355 quotes su tenant PanoramaPilot → NO problem
- A 100k quotes → cursor.sort su indici già preparati OK
- A 1M quotes → serve archiviazione quotes chiuse in collezione separata

---

## ANALISI API

**57 router**. Sample verifica:

| Endpoint | Nome REST corretto? | Duplicato? | Tenant isolated? | Permessi? |
|---|---|---|---|---|
| `POST /api/quote-structure/{qid}/openings/{oid}/products/compute-and-add` | Troppo lungo | No | ✅ | ✅ |
| `POST /api/parametric/preview` | OK | No | ✅ | ✅ (implicit via user) |
| `GET /api/catalog/products` | OK | No (ma `/api/product-catalog/*` fa cose simili) | ✅ | ✅ |
| `GET /api/parametric/profile-systems` | OK | No | ✅ | ✅ |
| `POST /api/quotes/{id}/status` | OK | No | ✅ | ✅ |

**Problemi generali**:
- **Nessuna versione API** (`/api/v1/` vs `/api/v2/`) → migrazioni future rompono client
- **Nessuna specifica OpenAPI curata** (FastAPI genera auto, ma non validata dal team)
- **Nessun rate-limit su endpoint pubblici** oltre auth
- **Coerenza naming**: `/api/catalog` vs `/api/product-catalog` vs `/api/products` (via product_catalog router) — 3 root per gestire prodotti

---

## ANALISI FRONTEND

- **Componenti riutilizzabili**: Radix UI 30+ primitive OK. Ma le pagine spesso duplicano forms invece di usare abstractions
- **Stato globale**: React Query 5 (28 file). ✅ **swr installato ma inutilizzato** — RIMUOVERE
- **Stato locale**: `useState`/`useReducer` diffusi. Nessun state management server centralizzato oltre react-query
- **Routing**: react-router 7 OK
- **Performance**: nessun lazy loading verificato; bundle contiene ~500kb di librerie mai usate (`framer-motion`, `swr`, `dayjs`, `lodash`)
- **Error boundary**: assente a livello globale (ogni pagina catch localmente)
- **Loading states**: incoerenti (Skeleton vs Spinner vs "Caricamento..." plaintext)
- **Debounce**: presente in alcune search bar, assente in altre
- **Cache**: React Query gestisce la maggior parte; ma no persist across reload
- **UX**: mobile responsive parziale — molte tabelle rompono su smartphone

---

## ANALISI BACKEND

- **Servizi**: 25+ file in `app/services/` — misto tra logica core (`commercial_perimeter`, `parametric_engine`) e helper (`ops_common`, `formula`)
- **Repository**: **assente pattern esplicito** — la maggior parte dei router chiama direttamente `db.collection.find(...)` invece di passare per repository
- **Modelli**: Pydantic v2 molto ricco (25+ file `models_*.py`). Buon uso di `BaseDoc`
- **Test**: 96 pass + xfail documentati. Copertura motore commerciale eccellente, motore tecnico moderata, router endpoint parziale
- **Validazioni**: `require_permission` diffuso ✅. Ma alcune mutation permettono override senza check (audit v1)
- **Logging**: Python `logging` standard. Nessun structured JSON, nessun correlation ID request-scoped
- **Eventi**: **nessun event bus**. Ogni cambio di stato è chiamata sincrona → difficile aggiungere webhook / notifiche async
- **Error handling**: `HTTPException` con `detail={code, message, ...}` — OK

---

## ANALISI PRODUZIONE

**Domanda cardine**: *il sistema permette di produrre un serramento senza informazioni mancanti?*

**Risposta**: **NO**.

Problemi:
1. La cutting list generata dal motore parametric usa `bom_templates.components[]` che nessuno popola realmente (solo seed)
2. Il preventivo commerciale non produce cutting list
3. → **il produttore deve reinserire manualmente i dati** oppure fidarsi delle cutting list generate da BOM seed
4. Non c'è un "handoff" formalizzato: contratto firmato → ordine produzione → cutting list → magazzino

**Manca**: `ProductionOrder` come entità di stato "ricevuto da preventivo, in coda produzione" con collegamento diretto sia al contratto sia alla cutting list generata deterministicamente.

---

## ANALISI SCALABILITÀ

| Scala | Colli di bottiglia | Limiti |
|---|---|---|
| **100 aziende** | Nessuno oggi (già passato con PanoramaPilot su 355 quotes). Motor async + indici OK | ✅ Nessun problema |
| **1.000 aziende** | 1) MongoDB single-node → serve replica set. 2) Bundle frontend pesante → mobile lento. 3) Assenza cache Redis per lookup catalog → query ripetute. 4) Nessun rate-limit granulare tenant-scoped | 🟠 Serve refactor performance |
| **10.000 aziende** | 1) `quotes` collection cresce senza archiviazione. 2) `item_pricelists.entries[]` inline può superare 16MB doc limit. 3) Manca sharding key strategy. 4) Manca CDN per assets frontend. 5) Nessun APM per capire dove ottimizzare | 🔴 Serve refactor architetturale profondo |

**Per raggiungere 10k aziende serve**:
- Sharding MongoDB per `tenant_id`
- Redis cache aggressiva
- Archiviazione quotes/contracts chiusi in tier storage
- CDN Cloudflare/Fastly
- APM (Sentry Performance / DataDog / New Relic)
- Rate-limit per tenant
- Job queue (arq/celery) per operazioni async
- Read replicas per BI dashboard

---

## OUTPUT — deliverable strutturato

### 1. Punti di forza

1. **Motore commerciale matematicamente corretto** — 96 test verdi, snapshot hash deterministico, precisione Decimal
2. **Multi-tenant isolation forte** — ogni endpoint filtra su `tenant_id`
3. **Pydantic v2 modelling ricco** — 25+ file `models_*.py` ben tipizzati
4. **Parser AST sicuro (no eval)** — proteggerà da injection quando le formule saranno esposte agli utenti
5. **Auth solido** — JWT + bcrypt + audit trail eventi
6. **Radix UI + shadcn** — base UI moderna, accessibile
7. **Test infrastructure OK** — pytest + pytest-xdist, coverage crescente
8. **Emergent integrations disponibili** — Universal LLM Key già presente in requirements, mai sfruttata
9. **Snapshot design** — concetto di immutabilità presente (anche se monolitico)
10. **355 quotes reali su PanoramaPilot** — il prodotto **funziona in produzione** oggi

### 2. Lacune progettuali

1. **Due fonti autorevoli** per dati tecnici — non risolto (V3 direzione)
2. **Snapshot monolitico** — tech+commercial mescolati
3. **Preventivatore frammentato** in 3+ pagine
4. **Terminologia margin/markup ambigua** in codice + UI
5. **Nessuno scheduler** → tutti i job cron mancano (reminder, cleanup, follow-up)
6. **Nessun monitoring** → errori 500 invisibili (BUG-16 latente scoperto solo per fortuna)
7. **Nessuna Fatturazione Elettronica SDI** → **bloccante commerciale in Italia**
8. **Nessun WhatsApp Business** → canale principale settore serramenti assente
9. **Firma canvas primitiva** — non touch-first, no audit trail robusto (IP/UA/hash)
10. **ParametricAdminPage read-only** — admin non può configurare il preventivatore
11. **Ricerca globale non instant** — SearchPage lenta e disconnessa
12. **Nessun onboarding utile** — nuovo utente perso in 53 pagine
13. **500kb di deps frontend mai usate** — `swr`, `framer-motion`, `dayjs`, `lodash`
14. **4 SDK AI mai attivati** — spreco assoluto
15. **Nessuna produzione end-to-end** — handoff contratto → produzione manuale
16. **Nessun offline / mobile posatore** — flusso posa/collaudo scoperto
17. **Nessuna API versionata** — cambi rompono i client
18. **Terminologia collections incoerente** — `products` vs `product_catalog` vs `catalog_*`

### 3. Bug architetturali

Vedi V3 §11:
- **ARCH-01 CRITICAL**: due fonti autorevoli tecniche
- **ARCH-02 CRITICAL**: `item_pricelists.entries[]` schema dual
- **ARCH-03 CRITICAL**: ParametricAdminPage scollegata
- **ARCH-04 HIGH**: valori tecnici duplicati (bar_length, kerf) profile_systems vs production_config
- **ARCH-05 HIGH**: sfrido duplicato
- **ARCH-06 HIGH**: nessuna FK products.components[].code ↔ profiles.code
- **ARCH-07 HIGH**: parametric_snapshots orfana
- **ARCH-08 MEDIUM**: colors solo lookup UI
- **ARCH-09 MEDIUM**: price_matrices legacy
- **ARCH-10 MEDIUM**: pricing_mode_configs vs production_config sovrapposti
- **ARCH-11 MEDIUM**: nessuna UI per glass_recipes
- **BUG-15 HIGH**: production_config duplicato PanoramaPilot (script pronto)

### 4. Ridondanze

- 3 dashboard KPI
- 4 pagine gestione prezzi
- 3 pagine catalogo prodotti
- 2 editor preventivo
- 2 sistemi componenti
- 2 formule perimetro (cablate vs BOM)
- Dual icon library (phosphor + lucide)
- Dual date library (date-fns + dayjs)
- Dual server state (react-query + swr)

### 5. Moduli da ELIMINARE

- `parametric_snapshots` (orfano)
- `bar_optimization_runs` (opzionale — solo audit dev)
- `price_matrices` (Modalità A legacy)
- `pricing_mode_configs` (post consolidamento)
- `QuoteEditorPage.jsx` (legacy manual price)
- `ParametricConfiguratorPage.jsx` (duplicato di QuoteStructurePage)
- Deps: `swr`, `framer-motion`, `dayjs`, `lodash`, `pymupdf` (se non usato), duplicati risoluzioni yarn
- `AI CFO` router **solo se non attivato** (verificare adoption)

### 6. Moduli da RIFARE

- **Preventivatore unico** (mobile-first, 3-step) — sostituisce QuoteStructurePage/QuoteEditorPage/ProductSimulatorPage
- **Sistemi profilo e formule** (V3 §9) — 9 tab admin tecnico → Sistema B come fonte
- **Firma pad** — react-signature-canvas + audit trail (IP, UA, hash)
- **Search globale** — cmdk + backend parallelo con instant results
- **Onboarding** — react-joyride con tour role-based
- **Dashboard** — 1 pagina con tab per ruolo
- **Contratti** — separare `technical_snapshot` + `commercial_snapshot` (V3 §8)
- **Fatturazione** — SDI via Aruba/Fatture in Cloud
- **Notifiche real-time** — SSE (Server-Sent Events)
- **Motore commerciale** — refactor per usare `TechnicalCostResolver` (V3)

### 7. Moduli da MANTENERE

- Auth + Users + Roles + Sessions
- Contracts (design OK, richiede doppio snapshot)
- CRM leads/contacts/customers/pipelines/tasks
- Surveys / SiteConditions / TechnicalSchedules
- Appointments / Calendar
- Attachments / Object storage
- Email + Templates
- Audit trail
- BI aggregations backend (dashboards frontend da consolidare)
- Multi-company / Legal entities
- Public quote / signing pages
- Service tickets / Assistenza

### 8. Priorità

**🔴 CRITICAL (blocca uso enterprise IT)**
1. Fatturazione Elettronica SDI (obbligo legale)
2. Sistema B autorevole (V3 §10 Fase 1-2)
3. Sentry backend + APScheduler
4. Firma canvas rewrite
5. Preventivatore unificato

**🟠 HIGH**
6. WhatsApp Business integration
7. Portale ENEA ecobonus
8. OCR listini via Gemini Vision (già installato!)
9. Cache Redis su lookup
10. Cleanup deps + bundle analyzer
11. Cleanup production_config duplicato (script pronto)
12. Fix terminologia margin→markup
13. Rewrite ParametricAdminPage (V3 §9)
14. Doppio snapshot su preventivi
15. Onboarding user-friendly

**🟡 MEDIUM**
16. Ricerca globale instant
17. Dashboard unica
18. PDF viewer inline
19. Table virtualizzata liste lunghe
20. MFA con OTP (input-otp già installato)
21. Drag & drop vani
22. Bundle analyzer + code splitting
23. Notifiche real-time
24. Antivirus upload

**🟢 LOW**
25. API versioning `/api/v1/`
26. Realtà aumentata
27. TTS/STT
28. RAG capitolati
29. 3D configurator

### 9. Roadmap di rifattorizzazione (12 mesi)

**Q1 (0-3 mesi)** — Stabilizzazione + P0 critici
- Approvazione ARCHITECTURAL_AUDIT_V3
- Fase 1-2 V3 (modelli + migrazione dati)
- Sentry + APScheduler online
- Cleanup deps + bundle
- Fix cleanup production_config

**Q2 (3-6 mesi)** — Motore unificato + fatturazione
- Fase 3-5 V3 (wire-in motori + preventivatore)
- Integrazione SDI (Aruba/Fatture in Cloud)
- ParametricAdminPage rewrite (V3 §9)
- Firma canvas mobile-first

**Q3 (6-9 mesi)** — Ecosistema + comunicazione
- WhatsApp Business
- Portale ENEA
- OCR listini via Gemini Vision
- ezdxf export CNC
- Dashboard unificata

**Q4 (9-12 mesi)** — Scalabilità + UX
- Cache Redis + CDN
- API versioning
- Notifiche real-time SSE
- Search instant
- Onboarding role-based
- Mobile app posatore (PWA)

### 10. Nuovo modello architetturale consigliato

```
┌─────────────────────────────────────────────────────────────────┐
│                     LAYER FRONTEND (React 19)                    │
│  Mobile-first, PWA, offline-tolerant, i18n IT-first              │
│  ┌────────────┬─────────────┬──────────────┬─────────────────┐   │
│  │ Preventivo │ Sistemi B   │ Regole A     │ CRM+Cal+Contr  │   │
│  │ Wizard 3   │ (9 tab)     │ (commerc.)   │                │   │
│  │ step       │             │              │                │   │
│  └────────────┴─────────────┴──────────────┴─────────────────┘   │
└──────────────────────────────┬──────────────────────────────────┘
                               │ REST /api/v1/*  (JWT + tenant)
┌──────────────────────────────▼──────────────────────────────────┐
│              LAYER API (FastAPI 0.11x, versioned)                │
│  Rate-limit per tenant · Sentry APM · Structured logging JSON    │
└────────┬───────────────────┬─────────────────┬──────────────────┘
         │                   │                 │
┌────────▼─────────┐  ┌──────▼──────┐  ┌───────▼───────────────┐
│ Domain Services   │  │ Integration │  │ Event Bus (SSE→client)│
│ (single-resp)     │  │ Adapters    │  │ + Job Queue (APS)     │
│ ProfileSystemRes  │  │ SDI, WhAts, │  │ (reminder, cleanup)   │
│ BomResolver       │  │ ENEA, OCR   │  │                       │
│ TechnicalCostRes  │  │             │  │                       │
│ CommercialPricSvc │  │             │  │                       │
│ CommercialPricingSvc│ Stripe, PEC  │  │                       │
└────────┬─────────┘  └─────────────┘  └───────────────────────┘
         │
┌────────▼──────────────────────────────────────────────────────┐
│                    LAYER DATA (Mongo + Redis)                  │
│  ┌─────────────────┬──────────────────┬──────────────────┐     │
│  │ Sistema B       │ Sistema A        │ Operativo         │     │
│  │ (autorevole)    │ (commerciale)    │                   │     │
│  │ profile_systems │ commercial_prods │ quotes            │     │
│  │ profiles        │ commercial_rules │ contracts         │     │
│  │ bom_templates   │ promotions       │ leads/customers   │     │
│  │ item_pricelists │ tax_configs      │ appointments      │     │
│  │  (kind=cost)    │                  │ activities        │     │
│  │ glass_recipes   │                  │ production_orders │     │
│  │ production_conf │                  │ cutting_lists     │     │
│  │ color_categories│                  │ service_tickets   │     │
│  └─────────────────┴──────────────────┴──────────────────┘     │
│  Redis cache: lookup catalog, session, rate-limit, pub/sub      │
└──────────────────────────────────────────────────────────────┘
```

**Principi cardine del nuovo modello**:
1. **Single Source of Truth per dominio** (tecnico ≠ commerciale, no duplicati)
2. **Flusso unidirezionale**: Sistema B → Resolver → Sistema A → Preventivo → Contratto
3. **Doppio snapshot immutabile** su ogni riga di preventivo
4. **Servizi single-responsibility** (4 resolver esplicitati in V3)
5. **API versionata** `/api/v1/` per stabilità client
6. **Event-driven per integrazioni esterne** (SDI, WhatsApp, ENEA, OCR) via queue async
7. **Frontend mobile-first PWA** con offline-tolerance per posatore
8. **Cache Redis strategica** su lookup ad alta frequenza
9. **Observability nativa** — Sentry + structured logging + tenant-scoped tracing
10. **Test contract per ogni resolver** — regressione automatica

---

## DOPO IL REPORT

**Nessuna implementazione avviata.** Il documento è pronto per **cross-validation** con un secondo modello (Claude Opus / Gemini 3 Pro).

**Suggerimento per la cross-validation**: chiedere al secondo modello di:
1. Contestare punto per punto le classificazioni Livello 1 (ESSENZIALE/DA RIFARE/LEGACY)
2. Sfidare la direzione V3 "Sistema B autorevole" — è la scelta giusta o esistono alternative migliori?
3. Verificare le priorità Q1-Q4 — sono realistiche o troppo ambiziose?
4. Individuare ulteriori bug architetturali non visti da me
5. Proporre modello architetturale alternativo se ha argomenti forti

---

**Documento chiuso.** Attende il secondo review + decisione finale del PO.
