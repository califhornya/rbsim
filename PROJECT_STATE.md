# State of the Project & What Comes Next

_Last updated: 2026-08-31 · branch `claude/handoff-60239e`_

This document is the single honest snapshot of where the Riftbound simulator
stands, what was built recently, and the road to the real goal: a **self-play
learning environment** where an agent teaches itself to pilot each deck (mulligan
Nocturne every time, open the right battlefield, play the correct on-play vs.
on-draw line) by playing millions of games against itself.

> **Stage 0 progress (this session).** A coverage audit tool now measures exactly
> which cards the engine models (`scripts/coverage_audit.py` → `COVERAGE_REPORT.md`).
> Corpus: **669 LIVE / 213 INERT / 48 VANILLA** (was 660 / 222 / 48). Across the
> **8 meta decks: 6 of 8 decks are now fully modeled**, with only **4 distinct
> INERT cards left**. Shipped this session: spells→trash (#19a), two on-play
> conditions, three battlefield rule-modifiers (Void Gate / Heisho Shell /
> Sandswept Tomb), the optional-effect ("you may") seam, Nocturne's top-of-deck
> banish+play, **AMBUSH** (reaction-speed champion deploy), the **HIDDEN** keyword
> (hide / play-from-hidden / cleanup), **Switcheroo** (might-swap), and **Star
> Spring** (first-unit-here retreat). ~200 tests; golden green throughout.
>
> **Tideturner is now LIVE** — the blocking bug (KNOWN_ISSUES #24: UnitInPlay value
> equality causing wrong-duplicate removal / card loss) was root-caused and fixed by
> making UnitInPlay identity-equal, which also hardened every `in`/`remove` unit site
> in the engine against silent card loss.
>
> **Remaining 3 meta INERT cards** (all niche, deferred): **Diana Scorn** & **Ornn**
> legends — need an earmarked-resource sub-system (energy only in showdowns / power
> only for gear); a loose version would deviate from the rules. **Diana Lunari** — a
> showdown-begin predict/draw ability on the golden diana champion. Card-by-card work
> has hit strong diminishing returns; the highest-leverage next step is Stage 0.5 /
> the RL env.

---

## 1. The goal, stated plainly

The end state is an **AlphaZero-style self-play RL environment** for Riftbound:
a neural network that improves every game and ends up "knowing" deck-specific
strategy — not because anyone coded that strategy, but because it learned it by
winning and losing.

Everything built so far is foundation for that. It is not the goal itself.

### The one hard truth to keep in view

A self-play agent learns to win **the simulation it is trained in**. If the engine
is incomplete or wrong, the agent learns to exploit the bugs, not to play
Riftbound. So **engine completeness and correctness is the gate** — it must come
before any serious training. This is the single most important thing in this
document.

---

## 2. What we have now (done and pushed)

### Engine & rules
- **Resumable game loop.** `GameLoop.start()` was decomposed into `_setup()`,
  `_play_all_turns()`, `_begin_turn()`, `_run_main_actions()`, `_end_turn()`,
  `_final_result()`, plus `resume_to_completion()`. A game can now be continued
  from an arbitrary mid-turn state — the primitive every rollout/search needs.
  The normal path stays byte-identical (golden fixture is the oracle).
- **Correct mulligan (Core Rules §116–117).** Draw 4, set aside up to **two**
  cards, draw that many from the **top**, recycle the set-aside cards to the
  **bottom** (no shuffle). Lives on `Player.mulligan(...)`, shared by the engine
  and the search agents. This also fixed a pre-existing no-op mulligan bug.
- **Legends & champions in play.** Legend units are now actually placed on the
  board, so their activated abilities — crucially **EMPOWER on the legend/champion**
  — fire. (These special-zone cards were never loaded before; the meta decks lean
  on them heavily.)
- **EMPOWER / EMPOWERED and BURN** (Vendetta set). `empower_self`, `disempower`,
  `this_is_empowered` passive bonuses; `burn` + `cards_burned_this_turn`.
- **Battlefields.** Decks now carry their battlefield cards; the game uses them and
  fires their triggered abilities.
- **Robustness.** Triggered-effect handlers are wrapped in a `[EFFECT-SKIP]`
  guard so one bad effect can't crash a whole match.

### The new Vendetta set & decks
- Card corpus grew from ~763 to **932 cards** (Vendetta imported from RiftMana HTML
  via `scripts/import_cards.py merge-html`), with correct **power-pip costs**
  (a repeated domain token = that many power pips, e.g. "Order Order" = 2).
- Deck files present in `riftbound/data/decks/`: `vendetta_akali`, `vendetta_ezreal`,
  `vendetta_kennen`, `vendetta_ornn`, `vendetta_rengar` (+ the three earlier
  `calm_chaos_yasuo`, `chaos_mind_diana`, `fury_chaos_pyke`).

### Search agents (no hand-written strategy)
- **`mc` — flat Monte-Carlo** (`monte_carlo_agent.py`). At each decision it plays
  many determinized rollouts per candidate action and keeps the best; it also
  **searches the mulligan**. Beats the `simple_trade` heuristic 12/12 head-to-head.
- **`ismcts` — Information-Set MCTS** (`ismcts_agent.py`). Builds a tree over the
  turn's action sequence across determinized worlds. Beats `simple_trade` 10/10.
  **But** it only ties `mc` at ~4× the compute, so **`mc` is the practical
  opponent today.**
- Supporting pieces: `random_agent.py`, `scripts/round_robin.py` (seat-swapped
  win-rate harness), and `scripts/trace_game.py` (full decision-by-decision
  tracer — the tool for *seeing* what the agent actually does, which is how we
  validate correctness).

### Stage 0 engine-completeness work (this session)
- **Coverage audit** (`scripts/coverage_audit.py` → `COVERAGE_REPORT.md`): the map
  of LIVE/INERT/VANILLA per meta deck and corpus-wide.
- **Spells → trash** (#19a): cast spells no longer vanish (unblocks trash mechanics).
- **Two on-play conditions** (`friendly_total_might_at_least`,
  `you_control_n_or_more_gear`) → Kinkou Initiate, Patched Porobot LIVE.
- **Battlefield rule-modifiers** (data-driven markers): Void Gate (+1 damage here),
  Heisho Shell (ignore DEFLECT here), Sandswept Tomb (friendly spells cost less here).
- **Optional-effect seam**: `Agent.decide_optional` gates "you may" effects.
- **Nocturne**: top-of-deck reveal → banish → play for [rune], via the dig/predict
  hook. The canonical mulligan card is now modeled.

### Tests
- **~34 test files, 178 tests passing**, including the golden-game fixture (kept
  byte-identical except the one legitimate spells→trash regen), plus new coverage
  for the conditions, battlefield modifiers, the optional seam, and Nocturne.

---

## 3. The honest state — limits to keep in mind

- **Search is not learning.** `mc` and `ismcts` have **no memory**. They recompute
  from scratch at every decision and improve nothing between games. They cannot
  "know" to open Zaun Warrens or to always mulligan Nocturne — they re-derive a
  noisy answer each time, and only for decisions the engine models correctly.
- **Battlefield selection is still random and unsearched.** The opening battlefield
  is picked by a seeded coin flip, not chosen strategically.
- **Card coverage is much improved but not complete.** Corpus **216 INERT** of 932;
  across the meta decks only **9 INERT** remain (5 of 8 decks fully modeled). The
  remaining meta INERT cards need bigger, un-scaffolded mechanics:
  - **HIDDEN** (44 corpus cards; Tideturner, Switcheroo) — a hidden-zone alt-play
    ("hide now for [rune], react later for [0]"). No scaffolding yet.
  - **AMBUSH** (14 corpus cards; Rengar Trophy Hunter) — reaction-timing deploy.
  - **Showdown/gear-restricted resource abilities** (Diana Scorn, Ornn legend) —
    need "earmarked energy" tracking to avoid a rules deviation.
  - **Star Spring** — needs a per-BF "first unit here this turn" trigger.
- **Deferred mechanics** (tracked in `KNOWN_ISSUES.md`):
  - **FLOW play-from-trash** (#19b) — trash is now populated (#19a done); still
    needs the from-trash play + banish action.
  - **EMPOWERED-modifier / on-become-empowered / on-burn** (#20) — mostly non-meta
    corpus cards.
  - **Burn Out** (§431) — not implemented; gated on reading §431 from the rulebook.
  - `enters_exhausted` (#21).
- **Search is still not learning; battlefield selection still random; no Bo3/sideboards.**

Net: meta-deck card fidelity is now high, but the win-rate numbers are **still not
trustworthy as meta reads** — the piloting is memoryless (search, not learning) and
battlefield selection is a coin flip. That is Stage 0.5 / the RL stages, not card work.

---

## 4. What to do next — the roadmap

Ordered. Stage 0 is the gate; do not skip ahead to training on a broken engine.

### Stage 0 — Engine completeness & correctness (the gate) ⬅ in progress
The prerequisite for everything. Until the simulation *is* Riftbound, a learner
learns the wrong game. **Meta-deck fidelity is now high (9 INERT left).** The
remaining meta cards are the big mechanics: **HIDDEN** and **AMBUSH** (each its
own focused build — no scaffolding today), showdown-restricted resources, and
Star Spring. Then the corpus long tail via the parser.
1. **Finish card effects coverage.** Drive the inert/misparsed fraction toward
   zero; verify with `trace_game.py` on real games, not aggregate win-rates.
   (Nocturne — the canonical example — is now modeled.)
2. **Implement the deferred mechanics:** FLOW (route cast spells to trash first —
   this changes trash counts, so regenerate the golden fixture and eyeball the
   diff), EMPOWERED-modifiers, on-burn triggers, **Burn Out**, battlefield
   passives, token anthems.
3. **Fix the open bugs** in `KNOWN_ISSUES.md`.
4. **Validation discipline:** read full game traces; keep the golden fixture green
   (regenerate only for legitimate gameplay changes).

### Stage 0.5 — Match structure (can run in parallel with Stage 0)
- **Bo3 match harness** (default Bo3), with the §458 battlefield rules
  (Match = players choose, no reuse).
- **Searched battlefield selection** — make the opening battlefield a real,
  searchable/learnable decision instead of a coin flip.
- **Sideboarding** — apply fixed in/out swaps per matchup for games 2 and 3
  (user will supply sideboards like decklists).

### Stage 1 — RL environment API
Wrap the resumable engine in a clean, gym-style step interface:
`reset() → observation`, `step(action) → observation, reward, done`, with
`legal_actions()` exposed. The primitives (`clone`, `determinize`,
`legal_actions`, resumable loop) already exist — this is the packaging.

### Stage 2 — State & action encoding
Fixed-size tensor encodings of the game state (hands, board, runes, points,
battlefields, empower status) and a canonical action space. This is what the
network reads and writes.

### Stage 3 — Policy + value network
A network that maps an encoded state to (policy over actions, value estimate).
Start small; correctness of the encoding matters more than size.

### Stage 4 — Network-guided MCTS
Replace the flat rollouts in the MCTS with network-guided search (PUCT), the
AlphaZero search core. Much of the tree machinery from `ismcts_agent.py` carries
over.

### Stage 5 — Self-play + training loop
Generate games by self-play, train the network on the outcomes, iterate. **This is
where the agent finally starts to _improve every game_** and to learn deck-specific
strategy (mulligan Nocturne, open the right battlefield, the correct on-play line).

---

## 5. Quick reference

- **Branch:** `claude/handoff-60239e` (working tree clean, level with origin).
- **Run tests:** `uv run pytest -q`
- **Trace a game (how to _see_ decisions):** `scripts/trace_game.py`
- **Head-to-head win rates:** `scripts/round_robin.py --agent ...`
- **Import cards:** `scripts/import_cards.py merge-html ...`
- **Deck from decklist:** `scripts/deck_from_txt.py ...`
- **Known bugs & deferred mechanics:** `KNOWN_ISSUES.md`
- **Best practical opponent today:** `mc` (flat Monte-Carlo).

### One-line summary
Solid engine + set import + two memoryless search agents are in place; the next
real milestone is **finishing the engine (Stage 0)** so that self-play RL — the
actual goal — learns to play Riftbound rather than to exploit its bugs.
