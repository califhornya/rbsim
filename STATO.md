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
- Traduzione fedele, funzione per funzione; sincrono a callback (Agent con `has()` =
  hasattr, Chooser); arene di id; `not_ported!` = errore identificabile.
- Confine PPO: Rust costruisce domanda (osservazione e turno del gioco reale,
  descrittori, contesto), Python (`AskPPO`) forward + campionamento + record.
- Prima integrazione = raccolta PPO (F0); `ppo.py --motore rust`: EK su Rust, altri
  matchup e bot su Python (dichiarato all'avvio). Default resta python.
- Copia di dichiarazione = loop nuovo (come `GameLoop(gs2)`); `bf.control()` muta
  lo stato: chiamato negli stessi punti (anche l'osservazione PPO).
- Sideboard EK (4 verbi) non portata: non entra in partita.

## Fatto
- F0 misure Python; F1 traccia/canon/comparatore; motore Rust (`rust/rbsim-core`).
- F2 consegna Gold (`docs/rust/CONSEGNA1.md`): D59, D59b, D62 identiche.
- F3 `docs/rust/INVENTARIO_EK.md`: 46 carte, 34 verbi, tutti quelli in partita portati.
- F4 agenti Rust random e simple_trade; partite autonome identiche.
- F5 osservazione, codifica, descrittori in Rust; PPO su Rust (`collect_rs.play`),
  esempi identici bit per bit a `collect.play`.
- F6 (`docs/rust/RAPPORTO_EK.md`): build finale, zero divergenze su replay 40/40,
  autonome 300/300, PPO 251/251; semi tenuti 900001–900040 tutti identici.
  Misure: raccolta su un core ×2,9; ciclo PPO 4 processi 10,2 → 6,5 s (×1,57),
  1.000 partite 2,7 → 1,7 min. Rust: 84% della raccolta è ora il forward torch.
- Errori Rust trovati e corretti: ordine chiavi del dump, cleanup_hidden_cards,
  copia di dichiarazione.

## In corso
Chiusura EK: manca la prova con `ckpt_020032.pt` (sul Mac:
`bash scripts/rust/confronto_mac.command <ckpt>`, oppure caricato in chat).

## Prossimi passi
1. Prova col checkpoint allenato; misure ufficiali sul Mac.
2. Decide Matteo: arena su Rust (copie con scelta pendente, `priors`, budget ridotto
   validato a posti scambiati), oppure Rengar/Ivern/Sett per il PPO multi-mazzo.
3. Ciclo PPO oltre ×1,6: aggiornamento (71%) e forward a batch 1 (fuori dal motore).

## File principali
- `rust/rbsim-core/src/`: motore (`game.rs`, `lp_*.rs` = metodi di GameLoop,
  `effects*.rs`, `legality.rs`, `agents.rs` random/simple_trade/SideChooser,
  `obs.rs` osservazione+codifica, `features.rs` descrittori, `dump.rs`, `trace.rs`).
- `rust/rbsim-py/`: estensione `riftbound_rs` (`ppo.rs` agente PPO di confine).
- `riftbound/rs/`: `canon.py`, `trace_py.py`, `rust_bridge.py`, `agent_rs.py`, `collect_rs.py`.
- `scripts/rust/`: `diff_trace.py`, `autonome.py`, `parita_ppo.py`, `consegna1.py`,
  `inventario.py`, `bench_raccolta.py`, `bench_ppo_ciclo.py`, `confronto_mac.command`.
- `tests/rust/`: parità (richiede l'estensione, non salta).
- `docs/RUST.md` (contratti, uso), `docs/rust/` (rapporti, misure, tracce).
- `riftbound/core/`: motore Python di riferimento (non si modifica).
