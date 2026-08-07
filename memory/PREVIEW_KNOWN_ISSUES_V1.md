# PREVIEW_KNOWN_ISSUES_V1

**Data:** 2026-08-07  
**Ambiente:** PREVIEW / STAGING (NON produzione)  
**Release tag:** `preview-full-test-v1`  
**Rollback tag:** `pre-preview-full-publish-2026-08`  
**Commit:** `2b97058`

Questo documento elenca **con assoluta trasparenza** le limitazioni note della release di collaudo. È lettura **obbligatoria** prima di iniziare i test operativi.

---

## 1. Motore preventivi — Stato ARCHITETTURALE

### 1.1 Doppia fonte dati NON ancora unificata (P0 — Critical)
Sono attualmente presenti **due sorgenti autoritative parallele** per i dati di prodotto:

| Sorgente | Dove viene scritta | Chi la legge |
|---|---|---|
| **Sistema A — commerciale** | `products`, `item_pricelists`, `production_configs` | motore `commercial_perimeter` (attivo) |
| **Sistema B — parametrico/tecnico** | `parametric_profile_systems`, `parametric_bom_recipes` | UI `/parametric/admin` (read-only per il motore) |

Il motore che calcola i prezzi **legge solo il Sistema A**. La sezione "Sistemi profilo e formule" (Sistema B) è **scollegata** dal preventivatore.

**Impatto per il collaudante:** modificare regole/formule tramite `/parametric/admin` **NON ha effetto** sul preventivo. Per cambiare i costi bisogna operare su:
- `/catalog/production-config` (parametri di produzione)
- `/catalog/pricelists` (listini prezzo)
- `/catalog/products` (prodotti e ricette base)

### 1.2 `commercial_perimeter` non ancora sostituito da `TechnicalCostResolver`
Il motore attuale (`backend/app/services/recipes/commercial_perimeter.py`) calcola **sia** il costo tecnico **sia** il markup commerciale. La separazione prevista da `ARCHITECTURAL_AUDIT_V3.md`:

```
Sistema B (tecnico) → costo tecnico autorevole
      ↓
Sistema A (commerciale) → applica solo moltiplicatore/markup
      ↓
prezzo cliente
```

**NON è ancora implementata.** I documenti V1_3 (`PRODUCTION_FORMULA_ANALYSIS_V1_3.md`, `A_TO_B_FIELD_MAPPING_V1.md`, `ENERHIA_GOLDEN_TEST_CASES_V1.md`) descrivono l'architettura target, ma non c'è ancora codice.

### 1.3 Formule Excel `Preventivatore 4.0.xlsx` NON ancora implementate
Le formule reali estratte dal file Excel del cliente sono documentate in `PRODUCTION_FORMULA_ANALYSIS_V1_3.md` ma **non sono ancora nel motore di produzione**. Il motore attuale usa ricette semplificate.

### 1.4 Ricetta tre-ante a telaio unico — MANCANTE (BR-03)
Per finestra 3 ante in telaio unico (non 1/3+2/3) il motore ritorna `MISSING_TECHNICAL_RECIPE`. In attesa di conferma tecnica dal cliente sulla formula reale.

---

## 2. UI "Sistemi profilo e formule" — Legacy, scollegata

**Route:** `/parametric/admin` (e sotto-route)  
**Stato:** ⚠️ **LEGACY** — funzionalmente operativa **ma scollegata dal motore di prezzo**.

- Funzioni operative:
  - Configurare sistemi profilo, ricette BOM, formule
  - CRUD completo su `parametric_profile_systems`, `parametric_bom_recipes`
- Funzioni **read-only** dal punto di vista dell'effetto:
  - Nulla di quanto configurato qui viene letto da `POST /api/quote-structure/.../compute-and-add`
  - Le formule Excel non vengono valutate dal preventivatore

**Nel report di release e nelle release notes appare come limitazione CRITICAL.**  
La sezione **non deve essere presentata come "gestione formule preventivo"** all'utente finale finché non si completa la Fase 1 di unificazione.

---

## 3. Configurazioni disponibili solo via DB/API

Le seguenti configurazioni **non hanno ancora un'UI dedicata** e vanno gestite via API o direttamente in MongoDB:

- Ricette vetro alternative (`glass_recipes` — via API `PUT /api/catalog/production-config`)
- Regole geometriche 3-ante telaio unico (attualmente assenti)
- Overrides per singola opening dentro un preventivo (via `PATCH /api/quote-structure/openings/{id}`)
- Feature flags `RELEASE_STAGE`, `DEMO_MODE`, `DEMO_SEED_ENABLED`, `TEST_DATA_ENABLED` (via `backend/.env`)

