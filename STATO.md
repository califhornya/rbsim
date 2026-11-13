# STATO

Aggiornato: 2026-11-13 (coach senza rete allenata; build con `runs/` nella radice).

## Obiettivo
Motore Riftbound fedele a `docs/rules/CORE_RULES.md` e al testo stampato delle
carte, prima di qualsiasi training (precon Zed vs Shen per primi).
Documento di riferimento: `docs/audit/AUDIT.md` (l'intestazione riassume lo stato).

## Decisioni prese
- Una deviazione = un test in `tests/audit/` che gioca la situazione + un commit
  di fix (verificabile e reversibile). Eccezione: D35-D49, soli dati, un commit.
- Golden game rigenerate solo per cambi voluti, motivo per partita nel commit.
- D19-D21, D23, D26, D29, D34: scelte tecniche, motivate in AUDIT.md.
- Q1–Q4, D27 (utente): priorità §337.4; Shadow Order Disciple invariato; cap
  dei turni = pareggio; Keeper of Law conta solo le unità di chi la gioca;
  Patched Porobot è unità e gear insieme.
- Quarto passaggio per classi (~930 carte fuori dalle liste, lette le segnalate).
- (Utente, 2026-11-12) Otto mazzi non precon eliminati (con agenti Pyke e
  Diana), correzioni di carte tenute; training sui due mazzi competitive.
- L'agente random è seminato dal seed della partita (riproducibile).
- Commenti di Codex: verificati uno per uno prima di agire (i due del
  2026-11-12 erano fondati: D53 e il default di `scripts/round_robin.py`).
- Flow: costo alternativo con i soli sconti di aura; gli altri modificatori
  §356.3-4 lasciati aperti perché nessuno è nei quattro mazzi.
- Scelte nella ricerca: nodi dell'albero per opzione con chiave (tipo, carta,
  descrizione), non per indice: le copie determinizzate mostrano altre carte.
  Prior uguali tra le opzioni (con 0.75 alla baseline le visite restavano
  sulla baseline anche quando valeva meno).
- Scelte nascoste: decise quando la partita le chiede, rigiocando il tratto
  dall'ultima decisione del turno (giornale nel motore; un fork del processo
  non funziona su Windows).

## Fatto
- Passaggi 1-4: D1–D49, Q1–Q4, bug del coach (`cc3d776`). Dettagli in AUDIT.md.
- Rimozione mazzi: test spostati sui precon, 20 golden game rigenerate.
- Quinto passaggio (mazzi competitive, D50-D52, 8 golden game Kai'Sa vs
  Kennen) e sesto (righe MECHANICS.md, D53-D56 `0b877df` `5ef1d33` `e115324`
  `56ce034`; sostituzioni §367-373 e layer §475-482 giusti). Dettagli in
  AUDIT.md.
- Punto 3 (BACKLOG O3, `6ebd0e7`): la ricerca fa tutte le scelte del suo
  giocatore (`riftbound/ai/net_mcts.py`): ogni scelta dell'azione (albero),
  quelle in difesa (showdown/chain anche con solo PASS, se una sonda vede
  scelte), quelle nascoste e quelle non viste dal piano (`_Fallback`:
  rigioca il segmento per opzione, `GameLoop.journal`/`replay_segment`).
  PREDICT: carte note in cima al mazzo in Observation/encoding (zona nuova),
  determinize le lascia lì. Su 356 scelte in 8 partite Kai'Sa-Kennen: 318
  dal piano, 35 rigiocate, 3 alla baseline (prima 41% cercate).
  A/B stesso valutatore (punteggio del tavolo), 240 partite, 16 iterazioni:
  nuova 68,8% contro la vecchia (Kai'Sa 81%, Kennen 56%). Costo per
  decisione invariato. Suite verde (1792 passed: ora torch è installato).

- Coach (2026-11-13): senza `runs/competitive/net.pt` parte con una rete non
  allenata (`runs/coach/untrained_net.pt`), mosse e probabilità senza senso.
  `pyproject.toml`: pacchetti solo `riftbound*` (con `runs/` nella radice
  `uv sync` falliva: "Multiple top-level packages").

## In corso
Niente.

## Prossimi passi
Piano concordato (2026-11-12). Punti in ordine di peso per il training:
1. Banlist del 23/11: l'utente incolla l'elenco → aggiornare
   `riftbound/data/banned_cards.json`, ricontrollare i due mazzi competitive.
2. Regole: fatto. Aperti, fuori dai mazzi: Flow §356.3-4, sostituzioni di
   morte §372-373, layer §480-481 (AUDIT.md, "Left open").
3. Fatto (sopra). Approssimazioni rimaste: il replay prosegue dalla scelta
   con le carte nascoste vere (mano avversaria, mazzo sotto), un campione
   per opzione, valore alla decisione successiva.
4. **Training (BACKLOG O4), da qui si riparte**: reti vecchie non caricabili
   (`ACTION_DIM` 319, ora anche una zona in più), riallenare da zero;
   budget MCTS, LR, dimensione rete; valutare su 100+ partite. Self-play qui:
   ~5 s a partita con 10 iterazioni (1 thread). Conta la CPU, non la GPU: la
   rete (~1M parametri, una posizione per volta) è ~25% del tempo.
5. Possono aspettare: sideboard imparato, tempi per turno del match, carte
   del corpus fuori dai mazzi, costruzione del mazzo (§103).

Training sulle macchine dell'utente, run in runs/competitive: PC Windows
(Ryzen 7 7800X3D, `scripts/allena.bat`, 8 worker) o Mac M1 (`allena.command`,
4 worker, torch 2.13 vuole macOS 14+). La RTX 4070 serve a poco.

## File principali
- `docs/audit/AUDIT.md`: elenco delle deviazioni, stato, domande aperte, cosa
  non è stato controllato.
- `tests/audit/`: un test per deviazione (`test_audit_precon_rules.py`,
  `test_audit_mechanics.py`, `test_audit_card_data.py`, `test_audit_decks.py`
  terzo passaggio, `test_audit_corpus.py` quarto, helper in `audit_helpers.py`).
- `riftbound/core/loop.py`: il motore (turno, chain, showdown, combattimento).
- `riftbound/core/battlefield.py` (controllo, Hold / Conquer), `effects.py`
  (effetti), `legality.py` (azioni legali offerte agli agenti).
- `riftbound/ai/net_mcts.py`: la ricerca guidata dalla rete (albero delle
  scelte, `_Plan`, `_Fallback`); test in `tests/test_net_mcts.py`.
- `riftbound/ai/coach.py` + `scripts/coach.py`: il coach e la sua pagina;
  `scripts/allena.bat` / `allena.command`: il training con doppio clic.
- `riftbound/data/cards/all_cards.json`: dati delle carte;
  `riftbound/data/reference/piltover_archive.json`: testo stampato
  (`scripts/piltover_sync.py compare` per le differenze).
- `riftbound/data/decks/`: `precon_zed`, `precon_shen`, `competitive_kaisa`,
  `competitive_kennen` (le liste dell'utente).
- `tests/audit/test_audit_competitive.py` (quinto passaggio, D53-D55),
  `tests/audit/test_audit_mechanics_rows.py` (sesto, D56).
- `docs/MECHANICS.md`: stato di ogni meccanica (riverificato 2026-11-12).
- `tests/golden_games.json` + `tests/test_golden_games.py`: 20 partite di
  riferimento Zed vs Shen (rigenerare con `RBSIM_REGEN_GOLDEN=1`).
- `BACKLOG.md`: tutto ciò che resta prima del training.
