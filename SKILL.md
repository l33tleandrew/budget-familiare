---
name: budget-familiare-workflow
description: Registra una transazione economica (spesa o entrata) nel foglio Budget su Google Sheets tramite budget_sheets.py. Usa questa skill ogni volta che l'utente menziona una spesa, un pagamento, un acquisto, un incasso, un rimborso o un versamento — a voce, per iscritto o mandando la foto di uno scontrino — anche se non chiede esplicitamente di registrarla e anche se il messaggio è breve tipo "benzina 50" o "cena fuori 30" o "8,5". Attivala anche per messaggi che contengono solo una cifra e un contesto di acquisto.
---

# Registra transazione nel foglio Budget

Trasforma un messaggio informale in una riga del foglio delle transazioni, passando per una
conferma esplicita dell'utente.

## Quando si attiva

Su **qualunque** messaggio che sembri descrivere una transazione, senza bisogno di un comando.
Le fonti sono tre e sono tutte informali:

- messaggio vocale ("stamattina ho fatto benzina, cinquanta euro")
- messaggio di testo ("cena fuori 30")
- foto di uno scontrino

Si registra **una transazione per messaggio**.

## Come funziona

Il comando `budget_sheets.py append` **non è solo lo scrittore: è il motore del dialogo**.
A ogni chiamata valida i campi uno alla volta — data, importo, categoria, sottocategoria,
conferma — e si ferma al primo che manca o non è conforme, restituendo un JSON con il campo
`messaggio`: è quello il testo da mostrare all'utente. Finché `messaggio` non è vuoto **non
viene scritto niente sul foglio**.

Il tuo compito è quindi solo:

1. estrarre dal messaggio i campi che riesci a capire (descrizione compresa: si decide qui,
  una volta sola — non tornarci più avanti, nemmeno alla conferma);
2. chiamare lo script, anche con campi mancanti o incerti;
3. mostrare all'utente il `messaggio` dello script **parola per parola, senza parafrasarlo e
  senza aggiungere domande tue**: se il JSON include `opzioni`, elencale numerate a partire da
  1 nell'ordine in cui arrivano, mai a memoria; per `Confermi?` componi
  tu il riepilogo (l'unica cosa che lo script non può produrre, perché include descrizione e
  note) con quello già deciso al punto 1 — non richiederle qui, è troppo tardi;
4. richiamare lo script ripassando **ogni** campo raccolto finora in questa conversazione, non
  solo quello appena arrivato — un campo dimenticato è identico, per lo script, a uno mai
  fornito, e te lo richiede da capo.

Ripeti 2-4 finché lo script non risponde `OK:`. Non decidere tu quando un campo è valido,
non saltare passaggi che lo script non ha ancora superato, non scrivere mai sul foglio per
altre vie.

## Flusso



### 1. Interpreta il messaggio

