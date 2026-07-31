# Panorama Pilot — AUDIT PLUGIN & DIPENDENZE STRATEGICHE v1
**Data**: Feb 2026 · Iter 31  
**Ambito**: analisi read-only di tutte le dipendenze installate + gap analysis per ERP SaaS verticale serramenti  
**Regola cardine**: nessun "plugin di moda". Solo strumenti che spostano il KPI di **conversione lead → contratto firmato → produzione consegnata**.  
**Fonte dati**: `package.json`, `requirements.txt`, grep uso reale nel codice, DB counts.

---

## 1 · Analisi stack attuale

### Backend

| Componente | Stack attuale | Stato | Note |
|---|---|---|---|
| Framework | FastAPI 0.110.1 + Starlette 0.37.2 + Uvicorn 0.25 | ✅ USATO | Solido, no upgrade richiesto |
| Server ASGI | Uvicorn | ✅ USATO | Single-worker in preview, va scalato in prod |
| ORM/ODM | **Motor 3.3.1** (async MongoDB) + Pydantic 2.13 | ✅ USATO | Nessun ORM SQL — coerente con no-SQL choice |
| Database | MongoDB (Atlas o self-hosted) | ✅ USATO | 57 router, ~200 collezioni |
| Auth | PyJWT 2.13 + passlib + bcrypt 4.1 | ✅ USATO | JWT custom, no OAuth. Buon audit hash. |
| Ruoli/permessi | Custom (`app/permissions.py` + `role_ids[]`) | ✅ USATO | `require_permission()` decoratore |
| Storage | `emergentintegrations` S3 wrapper (`app/services/object_storage.py`) | ✅ USATO | boto3 installato ma NON importato direttamente |
| Email | `aiosmtplib` + SiteGround SMTP + Jinja2 template | ✅ USATO | 3 template attivi (contract/quote/quote_signed) |
| PDF | **WeasyPrint 69** + pypdf 6.14 + pymupdf 1.28 | ⚠️ PARZIALE | WeasyPrint in 3 file. `pymupdf` **installato ma non usato**. |
| Rendering | HTML→PDF via Jinja+WeasyPrint | ✅ USATO | — |
| AI/LLM | `emergentintegrations` (Universal Key) + openai 1.99 + google-genai 2.11 + litellm | ⚠️ **INSTALLATE MA NON USATE** | Solo `object_storage.py` importa emergentintegrations. **Nessun endpoint AI attivo** nei 57 router. |
| Cache | `services/rate_limiter.py` (Redis primary + in-memory fallback) | ✅ USATO SOLO PER RATE LIMIT | Nessuna cache dati/query in atto |
| WebSocket | `websockets 16.1` **installato**, ma 0 file lo importa | ❌ INUTILIZZATO | Nessun real-time push (notifiche, chat, produzione) |
| Scheduler | ❌ ASSENTE | ❌ MANCANTE | Nessun `apscheduler`/`celery`/`dramatiq`. Zero cron. |
| Queue | ❌ ASSENTE | ❌ MANCANTE | Zero `BackgroundTasks` FastAPI usati nei router |
| Logging | `logging` standard Python | ⚠️ BASE | Nessun structured logging (JSON), no correlation ID |
| Monitoring | ❌ ASSENTE | ❌ **GRAVE per prod** | No Sentry, no Prometheus, no OpenTelemetry |
| Analytics | `models_bi.py` + custom KPI | ✅ USATO | Aggregazioni MongoDB pipelines |
| Testing | pytest 9.1 + pytest-xdist 3.8 | ✅ USATO | 96+ test verdi |
| CI/CD | Emergent platform | ✅ USATO | Deploy manuale da UI |
| Payments | `stripe 14.4.1` **installato**, ma 0 file lo importa | ❌ INUTILIZZATO | Nessun endpoint pagamento |
| Retry logic | `tenacity 9.1` **installato**, ma 0 file lo importa | ❌ INUTILIZZATO | — |
| Excel I/O | `openpyxl 3.1.5` **installato**, 0 uso diretto (via pandas?) | ⚠️ AL LIMITE | Verificare uso in importer |
| Data | `pandas 3.0` (1 file), `numpy 2.4` (indiretto) | ⚠️ MINIMO | Overkill se solo 1 file |

### Frontend

