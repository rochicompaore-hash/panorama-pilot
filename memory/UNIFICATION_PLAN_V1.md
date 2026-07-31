# Panorama Pilot — Piano di Unificazione Architetturale v1

**Contesto**: fix architetturale (opzione D2:b) — unificare "Engine Parametrico" (`parametric_*`) e "Motore Commerciale" (`item_pricelists`+`products`+`glass_recipes`+`production_config`) in una **fonte autorevole unica** che alimenta sia `commercial_perimeter` sia `technical_cut_list`.

**Stato**: DRAFT — nessun codice scritto. Attende approvazione Product Owner.

---

## 1 · Modello dati attuale (as-is)

### 1.1 Sistema A — "Engine Parametrico" (`parametric_*`)
| Collezione | Scopo | Campi chiave | Versionato |
|---|---|---|---|
| `parametric_profile_systems` | Sistema profilo (es. PVC70) | code, name, material, series, tech (frame_width_mm, sash_width_mm, central_node_mm, glass_deduction_mm, bar_length_mm, weld_allowance_mm, kerf_mm, min_reusable_scrap_mm, tolerances) | ✅ version, ps_status |
| `parametric_profiles` | Componente del sistema (telaio, anta, fermavetro, ecc.) | system_id, code, name, role, weight_per_m_kg, indicative_price_per_m, indicative_cost_per_m, is_cutting_relevant | ✅ status |
| `parametric_color_categories` | Categorie colore con policy scarto | code, scrap_mode, surcharge_pct, charges_whole_bar | ✅ |
| `parametric_colors` | Colori specifici | code, ral_code, category_id | ✅ |
| `parametric_glass_types` | Tipi vetro | code, thickness_mm, indicative_sqm_price | ✅ |
| `parametric_hardware_kits` | Kit ferramenta | code, kit_type, indicative_price | ✅ |
| `parametric_accessories` | Accessori | code, kind, unit_type, indicative_price | ✅ |
| `parametric_item_pricelists` | Listini vendita/costo | code, name, kind, currency, entries[] | ✅ valid_from, valid_to |
| `parametric_price_matrices` | Matrici L×H per pricing rapido | code, product_key, interpolation | ✅ |
| `parametric_bom_templates` | BOM parametriche tecniche | code, product_key, level, bom_status, rules[] | ✅ |
| `parametric_pricing_modes` | Modalità pricing A/B/C | scope, product_key, mode, b_markup_pct | ✅ |

**Forza**: modello completo, tecnico, versionato. **Debolezza**: mai collegato al preventivo reale — dati demo isolati.

### 1.2 Sistema B — "Motore Commerciale" (Fase 1)
| Collezione | Scopo | Campi chiave | Versionato |
|---|---|---|---|
| `products` | Prodotto commerciale (es. ProEvolution) | key, name, components[]={code, category, waste_percentage, applies_to}, default_hardware_kit | ❌ nessun versioning |
| `item_pricelists` | Listino componenti (usato dal motore) | name, active, entries[]={code, color_code, unit_price, unit} | ❌ solo active=true/false |
| `glass_recipes` | Formule vetro per prodotto+ante | product_key, frame_code, sash_code, window_type, number_of_sashes, formula_type, structured/custom | ✅ version |
| `production_config` | Config tenant (hourly_cost, tempi, margine) | tenant_id, hourly_cost, one_sash_time_minutes, default_margin_pct | ❌ singleton per tenant |
| `color_categories` | Colori (dup di parametric_color_categories!) | code, is_premium | ❌ |

**Forza**: collegato al motore, funzionante end-to-end (test hard verde). **Debolezza**: no versioning su products+item_pricelists, no matrici prezzi, no BOM.

### 1.3 Duplicazioni e overlap identificati
| Concetto | In Sistema A | In Sistema B | Fonte "vincente" |
|---|---|---|---|
| Sistema profilo | `parametric_profile_systems` | ❌ implicito in products.components | **A** (più ricco, versionato) |
| Componente profilo | `parametric_profiles` (con role, weight, cost) | `products.components[]` (solo code+category) | **A** ma manca color-price |
| Prezzo componente per colore | ❌ | `item_pricelists.entries[]` con color_code | **B** |
| Categorie colore | `parametric_color_categories` (con scrap policy) | `color_categories` (solo is_premium) | **A** |
| Colori specifici | `parametric_colors` | ❌ | **A** |
| Formule vetro | ❌ | `glass_recipes` | **B** |
| Kit ferramenta | `parametric_hardware_kits` (indicative_price) | products.default_hardware_kit (price) | **A** + B |
| Config produzione | ❌ | `production_config` | **B** |
| BOM tecnica | `parametric_bom_templates` | ❌ | **A** |
| Prodotto commerciale | ❌ | `products` | **B** |

