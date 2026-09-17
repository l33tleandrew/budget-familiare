#!/usr/bin/env python3
"""Eval avversariale: il modello peggiore possibile deve arrivare lo stesso in fondo.

eval_protocollo.py verifica che il protocollo funzioni quando lo si segue. Questo
file verifica che funzioni anche quando chi lo segue e' incapace, perche' e' li'
che la skill sbagliava davvero. Tre livelli, sugli stessi casi:

  smemorato       gia' in eval_protocollo: estrae al primo giro, poi solo
                  --risposta. E' la regressione diretta del sintomo "perde i
                  campi gia' raccolti".

  amnesia_totale  il primo giro porta solo --nuova --importo: data, categoria,
                  sottocategoria e descrizione vengono buttate via. Lo script
                  deve condurre il dialogo dal nulla e arrivare alla stessa riga
                  (la descrizione no: quella e' persa per davvero, ed e' giusto
                  che si veda).

  pappagallo      il sintomo "non mostra il messaggio esatto". All'utente finto
                  si passa SOLO payload["messaggio"]: se il numero da digitare
                  non e' gia' dentro quel testo, non riesce a rispondere e il
                  caso fallisce. L'eval non puo' leggere "opzioni" — non ce l'ha.

    python3 -m unittest tests.eval_smemorato -v
    python3 tests/eval_smemorato.py
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from eval_protocollo import (  # noqa: E402
    OGGI, ModelloSmemorato, VerificaCaso, carica_casi, genera_test, rapporto,
)

# I livelli 2 e 3 rigiocano la conversazione decidendo le risposte al volo, quindi
# hanno senso solo dove c'e' una riga di arrivo da raggiungere.
CASI_CON_RIGA = [c for c in carica_casi() if c["riga_attesa"]]


class ModelloAmnesiaTotale(ModelloSmemorato):
    """Estrae solo l'importo e butta via tutto il resto.

    E' il caso peggiore realistico: un modello che capisce che si parla di soldi
    e nient'altro. Se lo script porta a casa anche questo, lo stato del dialogo
    e' interamente suo.
    """

    nome = "amnesia_totale"

    def primo_giro(self, interpretazione):
        return ["append", "--nuova", "--importo", str(interpretazione["importo"])]


class ModelloPappagallo(ModelloAmnesiaTotale):
    """Ripete il messaggio e basta: non vede il resto del JSON.

    Parte dal minimo come l'amnesia totale, cosi' lo script fa tutte le domande
    e si puo' verificare che ogni risposta sia gia' dentro il testo mostrato.
    """

    nome = "pappagallo"


def risposta_dal_messaggio(messaggio, atteso):
    """Quello che l'utente puo' rispondere avendo davanti SOLO il messaggio.

    Cerca il nome voluto nell'elenco numerato e ne restituisce il numero. Se
    l'elenco non c'e' — perche' chi doveva mostrarlo avrebbe dovuto comporlo da
    se' — non c'e' niente da digitare e il caso fallisce, che e' il punto.
    """
    for riga in messaggio.splitlines():
        m = re.fullmatch(r"(\d+)\. (.+)", riga.strip())
        if m and m.group(2).strip().lower() == str(atteso).strip().lower():
            return m.group(1)
    return None


class UtenteCheSaCosaVuole:
    """Risponde alle domande dello script puntando alla riga attesa.

    `solo_messaggio=True` gli lascia vedere unicamente il testo mostrato: e' cosi'
    che si verifica che il testo basti da solo.
    """

    def __init__(self, caso, solo_messaggio=False):
        self.riga = caso["riga_attesa"]
        self.solo_messaggio = solo_messaggio
        self.mostrati = []

    def rispondi(self, stato, messaggio):
        self.mostrati.append(messaggio)
        if stato == "chiedi_conferma":
            return "sì"
        if stato == "chiedi_data":
            # La data giusta, non quella del caso: certi casi partono da una data
            # inesistente apposta, e ripeterla sarebbe un loop dell'utente finto.
            data = self.riga["data"]
            return OGGI if data == "OGGI" else data
        if stato == "chiedi_importo":
            return str(self.riga["importo"])
        atteso = self.riga["categoria" if stato == "chiedi_categoria" else "sottocategoria"]
        if not self.solo_messaggio:
            return str(atteso)
        numero = risposta_dal_messaggio(messaggio, atteso)
        if numero is None:
            raise AssertionError(
                f"«{atteso}» non e' nel testo mostrato: chi legge non ha un numero da "
                f"digitare e avrebbe dovuto comporre l'elenco da se'.\n--- mostrato ---\n"
                f"{messaggio}")
        return numero


def esegui_con_utente(caso, modello, solo_messaggio=False):
    """Come esegui_caso, ma le risposte le decide l'utente finto turno per turno."""
    utente = UtenteCheSaCosaVuole(caso, solo_messaggio)
    caso = dict(caso, risposte=[])

    # esegui_caso consuma caso["risposte"]: qui la lista non serve, perche'
    # l'utente decide al volo. Si rigioca a mano il ciclo con la stessa macchina.
    from eval_protocollo import MAX_GIRI, chiama_script
    import tempfile
    from unittest import mock
    import budget_sheets as bs

    scritte, stati = [], []
    tmp = tempfile.TemporaryDirectory()
    try:
        with mock.patch.object(bs, "BOZZA_FILE", os.path.join(tmp.name, "bozza.json")):
            argv = modello.primo_giro(caso["interpretazione"])
            for numero in range(MAX_GIRI):
                if numero:
                    assert argv[:2] == ["append", "--risposta"] and len(argv) == 3, \
                        f"il modello ha ripassato qualcosa: {argv}"
                giro = chiama_script(argv, scritte)
                if giro.stato == "scritto":
                    return {"riga": giro.riga, "stati": stati, "utente": utente}
                if not giro.stato.startswith("chiedi_"):
                    raise AssertionError(f"stato inatteso: {giro.stato}")
                stati.append(giro.stato)
                argv = modello.giro_successivo(utente.rispondi(giro.stato, giro.messaggio))
            raise AssertionError(f"non converge in {MAX_GIRI} giri: {stati}")
    finally:
        tmp.cleanup()


