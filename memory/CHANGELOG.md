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