| Componente | Stack attuale | Stato | Note |
|---|---|---|---|
| Framework | React 19 + CRA (react-scripts 5) + Craco | ✅ USATO | React 19 recente, no Vite ma OK |
| Router | react-router-dom 7.15 | ✅ USATO | — |
| State server | **@tanstack/react-query 5** (28 file) | ✅ USATO INTENSAMENTE | Ottima scelta |
| State server 2° | **swr 2.3.8 installata, ZERO file la usa** | ❌ INUTILIZZATA | **Rimuovere** — duplicato con react-query |
| Form | react-hook-form 7 + zod 3.24 + @hookform/resolvers 5 | ⚠️ MINIMO | Solo 1 file usa `useForm` → sotto-utilizzato |
| UI kit | Radix UI (**30+ primitive**) + shadcn/ui + Tailwind 3.4 | ✅ USATO | Setup completo |
| Motion | **framer-motion 11 installata, ZERO file la usa** | ❌ INUTILIZZATA | **Rimuovere** — 100kb sprecati nel bundle |
| Icone | **@phosphor-icons/react (37 file) + lucide-react (installata)** | ⚠️ DUAL | Consolidare su uno solo |
| Date | **date-fns 4 (2 file) + dayjs 1.11 (0 file)** | ⚠️ DUAL | **Rimuovere dayjs** |
| Utils | **lodash 4 installata, ZERO file la usa** | ❌ INUTILIZZATA | **Rimuovere** |
| Firma elettronica | signature_pad 5.1.3 (1 file: `PublicQuotePage.jsx`) | ✅ USATO | Base grezza, no touch-optimized |
| Charts | recharts 3.6 (1 file) | ✅ USATO | Solo dashboard direzione |
| Command palette | cmdk 1.1 (1 file) | ⚠️ PARZIALE | Componente shadcn base, no ricerca globale reale |
| i18n | i18next 26 + react-i18next 17 | ✅ USATO | — |
| Theme | next-themes 0.4 | ✅ USATO | Dark/light toggle |
| Toaster | sonner 2 | ✅ USATO | — |
| Calendar | react-day-picker 8 | ✅ USATO | — |
| OTP | input-otp 1.4 | ✅ USATO | — |
| Drawer mobile | vaul 1.1 | ✅ USATO | 1 componente |
| Carousel | embla-carousel-react 8 | ✅ USATO | — |
| HTTP | axios 1.16 | ✅ USATO | — |
| Visual editor | @emergentbase/visual-edits | ✅ USATO | Dev tool |
| Bundle analyzer | ❌ ASSENTE | ❌ MANCANTE | No webpack-bundle-analyzer |
| Firma canvas mobile | ❌ base signature_pad senza wrap | ⚠️ INSUFFICIENTE | UX_ARCH V2 richiede rewrite dedicato |
| PDF viewer inline | ❌ ASSENTE | ❌ MANCANTE | Preventivo PDF si scarica, no viewer inline |
| Drag & drop | ❌ ASSENTE | ❌ MANCANTE | Necessario per ordinare vani/aperture nel preventivo |
| Upload avanzato | ❌ input file base | ⚠️ INSUFFICIENTE | No drop-zone, no resume, no preview |
| Table virtualizzata | ❌ ASSENTE | ❌ MANCANTE | Liste 1000+ righe usano render classico |
| Tour guidati | ❌ ASSENTE | ❌ MANCANTE | Nessun onboarding per nuovi utenti |

---

## 2 · Plugin / librerie mancanti (con giustificazione settore serramenti)

### Frontend — proposte

