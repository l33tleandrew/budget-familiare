# Test ed eval

Tutto gira con la sola stdlib (`unittest`), come lo script: sul server il plugin usa
l'interprete di Hermes e non c'e' modo di installare pacchetti. L'unica eccezione e'
`eval_modello.py`, che e' opt-in e chiede l'SDK ufficiale.

```bash
make test             # tutto quello che gira offline
make plugin           # solo il plugin: manifest, registrazioni, middleware, hook
make eval             # la sola eval deterministica, con le trascrizioni
make eval-smemorato   # l'eval avversariale: un modello che non ricorda niente
make eval-modello     # l'eval col modello: chiamate a pagamento
```

## Cosa c'e' dentro

| File | Cosa verifica |
|---|---|
| `test_budget_sheets.py` | Lo script: validazione di data, importo e tassonomia, la macchina a stati di `parse_data`, la CLI con i suoi exit code, e lo strato di rete (auth, retry sul 401, riga scritta) sotto mock. |
| `test_plugin.py` | Il plugin: manifest coerente con quello che `register()` registra davvero, e i vincoli che deve imporre — il middleware che deriva `nuova` dal disco, `transform_llm_output` che sostituisce la risposta col messaggio dello script, `pre_tool_call` che blocca lo script shellato. |
| `test_schemas.py` | Che lo schema del tool — l'unico testo che il modello legge a ogni turno — non sappia cose che non sono affar suo: percorsi, interprete, flag da riga di comando, i messaggi dello script, l'elenco delle categorie, il foglio di destinazione. E che resti corto. |
| `percorsi.py` | Dove stanno le cose, in un posto solo. |
| `eval_protocollo.py` | La skill a livello di protocollo: rigioca le conversazioni di `casi_eval.json` e verifica messaggi mostrati, gating della conferma, trappole e riga finale. |
| `eval_smemorato.py` | La resistenza: modelli che dimenticano tutto fra un turno e l'altro devono arrivare lo stesso alla stessa riga. |
| `eval_modello.py` | L'interpretazione: un modello legge lo schema del tool insieme al messaggio informale, e si verifica che ne ricavi i campi giusti. |
| `casi_eval.json` | I casi, condivisi dalle tre eval. |

## Perche' non si tocca mai Google Sheets

Le due funzioni che parlano con Google — `get_access_token` e `append_row` — sono
sostituite a ogni giro, e `urllib.request.urlopen` e' sotto mock con un `side_effect`
che solleva: se un giorno lo script provasse a raggiungere la rete per altre vie,
l'eval fallisce invece di scrivere davvero. L'unico test che lancia lo script come
processo vero non arriva mai alla conferma, quindi si ferma sulla validazione.

`test_plugin.py` scrive la bozza in un file temporaneo (`BUDGET_BOZZA_FILE`, impostato
prima di caricare il plugin): senza, userebbe la bozza vera del profilo.

`eval_modello.py` non esegue comandi affatto: chiede al modello *quali* campi
passerebbe, non glieli fa passare.

## Aggiungere un caso

Una voce in `casi_eval.json`:

```jsonc
{
  "id": "identificativo-in-kebab-case",
  "descrizione": "cosa dimostra questo caso",
  "messaggio": "il messaggio informale dell'utente",
  "interpretazione": {                  // i campi della PRIMA chiamata; "" = non deducibile
    "data": "", "categoria": "Supermercato", "sottocategoria": "",
    "importo": "40.00", "descrizione": "Spesa"
  },
  "valuta_interpretazione": true,       // false se l'interpretazione e' sbagliata apposta
  "risposte": ["sì"],                   // cosa risponde l'utente, in ordine
  "stati_attesi": ["chiedi_conferma"],  // gli stati attraversati, in ordine
  "esito": "scritta",                   // scritta | non_scritta | loop | errore
  "riga_attesa": {                      // null se non si deve scrivere niente
    "data": "OGGI", "tipo": "Uscita", "categoria": "Supermercato",
    "sottocategoria": "", "importo": 40.0
  }
}
```

In `stati_attesi` vanno i nomi degli stati `chiedi_*` che lo script attraversa, uno per
domanda posta, nell'ordine in cui le pone — non i messaggi mostrati all'utente.

### Date: mai scritte a mano

Da quando le date fuori dall'anno del budget vengono rifiutate, un `2026` scritto a mano in
un caso è una bomba a orologeria: verde finché `ANNO_BUDGET` è quello, rossa il giorno in cui
si sposta. Quindi nei casi si usano tre segnaposto, e mai un anno letterale:

| | Vale |
|---|---|
| `OGGI` | la data odierna del sistema — **solo** in `riga_attesa` |
| `{ANNO}` | `ANNO_BUDGET`, ovunque nel caso: una data che si deve poter registrare |
| `{ALTRO_ANNO}` | `ANNO_BUDGET - 1`: una data che il plugin **deve** rifiutare |

`{ANNO}` e `{ALTRO_ANNO}` si risolvono al caricamento, in `carica_casi()`, quindi valgono in
`messaggio`, `interpretazione`, `risposte` e `riga_attesa` allo stesso modo.

I casi con `valuta_interpretazione: false` partono da un'interpretazione sbagliata di
proposito, per provare il recupero: l'eval deterministica li usa, quella col modello li salta.

## L'eval col modello

Usa `claude-opus-5` (override con `EVAL_MODELLO`), legge lo schema del tool e la
tassonomia dal repo come farebbe il plugin vero, e confronta i campi normalizzandoli
con le stesse funzioni dello script: `3` e `Cibo fuori / bevute` contano uguale, e da
quando le migliaia le scioglie lo script anche `1.500` e `1500.00`. `30 €` no: lo
script lo rifiuterebbe. La descrizione si riporta ma
non fa punteggio: e' testo libero e non ha una risposta giusta sola.

Non ha i fallback server-side sulle rifiutate: in un'eval un instradamento silenzioso
verso un altro modello falserebbe la misura, che serve proprio a dire come si comporta
*quel* modello. Una rifiutata viene riportata come errore del caso.
