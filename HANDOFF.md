# rbsim — Session Handoff (for the next agent)

This is a self-contained briefing to continue the rbsim completion work without
re-deriving context. Read this first, then `RECAP.md` (the parser-pipeline
details) and `KNOWN_ISSUES.md`. Where this file and older docs disagree, **this
file wins** — it reflects the latest state.

---

## 0. TL;DR — where things stand

- **What rbsim is:** a Python simulator for *Riftbound* (the League of Legends
  TCG). It plays full games between AI agents. Cards carry structured `effects[]`
  executed by handlers; an LLM parser translates printed card text into those
  effects.
- **The goal (user's vision):** (1) all 4 card sets fully playable in the sim;
  (2) strong, deck-agnostic agents that self-improve and can be studied / played
  against at chosen difficulty (chess-engine style); (3) a simple web UI to play
  vs an agent and to spectate agent-vs-agent games; (4) study reports.
- **Progress:** Steps 0–1 of a 6-step plan are **done and committed**. Next is
  **Step 2 (make the engine pausable)**. Plan + status in §4–5 below.
- **Tests:** `uv run pytest -q` → **68 passed** (was 54 at baseline).
- **Cards:** 354 / 763 have parsed `effects[]`. ~387 flagged in
  `scripts/review_needed.txt` (mostly mechanics the engine doesn't support yet).

---

## 1. Repo location, git, and how to run

- **Canonical working copy: `~/rbsim-v2`.** This is the ONLY copy to work in.
  - It was moved out of `~/Downloads/rbsim-main` because macOS TCC blocks
    tool/sandbox access to `~/Downloads` (directory enumeration is denied even
    after granting file access). **Do not move the project back into
    `~/Downloads`** — git will fail with "Operation not permitted".
  - An old stale copy `~/rbsim` still exists (old code `003b1d5`, same remote).
    Ignore it. The user was asked about deleting it but deferred. Never edit it.
- **GitHub: `github.com/califhornya/rbsim`** (PUBLIC). `main` = v2 (this code).
  Local `main` tracks `origin/main`; pushes are plain `git push` (no force needed
  anymore). The old code is archived on branch **`v1-legacy`** (`003b1d5`).
  Branches `codex-old` / `codex/...` are untouched, ignore them.
- **Workflow the user wants: GitHub is the source of truth.** Commit and push
  after every meaningful step so `origin/main` always reflects the latest.
- **Environment:** Python 3.11+ via `uv`. If tests error with
  `ModuleNotFoundError` (e.g. `typer`), the venv is stale — run `rm -rf .venv &&
  uv sync` (it was just rebuilt; noting the fix in case it recurs after a move).
- **Commands:**
  - Tests: `uv run pytest -q`
  - Simulate: `uv run rbsim simulate --games 100 --seed 42 --aiA pyke --aiB diana
    --deckA riftbound/data/decks/fury_chaos_pyke.json
    --deckB riftbound/data/decks/chaos_mind_diana.json --no-verbose`
  - Import smoke / vocab drift guard: `uv run python -c "import riftbound.core.loop"`
  - Parser (paid, needs `ANTHROPIC_API_KEY`): see `RECAP.md §7`. `--dry-run` first.
    New: `--names "Card A;Card B"` for a targeted re-parse without wiping the whole
    review list.
  - EQUIP audit: `uv run python scripts/audit_equip.py` (`--fix` to reconcile).

---

## 2. Commits so far (both on `origin/main`)

- `00f12d3` **Baseline** — the v2 zip content as first committed (354/763 cards,
  54 tests).
- `d5edf47` **Step 1** — fixes below.

---

## 3. What Step 1 did (already committed)

**The headline fix — the engine used to hang on every full game.** A ready
**token** in a player's base (Recruit/Gold) made the heuristic agents propose a
`MOVE` the engine silently refuses (tokens can't move to a battlefield); the
action state never changed, so the `while True` action loop spun forever. This is
why earlier sims looked like "~12s/game" — they never actually completed.

Fixes (see `KNOWN_ISSUES.md` "Completion-work log (Step 1)"):
1. **Engine no-op guard** in the action loop — `GameLoop._action_fingerprint()`
   (in `riftbound/core/loop.py`) compares state before/after each action and ends
   the action phase if nothing changed. **Durable**: protects against ANY agent
   proposing an unapplicable action. This is a precursor to Step 2's
   `legal_actions()`. There is also an absolute per-turn action cap (200).
2. `Player.pop_base_unit()` skips tokens + new `Player.has_movable_base_unit()`;
   both heuristic agents' `_score_move` use it (`riftbound/ai/heuristics/*.py`).
3. Result: **100 seeded games in 0.2s, 0 hangs** (was: never completed). The
   engine is fast — good for the MCTS work in Step 4.

Also in Step 1:
- Fixed 4 malformed card specs (Thermo Beam, Retreat, Annie Stubborn, Desert's
  Call) in `all_cards.json`.
- New effect handlers in `riftbound/core/effects.py`: **`kill_gear`** ("Kill all
  gear"), **`channel_rune`** (channel N runes, optional `exhausted`), plus
  **both-sides target** support (`target: "battlefield"` + `scope: "all"`), so
  The Ruination / Angler Beast resolve. **`recall_unit` now returns units to
  hand** (was: base) — correct per "return to its owner's hand"; tokens cease to
  exist; attached gear is recovered to base.
- Parser prompt (`scripts/generate_effects.py`): kicker uses `power` not `energy`
  for domain symbols; partial-parse guidance (parse supported abilities, flag
  only the unsupported remainder); token-spec style; "here"-scoping clarified.
- `scripts/audit_equip.py` (new) reconciled 6 EQUIP keyword costs with printed
  text. NOTE: the engine pays EQUIP from the gear's `cost_energy`/`cost_power`
  fields, not this keyword — the keyword is cosmetic (see KNOWN_ISSUES).
- 14 new tests: `tests/test_step1_fixes.py`, `tests/test_no_hang.py`.

---

## 4. The plan (6 steps) — what's left

**Step 0 — Safety net.** ✅ Done (git repo, now on GitHub).

**Step 1 — Small fixes.** ✅ Done (see §3; the hang fix was the big one).

**Step 2 — Make the engine "pausable" (NEXT).** The engine runs a whole game to
completion with agents called inline; the search AI and browser play both need it
to *pause at decision points*. Concretely:
  - **Golden fixture first** (parity oracle): record ~20 seeded agent-vs-agent
    games — snapshot (winner, turns, points, units/spells) to a JSON fixture in
    `tests/`. The refactor is not "done" until it reproduces this byte-identically.
    Add invariant tests too (card conservation across zones, no negative
    resources, chain empty between actions).
  - **Decision protocol** (`riftbound/core/decisions.py`, new): a `DecisionPoint`
    enum (MULLIGAN, TURN_ACTION, REACTION, SHOWDOWN_ACTION, OPTIONAL_COST,
    CHOOSE_TARGET), a `DecisionRequest(point, player, legal_actions, observation)`,
    a typed `GameAction`, and an `Observation` that shows only what a real player
    sees (own hand, boards, VP/energy, deck counts — NOT the opponent's hand/deck
    order). Today agents receive the full opponent `Player` — an info leak to fix.
  - **`legal_actions(gs, point)`** (`riftbound/core/legality.py`, new): extract
    the validity checks currently inlined in `_apply_action` (which silently
    no-ops illegal actions). MCTS, the web UI, and correctness all consume this.
    The Step 1 `_action_fingerprint` guard is a stopgap for exactly the gap this
    closes.
  - **Generator engine**: convert `GameLoop.start()` to yield `DecisionRequest`
    and resume via `.send(action)`. Two thin drivers: `SyncDriver` (replicates
    current CLI behavior exactly — verify against the golden fixture) and
    `SessionDriver` (holds a paused game for the web layer and search).
  - **Clone + determinize**: `GameState.clone()` (deepcopy excluding
    `Player.agent` + recorder; benchmark it), and `determinize(gs, observer, rng)`
    (reshuffle opponent hidden info) for ISMCTS.
  - Agent call sites to invert are in `riftbound/core/loop.py` (`decide_mulligan`,
    `decide_action`, `decide_reaction`, `decide_showdown_action`).

**Step 3 — Finish the cards ("all 4 sets playable").** Fat-head-first from
`scripts/suggested_vocab.txt` (top items today: `target:all_friendly_units_anywhere`
×12, `channel_rune_exhausted` ×10 — note `channel_rune` itself now exists,
`gain_power_any_domain` ×8, `mode_choice` ×7, `spend_buff` cost ×7,
`aura:reduce_cost` ×6). Per mechanic follow the RECAP §6c recipe: implement in
engine → add to the right `engine_vocab.py` frozenset (the loop import-time drift
guard enforces sync for triggers/conditions) → document in parser prompt → add a
focused test → re-parse affected cards (`--retry-review`) → update
`scripts/sync_report.md`. Add a **`rbsim coverage`** command (% full/partial/
unsupported per set) and a **deck validator** (a deck is "playable" only if every
card is fully implemented; the web UI + arena offer only playable decks).
Honest scope: 763/763 won't happen in one pass — mark true one-offs `unsupported`
with a reason; the coverage report makes the tail explicit and mechanical to close.

**Step 4 — Strong agents.** (a) `GreedyAgent` (`riftbound/ai/greedy_agent.py`,
new): deck-agnostic, 1-ply — for each legal action clone→apply→evaluate (VP diff
dominant, battlefield might/control, pending Hold/Conquer, tempo). Implements ALL
decision points (existing agents stub reaction/showdown). (b) **Arena + Elo**
(`riftbound/ai/arena.py`, `rbsim arena`): round-robin, seat-swapped, mirrored
seeds; Elo in SQLite (extend `riftbound/data/schema.py`). (c) **ISMCTS**
(`riftbound/ai/ismcts_agent.py`): determinized information-set MCTS, Greedy-policy
rollouts, time/sim budget (= web difficulty knob). Strength gates: ISMCTS > Greedy
>65%, Greedy > Random >85%, ≥400 games, strength rises with think budget.

**Step 5 — Web UI.** FastAPI backend (`riftbound/web/app.py`) with a
`SessionDriver` store: `POST /games`, `GET /games/{id}/state` →
{observation, pending_decision, legal_actions}, `POST /games/{id}/action` (drive
the agent in a thread executor until the human's turn), `GET /games/{id}/spectate`
(SSE agent-vs-agent). Plain HTML+JS frontend (`riftbound/web/static/`), `rbsim
serve`. The user has FastAPI experience. Verify by playing a full browser game.

**Step 6 — Study reports.** Extend `riftbound/data/analytics.py`: deck×deck
matchup matrix from the arena DB, per-card winrate-when-drawn/played (recorder
already logs these), opening-line stats. `rbsim report` + one static HTML page.

---

## 5. Invariants & gotchas (do NOT break)

- **`engine_vocab.py` single-source-of-truth** — any new trigger/condition/filter/
  amount-source/cost-key must be added to both the engine AND the matching
  frozenset; the loop's import-time drift guard fails the import otherwise
  (`RECAP.md §1a`).
- **Additive-only** — the 354 existing parses must keep working; don't rename or
  reshape fields (`RECAP.md §1b`).
- **Per-handler resilience guard** in `_resolve_card_effects` (`[EFFECT-SKIP]`)
  stays — one malformed spec must not abort a match (`RECAP.md §1c`).
- **KNOWN_ISSUES.md** has the deferred items: gear collapses play-cost/equip-cost;
  Pyke-vs-Diana ~66% Diana (agent-balance artifact, not a bug — Step 4 replaces
  those bots); the 6 malformed-spec offenders (4 now fixed).
- **Decisions already made (don't relitigate):** B1 kicker = always-pay-if-
  affordable; activated-cost keys are 6 not 10; bare REPEAT defaults to the
  spell's `cost_energy`; EQUIP keyword cost = derived from printed pips
  (`RECAP.md §4`).

---

## 6. The user's own side-task (does not block the agent)

`scripts/spot_check_round2.md` — 18 cards where the user eyeballs whether the
LLM-parsed effects match the printed card text (fills `Round 2 Verdict`). Their
verdicts tell us if parser quality is ≥80% OK+MINOR before big Step-3 parse waves;
if it's below, reinforce the parser prompt first (`RECAP.md §9`). It's the user's
task — proceed with engine/AI/UI work regardless.

---

## 7. Suggested first moves for the next agent

1. `cd ~/rbsim-v2 && uv run pytest -q` → confirm 68 passing (rebuild venv with
   `rm -rf .venv && uv sync` if you hit a stale-venv `ModuleNotFoundError`).
2. Read `RECAP.md` and `KNOWN_ISSUES.md`.
3. Start Step 2 with the **golden-game fixture** (the parity oracle) BEFORE any
   refactor — that's what makes the pausable-engine rewrite safe.
4. Commit + push after each milestone so `origin/main` stays current.
