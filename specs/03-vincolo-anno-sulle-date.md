# SPEC-03 — Vincolo d'anno sulle date

**Stato:** fatto · **Dipende da:** [SPEC-01](01-anno-budget-centralizzato.md) ·
**Comportamento:** ⚠️ **restringe** un comportamento esistente

---

## Problema

Il foglio tiene **un anno solo** — la scheda si chiama `Transazioni 2026` — ma oggi nulla
impedisce di scriverci dentro una riga di un altro anno:

```
utente  │ 10/09/2025 spesa 40
agente  │ Data: 10/09/2025 … Confermi?
utente  │ sì
        │ → riga del 2025 scritta nel foglio del 2026
```

[`validate_data()`](../budget_sheets.py#L341) accetta qualunque anno a quattro cifre: è un
controllo di formato, e il formato di `10/09/2025` è ineccepibile. La regola secondo cui il
budget copre un anno solo non è scritta da nessuna parte.

---

## Comportamento richiesto

Una transazione fuori dall'anno configurato **non si può registrare, da nessuna strada e in
nessun formato**: né `gg/mm/aaaa`, né parlata, né relativa.

Il rifiuto deve dire **la verità**. Chi scrive `10/09/2025` non ha sbagliato a scrivere: ha
indicato un anno che questo foglio non tiene. Dirgli «non ho capito la data» lo manderebbe a
riscrivere la stessa data nello stesso formato.

| Input | Messaggio |
|---|---|
| `10/09/2025` | «Questo budget tiene solo il 2026, e «10/09/2025» è di un altro anno…» |
| `31/02/2026` | «Non ho capito la data «31/02/2026»…» |

---

## Progettazione

### Dove va il controllo, e perché non in `validate_data`

**Il formato lo valida `validate_data`, la politica la applica `normalizza()`.**

`validate_data` è un predicato di formato — lo dice il nome, lo dice il docstring, e ha
quattro classi di test che lo trattano così. L'anno del budget è una **regola di dominio**,
non una sintassi. Tenerle separate ha due effetti concreti: `validate_data` non va toccata
(quindi nessuno dei suoi test cambia) e il messaggio può dire la verità.

### La regola

```python
def _nell_anno(data):
    """True se la data gg/mm/aaaa e' dentro l'anno del budget.

    Sta qui e non in validate_data di proposito: quella verifica il formato, e
    il formato di "10/09/2025" e' ineccepibile. Questa e' la regola secondo cui
    il foglio tiene un anno solo, ed e' una regola, non una sintassi.
    """
    return data.endswith(f"/{ANNO_BUDGET}")
```

### Il cancello

In [`normalizza()`](../budget_sheets.py#L580), il primo blocco diventa:

```python
    if not campi.get("data"):
        campi["data"] = datetime.now().strftime("%d/%m/%Y")
    campi["data"] = normalizza_data_relativa(campi["data"])
    if not validate_data(campi["data"]) or not _nell_anno(campi["data"]):
        rifiutato, campi["data"] = campi["data"], ""
        return campi, "chiedi_data", rifiutato
```

È un punto solo, ed è quello da cui **ogni** data passa: relativa, parlata o in cifre.

### Il messaggio onesto

In [`componi_messaggio()`](../budget_sheets.py#L668), il ramo `chiedi_data` distingue i due
rifiuti:

```python
    if stato == "chiedi_data":
        if rifiutato and validate_data(rifiutato):
            # Formato giusto, anno sbagliato: dirgli che non si e' capito
            # sarebbe falso, e lo manderebbe a riscrivere la stessa data.
            return (f"Questo budget tiene solo il {ANNO_BUDGET}, e «{rifiutato}» è di un "
                    f"altro anno. Non posso registrarla qui. Di che giorno del "
                    f"{ANNO_BUDGET} si tratta?")
        if rifiutato:
            return (f"Non ho capito la data «{rifiutato}». Scrivila come gg/mm/aaaa, "
                    f"per esempio 01/09/{ANNO_BUDGET}.")
        return (f"Di che giorno è? Scrivilo come gg/mm/aaaa, "
                f"per esempio 01/09/{ANNO_BUDGET}.")
```

### L'esempio deve stare dentro l'anno

Le due ultime righe portavano un `01/09/2026` scritto a mano, indipendente da tutto. Finché
nessuno rifiuta le date fuori anno è innocuo; **da questo spec in poi non lo è più**, perché
il plugin arriverebbe a suggerire una data che poi rifiuta:

```
plugin  → Di che giorno è? Scrivilo come gg/mm/aaaa, per esempio 01/09/2026.
utente  → 01/09/2026
plugin  → Questo budget tiene solo il 2027, e «01/09/2026» è di un altro anno.
```

Un giro chiuso, da cui l'utente esce solo indovinando. Per lo stesso motivo va reso generico
il docstring di [`validate_data()`](../budget_sheets.py#L341), che dice «(es. 01/09/2026)».

È [SPEC-01](01-anno-budget-centralizzato.md) ad aver introdotto `ANNO_BUDGET`, ma ha lasciato
qui la correzione apposta: là sarebbe stata una riga senza motivo, qui è il difetto che
questo spec crea.

### Coerenza con SPEC-02

Quando la data manca si usa `datetime.now()`. Ciò che garantisce che «oggi» cada dentro
`ANNO_BUDGET` è la guardia di [SPEC-02](02-guardia-cambio-anno.md). I due spec sono
indipendenti nell'ordine di applicazione, ma **insieme** chiudono il cerchio: senza SPEC-02,
dal 1° gennaio il plugin rifiuterebbe il proprio valore di default. Vale la pena prenderli
entrambi prima di un cambio d'anno.

### Aggiornamento della documentazione

[`ARCHITECTURE.md`](../ARCHITECTURE.md) §4.5, nel paragrafo sulla validazione: la regola
dell'anno, e il fatto che stia in `normalizza` e non in `validate_data`.

---

## Fuori scope

- Riconoscere nuove forme di data: è [SPEC-04](04-date-parlate.md).
- Una via di fuga per registrare in un altro anno. È stata considerata e poi esclusa su
  richiesta esplicita: vedi Decisioni.
- Cambiare `validate_data`: resta un controllo di **formato**, cieco all'anno. Se ne tocca
  solo il docstring, per l'esempio.

---

## Criteri di accettazione

- [x] `10/09/2025`, `31/12/1999`, `10/09/2027` → stato `chiedi_data`
- [x] `10/09/2026` passa
- [x] Il messaggio per una data fuori anno cita `ANNO_BUDGET` e dice «di un altro anno»
- [x] `31/02/2026` continua a produrre «Non ho capito la data»
- [x] **I due messaggi non si scambiano mai**: una data malformata non è «di un altro anno»,
      una data di un altro anno non è «non capita»
- [x] **`validate_data` invariata**: `validate_data("31/12/1999")` resta `True`
- [x] Nessun letterale d'anno resta negli esempi — ma verificato in un modo diverso da quello
      previsto: vedi D2 qui sotto. La sonda `ANNO_BUDGET=2027` da sola **non** basta più
- [x] `make test` verde: 277 → **288**. Tre test esistenti sono stati toccati, di proposito:
      vedi D1

> L'ultimo punto era verificabile in anticipo, e in effetti reggeva: tutte le date usate nei
> test fuori da `TestValidateData` erano del 2026. Ma reggeva **solo finché `ANNO_BUDGET`
> vale 2026**, che è il difetto che D1 ha chiuso.

---

## Test

Nuova classe in `tests/test_budget_sheets.py`. Quella scritta qui sotto è la forma proposta;
quella consegnata ha due prove in più e non usa letterali d'anno — vedi **D1** e **D5**:

- `test_una_data_inesistente_di_un_altro_anno_resta_non_capita` — l'ordine dei due controlli;
- `test_l_esempio_suggerito_non_e_mai_una_data_che_si_rifiuta` — il giro chiuso, provato
  spostando anno e orologio insieme.

```python
class TestAnnoUnico(unittest.TestCase):
    """Niente entra da fuori l'anno del budget, da nessuna strada."""

    def normalizza(self, data):
        campi = bs.campi_vuoti()
        campi.update({"data": data, "importo": "10"})
        return bs.normalizza(campi)

    def test_le_date_di_altri_anni_non_passano(self):
        for data in ("10/09/2025", "31/12/1999", "10/09/2027"):
            with self.subTest(data=data):
                _, stato, _ = self.normalizza(data)
                self.assertEqual(stato, "chiedi_data")

    def test_dentro_l_anno_passa(self):
        _, stato, _ = self.normalizza(f"10/09/{bs.ANNO_BUDGET}")
        self.assertNotEqual(stato, "chiedi_data")

    def test_il_messaggio_dice_la_verita(self):
        """Fuori anno e malformata sono due cose diverse e non devono
        scambiarsi il messaggio: il primo manderebbe l'utente a riscrivere la
        stessa data, il secondo lo lascerebbe senza sapere cosa correggere."""
        campi, stato, rifiutato = self.normalizza("10/09/2025")
        fuori_anno = bs.componi_messaggio(stato, campi, rifiutato)
        self.assertIn(str(bs.ANNO_BUDGET), fuori_anno)
        self.assertNotIn("Non ho capito", fuori_anno)

        campi, stato, rifiutato = self.normalizza("31/02/2026")
        rotta = bs.componi_messaggio(stato, campi, rifiutato)
        self.assertIn("Non ho capito", rotta)

    def test_validate_data_resta_un_controllo_di_formato(self):
        """La regola dell'anno sta in normalizza, non qui: se un giorno qualcuno
        la sposta dentro validate_data, questo test glielo dice."""
        self.assertTrue(bs.validate_data("31/12/1999"))
        self.assertTrue(bs.validate_data("29/02/2024"))
```

---

## Verifica

```bash
cd /Users/loprieno-andrea/Documents/budget-familiare-workflow

make test                             # 277 → 288
make eval && make eval-smemorato      # 20/20 casi, di cui uno è data-fuori-anno

# il cancello e i due messaggi, affiancati (ok / chiedi_data ×3, e mai scambiati):
python3 -c "
import budget_sheets as b
A = b.ANNO_BUDGET
for grezzo in (f'10/09/{A}', f'10/09/{A-1}', '31/12/1999', f'31/02/{A}'):
    campi = b.campi_vuoti(); campi.update({'data': grezzo, 'importo': '10'})
    campi, stato, rifiutato = b.normalizza(campi)
    esito = campi['data'] if not stato else b.componi_messaggio(stato, campi, rifiutato)[:70]
    print(f'{grezzo:14} → {stato or \"ok\":12} {esito}')
"

# end-to-end: si ferma sulla validazione, non tocca la rete.
# Lascia una bozza in chiedi_data: chiuderla con `append --annulla`.
python3 budget_sheets.py append --nuova --importo 30 --categoria Supermercato --data 10/09/2025

# l'anno spostato NON produce un esempio stantio, perché non ci si arriva: errore_anno
B=$(mktemp -d)/bozza.json
ANNO_BUDGET=2027 BUDGET_BOZZA_FILE=$B python3 budget_sheets.py \
    append --nuova --importo 30 --categoria Supermercato
```

> La sonda `ANNO_BUDGET=2027 python3 -c "print(componi_messaggio('chiedi_data', …))"` che
> questo file prevedeva **non dimostra più** quel che prometteva: vedi D2. Al suo posto c'è
> `test_l_esempio_suggerito_non_e_mai_una_data_che_si_rifiuta`, che sposta anno e orologio
> insieme.

---

## Decisioni e alternative scartate

### In fase di esecuzione: cinque scostamenti da questo file

Presi in sessione, prima di scrivere una riga. Sono qui perché tre di loro **contraddicono**
quanto scritto sopra, e chi rilegge deve trovare il perché accanto al cosa.

#### D1 — Le date nei test si blindano su `ANNO_BUDGET`

Il criterio «`make test` verde senza modificare test esistenti» era vero, ma nascondeva il
problema invece di risolverlo: la suite era verde **perché** `ANNO_BUDGET` valeva 2026, lo
stesso anno delle date scritte a mano nei test. Il giorno della migrazione di gennaio
sarebbero diventate rosse tutte insieme, in mezzo a un'operazione già delicata.

Tre punti toccati, tutti e soli quelli che passano da `normalizza()`:
`test_ordine_data_importo_categoria_sottocategoria`, `test_scrittura_dopo_conferma` e
`test_normalizza_le_risolve`. Più i sei letterali in `casi_eval.json`, sostituiti dai
segnaposto `{ANNO}` e `{ALTRO_ANNO}` che `carica_casi()` risolve al caricamento — un punto
solo per tutte e tre le eval.

Il caso più insidioso era `test_normalizza_le_risolve`: fa passare «ieri» per `normalizza()`
con l'orologio **vero**, e `normalizza()` non accetta un `oggi` iniettabile. Il 1° gennaio
«ieri» cade nell'anno prima e il test diventa rosso **da solo**, un giorno all'anno, senza
che nessuno abbia toccato niente. Ora l'orologio è fermo, con un helper che usa
`mock.patch.object(..., wraps=datetime)`: senza `wraps` `strptime` finirebbe su un Mock e
`validate_data` direbbe di sì a qualunque cosa.

**Non** sono state toccate due cose, e sono le più istruttive:

- `TestDataRelativa.OGGI = datetime(2026, 9, 17)`: quei test iniettano `oggi` e non passano
  mai da `normalizza()`. Parametrizzarli su `ANNO_BUDGET` li **romperebbe**, perché il 17
  settembre 2026 è giovedì e il 17 settembre 2027 è venerdì, e le asserzioni su «lunedì
  scorso» dipendono dal giorno della settimana.
- `TestGuardiaAnno`: il turno si ferma su `errore_anno` prima di `normalizza()`, quindi la
  data nella bozza non viene mai validata.

#### D2 — La data d'esempio è **oggi**, non `01/09/{ANNO_BUDGET}`

Questo file proponeva `01/09/{ANNO_BUDGET}`. Risolve il giro chiuso, ma `01/09` resta un
giorno arbitrario: a gennaio 2027 il plugin suggerirebbe `01/09/2027`, cioè una data futura.
`datetime.now()` è sempre valida, mai futura, e coincide col default quando la data manca.

Ha una conseguenza da conoscere: **l'esempio segue l'orologio, non la costante.** Quindi la
sonda `ANNO_BUDGET=2027 python3 -c "…"` prevista nella Verifica non dimostra più quello che
prometteva — con la costante spostata e l'orologio fermo al 2026 suggerisce ancora una data
del 2026. Non è un difetto: è uno stato **irraggiungibile in produzione**, perché
`anno_disallineato()` ferma il turno con `errore_anno` prima che quel messaggio si componga
(verificato: `ANNO_BUDGET=2027 python3 budget_sheets.py append --nuova --importo 30 …` →
`errore_anno`). La garanzia sta quindi altrove: in
`test_l_esempio_suggerito_non_e_mai_una_data_che_si_rifiuta`, che sposta **insieme** anno e
orologio — lo stato del giorno dopo la migrazione — e verifica che la data suggerita sia una
che il cancello accetta.

Effetto di lato: questo spec ora **dipende** da [SPEC-02](02-guardia-cambio-anno.md) per la
correttezza dell'esempio. Sopra si diceva che i due sono indipendenti nell'ordine di
applicazione: resta vero, ma non sono più indipendenti nel risultato.

#### D3 — Fra virgolette va la data **risolta**

Quando l'input era relativo o parlato, `rifiutato` contiene la data dopo
`normalizza_data_relativa()`, non il testo dell'utente: chi scrive «ieri» il 1° gennaio legge
«e «31/12/2026» è di un altro anno». Sembra infedele, ma è l'unica versione che **spiega**:
senza vedere la data risolta, chi ha scritto «ieri» non capisce cosa c'entri l'anno.
Riportare il grezzo richiederebbe di farlo viaggiare accanto al risolto per tutta
`normalizza()`, per dire di meno.

#### D4 — La documentazione tocca §4.5, §6 e §13.4

Qui sopra era previsto solo §4.5. Ma il cancello rende **incompleti** altri due punti: §6
descrive l'ordine di validazione di `normalizza()` e la tabella degli stati diceva che
`chiedi_data` significa «data assente o non valida»; §13.4 è il playbook di chi fa la
migrazione di gennaio, e ora ha un fatto nuovo da dire — le spese di fine dicembre vanno
registrate **prima** di spostare la costante. Nessuna invariante nuova in §10: c'è già la
I12 sull'anno, e «niente arriva sul foglio» lo copre il test CLI.

#### D5 — Un test CLI e un caso eval oltre a `TestAnnoUnico`

Le quattro prove previste qui coprono `normalizza()` e `componi_messaggio()`, ma nessuna dice
che dal rifiuto si **esca**. È il punto che rende questo spec accettabile — è l'unico che
toglie qualcosa a un utente, e un rifiuto senza via d'uscita sarebbe un dialogo in cui si
resta incastrati. Quindi:

- `TestCli.test_una_data_fuori_anno_non_arriva_al_foglio_e_si_corregge`: due giri, e prova
  entrambe le cose — `append_row` mai chiamata, e la correzione che porta a `chiedi_conferma`
  con importo e categoria sopravvissuti;
- caso `data-fuori-anno` in `casi_eval.json`, che rigioca la conversazione intera. È anche
  l'unico posto dove la trascrizione del rifiuto si **legge**, e leggerla è il modo per
  accorgersi se un giorno smettesse di dire la verità.

### Nessuna via di fuga

In una fase intermedia il design prevedeva che `gg/mm/aaaa` restasse la strada esplicita per
registrare fuori anno. È stato escluso su indicazione esplicita: *«l'inserimento al di fuori
dell'anno in corso così come configurato non deve essere possibile, mai»*.

La conseguenza è che questo è **l'unico spec dei sette che toglie qualcosa a un utente**. È
la ragione per cui è isolato: se a valle risultasse troppo rigido, si annulla da solo senza
toccare gli altri sei.

### Il vincolo in `normalizza()`, non in `validate_data()`

Metterlo dentro `validate_data` sarebbe l'istinto — è «la funzione delle date» — e produrrebbe
un messaggio **falso**. L'utente che scrive `10/09/2025` leggerebbe «Non ho capito la data
«10/09/2025». Scrivila come gg/mm/aaaa»: ma è già scritta come gg/mm/aaaa. Il consiglio è
inapplicabile e l'utente riscriverebbe la stessa cosa.

Effetto collaterale gradito della separazione: `validate_data` non cambia, quindi i suoi
quattro test non cambiano, e l'accettazione «`make test` verde senza modificare test
esistenti» resta verificabile.

### Un ramo in `componi_messaggio`, non un nuovo stato

`chiedi_data_fuori_anno` avrebbe richiesto una voce in `risolvi_risposta`, una in `EXIT` e un
ramo in più ovunque si controlli lo stato — per una differenza che è **solo di parole**. La
domanda posta è la stessa («di che giorno?») e la risposta va nello stesso campo. Tutto il
testo mostrato all'utente vive già in `componi_messaggio`: è lì che va la distinzione.

### `data.endswith(f"/{ANNO_BUDGET}")` e non un parsing

La stringa arriva qui già validata da `validate_data`, quindi è `gg/mm/aaaa` e il suffisso è
l'anno. Un `datetime.strptime` per rileggere quello che è appena stato verificato aggiunge un
modo di fallire senza aggiungere sicurezza.
