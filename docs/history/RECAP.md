# Riftbound TCG Simulator — Handoff Recap

This file is a self-contained briefing for the next model to pick up the work
without re-doing the discovery. It covers: what the project is, what's been
done, the conventions you must preserve, what's still open, and the concrete
next steps.

## 0. Project at a glance

**Repo:** `/Users/mateo/Downloads/rbsim-main` (the v2 zip extract). **Not a git
repo** — there is no `.git` directory, so no per-commit history. The older
`~/rbsim` IS a git repo but is stale (predates Phase A). Work in
`~/Downloads/rbsim-main`.

**What it is:** a Python simulator for the *Riftbound* TCG. The engine reads
structured `effects[]` per card from `riftbound/data/cards/all_cards.json` and
executes them via handlers registered in `riftbound/core/effects.py`. A separate
LLM-based parser (`scripts/generate_effects.py`, model `claude-opus-4-7`)
translates each card's printed rules text (the `effect` field) into those
structured effects.

**Working brief:** `~/Downloads/CLAUDE_CODE_BRIEF_v3.md` (in Italian) defines
Phase A (parser↔engine sync), Spot-check (manual QA), B1 (additional_cost /
kicker), B2 (more target_filter + amount_source), Phase C (long tail). The
brief is the spec; this recap captures what's been done against it and what's
new.

**State today:**
- 763 cards total; **354 with `effects[]`** (up from 86 pre-v3, 275 pre-A, 344
  post-A round 1).
- **54 tests passing** (`uv run pytest -q`).
- ~358 unique cards still flagged in `scripts/review_needed.txt` — long tail.
- A round-1 spot-check at **75% OK+MINOR** (28/30 reviewed) drove a parser
  prompt reinforcement + a 2nd targeted re-parse. Round-2 verdicts are PENDING
  the human.

## 1. Architecture you must not break

### 1a. The `engine_vocab` single-source-of-truth invariant
The parser used to hardcode its own copies of "known triggers" / "known
conditions", which drifted from the engine and silently produced bad parses.
All vocabulary now lives in **`riftbound/registry/engine_vocab.py`** as
frozensets:
- `KNOWN_TRIGGERS`, `KNOWN_CONDITIONS`, `SAFE_FALSE_CONDITIONS`,
  `KNOWN_FILTER_KEYS`, `KNOWN_AMOUNT_SOURCES`, `KNOWN_ACTIVATED_COST_KEYS`,
  `KNOWN_ADDITIONAL_COST_KEYS`, `NON_HANDLER_VERBS`.

**Drift guard at `loop.py` import time:** module-level `_DISPATCHED_TRIGGERS`
and `_HANDLED_CONDITIONS` mirror the dispatch tables and are asserted against
`engine_vocab` — extending the engine without updating the vocab fails the
import (see top of `riftbound/core/loop.py`).

**Rule of thumb when you add a new condition/trigger/filter/amount-source:**
update both the engine code AND the matching frozenset in `engine_vocab.py`.
The parser's `validate_card_result` auto-follows the frozensets, so the prompt's
list of valid keys regenerates from them (no parser code change needed for the
common case).

### 1b. Additive-only policy
The 354 existing parses must keep working. Don't reshape existing fields,
don't rename, don't change defaults. Add new fields/keys; don't break old ones.

### 1c. Per-handler resilience in `_resolve_card_effects`
Handler execution is wrapped in `try/except` with a `[EFFECT-SKIP]` verbose log.
A single malformed parsed spec can't abort a match. Keep this guard; do not
remove it without an equivalent (the brief precedent is `_player_for_target`
being made permissive).

## 2. Files to know

- **`riftbound/registry/engine_vocab.py`** — vocab frozensets (see §1a).
- **`riftbound/registry/cards_registry.py`** — `EffectSpec` dataclass (frozen),
  `_EFFECT_TOP_LEVEL_FIELDS` tuple, `CARD_REGISTRY` (built by
  `load_cards_json()`).
- **`riftbound/core/loop.py`** — the play loop. Key surfaces:
  - `_resolve_card_effects(card, battlefield, actor, opponent)` — on_play /
    on_cast resolution with the `_kicker_paid` reset in a `try/finally`.
  - `_check_condition(...)` — 15 active conditions + 3 safe-False.
  - `_cost_reduction(card, actor)` — flat `reduce_cost` static/conditional.
  - `_try_pay_additional_costs(card, ap)` / `_pay_one_additional_cost(...)` —
    B1 kicker payment (always-pay-if-affordable).
  - `_first_friendly_unit_on_board(ap)` — helper used by kicker
    kill/exhaust costs.
  - UNIT branch (`_apply_action`) — base cost paid, kicker tried, then
    `_resolve_card_effects` called UNCONDITIONALLY for every unit (this was
    LEGION-gated before — see §3).
  - SPELL branch — base cost paid, kicker tried, REPEAT block (bare keyword
    defaults to `card.cost_energy`), chain runs.
