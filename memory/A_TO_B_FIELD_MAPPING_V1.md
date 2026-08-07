# A → B FIELD MAPPING V1 — Sistema commerciale → Sistema tecnico autorevole
**Iter 38** · Read-only · Zero codice modificato · Attende cross-review

## Regole
- Fonte autorevole = Sistema B (tecnico)
- Sistema A commerciale referenzia B (nessun secondo listino)
- Codici temp con `needs_supplier_code_confirmation=true` accettati
- `technical_snapshot` immutabile ai cambi listino; `commercial_snapshot` immutabile ai cambi moltiplicatore

## Legenda colonne
`src_system` · `src_collection` · `src_field` · `meaning` · `unit` · `value_source` · `dest_proposed` · `transform` · `versioned` · `req` · `motor` · `loss_risk` · `confirm_status`

## Mapping (raggruppato per dominio)

### Sistemi profilo
| src_sys | src_coll | src_field | meaning | dest | transform | ver | req | motor | loss | conf |
|---|---|---|---|---|---|---|---|---|---|---|
| A | products | key | codice sistema | B.profile_systems.code | copy | Y | Y | tech | none | OK |
| A | products | name | nome | B.profile_systems.name | copy | Y | Y | tech | none | OK |
| A | products | material | pvc/alu/wood | B.profile_systems.material | copy | Y | Y | tech | none | OK |
| A | products | version | versione | B.profile_systems.version | copy | Y | Y | tech | none | OK |
| B | profile_systems.tech | bar_length_mm | lunghezza barra | B.production_config.bar_length_pvc_mm (override per system) | consolidare in production_config, override in profile_systems.tech | Y | N | tech | riconciliazione | MEDIA |

### Componenti tecnici (profili)
| src_sys | src_coll | src_field | meaning | dest | transform | ver | req | motor | loss | conf |
|---|---|---|---|---|---|---|---|---|---|---|
| A | products.components[] | code | codice articolo | B.profiles.code | copy + FK a profile_systems | Y | Y | tech | dedup se già in B | verifica |
| A | products.components[] | category | telaio/anta/... | B.profiles.role (FRAME/SASH/…) | map: telaio→FRAME, anta→SASH, rinforzo_telaio→FRAME_REINFORCEMENT, rinforzo_anta→SASH_REINFORCEMENT, fermavetro→GLAZING_BEAD, scambio_battuta→MEETING_STILE | Y | Y | tech | mapping ambiguo per componenti non catalogati | ATTENZIONE |
| A | products.components[] | applies_to[] | tipologia | B.bom_templates.product_key + component.condition[] | 1a→window_1_leaf, 2a→window_2_leaves, PF→door variants | Y | Y | tech | none | OK |
| A | products.components[] | waste_percentage | sfrido % | B.bom_templates.components[].waste_pct | copy | Y | N | tech | duplicazione (già in bom) | consolidare in B |
| A | products.components[] | formula_qty | formula quantità | B.bom_templates.components[].quantity_formula | AST parser (formula.py) | Y | N | tech | verificare parsing | OK |
| A | products.components[] | formula_cut | formula lunghezza | B.bom_templates.components[].length_formula | idem | Y | N | tech | idem | OK |

### Componenti nuovi (da V1.2/V1.3)
| Ruolo | Codice temp | Prezzo | Unità | Formula | Dest |
|---|---|---|---|---|---|
| MEETING_STILE | MEETING_STILE_TEMP | 5.50 €/ml | EUR_PER_ML | H/1000 (n_sashes≥2) | B.profiles + item_pricelists(kind=cost) |
| THRESHOLD | THRESHOLD_TEMP | 29.50 €/ml + fisso | EUR_PER_ML + FIXED | H/1000×29.50 + (7.49 se 1a, 9.84 se 2a) | B.profiles + config a livello di sistema |
| FIXED_MULLION | FIXED_MULLION_TEMP | 7.51 €/ml | EUR_PER_ML | H/1000 × qty | B.profiles |
| TRANSOM | TRANSOM_TEMP | 7.50 €/ml | EUR_PER_ML | L/1000 × qty | B.profiles |

### Listini
| src_sys | src_coll | src_field | meaning | dest | transform | ver | req | motor | loss | conf |
|---|---|---|---|---|---|---|---|---|---|---|
| BOTH | item_pricelists | entries[].code (schema A) | codice stringa | DEPRECATED | migrazione a schema B | — | — | — | ⚠️ rischio se pricelist A ha code non mappato in B.profiles | MIGRAZIONE |
| B | item_pricelists | entries[].ref_type + ref_id | FK verso profiles | B.item_pricelists.entries[].ref_type+ref_id (unico schema) | copy | Y | Y | tech | none | OK |
| A | products.default_hardware_kit.price | prezzo inline | B.item_pricelists.entries[ref_type=hardware] | spostare in listino kind=cost | Y | N | tech | verificare che non serva più inline | OK |
| BOTH | item_pricelists | entries[].color_code (A) o color_id (B) | join colore | B.item_pricelists.entries[].color_id | code→id resolve via colors.code | Y | N | tech | 1 tenant ha color_code stringa libera | verifica |

