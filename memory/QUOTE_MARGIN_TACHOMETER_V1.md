# QUOTE MARGIN TACHOMETER V1 — Deliverable (msg 392)

**Stato:** BACKEND_READY + UI_READY + MANUAL_E2E_PENDING (§28).
**Author:** Enerhia Operating Core — Iter 48 (Feb 2026).
**Prerequisiti:** P0 HOTFIX Live Price Tapparelle/Zanzariere (msg 391) CHIUSO.

---

## 1. Formule (§1 msg 392)

```
PRE_COMMISSION_CONTRIBUTION =
    NET_REVENUE_EX_VAT  -  SUPPLY_COST  -  INSTALLATION_COST  -  OTHER_DIRECT_COSTS

PRE_COMMISSION_MARGIN (%) =
    PRE_COMMISSION_CONTRIBUTION / NET_REVENUE_EX_VAT * 100

COMMISSION_BASE  = NET_REVENUE_EX_VAT              (§4 — risposta 1=B)
COMMISSION_GROSS = COMMISSION_BASE * COMMISSION_RATE   (solo se band != CRITICO)

FINAL_COMPANY_CONTRIBUTION =
    PRE_COMMISSION_CONTRIBUTION - COMMISSION_GROSS
FINAL_COMPANY_MARGIN (%) =
    FINAL_COMPANY_CONTRIBUTION / NET_REVENUE_EX_VAT * 100
```

**NESSUNA FORMULA CIRCOLARE**: la fascia è determinata dal margine *pre-commissione*, mai da quello post.

---

## 2. Cost Aggregation (§6 msg 392 — motore CONSUMER)

Il Margin Engine **NON ricalcola** i prezzi dei prodotti. Consuma gli snapshot già congelati in `QuoteLine`. Precedenza (`app/services/margin_engine.py::_extract_line_cost`):

1. `technical_snapshot.total_internal_cost * quantity` — FORMULA_TECHNICAL (Finestre/ProEvolution)
2. `simple_snapshot.purchase_total_cost` — se presente, autoritativo (già qty-multiplied)
3. `simple_snapshot.purchase_cost_per_item * quantity` — Tapparelle / Zanzariere
4. `simple_snapshot.internal_production_cost_per_item * quantity` — Cassonetti (GRID)
5. `line.internal_cost * quantity` — fallback legacy / servizi manuali

**Bucketing per categoria** (`_line_bucket`):

- `installation, posa, montaggio, montaggi_posa` → **INSTALLATION_COST** (§7)
- `disposal, smaltimento, accessory, accessori, extra, servizi` → **OTHER_DIRECT_COSTS** (§5)
- Tutto il resto (window/roller/screen/box/persian/…) → **SUPPLY_COST**

---

## 3. Fasce commissione (§2/§13 msg 392)

| Margin pre-commissione | Band          | Commission rate | Status                   |
| ---------------------- | ------------- | --------------- | ------------------------ |
| ≥ 30 %                 | OTTIMO        | 15 %            | OK                       |
| ≥ 20 % e < 30 %        | BUONO         | 10 %            | OK                       |
| ≥ 15 % e < 20 %        | SUFFICIENTE   | 8 %             | OK                       |
| ≥ 8 % e < 15 %         | SCARSO        | 5 %             | OK                       |
| < 8 %                  | CRITICO       | **None**        | AUTHORIZATION_REQUIRED   |

**§15 vincolante:** sotto 8% la commissione NON è definita. `commission_rate = None`, `commission_gross = None`. NON si applica `0 %` come regola automatica.

### Boundary test (§3) — implementati in `tests/test_margin_engine.py::TestResolveBand::test_boundary`

| Input   | Band          | Rate |
| ------- | ------------- | ---- |
| 30.00 % | OTTIMO        | 15 % |
| 29.99 % | BUONO         | 10 % |
| 20.00 % | BUONO         | 10 % |
| 19.99 % | SUFFICIENTE   | 8 %  |
| 15.00 % | SUFFICIENTE   | 8 %  |
| 14.99 % | SCARSO        | 5 %  |
| 8.00 %  | SCARSO        | 5 %  |
| 7.99 %  | CRITICO       | None |

---

## 4. Financial Snapshot (§16 msg 392)

Salvato a livello **Quote** in `financial_snapshot` (17 campi):

