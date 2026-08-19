# GEOMETRIC → COMMERCIAL PRICING ARCHITECTURE — Enerhia Operating Core V1

**Data:** 2026-02-19 · **Branch:** `feature/enerhia-operating-core-v1`
**Stato:** Architettura definitiva approvata (Master Plan §37).
**Preview:** https://serramento-ops.preview.emergentagent.com

---

## 0. Principio fondante (vincolante)

Il preventivo Enerhia **non nasce da un prezzo al m²**. Non nasce da un prezzo scritto dal commerciale. Non nasce da un secondo simulatore. Nasce da:

```
CONFIGURAZIONE GEOMETRICA (UI/tecnica)
        │
        ▼
UN SOLO MOTORE (pricing_v3)
   ProfileSystemResolver
        →  BomResolver
        →  TechnicalCostResolver
        │
        ▼
PRODUCTION_COST (costo interno reale)
        │  × multiplier (default Enerhia = 3.00, configurable)
        ▼
BASE_PRODUCT_SALE_PRICE
        │  + CommercialPackage
        │  + Installation (customer_sale_price da simple_services)
        │  + Extra services
        │  − Authorized discount
        ▼
PREZZO CLIENTE (net_quote_amount, pre-IVA)
```

Il **Configuratore Geometrico** è la **vista UI del pricing_v3**, non un motore separato.

---

## 1. Situazione attuale — due motori attivi (DA DECOMMISSIONARE M5)

Al 2026-02-19, esistono **due percorsi** che calcolano production/quote pricing:

| Motore | Endpoint | Stato | Uso attuale |
|---|---|---|---|
| **pricing_v3** (autoritativo) | `POST /api/pricing/compute` | ✅ Attivo, single-source | Golden tests M3/M4, tech-config admin, nessun caller commerciale |
| **commercial_perimeter** (legacy) | `POST /api/quote-structure/quotes/{id}/lines` + `perimeter_assembler.run_perimeter_simulation` | ⚠️ Attivo, ancora usato | Preventivi storici, catalog product simulator, pricing_hub `/simulate` |

**Consumatori del motore legacy da rifattorizzare in M5:**
- `/app/backend/app/routers/quote_structure.py` (linee 46, 340, 382, 413, 425, 476, 485, 514, 543) — motore integrato preventivo
- `/app/backend/app/routers/catalog.py` (linee 298, 321, 322) — product simulator
- `/app/backend/app/routers/pricing_hub.py` (righe 142, 419) — `/simulate` e `/bom-simulate`

**⚠️ Master Plan §37: NON collegare il preventivatore commerciale a pricing_v3 finché il commercial_perimeter non è dichiarato deprecato per il nuovo flusso.**

---

## 2. Il flusso definitivo (target M5)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    UI COMMERCIALE (semplice)                        │
│                                                                     │
│  Cliente → Cantiere → Nuovo preventivo → Ambiente → Posizione      │
│                              │                                       │
│                     Prodotto (ProEvolution)                          │
│                              │                                       │
│                 Configura: 1 sash / 1200×1400 / white / vetro       │
│                              │                                       │
│                          [ Calcola ]                                 │
└──────────────────────────────┼──────────────────────────────────────┘
                               │
                               ▼ POST /api/pricing/compute
┌─────────────────────────────────────────────────────────────────────┐
│                    MOTORE UNICO (pricing_v3)                         │
│                                                                     │
│   ProfileSystemResolver → BomResolver → TechnicalCostResolver       │
│                                                                     │
│   Output: {                                                          │
│     technical_snapshot: {                                            │
│       components[], glass, hardware, labor, foil,                   │
│       total_internal_cost: PRODUCTION_COST                          │
│     },                                                               │
│     commercial_snapshot: {                                           │
│       multiplier: 3.00,                                              │
│       unit_sale_price: base_product_sale_price                      │
│     },                                                               │
│     calculation_hash                                                 │
│   }                                                                  │
└──────────────────────────────┼──────────────────────────────────────┘
                               │
                               ▼ CommercialPricingService (livello 2)
