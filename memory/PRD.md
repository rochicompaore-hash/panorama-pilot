# Infissi Express Cloud — PRD & Roadmap

## Original problem
ERP verticale per aziende di serramenti. Copertura end-to-end: Lead → Preventivo → Contratto → Rilievo → Produzione → Posa → Assistenza. Multi-tenant ready, API-first, RBAC granulare.

## Architecture
- Backend: FastAPI + MongoDB (Motor async). Pydantic v2, BaseDoc con `version:int=1`, tenant_id obbligatorio, audit append-only.
- Frontend: React 19 + Tailwind + shadcn/ui + Zustand + React Query + i18next (IT).
- Auth: JWT access+refresh, RBAC (`*` wildcard superadmin), ABAC-ready.

## Milestones status
- **M1 Fondazioni** ✅ (auth, ruoli, permessi, audit, allegati S3, notifiche, ricerca, numerazioni).
- **M2 CRM** ✅ (leads/customers/contacts, pipeline, timeline, dashboard, WhatsApp/Email log).
- **M3.1 Preventivatore** ✅ (Quote/Opening/Line, price engine base, approval flow, revisioni, conversione contratto).
- **M3.2 Configuratori + Live Pricing** ✅ (this iteration)
  - Optimistic Concurrency Control (version + If-Match, 409 modal, force override + reason)
  - Motore formule sicuro (AST whitelist, no eval)
  - Motore condizioni dichiarativo (eq/neq/in/nin/exists/truthy/falsy/gte/lte)
  - Listini + regole (11 regole Infissi seed)
  - Configuratore guidato wizard + modalità avanzata (accordion)
  - Live pricing debounced 450ms, out-of-order guard, cancel previous request
  - Breakdown trasparente per riga + costi/margini gated by permission
  - Snapshot listino su invio preventivo (per riproducibilità)
  - Prodotti seed: Finestra PVC, Alluminio, Tapparella, Zanzariera, Persiana, Cassonetto
- **M3.3 PDF + Firma + Contratti** 🟡 (parziale — contratti CRUD OK, PDF/firma da fare)
- M4..M10 pianificate

## Regole economiche seed (11)
- Colori: avorio massa +8%, film ext/int +14.5%, film both +16%, film int-only +16%, film diff +22% e +€150 fisso
- Tapparella RAL +8%, effetto legno/metallizzata +30%, abbinata a serramento -30%
- Motorizzazione: meccanica +€180, radio +€260

## Concorrenza — entità protette
`quotes`, `quote_openings`, `quote_lines`, `contracts`, `pricelists`, `price_rules`, `products`, `customers`, `leads`, `contacts`.

Non-versionate (append-only): `audit_logs`, `notifications`, timeline `activities`, email/WA log.

## Test coverage
- iteration_5.json: 22/22 backend PASS, frontend E2E 100%.

## Backlog residuo
- P0: Auto-save preventivo con indicator "salvato"
- P0: Badge "Risparmio vs listino" (permission-gated)
- P0: Prezzo formule con base cost / margin flow completo
- P1: M3.3 PDF preventivo + Firma FES canvas + Contratti finalizzati
- P1: M4 Rilievo tecnico + blocco misure
- P1: Multi-azienda operativa (feature flag)
- P2: Portale posatore PWA
- P2: Simulatore marginalità what-if
- P2: Event bus interno per notifiche/audit disaccoppiati

## Test credentials
Vedi `/app/memory/test_credentials.md`.

## Iteration 6 (2026-02) — Correzione economica + Autosalvataggio
### Fix ambiguità applicazione regole
- Campi espliciti su PriceRuleV2:
  - `application_scope`: unit | line | opening | quote (default unit)
  - `apply_before_quantity` (default true; scope=unit)
  - `once_per_line` (default false; se true su fixed+unit → deferimento a line)
- Motore pricing_v2 rifatto in 3 passi: (1) unit rules → (2) quantity mult → (3) line/once-per-line rules
- Migrate DB one-shot: `COLOR_FILM_DIFF_FIXED`, `ROLLER_MOTOR_MECHANICAL`, `ROLLER_MOTOR_RADIO` → scope=line
- Breakdown v2: ogni entry ha `scope`, `unit_before/after`, `line_before/after`, `per_piece`
- Response arricchita: `unit_price_pre_qty` (per pezzo prima quantità) + `unit_price_final` (per pezzo effettivo = subtotale/qty)