| Area | Libreria consigliata | Motivo | Sostituisce? |
|---|---|---|---|
| Drag & drop | **@dnd-kit/core** (60kb) | Riordinare vani, aperture, prodotti del preventivo. **Accessibile (a11y)** — critico per certificazione | — |
| Firma elettronica touch-first | **react-signature-canvas 1.1** (wrapper di signature_pad) + salvare `Blob` PNG + audit trail (IP, UA, hash doc) | La UX_PRODUCT_ARCHITECTURE_V2 lo richiede esplicitamente (Fase 3). Il PO ha detto "signature pad attuale è un giocattolo". | Wrappa `signature_pad` già installato |
| PDF viewer inline | **react-pdf** (di @wojtekmaj) o **pdfjs-dist** wrapper | Cliente vede preventivo/contratto nel browser prima di firmare — riduce dropout | — |
| Canvas geometrie | **konva.js** + react-konva (o **fabric.js**) | Configuratore grafico apertura finestra (drag maniglia, ridimensiono, ecc.). Serramento è visuale. | — |
| Diagrammi struttura | **@xyflow/react** (React Flow) | Se serve visualizzare gerarchia sistema→profilo→componente | Solo P2 |
| Upload avanzato | **react-dropzone 14** | Foto sopralluogo, allegati capitolato, importer listini | — |
| Immagini | **@radix-ui/react-aspect-ratio** già presente + eventualmente `sharp`-server-side | Gallerie sopralluogo | — |
| OCR client-side | **tesseract.js** (WASM, 10MB) — SOLO se serve offline | Estrazione dati listini fornitori PDF/scan. Alternativa: backend con Vision AI (più affidabile). | — |
| Scanner documenti | **@microsoft/dynamicproto-js** o soluzione mobile-web PWA | Fatture, DDT | Solo P3 |
| File explorer | Custom su Radix — no libreria dedicata | — | — |
| Rich text editor | **@tiptap/react** (Prosemirror-based, modulare) | Note commerciali, corpo email personalizzato, capitolato tecnico | — |
| Shortcut tastiera | **react-hotkeys-hook 4** | ⌘K global search, ⌘S salva preventivo, ⌘N nuovo lead | — |
| Table virtualizzata | **@tanstack/react-virtual 3** (stesso autore di react-query) | Liste 5000+ leads, 100k€ pricelist entries | — |
| Grafici avanzati | recharts già presente | Nessun upgrade | — |
| Tour guidati | **shepherd.js** o **react-joyride** | Onboarding nuovo utente ERP (bug: OnboardingWizard esiste ma è generico) | — |
| Notifiche real-time | **socket.io-client** o **native EventSource (SSE)** | Notifica: contratto firmato, sopralluogo confermato, preventivo aperto dal cliente | — |
| Accessibilità | eslint-plugin-jsx-a11y **già installato** | Non attivato — attivare rule set strict | — |
| Bundle analyzer | **webpack-bundle-analyzer** (devDep) | Identificare i 3 giganti già installati inutilizzati (~500kb) | — |

### Backend — proposte

| Area | Libreria consigliata | Motivo | Priorità |
|---|---|---|---|
| **Scheduler** | **APScheduler 3.10** async (o **arq** su Redis) | Follow-up automatici lead, reminder scadenze contratti, invio KPI settimanale, cleanup expired sessions, ri-check listini scaduti | 🔴 P0 |
| **Queue** | **arq** o **taskiq** (async-nativi) | Invio email massivi (100+ notifiche), generazione PDF pesanti, import listini XLS 10k+ righe | 🔴 P0 |
| **Cache dati** | Redis (già installato) — usare per lookup catalog | Motore commerciale ricalcola ogni volta anche se gli input non cambiano. Cache `production_config`, `item_pricelists.entries[]`, `catalog_code_mappings` per tenant | 🟠 P1 |
| **Rate limit avanzato** | Estendere `services/rate_limiter.py` per API pubbliche `/sign/*`, webhook | Già ok su auth; aggiungere ai public endpoints | 🟠 P1 |
| **Monitoring** | **sentry-sdk 2** (FastAPI integration) | Traccia errori 500 su prod (già capitato con BUG-16 latente) | 🔴 P0 |
| **APM** | Sentry Performance + eventualmente **OpenTelemetry** | Traccia query lente, endpoint P95 | 🟡 P2 |
| **Profiling** | py-spy (esterno, no dep) | Debug produzione | 🟢 P3 |
| **Retry** | tenacity già installata (mai usata) | Retry email SMTP, chiamate S3, webhook | 🟠 P1 |
| **Audit trail** | `models_audit.py` + `services/audit.py` già presenti | Verificare copertura completa mutations | 🟠 P1 verifica |
| **Versionamento** | Solo custom (snapshot). Nessun `python-jose` per timestamp cryptographic | Contratti firmati richiedono timestamp certificato (LegalWeb, Aruba) | 🟡 P2 |
| **Import/export** | `openpyxl` già installato + `pandas` (in importer) | Estendere a export XLS quote, contratti, KPI | 🟠 P1 |
| **OCR listini fornitori** | **Vision AI via emergentintegrations** (già installato!) | Estrarre prezzi da PDF/foto listino fornitore. **Gemini Vision è già in requirements.txt** — solo da attivare | 🔴 P0 differenziante |
| **Barcode / QRCode** | **qrcode 7.4** (Python) + **python-barcode** | QR sui contratti per verifica firma pubblica, QR su etichette produzione | 🟠 P1 |
| **Gestione allegati** | Object storage già in place | Estendere a versioning file (v1/v2) | 🟡 P2 |
| **Ricerca full-text** | MongoDB text index (built-in) o **Meilisearch** | 355 quotes + 1000+ contacts → serve ricerca globale veloce | 🟠 P1 |

