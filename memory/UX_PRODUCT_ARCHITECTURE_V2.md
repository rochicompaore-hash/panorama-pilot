# Panorama Pilot — UX & Product Architecture v2

**Autore**: Design partner  
**Versione**: 2.0 — Reset architetturale  
**Data**: Feb 2026  
**Stato**: DRAFT — In attesa di approvazione del Product Owner  
**Ambito**: definizione dell'esperienza utente completa PRIMA di qualunque nuova implementazione  
**Regola vincolante**: nessun codice viene modificato finché questo documento non è approvato.

---

## 0 · Executive Summary

Panorama Pilot v1 è stato costruito **per pagine** (CRUD + tabelle + form). Ogni funzione ha ricevuto una route dedicata. Il risultato: 64 route frontend, 3 pagine diverse per fare lo stesso preventivo, un motore di calcolo perfetto ma sconnesso dal flusso operativo, una firma canvas non utilizzabile da smartphone.

Panorama Pilot v2 sarà costruito **per processo**. Un solo motore, un solo flusso, un solo modo di fare le cose. Il commerciale non deve mai chiedersi "in quale pagina vado?", perché la piattaforma lo accompagna lungo il percorso naturale della vendita di serramenti:

> **Lead → Cliente → Preventivo → Contratto → Firma → Produzione → Consegna → Assistenza**

Ispirazione: la linearità di **DocuSign**, la pipeline di **Pipedrive**, la velocità di **Linear**, la chiarezza numerica di **Stripe**, la contextuality di **HubSpot**, la keyboard-first culture di **Figma**. Non copiare. Applicare i principi al mondo serramenti.

Il commerciale userà v2 in due contesti principali: (1) in ufficio davanti al desktop, (2) **a casa del cliente con lo smartphone in mano**. Il design deve funzionare in entrambi, con le stesse funzionalità.

---

## 1 · Filosofia del prodotto

### 1.1 Cosa NON siamo
- Non siamo un CRM generico. Salesforce lo fa meglio.
- Non siamo un sistema di fatturazione. Fatture in Cloud lo fa meglio.
- Non siamo un configuratore CAD. AutoCAD lo fa meglio.

### 1.2 Cosa SIAMO
Siamo l'unico posto dove **un commerciale italiano di serramenti** completa in massimo 20 minuti il percorso "voglio un preventivo per una finestra" → "contratto firmato dal cliente". Tutto il resto della piattaforma esiste solo per supportare questo percorso.

### 1.3 I sei principi fondanti

**P1 · Un solo modo di fare le cose**  
Se ci sono due percorsi per creare un preventivo, uno dei due è sbagliato. Un motore, un editor, un flusso.

**P2 · Il motore calcola, l'utente configura**  
Il commerciale sceglie prodotto, misure, colore, vetro. Il prezzo appare. Non lo digita mai. Se il motore non sa calcolare (dato mancante) lo dice chiaramente, non mette zero.

**P3 · La velocità è una feature**  
Command palette `Cmd+K` ovunque. Scorciatoie da tastiera. Nessun modal per operazioni frequenti. Ricerca fulminea.

**P4 · Mobile-first per il commerciale**  
Il commerciale è nel salotto del cliente. Deve poter creare, firmare e inviare il contratto dal telefono senza friction. Se una feature funziona meglio su desktop che su mobile, è progettata male.

**P5 · Il contesto vive con te**  
Quando lavori su un preventivo, vedi il cliente. Quando lavori sul cliente, vedi lo storico. Nessun click per "tornare indietro a vedere chi è". Pannello destro sempre attivo con il contesto rilevante (pattern HubSpot).

**P6 · Il numero grande è la verità**  
Il prezzo finale del preventivo è il pezzo di informazione più importante di quella schermata. Deve essere il più grande. Il resto è supporto (pattern Stripe).

### 1.4 Antipattern che elimineremo
- Tabelle con 15 colonne
- Modal dentro modal
- "Sei sicuro?" per operazioni non distruttive
- Salvataggio manuale (deve essere autosave con indicatore discreto)
- Terminologia tecnica nell'interfaccia commerciale ("BOM", "recipe", "snapshot" → nascosti)
- Configurazioni prima di poter iniziare a lavorare (onboarding = 3 domande, non 20)

---

## 2 · Utenti & ruoli

### 2.1 Personas primarie

