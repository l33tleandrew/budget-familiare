# SPEC-02 — Guardia sul cambio d'anno

**Stato:** fatto · **Dipende da:** [SPEC-01](01-anno-budget-centralizzato.md) ·
**Comportamento:** nuovo stato terminale

---

## Problema

Con [SPEC-01](01-anno-budget-centralizzato.md) l'anno è una costante che si aggiorna a mano.
Il giorno in cui l'anno civile la supera e nessuno se n'è accorto, due cose vanno storte in
silenzio:

1. **La scheda di destinazione potrebbe non esistere.** `GOOGLE_SHEET_NAME` resta
   `Transazioni 2026` mentre siamo nel 2027; se la scheda del 2027 non è ancora stata creata,
   ogni scrittura la manderebbe comunque nel foglio vecchio, il che è peggio di un errore.
2. **Ogni data senza anno finirebbe nell'anno sbagliato.** Da
   [SPEC-04](04-date-parlate.md) in poi «10 settembre» significa «nell'anno del budget», e
   il default quando la data manca è `datetime.now()` — che nel 2027 produce `01/01/2027`,
   una data che [SPEC-03](03-vincolo-anno-sulle-date.md) rifiuterebbe. **Il plugin
   rifiuterebbe il proprio valore di default**, con il messaggio sbagliato.

Il secondo punto è la ragione per cui questa guardia non è un vezzo: senza, il ramo `01→03`
diventa incoerente il 1° gennaio.

---

## Comportamento richiesto

Quando l'anno civile e `ANNO_BUDGET` divergono, il plugin **non registra niente** e lo dice
in modo azionabile, nominando entrambi gli anni.

Resta possibile **annullare** una transazione in corso: chiudere una bozza aperta non scrive
nulla e non deve diventare impossibile.

---

## Progettazione

### La sentinella

Nello strato "Validazione" di `budget_sheets.py`:

```python
def anno_disallineato():
    """True se l'anno civile e quello configurato non combaciano.

    L'orologio si accorge del cambio d'anno, la costante e' la presa d'atto:
    finche' le due non combaciano non si scrive niente, perche' la scheda
    dell'anno nuovo potrebbe non esistere e le date senza anno finirebbero
    tutte in quello vecchio.
    """
    return datetime.now().year != ANNO_BUDGET
```

### Lo stato e il suo messaggio