1. `Importo` — obbligatorio, vedi [--importo](#--importo).
2. `Categoria` e `Sottocategoria` — prova a indovinarle dal messaggio se ti sembra ovvio (vedi
  [--categoria e --sottocategoria](#--categoria-e---sottocategoria)); non serve che siano
   esatte, un tentativo sbagliato costa solo un giro in più. Se non hai nessuna idea, lascia i
   campi vuoti: ci pensa lo script a chiedertele con l'elenco vero.
3. `Data` — **solo se il messaggio ne indica una**, vedi [--data](#--data). Se il messaggio non
  dice niente sulla data, ometti `--data`: lo script mette oggi da sé.
4. `Descrizione` — sintetica, dal contenuto del messaggio.
5. `Note` — sempre `""`.

Il `Tipo` (`Entrata`/`Uscita`) **non si deduce e non si passa**: lo ricava lo script e te lo
restituisce nel JSON.

### 2. Chiama lo script

Chiama `append` con i campi che hai, anche se non hai validato niente e anche se ne mancano:

```bash
/opt/hermes/.venv/bin/python /opt/data/profiles/budgetingagent/skills/budget-familiare-workflow/scripts/budget_sheets.py append \
--categoria "Cibo fuori / bevute" \
--sottocategoria "Ristorante" \
--importo 30.00 \
--descrizione "Trattoria da Nino, cena con Marco" \
--note ""
```



### 3. Reagisci al `messaggio`

La risposta ha sempre una di queste forme:

- **JSON con** `"messaggio"` **non vuoto** (exit code `3`, su stdout): non è stato scritto niente.
Mostra all'utente esattamente il testo di `messaggio`, senza parafrasarlo né aggiungere domande
tue (niente extra su descrizione/note: si decidono una sola volta, al punto 1 di "Come
funziona"), seguendo la tabella qui sotto, poi torna allo step 2 con **tutti** i campi già
noti — anche quelli raccolti nei turni precedenti, non solo l'ultimo — più quello appena
raccolto.
- `OK:<intervallo>` su stdout (exit code `0`): la transazione è stata scritta. Riporta
l'esito e la riga all'utente e fermati.
- `ERRORE ...` su stderr (exit code `1` = autenticazione, `2` = scrittura): riportalo
all'utente così com'è e fermati. Non è un caso da ritentare in loop.


| `messaggio` dello script                 | Cosa fare                                                                                                                                                                     |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Inserire importo:`                      | Mostra la riga così com'è e aspetta la risposta.                                                                                                                              |
| `Inserire una data valida (gg/mm/aaaa):` | Mostra la riga così com'è e aspetta la risposta.                                                                                                                              |
| `Quale categoria? Rispondi con il numero.`      | Mostra il messaggio + [elenco categorie](#elenco-categorie) e aspetta il numero.                                                                                      |
| `Quale sottocategoria? Rispondi con il numero.` | Mostra il messaggio + [elenco sottocategorie](#elenco-sottocategorie) della categoria scelta e aspetta il numero.                                                     |
| `Confermi?`                              | Mostra il [riepilogo](#riepilogo) compilato con i valori del JSON e aspetta una risposta esplicita. Sì → richiama con `--conferma "Si"`. No → richiama con `--conferma "No"`. |


Quattro regole che valgono in tutto il ciclo:

- **I valori del JSON hanno la precedenza sui tuoi.** Lo script normalizza: `3` diventa
`Cibo fuori / bevute`, `12,50` diventa `12.5`, e aggiunge `tipo`. Usa i suoi valori per il
riepilogo e per le chiamate successive.
- **Il JSON non è la tua memoria: sei tu.** Prima di ogni chiamata, scorri i campi — data,
importo, categoria, sottocategoria, descrizione, note, conferma — e passa ogni valore che hai
già raccolto in questa conversazione, non solo quello appena arrivato, anche se l'ultima
domanda dello script riguardava un campo diverso. Un campo dimenticato è identico, per lo
script, a un campo mai fornito: te lo richiede da capo, e l'utente deve ripetersi. Quando un
campo non passa la validazione, quelli dopo di lui tornano vuoti nel JSON anche se glieli
avevi passati: è solo l'ordine in cui lo script valida, non un segnale che vadano dimenticati.
- **I numeri si passano così come sono.** Categoria e sottocategoria accettano sia il nome esatto
sia l'id numerico: se l'utente risponde `5`, passa `5`, non tradurlo.
- **Cambiando categoria, la sottocategoria decade.** Appena l'utente sceglie una categoria
diversa da quella che avevi passato, rimetti `--sottocategoria ""` e fattela chiedere di nuovo:
quella vecchia appartiene a un'altra categoria e ti manderebbe nel loop senza uscita.

**Esempio di un errore da non ripetere.** L'utente scrive "2 euro" (solo l'importo, nessuna
categoria). Lo script chiede la categoria; l'utente risponde "2" (Supermercato). La chiamata
successiva **deve** includere ancora l'importo, anche se l'ultima domanda riguardava solo la
categoria:

```bash
# sbagliato: l'importo del primo messaggio e' sparito, lo script lo richiede da capo
... append --categoria "2"

# giusto: ogni campo gia' raccolto viene ripassato, sempre
... append --importo 2 --categoria "2"
```

Se ti ritrovi a mostrare di nuovo `"Inserire importo:"` dopo che l'utente l'aveva già detto, hai
perso un campo per strada: rileggi la conversazione e recuperalo, non richiederlo come se fosse
nuovo.



### Elenco categorie

Numerato nell'ordine di `opzioni` nel JSON, così il numero scelto dall'utente si gira allo
script tale e quale. Non consultare la memoria per questo elenco: l'unica fonte è `opzioni`.

### Elenco sottocategorie

Stessa logica, con `opzioni` della categoria scelta: le sue sottocategorie, già nell'ordine
dei loro id.



### Riepilogo

Compilato con i valori del JSON — `tipo` incluso, che arriva solo da lì. Campi vuoti: `—`.

```
Importo:        30.00 €
Data:           01/09/2026
Tipo:           Uscita
Categoria:      Cibo fuori / bevute
Sottocategoria: Ristorante
Descrizione:    Trattoria da Nino, cena con Marco
Note:           —

Confermi?
```

Aspetta sempre una risposta esplicita, anche quando tutto è ovvio. Se l'utente dice di no,
richiama con `--conferma "No"`: lo script azzera categoria e sottocategoria, tiene data e
importo e riparte dalla domanda sulla categoria. Se l'utente corregge un altro campo (importo,
data, descrizione), richiama senza `--conferma` passando il valore nuovo.

## Campi

`budget_sheets.py` valida `--data`, `--importo`, `--categoria` e `--sottocategoria` prima di
scrivere: se qualcosa manca o non è conforme non scrive niente e restituisce un messaggio.
I formati qui sotto vanno comunque rispettati alla lettera, per evitare giri a vuoto nel ciclo.


| Campo              | Formato                                               | Default                  | Esempio                             |
| ------------------ | ----------------------------------------------------- | ------------------------ | ----------------------------------- |
| `--data`           | `gg/mm/aaaa`, con gli zeri davanti                    | oggi, messa dallo script | `01/09/2026`                        |
| `--importo`        | positivo, punto decimale, senza valuta                | nessuno: obbligatorio    | `40.30`                             |
| `--categoria`      | nome esatto o id (te lo conferma lo script)           | nessuno: obbligatorio    | `Cibo fuori / bevute` oppure `3`    |
| `--sottocategoria` | nome esatto o id, `""` se la categoria non ne prevede | `""`                     | `Ristorante` oppure `5`             |
| `--descrizione`    | testo libero                                          | `""`                     | `Trattoria da Nino, cena con Marco` |
| `--note`           | sempre `""`                                           | `""`                     | `""`                                |
| `--conferma`       | `Si`, `No`, oppure omesso                             | `""`                     | `Si`                                |


`--tipo` non esiste più: se lo passi, lo script si ferma con un errore di argomenti.

### `--data`

Ometti il flag quando il messaggio non indica una data: lo script usa oggi. Quando invece il
messaggio indica un momento passato ("ieri", "lunedì scorso", "il 12"), risolvilo con `date` a
partire da oggi invece di calcolarlo a mente, e mai dalla memoria:

```bash
date +%d/%m/%Y                     # oggi
date -d yesterday +%d/%m/%Y        # ieri
date -d 'last monday' +%d/%m/%Y    # lunedì scorso
date -d '2026-09-12' +%d/%m/%Y     # una data precisa
```

Su una foto di scontrino vince la data stampata sullo scontrino, se leggibile.

Il formato è rigido: giorno e mese a due cifre, anno a quattro. `1/9/2026` e `2026-09-13`
vengono rifiutati.

### `--importo`

Numero sempre positivo: `0` e i negativi vengono rifiutati come se l'importo mancasse.
Il segno lo decide il `tipo`, che dipende dalla categoria.

Normalizza tu **prima** di chiamare e passa sempre il formato inglese con il punto decimale.
Lo script accetta anche la virgola italiana, ma un punto **senza** virgola lo legge sempre come
decimale: `1.500` diventa `1.5`, non `1500`.


| Nel messaggio | Regola                                        | Da passare                                     |
| ------------- | --------------------------------------------- | ---------------------------------------------- |
| `12,50`       | la virgola italiana è sempre decimale         | `12.50`                                        |
| `12.50`       | punto seguito da 1 o 2 cifre: decimale        | `12.50`                                        |
| `1.500`       | punto seguito da 3 cifre: migliaia            | `1500.00` ⚠ passato tale e quale diventa `1.5` |
| `1.200,00`    | entrambi i separatori: l'ultimo è il decimale | `1200.00`                                      |


Niente simboli di valuta: `30 €` e `€30` vengono rifiutati. Il foglio è in euro e l'utente
fornisce l'importo già convertito: nessuna conversione di cambio, in nessun caso. Se nel
messaggio non c'è un importo, chiedilo: non dedurlo dal contesto.

### `--categoria` e `--sottocategoria`

Se scrivi un nome a naso dal messaggio, va bene un tentativo imperfetto: se non combacia, te lo
fa scegliere lo script dall'elenco (`opzioni`). Non serve indovinarlo alla perfezione, ma
nemmeno inventarne uno di sana pianta o normalizzarlo tu (maiuscole, punteggiatura,
traduzioni): o è quello giusto o lascialo decidere allo script. In alternativa al nome passa
l'id numerico ricevuto in `opzioni`: è più corto e non si sbaglia.

`--sottocategoria ""` significa una cosa sola: **la categoria non ne prevede**. Non è il
valore da usare quando non sai quale scegliere — in quel caso lascia vuoto e fatti fare la
domanda dallo script.

⚠ Se `opzioni` arriva vuota insieme a `Quale sottocategoria? Rispondi con il numero.`, la
categoria scelta non ne prevede: non c'è niente da elencare e insistere ti manda in un loop
senza uscita. Passa `--sottocategoria ""` e vai avanti.

### `--descrizione`

Componila con quello che c'è nel messaggio, senza mai chiedere altro. Mettici, quando
disponibili: il posto o il negozio, il viaggio o l'occasione, cosa è stato comprato, con chi, e
qualunque contesto utile a riconoscere la spesa fra sei mesi.

Se il messaggio non contiene nulla di tutto questo, lasciala vuota. Non riempirla ripetendo la
categoria: è informazione già presente nella colonna accanto.

### `--conferma`

Passalo solo dopo che l'utente ha risposto al riepilogo. Prima di allora ometti il flag: lo
script risponderà `Confermi?` finché non riceve esplicitamente `--conferma "Si"`, così la
scrittura non parte mai senza una conferma reale dell'utente.

### Quoting

Campi liberi sempre fra virgolette doppie, anche quando sono vuoti; `--importo` senza
virgolette. Da descrizione e note togli prima i caratteri `"`, ```, `$` e `\`, che
romperebbero il comando. Gli apostrofi vanno benissimo, l'italiano ne è pieno.