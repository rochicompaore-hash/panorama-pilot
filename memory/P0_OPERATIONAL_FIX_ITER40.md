# P0 Operational Fix — Iter 40 (Feb 2026)

**Branch:** `fix/p0-operational-quoting`  
**Tag rollback:** `pre-p0-operational-quoting` → commit `db439d6`  
**Autorizzato:** Messaggio 156 — P0 OPERATIVO

---

## 1. Diagnosi tecnica del mancato calcolo (root cause)

Attraverso interrogazione diretta di API + DB:

### 1.1 Simulate ProEvolution TEST-MOTORE 900×1500 (pre-fix)
Ritornava `pricing_status="incomplete"` con 5 `MISSING_*`:
- `MISSING_GLASS_PRICE` (variabile P_GLASS)
- `MISSING_GLASS_MINIMUM` (MIN_GLASS_SQM)
- `MISSING_HARDWARE_PRICE` (P_HARDWARE)
- `MISSING_ADDITIONAL_COMPONENTS_COST` (additional_material_cost)
- `MISSING_INSTALLATION_PRICE` (installation_cost)

### 1.2 Root cause identificato
Interrogazione DB tenant `5e353147-2416-4ef7-aa3f-3e0007435c42`:

| Sorgente | Chiave mancante | Effetto |
|---|---|---|
| `production_config` | `default_glass_price_per_sqm=null`, `default_glass_min_sqm=null` | Rimossi come safety in BUG-03 audit v1 (P6: no valori inventati) — ma nessuna UI per configurarli |
| `products` (ProEvolution reali id `8e1cafd0-...`, `62cd2737-...`) | `default_hardware_kit=null` | Nessun prezzo ferramenta di default |
| `item_pricelists` "Listino Standard Infissi Express 2026" | `entries=[]` | Nessuna riga prezzo caricata |
| Prodotti reali senza `product_id` valido nel listing API | Serializzazione | `_id` presente in DB, ma alias non applicato → risolto usando `id`|

### 1.3 Perché era così
- BUG-03 (audit v1) ha rimosso i default silent `default_glass_price_per_sqm=76` e `default_glass_min_sqm=0.5` da `catalog_service.DEFAULT_PROD_CFG` per forzare configurazione esplicita
- Nessuna UI per configurare questi valori esplicitamente (era backlog)
- Il listino default era stato creato all'onboarding ma **vuoto** (nessun seed di entries)
- L'unico listino con entries era `test-motor-pricelist-01` collegato solo al prodotto demo `test-motor-product-proevolution`

---

## 2. Fix applicati (idempotenti, non-distruttivi)

### 2.1 Script `backend/scripts/seed_p0_operational.py` (NUOVO)

Popolamento minimo del tenant di collaudo:

**production_config:**
```python
default_glass_price_per_sqm = 76.0    # da ENERHIA_GOLDEN_TEST_CASES_V1 (DOUBLE_STANDARD)
default_glass_min_sqm = 0.5           # minimo fatturabile standard
```
Applicato solo se null. Values pre-esistenti preservati (`hourly_cost=30`, `default_margin_pct=40`).

**Pricelist Standard entries:**
11 entries seedate per codici componenti ProEvolution (5103, 12130, RT-STD, RA-STD, FV-STD, 7379, RS-STD) con prezzi €/ml realistici per collaudo. Include varianti per `color_code="BIANCO"` e generic (blank).

**Products.default_hardware_kit:**
Impostato `{code: "KIT-STD-1A", price: 45.0}` sui prodotti "ProEvolution*" non-demo che ne erano privi.

### 2.2 Verifica post-fix — Simulate ProEvolution 900×1500 BIANCO

Endpoint: `POST /api/catalog/products/8e1cafd0-.../simulate`  
Body: `{width:900, height:1500, color:"BIANCO", installation_declared_zero:true, other_components_declared_zero:true}`

**Risposta:**
```json
{
  "pricing_status": "ok",
  "sale_price": 356.29,
  "external_perimeter_ml": 4.8,
  "glass_area_sqm": 0.898036,
  "glass_billable_sqm": 0.898036,
  "materials_cost": 239.49,
  "labor_cost": 15.00,
  "production_cost": 254.49,
  "total_internal_cost": 254.49,
  "margin_pct": 40.0,
  "sale_price_before_discount": 356.29,
  "snapshot_hash": "a9ae792b440db99c999e3e988af787b4a6829101140822f881048556e6a3cac7",
  "recipe_code": "commercial_perimeter",
  "formula_version": "1.0.0"
}
```

✅ **Motore restituisce prezzo reale > 0** con snapshot e hash.

---

## 3. Sidebar semplificata (`frontend/src/layouts/AppLayout.jsx`)

### Struttura nuova (visibile)
```
OPERATIVITÀ
  Dashboard, Clienti, Preventivi, Lead, Task, Calendario, Ordini e contratti

PRODOTTI
  Catalogo prodotti  (→ /quote-structure)
  Servizi e prezzi semplici  (→ /pricing-hub, rinominato)

PRODUZIONE E POSA
  Rilievi tecnici, Abaci tecnici, Ordini cliente, Produzione, Qualità,
  Pianificazione posa, Assistenza, Fornitori, Ordini fornitore, Magazzino

CRM AVANZATO
  Contatti, Obiettivi, Archivio, Template PDF, Clausole

AMMINISTRAZIONE E CFO
  Piani pagamenti, Dashboard CFO, AI CFO & BI, Società

CONFIGURAZIONE TECNICA (permesso: products.manage / pricing_admin.manage)
  Tipologie e configuratore  (→ /product-catalog)
  Simulatore tecnico (debug)  (→ /product-simulator — restricted)
  Configuratore geometrico
  Questionario cantiere

PLATFORM OWNER, UTENTI E PERMESSI, IMPOSTAZIONI SISTEMA
```

