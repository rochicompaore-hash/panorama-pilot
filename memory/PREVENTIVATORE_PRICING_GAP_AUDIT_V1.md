# PREVENTIVATORE_PRICING_GAP_AUDIT_V1
**Data:** 22 Set 2026 · **Fonte:** backend source of truth (Mongo `products`, `simple_services`, `technical_recipes`, `product_colors`, `zanzariere_colors`) interrogato via `POST /api/multi-cat/products/{pid}/configure` (script `/app/memory/scripts/pricing_gap_audit.py`, output `/app/memory/pricing_audit_rows.json`). Nessun prezzo inventato.

**Stati:** OK · MISSING_SALE_PRICE · MISSING_INTERNAL_COST · MISSING_FORMULA · NEEDS_PO_PRICING · DISABLED_FAIL_CLOSED

## Sintesi numerica
| Metrica | Valore |
|---|---|
| PRICES_PUBLISHED (voci/configurazioni prezzate e usabili nel Preventivatore) | **4.540** = Finestre 16 combinazioni tipologia×vetro (+ colori MASS/STANDARD) · Zanzariere 20 · Tapparelle 3 · Persiane 6 · Cassonetti 4.464 celle · Servizi 41 |
| PRICES_MISSING (sale) | **7** (LOGISTICS_LOADING, LOGISTICS_RETURN_OLD, DISPOSAL_WINDOW/ROLLER_BOX/ROLLER_KIT/SHUTTER/MOSQUITO) |
| INTERNAL_COSTS_MISSING | **7** (le stesse 7 voci: sale e cost entrambi assenti) — nessuna voce con sale presente e costo assente tra i prodotti reali |
| FORMULAS_MISSING | **6 famiglie** (ProEvolution WINDOW 3 ante, 4 ante, SLIDING_DOOR_WINDOW, VASISTAS_ONLY; ProEvolution Restauro tutte le tipologie; colore PVC SPECIAL policy) |
| DISABLED_FAIL_CLOSED | **9 prodotti legacy** `TO_CONFIRM` (`new_quote_enabled=false`) + 6 famiglie sopra (risposta `not_available`/`incomplete`, mai prezzo 0) + 7 servizi NEEDS_PO_PRICING |
| Cassonetti doppio markup | **NO** — `compute_grid` legge `cell.sale` dal listino; ×2.5 solo in `pricing_formula_metadata` documentale (non usato) |
| Smontaggio | **OK** sale 30 €/unità × qty; costo interno 20 € (REMOVE_ARMORED_DOOR 30 €) → bucket OTHER_DIRECT_COSTS |