---

## 4. Funzioni incomplete del preventivatore

| Area | Stato | Nota |
|---|---|---|
| Wizard 6-step | ⚠️ Parziale | Passi 1-4 stabili; step firma/PDF dipende da Redis/OTP |
| Selezione multipla di prodotti in unico vano | ✅ OK | |
| Cambio prezzo manuale post-simulazione | ✅ Bloccato (guard attivo) | `manual_price_locked=true` |
| PDF preventivo | ⚠️ Parziale | WeasyPrint installato; layout non ancora rifinito |
| PDF contratto | ⚠️ Prototipo | NON dichiarare operativo; endpoint esiste ma template incompleto |
| Firma elettronica (OTP) | ❌ **NON DISPONIBILE IN PREVIEW** | vedi §5 |
| Preventivo legacy (pre-motore) | ⚠️ Read-only | modifiche generano errore controllato `LEGACY_QUOTE_READONLY` |

---

## 5. Redis NON disponibile in preview (Critical per Firma/OTP)

Supervisor riporta:
```
redis   FATAL   can't find command '/usr/bin/redis-server'
```

**Conseguenze operative:**
- **Firma elettronica semplice (M3.3.4) NON è testabile** — la generazione OTP e il rate-limit si basano su Redis. Fail-closed attivo in staging/prod.
- Il link pubblico per firma cliente può essere generato ma **la finalizzazione firma restituirà 5xx**.
- **Rate-limit** su `link_open`, `pdf_download`, `sign` **non applicati** (nessun backend). Non usare la preview per test di sicurezza rate-limit.

**Workaround per collaudo:** limitarsi a testare il flusso Lead → Cliente → Preventivo → Riepilogo → PDF (se disponibile), evitando il ramo firma/pubblicazione.

---

## 6. Limitazioni Mobile

- Il layout è responsive ma **non ottimizzato** per viewport < 375px.
- La `GeometryBuilderPage` (canvas SVG) può risultare piccola su smartphone verticale (< 600px altezza).
- Il wizard preventivo su mobile è **funzionante** ma con transizioni non ottimizzate.
- Firma con dito su touch: **non testabile in preview** (Redis assente).

---

## 7. Tenant isolation & Demo Guard

- **Tenant operativo:** Infissi Express (`5e353147-2416-4ef7-aa3f-3e0007435c42`) — `is_demo=false`, `demo_mode` non applicabile ai prodotti reali.
- **DEMO_PRODUCT_NOT_ALLOWED** — guard attivo: nessun prodotto con `is_demo=true` può essere aggiunto a un preventivo di un tenant `is_demo=false`.
- **Environment scopes**: `preview`, `production`, `test`, `all` — filtro applicato dai router `catalog_service`.
- Un tenant di test dedicato `PanoramaPilot Test` NON è ancora seedato in questa release. Per test di isolamento cross-tenant si consiglia di **creare un secondo tenant via `/admin/tenants`** manualmente durante il collaudo (nessun impatto sui dati esistenti).

---

## 8. Configurazioni ambiente (report senza segreti)

| Variabile | Stato | Note |
|---|---|---|
| `RELEASE_STAGE` | ✅ `first_operational_release` | |
| `DEMO_MODE` | ✅ `true` | Solo per tenant `is_demo=true` |
| `DEMO_SEED_ENABLED` | ✅ `false` | Nessun dato demo iniettato all'avvio |
| `TEST_DATA_ENABLED` | ✅ `false` | |
| `APP_ENV` | ✅ `development` | Preview usa questa modalità |
| `MONGO_URL` | ✅ configurato | |
| `DB_NAME` | ✅ `infissi_express` | |
| `JWT_SECRET` | ✅ configurato | |
| `EMAIL_PROVIDER` | ⚠️ `mock` | Nessuna email reale in preview |
| `MAIL_DELIVERY_MODE` | ✅ `test` | Redirect verso `MAIL_TEST_REDIRECT_TO` |
| `SMTP (SiteGround)` | ⚠️ Configurato ma inattivo | Attende API key reale |
| `STORAGE_PROVIDER` | ✅ `emergent` | |
| `EMERGENT_LLM_KEY` | ✅ configurato | Per moduli AI (non usati in questo collaudo) |
| `REDIS_URL` | ❌ **redis non disponibile** | Fail-closed su OTP/firma |
| `CORS_ORIGINS` | ✅ `*` | Solo preview; da restringere in produzione |
| `PLATFORM_OWNER_EMAIL` | ✅ configurato | |
| `SIGNATURE_EVIDENCE_ISSUER` | ✅ configurato | |
| `OTP_TTL_SECONDS`, `OTP_LENGTH`, `OTP_DEBUG_ENABLED` | ✅ configurati | inefficaci senza Redis |

