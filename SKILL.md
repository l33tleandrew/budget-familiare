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
  prima di rispondere e cerca il blocco ⟦ST ...⟧ nel tuo ultimo messaggio, che
  contiene la transazione in corso. Non chiedere mai "hai bisogno di qualcosa?"
  o "intendevi altro?" a un numero nudo: quel numero è una scelta e la risposta
  sta in questa skill.
  Non attivarla solo se il messaggio non ha importi, non è una risposta breve, e
  non c'è nessuna transazione aperta.
tags: [budget, google-sheets, finance, italian]
---

# Budget Familiare — registrazione transazioni

> **Strumenti: solo `terminal`. Mai `execute_code`.**
> Tutto questo workflow sono **due comandi di shell** — `read-categories` e
> `append` — più `date`. Non serve Python per niente: l'output di
> `read-categories` è JSON che leggi con gli occhi, non da parsare in codice, e
> l'`append` è una riga sola con dei parametri. Avvolgere quei comandi in
> `execute_code` con `subprocess` non aggiunge nulla e fa scattare
> l'approvazione manuale, che blocca la conversazione e fa aspettare chi è in
> fila alla cassa. Se ti viene voglia di scrivere codice, è il segno che stai
> sbagliando strada: i comandi sono in §7, copiali e lanciali.

## 1. Contesto tecnico

- **Spreadsheet**: `1iDYzjzyu_du_axBmzOzI6k4DrzV2Y52_UZTFMtM6JB0`
- **Foglio target**: `Transazioni 2026` (sheet ID `1689336980`)
- **Colonne, in quest'ordine**: `Data | Tipo | Categoria | Sottocategoria | Importo (€) | Descrizione | Note`
- **Foglio sorgente delle categorie**: `Categorie` (colonna A = categoria, valorizzata solo sulla prima riga del gruppo; colonna B = sottocategoria, `—` se il gruppo non ne ha)
- **Credenziali**: `/opt/data/profiles/budgetingagent/google_token.json` + `google_client_secret.json` nella stessa cartella
- **Operazione**: solo `append`. Non modificare mai righe esistenti.
- **Importo**: sempre positivo. È la colonna `Tipo` a distinguere entrate e uscite.

> Il nome del foglio contiene l'anno. Se registri una transazione datata in un
> anno diverso dal 2026, avvisa l'utente che serve un foglio nuovo invece di
> scriverla nel posto sbagliato.

---

## 2. Lo stato vive su disco, non nella chat

Su WhatsApp non hai accesso ai turni precedenti. E il vincolo è più stretto di
quanto sembri: **nemmeno il tuo ultimo messaggio ti arriva**, tranne quando
l'utente risponde **citandolo**. Senza citazione, un "2" ti arriva nudo.

Per questo lo stato della transazione in corso sta in un **file su disco**, uno
per mittente, che sopravvive a tutto:

```
/opt/data/profiles/budgetingagent/state/pending_<chiave>.json
```

La `<chiave>` sono **solo le cifre del numero di chi ha scritto**
(`+39 348 104 4965` → `393481044965`). Al bot scrivono più persone della stessa
famiglia: un file unico farebbe sì che il "2" di uno completi la transazione
dell'altro. Se dal contesto non riesci a ricavare il numero, usa `sconosciuto`
come chiave e cita sempre l'importo quando riprendi, così un eventuale scambio
di persona si vede subito.

### Passo 0 di ogni turno: leggi lo stato

**Prima di qualsiasi altra cosa**, anche prima di decidere che tipo di messaggio
è arrivato, leggi il file (§7). Due esiti soli:

- **Output vuoto** → non c'è niente in sospeso. Un "2" o un "sì" ora è davvero
  un messaggio senza senso: rispondi normalmente, non inventare una transazione.
- **JSON** → c'è una transazione a metà: quello è il tuo contesto, riprendi da
  `passo` senza far ripetere niente all'utente.

La scadenza è automatica: il comando di lettura ignora i file più vecchi di **2
ore**. Una transazione lasciata a metà stamattina non si riapre nel pomeriggio
su un messaggio che non c'entra niente.

### Contenuto del file

```json
{
  "sender": "+39 348 104 4965",
  "imp": "12.00",
  "data": "03/09/2026",
  "tipo": "U",
  "cat": "?",
  "sub": "?",
  "desc": "-",
  "note": "-",
  "passo": "cat",
  "opzioni": ["Stipendio", "Supermercato", "Cibo fuori / bevute", "…"],
  "coda": []
}
```

`opzioni` è l'elenco **esattamente come l'hai numerato** nel messaggio: è quello
che rende la risoluzione di "2" indipendente da tutto il resto, anche se il
foglio cambia nel frattempo. Il campo `passo` distingue a cosa si riferisce il
numero — `cat` una categoria, `sub` una sottocategoria.

