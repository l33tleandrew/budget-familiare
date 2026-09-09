---
name: budget-familiare-workflow
description: Registra una transazione economica (spesa o entrata) nel foglio Budget su Google Sheets tramite budget_sheets.py. Usa questa skill ogni volta che l'utente menziona una spesa, un pagamento, un acquisto, un incasso, un rimborso o un versamento — a voce, per iscritto o mandando la foto di uno scontrino — anche se non chiede esplicitamente di registrarla e anche se il messaggio è breve tipo "benzina 50" o "cena fuori 30". Attivala anche per messaggi che contengono solo una cifra e un contesto di acquisto.
---

# Registra transazione nel foglio Budget

Trasforma un messaggio informale in una riga del foglio delle transazioni dell'anno di `--data`, che `budget_sheets.py` seleziona da solo, passando per una conferma esplicita dell'utente. 

## Quando si attiva

Su **qualunque** messaggio che sembri descrivere una transazione, senza bisogno di un comando. Le fonti sono tre e sono tutte informali:

- messaggio vocale ("stamattina ho fatto benzina, cinquanta euro")
- messaggio di testo ("cena fuori 30")
- foto di uno scontrino

Si registra **una transazione per messaggio**.

## Flusso

0. **Carica la tassonomia**

   Leggi `references/tassonomia.yaml`. È l'unica fonte per categorie, sottocategorie e per il `tipo` di ciascuna categoria. Non procedere a memoria: le categorie cambiano nel tempo e il file vince sempre.

1. **Leggi la data odierna dal sistema:**

   Esegui: `date +%d/%m/%Y`

2. **Interpreta il messaggio utente ed estrapola le informazioni:**

   1. Individua la `Data` (default: data odierna)
   2. Deduci il `Tipo` (`Entrata`/`Uscita` default: `Uscita`)
   3. Leggi l' `Importo`
   4. Individua la `Categoria` - (vedi `references/tassonomia.yaml`)
   5. Individua la `Sottocategoria` usando la `Categoria` individuata **solo se questa ne prevede** (vedi `references/tassonomia.yaml`) altrimenti resta vuota.
   6. Formula una `Descrizione` sintetica
   7. `Note` rimane vuota

3. **Valida Categoria e Sottocategoria**

   Verifica che la `Categoria` individuata esista nella tassonomia e che contenga la `Sottocategoria` individuata. Se la verifica va a buon fine salta allo step 6, altrimenti prosegui.