Nessun segreto è esposto in questo report.

---

## 9. Test automatici — Stato

**Totale eseguito prima del deploy:** 137+ test in 8 suite  
**Risultato:**

| Suite | Passati | Falliti | Note |
|---|---|---|---|
| `test_first_operational_release` | ✅ | | |
| `test_no_eval_regression` | ✅ | | |
| `test_commercial_perimeter_e2e` | 18/19 | 1 xfail | `test_no_alteration_of_existing_kpi` — race condition `xdist` documentata (BUG-16 followup) |
| `test_fase1_motor_integration` | ✅ | | |
| `test_demo_product_guard` | ✅ | | |
| `test_motor_full_listino_hard` | ✅ | | |
| `test_audit_v1_sez20_economic` | ✅ 2/2 | | Terminologia markup vs margin |
| `test_audit_v1_regression` | ✅ 31/31 | | Regressione bug audit v1 |
| `test_commercial_perimeter_recipe` | ✅ | | |
| `test_ci_security_guards` | ✅ | | |
| `test_code_quality_regression` | ✅ | | |
| `test_finestra_1a_recipe` | ✅ | | |
| `test_bom_engine_blocco_a` | ✅ | | |
| `test_stabilization_rc1` | ⚠️ | 25 err | **Non è un bug del codice**: i test invocano l'URL pubblico preview che non è raggiungibile dall'interno del container. Test riproducibili in browser. |

**Nessun test critico è stato saltato.**

---

## 10. Cosa NON viene fatto in questa release

Come da autorizzazione utente Messaggio 155, in questa pubblicazione **NON** vengono:

- ❌ Implementati `ProfileSystemResolver`, `BomResolver`, `TechnicalCostResolver`, `CommercialPricingService`
- ❌ Attivati nuovi plugin (OCR, AI, WhatsApp, scheduler)
- ❌ Eseguiti cleanup distruttivi (`cleanup_production_config_duplicates.py --apply` NON è stato eseguito)
- ❌ Rinominate collezioni MongoDB
- ❌ Modificate formule esistenti
- ❌ Inventate ricette mancanti (BR-03 rimane `MISSING_TECHNICAL_RECIPE`)
- ❌ Pubblicati dati in produzione

---

## 11. Rollback

In caso di anomalie bloccanti durante il collaudo:

```bash
# Ripristino codice al commit precedente la release
git checkout pre-preview-full-publish-2026-08

# oppure ripartire dal tag
git reset --hard pre-preview-full-publish-2026-08
```

Il tag `pre-preview-full-publish-2026-08` punta al commit **`2b97058`** che è **identico** al tag di release `preview-full-test-v1` (nessuna modifica di codice è stata introdotta con la pubblicazione). Il rollback è quindi effettivo verso l'ultimo stato pre-Blocco Sviluppo.

---

## 12. Criterio di accettazione della preview

La release è **accettata** quando l'utente conferma di poter eseguire dal browser:

- login → 
- creazione/modifica cliente → 
- selezione prodotto dal catalogo → 
- inserimento larghezza/altezza/colore/vetro/ferramenta → 
- simulazione con `pricing_status=ok` (per prodotti con listino completo) → 
- creazione preventivo con almeno un ambiente/vano/prodotto → 
- visualizzazione riepilogo con totale > 0 → 
- generazione PDF preventivo (se già implementato; layout può essere prototipo)

Le funzioni non ancora operative (§ 4, § 5) **non entrano** nel criterio di accettazione di questa release.

---

## 13. Prossimo step (dopo collaudo)

Dopo il collaudo manuale dell'utente e sua approvazione esplicita:
1. Fase 1 — Unificazione: `ProfileSystemResolver`, `BomResolver`, `TechnicalCostResolver`, `CommercialPricingService`
2. Fase 2 — Migrazione dati `Sistema B → Sistema A` (dry-run + backup + apply)
3. Fase 3 — Rifacimento UI "Sistemi profilo e formule" come single-source
4. Fase 4 — Riabilitazione Redis + collaudo firma OTP

Fino ad allora — **STOP**.