### Database

| Sistema | Pro | Contro | Verdetto per Panorama Pilot |
|---|---|---|---|
| **Redis** | Cache low-latency, pub/sub, session store, rate limit | Overhead operativo | ✅ **GIÀ INSTALLATO**, usare oltre il rate-limiter (cache dati) |
| **ElasticSearch** | Search potente, aggregazioni complesse | Costoso, complesso, richiede sysop dedicato | ❌ **NO** — sovradimensionato |
| **Meilisearch** | Full-text semplice, self-hosted 1 binary, tipo-tollerante | Meno maturo di ES | 🟡 **CONSIDERARE** per ricerca globale se MongoDB text index insufficiente |
| **Vector Database** (Qdrant/pgvector/Chroma) | RAG, ricerca semantica su capitolati/preventivi passati | Utile solo con AI attiva | 🟢 P3 — solo dopo attivazione AI |
| **Mongo Atlas Search** | Full-text nativo su MongoDB Atlas | Solo su Atlas, non self-hosted | ✅ **USARE SE SU ATLAS** — zero effort |
| **ClickHouse** | Analytics enorme scala (miliardi righe) | Overkill per ERP SMB | ❌ NO |
| **PostgreSQL aggiuntivo** | Ottima consistenza transazionale | Richiede dual-DB pattern, complessità | ❌ NO — Mongo basta con transazioni multi-doc |

---

## 3 · Plugin AI

**Situazione attuale**: `emergentintegrations` + Universal LLM Key + `openai` + `google-genai` + `litellm` — TUTTI installati, **UNO SOLO USATO** (`object_storage.py`). **Nessun endpoint AI attivo nei 57 router**. È lo spreco più grande dell'ecosistema installato.

| Plugin AI | Utilità Panorama Pilot | Dove integrarlo | Beneficio operativo | Priorità |
|---|---|---|---|---|
| **Claude Sonnet 5 (text)** via Universal Key | Redazione capitolato tecnico, risposte email cliente, riepilogo preventivo | Nuovo endpoint `/api/ai/draft-*` | Riduce tempo commerciale del 40% | 🔴 P0 |
| **Gemini 3.1 Pro Vision** via Universal Key | **OCR listino fornitori** (PDF/foto→JSON prezzi) | Nuovo router `/api/ai/vision/parse-pricelist` | Aggiornamento listini in 10 min anziché 8 ore | 🔴 **P0 killer feature** |
| **GPT Image / Nano Banana** via Universal Key | Anteprima render infisso su foto ambiente cliente | Configuratore visuale | Aumenta conversione preventivo | 🟠 P1 |
| **OpenAI Whisper** | Trascrizione note sopralluogo audio | App mobile → backend | Zero digitazione in cantiere | 🟠 P1 |
| **OpenAI TTS** | Lettura preventivo per cliente anziano/ipovedente | Preventivo PDF → audio | Nicchia ma differenziante | 🟢 P3 |
| **Embedding + Vector Search** | Ricerca semantica "trovami preventivi simili a Rossi 2024" | Serve vector DB (Qdrant/Atlas Vector) | Utile con 1000+ preventivi | 🟡 P2 |
| **Agent Framework** (LangGraph, CrewAI) | Auto-follow-up lead: agent legge conversazione, propone email | Complesso, richiede vector + memory | 🟡 P2 solo se team AI dedicato |
| **RAG** su capitolati storici | Trovare soluzioni tecniche già usate | Vector + LLM | 🟡 P2 |
| **Memory** conversazionale | Chat con cliente ricorrente | Conversazioni + LLM | 🟡 P2 |
| **Workflow AI** (auto-generazione preventivi) | Da fotografia sopralluogo → preventivo bozza | Vision + Text + template | 🟠 P1 differenziante |

