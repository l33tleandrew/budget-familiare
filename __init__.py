"""budget-familiare — registra spese ed entrate sul foglio Budget.

`budget_sheets.py` e' gia' una macchina a stati: stato su disco con TTL, lock,
marcatore anti-doppione, validazione, e i messaggi all'utente composti
interamente in Python. Il non-determinismo non
stava li' dentro, stava nel modo in cui ci si arrivava — il modello shellava un
comando, decideva lui l'instradamento, e il testo che l'utente leggeva era una
sua parafrasi.

Questo plugin toglie al modello tutto quello che non e' comprensione del
linguaggio, una superficie per volta:

  register_tool          la shell — argomenti tipizzati, niente quoting
  tool_request           l'instradamento — `nuova` si legge dal disco
  pre_llm_call           la memoria — lo stato reale reiniettato ogni turno
  transform_llm_output   la parafrasi — la risposta finale e' il testo dello script
  pre_tool_call          le scorciatoie — una sola strada per arrivare al foglio

Quello che resta al modello e' l'unica cosa che sa fare meglio del codice:
capire che "benzina 50" e' una spesa, e tirarne fuori i campi.
"""
from . import budget_sheets, tools
from .schemas import REGISTRA_TRANSAZIONE


def forza_instradamento(**kwargs):
    """Deriva `nuova` dalla bozza su disco, scartando quello che ha deciso il modello.

    E' la sorgente di errore piu' cara delle cinque: se il modello dimentica
    `nuova` la spesa nuova si fonde con quella di prima, se lo mette di troppo
    butta via un dialogo a meta'. Ed e' una decisione che non richiede giudizio —
    se c'e' una bozza aperta il turno e' una continuazione, sempre.

    Il middleware `tool_request` gira prima di availability check, guardrail,
    approvazioni ed esecuzione, quindi e' un vincolo vero e non un suggerimento.
    """
    if kwargs.get("tool_name") != "registra_transazione":
        return None
    args = dict(kwargs.get("args") or {})
    args["nuova"] = not budget_sheets.in_dialogo()
    return {"args": args, "source": "budget-familiare",
            "reason": "instradamento derivato dalla bozza su disco"}


def inietta_stato(**kwargs):
    """Ricorda al modello che c'e' una transazione aperta. Dal file, non dalla sessione.

    Sopravvive alla compressione del contesto, che e' il modo tipico in cui un
    dialogo a meta' si perde. Si inietta un'istruzione, non i campi raccolti:
    darglieli in pasto sarebbe un invito a ricomporre a mano il riepilogo che lo
    script compone gia' per intero.
    """
    if not budget_sheets.in_dialogo():
        return None
    return {"context": (
        "C'è una transazione a metà: l'ultima domanda di registra_transazione "
        "aspetta risposta. Richiamalo passando in `risposta` quello che ha appena "
        "scritto l'utente, testuale. Non ricominciare da capo, non ricostruire "
        "l'elenco delle categorie e non riassumere: ci pensa il tool."
    )}


def blocca_scorciatoie(tool_name=None, args=None, **kwargs):
    """Una sola strada per arrivare al foglio.

    Lo script resta eseguibile a mano da un terminale umano — e' una CLI e
    continua a funzionare come tale. Quello che non deve succedere e' che ci
    arrivi l'agente: shellandolo si salterebbero middleware e hook, cioe'
    esattamente i vincoli che questo plugin esiste per imporre.
    """
    if tool_name != "terminal":
        return None
    comando = str((args or {}).get("command", ""))
    if "budget_sheets" not in comando:
        return None
    return {"action": "block", "message": (
        "Per registrare una transazione usa il tool registra_transazione, non il "
        "terminale: lo script da solo salta i controlli sullo stato del dialogo."
    )}


def resa_verbatim(**kwargs):
    """La risposta finale del turno e' il messaggio composto dallo script.

    `transform_llm_output` scatta una volta per turno, a ciclo dei tool concluso,
    e la prima stringa non vuota sostituisce la risposta. Se il turno non ha
    chiamato il tool la cassetta e' vuota, si ritorna None e Hermes si comporta
    come sempre — niente platform handler, niente rischio di mangiarsi i flussi
    core (approvazioni, selettore modello, prompt di chiarimento).

    E' l'unico punto in cui "stampa il messaggio parola per parola" smette di
    essere una richiesta al modello e diventa un fatto.
    """
    return tools.ritira(kwargs.get("session_id"))


def pulisci(**kwargs):
    """Se un turno deposita un messaggio e transform_llm_output non scatta — un
    errore a meta' strada — quel messaggio non deve ricomparire tre turni dopo."""
    tools.dimentica(kwargs.get("session_id"))


def register(ctx):
    ctx.register_tool(
        name="registra_transazione",
        toolset="budget",
        schema=REGISTRA_TRANSAZIONE,
        handler=tools.registra_transazione,
    )

    ctx.register_middleware("tool_request", forza_instradamento)

    ctx.register_hook("pre_llm_call", inietta_stato)
    ctx.register_hook("pre_tool_call", blocca_scorciatoie)
    ctx.register_hook("transform_llm_output", resa_verbatim)
    ctx.register_hook("on_session_end", pulisci)

    def spesa(args="", **kwargs):
        """L'innesco esplicito per quando il messaggio e' troppo scarno perche' il
        trigger scatti da solo. L'estrazione dei campi resta al modello: e' la
        parte che sa fare, e farla qui con una regex sarebbe un passo indietro."""
        testo = (args or "").strip()
        ctx.inject_message(
            f"Registra questa transazione: {testo}" if testo
            else "Registra una transazione."
        )

    ctx.register_command(
        "spesa", spesa,
        description="Registra una spesa o un'entrata nel foglio Budget",
        args_hint="[testo della spesa]",
    )
