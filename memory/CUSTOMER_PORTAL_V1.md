# CUSTOMER_PORTAL_V1 — STATO E PIANO ESECUTIVO (handoff operativo)

**Stato**: NOT STARTED (autorizzato dal PO msg 406 come unico modulo fuori freeze). Questo file è il piano "understand once" per il prossimo ciclo: partire da qui senza ri-esplorare.

## Riuso obbligatorio (già esistente in Panorama)
- Entità: `customers`, `sites`, `quotes` (+ `quote_pdfs` con `download` endpoint `GET /api/quote-pdfs/{pid}/download`), `contracts` (+ signature OTP, `contract_pdf`), `surveys`, `sales_orders`, `production`, `installations/logistics`, `service_tickets`, `documents`/`storage.py` (S3/local), `email_service.enqueue_email` + `email_logs`, `audit`.
- Auth pattern: `app/routers/auth.py` (JWT + cookie, `create_login_session`, `_set_auth_cookies`), `app/deps.py` (`get_current_user`, `require_permission`). Google: `POST /api/auth/google/session` (fail-closed).

## Lotto 1 — AUTH + ISOLATION (prima di tutto)
- Collezione `customer_portal_users` {tenant_id, customer_id|null, email(norm), phone, first_name, last_name, fiscal_code(norm upper), password_hash, status: REGISTERED|EMAIL_TO_VERIFY|PENDING_AUTHORIZATION|AUTHORIZED|SUSPENDED, email_verified_at, invited_by, created_at}.
- JWT separato: claim `aud="customer_portal"`, `sub=customer_user_id`, `tenant_id`; dependency `get_current_customer()` che rifiuta token dipendenti (aud diversa) e utenti non AUTHORIZED. **Chiamare integration_expert (JWT auth) prima di scrivere il codice auth.**
- Endpoint `/api/customer-portal/auth/{register,login,verify-email,forgot,reset}`; admin `/api/admin/customer-portal/{users,link,authorize,suspend,resend,reset}` (permesso `customer_portal.manage`).
- Matching proposto all'admin (mai automatico): CF → email → telefono → nome+cognome+indirizzo su `customers` del tenant.
- Scope query: ogni endpoint filtra `{tenant_id, customer_id}` server-side; ID sconosciuti → 404 (mai 403 con payload).
- Test: `tests/test_customer_portal_auth_isolation.py` (Customer A/B: quotes, contracts, sites, documents, tickets, jobs con ID diretti → 404; leak keys: supply_cost, internal_reference_price, financial_snapshot, commission*, pre_commission_margin, internal_cost, technical_snapshot, notes interne).

## Lotto 2 — JOB VIEW + TIMELINE
- `GET /api/customer-portal/jobs` e `/jobs/{id}`: aggregato per contratto (o quote accepted): numero, cantiere, data, importo totale cliente (solo `total`), `customer_status`, `progress_pct`, `next_step`, appuntamenti (survey/installation date), documenti, ENEA, ticket.
- Mapping `INTERNAL_STATUS → CUSTOMER_STATUS` in `app/services/customer_status_map.py` (config dict, 20 step PO): contract signed → attesa acconto → pagamento ricevuto → rilievo (da programmare/programmato/eseguito/confermato) → ordine confermato → produzione → QC → merce pronta/saldo richiesto → saldo ricevuto → montaggio (da programmare/programmato/eseguito) → collaudo → ENEA (se prevista) → garanzia. Step non applicabili omessi.
- Nessuna scrittura da parte del cliente; stati letti da quotes/contracts/surveys/production/installations/payment_schedule.

## Lotto 3/4 — DOCUMENTI + LIBRERIA TECNICA
- Aggiungere ai documenti esistenti (`quote_pdfs`, `contract_pdfs`, `documents`) i campi `customer_visible` (bool), `customer_visible_from`, `document_category` (PREVENTIVO, CONTRATTO, RILIEVO_TECNICO, ORDINE, VERBALE_MONTAGGIO, COLLAUDO, ENEA, CERTIFICAZIONE_TERMICA, CE_CERTIFICATION, TECHNICAL_DATA_SHEET, USE_AND_MAINTENANCE_MANUAL, WARRANTY, GLASS_DOCUMENTATION, ALTRO). Policy automatica: PDF preventivo definitivo/contratto firmato/rilievo validato/verbale montaggio → `customer_visible=true`.
- `product_document_library` {tenant_id, product_id|system_code, category, version, validity, storage_key} referenziata (no copie) → pubblicazione per i prodotti realmente presenti nelle righe del contratto.
- `GET /api/customer-portal/documents?job_id=` + `GET /documents/{id}/download` (stream da storage, audit `customer.document_download`).

## Lotto 5 — ENEA: stato pratica da `quotes.enea_practice_code` + `enea_status` (DA_AVVIARE, DOCUMENTI_DA_RACCOGLIERE, IN_PREPARAZIONE, INVIATA, COMPLETATA) + documenti categoria ENEA/certificazioni.
## Lotto 6 — ASSISTENZA: riuso `service_tickets` con `customer_visible` per messaggi (`customer_message` vs `internal_note`), categorie configurabili, allegati via storage (limiti tipo/size), stati cliente RICEVUTO→IN_VALUTAZIONE→DA_PROGRAMMARE→PROGRAMMATO→RISOLTO→CHIUSO.
## Lotto 7 — NOTIFICHE: `customer_communication_log` {customer_id, job_id, channel=EMAIL, event, recipient, sent_at, provider_message_id, delivery_status, error}; trigger su cambio stato (hook nei router production/installation/payments) via `enqueue_email` template `CUSTOMER_*`. **Dipende dal provider email reale (vedi blocker).**
## Frontend: route `/customer-portal/*` con layout mobile-first separato (bottom nav HOME · IL MIO ORDINE · DOCUMENTI · ENEA · ASSISTENZA · PROFILO), nessuna sidebar ERP; token cliente in storage separato (`cp_access_token`).

## BLOCKER REALI (aperti, servono decisioni/accessi PO)
1. **EMAIL**: `.env` → `EMAIL_PROVIDER=mock`, `MAIL_DELIVERY_MODE=test`, `MAIL_TEST_REDIRECT_TO=pilot@panoramapilot.com`, `MAIL_PASSWORD` assente. Il test reale restituisce `configuration_required / SMTP_NOT_CONFIGURED`. Serve: credenziali SMTP (MAIL_PASSWORD) **oppure** `EMAIL_PROVIDER=resend` + `RESEND_API_KEY` valida nei secrets backend, e `MAIL_DELIVERY_MODE=live`. Senza, nessuna notifica/verifica email cliente può essere validata.
2. **GOOGLE DRIVE**: accesso negato (401/Sign-in). Serve **service account JSON** (Drive API, scope `drive.readonly`) con la cartella condivisa in lettura con l'email del service account; il file va messo nei secrets backend (`GOOGLE_SA_JSON` o path), mai nel frontend/report.
3. **GOOGLE LOGIN**: test browser reale con account `rochicompaore@gmail.com` da eseguire dal PO (automation non può completare OAuth Google).
