#!/usr/bin/env python3
"""Il plugin: manifest, registrazioni, e i vincoli che deve imporre davvero.

Nessuna rete e nessuna riga sul foglio: si arriva al massimo fino a "chiedi_",
dove lo script si ferma da solo ad aspettare una risposta.
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from percorsi import REPO, PLUGIN_YAML  # noqa: E402

# Ogni bozza scritta da questi test finisce in un file temporaneo. Va impostato
# prima di caricare il plugin: budget_sheets legge BUDGET_BOZZA_FILE all'import,
# e senza questo scriverebbe nella bozza vera del profilo.
_BOZZA = tempfile.NamedTemporaryFile(prefix="test_plugin_bozza_", suffix=".json",
                                     delete=False)
_BOZZA.close()
os.environ["BUDGET_BOZZA_FILE"] = _BOZZA.name


def carica_plugin():
    """Carica la directory del repo come il package che Hermes si aspetta.

    Serve un vero package, non un modulo sciolto: __init__.py, tools.py e
    budget_sheets.py si importano fra loro con import relativi, che e' come sono
    strutturati i plugin negli esempi ufficiali.
    """
    spec = importlib.util.spec_from_file_location(
        "budget_familiare_plugin", os.path.join(REPO, "__init__.py"),
        submodule_search_locations=[REPO])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules["budget_familiare_plugin"] = pkg
    spec.loader.exec_module(pkg)
    return pkg


plugin = carica_plugin()


class CtxFinto:
    """Registra quello che gli viene chiesto, senza fare niente."""

    def __init__(self):
        self.tools, self.hook, self.middleware = {}, {}, {}
        self.comandi, self.skill, self.iniettati = {}, {}, []

    def register_tool(self, name, schema, handler, toolset="", **kwargs):
        self.tools[name] = {"schema": schema, "handler": handler, "toolset": toolset}

    def register_hook(self, nome, callback):
        self.hook.setdefault(nome, []).append(callback)

    def register_middleware(self, tipo, callback):
        self.middleware.setdefault(tipo, []).append(callback)

    def register_command(self, nome, handler, description="", args_hint=""):
        self.comandi[nome] = handler

    def register_skill(self, nome, percorso):
        self.skill[nome] = percorso

    def inject_message(self, contenuto, role="user", **kwargs):
        self.iniettati.append(contenuto)


class ConPlugin(unittest.TestCase):

    def setUp(self):
        self.ctx = CtxFinto()
        plugin.register(self.ctx)
        self.azzera()

    def tearDown(self):
        self.azzera()

    def azzera(self):
        plugin.budget_sheets.cancella_bozza()

    def chiama(self, session_id="s1", **args):
        """Il tool come lo chiamerebbe Hermes: prima il middleware, poi l'handler."""
        for mw in self.ctx.middleware["tool_request"]:
            esito = mw(tool_name="registra_transazione", args=args)
            if esito:
                args = esito["args"]
        grezzo = self.ctx.tools["registra_transazione"]["handler"](
            args, session_id=session_id)
        return json.loads(grezzo)


# ─────────────────────────────────────────────
# Manifest
# ─────────────────────────────────────────────

class TestManifest(ConPlugin):

    def manifest(self):
        """Il manifest a mano: il parsing YAML non e' garantito nello stdlib, e
        questi campi sono scalari e liste piatte."""
        dati, chiave = {}, None
        with open(PLUGIN_YAML, encoding="utf-8") as f:
            for riga in f:
                if not riga.strip() or riga.lstrip().startswith("#"):
                    continue
                if riga.startswith("  - "):
                    dati.setdefault(chiave, []).append(riga[4:].strip())
                elif ":" in riga:
                    chiave, _, valore = riga.partition(":")
                    chiave, valore = chiave.strip(), valore.strip()
                    if valore:
                        dati[chiave] = valore.strip('"')
        return dati

    def test_campi_richiesti(self):
        m = self.manifest()
        self.assertEqual(m["name"], "budget-familiare")
        self.assertTrue(m.get("version"))
        self.assertTrue(m.get("description"))

    def test_tool_dichiarati_e_registrati_coincidono(self):
        self.assertEqual(set(self.manifest()["provides_tools"]), set(self.ctx.tools))

    def test_hook_dichiarati_e_registrati_coincidono(self):
        self.assertEqual(set(self.manifest()["provides_hooks"]), set(self.ctx.hook))

    def test_niente_capabilities(self):
        """Dichiararne una fa comparire un prompt di consenso all'installazione.
        Questo plugin non ne ha bisogno: aggiungerne una va fatto apposta."""
        self.assertNotIn("capabilities", self.manifest())


