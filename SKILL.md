---
name: budget-familiare-workflow
description: Registra una transazione economica (spesa o entrata) nel foglio Budget su Google Sheets tramite budget_sheets.py. Usa questa skill ogni volta che l'utente menziona una spesa, un pagamento, un acquisto, un incasso, un rimborso o un versamento — a voce, per iscritto o mandando la foto di uno scontrino — anche se non chiede esplicitamente di registrarla e anche se il messaggio è breve tipo "benzina 50" o "cena fuori 30". Attivala anche per messaggi che contengono solo una cifra e un contesto di acquisto.
---

# Registra transazione nel foglio Budget

Trasforma un messaggio informale in una riga del foglio `Transazioni 2026`, passando per una conferma esplicita dell'utente.

## Quando si attiva

Su **qualunque** messaggio che sembri descrivere una transazione, senza bisogno di un comando. Le fonti sono tre e sono tutte informali:

- messaggio vocale ("stamattina ho fatto benzina, cinquanta euro")
- messaggio di testo ("cena fuori 30")
- foto di uno scontrino

Si registra **una transazione per messaggio**.

## Flusso

1. **Leggi la data odierna dal sistema:** 

  Esegui: `bash date +%d/%m/%Y`

2. **Interpreta il messaggio utente ed estrapola le informazioni:**
   
  - Individua la `Data` (default: data odierna)
  - Deduci il `Tipo` (`Entrata`/`Uscita` default: `Uscita`)
  - Leggi l' `Importo`
  - Individua la `Categoria` - (vedi tassonomia)
  - Individua la `Sottocategoria` usando la `Categoria` individuata **solo se questa ne prevede** (vedi tassonomia) altrimenti resta vuota.
  - Formula una `Descrizione` sintetica
  - `Note` rimane vuota

3. **Valida Categoria e Sottocategoria**

  Verifica che la `Categoria` individuata esista nella tassonomia e che contenga la `Sottocategoria` individuata. Se la verifica va a buon fine salta allo step 6, altrimenti prosegui.

4. **Mostra l'elenco delle categorie** 

  Presenta all'utente l'elenco **completo** e numerato delle categorie presenti nella tassonomia e fallo scegliere. Esempio:
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

  Se la `Categoria` scelta dall'utente possiede sottocategorie nella tassonomia (es. `Cibo fuori / bevute`), presenta all'utente l'elenco **completo** e numerato delle relative sottocategorie e fallo scegliere. Esempio:
  ```
  La categoria scelta è **Cibo fuori / bevute**. In che sottocategoria?
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

7. **Scrivi la transazione sul foglio e riporta l'esito**

  Usa i dati confermati e lo script `budget_sheets.py` per aggiungere la transazione sul file Google Sheet.
  
  Esempio: 
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

## Regole di classificazione

**Tassonomia chiusa.** Scegli solo tra le voci elencate più sotto. Non inventare categorie né sottocategorie. Se una transazione non trova casa, **dillo all'utente** invece di forzarla in "Altro": è così che emergono le voci mancanti.

**Entrate.** Non sono limitate a `Stipendio`. Oltre ai rimborsi, sono entrate anche `Investimento > Plusvalenza`, `Dividendi`, `Interessi maturati`.

**Valuta.** Il foglio è in euro e l'utente fornisce già l'importo convertito. Non fare conversioni di cambio.

**Tipo.** In assenza di indicazioni contrarie, una transazione è un'`Uscita`. Trattala come `Entrata` solo se il messaggio lo indica (incasso, rimborso, stipendio, regalo ricevuto).

## Formati

Vanno rispettati alla lettera: lo script non valida nulla e un errore di formato passa silenziosamente nel foglio.

| Campo | Formato | Esempio |
|---|---|---|
| `--data` | `gg/mm/aaaa` | `01/09/2026` |
| `--tipo` | `Entrata` o `Uscita` | `Uscita` |
| `--importo` | numero **positivo**, punto decimale | `40.30` (mai `40,30`, mai `-40.30`) |
| `--categoria` | esatta come in tassonomia | `Cibo fuori / bevute` |
| `--sottocategoria` | esatta, o `""` se non prevista | `Ristorante` |
| `--descrizione` | testo libero, o `""` | `Trattoria da Nino, cena con Marco` |
| `--note` | **sempre** `""` | `""` |

**Data.** Se il messaggio non indica quando, usa **oggi** — e prendila dal sistema con `date +%d/%m/%Y`, mai dalla memoria. Se indica un momento passato ("ieri", "lunedì scorso", "il 12"), calcola quella data partendo dalla data di oggi. Su una foto di scontrino, usa la data stampata sullo scontrino se leggibile.

**Importo.** Sempre positivo: il segno lo porta la colonna `Tipo`, non il numero. La virgola italiana è sempre decimale (`12,50` → `12.50`); un punto seguito da tre cifre sono migliaia (`1.500` → `1500.00`), da una o due cifre è decimale (`12.50` → `12.50`).

## Descrizione

Componila con quello che c'è nel messaggio, senza mai chiedere altro. Mettici, quando disponibili: il posto o il negozio, il viaggio o l'occasione, cosa è stato comprato, con chi, e qualunque contesto utile a riconoscere la spesa tra sei mesi.

Se il messaggio non contiene nulla di tutto questo, **lasciala vuota**. Non riempirla ripetendo la categoria: è informazione già presente nella colonna accanto.

La descrizione è particolarmente importante sulle spese di viaggio: dato che tutte finiscono sotto `Viaggi`, è l'unico posto dove sopravvive l'informazione di *quale* viaggio fosse. Se l'utente nomina la destinazione, mettila lì.

## Comando

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

**Quoting.** Campi liberi sempre fra virgolette doppie. Da descrizione e note togli prima i caratteri `"`, `` ` ``, `$` e `\`, che romperebbero il comando; gli apostrofi vanno benissimo, l'italiano ne è pieno. Sottocategoria assente = `""`.

