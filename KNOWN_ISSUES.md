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

## 9. (FIXED Step 3) `leaves_board` trigger distinct from `on_death`
**RESOLVED:** added a `leaves_board` trigger firing on any board exit (combat death + recall-to-hand wired; registered in engine_vocab). Test: test_leaves_board_fires_on_recall. Re-parse affected cards to route them off `on_death`.
- **What:** "When this leaves the board" fires on death AND on recall/bounce-to-hand
  (and banish). Engine currently only has on_death; cards like Treasure Trove parse
  "leaves the board" as on_death, missing the bounce/recall cases.
- **RULING (confirmed by user, spot-check rescued v2):** leaving the board is NOT dying —
  `leaves_board` fires on death AND recall AND bounce-to-hand AND banish (any board exit).
  So mapping it to `on_death` is definitively wrong, not merely narrow: recall/bounce cases
  are silently lost.
- **Fix (Step 3):** add a `leaves_board` (a.k.a. on_leave) trigger that fires on any
  board-exit (death, recall, return-to-hand, banish), and re-parse affected cards.

## 10. `reduce_cost` verb missing but referenced by populated parses
- Ornn's Forge parsed with effect `reduce_cost` (trigger cost_modifier) — but NO
  `reduce_cost` handler exists in effects.py. Populated-but-inert. aura:reduce_cost
  is in the Step 3 queue (x6). Build the verb + a cost-modifier application path;
  until then these should be flagged, not emitted as populated.

## Spot-check findings (rescued v2, 30/30 reviewed, 73% OK+MINOR+FLAGGED_OK)
Sample: `scripts/spot_check_rescued_v2.md` (same 30 "rescued" cards re-parsed under the
reinforced prompt). Recovery-floor sample of previously-hard cards, NOT an RNG-seeded
representative gate. Result: 1 OK + 11 MINOR + 10 FLAGGED_OK = 22/30 = **73.3% < 80%**.
Fail bucket = 6 MISSING_EFFECT + 1 WRONG_CONDITION + 1 FLAGGED_WRONG, dominated by the
parser dropping whole abilities on MULTI-CLAUSE cards (Nami, Cursed Sarcophagus, Treasure
Trove, Death from Below, Daisy!, Blood Money). Engine findings below.

## 11. (OPEN) `all_units_here` mis-resolves to opponent-only on the deal_damage path
- **Where:** `effects.py` `_deal_damage` (:24-28) -> `loop.py` `ctx.deal_damage`
  (:108-119), which maps only {actor,ally,self} to the friendly side; everything else
  (incl. `all_units_here`, `battlefield`, `both`) falls through to opponent_side.
- **What:** "deal N to EACH unit here" (both sides) hits only the OPPONENT's units at the
  battlefield. Friendly units here are never damaged. Found via **Frozen Fortress**.
- **Also:** `all_units_here` is resolved THREE inconsistent ways across the engine:
  `_units_for_target` (loop.py:104, FRIENDLY-only), `_target_side` (effects.py:231,
  OPPONENT-only for deal_damage), `_passive_targets` (loop.py:536, BOTH sides). Pick one
  canonical meaning ("both sides at this battlefield") and route deal_damage through a
  both-sides resolver (or add an `all_units_here` case to `ctx.deal_damage`).
- **Fix (Step 3):** make `ctx.deal_damage` honor a both-sides target; unify the three
  resolvers. Add a test: deal 1 to all_units_here damages friendly AND enemy units.

## 12. (FIXED Step 3) Triggered effects never pay `cost` / `additional_cost` (kicker)
**RESOLVED:** `_pay_triggered_cost` pays cost/additional_cost (pay-if-affordable) before the condition check, sets `_kicker_paid`; unaffordable → effect skipped. NB generic domainless [rune] power still isn't affordability-checked (pre-existing power-model gap). Test: test_triggered_kicker_paid_gates_effect.
- **Where:** `loop.py` `_resolve_triggered_effects` (:447-455) checks only `condition`
  then runs the handler. `_try_pay_additional_costs` / `_parse_activated_cost` are wired
  only into the play path and the activated-ability path, never into on_hold/on_attack/
  on_conquer/on_*-triggered effects.
- **What:** (a) optional/kicker costs on triggered abilities are silently skipped —
  "you MAY exhaust me" (Volibear) channels for free with no exhaust; "pay [rune]x4 to
  score on hold" (Power Nexus) is never paid, so a `kicker_paid` gate stays False and the
  score_point silently no-ops. (b) any triggered effect with a `cost` field is executed
  cost-free.
- **Fix (Step 3):** thread cost/additional_cost payment through `_resolve_triggered_effects`
  (pay-if-affordable for the baseline agents, set `_kicker_paid`), OR mark such abilities
  as "optional triggered" so the effect only fires when the cost is paid.

