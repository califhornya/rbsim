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
- 21/11, prova A sul Mac (sviluppo, 128 radici):
  - alla decisione successiva: sceglie diversamente dal bot in 36; **G =
    +0,007 ± 0,012** (-0,005 - +0,019); meglio A in 9, il bot in 6.
  - a fine partita: diversamente in 27; **G = +0,006 ± 0,013** (-0,007 -
    +0,019); meglio A in 11, il bot in 6.
  Per la regola si chiude (limite superiore sotto +0,02): guardare tutto il
  turno avversario, anche con 5-30 volte il tempo, sposta poco, sempre nello
  stesso verso (come le sorelle del passo 2: +0,008 per radice).
- 21/11, prova B sul Mac (un core): 120 ms a partita, 8,4 partite/s, 579
  decisioni con scelta al secondo; la rete 0,41 ms a decisione (24%). Opzioni
  senza indice: 654 su 23.423 (2,8%); scelte interne al baseline: 39,7 a
  partita. Con 8 core ~65 partite/s: 100.000 partite in meno di mezz'ora di
  simulazione.

## Decisione (21/11)
Per la regola della revisione (il port si finanzia se una delle due prove
mostra valore e la velocità la frena): A non mostra un valore misurabile, B
non è frenata dalla velocità. **Rust rimandato; prossima strada: una rete che
impara giocando contro sé stessa (PPO), in Python.** Prima: ogni opzione
legale indicabile dalla rete, le scelte interne (bersagli, modi, "puoi",
mulligan) decise dalla rete, due controllori per il self-play; poi pilota a
5.000 / 15.000 / 30.000 partite con arene contro avversari congelati e
contro il bot a mano.

## Il pilota PPO (21/11, disegno della revisione esterna)
- `riftbound/ai/ppo/`: `features.py` (ogni domanda e ogni opzione descritte:
  mosse del turno, reazioni, showdown, mulligan come un menu di sottoinsiemi,
  ogni GameLoop.choose: bersagli, "you may", ordini, destinazioni, trigger,
  gear...), `model.py` (lo stato come la rete attuale, un punteggio per ogni
  opzione, softmax sul menu, valore dal lato di chi decide), `agent.py` (la
  rete decide ogni scelta vera; le dichiarazioni sulla copia contano una
  volta; lo stato è sempre quello reale), `collect.py` (due agenti, una
  traiettoria per posto, ricompensa finale, GAE gamma 1 lambda 0,98),
  `train.py` (PPO). L'osservazione ora ha la catena in ordine e le carte
  avversarie note in mano.
