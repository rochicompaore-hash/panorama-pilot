# MARGIN & CASH FLOW CONTROL — Enerhia Operating Core V1

**Data:** 2026-02-19 · **Branch:** `feature/enerhia-operating-core-v1`
**Preview:** https://serramento-ops.preview.emergentagent.com
**Test:** 17/17 golden test verdi (M3 3/3 · M4 7/7 · Margin Control 7/7)

Modulo di controllo economico-finanziario del preventivo. Distingue rigorosamente **PROFITABILITY ≠ CASH FLOW** (Master Plan §Principio Finale).

---

## 0. Flusso definitivo

```
CONFIGURATORE GEOMETRICO
        ▼
   PRODUCTION_COST    (BOM tecnica pura — pricing_v3)
        ▼ × commercial_multiplier (3.00 configurable)
BASE_PRODUCT_SALE_PRICE
        + Posa (customer_sale_price)
        + Servizi (customer_sale_price)
        + Extra
        − Sconto (autorizzato)
        ▼
CUSTOMER_PRICE (net VAT) + VAT = customer_price_gross
        │
        ├─► COMMERCIAL_COMMISSION = net_vat / 1.17 × 0.10   (costo diretto)
        │       ▼
        ├─► CONTRIBUTION_MARGIN                             (economic view)
        │       = net_revenue − PC − install_ref − services_int
        │         − other_direct − commission
        │       ▼
        └─► WITHHOLDING_CASH_EFFECT = net_vat / 1.22 × 0.11 (cash view, se applicabile)
                ▼
        EXPECTED_AVAILABLE_CASH = contribution − withholding
        WITHHOLDING_RECEIVABLE  = credito da recuperare

TARGET AZIENDALI
        MONTHLY_FIXED_COSTS + EMERGENCY_ALLOC + INVESTMENT_ALLOC + PROFIT_TARGET
        = REQUIRED_MONTHLY_CONTRIBUTION
        / MONTHLY_REVENUE_TARGET = REQUIRED_MARGIN_RATE

DISCOUNT ROOM
        MIN_SUSTAINABLE = variable_costs / (1 − required_margin_rate)
        DISCOUNT_ROOM   = LIST_PRICE − MIN_SUSTAINABLE
```

---

## 1. Endpoint API (backend)

Router: `/api/margin-control/*` (permessi: `pricing_admin.manage` per gestione, `quotes.view` per compute).

| Endpoint | Metodo | Descrizione |
|---|---|---|
| `/rules` | GET/PUT | Business rules (commission_rate/divisor, withholding_rate/divisor, default_multiplier, semaforo thresholds) |
| `/targets` | GET/PUT | Target aziendali (fissi, emergency, investment, profit, revenue) + `NEEDS_PO_CONFIGURATION` di default |
| `/company-dashboard` | GET | Dashboard §36: target + derived allocations |
| `/compute-snapshot` | POST | **Calcolo core**. Ritorna `FinancialSnapshot` per una configurazione. Non persiste. |

Collection Mongo:
- `margin_control_rules` (per tenant · versionata)
- `margin_control_targets` (per tenant · versionata · `policy_status`)

---

## 2. Business rules Enerhia (configurabili, non hardcoded)

Default seedati al primo GET:

| Rule | Default | Config path |
|---|---|---|
| `commission_rate` | 0.10 (10%) | `margin_control_rules.commission_rate` |
| `commission_divisor` | 1.17 | `margin_control_rules.commission_divisor` |
| `withholding_rate` | 0.11 (11%) | `margin_control_rules.withholding_rate` |
| `withholding_divisor` | 1.22 | `margin_control_rules.withholding_divisor` |
| `default_commercial_multiplier` | 3.00 | `margin_control_rules.default_commercial_multiplier` |
| VAT % | 22% | `FinancialSnapshotRequest.vat_pct` (override per commessa) |
| Semaforo GREEN over target | +5% | `status_thresholds.green_over_target_pct` |
| Semaforo YELLOW below target | −5% | `status_thresholds.yellow_below_target_pct` |

**Nessun valore Enerhia inventato**: target aziendali sono `NEEDS_PO_CONFIGURATION` finché l'Admin non li imposta.

