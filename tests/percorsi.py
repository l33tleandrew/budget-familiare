"""Dove stanno le cose, in un posto solo.

Quattro file di test ricostruivano il layout a mano con dei dirname annidati:
alla prima riorganizzazione si sarebbero rotti tutti e quattro, uno alla volta e
con quattro errori diversi.

La radice del repo E' la radice del plugin: e' quello che Hermes si aspetta di
trovare sotto ~/.hermes/plugins/<nome>/, quindi il repo si clona li' dentro e
basta.

Questo modulo e' anche l'unico punto che ogni file di test importa *prima* di
budget_sheets, quindi e' l'unico da cui si possa fissare l'ambiente che lo script
legge all'import. Ogni riga qui sotto e' spiegata dov'e'.
"""
import atexit
import os
import shutil
import tempfile
from datetime import datetime

# Un profilo Hermes vuoto, sempre, anche quando la suite gira sul server: li' il
# repo sta dentro il profilo vero, e lo script lo ricaverebbe dalla sua
# posizione. Token, credenziali, .env e bozza non devono essere raggiungibili.
# Assegnato e non setdefault: un BUDGET_PROFILE_DIR rimasto esportato nella
# shell potrebbe puntare proprio al profilo vero.
os.environ["BUDGET_PROFILE_DIR"] = tempfile.mkdtemp(prefix="budget_test_profilo_")
atexit.register(shutil.rmtree, os.environ["BUDGET_PROFILE_DIR"], True)

# La configurazione dell'istanza. setdefault, cosi' `ANNO_BUDGET=2025 make test`
# resta una prova possibile. L'anno e' quello civile: altrimenti la guardia sul
# cambio d'anno renderebbe rossa in blocco ogni prova che esegue un turno.
os.environ.setdefault("ANNO_BUDGET", str(datetime.now().year))
os.environ.setdefault("GOOGLE_SPREADSHEET_ID", "foglio-di-prova")

REPO        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT      = os.path.join(REPO, "budget_sheets.py")
SCRIPTS     = REPO                       # lo script sta alla radice del plugin
TASSONOMIA  = os.path.join(REPO, "tassonomia.yaml")
PLUGIN_YAML = os.path.join(REPO, "plugin.yaml")
SCHEMAS     = os.path.join(REPO, "schemas.py")
