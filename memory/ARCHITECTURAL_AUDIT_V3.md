# Panorama Pilot — AUDIT ARCHITETTURALE v3 (DECISIONE RIBALTATA)
**Data**: Feb 2026 · Iter 33  
**Sostituisce**: `ARCHITECTURAL_AUDIT_V2.md` (opzione B ridotta rifiutata dal PO)  
**Direzione approvata**: **Sistema B diventa fonte autorevole tecnico-produttiva**. **Sistema A si riduce a livello commerciale puro**.  
**Vincolo**: zero implementazione. Solo diagnosi + piano + modelli dati. Attende approvazione esplicita.

---

## 0 · Principio guida (dal PO)

> Il prezzo di vendita **nasce dal costo tecnico**, non da un catalogo commerciale parallelo.  
> Il motore commerciale **non deve mai possedere un secondo catalogo componenti o un secondo listino tecnico**.  
> Deve ricevere `total_internal_cost` dal Sistema B e applicare solo regole commerciali.

Ogni proposta successiva deve rispettare questo principio.

---

## 1 · Nuovo diagramma architetturale

```
┌───────────────────────────────────────────────────────────────────────────┐
│                         SISTEMA B — TECNICO-PRODUTTIVO                     │
│                        (fonte autorevole unica)                            │
│                                                                            │
│  profile_systems (tech, bar, kerf, weld_allowance, offcuts)                │
│  profiles (componenti fisici: telaio/anta/rinforzo/fermavetro/scambio)     │
│  bom_templates (formule quantità/lunghezza/area/condizioni)                │
│  glass_types + glass_recipes (formule vetro)                               │
│  hardware_kits + accessories                                               │
│  color_categories + colors (con is_premium, scrap_mode)                    │
│  item_pricelists (kind=cost) ← COSTI DI ACQUISTO reali                     │
│  production_config (hourly, prod_time, kerf, weld, bar_len)                │
│  scrap_stock (residui riutilizzabili)                                      │
│                                                                            │
└──────────────────┬──────────────────────────────────────────────────────────┘
                   │
   ┌───────────────▼────────────────┐  ┌───────────────┐  ┌───────────────┐
   │    ProfileSystemResolver         │  │  BomResolver  │  │ CutList Engine│
   │ (versione, tech, componenti      │  │ (BOM + form.  │  │ (nesting FFD/ │
   │  autorizzati, scope tenant)      │  │  → concrete)  │  │  BFD, taglio) │
   └───────────────┬────────────────┘  └──────┬────────┘  └───────┬───────┘
                   │                          │                   │
                   └───────┬──────────────────┘                   │
                           │                                       │
                           ▼                                       │
              ┌──────────────────────────────┐                   │
              │   TechnicalCostResolver        │                   │
              │                                │                   │
              │  materials_cost                │                   │
              │  labor_cost                    │                   │
              │  waste_cost                    │                   │
              │  services_cost                 │                   │
              │  accessories_cost              │                   │
              │  ─────────────────────         │                   │
              │  total_internal_cost           │                   │
              │  + technical_snapshot          │                   │
              │  + technical_hash              │                   │
              └───────────────┬────────────────┘                   │
                              │                                     │
                              ▼                                     │
┌──────────────────────────────────────────────────────────────┐   │
│                  SISTEMA A — LIVELLO COMMERCIALE              │   │
│                                                               │   │
│  commercial_products (referenzia profile_system_id +          │   │
│                       profile_system_version)                 │   │
│  commercial_rules: pricing_method, multiplier / markup_pct /  │   │
│                    gross_margin_pct / fixed_price             │   │
│  commercial_discounts, promotions, tax_rate, commissions      │   │
│                                                               │   │
│  ┌───────────────────────────────────────────────┐            │   │
│  │       CommercialPricingService                 │            │   │
│  │  input: technical_cost_snapshot + rules        │            │   │
│  │  output: sale_price + commercial_snapshot      │            │   │
│  └───────────────────────────────────────────────┘            │   │
└───────────────────────────────┬───────────────────────────────┘   │
                                │                                   │
                                ▼                                   ▼
                    ┌──────────────────────────┐        ┌────────────────────┐
                    │  quote.lines[]:            │        │  cutting_lists     │
                    │   • technical_snapshot     │        │  (produzione)      │
                    │   • commercial_snapshot    │        └────────────────────┘
                    └──────────┬──────────────┘
                               │
                               ▼
                    ┌──────────────────────────┐
                    │   contracts (snapshot     │
                    │   ereditato immutabile)   │
                    └──────────────────────────┘
```

**Punto chiave**: il flusso è **unidirezionale** dal Sistema B verso il Sistema A. Il Sistema A **non legge mai** direttamente da `profiles`, `bom_templates`, `item_pricelists`. Legge solo il `technical_cost_snapshot` prodotto dal resolver.

