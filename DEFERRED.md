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
- **`grant_*` verb parser fix** — `grant_assault`/`grant_shield`/`grant_keyword` are
  misparses (static keyword vs temporary grant); per-card parser cleanup, not aliases.
- **Burn Out (§431)** — empty-deck handling in `_phase_draw`. The rule text is in
  `Riftbound Core Rules v1.2.pdf` (extractable now via `uv run --with pypdf`); confirm
  §431 exactly, then implement. Changes deck/trash/points → golden regen.
- **Corpus long tail** — ~212 INERT cards outside the meta decks. Drive with
  `scripts/generate_effects.py` + new verbs/conditions; prioritize any that later
  enter a meta deck. Use `scripts/coverage_audit.py` → `COVERAGE_REPORT.md` as the
  worklist.

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
