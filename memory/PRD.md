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
