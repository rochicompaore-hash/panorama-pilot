# CURRENT_PRODUCT_CAPABILITY_AUDIT_V1

**Data:** 2026-08-11 · **Modalità:** SOLO ANALISI (zero modifiche)  
**Scopo:** Rispondere a: *"Cosa sa fare Panorama Pilot OGGI?"* e *"Cosa manca per usarlo davvero in Enerhia?"*  
**Base evidenze:** codice preview (branch `feature/unified-pricing-phase1`, commit `86c2067`), 53 pagine frontend, 56 router backend, verifica endpoint via curl, audit precedenti (`CURRENT_PRICING_FLOW_AUDIT_V1.md`, `MILESTONE_1_UNIFIED_PRICING_DELIVERABLE.md`, `PREVIEW_KNOWN_ISSUES_V1.md`).

---

## 0. Executive Summary

**Panorama Pilot NON è ancora utilizzabile come ERP quotidiano da Enerhia.**  
Ha una **struttura ampia ma disconnessa**: il backend copre l'80% dei domini, il frontend ha 53 pagine, ma il **flusso Lead → Contratto → Produzione → Posa non è mai unificato end-to-end**. Il nuovo motore Unified Pricing (Milestone 1) funziona via API ma la UI del preventivatore continua a bypassarlo con `unit_price` manuale.

### Percentuali (pesate per importanza operativa)

| Dimensione | % | Motivazione |
|---|:-:|---|
| **Backend implementato** | **~72%** | 56 router, motore pricing_v3 funzionante, CRM/Preventivi/Contratti/Produzione presenti; mancano BOM tecnica reale, cutlist, magazzino operativo |
| **Frontend implementato** | **~55%** | 53 pagine ma molte legacy/duplicate; nuovo configuratore prodotto assente |
| **Flussi realmente end-to-end** | **~20%** | Solo Lead→Cliente→Preventivo con prezzo manuale funziona. Firma OTP/produzione/cutlist/posa non collegati |
| **Prontezza per utilizzo aziendale reale** | **~15%** | Enerhia oggi non può fare un ciclo commerciale completo senza intervento tecnico |

---

## 1. Percorso commerciale completo (§3 richiesta)

| # | Fase | UI presente | Backend | Salva davvero | Collegata alla successiva | Stato |
|---|---|:-:|:-:|:-:|:-:|---|
| 1 | Lead | ✅ /leads | ✅ /api/leads | ✅ | ✅ conversione a cliente | **OPERATIVO UI** |
| 2 | Cliente | ✅ /customers | ✅ /api/customers | ✅ | ✅ | **OPERATIVO UI** |
| 3 | Appuntamento | ✅ /calendar | ✅ /api/appointments | ✅ | ⚠️ notifiche mock | **PARZIALE** |
| 4 | Sopralluogo/rilievo | ✅ /surveys | ✅ | ⚠️ | ⚠️ non genera revisione automatica | **PARZIALE** |
| 5 | Preventivo (creazione) | ✅ /quotes, /quote-structure | ✅ /api/quotes, /api/quote-structure | ✅ | ✅ | **OPERATIVO UI** |
| 6 | Configurazione prodotti | ⚠️ QuoteStructurePage aggiunge tramite `unit_price` manuale | ✅ `compute-and-add` (motore legacy) + `/api/pricing/compute` (nuovo, non usato dalla UI) | ✅ | ⚠️ senza snapshot | **UI SENZA MOTORE (unified)** |
| 7 | Calcolo prezzo | ✅ manuale in UI · ✅ automatico via API v3 · ✅ automatico via commercial_perimeter legacy | ✅ | ✅ | — | **PARZIALE** — 3 percorsi non allineati |
| 8 | PDF preventivo | ✅ endpoint PDF | ✅ WeasyPrint | ✅ | ⚠️ layout prototipo | **PARZIALE** |
| 9 | Firma cliente | ⚠️ endpoint OTP/firma | ⚠️ | ❌ Redis mancante in preview | ❌ | **ROTTO in preview / PARZIALE prod** |
| 10 | Contratto | ✅ /contracts | ✅ /api/contracts | ✅ | ⚠️ conversione preventivo→contratto manuale | **PARZIALE** |
| 11 | Acconto | ⚠️ /payment-plans | ✅ | ✅ | ❌ logica "50% firma + 50% avviso" non enforced | **PARZIALE** |
| 12 | Rilievo tecnico | ✅ /surveys, /technical-schedules | ✅ | ✅ | ❌ non genera automaticamente ordine produzione | **PARZIALE** |
| 13 | Produzione | ✅ /production-orders | ✅ | ✅ | ❌ non collega a cutlist automaticamente | **PARZIALE** |
| 14 | Merce pronta | ⚠️ | ✅ /api/production-orders status | ✅ | ❌ no notifica saldo | **PARZIALE** |
| 15 | Posa | ✅ /installation-plans, /install-reports | ✅ | ✅ | ⚠️ no verbale firmato | **PARZIALE** |
| 16 | Collaudo | ✅ /qc | ✅ | ✅ | — | **PARZIALE** |
| 17 | Saldo | ⚠️ | ✅ | ⚠️ | ❌ | **PARZIALE** |
| 18 | Assistenza | ✅ /service-tickets | ✅ | ✅ | ✅ | **OPERATIVO UI** |
| 19 | Recensione | ❌ | ❌ | ❌ | ❌ | **NON IMPLEMENTATO** |

