# SPEC-05 — Configurazione per istanza

**Stato:** fatto · **Dipende da:** [SPEC-01](01-anno-budget-centralizzato.md),
[SPEC-02](02-guardia-cambio-anno.md) · **Comportamento:** nuovo stato terminale

---

## Problema

Il plugin deve poter girare su un'altra istanza Hermes, con un altro account Google e un altro
foglio, seguendo lo stesso flusso. Oggi non può: quello che distingue un'istanza dall'altra è
scritto nel codice, in cima a `budget_sheets.py`.

```python
PROFILE_DIR       = "/opt/data/profiles/budgetingagent"
SPREADSHEET_ID    = "1iDYzjzyu_du_axBmzOzI6k4DrzV2Y52_UZTFMtM6JB0"
ANNO_BUDGET       = int(os.environ.get("ANNO_BUDGET") or 2026)
```

- **`PROFILE_DIR`** nomina il profilo di un'istanza precisa. Ne discendono token, credenziali
  e bozza: su un altro profilo lo script li cercherebbe nel posto sbagliato.
- **`SPREADSHEET_ID`** è il foglio di una famiglia. Un'altra istanza scriverebbe lì.
- **`ANNO_BUDGET`** ha nel sorgente un default che vale per tutti. Ma la scheda del nuovo anno
  la crea ogni famiglia sul proprio foglio, quindi il cambio d'anno è per sua natura
  per-istanza. Con l'anno nel codice, una sola release a Capodanno sposterebbe tutte le istanze
  insieme, anche quelle che la scheda non l'hanno ancora creata.

---

## Comportamento richiesto

1. Lo stesso commit si installa su un'istanza qualsiasi **senza toccare il codice**.
2. Ciò che è per-istanza — id del foglio, anno, nome della scheda, credenziali, bozza — sta
   **nel profilo Hermes** dell'istanza.
3. `hermes plugins install` **chiede** l'id del foglio e l'anno a chi installa.
4. Un'istanza senza configurazione **non registra niente** e lo dice, nominando cosa manca e
   dove si sistema. Come per la guardia d'anno, `annulla` resta possibile.
5. Sull'istanza attuale, una volta migrata, nulla cambia.

---

## Progettazione

### Il profilo è `HERMES_HOME`

`hermes -p <nome>` mette la directory del profilo in `HERMES_HOME` prima di qualunque import,
e i plugin vivono in `$HERMES_HOME/plugins/<nome>`. Nel codice di Hermes c'è un helper,
`hermes_constants.get_hermes_home()`, con fallback `~/.hermes`.

```python
PROFILE_DIR = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
```

Si legge la variabile e non l'helper: lo script resta una CLI che gira anche dove Hermes non
è importabile.

### Il resto viene da `requires_env`, cioè dal `.env` del profilo

```yaml
requires_env:
  - name: GOOGLE_SPREADSHEET_ID
    description: "ID del foglio Google: la parte dell'URL fra /d/ e /edit"
  - name: ANNO_BUDGET
    description: "Anno del budget, es. 2026: la scheda «Transazioni <anno>» deve esistere"
optional_env:
  - GOOGLE_SHEET_NAME
```

`hermes plugins install` chiede ogni variabile ancora vuota e la salva in
`$HERMES_HOME/.env`, che Hermes carica nell'ambiente all'avvio. Lo script le legge con
`_config(nome)`: **prima l'ambiente, poi il `.env` del profilo**. Il secondo passo dentro
Hermes non fa niente; serve alla CLI lanciata da una shell, dove c'è al massimo `HERMES_HOME`.

```python
GOOGLE_SPREADSHEET_ID = _config("GOOGLE_SPREADSHEET_ID")
ANNO_BUDGET           = _anno(_config("ANNO_BUDGET"))
GOOGLE_SHEET_NAME     = _config("GOOGLE_SHEET_NAME") or f"Transazioni {ANNO_BUDGET}"
CONFIGURAZIONE        = ("GOOGLE_SPREADSHEET_ID", "ANNO_BUDGET")
```

`SPREADSHEET_ID` diventa **`GOOGLE_SPREADSHEET_ID`**, per la regola di SPEC-01 («la variabile
porta il nome della costante») e sul suo precedente: `SHEET_NAME` divenne `GOOGLE_SHEET_NAME`.

`_anno()` restituisce un intero per quattro cifre e `None` per qualunque altra cosa: un anno
storto **non fa più fallire l'import** (vedi Decisioni).

### La guardia e lo stato

```python
def configurazione_mancante():
    return [nome for nome in CONFIGURAZIONE if not globals()[nome]]
```

In `_turno()` va dopo `annulla` e **prima** di `anno_disallineato()`, che senza anno direbbe
«impostato sul None». Emette `errore_configurazione`, exit **8**, senza toccare la bozza. Il
messaggio nomina le variabili e il `.env` del profilo.

### Manifest e codice allineati

Un test confronta `requires_env` con `CONFIGURAZIONE`, come già si fa per tool e hook: una
variabile letta e non dichiarata non verrebbe chiesta a nessuno.

