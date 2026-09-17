"""Lo schema del tool. La `description` e' il trigger.

Questo file e' l'unica cosa che il modello legge a ogni turno: il tool sta nel
system prompt, e da qui decide se attivarsi e cosa passare. Il progetto aveva
anche una SKILL.md che diceva le stesse cose, ma le skill impacchettate in un
plugin non compaiono nell'index ne' in `skills_list` — erano istruzioni che
nessuno leggeva, e una seconda copia che poteva divergere da questa.

Quindi: quello che il modello deve sapere sta qui, e solo qui. Le descrizioni
dei parametri non sono documentazione, sono il prompt.
"""

TRIGGER = (
    "Registra una transazione economica (spesa o entrata) nel foglio Budget su "
    "Google Sheets. Usa questo tool ogni volta che l'utente menziona una spesa, "
    "un pagamento, un acquisto, un incasso, un rimborso o un versamento — a voce, "
    "per iscritto o mandando la foto di uno scontrino — anche se non chiede "
    "esplicitamente di registrarla e anche se il messaggio è breve tipo "
    "\"benzina 50\" o \"cena fuori 30\" o \"8,5\". Attivalo anche per messaggi che "
    "contengono solo una cifra e un contesto di acquisto, e richiamalo a ogni "
    "turno finché la transazione non è chiusa: è lui a condurre il dialogo e a "
    "ricordarsi i campi già raccolti."
)

REGISTRA_TRANSAZIONE = {
    "name": "registra_transazione",
    "description": TRIGGER,
    "parameters": {
        "type": "object",
        "properties": {
            "risposta": {
                "type": "string",
                "description": (
                    "Quello che ha scritto l'utente, testuale, quando sta "
                    "rispondendo a una domanda del turno precedente. Non "
                    "interpretarlo e non tradurlo: ci pensa il tool a capire a "
                    "quale campo appartiene."
                ),
            },
            "importo": {
                "type": "string",
                "description": (
                    "L'importo come l'ha scritto l'utente: \"12,50\", \"1.500\", "
                    "\"1.200,00\" e \"30\" vanno bene tutti così come sono. Niente "
                    "simboli di valuta. Il foglio è in euro e l'importo arriva già "
                    "convertito: nessun cambio, mai. Se nel messaggio non c'è una "
                    "cifra non dedurla — chiama lo stesso e lascia che la chieda il tool."
                ),
            },
            "data": {
                "type": "string",
                "description": (
                    "Solo se il messaggio ne indica una; altrimenti ometti e vale "
                    "oggi. Accetta sia gg/mm/aaaa sia le espressioni relative "
                    "dell'utente (\"ieri\", \"l'altro ieri\", \"lunedì scorso\") "
                    "passate così come le ha scritte. Su una foto di scontrino "
                    "vince la data stampata, se leggibile."
                ),
            },
            "categoria": {
                "type": "string",
                "description": (
                    "Nome o numero. Tentala se ti sembra ovvia, anche senza "
                    "azzeccarla: se non combacia te la fa scegliere il tool. Non "
                    "inventarne di nuove. Se non hai idea, ometti."
                ),
            },
            "sottocategoria": {
                "type": "string",
                "description": "Nome o numero, come la categoria.",
            },
            "descrizione": {
                "type": "string",
                "description": (
                    "Sintetica, con quello che c'è nel messaggio: il posto, cosa è "
                    "stato comprato, con chi, l'occasione — quel che serve a "
                    "riconoscere la spesa fra sei mesi. Se il messaggio non dice "
                    "niente di tutto questo lasciala vuota; non riempirla ripetendo "
                    "la categoria. Si decide una volta sola: non chiederla mai."
                ),
            },
            "note": {
                "type": "string",
                "description": "Sempre stringa vuota.",
            },
            "annulla": {
                "type": "boolean",
                "description": (
                    "True solo se l'utente lascia perdere la transazione in corso."
                ),
            },
        },
        "required": [],
    },
}

# I parametri che l'handler gira allo script. `nuova` non c'e' e non e' una
# dimenticanza: decidere se il turno apre una transazione nuova o ne continua una
# non e' un giudizio, e' una lettura del disco. La fa il middleware.
CAMPI_TOOL = ("risposta", "data", "importo", "categoria", "sottocategoria",
              "descrizione", "note", "annulla")