### Dove si interrompe oggi il flusso
Il flusso si spezza **tra passi 6-7-9-12-13**:
- **6-7**: la UI del preventivatore usa `unit_price` manuale — nessun percorso automatico dal Catalogo al Preventivo con snapshot verificato
- **9**: Firma OTP inattiva in preview (Redis assente); rischiosa anche in produzione
- **12-13**: nessun passaggio automatico `contratto → rilievo → ordine produzione → cutlist`
- **19**: recensione post-installazione non prevista

---

## 2. Unified Pricing — Milestone 1 (§7-8 richiesta)

Verifica endpoint via curl (evidenza):
```
POST /api/pricing/compute {product_key:PROEVOLUTION, window_type:WINDOW, n_sashes:1, 900×1500, DOUBLE_STANDARD}
→ pricing_status: ok
→ final_unit_price: 960.25 €
→ n_components: 5 (FRAME, FRAME_REINFORCEMENT, SASH, SASH_REINFORCEMENT, GLAZING_BEAD)
→ calculation_hash: SHA-256 verificabile
```

### Matrice punti d'ingresso (§8)

| Punto d'ingresso | Usa Unified Pricing? | Usa commercial_perimeter? | Prezzo per GT-01 |
|---|:-:|:-:|:-:|
| `POST /api/pricing/compute` | ✅ SÌ | ❌ | **960.25 €** |
| `/product-simulator` | ❌ | ✅ | 356.29 € (con seed P0 iter40) |
| `/quote-structure` catalogo | ❌ | ❌ (usa `unit_price` manuale) | scritto a mano |
| `compute-and-add` | ❌ | ✅ | 356.29 € |
| `recompute` | ❌ | ✅ | 356.29 € |
| PDF preventivo | ❌ | ✅ | come snapshot salvato |

**Verdetto:** ⚠️ **UNIFIED PRICING IMPLEMENTATO MA NON ANCORA CABLATO NEL FLUSSO COMMERCIALE.**  
Solo l'endpoint HTTP e i test golden lo esercitano. Nessuna UI operativa lo invoca.

**Un utente commerciale può OGGI creare un preventivo dalla UI usando il NUOVO Unified Pricing?**  
**NO.** Motivazione: il Catalogo prodotti (`/quote-structure`) chiama `POST /api/quote-structure/openings/{id}/products` con `unit_price` manuale. Il motore v3 non è raggiunto da nessuna interazione UI.

---

## 3. Copertura prodotti del nuovo motore (§9)

