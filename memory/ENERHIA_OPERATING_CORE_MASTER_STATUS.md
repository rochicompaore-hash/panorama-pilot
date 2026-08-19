# ENERHIA OPERATING CORE — MASTER STATUS

**Branch:** `feature/enerhia-operating-core-v1`
**Preview:** https://serramento-ops.preview.emergentagent.com

## Legenda status

| Status | Significato |
|---|---|
| `NOT_STARTED` | Non ancora iniziato |
| `IN_PROGRESS` | Lavorazione in corso |
| `E2E_READY` | Backend + Frontend implementati e testati automaticamente |
| `APPROVED` | Collaudato manualmente dall'utente |

---

## Milestone status

| M | Nome | Status | Preview URL | Commit | Readiness |
|---|---|---|---|---|---|
| 1 | Customer + Site + Timeline + Quote header | `E2E_READY` (attende approvazione) | `/customers`, `/customers/:id` | (post-M1 P2) | 100% |
| 2 | Configurazione tecnica (Single Source of Truth) | `E2E_READY` (P0 completa) | `/tech-config` (7 tab) | (M2 P0) | 85% |
| 3 | Golden Test economico (GT-REAL) | `TECHNICAL_TEST_READY` · **BUSINESS_GOLDEN = FAIL** (delta 28.34 €) | pytest | (M3) | 70% |
| 4 | Copertura configurazioni (WINDOW_1_2, DOOR_WINDOW_1_2, VASISTAS) | `E2E_READY` (5 config + foil, 7/7 test) | pytest + `/tech-config` | (M4) | 90% |
| 5 | Preventivatore commerciale unico | `BLOCKED_BY_ARCHITECTURE` (§37 — due motori paralleli attivi) | — | — | 0% |
| 6 | PDF preventivo | `NOT_STARTED` | — | — | 0% |
| 7 | Contratto (con snapshot congelati) | `NOT_STARTED` | — | — | 0% |
| 8 | Document center | `NOT_STARTED` | — | — | 0% |
| 9 | JOB / Commessa | `NOT_STARTED` | — | — | 0% |
| 10 | Rilievo tecnico + abaco | `NOT_STARTED` | — | — | 0% |
| 11 | Production order + BOM/cut list | `NOT_STARTED` | — | — | 0% |
| 12 | Magazzino | `NOT_STARTED` | — | — | 0% |
| 13 | Fabbisogno + acquisti | `NOT_STARTED` | — | — | 0% |
| 14 | Pianificazione posa | `NOT_STARTED` | — | — | 0% |
| 15 | Assistenza | `NOT_STARTED` | — | — | 0% |
| 16 | Lead conversion wizard | `NOT_STARTED` | — | — | 0% |
| 17 | Timeline completa (system events) | `IN_PROGRESS` (base creata M1) | — | — | 40% |
| 18 | RBAC finale | `IN_PROGRESS` (ruoli seedati) | — | — | 30% |
| 19 | Obiettivi commerciali | `NOT_STARTED` | — | — | 0% |
| 20 | Pagamenti + cash flow | `NOT_STARTED` | — | — | 0% |
| 2.14 | Servizi & Prezzi Semplici (dual pricing) | `E2E_READY` (backend + seed listino Enerhia) | `/api/simple-services` | (questo turno) | 70% (UI in M5) |

## Sezioni M2 (Configurazione tecnica) — dettaglio

| # | Sezione | Status | Note |
|---|---|:---:|---|
| 2.1 | Sistemi profilo | `IN_PROGRESS` | `technical_recipes` esiste, UI read-only |
| 2.2 | Componenti e costi | `E2E_READY` | UI CRUD via `/tech-config/component-prices` — schema listino v3 |
| 2.3 | Ricette e formule | `IN_PROGRESS` | Formule V1_3 in codice `services/pricing_v3/formulas.py`, editing UI aperto |
| 2.4 | Vetri | `E2E_READY` | ✅ Nuova collection `glass_price_configs` + tab UI. Valori ufficiali seedati |
| 2.5 | Ferramenta | `E2E_READY` | ✅ Nuova collection `hardware_rules` + tab UI. Resolver `(opening_type, n_sashes)` |
| 2.6 | Tempi produzione | `E2E_READY` | ✅ Nuova collection `production_time_configs` + tab UI |
| 2.7 | Costo officina | `APPROVED` | Già 180 €/h, versionato |
| 2.8 | Scambio battuta | `NOT_STARTED` | Formula `H/1000×5.50` da integrare in BOM WINDOW_2_SASH |
| 2.9 | Soglia ribassata | `NOT_STARTED` | Formule `H/1000×29.50+7.49` / `+9.84` per DOOR_WINDOW_* |
| 2.10 | Montante fisso | `NOT_STARTED` | `H/1000×7.51×q` |
| 2.11 | Traverso | `NOT_STARTED` | `L/1000×7.50×q` |
| 2.12 | Colori | `IN_PROGRESS` | +10% pellicolato applicato solo su PVC_ELIGIBLE_ROLES |
| 2.13 | Regola commerciale | `APPROVED` | 4 metodi supportati (MULTIPLIER/MARKUP/MARGIN/FIXED) |

---

## Blocchi noti / conferme in attesa

| # | Item | Stato | Serve dal cliente |
|---|---|---|---|
| B1 | Prezzo `GLAZING_BEAD_PROEVOLUTION` | seed 2.10 €/ml (placeholder) | Prezzo reale listino Enerhia |
| B2 | Prezzi profili V1_3 (FRAME 4.02, FRAME_REINFORCEMENT 1.52, SASH 2.31, SASH_REINFO 1.34) | seed V1_3 (documentati) | Listino Enerhia reale — questo spiega delta di ~28 € vs Excel |
| B3 | Ricetta 3-ante telaio unico | fail-closed `MISSING_TECHNICAL_RECIPE` | Ricetta Excel ufficiale |
| B4 | Codici fornitore componenti | `NEEDS_SUPPLIER_CODE_CONFIRMATION` | Solo FRAME (5103), SASH (12130) noti |
| B5 | Lead time BICOLOR | `NEEDS_PO_CONFIRMATION` | Da confermare |
| B6 | Clausole contratto ufficiali | `WAITING_FOR_PO_CONTRACT_TEMPLATE` | Da fornire |

---

## Regole di stop rispettate (Master Plan)

- ✅ Solo preview, nessuna pubblicazione in produzione
- ✅ Nessuna migrazione distruttiva
- ✅ Nessun prezzo inventato — placeholder documentati con `NEEDS_PO_CONFIRMATION`
- ✅ Nessuna eliminazione di codice legacy (commercial_perimeter, parametric)
- ✅ Motore v3 fail-closed su MISSING_*
- ✅ Snapshot congelato preservato (preventivi storici invariati)
- ⚠️ **NUOVO §37 Master Plan**: identificati due motori attivi (`pricing_v3` autoritativo + `commercial_perimeter` legacy). **M5 NON INIZIA** finché non è certificato l'uso esclusivo di `pricing_v3` per nuovi preventivi. Vedi `/app/memory/GEOMETRIC_TO_COMMERCIAL_PRICING_ARCHITECTURE_V1.md`.
- ✅ **NUOVO §9 Master Plan**: default commercial multiplier = **3.00** verificato attivo (production_cost 338.90 × 3 = base_product_sale_price 1016.70 €).