---

## 2 · Modello dati del Sistema B autorevole

### 2.1 · Sistema profilo
```python
class ProfileSystem(BaseDoc):
    code: str                             # "PROEVOLUTION", "PROEVOLUTION-RESTAURO"
    name: str
    material: Literal["pvc","alu","wood","alu_wood","alu_pvc"]
    series: Optional[str]
    tech: ProfileSystemTech               # bar_length, kerf, offcuts, weld_allow, ecc.
    version: int
    parent_version_id: Optional[str]
    valid_from / valid_to
    ps_status: Literal["draft","active","archived"]
    tenant_id: str  (o None per system)
```

`ProfileSystemTech` (già in `models_parametric.py`) — MANTENUTO, esteso opzionalmente con:
- `default_labor_rate_per_hour: Optional[float]` (fallback se non in production_config)
- `default_installation_time_min: Optional[float]`

### 2.2 · Componenti fisici
```python
class Profile(BaseDoc):
    system_id: str                        # FK obbligatoria a profile_systems
    code: str                             # "5103", "12130"
    name: str
    role: ProfileRole                     # frame, sash, reinforcement_frame,
                                           # reinforcement_sash, glazing_bead,
                                           # meeting_stile, reinforcement_meeting_stile,
                                           # threshold, sill_int/ext, ecc.
    bar_length_mm: Optional[int]          # override sul sistema
    weight_per_m_kg: float
    section_desc: Optional[str]
    supplier_id / supplier_code
    is_cutting_relevant: bool
    is_demo: bool
    active: bool
    tenant_id: str
```

Idem `GlassType`, `HardwareKit`, `Accessory` (già in `models_parametric.py`).

### 2.3 · BOM (formule)
```python
class BomComponent:
    id: str
    sequence: int
    component_type: ComponentType         # profile|glass|hardware|accessory|labor|...
    ref_id: Optional[str]                 # FK verso Profile/Glass/Hardware/Accessory
    role: Optional[str]
    quantity_formula: str = "1"
    length_formula: Optional[str]
    width_formula / height_formula / area_formula / weight_formula
    condition: List[Dict]
    unit_of_measure: str
    waste_pct: float
    scrap_fixed_mm_per_cut / scrap_fixed_per_piece
    rounding_rule
    minimum_quantity / minimum_billable_qty
    consumption_mode: "proportional" | "full_bar"
    bar_rounding: bool
    application_scope: per_piece | per_line | per_opening | per_quote
    color_category_id_override: Optional[str]
    is_customer_visible / is_cost_relevant / is_cutting_relevant / is_optional

class BomTemplate(BaseDoc):
    code: str
    name: str
    product_key: str                      # window_1_leaf | window_2_leaves | fixed | door_1_leaf | ...
    profile_system_id: str
    hardware_kit_default_id / glass_type_default_id / color_category_default_id
    level: "commercial" | "production"   # → deprecato: sempre "production"
    components: List[BomComponent]
    version: int
    bom_status: draft | active | scheduled | archived
    valid_from / valid_to
    approved_by / approved_at
    formula_schema_version: int
    tenant_id: str
```

### 2.4 · Listini di **COSTO**
```python
class ItemPricelist(BaseDoc):
    code, name
    kind: Literal["cost"]                 # ← Sistema B usa SOLO kind=cost
                                           # (le entrate "sell" del vecchio schema
                                           #  vengono DEPRECATE — vedi §4)
    currency: str
    valid_from / valid_to
    ipl_status: draft | active | archived
    priority: int
    version: int
    entries: List[ItemPricelistEntry]     # {ref_type, ref_id, color_id?, unit, unit_price}
    is_demo: bool
    tenant_id: str
```

Schema entry **unico** (lookup sempre via `ref_type + ref_id`, opzionalmente filtrato per `color_id`). Nessuno schema dual.

### 2.5 · Configurazione produzione
```python
class ProductionConfig(BaseDoc):
    hourly_cost: Optional[float]          # €/h — obbligatorio; MISSING_HOURLY_COST
    production_time_default_minutes: Optional[float]
    # Per tipologia (dettaglio):
    fixed_window_time_minutes / one_sash_time_minutes / two_sash_time_minutes / …
    # Vetro
    default_glass_price_per_sqm: Optional[float]  # opzionale se ricetta specifica
    default_glass_min_sqm: Optional[float]
    # Tecnici (assorbono i valori duplicati oggi in profile_systems.tech)
    kerf_default_mm: float = 3.0
    weld_allowance_default_mm: float = 0.0
    bar_length_pvc_mm: int = 6500
    bar_length_reinforcement_mm: int = 6000
    bar_head_offcut_mm / bar_tail_offcut_mm
    min_reusable_scrap_mm: float = 400.0
    premium_pvc_surcharge_pct: float = 6.0
    tenant_id: str  (unique)
```

