# Infissi Express Cloud — PRD

## Original Problem Statement
Piattaforma SaaS cloud (Web based App, responsive) per la gestione end-to-end del ciclo di vita commerciale, tecnico, produttivo e post-vendita di un'azienda produttrice e installatrice di infissi. ERP verticale (M1-M10).

## Milestones — Completate

### M1 (Fondazioni) — 2026-07-15
Auth JWT + refresh rotation + jti, RBAC granulare (28 perms + 10 ruoli), audit append-only, allegati (S3-ready), numerazioni progressive, notifiche, sessioni, ricerca globale, dashboard, gestione utenti/ruoli/azienda. 34/34 test PASS.

### M2 (CRM) — 2026-07-15
- **Onboarding wizard** (5 step: azienda → logo → numerazioni → invito → primo lead → completato)
- **Fase 1 CRM**: Lead con intelligenza vendita (probability, days_since_contact, next_action suggerita), Clienti (conversione da lead), Contatti, Pipeline commerciale (7 stage: Nuovo/Contattato/Qualificato/Preventivo/Trattativa/Vinto/Perso), **Timeline centrale** (ogni evento del sistema registra un'attività), Task, Note, Calendario settimanale
- **Fase 2 CRM**: Comunicazioni telefonate (registrazione con esito/durata), email (mock provider dev, Resend prod-ready), WhatsApp (mock provider dev, Twilio prod-ready), promemoria, appuntamenti con calendar view, obiettivi (per user/periodo/metrica), regole provvigioni
- **Fase 3 CRM**: Dashboard **role-adaptive** (endpoint /variant + rendering client) — Commerciale (lead aperti, appuntamenti oggi, task, pipeline ponderata, obiettivi, prossime azioni), Direzione (conversion rate, top performer, stage breakdown, fatturato acquisito), Produzione (placeholder M6), Posatore (placeholder M8)
- **Global search estesa**: lead, clienti, contatti, attività, task, appuntamenti, utenti, allegati (multi-collection cross-tenant filtered)
- 37/37 backend + 17/17 frontend test PASS

## Architecture
- Backend: FastAPI + Motor (MongoDB) + PyJWT + bcrypt, 27+ router `/api/*` modulari
- Frontend: React 19 + Tailwind + Shadcn/UI + react-i18next + Zustand-ready + React Query
- Storage: Local dev, S3-compatible provider ready
- Email: Mock (dev) + Resend (prod stub)
- WhatsApp: Mock (dev) + Twilio (prod stub)

## Roadmap
- **M3** Preventivatore + configuratori (serramenti/vetri/ferramenta/cassonetti/persiane/zanzariere) + PDF + contratti + firma
- **M4** Rilievo tecnico + ordine esecutivo con blocco misure
- **M5** Ordini fornitore + magazzino base + varianti/lotti
- **M6** Produzione: distinte base + liste taglio + ottimizzazione barre + tracciabilità QR
- **M7** Pianificazione + QC + non conformità
- **M8** Prodotto finito + logistica + posa + verbali mobile
- **M9** Assistenza + garanzie + portale cliente
- **M10** Amministrazione + BI + cash flow + AI CFO

## Test Credentials
`/app/memory/test_credentials.md` — admin@infissiexpress.com / Admin!2025
