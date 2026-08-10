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

### (DEFERRED) No stepwise engine → MCTS can't expand arbitrary mid-game nodes
- **What:** the pausable-engine work (Step 2) delivered `GameState.clone()`,
  `legal_actions()`, `determinize()`, and a thread-backed `SessionDriver`. Those
  cover MCTS **1-ply / full-rollout** search (clone → `_apply_action` → evaluate)
  and interactive web play. What they do NOT cover: continuing a game from a
  *cloned mid-game state* through the begin/draw/showdown/combat phases — the
  phase engine (`GameLoop.start`) still only runs a whole game start→finish, and a
  thread/generator frame isn't cloneable.
- **Impact:** if Step 4's ISMCTS needs deep information-set trees (expanding node
  after node), rather than root-parallel rollouts, it needs a **stepwise engine**:
  move all "where am I in the game" state into `GameState` (a phase/decision
  cursor) and expose `advance(gs, action) -> gs'`, so a clone can be advanced one
  decision at a time. That is a substantial rewrite of the phase structure and was
  deliberately deferred (the golden fixture only weakly protects the reaction/
  showdown paths, which stub agents don't exercise).
- **Recommendation:** start ISMCTS with Greedy-policy full rollouts on clones
  (already supported); build the stepwise engine only if measured strength needs
  deeper trees. Do it behind the golden fixture, and add reaction/showdown-heavy
  fixtures first so the refactor is actually covered.

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

## 5. BUFF (object) vs raw might modifier — engine conflates them (found in spot-check R2)
- **What:** English "buff" collapses two DIFFERENT Riftbound concepts:
  1. A **Buff** = a specific object placed on a unit, **max 1 per unit, non-stacking**,
     spendable, checkable (`is_buffed`). Example: **Arena Bar**.
  2. A raw **"+N might (this turn)" modifier** — freely additive, no object, no
     one-per-unit limit. Examples: **Discipline**, **Grand Strategem** ("+5 might").
- **Where:** `riftbound/core/effects.py` `_buff_unit` (~:195) models concept (1):
  `if unit.might_counters < 1: unit.might_counters += 1` — non-stacking, ignores
  `amount`. `spend_buff`, filter `is_buffed`, condition `this_is_buffed` all build
  on this same counter — consistent with the Buff-OBJECT reading.
- **Problem:** there is currently **NO verb for concept (2)** (raw temporary might
  modifier). Cards like Grand Strategem / Discipline have nowhere correct to parse.
  Using `buff_unit` for them is WRONG: caps at +1, places a Buff object, and would
  wrongly satisfy `is_buffed`.
- **CORRECTION (found at card 9):** the raw-modifier verb ALREADY EXISTS —
  `grant_might` (effects.py:31, honors `amount`, folds into passive_might overlay
  when trigger=passive; contrast buff_unit which caps at 1 and sets might_counters).
  Negative side also exists: `debuff_might` (effects.py:99), and `grant_might`
  accepts negative `amount` too (no zero floor in loop.py:134 grant_might). So this
  is NOT a missing-verb problem — it's a PARSER-ROUTING problem.
- **Fix (Step 3) — per user, the clean verb set is:**
  - `buff_unit` = place a BUFF OBJECT (max 1, might_counters). KEEP.
  - `grant_might` = raw +N might (Discipline, Grand Strategem). Already exists,
    honors amount, folds as passive. Handles NEGATIVE amount too, so it also
    covers "-N might" (Stupefy). USE THIS for raw might up OR down.
  - `debuff_might` (effects.py:99): user says USELESS — do not route cards to it.
    grant_might(negative) is the canonical raw-reduction path. Deprecate/remove
    debuff_might.
  - `spend_buff` (effects.py:202): removes a BUFF counter as a COST, default
    FRIENDLY ("spend a buff to ..."). KEEP as-is for costs.
  - `debuff_unit` = NEW verb the user wants, DOES NOT EXIST yet: remove a BUFF
    TOKEN from a unit as an EFFECT (can target an ENEMY's buffed unit). Distinct
    from spend_buff (that's your own buff, paid as a cost). Same state poke
    (might_counters -= 1) but different semantics + default target (enemy/chosen).
  - Parser routing: "place a buff / gets a +1 buff" -> buff_unit; "gets +N/-N
    might" -> grant_might; "spend a buff (cost)" -> spend_buff; "remove a buff
    from a unit (effect)" -> debuff_unit (once built).
  - Tests: raw grant_might +/- must NOT set is_buffed; buff_unit must; debuff_unit
    removes a buff from an enemy unit without being a cost.

## 6. No location filter on targets — "at a battlefield" vs "in base" indistinguishable
- **What:** target resolution (`effects.py` `_resolve_targets` ~:299 +
  `target_filter` via `_passes_filter`) selects by SIDE and by unit PROPERTIES
  (is_buffed, is_mighty, subtype, etc.) but has no concept of unit LOCATION.
  Cards that restrict to "a unit at a battlefield" (excludes base) or "in a base"
  cannot express that restriction — the target is silently too broad.
- **Found via:** Blast Corps Cadet ("deal 2 to a unit at a battlefield") parsed
  with target `chosen_unit` — would wrongly allow hitting a base unit.
- **Also relevant to:** Rocket Barrage ("a unit in a base" — the opposite
  restriction), and likely others.
- **REFINEMENT (found at Yasuo, card 11/13):** location scoping is actually
  CORRECT for triggered effects whose context is a single battlefield —
  combat/scoring triggers (on_attack, on_hold, on_conquer) resolve with
  ctx.battlefield = the relevant battlefield, and enemy_unit/friendly targets go
  through `_units_for_side` -> `self.battlefield.units_*` (singular), so "here" is
  enforced by construction. The gap is NARROWER than first stated: it only bites
  effects where the PLAYER CHOOSES a target that the card restricts by location
  (e.g. a spell: "deal 2 to a unit AT A BATTLEFIELD" / "a unit IN A BASE"). There
  the chooser isn't constrained to a location. Scope the Step 3 fix to
  player-choice targets on non-battlefield-context effects; do NOT chase a
  location bug in triggered "here" effects — there isn't one.
- **Fix (Step 3):** add a location dimension — either dedicated targets
  (`battlefield_unit` / `base_unit`) or a target_filter key
  (`location: "battlefield" | "base"`). Register in engine_vocab, document in
  parser prompt, add tests, re-parse affected cards.

## 7. Equipped gear does not fire its own triggered abilities (systemic)
- **What:** the combat trigger loop (`loop.py` ~:1516-1521) fires
  on_attack/on_defend on `unit.card` only — it iterates units at the battlefield
  and resolves THEIR card triggers. It never iterates a unit's attached `gear`
  cards. So a gear's equipped ability "When I attack/defend, ..." (where "I" =
  the wearer via the gear) NEVER fires.
- **Found via:** Recurve Bow (equipped: "When I attack or defend, deal 2 to an
  enemy unit here"). Parse is correct; the specs are dead because nothing fires
  gear triggers in combat.
- **Scope:** likely affects EVERY equipped-gear triggered ability, not just
  on_attack/on_defend — check on_play/on_hold/on_conquer/on_death paths too:
  do any of them iterate `unit.gear` and fire the gear card's triggers? The
  broader trigger dispatch (loop.py:431 `_resolve_triggered_effects`, and the
  scoring/on_move call sites) all appear to pass `unit.card`, not gear.
- **Fix (Step 3 / engine correctness):** wherever unit triggers are fired, also
  iterate `unit.gear` and fire each gear card's matching trigger with the SAME
  battlefield context (so the gear's enemy_unit/"here" resolves correctly).
  Add a test: equip Recurve Bow, attack, assert 2 damage dealt to an enemy at
  that battlefield; move wearer, assert it follows the wearer (not the base).
- **Note:** this is an ENGINE gap, not a parser gap — no re-parse fixes it.
  Several "POPULATED" gear cards are currently inert for this reason; the
  coverage report should not count equipped-trigger gear as "fully playable"
  until this lands.
- **EXTENDED (found at Serrated Dirk, card 14): the KEYWORD case, same root.**
  Equipped gear KEYWORDS (ASSAULT, SHIELD, GANKING, ...) also fail to project
  onto the wearer. combat.py:162 reads ASSAULT via `keyword_value`, which checks
  the unit's own card keywords + `passive_keywords` only — NOT `unit.gear`
  keywords (verified: cards.py `keyword_value`/`has_keyword` and combat.py
  overrides all ignore attached gear). So Serrated Dirk's "ASSAULT 2" never
  reaches the wearer; the unit attacks at +0.
- **Unified fix:** "equipped gear acts through its wearer" has TWO facets that
  should be fixed together: (a) TRIGGERS — fire each `unit.gear` card's triggers
  in the wearer's combat/scoring context; (b) KEYWORDS — fold each gear card's
  keywords into the wearer's effective keyword lookup (has_keyword/keyword_value),
  or onto passive_keywords on attach. Tests: Serrated Dirk wearer attacks at
  +2 might; Recurve Bow wearer deals 2 on attack; both stop when the gear is
  removed / the wearer dies.

## 8. Recall always heals+exhausts; per rules a generic recall must NOT (found spot-check rescued)
- **Rule (user):** "Recalls do not affect the state of the Permanent being recalled.
  Unless otherwise stated by the source, Damage, Exhausted Status, Buffed Status,
  and applied Layer alterations remain UNAFFECTED by a Recall."
- **Engine:** `GameLoop._try_replace_death` performs reset_damage() (heal) +
  ready=False (exhaust) unconditionally on recall. That's correct for cards that
  STATE it (e.g. Soraka Wanderer: "heal it, exhaust it, recall it"), but wrong as
  a general recall primitive.
- **Fix (Step 3):** the generic recall verb (recall_unit / move-to-base) must
  preserve damage, exhausted, buff (might_counters), and layer alterations by
  default. Only reset the specific attributes a card explicitly names. Audit
  recall_unit and _try_replace_death: split "recall" (state-preserving) from
  Soraka-style "heal+exhaust+recall" (explicit resets).

## 9. `leaves_board` trigger distinct from `on_death` (found spot-check rescued)
- **What:** "When this leaves the board" fires on death AND on recall/bounce-to-hand
  (and banish). Engine currently only has on_death; cards like Treasure Trove parse
  "leaves the board" as on_death, missing the bounce/recall cases.
- **Fix (Step 3):** add a `leaves_board` (a.k.a. on_leave) trigger that fires on any
  zone-exit from the board (death, recall-to-base?, return-to-hand, banish), and
  re-parse affected cards. Clarify which exits count (base is still "on board"?).

## 10. `reduce_cost` verb missing but referenced by populated parses
- Ornn's Forge parsed with effect `reduce_cost` (trigger cost_modifier) — but NO
  `reduce_cost` handler exists in effects.py. Populated-but-inert. aura:reduce_cost
  is in the Step 3 queue (x6). Build the verb + a cost-modifier application path;
  until then these should be flagged, not emitted as populated.