| Categoria | Config | Unified Pricing | Legacy commercial_perimeter | Non disponibile |
|---|---|:-:|:-:|:-:|
| Finestre | 1 anta | ✅ (Milestone 1) | ✅ | — |
| Finestre | 2 ante | ❌ | ✅ | — |
| Finestre | 3 ante composizione (1+2) | ❌ | ✅ (approssimato) | — |
| Finestre | 3 ante telaio unico | ❌ | ❌ MISSING_TECHNICAL_RECIPE | ⚠️ BR-03 aperta |
| Finestre | 4 ante | ❌ | ❌ | ✅ |
| Finestre | fisso | ❌ | ✅ | — |
| Portefinestre | 1 anta | ❌ | ⚠️ (senza soglia) | — |
| Portefinestre | 2 ante | ❌ | ⚠️ | — |
| Portefinestre | 3 ante | ❌ | ❌ | ✅ |
| Soglia ribassata | tutte config | ❌ | ❌ (formula V1_3 non implementata) | ✅ |
| Scambio battuta €5.50/ml | 2+ ante | ❌ | ⚠️ prezzo €/ml da listino (non V1_3) | — |
| Montante fisso | tutte | ❌ | ❌ | ✅ |
| Traverso | tutte | ❌ | ❌ | ✅ |
| Pellicolato +10% | colori standard | ⚠️ framework presente in v3 ma inattivo (colori non riconosciuti) | ⚠️ +6% (non 10%) | — |
| Vetri DOUBLE_STANDARD/SATIN/TRIPLE | tutti | ✅ v3 | ✅ (solo DOUBLE_STANDARD nel motore attuale) | — |

**Verdetto copertura:** **~5%** delle configurazioni serramento richieste da Enerhia sono coperte dal nuovo motore. Il legacy copre ~40%.

---

## 4. BOM e costo industriale ProEvolution 1-anta (§10)

Fonte di ogni prezzo componente:

| Componente | Prezzo unitario | Fonte reale |
|---|---:|---|
| FRAME | 4.02 €/ml | Costante V1_3 (`V1_3_COMPONENT_PRICES`) — **placeholder normativo**, NON dato reale Enerhia |
| FRAME_REINFORCEMENT | 1.52 €/ml | Idem |
| SASH | 2.31 €/ml | Idem |
| SASH_REINFORCEMENT | 1.34 €/ml | Idem |
| **GLAZING_BEAD** | **0.00 €/ml** | ⚠️ **PLACEHOLDER** (attende catalogo). Il costo non viene realmente calcolato |
| GLASS DOUBLE_STANDARD | 76 €/m² | Costante V1_3 BR-07 — corretto ma statico |
| HARDWARE_WINDOW_STD | 76.00 € | Costante V1_3 — non modificabile da UI |
| LABOR hourly_workshop_cost | 180 €/h | Collection `workshop_cost_configs` — **versionato** (buono), ma **inserito manualmente in DB tramite seed script**, nessuna UI per modificarlo |

**Solo `workshop_cost_configs` e `commercial_pricing_rules` sono in DB versionati.** Tutto il resto è nel codice.

---

## 5. Listini (§11)

| Sorgente | Ancora letta? | Da quale motore? | UI modificabile? | Versionata? | Tenant scoped? | Legacy? | Autorevole? |
|---|:-:|---|:-:|:-:|:-:|:-:|:-:|
| `item_pricelists` schema catalog | ✅ | `commercial_perimeter` | ✅ /pricelists + importer | ⚠️ solo `version` numerica | ✅ | ⚠️ target di sostituzione | ✅ per legacy |
| `item_pricelists` schema parametric | ❌ | `parametric_engine` (isolato) | ✅ /parametric/admin | ✅ | ✅ | ✅ Legacy | ❌ |
| `production_config` | ✅ | commercial_perimeter | ⚠️ endpoint PATCH, nessuna UI | ❌ | ✅ | ⚠️ target di sostituzione | ✅ per legacy |
| `workshop_cost_configs` (nuovo) | ✅ v3 | TechnicalCostResolver | ❌ solo DB/API | ✅ | ✅ | ❌ | ✅ per v3 |
| `commercial_pricing_rules` (nuovo) | ✅ v3 | CommercialPricingService | ❌ solo DB/API | ✅ | ✅ | ❌ | ✅ per v3 |
| Prezzi V1_3 hardcoded | ✅ v3 fallback | TechnicalCostResolver | ❌ codice | ⚠️ solo git | ❌ tenant-agnostic | ⚠️ transitorio | ⚠️ solo Milestone 1 |
| `glass_recipes` | ✅ | commercial_perimeter | ⚠️ | ⚠️ | ✅ | ⚠️ | ⚠️ |