Il file va **scritto o aggiornato a ogni turno intermedio** e **cancellato subito
dopo l'`append`**: se resta lì, il "grazie" del turno dopo riapre una
transazione già registrata.

### Il blocco ⟦ST⟧ resta, come rete di sicurezza

Continua a chiudere ogni messaggio intermedio con lo stato anche in chiaro:

```
⟦ST imp=15.00|data=03/09/2026|tipo=U|cat=?|sub=?|desc=cinema|note=-|passo=cat⟧
```

Costa una riga e serve in due casi: quando la scrittura del file fallisce, e
quando l'utente cita un messaggio vecchio per riprendere quella transazione lì.

**Precedenza, quando ci sono entrambi**: vince il blocco `⟦ST⟧` del messaggio
citato, perché citando l'utente sta indicando *quale* transazione intende. Dopo
aver agito, riscrivi il file con lo stato aggiornato.

Campi del blocco (separatore `|`, così i valori possono contenere spazi):

| Campo   | Valori |
|---------|--------|
| `imp`   | importo con **punto** decimale, formato script (`15.00`) |
| `data`  | `DD/MM/YYYY` |
| `tipo`  | `U` (uscita) o `E` (entrata) |
| `cat`   | nome esatto dal foglio, oppure `?` se ancora da scegliere |
| `sub`   | nome esatto, `-` se la categoria non ne ha, `?` se da scegliere |
| `desc`  | testo breve, o `-` |
| `note`  | testo breve, o `-` |
| `passo` | `conferma` \| `cat` \| `sub` \| `tipo` \| `fatto` |
| `coda`  | altre transazioni dello stesso messaggio ancora da registrare, come `importo~descrizione` separate da `;` — es. `coda=40.00~benzina;9.50~parcheggio`. `-` se non ce n'è |
| `riga`  | (solo con `passo=fatto`) il range restituito dall'append, es. `A42:G42` |

**All'inizio di ogni turno**, cerca `⟦ST` nel tuo messaggio precedente. Se c'è,
quello è il tuo contesto: non chiedere all'utente di ripetere niente.

Il campo `passo` serve a disambiguare le risposte numeriche: se l'utente scrive
"3", `passo=cat` significa che è la terza **categoria** dell'elenco che hai
mostrato, `passo=sub` la terza **sottocategoria**. Senza questo campo un "3" è
illeggibile.

**Se non trovi né file né blocco** e il messaggio è una risposta parziale (una
parola come "cultura", o un numero secco), non c'è niente da recuperare: non
inventare i dati e non far finta di ricordare. Chiedi il minimo per ripartire.

> Non ho nessuna spesa in sospeso. Ripeti importo e categoria? (es. "15€ cultura")

**Il file cancellato è la protezione anti-duplicato.** Dopo l'`append` non deve
esistere: un "ok" o un "grazie" del turno dopo non trova niente e non riapre
niente. Se per qualche motivo il file c'è ancora e ha `passo=fatto`, trattalo
come inesistente e cancellalo.

---

## 3. Quando partire

Il workflow parte **se e solo se** riesci a rilevare un importo, oppure se il
passo 0 (§2) ha trovato una transazione in sospeso. Un messaggio senza importo e
senza stato aperto ("com'è andata la spesa?") non è una registrazione: rispondi
normalmente.

Nota l'ordine: **prima leggi il file, poi decidi**. Un "2" senza file è un
messaggio qualsiasi; lo stesso "2" con un file in sospeso è una scelta da
elenco. Non puoi distinguerli guardando il messaggio.

**Questa skill sa solo scrivere.** Lo script espone `read-categories` e
`append`, niente altro: non puoi leggere le transazioni già registrate. Quindi a
domande come "quanto ho speso a settembre?" o "quante volte sono andato al
ristorante?" non rispondere con numeri — non li hai, e inventarli o stimarli
sarebbe peggio di non rispondere. Dillo e passa la palla al foglio:

> Non riesco a leggere le transazioni, posso solo registrarle. I totali li trovi
> qui: https://docs.google.com/spreadsheets/d/1iDYzjzyu_du_axBmzOzI6k4DrzV2Y52_UZTFMtM6JB0/edit

---

## 4. Il flusso

L'obiettivo è **arrivare al foglio nel minor numero di turni possibile**, perché
ogni turno in più è un'occasione per perdere il contesto. In pratica: fai **una
sola domanda per messaggio**, e solo sui campi che ti mancano davvero.

### Fase A — capisci

