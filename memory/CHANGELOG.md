# CHANGELOG (dal 2026-09-08 — PRD.md > 700 righe, nuove voci qui)

## 2026-09-08 — msg 401 P0 PRICING INTEGRITY AUDIT → PASS (Cassonetti PASS · Persiane PASS)
- Cassonetti: importer autoritativo workbook (`app/scripts/import_cassonetti_grid.py`), JSON rigenerato, 4464+4464 celle validate (`tests/test_cassonetto_grid_full_matrix.py`), UI L/H a select, fail-closed espliciti. Report `CASSONETTO_GRID_VALIDATION.md`.
- Persiane: nuovo `pricing_model=AREA_PURCHASE_MULTIPLIER` + prodotto `PERSIANA_STD` (285/299/350 ×2.5, +99 orientabile, min 1,30 m²/pz), UI card, RBAC redaction, `tests/test_persiane_pricing_golden.py`. Report `PERSIANE_PRICING_VALIDATION.md`.
- Audit prodotti attivi: `app/scripts/pricing_model_audit.py` → `PRICING_MODEL_AUDIT_TABLE.md` (13/13 PASS). `PROEVOLUTION_RESTAURO` disabilitato (NEEDS_PO_RECIPE).
- Fix 500 configure FORMULA_TECHNICAL (errori dict→str); RBAC leak `GET /multi-cat/products/{pid}` chiuso.
- Vetri TRIPLE_SATIN 156,00; ENEA costi interni 50/120 IVA incl. → 40,98/98,36 netti, CONFIGURED.
- STEP 0 withholding golden permanente `tests/test_withholding_golden_step0.py`.
- Testing agent iteration_33: 14/14 API + 8/8 golden browser.
- Stato: PRE_RELEASE_CLEANUP ancora FAIL (in corso) — restano: full-suite chunked, `/api/sequences`, tenant isolation, frontend build/lint. NON pubblicare.

## 2026-09-08 — msg 402 QUOTE EDITOR COMPLETION V1 → QUOTE_EDITOR_FINAL_AUDIT = PASS
- Lotto 1: `PUT /quotes/{qid}/lines/{lid}/reconfigure` + UI "Modifica" (stesso configuratore prefilled, recompute autoritativo, history `previous_snapshots`).
- Lotto 2: cantiere obbligatorio (SITE_*_REQUIRED, SITE_INCOMPLETE) + form inline nuovo cantiere nel dialog preventivo.
- Lotto 4: smontaggio REMOVE_* customer_sale 30 €/unità (internal listino mantenuto).
- Lotto 5: payment terms strutturati (5 policy, FULL_UPFRONT sconto 5% su totali/margine) `app/services/payment_terms.py`.
- Lotto 6: vetri 4 tipi in UI (TRIPLE_SATIN ripristinato 156,25), PROFILATURA 8 €/ml automatica (costo interno NEEDS_PO_COSTING).
- Lotto 8: foil surcharge configurabile (10%, NEEDS_PO_FINAL_CONFIRMATION). Lotto 9: delivery policy STANDARD >90gg / EXPRESS +20% `app/services/delivery_policy.py`. Lotto 10: PDF (consegna, pagamento, sconti, maggiorazione).
- Test: tests/test_quote_editor_v1_lotto1_reconfigure.py, tests/test_quote_editor_v1_lotti_2_5_6_9.py; testing agent iteration_34. Report: memory/QUOTE_EDITOR_FINAL_AUDIT.md.
- Prossimo: GENERAL PRE-PRODUCTION RELEASE GATE (dopo chiusura PRE-RELEASE CLEANUP residuo: full-suite, /api/sequences, tenant isolation). Connector Audit rimandato (solo analisi).

## 2026-09-08 — msg 403 CONNECTOR AUDIT = COMPLETE + governance V1
- `memory/CONNECTOR_AUDIT_REPORT.md` (analisi, nessun codice): MUST-HAVE = SDI via intermediario, email inbound, riconciliazione bancaria, export contabilità, monitoring/backup.
- Governance: foil 10% ACTIVE; EXPRESS delivery fail-closed (EXPRESS_DELIVERY_NOT_READY_FOR_CUSTOMER_USE, UI disabilitata); ENEA internal cost riportato a NEEDS_PO_COSTING (snapshot INCOMPLETE); profilatura costo NEEDS_PO_COSTING. Verificato testing agent iteration_35.
- Preventivatore in FUNCTIONAL FREEZE. Prossimo: PRE-RELEASE CLEANUP residuo → Release Gate.
