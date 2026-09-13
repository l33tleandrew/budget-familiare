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

1. estrarre dal messaggio i campi che riesci a capire;
2. chiamare lo script, anche con campi mancanti o incerti;
3. mostrare all'utente il `messaggio` dello script, aggiungendoci i dati che lo script non
  può produrre (l'elenco numerato, il riepilogo);
4. richiamare lo script con tutto quello che sai, incluso quello appena raccolto.

Ripeti 2-4 finché lo script non risponde `OK:`. Non decidere tu quando un campo è valido,
non saltare passaggi che lo script non ha ancora superato, non scrivere mai sul foglio per
altre vie.

## Flusso



### 0. Carica la tassonomia

Leggi per intero `references/tassonomia.yaml`, accanto a questo SKILL.md. È l'unica fonte per
categorie e sottocategorie. Non procedere a memoria: le categorie cambiano nel tempo e il file
vince sempre.

### 1. Interpreta il messaggio

1. `Importo` — obbligatorio, vedi [--importo](#--importo).
2. `Categoria` e `Sottocategoria` — da `references/tassonomia.yaml`, vedi
  [--categoria e --sottocategoria](#--categoria-e---sottocategoria). Se non le capisci dal
   messaggio, lascia i campi vuoti: ci pensa lo script a chiedertele.
3. `Data` — **solo se il messaggio ne indica una**, vedi [--data](#--data). Se il messaggio non
  dice niente sulla data, ometti `--data`: lo script mette oggi da sé.
4. `Descrizione` — sintetica, dal contenuto del messaggio.
5. `Note` — sempre `""`.

Il `Tipo` (`Entrata`/`Uscita`) **non si deduce e non si passa**: lo ricava lo script dalla
tassonomia e te lo restituisce nel JSON.

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
Mostra il messaggio all'utente **con le parole esatte dello script**, seguendo la tabella qui
sotto, poi torna allo step 2 con **tutti** i campi già noti più quello appena raccolto.
- `OK:<intervallo>` su stdout (exit code `0`): la transazione è stata scritta. Riporta
l'esito e la riga all'utente e fermati.
- `ERRORE ...` su stderr (exit code `1` = autenticazione, `2` = scrittura): riportalo
all'utente così com'è e fermati. Non è un caso da ritentare in loop.


| `messaggio` dello script                 | Cosa fare                                                                                                                                                                     |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Inserire importo:`                      | Mostra la riga così com'è e aspetta la risposta.                                                                                                                              |
| `Inserire una data valida (gg/mm/aaaa):` | Mostra la riga così com'è e aspetta la risposta.                                                                                                                              |
| `Quale categoria vuoi inserire?`         | Mostra la domanda + [elenco categorie](#elenco-categorie) e aspetta il numero.                                                                                                |
| `Quale sottocategoria vuoi inserire?`    | Mostra la domanda + [elenco sottocategorie](#elenco-sottocategorie) della categoria scelta e aspetta il numero.                                                               |
| `Confermi?`                              | Mostra il [riepilogo](#riepilogo) compilato con i valori del JSON e aspetta una risposta esplicita. Sì → richiama con `--conferma "Si"`. No → richiama con `--conferma "No"`. |


Quattro regole che valgono in tutto il ciclo:

- **I valori del JSON hanno la precedenza sui tuoi.** Lo script normalizza: `3` diventa
`Cibo fuori / bevute`, `12,50` diventa `12.5`, e aggiunge `tipo`. Usa i suoi valori per il
riepilogo e per le chiamate successive.
- **Il JSON non è la tua memoria.** Quando un campo non passa la validazione, quelli dopo di lui
tornano vuoti anche se glieli avevi passati. Tieni tu traccia di tutto ciò che hai già
raccolto e ripassalo intero a ogni chiamata.
- **I numeri si passano così come sono.** Categoria e sottocategoria accettano sia il nome esatto
sia l'id numerico della tassonomia: se l'utente risponde `5`, passa `5`, non tradurlo.
- **Cambiando categoria, la sottocategoria decade.** Appena l'utente sceglie una categoria
diversa da quella che avevi passato, rimetti `--sottocategoria ""` e fattela chiedere di nuovo:
quella vecchia appartiene a un'altra categoria e ti manderebbe nel loop senza uscita.



### Elenco categorie

Numerato con l'`id` di `references/tassonomia.yaml` (non con la posizione nella lista), così il
numero che risponde l'utente si può girare allo script tale e quale. Chiudi con
"Rispondi con il numero.":

```
Quale categoria vuoi inserire?
1. Stipendio
2. Supermercato
3. Cibo fuori / bevute
4. Auto / Moto
5. Sport
6. Casa
7. Abbigliamento
8. Abbonamenti
9. Divertimento
10. Investimento
11. Regali
12. Viaggi
13. Cura / Benessere
14. Trasporto pubblico
15. Salute
16. Cultura
17. Beneficienza

Rispondi con il numero.
```



### Elenco sottocategorie

Stessa logica, con gli `id` delle sottocategorie della categoria scelta (ripartono da 1 per ogni
categoria):

```
Quale sottocategoria vuoi inserire?
La categoria scelta è Cibo fuori / bevute.
1. Asporto
2. Bar
3. Da amici
4. Fast food
5. Ristorante
6. Bevuta
7. Altro

Rispondi con il numero.
```



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
| `--categoria`      | nome esatto o id da `references/tassonomia.yaml`      | nessuno: obbligatorio    | `Cibo fuori / bevute` oppure `3`    |
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

Tassonomia chiusa: `references/tassonomia.yaml` è l'unica fonte, e i nomi si copiano carattere
per carattere. Mai inventarne di nuovi, mai tradurre, abbreviare, correggere la punteggiatura o
normalizzare le maiuscole. In alternativa al nome passa l'id numerico: è più corto e non si
sbaglia.

`--sottocategoria ""` significa una cosa sola: **la categoria non ne prevede** (in
`tassonomia.yaml` ha `sottocategorie: []`). Non è il valore da usare quando non sai quale
scegliere — in quel caso lascia vuoto e fatti fare la domanda dallo script.

⚠ Se passi una sottocategoria a una categoria che non ne prevede (per esempio `Supermercato`),
lo script chiede `Quale sottocategoria vuoi inserire?` e non c'è niente da elencare: sei in un
loop senza uscita. Quando la categoria ha `sottocategorie: []`, passa `--sottocategoria ""`.

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