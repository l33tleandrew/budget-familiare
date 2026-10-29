# Specifiche

Ogni file descrive **un cambiamento atomico**: consegnabile da solo, reversibile da solo,
con criteri di accettazione che passano o falliscono. Si prendono in carico uno alla volta.

## Stato

| # | Spec | Stato | Dipende da |
|---|---|---|---|
| 00 | [Correzioni di documentazione](00-correzioni-documentazione.md) | da fare | — |
| 01 | [Anno del budget centralizzato](01-anno-budget-centralizzato.md) | **fatto** | — |
| 02 | [Guardia sul cambio d'anno](02-guardia-cambio-anno.md) | **fatto** | 01 |
| 03 | [Vincolo d'anno sulle date](03-vincolo-anno-sulle-date.md) | **fatto** | 01 |
| 04 | [Giorno e mese](04-date-parlate.md) | da fare | 01 |
| 05 | [Configurazione per istanza](05-configurazione-per-istanza.md) | **fatto** | 01, 02 |
| 06 | [Consenso OAuth incluso](06-consenso-oauth-incluso.md) | **fatto** | 05 |
| 07 | [Il profilo dalla posizione del plugin](07-profilo-dalla-posizione-del-plugin.md) | **fatto** | 05 |

Più un file che **non è uno spec**: [`arretrato-date.md`](arretrato-date.md), dove stanno le
famiglie di date valutate e rinviate, con le misure che le motivano. Ha assorbito i due spec
che prima si chiamavano 05 (prompt del modello) e 06 (copertura eval): il minimo di prompt
senza cui SPEC-04 non si attiva è entrato in SPEC-04, il resto è arretrato. I due numeri,
rimasti liberi, sono stati poi riusati per gli SPEC-05 e 06 della tabella, che non hanno niente
a che fare con quelli.

```
00  indipendente, rischio zero

01  anno del budget centralizzato     ◆ refactor puro
 ├── 02  guardia sul cambio d'anno
 ├── 03  vincolo d'anno sulle date    ◆ l'unico che restringe
 ├── 04  giorno e mese                ◆ la richiesta iniziale, prima versione
 │    └── arretrato-date.md           ◇ non uno spec: le voci rinviate
 └── 05  configurazione per istanza  ◆ il plugin su un'altra istanza Hermes (anche da 02)
      ├── 06  consenso OAuth incluso
      └── 07  profilo dalla posizione del plugin  ◆ correzione: HERMES_HOME sbagliava
```

02, 03 e 04 sono fra loro indipendenti: dipendono solo da 01 e si possono prendere in
qualsiasi ordine. Fermarsi dopo uno qualsiasi lascia la suite verde e il plugin funzionante.

## Criterio di atomicità

Uno spec entra qui solo se soddisfa tutte e quattro:

| | Criterio |
|---|---|
| **Consegnabile** | ci si può fermare lì: la suite è verde e il plugin funziona |
| **Reversibile** | si può annullare senza toccare gli altri |
| **Verificabile** | i criteri di accettazione passano o falliscono, non sono opinioni |
| **Una ragione** | se qualcosa va storto, si sa quale decisione rimettere in discussione |

## Struttura di ogni file

Stato · Dipende da · Problema · Comportamento richiesto · Progettazione · Fuori scope ·
Criteri di accettazione · Test · Verifica · **Decisioni e alternative scartate**.

L'ultima sezione è quella che rende questi file utili fra sei mesi: le scelte sono state
prese con misure concrete, e senza il «perché» qualcuno le rifarà al contrario.

## Contesto

Nascono da una richiesta sola — riconoscere date tipo «il 10 settembre» — che ha fatto
emergere un problema più a monte: l'anno del budget era sepolto dentro la stringa
`SHEET_NAME = "Transazioni 2026"` e non esisteva come parametro, pur essendo il criterio con
cui le transazioni sono organizzate. Da qui la separazione fra il ramo `01→02/03` (l'anno
come configurazione) e il ramo `01→04` (le date parlate).

La richiesta ha però una coda lunga: una data detta a voce arriva in molte forme, e provarle
tutte contro il codice ha mostrato che la prima stesura di SPEC-04 ne copriva 3 su 22. Invece
di allargare lo spec si è scelto il contrario — ridurlo alla forma `<giorno> <mese>`, che si
innesta senza modificare una riga esistente — e di spostare il resto nell'arretrato, misurato
voce per voce. Il criterio di atomicità qui sotto è la ragione della scelta.

Con 01 fatto, `ANNO_BUDGET` esiste e nessuno ancora lo usa: è esattamente il presupposto su
cui 02, 03 e 04 sono stati scritti.

Per come è fatto il sistema che questi spec modificano, vedi [ARCHITECTURE.md](../ARCHITECTURE.md).