**Solo in A**: profile_systems.tech, price_matrices, bom_templates, pricing_modes, valid_from/to per listini.  
**Solo in B**: products (prodotti commerciali), glass_recipes, production_config.

---

## 2 · Fonte autorevole scelta

**Nessuno dei due sistemi da solo è sufficiente**. La fonte autorevole sarà una **consolidazione ibrida** — non un semplice "vince A" o "vince B". Motivo: A ha la struttura tecnica corretta (versionamento, sistema profilo, matrici, BOM); B ha i concetti commerciali chiave (prodotti, formule vetro, config produzione). Adottare A come base + integrarla con le entità mancanti di B.

### 2.1 Modello unificato proposto (naming semplificato)
| Collezione unificata | Origine | Ruolo |
|---|---|---|
| `profile_systems` | ← `parametric_profile_systems` | Sistema profilo con tech dimensions, versionato |
| `profile_components` | ← `parametric_profiles` + arricchito con `color_price_map` | Componente (5103, 12130, ecc.) con prezzo €/ml per colore |
| `color_categories` | ← `parametric_color_categories` | Colori con scrap policy + is_premium (fuso da B) |
| `glass_types` | ← `parametric_glass_types` + campi da `glass_recipes` | Tipi vetro con formule collegate |
| `glass_recipes` | ← `glass_recipes` (B) | Formule per prodotto+ante — mantenuto |
| `hardware_kits` | ← `parametric_hardware_kits` | Kit ferramenta con prezzo per colore |
| `accessories` | ← `parametric_accessories` | Accessori |
| `products` | ← `products` (B) + collegato a profile_systems | Prodotto commerciale (ProEvolution, ecc.) con `system_id` che referenzia profile_systems |
| `production_config` | ← `production_config` (B) | Config produzione tenant — mantenuta |
| `price_matrices` | ← `parametric_price_matrices` | Rimane per pricing rapido opzionale |
| `bom_templates` | ← `parametric_bom_templates` | Per `technical_cut_list` |

**Regola d'oro**: nessun prezzo componente vive in due posti. Vive in `profile_components.color_price_map` come dict `{color_code → unit_price}` con validità.

### 2.2 Adapter: `PricingConfigurationResolver`
Un singolo servizio Python che, dato `(tenant_id, product_id, color_code, number_of_sashes, ecc.)`, legge dalla fonte autorevole e restituisce il **PricingContext normalizzato** che entrambi i motori (`commercial_perimeter` e `technical_cut_list`) consumano:

```
PricingContext {
  product: Product
  system: ProfileSystem (con tech)
  components: Dict[role, ProfileComponent]  # frame, sash, glazing_bead, ...
  component_prices: Dict[code_color, unit_price]  # da color_price_map
  color: ColorCategory (con is_premium, scrap_mode)
  glass_recipe: GlassRecipe
  hardware_kit: HardwareKit
  production_config: ProductionConfig
}
```

**Vantaggio**: i due motori restano stupidi; l'adapter fa solo lookup. Zero duplicazione runtime.

---

## 3 · Mapping campo-per-campo (dettaglio)

`parametric_profiles.indicative_price_per_m` (float) → `profile_components.default_price_per_m` (baseline se colore non ha prezzo esplicito)  
`item_pricelists.entries[].{code, color_code, unit_price}` → `profile_components.color_price_map[color_code].unit_price`  
`parametric_profile_systems.tech.*` → `profile_systems.tech.*` (unchanged)  
`products.components[].code` → **deve corrispondere** a `profile_components.code` con FK logica  
`glass_recipes.*` → invariato  
`production_config.*` → invariato  
`parametric_color_categories.surcharge_pct` + `color_categories.is_premium` → `color_categories` fuso (surcharge se premium)

**Naming migration**: rimuovere prefisso `parametric_` da tutte le collezioni. Es. `parametric_profile_systems` → `profile_systems`.

---

## 4 · Strategia di migrazione (append-only, no distruzione)

