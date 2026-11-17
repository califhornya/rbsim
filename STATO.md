# STATO

Aggiornato: 2026-11-17 (PR #26 su main; base del bot misurata sui mazzi nuovi).

## Obiettivo
Motore Riftbound fedele a `docs/rules/CORE_RULES.md` e al testo stampato delle
carte; su quello, una rete allenata in self-play sui due mazzi competitive.
Documento di riferimento: `docs/audit/AUDIT.md` (l'intestazione riassume lo stato).

## Decisioni prese
- Una deviazione = un test in `tests/audit/` che gioca la situazione + un commit
  di fix (verificabile e reversibile). Eccezione: D35-D49, soli dati, un commit.
- Golden game rigenerate solo per cambi voluti, motivo per partita nel commit.
  D19-D21, D23, D26, D29, D34: scelte tecniche, motivate in AUDIT.md.
- Q1–Q4, D27 (utente): priorità §337.4; Shadow Order Disciple invariato; cap
  dei turni = pareggio; Keeper of Law conta solo le unità di chi la gioca;
  Patched Porobot è unità e gear insieme.
- (Utente, 2026-11-12) Otto mazzi non precon eliminati (con agenti Pyke e
  Diana), correzioni di carte tenute; training sui due mazzi competitive.
- (Utente, 17/11) Kai'Sa e Kennen non si usano più (ban): i competitive sono
  Evelynn e Kha'Zix. File vecchi tenuti come fixture (test, golden game).
- Agente random seminato dal seed della partita; commenti di Codex
  verificati uno per uno. Imitazione di simple_trade scartata (da neofita).
- Flow: costo alternativo con i soli sconti di aura; gli altri modificatori
  §356.3-4 lasciati aperti perché nessuno è nei quattro mazzi.
- Scelte nella ricerca: nodi dell'albero per opzione con chiave (tipo, carta,
  descrizione), non per indice: le copie determinizzate mostrano altre carte.
  Prior uguali tra le opzioni (con 0.75 alla baseline le visite restavano
  sulla baseline anche quando valeva meno).
- Scelte nascoste: decise quando la partita le chiede, rigiocando il tratto
  dall'ultima decisione del turno (giornale nel motore; un fork del processo
  non funziona su Windows).
- (Utente, 13/11) La rete serve come avversario per allenarsi e per misurare
  mazzi e matchup. Tetto al training rispettato: run 4 non migliora → stop.
  Proposte in parole semplici (cosa faccio, quanto costa, cosa sapremo);
  ogni deviazione dal piano concordato detta esplicitamente.
- Training: si parte senza aspettare il BACKLOG vuoto (di fatto, 2026-11-12).
  Più partite e meno esempi per partita invece di più ricerca per mossa: il
  valore ha bisogno di esiti, non di posizioni della stessa partita.

## Fatto
- Passaggi 1-4: D1–D49, Q1–Q4, bug del coach (`cc3d776`). Dettagli in AUDIT.md.
- Quinto passaggio (Kai'Sa, Kennen: D50-D52) e sesto (righe MECHANICS.md,
  D53-D56). Dettagli in AUDIT.md.
- Punto 3 (BACKLOG O3, `6ebd0e7`): la ricerca fa tutte le scelte del suo
  giocatore (albero, difesa, nascoste, `_Fallback`); PREDICT nell'encoding.
  A/B con lo stesso valutatore, 240 partite: nuova 68,8% contro la vecchia.
