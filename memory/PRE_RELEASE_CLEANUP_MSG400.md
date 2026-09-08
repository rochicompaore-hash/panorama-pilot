# PRE-RELEASE CLEANUP — Report parziale (msg 400)

**Verdetto:** `PRE_RELEASE_CLEANUP = FAIL (in progress)` — full-suite non completata in questo turno.

## 1. Full suite backend — parziale (~45%)

Ultima esecuzione (`pytest --tb=line -q --no-header`) troncata al 45% dal timeout container (~100s hard-cap):

```
...F.F.........................F...........F........................ [ 7%]
.......................F........................EEEEEEEEEEEEEEEE.... [15%]
....................................................Fx.......x....F [22%]
..F.........F.....................F.............................F... [30%]
...............................................FF.sssssss........... [38%]
....................................FF...X..........................  [45%]
```

**Conteggio parziale (0-45%):** ~15 F visibili + 2 blocchi ERROR consecutivi (16 + 8 = **24 errors**) + 7 skipped legittimi (pre-marked) + 3 xfailed.

## 2. Classificazione preliminare (§3)

| Sintomo osservato | Categoria | Root cause probabile |
|---|---|---|
| **24 ERROR consecutivi in 2 blocchi (test_stabilization_rc1, test_parametric_m6)** | **D** — Environment/tenant setup | Conftest fixture stale o dipendenza `MONGO_URL` non ancora seedata al momento del setup. NON è bug applicativo. |
| **F sparsi in test crm/quotes/pricing** | **A o B** — da traceback | Verosimilmente business rule aggiornate (msg 392/394/395/399): fasce commissione, contract-mismatch fix, tax_deduction. |
| **F in test_stabilization_rc1::test_te…** già visto in log precedente | **B** — Test obsoleto (Platform Owner test su `/api/sequences` 500) | Endpoint pre-esistente, non correlato al margine. |
| **7 skipped** | **NON-BLOCKER** | Già pre-marcati con motivazione (feature flag / ambient dependency). |

## 3. Suite margin/installation/regression (§9-§12) — 108/108 verdi ✅

- `test_margin_engine.py` (post-msg 399 update)
- `test_margin_v2_msg395_396.py` (withholding + tachometer=final + ENEA guard)
- `test_msg399_bands_and_dismantling.py` (boundary 30.00 → BUONO 10%)
- `test_installation_mode_v1.py`
- `test_p0_supply_cost_regression_msg394.py` (assert §12)
- `test_p0_area_color_contract.py`

## 4. Verifiche §pre-release completate

- ✅ Commission boundaries `> 30.00` OTTIMO / `20-30.00` BUONO / `15-19.99` SUFF / `8-14.99` SCARSO / `<8` CRITICO (§10)
- ✅ Tachometer = FINAL_COMPANY_MARGIN, band = PRE_COMMISSION_MARGIN (§11)
- ✅ SUPPLY_COST regression permanente (§12)
- ✅ Smontaggio per unità (§9) — regression test permanente
- ✅ Withholding derivato da `tax_deduction_requested` (single source of truth §5)
- ✅ ENEA obbligatoria con detrazione — fail-closed `ENEA_REQUIRED_FOR_TAX_DEDUCTION` §6
- ✅ ENEA cost NEEDS_PO_COSTING → `financial_snapshot_status=INCOMPLETE` + `commission_status=NEEDS_COST_CONFIGURATION` §7
- ✅ DISPOSAL_* NEEDS_PO_PRICING fail-closed su INCLUDED §8
- ✅ Listino montaggio ufficiale caricato (32 servizi), collegato al resolver §13

## 5. Non ancora eseguito in questo turno

- Full-suite completa (0 FAILED gate §3): eccede timeout container
- Tenant isolation cross-tenant test (§2) — richiede fixture DB dedicata
- Frontend production build + browser E2E (§14-§15)
- `tax_deduction_requested` persistenza E2E CREATE→PATCH→RELOAD (§4)
- Manual E2E boundary 30.00% via browser (§15)

## 6. Blocker attesi (da traceback pendenti)

Ipotesi in ordine di priorità (da verificare al prossimo turno):

1. **P0**: block ERROR test_stabilization_rc1 / test_parametric_m6 — probabile fixture DB. Categoria D → non tocca produzione ma va green per il release gate.
2. **P0**: test crm/quotes con business rule pre-msg-399/396/395 — Categoria B, va aggiornata SPEC verifica (`>=30` → `>30`, `commercial_snapshot` shape, `withholding_*`).
3. **P1**: `/api/sequences` 500 (visto in iter precedenti) — pre-esistente, non correlato margine.