### Fasi
1. **T0 · Backup completo**: mongodump di tutte le collezioni `parametric_*` + `products` + `item_pricelists` + `glass_recipes` + `production_config`. Restore-ready.
2. **T1 · Rinomina collezioni**: renameCollection append `_v1_deprecated`. Non cancellare mai.
3. **T2 · Materializzare collezioni unificate**: script `migrate_unify_v1.py` che legge da `_v1_deprecated` e scrive in nuove collezioni pulite.
4. **T3 · Attivare adapter**: il `PricingConfigurationResolver` va live e legge dalle nuove collezioni.
5. **T4 · Dual-read grace period (14 giorni)**: se un dato manca nella nuova, fallback a `_v1_deprecated` con warning log. Aiuta a scoprire gap.
6. **T5 · Rimozione fallback**: quando log = 0 gap, si disattiva il dual-read.
7. **T6 · Drop `_v1_deprecated` collections** (solo dopo tua approvazione esplicita).

### Compatibilità dati esistenti
- **Preventivi già emessi**: hanno `pricing_snapshot` immutabile → **non toccati mai**. Continuano a rendere PDF e a essere leggibili.
- **Contratti firmati**: idem, immutabili.
- **Preventivi bozza in corso**: verranno ricalcolati alla prossima modifica. Se la ricalcolazione fallisce (`PRICING_INCOMPLETE`) l'utente vede errore parlante — mai crash.
- **`glass_recipes` esistenti**: preservate 1:1.
- **`production_config`**: preservata 1:1.

### Rollback plan
Se qualcosa va storto in T2-T4:
1. Disattivare adapter (feature flag)
2. Rinominare nuove collezioni → `_failed_migration`
3. Rinominare `_v1_deprecated` → nomi originali
4. Restart backend
5. Torniamo esattamente allo stato di prima. Nessun dato perso.

---

## 5 · Endpoint

### Mantenuti
- `POST /api/quote-structure/{qid}/openings/{oid}/products/compute-and-add` (Fase 1)
- `POST /api/quote-structure/products/{lid}/recompute`
- `GET /api/quote-structure/{qid}/legacy-status`
- `POST /api/catalog/products/{pid}/simulate`

### Nuovi (nella pagina unificata)
- `GET/POST/PATCH/DELETE /api/config/profile-systems` (+ `{id}/publish`, `{id}/duplicate`, `{id}/version`)
- `GET/POST/PATCH /api/config/profile-systems/{sid}/components`
- `GET/POST/PATCH /api/config/profile-components/{cid}/color-prices`
- `GET/POST/PATCH /api/config/glass-recipes`
- `POST /api/config/glass-recipes/{rid}/simulate` (con L, H, ante)
- `GET/PATCH /api/config/production-config`
- `POST /api/config/profile-systems/{sid}/preview-quote` (simulazione L×H nella pagina)
- `GET /api/config/legacy-mapping` (report gap dati durante grace period)

### Deprecati (mantenuti per compatibilità 90 giorni)
- Tutti `/api/parametric/*` → risposta 200 ma con header `X-Deprecated: use /api/config/*`
- `/api/parametric/admin` frontend page → banner deprecato + link alla nuova pagina

---

## 6 · Pagine

| Pagina attuale | Destino |
|---|---|
| `/parametric/admin` | **Riscritta completamente** come Sistema unificato (mantiene la route per compatibilità link esistenti) |
| `/parametric` (configurator) | Marcata legacy, rimane leggibile |
| `/pricelists`, `/pricelist-importer`, `/pricing-hub` | Rimangono admin, ma marcate come "listino diretto — usa Sistemi & Formule per catalogo strutturato" |
| `/product-catalog` | Fuso in nuova pagina come tab "Prodotti associati" |
| `/settings/glass`, `/settings/hardware`, `/settings/formulas` | Fusi come tab della nuova pagina |

### Wireframe pagina unificata (URL: `/parametric/admin`)
```
┌────────────────────────────────────────────────────────────────────┐
│ Sistemi e formule profili                    [+ Nuovo sistema]     │
├────────────────────────────────────────────────────────────────────┤
│ Sidebar sistemi:              Contenuto tab attiva:                │
│  ○ PVC70 (v3, attivo)         ┌──────────────────────────────────┐│
│  ○ PVC80 (v1, bozza)          │ Tabs:                            ││
│  ○ ALU-Slim (archiviato)      │ [1.Dati sistema] [2.Prodotti]    ││
│                               │ [3.Componenti] [4.Prezzi&colori] ││
│  [+ nuovo]                    │ [5.Vetri&formule] [6.Produzione] ││
│                               │ [7.Simulazione] [8.Versioni]     ││
│                               │──────────────────────────────────││
│                               │ (contenuto tab...)                ││
│                               └──────────────────────────────────┘│
└────────────────────────────────────────────────────────────────────┘
```

