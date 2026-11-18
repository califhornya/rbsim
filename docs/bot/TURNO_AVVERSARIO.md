# La ricerca che gioca anche il turno avversario (18/11)

Domanda: se la ricerca, invece di valutare la posizione a fine del proprio
turno, fa giocare all'avversario il suo turno e valuta dopo, gioca meglio?

## Le due versioni
- **Riferimento**: il bot della PR #32 (`scripts/diag/handwritten_value.py`:
  prior uguali, `table_value`, backup "best"). Una foglia dell'albero del
  turno vale la posizione com'è, a metà o a fine del proprio turno.
- **Variante**: stessa ricerca, stesso valore. Ogni foglia vale la posizione
  dopo che il turno finisce lì, l'avversario gioca tutto il suo turno con le
  mosse di simple_trade (sulla mano e sul mazzo estratti per quell'iterazione)
  e comincia il turno dopo (Hold, rune, pesca). Cambia solo il turno
  principale; reazioni e showdown come nel riferimento.
- Stesso tempo di CPU per decisione: 0,4 s (circa le 100 iterazioni della
  base #32). Iterazioni medie per decisione del turno: riferimento 116,
  variante 54.
- 100 coppie: stesso seme, Evelynn al posto A e Kha'Zix al B, i bot scambiati
  tra le due partite. Script: `scripts/diag/opponent_turn.py 100 0.4`
  (28 minuti su 4 core).

## Risultato
| | Punteggio della variante |
|---|---|
| 200 partite | **0,44** (88 vinte, 112 perse) |
| per coppia | 0,44 ± 0,05 (95%): 9 coppie vinte tutte e due, 70 pari, 21 perse |
| con Evelynn | 0,61 (il riferimento con Evelynn fa 0,73 contro di lei) |
| con Kha'Zix | 0,27 |

Evelynn vince 134 partite su 200 qualunque sia il bot: il mazzo pesa più del bot.
La variante è **più debole** a parità di tempo.

## Perché
I due bot scelgono mosse diverse in 1.816 decisioni del turno su 4.137
(controllo in ombra: il riferimento cerca la stessa posizione senza giocare).
Prendo ogni disaccordo, gioco ciascuna delle due mosse da sola, faccio
giocare il turno avversario e faccio la media su 16 mondi: la mossa della
variante vale di più solo in 438 casi su 1.816. Quasi sempre la variante
sceglie per rumore, non per una previsione. Un turno avversario simulato
cambia molto da un'estrazione all'altra (con o senza la carta giusta in
mano), il backup "best" prende il massimo e quindi premia l'estrazione
fortunata, e le iterazioni sono la metà.

## Le posizioni controllate
Verifica (`scripts/diag/opponent_turn_check.py`): dalla posizione salvata,
K mondi che chi muove non distingue (mano avversaria e mazzi ridistribuiti),
gli stessi per i due bot. Ognuno gioca il resto del proprio turno (riferimento
100 iterazioni, variante 47: lo stesso tempo), poi il riferimento gioca la
partita da entrambe le parti.

| Posizione | Variante | Riferimento | Differenza |
|---|---|---|---|
| s3090 A t3 (Evelynn: Rampage invece di conquistare) | 0,72 | 0,97 | −0,25 ± 0,14 |
| s3029 B t7 | 0,78 | 0,90 | −0,12 ± 0,13 |
| s3076 B t3 | 0,82 | 0,93 | −0,10 ± 0,15 |
| s3026 B t6 | 0,35 | 0,42 | −0,07 ± 0,13 |
| s3048 A t3 | 0,90 | 0,97 | −0,07 ± 0,11 |
| s3076 B t5 | 0,29 | 0,46 | −0,17 ± 0,23 |
| s3037 B t5 | 0,88 | 0,83 | +0,04 ± 0,19 |
| s3037 B t9, s3066 B t7 | uguali | | 0 |
| **s3012 B t7** | **0,96** | **0,50** | **+0,46 ± 0,20** (24 mondi) |
| s3012 B t7, 60 mondi nuovi | **0,92** | **0,47** | **+0,45 ± 0,14** (meglio in 29, peggio in 2) |
| **s3011 B t7** | **0,67** | **0,38** | **+0,29 ± 0,25** (24 mondi) |
| s3011 B t7, 60 mondi nuovi | **0,63** | **0,42** | **+0,22 ± 0,15** (meglio in 18, peggio in 5) |

Le tre posizioni del turno 3 seguono lo stesso schema: la variante non
conquista il campo vuoto con un'unità piccola perché prevede che lui se lo
riprenda. Il riferimento conquista, e ha ragione.

## La posizione nuova: s3012, turno 7, Kha'Zix
File: `docs/bot/posizioni/s3012_B_t07_05.pkl`. Sei Kha'Zix (posto B), avanti
3-2, a metà del tuo turno: hai già giocato 3 carte e non hai più energia.
- BF0 Rakelstake, tuo: due Traveling Merchant (2 e 2, uno esaurito).
- BF1 Sandswept Tomb, di Evelynn: Reckless Innovator (3), Pyke Returned (3),
  Evelynn Entrancing (2), pronti: 8 di Might.
- In base: Zed Without a Sound (5, pronto), Kha'Zix Mutating Horror (4,
  esaurito). Lei ha Momentary Companion (4) in base, 5 carte, 2 energia.

La mossa è dove mandare Zed. Per il riferimento attaccare BF1 o difendere
BF0 vale lo stesso (+0,46 tutte e due); sceglie BF1 in 60 mondi su 60: Zed
muore contro 8 (a volte porta con sé due unità), poi al turno 8 lei tiene
BF1 e la Companion (4, spesso con Hold 'Em) prende BF0 ai due Merchant (4).
La variante manda Zed a BF0 in 59 mondi su 60: il campo ha 9 di Might, lei
non lo attacca, al turno 9 lo tieni tu. **Su 84 mondi: 0,93 contro 0,48.**

L'idea: con l'ultima unità pronta e niente energia, non attaccare un campo
più forte; mettila sul campo che hai, perché il suo turno dopo non possa
prenderlo. La valutazione da ferma non vede la differenza perché conta la
Might sul tavolo e i campi di adesso, non chi attacca dopo.

## Un'altra: s3011, turno 7, Kha'Zix
File: `docs/bot/posizioni/s3011_B_t07_03.pkl` (`opponent_turn_check.py
--show` la stampa). Sei Kha'Zix (posto B), avanti 3-2, inizio del Main Phase,
6 rune, 2 XP, legend pronta. Campi: BF0 Rakelstake vuoto; BF1 Zaun Warrens
di Evelynn, con Rengar Trophy Hunter (6) ed Evelynn Entrancing (2), esauriti.
In base: Traveling Merchant (3). Mano: Vex Apathetic, Void Assault, Traveling
Merchant, Fizz Trickster ×2. Nel cestino c'è un altro Void Assault (Fizz lo
rigioca gratis). Lei ha 5 carte e 4 rune.

- **Riferimento**, in tutti i mondi: Fizz rigioca Void Assault dal cestino
  (Merchant a BF0, Rengar in base) e conquista BF0; Void Assault dalla mano
  (Fizz a BF1, Evelynn spostata) e conquista BF1. Fine turno 5-2, tutti e due
  i campi suoi, Merchant e Fizz da soli sui campi, Rengar vivo in base.
  Quando sposta Evelynn in base invece che contro il Merchant (28 mondi su
  60) fa 0,32; quando lei muore, 0,50. Al turno 8 Rengar si riprende un campo.
- **Variante**: uccide Evelynn in 58 mondi su 60 (Merchant spostato a BF1
  contro di lei) e lascia meno roba esposta a Rengar: con la legend
  (2 XP) riporta il Merchant esaurito in base, oppure manda Rengar contro i
  due Fizz. Le linee variano da un mondo all'altro; con tutti e due i campi
  suoi a fine turno fa 0,70 (30 mondi).
- Sugli stessi mondi la variante fa meglio sia dove il riferimento lascia
  vivere Evelynn (0,57 contro 0,32) sia dove la uccide (0,69 contro 0,50).

L'idea: con +2 sul tavolo, prendere tutti e due i campi con unità da 3
lasciando vivo Rengar (6) gli dà il turno dopo un bersaglio facile per
riprendersi un campo (e il punto). Conviene togliergli le unità che possono
attaccare e tenere al sicuro le proprie, anche cedendo un campo.

Limiti: il resto della partita lo gioca il riferimento (debole: 0,80 contro
simple_trade); la variante prevede l'avversario come simple_trade. La
posizione non è ancora uno scenario della pagina (`scenari.json`): per
farlo serve il copione dal turno 1.