## 13. (FIXED Step 3) `banish_card` ignores `scope:"all"` and has no card-type filter
**RESOLVED:** honors scope:"all" + card-type target_filter (is_unit/is_spell/is_gear); end-order preserved for the count case. Test: test_banish_all_units_from_trash_leaves_non_units. (Replay-from-banish provenance still open.)
- **Where:** `effects.py` `_banish_card` (:611-622) reads `count` (default 1) and pops
  from one zone; it does not read `scope` and applies no unit/type filter.
- **What:** "Banish ALL units from your trash" (Cursed Sarcophagus) banishes ONE arbitrary
  card (could be a spell/gear). The paired "play a unit banished with this" tap ability is
  also unrepresented (needs a "banished-by-source" provenance tag + an activated replay).
- **Fix (Step 3):** honor `scope:"all"` (banish every matching card), add a `card_type`/
  `is_unit` filter, and add a provenance link so cards can replay "a unit banished with this".

## 14. (FIXED Step 3) `move_units_to_base` is all-friendly-at-BF only; no single / "exhausted" target
**RESOLVED:** routes through _resolve_targets (honors scope + is_exhausted filter); added is_exhausted/is_ready filters. Parser should route single "a unit" to move_unit. Test: test_move_units_to_base_only_exhausted.
- **Where:** `effects.py` `_move_units_to_base` (:138-146) moves EVERY friendly unit at
  ctx.battlefield to base, ignoring `target`/`scope`/filters.
- **What:** "Move an EXHAUSTED friendly unit ... to its base" (Kha'Zix Voidreaver, 3rd
  ability) over-moves (all instead of one) and can't restrict to exhausted units. A
  single-target `move_unit` (effects.py:433) already exists and is the better route for
  "move A unit to base".
- **Fix (Step 3):** parser should route single-unit "move to base" to `move_unit`; add a
  ready/exhausted target_filter (`is_exhausted`) for the "exhausted" restriction.

## 15. (FIXED Step 3) `this_is_mighty` checks the SOURCE card, not the triggering unit
**RESOLVED:** added `triggering_unit_is_mighty` condition + threaded the triggering card through _fire_units_trigger. Test: test_triggering_unit_is_mighty_uses_played_unit.
- **Where:** `loop.py` `_check_condition` (:634-635): `this_is_mighty` reads
  `card.might` where `card` is the effect's own source.
- **What:** on an `on_friendly_unit_played` trigger ("When you play a MIGHTY unit ...",
  Volibear), the gate should test the UNIT JUST PLAYED, but it tests Volibear's own might
  — so it fires on every unit played iff the source is 5+, else never. There is no
  condition that inspects the triggering unit, so the parser has no correct option today.
- **Fix (Step 3):** add a `triggering_unit_is_mighty` (and generally a triggering-unit
  context) so on_friendly_unit_played effects can gate on the played unit's stats.

