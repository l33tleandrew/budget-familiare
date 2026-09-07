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

## Campi obbligatori

Senza questi non si scrive:

1. `Data` — (default: data odierna)
2. `Tipo` — `Entrata` o `Uscita` (default: `Uscita`)
3. `Importo`
4. `Categoria` - (vedi tassonomia)
5. `Sottocategoria` — **solo se la categoria ne prevede** (vedi tassonomia). Dove la categoria non ne ha, resta vuota.

`Descrizione` e `Note` non sono obbligatori e **non vanno mai chiesti all'utente**.

## Flusso

1. **Leggi la data odierna dal sistema** eseguendo `date +%d/%m/%Y` col tool `terminal`. Sempre, prima di interpretare il messaggio.
2. **Interpreta** il messaggio ed estrai i campi validando la coppia categoria/sottocategoria con la tassonomia. Se contiene già tutti i campi obbligatori, si chiede conferma e si va dritti al punto 4. I passaggi 2 e 3 esistono per l'incertezza reale.
3. **Se `Categoria` non è determinabile con certezza**: presenta all'utente l'elenco **completo** delle categorie e fagli scegliere. Non proporre una rosa ristretta di 2-3.
4. **Se la `Categoria` prevede sottocategorie e quella giusta non è determinabile con certezza**: presenta le sottocategorie di quella categoria e fagli scegliere. Non proporre una rosa ristretta di 2-3.
5. **Mostra la riga completa e aspetta l'ok.** Sempre, senza eccezioni, anche quando tutto è ovvio.
6. **Scrivi** con `budget_sheets.py append` e riporta l'esito.


## Contesto tecnico

Tutte le coordinate per scrivere davvero sul foglio.

| | |
|---|---|
| **Interprete Python** | `/opt/hermes/.venv/bin/python` |
| **Script** | `/opt/data/profiles/budgetingagent/scripts/budget_sheets.py` |
| **Cartella profilo** | `/opt/data/profiles/budgetingagent` |
| **Token OAuth** | `/opt/data/profiles/budgetingagent/google_token.json` |
| **Client secret** | `/opt/data/profiles/budgetingagent/google_client_secret.json` |
| **Spreadsheet ID** | `1iDYzjzyu_du_axBmzOzI6k4DrzV2Y52_UZTFMtM6JB0` |
| **Foglio target** | `Transazioni 2026` (sheet ID `1689336980`) |
| **Foglio categorie** | `Categorie` (colonna A = categoria, colonna B = sottocategoria) |
| **Colonne, in quest'ordine** | `Data \| Tipo \| Categoria \| Sottocategoria \| Importo (€) \| Descrizione \| Note` |
| **Link al foglio** | `https://docs.google.com/spreadsheets/d/1iDYzjzyu_du_axBmzOzI6k4DrzV2Y52_UZTFMtM6JB0/edit` |

Le credenziali le gestisce lo script da solo: rinfresca l'access token partendo dal refresh token e non richiede nessun intervento. Non leggere né scrivere quei due file a mano.

Lo script espone **solo** `append` e `read-categories`. Non può leggere le transazioni già registrate: a domande come "quanto ho speso a settembre?" non rispondere con cifre — non le hai, e stimarle è peggio di non rispondere. Passa la palla al foglio con il link qui sopra.

`append` scrive sempre in fondo e non modifica mai righe esistenti. Una riga sbagliata si corregge solo a mano nel foglio: per questo la conferma prima di scrivere non è opzionale.

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

La lettura delle categorie, se ti serve verificare la lista corrente:

```bash
/opt/hermes/.venv/bin/python /opt/data/profiles/budgetingagent/scripts/budget_sheets.py read-categories
```

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

Se una spesa auto non rientra in nessuna delle otto, non forzarla: presenta l'elenco all'utente e fallo scegliere.
