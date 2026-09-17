#!/usr/bin/env python3
"""Eval col modello: verifica come interpreta il messaggio dell'utente.

E' il pezzo che l'eval deterministica non puo' coprire. Da' a un modello gli
artefatti veri — lo schema del tool e tassonomia.yaml — e il messaggio informale
di ogni caso, e verifica che ne ricavi i campi giusti per la prima chiamata a
`registra_transazione`. Non esegue nessun comando e non tocca Google Sheets.

I campi che il modello restituisce vengono normalizzati con le stesse funzioni
dello script, quindi il confronto risponde alla domanda giusta: la riga finirebbe
sul foglio con i valori attesi? "3" e "Cibo fuori / bevute" contano uguale, e da
quando le migliaia le scioglie lo script anche "1.500" e "1500.00". "30 €" no:
lo script lo rifiuterebbe.

Costa token a ogni esecuzione, quindi non parte senza --esegui.

    pip install anthropic
    python3 tests/eval_modello.py              # mostra cosa farebbe
    python3 tests/eval_modello.py --esegui     # esegue davvero
"""
import argparse
import concurrent.futures
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from percorsi import REPO, SCRIPTS, TASSONOMIA  # noqa: E402
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, REPO)

import budget_sheets as bs  # noqa: E402
from schemas import REGISTRA_TRANSAZIONE, TRIGGER  # noqa: E402
from eval_protocollo import carica_casi  # noqa: E402

MODELLO = os.environ.get("EVAL_MODELLO", "claude-opus-5")
OGGI = datetime.now().strftime("%d/%m/%Y")
CAMPI = ("data", "categoria", "sottocategoria", "importo", "descrizione")

FORMATO = {
    "format": {
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {
                "data": {"type": "string",
                         "description": "gg/mm/aaaa, oppure \"\" se il messaggio non indica una data"},
                "categoria": {"type": "string",
                              "description": "nome esatto o id da tassonomia.yaml, \"\" se non deducibile"},
                "sottocategoria": {"type": "string",
                                   "description": "nome esatto o id, \"\" se la categoria non ne prevede o non e' deducibile"},
                "importo": {"type": "string",
                            "description": "positivo, punto decimale, senza valuta, \"\" se assente"},
                "descrizione": {"type": "string"},
            },
            "required": list(CAMPI),
            "additionalProperties": False,
        },
    }
}

ISTRUZIONI = """Hai a disposizione il tool descritto qui sotto. Ti arriva un messaggio
dell'utente e devi decidere con quali campi lo chiameresti la PRIMA volta.

Non stai conversando: non fare domande, non immaginare le risposte dell'utente, non
eseguire comandi. Restituisci solo i campi che ricavi da questo messaggio. Un campo che
il messaggio non permette di determinare va lasciato a "": sara' lo script a chiederlo.

Oggi e' {oggi}.

--- descrizione del tool registra_transazione ---
{trigger}

--- i suoi parametri ---
{campi}

--- references/tassonomia.yaml ---
{tassonomia}"""


def leggi(percorso):
    with open(percorso, encoding="utf-8") as f:
        return f.read()


def descrizioni_dei_campi():
    """Lo schema come lo vede il modello: l'unica cosa che legge a ogni turno,
    e quindi l'artefatto vero da valutare."""
    props = REGISTRA_TRANSAZIONE["parameters"]["properties"]
    return "\n".join(f"{nome}: {p['description']}" for nome, p in props.items())


def normalizza(campo, valore):
    """Riduce il valore a quello che lo script ne farebbe. None = lo rifiuterebbe."""
    if campo == "importo":
        esito = bs.validate_importo(str(valore))
        return None if esito is False else esito
    if campo == "categoria":
        esito = bs.validate_categoria(valore)
        return None if esito is False else esito
    if campo == "data":
        # "" e la data di oggi sono equivalenti: lo schema dice di omettere il
        # campo, ma passare oggi per esteso produce la stessa riga.
        if valore in ("", OGGI):
            return ""
        return valore if bs.validate_data(valore) else None
    return valore


