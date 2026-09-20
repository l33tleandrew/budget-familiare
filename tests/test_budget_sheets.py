#!/usr/bin/env python3
"""Suite di test per budget_sheets.py.

Solo stdlib (unittest): sul server il plugin gira con l'interprete di Hermes e
non c'e' modo di installare pytest. Nessun test tocca la rete: le due funzioni
che parlano con Google (get_access_token, append_row) vengono sostituite, e
urlopen e' sempre sotto mock quando serve.

    python3 -m unittest discover -s tests -v
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from percorsi import REPO, SCRIPT, SCRIPTS  # noqa: E402

sys.path.insert(0, SCRIPTS)

import budget_sheets as bs  # noqa: E402

OGGI = datetime.now().strftime("%d/%m/%Y")
CHIAVI = {"stato", "messaggio", "data", "importo", "categoria", "sottocategoria",
          "tipo", "descrizione", "note", "conferma", "opzioni", "intervallo"}


# ─────────────────────────────────────────────
# Configurazione
# ─────────────────────────────────────────────

class TestAnnoBudget(unittest.TestCase):

    @unittest.skipIf(os.environ.get("GOOGLE_SHEET_NAME"),
                     "il nome del foglio e' sovrascritto dall'ambiente")
    def test_il_nome_predefinito_della_scheda_discende_dall_anno(self):
        """Un posto solo: se il default tornasse a essere un letterale,
        cambiare anno ridiventerebbe una modifica in due punti."""
        self.assertEqual(bs.GOOGLE_SHEET_NAME, f"Transazioni {bs.ANNO_BUDGET}")


# ─────────────────────────────────────────────
# Validazione: data
# ─────────────────────────────────────────────

class TestValidateData(unittest.TestCase):

    def test_formato_valido(self):
        for d in ("01/09/2026", "13/09/2026", "31/12/1999", "29/02/2024"):
            with self.subTest(d=d):
                self.assertTrue(bs.validate_data(d))

    def test_giorno_e_mese_vanno_a_due_cifre(self):
        for d in ("1/9/2026", "1/09/2026", "01/9/2026"):
            with self.subTest(d=d):
                self.assertFalse(bs.validate_data(d))

    def test_altri_formati_rifiutati(self):
        for d in ("2026-09-13", "13-09-2026", "13/09/26", "13/09/2026 10:00", " 13/09/2026 "):
            with self.subTest(d=d):
                self.assertFalse(bs.validate_data(d))

    def test_date_inesistenti(self):
        for d in ("31/02/2026", "29/02/2023", "13/13/2026", "00/09/2026", "01/00/2026"):
            with self.subTest(d=d):
                self.assertFalse(bs.validate_data(d))

    def test_non_stringhe(self):
        for d in ("", None, 20260913, ["13/09/2026"]):
            with self.subTest(d=d):
                self.assertFalse(bs.validate_data(d))


# ─────────────────────────────────────────────
# Validazione: date relative
# ─────────────────────────────────────────────

class TestDataRelativa(unittest.TestCase):
    """Era `date -d yesterday` fatto shellare al modello. Ora e' codice."""

    # Giovedi 17 settembre 2026. Fisso, perche' un test che chiede l'ora al
    # sistema fallisce a mezzanotte e nessuno capisce perche'.
    OGGI = datetime(2026, 9, 17)

    def relativa(self, testo):
        return bs.normalizza_data_relativa(testo, oggi=self.OGGI)

    def test_giorni_fissi(self):
        for testo, atteso in (("oggi", "17/09/2026"),
                              ("ieri", "16/09/2026"),
                              ("l'altro ieri", "15/09/2026"),
                              ("avantieri", "15/09/2026")):
            with self.subTest(testo=testo):
                self.assertEqual(self.relativa(testo), atteso)

    def test_maiuscole_accenti_e_spazi(self):
        for testo in ("Ieri", "  IERI  ", "L'ALTRO  IERI"):
            with self.subTest(testo=testo):
                self.assertIn(self.relativa(testo), ("16/09/2026", "15/09/2026"))

    def test_giorni_della_settimana(self):
        # Da giovedi: lunedi e' 3 giorni fa, venerdi 6 (quello passato, non domani).
        for testo, atteso in (("lunedi scorso", "14/09/2026"),
                              ("lunedì scorso", "14/09/2026"),
                              ("martedi", "15/09/2026"),
                              ("venerdi scorso", "11/09/2026"),
                              ("domenica", "13/09/2026")):
            with self.subTest(testo=testo):
                self.assertEqual(self.relativa(testo), atteso)

    def test_lo_stesso_giorno_di_oggi_e_una_settimana_fa(self):
        # "giovedi scorso" detto di giovedi non e' oggi.
        self.assertEqual(self.relativa("giovedi scorso"), "10/09/2026")

    def test_il_resto_passa_intatto(self):
        for testo in ("13/09/2026", "", "boh", "il mese scorso", "2026-09-13"):
            with self.subTest(testo=testo):
                self.assertEqual(self.relativa(testo), testo)

    def test_non_stringhe_passano_intatte(self):
        for valore in (None, 42, ["ieri"]):
            with self.subTest(valore=valore):
                self.assertIs(self.relativa(valore), valore)

    def test_normalizza_le_risolve(self):
        campi = bs.campi_vuoti()
        campi.update({"data": "ieri", "importo": "10"})
        campi, stato, _ = bs.normalizza(campi)
        self.assertNotEqual(stato, "chiedi_data", "la data relativa e' stata rifiutata")
        self.assertTrue(bs.validate_data(campi["data"]))


# ─────────────────────────────────────────────
# Validazione: importo
# ─────────────────────────────────────────────

