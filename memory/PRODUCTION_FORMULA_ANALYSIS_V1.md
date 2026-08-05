# Panorama Pilot — PRODUCTION FORMULA ANALYSIS V1
**Fonte**: `Preventivatore 4.0.xlsx` (Enerhia Srl, cliente Francesco Viti)  
**Data**: Feb 2026 · Iter 36  
**Scope**: analizzare, formalizzare, NON copiare  
**Cliente conferma richiesta su 10+ punti**

---

## 1 · Sommario e verdetto

Il foglio conferma la direzione V3: **il prezzo commerciale nasce dal costo tecnico di produzione, non da un calcolo perimetrale indipendente**. Il flusso reale è:

```
misure + configurazione
  → quantità per componente (formule per numero ante)
  → costi materiali (€/ml, €/mq, €/pz da listino "Costo Materiale")
  → tempo di produzione (h per tipologia e ante)
  → costo manodopera = tempo × costo_orario
  → costo produzione totale
  → moltiplicatore commerciale × 3 (HARDCODED)
  → prezzo di vendita
```

**Il moltiplicatore ×3 è cablato nella formula** — deve diventare `pricing_method=MULTIPLIER, multiplier=3.0` versionato per tenant.

**8 ambiguità gravi identificate** — richiedono approvazione del PO prima di implementare (vedi §16).

---

## 2 · Struttura del foglio (6 schede)

| Scheda | Contenuto | Note |
|---|---|---|
| Formule | Definizioni di calcolo dimensioni componenti | Manca ferramenta, non chiaro il layout — OCR ha estratto anche errori (`ò-186*2` invece di `L-186*2`) |
| Costo di Produzione | Righe articoli con dimensioni, colore, ante, prezzo singolo, totale | 88 righe reali del preventivo Viti |
| Costo Materiale | Elenco materiali con prezzo unitario | Contiene descrizioni duplicate (Rinforzo telaio appare 2 volte) — vedi §5 |
| Tempi di produzione | Tabella tipologia → tempo (h) | Anomalia: **1 anta=1h, 2 ante=0.75h** (2 ante meno di 1 anta?) — DA CONFERMARE §16 |
| Inserimento dati | Il preventivo operativo (posizione, tipologia, ante, colore, W, H, pezzi, importo, tapparella) | 3 esempi di prodotti aggiuntivi separati (colonna "tapp") |
| Preventivo Definitivo | Documento cliente finale — Subtotale 46199, Adeguamento -2000, Totale offerta scontata 44199 | Include Trasporto e Pratica ENEA come voci standard |

---

## 3 · Formule per configurazione (dizionario esplicito)

### 3.1 · Formule dimensionali (1 anta apribile)

| Componente | Formula Excel (raw) | Formula normalizzata | Significato | Valori con S=3 |
|---|---|---|---|---|
| Telaio | `=L+S*2+H+S*2` | `2*L + 2*H + 4*S` | perimetro esterno + saldatura 4 angoli (S=allowance mm) | L=900,H=1500 → 4812mm |
| Rinforzo telaio (v1) | `=L-108*2+H-108*2` | `2*(L-108) + 2*(H-108)` | perimetro ridotto -108mm/lato | 4368mm |
| Rinforzo telaio (v2, 1 anta) | `=L+-70+S/2+H-70+S*2` (**parziale OCR**) | probabile `2*(L-70) + 2*(H-70)` con offset S | perimetro ridotto -70mm/lato | 4560mm |
| Anta | `=L-206*2+H*208*2` (**errore OCR**: `H*208*2` non ha senso — probabile `H-206*2`) | `2*(L-206) + 2*(H-206)` | perimetro anta ridotto -206mm/lato | 3976mm |
| Componente interno (fermavetro?) | `=ò-186*2+H-186*2` (**errore OCR**: `ò` è probabilmente `L`) | `2*(L-186) + 2*(H-186)` | -186mm/lato | 4056mm |
| Vetro 33.1-16-33.1 (1 anta) | `=L-206+H-206*2` (**dubbia**: probabilmente `(L-206) * (H-206)`) | `(L-206) * (H-206)` | area vetro in mm² | 900,1500 → 694×1294 = 898036 mm² = 0.898 m² |

