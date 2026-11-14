# Centro operativo — attività, consegne e verifiche

## Il percorso operativo

Il centro `/operations` usa le commesse già presenti in `sales_orders`. Ogni commessa adottata ha **una sola attività corrente**, con reparto, persona, scadenza e stato. Concludere un’attività registra l’esito e genera quella successiva nella stessa scrittura atomica: un passaggio non può chiudere il lavoro precedente senza conservarne la destinazione.

| Attività | Reparto destinatario | Permesso per eseguirla |
| --- | --- | --- |
| Contratto e allegati | Commerciale | `sales_orders.edit` |
| Nulla osta al rilievo | Amministrazione | `admin.payments.edit` |
| Pianificazione rilievo | Coordinamento | `surveys.assign` |
| Rilievo e fascicolo | Tecnico | `surveys.measure` |
| Verifica tecnica e varianti | Tecnico | `surveys.validate` |
| Copertura dell’ordine | Amministrazione | `admin.payments.edit` |
| Invio ordine con revisione | Acquisti | `purchase_orders.edit` |
| Conferma fornitore e data | Acquisti | `purchase_orders.edit` |
| Completezza e integrità materiali | Magazzino | `logistics.edit` |
| Condizioni per la posa | Amministrazione | `admin.payments.edit` |
| Data, caposquadra, mezzi e accessi | Coordinamento | `installation.edit` |
| Posa, rapporto e riserve | Posa | `installation.edit` |
| Collaudo e completamenti | Posa | `installation.edit` |
| Documenti finali | Documentazione | `sales_orders.edit` |
| Chiusura amministrativa | Amministrazione | `admin.payments.edit` |

Le verifiche commerciali, tecniche e amministrative sono cumulative. La fase sintetica della commessa è aggiornata dalla procedura e non sostituisce l’attività dettagliata. Il percorso è quello di fornitura e posa: non simula le lavorazioni di una fabbrica.

## Avvio e lavoro quotidiano

1. Distribuire frontend e backend della stessa versione in staging, con database separato e invii esterni disattivati o reindirizzati al collaudo.
2. Verificare i ruoli reali. Tutti gli operatori del centro devono avere `sales_orders.view`, oltre al permesso della propria attività. Le configurazioni e le riassegnazioni richiedono anche `workflow.assign`. I ruoli predefiniti del gestionale potrebbero non avere ancora questi permessi: il codice non li amplia automaticamente.
3. In **Attività dei reparti → Incaricati e tempi dei passaggi automatici**, configurare il destinatario di ogni attività e il suo obiettivo interno in ore continuative. La scelta include solo utenti attivi della stessa azienda con i permessi richiesti. I tempi non sono scadenze contrattuali, turni o giorni lavorativi: impostare i termini effettivi sulla specifica attività quando necessario.
4. Le nuove commesse nascono già con la prima attività. Per quelle pregresse, aprire la scheda e usare **Avvia procedura dal fascicolo**: riparte la verifica commerciale, le attestazioni precedenti vengono revocate e lo storico rimane. Nessuna attività pregressa viene dichiarata eseguita automaticamente.
5. L’incaricato apre **Solo le mie**, prende in carico, esegue il lavoro e inserisce un esito con riferimento al documento e alla revisione. **Concludi e consegna al reparto successivo** chiude la sua attività e assegna la successiva secondo la configurazione. Anche un amministratore deve essere l’incaricato nominativo per attestare l’esecuzione.
6. Se manca la configurazione o il destinatario non è più abilitato, l’attività successiva viene comunque creata e compare tra quelle da assegnare. Non è possibile prenderla in carico senza persona e termine. La direzione usa il filtro **Da assegnare, bloccate o scadute**, valido sull’intero insieme dei risultati, e assegna un utente competente.

Una modifica alla regola di assegnazione riguarda solo i futuri incarichi: non sposta scadenze o responsabilità già assegnate. Per il lavoro aperto usare **Assegna, ripianifica o rinvia**, indicando il motivo. Un cambio di incaricato richiede una nuova presa in carico. Un blocco aperto resta tale anche dopo la riassegnazione, l’adozione di una vecchia commessa o una revisione: serve registrarne esplicitamente la soluzione.

## Blocchi, varianti e completamenti

- **Segnala blocco** conserva motivo, responsabile e termine. **Registra soluzione e riprendi** richiede un riscontro. Il blocco impedisce il completamento dell’attività; altre commesse e moduli rimangono accessibili.
- **Rinvia** genera una nuova attività nella stessa fase o in una precedente, revoca i controlli dipendenti e conserva quelli precedenti. Non permette salti in avanti.
- Una modifica a righe o indirizzo riapre il fascicolo commerciale. Una variazione delle condizioni finanziarie, quando il percorso ha già superato il primo nulla osta, lo rinvia in amministrazione e revoca le verifiche successive. È una scelta prudenziale esplicita: va rivalutata con i dati reali se provoca lavoro ridondante.
- Approvazione, firma ed erogazione restano distinte. Il finanziamento deve essere almeno sottoscritto per superare il nulla osta al rilievo; gli altri nulla osta richiedono comunque la verifica competente.
- Il rapporto posa può lasciare un numero di completamenti aperti. Il collaudo non consegna il lavoro alla documentazione finché questi non sono risolti. Restano completamenti della commessa, non nuove assistenze.
- Le commesse adottate non si eliminano: si annullano con un motivo. Chiuse o annullate non sono modificabili dal centro.