---

## Fuori scope

- **Il primo consenso OAuth** su un'istanza nuova: è [SPEC-06](06-consenso-oauth-incluso.md).
- **Tassonomia per istanza.** «Lo stesso flusso» vuol dire le stesse categorie, e gli id sono
  ciò che l'utente digita.
- **Spostare la bozza in `$HERMES_HOME/plugin-data/`**, il posto che Hermes suggerisce per lo
  stato dei plugin. Funziona già dov'è, fuori dalla directory del plugin.
- **Profili multipli nello stesso processo.** Vedi Decisioni.

---

## Criteri di accettazione

- [x] `budget_sheets.py` non contiene un id di foglio, un anno o un percorso di profilo
- [x] Senza `GOOGLE_SPREADSHEET_ID` o senza `ANNO_BUDGET`: stato `errore_configurazione`,
      exit **8**, **nessuna riga scritta**, **bozza preesistente intatta**
- [x] `annulla` produce ancora `annullata`
- [x] Il messaggio nomina la variabile mancante e il `.env`, e non nomina quelle presenti
- [x] Senza anno, vince `errore_configurazione` su `errore_anno`
- [x] Un `ANNO_BUDGET` storto non fa fallire l'import
- [x] Il `.env` del profilo viene letto, e l'ambiente vince su di esso
- [x] `requires_env` del manifest = `CONFIGURAZIONE`
- [x] La suite non vede mai il profilo vero, nemmeno lanciata sul server
- [x] `make test` verde: 288 → **300**; `make eval` e `make eval-smemorato` 20/20

---

## Test

- **`tests/percorsi.py`** assegna a `HERMES_HOME` una directory temporanea vuota, e imposta
  con `setdefault` `ANNO_BUDGET` all'anno civile e `GOOGLE_SPREADSHEET_ID` a `foglio-di-prova`.
- **`TestConfigurazione`** rilegge il modulo in un subprocess, con l'ambiente e il `.env` che
  servono. Le costanti si fissano all'import: patcharle non proverebbe la lettura.
- **`TestGuardiaConfigurazione`** segue `TestGuardiaAnno` riga per riga, con in più la
  precedenza fra le due guardie.
- **`TestManifest`**: il parser a mano salta gli attributi indentati di quattro spazi.
  Altrimenti la `description:` di una variabile prenderebbe il posto di quella del plugin.
- **Eliminato** `TestAnnoBudget.test_la_costante_e_allineata_all_anno_civile`: confrontava con
  l'anno civile il default nel sorgente, che non c'è più.

---

## Verifica

```bash
make test && make eval && make eval-smemorato

# la guardia, end-to-end, in un profilo vuoto
B=$(mktemp)
env -u GOOGLE_SPREADSHEET_ID -u ANNO_BUDGET HERMES_HOME=$(mktemp -d) BUDGET_BOZZA_FILE=$B \
  python3 budget_sheets.py append --nuova --importo 30
echo "exit: $?"      # atteso: 8, stato = errore_configurazione, nomina entrambe

# la stessa cosa con il .env del profilo: si passa alla domanda successiva
P=$(mktemp -d); printf 'GOOGLE_SPREADSHEET_ID=x\nANNO_BUDGET=%s\n' "$(date +%Y)" > $P/.env
env -u GOOGLE_SPREADSHEET_ID -u ANNO_BUDGET HERMES_HOME=$P BUDGET_BOZZA_FILE=$B \
  python3 budget_sheets.py append --nuova --importo 30
echo "exit: $?"      # atteso: 3, stato = chiedi_categoria
rm -rf $B $P
```

### Migrazione dell'istanza attuale, in quest'ordine

Saltare un passo ferma il plugin rumorosamente — `errore_configurazione` o `errore_auth` — mai
in silenzio.

1. **Prima del deploy**, in `/opt/data/profiles/budgetingagent/.env`:
   ```
   GOOGLE_SPREADSHEET_ID=1iDYzjzyu_du_axBmzOzI6k4DrzV2Y52_UZTFMtM6JB0
   ANNO_BUDGET=2026
   ```
2. Verificare che il processo Hermes del profilo abbia
   `HERMES_HOME=/opt/data/profiles/budgetingagent`:
   `tr '\0' '\n' < /proc/<pid>/environ | grep HERMES_HOME`. Nel container il Dockerfile
   imposta `/opt/data`: se il profilo non lo sovrascrive, token e credenziali non si trovano.
3. Deploy e riavvio di Hermes.
4. Una `/spesa` vera, fino alla riga sul foglio.

---

## Decisioni e alternative scartate

### `requires_env` e non `config_schema`

Hermes ha due meccanismi per la configurazione di un plugin.