**A · Marco — Commerciale (persona primaria, 80% dell'uso)**
- 45 anni, ex-installatore diventato venditore
- Non è nato con lo smartphone in mano ma lo usa quotidianamente
- Passa 60% del tempo in trasferta, 40% in ufficio
- Odia i software complicati, ama i tool che gli fanno vincere velocità
- Metrica di successo: quanti preventivi manda al giorno, quanti si chiudono
- KPI dolorosi: tempo tra sopralluogo e invio preventivo, tasso di ripensamenti "aspetta ho sbagliato il prezzo"

**B · Laura — Ufficio (amministrazione, back office)**
- 38 anni, si occupa di listini, contratti, contabilità, coordinamento posa
- Usa il desktop, doppio monitor
- Ha bisogno di viste dense, tabelle filtrabili, export Excel
- Deve poter correggere errori del commerciale senza rifare tutto
- KPI: tempo dall'accettazione preventivo alla consegna materiale

**C · Roberto — Titolare / responsabile commerciale**
- 55 anni, vede tutto e decide tutto
- Non ha tempo per esplorare il software
- Vuole 4 numeri in dashboard e la possibilità di andare in profondità con un click
- KPI: fatturato mese, margine medio, tempo medio ciclo vendita

**D · Anna — Tecnico produzione**
- 32 anni, decide se un preventivo è tecnicamente fattibile
- Riceve le commesse, gestisce la lista di taglio, coordina il montaggio
- Vive nella schermata "Produzione" — non entra quasi mai nel CRM

**E · Emergent SaaS Owner (proprietario piattaforma)**
- Vede tutti i tenant, gestisce pricing SaaS, onboarding nuovi clienti
- Persona secondaria, usa un'area dedicata

**F · Cliente finale (Sig. Rossi)**
- Non installa nulla, non fa login
- Riceve un link, apre il preventivo/contratto, firma dal telefono
- Non deve aver bisogno di aiuto per completare il flusso

### 2.2 Matrice ruolo → permessi essenziali

| Ruolo | Vede prezzi vendita | Vede costi | Modifica prezzo manualmente | Firma contratti | Gestisce listini | Gestisce utenti |
|---|---|---|---|---|---|---|
| Commerciale | ✅ | ❌ | ❌ (solo con `override_price`) | ❌ | ❌ | ❌ |
| Commerciale senior | ✅ | ❌ | ✅ con audit | ❌ | ❌ | ❌ |
| Back office | ✅ | ✅ margine | ✅ con audit | ❌ | ❌ | ❌ |
| Titolare | ✅ | ✅ tutto | ✅ | ✅ | ✅ | ✅ |
| Tecnico produzione | ❌ | ✅ costi materiali | ❌ | ❌ | ❌ (solo lettura tecnica) | ❌ |
| Platform Owner | Cross-tenant | Cross-tenant | ❌ | ❌ | ✅ template | ✅ tenant admin |

### 2.3 Superficie ridotta per ruolo

Il segreto per un'app veloce è **mostrare solo quello che serve al ruolo**. In v1 tutti vedono tutto e questo è ingestibile.

**Commerciale vede nel menu (7 voci):**
1. Dashboard (KPI personali)
2. Lead
3. Clienti
4. Preventivi
5. Contratti
6. Calendario
7. Notifiche

**Back office aggiunge (4 voci):**
8. Produzione (commesse)
9. Fatturazione
10. Pagamenti
11. Assistenza

**Titolare vede TUTTO** (accede a sezione "Configurazione" contenente il resto).

**Sezione Configurazione** (accessibile via icona ingranaggio in header, non nel menu principale):
- Anagrafica azienda
- Utenti & ruoli
- Catalogo prodotti (admin)
- Listini
- Formule di calcolo
- Ferramenta
- Montaggio & posa
- Costi accessori
- Template email
- Firma elettronica
- Integrazioni
- Audit log
- Legacy (preventivi vecchio motore — read-only)

---

## 3 · Casi d'uso principali

### 3.1 Storie utente (in ordine di importanza)

**S1 · "Voglio inviare un preventivo al Sig. Rossi in 5 minuti dallo smartphone"**  
Il commerciale è nel salotto del cliente. Ha rilevato le misure con il metro laser. Apre l'app dal telefono, sceglie il cliente, aggiunge un vano, mette larghezza/altezza/colore/vetro. Il prezzo si calcola. Duplica il vano per la stanza gemella. Invia il PDF via email dal cliente stesso, con il cliente che guarda lo schermo. Chiude la vendita a caldo.

**S2 · "Voglio trasformare un preventivo accettato in contratto firmato via link"**  
Il cliente ha risposto "OK procediamo". Il commerciale apre il preventivo dal telefono, tocca "Genera contratto". Sceglie condizioni pagamento standard (già preimpostate). Invia link firma via email/WhatsApp. Il cliente riceve, apre il link sul suo telefono, legge, firma con il dito, conferma. Il commerciale riceve notifica push "Contratto firmato" entro 3 minuti.

**S3 · "Sto guardando un lead — voglio sapere tutto sul cliente e cosa fare ora"**  
Il commerciale apre un lead. Vede subito: chi è, cosa ha chiesto, ultima interazione, prossima azione consigliata. Un pulsante primario "Programma sopralluogo" o "Crea preventivo" già suggerito dal sistema in base allo stato del lead.

**S4 · "Ho ricevuto un errore sul prezzo — voglio capire perché"**  
Il commerciale ha configurato un vano che risulta con status "incomplete". Non gli si dice solo "errore". Gli si dice: **"Manca il prezzo del vetro 33.1/16/33.1 per il colore Bianco RAL 9016. Chiedi a Laura di aggiornare il listino."** Con un pulsante "Notifica Laura" che manda ticket interno.

**S5 · "Voglio rivedere quanto guadagnamo su un preventivo"**  
Il titolare apre un preventivo. Il commerciale non vede il margine. Il titolare invece vede in un pannello dedicato: costo materiali, costo manodopera, costo posa, margine assoluto, margine %. Con visualizzazione a torta.

**S6 · "Voglio duplicare un preventivo di 3 mesi fa per fare un cliente simile"**  
Duplicazione con un click. Cliente vuoto, misure preservate, prezzi RICALCOLATI dal listino attuale (mai congelati). Se qualcosa non è più disponibile, avviso.

**S7 · "Come amministratore voglio aggiornare il listino telaio 5103 da 8€/ml a 8,50€/ml"**  
Vado in Configurazione → Listini → Cerco "5103" → modifica → salvo. Il sistema crea nuova versione, chiede: "Applicare al prossimo preventivo o retroattivamente?". Retroattività **mai automatica** su preventivi già inviati/firmati.

**S8 · "Cliente vuole cambiare colore su preventivo già inviato"**  
Il commerciale duplica il preventivo (nuova revisione), cambia il colore. Nuovo prezzo. Manda al cliente sotto forma di "Revisione 2 del preventivo Q-2026-000123".

**S9 · "Voglio vedere lo stato di tutte le commesse in produzione"**  
Vista Kanban: Da programmare / In produzione / Pronte / In consegna / Installate.

**S10 · "Sto cercando un cliente ma non ricordo il nome esatto"**  
`Cmd+K` → digito "rossi" → vedo lista cliente/lead/preventivo/contratto → click e ci sono.

### 3.2 Anti-storie (cosa NON dovrà mai succedere)
- Il commerciale che digita a mano un prezzo perché "così è più veloce"
- Il commerciale che invia un preventivo con "prezzo 0€" perché il vetro non era in listino
- Il cliente che riceve una firma richiesta e non capisce come firmare
- Il titolare che ha 4 preventivi con stesso numero perché il commerciale ha duplicato male
- L'amministratore che modifica un listino e cambia i prezzi su contratti già firmati

---

## 4 · Customer Journey

### 4.1 Journey del Commerciale (Marco)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  T0 · Lead                                                              │
│  Fonte: sito web / passaparola / campagna / spontaneo                   │
│  Marco vede notifica push "Nuovo lead: Sig. Rossi, cambio 5 finestre"   │
│  → Apre lead: vede richiesta, contatto, mappa località                  │
│  → Un click: "Programma sopralluogo"                                    │
│  → Suggerimento automatico: martedì mattina (agenda libera)             │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  T1 · Sopralluogo                                                       │
│  Marco arriva a casa Rossi                                              │
│  Apre l'app dal telefono                                                │
│  → Il lead si è già trasformato in Cliente (con un click al T0)         │
│  → Vede scheda cliente + suggerimento "Crea preventivo"                 │
│  → Tap "Nuovo preventivo"                                               │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  T2 · Configurazione preventivo (wizard 7 step)                         │
│  STEP 1 · Cliente        (già preselezionato, salta)                   │
│  STEP 2 · Vani           (aggiunge 5 vani rapidamente)                 │
│  STEP 3 · Configurazione (per ogni vano: prodotto, L, H, ante, colore, │
│                           vetro, ferramenta, accessori, montaggio)     │
│  STEP 4 · Prezzo auto    (vede subito totale finestra + totale generale)│
│  STEP 5 · Riepilogo      (schema visivo + lista + duplica/modifica)    │
│  STEP 6 · Totale         (imponibile, IVA, sconto, montaggio, servizi) │
│  STEP 7 · PDF + Invia    (anteprima → invia via email o WhatsApp)      │
│  Tempo target: 8-12 minuti                                              │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  T3 · Follow-up                                                         │
│  Il preventivo va in stato "Inviato"                                   │
│  Sistema crea task automatico: "Ricorda: chiama Sig. Rossi tra 3 giorni"│
│  Marco vede notifica il giorno T+3                                     │
│  Chiama → cliente conferma → tap "Preventivo accettato"                │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  T4 · Contratto                                                         │
│  Bottone primario: "Genera contratto"                                   │
│  Precompila tutto dal preventivo (nessun re-input dati)                │
│  Condizioni pagamento: template scelti dal menu                        │
│  Anteprima PDF integrale                                                │
│  Tap "Invia link firma" → link va al cliente via email + WhatsApp     │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  T5 · Firma cliente                                                     │
│  Cliente riceve link                                                    │
│  Apre da smartphone                                                     │
│  Legge contratto (rendering PDF inline, no download obbligatorio)     │
│  Checkbox: "Ho letto e accetto termini e condizioni"                  │
│  Firma disegnata a dito su canvas mobile-first                        │
│  Conferma → riceve email con PDF firmato + copia in CC alla società   │
│  Marco riceve notifica push in tempo reale                            │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  T6 · Handoff a Produzione                                              │
│  Marco vede: "✓ Contratto firmato"                                     │
│  Il contratto diventa automaticamente una "Commessa di produzione"     │
│  Anna (produzione) riceve notifica                                     │
│  Marco esce dal flusso — la sua vendita è chiusa                       │
│  Sistema calcola provvigione automatica                                │
└─────────────────────────────────────────────────────────────────────────┘
```

**Metriche journey Commerciale**:
- Tempo Lead → Sopralluogo: ≤ 3 giorni (obiettivo)
- Tempo Sopralluogo → Preventivo inviato: ≤ 30 minuti
- Tempo Contratto → Firma cliente: ≤ 48 ore
- % preventivi inviati che vanno in firma: ≥ 45%

### 4.2 Journey dell'Amministrazione (Laura)

```
Preventivi in coda "In attesa validazione" (opzionale)
  ↓
Contratti firmati oggi
  ↓ tap
Verifica dati fatturazione cliente (P.IVA, indirizzo, PEC)
  ↓
Segna "Pronto per ordine materiale"
  ↓
Sistema genera Ordine di Fornitura dai listini
  ↓
Invia ai fornitori (email precompilata)
  ↓
Traccia stato consegna materiali
  ↓
Quando tutto arrivato: cambia stato commessa in "Pronto per produzione"
  ↓
Anna prende in carico (T6 del journey commerciale)
```

Laura NON entra mai in un preventivo per modificarlo. Se serve modifica, il commerciale crea una revisione.

### 4.3 Journey del Cliente (Sig. Rossi)

**Punto di contatto 1**: riceve email  
Oggetto: "Preventivo Q-2026-000123 — Panorama Pilot"  
Corpo: HTML con logo azienda, saluto personalizzato, "Clicca qui per vedere il tuo preventivo"

**Punto di contatto 2**: apre link  
Landing pagina pubblica `/p/{token}` — no login richiesto  
Sopra: nome azienda + logo + "Preventivo per Sig. Rossi"  
Anteprima PDF inline (WeasyPrint rendering)  
CTA: "Ho domande" (apre WhatsApp/email al commerciale) + "Accetta preventivo" (opzionale, o via risposta email)

**Punto di contatto 3**: riceve email "Contratto pronto per firma"  
Corpo: "Sig. Rossi, il suo contratto è pronto. Firmi qui in 30 secondi."  
Un unico pulsante: "Firma contratto"

**Punto di contatto 4**: pagina firma `/sign/{token}`  
Layout mobile-first:
- Header: "Contratto #CON-2026-000045 · Panorama Pilot"
- Scroll: contratto completo leggibile
- Sticky bottom: box firma
- Checkbox: "Ho letto e accetto termini, condizioni e informativa privacy"
- Canvas grande: "Firma qui con il dito o pennino"
- Pulsanti: "Cancella firma" · "Conferma firma"
- Nome + data auto-compilati (modificabili)

**Punto di contatto 5**: post-firma  
Pagina di conferma "Grazie! Il PDF firmato è stato inviato al tuo indirizzo email"  
Il PDF arriva entro 60 secondi con firma incorporata, timestamp, hash

**Punto di contatto 6**: eventuali comunicazioni successive  
Email di aggiornamento stato produzione ("La sua commessa è in produzione, consegna prevista 15/03/2026")

---

## 5 · Mappa schermate

### 5.1 Schermate PUBBLICHE (no login)
| Route | Nome | Ruolo | Priorità |
|---|---|---|---|
| `/` | Landing marketing (vetrina B2B panoramapilot.com) | pubblico | P1 |
| `/login` | Login | tutti | P0 |
| `/forgot-password` | Recupero password | tutti | P0 |
| `/accept-invitation` | Accettazione invito | nuovi utenti | P0 |
| `/p/:token` | Preventivo pubblico (view+accept) | cliente finale | P0 |
| `/sign/:token` | **Pagina firma NUOVA (mobile-first)** | cliente finale | P0 |
| `/onboarding` | Onboarding tenant (3 step) | admin nuovo | P1 |

### 5.2 Schermate COMMERCIALE (menu principale)
| Route | Nome | Note |
|---|---|---|
| `/dashboard` | Home commerciale con KPI personali + task del giorno | P0 |
| `/leads` | Lead list + kanban | P0 |
| `/leads/:id` | Lead detail | P0 |
| `/customers` | Clienti list | P0 |
| `/customers/:id` | Cliente detail (con storico preventivi, contratti, note) | P0 |
| `/quotes` | Preventivi list (con filtri) | P0 |
| `/quotes/new` | **Nuovo wizard preventivo** (path unico) | P0 |
| `/quotes/:id` | **Preventivo editor** (stesso wizard in modalità edit) | P0 |
| `/contracts` | Contratti list | P0 |
| `/contracts/:id` | Contract detail + invia firma | P0 |
| `/calendar` | Calendario appuntamenti | P1 |
| `/notifications` | Centro notifiche | P1 |

### 5.3 Schermate BACK OFFICE
| Route | Nome | Note |
|---|---|---|
| `/production` | Kanban commesse in produzione | P1 |
| `/production/:id` | Commessa detail | P1 |
| `/billing` | Fatturazione (fatture da emettere/emesse) | P1 |
| `/payments` | Piani pagamento clienti + solleciti | P1 |
| `/service` | Ticket assistenza post-vendita | P2 |

### 5.4 Sezione CONFIGURAZIONE (icona ingranaggio in header)
Accesso: solo con permessi admin
| Route | Nome | Note |
|---|---|---|
| `/settings/company` | Anagrafica azienda | P0 |
| `/settings/users` | Utenti & ruoli | P0 |
| `/settings/catalog` | Catalogo prodotti | P0 |
| `/settings/pricelists` | Listini componenti | P0 |
| `/settings/glass` | Listino vetri | P0 |
| `/settings/hardware` | Kit ferramenta | P1 |
| `/settings/installation` | Regole montaggio & posa | P1 |
| `/settings/accessories` | Costi accessori (16 categorie) | P1 |
| `/settings/formulas` | Formule di calcolo | P1 |
| `/settings/import` | Import listini (CSV/XLS/XLSX) | P0 |
| `/settings/email` | SMTP + template email | P0 |
| `/settings/clauses` | Clausole contrattuali | P1 |
| `/settings/templates` | Template PDF preventivo/contratto | P1 |
| `/settings/legal-entities` | Ragioni sociali multiple | P2 |
| `/settings/integrations` | Integrazioni esterne | P2 |
| `/settings/audit` | Log di audit | P1 |
| `/settings/legacy` | Preventivi legacy (read-only) | P1 |

### 5.5 Schermate PLATFORM OWNER (Emergent)
| Route | Nome | Note |
|---|---|---|
| `/platform/tenants` | Tenants list | P2 |
| `/platform/pricing` | Piani SaaS | P2 |
| `/platform/health` | Stato piattaforma | P2 |

**Totale route utente commerciale visibili: 7** (era 25+ in v1)  
**Totale route utente back office visibili: 11**  
**Totale route admin (via Configurazione): 17**

---

## 6 · Schema navigazione

### 6.1 Chrome desktop (≥1024px)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  🏠 [Panorama Pilot logo]    [Cmd+K Cerca...]   🔔  ⚙️  👤 Marco Rossi   │
├──────────────────────────────────────────────────────────────────────────┤
│ ┌─────────────┐  ┌──────────────────────────────────────────────────────┐│
│ │ ▸ Dashboard │  │                                                      ││
│ │ ▸ Lead      │  │                                                      ││
│ │ ▸ Clienti   │  │              MAIN CONTENT AREA                       ││
│ │ ▸ Preventivi│  │                                                      ││
│ │ ▸ Contratti │  │                                                      ││
│ │ ▸ Calendario│  │                                                      ││
│ │ ▸ Notifiche │  │                                                      ││
│ │             │  │                                                      ││
│ │ [+ Nuovo ▾] │  │                                                      ││
│ │             │  │                                                      ││
│ └─────────────┘  └──────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────────┘
```

- Sidebar sinistra: 220px, fissa, icone Phosphor + label
- Pulsante "**+ Nuovo**" in fondo alla sidebar → dropdown con: Nuovo lead, Nuovo cliente, Nuovo preventivo, Nuovo contratto
- Header: 56px, con Cmd+K prominente al centro (pattern Linear/Stripe)
- Icona ⚙️ in header apre `/settings/...` come pannello slide-in (non full navigation)

### 6.2 Chrome mobile (<768px)

```
┌──────────────────────────────┐
│ ☰   Panorama Pilot      🔔   │
├──────────────────────────────┤
│                              │
│                              │
│      MAIN CONTENT            │
│                              │
│                              │
├──────────────────────────────┤
│  🏠  💼  📄  📁  ⋯          │  ← Bottom nav (Dash/Lead/Prev/Contr/Altro)
└──────────────────────────────┘
```

- Hamburger apre drawer laterale con menu completo
- Bottom nav con 5 icone: le 5 azioni più frequenti del commerciale
- FAB (floating action button) "+" in basso a destra su schermate Preventivi/Contratti

### 6.3 Command Palette (Cmd+K / Ctrl+K)

Ispirazione: Linear, Stripe, Figma, Notion

```
┌─────────────────────────────────────────────────────┐
│  🔍  Cerca clienti, preventivi, comandi...          │
├─────────────────────────────────────────────────────┤
│  AZIONI                                             │
│    + Nuovo preventivo                     ⌘N        │
│    + Nuovo cliente                        ⌘⇧N       │
│    ↻ Ricalcola preventivo corrente        ⌘R        │
│    ✉ Invia preventivo                     ⌘⏎        │
│                                                     │
│  CLIENTI RECENTI                                    │
│    ○ Sig. Rossi Mario — Via Roma 12                 │
│    ○ Beta Costruzioni SRL                           │
│                                                     │
│  PREVENTIVI RECENTI                                 │
│    Q-2026-000123 — Rossi Mario — €12.400            │
│                                                     │
│  IMPOSTAZIONI                                       │
│    ⚙ Listini                                        │
│    ⚙ Utenti                                         │
└─────────────────────────────────────────────────────┘
```

Diventa il modo primario di navigare per utenti esperti.

---

## 7 · Wireframe testuali delle schermate chiave

### 7.1 Dashboard commerciale

```
┌────────────────────────────────────────────────────────────────────────┐
│  Buongiorno Marco 👋                                                   │
│  Oggi è mercoledì 15 febbraio 2026                                     │
├────────────────────────────────────────────────────────────────────────┤
│  KPI ROW (4 card grandi orizzontali)                                   │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐              │
│  │ Preventivi│ │ In firma  │ │ Fatturato │ │  Task     │              │
│  │  del mese │ │           │ │  del mese │ │  di oggi  │              │
│  │           │ │           │ │           │ │           │              │
│  │    12     │ │     3     │ │  €48.200  │ │     4     │              │
│  │   ↑ 20%   │ │           │ │   ↑ 12%   │ │           │              │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘              │
├────────────────────────────────────────────────────────────────────────┤
│  TASK DEL GIORNO                                                       │
│  ○ 09:30 · Sopralluogo Sig. Rossi (Via Roma 12)         [Vai]         │
│  ○ 11:00 · Follow-up Beta Costruzioni                    [Vai]         │
│  ○ 15:00 · Firma contratto Sig. Verdi                    [Vai]         │
│  ○ 17:00 · Chiamata post-vendita Sig. Bianchi            [Vai]         │
├────────────────────────────────────────────────────────────────────────┤
│  PIPELINE PREVENTIVI (mini kanban orizzontale)                         │
│  Bozza (2)  →  Inviato (5)  →  Accettato (3)  →  In firma (1)         │
├────────────────────────────────────────────────────────────────────────┤
│  NOTIFICHE RECENTI                                                     │
│  • 2h fa — Sig. Rossi ha aperto il preventivo Q-000123                 │
│  • 5h fa — Contratto CON-000045 firmato da Sig. Verdi                  │
│  • Ieri — Nuovo lead da sito: Alfa SRL                                 │
└────────────────────────────────────────────────────────────────────────┘
```

**Principi applicati**: numeri grandi (Stripe), task actionable con CTA laterale (Linear), pipeline visiva compatta (Pipedrive).

### 7.2 Lista Preventivi

```
┌────────────────────────────────────────────────────────────────────────┐
│  Preventivi                                              [+ Nuovo]     │
├────────────────────────────────────────────────────────────────────────┤
│  [Tutti] [Bozza] [Inviato] [Accettato] [In firma] [Rifiutato]         │
│  🔍 Cerca cliente, numero...                        Filtri ▾  Export ▾ │
├────────────────────────────────────────────────────────────────────────┤
│  N°           Cliente          Data      Stato       Totale     Az.   │
│  Q-000125     Rossi M.         14 feb    ● Inviato   €12.400    ⋯     │
│  Q-000124     Beta SRL         13 feb    ● Bozza     €8.900     ⋯     │
│  Q-000123     Verdi G.         12 feb    ● Accettato €22.100    ⋯     │
│  ...                                                                   │
└────────────────────────────────────────────────────────────────────────┘
```

Riga cliccabile = apre editor. Menu `⋯`: Duplica, Invia via email, Genera contratto (se accettato), Elimina bozza.

### 7.3 Wizard Nuovo Preventivo — Layout comune (ispirato DocuSign)

```
┌────────────────────────────────────────────────────────────────────────┐
│  ← Preventivi          Q-000126 · Bozza · Auto-saved 3s fa           │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│    ①  ②  ③  ④  ⑤  ⑥  ⑦   ← step indicator con checkmark          │
│    Cli Van Cfg Prz Rip Tot Inv                                        │
│                                                                        │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│                  [CONTENUTO STEP CORRENTE]                             │
│                                                                        │
├────────────────────────────────────────────────────────────────────────┤
│  ← Indietro                            [Salva bozza]      Avanti →    │
└────────────────────────────────────────────────────────────────────────┘
```

Autosave silenzioso ogni 3s. Nessun pulsante "Salva" per lo step corrente.

### 7.3.1 STEP 1 · Cliente

```
Chi è il cliente per questo preventivo?

  🔍 Cerca cliente esistente...
  
  oppure crea nuovo cliente:
  
  ○ Persona fisica    ○ Azienda
  
  [Nome / Ragione sociale]
  [Email]      [Telefono]
  [Indirizzo]  [Cap] [Città] [Provincia]
  [P.IVA]      [Codice fiscale]
  
  [+ Aggiungi indirizzo di posa (se diverso)]
```

### 7.3.2 STEP 2 · Vani

```
Aggiungi i vani da preventivare.

  ┌─────────────────────────────────────────────────┐
  │  Cucina · Finestra                              │
  │  1 anta · 900×1500 · Bianco                     │
  │  ⚙ Configura    ✎ Modifica    📄 Duplica    🗑  │
  └─────────────────────────────────────────────────┘
  
  ┌─────────────────────────────────────────────────┐
  │  Camera matrimoniale · Portafinestra            │
  │  Configurazione incompleta                      │
  │  ⚙ Completa configurazione                      │
  └─────────────────────────────────────────────────┘
  
  [+ Aggiungi vano]
  
  Suggerimenti: [+ Cucina] [+ Bagno] [+ Camera] [+ Salotto]
```

### 7.3.3 STEP 3 · Configurazione vano (pannello dedicato per singolo vano)

```
┌────────────────────────────────────────────────────────────────────────┐
│  Cucina · Vano 1                                                       │
├────────────────────────────────────────────────────────────────────────┤
│  [3.1] Prodotto                                                        │
│    ○ ProEvolution        ○ ProEvolution Restauro                       │
│                                                                        │
│  [3.2] Tipologia                                                       │
│    ○ Finestra   ○ Portafinestra   ○ Fisso   ○ Scorrevole              │
│                                                                        │
│  [3.3] Ante e apertura                                                 │
│    Numero ante:  ⚪ 1  ⚪ 2  ⚪ 3  ⚪ 4                                  │
│    Apertura: [Anta ribalta ▾]                                          │
│                                                                        │
│  [3.4] Dimensioni                                                      │
│    Larghezza [900] mm      Altezza [1500] mm                          │
│                                                                        │
│  [3.5] Colore                                                          │
│    Interno: [Bianco RAL 9016 ▾]                                        │
│    Esterno: [Bianco RAL 9016 ▾]                                        │
│    ☐ Premium (+6%)                                                     │
│                                                                        │
│  [3.6] Vetro                                                           │
│    [Doppio 33.1/16/33.1 (76 €/mq) ▾]                                  │
│                                                                        │
│  [3.7] Ferramenta                                                      │
│    [Kit standard 1 anta ▾]                                             │
│                                                                        │
│  [3.8] Accessori (opzionali)                                           │
│    ☐ Zanzariera  ☐ Cassonetto  ☐ Controtelaio  ☐ Coprifili           │
│                                                                        │
│  [3.9] Montaggio                                                       │
│    ☐ Sì, includere montaggio                                           │
│    ☐ Include smontaggio infisso esistente                              │
│                                                                        │
├────────────────────────────────────────────────────────────────────────┤
│  💰 Prezzo vano calcolato                                              │
│                                                                        │
│                            €  1.240,00                                 │
│                                                                        │
│  [ⓘ Vedi dettaglio calcolo]  ← visibile solo con permesso              │
├────────────────────────────────────────────────────────────────────────┤
│  ← Indietro (vani)                       [Salva vano e continua]      │
└────────────────────────────────────────────────────────────────────────┘
```

Il prezzo si aggiorna live (debounce 400ms) ogni volta che cambi un input. Se qualcosa manca:

```
⚠️ Prezzo incompleto
Manca il prezzo del componente [Fermavetro FV-STD, colore Bianco].
Chiedi all'amministratore di aggiornare il listino.
[Notifica amministratore]
```

Il pulsante "Salva vano e continua" è **disabilitato** finché il prezzo non è completo (evita preventivi con vani a €0).

### 7.3.4 STEP 4 · Prezzo automatico (recap per titolare/back office)

```
Prezzo automatico calcolato dal motore commerciale

  Vano 1 · Cucina                                          €  1.240,00
  Vano 2 · Camera                                          €  1.480,00
  Vano 3 · Bagno                                           €    890,00
  ─────────────────────────────────────────────────────────────────────
  Subtotale vani                                          €  3.610,00
  Montaggio                                                €    450,00
  Trasporto                                                €    120,00
  ─────────────────────────────────────────────────────────────────────
  Imponibile                                              €  4.180,00
  IVA 22%                                                  €    919,60
  ═════════════════════════════════════════════════════════════════════
  TOTALE                                                  €  5.099,60
```

Nel STEP 4 il commerciale può applicare uno **sconto commerciale globale** (max % da permesso), il quale ridurrà l'imponibile ma NON i costi.

### 7.3.5 STEP 5 · Riepilogo vani (visivo)

Ogni vano con schema SVG stilizzato + specs + prezzo. Duplica/modifica/elimina.

### 7.3.6 STEP 6 · Totale e condizioni

Condizioni di pagamento (dropdown template), tempi di consegna, note libere.

### 7.3.7 STEP 7 · Invio

```
Il tuo preventivo è pronto!

  [📄 Anteprima PDF]  [📥 Scarica PDF]

  Invia a:
  ○ Email: cliente@example.com    ✎
  ○ WhatsApp: +39 333 1234567     ✎

  [✉ Invia preventivo]

  Al momento dell'invio:
  • il preventivo diventerà "Inviato"
  • verrà creato un task di follow-up per il 18 febbraio
  • il cliente riceverà un link web + PDF allegato
```

### 7.4 Editor Contratto (mobile-first)

```
┌─────────────────────────────────────┐
│  ← Contratto CON-000045             │
│  Stato: Bozza                       │
├─────────────────────────────────────┤
│  Cliente                            │
│  Sig. Rossi Mario                   │
│  Via Roma 12, Milano                │
├─────────────────────────────────────┤
│  Riferimento preventivo             │
│  Q-2026-000123 · €5.099,60          │
│  [Vedi preventivo]                  │
├─────────────────────────────────────┤
│  Condizioni pagamento               │
│  [Standard 30/60/10 ▾]              │
│                                     │
│  Tempi di consegna                  │
│  [45 giorni lavorativi]             │
│                                     │
│  Clausole                           │
│  ☑ Garanzia 10 anni                 │
│  ☑ Assicurazione trasporto          │
│  ☐ Servizio manutenzione            │
├─────────────────────────────────────┤
│  [Anteprima contratto]              │
│  [Invia link firma al cliente]      │
└─────────────────────────────────────┘
```

### 7.5 Pagina firma (`/sign/{token}`) — mobile-first

```
┌─────────────────────────────────────┐
│  Panorama Pilot                     │
│  Contratto CON-000045               │
├─────────────────────────────────────┤
│  [ === PDF contract inline === ]    │
│  [                                ] │
│  [   scroll per leggere            ]│
│  [                                ] │
│  [ (embedded PDF viewer)          ] │
│  [                                ] │
├─────────────────────────────────────┤
│  ☐ Ho letto e accetto termini e     │
│    condizioni e informativa privacy │
├─────────────────────────────────────┤
│  Firmi qui ↓                        │
│  ┌─────────────────────────────┐    │
│  │                             │    │
│  │    (canvas grande touch)    │    │
│  │                             │    │
│  └─────────────────────────────┘    │
│                                     │
│  [Cancella]                         │
│                                     │
│  Nome firmatario:                   │
│  [Rossi Mario____________]          │
│                                     │
│  [🔒 CONFERMA FIRMA]                │
└─────────────────────────────────────┘
```

Il pulsante "Conferma firma" è disabilitato finché:
- Checkbox consenso spuntato
- Canvas non vuoto (verifica pixel non-white > soglia)
- Nome inserito

Post-conferma: schermo pieno con "✓ Firma completata" + info hash + "PDF firmato in arrivo via email".

---

## 8 · Flussi operativi (state machines)

### 8.1 Ciclo preventivo

```
[bozza] → send → [inviato] → accept → [accettato] → generate_contract → (contract)
                    ↓ reject                ↓ reject
                [rifiutato]              [rifiutato]
                    ↓ replace                ↓
                [nuova revisione]      [nuova revisione]

[inviato] → expire → [scaduto]
[bozza] → delete → 🗑
```

### 8.2 Ciclo contratto

```
[bozza] → ready_for_signature → [pronto per firma]
              → send_to_customer → [sent]
                   → customer_views → [viewed]
                        → customer_signs → [firmato] (state terminale)
                        → customer_rejects → [rifiutato] → new revision
                        → expires (default 7 giorni) → [scaduto]
```

Firma = state terminale. Modifiche successive → nuova revisione (nuovo id, riferimento a padre).

### 8.3 Ciclo commessa produzione

```
[firmato] → auto → [pronto per ordini] → order_materials → [materiali_ordinati]
   → materials_arrived → [pronto produzione] → produce → [in_produzione]
   → produced → [pronto_consegna] → install → [installato] (terminale)
```

### 8.4 Flusso assistenza

```
Ticket aperto → [triage] → assign → [assegnato] → resolve → [risolto]
                    ↓ reject → [chiuso senza intervento]
```

---

## 9 · Principi UX (le 10 leggi Panorama Pilot)

**Legge 1 · Un solo pulsante primario per schermata**  
Al massimo una CTA primaria (colorata, prominente). Le altre azioni sono secondarie (outline) o menu.

**Legge 2 · Il numero grande è la verità**  
Su ogni schermata di preventivo/contratto/fattura, il totale è il testo più grande. Tipografia H1 42-56px.

**Legge 3 · Zero click sprecati**  
Se un dato è deducibile dal contesto (data odierna, cliente selezionato, listino attivo), è precompilato. Il tab funziona sempre nell'ordine naturale.

**Legge 4 · Errori parlano umano**  
Mai "Error 500" al commerciale. Sempre: "Il vetro X non è disponibile per il colore Y. Chiedi a Laura di aggiornare il listino."

**Legge 5 · Autosave silenzioso**  
Ogni azione viene salvata. Nessun "Salva". Piccolo indicatore "Salvato 3s fa" in alto.

**Legge 6 · Mobile-first per il commerciale**  
Ogni pattern è progettato prima per mobile. Il desktop è una versione arricchita.

**Legge 7 · Il contesto è cliente-centrico**  
Ogni schermata operativa mostra il cliente in alto/laterale, non richiede navigazione per "sapere chi è".

**Legge 8 · Nessun jargon tecnico visibile al commerciale**  
Mai "BOM", "recipe", "snapshot", "aggregate", "provisioning". Sempre: "distinta materiali", "listino applicato", "versione bloccata", "totale calcolato".

**Legge 9 · Empty state è educativo**  
Ogni tabella vuota mostra: illustrazione + una frase chiara + CTA per iniziare. Mai un vuoto muto.

**Legge 10 · Undo prima di conferma**  
Ogni azione critica (invio preventivo, cancellazione, cambio stato) è annullabile per 10 secondi tramite toast "Azione eseguita — Annulla". Confirm dialog solo quando davvero irreversibile.

---

## 10 · Regole di progettazione

### 10.1 Tipografia
- Display: **font sans-serif italiana carattere neutro** (default: Instrument Sans + Instrument Serif per accenti editoriali)
- Body: 15px desktop, 14px mobile
- Monospace (numeri): **IBM Plex Mono** — per prezzi, codici, id
- H1: 42-56px  |  H2: 24-32px  |  H3: 18-20px

### 10.2 Colori
- **Primary** (azioni positive): nero profondo `#0A0A0B` (contrasto massimo, no palette blu banale)
- **Accent** (evidenziazione): rosso mattone `#B33A2A` (matcha con contesto italiano professionale)
- **Success**: verde salvia `#4A7C59` (non il verde acido)
- **Warning**: ocra `#B87333`
- **Danger**: rosso profondo `#8B1E1E`
- **Neutrals**: greyscale con tinting caldo (non pure grey)
- **Background**: bianco crema `#FAFAF8` (non pure white — riduce eye strain)

Regola: mai gradienti. Mai emoji nell'interfaccia (solo icone Phosphor).

### 10.3 Spacing e layout
- Grid 4px base
- Card padding: 24px desktop, 16px mobile
- Container max-width: 1280px
- Line-height body: 1.55

### 10.4 Motion
- Transizioni: 150-200ms cubic-bezier(0.4, 0, 0.2, 1)
- Page transitions: fade + subtle slide 8px
- Skeleton loaders (non spinner)
- Toast: slide da bottom su mobile, top-right su desktop
- Autosave indicator: fade pulse

### 10.5 Immagini e iconografia
- Icone: **Phosphor Icons** (già installate)
- Illustrations empty state: **line art minimale** (no illustrazioni cartoon)
- Foto stock: mai. Solo immagini di prodotti realmente configurabili nel catalogo.

### 10.6 Accessibility
- Contrast ratio WCAG AA minimo su tutti i testi
- Focus visible su tutti gli elementi interattivi
- Aria-label su icone senza testo
- Tab order logico
- Screen reader friendly su form

### 10.7 Data density
- Tabelle: max 8 colonne visibili. Il resto in dropdown "⋯".
- Row height: 48px desktop, 56px mobile (touch-friendly).
- Sticky header. Sticky first column su mobile con horizontal scroll.

---

## 11 · Componenti standard

### 11.1 Design system existing (shadcn/ui)
Rimane la base. Non reinventare.

### 11.2 Componenti custom da introdurre in v2
| Componente | Uso | Ispirazione |
|---|---|---|
| `<CommandPalette />` | Cmd+K globale | Linear/Stripe |
| `<WizardStepper />` | Wizard 7 step preventivo | DocuSign |
| `<PricingCard />` | Card prezzo grande con breakdown collassabile | Stripe |
| `<VanoConfigurator />` | Form guidato config vano | Pipedrive deal editor |
| `<SignaturePad />` | Canvas firma touch/mouse/pen | DocuSign |
| `<KanbanBoard />` | Board preventivi/produzione | Pipedrive/Monday |
| `<ContextPanel />` | Pannello destro cliente context | HubSpot |
| `<InlinePDFViewer />` | Anteprima PDF integrata | Stripe invoice |
| `<AutoSaveIndicator />` | "Salvato 3s fa" nell'header | Notion/Figma |
| `<StatusPill />` | Badge stato colorato | Linear |
| `<QuickAdd />` | + dropdown creazione veloce | Pipedrive |
| `<UndoToast />` | Toast con annulla temporizzato | Gmail |

### 11.3 Convenzioni componenti
- Nome file: `PascalCase.jsx`
- Data-testid su ogni elemento interattivo
- Props tipizzate (JSDoc o TS futuro)
- Zero uso di className inline massiccio — solo Tailwind utilities

---

## 12 · Design system (tokens)

```css
/* Sample tokens — da consolidare in design_guidelines.md */
--ppilot-color-bg:              #FAFAF8;
--ppilot-color-surface:         #FFFFFF;
--ppilot-color-primary:         #0A0A0B;
--ppilot-color-primary-hover:   #1F1F22;
--ppilot-color-accent:          #B33A2A;
--ppilot-color-success:         #4A7C59;
--ppilot-color-warning:         #B87333;
--ppilot-color-danger:          #8B1E1E;
--ppilot-color-border:          #E5E5E0;
--ppilot-color-muted:           #F4F4F0;
--ppilot-color-text:            #18181B;
--ppilot-color-text-muted:      #71717A;

--ppilot-radius-sm:             2px;
--ppilot-radius-md:             6px;
--ppilot-radius-lg:             12px;

--ppilot-font-display:          "Instrument Serif", Georgia, serif;
--ppilot-font-body:             "Instrument Sans", -apple-system, sans-serif;
--ppilot-font-mono:             "IBM Plex Mono", ui-monospace, monospace;

--ppilot-shadow-sm:             0 1px 2px rgba(0,0,0,.05);
--ppilot-shadow-md:             0 4px 12px rgba(0,0,0,.08);
```

Da consolidare in `/app/design_guidelines.md` con esempi di composizione (button variants, form field states, ecc.).

---

## 13 · Roadmap

### Fase 0 · UX Architecture (questo documento)
- Documento completo → **stato attuale**
- Approvazione Product Owner → **in attesa**
- Consolidamento `design_guidelines.md` con token e regole → dopo approvazione

### Fase 1 · Backend
- Nuovo endpoint `POST /api/quotes/:id/openings/:openingId/products/compute-and-add` (motore integrato)
- Endpoint `PATCH /api/quote-structure/products/:lineId` con ricalcolo
- Bloccare `base_price` da input commerciale (403 senza `override_price`)
- Migrare `pricing_snapshot` completo su ogni riga vano
- Endpoint `POST /api/contracts/generate-from-quote/:quoteId` migliorato
- Test regressione backend

### Fase 2 · Frontend Wizard
- Nuovo `/quotes/new` e `/quotes/:id` con `<WizardStepper>` 7 step
- Rimozione `QuoteEditorPage` (route disabilitata, marcata legacy)
- Rimozione `QuoteStructurePage` (route disabilitata)
- `<CommandPalette>` globale
- `<ContextPanel>` cliente
- `<AutoSaveIndicator>`

### Fase 3 · Firma canvas mobile
- Nuova rotta pubblica `/sign/:token`
- `<SignaturePad>` con `react-signature-canvas`
- Validazione consenso + firma non vuota
- Metadata cattura (nome, IP, UA, timestamp, hash)
- Incorporazione firma nel PDF finale
- Test manuale mobile viewport (Playwright user agent iPhone/Android)

### Fase 4 · Contratto da preventivo
- Precompilazione totale da `pricing_snapshot`
- Template clausole configurabili
- Anteprima PDF integrata
- Invio link firma via email/WhatsApp

### Fase 5 · Cleanup e menu per ruolo
- `AppLayout` con menu differenziato per ruolo
- Sezione `/settings/*` accessibile via icona ingranaggio
- Route legacy marcate e disabilitate (non eliminate)
- Aggiornamento permessi

### Fase 6 · Test operativo end-to-end
- Script Playwright: lead → cliente → preventivo → PDF → contratto → firma mobile → PDF firmato
- Test in viewport mobile (390x844)
- Test cross-browser (Chromium, WebKit, Firefox)
- Se tutto verde → merge in main

### Fase 7 (post-approvazione) · Sezioni admin catalog
- UI Kit ferramenta
- UI Montaggio & posa
- UI Costi accessori (16 categorie)
- UI Listino vetri dedicato

### Fase 8 (futuro) · Produzione + fatturazione
- Kanban produzione operativo
- Ordini fornitori
- Fatturazione elettronica

---

## 14 · Metriche di successo

Il successo di v2 non si misura in feature spedite, ma in questi 6 numeri:

| Metrica | Baseline v1 | Target v2 |
|---|---|---|
| Tempo medio da "nuovo preventivo" a "inviato" | ~45 min | ≤ 15 min |
| % preventivi con prezzo digitato a mano | 100% | 0% |
| % preventivi con vano a prezzo 0 (bug) | ~5% | 0% |
| % firme completate su smartphone al primo tentativo | ~30% | ≥ 90% |
| NPS commerciali (survey trimestrale) | n/a | ≥ 40 |
| Click medi per completare "lead → firma" | ~120 | ≤ 40 |

---

## 15 · Rischi noti e ipotesi

### Rischi
1. **Listini incompleti** — molti motori "incomplete" al lancio. Mitigazione: importer intuitivo + banner "prima di iniziare, carica i tuoi listini".
2. **Utenti abituati a v1** — resistenza al cambio. Mitigazione: tutorial in-app, video 90s.
3. **Contratti legacy** — restano vecchia UI in sola lettura, non impattano.
4. **Performance mobile** — su rete 3G il caricamento wizard deve stare ≤ 3s. Mitigazione: code splitting per step.

### Ipotesi da validare
- Il commerciale usa davvero lo smartphone in casa cliente? → user testing 3 commerciali
- La firma disegnata è legalmente sufficiente in Italia? → sì, firma elettronica semplice ex eIDAS, ma per firme "avanzate" servirebbe OTP+SPID (fuori scope v2)
- Il cliente finale sa cliccare un link email e firmare? → user test 5 clienti finali età varia

---

## 16 · Cosa richiede approvazione (checklist Product Owner)

- [ ] Filosofia e principi (sezioni 1)
- [ ] Personas e matrice ruoli (sezioni 2)
- [ ] Mappa schermate (sezione 5)
- [ ] Schema navigazione desktop + mobile (sezione 6)
- [ ] Wireframe testuali wizard (7.3.1 - 7.3.7)
- [ ] Wireframe firma mobile (7.5)
- [ ] State machine cicli (sezione 8)
- [ ] 10 leggi UX (sezione 9)
- [ ] Design system token (sezione 12)
- [ ] Roadmap fasi 0-6 (sezione 13)
- [ ] Target metriche di successo (sezione 14)

Alla firma di approvazione, questo documento diventa la fonte unica di verità per lo sviluppo di v2. Ogni deviazione richiederà nuovo giro di approvazione.

---

**Fine documento — pronto per revisione**
