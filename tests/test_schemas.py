#!/usr/bin/env python3
"""Coerenza fra lo schema del tool, budget_sheets.py e tassonomia.yaml.

Erede di test_skill_md.py. Il criterio non e' cambiato, e' cambiato il bersaglio:
questi controlli guardavano SKILL.md, che il modello leggeva a ogni turno. Ora
SKILL.md non esiste piu' e il testo che il modello legge a ogni turno e' la
descrizione del tool — TRIGGER piu' le descrizioni dei parametri. E' li' che
possono tornare le cose che non devono tornarci.

Il criterio e' rovesciato rispetto alla prima versione della skill: allora si
verificava che i messaggi dello script fossero citati alla lettera, e si
disallineavano in silenzio a ogni modifica. Ora quei testi li compone lo script,
quindi si verifica che NON siano copiati qui — ne' loro, ne' gli elenchi, ne' il
riepilogo, ne' i nomi delle chiavi del payload.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from percorsi import REPO, SCRIPTS  # noqa: E402
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, REPO)

import budget_sheets as bs  # noqa: E402
import schemas  # noqa: E402

PROPRIETA = schemas.REGISTRA_TRANSAZIONE["parameters"]["properties"]

# Tutto quello che finisce nel system prompt a ogni turno, in un blocco solo.
PROMPT = schemas.TRIGGER + "\n" + "\n".join(
    p["description"] for p in PROPRIETA.values())


class TestFormaDelloSchema(unittest.TestCase):

    def test_nome_e_descrizione(self):
        self.assertEqual(schemas.REGISTRA_TRANSAZIONE["name"], "registra_transazione")
        self.assertIs(schemas.REGISTRA_TRANSAZIONE["description"], schemas.TRIGGER)

    def test_ogni_parametro_e_descritto(self):
        for nome, p in PROPRIETA.items():
            with self.subTest(nome=nome):
                self.assertTrue(p.get("description", "").strip(),
                                "un parametro senza descrizione il modello lo ignora")

    def test_niente_campi_obbligatori(self):
        """Lo script e' fatto per essere chiamato anche a mani vuote: e' lui a
        chiedere quello che manca. Un `required` qui bloccherebbe il primo turno
        proprio nei casi ambigui, che sono quelli che contano."""
        self.assertEqual(schemas.REGISTRA_TRANSAZIONE["parameters"]["required"], [])

    def test_campi_tool_combacia_con_lo_schema(self):
        self.assertEqual(set(schemas.CAMPI_TOOL), set(PROPRIETA))

    def test_il_trigger_tiene_le_sue_esche(self):
        """Sono gli esempi che fanno scattare il tool su un messaggio scarno. Se
        spariscono, sparisce l'attivazione automatica — che e' tutto il valore."""
        for esca in ("benzina 50", "cena fuori", "8,5"):
            with self.subTest(esca=esca):
                self.assertIn(esca, schemas.TRIGGER)


class TestNienteTestoDelloScript(unittest.TestCase):
    """Tutto quello che si mostra all'utente lo compone lo script."""

    def messaggi_dello_script(self):
        campi = bs.campi_vuoti()
        campi.update({"categoria": "Cibo fuori / bevute", "importo": 30.0})
        return [bs.componi_messaggio(s, campi, tipo="Uscita") for s in
                ("chiedi_data", "chiedi_importo", "chiedi_categoria",
                 "chiedi_sottocategoria", "chiedi_conferma")]

    def test_nessuna_domanda_dello_script_e_copiata(self):
        for messaggio in self.messaggi_dello_script():
            prima_riga = messaggio.splitlines()[0]
            with self.subTest(prima_riga=prima_riga):
                self.assertNotIn(prima_riga, PROMPT,
                                 "e' testo dello script: una copia qui si disallinea")

    def test_niente_elenco_di_categorie(self):
        for nome in bs.get_taxonomy_map():
            with self.subTest(nome=nome):
                self.assertNotIn(nome, PROMPT,
                                 "l'elenco arriva dallo script, non da qui")

    def test_niente_riepilogo(self):
        for etichetta in ("Sottocategoria:", "Tipo:", "Confermi?"):
            with self.subTest(etichetta=etichetta):
                self.assertNotIn(etichetta, PROMPT)

    def test_non_nomina_le_chiavi_del_payload(self):
        """Se le chiavi strutturate si vedono, verranno usate — e comporre a mano
        e' esattamente quello che questa architettura serve a impedire.
        L'handler ne restituisce due, `stato` e `messaggio`, e bastano."""
        for chiave in ("opzioni", "intervallo"):
            with self.subTest(chiave=chiave):
                self.assertNotIn(chiave, PROMPT)