class TestValidateImporto(unittest.TestCase):

    def test_formato_inglese(self):
        self.assertEqual(bs.validate_importo("30.00"), 30.0)
        self.assertEqual(bs.validate_importo("12.5"), 12.5)
        self.assertEqual(bs.validate_importo("0.01"), 0.01)

    def test_formato_italiano(self):
        self.assertEqual(bs.validate_importo("12,50"), 12.5)
        self.assertEqual(bs.validate_importo("1.200,00"), 1200.0)
        self.assertEqual(bs.validate_importo("1.500,50"), 1500.5)
        self.assertEqual(bs.validate_importo("12.345.678,90"), 12345678.9)

    def test_interi(self):
        self.assertEqual(bs.validate_importo("30"), 30.0)
        self.assertEqual(bs.validate_importo("1500"), 1500.0)

    def test_spazi_ai_lati_tollerati(self):
        self.assertEqual(bs.validate_importo("  30  "), 30.0)

    def test_punto_delle_migliaia(self):
        # Era la trappola documentata nel prompt con una tabella: "1.500" cadeva
        # nel ramo decimale e valeva 1.5, quindi la normalizzazione toccava al
        # modello. Ora la fa lo script, ed e' qui che si verifica.
        self.assertEqual(bs.validate_importo("1.500"), 1500.0)
        self.assertEqual(bs.validate_importo("1.200.000"), 1200000.0)
        self.assertEqual(bs.validate_importo("12.000"), 12000.0)

    def test_il_punto_decimale_non_regredisce(self):
        # Il ramo delle migliaia non deve mangiarsi i decimali veri: "1.5" ha una
        # cifra sola dopo il punto, "1.50" due. Solo tre lo rendono migliaia.
        self.assertEqual(bs.validate_importo("1.5"), 1.5)
        self.assertEqual(bs.validate_importo("1.50"), 1.5)
        self.assertEqual(bs.validate_importo("1500.00"), 1500.0)
        self.assertEqual(bs.validate_importo("12,50"), 12.5)
        self.assertEqual(bs.validate_importo("1.200,00"), 1200.0)

    def test_zero_e_negativi_rifiutati(self):
        for s in ("0", "0.00", "0,00", "-5", "-12.50"):
            with self.subTest(s=s):
                self.assertIs(bs.validate_importo(s), False)

    def test_valuta_rifiutata(self):
        for s in ("30 €", "€30", "30 EUR", "30$"):
            with self.subTest(s=s):
                self.assertIs(bs.validate_importo(s), False)

    def test_spazzatura_rifiutata(self):
        for s in ("", "abc", "1.2.3", "30.", ".50", "1,2,3", "30,00.5"):
            with self.subTest(s=s):
                self.assertIs(bs.validate_importo(s), False)

    def test_numeri_accettati(self):
        # La bozza conserva l'importo gia' convertito a float: rivalidarlo a ogni
        # turno deve funzionare, o una conversazione lunga si spezzerebbe a meta'.
        for v in (30, 30.0, 12.5):
            with self.subTest(v=v):
                self.assertEqual(bs.validate_importo(v), float(v))

    def test_numeri_non_positivi_rifiutati(self):
        for v in (0, -1, -12.5):
            with self.subTest(v=v):
                self.assertIs(bs.validate_importo(v), False)

    def test_non_numeri_rifiutati(self):
        for v in (None, [30], {}, True, False):
            with self.subTest(v=v):
                self.assertIs(bs.validate_importo(v), False)

    def test_float_stringato(self):
        self.assertEqual(bs.validate_importo(str(30.0)), 30.0)


class TestValidateTipo(unittest.TestCase):

    def test_validi(self):
        self.assertTrue(bs.validate_tipo("Entrata"))
        self.assertTrue(bs.validate_tipo("Uscita"))

    def test_non_validi(self):
        for t in ("entrata", "USCITA", "", None, "Entrate"):
            with self.subTest(t=t):
                self.assertFalse(bs.validate_tipo(t))


# ─────────────────────────────────────────────
# Tassonomia
# ─────────────────────────────────────────────

class TestTassonomia(unittest.TestCase):

    def setUp(self):
        self.mappa = bs.get_taxonomy_map()

    def test_tutte_le_categorie_lette(self):
        self.assertEqual(len(self.mappa), 17)
        self.assertIn("Stipendio", self.mappa)
        self.assertIn("Beneficienza", self.mappa)

    def test_nomi_con_barra_e_spazi_preservati(self):
        self.assertIn("Cibo fuori / bevute", self.mappa)
        self.assertIn("Auto / Moto", self.mappa)
        self.assertIn("Cura / Benessere", self.mappa)

    def test_categorie_senza_sottocategorie(self):
        for c in ("Stipendio", "Supermercato", "Abbigliamento",
                  "Divertimento", "Cultura", "Beneficienza"):
            with self.subTest(c=c):
                self.assertEqual(self.mappa[c], [])

    def test_ordine_sottocategorie_preservato(self):
        self.assertEqual(
            self.mappa["Cibo fuori / bevute"],
            ["Asporto", "Bar", "Da amici", "Fast food", "Ristorante", "Bevuta", "Altro"],
        )

    def test_spazi_in_coda_nel_yaml_non_sporcano_il_nome(self):
        # In tassonomia.yaml la voce "Altro" di Salute ha spazi finali.
        self.assertIn("Altro", self.mappa["Salute"])
        self.assertNotIn("Altro  ", self.mappa["Salute"])


class TestCategoria(unittest.TestCase):

    def test_id_risolto_in_nome(self):
        self.assertEqual(bs.find_categoria_by_id(1), "Stipendio")
        self.assertEqual(bs.find_categoria_by_id(3), "Cibo fuori / bevute")
        self.assertEqual(bs.find_categoria_by_id(17), "Beneficienza")

    def test_id_inesistente(self):
        for i in (0, 18, 99):
            with self.subTest(i=i):
                self.assertIs(bs.find_categoria_by_id(i), False)

    def test_accetta_nome_esatto(self):
        self.assertEqual(bs.validate_categoria("Supermercato"), "Supermercato")

    def test_accetta_id_come_stringa(self):
        self.assertEqual(bs.validate_categoria("3"), "Cibo fuori / bevute")

    def test_maiuscole_e_accenti_tollerati(self):
        # Lo script legge il testo grezzo dell'utente: pretendere la maiuscola
        # giusta sarebbe un fallimento gratuito.
        for c in ("supermercato", "SUPERMERCATO", "SuperMercato"):
            with self.subTest(c=c):
                self.assertEqual(bs.validate_categoria(c), "Supermercato")
        self.assertEqual(bs.validate_categoria("cura / benessere"), "Cura / Benessere")

    def test_nomi_approssimati_rifiutati(self):
        # Tollerante su maiuscole e accenti, non sull'approssimazione: meglio
        # rifare la domanda che indovinare la categoria sbagliata.
        for c in ("Cibo fuori/bevute", "Cibo fuori", "Auto/Moto", "Benzina", "Pizza", ""):
            with self.subTest(c=c):
                self.assertIs(bs.validate_categoria(c), False)

    def test_id_numerico_non_stringato(self):
        self.assertEqual(bs.validate_categoria(3), "Cibo fuori / bevute")

    def test_non_stringhe(self):
        for c in (None, ["Supermercato"]):
            with self.subTest(c=c):
                self.assertIs(bs.validate_categoria(c), False)


class TestSottocategoria(unittest.TestCase):

    def test_id_risolto_nel_contesto_della_categoria(self):
        self.assertEqual(bs.find_sottocategoria_by_id("Cibo fuori / bevute", "5"), "Ristorante")
        self.assertEqual(bs.find_sottocategoria_by_id("Auto / Moto", "1"), "Benzina")
        self.assertEqual(bs.find_sottocategoria_by_id("Cibo fuori / bevute", "1"), "Asporto")

    def test_id_non_trovato(self):
        self.assertIs(bs.find_sottocategoria_by_id("Cibo fuori / bevute", "99"), False)
        self.assertIs(bs.find_sottocategoria_by_id("Supermercato", "1"), False)

    def test_accetta_nome_e_id(self):
        self.assertEqual(bs.validate_sottocategoria("Cibo fuori / bevute", "Ristorante"), "Ristorante")
        self.assertEqual(bs.validate_sottocategoria("Cibo fuori / bevute", "5"), "Ristorante")

    def test_vuota_valida_solo_se_la_categoria_non_ne_prevede(self):
        self.assertEqual(bs.validate_sottocategoria("Supermercato", ""), "")
        self.assertIs(bs.validate_sottocategoria("Cibo fuori / bevute", ""), False)

    def test_categoria_senza_sottocategorie_le_ignora(self):
        # Era la trappola senza uscita: lo script chiedeva una sottocategoria che
        # non esiste, con un elenco vuoto, e il dialogo non ne usciva piu'. Ora
        # e' la tassonomia a decidere, non chi chiama.
        self.assertEqual(bs.validate_sottocategoria("Supermercato", "Altro"), "")
        self.assertEqual(bs.validate_sottocategoria("Supermercato", "1"), "")

    def test_sottocategoria_di_un_altra_categoria_rifiutata(self):
        self.assertIs(bs.validate_sottocategoria("Cibo fuori / bevute", "Benzina"), False)

    def test_categoria_non_valida(self):
        for c in (False, "Pizza", None):
            with self.subTest(c=c):
                self.assertIs(bs.validate_sottocategoria(c, "Ristorante"), False)

    def test_id_numerico_non_stringato(self):
        self.assertEqual(bs.validate_sottocategoria("Cibo fuori / bevute", 5), "Ristorante")

    def test_non_stringhe(self):
        self.assertIs(bs.validate_sottocategoria("Cibo fuori / bevute", None), False)


