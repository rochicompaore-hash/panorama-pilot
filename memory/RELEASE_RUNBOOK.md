# RELEASE RUNBOOK — Infissi Express Cloud (msg 629 PRODUCTION READINESS)

Stato: **APPLICATION_CODE = RELEASE_READY** · **PRODUCTION_DEPLOY = BLOCKED** (configurazione produzione mancante, vedi §1).
Regola: nessun secret in questo documento — solo CONFIGURED / MISSING / INVALID.

## 1. Production Config Audit (`python -m app.scripts.production_config_audit --target production`)
Eseguito sull'ambiente preview con semantica produzione. Da rieseguire nel pod di produzione dopo aver impostato gli Emergent Secrets.

| Chiave | Stato (preview→prod) | Azione PO |
|---|---|---|
| MONGO_URL / DB_NAME | CONFIGURED (managed dal deploy) | — |
| JWT_SECRET | CONFIGURED | usare valore dedicato produzione (≥32 char) |
| ADMIN_EMAIL / ADMIN_PASSWORD | CONFIGURED (ruotato in preview) | in produzione: password nuova, mai riportata |
| **REDIS_URL** | **INVALID** (localhost) | **Redis managed** (Upstash/Redis Cloud) `rediss://` con auth — rate limit OTP/firma è fail-closed senza Redis |
| **EMAIL_PROVIDER / MAIL_DELIVERY_MODE** | **INVALID** (mock / test) | `smtp` o `resend` + `live` — l'OTP firma pubblica viaggia via email ⇒ **PRODUCTION BLOCKER** (dependency graph verificato: `public.py → otp_svc.build_and_send → email_service.send_email`) |
| **MAIL_PASSWORD** (SMTP) o **RESEND_API_KEY** | **MISSING** | Emergent Secret |
| OTP_DEBUG_ENABLED | INVALID (true) | `false` in produzione (mai OTP in risposta API) |
| APP_BASE_URL | INVALID (http preview) | URL https produzione |
| CORS_ORIGINS | INVALID (`*`) | origini esplicite (frontend prod) |
| APP_ENV / DEMO_MODE / DEMO_SEED_ENABLED / TEST_DATA_ENABLED | INVALID per prod | `production` / `false` / `false` / `false` |
| TEST_LIMITED_EMAIL/PASSWORD | presenti solo preview | NON impostare in produzione |
| STORAGE_PROVIDER (+ path/S3) | CONFIGURED | verificare persistenza volume in prod |
| EMERGENT_LLM_KEY (Google Sign-In managed) | CONFIGURED | — |
| PDF fonts Roboto (vendorizzati) | CONFIGURED | — |

Google Login: smoke reale (identity → utente Panorama esistente → tenant/ruolo; account non collegato → 403 GOOGLE_ACCOUNT_NOT_LINKED, no auto-provisioning) da eseguire con account autorizzato sull'URL di produzione.

## 2. Redis security checklist (da verificare al primo avvio prod)
TLS (`rediss://`) · auth in URL secret · timeout connessione (`RedisRateLimiter._ping`) · nessun retry infinito · key prefix per scope (`otp:`, `sign:`, `link_open:`, `pdf:`) + tenant/quote id · TTL OTP = `OTP_TTL_SECONDS` · fail-closed su scope sensibili quando `ready=False` (già implementato in `services/rate_limiter.py`).
Test OTP da rieseguire con Redis attivo: `pytest tests/test_public_signature_m334.py tests/test_fase2_pdf_otp_storage.py` (in preview, in-memory: 62 passed + one-time-use/expiry PASS).

## 3. Credential rotation
- Preview: `admin@infissiexpress.com` password **ruotata** (valore solo in `memory/test_credentials.md`, gitignored, e in `backend/.env`); portale `cliente.demo@…` **SOSPESO** + password ruotata; `TEST_LIMITED_PASSWORD` ruotata. Le vecchie credenziali riportate in chat non funzionano più (401 verificato).
- Account test commerciali del preview (pattern `commercial_test*`, `pilot*`, …) restano attivi SOLO nel DB preview perché usati dalla regression suite; **non esistono nel DB produzione** (fresh) e il seed prod ha `TEST_DATA_ENABLED=false`.
- Produzione: unico account seedato = ADMIN (password secret nuova). Per lo smoke creare un account temporaneo a permessi minimi → poi DISABLE.

