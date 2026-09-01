# Deferred — what's parked, to pick up in the future

Snapshot of everything intentionally left behind as of the Stage 0.5 + RL-env-
skeleton milestone. Grouped by area; engine items cross-reference `KNOWN_ISSUES.md`.
Nothing here is a blocker for what's already shipped — these are the next chunks.

## Meta-deck cards still INERT (3)
- **Diana Scorn of the Moon** (legend) & **Ornn Fire Below the Mountain** (legend) —
  activated resource abilities with an **earmark**: energy usable only during
  showdowns / power usable only for gear. Needs a restricted-resource sub-system
  (a separate pool checked at each spend site). A loose "just add the resource"
  version would be a rules deviation, so it's deferred rather than done wrong.
- **Diana Lunari** (champion) — "when a showdown begins here, may pay [1] → PREDICT,
  reveal top, draw if a spell." Needs a new `on_showdown_begin` trigger + a
  reveal-top-draw-if-spell verb. It sits on the **golden diana champion**, so it
  forces a golden regen (and, like Tideturner did, may surface further latent bugs
  — do it carefully).

## Engine mechanics (KNOWN_ISSUES)
- **`aura:reduce_cost` primitive** — the engine applies `reduce_cost`/`cost_modifier`
  only to the card being played (self-cost, `loop.py:878`); it has no AURA form that
  reduces the cost of *other* cards while a source is in play. So cards like Eager
  Apprentice ("spells you play cost [1] less"), Herald of Scales, Vex, Marai Spire,
  Ornn's Forge, Helm of Suppression, Applied Researchers, Stargazer are silently
  **inert** (safe — they just don't grant the discount; NOT a correctness landmine).
  Eager Apprentice sits in the golden Diana deck, so this is a fidelity gap there.
  Fix = an aura pass at cost-computation time that scans in-play sources; then re-parse
  these cards to the aura form. Also enables `aura:reduce_cost` from suggested_vocab.
- **FLOW play-from-trash + banish** (#19b) — trash is now populated; still needs the
  from-trash play action + banish-after-resolve.
- **EMPOWERED-modifier / on-become-empowered / on_burn** (#20) — mostly non-meta
  corpus cards; value-swap in `_amount`, a trigger after `player.burn`.
- **`enters_exhausted`** (#21) — units that enter exhausted (e.g. Patched Porobot's
  reminder) currently enter ready.
- **AMBUSH nested showdown** (#22) — an AMBUSH deploy into a contested lane sets the
  contested flags but doesn't itself spawn a nested showdown.
- **HIDDEN nuances** (#23) — champion-zone hiding (Pyke); from-Hidden targeting
  restriction (on-play effects lane-restricted).
- [DONE] **`grant_*` verb misparses** — fixed the 5 cards: Blood Rush → LIVE
  (`give_temporary_assault`), Gem Jammer → LIVE (`give_keyword` GANKING; permanent
  vs "this turn" is a minor documented approximation), and 3 static-keyword misparses
  (Laurent Duelist, Rengar Pouncing, Needlessly Large Yordle) had their spurious
  grant effect removed (the ASSAULT/SHIELD is a printed static keyword). Result:
  **0 engine-fixable INERT remain** — every remaining INERT card is empty-effects.
- **Burn Out (§431)** — empty-deck handling in `_phase_draw`. The rule text is in
  `Riftbound Core Rules v1.2.pdf` (extractable now via `uv run --with pypdf`); confirm
  §431 exactly, then implement. Changes deck/trash/points → golden regen.

- **Corpus long tail — the bottleneck is engine PRIMITIVES, not the parser model.**
  A Sonnet-5 parse pass (`--only-empty`, commit `29da7bb`) took the corpus from
  672 → **706 LIVE / 176 INERT** (+34 cards). It flagged **188** cards to
  `scripts/review_needed.txt`; **168 of those are still empty** because they need
  verbs the engine does not yet have. This is the key finding: re-parsing the
  failures with a stronger model (e.g. Opus) will NOT help — the model is
  constrained to the allowed vocab, so it flags the same cards. The lever is
  **adding the missing primitives, then re-parsing the cards that need them.**
  Highest-leverage missing primitives (live counts from `scripts/suggested_vocab.txt`):
  `effect:gain_power_any_domain` (10), `effect:mode_choice` (9, modal "choose one"),
  `cost_gated_trigger` (4), `aura:reduce_cost` (3), `effect:play_to_open_battlefield`
  (3), `effect:reveal_top_n_banish_play` (3), then a long one-off tail. Each new
  primitive = engine_vocab entry + handler/condition + a targeted re-parse of the
  cards that need it (a primitive alone flips nothing until those cards are re-parsed).
  Turnkey for a future parse (needs `ANTHROPIC_API_KEY`; not available in dev/CI):
  ```
  export ANTHROPIC_API_KEY=...            # required by generate_effects.py
  RBSIM_PARSER_MODEL=claude-sonnet-5 \
    uv run python scripts/generate_effects.py --retry-review   # reprocess flagged
  uv run python scripts/coverage_audit.py      # re-measure; eyeball COVERAGE_REPORT.md
  RBSIM_REGEN_GOLDEN=1 uv run pytest tests/test_golden_games.py -q  # if gameplay changed
  uv run pytest -q                             # must stay green
  ```
  Note on cost/model: Sonnet-5 parsed the ~209-card empty tail for ≈ $2.3. A full
  Opus pass on the same set is ~5× (≈ $9+), and the evidence above says it buys
  little — reserve Opus (if ever) for a small, curated set of cards you have a
  specific reason to believe are model-misses rather than vocab gaps. Prioritize
  any card that enters a meta deck.
- **Meta INERT (2 left, need subsystems):** Diana Scorn / Ornn legends (earmarked-
  resource: energy only in showdowns / power only for gear) and Diana Lunari
  (showdown-begin predict/draw on the golden champion → golden regen).

## Stage 0.5 (match layer)
- **Strategic / searched battlefield selection.** `play_match` has a pluggable
  `bf_chooser`; today it just takes the first available. Making the pre-game choice
  a learned/searched decision is future work (and ties into the RL env's action space).
- **Sideboarding** between games (fixed in/out per matchup — user will supply lists
  like decklists). Decks are static in `play_match` today.
- **Full §458 pre-game protocol** (reveal/pick order). We model the competitive
  essentials: one battlefield per player per game, no reuse, loser-chooses-first.

## Stage 1+ (the RL environment → self-play)
`riftbound/ai/env.py` (`RiftboundEnv`) is a working gym-style single-agent env over
the real engine (reset/step/legal_actions/observation/reward vs a fixed opponent).
Progress:
1. [DONE] **Tensor encoding** — `riftbound/ai/encoding.py` (OBS_DIM=3884 state vector
   + ACTION_DIM=113 canonical action space + legal mask + mulligan head).
2. [DONE] **Policy + value network** — `riftbound/ai/net.py` (PyTorch dual-head MLP,
   CUDA-aware, masked policy, checkpoint save/load; tests in `tests/test_net.py` are
   torch-gated and run after `uv sync --extra rl`).

3. [DONE] **Network-guided MCTS** (PUCT) — `riftbound/ai/net_mcts.py`
   (`NetGuidedMCTSAgent`): net priors steer selection, net value evaluates leaves
   (no rollout), most-visited root action chosen; exposes `last_visits` (the policy
   target for training). torch-gated tests in `tests/test_net_mcts.py`.

4. [DONE] **Self-play + training loop** — `riftbound/ai/selfplay.py` +
   `scripts/train_selfplay.py`: guided-MCTS self-play on both seats records
   (state, visit policy, mask, outcome z); train_step = policy cross-entropy +
   value MSE; `run_training` iterates generate→train→checkpoint (CUDA-aware,
   headless). Verified end-to-end (loss decreases across iterations).

Still to build / tune:
5. **Scale + tune the training** on a rented GPU box (more games/iters/MCTS sims,
   LR schedule, larger net, eval vs. baselines). This is the "run it big" phase.
6. **True self-play refinements** — Dirichlet exploration noise at the root,
   temperature schedule for move selection, and (optionally) a two-controller
   driver. The current loop already self-plays (both seats = the net's MCTS).
7. [DONE] **Learned mulligan + battlefield** — both are now net-value-guided (they
   use the trained net, so they improve as it learns):
   - `NetGuidedMCTSAgent.decide_mulligan` scores every keep/return combo by the net's
     value on a determinized opening and keeps the best (→ "mulligan Nocturne" once
     the net learns it's a dead card).
   - `riftbound/ai/pregame.py` scores each battlefield the deck can bring by the net's
     opening value; `make_net_bf_chooser` plugs into `match.play_match`.
   Refinement (deferred): a stronger battlefield signal from a few net-guided games
   per candidate rather than the static opening value.
- Also fold the battlefield choice and mulligan into the learned decision space so
  the agent learns those (the user's original examples: mulligan Nocturne, open the
  right battlefield).