class TestGetTipo(unittest.TestCase):

    def test_tipo_della_categoria(self):
        self.assertEqual(bs.get_tipo("Stipendio", ""), "Entrata")
        self.assertEqual(bs.get_tipo("Supermercato", ""), "Uscita")

    def test_tipo_ereditato_dalla_categoria_con_sottocategoria(self):
        self.assertEqual(bs.get_tipo("Cibo fuori / bevute", "Ristorante"), "Uscita")
        self.assertEqual(bs.get_tipo("Auto / Moto", "Benzina"), "Uscita")

    def test_categoria_entrambi_il_tipo_lo_da_la_sottocategoria(self):
        self.assertEqual(bs.get_tipo("Investimento", "Dividendi"), "Entrata")
        self.assertEqual(bs.get_tipo("Investimento", "Plusvalenza"), "Entrata")
        self.assertEqual(bs.get_tipo("Investimento", "Interessi maturati"), "Entrata")
        self.assertEqual(bs.get_tipo("Investimento", "PAC"), "Uscita")
        self.assertEqual(bs.get_tipo("Investimento", "Tasse"), "Uscita")
        self.assertEqual(bs.get_tipo("Investimento", "Minusvalenza"), "Uscita")

    def test_categoria_entrambi_senza_sottocategoria_non_ha_tipo(self):
        # Irraggiungibile dal flusso (Investimento ha sottocategorie obbligatorie),
        # ma se un giorno le perdesse il tipo resterebbe indeterminato.
        self.assertIs(bs.get_tipo("Investimento", ""), False)

    def test_categoria_inesistente(self):
        self.assertIs(bs.get_tipo("Pizza", ""), False)


# ─────────────────────────────────────────────
# Bozza: lo stato del dialogo su disco
# ─────────────────────────────────────────────

class ConBozza(unittest.TestCase):
    """Ogni test CLI ha la sua bozza in una tmpdir.

    Senza isolamento i test si contaminano a vicenda e — peggio — sporcano la
    bozza vera della macchina su cui girano.
    """

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.bozza = os.path.join(d.name, "bozza.json")
        p = mock.patch.object(bs, "BOZZA_FILE", self.bozza)
        p.start()
        self.addCleanup(p.stop)

    def scrivi_bozza(self, stato, campi, aggiornato=None):
        campi_pieni = bs.campi_vuoti()
        campi_pieni.update(campi)
        bs.salva_bozza(stato, campi_pieni, ora=aggiornato)
        return campi_pieni


