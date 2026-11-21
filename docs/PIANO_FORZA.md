# Piano per la forza (21/11)

Deciso con l'utente il 21/11, sentita la revisione esterna: puntare a un
avversario chiaramente più forte del bot a mano, anche se ci vuole tempo. Il
fine resta quello del 13/11: un avversario per allenarsi e uno strumento per
misurare mazzi e matchup.

## Da dove si parte
- Cinque prove con regola fissata prima, nessuna sopra il bot a mano: boot1,
  spareggio, passo 2, tempo (0,8 s contro 0,4 s: 0,472), orizzonte (0,490).
  La ricerca attuale è satura: pensare il doppio non serve; il limite è come
  valuta una posizione e il fatto che vede solo il proprio turno
  (`docs/bot/RETE.md`).
- Velocità: ~2,3-3 ms per iterazione di ricerca, 24,9 s di CPU a partita a
  0,4 s per mossa. Il 93% del tempo di un'iterazione è motore (copia dello
  stato, determinize, mosse legali, applicazione); ottimizzare il Python dà al
  massimo 2-3×; PyPy è 4× più lento (copie via pickle e deepcopy).
- Il motore: ~18.800 righe (loop.py 8.454, effects.py 5.908 con 226
  effetti), 1.100 carte; 1.939 test, 28 golden, audit D1-D70.
- Macchine: Mac M1 Max (CPU 8+2 core, GPU 32 core, 64 GB), PC Ryzen 7 7800X3D
  (8 core / 16 thread) con RTX 4070 (12 GB, CUDA).

## Mazzi dello sparring (meta post-ban dell'utente)
Evelynn, Kha'Zix, Ivern, Sett, Rengar (`riftbound/data/decks/competitive_*.json`;
Rengar aggiunto il 21/11). Dieci matchup, più cinque mirror. Nomi di carte
distinti: Evelynn + Kha'Zix 35; + Rengar 51; + Ivern e Sett 83; con le
sideboard 99. Ogni misura di matchup: divisa per chi comincia.

## L'ordine (revisione esterna, 21/11)
Prima di riscrivere il motore, due prove in Python dicono a cosa servirebbe:

A. **Ricerca che gioca tutto il turno avversario, con tempo abbondante.** Per
   le mosse candidate (la mossa del bot, le migliori per Q, una fuori dalle
   prime due), in mondi condivisi: finire il nostro turno, far giocare
   davvero la risposta avversaria (tutte le sue decisioni, con un bot
   economico congelato che vede solo ciò che sa), arrivare alla nostra
   prossima decisione o alla fine; media sui mondi. Giudizio: la mossa scelta
   e quella del bot forzate su 16 mondi nuovi e comuni, giocate fino alla
   fine dagli stessi piloti congelati; G = guadagno medio per radice (0 dove
   coincidono). 128 radici per lo sviluppo, poi 400 nuove per confermare la
   variante congelata. Regola: G >= +0,02 e limite inferiore > 0. Se passa,
   il motore veloce serve a portarla a 0,4 s per mossa.
B. **Una rete senza ricerca (PPO).** Prima le decisioni al secondo di una
   rete vera che gioca entrambe le parti (encoding, inferenza, menu), poi un
   pilota di self-play (5.000 / 15.000 / 30.000 partite). Prerequisiti: due
   controllori per il self-play, codifica che copra ogni opzione legale
   (oggi `action_to_index` può dare None), scelte interne e mulligan.
   simple_trade contro simple_trade: 53 ms a partita (revisione).

Poi, se almeno una delle due mostra valore e la velocità la limita:

0. **Prototipo Rust (1-2 settimane).** Un percorso completo: copia dello stato
   e del lavoro pendente, mondi, menu, dichiarazioni, costi, reazioni,
   catena, showdown, combattimento, trigger, cleanup, inizio del turno
   seguente; poche carte che li attivano (Gold, una magia dal cestino, una
   conquista, una risposta in catena). Stesso lavoro sui due motori, un core.
   Avanti con >= 20× sulla decisione intera; sotto 5× (dopo una correzione
   mirata) quel disegno si ferma. Confine: motore e continuazioni in Rust
   (PyO3, lotti per chiamata), strategia di ricerca in Python finché conviene.
1. **Motore veloce per le carte dei mazzi.** Prima Evelynn-Kha'Zix (35), poi
   Rengar (51), poi Ivern e Sett (83). Fedeltà: il motore Python è l'arbitro;
   tracce di decisioni ed eventi casuali, stesso menu e stato a ogni
   decisione su ~2.000 replay, nessuna differenza inspiegata; D59 e D62 tra
   le prime fixture.
2. **Ricerca sul motore veloce.** Prima la versione di A a 0,4 s; se guadagna,
   ISMCTS a più osservatori. Arena 800 coppie, >= 0,52 e limite inferiore
   > 0,50; poi traguardo 0,60.
3. **Self-play su larga scala.** 5.000 / 15.000 / 30.000 partite, 100.000+
   solo con un miglioramento ripetuto con un secondo seed di allenamento.

Regole di stop per ogni fase: quelle della revisione (in sintesi sopra).

## Avanzamento
- 21/11, prova B, prima misura (`scripts/diag/rete_veloce.py`, Linux, un
  core, rete a pesi casuali che gioca senza ricerca): 190-230 ms a partita,
  4-5 partite al secondo per core, 300-480 decisioni con scelta al secondo;
  la rete (osservazione, codifica, inferenza) è il 37-40% del tempo, ~1 ms a
  decisione. Una partita costa ~100 volte meno di una del bot a 0,4 s per
  mossa: 100.000 partite sono ore, non settimane, anche in Python.
  Da sistemare per PPO: opzioni legali senza indice nella codifica (488 su
  11.987 in una prova, 0 nell'altra) e scelte interne lasciate al baseline
  (~37 a partita: bersagli, modi, "you may").
- 21/11, prova A pronta (`scripts/diag/prova_a.py`, `scripts/prova_a.command`):
  due varianti sul gruppo di sviluppo, valutazione alla nostra decisione
  successiva (table_value) o a fine partita. In prova sulle posizioni note,
  la prima sbaglia le conquiste del turno 3 (come il tentativo del 18/11), la
  seconda ne prende 3 su 4; s3012 giusto per entrambe.
