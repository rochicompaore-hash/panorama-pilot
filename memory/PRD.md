# Infissi Express Cloud — PRD

## Original Problem Statement
Piattaforma SaaS cloud (Web based App, responsive) per la gestione end-to-end del ciclo di vita commerciale, tecnico, produttivo e post-vendita di un'azienda produttrice e installatrice di infissi. ERP verticale (M1-M10).

## Milestone 1 (Full) — Implemented
- Auth custom email/password + refresh token rotation, session revocation, brute-force lock
- Password reset via email token, invitation acceptance, must_change_password flow
- Users CRUD (create/invite/deactivate/unlock/resend), Roles CRUD (system + custom), Permissions matrix (28 keys)
- Multi-tenant scaffolding (`tenant_id` = `company_id` on every entity)
- Company settings (anagrafica, logo URL, locale/currency/timezone)
- Audit log append-only + viewer with filters
- Attachments: upload/list/download/delete, S3-compatible provider (local dev, S3 ready)
- Progressive numerations (sequences) with year_reset + next atomic generator
- Global search across users/roles/attachments/sequences/audit
- Notifications (in-app), Sessions management, Email logs viewer
- Dashboard with counters + recent activity + recent users
- i18n predisposed (italiano attivo)
- 20+ data-testid coverage for automated testing

## Architecture
- Backend: FastAPI + Motor (MongoDB) + PyJWT + bcrypt, modular routers under `/api`
- Frontend: React 19 + Tailwind + Shadcn/UI + react-i18next + Zustand-ready + React Query
- Storage: Local dev, S3-compatible provider abstraction ready for Emergent Object Storage
- Email: Mock provider (dev), Resend provider stub for prod (behind interface)

## User Personas
- Super Admin (system-wide)
- Admin Azienda (tenant-wide, full)
- Commerciale, Tecnico Rilievo, Produzione, Magazzino, Posatore, Amministrazione, Cliente, Viewer

## Roadmap (Backlog)
- M2: CRM, lead, clienti, calendario, comunicazioni email/WhatsApp
- M3: Preventivatore + configuratori + PDF + contratti + firma
- M4: Rilievo tecnico + ordine esecutivo
- M5: Ordini fornitore, acquisti, magazzino base
- M6-M10: produzione, QC, posa, assistenza, BI, AI CFO

## What's implemented (2026-07-15)
Full Milestone 1 as above, italiano UI, admin seed + credentials in `/app/memory/test_credentials.md`.

## Next Tasks
- Test with testing_agent_v3 for validation
- M2 planning: CRM + lead + clienti next