class TestBozza(ConBozza):

    def test_la_bozza_predefinita_sta_fuori_dal_repo(self):
        """La cron di sync fa `git add -A` dentro il repo: la bozza deve essere
        irraggiungibile, non solo ignorata. Dentro ci sono le spese di casa."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BUDGET_BOZZA_FILE", None)
            predefinita = os.path.abspath(bs._bozza_predefinita())
        self.assertFalse(predefinita.startswith(os.path.abspath(REPO) + os.sep),
                         f"la bozza finirebbe nel worktree git: {predefinita}")

    def test_giro_completo_salva_e_rilegge(self):
        self.scrivi_bozza("chiedi_conferma", {"importo": 30.0, "categoria": "Supermercato"})
        b = bs.carica_bozza()
        self.assertEqual(b["stato"], "chiedi_conferma")
        self.assertEqual(b["campi"]["importo"], 30.0)
        self.assertEqual(b["campi"]["categoria"], "Supermercato")

    def test_bozza_assente(self):
        self.assertIsNone(bs.carica_bozza())

    def test_bozza_scaduta(self):
        self.scrivi_bozza("chiedi_importo", {}, aggiornato=time.time() - bs.BOZZA_TTL - 60)
        self.assertEqual(bs.carica_bozza(), "scaduta")
        self.assertFalse(os.path.exists(self.bozza), "una bozza scaduta va rimossa")

    def test_bozza_viva_entro_il_ttl(self):
        self.scrivi_bozza("chiedi_importo", {"categoria": "Supermercato"},
                          aggiornato=time.time() - bs.BOZZA_TTL + 60)
        self.assertIsInstance(bs.carica_bozza(), dict)

    def test_bozza_corrotta_non_esplode(self):
        for contenuto in ("{", "", "[]", '{"versione": 99}'):
            with self.subTest(contenuto=contenuto):
                with open(self.bozza, "w") as f:
                    f.write(contenuto)
                self.assertIsNone(bs.carica_bozza())

    def test_scrittura_atomica_non_lascia_temporanei(self):
        self.scrivi_bozza("chiedi_importo", {})
        residui = [f for f in os.listdir(os.path.dirname(self.bozza)) if f.endswith(".tmp")]
        self.assertEqual(residui, [])

    def test_scrittura_fallita_lascia_intatta_la_bozza_di_prima(self):
        self.scrivi_bozza("chiedi_conferma", {"importo": 30.0})
        with mock.patch("os.replace", side_effect=OSError("disco pieno")):
            with self.assertRaises(OSError):
                bs.salva_bozza("chiedi_importo", bs.campi_vuoti())
        self.assertEqual(bs.carica_bozza()["campi"]["importo"], 30.0)

    def test_cancella_bozza_e_idempotente(self):
        bs.cancella_bozza()
        bs.cancella_bozza()


# ─────────────────────────────────────────────
# Logica pura del dialogo
# ─────────────────────────────────────────────

class TestUnisci(unittest.TestCase):

    def test_i_campi_non_passati_restano(self):
        campi = dict(bs.campi_vuoti(), importo=30.0, descrizione="Trattoria")
        unito = bs.unisci(campi, {"categoria": "Supermercato", "importo": None})
        self.assertEqual(unito["importo"], 30.0)
        self.assertEqual(unito["descrizione"], "Trattoria")
        self.assertEqual(unito["categoria"], "Supermercato")

    def test_cambiare_categoria_azzera_la_sottocategoria(self):
        campi = dict(bs.campi_vuoti(), categoria="Cibo fuori / bevute", sottocategoria="Ristorante")
        unito = bs.unisci(campi, {"categoria": "Auto / Moto"})
        self.assertEqual(unito["sottocategoria"], "",
                         "la sottocategoria apparteneva alla categoria di prima")

    def test_stessa_categoria_non_azzera_la_sottocategoria(self):
        """Anche ridetta in un altro modo: per id, o senza maiuscole. Confrontare
        le stringhe grezze faceva decadere una sottocategoria gia' scelta solo
        perche' l'utente aveva ripetuto la categoria diversamente."""
        campi = dict(bs.campi_vuoti(), categoria="Cibo fuori / bevute", sottocategoria="Ristorante")
        for ridetta in ("Cibo fuori / bevute", "3", 3, "cibo fuori / bevute"):
            with self.subTest(ridetta=ridetta):
                self.assertEqual(bs.unisci(campi, {"categoria": ridetta})["sottocategoria"],
                                 "Ristorante")

    def test_ogni_modifica_invalida_la_conferma(self):
        campi = dict(bs.campi_vuoti(), conferma="Si", importo=30.0)
        self.assertEqual(bs.unisci(campi, {"importo": "40"})["conferma"], "",
                         "correggere un campo non deve far partire la scrittura")

    def test_la_conferma_da_sola_non_si_invalida(self):
        campi = dict(bs.campi_vuoti(), importo=30.0)
        self.assertEqual(bs.unisci(campi, {"conferma": "Si"})["conferma"], "Si")

    def test_chiavi_sconosciute_ignorate(self):
        self.assertNotIn("tipo", bs.unisci(bs.campi_vuoti(), {"tipo": "Uscita"}))


class TestNormalizza(unittest.TestCase):

    def campi(self, **kw):
        return dict(bs.campi_vuoti(), **kw)

    def test_data_vuota_diventa_oggi(self):
        campi, _, _ = bs.normalizza(self.campi(importo="30", categoria="Supermercato"))
        self.assertEqual(campi["data"], datetime.now().strftime("%d/%m/%Y"))

    def test_data_non_valida_conserva_tutto_il_resto(self):
        """La differenza col vecchio gateway, che azzerava ogni campo a valle e
        costringeva chi chiamava a ricordarseli."""
        campi, stato, rifiutato = bs.normalizza(
            self.campi(data="31/02/2026", importo="30", categoria="Supermercato",
                       descrizione="Spesa"))
        self.assertEqual(stato, "chiedi_data")
        self.assertEqual(rifiutato, "31/02/2026")
        self.assertEqual(campi["data"], "", "la data non valida va scartata")
        self.assertEqual(campi["importo"], "30")
        self.assertEqual(campi["categoria"], "Supermercato")
        self.assertEqual(campi["descrizione"], "Spesa")

    def test_importo_mancante(self):
        campi, stato, _ = bs.normalizza(self.campi(categoria="Supermercato"))
        self.assertEqual(stato, "chiedi_importo")
        self.assertEqual(campi["categoria"], "Supermercato")

    def test_importo_non_valido_viene_citato(self):
        _, stato, rifiutato = bs.normalizza(self.campi(importo="30 €"))
        self.assertEqual(stato, "chiedi_importo")
        self.assertEqual(rifiutato, "30 €")

    def test_importo_normalizzato(self):
        campi, _, _ = bs.normalizza(self.campi(importo="12,50", categoria="Supermercato"))
        self.assertEqual(campi["importo"], 12.5)

    def test_categoria_mancante(self):
        _, stato, _ = bs.normalizza(self.campi(importo="30"))
        self.assertEqual(stato, "chiedi_categoria")

    def test_categoria_per_id_diventa_il_nome(self):
        campi, stato, _ = bs.normalizza(self.campi(importo="30", categoria="2"))
        self.assertEqual(campi["categoria"], "Supermercato")
        self.assertEqual(stato, "chiedi_conferma")

    def test_sottocategoria_mancante(self):
        _, stato, _ = bs.normalizza(self.campi(importo="30", categoria="Cibo fuori / bevute"))
        self.assertEqual(stato, "chiedi_sottocategoria")

    def test_categoria_senza_sottocategorie_non_la_chiede_mai(self):
        """L'invariante che elimina il loop senza uscita."""
        for passata in ("", "Altro", "1", "qualunque cosa"):
            with self.subTest(passata=passata):
                campi, stato, _ = bs.normalizza(
                    self.campi(importo="30", categoria="Supermercato", sottocategoria=passata))
                self.assertEqual(stato, "chiedi_conferma")
                self.assertEqual(campi["sottocategoria"], "")

    def test_conferma_si_completa(self):
        campi, stato, _ = bs.normalizza(
            self.campi(importo="30", categoria="Supermercato", conferma="Si"))
        self.assertIsNone(stato)
        self.assertEqual(campi["importo"], 30.0)

    def test_senza_conferma_chiede_conferma(self):
        _, stato, _ = bs.normalizza(self.campi(importo="30", categoria="Supermercato"))
        self.assertEqual(stato, "chiedi_conferma")

    def test_ordine_data_importo_categoria_sottocategoria(self):
        campi = self.campi(data="nonvalida", importo="boh", categoria="Pizza")
        _, stato, _ = bs.normalizza(campi)
        self.assertEqual(stato, "chiedi_data")
        campi["data"] = "01/09/2026"
        _, stato, _ = bs.normalizza(campi)
        self.assertEqual(stato, "chiedi_importo")
        campi["importo"] = "30"
        _, stato, _ = bs.normalizza(campi)
        self.assertEqual(stato, "chiedi_categoria")
        campi["categoria"] = "Cibo fuori / bevute"
        _, stato, _ = bs.normalizza(campi)
        self.assertEqual(stato, "chiedi_sottocategoria")

    def test_tassonomia_incoerente_non_arriva_alla_scrittura(self):
        rotta = [{"nome": "Ambigua", "id": 1, "tipo": "entrambi", "sottocategorie": []}]
        with mock.patch.object(bs, "_TASSONOMIA_CACHE", rotta):
            _, stato, _ = bs.normalizza(self.campi(importo="30", categoria="Ambigua"))
        self.assertEqual(stato, "errore_tassonomia")


class TestInterpretaConferma(unittest.TestCase):

    def test_si_in_tutte_le_forme(self):
        for t in ("sì", "Sì", "SI", "si ", "s", "ok", "OK", "va bene", "confermo", "Perfetto"):
            with self.subTest(t=t):
                self.assertEqual(bs.interpreta_conferma(t), "Si")

    def test_no_in_tutte_le_forme(self):
        for t in ("no", "No", "NO", "n", "annulla", "sbagliato", "lascia perdere"):
            with self.subTest(t=t):
                self.assertEqual(bs.interpreta_conferma(t), "No")

    def test_non_capito(self):
        for t in ("boh", "forse", "", "magari"):
            with self.subTest(t=t):
                self.assertEqual(bs.interpreta_conferma(t), "")

    def test_numeri_non_sono_conferme(self):
        # Sarebbero ambigui contro un numero di categoria.
        for t in ("1", "2"):
            with self.subTest(t=t):
                self.assertEqual(bs.interpreta_conferma(t), "")