Un ramo in [`componi_messaggio()`](../budget_sheets.py#L668):

```python
    if stato == "errore_anno":
        return (f"Il budget è impostato sul {ANNO_BUDGET}, ma siamo nel "
                f"{datetime.now().year}. Non registro niente finché non viene "
                "aggiornato: serve la scheda del nuovo anno sul foglio e l'anno "
                "nuovo nella configurazione.")
```

E l'exit code in `EXIT` ([`:753`](../budget_sheets.py#L753)):

```python
    "errore_anno": 7,
```

### Il controllo

In [`_turno()`](../budget_sheets.py#L854), **dopo** il ramo `annulla` e prima di tutto il
resto:

```python
        if annulla:
            cancella_bozza()
            _emetti("annullata", campi_vuoti())

        if anno_disallineato():
            # Dopo `annulla` di proposito: abbandonare una bozza rimasta aperta
            # non scrive niente e non deve restare impossibile.
            _emetti("errore_anno", campi_vuoti())
```

La posizione è prima del `if nuova` e prima di `carica_bozza()`: non si tocca la bozza
esistente, che resta dov'è in attesa che la configurazione venga sistemata.

### Aggiornamento della documentazione

In [`ARCHITECTURE.md`](../ARCHITECTURE.md):

- **§6, tabella degli stati**: aggiungere `errore_anno` — bozza intatta, exit 7.
- **§6, exit code**: il 7 entra nella sequenza degli errori non di rete.
- **§7, albero decisionale**: il nuovo ramo, subito dopo `annulla`.
- **§11 e §13.4**: la manutenzione annuale di `ANNO_BUDGET` ora ha una guardia che la
  presidia. (L'avvertenza «⚠️ cambia a ogni anno solare» non c'è più: l'ha tolta
  [SPEC-01](01-anno-budget-centralizzato.md) insieme al letterale.)

---

## Fuori scope

- **Qualunque vincolo sulle date scritte dall'utente**: è [SPEC-03](03-vincolo-anno-sulle-date.md).
- Creare automaticamente la scheda del nuovo anno sul foglio. Richiede una chiamata API di
  scrittura sulla struttura del documento, con i suoi permessi e i suoi modi di fallire: è un
  altro cambiamento, con un'altra ragione.
- Avvisare in anticipo (es. a dicembre). Sarebbe utile, ma è una funzione diversa — una
  notifica proattiva, non una guardia — e non ha un posto naturale in un plugin che parla
  solo quando l'utente scrive.

---

## Criteri di accettazione

- [x] con l'orologio alle 23:59 del 31/12/2026, `anno_disallineato()` è `False`
- [x] con l'orologio al 01/01/2027, `anno_disallineato()` è `True`
- [x] Con anno disallineato, un turno qualsiasi: stato `errore_anno`, exit **7**,
      **nessuna riga scritta**, **bozza preesistente intatta**
- [x] Con anno disallineato, `annulla` produce ancora `annullata` e cancella la bozza
- [x] Il messaggio cita **entrambi** gli anni e dice cosa fare
- [x] Con anno allineato (il caso normale) nulla cambia: `make test` verde senza modificare
      test esistenti — 268 → **277**, nessun test preesistente toccato

---

## Test

Nuova classe in `tests/test_budget_sheets.py`. L'anno si fissa con
`mock.patch.object(bs, "ANNO_BUDGET", ...)`; i tre test che provano il confine di mezzanotte
spostano l'orologio, con un helper di due righe.

```python
class TestGuardiaAnno(ConBozza):

    @staticmethod
    def orologio(momento):
        return mock.patch.object(bs, "datetime", **{"now.return_value": momento})

    def test_un_minuto_prima_di_mezzanotte_non_scatta(self):
        with self.orologio(datetime(bs.ANNO_BUDGET, 12, 31, 23, 59)):
            self.assertFalse(bs.anno_disallineato())

    def test_il_primo_gennaio_scatta(self):
        with self.orologio(datetime(bs.ANNO_BUDGET + 1, 1, 1)):
            self.assertTrue(bs.anno_disallineato())

    def test_non_si_registra_niente(self):
        """Il criterio vero: non che risponda male, ma che non scriva."""
        # con ANNO_BUDGET patchato a un anno diverso da quello di sistema:
        # stato errore_anno, append_row mai chiamata, bozza invariata

    def test_annulla_resta_possibile(self):
        """Chi ha una bozza aperta deve poterla chiudere anche a configurazione
        rotta, altrimenti resta incastrato in un dialogo a meta'."""
```

I due test sul comportamento usano i mock già in uso nel file per `get_access_token` e
`append_row`, e `ConBozza` per la bozza su file temporaneo.

---

## Verifica

```bash
cd /Users/loprieno-andrea/Documents/budget-familiare-workflow

make test

# la sentinella legge l'orologio di sistema, quindi a mano si muove la costante
python3 -c "
import budget_sheets as b
print('allineato:   ', b.anno_disallineato())          # atteso False
b.ANNO_BUDGET -= 1
print('disallineato:', b.anno_disallineato())          # atteso True
"

# il blocco end-to-end, senza toccare la rete e senza toccare la bozza vera:
# senza BUDGET_BOZZA_FILE, `append --annulla` cancellerebbe il dialogo in corso
# sulla macchina su cui si sta provando.
B=$(mktemp)
ANNO_BUDGET=2025 BUDGET_BOZZA_FILE=$B python3 budget_sheets.py \
  append --nuova --importo 30 --categoria Supermercato
echo "exit: $?"      # atteso: 7, e nel JSON stato = errore_anno

# e che annulla passi comunque
ANNO_BUDGET=2025 BUDGET_BOZZA_FILE=$B python3 budget_sheets.py append --annulla
echo "exit: $?"      # atteso: 3, stato = annullata
rm -f $B
```

---

## Decisioni e alternative scartate

### `annulla` resta consentito

«Impedisce di procedere» è stato letto come «non si registra nulla», non come «non si può
chiudere una bozza aperta». Bloccare anche l'annullamento lascerebbe chi ha un dialogo a metà
senza alcuna via d'uscita fino al prossimo deploy, e `annulla` non scrive niente per
definizione: cancella un file locale.

Se il blocco dovesse diventare totale, è spostare il controllo di quattro righe più su.

### Exit code 7 e non 4

Il 4 è libero, ma la tabella esistente usa `0` per il successo, `3` per «in dialogo o
terminale benigno», e `1, 2, 5, 6` per gli errori. Il 7 continua la sequenza degli errori
invece di infilarsi in mezzo agli stati benigni.

### La sentinella è l'orologio, la verità è la costante

L'alternativa — far derivare `ANNO_BUDGET` da `datetime.now().year` — è discussa e scartata
in [SPEC-01](01-anno-budget-centralizzato.md#decisioni-e-alternative-scartate): il cambio
automatico punterebbe a una scheda che può non esistere. Qui l'orologio fa il lavoro che sa
fare — accorgersi che il tempo è passato — e la decisione resta a chi aggiorna la costante
dopo aver creato la scheda.

### `!=` e non `>` — la docstring era sbagliata, non il codice

In questo file il codice diceva `!=` e la docstring «ha superato», cioè `>`. I due divergono
per chi porta avanti `ANNO_BUDGET` **in anticipo**: scheda del 2027 creata a dicembre 2026 e
costante aggiornata subito. Con `>` il plugin continuerebbe a funzionare e le spese di
dicembre finirebbero in silenzio sulla scheda del 2027 — dato mal collocato, esattamente il
male che questa guardia esiste per impedire. Con `!=` resta bloccato fino a Capodanno:
fastidioso, ma rumoroso, e si annulla riportando indietro la costante.

Vale `!=`. La docstring è stata riscritta di conseguenza, e c'è un test apposta
(`test_il_31_dicembre_dell_anno_prima_scatta`) perché la prossima persona non la «corregga»
al contrario.

### Niente `oggi` iniettabile, al contrario delle date relative

La prima stesura di questo spec dava alla sentinella un `oggi=None`, «per la stessa ragione
delle date relative». È un argomento preso in prestito, e in prestito non regge: in
[`normalizza_data_relativa()`](../budget_sheets.py#L374) l'orologio è **l'unico** ingresso —
«ieri» senza iniettarlo non si prova. Qui i lati del confronto sono due, e quello facile da
muovere è l'altro: `ANNO_BUDGET` è una globale, `mock.patch.object` basta. Infatti i test di
comportamento lo patchano già, e il parametro non lo usavano.

Restava un solo caso che la costante non sa esprimere — le **23:59 del 31 dicembre**, cioè il
confine come lo pensa chi legge. Si prova lo stesso sostituendo `bs.datetime` per il tempo di
una chiamata: due righe di helper nella classe di test.

Contro, e ha deciso: era un parametro che la produzione non passa mai. `_turno()` chiama
`anno_disallineato()` nudo e [`componi_messaggio()`](../budget_sheets.py#L687) legge `now()`
per conto suo, quindi l'unico effetto possibile di un `oggi` iniettato da codice vero sarebbe
**far dire due anni diversi alla guardia e al messaggio**. Una superficie che esiste solo per
i test, e che può solo rompere qualcosa, non vale il posto che occupa.

### La suite si isola dall'orologio, con **una** sentinella

Non previsto da questo spec, ma è una conseguenza diretta del metterlo in `_turno()`: la
guardia accoppia all'orologio **tutta** la suite. `TestCli`, `test_plugin.py` e le due eval
(`OGGI = datetime.now()`) eseguono turni veri, quindi il 1° gennaio diventerebbero rosse in
blocco. Misurato: `ANNO_BUDGET=2025 make test` produce **106 fallimenti**.

Cento fallimenti muti non sono un allarme, sono rumore: dicono che qualcosa è rotto, non
cosa. Quindi:

- `tests/percorsi.py` — l'unico modulo che ogni file di test importa *prima* di
  `budget_sheets`, che legge `ANNO_BUDGET` all'import — fa
  `os.environ.setdefault("ANNO_BUDGET", str(datetime.now().year))`. È la stessa finestra che
  `test_plugin.py` già usa per `BUDGET_BOZZA_FILE`. `setdefault` e non un'assegnazione, così
  `ANNO_BUDGET=2025 make test` resta una prova possibile.
- **Un** test, `TestAnnoBudget.test_la_costante_e_allineata_all_anno_civile`, rilegge il
  default **dal sorgente** (subprocess con `ANNO_BUDGET` rimosso dall'ambiente — leggere
  `bs.ANNO_BUDGET` darebbe il valore iniettato e non direbbe nulla) e lo confronta con l'anno
  civile. Il 1° gennaio diventa rosso quello, da solo, con nel messaggio l'ordine da seguire:
  prima la scheda sul foglio, poi la costante.

L'alternativa — lasciare che sia il rosso di massa a fare da allarme — è stata scartata: un
test che fallisce a Capodanno costa a qualcuno un'ora per capire perché, e quel qualcuno sta
già gestendo il cambio d'anno. Un rosso che dice cosa fare vale cento rossi muti.

### Il controllo sta in `_turno` e non in un hook del plugin

Metterlo in `pre_llm_call` o in `pre_tool_call` lo renderebbe invisibile alla CLI, che è
ancora una strada valida per uso manuale. In `_turno` vale per entrambe, ed è il punto da cui
passa ogni scrittura.
