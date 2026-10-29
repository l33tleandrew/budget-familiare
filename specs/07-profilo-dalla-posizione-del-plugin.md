# SPEC-07 — Il profilo dalla posizione del plugin

**Stato:** fatto · **Dipende da:** [SPEC-05](05-configurazione-per-istanza.md) ·
**Comportamento:** correzione, nessun cambiamento al dialogo

---

## Problema

Con [SPEC-05](05-configurazione-per-istanza.md) il profilo dell'istanza veniva da `HERMES_HOME`:

```python
PROFILE_DIR = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
```

Dopo il deploy il plugin non ha più trovato `google_token.json` e `google_client_secret.json`.
Prima il percorso era un letterale, `/opt/data/profiles/budgetingagent`, e non dipendeva da
come il processo era stato avviato. Ora sì, in due modi:

- **nel container** il Dockerfile imposta `HERMES_HOME=/opt/data`, anche se il plugin sta in
  `/opt/data/profiles/budgetingagent/plugins/`;
- **da una shell** (`setup_google.py`, la CLI a mano) `HERMES_HOME` di solito non c'è, e
  vale `~/.hermes`.

La suite non poteva accorgersene: `tests/percorsi.py` assegnava sempre `HERMES_HOME`, quindi
il caso «variabile assente o sbagliata» non girava mai. SPEC-05 il rischio lo nominava, al
passo 2 della migrazione, ma come verifica a mano.

---

## Comportamento richiesto

1. Il profilo è la cartella **in cui il plugin è installato**: `<profilo>/plugins/<nome>/`
   → `<profilo>`. Token, credenziali, `.env` e bozza si leggono da lì.
2. `HERMES_HOME` **non si legge**, né dentro Hermes né da una shell.
3. La suite non vede mai il profilo vero, nemmeno quando il repo è dentro il profilo vero.
4. Un checkout che non sta sotto `plugins/` non legge né scrive la cartella due livelli sopra.

---

## Progettazione

```python
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

def _profilo():
    imposto = os.environ.get("BUDGET_PROFILE_DIR")
    if imposto:
        return imposto
    plugins = os.path.dirname(PLUGIN_DIR)
    if os.path.basename(plugins) == "plugins":
        return os.path.dirname(plugins)
    return os.path.expanduser("~/.hermes")

PROFILE_DIR = _profilo()
```

`TOKEN_FILE`, `CRED_FILE`, il `.env` di `_config()`, la bozza e `budget_oauth_pending.json` di
`setup_google.py` discendono tutti da `PROFILE_DIR` e non cambiano. `TASSONOMIA_FILE` usa
`PLUGIN_DIR`.

`tests/percorsi.py` assegna `BUDGET_PROFILE_DIR` a una directory temporanea vuota, al posto
di `HERMES_HOME`.

---

## Fuori scope

- **La precedenza fra ambiente e `.env`**: resta quella di SPEC-05, prima l'ambiente.
- **Più profili nello stesso processo**: stesso limite di SPEC-05.

---

## Criteri di accettazione

- [x] `budget_sheets.py` non legge `HERMES_HOME`
- [x] Plugin in `<p>/plugins/budget-familiare`, con `HERMES_HOME` su un'altra cartella che ha
      un `.env` suo: `PROFILE_DIR` è `<p>`, il token è `<p>/google_token.json`, l'id del foglio
      viene da `<p>/.env`
- [x] `BUDGET_PROFILE_DIR` vince sulla posizione
- [x] Checkout fuori da `plugins/`: `PROFILE_DIR` è `~/.hermes`
- [x] Il test sul caso del server fallisce con il codice di SPEC-05
- [x] `make test` verde: 329 → **331**; `make eval` e `make eval-smemorato` 20/20
- [ ] Sul server: `setup_google.py verifica` mostra il profilo giusto, e una `/spesa` vera
      arriva fino alla riga sul foglio

---

## Test

In `TestConfigurazione`, che rilegge il modulo in un processo nuovo, `importa()` accetta la
cartella da cui importare lo script; `installa()` ce ne copia uno.

- **`test_il_profilo_e_quello_in_cui_il_plugin_e_installato`**: il caso del server, con
  `HERMES_HOME` su un'altra cartella che ha un `.env` con un altro id.
- **`test_budget_profile_dir_vince_sulla_posizione`**: la garanzia su cui si regge I16.
- **`test_fuori_da_un_profilo_vale_il_default_di_hermes`**: `HOME` su una tmpdir.

Le cartelle temporanee passano da `realpath`: su macOS `/var` è un link a `/private/var`, e il
percorso dello script importato arriva già risolto.

---

## Verifica

```bash
make test

# a mano, con HERMES_HOME altrove come nel container
S=$(mktemp -d); mkdir -p $S/profilo/plugins $S/altrove
rsync -a --exclude .git ./ $S/profilo/plugins/budget-familiare/
printf 'GOOGLE_SPREADSHEET_ID=x\nANNO_BUDGET=%s\n' "$(date +%Y)" > $S/profilo/.env
cd /tmp && HERMES_HOME=$S/altrove python3 $S/profilo/plugins/budget-familiare/setup_google.py verifica
# ✓ configurazione in $S/profilo, ✗ client OAuth e ✗ token in $S/profilo: exit 1
rm -rf $S
```

**Sul server**, dopo il deploy:

```bash
python3 /opt/data/profiles/budgetingagent/plugins/budget-familiare/setup_google.py verifica
```

Poi il riavvio di Hermes e una `/spesa` vera, fino alla riga sul foglio.

---

## Decisioni e alternative scartate

### La posizione del plugin e non `HERMES_HOME`

SPEC-05 aveva scelto il contrario: «sarebbe esatto in produzione e sbagliato ovunque altrove:
un checkout di sviluppo, i test». In produzione però era `HERMES_HOME` a sbagliare, e
dipendeva da chi avvia il processo. La posizione del plugin dipende solo da dove Hermes lo ha
installato, cioè dal profilo stesso. Le due obiezioni di SPEC-05 hanno ciascuna una risposta:
i test hanno `BUDGET_PROFILE_DIR`, il checkout ha il controllo su `plugins`.

### `BUDGET_PROFILE_DIR` e non più `HERMES_HOME` per i test

`HERMES_HOME` la impostano altri, Hermes e il Dockerfile: è la variabile che ha causato il
guasto. `BUDGET_PROFILE_DIR` la imposta solo chi la vuole. Non segue la regola di SPEC-01
(«la variabile porta il nome della costante»), come le due `BUDGET_BOZZA_*`: non è
configurazione, decide dove sta il `.env`, quindi non può stare dentro.

### Il controllo su `plugins`

Senza, un checkout in `~/Documents/budget-familiare` avrebbe come profilo la home, e ne
leggerebbe il `.env` e ci scriverebbe la bozza. `~/.hermes` è il profilo di default di
Hermes, ed è quello che SPEC-05 usava senza `HERMES_HOME`: sulla macchina di sviluppo il
comportamento non cambia.

### `abspath` e non `realpath`

Un plugin collegato con un symlink, `<profilo>/plugins/budget-familiare → ~/dev/budget`,
appartiene al profilo in cui sta il link. `realpath` lo risolverebbe al checkout.

### L'ambiente resta prima del `.env`

Con `HERMES_HOME` su un'altra cartella, Hermes carica nell'ambiente il `.env` di quella. Una
variabile con lo stesso nome vincerebbe su quella del profilo del plugin. È proprio il caso
utile, però: un `hermes plugins install` lanciato senza `-p` salva le risposte nel `.env` del
profilo attivo, e così continuano a valere. Cambiare la precedenza è un'altra decisione.
