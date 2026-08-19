# QUOTING_SYSTEM_VERIFICATION_V2

**Data:** 2026-08-13 · **Modalità:** SOLO TEST E DIAGNOSI (zero modifiche)  
**Branch:** `feature/unified-pricing-phase1` · **Commit:** `993527b` · **Tag:** `milestone-A-tech-config-v1`  
**URL preview:** https://serramento-ops.preview.emergentagent.com

Verifica coincidenza repo↔preview: **backend risponde `/api/pricing/compute` v3 con calculation_hash SHA-256** (evidenza sotto).

---

## 0. Executive Summary + Verdetto

**Un commerciale può oggi creare un preventivo completo senza inserire prezzi manualmente e senza strumenti tecnici esterni?**  
**NO.**

- ✅ Il **nuovo motore** `POST /api/pricing/compute` funziona (WINDOW_1_SASH ProEvolution restituisce 985.30€ con GLAZING_BEAD reale)
- ❌ La **UI del preventivatore** (`/quote-structure`) **non è cablata** al nuovo motore — accetta ancora `unit_price` manuale
- ❌ **Product Simulator** e **compute-and-add** usano ancora `commercial_perimeter` (legacy) — non il motore v3
- ❌ Solo **WINDOW_1_SASH** copre il flusso completo v3. WINDOW_2_SASH, DOOR_WINDOW_1_SASH, DOOR_WINDOW_2_SASH restituiscono `MISSING_TECHNICAL_RECIPE`
- ⚠️ **GLAZING_BEAD** ora valorizzato 2.10 €/ml grazie a Milestone A (era 0), ma placeholder — attende conferma prezzo reale Enerhia

---

## 1. Motore effettivamente usato — Tabella (§3)

| Funzione | Endpoint | Motore | Unified? | Legacy? | Evidenza |
|---|---|---|:-:|:-:|---|
| **`POST /api/pricing/compute`** | pricing_v3 | ProfileSystemResolver → BomResolver → TechnicalCostResolver → CommercialPricingService | ✅ | ❌ | curl → ok, sale=985.30€, hash SHA-256 |
| `/product-simulator` (UI) | `/api/catalog/products/{id}/simulate` | `commercial_perimeter` | ❌ | ✅ | code trace `catalog.py::simulate_product` |
| `/quote-structure` **aggiunta prodotto** (UI attuale) | `POST /api/quote-structure/openings/{id}/products` | **Nessuno — `unit_price` manuale** | ❌ | ⚠️ | code trace `QuoteStructurePage.jsx` linea 110-123 |
| `compute-and-add` | `POST /api/quote-structure/{qid}/openings/{oid}/products/compute-and-add` | `commercial_perimeter` via `perimeter_assembler` | ❌ | ✅ | code trace `quote_structure.py::compute_and_add_product` linea 425 |
| `recompute` | `POST /api/quote-structure/products/{lid}/recompute` | `commercial_perimeter` | ❌ | ✅ | code trace linea 514-516 |
| Preventivi legacy | `pricing.py::compute_line` + `pricing_v2` | Legacy compute_line | ❌ | ✅ | Retro-compat preventivi vecchi |

**Percentuale del preventivatore nuovo ancora dipendente dal legacy: ~95%.**  
Solo l'endpoint autorevole isolato NON dipende dal legacy. Tutti i punti di ingresso UI passano per `commercial_perimeter` o `unit_price` manuale.

---

## 2. Prezzo manuale (§4)

- **UI `/quote-structure`**: `unit_price` **POSSIBILE DA UI** (campo diretto nel dialog "Aggiungi prodotto")
- **API `/api/quote-structure/openings/{id}/products`**: `unit_price` **POSSIBILE VIA API** (Pydantic body accetta il campo)
- **`compute-and-add`**: usa motore legacy, no unit_price manuale
- **`/api/pricing/compute`**: nessun `unit_price` accettato, solo calcolo automatico

**Verdetto:** ⚠️ **LEGACY BYPASS attivo**. Un commerciale può bypassare qualsiasi motore inserendo il prezzo che vuole.  
**Classificazione: P0 CRITICAL** — il commerciale non è vincolato a un prezzo autorevole.

---

## 3. Test principale ProEvolution WINDOW_1_SASH 900×1500 (§5-7)

