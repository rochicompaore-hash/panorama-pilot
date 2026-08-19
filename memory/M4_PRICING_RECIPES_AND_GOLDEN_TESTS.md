# M4 PRICING RECIPES & GOLDEN TESTS — Enerhia Operating Core

**Data:** 2026-02-19 · **Branch:** `feature/enerhia-operating-core-v1`
**Preview:** https://serramento-ops.preview.emergentagent.com
**Stato milestone:** M2 `E2E_READY` (source-of-truth) · M3 `TECHNICAL_TEST_READY` (BUSINESS_GOLDEN = **FAIL** — delta 28.34 € da chiudere con listino Enerhia reale) · M4 `E2E_READY` (5 configurazioni, 7/7 test verdi)

---

## 1. Delta 28.34 € — Analisi riga-per-riga (GT-REAL 1200×1400)

Panorama V3 calcola i seguenti valori (verificati dal pytest):

| Ruolo | Panorama qty | Panorama unit € | Panorama total € |
|---|---:|---:|---:|
| FRAME              | 5.212 ml | 4.02 | **20.95** |
| FRAME_REINFORCEMENT | 4.920 ml | 1.52 | **7.48** |
| SASH               | 4.376 ml | 2.31 | **10.11** |
| SASH_REINFORCEMENT  | 4.456 ml | 1.34 | **5.97** |
| GLAZING_BEAD       | 4.376 ml | 2.10 | **9.19** ← *placeholder NEEDS_PO_CONFIRMATION* |
| **MATERIAL SUB-TOTAL** |  |  | **53.70** |
| GLASS              | 1.1868 m² | 76.00 | **90.20** |
| HARDWARE           | 1 pz | 60.00 | **60.00** *(era 76 — corretto)* |
| LABOR              | 0.75 h | 180.00 | **135.00** |
| FOIL SURCHARGE     | — | — | **0.00** *(WHITE_MASS)* |
| **TOTAL INTERNAL** |  |  | **338.90** |

**Target Excel Enerhia (approssimativo):** 310.56 € · **Delta: +28.34 €**

### Quantità Panorama vs Formule V1_3 approvate

| Ruolo | Formula V1_3 (docs) | Applicata da Panorama | Coincide? |
|---|---|---|:-:|
| FRAME              | `2·(L+S) + 2·(H+S)` con S=3 | `2·(1200+3) + 2·(1400+3) = 5212 mm` = 5.212 ml | ✅ |
| FRAME_REINFORCEMENT | `2·(L-70) + 2·(H-70)` | `2·1130 + 2·1330 = 4920 mm` = 4.920 ml | ✅ |
| SASH               | `2·(L-206) + 2·(H-206)` | `2·994 + 2·1194 = 4376 mm` = 4.376 ml | ✅ |
| SASH_REINFORCEMENT  | `2·(L-186) + 2·(H-186)` | `2·1014 + 2·1214 = 4456 mm` = 4.456 ml | ✅ |
| GLAZING_BEAD        | perimetro anta apribile | 4.376 ml | ✅ |
| GLASS              | `(L-206) × (H-206)` con min 0.50 m² | 994×1194 = 1.186836 m² | ✅ |
| HARDWARE           | Regola `(WINDOW, 1) → 60 €` | 60 € (letto da `hardware_rules`) | ✅ |
| LABOR              | 0.75 h × 180 €/h | 135 € (letto da `production_time_configs` × `workshop_cost_configs`) | ✅ |

**Conclusione:** le **quantità** e le **formule** sono corrette. Il problema è **esclusivamente il valore economico** di alcuni componenti.

### Origine specifica del delta 28.34 €

I prezzi unitari attualmente nel motore v3 sono i valori "V1_3_COMPONENT_PRICES" tratti dal file `PRODUCTION_FORMULA_ANALYSIS_V1_3.md`:
```
FRAME               4.02 €/ml
FRAME_REINFORCEMENT 1.52 €/ml
SASH                2.31 €/ml
SASH_REINFORCEMENT  1.34 €/ml
GLAZING_BEAD        2.10 €/ml  ← PLACEHOLDER
```

Il target Excel ≈ 310.56 € corrisponderebbe a materiali ≈ **25.36 €** vs Panorama **53.70 €** (delta materiali 28.34 €, che è **esattamente** il delta totale poiché GLASS, HARDWARE, LABOR coincidono).

Le due possibili cause **sono di listino, non di formula**:
1. **Prezzi profili V1_3 di riferimento ≠ listino cliente Enerhia reale.** I profili PVC ProEvolution potrebbero avere prezzi unitari inferiori nel listino Enerhia rispetto ai valori V1_3 documentati.
2. **GLAZING_BEAD 2.10 €/ml è placeholder** — se il listino Enerhia lo assegna a 0 (o valore diverso), il delta materiali si sposta.

