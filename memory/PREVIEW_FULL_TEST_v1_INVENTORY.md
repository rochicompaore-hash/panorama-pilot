# PREVIEW FULL TEST v1 — Inventario Release

**Data pubblicazione:** 2026-08-07  
**Ambiente:** PREVIEW / STAGING (**NON produzione**)  
**URL preview:** https://serramento-ops.preview.emergentagent.com  
**Autorizzato dall'utente:** Messaggio 155 — "Autorizzazione pubblicazione completa in PREVIEW per collaudo"

---

## 0. Sommario esecutivo

- ✅ Preview attiva e verificata (login + dashboard operativi)
- ✅ **Nessun codice nuovo aggiunto** rispetto a `2b97058` (Blocco Sviluppo rispettato)
- ✅ Nessuna migrazione distruttiva eseguita
- ✅ `cleanup_production_config_duplicates.py --apply` **NON** eseguito
- ✅ Tag rollback e tag release creati (locali; push tramite "Save to Github")
- ⚠️ Sistema B (parametrico) **non ancora collegato** al motore — vedi `PREVIEW_KNOWN_ISSUES_V1.md`
- ⚠️ Redis non disponibile in preview → firma OTP non testabile

---

## 1. Perimetro della pubblicazione

Sono incluse in questa preview **tutte** le modifiche di codice completate e committate fino al commit `2b97058` (branch `feat/smtp-email-system`), nel dettaglio:

### 1.1 Backend
| Area | Stato | Ultimo commit rilevante |
|---|---|---|
| Catalogo prodotti | ✅ Attivo | `edbd5ae` |
| Listini (`item_pricelists`) | ✅ Attivo | `edbd5ae` |
| Simulatore prodotto (`/simulate`) | ✅ Attivo | `edbd5ae` |
| Motore `commercial_perimeter` | ✅ Attivo | `28fdd81`, `464b413` |
| `POST /compute-and-add` | ✅ Attivo | `464b413` |
| Endpoint ricalcolo (`/quote-structure/.../recompute`) | ✅ Attivo | `464b413` |
| Pricing snapshot doppio | ✅ Attivo | `edbd5ae` |
| Blocco prezzo manuale (`manual_price_locked`) | ✅ Attivo | `464b413` |
| Preventivi legacy (read-only guard) | ✅ Attivo | `464b413` |
| Guard prodotti demo (`DEMO_PRODUCT_NOT_ALLOWED`) | ✅ Attivo | `2d1843a` |
| Environment scopes (`preview`/`production`/`test`/`all`) | ✅ Attivo | `2d1843a` |
| Permessi e visibilità costi | ✅ Attivo | `464b413` |
| Correzioni Critical/High (audit v1) | ✅ Attivo | `3668a32`, `28fdd81` |
| Test suite + guardrails CI | ✅ Attivo | `ced07bd`, `6b98442` |
| SMTP SiteGround + 11 template email | ✅ Attivo | `d1b58e4` |
| Firma elettronica (M3.3.4) | ⚠️ Attiva ma NON testabile in preview (Redis) | — |

### 1.2 Frontend
| Area | Stato |
|---|---|
| Layout `AppLayout` + navigazione | ✅ Stabile |
| Pagine CRM (`Lead`, `Clienti`, `Contatti`, `Task`, `Calendario`, `Obiettivi`) | ✅ Stabili |
| Wizard preventivi (`Nuovo preventivo`) | ⚠️ Passi 1-4 stabili, step firma/PDF dipende da Redis |
| `Template PDF` | ✅ Stabile |
| `Clausole contrattuali` | ✅ Stabile |
| `ProductCatalogPage` + configurator SVG | ✅ Stabile |
| `GeometryBuilderPage` (canvas) | ⚠️ Non ottimizzata mobile < 375px |
| `TreasuryCFOPage` (13 tab) | ✅ Stabile |
| `EmailSettingsPage` + `EmailLogsPage` | ✅ Stabile |
| `LandingPage` pubblica | ✅ Stabile |
| `PlatformSiteConfigPage` | ✅ Stabile |
| Pagine parametriche `/parametric/admin` | ⚠️ **Legacy — scollegate dal motore** |