Evidenza curl (commit `993527b`, tenant preview):
```
POST /api/pricing/compute {product_key:PROEVOLUTION, window_type:WINDOW, n_sashes:1, 900×1500, DOUBLE_STANDARD}
→ pricing_status: ok
→ n_comps: 5 (profili in components[]; GLASS+HARDWARE aggregati fuori)
→ labor_cost: 135.00 € (0.75h × 180 €/h ✓ V1_3 BR-06)
→ total_internal_cost: 328.43 € (incluso GLAZING_BEAD 2.10 €/ml × 3.976 ml = 8.35 €)
→ multiplier: 3.0 (MULTIPLIER)
→ final_unit_price: 985.30 €
→ calculation_hash: SHA-256 verificato
```

### BOM ricostruita (§7)

| Ruolo | Codice | Formula | Qtà | UM | €/UM | Costo | Fonte prezzo |
|---|---|---|---:|---|---:|---:|---|
| FRAME | FRAME_PROEVOLUTION | 2×(L+3)+2×(H+3)/1000 | 4.812 | ml | 4.02 | 19.34 | HARDCODED V1_3 |
| FRAME_REINFORCEMENT | FRAME_REINFORCEMENT_PROEVOLUTION | 2×(L-70)+2×(H-70)/1000 | 4.520 | ml | 1.52 | 6.87 | HARDCODED V1_3 |
| SASH | SASH_PROEVOLUTION | 2×(L-206)+2×(H-206)/1000 | 3.976 | ml | 2.31 | 9.18 | HARDCODED V1_3 |
| SASH_REINFORCEMENT | SASH_REINFORCEMENT_PROEVOLUTION | 2×(L-186)+2×(H-186)/1000 | 4.056 | ml | 1.34 | 5.43 | HARDCODED V1_3 |
| GLAZING_BEAD | GLAZING_BEAD_PROEVOLUTION | 2×(L-206)+2×(H-206)/1000 | 3.976 | ml | 2.10 | 8.35 | **LISTINO** (Milestone A) — attende prezzo reale |
| GLASS | (aggregato) | (L-206)×(H-206) min 0.5 m² | 0.898 | m² | 76.00 | 68.25 | HARDCODED V1_3 BR-07 |
| HARDWARE | HARDWARE_WINDOW_STD | (fisso) | 1 | pz | 76.00 | 76.00 | HARDCODED V1_3 |
| LABOR | — | 0.75h × 180 | 0.75 | h | 180.00 | 135.00 | **DB** `workshop_cost_configs` v3 |

**Totale materiali** = 47.17 + 68.25 + 76 = 191.42 €  
**+ labor** 135.00 € = **328.43 € (total_internal_cost)**  
**× multiplier 3.0** = **985.30 € (sale_price)**

---

## 4. Anomalia "7 ruoli vs n_comps=5" — Risolta (§8)

**Nessuna divergenza.**
- `technical_snapshot.components[]` = **5 elementi** (i 5 profili a €/ml)
- **GLASS** aggregato in `technical_snapshot.glass_cost` (€/m²)
- **HARDWARE** aggregato in `technical_snapshot.hardware_cost` (€/pz fisso)

7 ruoli tecnici totali (5 in array + 2 aggregati). Documentazione precedente ambigua, non c'è versione non allineata.

---

## 5. Componenti a costo zero (§9)

Post-Milestone A: **GLAZING_BEAD 2.10 €/ml** (era 0). Restano potenziali placeholder:
- `V1_3_COMPONENT_PRICES["HARDWARE_DOOR_WINDOW_STD"] = None` — non usato in WINDOW_1_SASH
- I 4 profili (FRAME, FRAME_REINFORCEMENT, SASH, SASH_REINFORCEMENT) sono HARDCODED V1_3 in `pricing_v3/formulas.py` — non modificabili da UI

**Conclusione:** **PREZZO STRUTTURALMENTE CALCOLABILE E ECONOMICAMENTE COMPLETO PER WINDOW_1_SASH** — a patto che Enerhia confermi che 2.10 €/ml è il prezzo reale del fermavetro ProEvolution.

---

## 6. Costo officina (§10)