**Nota**: valori tecnici come `kerf` restano ANCHE in `profile_systems.tech` come **override per sistema**. `production_config` fornisce il **fallback tenant**.

### 2.6 · Configurazione servizi (nuova)
```python
class ServicesConfig(BaseDoc):
    """Costi standard servizi accessori — parte del Sistema B (tecnico)."""
    installation_default_per_piece: Optional[float]
    installation_default_per_hour: Optional[float]
    transport_default_per_km: Optional[float]
    transport_default_flat: Optional[float]
    disposal_default_per_kg: Optional[float]
    tenant_id: str
```

Questi valori sono **default tecnici** che il preventivatore può override caso-per-caso ma che NON sono decisioni commerciali.

---

## 3 · Modello dati del Sistema A (commerciale, ridotto)

Sostituisce `products` (models_catalog) attuale, che oggi contiene sia elementi commerciali sia tecnici.

### 3.1 · Prodotto commerciale
```python
class CommercialProduct(BaseDoc):
    code: str                             # "ProEvolution-1anta-standard"
    name: str
    description: Optional[str]
    # RIFERIMENTI al Sistema B (versionati)
    profile_system_id: str                # FK → profile_systems
    profile_system_version: int           # snapshot version
    bom_template_id: str                  # FK → bom_templates
    bom_template_version: int
    # Compatibilità visuale
    product_key: str                      # window_1_leaf | ...
    default_color_category_id: Optional[str]
    default_hardware_kit_id: Optional[str]
    default_glass_type_id: Optional[str]
    # Regole commerciali (default; il preventivo può override)
    default_pricing_method: PricingMethod
    default_multiplier: Optional[float]
    default_markup_percentage: Optional[float]
    default_gross_margin_percentage: Optional[float]
    default_fixed_price: Optional[float]
    # Metadata
    is_active: bool
    is_demo: bool
    tenant_id: str
```

**Nota critica**: `CommercialProduct` **NON contiene componenti**. Non contiene prezzi di acquisto. Contiene solo `profile_system_id`, `bom_template_id`, e le regole commerciali.

### 3.2 · Regole commerciali
```python
PricingMethod = Literal["MULTIPLIER", "MARKUP_ON_COST", "TARGET_GROSS_MARGIN", "FIXED_PRICE"]

class CommercialRules(BaseModel):
    pricing_method: PricingMethod
    multiplier: Optional[float]                     # per MULTIPLIER
    markup_percentage: Optional[float]              # per MARKUP_ON_COST
    gross_margin_percentage: Optional[float]        # per TARGET_GROSS_MARGIN
    fixed_price: Optional[float]                    # per FIXED_PRICE
    # Sconti / promozioni
    discount_amount: float = 0.0
    discount_pct: float = 0.0
    promotion_code: Optional[str]
    # Fiscale
    tax_rate: float = 0.22                          # IVA 22% default
    tax_included: bool = False
    # Commissioni (per calcolo netto agente)
    commission_pct: float = 0.0
    # Arrotondamenti commerciali
    round_to_nearest: float = 0.01                  # €
    # Metadata
    scope: Literal["product","quote","quote_line"]  # da dove viene la regola
    approved_by: Optional[str]
```

---

## 4 · Mapping "Sistema A oggi" → "Sistema B" (dove va cosa)

| Oggi in Sistema A (products/catalog) | Destinazione | Note |
|---|---|---|
| `products.components[].code` (`"5103"`) | → `profiles.code` in Sistema B | Codice fisico va nel Sistema B, referenziato via `ref_id` |
| `products.components[].category` (`"telaio"`) | → `profiles.role` (`"frame"`) | Mappatura semantica 1:1 |
| `products.components[].applies_to[]` (`["finestra_1a"]`) | → `bom_templates.product_key` + `condition[]` sui componenti | I bom templates hanno già scope per `product_key` |
| `products.components[].waste_percentage` | → `bom_templates.components[].waste_pct` | Sistema B è la sede unica dello sfrido |
| `products.components[].formula_qty/formula_cut` | → `bom_templates.components[].quantity_formula/length_formula` | Sistema B ha già i parser AST |
| `products.default_hardware_kit.{code, price}` | → `bom_templates.hardware_kit_default_id` + `item_pricelists.entries[ref_type=hardware].unit_price` | Prezzo va nel listino di **costo** |
| `products.default_glass_price_per_sqm` | → `production_config.default_glass_price_per_sqm` (già presente) | Rimane fallback tenant |
| `products.default_other_components_cost` | → `bom_templates.components[type=accessory].unit_cost` OPPURE `ServicesConfig` | Da decidere per singolo caso |
| `catalog_code_mappings` (5103→telaio, 12130→anta, ecc.) | → utility di import (rimane in Sistema A come helper importer) | Non è dato autoritativo di prezzo/quantità |
| `item_pricelists` (sell schema `entries[].code`) | **DEPRECATO** — migrare a schema Sistema B `{ref_type, ref_id, color_id}` | Fase 2 migrazione |
| `production_config` (hourly, prod_time, glass_price, margin, ecc.) | Restano nel Sistema B (già lo sono di fatto) — Sistema A **non usa** `default_margin_pct` | `default_margin_pct` diventa fallback commerciale, sposta in `CommercialProduct` |
| `glass_recipes` | Restano — sono formule tecniche autorevoli | Sistema B |
| `color_categories`, `colors` | Restano — Sistema B (con `is_premium` letto anche da CommercialPricingService per surcharge PVC) | Il +6% PVC è tecnicamente una maggiorazione costo, semanticamente commerciale — decidere in Fase 1 dove metterlo |

