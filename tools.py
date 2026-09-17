"""L'handler del tool, e la cassetta da cui `transform_llm_output` ripesca il testo."""
import json
import threading

from . import budget_sheets
from .schemas import CAMPI_TOOL

# Il messaggio dell'ultimo turno, per sessione. Lo deposita l'handler e lo
# ritira `transform_llm_output`, che lo usa come risposta finale: e' cosi' che il
# testo mostrato all'utente e' quello composto dallo script, e non una parafrasi.
#
# Sta in memoria e non in ctx.state di proposito: vale per un turno solo, e uno
# stato che deve morire subito e' meglio che non sopravviva a un riavvio.
_ULTIMO = {}
_ULTIMO_LOCK = threading.Lock()


def deposita(session_id, messaggio):
    with _ULTIMO_LOCK:
        _ULTIMO[session_id] = messaggio


def ritira(session_id):
    """Il messaggio del turno, una volta sola. None se il turno non ha registrato nulla."""
    with _ULTIMO_LOCK:
        return _ULTIMO.pop(session_id, None)


def dimentica(session_id):
    ritira(session_id)


def registra_transazione(args, **kwargs):
    """Un turno di dialogo.

    Ritorna sempre una stringa JSON e non solleva mai: sono due delle tre regole
    degli handler di Hermes (la terza e' il **kwargs qui sopra). Un'eccezione che
    esce di qui disabilita il tool per il resto della sessione.
    """
    args = args if isinstance(args, dict) else {}
    try:
        campi = {c: args[c] for c in CAMPI_TOOL if args.get(c) is not None}
        campi["nuova"] = bool(args.get("nuova", False))
        payload = budget_sheets.esegui(**campi)
    except Exception as e:                       # noqa: BLE001 — vedi docstring
        return json.dumps({"errore": str(e)}, ensure_ascii=False)

    deposita(kwargs.get("session_id"), payload["messaggio"])

    # Solo stato e messaggio. `opzioni` e `intervallo` esistono nel payload per i
    # test, ma se il modello li vede prima o poi ricompone l'elenco a mano — ed e'
    # esattamente quello che tutta questa architettura serve a impedire.
    return json.dumps({"stato": payload["stato"], "messaggio": payload["messaggio"]},
                      ensure_ascii=False)