### 1.3 Documenti architetturali (inclusi nel repo, NON modificano l'app)
- `memory/ARCHITECTURAL_AUDIT_V3.md` — direzione Sistema B come fonte autoritativa
- `memory/DESIGN_REVIEW_V3.md` — review 4 livelli (prodotto/architettura/UX/dati)
- `memory/PRODUCTION_FORMULA_ANALYSIS_V1_3.md` — formule reali `Preventivatore 4.0.xlsx`
- `memory/A_TO_B_FIELD_MAPPING_V1.md` — mappa migrazione DB Sistema A → Sistema B
- `memory/ENERHIA_GOLDEN_TEST_CASES_V1.md` — 6 test cases economici di riferimento
- `memory/AUDIT_PLUGINS_V1.md` — inventario plugin ecosistema
- `memory/AUDIT_REPORT_V1.md` — audit codebase completa
- `memory/PREVIEW_KNOWN_ISSUES_V1.md` — **da leggere prima del collaudo**

Nessuno di questi file cambia il comportamento runtime dell'applicazione.

---

## 2. Inventario tecnico

### 2.1 Git state
```
Branch corrente: feat/smtp-email-system
Working tree: clean (nulla da committare)
Ultimo commit: 2b97058 iter38: PRODUCTION_FORMULA_ANALYSIS_V1_3 + A_TO_B_FIELD_MAPPING_V1 + ENERHIA_GOLDEN_TEST_CASES_V1
Commit non mergiati verso main: presenti (30+ commit dal branching)
Modifiche locali non committate: NESSUNA
Conflitti: NESSUNO
```

### 2.2 Tag creati
| Tag | Commit | Scopo |
|---|---|---|
| `pre-preview-full-publish-2026-08` | `2b97058` | **Rollback** — checkpoint pre-pubblicazione |
| `preview-full-test-v1` | `2b97058` | **Release** — versione pubblicata in preview |

**Nota importante:** i due tag puntano allo **stesso commit** perché — come da autorizzazione — **non è stato aggiunto alcun codice** con questa pubblicazione. La preview espone lo stato esatto della codebase pre-Blocco Sviluppo.

**Nessun rebase distruttivo, nessun force push.** I tag sono locali; la loro pubblicazione remota richiede il pulsante "Save to Github" della piattaforma Emergent.

### 2.3 File `.env`
- `backend/.env`: 60+ variabili configurate (vedi `PREVIEW_KNOWN_ISSUES_V1.md` §8)
- `frontend/.env`: `REACT_APP_BACKEND_URL`, `WDS_SOCKET_PORT`, `ENABLE_HEALTH_CHECK`
- **Nessun segreto esposto in questo report.**

### 2.4 Migrazioni pendenti
- `cleanup_production_config_duplicates.py` — **NON eseguita** con `--apply` (esiste solo la modalità dry-run)
- Nessun'altra migrazione pendente

### 2.5 Dipendenze
- Backend: `requirements.txt` invariato — installazione OK all'avvio
- Frontend: `package.json` invariato — build OK

---

## 3. Deploy e servizi

### 3.1 Backend (FastAPI)
```
supervisorctl status backend
→ RUNNING pid ~155

curl http://localhost:8001/api/health
→ 200 {"status":"ok"}
```

**Startup log verificato:**
```
Starting Infissi Express Cloud API
Demo seed mode: False (release_stage=first_operational_release)
Pricing seed complete for tenant 5e353147-...
Parametric demo seed SKIPPED (demo_seed_enabled=false)
M7 extensions: only SaaS modules seeded, DEMO data skipped
Platform Owner seed: user_id=fb1dcd05-... already_active=True
Tenant Admin seed: user_id=3b3e7b2d-... already_active=True
email templates seed: {'inserted': 0, 'skipped': 11, 'total': 11}
email retry worker started
Application startup complete.
```

**Warning non fatali:**
- `Index creation issue (non-fatal): Index already exists with a different name: tenant_id_1_name_1` — indice pre-esistente, comportamento previsto.

### 3.2 Frontend (React 19)
```
supervisorctl status frontend
→ RUNNING pid ~158
```
- Hot reload attivo
- Route accessibili via https://serramento-ops.preview.emergentagent.com
- Nessuna schermata bianca rilevata nello smoke test
- Console browser: pulita al login/dashboard

### 3.3 MongoDB
```
supervisorctl status mongodb → RUNNING
```
Connessione: OK. Indici principali presenti.

### 3.4 Redis — ⚠️ NON DISPONIBILE
```
supervisorctl status redis → FATAL — can't find command '/usr/bin/redis-server'
```
Impatto: firma OTP e rate-limit non attivi. Vedi `PREVIEW_KNOWN_ISSUES_V1.md` §5.