**⚠️ Nota critica**: 2 formule per il "rinforzo telaio" (`-108` e `-70`) → il foglio ha **doppia riga con nomi identici** ma valori diversi. Serve chiarimento (vedi §16 punto 1).

### 3.2 · Formule dimensionali (2 ante apribile)

| Componente | Formula Excel (raw) | Formula normalizzata | Significato |
|---|---|---|---|
| Telaio (2 ante) | `=[(L-75)/2*+S]*4+H-70+S` (**errore sintassi Excel**) | probabile `[(L-75)/2 + S]*4 + 2*(H-70) + 2*S` | 4 tratti verticali di ante/2 + telaio superiore/inferiore |
| Rinforzo telaio (2 ante) | `=(L-347)/2*4+H-347*4` | `4*((L-347)/2) + 4*(H-347)` = `2*(L-347) + 4*(H-347)` | 2 volte larghezza-347, 4 volte altezza-347 |
| Fermavetro (2 ante) | `=(L-307)/2*4+H-186*4` | `4*((L-307)/2) + 4*(H-186)` = `2*(L-307) + 4*(H-186)` | per 2 specchiature vetro |
| Vetro (2 ante) | `=((L-347)/2*H-206)*2` (dubbia) | `((L-347)/2) * (H-206) * 2` | 2 vetri, ognuno larghezza-347 diviso 2 |
| Componente aggiuntivo | `H × 5.5 / 1000` | `H_m * 5.5 €/ml` | **funzione ignota** — probabile scambio battuta (meeting stile) — vedi §16 punto 2 |

### 3.3 · Formule 3 ante (composizione)

**Non ci sono formule dirette a 3 ante**. Il foglio suggerisce **composizione**: `1/3 (finestra 1 anta) + 2/3 (finestra 2 ante)`.

**⚠️ AMBIGUITÀ GRAVE — vedi §16 punto 3**: significa
- (a) una finestra unica a 3 ante con 1 telaio esterno? oppure
- (b) due finestre accoppiate con 2 telai separati?

Il PO ha esplicitamente chiesto di NON implementare fino a chiarimento.

### 3.4 · Portafinestra vs finestra

**Il foglio distingue tramite lettera colonna Tipologia**: `F` (finestra) vs `pf` / `PF` (portafinestra).

Le differenze rilevate:
- **Tempi diversi** (§4)
- **Costo aggiuntivo**: `H × 29.5 / 1000 + 7.49` (finestra) o `H × 29.5 / 1000 + 9.84` (portafinestra) — **funzione ignota** (vedi §16 punto 4). Possibili significati:
  - `29.5 €/ml` = costo profilo verticale aggiuntivo (soglia? traversa portafinestra?)
  - `+7.49` / `+9.84` = costo fisso ferramenta specifica

### 3.5 · Tabella tempi di produzione (scheda "Tempi")

| Tipologia | Tempo (h) | Note |
|---|---|---|
| Finestra 1 Anta | 1.0 | baseline |
| Finestra 2 Ante | **0.75** | ⚠️ **inferiore a 1 anta!** — richiede conferma §16 punto 5 |
| Portafinestra 1 Anta | 1.0 | uguale a finestra 1 anta |
| Portafinestra 1.5 Anta | 1.0 | tipologia "1.5 ante" non standard |
| Finestra 3 Ante | 1.5 | |
| Portafinestra 3 Ante | 2.3 | |
| (riga senza etichetta) | 3.0 | probabilmente 4 ante o portafinestra 4 ante |

---

## 4 · Costanti hardcoded → variabili tecniche configurabili

Ogni numero magico del foglio deve avere un nome esplicito nel modello dati:

