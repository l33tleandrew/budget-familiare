---
name: budget-familiare-workflow
description: Registra una transazione economica (spesa o entrata) nel foglio Budget su Google Sheets tramite budget_sheets.py. Usa questa skill ogni volta che l'utente menziona una spesa, un pagamento, un acquisto, un incasso, un rimborso o un versamento — a voce, per iscritto o mandando la foto di uno scontrino — anche se non chiede esplicitamente di registrarla e anche se il messaggio è breve tipo "benzina 50" o "cena fuori 30" o "8,5". Attivala anche per messaggi che contengono solo una cifra e un contesto di acquisto.
---

# Registra transazione nel foglio Budget

Lo script conduce il dialogo e ne conserva lo stato: tu estrai quello che capisci
dal messaggio, poi fai da tramite fra lui e l'utente. Una transazione per messaggio.

## Cosa fai

1. Chiama lo script con i campi che riesci a estrarre, anche pochi o nessuno.
2. Stampa `messaggio` **parola per parola**, senza aggiungere niente.
3. Gira la risposta dell'utente con `--risposta`, e basta.
4. Ripeti finché `stato` inizia per `chiedi_`. Quando cambia, hai finito: stampa
   `messaggio` e fermati.

Non ti serve ricordare i campi già raccolti, né ripassarli: li tiene lo script.

## Le chiamate

```bash
SCRIPT=/opt/data/profiles/budgetingagent/skills/budget-familiare-workflow/scripts/budget_sheets.py

# primo turno di ogni nuova transazione: --nuova e quello che hai estratto
/opt/hermes/.venv/bin/python $SCRIPT append --nuova \
  --importo 30.00 --categoria "Cibo fuori / bevute" \
  --descrizione "Trattoria da Nino, cena con Marco" --note ""

# ogni turno dopo: solo quello che ha scritto l'utente, testuale
/opt/hermes/.venv/bin/python $SCRIPT append --risposta "5"
/opt/hermes/.venv/bin/python $SCRIPT append --risposta "sì"

# l'utente corregge un campo fuori turno: passa solo quel campo
/opt/hermes/.venv/bin/python $SCRIPT append --importo 40.00

# l'utente lascia perdere
/opt/hermes/.venv/bin/python $SCRIPT append --annulla
```

`--nuova` va sempre al primo turno: senza, la nuova spesa si fonde con quella di
prima. Categoria e sottocategoria accettano il nome o il numero: passa quello che
ha scritto l'utente, non tradurlo.

## Cosa estrai dal messaggio

**Importo** — obbligatorio. Passa il punto decimale. Un punto senza virgola lo
script lo legge sempre come decimale, quindi le migliaia normalizzale tu:

| Nel messaggio | Da passare | |
| --- | --- | --- |
| `12,50` | `12.50` | la virgola italiana è sempre decimale |
| `1.500` | `1500.00` | punto + 3 cifre: migliaia (tale e quale diventa `1.5`) |
| `1.200,00` | `1200.00` | entrambi: l'ultimo è il decimale |

Niente simboli di valuta. Il foglio è in euro e l'importo arriva già convertito:
nessun cambio, mai. Se nel messaggio non c'è una cifra, non dedurla: chiamalo
lo stesso e lascia che te la chieda lo script.

**Data** — passala **solo** se il messaggio ne indica una; altrimenti ometti il
flag e lo script mette oggi. Formato `gg/mm/aaaa` con gli zeri davanti. Risolvi
sempre con `date`, mai a memoria:

```bash
date -d yesterday +%d/%m/%Y        # ieri
date -d 'last monday' +%d/%m/%Y    # lunedì scorso
date -d '2026-09-12' +%d/%m/%Y     # una data precisa
```

Su una foto di scontrino vince la data stampata, se leggibile.

**Descrizione** — sintetica, con quello che c'è nel messaggio: il posto, cosa è
stato comprato, con chi, l'occasione — quel che serve a riconoscere la spesa fra
sei mesi. Se il messaggio non dice niente di tutto questo lasciala vuota; non
riempirla ripetendo la categoria. Si decide qui, una volta sola: non chiederla mai.

**Categoria e sottocategoria** — tentale se ti sembrano ovvie, anche senza
azzeccarle: se non combaciano te le fa scegliere lo script. Non inventarne di
nuove. Se non hai idea, ometti i flag.

**Note** — sempre `""`.

## Come rispondi

`messaggio` è già completo: contiene l'elenco numerato quando serve e il riepilogo
per intero. Stampalo e basta — niente introduzioni, niente riformulazioni, niente
domande tue, e mai un elenco ricostruito a memoria. Poi aspetta.

## Quoting

Campi liberi sempre fra virgolette doppie, anche vuoti; `--importo` senza. Da
descrizione e note togli prima i caratteri `"`, ```, `$` e `\`, che romperebbero
il comando. Gli apostrofi vanno benissimo, l'italiano ne è pieno.
