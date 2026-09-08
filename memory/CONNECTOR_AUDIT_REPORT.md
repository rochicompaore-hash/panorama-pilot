# CONNECTOR AUDIT REPORT — Panorama Pilot / Infissi Express
**Data**: 2026-09-08 · **Tipo**: SOLO ANALISI (nessun codice, SDK, schema, dependency o webhook modificato) · **Stato**: CONNECTOR_AUDIT = COMPLETE

## 0. Base di analisi (stato reale del software)
Moduli già presenti in Panorama (router/servizi): CRM interno (leads, contacts, customers, sites, pipelines, timeline, landing/public form), preventivatore (quotes, multi-cat configurator, pricing v3, margin engine, payment terms, delivery policy, PDF), contratti + **firma interna OTP con evidence** (`signature.py`, `signature_provider.py` astratto, `otp.py`), rilievi (`surveys`), ordini di vendita, acquisti (`purchasing`), produzione (`production`, BOM, nesting), magazzino (`inventory`), logistica (`logistics`), assistenza (`service_tickets`), tesoreria/finanza (`treasury`, `admin_finance`, `management_control`, `margin_control`, `bi`, `ai_cfo`), appuntamenti interni (`appointments`), notifiche interne, audit log, email (provider astratto: Resend API o SMTP; IMAP config presente; `email_logs`), WhatsApp (astrazione: mock + stub Twilio), storage (astrazione Local / S3-compatible), rate limiting/OTP con Redis, sequences/numerazioni, multi-tenant con `tenant_id` su ogni collezione e RBAC a permessi.

Conseguenza: **non servono connettori che duplicano CRM, firma semplice, storage, ticketing, BI, magazzino**. Servono connettori dove il dato deve **entrare/uscire dall'azienda** o dove esiste un **obbligo amministrativo/legale** che Panorama non può assolvere da solo (fatturazione elettronica, banca, PEC, ENEA, fornitori).

Legenda priorità: **P0** fondamentale · **P1** molto importante · **P2** utile · **P3** futuro. Complessità: S/M/L/XL (dev / manutenzione).

