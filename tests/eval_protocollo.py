#!/usr/bin/env python3
"""Eval deterministica della skill: rigioca le conversazioni di casi_eval.json.

Esegue il vero main() di budget_sheets.py a ogni giro — argparse, bozza, exit
code, stdout — sostituendo solo le due funzioni che parlano con Google. urlopen
e' sotto mock e solleva: se un giorno lo script provasse a raggiungere la rete
per altre vie, l'eval fallisce invece di scrivere davvero.

Quello che qui rimpiazza il modello e' ModelloSmemorato, e il punto e' proprio
che non ricorda niente: dopo il primo giro passa allo script solo il testo
dell'ultima risposta dell'utente. E' il protocollo dello schema preso alla
lettera — se la conversazione converge lo stesso, lo stato e' davvero nello
script e non nella testa di chi lo chiama.

    python3 -m unittest tests.eval_protocollo -v    # come test
    python3 tests/eval_protocollo.py                # con le trascrizioni
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from percorsi import REPO, SCRIPTS, TASSONOMIA  # noqa: E402
sys.path.insert(0, SCRIPTS)

import budget_sheets as bs  # noqa: E402

CASI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "casi_eval.json")
OGGI = datetime.now().strftime("%d/%m/%Y")
MAX_GIRI = 10
INTERVALLO_FINTO = "Transazioni 2026!A99:G99"

CAMPI_ESTRAIBILI = ("data", "importo", "categoria", "sottocategoria", "descrizione")


def carica_casi():
    with open(CASI_FILE, encoding="utf-8") as f:
        return json.load(f)["casi"]


def _atteso(valore):
    return OGGI if valore == "OGGI" else valore


class Giro:
    def __init__(self, argv, code, payload, riga):
        self.argv, self.code, self.payload, self.riga = argv, code, payload, riga

    @property
    def stato(self):
        return self.payload["stato"] if self.payload else ""

    @property
    def messaggio(self):
        return self.payload["messaggio"] if self.payload else ""


def chiama_script(argv, scritte):
    """Un giro di `budget_sheets.py append`, senza rete e senza scrittura vera."""

    def finto_append_row(token, data, tipo, categoria, sottocategoria, importo, descrizione, note):
        scritte.append({"data": data, "tipo": tipo, "categoria": categoria,
                        "sottocategoria": sottocategoria, "importo": importo,
                        "descrizione": descrizione, "note": note})
        return INTERVALLO_FINTO

    out, err, code = io.StringIO(), io.StringIO(), 0
    with mock.patch.object(sys, "argv", ["budget_sheets.py"] + argv), \
         mock.patch.object(bs, "get_access_token", return_value="token-finto"), \
         mock.patch.object(bs, "append_row", side_effect=finto_append_row), \
         mock.patch("urllib.request.urlopen",
                    side_effect=AssertionError("l'eval non deve toccare la rete")):
        try:
            with redirect_stdout(out), redirect_stderr(err):
                bs.main()
        except SystemExit as e:
            code = e.code or 0
    try:
        payload = json.loads(out.getvalue())
    except ValueError:
        payload = None
    return Giro(argv, code, payload, scritte[-1] if scritte else None)


class ModelloSmemorato:
    """Il modello che perde i campi, simulato sul serio.

    Non ha memoria: fra un giro e l'altro non conserva NIENTE. L'unica cosa che
    passa allo script e' il testo dell'ultima risposta dell'utente.

    Il vecchio eval non poteva accorgersi del problema: il suo dizionario dei
    campi noti non ne perdeva mai uno, e per di piu' sapeva a quale campo
    apparteneva ogni risposta guardando il messaggio. Due cose che il modello
    vero sbaglia, e che qui sono rese impossibili per costruzione.
    """

    nome = "smemorato"

    def primo_giro(self, interpretazione):
        argv = ["append", "--nuova"]
        for flag in CAMPI_ESTRAIBILI:
            if interpretazione.get(flag):
                argv += [f"--{flag}", str(interpretazione[flag])]
        return argv

    def giro_successivo(self, risposta_utente):
        return ["append", "--risposta", risposta_utente]  # e nient'altro. Mai.


def esegui_caso(caso, modello=None, verifica_amnesia=None):
    """Rigioca una conversazione. `verifica_amnesia` riceve (giro, argv) e puo'
    sollevare: e' li' che si controlla che il modello non stia barando."""
    modello = modello or ModelloSmemorato()
    risposte = list(caso["risposte"])
    stati, trascrizione, scritte = [], [], []
    riga = esito = None
    visti = set()

    tmp = tempfile.TemporaryDirectory()
    try:
        with mock.patch.object(bs, "BOZZA_FILE", os.path.join(tmp.name, "bozza.json")):
            trascrizione.append(("utente", caso["messaggio"]))
            argv = modello.primo_giro(caso["interpretazione"])

            for numero in range(MAX_GIRI):
                if verifica_amnesia:
                    verifica_amnesia(numero, argv)
                giro = chiama_script(argv, scritte)

                if giro.stato == "scritto":
                    riga, esito = giro.riga, "scritta"
                    trascrizione.append(("scritta", giro.messaggio.splitlines()[0]))
                    break
                if not giro.stato.startswith("chiedi_"):
                    esito = "errore"
                    trascrizione.append(("errore", f"{giro.stato} (exit {giro.code})"))
                    break

                stati.append(giro.stato)
                trascrizione.append(("script", giro.messaggio))

                impronta = (giro.stato, giro.payload["importo"], giro.payload["categoria"],
                            giro.payload["sottocategoria"], len(risposte))
                if impronta in visti:
                    esito = "loop"
                    trascrizione.append(("loop", "stesso stato, stessa domanda: non si esce"))
                    break
                visti.add(impronta)

                if not risposte:
                    esito = "non_scritta"
                    trascrizione.append(("fine", "l'utente non ha risposto: niente scrittura"))
                    break
                risposta = risposte.pop(0)
                trascrizione.append(("utente", risposta))
                argv = modello.giro_successivo(risposta)
            else:
                esito = "loop"
                trascrizione.append(("loop", f"non converge in {MAX_GIRI} giri"))
    finally:
        tmp.cleanup()

    return {"stati": stati, "esito": esito, "riga": riga, "trascrizione": trascrizione}


class VerificaCaso(unittest.TestCase):
    """Le asserzioni condivise fra questo eval e quello smemorato."""

    modello = None
    controlla_stati = True
    controlla_descrizione = True

    def verifica(self, caso):
        r = esegui_caso(caso, self.modello, self.verifica_amnesia)
        if self.controlla_stati:
            self.assertEqual(r["stati"], caso["stati_attesi"],
                             "sequenza di stati diversa da quella attesa")
        self.assertEqual(r["esito"], caso["esito"])

        attesa = caso["riga_attesa"]
        if attesa is None:
            self.assertIsNone(r["riga"], "non doveva essere scritta nessuna riga")
            return
        self.assertIsNotNone(r["riga"], "la riga non e' stata scritta")
        for campo, valore in attesa.items():
            with self.subTest(campo=campo):
                self.assertEqual(r["riga"][campo], _atteso(valore))
        if self.controlla_descrizione:
            self.assertEqual(r["riga"]["descrizione"],
                             caso["interpretazione"].get("descrizione", ""),
                             "la descrizione deve arrivare intatta dal messaggio")
        self.assertEqual(r["riga"]["note"], "", "le note restano sempre vuote")

    def verifica_amnesia(self, numero, argv):
        """Dopo il primo giro non deve passare altro che la risposta: ogni flag
        in piu' sarebbe stato tornato dentro il modello."""
        if numero == 0:
            return
        self.assertEqual(argv[:2], ["append", "--risposta"], f"giro {numero}: {argv}")
        self.assertEqual(len(argv), 3, f"giro {numero}: flag di troppo in {argv}")


