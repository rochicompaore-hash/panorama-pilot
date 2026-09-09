# MILESTONE A — Configurazione tecnica amministrabile

**Data:** 2026-08-13 · **Branch:** `feature/unified-pricing-phase1` · **Commit:** `<al termine>`  
**Autorizzato:** Messaggio 162

---

## 0. Anomalie risolte (documentali, come richiesto)

### A1 — n_comps=5 vs "7 ruoli BOM"
**Nessuna divergenza test↔codice↔deploy.** Scelta strutturale:
- `technical_snapshot.components[]` contiene i **5 componenti profilo** (FRAME, FRAME_REINFORCEMENT, SASH, SASH_REINFORCEMENT, GLAZING_BEAD) — tutti a **€/ml** con formula perimetrale
- **GLASS** è aggregato **fuori** da `components[]` come `technical_snapshot.glass_cost` (€/m² × area billable, formula strutturata `L-206 × H-206`)
- **HARDWARE** è aggregato come `technical_snapshot.hardware_cost` (€/pz fisso finestra)
- Totale ruoli tecnici rappresentati: **7** (5 in array + 2 aggregati) → documentazione corretta

### A2 — GLAZING_BEAD = 0 €/ml
**Fonte prevista:** `item_pricelists.entries[]` con `code="GLAZING_BEAD_PROEVOLUTION"`. Il resolver v3 (`TechnicalCostResolver._load_component_price`) legge prima il listino attivo del tenant, poi cade sul fallback `V1_3_COMPONENT_PRICES` che è impostato a 0.00 (placeholder documentato).  
**Prima di Milestone A** l'unico modo per valorizzarlo era editare direttamente MongoDB.  
**Dopo Milestone A** l'admin lo aggiunge da UI → tab "Prezzi componenti" → codice `GLAZING_BEAD_PROEVOLUTION`, prezzo €/ml.

**Verificato in questa iter:** PUT `/api/tech-config/component-prices/GLAZING_BEAD_PROEVOLUTION` = 2.10 €/ml → nuovo `/api/pricing/compute` mostra `unit_cost=2.1, total_cost=8.35€`, sale_price = **985.30€** (vs 960.25€ pre-fix).

Il golden test GT-01 va aggiornato quando Enerhia fornirà il prezzo reale del fermavetro ProEvolution.

---

## 1. Cosa è stato implementato

### Backend (`app/routers/tech_config.py`, 175 righe, NUOVO)
Endpoint amministrativi protetti da `pricing_admin.manage`:

| Metodo | Endpoint | Scopo |
|---|---|---|
| GET | `/api/tech-config/workshop-cost` | Legge `hourly_workshop_cost` + versione |
| PUT | `/api/tech-config/workshop-cost` | Aggiorna il costo officina (bump `version`) |
| GET | `/api/tech-config/commercial-rule` | Legge regola commerciale + versione |
| PUT | `/api/tech-config/commercial-rule` | Aggiorna metodo + parametri (MULTIPLIER / MARKUP_ON_COST / TARGET_GROSS_MARGIN / FIXED_PRICE) |
| GET | `/api/tech-config/component-prices` | Lista entries listino v3 |
| PUT | `/api/tech-config/component-prices/{code}` | Insert/update entry per componente (`unit`, `color_code`, `description`) |
| GET | `/api/tech-config/technical-recipes` | Lista ricette (read-only in Milestone A) |

**Nessuna nuova collection.** Scrive nelle tre collezioni già create in Milestone 1:  
- `workshop_cost_configs`
- `commercial_pricing_rules`
- `item_pricelists` (schema v3)

### Frontend (`src/pages/TechConfigPage.jsx`, 195 righe, NUOVO)
Pagina unica "Configurazione tecnica" con **4 tab**:
1. **Costo officina** — input singolo, mostra versione corrente
2. **Regola commerciale** — dropdown metodo + campi condizionali (multiplier / markup_pct / gross_margin_pct / fixed_price)
3. **Prezzi componenti** — form add/update + tabella entries
4. **Ricette tecniche** — read-only (edit rinviato)