- **`requires_env`**: l'install chiede i valori e li salva nel `.env` del profilo.
- **`config_schema`**, con `ctx.get_config()`: valori in `config.yaml` sotto
  `plugins.entries.<id>.settings`. È la sede «giusta» per impostazioni non segrete, e l'app
  Desktop ne fa un form. Ma l'install da CLI **non li chiede**. E soprattutto `ctx` esiste solo
  dentro `register()`: la CLI e i test ne avrebbero bisogno di un'altra strada, e due strade
  per la stessa configurazione prima o poi divergono.

Con `requires_env` plugin, CLI e test leggono dallo stesso posto, l'ambiente. È anche la
convenzione che il file aveva già per `ANNO_BUDGET` e `GOOGLE_SHEET_NAME`.

### Il riscontro di Hermes, verificato

L'agente su cui il plugin gira proponeva due approcci. Verificati sul sorgente di
`NousResearch/hermes-agent`:

- **A — `requires_config` nel manifest e `ctx.plugin_config`**: nessuno dei due esiste. Il
  campo sconosciuto verrebbe ignorato con un warning. L'equivalente reale è `config_schema`,
  discusso sopra.
- **B — un `budget-familiare.yaml` nel profilo**: funzionerebbe, ma è un terzo meccanismo
  accanto ai due di Hermes, con un altro parser a mano, e all'installazione non verrebbe
  chiesto niente a nessuno.

### Un file di configurazione, dopotutto — ma quello di Hermes

[SPEC-01](01-anno-budget-centralizzato.md) aveva scartato un file di configurazione, perché
«introdurne uno per un intero sarebbe sproporzionato». Il conto è cambiato: i valori
per-istanza sono quattro, e c'è una seconda istanza. Il file però non è nostro, è il `.env`
che Hermes gestisce già. `_env_del_profilo()` lo legge solo per la CLI.

### Un anno storto non fa più fallire l'import

SPEC-01 aveva scelto il contrario: «un anno storto sceglierebbe il foglio sbagliato, meglio non
partire». Allora la variabile serviva alle prove da terminale. Ora la scrive chi installa,
rispondendo a un prompt, e un errore di battitura è il caso normale.

In un plugin, «non partire» vuol dire import fallito, tool sparito, e il modello che risponde
da solo a «benzina 50». È la parafrasi che l'architettura esiste per impedire, e in più
direbbe all'utente di aver registrato una spesa che non c'è. `errore_configurazione` invece
arriva parola per parola, tramite `transform_llm_output`, e dice cosa sistemare. Il foglio
sbagliato resta impossibile: senza anno valido non si scrive.

### Nessun default, nemmeno per l'anno

Un default per `GOOGLE_SPREADSHEET_ID` è il foglio di qualcun altro. Per `ANNO_BUDGET`
l'alternativa tentatrice è l'anno civile, ma
[SPEC-01](01-anno-budget-centralizzato.md#decisioni-e-alternative-scartate) l'ha già scartata:
il primo gennaio punterebbe a una scheda che può non esistere, e annullerebbe la guardia di
[SPEC-02](02-guardia-cambio-anno.md). Meglio fermarsi e chiedere.

### `GOOGLE_*` in un `.env` condiviso

Il `.env` del profilo è di tutto l'agente, non solo del plugin. Nomi come
`GOOGLE_SPREADSHEET_ID` potrebbero collidere con un'altra integrazione di Sheets nello stesso
profilo. Un prefisso `BUDGET_` lo eviterebbe, ma romperebbe la regola di SPEC-01 e il rename
di `GOOGLE_SHEET_NAME`, già documentato e usato. Rischio accettato, da ricontrollare quando si
aggiunge un'integrazione Google al profilo: chi installa vede comunque il `.env` intero.

### `HERMES_HOME` e non la posizione del plugin

> **Rivista da [SPEC-07](07-profilo-dalla-posizione-del-plugin.md).** In produzione
> `HERMES_HOME` non puntava al profilo, e token e credenziali non si trovavano più.

`PROFILE_DIR` si potrebbe ricavare da `__file__`, perché il plugin vive in
`<profilo>/plugins/<nome>`. Sarebbe esatto in produzione e sbagliato ovunque altrove: un
checkout di sviluppo, i test. `HERMES_HOME` è la variabile che Hermes stesso imposta e legge.

### Limite: un profilo per processo

Un processo Hermes che serve più profili li distingue per richiesta, con una ContextVar che
deliberatamente non tocca `os.environ`. Le costanti di questo modulo si fissano all'import,
quindi in quel caso vedrebbero un profilo solo. Oggi ogni istanza è un processo suo, ed è il
caso che questo spec serve. Leggere la configurazione a ogni turno lo risolverebbe, al prezzo
di toccare ogni lettura delle costanti: è un altro cambiamento.

### La suite ha un profilo suo, assegnato

`HERMES_HOME` in `percorsi.py` è un'assegnazione e non un `setdefault`, al contrario di
`ANNO_BUDGET`. Sul server `HERMES_HOME` è già impostato, e con `setdefault` la suite leggerebbe
il `.env`, il token e la bozza veri. Per l'anno vale il contrario: sovrascriverlo dall'esterno
è una prova utile, e innocua.