Tab 7 · Simulazione: L=900, H=1500, ante=1, colore=BIANCO → invoca `preview-quote` → mostra breakdown vetro completo (larghezza × altezza × superficie reale × superficie fatturabile × formula) e prezzo finale.

---

## 7 · Test di accettazione

Il fix è concluso solo quando:
1. Creo componente "5103" con prezzo BIANCO=8.50 dalla pagina unificata
2. `commercial_perimeter` recupera 8.50 automaticamente (verificato con compute-and-add reale)
3. `technical_cut_list` (dry-run) recupera lo stesso codice 5103 con stessa lunghezza barra
4. Modifico prezzo → viene creata nuova versione automaticamente
5. Preventivo già emesso NON cambia (verificato con hash snapshot invariato)
6. Nessun dato reinserito in due posti (verificato con grep pre/post)
7. `is_demo=true` filtrato in ambiente operativo (`DEMO_MODE=false`)

Test automatici hard non-skippable (7 test).

---

## 8 · Tempi realistici

| Fase | Effort | Note |
|---|---|---|
| Backup + modello dati unified backend (models, schemas) | 4h | |
| Migration script + dry-run + validation | 5h | |
| Adapter `PricingConfigurationResolver` + refactor motori per usarlo | 6h | rischio medio |
| Endpoint CRUD nuovi `/api/config/*` | 5h | |
| Pagina unificata frontend con 8 tab | 8h | grande |
| Test automatici hard | 3h | |
| Test regressione + testing agent | 3h | |
| **Totale** | **34h** | 4–5 giorni di lavoro concentrato |

Fase 2A resta sospesa per tutto questo tempo.

---

## 9 · Rischi

| Rischio | Impatto | Mitigazione |
|---|---|---|
| Dati "orfani" nelle vecchie collezioni non migrati | ALTO | Dual-read grace 14gg + log gap |
| Preventivi bozza rotti dopo migrazione | ALTO | Snapshot immutabili + banner "ricalcola" |
| Adapter più lento del lookup diretto | MEDIO | Cache in-memory su tenant + invalidation su modifica listino |
| Nomi collezione hardcoded in altri servizi | MEDIO | Grep completo prima di rinominare |
| Team confuso da nuovi endpoint | BASSO | Doc changelog + header X-Deprecated |
| Il seed demo TEST-MOTORE deve continuare a funzionare | BASSO | Migrare anche lui, mantenendo is_demo=true |

---

## 10 · Piano di rollback

**Feature flag** `UNIFIED_MODEL_ACTIVE` in env.
- Se `false` (default fino a T3): adapter legge da vecchie collezioni, motore invariato
- A T3 attiviamo `true` in preview, testiamo 48h
- Se problemi: `UNIFIED_MODEL_ACTIVE=false` + rinomina collezioni (script `rollback_unify.sh` pronto)
- In produzione: attivazione solo dopo 14gg preview senza errori

---

## 11 · Prima domanda onesta prima di iniziare

Ti chiedo di riflettere onestamente:

1. **34h di lavoro** su un progetto già in ritardo per il preventivatore. Vale la pena bloccare Fase 2A per 4-5 giorni per il fix architetturale?
2. La maggior parte dei prodotti reali che venderai userà **1 sistema profilo (ProEvolution)**. La complessità di `parametric_bom_templates`, `parametric_price_matrices`, `parametric_pricing_modes` (mode A/B/C) è utile per **te subito** o è over-engineering ereditato da un iterazione precedente?
3. Se rispondessi *"no, la maggior parte dei prodotti sono ProEvolution semplice"* — allora potremmo **buttare via** metà delle collezioni `parametric_*` (matrici prezzi, BOM templates, pricing modes) invece che migrarle. Migrazione più veloce (~18h invece di 34h).

Rispondi prima di autorizzare:
- **A) Confermo b) fix architetturale completo — 34h, migro tutto**
- **B) Fix architetturale ridotto — 18h, migro solo l'essenziale (systems, components, colors, prices, glass, production). Butto price_matrices+bom_templates+pricing_modes come "non usati oggi"**
- **C) Torna sull'opzione c ibrida (10-14h) sapendo che è una vista/adapter e non una vera migrazione**

**Non partirò prima di questa scelta.**