- Copertura sui cinque mazzi (50 partite): 26.853 opzioni, nessuna senza
  descrizione, nessuna domanda sconosciuta; le euristiche danno solo il
  suggerimento iniziale, decide la rete. Test: `tests/test_ppo.py` (copertura,
  rapporto PPO 1 prima del primo aggiornamento, segno dei ritorni, nessuna
  dipendenza dall'ordine delle carte nascoste).
- `scripts/ppo.py` / `scripts/ppo.command`: aggiornamenti da 64 partite (prima
  tutte contro se stessa, poi 80% / 20% contro le ultime versioni salvate),
  misure ogni 1.000 partite a scelta deterministica; regola alle tappe 5.000
  / 15.000 / 30.000: batte la rete iniziale (>= 0,52, limite inferiore > 0,50)
  e fa meglio di lei contro simple_trade. La rete iniziale (pesi casuali) fa
  ~0,13 contro simple_trade: il segnale che conta è quella misura, poi il bot
  a mano.
- 21/11, prima tappa sul Mac (`runs/ppo1`, 8 processi, **7 minuti**): contro
  simple_trade 0,065 (iniziale) -> 0,425 (1.024 partite) -> 0,515 -> 0,595
  -> 0,535 -> **0,665** (5.056); contro la rete iniziale 0,910 ± 0,028. Per
  la regola della tappa 5.000 impara (la riga non era stampata: le partite
  vanno a blocchi di 64, corretto). Per confronto, il bot a mano fa 0,80
  contro simple_trade. Arena contro il bot a mano: `scripts/arena_ppo.command`.
- 21/11, fino a 30.016 partite (36 min): contro simple_trade 0,72 a 7.000,
  poi piatta (0,63-0,75; 0,680 a 15.040, 0,705 a 30.016); contro la rete
  iniziale 0,99 (ancora satura: non misura più). Regola alle tappe 15.000 e
  30.000: impara (come scritta; ma un'ancora satura non distingue i
  progressi). **Contro il bot a mano: 0,425 ± 0,044** (0,381-0,469), senza
  nessuna ricerca; Evelynn che comincia 0,71 (il bot contro se stesso 0,92),
  Evelynn con Kha'Zix che comincia 0,33 (0,45), Kha'Zix con Evelynn che
  comincia 0,12 (0,08), Kha'Zix che comincia 0,54 (0,55).
- 22/11, preparate: incroci tra checkpoint 5.000 / 15.000 / 30.000
  (`scripts/diag/incroci_ppo.py`) e il bot a mano con i prior della rete PPO
  (`riftbound/ai/ppo/prior_bot.py`, arena contro il bot a mano):
  `scripts/dopo_ppo.command`.
- 22/11, sul Mac:
  - incroci (200 coppie): 15.040 contro 5.056 **0,552 ± 0,041** (0,512-0,593);
    30.016 contro 5.056 0,532 ± 0,039 (0,494-0,571); 30.016 contro 15.040
    **0,453 ± 0,038** (0,415-0,490). Migliora fino a ~15.000 partite, poi
    peggiora: la ricetta va corretta prima di allenare di più.
  - **il bot a mano con i prior della rete PPO (checkpoint 30.016) contro il
    bot a mano: 0,540 ± 0,027** (0,513-0,567, 400 coppie): **PROMOSSO**, la
    prima prova che supera la regola. Evelynn che comincia 0,880, Evelynn con
    Kha'Zix che comincia 0,525, Kha'Zix con Evelynn che comincia 0,145,
    Kha'Zix che comincia 0,610; iterazioni 169 contro 182; turni passati
    subito 0,7% contro 1,8%.
- 22/11, secondo giro della revisione: il campione di sparring resta il bot
  con prior 30.016 (sha256 f4f6ec4f...); il 15.040 (27eeb548...) riferimento
  della rete pura. Difetto trovato: contro l'archivio chi impara cominciava
  sempre (posto per parità dell'indice, chi comincia per parità del seed,
  coincidenti con blocchi da 64). Il calo 30.016 contro 15.040 si replica
  (0,4575 su 200 nuove aperture); l'entropia media non crolla (0,695 contro
  0,699), la mossa migliore cambia nel 52,6% dei menu.
  Fatto: `scripts/ppo.py` con assegnazione bilanciata (e la vecchia per
  confronto), --seme, --archivio recenti/misto, pannello per tappa (ancore
  congelate, simple_trade, bot a mano ogni 5.000), tappe.jsonl con KL, clip,
  entropia per famiglia di menu; arena tra due bot con prior PPO
  (`arena_bot.py --avversario prior_ppo`, impronte dei pesi).
  Notte (`scripts/notte_ricetta.command`): sfida 15.040 contro 30.016 (400
  coppie, seed 16000-16399, la solita regola); ricetta bilanciata contro
  vecchia, semi 1 e 2, 20.000 partite; incroci finali.
- 22/11, la notte (Mac):
  - sfida prior 15.040 contro prior 30.016: **0,512 ± 0,025** (0,487-0,538):
    non promosso, il campione resta il 30.016.
  - ricetta, 20.000 partite, 39 minuti ciascuna; celle contro l'archivio:
    bilanciata ~900 ciascuna, vecchia solo Aa e Bb (il difetto). Incroci
    finali: bilanciata contro vecchia **0,698** col seme 1, **0,470** col
    seme 2 (0,442-0,498); bilanciata s2 contro bilanciata s1 0,383: la
    varianza tra semi è grande. Pannello (media delle ancore del pilota):
    tutte le corse oscillano di ~0,1 tra tappe e finiscono tra 0,42 e 0,53;
    picchi a metà corsa (bilanciata s2 0,589 a 14.000, poi 0,432). Allarme
    bot a mano (32 coppie, +-0,10): bilanciata s1 0,484 e 0,516; le altre
    0,28-0,44.
  - Lettura: la correzione è giusta ma il suo effetto non si vede in modo
    stabile; il problema che domina è l'instabilità dell'allenamento (lr
    costante). Si confrontano ora le corse sulla media delle ultime tappe
    (`scripts/diag/riassunto_ppo.py`), non sulla sola rete finale.
  - Seconda notte (`scripts/notte_ricetta2.command`): controllo (bilanciata)
    contro nuova (bilanciata + lr da 3e-4 a 1e-4 + archivio misto), semi 3 e
    4. Deviazione detta: due cambi insieme (la revisione li proponeva uno
    alla volta), per non spendere due notti; se la nuova vince, si separano.