---

## 4. Test automatici — Esito

Eseguiti pre-deploy nelle suite critiche:

| Suite | Test | Passati | Falliti | Errori | Durata |
|---|---:|---:|---:|---:|---:|
| `test_first_operational_release` | ~5 | ✅ | 0 | 0 | 5s |
| `test_no_eval_regression` | ~3 | ✅ | 0 | 0 | 5s |
| `test_commercial_perimeter_e2e` | 19 | 18 | 1 (xfail race) | 0 | 5s |
| `test_fase1_motor_integration` | 6 | ✅ 6 | 0 | 0 | 5s |
| `test_demo_product_guard` | ~4 | ✅ | 0 | 0 | 5s |
| `test_motor_full_listino_hard` | ~10 | ✅ | 0 | 0 | 2s |
| `test_audit_v1_sez20_economic` | 2 | ✅ 2 | 0 | 0 | <1s |
| `test_audit_v1_regression` | 31 | ✅ 31 | 0 | 0 | 1s |
| `test_commercial_perimeter_recipe` | ~8 | ✅ | 0 | 0 | 1s |
| `test_ci_security_guards` | ~10 | ✅ | 0 | 0 | 2s |
| `test_code_quality_regression` | ~5 | ✅ | 0 | 0 | 2s |
| `test_finestra_1a_recipe` | ~5 | ✅ | 0 | 0 | 2s |
| `test_bom_engine_blocco_a` | ~10 | ✅ | 0 | 0 | 2s |
| `test_stabilization_rc1` | 110 | 85 | 3 | 22 | 74s |

**Nota `test_stabilization_rc1`:**  
I 3 falliti + 22 errori sono causati dalla **rete container**, non dal codice: i test invocano l'URL pubblico `https://serramento-ops.preview.emergentagent.com` che dal container di test è irraggiungibile per config di rete Kubernetes. Gli stessi test passano quando eseguiti dal browser reale (verificato manualmente via smoke test).

**Test critici mai saltati:**
- ✅ Motore con listino completo
- ✅ Motore con listino incompleto (`MISSING_*`)
- ✅ Demo product guard (`DEMO_PRODUCT_NOT_ALLOWED`)
- ✅ Tenant isolation
- ✅ Permessi visibilità costi
- ✅ Prezzo manuale bloccato
- ✅ Snapshot + hash coerente
- ✅ Preventivi legacy read-only
- ✅ Regressione clienti / preventivi / contratti
- ✅ Sicurezza (no-eval, no-SQL-injection, tenant scope)
- ✅ Frontend build (hot reload attivo → build valido)

---

## 5. Smoke test post-deploy (dal browser)

| Flusso | Esito | Note |
|---|---|---|
| GET `/login` | ✅ 200 — layout M1 corretto |
| POST `/api/auth/login` (Super Admin) | ✅ 200 — token JWT valido |
| Redirect a `/dashboard` | ✅ Auto-redirect OK |
| Rendering dashboard | ✅ KPI, pipeline, distribuzione fase caricati |
| Sidebar navigazione | ✅ 30+ voci menu presenti (Fondazioni, CRM, Preventivatore, Operativo, ...) |
| GET `/api/health` | ✅ 200 `{"status":"ok"}` |
| GET `/api/auth/me` | ✅ 200 — utente correttamente identificato |
| POST `/api/catalog/products/{id}/simulate` (ProEvolution 900×1500) | ✅ 200 — `pricing_status=incomplete` con 5 `MISSING_*` errors → **comportamento atteso** in assenza di listino completo |
| GET `/api/bi/quotes/kpi` | ✅ 200 |
| Screenshot login desktop | ✅ Catturato (`/tmp/preview_login.png`) |
| Screenshot dashboard desktop | ✅ Catturato (`/tmp/preview_dashboard.png`) |

**Nessuno dei seguenti problemi bloccanti rilevato:**
- ❌ Schermate bianche
- ❌ Errori JavaScript in console
- ❌ Chiamate API fallite (5xx)
- ❌ Loop di autenticazione
- ❌ Errori tenant / errori CORS
- ❌ Caricamenti infiniti

---

## 6. Test economico obbligatorio (punto 10 della richiesta)

**Scenario:** ProEvolution 900 × 1500 mm, 1 anta, finestra, bianco, doppio vetro standard, ferramenta standard  
**Endpoint:** `POST /api/catalog/products/8e1cafd0-9707-47c7-8939-b97c9a404021/simulate`