class TestRisolviRisposta(unittest.TestCase):

    def test_ogni_domanda_instrada_al_suo_campo(self):
        casi = {
            "chiedi_data": ("01/09/2026", {"data": "01/09/2026"}),
            "chiedi_importo": ("12,50", {"importo": "12,50"}),
            "chiedi_categoria": ("3", {"categoria": "3"}),
            "chiedi_sottocategoria": ("5", {"sottocategoria": "5"}),
        }
        for stato, (testo, atteso) in casi.items():
            with self.subTest(stato=stato):
                self.assertEqual(bs.risolvi_risposta(stato, testo), atteso)

    def test_conferma_interpretata(self):
        self.assertEqual(bs.risolvi_risposta("chiedi_conferma", "sì"), {"conferma": "Si"})
        self.assertEqual(bs.risolvi_risposta("chiedi_conferma", "no"), {"conferma": "No"})


# ─────────────────────────────────────────────
# Messaggi: il testo completo da mostrare
# ─────────────────────────────────────────────

class TestMessaggi(unittest.TestCase):

    def messaggio(self, stato, campi=None, **kw):
        campi_pieni = bs.campi_vuoti()
        campi_pieni.update(campi or {})
        return bs.componi_messaggio(stato, campi_pieni, **kw)

    def test_elenco_categorie_dentro_il_messaggio(self):
        """Chi chiama deve avere una sola cosa da stampare: se il numero da
        digitare non e' gia' nel testo, qualcuno dovra' comporlo."""
        m = self.messaggio("chiedi_categoria")
        self.assertIn("Quale categoria? Rispondi con il numero.", m)
        self.assertIn("\n2. Supermercato", m)
        self.assertIn("\n17. Beneficienza", m)

    def test_i_numeri_sono_gli_id_della_tassonomia(self):
        m = self.messaggio("chiedi_categoria")
        for cat in bs.leggi_tassonomia():
            with self.subTest(cat=cat["nome"]):
                self.assertIn(f"\n{cat['id']}. {cat['nome']}", "\n" + m)

    def test_elenco_sottocategorie_dentro_il_messaggio(self):
        m = self.messaggio("chiedi_sottocategoria", {"categoria": "Cibo fuori / bevute"})
        self.assertIn("Quale sottocategoria di «Cibo fuori / bevute»?", m)
        self.assertIn("\n5. Ristorante", m)

    def test_riepilogo_completo_dentro_il_messaggio(self):
        m = self.messaggio("chiedi_conferma", {
            "importo": 30.0, "data": "01/09/2026", "categoria": "Cibo fuori / bevute",
            "sottocategoria": "Ristorante", "descrizione": "Trattoria da Nino"}, tipo="Uscita")
        atteso = ("Importo:        30.00 €\n"
                  "Data:           01/09/2026\n"
                  "Tipo:           Uscita\n"
                  "Categoria:      Cibo fuori / bevute\n"
                  "Sottocategoria: Ristorante\n"
                  "Descrizione:    Trattoria da Nino\n"
                  "Note:           —\n\n"
                  "Confermi?")
        self.assertEqual(m, atteso)

    def test_valore_rifiutato_citato(self):
        self.assertIn("«30 €»", self.messaggio("chiedi_importo", rifiutato="30 €"))
        self.assertIn("«Pizzeria»", self.messaggio("chiedi_categoria", rifiutato="Pizzeria"))
        self.assertIn("«31/02/2026»", self.messaggio("chiedi_data", rifiutato="31/02/2026"))

    def test_stati_terminali_hanno_un_testo(self):
        for stato in ("scritto", "annullata", "bozza_scaduta", "bozza_assente",
                      "errore_auth", "errore_scrittura", "errore_tassonomia"):
            with self.subTest(stato=stato):
                self.assertTrue(self.messaggio(stato, {"categoria": "Ambigua"}).strip())


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