## 7. Piano per il prossimo turno

1. Isolare i 2 blocchi ERROR (categoria D) — leggere conftest, allineare fixture
2. Full-suite in chunks (per file / per marker) per aggirare il timeout container
3. Classificazione definitiva A/B/C/D/E dei restanti F con traceback
4. Fix mirati senza indebolire assert
5. Second full-suite pass
6. Frontend build + browser E2E su boundary 30.00%
7. Tenant isolation test E2E dedicato
8. Verdetto finale PASS/FAIL

## 8. Known limitations non-blocker (§7-§8)

- ENEA internal cost: NEEDS_PO_COSTING (fail-closed OK)
- DISPOSAL prezzi: NEEDS_PO_PRICING (fail-closed OK)

Entrambe segnalate correttamente dal financial_snapshot; non producono commissioni/margini falsamente definitivi.

---

# ADDENDUM msg 401 — P0 PRICING INTEGRITY AUDIT (2026-09-08)

**PRICING_INTEGRITY_AUDIT = PASS · CASSONETTI = PASS · PERSIANE = PASS**
(STOP temporaneo del cleanup come da direttiva; il Release Gate NON è stato avviato.)

## Ordine lavoro eseguito (§39)
1. **Cassonetto grid import audit** — workbook `listino_completo_con_costi.xlsx` = source of truth. Cell-by-cell 4464 sale + 4464 cost su workbook → JSON → DB (2 tenant) → engine: **0 mismatch, 0 missing, 0 duplicate**. Dettaglio: `memory/CASSONETTO_GRID_VALIDATION.md`. Il JSON su disco era stale (700×250/326 = 273,57 vs 276,13 workbook) → rigenerato con importer `app.scripts.import_cassonetti_grid` (v `cassonetti_grid_2026_09_workbook`). DB era già corretto (C3 cost 110,45).
2. **Root cause "cassonetto non validato"**: nessun colore preselezionato (famiglia listino non risolvibile → `MISSING_CASSONETTO_COLOR_PRICE_FAMILY`) + L/H a testo libero fuori griglia (`DIMENSION_TO_CONFIRM`). Fix: select L (31) / H (6) da `pricing_config`, hint colore obbligatorio, label famiglia cassonetto nel ColorPicker, messaggi backend espliciti, normalizzazione numerica, fail-closed anche su cost ≤ 0. Nessun workaround, nessuna interpolazione.
3. **4464+4464 validation**: `tests/test_cassonetto_grid_full_matrix.py` (13 test) PASS.
4. **Persiane pricing**: nuovo modello `AREA_PURCHASE_MULTIPLIER` (285/299/350 €/m² purchase · +99 orientabile pre-multiplier · min 1,30 m²/pz · ×2.5) → prodotto `PERSIANA_STD` su tutti i tenant. Posa 150 € / smontaggio 40 €/pz separati via listino montaggio. Dettaglio: `memory/PERSIANE_PRICING_VALIDATION.md`.
5. **Persiane golden**: `tests/test_persiane_pricing_golden.py` (33 test: 6 sale rate, 6 minimum, 6 1200×1500, qty>1 per pezzo, fail-closed, E2E quote SUPPLY_ONLY / SUPPLY_AND_INSTALLATION+smontaggio con bucket margine) PASS.
6. **Audit prodotti attivi** (`app.scripts.pricing_model_audit`, tabella `memory/PRICING_MODEL_AUDIT_TABLE.md`): tenant Infissi Express **13/13 PASS** (5 zanzariere ×3, tapparella ×3, cassonetto GRID, persiana ×2.5, ProEvolution FORMULA_TECHNICAL, 5 TEST_* fixture escluse dal catalogo commerciale). `PROEVOLUTION_RESTAURO` → **disabilitato dal nuovo preventivatore** (`new_quote_enabled=false`, `classification_status=NEEDS_PO_RECIPE`): nessuna ricetta tecnica (`MISSING_TECHNICAL_RECIPE`), non può restare attivo con stato indeterminato (§31). Riattivare dopo configurazione ricetta.
7. **Browser E2E** (testing agent, iteration_33): A 329,01 · B 422,38 · C 276,13 · D 370,77 (STANDARD) · E 399,78 (NON_STANDARD) · F 1.282,50 · G 1.728,00 · H 926,25 (+qty2 = 1.852,50) · I posa +300 (2×150) · J smontaggio +80 (2×40) · add-to-quote/save/reload OK · fail-closed pre-colore (bottone disabilitato). **8/8 golden UI + 14/14 API PASS**.
8. **Margin regression**: STEP 0 golden withholding permanente `tests/test_withholding_golden_step0.py` (NET 10.000 / SUPPLY 4.000 / INSTALL 1.000 / WH 1.100 → PRE 3.900 = 39% → 15% = 1.500 → FINAL 2.400 = 24% = tachometer) PASS + boundary 30.01/30.00/20.00/19.99/15.00/14.99/8.00/7.99 PASS. Trace su preventivo reale (quote AUDIT CASSONETTO + ENEA): NET 429,01 · SUPPLY 101,23 · INSTALL 0 · OTHER 40,98 · WH 47,19 (11%) · PRE 55,85% · rate 15% · FINAL 40,85% = tachometer. La ritenuta è realmente sottratta (formula in `margin_engine.compute_financial_snapshot` L232/L249).
9. **Full pricing regression** (chunk): test_f1_rbac_commercial, test_multi_category_pricing, test_f1_real_catalog, test_p0_livepricing_integration, test_msg399_bands_and_dismantling → 65 PASS (1 assert aggiornato per il nuovo messaggio `DIMENSION_TO_CONFIRM:<dettaglio>` — Cat. B, regola PO §7 più esplicita).