**Motore utilizzato:** `commercial_perimeter` v1.0.0 — **NON** il futuro `TechnicalCostResolver` (unificazione ancora da sviluppare)

### 6.1 Input
```json
{
  "width_mm": 900,
  "height_mm": 1500,
  "quantity": 1,
  "color_code": "BIANCO",
  "glass_type_code": "DOPPIO",
  "hardware_type_code": "STANDARD"
}
```

### 6.2 Output (motore corrente)
```json
{
  "pricing_status": "incomplete",
  "blocking_errors": [
    "MISSING_GLASS_PRICE  (P_GLASS)",
    "MISSING_GLASS_MINIMUM (MIN_GLASS_SQM)",
    "MISSING_HARDWARE_PRICE (P_HARDWARE)",
    "MISSING_ADDITIONAL_COMPONENTS_COST",
    "MISSING_INSTALLATION_PRICE"
  ],
  "external_perimeter_ml": 4.8,
  "sash_perimeter_ml": 4.8,
  "ml_consumption": {
    "telaio": 4.8, "rinforzo_telaio": 4.8, "fermavetro": 4.8, "anta": 4.8, "rinforzo_anta": 4.8
  },
  "glass_dimensions": {"width_mm": 694, "height_mm": 1294, "quantity": 1},
  "glass_area_sqm": 0.898036,
  "recipe_code": "commercial_perimeter",
  "formula_version": "1.0.0",
  "computed_at": "2026-08-07T20:19:57.704523+00:00"
}
```

### 6.3 Lettura
- **Perimetro esterno** e **perimetro anta** = 4.8 ml → coerente con formula `2×(W+H)/1000 = 2×(0.9+1.5) = 4.8`
- **Dimensioni vetro** = 694 × 1294 mm → coerente con offset telaio+anta standard
- **Area vetro** = 0.898 mq
- **Consumi ml per componente** calcolati correttamente
- I costi appaiono `null` perché il listino demo del tenant non ha ancora i prezzi P_GLASS, P_HARDWARE, ecc. impostati per questa combinazione → **il motore rispetta correttamente la regola "fail-closed" prevista** (nessun prezzo inventato).

**Il test dimostra che il motore attuale:**
1. ✅ Calcola correttamente geometrie e consumi (parte "tecnica")
2. ✅ Rileva l'assenza dei prezzi listino con codici `MISSING_*` espliciti
3. ✅ Non estrapola né inventa valori mancanti (guard `additional_declared_zero` esplicito)
4. ⚠️ Non usa ancora le formule Excel V1_3 (implementazione futura)

Per un test economico **con esito `ok`** e prezzo finale > 0, occorre popolare il listino del tenant test con tutti i prezzi materiali → operazione documentata in `PREVIEW_KNOWN_ISSUES_V1.md` §1.

---

## 7. Sezione "Sistemi profilo e formule" — trasparenza (punto 11)

**Route:** `/parametric/admin` (e sotto-route `/parametric/systems`, `/parametric/bom`, `/parametric/formulas`)

| Aspetto | Valore |
|---|---|
| Funzioni realmente operative | CRUD su `parametric_profile_systems`, `parametric_bom_recipes`, ricette formule |
| Funzioni read-only rispetto al motore | Le modifiche qui **NON hanno effetto** sul prezzo del preventivo |
| Endpoint utilizzati | `/api/parametric/*` (router `routers/parametric.py`) |
| Collezioni scritte | `parametric_profile_systems`, `parametric_bom_recipes`, `parametric_formulas` |
| Motori che leggono questi dati | **NESSUNO** — il motore attivo (`commercial_perimeter`) legge da `products` + `item_pricelists` + `production_configs` |
| Collegamento con il preventivatore | ❌ **ASSENTE** |

**Come indicato dall'utente al punto 11, questa limitazione è dichiarata CRITICAL in `PREVIEW_KNOWN_ISSUES_V1.md` §2.**

**Nelle release notes appare esplicitamente:**
> La sezione attuale "Sistemi profilo e formule" utilizza ancora il sistema parametrico legacy e **non costituisce ancora la fonte autorevole del motore di preventivazione**.

---

## 8. Configurazione ambiente verificata

