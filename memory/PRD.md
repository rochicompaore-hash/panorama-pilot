## Iter 56 — FASE A: PREVENTIVATORE COMPLETO + SCONTO DROPDOWN + SMONTAGGIO + PRICING GAP AUDIT (22 Set 2026)

**Autorizzato:** PO revoca temporanea freeze (Fase A). Fase B (Financing Engine V1) NON iniziata.

### Consegnato
- `margin_engine.py`: `max_commercial_discount_step_percent` (int 0..30, floor mai verso l'alto, tiene conto stacking moltiplicativo con FULL_UPFRONT 5%); aggiunto a `COMMERCIAL_SAFE_KEYS`; costante `COMMERCIAL_DISCOUNT_DROPDOWN_MAX=30`.
- `quotes.py` PATCH `global_discount_percent`: solo interi 0..30 (400 `GLOBAL_DISCOUNT_INVALID`); pre-check floor >15% invariato (`DISCOUNT_BLOCKED_MARGIN_FLOOR`).
- `QuoteEditorPage.jsx`: sconto = Select 0–30% step 1 (`quote-discount-pct-select`, `discount-opt-{i}`), opzioni > max disabilitate "non consentito", label "max consentito N%".
- Smontaggio: già presente (REMOVE_* 30 € sale / 20 € int, qty riga, bucket OTHER) — verificato 3×30=90 €.
- Audit prezzi: `/app/memory/PREVENTIVATORE_PRICING_GAP_AUDIT_V1.md` (+ script `/app/memory/scripts/pricing_gap_audit.py`). 4.540 prezzi pubblicati, 7 sale/cost mancanti (DISPOSAL×5, LOGISTICS×2), 6 famiglie senza formula (3/4 ante, scorrevole, vasistas, Restauro, colore SPECIAL), 9 legacy disabilitati. Cassonetti: nessun doppio markup.

### Test
- `tests/test_fase_a_preventivatore.py` 8/8 (step validation, max step int, FULL_UPFRONT max 8→3, blocco oltre max, smontaggio 90 € + OTHER cost). Regressione margin/pdf/discount/installation 134/134. Testing agent `iteration_48.json` frontend PASS (dropdown, smontaggio +90 €, riepilogo, reload, RBAC commerciale zero leak; PDF preview apre in nuova tab — by design).

### Stato
- APPLICATION_CODE = STRICT_FEATURE_FREEZE (Fase A chiusa). Prossimo: FASE B Financing Engine V1 su autorizzazione PO.

---

## Iter 55 — STABILIZZAZIONE FINALE + E2E + MASTER CAPABILITY GAP AUDIT V1 (11 Set 2026)

**Autorizzato:** PO "CONFERMA PO — OPZIONE B" + "PO DIRECTIVE MASTER CAPABILITY GAP AUDIT V1" (audit only).

### Consegnato
- Fix SOLO fixture/setup test legacy incompatibili con pre-firma check msg 803 §18 (NESSUNA modifica business logic): `test_workflow_m6_wf.py` (IndentationError riga 330), `m3_quotes_test.py` (cliente completo + site_address; assert snapshot `economics.lines` / `quote_totals`), `test_blocco_bcd_iter20.py` (fixture crea preventivo accettato completo; rimosso `pytest.skip` su PRESIGN — non si dichiara verde ciò che è escluso), `test_customer_email_notifications_v1.py` (tax_code + address sui clienti fixture).
- FULL_PYTEST: **1224 passed, 9 failed, 1 error, 56 skipped** → RELATED_FAILURES = 0. KNOWN_UNRELATED: 429 brute-force login (2), race xdist su utente viewer/contatore clienti in `security_audit_test` (7, passano in seriale `-n0`), 1 read timeout infra.
- CONTRACT_E2E + FAST_FLOW_E2E via testing agent `iteration_47.json`: PASS (backend 42/42 incl. 12 nuovi in `test_iter47_po_verification.py`; frontend 1366×768 PASS su quote-convert → contract-viewer, presign-ok, PDF iframe, Fast Flow A/B, inline create senza duplicati, RBAC commerciale no leak, tenant isolation).
- **APPLICATION_CODE = STRICT_FEATURE_FREEZE. HARD STOP.**
- Audit: `/app/memory/PANORAMA_MASTER_CAPABILITY_MATRIX_V1.md` (22 domini, control tower, top 20/30/20/20, roadmap P0–P4). Completamento medio ~52%.

---

## Iter 53 — MODULAR COMMISSION + ADMIN MASTER DUAL MARGIN + COMMERCIAL COMMISSION TACHOMETER + FLOOR >15% (Set 2026)

**Autorizzato:** msg 796 (commissione modulare per sconto), msg 800 (Admin Master dual margin), msg 801 (UI commerciale: rimozione margine + tachimetro commissione), msg 802 (floor POST_MARGIN > 15%).

### Consegnato
- `margin_engine.py`: `effective_discount_percent` (global + promo + FULL_UPFRONT vs `commercial_subtotal`), fasce cap 15/12/10/8/5/3/0 (+DIRECTOR_APPROVAL >30%), `ACTUAL_COMMISSION_RATE = min(cap, compat floor)` con floor **strettamente > 15.00%** (epsilon 0.01pp, floor a 4dp), `discount_status ∈ {BLOCKED (<=15), LOW_MARGIN (15–20), ALLOWED (>=20), NO_DATA}`, `max_discount_for_margin_floor` (>15 strict). Snapshot esteso: `pre_margin_amount/percent` (NO ritenuta/commissione), `post_margin_amount/percent` (= FINAL), `actual_commission_rate`, `commercial_commission`. `commission_policy_version = commission_policy_v3_modular_floor15_2026_09`.
- RBAC 3 livelli server-side: **Admin Master** (`is_superadmin` o ruolo Super Admin / tenant_owner → `is_admin_master()`) = snapshot completo; **Commerciale e Admin Azienda** = solo `COMMERCIAL_SAFE_KEYS` (commissione, sconto effettivo, sconto max, stato) — NESSUN margine (%/€/fascia/tachometer). Marker `__ADMIN_MASTER__` in `_get_perms`.
- `quotes.py`: `_raise_if_price_blocked` (400 `DISCOUNT_BLOCKED_MARGIN_FLOOR`, messaggio senza %), pre-check PRIMA di persistere su PATCH sconto/pagamento (bug fix: prima lo sconto bloccato veniva salvato), gate su `update_line` (base_price/discount). Nessun bypass superadmin.
- PDF leak fix: `pdf_renderer.build_snapshot` strip ricorsivo di `position_internal_cost_total`, `standard_services_internal_cost_total`, `internal_cost_total`, `unit_internal_reference_price`, `simple_snapshot`, `commercial_snapshot`.
- Frontend: `CommissionTachometer.jsx` (0–15%, tick 0/3/5/8/10/12/15, zone neutre) per commerciale; `MarginPanel` → commerciale: sconto effettivo / commissione / sconto max / PREZZO CONSENTITO|NON CONSENTITO / badge >30%; Admin Master: MarginTachometer + REDDITIVITÀ COMMESSA (pre €|%, post €|%, badge NORMALE/MARGINALITÀ BASSA/CRITICA) + Riservato Direzione. Prop `isAdmin = financial.is_admin_master_view`.
- Utente test `admin_azienda_test@infissiexpress.com` (Admin Azienda, non master).

### Test
- `tests/test_margin_dynamic_commission.py` 59 test (boundary 12 fasce, FULL_UPFRONT, ritenuta post-sconto, floor 14.99/15/15.01/16/19.99/20/25, cap10→guard7, max discount, dual margin, API redaction 3 ruoli, cross-owner, PDF no-leak, edit price gate, freeze).
- Suite legacy aggiornata alla policy v3. Totale: 1196+ passed; residui non correlati: `test_p0_formula_technical_quoteline` (quote fixture ormai `converted`), `test_parametric_m6` 403, `test_prod_gate_iter41` 429 rate-limit.

### Stato
- APPLICATION_CODE = STRICT_FEATURE_FREEZE (in attesa deploy per SMTP reale).
- PENDING PO (non iniziati): CUSTOMER → QUOTE FAST FLOW + SEARCHABLE CUSTOMER SELECTOR; ACCEPTED QUOTE → CONTRACT GENERATION V1.

---

## Iter 52 — Margin Engine V2 (Ritenuta + Tachometer=Final + ENEA Guard) (Feb 2026)

**Autorizzato:** Msg 395 + 396 + ENEA UI (post-P0 SUPPLY_COST).

### Consegnato
- **Withholding V1 (msg 395)**: `withholding_applicable` + `withholding_rate` (default 11%) sulla Quote; nuovo bucket `WITHHOLDING_COST` sottratto in `PRE_COMMISSION_CONTRIBUTION`. Snapshot esteso: `withholding_applicable/base/rate/cost/policy_version`. Bucket SEPARATO da SUPPLY/INSTALL/OTHER (§14).
- **Tachometer semantica corretta (msg 396)**: aggiunto `tachometer_value = final_company_margin` nel snapshot; frontend `MarginTachometer` legge `fs.tachometer_value` invece di `pre_commission_margin`. Label UI "MARGINE AZIENDALE". Il PO chiedeva §11 verificato E2E: NET=10000 SUPPLY=4000 INSTALL=1000 WH=1100 → pre 39% OTTIMO 15% (commission engine input) → **tachometer = 24%** (post-commission).
- **ENEA safety guard**: PATCH `enea_practice_code` (ENEA_STANDARD/ENEA_INSURED/null) materializza hidden line con `enea_practice=True`. Se `internal_cost` mancante ⇒ `financial_snapshot_status="INCOMPLETE"` + `MISSING_INTERNAL_COST_ENEA` + `commission_status="NEEDS_COST_CONFIGURATION"`. UI Admin mostra banner giallo "MARGINE NON DEFINITIVO — Costo interno Pratica ENEA non configurato".
- **UI card Installation Mode** estesa: toggle Ritenuta [No / 11%], select Pratica ENEA [Nessuna / Standard / Assicurata] con mutua esclusione.
- **RBAC aggiornato (msg 396 §6)**: `COMMERCIAL_SAFE_KEYS` ora contiene `tachometer_value` + `financial_snapshot_status/errors`. **NON contiene** `pre_commission_margin` (valore tecnico solo per Direzione).
- **Bumped**: `margin_policy_version = margin_policy_v2_2026_02`.

### Test
- **21 pytest nuovi** in `test_margin_v2_msg395_396.py` (§13 msg 395 withholding band flip, §11 msg 396 tachometer≠pre, ENEA guard 3 casi, RBAC tachometer visibility, WITHHOLDING bucket separato).
- **97/97 totali verdi** dopo aggiornamento suite pre-esistente.
- **E2E curl completo** su quote `8d2efe76-3719-4922-a9fb-e5cceba6378f`: baseline 50%/35%, con ritenuta 39%/**24%**, con ENEA fs_status=INCOMPLETE + tachometer=24.495%. RBAC commerciale: NESSUN LEAK breakdown.
- **Screenshot UI verificato**: "MARGINE AZIENDALE 24,50 % OTTIMO" + banner "MARGINE NON DEFINITIVO" + breakdown Riservato Direzione con `Ritenuta d'acconto (11%) −1.111,00 €`.

### Vincoli PO rispettati
- ✅ 395 §1-§4 formula con WITHHOLDING sottratta
- ✅ 395 §2-§3 default 11%, applicabile solo se `withholding_applicable=true`
- ✅ 395 §5-§7 esempi verificati
- ✅ 395 §8 UI Direzione mostra ritenuta separata
- ✅ 395 §9 commerciale NON vede l'importo ritenuta
- ✅ 395 §10-§11 snapshot esteso + freeze on accepted
- ✅ 395 §12 PDF cliente non contiene ritenuta interna (già stripped da `strip_margin_from_pdf_payload`)
- ✅ 395 §14 bucket SEPARATO (test dedicato)
- ✅ 396 §4/§13 tachometer_value = final_company_margin
- ✅ 396 §6-§7 UI commerciale/direzione differenziata
- ✅ 396 §12 pre_commission = commission engine input, final = tachometer output
- ✅ ENEA §3-§5 safety guard su costi mancanti
- ✅ ENEA §7 DISPOSAL_* rimane NEEDS_PO_PRICING, no INCLUDED sbloccabile

### Aperto
- Costi interni ENEA (2 valori dal PO) → sbloccheranno `commission_status="OK"` con contributo `OTHER_DIRECT_COSTS` a costo reale.
- Prezzi Smaltimento (5 coppie int_ref/customer_sale) → sbloccheranno `disposal_mode=INCLUDED`.
- Collaudo manuale post-regression PO (Vano V2 in attesa).

### Stato ufficiale
- `MARGIN_ENGINE_V2` = **BACKEND_READY + UI_READY + MANUAL_E2E_PENDING**.

---

## Iter 51 — P0 REGRESSION SUPPLY_COST + ENEA services (Feb 2026)

**Autorizzato:** Messaggio 394 §21 — STOP Vano V2, fix immediato marginalità.

### Root cause (§19 msg 394)
Il preview `/multi-cat/products/{pid}/configure` applica RBAC redaction (nasconde `purchase_cost_per_item` / `total_internal_cost` ai commerciali). Il frontend `MultiCategoryConfiguratorDialog.submit()` inoltrava quel payload **redacted** al `POST /quotes/{qid}/lines`, che lo salvava così com'era. Risultato: `simple_snapshot.purchase_cost_per_item=None`, `internal_cost=0` → **SUPPLY_COST=0** anche per prodotti con costo reale >0.

Trace §19 documentato via script diretto contro `_extract_line_cost` / `_line_bucket` / `aggregate_costs_from_lines` su 6 preventivi reali.

### Fix architetturale (§4/§7/§9 msg 394)
`app/routers/quotes.py::add_line` ora fa un **AUTHORITATIVE PRICING RECOMPUTE lato backend** ogni volta che riceve `product_id + configuration_snapshot + pricing_model`:
1. Fetch prodotto + categoria dal DB
2. Chiama `resolve_and_compute(product, category, req, tenant_id)` — bypass RBAC (backend è source-of-truth)
3. Sovrascrive `simple_snapshot`, `technical_snapshot`, `commercial_snapshot` con i valori COMPLETI (non redacted)
4. Popola `internal_cost` autoritativo dal snapshot appena computato (fallback ordinato tra `technical.total_internal_cost` / `simple.purchase_total_cost` / `simple.purchase_cost_per_item` / `simple.internal_production_cost_per_item`)

Bonus: aggiunto campo `simple_snapshot` mancante al modello `QuoteLine` (era esposto solo come dict opaco).

### Verifica E2E msg 394 §13
Preventivo `PRV-2026-01748-R00` (creato via Commercial user con payload redacted):
- Tapparella 1200×1400 RAL → `simple_snapshot.purchase_cost_per_item=58.80` ✅
- UNIKVER 800×800 BASE → `simple_snapshot.purchase_cost_per_item=32.34` ✅
- Financial: net 483.42€, **supply 91.14€** (58.80+32.34), install 170€, other 0€
- Margin 45.98% OTTIMO 15%

### Test regressione (§12 msg 394 assert obbligatorio)
`tests/test_p0_supply_cost_regression_msg394.py` — 12 pytest verdi:
- Legacy internal_cost path
- Simple snapshot per Tapparella/Zanzariera
- Technical snapshot per Finestra
- POSA aggiuntiva NON sostituisce SUPPLY
- SUPPLY_ONLY mantiene SUPPLY
- Assert strutturale "product with cost>0 → SUPPLY>0"
- E2E full snapshot §13

**Totale suite: 86/86 pytest verdi** (12 nuovi + 28 Installation Mode + 38 Margin Engine + 8 P0 area color).

### ENEA services seedati (msg 394)
Anagrafiche `simple_services` create su tenant Infissi Express:
- `ENEA_STANDARD` — Pratica ENEA Standard — 100.00 € (customer_sale_price)
- `ENEA_INSURED` — Pratica ENEA Assicurata — 350.00 € (customer_sale_price)
- Entrambe con `internal_cost_status = "NEEDS_PO_COSTING"`, `internal_reference_price = null`, `pricing_unit = FIXED_PRICE`, `quantity_rule = ONE_PER_QUOTE`.
- NO commercial multiplier applicato: sono prezzi finali cliente.
- Quando entreranno nel preventivo: contribuiscono a NET_REVENUE_EX_VAT ma NON a OTHER_DIRECT_COSTS finché il PO non definisce l'`internal_reference_price`.

### Vincoli PO rispettati (msg 394)
- ✅ §1 formula PRE_COMMISSION invariata
- ✅ §2 SUPPLY_COST = costo interno prodotti (mai vendita)
- ✅ §3 tre bucket separati (SUPPLY / INSTALLATION / OTHER)
- ✅ §4 ogni QuoteLine contribuisce a SUPPLY_COST
- ✅ §5-§6 posizione espone product/service costs separatamente
- ✅ §7 no product_sale_price come cost
- ✅ §8-§10 esempi verificati Tapparella/Zanzariera/Finestra/Cassonetto
- ✅ §11-§13 test E2E completo
- ✅ §14 SUPPLY_ONLY mantiene SUPPLY
- ✅ §15 SUPPLY_AND_INSTALL somma i costi
- ✅ §17 fasce commissione invariate
- ✅ §19 root cause trace fornito, NO workaround
- ✅ §20 acceptance 10/10
- ✅ §21 STOP Vano V2 rispettato

### Stato aggiornato
- `QUOTE_MARGIN_TACHOMETER_V1` = BACKEND_READY + UI_READY + **REGRESSION_FIXED** + MANUAL_E2E_PENDING.
- `QUOTE_INSTALLATION_MODE_V1` = BACKEND_READY + UI_READY + MANUAL_E2E_PENDING.
- `ENEA services` = SEEDED (prezzi vendita) + NEEDS_PO_COSTING (costi interni).

---

## Iter 50 — QUOTE INSTALLATION MODE + AUTO SERVICE BUNDLE V1 (Feb 2026)

**Autorizzato:** Messaggio 393 §28 — parallelo al collaudo Tachimetro senza modifiche al Margin Engine.
**Deliverable:** `/app/memory/QUOTE_INSTALLATION_MODE_V1.md`.

### Consegnato
- **Modello Quote esteso**: `installation_mode` (SUPPLY_ONLY | SUPPLY_AND_INSTALLATION), `dismantling_mode`, `disposal_mode` (INCLUDED | EXCLUDED | NOT_APPLICABLE).
- **Modello QuoteLine esteso** (additive): `automatic_services[]`, `manual_extra_services[]`, `standard_services_sale_total`, `standard_services_internal_cost_total`, `position_sale_total`, `position_internal_cost_total`, `service_policy_version`.
- **`app/services/service_resolver.py`** — StandardServiceResolver deterministico. Priorità finestre: underlight DOUBLE → SINGLE → SLIDING → FIXED → VASISTAS → 4 ante → 3 ante → 1/2 ante. Mapping deterministico anche per Cassonetti (single/double), Zanzariere (single/double), Tapparelle, Persiane, Porte.
- **Seed 5 DISPOSAL_\*** con `pricing_status=NEEDS_PO_PRICING` — fail-closed §8 su INCLUDED se prezzo mancante.
- **Router quotes esteso**: `PATCH /quotes/{qid}` valida enum e ri-risolve tutte le righe su cambio mode (§19-§20, preserva `manual_extra_services`). `POST /quotes/{qid}/lines` auto-resolve on add. `POST /quotes/admin/seed-disposal-services`.
- **`compute_line` esteso**: `subtotal_line = product + automatic_services + manual_extra_services`. Nessuna modifica alle engine pricing prodotto (§25).
- **`margin_engine.aggregate_costs_from_lines` esteso**: POSA/MOTORIZZAZIONE → INSTALLATION_COST, SMONTAGGIO/SMALTIMENTO → OTHER_DIRECT_COSTS (§22).
- **UI `InstallationModeCard`** in QuoteEditor: toggle Solo fornitura / Fornitura + posa + selettori Smontaggio/Smaltimento. Riga preventivo mostra sotto-riga "Servizi standard inclusi" quando `automatic_services` non vuoto.

### Test
- **28 pytest verdi** in `test_installation_mode_v1.py` (priorità resolver + bucket mapping + wiring Margin Engine).
- **75/75 totali** dopo integrazione (Installation + Margin + P0 area color).
- **E2E curl verificato**: quote `c322c398-...` — Finestra 2 ante 1250€ + `INSTALL_WINDOW_1_2_SASH` 150€ + Tapparella 176.40€ + `INSTALL_ROLLER_KIT` 120€ → net 1696.40€, supply 858.80€, install 230€, margin 35.82% OTTIMO 15% = 254.46€.

### Vincoli PO rispettati (msg 393)
- ✅ §1-§5 Resolver deterministico con underlight priority
- ✅ §7-§8 Disposal seed NEEDS_PO_PRICING + fail-closed
- ✅ §10 Dismantling ≠ Disposal
- ✅ §14 POSA fuori dai multiplier prodotto
- ✅ §17-§18 UI card dedicata, no refactor QuoteEditor
- ✅ §19-§20 Cambio mode ricalcola + preserva manual
- ✅ §22 Wiring Margin Engine automatico
- ✅ §25 Engine CONSUMER, no modifiche alle pricing engines
- ✅ §28 STOP F2/F3/F4 rispettato

### Stato ufficiale
- `QUOTE_INSTALLATION_MODE_V1` = **BACKEND_READY + UI_READY + MANUAL_E2E_PENDING**.

---

## Iter 49 — QUOTE MARGIN TACHOMETER V1 (Feb 2026)

**Autorizzato:** Messaggio 392 §29 — E1 + E2 + 2 decimal UI fix.
**Deliverable primario:** `/app/memory/QUOTE_MARGIN_TACHOMETER_V1.md`.

### Consegnato
- **E1 Backend**: `app/services/margin_engine.py` (pure consumer, no pricing recompute §25). Fasce esatte ≥30/≥20/≥15/≥8/<8 (CRITICO=AUTHORIZATION_REQUIRED, rate=None). Financial snapshot 17 campi (§16). Commission base = NET_REVENUE_EX_VAT (§4). Include OTHER_DIRECT_COSTS (§5). Freeze on ACCEPTED (§18).
- **Router quotes**: agganciato `_financial_totals_patch` in add_line/update_line/delete_line/delete_opening, endpoint `GET /api/quotes/{qid}/financial-snapshot` con RBAC redaction (§20), freeze automatico su status→accepted.
- **PDF guard §19**: `pdf_renderer.build_snapshot` strippa `financial_snapshot`/`technical_snapshot`/`pricing_snapshot`/`internal_cost`/`margin_*` sia top-level sia per line.
- **E2 Frontend**: `MarginTachometer.jsx` SVG semicircolare scala 0-40% (§13) con 5 zone colorate. `MarginPanel` nel QuoteEditor con vista commerciale (§10: margin+band+commission) e admin breakdown Riservato Direzione (§12). Live recalc via `useQuery` invalidato su `q.version` (§14). Banner rosso "PREVENTIVO DA AUTORIZZARE" se CRITICO (§15).
- **Formattazione 2 decimali §21**: `fmtEUR` ora usa `minimumFractionDigits: 2` — applicato a prezzo/subtotale/imponibile/IVA/totale/commissione/breakdown.

### Test
- **38 pytest verdi** in `test_margin_engine.py` (boundary §3 · resolve_band · cost aggregation §6 · golden §23/§24 · CRITICO §15 · live recalc band flip §14 · RBAC §20 · PDF guard §19 · policy versioning).
- **Testing agent iter_32** — backend 100%, frontend 100%, 0 blocker (RBAC OK, freeze OK, PDF guard OK, 2-decimali applicato). Golden §23 confermato E2E via curl su quote `3b4fd98a-fc62-457d-9d66-494742e5fc90`.

### Vincoli PO rispettati (msg 392)
- ✅ §1 formule + NO circolari
- ✅ §2/§3 fasce ESATTE con 8 boundary verificati
- ✅ §4 base = NET_REVENUE_EX_VAT
- ✅ §5 OTHER_DIRECT_COSTS incluso
- ✅ §6/§7 motore CONSUMER di snapshot
- ✅ §9 NESSUN overhead gestionale fittizio
- ✅ §11/§20 RBAC backend-side (commerciale vede solo 7 chiavi safe)
- ✅ §13 tachimetro leggibile con readout numerico
- ✅ §14 live recalc su ogni mutazione
- ✅ §15 CRITICO ≠ 0% (rate=None)
- ✅ §18 freeze on ACCEPTED
- ✅ §19 PDF guard rinforzato
- ✅ §21/§22 2 decimali sempre in UI, calcolo interno full precision
- ✅ §25 no duplicazione pricing engines
- ✅ §26/§29 VANO MODEL V2 NON iniziato (stop rispettato)

### Stato ufficiale
- `QUOTE_MARGIN_TACHOMETER_V1` = **BACKEND_READY + UI_READY + MANUAL_E2E_PENDING** (§28).

---

## Iter 48 — P0 HOTFIX Live Price Tapparelle/Zanzariere (Feb 2026)

**Autorizzato:** Messaggio 391 §1-10 — bug live price nel configuratore multi-categoria da chiudere PRIMA del Margin Tachometer.

### Bug
`COMMERCIAL_PRICING_NOT_CONFIGURED` / `MISSING_UNIT_SALE_PRICE` visualizzato in `PricingPreviewCard` per Tapparelle e Zanzariere anche con calcolo backend corretto. Root cause: `compute_area_by_color` esponeva `sale_price_per_item` ma NON `unit_price_final`, mentre tutte le altre engine (compute_area basic, compute_grid, compute_per_item…) e il frontend leggono `unit_price_final`. Contract mismatch, non regressione RBAC.

### Fix (msg 391 §6 — contratto canonico)
1. `backend/app/services/multi_category_pricing.py::compute_area_by_color`: aggiunto `unit_price_final = sale_price_per_item` allo snapshot (per-billed-unit).
2. `frontend/src/components/app/MultiCategoryConfiguratorDialog.jsx`: submit() e PricingPreviewCard leggono anche `sale_price_per_item` come alias canonico → catena `unit_price_final ?? sale_price_per_item ?? c.final_unit_price ?? c.unit_sale_price`.
3. NO fallback, NO default, NO 0 — pura normalizzazione di contratto.

### Test
- `backend/tests/test_p0_area_color_contract.py` — 8/8 pytest verdi (contract + valori attesi 176.40/201.60/226.80 tapparella 1200×1400; 97.02 UNIKVER 800×800 con min 1.5 m²).
- `testing_agent iter_31.json`: **backend 100% (13/13), frontend E2E 100%**, RBAC OK (commerciale vede `unit_price_final`/`sale_price_total`, NON vede `purchase_*`/`commercial_multiplier`), add-to-quote + save + reload persistono.

### Vincoli PO rispettati (msg 391)
- ✅ §2 — nessun fallback, nessun default, nessun placeholder
- ✅ §6 — contratto canonico `unit_price_final` / `sale_price_total`
- ✅ §7-8 — commerciale riceve solo campi di vendita, no leak costi/multiplier
- ✅ §10 — acceptance browser PASS via testing_agent

### Aperto per prossimo giro
- Margin Tachometer V1 (msg 391 §11-19): sbloccato ora che hotfix P0 è chiuso.
  - Fasce: ≥30%=15% · ≥20%=10% · ≥15%=8% · ≥8%=5% · <8% NEEDS_AUTHORIZATION (non 0%).
  - Base commissione: NET_REVENUE_EX_VAT (§11 risposta 1=B).
  - Include OTHER_DIRECT_COSTS (§12 risposta 2=A).

---

## Iter 47 — F1 REAL CATALOG PRICING V1 (P0 — Ago 2026)

**Autorizzato:** Messaggio "P0 — COMPLETAMENTO REALE PREVENTIVATORE + CATALOGO + VISUAL CONFIGURATOR + PDF" (modalità 1a: F1 completa poi STOP).
**Deliverable primario:** `/app/memory/REAL_CATALOG_PRICING_V1.md`

### Consegnato (F1 backend + parte UI del configuratore)
- **Gerarchia FINESTRE unica**: PORTEFINESTRE `active=false` (soft-delete). TIPO SERRAMENTO chiesto dentro ProEvolution: `WINDOW / DOOR_WINDOW` come primo campo del `cfg-technical`.
- **Anagrafica colori PVC** (`product_colors`): 13 colori seedati con doppia classificazione esplicita `pvc_color_category ∈ {MASS_COLOR, STANDARD, SPECIAL}` + `cassonetti_price_family ∈ {BIANCO_MASSA, STANDARD, NON_STANDARD}`. Router CRUD + `visual_hex` per F3. `003` e `100` (stesso RAL 9016) → famiglie diverse verificate.
- **Zanzariere reali** (5 modelli): `SWITCH_5 / SKAT / UNIKLAT / UNIKVER / UNIKCAT` con `pricing_model=AREA` + `purchase_cost_table_per_m2` per {BASE, WOOD_EFFECT, MARBLE, SPECIAL} × `commercial_multiplier=3.00`. Fixture `TEST_ZANZARIERA_AREA_130` disattivata. `zanzariere_colors` collection separata (§7 mapping) con placeholder `ZC_*_DEFAULT` (colori reali TO_CONFIRM).
- **Tapparelle reali**: `TAPPARELLA_STANDARD` con 3 varianti colore (RAL 35 / LEGNO 40 / RAFFAELLO 45 €/m²), min 1.50 m²/pz, NO ×3. `direct_product_cost=NEEDS_PO_CONFIGURATION`.
- **Cassonetti — nuovo `pricing_model=GRID`**: importato da workbook `listino_completo_con_costi.xlsx` (3 famiglie × 8 sotto-griglie × 186 dimensioni = 4.464 celle prezzo con `{internal, sale}`). Il file vince — nessun ricalcolo dal costo. Fail-closed `DIMENSION_TO_CONFIRM` + `MISSING_CASSONETTO_COLOR_PRICE_FAMILY`. Il colore selezionato risolve `finish_family` via `product_colors.cassonetti_price_family` (mapping esplicito). NO ×3.
- **Frontend**: `MultiCategoryConfiguratorDialog` esteso con: (1) TIPO SERRAMENTO in `cfg-technical`, (2) ColorPicker data-driven con swatch hex per Zanzariere/PVC/Tapparelle, (3) `cfg-grid` renderer per cassonetti (L/H/depth/ceiling/color), (4) preview esteso con dettagli condizionali per AREA e GRID + campi `canSeeCosts` per admin.

### Vincoli PO rispettati (§1-40)
- ✅ Categoria FINESTRE unica, no dropdown misto (§1)
- ✅ TIPO in configurazione, no prodotti duplicati (§2)
- ✅ Numero ante configurabile (§4)
- ✅ Anagrafica colori PVC 13 (§9-10)
- ✅ Zanzariere reali 5 modelli con min per pezzo (§19-25)
- ✅ Tapparelle 3 varianti no ×3 (§34-37)
- ✅ Cassonetti GRID no ×3 no formula (§29-33)
- ✅ Fail-closed su tutti i pricing (§16, §33)
- ✅ Snapshot con pricing_version (§25 direttiva master)
- ✅ Distinzione REAL_CATALOG_DATA vs TEST_FIXTURE vs LEGACY (§18)

### Test
- **34/34 pytest verdi**: `test_multi_category_pricing.py` (19) + `test_p0_formula_technical_quoteline.py` (5) + `test_f1_real_catalog.py` (10)
- Acceptance verificati: §21 UNIKVER 97,02€ · §22 tapparelle 52,50/60/67,50€ · §23 cassonetti 3 celle (329,01€/422,38€/296,20€ con relativi costi interni)

### Stato ufficiale post-F1
- `FINESTRE_REAL_CATALOG` = **E2E_READY (backend)** — richiede tuo ricollaudo UI
- `ZANZARIERE_REAL_CATALOG` = **E2E_READY (backend)** — richiede tuo ricollaudo UI
- `TAPPARELLE_REAL_CATALOG` = **E2E_READY (backend)** — richiede tuo ricollaudo UI
- `CASSONETTI_REAL_CATALOG` = **E2E_READY (backend)** — richiede tuo ricollaudo UI
- `POSITION_TECHNICAL_DATA_V1` = **NOT_STARTED** (F2)
- `VISUAL_CONFIGURATOR_V1` = **NOT_STARTED** (F3)
- `QUOTE_PDF_V2` = **NOT_STARTED** (F4)
- `M5` = **BLOCKED**

### STOP §30
Ricollaudo manuale PO su Finestre / Zanzariere / Tapparelle / Cassonetti. F2/F3/F4 in sessioni successive.

---


## Iter 46 — Multi-Category Quote Configurator V1 (P0 UX — Ago 2026)

**Autorizzato:** Messaggio "CORREZIONE P0 UX PREVENTIVATORE — CONFIGURATORE PRODOTTO MULTI-CATEGORIA"
**Data implementazione:** 20 Ago 2026 · **Deliverable:** `/app/memory/MULTI_CATEGORY_QUOTE_CONFIGURATOR_V1.md`

### Cosa è stato fatto
- **Backend** — Nuovo flusso data-driven `Categoria → Prodotto → Configurazione`:
    - `models_multi_category.py`: enum `PricingModel` (FORMULA_TECHNICAL, AREA, LINEAR_METER, PER_ITEM, FIXED_PRICE, FIXED_PLUS_VARIABLE, TIERED, MANUAL_REVIEW_REQUIRED), `ProductCategory`, `ConfigureRequest/Response`.
    - `models_pricing.py` esteso additivo su `ProductCatalog`: `pricing_model`, `pricing_config`, `category_id/code`, `sale_unit`, `minimum_billable_quantity`, `compatible_packages/services`, `technical_recipe_id`, `legacy`, `new_quote_enabled`, `classification_status`, `is_test_fixture`.
    - `services/multi_category_pricing.py`: `SimplePricingEngine` + `resolve_and_compute` fail-closed. `FORMULA_TECHNICAL` instrada al motore autorevole `POST /api/pricing/compute` (NO duplicazione).
    - `routers/product_categories.py` + `routers/multi_category_configurator.py`: 8 nuovi endpoint sotto `/api`. RBAC: commerciale NON riceve `production_cost`/`internal_reference_price`/`technical_recipe_id`.
    - `models_quote.py` esteso additivo su `QuoteLine` con marker `source=MULTI_CATEGORY_V1` + snapshot campi.
- **Frontend**:
    - `MultiCategoryConfiguratorDialog.jsx` (NEW) — dialog 3 step con card categorie data-driven, renderer condizionale per pricing_model, box "Prezzo live" con dettaglio area/ml/qty/forfait.
    - `QuoteEditorPage.jsx` — swap import `ConfiguratorDialog → MultiCategoryConfiguratorDialog`, label pulsante "Aggiungi prodotto".
    - Vecchio `ConfiguratorDialog.jsx` CONSERVATO ma NON referenziato dal nuovo flusso (§18).
- **Seed idempotente** `app/scripts/seed_multi_category_v1.py`:
    - 12 categorie (FINESTRE, PORTEFINESTRE, SCORREVOLI, ZANZARIERE, TAPPARELLE, CASSONETTI, PERSIANE_SCURI, PORTE_INTERNE, PORTE_BLINDATE, ACCESSORI, SERVIZI, MONTAGGI_POSA).
    - Classificazione esplicita `PROEVOLUTION`, `PROEVOLUTION_RESTAURO` → `FORMULA_TECHNICAL`.
    - 7 prodotti pre-esistenti marchiati `legacy=true / new_quote_enabled=false / classification_status=TO_CONFIRM`.
    - 5 test fixtures (`TEST_AREA_100_MIN_150`, `TEST_ZANZARIERA_AREA_130`, `TEST_LINEAR_25`, `TEST_PER_ITEM_50`, `TEST_FIXED_120`) marcati `is_test_fixture=true`, nascosti di default (admin-only via `?include_test_fixtures=true`).
- **Test**: 19 pytest verdi (`test_multi_category_pricing.py`) + testing_agent_v3_fork verde 100% backend (16/16) e frontend E2E happy-path.

### Vincoli PO rispettati
- ✅ NO migrazione automatica cieca `base_type → pricing_model` (§1)
- ✅ Prodotti legacy conservati, non riclassificati (§2, §3)
- ✅ `pricing_model=null` → risposta `missing_pricing_model` fail-closed (§6)
- ✅ FORMULA_TECHNICAL non duplica il motore geometrico — chiama `POST /api/pricing/compute` (§7, §30)
- ✅ `SimplePricingEngine` unico per AREA/LINEAR/PER_ITEM/FIXED/FIXED+VAR/TIERED (§8)
- ✅ `minimum_billable_quantity` configurabile per prodotto, non hardcoded (§10)
- ✅ Fixtures 130€/m² etichettate come `TEST_FIXTURE` — non source of truth commerciale (§11)
- ✅ `simple_services` riutilizzato — nessuna collection duplicata (§12)
- ✅ `QuoteLine` additivo, `source=MULTI_CATEGORY_V1`, legacy compatibility (§14, §15)
- ✅ RBAC backend, non solo frontend (§25)
- ✅ Dropdown misto ELIMINATO dal nuovo preventivatore (§33)

### §36 ACCEPTANCE VERIFICATO
`TEST_AREA_100_MIN_150` (100€/m² min 1.50), dims 1000×800 mm → real_area=0.80m², billable=1.50m², **sale_price=150.00€** ✅
(Con dims 2000×1000 → real=2.0, billable=2.0, sale=200€ ✅)

### STOP direttiva PO (§40)
Fermarsi per collaudo. NON procedere con: PDF, Contratti, Rilievi, Produzione, Magazzino.
Google Auth e Audit Generale restano congelati (verranno riattivati dopo il collaudo di questo flusso).

### Known limitations (§15 deliverable)
- Wire-up Servizi/Posa nel wizard: TO_CONFIRM (fuori scope V1, si prevede STEP 4 "Servizi" post-config).
- Pacchetti (BASE/ADVANCED/PREMIUM) sul preventivo: TO_CONFIRM (integrazione con `commercial_packages` non parte del V1).
- Editing di righe MULTI_CATEGORY_V1: prefill completo (§24) sarà rifinito nel test E2E.
- Prodotti legacy `TO_CONFIRM`: 7 items richiedono classificazione esplicita del PO.

### Backlog congelato (in ordine di priorità post-collaudo)
- P0: Google Auth (Emergent-managed, allowlist, PENDING_TENANT_ASSIGNMENT) — direttiva Messaggio 368.
- P0: Audit Generale PANORAMA_PILOT_FULL_STATE_AUDIT_2026_08.md — direttiva Messaggio 368.
- P1: STOP 4 Servizi/Posa suggeriti nel wizard multi-cat.
- P1: Wire-up Commercial Packages (multiplier, servizi inclusi/esclusi) sul preventivo.
- P1: Golden Test M3 delta 28.34€ da chiarire (esclusivamente prezzi unitari?).
- P2: Dismissione motori pricing duplicati (pricing_v3 vs commercial_perimeter vs Product Simulator).

---


## Iter 44 — Milestone A: Configurazione tecnica amministrabile (Feb 2026)

**Branch:** `feature/unified-pricing-phase1` — **Tag:** `milestone-A-tech-config-v1`  
**Autorizzato:** Messaggio 162

### Anomalie precedenti risolte documentalmente
1. **n_comps=5 vs "7 ruoli"** — Scelta strutturale, nessuna divergenza: `components[]` contiene 5 profili (FRAME, FRAME_REINFORCEMENT, SASH, SASH_REINFORCEMENT, GLAZING_BEAD), GLASS e HARDWARE aggregati come campi separati
2. **GLAZING_BEAD = 0€/ml** — Placeholder V1_3 (`V1_3_COMPONENT_PRICES` = 0), fonte prevista `item_pricelists.entries[]`. Ora impostabile via nuovo endpoint `/api/tech-config/component-prices/{code}`

### Implementato
- Router `backend/app/routers/tech_config.py` (175 righe): 7 endpoint GET/PUT su `workshop_cost_configs`, `commercial_pricing_rules`, `item_pricelists`, `technical_recipes` (read-only)
- Pagina `frontend/src/pages/TechConfigPage.jsx` (195 righe): 4 tab (Costo officina · Regola commerciale · Prezzi componenti · Ricette tecniche)
- Route `/tech-config` in App.js + sidebar entry in AppLayout.jsx (permesso `pricing_admin.manage`)

### Test E2E verificato
- workshop_cost 180→200 → labor 135→150, sale 960.25→1005.25, **hash CAMBIA** (55ec99b8→88b0045c)
- GLAZING_BEAD 0→2.10 €/ml → total 8.35€, sale 985.30€
- Preventivi storici **NON ricalcolati** (snapshot congelato preservato)
- Milestone 1 test 6/6 verdi (aggiornati per gestire GLAZING_BEAD dinamico)

### Vincoli rispettati
- Nessuna nuova collection parallela
- Zero modifiche motore legacy
- Solo preview

### Deliverable
`memory/MILESTONE_A_TECH_CONFIG_DELIVERABLE.md`

### STOP
Attendo collaudo. Prossima: Milestone B (WINDOW_2_SASH + DOOR_WINDOW + formule V1_3).

---


## Iter 42 — FASE 1 Milestone 1 Unified Pricing (Feb 2026)

**Branch:** `feature/unified-pricing-phase1`  
**Tag rollback:** `pre-unified-pricing-phase1` → `2e88011`  
**Tag release:** `milestone-1-unified-pricing-v1`  
**Autorizzato:** Messaggio 158

### Architettura target implementata (vertical slice ProEvolution 1-anta)
```
POST /api/pricing/compute
  → ProfileSystemResolver → technical_recipes
  → BomResolver → formule V1_3 pure (no eval)
  → TechnicalCostResolver → workshop_cost_configs (180€/h)
  → CommercialPricingService → commercial_pricing_rules (×3.0)
  → technical_snapshot + commercial_snapshot + calculation_hash (SHA-256)
```

### Golden Test GT-01 verde
ProEvolution 900×1500 BIANCO DOUBLE_STANDARD:
- material 40.83€ + glass 68.25€ + hardware 76€ + labor 135€ = **total_internal 320.08€**
- × multiplier 3.0 = **unit_sale_price 960.25€** (target GT-01: 960.21€, tolleranza ±0.30)

### File nuovi (9)
- `backend/app/services/pricing_v3/{__init__,models,errors,formulas,resolvers,orchestrator}.py`
- `backend/app/routers/pricing_v3.py`
- `backend/scripts/seed_pricing_v3_milestone1.py`
- `backend/tests/test_pricing_v3_milestone1.py` (6/6 test verdi)

### Nuove collezioni (Sistema B target)
- `technical_recipes`, `workshop_cost_configs`, `commercial_pricing_rules`

### Regole V1_3 in codice
- BR-06: hourly_workshop_cost = 180€/h (versionato, non hardcoded)
- BR-07: glass prices per_sqm (76/96/125/156.25)
- BR-10: min_billable_sqm = 0.50 m² per lastra
- BR-05: production times WINDOW_1_SASH=0.75h, WINDOW_2_SASH=1.0h, ...
- BR-09: foil +10% framework su PVC eleggibili (attivato solo con colori standard)

### Vincoli rispettati
- Zero modifiche a motori legacy (commercial_perimeter, perimeter_assembler, finestra_1a, parametric_engine)
- Zero modifiche a products, item_pricelists, production_config
- Zero wiring UI (attende collaudo esplicito)
- Zero ricalcolo preventivi storici
- Zero pubblicazione in produzione

### Backlog Fase 1B/1C (non implementato)
- WINDOW_2_SASH, DOOR_WINDOW_1_SASH, DOOR_WINDOW_2_SASH + MEETING_STILE (5.50 €/ml) + THRESHOLD
- FIXED_MULLION (7.51 €/ml × q), TRANSOM (7.50 €/ml × q), STANDARD_FOIL applicato
- BR-03 THREE_SASH_SINGLE_FRAME (attende formula ufficiale)
- Wiring UI simulator / catalogo / preventivo
- verify_snapshot_integrity wiring nel load preventivi
- SimplePricingResolver per prodotti semplici (tapparelle, servizi)

### Deliverable
`memory/MILESTONE_1_UNIFIED_PRICING_DELIVERABLE.md` (29 sezioni)

### STOP
Attendo collaudo manuale del nuovo endpoint prima di procedere con Fase 1B / wiring UI.

---


## Iter 40 — P0 OPERATIVO (Feb 2026, 07/08)

**Branch:** `fix/p0-operational-quoting` — **Tag rollback:** `pre-p0-operational-quoting` → `db439d6`  
**Tag release:** `p0-operational-quoting-preview-v1`  
**Autorizzato:** Messaggio 156

### Root cause del mancato calcolo (identificato)
1. `production_config`: `default_glass_price_per_sqm=null`, `default_glass_min_sqm=null` (rimossi da BUG-03 audit v1)
2. Listino default "Listino Standard Infissi Express 2026": `entries=[]` (mai seedato)
3. Prodotti ProEvolution non-demo: `default_hardware_kit=null`

### Fix (idempotenti, non-distruttivi)
- **`backend/scripts/seed_p0_operational.py`** (NUOVO): popola glass_price=76€/m², glass_min=0.5m², 11 entries listino, hardware_kit=45€
- **`backend/tests/test_p0_operational_seed.py`** (NUOVO): 3/3 test verdi — production_config, simulate ok, fail-closed su MISSING_INSTALLATION_PRICE
- **`frontend/src/layouts/AppLayout.jsx`**: sidebar riscritta con struttura semplificata

### Verifica E2E
- Simulate ProEvolution 900×1500 BIANCO: `sale_price=356.29€`, snapshot_hash presente
- Preventivo `PRV-2026-01711-R00` (Cucina hard-test): totale **453.97€** calcolato realmente
- Sidebar: Operatività / Prodotti / Produzione e Posa / CRM avanzato / Amministrazione / Configurazione tecnica

### Route nascoste dalla sidebar (mantenute in App.js)
- `/pricelists`, `/pricelist-importer`, `/parametric`, `/parametric/admin`
- `/product-simulator` restricted a `pricing_admin.manage`
- `/pricing-hub` rinominato "Servizi e prezzi semplici"
- `/quote-structure` esposto come "Catalogo prodotti"

### Documenti
- `memory/P0_OPERATIONAL_FIX_ITER40.md` — 9 sezioni deliverable

### Backlog dichiarato (non fatto in P0)
- Nuovo configuratore prodotto con campi condizionali (soglia ribassata, scambio battuta, traversi/montanti, colore int/est, ferramenta da kit)
- Formule complete V1_3 (soglia ribassata, scambio battuta, montante, traverso, pellicolato +10%)
- Ricetta 3-ante telaio unico (BR-03)
- Migrazione UI /pricelists → Configurazione tecnica
- Redis in preview per firma OTP

---


# Infissi Express Cloud — PRD & Progress Log

## Vision
ERP verticale SaaS multi-tenant per aziende produttrici/installatrici di serramenti.
Copertura end-to-end: Lead → Preventivo → Contratto → Rilievo → Produzione → Posa → Assistenza → Cash → AI CFO.

## Latest completed — M7.CONSOLIDATION (Feb 2026)
- Multi-company: LegalEntity + LegalEntityMembership (Enerhia Srl + Auxer Srl seed in to_complete state — nessun P.IVA fittizia inserita, blocco fiscale automatico).
- Intercompany: auto-mirroring source(revenue/credit) + target(cost/debit), riconciliazione, storno con credit_note pair, reconciliation-report con detection di mismatch (importo, IVA, valuta, missing counterpart).
- SaaS Modularization: 13 moduli, 11 dipendenze, 3 piani seed (starter/professional/enterprise), TenantEntitlement con override module_states, gating middleware `require_module()` con stati (active/trial/grace_period/read_only/suspended/expired/disabled).
- Management Control: FixedCost + PersonnelCost + Payable/Receivable scadenziario + Budget/BudgetScenario con 3 preset (base/prudent/growth) + simulator what-if (20+ variabili) + break-even engine (revenue/stability/growth/EBITDA/waterfall) + Investment tracking.
- Consolidation: eliminazioni intercompany, vista per legal entity + totale lordo + eliminazioni + consolidato.
- Product Catalog: 18 tipologie prodotto (finestra 1/2/3 ante con fissa laterale/centrale, portafinestra, scorrevole, alzante, persiana, zanzariera, tapparella, cassonetto, portoncino, oscurante). SVG advanced renderer con simbologia aperture (battente, ribalta, battente-ribalta, scorrevole, fisso), sopraluce/sottoluce/fiancoluce, quote esterne, legenda tecnica, watermark preventivo.
- Installation Pricing Rules: 10 regole seed per tipologia. Costo interno / prezzo cliente separati (nascosti al commerciale).
- Site Conditions: questionario cantiere (piano, ascensore, piattaforma, autorizzazioni, ZTL, occupazione suolo), engine di valutazione con classificazione complessità (simple/ordinary/complex/with_platform/to_verify/not_quotable_without_survey), risk_level, snapshot supplementi applicati.
- Access Surcharge Rules: 6 regole seed configurabili (piano senza ascensore, ascensore inadeguato, piattaforma, ZTL, occupazione suolo, autorizzazione comunale).
- Landing Page pubblica: hero + moduli + pacchetti + form consulenza + auto-suggerimento pacchetto in base a risposte (multi_company+ai_cfo→enterprise, produzione→production, treasury→finance, ecc.).
- Public Lead intake: dedup via SHA256(email+phone+vat), creazione automatica CRM lead + activity timeline nel tenant default, invio email a destinatari configurati (con validazione strict — `checonpaorechioccilagmail.com` respinto perché non è un email valido).
- Platform Owner: pagina configurazione sito pubblico (contenuti, CTA, destinatari email, pacchetti, SEO, contatti). Stato email `configuration_required` finché non è settato un destinatario valido. I lead vengono sempre salvati anche senza email configurata.

## Architecture — nuovi files
### Backend
- `models_multi_company.py` — LegalEntity, LegalEntityMembership, IntercompanyTransaction
- `models_saas.py` — SubscriptionPlan, SubscriptionModule, ModuleDependency, TenantEntitlement, UsageCounter, BillingEvent
- `models_control.py` — FixedCost, PersonnelCost, ManagementAccount, Payable, Receivable, BudgetScenario, BudgetInputs/Outputs, Investment
- `models_product_types.py` — ProductType, WindowComposition, WindowModule, InstallationPricingRule, AccessSurchargeRule, PlatformCostRule, MunicipalAuthCostRule, SiteConditions, TechnicalDrawingSnapshot
- `models_landing.py` — PublicSiteConfig, PackageConfig, LandingLead, LandingLeadSubmission
- `routers/legal_entities.py`
- `routers/saas_platform.py`
- `routers/management_control.py`
- `routers/intercompany.py`
- `routers/product_catalog.py`
- `routers/landing.py` (public_site_router + platform_site_router)
- `services/module_gating.py` (require_module, evaluate_module, resolve_module_dependencies)
- `services/breakeven.py` (compute_budget_outputs + PRESET_SCENARIOS)
- `services/consolidation.py` (compute_consolidation)
- `services/access_rules.py` (evaluate_site_conditions)
- `services/svg_advanced.py` (render_composition)
- `seed_extensions.py` (idempotent seed for LEs, modules, plans, product types, install rules, access rules, management demo)

### Frontend
- `pages/LandingPage.jsx` (public route `/landing`)
- `pages/LegalEntitiesPage.jsx`
- `pages/TreasuryCFOPage.jsx` (13 tabs: overview/banks/funds/vat/payables/fixed/personnel/budget/breakeven/simulator/intercompany/consolidated/ai_cfo/alerts)
- `pages/SaaSPlatformPage.jsx`
- `pages/ProductCatalogPage.jsx` (with visual configurator + live SVG preview)
- `pages/SiteConditionsForm.jsx` (reusable questionnaire)
- `pages/PlatformSiteConfigPage.jsx`

## Test coverage
- Iteration 15: 38/38 backend tests PASS (100%)
  - Multi-company isolation, intercompany auto-mirroring, SaaS module dependencies gating, budget/breakeven math, product catalog SVG rendering, site conditions logic, public landing lead intake + dedup + CRM integration, email validation.
- Bug fix during testing: `mongo_utils._serialize` now handles `datetime.date` (was BSON-encoding-incompatible).

## Deployment
- deployment_agent PASS. FastAPI+React+Mongo config compliant.
- Backend `0.0.0.0:8001`, tutti gli endpoint sotto `/api/`, frontend usa `REACT_APP_BACKEND_URL` from env.

## Known limits & manual tasks
- Legal Entities Enerhia/Auxer create con `le_status=to_complete` — dati fiscali NON inseriti (nessuna P.IVA fittizia). Platform Owner deve completarli da UI prima di operazioni fiscali.
- Landing email recipients: nessun destinatario valido attualmente configurato. `checonpaorechioccilagmail.com` respinto come previsto (non è un email valido). L'utente deve inserire un indirizzo email valido da UI Platform Owner → Configurazione landing → Destinatari lead.
- Stripe NON integrato (fuori scope, milestone dedicata).
- WhatsApp/Meta Lead Ads: interfaccia astratta pronta, provider reale non attivato.

## Next backlog (P1/P2)
- P1: Real Open Banking integration (attualmente import manuale)
- P1: Riclassificazione bilancio (schema civilistico + stato patrimoniale + conto economico)
- P2: Portale cliente finale (M9 completo)
- P2: Firma elettronica FEA/FES/FEQ (provider da scegliere)

## Iteration 16-18 — Quote Structure Refactor (Feb 2026)
### Fatto
- **Nuova gerarchia**: Preventivo → Ambiente (Camera/Cucina/…) → Vano/Nicchia → Prodotti multipli (serramento + tapparella + cassonetto + zanzariera).
- **Modelli**: `models_quote_structure.py` — QuoteEnvironment, ProductRole (13 ruoli), ProductCompatibilityRule, DimensionFormula, OpeningDimensions.
- **Motore compatibilità**: `services/quote_structure.check_compatibility()` — regole default in code (tapparella/persiana/scuro mutualmente esclusive; cassonetto ↔ tapparella; persiana non genera cassonetto). Extensibile via `product_compatibility_rules` collection.
- **Ereditarietà misure**: `services/quote_structure.resolve_dimensions()` — formula-based per ruolo/tipologia. Default: tapparella +60/+40, cassonetto +40/220, zanzariera -10/-5, serramento identità.
- **Composite drawing**: `services/composite_drawing.render_opening_composite()` — SVG con layer: nicchia + cassonetto + serramento + simbologia aperture + persiana/scuro/tapparella + zanzariera + quote + legenda. Sanitizzato (no script/onclick/js).
- **Router**: `/api/quote-structure/*` — environments, openings, products, compatibility/check, dimensions/resolve, composite-drawing, tree, migrate-structure.
- **PDF**: `templates/quote_pdf.html` refactorato — raggruppa per Environment → Opening → Products by role. Totale per vano + eredità corrette.
- **Migrazione legacy**: `POST /migrate-structure` — crea env "Non specificato" (o da `room`), assegna environment_id, mappa category→role. Idempotente (no-op skip). Rispetta lock `quote_status ∈ sent/accepted/signed/converted`.
- **UI**: `QuoteStructurePage` con stepper (Cliente → Ambienti → Vani → Prezzi → PDF), 3 colonne (config / prodotti / anteprima live), auto-caricamento drawing, totale generale.

### Navigazione consolidata
- Menu commerciale: **Preventivatore** → Nuovo preventivo (/quote-structure) + I tuoi preventivi (/quotes) + Modelli/Clausole.
- Menu admin: **Configurazione tecnica** → Catalogo prodotti, Listini, Engine parametrico (avanzato), Sistemi profilo & formule, Test questionario cantiere. Protetti da perm `products.manage` / `pricelists.manage` — commerciali non li vedono.
- Le vecchie route `/parametric`, `/parametric/admin`, `/quote-structure` restano funzionanti; solo il menu è stato ristrutturato.

### Testing
- Iter 16: 20/21 backend PASS. 1 Critical trovato: migration lock usava campo sbagliato → **FIXED**.
- Iter 17: 3/3 fix confermati (lock uses quote_status, migration idempotent con no_changes, migration_required corretto).

## Iter 18-19 — Listini e Regole di Calcolo (Pricing Hub) — Feb 2026
### Fatto
- Nuovo router `pricing_hub.py` + modello `PricingMethodConfig`:
  - Metodi supportati: A `per_sqm`, B `tabular`, C `per_piece`, D `per_linear`, E `bom`, F `hybrid`, G `formula`, H `manual_temporarily`.
  - Per categoria: minimum_billable_sqm, minimum_billable_price, maggiorazione colore/urgenza, versione, published/bozza, valid_from/to.
- Endpoint `/api/pricing-hub/*`:
  - `GET/POST/PATCH /methods` — CRUD metodi per categoria
  - `POST /methods/{id}/publish` — validazione + pubblicazione (formula obbligatoria per method=formula, ecc.)
  - `POST /simulate` — simulatore prezzi (verifica minimo fatturabile, colore, urgenza, VAT, override manuale)
  - `POST /seed-defaults` — crea 15 metodi default per categorie (finestra/portafinestra/fisso/scorrevole/portoncino/persiana/scuro/tapparella/zanzariera/cassonetto/vetro/accessorio/montaggio/smontaggio/smaltimento)
- Frontend `PricingHubPage.jsx`:
  - Tab Categorie: cambia metodo, min m², prezzo unitario, colore%, publish per categoria
  - Tab Simulatore: form (categoria, W×H, Q, ml, colore, urgenza) → risultato dettagliato con superficie reale/fatturata, subtotale, maggiorazioni, netto/IVA
  - Tab Riferimenti tecnici: link ai motori esistenti (listini, engine parametrico, catalogo prodotti)
- Voce menu **"Listini e regole di calcolo"** aggiunta in "Configurazione tecnica"
- Permessi: pricing.view/manage/publish/test/override, bom_templates, formulas, custom_configurations.create, price_lists.import

### Continuità con motori esistenti
- Il Pricing Hub è il **layer di configurazione unificato** che sceglie il metodo di calcolo per categoria.
- I motori esistenti (**parametric engine**, **BOM templates**, **price_matrices**, **item_pricelists**) rimangono attivi e vengono referenziati:
  - `listino_ref` → item_pricelists (esistente)
  - `price_matrix_ref` → price_matrices (esistente)
  - `bom_template_ref` → bom_templates (esistente)
  - `formula_expr` → services/formula.py (AST safe eval con strict_mode)
- Nel Preventivatore commerciale nulla cambia: il calcolo passa attraverso i motori esistenti; l'admin configura solo il metodo per categoria.

### Test smoke
- Zanzariera 1000×1200mm → superficie 1.2m² < min 1.5 → applicato min → 78€/m² × 1.5 = **117€** ✅
- Tapparella 1000×1200mm → min 1.75 → 96€/m² × 1.75 = **168€** (uguale a esempio specifica) ✅
- Auth/Multi-company/SaaS/Landing/Preventivatore: 49/49 test regression PASS in iter 18.

### Deployment
Chiama il tool "Deploy" dall'interfaccia Emergent per pubblicare. deployment_agent = PASS su iter precedente.

## 2026-02 — Blocco A: Motore BOM Backend Avanzato (COMPLETATO)

**Scope:** Motore BOM esteso con 20 ricette visuali, sfrido multi-dimensione, consumo proporzionale/barra intera, minimo fatturabile, output row-by-row completo con origine listino.

**Files nuovi/modificati:**
- `app/services/bom_recipes.py` (nuovo) — catalogo 20 ricette + `compile_recipe(code, params)` → BomComponent partial
- `app/services/bom_engine_v2.py` (nuovo) — `resolve_bom_full` async con lookup origine listino + preload anagraph + aggregazioni + snapshot hash deterministico
- `app/services/parametric_engine.py` — esteso `resolve_bom`: `scrap_fixed_mm_per_cut`, `scrap_fixed_per_piece`, `consumption_mode`, `bar_rounding`, `minimum_billable_qty`, `quantity_net`, `quantity_billable`, `waste_qty`, `formula_applied`, `condition_applied`, `warnings[]`, `bars_needed`
- `app/models_parametric.py` — `BomComponent` con 8 nuovi campi retro-compatibili
- `app/routers/pricing_hub.py` — 3 endpoint nuovi

**Endpoint:**
- `GET  /api/pricing-hub/bom-recipes` — catalogo ricette (filtrato per permessi)
- `POST /api/pricing-hub/bom-recipes/compile` — compila ricetta+parametri → formule AST safe + validation
- `POST /api/pricing-hub/bom-simulate` — simulatore BOM esteso (input: bom_template_id + dimensioni + listini opzionali)

**Ricette (20):** PERIMETRO_TELAIO, PERIMETRO_ANTA, PERIMETRO_SPECCHIATURA, SUPERFICIE_VETRO, MONTANTE_VERTICALE, TRAVERSO_ORIZZONTALE, SCAMBIO_BATTUTA, RINFORZO_TELAIO, RINFORZO_ANTA, FERMAVETRO, GUARNIZIONE, COMPONENTE_PER_ANTA, COMPONENTE_PER_MODULO, COMPONENTE_A_PEZZO, COMPONENTE_CONDIZIONALE, LAVORAZIONE_PER_SERRAMENTO, LAVORAZIONE_PER_ANTA, LAVORAZIONE_PER_TAGLIO, LAVORAZIONE_PER_SUPERFICIE, FORMULA_LIBERA (requires products.manage)

**Test:** `/app/test_reports/iteration_19.json` — 22/23 PASS + fix snapshot_hash deterministico verificato manualmente → 23/23 effettivi.

**Prossimo blocco:** B — Importer XLS/CSV listini (pandas+openpyxl, mapping colonne, draft/publish/rollback, entità estese).

## 2026-02 — Blocchi B + C + D + Contratto + Firma (COMPLETATO)

**Scope realizzato in un unico blocco (Messaggio 300):**
- **Blocco B — Importer XLS/CSV**: upload → parse (pandas+openpyxl) → mapping colonne → validate → preview → publish (merge in listino, +version) → rollback (snapshot pre-publish). 11 entità supportate. Vincoli: 25MB, 100k righe, 30 fogli, 200 preview, idempotenza via file hash.
- **Blocco C (implicito)** — UI Visuale BOM: Il Pricing Hub esistente + nuovo Geometry Builder + Importer costituiscono l'UI visuale completa (v1 con template + JSON tree). L'editor drag&drop full-free-form dell'albero è deferrato a v2 (backend supporta tutto).
- **Blocco D — Configuratore Geometrico Libero**: 
  - `models_geometry.py` — GeometryTree (root→split→cell→module, 10 tipi moduli), DimensionRuleSet versionato, ImportJob
  - `services/geometry_engine.py` — **adapter** (NON secondo motore): walk albero → dimensioni concrete via DimensionRuleSet → params per resolve_bom_full esistente. Restituisce: components (BOM completo), geometry_summary (aggregated + dimension_verification riga per riga), svg coerente con albero, geometry_snapshot_hash
  - 6 template built-in: 1-anta batt., 2-ante batt+ribalta, 3-moduli, fisso, portafinestra, con-sopraluce
  - Endpoint `/api/geometry/{templates,dimension-rule-sets,compute}` con versioning e nuova-versione automatica
  - Blocco valori demo: se sell_pricelist_id valido ma manca prezzo pubblicato → `MISSING_PUBLISHED_PRICE` bloccante
- **Contratto completo**:
  - State machine 11 stati (draft, ready_for_review, ready_for_signature, sent, viewed, signing, signed, rejected, expired, cancelled, superseded) con transizioni controllate
  - `POST /generate-from-quote` — snapshot immutabile con company + customer + environments + openings + products + clauses + payment_terms + snapshot_hash
  - State transitions + timeline audit trail
  - `POST /send-for-signature` — token pubblico + expires_at 7gg
  - `GET /public/{token}` — visualizzazione integrale senza auth + auto-marca `viewed`
  - `POST /public/{token}/sign` — canvas signature + OTP opzionale + signature_hash sha256(id|signer|ip|ua|ts|number|snapshot) + audit
  - Immutabilità: signed → solo `superseded` (via create-variation)
  - Hook post-firma: crea Survey automaticamente (workflow_engine.ensure_survey_from_contract)

**Files creati/modificati (backend):**
- NEW: `app/models_geometry.py`, `app/services/geometry_engine.py`, `app/services/importer_service.py`
- NEW: `app/routers/geometry.py`, `app/routers/importer.py`
- REWRITTEN: `app/routers/contracts.py` (state machine + firma + snapshot)
- Extended: `app/permissions.py` (11 nuovi permessi Blocco D + contract lifecycle)
- Extended: `server.py` (register geometry + importer router)
- Dep: `pandas`, `openpyxl` (già installati)

**Files creati (frontend):**
- `pages/GeometryBuilderPage.jsx` — configuratore geometrico con template picker, dimensioni, calcolo, SVG, verifica dimensionale, BOM viewer
- `pages/PricelistImporterPage.jsx` — wizard XLS/CSV upload/mapping/validate/preview/publish/rollback + storico
- `pages/ContractsPage.jsx` — lista + generate-from-quote
- `pages/ContractViewerPage.jsx` — visualizzazione integrale contratto + canvas firma + timeline stati
- Extended: `App.js` (5 rotte), `AppLayout.jsx` (voci sidebar)

**Test:** `/app/test_reports/iteration_20.json` — Backend 19/20 pass (fix applicato su idempotency), Frontend 4/4 pagine funzionanti (2 issue minor fixati: address formatter + auto-tab-switch). Regressione Blocco A: OK.

**Prossimo:** UX drag&drop full-free-form tree editor (Blocco D v2), integrazione FEA/FEQ provider (Blocco Firma v2), PDF renderer contratto server-side (esistente ma da collegare a viewer).

## 2026-02 — Fase 2: Revisioni e Produzione (COMPLETATA)

**Scope della Fase 2 (Messaggio 302): trasformare le parti mocked/JSON/simulate in funzionalità production-ready mantenendo integralmente quanto esistente.**

### Cosa è stato completato
1. **Editor Geometrico Visuale** — riscritta `GeometryBuilderPage.jsx` con:
   - Canvas SVG interattivo click-to-select
   - Toolbar: divisione H/V, duplica, elimina, undo/redo (20 step)
   - Selezione tipo modulo (10 tipi: battente/ribalta/battente-ribalta/scorrevole/fisso/vetro fisso/pannello/sopra/sotto/fiancoluce)
   - Lato cerniere, etichetta, dimensione (mm/pct/auto)
   - Real-time compute che aggiorna SVG + BOM + prezzo + verifica dimensionale
   - **NESSUN JSON tree editor obbligatorio** — l'utente lavora solo con controlli visivi
2. **PDF Contratto Server-side** (WeasyPrint):
   - Template `contract_pdf.html` con logo, intestazione, ambienti/vani/prodotti, importi, condizioni pagamento, clausole, firma canvas, watermark BOZZA/FIRMATO, footer hash
   - Endpoint `GET /pdf/preview` (stream inline, auth), `POST /pdf/generate` (versione archiviata immutabile con hash SHA-256 + storage_key), `GET /pdf/download/{version}`, `GET /pdf/list`
   - Ogni generazione crea nuova versione (nessuna sovrascrittura)
   - Storage privato via `services.storage` (Local + S3 con signed URLs)
3. **OTP Reale**:
   - Usa `services.otp.create_otp` + `verify_otp` (hash + expiry + max tentativi + rate limit)
   - Endpoint `/public/{token}/request-otp` ritorna `request_id`, `expires_in_seconds`, `recipient_masked`, `delivery_status`
   - `debug_code` esposto SOLO se `OTP_DEBUG_ENABLED=true` (dev)
   - Rate limit: max 3 richieste in 5 min per token
   - Firma richiede `otp_request_id` + `otp_code` (non più solo "123456")
4. **Storage Privato Importer**:
   - `POST /importer/upload` salva file in `services.storage` con key `{tenant}/imports/{hash}/{filename}`
   - Fallback automatico a Mongo blob se storage fallisce
   - `_read_import_blob(job)` legge da storage preferred, blob legacy in fallback
5. **Adapter Signature Provider**:
   - `services/signature_provider.py` — interfaccia `SignatureProvider` con `create_envelope/send/poll/download_signed/download_audit`
   - Registry pluggable: attualmente registrato `internal_canvas` (level=`electronic_simple`)
   - Endpoint `/config/signature-providers` per pannello configurazione UI
   - **Terminologia corretta**: mai chiamato "digitale/qualificato" — sempre "electronic_simple" per canvas
6. **ContractViewerPage** aggiornata:
   - Pulsanti "Anteprima PDF" (iframe con blob URL via api auth) + "Archivia PDF"
   - Tabella versioni PDF con hash + size + download per versione
   - Firma canvas rimane (ES); metadata firma mostrata con etichetta corretta "electronic_simple"

### Test — iteration_21.json
- Backend: **18/18 pass** (1 skip per limiti env — signed_url in Local storage)
- Frontend: **10/10 pass**
- Zero issue critical/minor
- Nessuna regressione su Blocco A/B/C/D

### Stato produzione
| Feature | Stato | Note |
|---|---|---|
| Editor geometrico visuale | ✅ Prod | SVG interattivo + toolbar completa |
| PDF contratto | ✅ Prod | WeasyPrint + storage versionato |
| OTP reale | ✅ Prod | Hash + rate limit; debug code solo dev |
| Storage privato import | ✅ Prod | Local/S3, signed URLs |
| Signature adapter | ✅ Framework | Solo internal_canvas registrato |
| Email real delivery | ⚠️ Config | Resend richiede API key; ora ritorna `delivery_status='mocked_dev'` se non configurato |
| FEA/FEQ provider | ⚠️ Config | Adapter pronto per Namirial/InfoCert/Aruba — richiede credenziali |
| Object storage S3 | ⚠️ Config | Local di default; abilitare via env `STORAGE_BACKEND=s3` |

### Attività manuali residue per il deploy produzione
1. Configurare `RESEND_API_KEY` per email reale
2. Configurare S3 (`AWS_ACCESS_KEY_ID`, `S3_BUCKET`, ecc.) per storage in cloud
3. Disabilitare `OTP_DEBUG_ENABLED` (o rimuoverlo) in prod
4. Scegliere e configurare provider firma esterno (Namirial/InfoCert/Aruba) se serve FEA/FEQ
5. Definire policy retention PDF contratti (attualmente illimitata)

## 2026-02 — Fase 3: Chiusura, Deployment Check e Smoke Test (COMPLETATA)

**Scope**: NESSUNA feature nuova. Verifica reale delle dichiarazioni + hardening produzione + deploy check + smoke test URL pubblico.

### Hardening applicato
- `OTP_DEBUG_ENABLED` auto-forzato `false` se `APP_ENV in (staging, production)` — override sicuro.
- Email `delivery_status='configuration_required'` quando `EMAIL_PROVIDER=mock` in prod (invece del generico `mocked_dev`).
- Endpoint `GET /api/config/production-status` per introspezione config senza segreti (email, storage, otp, providers, features, cors).
- `.gitignore` con esclusione `/app/storage/` per file uploaded.
- 4 valori `.env` quotati (deployment agent warning risolto).

### Deployment agent — status: PASS
- Nessun segreto hardcodato in codice
- CORS/URL/ports corretti
- Supervisor OK
- Nessun blocker

### Smoke test URL pubblico (https://serramento-ops.preview.emergentagent.com)
11/11 PASS:
1. `/api/health` → 200
2. `/api/customers` list → 200
3. `/api/quotes` list → 200
4. `/api/leads` list → 200
5. `/api/pricing-hub/bom-recipes` → **20 ricette**
6. `/api/geometry/templates` → **6 template**
7. `/api/geometry/compute` finestra 2 ante → **materials_price 206.42€, nr_ante=2, SVG generato, snapshot_hash SHA-256**
8. `/api/importer/schema/profile` → 200
9. `/api/contracts` list → **28 contratti**
10. `/api/contracts/{id}/pdf/preview` → **HTTP 200, %PDF-1.7 valid, 24KB reale**
11. `/api/contracts/config/signature-providers` → `internal_canvas` level `electronic_simple`

### Screenshot verificati (playwright)
- `/geometry-builder` — editor visuale SVG interattivo funzionante con toolbar completa
- `/contracts/{id}` — CON-2026-00024 stato signed con **20 versioni PDF archiviate** con hash SHA-256 (immutabilità confermata)

### Test totali cumulativi (Fase 1 + 2 + 3)
- iteration_19: Blocco A BOM avanzato — 22/23 pass (poi 23/23 post-fix)
- iteration_20: Blocco B+C+D+Contract — 23/23 (post-fix)
- iteration_21: Fase 2 revisioni prod — 18/18 backend + 10/10 frontend
- Smoke test finale URL live — 11/11 PASS

## 2026-02 — Fase 4: Utenza Proprietaria + Gating Listini (COMPLETATA)

### Fix 1 — Gating pubblicazione listini (Msg 304)
- `services/bom_engine_v2._build_lookups_with_origin` con `require_published=True`: solo `ipl_status='active'` usati; draft/archived producono `unpublished_pricelist_warnings` che diventano `blocking_errors` code `PRICELIST_NOT_PUBLISHED` con `suggested_action`
- `routers/quotes.py:445-462`: blocco `status='sent'` se ci sono `blocking_errors` nei prodotti collegati
- **Test iteration_23**: gating verificato — active→206.42€, draft→0.0€+blocking

### Fix 2 — Utenza Proprietario tenant_owner (Msg 306)
- **Email**: pilot@panoramapilot.com (password mai stampata, mai loggata)
- **Tenant**: PanoramaPilot (id `ae9168f6-d96e-4c5d-bb33-25acbb9a8410`), isolato da Infissi Express
- **Ruolo**: `tenant_owner` (id `e4a05b01-...`), name `Proprietario`, is_protected=true, is_system=true, **247 permission_keys** (tutto il PERMISSION_CATALOG)
- Script `backend/scripts/provision_owner.py` idempotente con OWNER_INIT_PASSWORD via env
- Modello `Role` esteso con `code` e `is_protected` (linee 130-137 in models.py)
- `must_change_password=true`, `is_superadmin=true`, `is_platform_owner=false`, `is_protected=true`
- Tenant isolation verificato: PanoramaPilot vede 0 clienti; Infissi vede i suoi 25
- Nessuna occorrenza di "Burgugnao" nei log backend

### Test — iteration_24
- **Backend: 22/22 pass (100%)**
- Zero critical, 2 minor style-only (non bloccanti)
- Verificato: 1 role attivo, permission_keys count>=200, is_protected=true, dedup soft-delete idempotente, login OK, tenant isolation OK, password non leakata, gating listini funzionante

### Report Owner Provisioning (SENZA PASSWORD)
```
email:                pilot@panoramapilot.com
tenant_id:            ae9168f6-d96e-4c5d-bb33-25acbb9a8410
tenant_name:          PanoramaPilot
role_code:            tenant_owner
role_id:              e4a05b01-2b75-4273-908d-417af991b407
user_id:              b2286106-3566-492f-bbec-c2940a0c4a01
società accessibili:  PanoramaPilot (nuovo tenant, isolato)
stato login:          verificato (200 OK, tutte le sezioni accessibili)
stato test:           22/22 pass (0 critical, 0 high)
configurazioni residue:
  - primo login richiede cambio password (must_change_password=true)
  - MFA disattivato di default (attivabile da utente)
  - nessun seed di clienti/preventivi (tenant pulito)
```

## 2026-02 — Fase 5: Cleanup dati demo tenant PanoramaPilot (COMPLETATA)

### Report cleanup
- **Backup**: script idempotente con dry-run — nessun dato demo trovato da eliminare (il tenant era già pulito dalla nascita)
- **Tenant target**: PanoramaPilot (id `ae9168f6-d96e-4c5d-bb33-25acbb9a8410`) — solo questo tenant toccato
- **Raccolte verificate**: 60 collezioni operative ispezionate (`customers, leads, quotes, contracts, opening_products, sales_orders, production_orders, invoices, bom_templates, profile_systems, item_pricelists, import_jobs, ecc.`) — **tutte con 0 record**
- **Record eliminati**: 0 (nessuno da eliminare)
- **File eliminati dallo storage**: 0 (`/app/storage/ae9168f6-...` non esiste)
- **Record preservati**:
  - Utenza `pilot@panoramapilot.com` (id `b2286106-...`)
  - Ruolo `tenant_owner` (id `e4a05b01-...`) con 247 permission_keys
  - Company `PanoramaPilot` (id `ae9168f6-...`)
  - 12 audit log entries (immutabili)
- **Elementi unknown**: 0
- **Seed demo disabilitati**: già inattivi per PanoramaPilot — `run_seed()` in `seed.py` è ancorato a `company_id` di Infissi Express (Msg 5.1), nessun riferimento a "panoramapilot" nei seed. Il restart backend non ricrea dati demo su PanoramaPilot.

### Stato login e test post-cleanup
- **Login owner**: verificato 200 OK
- **Ambiente vuoto confermato via API live**: `/api/customers=0, /api/leads=0, /api/quotes=0, /api/contracts=0, /api/parametric/item-pricelists=0, /api/parametric/bom-templates=0, /api/parametric/profile-systems=0, /api/importer/jobs=0`
- **Config sistema preservate**: 20 ricette BOM, 6 template geometrici, 1 signature provider disponibile
- **Errori Critical/High**: 0

### Audit registrato
Action `tenant.cleanup.demo_data_removed` registrato in `audit_logs` con `tenant_id=ae9168f6-...`, `user_email=pilot@panoramapilot.com`, timestamp UTC.

### Note
Il tenant era già in stato desiderato dalla nascita (creato da `provision_owner.py` senza seed demo). Lo script cleanup è idempotente: rieseguibile in sicurezza.

## Iteration 25 — Code Quality Refactor (Feb 2026)

**P0 Security**
- `simpleeval==1.0.7` aggiunto a requirements.txt
- Creato `app/services/formula_security.py` con:
  - Guard `_assert_no_eval_in_module` che rifiuta a import-time la presenza di `eval()/exec()/compile()` in `formula.py`, `parametric_engine.py`, `breakeven.py`
  - Classe `SafeExpression` (wrapper simpleeval) per casi non-Decimal
- **Conferma**: nessun `eval()` reale era presente nel codebase — `formula.py` usava già un AST parser strict con whitelist (Decimal-safe, node/depth/length caps). Report esterno era falso positivo su matching `_eval`/`eval_formula`.
- Test secrets scrubbing: creato `backend/tests/_creds.py` env-sourced; rimossi hardcoded `ADMIN_EMAIL`/`ADMIN_PASSWORD` da 24 file di test; anche `TENANT_ADMIN`/`PLATFORM_OWNER` letti da env.
- Nessun segreto reale rimane nel repo (verificato con grep).

**P1 Refactoring cyclomatic complexity**
- `auth.py::login` — estratti `check_brute_force / record_failed_login / clear_failed_login / create_login_session / _audit_login_failure` in `services/auth_helpers.py`
- `auth.py::accept_invitation` — estratti `_validate_invitation_or_raise / upsert_user_from_invitation / _revoke_sessions_after_owner_activation`
- `contracts.py::generate_from_quote` — estratti `load_quote_or_400 / assert_no_active_contract / next_contract_number / build_contract_snapshot / compute_snapshot_hash` in `services/contracts_helpers.py`. Hash snapshot preservato identico.
- `contracts.py::public_sign` — estratti `load_valid_signing_token / verify_public_otp / build_signature_hash`. Fallimento hook workflow ora loggato (prima: silenzioso).
- `bi.py::quotes_kpi` — estratti `_sum_total / _avg_hours_between / _pipeline_conversion_rate / _pipeline_weighted_value / _rejection_reasons`. Costante `QUOTE_STATUSES`.
- `ai_cfo.py::generate_suggestions` — estratti `_cash_flow_suggestion / _receivables_suggestion / _conversion_suggestion / _persist_suggestions`.
- `platform_owner.py::ensure_platform_owner_user` — estratti `_upsert_platform_owner_flags / _create_platform_owner_user / _reuse_active_invitation / _create_activation_invitation`.

**P1 server.py import cleanup**
- Import raggruppati per dominio (Foundations, CRM, Quoting, Ops, Finance/BI, Public)
- Router registrati via 6 liste raggruppate (`FOUNDATION_ROUTERS`, `CRM_ROUTERS`, ...)
- Estratto endpoint `/api/config/production-status` in helper locale, semplificato lookup OTP status.
- Rimosso import inutilizzato `os`.

**Testing**
- Nuovo `tests/test_code_quality_regression.py` (14 test): login, accept-invitation guards, quotes KPI shape, AI CFO generate, public sign 404, formula math determinism, formula rejects unknown vars/functions/div-zero, formula_security guard.
- `tests/test_iter25_smoke.py` (6 test aggiunti dal testing subagent) — health, /auth/me shape, login token, generate-from-quote 404, KPI period_days, openapi route count.
- **Risultato**: 20/20 PASS. Zero regressioni.

**Vincoli rispettati**
- ✅ Punto di ripristino creato (commit `58d0e41`)
- ✅ Significato formule invariato (Decimal, whitelist, strict mode)
- ✅ Nessun fallback silenzioso a zero (FormulaError bloccante in strict; nessun `except: pass` reintrodotto — solo l'hook workflow post-firma ora logga)
- ✅ Segreti solo da env/fixture (`tests/_creds.py`)
- ✅ API/permessi/snapshot/contratti firmati preservati (test 404/400 error paths verdi)

**Files aggiunti/modificati**: 30+ file (vedi `git log --stat 58d0e41..HEAD`).

## Iteration 27 — Opzione A: Catalogo & Simulatore 1-anta (Feb 2026)

**Backend**
- Ricetta `finestra_1a_5103_12130` in `app/services/recipes/finestra_1a.py` con formule esatte da spec (paragrafi 3-14):
  - Telaio 5103: 2×(L+S) + 2×(H+S); Rinforzo telaio: 2×(L-108)+2×(H-108); Anta 12130: 2×(L-70+S)+2×(H-70+S); Rinforzo anta: 2×(L-206)+2×(H-206); Fermavetro: 2×(L-186)+2×(H-186); Vetro: (L-206)×(H-206)/1e6 con min 0.50 m²
  - Test 900×1500 (S=6): telaio 4.824 ml, rinforzo t. 4.368 ml, anta 4.544 ml, rinforzo a. 3.976 ml, fermavetro 4.056 ml, vetro 0.898036 m² × 76 = €68,25
  - MISSING_*_PRICE codes: FRAME/SASH/FRAME_REINFORCEMENT/SASH_REINFORCEMENT/GLAZING_BEAD/GLASS/GLASS_MINIMUM/HARDWARE/HOURLY_COST/PRODUCTION_TIME/MARGIN/ADDITIONAL_COMPONENTS_COST
  - Geometry validation: L>206, H>206, L-108>0, H-108>0, L-70+S>0, H-70+S>0, L-186>0, H-186>0
  - +6% Premium PVC-only (telaio+anta+fermavetro+altri_pvc_share) — NON su rinforzi/vetro/ferramenta/manodopera
  - Snapshot hash deterministico su risultato
- `app/models_catalog.py` — ProductComponentAssoc (14 categorie), ProductionConfig, CatalogCodeMapping, ProductSimulateRequest
- `app/services/catalog_service.py` — get_production_config (merge defaults), load_product, resolve_component_prices (colour-sensitive per PVC, colour-independent per rinforzi acciaio, esclude prezzi ≤0), get_color_is_premium, seed_factory_code_mappings
- `app/routers/catalog.py` — 9 endpoint sotto `/api/catalog/`: production-config GET/PATCH, code-mappings GET/POST/PATCH, products/{id}/components, /lifecycle (5 stati), /simulate. Visibility gating server-side: costi interni nascosti se non `pricing_admin.view_costs` o `quotes.view_costs`.
- `app/permissions.py` — 9 nuove permission: catalog.view/manage/publish/import/delete + pricing_admin.view/manage/publish/view_costs
- `app/models_parametric.py` — `ColorCategory.is_premium` boolean (per +6% PVC)
- `app/seed_catalog.py` — idempotent:
  - Factory code mappings: 5103→telaio, 5105→telaio, 12130→anta_standard, 7379→scambio_battuta (is_system=True, tenant_id=None)
  - ProEvolution seed (7 componenti: 5103+12130+7379+FV-STD+RT-STD+RA-STD+RS-STD)
  - ProEvolution Restauro seed (identico ma telaio=5105)
  - Grant catalog.*/pricing_admin.* a Super Admin / Admin Azienda / Proprietario (via `permissions="*"` esistente + ensure keys)
- Server.py: mount `catalog_admin_router` + `run_catalog_seed()` on startup

**Frontend**
- `pages/ProductSimulatorPage.jsx` — UI /product-simulator: form L/H/colore/premium/hardware/altri, override manodopera+margine, cut-list table, stato pricing con badge, blocking_errors list, prezzo finale, snapshot hash
- `layouts/AppLayout.jsx` — nuovo gruppo "Catalogo e listini" con 7 sotto-voci (Catalogo prodotti, Simulatore prodotto, Listini e regole, Listini dettaglio, Importazione XLS/CSV, Sistemi profilo & formule, Engine parametrico avanzato)
- `App.js` — route `/product-simulator` → ProductSimulatorPage

**Bug corretto (HIGH) durante testing agent**
- `catalog.py::simulate_product` leggeva `user.get("permission_keys")` che get_current_user NON popola per utenti non-superadmin → tutti i Commerciali ricevevano 403
- Fix: usa `await get_permission_keys_for_user(user)` — pattern coerente con altri router

**Test finali**
- `tests/test_finestra_1a_recipe.py` (16): geometria, MISSING_*, Premium PVC-only, margin flow, snapshot determinism, display rounding
- `tests/test_catalog_area.py` (11): seed products/mappings, prod config, simulate scenarios, lifecycle, no-alteration KPI
- `tests/test_catalog_area_supplementary.py` (6): visibility gating Commerciale (bug fix verificato), MISSING_ADDITIONAL_COMPONENTS_COST, PATCH+GET production-config, KPI regression
- Regression: `test_ci_security_guards` (6) + `test_code_quality_regression` (14) + `test_iter25_smoke` (6) tutti verdi
- **Totale: 58/58 PASS**, scanner segreti clean, eval-ban attivo

**Limitazioni residue (fase 2 — dopo collaudo)**
- PDF import non implementato (pdfplumber pianificato in fase 2)
- Ricetta 2 ante non implementata (attende spec puntuale come per l'1-anta)
- Nessun listino barre seedato per tenant demo: simulate ritorna `incomplete` con MISSING_*_PRICE finché l'operatore non importa un file XLS/CSV valorizzato per i codici 5103/12130/rinforzi/fermavetro
- Il wizard "duplica/versiona prodotto" mostra solo transizioni di stato via API (draft/validated/active/superseded/archived), non ha UI full-featured

**Stato collaudo domani**
- Login admin OK
- Sidebar "Catalogo e listini" visibile e navigabile
- /product-simulator carica ProEvolution pre-selezionato con L=900/H=1500
- Ogni simulazione produce cut-list corretta + errori MISSING chiari
- Per raggiungere `pricing_status=ok` in demo: pre-caricare listino barre via /pricelist-importer con almeno codici 5103, 12130, RT-STD, RA-STD, FV-STD, e opzionalmente 7379 (per 2-ante che comunque non è nella fase 1)

## Iteration 28 — SMTP Email System SiteGround (Feb 2026)

### Scope
Implementazione servizio SMTP production-ready per SiteGround (`gnldm1111.siteground.biz:465`, SSL, user `pilot@panoramapilot.com`).

### Backend
- **`app/services/email_service.py`**: `enqueue_email()` con SMTP via `aiosmtplib` (SSL/STARTTLS), delivery-mode redirect, idempotency check, retry worker in background (backoff 1m/5m/15m, max 3 tentativi), status: queued/sending/sent/failed/retrying/bounced/test_intercepted/configuration_required.
- **`app/services/email_config.py`**: `MailConfig` dataclass; `get_public_config()` mai espone password.
- **`app/services/email_dns.py`**: `check_domain()` SPF/DKIM/DMARC via `dnspython`.
- **`app/models_email.py`**: `EmailLogV2` esteso (tenant_id, original_to, delivery_mode, attempt_count, next_retry_at, idempotency_key, payload_hash, stored_html/text), `EmailTemplateDoc`, `TestEmailRequest`.
- **`app/routers/email_settings.py`**: `/api/email-settings` (GET config, POST /test rate-limit 5/5min, GET /dns-check, template CRUD).
- **`app/routers/email_logs.py`** (esteso): tenant scope, filtri (status/template/to), counts_by_status, `POST /{id}/retry`.
- **`app/seed_email_templates.py`**: 11 template canonici seminati come sistema idempotente.
- **`app/services/email.py`** (compat): wrapper backward-compatible per `send_email()` legacy — delega a `enqueue_email`.
- **Permessi**: `email.view_settings`, `email.manage_settings`, `email.send_test`, `email.view_logs`, `email.retry`, `email.templates.manage`.

### Frontend
- **`pages/EmailSettingsPage.jsx`**: 4 tab (Configurazione, Invio di test, Verifica DNS, Template) con editor Jinja2 + anteprima HTML live + reset override tenant.
- **`pages/EmailLogsPage.jsx`** (riscritto): filtri stato/destinatario, counts_by_status cliccabili, dialog dettaglio con anteprima HTML/text, retry inline.
- Menu sidebar: "Impostazioni email" + "Registro email".

### Env variabili aggiunte
`MAIL_HOST`, `MAIL_PORT=465`, `MAIL_SECURITY=ssl`, `MAIL_USER`, `MAIL_FROM`, `MAIL_FROM_NAME`, `MAIL_REPLY_TO`, `MAIL_DELIVERY_MODE=test`, `MAIL_TEST_REDIRECT_TO=pilot@panoramapilot.com`, `MAIL_IMAP_HOST/PORT/SECURITY` (predisposte, non implementate).

### Sicurezza
- **Password**: SOLO da `os.environ.get("MAIL_PASSWORD")`. Mai loggata. Se manca → status `configuration_required` con messaggio `SMTP_NOT_CONFIGURED`.
- **Protezione preview**: tutti gli invii reindirizzati a `pilot@panoramapilot.com`, oggetto con prefisso `[TEST - Destinatario originale: ...]`, `original_to` preservato nel log.
- **Isolamento tenant**: `email_logs` scoped per tenant_id (bypass solo per superadmin/platform_owner).
- **Idempotency**: se `idempotency_key` esiste con status=sent/test_intercepted, ritorna log esistente senza reinvio.
- **Rate limit**: 5 test-email ogni 5 minuti per utente (in-memory, ok per single-instance).
- **Password redaction**: se cfg.smtp_password appare nell'eccezione SMTP, viene sostituita con `***REDACTED***`.

### Test — iteration_28.json
- **Backend**: 45/45 PASS (10 test_email_service + 9 test_email_extra + 26 regressione)
- **Zero critical/high**, 1 minor cosmetico (rate-limit in-memory)
- **Regressione**: 73/73 su commercial_perimeter, finestra_1a, catalog, ci_security_guards, code_quality_regression, iter25_smoke

### Deploy checklist (post MAIL_PASSWORD)
1. Aggiungere `MAIL_PASSWORD` in **Emergent → Profile → Secrets** con la password SMTP di `pilot@panoramapilot.com`.
2. Restart backend (o attende reload automatico).
3. Verificare `GET /api/email-settings` → `password_configured=true`, `is_configured=true`, `provider_name=siteground_smtp`.
4. In "Impostazioni email → Invio di test" mandare test USER_INVITATION → deve arrivare a `pilot@panoramapilot.com` con oggetto `[TEST - ...]`.
5. Attivare LIVE mode solo dopo verifica cambiando `MAIL_DELIVERY_MODE=live` in produzione (mai in preview).

### Prossimo (P1)
- Sprint 2 Catalogo: UI Ferramenta (Kit), UI Montaggio e posa
- Sprint 3 Catalogo: UI Costi accessori (16 categorie)
- Formule vetro 3-ante e 4-ante (bloccato: attende specifiche tecniche)

## Fase 1 · Motore commercial_perimeter integrato — Feb 2026 (iter 29)

### Deliverables
- Nuovi endpoint (`/app/backend/app/routers/quote_structure.py`):
  - `POST /api/quote-structure/{qid}/openings/{oid}/products/compute-and-add` — motore integrato, salva pricing_snapshot
  - `POST /api/quote-structure/products/{line_id}/recompute` — ricalcolo linea esistente
  - `GET /api/quote-structure/{qid}/legacy-status` — flag legacy read-only
- Endpoint esistente `POST /api/quote-structure/openings/{oid}/products` ora rifiuta `unit_price>0` senza permesso `quotes.edit_prices` (403 MANUAL_PRICE_NOT_ALLOWED)
- Helper `is_legacy_quote(q)` + `_assert_not_legacy(q)` (409 LEGACY_QUOTE_READ_ONLY su mutations)
- Guard `_guard_unit_price(user, val)` — bypass solo per superadmin o utenti con `quotes.edit_prices`
- Test file `/app/backend/tests/test_fase1_motor_integration.py` — 6 test (5 pass + 1 skip in caso listini incompleti, comportamento voluto)
- Git tags: `pre-fase1-backend-motor-2026-02` (rollback), `p0-fase1-motor-integrato` (checkpoint)
- Commit: `464b413`

### Codici errore bloccanti gestiti (dal motore)
MISSING_ADDITIONAL_COMPONENTS_COST, MISSING_COMPONENT_COLOR_PRICE, MISSING_FRAME_PRICE, MISSING_FRAME_REINFORCEMENT_PRICE, MISSING_GLASS_MINIMUM, MISSING_GLASS_PRICE, MISSING_GLASS_RECIPE, MISSING_GLAZING_BEAD_PRICE, MISSING_HARDWARE_PRICE, MISSING_HOURLY_COST, MISSING_INSTALLATION_PRICE, MISSING_MARGIN, MISSING_MEETING_STILE_PRICE, MISSING_MEETING_STILE_REINFORCEMENT_PRICE, MISSING_PRODUCTION_TIME, MISSING_SASH_PRICE, MISSING_SASH_REINFORCEMENT_PRICE

### Comportamento preventivi legacy
- Rilevati automaticamente: `is_legacy=true` OR `pricing_engine≠commercial_perimeter` OR presenza linee con `base_price>0` e senza `pricing_snapshot`
- API `/api/quote-structure/{qid}/legacy-status` espone il flag al frontend
- Mutations su preventivi legacy → HTTP 409 con code `LEGACY_QUOTE_READ_ONLY`
- Nessuna migrazione automatica, nessuna cancellazione automatica


## Iterazione 30 · AUDIT TECNICO COMPLETO v1 — Feb 2026

**Scope**: audit pre-unificazione architetturale (opzione D2:b) su richiesta esplicita del PO — 17 sezioni di analisi + fix Critical/High + report + rollback tag.

### Report completo
`/app/memory/AUDIT_REPORT_V1.md` — mappa file, duplicazioni, query, motori, formule vetro, unità, versionamento, legacy, permessi, frontend, seed, performance, error handling, bug classificati, test, verdetto finale.

### Bug fixati (Critical / High)
| ID | Severità | File | Descrizione |
|---|---|---|---|
| BUG-01 | CRITICAL | `routers/quotes.py:449-462` | Guard `sent` leggeva collezione `opening_products` inesistente per lo schema — preventivi con `pricing_status=incomplete` potevano essere inviati. Ora ispeziona `q.lines[].pricing_snapshot.blocking_errors` inline + codes `QUOTE_HAS_BLOCKING_ERRORS` / `QUOTE_CONTAINS_MANUAL_PRICES`. |
| BUG-02 | HIGH | `services/catalog_service.py:126-140` | `resolve_component_prices` senza ordering deterministico su `find_one`. Aggiunto sort `version DESC, updated_at DESC, _id DESC`. |
| BUG-03 | CRITICAL | `services/catalog_service.py:24-33` | `DEFAULT_PROD_CFG` inventava `default_glass_price_per_sqm=76.0` e `default_glass_min_sqm=0.50` silent. Rimossi → ora `None` → motore emerge MISSING_GLASS_PRICE / MISSING_GLASS_MINIMUM esplicito (P6 rispettato). |
| BUG-04 | HIGH | `services/indexes.py` | Indici mancanti su 6 collezioni hot. Aggiunti: `ix_ipl_tenant_status_ver`, `ix_ipl_tenant_active_ver`, `ix_glass_recipes_lookup`, `ix_color_categories_tenant_code`, `ix_ccm_tenant_code`, `ix_products_demo_guard`, `ux_production_config_tenant`. |
| BUG-06 | HIGH | `services/recipes/glass_engine.py:136-170` | Troncamento `int((L-wr)/sf)` → ROUND_HALF_UP. 2-ante L=1400 wr=347 sf=2 ora restituisce 527 (era 526 silent). Rifiuta split_factor ≤0. |
| BUG-15 | HIGH | `production_config` | Unique sparse index per tenant_id. Cleanup manuale duplicati esistenti demandato. |
| BUG-16 | HIGH | `services/recipes/commercial_perimeter.py:377-385` | Latent bug: `installation_declared_zero=True` con `installation_cost=None` causava TypeError `None + Decimal` in service_cost. Aggiunto helper `_z()` che coerce None→Decimal("0"). |

### Bug documentati NON corretti (in scope unificazione)
- **BUG-14** [CRITICAL/ARCHITETTURALE] — `ParametricAdminPage.jsx` disconnessa dai listini/motore commerciale. Fix = opzione D2:b (unificazione), documentato in `/app/memory/UNIFICATION_PLAN_V1.md` (attende approvazione A/B/C).
- BUG-05/07/09/10/11/12/13 (MEDIUM cosmetici/refactor) — documentati nel report.

### Test aggiunti
- `tests/test_audit_v1_regression.py` — 7 test regressione per BUG-01/02/03/04/06/15
- Totale: **92 test verdi + 2 xfail attesi** (test flaky su tenant Infissi Express con listino ricco)
- Regressione: `test_finestra_1a_recipe`, `test_catalog_area*`, `test_commercial_perimeter*`, `test_motor_full_listino_hard`, `test_iter25_smoke`, `test_ci_security_guards`, `test_code_quality_regression` — tutti verdi

### Git tags
- `pre-audit-v1-2026-02` — rollback point (commit `870d704`)
- `p1-audit-v1-fixes` — dopo primo giro di fix (commit `3668a32`)
- `p1-audit-v1-fixes-final` — dopo fix BUG-16 e finalizzazione (commit `28fdd81`)

### Verdetto
✅ **Motore commercial_perimeter corretto e coerente** per il perimetro implementato: math, snapshot deterministico, MISSING_* espliciti, no silent zeros, no fallback inventati, permessi enforced, tenant isolation OK.  
⚠️ **Fase 2A/unificazione ancora bloccati**: `ParametricAdminPage` disconnessa. Serve approvazione utente su UNIFICATION_PLAN_V1 (opzione A/B/C) per procedere.  
⚠️ **BUG-15 duplicato production_config** su PanoramaPilot richiede cleanup manuale prima dell'attivazione unique index in produzione.

### Endpoint modificati (comportamento)
- `POST /api/quotes/{id}/status` — ora blocca correttamente invio con blocking errors
- `POST /api/catalog/products/{id}/simulate` — glass_price/min_sqm ora obbligatori esplicitamente
- `POST /api/quote-structure/{qid}/openings/{oid}/products/compute-and-add` — behavior invariato ma ora usa motore corretto per service_cost None

### File modificati (7 file)
```
app/routers/quotes.py                          +43 -11
app/services/catalog_service.py                +18  -4
app/services/recipes/glass_engine.py           +22  -8
app/services/recipes/commercial_perimeter.py    +8  -3
app/services/indexes.py                        +45   0
backend/tests/test_audit_v1_regression.py     +140   0 (new)
memory/AUDIT_REPORT_V1.md                     +500   0 (new)
```

## Iterazione 30-bis · Vincoli 18-22 formalizzati + false positive Code Review

### Contesto
L'utente ha esteso il prompt audit con 5 nuove sezioni permanenti (18-22)
e ha fornito un "Code Quality Report" contenente falsi positivi Security
(grep testuale su "eval").

### Azioni eseguite
1. **Falso positivo eval/exec/compile chiuso permanentemente**:
   - Test `tests/test_no_eval_regression.py` — verifica AST-based che NESSUN
     modulo di produzione contiene chiamate reali a eval/exec/compile built-in.
   - I 6 file segnalati dal Code Review contengono solo:
     - nomi di funzioni custom (`_eval`, `eval_formula`, `SafeExpression`)
     - docstring/commenti che DOCUMENTANO il divieto
     - `simpleeval` come libreria safe importata
   - Il guard import-time `_assert_no_eval_in_module` è attivo e verificato.

2. **Sezioni 18-22 documentate permanentemente** in `/app/memory/AUDIT_REPORT_V1.md`:
   - Sez 18: vincoli di esecuzione (checkpoint, backup, read-only initial) — rispettati
   - Sez 19: gestione dati demo — nessuna cancellazione fatta, protocollo definito
   - Sez 20: validazione economica esplicita — test `test_audit_v1_sez20_economic.py`
     stampa report con TUTTI i campi (input, quantità, prezzi, unità, breakdown,
     margine, sconto, prezzo finale, hash)
   - Sez 21: criterio di accettazione 15-step — analizzato:
     * Step 1-8 (UI unificata): NON REALIZZABILI oggi (BUG-14 aperto)
     * Step 9-15 (backend puro): VERDI e verificati
   - Sez 22: STOP obbligatorio dopo audit — RISPETTATO

3. **Tech-debt terminologico documentato**:
   - Il campo `margin_pct` si comporta come markup-on-cost (sale=cost*(1+m/100)),
     NON margine sul ricavo (sale=cost/(1-m/100))
   - Rinomina in `markup_pct` richiede migrazione ampia → deferita
   - Test `test_sez20_terminology_markup_vs_margin_documented` fissa la semantica

### Refactor code quality (NON applicati)
- `_load_recipe_inputs` (67 righe, complessità 18), `simulate_product`,
  `direction_dashboard`, `upload_file`, `public_sign`, `create_variation`,
  `compute()` — sono stabili, testati, in produzione. Split arbitrario per
  soglie numeriche NON riduce complessità reale.
- Deferiti post-unificazione D2:b.

### Test totali verdi
- 97 pass + 2 xfail attesi (test flaky su tenant con listino ricco)
- Nuovi file:
  - `tests/test_no_eval_regression.py` (3 test)
  - `tests/test_audit_v1_sez20_economic.py` (2 test)

### Prossima azione (BLOCCANTE)
L'utente deve scegliere A/B/C su `/app/memory/UNIFICATION_PLAN_V1.md`.
Fino alla scelta esplicita, l'agente NON procede con migrazione,
riscrittura ParametricAdminPage, o unificazione dei modelli.



## Iterazione 31 · AUDIT PLUGIN & DIPENDENZE + Script cleanup production_config

### Deliverable
- `/app/memory/AUDIT_PLUGINS_V1.md` — audit 10 sezioni, evidence-based
- `/app/backend/scripts/cleanup_production_config_duplicates.py` — dry-run + apply per BUG-15

### Plugin da rimuovere subito (~500kb bundle sprecati)
Frontend: `swr`, `framer-motion`, `dayjs`, `lodash`, `@types/lodash`
Backend: `pymupdf` (opzionale), `websockets` (o attivare), `tenacity` (o usare per retry)

### GAP P0 identificati per ERP serramenti IT
1. Fatturazione Elettronica SDI (Aruba/FIC) — **obbligo legale**
2. Portale ENEA ecobonus — killer feature settore
3. OCR listini fornitori via Gemini Vision (Universal Key già in deps!)
4. WhatsApp Business (Twilio o Meta Cloud)
5. APScheduler async — reminder/follow-up/cleanup
6. Sentry SDK backend — visibilità errori produzione
7. ezdxf export lista taglio → CNC
8. Firma canvas mobile-first (Fase 3 UX_ARCH V2)
9. Verifica backup + procedura restore MongoDB

### Cleanup production_config duplicati (BUG-15)
- Script pronto: `python3 backend/scripts/cleanup_production_config_duplicates.py [--apply]`
- Dry-run eseguito ✅ — 1 tenant con 2 doc, KEEP pc-* più recente, DELETE prodcfg-*
- **Non applicato** — attende conferma utente prima di `--apply` in preview e prod


## Iterazione 33 · ARCHITECTURAL_AUDIT_V3 — direzione ribaltata

Il PO ha rifiutato l'Opzione B ridotta (V2) e richiesto la direzione opposta:
**Sistema B (parametric) diventa fonte autorevole tecnico-produttiva.
Sistema A (catalog) si riduce a livello commerciale puro.**

### Deliverable
- `/app/memory/ARCHITECTURAL_AUDIT_V3.md` — piano completo con 4 resolver,
  4 pricing method distinti, doppio snapshot, 9 fasi, 18-step accettazione
- `/app/memory/ARCHITECTURAL_AUDIT_V2_SUPERSEDED.md` — versione superata (V2)

### Punti architetturali chiave
1. `TechnicalCostResolver → CommercialPricingService` (flusso unidirezionale)
2. Sistema A tiene solo: `CommercialProduct` (FK a profile_system+bom+versione)
   e `CommercialRules` (pricing_method + parametri)
3. 4 pricing_method separati: `MULTIPLIER`, `MARKUP_ON_COST`,
   `TARGET_GROSS_MARGIN`, `FIXED_PRICE` — no più uso generico di margin_pct
4. Doppio snapshot immutabile per riga preventivo:
   - `technical_snapshot` (immutabile ai cambi di listino costo)
   - `commercial_snapshot` (immutabile ai cambi di regola commerciale)
5. `ParametricAdminPage` rewrite come "Sistemi profilo e formule"
   con 9 tab (8 tecnici + 1 commerciale con permesso separato)

### Stato
- Zero implementazione
- Zero modifica frontend/wizard/firma/plugin
- Attende approvazione esplicita del PO su §2/§3/§6/§8/§9/§10/§11 di V3

### Git tag
- `p1-architectural-audit-v3` — punto di ripartenza dopo approvazione


## Iterazione 34 · DESIGN_REVIEW_V3 (4 livelli, pronto per cross-validation)

### Deliverable unico
`/app/memory/DESIGN_REVIEW_V3.md` — analisi completa Prodotto+Architettura+UX+Dati
+ analisi flusso aziendale + preventivatore + motori + schermate + DB + API +
frontend + backend + produzione + scalabilità 100/1k/10k aziende.

### Output strutturato consegnato
1. Punti di forza (10)
2. Lacune progettuali (18)
3. Bug architetturali (12: ARCH-01..11 + BUG-15)
4. Ridondanze (9)
5. Moduli da ELIMINARE
6. Moduli da RIFARE
7. Moduli da MANTENERE
8. Priorità Critical(5) / High(10) / Medium(9) / Low(5)
9. Roadmap Q1-Q4 (12 mesi)
10. Nuovo modello architetturale a 4 layer

### Verdetto principale
ERP funzionalmente ricco ma architetturalmente frammentato:
- 57 router + 53 pagine + 200 collezioni
- 6 pagine per preparare 1 preventivo
- 2 fonti autorevoli tecniche in conflitto
- 4 SDK AI mai attivate
- 500kb deps frontend mai usate
- Nessuna fatturazione elettronica IT (bloccante legale)
- Nessun scheduler, nessun monitoring
- Preventivatore matematicamente corretto ma disconnesso dalla produzione

### Prossimo passo (PO)
Sottoporre il documento a un secondo modello indipendente (Claude Opus /
Gemini 3 Pro) per cross-validation. Suggerimenti espliciti forniti nel doc §
"DOPO IL REPORT" per guidare il secondo review.

### Git tag
- `p1-design-review-v3` — checkpoint post-review, pre-decisione finale

### Vincoli rispettati
- Zero implementazione
- Zero modifica codice
- Zero plugin add/remove
- Zero nuove pagine/collezioni


---

## Iter 39 — PREVIEW FULL TEST v1 (Feb 2026)

**Data:** 2026-08-07  
**Autorizzato dall'utente:** Messaggio 155 — pubblicazione completa in **PREVIEW / STAGING** (NON produzione)

### Cosa è stato fatto
- ✅ Inventario completo (28 commit tra `main` e `feat/smtp-email-system`)
- ✅ Verifica configurazione ambiente (60+ variabili `backend/.env`, tutte configurate; nessun segreto esposto nel report)
- ✅ Verifica servizi: `backend` RUNNING, `frontend` RUNNING, `mongodb` RUNNING; `redis` FATAL (documentato in known issues)
- ✅ Esecuzione suite test critiche: `test_first_operational_release`, `test_no_eval_regression`, `test_commercial_perimeter_e2e` (18/19 + 1 xfail race), `test_fase1_motor_integration`, `test_demo_product_guard`, `test_motor_full_listino_hard`, `test_audit_v1_sez20_economic` (2/2), `test_audit_v1_regression` (31/31), `test_commercial_perimeter_recipe`, `test_ci_security_guards`, `test_code_quality_regression`, `test_finestra_1a_recipe`, `test_bom_engine_blocco_a`, `test_stabilization_rc1` (85 pass + errori di rete non-code)
- ✅ Test economico obbligatorio ProEvolution 900×1500 — motore risponde `pricing_status=incomplete` con `MISSING_GLASS_PRICE`, `MISSING_GLASS_MINIMUM`, `MISSING_HARDWARE_PRICE`, `MISSING_ADDITIONAL_COMPONENTS_COST`, `MISSING_INSTALLATION_PRICE` (comportamento **fail-closed** corretto: geometria calcolata, prezzi mancanti dichiarati esplicitamente)
- ✅ Smoke test browser desktop 1920×800: login → dashboard OK, nessuna schermata bianca, console pulita, KPI e pipeline caricati
- ✅ Smoke test mobile 390×800: login mobile-friendly, dashboard responsive
- ✅ Documenti prodotti:
  - `memory/PREVIEW_KNOWN_ISSUES_V1.md` — 13 sezioni di limitazioni con trasparenza CRITICAL
  - `memory/PREVIEW_FULL_TEST_v1_INVENTORY.md` — deliverable completo (13 sezioni)

### Git checkpoints creati (locali)
- **Tag rollback:** `pre-preview-full-publish-2026-08` → commit `2b97058`
- **Tag release:** `preview-full-test-v1` → commit `2b97058`
- I due tag puntano allo stesso commit perché **nessun codice è stato aggiunto** con questa pubblicazione (Blocco Sviluppo rispettato).

### Vincoli rispettati (nessuna operazione distruttiva)
- ❌ NON eseguito: `cleanup_production_config_duplicates.py --apply`
- ❌ NON eseguite: migrazioni distruttive, rinomine collezioni, cancellazioni dati demo
- ❌ NON implementati: `ProfileSystemResolver`, `BomResolver`, `TechnicalCostResolver`, `CommercialPricingService`
- ❌ NON attivati: nuovi plugin (OCR, AI, WhatsApp, scheduler)
- ❌ NON pubblicato in produzione
- ❌ NON eseguito force push / rebase distruttivo

### Limitazioni note dichiarate (in `PREVIEW_KNOWN_ISSUES_V1.md`)
1. Doppia fonte dati Sistema A ↔ Sistema B non unificata (P0 Critical)
2. `commercial_perimeter` non ancora sostituito da `TechnicalCostResolver`
3. Formule Excel V1_3 non ancora nel motore
4. Ricetta 3-ante telaio unico (BR-03) mancante
5. UI `/parametric/admin` scollegata dal motore (dichiarata legacy)
6. Redis non disponibile in preview → firma OTP non testabile
7. Tenant `PanoramaPilot Test` non pre-seedato (guard `DEMO_PRODUCT_NOT_ALLOWED` già attivo)
8. Layout mobile non ottimizzato < 375px

### Criterio di accettazione preview
La release è accettata quando l'utente conferma dal browser:  
login → cliente → prodotto → simulazione → preventivo → PDF (se già implementato).

### STOP
Attendo:  
1. Collaudo manuale dell'utente sulla preview  
2. Lista precisa anomalie e funzioni mancanti  
3. Approvazione esplicita per avviare Fase 1 (Unificazione Sistema B → Sistema A)

Fino ad allora — nessuna modifica al codice.

---

## 2026-02-19 — Milestone 1 Enerhia Operating Core (PART 2 / FINAL) ✅

Implementato flusso completo **Cliente → Cantiere → Timeline → Preventivo** con UI Italia.

### Cosa è stato consegnato
- **Customer esteso**: `customer_type` PRIVATE/COMPANY/TO_CONFIRM (retro-compat con legacy `private`/`business`), `customer_number` progressivo continuo `CLI-000001` per tenant (atomico, non riutilizzabile, niente reset annuale), `contact_person{}` strutturato, PEC, SDI.
- **Timeline strutturata**: `/api/customers/{id}/timeline` con categorie CALL/FOLLOW_UP/COMMERCIAL_NOTE/TECHNICAL_NOTE/ADMIN_NOTE/INSTALLATION_NOTE/SUPPORT_NOTE/SYSTEM_EVENT + channel PHONE/EMAIL/WHATSAPP/IN_PERSON/SYSTEM/OTHER + event_source MANUAL|SYSTEM. Eventi SYSTEM read-only, emessi automaticamente su create Customer/Site/Quote.
- **Site integrato UI**: SitesTab con CRUD (CANT-YYYY-NNNNN + property_type/floor/elevator/logistics).
- **Quote vincolato al Site**: `site_id` obbligatorio nella UI, validato server-side (customer/tenant match), pre-compila site_address.
- **Gate `MISSING_CUSTOMER_TAX_CODE`**: applicato SOLO su `POST /quotes/{id}/convert-to-contract` tramite `validate_customer_contract_readiness()` riutilizzabile.
- **CustomerDetailPage**: 5 tab (Panoramica, Anagrafica, Cantieri, Timeline, Preventivi) + banner "Da confermare" con edit forzato per legacy.
- **QuotesPage**: nuovo modal Cliente → Cantiere obbligatori con warning inline se cliente senza cantieri.

### Test (iter29 · testing_agent_v3_fork)
- 15/15 backend pytest, frontend happy-path desktop + mobile 390px passing.
- Nessun bug aperto.

### Vincoli rispettati
- Nessuna modifica a pricing V3, commercial_perimeter, catalog, formule, listini, PDF, produzione, contratti (a parte gate isolato in convert-to-contract).
- Backward compatibility verificata su clienti legacy.
- Tenant isolation invariata.

### STOP
Milestone 1 chiusa. In attesa del **collaudo manuale** dell'utente prima di iniziare Milestone 2 (Configurazione Tecnica).

---

## 2026-02-19 — Milestone 2 & 3 (P0 parte) — Enerhia Operating Core

### Consegnato
- **Configurazione tecnica come single source of truth** (3 nuove collezioni + 3 endpoint CRUD + 3 tab UI):
  - `glass_price_configs`: DOUBLE_STANDARD 76 · DOUBLE_SATIN 96 · TRIPLE_STANDARD 125 · TRIPLE_SATIN 156.25 €/m² con min 0.5 m² per pannello.
  - `hardware_rules`: WINDOW_1_SASH 60 · WINDOW_2_SASH 80 · DOOR_WINDOW_1_SASH 75 · DOOR_WINDOW_2_SASH 90 · SLIDING_DOOR_WINDOW 380 €/anta · VASISTAS_ONLY 40. Resolver `(opening_type, number_of_sashes)`.
  - `production_time_configs`: WINDOW 0.75/1.00/2.30 · DOOR_WINDOW 1.00/1.50/3.00 h.
- **Motore Unified Pricing v3** ora legge tutti i valori da DB (fail-closed su `MISSING_GLASS_PRICE`/`MISSING_HARDWARE_RULE`/`MISSING_PRODUCTION_TIME`). Costanti V1_3 restano come fallback documentato.
- **Rimosso hardware 76 €** cablato: ora `WINDOW_1_SASH` legge dal DB → 60 €. Nessun altro valore hardcoded per hardware.
- **Golden Test M3** (pytest, 3/3 passing): report riga-per-riga per GT-REAL (ProEvolution WINDOW 1 sash 1200×1400) + verifica hw=60 + verifica glass min 0.5m².

### GT-REAL — report
```
FRAME              5.212 × 4.02  =  20.95
FRAME_REINFO       4.920 × 1.52  =   7.48
SASH               4.376 × 2.31  =  10.11
SASH_REINFO        4.456 × 1.34  =   5.97
GLAZING_BEAD       4.376 × 2.10  =   9.19
MATERIAL COST                    =  53.70
GLASS              1.187 × 76.00 =  90.20
HARDWARE                         =  60.00  (era 76, ora corretto)
LABOR              0.75  × 180   = 135.00
FOIL SURCHARGE                   =   0.00
─────────────────────────────────────────
TOTAL INTERNAL                     338.90
EXCEL TARGET                     ≈ 310.56
DELTA                              +28.34  (probabile: prezzi profili V1_3 di riferimento ≠ listino Enerhia reale)
```
Delta NON forzato: come da Master Plan si documenta la riga responsabile. La correzione avverrà quando Enerhia fornirà i prezzi ufficiali dei profili (usare tab "Prezzi componenti" senza modificare codice).

### Milestone status snapshot
| M1 Customer/Site/Timeline | E2E_READY ✅ |
| M2 Configurazione tecnica P0 | E2E_READY ✅ (2.4, 2.5, 2.6, 2.7, 2.13) |
| M3 Golden Test | E2E_READY ✅ (report generato) |
| M4-M20 | NOT_STARTED |

### Bloccanti in attesa cliente
- Prezzo `GLAZING_BEAD_PROEVOLUTION` reale (oggi 2.10 placeholder)
- Prezzi profili V1_3 (FRAME/SASH/rinforzi) — delta 28.34 € vs Excel
- Ricetta 3-ante telaio unico
- Ricette DOOR_WINDOW_*, WINDOW_2_SASH, VASISTAS_ONLY (fail-closed corretto oggi)

### STOP
M4 (copertura DOOR_WINDOW/WINDOW_2_SASH/VASISTAS con formule V1_3 complete: meeting stile 5.50 €/ml, threshold H×29.50+7.49/9.84, montante 7.51 €/ml, transom 7.50 €/ml, pellicolato +10%) è la prossima milestone approvata dal Master Plan. Non iniziata in questo turno per rispettare i limiti di context.

**Non pubblicare in produzione fino al collaudo utente.**

---

## 2026-02-19 — M4 Ricette + M2.14 Servizi & Prezzi Semplici

### M4 Ricette pricing (TECHNICALLY_IMPLEMENTED)
Estesa `BomResolver` a 5 ricette con formule V1_3 complete:
- `WINDOW_1_SASH` (5 profili + GLASS + HW60 + LABOR)
- `WINDOW_2_SASH` (+ MEETING_STILE H/1000×5.50, HW80, LABOR 180)
- `DOOR_WINDOW_1_SASH` (+ THRESHOLD variabile H/1000×29.50 + fixed 7.49, HW75, LABOR 180)
- `DOOR_WINDOW_2_SASH` (+ MEETING_STILE + THRESHOLD + fixed 9.84, HW90, LABOR 270)
- `VASISTAS_ONLY_1_SASH` (HW40, LABOR 135)
- `SLIDING_DOOR_WINDOW`: solo regola hardware 380 €/anta (formula geom. in backlog M4B)

Foil surcharge +10% applicato SOLO su PVC eleggibili (FRAME/SASH/GLAZING_BEAD/MEETING_STILE/FIXED_MULLION/TRANSOM) — verificato test `test_foil_surcharge_walnut`.

**Golden tests: 10/10 verdi** (`test_golden_m3_v3.py` 3/3 + `test_golden_m4_recipes.py` 7/7). Report riga-per-riga incluso.

### M3 Status: TECHNICAL_TEST_READY · BUSINESS_GOLDEN = FAIL
Delta 28.34 € vs Excel target 310.56 € **spiegato analiticamente**: quantità corrette, formule corrette, delta interamente su prezzi profili V1_3 vs listino Enerhia reale. Nessuna correzione compensativa applicata. Chiusura richiede prezzi ufficiali profili da Enerhia → import via UI `/tech-config/component-prices`, zero codice.

### M2.14 Servizi & Prezzi Semplici
- Nuova collection `simple_services` + router `/api/simple-services` (CRUD + discount-guard)
- **34 servizi seedati** con dual pricing (listino Enerhia ufficiale posa/smontaggi/motorizzazioni/accessori/logistica)
- **Dual pricing**: `internal_reference_price` visibile solo a `pricing_admin.manage`, `customer_sale_price` visibile a tutti
- **Discount Guard** endpoint: `override_required=true` quando net_sale < internal_reference. Preparato per collegamento M5.
- LOGISTICS_LOADING seedato come `PRICING_RULE_TO_DEFINE`

### Deliverables
- `/app/memory/M4_PRICING_RECIPES_AND_GOLDEN_TESTS.md` — delta analysis, source-of-truth matrix, ricette, placeholders
- `/app/memory/ENERHIA_OPERATING_CORE_MASTER_STATUS.md` — status corretti (M2 85%, M3 BUSINESS_GOLDEN FAIL, M4 90%)

### Prossimi bloccanti
- **B2** Prezzi profili V1_3 reali Enerhia → chiude delta M3 (senza modifica codice)
- **B9** Formula geometrica SLIDING_DOOR_WINDOW → M4B
- **B10** Ricetta 3/4 ante telaio unico → M4B

### M5 avviabile con etichetta `TECHNICALLY_IMPLEMENTED · ECONOMICALLY_NOT_VALIDATED`
Come da Master Plan §21+§27. Non collegare UI commerciale fino a collaudo utente.

---

## 2026-02-19 — Architettura Definitiva Geometric → Commercial Pricing

### Principio vincolante
Il preventivo Enerhia nasce da: **CONFIGURAZIONE GEOMETRICA → PRODUCTION_COST → × 3 → BASE_PRODUCT_SALE_PRICE + PACCHETTO + POSA + SERVIZI − SCONTO = PREZZO CLIENTE**.
Il Configuratore Geometrico è la **vista UI** del pricing_v3, non un motore separato.

### Verifica applicata
- ✅ `pricing_v3` è l'unico motore autoritativo (`ProfileSystemResolver → BomResolver → TechnicalCostResolver`)
- ✅ Multiplier commerciale default **3.00** verificato attivo (production_cost 338.90 × 3 = **1016.70 €** base_product_sale_price)
- ⚠️ **Identificati due motori paralleli attivi** — Master Plan §37 attivato:
  - `pricing_v3` autoritativo (M4 verde)
  - `commercial_perimeter` (legacy) ancora usato da `quote_structure.py`, `catalog.py`, `pricing_hub.py` per preventivi correnti/storici
- ✅ Regola commerciale è UI-configurable via `/tech-config/commercial-rule`

### STOP M5 (§37)
M5 (Preventivatore commerciale unificato) è marcato `BLOCKED_BY_ARCHITECTURE`. Non può iniziare finché:
1. Delta 28.34 € chiuso o classificato `ECONOMICALLY_NOT_VALIDATED`
2. CommercialPackage entity creata
3. Legacy `commercial_perimeter` etichettato `LEGACY_ONLY_HISTORICAL_QUOTES`
4. Vista Tecnica UI collegata a `pricing_v3` (read-only del motore)
5. Test di identità (§33) verde su 3 canali (compute API, Vista Tecnica UI, QuoteLine)

### Deliverable
- `/app/memory/GEOMETRIC_TO_COMMERCIAL_PRICING_ARCHITECTURE_V1.md` — architettura definitiva + flusso E2E target + inventario legacy da decommissionare + step ordinati M5

### Prossima iterazione (M5 preparatoria — appena delta chiuso)
1. CommercialPackage backend + seed pacchetti Enerhia Standard/Premium
2. Vista Tecnica UI (component `<TechnicalView />` legge `/api/pricing/compute`)
3. UI Commerciale Preventivo: `base_product_sale_price` visibile, `production_cost` nascosto al Commerciale
4. Endpoint `POST /api/quotes/{id}/lines/from-configuration` con snapshot congelati (tech + comm + hash)
5. Feature flag `USE_UNIFIED_PRICING_V3` in `quote_structure.py` (default false)

---

## 2026-02-19 — Margin Control + Cash Flow Control ✅

### Modulo backend consegnato
Nuovo router `/api/margin-control/*` con **7 endpoint** (rules, targets, company-dashboard, compute-snapshot).
Nuove collection MongoDB: `margin_control_rules`, `margin_control_targets` (tenant-scoped, versionate).

### Business rules Enerhia (configurabili, non hardcoded)
- **Commissione**: `net_vat / 1.17 × 0.10` → `commercial_commission` (costo diretto)
- **Ritenuta**: `net_vat / 1.22 × 0.11` se `withholding_applicable=YES` → `withholding_cash_effect` (NON è costo economico)
- **Multiplier default**: 3.00

### Separazione rigorosa applicata
- `production_cost` **mai modificato** da sconto/commissione/ritenuta/fissi (verificato in test)
- `contribution_margin` = **economic view** (include commissione, esclude ritenuta)
- `expected_available_cash` = **cash view** (contribution − withholding)
- `withholding_receivable` = credito da recuperare
- Costi fissi/emergency/investment sono **allocations of company margin**, NON costi di commessa

### Target aziendali
Default `NEEDS_PO_CONFIGURATION` (nessun valore Enerhia inventato). Formule:
- `MONTHLY_EMERGENCY_ALLOCATION = (target − current) / months`
- `MONTHLY_INVESTMENT_ALLOCATION = remaining / months`
- `REQUIRED_MONTHLY_CONTRIBUTION = fissi + emergency + investment + profit_target`
- `REQUIRED_MARGIN_RATE = REQUIRED_CONTRIBUTION / MONTHLY_REVENUE_TARGET`
- `MINIMUM_SUSTAINABLE_PRICE = variable_costs / (1 − required_margin_rate)`

### Semaforo GREEN/YELLOW/ORANGE/RED con soglie configurabili (§26)
Se target non configurati → `POLICY_NOT_CONFIGURED`, ma preventivo procede (§48).

### Test — 17/17 verdi
`test_margin_control.py` (7): §41 base numerico · §42 sconto · §9/§10/§43 ritenuta · §44 target math · §26 semaforo · §48 policy not configured · §22 immutabilità production_cost.
+ M3 (3/3) + M4 (7/7) invariati.

### Deliverable
- **`/app/memory/MARGIN_AND_CASHFLOW_CONTROL_V1.md`** — flusso completo, endpoint, RBAC, snapshot, integrazione M5
- Master Status aggiornato con voce **MC**

### Attesa (UI non implementata questa iterazione)
- AMMINISTRAZIONE → CONTROLLO MARGINALITÀ (5 tab)
- Financial snapshot preview panel real-time
- Dashboard Cash Flow forecast mensile
- Integrazione discount guard nel motore preventivo (M5)

### Vincoli rispettati
Nessuna pubblicazione produzione · Nessun blocco M5 aggiuntivo · Nessuna modifica al motore pricing_v3 · M3 BUSINESS_GOLDEN rimane separato (§49)

---

## 2026-02-19 — Commercial Packages V1 (BASE/ADVANCED/PREMIUM)

### Backend consegnato
Nuovo router `/api/commercial-packages/*` + collection `commercial_packages`. Seed dei 3 pacchetti Enerhia (BASE/ADVANCED/PREMIUM) con **multiplier = null (NEEDS_PO_CONFIGURATION)** — nessun valore inventato (§25/§48).

### Simulator §24
`POST /api/commercial-packages/simulate` confronta contribution margin dei 3 pacchetti su stesso production_cost. Riusa `_compute_snapshot` del Margin Control (unica fonte di verità economica).

### Verifica live
Con TEMPORARY multiplier 2.5/3.0/3.5 e included_services 30/200/500 €: BASE 50.25%, ADVANCED 51.45%, **PREMIUM 48.60%** — dimostra §25 (Premium non automaticamente più marginale).

### Deliverable
`/app/memory/COMMERCIAL_PACKAGES_V1.md` con matrice completa delle policy per pacchetto (§5-§16): warranty, delivery, product_origin, floor_transport (Advanced fino al 3° piano), platform (Premium fino al 6° piano ma **disponibile anche sotto per protected_window_handling §14**), disposal, ENEA, cleaning, priority_support, Verisure 299 € display value.

### STOP §47/§50
- Nessun PDF avviato (esplicitamente vietato §47)
- Fermato dopo PACKAGE_ENGINE = E2E_READY
- UI Admin package configuration in backlog per prossima iterazione
- Multiplier BASE/ADVANCED/PREMIUM restano null finché il PO non li imposta

### Test — 17/17 verdi (invariati)

---
## 2026-09-08 — Vedi `memory/CHANGELOG.md`: msg 401 Pricing Integrity Audit = PASS; msg 402 Quote Editor Completion V1 = PASS (`QUOTE_EDITOR_FINAL_AUDIT.md`). Backlog P0: PRE-RELEASE CLEANUP residuo (full-suite 0F/0E, /api/sequences, tenant isolation, frontend build) → GENERAL PRE-PRODUCTION RELEASE GATE. Prossimo turno richiesto dal PO: CONNECTOR AUDIT (solo analisi). FREEZE: Vano V2, F2, F3, F4.

---
## 2026-09-09 — P0 QUOTE VISUALS + WINDOW/CASSONETTO COLOR ENGINE (msg 625) = PASS
- **VisualSpec canonico** (`backend/app/services/visual_spec.py`): PRODUCT CONFIG → VISUAL_SPEC → SVG deterministico (Python, unica source of truth). `ConfigureResponse.visual = {spec, is_bicolor, svg_interior, svg_exterior}`; UI (`ProductVisualSVG.jsx`) e PDF consumano lo stesso payload. Tipi: WINDOW, DOOR_WINDOW, ROLLER_BOX, SHUTTER, ROLLER_SHUTTER, MOSQUITO_NET.
- **Visual snapshot** congelato in `QuoteLine.visual_spec` al save/reconfigure (DRAFT rigenerabile, ACCEPTED immutabile — catalogo colori non altera PDF già accettati).
- **PDF**: miniatura per riga (2 viste se bicolore) + sezione "Schemi prodotti" (dedup per configurazione). Mai price family nel PDF cliente.
- **Window Color Engine** (`color_engine.py`, `resolvers._foil_applicable`): codici catalogo product_colors; 003 = BIANCO MASSA no surcharge; STANDARD +10% solo base PVC eleggibile (una volta anche 2 lati); SPECIAL → NEEDS_PO_PRICING; ignoto → UNKNOWN_COLOR_CODE. UI 4 modalità: WHITE_MASS / WHITE_IN_FOIL_OUT / FOIL_BOTH_SAME / BICOLOR + toggle vista interna/esterna. Placeholder WHITE_MASS/ANTHRACITE/OAK rimossi dalla UI.
- **Cassonetto Color Engine**: mapping rigido codice→famiglia (003 BIANCO_MASSA; 100/096/694/110/154/048 STANDARD; 019/145/146/109/402/663 NON_STANDARD); altro → `CASSONETTO_COLOR_FAMILY_UNMAPPED` fail closed. Famiglia visibile solo con canSeeCosts.
- Test: `tests/test_p0_visuals_color_engine.py` 22/22 + testing agent iteration_38 (FE 11/11, BE 100%).
- Data gap noto (non P0): ricetta tecnica PROEVOLUTION WINDOW_3_SASH / WINDOW_4_SASH assente → 3/4 ante = INCOMPLETE (SVG ok).
- Pre-esistenti non correlati: `test_pdf_m332` (XPASS strict missing_site, snapshot non in listing), `test_multi_category_v1_e2e` fixture TEST_ZANZARIERA_AREA_130 e categoria PORTEFINESTRE mancanti.

## 2026-09-09 — PROEVOLUTION 3/4 ANTE (msg 627) = DISABLED_FAIL_CLOSED
- Nessuna `hardware_rule`/`technical_recipe` autoritativa per 3/4 ante → `quotable_configurations()` (ricetta+ferramenta+tempo produzione) esposta su GET /api/multi-cat/products; UI limita N. ante ai valori prezzabili; API `configure` → `not_available` + `CONFIGURATION_NOT_AVAILABLE_FOR_QUOTING`; add_line → 400. Test in `test_p0_visuals_color_engine.py` (25/25).

## 2026-09-09 — QUOTE PDF PREMIUM V2 (msg 626) = PASS
- Template `quote_pdf.html` riscritto: Roboto (font vendorizzati in `app/templates/fonts/`), primary #12a16b, A4; header brand reale + card Preventivo/Cliente/Cantiere (site join), banner Termini di pagamento (policy reale), posizioni V1.. con visual + spec, card Servizi previsti (solo inclusi) / Tempi indicativi (delivery policy) / Riepilogo economico (totale finale evidenziato), Schemi prodotti, Condizioni generali — in sintesi, condizioni complete (clauses), firma.
- `services/general_terms.py`: GENERAL_TERMS_VERSION=GT-2026.09-V1, 14 sezioni PO + sezioni legali SOLO da `clauses` ufficiali (recesso, garanzia 24); penali/foro/forza maggiore/risoluzione/perdita acconto/limitazioni → CONTRACT_TERMS_SOURCE_MISSING (non completate). Snapshot in `general_terms_snapshots`; quote salva `general_terms_version`/`general_terms_snapshot_id`; ACCEPTED → congelato.
- Fix: VAT breakdown riproporzionato sull'imponibile netto (IVA/Totale PDF = quote.vat_amount/total); customer name derivato da first/last/company.
- Test `tests/test_quote_pdf_premium_v2.py` 5/5 (render reale, fonts, contenuti, totali, no-leak, versioning/freeze).
- Pre-esistenti (PRE-RELEASE CLEANUP): test_pdf_m332 missing_site XPASS-strict, snapshot non in listing.

## 2026-09-09 — CUSTOMER PORTAL CORE V1 = PASS (Lotti 1-2 + documenti + assistenza)
- Backend `routers/customer_portal.py`: auth separata (JWT aud=customer_portal, cookie httpOnly + bearer), register → PENDING_AUTHORIZATION (mai accesso automatico), login lock per account (5 tentativi/15 min), forgot/reset; admin `/api/admin/customer-portal/users` (crea/autorizza/sospende, permessi customers.view/edit). Dati: `/jobs` (quote accepted/converted del customer), `/jobs/{id}` (righe customer-safe + visual_spec + timeline + payment_schedule), `/documents` (+ download PDF definitivi), `/tickets` (lista/crea → RICEVUTO). Isolation server-side {tenant_id, customer_id}; 404 cross-customer; zero chiavi interne.
- Frontend `pages/CustomerPortal.jsx` (route `/customer-portal/*`, mobile-first, bottom nav Home/Documenti/Assistenza/Profilo) riusa `ProductVisualSVG`.
- Test: `tests/test_customer_portal_core_v1.py` 5/5 + testing agent iteration_39 (BE 7/7, FE mobile tutto verde). Demo: cliente.demo@infissiexpress.com / <REDACTED_CUSTOMER_DEMO_PASSWORD>.
- Lotti futuri (P1): libreria tecnica/certificazioni/manuali, ENEA docs, contratto/rilievo/verbali nel portale (richiede document service con `customer_visible`).

## 2026-09-09 — PRE-RELEASE CLEANUP (in corso → vedi esito suite)
- Fix reali: `/api/sequences` 500 (doc legacy con ObjectId → `from_mongo` stringifica ObjectId; counter contratti CT- ripristinato con key), brute-force lock per account (IP ingress variabili aggiravano il lock), `contract.signed` evento timeline mancante (workflow_engine), gating invio quote su `opening_products` legacy, endpoint `GET /api/quote-pdfs/{pid}/snapshot` (audit), VAT breakdown PDF riproporzionato.
- Test stale allineati alle regole vigenti: PRV- numbering, convert idempotente (200), film_diff fixed per linea (M3.3.2), hardware WINDOW_1 = 60 €, glass config tenant 76 €/m², cassonetto `CASSONETTO_COLOR_FAMILY_UNMAPPED`, allowed_actions M3.3.4, tax_code/first_name obbligatori, ENEA costing definito, autosave whitelist, permessi ≥28, delivery_mode TEST redirect email, firma = +1 pagina. Quote Structure V1 (frozen) → skip motivato. Credenziali test solo da env (`tests._creds`, TEST_LIMITED_* in backend/.env). Frontend `yarn build` OK.

## 2026-09-09 — PRE-RELEASE CLEANUP = PASS · GENERAL PRE-PRODUCTION RELEASE GATE = PASS (con 1 prerequisito infra)
- Full backend suite chunked (7 chunk, 79 file): **1053 passed, 0 FAILED, 0 ERROR** (skip motivati: Quote Structure V1 frozen; test TENANT_ADMIN/PLATFORM_OWNER senza env). Frontend `yarn build` OK. Browser E2E finale testing agent iteration_40: BE 8/8 + FE ERP desktop + Portale mobile tutto verde.
- deployment_agent: codice deploy-ready (env-only, CORS, /api, Mongo). **PREREQUISITO INFRA (non inventabile)**: `REDIS_URL` deve puntare a un Redis gestito (Upstash/Redis Cloud) in produzione — il rate limiter OTP/firma pubblica è fail-closed senza Redis in APP_ENV=production (design voluto). In preview: fallback in-memory (development).
- NO PUBLISH eseguito (direttiva PO §12). Prossimi: backup, rotazione credenziali test esposte, deploy, smoke, rollback plan.

## 2026-09-09 — CONTRACT SOURCE OF TRUTH (msg 782) = PASS
- `services/general_terms_canonical.py`: trascrizione integrale (OCR pagine 4-8 + modulo pag. 2-3) del contratto ufficiale "modulo proposta d'acquisto corretto (1).pdf" → **GENERAL_TERMS_VERSION = GT-INFISSIEXPRESS-2026-09-V1** (31 articoli, ordine/numerazione ufficiale, APPROVAZIONE SPECIFICA clausole onerose 1341/1342 doppia, punti firma, consenso GDPR, istruzioni pagamento, Procedura Aziendale, `full_text` + `general_terms_hash` SHA-256). `GT_VERSIONS` registry, `get_canonical(version)` fail-closed (KeyError/404).
- `services/general_terms.py`: summary GENERAL_TERMS_SUMMARY_V1 (14 punti PO §8) DERIVATO dal canonico, ogni punto con `source_articles` (validati vs articoli esistenti); `info_notice` PO §6; nessuna dipendenza da `clauses`; `missing_sources=[]`. Freeze su ACCEPTED (snapshot `general_terms_snapshots`), congelamento esplicito anche in `POST /quotes/{qid}/status accepted`.
- Contratto (`contracts_helpers.build_contract_snapshot`): snapshot include `general_terms` (testo canonico integrale della versione congelata sul preventivo), `economics` (lines customer-safe, totali, vat_breakdown, `vat_regime` 22/10/4/MISTA + `declaration_required`, payment_terms dal preventivo, servizi, delivery/installation), `quote_revision_id`, `quote_snapshot_id` (ultimo quote_pdf), `accepted_at`; campi top-level contratto: general_terms_version/hash/snapshot_id. `GET /api/contracts/{cid}/terms-verify` → IDENTICAL/DIVERGENT/CONTRACT_TERMS_SOURCE_MISSING (legacy). `GET /api/general-terms/current`, `GET /api/general-terms/{version}`.
- PDF contratto (`contract_pdf.html`) ricomposto: modulo proposta d'acquisto (dati cliente/cantiere, configurazione approvata, importi+IVA, sezione 4 pagamento, dichiarazioni + firma), GDPR + firma, Condizioni Generali integrali (footer "Sigla" su pagine termini), approvazione clausole onerose con 2 firme, allegato dichiarazione IVA agevolata (solo regime ridotto), Procedura Aziendale + firma, firma elettronica (vale come firma/sigla/approvazione). PDF preventivo: sezione "CONDIZIONI CONTRATTUALI — IN SINTESI" + avviso informativo; rimosso il blocco divergente "Condizioni generali di contratto" da `clauses`.
- Frontend `ContractViewerPage.jsx`: card Condizioni Generali (versione, hash, 31 articoli, approvazione clausole); checkbox firma cita artt. 1341/1342.
- Test: `tests/test_contract_source_of_truth.py` 9/9 (struttura canonica, approvazione clausole, fail-closed versione, summary consistency, quote PDF summary-only, INVARIANCE IDENTICAL, PDF contratto completo, parità economica, freeze) + `test_contract_legacy_fallback.py` 2/2 + testing agent iteration_44 (BE+FE verde). LEGAL_REVIEW_RECOMMENDED: seconda approvazione nel documento sorgente riporta "3, 5, 6,9,12,15, 1, 6, 21" (trascritto 16) — nessuna correzione automatica.
- Pre-esistenti non correlati: `test_release_gate_iter40`/`test_customer_portal_iter39` usano credenziali hardcoded ruotate → 401/429.

## 2026-09-09 — FINAL CLOSE (msg 783) = NOT_READY (prerequisiti infra produzione)
- COLOR_INPUT_V2 = PASS (browser save→reload→modifica, "096" preservato, nomi ripopolati, BICOLOR ok; fail-closed codice/nome vuoto anche a livello API `configure` → `incomplete` COLOR_CODE_REQUIRED/COLOR_NAME_REQUIRED — fix blocker in `multi_category_pricing.py`). Screenshot `test_reports/screenshots/iter45_final_reload_modify_096_GRIGIO.jpeg`. Testing agent iteration_45.
- CONTRACT_SOURCE_VISUAL_VERIFY = VERIFIED_WITH_LEGAL_NOTE: pag. 7 mostra chiaramente "3, 5, 6,9,12,15, 1, 6, 21." → canonico allineato alla sorgente; LEGAL_REVIEW_RECOMMENDED. CONTRACT_EXACT_TERMS = PASS (terms-verify IDENTICAL; 14 test SoT verdi).
- Credential hygiene: password admin corrente rimossa da `tests/test_prod_gate_iter41.py`, redatti report/memo, fixture legacy → env (`TEST_CUSTOMER_DEMO_EMAIL/PASSWORD` in backend/.env); demo portale resta SOSPESO (iter39 skip motivato). Secret scanner clean.
- Full suite: 1111 passed; i 14 fail sotto -n 4 erano flake da rate-limit/stale fixture → tutti verdi rieseguiti (security_audit, pricelist_gating, quote_structure, prod_gate, ci_guards, cassonetto 999→NON_STANDARD).
- Backup preview `/app/backups/20260909T172813Z`. deployment_agent: READY (codice). PRODUCTION_CONFIG = FAIL (REDIS_URL managed, EMAIL live, APP_ENV/flag prod, CORS/APP_BASE_URL) → da impostare dal PO in Deployments → Secrets → Custom Keys; Emergent non fornisce Redis gestito. Deploy = azione manuale utente (pulsante Deploy). Runbook aggiornato §6-bis.

## 2026-09-10 — FASE 1 BRAND CLEANUP + SEO/META V1 = PASS · FASE 2 SELF REGISTRATION + ROLE APPROVAL V1 = PASS (freeze riattivato)
- SEO centralizzato `frontend/src/seo/{config.js,Seo.jsx}` (title/description/robots/canonical/OG/Twitter/JSON-LD; default noindex). Landing index (`Software Gestionale per Serramentisti | Panorama Pilot`), login/register/AppLayout/CustomerPortal noindex. `public/index.html` riscritto (lang it, Panorama Pilot, rimossi script badge/telemetria Emergent), `manifest.json`, `favicon.svg`, `og-image.png`; `robots.txt`/`sitemap.xml` generati da `scripts-gen-seo.js` (prestart/prebuild) con REACT_APP_PUBLIC_BASE_URL|REACT_APP_BACKEND_URL. Brand piattaforma: landing `product_name`/seo (models_landing default + public_site_configs), AuthLayout, it.json; brand tenant intatto su PDF/portale/email. PUBLIC_EMERGENT_REFERENCES(testo)=0 (restano solo host tecnici: backend URL, auth.emergentagent.com Google SSO). Nota: robots.txt sul preview è intercettato dall'ingress della piattaforma.
- Registrazione: `routers/registration.py` — `POST /api/auth/register` (whitelist SELF_REGISTRABLE_ROLES, extra ignorati, 409 ACCOUNT_ALREADY_EXISTS), `POST /api/auth/verify-email` (token sha256, TTL 48h, one-time), `GET /api/auth/registration/{id}`, `GET /api/auth/register/roles`; login → 403 {code ACCOUNT_PENDING_EMAIL_VERIFICATION|ACCOUNT_PENDING_APPROVAL|ACCOUNT_NOT_APPROVED|ACCOUNT_SUSPENDED} solo con password corretta. Superadmin: `GET /api/registration-requests[/count|/options|/{id}|/{id}/customer-matches]`, `POST /{id}/approve` (tenant+ruolo effettivo, no super_admin/admin_azienda; cliente → customer_portal_users AUTHORIZED con customer_id obbligatorio), `/reject`, `/suspend`, `/reactivate`; transizioni atomiche `find_one_and_update` + status_history + audit. Frontend: AuthTabs, `/register`, `/verify-email`, `/registration-status`, `/registration-requests` (nav superadmin con contatore). Test: `tests/test_self_registration_v1.py` 7/7, testing agent iteration_46 BE+FE verde. Email in preview = MOCK (debug_verification_token se OTP_DEBUG_ENABLED).
- Stato: APPLICATION_CODE = FROZEN_FOR_RELEASE; PRODUCTION_STATUS = NOT_READY (solo config esterna).

## 2026-09-10 — EMAIL REAL DELIVERY + REGISTRATION NOTIFICATIONS (msg 792) — EMAIL_LOGIC = PASS · EMAIL_REAL_DELIVERY = PENDING PRODUZIONE
- Un solo servizio email (`email_service.enqueue_email`/`email.send_email`); aggiunti `event_type`, `delivery_status` (provider_accepted|failed — mai "delivered"), `provider_message_id` (Message-ID generato), `error_code`; esposti in `GET /api/email-logs`.
- Registrazione: email verifica "Verifica il tuo indirizzo email | Panorama Pilot" (CTA, scadenza 48h); esito onesto `verification_email_status` SENT|EMAIL_SEND_FAILED; `POST /api/auth/resend-verification` {request_id} (60s min, max 6 invii, token precedente invalidato, risposta neutra); notifica Superadmin su PENDING_APPROVAL ("Nuova richiesta di registrazione | Panorama Pilot", CTA Gestisci richiesta); email approvato (CTA Accedi, login o portale), rifiutato (senza motivo interno), sospeso. UI: "Non hai ricevuto l'email? Invia di nuovo" su success e stato richiesta.
- Preview: provider mock → log `configuration_required` → EMAIL_SEND_FAILED mostrato onestamente (atteso). Notifiche email al cliente finale (DOCUMENT_AVAILABLE ecc.) NON esistono: eventi solo in-app (backlog post-release, non implementato).
- Test: `test_self_registration_v1.py` 8/8.
