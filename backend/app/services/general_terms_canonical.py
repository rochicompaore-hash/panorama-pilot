"""CANONICAL GENERAL TERMS — ONE CONTRACT SOURCE (PO msg 782).

Trascrizione integrale del contratto ufficiale Infissi Express
"modulo proposta d'acquisto corretto (1).pdf" (Enierhia S.r.l.).
Questo modulo è la SOURCE OF TRUTH: il contratto generato deve usare questo testo IDENTICO,
il preventivo ne mostra solo una sintesi informativa (general_terms.py).
NESSUNA riscrittura/rinumerazione automatica: modifiche solo tramite nuova versione approvata dal PO.
"""
from __future__ import annotations
import hashlib
from typing import Any, Dict, List, Optional

GENERAL_TERMS_VERSION = "GT-INFISSIEXPRESS-2026-09-V1"
EFFECTIVE_FROM = "2026-09-01"
SOURCE_DOCUMENT = "modulo proposta d'acquisto corretto (1).pdf"

SUPPLIER_HEADER = (
    "ENIERHIA SRL con sede legale in Via privata del Gonfalone 3 Milano (MI) 20123 e avente sede in Missaglia (LC) "
    "via Giuseppe Garibaldi, n. 64, iscritta al Registro Imprese di MILANO al n. MI-2701654, C.F. e partita IVA IT13060750152, "
    "in persona del proprio legale rappresentante pro tempore, di seguito per brevità, \"FORNITORE\" da una parte"
)
COMMITTENTE_HEADER = (
    "di seguito per brevità, \"COMMITTENTE\", il FORNITORE dispone di esperienza, capacità tecniche, attrezzature necessarie e personale idoneo "
    "per eseguire la fornitura oggetto del presente proposta di acquisto. Tutto ciò premesso si conviene e si stipula quanto segue:"
)

# Modulo pag. 2 — dichiarazioni del sottoscrittore
CUSTOMER_DECLARATIONS: List[str] = [
    "Di aver ricevuto preventivo dettagliato e accettarne il contenuto",
    "Di essere consapevole che i prodotti sono realizzati su misura e per tanto non è previsto il diritto di recesso",
    "Di essere a conoscenza delle condizioni generali di e di averle lette e accettate integralmente",
]

# Modulo pag. 3 — modalità di pagamento (testo ufficiale)
PAYMENT_INSTRUCTIONS = (
    "I pagamenti dovranno essere effettuati tramite Bonifico Bancario Per detrazione fiscale avente legge legge 296/2006, intestato a:\n"
    "Enerhia Srl\nIBAN: IT 46 V 03069 51550 10000012217\nCausale: Acconto/Saldo ordine serramenti\n"
    "In caso di detrazione fiscale, utilizzare il bonifico parlante specifico per bonus edilizi.\n"
    "In caso di finanziamento, fornire copia della Dichiarazione dei Redditi e altri documenti richiesti."
)

# Modulo pag. 3 — consenso GDPR
GDPR_CONSENT = {
    "title": "CONSENSO AL TRATTAMENTO DEI DATI PERSONALI REG. UE 2016/679",
    "text": (
        "In ottemperanza all'art. 13 D.Lgs. 196/03 e del Regolamento Europeo 2016/679 (GDPR), il Cliente dichiara di aver ricevuto e compreso "
        "l'informativa fornita da ENERHIA SRL, in qualità di Titolare del trattamento, e di prestare liberamente il proprio consenso per il "
        "trattamento dei dati personali con le seguenti finalità:\n"
        "1) Finalità istituzionali e contrattuali: esecuzione del contratto; adempimenti contabili, fiscali, amministrativi; attività "
        "tecnico-commerciali e post-vendita; erogazione di garanzie e servizi.\n"
        "2) Comunicazioni informative e commerciali: utilizzo di email, telefono, SMS, posta cartacea per informazioni su prodotti, offerte, "
        "attività promozionali relative a serramenti e soluzioni integrate."
    ),
    "specific_consents_intro": "Consenso specifico per le seguenti finalità (barrare la casella):",
    "specific_consents": [
        "Fotografie dell'impianto o dell'intervento - Autorizza ENERHIA SRL ad acquisire e utilizzare immagini dell'intervento/installazione per documentazione interna o finalità divulgative (es. sito web, brochure)",
        "Finanziamento Qualora si scelga di pagare tramite finanziamento, autorizza ENERHIA SRL a trasmettere i dati personali alle finanziarie partner per avviare la pratica e gestire l'erogazione",
        "Monitoraggio impianto / serramenti Autorizza ENERHIA SRL ad accedere ai portali (Enel. E-Distribuzione, ecc.) per attivazione e verifica corretta esecuzione",
        "Accesso agli atti - Autorizza ENERHIA SRL ad accedere presso enti pubblici (es. Catasto, Comune) per visionare atti utili al completamento dell'intervento",
    ],
}