## Tabella dettaglio
| CATEGORIA | PRODOTTO / SERVIZIO | VARIANTE | SALE PRICE | INTERNAL COST | FORMULA | STATO | SOURCE | AZIONE RICHIESTA |
|---|---|---|---|---|---|---|---|---|
| FINESTRE | ProEvolution | WINDOW 1 anta · vetri DOUBLE_STANDARD/DOUBLE_SATIN/TRIPLE_STANDARD/TRIPLE_SATIN · colori MASS (003) / STANDARD (100,096,694,110,154,048) | es. 1016,70 € (1200×1400 DS bianco) | 338,90 € | pricing_v3 recipe WINDOW_1_SASH ×3.0 | OK | `technical_recipes`, `workshop_cost_configs`, `commercial_pricing_rules`, `formulas.GLASS_PRICES_PER_SQM` | — |
| FINESTRE | ProEvolution | WINDOW 2 ante (stessi vetri/colori) | 1427,64 € | 475,88 € | recipe WINDOW_2_SASH | OK | idem | — |
| FINESTRE | ProEvolution | WINDOW 3 ante | — | — | recipe WINDOW_3_SASH assente (BR-03 telaio unico) | MISSING_FORMULA / DISABLED_FAIL_CLOSED | `quotable_configurations` | PO: formula ufficiale 3 ante |
| FINESTRE | ProEvolution | WINDOW 4 ante | — | — | assente | MISSING_FORMULA / DISABLED_FAIL_CLOSED | idem | PO: formula 4 ante |
| FINESTRE | ProEvolution | Colore PVC SPECIAL (019,145,146,109,402,663) | — | — | policy pellicolato speciale assente | NEEDS_PO_PRICING (`incomplete`) | `color_engine` | PO: maggiorazione SPECIAL |
| FINESTRE | ProEvolution | Profilatura/foil STANDARD +10% | incluso | incluso | BR-09 | OK | formulas | — |
| FINESTRE | ProEvolution | Ferramenta kit 45 € · soglia ribassata | incluso | incluso | hardware kit + THRESHOLD | OK | pricing_v3 | — |
| PORTEFINESTRE | ProEvolution DOOR_WINDOW | 1 anta / 2 ante · 4 vetri · MASS/STANDARD | 1649,37 € / 2334,32 € | 549,79 € / 778,11 € | recipe DOOR_WINDOW_1/2_SASH | OK | pricing_v3 | — |
| SCORREVOLI | ProEvolution SLIDING_DOOR_WINDOW | 2 ante | — | — | solo hardware, formula geometrica backlog | MISSING_FORMULA / DISABLED_FAIL_CLOSED | resolvers.py:101 | PO: formula scorrevole |
| FISSI / VASISTAS | ProEvolution VASISTAS_ONLY | 1 anta | — | — | recipe presente ma non in `quotable_configurations` | DISABLED_FAIL_CLOSED | technical_recipes | PO: conferma prezzabilità |
| FINESTRE | ProEvolution Restauro | tutte | — | — | nessuna technical_recipe per PROEVOLUTION_RESTAURO | MISSING_FORMULA / DISABLED_FAIL_CLOSED | technical_recipes | PO: ricette Restauro |
| PORTONCINI | Porta ingresso PVC / blindata | — | solo posa (INSTALL_PVC_ENTRY_DOOR 320 €, INSTALL_ARMORED_DOOR 450 €) | 250 € / 300 € | nessun prodotto catalogato | MISSING_SALE_PRICE (prodotto) | products | PO: listino portoncini |
| PROFILI | PVC ProEvolution (FRAME/SASH/REINFORCEMENT/GLAZING_BEAD/MEETING_STILE/MULLION/TRANSOM) | €/ml | interno | interno | V1_3 component prices | OK (interno) | `item_pricelists` / tech-config | — |
| VETRI | DOUBLE_STANDARD 76 · DOUBLE_SATIN 96 · TRIPLE_STANDARD 125 · TRIPLE_SATIN 156,25 €/m² min 0,50 m² | — | interno | interno | BR-07 | OK | formulas.py | — |
| FERRAMENTA | Kit standard 45 € | — | interno | interno | production_config | OK | production_config | — |
| COLORI | 13 colori PVC (dup. seed: 26 doc) · 4 famiglie zanzariere placeholder ZC_*_DEFAULT | — | — | — | mapping | OK (PVC) / NEEDS_PO (nomi colori zanzariere reali `TO_CONFIRM`) | product_colors, zanzariere_colors | PO: colori zanzariere reali; dedup seed |
| TAPPARELLE | Tapparella PVC | RAL_STANDARD 35 €/m² · WOOD_EFFECT 40 · RAFFAELLO 45 · min 1,50 m² · ×3 | 176,40 / 201,60 / 226,80 € (1200×1400) | 58,80 / 67,20 / 75,60 € | AREA color table | OK | products.pricing_config | — |
| ZANZARIERE | SWITCH_5 · SKAT · UNIKLAT · UNIKVER · UNIKCAT | BASE/WOOD_EFFECT/MARBLE/SPECIAL · min 1,5 (2,0 Skat/Uniklat) · ×3 | es. Unikver BASE 108,66 € | 36,22 € | AREA color table | OK | products.pricing_config | — |
| PERSIANE | Persiana alluminio | RAL / WOOD / SPECIAL · orientabile +99 €/m² · min 1,30 m² · ×2.5 | 1197 / 1255,80 / 1470 € (+orient. 1612,80/1671,60/1885,80) | 478,80 / 502,32 / 588 € | AREA_PURCHASE_MULTIPLIER | OK | products.pricing_config | — |
| CASSONETTI | Cassonetto Listino Ufficiale 2026 | 3 famiglie (BIANCO_MASSA/STANDARD/NON_STANDARD) × profondità 163/326/489/652 × cielino SI/NO × 186 dimensioni | da listino (es. 500×250 BM 163 c = 329,01 €; 1200×250 = 324,78 €) | da listino (101,23 €) | GRID lookup, NO ×2.5 | OK | `listino_completo_con_costi.xlsx` importato | — |
| POSA | 24 servizi INSTALL_* (finestre 1-2/3/4 ante, sottoluce, vasistas, fisso, scorrevole, porte, cassonetti, lamiere, tapparelle, motori, zanzariere) | PER_ITEM | 90–650 € | 70–500 € | resolver deterministico | OK | simple_services | — |
| SMONTAGGIO | REMOVE_WINDOW/ROLLER_BOX/ROLLER_KIT/SHUTTER/MOSQUITO/ARMORED_DOOR | PER_ITEM × qty riga | 30,00 € | 20,00 € (ARMORED 30) | dismantling_mode=INCLUDED | OK | simple_services | — |
| SMALTIMENTO | DISPOSAL_WINDOW/ROLLER_BOX/ROLLER_KIT/SHUTTER/MOSQUITO | PER_ITEM | — | — | fail-closed §8 | NEEDS_PO_PRICING (INCLUDED disabilitato in UI) | simple_services | PO: 5 coppie sale/cost |
| ENEA | ENEA_STANDARD 100 € · ENEA_INSURED 350 € | ONE_PER_QUOTE | 100 / 350 € | 50 / 120 € | FIXED_PRICE | OK | simple_services | — |
| TRASPORTO / CONSEGNA | STANDARD (oltre 90 gg) 0 € · EXPRESS +20% | — | 0 / +20% | — | delivery_policy | OK STANDARD / DISABLED_FAIL_CLOSED EXPRESS (tempistica da definire) | delivery_policy.py | PO: tempistica EXPRESS |
| LOGISTICA | LOGISTICS_LOADING · LOGISTICS_RETURN_OLD | VARIABLE | — | — | — | NEEDS_PO_PRICING | simple_services | PO: prezzo/costo |
| SERVIZI / EXTRA | REPAIR_ACCESSORIES 30 · REPAIR_ROLLER_KIT 60 · COPRIFILI 25 · IMBOTTI 50 · ACC_KIT_REPLACEMENT 60 · ACC_SMALL_PARTS 30 · ACC_COVER_STRIPS 25 · ACC_METAL_PVC_JAMBS 50 · INSTALL_METAL_COVER/SHEETS 30 | PER_ITEM | come indicato | 15–40 € | — | OK | simple_services | — |
| ALTRO | 9 prodotti legacy (Cassonetto linear_m, Tapparella PVC, Zanzariera avvolgibile, Persiana/Scuro PVC, Finestra Alluminio TT, Finestra PVC standard, PROEVOLUTION TEST-MOTORE, …) | — | — | — | — | DISABLED_FAIL_CLOSED (`legacy=true`, `new_quote_enabled=false`, TO_CONFIRM) | products | PO: classificare o archiviare |
| ALTRO | 5 test fixtures (TEST_AREA_100, TEST_ZANZARIERA_130, TEST_LINEAR_25, TEST_PER_ITEM_50, TEST_FIXED_120) | — | fittizio | assente | — | MISSING_INTERNAL_COST — nascoste di default (`is_test_fixture`) | products | nessuna (non commerciali) |
| PACCHETTI | BASE / ADVANCED / PREMIUM | — | multiplier null | — | — | NEEDS_PO_PRICING (non wired nel preventivo) | commercial_packages | PO: multiplier/servizi |

