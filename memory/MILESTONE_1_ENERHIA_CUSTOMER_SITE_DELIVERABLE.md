# MILESTONE 1 Enerhia Operating Core — PART 2 / FINAL

**Data completamento:** 2026-02-19 · **Branch:** `feature/enerhia-operating-core-v1`
**Tag rollback pre-M1P1:** `pre-enerhia-operating-core-v1` (1e38818) · **Tag rollback pre-M1P2:** commit `0883e32`
**Preview URL:** `https://serramento-ops.preview.emergentagent.com`

---

## Part 1 (Sites/Cantieri) — completata in iter46

`backend/app/routers/sites.py` — CRUD completo `/api/sites`, progressivo `CANT-YYYY-NNNNN`, tenant isolation, campi logistica (piano, ascensore, tipologia, accessibilità, scarico, referente).

## Part 2 (Anagrafica + Timeline + UI + Preventivo vincolato) — completata ora

### 1. Backend — Customer schema esteso

**Modelli** (`backend/app/models_crm.py`):
```python
class Customer(BaseDoc):
    customer_number: Optional[str] = None          # CLI-000001 (per tenant, atomico)
    customer_type: str = "TO_CONFIRM"              # PRIVATE | COMPANY | TO_CONFIRM
    first_name, last_name                          # PRIVATE
    company_name                                   # COMPANY
    contact_person: ContactPerson                  # first/last/role/phone/email
    email, phone, whatsapp, pec, sdi_code
    address: LeadAddress                           # residenza (PRIVATE) o sede legale (COMPANY)
    billing_address: Optional[LeadAddress]
    vat_number, tax_code
    assigned_to, origin_lead_id, tags, notes, total_value
```

**Progressivo** (`backend/app/services/customer_number.py`):
- Formato `CLI-{6 cifre}`  (padding fisso, no reset annuale)
- Atomico via `find_one_and_update({$inc: current_number})` sulla collection `sequences` (key=`customer`)
- Non riutilizzabile dopo delete (contatore monotono crescente)
- Univoco per `tenant_id`

**Validation** (`backend/app/services/customer_validation.py`):
- `normalize_customer_type`: mapping legacy `private`→PRIVATE, `business`→COMPANY, mancante→TO_CONFIRM
- `validate_customer_type_on_create`: PRIVATE richiede first_name+last_name; COMPANY richiede company_name
- `validate_customer_type_on_update`: cliente legacy TO_CONFIRM forza la scelta al primo edit
- **`validate_customer_contract_readiness`** (gate `MISSING_CUSTOMER_TAX_CODE`): PRIVATE→tax_code, COMPANY→vat_number (fallback tax_code). Invocato SOLO in `POST /api/quotes/{id}/convert-to-contract`.

**Endpoint aggiornati** (`backend/app/routers/customers.py`):
- `POST /api/customers` → assegna `customer_number` atomico + valida tipo
- `PATCH /api/customers/{id}` → forza classificazione legacy al primo edit
- `GET /api/customers?q=&customer_type=&assigned_to=` → filtro tipo + ricerca su customer_number/nomi/P.IVA/CF
- Retro-compat: output `customer_type` sempre normalizzato

### 2. Backend — Timeline strutturata

**Nuovo router** `backend/app/routers/customer_timeline.py`:
- `GET /api/customers/{cid}/timeline?site_id=&category=` → DESC per created_at
- `POST /api/customers/{cid}/timeline` → crea evento MANUAL
- `DELETE /api/customers/{cid}/timeline/{eid}` → soft delete (autore o admin)

**Categorie**: CALL, FOLLOW_UP, COMMERCIAL_NOTE, TECHNICAL_NOTE, ADMIN_NOTE, INSTALLATION_NOTE, SUPPORT_NOTE, SYSTEM_EVENT.
**Channel** (separato): PHONE, EMAIL, WHATSAPP, IN_PERSON, SYSTEM, OTHER.
**event_source**: MANUAL (utente) o SYSTEM (backend, read-only).
**Visibility**: INTERNAL / SHARED.

**System events emessi automaticamente** da:
- `POST /api/customers` → "Cliente creato" con codice
- `POST /api/sites` → "Cantiere CANT-XXXX creato"
- `POST /api/quotes` (se customer_id valorizzato) → "Preventivo PRV-XXXX creato"

**RBAC**: `crm.customers.view` per leggere, `crm.customers.edit` per creare. In futuro potranno scrivere anche ruoli allargati (posatore/assistenza) mantenendo il tenant isolation.

### 3. Backend — Quote vincolato al Site

`backend/app/models_quote.py`: aggiunto `site_id: Optional[str]` a `Quote` e `QuoteCreate`.
`backend/app/routers/quotes.py`:
- Se `site_id` presente, valida che appartenga a `customer_id` e allo stesso tenant → 400 altrimenti
- `site_id` richiede `customer_id`
- `site_address` pre-compilato dal cantiere se non passato
- Gate `MISSING_CUSTOMER_TAX_CODE` inserito in `POST /quotes/{id}/convert-to-contract` (NON su create/PDF)

