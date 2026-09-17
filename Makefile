# Suite offline del plugin: nessuna rete, nessuna riga su Google Sheets.
PY ?= python3

.DEFAULT_GOAL := test
.PHONY: test plugin eval eval-smemorato eval-modello

test: ## Tutto: script, plugin, coerenza dello schema ed eval deterministica
	$(PY) -m unittest discover -s tests -p "*.py" -v

plugin: ## Solo il plugin: manifest, registrazioni, middleware, hook
	$(PY) -m unittest tests.test_plugin -v

eval: ## Eval deterministica con le trascrizioni delle conversazioni
	$(PY) tests/eval_protocollo.py

eval-smemorato: ## Eval avversariale: il modello che non ricorda niente deve arrivare in fondo
	$(PY) -m tests.eval_smemorato

eval-modello: ## Eval col modello: chiamate a pagamento, serve `pip install anthropic`
	$(PY) tests/eval_modello.py --esegui