### Azione richiesta al cliente per chiudere M3 BUSINESS_GOLDEN
- Fornire il listino ufficiale Enerhia per: FRAME_PROEVOLUTION, FRAME_REINFORCEMENT_PROEVOLUTION, SASH_PROEVOLUTION, SASH_REINFORCEMENT_PROEVOLUTION, GLAZING_BEAD_PROEVOLUTION.
- **Nessuna modifica codice necessaria** — l'admin li inserirà da `/tech-config` → Prezzi componenti.
- Quando il delta scenderà entro tolleranza approvata, il pytest continuerà a passare e la milestone potrà passare a `BUSINESS_GOLDEN = PASS`.

---

## 2. Source-of-Truth Matrix (Milestone 2)

| Dato | UI editable | Collection / API | V3 legge da DB? | Hardcoded? |
|---|:-:|---|:-:|:-:|
| FRAME cost              | ✅ | `item_pricelists` / `/tech-config/component-prices` | ✅ | fallback V1_3 (documentato) |
| FRAME_REINFORCEMENT cost | ✅ | idem | ✅ | fallback V1_3 |
| SASH cost               | ✅ | idem | ✅ | fallback V1_3 |
| SASH_REINFORCEMENT cost  | ✅ | idem | ✅ | fallback V1_3 |
| GLAZING_BEAD cost       | ✅ | idem | ✅ | fallback 2.10 placeholder |
| MEETING_STILE cost      | ✅ | idem (code=`MEETING_STILE_PROEVOLUTION`) | ✅ | fallback 5.50 €/ml |
| THRESHOLD variable cost | ✅ | idem (code=`REDUCED_THRESHOLD_PROEVOLUTION`) | ✅ | fallback 29.50 €/ml |
| THRESHOLD fixed part    | ⚠️ | Costante in ricetta (7.49/9.84 €) | ✅ | Determinato dal recipe_code — configurable via technical_recipes future |
| FIXED_MULLION cost      | ✅ | idem (code=`FIXED_MULLION_PROEVOLUTION`) | ✅ | fallback 7.51 €/ml — quantità richiede input `mullions_count` (M5) |
| TRANSOM cost            | ✅ | idem (code=`TRANSOM_PROEVOLUTION`) | ✅ | fallback 7.50 €/ml — quantità richiede input `transoms_count` (M5) |
| GLASS prices (4 tipi)   | ✅ | `glass_price_configs` / `/tech-config/glass-prices` | ✅ | NO — solo fallback V1_3 documentato |
| Glass min billable      | ✅ | idem | ✅ | fallback 0.5 m² |
| HARDWARE (6 regole)     | ✅ | `hardware_rules` / `/tech-config/hardware-rules` | ✅ | NO |
| PRODUCTION TIME (7 ric.)| ✅ | `production_time_configs` / `/tech-config/production-times` | ✅ | fallback V1_3 |
| WORKSHOP COST           | ✅ | `workshop_cost_configs` | ✅ | NO |
| FOIL surcharge %        | ⚠️ | Costante 10% + set colori in codice | ✅ | Set colori STANDARD_FOIL_COLORS in formulas.py — refactor in DB nella prossima iter |
| COMMERCIAL MULTIPLIER   | ✅ | `commercial_pricing_rules` | ✅ | NO |
| TECHNICAL RECIPE        | ⚠️ | `technical_recipes` | ✅ | UI read-only oggi — CRUD nel backlog |

**Conclusione M2:** tutti i costi principali sono `UI EDITABLE = YES · V3 READS FROM DB = YES`. I fallback V1_3 restano come **safety net** documentata (attivi solo se l'admin non ha ancora popolato l'entry), non come "hardcoded". Per considerare M2 **completamente `APPROVED`**, mancano:
- CRUD ricette tecniche (oggi read-only)
- Configurabilità del set colori pellicolati (oggi in codice)
- Input `mullions_count` / `transoms_count` nel PricingRequest (arriverà con M5 quando la UI configuratore verrà connessa)

---

## 3. Ricette M4 implementate

### `WINDOW_1_SASH` (GT-W1 · 1200×1400)
Componenti: FRAME · FRAME_REINFORCEMENT · SASH · SASH_REINFORCEMENT · GLAZING_BEAD (+ GLASS aggregato + HARDWARE + LABOR).
Hardware: **60 €** · Time: **0.75 h** · Labor: **135 €** · Total internal: **338.90 €**.

