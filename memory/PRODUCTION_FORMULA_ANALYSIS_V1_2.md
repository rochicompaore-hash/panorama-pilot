# PRODUCTION FORMULA ANALYSIS V1.2 — Regole di business confermate
**Sostituisce**: `PRODUCTION_FORMULA_ANALYSIS_V1.md` (iter 36)  
**Data**: Feb 2026 · Iter 37  
**Autorità**: Product Owner (Enerhia Srl / Infissi Express)  
**Scope**: business rules confermate. Zero implementazione.

---

## CHANGELOG (V1 → V1.2)

| BR | V1 stato | V1.2 stato | Decisione PO |
|---|---|---|---|
| BR-01 | doppia riga "Rinforzo telaio" `-108` vs `-70` | ⏳ APERTA | non ancora risolta (codice reale fornitore) |
| BR-02 | `H × 5.5 / 1000` ambiguo | ✅ RISOLTA | scambio battuta (`MEETING_STILE`, 5.50 €/ml) |
| BR-03 | geometria 3 ante | ⏳ APERTA | attende conferma (telaio unico vs composizione 1+2) |
| BR-04 | `29.5 + 7.49/9.84` | ✅ RISOLTA | soglia ribassata portafinestra (variabile+fisso) |
| BR-05 | tempi 2 ante < 1 anta | ⏳ APERTA | non ancora chiarita |
| BR-06 | valore `180` | ✅ RISOLTA | `hourly_workshop_cost = 180 €/h` |
| BR-07 | valore `76` | ✅ RISOLTA | vetro doppio standard 76 €/m² |
| BR-08 | totale Enerhia | ⏳ APERTA | attende conferma composizione totale |
| BR-09 | pellicolato +6% | ✅ **RISOLTA con MODIFICA**: +10% (non +6%) su pellicolati standard |
| BR-10 | minimo vetro 0.5 m² | ✅ RISOLTA | applica per singola lastra |
| BR-11 | `H × 7.51 / 1000` | ✅ **NUOVA / RISOLTA** | montante fisso verticale (`FIXED_MULLION`) |
| BR-12 | `L × 7.50 / 1000` | ✅ **NUOVA / RISOLTA** | traverso orizzontale (`TRANSOM`) |

**Regole risolte: 8 · Ancora aperte: 4**

---

## 1 · Componente MEETING_STILE (scambio battuta) — BR-02 ✅

```
component_role = MEETING_STILE
component_code = MEETING_STILE_TEMP (attende codice fornitore reale)
material = PVC (pellicolabile → soggetto a +10% se foil)
unit_of_measure = EUR_PER_ML
unit_cost = 5.50 €/ml (da listino tecnico versionato, NON hardcoded)
applies_when = number_of_sashes >= 2

Formula:
  meeting_stile_length_ml = height_mm / 1000
  meeting_stile_cost      = meeting_stile_length_ml * 5.50
```

Cella Excel di riferimento: `H × 5.5 / 1000` nella formula 2 ante.

---

## 2 · Componente THRESHOLD (soglia ribassata portafinestra) — BR-04 ✅

```
component_role = THRESHOLD
applies_when = window_type == "portafinestra"

Variabili tecniche versionate (NON hardcoded in formula):
  threshold_variable_cost_per_ml = 29.50 €/ml
  threshold_fixed_cost_1_sash    =  7.49 €
  threshold_fixed_cost_2_sashes  =  9.84 €

Formula (portafinestra 1 anta):
  threshold_variable = height_mm / 1000 * 29.50
  threshold_cost     = threshold_variable + 7.49

Formula (portafinestra 2 ante):
  threshold_variable = height_mm / 1000 * 29.50
  threshold_cost     = threshold_variable + 9.84

Composizioni (es. 1+2 ante):
  threshold_cost = somma delle formule per ogni sezione portafinestra
```

Il costo appartiene al **dominio tecnico**, prima del moltiplicatore commerciale.

