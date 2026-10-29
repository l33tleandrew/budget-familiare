#!/usr/bin/env python3
"""Il consenso OAuth di un'istanza nuova, e la sua verifica.

Nessuna rete: urlopen e' sempre sotto mock, e i file del profilo — client,
token, consenso in corso — stanno in una tmpdir per ogni test.
"""
import base64
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from percorsi import SCRIPTS  # noqa: E402

sys.path.insert(0, SCRIPTS)

import budget_sheets as bs  # noqa: E402
import setup_google as sg  # noqa: E402


class _Risposta:
    """Finto oggetto restituito da urlopen()."""

    def __init__(self, payload):
        self._corpo = json.dumps(payload).encode()

    def read(self):
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _permessi(percorso):
    return stat.S_IMODE(os.stat(percorso).st_mode)


class ConProfilo(unittest.TestCase):
    """Un profilo finto con un client desktop, e niente token."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = d.name
        self.cred = os.path.join(d.name, "google_client_secret.json")
        self.token = os.path.join(d.name, "google_token.json")
        self.pending = os.path.join(d.name, "budget_oauth_pending.json")
        self.scrivi_client({"installed": {"client_id": "cid", "client_secret": "csec"}})
        for oggetto, nome, valore in ((bs, "CRED_FILE", self.cred),
                                      (bs, "TOKEN_FILE", self.token),
                                      (sg, "PENDING_FILE", self.pending)):
            p = mock.patch.object(oggetto, nome, valore)
            p.start()
            self.addCleanup(p.stop)

    def scrivi_client(self, dati):
        with open(self.cred, "w") as f:
            json.dump(dati, f)

    def parametri(self, url):
        return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(url).query).items()}

    def in_attesa(self):
        with open(self.pending) as f:
            return json.load(f)


# ─────────────────────────────────────────────
# url
# ─────────────────────────────────────────────

class TestUrl(ConProfilo):

    def test_chiede_solo_lo_scope_dei_fogli(self):
        """Quello che privacy.md dichiara, e nient'altro."""
        p = self.parametri(sg.prepara_url())
        self.assertEqual(p["scope"], "https://www.googleapis.com/auth/spreadsheets")

    def test_parametri_del_flusso(self):
        p = self.parametri(sg.prepara_url())
        self.assertEqual(p["client_id"], "cid")
        self.assertEqual(p["redirect_uri"], "http://localhost:1")
        self.assertEqual(p["response_type"], "code")
        self.assertEqual(p["access_type"], "offline", "senza, niente refresh_token")
        self.assertEqual(p["prompt"], "consent")
        self.assertEqual(p["code_challenge_method"], "S256")
        self.assertEqual(p["state"], self.in_attesa()["state"])

    def test_la_challenge_e_lo_sha256_del_verifier(self):
        p = self.parametri(sg.prepara_url())
        verifier = self.in_attesa()["verifier"]
        atteso = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(p["code_challenge"], atteso)
        self.assertTrue(43 <= len(verifier) <= 128, "lunghezza imposta da PKCE")

    def test_il_consenso_in_corso_e_privato(self):
        sg.prepara_url()
        self.assertEqual(_permessi(self.pending), 0o600)

    def test_ogni_giro_ha_un_verifier_nuovo(self):
        sg.prepara_url()
        primo = self.in_attesa()
        sg.prepara_url()
        self.assertNotEqual(self.in_attesa()["verifier"], primo["verifier"])

    def test_client_mancante_dice_dove_metterlo(self):
        os.remove(self.cred)
        with self.assertRaises(sg.Errore) as cm:
            sg.prepara_url()
        self.assertIn(self.cred, str(cm.exception))
        self.assertFalse(os.path.exists(self.pending))

    def test_client_web_rifiutato(self):
        """Un client web non accetta il ritorno su localhost: Google rifiuterebbe
        dopo il consenso, con un errore che non dice perche'."""
        self.scrivi_client({"web": {"client_id": "cid", "client_secret": "csec"}})
        with self.assertRaises(sg.Errore) as cm:
            sg.prepara_url()
        self.assertIn("App desktop", str(cm.exception))

    def test_client_storto(self):
        with open(self.cred, "w") as f:
            f.write("[]")
        with self.assertRaises(sg.Errore):
            sg.prepara_url()


# ─────────────────────────────────────────────
# codice
# ─────────────────────────────────────────────