```
gross_contract_value           – Totale IVA inclusa
net_revenue_ex_vat             – Imponibile (base commissione)
supply_cost                    – SUPPLY aggregato
installation_cost              – INSTALLATION aggregato
other_direct_costs             – OTHER_DIRECT aggregato
pre_commission_contribution    – NET − SUPPLY − INSTALL − OTHER
pre_commission_margin          – % (4 dp)
margin_band                    – OTTIMO/BUONO/SUFFICIENTE/SCARSO/CRITICO/UNKNOWN
commission_base_policy         – "NET_REVENUE_EX_VAT"
commission_base                – = NET_REVENUE_EX_VAT
commission_rate                – 0.15/0.10/0.08/0.05 o None (CRITICO)
commission_gross               – € o None
commission_status              – OK / AUTHORIZATION_REQUIRED / NO_DATA
final_company_contribution     – € o None
final_company_margin           – % o None
margin_policy_version          – "margin_policy_v1_2026_02"
commission_policy_version      – "commission_policy_v1_2026_02"
```

### DRAFT vs ACCEPTED (§17-§18)

- **DRAFT / to_complete / …**: `financial_snapshot` è ricalcolato ad ogni mutazione (add/update/delete line, delete opening, patch quote). Endpoint `GET /api/quotes/{qid}/financial-snapshot` ricalcola in read-time per garantire freschezza.
- **ACCEPTED / CONVERTED**: `_is_frozen` blocca ogni ricalcolo. Alla transizione `accepted` viene aggiunto `{frozen_at, frozen_by}` nello snapshot; il valore congelato è la fotografia definitiva per il contratto.

---

## 5. RBAC (§11 / §20 msg 392)

Redaction **backend-side** (`redact_financial_snapshot_for_role`).

**Admin** (`quotes.view_costs` o `quotes.view_margins` o `*`): vede l'intero snapshot.

**Commerciale** (nessun permesso costi): riceve SOLO
```
net_revenue_ex_vat, pre_commission_margin, margin_band,
commission_rate, commission_gross, commission_status,
commission_policy_version
```
Tutti gli altri campi (`supply_cost`, `installation_cost`, `other_direct_costs`, `pre_commission_contribution`, `commission_base`, `final_company_contribution`, `final_company_margin`, `margin_policy_version`) sono **omessi dal payload API** — non basta nasconderli in UI.

Applicato sia in `_strip_costs_if_needed` (route `GET /api/quotes/{qid}`) sia in `GET /api/quotes/{qid}/financial-snapshot`.

---

## 6. UI

### Commerciale (§10) — sempre visibile
- Tachimetro SVG con lancetta + numeric readout (2 dp).
- FASCIA (OTTIMO/BUONO/…).
- Ricavo netto.
- Commissione %.
- Commissione lorda stimata €.
- Se CRITICO: banner rosso "PREVENTIVO DA AUTORIZZARE".

### Admin (§12) — sezione "Riservato Direzione"
Breakdown completo: valore contratto IVA incl., costo fornitura, costo posa, altri costi diretti, margine pre-commissione, commissione, restante azienda, margine post-commissione.

### Live recalc (§14)
`useQuery(["quote-financial", id, q.version])` — invalidato automaticamente quando cambia `q.version`, che il backend `$inc` ad ogni mutazione (add/update/delete line, delete opening, patch quote).

### Tachimetro (§13)
Scala visiva 0 → 40 %. Zone colorate leggibili (rosso/arancio/ambra/verde/blu). Tick label a 0/8/15/20/30/40+. Numeric readout a 2 dp sempre visibile (per valori > 40 % la lancetta cap a 40 % ma il numero mostra il vero valore).

---

## 7. PDF / Contract Guard (§19 msg 392) — DIVIETO ASSOLUTO

`app/services/pdf_renderer.py::build_snapshot` strippa dai payload dei documenti cliente:

**Top-level**: `financial_snapshot`, `internal_cost`, `margin_abs`, `margin_pct`, `cost_price`.

**Per line**: `internal_cost`, `margin`, `margin_abs`, `margin_pct`, `cost_price`, `technical_snapshot` (contiene `total_internal_cost`, `components`, `glass_cost`, `hardware_cost`, `labor_cost`), `pricing_snapshot` (contiene indirettamente il technical_snapshot), `financial_snapshot`.

Helper riutilizzabile: `margin_engine.strip_margin_from_pdf_payload()` per futuri renderer (contract PDF v2).