- **`riftbound/core/effects.py`** — handler `@effect` decorator + `REGISTRY`.
  - `_passes_filter(unit, tf, ctx)` — 17 keys (10 original + 7 B2 additions).
  - `_amount(ctx, spec)` — 12 sources (4 original + 8 B2 additions).
  - Helpers: `_source_unit(ctx)`, `_friendly_units(ctx)`,
    `_card_category_name(card)`.
- **`scripts/generate_effects.py`** — LLM parser (Anthropic SDK, model
  `claude-opus-4-7`, batches of 10, cached system prompt).
  - Flags: `--set`, `--only-empty`, `--retry-review`, `--limit`, `--sample`,
    `--dry-run`.
  - Backups: `.bak` is the pre-this-run snapshot; the *original* pre-parse
    backup is preserved one-time as `.preparse.bak`.
- **`scripts/spot_check.py`** — generates a stratified sample into
  `spot_check_results.md`. **Refuses to overwrite a file with filled
  verdicts** (use `--force`). Footgun fixed.
- **`scripts/spot_check_summary.py`** — aggregates verdicts. Tolerates
  case-insensitive codes and combined annotations (e.g. `Minor,
  MISSING_TRIGGER ...`).
- **`tests/test_effects.py`** — main effects regressions. Patterns:
  `_make_loop()`, `_register(name, effects, might)`,
  `cleanup_registry` fixture, plain asserts, append units to
  `bf.units_A`/`units_B`.

## 3. Pre-existing engine bug we fixed (scope expansion)