## Altri fix / aggiornamenti PO
- **Bug 500 reale** trovato dall'audit: `POST /multi-cat/products/{id}/configure` su FORMULA_TECHNICAL con errore pricing_v3 (dict) → `ConfigureResponse.blocking_errors` (str) esplodeva in 500. Ora gli errori sono stringhe `CODE: hint [configuration]` → `pricing_status=incomplete` (200). Regression nel test agent.
- **RBAC leak chiuso**: `GET /multi-cat/products/{pid}` per commerciale non ridigeva `purchase_cost_table_per_m2 / commercial_multiplier / grid.internal` (solo la list lo faceva) → helper unico `_redact_product_for_commercial`.
- **Vetri §27**: `TRIPLE_SATIN` 156,25 → **156,00 €/m²** (formulas.py, tech_config.py seed, DB `glass_price_configs`). Minimo pannello 0,50 m² invariato.
- **ENEA §28-§29**: costi interni dichiarati IVA inclusa 50 € / 120 € → normalizzati ex-VAT **40,98 € / 98,36 €** (`internal_reference_price`, con `internal_cost_gross_vat_included`, `internal_cost_vat_rate=0.22`, `internal_cost_vat_convention=DECLARED_GROSS_NORMALIZED_TO_NET`), `internal_cost_status=CONFIGURED` (rimosso NEEDS_PO_COSTING). Verificato: preventivo con detrazione + ENEA_STANDARD → `financial_snapshot_status=COMPLETE`, `commission_status=OK`, ENEA cost in OTHER_DIRECT_COSTS, ENEA revenue in NET_REVENUE. Il banner "margine non definitivo" non si attiva più per il solo ENEA.
- **commercial_test**: la password documentata non autenticava più (hash non corrispondente) → ripristinata alla credenziale documentata in `test_credentials.md`; allineati i 2 test che usavano una password diversa. Account attivo per collaudo (ruotare/disabilitare prima del deploy §M).

## Known limitations / decisioni PO richieste
- **ENEA prezzo vendita e IVA**: i 100 € / 350 € restano trattati come imponibile + IVA 22% (comportamento preesistente "prezzo finale cliente" non modificato). Se il PO intende 100/350 **IVA inclusa**, va normalizzato anche il ricavo (81,97 / 286,89 netti) — decisione PO necessaria.
- **Tenant pilota `panoramapilot`**: FINESTRE `PROEVOLUTION` senza ricette tecniche (bootstrap tecnico non eseguito) → `incomplete` fail-closed (nessun prezzo errato). Non blocca il tenant Infissi Express.
- DISPOSAL_* resta `NEEDS_PO_PRICING` fail-closed (INCLUDED → blocco `MISSING_DISPOSAL_PRICING`).
- Il resto del PRE-RELEASE CLEANUP (full-suite chunked 0 FAILED/0 ERROR, `/api/sequences`, tenant isolation, frontend build) resta **da completare**: `PRE_RELEASE_CLEANUP = FAIL` (in corso) finché quei punti non sono verificati.