## 1. Analisi per area (SERVE / NON SERVE / PIÙ AVANTI)
| Area | Verdetto | Note |
|---|---|---|
| A. EMAIL ordinaria | **SERVE (P0)** — già parzialmente presente | Invio transazionale (Resend/SMTP) esiste. Manca la **ricezione + associazione automatica** (IMAP configurato ma non operativo): senza inbound, il commerciale torna sul client di posta. Provider: SMTP/IMAP del dominio aziendale o Resend/Postmark per outbound + IMAP idle/poll per inbound. Storico, allegati → storage interno, tracking aperture (webhook provider). |
| B. PEC | **SERVE (P1, diventa P0 con SDI/contratti)** | Separata dall'email: valore legale (ricevute di accettazione/consegna da protocollare). Invio contratti firmati, solleciti, comunicazioni formali. Integrazione corretta: **SMTP/IMAP PEC del gestore** (Aruba/Legalmail/Namirial) con parsing ricevute `daticert.xml` e protocollazione nel timeline cliente/commessa. Nessuna API "moderna": adapter SMTP/IMAP dedicato. |
| C. WHATSAPP / SMS / VoIP | WhatsApp **SERVE (P1)**, SMS **P2** (fallback OTP/notifiche), VoIP/call tracking **P3** | Astrazione WhatsApp già presente (Twilio stub). Valore reale: conferme appuntamento rilievo/posa, avviso merce pronta, richiesta acconto, link firma/PDF, con log in timeline. WhatsApp Business Cloud API (Meta) o Twilio. Telefonia/registrazione chiamate: complessità e privacy alte, ROI basso ora. |
| D. CALENDARIO | **SERVE PIÙ AVANTI (P2)** | Appuntamenti interni esistono. Google/Microsoft Calendar sync (bidirezionale, OAuth per utente) utile per commerciali/posatori sul telefono; alternativa a costo zero: **export ICS + inviti email** (già fattibile con l'email). |
| E. FIRMA ELETTRONICA | **NON SERVE ORA (P2/P3)** | Firma interna OTP + audit trail/evidence = **FES** adeguata per preventivo/contratto B2C/B2B con tracciabilità. FEA/qualificata (Namirial, Yousign, DocuSign) solo se richiesto da banche/finanziarie o contenziosi. `signature_provider.py` è già un adapter astratto → aggiunta futura non invasiva. |
| F. PAGAMENTI | **SERVE (P1)** — payment link per acconto | Flusso CONTRATTO → ACCONTO ATTESO → INCASSO → SALDO → STATO è già modellabile con payment_schedule. Serve un provider per **payment link/carta** (Stripe, o Nexi/Satispay per contesto IT) con webhook → riconciliazione automatica dell'acconto. Bonifici restano prevalenti nel settore → vedi J. |
| G. FINANZIAMENTI CLIENTE | **SERVE PIÙ AVANTI (P2, adapter-based)** | Le finanziarie consumer (Compass, Agos, Findomestic, Cofidis) offrono di norma **portali dealer**, raramente API pubbliche; quando esistono sono su convenzione. Modello dati: `financing_request {quote_id, provider, amount, deposit, status, reference, documents[]}`; architettura **adapter con fallback manuale** (stato aggiornato a mano + upload esito). Non inventare API. |
| H. CONTABILITÀ / FATTURAZIONE | **SERVE (P0)** — Panorama NON deve diventare software contabile | Scelta **B**: ERP operativo che **esporta** a un gestionale contabile/commercialista (TeamSystem, Zucchetti, Fatture in Cloud, Aruba, Danea…). Dati in uscita: cliente, contratto, acconto/fattura di acconto, saldo, nota credito, IVA (10%/22%, detrazione), incassi. Motivazione: partita doppia, adempimenti fiscali, F24, bilancio = dominio del commercialista; duplicarlo è rischio compliance e zero valore competitivo. Connector categories indispensabili: **anagrafiche + documenti fiscali (export XML/CSV/API) + incassi**. |
| I. FATTURAZIONE ELETTRONICA / SDI | **SERVE (P0)** via **provider intermediario** | Collegamento diretto SDI (SDICoop/SDIFTP, accreditamento, certificati) è sproporzionato per una PMI. Raccomandazione: **intermediario** (Aruba, Fatture in Cloud API, TeamSystem, Zucchetti, Openapi) che gestisce XML FatturaPA, codice destinatario/PEC, stato consegna, ricevute (RC/NS/MC), **conservazione a norma 10 anni**. Panorama genera i dati fattura (acconto/saldo) e riceve lo stato. |
| J. HOME BANKING / RICONCILIAZIONE | **SERVE (P1)** | Nel settore l'80%+ degli incassi è bonifico. Senza riconciliazione l'amministrazione lavora su due schermi. Opzioni: **PSD2/Open Banking aggregator** (Fabrick, Tink, Salt Edge, Yapily — API standard) oppure import CBI/CAMT.053 dall'home banking. Matching su causale/importo/cliente → aggiorna payment_schedule e commissioni. |
| K. ENEA / DETRAZIONI | **NON automatizzabile via API (P2 = workflow assistito)** | Il portale ENEA (detrazioni) **non espone API pubbliche**; RPA sul portale è fragile e non consigliato. Livello realistico: **precompilazione dati + export/checklist** (dati cliente, immobile, trasmittanze/certificazioni prodotto, importi) e stato pratica gestito a mano (ENEA_STANDARD/INSURED già nel preventivo). Automazione: L0-L1. |
| L. CLOUD STORAGE / DOCUMENTI | **NON SERVE connector** (P3) | Storage interno S3-compatible già astratto: è il sistema documentale. Un connector Drive/SharePoint serve solo per **export/backup copia** o per chi lavora già su Drive; non come sorgente. |
| M. FORNITORI / ORDINI | **SERVE (P1, adapter-based)** | Flusso QUOTE→ordine fornitore→conferma→merce pronta→consegna esiste in `purchasing`. I fornitori serramenti (profili, vetro, tapparelle) di norma **non hanno API**: portali, email + PDF/XLS/CSV, a volte EDI. Architettura: `SupplierOrderAdapter` con canali `EMAIL_PDF` (default, immediatamente utile), `CSV/XML_EXPORT`, `PORTAL_MANUAL`, `API` futuro. Inbound: parsing conferme (email strutturata) con stato ordine. |
| N. CORRIERI / LOGISTICA | **SERVE PIÙ AVANTI (P2)** | Consegne prevalentemente con mezzi propri/trasportatori locali: POD e firma consegna coperti dal modulo logistica interno (foto + firma su mobile). Tracking corrieri (GLS/BRT/DHL API) solo per accessori/ricambi. |
| O. MAPPE / GEOCODING | **SERVE (P1)** | Indirizzo cantiere ora obbligatorio → geocoding + distanza/tempi per pianificare rilievi/pose e calcolare costi trasferta. Google Maps Platform / Mapbox / OpenStreetMap (Nominatim+OSRM, zero costo). Ottimizzazione agenda = P2. |
| P. RECENSIONI | **P3** | Richiesta recensione Google post-collaudo via WhatsApp/email (usa i connettori A/C, nessun connector dedicato). |
| Q. CRM / LEAD SOURCES | CRM esterno **NON SERVE**; lead intake **SERVE (P1)** | CRM interno esiste. Serve l'**ingresso automatico lead**: webhook form sito/landing (già `public`/`landing`), **Meta Lead Ads** (Graph API webhook), Google Ads lead form, email parsing. Zero import manuale. |
| R. ADVERTISING | **P3** | Reporting spesa/conversioni: BI futura. Le conversioni offline (contratto firmato) verso Meta/Google = P3. |
| S. CUSTOMER PORTAL | **NON è un connector** | Link pubblici PDF/firma esistono; portale = feature interna futura. |
| T. TICKETING | **NON SERVE** | `service_tickets` interno; canale d'ingresso = email/WhatsApp (A/C). |
| U. PRODUZIONE / MACCHINARI | **P3 (architettura generica)** | `MachineAdapter` con export standard: distinta taglio CSV/XML, etichette ZPL/PDF, piani di produzione. Nessuna macchina assunta. Nesting e BOM già interni. |
| V. MAGAZZINO / BARCODE | **P2 hardware, nessun SaaS** | Barcode/QR generati internamente; scanner = tastiera HID / camera browser; stampanti etichette = PDF/ZPL. Nessun connector SaaS necessario. |
| W. PAGHE / HR | **NON SERVE (P3)** | Fuori dominio: export ore/presenze posatori al consulente del lavoro (CSV) al massimo. |
| X. BI / REPORTING | **NON SERVE connector** | BI interna (`bi`, `management_control`, `ai_cfo`). Export CSV/Excel verso Power BI/Sheets = P3. |
| Y. BACKUP / MONITORING / ERROR TRACKING | **SERVE (P0 infrastrutturale)** | Non commerciale ma indispensabile per produzione: error tracking (Sentry o equivalente self-host GlitchTip), uptime monitor (Better Uptime/Uptime Kuma), backup Mongo giornaliero cifrato con restore test, alerting (email/Telegram), audit/security log già interno. |

## 2. Tabella master
| Connector / Area | Problema risolto | Dati IN | Dati OUT | Bidir. | Priorità | Motivo | Rischio senza | Implementazione indicativa | Provider / dependency | Lock-in | Security / privacy |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Email outbound+inbound (dominio) | Comunicazioni cliente/fornitore dentro Panorama con storico | mail ricevute, allegati, tracking | preventivi, PDF, link firma, notifiche | YES | **P0** | Senza inbound si torna al client di posta | Re-entry, storico frammentato | Outbound già presente; inbound IMAP poll + matching su email/quote ref | SMTP/IMAP aziendale, Resend/Postmark (webhook) | Basso | Credenziali per tenant cifrate, OAuth2 (M365/Google) se possibile, no PII nei log |
| PEC | Valore legale contratti/solleciti, ricevute protocollate | ricevute accettazione/consegna, PEC in ingresso | contratti firmati, comunicazioni formali | YES | **P1** (P0 se contratti solo via PEC) | Obbligo formale su alcune comunicazioni | Prove legali fuori sistema | Adapter SMTP/IMAP PEC + parser daticert.xml + protocollo | Aruba PEC / Legalmail / Namirial | Basso (standard) | Credenziali cifrate, conservazione ricevute |
| Fatturazione elettronica (SDI via intermediario) | Fattura acconto/saldo/nota credito senza reinserimento | stati SDI, ricevute, conservazione | XML FatturaPA (dati cliente, righe, IVA, detrazione) | YES | **P0** | Obbligo di legge; oggi doppio inserimento | Errori fiscali, tempo amministrazione | Adapter `EInvoiceProvider` (create/send/status/PDF) + mapping IVA 10/22 + bollo | Aruba, Fatture in Cloud, TeamSystem, Zucchetti, Openapi | Medio (dati esportabili in XML standard) | API key per tenant, dati fiscali, log firmati |
| Contabilità esterna (export) | Commercialista riceve tutto senza chiedere | piano conti/codici (config) | anagrafiche, documenti, incassi, scadenzario | NO→YES | **P0** (export) | Panorama resta ERP operativo | Riconciliazioni manuali mensili | Export periodico CSV/XML + API dove disponibile | dipende dal gestionale del commercialista | Medio | Export cifrato, audit |
| Open Banking / riconciliazione | Incassi bonifico → stato pagamento automatico | movimenti conto (PSD2/CAMT) | — | NO | **P1** | 80% incassi via bonifico | Stato pagamenti non affidabile, commissioni sbagliate | Aggregator PSD2 + matching regole causale/importo + coda eccezioni | Fabrick / Tink / Salt Edge / import CAMT.053 | Medio | Consenso PSD2 90 gg, dati bancari sensibili, cifratura at-rest |
| Payment link (carta/SDD) | Acconto pagato in 1 click dal PDF/WhatsApp | webhook pagamento | link/importo/causale | YES | **P1** | Riduce tempi incasso acconto | Solleciti manuali | Provider link + webhook firmato → payment_schedule | Stripe (test key già in env) / Nexi / Satispay | Basso | Webhook signature, nessun dato carta in Panorama |
| WhatsApp Business API | Conferme, avvisi merce pronta, link firma/pagamento con log | risposte cliente | template messages | YES | **P1** | Canale dominante B2C in Italia | Comunicazioni fuori sistema | Astrazione esistente → Twilio o Meta Cloud API, template approvati | Meta / Twilio | Medio (template) | Opt-in GDPR, webhook signature, retention |
| Lead intake (Meta Lead Ads, form sito, Google) | LEAD → CRM senza import | lead payload | — | NO | **P1** | Zero re-entry commerciale | Lead persi/ritardi | Webhook endpoint per tenant + dedupe telefono/email | Meta Graph API, form sito (già), Google Ads | Basso | Token app per tenant, consenso privacy |
| Maps / geocoding | Cantiere geolocalizzato, distanze/tempi rilievo-posa | coordinate, distanza, ETA | indirizzi | NO | **P1** | Pianificazione posa/rilievi reale | Costi trasferta a stima | Geocode on save site + matrix distanze | Google Maps / Mapbox / OSM (Nominatim+OSRM) | Basso | API key server-side, cache |
| Supplier order adapter (email PDF/CSV/portale) | Ordine fornitore generato e tracciato | conferme ordine (email/PDF) | ordine PDF/CSV/XML | YES (parziale) | **P1** | Fornitori senza API | Ordini a mano su portali | `EMAIL_PDF` canale default + stato manuale + parser conferme | fornitori serramenti/vetro/tapparelle | Basso | Email fornitore, nessun dato cliente non necessario |
| Calendar (Google/M365) | Agenda commerciale/posa sincronizzata | eventi esterni | appuntamenti | YES | P2 | Comodità mobile | Doppie agende | OAuth per utente + ICS | Google / Microsoft | Medio | OAuth token per utente cifrati |
| Finanziamenti (adapter + manuale) | Stato pratica finanziaria nel contratto | esito pratica | richiesta + documenti | YES (dove API) | P2 | Poche API pubbliche | Stato fuori sistema | Modello dati + adapter manuale ora | Compass/Agos/Findomestic (convenzione) | Alto se API proprietaria | Dati reddituali: minimizzazione, cifratura |
| Corrieri tracking | Tracking accessori/ricambi | stato spedizione | — | NO | P2 | Consegne prevalentemente proprie | Basso | Adapter per corriere | GLS/BRT/DHL | Basso | — |
| SMS fallback | OTP/notifiche se no WhatsApp | delivery status | SMS | YES | P2 | Fallback | Basso | Twilio/Skebby | Twilio / Skebby | Basso | Numeri telefono |
| ENEA (workflow assistito) | Pratica ENEA precompilata | — | export dati/checklist | NO | P2 | Nessuna API pubblica | Ore amministrative | Export PDF/CSV + stato manuale | — | — | Dati immobile/cliente |
| Firma FEA/qualificata | Firma rafforzata per casi speciali | stato busta | documento | YES | P3 | FES interna sufficiente | — | `signature_provider` adapter | Namirial/Yousign/DocuSign | Alto | Identità firmatario |
| Drive/SharePoint export | Copia documenti per chi vive su Drive | — | PDF/documenti | NO | P3 | Storage interno sufficiente | — | Export job | Google/Microsoft | Medio | OAuth |
| Machine/production adapters | Export taglio/etichette | conferme | CSV/XML/ZPL | NO | P3 | Nessuna macchina definita | — | Export standard | — | — | — |
| Ads conversions / BI export | Conversioni offline, report | — | eventi | NO | P3 | Marketing | — | — | Meta/Google | Medio | Consent |
| Error tracking / uptime / backup | Produzione osservabile e ripristinabile | alert | log/errori/backup | NO | **P0 infra** | Senza backup testato non si va live | Perdita dati | Sentry-like + uptime + dump Mongo cifrato + restore test | Sentry/GlitchTip, Uptime Kuma, S3 | Basso | Scrub PII negli eventi |

## 3. TOP 10 connector (impatto operativo reale)
1. **Fatturazione elettronica via intermediario (SDI)** — unico obbligo di legge non coperto; chiude CONTRATTO→ACCONTO→FATTURA senza reinserimento; sblocca il commercialista.
2. **Email inbound + associazione automatica** — l'outbound c'è; senza inbound il commerciale vive nel client di posta e lo storico cliente è monco.
3. **Riconciliazione incassi (Open Banking / CAMT)** — trasforma payment_schedule in stato pagamento reale; senza, commissioni e saldo restano "a fiducia".
4. **Export contabilità** — un solo dato verso il gestionale del commercialista (anagrafiche, documenti, incassi); evita di trasformare Panorama in software contabile.
5. **WhatsApp Business API** — canale dominante del cliente finale: conferme rilievo/posa, merce pronta, link firma/pagamento, tutto loggato in timeline (astrazione già pronta).
6. **Lead intake automatico (Meta Lead Ads + form sito)** — LEAD→CRM senza import; il CRM interno esiste, manca solo la porta d'ingresso.
7. **Payment link acconto (Stripe/Nexi)** — acconto pagato dal PDF/WhatsApp con webhook che chiude la rata; riduce il ciclo d'incasso.
8. **PEC** — contratti firmati e comunicazioni formali con ricevute protocollate nel fascicolo commessa; valore legale che la mail ordinaria non ha.
9. **Maps/geocoding** — cantiere obbligatorio ⇒ distanze e tempi per pianificare rilievi/pose e costi trasferta reali.
10. **Supplier order adapter (email PDF/CSV)** — ordini fornitore emessi da Panorama anche senza API, con stato e conferme nel flusso produzione.

## 4. MUST-HAVE prima di poter definire Panorama "gestionale unico" (max 5)
1. **Fatturazione elettronica SDI (intermediario)** — altrimenti ogni contratto viene rifatturato a mano altrove.
2. **Email inbound/outbound integrata con timeline** — altrimenti la comunicazione vive fuori.
3. **Riconciliazione incassi bancari** — altrimenti lo stato pagamenti/commissioni non è affidabile.
4. **Export contabilità verso il commercialista** — altrimenti l'amministrazione reinserisce.
5. **Monitoring + backup/restore testato** (infra, non commerciale) — altrimenti non si può andare in produzione con dati aziendali unici.
WhatsApp e lead intake sono i primi P1 subito dopo: alto ROI ma l'azienda può operare qualche settimana senza.

## 5. TOP 5 connector da NON fare ora
1. **CRM esterno (HubSpot/Salesforce/Pipedrive)** — duplica il CRM interno, doppio dato, lock-in.
2. **Firma qualificata/FEA esterna (DocuSign/Namirial)** — la FES interna con OTP+evidence copre il caso d'uso; costo per busta e complessità identità.
3. **Collegamento diretto SDI (SDICoop/FTP)** — accreditamento, certificati, conservazione in casa: sproporzionato; usare intermediario.
4. **RPA su portale ENEA** — fragile, nessuna API, rischio blocco pratiche; workflow assistito è la strada.
5. **VoIP/call recording, ads conversions, machine connectors** — ROI basso in questa fase, privacy/complessità alti, nessuna macchina definita.

## 6. Architettura — raccomandazione
Stato attuale: esistono già **adapter puntuali** (`storage.py` Local/S3, `email_service.py` Resend/SMTP, `whatsapp.py` mock/Twilio, `signature_provider.py` ABC, `rate_limiter` su Redis, `audit`). Il sistema è quindi **pronto per un pattern ConnectorAdapter per-servizio**, ma **non** ha ancora un layer trasversale. Prima della WAVE 1 conviene introdurre (futuro, non ora) un **IntegrationHub minimale**:
- `integration_connections` (tenant_id, provider, kind, status, config non sensibile, secret_ref, created_by) — **tenant-scoped, nessuna credenziale condivisa**;
- **secret storage** cifrato at-rest (chiave master da env/KMS, mai nel frontend, rotazione versionata);
- **webhook gateway** `/api/integrations/{provider}/webhook/{connection_id}` con verifica firma, idempotency key (event_id) e coda;
- **sync jobs** (cron piattaforma già disponibile) con retry esponenziale, `integration_events` (audit), **dead-letter** per eventi falliti con replay manuale;
- permessi RBAC dedicati (`integrations.manage` admin tenant; Platform Owner solo provisioning), sync state per connessione;
- osservabilità: contatori successi/fallimenti per connessione, alert.
Multi-tenant: ogni chiamata esterna parte da una `connection` risolta per `tenant_id`; webhook mappati per `connection_id` → tenant; audit su ogni scambio; PII minimizzata nei log.
Sicurezza per connettori sensibili (banca, SDI, PEC): OAuth2/PSD2 dove disponibile, API key cifrate, webhook signature obbligatoria, rotazione periodica, log di accesso ai segreti.

## 7. Roadmap consigliata
- **WAVE 1 — fondamentali (dopo Release Gate)**: IntegrationHub minimale (connections, secrets, webhook gateway) → Fatturazione elettronica via intermediario → Email inbound + associazione → Monitoring/backup (infra, anche prima del go-live). *Dipendenze*: numerazioni/sequences stabili (fatture), payment_schedule (già), storage S3 in produzione.
- **WAVE 2 — automazioni operative**: WhatsApp Business (template) → Lead intake (Meta/form) → Payment link acconto → Maps/geocoding → Supplier order adapter email/PDF. *Dipendenze*: Hub webhook + timeline eventi.
- **WAVE 3 — amministrazione/finanza avanzata**: Open Banking riconciliazione → Export contabilità completo → PEC protocollata → Finanziamenti adapter (manuale→API). *Dipendenze*: fatturazione attiva, scadenzario.
- **WAVE 4 — produzione/BI/AI**: Calendar sync, corrieri, machine adapters (taglio/etichette), export BI, conversioni ads, firma FEA se richiesta.

## 8. Risposta alla domanda finale
**"Se Panorama andasse in produzione domani, quali connector mancano davvero per usarlo ogni giorno senza tornare su altri software?"**
Concretamente tre, più uno infrastrutturale: (1) **fatturazione elettronica** — oggi acconto e saldo andrebbero riscritti nel software di fatturazione; (2) **email in ingresso collegata a cliente/preventivo** — oggi la posta si legge altrove e nulla finisce nel fascicolo; (3) **riconciliazione bancaria** — oggi si controlla l'home banking a mano per sapere se l'acconto è arrivato e sbloccare produzione/commissioni; (4) **backup/monitoring** per poter dormire. Tutto il resto (WhatsApp, lead ads, payment link, PEC, maps, fornitori) aumenta molto l'efficienza ma non obbliga a "tornare su altri software" per lavorare: preventivazione, contratto, firma, rilievo, produzione, posa, assistenza e controllo margini sono già interni.

---
**CONNECTOR_AUDIT = COMPLETE** — nessun connector implementato. Prossimo step: PRE-RELEASE CLEANUP residuo (`/api/sequences`, full suite chunked 0F/0E, tenant/RBAC E2E, frontend build) → GENERAL PRE-PRODUCTION RELEASE GATE.