**Domanda chiave:** *Un amministratore può oggi da UI aggiornare il costo del FRAME e vedere il nuovo prezzo usato dal nuovo TechnicalCostResolver?*  
**NO.** Il fallback V1_3 è hardcoded. Il listino tenant (`item_pricelists`) è letto dal resolver come primo lookup, ma la UI attuale gestisce entries in schema legacy.

Stessa domanda per: **vetro** → ❌ (in codice) · **ferramenta** → ❌ (in codice) · **hourly_workshop_cost** → ❌ (solo DB) · **moltiplicatore** → ❌ (solo DB).

---

## 6. Configurazione tecnica (§12)

| Funzione | Stato |
|---|---|
| Creare sistema profilo (`parametric_profile_systems`) | UI OPERATIVA `/parametric/admin` — **legacy, scollegata dal preventivo** |
| Modificare sistema profilo | UI OPERATIVA — non impatta preventivo |
| Creare componenti (`profiles`) | UI OPERATIVA — non impatta preventivo |
| Associare codici componente al motore v3 | ❌ nessuna UI |
| Inserire costo €/ml da UI del nuovo motore | ❌ solo DB |
| Versionare costo | ⚠️ solo tramite versione listino (legacy) |
| Creare ricetta tecnica (`technical_recipes` nuova collection) | ❌ solo DB/API |
| Modificare formula (bomTemplates parametric) | ⚠️ UI legacy `/parametric` con AST safe editor |
| Definire BOM | ⚠️ solo in codice per v3, UI parametric per legacy |
| Configurare vetro | ⚠️ /parametric/admin (legacy) |
| Configurare ferramenta | ⚠️ /parametric/admin (legacy) |
| Configurare tempi produzione | ❌ solo DB `production_config` |
| Configurare costo officina | ❌ solo DB `workshop_cost_configs` |
| Configurare colori | ⚠️ `/parametric/admin` |
| Configurare moltiplicatore | ❌ solo DB `commercial_pricing_rules` |

**Verdetto:** l'utente **non può amministrare i dati del nuovo motore senza toccare MongoDB**.

---

## 7. Riepilogo per sezione (§4-45, sintetico)

| Sezione | Stato reale | Note |
|---|---|---|
| **CRM Lead** | ✅ OPERATIVO UI | Pipeline configurabili, non hardcoded |
| **Clienti** | ✅ OPERATIVO UI | Timeline unica presente (attività + storico) |
| **Calendario/Appuntamenti** | ⚠️ PARZIALE | Reminder mock, no sync Google Calendar attiva |
| **Preventivi (CRUD)** | ✅ OPERATIVO UI | Numerazione aziendale progressiva OK |
| **Preventivi (pricing automatico)** | ❌ UI SENZA MOTORE | Solo unit_price manuale nella UI |
| **Product Simulator** | ✅ OPERATIVO BACKEND/API + UI | Usa commercial_perimeter (legacy) |
| **/pricing/compute Milestone 1** | ✅ OPERATIVO BACKEND/API | Non collegato a nessuna UI |
| **Catalogo prodotti** | ⚠️ PARZIALE | 9 prodotti presenti, no configuratore avanzato |
| **Servizi e prezzi semplici** | ⚠️ PARZIALE | Metodi A-G esistono ma non entrano nel preventivo |
| **PDF preventivo** | ⚠️ PARZIALE | Genera ma layout prototipo, dati completi |
| **Contratti** | ⚠️ PARZIALE | CRUD OK, conversione preventivo→contratto manuale |
| **Firma OTP** | ❌ ROTTO in preview | Redis assente. Rate limit OTP non attivo |
| **Pagamenti** | ⚠️ PARZIALE | Piani pagamenti esistono, no enforcement "50%+50%" |
| **Rilievo tecnico** | ⚠️ PARZIALE | Modulo presente, no ponte automatico a produzione |
| **Produzione** | ⚠️ PARZIALE | Ordini presenti, senza cut-list automatico |
| **Cut list** | ❌ NON IMPLEMENTATO | Preventivo → BOM → lista taglio non è un flusso |
| **Magazzino** | ⚠️ PARZIALE | Articoli/giacenze CRUD, no ordini fornitore integrati |
| **Fornitori & PO** | ⚠️ PARZIALE | Anagrafica OK, ricezione parziale |
| **Posa** | ⚠️ PARZIALE | Pianificazione OK, verbale firmato mancante |
| **Assistenza** | ✅ OPERATIVO UI | Ticket, categorie, assegnazione |
| **Portale cliente** | ❌ NON IMPLEMENTATO | Nessuna UI cliente-facing |
| **Provvigioni** | ⚠️ PARZIALE | `commission_engine` esiste, calcolo su contratto non automatico |
| **Dashboard/KPI** | ⚠️ PARZIALE | KPI CRM reali; produzione/incassi mock/parziali |
| **Multi-tenant** | ✅ OPERATIVO | Guard `tenant_id` enforced. Test isolation verdi |
| **RBAC** | ✅ OPERATIVO | Permessi granulari; Super Admin bypassa (voluto) |
| **Documenti generati** | preventivo PARZIALE · contratto PARZIALE · rilievo PARZIALE · cutlist ❌ · verbale posa ❌ · conferma ordine ❌ |
| **Comunicazioni email** | ⚠️ PARZIALE | SMTP SiteGround configurato, delivery=test in preview |
| **WhatsApp/SMS** | ❌ NON IMPLEMENTATO | Nessuna integrazione attiva |
| **Audit log** | ✅ OPERATIVO | 100+ tipi di azione tracciati con audit_service |
| **Mobile** | ⚠️ USABILE CON LIMITI | Login/dashboard OK, wizard preventivo non ottimizzato < 375px, canvas GeometryBuilder illeggibile |