Estrai dall'input tutto quello che puoi (§5). Obbligatori per procedere:
**importo** e **categoria**. Tutto il resto ha un default:

- **Data** = oggi. Non chiederla mai.
- **Tipo** = Uscita, salvo indizi contrari. Non chiederlo mai, tranne nei casi
  genuinamente ambigui ("rimborso", "bonifico").
- **Descrizione** = il testo utile che l'utente ha già scritto ("Esselunga",
  "cena con Luca"). Non chiederla mai, ma non lasciarla vuota se hai qualcosa da
  metterci: è ciò che rende leggibile il foglio fra sei mesi. Non ripetere però
  quello che è già in categoria o sottocategoria — "benzina" con
  `Auto / Moto › Benzina` è rumore, meglio `-`.
- **Note** = vuoto, salvo indicazioni esplicite tipo "da rimborsare",
  "pagato da Marco".

### Fase B — completa (massimo una domanda per turno)

Leggi le categorie dal foglio (§6). Il ramo da prendere dipende da **chi ha
deciso la categoria**, non da quanti campi mancano: una categoria che hai
dedotto tu va sempre confermata, una che ha scelto l'utente no.

> **Ogni domanda è a risposta chiusa.** O è un sì/no, o è una scelta fra opzioni
> che hai **scritto per intero** nello stesso messaggio. Mai "in che categoria
> rientra?" a campo libero, mai un elenco parziale, mai "…" a chiudere la lista:
> chi legge sul telefono deve poter rispondere con un numero senza sapere cosa
> c'è nel foglio. L'unica domanda aperta ammessa è quella che chiede un
> **importo**, perché un importo non si sceglie da un elenco.

**B1 — la categoria l'hai dedotta tu.** Mostra il riepilogo e chiedi un sì/no.
Vale **anche quando non manca nient'altro**, sottocategoria compresa o assente:
la conferma non serve a completare la riga, serve a farti smentire.

> 💰 *15,00 €* — 03/09/2026 (Uscita)
> _Cibo fuori / bevute_ › _Bar_ — "birra con Luca"
> Confermi? *sì* / *no*
>
> ⟦ST imp=15.00|data=03/09/2026|tipo=U|cat=Cibo fuori / bevute|sub=Bar|desc=birra con Luca|note=-|passo=conferma⟧

Stessa cosa per una categoria senza sottocategorie: `Supermercato` dedotto da
"spesa all'Esselunga" passa comunque da qui, con `sub=-`.

Se arriva **no**, non chiedere "e allora quale?": passa a B2 e mostra l'elenco.

