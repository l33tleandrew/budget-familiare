"""Dove stanno le cose, in un posto solo.

Quattro file di test ricostruivano il layout a mano con dei dirname annidati:
alla prima riorganizzazione si sarebbero rotti tutti e quattro, uno alla volta e
con quattro errori diversi.

La radice del repo E' la radice del plugin: e' quello che Hermes si aspetta di
trovare sotto ~/.hermes/plugins/<nome>/, quindi il repo si clona li' dentro e
basta.

Questo modulo e' anche l'unico punto che ogni file di test importa *prima* di
budget_sheets, quindi e' l'unico da cui si possa fissare l'ambiente che lo script
legge all'import. Sotto ce n'e' uno solo, ed e' spiegato dov'e'.
"""
import os
from datetime import datetime

os.environ.setdefault("ANNO_BUDGET", str(datetime.now().year))

REPO        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT      = os.path.join(REPO, "budget_sheets.py")
SCRIPTS     = REPO                       # lo script sta alla radice del plugin
TASSONOMIA  = os.path.join(REPO, "tassonomia.yaml")
PLUGIN_YAML = os.path.join(REPO, "plugin.yaml")
SCHEMAS     = os.path.join(REPO, "schemas.py")