**Regola d'oro**: prima **attivare 1-2 use case AI concreti** con quello che è già installato (Universal Key), poi valutare framework. Non installare `langchain` prima di aver dimostrato ROI su un endpoint.

---

## 4 · Plugin specifici settore serramenti

Questi sono il **vero differenziale competitivo**. La maggior parte dei competitor open-source ERP non li ha.

| Modulo | Libreria consigliata | Motivo | Priorità |
|---|---|---|---|
| **Motore ottimizzazione barre** (cutting stock 1D) | Custom Python: greedy + FFD + best-fit + PuLP (LP solver) o **rectpack** per 2D | Già presente `parametric_engine` + `nesting.py`? Verificare completezza. Con 15-20% risparmio sfrido = margine +3-5 pts | 🔴 **P0 esistente da verificare** |
| **Nesting 2D** (per lastre vetro/pannelli) | **rectpack** 0.2 (Python pure) o **shapely + custom** | Vetraio ottimizza taglio lastre 3210×2250 | 🟠 P1 |
| **CAD DXF** | **ezdxf 1.3** (Python, MIT) | Import disegno del rilevatore, export lista taglio per macchina CNC | 🔴 **P0 killer feature settore** |
| **SVG** | Native browser + custom | Anteprima quotature | ✅ già possibile |
| **Generazione liste taglio** | Custom + esistente `technical_cut_list` recipe | ✅ già presente in backend | ✅ USATO |
| **Import listini fornitori PDF** | **pdfplumber** + Gemini Vision (già installato!) | Vedi §3 — killer feature | 🔴 P0 |
| **Import listini XLS/CSV** | **openpyxl** + pandas + import router | ⚠️ verificare `PricelistImporterPage` esistente | ✅ presente (verificare) |
| **Configuratore grafico** finestra | **konva-react** — drag maniglie, resize, click aperture | Mostra al cliente il prodotto | 🟠 P1 |
| **Rendering ambienti** (foto stanza + finestra virtuale) | Gemini Vision + inpainting (Nano Banana) | Cliente vede la finestra installata a casa sua | 🟠 P1 |
| **Realtà aumentata mobile** | **model-viewer** (web component Google) per iOS/Android AR | Cliente vede modello 3D dell'infisso | 🟡 P2 |
| **Configuratore 3D** | **three.js** + react-three-fiber | Vista 3D infisso — pesante ma differenziante | 🟡 P2 |
| **Certificazione energetica** (CasaClima, ETIC-B) | Custom + input U-value + calcolo trasmittanza | Bonus ecobonus / conto termico | 🟠 P1 |
| **Preventivazione multi-listino** | Custom | Confronto fornitori | ✅ già presente |

---

## 5 · Integrazioni esterne (settore + Italia)

### 🔴 P0 — indispensabili per ERP italiano serramenti

| Servizio | Motivo | Complessità | Impatto business |
|---|---|---|---|
| **Fatturazione Elettronica (FE)** SDI via provider (**Aruba API**, Fatture in Cloud, Register.it) | OBBLIGO DI LEGGE B2B/B2C dal 2024 | Alta | 🔴 CRITICO — senza FE nessun cliente italiano ci passa il gestionale |
| **PEC (Aruba/InfoCert API)** | Invio contratti a PA e amministratori condominiali | Media | 🟠 |
| **ENEA (portale Ecobonus)** invio pratica | Cliente aspetta detrazione 50-65-75% — il commerciale che compila la pratica per lui vince il lavoro | Alta | 🔴 **P0 killer feature** |
| **Stripe** (già installato!) o **Nexi Xpay** | Acconti 30% online al momento della firma | Bassa (Stripe già in deps) | 🟠 P1 |
| **PagoPA** | Se lavorano con enti pubblici | Media | 🟡 P2 solo se target PA |

### 🟠 P1 — comunicazione cliente

| Servizio | Motivo | Priorità |
|---|---|---|
| **WhatsApp Business API** (via Twilio o Meta Cloud) | Cliente medio serramenti usa WhatsApp, non email | 🔴 P0 |
| **Twilio SMS** | Reminder appuntamenti sopralluogo | 🟠 P1 |
| **Google Calendar / Outlook API** | Sincronizza appuntamenti commerciali | 🟠 P1 |
| **Google Drive / OneDrive** | Backup file allegati | 🟢 P3 |

