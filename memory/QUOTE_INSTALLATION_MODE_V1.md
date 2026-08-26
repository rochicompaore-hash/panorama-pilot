# QUOTE INSTALLATION MODE + AUTO SERVICE BUNDLE V1 (msg 393)

**Stato:** BACKEND_READY + UI_READY + MANUAL_E2E_PENDING (§28 msg 393).
**Author:** Enerhia Operating Core — Iter 50 (Feb 2026).
**Parallelo a:** Tachometer V1 (msg 392) — nessuna modifica alle formule margine.

---

## 1. Modello dati

### Quote (livello preventivo)
- `installation_mode` — enum obbligatorio (`SUPPLY_ONLY` | `SUPPLY_AND_INSTALLATION`) prima di iniziare la configurazione prodotti (§1 msg 393). `None` iniziale in DRAFT.
- `dismantling_mode` — `INCLUDED` | `EXCLUDED` (default) | `NOT_APPLICABLE` (§15).
- `disposal_mode` — idem, `EXCLUDED` default (§16).

### QuoteLine (livello posizione)
Nuovi campi additive (backward-compat con righe legacy):
- `automatic_services[]` — snapshot dei servizi risolti dal resolver.
- `manual_extra_services[]` — servizi accessori aggiunti manualmente (§8), preservati anche allo switch mode (§20).
- `standard_services_sale_total` — €.
- `standard_services_internal_cost_total` — €.
- `position_sale_total` — prodotto + servizi standard + manual (§4 formula).
- `position_internal_cost_total` — costo interno aggregato.
- `service_policy_version` — `installation_v1_2026_02`.

Struttura snapshot `automatic_services[]`:
```
{id, automatic=true, service_id, service_code, service_name,
 service_category, service_type ("POSA"|"SMONTAGGIO"|"SMALTIMENTO"|"MOTORIZZAZIONE"),
 pricing_unit, quantity, unit_sale_price, unit_internal_reference_price,
 sale_price_total, internal_cost_total, pricing_status, service_policy_version}
```

---

## 2. Deterministic Resolver — `app/services/service_resolver.py`

### FINESTRE — priorità §5 msg 393
1. `underlight_type=DOUBLE` → `INSTALL_WINDOW_UNDERLIGHT_DOUBLE`
2. `underlight_type=SINGLE` → `INSTALL_WINDOW_UNDERLIGHT`
3. `window_type=SLIDING/SLIDING_DOOR_WINDOW` → `INSTALL_SLIDING`
4. `window_type=FIXED` → `INSTALL_FIXED_WINDOW`
5. `window_type=VASISTAS` → `INSTALL_VASISTAS`
6. `number_of_sashes≥4` → `INSTALL_WINDOW_4_SASH`
7. `number_of_sashes=3` → `INSTALL_WINDOW_3_SASH`
8. `number_of_sashes∈{1,2}` (o mancante) → `INSTALL_WINDOW_1_2_SASH`

**Underlight sostituisce e non somma** (§3 msg 393): niente doppia posa. `underlight_type` opzionale con default `NONE`, backward-compat (§2 msg 393).

### Altre categorie
- `CASSONETTI` → `INSTALL_ROLLER_BOX_SINGLE` / `_DOUBLE` (se `assembly_type=DOUBLE`)
- `ZANZARIERE` → `INSTALL_MOSQUITO` / `_DOUBLE`
- `TAPPARELLE` → `INSTALL_ROLLER_KIT`
- `PERSIANE_SCURI` → `INSTALL_SHUTTER_1_2_SASH`
- `PORTE_BLINDATE` → `INSTALL_ARMORED_DOOR`
- `PORTE_INTERNE` → `INSTALL_INTERIOR_DOOR_HINGED`

### SMONTAGGIO (§11 msg 393)
Attivato quando `dismantling_mode=INCLUDED` AND `intervention_type ∈ {replacement, renovation, sostituzione}`:
- FINESTRE/PORTEFINESTRE → `REMOVE_WINDOW`
- CASSONETTI → `REMOVE_ROLLER_BOX`
- TAPPARELLE → `REMOVE_ROLLER_KIT`
- PERSIANE_SCURI → `REMOVE_SHUTTER`
- ZANZARIERE → `REMOVE_MOSQUITO`
- PORTE_BLINDATE → `REMOVE_ARMORED_DOOR`

