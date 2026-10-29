# SPEC-06 — Consenso OAuth incluso nel plugin

**Stato:** fatto · **Dipende da:** [SPEC-05](05-configurazione-per-istanza.md) ·
**Comportamento:** nuovo script, nessun cambiamento al dialogo

---

## Problema

Con [SPEC-05](05-configurazione-per-istanza.md) il plugin si installa su qualunque istanza,
ma un'istanza nuova non ha un token Google, e il plugin non ha modo di procurarselo.

- Il messaggio di `invalid_grant` in `_do_refresh` rimandava a «il flusso `setup.py`»: nel
  repo non c'è. È quello della skill google-workspace di Hermes, che usa gli stessi nomi di
  file nel profilo.
- Quello script chiede **Gmail, Drive, Calendar, Contatti, Documenti e Fogli**, mentre
  [`privacy.md`](../privacy.md) dichiara il solo `spreadsheets`. Per un'app che chiede la
  verifica di Google con quella privacy policy, non è un dettaglio.
- Anche a token ottenuto non c'era modo di sapere se l'installazione regge — id del foglio,
  scheda, accesso dell'account — senza registrare una spesa vera.

---

## Comportamento richiesto

1. Il plugin porta con sé il primo consenso, **con il solo scope `spreadsheets`**.
2. Il consenso funziona su un **server senza browser**.
3. Il token scritto è nel formato che il motore legge già: nessuna modifica allo strato auth.
4. Un token già presente nel profilo **non si sostituisce in silenzio**.
5. Una **verifica** dice se l'istanza è pronta, senza scrivere sul foglio.

---

## Progettazione

`setup_google.py`, alla radice del plugin, solo stdlib. Importa `budget_sheets` per costanti
e helper (`CRED_FILE`, `TOKEN_FILE`, `_load_creds`, `get_access_token`, `_api_request`,
`configurazione_mancante`, `anno_disallineato`): un posto solo per i percorsi.

```
python3 setup_google.py url
python3 setup_google.py codice "<indirizzo>" [--force]
python3 setup_google.py verifica
```

### `url`

Authorization code con **PKCE S256** e `state`, redirect `http://localhost:1`,
`access_type=offline`, `prompt=consent`. Il verifier e lo `state` restano in
`<PROFILE_DIR>/budget_oauth_pending.json`, scritto atomico e `0600` come la bozza. Il client
deve essere «App desktop» (chiave `installed` nel JSON): un client web non accetta il
loopback, e Google lo direbbe solo dopo il consenso.

### `codice`

Accetta l'indirizzo intero o il solo codice. Nell'ordine:

1. se `google_token.json` esiste e manca `--force`, si ferma **prima della rete**, perché il
   codice vale una volta sola;
2. verifica lo `state`, se c'è;
3. scambia il codice;
4. controlla che lo scope concesso contenga `spreadsheets`, e che ci sia un `refresh_token`;
5. scrive `{access_token, refresh_token, expires_at}`, atomico e `0600`, e cancella il
   consenso in corso.

### `verifica`

Una riga per controllo, con exit 0 se passano tutti. Si ferma dove i successivi non hanno
senso:

```
✓ configurazione in /opt/data/profiles/<p>: foglio e anno impostati
✓ client OAuth: …/google_client_secret.json
✓ token: …/google_token.json
✓ accesso a Google: token valido
✓ foglio: «Budget famiglia»
✓ scheda «Transazioni 2026»: c'e'
✓ anno: ANNO_BUDGET=2026, anno civile 2026
```

Il foglio si legge con
`GET spreadsheets/{id}?fields=properties.title,sheets.properties.title`: titolo e nomi delle
schede, nessun valore di cella.

### Ritocchi

- Il messaggio di `invalid_grant` rimanda a `setup_google.py url` e a `codice --force`.
- [`privacy.md`](../privacy.md): la verifica legge titolo e nomi delle schede, e il consenso
  in corso è un file nel profilo che sparisce a consenso finito.

---

## Fuori scope

- **Creare il foglio o la scheda.** Sarebbe una scrittura sulla struttura del documento, con
  i suoi permessi e i suoi modi di fallire. La verifica dice che manca; crearla resta a chi
  installa.
- **Un token separato per il plugin**, per non condividere il file con la skill
  google-workspace. Vedi Decisioni.
- **Il blocco `oauth:` nativo di Hermes.** Vedi Decisioni.

---

## Criteri di accettazione

- [x] L'URL chiede il solo scope `spreadsheets`, con PKCE S256, `state`, `access_type=offline`
- [x] Il consenso in corso e il token sono file `0600`, anche quando il token ne sostituisce
      uno con permessi diversi
- [x] Il token scritto lo usa `get_access_token()` così com'è, senza rinnovarlo
- [x] `state` sbagliato, consenso negato, scope non concesso, `refresh_token` assente: errore
      che dice cosa fare, e nessun token scritto
- [x] Token esistente senza `--force`: rifiuto **senza chiamare Google**; con `--force`, lo
      sostituisce
- [x] `verifica` fa una sola `GET` con `fields=` limitato a titolo e schede, e non chiama
      Google se manca configurazione o token