## 4. Backup pre-deploy
`python -m app.scripts.backup_pre_deploy` → `/app/backups/<ts>/` (JSON gz per collection + `MANIFEST.json` con git commit, migration state, versione condizioni generali, conteggi, elenco NOMI variabili configurate). Eseguito in preview: 138 collection, 28.296 documenti, release `bb8c373`. Restore: `--restore <dir>` (drop + insert per collection).
Da rieseguire sul DB di produzione subito prima del deploy (release identifier = git commit del build).

## 5. Rollback plan
- Previous build: checkpoint Emergent precedente (funzione **Rollback** della piattaforma) — nessuna migrazione DB distruttiva in questa release (solo nuove collection/campi additivi: `general_terms_snapshots`, `customer_portal_users`, `QuoteLine.visual_spec`, `quotes.general_terms_*`). Compatibilità DB: il build precedente ignora i campi nuovi → rollback applicativo sicuro senza restore.
- Restore dati (solo se corruzione): `backup_pre_deploy --restore`.
- Trigger rollback immediato (§20 PO): data leak tenant/customer, pricing/margin errati, document leak, auth bypass, snapshot mutation, totali PDF errati, failure firma, corruzione DB, 5xx critici ripetuti.

## 6. Smoke test produzione (dati controllati, nessun cliente reale)
Checklist §11-§15 PO: login admin · Google login · customer/site/quote create · configurazione finestra (003/110, bicolore) · live price · visual · save/reload · sconto globale · payment terms · ENEA (100/50 standard, 350/120 assicurata → OTHER_DIRECT_COSTS) · margin/tachometer (FINAL_COMPANY_MARGIN) · PDF V2 (Roboto, #12a16b, no leak) · accepted snapshot · contratto · portale cliente A/B isolation (404) · download documento · ticket · OTP firma pubblica (one-time use). Monitorare 5xx/auth/DB/Redis/PDF/signature errors.

## 6-bis. FINAL CLOSE (PO msg 783) — esito verifiche pre-deploy (2026-09-09)
- COLOR_INPUT_V2 = PASS (browser: save→reload→modifica; '096' resta "096"; nome ripopolato; BICOLOR 003/154 4 campi ok; fail-closed codice/nome vuoto ora anche a livello API `configure` → `incomplete` + COLOR_CODE_REQUIRED/COLOR_NAME_REQUIRED). Screenshot: `/app/test_reports/screenshots/iter45_final_reload_modify_096_GRIGIO.jpeg`.
- CONTRACT_SOURCE_VISUAL_VERIFY = VERIFIED_WITH_LEGAL_NOTE: il PDF sorgente (pag. 7) mostra chiaramente "3, 5, 6,9,12,15, 1, 6, 21." → canonico allineato alla sorgente (nessuna interpretazione "16"); LEGAL_REVIEW_RECOMMENDED sull'elenco (contiene "1" e "6" ripetuto) — nessuna modifica senza approvazione PO. Verifiche a campione OK (Art. 7, Art. 13 "DEI PRODOTTI").
- Credential hygiene: rimossa password admin corrente hardcoded in `tests/test_prod_gate_iter41.py` (ora `tests._creds`), redatti i report `test_reports/*.json` e i memo `memory/*.md`; fixture legacy (`test_release_gate_iter40`, `test_customer_portal_iter39`, `test_iter45_po_smoke`) passate a env (`TEST_CUSTOMER_DEMO_*`). Secret scanner = clean.
- Backup pre-deploy preview: `/app/backups/20260909T172813Z` (138 collection, 30.200 doc, release 8abe5e9).
- Deploy: NON eseguibile dall'agente — richiede click "Deploy" in Emergent dopo aver impostato i Custom Secrets (Deployments → Secrets → Custom Keys) e Redis esterno (Emergent non fornisce Redis gestito).

## 7. Verdetto corrente
PRODUCTION_CONFIG = FAIL (secret produzione mancanti: Redis managed, email provider live, flag prod) · REDIS = FAIL · CREDENTIAL_ROTATION = PASS (preview) · BACKUP = PASS (preview; da ripetere su prod) · DEPLOY = NOT EXECUTED · PRODUCTION_STATUS = **NOT_READY** fino a configurazione secret da parte del PO.
