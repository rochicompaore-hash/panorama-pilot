# QUOTE_EDITOR_FINAL_AUDIT — PO msg 402 (Quote Editor Completion V1)

**Data**: 2026-09-08 · **Verdetto: QUOTE_EDITOR_FINAL_AUDIT = PASS** (percorso di preventivazione utilizzabile end-to-end; nessun blocker "zero tolerance" aperto — vedi *Known limitations* per i punti PO da confermare).

## 1. Modifiche implementate (per lotto)
| Lotto | Cosa | Dove | Test |
|---|---|---|---|
| 1 Modifica riga | `PUT /api/quotes/{qid}/lines/{lid}/reconfigure` — stessa line identity/order, `previous_snapshots` (history, max 10), recompute autoritativo prezzo/snapshot tecnico-simple-commerciale/servizi/totali/financial snapshot; helper condiviso `_build_priced_line` (usato anche da add_line). UI: bottone **Modifica** (`line-edit-{id}`) riapre lo stesso `MultiCategoryConfiguratorDialog` allo step 3 con tutti i valori popolati (L/H/qty/tipologia/ante/vetro/colore/opzioni). Frozen (ACCEPTED) → 400/409. | quotes.py, MultiCategoryConfiguratorDialog.jsx, QuoteEditorPage.jsx | `test_quote_editor_v1_lotto1_reconfigure.py` (3) + E2E browser |
| 2 Cantiere | Obbligatori: indirizzo, civico, CAP, comune, provincia, piano, ascensore, telefono (`SITE_ADDRESS_REQUIRED / SITE_FLOOR_REQUIRED / SITE_ELEVATOR_REQUIRED / SITE_PHONE_REQUIRED`) su create + edit; `POST /quotes` con cantiere incompleto → `SITE_INCOMPLETE`. UI: form inline "+ Nuovo cantiere" nel dialog Nuovo preventivo, precompilato da Customer (indirizzo/telefono), auto-selezione dopo creazione. | sites.py, quotes.py, QuotesPage.jsx | `test_quote_editor_v1_lotti_2_5_6_9.py::TestSiteValidation` (9) + browser |
| 3 Flags | Montaggio / Smontaggio / Smaltimento in testata (già presenti, verificati); Smaltimento INCLUDED resta **fail-closed** (`MISSING_DISPOSAL_PRICING`, UI disabilitata). | — | browser |
| 4 Smontaggio 30 € | `simple_services` categoria SMONTAGGIO `REMOVE_*`: `customer_sale_price` 40 → **30,00 €/unità** (`sale_policy_version=dismantling_sale_30_msg402`); `internal_reference_price` del listino ufficiale **mantenuto** (20 €; REMOVE_ARMORED_DOOR 30 €). Applicato per ogni unità (qty prodotto = qty smontaggio) → OTHER_DIRECT_COSTS. | DB | persiane/integrity/installation tests (aggiornati 40→30) |
| 5 Payment terms | `app/services/payment_terms.py`: 5 policy strutturate (`DEPOSIT_50_BALANCE_50` default, `FULL_UPFRONT` → **sconto automatico 5%**, `DEPOSIT_30_SURVEY_20_BALANCE_50`, `FINANCING_WITHOUT_DEPOSIT`, `FINANCING_WITH_DEPOSIT`); snapshot `payment_terms_code, payment_terms_label, payment_schedule[], automatic_discount_percent, financing_mode, payment_policy_version, payment_discount_amount, subtotal_before_payment_discount`; codice sconosciuto → 400 `PAYMENT_TERMS_INVALID`; sconto applicato in `_financial_totals_patch` (subtotal/IVA/totale/NET_REVENUE/margine/commissione/tachimetro), frozen su ACCEPTED. UI: select in editor + dialog nuovo preventivo, riga "Sconto automatico pagamento 5% = −X". | payment_terms.py, quotes.py, models_quote.py | `TestPaymentTerms` (5) + browser |
| 6 Vetri + Profilatura | Vetri: UI select con **esattamente 4 tipi** (76 / 96 / 125 / **156,25** €/m² — ripristinato per msg 402 in formulas.py, tech_config seed, DB `glass_price_configs`). Profilatura: servizio automatico `PROFILING` su FINESTRE/PORTEFINESTRE FORMULA_TECHNICAL: `perimeter_ml = 2×(L+H)/1000`, `8,00 €/ml`, × qty; ricalcolato su modifica L/H/qty. Costo interno **NEEDS_PO_COSTING** (non inventato) → `financial_snapshot_status=INCOMPLETE` + `MISSING_INTERNAL_COST_PROFILING` finché il PO non lo definisce. | service_resolver.py, quotes.py, margin_engine.py, dialog | `TestProfiling` + browser (43,20 € · 5,80 ml → 46,40 × 2 = 92,80 €) |
| 7 Cassonetti + Persiane | Verificati live → add → save → reload → modify → recompute (browser): cassonetto 500×250/163/SI/003 = 329,01 → modifica 700×250/326 = 276,13 (grid lookup, no multiplier); persiana RAL 1200×1500 fissa 1.282,50 → orientabile qty 2 = 1.728,00 × 2 + posa 300 + smontaggio 60. Nessun 0 €. | — | iteration_33/34 + `test_cassonetto_grid_full_matrix.py`, `test_persiane_pricing_golden.py` |
| 8 Pellicolato | Policy vigente resa configurabile: `STANDARD_FOIL_SURCHARGE_PERCENT = 10` (`formulas.py`), `STATUS = NEEDS_PO_FINAL_CONFIRMATION`. **CURRENT VALUE 10% · SOURCE BR-09 (pricing_v3/resolvers) · EFFECTIVE DATE 2026-08-11**. Applicata solo ai ruoli PVC `FRAME, SASH, GLAZING_BEAD, MEETING_STILE` (non vetro/ferramenta/rinforzo/servizi). Nessun cambio silenzioso. | formulas.py, resolvers.py | pricing_v3 tests |
| 9 Delivery | `app/services/delivery_policy.py`: `STANDARD` (min 90 gg, "Oltre 90 giorni…") default; `EXPRESS` +20% su base commerciale (righe prodotto+servizi, **esclusi ENEA**), `express_days_status=NEEDS_PO_CONFIRMATION` (giorni non inventati); snapshot `delivery_mode, estimated_delivery_min/max_days, delivery_customer_text, delivery_surcharge_percent/amount, delivery_policy_version`. Ordine: maggiorazione → sconto pagamento. Rimosso il campo libero "Tempi di consegna (giorni)" dall'editor. | delivery_policy.py, quotes.py, QuoteEditorPage.jsx | `TestDeliveryPolicy` + browser |
| 10 PDF | Snapshot PDF: "Tempi indicativi di consegna" da policy, modalità fornitura/posa, Condizioni di pagamento da `payment_schedule`, righe "Maggiorazione consegna accelerata (+20%)", "Imponibile prima dello sconto", "Sconto pagamento anticipato (5%)". Nessun dato interno (verificato: assenti internal_cost/supply_cost/costo). | pdf_renderer.py, quote_pdf.html | browser + pypdf |