def confronta(caso, risposta):
    """Un verdetto per campo. La descrizione si riporta ma non fa punteggio."""
    atteso = caso["interpretazione"]
    esiti = {}
    categoria = bs.validate_categoria(risposta.get("categoria", ""))

    for campo in ("data", "importo", "categoria"):
        ottenuto = normalizza(campo, risposta.get(campo, ""))
        voluto = normalizza(campo, atteso[campo])
        esiti[campo] = (ottenuto == voluto, risposta.get(campo, ""), atteso[campo])

    # La sottocategoria ha senso solo dentro la categoria che il modello ha scelto.
    sotto = risposta.get("sottocategoria", "")
    if categoria is False:
        ok = False
    else:
        risolta = bs.validate_sottocategoria(categoria, sotto)
        voluta = bs.validate_sottocategoria(
            bs.validate_categoria(atteso["categoria"]) or "", atteso["sottocategoria"])
        ok = risolta is not False and risolta == voluta
    esiti["sottocategoria"] = (ok, sotto, atteso["sottocategoria"])
    return esiti


def interroga(client, caso, sistema):
    risposta = client.messages.create(
        model=MODELLO,
        max_tokens=16000,
        system=sistema,
        messages=[{"role": "user", "content": caso["messaggio"]}],
        output_config=FORMATO,
    )
    if risposta.stop_reason == "refusal":
        raise RuntimeError(f"il modello ha rifiutato: {risposta.stop_details}")
    testo = next(b.text for b in risposta.content if b.type == "text")
    return json.loads(testo)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--esegui", action="store_true", help="esegue davvero le chiamate al modello")
    p.add_argument("--caso", help="esegue un solo caso, per id")
    args = p.parse_args()

    casi = [c for c in carica_casi() if c["valuta_interpretazione"]]
    if args.caso:
        casi = [c for c in casi if c["id"] == args.caso]
        if not casi:
            print(f"nessun caso con id {args.caso!r}", file=sys.stderr)
            return 2

    if not args.esegui:
        print(f"Modello:  {MODELLO}   (override con EVAL_MODELLO)")
        print(f"Casi:     {len(casi)} — una chiamata ciascuno, a pagamento")
        print("Artefatti: schema del tool + tassonomia, letti dal repo")
        print("\nNiente e' stato eseguito. Per farlo davvero:")
        print("    python3 tests/eval_modello.py --esegui")
        return 0

    try:
        import anthropic
    except ImportError:
        print("serve l'SDK ufficiale: pip install anthropic", file=sys.stderr)
        return 2

    client = anthropic.Anthropic()
    sistema = ISTRUZIONI.format(oggi=OGGI, trigger=TRIGGER,
                                campi=descrizioni_dei_campi(),
                                tassonomia=leggi(TASSONOMIA))

    def lavora(caso):
        try:
            return caso, interroga(client, caso, sistema), None
        except Exception as e:
            return caso, None, e

    risultati = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for caso, risposta, errore in pool.map(lavora, casi):
            risultati.append((caso, risposta, errore))

    superati = 0
    for caso, risposta, errore in risultati:
        if errore is not None:
            print(f"\n✗ {caso['id']}\n    ERRORE │ {errore}")
            continue
        esiti = confronta(caso, risposta)
        ok = all(v[0] for v in esiti.values())
        superati += ok
        print(f"\n{'✓' if ok else '✗'} {caso['id']}")
        print(f"    messaggio │ {caso['messaggio']}")
        for campo, (buono, ottenuto, voluto) in esiti.items():
            riga = f"    {campo:>13} │ {ottenuto or '—'}"
            if not buono:
                riga += f"   ✗ atteso: {voluto or '—'}"
            print(riga)
        print(f"    {'descrizione':>13} │ {risposta.get('descrizione') or '—'}   (non fa punteggio)")

    print(f"\n{'─' * 60}\n{superati}/{len(risultati)} casi interpretati correttamente da {MODELLO}")
    return 0 if superati == len(risultati) else 1


if __name__ == "__main__":
    sys.exit(main())