---

## 8. Ridondanze (§38-40)

### 8.1 Pagine ridondanti (route frontend)
| Route | Raccomandazione |
|---|---|
| `/quote-structure` | MANTENERE (rinominata Catalogo) — da wired al nuovo motore |
| `/product-simulator` | MANTENERE come debug tecnico (ristretto pricing_admin) |
| `/pricing-hub` | UNIRE con "Servizi e prezzi semplici" |
| `/pricelists` | LEGACY — nascosta iter40, ELIMINARE DOPO MIGRAZIONE |
| `/pricelist-importer` | LEGACY — nascosta iter40, ELIMINARE DOPO MIGRAZIONE |
| `/parametric` + `/parametric/admin` | LEGACY — nascoste iter40, ELIMINARE DOPO MIGRAZIONE dati utili nella nuova "Configurazione tecnica" |
| `/product-catalog` | UNIRE con `/quote-structure` |
| `/geometry-builder` | MANTENERE (utile) ma migliorare mobile |
| `/technical-schedules` | MANTENERE |
| `/site-conditions` | UNIRE con rilievo tecnico |

**Riduzione realistica:** ~8 pagine su 53 possono essere nascoste/unite → **-15%** superficie UI.

### 8.2 Motori pricing (§39 aggiornato post-Milestone 1)
| Motore | Stato |
|---|---|
| `pricing_v3` (4 resolver + orchestrator) | **TARGET ATTIVO API** |
| `commercial_perimeter` | **ADAPTER TEMPORANEO** (usato da UI + simulate + compute-and-add) |
| `perimeter_assembler` | **ADAPTER TEMPORANEO** |
| `finestra_1a` | **LEGACY** |
| `pricing.py` | **LEGACY** |
| `pricing_v2.py` | **LEGACY** |
| `parametric_engine` | **NON USATO** (isolato, UI nascosta) |
| `bom_engine_v2` | **NON USATO** (solo via /pricing-hub) |
| `pricing_hub A-G` | **DEPRECATO** per prodotti complessi, **TARGET** per SimplePricingResolver futuro |

