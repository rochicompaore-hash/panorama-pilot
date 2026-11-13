# Panorama Pilot

Gestionale con frontend React e backend FastAPI/MongoDB. Il centro operativo `/operations` aggiunge responsabilità, controlli con evidenze e scadenze alle commesse già utilizzate dagli altri moduli.

- **Commesse:** responsabile, prossima azione, scadenza, blocchi e completamenti.
- **Avanzamenti controllati:** verifiche commerciali, amministrative, tecniche, logistiche e di posa, con autore e data.
- **Finanziamenti:** approvazione, firma, richiesta di liquidazione ed erogazione distinte.
- **Assistenza:** prima segnalazione conservata, termini per priorità, assegnazione e chiusura motivata.
- **Esportazione:** CSV operativo e JSON delle commesse, inclusi controlli e storico. Tutte le righe corrispondenti a ricerca e fase, non soltanto la pagina corrente.

La [guida del centro operativo](docs/OPERATIONS.md) descrive uso, permessi, compatibilità e verifiche di avvio.

## Sviluppo e verifica

Per le sole verifiche delle nuove regole, senza database esterno né invio email:

```bash
python -m venv .venv
.venv/bin/pip install -r backend/requirements-operations-test.txt
PYTHONPATH=backend .venv/bin/pytest backend/tests/test_operational_control.py -q
```

Per compilare il frontend:

```bash
cd frontend
npx --yes yarn@1.22.22 install --frozen-lockfile --ignore-scripts --non-interactive
CI=false REACT_APP_BACKEND_URL=https://example.invalid GENERATE_SOURCEMAP=false npx --yes yarn@1.22.22 build
```

L’URL dell’esempio è intenzionalmente non operativo. In esecuzione impostare `REACT_APP_BACKEND_URL` all’origine HTTPS reale dell’API, senza suffisso `/api`. `CI=false` mantiene gli avvisi già presenti nel progetto senza trasformarli in errori; gli errori di compilazione restano bloccanti.

L’avvio completo usa le dipendenze di `backend/requirements.txt` e l’infrastruttura esistente. Il backend richiede almeno `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`. Configurare inoltre origine frontend, CORS, storage e servizi previsti dal proprio ambiente. In staging/produzione disattivare dati demo e debug OTP, e verificare backup e accessi prima di usare dati reali. Non usare le credenziali fittizie dei test.

GitHub conserva il codice e può eseguire i controlli; non ospita il database MongoDB e non rende automaticamente operativa l’applicazione FastAPI. Questo repository non deve contenere dati cliente, allegati aziendali, esportazioni, credenziali o file `.env`.