| Valore Excel | Nome proposto | Significato tecnico | Unità |
|---|---|---|---|
| `S=3` (implicito, `S*2=6`) | `weld_allowance_mm` | saldatura per lato telaio | mm |
| `-70` (rinforzo telaio v2) | `frame_reinforcement_reduction_mm` | riduzione perimetro rinforzo | mm |
| `-108` (rinforzo telaio v1) | ⚠️ **duplicato non chiarito** | vedi §16 punto 1 | — |
| `-186` (fermavetro 1a; fermavetro H 2a) | `glazing_bead_reduction_mm` | riduzione fermavetro | mm |
| `-206` (anta e vetro 1a) | `sash_reduction_mm` | riduzione anta 1 anta / vetro | mm |
| `-307` (fermavetro 2a L) | `glazing_bead_2sash_L_reduction_mm` | riduzione fermavetro L per 2 ante | mm |
| `-347` (rinforzo 2a, vetro 2a) | `sash_reinforcement_2sash_reduction_mm` | riduzione rinforzo/vetro 2 ante | mm |
| `-75` (telaio 2a) | `telaio_2sash_L_reduction_mm` | riduzione telaio 2 ante | mm |
| `5.5 €/ml` (2 ante) | `meeting_stile_cost_per_ml`? | scambio battuta? — vedi §16 punto 2 | €/ml |
| `7.51 €/ml` (menzionato PO) | `?` — non trovato nell'estrazione Excel | — | €/ml |
| `29.5 €/ml + 7.49` (finestra) | `threshold_finestra_per_ml + fixed_component_finestra` | vedi §16 punto 4 | €/ml + € fisso |
| `29.5 €/ml + 9.84` (portafinestra) | `threshold_portafinestra_per_ml + fixed_component_portafinestra` | vedi §16 punto 4 | €/ml + € fisso |
| `180.0` (Costo Materiale) | `ferramenta_portafinestra_price` **oppure** `hourly_cost=180 €/h` | ⚠️ **AMBIGUO** — vedi §16 punto 6 | € o €/h |
| `76.0` | `ferramenta_finestra_price` **oppure** `glass_price_per_sqm` | ambiguo — vedi §16 punto 7 | € o €/mq |
| `4.02` `1.52` `2.31` `1.34` (Costo Materiale prime 4 righe) | prezzi profili — mapping componente-per-componente RICHIESTO | €/ml | |
| `29, 35, 46, 57, 65, 73, 82` €/mq (Costo Materiale) | prezzi vetri e/o accessori (7 tipi) — mapping richiesto | €/mq | |
| `40` | ? | conteggio finestre? codice? | — |
| `moltiplicatore = 3` (implicito) | `commercial_multiplier` | markup commerciale | pure number |

---

## 5 · Righe materiale — mapping componente-per-componente RICHIESTO

Il foglio "Costo Materiale" contiene **descrizioni duplicate** e **prezzi separati**. Servirà una tabella condivisa PO ↔ agente:

| Riga # | Descrizione Excel | Prezzo unitario | Unità | Ruolo tecnico (proposto) | ⚠️ Da confermare |
|---|---|---|---|---|---|
| 1 | Telaio | (implicito, formula usa L,H) | €/ml | FRAME | Il prezzo unitario del telaio dove è? deve essere in listino separato |
| 2 | Rinforzo telaio (occorrenza 1) | 4.02 (?) | €/ml | FRAME_REINFORCEMENT | Se `-108` |
| 3 | Rinforzo telaio (occorrenza 2, duplicato) | 1.52 (?) | €/ml | ⚠️ **NON CHIARO** | Duplicato reale o refuso? — §16 punto 1 |
| 4 | Fermavetro | 2.31 (?) | €/ml | GLAZING_BEAD | Da confermare |
| 5 | Vetro 33.1-16-33.1 | 76.0 (?) | €/mq | GLASS (stratificato interno-camera-stratificato esterno) | Verificare che 76 sia il vetro e non la ferramenta |
| 6 | ferramenta | 76.0 (?) | €/pz | HARDWARE_FINESTRA | Se il 76 è ferramenta, allora il vetro ha altro prezzo |
| 7 | ZANZARIERA A RULLO UNIKVER... | 1.34 (?) | €/mq | ACCESSORY | Non è core; è opzione |
| 8+ | Numerosi valori 29, 35, 46, 57, 65, 73, 82 €/mq | vari | €/mq | 7 tipi di vetro? oppure di tapparelle? | Etichette mancanti nell'estrazione — DA CHIARIRE |

**Serve un file dettagliato del PO** con per ogni riga: componente + codice fornitore + prezzo + unità. Senza questo la migrazione dei prezzi non è possibile.

---

## 6 · Modello dichiarativo proposto

Ogni componente di costo diventa **una entry BOM template** con struttura:

```yaml
- component_role: FRAME
  component_code: "5103"
  quantity_formula: "2*L_mm + 2*H_mm + 4*S_mm"
  unit_of_measure: mm
  unit_cost_source: item_pricelist(kind=cost, ref_type=profile, ref_id=<profile_id>, color_id=<X>)
  applies_when: "any"
  formula_version: 1
  valid_from: 2026-02-01
  valid_to: null
- component_role: FRAME_REINFORCEMENT
  component_code: "4133"
  quantity_formula: "2*(L_mm - frame_reinforcement_reduction_mm) + 2*(H_mm - frame_reinforcement_reduction_mm)"
  unit_of_measure: mm
  unit_cost_source: item_pricelist(kind=cost, ref_type=profile, ref_id=<X>)
  applies_when: "any"
  formula_version: 1
- component_role: SASH
  component_code: "12130"
  quantity_formula: "2*(L_mm - sash_reduction_mm) + 2*(H_mm - sash_reduction_mm)"
  applies_when: "number_of_sashes==1 AND window_type=='apribile'"
- component_role: SASH
  component_code: "12130"
  quantity_formula: "4*((L_mm - telaio_2sash_L_reduction_mm)/2 + S_mm) + 2*(H_mm - frame_reinforcement_reduction_mm) + 2*S_mm"
  applies_when: "number_of_sashes==2"
# ...ecc per ogni componente e configurazione
- component_role: MEETING_STILE
  component_code: "?"
  quantity_formula: "H_mm / 1000"  # solo lunghezza H in m
  unit_cost_source: constant_or_config(meeting_stile_cost_per_ml)
  applies_when: "number_of_sashes >= 2"
- component_role: LABOR
  quantity_formula: "lookup_time(window_type, number_of_sashes)"
  unit_of_measure: hour
  unit_cost_source: production_config.hourly_cost
```

**Il motore tecnico esegue in ordine**: BOM → per ogni componente valuta formula → moltiplica per prezzo → aggrega. Nessun `commercial_perimeter` cablato.

---

## 7 · Ruoli formali componente (18 minimi)

Come proposti dal PO + estensioni:
`FRAME, FRAME_REINFORCEMENT, SASH, SASH_REINFORCEMENT, GLAZING_BEAD, MEETING_STILE, MEETING_STILE_REINFORCEMENT, GLASS, HARDWARE, THRESHOLD, LABOR, ACCESSORY, INSTALLATION, TRANSPORT, DISPOSAL, ADDITIONAL_COMPONENT_FIXED, ADDITIONAL_COMPONENT_PER_ML, WASTE`

Il foglio Excel richiede almeno 3 nuovi ruoli oltre alla lista PO:
- `ADDITIONAL_COMPONENT_PER_ML` (per `29.5 €/ml`)
- `ADDITIONAL_COMPONENT_FIXED` (per `+7.49` / `+9.84`)
- `WASTE` (per sfrido, non presente nel foglio ma richiesto dal modello)

---

## 8 · Nessuno zero silenzioso

Il foglio inizia la formula con: **se L o H vuote → 0**. Nel software questa è una violazione del principio audit v1 §Sez4.

**Regola vincolante**: il motore deve emettere errori bloccanti:
```
MISSING_WIDTH  →  code, message, entity, severity=blocking
MISSING_HEIGHT
PRICING_INCOMPLETE  (aggregato)
MISSING_TECHNICAL_RECIPE   (per 4 ante e configurazioni non approvate)
```

Lo zero è ammesso **solo quando è configurato esplicitamente** (es. `additional_declared_zero=True`, `installation_declared_zero=True`).

---

## 9 · Snapshot tecnico + commerciale (V3 §8)

**Doppio snapshot immutabile** per riga preventivo — struttura confermata dalla scheda Excel (i valori "Singolo pezzo" del foglio sarebbero il `final_sale_price` post-moltiplicatore ×3):

**technical_snapshot** contiene: BOM utilizzata, quantità calcolate componente per componente, unit_cost letti dal listino, aggregati (`material_cost`, `glass_cost`, `hardware_cost`, `labor_time`, `hourly_cost`, `labor_cost`, `additional_costs`, `total_internal_cost`) + `calculation_hash`.

**commercial_snapshot** contiene: `pricing_method=MULTIPLIER`, `multiplier=3`, `final_sale_price`, tasse/sconti/promozioni + `calculation_hash`.

