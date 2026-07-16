# Infissi Express Cloud — PRD

## Milestones Complete
- **M1** (2026-07-15): Fondazioni — auth+RBAC+audit+attachments+sequences+search+notifications. 34/34 test PASS.
- **M2** (2026-07-15): CRM — Onboarding wizard, Lead/Cliente/Contatto/Pipeline/Timeline centrale/Task/Calendario, Comunicazioni (call/email/WA mock), Obiettivi/Provvigioni, dashboard role-adaptive, ricerca globale estesa. 37/37 test PASS.
- **M2 Audit** (2026-07-16): Tenant isolation, IDOR, RBAC backend, soft-delete, convert idempotency, timeline immutability. 34/34 audit test PASS.
- **M3.1** (2026-07-16): Preventivatore Fondazioni — quotes CRUD + openings (vani) + lines + numerazione PREV-YYYY-NNNNN-R00 partenza=1350 configurabile, price engine base (base+surcharges+discount, VAT per rate), 12 status con transizioni validate, approval workflow (soglie sconto), revisioni R00→R01 con parent superseded + history, snapshot listino congelato al send, convert-to-contract con snapshot, firma elettronica FES semplice (canvas + IP + UA + SHA-256), 23 permessi granulari (quotes.*/pricelists.*/products.*/contracts.*), costi/margini mascherati senza permessi dedicati. 32/32 test PASS.

## Roadmap
- **M3.2**: Configuratori UI (finestre 12 tipologie, vetri, colori con regole 8/14.5/16/22+150€, tapparelle base+kit+guide+96€/m² min 1.75 m², cassonetti auto-larghezza, zanzariere 8 tipologie, posa/extra), motore listini formule versionate, soglie sconto per ruolo
- **M3.3**: PDF professionale (reportlab), firma canvas UI completa, contratto UI, dashboard preventivi (KPI: conversion, sconto medio, marginalità autorizzata, ecc.), tracking apertura link, send email/whatsapp/link/print
- **M4** Rilievo tecnico + ordine esecutivo + blocco misure
- **M5-M10** Acquisti/Magazzino/Produzione/QC/Posa/Assistenza/BI/AI CFO

## Test Credentials
`/app/memory/test_credentials.md` — admin@infissiexpress.com / Admin!2025
