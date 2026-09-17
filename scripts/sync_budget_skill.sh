#!/bin/bash
# Sync del plugin budget-familiare verso GitHub.
# Gira ogni 30 minuti via cron.
#
# NOTA: e' una soluzione di passaggio. La strada giusta col plugin e'
#   hermes plugins install l33tleandrew/budget-familiare-workflow --ref <sha-40>
# che porta con se' scan di sicurezza, provenienza registrata e pin a un commit
# esatto (i ref devono essere SHA di 40 caratteri: tag e branch vengono rifiutati).
#
# Il percorso non e' piu' quello della skill: il plugin vive sotto plugins/. La
# doc di Hermes indica ~/.hermes/plugins/, ma questa installazione ha un
# HERMES_HOME suo, quindi il valore vero si legge con `hermes plugins list`.

PLUGIN_DIR="${BUDGET_PLUGIN_DIR:-/opt/data/profiles/budgetingagent/plugins/budget-familiare}"

cd "$PLUGIN_DIR" || {
  echo "directory del plugin non trovata: $PLUGIN_DIR" >&2
  echo "impostala con BUDGET_PLUGIN_DIR, o leggila da \`hermes plugins list\`" >&2
  exit 0
}

# Niente da fare?
if git diff --quiet && git diff --cached --quiet; then
  exit 0
fi

git add -A

TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
git commit -m "auto-sync: $TIMESTAMP"

git push origin main

echo "Pushed plugin changes to GitHub at $TIMESTAMP"
