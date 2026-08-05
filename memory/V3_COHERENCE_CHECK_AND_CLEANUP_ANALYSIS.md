# Panorama Pilot — V3 Coherence Check + Cleanup Comparison + Formula Analysis Stub
**Data**: Feb 2026 · Iter 35  
**Scope**: 3 deliverable operativi. Zero implementazione.

---

## PARTE 1 — Verifica coerenza DESIGN_REVIEW_V3 rispetto alla regola "Sistema B → costo → prezzo"

| Tema | Posizione V3 | Regola definitiva | Coerente? | Modifica necessaria |
|---|---|---|---|---|
| **Fonte del costo** | V3 §5 "Moduli da RIFARE" include "motore commerciale refactor per usare TechnicalCostResolver". V3 §9 modello a 4 layer mostra `TechnicalCostResolver → CommercialPricingService` (unidirezionale) | Sistema B autorevole → costo → moltiplicatore → prezzo | ✅ **COERENTE** — la direzione è già Sistema B autorevole (confermata in `ARCHITECTURAL_AUDIT_V3.md`) | Nessuna modifica di direzione; serve rendere esplicito nel testo che V3 assume V3 architettura |
| **Ruolo commercial_perimeter** | V3 lo tratta come "motore da rifattorizzare come livello commerciale" (§5 "Moduli da RIFARE") ma nel dettaglio §Motori dice ancora "matematicamente corretto, calcola il costo tecnico ex-novo — V3 lo risolve invertendo la dipendenza" | Deve essere sostituito o ridotto a livello commerciale puro che riceve `total_internal_cost` | 🟡 **PARZIALMENTE** — V3 lo cita come "da rifattorizzare" ma non è chiaro se **rimane** con logica commerciale o viene **eliminato** e sostituito da `CommercialPricingService` | Chiarire: `commercial_perimeter.py` va **sostituito** da `TechnicalCostResolver + CommercialPricingService`. Non refactor. Deprecato dopo Fase 3 V3 |
| **Sistemi profilo** | V3 §Moduli MANTENERE include implicitamente `profile_systems`. `ARCHITECTURAL_AUDIT_V3.md` li mette esplicitamente in Sistema B autorevole | Fonte tecnica condivisa unica | ✅ **COERENTE** | — |
| **Componenti** | V3 §DB "eliminabile products.components[] inline". V3 §Moduli RIFARE "Sistema B admin (9 tab)" | Inseriti una sola volta in Sistema B (`profiles` + `bom_templates.components[]`) | ✅ **COERENTE** | — |
| **Listini di acquisto** | V3 §Mapping A→B "item_pricelists schema unificato" — MA nel V3 doc del passo Design Review non è esplicitato che i listini appartengono al Sistema B (technical, kind=cost) | Sistema tecnico (`item_pricelists kind=cost`) | 🟡 **PARZIALE** — la Design Review non enfatizza che i listini sono TECNICI. `ARCHITECTURAL_AUDIT_V3.md` §2.4 lo esplicita | Aggiungere nella prossima revisione: "listini appartengono al Sistema B come fonte costi. Il Sistema A non li legge mai direttamente" |
| **Formule** | V3 §Moduli RIFARE "Sistema B admin" include gestione formule. `ARCHITECTURAL_AUDIT_V3.md` §2.3 le mette in `bom_templates` | Ricette tecniche versionate in Sistema B | ✅ **COERENTE** | — |
| **Snapshot** | V3 §Ridondanze include "snapshot design monolitico". V3 §Moduli RIFARE include "doppio snapshot su preventivi". `ARCHITECTURAL_AUDIT_V3.md` §8 esplicita doppio snapshot | Tecnico + Commerciale separati, entrambi immutabili | ✅ **COERENTE** | — |
| **Produzione** | V3 §Analisi Produzione dichiara esplicitamente: "handoff contratto → produzione ROTTO. Il produttore ricompila i dati manualmente. Manca ProductionOrder come entità di stato." | Deriva dalla configurazione approvata (con BOM condivisa) | ✅ **COERENTE** (diagnosi corretta) — ma V3 **non ha ancora proposto** ProductionOrder come entità operativa unificante | Aggiungere in V4 finale la struttura `ProductionOrder` che collega `contracts` ↔ `cutting_lists` ↔ inventory |

### Sintesi coerenza

- **7 temi**: 5 COERENTI, 2 PARZIALI
- **Non c'è contraddizione tra V3 e la regola "Sistema B → costo → prezzo"**
- **Ma V3 è ambigua su 2 punti**: destino di `commercial_perimeter.py` (sostituito vs refactored) e enfasi sui listini come parte del Sistema B
- Le 2 modifiche vanno inserite nel prossimo passo (V4 finale), NON in V3 stessa