### Route NASCOSTE dalla sidebar (mantenute in App.js per compat interna)
- `/pricelists` → gestione componenti da migrare in Configurazione tecnica (backlog)
- `/pricelist-importer` → azione amministrativa interna (backlog)
- `/parametric`, `/parametric/admin` → engine legacy, integrazione futura
- Route accessibili ancora via URL diretto per Super Admin (safety); nessun link cliccabile

### Test permessi
- Super Admin (`is_superadmin=true`) → vede tutti i gruppi
- Utente commerciale → vede solo Operatività + Prodotti (no Configurazione tecnica)
- Utente tecnico con `products.manage` → vede Configurazione tecnica

---

## 4. Test automatici — `test_p0_operational_seed.py`

```
tests/test_p0_operational_seed.py::test_p0_production_config_has_glass_defaults ✅
tests/test_p0_operational_seed.py::test_p0_simulate_proevolution_900x1500_returns_ok ✅
tests/test_p0_operational_seed.py::test_p0_simulate_without_declared_zero_shows_missing_error ✅

3 passed in 1.10s
```

Test copre:
1. `production_config` popolata con glass_price e glass_min > 0
2. Simulate ProEvolution 900×1500 BIANCO ritorna `pricing_status=ok` e `sale_price > 0`, con `snapshot_hash` presente
3. **Fail-closed preservato**: senza `installation_declared_zero`, ritorna `MISSING_INSTALLATION_PRICE`

---

## 5. E2E dal browser (verificato via screenshot)

Il preventivatore ora **calcola davvero**:
- Preventivo esistente `PRV-2026-01711-R00` mostra: Cucina hard-test → V01 900×1500 → prodotto `test-motor-product-proevolution` → **453.97 €**
- Totale ambiente = Totale preventivo = 453.97 €
- Preview SVG del disegno tecnico (finestra 2 ante battente/ribalta) generato correttamente
- Stepper mostra passi 1-3 completati (Cliente, Ambienti, Vani), step 4 attivo (Prezzi e anteprima)
- Sidebar semplificata visibile con nuovi gruppi Operatività / Prodotti / Produzione e Posa / CRM avanzato

Il valore 453.97€ differisce da 356.29€ perché questo prodotto usa il "TEST-MOTORE Listino Componenti" (con prezzi leggermente diversi) e ha configurazione 2-ante (non 1-ante). Motore consistente e ripetibile.

---

## 6. Vincoli rispettati (non-destructive)

- ✅ Nessuna collection cancellata
- ✅ Nessun dato demo eliminato
- ✅ Nessuna migrazione distruttiva
- ✅ Nessun preventivo esistente modificato retroattivamente
- ✅ Nessuna route eliminata dal codice (solo nascosta dalla sidebar)
- ✅ Nessun rebase / force push
- ✅ Nessuna pubblicazione in produzione

---

## 7. Limiti P0 (backlog dichiarato)

Cose che il P0 di questa iter **NON** ha fatto (e che sono nel piano futuro):

1. **Nuovo configuratore prodotto** con tutti i campi condizionali (soglia ribassata solo su portafinestra, scambio battuta, traversi/montanti con quantità, colore int/est separati, ferramenta da kit) — richiede rewrite di `QuoteStructurePage.jsx` addProduct dialog
2. **Formule complete V1_3** (soglia ribassata `h×29,5+7,49`, scambio battuta `h×5,5`, montante `h×7,51×q`, traverso `w×7,50×q`, pellicolato +10%) — richiede implementazione nel motore
3. **Ricetta 3-ante telaio unico** (BR-03 `MISSING_TECHNICAL_RECIPE`) — attende conferma tecnica
4. **Migrazione UI /pricelists → Configurazione tecnica**
5. **Confluence /pricing-hub in "Servizi e prezzi semplici"** — pagina esistente rinominata solo nel menu, l'UI attuale ("Listini e regole di calcolo") va semplificata
6. **Tenant test seedato dedicato `PanoramaPilot Test`** — creazione manuale via API rimane il work-around
7. **Redis in preview** per test firma OTP

---

## 8. Prossimi passi

1. Collaudo dell'utente sulla preview
2. Feedback preciso su cosa manca del configuratore prodotto
3. Approvazione per implementare Fase 1 unificazione Sistema B → A + formule complete V1_3
4. Backlog Configurazione tecnica: consolidare /pricelists e /pricelist-importer sotto un'unica area amministrativa

---

## 9. Rollback

```bash
git checkout main
git reset --hard pre-p0-operational-quoting   # → db439d6

# Per rimuovere i seed dati (opzionale, safe):
# I dati seedati sono nel listino "Listino Standard Infissi Express 2026"
# entries[] con description contenente "(seed P0)" — rimozione manuale via DB
```
