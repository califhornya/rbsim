# STATO

Aggiornato: 2026-11-24 (notte). Ramo di lavoro `rust` (default su GitHub; Rengar PR 43, Ivern PR 44 e
Sett PR 45 unite; pagina col campione su `claude/gifted-gauss-v0qj89`). `main` resta fermo al 19/11.

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
- (24/11, Astra/Matteo) Matteo gioca a mano contro il campione nella pagina coach (motore Python, 0,4 s
  a mossa); si tocca solo la pagina. I consigli della vecchia rete si scollegano (solo con `--net`).
- Rust identico a Python, deviazioni note comprese (D59, D62, D71); ramo non portato = NotPorted.
- Ogni tappa comprende i matchup con i mazzi già ammessi (Rengar: ER, KR, ed EK di nuovo).
- Liste riconosciute dal contenuto (`lista_sha`); perimetro Rust = `arena_rs.COPERTI` (i cinque mazzi fra loro).
- Elementi della pila con identità (`ChainItem.uid`): in Python una scelta sulla pila è l'oggetto, non l'indice.
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
- 24/11 tappa Ivern (`docs/rust/RAPPORTO_IVERN.md`, inventario `INVENTARIO_IVERN.md`): `counter_spell`, `dig`,
  abilità riflesse (`EffectSpec.from_dict`), leggenda e token Brush, `name_spell`, `ready_units`, `heal_unit`,
  Vilemaw, 4 condizioni e una quantità; pila con identità. Sviluppo: autonome 3.360/3.360 (con sideboard e
  regressione), PPO bit per bit 720/720, replay 640/640, arena 60/60, 3 posizioni mirate; `tests/rust` 74 verdi.
  Perimetro: `COPERTI` con EI, KI, RI. Divergenze: scelta sulla pila per indice, dump dell'elemento scelto,
  replay senza l'effetto dell'osservazione PPO (strumento). Semi tenuti da parte 3.120/3.120 con EK/ER/KR di
  nuovo (`docs/rust/misure/tenuti_ivern_*.json`), 720 partite d'arena e 53.355 ricerche confrontate.
  Mac col campione: esempi PPO 240/240, arena col prior EI/KI/RI 60/60 (6.120 ricerche), Rust ×15 a partita.

- 25/11 tappa Sett (`docs/rust/RAPPORTO_SETT.md`, inventario `INVENTARIO_SETT.md`): costi aggiunti (Call to Glory),
  "spendi un buff" (Monastery of Hirana), `sett_save`, `this_is_mighty`, `kill_unit_or_gear`, Sett Kingpin.
  Sviluppo: autonome 3.760/3.760, PPO bit per bit 960/960, replay 640/640, arena 80/80, 3 posizioni mirate;
  `tests/rust` 97 verdi. Perimetro: `COPERTI` coi cinque mazzi fra loro. Nessuna divergenza del motore.
  Semi tenuti da parte 4.320/4.320 con gli altri sei matchup di nuovo (`docs/rust/misure/tenuti_sett_*.json`),
  640 partite d'arena e 43.103 ricerche; suite Python 1.952 verdi. Misure sul Mac col campione in `docs/rust/misure/mac_sett_*`.
- 24/11 pagina col campione (`scripts/coach.py`, `riftbound/ai/coach.py`, `coach_page.html`): avversario
  "Il campione" (`PPOPriorAgent`, `--campione`, `--budget 0.4`, rete in cache), primo nel menu se il
  checkpoint c'è; `--net` facoltativo (senza: niente consigli né esempi, l'abbandono passa e il campione
  chiude a 0,01 s); `games.jsonl` scrive sempre il risultato. Lanciatori `allenatore.command` (Mac) e
  `allenatore.bat` con `--extra rl` (il campione anche da `../rbsim/runs/`). Immagini: copia locale, se no
  Piltover Archive in cache (`riftbound/ai/card_images.py`, stessa cartella degli scenari), campi
  raddrizzati in orizzontale; chi inizia nel mulligan, nel turno e nel registro. `tests/test_coach.py` 19 verdi, suite Python 1.955; pagina provata con Playwright.

## In corso
- Pagina col campione pronta per la PR verso `rust`; Matteo la prova sul Mac.

## Prossimi passi
1. Arene EK su Rust a 0,030 s (`arena_mazzi.py --motore rust --budget-candidato 0.03
   --budget-avversario 0.03`); budget da ricontrollare sugli altri matchup prima di usarlo lì.
2. Rete del prior in Rust o a batch (collo di bottiglia dell'arena).
3. D72 in Rust (Rengar Trophy Hunter dove ci sono solo nemici; AUDIT.md), test rosso prima.

## File principali
- `rust/rbsim-core/src/`: motore (`game.rs`, `lp_*.rs`, `effects*.rs`, `legality.rs`, `agents.rs`,
  `obs.rs`, `features.rs`, `dump.rs`, `trace.rs`); `search.rs` la ricerca dell'arena.
- `rust/rbsim-py/`: estensione `riftbound_rs` (`ppo.rs` agente PPO, `search_py.rs` prior).
- `riftbound/rs/`: ponte Python (`rust_bridge.py`, `collect_rs.py`, `arena_rs.py` con il perimetro,
  `trace_py.py`, `mazzi.py` liste con sideboard).
- `scripts/rust/`: verifiche (`autonome.py`, `diff_trace.py`, `parita_ppo.py`, `arena_parita.py`,
  `posizioni_*.py`, `tenuti_*.sh`, `inventario.py`), Mac (`rengar_mac.command`, `ivern_mac.command`, `sett_mac.command`,
  `arena_mac.command`), misure (`bench_*.py`), arena mista (`arena_mista*.py`, altra sessione).
- `tests/rust/`: test che caricano davvero l'estensione (`test_rengar.py`, `test_ivern.py`, `test_sett.py`).
- `scripts/ppo.py` (`_motore`), `scripts/diag/arena_mazzi.py` (`--motore rust`).
- Partita a mano: `scripts/coach.py` (server, `--campione`, `--budget`, `--net`), `riftbound/ai/coach.py`
  (`CoachSession`, `opponents()`), `riftbound/ai/coach_page.html`; `scripts/allenatore.command` (Mac).
- `docs/RUST.md`, `docs/rust/` (rapporti, inventari, misure), `docs/audit/AUDIT.md`.
- `riftbound/core/`: motore Python di riferimento (congelato).