ARTICLES: List[Dict[str, str]] = [
    {"code": "ART_1", "number": "1", "title": "PREMESSE",
     "text": "Le premesse e gli allegati espressamente richiamati nelle clausole che seguono formano parte integrante del presente Contratto."},
    {"code": "ART_2", "number": "2", "title": "OGGETTO DELLA PROPOSTA DI ACQUISTO",
     "text": "Il FORNITORE si obbliga ad eseguire la fornitura con posa in opera di serramenti su misura presso il cantiere indicato nel Modulo di Proposta d'Acquisto, in conformità alle specifiche di cui al preventivo accettato e sottoscritto dal COMMITTENTE (Allegato A)."},
    {"code": "ART_2_BIS", "number": "2-bis", "title": "COMPRENSIONE DEL PRODOTTO E CONFERMA TECNICA",
     "text": "Il COMMITTENTE dichiara di aver esaminato, compreso appieno e accettato le caratteristiche tecniche, dimensionali, prestazionali ed estetiche dei prodotti oggetto della fornitura, come illustrate in sede di preventivazione e riportate nell'Allegato A.\n"
             "Il COMMITTENTE dichiara altresì di essere a conoscenza che i serramenti su misura sono realizzati esclusivamente sulla base delle specifiche dallo stesso approvate, senza possibilità di modifica una volta avviata la produzione, fatte salve le ipotesi disciplinate all'articolo 3 del presente Contratto.\n"
             "La firma del presente Contratto costituisce accettazione definitiva e consapevole del prodotto nelle sue caratteristiche tecniche e configurazione."},
    {"code": "ART_3", "number": "3", "title": "ORDINI",
     "text": "Gli ordini si intendono accettati esclusivamente con la firma del preventivo di cui all'Allegato A. Per ragioni tecnico-produttive non sarà possibile accettare annullamenti o modifiche dell'ordine in corso.\n"
             "Nel caso in cui il COMMITTENTE ritenesse indispensabile effettuare variazioni, il FORNITORE si riserva di valutarne la fattibilità. Qualora le variazioni fossero accettate, il COMMITTENTE si farà carico delle eventuali variazioni di corrispettivo e verrà redatto un nuovo preventivo da sottoscriversi da entrambe le parti.\n"
             "La FORNITRICE si riserva espressamente il diritto, per esigenze produttive, logistiche o di approvvigionamento, di modificare o sostituire, a propria discrezione, il fornitore, il produttore o il sistema di profili originariamente indicato, fermo restando il mantenimento delle medesime caratteristiche tecniche, prestazionali ed energetiche previste contrattualmente.\n"
             "Eventuali sostituzioni potranno avvenire esclusivamente mediante l'impiego di profili, sistemi o componenti aventi caratteristiche tecniche equivalenti o superiori, garantendo in ogni caso il mantenimento di tutti i parametri prestazionali originariamente previsti, inclusi a titolo esemplificativo:\n"
             "la trasmittanza termica (Uw);\nla composizione e la tipologia dei vetri;\nil numero e la tipologia delle guarnizioni;\nle prestazioni termiche e acustiche;\nla qualità strutturale e funzionale del serramento;\nla conformità alle normative vigenti;\nle medesime condizioni di garanzia legale e commerciale.\n"
             "Tali variazioni non costituiscono modifica sostanziale della fornitura né potranno costituire motivo di contestazione, risoluzione del contratto o richiesta di risarcimento da parte del COMMITTENTE, qualora siano rispettate le caratteristiche tecniche e prestazionali concordate.\n"
             "Resta inteso che la modifica e/o l'annullamento del preventivo comporta l'addebito dei costi che il FORNITORE avrà sostenuto fino a quel momento."},
    {"code": "ART_3_BIS", "number": "3-bis", "title": "VARIAZIONI DI COLORE, TIPOLOGIA E SERVIZI NON PREVISTI",
     "text": "Con la sottoscrizione del presente Contratto, il FORNITORE avvia immediatamente il processo di approvvigionamento dei materiali necessari alla produzione, con particolare riferimento alle barre in PVC e/o alluminio, ai profili, ai vetri e alle pellicole di finitura nei colori e nelle tipologie specificate nel preventivo sottoscritto (Allegato A). Tale processo comporta l'impegno contrattuale con i fornitori di materia prima e l'allocazione delle risorse produttive sin dalla data di decorrenza dei termini contrattuali.\n"
             "Qualsiasi richiesta di variazione rispetto a quanto contrattualizzato – a titolo esemplificativo e non esaustivo: cambio di colore o finitura superficiale, modifica della tipologia di apertura, variazione del tipo di vetraggio, cambio della posizione di sotto-luce o sopra-luce, variazioni dimensionali o di trattamento – deve essere formulata per iscritto dal COMMITTENTE e sarà soggetta a preventiva valutazione da parte della FORNITRICE.\n"
             "La FORNITRICE si riserva la facoltà insindacabile di accettare o rifiutare qualsiasi richiesta di variazione. In caso di accettazione, la FORNITRICE procederà alla redazione di un nuovo preventivo che quantificherà i costi aggiuntivi derivanti dalla modifica richiesta. Ogni variazione è soggetta a un costo aggiuntivo: nessuna variazione, di qualsiasi natura essa sia, potrà essere eseguita a titolo gratuito. Il COMMITTENTE dovrà approvare e sottoscrivere il nuovo preventivo prima che la FORNITRICE proceda con le modifiche richieste.\n"
             "In nessun caso tali variazioni daranno diritto al COMMITTENTE di recedere dal presente Contratto, sospendere i pagamenti dovuti, o ottenere una chiusura bonaria dello stesso a condizioni diverse da quelle pattuite. Il COMMITTENTE riconosce espressamente che la richiesta di variazione non costituisce inadempimento del FORNITORE e non giustifica contestazioni sul corrispettivo originariamente concordato, né comporta la sospensione dei termini di pagamento già scaduti o in scadenza."},
    {"code": "ART_3_TER", "number": "3-ter", "title": "ACCESSORI E COMPLEMENTI NON INCLUSI NELLA FORNITURA",
     "text": "Ove non espressamente indicato nel preventivo (Allegato A), sono esclusi dalla fornitura tutti gli accessori, complementi, raccorderie, sistemi di fissaggio, cassonetti, zanzariere, persiane, scuri, tapparelle, avvolgibili e ogni altro elemento non riportato nel dettaglio dell'offerta.\n"
             "Il COMMITTENTE prende atto che la fornitura si intende limitata ai prodotti esplicitamente elencati nel preventivo sottoscritto. Eventuali elementi aggiuntivi richiesti in fase di installazione o a seguito del rilievo tecnico definitivo saranno oggetto di preventivo separato, previo accordo scritto tra le parti."},
    {"code": "ART_3_QUATER", "number": "3-quater", "title": "RILIEVO TECNICO DEFINITIVO E RELATIVO CORRISPETTIVO",
     "text": "Il rilievo tecnico definitivo è un servizio professionale specializzato e come tale soggetto a corrispettivo. Il costo del rilievo è fissato in Euro 80,00 (ottanta/00) per singolo pezzo/vano rilevato, salvo diversa pattuizione scritta indicata nel preventivo.\n"
             "Qualora il COMMITTENTE richieda, in sede di rilievo tecnico definitivo, il rilevamento di vani o prodotti non oggetto della fornitura (a titolo esemplificativo: misurazioni aggiuntive, sopralluoghi tecnici per altri ambienti, verifica di prodotti non inclusi nel preventivo), il relativo costo sarà conteggiato separatamente e addebitato al COMMITTENTE, a prescindere dall'eventuale successiva conversione in ordine.\n"
             "I termini di consegna di cui all'articolo 12 decorrono esclusivamente dalla data di completamento del rilievo tecnico definitivo e dall'avvenuto versamento dell'acconto concordato."},
    {"code": "ART_4", "number": "4", "title": "POSA IN OPERA E SUBAPPALTO",
     "text": "La posa in opera della fornitura sarà eseguita con materiali, metodi e costi indicati nel preventivo di cui all'Allegato A. La selezione dei modelli e dei colori del serramento è effettuata dal COMMITTENTE, il quale è ritenuto responsabile in via esclusiva della predetta scelta.\n"
             "Sono in ogni caso escluse dal corrispettivo della posa in opera lo smaltimento, eventuali interventi murari o elettrici e servizi accessori alla fornitura, che restano a carico esclusivo del COMMITTENTE, salvo diversa previsione nel preventivo di cui all'Allegato A.\n"
             "Nel caso in cui la posa non possa essere effettuata a causa di muffa, muro ammalorato o per ogni altra causa imputabile al COMMITTENTE, l'onere del ripristino e della riparazione sarà posto a carico del COMMITTENTE.\n"
             "Per la posa in opera, il FORNITORE è sin d'ora autorizzato dal COMMITTENTE ad avvalersi di subappaltatori, i quali agiscono sotto la completa responsabilità del FORNITORE."},
    {"code": "ART_4_BIS", "number": "4-bis", "title": "DOCUMENTAZIONE FOTOGRAFICA PRE-INSTALLAZIONE",
     "text": "Prima dell'avvio delle attività di posa, il FORNITORE o il suo incaricato procederà alla documentazione fotografica dello stato preesistente delle aree di intervento (pavimenti, muri, infissi esistenti, vani, contorni).\n"
             "Tale documentazione costituirà prova inconfutabile dello stato dei luoghi anteriore all'installazione e sarà opponibile a qualsiasi contestazione relativa a presunte lesioni, danni o deterioramenti che il COMMITTENTE intenda attribuire all'attività del FORNITORE.\n"
             "Il COMMITTENTE prende atto che, in assenza di contestazione documentata e firmata al momento del sopralluogo fotografico, non potrà successivamente imputare al FORNITORE danni che risultino preesistenti alla data dell'intervento."},
    {"code": "ART_5", "number": "5", "title": "CORRISPETTIVO",
     "text": "Il corrispettivo della fornitura è concordato nella sezione \"3. PREZZI E SERVIZI\" del preventivo (Allegato A). I prezzi resteranno fissi ed invariabili per tutta la durata del presente rapporto contrattuale.\n"
             "Resta espressamente escluso dal corrispettivo pattuito il costo dell'asseverazione, nonché ogni ulteriore onere, prestazione o intervento non preventivabile sulla base delle informazioni rilevate in fase di preventivazione preliminare.\n"
             "Il corrispettivo è determinato sulla base dei dati dimensionali, tecnici e strutturali forniti dal COMMITTENTE e/o rilevati in via preliminare. Qualora in sede di rilievo tecnico definitivo emergano difformità, la FORNITRICE si riserva il diritto di rideterminare il corrispettivo, previa comunicazione al COMMITTENTE. In tal caso, l'esecuzione della fornitura resterà subordinata all'accettazione formale del nuovo corrispettivo da parte del COMMITTENTE."},
    {"code": "ART_5_BIS", "number": "5-bis", "title": "COMUNICAZIONI TECNICHE E SILENZIO-ASSENSO",
     "text": "Qualsiasi comunicazione tecnica, proposta di variante, richiesta di conferma o notifica operativa inviata dal FORNITORE al COMMITTENTE a mezzo PEC o e-mail si intenderà tacitamente accettata qualora il COMMITTENTE non risponda per iscritto entro 5 (cinque) giorni lavorativi dal ricevimento.\n"
             "Il decorso di tale termine senza risposta scritta del COMMITTENTE equivale a piena e incondizionata accettazione del contenuto della comunicazione, senza possibilità di successiva contestazione in merito."},
    {"code": "ART_6", "number": "6", "title": "PAGAMENTO",
     "text": "Il pagamento del corrispettivo avverrà con le modalità sottoscritte dal cliente nella sezione 4 del Modulo di Proposta d'Acquisto, secondo le seguenti scadenze: acconto nella misura indicata nel preventivo (Allegato A), da versarsi contestualmente alla sottoscrizione del presente Contratto quale condizione necessaria per l'avvio della produzione; saldo dovuto ad avviso di merce pronta.\n"
             "Pre-autorizzazione POS in fase di stipula. In sede di sottoscrizione del presente Contratto, la FORNITRICE potrà richiedere al COMMITTENTE l'autorizzazione di un importo a titolo di pre-autorizzazione tramite terminale POS elettronico. Tale pre-autorizzazione non costituisce addebito definitivo, bensì una temporanea indisponibilità della somma a garanzia della serietà dell'impegno contrattuale assunto. L'importo pre-autorizzato verrà integralmente sbloccato e restituito al COMMITTENTE non appena quest'ultimo provveda, in alternativa, all'effettivo versamento dell'acconto mediante bonifico bancario ovvero alla finalizzazione del finanziamento con l'istituto partner. Il COMMITTENTE prende atto e accetta espressamente tale modalità operativa, riconoscendone la finalità di garanzia e non di pagamento anticipato.\n"
             "A seguito della comunicazione ufficiale di merce pronta trasmessa dalla FORNITRICE a mezzo PEC o e-mail, il COMMITTENTE è tenuto a disporre il pagamento del saldo residuo entro e non oltre 7 (sette) giorni solari dal ricevimento di tale comunicazione. Il saldo deve essere effettivamente accreditato sul conto della FORNITRICE entro tale termine.\n"
             "La consegna e l'installazione dei serramenti sono condizionate all'avvenuto e comprovato versamento integrale del saldo dovuto. Il FORNITORE si riserva di sospendere o rinviare la data di posa in caso di mancato pagamento del saldo nei termini previsti, senza che ciò costituisca inadempimento contrattuale né dia luogo a richieste di indennizzo, risarcimento o compensazione da parte del COMMITTENTE.\n"
             "Qualsiasi ritardo nella data di posa e di installazione, conseguente al mancato o tardivo versamento del saldo da parte del COMMITTENTE entro i 7 giorni dall'avviso di merce pronta, è imputabile esclusivamente al COMMITTENTE. In tal caso il COMMITTENTE non potrà avanzare alcuna pretesa, richiesta di indennizzo, riduzione del corrispettivo o contestazione per il ritardo nella posa. La FORNITRICE potrà altresì applicare la penale di giacenza di Euro 50,00 (cinquanta/00) per ogni giorno di ritardo nel pagamento, a decorrere dall'ottavo giorno dall'avviso di merce pronta.\n"
             "In caso di ritardato pagamento rispetto ai termini sopra indicati, sulle somme dovute e non pagate decorreranno automaticamente gli interessi di mora nella misura fissata dal D.Lgs. n. 231/2002, a partire dall'ottavo giorno dall'avviso di merce pronta."},
    {"code": "ART_7", "number": "7", "title": "CLAUSOLA RISOLUTIVA ESPRESSA",
     "text": "Ai sensi dell'art. 1456 c.c., il presente Contratto si intende risolto di diritto, previa comunicazione scritta del FORNITORE inviata a mezzo PEC o raccomandata A/R, al verificarsi di uno dei seguenti inadempimenti da parte del COMMITTENTE:\n"
             "mancato pagamento dell'acconto nei termini pattuiti;\nmancato pagamento del saldo entro 7 (sette) giorni solari dall'avviso di merce pronta;\nimpossibilità reiterata di accesso al cantiere per cause imputabili al COMMITTENTE per oltre 15 (quindici) giorni solari.\n"
             "In caso di risoluzione per inadempimento del COMMITTENTE, quest'ultimo sarà tenuto al rimborso integrale di tutti i costi sostenuti dalla FORNITRICE fino alla data di risoluzione, nonché al pagamento di una penale pari al 20% (venti per cento) dell'importo contrattuale totale, a titolo di risarcimento forfettario del danno, fatta salva la prova di un danno maggiore."},
    {"code": "ART_8", "number": "8", "title": "SCONTO IN FATTURA",
     "text": "Si pattuise tra le parti la non applicazione dello \"sconto in fattura\" se non espressamente indicato nel preventivo di cui all'Allegato A."},
    {"code": "ART_9", "number": "9", "title": "SOLVE ET REPETE (paga e poi chiedi)",
     "text": "In nessun caso il COMMITTENTE potrà rifiutare o ritardare il pagamento della merce. Eventuali contestazioni relative alla merce non autorizzano il COMMITTENTE a sospendere il pagamento delle fatture, anche se si tratta di ordine solo parzialmente eseguito. L'eventuale reclamo dovrà essere elevato esclusivamente dopo il pagamento integrale delle fatture emesse."},
    {"code": "ART_10", "number": "10", "title": "TRASPORTO, CONSEGNA, MONTAGGIO E POSA",
     "text": "Il trasporto, la consegna, il montaggio di infissi e serramenti e lo smontaggio di vecchi infissi sono compresi nel corrispettivo pattuito all'articolo 5 esclusivamente ove espressamente indicato nel preventivo di cui all'Allegato A. In assenza di tale indicazione, tali servizi si intendono esclusi dal corrispettivo e saranno oggetto di preventivazione separata, concordata per iscritto tra le parti prima dell'esecuzione. Ove inclusi, anche il costo degli imballi è compreso nel corrispettivo.\n"
             "Le consegne avverranno presso il cantiere o altro luogo indicato dal COMMITTENTE. Dal momento della consegna il COMMITTENTE acquisisce la proprietà della merce e da tale data decorre la garanzia convenzionale del FORNITORE in relazione a quanto oggetto della fornitura.\n"
             "Il COMMITTENTE si assume ogni e qualsiasi responsabilità per danneggiamenti, furti o quant'altro, non imputabile al FORNITORE, dovesse verificarsi successivamente alla consegna della fornitura presso il cantiere o presso altro luogo indicato dal COMMITTENTE. Eventuali ritardi rispetto ai tempi di consegna concordati, dovuti alla necessità di sostituire quanto sottratto o danneggiato successivamente alla consegna, non potranno in alcun caso essere addebitati al FORNITORE.\n"
             "Una volta eseguiti gli interventi di montaggio e/o posa, il FORNITORE effettuerà il collaudo finale e provvederà alla redazione del relativo verbale in contraddittorio con il COMMITTENTE, che dovrà sottoscriverlo per accettazione."},
    {"code": "ART_11", "number": "11", "title": "ONERI A CARICO DEL COMMITTENTE",
     "text": "Sono a carico del COMMITTENTE i seguenti oneri:\n"
             "La messa a disposizione di documenti, informazioni e quant'altro necessario per l'esecuzione della fornitura, per l'eventuale applicazione dell'IVA agevolata e dello sconto in fattura.\n"
             "La messa a disposizione delle aree di lavoro presso il cantiere, libere da impedimenti e intralci (evitare la presenza di bambini, persone non autosufficienti e animali domestici).\n"
             "L'adeguata protezione di pavimentazioni e arredi già esistenti. Il FORNITORE non potrà essere ritenuto responsabile per danni alle pavimentazioni qualora il COMMITTENTE non abbia predisposto tale protezione né ne abbia espressamente fatto richiesta al FORNITORE.\n"
             "L'adeguata protezione degli arredi e di quant'altro oggetto della fornitura nel caso sul cantiere sia all'opera personale di altri fornitori."},
    {"code": "ART_11_BIS", "number": "11-bis", "title": "INDISPONIBILITÀ DEL CANTIERE E PENALE",
     "text": "Qualora il cantiere non sia accessibile o disponibile alla data concordata per cause imputabili al COMMITTENTE (a titolo esemplificativo: lavori di terzi non ultimati, assenza del committente o suo delegato, mancata sgombero di arredi, diniego di accesso), sarà applicata una penale di Euro 50,00 (cinquanta/00) per ogni giorno solare di rinvio, oltre al rimborso documentato dei costi di trasferta e manodopera già mobilizzati.\n"
             "Il COMMITTENTE riconosce sin d'ora che tale penale è equa e proporzionata rispetto all'organizzazione produttiva e logistica del FORNITORE."},
    {"code": "ART_12", "number": "12", "title": "TERMINI DI CONSEGNA",
     "text": "I termini di consegna decorrono esclusivamente dalla data di completamento del rilievo tecnico definitivo e dall'avvenuto versamento dell'acconto concordato, entrambi necessari ai fini della conferma esecutiva dell'ordine.\n"
             "Per i prodotti standard in PVC e alluminio (finestre e portefinestre a una o due ante, prive di centine, sagomature o angoli diversi da 90°) e per le colorazioni standard (bianco in massa, avorio in massa, rovere dorato, noce con finitura identica interno/esterno), i tempi di consegna sono fissati indicativamente in 90 (novanta) giorni.\n"
             "Per prodotti bicolore, fuori standard, con finiture speciali, sagomature particolari, angoli non ortogonali o colorazioni speciali, i tempi saranno superiori a 90 giorni.\n"
             "Per serramenti in legno o legno-alluminio, il termine indicativo è 120 (centoventi) giorni.\n"
             "Tutti i termini di produzione e consegna si intendono meramente indicativi e non perentori, in quanto subordinati a fattori tecnici, produttivi e logistici. I termini di consegna non costituiscono termine essenziale ai sensi dell'art. 1457 c.c. e non potranno determinare la risoluzione automatica del contratto né dar luogo a richieste di risarcimento, salvo dolo o colpa grave della FORNITRICE.\n"
             "Qualora la consegna o l'installazione non possono essere eseguite per cause imputabili al COMMITTENTE, i materiali potranno essere posti in giacenza e il COMMITTENTE sarà tenuto al pagamento di Euro 50,00 (cinquanta/00) per ogni giorno solare di giacenza.\n"
             "Proposta di data di montaggio e rispetto delle tempistiche contrattuali. Una volta avvenuto il pagamento integrale del saldo, la FORNITRICE provvederà a comunicare al COMMITTENTE una o più date disponibili per l'esecuzione della posa. Qualora il COMMITTENTE non sia disponibile nelle date proposte dalla FORNITRICE, le tempistiche contrattuali di consegna e installazione si intendono comunque rispettate dalla FORNITRICE a tutti gli effetti contrattuali e di legge. In tale ipotesi, il ritardo nell'esecuzione della posa è imputabile esclusivamente al COMMITTENTE e non potrà costituire motivo di contestazione, richiesta di indennizzo, risarcimento o riduzione del corrispettivo.\n"
             "La posa verrà pertanto programmata in accordo con le effettive disponibilità del COMMITTENTE, anche oltre le tempistiche indicative previste dal presente Contratto, senza che ciò comporti alcuna responsabilità o inadempimento da parte della FORNITRICE. Il COMMITTENTE prende atto e accetta espressamente che la data di esecuzione della posa, in tali circostanze, dipende esclusivamente dalla propria disponibilità e non può essere opposta alla FORNITRICE come ritardo contrattuale.\n"
             "Rinvio per condizioni climatiche avverse. La FORNITRICE si riserva la facoltà di rinviare la data di posa qualora, al momento dell'intervento, siano presenti condizioni climatiche avverse che possano pregiudicare la corretta esecuzione dell'installazione, la qualità del prodotto installato o la sicurezza degli operatori (a titolo esemplificativo: pioggia, neve, gelo, vento forte, temperature eccessivamente basse o elevate). In tali casi il rinvio non costituisce inadempimento contrattuale né comporta alcun obbligo di indennizzo o risarcimento nei confronti del COMMITTENTE. La nuova data di posa verrà concordata con il COMMITTENTE non appena le condizioni climatiche lo consentano."},
    {"code": "ART_13", "number": "13", "title": "VIZI E DIFETTI DEI PRODOTTI ALLA CONSEGNA",
     "text": "Il COMMITTENTE, al momento della ricezione della merce, ha l'onere di controllarla e di denunciare eventuali vizi e/o difetti qualitativi – ivi inclusi difformità di colore, tipologia di apertura, progettazione tecnica o qualsiasi altra caratteristica rispetto a quanto indicato nel preventivo – entro il termine di decadenza di 7 (sette) giorni dalla ricezione, ovvero entro 7 (sette) giorni dalla scoperta, a mezzo raccomandata A/R o PEC. Decorso inutilmente tale termine, il prodotto si intende accettato in ogni sua caratteristica.\n"
             "Accettazione implicita per installazione. Qualora il COMMITTENTE, o terzi da lui incaricati, proceda all'installazione o al montaggio del serramento ricevuto – a prescindere da chi esegua materialmente la posa – tale condotta costituisce accettazione implicita, definitiva e irrevocabile del prodotto in tutte le sue caratteristiche, incluse colorazione, tipologia di apertura, configurazione tecnica e progettazione. L'avvenuta installazione preclude qualsiasi successiva contestazione relativa a difformità apparenti, errata apertura, colore non conforme o qualsivoglia caratteristica verificabile prima o durante la posa. Nessuna richiesta di sostituzione, rimborso, risarcimento o risoluzione contrattuale potrà essere avanzata dal COMMITTENTE successivamente all'installazione per vizi o difformità che avrebbero potuto essere rilevati prima o durante la posa stessa.\n"
             "Il FORNITORE procederà a sua discrezione alla riparazione, ripristino o sostituzione dei prodotti viziati, alla sola condizione che gli stessi vengano restituiti e non siano stati oggetto di installazione, lavorazione o trasformazione, anche parziale, da parte di personale non autorizzato dal FORNITORE."},
    {"code": "ART_14", "number": "14", "title": "GARANZIA",
     "text": "La garanzia riconosciuta dal FORNITORE e la sua durata sono scritte nel preventivo e/o nella proposta di acquisto. In assenza di tale indicazione, la garanzia riconosciuta è quella prevista per legge, con decorrenza dalla data del verbale di fine lavori.\n"
             "Eventuali difetti coperti dalla garanzia devono essere segnalati entro 7 (sette) giorni dalla comparsa tramite raccomandata A/R o PEC, pena la decadenza della garanzia.\n"
             "La garanzia non si applica in caso di manutenzione impropria, assenza di manutenzione ordinaria, normale usura dei componenti, o utilizzo dei prodotti per scopi diversi da quelli a cui erano destinati. In caso di reclami ingiustificati, il costo dell'intervento tecnico sarà addebitato al COMMITTENTE."},
    {"code": "ART_15", "number": "15", "title": "FORZA MAGGIORE – RECESSO",
     "text": "Nel caso in cui l'esecuzione del presente Contratto sia ritardata, impedita od ostacolata da cause di forza maggiore, l'esecuzione si intenderà sospesa per un periodo equivalente alla durata della causa. Se la sospensione si protrae oltre 30 giorni, ciascuna parte potrà recedere con comunicazione scritta a mezzo raccomandata A/R o PEC, fermo restando l'obbligo del COMMITTENTE di pagare il corrispettivo per la parte di fornitura eseguita."},
    {"code": "ART_16", "number": "16", "title": "ESCLUSIONE DEL DIRITTO DI RECESSO",
     "text": "Ai sensi dell'art. 59, comma 1, lett. c) del D.Lgs. 206/2005 (Codice del Consumo), i prodotti oggetto del presente contratto costituiscono beni confezionati su misura e chiaramente personalizzati, realizzati esclusivamente sulla base delle specifiche dimensionali, tecniche ed estetiche del COMMITTENTE. Pertanto, il COMMITTENTE non beneficia del diritto di recesso, a prescindere dall'effettivo stato di avanzamento della commessa.\n"
             "Qualora la FORNITRICE, a propria esclusiva discrezione, dovesse accogliere un'eventuale richiesta di scioglimento anticipato, tutti i costi sostenuti (progettazione, rilievo tecnico, gestione amministrativa, approvvigionamento, avvio produzione) resteranno integralmente a carico del COMMITTENTE, unitamente a una penale per la perdita della commessa."},
    {"code": "ART_17", "number": "17", "title": "VERIFICA E ACCETTAZIONE DELL'OPERA",
     "text": "La verifica della corretta esecuzione dell'opera sarà effettuata dal COMMITTENTE al termine delle attività di fornitura e posa, in contraddittorio con la FORNITRICE o con un soggetto dalla stessa incaricato.\n"
             "Il verbale di collaudo, una volta redatto, dovrà essere sottoscritto dal COMMITTENTE per presa visione e accettazione e costituirà prova dell'avvenuta consegna, installazione e verifica della fornitura.\n"
             "Qualora il COMMITTENTE si rifiuti di sottoscrivere il verbale di collaudo senza motivazione tecnica documentata e contestuale, la fornitura si intenderà comunque accettata e regolarmente eseguita, con decorrenza della garanzia dalla data dell'intervento. Il rifiuto ingiustificato non sospende né proroga i termini di pagamento né costituisce titolo per richieste di indennizzo o risarcimento."},
    {"code": "ART_18", "number": "18", "title": "DISPOSIZIONI VARIE",
     "text": "Il presente Contratto annulla e sostituisce qualsiasi altro precedente accordo, verbale o scritto, tra le parti relativamente al suo oggetto. Qualsiasi integrazione o modifica sarà considerata valida solo se apportata per iscritto e approvata da entrambe le parti."},
    {"code": "ART_19", "number": "19", "title": "TUTELA DATI PERSONALI",
     "text": "I dati personali delle parti verranno utilizzati al fine esclusivo di dare esecuzione al presente Contratto o per adempiere ad obblighi di legge, nel rispetto del D.Lgs. 196/2003 e del Regolamento Europeo 2016/679 (GDPR)."},
    {"code": "ART_20", "number": "20", "title": "LEGGE APPLICABILE",
     "text": "Il presente Contratto è soggetto alla legge italiana. Ad esso si applicano, per quanto non previsto, le norme del Codice Civile e le altre disposizioni di legge vigenti in materia."},
    {"code": "ART_21", "number": "21", "title": "CONTROVERSIE – FORO COMPETENTE",
     "text": "Per qualsiasi controversia inerente l'interpretazione, l'esecuzione o l'invalidità del presente contratto, sarà in via esclusiva competente il Foro di Lecco."},
    {"code": "ART_22", "number": "22", "title": "BONIFICO PARLANTE PER DETRAZIONE FISCALE",
     "text": "Qualora il COMMITTENTE intenda usufruire delle detrazioni fiscali previste dalla normativa vigente, è tenuto ad effettuare i pagamenti mediante bonifico parlante conforme alle disposizioni di legge applicabili, attenendosi scrupolosamente alle istruzioni fornite dalla FORNITRICE.\n"
             "La responsabilità per la corretta esecuzione del bonifico parlante (causale, codice fiscale, P.IVA, riferimenti normativi) resta integralmente ed esclusivamente a carico del COMMITTENTE. La FORNITRICE non assume alcuna responsabilità per errori, omissioni o inesattezze del COMMITTENTE nell'esecuzione del bonifico, né per l'eventuale perdita del beneficio fiscale."},
    {"code": "ART_23", "number": "23", "title": "PRATICA ENEA, NATURA DEL SERVIZIO ED ESCLUSIONE DI RESPONSABILITÀ",
     "text": "Qualora il COMMITTENTE richieda la trasmissione della pratica ENEA, tale attività costituisce un servizio accessorio distinto dalla fornitura principale, soggetto a un corrispettivo di Euro 250,00 (duecentocinquanta/00) per ciascuna pratica.\n"
             "La trasmissione viene effettuata dalla FORNITRICE esclusivamente in nome e per conto del COMMITTENTE, sulla base delle informazioni fornite dal COMMITTENTE stesso, che resta il solo responsabile della veridicità e correttezza dei dati trasmessi. La FORNITRICE non assume alcuna responsabilità legale, fiscale o economica in relazione alla pratica ENEA."},
    {"code": "ART_24", "number": "24", "title": "TUTELA DELLA REPUTAZIONE COMMERCIALE",
     "text": "Il COMMITTENTE si impegna a non pubblicare, su qualsiasi piattaforma digitale, social network, portale di recensioni o altro mezzo di comunicazione, dichiarazioni false, gravemente tendenziose o diffamatorie nei confronti del FORNITORE.\n"
             "In caso di violazione accertata, il FORNITORE si riserva ogni azione legale nelle sedi competenti, inclusa la richiesta di risarcimento dei danni patrimoniali e non patrimoniali, con particolare riferimento al danno all'immagine commerciale.\n"
             "Resta fermo il diritto del COMMITTENTE di esprimere valutazioni veritiere e circostanziate sull'esecuzione della fornitura, nel rispetto dei limiti della critica legittima e della correttezza delle informazioni riportate."},
]