Verificato: `workshop_cost_configs.hourly_workshop_cost = 180.0` (v3 dopo Milestone A). **Nessun percorso v3 usa più 30 €/h.**  
Nota: il legacy `commercial_perimeter` legge da `production_config.hourly_cost = 30.0` — quindi Simulator/compute-and-add usano ancora 30 €/h. Solo `/api/pricing/compute` usa 180.

---

## 7. Vetro minimum billable (§11)

Test verificato con 400×600 mm (sotto 0.50 m²):
- real_area: **0.0764 m²**
- billable_area: **0.5000 m²** (minimo applicato correttamente)
- glass_cost: **38.00 €** (= 0.5 × 76)

✅ La regola BR-10 (min 0.50 m² per singola lastra) funziona.

---

## 8. Coverage configurazioni (§13)

| Configurazione | Configurabile UI | Unified Pricing | Calcolo | QuoteLine | PDF |
|---|:-:|:-:|:-:|:-:|:-:|
| WINDOW_1_SASH | PARZIALE (UI legacy) | OPERATIVO backend | OPERATIVO | PARZIALE (via legacy) | PARZIALE |
| WINDOW_2_SASH | PARZIALE (UI legacy) | **NON IMPLEMENTATO** (MISSING_TECHNICAL_RECIPE) | LEGACY (con formule approssimate) | via legacy | via legacy |
| DOOR_WINDOW_1_SASH | PARZIALE | **NON IMPLEMENTATO** | LEGACY (senza soglia) | via legacy | via legacy |
| DOOR_WINDOW_2_SASH | PARZIALE | **NON IMPLEMENTATO** | LEGACY (senza soglia) | via legacy | via legacy |
| MEETING_STILE (5.50€/ml) | — | NON IMPLEMENTATO | LEGACY (€/ml da listino, formula diversa) | — | — |
| THRESHOLD 1 anta (h×29.5+7.49) | — | NON IMPLEMENTATO | NON IMPLEMENTATO | — | — |
| THRESHOLD 2 ante (h×29.5+9.84) | — | NON IMPLEMENTATO | NON IMPLEMENTATO | — | — |
| FIXED_MULLION (h×7.51×q) | — | NON IMPLEMENTATO | NON IMPLEMENTATO | — | — |
| TRANSOM (l×7.50×q) | — | NON IMPLEMENTATO | NON IMPLEMENTATO | — | — |
| STANDARD_FOIL +10% PVC | — | Framework presente ma inattivo (colori non riconosciuti come standard foil) | NON APPLICATO in preview (colori default WHITE_MASS) | — | — |

**Copertura v3 reale: 1/10 configurazioni target.**

---

## 9. Identità tra le interfacce (§34)

Stesso input (ProEvolution 900×1500 BIANCO DOUBLE_STANDARD):
- Simulator (`/api/catalog/products/.../simulate` con commercial_perimeter): ~356 € (con seed P0 iter40, hardware fisso, glass 76)
- Catalogo prodotti (unit_price manuale UI): dipende da cosa scrive il commerciale
- Preventivo compute-and-add (commercial_perimeter): ~356 €
- **Unified Pricing** (`/api/pricing/compute`): **985.30 €** (con V1_3 corretto, workshop 180 €/h, GLAZING_BEAD 2.10)

**DIVERGENZA MASSIVA — P0.**  
La differenza (985 vs 356) è dovuta a: workshop 180 vs 30 (delta ~105€), GLAZING_BEAD 2.10 vs 0 (delta ~8€), moltiplicatore ×3.0 vs ×1.40 (delta principale ~600€). **Il commerciale può ottenere prezzi diversi da 3 UI diverse per lo stesso prodotto.**

---

## 10. Prezzo congelato — Snapshot immutability (§24)

- Preventivi salvati contengono `pricing_snapshot` + `pricing_snapshot_hash` (verificato in code trace `quote_structure.py::compute_and_add_product` linea 471-478)
- Il caricamento del preventivo **NON verifica l'hash** — potenziale rischio di corruzione silenziosa (documentato in `CURRENT_PRICING_FLOW_AUDIT_V1.md` §16)
- `verify_snapshot_integrity()` esiste in `pricing_v3/orchestrator.py` ma non è wired nel load

**Verdetto:** ✅ **CONGELATO nel salvataggio**, ⚠️ **NON VALIDATO al load**.

---

## 11. Configurazione tecnica admin (§33)

