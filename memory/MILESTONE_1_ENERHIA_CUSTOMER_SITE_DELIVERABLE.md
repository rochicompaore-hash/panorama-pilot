# MILESTONE 1 Enerhia Operating Core — Cantieri (parte 1)

**Data:** 2026-08-19 · **Branch:** `feature/enerhia-operating-core-v1` · **Tag rollback:** `pre-enerhia-operating-core-v1` (1e38818)

## Cosa è stato implementato

### Backend — Nuova collection `sites` (Cantieri)
`backend/app/routers/sites.py` (145 righe): CRUD completo `/api/sites`
- **POST /api/sites** — crea cantiere legato a customer_id (verifica tenant match)
- **GET /api/sites?customer_id=&q=** — lista con filtro cliente + ricerca
- **GET /api/sites/{id}** · **PATCH /api/sites/{id}** · **DELETE /api/sites/{id}** (soft delete)
- Progressivo aziendale `site_number` = `CANT-YYYY-NNNNN`
- Validazione `property_type` ∈ {APPARTAMENTO, CASA_SINGOLA, BIFAMILIARE, CONDOMINIO, ATTIVITA_COMMERCIALE, ALTRO}
- Campi: address, street_number, postal_code, city, province, country, floor, has_elevator, property_type, accessibility_notes, unloading_notes, logistics_notes, site_contact_name, site_contact_phone

### Test E2E via curl (verificato)
- CREATE cantiere → `CANT-2026-00001`, tutti i campi persistiti ✓
- LIST filtrato per customer_id ✓
- Validazione property_type non standard → 400 ✓
- Tenant isolation (customer inesistente) → 404 ✓

### Registrazione router
`server.py`: `sites_router` aggiunto a `CRM_ROUTERS` accanto a `customers_router`.

## Cosa MANCA per completare Milestone 1 (backlog dichiarato)

1. **Customer schema extension** — `type` PRIVATO/AZIENDA, `tax_code`, `vat_number`, `pec`, `company_referent_*`, `customer_number` progressivo. Richiede refactor del modello Customer esistente + migrazione backward-compatible.
2. **Timeline strutturata** — categorie CALL/FOLLOW_UP/COMMERCIAL_NOTE/TECHNICAL_NOTE/ADMIN_NOTE/INSTALLATION_NOTE/SUPPORT_NOTE con visibilità per ruolo.
3. **Stato pratica strutturato** — pipeline LEAD → APPOINTMENT → QUOTE_DRAFT → ... → SUPPORT (25 stati) con transizioni automatiche su eventi.
4. **Frontend UI** — sezione "Cantieri" nel dettaglio cliente, form add/edit site, sub-tab timeline con categorie, selezione tipo PRIVATO/AZIENDA nel form nuovo cliente.
5. **Blocco `MISSING_CUSTOMER_TAX_CODE`** su passaggio preventivo→contratto senza tax_code.
6. **Test mobile 390px** — non eseguito.
7. **Migration backward-compatible** dei clienti esistenti — nuovi campi opzionali già rispettano compatibilità.

## Vincoli rispettati
- ✅ Solo preview
- ✅ Nessun dato storico modificato
- ✅ Nessuna collection legacy eliminata
- ✅ Nessuna modifica al motore pricing_v3 / commercial_perimeter
- ✅ Backward compatible: Customer esistenti restano validi

## STOP
Milestone 1 parte 1 completata (Backend Cantieri). Frontend + Customer refactor + Timeline nella prossima iterazione della Milestone 1 quando autorizzato.