# ─────────────────────────────────────────────
# Registrazioni
# ─────────────────────────────────────────────

class TestRegistrazioni(ConPlugin):

    def test_registra_tutto_quello_che_serve(self):
        self.assertIn("registra_transazione", self.ctx.tools)
        self.assertIn("tool_request", self.ctx.middleware)
        self.assertIn("spesa", self.ctx.comandi)

    def test_non_registra_skill(self):
        """Il plugin ne aveva una e l'ha persa apposta.

        Una skill impacchettata in un plugin non compare nell'index ne' in
        `skills_list`: nessuno la caricherebbe mai, e la sua era una seconda
        copia di quello che gia' dice lo schema del tool — che il modello legge
        a ogni turno. Se qualcuno ne riaggiunge una, questo test lo ferma e gli
        chiede di spiegare chi la caricherebbe."""
        self.assertEqual(self.ctx.skill, {})

    def test_il_comando_inietta_senza_interpretare(self):
        self.ctx.comandi["spesa"]("benzina 50")
        self.assertEqual(len(self.ctx.iniettati), 1)
        self.assertIn("benzina 50", self.ctx.iniettati[0])

    def test_il_comando_regge_anche_senza_argomenti(self):
        self.ctx.comandi["spesa"]()
        self.assertTrue(self.ctx.iniettati[0])


# ─────────────────────────────────────────────
# Il middleware: l'instradamento non e' del modello
# ─────────────────────────────────────────────

class TestInstradamento(ConPlugin):
    """Il test che vale piu' di tutti gli altri messi insieme.

    Dimenticare `nuova` fondeva una spesa nuova con quella di prima; metterlo di
    troppo buttava via un dialogo a meta'. Ora non e' piu' una decisione.
    """

    def middleware(self, **args):
        return self.ctx.middleware["tool_request"][0](
            tool_name="registra_transazione", args=args)

    def test_senza_bozza_e_una_transazione_nuova(self):
        self.assertTrue(self.middleware(importo="30")["args"]["nuova"])

    def test_con_bozza_aperta_e_una_continuazione(self):
        self.chiama(importo="30")                      # si ferma su chiedi_categoria
        self.assertTrue(plugin.budget_sheets.in_dialogo())
        self.assertFalse(self.middleware(risposta="5")["args"]["nuova"])

    def test_sovrascrive_il_modello_che_sbaglia(self):
        self.chiama(importo="30")
        # Il modello insiste che e' una transazione nuova: il disco dice di no.
        self.assertFalse(self.middleware(risposta="5", nuova=True)["args"]["nuova"])
        # E viceversa, a bozza chiusa.
        self.azzera()
        self.assertTrue(self.middleware(importo="30", nuova=False)["args"]["nuova"])

    def test_non_tocca_gli_altri_tool(self):
        self.assertIsNone(self.ctx.middleware["tool_request"][0](
            tool_name="terminal", args={"command": "ls"}))

    def test_lascia_annulla_al_modello(self):
        """Annullare e' un intento dell'utente, non un instradamento."""
        self.chiama(importo="30")
        self.assertIs(self.middleware(annulla=True)["args"]["annulla"], True)

    def test_una_continuazione_non_perde_i_campi(self):
        """Tre turni, e nessuno di loro ripassa quello che si e' detto prima:
        importo e descrizione del primo turno devono ricomparire nel riepilogo."""
        self.chiama(importo="30", descrizione="Trattoria da Nino")
        self.chiama(risposta="3")                      # Cibo fuori / bevute
        esito = self.chiama(risposta="1")
        self.assertEqual(esito["stato"], "chiedi_conferma")
        self.assertIn("Trattoria da Nino", esito["messaggio"])
        self.assertIn("30.00", esito["messaggio"])


# ─────────────────────────────────────────────
# L'handler
# ─────────────────────────────────────────────