class TestCli(ConBozza):

    def esegui(self, *argv):
        """Un giro di main(), senza rete. Restituisce (payload, exit, stderr)."""
        self.scritte = []

        def finto_append_row(token, data, tipo, categoria, sottocategoria, importo, descrizione, note):
            self.scritte.append({"data": data, "tipo": tipo, "categoria": categoria,
                                 "sottocategoria": sottocategoria, "importo": importo,
                                 "descrizione": descrizione, "note": note})
            return "Transazioni 2026!A42:G42"

        out, err, code = io.StringIO(), io.StringIO(), 0
        with mock.patch.object(sys, "argv", ["budget_sheets.py"] + list(argv)), \
             mock.patch.object(bs, "get_access_token", return_value="token-finto"), \
             mock.patch.object(bs, "append_row", side_effect=finto_append_row), \
             mock.patch("urllib.request.urlopen",
                        side_effect=AssertionError("i test non devono toccare la rete")):
            try:
                with redirect_stdout(out), redirect_stderr(err):
                    bs.main()
            except SystemExit as e:
                code = e.code or 0
        try:
            payload = json.loads(out.getvalue())
        except ValueError:
            payload = None
        return payload, code, err.getvalue()

    def test_forma_del_payload(self):
        payload, code, _ = self.esegui("append", "--nuova", "--importo", "30")
        self.assertEqual(set(payload), CHIAVI)
        self.assertEqual(code, 3)

    def test_dialogo_bloccato_non_autentica_nemmeno(self):
        with mock.patch.object(bs, "get_access_token") as m:
            with mock.patch.object(sys, "argv", ["budget_sheets.py", "append", "--nuova"]):
                with redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        bs.main()
        m.assert_not_called()

    def test_lo_stato_sopravvive_fra_le_chiamate(self):
        """Il cuore della riscrittura: al secondo giro si passa SOLO la risposta."""
        self.esegui("append", "--nuova", "--importo", "30", "--categoria", "3",
                    "--descrizione", "Trattoria da Nino")
        payload, code, _ = self.esegui("append", "--risposta", "5")
        self.assertEqual(payload["stato"], "chiedi_conferma")
        self.assertEqual(payload["importo"], 30.0)
        self.assertEqual(payload["categoria"], "Cibo fuori / bevute")
        self.assertEqual(payload["sottocategoria"], "Ristorante")
        self.assertEqual(payload["descrizione"], "Trattoria da Nino")
        self.assertEqual(payload["tipo"], "Uscita")

    def test_scrittura_dopo_conferma(self):
        self.esegui("append", "--nuova", "--data", "01/09/2026", "--importo", "30",
                    "--categoria", "Cibo fuori / bevute", "--sottocategoria", "Ristorante",
                    "--descrizione", "Trattoria da Nino")
        payload, code, _ = self.esegui("append", "--risposta", "sì")
        self.assertEqual(code, 0)
        self.assertEqual(payload["stato"], "scritto")
        self.assertEqual(payload["intervallo"], "Transazioni 2026!A42:G42")
        self.assertEqual(self.scritte, [{
            "data": "01/09/2026", "tipo": "Uscita", "categoria": "Cibo fuori / bevute",
            "sottocategoria": "Ristorante", "importo": 30.0,
            "descrizione": "Trattoria da Nino", "note": ""}])
        self.assertFalse(os.path.exists(self.bozza), "la bozza va cancellata dopo la scrittura")

    def test_la_descrizione_arriva_sul_foglio_senza_essere_ripassata(self):
        """Prima descrizione e note scavalcavano la validazione: se chi chiamava
        le perdeva, nessuno le richiedeva e la riga arrivava muta e sbagliata."""
        self.esegui("append", "--nuova", "--importo", "30", "--descrizione", "Trattoria da Nino")
        self.esegui("append", "--risposta", "3")
        self.esegui("append", "--risposta", "5")
        self.esegui("append", "--risposta", "sì")
        self.assertEqual(self.scritte[0]["descrizione"], "Trattoria da Nino")

    def test_senza_conferma_non_scrive(self):
        self.esegui("append", "--nuova", "--importo", "30", "--categoria", "Supermercato")
        self.assertEqual(self.scritte, [])

    def test_nuova_scarta_la_bozza_precedente(self):
        self.esegui("append", "--nuova", "--importo", "30", "--categoria", "Auto / Moto")
        payload, _, _ = self.esegui("append", "--nuova", "--importo", "85")
        self.assertEqual(payload["categoria"], "", "--nuova deve ripartire da zero")
        self.assertEqual(payload["importo"], 85.0)

    def test_senza_nuova_i_campi_si_fondono(self):
        """Nel dubbio si fonde e si richiede conferma, mai si scarta: una fusione
        sbagliata l'utente la vede nel riepilogo e la rifiuta in un turno."""
        self.esegui("append", "--nuova", "--importo", "50", "--categoria", "Auto / Moto",
                    "--sottocategoria", "Benzina")
        payload, _, _ = self.esegui("append", "--importo", "85")
        self.assertEqual(payload["stato"], "chiedi_conferma")
        self.assertEqual(payload["importo"], 85.0)
        self.assertEqual(payload["categoria"], "Auto / Moto")
        self.assertEqual(self.scritte, [], "niente arriva sul foglio senza conferma")

    def test_dopo_la_scrittura_si_riparte_puliti(self):
        """La bozza cancellata e' quello che impedisce alla transazione appena
        registrata di contaminare la successiva."""
        self.esegui("append", "--nuova", "--importo", "30", "--categoria", "Supermercato")
        self.esegui("append", "--risposta", "sì")
        payload, _, _ = self.esegui("append", "--importo", "40")
        self.assertEqual(payload["categoria"], "", "la categoria di prima non deve sopravvivere")
        self.assertEqual(payload["stato"], "chiedi_categoria")

    def test_no_al_riepilogo_tiene_data_e_importo(self):
        self.esegui("append", "--nuova", "--importo", "30", "--categoria", "Supermercato")
        payload, _, _ = self.esegui("append", "--risposta", "no")
        self.assertEqual(payload["stato"], "chiedi_categoria")
        self.assertEqual(payload["importo"], 30.0)
        self.assertEqual(payload["categoria"], "")

    def test_conferma_non_capita_rimostra_il_riepilogo(self):
        self.esegui("append", "--nuova", "--importo", "30", "--categoria", "Supermercato")
        payload, _, _ = self.esegui("append", "--risposta", "boh")
        self.assertEqual(payload["stato"], "chiedi_conferma")
        self.assertIn("Non ho capito", payload["messaggio"])
        self.assertEqual(self.scritte, [])

    def test_annulla(self):
        self.esegui("append", "--nuova", "--importo", "30", "--categoria", "Supermercato")
        payload, code, _ = self.esegui("append", "--annulla")
        self.assertEqual(payload["stato"], "annullata")
        self.assertEqual(code, 3)
        self.assertFalse(os.path.exists(self.bozza))

    def test_risposta_senza_bozza(self):
        payload, code, _ = self.esegui("append", "--risposta", "5")
        self.assertEqual(payload["stato"], "bozza_assente")
        self.assertEqual(code, 3)

    def test_risposta_su_bozza_scaduta(self):
        self.scrivi_bozza("chiedi_categoria", {"importo": 30.0},
                          aggiornato=time.time() - bs.BOZZA_TTL - 60)
        payload, _, _ = self.esegui("append", "--risposta", "3")
        self.assertEqual(payload["stato"], "bozza_scaduta")

    def test_ogni_turno_rinfresca_la_scadenza(self):
        """La scadenza e' di inattivita', non di eta': un dialogo lento non deve
        morire a meta'."""
        quasi = bs.BOZZA_TTL - 60
        self.esegui("append", "--nuova", "--importo", "30")
        for risposta in ("3", "5"):
            b = bs.carica_bozza()
            bs.salva_bozza(b["stato"], b["campi"], ora=time.time() - quasi)
            payload, _, _ = self.esegui("append", "--risposta", risposta)
            self.assertNotEqual(payload["stato"], "bozza_scaduta")
        self.assertEqual(payload["stato"], "chiedi_conferma")

    def test_errore_di_scrittura_conserva_la_bozza(self):
        self.esegui("append", "--nuova", "--importo", "30", "--categoria", "Supermercato")
        with mock.patch.object(bs, "append_row", side_effect=RuntimeError("HTTP 500")):
            with mock.patch.object(sys, "argv",
                                   ["budget_sheets.py", "append", "--risposta", "sì"]), \
                 mock.patch.object(bs, "get_access_token", return_value="t"):
                out, err = io.StringIO(), io.StringIO()
                with self.assertRaises(SystemExit) as cm:
                    with redirect_stdout(out), redirect_stderr(err):
                        bs.main()
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(json.loads(out.getvalue())["stato"], "errore_scrittura")
        self.assertIn("HTTP 500", err.getvalue())
        self.assertIsInstance(bs.carica_bozza(), dict,
                              "la bozza serve per riprovare con una parola sola")

    def test_errore_di_autenticazione_conserva_la_bozza(self):
        self.esegui("append", "--nuova", "--importo", "30", "--categoria", "Supermercato")
        with mock.patch.object(sys, "argv", ["budget_sheets.py", "append", "--risposta", "sì"]), \
             mock.patch.object(bs, "get_access_token", side_effect=RuntimeError("token morto")):
            out, err = io.StringIO(), io.StringIO()
            with self.assertRaises(SystemExit) as cm:
                with redirect_stdout(out), redirect_stderr(err):
                    bs.main()
        self.assertEqual(cm.exception.code, 1)
        self.assertEqual(json.loads(out.getvalue())["stato"], "errore_auth")
        self.assertIsInstance(bs.carica_bozza(), dict)

    def test_una_scrittura_in_corso_non_ne_fa_partire_una_seconda(self):
        """Un doppione su un foglio di spese non lo nota nessuno, quindi il turno
        che trova il marcatore si ferma invece di rimandare la stessa riga."""
        self.esegui("append", "--nuova", "--importo", "30", "--categoria", "Supermercato")
        b = bs.carica_bozza()
        bs.salva_bozza("scrittura_in_corso", b["campi"])
        payload, code, _ = self.esegui("append", "--risposta", "sì")
        self.assertEqual(payload["stato"], "scrittura_in_corso")
        self.assertEqual(code, 3)
        self.assertEqual(self.scritte, [])

    def test_la_bozza_e_marcata_prima_di_uscire_dal_lock(self):
        """Il marcatore deve essere gia' su disco quando parte la chiamata a
        Google, o la finestra del doppione resta aperta."""
        visto = []
        self.esegui("append", "--nuova", "--importo", "30", "--categoria", "Supermercato")

        def spia(*a, **kw):
            visto.append(bs.carica_bozza()["stato"])
            return "Transazioni 2026!A42:G42"

        with mock.patch.object(bs, "append_row", side_effect=spia):
            with mock.patch.object(sys, "argv", ["budget_sheets.py", "append", "--risposta", "sì"]), \
                 mock.patch.object(bs, "get_access_token", return_value="t"):
                with self.assertRaises(SystemExit):
                    with redirect_stdout(io.StringIO()):
                        bs.main()
        self.assertEqual(visto, ["scrittura_in_corso"])

    def test_scrittura_fallita_riporta_alla_conferma_senza_il_si(self):
        """Altrimenti il turno dopo riscriverebbe da solo, senza che nessuno
        abbia riconfermato."""
        self.esegui("append", "--nuova", "--importo", "30", "--categoria", "Supermercato")
        with mock.patch.object(bs, "append_row", side_effect=RuntimeError("HTTP 500")):
            with mock.patch.object(sys, "argv", ["budget_sheets.py", "append", "--risposta", "sì"]), \
                 mock.patch.object(bs, "get_access_token", return_value="t"):
                with self.assertRaises(SystemExit):
                    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                        bs.main()
        b = bs.carica_bozza()
        self.assertEqual(b["stato"], "chiedi_conferma")
        self.assertEqual(b["campi"]["conferma"], "")
        self.assertEqual(b["campi"]["importo"], 30.0, "il resto non si perde")

    def test_errore_tassonomia_non_blocca_la_bozza(self):
        """Non e' una domanda: salvarlo come stato lascerebbe la bozza in un punto
        a cui nessuna risposta sa rispondere."""
        self.esegui("append", "--nuova", "--importo", "30", "--categoria", "Cibo fuori / bevute")
        prima = bs.carica_bozza()["stato"]
        rotta = [{"nome": "Cibo fuori / bevute", "id": 3, "tipo": "entrambi",
                  "sottocategorie": [{"nome": "Ristorante", "id": 5, "tipo": None}]}]
        with mock.patch.object(bs, "_TASSONOMIA_CACHE", rotta):
            self.esegui("append", "--risposta", "5")
        self.assertEqual(bs.carica_bozza()["stato"], prima,
                         "la bozza di prima deve restare dov'era")

    def test_bozza_scritta_con_permessi_stretti(self):
        self.esegui("append", "--nuova", "--importo", "30")
        self.assertEqual(os.stat(self.bozza).st_mode & 0o777, 0o600)

    def test_bozza_non_salvabile_lo_dice_invece_di_esplodere(self):
        """Senza bozza il turno dopo non avrebbe un contesto: meglio fermarsi con
        una frase che fare una domanda di cui si perdera' la risposta."""
        with mock.patch.object(bs, "salva_bozza", side_effect=OSError("sola lettura")):
            payload, code, err = self.esegui("append", "--nuova", "--importo", "30")
        self.assertEqual(payload["stato"], "errore_bozza")
        self.assertEqual(code, 6)
        self.assertIn("sola lettura", err, "il dettaglio tecnico va nei log")
        self.assertNotIn("Traceback", payload["messaggio"])

    def test_tassonomia_incoerente_non_scrive(self):
        rotta = [{"nome": "Ambigua", "id": 1, "tipo": "entrambi", "sottocategorie": []}]
        with mock.patch.object(bs, "_TASSONOMIA_CACHE", rotta):
            payload, code, _ = self.esegui("append", "--nuova", "--importo", "30",
                                           "--categoria", "Ambigua")
        self.assertEqual(payload["stato"], "errore_tassonomia")
        self.assertEqual(code, 5)
        self.assertEqual(self.scritte, [])

    def test_mai_una_sottocategoria_senza_opzioni(self):
        """L'invariante che elimina il loop senza uscita, vista dalla CLI."""
        for cat in bs.leggi_tassonomia():
            with self.subTest(cat=cat["nome"]):
                payload, _, _ = self.esegui("append", "--nuova", "--importo", "30",
                                            "--categoria", str(cat["id"]),
                                            "--sottocategoria", "Altro")
                if payload["stato"] == "chiedi_sottocategoria":
                    self.assertTrue(payload["opzioni"])

    def test_flag_conferma_non_esiste_piu(self):
        for argv in (["append", "--conferma", "Si"], ["append", "--tipo", "Uscita"]):
            with self.subTest(argv=argv):
                r = subprocess.run(
                    [sys.executable, SCRIPT] + argv,
                    capture_output=True, text=True,
                    env={**os.environ, "BUDGET_BOZZA_FILE": self.bozza})
                self.assertEqual(r.returncode, 64)
                self.assertIn("unrecognized arguments", r.stderr)

    def test_senza_sottocomando_esce_64(self):
        r = subprocess.run(
            [sys.executable, SCRIPT],
            capture_output=True, text=True,
            env={**os.environ, "BUDGET_BOZZA_FILE": self.bozza})
        self.assertEqual(r.returncode, 64)

    def test_subprocess_reale_non_scrive_senza_conferma(self):
        """L'unico test che lancia lo script davvero: senza conferma non deve
        arrivare a chiedere un token, quindi non puo' toccare Google."""
        r = subprocess.run(
            [sys.executable, SCRIPT,
             "append", "--nuova", "--importo", "30", "--categoria", "Supermercato"],
            capture_output=True, text=True,
            env={**os.environ, "BUDGET_BOZZA_FILE": self.bozza})
        self.assertEqual(r.returncode, 3)
        self.assertEqual(json.loads(r.stdout)["stato"], "chiedi_conferma")