### `WINDOW_2_SASH` (GT-W2 · 1500×1400)
Componenti: 5 profili + **MEETING_STILE** (`H/1000 × 5.50 €/ml` → 1.4 ml × 5.50 = **7.70 €**).
Hardware: **80 €** · Time: **1.00 h** · Labor: **180 €** · Total internal: **537.10 €**.

### `DOOR_WINDOW_1_SASH` (GT-DW1 · 900×2200)
Componenti: 5 profili + **THRESHOLD** (`H/1000 × 29.50` → 2.2 × 29.50 = **64.90 €**) + **THRESHOLD_FIXED** (`7.49 €`).
Hardware: **75 €** · Time: **1.00 h** · Labor: **180 €** · Total internal: **497.55 €**.

### `DOOR_WINDOW_2_SASH` (GT-DW2 · 1600×2200)
Componenti: 5 profili + **MEETING_STILE** + **THRESHOLD** (variabile + **fixed 9.84 €**).
Hardware: **90 €** · Time: **1.50 h** · Labor: **270 €** · Total internal: **908.37 €**.

### `VASISTAS_ONLY_1_SASH` (GT-VAS · 800×600)
Componenti: 5 profili (senza meeting stile né threshold). Vetro sotto minimo → **billable 0.50 m² = 38 €**.
Hardware: **40 €** (isolato: non si applica alle normali finestre anta-ribalta) · Time: **0.75 h** · Labor: **135 €** · Total internal: **239.60 €**.

### `SLIDING_DOOR_WINDOW_N_SASH`
- Hardware regola: **380 €/anta** (per_sash=True) letta da `hardware_rules` per opening_type `SLIDING_DOOR_WINDOW`.
- **Formula geometrica non implementata** (backlog M4B): fail-closed su `MISSING_TECHNICAL_RECIPE`.
- `NEEDS_PO_CONFIRMATION` per la BOM completa scorrevole.

### Formule extra V1_3 disponibili nel motore (attivabili in M5 al ricevimento di `mullions_count`/`transoms_count`)
- `FIXED_MULLION`: `H/1000 × 7.51 × quantity`
- `TRANSOM`: `L/1000 × 7.50 × quantity`

---

## 4. Foil Surcharge — Test WALNUT

Configurazione WINDOW_1_SASH 1200×1400 con colore interno/esterno = **WALNUT** (colore pellicolato standard).

Formula V1_3: `foil = 0.10 × Σ(costi PVC eleggibili)` dove eleggibili sono {FRAME, SASH, GLAZING_BEAD, MEETING_STILE, FIXED_MULLION, TRANSOM}.

- FRAME 20.952 + SASH 10.109 + GLAZING_BEAD 9.190 = **40.25 €**
- FOIL = **4.03 €** (10%)
- NON incluso: FRAME_REINFORCEMENT, SASH_REINFORCEMENT (metallici), GLASS, HARDWARE, LABOR, servizi.

Test pytest `test_foil_surcharge_walnut` verifica esplicitamente che foil > 0 ma < 5 (non è tutto il materiale).

---

## 5. Fail-Closed rigorosamente applicato

Codici errore attivi (nessun fallback silenzioso, nessun `0 €`, nessun default nascosto):

| Codice | Attivato quando | Hint UI |
|---|---|---|
| `MISSING_TECHNICAL_RECIPE` | recipe_code non seedato per il tenant | `/tech-config/ricette` |
| `MISSING_PROFILE_SYSTEM` | recipe senza profile_system_id | `/tech-config/ricette` |
| `MISSING_COMPONENT_PRICE` | componente non nel listino tenant né in fallback V1_3 | `/tech-config/component-prices` |
| `MISSING_GLASS_PRICE` | glass_type non in `glass_price_configs` né in fallback | `/tech-config/vetri` |
| `MISSING_HARDWARE_RULE` | combinazione (opening_type, n_sashes) non definita | `/tech-config/ferramenta` |
| `MISSING_PRODUCTION_TIME` | recipe_code non in `production_time_configs` né in fallback | `/tech-config/tempi-produzione` |
| `MISSING_WORKSHOP_COST` | workshop_cost_configs vuoto | `/tech-config/costo-officina` |
| `MISSING_COMMERCIAL_MULTIPLIER` | commercial_pricing_rules vuoto | `/tech-config/regola-commerciale` |
| `INVALID_GEOMETRY` | width_mm o height_mm ≤ 0 | Configurazione prodotto |

**Nessun path riporta 0 € come costo tecnico valido.**

---

## 6. Discount Guard preparato (Milestone 2.14 · Servizi & Preventivo)

