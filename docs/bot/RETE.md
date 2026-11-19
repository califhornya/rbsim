# La rete dal bot scritto a mano (18/11)

Deciso con l'utente il 18/11: la rete parte dalle partite del bot scritto a
mano (`riftbound/ai/handwritten.py`, 0,80 contro simple_trade), poi il
self-play la migliora. Rispetto al piano del 13/11 si imita il nostro bot
migliore, non simple_trade (scartato perché gioca da neofita). Si allena
sul Mac.

## Cosa fa `scripts/rete.command` (doppio clic)
1. **Partite**: il bot gioca contro se stesso 2.000 partite Evelynn–Kha'Zix,
   a posti alternati, con 100 iterazioni per decisione. Il 30% delle sue
   decisioni con una scelta diventa un esempio: la posizione vista da chi
   decide, la mossa giocata, chi ha vinto alla fine e il valore a mano della
   posizione (per confrontarlo). Circa 14 esempi a partita (il 13/11 troppi
   esempi della stessa partita facevano memorizzare gli esiti).
2. **Allenamento**: le partite si dividono per seed in tre gruppi
   disgiunti (correzione del 18/11, da gptAstra: prima le 200 partite di
   verifica avevano tutte Evelynn in B e servivano sia a scegliere l'epoca
   sia a misurare): 1.600 per allenare, 200 per scegliere l'epoca, 200 per
   il test finale, in ognuno Evelynn metà delle volte in A e metà in B. La
   rete impara la mossa del bot e chi vince sulle 1.600; si tiene l'epoca
   con l'errore del valore più basso sulle 200 della scelta (30 epoche,
   pochi minuti). I conteggi sono controllati a ogni lettura dei dati
   (`check_split`, `tests/test_bootstrap_split.py`).
3. **Misure**, in `runs/boot1/RISULTATI.txt`:
   1. chi vince, previsto sulle 200 partite del test finale (mai usate
      prima): la rete scelta contro il valore a mano, anche per fasi della
      partita;
   2. la prima mossa in quattro posizioni dove si sa qual è la giusta
      (`docs/bot/posizioni/`): s3012, dove Zed deve difendere BF0 (il bot a
      mano sbaglia), e tre del turno 3, dove si deve conquistare (il bot a
      mano fa giusto);
   3. 100 coppie contro il bot a mano, allo stesso tempo di CPU per mossa
      (0,4 s);
   4. 200 partite contro simple_trade come `handwritten_value.py` (0,80).

Cosa vede la rete (correzioni del 18/11 sera, prima del run):
- **La mano e le mosse**: prima la mano era contata per nome (l'ordine non
  si vedeva) e le mosse di una carta erano indicate dalla posizione nella
  mano: scambiate due carte, la preferenza restava al posto e passava
  all'altra carta (S6, Pyke Returned e Gutter Guardian). Ora la mano è una
  riga per carta, nell'ordine del motore, e le mosse di una carta in mano
  (giocarla, coprirla) hanno il punteggio calcolato da quella carta: la
  preferenza segue la carta, nell'allenamento e quando il bot gioca.
- **Evelynn può ancora pescare**: un valore per giocatore dice se l'abilità
  "una volta per turno" della leggenda è ancora libera in questo turno
  (Agony's Embrace pesca quando una carta coperta viene giocata). È l'unica
  differenza tra S11a e S11b.
Test: `tests/test_net_hand_and_legend.py` (falliscono 4 su 5 col codice di
prima). Reti e partite salvate prima non si usano più (input diverso): un
`runs/boot1` vecchio ferma il run subito, con il messaggio di spostarlo.

Tempi sul Mac (stima da qui: 24 s a partita per core): circa un'ora e
mezza per le partite, mezz'ora per le misure.

## Sul Mac
Una volta:
```
cd ~/projects/rbsim2026/rbsim
git fetch origin
git checkout claude/vigilant-gates-b95tqx
git pull
uv sync --extra rl
```
Poi doppio clic su `scripts/rete.command` (o `scripts/rete.command` dal
Terminale). Rilanciato, riprende: le
partite salvate restano. Per fermarlo con tutto salvato basta un file
`STOP` in `runs/boot1`; va cancellato prima di rilanciare. Alla fine
carica in chat `runs/boot1/RISULTATI.txt` e `runs/boot1/net_boot.pt`.

## Quando fermarsi (concordato)
- Se la rete non prevede chi vince meglio del valore a mano (misura 1), o
  non arriva a 0,55 contro il bot a mano (misura 3): stop, e si guardano i
  numeri.
- Altrimenti, punto 4 del piano: self-play con la ricetta del run 3 partendo
  da `net_boot.pt` (`train_selfplay.py --init`), controllando la rete ogni
  10 iterazioni contro il bot a mano. Il lanciatore si prepara dopo aver
  visto i numeri.

Provato qui in piccolo (20 partite, 3 epoche, misure ridotte): la catena
gira dall'inizio alla fine.

## Risultati di boot1 (Mac, 18/11 20:39): stop per la regola concordata
2.000 partite, 28.919 esempi; tenuta l'epoca 13 (errore 0,447 sulle 200
della scelta). Il bot contro se stesso: Evelynn vince 1.386 su 2.000 (0,69).
1. Chi vince (test finale, errore quadratico, 1 = non sapere niente):
   rete 0,466, valore a mano 0,559 (× 1,10: 0,553). Per fasi, turni 1-4 /
   5-8 / 9+: rete 0,514 / 0,396 / 0,485, a mano 0,761 / 0,516 / 0,516.
   **Passa**, meglio in ogni fase.
