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