# ─────────────────────────────────────────────
# Strato di rete (sempre sotto mock)
# ─────────────────────────────────────────────

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


def _errore_http(code, corpo=b"{}"):
    return urllib.error.HTTPError("https://esempio", code, "errore", {}, io.BytesIO(corpo))


class TestAuth(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.token_file = os.path.join(self.dir.name, "token.json")
        self.cred_file = os.path.join(self.dir.name, "cred.json")
        with open(self.cred_file, "w") as f:
            json.dump({"installed": {"client_id": "cid", "client_secret": "csec"}}, f)
        p1 = mock.patch.object(bs, "TOKEN_FILE", self.token_file)
        p2 = mock.patch.object(bs, "CRED_FILE", self.cred_file)
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)

    def scrivi_token(self, **kw):
        dati = {"access_token": "vecchio", "refresh_token": "rt", "expires_at": 0}
        dati.update(kw)
        with open(self.token_file, "w") as f:
            json.dump(dati, f)
        return dati

    def leggi_token(self):
        with open(self.token_file) as f:
            return json.load(f)

    def test_credenziali_lette_da_qualunque_chiave_di_primo_livello(self):
        self.assertEqual(bs._load_creds(), ("cid", "csec"))

    def test_token_in_cache_riusato(self):
        self.scrivi_token(access_token="buono", expires_at=time.time() + 3600)
        with mock.patch.object(bs, "_do_refresh") as m:
            self.assertEqual(bs.get_access_token(), "buono")
        m.assert_not_called()

    def test_token_quasi_scaduto_viene_rinnovato(self):
        # margine di 60 s: a 30 s dalla scadenza si rinnova comunque
        self.scrivi_token(access_token="quasi", expires_at=time.time() + 30)
        with mock.patch.object(bs, "_do_refresh",
                               return_value={"access_token": "nuovo", "expires_in": 3600}) as m:
            self.assertEqual(bs.get_access_token(), "nuovo")
        m.assert_called_once_with("rt", "cid", "csec")
        self.assertGreater(self.leggi_token()["expires_at"], time.time())

    def test_refresh_token_preservato_se_google_non_ne_manda_uno_nuovo(self):
        self.scrivi_token()
        with mock.patch.object(bs, "_do_refresh",
                               return_value={"access_token": "nuovo", "expires_in": 3600}):
            bs.get_access_token()
        self.assertEqual(self.leggi_token()["refresh_token"], "rt")

    def test_refresh_token_aggiornato_se_google_ne_manda_uno_nuovo(self):
        self.scrivi_token()
        with mock.patch.object(bs, "_do_refresh",
                               return_value={"access_token": "n", "expires_in": 3600,
                                             "refresh_token": "rt2"}):
            bs.get_access_token()
        self.assertEqual(self.leggi_token()["refresh_token"], "rt2")

    def test_refresh_revocato_spiega_come_rimediare(self):
        with mock.patch("urllib.request.urlopen",
                        side_effect=_errore_http(400, b'{"error":"invalid_grant"}')):
            with self.assertRaises(RuntimeError) as cm:
                bs._do_refresh("rt", "cid", "csec")
        self.assertIn("setup.py", str(cm.exception))

    def test_altro_errore_oauth_propagato(self):
        with mock.patch("urllib.request.urlopen",
                        side_effect=_errore_http(500, b'{"error":"server"}')):
            with self.assertRaises(RuntimeError) as cm:
                bs._do_refresh("rt", "cid", "csec")
        self.assertIn("Errore OAuth 500", str(cm.exception))

    def test_token_mancante_e_un_errore_di_autenticazione(self):
        os.path.exists(self.token_file) and os.remove(self.token_file)
        with self.assertRaises(FileNotFoundError):
            bs.get_access_token()