### 4. Frontend — UI

**CustomersPage** (`frontend/src/pages/CustomersPage.jsx`):
- Nuova colonna `N° Cliente` (CLI-000###), badge Privato/Azienda/Da confermare
- Ricerca su numero/nome/azienda/P.IVA/CF/email

**NewCustomerDialog** (`frontend/src/components/customers/NewCustomerDialog.jsx`):
- Tabs Privato/Azienda con campi condizionali
- PRIVATE: nome/cognome (req) + email/telefono/CF (opzionali) + residenza
- COMPANY: ragione sociale (req) + P.IVA/CF/PEC/SDI + referente strutturato + sede legale

**CustomerDetailPage** (5 tabs):
- **Panoramica**: sintesi (codice, tipo, denominazione, contatti, indirizzo, n. cantieri, ultimo aggiornamento) + ultime 5 attività
- **Anagrafica**: dettagli completi + edit (auto-open per legacy TO_CONFIRM)
- **Cantieri**: CRUD via `SitesTab.jsx` — card con badge tipologia/piano/ascensore + edit + archive
- **Timeline**: `CustomerTimelineTab.jsx` — form crea evento (categoria+canale+cantiere opz.) + cronologia con colore per categoria + badge SYSTEM per read-only
- **Preventivi**: `CustomerQuotesTab.jsx` — lista + creazione con select Cantiere obbligatorio (warning se nessun cantiere)

**Banner legacy TO_CONFIRM**: pannello ambra sopra la pagina + auto-apertura del dialog edit.

**QuotesPage** (`frontend/src/pages/QuotesPage.jsx`):
- Modal Nuovo Preventivo: **Cliente obbligatorio → Cantiere del cliente obbligatorio** (Select disabled finché cliente non scelto)
- Se il cliente non ha cantieri, warning giallo con CTA "Vai al cliente"
- Submit disabled finché entrambi non compilati

### 5. Schema DB nuovi/estesi

| Collection | Campi nuovi / estesi |
|---|---|
| `customers` | `customer_number`, `customer_type ∈ {PRIVATE,COMPANY,TO_CONFIRM}`, `contact_person{}`, `pec`, `sdi_code`. Legacy `private`/`business` restano leggibili grazie a `normalize_customer_type`. |
| `sequences` | Nuova key `customer` (prefix `CLI-`, padding 6, year_reset=false) creata al primo POST /customers |
| `sites` | Immutato (Part 1). Ora genera SYSTEM event su create. |
| `customer_timeline` | **Nuova collection**: `_id, tenant_id, customer_id, site_id?, category, channel?, title?, body, created_by_user_id/name/role, created_at, visibility, event_source, deleted_at?` |
| `quotes` | Nuovo `site_id` opzionale (validato contro customer_id). |

### 6. Test E2E — Iter29 (testing_agent_v3_fork)

- **Backend pytest**: 15/15 passing
- **Frontend happy-path desktop 1440x900**: PASS
- **Frontend happy-path mobile 390x844**: PASS

Casi verificati:
1. PRIVATE creation → `CLI-000006`, redirect a `/customers/:id`
2. COMPANY creation → `CLI-000007` con contact_person strutturato
3. Validation 400: `PRIVATE_REQUIRES_NAME`, `COMPANY_REQUIRES_NAME`, `CUSTOMER_TYPE_REQUIRED` (patch legacy)
4. Progressivo strettamente crescente e continuo
5. `GET /customers` normalizza `customer_type`
6. Site create → SYSTEM event in timeline
7. Timeline POST CALL/PHONE → visibile in cronologia con badge
8. `SYSTEM_EVENT_READONLY` (400) + `INVALID_CATEGORY` (400)
9. Quote create con site_id di altro cliente → 400 "Cantiere non valido"
10. UI: 5 tab, badge, cronologia, creazione preventivo vincolato
11. Mobile: creazione cliente + cantiere + timeline + preventivo tutti raggiungibili

### 7. Vincoli rispettati

- ✅ Nessuna modifica a: pricing V3, commercial_perimeter, product catalog, formule, listini, PDF, produzione, contratti (a parte gate isolato in convert-to-contract)
- ✅ Backward compatible: clienti storici visibili come `TO_CONFIRM` con banner + edit forzato
- ✅ Tenant isolation su tutti gli endpoint
- ✅ `MISSING_CUSTOMER_TAX_CODE` isolato tramite validator riutilizzabile, invocato solo in convert-to-contract
- ✅ Progressivo `CLI-` continuo (no reset annuale) e atomico

### 8. Known issues / debiti tecnici

- Nessuno rilevato in questa milestone.
- Debito M0 immutato: `2.10 €/ml` placeholder per `GLAZING_BEAD_PROEVOLUTION` (fuori scope M1).

### 9. STOP

**Milestone 1 completa.** L'utente può ora percorrere l'intero flusso dalla UI:
`Cliente (Privato/Azienda) → Cantiere → Timeline → Nuovo Preventivo (vincolato al Cantiere)`.

**In attesa del collaudo manuale dell'utente prima di iniziare la Milestone 2.**