class TestProtocollo(VerificaCaso):
    """Un test per caso; i metodi vengono generati in fondo al modulo."""


def genera_test(classe, casi=None):
    for caso in casi or carica_casi():
        def test(self, caso=caso):
            self.verifica(caso)
        test.__doc__ = f"{caso['id']}: {caso['descrizione']}"
        setattr(classe, "test_" + caso["id"].replace("-", "_"), test)


genera_test(TestProtocollo)


def rapporto(classe=None, titolo="protocollo"):
    casi = carica_casi()
    modello = (classe or ModelloSmemorato)()
    falliti = []
    print(f"\n╭─ eval {titolo} — modello «{modello.nome}»")
    for caso in casi:
        r = esegui_caso(caso, modello)
        ok = (r["stati"] == caso["stati_attesi"] and r["esito"] == caso["esito"])
        if ok and caso["riga_attesa"]:
            ok = r["riga"] is not None and all(
                r["riga"][k] == _atteso(v) for k, v in caso["riga_attesa"].items())
        elif ok:
            ok = r["riga"] is None
        if not ok:
            falliti.append(caso["id"])
        print(f"\n{'✓' if ok else '✗'} {caso['id']}")
        print(f"  {caso['descrizione']}")
        etichette = {"utente": "utente ", "script": "script ", "scritta": "SCRITTA",
                     "errore": "ERRORE ", "loop": "LOOP   ", "fine": "FINE   "}
        for chi, testo in r["trascrizione"]:
            prima, *altre = testo.split("\n")
            print(f"    {etichette[chi]} │ {prima}")
            for riga in altre:
                print(f"            │ {riga}")
        if r["riga"]:
            v = r["riga"]
            print(f"    RIGA    │ {v['data']} | {v['tipo']} | {v['categoria']} | "
                  f"{v['sottocategoria'] or '—'} | {v['importo']} | {v['descrizione'] or '—'}")
    print("\n" + "─" * 60)
    print(f"{len(casi) - len(falliti)}/{len(casi)} casi superati"
          + (f" — falliti: {', '.join(falliti)}" if falliti else ""))
    print("nessuna riga e' finita su Google Sheets: append_row e urlopen erano sostituite")
    return 1 if falliti else 0


if __name__ == "__main__":
    sys.exit(rapporto())
