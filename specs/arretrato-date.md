# Arretrato — date

**Non è uno spec.** È il posto dove sta tutto ciò che è stato valutato, misurato e **rinviato**
mentre si scriveva [SPEC-04](04-date-parlate.md), più i due spec che sono confluiti qui:
`05-prompt-date-parlate.md` e `06-eval-date-parlate.md`.

Una voce di questo file diventa uno spec vero solo quando qualcuno la prende in carico. Fino
ad allora non è un impegno: è una decisione già istruita, con la misura accanto, che qualcuno
non dovrà rifare da capo.

> **Perché esiste.** SPEC-04 nella sua prima stesura copriva 3 forme su 22 e chiamava «fuori
> scope» tutto il resto, con una riga per voce. Quel resto è il problema vero — la maggior
> parte delle date dette a voce ci cade dentro — e meritava le sue misure invece di un elenco.

---

## Come si legge

| Sezione | Cosa contiene |
|---|---|
| [La forma verso cui si va](#la-forma-verso-cui-si-va) | l'architettura decisa per quando le famiglie saranno più di una |
| [Famiglie rinviate](#famiglie-rinviate) | le voci vere e proprie, con costo e rischio |
| [Il prompt e la misura](#il-prompt-e-la-misura) | ciò che resta degli spec 05 e 06 |
| [Difetti noti](#difetti-noti) | cose rotte oggi, indipendenti dalle famiglie |
| [Reperti](#reperti) | le misure su cui tutto quanto sopra si regge |

L'ordine consigliato di lavorazione è in fondo.

---

## La forma verso cui si va

SPEC-04 è **un ramo solo**, quindi non ha una forma: si innesta e basta. Dalla seconda famiglia
in poi serve una struttura, ed è stata decisa e prototipata.

**Una pulizia parametrica più N rami indipendenti**, ciascuno con il suo `fullmatch`:

```python
_RUMORE   = ("di", "del", "dello", "della", "dei", "dal",
             "sera", "serata", "mattina", "mattino", "pomeriggio")

def _pulisci(testo, rumore=_RUMORE): ...      # estende la pulizia esistente (:419-420)

def normalizza_data_relativa(testo, oggi=None):
    p = _pulisci(testo)
    1. p in _GIORNI_FA                     # + stamattina/stamane/stasera = oggi
    2. _RE_SETTIMANA.fullmatch(p)          # invariato; «scorso» qui è PORTANTE
    3. _RE_CONTATA.fullmatch(p)            # tre giorni fa
    4. _RE_GIORNO_MESE.fullmatch(p)        # SPEC-04, esteso
    return testo
```

### Perché a rami e non un pattern unico

Prototipate entrambe le forme sullo stesso corpus (26 forme da riconoscere, 16 avversariali):
**comportamento identico**, 24/26 e 16/16. La scelta non è di funzionalità ma di
manutenibilità, e il discriminante è emerso da una misura:

```
«lunedì scorso»              →  «scorso» è PORTANTE  (sceglie la settimana prima)
«il dieci settembre scorso»  →  «scorso» è RUMORE    (la data è già completa)
```

Stessa parola, due ruoli opposti: **un preprocessing uniforme non può averli entrambi.** A
rami, la regola è un *dato* — una seconda tupla passata a `_pulisci`. In un pattern unico è
*struttura duplicata* (`(?:scorso |ultimo )?` in due alternanze, +44 caratteri, e una copia in
più per ogni famiglia futura).

Una terza forma — parser a token con verifica dei residui — è stata **scartata dalla misura**:
21/26, perché lo slash non è un confine di token e perde `10/09`; le serve una tabella di anni
di 300 voci contro 11; e ha comunque bisogno dei rami regex per le relative. Non è
un'architettura, è l'implementazione di un ramo.

### Il vincolo che non si tocca

`fullmatch` su ogni ramo. È la riga che rende «10 settembre 5 euro» una domanda e non una data,
e vale tanto per SPEC-04 quanto per tutto quello che segue. Insieme al principio **il match è
la validazione** — vocabolari chiusi dentro il pattern, nessun `if` a valle — è ciò che tiene
vuota la colonna «forma capita male» dello script.

---

## Famiglie rinviate

### Anno esplicito

**Cosa:** `10 settembre 2026`, `10 settembre 2025`.

**Costo:** un gruppo opzionale `(?: (\d{4}))?` — **13 caratteri** di pattern.

**Perché è la prima voce.** Oggi `10 settembre 2025` riceve «Non ho capito la data», che è
**falso**: la data è stata capita benissimo, non è stata accettata. È esattamente la bugia
contro cui [SPEC-03](03-vincolo-anno-sulle-date.md) ha costruito tutto il suo progetto. Con il
gruppo, la data si compone come `10/09/2025`, arriva al cancello e riceve il messaggio onesto
«questo budget tiene solo il 2026, e «10/09/2025» è di un altro anno». E `10 settembre 2026` —
l'anno **giusto**, detto per completezza — smette di essere un errore.

**Gli anni a parole** (`duemilaventicinque`) sono una voce a parte. SPEC-04 li scartava con
questo argomento: una tabella di 100 anni pesa 1783 dei 2215 caratteri del pattern, l'80%, per
riconoscere stringhe che vengono comunque rifiutate. La misura è giusta, l'alternativa no —
fra «un anno solo» e «cento anni» c'è un mezzo che non era stato valutato:

| Vocabolario | Pattern |
|---|---|
| solo `ANNO_BUDGET` | 400 car. |
| token generico `duemila[a-z]+` | **402 car.** |
| finestra ±5 anni (11 voci) | 567 car. |
| 100 anni (scartato) | 2168 car. |

Il «prezzo accettato» dallo spec costa **167 caratteri**, non 1783. Una finestra ±5 copre ogni
caso realistico e dà il messaggio onesto anche alla forma parlata.

**Dubbio aperto:** se il motore di trascrizione rende già «duemilaventicinque» come `2025` —
cosa che molti fanno — allora l'anno in cifre copre il caso dettato e la forma a parole non si
esercita mai. Serve un campione di trascrizioni vere per deciderlo.

### Ordinali

**Cosa:** `primo settembre`, e la questione di `1°` / `1o`.

**Perché.** In italiano non si dice «uno settembre». SPEC-04 esclude gli ordinali, e la misura
mostra l'effetto rovesciato:

```
'primo settembre'  → — intatta → chiedi_data      ← la forma che si dice
'uno settembre'    → 01/09/2026                    ← la forma che nessuno dice
```

Il giorno 1 non ha forma parlata usabile. **Costo per chiuderla: una riga** —
`_GIORNI_LETTERE["primo"] = 1`.

`1°` e `1o` restano comunque fuori: richiedono di decidere come normalizzare il segno di grado,
che è una decisione sul preprocessing e non sul vocabolario.

### Riempitivi

**Cosa:** `10 di settembre`, `del 10 settembre`, `dal 10 settembre`.

**Dove:** preprocessing, un insieme chiuso di parole da togliere. Non tocca nessun pattern.

**Attenzione a `dal`/`dalla`:** indicano l'inizio di un intervallo, non un punto. «Dal 10
settembre» non è la stessa cosa di «del 10 settembre». Rischio basso per una singola spesa, ma
va deciso invece che ereditato.

### Momento del giorno

**Cosa:** `ieri sera`, `ieri mattina`, `sabato sera`, `venerdì pomeriggio`, `stamattina`,
`stasera`.

**La riduzione che la rende quasi gratuita:** «ieri sera» **non è una data nuova**. È «ieri»
più rumore — il momento del giorno non porta informazione di data, perché il confine del giorno
è la mezzanotte. Quindi non è un ramo: sono tre parole nello stesso insieme dei riempitivi.

`stamattina`, `stamane`, `stasera` sono invece **contrazioni che significano oggi**, e vanno in
`_GIORNI_FA` con valore 0, non nell'insieme del rumore.

`stanotte` resta fuori: detta la mattina significa la notte appena passata, detta alle due di
notte significa oggi. È genuinamente ambigua, e l'invariante «quando ambiguo vince il passato»
non la risolve, perché entrambe le letture sono nel passato.

**È la famiglia con il miglior rapporto fra costo e copertura di tutto l'arretrato**, ed è
quella che il canale vocale esercita di più.

### Relative contate

**Cosa:** `tre giorni fa`, `una settimana fa`, `due settimane fa`.

**Come:** un ramo nuovo, `(numero|\d{1,2}) (giorni|giorno|settimane|settimana) fa`. Non ha il
problema dell'anno: calcola da oggi. Se il risultato cade fuori dall'anno del budget, il
cancello di SPEC-03 risponde già la verità.

**Intervallo dei numeri a parole: 1..31.** Misurato: 1..99 costa 1148 caratteri di pattern,
1..31 ne costa 312, 1..20 ne costa 206. «Novantasette giorni fa» non lo dice nessuno — oltre il
mese si dice la data.

**`mesi fa` resta fuori,** e non per dimensione: con 30 giorni è semplicemente **sbagliato**
(«un mese fa» detto il 31 marzo darebbe l'1 marzo), e con l'aritmetica di calendario porta un
caso limite — il giorno 31 in un mese di 30 — che va deciso e inchiodato con dei test suoi.

**Asimmetria da sanare o da dichiarare:** con `giorni` e `settimane` dentro e `mesi` fuori,
«tre giorni fa» e «una settimana fa» funzionano e «un mese fa» no. A chi parla sembra
arbitrario, e il messaggio di rifiuto non lo spiega.

### Abbreviazioni

**Cosa:** `10 set`, `4 ott`, `10 sett`.

**Come:** una tabella `_MESI_ABBR` accanto a `_MESI`, generata o scritta. Nessun rischio noto:
le abbreviazioni dei mesi non collidono con niente.

**Nota:** più tipica dello scritto che del parlato. Priorità bassa se il canale principale
resta la voce.

### Forme numeriche complete

**Cosa:** `10/9/26`, `10/09/25` — cioè le numeriche **con l'anno**. La forma senza anno
(`10/09`, `10-09`, `10 09`) è già in SPEC-04.

**Attenzione:** vale il [divieto sul punto](04-date-parlate.md#divieti-permanenti). Il
separatore `.` collide con la notazione inglese degli importi e produce quattro errori
silenziosi misurati. Qualunque estensione di questa famiglia ammette `/` e `-`, mai `.`.

### Scorso

**Cosa:** `il dieci settembre scorso`, `lo scorso dieci settembre`.

**Non è un riempitivo,** ed è la trappola più seria di tutto l'arretrato. Se si mette «scorso»
nell'insieme del rumore, insieme a «di» e «sera», il risultato misurato è:

```
«il dieci settembre scorso» detto a gennaio 2026  →  10/09/2026   ← FUTURA di 8 mesi
```

L'utente aveva detto «scorso», cioè esplicitamente «non quest'anno», e si ottiene una data
futura. È il tipo di errore peggiore possibile: silenzioso e in contraddizione letterale con
l'input.

**Il trattamento corretto** è riconoscere che «scorso» **sposta indietro**, in entrambi i rami:

- accanto a un giorno della settimana → l'occorrenza precedente (già fatto, `% 7 or 7`);
- accanto a una data completa → **l'anno precedente**.

Con quella regola, «il dieci settembre scorso» detto a gennaio 2026 compone `10/09/2025`, e il
cancello di SPEC-03 risponde la verità: «questo budget tiene solo il 2026, e «10/09/2025» è di
un altro anno». Nessuna politica nuova sulle date future, nessun ramo in più: basta smettere di
trattare una parola portante come rumore.

Questa voce **dipende** da [Anno esplicito](#anno-esplicito): senza un anno nella grammatica non
c'è niente da spostare indietro.

### Fuori da tutte le famiglie

Valutate e escluse **per concetto**, non per dimensione. Non diventeranno voci.

| Forma | Perché no |
|---|---|
| `il 10` (mese sottinteso) | unica forma che trasforma un taglio sbagliato del modello in una data valida **in silenzio**. Vedi i [divieti di SPEC-04](04-date-parlate.md#divieti-permanenti) |
| `settembre scorso`, `scorso settembre` | è un **periodo**, non un giorno. Una transazione ha una data |
| `domani`, `dopodomani`, `lunedì prossimo`, `fra tre giorni` | forme inequivocabilmente in avanti. Una relativa in avanti in un messaggio di spesa è quasi sempre un errore di trascrizione o un taglio sbagliato: meglio una domanda |
| `stanotte` | ambigua, e l'invariante non la risolve |
| il separatore `.` | collide con gli importi. Vedi i divieti |

---

## Il prompt e la misura

*Questa sezione assorbe `05-prompt-date-parlate.md` e `06-eval-date-parlate.md`.*

La modifica minima al prompt — i due esempi e il divieto «non convertirle» — **è entrata in
[SPEC-04](04-date-parlate.md#6-il-prompt)**, perché senza di essa il ramo non si attiva mai in
produzione e lo spec non sarebbe consegnabile. Quello che resta qui è ciò che SPEC-04 non
chiude.

### La regola 3 di SPEC-05 è giusta sul posto sbagliato

SPEC-05 diceva: *«L'anno non si nomina… nominarlo nel prompt lo esporrebbe al disallineamento
il giorno in cui cambia.»* È un argomento contro un **letterale in un file statico**, e per
`schemas.py` è corretto — SPEC-04 lo mantiene.

Ma non è l'unico posto. [`pre_llm_call`](../__init__.py#L55-L60) inietta già contesto dinamico a
ogni turno, e **un'iniezione a runtime non può invecchiare**. SPEC-05 ha valutato un solo posto
e ne ha dedotto una regola sull'informazione stessa.

**Ipotesi da falsificare, non da assumere:** dare al modello la data odierna, da sola,
**peggiora** il problema dell'anno invece di risolverlo. La regola dello script è «una data
senza anno è dell'anno del budget, sempre». Un modello che sa che giorno è ragiona come una
persona: a gennaio, «il dieci settembre» diventa «il settembre scorso» → 2025 → rifiutato dal
cancello. Per aiutare davvero servirebbe iniettare **la regola**, non la data.

### Banco

Il banco di prova che deciderebbe cosa deve arrivare nel campo `data`. Quattro bracci, stesso
corpus, orologio congelato:

| Braccio | Cosa prova | Costo |
|---|---|---|
| 1 · script | il pavimento deterministico | gratis |
| 2 · modello, senza data odierna | il comportamento di oggi | a pagamento |
| 3 · modello + «Oggi è …» | l'iniezione in `pre_llm_call` | a pagamento |
| 4 · modello + «Oggi è …» + la regola dell'anno | l'ipotesi qui sopra | a pagamento |

**Due orologi: settembre e gennaio.** È a gennaio che l'ipotesi si rompe, ed è l'unico modo di
vederlo.

**La metrica primaria sono gli errori silenziosi, non la copertura**, perché le due strade
sbagliano in modi non confrontabili:

| | forma non capita | forma capita **male** |
|---|---|---|
| script | domanda all'utente | **impossibile** — il match è la validazione |
| modello | domanda all'utente | **riga sbagliata sul foglio**, se l'utente conferma |

E l'errore del modello passa `validate_data`, passa `_nell_anno`, entra nel riepilogo, e la
`resa_verbatim` (ARCHITECTURE.md §5, passo 7) lo mostra **nella voce autorevole dello script**.
Un braccio al 95% di copertura con 4% di errori silenziosi è peggiore di uno all'80% con zero.

#### I tre limiti del banco, da risolvere prima di costruirlo

**Potenza statistica.** La metrica primaria sono eventi rari, e un corpus da 120 forme non li
misura:

| forme | con 0 errori osservati, il tasso vero può arrivare a |
|---|---|
| 120 | **2,5 %** — una riga sbagliata ogni 40 spese |
| 300 | 0,99 % |
| 600 | 0,50 % |
| 1200 | 0,25 % |

Per *distinguere* due bracci (0,5 % contro 2 %) servono ~860 forme **per braccio**. Non è un
problema di costo in euro: è che la conclusione non reggerebbe.

**Validità del corpus.** Le forme scritte da noi sono ciò che *immaginiamo* sia una dettatura.
C'è una fonte migliore e disponibile: trenta spese dettate davvero valgono più di trecento
inventate.

**Il braccio giusto.** [`eval_modello.py`](../tests/eval_modello.py) ha un suo `ISTRUZIONI`
(righe 63-79) che **non è il prompt di produzione**, e uno schema di output che impone
`gg/mm/aaaa` (righe 47-48). Riusarlo così misurerebbe un modello che non è quello che gira.

### Il difetto di `eval_modello.py`

Indipendente dal banco, e va chiuso comunque. Due punti pretendono che il modello **converta**
in `gg/mm/aaaa`:

- `tests/eval_modello.py:47-48`, lo schema di output forzato — un secondo prompt che
  sovrascrive proprio la descrizione che dovrebbe misurare;
- `tests/eval_modello.py:102-107`, lo scorer: qualunque valore che non sia `""`, oggi, o un
  `gg/mm/aaaa` valido diventa `None` e fallisce il confronto.

**Con SPEC-04 applicato, un modello che obbedisce a «non convertirle» fallisce
`make eval-modello` per costruzione.** Lo scorer e lo schema vanno cambiati insieme al prompt.

### Il caso eval end-to-end

*Era il contenuto di SPEC-06.* Un caso in `tests/casi_eval.json` che chiuda il giro completo —
messaggio informale → campi del tool → stato → riga sul foglio — in modo deterministico e
gratuito. Il parente più prossimo è `data-esplicita`.

```jsonc
{
  "id": "data-parlata",
  "descrizione": "Data a parole nel messaggio: il modello la passa, non la converte.",
  "messaggio": "il dieci settembre ho fatto benzina, 45 euro",
  "interpretazione": {
    "data": "dieci settembre",                 // passata così com'è, non convertita
    "categoria": "Auto / Moto",
    "sottocategoria": "Benzina",
    "importo": "45.00",
    "descrizione": "Benzina"
  },
  "valuta_interpretazione": true,
  "risposte": ["sì"],
  "stati_attesi": ["chiedi_conferma"],
  "esito": "scritta",
  "riga_attesa": {
    "data": "10/09/{ANNO}",
    "tipo": "Uscita",
    "categoria": "Auto / Moto",
    "sottocategoria": "Benzina",
    "importo": 45.0
  }
}
```

Il caso mette alla prova due cose insieme: `interpretazione.data` verifica che il modello
**non** converta, `riga_attesa.data` che lo script converta al posto suo. Il segnaposto
`{ANNO}` esiste già ed è risolto al caricamento da
[`_segnaposto()`](../tests/eval_protocollo.py#L42): un anno letterale sarebbe una bomba a
orologeria.

Il messaggio usa «il dieci settembre» e non «10 settembre» di proposito: la forma a parole è
quella su cui il modello è più tentato di intervenire, ed è il caso peggiore.

**Un caso solo, non una batteria.** Le 1860 combinazioni di SPEC-04 coprono già il parsing.
Qui serve chiudere il giro completo, e per quello un caso rappresentativo basta.

**Niente caso per «10 settembre 5 euro».** Sarebbe il più interessante — misura se il modello
separa giorno e importo — ma `riga_attesa` non sarebbe deterministica: se il modello sbaglia il
taglio, il dialogo prende un numero variabile di turni e il caso diventa rumore. Il
comportamento **dello script** di fronte a un taglio sbagliato è già inchiodato da
`test_un_importo_non_diventa_una_data` in SPEC-04. Quel che resta scoperto è la *frequenza* con
cui il modello sbaglia, ed è una misura, non un test: appartiene al banco.

---

## Difetti noti

Cose rotte oggi, indipendenti dalle famiglie di date.

### Messaggio

Il rifiuto parla a chi scrive, in un plugin che dichiara di attivarsi anche a voce:

```
utente dice  │ "un mese fa"
plugin dice  │ Non ho capito la data «un mese fa». Scrivila come gg/mm/aaaa,
             │ per esempio 29/09/2026.
```

«Scrivila come gg/mm/aaaa» è un consiglio **inapplicabile** a chi sta dettando. È una riga in
[`componi_messaggio`](../budget_sheets.py#L726-L743), ed è probabilmente il miglior rapporto
fra valore e costo di tutto questo file. Va deciso insieme: il suggerimento dovrebbe proporre
una forma che si possa *dire* («per esempio «dieci settembre»»), e restare coerente con quello
che lo script sa davvero riconoscere in quel momento — cioè cambiare insieme alle famiglie.

### La data non si riporta fra spese consecutive

«Ieri ho speso 30 al supermercato, e 15 di benzina»: la seconda transazione apre una bozza
nuova con `data=""` e prende **oggi**, non ieri. Chi detta più spese di fila è il caso d'uso
tipico del canale vocale, e l'errore è silenzioso.

Non è una famiglia di date: è una decisione sul dialogo, e tocca `_turno()` e la bozza. Va
istruita a parte.

### `ARCHITECTURE.md` §4.5 dice una cosa falsa

«Non si guarda mai avanti» è scritto come proprietà del sistema; è la proprietà di un ramo.
Vedi la sezione sull'invariante in [SPEC-04](04-date-parlate.md). La correzione è dovuta a
prescindere da qualunque voce di questo file.

Manca anche una **voce di glossario** sulle date: §15 non ha `data relativa` né `data parlata`
né `ANNO_BUDGET`.

### `TestDataRelativa.OGGI` è un letterale

`datetime(2026, 9, 17)` mentre il resto della suite fissa `ANNO_BUDGET` all'anno civile
(`tests/percorsi.py:18`). **Attenzione:** parametrizzarlo su `ANNO_BUDGET` **rompe** le
asserzioni su «lunedì scorso», che dipendono dal giorno della settimana — il 17 settembre 2026
è giovedì, il 17 settembre 2027 è venerdì. Serve una data scelta, non una sostituzione.

### Conteggi stantii

I casi eval sono **20**, non 19. Stantio in `tests/README.md` e in `ARCHITECTURE.md`.

---

## Reperti

Le misure su cui tutto quanto sopra si regge. Rifarle costa più che leggerle.

**Copertura del codice attuale.** 22 forme provate; SPEC-04 nella sua prima stesura ne chiudeva
3. Le famiglie non coperte né prima né dopo: momento del giorno, relative contate, riempitivi,
numeriche parziali, abbreviazioni.

**Il costo del vocabolario degli anni.** Vedi [Anno esplicito](#anno-esplicito): 400 / 402 /
567 / 2168 caratteri per un anno / token generico / finestra ±5 / cento anni.

**A contro B contro parser a token.** Vedi [La forma verso cui si va](#la-forma-verso-cui-si-va):
24/26 e 16/16 per le prime due, 21/26 per la terza.

**Il conflitto su «scorso».** Vedi [Scorso](#scorso). Pattern unico ingenuo: fallisce entrambe
le forme. Pattern unico corretto: +44 caratteri e struttura duplicata. A rami: una tupla.

**I separatori numerici.** 12 forme da riconoscere, 18 avversariali:

| Separatori | Copre | Errori silenziosi |
|---|---|---|
| nessuno | 7/12 | 0 |
| `/` e `-` | 11/12 | 0 |
| `/`, `-`, spazio | 12/12 | 0 |
| `/`, `-`, spazio, `.` | 12/12 | **4** |

**L'invariante «mai in avanti».** Misurato il 23/09/2026: `31/12/2026` arriva a
`chiedi_categoria`; `domani` resta intatta. Non è mai stato un rifiuto, è una non-copertura.

**Potenza statistica del banco.** Vedi [Banco](#banco).

---

## Ordine consigliato

Non è un impegno, è il risultato del confronto fra costo, rischio e copertura.

| | Voce | Perché lì |
|---|---|---|
| 1 | [Momento del giorno](#momento-del-giorno) + [Riempitivi](#riempitivi) | miglior rapporto costo/copertura, solo preprocessing, zero pattern nuovi, ed è ciò che il canale vocale esercita di più |
| 2 | [Anno esplicito](#anno-esplicito) in cifre | 13 caratteri, e toglie una bugia dal messaggio di rifiuto |
| 3 | [Ordinali](#ordinali) — solo `primo` | una riga, e il giorno 1 smette di essere irraggiungibile |
| 4 | [Messaggio](#messaggio) | una riga, ma va dopo 1-3 perché deve dire il vero su ciò che lo script sa |
| 5 | [Relative contate](#relative-contate) | un ramo nuovo, nessun rischio noto |
| 6 | [Scorso](#scorso) | dipende da 2 |
| 7 | [Abbreviazioni](#abbreviazioni) · [numeriche complete](#forme-numeriche-complete) | priorità bassa nel canale vocale |
| — | [Banco](#banco) · [caso eval](#il-caso-eval-end-to-end) · [difetti noti](#difetti-noti) | trasversali, si prendono quando servono |

Le voci 1-3 e 5 richiedono tutte di **estendere la pulizia**, quindi la prima che si prende
porta con sé [la forma a rami](#la-forma-verso-cui-si-va).