---

## 5 · Dati tecnici da ELIMINARE dal Sistema A

Dopo migrazione:

1. **`products.components[]`** — l'intera lista inline. Sostituita da `CommercialProduct.bom_template_id` che referenzia la BOM in Sistema B.
2. **`products.default_hardware_kit`** (inline object) — sostituita da FK a `hardware_kits` + entry in `item_pricelists`.
3. **`products.default_other_components_cost`** — sostituita da BOM item accessory con costo dal listino B.
4. **`item_pricelists.entries[]` con schema `{code, color_code, unit_price}`** — l'intero schema dual è deprecato. Solo `{ref_type, ref_id, color_id, unit_price}`.
5. **`catalog_code_mappings`** — non è dato autoritativo. Rimane solo come mappa importer.

**Sistema A tiene**: `CommercialProduct` (nuovo), `CommercialRules` (nuovo), `discount_thresholds`, `promotions`, `commissions`, `tax_configs`.

---

## 6 · Modello dei resolver

### 6.1 · ProfileSystemResolver

```python
class ResolvedProfileSystem(BaseModel):
    system: ProfileSystem                       # documento completo
    version_snapshot: int
    tech: ProfileSystemTech
    profile_ids_by_role: Dict[str, List[str]]   # {"frame": ["prof_1"], "sash": ["prof_2"], ...}
    is_system_scope: bool                        # True se tenant_id is None

async def resolve_profile_system(
    tenant_id: str,
    profile_system_id: str,
    version: Optional[int] = None,               # None = latest active
) -> ResolvedProfileSystem: ...
```

**Responsabilità**:
- Carica sistema profilo per tenant (o system-wide) e versione
- Enumera profili collegati per ruolo (frame/sash/reinforcement/…)
- Valida che il sistema sia `ps_status="active"` (o versione approvata)
- Nessuna logica di prezzo. Nessuna formula.

### 6.2 · BomResolver

```python
class BomResolverInput(BaseModel):
    tenant_id: str
    bom_template_id: str
    bom_version: Optional[int] = None
    profile_system: ResolvedProfileSystem
    params: Dict[str, Any]                       # width_mm, height_mm, nr_ante, color_id, ...

class ResolvedBom(BaseModel):
    bom: BomTemplate
    components_resolved: List[ResolvedComponent] # con quantità/lunghezza post-formula post-sfrido
    warnings: List[str]
    blocking_errors: List[Dict]
    formula_versions: Dict[str, int]             # per snapshot

async def resolve_bom(inp: BomResolverInput) -> ResolvedBom: ...
```

**Responsabilità**:
- Recupera BOM template + version
- Valuta formule via `services.formula.eval_formula(strict=True)` (parser AST, no eval)
- Applica sfrido, rounding, minimum_billable
- Nessuna logica di prezzo. Solo quantità.

### 6.3 · TechnicalCostResolver

```python
class TechnicalCostInput(BaseModel):
    tenant_id: str
    resolved_bom: ResolvedBom
    cost_pricelist_id: str                       # kind="cost"
    color_id: Optional[str]
    glass_type_id: Optional[str]
    hardware_kit_id: Optional[str]
    installation_override: Optional[float]
    transport_override: Optional[float]
    accessory_overrides: List[Dict[str, float]]

class TechnicalCostSnapshot(BaseModel):
    # Identificatori versionati
    profile_system_id: str
    profile_system_version: int
    bom_template_id: str
    bom_version: int
    cost_pricelist_id: str
    cost_pricelist_version: int
    formula_schema_version: int
    # Componenti (dettaglio audit)
    components: List[Dict]                       # {code, ref_id, qty, unit, unit_cost, line_cost, waste}
    # Aggregati
    materials_cost: Decimal
    labor_cost: Decimal
    waste_cost: Decimal                          # sfrido monetizzato
    services_cost: Decimal                       # installation + transport + disposal
    accessories_cost: Decimal
    glass_cost: Decimal
    hardware_cost: Decimal
    # TOTALE
    total_internal_cost: Decimal
    # Meta
    blocking_errors: List[Dict]
    warnings: List[str]
    computed_at: datetime                        # audit-only, NON entra nel hash
    technical_hash: str                          # SHA256 deterministico input+output

async def resolve_technical_cost(inp: TechnicalCostInput) -> TechnicalCostSnapshot: ...
```

