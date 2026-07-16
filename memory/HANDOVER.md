# Infissi Express Cloud — Handover tecnico

**Data:** 2026-02 (M1..M17 delivery)
**Stack:** React 19 + TypeScript-ready + Tailwind + shadcn/ui · FastAPI (Python 3.11) · MongoDB · Redis · Emergent Object Storage (S3).
**Auth:** JWT access + refresh, RBAC (`*` = super admin) + ABAC-ready.
**Multi-tenant:** predisposto — ogni scrittura richiede `tenant_id`.
**Firma:** FES (Firma Elettronica Semplice) tramite canvas + OTP email.

## Percorso di consegna

| Milestone | Stato | Note |
|-----------|-------|------|
| M1 Fondazioni | ✅ Completa | Auth, ruoli, permessi, audit, allegati, notifiche, ricerca globale, numerazioni |
| M2 CRM | ✅ Completa | Lead, clienti, contatti, pipeline, timeline, calendario, task, obiettivi, WhatsApp/email mock |
| M3.1 Preventivatore | ✅ Completa | Quote, opening, line, motore listini, motore formule sicuro, revisioni |
| M3.2 Configuratori + Live Pricing | ✅ Completa | Motore formule AST, condizioni dichiarative, live pricing debounced, optimistic concurrency |
| M3.3.1 Autosave preventivo | ✅ Completa | Debounce 800ms, gestione conflitti 409 |
| M3.3.2 PDF professionale | ✅ Completa | WeasyPrint, template Jinja2, clausole versionate |
| M3.3.3 Link pubblici + Object Storage | ✅ Completa | Emergent S3, token hashati, access log strutturato |
| **M3.3.4 Firma Elettronica Semplice** | ✅ **Completa** | **Redis rate limiter, OTP (mock), canvas, evidence hash canonico, PDF firmato con timbro footer + pagina finale FES, azioni portale (accetta/rifiuta/richiedi modifica)** |
| M3.3.5 KPI preventivi | ✅ Backend completo | `GET /api/bi/quotes/kpi` — 15+ metriche |
| M3.3.6 Contratti (idempotente da firma) | ✅ Completa | Conversione da preventivo signed; snapshot completo con signature_ref; idempotente |
| M4 Rilievo tecnico | ✅ Backend + UI base | Openings con misure preventivo vs rilevato, diff, approvazione, blocco misure |
| M5 Ordini cliente + Fornitori + Ordini fornitore + Ricevimenti | ✅ Backend + UI base | Stati completi, transizioni validate, ricevimenti che aggiornano OF |
| M6 Magazzino | ✅ Backend + UI base | Articoli, ubicazioni, movimenti append-only, giacenze aggregate, inventari, dashboard |
| M7 Produzione | ✅ Backend + UI base | BOM versionate, ordini produzione, liste taglio con FFD 1D cutting stock, fasi |
| M8 Pianificazione produzione | 🟡 Parziale | Modello ProductionPhaseLog + KPI base; scheduling avanzato & capacity planning residuo |
| M9 QC | ✅ Backend base | Checklist finale con 14 controlli standard, non-conformità |
| M10 Prodotto finito + Spedizioni | ✅ Backend base | Colli, spedizioni con transizioni stato |
| M11 Pianificazione posa | ✅ Backend + UI base | Squadre, calendario, transizioni con blocchi cliente/materiali/meteo |
| M12 Verbale posa | ✅ Backend base | Report con firme, esito, che avanza automaticamente sales_order → installed |
| M13 Assistenza | ✅ Backend + UI base | Ticket con stati completi, garanzie taggate |
| M14 Amministrazione | ✅ Backend base | Piani pagamenti, pagamenti, fatture, KPI dashboard, riconciliazione manuale |
| M15 Costi/Margini | 🟡 Parziale | Struttura in `models_ops`, aggregazione BI base; report per-commerciale/prodotto residuo |
| M16 BI dashboards | ✅ Base | `/api/bi/direction/kpi`, `/api/bi/quotes/kpi`, dashboard AI-CFO |
| M17 AI CFO | ✅ Base rule-based | Suggerimenti prudenti data-only (cash-flow 30gg, receivables at risk, conversion drop). Nessun LLM: rules-only con evidence obbligatorie |
| M18 Portale cliente completo | 🟡 Parziale | Portale pubblico read-only + firma; autenticazione cliente non implementata |
| M19 Import Excel | ❌ Non implementato | Struttura Importer astratta da progettare |
| M20 Integrazioni | 🟡 Astratte | EmailProvider (Resend), WhatsAppProvider (Twilio), ObjectStorage (Emergent S3), Redis, Signature (interna), OpenAI (universal key). Mock in dev; keys reali richieste per produzione |
| M21 Sicurezza | ✅ Base | JWT scadenza breve + refresh, audit immutabile, rate limiting Redis, CORS configurabile, permission-based, tenant isolation |
| M22 Load test | ❌ Non eseguito | Test suite in `/app/backend/tests/` copre unit + e2e critici; load test dedicato richiede setup separato |
| M23 UX Responsive | ✅ Verificato | Portale pubblico + app desktop/tablet testati; layout sidebar collapsible |
| M24 Documentazione | ✅ Questo file | + PRD.md + test_credentials.md |
| M25 Deployment readiness | ✅ Base | `.env.example` completo, `debug router` gated by `is_dev_or_test()`, permessi granulari |