---

## PARTE 2 — Confronto puntuale duplicati `production_config` (CON EVIDENZA REALE)

**Nota metodologica**: come richiesto, il criterio "record più recente" NON è sufficiente. Confronto campo-per-campo, uso reale nel codice, riferimenti snapshot, **flag `is_demo`**.

### Evidenza raccolta dal DB (query effettiva iter 35)

Tenant `5e353147-2416-4ef7-aa3f-3e0007435c42` (Infissi Express Cloud demo tenant — NON PanoramaPilot come inizialmente scritto):

| Campo | Doc A (`pc-*`) | Doc B (`prodcfg-*`) | Interpretazione |
|---|---|---|---|
| `_id` | `pc-5e353147...` | `prodcfg-5e353147...` | prefix diverso |
| `tenant_id` | `5e353147...` | `5e353147...` | stesso tenant |
| `created_at` | 2026-07-20 13:34:55 | 2026-07-31 21:15:23 | **B creato DOPO A** |
| `updated_at` | 2026-07-31 **22:00:51** | 2026-07-31 21:15:23 | A aggiornato per ultimo |
| `created_by` | `924460c7-db5c...` (utente) | assente | A creato da utente reale |
| **`is_demo`** | **assente (=False)** | **`True`** | 🔴 **B è un doc SEED demo, non dato operativo** |
| `hourly_cost` | **30.0** €/h | 28.0 €/h | valori diversi |
| `production_time_default_minutes` | 30 min | 45 min | valori diversi |
| `default_margin_pct` | **40.0**% | 35.0% | valori diversi |
| `default_glass_price_per_sqm` | **assente** | 76.0 €/m² | A incompleto |
| `default_glass_min_sqm` | **assente** | 0.5 m² | A incompleto |
| `fixed_window_time_minutes` | **assente** | 30 min | A incompleto |
| `one_sash_time_minutes` | **assente** | 45 min | A incompleto |
| `two_sash_time_minutes` | **assente** | 60 min | A incompleto |
| `three_sash_time_minutes` | **assente** | 80 min | A incompleto |
| `four_sash_time_minutes` | **assente** | 100 min | A incompleto |
| `deleted_at` | None | None | entrambi attivi |

### Analisi verdetto rivista (rispetto alla prima ipotesi errata)

**Scoperta chiave**: Doc B è `is_demo=True`. Questo cambia radicalmente la decisione:

1. **Doc B è un seed demo** — creato dal `seed_test_motor.py` per popolare un tenant di test. NON è dato operativo del cliente
2. **Doc A è il config vero** del tenant (creato dall'utente reale `924460c7...` il 20 luglio, aggiornato il 31 luglio) — ma è **radicalmente sotto-configurato** (mancano glass_price, glass_min_sqm, tempi per tipologia)
3. **Il "criterio record più valorizzato" NON si applica** — B è più ricco solo perché è un seed template, non perché il cliente l'abbia configurato

### Decisione corretta

| Azione | Doc A (`pc-*`) | Doc B (`prodcfg-*`) |
|---|---|---|
| **Da mantenere?** | ✅ **SÌ** (config vero del tenant) | ❌ **NO** — è `is_demo=True` |
| **Da eliminare?** | No | ✅ **Sì** |
| **Motivazione** | Creato dall'utente reale, updated_at più recente, non demo | Doc seed inserito da script `seed_test_motor.py` per test motore |

### Problema secondario emerso: A è incompleto

Dopo l'eliminazione di B, il tenant si troverà con un `production_config` **valido ma incompleto**:
- Mancano `default_glass_price_per_sqm` → dopo BUG-03 audit v1: motore emette `MISSING_GLASS_PRICE` corretto ✅
- Mancano `default_glass_min_sqm` → `MISSING_GLASS_MINIMUM` corretto ✅
- Mancano tempi per tipologia → motore userà `production_time_default_minutes=30` per tutti (non ottimale, ma non blocca)

**Cioè: l'eliminazione di B è sicura ma dopo l'utente deve completare A tramite UI di gestione.**

### Rischi cancellazione B

- **Preventivi che citano B**: 0 (verificato — `pricing_snapshot` cattura valori, non ID)
- **Motore che legge B**: `find_one` non deterministico oggi. Se prende B → prezzi con hourly=28, margin=35, glass=76. Se prende A → hourly=30, margin=40, glass=None → `MISSING_GLASS_PRICE`. **Comportamento correntemente incoerente**.
- **Post-cleanup**: motore legge sempre A (unico record). Prezzi coerenti ma con MISSING errors espliciti per glass — che è il comportamento voluto post BUG-03.

### Comando cleanup aggiornato

**NON usare il criterio "record più recente"** dello script attuale (che avrebbe scelto A perché updated_at più recente — casualmente giusto).

**Comando corretto (semantico)**:
```bash
python3 scripts/cleanup_production_config_duplicates.py --tenant-id 5e353147-2416-4ef7-aa3f-3e0007435c42 --prefer-id pc-5e353147-2416-4ef7-aa3f-3e0007435c42
```

Con `--prefer-id` forziamo la scelta invece di affidarci all'euristica.

Successivamente, l'utente deve compilare i campi mancanti in A via `/pricing-hub` (o UI equivalente).

**Autorizzazione richiesta prima di procedere**: OK a lanciare `--apply` con `--prefer-id pc-5e353147...` sul preview? (0 rischio su preventivi storici — snapshot immutabili — ma verifica finale che il tenant sia effettivamente Infissi Express demo e non produzione reale)

---

## PARTE 3 — PRODUCTION_FORMULA_ANALYSIS_V1.md — stato

**Il file `Preventivatore 4.0.xlsx` NON è accessibile in questa run**. Ho verificato con `get_assets_tool`:
```
No assets found for job 9236a5d7-8037-4fa7-badc-acd83b877c0e.
```

**Cosa mi serve per produrre il documento completo**:
- Caricare il file `Preventivatore 4.0.xlsx` come asset del job (dal tuo lato), OPPURE
- Un URL diretto scaricabile del file (S3, Dropbox, Google Drive con link pubblico)

**Nel frattempo — bozza di indice per `PRODUCTION_FORMULA_ANALYSIS_V1.md`** (basata sulla tua analisi ricevuta):

1. Sommario e verdetto (il foglio conferma direzione V3: prezzo deriva dal costo)
2. Struttura del foglio (5 schede: Formule / Costo Produzione / Costo Materiale / Tempi / Inserimento dati / Preventivo)
3. Formule per configurazione — dizionario esplicito
   - 1 anta: telaio, rinforzo, anta, componente interno, vetro
   - 2 ante: 6 componenti + vetro doppio + H×5,5/1000 da identificare
   - 3 ante: composizione 1/3 + 2/3 — **APPROVAZIONE RICHIESTA** (2 telai vs 1?)
   - 4 ante: non gestita — **MISSING_TECHNICAL_RECIPE**
4. Costanti hardcoded → variabili tecniche configurabili:
   - `+6` → `welding_allowance_mm`
   - `-70`, `-186`, `-206`, `-307`, `-347` → `frame_reduction_mm`, `sash_reduction_mm`, `glazing_bead_reduction_mm`, ecc.
   - `5,5 €/m`, `7,51 €/m`, `29,5 €/m + 7,49`, `29,5 €/m + 9,84` → componenti da identificare per finestra vs portafinestra
   - `costo orario 180` → `hourly_cost` (VALORE DA CONFERMARE)
   - `moltiplicatore × 3` → `pricing_method=MULTIPLIER, multiplier=3` (versionato)
5. Componenti da mappare in ruoli formali (18 ruoli: FRAME, FRAME_REINFORCEMENT, SASH, SASH_REINFORCEMENT, GLAZING_BEAD, MEETING_STILE, MEETING_STILE_REINFORCEMENT, GLASS, HARDWARE, THRESHOLD, LABOR, ACCESSORY, INSTALLATION, TRANSPORT, DISPOSAL — + 3 nuovi identificati dal foglio)
6. Ambiguità sollevate (righe materiale duplicate, colore non applicato, minimo vetro assente, sfrido non incorporato)
7. Confronto Excel vs `commercial_perimeter` — 6 casi test (finestra 1a/2a/3a + portafinestra 1a/2a/3a)
8. Sezione `BUSINESS_RULES_REQUIRING_CONFIRMATION` con la lista puntuale (10 punti)
9. Modello dichiarativo proposto (componente = `{role, code, quantity_formula, unit_cost_source, applies_when, formula_version, valid_from, valid_to}`)
10. Casi di test e stima aggiornata

**Produrrò il documento completo appena il file Excel è accessibile.** Stimo 1 iterazione dedicata (~4-6h di lavoro dopo lettura celle+formule).

---

## PROSSIMI PASSI (attendo tue decisioni)

1. **Excel**: pubblica il file come asset del job (via UI Emergent) OR condividimi URL scaricabile diretto
2. **Cleanup**: autorizzi il dump JSON completo dei 2 doc `production_config` per confronto finale?
3. **Mapping campo-per-campo**: dopo Excel Analysis (ha bisogno delle formule per completare le colonne "trasformazione" e "rischio perdita")
4. **Cross-review**: pronto quando avremo V3 aggiornata + Formula Analysis + Mapping

**Zero codice modificato. Zero cleanup applicato. Zero migrazione.**

---