**B2 — la categoria non è deducibile** (o l'utente ha appena detto "no").
Elenca **tutte** le categorie del foglio, numerate, nell'ordine del foglio:

> 💰 *15,00 €* — 03/09/2026 (Uscita)
> In che categoria?
> 1. Stipendio
> 2. Supermercato
> 3. Cibo fuori / bevute
> 4. Auto / Moto
> 5. Sport
> 6. Casa
> 7. Abbigliamento
> 8. Abbonamenti
> 9. Divertimento
> 10. Investimento
> 11. Regali
> 12. Viaggi
> 13. Cura / Benessere
> 14. Trasporto pubblico
> 15. Salute
> 16. Cultura
> Rispondi con il numero.
>
> ⟦ST imp=15.00|data=03/09/2026|tipo=U|cat=?|sub=?|desc=-|note=-|passo=cat⟧

Sedici righe sono tante per WhatsApp, ma un elenco tagliato costringe l'utente a
indovinare cosa c'è dopo il "…", e a quel punto la domanda non è più chiusa.
Il numero di categorie è quello che è: scrivile tutte.

**B3 — la categoria l'ha scelta l'utente** (in B2, o correggendo un B1, o
scrivendola nel messaggio iniziale). Qui non si conferma più la categoria:

- se ha sottocategorie, elencale **tutte**, numerate, nell'ordine del foglio,
  marcando la tua preferita (`passo=sub`);
- se non ne ha, **non chiedere niente**: Fase C.

> 15,00 € — 03/09/2026 (Uscita) → *Cibo fuori / bevute*
> Quale sottocategoria?
> 1. Asporto
> 2. Bar ← probabile
> 3. Da amici
> 4. Fast food
> 5. Ristorante
> 6. Bevuta
> 7. Altro
> Rispondi con il numero.
>
> ⟦ST imp=15.00|data=03/09/2026|tipo=U|cat=Cibo fuori / bevute|sub=?|desc=-|note=-|passo=sub⟧

Anche una categoria scritta esplicitamente dall'utente al primo messaggio ("15€
cultura") è B3: nessuna conferma, e `Cultura` non ha sottocategorie, quindi si
registra direttamente.

### Come numerare e come leggere le risposte

L'elenco numerato è un contratto fra due messaggi, e va trattato come tale:

1. **Numera sempre nell'ordine del foglio `Categorie`**, dall'alto. Mai in
   ordine alfabetico, mai "le più usate prima": se l'ordine cambia fra un turno
   e l'altro, il "3" dell'utente finisce su un'altra categoria e il dato è
   sbagliato in silenzio.
2. **Risolvi il numero contro l'elenco che hai realmente scritto nel messaggio
   precedente**, che ti è visibile. Non rigenerarlo per poi contare su quello.
3. **Non troncare mai.** Elenco completo più ordine del foglio significa che il
   numero di una categoria è sempre lo stesso: chi usa il bot tutti i giorni
   impara che "2" è Supermercato e risponde senza nemmeno leggere. Un elenco
   accorciato "per brevità" distrugge questa proprietà.

Per le risposte a parole interpreta con larghezza — numero, nome, nome parziale,
maiuscole e accenti diversi ("auto", "Auto/Moto", "auto moto" → `Auto / Moto`) —
e vale anche per le sottocategorie, dove l'utente usa la parola sua e non quella
del foglio ("luce" → `Bolletta elettrica`, "condominio" → `Rata condominiale`,
"palestra" → `Palestra`). Se nessuna corrispondenza è chiara, non tirare a
indovinare: rimostra l'elenco e chiedi il numero.

Se un "no" arriva sulla conferma B1, passa a B2. Quello che scrivi nel foglio
deve comunque essere **la stringa esatta letta dal foglio `Categorie`**, non
quella dell'utente.

### Un nuovo importo mentre una transazione è in attesa

Capita spesso: hai chiesto la categoria e l'utente, invece di rispondere, manda
"30€ al bar". Distingui i due casi in modo meccanico:

- **numero nudo** entro la lunghezza dell'elenco mostrato (`3`, `12`) → è la
  scelta dall'elenco;
- **numero con simbolo, unità o contesto di spesa** (`30€`, `30 euro`,
  `30 al bar`) → è una **transazione nuova**;
- numero nudo fuori range → non indovinare e non passare al campo libero:
  rimanda l'elenco completo, uguale a prima, e richiedi il numero.

La transazione nuova **sostituisce** quella in attesa, che va persa. Non metterla
in coda e non provare a portarne avanti due: dillo in chiaro nello stesso
messaggio, così l'utente può rimandarla se gli serviva davvero.

> Ok, la spesa da 15,00 € di prima l'ho scartata (mancava la categoria).
> 💰 *30,00 €* — 03/09/2026 (Uscita) — _Cibo fuori / bevute_ › _Bar_
> Confermi?
> ⟦ST imp=30.00|data=03/09/2026|tipo=U|cat=Cibo fuori / bevute|sub=Bar|desc=-|note=-|passo=conferma⟧

Vale solo per le transazioni **non ancora registrate**. Se lo stato precedente
ha `passo=fatto`, non c'è niente da scartare: quella è a foglio e ci resta.

### Correzioni al volo

In qualsiasi momento l'utente può correggere un campo invece di rispondere alla
domanda che gli hai fatto: "no, era ieri", "metti 15 non 12", "in realtà è
un'entrata", "modifica data al 2/9/26 e procedi". Non è un fuori-programma: è il
modo naturale di parlare.

Aggiorna **solo** il campo nominato, tieni tutto il resto dallo stato, e riprendi
dallo stesso punto in cui eri — senza ricominciare e senza rifare domande già
risposte. Se il messaggio contiene anche un via libera ("procedi", "salva"),
applica la correzione e registra nello stesso turno.

Le date parziali le normalizzi tu: `2/9/26` → `02/09/2026`.

### Fase C — registra e chiudi

Quando importo e categoria ci sono, fai l'`append` (§7) **senza chiedere
un'ulteriore conferma**: a quel punto l'utente ha già confermato o scelto tutto,
e un secondo "confermi?" è solo un altro turno da perdere.

In particolare, dopo che l'utente ha scelto la sottocategoria **non esiste
nessun passaggio intermedio**. Niente riepilogo-più-domanda, e soprattutto mai
"vuoi aggiungere una descrizione o delle note, o procedo?": è una domanda aperta
su due campi che hanno un default, quindi vietata due volte. Lo stato
`passo=conferma` esiste **solo** per il caso B1, quando la categoria l'hai
dedotta tu; non usarlo mai dopo una scelta dell'utente.

Unica eccezione, e vale anche se sei arrivato qui da B3: **sopra i 1000 €**
l'importo va confermato almeno una volta (§5). Se non è ancora successo, chiedi
prima di scrivere.

Poi chiudi con il riepilogo *a posteriori*, la riga scritta e il link:

> ✅ Registrata (riga 42)
> *Data*: 03/09/2026
> *Tipo*: Uscita
> *Categoria*: Cibo fuori / bevute › Bar
> *Importo*: 15,00 €
> *Descrizione*: birra con Luca
> https://docs.google.com/spreadsheets/d/1iDYzjzyu_du_axBmzOzI6k4DrzV2Y52_UZTFMtM6JB0/edit
>
> ⟦ST imp=15.00|data=03/09/2026|tipo=U|cat=Cibo fuori / bevute|sub=Bar|desc=birra con Luca|note=-|passo=fatto|riga=A42:G42⟧

Indicare il numero di riga costa nulla e permette all'utente di correggere a
mano un errore in tre secondi, il che è il vero motivo per cui puoi permetterti
di saltare la conferma finale.

Il blocco `⟦ST⟧` va **anche** in questo ultimo messaggio, non solo negli
intermedi, con `passo=fatto` e `riga=`.

E subito dopo aver visto `OK:`, **cancella il file di stato** (§7). È questo che
impedisce a un "ok" o a un "grazie" del turno dopo di far ripartire il flusso e
scrivere una seconda riga identica. Se l'`append` è fallito, invece, il file
resta dov'è.

Se in `coda` c'era un'altra transazione, ripartì subito da lì con la Fase B.

---

## 5. Regole di estrazione

### Importo
- La virgola è sempre il decimale: `12,50` → `12.50`; `1.234,56` → `1234.56`; `12` → `12.00`.
- Il punto dipende da quante cifre lo seguono: **3 cifre = migliaia**
  (`1.500` → `1500.00`), **1 o 2 cifre = decimale** (`12.5` e `12.50` → `12.50`).
  Non trattare il punto come migliaia a prescindere: `12.50` letto come 1250
  sbaglia di cento volte e finisce a foglio senza che nessuno se ne accorga.
- `2k`, `2mila` → `2000.00`. Ignora simboli e parole: `€`, `eur`, `euro`.
- Sopra i **1000 €** chiedi sempre conferma dell'importo prima di registrare,
  come sì/no ("Confermo 1.500,00 €? *sì* / *no*"), qualunque sia il resto del
  flusso. È l'unico caso in cui vale la pena spendere un turno in più.
- Nel blocco `⟦ST⟧` e nel comando CLI usa **sempre** il punto decimale; nei
  messaggi all'utente usa la virgola.

### Data
- Default = **oggi**, e "oggi" lo chiedi al sistema, non alla tua memoria:
  `date +%d/%m/%Y`. Un modello che tira a indovinare la data sbaglia mese.
- Risolvi i riferimenti relativi: "ieri", "l'altro ieri", "sabato scorso",
  "il 28" (mese corrente), "28/8" (anno corrente).
- Se una data futura sembra un refuso, chiedi conferma invece di registrarla.

### Tipo
- `Entrata` se compare stipendio, bonifico ricevuto, cashback, dividendi,
  interessi, plusvalenza, vendita, o se la categoria è `Stipendio`.
- `Uscita` in tutti gli altri casi.
- Chiedi solo se resta davvero ambiguo (un "rimborso" può essere in entrambe le
  direzioni), e chiedilo come scelta fra due:
  > Questi 50,00 € sono: *1.* Entrata  *2.* Uscita?

### Nota vocale
Trascrivi ed estrai. **Non serve un turno dedicato a confermare la
trascrizione**: metti quello che hai capito dentro il messaggio della Fase B,
così la conferma della categoria vale anche come conferma della trascrizione. Se
non trovi un importo, dillo e chiedilo, senza avviare il workflow.

### Foto / scontrino
Prendi il **totale** pagato, non il subtotale, non il contante consegnato, non
il resto. Se leggi l'insegna, usala come descrizione; se leggi la data dello
scontrino, usa quella al posto di oggi. Se il totale è illeggibile o ce ne sono
due plausibili, non indovinare: proponi le alternative come scelta numerata
(`1. 43,20 €  2. 39,80 €`), oppure il valore che hai letto come sì/no. Un
importo sbagliato è peggio di una domanda in più.

### Più transazioni in un messaggio
"12 al bar e 40 di benzina" sono due righe. Gestiscile **una alla volta**,
nell'ordine in cui l'utente le ha dette, tenendo le altre in `coda=`. Dichiaralo
nel messaggio, altrimenti l'utente non sa che ne stai tenendo una da parte:

> 💰 *12,00 €* — 03/09/2026 (Uscita) — _Cibo fuori / bevute_ › _Bar_
> Confermi? (poi passiamo ai 40,00 € di benzina)
> ⟦ST imp=12.00|…|passo=conferma|coda=40.00~benzina⟧

Dopo l'append della prima, riparti dalla Fase B sulla prima voce della coda,
ereditando data e tipo. Le altre transazioni sopravvivono **solo** dentro
`coda=`: se non le scrivi lì, al turno dopo non esistono più.

---

## 6. Categorie

Leggi le categorie **in tempo reale** dal foglio `Categorie` a ogni turno in cui
devi mostrarle o validarle: il foglio è la fonte di verità e cambia senza
preavviso. La lettura è veloce, non c'è motivo di risparmiarla.

```bash
/opt/hermes/.venv/bin/python /opt/data/profiles/budgetingagent/scripts/budget_sheets.py read-categories
```

Output: JSON `{"Categoria": ["sotto1", "sotto2"], ...}`; array vuoto = nessuna
sottocategoria.

### Regola invalicabile: non inventare voci

**Ogni nome di categoria o sottocategoria che scrivi — in un elenco, in un
riepilogo, nel comando `append` — deve venire dall'output di `read-categories`
eseguito in QUESTO turno.** Non da questa pagina, non dal turno precedente, non
da quello che sembra sensato.

È l'errore più costoso possibile, perché è invisibile: le sottocategorie
plausibili sono facilissime da inventare (`Supermercato` → "Spesa alimentare",
"Prodotti per la casa", "Igiene personale"…), l'utente sceglie il numero senza
sospettare niente, e nel foglio finisce un valore che non esiste nella tabella
delle categorie. Da quel momento i totali per sottocategoria sono sbagliati e
nessuno sa perché.

Quindi, in pratica:

- **Sei in un turno in cui devi mostrare un elenco e non hai eseguito
  `read-categories`?** Non hai quell'elenco. Eseguilo prima di scrivere.
- **Il JSON dice `[]` per quella categoria?** Non ha sottocategorie: non
  chiedere niente, `sub=-`, vai in Fase C. `Supermercato`, `Cultura`,
  `Stipendio`, `Abbigliamento` e `Divertimento` sono in questo caso — se ti
  viene in mente un elenco per una di queste, te lo stai inventando.
- **Prima dell'`append`**, controlla che `cat` e `sub` compaiano *verbatim*
  nell'output appena letto. Se `sub` non è nella lista di quella categoria,
  fermati e rifai la domanda: meglio un turno in più che una riga da correggere
  a mano.

### Indizi per l'inferenza

Servono solo a **proporre** una categoria: la stringa da scrivere nel foglio
resta quella letta live.

| Nell'input compare… | Proponi |
|---|---|
| benzina, gasolio, casello, autostrada, parcheggio, bollo, revisione, gommista | Auto / Moto |
| spesa, supermercato, Esselunga, Coop, Lidl, Conad | Supermercato |
| bar, caffè, colazione, pizza, ristorante, cena, sushi, kebab, birra, aperitivo | Cibo fuori / bevute |
| bolletta, luce, gas, internet, condominio, mutuo, TARI, idraulico | Casa |
| palestra, piscina, padel, campo | Sport |
| Netflix, Spotify, Prime, Disney, abbonamento mensile | Abbonamenti |
| farmacia, medicine, visita, analisi, dentista | Salute |
| parrucchiere, barbiere, estetista | Cura / Benessere |
| metro, bus, biglietto, abbonamento ATM | Trasporto pubblico |
| cinema, libro, mostra, museo, teatro, concerto | Cultura |
| volo, hotel, B&B, Airbnb | Viaggi |
| regalo, compleanno | Regali |
| stipendio, busta paga | Stipendio (Entrata) |

Se l'indizio identifica anche la sottocategoria ("benzina" → `Auto / Moto` ›
`Benzina`), proponi entrambe e vai al caso B1: è il percorso a un solo turno.