Endpoint `POST /api/simple-services/discount-guard` calcola:
```json
{
  "list_price": 150.00,             // customer_sale_price
  "quantity": 1,
  "discount": 15.00,
  "net_sale_price_unit": 135.00,
  "net_sale_price_total": 135.00,
  "override_required": true,        // se net < internal_reference_price
  // Visibili solo con permesso pricing_admin.manage:
  "internal_reference_price": 130.00,
  "remaining_discount_room": 5.00
}
```

Sarà collegato al motore preventivo in M5.

---

## 7. Placeholders / NEEDS_PO_CONFIRMATION residui

| ID | Elemento | Stato | Come si chiude |
|---|---|---|---|
| B1 | Prezzo GLAZING_BEAD_PROEVOLUTION | 2.10 placeholder | UI: `/tech-config/component-prices` |
| B2 | Prezzi profili V1_3 vs listino Enerhia | delta 28.34 € | UI: `/tech-config/component-prices` |
| B3 | Ricetta 3-ante telaio unico | fail-closed | Business rule + ricetta seed |
| B4 | Codici fornitore componenti | FRAME 5103, SASH 12130; altri `NEEDS_SUPPLIER_CODE_CONFIRMATION` | Anagrafica fornitori (M12) |
| B5 | Lead time BICOLOR | `NEEDS_PO_CONFIRMATION` | Business rule commerciale |
| B6 | Clausole contratto ufficiali | `WAITING_FOR_PO_CONTRACT_TEMPLATE` | Fornitura contratto Enerhia |
| B7 | Servizi logistica CARICO/TRASPORTO/SCARICO | `PRICING_RULE_TO_DEFINE` | Business rule |
| B8 | Sostituzione accessori (unità PER_INTERVENTION o PER_ITEM) | `NEEDS_PO_CONFIRMATION` | Chiarimento cliente |
| B9 | SLIDING_DOOR_WINDOW formula geometrica | Non implementata (solo hardware) | V1_3 formula scorrevole |
| B10 | Ricetta 3/4 ante fittizia (INSTALL_WINDOW_4_SASH) | Servizio seedato, formula tecnica assente | Fornire ricetta |

---

## 8. Test suite

| Test | File | Casi | Status |
|---|---|---|---|
| Golden Test M3 (GT-REAL) | `tests/test_golden_m3_v3.py` | 3 | ✅ PASS |
| Golden Tests M4 | `tests/test_golden_m4_recipes.py` | 7 (GT-W1, GT-W2, GT-DW1, GT-DW2, GT-VAS, FOIL, HARDWARE_SOURCE) | ✅ PASS |
| **TOTALE** | | **10** | **✅ 10/10** |

Comando: `cd /app/backend && python3 -m pytest tests/test_golden_m3_v3.py tests/test_golden_m4_recipes.py -o addopts="" -s`

---

## 9. Vincoli Master Plan rispettati

- ✅ Nessun costo hardcoded per HARDWARE (60 €, non più 76)
- ✅ Prezzi V1_3 restano come *fallback documentato* per NEEDS_PO_CONFIRMATION, non come override forzato
- ✅ Delta economico spiegato riga-per-riga (quantities corrette, listino da confermare)
- ✅ Fail-closed su tutte le combinazioni non seedate (nessun `0 €`)
- ✅ Nessuna migrazione distruttiva
- ✅ Snapshot congelato preservato (preventivi storici invariati)
- ✅ Preview only, nessuna pubblicazione

---

## 10. Autorizzazione a procedere M5?

Secondo il criterio del Master Plan (§27):
- WINDOW_1_SASH: BOM valida + hardware corretto + glass corretto + labor corretto + snapshot + hash → ✅
- WINDOW_2_SASH: idem + MEETING_STILE ✅
- DOOR_WINDOW_1_SASH: idem + THRESHOLD (var+fixed) ✅
- DOOR_WINDOW_2_SASH: idem + MEETING_STILE + THRESHOLD ✅
- VASISTAS_ONLY: BOM + hardware 40 € ✅

Il **delta economico residuo è esclusivamente dovuto a listini `NEEDS_PO_CONFIRMATION`**. Come da Master Plan §21, questo permette classificazione `TECHNICALLY_IMPLEMENTED · ECONOMICALLY_NOT_VALIDATED`.

**Prossima milestone (M5)** può iniziare (Catalogo Prodotti + Preventivatore commerciale unificato → `POST /api/pricing/compute`), ma con etichetta "prezzi non ancora validati economicamente" fino alla chiusura del delta.

**STOP fino al collaudo utente del delta economico.**
