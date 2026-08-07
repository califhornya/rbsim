# Known Issues

Out-of-scope findings logged here instead of being fixed inline (per brief v3
convention). Each entry: what, where, why deferred.

## Completion-work log (Step 1)

### (FIXED) Action-phase infinite loop / apparent "12s per game"
- **Was:** a ready **token** in base (e.g. Recruit/Gold) made the Pyke/Diana
  agents propose `MOVE` every action; the engine silently refuses to move tokens
  to a battlefield (`loop.py` MOVE branch re-inserts the token and returns), so
  the action state never changed and the `while True` action loop spun forever.
  Full games never completed — what looked like "~12s/game slowness" was this
  hang hitting the harness timeout.
- **Fix:** (1) engine no-op guard in the action loop — `_action_fingerprint()`
  compares state before/after each action and ends the action phase if nothing
  changed (durable: protects against *any* agent proposing an unapplicable
  action; a precursor to the Step 2 `legal_actions()` work). (2) `pop_base_unit()`
  now skips tokens + `Player.has_movable_base_unit()`. (3) both agents' `_score_move`
  use that helper so they don't propose impossible moves. Regression: `tests/test_no_hang.py`.
- After the fix: 100 seeded games in 0.2s, 0 hangs, avg 14.3 turns.

### (DEFERRED) Gear collapses play-cost and equip-cost
- The engine pays EQUIP from the gear card's `cost_energy`/`cost_power` fields
  (`loop.py` equip branch), the SAME fields used to play the gear from hand — so
  a gear's printed EQUIP cost (e.g. `EQUIP [1][fury]` = 2) is not modeled
  separately from its play cost. The parsed `EQUIP N` keyword is cosmetic to the
  engine (never read on the pay path); `scripts/audit_equip.py` now keeps that
  keyword consistent with the printed text (6 fixed), for display/future use.
- Deferred: modeling a distinct equip cost is an engine-semantics change; revisit
  after the Step 2 refactor lands the golden-game fixture.

### (NOTE) Pyke-vs-Diana winrate is ~66% Diana
- Not a correctness bug — a heuristic-agent/deck balance artifact. The Step 4
  agents (Greedy/ISMCTS) replace these hand-tuned bots; revisit balance then.

## Step 2 findings (surfaced by the parity-oracle / invariant work)

### (DEFERRED) Resolved spells are never put into the trash
- **Where:** `loop.py` `_run_chain` resolution loop (~:1407-1422) and the main-phase
  SPELL branch (`_apply_action`, ~:914-919). A cast spell is removed from hand and
  placed on the chain; after its effects resolve, the card is dropped — it is never
  appended to `owner.trash` (or banished). So spell card objects leave every zone.
- **Impact:** breaks strict card conservation (each game "loses" its cast spells);
  also means trash-count conditions / recursion (`card_in_trash_count_at_least`,
  return-from-trash) undercount by the spells that should be there. Units, gear and
  champions ARE routed to trash correctly, so only spells are affected.
- **Deferred:** it's a card-lifecycle fix, not part of the pausable-engine refactor.
  `tests/test_invariants.py` encodes the current reality (only spells may vanish) so
  a regression that starts leaking *non-spell* cards fires immediately. Fix later by
  appending the spell card to `owner.trash` after resolution in `_run_chain`.

### (DEFERRED) Baron Nashor's add_battlefield duplicates the played card
- **Where:** `effects.py` `_add_battlefield` (~:675-694). Baron Nashor's on-play
  effect creates a new `Battlefield`, sets `bf.card = ctx.card`, and spawns a
  `UnitInPlay(card=ctx.card)` on it — but the same played card object also remains
  reachable from the player's hand, so one `Card` occupies two zones (hand +
  battlefield) at once (observed at `tests/test_invariants.py` seed 1, pyke vs diana).
- **Impact:** card aliasing / duplication for this one card mechanic. Deterministic,
  so the golden fixture pins the (buggy) end-state; the invariant test therefore does
  NOT assert global "one card, one zone" — it would fail on this pre-existing bug.
- **Deferred:** card-mechanic fix, out of scope for Step 2. Revisit with the Step 3
  card-completion work; likely the UNIT play path's hand-removal and the on-play
  battlefield spawn need reconciling (remove the played card from hand exactly once).

## 0. (FIXED) Unit on_play effects never resolved
- **Was:** the UNIT play branch only called `_resolve_card_effects` when
  `LEGION and cards_played>0`, so every non-LEGION unit's "When you play me…"
  effect was inert. Confirmed at runtime.
- **Fix (B1 prep, approved scope expansion):** resolve on_play unconditionally
  for units; removed the LEGION gating of resolution (LEGION's effect is the cost
  reduction, already applied). Added resilience: handler execution in
  `_resolve_card_effects` is wrapped in try/except (`[EFFECT-SKIP]` verbose log)
  so one malformed spec can't abort a match.

