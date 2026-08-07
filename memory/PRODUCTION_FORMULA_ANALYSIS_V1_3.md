# PRODUCTION FORMULA ANALYSIS V1.3 — Stato corretto
**Sostituisce**: V1_2 · Iter 38

## Business rules — stato definitivo

**RISOLTE (11 su 12)**:
| BR | Regola | Decisione PO |
|---|---|---|
| BR-01 | Ruoli tecnici Costo Materiale | B2=FRAME, B3=FRAME_REINFORCEMENT, B4=SASH, B5=SASH_REINFORCEMENT, B6=GLAZING_BEAD, B7=GLASS, B8=WORKSHOP_LABOR. Duplicato "Rinforzo telaio" = errore etichetta Excel |
| BR-02 | H×5.5/1000 | MEETING_STILE 5.50 €/ml |
| BR-04 | 29.5+7.49/9.84 | THRESHOLD portafinestra (variabile+fisso per n_ante) |
| BR-05 | Tempi produzione | WINDOW_1_SASH=0.75h, WINDOW_2_SASH=1.00h, DOOR_WINDOW_1_SASH=1.00h, DOOR_WINDOW_2_SASH=1.50h, WINDOW_3_SASH=2.30h, DOOR_WINDOW_3_SASH=3.00h. "Portafinestra 1,5 anta" = etichetta incoerente Excel usata per PF 2 ante |
| BR-06 | 180 €/h | hourly_workshop_cost |
| BR-07 | Listino vetro | DOUBLE_STANDARD 76, DOUBLE_SATIN 96, TRIPLE_STANDARD 125, TRIPLE_SATIN 156.25 (=125×1.25) |
| BR-08 | Totale Enerhia | 46199 è **seriale data Excel**, non totale economico. Il totale ~25.202,82 € nel foglio "Inserimento dati" **include già** il moltiplicatore ×3. NON ri-moltiplicare |
| BR-09 | Pellicolato +10% | Su soli profili PVC eleggibili (6 colori standard) |
| BR-10 | Minimo vetro | 0.50 m² per singola lastra |
| BR-11 | H×7.51/1000 | FIXED_MULLION verticale 7.51 €/ml |
| BR-12 | L×7.50/1000 | TRANSOM orizzontale 7.50 €/ml |

**PARZIALMENTE APERTA (1)**:
- **BR-03** Geometria 3 ante:
  - La formula Excel esistente = `COMPOSITION_1_SASH_PLUS_2_SASH` (1 anta 1/3 + 2 ante 2/3 con 2 telai)
  - Ricetta `THREE_SASH_SINGLE_FRAME` (telaio unico) = **non ancora disponibile** → il motore deve emettere `MISSING_TECHNICAL_RECIPE` fino a formula ufficiale
  - Non blocca il mapping generale

**Dati anagrafici da completare (non regole di calcolo)**:
- Codici fornitore reali per: `FRAME_REINFORCEMENT_TEMP`, `SASH_REINFORCEMENT_TEMP`, `GLAZING_BEAD_TEMP`, `MEETING_STILE_TEMP`, `THRESHOLD_TEMP`, `FIXED_MULLION_TEMP`, `TRANSOM_TEMP` (con `needs_supplier_code_confirmation=true`)
- Categorie colore extra oltre `STANDARD_FOIL`
- Formule montanti/traversi parziali
- Prezzi futuri versionati

**Verdetto**: mapping può partire. Cross-review + implementazione dopo mapping + golden test.

**Zero codice modificato.** Vedi anche `A_TO_B_FIELD_MAPPING_V1.md` e `ENERHIA_GOLDEN_TEST_CASES_V1.md`.