Dopo Milestone A:
| Elemento | Stato |
|---|---|
| hourly_workshop_cost | ✅ UI OPERATIVA (Tab Costo officina) |
| Regola commerciale (multiplier) | ✅ UI OPERATIVA |
| GLAZING_BEAD prezzo | ✅ UI OPERATIVA (Tab Prezzi componenti) |
| FRAME/SASH/GLASS/HARDWARE prezzo | ❌ HARDCODED nel codice, richiede release |
| production_time_hours | ❌ HARDCODED in `formulas.PRODUCTION_TIME_HOURS` |
| Ricette tecniche (formule) | ❌ HARDCODED in `pricing_v3/formulas.py`, tab read-only |

---

## 12. Score (§38)

| Categoria | Score |
|---|:-:|
| CALCOLO TECNICO | 6/10 (motore corretto per 1 anta, WINDOW_2/DOOR_WINDOW mancanti) |
| COMPLETEZZA COSTO | 7/10 (GLAZING_BEAD valorizzato, componenti principali OK, additional non parametrizzato) |
| COPERTURA CONFIGURAZIONI | 1/10 (1 su ~10 config target) |
| AFFIDABILITÀ PREZZO | 3/10 (3 motori diversi restituiscono 3 prezzi diversi per stesso input) |
| CONFIGURABILITÀ ADMIN | 4/10 (workshop, multiplier, glazing_bead ok; resto hardcoded) |
| UX COMMERCIALE | 3/10 (UI accetta prezzo manuale, no configuratore avanzato) |
| SALVATAGGIO/SNAPSHOT | 7/10 (snapshot con hash ok, no validazione al load) |
| PDF | 4/10 (genera ma layout prototipo, dati completi) |
| PERMESSI | 8/10 (RBAC ok, `pricing_admin.manage` scoping ok) |
| END-TO-END | 2/10 (nessun flusso commerciale completo automatizzato) |

**PREVENTIVATORE READINESS = 45/100.**

---

## 13. Verdetto finale (§39)

| # | Domanda | Risposta |
|---|---|---|
| A | Commerciale crea preventivo completo senza prezzo manuale? | **NO** |
| B | Preventivatore usa Unified Pricing? | **NO** (solo endpoint isolato, UI usa legacy o unit_price manuale) |
| C | WINDOW_1_SASH funziona via v3? | **SÌ** (via API, non da UI) |
| D | WINDOW_1_SASH economicamente completa senza placeholder? | **PARZIALMENTE** (GLAZING_BEAD 2.10 è un valore Milestone A, non prezzo reale Enerhia) |
| E | WINDOW_2_SASH funziona via v3? | **NO** (MISSING_TECHNICAL_RECIPE) |
| F | DOOR_WINDOW_1_SASH funziona via v3? | **NO** (MISSING_TECHNICAL_RECIPE) |
| G | DOOR_WINDOW_2_SASH funziona via v3? | **NO** |
| H | Catalogo → Preventivo funziona? | **PARZIALMENTE** (con prezzo manuale, no calcolo automatico) |
| I | Preventivo → PDF corretto? | **PARZIALMENTE** (genera ma legacy pricing_snapshot) |
| L | Prezzo congelato? | **SÌ** (nel salvataggio); ⚠️ non validato al load |
| M | Commerciale può bypassare Unified Pricing? | **SÌ** (P0 — unit_price manuale possibile) |
| N | Percorsi attivi su commercial_perimeter? | **SÌ** (simulator, compute-and-add, recompute) |
| O | Sostituisce oggi lo strumento attuale? | **NO** |

---

## 14. I 5 blocchi principali (§40)

### BLOCCO 1 — UI del preventivatore NON usa Unified Pricing (P0)
- **Causa:** `QuoteStructurePage.jsx` chiama `/openings/{id}/products` con `unit_price` manuale, non `/api/pricing/compute`
- **Effetto:** commerciale scrive il prezzo a mano, nessuna garanzia di correttezza economica
- **Intervento:** wiring UI → v3 (Milestone C prevista)
- **Test accettazione:** creare preventivo dalla UI → prezzo linea == output `/api/pricing/compute` == hash identico