## 0b. Six cards have malformed on_play/on_cast specs (now skipped, not crashing)
The corpus crash-check surfaced 6 cards whose effects raise during resolution —
now caught by the resilience guard above, but the underlying spec/handler
mismatch should be fixed (good spot-check / Phase-C candidates):
- `Thermo Beam`, `Desert's Call`, `Angler Beast`, `The Ruination`:
  `target: "battlefield"` passed to a handler expecting a player target.
- `Retreat`: `add_rune` effect missing its required `domain` param.
- `Annie Stubborn`: `target: "chosen_spell"` passed to a handler expecting a
  player target.
Fix path: either teach the handler/`_player_for_target` to accept these targets
(engine) or correct the parsed spec (re-parse with a sharper prompt).

## 0c. Spot-check findings (round 1, 28/30 reviewed, 75% OK+MINOR)
Recurring parser errors identified from the human verdicts in
`scripts/spot_check_results.md`. Each is being addressed by a few-shot example in
`build_system_prompt` for the next re-parse:
- **EQUIP cost overestimated.** Parser frequently produced `EQUIP 2` where the
  printed ability requires only `1`. Looks systematic across gear (e.g. Recurve
  Bow, Serrated Dirk, Shurelya's Requiem). Audit gear `keywords` against
  printed `effect` text after re-parse; consider a deterministic regex
  corrector on `EQUIP \[N\]` if it persists.
- **REPEAT keyword + cost.** The printed REPEAT keyword carries the cost only as
  a reminder; in the rules the REPEAT cost equals the spell's printed cost.
  Engine fix landing: in `loop.py` SPELL branch, fall back to `card.cost_energy`
  when `keyword_value("REPEAT")` is missing/0. Parser may emit a bare `REPEAT`.
  Exceptions get an explicit value (override the default).
- **`ADD [rune]/[power]` ≠ `add_rune`.** "ADD [rune]" means "gain 1 power of any
  domain" (rune-tap abilities) — should be `gain_power` (or similar), not the
  `add_rune` verb that puts cards into the rune deck (Kai'Sa Daughter of the
  Void).
- **"Choose one" / multi-modal effects.** Currently flattens into one branch;
  needs a representation for mode-selected effects (Rocket Barrage).
- **"here" scoping confusion.** Sometimes added when the text omits it
  (Grand Strategem), sometimes missing when present (Recurve Bow,
  Navori Fighting Pit — needs `here` scope).
- **HIDDEN keyword.** Emit as keyword; mark spell as playable from facedown for
  alternate cost (engine support deferred).
- **Token specs redundancy.** Canonical tokens (Recruit, Sprite, Gold) have
  fixed might/keywords — `play_token` spec should just name the token, not
  duplicate its stats (Viktor Herald of the Arcane, Sprite Queen, Sprite Fountain).

## 1. Activated-cost keys: engine parses 6, brief claimed 10
- **Where:** `riftbound/core/loop.py` `_parse_activated_cost` (~:1019-1047).
- **What:** the v3 brief's "Stato attuale" lists 10 accepted cost keys
  (`energy, power, tap, exhaust, exhaust_self, recycle, recycle_from_trash,
  sacrifice_self, kill_friendly, spend_xp`), but the engine actually parses only
  **6**: `energy, power, tap, recycle, sacrifice, spend_xp`.
- **Decision:** `engine_vocab.KNOWN_ACTIVATED_COST_KEYS` lists only the real 6,
  so the parser won't emit costs the engine silently drops. Costs using the
  missing mechanics (exhaust another unit, recycle-from-trash, kill-friendly,
  pay-xp-as-activated-cost) are flagged to `suggested_vocab.txt` (tags like
  `cost:exhaust_self`, `cost:recycle_from_trash`). Extend the engine + the
  frozenset together if these cross a frequency threshold at re-parse.

## 2. Multiple kickers per card — rules unclear (brief open Q2)
- **What:** the planned B1 `_try_pay_additional_costs` pays only the first
  affordable `additional_cost` (one kicker per card). Do the Riftbound rules
  allow multiple kickers on one card?
- **Where to verify:** `Riftbound Core Rules v1.2.pdf` (costs section). The repo
  ships the PDF, not the markdown the brief references.
- **Status:** unresolved; resolve before implementing B1.

## 3. `you_discarded_card_this_turn` semantics — active vs passive (brief open Q3)
- **Where:** `loop.py` `_check_condition` (`you_discarded_card_this_turn`, ~:610)
  reads `gs.discarded_this_turn`.
- **What:** unclear whether this should fire only on a discard the player chose
  to make ("you discarded") or also on discards forced by an opponent. Current
  engine tracks any discard for that side.
- **Status:** flag for rules clarification; revisit if a card depends on the
  distinction.

## 4. `reduce_cost` auras on other cards not dispatched
- **Where:** `loop.py` `_cost_reduction` (:617-634) applies `reduce_cost` only as
  a flat discount to the card that owns the effect.
- **What:** "Spells you play cost [1] less" style auras affecting OTHER cards are
  not dispatched yet. The parser still emits them (correct) and tags
  `aura:reduce_cost` in suggested_vocab so we can measure coverage before
  building the general dispatch (out of scope for v3 phase A).