**Successo.** Lo script stampa `OK:` seguito dall'intervallo aggiornato, per esempio `OK:Transazioni 2026!A42:G42`. Riporta all'utente il numero di riga in una riga sola: gli permette di correggere a mano in tre secondi.

**Se l'output non inizia con `OK:`, non dire che hai registrato.** Riprova **una volta sola**, poi fermati e mostra all'utente il comando completo già pronto, così può lanciarlo lui. Una precisazione che conta: un errore di autenticazione (`ERRORE autenticazione`) avviene *prima* di qualunque scrittura, quindi ritentare è sicuro. Se invece l'errore arriva dopo la chiamata a Google e non capisci se la riga sia passata o no, **non ritentare**: fai controllare il foglio, perché un secondo append creerebbe un duplicato che nessuno noterà più.

## Tassonomia

Le categorie senza sottocategorie elencate lasciano `--sottocategoria ""`.

| Categoria | Sottocategorie |
|---|---|
| Stipendio | *nessuna* |
| Supermercato | *nessuna* |
| Cibo fuori / bevute | Asporto · Bar · Da amici · Fast food · Ristorante · Bevuta · Altro |
| Auto / Moto | Benzina · Bollo · Assicurazione · Parcheggio · Pedaggio · Autolavaggio · Riparazione · Multa |
| Sport | Palestra · Piscina · Padel · Altro |
| Casa | Rata condominiale · Bolletta Internet · Bolletta elettrica · Rata mutuo · TARI · Manutenzione/Riparazione · Oggettistica · Altro |
| Abbigliamento | *nessuna* |
| Abbonamenti | Spotify · Amazon Prime · Disney Plus · Netflix · Altro |
| Divertimento | *nessuna* |
| Investimento | Tasse · PAC · Plusvalenza · Minusvalenza · Interessi maturati · Commissioni · Dividendi · Altro |
| Regali | Compleanno · Natale · Anniversario · San Valentino · Matrimonio · Altro |
| Viaggi | Voli · Alloggio · Cibo fuori · Supermercato · Mezzi pubblici · Auto · Divertimento · Altro |
| Cura / Benessere | Taglio capelli · Estetista · Altro |
| Trasporto pubblico | Abbonamento · Biglietto singolo · Sharing · Altro |
| Salute | Medicine · Visita specialistica · Analisi · Altro |
| Cultura | *nessuna* |
| Beneficienza | *nessuna* |