**Responsabilità**:
- Chiama `BomResolver` per ottenere componenti concreti
- Per ogni componente cerca `unit_cost` in `item_pricelists(kind=cost, ipl_status=active)` — filtro `ref_type+ref_id+color_id`
- Calcola `line_cost = qty * unit_cost * (1 + waste/100)`
- Aggrega materials/labor/waste/services/accessories
- **NON conosce moltiplicatori, sconti, IVA**
- Emette `MISSING_*` come blocking_errors se dato mancante

### 6.4 · CommercialPricingService

```python
class CommercialPricingInput(BaseModel):
    technical_cost_snapshot: TechnicalCostSnapshot
    rules: CommercialRules

class CommercialSnapshot(BaseModel):
    pricing_method: PricingMethod
    # Input economici
    total_internal_cost: Decimal                 # copiato da technical_snapshot per audit
    # Parametri applicati
    multiplier: Optional[Decimal]
    markup_percentage: Optional[Decimal]
    gross_margin_percentage: Optional[Decimal]
    fixed_price: Optional[Decimal]
    # Calcolo intermedio
    sale_price_before_discount: Decimal
    discount_amount: Decimal
    discount_pct: Decimal
    promotion_code: Optional[str]
    # Fiscale
    taxable_amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    tax_included: bool
    # OUTPUT
    final_sale_price: Decimal                    # netto imposte se tax_included=False
    final_sale_price_with_tax: Decimal
    # Meta
    commission_pct: Decimal
    commission_amount: Decimal
    commercial_hash: str                         # SHA256 deterministico
    computed_at: datetime

def compute_commercial_price(inp: CommercialPricingInput) -> CommercialSnapshot: ...
```

**Responsabilità**:
- Applica la formula corrispondente al `pricing_method`
- Applica sconto → tassa → arrotondamento
- **NON tocca il costo**. Il `total_internal_cost` viene copiato as-is.
- Emette `commercial_snapshot` deterministico.

---

## 7 · Formule supportate (esplicite)

| Metodo | Formula | Esempio con cost=1000, param=40 |
|---|---|---|
| **MULTIPLIER** | `sale_before_discount = cost × multiplier` | mult=1.40 → 1400 |
| **MARKUP_ON_COST** | `sale_before_discount = cost × (1 + markup/100)` | markup=40% → 1400 |
| **TARGET_GROSS_MARGIN** | `sale_before_discount = cost / (1 - margin/100)` | margin=40% → 1666.67 |
| **FIXED_PRICE** | `sale_before_discount = fixed_price` (cost usato solo per audit) | fixed=1500 → 1500 |

Poi in tutti i casi:
```
sale_after_discount = sale_before_discount - discount_amount - (sale_before_discount * discount_pct/100)
taxable_amount      = sale_after_discount
tax_amount          = taxable_amount * tax_rate
final_sale_price    = sale_after_discount        (se tax_included=False)
                     OR sale_after_discount + tax_amount   (se tax_included=True)
```

**Rinomina obbligatoria**: il campo attuale `margin_pct` del motore commercial_perimeter (audit v1) deve essere rinominato/mappato:
- Se il valore è "40" e l'intento era markup → `pricing_method=MARKUP_ON_COST, markup_percentage=40`
- Se il valore era margine vero → `pricing_method=TARGET_GROSS_MARGIN, gross_margin_percentage=40`

**Decisione operativa storica** (dal codice attuale): comportamento = MARKUP_ON_COST. La migrazione dei dati esistenti deve preservare questa semantica.

---

## 8 · Doppio snapshot su ogni riga di preventivo

```python
class QuoteLine(BaseModel):
    # ...campi esistenti...
    technical_snapshot: TechnicalCostSnapshot    # § 6.3
    commercial_snapshot: CommercialSnapshot      # § 6.4
    # Legacy pricing_snapshot: MIGRATO a technical+commercial (Fase 2)
```

**Regola fondamentale**:
- Modificare `item_pricelists` (costi acquisto) → **non altera** i preventivi salvati (technical_snapshot immutabile)
- Modificare `CommercialRules` (moltiplicatore) → **non altera** i preventivi salvati (commercial_snapshot immutabile)
- Un nuovo preventivo con stessi input ricalcola entrambi con i nuovi valori — questa è la parte richiesta dallo scenario di accettazione (§13)

