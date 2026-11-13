# STATO

Aggiornato: 2026-11-13 (ban del 13/11 registrate; i due mazzi competitive da rifare).

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
- L'agente random è seminato dal seed della partita (riproducibile).
- Commenti di Codex: verificati uno per uno prima di agire.
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
- Quinto passaggio (mazzi competitive, D50-D52, 8 golden game Kai'Sa vs
  Kennen) e sesto (righe MECHANICS.md, D53-D56 `0b877df` `5ef1d33` `e115324`
  `56ce034`; sostituzioni §367-373 e layer §475-482 giusti). Dettagli in
  AUDIT.md.
- Punto 3 (BACKLOG O3, `6ebd0e7`): la ricerca fa tutte le scelte del suo
  giocatore (albero, difesa, nascoste, `_Fallback`); PREDICT nell'encoding.
  A/B con lo stesso valutatore, 240 partite: nuova 68,8% contro la vecchia.
- Ban del 13/11 in `banned_cards.json`; avviso anche per campi e campione.
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
1. Proposto all'utente, in attesa di risposta: un bot con i suoi giudizi
   (cosa vale cosa, cosa temere da ogni mazzo) come valutazione della
   ricerca che c'è. Prima versione: un'ora con l'utente sui due mazzi; stop
   se non batte nettamente simple_trade o non gioca in modo sensato per lui.
2. Giudizi dell'utente da situazioni concrete: `docs/bot/GIUDIZI.md` (primo gruppo fatto).
3. Ban del 13/11 (effettive dal 23/11) in `banned_cards.json`; i mazzi si
   caricano ancora, con un avviso. Toccano Kai'Sa (3 Brynhir Thundersong) e
   Kennen (3 Nocturne Horrifying, 3 Rhasa the Sunderer): in attesa delle
   sostituzioni dell'utente. GIUDIZI.md (G1, G4, G6, S1) usa queste carte:
   da rivedere. Manca la lista di settembre (12 carte, qui solo 2).
4. Possono aspettare: sideboard, tempi per turno, carte fuori dai mazzi,
   costruzione del mazzo (§103), regole aperte fuori dai mazzi (AUDIT.md).

Macchine: PC Windows (Ryzen 7 7800X3D) o Mac M1 Max; conta la CPU. Nel log:
`fresh`/`|v|` (valore sulle partite nuove), `empty_turns` (turni a vuoto).

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
- `docs/history/SESSIONE_2026-11-13.md`: il primo training nel dettaglio; `scripts/diag/`: le misure.
- `riftbound/data/cards/all_cards.json`: dati delle carte;
  `riftbound/data/reference/piltover_archive.json`: testo stampato
  (`scripts/piltover_sync.py compare` per le differenze).
- `riftbound/data/decks/`: i due precon e i due competitive dell'utente.
- `tests/golden_games.json` + `test_golden_games.py`: 20 partite Zed vs Shen
  (`RBSIM_REGEN_GOLDEN=1` per rigenerarle); `BACKLOG.md`: quel che resta.
