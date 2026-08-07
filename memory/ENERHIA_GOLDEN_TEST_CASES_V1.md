# ENERHIA GOLDEN TEST CASES V1
**Iter 38** · Specifica di validazione riproducibile · Zero codice
**Uso**: base dei test automatici del nuovo motore. Impediscono modifiche silenziose ai costi.

## Assunzioni globali
- `S = 3` (weld_allowance_mm), quindi `S*2 = 6`
- `hourly_workshop_cost = 180 €/h`
- Multiplier commerciale = 3.0
- Tolleranza costo componente: ±0.01 €. Tolleranza totale: ±0.05 €

## Costi unitari di riferimento (Preventivatore 4.0)
| Componente | €/unità | Ruolo |
|---|---|---|
| Telaio | 4.02 €/ml | FRAME |
| Rinforzo telaio | 1.52 €/ml | FRAME_REINFORCEMENT |
| Anta | 2.31 €/ml | SASH |
| Rinforzo anta | 1.34 €/ml | SASH_REINFORCEMENT |
| Fermavetro | ? (attende catalogo) | GLAZING_BEAD |
| Meeting stile | 5.50 €/ml | MEETING_STILE |
| Threshold var | 29.50 €/ml | THRESHOLD |
| Threshold fix 1a | 7.49 € | THRESHOLD_FIXED |
| Threshold fix 2a | 9.84 € | THRESHOLD_FIXED |
| Fixed mullion | 7.51 €/ml | FIXED_MULLION |
| Transom | 7.50 €/ml | TRANSOM |
| Vetro DOUBLE_STANDARD | 76.00 €/m² | GLASS |
| Vetro DOUBLE_SATIN | 96.00 €/m² | GLASS |
| Vetro TRIPLE_STANDARD | 125.00 €/m² | GLASS |
| Vetro TRIPLE_SATIN | 156.25 €/m² | GLASS |
| Ferramenta finestra | 76.00 € | HARDWARE |
| Ferramenta portafinestra | (temporaneo, non definito) | HARDWARE |

## Test case obbligatori (12)

### GT-01 · Finestra 1 anta 900×1500 BIANCO massa (no pellicolato)
- L=900, H=1500, S=3, n_sashes=1, window_type=window, color=WHITE_MASS (no surcharge)
- Formule:
  - FRAME: `2*(L+S) + 2*(H+S) = 2*903 + 2*1503 = 4812mm = 4.812 ml` × 4.02 = **19.34 €**
  - FRAME_REINFORCEMENT: `2*(L-70) + 2*(H-70) = 2*830 + 2*1430 = 4520mm = 4.520 ml` × 1.52 = **6.87 €**
  - SASH: `2*(L-206) + 2*(H-206) = 2*694 + 2*1294 = 3976mm = 3.976 ml` × 2.31 = **9.18 €**
  - SASH_REINFORCEMENT: analoga con -186 = 4056mm × 1.34 = **5.43 €** (verificare formula)
  - GLASS: `(L-206)*(H-206)/1e6 = 694*1294/1e6 = 0.898 m²`, billable=max(0.898, 0.50)=0.898, cost = 0.898 × 76 = **68.25 €**
  - HARDWARE: **76.00 €** (fissa)
  - LABOR: 0.75h × 180 = **135.00 €**
- Costo materiali = 19.34 + 6.87 + 9.18 + 5.43 + 68.25 + 76.00 = **185.07 €**
- Costo interno = 185.07 + 135.00 = **320.07 €**
- Sale price = 320.07 × 3 = **960.21 €**
- Expected: 960.21 € ± 0.05

### GT-02 · Finestra 2 ante 1700×1600 PELLICOLATO NOCE (esterno + bianco interno)
- L=1700, H=1600, n=2, color=NOCE (foil_category=STANDARD, +10% su PVC)
- Confronto atteso col foglio Enerhia: **1452.08 €** ("Salotto")
- Componenti PVC: FRAME, SASH, GLAZING_BEAD, MEETING_STILE, (montante fisso se presente)
- Componenti NON PVC (no surcharge): FRAME_REINFORCEMENT (metallo), SASH_REINFORCEMENT (metallo), GLASS, HARDWARE, LABOR
- Formule 2 ante (dal foglio):
  - FRAME: `[(L-75)/2 + S]*4 + 2*(H-70) + 2*S`
  - FRAME_REINFORCEMENT: `2*(L-347) + 4*(H-347)`
  - GLAZING_BEAD: `2*(L-307) + 4*(H-186)`
  - MEETING_STILE: `H/1000 = 1.60 ml × 5.50 = 8.80 €`
  - GLASS (2 lastre): `((L-347)/2) * (H-206) * 2` = 2 lastre da (1353/2)×1394 = 676.5×1394 mm
- Applica surcharge_pct = 10% solo su base_cost dei componenti PVC eleggibili
- Sale price atteso = costo_totale × 3
- Expected: verifica corrisponda a **1452.08 €**