4. **Mostra l'elenco delle categorie**

   Elenca **tutte** le categorie di `references/tassonomia.yaml`, nell'ordine in cui compaiono nel file, numerate da 1, e chiudi con "Rispondi con il numero.". Esempio:
   ```
   In che categoria?
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

5. **Mostra l'elenco delle sottocategorie se previste**

   Se la categoria scelta non prevede sottocategorie nella tassonomia, lascia `--sottocategoria ""` e vai allo step 6. Altrimenti elenca **tutte** le relative sottocategorie di `references/tassonomia.yaml`, nell'ordine in cui compaiono nel file, numerate da 1, e chiudi con "Rispondi con il numero.". Esempio:
   ```
   La categoria scelta è Cibo fuori / bevute. In che sottocategoria?
   1. Asporto
   2. Bar
   3. Da amici
   4. Fast food
   5. Ristorante
   6. Bevuta
   7. Altro
   
   Rispondi con il numero.
   ```

6. **Riepiloga e chiedi conferma all'utente**

   Mostra il riepilogo delle informazioni ottenute e aspetta conferma. Sempre, senza eccezioni, anche quando tutto è ovvio. Esempio:
   ```
   Importo:        30.00 €
   Data:           01/09/2026
   Tipo:           Uscita
   Categoria:      Cibo fuori / bevute
   Sottocategoria: Ristorante
   Descrizione:    Trattoria da Nino, cena con Marco
   Note:           —
   
   Confermo?
   ```

7. **Scrivi la transazione sul foglio e riporta l'esito e il numero di riga all'utente**

   Usa i dati confermati e lo script `budget_sheets.py` per aggiungere la transazione sul file Google Sheet. Le categorie senza sottocategorie elencate lasciano `--sottocategoria ""`. Esempio: 
   ```bash
   /opt/hermes/.venv/bin/python /opt/data/profiles/budgetingagent/scripts/budget_sheets.py append \
   --data "01/09/2026" \
   --tipo "Uscita" \
   --categoria "Cibo fuori / bevute" \
   --sottocategoria "Ristorante" \
   --importo 30.00 \
   --descrizione "Trattoria da Nino, cena con Marco" \
   --note ""
   ```

## Campi
 
`budget_sheets.py` non valida nulla: un errore di formato finisce sul foglio senza
segnalazione. I formati qui sotto vanno rispettati alla lettera.
 
| Campo | Formato | Default | Esempio |
|---|---|---|---|
| `--data` | `gg/mm/aaaa` | oggi, letta dal sistema | `01/09/2026` |
| `--tipo` | `Entrata` o `Uscita` | `Uscita` | `Uscita` |
| `--importo` | positivo, punto decimale, senza valuta | nessuno: obbligatorio | `40.30` |
| `--categoria` | stringa esatta da `references/tassonomia.yaml` | nessuno | `Cibo fuori / bevute` |
| `--sottocategoria` | stringa esatta, `""` se la categoria non ne prevede | `""` | `Ristorante` |
| `--descrizione` | testo libero | `""` | `Trattoria da Nino, cena con Marco` |
| `--note` | sempre `""` | `""` | `""` |
 
### `--data`
 
Leggila dal sistema con `date +%d/%m/%Y`, mai dalla memoria. Se il messaggio indica un
momento passato ("ieri", "lunedì scorso", "il 12"), risolvilo con `date -d` a partire da
oggi invece di calcolarlo a mente: `date -d yesterday +%d/%m/%Y`, `date -d 'last monday' +%d/%m/%Y`,
`date -d '2026-09-12' +%d/%m/%Y`. Su una foto di scontrino vince la data stampata sullo scontrino,
se leggibile.
 
### `--importo`
 
Sempre positivo: il segno lo porta `--tipo`, non il numero. `-40.30` e "meno 40" si
registrano come `40.30` con `--tipo Uscita`.
 
| Nel messaggio | Regola | Sul foglio |
|---|---|---|
| `12,50` | la virgola italiana è sempre decimale | `12.50` |
| `1.500` | punto seguito da 3 cifre: migliaia | `1500.00` |
| `12.50` | punto seguito da 1 o 2 cifre: decimale | `12.50` |
| `1.200,00` | entrambi i separatori: l'ultimo è il decimale | `1200.00` |
 
Il foglio è in euro e l'utente fornisce l'importo già convertito: nessuna conversione di
cambio, in nessun caso. Se nel messaggio non c'è un importo, chiedilo e fermati: non
dedurlo dal contesto.
 
### `--tipo`
 
`Uscita` salvo indicazione contraria esplicita (incasso, rimborso, stipendio, accredito,
regalo ricevuto). Le entrate non sono solo lo stipendio: il tipo lo stabilisce la
categoria scelta, non l'intuizione. Ogni categoria in `references/tassonomia.yaml` dichiara il
proprio `tipo`, e `--tipo` deve essere coerente con quello: se non lo è, l'inferenza è
sbagliata da qualche parte e va rifatta, non forzata.
 
### `--categoria` e `--sottocategoria`
 
Tassonomia chiusa: `references/tassonomia.yaml` è l'unica fonte, e i valori si copiano carattere per
carattere. Mai inventarne di nuovi, mai tradurre, abbreviare, correggere la punteggiatura
o normalizzare le maiuscole.
 
`--sottocategoria ""` significa una cosa sola: la categoria non ne prevede. Non è il
valore da usare quando non sai quale scegliere — in quel caso mostra l'elenco.
 
### `--descrizione`
 
Componila con quello che c'è nel messaggio, senza mai chiedere altro. Mettici, quando
disponibili: il posto o il negozio, il viaggio o l'occasione, cosa è stato comprato, con
chi, e qualunque contesto utile a riconoscere la spesa fra sei mesi.
 
Se il messaggio non contiene nulla di tutto questo, lasciala vuota. Non riempirla
ripetendo la categoria: è informazione già presente nella colonna accanto.
 
### Quoting
 
Campi liberi sempre fra virgolette doppie, anche quando sono vuoti; `--importo` senza
virgolette. Da descrizione e note togli prima i caratteri `"`, `` ` ``, `$` e `\`, che
romperebbero il comando. Gli apostrofi vanno benissimo, l'italiano ne è pieno.
 
