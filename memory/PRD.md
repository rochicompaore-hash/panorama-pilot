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