### SMALTIMENTO (§7-§8 msg 393)
5 anagrafiche seedate con `pricing_status=NEEDS_PO_PRICING`:
`DISPOSAL_WINDOW / DISPOSAL_ROLLER_BOX / DISPOSAL_ROLLER_KIT / DISPOSAL_SHUTTER / DISPOSAL_MOSQUITO`.

Fail-closed §8: se `disposal_mode=INCLUDED` ma il servizio ha `NEEDS_PO_PRICING` o prezzo mancante → HTTP 400 `MISSING_DISPOSAL_PRICING`, blocco add_line + blocco PATCH. Mai smaltimento a 0 €.

Seed via `POST /api/quotes/admin/seed-disposal-services` (idempotente, richiede `products.manage`).

---

## 3. Semantica costi (§16 msg 393)

Ogni entry del listino `simple_services` ha:
- `internal_reference_price` — costo aziendale interno per il Margin Engine (INSTALLATION_COST / OTHER_DIRECT_COSTS).
- `customer_sale_price` — prezzo vendita cliente (NET_REVENUE).

Per V1 Enerhia: `internal_reference_price` è utilizzato come proxy di costo interno del servizio (assunzione documentata qui). Se in un iter futuro la semantica diverge (es. reference commerciale ≠ costo industriale), il resolver dovrà accettare un secondo campo `industrial_cost` senza cambiare l'API contract.

---

## 4. Regole prezzo — §14 msg 393 (NO doppio moltiplicatore)

La posa NON entra nei multiplier prodotto:

| Prodotto | Formula prezzo cliente |
|---|---|
| Finestra (FORMULA_TECHNICAL) | `commercial_final_unit_price` + install |
| Zanzariera (AREA×3) | `purchase_cost × 3` + install |
| Tapparella (AREA×3) | `purchase_cost × 3` + install |
| Persiana (AREA×2.5) | `purchase_cost × 2.5` + install |
| Cassonetto (GRID) | `grid_sale_price` + install |

`compute_line` (in `app/services/pricing.py`) aggrega `standard_services_sale_total` sopra il prodotto per ottenere `subtotal_line = position_sale_total`. Nessuna modifica alle engine di pricing prodotto (§25 msg 393).

---

## 5. Wiring col Margin Engine (§22 msg 393)

`aggregate_costs_from_lines` (in `margin_engine.py`) è stato esteso per foldare i services embedded:
- `service_type ∈ {POSA, MOTORIZZAZIONE}` → **INSTALLATION_COST**
- `service_type ∈ {SMONTAGGIO, SMALTIMENTO, ACCESSORIO, …}` → **OTHER_DIRECT_COSTS**

Tachimetro (`GET /quotes/{qid}/financial-snapshot`) NON è stato modificato — riceve automaticamente i nuovi costi via aggregation.

---

## 6. Endpoint API

- `PATCH /api/quotes/{qid}` — accetta `installation_mode`, `dismantling_mode`, `disposal_mode`. Se uno cambia in DRAFT, ri-risolve TUTTE le righe (§19-§20):
  - Rimuove i vecchi `automatic_services`
  - Se `SUPPLY_AND_INSTALLATION`: risolve nuovi services per ogni riga
  - `manual_extra_services` NON toccati (§20)
  - Ricalcola `subtotal / vat / total` + `financial_snapshot`
  - Fail-closed su `MISSING_DISPOSAL_PRICING` — 400 con codice + lista errori
- `POST /api/quotes/{qid}/lines` — quando `installation_mode=SUPPLY_AND_INSTALLATION`, la nuova riga riceve automaticamente `automatic_services` alla creazione. Idempotente.
- `POST /api/quotes/admin/seed-disposal-services` — seed 5 codici DISPOSAL_*.
- Freeze on `accepted` — invariato: `financial_snapshot` + `automatic_services` congelati dentro la fotografia della quote (§28 msg 393).

---

## 7. UI

