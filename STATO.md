# STATO

Aggiornato: 2026-11-24 (pomeriggio). Ramo di lavoro `rust` (default su GitHub; sessione su
`claude/magical-allen-m3o90h`). `main` resta fermo al 19/11.

## Sigle
- EK = Evelynn contro Kha'Zix; R/I/S = Rengar, Ivern, Sett (EKR, EKRI, EKRIS = i pool di mazzi).
- PPO = la rete allenata giocando contro sé stessa; "prior" = le sue preferenze sulle mosse.
- Bot a mano = la ricerca (MCTS: prova molte continuazioni) con una valutazione scritta a mano.
- Campione = il bot a mano guidato dai prior di `ekris_s12/ckpt_040000.pt`.
- Arena = partite a coppie (posti scambiati) per decidere se un candidato è più forte.
- Lavoro fisso = numero fisso di iterazioni per decisione (invece di un tempo).

## Obiettivo (Matteo, 24/11)
Porting completo su Rust di carte e funzionalità del motore Python; i cinque mazzi
sono la prima tappa verificabile. Si tengono i checkpoint. Obiettivo pratico: un
avversario con cui Matteo possa giocare e allenarsi, anche con pochi mazzi.

## Decisioni prese
- (24/11, Astra/Matteo) Python congelato: regole `6427b90`, agente PPO con `f8a50e4`.
  Fine del doppio fix: un difetto nuovo si corregge una volta, in Rust (AUDIT.md).
- Ogni run registra regole, commit, motore per matchup, liste per contenuto,
  registro carte, checkpoint (`provenienza.jsonl`). Liste EK riconosciute dal contenuto.
- Ordine: prima l'arena EK su Rust, poi Rengar, Ivern, Sett con sideboard e test,
  poi il resto del catalogo.
- Fix di `made`: già sul ramo dei training (unito in `rust`).
- Rust identico a Python, deviazioni note comprese (D59, D62, D71).
- Confine PPO e prior: Rust costruisce la domanda, Python forward (+ campionamento o softmax).
- Etichette delle scelte che in Python sono un `repr`: in Rust un testo diverso con la stessa
  uguaglianza (carte per `uuid`). Si confrontano forma e numeri dell'albero, non il testo.
- Chiavi di ripresa dell'arena: checkpoint (hash), budget, motore, regole (non il commit).

## Fatto
- Porting EK del motore (`docs/rust/RAPPORTO_EK.md`).
- 24/11 tappa 1: provenienza delle run, procedura dei difetti.
- 24/11 tappa A (`docs/rust/RAPPORTO_ARENA.md`): ricerca dell'arena in Rust (`search.rs`).
  Parità a 50 iterazioni: bot a mano 40/40 + 10/10 tenuti da parte, bot col prior
  (rete casuale) 20/20 + 10/10; ogni ricerca identica (menu, prior, visite, Q, mossa).
  Tempo per partita col prior: Python 11–12 s, Rust 1,3–1,4 s (×8,5); senza prior ×28.
  Su Rust il 63% è il forward della rete (batch 1, Python).
- Mac (M1 Max, campione `ekris_s12/ckpt_040000.pt`): parità 20/20 a 50 iterazioni; tempo per
  partita a lavoro fisso Python 8,6–8,8 s, Rust 0,61 s (×14,6). Tappa A verificata.
- `arena_mazzi.py --motore rust`, `arena_rs.game`, `tests/rust/test_arena_rs.py`.

## In corso
- Prova di forza a budget ridotto (Astra, 24/11): arena mista a passo comune, Rust 0,030 s
  contro Python 0,400 s, 800 coppie, semi 70000–70799, promosso se lim. inf. > 0,47
  (`bash scripts/rust/arena_mista.command` sul Mac, 2-3 ore).
- Rengar nel motore Rust (in parallelo, come dice Astra).

- Divergenza del seme 70113 spiegata: chiavi della ricerca Python dipendenti dall'ordine di un
  insieme (indirizzi di memoria); correzione minima in `net_mcts._label` (regola del congelamento),
  Rust già deterministico. Rilancio dell'arena con `--spiegata 70113:A` (riprende).
- Divergenze successive gestite dall'arena: quelle solo nelle ricerche si rigiocano a fine arena
  coi conteggi registrati (identiche ora = spiegate, `.spiegate.json`); quelle di partita si
  rigiocano al rilancio; solo quelle che restano vanno guardate.

## Decisioni prese il 24/11 pomeriggio
- Budget: metodo (a) di Astra; verifica esatta con due copie a passo comune (niente import
  di posizioni); l'importatore completo seguirà le esigenze dei test.

## Prossimi passi
1. Esito della prova mista; se promosso, arene EK su Rust a 0,030 s (`arena_mazzi.py --motore rust
   --budget-candidato 0.03 --budget-avversario 0.03`).
2. Rengar, Ivern, Sett (+ sideboard) nel motore Rust, con i test di ciascun mazzo; budget da
   ricontrollare sui nuovi matchup.
3. Rete del prior in Rust o a batch (ora è il collo di bottiglia dell'arena).
4. Partita interattiva contro il bot su Rust (oggi il coach usa Python).

## File principali
- `rust/rbsim-core/src/`: motore (`game.rs`, `lp_*.rs`, `effects*.rs`, `legality.rs`,
  `agents.rs`, `obs.rs`, `features.rs`, `dump.rs`, `trace.rs`); `search.rs` la ricerca dell'arena.
- `rust/rbsim-py/`: estensione `riftbound_rs` (`ppo.rs` agente PPO, `search_py.rs` prior).
- `riftbound/rs/`: ponte Python (`rust_bridge.py`, `collect_rs.py`, `arena_rs.py`, `trace_py.py`).
- `riftbound/provenienza.py`: provenienza delle run.
- `scripts/rust/arena_mista.py`: arena mista a passo comune (Python contro Rust).
- `scripts/rust/`: verifiche (`arena_parita.py`, `diff_trace.py`, `autonome.py`, `parita_ppo.py`)
  e misure (`bench_arena_fisso.py`, `bench_ppo_ciclo.py`, `arena_mac.command`).
- `scripts/diag/arena_mazzi.py`: l'arena (`--motore rust`).
- `docs/RUST.md`, `docs/rust/`, `docs/PIANO_FORZA.md`, `docs/audit/AUDIT.md`.
- `riftbound/core/`: motore Python di riferimento (congelato).