class TestCodice(ConProfilo):

    RISPOSTA = {"access_token": "a", "refresh_token": "r", "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/spreadsheets"}

    def setUp(self):
        super().setUp()
        sg.prepara_url()
        self.state = self.in_attesa()["state"]

    def indirizzo(self, state=None, codice="4/abc"):
        return (f"http://localhost:1/?state={state or self.state}&code={codice}"
                "&scope=https://www.googleapis.com/auth/spreadsheets")

    def scambia(self, testo, risposta=None, **kw):
        with mock.patch("urllib.request.urlopen",
                        return_value=_Risposta(risposta or self.RISPOSTA)) as m:
            sg.scambia_codice(testo, **kw)
        return m

    def leggi_token(self):
        with open(self.token) as f:
            return json.load(f)

    def test_scrive_il_token_nel_formato_del_motore(self):
        self.scambia(self.indirizzo())
        token = self.leggi_token()
        self.assertEqual(token["access_token"], "a")
        self.assertEqual(token["refresh_token"], "r")
        self.assertGreater(token["expires_at"], time.time())

    def test_il_motore_usa_il_token_senza_rinnovarlo(self):
        """Il formato giusto si prova facendolo leggere a chi lo usa davvero."""
        self.scambia(self.indirizzo())
        with mock.patch.object(bs, "_do_refresh") as rinnovo:
            self.assertEqual(bs.get_access_token(), "a")
        rinnovo.assert_not_called()

    def test_la_richiesta_porta_codice_e_verifier(self):
        verifier = self.in_attesa()["verifier"]
        m = self.scambia(self.indirizzo())
        richiesta = m.call_args[0][0]
        corpo = {k: v[0] for k, v in urllib.parse.parse_qs(richiesta.data.decode()).items()}
        self.assertEqual(richiesta.full_url, "https://oauth2.googleapis.com/token")
        self.assertEqual(corpo["code"], "4/abc")
        self.assertEqual(corpo["code_verifier"], verifier)
        self.assertEqual(corpo["grant_type"], "authorization_code")
        self.assertEqual(corpo["redirect_uri"], "http://localhost:1")

    def test_il_token_e_privato_e_il_consenso_in_corso_sparisce(self):
        self.scambia(self.indirizzo())
        self.assertEqual(_permessi(self.token), 0o600)
        self.assertFalse(os.path.exists(self.pending))

    def test_accetta_anche_il_solo_codice(self):
        m = self.scambia("  4/solo-codice \n")
        corpo = urllib.parse.parse_qs(m.call_args[0][0].data.decode())
        self.assertEqual(corpo["code"], ["4/solo-codice"])

    def test_state_sbagliato_rifiutato_senza_rete(self):
        with mock.patch("urllib.request.urlopen") as m, self.assertRaises(sg.Errore):
            sg.scambia_codice(self.indirizzo(state="altro"))
        m.assert_not_called()
        self.assertFalse(os.path.exists(self.token))

    def test_consenso_negato(self):
        with mock.patch("urllib.request.urlopen") as m, self.assertRaises(sg.Errore) as cm:
            sg.scambia_codice("http://localhost:1/?error=access_denied&state=" + self.state)
        m.assert_not_called()
        self.assertIn("access_denied", str(cm.exception))

    def test_senza_url_prima(self):
        os.remove(self.pending)
        with self.assertRaises(sg.Errore) as cm:
            sg.scambia_codice(self.indirizzo())
        self.assertIn("setup_google.py url", str(cm.exception))

    def test_token_esistente_non_si_sovrascrive_senza_force(self):
        """Lo stesso file lo usa la skill google-workspace: sostituirlo in
        silenzio le toglierebbe l'accesso. E il controllo viene prima della
        rete, perche' il codice vale una volta sola."""
        with open(self.token, "w") as f:
            json.dump({"refresh_token": "di-qualcun-altro"}, f)
        with mock.patch("urllib.request.urlopen") as m, self.assertRaises(sg.Errore) as cm:
            sg.scambia_codice(self.indirizzo())
        m.assert_not_called()
        self.assertIn("--force", str(cm.exception))
        self.assertEqual(self.leggi_token()["refresh_token"], "di-qualcun-altro")

        self.scambia(self.indirizzo(), forza=True)
        self.assertEqual(self.leggi_token()["refresh_token"], "r")
        self.assertEqual(_permessi(self.token), 0o600,
                         "anche sostituito, il token non eredita i permessi del vecchio")

    def test_senza_refresh_token(self):
        risposta = {k: v for k, v in self.RISPOSTA.items() if k != "refresh_token"}
        with self.assertRaises(sg.Errore) as cm:
            self.scambia(self.indirizzo(), risposta=risposta)
        self.assertIn("myaccount.google.com/permissions", str(cm.exception))
        self.assertFalse(os.path.exists(self.token))

    def test_scope_non_concesso(self):
        """Il consenso di Google ha le caselle: si puo' accettare senza spuntarla."""
        with self.assertRaises(sg.Errore) as cm:
            self.scambia(self.indirizzo(), risposta=dict(self.RISPOSTA, scope="openid"))
        self.assertIn("Fogli Google", str(cm.exception))
        self.assertFalse(os.path.exists(self.token))

    def test_codice_rifiutato_da_google(self):
        errore = urllib.error.HTTPError(sg.TOKEN_URL, 400, "x", {},
                                        io.BytesIO(b'{"error":"invalid_grant"}'))
        with mock.patch("urllib.request.urlopen", side_effect=errore), \
             self.assertRaises(sg.Errore) as cm:
            sg.scambia_codice(self.indirizzo())
        self.assertIn("invalid_grant", str(cm.exception))
        self.assertIn("setup_google.py url", str(cm.exception))