## 16. (FIXED Step 3) `chosen_unit` wrongly filed under FRIENDLY aliases — narrows 82 effects to caster's side
**RESOLVED:** chosen_unit now resolves to a both-sides pool with a harmful/beneficial pick bias (kill/stun/exhaust/debuff pick enemy-first). Removed from _FRIENDLY_TARGET_ALIASES; safe fallback for non-unit callers. Tests: test_chosen_unit_kill_hits_enemy_not_own, test_chosen_unit_buff_hits_own_not_enemy.
- **DESIGN (confirmed by user):** `chosen_unit` = "player picks a unit"; unless the card
  text restricts to friendly/enemy, it may target EITHER side (incl. the caster's own).
  The parser is CORRECT to emit `chosen_unit` for an unrestricted "a unit". This is NOT a
  parser bug and does NOT need a new alias.
- **BUG (engine):** `loop.py` `_FRIENDLY_TARGET_ALIASES` (:85-88) lists `chosen_unit`, so
  `_player_for_target`/`_units_for_target` resolve it to the ACTOR's side. Every effect
  using it (`_resolve_targets` path: kill_unit, deal_damage-via-target, buff, stun, ...)
  is silently narrowed to friendly-only.
- **Blast radius:** `target=chosen_unit` appears on **72 cards / 82 effects** (Cleave,
  Disintegrate, Hextech Ray, Rune Prison, Void Seeker, Falling Star, Death from Below,
  Blood Money, ...). Enemy-facing removal/damage currently hits the CASTER's own units.
- **Fix (Step 3):** make `chosen_unit` resolve to a BOTH-SIDES candidate pool (remove it
  from `_FRIENDLY_TARGET_ALIASES`; add a chosen/both-sides branch in `_resolve_targets`
  before `_player_for_target` so it doesn't raise). Because Step 2 made the loop pausable,
  the correct resolution is a real player choice at a DecisionPoint over all units either
  side; the deterministic baseline needs a sane pick policy (a kill/damage spell must not
  auto-select the caster's own unit). `chosen_enemy` stays enemy-only; add/keep a
  friendly-only alias for cards whose text says "a friendly unit".
- NB: `_target_side` (effects.py:231) does NOT list `chosen_unit`, so score_point/gain_xp
  resolve it to OPPONENT — a second inconsistency to unify when this is fixed.

## 17. (FIXED Step 3) `kill_gear` ignores target/target_filter — always destroys ALL gear, both sides
**RESOLVED:** with a filter/single scope/chooser target, kills ONE matching gear (enemy-biased, energy_at_most/at_least filters); plain "kill all gear" still wipes. Test: test_kill_gear_single_energy_filter_enemy_first. (Optional "if you do" gate still open.)
- **Where:** `effects.py` `_kill_gear` (:389-405) loops every unit on both sides + both
  bases and clears all gear; `target`/`target_filter` (e.g. is_gear, energy<=1) are unused.
- **What:** "you may kill A gear" (Adaptatron) / "kill a gear with Energy cost <= 1"
  (Pickpocket) becomes a board wipe of ALL gear. Also there's no energy-cost filter key to
  express "<= 1", and no way to gate the follow-on ("if you do ...") on the optional kill.
- **Fix (Step 3):** make kill_gear honor target/scope (single chosen gear) + target_filter;
  add an energy-cost filter key; add an "if-you-did"/optional-resolution gate for the
  paired token spawn.

## 18. (FIXED Step 3) Passive grants ignore `target_filter` (and are BF-local, not board-wide)
**RESOLVED:** _apply_passive_grant applies target_filter; _passive_targets supports a board-wide scope for "your <X> units" anthems. Test: test_passive_anthem_only_tokens.
- **Where:** `loop.py` `_apply_passive_grant` (:543-572) resolves targets via
  `_passive_targets` (side at the source's battlefield) and folds might/keywords onto them
  WITHOUT applying any `target_filter`.
- **What:** "Your TOKEN units have +1 [might]" (Soul Shepherd) buffs ALL friendly units at
  the source's battlefield (non-tokens included) and only there, not the intended
  token-only, board-wide anthem.
- **Fix (Step 3):** apply target_filter inside the passive path (reuse `_passes_filter`),
  and support a board-wide scope for anthems that read "your <X> units" with no "here".

## 19. (PARTIAL) cast spells now routed to trash (a, FIXED); FLOW play-from-trash still deferred (b)
- **(a) FIXED:** `_run_chain`'s LIFO resolve loop (`loop.py`, after the `on_play_spell`
  trigger) now appends each resolved `SpellCard` to its caster's `trash` — spells no
  longer vanish. Countered spells are popped + trashed by `counter_spell` before the
  resolve loop, so there is no double-trash. Golden fixture regenerated (trash counts
  rise; 3/20 games shifted outcome because the agents' `_action_fingerprint` counts
  trash and trash-based card effects now have targets — expected, not a regression).
  `test_invariants.py` strengthened to full card conservation; new
  `test_effects.py::test_resolved_spell_goes_to_caster_trash`.
- **(b) OPEN:** FLOW (Vendetta) lets you play a spell from your TRASH for an alternate
  cost, then banish it. Now that (a) populates trash, FLOW targets exist; still missing:
  a new action source (`legality.py`) + `_apply_action` branch that pays the FLOW cost,
  plays from trash, and BANISHES after resolve (needs `ChainItem` provenance so the
  resolve loop banishes rather than trashes that instance). FLOW spells still work
  normally from hand; the replay permission is flagged (suggested_vocab "keyword:flow").
  Complex FLOW costs (Kennen "FLOW equal to its cost", Stargazer FLOW discount) need
  per-card handling.

## 20. (OPEN) EMPOWERED-modifier clauses and on-burn triggers deferred
- **What:** EMPOWER/EMPOWERED and BURN are implemented (empower_self / this_is_empowered
  passive bonuses / disempower; burn + cards_burned_this_turn). Two dependent sub-mechanics
  remain flagged by the parser rather than emitted:
  - An EMPOWERED clause that MODIFIES another ability ("deal 2 instead if I'm Empowered",
    "they have +2 instead") — needs a value-swap on a sibling effect (suggested_vocab
    "effect:empowered_modifier").
  - A "when a card is burned / when you burn" trigger (suggested_vocab "trigger:on_burn").
- **Fix (future):** add an empowered-conditional amount/override on effects; add an on_burn
  trigger fired from Player.burn / the burn effect.
