# SPEC-01 — Anno del budget centralizzato

**Stato:** fatto · **Dipende da:** nessuno · **Comportamento:** invariato

---

## Problema

Le transazioni sono organizzate per anno — il foglio di destinazione si chiama
`Transazioni 2026` — ma l'anno **non esiste come parametro del sistema**. Viveva solo dentro
una stringa, in cima a `budget_sheets.py` (la riga com'era prima di questo intervento):

```python
SHEET_NAME       = "Transazioni 2026"
```

Ne discendono tre conseguenze:

1. **Non è interrogabile.** Nessuna parte del codice può chiedere «di che anno è questo
   budget?» senza fare parsing di un nome di scheda.
2. **Non è verificabile.** Niente può accorgersi che l'anno civile ha superato quello del
   foglio (→ [SPEC-02](02-guardia-cambio-anno.md)).
3. **Non è applicabile.** Nessuna regola può dire «questa data è fuori dall'anno del budget»
   (→ [SPEC-03](03-vincolo-anno-sulle-date.md)) né «una data senza anno è di quest'anno»
   (→ [SPEC-04](04-date-parlate.md)).

[`ARCHITECTURE.md`](../ARCHITECTURE.md) §11 lo segnala già come attrito: «⚠️ cambia a ogni
anno solare», ed è oggi una modifica al codice in un punto che nessuno cerca.

---

## Comportamento richiesto

Nessun cambiamento visibile all'utente. L'anno diventa una costante con un nome,
sovrascrivibile da ambiente, e il nome della scheda lo eredita come default invece di
contenerlo come letterale.

Cambia però **il nome di una costante pubblica del modulo**: `SHEET_NAME` diventa
`GOOGLE_SHEET_NAME`. È l'unica cosa in tutto lo spec che non sia a costo zero — vedi Decisioni.

---

## Progettazione

In cima a `budget_sheets.py` ([`:40-41`](../budget_sheets.py#L40-L41)), al posto della riga
di `SHEET_NAME`:

```python
ANNO_BUDGET       = int(os.environ.get("ANNO_BUDGET") or 2026)
GOOGLE_SHEET_NAME = os.environ.get("GOOGLE_SHEET_NAME") or f"Transazioni {ANNO_BUDGET}"
```

Due righe, senza commenti: il nome che compare due volte sulla stessa riga dice già che
l'una sovrascrive l'altra, e il *perché* delle due costanti sta qui e in
[`ARCHITECTURE.md`](../ARCHITECTURE.md) §11, dove chi cerca la configurazione guarda davvero.

Ogni costante sovrascrivibile si legge dalla variabile d'ambiente **che porta il suo stesso
nome**: letto `ANNO_BUDGET` nel codice, si sa già come esportarlo, senza una seconda parola da
ricordare. È ciò che permette ai test degli spec successivi di fissare l'anno senza dipendere
dall'orologio.

L'uso di `os.environ.get(...) or <default>` segue la forma che il file adotta già per
`BUDGET_BOZZA_FILE` ([`:63-67`](../budget_sheets.py#L63-L67)); il **nome** invece no, e quelle
due variabili restano l'eccezione anteriore alla convenzione.

### Aggiornamento della documentazione

In [`ARCHITECTURE.md`](../ARCHITECTURE.md):

- **§11, tabella delle costanti**: aggiungere `ANNO_BUDGET`, rinominare la riga di
  `SHEET_NAME` e sostituire «⚠️ cambia a ogni anno solare» con il fatto che ora lo eredita;
  più un paragrafo che dice che i due **non** sono la stessa cosa.
- **§11, tabella delle variabili d'ambiente**: aggiungere `ANNO_BUDGET` e `GOOGLE_SHEET_NAME`,
  e la nota sulla convenzione dei nomi.
- **§4.5**, dove si descrive `append_row()`: il foglio di destinazione si chiama con la
  costante nuova.
- **§13.4** («Cambiare il foglio a inizio anno»): oggi dice di modificare `SHEET_NAME`.
  Diventa: modificare `ANNO_BUDGET`, da cui il nome della scheda discende.

### Riferimenti di riga

La riga in più sposta di **+1** tutto ciò che stava da riga 41 in giù, e i riferimenti
`budget_sheets.py#L<n>` in `ARCHITECTURE.md` e nelle spec sono esatti, non approssimativi.
Vanno ricalcolati — target dei link *e* testo visibile — e il controllo non si fa a occhio:
vedi Verifica.

Lo scostamento **dipende da quanto commento sopravvive nel blocco**: una stesura intermedia
con sei righe di commento dava +7. Vale la pena scriverlo il codice prima, contare dopo.

---

## Fuori scope

- **Qualsiasi uso di `ANNO_BUDGET` nella logica.** Qui viene solo introdotto. Usarlo è il
  compito di SPEC-02, 03 e 04, e mescolarlo qui farebbe perdere l'unica proprietà preziosa di
  questo spec: essere a comportamento invariato.
- Derivare l'anno dall'orologio (`datetime.now().year`). È stato considerato e scartato: vedi
  Decisioni.
- Creare automaticamente la scheda dell'anno nuovo sul foglio.

---

## Criteri di accettazione

- [x] `bs.GOOGLE_SHEET_NAME == "Transazioni 2026"`: il **valore** è identico a prima
- [x] `bs.ANNO_BUDGET == 2026`
- [x] `ANNO_BUDGET=2027` produce `ANNO_BUDGET == 2027` e `GOOGLE_SHEET_NAME == "Transazioni 2027"`
- [x] `GOOGLE_SHEET_NAME=Transazioni` produce `GOOGLE_SHEET_NAME == "Transazioni"` **senza**
      toccare `ANNO_BUDGET`, che resta `2026`
- [x] `ANNO_BUDGET=` (vuoto) vale come «non impostato»; `ANNO_BUDGET=abc` fa fallire l'import,
      deliberatamente
- [x] `make test` verde, e **l'unica modifica ai test esistenti è il nome della costante**:
      due righe, `bs.SHEET_NAME` → `bs.GOOGLE_SHEET_NAME`. Nessuna asserzione cambia
- [x] Nessun letterale è entrato nei test al posto della costante: entrambe le righe la
      leggono ancora da `bs`, quindi continuano a seguire l'anno da sole
- [x] L'unico letterale d'anno nel codice è il default di `ANNO_BUDGET`; restano solo i tre
      **esempi** (`validate_data`, i due messaggi `chiedi_data`), che sono un'altra cosa e li
      prende in carico [SPEC-03](03-vincolo-anno-sulle-date.md)
- [x] Ogni riferimento di riga a `budget_sheets.py` cade sullo stesso costrutto di prima

> Il criterio originale era **«suite verde senza aver toccato un solo test»**, ed era il più
> severo dello spec: se un test va modificato, non era un refactor. Il rename di `SHEET_NAME`
> — deciso dopo, per la convenzione sui nomi — lo fa decadere. Non è stato aggirato: è stato
> sostituito con quello che regge ancora, cioè che nessuna **asserzione** cambia. Le due righe
> toccate rinominano un simbolo e basta.

---

## Test

Un solo test nuovo, in `tests/test_budget_sheets.py`
([`test_budget_sheets.py:41-48`](../tests/test_budget_sheets.py#L41-L48)):

```python
class TestAnnoBudget(unittest.TestCase):

    @unittest.skipIf(os.environ.get("GOOGLE_SHEET_NAME"),
                     "il nome del foglio e' sovrascritto dall'ambiente")
    def test_il_nome_predefinito_della_scheda_discende_dall_anno(self):
        """Un posto solo: se il default tornasse a essere un letterale,
        cambiare anno ridiventerebbe una modifica in due punti."""
        self.assertEqual(bs.GOOGLE_SHEET_NAME, f"Transazioni {bs.ANNO_BUDGET}")
```

Lo `skipIf` c'è perché il test asserisce il **default**: senza, chi esporta
`GOOGLE_SHEET_NAME` — una configurazione legittima, che questo spec introduce apposta — si
troverebbe la suite rossa.

I due test esistenti che usano la costante
([`test_schemas.py:161`](../tests/test_schemas.py#L161),
[`test_budget_sheets.py:1171`](../tests/test_budget_sheets.py#L1171)) la leggono già da `bs`,
in modo dinamico. Cambia loro **solo il nome del simbolo**: nessuna asserzione, nessun valore
atteso, nessun letterale al posto della costante. Che continuino a passare senza altro
intervento è parte dell'accettazione.

---

## Verifica

```bash
cd /Users/loprieno-andrea/Documents/budget-familiare-workflow

make test                                          # 268 test, verde

# le uniche righe rimosse dai test sono le due del rename, nient'altro
git diff -U0 tests/ | grep '^-' | grep -v '^---'

P() { python3 -c "import budget_sheets as b; print(repr(b.ANNO_BUDGET), '|', repr(b.GOOGLE_SHEET_NAME))"; }
P                                     # 2026 | 'Transazioni 2026'
ANNO_BUDGET=2027 P                    # 2027 | 'Transazioni 2027'
GOOGLE_SHEET_NAME=Transazioni P       # 2026 | 'Transazioni'
ANNO_BUDGET= P                        # 2026 | 'Transazioni 2026'
ANNO_BUDGET=abc python3 -c "import budget_sheets" >/dev/null 2>&1; echo $?   # != 0

# i letterali d'anno rimasti sono solo quelli previsti:
# il default di ANNO_BUDGET, e i tre esempi che passano a SPEC-03
grep -n '2026' budget_sheets.py
```

### Riferimenti di riga: controllo meccanico

Non si ricontano a mano. Uno script risolve ogni riferimento contro il file vero e stampa
`<file>|<tipo>|<contenuto della riga puntata>`; si esegue con il `budget_sheets.py` di prima
(`git show HEAD:budget_sheets.py`) e con quello dopo, e si confronta la **colonna del
contenuto**, non il numero:

```bash
diff <(risolvi prima) <(risolvi dopo)
# atteso: solo i riferimenti alla vecchia riga 40, che cambiano significato apposta
```

Il confronto sul contenuto è l'unica verifica che non si può sbagliare a occhio. Due tranelli,
entrambi da evitare con un lookbehind nello script:

- i riferimenti a `tests/test_budget_sheets.py` contengono il nome dello script come
  sottostringa, e un'espressione regolare ingenua sposta anche quelli;
- la forma abbreviata `` `:<n>` `` per convenzione significa sempre lo script: non va usata
  per riferirsi ai file di test, o il prossimo spostamento la sballa.

---

## Decisioni e alternative scartate

### La variabile d'ambiente si chiama come la costante

Prima stesura: costanti `ANNO_BUDGET` e `SHEET_NAME`, variabili `BUDGET_ANNO` e
`BUDGET_SHEET_NAME`. Seguiva il prefisso di `BUDGET_BOZZA_FILE`, ma costringeva a ricordare
**due nomi per la stessa cosa**, per giunta con le parole invertite (`ANNO_BUDGET` /
`BUDGET_ANNO`): un invito a sbagliare esportazione e a non capire perché non succede niente.

La regola adottata è una sola: **la variabile d'ambiente porta il nome della costante che
sovrascrive.** Letto il codice, si sa già come sovrascriverlo.

Da qui il rename di `SHEET_NAME` in **`GOOGLE_SHEET_NAME`**: applicare la convenzione voleva
dire esportare una variabile chiamata `SHEET_NAME`, troppo generica per l'ambiente di un
processo. Il prefisso `GOOGLE_` la qualifica — è il nome di una scheda di Google Sheets — e
resta lo stesso identificatore da entrambe le parti.

Le due `BUDGET_BOZZA_*` **non** sono state rinominate. Sono anteriori alla convenzione, i test
le usano, e toccarle non avrebbe avuto niente a che vedere con l'anno del budget: sarebbe
stato un secondo cambiamento infilato dentro il primo.

Il prezzo, pagato consapevolmente, è che `GOOGLE_SHEET_NAME` non è più il `SHEET_NAME` che
il resto del mondo conosceva: due righe di test rinominate, e il criterio di accettazione più
severo dello spec sostituito (vedi la nota sotto i Criteri). In un modulo senza altri
consumatori è un prezzo piccolo; in una libreria pubblicata non lo sarebbe stato.

### Il nome del foglio eredita l'anno, non ne discende

La prima stesura di questo spec scriveva `SHEET_NAME = f"Transazioni {ANNO_BUDGET}"`, secco.
È stato scartato: fa del nome del foglio **una funzione dell'anno**, e non lo è. Il nome del
foglio è l'etichetta di una destinazione; l'anno è un fatto su quali date il budget accetta.
Oggi coincidono perché il foglio si chiama così, ma domani potrebbe chiamarsi `Transazioni` o
`Default` e tenere più anni — e `ANNO_BUDGET` continuerebbe a valere per le date, che è
l'unica ragione per cui SPEC-03 e SPEC-04 ne hanno bisogno.

Da qui la forma adottata: **default ereditato più override**.

```python
GOOGLE_SHEET_NAME = os.environ.get("GOOGLE_SHEET_NAME") or f"Transazioni {ANNO_BUDGET}"
```

Il legame c'è — al cambio d'anno resta una modifica sola, che è ciò che il test presidia — ma
non è obbligatorio: si scioglie senza toccare il codice.

L'alternativa più radicale (due costanti del tutto indipendenti, il nome del foglio col suo
letterale) è stata scartata per il motivo opposto: riporterebbe il cambio d'anno a due
modifiche a mano, e nessun test potrebbe accorgersi se ne dimentichi una.

### Costante con override, non derivazione dall'orologio

`ANNO_BUDGET = datetime.now().year` toglierebbe la manutenzione annuale, ma introduce un
guasto a orologeria: **il 1° gennaio a mezzanotte `GOOGLE_SHEET_NAME` punterebbe a una scheda che
può non esistere ancora**, e ogni scrittura fallirebbe con `errore_scrittura` finché qualcuno
non la crea. Un cambio silenzioso di destinazione è peggio di una manutenzione dimenticata —
e la manutenzione dimenticata la intercetta [SPEC-02](02-guardia-cambio-anno.md), che
confronta la costante con l'orologio e blocca invece di indovinare.

L'orologio quindi **serve**, ma come sentinella, non come sorgente.

### `int(os.environ.get(...) or 2026)` e non `os.environ.get(..., "2026")`

La forma con `or` tratta la stringa vuota come «non impostato»: `ANNO_BUDGET=` non fa
esplodere l'import con un `ValueError`. È la stessa forma già usata per `BUDGET_BOZZA_FILE`
a [`:63`](../budget_sheets.py#L63).

Un `ANNO_BUDGET=abc` fa comunque fallire l'import. È deliberato e coerente con il resto:
`BUDGET_BOZZA_TTL_MIN` invece degrada a un default perché un TTL storto non compromette i
dati, mentre un anno storto sceglierebbe il foglio sbagliato. Meglio non partire.

### Gli esempi `01/09/2026` nei messaggi restano a SPEC-03

Il criterio «nessun letterale `2026` fuori da `ANNO_BUDGET`», come era scritto in origine, era
**impossibile**: nel file ci sono altri tre `2026` che non c'entrano niente col nome del foglio —
il docstring di `validate_data` e i due esempi nei messaggi `chiedi_data` («…scrivila come
gg/mm/aaaa, per esempio 01/09/2026»). Sono date di esempio, non il nome di un foglio.

Non vengono toccati qui. Diventano un problema solo con [SPEC-03](03-vincolo-anno-sulle-date.md),
che rifiuta le date fuori anno: da quel momento un esempio fisso al 2026, con `ANNO_BUDGET`
diverso, farebbe suggerire al plugin una data che poi rifiuta —

```
plugin  → Di che giorno è? Scrivilo come gg/mm/aaaa, per esempio 01/09/2026.
utente  → 01/09/2026
plugin  → Questo budget tiene solo il 2027, e «01/09/2026» è di un altro anno.
```

— ed è SPEC-03 a riscrivere quelle righe comunque. La correzione va dove nasce il difetto,
non dove il letterale è stato notato per primo.

### Perché non un file di configurazione

Il profilo contiene già credenziali e token, ma non c'è nessun file di configurazione del
plugin, e introdurne uno per un intero sarebbe sproporzionato. Costante più variabile
d'ambiente è la convenzione che il file ha già.