### 8.3 Fonti dati duplicate (§40 aggiornato)
| Concetto | Copie | Fonte attuale | Fonte target |
|---|:-:|---|---|
| Sistema profilo | 2 (`products.system`, `parametric_profile_systems`) | products (legacy) | `technical_recipes.profile_system_id` (v3) |
| Componente | 3 (`products.components`, `profiles`, `catalog_code_mappings`) | products.components | `technical_recipes.components` (v3) |
| Formula | 3 (hardcoded `commercial_perimeter`, `bom_templates`, hardcoded `pricing_v3/formulas.py`) | commercial_perimeter | `pricing_v3/formulas.py` versionato |
| BOM | 2 (commercial_perimeter, bom_templates) | commercial_perimeter | `BomResolver` v3 |
| Vetro | 2 (`glass_recipes`, `glass_types`) | glass_recipes | `pricing_v3/formulas.GLASS_PRICES_PER_SQM` |
| Colore | 2 (`color_categories`, `colors`) | color_categories | `formulas.STANDARD_FOIL_COLORS` |
| Ferramenta | 2 (`products.default_hardware_kit`, `hardware_kits`) | products | codice v3 (transitorio) |
| Costo officina | 2 (`production_config.hourly_cost`, `workshop_cost_configs`) | production_config (legacy) | **workshop_cost_configs** (v3) |
| Moltiplicatore | 2 (`production_config.default_margin_pct`, `commercial_pricing_rules`) | production_config (legacy) | **commercial_pricing_rules** (v3) |

---

## 9. Simulazioni ruoli (§41-44)

### 9.1 Cosa può fare oggi un'AZIENDA (Enerhia)
**Posso già fare:**
- Anagrafica clienti/lead completa
- Preventivi con prezzi scritti a mano
- Contratti generici
- Ticket assistenza
- Audit log immutabile
- Multi-tenant isolato

**Posso fare ma con limitazioni:**
- Preventivi con prezzi manuali (no automatismo)
- PDF preventivo (layout prototipo)
- Produzione (senza cutlist automatico)
- Posa (senza verbale firmato)

**Non posso ancora fare:**
- Preventivare automaticamente ProEvolution dalla UI col nuovo motore
- Configurare 2 ante, portefinestre, montanti/traversi
- Firma cliente OTP (Redis mancante)
- Passaggio automatico contratto→produzione→cutlist
- Portale cliente
- WhatsApp/SMS
- Recensioni post-installazione

**Non devo usare perché legacy:**
- /pricelists, /pricelist-importer, /parametric*, /parametric/admin (nascoste iter40)

### 9.2 Cosa fa oggi un COMMERCIALE
Un venditore Enerhia: **lead → chiamata → appuntamento → cliente → preventivo con prezzo manuale**.  
**Si ferma qui.** Non può configurare tecnicamente il prodotto in modo che il sistema calcoli il prezzo. Deve scriverlo a mano. Il PDF si genera. La firma OTP non funziona in preview.

### 9.3 Cosa fa oggi la PRODUZIONE
Ordine produzione lo può creare manualmente. **Non riceve automaticamente** distinta materiali dal contratto. Nessuna lista di taglio. Nessuna prenotazione magazzino automatica.

### 9.4 Cosa fa oggi il TITOLARE
Vede: pipeline lead (reale), clienti totali, preventivi totali. **Non vede**: incassi reali (mock), margine per prodotto (dati insufficienti), performance venditore su chiusure firmate (firma non funziona).

---

## 10. Gap → Priorità (§45)

| Modulo | Obiettivo | Stato oggi | Gap | Priorità |
|---|---|---|---|:-:|
| Preventivo con Unified Pricing | Prezzo da UI = prezzo da API v3 | UI usa unit_price manuale | Wire `/api/pricing/compute` dal configuratore prodotto | **P0** |
| Configuratore prodotto UI | Wizard step-by-step con validazione | Non esiste | Costruire configuratore in `/quote-structure` addProduct dialog | **P0** |
| Firma cliente | OTP funzionante | Redis assente in preview, incerto in prod | Installare Redis in ambienti | **P0** |
| Copertura formule V1_3 | 6/6 configurazioni base (1a/2a WINDOW + 1a/2a DOOR_WINDOW + fisso) | Solo 1a WINDOW | Fase 1B implementazione | **P0** |
| Contratto → Produzione automatico | Un contratto firmato genera ordine + cutlist | Non collegato | Ponte contratti→production_orders + BomResolver output → cutlist | **P0** |
| GLAZING_BEAD prezzo reale | Costo €/ml documentato | Placeholder 0€ | Fornire prezzo reale | **P0** |
| UI configurazione tecnica nuovo motore | Admin gestisce workshop_cost/multiplier/ricette | Solo DB/API | Costruire pagina admin per `workshop_cost_configs`, `commercial_pricing_rules`, `technical_recipes` | **P1** |
| PDF layout finale | Layout brand-compliant | Prototipo | Design + template Jinja | **P1** |
| Portale cliente | Vede stato ordine + firma | Non esiste | Costruire mini-UI cliente | **P1** |
| Cut list generazione | Da BOM v3 a cutlist ottimizzata | Non implementato | Algoritmo nesting + integrazione | **P1** |
| Verbale posa firmato | Documento firmato al termine | Non esiste | Modulo verbale + firma installatore | **P2** |
| Recensione post-installazione | Email automatica al cliente | Non esiste | Modulo recensione + email | **P3** |