---

## 8. Formattazione moneta (§21 msg 392)

`fmtEUR` (frontend) ora usa
```js
Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR",
                             minimumFractionDigits: 2, maximumFractionDigits: 2 })
```
Applicato a: prezzo unitario, subtotale riga, imponibile, IVA, totale, commissione, breakdown direzione.

**Rounding (§22)**: calcoli backend a piena precisione, arrotondamento a 2 dp solo in output. Percentuali a 4 dp internamente per stabilità delle fasce, display a 2 dp.

---

## 9. Golden Tests (§23-§24) — implementati in `tests/test_margin_engine.py::TestGoldenScenarios`

**Golden #1 (§23)**: NET=10.000 SUPPLY=6.000 INSTALL=1.000 OTHER=0
→ margin 30 % · OTTIMO · commission 15 % = 1.500 € · final company 1.500 € · final margin 15 %.
Verificato E2E via curl: quote id `3b4fd98a-fc62-457d-9d66-494742e5fc90` sul preview tenant.

**Golden #2 (§24)**: NET=10.000 SUPPLY=7.000 INSTALL=500 OTHER=0
→ margin 25 % · BUONO · commission 10 % = 1.000 € · final company 1.500 € · final margin 15 %.

---

## 10. No duplicazione pricing (§25 msg 392)

Il Margin Engine **NON conosce** le formule di:
- ProEvolution / FORMULA_TECHNICAL (delegato a `pricing_v3`)
- Tapparella / AREA-by-color (delegato a `SimplePricingEngine.compute_area_by_color`)
- Zanzariera / idem
- Cassonetto / GRID (delegato a `SimplePricingEngine.compute_grid`)
- Persiana futura / direct purchase cost

Vincolo architetturale: `margin_engine.py` importa **solo** stdlib + tipi. Non tocca engines, non tocca DB. Alimentato tramite `compute_financial_snapshot(quote_dict)` letto dal router.

---

## 11. Known Limitations V1

- **INSTALLATION_COST §7**: attualmente usa `line.internal_cost * qty` per righe di categoria `installation`. Non ancora integrato con `internal_reference_price` / `customer_sale_price` a livello Anagrafica Servizi (previsto in un iter successivo).
- **Overhead gestionale (§9 msg 392)**: REVOCATO. Non implementato. Nessun `65.000/220`, `295 €/serramento`, quote struttura o site margin.
- **VANO MODEL V2 (§26 msg 392)**: NON iniziato. Prossima autorizzazione PO necessaria.
- **Freezing on non-accepted flows**: solo `accepted` e `converted` congelano lo snapshot. Le transizioni `sent/viewed/negotiating` continuano a ricalcolare per allineamento con eventuali revisioni durante trattativa.

---

## 12. Test Coverage

- `backend/tests/test_margin_engine.py` — **38 pytest** (boundary 8 + resolve_band 4 + aggregate 7 + golden 5 + RBAC 4 + PDF guard 2 + policy 1).
- E2E curl verificato: golden #1 su preview tenant, sia ADMIN sia COMMERCIAL.
- Frontend smoke: screenshot conferma tachimetro renderizzato con 30,00 % / OTTIMO / breakdown Riservato Direzione visibile (admin) + fmtEUR a 2 decimali su tutte le righe.

---

## 13. API contract

- `GET /api/quotes/{qid}/financial-snapshot`
  ```
  200 {
    quote_id: str,
    quote_status: str,
    frozen: bool,
    is_admin_view: bool,
    financial_snapshot: FinancialSnapshot | RedactedFinancialSnapshot
  }
  ```
- `GET /api/quotes/{qid}` — ora include `financial_snapshot` (redatto per commerciale) come campo top-level della quote.
- Mutation endpoints (`POST/PATCH/DELETE /lines`, `PATCH /quotes/{qid}`, `DELETE /openings`, `POST /quotes/{qid}/status → accepted`) triggerano ricalcolo o freeze.

---

## 14. Prossimi passi (fuori scope V1)

1. Manual E2E PO — collaudo tachimetro live (§29 msg 392).
2. VANO MODEL V2 — solo dopo autorizzazione (§26).
3. Contract PDF v2 — riutilizzo `strip_margin_from_pdf_payload` per garantire zero leak.
4. Rilievo → Produzione → Assistenza — propagazione `financial_snapshot` congelato.