class TestApiRequest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.token_file = os.path.join(self.dir.name, "token.json")
        with open(self.token_file, "w") as f:
            json.dump({"access_token": "vecchio", "refresh_token": "rt", "expires_at": 0}, f)
        p = mock.patch.object(bs, "TOKEN_FILE", self.token_file)
        p.start(); self.addCleanup(p.stop)

    def test_chiamata_riuscita(self):
        with mock.patch("urllib.request.urlopen", return_value=_Risposta({"ok": 1})) as m:
            risultato, token = bs._api_request("GET", "https://esempio/x", "t")
        self.assertEqual(risultato, {"ok": 1})
        self.assertEqual(token, "t")
        richiesta = m.call_args[0][0]
        self.assertEqual(richiesta.get_header("Authorization"), "Bearer t")

    def test_401_rinnova_il_token_e_riprova_una_volta(self):
        with mock.patch("urllib.request.urlopen",
                        side_effect=[_errore_http(401), _Risposta({"ok": 2})]) as m, \
             mock.patch.object(bs, "_load_creds", return_value=("cid", "csec")), \
             mock.patch.object(bs, "_do_refresh",
                               return_value={"access_token": "rinnovato", "expires_in": 3600}):
            risultato, token = bs._api_request("GET", "https://esempio/x", "scaduto")
        self.assertEqual(risultato, {"ok": 2})
        self.assertEqual(token, "rinnovato")
        self.assertEqual(m.call_count, 2)
        self.assertEqual(m.call_args[0][0].get_header("Authorization"), "Bearer rinnovato")

    def test_401_due_volte_non_va_in_loop(self):
        with mock.patch("urllib.request.urlopen",
                        side_effect=[_errore_http(401), _errore_http(401, b"no")]) as m, \
             mock.patch.object(bs, "_load_creds", return_value=("cid", "csec")), \
             mock.patch.object(bs, "_do_refresh",
                               return_value={"access_token": "r", "expires_in": 3600}):
            with self.assertRaises(RuntimeError) as cm:
                bs._api_request("GET", "https://esempio/x", "scaduto")
        self.assertEqual(m.call_count, 2)
        self.assertIn("HTTP Error 401", str(cm.exception))

    def test_altri_errori_non_vengono_ritentati(self):
        with mock.patch("urllib.request.urlopen", side_effect=_errore_http(500, b"boom")) as m:
            with self.assertRaises(RuntimeError) as cm:
                bs._api_request("GET", "https://esempio/x", "t")
        self.assertEqual(m.call_count, 1)
        self.assertIn("HTTP Error 500", str(cm.exception))

    def test_post_serializza_il_corpo(self):
        with mock.patch("urllib.request.urlopen", return_value=_Risposta({})) as m:
            bs._api_request("POST", "https://esempio/x", "t", body={"values": [[1]]})
        richiesta = m.call_args[0][0]
        self.assertEqual(richiesta.get_method(), "POST")
        self.assertEqual(json.loads(richiesta.data), {"values": [[1]]})
        self.assertEqual(richiesta.get_header("Content-type"), "application/json")


class TestAppendRow(unittest.TestCase):

    def esegui(self, risposta, **kw):
        argomenti = dict(data="01/09/2026", tipo="Uscita", categoria="Cibo fuori / bevute",
                         sottocategoria="Ristorante", importo=30.0,
                         descrizione="Trattoria da Nino", note="")
        argomenti.update(kw)
        with mock.patch("urllib.request.urlopen", return_value=_Risposta(risposta)) as m:
            esito = bs.append_row("t", **argomenti)
        return esito, m.call_args[0][0]

    def test_riga_nellordine_delle_colonne_del_foglio(self):
        _, richiesta = self.esegui({"updates": {"updatedRange": "X!A1:G1"}})
        self.assertEqual(
            json.loads(richiesta.data)["values"],
            [["01/09/2026", "Uscita", "Cibo fuori / bevute", "Ristorante", 30.0,
              "Trattoria da Nino", ""]],
        )

    def test_url_punta_al_foglio_configurato(self):
        _, richiesta = self.esegui({"updates": {"updatedRange": "X!A1:G1"}})
        url = richiesta.full_url
        self.assertIn(urllib.parse.quote(bs.GOOGLE_SHEET_NAME), url)
        self.assertIn(bs.SPREADSHEET_ID, url)
        self.assertIn("!A:G:append", url)
        self.assertIn("valueInputOption=USER_ENTERED", url)
        self.assertIn("insertDataOption=INSERT_ROWS", url)

    def test_restituisce_lintervallo_aggiornato(self):
        esito, _ = self.esegui({"updates": {"updatedRange": "Transazioni 2026!A42:G42"}})
        self.assertEqual(esito, "Transazioni 2026!A42:G42")

    def test_risposta_senza_intervallo(self):
        esito, _ = self.esegui({})
        self.assertEqual(esito, "?")

    def test_importo_scritto_come_numero_non_come_testo(self):
        _, richiesta = self.esegui({"updates": {}}, importo="30.00")
        self.assertEqual(json.loads(richiesta.data)["values"][0][4], 30.0)



if __name__ == "__main__":
    unittest.main(verbosity=2)
