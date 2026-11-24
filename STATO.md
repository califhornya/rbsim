# STATO

Aggiornato: 2026-11-24. Ramo di lavoro `rust` (default su GitHub; sessione su
`claude/magical-allen-m3o90h`). `main` resta fermo al 19/11.

## Sigle
- EK = Evelynn contro Kha'Zix; R/I/S = Rengar, Ivern, Sett (EKR, EKRI, EKRIS = i pool di mazzi).
- PPO = la rete allenata giocando contro sé stessa; "prior" = le sue preferenze sulle mosse.
- Bot a mano = la ricerca (MCTS: prova molte continuazioni) con una valutazione scritta a mano.
- Campione = il bot a mano guidato dai prior di `ekris_s12/ckpt_040000.pt`.
- Arena = partite a coppie (posti scambiati) per decidere se un candidato è più forte.

## Obiettivo (Matteo, 24/11)
Porting completo su Rust di carte e funzionalità del motore Python; i cinque mazzi
sono la prima tappa verificabile. Si tengono i checkpoint. Obiettivo pratico: un
avversario con cui Matteo possa giocare e allenarsi, anche con pochi mazzi.

## Decisioni prese
- (24/11, Astra/Matteo) Python congelato: regole `6427b90`, agente PPO con `f8a50e4`.
  Fine del doppio fix: un difetto nuovo si corregge una volta, in Rust (AUDIT.md,
  "The Python engine is frozen").
- Ogni run registra regole, commit, motore per matchup, liste per contenuto,
  registro carte, checkpoint (`provenienza.jsonl`). Liste EK riconosciute dal contenuto.
- Ordine: prima l'arena EK su Rust (ricerca del bot a mano + prior PPO), poi
  Rengar, Ivern, Sett con sideboard e test, poi il resto del catalogo.
- Fix di `made`: già sul ramo dei training (unito in `rust`). Per confronti sensibili
  con `PPOAgent.inner`, rivalutare i due checkpoint con la stessa versione.
- Rust identico a Python, deviazioni note comprese (D59, D62, D71); traduzione fedele.
- Confine PPO: Rust costruisce la domanda, Python forward + campionamento.

## Fatto
- Porting EK chiuso (`docs/rust/RAPPORTO_EK.md`): replay 40/40, autonome 300/300,
  PPO 251/251 bit per bit; Mac: ciclo PPO 1.000 partite 1,31 → 1,00 min.
- Training: campione promosso (arena 0,484, lim. inf. 0,470).
- 24/11: `riftbound/provenienza.py`; `ppo.py` (instradamento per contenuto,
  provenienza a ogni lancio), `arena_mazzi.py` (provenienza); AUDIT.md e RUST.md.

## In corso
Tappa A: ricerca del bot a mano in Rust per l'arena EK.
Ti permetterà: partite d'arena (e poi contro di te) più veloci a parità di forza.
Pezzi: copia e ripresa da scelta pendente (journal/segment), determinizzazione,
etichette delle opzioni, PUCT/backup best, piani di scelta, mulligan, prior PPO
calcolato su tutto il menu (forward in Python).

## Prossimi passi
1. Parità a 50 iterazioni (semi appaiati): menu, prior, visite, mossa, traccia; tempo per partita.
2. Sul Mac col campione: stessa parità; poi budget Rust ridotto contro Python a 0,4 s
   (tolleranza fissata prima, lim. inf. 0,47).
3. Rengar, Ivern, Sett (+ sideboard), con le interazioni coi mazzi già ammessi.
4. Rifiuto prima della partita di liste fuori copertura (carta/meccanica mancante).

## File principali
- `rust/rbsim-core/src/`: motore (`game.rs`, `lp_*.rs`, `effects*.rs`, `legality.rs`,
  `agents.rs`, `obs.rs`, `features.rs`, `dump.rs`, `trace.rs`).
- `rust/rbsim-py/`: estensione `riftbound_rs` (`ppo.rs` agente PPO di confine).
- `riftbound/rs/`: ponte Python (`canon.py`, `trace_py.py`, `rust_bridge.py`, `agent_rs.py`, `collect_rs.py`).
- `riftbound/ai/net_mcts.py`, `handwritten.py`, `ppo/prior_bot.py`: la ricerca da portare.
- `riftbound/provenienza.py`: provenienza delle run.
- `scripts/rust/`: verifiche e misure; `tests/rust/`: parità.
- `docs/RUST.md`, `docs/rust/`, `docs/PIANO_FORZA.md`, `docs/audit/AUDIT.md`.
- `riftbound/core/`: motore Python di riferimento (congelato).