# Approvazione specifica clausole onerose (artt. 1341/1342 c.c.) — doppia approvazione come da documento ufficiale.
CLAUSE_APPROVAL = {
    "title": "APPROVAZIONE SPECIFICA DI CLAUSOLE ONEROSE",
    "text": (
        "Il COMMITTENTE dichiara di aver letto e di approvare espressamente le seguenti clausole del presente contratto, ai sensi degli artt. 1341 e 1342 c.c.:\n"
        "Sezione 4 (modalità di pagamento); Artt. 2-bis (comprensione tecnica), 3 (ordini e modifiche), 3-bis (variazioni colore/tipologia), 3-ter (accessori esclusi), "
        "3-quater (rilievo tecnico a pagamento), 4 (posa e subappalto), 5 (corrispettivo), 5-bis (silenzio-assenso), 6 (pagamento e sospensione consegna), "
        "7 (clausola risolutiva espressa e penale 20%), 9 (solve et repete), 10 (trasporto e consegna), 11-bis (penale accesso cantiere), 12 (termini di consegna indicativi), "
        "13 (decadenza denuncia vizi 7 giorni e accettazione implicita per installazione), 14 (garanzia e decadenza 7 giorni), 15 (forza maggiore), 16 (esclusione recesso), "
        "17 (accettazione tacita collaudo), 21 (foro esclusivo di Lecco), 22 (responsabilità bonifico parlante), 23 (pratica ENEA), 24 (tutela reputazione)."
    ),
    "article_numbers": ["2-bis", "3", "3-bis", "3-ter", "3-quater", "4", "5", "5-bis", "6", "7", "9", "10", "11-bis", "12", "13", "14", "15", "16", "17", "21", "22", "23", "24"],
    "second_approval_text": (
        "IL COMMITTENTE ai sensi e per gli effetti degli artt. 1341 e 1342 Cod. Civ., approva espressamente le seguenti clausole: 3, 5, 6,9,12,15, 1, 6, 21."
    ),
    "legal_review_note": "LEGAL_REVIEW_RECOMMENDED: verifica visiva del documento sorgente (pag. 7) — la seconda approvazione riporta chiaramente '3, 5, 6,9,12,15, 1, 6, 21.' (elenco separato '1, 6'). Trascritto fedelmente, nessuna reinterpretazione.",
}