Extra: fix Radix Select (`onValueChange("")` spontaneo) nel dialog cantiere; PDF `display_note` template soppresso quando esiste `payment_schedule`.

## 2. Pricing source per categoria
| Categoria | Modello | Costo interno | Vendita |
|---|---|---|---|
| FINESTRE/PORTEFINESTRE | FORMULA_TECHNICAL (pricing_v3 BOM + vetro + ferramenta + manodopera + pellicolato 10%) | technical `total_internal_cost` | ×3 pacchetto |
| TAPPARELLE | AREA (purchase 35/40/45 ×3, min 1,50) | purchase | ×3 |
| ZANZARIERE | AREA (purchase table ×3, minimi per modello) | purchase | ×3 |
| CASSONETTI | GRID (workbook 4464 celle) | cella `internal` | cella `sale` |
| PERSIANE | AREA_PURCHASE_MULTIPLIER (285/299/350 +99 orientabile, min 1,30/pz) | purchase | ×2,5 |
| Servizi (posa/smontaggio/ENEA) | listino montaggio ufficiale | `internal_reference_price` | `customer_sale_price` (nessun multiplier) |
| PROFILATURA | 8 €/ml × perimetro | NEEDS_PO_COSTING | 8 €/ml |

## 3. Esiti test
- Backend (pytest, chunk): `test_quote_editor_v1_lotto1_reconfigure.py` 3/3 · `test_quote_editor_v1_lotti_2_5_6_9.py` 16/16 · persiane 33/33 · cassonetto matrix 13/13 · pricing integrity 22/22 · installation_mode/msg399/margin/withholding 63+ · margin_tachometer_e2e 5/5 (assert aggiornati alla policy 30,00% → 10% e RBAC tachimetro) · pdf formula-technical 5/5.
- Frontend E2E (testing agent iteration_34): 7/8 flussi PASS al primo giro; unico difetto (auto-selezione cantiere dopo creazione) **corretto e riverificato** in browser (cantiere selezionato → preventivo creato).
- Margin: golden withholding STEP 0 e boundary commissioni invariati e verdi; sconto 5% e maggiorazione 20% entrano in NET_REVENUE prima del calcolo margine/commissione/tachimetro (§38: 10.000 → 50/50 sconto 0; 100% → 500 € sconto, net 9.500, IVA 2.090, totale 11.590).

## 4. Known limitations / decisioni PO
1. **STANDARD FOIL SURCHARGE = 10%** (vigente dal 2026-08-11, BR-09). Confermare 10% o indicare 15% (`NEEDS_PO_FINAL_CONFIRMATION`).
2. **EXPRESS DELIVERY DAYS**: +20% attivo; giorni = `NEEDS_PO_CONFIRMATION` (testo PDF: "tempistica da confermare per iscritto").
3. **PROFILATURA costo interno**: non definito → snapshot margine INCOMPLETE finché il PO non fornisce il costo (nessun costo inventato).
4. Smontaggio `REMOVE_ARMORED_DOOR`: internal 30 = sale 30 (margine 0) — coerente con policy "30 € per tutti", segnalato.
5. ENEA vendita 100/350 € trattati imponibile + IVA (decisione IVA-inclusa ancora aperta, vedi msg 401 report).
6. Finanziamento: solo WITH/WITHOUT_DEPOSIT (TAN/TAEG/rate = BACKLOG).
7. Test suite pre-esistenti ancora rossi **fuori scope di questo intervento** (PRE-RELEASE CLEANUP): `m3_quotes_test` (numerazione `PREV-` vs `PRV-`, `/api/sequences` 500, convert), `test_pdf_m332` (snapshot non incluso nel listing, gate missing_site), `test_quote_structure_iter16/17` (legacy structure page, Vano V2 freeze), `test_pricing_v3_milestone1::gt01` (hardware 60 vs 76 da `hardware_rules`), `test_m1_part2` (`pytest.site_id` fixture chain).

## 5. Blocker
Nessun blocker "zero tolerance" (§41) aperto sul percorso di preventivazione.
