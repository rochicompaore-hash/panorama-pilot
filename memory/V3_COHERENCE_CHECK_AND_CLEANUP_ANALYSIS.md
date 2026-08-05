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

## PARTE 2 — Confronto puntuale duplicati `production_config`

**Nota metodologica**: come richiesto, il criterio "record più recente" NON è sufficiente. Confronto campo-per-campo, uso reale nel codice, riferimenti snapshot.

**Stato DB (verificato ora)**: la query mostra i doc esistenti. Vista tenant PanoramaPilot esistono 2 doc di `production_config`. Struttura confrontata (già raccolta iter 30 audit v1):

| Campo | Doc A (`pc-*`) | Doc B (`prodcfg-*`) | Fonte / significato | Ultima modifica | Uso codice | Ref snapshot | Scelta proposta | Motivazione |
|---|---|---|---|---|---|---|---|---|
| `_id` | `pc-5e353147...` | `prodcfg-5e353147...` | ID doc | A: 2026-07-31 22:00:51 · B: 2026-07-31 21:15:23 | `catalog_service.get_production_config` fa `find_one` per `tenant_id` (non deterministico oggi, prende primo che restituisce l'index) | 0 quote referenziano esplicitamente il `_id` (snapshot cattura valori non ID) | **Tenere A** (`pc-*`) | Il prefix `pc-` è quello nuovo introdotto in area catalog (post audit v1). Il `prodcfg-*` è il legacy pre-refactor |
| `tenant_id` | uguale | uguale | scope tenant | uguale | filtro tenant | — | — | — |
| `hourly_cost` | Da verificare | Da verificare | €/h manodopera | — | letto da `perimeter_assembler` | usato in `pricing_snapshot.labor_cost` (valore, non ref) | **Verificare uguaglianza**. Se A=None e B=30 → tenere B; se A=30 e B=None → tenere A | Non si può ancora decidere senza confronto valore-per-valore |
| `production_time_default_minutes` | idem | idem | tempo default manodopera | — | idem | idem | idem | idem |
| `default_margin_pct` | idem | idem | markup applicato al costo | — | usato da motore commerciale | catturato nello snapshot (audit v1 sez 20 markup vs margine) | Tenere quello **usato** — verificare quale il tenant sta usando in produzione | Cambia il prezzo dei prossimi preventivi |
| `default_glass_price_per_sqm` | Post BUG-03 fix: `None` | Legacy: potrebbe avere 76.0 | €/m² vetro fallback | audit v1 BUG-03 ha rimosso i default silent | letto da perimeter_assembler | valore assoluto in snapshot | Tenere quello con valore **esplicito valorizzato** dal tenant | Se A=None e B=76 → il valore utile è B; se A=76 (ancora legacy) e B=76 → equivalenti |
| `default_glass_min_sqm` | idem BUG-03 | idem | m² minimo fatturabile | — | idem | idem | idem | idem |
| `premium_pvc_surcharge_pct` | 6.0 | 6.0 | +6% PVC premium | probabile uguale | motore commerciale | idem | equivalenti | Documentato standard |
| `default_bar_length_pvc_mm` | 6500 | 6500 | mm barra PVC | uguale | motore commerciale | idem | equivalenti | standard |
| `default_bar_length_reinforcement_mm` | 6000 | 6000 | mm barra acciaio | uguale | motore | idem | equivalenti | standard |
| `fixed_window_time_minutes` / `one_sash_time_minutes` / ecc. | Da verificare presenza | Da verificare presenza | tempi per tipologia | — | motore (via `prod_time_field_map`) | valore in snapshot | Tenere quello **valorizzato** per più tipologie | Se A ha solo default e B ha per-tipologia → tenere B |
| `created_at` | 2026-07-31 22:00 | 2026-07-31 21:15 | audit | — | — | — | — | — |
| `updated_at` | 2026-07-31 22:00 | 2026-07-31 21:15 | audit | — | — | — | — | — |
| `updated_by` | Da verificare | Da verificare | audit | — | — | — | Tenere il più recente per continuità audit trail | — |

### Verdetto cleanup

- **Nessuna quote referenzia `production_config._id` esplicitamente** → i valori sono già catturati nel `pricing_snapshot` dei preventivi. **Cancellare il doc "perdente" NON tocca i preventivi storici** (sono immutabili grazie al snapshot).
- Il criterio raccomandato è **NON "più recente"** ma **"più valorizzato"**: teniamo il doc che ha più campi popolati (specialmente tempi per tipologia e prezzi vetro).
- **Serve un dump JSON dei 2 doc completi** prima di decidere. Lo script `cleanup_production_config_duplicates.py --apply` **NON va lanciato** finché non hai visto il dump e approvato quale record tenere. Il dump lo produco in iterazione dedicata se lo autorizzi.
- **Autorizzazione richiesta**: dammi luce verde a produrre il dump JSON side-by-side dei 2 doc per una decisione finale caso-per-caso.

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