┌─────────────────────────────────────────────────────────────────────┐
│                COMMERCIAL LAYER (nuovo, M5)                          │
│                                                                     │
│   CommercialPackage → included services / warranties / policies      │
│   + Installation (simple_services.customer_sale_price)               │
│   + Extra services                                                   │
│   − Authorized discount (DiscountGuard)                              │
│                                                                     │
│   QuoteLine (persisted con snapshot congelati):                     │
│     technical_snapshot (frozen)                                      │
│     commercial_snapshot (frozen)                                     │
│     calculation_hash                                                 │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Cosa esiste già e cosa manca

### 3.1 Livello tecnico (production_cost) — ✅ pronto
- `pricing_v3.ProfileSystemResolver` — legge `technical_recipes` per tenant
- `pricing_v3.BomResolver` — 5 ricette V1_3 (WINDOW_1/2, DOOR_WINDOW_1/2, VASISTAS_ONLY) + MEETING_STILE, THRESHOLD, FIXED_MULLION, TRANSOM
- `pricing_v3.TechnicalCostResolver` — legge da:
  - `hardware_rules` (60/80/75/90/380·n/40) ✅
  - `glass_price_configs` (76/96/125/156.25 · min 0.50 m²) ✅
  - `production_time_configs` (0.75/1.00/1.50/2.30/3.00 h) ✅
  - `workshop_cost_configs` (180 €/h) ✅
  - `item_pricelists` (profili — fallback V1_3 documentato) ⚠️ delta 28.34 €
- Foil surcharge +10% su PVC eleggibile ✅
- Fail-closed su tutti i MISSING_* ✅

### 3.2 Livello commerciale (base_product_sale_price) — ✅ pronto
- `pricing_v3.CommercialPricingService` — legge `commercial_pricing_rules`
- Default Enerhia: `method=MULTIPLIER · multiplier=3.00` (verificato oggi)
- Metodi supportati: MULTIPLIER, MARKUP_ON_COST, TARGET_GROSS_MARGIN, FIXED_PRICE
- Configurabile via UI: `/tech-config` → Regola commerciale

### 3.3 CommercialPackage — ❌ da creare (M5)

Struttura richiesta:
```python
class CommercialPackage:
    id: str
    tenant_id: str
    name: str                          # es. "Enerhia Standard"
    description: str
    status: str                        # ACTIVE / DRAFT / ARCHIVED
    valid_from: datetime | None
    valid_to: datetime | None
    included_services: List[str]       # simple_services.id[] (posa, smontaggi)
    included_warranties: List[str]     # warranty.id[]
    installation_policy: str           # INCLUDED / EXCLUDED / OPTIONAL
    survey_policy: str                 # INCLUDED / EXCLUDED
    discount_policy: str | None
    compatible_categories: List[str]   # ["FINESTRE", "PORTE"]
    display_order: int
```

Il **pacchetto NON modifica production_cost né base_product_sale_price**. Aggiunge/rimuove servizi (§19 Master Plan).

### 3.4 Installation & Services (customer_sale_price) — ✅ pronto
- Collection `simple_services` (34 servizi seedati)
- Endpoint `/api/simple-services` con dual pricing
- `POST /api/simple-services/discount-guard` per validazione sconti
- **Regola posa** (§21 Master Plan):

| Configurazione tecnica | Servizio posa suggerito |
|---|---|
| WINDOW_1_SASH / WINDOW_2_SASH | `INSTALL_WINDOW_1_2_SASH` (150 €) |
| WINDOW_3_SASH | `INSTALL_WINDOW_3_SASH` (215 €) |
| WINDOW_4_SASH | `INSTALL_WINDOW_4_SASH` (280 €) |
| DOOR_WINDOW_1_SASH / DOOR_WINDOW_2_SASH | `INSTALL_WINDOW_1_2_SASH` (150 €) *(coerente con listino)* |
| VASISTAS_ONLY | `INSTALL_VASISTAS` (250 €) |
| SLIDING_DOOR_WINDOW | `INSTALL_SLIDING` (650 €) |
| Porta blindata | `INSTALL_ARMORED_DOOR` (450 €) |
| Cassonetto singolo | `INSTALL_ROLLER_BOX_SINGLE` (90 €) |