## UNRESOLVED_PO_PRICING (elenco esatto)
1. ProEvolution WINDOW 3 ante — formula/ricetta (BR-03).
2. ProEvolution WINDOW 4 ante — formula/ricetta.
3. ProEvolution SLIDING_DOOR_WINDOW — formula geometrica.
4. ProEvolution VASISTAS_ONLY — conferma prezzabilità (ricetta presente, non abilitata).
5. ProEvolution Restauro — ricette tecniche per tutte le tipologie.
6. Colore PVC SPECIAL (6 codici) — policy maggiorazione pellicolato speciale.
7. DISPOSAL_WINDOW / ROLLER_BOX / ROLLER_KIT / SHUTTER / MOSQUITO — 5 coppie sale/cost.
8. LOGISTICS_LOADING / LOGISTICS_RETURN_OLD — sale/cost.
9. Consegna EXPRESS — tempistica cliente (prezzo +20% già definito).
10. Portoncini (PVC/blindati) — nessun prodotto a listino (solo posa).
11. Colori zanzariere reali (ora placeholder ZC_*_DEFAULT).
12. Pacchetti commerciali BASE/ADVANCED/PREMIUM — multiplier e servizi inclusi.
13. 9 prodotti legacy TO_CONFIRM — classificare o archiviare.

## Osservazioni non bloccanti
- `product_colors` e `zanzariere_colors` contengono ogni codice 2 volte (seed idempotente non applicato al secondo run): il lookup resta corretto (stessa categoria), consigliato dedup in sessione dati (non fatto: freeze).
- Smontaggio selezionabile solo con `installation_mode=SUPPLY_AND_INSTALLATION` (policy Iter 50); con SUPPLY_ONLY non è offerto.
