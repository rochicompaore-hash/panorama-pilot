# Anteprima del modulo cassa

Questa anteprima importa `CashCommandCenterView` direttamente dal frontend di Panorama Pilot. Non contiene una seconda implementazione della dashboard o delle formule finanziarie.

## Rigenerazione

Dalla radice del repository:

```bash
python preview/cashflow/generate_data.py
cd preview/cashflow
npm ci --no-audit --no-fund
npm run build
```

Il generatore Python deve poter importare i servizi del backend e le loro dipendenze. Produce `data/scenarios.json` richiamando il vero motore di calcolo con dati sintetici. La build si interrompe se il file manca, non contiene JSON valido o non rispetta il formato richiesto. Non esiste un ripiego su risultati scritti manualmente.

Per una verifica locale, dalla directory `preview/cashflow`:

```bash
python -m http.server 4173 --directory dist --bind 127.0.0.1
```

Aprire `http://127.0.0.1:4173`. La directory `dist/` contiene i file statici da pubblicare nell’ambiente di anteprima.

## Scenari

Il JSON ha questo contratto:

```text
Array di quattro oggetti:
{
  id: "overdue" | "uncertified" | "undated" | "boundary",
  title: string,
  description: string,
  data: payload completo dell’endpoint cash-command-center
}
```

Ogni ID deve essere presente una volta. Il selettore monta la stessa vista con il payload scelto; il frammento URL consente di aprire direttamente un caso, per esempio `#uncertified`. I risultati finanziari provengono dal generatore Python; il selettore non li ricalcola in JavaScript.

## Isolamento dell’anteprima

La pagina monta soltanto `CashCommandCenterView`, senza il wrapper di produzione che esegue `useQuery`. Un alias di build sostituisce esclusivamente l’import di `@/api/client` con `src/api-disabled.js`: qualunque utilizzo accidentale genera un errore locale. Questo file non simula risposte API e non contiene formule finanziarie. Il build verifica inoltre che il client API di produzione non compaia fra i moduli inclusi.

Gli scenari sono importati nel bundle. Non sono presenti chiamate a servizi aziendali, autenticazione, invii o salvataggi. Le interazioni disponibili riguardano la selezione dello scenario, l’apertura delle sezioni e i tooltip del grafico.

La build legge il tema Tailwind e il CSS del frontend reale, aggiungendo soltanto la cornice dell’anteprima. L’import remoto dei font Google viene rimosso per mantenere la pagina autonoma; si usano i font disponibili nel browser. Le dipendenze React, Recharts e Tailwind sono allineate alle versioni dichiarate in `frontend/package.json`.

`build-manifest.json` identifica il componente e gli scenari inclusi. `node_modules/` e `dist/` restano fuori dal versionamento.