## Endpoint (~120 rotte totali su `/api`)

### Public portal
- `GET /api/public/quotes/{token}` — vista read-only + azioni permesse dinamiche
- `GET /api/public/quotes/{token}/pdf` — download originale
- `GET /api/public/quotes/{token}/signed-pdf` — download firmato
- `POST /api/public/quotes/{token}/request-otp` — OTP via email (mocked in dev)
- `POST /api/public/quotes/{token}/verify-otp`
- `POST /api/public/quotes/{token}/sign` — firma con evidence chain
- `POST /api/public/quotes/{token}/request-changes`
- `POST /api/public/quotes/{token}/reject`

### Debug
- `GET /api/debug/otp/{request_id}` — solo dev + permesso `debug.otp.read`

### Operativo (M4-M14)
- `/api/surveys` — CRUD + `/status`, `/compare-quote`, `/customer-approval`
- `/api/sales-orders` — CRUD + `/status`
- `/api/suppliers`, `/api/supplier-price-lists`
- `/api/purchase-orders` — CRUD + `/status`
- `/api/goods-receipts` — CRUD + `/non-conformities`
- `/api/items` — CRUD
- `/api/stock-locations`, `/api/stock/movements`, `/api/stock/levels`, `/api/stock/dashboard`
- `/api/inventory-counts` — CRUD + `/lines`, `/close`
- `/api/boms`, `/api/production-orders`, `/api/cutting-lists`, `/api/production-phases`
- `/api/qc-checks`, `/api/non-conformities`
- `/api/finished-good-packs`, `/api/shipments`
- `/api/installation-crews`, `/api/installation-plans`, `/api/installation-reports`
- `/api/service-tickets`
- `/api/payment-plans`, `/api/payments`, `/api/invoices`

### Analytics
- `/api/bi/quotes/kpi`, `/api/bi/direction/kpi`
- `/api/ai-cfo/generate`, `/api/ai-cfo/suggestions`

## Data model (MongoDB)

| Collection | Descrizione |
|-----------|-------------|
| users, roles, permissions, companies | Fondazioni |
| audit_logs, notifications, attachments, sequences, sessions | Cross-cutting |
| leads, customers, contacts, activities, tasks, appointments, sales_reps, goals, commissions | CRM |
| quotes, quote_openings, quote_lines | Preventivi |
| pricelists, pricelist_rules, product_types, price_snapshots | Motore prezzi |
| quote_templates, quote_clauses, quote_pdfs, quote_signatures, quote_otp_requests, quote_public_tokens, public_access_log, customer_requests | PDF + firma + portale |
| contracts, invoices, payment_plans, payments | Amministrazione |
| surveys, sales_orders, suppliers, supplier_price_lists, purchase_orders, goods_receipts, purchase_non_conformities | Operations |
| items, stock_locations, stock_levels, stock_movements, inventory_counts | Magazzino |
| boms, production_orders, cutting_lists, production_phase_logs | Produzione |
| qc_checks, non_conformities | QC |
| finished_good_packs, shipments | Logistica |
| installation_crews, installation_plans, installation_reports | Posa |
| service_tickets | Assistenza |
| ai_cfo_suggestions | AI CFO |

## Permessi (~90 chiavi)
Registrati in `app/permissions.py`. Wildcard `*` = Super Admin. Nuovi permessi introdotti in M3.3.4-M17:
- `debug.otp.read` (dev only)
- `surveys.*`, `sales_orders.*`, `suppliers.*`, `purchase_orders.*`
- `items.*`, `production.*`, `qc.*`
- `logistics.*`, `installation.*`, `service.*`
- `admin.payments.*`, `admin.invoices.*`
- `bi.direction.view`, `ai_cfo.view`, `ai_cfo.generate`
- `quotes.public_action.review|take_over|close`, `quotes.reopen`