# Punti firma previsti dal documento ufficiale
SIGNATURE_POINTS: List[Dict[str, str]] = [
    {"key": "modulo", "label": "Firma per esteso", "where": "Modulo di Proposta d'Acquisto — dichiarazioni del COMMITTENTE", "with_date": True},
    {"key": "gdpr", "label": "Firma per esteso", "where": "Consenso al trattamento dei dati personali", "with_date": True},
    {"key": "sigla", "label": "Sigla", "where": "In calce a ciascuna pagina delle Condizioni Generali", "with_date": False},
    {"key": "clausole_onerose", "label": "Firma per esteso", "where": "Approvazione specifica di clausole onerose (artt. 1341 e 1342 c.c.)", "with_date": True},
    {"key": "clausole_onerose_2", "label": "Firma per esteso", "where": "Seconda approvazione espressa artt. 1341 e 1342 Cod. Civ.", "with_date": True},
    {"key": "procedura", "label": "Firma per esteso", "where": "Procedura Aziendale - Produzione e Installazione Infissi", "with_date": False},
]

# Allegato — Procedura Aziendale (pag. 8)
COMPANY_PROCEDURE = {
    "title": "Procedura Aziendale - Produzione e Installazione Infissi",
    "intro": "Gentile Cliente,\nper garantire trasparenza, qualità e puntualitas, la nostra azienda adotta una procedura standardizzata che accompagna ogni progetto, dalla prima consulenza fino al collaudo finale.",
    "steps": [
        {"title": "1. Primo contatto", "items": ["Chiamata conoscitiva per comprendere le necessità iniziali.", "Pianificazione del primo incontro."]},
        {"title": "2. Consulenza e sopralluogo", "items": ["Incontro conoscitivo presso il cliente o in showroom.", "Analisi delle esigenze estetiche e funzionali.", "Rilevazione preliminare dei dati."]},
        {"title": "3. Studio tecnico e proposta", "items": ["Approfondimento delle richieste.", "Ricerca delle soluzioni più adatte in base a funzionalità, estetica e budget.", "Presentazione delle opzioni con caratteristiche tecniche illustrate."]},
        {"title": "4. Offerta personalizzata", "items": ["Invio di un preventivo chiaro e dettagliato.", "Eventuali modifiche sulla base delle preferenze del cliente."]},
        {"title": "5. Conferma e avvio lavori", "items": ["Accettazione dell'offerta e firma del contratto.", "Versamento dell'acconto concordato. o avvio pratica di finanziamento.", "Presa misure tecnica da parte del nostro staff specializzato."]},
        {"title": "6. Produzione infissi", "items": ["Realizzazione su misura con processi certificati e materiali Made in Italy.", "Controlli qualità in ogni fase produttiva."]},
        {"title": "7. Avviso merce pronta e saldo", "items": ["Comunicazione ufficiale al cliente della disponibilità della merce.", "Regolarizzazione del saldo prima della consegna."]},
        {"title": "8. Logistica e documentazione", "items": ["Consegna presso il nostro magazzino e verifica qualità finale.", "Compilazione e invio della pratica ENEA (ove prevista)."]},
        {"title": "9. Montaggio", "items": ["Concordo con il cliente la data di posa.", "Preparazione dell'area di lavoro.", "Installazione dei serramenti.", "Pulizia area di lavoro."]},
        {"title": "10. Collaudo finale", "items": ["Verifica funzionalità, isolamento e finiture.", "Redazione e consegna del verbale di collaudo."]},
    ],
    "quality_title": "Garanzia di Qualità",
    "quality_intro": "La procedura adottata garantisce:",
    "quality_items": ["Massima trasparenza in ogni fase.", "Rispetto dei tempi concordati.", "Controlli tecnici e qualitativi costanti.", "Servizio completo dalla consulenza alla posa, con garanzia."],
}