Contratti derivati ereditano **entrambi gli snapshot** — invariabili per definizione.

---

## 9 · Pagina "Sistemi profilo e formule" (redisegn UX)

L'attuale `ParametricAdminPage` diventa il **centro operativo** dell'admin tecnico:

### Tab 1: Sistemi profilo
- Lista `profile_systems` (con versioning: draft/active/archived)
- Editor `ProfileSystemTech` (bar_length, kerf, offcuts, weld_allowance, ecc.)
- Create/Update/Publish workflow

### Tab 2: Componenti
- Lista `profiles` filtrata per `system_id`
- Editor `Profile` (code, role, bar_length_override, weight, supplier)

### Tab 3: Formule e BOM
- Lista `bom_templates` per `profile_system`
- Editor `BomComponent` (quantity_formula, length_formula, ecc.) con parser AST validator live
- **Simulazione tecnica**: dato L,H,n_ante → mostra qty/length calcolate

### Tab 4: Vetri
- Lista `glass_types` + `glass_recipes`
- Editor formule vetro (structured/custom)

### Tab 5: Ferramenta + Accessori
- Lista `hardware_kits` + `accessories`
- Editor semplice (code, name, kit_type, supplier)

### Tab 6: Prezzi di acquisto
- Editor `item_pricelists(kind=cost)` — schema unificato `{ref_type, ref_id, color_id, unit_price}`
- Import da XLS/CSV
- Versioning (draft → active)

### Tab 7: Tempi produzione + Costi
- Editor `production_config` (hourly, prod_time by n_sashes)
- Editor `ServicesConfig` (installation/transport/disposal defaults)

### Tab 8: Simulazione tecnica (nuova)
- Input: profile_system, bom_template, W, H, n_ante, color
- Output: `TechnicalCostSnapshot` completo con breakdown per componente + `total_internal_cost`

### Tab 9 (SOLO admin commerciale, permesso separato): Regole commerciali
- Editor `CommercialProduct` (referenzia profile_system + bom)
- Editor `CommercialRules` (pricing_method + parametri)
- Simulazione commerciale: `technical_cost` + rule → `sale_price`

**Il Sistema B (Tab 1-8) e il Sistema A (Tab 9) sono chiaramente separati per permessi.**

---

## 10 · Strategia di migrazione (9 fasi)

### Fase 0 — Audit (completata con questo doc)
- **Deliverable**: `ARCHITECTURAL_AUDIT_V3.md` ← questo file
- **Durata**: 3h (completata)
- **Rollback**: N/A

### Fase 1 — Modelli e resolver (implementazione backend, no wire-in)
- **Deliverable**:
  - `app/models_technical.py` — `TechnicalCostSnapshot`, `ResolvedBom`, `ResolvedProfileSystem`, `ResolvedComponent`
  - `app/models_commercial.py` — `CommercialProduct`, `CommercialRules`, `CommercialSnapshot`, `PricingMethod` enum
  - `app/services/profile_system_resolver.py` (§ 6.1)
  - `app/services/bom_resolver.py` (§ 6.2, wrapper di `parametric_engine.resolve_bom`)
  - `app/services/technical_cost_resolver.py` (§ 6.3)
  - `app/services/commercial_pricing_service.py` (§ 6.4) con 4 metodi
  - Unit test estesi (30+ scenari)
- **Durata**: 5 giorni
- **Rollback**: git revert (nessun wire-in)
- **Rischi**: BASSO — solo aggiunta, nessuna modifica esistente
- **Test**: contract test per ogni resolver (input→output deterministico)

### Fase 2 — Migrazione dati (DRY-RUN → APPLY)
- **Deliverable**:
  - `scripts/migrate_products_components_to_bom.py`: per ogni `products.components[]` cerca (o crea) entry in `bom_templates.components[]` con formule di default per la categoria
  - `scripts/migrate_pricelist_schema.py`: normalizza `item_pricelists.entries[]` da `{code, color_code}` a `{ref_type, ref_id, color_id}` risolvendo `code → profile.id`
  - `scripts/migrate_hardware_kit_prices.py`: sposta `products.default_hardware_kit.price` in entry `item_pricelists(kind=cost)`
  - `scripts/create_commercial_products.py`: per ogni `products` crea `CommercialProduct` con FK a `profile_system_id` + `bom_template_id`
  - Ognuno con dry-run + apply + checksum verify
- **Durata**: 5 giorni
- **Rollback**: dump MongoDB pre-Fase 2 obbligatorio. Rollback = ripristino
- **Rischi**: ALTO — è la fase più delicata. Ogni script deve produrre report before/after
- **Test**: aggregate count(products.components) → count(bom_templates.components) equivalente; hash dei prezzi migrati

