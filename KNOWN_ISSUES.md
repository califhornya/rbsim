# Known Issues

Out-of-scope findings logged here instead of being fixed inline (per brief v3
convention). Each entry: what, where, why deferred.

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