- 22/11, seconda notte (Mac, 20.000 partite per corsa): media del pannello
  dalle 14.000 partite: controllo s3 0,517, nuova s3 0,513; controllo s4
  0,512, nuova s4 0,555. Incroci finali: nuova contro controllo 0,623 (s3),
  0,490 (s4). **La regola non è soddisfatta: la nuova ricetta non diventa
  standard.** La varianza tra semi resta più grande degli effetti cercati;
  tutte le ricette finiscono intorno a 0,50-0,55 contro le ancore del pilota.
  La rete finale migliore fra le otto corse è nuova s3 (pannello 0,594 alla
  fine, in salita; batte le altre tre di questa notte negli incroci; allarme
  bot a mano 0,531 e 0,594, 32 coppie +-0,10).
- 22/11, terzo giro della revisione: chiusa la messa a punto di PPO su
  Evelynn-Kha'Zix (la bilanciata resta il controllo; niente corse corte con
  eliminazione: nuova s3 era 7ª-8ª fino a 16.000 e 1ª a 20.032). La
  selezione tra otto con una sola conferma su seed nuovi è corretta (arena
  s3 contro il campione, 400 coppie, seed 17000-17399, sha256 932c1d83...).
  Distillazione: la revisione ha interrogato due volte il maestro su 64
  radici: cambia la mossa dello studente in 33, le due ricerche concordano
  in 62; copiare solo la prima mossa: G = +0,0039 (-0,0176 - +0,0234).
  Pilota (`scripts/distilla.py`, `scripts/distilla.command`): margine del
  maestro sullo studente (200 coppie); 2.000 + 400 radici etichettate (mossa
  e scelte interne del piano del maestro, menu dinamico PPO); due studenti
  (solo mossa / mossa + interne) contro la partenza; stesso budget PPO
  (5.000 partite, seme 5) a studenti e controllo; incroci. Regola fissata
  prima: 10.000 radici se il maestro batte lo studente e uno studente dopo
  il PPO batte il controllo (>= 0,52, limite inferiore > 0,50). Rengar dopo,
  in un ramo separato (50/25/25).
- 22/11, arena prior nuova s3 contro prior 30.016: **0,501 ± 0,023**
  (0,479-0,524): non promosso, il campione resta il 30.016. Una rete pura un
  po' migliore non rende migliore il bot che la usa come guida.
- 22/11, pilota di distillazione (Mac, ~1 ora):
  - margine del maestro: bot con prior 30.016 contro la rete 30.016 da sola
    **0,698 ± 0,041** (0,656-0,739, 200 coppie): c'è molto da imparare.
  - accordo col maestro sullo sviluppo (400 radici): partenza 0,468 (mosse),
    0,372 (scelte interne); studente "mossa" 0,655 / 0,427; studente
    "interne" 0,637 / 0,561. L'imitazione funziona.
  - subito dopo, contro la partenza: mossa 0,475 (0,437-0,513), interne
    0,497 (0,461-0,534); interne contro mossa 0,560 (0,523-0,597).
  - dopo lo stesso PPO (5.000 partite, seme 5): mossa contro controllo
    0,485; **interne contro controllo 0,535 ± 0,040 (0,495-0,575)**; interne
    contro mossa 0,507.
  - Regola: margine sì, studente dopo il PPO no (limite inferiore 0,495):
    **non si sale a 10.000 radici.** Copiare le scelte del maestro alza
    l'accordo ma non la forza della rete da sola; con anche bersagli e modi va
    meglio che con la sola mossa (0,560), al limite della soglia dopo il PPO.
- 22/11, quarto giro della revisione: i due checkpoint finali del seme 5 su
  600 aperture nuove (8.510.000-8.510.599): interne + PPO contro controllo
  **0,546** (0,522-0,570; 0,548 se comincia Evelynn, 0,543 se Kha'Zix).
  Bersaglio visite contro azione (stesse etichette): 0,499 (0,472-0,526); le
  visite seguono spesso la preferenza della rete di partenza (151 contro 55
  radici). Prior dello studente "interne" contro prior 30.016 nella ricerca,
  effetto locale su 96 radici: 0,000 (-0,012 - +0,013): niente arena.
  Richiesta: replica col seme PPO 6 (`scripts/replica_s6.command`): due
  reti, 5.056 partite, da studente_interne.pt e da ckpt_030016.pt; 600
  coppie senza ricerca, seed 8.600.000-8.600.599; regola >= 0,52 e limite
  inferiore > 0,50. Poi, se serve: distillazione di turni interi giocati dal
  maestro (prima la misura a/b/c sul margine del resto del turno; al
  massimo 2.000 chiamate di ricerca); il raccoglitore registra la
  provenienza dell'etichetta (piano, ripiego, default) e il contesto "made".
  Poi, nell'ordine della revisione: archivio misto (10% recenti, 10%
  vecchi), decadimento del lr; distillazione della ricerca (10.000 radici,
  maestro il bot con prior 30.016); valore PPO alle foglie (prova G, miscela
  0,8 / 0,2, non sul PASS di fine turno); Rengar (50% Evelynn-Kha'Zix, 25% e
  25% con Rengar), poi Ivern e Sett.