# ─────────────────────────────────────────────
# verifica
# ─────────────────────────────────────────────

class TestVerifica(ConProfilo):

    def setUp(self):
        super().setUp()
        with open(self.token, "w") as f:
            json.dump({"refresh_token": "r"}, f)

    def verifica(self, schede=None):
        foglio = {"properties": {"title": "Budget"},
                  "sheets": [{"properties": {"title": s}}
                             for s in (schede if schede is not None else [bs.GOOGLE_SHEET_NAME])]}
        with mock.patch.object(bs, "get_access_token", return_value="t"), \
             mock.patch("urllib.request.urlopen", return_value=_Risposta(foglio)) as m:
            return sg.verifica(), m

    def test_tutto_a_posto(self):
        esito, _ = self.verifica()
        self.assertTrue(all(ok for ok, _ in esito), esito)

    def test_legge_solo_titolo_e_schede(self):
        """privacy.md: niente contenuti del foglio, e mai una scrittura."""
        _, m = self.verifica()
        richiesta = m.call_args[0][0]
        self.assertEqual(richiesta.get_method(), "GET")
        self.assertIn(f"/spreadsheets/{bs.GOOGLE_SPREADSHEET_ID}?", richiesta.full_url)
        self.assertIn("fields=properties.title,sheets.properties.title", richiesta.full_url)

    def test_scheda_assente(self):
        esito, _ = self.verifica(schede=["Transazioni 1999", "Riepilogo"])
        ko = [riga for ok, riga in esito if not ok]
        self.assertEqual(len(ko), 1)
        self.assertIn("Transazioni 1999", ko[0], "deve dire quali schede ci sono")

    def test_senza_configurazione_non_chiama_google(self):
        with mock.patch.object(bs, "GOOGLE_SPREADSHEET_ID", ""), \
             mock.patch.object(bs, "get_access_token") as token, \
             mock.patch("urllib.request.urlopen") as rete:
            esito = sg.verifica()
        token.assert_not_called()
        rete.assert_not_called()
        self.assertFalse(esito[0][0])
        self.assertIn("GOOGLE_SPREADSHEET_ID", esito[0][1])

    def test_senza_token_non_chiama_google(self):
        os.remove(self.token)
        with mock.patch("urllib.request.urlopen") as rete:
            esito = sg.verifica()
        rete.assert_not_called()
        self.assertIn((False, f"token: {self.token} — manca"), esito)

    def test_foglio_irraggiungibile(self):
        errore = urllib.error.HTTPError("x", 404, "x", {}, io.BytesIO(b"not found"))
        with mock.patch.object(bs, "get_access_token", return_value="t"), \
             mock.patch("urllib.request.urlopen", side_effect=errore):
            esito = sg.verifica()
        self.assertFalse(esito[-1][0])
        self.assertIn("controlla l'id", esito[-1][1])


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

class TestCliSetup(unittest.TestCase):
    """Lo script davvero, in un profilo vuoto: non arriva mai alla rete."""

    def lancia(self, *argv):
        with tempfile.TemporaryDirectory() as profilo:
            env = {**os.environ, "HERMES_HOME": profilo}
            return subprocess.run([sys.executable, os.path.join(SCRIPTS, "setup_google.py"),
                                   *argv], capture_output=True, text=True, env=env)

    def test_senza_sottocomando(self):
        self.assertEqual(self.lancia().returncode, 64)

    def test_url_senza_client(self):
        r = self.lancia("url")
        self.assertEqual(r.returncode, 1)
        self.assertIn("google_client_secret.json", r.stderr)

    def test_verifica_in_un_profilo_vuoto(self):
        r = self.lancia("verifica")
        self.assertEqual(r.returncode, 1)
        self.assertIn("✗ token", r.stdout)


if __name__ == "__main__":
    unittest.main()