### 🟡 P2 — firma elettronica avanzata

| Servizio | Motivo |
|---|---|
| **DocuSign / Adobe Sign** | Firma qualificata per contratti >20k€ o con enti pubblici |
| Firma con **OTP+SMS+audit trail** custom | Già possibile con signature_pad + Twilio SMS — basta per B2C |

### 🟡 P2 — finanziamenti al cliente

| Servizio | Motivo |
|---|---|
| **Agos / Findomestic / DB Easy** API | Cliente rateizza il serramento — chiude più contratti |
| **Compass** | idem |

---

## 6 · Sicurezza

| Plugin | Stato | Priorità |
|---|---|---|
| **MFA** (multi-factor auth) | ❌ ASSENTE — input-otp installato ma non collegato a flow MFA | 🟠 P1 |
| **Audit avanzato** | ⚠️ `services/audit.py` esiste — verificare copertura | 🟠 verifica |
| **Intrusion detection** | ❌ non applicabile a SaaS multi-tenant senza WAF | 🟡 P2 (via Cloudflare/Emergent) |
| **CSP (Content Security Policy)** | ❌ non definita in Nginx/FastAPI middleware | 🟠 P1 |
| **Secret manager** | ✅ Emergent secrets (env) | ok |
| **Antivirus su upload** | ❌ ASSENTE — allegati sopralluogo, PDF importer non scansionati | 🟠 P1 (ClamAV o VirusTotal API) |
| **Backup** | ⚠️ MongoDB Atlas snapshot automatico se su Atlas, altrimenti manuale | 🔴 P0 verificare |
| **Disaster recovery** | ⚠️ non documentato RTO/RPO | 🟠 P1 |

---

## 7 · Performance

| Strumento | Stato | Priorità |
|---|---|---|
| **Caching** | Redis presente, usato solo per rate-limit | 🟠 P1 estendere |
| **Profiling** | ❌ py-spy non installato | 🟢 P3 ad hoc |
| **APM** | ❌ Sentry Performance | 🟠 P1 |
| **Query analysis** | ❌ MongoDB explain manuale | 🟡 P2 |
| **Bundle analyzer** | ❌ webpack-bundle-analyzer | 🟠 P1 (per rimuovere framer-motion/swr/lodash/dayjs = ~500kb) |
| **Lazy loading** | React.lazy nativo — verificare uso reale | 🟠 P1 |
| **Image optimization** | ❌ nessuno (uso `<img>` diretto) | 🟡 P2 (Next.js Image non applicabile a CRA — usare `sharp` server-side) |

---

## 8 · Esperienza utente

| Area | Stato | Consigliato |
|---|---|---|
| Onboarding | ⚠️ `OnboardingWizard.jsx` esiste — verificare qualità | react-joyride 2.7 |
| Tooltip intelligenti | ✅ Radix Tooltip presente, usato | — |
| Command palette | ⚠️ cmdk installato, componente base ma no "azioni globali" | Estendere cmdk con navigation + azioni |
| Ricerca globale | ⚠️ `SearchPage.jsx` esiste ma non è "instant" | Cmdk + backend `/api/search?q=` con aggregazione parallela (già presente) |
| Wizard | ✅ 1 wizard (Onboarding) | Estendere a: nuovo lead, nuovo preventivo, contratto |
| Autosave | ❌ ASSENTE — perdita dati se browser crasha | Draft con debounce `useEffect` 3s |
| Undo/Redo | ❌ ASSENTE — utile su preventivo lungo | Optional (react-command-menu) |
| Hotkeys | ❌ ASSENTE | react-hotkeys-hook 4 |
| Notifiche realtime | ⚠️ `NotificationsPage.jsx` polling? | SSE (EventSource) semplice → no WebSocket overhead |

---

## 9 · Classificazione finale

### 🔴 P0 — INDISPENSABILI prima del rilascio pubblico completo

1. **Fatturazione Elettronica** (Aruba/Fatture in Cloud API) — **obbligo legale**
2. **Portale ENEA** invio pratica ecobonus — **killer feature settore**
3. **OCR listini fornitori** via Gemini Vision (già installato) — **killer feature**
4. **WhatsApp Business** (Twilio o Meta Cloud) — canale di comunicazione principale
5. **Scheduler backend** (APScheduler async) — follow-up, reminder, cleanup
6. **Sentry SDK backend** — visibilità errori produzione
7. **CAD DXF** (ezdxf) — export lista taglio CNC + import disegno rilevatore
8. **Backup verifica**: assicurarsi che MongoDB abbia snapshot automatici + procedura restore documentata
9. **Firma canvas mobile-first** (react-signature-canvas + audit trail) — UX_ARCH V2 Fase 3

