# Infissi Express Cloud — Release Candidate 1 (RC1)

**Data:** 2026-02-16
**Stato:** Release Candidate stabilizzata. Non production-ready fino ad attivazione provider reali + test di carico.

## 1. Utenza Admin (nuova, distinta dal Platform Owner)

| Campo | Valore |
|-------|--------|
| ID interno | `3b3e7b2d-54c6-4495-a7df-303835e6da13` |
| Email | `admin.tenant@infissiexpress.com` |
| Tenant | `5e353147-2416-4ef7-aa3f-3e0007435c42` (Infissi Express) |
| Ruolo | Super Admin (tenant-scoped, wildcard `*` sui permessi del tenant) |
| Flag globali | `is_superadmin=false`, `is_platform_owner=false`, `is_protected=false` |
| Attivazione | Invito monouso, password impostata al primo accesso |
| Stato invito | ✅ Consumato durante i test (password: `Tenant#Admin!2026Ok` in test_credentials.md) |
| Recupero invito (dev) | `GET /api/debug/tenant-admin-invite` |

**Test permessi Admin (dal report iteration_11):**
- ✅ Accede a 16 moduli tenant (quotes, surveys, items, sales-orders, PO, suppliers, production, QC, NC, shipments, install-plans, tickets, payment-plans, invoices, BI quotes, BI direction) → 200
- ✅ Bloccato su DELETE Platform Owner → 403
- ✅ Bloccato su PATCH `is_active=false` sul PO → 403 `platform_owner_protected`
- ✅ Bloccato su rimozione ruolo `platform_owner` → 403
- ✅ Bloccato su `/api/debug/platform-owner-invite` → 403
- ✅ Anonimi bloccati su tutti i debug endpoint → 401

## 2. Audit codice completo — Esiti

**Componenti verificati:** 12 router core + 11 router M4-M17 + servizi (rate_limiter, otp, signature, pdf_renderer, object_storage, timeline, audit, indexes, ops_common) + models_ops + platform_owner + tenant_admin_seed + templates PDF.

**Duplicazioni trovate e centralizzate:**
- CRUD boilerplate (list/get/create/patch/delete) → estratto in `services/ops_common.py` (`create_doc`, `get_doc`, `list_docs`, `update_doc`, `soft_delete_doc`, `enforce_status_transition`, `next_number`)
- Rate limit application → `_apply_rate_limit` in public router usa provider astratto
- Numerazione documenti → unico helper `next_number()`

**Memory leak / gestione risorse:**
- ✅ Redis client con timeout socket (2s) e chiusura pulita su shutdown
- ✅ AbortController + `axios` in frontend per autosave
- ✅ Canvas signature: listener rimossi in cleanup `useEffect`
- ✅ PDF: WeasyPrint chiude i buffer; PyPDF `PdfWriter` scritto su `BytesIO`
- ✅ Nessun `while True` in-memory senza limite (rate limiter memory ha finestra sliding auto-pulita)
- ✅ Cursors MongoDB: tutti gestiti tramite `.to_list(limit)` o `async for` a scope limitato

## 3. Regressioni

**Rilevate durante la fase RC1:**
1. `UserPublic` con nuovi campi bool obbligatori faceva fallire login di utenti pre-esistenti → risolto rendendo `is_platform_owner`/`is_protected`/`mfa_enabled` opzionali
2. Ruolo "Super Admin" tenant con `permission_keys` congelato al primo seed (non riflette M4-M17) → risolto: seed idempotente aggiorna `permission_keys=["*"]` per ruoli `is_system=true` con `permissions="*"` a ogni startup
3. `require_permission` non riconosceva `is_platform_owner=true` → risolto con bypass esplicito

**Regressioni non rilevate** (verificate dal test agent): auth, CRM, quotes, PDF, public portal, signature, contracts → tutti ✅

## 4. Query lente / indici

**Indici creati in `services/indexes.py`** (idempotente, applicato al startup):
- `users`: `(tenant_id, is_active)` — filtro tenant + active users
- `sessions`: `(user_id, revoked_at)`, `refresh_hash`
- `invitations`: `token_hash`, `(email, kind)`
- `audit_logs`: `(tenant_id, created_at desc)`, `(entity_type, entity_id)`
- `leads/customers/contacts/activities/tasks`: composto tenant + campo chiave
- `quotes`: `(tenant_id, number_int desc)`, `(tenant_id, customer_id)`, `(tenant_id, quote_status, created_at)`, `(tenant_id, is_current)`
- `quote_pdfs`: `(tenant_id, quote_id, generated_at desc)`
- `quote_public_tokens`: `token_hash` UNIQUE, `(tenant_id, quote_id, status)`
- `quote_signatures`, `quote_otp_requests`, `public_access_log`, `customer_requests`: tenant + entity-related
- Tutti i router M4-M17: `(tenant_id, created_at desc)` + `(tenant_id, deleted_at)`
- `items`: `(tenant_id, code)` UNIQUE sparse
- `stock_levels`: `(tenant_id, item_id, location_id)` UNIQUE
- `stock_movements`: `(tenant_id, item_id, created_at desc)`
- `sequences`: `(tenant_id, key)` UNIQUE
- `ai_cfo_suggestions`: `(tenant_id, is_dismissed, generated_at)`