Modifica futura del listino costo → **non altera** i preventivi salvati (technical_snapshot immutabile).  
Modifica futura del moltiplicatore → **non altera** i preventivi salvati (commercial_snapshot immutabile).

---

## 10 · Confronto Excel vs codice attuale (`commercial_perimeter.py`)

| Aspetto | Formula Excel | `commercial_perimeter` attuale | Divergenza | Gravità |
|---|---|---|---|---|
| Formula telaio | `2*(L+S) + 2*(H+S)` con S=3 | `external_perimeter = 2*(L + H)` (no allowance) | ⚠️ **Excel aggiunge +4×S**, il motore no | 🔴 CRITICAL — sottostima 12mm |
| Formula rinforzo | 2 varianti (-108 e -70) | Legge da `products.components[].code="rinforzo_telaio"` | ✅ separato ma il motore usa altra formula (perimetro esterno intero, non ridotto) | 🔴 CRITICAL |
| Formula anta | `2*(L-206) + 2*(H-206)` | `sash_perimeter = ext + 2*H*(n-1)` (perimetro anta ≠ perimetro con riduzione) | 🔴 **FORMULA COMPLETAMENTE DIVERSA** | 🔴 CRITICAL |
| Formula 2 ante | Composita con `-347`, `-307`, `-75` | Extra_sashes → `meeting_stile = H*(n-1)` (semplificato) | 🔴 CRITICAL |
| Formula 3 ante | Composizione 1/3 + 2/3 | ⛔ NON GESTITA (MISSING_GLASS_RECIPE) | ok fallback ma no calcolo | 🟠 HIGH |
| Vetro | Area diretta `(L-206) × (H-206)` | Formula da `glass_recipes` structured | ✅ concettualmente uguale | ok se recipe matcha |
| Ferramenta | Prezzo fisso per tipologia F/PF | `body.hardware_kit_price` | 🟠 dipende da configurazione manuale | 🟠 HIGH |
| Manodopera | `time_h × 180 €/h` con tabella tipologia/ante | `time_min/60 × hourly_cost` con production_config | ✅ concettualmente uguale ma valori tempo diversi | 🟡 MEDIUM |
| Moltiplicatore | ×3 fisso | `margin_pct` variabile (interpretato come markup) | 🟠 semantica diversa — vedi audit v1 sez 20 | 🟠 HIGH |
| Colore | Colonna colore NON entra nella formula | `+6% PVC premium` sui componenti | 🟡 divergenza — il foglio potrebbe applicarlo tramite prezzo unitario diverso in listino | 🟡 MEDIUM |
| Sfrido | Non presente | `waste_percentage` in `products.components[]` | 🟠 il costo Excel è teorico, non industriale | 🟠 HIGH |

**Verdetto**: il motore `commercial_perimeter` attuale **NON riproduce** le formule reali del preventivatore Excel. Le divergenze CRITICAL su formula anta / 2 ante / 3 ante sono **strutturali** — il motore va **sostituito** dal nuovo `TechnicalCostResolver` (V3), non refactor.

---

## 11 · Validazione con esempi reali (dal foglio "Costo di Produzione")

Ricostruzione richiesta di 6 casi test:

| Caso | Input dal foglio | Prezzo Excel "Singolo Pezzo" | Motore attuale calcola? | Diff attesa |
|---|---|---|---|---|
| Salotto Finestra 2 ante 1700×1600 | L=1700 H=1600 n=2 F PELLICOLATO | **1452.077** € | ? (probabilmente diverso) | Da misurare in Fase 1 V3 |
| Cucina Finestra 1 anta 750×2500 | L=750 H=2500 n=1 F | **544.125** € | ? | idem |
| Ingresso Portafinestra 2 ante 2300×2500 | L=2300 H=2500 n=2 pf | **1381.599** € | ? | idem |
| Camera Finestra 1 anta 750×1400 | L=750 H=1400 n=1 F | **444.316** € | ? | idem |
| Bagno Finestra 1 anta 1100×1400 | L=1100 H=1400 n=1 F | **1424.001** € (2 pezzi?) | ? | idem |
| Balcone PF 2 ante 2250×2500 | L=2250 H=2500 n=2 pf | **1001.838** € | ? | idem |

**Tolleranza ammessa**: solo arrotondamenti (± 0.05 €). Divergenze maggiori indicano formula sbagliata.

