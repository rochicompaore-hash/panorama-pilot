# Panorama Pilot — UX & Product Architecture v2.1

**Autore**: Design partner  
**Versione**: 2.1 — Recepimento feedback strutturale Product Owner  
**Data revisione**: Feb 2026  
**Stato**: DRAFT v2.1 — In attesa di approvazione esplicita  
**Regola vincolante**: nessun codice, nessun file `design_guidelines.md`, nessuna Fase 1 finché il documento non è approvato.

---

## Changelog v2.0 → v2.1

**Sezioni modificate**:
- §1 · Filosofia — **modificato P6** (rimossa retorica "numero grande = verità"), **aggiunto P7** ("Ogni informazione si inserisce una sola volta"), **aggiunta Regola Architetturale** (fonte autorevole unica)
- §2 · Utenti & ruoli — **estese le personas** da 6 a 11 (aggiunti Tecnico Rilevatore, Responsabile Tecnico, Responsabile Produzione, Operatore Produzione, Posatore/Caposquadra), **matrice permessi completa** riscritta con 11 righe
- §4 · Customer Journey — **journey commerciale ridisegnato** rimuovendo il rilievo dal preventivo, **journey del Rilevatore** aggiunto, **journey del Posatore** aggiunto, **journey del Cliente** esteso
- §5 · Mappa schermate — **aggiunte schermate operative** per Rilievo, Produzione, Posa
- §6 · Navigazione — **menu commerciale aggiornato** (Attività al posto di Notifiche), **menu specifico per ruolo** dettagliato in §13
- §7 · Wireframes — **wizard preventivo riportato a 6 step** (non 7), con Step 3 unificato configurazione+prezzo, rilievo tecnico rimosso dal preventivo
- §7.5 · Firma — **requisiti espansi** (token non prevedibile, scadenza, revoca, single-document, audit trail), **OTP → estensione futura**, **rimossa dicitura "firma elettronica avanzata"**
- §8 · Flussi operativi — **state machine completa** Vendita → Rilievo → Produzione → Posa → Assistenza, **regole cambio stato**, **condizioni bloccanti produzione**
- §9 · Principi UX — **Legge 2 riformulata** in coerenza col nuovo P6
- §10 · Regole progettazione — **font UI cambiato da Instrument Sans a Inter**, Serif solo per titoli/editoriale, mai in form/tabelle
- §12 · Design tokens — **estesi** con testo primario/secondario, bordi, superfici, hover, focus, successo, avviso, errore, info, disabled

**Nuove sezioni**:
- §13 · Menu specifico per ruolo (11 ruoli)
- §14 · Matrice Dato → Fonte autorevole → Moduli lettori
- §15 · Misure indicative vs misure definitive
- §16 · Gestione errori bloccanti nel preventivo
- §17 · Comportamento dei preventivi legacy
- §18 · Criteri di accessibilità