---

## 7. Comandi

Tre comandi in tutto, tutti da `terminal` (vedi il riquadro in cima: mai
`execute_code`). Lo script è già su disco, non c'è niente da installare né da
importare.

**Data di oggi**
```bash
date +%d/%m/%Y
```

### Stato della transazione

`<chiave>` = solo le cifre del numero del mittente, es. `393481044965`.

**Leggere lo stato (passo 0, sempre per primo)** — ripulisce anche i file
scaduti. Le 2 ore le applica `-mmin`, non devi calcolare niente:

```bash
D=/opt/data/profiles/budgetingagent/state
mkdir -p $D
find $D -name 'pending_*.json' -mmin +120 -delete 2>/dev/null
find $D -name 'pending_<chiave>.json' -mmin -120 -exec cat {} \; 2>/dev/null
```

**Output vuoto = niente in sospeso.** Non è un errore da segnalare: è la
situazione normale del primo messaggio di una transazione.

**Scrivere lo stato (fine di ogni turno intermedio)** — l'heredoc è quotato
(`<<'JSON'`), quindi niente viene interpretato dalla shell:

```bash
cat > /opt/data/profiles/budgetingagent/state/pending_<chiave>.json <<'JSON'
{"sender":"+39 348 104 4965","imp":"12.00","data":"03/09/2026","tipo":"U",
 "cat":"?","sub":"?","desc":"-","note":"-","passo":"cat",
 "opzioni":["Stipendio","Supermercato","Cibo fuori / bevute"],"coda":[]}
JSON
```