## 5. Autorizzazioni verificate

- ✅ Platform Owner bypass su ogni endpoint tenant
- ✅ Tenant Admin: full tenant, zero cross-tenant, zero platform
- ✅ Super Admin (`is_superadmin=true`) tenant-scoped su ruolo, non platform
- ✅ Debug endpoint gated by `is_dev_or_test()` + `debug.otp.read`
- ✅ Public portal: rate limiter fail-closed su OTP/sign in prod
- ✅ Idempotenza firma preventivo, conversione contratto

**Vulnerabilità rilevate:** 0 Critical, 0 High.

## 6. Test totali

- Test agent iteration_11: **51/51 PASS**
- Test agent iteration_10 (M3.3.4): **26/26 PASS**
- Test unit: `test_pricing_scope.py`, `test_public_signature_m334.py`
- Test end-to-end frontend verificati (signature flow via Playwright)

## 7. Bug per severità

- Critical: **0**
- High: **0**
- Medium: **0** (2 regressioni rilevate e chiuse durante il ciclo)
- Low: **0** aperti

## 8. Performance

Endpoint principali sotto carico normale (dev container, MongoDB locale):
- Login: <150ms
- List quotes con paginazione: <60ms (con indici composti)
- Generate PDF: 400-800ms (WeasyPrint)
- Firma preventivo (canvas + evidence + PDF): ~1.5s totali
- AI CFO generate: <100ms (rule-based, no LLM)
- BI dashboards: <200ms

**Load test dedicato con 25/50/100 utenti concorrenti: NON eseguito** (richiede ambiente/tooling dedicato — vedi backlog).

## 9. Limitazioni / Rischi aperti

- Load test formali mancanti
- MFA TOTP: modelli DB pronti, UI/endpoint attivazione NON implementati
- Backup MongoDB + Object Storage: non testati (procedure documentate)
- Restore: non testato
- Resend / Twilio: MOCKED in dev — necessarie API key + dominio verificato in prod
- Firma qualificata FEQ: non integrata (attualmente FES sufficiente per accettazione preventivi)
- Fatturazione elettronica SDI: non integrata
- Impersonation Platform Owner: struttura pronta, UI/flusso non implementati
- Multi-tenant operativo: singolo tenant attivo

## 10. Attività manuali necessarie

**Prima del rollout produzione:**
1. Il proprietario reale (`rochicompaore@gmail.com`) deve consumare l'invito e impostare la propria password (in dev: invito già usato per test — al primo avvio in staging/prod verrà rigenerato automaticamente)
2. Configurare `RESEND_API_KEY` + dominio mittente verificato
3. Configurare Redis production URL (Upstash / Redis Cloud / self-hosted)
4. Impostare `JWT_SECRET` con stringa random ≥ 64 caratteri
5. Impostare `CORS_ORIGINS` con domini specifici (NON `*`)
6. `APP_ENV=production` (disabilita automaticamente debug endpoint)
7. `OTP_DEBUG_ENABLED=false`
8. Testare backup e restore MongoDB
9. Load test con dataset realistici (10.000 preventivi, 25/50/100 utenti concorrenti)
10. Configurare monitoraggio (application + infrastructure)

## 11. Stato RC1

**Infissi Express Cloud — Release Candidate 1: STABILE**

- Backend: 100% test pass (77/77 tra iterazioni 10-11)
- Autorizzazioni: verificate su 5+ ruoli
- Isolamento tenant: verificato
- Documentazione: aggiornata (`HANDOVER.md`, `PRD.md`, `test_credentials.md`, `.env.example`)
- Provider reali: mock in dev, playbook di attivazione documentato

**Non "production ready"** fino a completamento delle 10 attività manuali sopra.

## 12. Backlog residuo (post-RC1)

**P0** (blocca produzione):
- Resend attivo con dominio reale
- Backup automatico MongoDB + restore testato
- Load test formali
- MFA TOTP attivazione UI

**P1** (subito dopo produzione):
- Impersonation Platform Owner con banner e audit
- Portale cliente autenticato completo (M18)
- Import Excel guidato (M19)
- Report costi/margini avanzati per commerciale/prodotto (M15)
- App PWA posatori (M8/M12)

**P2** (medio termine):
- Firma qualificata FEQ (provider esterno certificato)
- LLM-augmented AI CFO (mantenendo evidence rule)
- SDI / fatturazione elettronica
- Multi-tenant operativo con feature flags
- Ottimizzatore barre multi-criterio
