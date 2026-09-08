# CASSONETTO_GRID_VALIDATION — PO msg 401 (§1-§11, §34)

**Data**: 2026-09-08 · **Source of truth**: `backend/data/listino_completo_con_costi.xlsx` (SALE GRID: Bianco massa / Pellicolato standard / Pellicolato no-std · COST GRID: Costo prod. Bianco / Std / No-std)

## Verdetto: **CASSONETTI = PASS**

| Metrica | Valore | Requirement |
|---|---|---|
| sale cells checked | **4464** (3 famiglie × 31 L × 6 H × 4 prof × 2 cielino) | 4464 |
| sale matches (workbook == JSON == DB tenant A == DB tenant B == engine) | **4464** | 4464 |
| sale mismatches | **0** | 0 |
| cost cells checked | **4464** | 4464 |
| cost matches | **4464** | 4464 |
| cost mismatches | **0** | 0 |
| missing valid grid keys | **0** | 0 |
| duplicate keys | **0** (186 righe uniche L×H per foglio) | 0 |
| invalid color mappings | **0** (13 codici PVC → famiglia esplicita; altri → NEEDS_PO_MAPPING/fail-closed) | 0 |
| invalid dimensions nel workbook | **0** | 0 |
| celle workbook con sale ≤ 0 / cost ≤ 0 / sale ≤ cost | **0** | 0 |

Test permanente: `backend/tests/test_cassonetto_grid_full_matrix.py` (13 test, cell-by-cell su workbook→JSON→DB→engine + golden API + fail-closed) — **PASS**.
Regressione aggiuntiva testing agent: `backend/tests/test_pricing_integrity_audit_msg401.py` — **PASS**.

## Golden (workbook corrente)

| Case | Input | SALE atteso | SALE engine/API/UI | COST atteso | COST engine/API |
|---|---|---|---|---|---|
| C1 | 500×250 · 163 · con cielino · 003 (BIANCO_MASSA) | 329,01 | **329,01** | 101,23 | **101,23** |
| C2 | 500×550 · 163 · con cielino · 003 | 422,38 | **422,38** | 112,63 | **112,63** |
| C3 | 700×250 · 326 · con cielino · 003 | 276,13 | **276,13** | 110,45 | **110,45** (il vecchio 110,43 non è più presente in DB/JSON) |
| D | 500×250 · 163 · SI · 100 (STANDARD) | 370,77 | **370,77** | 114,08 | **114,08** |
| E | 500×250 · 163 · SI · 019 (NON_STANDARD) | 399,78 | **399,78** | 123,01 | **123,01** |

## Root cause del bug "cassonetto non viene validato" (§10 — TRACE)

Riproduzione UI (admin, dialog `MultiCategoryConfiguratorDialog`, prodotto `CASSONETTO_STD`):

| Step | Valore |
|---|---|
| raw UI inputs | width_mm=500, height_mm=250, depth_mm=163, ceiling_liner=SI, **color_code = (vuoto)** |
| normalized width/height | 500 / 250 |
| depth / cielino | 163 / SI → `col_key=163_c` |
| PVC color code | nessuno → `resolved price_family = None` |
| expected grid key | `BIANCO_MASSA/163_c/500x250` (solo dopo scelta colore) |
| lookup | non eseguito: resolver fail-closed `MISSING_CASSONETTO_COLOR_PRICE_FAMILY` |
| API response | `pricing_status=invalid_inputs`, `blocking_errors=[MISSING_CASSONETTO_COLOR_PRICE_FAMILY]` |
| frontend field letto | `preview.pricing_status` ≠ ok → badge INVALID_INPUTS, bottone "Aggiungi" disabilitato |

Secondo trigger (input libero): campi L/H erano `<input type=number>` a testo libero (es. 1200×300, 550×250) → nessuna cella → `DIMENSION_TO_CONFIRM` senza indicazione delle misure ammesse.

**Root cause**: (1) nessun colore preselezionato + label del ColorPicker che mostrava la categoria PVC (`MASS_COLOR/STANDARD/SPECIAL`) invece della famiglia cassonetto → l'operatore non capiva che il colore era obbligatorio per il listino; (2) misure inserite a testo libero fuori griglia. **Nessun problema di dati**: DB e JSON erano già allineati al workbook (verificato cell-by-cell prima dell'intervento; il file JSON su disco era invece una versione precedente — rigenerato).

**Fix (no workaround)**:
- Frontend: L e H diventano **select** alimentate da `pricing_config.widths_mm/heights_mm` (31 larghezze, 6 altezze); hint esplicito misure di listino; messaggio "Seleziona il colore PVC: determina la famiglia di listino"; ColorPicker per CASSONETTI mostra `cassonetti_price_family`.
- Backend: `compute_grid` normalizza input numerici (float→int), accetta `has_cielino` come alias, `DIMENSION_TO_CONFIRM:<LxH> non in griglia (L 500-3500 step 100; H 250/…/750)`, fail-closed anche su `internal ≤ 0` (`MISSING_CASSONETTO_INTERNAL_COST`), snapshot con `cassonetto_width_mm/height_mm`, `price_family`, `grid_key`, `has_cielino`.
- Importer autoritativo: `python -m app.scripts.import_cassonetti_grid --apply-db` (workbook → `app/data/cassonetti_grid_2026.json` v`cassonetti_grid_2026_09_workbook` → DB tutti i tenant; abort se ≠ 4464 celle o celle invalide).

## Vincoli verificati
- §6 NO multiplier runtime: il compute è `lookup exact sale cell` / `lookup exact cost cell` (metadata ×2.5/+30%/+50% solo documentale).
- §7 NO interpolazione: `DIMENSION_TO_CONFIRM` (test su 550×250, 500×300, 400×250, 3600×250, 500×800).
- §8 Il cassonetto NON eredita L/H dal vano (dialog indipendente, campi propri).
- §9 Color family solo da mapping esplicito `product_colors.cassonetti_price_family` (003→BIANCO_MASSA; 100/096/694/110/154/048→STANDARD; 019/145/146/109/402/663→NON_STANDARD); codice sconosciuto → fail-closed.
- RBAC: griglia per commerciale ridotta a `{sale}`; `internal_production_cost_per_item` rimosso dallo snapshot commerciale.