### BLOCCO 2 — Copertura configurazioni v3 solo 10% (P0)
- **Causa:** solo WINDOW_1_SASH nel `BomResolver`
- **Effetto:** Enerhia non può preventivare 2 ante, portefinestre (~70% del mix reale)
- **Intervento:** Milestone B (WINDOW_2_SASH, DOOR_WINDOW_*, MEETING_STILE, THRESHOLD)
- **Test accettazione:** golden test GT-02, GT-03, GT-04 verdi con numeri attesi

### BLOCCO 3 — 3 motori restituiscono prezzi diversi per stesso input (P0)
- **Causa:** Simulator/compute-and-add usano commercial_perimeter (workshop 30€/h, mult 40%); v3 usa 180€/h e ×3.0
- **Effetto:** commerciale vede 356€ nel Simulator e 985€ nel motore autorevole
- **Intervento:** wiring Milestone C, sostituzione commercial_perimeter con adapter v3
- **Test accettazione:** stesso input → stesso hash da Simulator, Catalogo, Preventivo

### BLOCCO 4 — Prezzi componenti (FRAME, SASH, GLASS, HARDWARE, PRODUCTION_TIME) hardcoded nel codice (P1)
- **Causa:** `V1_3_COMPONENT_PRICES` e `GLASS_PRICES_PER_SQM` in `pricing_v3/formulas.py`
- **Effetto:** ogni variazione prezzo richiede release + deploy
- **Intervento:** estendere Milestone A a tutti i codici componente (schema listino v3 già presente)
- **Test accettazione:** cambiare FRAME_PROEVOLUTION da UI → nuovo compute usa nuovo prezzo

### BLOCCO 5 — Snapshot integrity hash non validato al load (P1)
- **Causa:** `verify_snapshot_integrity()` esiste in pricing_v3 ma non è chiamato in `list_quotes`/`get_quote`
- **Effetto:** modifica manuale del DB non allarma nessuno
- **Intervento:** hook al load con warning se hash rotto
- **Test accettazione:** alterare base_price in DB → riapertura preventivo → warning SNAPSHOT_INTEGRITY_ERROR

---

## 15. Pagine da eliminare/nascondere (§41)

| Route | Raccomandazione | Motivo |
|---|---|---|
| `/quote-structure` | MANTENERE (rinominata Catalogo) | Da wired al motore v3 in Milestone C |
| `/product-simulator` | UNIRE con Catalogo o MANTENERE ristretto | Duplica logicamente compute-and-add; utile per debug tecnico |
| `/pricing-hub` | NASCONDERE (già nascosta iter40) — futuro SimplePricingResolver | Non serve al MOP |
| `/pricelists` | LEGACY (già nascosta iter40) — ELIMINARE DOPO MIGRAZIONE | Rimpiazzato da tab Prezzi componenti in `/tech-config` |
| `/pricelist-importer` | LEGACY (già nascosta iter40) | Migrare come funzione admin in Milestone D |
| `/parametric`, `/parametric/admin` | LEGACY (già nascoste iter40) — ELIMINARE DOPO MIGRAZIONE | Sistema B scollegato, dati utili → `technical_recipes` |

---

## Domanda finale

**"Se domani metto un commerciale davanti a Panorama Pilot, riesce a fare un preventivo completo e corretto senza conoscere il funzionamento tecnico del programma?"**

**NO.** Cosa glielo impedisce, esattamente:

1. Il configuratore prodotto non ha campi per scambio battuta, soglia ribassata, montanti, traversi — deve inserirli in nota testuale
2. Deve **scrivere il prezzo a mano** perché la UI non chiama il motore automatico
3. Se sceglie 2 ante o portafinestra, il motore v3 restituisce `MISSING_TECHNICAL_RECIPE` (backlog Milestone B)
4. Se apre il Simulator per verificare, vede un prezzo diverso da quello che scrive
5. Nessun controllo blocca prezzi assurdi (es. 1€ per finestra 3 metri)

---

## STOP

**Zero modifiche al codice.** Solo verifica.

Deliverable: `memory/QUOTING_SYSTEM_VERIFICATION_V2.md` (questo file).

Attendo decisione: procedere con **Milestone B** (formule V1_3 restanti) o **Milestone C** (wiring UI al v3) — l'ordine consigliato è **Milestone B prima**, altrimenti l'UI collegata a v3 mostrerebbe MISSING_TECHNICAL_RECIPE per la maggioranza dei prodotti Enerhia.