- 22/11, replica col seme 6: interne + PPO contro controllo **0,428 ±
  0,024** (0,404-0,453; 0,500 se comincia Evelynn, 0,357 se Kha'Zix). Non si
  replica, anzi va al contrario: **la prova di distillazione si chiude.**
  Su questa scala, come per le ricette, l'effetto del seme supera quello
  cercato. Il campione resta il bot con prior 30.016; prossimo: Rengar.
- 22/11, ramo a tre mazzi (`scripts/ppo.py --mazzi ekr`,
  `scripts/rengar.command`): ciclo fisso di 4 partite (EK, EK, ER, KR), chi
  comincia alternato entro il matchup; contro l'archivio le quattro celle
  posto x chi comincia bilanciate entro il matchup. Quattro reti da
  ckpt_030016, 20.032 partite, semi 7 e 8: `ekr` e il controllo `ek`.
  Pannello su EK, ER, KR (simple_trade per mazzo, coppie contro 30.016).
  Verifica (`scripts/diag/verifica_mazzi.py`, aperture 9.000.000+): EK 2.000
  coppie, ER e KR 1.000, contro la partenza; regole fissate prima: Rengar
  entra se su ER e KR insieme >= 0,52, limite inferiore > 0,50 e differenza
  col controllo con limite inferiore > 0; EK tiene se la differenza appaiata
  ha limite inferiore > -0,03. Riferimenti della revisione (30.016 contro
  simple_trade, 100 coppie): con Kha'Zix contro Rengar 0,26, con Rengar
  contro Kha'Zix 0,70.
- 22/11, ramo a tre mazzi, risultati (Mac; verifica 20 min, 39.200 partite):
  contro la partenza 30.016, prova (ekr) / controllo (ek):
  Evelynn-Kha'Zix 0,585 / 0,560, differenza **+0,025** (+0,013 - +0,038);
  Evelynn-Rengar 0,601 / 0,473, **+0,128**; Kha'Zix-Rengar 0,622 / 0,496,
  **+0,126**; Rengar insieme 0,612 (lim. inf. 0,602), +0,127 (+0,114 -
  +0,140). Per seme: +0,103 (s7) e +0,150 (s8) su Rengar, +0,043 e +0,008 su
  EK. Testa a testa ekr contro ek: EK 0,568 / 0,500, ER 0,598 / 0,602, KR
  0,621 / 0,690. **Rengar entra: SÌ; Evelynn-Kha'Zix tiene: SÌ** (anzi
  migliora). Il primo effetto che si replica sui due semi. Cella più debole:
  la rete con Kha'Zix contro Rengar di simple_trade, 0,22 → 0,37 (s7) e
  0,42 (s8); con Rengar contro Kha'Zix 0,79-0,87.
  Prossimo: arena sui tre matchup (`scripts/diag/arena_mazzi.py`,
  `scripts/arena_rengar.command`): bot a mano con prior ekr_s8 (media più
  alta nella verifica, 0,613 contro 0,593) contro il campione (prior
  30.016), 600 coppie EK, 400 ER, 400 KR, seed 30.000/31.000/32.000; regole
  fissate prima: Rengar (ER e KR) >= 0,52 e lim. inf. > 0,50, EK lim. inf.
  > 0,47; entrambe -> promosso. Poi Ivern.
- 23/11, arena sui tre matchup (156 min): bot con prior ekr_s8 contro il
  campione (prior 30.016): Evelynn-Kha'Zix **0,515 ± 0,022** (0,493-0,537),
  Evelynn-Rengar 0,544 ± 0,029, Kha'Zix-Rengar 0,539 ± 0,028; Rengar insieme
  **0,541 ± 0,020** (0,521-0,561). **PROMOSSO**: il campione è il bot a mano
  con i prior di `runs/rengar/ekr_s8/corrente.pt` (sha256 24807b53fdc49e49).
  Prossimo: Ivern (miscela a quattro mazzi da decidere con la revisione).