Il campo `suggested_for_recipes` nel simple_service permette il matching automatico. Il commerciale può selezionare/deselezionare.

### 3.5 Discount system — ✅ base pronta

Modello dati per DiscountGuard (già implementato per servizi):
```json
{
  "list_price": 150.00,                    // customer_sale_price
  "discount": 15.00,
  "net_sale_price": 135.00,
  "internal_reference_price": 130.00,      // solo pricing_admin
  "remaining_discount_room": 5.00,         // solo pricing_admin
  "override_required": false               // true se net < internal_reference
}
```

Per il **serramento**: `minimum_commercial_rule` da configurare (Master Plan §25 → `NEEDS_PO_CONFIRMATION`).

### 3.6 QuoteLine snapshot (M5)
Ogni riga del preventivo deve conservare:

```python
QuoteLine = {
  # Identità
  "id": ..., "quote_id": ..., "environment_id": ..., "position_number": 1,
  # Prodotto
  "product_key": "PROEVOLUTION", "recipe_code": "WINDOW_1_SASH",
  "configuration": { ... },
  # TECHNICAL (frozen)
  "technical_snapshot": {
    "production_cost": 338.90,
    "bom_components": [...],
    "geometry": {...},
    "glass": {...},
    "hardware_rule_version": 1,
    "recipe_version": 1,
    "hourly_cost": 180.00,
    "production_time_hours": 0.75
  },
  # COMMERCIAL (frozen)
  "commercial_snapshot": {
    "multiplier": 3.00,
    "base_product_sale_price": 1016.70,
    "package_id": "...", "package_name": "Standard",
    "services": [
      {"service_id": "...", "list_price": 150.00, "discount": 0, "net": 150.00}
    ],
    "installation_included": true,
    "discount_amount": 0,
    "authorized_override": null,
    "net_sale_price": 1166.70,
    "vat_pct": 22.0
  },
  "calculation_hash": "sha256:..."
}
```

---

## 4. Formula commerciale principale (§28 Master Plan)

```
A = PRODUCTION_COST                                (dal pricing_v3.technical_snapshot)
B = A × MULTIPLIER (3.00)                          (base_product_sale_price)
C = PACKAGE / SERVICES INCLUSI                     (0 o + servizi già valorizzati)
D = INSTALLATION                                   (posa customer_sale_price)
E = OTHER EXTRAS                                   (accessori opzionali)
F = DISCOUNT                                       (autorizzato, DiscountGuard)

PRE-VAT TOTAL = B + C + D + E − F
VAT = PRE-VAT × 22%
TOTAL = PRE-VAT + VAT
```

Esempio numerico per la finestra GT-REAL (1200×1400):
```
A = 338.90 €    (production_cost)
B = 1016.70 €   (338.90 × 3.00)
D =  150.00 €   (INSTALL_WINDOW_1_2_SASH)
F =    0.00 €
────────────────────────────
PRE-VAT = 1166.70 €
VAT     =  256.67 €
TOTAL   = 1423.37 €
```

---

## 5. Legacy da decommissionare (dopo M5 verde)

**Nessuna eliminazione ora.** Solo etichettatura come `LEGACY_ONLY_HISTORICAL_QUOTES`.

| Modulo | Path | Cosa fa oggi | Sostituto |
|---|---|---|---|
| `commercial_perimeter` engine | `app/services/recipes/commercial_perimeter.py` | Calcolo prezzo con hash snapshot | `pricing_v3.TechnicalCostResolver + CommercialPricingService` |
| `perimeter_assembler.run_perimeter_simulation` | `app/services/perimeter_assembler.py` | Wrapper del motore legacy | `pricing_v3.compute_pricing` |
| Quote line create via `/quote-structure/lines` | `app/routers/quote_structure.py` | Aggiunta linea preventivo | Nuovo endpoint M5 con snapshot pricing_v3 |
| Catalog product-simulator | `app/routers/catalog.py` L298-322 | Simulazione prezzo da catalogo | Vista tecnica del pricing_v3 |
| Pricing hub `/simulate` | `app/routers/pricing_hub.py` L142 | Debug simulator | Deprecato, redirect a `/pricing/compute` |

