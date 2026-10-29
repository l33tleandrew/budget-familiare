# budget-familiare

Plugin [Hermes Agent](https://hermes-agent.nousresearch.com) che registra spese
ed entrate sul foglio Budget di Google Sheets, conducendo il dialogo con
l'utente un campo alla volta.

```
utente  │ benzina 50
agente  │ Quale categoria? Rispondi con il numero.
        │ 1. Stipendio
        │ 2. Supermercato
        │ …
utente  │ 4
agente  │ Quale sottocategoria di «Auto / Moto»? …
```

## Installazione

```bash
hermes plugins install l33tleandrew/budget-familiare --ref <sha-40>
hermes plugins enable budget-familiare
hermes plugins list        # ✓ budget-familiare v1.0.0 (1 tools, 4 hooks)
```

I plugin generali sono disabilitati di default: senza `enable` non carica. Il
`--ref` vuole uno SHA esatto di 40 caratteri — tag e branch vengono rifiutati.

La radice del repo **è** la radice del plugin, quindi in alternativa si clona
direttamente al posto giusto — la directory va chiamata come il plugin, non come
il repo:

```bash
git clone https://github.com/l33tleandrew/budget-familiare.git \
    <profilo>/plugins/budget-familiare
hermes plugins doctor <profilo>/plugins/budget-familiare --ci
hermes plugins enable budget-familiare
```

### Configurazione e credenziali

Il codice non nomina nessuna istanza: lo stesso commit gira con fogli e account Google
diversi. Tutto quello che è per-istanza sta nel profilo Hermes in cui il plugin è
installato, cioè due livelli sopra la sua cartella (`<profilo>/plugins/budget-familiare`):

| Nel profilo | Cosa contiene |
|---|---|
| `.env` | `GOOGLE_SPREADSHEET_ID` e `ANNO_BUDGET`, chieste da `hermes plugins install`; facoltativa `GOOGLE_SHEET_NAME` (default `Transazioni <anno>`) |
| `google_client_secret.json` | il client OAuth «App desktop» del progetto Google Cloud |
| `google_token.json` | token con refresh, creato da `setup_google.py` |

Se manca l'id del foglio o l'anno, il plugin non registra niente: risponde che non è
configurato e nomina la variabile da impostare. L'anno si cambia nel `.env`, dopo aver
creato la scheda del nuovo anno sul foglio, e poi si riavvia Hermes.

### Su un'istanza nuova, passo per passo

Una volta per istanza. Servono l'account Google della famiglia e una shell sul server.

**1. Google Cloud.** Nella [Google Cloud Console](https://console.cloud.google.com/):

- abilita la **Google Sheets API**;
- nella schermata di consenso OAuth, aggiungi lo scope `…/auth/spreadsheets`;
- crea una credenziale **ID client OAuth, tipo «App desktop»** e scarica il JSON.

Si può anche riusare il client di un'altra istanza: identifica l'app, non la famiglia.

> ⚠️ Se l'app è in stato **«Testing»**, l'account va aggiunto agli utenti di test, e Google
> fa scadere i refresh token dopo **7 giorni**: una volta a settimana il plugin risponderebbe
> che le credenziali vanno rigenerate. Per un uso stabile l'app va pubblicata («In
> production»).

**2. Il foglio.** Nell'account della famiglia, un foglio con una scheda
`Transazioni <anno>` (es. `Transazioni 2026`). Il plugin scrive sette colonne, da A a G:
data, tipo, categoria, sottocategoria, importo, descrizione, note. Conviene metterle come
intestazioni in riga 1. L'id è nell'URL: `https://docs.google.com/spreadsheets/d/<ID>/edit`.

**3. Il plugin.**

```bash
hermes -p <profilo> plugins install l33tleandrew/budget-familiare --ref <sha-40>
#   GOOGLE_SPREADSHEET_ID: <l'id del foglio>
#   ANNO_BUDGET: 2026
hermes -p <profilo> plugins enable budget-familiare
```

Senza `-p` vale il profilo attivo. Se invece si clona il repo a mano, nessuno chiede niente:
le due righe vanno scritte nel `.env` del profilo.

**4. Il consenso.** Copia il JSON del client in `<profilo>/google_client_secret.json`, poi:

```bash
cd <profilo>/plugins/budget-familiare      # es. /opt/data/profiles/<profilo>/plugins/…
python3 setup_google.py url        # apri l'indirizzo e accedi con l'account della famiglia
python3 setup_google.py codice "<l'indirizzo su cui è finito il browser>"
python3 setup_google.py verifica   # una ✓ per riga: client, token, foglio, scheda, anno
```

Il browser può stare su un altro computer. Dopo il consenso si ferma su
`http://localhost:1/…`, una pagina che non si carica: è normale, si copia l'indirizzo dalla
barra. `codice` non sostituisce un `google_token.json` già presente senza `--force`, perché
potrebbe appartenere a un'altra integrazione Google del profilo.

**5. La prova.** Riavvia Hermes e registra una spesa vera con `/spesa`: la riga deve
comparire sul foglio.

**Da non fare:** non installare il cron di `scripts/sync_budget_skill.sh`. Serve all'istanza
di sviluppo; da una seconda spingerebbe su `main` anche lei.

**Ogni anno:** prima crea la scheda `Transazioni <anno nuovo>` sul foglio, poi cambia
`ANNO_BUDGET` nel `.env` e riavvia Hermes. `setup_google.py verifica` dice se tornano.

## Com'è fatto

Lo stato del dialogo vive su disco, gestito da `budget_sheets.py`: TTL, lock,
marcatore anti-doppione, validazione, e i messaggi all'utente composti per
intero in Python. Il plugin non riscrive niente di tutto questo — toglie al
modello quello che non è comprensione del linguaggio, una superficie per volta.

```
budget-familiare/
├── plugin.yaml          manifest: tool, hook e variabili per istanza
├── __init__.py          register(ctx): le cinque superfici di vincolo
├── schemas.py           schema del tool — qui vive il trigger
├── tools.py             handler + la cassetta della resa verbatim
├── budget_sheets.py     il motore: macchina a stati, bozza, Google Sheets
├── setup_google.py      il consenso OAuth di un'istanza nuova, e la verifica
└── tassonomia.yaml      le categorie (dato, non codice)
```

| Superficie | Cosa toglie al modello |
|---|---|
| `register_tool` | la shell: argomenti tipizzati, nessun quoting |
| middleware `tool_request` | l'instradamento: `nuova` si legge dal disco |
| `pre_llm_call` | la memoria: lo stato reiniettato a ogni turno |
| `transform_llm_output` | la parafrasi: la risposta è il testo dello script |
| `pre_tool_call` | le scorciatoie: lo script shellato viene bloccato |

Resta probabilistico un punto solo: se «8,5» a freddo faccia scattare il tool.
`/spesa 8,5` è la via esplicita quando non scatta.

**Non c'è nessuna SKILL.md, ed è deliberato.** Una skill impacchettata in un
plugin non compare nell'index né in `skills_list`: si carica solo con un
`skill_view()` esplicito, quindi nessuno la leggerebbe mai. Tutto quello che il
modello deve sapere — quando attivarsi, cosa estrarre, come passarlo — sta nella
descrizione del tool e in quelle dei suoi parametri, in [schemas.py](schemas.py),
che il system prompt porta con sé a ogni turno.

Lo script resta una CLI funzionante, per l'uso a mano da un terminale. `.env` e
credenziali li legge dal profilo in cui è installato, quindi basta lanciare quella copia:

```bash
python3 <profilo>/plugins/budget-familiare/budget_sheets.py append --importo 30 --categoria Sport
```

## Test

```bash
make test             # 331 test, nessuna rete, nessuna riga sul foglio
make plugin           # solo il plugin
make eval             # rigioca le conversazioni di tests/casi_eval.json
make eval-smemorato   # un modello che non ricorda niente deve arrivare in fondo
```

Dettagli in [tests/README.md](tests/README.md).
