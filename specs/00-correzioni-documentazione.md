# SPEC-00 — Correzioni di documentazione

**Stato:** da fare · **Dipende da:** nessuno · **Tocca codice:** no

---

## Problema

Tre affermazioni false nella documentazione, trovate verificando il formato reale dei file.
Nessuna ha a che vedere con le altre specifiche: sono bug preesistenti.

### 1. `tests/README.md` documenta una chiave che l'harness non legge

[`tests/README.md:58`](../tests/README.md#L58), nel template per aggiungere un caso di eval:

```jsonc
"messaggi_attesi": ["Confermi?"], // i messaggi dello script, alla lettera
```

Le chiavi realmente usate dai 19 casi in `casi_eval.json` sono:

```
descrizione, esito, id, interpretazione, messaggio, riga_attesa,
risposte, stati_attesi, valuta_interpretazione
```

Non esiste nessun `messaggi_attesi`: la chiave è **`stati_attesi`**, e contiene nomi di stato
(`"chiedi_conferma"`), non messaggi. Chi seguisse il README scriverebbe un caso che l'harness
ignora silenziosamente — il caso passerebbe senza verificare nulla.

### 2. `ARCHITECTURE.md` sbaglia il numero dei casi di eval

Dice «~14 casi» in due punti. Sono **19**:

```
ristorante-completo, categoria-da-chiedere, benzina, categoria-senza-sottocategorie,
stipendio-entrata, investimento-dividendi, investimento-pac, data-esplicita,
importo-migliaia, importo-mancante, recupero-data-non-valida,
recupero-importo-con-valuta, conferma-negata-e-corretta, mai-confermata,
trappola-sottocategoria-inesistente, conferma-con-ok, conferma-accentata,
conferma-non-capita, categoria-minuscola
```

### 3. `README.md` sbaglia il numero dei test

[`README.md:95`](../README.md#L95) dice «263 test». `make test` ne esegue **267**.

---

## Comportamento richiesto

La documentazione dice il vero. In particolare, chi legge `tests/README.md` per aggiungere un
caso di eval scrive un caso che l'harness esegue davvero.

---

## Progettazione

### `tests/README.md`

Nel blocco del template, sostituire la riga di `messaggi_attesi` con quella vera. Il commento
va corretto insieme alla chiave, perché è la parte che induce in errore: parla di «messaggi
dello script, alla lettera», mentre il contenuto sono nomi di stato.

```jsonc
"stati_attesi": ["chiedi_conferma"],  // gli stati attraversati, in ordine
```

Verificare anche il resto del template contro un caso reale — `data-esplicita` è il più
rappresentativo — e allineare quello che non combacia.

### `ARCHITECTURE.md`

Entrambe le occorrenze di «~14»: portarle a **19**. Sono in §4 (mappa dei file) e §12
(test ed eval).

### `README.md`

«263 test» → «267 test».

---

## Fuori scope

- Gli altri riferimenti stantii già mappati in [`ARCHITECTURE.md`](../ARCHITECTURE.md) §14.5
  (`references/tassonomia.yaml` in `budget_sheets.py:965` e `tests/eval_modello.py:78`,
  l'import inutilizzato in `eval_protocollo.py:29`, il commento a `SKILL.md` in
  `casi_eval.json:8`, gli spazi in coda in `tassonomia.yaml:224`). Restano lì come debito
  noto: correggerli è un altro cambiamento, con un'altra ragione.
- Qualunque modifica a `casi_eval.json` o all'harness.
- Automatizzare il conteggio dei test nel README.

---

## Criteri di accettazione

- [ ] Ogni chiave citata in `tests/README.md` esiste davvero nei casi di `casi_eval.json`
- [ ] `ARCHITECTURE.md` non contiene più «~14» riferito ai casi di eval
- [ ] Il numero di test nel `README.md` combacia con l'output di `make test`
- [ ] `make test` verde (nessun file di codice è stato toccato)

---

## Test

Nessuno. È documentazione.

> Si potrebbe aggiungere un test che verifica il numero di casi citato nei README, ma
> legherebbe la suite al testo della documentazione e fallirebbe a ogni caso aggiunto. Il
> costo supera il beneficio per un documento che si legge, non si esegue.

---

## Verifica

```bash
cd /Users/loprieno-andrea/Documents/budget-familiare-workflow

# 1. le chiavi citate nel README esistono davvero
python3 -c "
import json, re
casi = json.load(open('tests/casi_eval.json'))['casi']
reali = set().union(*(set(c) for c in casi))
citate = set(re.findall(r'\"(\w+)\":', open('tests/README.md').read()))
print('nei casi:', sorted(reali))
print('citate nel README ma inesistenti:', sorted(citate - reali) or 'nessuna')
"

# 2. i numeri
python3 -c "
import json
print('casi di eval:', len(json.load(open('tests/casi_eval.json'))['casi']))
"
make test 2>&1 | tail -3        # il numero di test da citare nel README
grep -n '~14\|263 test' README.md ARCHITECTURE.md || echo 'nessun numero stantio'
```

---

## Decisioni e alternative scartate

**Perché è uno spec a sé e non una riga dentro gli altri.** Sono bug preesistenti, senza
alcun rapporto con le date o con l'anno del budget. Infilarli in un altro commit ne
confonderebbe la storia: chi un domani leggesse `git log` per capire perché è cambiato
`tests/README.md` troverebbe un commit intitolato «date parlate».

**Perché la chiave sbagliata conta più degli altri due errori.** Un numero sbagliato si nota
e si ignora. Una chiave sbagliata produce un caso di test che **sembra** verificare qualcosa
e non verifica niente — è un errore che si propaga silenziosamente nel lavoro di chi legge.