- Banlist completa (marzo-novembre). Settimo passaggio (Evelynn, Kha'Zix):
  D57-D58, 480 partite sotto gli invarianti; Q6 (utente): gear da nascosta = giocata lì.
- Training: due budget di ricerca in self-play, weight decay, misure nuove
  nel log (`fd01c63`); ricerca `backup="best"`; bersaglio della politica dai
  Q (Gumbel "completed Q", costanti di mctx) e `--init` per partire da una rete.

## In corso
Training (O4) fermo per decisione (13/11). Esiti contro simple_trade:
- Run 1 (ricetta originale): la rete imparava a passare, da buttare.
- Run 2 (ricetta nuova, ricerca vecchia): 0,52.
- Run 3 (`backup="best"`): 0,80 alla 10, poi fermo (0,72 fino alla 60);
  rete 60 contro rete 10 (`scripts/diag/net_vs_net.py`): 0,49 ± 0,07.
- Run 4 (`--policy-target q`, 30 iterazioni dalla rete 60 del run 3): 0,68,
  valore peggiorato (errore sulle partite nuove 0,70 → 0,84). Il log basta,
  confronto testa a testa non fatto.
simple_trade è un bot da neofita: 0,72 contro di lui = rete debole.
`allena.command` punta ancora al run 4: non rilanciarlo.

## Prossimi passi
1. Bot con i giudizi dell'utente come valutazione della ricerca che c'è; stop
   se non batte nettamente simple_trade o non gioca in modo sensato per lui.
   Base (17/11, `handwritten_value.py`, 400 partite): 0,59 contro simple_trade
   (0,50 se gioca Evelynn, 0,69 Kha'Zix), 0,85 contro random.
0. Sera del 17/11: partita dal vivo su RiftAtlas con l'utente (Evelynn contro
   un amico): leggere `docs/bot/PARTITA_LIVE.md`.
2. Giudizi dell'utente: `docs/bot/GIUDIZI.md`. Evelynn e Kha'Zix: S6-S9 sulla
   pagina degli scenari (`scripts/scenari.bat`), S10 in chat; in attesa.
3. Script di training e diag puntano ancora a Kai'Sa/Kennen: spostarli su
   Evelynn/Kha'Zix solo quando si riallena (consiglio: non prima del bot).
4. Possono aspettare: sideboard, tempi per turno, carte e regole fuori dai mazzi.

Macchine: PC Windows (Ryzen 7 7800X3D) o Mac M1 Max. Log: `fresh`/`|v|`, `empty_turns`.

## File principali
- `docs/audit/AUDIT.md`: deviazioni, stato, domande aperte, cosa non è stato
  controllato; `tests/audit/`: un test per deviazione (un file per passaggio,
  helper in `audit_helpers.py`); `docs/MECHANICS.md`: le meccaniche.
- `riftbound/core/loop.py`: il motore (turno, chain, showdown, combattimento).
- `riftbound/core/`: `battlefield.py` (controllo, Hold / Conquer),
  `effects.py` (effetti), `legality.py` (azioni legali offerte agli agenti).
- `riftbound/ai/net_mcts.py`: la ricerca guidata dalla rete (albero delle
  scelte, `_Plan`, `_Fallback`); test in `tests/test_net_mcts.py`.
- `riftbound/ai/selfplay.py` + `scripts/train_selfplay.py`: self-play e
  training; `scripts/allena.bat` / `allena.command`: lo stesso con doppio clic.
- `riftbound/ai/coach.py` + `scripts/coach.py`: il coach e la sua pagina.
- `riftbound/ai/scenari.py` + `scripts/scenari.py`: scenari dei giudizi (mosse vere).
- `docs/history/SESSIONE_2026-11-13.md`: il primo training nel dettaglio; `scripts/diag/`: le misure.
- `riftbound/data/cards/all_cards.json`: dati delle carte;
  `riftbound/data/reference/piltover_archive.json`: testo stampato
  (`scripts/piltover_sync.py compare` per le differenze).
- `riftbound/data/decks/`: precon, competitive dell'utente (`scripts/deck_from_txt.py`).
- `tests/golden_games.json` + `test_golden_games.py`: 20 partite Zed vs Shen
  (`RBSIM_REGEN_GOLDEN=1` per rigenerarle); `BACKLOG.md`: quel che resta.
