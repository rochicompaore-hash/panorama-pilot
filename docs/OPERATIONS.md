# Centro operativo — guida di adozione

## Cosa introduce

Il centro operativo usa la collezione `sales_orders` esistente. Non crea un secondo registro delle commesse. CRM, preventivi, contratti, acquisti, produzione, magazzino, tesoreria e portale cliente restano nei moduli già presenti.

L’intervento implementa la gestione operativa di commesse e assistenze. Non certifica l’intero gestionale e non importa automaticamente Drive, contabilità, movimenti bancari o dati di una finanziaria. Un incasso deve essere riscontrato da una persona autorizzata prima di registrare la relativa verifica.

## Avvio pratico

1. Distribuire frontend e backend della stessa versione in staging, con database separato e invio email disattivato o reindirizzato al collaudo.
2. Verificare i ruoli effettivi degli utenti della propria azienda. Gli incaricati provengono dagli utenti attivi della stessa azienda.
3. Aprire **Centro operativo**. Le nuove commesse nascono già soggette ai controlli; non avanzano finché mancano le verifiche. Per quelle pregresse, **Attiva procedura e salva** adotta il controllo sulla singola commessa.
4. Registrare responsabile, prossima azione e scadenza reale. Per le commesse avanzate, verificare anche i prerequisiti delle fasi precedenti: non sono attestati automaticamente.
5. Ogni reparto inserisce un riscontro concreto nel proprio controllo. Il testo deve identificare documento/revisione/verifica; il programma conserva autore e data, ma non certifica la veridicità del contenuto.
6. Eseguire un ciclo di collaudo completo, incluse revisione ordine, annullamento, esportazione e assistenza. Dopo il collaudo, distribuire con backup e piano di ripristino dell’ambiente esistente.

Le commesse pregresse non ancora adottate conservano il comportamento precedente e sono indicate come **Da attivare**. Non c’è una migrazione automatica che possa attestare documenti mancanti. Le commesse chiuse o annullate non sono modificabili da questo centro.

## Regole di avanzamento

| Passaggio | Evidenze richieste |
| --- | --- |
| Rilievo da completare | Contratto/allegati e nulla osta amministrativo al rilievo |
| Ordine validato e fasi di fornitura | Prerequisiti precedenti, rilievo/revisione tecnica, copertura e nulla osta all’ordine |
| Posa confermata o eseguita | Prerequisiti precedenti, materiali completi/utilizzabili, nulla osta posa, squadra/mezzi/accessi |
| Chiusura | Prerequisiti precedenti, collaudo, documenti finali, verifica amministrativa e zero completamenti aperti |
| Annullamento | Motivo scritto; non richiede di completare i controlli operativi |

Un blocco aperto impedisce l’avanzamento della commessa interessata. Gli altri lavori restano utilizzabili. Una scadenza superata resta visibile e richiede gestione; non viene interpretata come prova automatica di impossibilità a lavorare.

Le verifiche sono cumulative. Una modifica a righe o indirizzo invalida contratto, controllo tecnico, copertura ordine, materiali, condizioni posa, risorse e controlli finali. Una variazione di modalità o stato del finanziamento invalida i quattro nulla osta amministrativi. Riattestarli dopo aver verificato le nuove condizioni.

**Approvato ≠ sottoscritto ≠ erogato.** Nei lavori finanziati, il rilievo richiede almeno la sottoscrizione registrata. Produzione/ordine e posa richiedono comunque i rispettivi nulla osta: il solo stato del finanziamento non li concede.

I completamenti restano sulla commessa, con numero aperto, azione e scadenza. Il contatore non è una lista dettagliata dei singoli difetti: usare il riscontro e la documentazione della commessa per il dettaglio.

## Permessi

| Azione | Permesso |
| --- | --- |
| Leggere centro, dettaglio ed esportare commesse | `sales_orders.view` |
| Assegnare e avanzare commessa; verificare contratto e documenti | `sales_orders.edit` |
| Creare commessa | `sales_orders.create` (la selezione cliente in UI richiede anche `crm.customers.view`) |
| Stato finanziamento e nulla osta amministrativi | `admin.payments.edit` |
| Verifica tecnica | `surveys.validate` |
| Disponibilità materiali | `logistics.edit` |
| Risorse, collaudo e contatore completamenti | `installation.edit` |
| Leggere, creare, modificare assistenze | `service.view`, `service.create`, `service.edit` rispettivamente |

Le verifiche di reparto richiedono anche la lettura della commessa. I superamministratori mantengono i poteri già previsti. I ruoli ordinari sono cercati esclusivamente nell’azienda dell’utente. La scheda assistenze del centro richiede anche accesso al centro; il modulo assistenze esistente resta disponibile ai ruoli dedicati.