Celle Excel: `H × 29.5/1000 + 7.49` (F portafinestra 1a), `H × 29.5/1000 + 9.84` (PF 2a).

---

## 3 · Costo orario officina — BR-06 ✅

```
Denominazione ufficiale: hourly_workshop_cost (NON hourly_cost generico)
Valore: 180.00 €/h
Rappresenta: costo complessivo dell'officina (non singolo operaio)

Configurabile per tenant · versionato · valid_from/valid_to · nello snapshot

Formula:
  labor_cost = production_time_hours * hourly_workshop_cost
```

Il valore `180.0` nel foglio "Costo Materiale" è quindi **costo orario**, non ferramenta portafinestra.

---

## 4 · Listino vetri — BR-07 ✅

| Tipo vetro | Codice | Prezzo unitario | Sorgente prezzo |
|---|---|---|---|
| Doppio standard | `DOUBLE_STANDARD` | 76.00 €/m² | `FIXED_UNIT_PRICE` |
| Doppio satinato | `DOUBLE_SATIN` | 96.00 €/m² | `FIXED_UNIT_PRICE` |
| Triplo standard | `TRIPLE_STANDARD` | 125.00 €/m² | `FIXED_UNIT_PRICE` |
| Triplo satinato | `TRIPLE_SATIN` | **156.25 €/m²** | `PERCENTAGE_SURCHARGE_ON_BASE_GLASS` (base=TRIPLE_STANDARD, +25%) |

**Regola critica**: il triplo satinato è calcolato come `125 × 1.25`, NON come `125 + 25`.

Modalità pricing supportate dal modello:
```
glass_pricing_mode: FIXED_UNIT_PRICE | PERCENTAGE_SURCHARGE_ON_BASE_GLASS

Per TRIPLE_SATIN:
  base_glass_type       = TRIPLE_STANDARD
  surcharge_percentage  = 25
  resulting_unit_cost   = base_glass_unit_cost * (1 + surcharge/100) = 156.25
```

---

## 5 · Minimo vetro — BR-10 ✅

```
minimum_billable_area_per_pane = 0.50 m²

Per ogni singola lastra:
  real_area_sqm      = (glass_width_mm * glass_height_mm) / 1_000_000
  billable_area_sqm  = max(real_area_sqm, 0.50)
  total_cost_pane    = billable_area_sqm * unit_cost_sqm

Costo totale vetro serramento = somma su tutte le lastre
```

Il minimo si applica **per singola lastra**, non aggregato.

---

## 6 · Maggiorazione colore pellicolato — BR-09 ✅ (MODIFICA da V1)

**Nuovo valore: `+10%`** (non più `+6%`).

Categorie colore soggette al **+10%** (`STANDARD_FOIL`):
- bianco effetto legno
- cedro sbiancato
- noce
- rovere dorato
- ciliegio
- crema

Configurazioni pellicolate equivalenti (entrambe +10%):
- `FOILED_BOTH_SIDES_STANDARD` (pellicolato su entrambi i lati)
- `FOILED_OUTSIDE_WHITE_INSIDE_STANDARD` (pellicolato esterno + bianco massa interno)

### 6.1 · Base di applicazione (RESTRETTA)

Il +10% si applica **esclusivamente** ai componenti PVC pellicolati:
- ✅ Telaio PVC
- ✅ Anta PVC
- ✅ Fermavetro PVC
- ✅ Scambio battuta PVC (MEETING_STILE)
- ✅ Montante fisso PVC (FIXED_MULLION)
- ✅ Traverso PVC (TRANSOM)
- ✅ Altri profili PVC pellicolati

**NON si applica a**:
- ❌ Rinforzi metallici
- ❌ Vetro
- ❌ Ferramenta
- ❌ Soglia ribassata (se non pellicolata)
- ❌ Manodopera / costo orario officina
- ❌ Posa / trasporto / smaltimento
- ❌ Accessori non pellicolati
- ❌ Totale generale del serramento

