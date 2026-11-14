# Collaudo dei passaggi tra reparti

## Obiettivo e stato

Dimostrare che ogni attività arriva alla persona competente, richiede presa in carico ed esito, e lascia uno storico ricostruibile. Un cambio di stato visibile o una prova svolta tutta come superamministratore non sono sufficienti.

La versione di partenza è la proposta GitHub #2, commit `7b99dec8229faa2be2759c160ba06d9b9668d502`. Su questa versione sono passati 37 test isolati e la build frontend. La precedente prova browser ha usato API reali con database e autenticazione di prova: non certifica login, permessi aziendali reali o integrazioni degli altri moduli.

Questa scheda è un protocollo da eseguire: non attesta che il collaudo aziendale sia già avvenuto. I casi e gli utenti sotto sono dati fittizi da predisporre nell'ambiente separato. Nessuna commessa reale va adottata o modificata durante questa prova.

## Preparazione dell'ambiente

- Frontend e backend devono usare la stessa versione della proposta, in un ambiente separato dalla produzione.
- Database e archivio documenti di prova separati; nessuna credenziale bancaria, finanziaria o di invio cliente. Gli invii devono essere disabilitati o instradati esclusivamente a destinatari di collaudo.
- Mostrare chiaramente che si tratta di un ambiente di prova e usare solo dati inventati.
- Creare un cliente `Cliente COLLAUDO` e tre commesse: `TEST-A percorso completo`, `TEST-B blocco e variante`, `TEST-C incarico e scadenza`.
- Predisporre un utente direzione e operatori distinti per commerciale, amministrazione, coordinamento, tecnico, acquisti, magazzino, posa e documentazione. Gli operatori non devono essere superamministratori.
- Ogni operatore necessita di `sales_orders.view` e dei permessi delle attività assegnate, indicati in [OPERATIONS.md](OPERATIONS.md). La direzione necessita anche di `workflow.assign` per regole e riassegnazioni. Non concedere agli operatori tutti i permessi solo per far riuscire il test.
- Configurare i destinatari delle 15 attività in **Centro operativo → Attività dei reparti → Incaricati e tempi dei passaggi automatici**. Usare un obiettivo interno di prova esplicito; i termini sono in ore continuative, non in giorni lavorativi.
- Usare sessioni browser separate per gli operatori. Prima di ogni azione annotare l'utente effettivamente autenticato.

## TEST-A — percorso completo

Per ciascuna riga: il destinatario apre **Solo le mie**, verifica incarico e termine, seleziona **Prendi in carico**, inserisce il riscontro indicato e conclude. Il reparto successivo apre la propria coda e verifica che sia nata una sola attività, ancora da prendere in carico.

| Passo | Chi lavora | Riscontro fittizio da registrare | Destinazione attesa |
| --- | --- | --- | --- |
| 1 | Commerciale | Contratto TEST e allegati, revisione 1 | Amministrazione: nulla osta al rilievo |
| 2 | Amministrazione | Contratto e condizione di pagamento TEST verificati | Coordinamento: pianificazione rilievo |
| 3 | Coordinamento | Appuntamento TEST con data e tecnico | Tecnico: esecuzione rilievo |
| 4 | Tecnico | Misure, foto e fascicolo TEST consegnati | Tecnico: validazione tecnica |
| 5 | Tecnico | Revisione TEST validata, varianti verificate | Amministrazione: copertura ordine |
| 6 | Amministrazione | Copertura TEST e autorizzazione ordine | Acquisti: invio ordine |
| 7 | Acquisti | Ordine TEST, revisione e invio registrati | Acquisti: conferma fornitore |
| 8 | Acquisti | Conferma TEST e data prevista | Magazzino: controllo materiali |
| 9 | Magazzino | Tutte le righe e accessori TEST integri/utilizzabili | Amministrazione: condizioni posa |
| 10 | Amministrazione | Condizioni contrattuali TEST per la posa verificate | Coordinamento: risorse e data posa |
| 11 | Coordinamento | Data, caposquadra, mezzi e accessi TEST confermati | Posa: esecuzione |
| 12 | Posa | Rapporto TEST e riserve, zero completamenti aperti | Posa: collaudo |
| 13 | Posa | Collaudo TEST concluso, zero completamenti | Documentazione: fascicolo finale |
| 14 | Documentazione | Documenti finali TEST completi | Amministrazione: chiusura |
| 15 | Amministrazione | Chiusura amministrativa TEST verificata | Commessa chiusa, nessuna attività aperta |

**Superato se:** nessun passaggio richiede di ricopiare manualmente l'incarico nel reparto successivo; persona e termine sono coerenti con la regola; la presa in carico non è automatica; tutti i riscontri sono nello storico; la commessa chiusa esce dalla coda aperta. Quando cambia reparto, verificare che il precedente incaricato non trovi più la commessa tra le attività correnti di **Solo le mie**.

Concludere un'attività attesta il lavoro: non crea o invia automaticamente ordini, appuntamenti o documenti negli altri moduli. Questi collegamenti richiedono un collaudo separato.