### Wiring
- `server.py`: import + include `tech_config_router` in `QUOTING_ROUTERS`
- `App.js`: route `/tech-config` con `TechConfigPage`
- `AppLayout.jsx`: nuova voce sidebar "Configurazione tecnica (nuovo motore)" sotto gruppo "Configurazione tecnica", visibile con permesso `pricing_admin.manage`

---

## 2. Test end-to-end eseguito (evidenza)

**Scenario:** modifica costo → nuovo /api/pricing/compute usa nuovo costo → hash cambia → preventivo storico invariato.

```
1) GET workshop-cost → 180 €/h v1
2) POST /pricing/compute → labor=135, total=320.08, sale=960.25, hash=55ec99b8...
3) PUT workshop-cost = 200 €/h → v2
4) POST /pricing/compute → labor=150, total=335.08, sale=1005.25, hash=88b0045c... (CAMBIATO)
5) PUT workshop-cost = 180 €/h → v3 (ripristino)

Prezzo GLAZING_BEAD:
A) Prima: unit=0.00 total=0.00
B) PUT /component-prices/GLAZING_BEAD_PROEVOLUTION = 2.10 €/ml
C) POST /pricing/compute → GLAZING_BEAD unit=2.1 total=8.35, sale=985.30€
```

**Preventivi storici NON ricalcolati:** il resolver v3 legge `workshop_cost_configs` solo al tempo del compute; i preventivi salvati contengono già `pricing_snapshot` congelato. Test manuale su preventivo esistente ha confermato: `base_price` e `pricing_snapshot_hash` invariati.

### Milestone 1 regression
- `test_gt01_deterministic_hash` ✅
- `test_multiplier_override` ✅
- `test_fail_closed_missing_technical_recipe` ✅

---

## 3. Come collaudarlo

```
1. Login: https://serramento-ops.preview.emergentagent.com
   admin@infissiexpress.com / <ROTATED_OLD_PASSWORD>
2. Menu → Configurazione tecnica → Configurazione tecnica (nuovo motore)
3. Tab "Costo officina": cambia 180 → 200 → Salva
4. Chiama /api/pricing/compute → labor_cost = 150 (era 135)
5. Ripristina a 180
6. Tab "Prezzi componenti": aggiungi GLAZING_BEAD_PROEVOLUTION 2.10 €/ml
7. Chiama /api/pricing/compute → GLAZING_BEAD ora ha costo > 0
```

---

## 4. Cosa NON è stato fatto (backlog Milestone A+)

- ❌ Edit ricette tecniche (`technical_recipes`) — solo lettura
- ❌ Gestione sistemi profilo — richiede modello dati esteso
- ❌ Gestione vetri — attualmente prezzi in `GLASS_PRICES_PER_SQM` (codice) → serve migrazione a collection `glass_price_configs`
- ❌ Gestione ferramenta — prezzi in `V1_3_COMPONENT_PRICES` (codice)
- ❌ Gestione tempi produzione — `PRODUCTION_TIME_HOURS` in codice
- ❌ Validità/data-attiva del costo (versione ma non data range)

Sufficiente per il MOP: **hourly_workshop_cost**, **moltiplicatore**, **prezzi componenti listino** modificabili da UI.

---

## 5. Regole rispettate

- ✅ Nessuna nuova collection parallela
- ✅ Zero modifiche al motore legacy `commercial_perimeter`
- ✅ Preventivi storici invariati (snapshot congelato preservato)
- ✅ Versione incrementata ad ogni PUT (audit di base)
- ✅ Permesso `pricing_admin.manage` richiesto
- ✅ Pubblicazione solo in preview

---

## 6. STOP

Attendo collaudo manuale. Milestone B non avviata.

### Prossimi passi post-collaudo
- **Milestone B**: WINDOW_2_SASH + DOOR_WINDOW_1_SASH + DOOR_WINDOW_2_SASH con MEETING_STILE, THRESHOLD, FIXED_MULLION, TRANSOM, STANDARD_FOIL — formule V1_3 approvate + golden test numerici
- **Milestone C**: wiring UI simulator/catalogo/preventivo al nuovo endpoint
- **Milestone D**: Preventivo → PDF → Contratto → Rilievo (senza reinserimento)
- **Milestone E**: Rilievo → ProductionOrder → BOM → Cut List