---

## 11. Minimum Operating Product per Enerhia (§46)

Il MOP è ciò che Enerhia deve poter fare per sostituire gli strumenti attuali:

1. ✅ **Anagrafica clienti/lead** — già OK
2. ⚠️ **Preventivo con calcolo automatico**: ProEvolution 1-anta + 2-ante + portafinestra 1a-2a con formule reali → **richiede wiring UI + Fase 1B**
3. ⚠️ **PDF preventivo pulito** → richiede design layout
4. ⚠️ **Firma cliente** → richiede Redis
5. ⚠️ **Contratto congelato con snapshot** → parziale, richiede validazione hash al load
6. ⚠️ **Passaggio a produzione** → richiede automation contratto→ordine
7. ⚠️ **Pianificazione posa** → OK ma serve verbale firmato
8. ✅ **Ticket assistenza** — già OK
9. ✅ **Audit e multi-tenant** — già OK

**MOP raggiungibile in 3-4 iterazioni focalizzate** (Fase 1B + wiring UI + Redis + design PDF).

---

## 12. Cosa possiamo ELIMINARE o CONGELARE (§47-48)

### Eliminare (dopo migrazione)
- `finestra_1a.py` legacy engine (dopo wiring v3)
- `pricing.py` legacy compute_line (dopo migrazione preventivi vecchi)
- `pricing_v2.py` (idem)
- `/parametric`, `/parametric/admin` UI (dati preservati, UI eliminata)

### Congelare (non sviluppare oltre)
- **AI/OCR/WhatsApp** — nessuna necessità operativa Enerhia oggi
- **Plugin ecosystem** (AUDIT_PLUGINS_V1) — enterprise, non pilota
- Nuovi metodi in `/pricing-hub` — semplificare a SimplePricingResolver
- Sistema `parametric_engine` — dati utili → migrare a `technical_recipes` (backlog Fase 3)

---

## 13. Roadmap minima (§49)

**STEP 1 — Wiring UI Milestone 1** (1-2 iter)  
Obiettivo: `/product-simulator` chiama `/api/pricing/compute`  
Criterio: stesso input → stesso hash sia da UI che da curl

**STEP 2 — Fase 1B: WINDOW_2_SASH + DOOR_WINDOW_1_SASH + DOOR_WINDOW_2_SASH** (2-3 iter)  
Obiettivo: MEETING_STILE, THRESHOLD, glass 2-lastre  
Criterio: Golden Test GT-02, GT-03, GT-04 verdi

**STEP 3 — Wiring UI preventivatore + `/quote-structure` add product** (2 iter)  
Obiettivo: bottone "Configura & Aggiungi" chiama `/api/pricing/compute`  
Criterio: linea preventivo con `pricing_engine=pricing_v3` + snapshot v3

**STEP 4 — Redis + Firma OTP** (1 iter)  
Obiettivo: firma cliente end-to-end  
Criterio: preventivo → PDF → OTP → firmato → contratto

**STEP 5 — Ponte Contratto → Produzione + Cutlist** (2-3 iter)  
Obiettivo: firma contratto genera automaticamente ordine produzione + cutlist da BOM v3  
Criterio: bottone contratto → produzione senza intervento manuale

**STEP 6 — Configurazione tecnica UI** (2 iter)  
Obiettivo: admin edita workshop_cost, multiplier, prezzi listino da UI  
Criterio: cambio prezzo FRAME da UI → nuovo preventivo usa il nuovo valore

**STEP 7 — MOP DEPLOY** (1 iter)  
Obiettivo: pilota Enerhia in ambiente dedicato  
Criterio: 5 preventivi reali generati, firmati, portati a contratto, avviati in produzione