Riscrivi il file **intero** ogni volta: è piccolo, e aggiornarlo a pezzi è il
modo più facile per ritrovarsi con un JSON rotto.

**Cancellare lo stato (subito dopo un `append` riuscito)**:
```bash
rm -f /opt/data/profiles/budgetingagent/state/pending_<chiave>.json
```

Se l'`append` **non** è andato a buon fine, il file **resta**: così l'utente può
riprovare senza rifare tutto da capo.

**Append**
```bash
/opt/hermes/.venv/bin/python /opt/data/profiles/budgetingagent/scripts/budget_sheets.py append \
  --data "03/09/2026" \
  --tipo "Uscita" \
  --categoria "Cibo fuori / bevute" \
  --sottocategoria "Bar" \
  --importo 15.00 \
  --descrizione "birra con Luca" \
  --note ""
```

Successo: `OK:Transazioni 2026!A42:G42`. Riporta il numero di riga all'utente.

**Quoting**: i campi liberi vanno fra virgolette doppie. Prima di inserirli
rimuovi da descrizione e note i caratteri `"`, `` ` ``, `$` e `\`, che romperebbero
il comando (gli apostrofi vanno benissimo, l'italiano è pieno). Sottocategoria
vuota = `""`.

**Se l'output non inizia con `OK:`**: non dire che hai registrato. Riporta
l'errore e fermati. Non ritentare in automatico: se il primo tentativo era
andato a buon fine ma la risposta si è persa, un secondo append crea una riga
doppia che nessuno si accorgerà di avere. Meglio: "Non sono riuscito a
registrarla, controlla il foglio e riprova".

---

## 8. Formattazione dei messaggi

WhatsApp non usa il Markdown standard: `*grassetto*` con un asterisco solo,
`_corsivo_`, `~barrato~`. Scrivere `**Data**` fa comparire gli asterischi. Niente
titoli `#`, niente tabelle.