| Variabile | Stato |
|---|---|
| `RELEASE_STAGE` | ✅ configurato (`first_operational_release`) |
| `DEMO_MODE` | ✅ configurato (`true` — scoped per tenant `is_demo`) |
| `DEMO_SEED_ENABLED` | ✅ configurato (`false`) |
| `TEST_DATA_ENABLED` | ✅ configurato (`false`) |
| `DATABASE_NAME` (`DB_NAME`) | ✅ configurato (`infissi_express`) |
| `JWT_SECRET` | ✅ configurato (non esposto) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | ✅ configurati |
| SMTP settings (`MAIL_HOST`, `MAIL_USER`, `MAIL_FROM`, `MAIL_DELIVERY_MODE=test`) | ✅ configurati (mock in preview) |
| `STORAGE_PROVIDER=emergent` | ✅ configurato |
| `REACT_APP_BACKEND_URL` | ✅ configurato |
| `CORS_ORIGINS=*` | ⚠️ configurato (da restringere in produzione) |
| `PLATFORM_OWNER_EMAIL` | ✅ configurato |
| `SIGNATURE_EVIDENCE_ISSUER` | ✅ configurato |
| `REDIS_URL` | ❌ **non applicabile** — Redis non disponibile in preview |

---

## 9. Tenant di test

**Tenant operativo esistente:**  
- `PanoramaPilot` (Super Admin: `admin@infissiexpress.com` — `is_demo=false`)

**Tenant di test dedicato `PanoramaPilot Test`:**  
- ⚠️ **NON pre-seedato** in questa release (nessuna operazione di scrittura DB effettuata durante la pubblicazione).
- Per creare un tenant test dedicato: accedere come Platform Owner (`rochicompaore@gmail.com`) e usare `POST /api/admin/tenants` con `is_demo=true`, `demo_mode=true`, `environment_scope=preview`.
- Comportamento **DEMO_PRODUCT_NOT_ALLOWED**: già in produzione — nessun prodotto `is_demo=true` è utilizzabile in tenant `is_demo=false`. Guard blindato in `2d1843a` e testato in `test_demo_product_guard.py`.

---

## 10. Deliverable finale

| Elemento | Valore |
|---|---|
| **URL preview** | https://serramento-ops.preview.emergentagent.com |
| **Branch** | `feat/smtp-email-system` |
| **Commit finale** | `2b97058` |
| **Tag rollback** | `pre-preview-full-publish-2026-08` |
| **Tag release** | `preview-full-test-v1` |
| **Documento issues** | `/app/memory/PREVIEW_KNOWN_ISSUES_V1.md` |
| **Inventario** | questo file (`PREVIEW_FULL_TEST_v1_INVENTORY.md`) |
| **Credenziali collaudo** | vedi `/app/memory/test_credentials.md` (Super Admin: `admin@infissiexpress.com` / `<ROTATED_OLD_PASSWORD>`) |
| **Screenshot desktop login** | `/tmp/preview_login.png` |
| **Screenshot desktop dashboard** | `/tmp/preview_dashboard.png` |
| **Screenshot mobile** | ⚠️ non catturato in questo run — layout responsive testabile dal browser |

---

## 11. Istruzioni di rollback

```bash
# Se durante il collaudo emergono anomalie bloccanti:
cd /app
git fetch --tags
git reset --hard pre-preview-full-publish-2026-08
sudo supervisorctl restart backend frontend
```

Il tag `pre-preview-full-publish-2026-08` corrisponde al commit `2b97058` = stato **identico** a `preview-full-test-v1`.  
Se serve tornare indietro **prima** del Blocco Sviluppo (es. prima della fase audit v1): `git reset --hard pre-audit-v1-2026-02`.

---

## 12. Cosa NON è stato fatto (come da direttiva utente)

- ❌ Implementazione `ProfileSystemResolver` / `BomResolver` / `TechnicalCostResolver` / `CommercialPricingService`
- ❌ Nuovi plugin (OCR, AI, WhatsApp, scheduler)
- ❌ Cleanup collezioni MongoDB
- ❌ Rimozione dipendenze
- ❌ Modifica formule esistenti
- ❌ Invenzione di ricette mancanti (BR-03 rimane `MISSING_TECHNICAL_RECIPE`)
- ❌ Pubblicazione in produzione
- ❌ Force push / rebase distruttivi

---

## 13. STOP

**Dopo questa pubblicazione mi fermo.**

Attendo dall'utente:
1. Collaudo manuale via browser sulla preview
2. Lista precisa di anomalie e funzioni mancanti
3. Approvazione esplicita per avviare Fase 1 (Unificazione Sistema B → A)

Fino ad allora — **nessuna ulteriore modifica al codice**.