**Totale realistico:** 11-14 iterazioni → **~3-4 mesi** di sviluppo focalizzato.

---

## 14. Verdetto finale (§50)

| Domanda | Risposta |
|---|---|
| **A. Panorama Pilot è utilizzabile oggi come ERP principale di Enerhia?** | **NO** |
| **B. Può sostituire il CRM attuale?** | **PARZIALMENTE** (lead/cliente/appuntamento sì, KPI conversione parziali) |
| **C. Può sostituire il preventivatore attuale?** | **NO** (motore v3 esiste ma UI non lo usa; V1_3 formule mancanti) |
| **D. Può gestire correttamente la produzione?** | **NO** (nessun ponte automatico da contratto, nessuna cutlist) |
| **E. Può gestire posa e assistenza?** | **PARZIALMENTE** (ticket sì, verbale posa firmato no) |
| **F. Primo blocco operativo** | **UI preventivo scollegata dal motore v3** — il commerciale scrive prezzi a mano |
| **G. Secondo blocco** | **Formule V1_3 mancanti per 2 ante / portafinestra** — Enerhia produce anche questi prodotti |
| **H. Terzo blocco** | **Firma OTP non funzionante in preview (Redis assente)** e ponte contratto→produzione mancante |
| **I. 5 interventi che portano più velocemente all'uso reale** | 1. Wire UI simulator + preventivo al `/api/pricing/compute` <br> 2. Fase 1B (2 ante + portafinestra + soglia + meeting stile) <br> 3. Redis + firma OTP funzionante <br> 4. Ponte contratto → ordine produzione + cutlist v3 <br> 5. UI amministrazione (workshop_cost, multiplier, listino nuovo schema) |
| **L. Funzioni da eliminare/congelare** | AI/OCR/WhatsApp (congelare) · Plugin ecosystem (congelare) · `/parametric*` (nascondere ✓ fatto) · `finestra_1a` (eliminare dopo wiring) · `pricing_v2` (eliminare dopo migrazione preventivi vecchi) · `bom_engine_v2` (congelare) |

---

## 15. Evidenze (§51)

Ogni claim OPERATIVO in questo audit ha almeno una delle seguenti evidenze:

- **Unified Pricing v3**: curl POST `/api/pricing/compute` risposta `pricing_status=ok, final_unit_price=960.25€, calculation_hash=<sha256>` — verificato in questa sessione + 6/6 test golden verdi in `test_pricing_v3_milestone1.py` (iter42)
- **CRM Lead/Cliente/Preventivo CRUD**: esiste `/api/leads`, `/api/customers`, `/api/quotes` con `list_docs` da `ops_common.py` — evidenze in test_stabilization_rc1.py (85 pass)
- **commercial_perimeter attivo**: verificato in `CURRENT_PRICING_FLOW_AUDIT_V1.md` con curl `/api/catalog/products/{id}/simulate` = 356.29€
- **Redis assente**: `supervisorctl status` = `redis BACKOFF can't find command '/usr/bin/redis-server'` — verificato in questa sessione
- **Sidebar nuova**: `AppLayout.jsx` NAV = struttura Operatività/Prodotti/Produzione/CRM/Amministrazione — iter40 diff visibile
- **Multi-tenant guard**: 31 test in `test_audit_v1_regression.py` verificano isolamento — verdi

Claim con evidenza mancante (segnalati esplicitamente):
- Provvigioni calcolo automatico su contratto → **non testato in questa sessione**, marcato PARZIALE
- Cutlist generation → **file non presente**, marcato NON IMPLEMENTATO
- Portale cliente → **nessuna pagina in `/frontend/src/pages` matcha**, marcato NON IMPLEMENTATO
- WhatsApp integration → nessun router `whatsapp_*` attivo (solo `WhatsappLogo` icon nella sidebar per email logs)

---

## STOP

**Zero modifiche al codice.** Audit di sola lettura. In attesa della tua approvazione per procedere con:
- **Wiring UI Milestone 1** (Opzione consigliata come Step 1)
- **Fase 1B** (2 ante + portafinestra)
- **Redis + Firma OTP**
- Oppure altre priorità che vorrai indicare.
