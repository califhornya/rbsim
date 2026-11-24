# STATO

Aggiornato: 2026-11-24 (sera). Ramo di lavoro `rust` (default su GitHub; tappa Rengar unita, PR 43;
tappa Ivern su `claude/vibrant-johnson-k8ovzv`). `main` resta fermo al 19/11.

## Sigle
- EK = Evelynn contro Kha'Zix; R/I/S = Rengar, Ivern, Sett (EKR, EKRI, EKRIS = i pool di mazzi).
- PPO = la rete allenata giocando contro sé stessa; "prior" = le sue preferenze sulle mosse.
- Bot a mano = la ricerca (MCTS: prova molte continuazioni) con una valutazione scritta a mano.
- Campione = il bot a mano guidato dai prior di `ekris_s12/ckpt_040000.pt`.
- Arena = partite a coppie (posti scambiati) per decidere se un candidato è più forte.
- Lavoro fisso = numero fisso di iterazioni per decisione (invece di un tempo).
- Lettera minuscola nei matchup degli script (`Er`) = la lista con tutta la sideboard nel mazzo.

## Obiettivo (Matteo, 24/11)
Porting completo su Rust di carte e funzionalità del motore Python; i cinque mazzi
sono la prima tappa verificabile (ordine Rengar, Ivern, Sett, ciascuno con sideboard e test).
Obiettivo pratico: un avversario con cui Matteo possa giocare e allenarsi, anche con pochi mazzi.

## Decisioni prese
- (24/11, Astra/Matteo) Python congelato: regole `6427b90`, agente PPO con `f8a50e4`.
  Un difetto nuovo si corregge una volta, in Rust (AUDIT.md).
- Rust identico a Python, deviazioni note comprese (D59, D62, D71); ramo non portato = NotPorted.
- Ogni tappa comprende i matchup con i mazzi già ammessi (Rengar: ER, KR, ed EK di nuovo).
- Liste riconosciute dal contenuto (`lista_sha`); perimetro Rust = `arena_rs.COPERTI` (EK, ER, KR).
- Sideboard provata con liste variate (`riftbound/rs/mazzi.py`): il training non fa sideboarding.
- Confine PPO e prior: Rust costruisce la domanda, Python forward (+ campionamento o softmax).
- Etichette dei `repr` Python: in Rust testo diverso con la stessa uguaglianza (carte per `uuid`).
- Chiavi di ripresa dell'arena: checkpoint (hash), budget, motore, regole (non il commit).
- Budget (metodo (a) di Astra): verifica esatta con due copie a passo comune, niente import di posizioni.
- Divergenze dell'arena mista: quelle solo nelle ricerche si rigiocano coi conteggi registrati
  (identiche = spiegate); quelle di partita al rilancio; si guardano solo quelle che restano.

## Fatto
- Porting EK (`docs/rust/RAPPORTO_EK.md`); ricerca dell'arena in Rust (`docs/rust/RAPPORTO_ARENA.md`),
  verificata sul Mac col campione (20/20 a 50 iterazioni; Rust ×14,6 a partita).
- 24/11 prova di forza (arena mista a passo comune, Mac, 800 coppie, semi 70000–70799): bot Rust a
  0,030 s contro Python a 0,400 s = 0,4938 ± 0,0158, lim. inf. 0,4780 > 0,47: **PROMOSSO 0,030 s per EK**.
  1.600 partite verificate; 2 divergenze nelle ricerche spiegate (etichette Python dipendenti
  dall'ordine di un insieme, corrette in `net_mcts._label`). Partita Rust a 0,03 s: 2,36 s.
- 24/11 tappa Rengar (`docs/rust/RAPPORTO_RENGAR.md`): verbi `ready_unit`, `blink_unit`, `deal_damage`,
  `kill_gear`; tre condizioni e una quantità; `_kicker_paid`/`_showed_off` a tre stati (assente, None, bool).
  Parità ER/KR/EK nei due posti: autonome, replay, PPO bit per bit, arena (mano e prior), 7 posizioni mirate;
  semi tenuti da parte 2.000/2.000 (`docs/rust/misure/tenuti_rengar_*.json`); zero divergenze inspiegate, nessun
  NotPorted. Suite Python 1.952 verdi, `tests/rust` 49 verdi. Inventario `docs/rust/INVENTARIO_RENGAR.md`.
  Mac col campione: esempi PPO 240/240, arena col prior ER/KR 40/40 (3.030 ricerche), Rust ×14–16 a partita.
- Perimetro esteso: `arena_rs.COPERTI = ("EK", "ER", "KR")`, `ppo._motore` e `arena_mazzi.py` lo seguono.
- Script di parità con `--matchup` e `--posti`; difetto dello strumento di traccia (`_to_real_any`) corretto.

## In corso
- Tappa Ivern: inventario (`inventario.py --liste I --matchup EI KI RI Ei Ki Ri`).

## Prossimi passi
1. Ivern (EI, KI, RI, mix `ekri`): porting, parità, posizioni mirate, semi tenuti da parte,
   verifica sul Mac; aggiungere a `arena_rs.COPERTI`. Poi Sett.
2. Arene EK su Rust a 0,030 s (`arena_mazzi.py --motore rust --budget-candidato 0.03
   --budget-avversario 0.03`); budget da ricontrollare su ER/KR prima di usarlo lì.
3. Rete del prior in Rust o a batch (collo di bottiglia dell'arena); partita interattiva su Rust.

## File principali
- `rust/rbsim-core/src/`: motore (`game.rs`, `lp_*.rs`, `effects*.rs`, `legality.rs`, `agents.rs`,
  `obs.rs`, `features.rs`, `dump.rs`, `trace.rs`); `search.rs` la ricerca dell'arena.
- `rust/rbsim-py/`: estensione `riftbound_rs` (`ppo.rs` agente PPO, `search_py.rs` prior).
- `riftbound/rs/`: ponte Python (`rust_bridge.py`, `collect_rs.py`, `arena_rs.py` con il perimetro,
  `trace_py.py`, `mazzi.py` liste con sideboard).
- `scripts/rust/`: verifiche (`autonome.py`, `diff_trace.py`, `parita_ppo.py`, `arena_parita.py`,
  `posizioni_rengar.py`, `tenuti_rengar.sh`, `inventario.py`), Mac (`rengar_mac.command`,
  `arena_mac.command`), misure (`bench_*.py`), arena mista (`arena_mista*.py`, altra sessione).
- `tests/rust/`: test che caricano davvero l'estensione (`test_rengar.py` per Rengar).
- `scripts/ppo.py` (`_motore`), `scripts/diag/arena_mazzi.py` (`--motore rust`).
- `docs/RUST.md`, `docs/rust/` (rapporti, inventari, misure), `docs/audit/AUDIT.md`.
- `riftbound/core/`: motore Python di riferimento (congelato).