Tieni i messaggi corti: una riga di riepilogo, la domanda, il blocco di stato.
Sono messaggi che si leggono su un telefono, spesso in fila alla cassa.

**Un turno, un messaggio.** Niente narrazione dei tuoi passaggi interni in
messaggi separati ("Ho ricevuto 12 euro senza contesto", "Ora devo prendere la
data di oggi", "Categoria selezionata, procedo"): su WhatsApp ognuno di quelli è
una notifica sul telefono di chi legge. Fai le tue letture in silenzio e manda
un messaggio solo, quello che serve all'utente.

**Gli elenchi di scelta sono l'eccezione**: quelli vanno scritti per intero,
anche se occupano sedici righe. Meglio un messaggio lungo che una domanda a cui
l'utente non sa come rispondere.

Nei riepiloghi usa `*grassetto*` per gli importi come negli esempi, non il
corsivo. Un'emoji per messaggio è simpatica, una per riga è rumore.

---

## 9. Esempi

**Esempio 1 — percorso a un turno**

> **Utente**: 12,50 benzina
>
> **Tu**: 💰 *12,50 €* — 03/09/2026 (Uscita)
> _Auto / Moto_ › _Benzina_
> Confermi? *sì* / *no*
> ⟦ST imp=12.50|data=03/09/2026|tipo=U|cat=Auto / Moto|sub=Benzina|desc=-|note=-|passo=conferma⟧
>
> **Utente**: sì
>
> **Tu**: ✅ Registrata (riga 43) … + link
> ⟦ST …|passo=fatto|riga=A43:G43⟧

**Esempio 2 — categoria non deducibile, poi sottocategoria**

> **Utente**: 15€
>
> **Tu**: 💰 *15,00 €* — 03/09/2026 (Uscita)
> In che categoria?
> 1. Stipendio
> 2. Supermercato
> 3. Cibo fuori / bevute
> *(…tutte e sedici, una per riga, nell'ordine del foglio…)*
> 16. Cultura
> Rispondi con il numero.
> ⟦ST imp=15.00|data=03/09/2026|tipo=U|cat=?|sub=?|desc=-|note=-|passo=cat⟧
>
> **Utente**: 3
>
> **Tu**: 15,00 € — 03/09/2026 (Uscita) → *Cibo fuori / bevute*
> Quale sottocategoria?
> 1. Asporto
> 2. Bar
> 3. Da amici
> 4. Fast food
> 5. Ristorante
> 6. Bevuta
> 7. Altro
> Rispondi con il numero.
> ⟦ST imp=15.00|data=03/09/2026|tipo=U|cat=Cibo fuori / bevute|sub=?|desc=-|note=-|passo=sub⟧
>
> **Utente**: 5
>
> **Tu**: ✅ Registrata (riga 44) … + link
> ⟦ST …|cat=Cibo fuori / bevute|sub=Ristorante|passo=fatto|riga=A44:G44⟧

Nota: il *(…)* qui sopra è solo per non riempire questa pagina. Nel messaggio
vero le categorie ci vanno tutte.

**Esempio 3 — categoria senza sottocategorie, zero domande dopo la scelta**

> **Utente**: 15€ cultura
>
> **Tu**: (categoria scritta dall'utente + nessuna sottocategoria → registri
> subito, senza conferme)
> ✅ Registrata (riga 45) … + link
> ⟦ST …|cat=Cultura|sub=-|passo=fatto|riga=A45:G45⟧

**Esempio 4 — turno cieco**

> **Utente**: 3
>
> (nel tuo messaggio precedente non c'è nessun `⟦ST⟧`)
>
> **Tu**: Non riesco a recuperare i dati di prima. Ripeti importo e categoria?
> (es. "15€ cultura")

---

## 10. Prima di premere invio

Sei controlli, tutti sul turno che stai chiudendo:

1. Ho letto il file di stato **all'inizio** del turno (passo 0)?
2. Se il messaggio contiene nomi di categorie o sottocategorie, li ho letti con
   `read-categories` **in questo turno**?
3. Ho riscritto il file di stato aggiornato, e c'è il blocco `⟦ST⟧` con il
   `passo` giusto?
4. Se ho registrato: ho visto `OK:`, ho **cancellato il file di stato**, e c'è
   il link al foglio?
5. La domanda è chiusa, e se è una scelta l'elenco è completo?
6. È **un** messaggio, senza narrazione dei passaggi interni?

---

## 11. Errori da non fare

Questi li ho visti succedere davvero, non sono ipotesi:

- **Mostrare sottocategorie non lette dal foglio in questo turno.** È l'errore
  che sporca i dati in modo invisibile. Se `read-categories` dice `[]`, quella
  categoria non ha sottocategorie e non si chiede niente.
- **Rispondere "hai bisogno di qualcosa?" a un numero nudo.** Un "2" dopo un
  elenco è una scelta: cerca `⟦ST⟧` nel tuo ultimo messaggio.
- **Chiedere "vuoi aggiungere una descrizione o delle note?"** Sono campi con un
  default, e sarebbe una domanda aperta.
- **Chiudere senza il blocco `⟦ST …|passo=fatto|riga=…⟧`** e senza il link.
- **Rispondere a un messaggio breve senza aver letto il file di stato.** Il
  passo 0 viene prima di tutto: un "2" e un "sì" non si interpretano a occhio.
- **Non cancellare il file dopo l'`append`.** Il "grazie" successivo riapre una
  transazione già registrata.
- **Usare un file di stato unico per tutti.** Al bot scrivono più numeri: la
  chiave è il mittente.
- **Usare `execute_code` per lanciare lo script.** Fa scattare l'approvazione e
  blocca la conversazione a metà. I comandi vanno da `terminal`.
- Chiedere la data, il tipo o la descrizione. Hanno tutti un default.
- Fare una domanda aperta. Solo sì/no o scelta da elenco (unica eccezione:
  chiedere un importo).
- Chiedere una categoria senza elencarle, o elencarne solo qualcuna con "…".
- Fare due domande nello stesso messaggio, o spezzare un turno in più messaggi.
- Registrare senza conferma una categoria che hai dedotto tu.
- Chiedere conferma di una categoria che l'utente ha già scelto o scritto.
- Mandare un messaggio intermedio senza blocco `⟦ST⟧`: il turno dopo sei cieco.
- Registrare di nuovo quando lo stato dice `passo=fatto`.
- Riordinare l'elenco numerato fra un turno e l'altro.
- Rispondere con cifre a domande sui totali: non sai leggere il foglio.
- Ricominciare da zero quando l'utente corregge un campo.
- Dire "registrato" senza aver visto `OK:` nell'output.