def canonical_terms_text(articles: Optional[List[Dict[str, str]]] = None, approval: Optional[Dict[str, Any]] = None) -> str:
    """Testo integrale deterministico (articoli + approvazione clausole onerose). Usato per hash e invariance test."""
    arts = articles if articles is not None else ARTICLES
    appr = approval if approval is not None else CLAUSE_APPROVAL
    blocks = [f"Articolo {a['number']} – {a['title']}\n{a['text']}" for a in arts]
    blocks.append(f"{appr['title']}\n{appr['text']}\n{appr['second_approval_text']}")
    return "\n\n".join(blocks)


def canonical_hash(text: Optional[str] = None) -> str:
    return hashlib.sha256((text if text is not None else canonical_terms_text()).encode("utf-8")).hexdigest()


def canonical_document() -> Dict[str, Any]:
    """Risorsa canonica completa GENERAL_TERMS_VERSION (serializzabile, congelabile nello snapshot contratto)."""
    text = canonical_terms_text()
    return {
        "version": GENERAL_TERMS_VERSION,
        "effective_from": EFFECTIVE_FROM,
        "source_document": SOURCE_DOCUMENT,
        "supplier_header": SUPPLIER_HEADER,
        "committente_header": COMMITTENTE_HEADER,
        "customer_declarations": CUSTOMER_DECLARATIONS,
        "payment_instructions": PAYMENT_INSTRUCTIONS,
        "gdpr_consent": GDPR_CONSENT,
        "articles": [dict(a) for a in ARTICLES],
        "articles_count": len(ARTICLES),
        "clause_approval": dict(CLAUSE_APPROVAL),
        "signature_points": [dict(s) for s in SIGNATURE_POINTS],
        "company_procedure": COMPANY_PROCEDURE,
        "full_text": text,
        "general_terms_hash": canonical_hash(text),
    }


GT_VERSIONS: Dict[str, Any] = {GENERAL_TERMS_VERSION: canonical_document}


def get_canonical(version: Optional[str] = None) -> Dict[str, Any]:
    """Ritorna la versione richiesta (default: corrente). Versioni sconosciute -> KeyError (fail-closed)."""
    return GT_VERSIONS[version or GENERAL_TERMS_VERSION]()
