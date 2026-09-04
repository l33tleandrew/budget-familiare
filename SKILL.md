---
name: budget-familiare-workflow
description: >
  Registra spese ed entrate nel Google Sheet "Budget Familiare" (foglio
  "Transazioni 2026"). DUE casi di attivazione, entrambi obbligatori.
  (1) Il messaggio contiene un importo che sembra una spesa o un'entrata, anche
  in forma telegrafica ("12€ benzina", "15 al bar", "12 euro", "stipendio
  2000"), anche come nota vocale o foto di scontrino.
  (2) Il messaggio è brevissimo e da solo non significa niente — un numero nudo
  ("1", "2", "16"), un "sì", un "no", una parola sola ("cultura", "benzina",
  "supermercato"), un "procedi", "salva", "ok". Messaggi così NON sono
  conversazione: sono la risposta a un elenco numerato o a un sì/no che hai
  mostrato tu in un messaggio precedente, e vanno gestiti QUI. Attiva la skill
  prima di rispondere: la transazione in corso sta nel file di stato su disco e
  nel blocco ⟦ST ...⟧ del tuo ultimo messaggio. Non chiedere mai "hai bisogno di
  qualcosa?" o "intendevi altro?" a un numero nudo: quel numero è una scelta e
  la risposta sta in questa skill.
  Non attivarla solo se il messaggio non ha importi, non è una risposta breve, e
  non c'è nessuna transazione aperta.
tags: [budget, google-sheets, finance, italian]
---

# Budget Familiare — registrazione transazioni

## 0. Le cinque regole che non si negoziano

1. **Solo `terminal`, mai `execute_code`.** Tutto il workflow sono tre comandi di
   shell già pronti (§2). Avvolgerli in `subprocess` non aggiunge niente e fa
   scattare l'approvazione manuale, che blocca la conversazione mentre l'utente è
   in fila alla cassa. Se ti viene voglia di scrivere codice, stai sbagliando
   strada: i comandi sono in §2, copiali e lanciali.
2. **Ogni turno comincia con il blocco di apertura** (§2.1), prima ancora di
   decidere che tipo di messaggio è arrivato.
3. **Ogni nome di categoria e sottocategoria viene dall'output di
   `read-categories` di questo turno.** In questa pagina non è scritto nessun
   nome reale: dove vedi `⟨…⟩` è un segnaposto (§5).
4. **Una sola domanda per messaggio, e chiusa**: o un sì/no, o un elenco
   numerato scritto per intero. Unica domanda aperta ammessa: chiedere un
   importo.
5. **Un turno = un messaggio**, che finisce sempre con il blocco `⟦ST⟧`.

---

## 1. Contesto tecnico

- **Spreadsheet**: `1iDYzjzyu_du_axBmzOzI6k4DrzV2Y52_UZTFMtM6JB0`
- **Foglio target**: `Transazioni 2026` (sheet ID `1689336980`)
- **Colonne, in quest'ordine**: `Data | Tipo | Categoria | Sottocategoria | Importo (€) | Descrizione | Note`
- **Foglio sorgente delle categorie**: `Categorie` (colonna A = categoria,
  valorizzata solo sulla prima riga del gruppo; colonna B = sottocategoria, `—`
  se il gruppo non ne ha). Non leggerlo a mano: ci pensa `read-categories`.
- **Credenziali**: `/opt/data/profiles/budgetingagent/google_token.json` +
  `google_client_secret.json` nella stessa cartella
- **Operazione**: solo `append`. Non modificare mai righe esistenti.
- **Importo**: sempre positivo. È la colonna `Tipo` a distinguere entrate e uscite.

> Il nome del foglio contiene l'anno. Se registri una transazione datata in un
> anno diverso dal 2026, avvisa l'utente che serve un foglio nuovo invece di
> scriverla nel posto sbagliato.

**Questa skill sa solo scrivere.** Lo script espone `read-categories` e
`append`, niente altro: non puoi leggere le transazioni già registrate. A
domande come "quanto ho speso a settembre?" non rispondere con numeri — non li
hai, e stimarli è peggio di non rispondere. Dillo e passa la palla al foglio:

> Non riesco a leggere le transazioni, posso solo registrarle. I totali li trovi
> qui: https://docs.google.com/spreadsheets/d/1iDYzjzyu_du_axBmzOzI6k4DrzV2Y52_UZTFMtM6JB0/edit

---

## 2. Comandi

`<chiave>` = **solo le cifre del numero del mittente** (`+39 348 104 4965` →
`393481044965`). Al bot scrivono più persone della stessa famiglia: un file di
stato unico farebbe sì che il "2" di uno completi la transazione dell'altro. Se
dal contesto non ricavi il numero, usa `sconosciuto` e cita sempre l'importo
quando riprendi, così uno scambio di persona si vede subito.

### 2.1 Blocco di apertura — primo comando di ogni turno, senza eccezioni

Una sola chiamata a `terminal` che ti dà tutto il contesto: data di oggi, stato
in sospeso, categorie aggiornate.

```bash
D=/opt/data/profiles/budgetingagent/state
mkdir -p $D
find $D -name 'pending_*.json' -mmin +120 -delete 2>/dev/null
echo "--- OGGI ---";      date +%d/%m/%Y
echo "--- STATO ---";     find $D -name 'pending_<chiave>.json' -mmin -120 -exec cat {} \; 2>/dev/null
echo "--- CATEGORIE ---"; /opt/hermes/.venv/bin/python /opt/data/profiles/budgetingagent/scripts/budget_sheets.py read-categories
```

Cosa ti dice:

- **OGGI** — la data la chiedi al sistema, mai alla memoria: un modello che tira
  a indovinare sbaglia mese.
- **STATO** — vuoto significa *niente in sospeso*, ed è la situazione normale del
  primo messaggio: non è un errore da segnalare. Se c'è un JSON, quello è il tuo
  contesto: riprendi da `passo` senza far ripetere niente all'utente. La scadenza
  la applica `-mmin +120`: una transazione lasciata a metà stamattina non si
  riapre nel pomeriggio su un messaggio che non c'entra niente.
- **CATEGORIE** — JSON `{"Categoria": ["sotto1", "sotto2"], …}`; array vuoto =
  quella categoria non ha sottocategorie. È l'unica fonte lecita di nomi (§5).

Lo esegui **sempre**, anche quando il messaggio ti sembra chiarissimo: leggere
costa un attimo, e senza queste tre informazioni ogni decisione successiva è a
occhio.

### 2.2 Scrivere lo stato — fine di ogni turno intermedio

L'heredoc è quotato (`<<'JSON'`), quindi la shell non interpreta niente.
Riscrivi il file **intero** ogni volta: è piccolo, e aggiornarlo a pezzi è il
modo più facile per ritrovarsi con un JSON rotto.

```bash
cat > /opt/data/profiles/budgetingagent/state/pending_<chiave>.json <<'JSON'
{"sender":"+39 348 104 4965","imp":"12.00","data":"03/09/2026","tipo":"U",
 "cat":"?","sub":"?","desc":"-","note":"-","passo":"cat",
 "opzioni":["⟨1ª voce come l'hai numerata⟩","⟨2ª⟩","⟨3ª⟩"],"coda":[]}
JSON
```

### 2.3 Cancellare lo stato — subito dopo un `append` riuscito

```bash
rm -f /opt/data/profiles/budgetingagent/state/pending_<chiave>.json
```

Se l'`append` **non** è andato a buon fine il file **resta**, così l'utente può
riprovare senza rifare tutto da capo.

### 2.4 Append

```bash
/opt/hermes/.venv/bin/python /opt/data/profiles/budgetingagent/scripts/budget_sheets.py append \
  --data "03/09/2026" \
  --tipo "Uscita" \
  --categoria "⟨categoria verbatim dall'output⟩" \
  --sottocategoria "⟨sottocategoria verbatim dall'output, o ""⟩" \
  --importo 15.00 \
  --descrizione "birra con Luca" \
  --note ""
```

- **Successo**: `OK:Transazioni 2026!A42:G42`. Riporta il numero di riga
  all'utente.
- **Quoting**: campi liberi fra virgolette doppie. Da descrizione e note togli
  prima i caratteri `"`, `` ` ``, `$` e `\`, che romperebbero il comando (gli
  apostrofi vanno benissimo, l'italiano è pieno). Sottocategoria assente = `""`.
- **Se l'output non inizia con `OK:`**: non dire che hai registrato. Riporta
  l'errore e fermati. Non ritentare in automatico: se il primo tentativo era
  andato a buon fine ma la risposta si è persa, un secondo append crea una riga
  doppia che nessuno si accorgerà di avere. Meglio: "Non sono riuscito a
  registrarla, controlla il foglio e riprova".

---

## 3. Lo stato vive su disco, non nella chat

Su WhatsApp non hai accesso ai turni precedenti, e il vincolo è più stretto di
quanto sembri: **nemmeno il tuo ultimo messaggio ti arriva**, tranne quando
l'utente risponde **citandolo**. Senza citazione, un "2" ti arriva nudo. Per
questo lo stato sta in un file su disco, uno per mittente.

### Il file

```json
{
  "sender": "+39 348 104 4965",
  "imp": "12.00", "data": "03/09/2026", "tipo": "U",
  "cat": "?", "sub": "?", "desc": "-", "note": "-",
  "passo": "cat",
  "opzioni": ["⟨…⟩", "⟨…⟩"],
  "coda": []
}
```

`opzioni` è l'elenco **esattamente come l'hai numerato** nel messaggio: è quello
che rende la risoluzione di "2" indipendente da tutto il resto. Il campo `passo`
dice a cosa si riferisce il numero — senza, un "3" è illeggibile.

Ciclo di vita: **scritto o aggiornato a ogni turno intermedio**, **cancellato
subito dopo l'`append`**. Il file cancellato *è* la protezione anti-duplicato: un
"ok" o un "grazie" del turno dopo non trova niente e non riapre niente. Se per
qualche motivo il file c'è ancora e ha `passo=fatto`, trattalo come inesistente e
cancellalo.

### Il blocco ⟦ST⟧, rete di sicurezza

Chiudi **ogni** messaggio con lo stato anche in chiaro, intermedi e finale:

```
⟦ST imp=15.00|data=03/09/2026|tipo=U|cat=?|sub=?|desc=cinema|note=-|passo=cat⟧
```

Costa una riga e serve in due casi: quando la scrittura del file fallisce, e
quando l'utente cita un messaggio vecchio per riprendere *quella* transazione.

**Precedenza, quando ci sono entrambi**: vince il `⟦ST⟧` del messaggio citato,
perché citando l'utente sta indicando quale transazione intende. Dopo aver agito,
riscrivi il file con lo stato aggiornato.

| Campo   | Valori |
|---------|--------|
| `imp`   | importo con **punto** decimale, formato script (`15.00`) |
| `data`  | `DD/MM/YYYY` |
| `tipo`  | `U` (uscita) o `E` (entrata) |
| `cat`   | nome esatto dall'output di `read-categories`, oppure `?` se da scegliere |
| `sub`   | nome esatto, `-` se la categoria non ne ha, `?` se da scegliere |
| `desc`  | testo breve, o `-` |
| `note`  | testo breve, o `-` |
| `passo` | `conferma` \| `cat` \| `sub` \| `tipo` \| `fatto` |
| `coda`  | altre transazioni dello stesso messaggio ancora da registrare, come `importo~descrizione` separate da `;` — es. `coda=40.00~benzina;9.50~parcheggio`. `-` se non ce n'è |
| `riga`  | (solo con `passo=fatto`) il range restituito dall'append, es. `A42:G42` |

### Turno cieco

Se non trovi **né file né blocco** e il messaggio è una risposta parziale (una
parola sola, un numero secco), non c'è niente da recuperare: non inventare i dati
e non far finta di ricordare. Chiedi il minimo per ripartire.

> Non ho nessuna spesa in sospeso. Ripeti importo e categoria? (es. "15€ cultura")

---

## 4. Il flusso

Il workflow parte **se e solo se** rilevi un importo, oppure il blocco di
apertura ha trovato una transazione in sospeso. Un messaggio senza importo e
senza stato aperto ("com'è andata la spesa?") non è una registrazione: rispondi
normalmente.

Nota l'ordine: **prima leggi, poi decidi**. Un "2" senza stato è un messaggio
qualsiasi; lo stesso "2" con uno stato in sospeso è una scelta da elenco. Non
puoi distinguerli guardando il messaggio.

L'obiettivo è **arrivare al foglio nel minor numero di turni possibile**: ogni
turno in più è un'occasione per perdere il contesto.

### Fase A — capisci

Estrai dall'input tutto quello che puoi (§6). Obbligatori per procedere:
**importo** e **categoria**. Tutto il resto ha un default:

- **Data** = oggi (dal blocco di apertura). Non chiederla mai.
- **Tipo** = Uscita, salvo indizi contrari. Non chiederlo mai, tranne nei casi
  genuinamente ambigui ("rimborso", "bonifico").
- **Descrizione** = il testo utile che l'utente ha già scritto ("Esselunga",
  "cena con Luca"). Non chiederla mai, ma non lasciarla vuota se hai qualcosa da
  metterci: è ciò che rende leggibile il foglio fra sei mesi. Non ripetere però
  quello che è già in categoria o sottocategoria — "benzina" sotto una categoria
  che si chiama già così è rumore, meglio `-`.
- **Note** = vuoto, salvo indicazioni esplicite tipo "da rimborsare", "pagato da
  Marco".

### Fase B — completa (massimo una domanda per turno)

Il ramo dipende da **chi ha deciso la categoria**, non da quanti campi mancano:
una categoria che hai dedotto tu va sempre confermata, una che ha scelto
l'utente no.

**B1 — la categoria l'hai dedotta tu.** Riepilogo + sì/no. Vale **anche quando
non manca nient'altro**, sottocategoria compresa o assente: la conferma non serve
a completare la riga, serve a farti smentire.

> 💰 *15,00 €* — 03/09/2026 (Uscita)
> _⟨categoria⟩_ › _⟨sottocategoria⟩_ — "birra con Luca"
> Confermi? *sì* / *no*
>
> ⟦ST imp=15.00|data=03/09/2026|tipo=U|cat=⟨categoria⟩|sub=⟨sottocategoria⟩|desc=birra con Luca|note=-|passo=conferma⟧

Una categoria senza sottocategorie passa comunque da qui, con `sub=-`. Se arriva
**no**, non chiedere "e allora quale?": passa a B2 e mostra l'elenco.

**B2 — la categoria non è deducibile** (o l'utente ha appena detto "no").
Elenca **tutte** le categorie dell'output, numerate, nell'ordine dell'output:

> 💰 *15,00 €* — 03/09/2026 (Uscita)
> In che categoria?
> 1. ⟨1ª categoria dell'output⟩
> 2. ⟨2ª⟩
> … *(tutte, una per riga)*
> N. ⟨ultima⟩
> Rispondi con il numero.
>
> ⟦ST imp=15.00|data=03/09/2026|tipo=U|cat=?|sub=?|desc=-|note=-|passo=cat⟧

`N` è quante ne restituisce il comando, non un numero che sai a memoria. Sono
tante righe per WhatsApp, ma un elenco tagliato costringe l'utente a indovinare
cosa c'è dopo il "…", e a quel punto la domanda non è più chiusa. Scrivile tutte.

**B3 — la categoria l'ha scelta l'utente** (in B2, correggendo un B1, o
scrivendola nel messaggio iniziale). Qui la categoria non si conferma più:

- se nell'output ha sottocategorie, elencale **tutte**, numerate, nell'ordine
  dell'output, marcando la tua preferita (`passo=sub`);
- se l'output dice `[]`, **non chiedere niente**: `sub=-`, vai in Fase C.

> 15,00 € — 03/09/2026 (Uscita) → *⟨categoria scelta⟩*
> Quale sottocategoria?
> 1. ⟨1ª sottocategoria di quella categoria⟩
> 2. ⟨2ª⟩ ← probabile
> … *(tutte)*
> N. ⟨ultima⟩
> Rispondi con il numero.
>
> ⟦ST imp=15.00|data=03/09/2026|tipo=U|cat=⟨categoria scelta⟩|sub=?|desc=-|note=-|passo=sub⟧

Anche una categoria scritta esplicitamente al primo messaggio ("15€ cultura") è
B3: nessuna conferma.

### Come numerare e come leggere le risposte

L'elenco numerato è un contratto fra due messaggi:

1. **Numera nell'ordine dell'output**, dall'alto. Mai in ordine alfabetico, mai
   "le più usate prima": se l'ordine cambia fra un turno e l'altro, il "3"
   dell'utente finisce su un'altra categoria e il dato è sbagliato in silenzio.
2. **Risolvi il numero contro `opzioni`**, cioè l'elenco che hai realmente
   scritto, non contro l'output appena riletto. Se nel frattempo il foglio è
   cambiato e la voce scelta non compare più nell'output di questo turno,
   rimostra l'elenco aggiornato invece di scrivere un nome che non esiste più.
3. **Non troncare mai.** Elenco completo più ordine stabile significa che il
   numero di una categoria resta lo stesso: chi usa il bot tutti i giorni impara
   a rispondere senza nemmeno leggere. Un elenco accorciato "per brevità"
   distrugge questa proprietà.

Per le risposte a parole interpreta con larghezza — numero, nome, nome parziale,
maiuscole e accenti diversi ("auto", "auto moto" → la voce dell'output che
corrisponde) — e vale anche per le sottocategorie, dove l'utente usa la parola
sua e non quella del foglio ("luce" → la voce delle bollette elettriche,
"palestra" → la voce della palestra). Se nessuna corrispondenza è chiara, non
tirare a indovinare: rimostra l'elenco e chiedi il numero. Quello che finisce nel
foglio è comunque **la stringa verbatim dell'output**, non quella dell'utente.

### Fase C — registra e chiudi

Quando importo e categoria ci sono, fai l'`append` **senza chiedere un'ulteriore
conferma**: l'utente ha già confermato o scelto tutto, e un secondo "confermi?" è
solo un altro turno da perdere.

In particolare, dopo che l'utente ha scelto la sottocategoria **non esiste nessun
passaggio intermedio**. Niente riepilogo-più-domanda, e soprattutto mai "vuoi
aggiungere una descrizione o delle note, o procedo?": è una domanda aperta su due
campi che hanno un default, quindi vietata due volte. Lo stato `passo=conferma`
esiste **solo** per il caso B1.

Unica eccezione, e vale anche arrivandoci da B3: **sopra i 1000 €** l'importo va
confermato almeno una volta (§6). Se non è ancora successo, chiedi prima di
scrivere.

Ultimo controllo prima del comando: `cat` e `sub` compaiono *verbatim*
nell'output letto in questo turno? Se `sub` non è nella lista di quella
categoria, fermati e rifai la domanda.

Poi chiudi con il riepilogo *a posteriori*, la riga scritta e il link:

> ✅ Registrata (riga 42)
> *Data*: 03/09/2026
> *Tipo*: Uscita
> *Categoria*: ⟨categoria⟩ › ⟨sottocategoria⟩
> *Importo*: 15,00 €
> *Descrizione*: birra con Luca
> https://docs.google.com/spreadsheets/d/1iDYzjzyu_du_axBmzOzI6k4DrzV2Y52_UZTFMtM6JB0/edit
>
> ⟦ST imp=15.00|data=03/09/2026|tipo=U|cat=⟨categoria⟩|sub=⟨sottocategoria⟩|desc=birra con Luca|note=-|passo=fatto|riga=A42:G42⟧

Il numero di riga costa nulla e permette all'utente di correggere a mano un
errore in tre secondi: è il vero motivo per cui puoi permetterti di saltare la
conferma finale.

Poi, **visto `OK:`, cancella il file di stato** (§2.3). Se in `coda` c'era
un'altra transazione, riparti subito da lì con la Fase B, ereditando data e tipo.

---

## 5. Categorie: la regola invalicabile

**Ogni nome di categoria o sottocategoria che scrivi — in un elenco, in un
riepilogo, nel comando `append` — viene dall'output di `read-categories` di
QUESTO turno.** Non da questa pagina, non dal turno precedente, non da quello che
sembra sensato.

In questa skill non è scritto nessun nome reale, di proposito: `⟨…⟩` è un
segnaposto tipografico, e nel messaggio vero ci vanno i nomi veri senza
parentesi. **Se ti viene in mente un elenco di categorie o sottocategorie senza
avere l'output davanti, te lo stai inventando.**

È l'errore più costoso possibile perché è invisibile: le sottocategorie
plausibili sono facilissime da inventare, l'utente sceglie il numero senza
sospettare niente, e nel foglio finisce un valore che non esiste nella tabella
delle categorie. Da quel momento i totali per sottocategoria sono sbagliati e
nessuno sa perché.

In pratica:

- **Quante categorie ci sono, come si chiamano e in che ordine stanno** lo dice
  l'output, ogni volta. Non è un elenco fisso.
- **Quali categorie hanno sottocategorie** lo dice l'output. `[]` significa
  nessuna: non chiedi niente, `sub=-`, Fase C.
- **Gli indizi qui sotto servono solo a scegliere una voce dell'output**, mai a
  crearne una. Se nell'output non c'è una voce che copre quell'area, l'indizio
  non vale: vai a B2 con l'elenco completo.

### Indizi per l'inferenza

| Nell'input compare… | Cerca nell'output la voce che copre… |
|---|---|
| benzina, gasolio, casello, autostrada, parcheggio, bollo, revisione, gommista | auto / veicoli |
| spesa, supermercato, Esselunga, Coop, Lidl, Conad | supermercato |
| bar, caffè, colazione, pizza, ristorante, cena, sushi, kebab, birra, aperitivo | cibo e bevute fuori |
| bolletta, luce, gas, internet, condominio, mutuo, TARI, idraulico | casa |
| palestra, piscina, padel, campo | sport |
| Netflix, Spotify, Prime, Disney, abbonamento mensile | abbonamenti |
| farmacia, medicine, visita, analisi, dentista | salute |
| parrucchiere, barbiere, estetista | cura della persona |
| metro, bus, biglietto, abbonamento urbano | trasporto pubblico |
| cinema, libro, mostra, museo, teatro, concerto | cultura |
| volo, hotel, B&B, Airbnb | viaggi |
| regalo, compleanno | regali |
| stipendio, busta paga | stipendio → e `tipo=E` |

Se l'indizio identifica anche la sottocategoria (e quella sottocategoria esiste
davvero nell'output), proponi entrambe e vai a B1: è il percorso a un solo turno.

---

## 6. Regole di estrazione

### Importo
- La virgola è sempre il decimale: `12,50` → `12.50`; `1.234,56` → `1234.56`;
  `12` → `12.00`.
- Il punto dipende da quante cifre lo seguono: **3 cifre = migliaia**
  (`1.500` → `1500.00`), **1 o 2 cifre = decimale** (`12.5` e `12.50` → `12.50`).
  Non trattare il punto come migliaia a prescindere: `12.50` letto come 1250
  sbaglia di cento volte e finisce a foglio senza che nessuno se ne accorga.
- `2k`, `2mila` → `2000.00`. Ignora simboli e parole: `€`, `eur`, `euro`.
- Sopra i **1000 €** chiedi sempre conferma dell'importo prima di registrare,
  come sì/no ("Confermo 1.500,00 €? *sì* / *no*"), qualunque sia il resto del
  flusso. È l'unico caso in cui vale la pena spendere un turno in più.
- Nel blocco `⟦ST⟧` e nel comando usa **sempre** il punto decimale; nei messaggi
  all'utente la virgola.

### Data
- Default = **oggi**, quello letto nel blocco di apertura.
- Risolvi i riferimenti relativi: "ieri", "l'altro ieri", "sabato scorso",
  "il 28" (mese corrente), "28/8" (anno corrente).
- Normalizza le date parziali: `2/9/26` → `02/09/2026`.
- Se una data futura sembra un refuso, chiedi conferma invece di registrarla.

### Tipo
- `Entrata` se compare stipendio, bonifico ricevuto, cashback, dividendi,
  interessi, plusvalenza, vendita, o se la categoria è quella dello stipendio.
- `Uscita` in tutti gli altri casi.
- Chiedi solo se resta davvero ambiguo (un "rimborso" può andare in entrambe le
  direzioni), e chiedilo come scelta fra due:
  > Questi 50,00 € sono: *1.* Entrata  *2.* Uscita?

### Nota vocale
Trascrivi ed estrai. **Non serve un turno dedicato a confermare la
trascrizione**: metti quello che hai capito dentro il messaggio della Fase B,
così la conferma della categoria vale anche come conferma della trascrizione. Se
non trovi un importo, dillo e chiedilo, senza avviare il workflow.

### Foto / scontrino
Prendi il **totale** pagato, non il subtotale, non il contante consegnato, non il
resto. Se leggi l'insegna, usala come descrizione; se leggi la data dello
scontrino, usa quella al posto di oggi. Se il totale è illeggibile o ce ne sono
due plausibili, non indovinare: proponi le alternative come scelta numerata
(`1. 43,20 €  2. 39,80 €`), oppure il valore letto come sì/no. Un importo
sbagliato è peggio di una domanda in più.

### Più transazioni in un messaggio
"12 al bar e 40 di benzina" sono due righe. Gestiscile **una alla volta**,
nell'ordine in cui l'utente le ha dette, tenendo le altre in `coda=`. Dichiaralo
nel messaggio, altrimenti l'utente non sa che ne stai tenendo una da parte:

> 💰 *12,00 €* — 03/09/2026 (Uscita) — _⟨categoria⟩_ › _⟨sottocategoria⟩_
> Confermi? (poi passiamo ai 40,00 € di benzina)
> ⟦ST imp=12.00|…|passo=conferma|coda=40.00~benzina⟧

Le altre transazioni sopravvivono **solo** dentro `coda=` (e nel file): se non le
scrivi lì, al turno dopo non esistono più.

---

## 7. Casi particolari

### Un nuovo importo mentre una transazione è in attesa

Capita spesso: hai chiesto la categoria e l'utente, invece di rispondere, manda
"30€ al bar". Distingui in modo meccanico:

- **numero nudo** entro la lunghezza dell'elenco mostrato (`3`, `12`) → è la
  scelta dall'elenco;
- **numero con simbolo, unità o contesto di spesa** (`30€`, `30 euro`,
  `30 al bar`) → è una **transazione nuova**;
- **numero nudo fuori range** → non indovinare e non passare al campo libero:
  rimanda l'elenco completo, identico a prima, e richiedi il numero.

La transazione nuova **sostituisce** quella in attesa, che va persa. Non metterla
in coda e non provare a portarne avanti due: dillo in chiaro nello stesso
messaggio, così l'utente può rimandarla se gli serviva davvero.

> Ok, la spesa da 15,00 € di prima l'ho scartata (mancava la categoria).
> 💰 *30,00 €* — 03/09/2026 (Uscita) — _⟨categoria⟩_ › _⟨sottocategoria⟩_
> Confermi?
> ⟦ST imp=30.00|…|passo=conferma⟧

Vale solo per le transazioni **non ancora registrate**: se lo stato precedente ha
`passo=fatto`, non c'è niente da scartare, quella è a foglio e ci resta.

### Correzioni al volo

In qualsiasi momento l'utente può correggere un campo invece di rispondere alla
domanda: "no, era ieri", "metti 15 non 12", "in realtà è un'entrata", "modifica
data al 2/9/26 e procedi". Non è un fuori-programma, è il modo naturale di
parlare.

Aggiorna **solo** il campo nominato, tieni tutto il resto dallo stato, e riprendi
dallo stesso punto in cui eri — senza ricominciare e senza rifare domande già
risposte. Se il messaggio contiene anche un via libera ("procedi", "salva"),
applica la correzione e registra nello stesso turno.

---

## 8. Formattazione dei messaggi

WhatsApp non usa il Markdown standard: `*grassetto*` con un asterisco solo,
`_corsivo_`, `~barrato~`. Scrivere `**Data**` fa comparire gli asterischi. Niente
titoli `#`, niente tabelle.

Tieni i messaggi corti: una riga di riepilogo, la domanda, il blocco di stato.
Si leggono su un telefono, spesso in fila alla cassa.

**Un turno, un messaggio.** Niente narrazione dei passaggi interni in messaggi
separati ("Ho ricevuto 12 euro senza contesto", "Ora prendo la data di oggi",
"Categoria selezionata, procedo"): su WhatsApp ognuno di quelli è una notifica
sul telefono di chi legge. Fai le tue letture in silenzio e manda un messaggio
solo, quello che serve all'utente.

**Gli elenchi di scelta sono l'eccezione**: vanno scritti per intero, anche se
occupano quindici righe. Meglio un messaggio lungo che una domanda a cui l'utente
non sa come rispondere.

Nei riepiloghi usa `*grassetto*` per gli importi come negli esempi, non il
corsivo. Un'emoji per messaggio è simpatica, una per riga è rumore.

---

## 9. Esempi

Nei tre esempi i nomi fra `⟨…⟩` sono segnaposto: nel messaggio vero ci vanno i
nomi letti da `read-categories`, tutti e senza parentesi.

**Esempio 1 — percorso a un turno (B1)**

> **Utente**: 12,50 benzina
>
> **Tu**: 💰 *12,50 €* — 03/09/2026 (Uscita)
> _⟨categoria auto⟩_ › _⟨sottocategoria benzina⟩_
> Confermi? *sì* / *no*
> ⟦ST imp=12.50|data=03/09/2026|tipo=U|cat=⟨…⟩|sub=⟨…⟩|desc=-|note=-|passo=conferma⟧
>
> **Utente**: sì
>
> **Tu**: ✅ Registrata (riga 43) … + link
> ⟦ST …|passo=fatto|riga=A43:G43⟧

**Esempio 2 — categoria non deducibile, poi sottocategoria (B2 → B3)**

> **Utente**: 15€
>
> **Tu**: 💰 *15,00 €* — 03/09/2026 (Uscita)
> In che categoria?
> 1. ⟨1ª dell'output⟩
> 2. ⟨2ª⟩
> *(…tutte quelle dell'output, una per riga, nel suo ordine…)*
> N. ⟨ultima⟩
> Rispondi con il numero.
> ⟦ST imp=15.00|data=03/09/2026|tipo=U|cat=?|sub=?|desc=-|note=-|passo=cat⟧
>
> **Utente**: 3
>
> **Tu**: 15,00 € — 03/09/2026 (Uscita) → *⟨3ª voce di `opzioni`⟩*
> Quale sottocategoria?
> 1. ⟨1ª sottocategoria di quella categoria⟩
> *(…tutte…)*
> N. ⟨ultima⟩
> Rispondi con il numero.
> ⟦ST imp=15.00|…|cat=⟨3ª voce⟩|sub=?|passo=sub⟧
>
> **Utente**: 5
>
> **Tu**: ✅ Registrata (riga 44) … + link
> ⟦ST …|sub=⟨5ª sottocategoria⟩|passo=fatto|riga=A44:G44⟧

**Esempio 3 — categoria scelta dall'utente, output `[]`: zero domande**

> **Utente**: 15€ cultura
>
> **Tu**: *(la categoria l'ha scritta l'utente e l'output dice `[]` per quella
> categoria → registri subito, senza conferme)*
> ✅ Registrata (riga 45) … + link
> ⟦ST …|cat=⟨voce corrispondente a "cultura"⟩|sub=-|passo=fatto|riga=A45:G45⟧

**Esempio 4 — turno cieco**

> **Utente**: 3
>
> *(blocco di apertura: STATO vuoto, e nessun `⟦ST⟧` citato)*
>
> **Tu**: Non ho nessuna spesa in sospeso. Ripeti importo e categoria?
> (es. "15€ cultura")

---

## 10. Prima di premere invio

1. Ho lanciato il **blocco di apertura** all'inizio del turno?
2. Ogni nome di categoria/sottocategoria che ho scritto compare **verbatim**
   nell'output di questo turno? (elenchi, riepilogo, comando)
3. Se ho mostrato un elenco: è **completo** e nell'ordine dell'output?
4. Ho riscritto il file di stato aggiornato, e c'è il blocco `⟦ST⟧` con il
   `passo` giusto?
5. Se ho registrato: ho visto `OK:`, ho **cancellato il file di stato**, e c'è il
   numero di riga e il link?
6. La domanda è una sola ed è chiusa?
7. È **un** messaggio, senza narrazione dei passaggi interni?

---

## 11. Errori visti succedere davvero

- **Mostrare o scrivere voci non lette in questo turno.** Sporca i dati in modo
  invisibile. Se l'output dice `[]`, quella categoria non ha sottocategorie e non
  si chiede niente.
- **Rispondere "hai bisogno di qualcosa?" a un numero nudo.** Un "2" dopo un
  elenco è una scelta: il contesto sta nel file di stato.
- **Rispondere a un messaggio breve senza il blocco di apertura.** Un "2" e un
  "sì" non si interpretano a occhio.
- **Chiedere "vuoi aggiungere una descrizione o delle note?"** Campi con un
  default, e per di più domanda aperta.
- **Non cancellare il file dopo l'`append`.** Il "grazie" successivo riapre una
  transazione già registrata.
- **Usare un file di stato unico per tutti.** La chiave è il mittente.
- **Usare `execute_code`.** Fa scattare l'approvazione e blocca la conversazione
  a metà.
- Chiedere la data, il tipo o la descrizione: hanno tutti un default.
- Chiedere una categoria senza elencarle, o elencarne solo qualcuna con "…".
- Fare due domande nello stesso messaggio, o spezzare un turno in più messaggi.
- Registrare senza conferma una categoria dedotta da te (B1), o chiedere conferma
  di una che l'utente ha già scelto (B3).
- Mandare un messaggio senza blocco `⟦ST⟧`: il turno dopo sei cieco.
- Registrare di nuovo quando lo stato dice `passo=fatto`.
- Riordinare l'elenco numerato fra un turno e l'altro.
- Rispondere con cifre a domande sui totali: non sai leggere il foglio.
- Ricominciare da zero quando l'utente corregge un campo.
- Dire "registrato" senza aver visto `OK:` nell'output.