- 23/11, quinto giro della revisione (Ivern, poi Sett): Ivern adesso, da
  `runs/rengar/ekr_s8/ckpt_020032.pt`, semi 9 e 10, 30.016 partite; prova
  `--mazzi ekri` (ciclo di 24: 6 EK, 3 ER, 3 KR, 4 EI, 4 KI, 4 RI, Ivern in
  B; 5.000 partite per matchup nuovo, come Rengar), controllo `ekr`. Pannello
  sui sei matchup contro ekr_s8. Verifica (`verifica_mazzi.py`, generale:
  --vecchi / --nuovi, ancora obbligatoria) sui checkpoint finali (scelta
  fissata prima), contro ekr_s8, 1.000 coppie per matchup, seed da
  10.000.000; regole: Ivern entra se la media a pesi uguali di EI, KI, RI fa
  >= 0,52, limite inferiore > 0,50, e Δ sul controllo limite inferiore > 0;
  i vecchi tengono se Δ ha limite inferiore > -0,03 su **ciascuno** di EK,
  ER, KR (un buco su un solo matchup conta per lo sparring). Semi riportati
  anche uno per uno. Partenza di ekr_s8 contro simple_trade (revisione, 200
  aperture): la rete con Ivern / con l'altro mazzo: EI 0,525 / 0,540, KI
  0,605 / 0,310, RI 0,335 / 0,365. Poi Sett dal checkpoint a quattro mazzi
  (controllo: quattro mazzi dalla stessa partenza); ekr_s8 resta il
  campione fino a un'arena finale sui dieci matchup (blocchi Ivern e Sett
  separati, >= 0,52 e lim. inf. > 0,50 ciascuno; ogni vecchio lim. inf. >
  0,47; coppie fissate prima per la tolleranza: ~800 per vecchio, ±0,02).
  `scripts/ivern.command`.