2. Posizioni note: rete giusta 24/24 in s3012, s3090, s3076; 17/24 in s3048
   (7 volte BF1 invece di BF0, 0,90 contro 0,97). Il bot a mano 24/24 in tutte.
3. Contro il bot a mano, 100 coppie, 0,4 s per mossa: rete 0,460 ± 0,053
   (95%), cioè tra 0,41 e 0,51: **non passa** (serviva 0,55), ma non si
   distingue da 0,50. Con Evelynn 0,63 (il bot fa 0,69), con Kha'Zix 0,29
   (0,31). Iterazioni per decisione: rete 94, bot 114.
4. Contro simple_trade: rete 0,86, il bot a mano 0,80 (differenza dentro
   l'errore di due misure da 200 partite).

Lettura: la rete prevede meglio chi vince, ma gioca come il bot. La ricerca
è la stessa (`backup="best"`); cambiano solo i prior (della rete invece che
uguali) e il valore. Possibili cause, da misurare: i prior imitano il bot e
spingono la ricerca sulle mosse che lui giocherebbe comunque; il valore è
più preciso sulle posizioni delle partite del bot, non per forza nel
distinguere le opzioni di una stessa decisione; il 18% di iterazioni in meno.

## Arena di boot1 (19/11): la prova che decide
Disegno della revisione esterna, regola fissata dall'utente prima del lancio.
- Candidato: `NetValueAgent` (`riftbound/ai/handwritten.py`), la ricerca del
  bot a mano (prior uguali) con il valore di boot1, anche negli showdown,
  nelle reazioni e nel mulligan. Avversario: il bot a mano. Per entrambi
  backup best, mossa col Q massimo, 0,4 s di CPU per mossa.
- 230 coppie di seed nuovi (7000-7229), ogni seed giocato due volte a posti
  scambiati. Si riportano il punteggio, l'IC 95% sulle medie di coppia, il
  punteggio con ciascun mazzo e le iterazioni per decisione.
- Regola: punteggio osservato ≥ 0,55 → ibrido promosso, il self-play parte
  da lui con i prior uguali (da attivare in `selfplay.py`); sotto → boot1
  chiuso con questa ricerca.
- `--avanza` (proposta di Claude; lanciata questa, 19/11, ed è quella che decide): per
  entrambi, il PASS forzato che chiude un movimento (nessun'altra unità può
  unirsi) si gioca subito, invece di valutare il movimento dichiarato a metà.
  Il bot non cerca e non registra le decisioni con una sola azione, quindi la
  rete quello stato non l'ha mai visto; in s3090, s3076 e s3048 entrambe le
  mosse di Evelynn ci passano. Revisione: in s3048 la rete vale -0,37 prima
  del PASS e +0,84 dopo; senza `--avanza` l'ibrido fa 0/24 in s3090 e s3048.
  Il bot a mano, con e senza: stesse scelte nelle quattro posizioni (24
  mondi). Test: `tests/test_advance_forced_move.py`.
- s3012 non dice niente sul bot a mano: le due mosse di Zed hanno lo stesso Q
  fino all'ultima cifra (0,4621171572600096 e ...097), decide l'arrotondamento
  (qui l'attacco, sul Mac la difesa).
- Lancio: `scripts/arena.command` (circa mezz'ora); risultato in
  `runs/boot1/ARENA.txt`.

### Esito (Mac, 19/11 01:34, con `--avanza`): non promosso, boot1 chiuso
- Punteggio **0,296 ± 0,038** (95%, 230 medie di coppia: 0,258-0,333);
  vinte 136, perse 324. Con Evelynn 0,339 ± 0,061 (il bot contro se stesso
  0,69), con Kha'Zix 0,252 ± 0,056 (0,31). Iterazioni: candidato 91, bot 118.
- Posizioni: s3012 e s3076 24/24 per entrambi; s3090 candidato 0/24 (24 volte
  Rampage @BF0), s3048 2/24 (Rampage @BF1 o @BF0); il bot 24/24.
- Lettura: da solo il valore di boot1 gioca molto peggio di `table_value`
  (0,30); lo 0,46 della rete completa veniva dai prior che imitano il bot.
  Prevede chi vince meglio, ma ordina male le mosse di una stessa decisione.
  `--avanza` non era la spiegazione: tolto lo stato a metà movimento,
  l'ibrido sceglie comunque Rampage invece di conquistare.
