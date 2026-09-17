# budget-familiare

Plugin [Hermes Agent](https://hermes-agent.nousresearch.com) che registra spese
ed entrate sul foglio Budget di Google Sheets, conducendo il dialogo con
l'utente un campo alla volta.

```
utente  │ benzina 50
agente  │ Quale categoria? Rispondi con il numero.
        │ 1. Stipendio
        │ 2. Supermercato
        │ …
utente  │ 4
agente  │ Quale sottocategoria di «Auto / Moto»? …
```

## Installazione

```bash
hermes plugins install l33tleandrew/budget-familiare-workflow --ref <sha-40>
hermes plugins enable budget-familiare
hermes plugins list        # ✓ budget-familiare v1.0.0 (1 tools, 4 hooks)
```

I plugin generali sono disabilitati di default: senza `enable` non carica. Il
`--ref` vuole uno SHA esatto di 40 caratteri — tag e branch vengono rifiutati.

La radice del repo **è** la radice del plugin, quindi in alternativa si clona
direttamente al posto giusto — la directory va chiamata come il plugin, non come
il repo:

```bash
git clone https://github.com/l33tleandrew/budget-familiare-workflow.git \
    <HERMES_HOME>/plugins/budget-familiare
hermes plugins doctor <HERMES_HOME>/plugins/budget-familiare --ci
hermes plugins enable budget-familiare
```

### Credenziali

Lo script si aspetta, nel profilo (`PROFILE_DIR` in `budget_sheets.py`):

| File | Cosa contiene |
|---|---|
| `google_client_secret.json` | credenziali OAuth del progetto Google Cloud |
| `google_token.json` | token con refresh, dal primo consenso |

ID del foglio, nome della scheda e percorso del profilo sono costanti in cima a
`budget_sheets.py`.

## Com'è fatto

Lo stato del dialogo vive su disco, gestito da `budget_sheets.py`: TTL, lock,
marcatore anti-doppione, validazione, e i messaggi all'utente composti per
intero in Python. Il plugin non riscrive niente di tutto questo — toglie al
modello quello che non è comprensione del linguaggio, una superficie per volta.

```
budget-familiare/
├── plugin.yaml          manifest: tool e hook dichiarati
├── __init__.py          register(ctx): le cinque superfici di vincolo
├── schemas.py           schema del tool — qui vive il trigger
├── tools.py             handler + la cassetta della resa verbatim
├── budget_sheets.py     il motore: macchina a stati, bozza, Google Sheets
└── tassonomia.yaml      le categorie (dato, non codice)
```

| Superficie | Cosa toglie al modello |
|---|---|
| `register_tool` | la shell: argomenti tipizzati, nessun quoting |
| middleware `tool_request` | l'instradamento: `nuova` si legge dal disco |
| `pre_llm_call` | la memoria: lo stato reiniettato a ogni turno |
| `transform_llm_output` | la parafrasi: la risposta è il testo dello script |
| `pre_tool_call` | le scorciatoie: lo script shellato viene bloccato |

Resta probabilistico un punto solo: se «8,5» a freddo faccia scattare il tool.
`/spesa 8,5` è la via esplicita quando non scatta.

**Non c'è nessuna SKILL.md, ed è deliberato.** Una skill impacchettata in un
plugin non compare nell'index né in `skills_list`: si carica solo con un
`skill_view()` esplicito, quindi nessuno la leggerebbe mai. Tutto quello che il
modello deve sapere — quando attivarsi, cosa estrarre, come passarlo — sta nella
descrizione del tool e in quelle dei suoi parametri, in [schemas.py](schemas.py),
che il system prompt porta con sé a ogni turno.

Lo script resta una CLI funzionante, per l'uso a mano da un terminale:

```bash
python3 budget_sheets.py append --importo 30 --categoria Sport
```

## Test

```bash
make test             # 263 test, nessuna rete, nessuna riga sul foglio
make plugin           # solo il plugin
make eval             # rigioca le conversazioni di tests/casi_eval.json
make eval-smemorato   # un modello che non ricorda niente deve arrivare in fondo
```

Dettagli in [tests/README.md](tests/README.md).