### 6.2 · Formula

```
eligible_pvc_components_cost = somma(cost dei profili PVC pellicolabili)
standard_foil_surcharge      = eligible_pvc_components_cost * 0.10

technical_internal_cost =
    base_components_cost
  + standard_foil_surcharge
  + glass_cost
  + hardware_cost
  + threshold_cost
  + labor_cost
  + other_technical_costs

sale_price = technical_internal_cost * commercial_multiplier   (regola commerciale)
```

### 6.3 · Configurazione colore

Ogni colore deve avere schema esplicito:
```
color_code, color_name, color_family, foil_category, inside_finish, outside_finish,
surcharge_type, surcharge_value, applies_to_materials,
valid_from, valid_to, version, status
```

**Il sistema NON deduce la maggiorazione dal nome del colore**. Deve essere esplicita nella configurazione.

Esempio:
```
color_name         = NOCE
foil_category      = STANDARD
surcharge_type     = PERCENTAGE_ON_ELIGIBLE_PVC_COMPONENTS
surcharge_value    = 10
```

---

## 7 · Montante fisso verticale (FIXED_MULLION) — BR-11 ✅ (NUOVA)

```
component_role      = FIXED_MULLION
component_code      = FIXED_MULLION_TEMP (needs_supplier_code_confirmation = true)
orientation         = VERTICAL
material            = PVC (pellicolabile)
unit_of_measure     = EUR_PER_ML
unit_cost           = 7.51 €/ml (da listino tecnico versionato, NON hardcoded)

Applicabile:
- 3 ante quando la ricetta prevede montante fisso
- Ogni configurazione con montante fisso aggiuntivo

Formula:
  fixed_mullion_length_ml = height_mm / 1000
  fixed_mullion_cost      = fixed_mullion_length_ml * 7.51 * quantity
```

Cella Excel: `H × 7.51 × 10^-3` nella ricetta 3 ante.

---

## 8 · Traverso orizzontale (TRANSOM) — BR-12 ✅ (NUOVA)

```
component_role      = TRANSOM
component_code      = TRANSOM_TEMP (needs_supplier_code_confirmation = true)
orientation         = HORIZONTAL
material            = PVC (pellicolabile)
unit_of_measure     = EUR_PER_ML
unit_cost           = 7.50 €/ml (NON arrotondare a 7.51 — sono due componenti distinti)

Applicabile quando il cliente richiede uno o più traversi.

Formula:
  transom_length_ml = width_mm / 1000
  transom_cost      = transom_length_ml * 7.50 * quantity

Esempio (L=1200, 1 traverso):
  1.20 * 7.50 * 1 = 9.00 €

Esempio (L=1200, 2 traversi):
  1.20 * 7.50 * 2 = 18.00 €
```

⚠️ **Nota importante**: `7.51` e `7.50` sono due valori **distinti e separati**. Il documento e il codice li tratta come componenti diversi. Nessun arrotondamento automatico.

---

## 9 · Distinzione MONTANTE FISSO vs TRAVERSO

| Componente | Orientamento | Lunghezza | Prezzo | Ruolo |
|---|---|---|---|---|
| Montante fisso | Verticale | altezza H | 7.51 €/ml | `FIXED_MULLION` |
| Traverso | Orizzontale | larghezza L | 7.50 €/ml | `TRANSOM` |

Il modello dati deve trattarli come **due entry BOM separate**. Non usare voce generica come `mullion_or_transom`.

### 9.1 · Configurazione prodotto estendibile

```
additional_components: [
  {role: "FIXED_MULLION", orientation: "VERTICAL",   quantity: 1},
  {role: "TRANSOM",       orientation: "HORIZONTAL", quantity: 2}
]
```

Il commerciale sceglie graficamente montanti e traversi. Il motore tecnico determina lunghezza + costo + colore surcharge.