Non-LEGION units never resolved their `on_play` effects — the UNIT branch only
called `_resolve_card_effects` when `LEGION and cards_played > 0`, leaving most
unit cards inert in sim. We resolve unconditionally now. A corpus crash-check
turned up **6 cards with malformed on_play/on_cast specs** (now skipped, not
crashing, thanks to the resilience guard — see KNOWN_ISSUES #0b):
- `Thermo Beam`, `Desert's Call`, `Angler Beast`, `The Ruination` — pass
  `target: "battlefield"` to a handler expecting a player target.
- `Retreat` — `add_rune` missing required `domain` param.
- `Annie Stubborn` — `target: "chosen_spell"` to a handler expecting a player target.

Fix path: either teach `_player_for_target` to accept these targets, or correct
the parsed specs.

## 4. Decisions already made (don't relitigate)

- **B1 kicker policy = always pay if affordable** (deterministic; baseline
  agents are NOT kicker-aware, so the loop pays for them).
- **Activated-cost keys: 6, not 10.** The v3 brief's "Stato attuale" listed 10
  keys for `_parse_activated_cost`, but the engine truly parses only
  `energy, power, tap, recycle, sacrifice, spend_xp`. The vocab reflects this;
  extras (`exhaust_self`, `recycle_from_trash`, `kill_friendly`, etc.) are
  flagged to `suggested_vocab.txt`, not emitted.
- **Bare `REPEAT` defaults to `card.cost_energy`.** Per the rules, REPEAT cost
  generally equals the spell's printed cost; the printed `[N]` is a reminder.
  Bare-vs-parameterized is detected by inspecting the raw keyword string
  (`keyword_value` returns 1 for bare, which is misleading — see the inline
  comment in `loop.py`). Explicit `REPEAT N` still overrides for exceptions.
- **EQUIP cost = 1.** Several rounds of fixing this; the prompt now emits
  `EQUIP 1` not `EQUIP 2`. The post-A round 1 had many `EQUIP 2`; the round-2
  re-parse fixed it in re-parsed cards (e.g. Recurve Bow). A gear-wide audit
  is still on the to-do list.
- **No git commits.** Repo isn't initialized. Don't `git init` without asking.
- **Out-of-scope bugs go to `KNOWN_ISSUES.md`**, not fixed inline.

## 5. What's been done (chronological summary)

### Phase A — parser↔engine sync
- Created `engine_vocab.py` and the loop import-time drift guard.
- Reworked `generate_effects.py` to import vocab, validate `target_filter` /
  `amount_source` / `cost` / `additional_cost` keys, expand the prompt, add
  `--retry-review`, reset `review_needed.txt` per run, preserve the original
  pre-parse backup once.
- Re-parse round 1 (`--only-empty`, 488 cards): **275 → 344 with effects
  (+69), 0 regressions**.

### Spot-check round 1
- 30-card stratified sample; human filled 28 of 30 verdicts.
- Manual re-tally: **OK+MINOR = 21/28 = 75%** (the summary script's old regex
  reported 0% — bug fixed). Below the 80% gate.
- Identified 7 recurring error buckets — addressed by prompt reinforcement +
  the bug-fix engine work in B1 and the cost-default change.

### Engine: B1 (additional_cost / kicker)
- `EffectSpec.additional_cost` field + `_EFFECT_TOP_LEVEL_FIELDS`,
  `KNOWN_ADDITIONAL_COST_KEYS`.
- `_try_pay_additional_costs` / `_pay_one_additional_cost` wired into UNIT and
  SPELL play branches after base cost. `_kicker_paid` set then reset in
  `_resolve_card_effects` finally.
- **Index-shift bug fixed**: the played card is removed by identity, because a
  kicker `discard_cards` cost can shift hand indices and break a stale
  `remove_from_hand(idx)`.
- Parser documents + validates `additional_cost`.
- `tests/test_additional_costs.py` (6 tests).

### Engine: B2 (filter + amount expansions)
- `_passes_filter` +7: `non_token`, `is_buffed`, `is_mighty`,
  `might_less_than_self` (vs `_source_unit(ctx)`), `card_type`, `is_legend`,
  `is_champion`.
- `_amount` +8: `controller_points`, `opponent_points`,
  `highest_might_friendly`, `cards_in_hand`, `enemies_here`,
  `friendly_units_here`, `n_friendly_with_tag` (uses `spec.params.tag`),
  `n_distinct_tags_among_friendlies` (+ new `_friendly_units(ctx)` helper).
- `engine_vocab` + parser prompt updated; validation auto-follows.
- `tests/test_target_filter.py` (8) + `tests/test_amount_source.py` (6).

### Reinforcement + Re-parse round 2
- Added few-shot examples in `build_system_prompt` for the 7 error buckets:
  bare REPEAT, EQUIP cost, `ADD [rune]/[power]` ≠ `add_rune`, choose-one,
  `here` scoping, HIDDEN, canonical-token specs, kicker.
- Bare REPEAT default in engine (`tests/test_repeat_cost.py`, 3 tests).
- Cleared `effects[]` on the 18 round-1-flagged cards (7 BAD + 11 MINOR) and
  ran `--only-empty` (437 cards) with reinforced prompt.
- Result: **326 → 354 with effects (+28), 0 regressions**.
- Of the 18 cleared cards: **7 came back populated**, **11 stayed empty** —
  most of the empties are the prompt correctly refusing wrong parses for
  unsupported mechanics; ~5 look like over-conservative regressions.
- Round-2 review artifact in `scripts/spot_check_round2.md` (PENDING human
  verdicts).

## 6. What's left

### a) Spot-check round-2 verdicts (human task)
`scripts/spot_check_round2.md` has the 18 round-1-flagged cards with both the
round-1 verdict/notes and the new parse. Human fills the `**Round 2 Verdict:**`
lines using OK / MINOR / WRONG_* / MISSING_* / PHANTOM_EFFECT / UNCERTAIN /
FLAGGED_OK / FLAGGED_WRONG. The summary script reads `spot_check_results.md`
today — to point it at round2 you'd need a `--path` flag or to rename the file.

### b) Likely round-3 prompt permissiveness tweak
5 cards regressed to empty under the reinforced prompt where round 1 had a
populated parse (suspect over-flagging):
- `Sprite Fountain`, `Sprite Queen` — `play_token` of canonical tokens
  (the "omit redundant might/keyword" guidance may have been read too strictly).
- `Navori Fighting Pit` — `buff_unit` "here" — possibly the "don't add `here`
  unless text says so" guidance conflicted with text that DOES say "here".
- `Poro Snax` — activated cost includes `kill_self` (not in
  `KNOWN_ACTIVATED_COST_KEYS`), but the on_play `draw 1` is independently
  parseable.
- `Super Mega Death Rocket!` — `return_from_trash` as cost-gated trigger
  effect; may need a few-shot.

Fix: small prompt amendments + a third tiny re-parse on only these names.

### c) Phase C — long tail (fat head first)
Use `scripts/suggested_vocab.txt` as the priority queue. Top counts:
- `channel_rune` ×6 / `channel_rune_exhausted` ×5 (rune-tap economy)
- `play_token_exhausted` ×6
- `bonus_damage` ×5
- `cond:excess_damage_at_least` ×5 (a "safe-False" condition awaiting damage
  context — see `_check_condition`)
- `cost:kill_self` ×4 (the Poro Snax family)
- `aura:reduce_cost` ×3 (reduce_cost on OTHER cards — not just self)
- `mutual_combat_damage` ×3
- `play_to_open_battlefield` ×3
- `effect:gain_power_any_domain` (Kai'Sa family) — currently flagged via prompt
- `effect:mode_choice` (Rocket Barrage family) — currently flagged via prompt
- `target:all_friendly_units_anywhere` (Grand Strategem family)

Per mechanic, the repeating recipe:
1. Implement in the engine (new condition branch in `_check_condition`, new
   trigger dispatch, new `@effect` verb, new filter/amount, or new activated-
   cost key + payment).
2. Add to the right `engine_vocab` frozenset (the loop guard enforces sync for
   conditions/triggers; the parser auto-picks up the rest).
3. Document it in the parser system prompt; validation auto-follows.
4. Add a focused test.
5. `--retry-review` to unlock affected cards; update `scripts/sync_report.md`.

Stop when the remaining tail is all low-ROI singletons (log them in
`KNOWN_ISSUES.md` as deferred).

### d) Known engine + parser gaps to address ad-hoc
- **Gear EQUIP cost audit** — even after round 2, the audit hasn't been
  systematized. A small script could diff parsed `EQUIP N` against printed
  `effect` text and flag mismatches.
- **The 6 malformed-spec offenders** in §3 — fix targets/handlers or
  re-parse with sharper prompts.
- **The few-shot example for kicker uses `energy: 1`** for Blast Corps Cadet,
  but the model correctly emitted `power: 1` (because `[fury]` is a power
  symbol). Update the few-shot to use `power` to avoid teaching the wrong
  pattern.

## 7. Commands — quick reference

```bash
# tests (54 must pass)
uv run pytest -q

# parser dry-run (no API)
uv run python scripts/generate_effects.py --dry-run --retry-review

# paid re-parse (needs ANTHROPIC_API_KEY in env or inline)
ANTHROPIC_API_KEY='sk-…' uv run python scripts/generate_effects.py --only-empty

# spot-check sampler (refuses to overwrite a verdicted file; use --force)
uv run python scripts/spot_check.py
uv run python scripts/spot_check_summary.py

# import smoke-test (confirms engine_vocab drift guard holds)
uv run python -c "import riftbound.core.loop; print('OK')"
```

## 8. Pointers
- `PROGRESS.md` — running log of phases done with results.
- `scripts/sync_report.md` — per-re-parse deltas + buckets blocked.
- `KNOWN_ISSUES.md` — out-of-scope findings (read this before assuming a bug
  is new; it's where the on_play fix, EQUIP cost notes, REPEAT default,
  cost-keys gap, etc. are logged).
- `scripts/spot_check_results.md` — fresh stratified 30-card sample (post-A
  round 2, blank verdicts).
- `scripts/spot_check_round2.md` — the focused 18-card re-verification file
  (PENDING human round-2 verdicts).
- `scripts/suggested_vocab.txt` — Phase C priority queue (count-sorted).
- `scripts/review_needed.txt` — currently flagged cards (358 unique).
- `~/Downloads/CLAUDE_CODE_BRIEF_v3.md` — the original Italian brief; treat
  this recap as authoritative where they disagree (a few brief claims about
  engine state were wrong — see §4).

## 9. One-paragraph "what to do next"

Read `scripts/spot_check_round2.md` for the round-2 quality signal. If the
human's verdicts confirm the round-2 re-parse hit ≥80% OK+MINOR, do a small
round-3 prompt permissiveness pass for the 5 regression suspects in §6b (and
fix the kicker few-shot example to use `power` not `energy`), re-parse just
those names, then start Phase C with `channel_rune` / `gain_power` /
`mode_choice` / `all_friendly_anywhere` per §6c. If verdicts come back below
80%, prompt-reinforce again before doing more parsing. Either way, keep the
engine_vocab single-source-of-truth invariant intact and never remove the
per-handler resilience guard.