### Fase 3 — Wire-in motore commerciale al nuovo TechnicalCostResolver
- **Deliverable**: `perimeter_assembler.py` **deprecato** in favore di `technical_cost_resolver + commercial_pricing_service`. Nuovo endpoint `POST /api/pricing/compute` che restituisce entrambi gli snapshot.
- **Durata**: 4 giorni
- **Rollback**: `perimeter_assembler.py` rimane in codice ma non chiamato — feature flag
- **Rischi**: MEDIO — deve produrre lo stesso `sale_price` del vecchio motore su preventivi test
- **Test**: **contract test** su 20 preventivi reali → sale_price pre e post identico ±0.01€

### Fase 4 — Wire-in preventivatore
- **Deliverable**: `/api/quote-structure/{qid}/openings/{oid}/products/compute-and-add` chiama il nuovo endpoint. `quote.lines[]` salva `technical_snapshot + commercial_snapshot`.
- **Durata**: 3 giorni
- **Rollback**: git revert
- **Rischi**: MEDIO
- **Test**: E2E preventivo Lead→Firma con nuovi snapshot

### Fase 5 — Wire-in motore tecnico + lista taglio
- **Deliverable**: `technical_cut_list` deriva da `bom_resolver.components_resolved` (già disponibile). CuttingList generata direttamente dal preventivo.
- **Durata**: 3 giorni
- **Rollback**: git revert
- **Rischi**: MEDIO
- **Test**: cuts generati per preventivo test corrispondono al legacy

### Fase 6 — Riscrittura frontend "Sistemi profilo e formule"
- **Deliverable**: nuovo `TechnicalConfigPage.jsx` (Tab 1-8) + `CommercialRulesPage.jsx` (Tab 9). Sostituisce `ParametricAdminPage.jsx`.
- **Durata**: 8 giorni
- **Rollback**: nuovo file, vecchio non toccato in questa fase
- **Rischi**: MEDIO (nuova UX, feedback utente necessario)
- **Test**: manuale + Playwright per ogni tab

### Fase 7 — Contratti / PDF
- **Deliverable**: PDF template aggiornato per mostrare `commercial_snapshot` (senza esporre `technical_snapshot` al cliente)
- **Durata**: 2 giorni
- **Rischi**: BASSO

### Fase 8 — Pulizia legacy
- **Deliverable**:
  - Rimozione `perimeter_assembler.py`, `commercial_perimeter.py` (dopo verifica zero uso)
  - Rimozione `products.components[]` inline (già migrato)
  - Rimozione `products.default_hardware_kit` inline
  - `item_pricelists.entries[]` legacy schema drop (già migrato)
  - Rimozione `ParametricAdminPage.jsx`
  - Drop feature flag Fase 3
- **Durata**: 3 giorni
- **Rollback**: git revert + dump restore
- **Rischi**: ALTO (drop finale)

### Totale
- **~33 giorni-uomo** (best case)
- **Ordine strettamente sequenziale**: 1→2→3→4→5→6→7→8

---

## 11 · Test di accettazione finale (scenario obbligatorio)

Riprende il test richiesto dal PO — 12 step + doppio snapshot:

```
1.  admin crea sistema profilo "ProEvolution" via TechnicalConfigPage Tab 1   ✅
2.  admin aggiunge profili "5103" (frame) e "12130" (sash) via Tab 2          ✅
3.  admin aggiunge rinforzi 4133/4135 via Tab 2                                ✅
4.  admin inserisce prezzi di acquisto in item_pricelists(kind=cost) Tab 6    ✅
5.  admin configura formule BOM tramite Tab 3                                  ✅
6.  admin approva glass_recipe Tab 4                                           ✅
7.  admin imposta production_config + services_config Tab 7                    ✅
8.  admin simula tecnica Tab 8 → TechnicalCostSnapshot con total_internal=X    ✅
9.  admin crea CommercialProduct + rule (MARKUP_ON_COST 40%) via Tab 9         ✅
10. commercial simulator → sale_price = X*1.40, commercial_hash=h_c            ✅
11. crea preventivo → line con technical_snapshot(hash=h_t) + commercial_snapshot(h_c) ✅
12. genera contratto → contract.technical=h_t + commercial=h_c invariati       ✅
13. admin modifica prezzo acquisto 5103 da 6.50 a 7.00, pubblica listino v2    ✅
14. il preventivo del punto 11 → total_internal INVARIATO, sale_price INVARIATO ✅
15. nuovo preventivo con stesso input → nuovo technical_snapshot con costo aggiornato ✅
16. admin modifica multiplier da 1.40 a 1.50 sul CommercialProduct              ✅
17. il preventivo del punto 11 → commercial_snapshot INVARIATO, sale_price INVARIATO ✅
18. nuovo preventivo → nuovo commercial_snapshot con moltiplicatore aggiornato  ✅
```