### Verifica economica
| Qty | Base unit | +22% unit | €150 (line) | Subtotale | Precedente (buggy) |
|-----|-----------|-----------|-------------|-----------|--------------------|
| 1 | 806,40 | 177,41 | 150,00 (×1) | 1.133,81 | 1.133,81 |
| 2 | 806,40 | 177,41 | 150,00 (×1) | **2.117,62** | 2.267,62 ❌ |
| 5 | 806,40 | 177,41 | 150,00 (×1) | **5.069,05** | 5.669,05 ❌ |

### Autosalvataggio (M3.3.1)
- Endpoint `POST /api/quotes/{id}/autosave` (whitelist campi, version check, blocco consolidati)
- Hook `useAutosave`: debounce 800ms, AbortController, request_id out-of-order guard, beforeunload guard
- `AutosaveIndicator`: 6 stati (idle/dirty/saving/saved/error/conflict) + retry manuale
- Integrato: title (inline editable), notes, payment_terms, delivery_days, warranty_months, valid_until, internal_notes
- Auto-flush prima di azioni critiche (invia, revise, converti)

### Test coverage
- `tests/test_pricing_scope.py`: 10/10 (qty 1/2/5, deterministic order, once_per_line, min_billable, scope line/unit)
- iteration_6.json: backend 22/22 · frontend Playwright 100%

## Backlog M3.3 residuo (ordine confermato)
- P0: PDF professionale con snapshot revisione (template configurabile)
- P0: Link pubblico read-only sicuro (token high-entropy, hash, scadenza, rate limit)
- P0: Firma elettronica canvas legata a hash+revisione
- P0: Azioni portale cliente: Accetta&Firma / Richiedi modifica / Rifiuta (con motivazione configurabile)
- P0: Conversione contratto idempotente con snapshot completo
- P1: Badge risparmio (solo con snapshot valido)
- P1: KPI dashboard preventivi (conversion, avg deal, WoW)
- P2: Template Excel import listini

## Iteration 7 (2026-02) — M3.3.2 PDF Professionale

### Backend
- **Modelli**: `Clause`, `QuoteTemplate`, `QuotePdf` (con snapshot_hash+pdf_hash), `PaymentTermsSchema` (rate strutturate), `Company` estesa (legal_name, commercial_name, PEC, IBAN, REA, certifications, colori, logo, signature, stamp).
- **Servizio** `pdf_renderer.py`: WeasyPrint HTML→PDF, `build_snapshot` (esclude internal_cost/margin), `compute_snapshot_hash` (esclude volatili → idempotenza), `validate_quote_for_definitive` (gate: lines, subtotal, cliente, site_address con check nested), `safe_filename` (regex whitelist + dedup R00).
- **Template HTML** `templates/quote_pdf.html`: A4, running header/footer, page-break, watermark BOZZA/SUPERATO, IVA multi-aliquota, badge OBBLIGATORIA sulle clausole, tabelle vani con codice/desc/misure, blocco firma cliente+azienda, disclaimer misure/immagini/privacy.
- **Router**: `/clauses` CRUD + versionamento (`clause_versions`), `/quote-templates` CRUD + versionamento, `/quotes/{id}/pdf/preview|generate` con validation gate e idempotency by snapshot_hash, `/quote-pdfs/{pid}/download|invalidate`, `/quotes/scan/pricing-scope-bug` read-only.
- **Seed**: 12 clausole standard (misure, posa, opere murarie, smaltimento, accessibilità, pagamenti 50/50, garanzia 24m, detrazioni, variazioni, annullamento, immagini, privacy) + template `IE_STANDARD_2026` con 8 sezioni.
- **Permessi nuovi**: `quotes.preview_pdf/generate_pdf/download_pdf/invalidate_pdf/manage_templates/manage_clauses`.
- **Indice Mongo**: `ux_pdf_idempotent` unique parziale su `(tenant_id, quote_id, snapshot_hash, kind)` con `kind=definitive, invalidated_at=null` → previene race parallel double-click.