### GT-03 · Portafinestra 1 anta 900×2500
- L=900, H=2500, n=1, window_type=door_window
- FRAME/SASH/vetro come GT-01 con nuove dimensioni
- THRESHOLD: `H/1000 × 29.50 + 7.49 = 2.5×29.50 + 7.49 = 73.75 + 7.49 = 81.24 €`
- LABOR: 1.00h × 180 = 180.00 €
- Sale price = costo_totale × 3

### GT-04 · Portafinestra 2 ante 2300×2500
- L=2300, H=2500, n=2, window_type=door_window
- THRESHOLD: `2.5 × 29.50 + 9.84 = 82.99 €`
- LABOR: 1.50h × 180 = 270.00 €
- Confronto atteso col foglio Enerhia: **1381.60 €** ("Ingresso")

### GT-05 · Composizione 3 ante 1+2 (COMPOSITION_1_SASH_PLUS_2_SASH)
- L totale=..., H=..., n=3 come **composizione** modulo 1a (1/3) + modulo 2a (2/3) con 2 telai separati
- Ricetta approvata (BR-03 partial)
- Sale price = somma dei due moduli × 3

### GT-06 · Test THREE_SASH_SINGLE_FRAME (non implementato)
- Deve emettere: `MISSING_TECHNICAL_RECIPE`
- Blocking error, no sale price

### GT-07 · Vetro satinato (DOUBLE_SATIN)
- Come GT-01 ma glass_type=DOUBLE_SATIN → unit_cost=96 €/m² invece di 76
- Verifica che GLASS cost aumenti proporzionalmente e HARDWARE/LABOR restino invariati

### GT-08 · Triplo vetro (TRIPLE_STANDARD)
- unit_cost=125 €/m²
- Verifica FIXED_UNIT_PRICE mode

### GT-09 · Triplo satinato (TRIPLE_SATIN)
- pricing_mode=PERCENTAGE_SURCHARGE_ON_BASE_GLASS
- base_glass_type=TRIPLE_STANDARD (125), surcharge=25%
- final_unit_cost = 125 × 1.25 = **156.25 €/m²** (NON 125+25=150)

### GT-10 · Vetro sotto minimo (0.35 m² reale)
- Vetro reale 700×500 = 0.35 m²
- billable_area = max(0.35, 0.50) = **0.50 m²**
- Verifica che il costo sia calcolato su 0.50 non su 0.35

### GT-11 · Finestra 1 anta con 1 traverso
- Come GT-01 + TRANSOM: `L/1000 × 7.50 × 1 = 0.9 × 7.50 = 6.75 €`
- Se PVC + pellicolato → +10% surcharge: 6.75 × 1.10 = 7.43 €
- Verifica che il traverso appaia nello snapshot con `orientation=HORIZONTAL`

### GT-12 · Finestra con montante fisso + traverso simultanei
- Configurazione 3 ante come composizione + traverso orizzontale
- FIXED_MULLION: `H/1000 × 7.51 × 1 = 1.5 × 7.51 = 11.27 €`
- TRANSOM: `L/1000 × 7.50 × 1 = ... €`
- Se pellicolati PVC → +10% su entrambi
- Verifica che compaiano come 2 entry separate nello snapshot

## Test di immutability

### GT-13 (regressione) · Modifica prezzo listino post-preventivo
- Crea preventivo GT-01, salva snapshot
- Modifica prezzo TELAIO da 4.02 a 5.00 €/ml
- Ricalcola preventivo GT-01 storico → deve restituire **stesso sale_price 960.21 €** (technical_snapshot immutabile)
- Nuovo preventivo con stessi input → nuovo sale_price con 5.00

### GT-14 (regressione) · Modifica moltiplicatore commerciale post-preventivo
- Crea preventivo GT-01 con multiplier=3
- Modifica multiplier globale a 3.5
- Preventivo GT-01 storico → sale_price INVARIATO (commercial_snapshot immutabile)

## Regole di validazione
- Ogni componente stampa: `role, code, qty, unit, unit_cost, base_cost, surcharge_pct, surcharge_amt, final_cost, pricelist_version`
- +10% surcharge visibile solo su componenti eleggibili
- +10% NON applicato a: GLASS, HARDWARE, LABOR, THRESHOLD, rinforzi metallici
- snapshot_hash deterministico (2 chiamate stesso input → stesso hash)

## Aperti (attendono PO)
- Fermavetro (GLAZING_BEAD) prezzo esatto in €/ml (Costo Materiale duplicato riga)
- Ferramenta portafinestra prezzo esatto
- Formule SASH_REINFORCEMENT 1 anta (`-186` vs `-206`?)
- Verifica formula 2 ante contro le 6 righe reali del preventivo Enerhia

## Uso
Ogni GT-XX diventa un pytest o Playwright test dopo Fase 1 V3.
