# Architettura — budget-familiare

> Documento di riferimento sullo **stato attuale** del sistema: com'è fatto, perché è
> fatto così, e dove mettere le mani per cambiarlo. Descrive il codice com'è oggi, non
> come dovrebbe essere. Quando il codice cambia, cambia anche questo file.

**Versione plugin:** 1.0.0 · **Ultimo allineamento:** 2026-09-19 · **Commit:** `8071fae`

---

## Indice

1. [Scopo e contesto](#1-scopo-e-contesto)
2. [Il principio architetturale](#2-il-principio-architetturale)
3. [Mappa dei file](#3-mappa-dei-file)
4. [I componenti, uno per uno](#4-i-componenti-uno-per-uno)
5. [Il flusso di un turno](#5-il-flusso-di-un-turno)
6. [La macchina a stati](#6-la-macchina-a-stati)
7. [Albero decisionale completo](#7-albero-decisionale-completo)
8. [Modello dei dati](#8-modello-dei-dati)
9. [Concorrenza, durabilità, idempotenza](#9-concorrenza-durabilità-idempotenza)
10. [Invarianti da non rompere](#10-invarianti-da-non-rompere)
11. [Configurazione e deploy](#11-configurazione-e-deploy)
12. [Test ed eval](#12-test-ed-eval)
13. [Playbook: come fare le modifiche comuni](#13-playbook-come-fare-le-modifiche-comuni)
14. [Debito noto e problemi aperti](#14-debito-noto-e-problemi-aperti)
15. [Glossario](#15-glossario)

---

## 1. Scopo e contesto

### Cosa fa

`budget-familiare` è un plugin per [Hermes Agent](https://hermes-agent.nousresearch.com)
che registra spese ed entrate della famiglia su un foglio Google Sheets. L'utente scrive
in linguaggio naturale («benzina 50», «cena fuori ieri 30», «8,5») e il sistema conduce un
dialogo a domande chiuse fino a raccogliere tutti i campi obbligatori, mostra un riepilogo,
chiede conferma e solo allora scrive una riga sul foglio.

### Il problema che risolve

Il motore (`budget_sheets.py`) esisteva già come CLI, ed era già una macchina a stati
completa: stato su disco con TTL, lock, marcatore anti-doppione, validazione, messaggi
all'utente composti interamente in Python.

**Il non-determinismo non stava nel motore, stava nel modo in cui ci si arrivava.** Il
modello shellava un comando da terminale, decideva lui quale flag passare, decideva lui a
quale campo apparteneva la risposta dell'utente, e il testo che l'utente leggeva era una
sua parafrasi del JSON di ritorno. Ogni turno era un'occasione di sbagliare:

- dimenticare `--nuova` → la spesa nuova si fondeva con quella precedente;
- metterlo di troppo → un dialogo a metà veniva buttato via;
- instradare male la risposta → «5» finiva nella descrizione invece che nella sottocategoria;
- riscrivere l'elenco delle categorie a memoria → numeri sbagliati, voci inventate;
- perdere il filo dopo una compressione del contesto → si ricominciava da capo.

Il plugin **non riscrive il motore**. Aggiunge intorno cinque superfici di vincolo che
tolgono al modello, una alla volta, ogni decisione che non sia comprensione del linguaggio.

### Cosa resta al modello

Una cosa sola, ed è quella che sa fare meglio del codice: **capire che «benzina 50» è una
spesa e tirarne fuori i campi**. Tutto il resto — instradamento, memoria, validazione,
composizione del testo, scrittura — è deterministico.

---

## 2. Il principio architetturale

Ogni superficie di Hermes usata dal plugin corrisponde a **una** classe di errore
eliminata. La tabella è il riassunto più denso dell'intero progetto:

| Superficie Hermes | Registrata in | Cosa toglie al modello |
|---|---|---|
| `register_tool` | [`__init__.py:104`](__init__.py#L104) | **la shell** — argomenti tipizzati, niente quoting, niente percorsi |
| middleware `tool_request` | [`__init__.py:111`](__init__.py#L111) | **l'instradamento** — `nuova` si legge dal disco, non si deduce |
| hook `pre_llm_call` | [`__init__.py:113`](__init__.py#L113) | **la memoria** — lo stato reale reiniettato a ogni turno |
| hook `pre_tool_call` | [`__init__.py:114`](__init__.py#L114) | **le scorciatoie** — una sola strada per arrivare al foglio |
| hook `transform_llm_output` | [`__init__.py:115`](__init__.py#L115) | **la parafrasi** — la risposta finale è il testo dello script |
| hook `on_session_end` | [`__init__.py:116`](__init__.py#L116) | (igiene) — un messaggio non ritirato non ricompare dopo |

Tre corollari che spiegano scelte che altrimenti sembrano arbitrarie:

**a. Il modello non deve mai vedere l'elenco delle categorie.** Se lo vede, prima o poi lo
ricompone a mano, e un elenco ricomposto ha numeri sbagliati. Per questo `opzioni` esiste
nel payload ma viene rimosso dal ritorno dell'handler ([`tools.py:50-53`](tools.py#L50-L53)),
e per questo esiste un test che verifica che **nessun nome di categoria compaia nel prompt**
([`tests/test_schemas.py:82`](tests/test_schemas.py#L82)).

**b. I messaggi sono battute complete, non frammenti.** «Confermi?» da solo non è una frase
che si possa ripetere, e chi la riceve fa la cosa ragionevole: la riscrive. Ogni messaggio
composto da [`componi_messaggio()`](budget_sheets.py#L667) è autosufficiente — elenco
numerato e riepilogo già dentro — così chi lo riceve ha **esattamente una cosa da stampare**,
e stamparla è la strada facile.

**c. Non esiste una SKILL.md, ed è deliberato.** Una skill impacchettata in un plugin non
compare nell'index né in `skills_list`: si carica solo con uno `skill_view()` esplicito,
quindi nessuno la leggerebbe mai. Tutto ciò che il modello deve sapere sta in
[`schemas.py`](schemas.py), che il system prompt porta con sé a ogni turno. Le descrizioni
dei parametri lì dentro **non sono documentazione, sono il prompt**.

---

## 3. Mappa dei file

```
budget-familiare/                 ← la radice del repo È la radice del plugin
│
├── plugin.yaml            manifest: dichiara tool e hook a Hermes
├── __init__.py            register(ctx): le cinque superfici di vincolo
├── schemas.py             schema del tool — qui vive il trigger, qui vive il prompt
├── tools.py               handler del tool + la "cassetta" della resa verbatim
├── budget_sheets.py       il motore: macchina a stati, bozza, validazione, Google Sheets
├── tassonomia.yaml        le categorie (dato, non codice)
│
├── Makefile               le quattro suite di test
├── README.md              installazione e vista d'insieme
├── ARCHITECTURE.md        questo file
│
├── scripts/
│   └── sync_budget_skill.sh   cron ogni 30': commit+push del checkout sul server
│
└── tests/
    ├── percorsi.py            dove stanno le cose, in un posto solo
    ├── test_budget_sheets.py  il motore (il file più grande: 56 KB)
    ├── test_plugin.py         le cinque superfici
    ├── test_schemas.py        cosa il modello NON deve sapere
    ├── casi_eval.json         19 conversazioni complete, condivise dalle tre eval
    ├── eval_protocollo.py     rigioca le conversazioni, deterministica
    ├── eval_smemorato.py      eval avversariale: modelli che non ricordano niente
    └── eval_modello.py        opt-in, a pagamento: misura l'interpretazione reale
```

**Dipendenze:** nessuna, oltre alla stdlib di Python 3. Sul server il plugin gira con
l'interprete di Hermes, dove non si possono installare pacchetti. Questo vincolo spiega
scelte che altrove sarebbero ingiustificabili — in particolare il parser YAML scritto a
mano (§4.6). L'unica eccezione è `tests/eval_modello.py`, opt-in, che chiede l'SDK
`anthropic`.

---

## 4. I componenti, uno per uno

### 4.1 `plugin.yaml` — il manifest

Dichiara a Hermes cosa il plugin fornisce: un tool (`registra_transazione`) e quattro hook.
`api_version: "1.0"`, `manifest_version: 2`.

Due assenze intenzionali, documentate nel file stesso:

- **niente `capabilities`**: non si fa override di tool né del modello, quindi
  all'installazione non c'è nessun consenso da chiedere all'utente;
- **niente `requires_env`**: le credenziali Google e l'id del foglio stanno nel profilo
  (`PROFILE_DIR`), non nell'ambiente.

> ⚠️ Il manifest e le registrazioni in `register()` devono restare allineati: c'è un test
> che lo verifica ([`tests/test_plugin.py`](tests/test_plugin.py)). Aggiungere un hook in
> `__init__.py` senza dichiararlo qui fa fallire la suite.

### 4.2 `__init__.py` — le cinque superfici

Espone `register(ctx)`, che Hermes chiama al caricamento. Contiene cinque funzioni, una per
superficie, più il comando slash.

#### `forza_instradamento(**kwargs)` — middleware `tool_request`

```python
args["nuova"] = not budget_sheets.in_dialogo()
```

Deriva `nuova` dalla bozza su disco e **scarta quello che ha deciso il modello**. È la
superficie più preziosa delle cinque, per due ragioni:

1. È la sorgente di errore più cara: `nuova` sbagliato in un senso fonde due transazioni,
   sbagliato nell'altro butta via un dialogo a metà.
2. Non richiede giudizio: se c'è una bozza aperta, il turno è una continuazione. Sempre.

Il middleware `tool_request` gira **prima** di availability check, guardrail, approvazioni
ed esecuzione: è un vincolo vero, non un suggerimento. Ritorna `None` (= nessuna modifica)
per qualsiasi tool diverso da `registra_transazione`.

#### `inietta_stato(**kwargs)` — hook `pre_llm_call`

Se c'è una bozza aperta, inietta nel contesto un'istruzione:

> «C'è una transazione a metà: l'ultima domanda di registra_transazione aspetta risposta.
> Richiamalo passando in `risposta` quello che ha appena scritto l'utente, testuale. Non
> ricominciare da capo, non ricostruire l'elenco delle categorie e non riassumere: ci pensa
> il tool.»

Due dettagli non negoziabili:

- **legge dal disco, non dalla sessione** — così sopravvive alla compressione del contesto,
  che è il modo tipico in cui un dialogo a metà si perde;
- **inietta un'istruzione, non i campi raccolti** — dare i campi in pasto al modello sarebbe
  un invito a ricomporre a mano il riepilogo che lo script compone già per intero.

#### `blocca_scorciatoie(tool_name, args, **kwargs)` — hook `pre_tool_call`

Se il tool è `terminal` e il comando cita `budget_sheets`, blocca con un messaggio che
rimanda al tool giusto. Lo script **resta** una CLI funzionante per l'uso a mano da un
terminale umano; quello che non deve succedere è che ci arrivi l'agente, perché shellandolo
si salterebbero middleware e hook — cioè esattamente i vincoli che questo plugin esiste per
imporre.

#### `resa_verbatim(**kwargs)` — hook `transform_llm_output`

```python
return tools.ritira(kwargs.get("session_id"))
```

Una riga, ed è il punto in cui «stampa il messaggio parola per parola» smette di essere una
richiesta al modello e diventa un fatto. L'hook scatta una volta per turno, a ciclo dei tool
concluso, e la prima stringa non vuota **sostituisce** la risposta del modello.

Se il turno non ha chiamato il tool, la cassetta è vuota, si ritorna `None` e Hermes si
comporta come sempre — niente platform handler, nessun rischio di mangiarsi i flussi core
(approvazioni, selettore modello, prompt di chiarimento).

#### `pulisci(**kwargs)` — hook `on_session_end`

Igiene: se un turno deposita un messaggio e `transform_llm_output` non scatta (un errore a
metà strada), quel messaggio non deve ricomparire tre turni dopo.

#### `/spesa [testo]` — comando slash

L'innesco esplicito per quando il messaggio è troppo scarno perché il trigger scatti da
solo. Fa `ctx.inject_message(f"Registra questa transazione: {testo}")`. **L'estrazione dei
campi resta al modello**: è la parte che sa fare, e farla qui con una regex sarebbe un passo
indietro.

### 4.3 `schemas.py` — il prompt

L'unica cosa che il modello legge a ogni turno. Contiene:

- **`TRIGGER`** — la `description` del tool. Decide *quando* il tool si attiva. È scritta
  per essere aggressiva di proposito: elenca spesa/pagamento/acquisto/incasso/rimborso/
  versamento, cita esplicitamente le foto di scontrini, dice «anche se il messaggio è breve
  tipo "benzina 50"», e chiude con «richiamalo a ogni turno finché la transazione non è
  chiusa: è lui a condurre il dialogo e a ricordarsi i campi già raccolti».
- **`REGISTRA_TRANSAZIONE`** — lo schema JSON degli otto parametri. Nessuno è `required`.
- **`CAMPI_TOOL`** — la tupla dei parametri che l'handler gira allo script.

I parametri, e cosa insegnano al modello:

| Parametro | Regola nel prompt |
|---|---|
| `risposta` | «testuale, non interpretarlo e non tradurlo: ci pensa il tool a capire a quale campo appartiene» |
| `importo` | come l'ha scritto l'utente, niente simboli di valuta, **nessun cambio valuta mai** |
| `data` | solo se indicata; accetta espressioni relative passate così come sono |
| `categoria` | nome o numero, «tentala se ti sembra ovvia, anche senza azzeccarla»; **non inventarne** |
| `sottocategoria` | «come la categoria» |
| `descrizione` | sintetica; se il messaggio non dice niente, vuota; **non chiederla mai** |
| `note` | sempre stringa vuota |
| `annulla` | true solo se l'utente lascia perdere |

> **`nuova` non è un parametro, e non è una dimenticanza.** Decidere se il turno apre una
> transazione nuova non è un giudizio, è una lettura del disco. La fa il middleware.

### 4.4 `tools.py` — handler e cassetta

#### La cassetta

```python
_ULTIMO = {}                    # session_id → messaggio
_ULTIMO_LOCK = threading.Lock()
```

Deposito del messaggio dell'ultimo turno, per sessione. Lo riempie l'handler, lo svuota
`transform_llm_output` con `ritira()` (che fa `pop`: una volta sola). Sta **in memoria e non
in `ctx.state`** di proposito: vale per un turno solo, e uno stato che deve morire subito è
meglio che non sopravviva a un riavvio.

#### `registra_transazione(args, **kwargs)`

Un turno di dialogo. Rispetta le tre regole degli handler di Hermes:

1. **ritorna sempre una stringa JSON**;
2. **non solleva mai** — un'eccezione che esce di qui disabilita il tool per il resto della
   sessione;
3. accetta `**kwargs`.

Il corpo è breve: filtra `args` per `CAMPI_TOOL` scartando i `None`, forza
`nuova = bool(args.get("nuova", False))`, chiama `budget_sheets.esegui(**campi)`, deposita
`payload["messaggio"]` nella cassetta, e **ritorna al modello solo `{stato, messaggio}`**.

> Il ritorno ridotto è architetturale, non cosmetico: `opzioni` e `intervallo` esistono nel
> payload per test e diagnostica, ma se il modello li vede prima o poi ricompone l'elenco a
> mano.

### 4.5 `budget_sheets.py` — il motore

Circa 1000 righe, organizzate in strati. Dal basso verso l'alto:

| Righe | Strato | Responsabilità |
|---|---|---|
| 36-69 | **Costanti** | percorsi, id del foglio, posizione e TTL della bozza |
| 71-139 | **Auth** | OAuth: refresh del token, cache su file con margine di 60 s |
| 141-168 | **HTTP** | `_api_request` con auto-retry una volta sola sul 401 |
| 170-334 | **Tassonomia** | parsing di `tassonomia.yaml`, lookup per id/nome, derivazione del tipo |
| 336-443 | **Validazione** | data (assoluta e relativa), importo (formati IT/EN), conferma |
| 445-527 | **Bozza** | lock, load, save atomico, TTL |
| 529-637 | **Logica del dialogo** | `unisci`, `normalizza`, `risolvi_risposta` |
| 639-732 | **Messaggi** | `componi_messaggio` — il testo intero da mostrare |
| 734-746 | **Sheets** | `append_row` |
| 748-986 | **Orchestrazione + CLI** | `esegui`, `_turno`, `main` |

Le funzioni che contano davvero sono quattro, e sono in §6.

#### Note sugli strati bassi

**Auth.** `get_access_token()` riusa l'access token in cache finché mancano più di 60 s alla
scadenza, altrimenti fa refresh e riscrive il file **preservando il `refresh_token`** (Google
a volte ne emette uno nuovo, a volte no). Se il refresh token è revocato, `_do_refresh`
riconosce `invalid_grant` nel corpo della risposta e solleva un `RuntimeError` con
istruzioni leggibili.

**HTTP.** `_api_request` ritenta **una volta sola** sul 401: invalida la cache locale del
token, ne prende uno nuovo e ripete con `_retry=False`. Non c'è retry su 5xx o su errori di
rete — un fallimento diventa `errore_scrittura`, che riporta il dialogo alla conferma e
lascia all'utente la decisione di riprovare.

**Validazione dell'importo.** Riconosce quattro forme: `1.200,00` (IT con migliaia),
`12,50` (IT), `1.500` (solo migliaia), `30` e `30.50` (EN). Il segno lo porta il *tipo*, non
il numero: i negativi sono rifiutati. Il ramo `1.500 → 1500` esiste perché senza cadrebbe
nel fallback inglese e varrebbe 1,5 — è la regola che in SKILL.md era una tabella che il
modello applicava a memoria.

**Date relative.** `normalizza_data_relativa()` traduce «ieri», «altro ieri», «lunedì
scorso». Due scelte deliberate: `oggi` è iniettabile (un test che dipende dall'orologio
fallisce a mezzanotte e nessuno capisce perché) e **non si guarda mai avanti** (una spesa la
si registra dopo averla fatta; «domani» è quasi sempre un errore di battitura).

**Conferma.** `interpreta_conferma()` riconosce ~15 forme di sì e ~7 di no. `"1"` e `"2"`
sono deliberatamente fuori da entrambi gli insiemi: sarebbero ambigui contro un numero di
categoria se lo stato andasse alla deriva.

### 4.6 `tassonomia.yaml` — il dato

17 categorie con id 1..17, ciascuna con una lista `sottocategorie` (sempre presente, `[]` se
vuota) i cui id **ripartono da 1 dentro ogni categoria**: il «5» di *Cibo fuori* non è il
«5» di *Auto / Moto*.

Ogni voce ha un `tipo` (`uscita` | `entrata` | `entrambi`, default `uscita`). Quando una
categoria è `entrambi` — il caso di *Investimento* — il tipo si prende dalla sottocategoria,
che deve averne uno esplicito.

#### ⚠️ Vincoli di formato

`leggi_tassonomia()` ([`budget_sheets.py:177`](budget_sheets.py#L177)) è un **parser a
espressioni regolari riga per riga, non PyYAML**, perché sul server non si possono
installare pacchetti. Di conseguenza l'indentazione è semanticamente carica:

| Elemento | Indentazione | Forma richiesta |
|---|---|---|
| categoria | 2 spazi | `  - nome: "Sport"` — **doppi apici obbligatori** |
| attributi della categoria | 4 spazi | `    id: 5` — intero nudo, senza apici |
| sottocategoria | 6 spazi | `      - nome: "Palestra"` |
| attributi della sottocategoria | 8 spazi | `        id: 1` |

Qualsiasi deviazione (apici singoli, indentazione a 3 spazi, id quotato) viene **ignorata
silenziosamente**: la voce non entra nella mappa e sparisce dall'elenco mostrato all'utente,
senza errori. Vedi §13.1 per la procedura di modifica sicura.

---

## 5. Il flusso di un turno

```
                MESSAGGIO UTENTE
                       │
    ┌──────────────────▼──────────────────┐
 1  │ pre_llm_call · inietta_stato()      │  legge il DISCO
    │ bozza aperta? → inietta istruzione  │  (non la sessione)
    └──────────────────┬──────────────────┘
                       │
    ┌──────────────────▼──────────────────┐
 2  │ IL MODELLO                          │  ⚠ unico punto probabilistico
    │ vede schemas.TRIGGER nel system     │
    │ prompt → estrae i campi → chiama    │
    └──────────────────┬──────────────────┘
                       │
    ┌──────────────────▼──────────────────┐
 3  │ tool_request · forza_instradamento()│  args["nuova"] = not in_dialogo()
    │ SOVRASCRIVE la scelta del modello   │  ← prima di guardrail e approvazioni
    └──────────────────┬──────────────────┘
                       │
    ┌──────────────────▼──────────────────┐
 4  │ pre_tool_call · blocca_scorciatoie()│  riguarda solo il tool `terminal`
    └──────────────────┬──────────────────┘
                       │
    ┌──────────────────▼──────────────────┐
 5  │ handler tools.registra_transazione()│  → budget_sheets.esegui()
    │ deposita il messaggio nella cassetta│  → ritorna {stato, messaggio}
    └──────────────────┬──────────────────┘
                       │
    ┌──────────────────▼──────────────────┐
 6  │ _turno()  la macchina a stati       │  vedi §6
    └──────────────────┬──────────────────┘
                       │
    ┌──────────────────▼──────────────────┐
 7  │ transform_llm_output·resa_verbatim()│  ritira dalla cassetta e
    │ la risposta finale È il testo       │  SOSTITUISCE la risposta
    └──────────────────┬──────────────────┘
                       ▼
               TESTO ALL'UTENTE
```

**Il punto più importante di tutto il diagramma:** al passo 5 il modello riceve indietro
`{stato, messaggio}`, ma **cosa ne fa è irrilevante**. Qualunque cosa scriva al passo 6,
il passo 7 la butta e mette il testo composto dallo script. Il modello non può sbagliare il
testo mostrato all'utente perché non è lui a scriverlo.

---

## 6. La macchina a stati

### Le quattro funzioni che contano

#### `risolvi_risposta(stato, testo)` — [`:619`](budget_sheets.py#L619)

**Il cuore del sistema.** Lo script sa che domanda ha fatto, quindi sa a quale campo
appartiene la risposta:

```python
{"chiedi_data": "data", "chiedi_importo": "importo",
 "chiedi_categoria": "categoria", "chiedi_sottocategoria": "sottocategoria"}[stato]
```

`"5"` durante `chiedi_sottocategoria` diventa `{"sottocategoria": "5"}`. Durante
`chiedi_conferma` il testo passa da `interpreta_conferma()`. Per qualsiasi altro stato
ritorna `{}`.

Questo è l'instradamento che prima toccava al modello, ed è dove sbagliava.

#### `unisci(campi, nuovi)` — [`:544`](budget_sheets.py#L544)

Fonde i campi nuovi nella bozza, ignorando i `None`. Tre regole:

1. **Regola d'oro: nel dubbio si fonde e si richiede conferma, mai si scarta.** La conferma
   è la rete di sicurezza — niente arriva sul foglio senza che l'utente abbia letto la riga
   intera — quindi una fusione sbagliata è visibile e si annulla in un turno, mentre uno
   scarto automatico sarebbe silenzioso e distruggerebbe quello che l'utente aveva già detto.
2. **Cambiare categoria azzera la sottocategoria**: apparteneva alla categoria di prima. Il
   confronto passa da `_stessa_categoria()`, che normalizza — `"3"`, `"supermercato"` e
   `"Supermercato"` sono la stessa cosa, e ridire la categoria in un altro modo non deve far
   decadere una sottocategoria già scelta.
3. **Qualsiasi modifica invalida una conferma già data.**

#### `normalizza(campi)` — [`:568`](budget_sheets.py#L568)

Valida in **ordine fisso** e ritorna il **primo** problema trovato:

```
data → importo → categoria → sottocategoria → tipo → conferma
```

Ritorna `(campi, stato, rifiutato)`. `stato` è `None` quando è tutto a posto; `rifiutato` è
il valore grezzo che non si è capito, per poterlo citare nel messaggio («Non ho trovato la
categoria «benzin».»).

**Azzera solo il campo incriminato**, non quelli a valle: è la differenza con il vecchio
gateway, che li cancellava tutti e obbligava il chiamante a ricordarseli.

Due comportamenti derivati dalla tassonomia, non dal chiamante:

- se la categoria non prevede sottocategorie, `sottocategoria` viene forzata a `""` e non
  viene mai chiesta — è ciò che eliminò la domanda senza risposta che mandava il dialogo in
  loop;
- se il tipo non è ricavabile (`entrambi` senza tipo sulla sottocategoria), lo stato è
  `errore_tassonomia`: è un errore di configurazione, non una domanda.

#### `componi_messaggio(stato, campi, ...)` — [`:667`](budget_sheets.py#L667)

Un ramo per stato, e ogni ramo ritorna il **testo intero** da mostrare, con elenco numerato
o riepilogo già dentro. `_elenco()` numera con **l'id della tassonomia, non con la
posizione**, così il contratto regge anche se un giorno gli id avranno dei buchi.

### Gli stati

| Stato | Significato | Bozza dopo | Exit CLI |
|---|---|---|---|
| `chiedi_data` | data assente o non valida | salvata | 3 |
| `chiedi_importo` | importo assente o non valido | salvata | 3 |
| `chiedi_categoria` | categoria assente o non riconosciuta | salvata | 3 |
| `chiedi_sottocategoria` | sottocategoria assente o non riconosciuta | salvata | 3 |
| `chiedi_conferma` | tutto raccolto, manca il «sì» | salvata | 3 |
| `scritto` | ✓ riga sul foglio | **cancellata** | 0 |
| `annullata` | l'utente ha lasciato perdere | **cancellata** | 3 |
| `bozza_assente` | è arrivata una risposta senza una domanda aperta | — | 3 |
| `bozza_scaduta` | idem, ma la bozza era scaduta per TTL | — | 3 |
| `scrittura_in_corso` | un'altra invocazione sta già scrivendo | intatta | 3 |
| `errore_auth` | credenziali Google da rigenerare | → `chiedi_conferma` senza «Si» | 1 |
| `errore_scrittura` | Google ha rifiutato la scrittura | → `chiedi_conferma` senza «Si» | 2 |
| `errore_tassonomia` | tipo non ricavabile | **non toccata** | 5 |
| `errore_bozza` | non si riesce a salvare lo stato | non salvabile | 6 |

Gli exit code valgono per l'uso da CLI; passando dal plugin conta solo `stato`. Il default è
3 (`EXIT.get(payload["stato"], 3)`), che copre tutti gli stati di dialogo e quelli terminali
benigni.

**Due scelte di recupero che vale la pena conoscere:**

- Gli errori di rete (`errore_auth`, `errore_scrittura`) riportano la bozza a
  `chiedi_conferma` **senza** il «Si»: si riprende con una parola invece di ridettare tutto,
  ma la scrittura non riparte da sola.
- Rispondere «no» alla conferma **non annulla**: azzera categoria e sottocategoria e rifà la
  domanda sulla categoria, che è l'errore più probabile in un riepilogo rifiutato. Per
  annullare davvero serve `annulla`.

---

## 7. Albero decisionale completo

```
MESSAGGIO UTENTE
│
├─ pre_llm_call · inietta_stato()
│  └─ in_dialogo()?  ├─ NO → nessuna iniezione
│                    └─ SÌ → inietta l'istruzione di continuazione
│
├─ IL MODELLO DECIDE ────────────────────────────────── ⚠ unico punto probabilistico
│  │
│  ├─ (A) NON chiama il tool
│  │      └─ resa_verbatim ritorna None → Hermes normale → risposta libera
│  │         Rimedio: /spesa <testo>
│  │
│  └─ (B) chiama registra_transazione
│         │
│         ├─ tool_request → nuova = not in_dialogo()   [scelta del modello scartata]
│         ├─ pre_tool_call → passa (riguarda solo `terminal`)
│         │
│         └─ handler
│            │
│            ├─ (B0) eccezione da esegui()
│            │       → {"errore": …}, NIENTE depositato in cassetta
│            │       → transform_llm_output ritorna None
│            │       → ⚠ l'utente legge una PARAFRASI, non testo dello script
│            │
│            └─ _turno()  ── dentro flock ──
│               │
│               ├─ annulla=True ──────────────────────► «annullata»            ✓ cancellata
│               ├─ nuova=True → cancella_bozza()
│               ├─ stato == "scrittura_in_corso" ─────► «scrittura_in_corso»   (vedi §14.1)
│               ├─ risposta≠None ma nessuna bozza ────► «bozza_assente/scaduta»
│               │
│               ├─ risolvi_risposta(stato_prec, testo)
│               ├─ conferma == "No" → azzera categoria+sottocategoria
│               ├─ unisci()      fonde, mai scarta
│               │
│               └─ normalizza()  ordine FISSO, primo problema vince
                  │
                  ├─ data non valida ──────────────► «chiedi_data»            ↻
                  ├─ importo non valido ───────────► «chiedi_importo»         ↻
                  ├─ categoria non trovata ────────► «chiedi_categoria»       ↻ +elenco
                  ├─ sottocategoria non trovata ───► «chiedi_sottocategoria»  ↻ +elenco
                  ├─ tipo non ricavabile ──────────► «errore_tassonomia»      ✗ bozza intatta
                  ├─ conferma ≠ "Si" ──────────────► «chiedi_conferma»        ↻ +riepilogo
                  │     └─ risposta non sì/no → ripete con "Non ho capito."
                  │
                  └─ TUTTO A POSTO
                     │
                     ├─ salva_bozza() fallisce ─────► «errore_bozza»          ✗
                     ├─ marca "scrittura_in_corso"   ← marcatore anti-doppione
                     ├─ ESCE DAL LOCK                ← Google è lento
                     │
                     ├─ get_access_token() ko ──────► «errore_auth»           ✗ → conferma
                     ├─ append_row() ko ────────────► «errore_scrittura»      ✗ → conferma
                     └─ OK ─────────────────────────► «scritto»               ✓ riga scritta

  ↓ in tutti i casi tranne (A) e (B0)
transform_llm_output → la risposta finale È il testo di componi_messaggio()
```

---

## 8. Modello dei dati

### La bozza su disco

```jsonc
{
  "versione": 1,                     // BOZZA_VERSIONE: una versione ignota = bozza cancellata
  "aggiornato": 1758240000.0,        // epoch; oltre BOZZA_TTL la bozza è "scaduta"
  "stato": "chiedi_sottocategoria",  // la domanda a cui si sta aspettando risposta
  "campi": {
    "data": "18/09/2026",            // sempre gg/mm/aaaa dopo normalizza()
    "importo": 50.0,                 // float dopo normalizza(), stringa prima
    "categoria": "Auto / Moto",      // nome canonico dalla tassonomia
    "sottocategoria": "",
    "descrizione": "Benzina Esso",
    "note": "",
    "conferma": ""                   // "" | "Si" | "No"
  }
}
```

`CAMPI` (i sette campi persistiti) è definito a [`:69`](budget_sheets.py#L69). Nota che
`tipo` **non** è un campo persistito: si ricava a ogni turno dalla tassonomia con
`tipo_di()`. È l'unica scelta che garantisce che una correzione della tassonomia si applichi
anche a una bozza aperta.

### Il payload di un turno

`_emetti()` produce sempre le stesse dodici chiavi, sempre lo stato completo: `stato`,
`messaggio`, `data`, `importo`, `categoria`, `sottocategoria`, `tipo`, `descrizione`,
`note`, `conferma`, `opzioni`, `intervallo`.

Di queste, **l'handler ne gira al modello solo due**: `stato` e `messaggio`. Le altre
esistono per la CLI, i test e la diagnostica.

### La riga sul foglio

`append_row()` scrive sette colonne in `A:G` del foglio `Transazioni 2026`:

| A | B | C | D | E | F | G |
|---|---|---|---|---|---|---|
| data | tipo | categoria | sottocategoria | importo | descrizione | note |
| `18/09/2026` | `Uscita` | `Auto / Moto` | `Benzina` | `50.0` (float) | `Benzina Esso` | `` |

`valueInputOption=USER_ENTERED`, `insertDataOption=INSERT_ROWS`.

---

## 9. Concorrenza, durabilità, idempotenza

### Il lock

`_bozza_lock()` ([`:450`](budget_sheets.py#L450)) è un `flock` esclusivo su
`<BOZZA_FILE>.lock`, esposto come context manager. Serializza il ciclo
**leggi → fondi → scrivi**: senza, due invocazioni ravvicinate leggono la stessa bozza e la
seconda scrittura perde il campo della prima.

Tre proprietà da preservare:

1. **Non va mai tenuto durante la chiamata HTTP a Google** — una richiesta appesa
   bloccherebbe ogni turno successivo per tutto il TTL. Per questo `_turno` esce dal lock
   prima di `get_access_token()` e lo riprende dopo.
2. **Se non si riesce ad aprire il file di lock, si procede senza** — meglio degradati che
   fermi.
3. **Non è rientrante.** `_bozza_lock` apre un fd nuovo a ogni chiamata e usa `flock`:
   una riacquisizione annidata nello stesso processo si impianterebbe. Per questo
   `stato_corrente()` prende il lock e lo rilascia **prima** di ritornare.

### La scrittura atomica

`salva_bozza()` scrive su un temporaneo `<BOZZA_FILE>.<pid>.tmp` con
`O_CREAT|O_WRONLY|O_TRUNC|O_NOFOLLOW` e `0600`, fa `flush` + `fsync`, poi `os.replace()`.
Un lettore vede la bozza vecchia o la nuova, mai metà.

`O_NOFOLLOW` e `0600` non sono paranoia: il fallback in `/tmp` è un percorso prevedibile e
condiviso, e in quel file c'è quanto e dove spende una famiglia.

### Il marcatore anti-doppione

Prima di uscire dal lock per chiamare Google, `_turno` salva lo stato
`scrittura_in_corso`. Se arrivasse un secondo turno mentre Google risponde, troverebbe il
marcatore invece di mandare la stessa riga una seconda volta — **un doppione su un foglio di
spese non lo nota nessuno**.

> ⚠️ Questo meccanismo ha oggi un difetto che lo rende inefficace quando si passa dal
> plugin. Vedi §14.1.

### Tolleranza ai guasti

`carica_bozza()` tratta **qualunque** anomalia — file assente, JSON rotto, versione ignota —
come «nessuna bozza»: chi sta registrando una spesa non deve mai vedere un traceback.

---

## 10. Invarianti da non rompere

Ognuna di queste ha un test che la sorveglia. Se una modifica ne infrange una, la suite
fallisce — ed è voluto.

| # | Invariante | Dove è sorvegliata |
|---|---|---|
| I1 | Nessun nome di categoria compare nel prompt del modello | `tests/test_schemas.py:82` |
| I2 | Nessun messaggio dello script compare nel prompt | `tests/test_schemas.py:~70` |
| I3 | Lo schema non conosce percorsi, interprete, flag CLI, id del foglio | `tests/test_schemas.py` |
| I4 | Il manifest dichiara esattamente ciò che `register()` registra | `tests/test_plugin.py` |
| I5 | L'handler non solleva mai e ritorna sempre una stringa JSON | `tests/test_plugin.py` |
| I6 | `nuova` deriva dal disco, mai dal modello | `tests/test_plugin.py` |
| I7 | `transform_llm_output` sostituisce la risposta col testo dello script | `tests/test_plugin.py` |
| I8 | I numeri mostrati sono gli id della tassonomia, non le posizioni | `tests/test_budget_sheets.py:~640` |
| I9 | Non si chiede mai una sottocategoria a una categoria che non ne ha | `tests/test_budget_sheets.py:936` |
| I10 | Niente arriva sul foglio senza una conferma esplicita | `tests/eval_protocollo.py` |
| I11 | La suite non tocca mai la rete né il foglio vero | mock con `side_effect` che solleva |

---

## 11. Configurazione e deploy

### Costanti

Tutte in cima a [`budget_sheets.py:36-41`](budget_sheets.py#L36-L41):

| Costante | Valore | Note |
|---|---|---|
| `PROFILE_DIR` | `/opt/data/profiles/budgetingagent` | il profilo Hermes |
| `TOKEN_FILE` | `<PROFILE_DIR>/google_token.json` | token con refresh |
| `CRED_FILE` | `<PROFILE_DIR>/google_client_secret.json` | credenziali OAuth |
| `SPREADSHEET_ID` | `1iDYzjzy…M6JB0` | il foglio di destinazione |
| `SHEET_NAME` | `Transazioni 2026` | ⚠️ cambia a ogni anno solare |
| `TASSONOMIA_FILE` | accanto allo script | risolto da `__file__` |

### Variabili d'ambiente

| Variabile | Default | Uso |
|---|---|---|
| `BUDGET_BOZZA_FILE` | (vedi sotto) | override del percorso della bozza — **usato dai test** |
| `BUDGET_BOZZA_TTL_MIN` | `15` | TTL della bozza in minuti; un valore storto non fa esplodere l'import |

### Dove vive la bozza

```python
if os.path.isdir(PROFILE_DIR):  →  <PROFILE_DIR>/bozza_transazione.json
else:                           →  <tmpdir>/budget_bozza_transazione.json
```

**La bozza sta fuori dal worktree git, ed è essenziale.** Due ragioni indipendenti:

1. `sync_budget_skill.sh` fa `git add -A` dentro la directory del plugin: un percorso fuori
   dal worktree è **irraggiungibile**, non solo ignorato. È una garanzia più forte di una
   riga in `.gitignore`, che un `git add -f` o un merge sbagliato vanificherebbero — e lì
   dentro c'è lo storico di spesa della famiglia.
2. **Hermes sostituisce la directory del plugin a ogni update.** Uno stato scritto lì dentro
   sparirebbe insieme alla vecchia versione.

> Su una macchina di sviluppo `PROFILE_DIR` non esiste, quindi la bozza finisce in `/tmp`.
> È il motivo per cui i test impostano `BUDGET_BOZZA_FILE` **prima** di caricare il plugin:
> senza, userebbero la bozza vera del profilo.

### Installazione

```bash
hermes plugins install l33tleandrew/budget-familiare --ref <sha-40>
hermes plugins enable budget-familiare
hermes plugins list        # ✓ budget-familiare v1.0.0 (1 tools, 4 hooks)
```

I plugin generali sono disabilitati di default: senza `enable` non carica. Il `--ref` vuole
uno SHA esatto di 40 caratteri — tag e branch vengono rifiutati.

### Sincronizzazione dal server

`scripts/sync_budget_skill.sh` gira da cron ogni 30 minuti sul server. Entra in
`$BUDGET_PLUGIN_DIR` (default `/opt/data/profiles/budgetingagent/plugins/budget-familiare`)
e, se il worktree è sporco, fa `git add -A` + commit `auto-sync: <ts>` + `git push origin main`.

> ⚠️ **Il checkout sul server è il repo.** Una modifica fatta lì viene committata e
> pushata da sola, senza revisione. Non c'è nessun gate.

---

## 12. Test ed eval

267 test, tutti con la sola stdlib, in meno di mezzo secondo. `make test` li esegue tutti.

| Comando | Cosa gira |
|---|---|
| `make test` | tutto quello che gira offline |
| `make plugin` | solo le cinque superfici |
| `make eval` | rigioca le conversazioni di `casi_eval.json`, deterministica |
| `make eval-smemorato` | eval avversariale: un modello che non ricorda niente deve arrivare in fondo |
| `make eval-modello` | ⚠️ chiamate a pagamento, richiede `pip install anthropic` |

### Cosa copre cosa

| File | Verifica |
|---|---|
| `test_budget_sheets.py` | il motore: validazione, tassonomia, macchina a stati, CLI con exit code, strato di rete sotto mock |
| `test_plugin.py` | le cinque superfici e il manifest |
| `test_schemas.py` | cosa il modello **non** deve sapere, e che il prompt resti corto |
| `eval_protocollo.py` | il protocollo: messaggi mostrati, gating della conferma, trappole, riga finale |
| `eval_smemorato.py` | resistenza: modelli che dimenticano tutto fra un turno e l'altro |
| `eval_modello.py` | l'interpretazione reale: un modello legge lo schema e si misura cosa ne ricava |

### Perché non si tocca mai Google Sheets

`get_access_token` e `append_row` sono sostituite a ogni giro, e `urllib.request.urlopen` è
sotto mock con un `side_effect` che **solleva**: se un giorno lo script provasse a
raggiungere la rete per altre vie, l'eval fallisce invece di scrivere davvero. L'unico test
che lancia lo script come processo vero non arriva mai alla conferma.

`eval_modello.py` non esegue comandi affatto: chiede al modello *quali* campi passerebbe,
non glieli fa passare. Non ha fallback server-side sulle richieste rifiutate — in un'eval un
instradamento silenzioso verso un altro modello falserebbe la misura, che serve proprio a
dire come si comporta *quel* modello.

---

## 13. Playbook: come fare le modifiche comuni

### 13.1 Aggiungere, rinominare o rimuovere una categoria

**Sorgente unica:** `tassonomia.yaml`. Nessun file di runtime contiene nomi di categoria.

**Procedura:**

1. Modifica `tassonomia.yaml` rispettando i vincoli di formato di §4.6 (doppi apici,
   indentazione 2/4/6/8, id interi nudi, `sottocategorie: []` se vuota).
2. Se la categoria ha `tipo: entrambi`, **ogni** sottocategoria deve avere il proprio
   `tipo:`, altrimenti si ottiene `errore_tassonomia` e nulla viene scritto.
3. Verifica il parsing prima di toccare i test:
   ```bash
   python3 -c "import budget_sheets as b; \
     [print(c['id'], c['nome'], [s['id'] for s in c['sottocategorie']]) \
      for c in b.leggi_tassonomia()]"
   ```
4. Aggiorna i punti che hanno **copiato** il dato:
   - [`tests/test_budget_sheets.py:227`](tests/test_budget_sheets.py#L227) — il conteggio `17`
   - [`tests/test_budget_sheets.py:231-250`](tests/test_budget_sheets.py#L231-L250) — nomi,
     insieme delle categorie senza sottocategorie, lista ordinata delle sottocategorie di
     *Cibo fuori*
   - [`tests/test_budget_sheets.py:257-262`](tests/test_budget_sheets.py#L257-L262) — id→nome
     per 1/3/17 e gli id fuori range (`0, 18, 99`: il `18` va alzato se aggiungi categorie)
   - [`tests/test_budget_sheets.py:634-635`](tests/test_budget_sheets.py#L634-L635) —
     `"\n2. Supermercato"`, `"\n17. Beneficienza"`
   - [`tests/eval_smemorato.py:203-204`](tests/eval_smemorato.py#L203-L204) —
     `"\n3. Cibo fuori / bevute"`, `"\n5. Ristorante"`
   - `tests/casi_eval.json` — solo se tocchi una delle voci usate nei 19 casi
   - [`README.md:9-15`](README.md#L9-L15) — il dialogo d'esempio
5. `make test`

**Due trappole:**

- **Gli id sono i numeri che l'utente digita.** Rinumerare cambia l'interfaccia. Riusare un
  id liberato da una rimozione è meno invasivo che rinumerare.
- **Non scegliere nomi generici.** [`tests/test_schemas.py:82`](tests/test_schemas.py#L82)
  pretende che nessun nome di categoria compaia nel prompt: un nome come «Nota», «Importo» o
  «Descrizione» farebbe fallire il test per collisione con il testo dello schema.

> ⚠️ **`_TASSONOMIA_CACHE` è globale di processo e non viene mai invalidata**
> ([`:174`](budget_sheets.py#L174)). Dopo aver modificato `tassonomia.yaml` sul server serve
> un ricaricamento del plugin (o un riavvio del processo Hermes) perché la modifica abbia
> effetto. Da CLI non si nota, perché ogni invocazione è un processo nuovo.

### 13.2 Cambiare un messaggio mostrato all'utente

Unico posto: [`componi_messaggio()`](budget_sheets.py#L667). Non esistono copie altrove — è
l'invariante I2. Controlla però le asserzioni letterali in `test_budget_sheets.py` e in
[`eval_smemorato.py:196-204`](tests/eval_smemorato.py#L196-L204), che legge il testo mostrato
per trovarci dentro il numero da digitare. `casi_eval.json` invece non contiene testo di
messaggi: i suoi `stati_attesi` sono nomi di stato.

### 13.3 Aggiungere un campo alla transazione

Tocca cinque punti, in quest'ordine:

1. `CAMPI` ([`:69`](budget_sheets.py#L69)) — se il campo va persistito nella bozza;
2. `CAMPI_TOOL` + `properties` in [`schemas.py`](schemas.py) — se il modello deve estrarlo;
3. `normalizza()` — se serve validazione e una domanda dedicata (nuovo stato `chiedi_*`);
4. `risolvi_risposta()` — la mappa stato→campo;
5. `ETICHETTE` ([`:643`](budget_sheets.py#L643)) e `append_row()` — riepilogo e colonna.

Se aggiungi uno stato `chiedi_*`, aggiungi anche il ramo in `componi_messaggio()`: il
fallback ritorna `dettaglio`, cioè stringa vuota, e l'utente vedrebbe un messaggio vuoto.

### 13.4 Cambiare il foglio a inizio anno

`SHEET_NAME` a [`:40`](budget_sheets.py#L40). È una costante, non una variabile d'ambiente:
serve una modifica al codice e un redeploy.

### 13.5 Modificare il comportamento del trigger

`TRIGGER` in [`schemas.py:13`](schemas.py#L13). Tieni presente I3: lo schema non deve
conoscere percorsi, flag o messaggi. E dopo ogni modifica sostanziale vale la pena far girare
`make eval-modello` — è l'unica misura reale di quanto il trigger scatta, ed è a pagamento
proprio perché misura il modello vero.

---

## 14. Debito noto e problemi aperti

> Questa sezione è il motivo principale per cui il documento esiste. Sono problemi **noti e
> non risolti** allo stato attuale del codice, ordinati per impatto.

### 14.1 Il marcatore anti-doppione è irraggiungibile passando dal plugin

**Gravità:** media · **Probabilità:** bassa (finestra di pochi secondi)

`in_dialogo()` è definito come `stato_corrente().startswith("chiedi_")`. Lo stato
`scrittura_in_corso` non inizia per `chiedi_`, quindi `in_dialogo()` ritorna `False`,
quindi `forza_instradamento` imposta `nuova=True`, quindi `_turno` esegue `cancella_bozza()`
alla [riga 865](budget_sheets.py#L865) — **cancellando il marcatore prima di leggerlo** alla
[riga 868](budget_sheets.py#L868).

La guardia scatta solo da CLI, invocata senza `--nuova`.

**Conseguenze concrete**, se un secondo messaggio arriva mentre Google sta rispondendo:

1. il turno 2 apre una transazione nuova a campi vuoti e comincia a chiedere;
2. quando il turno 1 completa la scrittura, esegue `cancella_bozza()` alla
   [riga 950](budget_sheets.py#L950) e **cancella la bozza del turno 2**;
3. l'utente risponde alla domanda del turno 2 e riceve `bozza_assente`.

**Dove intervenire:** `in_dialogo()` ([`:827`](budget_sheets.py#L827)) — far sì che consideri
anche `scrittura_in_corso` come «dialogo in corso» — oppure spostare la guardia della riga
868 prima del `if nuova` della riga 864.

### 14.2 `bozza_scaduta` non raggiunge mai l'utente con quel nome

**Gravità:** nessuna oggi · **Da sapere prima di differenziare il messaggio**

`forza_instradamento` chiama `in_dialogo()` → `stato_corrente()` → `carica_bozza()`, che su
una bozza scaduta la **cancella già lì** e ritorna la stringa `"scaduta"`. Quando `_turno`
esegue, il file non c'è più: `carica_bozza()` ritorna `None` e lo stato emesso è
`bozza_assente`.

Oggi è innocuo perché [`componi_messaggio:708`](budget_sheets.py#L708) rende i due stati con
lo stesso testo. Ma se un giorno si volesse dire «la transazione di prima è scaduta» invece
di «non sto registrando niente», non basterebbe cambiare quel ramo.

### 14.3 Un'eccezione nell'handler fa tornare la parafrasi

**Gravità:** bassa · **Percorso:** ramo (B0) dell'albero

Se `budget_sheets.esegui()` solleva, l'handler cattura, ritorna `{"errore": …}` e **non
deposita nulla nella cassetta**. Di conseguenza `resa_verbatim` ritorna `None` e la risposta
finale torna a essere quella del modello — cioè una parafrasi dell'errore, esattamente ciò
che l'architettura esiste per impedire.

`esegui()` è scritta per non sollevare (tutti gli errori previsti diventano stati), quindi il
ramo si attiva solo su un bug o su un guasto imprevisto. Rimedio possibile: depositare un
messaggio di fallback prima di ritornare l'errore.

### 14.4 `_ULTIMO` con `session_id` assente

**Gravità:** bassa

`tools.deposita()` e `ritira()` usano `kwargs.get("session_id")` come chiave. Se Hermes non
lo passasse, tutte le sessioni condividerebbero la chiave `None` e due sessioni concorrenti
potrebbero scambiarsi il messaggio.

### 14.5 Stringhe e riferimenti stantii

| Dove | Cosa |
|---|---|
| [`budget_sheets.py:964`](budget_sheets.py#L964) | l'help di `--categoria` dice `references/tassonomia.yaml`: quella cartella non esiste più |
| [`tests/eval_modello.py:78`](tests/eval_modello.py#L78) | stessa etichetta stantia nel prompt dell'eval |
| [`tests/eval_protocollo.py:29`](tests/eval_protocollo.py#L29) | importa `TASSONOMIA` e non lo usa |
| [`tests/casi_eval.json:8`](tests/casi_eval.json#L8) | un commento cita ancora `SKILL.md`, rimossa in `5eb3258` |
| [`tassonomia.yaml:224`](tassonomia.yaml#L224) | la voce `"Altro"` di *Salute* ha due spazi in coda — l'unica riga del file in queste condizioni (c'è un test che ne verifica il trim) |

### 14.6 Interfaccia legacy a tipi misti

I wrapper `validate_categoria`, `validate_sottocategoria`, `find_categoria_by_id`,
`find_sottocategoria_by_id` ([`:290-334`](budget_sheets.py#L290-L334)) ritornano `False` in
caso di fallimento e una stringa (a volte `""`, che è falsy) in caso di successo. Sono
l'interfaccia storica, usata solo dai test; il codice di produzione usa
`trova_categoria`/`trova_sottocategoria`, che ritornano `None` o il dizionario. Non
aggiungere chiamanti ai wrapper.

### 14.7 Nessun retry sugli errori transitori di Google

`_api_request` ritenta solo sul 401. Un 503 o un timeout diventa `errore_scrittura`, che
riporta alla conferma e delega all'utente il riprovare. È una scelta difendibile — meglio
chiedere che rischiare un doppione — ma è una scelta, non un'omissione.

---

## 15. Glossario

| Termine | Significato |
|---|---|
| **bozza** | lo stato del dialogo su disco: campi raccolti + stato + timestamp |
| **cassetta** | `tools._ULTIMO`: il deposito da cui `transform_llm_output` ripesca il testo del turno |
| **campo** | uno dei sette valori di una transazione (`CAMPI`) |
| **stato** | il nome del punto in cui si trova il dialogo (`chiedi_*`, `scritto`, `errore_*`…) |
| **superficie** | uno dei cinque punti di estensione di Hermes usati per vincolare il modello |
| **tassonomia** | l'albero categorie → sottocategorie, con il tipo (entrata/uscita) |
| **tipo** | `Entrata` o `Uscita`; **derivato** dalla tassonomia, mai persistito |
| **trigger** | la `description` del tool: ciò che decide se il modello si attiva |
| **resa verbatim** | la sostituzione della risposta del modello col testo dello script |

---

## Appendice — Dove guardare quando qualcosa non va

| Sintomo | Prima ipotesi | Dove guardare |
|---|---|---|
| Il tool non si attiva su un messaggio breve | trigger | `schemas.TRIGGER`; workaround `/spesa` |
| Una categoria non compare nell'elenco | formato YAML | §4.6 e §13.1; cache di processo |
| L'utente legge un testo parafrasato | la cassetta è vuota | rami (A) e (B0) di §7 |
| Un dialogo a metà «si dimentica» | TTL scaduto, o §14.1 | `BUDGET_BOZZA_TTL_MIN`, `carica_bozza()` |
| Due transazioni si fondono | `nuova` non derivato | `forza_instradamento`, `in_dialogo()` |
| «Non riesco a capire se … è entrata o uscita» | `entrambi` senza tipo sulla sotto | `tipo_di()`, `tassonomia.yaml` |
| La riga non arriva sul foglio | auth o rete | `errore_auth` / `errore_scrittura`; stderr |
| Modifica alla tassonomia senza effetto sul server | `_TASSONOMIA_CACHE` | ricarica il plugin |