- 23/11, Ivern, risultati (Mac; quattro corse da 42-46 min, verifica 26 min,
  57.600 partite), contro ekr_s8, prova (ekri) / controllo (ekr):
  nuovi a pesi uguali **0,712 / 0,468, Δ +0,244** (+0,233 - +0,254; s9
  +0,236, s10 +0,252): EI +0,236, KI +0,239, RI +0,256. **Ivern entra.**
  Vecchi, Δ: EK -0,006 (lim. inf. -0,023), ER +0,009 (-0,010), KR +0,006
  (-0,013): **tengono tutti e tre**; semi discordi su tutti e tre, ampio su
  KR (s9 +0,052, s10 -0,041 ± 0,027). Testa a testa EK ekri_s10 contro
  ekr_s10 0,439 ± 0,031. Il guadagno viene soprattutto dalla rete che
  pilota Ivern (il controllo con Ivern 0,07-0,37 contro l'ancora); con
  l'altro mazzo contro l'Ivern dell'ancora prova e controllo quasi uguali
  (0,6-0,9 entrambi). Contro simple_trade, la rete con Kha'Zix contro Ivern
  resta debole (0,38 / 0,24 s9, 0,52 / 0,40 s10; partenza 0,31). Rispetto a
  ekr_s8, EK non sale (prova 0,484, controllo 0,490): continuare da ekr_s8
  non migliora EK, su nessuna delle due miscele.
  Partenza per Sett: **ekri_s10/ckpt_030016** (sopra ekri_s9 contro l'ancora
  in tutti e sei i matchup; media 0,638 contro 0,594). Sett (`--mazzi
  ekris`, `scripts/sett.command`): metà la miscela ekri, un ottavo ciascuno
  ES, KS, RS, IS (Sett in B), 40.000 partite (5.000 per matchup nuovo, come
  Rengar e Ivern), semi 11 e 12, controllo ekri; pannello solo a 0, 20.000 e
  alla fine (`--pannello-ogni`, il pannello a dieci matchup costa ~3.400
  partite). Verifica contro ekri_s10, 1.000 coppie per matchup, seed da
  13.000.000; Sett entra se la media a pesi uguali di ES, KS, RS, IS fa >=
  0,52, lim. inf. > 0,50, Δ lim. inf. > 0; i sei vecchi tengono ciascuno
  con Δ lim. inf. > -0,03. Poi l'arena finale contro ekr_s8.
- 23/11, Sett, risultati (Mac; corse da 54-58 min, verifica 40 min, 88.000
  partite), contro ekri_s10: nuovi a pesi uguali **0,621 / 0,459, Δ
  +0,162** (+0,152 - +0,171; s11 +0,117, s12 +0,207): ES +0,122, KS +0,142,
  RS +0,178, IS +0,204. **Sett entra.** Vecchi, Δ (lim. inf.): EK +0,002
  (-0,016), ER +0,021 (+0,002), KR +0,028 (+0,008), **EI -0,032 (-0,051)**,
  KI +0,056 (+0,038), RI +0,061 (+0,041): EI non certificato (l'IC
  attraversa -0,03), gli altri cinque tengono. Semi discordi su tutti e sei
  i vecchi, di molto: s11 da -0,04 a -0,165 (EI), s12 da +0,06 a +0,175.
  Contro la partenza, media sui dieci matchup: ekris_s11 0,546, ekris_s12
  0,568, ekri_s11 0,541, **ekri_s12 0,417** (sotto la partenza in tutti e
  dieci, anche nei quattro con Sett che non allena). Una corsa da 40.000
  partite può perdere ~8 punti ovunque: la varianza tra corse domina i Δ per
  seme. ekris_s12 è sopra la partenza in tutti e dieci (vecchi 0,505-0,587,
  EI 0,587). Deviazione dalla regola (EI): si va all'arena finale con
  ekris_s12 (media più alta, criterio dei passi precedenti), perché la
  perdita sul checkpoint intermedio, misurata sulla rete scelta, non c'è.
  Arena finale (`scripts/arena_finale.command`, ~8 ore, riprende se
  interrotta): bot con prior ekris_s12/ckpt_040000 contro il campione
  (prior ekr_s8/ckpt_020032); 800 coppie EK, ER, KR; 300 per EI, KI, RI;
  250 per ES, KS, RS, IS; seed da 40.000 + 1.000 x indice; regole: ciascuno
  dei tre storici lim. inf. > 0,47; blocco Ivern e blocco Sett a pesi
  uguali >= 0,52 e lim. inf. > 0,50; tutte -> promosso.
- 23/11, sesto giro della revisione:
  - **Difetto in `scripts/ppo.py`** (trovato dalla revisione, patch sua):
    la cache delle reti nei processi indicizzava ancore e archivio col solo
    nome (`ckpt_030016`): un'ancora esterna e un checkpoint della corsa con
    lo stesso nome si scambiavano i pesi, nel pannello o come avversario
    d'archivio, secondo l'ordine delle chiamate. Coinvolti: tutte le corse
    con le ancore del pilota (ckpt_005056, 015040, 030016 di runs/ppo1:
    ricette, distillazione, Rengar), Ivern (ckpt_020032), Sett
    (ckpt_020032, 030016). Pannello EI del controllo s11 a 40.000: 0,672
    nel log, 0,539 rigiocato. **Non coinvolti**: verifiche
    (`verifica_mazzi.py`), incroci, arene (caricano per percorso): le
    promozioni e le regole decise restano. Corretto con chiavi distinte
    (rete in allenamento, archivio, candidato del pannello, ancore; ancore
    omonime per percorso) e tre test.
  - Sett: la regola sui vecchi resta fallita su EI (Δ -0,032, -0,051 -
    -0,012). Candidato fissato ora: ekris_s12/ckpt_040000. Arena in due
    fasi (`scripts/arena_finale.command`): A) EI con ricerca contro il bot
    con prior ekri_s10, 800 coppie, seed 53.000+, passa se lim. inf. >
    0,47, altrimenti il campione resta ekr_s8; B) se A passa, le 4.300
    coppie contro ekr_s8 già fissate. ~9 ore e mezza.
  - Instabilità: sul controllo s12 il pannello rigiocato sceglie la tappa
    25.024; su 640 aperture nuove 0,492 contro 0,420 della finale, +0,072
    (+0,040 - +0,104). Per le prossime corse: misurare ogni 5.000 partite
    dalla 20.000 (64-128 coppie per matchup contro un'ancora esplicita,
    stesse aperture, rapporto per vecchio matchup), la partenza tra le
    opzioni, criterio di scelta fissato prima, stesso diritto a prova e
    controllo, soglie formali solo nella verifica su aperture nuove. Primo
    esperimento: lr 1e-4 costante contro 3e-4 costante, semi appaiati, un
    solo parametro cambiato. KL e clip registrati a ogni aggiornamento
    (`aggiornamenti.jsonl`) prima di decidere uno stop sulla KL.