**Il test di validazione va eseguito in Fase 1 V3** su tutti i 6 casi. Il preventivo Enerhia totale è **25202.82 €** (Finestre) + **3312.81 €** (Tapparelle) = **28515.63 €**, poi **× moltiplicatore 3 = 85546.89 €**? Il totale preventivo cliente è **44199 €** post-adeguamento -2000. **Non torna se il moltiplicatore è 3** — potrebbe essere che i 25202.82 sono già post-moltiplicatore. **CHIARIMENTO RICHIESTO** — vedi §16 punto 8.

---

## 12 · Sfrido e barre — non presenti nel foglio

Il foglio Excel calcola **metri lineari teorici** dei profili, **non** include:
- sfrido (barre non tagliate perfettamente)
- kerf (larghezza della lama)
- testa/coda barra (offcuts fissi)
- barre intere acquistate (rounding)
- residui riutilizzabili
- ottimizzazione tagli

**Il costo Excel è un costo teorico**, non industriale.

Il modello nuovo deve separare:
```
net_component_quantity      = formula raw
waste_quantity              = net × waste_pct
gross_component_quantity    = net + waste
bar_consumption             = round_up(gross / bar_length) × bar_length
reusable_remainder          = gross - net (se > min_reusable_scrap_mm)
```

Il costo industriale reale = `bar_consumption × unit_cost` (non `net_quantity × unit_cost`).

---

## 13 · Moltiplicatore commerciale

Il foglio applica: `prezzo_singolo = costo_produzione × 3`.

Nel modello nuovo:
- `pricing_method = MULTIPLIER`
- `multiplier = 3.0`
- **Versionato per tenant**
- **Modificabile senza toccare i preventivi già salvati** (commercial_snapshot immutabile)

Alternative da supportare comunque nel modello (anche se il tenant di partenza usa MULTIPLIER):
- `MARKUP_ON_COST` (`sale = cost × (1 + markup_pct/100)`)
- `TARGET_GROSS_MARGIN` (`sale = cost / (1 - margin_pct/100)`)
- `FIXED_PRICE`

---

## 14 · Struttura motori proposta (ricap V3)

```
TechnicalCostResolver
   ├── BomResolver (formule → quantità)
   ├── PriceResolver (item_pricelists kind=cost → unit_cost)
   ├── LaborResolver (tempi tipologia+ante × hourly_cost)
   └── OUTPUT: TechnicalCostSnapshot { materials_cost, labor_cost, glass_cost, hardware_cost, waste_cost, services_cost, additional_costs, total_internal_cost, calculation_hash }

CommercialPricingService
   INPUT: TechnicalCostSnapshot + CommercialRules
   OUTPUT: CommercialSnapshot { pricing_method, multiplier|markup|margin|fixed, sale_price_before_discount, discount, tax, final_sale_price, calculation_hash }
```

Il vecchio `commercial_perimeter.py` **NON è più chiamato** — le formule cablate diventano BOM template configurabili.

---

## 15 · Casi di test obbligatori (18-step, ripreso V3 §11)

Ogni step con evidenza automatica (pytest o Playwright). Verde solo con **18/18**.

Test aggiuntivi introdotti da questo doc:
- Formula 1 anta: `frame = 2*L + 2*H + 4*3 = 2*L + 2*H + 12` deve produrre exact ml
- Formula 2 ante: composizione con `-75/-347/-307`
- Formula 3 ante: **skippato** finché §16 punto 3 non è risolto (test = `MISSING_TECHNICAL_RECIPE`)
- Moltiplicatore: `sale_price = internal_cost × 3` **verificato su 6 casi reali dal foglio Enerhia**

---

## 16 · `BUSINESS_RULES_REQUIRING_CONFIRMATION` — decisioni PO

**Non implementare nulla finché il PO non risponde a questi 10 punti**:

1. **Doppia riga "Rinforzo telaio"** nel Costo Materiale con differenziali `-108` e `-70`. Sono due componenti diversi (es. rinforzo interno + rinforzo esterno)? È refuso del foglio? Uno dei due è deprecato?
2. **`H × 5.5 / 1000` in formula 2 ante**: cosa rappresenta? Scambio battuta (meeting stile)? Rinforzo verticale? Guarnizione?
3. **Formula 3 ante**: composizione 1/3+2/3 con **quanti telai**? 1 (finestra 3 ante) o 2 (accoppiato)? Se composizione, come si calcola il costo del giunto centrale?
4. **`29.5 €/ml + 7.49` (F) vs `29.5 €/ml + 9.84` (PF)**: quale componente? Traversa portafinestra? Soglia? Serratura? Il `29.5 €/ml` è il profilo, il fisso è la ferramenta di quel profilo?
5. **Tempo Finestra 2 Ante = 0.75h < 1 Anta = 1.0h**: refuso? Semplificazione (2 ante prodotte in serie sono più veloci per pezzo)? Confermare valori corretti.
6. **`180.0` nella scheda "Costo Materiale"**: è il costo orario (`€180/h`) o il prezzo ferramenta portafinestra? La documentazione mostra "Costo Orario" come etichetta ma anche riferimenti a materiale.
7. **`76.0` come prezzo**: è vetro €/mq oppure ferramenta finestra €/pz? Gli altri valori €/mq (29, 35, 46, 57, 65, 73, 82) sono vari tipi di vetro? O tipi di tapparelle?
8. **Totale preventivo Enerhia**: `Subtotale 46199 = 25202.82 finestre + tapparelle + ...` OPPURE `Subtotale = costo × 3`? Se il ×3 è già applicato in "Singolo Pezzo", allora il moltiplicatore va estratto: `544.125 / (costo_teorico) = 3.0`?
9. **Colore Premium (Pellicolato)**: il foglio ha colonna colore ma la formula del costo non la usa. Il +6% PVC è invece nella logica attuale del motore. Applicare o no? Se sì, dove? Sul prezzo Excel dei profili o post-moltiplicatore?
10. **Minimo vetro**: il foglio calcola area reale senza minimo. Applicare o no `min_billable_sqm = 0.5 m²`?

Ulteriori punti tecnici:
- **4 ante**: non gestite → `MISSING_TECHNICAL_RECIPE` come da regola V3
- **Trasporto + Pratica ENEA + Posa in opera**: nel preventivo definitivo sono voci separate incluse (0 € in questo caso). Sono a corpo o dipendono da qualcosa (peso, distanza, superficie)?

---

## 17 · Stima aggiornata (impatto su V3)

Il piano V3 (33-40 gg) resta valido, ma:
- **Fase 1 (modelli+resolver)** aumenta di **+2 gg** per gestire i ruoli aggiuntivi (`ADDITIONAL_COMPONENT_PER_ML`, `ADDITIONAL_COMPONENT_FIXED`, `THRESHOLD`, doppio rinforzo)
- **Fase 2 (migrazione dati)** dipende dalle risposte ai 10 punti §16. Se il PO chiarisce entro 1 settimana, Fase 2 parte come previsto
- **Test di accettazione** aggiornati con i 6 casi reali del preventivo Enerhia (§11)

**Rischio principale**: se il PO non risponde a §16 punto 3 (3 ante), la formula 3-ante rimane **MISSING_TECHNICAL_RECIPE** in produzione. Impatto: preventivi 3-ante NON generabili automaticamente finché il chiarimento arriva.

---

## 18 · Rollback

- Tag git `pre-formula-analysis-v1-2026-02` (implicito, `p1-architectural-audit-v3` è il tag precedente)
- Nessun cambio dati eseguito
- Documento aggiungibile o modificabile senza impatto

---

## 19 · Prossimi passi (ordinati)

1. **PO risponde ai 10 punti §16** (bloccante per Fase 1 V3)
2. **PO conferma 6 casi test §11** (input + prezzo atteso per validazione)
3. **PO condivide il file "Costo Materiale" completo** con mapping riga → componente → codice fornitore
4. **Agente produce**: `A_TO_B_FIELD_MAPPING_V1.md` (mapping campo-per-campo Sistema A → Sistema B, come richiesto dal PO)
5. **Cross-review indipendente** (Claude Opus / Gemini 3 Pro) su V3 + V4 finale + questo Formula Analysis + Mapping
6. **PO approva V4 finale** con conferme punto-per-punto
7. **Inizia Fase 1 V3** (modelli + resolver, 5-7 gg)

**Zero implementazione eseguita in questo doc.** Attende risposte del PO.

---

**Documento chiuso.**