### Frontend
- **/templates**: editor 6-tab (Generale, Stile, Sezioni, Pagamenti, Clausole, Campi azienda) con PATCH concurrency-safe.
- **/clauses**: libreria con filtro categoria, editor con versioning storico, badge Obbligatoria.
- **QuoteEditor**: dropdown "PDF" con Anteprima BOZZA / Emetti definitivo / Scarica ultimo. Card "PDF emessi" con storico + hash snapshot troncato.

### Test coverage (iteration_7)
- Backend 16/16 PASS + 1 xfail iniziale (poi fixato)
- Frontend Playwright 100%
- 3 minor fixati: `missing_site` validation, list endpoint no base64/no `_id` leak, unique index race protection.

### Rendering PDF verificato visualmente
PDF 4 pagine, header ripetuto "Infissi Express · Preventivo PREV-2026-01383-R00", cover con dati cliente/cantiere/riferimento, riepilogo oggetto, dettaglio prodotti per vano con codici V1/V2, riepilogo economico con IVA 10%+22% suddivisa, condizioni pagamento 50/50 con nota "Saldo dovuto ad avviso merce pronta", 12 clausole formattate con badge OBBLIGATORIA in rosso, disclaimer evidenziati, blocco firma cliente+azienda. Simboli €, accenti italiani e page counter "Pag. X di Y" correttamente renderizzati.

### Backlog M3.3 residuo (ordine)
- M3.3.3 Link pubblico read-only con token high-entropy + revoca + rate limit + audit accessi
- M3.3.4 Firma elettronica canvas legata a snapshot+revisione (FES)
- M3.3.5 Azioni portale cliente: Accetta&Firma / Richiedi modifica / Rifiuta con motivazione
- M3.3.6 Conversione contratto idempotente con snapshot completo
- P1: Badge risparmio, KPI dashboard preventivi
- P2: Import Excel listini

## Iteration 8-9 (2026-02) — M3.3.3 Link pubblico + Object Storage

### Storage migration (Emergent Object Storage)
- Nuovo servizio `services/object_storage.py`: init lazy con `EMERGENT_LLM_KEY`, retry+backoff, path deterministica `infissi-express/tenants/{tid}/quotes/{qid}/{revision}/{pdf_id}.pdf`.
- `pdf_router._generate_pdf` scrive su Emergent storage (nuovi PDF) con fallback base64 in caso di storage_unavailable.
- `_fetch_pdf_bytes` legge da storage prima, fallback base64 per PDF pre-migrazione.
- Documento MongoDB `quote_pdfs` conserva `storage_provider`, `storage_key`, `pdf_base64=None` per i nuovi.

### Modello token pubblico (`QuotePublicToken`)
Campi: `id, tenant_id, quote_id, quote_number, quote_revision, quote_pdf_id, snapshot_hash, token_hash (sha256), status (active|expired|revoked|invalidated|consumed|blocked), expires_at, revoked_at/by/reason, last_access_at, access_count, maximum_accesses, requires_otp, allowed_actions, invalidated_by_revision_id, metadata, version`.

Il raw token (43 char URL-safe, 256 bit entropia da `secrets.token_urlsafe(32)`) viene restituito **una sola volta** al momento della creazione. In DB solo `token_hash` (sha256). Nessun UUID interno usato come credenziale.

### Sessione pubblica
Non JWT internal reuse. Ogni request al portale è stateless: il token risolve tenant + quote + pdf; il rate limiter è per (IP, token_prefix). Non c'è sessione persistente.

### Strategia hashing
- Token → `hashlib.sha256(raw).hexdigest()` (deterministico, 64 char hex)
- IP → `sha256("iph:"+ip)[:16]` per logs (pseudonimizzazione)
- Nessun HMAC secret (il token stesso è random 256 bit, hash-only per look-up rapido con index B-tree)

### Endpoint pubblici (no auth)
- `GET /api/public/quotes/{token}` → DTO PublicQuoteResponse (nessun ID interno, no cost/margin)
- `GET /api/public/quotes/{token}/pdf` → stream con security headers