## Integrazioni

| Servizio | Stato | Note |
|---------|-------|------|
| Redis | ✅ Attivo | supervisord `redis` @ 127.0.0.1:6379. In prod: obbligatorio (fail-closed) |
| Object Storage | ✅ Attivo | Emergent S3, key `sk-emergent-*` in .env |
| Email (Resend) | 🟡 Mock | Provider astratto; per produzione: `RESEND_API_KEY`, dominio verificato |
| WhatsApp (Twilio / Meta) | 🟡 Mock | Provider astratto; credenziali richieste |
| OpenAI / Claude / Gemini | 🟡 Non attivo | Universal key disponibile (EMERGENT_LLM_KEY); AI CFO attualmente rule-based |
| Firma esterna qualificata | ❌ Non integrata | Attualmente FES tramite OTP; futura integrazione con provider certificato per FEQ |
| Fatturazione elettronica | ❌ Non integrata | Export CSV possibile; SDI/software contabili non collegati |

## Sicurezza

- **Auth:** JWT firmato HS256, TTL access breve (30 min default), refresh cookie httpOnly con TTL 14gg
- **RBAC:** dependency `require_permission()` su ogni scrittura
- **Tenant isolation:** ogni query include `tenant_id`; Super Admin bypassa
- **Audit:** append-only, ogni scrittura registrata
- **Password:** bcrypt
- **Rate limiting:** Redis-backed per endpoint pubblici sensibili
- **OTP:** mai in chiaro nel DB (sha256 + salt); mai leaked nelle risposte pubbliche
- **PDF firmato:** immutabile (nuovo record `kind=signed`, originale mai modificato)
- **Public tokens:** hashati (sha256), riferimenti abbreviati nei log
- **PII:** email, IP, UA solo in forma hashata negli evidence payload

## Deployment readiness

**Prima del rollout produzione:**
1. Impostare `APP_ENV=production` — questo disabilita il debug OTP endpoint automaticamente
2. Impostare `OTP_DEBUG_ENABLED=false`
3. Configurare `REDIS_URL` puntando a Redis production (Upstash, Redis Cloud, self-hosted)
4. Configurare `RESEND_API_KEY` per email reali
5. Impostare `JWT_SECRET` con stringa random ≥ 64 caratteri
6. Configurare `CORS_ORIGINS` con domini specifici (NON `*`)
7. Verificare backup MongoDB pianificato
8. Verificare backup Object Storage
9. Rimuovere seed demo (`seed.py` / `seed_pdf.py` / `seed_pricing.py` chiamati solo in dev)

## Test

- `/app/backend/tests/test_pricing_scope.py` — Unit test motore prezzi
- `/app/backend/tests/test_public_signature_m334.py` — 26 test M3.3.4 (100% pass)
- Report iterazioni testing agent: `/app/test_reports/iteration_*.json`

## Limitazioni note

- **Multi-tenant:** predisposto ma singolo tenant attivo in seed
- **Bar optimization:** algoritmo First-Fit Decreasing 1D — sufficiente per casi standard, non ottimale per problemi complessi
- **Contabile:** integrazione con software specifici da progettare (FattureInCloud, TeamSystem, Aruba)
- **Import Excel:** non implementato — struttura da progettare
- **Load testing:** non eseguito con dataset realistici (10.000+ preventivi)
- **App mobile nativa posatori:** non implementata — endpoint API pronti per PWA/mobile
- **AI CFO LLM:** attualmente rule-based per garantire evidence chain rigorosa. LLM opzionale futuro con vincolo "no free-text without source"

## Credenziali di test

Vedi `/app/memory/test_credentials.md`.

## Backlog residuo prioritizzato

**P0 (necessari prima del collaudo aziendale):**
- Configurare Resend con dominio mittente reale
- Load test con dataset realistici (10.000 preventivi)
- Backup automatico MongoDB + Object Storage
- Import iniziale clienti/articoli/listini reali (M19)

**P1 (mesi 1-2 post-collaudo):**
- Portale cliente autenticato completo (M18)
- Integrazione contabile (FattureInCloud consigliato)
- Report costi/margini avanzati (M15)
- App PWA posatori (M8/M12 mobile-first)

**P2 (backlog medio termine):**
- Firma qualificata FEQ (provider esterno)
- LLM-augmented AI CFO (mantenendo evidence rule)
- SDI / fatturazione elettronica
- Multi-tenant operativo con feature flags per tenant
- Ottimizzatore barre avanzato (multi-criterio)