- [x] Client non desktop rifiutato già a `url`
- [x] `make test` verde: 300 → **329**, tutto sotto mock

---

## Test

`tests/test_setup_google.py`, sullo stile di `TestAuth`: profilo finto in una tmpdir per ogni
test, `urlopen` sempre sotto mock, tre prove della CLI vera in un profilo vuoto, che non
arrivano mai alla rete.

---

## Verifica

```bash
make test

# a occhio, con un client finto: scope, challenge, redirect
P=$(mktemp -d)
echo '{"installed":{"client_id":"123-abc.apps.googleusercontent.com","client_secret":"x"}}' \
  > $P/google_client_secret.json
HERMES_HOME=$P python3 setup_google.py url
ls -l $P                                    # budget_oauth_pending.json  -rw-------
HERMES_HOME=$P python3 setup_google.py verifica; echo "exit: $?"   # ✗ configurazione, ✗ token: 1
rm -rf $P
```

**Sull'istanza attuale** basta `verifica`: il token esistente vale così com'è, anche se è
stato creato con più scope.

```bash
HERMES_HOME=/opt/data/profiles/budgetingagent \
  python3 /opt/data/profiles/budgetingagent/plugins/budget-familiare/setup_google.py verifica
```

**Prova generale di un'istanza nuova**, prima di farlo davvero altrove. Sullo stesso server:

1. crea un profilo usa-e-getta (`hermes -p prova`) e un foglio di prova su un altro account
   Google;
2. segui il README, da «Su un'istanza nuova» in poi;
3. una `/spesa` deve finire sul foglio di prova, e nessuna su quello vero.

---

## Decisioni e alternative scartate

### Uno script nel plugin, e non il `setup.py` di google-workspace

È la strada a costo zero: lo script c'è già, fa PKCE, funziona senza browser e scrive gli
stessi file. Contro, e hanno deciso:

- **gli scope**: sei servizi Google per un plugin che ne usa uno, contro quello che
  `privacy.md` dichiara;
- **la dipendenza**: un plugin «self-contained» che per installarsi ha bisogno di una skill
  bundled di Hermes, e del suo percorso nel profilo;
- **la deriva**: la `SKILL.md` di quella skill documenta flag (`--services`, `--format json`)
  che il suo `setup.py` su `main` non ha.

### Uno script nel plugin, e non il blocco `oauth:` di Hermes

Hermes permette a un plugin di dichiarare il proprio client OAuth nel manifest. Chi installa
fa `hermes auth add <plugin>:<id>`, Hermes conserva e rinnova il token, e il plugin chiama le
API con `credentialed_provider_request()` senza mai vederlo. È la soluzione più pulita sulla
carta. Contro:

- riscrive lo strato auth del motore e i suoi test;
- la CLI smette di funzionare fuori da Hermes;
- il login ascolta su `127.0.0.1` del server, quindi da remoto serve un tunnel SSH;
- il suggerimento sul tunnel che la guida promette non risulta nel codice.

Resta l'evoluzione naturale, se un giorno il plugin smettesse di essere anche una CLI.

### Lo stesso `google_token.json` della skill, ma mai sostituito in silenzio

Un file del plugin — `budget_google_token.json` — eviterebbe ogni collisione, ma
costringerebbe l'istanza attuale a migrare il token, e due integrazioni Google nello stesso
profilo farebbero due consensi. Con lo stesso nome:

- dove google-workspace è già configurata, il plugin funziona senza consenso: il suo token
  copre anche i fogli;
- dove non c'è, `setup_google.py` crea un token con il solo scope `spreadsheets`.

Il rischio è il caso inverso: un token stretto che sostituisce quello largo e lascia la skill
senza Gmail. Per questo `--force`, e un messaggio che dice perché.

### `http://localhost:1`

Il flusso «fuori banda» (`urn:ietf:wg:oauth:2.0:oob`), che mostrava il codice in una pagina
di Google, è stato dismesso nel 2022. Il loopback è l'unico redirect rimasto per un client
desktop. Nessun server in ascolto, di proposito: il server di Hermes non è dove sta il
browser, e una pagina che non si carica lascia il codice nella barra degli indirizzi, che è
proprio dove serve.

### La verifica legge, non scrive

L'alternativa era una riga di prova sul foglio, da cancellare a mano: è l'unico modo di
provare davvero il permesso di scrittura. Ma una riga finta nel budget di una famiglia è
esattamente il tipo di dato mal collocato che il resto del plugin si sforza di impedire, e
la `/spesa` del passo finale prova la scrittura con una riga vera. La verifica si ferma a ciò
che si può controllare leggendo il meno possibile.

### Il nome non contiene `budget_sheets`

`blocca_scorciatoie` ferma i comandi da terminale che nominano `budget_sheets`, per non far
saltare all'agente i vincoli del dialogo. `setup_google.py` non scrive righe e non tocca la
bozza, quindi non ha vincoli da saltare. L'agente può lanciarlo se chi installa preferisce
incollargli l'indirizzo in chat: il codice da solo, senza il verifier che resta sul server,
non serve a nessuno.