**Sezioni invariate rispetto a v2.0**:
- §0 (Executive summary — solo aggiornati riferimenti step wizard)
- §3 (Casi d'uso — testo invariato, solo terminologia allineata)
- §11 (Componenti standard — inalterato)

**Conferma cambio codice**: **NESSUN file di codice modificato durante la stesura di v2.1**. Solo `/app/memory/UX_PRODUCT_ARCHITECTURE_V2.md` è stato aggiornato. Nessun `design_guidelines.md` creato. Nessuna Fase 1 avviata.

---

## 0 · Executive Summary

Panorama Pilot v1 è stato costruito **per pagine**. 64 route, 3 pagine diverse per lo stesso preventivo, un motore di calcolo perfetto sconnesso dal flusso, una firma canvas inutilizzabile da smartphone.

Panorama Pilot v2 si costruisce **per processo**. Un motore, un editor, un flusso. Il commerciale non si chiede mai "in quale pagina vado?". La piattaforma lo accompagna lungo il percorso naturale della vendita e post-vendita di serramenti:

> **Lead → Cliente → Preventivo → Contratto → Rilievo tecnico → Produzione → Posa → Assistenza**

Il preventivo lavora su **misure indicative** dichiarate dal commerciale in casa cliente. Il rilievo tecnico, effettuato SOLO dopo firma contratto da parte di un rilevatore autorizzato, produce le **misure definitive** che sbloccano la produzione. Nessuna commessa può entrare in lista di taglio senza rilievo approvato.

Ispirazione: linearità di **DocuSign**, pipeline di **Pipedrive**, velocità di **Linear**, chiarezza numerica di **Stripe**, contextuality di **HubSpot**, keyboard-first di **Figma**. Non copiare — applicare i principi al mondo serramenti italiano.

---

## 1 · Filosofia del prodotto

### 1.1 I sette principi fondanti

**P1 · Un solo modo di fare le cose**  
Se ci sono due percorsi per creare un preventivo, uno è sbagliato. Un motore, un editor, un flusso.

**P2 · Il motore calcola, l'utente configura**  
Il commerciale sceglie prodotto, misure, colore, vetro. Il prezzo appare. Non lo digita mai. Se il motore non sa calcolare (dato mancante), lo dice chiaramente — non mette zero.

**P3 · La velocità è una feature**  
Command palette `Cmd+K` ovunque. Scorciatoie da tastiera. Nessun modal per operazioni frequenti. Ricerca fulminea.

**P4 · Mobile-first per il commerciale**  
Il commerciale è nel salotto del cliente. Deve creare, firmare e inviare da telefono senza friction. Se una feature funziona meglio su desktop che su mobile, è progettata male.

**P5 · Il contesto vive con te**  
Quando lavori su un preventivo vedi il cliente. Quando lavori sul cliente vedi lo storico. Nessun click per "chi è". Pannello destro con contesto rilevante (pattern HubSpot).

**P6 · Risultato economico immediatamente leggibile — senza sovrastare errori, dati mancanti o stati critici** *(riformulato)*  
Nelle schermate commerciali, il prezzo/totale è visibile immediatamente. Se però esistono errori bloccanti, dati mancanti, o stati critici (es. `MISSING_GLASS_PRICE`, listino scaduto, cliente senza P.IVA per fattura B2B), questi hanno **precedenza visiva** sul risultato economico. Il prezzo non deve mai nascondere una condizione che impedirebbe la vendita o la produzione.

**P7 · Ogni informazione si inserisce una sola volta** *(nuovo)*  
Ogni dato viene inserito **una sola volta** nel punto di raccolta più naturale e riutilizzato automaticamente in tutti i moduli successivi lungo il flusso:

> **CRM → Preventivo → Contratto → Rilievo → Produzione → Posa → Assistenza**

Il commerciale non ridigita l'indirizzo del cliente nel contratto. Il rilevatore non ridigita le misure indicative — le riceve dal preventivo e le sovrascrive con quelle definitive. Il produzione non ridigita colori/vetri/ferramenta — li legge dal contratto approvato. Il posatore non ridigita l'indirizzo — lo riceve dalla commessa.

### 1.2 Regola architetturale — Fonte autorevole unica

> **Ogni dato deve avere una sola fonte autorevole. Gli altri moduli lo leggono ma non lo duplicano.**

Questa regola è **non negoziabile**. Il dettaglio della matrice Dato → Fonte → Lettori è in §14. Conseguenze pratiche:

- Un indirizzo cliente si modifica una sola volta, sull'anagrafica cliente. Preventivi e contratti già emessi conservano uno **snapshot immutabile** del dato al momento dell'emissione, ma i nuovi preventivi leggono sempre la fonte autorevole aggiornata.
- Un prezzo di listino si modifica una sola volta, sul listino. I preventivi già inviati non cambiano (snapshot); i nuovi preventivi usano il listino aggiornato.
- Le misure indicative vivono sul preventivo. Le misure definitive vivono sul rilievo. Nessuna copia bidirezionale: la produzione **legge sempre e solo il rilievo**.
- I contatti (email, telefono) vivono sull'anagrafica. Le comunicazioni (email inviate, WhatsApp) vivono sui log — che referenziano il contatto autorevole tramite id.

### 1.3 Antipattern eliminati
- Tabelle a 15 colonne
- Modal dentro modal
- "Sei sicuro?" per operazioni non distruttive
- Salvataggio manuale (autosave silenzioso con indicatore)
- Terminologia tecnica (`BOM`, `recipe`, `snapshot`, `aggregate`) esposta al commerciale
- Configurazioni obbligatorie prima di poter iniziare a lavorare
- **Ridigitazione di dati già presenti** (violazione P7)
- Fonti concorrenti dello stesso dato (violazione Regola Architetturale)

---

## 2 · Utenti & ruoli

### 2.1 Personas operative (11 ruoli identificati)

**A · Marco — Commerciale** (persona primaria, ~65% dell'uso)  
45 anni, ex-installatore. Passa 60% in trasferta, 40% ufficio. Usa smartphone in casa cliente. Metrica: preventivi/giorno, tasso di chiusura.

**B · Laura — Back Office**  
38 anni. Amministrazione ordini, contratti, fatturazione, coordinamento posa. Doppio monitor. Ha bisogno di tabelle dense filtrabili, export Excel. Metrica: tempo accettazione → consegna materiali.

**C · Sara — Amministratore configurazione** *(distinta da back office)*  
40 anni. Gestisce listini, formule, catalogo, template email/PDF, permessi, integrazioni. Non entra nel flusso commerciale.

**D · Roberto — Titolare / Responsabile commerciale**  
55 anni. Vede tutto, decide tutto. Metrica: fatturato/mese, margine medio, ciclo vendita medio.

**E · Giulio — Tecnico Rilevatore** *(nuovo)*  
50 anni. Va in cantiere con laser meter dopo firma contratto. Rileva misure definitive, scatta foto, segnala difformità (es. spalletta storta, controtelaio da sostituire), approva rilievo tecnico o richiede modifica contratto se emerge scostamento significativo.

Può:  
- consultare la commessa (dati contratto, misure indicative, prodotti)  
- inserire le misure definitive per ogni vano  
- caricare fotografie prima intervento  
- segnalare difformità con note strutturate  
- approvare il rilievo tecnico  

Non può:  
- modificare prezzi  
- modificare sconti  
- vedere margini  
- modificare listini  
- vedere altre commesse non a lui assegnate  

**F · Anna — Responsabile Tecnico** *(nuovo, distinto da produzione)*  
42 anni. Approva tecnicamente le commesse dopo rilievo, controlla distinta base, autorizza lista di taglio, gestisce qualità e non conformità. Ponte tra tecnico rilevatore e produzione.

Gestisce:  
- approvazione tecnica post-rilievo  
- distinta base finale (BOM)  
- lista di taglio  
- controllo materiali disponibili  
- programmazione tecnica  
- qualità  
- non conformità e loro chiusura  

**G · Franco — Responsabile Produzione** *(nuovo)*  
48 anni. Programma la produzione, assegna operatori, coordina reparto taglio/saldatura/assemblaggio, monitora avanzamento commesse.

**H · Pietro — Operatore Produzione** *(nuovo)*  
30 anni. Esegue una fase operativa (taglio, ferramenta, vetraggio). Vede solo il lavoro assegnato + istruzioni di lavorazione + spunta completamento.

**I · Salvo — Posatore / Caposquadra** *(nuovo)*  
35 anni. Va in cantiere per l'installazione. Usa quasi esclusivamente lo smartphone.

Può:  
- vedere solo i lavori assegnati (giornalieri/settimanali)  
- consultare indirizzo cantiere e contatti cliente  
- vedere i materiali previsti nella commessa  
- caricare foto prima e dopo intervento  
- compilare verbale di posa  
- raccogliere firma cliente su verbale  
- aprire ticket di assistenza per difformità/rotture  

Non può vedere:  
- margini, costi industriali, dati economici  
- altre commesse  
- prezzi vendita  

**J · Sig. Rossi — Cliente finale**  
Non installa nulla, non fa login. Riceve link, apre preventivo/contratto, firma dal telefono, riceve PDF firmato, riceve aggiornamenti stato.

**K · Emergent Platform Owner**  
Vede tutti i tenant, gestisce pricing SaaS, onboarding nuovi clienti. Area dedicata `/platform/*`.

### 2.2 Matrice completa dei permessi (11 ruoli × dimensioni chiave)

| Ruolo | Vede prezzi vendita | Vede costi/margini | Modifica prezzo unitario | Sconto commerciale | Firma contratti (interna) | Modifica listini | Rileva misure definitive | Approva tecnicamente | Gestisce produzione | Compila verbale posa | Gestisce utenti |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Commerciale | ✅ | ❌ | ❌ | ✅ entro max % | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Commerciale senior | ✅ | ❌ | ✅ con audit | ✅ oltre max | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Back Office | ✅ | ✅ margine | ✅ con audit | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Amministratore config | ✅ | ✅ tutto | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Titolare | ✅ | ✅ tutto | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Tecnico Rilevatore | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Responsabile Tecnico | ❌ | ✅ costi materiali | ❌ | ❌ | ❌ | ❌ (solo lettura) | ❌ | ✅ | parziale | ❌ | ❌ |
| Responsabile Produzione | ❌ | ✅ costi materiali | ❌ | ❌ | ❌ | ❌ (solo lettura) | ❌ | ❌ | ✅ | ❌ | ❌ |
| Operatore Produzione | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ solo fase assegnata | ❌ | ❌ |
| Posatore / Caposquadra | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Cliente | ❌ (vede solo suo prev/contratto) | ❌ | ❌ | ❌ | ✅ firma | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Platform Owner | Cross-tenant | Cross-tenant | ❌ | ❌ | ❌ | ✅ template globali | ❌ | ❌ | ❌ | ❌ | ✅ tenant admin |

### 2.3 Isolamento tenant
Tutti i ruoli operativi (A–J) operano dentro un singolo tenant. Il **Platform Owner** è l'unico ruolo cross-tenant. Ogni query backend applica filtro `tenant_id` in modo automatico tramite deps FastAPI.

---

## 3 · Casi d'uso principali

### 3.1 Storie utente (in ordine di importanza)

**S1 · "Voglio inviare un preventivo al Sig. Rossi in 5 minuti dallo smartphone"**  
Il commerciale è nel salotto del cliente. Ha rilevato misure indicative col metro laser. Apre l'app, sceglie cliente, aggiunge vano, mette L/H/colore/vetro. Prezzo si calcola. Duplica per stanza gemella. Invia PDF via email davanti al cliente.

**S2 · "Voglio trasformare preventivo accettato in contratto firmato via link"**  
Il cliente conferma. Il commerciale apre preventivo, tocca "Genera contratto". Sceglie condizioni pagamento standard. Invia link firma. Il cliente firma dal telefono. Notifica push al commerciale entro 3 minuti.

**S3 · "Sto guardando un lead — voglio sapere tutto e cosa fare ora"**  
Apre lead, vede chi è, cosa ha chiesto, ultima interazione, prossima azione consigliata. CTA primaria già suggerita in base allo stato.

**S4 · "Ho ricevuto errore prezzo — voglio capire perché"**  
Il vano risulta `pricing_status=incomplete`. Errore parlante: *"Manca prezzo vetro 33.1/16/33.1 colore Bianco RAL 9016. Chiedi all'amministratore di aggiornare il listino."* Pulsante "Notifica amministratore" apre ticket.

**S5 · "Voglio duplicare preventivo di 3 mesi fa"**  
Duplicazione con un click. Misure preservate, prezzi RICALCOLATI dal listino attuale. Se qualcosa non è più disponibile, avviso.

**S6 · "Il contratto è firmato — chi va a fare il rilievo?"** *(nuovo)*  
Il sistema assegna automaticamente il rilievo al rilevatore configurato per l'area geografica. Notifica push a Giulio con dettagli commessa e link mappa cantiere.

**S7 · "Sono a casa Rossi per il rilievo — le misure sono diverse"** *(nuovo)*  
Giulio apre app, vede commessa, inserisce misure definitive per ogni vano. Se scostamento supera soglia (es. >5%) sistema alza flag e chiede "Confermi scostamento? Serve rifare preventivo o è accettabile?".

**S8 · "Amministratore aggiorna listino telaio 5103 da 8€/ml a 8,50€/ml"**  
Sara va in Configurazione → Listini → cerca 5103 → modifica → salva. Sistema crea nuova versione. Chiede: "Applicare da quando?". Retroattività **mai automatica** su preventivi inviati/firmati.

**S9 · "Cliente vuole cambiare colore su preventivo già inviato"**  
Duplicazione preventivo (revisione 2), cambio colore, nuovo prezzo. Invia come "Revisione 2 del preventivo Q-2026-000123".

**S10 · "Voglio vedere stato commesse in produzione"**  
Vista Kanban: Rilievo → Approvazione tecnica → Ordine materiali → In produzione → Pronto consegna → Installato.

**S11 · "Posatore in cantiere per installazione"** *(nuovo)*  
Salvo apre app, vede lavori del giorno, tap sul primo. Vede indirizzo, contatti, materiali previsti. Foto pre-intervento. Installa. Foto post-intervento. Compila verbale (checklist). Cliente firma verbale su schermo. Chiude intervento.

**S12 · "Cerco un cliente ma non ricordo il nome"**  
`Cmd+K` → "rossi" → lista risultati → click.

### 3.2 Anti-storie (cosa non deve mai succedere)
- Commerciale che digita a mano prezzo
- Preventivo con vano a €0
- Cliente che riceve richiesta firma e non capisce come firmare
- Produzione che parte senza rilievo tecnico approvato
- Rilevatore che vede prezzi/margini
- Posatore che vede altre commesse

---

## 4 · Customer Journey

### 4.1 Journey del Commerciale (Marco)

```
T0 · Lead (fonte: sito / passaparola / campagna)
   → Notifica push "Nuovo lead: Sig. Rossi, cambio 5 finestre"
   → Marco apre lead, un click "Programma sopralluogo"

T1 · Sopralluogo commerciale
   → Marco in casa cliente, rileva misure indicative col metro laser
   → Lead → Cliente (un click)
   → Nuovo preventivo (wizard 6 step)

T2 · Configurazione preventivo (misure indicative)
   → 6 step, prezzo real-time, PDF, invio email/WhatsApp
   → Tempo target: 8-12 minuti

T3 · Follow-up
   → Task automatico "chiama Sig. Rossi tra 3 giorni"
   → Cliente conferma → "Preventivo accettato"

T4 · Contratto
   → "Genera contratto" precompila tutto (P7)
   → Anteprima PDF integrale
   → "Invia link firma" via email + WhatsApp

T5 · Firma cliente (rotta pubblica /sign/:token)
   → Cliente firma dallo smartphone
   → Marco riceve notifica push in tempo reale
   → Contratto → stato "firmato" (terminale, immutabile)

T6 · Handoff a Rilevatore
   → Marco esce dal flusso — la sua vendita è chiusa
   → Sistema assegna commessa a rilevatore area geografica
   → Provvigione calcolata automaticamente
```

### 4.2 Journey del Tecnico Rilevatore (Giulio) *(nuovo)*

```
T0 · Notifica assegnazione
   → Push "Nuova commessa da rilevare: Sig. Rossi, 5 vani"
   → Data suggerita in base a agenda

T1 · Programmazione visita
   → Giulio apre commessa, conferma appuntamento con cliente
   → Sistema invia conferma automatica a cliente (email + WhatsApp)

T2 · Rilievo in cantiere (mobile)
   → Apre commessa, vede misure indicative dal preventivo
   → Per ogni vano: inserisce misure definitive L_def, H_def
   → Sistema calcola scostamento vs misure indicative
   → Se scostamento > soglia: chiede conferma esplicita + nota
   → Scatta foto pre-intervento per ogni vano
   → Segnala difformità (es. spalletta storta) con note strutturate

T3 · Approvazione rilievo
   → Se scostamento sotto soglia: "Approva rilievo" → commessa passa a Responsabile Tecnico
   → Se scostamento significativo o difformità gravi: "Richiedi variante contratto"
     → Commerciale notificato, deve preparare revisione contratto o rinegoziazione
     → Commessa in stato "in attesa variante"

T4 · Chiusura
   → Rilievo approvato → Giulio esce dal flusso
   → Commessa passa a Responsabile Tecnico (Anna)
```

### 4.3 Journey del Responsabile Tecnico (Anna) *(nuovo)*

```
Riceve commessa con rilievo approvato
   ↓
Verifica distinta base finale (calcolata da misure definitive)
   ↓
Controlla disponibilità materiali
   ↓
Autorizza lista di taglio → produzione può programmare
   ↓
Monitora avanzamento produzione
   ↓
Chiude non conformità se emergono
   ↓
Approva commessa "pronta per consegna"
```

### 4.4 Journey del Posatore (Salvo) *(nuovo)*

```
T0 · Programma settimanale
   → Salvo apre app lunedì mattina
   → Vede 5 lavori assegnati settimana
   → Tap primo lavoro

T1 · Preparazione (dal telefono)
   → Vede indirizzo, contatti cliente, materiali previsti
   → Naviga con Google Maps (link diretto)

T2 · In cantiere
   → Foto pre-intervento (checklist obbligatoria per ogni vano)
   → Segnala eventuali problemi (controtelaio ammalorato, ecc.)

T3 · Installazione
   → Se serve chiama Responsabile Tecnico via app (link diretto)
   → Materiali spuntati man mano

T4 · Chiusura intervento
   → Foto post-intervento
   → Verbale di posa (checklist: pulizia, funzionamento, sigillature, ecc.)
   → Cliente firma verbale sul telefono di Salvo
   → Commessa → "installata"

T5 · Assistenza (se serve)
   → Se cliente chiama entro X giorni per problemi
   → Salvo può aprire ticket di assistenza dal detail commessa
```

### 4.5 Journey dell'Amministrazione (Laura)

Laura opera sul back office post-firma:

```
Contratti firmati oggi (dashboard)
   → verifica dati fatturazione (P.IVA, PEC, indirizzo)
   → segna "pronto per ordine materiale"
   → sistema genera Ordini Fornitori dai listini
   → invia richieste ai fornitori (email precompilata)
   → traccia consegna materiali
   → quando tutto in magazzino → commessa "pronto produzione"
```

Laura NON modifica preventivi altrui. Se serve modifica, richiede revisione al commerciale (P7 rispettato: unica fonte del prezzo è il preventivo del commerciale).

### 4.6 Journey del Cliente (Sig. Rossi)

**Punto 1**: email preventivo → link → apre PDF inline, "Ho domande" o "Accetta"  
**Punto 2**: email contratto pronto → un pulsante "Firma contratto"  
**Punto 3**: `/sign/:token` mobile-first — legge, checkbox consenso, firma dito, conferma  
**Punto 4**: post-firma → conferma su schermo + PDF firmato via email  
**Punto 5**: email conferma appuntamento rilievo  
**Punto 6**: (eventuale) email conferma appuntamento posa  
**Punto 7**: email chiusura intervento con verbale allegato

---

## 5 · Mappa schermate

### 5.1 Schermate PUBBLICHE (no login)
| Route | Nome | Ruolo | Priorità |
|---|---|---|---|
| `/` | Landing marketing | pubblico | P1 |
| `/login` | Login | tutti | P0 |
| `/forgot-password`, `/reset-password` | Recupero password | tutti | P0 |
| `/accept-invitation` | Accettazione invito | nuovi utenti | P0 |
| `/p/:token` | Preventivo pubblico (view+accept) | cliente | P0 |
| `/sign/:token` | Firma contratto mobile-first | cliente | P0 |
| `/onboarding` | Onboarding tenant | admin nuovo | P1 |

### 5.2 Schermate COMMERCIALE (menu principale) — 7 voci
| Route | Nome |
|---|---|
| `/dashboard` | Home commerciale |
| `/leads`, `/leads/:id` | Lead |
| `/customers`, `/customers/:id` | Clienti |
| `/quotes`, `/quotes/new`, `/quotes/:id` | Preventivi (wizard 6 step) |
| `/contracts`, `/contracts/:id` | Contratti |
| `/calendar` | Calendario |
| `/activities` | Attività *(nuovo, unifica task/promemoria/follow-up)* |

### 5.3 Schermate BACK OFFICE
| Route | Nome |
|---|---|
| `/production` | Kanban commesse |
| `/production/:id` | Commessa detail |
| `/billing` | Fatturazione |
| `/payments` | Piani pagamento + solleciti |
| `/service` | Ticket assistenza |

### 5.4 Schermate TECNICO RILEVATORE *(nuovo)*
| Route | Nome |
|---|---|
| `/survey/assigned` | Rilievi assegnati |
| `/survey/:commessaId` | Rilievo di dettaglio (misure def., foto, difformità) |

### 5.5 Schermate PRODUZIONE (Responsabile Tecnico, Responsabile Produzione, Operatore) *(nuovo)*
| Route | Nome |
|---|---|
| `/production/tech-approval` | Approvazione tecnica commesse |
| `/production/schedule` | Programmazione produzione |
| `/production/operator` | Vista operatore (fasi assegnate) |
| `/production/qc` | Controllo qualità e non conformità |

### 5.6 Schermate POSATORE *(nuovo)*
| Route | Nome |
|---|---|
| `/install/assigned` | Lavori assegnati (giornalieri/settimanali) |
| `/install/:commessaId` | Cantiere: foto, verbale, firma cliente |

### 5.7 Sezione CONFIGURAZIONE (icona ⚙️ in header, solo admin)
| Route | Nome |
|---|---|
| `/settings/company` | Anagrafica azienda |
| `/settings/users` | Utenti & ruoli |
| `/settings/catalog` | Catalogo prodotti |
| `/settings/pricelists` | Listini componenti |
| `/settings/glass` | Listino vetri |
| `/settings/hardware` | Kit ferramenta |
| `/settings/installation` | Regole montaggio |
| `/settings/accessories` | Costi accessori (16 categorie) |
| `/settings/formulas` | Formule di calcolo |
| `/settings/import` | Import listini |
| `/settings/email` | SMTP + template email |
| `/settings/clauses` | Clausole contrattuali |
| `/settings/templates` | Template PDF |
| `/settings/legal-entities` | Ragioni sociali multiple |
| `/settings/integrations` | Integrazioni |
| `/settings/audit` | Audit log |
| `/settings/legacy` | Preventivi/contratti legacy (read-only) |

### 5.8 Sezione PLATFORM OWNER
| Route | Nome |
|---|---|
| `/platform/tenants` | Tenants |
| `/platform/pricing` | Piani SaaS |
| `/platform/health` | Stato piattaforma |

---

## 6 · Schema navigazione

### 6.1 Chrome desktop (≥1024px)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 🏠 [Panorama Pilot]   [Cmd+K Cerca...]      🔔  ⚙️  👤 Marco Rossi        │
├──────────────────────────────────────────────────────────────────────────┤
│ ┌─────────────┐  ┌──────────────────────────────────────────────────────┐│
│ │ ▸ Dashboard │  │                                                      ││
│ │ ▸ Lead      │  │                                                      ││
│ │ ▸ Clienti   │  │              MAIN CONTENT                            ││
│ │ ▸ Preventivi│  │                                                      ││
│ │ ▸ Contratti │  │                                                      ││
│ │ ▸ Calendario│  │                                                      ││
│ │ ▸ Attività  │  │                                                      ││
│ │             │  │                                                      ││
│ │ [+ Nuovo ▾] │  │                                                      ││
│ └─────────────┘  └──────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────────┘
```

- Sidebar 220px fissa
- Pulsante "+ Nuovo" in fondo → dropdown creazione rapida
- Header 56px, `Cmd+K` prominente al centro
- Icona 🔔 apre pannello notifiche (drawer slide-in)
- Icona ⚙️ apre `/settings/*` (drawer laterale full-height per ammin.)

### 6.2 Chrome mobile (<768px)

```
┌──────────────────────────────┐
│ ☰   Panorama Pilot      🔔   │
├──────────────────────────────┤
│                              │
│      MAIN CONTENT            │
│                              │
├──────────────────────────────┤
│  🏠  💼  📄  📁  ⋯          │  Bottom nav 5 icone
└──────────────────────────────┘
```

Il menu Attività appare come sesta voce nel drawer laterale su mobile.

### 6.3 Notifiche: separate da Attività *(chiarito)*

- **Notifiche** = eventi istantanei (nuovo lead, contratto firmato, alert AI CFO). Vivono nell'icona 🔔 in header e in un centro notifiche `/notifications/center` (accessibile dalla campanella, non nel menu principale).
- **Attività** = azioni operative da svolgere. Raccoglie:
  - Follow-up commerciali (chiama tra N giorni)
  - Chiamate programmate
  - Appuntamenti (sopralluoghi, firma, rilievi, posa)
  - Preventivi incompleti (bozze aperte da >7 giorni)
  - Contratti da inviare (accettati ma non inviati)
  - Pagamenti da ricordare (solleciti)
  - Attività scadute (task overdue)
  - Promemoria custom

Vista Attività: **timeline con giorno di riferimento** + filtri "Oggi / Domani / Settimana / Scadute". Ogni riga ha CTA diretta ("Chiama", "Apri preventivo", "Invia contratto", "Segna come fatta"). Ispirazione: Superhuman todos + Linear cycle view.

### 6.4 Command Palette (Cmd+K)

Come descritto in v2.0. Diventa il modo primario per utenti esperti.

---

## 7 · Wireframe testuali delle schermate chiave

### 7.1 Dashboard commerciale
Come v2.0 — KPI row + Task del giorno + Pipeline preventivi + Notifiche recenti.

### 7.2 Lista Preventivi
Come v2.0. Aggiunta: filtro "solo con misure indicative" (in attesa di rilievo) per commerciali senior.

### 7.3 Wizard Nuovo Preventivo — **6 STEP** *(riformulato)*

Layout base con `<WizardStepper>`:

```
┌────────────────────────────────────────────────────────────────────────┐
│  ← Preventivi    Q-000126 · Bozza · Auto-saved 3s fa                  │
├────────────────────────────────────────────────────────────────────────┤
│    ①  ②  ③  ④  ⑤  ⑥        ← step indicator                          │
│    Cli Van Cfg Rie Eco Doc                                             │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│                  [CONTENUTO STEP CORRENTE]                             │
│                                                                        │
├────────────────────────────────────────────────────────────────────────┤
│  ← Indietro                        [Salva bozza]      Avanti →        │
└────────────────────────────────────────────────────────────────────────┘
```

Autosave silenzioso ogni 3s. Nessun pulsante "Salva" per step corrente.

#### STEP 1 · Cliente e contesto

```
Cliente e contesto

  🔍 Cerca cliente esistente...
  oppure crea nuovo cliente:
  ○ Persona fisica    ○ Azienda
  [Nome / Ragione sociale]
  [Email]      [Telefono]
  [Indirizzo residenza]

  Indirizzo installazione:
  ☐ Uguale a indirizzo residenza
  [Via]  [Cap]  [Città]  [Provincia]

  Origine lead:
  [Web / Passaparola / Campagna / Cliente esistente / Altro ▾]

  Commerciale responsabile:
  [Marco Rossi ▾]  ← default utente corrente, modificabile solo se admin

  Note preventivo (interne, non visibili al cliente):
  [                                                          ]
```

Dati letti dall'anagrafica cliente esistente vengono precompilati (P7). Nessuna ridigitazione.

#### STEP 2 · Ambienti e vani

```
Organizza i vani per ambiente.

  ┌─────────────────────────────────────────────────┐
  │  📁 Cucina                          [+ Vano]   │
  │    • Finestra 1 anta · 900×1500 · Bianco       │
  │    • Portafinestra 2 ante · 1400×2200 · Grigio │
  └─────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────┐
  │  📁 Camera matrimoniale             [+ Vano]   │
  │    • Finestra 1 anta · 900×1500                │
  └─────────────────────────────────────────────────┘

  [+ Aggiungi ambiente]
  Suggerimenti: [+ Cucina] [+ Bagno] [+ Camera] [+ Soggiorno]

  Azioni per vano: Duplica · Elimina · Sposta in altro ambiente · Riordina (drag)
```

#### STEP 3 · Configurazione vano — **Configurazione E prezzo insieme** *(unificato)*

Layout split-screen desktop, tab su mobile:

```
┌─────────────────────────────────────┬───────────────────────────────────┐
│  CONFIGURAZIONE                     │  DISEGNO + PREZZO                 │
│                                     │                                   │
│  Serie:                             │  ┌──────────────────────────┐    │
│  ○ ProEvolution                     │  │                          │    │
│  ○ ProEvolution Restauro            │  │   Schema SVG del vano    │    │
│                                     │  │   (aggiornato live)      │    │
│  Tipologia:                         │  │                          │    │
│  ○ Finestra                         │  └──────────────────────────┘    │
│  ○ Portafinestra                    │                                   │
│  ○ Fisso                            │                                   │
│  ○ Scorrevole                       │  💰 Prezzo vano (live)            │
│                                     │                                   │
│  Apertura:                          │           € 1.240,00              │
│  [Anta ribalta ▾]                   │                                   │
│                                     │  Supplementi:                     │
│  Numero ante:  1  2  3  4           │  • Premium PVC       + €  74,40   │
│                                     │  • Vetro selezione   + € 108,00   │
│  Dimensioni:                        │                                   │
│  L [900] mm     H [1500] mm         │  ⚠️ Errori / dati mancanti:       │
│                                     │  (nessuno — pronto per salvare)   │
│  Colori:                            │                                   │
│  Interno [Bianco RAL 9016 ▾]        │  [ⓘ Dettaglio calcolo] ← permesso │
│  Esterno [Bianco RAL 9016 ▾]        │                                   │
│  ☐ Premium (+6%)                    │                                   │
│                                     │                                   │
│  Vetro: [33.1/16/33.1 ▾]            │                                   │
│  Ferramenta: [Kit standard ▾]       │                                   │
│  Accessori: ☐ Zanzariera ☐ Cass.    │                                   │
│  Montaggio: ☐ Sì ☐ Smontaggio       │                                   │
│                                     │                                   │
└─────────────────────────────────────┴───────────────────────────────────┘
```

**Sono contemporaneamente visibili in questo step**:
- Disegno del vano (SVG live)
- Prezzo automatico (aggiornato con debounce 400ms)
- Supplementi (rincaro Premium PVC, upgrade vetro, ecc.)
- Errori bloccanti (`MISSING_*`)
- Dati mancanti (avviso "seleziona un vetro" ecc.)

Il tasto **"Salva vano e continua"** è **disabilitato** finché `pricing_status ≠ ok`.

#### STEP 4 · Riepilogo vani

```
Riepilogo vani configurati

  ┌─────────────────────────────────────────────────┐
  │  Cucina · Finestra 1 anta                       │
  │  900×1500 · Bianco · Doppio vetro               │
  │  1x                                    € 1.240  │
  │  [✎ Modifica] [📄 Duplica] [🗑 Elimina]         │
  └─────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────┐
  │  Cucina · Portafinestra 2 ante                  │
  │  1400×2200 · Grigio · Triplo vetro              │
  │  1x                                    € 2.840  │
  │  [✎] [📄] [🗑]                                  │
  └─────────────────────────────────────────────────┘

  Totale vani:                              € 4.080
```

#### STEP 5 · Condizioni economiche

```
Condizioni economiche

  Imponibile:                              € 4.080,00
  Sconto commerciale: [ 5 %]              − €   204,00
  Trasporto e servizi:                     + €   120,00
  Montaggio:                               + €   450,00
  ─────────────────────────────────────────────────────
  Imponibile finale:                        € 4.446,00
  IVA 22%:                                  € 978,12
  ═════════════════════════════════════════════════════
  TOTALE:                                   € 5.424,12

  Pagamento:
  ○ Acconto 30% + Saldo alla consegna
  ○ Acconto 50% + Saldo consegna
  ● Acconto 30% + 60% pre-consegna + 10% installazione
  ○ Finanziamento (contatta amministrazione)
  ○ Personalizzato: acconto [30]% saldo [70]%

  Validità preventivo: [30 giorni ▾]
  Tempi di consegna: [45 giorni lavorativi]
```

#### STEP 6 · Documento e azioni

```
Documento e azioni

  [📄 Anteprima PDF]  [📥 Scarica PDF]

  Condividi con il cliente:
  ○ Email: cliente@example.com    ✎
  ○ WhatsApp: +39 333 1234567     ✎
  ○ Link condivisibile (copia)

  [✉ Invia preventivo]

  Azioni successive (dopo accettazione):
  [Genera contratto] [Richiedi firma]
```

**Il rilievo tecnico NON è uno step del preventivo.** Come specificato in §7.4.

### 7.4 Flusso completo Vendita → Rilievo → Produzione → Posa *(nuovo)*

```
Preventivo (misure INDICATIVE dichiarate dal commerciale)
     ↓ accettazione cliente
Contratto (misure INDICATIVE ereditate dal preventivo)
     ↓ firma cliente
Rilievo tecnico (misure DEFINITIVE — sovrascrivono le indicative sulla commessa)
     ↓ approvazione rilevatore
Approvazione tecnica (Responsabile Tecnico)
     ↓ autorizzazione lista di taglio
Programmazione produzione
     ↓
Produzione (taglio → assemblaggio → vetraggio → controllo qualità)
     ↓ commessa "pronta consegna"
Consegna materiali in cantiere
     ↓
Posa (installazione + verbale + firma cliente)
     ↓
Assistenza (eventuali ticket post-vendita)
```

### 7.5 Pagina firma (`/sign/{token}`) — mobile-first *(requisiti espansi)*

**Requisiti tecnici e legali**:

- **Token non prevedibile** — generato da CSPRNG (min 128 bit entropia), non enumerabile
- **Scadenza token** — default 7 giorni dall'emissione, configurabile
- **Revoca token** — un amministratore può revocare un token da back office; token revocato produce pagina "Link non più valido"
- **Collegamento a un solo documento** — un token vale per un solo contratto (`contract_id`). Non riutilizzabile per altri documenti
- **Consenso esplicito** — checkbox obbligatoria "Ho letto e accetto termini, condizioni e informativa privacy ex GDPR"
- **Nome del firmatario** — input obbligatorio, precompilato dall'anagrafica cliente, modificabile
- **Firma disegnata** — canvas responsive con supporto **touch + mouse + pennino** (pointer events)
- **Timestamp** — istante ISO 8601 UTC, catturato server-side al momento della conferma
- **IP** — indirizzo IP client catturato server-side
- **User Agent** — stringa UA browser catturata server-side
- **Hash documento** — SHA-256 del PDF originale al momento della firma, incluso nel record firma
- **Audit trail** — record immutabile in `signature_events` con tutti i metadati sopra + eventuali retry/errori

**Layout mobile-first** (già descritto in v2.0 §7.5).

**Nota terminologica**: questa implementazione realizza una **firma elettronica semplice** ex eIDAS (Reg. UE 910/2014, art. 3, punto 10). NON è una firma elettronica avanzata né qualificata. La progettazione di una firma avanzata o qualificata (con OTP SMS/email/SPID + certificato) è **estensione futura** fuori scope di questa versione, e sarà progettata in un documento dedicato secondo i requisiti normativi applicabili.

### 7.5.1 · Signature Provider abstraction *(nota architetturale)*

La firma canvas interna è la prima implementazione, ma **non deve essere l'unica**. L'architettura backend deve prevedere fin da subito un layer di astrazione:

```
class SignatureProvider(ABC):
    def initiate_signing(contract, signer) -> SignatureSession
    def get_status(session_id) -> SignatureStatus
    def get_signed_document(session_id) -> bytes
    def revoke(session_id) -> None
```

Implementazioni previste:
- `InternalCanvasSignatureProvider` — canvas + hash + audit trail (la prima, in scope)
- `DocuSignSignatureProvider` — integrazione API DocuSign (futura)
- `NamirialSignatureProvider` — provider certificato italiano (futura)
- `AdESSignatureProvider` — firma elettronica avanzata via SPID/CIE (futura)

Il router `/api/contracts/{id}/sign` chiama `signature_provider.initiate_signing()` senza sapere quale implementazione sta usando. Il tenant può scegliere il provider in Configurazione → Firma. Le migrazioni tra provider **non richiedono riscrittura** del resto del sistema (contratti, PDF, audit, notifiche). Le firme già emesse restano legate al provider che le ha prodotte.

---

## 8 · Flussi operativi (state machines completi)

### 8.1 Ciclo preventivo

```
[bozza] --send--> [inviato]
                     ├── accept --> [accettato] --generate_contract--> (contratto)
                     ├── reject --> [rifiutato] --replace--> [bozza revisione N+1]
                     └── expire --> [scaduto] --replace--> [bozza revisione N+1]
[bozza] --delete--> 🗑
```

### 8.2 Ciclo contratto

```
[bozza] --ready--> [pronto_firma]
                       └── send_to_customer --> [sent]
                            ├── customer_views --> [viewed]
                            │    ├── customer_signs --> [firmato]  ← TERMINALE
                            │    ├── customer_rejects --> [rifiutato] --replace--> new revision
                            │    └── expires (7gg) --> [scaduto]
                            └── revoke_by_admin --> [revocato]
```

**`firmato`** è stato **terminale immutabile**. Modifiche successive → nuova revisione con riferimento al padre.

### 8.3 Ciclo rilievo tecnico *(nuovo)*

```
[in_attesa_assegnazione] --assign--> [assegnato_al_rilevatore]
    └── survey_scheduled --> [appuntamento_fissato]
         └── survey_completed --> [rilievo_completato]
              ├── approved --> [rilievo_approvato] --> (approvazione_tecnica)
              └── request_variant --> [in_attesa_variante_contratto]
                    └── commerciale prepara revisione contratto
                         └── nuovo contratto firmato --> [rilievo_completato] (loop)
```

### 8.4 Ciclo commessa produzione *(nuovo)*

```
[rilievo_approvato]
   └── tech_approve --> [approvazione_tecnica_completata]
        └── authorize_cut_list --> [lista_taglio_autorizzata]
             └── order_materials --> [materiali_ordinati]
                  └── materials_arrived --> [pronto_produzione]
                       └── schedule --> [in_produzione]
                            ├── phase_cutting --> [in_taglio]
                            ├── phase_hardware --> [in_ferramenta]
                            ├── phase_glazing --> [in_vetraggio]
                            └── phase_qc --> [in_controllo_qualita]
                                 ├── qc_ok --> [pronto_consegna]
                                 └── qc_ko --> [non_conformita_aperta] --resolve--> loop
```

### 8.5 Ciclo posa *(nuovo)*

```
[pronto_consegna]
   └── delivery_scheduled --> [consegna_programmata]
        └── delivery_done --> [consegnato_in_cantiere]
             └── installation_start --> [in_installazione]
                  ├── installation_complete + verbale_firmato --> [installato]  ← TERMINALE
                  └── installation_issue --> [problema_posa] --resolve--> loop
```

### 8.6 Ciclo assistenza *(nuovo)*

```
[ticket_aperto] --triage--> [in_triage]
    ├── assign --> [assegnato] --resolve--> [risolto]  ← TERMINALE
    ├── reject --> [chiuso_senza_intervento]  ← TERMINALE
    └── escalate --> [escalation] --resolve--> [risolto]
```

### 8.7 Regole di cambio stato commesse (invariants)

- **Da bozza a inviato (preventivo)**: richiede `pricing_status=ok` su TUTTI i vani. Zero vani a €0.
- **Da accettato a contratto**: richiede accettazione esplicita (checkbox back office + firma email cliente o telefono con nota audit).
- **Da contratto a firmato**: solo tramite pagina `/sign/:token` con checkbox consenso, canvas non vuoto, nome firmatario, IP, UA, hash documento catturati.
- **Da firmato a rilievo assegnato**: automatico entro 15 minuti dalla firma.
- **Da rilievo approvato a produzione**: richiede approvazione esplicita Responsabile Tecnico. Il sistema NON promuove automaticamente.
- **Da produzione a consegna**: richiede QC positivo su tutti i vani della commessa.
- **Da consegna a installato**: richiede verbale posa firmato dal cliente.

### 8.8 Condizioni che BLOCCANO la produzione *(nuovo)*

Una commessa **non può** entrare in stato "in_produzione" se anche una sola di queste condizioni è vera:

| Blocco | Descrizione |
|---|---|
| `MISSING_SURVEY` | Nessun rilievo tecnico approvato |
| `SURVEY_VARIANCE_UNACKNOWLEDGED` | Scostamento misure indicative → definitive > soglia e non c'è nota di accettazione |
| `MISSING_TECH_APPROVAL` | Responsabile tecnico non ha approvato |
| `MISSING_MATERIALS` | Materiali non ancora arrivati in magazzino (fornitori non hanno consegnato) |
| `MISSING_BOM` | Distinta base non ricalcolata dalle misure definitive |
| `PAYMENT_OVERDUE` | Acconto contrattuale non incassato (regola opzionale, on/off da configurazione) |
| `OPEN_QC_ISSUES` | Ci sono non conformità aperte sulla commessa |
| `LEGAL_HOLD` | Blocco manuale amministratore (es. contestazione cliente) |

Il sistema mostra sempre il **motivo esplicito del blocco** e a chi rivolgersi per sbloccare (P6 rispettato).

---

## 9 · Principi UX (le 10 leggi Panorama Pilot)

**Legge 1 · Un solo pulsante primario per schermata**  
Massimo una CTA primaria. Le altre sono secondarie (outline) o menu.

**Legge 2 · Risultato economico immediatamente leggibile — ma cede la scena a errori e stati critici** *(riformulato)*  
Il totale è visibile senza scrolling. Se però esistono errori bloccanti (`MISSING_*`), dati mancanti o stati critici, sono visualmente prioritari sul totale (banner rosso sopra, prezzo grigio finché non risolti).

**Legge 3 · Zero click sprecati**  
Dati deducibili dal contesto sono precompilati (data odierna, cliente selezionato, listino attivo, commerciale corrente).

**Legge 4 · Errori parlano umano**  
Mai codici tecnici al commerciale. Sempre: *"Manca prezzo vetro X per colore Y. Chiedi all'amministratore di aggiornare listino."*

**Legge 5 · Autosave silenzioso**  
Ogni azione salvata automaticamente. Nessun "Salva". Indicatore "Salvato Ns fa" discreto in header.

**Legge 6 · Mobile-first per il commerciale, il rilevatore, il posatore**  
Tutti i pattern operativi da campo (P4).

**Legge 7 · Il contesto è cliente-centrico**  
Ogni schermata operativa mostra il cliente in alto/laterale. Zero click "chi è".

**Legge 8 · Nessun jargon tecnico visibile agli utenti operativi**  
Terminologia parlante ai commerciali/rilevatori/posatori. Terminologia tecnica solo in area configurazione.

**Legge 9 · Empty state è educativo**  
Tabelle vuote mostrano illustrazione + frase chiara + CTA. Mai vuoto muto.

**Legge 10 · Undo prima di conferma**  
Azioni critiche annullabili per 10s via toast. Confirm dialog solo quando davvero irreversibile.

---

## 10 · Regole di progettazione

### 10.1 Tipografia *(aggiornato)*

- **Titoli editoriali** (H1 landing, hero, sezioni marketing): `Instrument Serif, Georgia, serif`
- **Interfaccia operativa** (form, tabelle, wizard, menu, labels, body): `Inter, system-ui, sans-serif`
- **Dati tecnici** (prezzi, codici prodotto, id, hash, snapshot): `IBM Plex Mono, ui-monospace, monospace`

**Regola inviolabile**: il font **serif NON viene mai usato in form, tabelle, wizard, aree operative**. Solo per titoli editoriali, hero, landing marketing.

**Sizing**:
- H1 editoriale (serif): 42–56px
- H1 operativo (sans): 28–32px
- H2: 20–24px
- H3: 16–18px
- Body: 15px desktop, 14px mobile
- Small: 13px
- Micro: 11px
- Line-height body: 1.55

### 10.2 Colori (base — dettaglio token in §12)
- Nero profondo primario, accento rosso mattone, background crema off-white, verde salvia per successo, ocra per avvisi
- Zero gradienti
- Nessun emoji nell'interfaccia (solo icone Phosphor)

### 10.3 Spacing e layout
- Grid 4px base
- Card padding: 24px desktop, 16px mobile
- Container max-width: 1280px

### 10.4 Motion
- Transizioni: 150-200ms cubic-bezier(0.4, 0, 0.2, 1)
- Skeleton loaders (non spinner)
- Toast slide da bottom (mobile) / top-right (desktop)

### 10.5 Iconografia e immagini
- Phosphor Icons come libreria unica
- Line art minimale per empty state
- Nessuna foto stock

### 10.6 Data density
- Tabelle: max 8 colonne visibili
- Row height: 48px desktop, 56px mobile
- Sticky header, sticky first column su mobile

---

## 11 · Componenti standard

Base: shadcn/ui. Nuovi componenti custom v2 (invariato rispetto v2.0):
`<CommandPalette>` `<WizardStepper>` `<PricingCard>` `<VanoConfigurator>` `<SignaturePad>` `<KanbanBoard>` `<ContextPanel>` `<InlinePDFViewer>` `<AutoSaveIndicator>` `<StatusPill>` `<QuickAdd>` `<UndoToast>` — più `<SurveyForm>` per rilievo, `<PostaVerbale>` per verbale posa, `<CommessaKanban>` per produzione.

---

## 12 · Design system tokens *(estesi)*

### 12.1 Font families
```css
--ppilot-font-display:  "Instrument Serif", Georgia, serif;      /* solo titoli editoriali */
--ppilot-font-body:     "Inter", system-ui, sans-serif;           /* interfaccia operativa */
--ppilot-font-mono:     "IBM Plex Mono", ui-monospace, monospace; /* dati tecnici */
```

### 12.2 Color tokens (completi)
```css
/* Superfici */
--ppilot-surface-base:          #FAFAF8;   /* background pagina */
--ppilot-surface-elevated:      #FFFFFF;   /* card, modal */
--ppilot-surface-muted:         #F4F4F0;   /* card secondaria, muted */
--ppilot-surface-inverse:       #0A0A0B;   /* footer scuro, hero notturno */

/* Testo */
--ppilot-text-primary:          #18181B;   /* titoli, testo principale */
--ppilot-text-secondary:        #52525B;   /* label, descrizioni */
--ppilot-text-muted:            #71717A;   /* helper, disabled label */
--ppilot-text-inverse:          #FAFAF8;   /* testo su fondo scuro */
--ppilot-text-link:             #0A0A0B;   /* link (sottolineato) */

/* Bordi */
--ppilot-border-subtle:         #EDEDE8;   /* separatori sottili */
--ppilot-border-default:        #E4E4E0;   /* input, card */
--ppilot-border-strong:         #A1A1AA;   /* focus, hover bordi */
--ppilot-border-inverse:        #27272A;

/* Azioni */
--ppilot-action-primary:        #0A0A0B;   /* pulsante primario */
--ppilot-action-primary-hover:  #1F1F22;
--ppilot-action-primary-active: #2A2A2E;
--ppilot-action-secondary:      #FFFFFF;   /* pulsante secondario (bordo primary) */

/* Stati */
--ppilot-state-success:         #4A7C59;   /* verde salvia */
--ppilot-state-success-bg:      #E8F0EA;
--ppilot-state-warning:         #B87333;   /* ocra */
--ppilot-state-warning-bg:      #F7ECDA;
--ppilot-state-danger:          #8B1E1E;   /* rosso profondo */
--ppilot-state-danger-bg:       #F8E2E2;
--ppilot-state-info:            #2F5C88;   /* blu neutro professionale */
--ppilot-state-info-bg:         #E3EAF2;
--ppilot-state-disabled-bg:     #F4F4F0;   /* fondo disabled */
--ppilot-state-disabled-text:   #A1A1AA;   /* testo disabled */

/* Focus (visibile su tutti gli elementi interattivi) */
--ppilot-focus-ring:            #2F5C88;
--ppilot-focus-ring-offset:     #FAFAF8;

/* Hover generico (aree cliccabili) */
--ppilot-hover-overlay:         rgba(0,0,0,.04);

/* Accent editoriale */
--ppilot-accent:                #B33A2A;
```

### 12.3 Radius e shadows
```css
--ppilot-radius-sm:  2px;
--ppilot-radius-md:  6px;
--ppilot-radius-lg:  12px;

--ppilot-shadow-sm:  0 1px 2px rgba(0,0,0,.05);
--ppilot-shadow-md:  0 4px 12px rgba(0,0,0,.08);
--ppilot-shadow-lg:  0 12px 24px rgba(0,0,0,.10);
```

### 12.4 Spacing scale
```css
--ppilot-space-1:  4px;
--ppilot-space-2:  8px;
--ppilot-space-3:  12px;
--ppilot-space-4:  16px;
--ppilot-space-5:  24px;
--ppilot-space-6:  32px;
--ppilot-space-7:  48px;
--ppilot-space-8:  64px;
```

---

## 13 · Menu specifico per ruolo *(nuovo)*

Ogni ruolo ha **il proprio menu principale**. La sezione Configurazione (⚙️) è disponibile solo a chi ha permessi admin.

### 13.1 Commerciale (menu principale — 7 voci)
Dashboard · Lead · Clienti · Preventivi · Contratti · Calendario · **Attività**

### 13.2 Commerciale Senior
Aggiunge: **Report vendite** (KPI personali estesi, provvigioni maturate)

### 13.3 Back Office
Dashboard · Contratti da elaborare · Ordini fornitori · Fatturazione · Pagamenti · Attività · Cerca

### 13.4 Amministratore configurazione
Solo la sezione Configurazione (⚙️). Nessun menu operativo — accesso completo a settings.

### 13.5 Titolare
Vede **tutto** — combinazione di Commerciale + Back Office + Configurazione. Il menu può essere personalizzato tramite "pin/unpin" delle voci più usate.

### 13.6 Tecnico Rilevatore (menu — 4 voci)
Dashboard rilevatore · Rilievi assegnati · Storico rilievi · Calendario

### 13.7 Responsabile Tecnico (menu — 5 voci)
Dashboard tecnico · Approvazioni in coda · Distinte base · Non conformità · Calendario

### 13.8 Responsabile Produzione (menu — 5 voci)
Dashboard produzione · Programmazione (Kanban) · Operatori · Non conformità · Calendario

### 13.9 Operatore Produzione (menu — 2 voci)
Fasi assegnate (oggi) · Storico personale

### 13.10 Posatore / Caposquadra (menu — 4 voci)
Lavori del giorno · Settimana · Verbali completati · Ticket aperti

### 13.11 Cliente
Nessun menu — sessione monodocumento su rotta pubblica (`/p/:token` o `/sign/:token`).

### 13.12 Platform Owner (Emergent)
Area separata `/platform/*` con: Tenants · Piani SaaS · Health · Fatturazione SaaS · Log cross-tenant.

---

## 14 · Matrice Dato → Fonte autorevole → Moduli lettori *(nuovo)*

Ogni dato ha **una sola fonte autorevole** (Regola Architetturale §1.2). Gli altri moduli lo leggono per `id` — mai lo duplicano.

| Dato | Fonte autorevole | Moduli lettori | Note snapshot |
|---|---|---|---|
| Anagrafica cliente (nome, email, tel, indirizzi) | `customers` | Preventivi, Contratti, Commesse, Fatture, Ticket assistenza | I preventivi/contratti/fatture emessi salvano uno **snapshot immutabile** dei campi anagrafici al momento dell'emissione. Modifiche successive al cliente non alterano documenti già emessi. |
| Prodotto (nome, codice, componenti associate) | `products` (catalogo) | Preventivi, Contratti, Rilievi, Distinte base | Snapshot in `pricing_snapshot` su ogni riga preventivo. |
| Listino componenti (telaio/anta/vetro/…) | `pricelists` + `pricelist_items` | Motore commerciale (compute), Preventivi | Snapshot in `pricing_snapshot` per ogni preventivo inviato. Versionamento listino: nuovo listino = nuova versione, mai overwrite. |
| Formule di calcolo (perimetro, vetro, ecc.) | `formulas` | Motore commerciale, Motore tecnico | Snapshot formula + versione nel `pricing_snapshot`. |
| Kit ferramenta | `hardware_kits` | Preventivi (selezione), Motore commerciale | Snapshot prezzo ferramenta nel pricing_snapshot. |
| Costi montaggio | `installation_rules` | Preventivi, Contratti | Snapshot regola montaggio nel pricing_snapshot. |
| Costi accessori | `accessories` | Preventivi, Contratti | Snapshot voci accessorie nel pricing_snapshot. |
| Misure indicative | `quotes.openings[].dimensions` (preventivo) | Contratto (eredita), Rilevatore (parte da qui) | Preservate storicamente sul preventivo. Non modificabili dopo firma contratto (ma sovrascrivibili dal rilievo). |
| Misure definitive | `surveys.openings[].dimensions_final` (rilievo tecnico) | Produzione (unica fonte per BOM finale), Posa | La produzione **NON legge mai** le misure indicative — solo definitive. Nessuna copia. |
| Foto rilievo | `surveys.photos` | Produzione (verifica), Posa (riferimento) | Fonte unica: rilievo. |
| Foto posa | `installations.photos` | Ticket assistenza (allegati) | Fonte unica: verbale posa. |
| Firma cliente su contratto | `contract_signatures` (immutabile) | Contratto PDF (rendering), Audit | Immutabile. Include IP, UA, hash documento, timestamp. |
| Firma cliente su verbale posa | `installation_signatures` (immutabile) | Verbale PDF, Audit | Immutabile. |
| Contratto firmato (documento) | `contracts.signed_pdf_ref` | Rilievo (link riferimento), Produzione, Fatturazione | Snapshot completo + hash SHA-256. |
| Log email inviate | `email_logs` | UI email logs, audit | Log immutabile. Non è fonte di stato — è log. |
| Ticket assistenza | `service_tickets` | Posatore (apertura), Back Office (gestione) | Fonte unica. |
| Provvigioni maturate | `commissions` (calcolate) | Report commerciali, contabilità | Calcolate da contratti firmati — mai digitate a mano. |

**Regole invariabili derivate**:
- **Nessuna doppia scrittura**: se un dato ha fonte X, moduli Y non lo scrivono. Al massimo scrivono un evento (log) che referenzia X.
- **Snapshot ≠ duplicazione**: uno snapshot storico immutabile all'interno di un documento emesso NON è duplicazione — è congelamento dello stato per riproducibilità.
- **Aggiornamenti retroattivi vietati**: modificare la fonte autorevole non deve mai cambiare documenti già emessi.

---

## 15 · Misure indicative vs misure definitive *(nuovo)*

### 15.1 Definizioni

**Misure indicative**  
Dichiarate dal **commerciale** durante il sopralluogo commerciale, con metro laser o metro tradizionale. Servono a produrre un **preventivo economicamente attendibile**. NON sono valide per la produzione. Possono essere approssimate (arrotondate a cm/mm), possono contenere errori di rilievo perché il commerciale non ha necessariamente competenza tecnica.

Vivono in `quotes.openings[].dimensions.width_indicative_mm` e `height_indicative_mm`.

**Misure definitive**  
Rilevate dal **tecnico rilevatore** dopo firma contratto, in cantiere, con strumenti calibrati e competenza tecnica. Sono le uniche misure valide per la produzione (lista di taglio, ordine materiali, ecc.). Il rilievo tecnico è OBBLIGATORIO prima di autorizzare la produzione.

Vivono in `surveys.openings[].dimensions_final.width_mm` e `height_mm`.

### 15.2 Regole di gestione

1. **Il preventivo lavora solo su misure indicative.** Il motore commerciale (`commercial_perimeter`) usa quelle misure per calcolare il prezzo.

2. **Il contratto eredita misure indicative dal preventivo.** Il PDF del contratto le riporta con la dicitura "misure indicative, soggette a rilievo tecnico".

3. **Dopo firma contratto**, il sistema crea automaticamente una richiesta di rilievo tecnico assegnata al rilevatore per l'area geografica.

4. **Il rilevatore sovrascrive** le misure con quelle definitive. Il sistema calcola lo **scostamento** in mm e in %.

5. **Soglia scostamento** (configurabile, default 3%):
   - Sotto soglia → rilievo approvabile automaticamente
   - Sopra soglia → richiede motivazione + accettazione esplicita del rilevatore, oppure richiesta variante contratto

6. **Se lo scostamento comporta variazione prezzo** oltre una soglia (default 5%), il sistema richiede al commerciale di preparare una **revisione contratto** (nuova offerta + rifirma cliente).

7. **La produzione legge esclusivamente le misure definitive.** La lista di taglio si genera dal rilievo, non dal preventivo. La distinta base finale (BOM) usa misure definitive per calcolo materiali.

8. **Non è mai lecito produrre senza rilievo approvato** (vedi §8.8 blocco `MISSING_SURVEY`).

### 15.3 Visualizzazione

Nelle schermate di rilievo, le misure indicative sono visibili in **grigio** come riferimento, quelle definitive in **nero grassetto**. Lo scostamento è visualizzato accanto:

```
Vano Cucina · Finestra 1 anta
Misure indicative:  900 × 1500 mm  (dal preventivo)
Misure definitive:  905 × 1495 mm  → scostamento +5mm / −5mm (0.5%)  ✅ entro soglia
```

---

## 16 · Gestione errori bloccanti nel preventivo *(nuovo)*

### 16.1 Cataloghi errori

Il motore `commercial_perimeter` produce, quando calcolo incompleto, uno o più codici errore:

- `MISSING_FRAME_PRICE` — Manca prezzo telaio per prodotto/colore selezionato
- `MISSING_SASH_PRICE` — Manca prezzo anta
- `MISSING_FRAME_REINFORCEMENT_PRICE` — Manca prezzo rinforzo telaio
- `MISSING_SASH_REINFORCEMENT_PRICE` — Manca prezzo rinforzo anta
- `MISSING_GLAZING_BEAD_PRICE` — Manca prezzo fermavetro
- `MISSING_MEETING_STILE_PRICE` — Manca prezzo scambio battuta (per n_ante > 1)
- `MISSING_GLASS_PRICE` — Manca prezzo vetro
- `MISSING_GLASS_FORMULA` — Manca formula vetro per configurazione
- `MISSING_GLASS_MINIMUM` — Manca minimo fatturabile vetro
- `MISSING_HARDWARE_PRICE` — Manca prezzo ferramenta
- `MISSING_INSTALLATION_PRICE` — Manca regola montaggio
- `MISSING_ACCESSORY_PRICE` — Manca prezzo accessorio selezionato
- `MISSING_HOURLY_COST` — Manca costo orario produzione (per pricing analitico)
- `MISSING_PRODUCTION_TIME` — Manca tempo produzione standard

### 16.2 Comportamento

Quando un vano ha `pricing_status=incomplete`:

- Il prezzo del vano è mostrato **grigio con lucchetto** e testo "Prezzo non calcolabile"
- Sopra al prezzo, banner rosso con:
  - Descrizione parlante dell'errore (P8: "Manca prezzo vetro 33.1/16/33.1 per colore Bianco RAL 9016")
  - Chi deve intervenire ("Chiedi all'amministratore di aggiornare listino")
  - CTA "Notifica amministratore" → crea ticket interno automatico
- Il tasto **"Salva vano e continua"** è **disabilitato**
- Il pulsante **"Invia preventivo"** al STEP 6 è **disabilitato** finché anche un solo vano è incompleto

### 16.3 Salvataggio bozza con errori

L'utente **può salvare come bozza** un preventivo con vani incompleti (per non perdere il lavoro), ma:
- Bozza NON può essere inviata (bloccato)
- Bozza NON può essere convertita in contratto (bloccato)
- Bozza appare in "Attività" come "Preventivo incompleto" con lista errori

### 16.4 Regola d'oro
**Nessun `pricing_status=incomplete` viene mai silenziosamente sostituito con `0`.** Nessuna riga vano a €0 è mai possibile. Se il motore non può calcolare, il vano è bloccato con messaggio parlante — mai zero.

---

## 17 · Comportamento dei preventivi legacy *(nuovo)*

I preventivi creati con il vecchio motore (v1, con `unit_price` digitato a mano) diventano **read-only** al momento del cutover a v2.

### 17.1 Identificazione

Sono legacy i preventivi con:
- Assenza di campo `pricing_engine` (o `pricing_engine ≠ commercial_perimeter`)
- Assenza di `pricing_snapshot` completo sui vani

### 17.2 Comportamento UI

- Compaiono nella lista preventivi con **badge `Legacy`** in colore grigio
- Aprendoli: **schermata read-only** che mostra i dati storici
- **Banner in alto**:
  > *Questo preventivo è stato creato con il motore precedente.  
  > Per modificarlo crea una nuova versione.*
- CTA nel banner: **"Crea nuova versione"** → apre il wizard v2 con precompilazione cliente + tentativo di mapping vani (dove possibile) alle nuove configurazioni. Prezzi RICALCOLATI dal motore v2 e dal listino attuale.
- Nessun campo modificabile
- Nessuna azione "Invia", "Genera contratto", ecc. disponibile
- Duplicazione crea una **nuova bozza v2** (mai duplica come legacy)

### 17.3 Migrazione

**Nessuna migrazione automatica dei dati legacy.** I preventivi legacy restano nel database come record storici, in una collection separata concettualmente (`quotes` con flag `is_legacy=true`) o filtrati tramite l'assenza di `pricing_snapshot`.

I contratti già firmati da preventivi legacy **restano validi e immutabili** — la firma è terminale. Non c'è conflitto: il contratto ha già congelato i dati economici, non ha bisogno di ricalcolo.

### 17.4 Cancellazione

Nessuna cancellazione automatica. La cancellazione dei record legacy avviene solo **dopo approvazione esplicita del Product Owner**, e comunque non prima del **completamento del ciclo di vita** di eventuali contratti/commesse ad essi collegati (i.e., non prima che il commesa sia in stato "installata" + eventuale periodo di garanzia).

---

## 18 · Criteri di accessibilità *(nuovo)*

Panorama Pilot v2 punta alla conformità **WCAG 2.1 livello AA** (target realistico prima release; livello AAA rimane obiettivo futuro).

### 18.1 Requisiti tecnici minimi

- **Contrasto testo**: rapporto ≥ 4.5:1 per body, ≥ 3:1 per testo grande (≥18pt o 14pt bold)
- **Focus visibile**: focus ring 2px offset 2px con colore `--ppilot-focus-ring` su tutti gli elementi interattivi (input, select, button, link, tab)
- **Ordine tab logico**: tab-order coerente con lettura visiva (left→right, top→bottom); nessun tabindex positivo custom
- **Aria label**: tutti gli elementi icona-only hanno `aria-label` descrittivo. Ogni icona in un bottone senza testo ha etichetta ("Modifica preventivo", non "Modifica")
- **Landmark ARIA**: `<header>`, `<nav>`, `<main>`, `<aside>`, `<footer>` — SPA usa `role="main"` per il container principale
- **Alt testi**: tutte le immagini funzionali hanno alt; decorative hanno `alt=""` esplicito
- **Screen reader friendly form**: `<label for=id>` per ogni input; messaggi errore associati via `aria-describedby`
- **Modal focus trap**: apertura modal → focus si sposta al primo elemento; chiusura → torna al trigger
- **Skip links**: "Salta al contenuto principale" come primo elemento tab

### 18.2 Requisiti operativi

- **Zoom 200%**: layout resta usabile a browser zoom 200% senza scroll orizzontale (eccetto tabelle dense che possono richiedere scroll orizzontale)
- **Riflow mobile**: layout riflow su viewport 320px (iPhone SE) senza rottura
- **Motion prefers-reduced-motion**: rispetto della media query — animazioni disabilitate se utente ha richiesto reduced motion
- **Contrasto stati**: hover, focus, disabled hanno contrasto sufficiente su sfondi diversi
- **Timeouts**: sessioni con timeout hanno avviso 60s prima con opzione "Continua sessione"
- **Errori form**: annunciati via live region (`aria-live="polite"`) — screen reader legge l'errore appena appare
- **Firma canvas**: alternativa accessibile per utenti con disabilità motorie? → **estensione futura** (firma da digitare o firma da caricare come immagine, con procedura assistita)

### 18.3 Testing

- Test automatico con **axe-core** (integrabile in CI)
- Test manuale con screen reader NVDA/VoiceOver su almeno le 5 schermate operative principali
- Test navigazione solo-tastiera su wizard preventivo e pagina firma

---

## 19 · Roadmap

### Fase 0 · UX Architecture (questo documento)
- Documento v2.1 → **in attesa approvazione**
- Solo dopo approvazione: consolidamento `design_guidelines.md` con token e regole

### Fase 1 · Backend motore integrato
- Endpoint `POST /api/quotes/:id/openings/:openingId/products/compute-and-add`
- Endpoint `PATCH /api/quote-structure/products/:lineId` (ricalcolo)
- Blocco `base_price` da input commerciale (403 senza `override_price`)
- `pricing_snapshot` completo su ogni riga vano
- Endpoint `POST /api/contracts/generate-from-quote/:quoteId` migliorato
- **Endpoint rilievo tecnico**: `/api/surveys/*` con misure definitive, scostamenti, approvazione
- Test regressione backend + testing agent

### Fase 2 · Frontend Wizard 6 step
- Nuovo `/quotes/new` e `/quotes/:id` con `<WizardStepper>` 6 step
- STEP 3 unificato configurazione+prezzo+disegno+errori
- `<CommandPalette>` globale
- `<ContextPanel>` cliente
- `<AutoSaveIndicator>`
- Route legacy nascoste dal menu (route disabilitate, marcate legacy)
- Nuova sezione `/settings/legacy` (read-only viewer)

### Fase 3 · Firma canvas mobile pubblica
- Rotta pubblica `/sign/:token` (token non prevedibile, scadenza, revoca)
- `<SignaturePad>` con `react-signature-canvas` (touch+mouse+pen)
- Validazione consenso + firma non vuota + nome firmatario
- Audit trail completo (IP, UA, timestamp, hash documento)
- Test manuale mobile viewport Playwright

### Fase 4 · Contratto da preventivo
- Precompilazione totale da `pricing_snapshot` (P7)
- Template clausole configurabili
- Anteprima PDF integrata
- Invio link firma via email/WhatsApp

### Fase 5 · Rilievo tecnico
- Nuovo ruolo utente `technical_surveyor`
- Sezione `/survey/*` con lista rilievi assegnati
- Form rilievo mobile-first con misure definitive, scostamento, foto, difformità
- Approvazione rilievo → passaggio a Responsabile Tecnico
- Blocco produzione senza rilievo approvato

### Fase 6 · Cleanup menu per ruolo
- `AppLayout` con menu differenziato per 11 ruoli
- Sezione `/settings/*` accessibile via icona ⚙️
- Route legacy marcate (non eliminate — conservazione fino ad approvazione esplicita)

### Fase 7 · Test operativo end-to-end
- Script Playwright: lead → cliente → preventivo → PDF → contratto → firma mobile → rilievo → produzione (dry run)
- Test viewport mobile (390x844)
- Test cross-browser

### Fase 8 (successiva) · Produzione e posa
- Kanban commesse produzione
- Ruolo Responsabile Tecnico + Responsabile Produzione + Operatore
- Ruolo Posatore con verbale posa
- Ticket assistenza

### Fase 9 (successiva) · Sezioni admin catalogo
- UI Kit ferramenta
- UI Montaggio & posa
- UI Costi accessori (16 categorie)
- UI Listino vetri dedicato

### Fase 10 (futuro) · Produzione + fatturazione end-to-end
- Ordini fornitori automatici da BOM finale
- Fatturazione elettronica
- Contabilità

---

## 20 · Metriche di successo

Il successo di v2 non si misura in feature spedite, ma in questi 8 numeri:

| Metrica | Baseline v1 | Target v2 |
|---|---|---|
| Tempo medio da "nuovo preventivo" a "inviato" | ~45 min | ≤ 15 min |
| % preventivi con prezzo digitato a mano | 100% | 0% |
| % preventivi con vano a €0 (bug) | ~5% | 0% |
| % firme completate su smartphone al primo tentativo | ~30% | ≥ 90% |
| % commesse in produzione senza rilievo approvato | non tracciato (rischio) | 0% |
| Tempo medio scostamento misure indicative → definitive | non tracciato | ≤ 3% |
| Click medi da lead a firma contratto | ~120 | ≤ 40 |
| NPS operativo (survey trimestrale su commerciali+rilevatori+posatori) | n/a | ≥ 40 |

---

## 21 · Rischi noti e ipotesi

### Rischi
1. **Listini incompleti al lancio** → molti motori "incomplete". Mitigazione: importer intuitivo + banner "prima di iniziare, carica listini".
2. **Utenti abituati a v1** → resistenza al cambio. Mitigazione: tutorial in-app, video 90s per ruolo.
3. **Contratti legacy** → restano vecchia UI in sola lettura (§17), non impattano.
4. **Performance mobile** → wizard ≤ 3s su 3G. Mitigazione: code splitting per step.
5. **Nuovo ruolo Rilevatore** → richiede formazione. Mitigazione: onboarding dedicato per rilevatore + video di 3 minuti.
6. **Nuovo ruolo Posatore** → dispositivi Android/iOS di generazioni miste. Mitigazione: PWA + supporto browser da Chrome 90 e Safari 14.
7. **Sovrapposizione responsabilità Responsabile Tecnico ↔ Responsabile Produzione** → i due ruoli devono avere confini chiari. Mitigazione: matrice permessi §2.2 già li distingue.

### Ipotesi da validare
- Il commerciale usa davvero lo smartphone in casa cliente? → user testing 3 commerciali reali
- Il rilevatore preferisce app mobile o tablet? → user testing 2 rilevatori
- Il posatore compila davvero il verbale sul telefono? → user testing 2 posatori
- Il cliente finale sa firmare da link email? → user test 5 clienti età varia
- La firma disegnata è legalmente sufficiente in Italia? → firma elettronica semplice ex eIDAS: sì, ma soggetta a valutazione giudice caso per caso; per contratti di valore significativo consulente legale può raccomandare firma avanzata (SPID/CIE + OTP), da progettare in fase futura secondo requisiti normativi

---

## 22 · Cosa richiede approvazione (checklist Product Owner)

- [ ] Filosofia e 7 principi + Regola Architetturale (§1)
- [ ] 11 personas + matrice permessi completa (§2)
- [ ] Journey commerciale, rilevatore, tecnico, posatore, back office, cliente (§4)
- [ ] Mappa schermate (§5) + navigazione desktop/mobile (§6)
- [ ] Wireframe wizard 6 step (§7.3)
- [ ] Wireframe firma mobile (§7.5) con requisiti legali/tecnici espansi
- [ ] Flusso completo Vendita → Rilievo → Produzione → Posa → Assistenza (§7.4, §8)
- [ ] State machine cicli (§8) + condizioni bloccanti produzione (§8.8)
- [ ] 10 leggi UX (§9)
- [ ] Regole progettazione fonts (§10) — Serif solo editoriale, Inter per UI, Mono per dati
- [ ] Design system tokens estesi (§12)
- [ ] Menu per ruolo — 11 varianti (§13)
- [ ] Matrice Dato → Fonte → Lettori (§14)
- [ ] Misure indicative vs definitive (§15)
- [ ] Gestione errori bloccanti preventivo (§16)
- [ ] Comportamento preventivi legacy (§17)
- [ ] Criteri accessibilità (§18)
- [ ] Roadmap fasi 0-10 (§19)
- [ ] Target metriche (§20)

Alla firma di approvazione, questo documento diventa la fonte unica di verità per lo sviluppo di v2. Ogni deviazione richiederà nuovo giro di approvazione.

---

**Fine documento v2.1 — pronto per revisione**