### Endpoint admin (tenant-scoped)
- `GET /api/quotes/{qid}/public-links` (mai token_hash o raw esposti)
- `POST /api/quotes/{qid}/public-links` (idempotente, guard: PDF definitivo esistente, quote current, non cancelled)
- `POST /api/quotes/{qid}/public-links/{tid}/revoke` (motivazione obbligatoria)
- `POST /api/quotes/{qid}/public-links/regenerate`
- `GET /api/quotes/{qid}/public-access-logs`

### Security headers portale pubblico
- `Cache-Control: private, no-store`
- `X-Content-Type-Options: nosniff`
- `X-Robots-Tag: noindex, nofollow, noarchive, nosnippet`
- `Referrer-Policy: no-referrer`
- `X-Frame-Options: SAMEORIGIN`
- Frontend `<meta name="robots" content="noindex, nofollow, noarchive, nosnippet">`

### Rate limiting
Token bucket in-memory `(IP, token_prefix)` → 30 req/min → 429. Nessun blocco permanente. Da migrare a Redis in produzione multi-nodo.

### Automatic invalidation
Su `POST /quotes/{id}/revise` chiamato `invalidate_tokens_for_previous_revisions` → tutti i token attivi delle revisioni precedenti passano a `status=invalidated`, `revocation_reason=superseded_by_new_revision`.

### Idempotenza
- Create link: se esiste token attivo per (quote, pdf, snapshot_hash) → torna `{idempotent_hit:true, raw_token:null}`.
- Il doppio click NON crea due token validi.
- `Rigenera link` esplicito revoca il precedente + crea nuovo.

### Isolamento tenant
- Nessun `tenant_id` accettato dal client pubblico.
- Risoluzione da `token_hash` → `tenant_id` interno.
- Cross-tenant test: token di A non può accedere a PDF di B (verificato).

### Compatibilità futura (M3.3.4-5)
`allowed_actions` supporta già: `view, download, request_changes, reject, accept, sign`. Attualmente attivi solo `view, download`.

### Access log tenant-scoped
Collection `public_access_log`, append-only, campi: `token_id, quote_id, revision, event, result, reason, ip_hash, user_agent, created_at, tenant_id`.
Eventi implementati: `link_opened, quote_viewed, pdf_opened, pdf_downloaded, token_expired, token_revoked, token_invalid, rate_limited`.
**Nessun raw token nei log** — solo `token_id` (UUID del record).

### Portale frontend (`/p/:token`)
- Isolato da app layout (nessun sidebar/menu interno)
- Mobile-responsive
- Alert espliciti: `Revisione superata` / `Preventivo scaduto`
- Download PDF + Apri PDF full-page
- Info commerciale + telefono/email
- Errori generici (`404 Link non disponibile`, `410 Documento non disponibile`, `429 Accessi eccessivi`) senza rivelare esistenza risorse

### Permessi nuovi
`quotes.public_link.create/view/revoke/regenerate/configure`, `quotes.public_access_logs.view`.

### Test coverage
- iteration_8: 17/18 backend PASS, frontend 100%. Bug HIGH rilevato (500 su valid_until datetime).
- iteration_9: fix HIGH validato (200 con is_expired computato), fix clipboard graceful validato, secondo minor `is_expired` naive datetime rilevato.
- Post-fix manuale: `is_expired: True` corretto per date passate anche naive.

### Backlog M3.3.4-6 (prossime milestone)
- **M3.3.4** Firma FES: canvas signature + hash chain (`quote_pdf_id + snapshot_hash + revision + firmatario_name + accepted_terms_version + timestamp + IP + user_agent + token_id`), PDF firmato archiviato in storage
- **M3.3.5** Azioni portale cliente: `POST /public/quotes/{token}/accept-sign|request-changes|reject` con motivazione configurabile (7 opzioni preset)
- **M3.3.6** Conversione contratto idempotente con snapshot + numerazione autonoma CTR-2026-
- **P1** Badge risparmio · KPI dashboard preventivi
- **M3.3.3.1** (nice-to-have) OTP email predisposto in `requires_otp` — provider mock, endpoint stub `POST /public/quotes/{token}/otp/request|verify`