### 🟠 P1 — molto consigliati (entro 3-6 mesi)

10. Cache Redis su lookup catalog/pricelist (già installato)
11. AI text (Claude Sonnet 5) per redazione capitolato/email
12. PDF viewer inline (react-pdf) — preventivo/contratto nel browser
13. Table virtualizzata `@tanstack/react-virtual` — liste lunghe
14. Drag & drop `@dnd-kit/core` — riordino vani/aperture
15. Upload avanzato `react-dropzone` — sopralluoghi
16. Stripe payments (già installato)
17. Ricerca full-text (MongoDB text index o Meilisearch)
18. MFA con OTP (input-otp già installato)
19. QRCode su contratti firmati
20. Antivirus su upload (ClamAV)
21. Notifiche real-time via SSE (Server-Sent Events)
22. Bundle analyzer + cleanup framer-motion/swr/lodash/dayjs

### 🟡 P2 — miglioramenti

- Konva canvas configuratore grafico
- Vector DB + RAG su capitolati storici
- APM + OpenTelemetry
- Compass/Agos finanziamenti
- Google Calendar sync
- Rich text editor (tiptap)

### 🟢 P3 — opzionali

- Realtà aumentata (model-viewer)
- Vision AI OCR client-side (tesseract.js)
- TTS lettura preventivo
- DocuSign qualified sign

---

## 10 · Report finale con punteggi

### 🗑️ Plugin da RIMUOVERE (installati, mai importati — ~500kb bundle sprecato)

| Plugin | Stato | Azione |
|---|---|---|
| `swr` (frontend) | 0 uso, react-query fa lo stesso | 🗑️ `yarn remove swr` |
| `framer-motion` (frontend) | 0 uso, ~100kb | 🗑️ `yarn remove framer-motion` |
| `dayjs` (frontend) | 0 uso, date-fns già presente | 🗑️ `yarn remove dayjs` |
| `lodash` (frontend) | 0 uso, `@types/lodash` idem | 🗑️ `yarn remove lodash @types/lodash` |
| `pymupdf` (backend) | 0 uso, weasyprint fa i PDF | 🗑️ verificare — se non usato, `pip remove` |
| `websockets` (backend) | 0 uso | 🗑️ oppure attivare per notifiche |
| `tenacity` (backend) | 0 uso | 🟡 USARE per retry email/S3 |
| `stripe` (backend) | 0 uso | 🟡 USARE per Stripe integration |
| `huggingface_hub` (backend) | 0 uso | 🗑️ dep transitiva? verificare |
| `tiktoken` (backend) | 0 uso, forse dep transitiva di litellm | 🗑️ o mantenere transitivo |
| `litellm`, `openai`, `google-genai` | 0 uso diretto (via emergentintegrations) | 🟡 mantenere solo se emergentintegrations li usa internamente |

### ⚠️ Dipendenze OBSOLETE / da aggiornare

| Package | Attuale | Ultima | Rischio |
|---|---|---|---|
| `motor` | 3.3.1 | 3.6+ | Basso — upgrade a Motor 3.6 supporta MongoDB 8 |
| `fastapi` | 0.110.1 | 0.115+ | Basso — ma migrations minori |
| `redis` | 8.0.1 | 5.x è quella corretta (major "8" è errata?) — **verificare** | ⚠️ da controllare |
| `bcrypt` | 4.1.3 | 4.2+ | Basso |
| React | 19.0.0 | 19.0.0 | ok |

### Scoring dei plugin proposti (1-10)

Legenda: **U**tilità · **I**mpatto · **C**omplessità implementazione (10=facile) · **R**OI · **P**riorità.