class TestHandler(ConPlugin):

    def test_ritorna_una_stringa_json(self):
        grezzo = self.ctx.tools["registra_transazione"]["handler"](
            {"importo": "30"}, session_id="s1")
        self.assertIsInstance(grezzo, str)
        json.loads(grezzo)

    def test_solo_stato_e_messaggio(self):
        """`opzioni` e `intervallo` restano nel payload dello script per i test.
        Se il modello li vedesse, ricomporrebbe l'elenco a mano — ed e' quello
        che tutta questa architettura serve a impedire."""
        self.assertEqual(set(self.chiama(importo="30")), {"stato", "messaggio"})

    def test_non_solleva_mai(self):
        handler = self.ctx.tools["registra_transazione"]["handler"]
        for args in ({}, {"importo": object()}, {"sconosciuto": 1}, None, []):
            with self.subTest(args=args):
                grezzo = handler(args, session_id="s1")
                self.assertIsInstance(grezzo, str)
                json.loads(grezzo)

    def test_un_importo_impossibile_diventa_una_domanda(self):
        self.assertEqual(self.chiama(importo="abc")["stato"], "chiedi_importo")

    def test_le_migliaia_arrivano_intere(self):
        """Passate come le scrive l'utente: era la tabella che stava nel prompt."""
        esito = self.chiama(importo="1.500", categoria="Cibo fuori / bevute",
                            sottocategoria="1")
        self.assertIn("1500.00", esito["messaggio"])

    def test_una_descrizione_con_metacaratteri_arriva_intatta(self):
        """Non c'e' piu' una shell in mezzo: niente da sanificare, niente da rompere."""
        velenosa = 'Bar "da $PIPPO" `whoami` \\ 100%'
        esito = self.chiama(importo="30", descrizione=velenosa,
                            categoria="Sport", sottocategoria="Palestra")
        self.assertEqual(esito["stato"], "chiedi_conferma")
        self.assertIn(velenosa, esito["messaggio"])


# ─────────────────────────────────────────────
# La resa verbatim
# ─────────────────────────────────────────────

class TestResaVerbatim(ConPlugin):
    """Qui "stampa il messaggio parola per parola" smette di essere una richiesta."""

    def transform(self, session_id="s1"):
        return self.ctx.hook["transform_llm_output"][0](session_id=session_id)

    def test_sostituisce_la_risposta_col_messaggio_dello_script(self):
        esito = self.chiama(importo="30")
        self.assertEqual(self.transform(), esito["messaggio"])

    def test_vale_una_volta_sola(self):
        self.chiama(importo="30")
        self.assertIsNotNone(self.transform())
        self.assertIsNone(self.transform(), "un messaggio vecchio non deve ricomparire")

    def test_un_turno_senza_tool_non_viene_toccato(self):
        self.assertIsNone(self.transform())

    def test_le_sessioni_non_si_mescolano(self):
        self.chiama(session_id="anna", importo="30")
        self.assertIsNone(self.transform("bruno"))
        self.assertIsNotNone(self.transform("anna"))

    def test_la_fine_sessione_ripulisce(self):
        self.chiama(session_id="anna", importo="30")
        self.ctx.hook["on_session_end"][0](session_id="anna")
        self.assertIsNone(self.transform("anna"))


# ─────────────────────────────────────────────
# Una sola strada
# ─────────────────────────────────────────────

class TestBloccoScorciatoie(ConPlugin):

    def pre(self, tool_name, **args):
        return self.ctx.hook["pre_tool_call"][0](tool_name=tool_name, args=args)

    def test_blocca_lo_script_shellato(self):
        esito = self.pre("terminal", command="python3 budget_sheets.py append")
        self.assertEqual(esito["action"], "block")
        self.assertIn("registra_transazione", esito["message"])

    def test_lascia_passare_il_resto(self):
        self.assertIsNone(self.pre("terminal", command="ls -la"))
        self.assertIsNone(self.pre("read_file", path="/tmp/x"))

    def test_regge_argomenti_strani(self):
        self.assertIsNone(self.ctx.hook["pre_tool_call"][0](
            tool_name="terminal", args=None))


# ─────────────────────────────────────────────
# L'iniezione di stato
# ─────────────────────────────────────────────

class TestIniezioneStato(ConPlugin):

    def inietta(self):
        return self.ctx.hook["pre_llm_call"][0](
            session_id="s1", user_message="5", model="x")

    def test_muta_quando_non_c_e_niente_in_corso(self):
        self.assertIsNone(self.inietta())

    def test_avvisa_quando_c_e_una_bozza(self):
        self.chiama(importo="30")
        self.assertIn("registra_transazione", self.inietta()["context"])

    def test_non_passa_i_campi_raccolti(self):
        """Dargli i campi sarebbe un invito a ricomporre il riepilogo a mano."""
        self.chiama(importo="30", descrizione="Trattoria da Nino")
        contesto = self.inietta()["context"]
        for campo in ("Trattoria da Nino", "30", "Importo:", "Categoria:"):
            with self.subTest(campo=campo):
                self.assertNotIn(campo, contesto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