### Vetri
| src_sys | src_coll | src_field | dest | note |
|---|---|---|---|---|
| B | glass_recipes | product_key + window_type + number_of_sashes + structured/custom | B.glass_recipes (rimane) | approvato PO. Aggiungere `formula_version` per versionamento |
| — | (nuovo) | glass_types | B.glass_types con DOUBLE_STANDARD/DOUBLE_SATIN/TRIPLE_STANDARD/TRIPLE_SATIN | prezzi in item_pricelists(kind=cost, ref_type=glass) |
| — | (nuovo) | glass_pricing_mode | FIXED_UNIT_PRICE / PERCENTAGE_SURCHARGE_ON_BASE_GLASS | TRIPLE_SATIN = base TRIPLE_STANDARD + 25% |
| A | production_config.default_glass_price_per_sqm | letto solo se glass_type non specificato | fallback tenant | Post BUG-03 → None → MISSING_GLASS_PRICE |

### Colori
| src_sys | src_coll | src_field | dest | note |
|---|---|---|---|---|
| B | colors | code, name | B.colors (mantenuto) | + `foil_category=STANDARD_FOIL` per i 6 colori pellicolati |
| B | color_categories | code, is_premium | B.color_categories | RIDEFINIZIONE: `is_premium` deprecato, sostituito da `surcharge_type=PERCENTAGE_ON_ELIGIBLE_PVC_COMPONENTS, surcharge_value=10` |
| — | (nuovo) | colors.foil_category | STANDARD/PREMIUM/CUSTOM_RAL | attende definizione categorie extra |
| — | (nuovo) | colors.applies_to_materials | [PVC_FOILED] | per limitare +10% ai soli PVC pellicolati |

### Ferramenta / accessori
| src_sys | src_coll | src_field | dest | note |
|---|---|---|---|---|
| A | products.default_hardware_kit | inline object | B.hardware_kits + item_pricelists(kind=cost, ref_type=hardware) | migrare, poi rimuovere inline |
| B | hardware_kits | code, name | B.hardware_kits (mantenuto) | prezzo va SEMPRE in item_pricelists |
| B | accessories | code, name | B.accessories (mantenuto) | idem |

### Configurazione produzione
| src_sys | src_coll | src_field | dest | note |
|---|---|---|---|---|
| A | production_config | hourly_cost | B.production_config.hourly_workshop_cost | **RENAME** hourly_cost → hourly_workshop_cost |
| A | production_config | fixed_/one_/two_/three_/four_sash_time_minutes | B.production_config.time_minutes_by_config | mappare a WINDOW_1_SASH=45', WINDOW_2_SASH=60', DOOR_WINDOW_1_SASH=60', DOOR_WINDOW_2_SASH=90', WINDOW_3_SASH=138', DOOR_WINDOW_3_SASH=180' (in minuti; PO ha dato ore) |
| A | production_config | default_glass_price_per_sqm | B.production_config idem (fallback) | resta None dopo BUG-03 |
| A | production_config | default_bar_length_pvc_mm | idem | consolidamento standard tenant |
| — | (nuovo) | threshold_variable_cost_per_ml | 29.50 | in ServicesConfig o production_config |
| — | (nuovo) | threshold_fixed_cost_1_sash / _2_sashes | 7.49 / 9.84 | idem |

### Moltiplicatore commerciale
| src_sys | src_coll | src_field | dest | note |
|---|---|---|---|---|
| A | production_config | default_margin_pct | A.commercial_rules.markup_percentage OPPURE A.commercial_rules.multiplier | **decidere pricing_method**: MULTIPLIER (×3) o MARKUP_ON_COST (%40 attuale). Excel usa MULTIPLIER=3 |
| — | (nuovo) | commercial_products.default_pricing_method | MULTIPLIER (per Enerhia baseline) | attende conferma tenant-per-tenant |

### Snapshot
| src_sys | src_field | dest | note |
|---|---|---|---|
| A | quote.lines[].pricing_snapshot (monolitico) | SPLIT in `technical_snapshot` + `commercial_snapshot` | migrazione Fase 2 |
| — | (nuovo) | technical_snapshot.calculation_hash | SHA256 deterministico | esclude timestamp variabili |
| — | (nuovo) | commercial_snapshot.calculation_hash | idem | |

### Lista taglio
| src_sys | src_coll | src_field | dest | note |
|---|---|---|---|---|
| B | cutting_lists | tutti | B.cutting_lists (mantenuto) | ora derivato dal BOM comune (non più isolato) |
| A | (nessuno) | — | contratto → BOM → cutting_list automatico | handoff produzione risolto |

## Rischi principali
1. **Codici A senza corrispondente B**: `products.components[].code="XYZ"` non presente in `B.profiles` → migrazione crea entry temp
2. **Doppi entries pricelist**: schema A `code` + schema B `ref_type+ref_id` sullo stesso codice → dedup con `code` come chiave
3. **Formule utente-defined**: `products.components[].formula_qty` incomplete rispetto alle formule Excel → gap identificati in analisi Formula V1_3
4. **`default_margin_pct=40` vs Excel ×3**: comportamento diverso — richiede scelta esplicita per ogni tenant durante migrazione

## Prossimi passi
- Cross-review indipendente su V1_3 + Mapping + Golden Tests
- Se approvato → Fase 1 V3 (implementazione modelli + resolver)
- Cleanup `production_config` duplicato **sospeso**