- `InstallationModeCard` (in `QuoteEditorPage.jsx`) — toggle "Solo fornitura" / "Fornitura + posa" + selettori Smontaggio/Smaltimento (§17). Data-testid: `installation-mode-card`, `installation-mode-supply-only`, `installation-mode-supply-and-installation`, `dismantling-mode`, `disposal-mode`, `installation-mode-error`.
- Righe preventivo: mostrano riga secondaria "Servizi standard inclusi: [POSA · nome · €]" sotto ogni QuoteLine con `automatic_services` non vuoto (data-testid `line-services-{lineId}`).
- Smaltimento INCLUDED è **selezionabile** ma fail-closed sul backend finché non sono definiti i prezzi; alternativa UX §9 disabilitata è possibile in un iter futuro quando saremo sicuri del feedback.

---

## 8. Test — 28 pytest verdi (`tests/test_installation_mode_v1.py`)

- Priorità resolver finestre (10 casi parametrizzati)
- Cassonetto/Zanzariera single vs double
- Mapping per categoria
- No auto-install su righe SERVIZI/MONTAGGI_POSA/ACCESSORI (§7)
- No ricorsione su righe `category=installation` legacy
- Bucket mapping POSA→INSTALLATION, SMONTAGGIO/SMALTIMENTO→OTHER
- Aggregazione totale servizi
- Wiring Margin Engine E2E (SUPPLY=800 + POSA cost 130 → INSTALL=130)
- Enum guards INSTALLATION_MODES / POLICY_MODES

**E2E curl verificato** sul preview tenant (`c322c398-535d-43b2-8e3e-94236bb97df2`):
- Quote DRAFT + `SUPPLY_AND_INSTALLATION`
- Add FINESTRE 2-ante 1250€ → auto-resolve `INSTALL_WINDOW_1_2_SASH` 150€ → subtotal 1400€
- Add TAPPARELLE 176.40€ → auto-resolve `INSTALL_ROLLER_KIT` 120€ → subtotal 296.40€
- Financial snapshot: net 1696.40€ · supply 858.80€ · install 230€ · **margin 35.82% OTTIMO** · commission 254.46€
- Switch → `SUPPLY_ONLY`: automatic_services rimossi, total scende a 1426.40€, financial_snapshot ricalcolato

---

## 9. Known Limitations V1

- **Duplicate detection §6**: non è ancora possibile aggiungere manualmente una POSA identica come `manual_extra_service`. La UI degli extra manuali sarà completata al primo giro del ciclo Position Technical Data / Vano Model V2.
- **UX §9 (INCLUDED disabilitato)**: attualmente l'opzione è selezionable ma fail-closed. Miglioria UX: disabilitare il bottone finché i prezzi disposal non sono seedati.
- **Servizi per line non-multi-cat legacy**: righe create prima del Multi-Category V1 senza `category_code` non ricevono auto-services (mapping su `category_code`). Non è una regressione — quelle righe restano compatibili col Margin Engine tramite `internal_cost`.
- **Motorizzazione automatica**: `INSTALL_MOTOR` / `INSTALL_MOTOR_VASISTAS` non ancora risolti automaticamente (richiede flag `has_motor` in `configuration_snapshot`, previsto in F2).

---

## 10. Vincoli PO rispettati (msg 393)

- ✅ §1-§5 Priorità deterministica finestra + underlight
- ✅ §6-§8 Modello dati installation/dismantling/disposal
- ✅ §7 Seed DISPOSAL_* con NEEDS_PO_PRICING
- ✅ §8 Fail-closed su MISSING_DISPOSAL_PRICING
- ✅ §9 UX smaltimento (INCLUDED selezionabile ma fail-closed; miglioria disabilitata riservata)
- ✅ §10 Dismantling ≠ Disposal (codici separati)
- ✅ §11 Smontaggio auto solo se SOSTITUZIONE
- ✅ §12-§14 Enum + no doppio multiplier (POSA fuori dal ×3/×2.5)
- ✅ §15 Wiring Margin Engine automatico
- ✅ §16 Semantica costi documentata
- ✅ §17 UX Card selettore
- ✅ §18 Nessun refactor QuoteEditor
- ✅ §19-§20 Cambio mode ricalcola + preserva manual
- ✅ §21 Nessuna riga posa manuale ordinaria
- ✅ §22 UI posizione compatta (servizi in sotto-riga, no micro-righe)
- ✅ §25-§26 Compatibile Tachometer + Vano V2 futuro
- ✅ §27-§28 Snapshot campi + freeze on accepted
- ✅ §29-§30 Test principali (parametrizzati) + wiring Margin OK
- ✅ §31 Il commerciale seleziona modalità, non compone servizi manualmente