Codice legacy resta **read-only** per preventivi storici. Nessuna migrazione dei documenti esistenti. Nuovi preventivi passeranno esclusivamente per `pricing_v3`.

---

## 6. Test di identità (§33 Master Plan)

Per verifica futura M5:
- Chiamare `POST /api/pricing/compute` con `product_key=PROEVOLUTION, WINDOW, 1 sash, 1200×1400, WHITE_MASS, DOUBLE_STANDARD` → memorizzare `technical_snapshot.total_internal_cost = X`.
- Aprire la **Vista Tecnica** UI (M5) sulla stessa configurazione → deve mostrare **lo stesso** production_cost X e lo **stesso** hash `sha256`.
- Creare una `QuoteLine` (nuovo endpoint M5) sulla stessa configurazione → il `technical_snapshot` congelato deve avere production_cost X e hash identico.

**Regola:** un delta anche di 1 centesimo tra questi tre canali è un blocker M5.

---

## 7. Delta 28.34 € (M3 BUSINESS_GOLDEN = FAIL) — resta il blocker economico

Come già documentato in `M4_PRICING_RECIPES_AND_GOLDEN_TESTS.md`:
- **Quantità Panorama vs V1_3: coincidono al 100%**
- **Formule V1_3 correttamente implementate**
- **Delta è esclusivamente sui prezzi unitari profili V1_3** (fallback documentato) vs listino Enerhia reale
- Chiusura in UI `/tech-config/component-prices` — zero codice

Nota architetturale importante: `production_cost` errato di 28.34 € produce prezzo vendita errato di **28.34 × 3 = 85 €** su ogni serramento. Quindi la chiusura del delta economico **è preventiva** al collegamento del preventivatore commerciale.

---

## 8. Stop conditions (§37 Master Plan)

**M5 NON PUÒ INIZIARE** finché:
1. ❌ Delta 28.34 € non chiuso (o classificato esplicitamente `ECONOMICALLY_NOT_VALIDATED` dal cliente)
2. ❌ CommercialPackage entity non creata
3. ❌ Legacy `commercial_perimeter` non contrassegnato come `LEGACY_ONLY_HISTORICAL_QUOTES`
4. ❌ Vista Tecnica UI non collegata al `pricing_v3` (deve essere una lettura del motore, non un secondo calcolo)
5. ❌ Test di identità (§33) non verde su 3 canali

---

## 9. Prossimi step ordinati (per iterazioni future)

1. **Bloccare uso legacy per nuovi preventivi**: aggiungere in `quote_structure.py` un feature flag `USE_UNIFIED_PRICING_V3 = false` (default), pronto per essere attivato in M5.
2. **CommercialPackage backend**: model + router `/api/commercial-packages` + seed pacchetti default (Standard/Premium).
3. **Vista Tecnica UI**: componente React `<TechnicalView />` che riceve il response di `/api/pricing/compute` e mostra BOM/quantità/costi. Read-only.
4. **UI Commerciale Preventivo**: modale/pagina che invoca compute → mostra `base_product_sale_price` (con `production_cost` nascosto al commerciale). Aggiunge selettore pacchetto + posa suggerita.
5. **QuoteLine snapshot**: nuovo endpoint `POST /api/quotes/{id}/lines/from-configuration` che congela technical + commercial snapshot + hash.
6. **Golden test di identità**: pytest che chiama compute + crea QuoteLine + confronta i due hash.

---

## 10. Deliverable & audit trail

- `/app/memory/GEOMETRIC_TO_COMMERCIAL_PRICING_ARCHITECTURE_V1.md` (**questo file**) — architettura definitiva
- `/app/memory/M4_PRICING_RECIPES_AND_GOLDEN_TESTS.md` — delta analysis + BOM per 5 ricette
- `/app/memory/ENERHIA_OPERATING_CORE_MASTER_STATUS.md` — status milestone
- Regola commerciale versione 2 salvata (`multiplier=3.00` confermato)

**Non pubblicato in produzione. Attende collaudo utente.**