### 9.2 · Estensione futura formule

Prima versione: montante usa `H`, traverso usa `L`. In futuro il modello deve permettere formule più precise:
- `H - offset` (montante non copre tutta l'altezza)
- `L - offset` (traverso non copre tutta la larghezza)
- larghezza/altezza singola specchiatura

Ogni componente ha `quantity_formula` e `length_formula` versionabili.

---

## 10 · Snapshot tecnico completo (aggiornato)

```
technical_snapshot: {
  profile_system_id,
  profile_system_version,
  technical_recipe_id,
  technical_recipe_version,

  input_dimensions,          # width_mm, height_mm
  window_type,               # finestra | portafinestra
  number_of_sashes,          # 1, 2, 3, 4

  components: [
    {
      component_role,        # FRAME | SASH | FRAME_REINFORCEMENT |
                             # SASH_REINFORCEMENT | GLAZING_BEAD |
                             # MEETING_STILE | FIXED_MULLION | TRANSOM |
                             # THRESHOLD | HARDWARE | ACCESSORY
      component_code,        # es. 5103, MEETING_STILE_TEMP
      material,              # PVC | STEEL | ALUMINUM | ...
      is_foiled,             # bool
      orientation,           # VERTICAL | HORIZONTAL | NONE
      quantity,
      length_formula,
      calculated_length_mm,
      total_length_ml,
      unit_of_measure,       # EUR_PER_ML | EUR_PER_SQM | EUR_PER_PIECE
      unit_cost,
      base_cost,
      color_surcharge_percentage,   # 10 se PVC pellicolato standard, 0 altrimenti
      color_surcharge_amount,
      final_component_cost,
      pricelist_version
    }
  ],

  glass: [
    {
      glass_type,             # DOUBLE_STANDARD | DOUBLE_SATIN | TRIPLE_STANDARD | TRIPLE_SATIN
      base_glass_type,        # per glass_pricing_mode=PERCENTAGE_SURCHARGE_ON_BASE_GLASS
      glass_pricing_mode,     # FIXED_UNIT_PRICE | PERCENTAGE_SURCHARGE_ON_BASE_GLASS
      width_mm,
      height_mm,
      real_area_sqm,
      minimum_area_sqm,       # 0.50
      billable_area_sqm,      # max(real, minimum)
      base_unit_cost_sqm,
      surcharge_percentage,   # 25 per TRIPLE_SATIN, 0 altri
      final_unit_cost_sqm,
      quantity,
      total_cost
    }
  ],

  meeting_stile_cost,
  threshold_variable_cost,
  threshold_fixed_cost,
  threshold_total_cost,

  fixed_mullion_total_cost,   # somma di eventuali montanti
  transom_total_cost,          # somma di eventuali traversi

  production_time_hours,
  hourly_workshop_cost,        # 180 default
  labor_cost,

  base_components_cost,        # somma componenti PRIMA color surcharge
  color_surcharge_cost,        # +10% su componenti eleggibili
  material_cost,               # base + color surcharge
  glass_cost,
  hardware_cost,
  additional_technical_costs,  # servizi tecnici (posa, trasporto se tecnicamente definiti)

  total_internal_cost,         # somma finale — INPUT per CommercialPricingService

  calculation_hash             # SHA256 deterministico
}
```

---

## 11 · Distinzione valori tecnici vs commerciali

**Dominio tecnico** (Sistema B): prezzi acquisto materiali, tempi produzione, sfrido, costo orario officina, ricette dimensionali, listino vetri, maggiorazione colore pellicolato.

**Dominio commerciale** (Sistema A): moltiplicatore ×3 (o markup/margin/fixed), sconti, promozioni, IVA, provvigioni, arrotondamenti commerciali.

**Regola fissa**: il +10% pellicolato è **tecnico** (applicato prima del moltiplicatore). Il ×3 è **commerciale** (applicato dopo il costo tecnico totale).

---

## 12 · Business rules ancora aperte

Solo 4 punti restano:

1. **BR-01** Doppia riga "Rinforzo telaio" `-108` vs `-70` → confermare se sono 2 componenti distinti (rinforzo esterno + interno?) o refuso Excel
2. **BR-03** Geometria 3 ante → 1 telaio unico OR composizione 1+2 accoppiate
3. **BR-05** Tempi: Finestra 2 ante = 0.75h < 1 anta = 1.0h → confermare valori o refuso
4. **BR-08** Totale Enerhia 46199 = subtotale post-moltiplicatore? Verificare composizione
5. **Codici articolo reali del fornitore** per: `FRAME_REINFORCEMENT_TEMP`, `SASH_REINFORCEMENT_TEMP`, `GLAZING_BEAD_TEMP`, `MEETING_STILE_TEMP`, `THRESHOLD_TEMP`, `FIXED_MULLION_TEMP`, `TRANSOM_TEMP` — tutti con `needs_supplier_code_confirmation=true`
6. Eventuali **categorie colore extra** oltre a `STANDARD_FOIL` (es. Premium, Custom RAL con maggiorazioni diverse)
7. **Formule dimensionali esatte** per montante/traverso quando non coprono tutta H/L

**Il mapping A→B definitivo attende BR-01, BR-03, BR-05, BR-08 + codici articolo reali.**

---

## 13 · Test aggiornati (piano)

Da aggiungere al piano di test (V3 §11), senza implementare codice:

1. Finestra 2 ante con `MEETING_STILE` presente e costo = `H/1000 * 5.50`
2. Portafinestra 1 anta con `THRESHOLD` = `H/1000 * 29.50 + 7.49`
3. Portafinestra 2 ante con `THRESHOLD` = `H/1000 * 29.50 + 9.84`
4. Vetro `DOUBLE_STANDARD` a 76 €/m²
5. Vetro `DOUBLE_SATIN` a 96 €/m²
6. Vetro `TRIPLE_STANDARD` a 125 €/m²
7. Vetro `TRIPLE_SATIN` = 125 × 1.25 = 156.25 €/m² (NON 125+25)
8. Vetro sotto minimo → billable = 0.50 m²
9. Colore bianco massa senza supplemento
10. Colore NOCE (pellicolato 2 lati) con +10% sui soli PVC eleggibili
11. Colore ROVERE DORATO (esterno pellicolato + bianco massa interno) con +10%
12. Verifica che +10% NON venga applicato al vetro
13. Verifica che +10% NON venga applicato alla manodopera / ferramenta / rinforzo metallico
14. `labor_cost = production_time_hours × 180` (hourly_workshop_cost)
15. Modifica futura `hourly_workshop_cost` NON altera preventivi congelati (immutability)
16. Tre ante con 1 montante fisso → cost = `H/1000 * 7.51 * 1`
17. Tre ante senza montante quando la ricetta non lo prevede → montante_cost = 0
18. Finestra con 1 traverso → `L/1000 * 7.50 * 1` = 9.00 € (per L=1200)
19. Finestra con 2 traversi → 18.00 €
20. Portafinestra con traverso presente
21. Montante pellicolato → +10% su costo montante
22. Traverso pellicolato → +10% su costo traverso
23. Modifica futura prezzo €/ml montante NON altera preventivi congelati
24. Montante + traverso presenti contemporaneamente nello stesso serramento

---

## 14 · Rollback

- Tag git precedente: `p1-formula-analysis-v1`
- Zero cambio dati eseguito in V1.2
- V1 mantenuto come documento storico

---

**Documento chiuso.** Attende risposte PO sui 4 punti rimasti (BR-01, BR-03, BR-05, BR-08 + codici fornitore) prima di procedere con `A_TO_B_FIELD_MAPPING_V1.md`.