class TestSmemorato(VerificaCaso):
    """Livello 1: la regressione diretta del sintomo «perde i campi»."""
    modello = ModelloSmemorato()


class RecuperaDalDialogo(unittest.TestCase):
    """Quello che lo script sa recuperare da solo, e quello che no.

    Categoria, sottocategoria, importo e tipo si recuperano: lo script li chiede.
    Data e descrizione no, e non c'e' niente da rimproverargli — nessuno gliele
    ha dette e non puo' inventarle. La data ricade su oggi, la descrizione resta
    vuota: e' giusto che si veda a occhio nudo invece di essere saltato.
    """

    modello = None
    solo_messaggio = False

    def verifica(self, caso):
        r = esegui_con_utente(caso, self.modello(), self.solo_messaggio)
        for campo, valore in caso["riga_attesa"].items():
            if campo == "data":
                continue  # buttata via al primo giro: si veda sotto
            with self.subTest(campo=campo):
                self.assertEqual(r["riga"][campo], valore)
        self.assertEqual(r["riga"]["data"], OGGI,
                         "senza data estratta lo script deve mettere oggi")
        self.assertEqual(r["riga"]["descrizione"], "",
                         "la descrizione buttata via non si puo' recuperare: se qui "
                         "comparisse, arriverebbe da qualche stato nascosto")


class TestAmnesiaTotale(RecuperaDalDialogo):
    """Livello 2: il primo giro porta solo l'importo."""
    modello = ModelloAmnesiaTotale


class TestPappagallo(RecuperaDalDialogo):
    """Livello 3: all'utente si mostra solo `messaggio`, niente altro."""
    modello = ModelloPappagallo
    solo_messaggio = True

    def test_il_riepilogo_e_gia_nel_messaggio(self):
        """Chi mostra il testo non deve comporre niente: il riepilogo arriva
        fatto, tipo incluso — il solo campo che nessun altro puo' sapere."""
        caso = next(c for c in CASI_CON_RIGA if c["id"] == "ristorante-completo")
        r = esegui_con_utente(caso, ModelloPappagallo(), solo_messaggio=True)
        conferma = r["utente"].mostrati[-1]
        for atteso in ("Importo:", "30.00 €", "Tipo:", "Uscita",
                       "Sottocategoria: Ristorante", "Confermi?"):
            with self.subTest(atteso=atteso):
                self.assertIn(atteso, conferma)

    def test_l_elenco_numerato_e_gia_nel_messaggio(self):
        caso = next(c for c in CASI_CON_RIGA if c["id"] == "categoria-da-chiedere")
        r = esegui_con_utente(caso, ModelloPappagallo(), solo_messaggio=True)
        self.assertIn("\n3. Cibo fuori / bevute", r["utente"].mostrati[0])
        self.assertIn("\n5. Ristorante", r["utente"].mostrati[1])


genera_test(TestSmemorato)
genera_test(TestAmnesiaTotale, CASI_CON_RIGA)
genera_test(TestPappagallo, CASI_CON_RIGA)


if __name__ == "__main__":
    uscita = rapporto(ModelloSmemorato, "smemorato")
    print("\nlivelli avversariali (amnesia totale, pappagallo):")
    risultato = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestLoader().loadTestsFromNames([
            "tests.eval_smemorato.TestAmnesiaTotale",
            "tests.eval_smemorato.TestPappagallo",
        ]))
    sys.exit(uscita or (0 if risultato.wasSuccessful() else 1))
