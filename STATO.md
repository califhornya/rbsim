# STATO

Aggiornato: 2026-11-17 sera (revisione esterna registrata: D59-D68 aperte; lavoro fermo).

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
- (Utente, 12/11) Otto mazzi non precon eliminati, correzioni di carte tenute.
  (17/11) Kai'Sa e Kennen bannati: i competitive sono Evelynn e Kha'Zix; i file
  vecchi restano come fixture (test, golden game).
- (Utente, 17/11) Pulizia: un solo file di stato (questo), BACKLOG solo voci aperte.
- (Utente, 17/11) Revisione esterna del motore: prima la correttezza (partita
  vera e copie della ricerca), poi la struttura. Piano v2 in
  `docs/PIANO_MOTORE.md`, non avviato: chi lo esegue e quando, da decidere.
- Agente random seminato dal seed della partita; commenti di Codex
  verificati uno per uno. Imitazione di simple_trade scartata (da neofita).
- Flow: costo alternativo con i soli sconti di aura; gli altri modificatori
  §356.3-4 lasciati aperti perché nessuno è nei quattro mazzi.
- Scelte nella ricerca: nodi per opzione con chiave (tipo, carta, descrizione),
  non per indice; prior uguali tra le opzioni.
- Scelte nascoste: decise quando la partita le chiede, rigiocando il tratto
  dall'ultima decisione del turno (giornale nel motore).
- (Utente, 13/11) La rete serve come avversario per allenarsi e per misurare
  mazzi e matchup. Tetto al training rispettato: run 4 non migliora → stop.
  Proposte in parole semplici (cosa faccio, quanto costa, cosa sapremo);
  ogni deviazione dal piano concordato detta esplicitamente.
- Training: più partite e meno esempi per partita invece di più ricerca per
  mossa: il valore ha bisogno di esiti, non di posizioni della stessa partita.

## Fatto
- Audit, passaggi 1-7: D1–D58, Q1–Q4 e Q6; dettagli in AUDIT.md.
- Ricerca (`6ebd0e7`): la ricerca fa tutte le scelte del suo giocatore;
  A/B, 240 partite: nuova 68,8% contro la vecchia. Banlist completa.
- Training: due budget di ricerca, weight decay, `backup="best"`, bersaglio
  della politica dai Q (Gumbel), `--init` (`fd01c63` e seguenti).
- Pulizia (17/11, PR #28): storico in `docs/archivio/`; tolti file morti e
  `allena.bat`/`.command` (ripartivano dal run 4).
- Revisione esterna (17/11): 7 rapporti in `docs/audit/revisione_esterna/`;
  D59-D68 in AUDIT, ottavo passaggio, ancora senza test. Verificato qui: la
  sonda sulle azioni (576 partite, totali identici), le riproduzioni, i
  conteggi, le copie (casi piccoli), Riven; la suite esegue 200/212 tipi di
  effetto. Non rifatti qui: la sonda grande sulle copie, D63.

## In corso
Niente: lavoro fermo per decisione dell'utente (17/11 sera); si rivaluta.
Training fermo dal 13/11. Esiti contro simple_trade: run 2: 0,52; run 3
(`backup="best"`): 0,80 alla 10, poi 0,72 fino alla 60 (rete 60 contro 10:
0,49 ± 0,07); run 4 (`--policy-target q`): 0,68, valore peggiorato (errore
sulle partite nuove 0,70 → 0,84). simple_trade è un bot da neofita: rete debole.

## Prossimi passi
0. Sera del 17/11: partita dal vivo su RiftAtlas, vedi `docs/bot/PARTITA_LIVE.md`
   (il motore non gioca le mosse: D59-D68 non la toccano).
1. Rivalutare (utente): se e come eseguire il piano v2. Candidato primo fix:
   fase 1, identità passo A (D66-D68): piccola, la partita vera non cambia, la
   ricerca smette di sbagliare le copie con Kha'Zix, Shadow Clone e Pyke.
2. Bot con i giudizi dell'utente come valutazione della ricerca; stop se non
   batte nettamente simple_trade o non gioca in modo sensato. Base (17/11,
   `handwritten_value.py`, 400 partite): 0,59 contro simple_trade (0,50 con
   Evelynn, 0,69 con Kha'Zix), 0,85 contro random; misurata con D59 e D66-D68.
3. Giudizi dell'utente: `docs/bot/GIUDIZI.md`. Evelynn e Kha'Zix: S6-S9 sulla
   pagina degli scenari (`scripts/scenari.bat`), S10 in chat; in attesa.
4. Script di training e diag puntano ancora a Kai'Sa/Kennen: spostarli quando
   si riallena, e rifare il lanciatore a doppio clic.
5. Possono aspettare: sideboard, tempi per turno, carte e regole fuori dai mazzi.

Macchine: PC Windows (Ryzen 7 7800X3D) o Mac M1 Max. Log: `fresh`/`|v|`, `empty_turns`.

## File principali
- `docs/audit/AUDIT.md`: deviazioni, stato, domande aperte, cosa non è stato
  controllato; `tests/audit/`: un test per deviazione; `docs/MECHANICS.md`.
- `docs/PIANO_MOTORE.md`: piano v2 (correttezza, poi struttura);
  `docs/audit/revisione_esterna/`: i rapporti della revisione (in inglese).
- `riftbound/core/`: il motore. `loop.py` (turno, chain, showdown, combattimento),
  `effects.py`, `battlefield.py` (Hold / Conquer), `legality.py` (azioni legali).
- `riftbound/ai/net_mcts.py`: la ricerca guidata dalla rete; test in
  `tests/test_net_mcts.py`. `riftbound/ai/selfplay.py` + `scripts/train_selfplay.py`.
- `riftbound/ai/coach.py` + `scripts/coach.py`: il coach e la sua pagina.
- `riftbound/ai/scenari.py` + `scripts/scenari.py`: scenari dei giudizi (mosse vere).
- `scripts/diag/`: le misure. `docs/archivio/`: storico (training del 13/11,
  BACKLOG A-G, piano v1).
- `riftbound/data/cards/all_cards.json`: dati delle carte;
  `riftbound/data/reference/piltover_archive.json`: testo stampato
  (`scripts/piltover_sync.py compare` per le differenze).
- `riftbound/data/decks/`: precon, competitive dell'utente (`scripts/deck_from_txt.py`).
- `tests/golden_games.json` + `test_golden_games.py`: 28 partite, solo stato
  finale (`RBSIM_REGEN_GOLDEN=1` per rigenerarle). `BACKLOG.md`: voci aperte.