## TEST-B — impedire avanzamenti errati

| Prova | Azione | Esito necessario |
| --- | --- | --- |
| Mancata presa in carico | Provare a concludere prima di prendere in carico | Conclusione non disponibile o rifiutata |
| Persona sbagliata | Aprire la commessa con un operatore diverso dall'incaricato | Può leggere se autorizzato, ma non attestare l'esecuzione |
| Blocco | Prendere in carico e segnalare `Manca allegato TEST` | Blocco visibile; nessuna attività successiva |
| Soluzione | Registrare `Allegato TEST acquisito` e riprendere | Stessa attività ripresa; il blocco precedente resta nello storico |
| Materiale parziale | Al magazzino segnalare `Manca accessorio TEST` | La posa non viene autorizzata dal percorso |
| Rinvio | La direzione rinvia alla stessa fase o a una precedente, con motivo | Nuovo incarico e nuova presa in carico; controlli dipendenti da rifare; storico conservato |
| Variante | Prima della posa, modificare righe o indirizzo della commessa | Riapertura della verifica commerciale; vecchie attestazioni non riutilizzate |
| Variante con blocco | Revisionare una commessa già bloccata | Il blocco non scompare senza registrare la soluzione |
| Completamenti | Concludere la posa dichiarando 2 completamenti aperti | Attività di collaudo ancora sulla commessa; non passare a documentazione finché restano aperti |
| Falsa chiusura | Tentare di chiudere con completamenti pendenti | Rifiuto; nessuna chiusura silenziosa |

Usare documenti e motivi inventati e riconoscibili come TEST. Non eseguire vere varianti contrattuali.

## TEST-C — incarichi, ritardi e conflitti

1. **Riassegnazione:** la direzione cambia l'incaricato a un altro operatore abilitato e scrive il motivo. Il vecchio operatore perde il diritto di lavorare l'attività; il nuovo deve prenderla in carico. Entrambi gli incarichi rimangono ricostruibili.
2. **Destinatario non disponibile:** su dati di prova, verificare il passaggio con una regola mancante o un destinatario non più abilitato. L'attività successiva deve esistere nella coda **Da assegnare, bloccate o scadute**, senza essere attribuita arbitrariamente a qualcuno. Ripristinare poi la configurazione di prova.
3. **Scadenza:** ripianificare l'attività di TEST-C a un orario passato, con motivo TEST. Deve comparire tra le scadute. Non è previsto un invio automatico email/push: si verifica la coda, non una notifica inesistente.
4. **Doppia finestra:** aprire la stessa attività nella stessa versione in due finestre. Dopo una prima modifica, tentare la seconda senza ricaricare. Il sistema deve segnalare il conflitto; non creare due attività successive e non sovrascrivere la prima modifica.
5. **Finanziamento:** su una commessa fittizia registrare una pratica solo approvata. Il nulla osta al rilievo non deve concludersi finché non viene attestata anche la sottoscrizione. La sottoscrizione non deve essere presentata come erogazione.
6. **Storico ed esportazione:** esportare il JSON, conservandolo nello spazio di collaudo, e confrontarlo con lo storico della schermata. Devono risultare autore, data, incarichi prima/dopo, scadenze, riscontri, blocchi e rinvii. Il CSV è una vista operativa, non il backup completo del sistema.

## Registro esiti

Per ogni prova compilare:

| Campo | Contenuto |
| --- | --- |
| Versione e ambiente | Commit, URL del collaudo, data |
| Caso e commessa | TEST-A/B/C, identificativo |
| Utente e reparto | Account effettivamente autenticato |
| Azione | Pulsante/operazione svolta |
| Atteso | Risultato previsto da questa scheda |
| Ottenuto | Risultato osservato e messaggio di errore, se presente |
| Evidenza | Immagine o riferimento alla voce dello storico |
| Esito | Superato / non superato / non eseguito |
| Correzione | Difetto, responsabile, termine e successiva riprova |

Il percorso passa al primo utilizzo controllato solo quando i tre casi sono superati e non restano difetti che perdono attività, permettono avanzamenti indebiti o cancellano tracce. Per i difetti corretti ripetere il caso interessato e i passaggi dipendenti.

La prova successiva, distinta da questi casi, riguarda una commessa reale selezionata nell'ambiente aziendale, con ruoli verificati e backup: non è autorizzata automaticamente dal successo della simulazione. Lead, firma contratto, apertura automatica commessa, integrazioni dei moduli e percorso automatico delle assistenze restano una lista separata di verifiche e sviluppi.

## Riesecuzione tecnica isolata

Dalla radice del repository, con le dipendenze di `backend/requirements-operations-test.txt` installate:

```bash
PYTHONPATH=backend python -m pytest backend/tests/test_operational_control.py -q
```

Il comando usa un database simulato e non contatta i clienti. Non sostituisce le prove con gli account reali di collaudo sopra descritte.
