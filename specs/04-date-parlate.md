# SPEC-04 — Giorno e mese

**Stato:** da fare · **Dipende da:** [SPEC-01](01-anno-budget-centralizzato.md) ·
**Comportamento:** capacità nuova · **Il resto:** [arretrato](arretrato-date.md)

> Questo file è la **prima versione**, volutamente minima: riconosce `<giorno> <mese>` e
> nient'altro. Tutto ciò che è stato valutato e rinviato — le altre famiglie di date, le
> misure che le motivano, i divieti che le vincolano — sta in [`arretrato-date.md`](arretrato-date.md).

---

## Problema

[`normalizza_data_relativa()`](../budget_sheets.py#L404) riconosce oggi due famiglie:

- i giorni fissi — `oggi`, `ieri`, `altro ieri`, `avantieri`;
- i giorni della settimana — `lunedì scorso`, `martedì`.

Tutto il resto passa intatto e [`validate_data()`](../budget_sheets.py#L341) pretende
`gg/mm/aaaa`. Quindi:

```
utente  │ il 10 settembre ho fatto benzina, 45
agente  │ Non ho capito la data «il 10 settembre».
        │ Scrivila come gg/mm/aaaa, per esempio 29/09/2026.
```

È la forma più naturale per registrare una spesa di qualche giorno fa, ed è quella in cui il
modello è più tentato di convertire da sé — sbagliando l'anno.

Il canale conta: il `TRIGGER` ([schemas.py:16](../schemas.py#L16)) dichiara che il tool si
attiva anche **a voce**. Una data dettata arriva a parole molto più spesso di una scritta.

---

## Comportamento richiesto

Viene riconosciuta la forma **`<giorno> <mese>`**, e solo quella.

| Forma | Esempio | Risultato (anno budget 2026) |
|---|---|---|
| giorno in cifre, mese a parole | `10 settembre`, `il 10 settembre` | `10/09/2026` |
| giorno a parole, mese a parole | `dieci settembre`, `ventotto febbraio` | `10/09/2026`, `28/02/2026` |
| entrambi in cifre | `10/09`, `10-09`, `10 09` | `10/09/2026` |

L'anno **non si dice e non si deduce**: una data senza anno è dell'anno del budget. Le
transazioni sono organizzate per anno, quindi l'anno è configurazione — non una scelta.

L'articolo funziona senza che il pattern se ne occupi: lo toglie già il preprocessing
esistente a [`budget_sheets.py:420`](../budget_sheets.py#L420).

### I tre separatori delle cifre

`/`, `-` e lo **spazio**. Non è simmetria gratuita: per iscritto arriva solo `/`, ma da una
trascrizione vocale possono arrivare tutti e tre. Il punto **no**: vedi i Divieti.

---

## Limiti noti di questa versione

Sono limiti **scelti**, non dimenticanze. Vanno letti prima di aprire un difetto.

| Limite | Effetto | Dove va |
|---|---|---|
| **Niente anno**, nemmeno quello giusto | `10 settembre 2026` → «Non ho capito la data». Dire l'anno è completezza formale, e in questa versione rompe il riconoscimento. Il messaggio non è del tutto vero: la data è stata capita, non è stata accettata | [arretrato](arretrato-date.md#anno-esplicito) |
| **Niente `primo`** | `primo settembre` → domanda. Il giorno 1 si registra in cifre. È il solo giorno su 31 senza forma parlata usabile | [arretrato](arretrato-date.md#ordinali) |
| **`uno settembre` combacia** | `uno` è nella tabella dei numeri a parole per costruzione. Non è una forma che qualcuno usi, e produce comunque la data giusta: si lascia invece di aggiungere un `if` per toglierla | — |
| **Niente riempitivi** | `10 di settembre`, `del 10 settembre` → domanda | [arretrato](arretrato-date.md#riempitivi) |
| **Niente momento del giorno** | `ieri sera`, `stamattina`, `sabato sera` → domanda | [arretrato](arretrato-date.md#momento-del-giorno) |
| **Niente relative contate** | `tre giorni fa`, `una settimana fa` → domanda | [arretrato](arretrato-date.md#relative-contate) |
| **Niente abbreviazioni** | `10 set`, `4 ott` → domanda | [arretrato](arretrato-date.md#abbreviazioni) |
| **Il messaggio di rifiuto parla a chi scrive** | «Scrivila come gg/mm/aaaa» è inapplicabile a chi sta dettando | [arretrato](arretrato-date.md#messaggio) |

Nessuno di questi limiti produce una data sbagliata: producono una **domanda**. È la proprietà
che questa versione difende sopra ogni altra.

---

## Progettazione

Tutto nello strato «Validazione» di `budget_sheets.py`. **Nessuna riga esistente viene
modificata**: è un ramo in più prima del `return testo` finale, e si annulla cancellandolo.

### 1. Il generatore dei numeri in lettere

Le tabelle si generano, non si scrivono a mano.

```python
_UNITA  = ("", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove")
_DIECI  = ("dieci", "undici", "dodici", "tredici", "quattordici",
           "quindici", "sedici", "diciassette", "diciotto", "diciannove")
_DECINE = ("", "", "venti", "trenta", "quaranta", "cinquanta",
           "sessanta", "settanta", "ottanta", "novanta")


def _in_lettere(n):
    """Il numero italiano in forma piatta: 21 → "ventuno", 28 → "ventotto", 23 → "ventitre".

    Le elisioni sono la ragione per cui questa funzione esiste invece di una
    tabella: "venti" + "uno" non fa "ventiuno". Verificate su tutti i valori
    1..31.
    """
    if n < 10:
        return _UNITA[n]
    if n < 20:
        return _DIECI[n - 10]
    decina, unita = divmod(n, 10)
    base = _DECINE[decina]
    if unita in (1, 8):
        base = base[:-1]          # venti + uno → ventuno, venti + otto → ventotto
    return base + _UNITA[unita]
```

`ventitré` dopo [`_piatto()`](../budget_sheets.py#L235) è `ventitre`, quindi la forma piatta
è quella giusta da generare.

### 2. I vocabolari

```python
# I nomi dei mesi sono scritti qui e non presi da `calendar.month_name`: quelli
# dipendono dal locale, e il locale italiano non e' garantito sul server. Stessa
# scelta, e stesso motivo, di `_GIORNI` per i giorni della settimana.
_MESI = {nome: n for n, nome in enumerate(
    ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
     "agosto", "settembre", "ottobre", "novembre", "dicembre"), start=1)}

# Niente "primo": questa versione non ha ordinali. Vedi i Limiti noti.
_GIORNI_LETTERE = {_in_lettere(n): n for n in range(1, 32)}
```

### 3. Il pattern: i vocabolari chiusi stanno dentro

I due insiemi sono piccoli e finiti — 31 giorni, 12 mesi — quindi **il match è la
validazione**. Quello che combacia è per costruzione un giorno fra 1 e 31 e un mese fra 1 e
12, e le guardie a runtime non servono perché diventano impossibili da violare.

```python
def _alternativa(parole):
    """Alternanza regex dalle chiavi, le piu' lunghe per prime: "ventisei" deve
    vincere su "venti"."""
    return "|".join(sorted(map(re.escape, parole), key=len, reverse=True))


_RE_GIORNO     = r"3[01]|[12]\d|0?[1-9]"       # 1..31, mai 0 e mai 32
_RE_MESE_CIFRE = r"1[0-2]|0?[1-9]"             # 1..12, mai 0 e mai 13

_RE_GIORNO_MESE = re.compile(
    rf"(?P<g>{_RE_GIORNO}|{_alternativa(_GIORNI_LETTERE)})"
    rf" (?P<m>{_alternativa(_MESI)})"           # mese a parole: l'ancora del match
    rf"|(?P<gn>{_RE_GIORNO})[/\- ](?P<mn>{_RE_MESE_CIFRE})"
)
```

**432 caratteri di pattern compilato**, da tre righe di sorgente. Le alternanze si generano
dagli stessi dizionari usati per tradurre, quindi non possono divergere.

Il giorno è `3[01]|[12]\d|0?[1-9]` e non `\d{1,2}`: `32 settembre`, `0 settembre`,
`00 settembre` e `99 settembre` non combaciano, senza bisogno di nessun `if`. Stessa cosa per
il mese in cifre: `10/13` e `0/9` non combaciano.

Il giorno a parole vale **solo** col mese a parole: `dieci/09` non è una forma che esista, e
ammetterla allargherebbe la superficie senza coprire niente.

### 4. La traduzione e la composizione

```python
def _data_giorno_mese(giorno, mese):
    """La data nell'anno del budget, o None se quel giorno in quel mese non esiste.

    Il controllo sul calendario e' l'unico che il pattern non puo' fare, perche'
    dipende da giorno e mese insieme: il 31 settembre e il 29 febbraio di un anno
    non bisestile sono sintatticamente ineccepibili e non esistono.
    """
    try:
        return datetime(ANNO_BUDGET, mese, giorno)
    except ValueError:
        return None
```

### 5. L'innesto

Un terzo ramo in `normalizza_data_relativa`, **dopo** i giorni della settimana e **prima** del
`return testo` finale:

```python
    m = _RE_GIORNO_MESE.fullmatch(piatto)
    if m:
        if m["g"]:
            giorno = int(m["g"]) if m["g"].isdigit() else _GIORNI_LETTERE[m["g"]]
            mese = _MESI[m["m"]]
        else:
            giorno, mese = int(m["gn"]), int(m["mn"])
        data = _data_giorno_mese(giorno, mese)
        if data:
            return data.strftime("%d/%m/%Y")

    return testo
```

`fullmatch` e non `search`, ed è la riga che regge tutta la sicurezza di questo spec: se il
modello taglia male il messaggio, quello che arriva nel campo non combacia e **esce intatto**,
producendo una domanda invece di una data verosimile e non detta.

### 6. Il prompt

Il modello non sa che può passare questa forma: la descrizione del campo `data`
([schemas.py:50-59](../schemas.py#L50-L59)) elenca solo `gg/mm/aaaa` e le relative. Senza
questa modifica il ramo nuovo è **raggiungibile solo dalla CLI e dai test, mai in produzione**.

```python
            "data": {
                "type": "string",
                "description": (
                    "Solo se il messaggio ne indica una; altrimenti ometti e vale "
                    "oggi. Accetta gg/mm/aaaa, le espressioni relative (\"ieri\", "
                    "\"l'altro ieri\", \"lunedì scorso\") e le date con giorno e "
                    "mese (\"il 10 settembre\", \"dieci settembre\"): passale così "
                    "come le ha scritte, non convertirle. Su una foto di scontrino "
                    "vince la data stampata, se leggibile."
                ),
            },
```

Tre cose, in ordine di importanza:

1. **«non convertirle»** è la parte che conta. L'elenco dice *cosa* può arrivare; questa dice
   *cosa non fare*. La versione precedente diceva «passate così come le ha scritte», che è
   un'affermazione: per una data parlata serve un divieto, perché convertire *sembra* utile ed
   è proprio la cosa che rompe l'anno.
2. Gli esempi sono **due**, non sei: bastano a stabilire la categoria.
3. L'anno **non si nomina**. È una regola dello script, e nominarla in un file statico la
   esporrebbe al disallineamento il giorno in cui cambia.

Il **`TRIGGER` non si tocca**: decide *se* il tool si attiva, non *cosa* riceve.

| | Oggi | Dopo | Limite |
|---|---|---|---|
| descrizione di `data` | 269 byte | 335 byte | — |
| `PROMPT` (trigger + tutte le descrizioni) | 1976 byte | **2042 byte** | 3000 |
| `TRIGGER` | 624 byte | 624 byte, invariato | 900 |

### Aggiornamento della documentazione

[`ARCHITECTURE.md`](../ARCHITECTURE.md) §4.5 («Date relative») e la voce di glossario, che non
c'è. E l'help della CLI a [`budget_sheets.py:1037`](../budget_sheets.py#L1037), che oggi dice
`Data gg/mm/aaaa, o "ieri" (default: oggi)`.

---

## ⚠️ Un invariante che era già falso

`ARCHITECTURE.md` §4.5 dice che lo script **non guarda mai avanti**. Non è vero, e non lo è
mai stato: nessuna riga rifiuta una data futura. L'invariante è un effetto collaterale di due
fatti nel solo ramo delle relative — `_GIORNI_FA` non ha voci in avanti, e il ramo settimanale
fa `% 7 or 7`. Misurato il 23/09/2026:

```
31/12/2026 → chiedi_categoria    ← data futura, già accettata oggi
domani     → 'domani'            ← non riconosciuta, non rifiutata
```

Quindi questo spec **non rompe un invariante: estende a una seconda strada un'asimmetria che
c'era già.** «4 ottobre» detto il 29 settembre diventa `04/10/2026`, una data futura, e la
cosa è deliberata: nessuna politica sulle date future, qui come prima.

L'invariante vero, quello che sopravvive e va scritto in `ARCHITECTURE.md` al posto di quello
falso, è:

> **quando una forma è ambigua fra passato e futuro, vince il passato.**

Spiega perché «domani» non si riconosce e perché «lunedì scorso» detto di lunedì vale sette
giorni fa. Non tocca «4 ottobre», che non ha nessuna ambiguità da sciogliere: l'utente ha
nominato un giorno.

---

## Come si distingue il giorno dall'importo in «10 settembre 5 euro»

Non lo distingue questo ramo: **il regex non vede mai il messaggio intero**.

```
"10 settembre 5 euro"
        │
        ▼  il MODELLO taglia il messaggio in campi
registra_transazione(data="10 settembre", importo="5", …)
        │
        ▼  ogni campo va al suo validatore, isolato
normalizza_data_relativa("10 settembre")  →  "10/09/2026"
validate_importo("5")                     →  5.0
```

La domanda che conta è cosa succede **se il modello taglia male**, ed è verificata:

| Cosa arriva in `data` | Esito |
|---|---|
| `10 settembre 5 euro` | intatta → `chiedi_data` |
| `10 settembre 5` | intatta → `chiedi_data` |
| `10 settembre 5,50` | intatta → `chiedi_data` |
| `5 euro 10 settembre` | intatta → `chiedi_data` |
| `12.05`, `10.09`, `3.10` | intatta → `chiedi_data` — **vedi i Divieti** |

Simmetricamente `validate_importo` rifiuta già `"5 euro"` e `"10 settembre"`. Nessuna via
porta a una riga sbagliata in silenzio.

---

## Fuori scope

- **Tutte le altre famiglie di date.** Stanno in [`arretrato-date.md`](arretrato-date.md) con
  le misure che le motivano e l'ordine in cui conviene prenderle.
- **Il vincolo sull'anno**: è [SPEC-03](03-vincolo-anno-sulle-date.md), già fatto. Qui la data
  si compone e basta.
- **Qualunque politica sulle date future.** Vedi l'invariante qui sopra.
- **Il `TRIGGER`** e le descrizioni degli altri sette parametri.
- **Un banco di prova contro il modello.** L'accettazione qui è `make test`, deterministica e
  gratuita. La misura di quanto il modello obbedisca al divieto è in
  [arretrato](arretrato-date.md#banco).

---

## Criteri di accettazione

- [ ] Le tre forme della tabella «Comportamento richiesto» danno il risultato indicato
- [ ] `ventisei settembre`, `ventuno settembre`, `trentuno dicembre`, `ventotto febbraio`,
      `ventitré marzo` sono corretti (elisioni, accento, alternanza ordinata)
- [ ] `05 settembre` → `05/09/2026`; `  IL  DIECI   SETTEMBRE  ` → `10/09/2026`
- [ ] `10/09`, `10-09`, `10 09`, `1/9`, `01/09` → `10/09/2026` e `01/09/2026`
- [ ] `32 settembre`, `0 settembre`, `00 settembre`, `99 settembre`, `trentadue settembre`,
      `10/13`, `0/9` restano **intatte** e non c'è nessun `if` che le rifiuti
- [ ] `31 settembre` resta intatta (giorno valido, mese sbagliato)
- [ ] `10 settembre 5`, `10 settembre 5 euro`, `5 euro 10 settembre` restano intatte
- [ ] **`12.05`, `10.09`, `3.10`, `5.12` restano intatte** — il punto non è un separatore
- [ ] I limiti noti si comportano come dichiarato: `primo settembre`, `10 settembre 2026`,
      `10 di settembre`, `ieri sera`, `10 set` restano intatte
- [ ] **Griglia esaustiva 31 × 12 × 5 = 1860 combinazioni** (due forme a parole/cifre più tre
      separatori), con `calendar.monthrange` come oracolo indipendente: zero errori
- [ ] Nessuna regressione su `ieri`, `lunedì scorso`, `gg/mm/aaaa`, `il mese scorso`, `boh`
- [ ] `PROMPT` sotto 3000 byte; `TRIGGER` invariato byte per byte; il prompt non nomina
      `ANNO_BUDGET`, l'anno corrente né il nome della scheda
- [ ] Tutti i test di `tests/test_schemas.py` verdi **senza modificarne nessuno**
- [ ] `make test` verde · `make eval` e `make eval-smemorato` verdi, 20 casi

---

## Test

Nuova classe `TestDataParlata` in `tests/test_budget_sheets.py`, dopo `TestDataRelativa`
(riga 121). **Non serve un `OGGI` fisso**: il ramo non dipende dall'orologio.

I casi mirati sono quelli dei criteri di accettazione. Oltre a quelli, tre test che portano il
loro peso:

```python
def test_un_importo_non_diventa_una_data(self):
    """Se il modello taglia male il messaggio, meglio una domanda che una data
    verosimile e non detta. Il punto NON e' un separatore proprio per questo:
    "12.05" e' un importo in notazione inglese, che validate_importo accetta."""
    for testo in ("10 settembre 5", "10 settembre 5 euro", "10 settembre 5,50",
                  "5 euro 10 settembre", "10 settembre alle 5",
                  "12.05", "10.09", "3.10", "5.12", "1.200,00"):
        with self.subTest(testo=testo):
            self.assertEqual(bs.normalizza_data_relativa(testo), testo)


def test_i_limiti_noti_restano_tali(self):
    """Non sono difetti, sono il taglio di questa versione. Se un giorno uno di
    questi passa, e' perche' qualcuno ha preso una voce dall'arretrato: allora
    va tolto da qui, non fatto fallire in silenzio."""
    for testo in ("primo settembre", "10 settembre 2026", "10 settembre 2025",
                  "10 di settembre", "ieri sera", "10 set", "tre giorni fa"):
        with self.subTest(testo=testo):
            self.assertEqual(bs.normalizza_data_relativa(testo), testo)


def test_tutti_i_giorni_di_tutti_i_mesi(self):
    """31 giorni x 12 mesi x 5 notazioni = 1860 combinazioni. Il dominio e'
    piccolo e chiuso: si prova tutto invece di scegliere dei campioni.

    L'attesa si calcola con calendar.monthrange e non costruendo un datetime:
    lo script valida la data proprio costruendola, e un test che usasse la
    stessa chiamata verificherebbe datetime() con datetime(). Cosi' le due
    strade sono indipendenti e concordano solo se hanno ragione entrambe.
    """
    for mese, n in bs._MESI.items():
        ultimo = calendar.monthrange(bs.ANNO_BUDGET, n)[1]
        for giorno in range(1, 32):
            forme = [f"{giorno} {mese}", f"{bs._in_lettere(giorno)} {mese}"]
            forme += [f"{giorno}{sep}{n}" for sep in ("/", "-", " ")]
            for testo in forme:
                atteso = (f"{giorno:02d}/{n:02d}/{bs.ANNO_BUDGET}"
                          if giorno <= ultimo else testo)
                with self.subTest(testo=testo):
                    self.assertEqual(bs.normalizza_data_relativa(testo), atteso)
```

E un test su `_in_lettere` (1..31, con le elisioni `21→ventuno`, `28→ventotto`,
`23→ventitre`), più l'equivalente di
[`test_normalizza_le_risolve`](../tests/test_budget_sheets.py#L120) per la forma nuova.

Su `tests/test_schemas.py` una sola asserzione in più, in `TestFormaDelloSchema`:

```python
def test_la_data_dice_di_non_convertire(self):
    """E' l'istruzione che impedisce al modello di scegliersi l'anno: se sparisce,
    sparisce in silenzio e se ne accorge solo un'eval col modello."""
    self.assertIn("non convertirle", PROPRIETA["data"]["description"])
```

> **Nota su `mock.patch.object(bs, "ANNO_BUDGET", ...)`.** Patchare l'anno funziona: in questa
> versione l'anno non entra nel pattern, che quindi non va ricompilato. È utile per provare
> `29 febbraio` in un anno bisestile.

---

## Verifica

```bash
cd /Users/loprieno-andrea/Documents/budget-familiare-workflow

make test
make eval && make eval-smemorato

python3 -c "
import budget_sheets as b
for t in ('10 settembre', 'il 10 settembre', 'dieci settembre', '4 ottobre',
          'ventotto febbraio', 'ventisei settembre', 'trentuno dicembre',
          '10/09', '10-09', '10 09', '1/9',
          '31 settembre', '32 settembre', '10/13',
          'primo settembre', '10 settembre 2026',       # limiti noti
          '12.05', '10.09',                             # il divieto sul punto
          '10 settembre 5', '10 settembre 5 euro',
          'ieri', 'lunedì scorso', 'il mese scorso', 'boh'):
    r = b.normalizza_data_relativa(t)
    print(f'{t:26} → {r if r != t else \"— intatta (→ chiedi_data)\"}')
"

# il prompt: margine e invarianti
python3 -c "
import schemas
P = schemas.TRIGGER + '\n' + '\n'.join(
    p['description'] for p in schemas.REGISTRA_TRANSAZIONE['parameters']['properties'].values())
print('PROMPT :', len(P.encode()), 'byte (limite 3000)')
print('TRIGGER:', len(schemas.TRIGGER.encode()), 'byte (deve restare 624)')
"

# end-to-end, si ferma prima della rete:
python3 budget_sheets.py append --nuova --importo 30 \
    --categoria Supermercato --data "dieci settembre"
# atteso: chiedi_conferma, e nel riepilogo «Data: 10/09/2026»
```

---

## Divieti permanenti

Non sono «fuori scope»: sono cose che **non vanno costruite così**, mai, nemmeno prendendo una
voce dall'arretrato. Stanno qui e non nell'arretrato perché chi implementa questo file legge
questo file, e tutti e tre sembrano miglioramenti ovvi.

### Il punto non è mai un separatore di data

`(\d{1,2})[/.-](\d{1,2})` sembra la generalizzazione naturale dei tre separatori ammessi. Non
lo è: [`validate_importo`](../budget_sheets.py#L441) accetta già la notazione inglese, quindi
`30.50` è un importo. Misurato su un campo `data` riempito male dal modello:

| valore | con il punto | senza |
|---|---|---|
| `12.05` | **12/05/2026** — silenzioso | intatta → domanda |
| `10.09` | **10/09/2026** — silenzioso | intatta → domanda |
| `3.10` | **03/10/2026** — silenzioso | intatta → domanda |
| `5.12` | **05/12/2026** — silenzioso | intatta → domanda |

Sono importi plausibili, e `/`, `-` e lo spazio non hanno questo problema: nessuna notazione
di importo italiana o inglese li usa. Quattro errori silenziosi per un separatore che nessuno
scrive.

### «il 10» col mese sottinteso non si riconosce

È l'unica forma valutata che trasformi un taglio sbagliato del modello in una **data valida in
silenzio**: `data="il 10"` diventerebbe `10/09/2026` senza che niente lo segnali. Tutte le
altre forme scartate, di fronte a un taglio sbagliato, restano intatte e producono una
domanda. Escluderla è ciò che tiene vuota la colonna «forma capita male» di questo spec.

### «scorso» non è mai rumore

Verrà la tentazione di toglierlo in preprocessing per capire «il dieci settembre scorso», come
si tolgono «di» e «sera». È sbagliato di concetto: «scorso» **sposta indietro**, in entrambi i
rami. Accanto a un giorno della settimana sceglie l'occorrenza precedente; accanto a una data
completa significa l'anno precedente. Misurato:

```
«il dieci settembre scorso» detto a gennaio 2026,
  con «scorso» trattato come rumore   →  10/09/2026   ← FUTURA di 8 mesi
```

L'utente aveva detto «scorso», cioè esplicitamente «non quest'anno», e il risultato è una data
futura. Il trattamento corretto è in [arretrato](arretrato-date.md#scorso): «scorso» accanto a
una data completa significa anno precedente, la data si compone nell'anno prima, e il cancello
di [SPEC-03](03-vincolo-anno-sulle-date.md) risponde la verità — «questo budget tiene solo il
2026».

---

## Decisioni e alternative scartate

### Un ramo in più, zero righe esistenti modificate

È il vincolo che ha dettato il taglio. `<giorno> <mese>` non ha bisogno di nessuna modifica al
preprocessing: l'articolo, gli accenti, le maiuscole e gli spazi multipli li toglie già
[`normalizza_data_relativa` alle righe 419-420](../budget_sheets.py#L419-L420). Quindi questa
versione si annulla cancellando un blocco, senza toccare niente di ciò che funziona — il grado
massimo di reversibilità previsto dal criterio di atomicità in [README](README.md).

Le altre famiglie richiedono tutte di **estendere la pulizia**, ed è la ragione per cui
formano un secondo passo e non un'aggiunta a questo.

### Niente anno, nemmeno in cifre

Il gruppo `(?: (\d{4}))?` costa **13 caratteri** di pattern e farebbe passare `10 settembre
2026`, e soprattutto comporrebbe `10 settembre 2025` così che il cancello di SPEC-03 risponda
«è di un altro anno» invece di «non ho capito» — che oggi è una bugia.

È stato valutato e rinviato su indicazione esplicita: questa versione riconosce **un giorno e
un mese**, e l'anno è un concetto in più. Il costo è scritto nei Limiti noti e la voce è la
prima dell'arretrato, proprio perché il rapporto fra costo e beneficio è sbilanciato.

### Niente `primo`, e `uno settembre` resta

In italiano non si dice «uno settembre»: senza `primo`, il giorno 1 non ha forma parlata
usabile. La misura:

```
'primo settembre'  → — intatta → chiedi_data      ← la forma che si dice
'uno settembre'    → 01/09/2026                    ← la forma che nessuno dice
```

È l'effetto rovesciato, ed è accettato: «nessuna parola ordinale» è una regola che si applica
o non si applica, e ammettere l'unica eccezione utile aprirebbe la discussione su `1°` e `1o`,
che richiedono di decidere come normalizzare il segno di grado. `uno` **resta** perché toglierlo
richiederebbe un `if` su una tabella generata, e produce comunque la data giusta: un `if` per
rifiutare una forma corretta è peggio della forma.

### I tre separatori, e perché il punto no

Misurato su 12 forme da riconoscere e 18 da rifiutare:

| Separatori | Copre | Errori silenziosi |
|---|---|---|
| nessuno (solo mese a parole) | 7/12 | 0 |
| `/` e `-` | 11/12 | 0 |
| `/`, `-` e spazio | **12/12** | **0** |
| `/`, `-`, spazio e `.` | 12/12 | **4** |

Lo spazio entra perché una trascrizione vocale può produrlo; il punto resta fuori perché è
l'unico che collide con gli importi. Vedi i Divieti.

### I mesi non vengono da `calendar.month_name`

Sembra la scelta giusta, e non lo è. Misurato:

| | Esito |
|---|---|
| `calendar.month_name[9]` senza locale | `'September'` |
| `setlocale(LC_TIME, "it_IT.UTF-8")` su macOS | funziona → `'Settembre'` (maiuscolo) |
| `setlocale(LC_TIME, "it_IT.utf8")` su macOS | **`locale.Error: unsupported locale setting`** |

La grafia del nome del locale cambia fra piattaforme (glibc vuole tipicamente `it_IT.utf8`,
macOS `it_IT.UTF-8`) e su un container minimale — cioè il server, dove non si installa nulla e
per lo stesso motivo non si usa PyYAML — i locale vanno *generati* e spesso non ci sono. Si
aggiungono due difetti indipendenti dalla disponibilità: **`setlocale` è stato globale di
processo** (un plugin che lo imposta muta il processo Hermes) e **non è thread-safe**, mentre
questo plugin i thread li usa (`tools._ULTIMO_LOCK`).

Dodici stringhe che non cambiano dal 1582 costano una riga. Ed è la scelta che il file ha già
fatto: [`_GIORNI`](../budget_sheets.py#L399) elenca i giorni della settimana esattamente così.

### `calendar` serve invece nel test

Come oracolo indipendente: vedi il docstring di `test_tutti_i_giorni_di_tutti_i_mesi`.

### I vocabolari dentro il pattern

La prima versione usava `(\w+)` per il giorno, poi validato a valle con `if 1 <= n <= 31`.
Portare i vocabolari chiusi dentro il pattern ha eliminato la condizione: **una condizione
qualcuno può toglierla per semplificare, un pattern no**.

### Il prompt sta qui e non in uno spec a sé

`schemas.py` non è codice come gli altri — è il prompt, sta nel system prompt a ogni turno, e
ha una suite dedicata. Una stesura precedente ne faceva uno spec separato (SPEC-05). È stato
riunito qui per una ragione sola: **senza le due righe di prompt, questo ramo non si attiva mai
in produzione**, e uno spec che consegna codice irraggiungibile non soddisfa il criterio
«consegnabile» di [README](README.md). Restano fuori il `TRIGGER` e tutto il resto di
`schemas.py`.