## Assistenze

La prima segnalazione effettiva può essere indicata all’apertura, non in futuro, e non può essere riscritta da PATCH. Per i ticket pregressi si usa `created_at` se manca la data dedicata; un’origine assente è mostrata come dato mancante.

- Rosso: 48 ore continuative.
- Arancione: 15 giorni di calendario.
- Verde: 30 giorni di calendario.
- Attesa cliente/ricambio e pianificazione non fermano il conteggio.
- Se un caso diventa rosso, si conserva il termine precedente quando più vicino; altrimenti scade dopo 48 ore dall’escalation. Le successive letture e modifiche non ricalcolano il termine dalla vecchia apertura.
- Abbassare la priorità non sposta in avanti un termine già assegnato.
- Per risolvere, chiudere o non accogliere occorre un esito scritto. Un ticket risolto può tornare in lavorazione con la transizione prevista; il termine originario resta conservato.

Il precedente sistema di notifiche cliente sugli avanzamenti dei ticket rimane in uso. Le modifiche interne a incarico/priorità/azione non inviano notifiche da questo centro. I test isolano le notifiche e non contattano destinatari.

## Compatibilità API e concorrenza

Le API sono sotto `/api`. `/operations/schema`, `/operations/assignees`, `/operations/orders` e `/operations/orders/{id}` alimentano la schermata. `/service-tickets/options` espone gli stati ammessi.

- `PUT /operations/orders/{id}/plan`: `version`, `owner_id`, `next_action`, `due_at` con fuso orario, `block`, `residuals`.
- `POST /operations/orders/{id}/checks`: `version`, `key`, `satisfied`, `evidence`.
- `PUT /operations/orders/{id}/finance`: `version`, `payment_mode`, `financing_status`, `evidence`.
- PATCH di una commessa gestita e POST al suo `/status` richiedono `expected_version`.
- PATCH ticket richiede `version` e accetta solo i campi esplicitamente previsti. Tenant, stato e origine del termine non sono modificabili da PATCH. Gli stati usano `/status`; il nuovo centro invia anche `expected_version`.

Le scritture confrontano versione letta e versione nel database, incrementano il numero e registrano lo storico nella stessa operazione MongoDB. Un conflitto restituisce 409; ricaricare e rivalutare, senza sovrascrivere ciecamente.

Il vecchio endpoint di avanzamento commessa applica gli stessi controlli. Il rapporto posa non avanza automaticamente una commessa gestita: registrare il rapporto e poi effettuare il passaggio controllato dal centro. Per i record non adottati rimane il comportamento precedente.

## Esportazione e limiti

`GET /operations/export?format=csv|json&q=...&status=...` esporta tutte le commesse autorizzate corrispondenti ai filtri, senza il limite della pagina. CSV separato da punto e virgola, UTF-8 con BOM e protezione delle celle interpretabili come formule. JSON include i campi della commessa e lo storico, senza `tenant_id`.

L’esportazione non è un backup dell’intero gestionale: non include i file binari allegati né le altre collezioni. Conservare database e storage con gli strumenti di backup dell’infrastruttura. L’export richiede autenticazione; salvare il risultato in uno spazio aziendale riservato, mai nel repository pubblico.

Gli indicatori di ritardo/blocco nella schermata sono dichiarati **in pagina**. La ricerca riguarda numero commessa, azione e blocco. Il numero totale riguarda tutti i risultati di ricerca/fase. Il filtro criticità locale non restringe l’export.

## Verifica automatica

Il workflow GitHub `Operational control` esegue i test isolati delle regole/API e la compilazione del frontend. Non usa MongoDB reale, credenziali aziendali, servizi bancari o SMTP. Non distribuisce automaticamente l’applicazione.

Restano da verificare nell’ambiente di staging: dati e ruoli reali, integrazioni con i moduli preesistenti, prestazioni sui volumi aziendali, storage e ripristino. I test di questa modifica non equivalgono a una certificazione completa degli altri moduli.

Verifiche eseguite per questa versione: 26 test di dominio/API passati anche con installazione pulita delle dipendenze di test; compilazione produzione riuscita (avvisi React preesistenti fuori dal nuovo centro); collaudo nel browser con dati sintetici, API reali dei tre router e MongoDB simulato. Nel browser verificati assegnazione/scadenza commessa, blocco e sblocco dopo evidenze, avanzamento di fase, assegnazione e avanzamento assistenza senza spostare il termine. Autenticazione e invio email erano sostituiti nel solo ambiente di collaudo temporaneo.
