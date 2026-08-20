# COMMERCIAL PACKAGES V1 — Enerhia Operating Core

**Data:** 2026-02-19 · **Branch:** `feature/enerhia-operating-core-v1`
**Stato:** Backend E2E_READY · UI in backlog · Multiplier `NEEDS_PO_CONFIGURATION`

## Principio

`production_cost` (dal Configuratore Geometrico) **non cambia** con il pacchetto (§1). Cambia il layer commerciale: **multiplier**, servizi inclusi, costi diretti, contribution margin.

## Backend consegnato

**Router** `/api/commercial-packages/*` (permesso `pricing_admin.manage`):
- `GET /` → lista 3 pacchetti seedati (BASE/ADVANCED/PREMIUM)
- `GET /{id}` → dettaglio con tutte le policy
- `PATCH /{id}` → modifica multiplier, warranty, delivery days, discount policy, min contribution margin %, ecc.
- `POST /simulate` → **Package Profitability Simulator** (§24). Input: `production_cost` + `included_services_internal_cost_map`. Output: BASE/ADVANCED/PREMIUM affiancati con sale price, commissione, contribution margin €/%, cash disponibile, semaforo.

**Collection** `commercial_packages` (tenant-scoped, versionata).

## Seed pacchetti (§5-§16)

| Campo | BASE | ADVANCED | PREMIUM |
|---|---|---|---|
| `commercial_multiplier` | **null (NEEDS_PO_CONFIGURATION)** | **null** | **null** |
| `delivery_min-max_days` | 120-180 | 90-120 | 30-30 |
| `warranty_months` | 24 | 120 | 180 |
| `product_origin_policy` | FOREIGN_PREFERRED_OR_ALLOWED | ITALIAN_PREFERRED_EQUIVALENT_FOREIGN_ALLOWED | ITALY_ONLY |
| `installation_policy` | INCLUDED | INCLUDED | INCLUDED |
| `installation_certification` | — | — | BGL |
| `site_transport_policy` | INCLUDED | INCLUDED | INCLUDED |
| `floor_transport_policy` | EXCLUDED | INCLUDED_UP_TO_LIMIT (3° piano) | INCLUDED |
| `platform_policy` | EXCLUDED | EXCLUDED | INCLUDED_UP_TO_LIMIT (6° piano) |
| `platform_available_below_max_floor` | — | — | **true** (§14) |
| `disposal_policy` | EXCLUDED | INCLUDED | INCLUDED |
| `enea_policy` | EXCLUDED | INCLUDED_BASIC | INCLUDED_ASSURED |
| `final_cleaning_policy` | EXCLUDED | EXCLUDED | INCLUDED |
| `priority_support_policy` | EXCLUDED | EXCLUDED | INCLUDED |
| `security_partner_policy` | EXCLUDED | DISCOUNT | FULL_PACKAGE (299 € display) |

## Regole conformi al piano

- **§17**: `included_services` NON hanno customer_increment > 0 ma HANNO `internal_direct_cost`. Il simulator accetta `included_services_internal_cost_map` per ogni pacchetto.
- **§21**: `PRODUCT_PACKAGE_SALE_PRICE = production_cost × package_multiplier`. Servizi inclusi non sommati al cliente.
- **§22**: Contribution margin calcolato includendo i costi diretti dei servizi del pacchetto. La ritenuta resta esclusa (rimane in cash view).
- **§25/§48**: Nessun multiplier inventato. Default `null`. Simulator ritorna esplicitamente `NEEDS_PO_CONFIGURATION`.
- **§27**: Ogni PATCH incrementa `version`. QuoteLine future dovranno congelare `package_version`.
- **§32**: Il simulator riusa `_compute_snapshot` del modulo Margin Control (unica fonte di verità economica).

## Test cardinale (§41) — dimostrato in preview

Con multiplier TEMPORARY (2.5 / 3.0 / 3.5) e servizi inclusi (30 / 200 / 500 €) su `production_cost = 1000 €`:

| Pacchetto | Sale | Included direct cost | Contribution € | Contribution % |
|---|---:|---:|---:|---:|
| BASE     | 2500 |  30 | 1256.32 | **50.25%** |
| ADVANCED | 3000 | 200 | 1543.59 | **51.45%** |
| PREMIUM  | 3500 | 500 | 1700.85 | **48.60%** |

**Dimostra §25**: Premium NON è automaticamente il più marginale — dipende dal bilanciamento multiplier / costi inclusi.

## Integrazione Margin Control

Il simulator richiama internamente `_compute_snapshot` (modulo Margin Control), quindi tutte le regole di:
- commissione `net/1.17×0.10` (§40)
- ritenuta `net/1.22×0.11` (§39)
- semaforo GREEN/YELLOW/ORANGE/RED
- discount room (se `required_margin_rate` configurato)

sono applicate automaticamente ai pacchetti. Nessuna duplicazione di logica.

## STOP conformi al piano

- ✅ **§25**: Multiplier non inventati (null default)
- ✅ **§47**: Nessun PDF/Contratto avviato
- ✅ **§50**: Fermato dopo `PACKAGE_ENGINE = E2E_READY`. UI Admin package configuration in backlog per prossima iterazione.
- ✅ Nessuna modifica al motore pricing_v3 (production_cost invariato)
- ✅ Rispetta §37 (M5 preventivatore commerciale unificato resta bloccato)

## Prossimi step (dopo scelta multiplier da parte del PO)

1. **UI Admin** `AMMINISTRAZIONE → CONFIGURAZIONE COMMERCIALE → PACCHETTI` (§26)
2. **Package selector** nella scheda preventivo (draft), con ricalcolo live via simulator
3. **Comparazione cliente** (§30/§31): 3 colonne senza production_cost/multiplier/margin
4. **QuoteLine.package_snapshot** — congelamento immutabile (§28)
5. **PackageDiscountPolicy** entity separata (§33)