| Plugin | U | I | C | ROI | P | Score |
|---|---|---|---|---|---|---|
| Fatturazione Elettronica (Aruba API) | 10 | 10 | 5 | 10 | 10 | **P0** |
| Portale ENEA ecobonus | 10 | 10 | 4 | 10 | 10 | **P0** |
| OCR listini via Gemini Vision | 10 | 9 | 8 | 10 | 10 | **P0** |
| WhatsApp Business (Twilio) | 10 | 9 | 8 | 9 | 9 | **P0** |
| APScheduler async | 9 | 9 | 9 | 9 | 10 | **P0** |
| Sentry backend | 9 | 10 | 10 | 10 | 10 | **P0** |
| ezdxf (CAD DXF export CNC) | 10 | 9 | 6 | 9 | 9 | **P0** |
| react-signature-canvas mobile | 9 | 9 | 8 | 9 | 10 | **P0** |
| MongoDB backup verify | 10 | 10 | 10 | 10 | 10 | **P0** |
| Redis cache dati (già installato!) | 8 | 8 | 9 | 9 | 8 | P1 |
| Claude Sonnet 5 text | 9 | 8 | 9 | 8 | 8 | P1 |
| react-pdf viewer | 7 | 7 | 9 | 8 | 7 | P1 |
| @tanstack/react-virtual | 7 | 6 | 9 | 8 | 7 | P1 |
| @dnd-kit/core | 8 | 7 | 8 | 7 | 7 | P1 |
| react-dropzone | 7 | 6 | 10 | 8 | 7 | P1 |
| Stripe (già installato!) | 8 | 7 | 8 | 7 | 7 | P1 |
| MongoDB text search / Meilisearch | 8 | 8 | 7 | 8 | 7 | P1 |
| Input-otp MFA hook | 8 | 8 | 8 | 8 | 7 | P1 |
| ClamAV upload scan | 6 | 8 | 6 | 6 | 7 | P1 |
| Bundle analyzer + cleanup deps | 6 | 6 | 10 | 7 | 8 | P1 |
| Konva configuratore | 8 | 7 | 5 | 6 | 5 | P2 |
| Nano Banana render infisso | 8 | 8 | 6 | 7 | 6 | P2 |
| Vector DB + RAG | 6 | 6 | 5 | 5 | 4 | P2 |
| DocuSign qualified sign | 6 | 6 | 6 | 5 | 4 | P2 |
| Three.js configuratore 3D | 6 | 6 | 3 | 5 | 3 | P3 |
| Tesseract.js client OCR | 5 | 5 | 7 | 4 | 3 | P3 |
| Realtà aumentata (model-viewer) | 5 | 5 | 7 | 4 | 3 | P3 |

### Rischi

1. **Dipendenza da emergentintegrations** — se il servizio Emergent AI ha downtime, OCR listini e AI text si fermano. Mitigazione: cache aggressiva + fallback graceful.
2. **Stripe key non presente in .env** — verificare prima di attivare pagamenti online
3. **Nessun monitoring produzione** — errori 500 come BUG-16 latente potrebbero passare inosservati fino al reclamo cliente
4. **Backup MongoDB non verificato** — se il tenant PanoramaPilot fa un errore, non c'è procedura documentata di restore

### Effort stimato per P0 (roadmap 8-12 settimane)

| Item | Effort (giorni) | Dipendenze |
|---|---|---|
| Cleanup deps inutilizzate + bundle analyzer | 1 | — |
| Sentry SDK backend + frontend | 2 | Sentry account |
| APScheduler + primi 3 job cron | 3 | — |
| MongoDB backup + procedura restore documentata | 2 | Atlas o VPS |
| Firma canvas mobile-first | 5 | UX_ARCH Fase 3 approvata |
| Aruba Fatturazione Elettronica API | 8 | Aruba account + P.IVA |
| Portale ENEA API | 10 | Delega ENEA + credenziali |
| OCR listini Gemini Vision | 6 | Universal Key (già presente) |
| WhatsApp Business (Twilio) | 5 | Twilio account |
| ezdxf export lista taglio | 6 | Confronto con macchine CNC utente |
| **TOTALE P0** | **~48 giorni-uomo** | |

---

## Regola cardine ricordata

Prima di installare qualsiasi nuova libreria: **verificare se una già presente e sotto-utilizzata risolve lo stesso problema**. Panorama Pilot ha già installate 8+ librerie mai importate — ripulirle è il primo guadagno di performance/manutenzione senza toccare business logic.

---

**Documento chiuso.** Attende decisione utente su:
1. Cleanup deps inutilizzate (safe, 30 min)
2. Prioritizzazione P0 (roadmap 8-12 settimane)
3. Attivazione Sentry + APScheduler (quick wins ~2 giorni)
