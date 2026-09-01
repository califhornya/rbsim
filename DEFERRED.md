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
Still to build, in order:
1. **Tensor encoding** of `Observation` + a canonical fixed action space (what the
   network reads/writes). Today `obs` is the structured `Observation`.
2. **Policy + value network** mapping encoded state → (action policy, value).
3. **Network-guided MCTS** (PUCT) — reuse the tree machinery from `ismcts_agent.py`.
4. **Self-play + training loop** — generate games, train on outcomes, iterate. This
   is where the agent finally *improves every game*.
5. **True self-play driver** — both seats sharing the learning policy (a
   two-controller driver; the current env is single-agent-vs-fixed).
- Also fold the battlefield choice and mulligan into the learned decision space so
  the agent learns those (the user's original examples: mulligan Nocturne, open the
  right battlefield).