## Storico e consistenza

Lo storico registra autore e data, attività e responsabili prima/dopo, scadenze, presa in carico, esito, blocco, soluzione, riassegnazione e rinvio. Due esecuzioni della stessa fase restano eventi distinti. Non sono deduplicate per il solo nome dello stato. Gli esiti sono attestazioni degli operatori: il software non certifica il contenuto di un documento citato.

Attività corrente, aggiornamento della commessa e storico sono scritti con confronto della versione nella stessa operazione MongoDB. Due completamenti concorrenti producono una sola attività successiva; il secondo riceve 409. Ricaricare e rivalutare senza sovrascrivere. Nessuna transazione su più collezioni è necessaria per la consegna.

Le vecchie API di piano, controllo e cambio stato non possono saltare il percorso sulle commesse adottate. Il rapporto posa non le avanza automaticamente. I record pregressi non adottati mantengono il comportamento precedente, con i controlli operativi precedenti se abilitati.

## API

Tutti i percorsi sono sotto `/api` e richiedono autenticazione e isolamento per azienda.

- `GET /operations/process/schema`: fasi, reparti, candidati abilitati, regole e permessi del chiamante.
- `GET /operations/process/inbox`: filtri `area`, `mine`, `attention`, paginazione `skip`/`limit` e totale.
- `PUT /operations/process/routes/{step}`: `version`, `owner_id`, `target_hours`; configurazione con concorrenza e storico separato.
- `POST /operations/process/orders/{id}/start`: `version`, avvio controllato di una commessa pregressa.
- `PUT /operations/process/orders/{id}/assignment`: `version`, `owner_id`, `due_at` con fuso orario, `reason`.
- `POST /operations/process/orders/{id}/action`: `version`, `action` (`accept`, `complete`, `block`, `resume`, `return`, `cancel`), `evidence`; `target_step` per il rinvio; `residuals` alla conclusione di posa/collaudo.
- `PUT /operations/orders/{id}/finance`: `version`, `payment_mode`, `financing_status`, `evidence`.
- `GET /operations/orders`, `/operations/orders/{id}` e `/operations/export?format=csv|json`: consultazione ed esportazione.

Il JSON comprende lo storico. Il CSV include tutte le commesse corrispondenti a ricerca e fase, con separatore `;`, BOM UTF-8 e protezione delle celle interpretabili come formule. Non sono backup completi: file allegati e altre collezioni non sono inclusi. Gli indicatori e il filtro criticità nella scheda **Commesse** restano locali alla pagina; il filtro della coda **Attività dei reparti** è invece applicato dal server.

## Assistenze e confini attuali

Il centro mantiene la gestione assistenze già introdotta: prima segnalazione conservata, priorità rosso 48 ore continuative/arancione 15 giorni/verde 30 giorni, assegnazione e chiusura motivata. Attese e declassamenti non prorogano il termine. Una nuova urgenza rossa usa 48 ore dall’escalation o il precedente termine se più vicino. Gli esiti cliente continuano a usare le notifiche del modulo preesistente.

Il nuovo passaggio automatico **copre le attività delle commesse dal fascicolo commerciale alla chiusura**. Non collega ancora automaticamente qualificazione lead, firma contratto e apertura commessa; non trasforma tutti i ticket assistenza in questa sequenza. I collegamenti a rilievi, acquisti, produzione e posa restano quelli del gestionale: concludere un’attività non crea né invia automaticamente documenti nei rispettivi moduli. La regola richiede il riscontro dell’operatore, non una semplice modifica allo stato esterno.

La coda è consultabile nel centro e si aggiorna dopo le operazioni o con **Aggiorna**. Non sono stati introdotti notifiche email/push, escalation pianificate, calendario di turni, un motore di attività parallele per singola riga, né integrazioni Drive, contabilità, banca o finanziaria. Il blocco riguarda il percorso principale della commessa; non modella dipendenze parziali tra righe. Questi limiti non vanno presentati come conformità completa di tutti i moduli.

## Collaudo

Il workflow GitHub esegue i test isolati e la compilazione del frontend; non distribuisce l’applicazione. I test coprono il ciclo dei 15 passaggi, permessi del reparto e dell’incaricato, isolamento aziendale, configurazioni mancanti/inattive, esiti, blocchi, rinvii, concorrenza, varianti, finanziamenti, completamenti, esportazione e regressioni assistenza.

Verificati localmente 37 test passati con dipendenze isolate e build produzione riuscita, con soli avvisi React preesistenti. Il collaudo browser usa dati sintetici, API reali e MongoDB simulato, con autenticazione e invii esterni sostituiti nel solo ambiente temporaneo. Verificati avvio, presa in carico, passaggio commerciale → amministrazione, blocco, soluzione e storico leggibile.

Prima dell’uso aziendale rimangono da verificare utenti e permessi reali, integrazioni dei moduli, prestazioni sui volumi effettivi, backup/ripristino e un ciclo completo in staging. Non è una certificazione dell’intero gestionale. Non inserire dati reali o esportazioni nel repository pubblico.
