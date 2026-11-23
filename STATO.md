# STATO

Aggiornato: 2026-11-23 notte. Ramo `claude/peaceful-lamport-gynyab`, porting Rust;
base `6427b90` (punta di `claude/rbsim2026-boot1-results-373ku0`, il ramo dei training).

## Obiettivo
Motore Riftbound fedele a `docs/rules/CORE_RULES.md` e al testo stampato delle
carte; su quello, una rete allenata in self-play. Riferimento: `docs/audit/AUDIT.md`.
**Questo ramo**: porting del motore in Rust per tappe (mandato di Matteo del 23/11),
primo traguardo una partita Evelynn–Kha'Zix (EK) completa con un checkpoint
esistente; prove riproducibili di correttezza (tracce appaiate) e velocità.
Piano: `docs/RUST.md` (contratti, comandi), misure in `docs/rust/`.

## Decisioni prese
- Porting (23/11): Rust identico a `6427b90`, deviazioni note comprese (D59, D62,
  Switcheroo/D71): una correzione = fix Python separato + stesso cambio in Rust.
- Porting: motore Rust sincrono a callback come il Python (traduzione fedele,
  funzione per funzione); MT19937 compatibile con `random.Random`; carte dal
  `CARD_REGISTRY` esportato; confine PyO3: Rust calcola osservazione, menu e
  descrittori, Python fa forward e campionamento (`ask`, `priors`).
- Porting (F0, 23/11): prima integrazione = raccolta PPO (`docs/rust/F0_MISURE.md`):
  guadagno leggibile sul ciclo; l'arena (più ore) dopo, serve un budget ridotto
  validato in forza. Sviluppo nel container; misure ufficiali sul Mac con un lanciatore.
- Una deviazione = un test in `tests/audit/` + un commit di fix. Golden rigenerate
  solo per cambi voluti. Regole dal motore o da CORE_RULES, mai a memoria.
- Q1–Q4, D27 (utente): priorità §337.4; cap dei turni = pareggio; Keeper of Law
  solo le unità di chi la gioca; Patched Porobot unità e gear insieme.
- Competitive: Evelynn, Kha'Zix, Rengar, Ivern, Sett (Kai'Sa e Kennen bannati, fixture).
- Rete: imita il bot a mano, poi self-play (sul Mac); semi disgiunti 1.600/200/200.
- Ricerca: un nodo per opzione; scelte nascoste decise quando servono, rigiocando;
  determinize ordina il pool prima di mescolare; mano nota per identità.

## Fatto
- Audit 1-7 e 9: D1–D58, D69-D70, Q1–Q4, Q6; D66-D68 corrette (AUDIT.md).
- Bot a mano + prior PPO (ekr_s8 `ckpt_020032.pt`) promosso; Rengar, Ivern, Sett
  entrati (dettagli e arena finale: STATO del ramo dei training).
- Porting F0 (23/11): misure Python provvisorie (container Linux 4 core, pesi dal
  seme 1). PPO EK: ciclo 10,7 s (raccolta 5,3 + aggiornamento 5,2, 4 processi);
  raccolta su un core 319 ms/partita: motore 43%, rete 24%, legali 18%,
  osservazione 11%, descrittori 3% → tetto ~1,6× sul ciclo. Arena PPOPriorAgent:
  14,8 s/partita a 50 iterazioni (motore e ricerca 86%), 22,4 s a 0,4 s (96–129 it.).
- Porting F1 (in parte): `riftbound/rs/canon.py`, dump canonico (id stabili per
  carte, incarnazioni, campi; stato rng); copia = originale verificato.
- Porting F3 (in parte): coverage su 240 partite EK (self-play, contro
  simple_trade, random): loop.py 62% di 5.503 istruzioni, effects.py 28%.

## In corso
F1: traccia Python (agenti, chooser, rng registrati), comparatore alla prima
differenza; contratti in `docs/RUST.md`. Poi F2: prima consegna (D59 e D62 con
Gold, tracce Python/Rust appaiate e tempi), quindi inventario e motore EK.

## Prossimi passi
1. F2 consegna breve; F3 `docs/rust/INVENTARIO_EK.md`; F4 motore EK in Rust.
2. F5 `ppo.py --motore rust` con record identici; F6 prove EK (semi da parte
   900001–900040), `docs/rust/RAPPORTO_EK.md`, `scripts/rust/confronto_mac.command`.
3. Dopo EK (decide Matteo): arena su Rust, Rengar, Ivern, Sett.
Macchine: Mac M1 Max (training), PC Windows, server Cherry (arene).

## File principali
- `docs/rust/F0_MISURE.md`: misure di partenza e scelta; `docs/rust/misure/`: JSON.
- `scripts/rust/`: `bench_ppo_ciclo.py` (ciclo PPO), `bench_ppo_split.py` (dove va
  il tempo della raccolta), `bench_arena_fisso.py` (arena a lavoro fisso o a tempo),
  `partite_ek.py` (partite EK per coverage e tracce).
- `riftbound/rs/`: ponte Python del porting (`canon.py`).
- `docs/audit/AUDIT.md`: deviazioni; `tests/audit/` (helper: `audit_helpers.py`).
- `riftbound/core/`: il motore Python di riferimento. `loop.py` (turno, catena,
  showdown, combattimento), `effects.py` (226 handler), `legality.py`, `decisions.py`.
- `riftbound/ai/ppo/`: PPO (`agent.py` PPOAgent/PPOChooser, `features.py`,
  `collect.py`, `prior_bot.py`); `scripts/ppo.py`; `scripts/diag/arena_*.py`.
- `riftbound/data/cards/all_cards.json` + `riftbound/registry/cards_registry.py`.
- `tests/golden_games.json` + `test_golden_games.py`: 28 partite, stato finale.
