# STATO

Aggiornato: 2026-11-23. Ramo `claude/peaceful-lamport-gynyab`, porting Rust;
base `6427b90` (punta di `claude/rbsim2026-boot1-results-373ku0`, il ramo dei training).

## Obiettivo
Motore Riftbound fedele a `docs/rules/CORE_RULES.md` e al testo stampato delle
carte; su quello, una rete allenata in self-play. Riferimento: `docs/audit/AUDIT.md`.
**Questo ramo**: porting del motore in Rust per tappe (mandato di Matteo del 23/11),
primo traguardo una partita Evelynn–Kha'Zix (EK) completa con un checkpoint
esistente; prove riproducibili di correttezza (tracce appaiate) e velocità.

## Decisioni prese
- Rust identico a `6427b90`, deviazioni note comprese (D59, D62, Switcheroo/D71):
  una correzione = fix Python separato + stesso cambio in Rust.
- Traduzione fedele, funzione per funzione (ogni fn Rust cita la py); sincrono a
  callback (trait Agent con `has()` = hasattr, Chooser); arene di id, copie Clone;
  `not_ported!` = errore identificabile, mai inghiottito.
- MT19937 compatibile con `random.Random`; carte dal `CARD_REGISTRY` esportato
  (`rust/data/registry.json`); confine PyO3 (`riftbound_rs`): Rust calcola
  osservazione, menu, descrittori; Python fa forward e campionamento.
- Prima integrazione = raccolta PPO (`docs/rust/F0_MISURE.md`): guadagno sul ciclo
  leggibile; arena dopo (serve budget ridotto validato in forza).
- Dump Rust con chiavi nell'ordine dei campi Python (`preserve_order`): gli id
  canonici delle copie dipendono dall'ordine di prima vista.
- Sviluppo nel container; misure ufficiali sul Mac con un lanciatore unico.
- Q1–Q4, D27 (utente); competitive: Evelynn, Kha'Zix, Rengar, Ivern, Sett.

## Fatto
- F0: misure Python provvisorie (container 4 core, pesi dal seme 1). PPO EK: ciclo
  10,7 s (raccolta 5,3 + aggiornamento 5,2); raccolta un core 319 ms/partita:
  motore 43%, rete 24%, legali 18%, osservazione 11% → tetto ~1,6× sul ciclo.
  Arena: 14,8 s/partita a 50 iterazioni (motore e ricerca 86%).
- F1: traccia Python (`trace_py.py`: agenti, chooser, rng; copie mappate al gioco
  reale), dump canonico, comparatore alla prima differenza (`diff_trace.py`).
- Motore Rust (`rust/rbsim-core`, ~30 moduli): stato, setup, turno, catena,
  showdown, combattimento, legalità, costi, passivi, effetti EK, dichiarazioni
  su copia, import da stato canonico, replay e traccia.
- Replay differenziale: 20/20 partite EK self-play (semi 1000001–1000020, rete dal
  seme 1) identiche evento per evento (stato, menu, scelte, estrazioni).
- F2 prima consegna (`docs/rust/CONSEGNA1.md`): D59, D59b, D62 con Gold, tracce
  identiche; Rust riproduce D59 (Gold non eseguito, movimento chiuso nella
  finestra; pass o "kept" secondo l'impronta) e D62 (B senza priorità). Segmento
  su un core ×13,6–17,5 (2–4 ms Python, 0,1–0,3 ms Rust), senza rete.

## In corso
F4: partite autonome dai semi con agenti Rust (simple_trade, random) per
verificare il consumo di casualità senza replay; più semi e modo PPO contro
simple_trade nel replay.

## Prossimi passi
1. F3 `docs/rust/INVENTARIO_EK.md` (verbi, trigger, carte esercitate).
2. F5: osservazione/codifica/descrittori in Rust, agente PPO con `ask`/`priors`,
   `riftbound/rs/collect_rs.py`, `ppo.py --motore rust`, record identici.
3. F6: semi tenuti da parte 900001–900040, casi rari mirati, misure senza traccia,
   `docs/rust/RAPPORTO_EK.md`, `scripts/rust/confronto_mac.command`, prova con
   `ckpt_020032.pt` (caricato in chat o sul Mac).
4. Dopo EK (decide Matteo): arena su Rust, Rengar, Ivern, Sett.

## File principali
- `rust/rbsim-core/src/`: motore (`game.rs`, `lp_*.rs` = metodi di GameLoop,
  `effects*.rs`, `legality.rs`, `dump.rs`, `import.rs`, `trace.rs`, `rng.rs`).
- `rust/rbsim-py/`: estensione `riftbound_rs` (`maturin develop --release`).
- `rust/PORTING_NOTE.md`: convenzioni del porting.
- `riftbound/rs/`: `canon.py`, `trace_py.py`, `export_registry.py`, `rust_bridge.py`.
- `scripts/rust/`: `diff_trace.py` (replay differenziale), `consegna1.py` (D59/D62),
  `bench_ppo_*.py`, `bench_arena_fisso.py`, `partite_ek.py`, `copertura_funzioni.py`.
- `tests/rust/`: parità (richiede l'estensione, non salta).
- `docs/rust/`: `F0_MISURE.md`, `CONSEGNA1.md`, `consegna1/` (tracce), `misure/`.
- `riftbound/core/`: motore Python di riferimento (non si modifica).
- `docs/audit/AUDIT.md`: deviazioni; `tests/audit/audit_helpers.py`.