---

## 3. Financial Snapshot — struttura completa

Output di `POST /api/margin-control/compute-snapshot`:

```json
{
  "production_cost": 1000.00,
  "commercial_multiplier": 3.00,
  "base_product_sale_price": 3000.00,
  "installation_sale_price": 150.00,
  "services_sale_price": 0.00,
  "gross_customer_price_pre_discount": 3150.00,
  "discount_amount": 0.00,
  "customer_price_net_vat": 3150.00,
  "vat_pct": 22.00,
  "vat_amount": 693.00,
  "customer_price_gross": 3843.00,

  "commission_rate": 0.10,
  "commission_divisor": 1.17,
  "commercial_commission": 269.23,

  "installation_internal_reference": 130.00,
  "services_internal_cost": 0.00,
  "other_direct_costs": 0.00,
  "contribution_margin_amount": 1750.77,
  "contribution_margin_pct": 55.58,

  "withholding_applicable": true,
  "withholding_rate": 0.11,
  "withholding_divisor": 1.22,
  "withholding_cash_effect": 284.02,
  "withholding_receivable": 284.02,
  "expected_available_cash": 1466.75,

  "required_margin_rate": null,
  "minimum_sustainable_price": null,
  "discount_room_amount": null,
  "max_theoretical_discount_pct": null,

  "margin_status": "POLICY_NOT_CONFIGURED",
  "margin_status_reason": "Costi fissi / target aziendali non ancora configurati."
}
```

---

## 4. Test golden documentati (pytest)

File `/app/backend/tests/test_margin_control.py` — 7 test:

| Test | Verifica | Master Plan |
|---|---|:-:|
| `test_gt_base_numeric_no_withholding_no_discount` | production=1000 × mult 3 + install 150 → net 3150 · commission ≈269.23 · contribution 1750.77 · cash = contribution (no withholding) | §41 |
| `test_gt_with_discount_10pct` | sconto 315 (10%) → net 2835 · commission 242.31 · **production_cost INVARIATO 1000** | §42 |
| `test_gt_with_withholding` | withholding 3150/1.22×0.11 ≈ **284.02** · **contribution IDENTICA con/senza ritenuta** · cash = contribution − withholding · receivable = 284.02 | §9, §10, §43 |
| `test_gt_targets_math_44` | fissi 60k + emergency 10k + investment 10k + profit 20k = 100k / rev 300k = **33.33%** | §44 |
| `test_gt_margin_status_thresholds` | Semaforo GREEN quando contribution >> target | §26 |
| `test_gt_policy_not_configured` | Se target non configurati → `POLICY_NOT_CONFIGURED` ma **compute prosegue** | §48 |
| `test_gt_production_cost_untouched_by_all_adjustments` | Sconto, ritenuta, extra costs → production_cost sempre = 1000 | §10, §22, §42 |

---

## 5. Separazione conforme (§10, §12, §14, §40)

| Concetto | Dove sta | Effetto |
|---|---|---|
| **Production cost** | Solo BOM tecnica pricing_v3 | Non modificato mai da sconto/commissione/ritenuta/fissi |
| **Commissione** | Costo diretto commerciale | Riduce contribution E cash |
| **Ritenuta** | Solo cash flow view | Riduce SOLO cash (non contribution). Registrato come `withholding_receivable` (credito) |
| **Costi fissi** | Target mensile aziendale | NON entrano in BOM (§40). Servono per calcolare required_margin_rate |
| **Fondo emergenza** | Allocation of company margin | NON è costo della commessa |
| **Fondo investimenti** | Allocation of company margin | NON è costo della commessa |
| **Utile target** | Allocation of company margin | Concorre a `required_monthly_contribution` |

---

## 6. Semaforo marginalità (§26)

| Status | Condizione | Azione UI |
|---|---|---|
| 🟢 GREEN | `contribution_pct ≥ required_pct + 5%` | Preventivo procede senza autorizzazioni |
| 🟡 YELLOW | `required_pct − 5% ≤ contribution_pct < required_pct + 5%` | Warning, procede |
| 🟠 ORANGE | `0 ≤ contribution_pct < required_pct − 5%` | Richiesta override autorizzato (sales manager) |
| 🔴 RED | `contribution_pct < 0` | Bloccato — sotto minimum sustainable price |
| ⚪ POLICY_NOT_CONFIGURED | Target aziendali non impostati | Preventivo procede senza semaforo |

