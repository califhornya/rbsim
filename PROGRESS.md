# Progress

Incremental log per brief v3. One short entry per phase.

## Phase A — Sync parser↔engine (code complete; re-parse pending)
- Created `riftbound/registry/engine_vocab.py` as the single source of truth for
  engine vocabulary (triggers, conditions, filter keys, amount sources,
  activated-cost keys, non-handler verbs). Corrected the activated-cost set to
  the **6 keys the engine actually parses** (brief claimed 10 — see
  KNOWN_ISSUES #1).
- Added an import-time drift guard in `loop.py`: `_DISPATCHED_TRIGGERS` and
  `_HANDLED_CONDITIONS` are asserted against `engine_vocab`, so extending the
  engine without updating the vocab fails the import.
- Reworked `scripts/generate_effects.py`: imports vocab from `engine_vocab`
  (deleted the hardcoded `TRIGGERS`/`CONDITION_TYPES`); `validate_card_result`
  now also checks `target_filter`, `amount_source`, and activated `cost` keys
  plus the `reduce_cost` non-handler verb; system prompt gained sections for
  target filters, dynamic amount sources, activated-ability costs, and
  `reduce_cost`, and the stale "on_move not supported" guidance was corrected.
- Added `--retry-review` (reprocess only cards in `review_needed.txt`); the file
  is now reset at the start of each run; the original `.bak` is preserved once as
  `.json.preparse.bak` before `.bak` is refreshed to the pre-run snapshot.
- Existing suite stays green (`uv run pytest` → 32 passed); drift guard verified
  to catch a simulated new condition.

### Re-parse — DONE
Ran `generate_effects.py --only-empty` (488 cards). Results (see
`scripts/sync_report.md` for the full breakdown):
- cards with effects: **275 → 344 (+69)**, **0 regressions**.
- review_needed.txt: 489 → 452 entries; unique flagged cards 437 → 368 (−16%).
  The 40% review-cut target was not met — most remaining flags need genuinely
  new engine verbs/conditions (out of phase-A scope).
- `review_needed.txt` / `suggested_vocab.txt` regenerated; registry loads all
  344 cleanly; `uv run pytest` → 32 passed.
- Backups: original preserved as `all_cards.json.preparse.bak`; `.bak` = pre-A
  snapshot.

## Spot-check — sample generated (awaiting human verdicts)
- `scripts/spot_check.py` (no API): stratified 30-card sample regenerated on the
  post-A 344-card corpus → `scripts/spot_check_results.md` (30 cards, 9
  categories, 11 complex). Verdicts are blank `⬜ TODO` for a human to fill.
- `scripts/spot_check_summary.py` (not run): aggregates human verdicts into
  overall + per-category rates and a PROSEGUI/RIPARSARE recommendation (≥80%).

**NEXT (human):** fill the Verdict lines in `scripts/spot_check_results.md`, then
`uv run python scripts/spot_check_summary.py`. If OK+MINOR ≥ 80% → B1; else
reinforce the prompt with few-shot examples and re-parse.

## Unit on_play bug fix (approved scope expansion)
Discovered while starting B1: non-LEGION units never resolved their on_play
effects (only a LEGION-gated `_resolve_card_effects` call existed) — most parsed
unit cards were inert. Fixed: units now resolve on_play unconditionally; added a
per-handler try/except resilience guard in `_resolve_card_effects` (`[EFFECT-SKIP]`
verbose log) so one malformed spec can't abort a match. Corpus crash-check: 6/222
on_play/on_cast cards had malformed specs — now skipped (not crashing) and logged
in KNOWN_ISSUES #0/#0b for spec-level fixes.

## Phase B1 — additional_cost / kicker (code done; re-parse pending gate)
- `EffectSpec.additional_cost` field + `_EFFECT_TOP_LEVEL_FIELDS`;
  `KNOWN_ADDITIONAL_COST_KEYS` in `engine_vocab.py`.
- `loop.py`: `_try_pay_additional_costs` + `_pay_one_additional_cost`
  (+ `_first_friendly_unit_on_board`), wired into both UNIT and SPELL play
  branches after base cost. Policy: **always pay if affordable**. `_kicker_paid`
  reset via try/finally in `_resolve_card_effects`. Fixed an index-shift bug: the
  played card is now removed by identity (a kicker discard can shift hand indices).
- Parser: `additional_cost` documented in the prompt (Blast Corps Cadet example) +
  key validation.
- `tests/test_additional_costs.py` (6 tests) green; full suite **38 passed**.
- PENDING: B1 re-parse on kicker cards (`--retry-review`) — paid, deferred to the
  post-spot-check batch.

## Phase B2 — target_filter + amount_source (code done; re-parse pending)
- `effects.py` `_passes_filter` +7 keys: `non_token`, `is_buffed`, `is_mighty`,
  `might_less_than_self` (vs source unit), `card_type`, `is_legend`, `is_champion`.
- `effects.py` `_amount` +8 sources: `controller_points`, `opponent_points`,
  `highest_might_friendly`, `cards_in_hand`, `enemies_here`, `friendly_units_here`,
  `n_friendly_with_tag` (uses spec `tag`), `n_distinct_tags_among_friendlies`
  (+ new `_friendly_units(ctx)` helper).
- `engine_vocab.py` `KNOWN_FILTER_KEYS` / `KNOWN_AMOUNT_SOURCES` extended; parser
  prompt gained NL→key mappings; validation auto-follows the frozensets.
- `tests/test_target_filter.py` (8) + `tests/test_amount_source.py` (6).
- Full suite: **51 passed**.
- PENDING: B2 re-parse — paid, deferred to the post-spot-check batch.

## Spot-check round 1 + reinforcement + paid re-parse (round 2) — DONE
- Spot-check round 1: 28/30 reviewed, **OK+MINOR 21/28 = 75%** — below 80% gate.
  Summary script had a too-strict regex (initially reported 0%); fixed to be
  case-insensitive and tolerate combined annotations.
- 7 recurring error buckets identified from notes → added one few-shot example
  per bucket in `build_system_prompt` (`scripts/generate_effects.py`). Also
  engine: bare `REPEAT` keyword now defaults its cost to `card.cost_energy`
  (`tests/test_repeat_cost.py`, 3 tests).
- Cleared `effects[]` on the 18 round-1-flagged cards (7 BAD + 11 MINOR) and
  ran `--only-empty` (437 cards) with the reinforced prompt.
- Result: **326 → 354 with effects (+28), 0 regressions**.
  Of the 18 cleared, 7 came back populated (kicker, EQUIP fix, bare REPEAT,
  clean token spec all visibly worked); 11 stayed empty — most acceptably
  flagged (Kai'Sa/`gain_power`, Rocket Barrage/`mode_choice`,
  Grand Strategem/`all_friendly_anywhere`), a few likely over-flagged (Sprite
  Fountain, Navori Fighting Pit, Poro Snax, Super Mega Death Rocket!,
  Sprite Queen).
- Hardened `scripts/spot_check.py`: refuses to overwrite a results file with
  filled verdicts (use `--force`), so future runs can't accidentally clobber
  the human's work.
- Round-2 review artifact in `scripts/spot_check_round2.md` — human fills the
  18 cards' round-2 verdicts to decide whether to clear the 80% gate.
- Tests: **54 passed** (51 + 3 REPEAT cost tests).
- See `scripts/sync_report.md` for the full delta + buckets still blocked.

## Out of scope this session
B1 (additional_cost/kicker) and B2 (more filters/amount_sources) — deferred. B1
is gated on a green spot-check. Decided defaults recorded for later: kicker =
never auto-pay; see KNOWN_ISSUES for open rules questions.
