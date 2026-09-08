# PERSIANE_PRICING_VALIDATION — PO msg 401 (§12-§23, §35)

**Data**: 2026-09-08 · **Verdetto: PERSIANE = PASS**

## Implementazione
- Prodotto seedato su tutti i tenant: `PERSIANA_STD` — "Persiana in alluminio (RAL / Effetto legno / Speciali)", categoria `PERSIANE_SCURI`, `pricing_model = AREA_PURCHASE_MULTIPLIER` (nuovo modello canonico, `app/services/multi_category_pricing.py::compute_area_purchase_multiplier`).
- `pricing_config`: `purchase_cost_table_per_m2 {RAL 285, WOOD 299, SPECIAL 350}` · `minimum_billable_area_m2 1.30` (PER PEZZO) · `commercial_multiplier 2.5` · `orientable_surcharge_per_m2 99` · `color_map {RAL→RAL, WOOD_EFFECT→WOOD, SPECIAL_RAFFAELLO→SPECIAL}` · `pricing_version persiane_2026_09_v1`.
- Formula: `billable = max(L×H/1e6, 1.30)` per unità → `effective_rate = purchase(cat) + 99 (se orientabile)` → `purchase_item = billable × effective_rate` → `sale_item = purchase_item × 2.5` → totali × qty.
- Snapshot (§22): `real_area_m2, billable_area_m2, color_price_category, purchase_rate_per_m2, orientable, orientable_surcharge_per_m2, effective_purchase_rate, purchase_cost_per_item, purchase_total_cost, commercial_multiplier=2.5, unit_sale_price_per_m2, unit_price_final, sale_price_total`.
- Fail-closed (§23): `MISSING_COLOR_PRICE_CATEGORY`, `MISSING_ORIENTABLE_STATE`, `INVALID_DIMENSIONS`, `INVALID_QUANTITY`, `MISSING_PURCHASE_RATE_TABLE`, `MISSING_COMMERCIAL_MULTIPLIER`, `MISSING_ORIENTABLE_SURCHARGE`. Mai 0 €.
- Posa/smontaggio SEPARATI (listino montaggio ufficiale, nessun multiplier): `INSTALL_SHUTTER_1_2_SASH` 130/150 € · `REMOVE_SHUTTER` 20/40 € per unità, qty = qty prodotto.
- Financial engine: `purchase_total_cost → SUPPLY_COST`, posa interna → INSTALLATION_COST, smontaggio interno → OTHER_DIRECT_COSTS.
- RBAC commerciale: rimossi `purchase_rate_per_m2, effective_purchase_rate, orientable_surcharge_per_m2, purchase_cost_per_item, purchase_total_cost, commercial_multiplier` dallo snapshot e `purchase_cost_table_per_m2, commercial_multiplier, orientable_surcharge_per_m2` dal `pricing_config` (list + get prodotto).
- UI: card `cfg-persiana` (L, H, qty, Categoria colore, Lamelle Fisse/Orientabili) + dettaglio `preview-persiana-detail`.

## Sale €/m² (§17)
| Categoria | Fissa | Orientabile |
|---|---|---|
| RAL | 712,50 ✅ | 960,00 ✅ |
| WOOD | 747,50 ✅ | 995,00 ✅ |
| SPECIAL | 875,00 ✅ | 1.122,50 ✅ |

## Golden minimo 1,30 m² (§18) — input 800×1000 (0,80 m²)
| Caso | Atteso | Engine | API/UI |
|---|---|---|---|
| RAL fissa | 926,25 | 926,25 ✅ | 926,25 ✅ (browser H) |
| WOOD fissa | 971,75 | 971,75 ✅ | 971,75 ✅ (API line, internal 388,70) |
| SPECIAL fissa | 1.137,50 | 1.137,50 ✅ | — |
| RAL orientabile | 1.248,00 | 1.248,00 ✅ | — |
| WOOD orientabile | 1.293,50 | 1.293,50 ✅ | — |
| SPECIAL orientabile | 1.459,25 | 1.459,25 ✅ | 1.459,25 ×2 = 2.918,50 ✅ (qty 2, minimo per pezzo) |
| qty>1 minimo per pezzo | 926,25 × 3 = 2.778,75 | ✅ | UI: 800×1000 RAL qty 2 → 1.852,50 ✅ |

## Golden 1200×1500 (§19) — 1,80 m², nessun minimo
| Caso | Atteso | Engine | API/UI |
|---|---|---|---|
| RAL | 1.282,50 | ✅ | ✅ (browser F) |
| WOOD | 1.345,50 | ✅ | — |
| SPECIAL | 1.575,00 | ✅ | — |
| RAL orientabile | 1.728,00 | ✅ | ✅ (browser G) |
| WOOD orientabile | 1.791,00 | ✅ | — |
| SPECIAL orientabile | 2.020,50 | ✅ | — |

## E2E quote (§20-§21, §37)
| Scenario | Risultato |
|---|---|
| SUPPLY_ONLY, RAL 1200×1500 qty 1 | line 1.282,50 · internal_cost 513,00 · automatic_services [] · FS supply 513 / install 0 / other 0 ✅ |
| SUPPLY_AND_INSTALLATION + dismantling INCLUDED, RAL orientabile 1200×1500 qty 2 | prodotto 3.456,00 + posa 2×150 = 300 + smontaggio 2×40 = 80 → subtotal 3.836,00 · FS supply 1.382,40 · installation 260,00 · other 40,00 ✅ (×2.5 NON applicato ai servizi) |
| Save / reload / recompute | riga persistita, recompute autoritativo backend (add_line ignora prezzi client) ✅ |

Test permanenti: `backend/tests/test_persiane_pricing_golden.py` (33 test) + `backend/tests/test_pricing_integrity_audit_msg401.py` (testing agent) — **PASS**.