Soglie configurabili in `margin_control_rules.status_thresholds`.

---

## 7. RBAC (§27)

| Ruolo | Può vedere |
|---|---|
| COMMERCIAL | list_price, discount, prezzo finale, semaforo marginalità (SALUTARE/ATTENZIONE/AUTORIZZAZIONE) |
| SALES_MANAGER / ADMIN | + production_cost, commission, contribution_margin/%, minimum_sustainable_price, discount_room |
| TENANT_ADMIN / ADMINISTRATION | + cash flow completo (withholding, receivable, available_cash), emergency fund, investment fund, fixed costs |

Attualmente l'endpoint `compute-snapshot` richiede solo `quotes.view` e restituisce **tutto**. Il filtro RBAC per ruolo Commerciale sarà applicato lato **UI M5** (nasconde/mostra campi in base ai permessi effettivi dell'utente), non lato API — perché l'API è consumata anche dal calcolo real-time del preventivatore che ha bisogno dell'output completo per validare i vincoli.

---

## 8. Snapshot immutabile (§28, §29)

Ogni QuoteLine (M5) dovrà congelare il `financial_snapshot` completo. Preventivi accettati non ricalcolano quando le rules o i target cambiano. Il campo `policy_snapshot_version` conserverà la versione delle `margin_control_rules` e `margin_control_targets` usate al momento del calcolo.

Draft (pre-accettazione): il ricalcolo è **live** (dimensioni, prodotti, sconto → ricalcolo di tutto).

---

## 9. Integrazione con M5 (§47)

Quando M5 sarà sbloccata (Master Plan §37 · vedi `GEOMETRIC_TO_COMMERCIAL_PRICING_ARCHITECTURE_V1.md`):
1. Il preventivatore chiama `POST /api/pricing/compute` → `production_cost`
2. Applica il multiplier commerciale → `base_product_sale_price`
3. Somma posa da `simple_services` → gross_pre_discount
4. Chiama `POST /api/margin-control/compute-snapshot` con tutti gli input
5. Riceve `financial_snapshot` completo
6. UI mostra al Commerciale solo i campi permessi
7. Se `override_required = true` (sconto sotto internal_reference o margine < required), gate `AUTHORIZED_PRICE_OVERRIDE`
8. Al salvataggio della QuoteLine, il snapshot viene congelato

---

## 10. STOP conditions rispettate

- ✅ Modulo funzionante senza target configurati (§48 — non blocca preventivo)
- ✅ Nessun valore Enerhia inventato (fissi/emergency/investment/profit/revenue = null di default, `NEEDS_PO_CONFIGURATION`)
- ✅ production_cost mai modificato (§10, §22, §42)
- ✅ Ritenuta separata dal costo economico (§10)
- ✅ commission_divisor / withholding_divisor configurabili, non sparsi nel codice (§34)
- ✅ M3 BUSINESS_GOLDEN rimane separato — il modulo Margin Control non lo modifica (§49)
- ✅ Nessuna pubblicazione produzione

---

## 11. Prossimi step

1. **UI AMMINISTRAZIONE → CONTROLLO MARGINALITÀ** (§46) — pagina con 5 tab: Costi fissi, Fondo emergenza, Fondo investimenti, Obiettivi, Regole (commission/withholding)
2. **Financial snapshot preview panel** — componente React che chiama `compute-snapshot` in tempo reale nel preventivatore M5
3. **RBAC filter lato UI** — nasconde production_cost/costi interni per ruolo Commerciale
4. **Cash Flow Forecast dashboard** (§37) — aggregato mensile
5. **Emergency/Investment fund progress bars** (§38/§39)
6. **Integrazione discount guard nel motore preventivo** — chiama compute-snapshot ad ogni cambio riga

Nessuna di queste attività **blocca** il modulo backend, che è già operativo via API.