**Ogni step deve avere test automatico** (pytest o Playwright). Il refactor è concluso solo con **18/18 verdi**.

---

## 12 · Rischi

| Categoria | Rischio | Mitigazione |
|---|---|---|
| **Dati** | Perdita dati in migrazione Fase 2 | Dump MongoDB pre-Fase 2 obbligatorio + checksum verifica |
| **Semantica** | `margin_pct` esistente interpretato come markup — se in realtà utente intendeva altro, prezzi cambiano | Contract test 20 preventivi pre/post identici + comunicazione utente pre-migrazione |
| **Formule** | Formule utente-defined in `bom_templates` non coprono tutti i casi che oggi `commercial_perimeter` calcola cablato (es. perimetro anta con extra_sashes) | Fase 1 include validazione: per ogni `product_key` esistente deve esistere BOM con formule complete → mancante = blocker |
| **Tempistica** | 33 giorni sono ottimistici. Se BOM template incompleta, si rientra in Fase 1 | Buffer 20% (~7 giorni) sulla stima |
| **Adoption** | Utente admin abituato a `ParametricAdminPage` deve imparare nuova UX | Fase 6 include user testing + documentazione |
| **Rollback tardivo** | Post-Fase 8 rollback impossibile senza dump | Tag git per ogni fase + dump progressivi |
| **Regressioni** | Snapshot hash cambia inavvertitamente → contratti storici sembrano corrotti | `technical_hash` e `commercial_hash` sono **calcolati con lo schema pre-migrazione** per doc storici; solo i nuovi usano il nuovo schema |

---

## 13 · Rollback strategy

Per ogni fase, tag git dedicato:
- `pre-audit-v1-2026-02` — punto zero (esistente)
- `pre-migration-fase1` — prima di aggiunta modelli
- `pre-migration-fase2` — **prima di modifica dati** (obbligatorio dump MongoDB pre-tag)
- `pre-migration-fase3` — prima wire-in motore
- `pre-migration-fase4` — prima wire-in preventivatore
- `pre-migration-fase8` — prima drop legacy

**Rollback Fase 2 (dati)**: `mongorestore` da dump pre-tag2.  
**Rollback Fase 3-7 (codice)**: `git reset --hard pre-migration-faseN`.  
**Rollback Fase 8 (drop legacy)**: git revert + eventuale re-migrate dei dati droppati (script inverso da preparare).

---

## 14 · Stima aggiornata

| Fase | Durata | Note |
|---|---|---|
| 0 Audit | ✅ done | — |
| 1 Modelli+Resolver | 5 gg | Include unit test |
| 2 Migrazione dati | 5 gg | Rischio ALTO, buffer ×1.5 |
| 3 Wire-in motore | 4 gg | Feature flag |
| 4 Wire-in preventivatore | 3 gg | E2E test |
| 5 Wire-in tecnico/taglio | 3 gg | |
| 6 Frontend rewrite | 8 gg | 9 tab |
| 7 PDF | 2 gg | |
| 8 Pulizia legacy | 3 gg | Rischio ALTO |
| **Totale nominale** | **33 gg** | |
| **Con buffer 20%** | **~40 gg** | ~8 settimane |

---

## 15 · Vincoli rispettati

- ✅ Sistema B **NON eliminato**, diventa fonte autorevole
- ✅ Sistema A ridotto a livello commerciale puro
- ✅ Motore commerciale NON mantiene secondo listino tecnico
- ✅ Componenti NON duplicati dentro ogni prodotto
- ✅ `CommercialProduct` referenzia `profile_system_id + version` (§3.1)
- ✅ Costo nasce dalla configurazione tecnica (`TechnicalCostResolver`)
- ✅ Prezzo di vendita = costo × regola commerciale (§7)
- ✅ 4 pricing method separati (`MULTIPLIER/MARKUP_ON_COST/TARGET_GROSS_MARGIN/FIXED_PRICE`)
- ✅ Doppio snapshot immutabile (§8)
- ✅ Zero implementazione iniziata
- ✅ Nessuna nuova collezione creata in questa iterazione
- ✅ Nessun refactoring estetico

---

## 🛑 STATO

**Nessuna riga di codice scritta.** Documento pronto per revisione.

**Attende approvazione esplicita del PO su**:
1. Modello dati Sistema B (§2) e Sistema A ridotto (§3) — modifiche puntuali OK
2. Contratti Resolver / PricingService (§6) — parametri e output
3. Doppio snapshot (§8) — schema
4. UX 9 tab (§9) — approvare mockup prima di sviluppare Fase 6
5. Piano 9 fasi (§10) — accettare durate e ordine
6. Test di accettazione 18-step (§11)

**Solo dopo approvazione punto per punto** parte la Fase 1.

---

**Documento chiuso.**