class TestNienteShell(unittest.TestCase):
    """Il tool ha sostituito la riga di comando: qui non deve restarne traccia.

    Un percorso, un interprete o un flag nella descrizione sarebbero istruzioni
    per una strada che non esiste piu' — e che `pre_tool_call` blocca.
    """

    def test_niente_percorsi_ne_interprete(self):
        for traccia in ("budget_sheets", "/opt/", "python", "$SCRIPT", "```"):
            with self.subTest(traccia=traccia):
                self.assertNotIn(traccia, PROMPT)

    def test_niente_flag_da_riga_di_comando(self):
        self.assertFalse(re.findall(r"--[a-z]+", PROMPT),
                         "i flag non esistono piu': sono parametri del tool")

    def test_niente_date_shellate(self):
        for traccia in ("date -d", "date +"):
            with self.subTest(traccia=traccia):
                self.assertNotIn(traccia, PROMPT,
                                 "le date relative le risolve lo script")

    def test_niente_tabella_delle_migliaia(self):
        """Era la compensazione di un bug in validate_importo. Il bug e' corretto,
        e citare "1.500" ora va benissimo — anzi serve, per dire che si passa
        tale e quale. Quello che non deve tornare e' la *conversione*."""
        for traccia in ("migliaia", "normalizzale", "Da passare"):
            with self.subTest(traccia=traccia):
                self.assertNotIn(traccia, PROMPT)
        self.assertNotRegex(PROMPT, r"\d[\d.,]*\s*(?:→|->)\s*\d",
                            "e' tornata una tabella di conversione degli importi")

    def test_niente_istruzioni_di_quoting(self):
        for traccia in ("virgolette", "backtick", "escape"):
            with self.subTest(traccia=traccia):
                self.assertNotIn(traccia, PROMPT,
                                 "non c'e' piu' una shell da cui difendersi")


class TestNuova(unittest.TestCase):

    def test_non_e_un_parametro(self):
        """`nuova` non e' una decisione del modello: la deriva il middleware dalla
        bozza su disco. Toglierlo dallo schema e' piu' forte che sovrascriverlo."""
        self.assertNotIn("nuova", PROPRIETA)
        self.assertNotIn("nuova", schemas.CAMPI_TOOL)

    def test_non_e_spiegato_nel_prompt(self):
        self.assertNotIn("`nuova`", PROMPT)


class TestConoscenzeCheNonDeveAvere(unittest.TestCase):
    """Dettagli interni allo script che il modello non deve conoscere.

    Se finiscono nel prompt si disallineano in silenzio il giorno in cui lo
    script cambia foglio, colonne o modo di tenere lo stato.
    """

    def test_non_nomina_il_foglio_di_destinazione(self):
        for dettaglio in (bs.GOOGLE_SHEET_NAME, "SHEET_NAME", bs.SPREADSHEET_ID):
            with self.subTest(dettaglio=dettaglio):
                self.assertNotIn(dettaglio, PROMPT)

    def test_non_nomina_la_bozza(self):
        for dettaglio in ("bozza", "BOZZA"):
            with self.subTest(dettaglio=dettaglio):
                self.assertNotIn(dettaglio, PROMPT,
                                 "dove lo script tenga lo stato non e' affar suo")


class TestLunghezza(unittest.TestCase):

    def test_il_prompt_resta_corto(self):
        """Questo testo sta nel system prompt a OGNI turno, anche nelle
        conversazioni che non parlano di spese: la ridondanza costa attenzione e
        token, non li compra. SKILL.md era arrivata a 15 KB un paragrafo
        enfatico alla volta, e ogni paragrafo era li' per compensare qualcosa che
        lo script non faceva.

        Se questo test fallisce, la domanda giusta non e' «alzo il limite?» ma
        «perche' questa cosa non la fa lo script, o il middleware?».
        """
        self.assertLess(len(PROMPT), 3000, f"il prompt sta ricrescendo: {len(PROMPT)} byte")

    def test_il_trigger_resta_una_descrizione(self):
        """E' la prima cosa che il modello legge per decidere se attivarsi: se
        diventa un manuale, la decisione si annacqua."""
        self.assertLess(len(schemas.TRIGGER), 900,
                        f"il trigger e' lungo {len(schemas.TRIGGER)} byte")


if __name__ == "__main__":
    unittest.main(verbosity=2)
