# Spot-check Round 2 — re-verification of the 18 re-parsed cards

The 7 BAD + 11 MINOR cards from round 1 had their `effects[]` cleared and were
re-parsed under the reinforced system prompt + the new B1/B2 engine features.

Counts: **7/18 came back populated**, **11/18 stayed empty** — the empties are
the reinforced prompt correctly refusing to produce wrong parses for mechanics
the engine doesn't support yet (Phase C candidates).

For each card you'll see your **round-1 verdict & notes** on top and the **new
parse** below. Fill **Round 2 Verdict** with one of:
`OK`, `MINOR`, `WRONG_TRIGGER`, `WRONG_TARGET`, `WRONG_AMOUNT`, `WRONG_FILTER`,
`MISSING_EFFECT`, `PHANTOM_EFFECT`, `MISSING_CONDITION`, `UNCERTAIN`,
`FLAGGED_OK` (empty parse is acceptable — mechanic genuinely unsupported), or
`FLAGGED_WRONG` (empty parse but we *could* have parsed it).

Then run `uv run python scripts/spot_check_summary.py` against this file too.

---

## BAD cards (round 1)

### [BAD] Sprite Fountain (Unleashed, Gear)

**Raw effect:** TEMPORARY (Kill this at the start of its controller's Beginning Phase, before scoring.) When you play this, play a ready 3 [might] Sprite unit token with TEMPORARY to your base. DEATHKNELL[>] Repeat this gear's play effect. (When this dies, get the effect.)

**Round 1 verdict:** WRONG_AMOUNT — "il 3 penso che si intenda il might del token. il token sprite ha sempre 3 might quindi serve solo dire 'crea uno Sprite'"
**Round 1 notes:** il deathknell fa morire il Gear (Sprite Fountain) il turno successivo a quello in cui lo si gioca. uno ora, uno prossimo turno.

**New parsed effects:**
```json
[]
```
**New parsed keywords:** ["TEMPORARY", "DEATHKNELL"]
**Status:** EMPTY (flagged)

**Round 2 Verdict:** FLAGGED_WRONG
**Notes:** Keywords correct. Empty is not justified — engine supports both halves: play_token (ready Sprite to base) on_play, and on_death (DEATHKNELL) to repeat the spawn. Parser should emit on_play->play_token(Sprite, ready) + on_death->play_token(Sprite, ready). The printed "3" is just the Sprite's fixed might; spec should name the token, not the stat.

---

### [BAD] Kai'Sa Daughter of the Void (Origins, Legend)

**Raw effect:** [tap] REACTION - ADD [rune]. Use only to play spells. (Abilities that add resources can't be reacted to.)

**Round 1 verdict:** WRONG_FILTER — "Questa abilità aggiunge 1 Power di qualsiasi domain da spendere solo per Spells."

**New parsed effects:**
```json
[]
```
**New parsed keywords:** ["REACTION"]
**Status:** EMPTY (flagged — expected, `gain_power` verb not yet in engine)

**Round 2 Verdict:** FLAGGED_OK
**Notes:** Empty is honest — gain_power_any_domain not in engine yet (Step 3 queue). SPEC REQ for that build: the added power is spendable ON SPELLS ONLY — not units, not ability activation. A generic "add 1 power any domain" verb would be too permissive and make Kai'Sa wrong. The spell-only spend restriction must be modeled.

---

### [BAD] Shurelya's Requiem (Spiritforged, Signature Gear)

**Raw effect:** UNIQUE (Your deck can have only 1 card with this name.) EQUIP [rune] ([rune]: Attach this to a unit you control.) When you play this, ready your units.
**Raw effect (equipped):** Your units here have GANKING (We can move from battlefield to battlefield.)

**Round 1 verdict:** WRONG_TRIGGER, on_play — "equip costa 1 power solo, errore di parsing. Manca anche tutta la parte di effetto quando equipaggiato. la unit equipaggiata e quelle nella sua stessa location guadagnano la keyword GANKING."

**New parsed effects:**
```json
[]
```
**New parsed keywords:** ["EQUIP 1"]
**Status:** EMPTY (flagged — `EQUIP 1` fix landed, but the rest needs engine work)

**Round 2 Verdict:** FLAGGED_WRONG
**Notes:** EQUIP 1 cost correct. But empty is NOT justified — the "needs engine work" note is stale; engine now supports both halves. (1) on_play "ready your units" -> ready_units verb exists (effects.py:53). (2) equipped aura "unit + its location gain GANKING" -> give_keyword exists (effects.py:448) AND passive/aura folding exists (loop.py:552, passive give_keyword). Targeted re-parse should emit on_play->ready_units(friendly) + equipped passive give_keyword(GANKING) scoped to the unit's location.

---

### [BAD] Danger Zone (Spiritforged, Signature Spell)

**Raw effect:** REACTION (Play any time, even before spells and abilities resolve.) REPEAT [1] [rune] (You may pay the additional cost to repeat this spell's effect.) Give your Mechs +1 [might] this turn.

**Round 1 verdict:** MISSING_TIMING reaction, MISSING_KEYWORD REPEAT, MISSING_TRIGGER on_cast

**New parsed effects:**
```json
[]
```
**New parsed keywords:** ["REACTION", "REPEAT"]
**Status:** EMPTY — REPEAT + REACTION captured as keywords, but "give your Mechs +N might" needs `target_filter:{subtype:"Mech"}` + an all-friendlies-anywhere target that doesn't exist yet.

**Round 2 Verdict:** FLAGGED_OK
**Notes:** Empty justified. Confirmed against engine: buff_unit exists (effects.py:195) and subtype filter exists (effects.py:275, checks against card tags), so "+1 might to Mechs" is half-ready. BLOCKER is real: "your Mechs" = all friendly Mechs anywhere, and all_friendly_units_anywhere target does NOT exist yet (Step 3 queue top item, x12). Once that target lands this is a one-line re-parse: buff_unit(+1, this_turn) target=all_friendly_anywhere filter subtype=Mech. Keywords REACTION+REPEAT correct.

---

### [BAD] Grand Strategem (Origins, Spell)

**Raw effect:** Give friendly units +5 [might] this turn.

**Round 1 verdict:** WRONG_TARGET — "all_friendly_units_here, non 'here', a tutte."

**New parsed effects:**
```json
[]
```
**New parsed keywords:** []
**Status:** EMPTY — exactly the case my few-shot example targeted; "all friendlies anywhere" needs a new engine target.

**Round 2 Verdict:** FLAGGED_OK
**Notes:** Empty is correct, but for a DEEPER reason than the status line says. TWO blockers, not one:
(1) all_friendly_units_anywhere target missing (Step 3 queue, x12) — known.
(2) NAMING TRAP: the engine's `buff_unit` verb models the Riftbound BUFF OBJECT (non-stacking, max 1, might_counters += 1, ignores amount) — that's the Arena Bar mechanic. Grand Strategem is NOT a Buff — it's a raw "+5 might this turn" modifier (like Discipline). There is currently NO engine verb for a raw temporary might modifier. Parsing "+5 might" into buff_unit would be WRONG (caps at +1, places a Buff object, would trip is_buffed conditions).
ENGINE SPEC REQ for Step 3: add a distinct verb (e.g. `grow_might` / `modify_might`) for raw might modifiers, separate from `buff_unit` (=place Buff object). Grand Strategem/Discipline use the new verb; Arena Bar uses buff_unit. Keep them separate. See card-5 discussion for the full rationale.

---

### [BAD] Rocket Barrage (Spiritforged, Spell)

**Raw effect:** REPEAT [4] [mind] (You may pay the additional cost to repeat this spell's effect, and may make different choices.) Choose one — • Deal 4 damage to a unit in a base. • Kill a gear.

**Round 1 verdict:** WRONG — "puoi scegliere se fare 4 danni a una unit nemica in base (solo in base) oppure distruggere un gear nemico. Se la gioco RIPETUTA posso riscegliere..."

**New parsed effects:**
```json
[]
```
**New parsed keywords:** ["REPEAT"]
**Status:** EMPTY — "choose one" not engine-supported; correctly flagged.

**Round 2 Verdict:** FLAGGED_OK
**Notes:** Empty is honest — mode_choice / "choose one" has NO engine representation (confirmed absent). Step 3 queue x7. Good news: both branch verbs already exist — deal_damage (effects.py:24) and kill_gear (effects.py:389) — so mode_choice is a contained build: a chooser wrapper over existing verbs, not new effect logic. Nuances to preserve when built: (a) damage branch targets a unit IN A BASE only (base-restricted target); (b) REPEAT lets you re-pick the mode on each repeat. Keyword REPEAT correct.

---

### [BAD] Blast Corps Cadet (Spiritforged, Unit)

**Raw effect:** You may pay [1] [fury] as an additional cost to play me. When you play me, if you paid the additional cost, deal 2 to a unit at a battlefield.

**Round 1 verdict:** MISSING_CONDITION — "se ho pagato il costo addizionale sparerò 2 danni, se no no."

**New parsed effects:**
```json
[
  {
    "effect": "deal_damage",
    "trigger": "on_play",
    "amount": 2,
    "target": "chosen_unit",
    "condition": {"type": "kicker_paid"},
    "additional_cost": {"power": 1}
  }
]
```
**New parsed keywords:** []
**Status:** POPULATED ✓ — B1 kicker fully wired. Note: `additional_cost.power: 1` reflects the [1] [fury] reading as a POWER cost (which it is). My few-shot example in the prompt used `energy` — that was misleading; the model picked the more accurate `power` key anyway.

**Round 2 Verdict:** MINOR
**Notes:** Kicker (additional_cost power:1), kicker_paid condition, and deal_damage amount:2 all CORRECT. One issue: target "chosen_unit" is too broad. Card says "a unit AT A BATTLEFIELD" = cannot hit units in base. Engine gap confirmed: _resolve_targets honors side + target_filter (unit properties) but has NO location filter — nothing distinguishes battlefield units from base units. Fix (Step 3): add a location restriction (a `battlefield_unit` target or a target_filter key like location:"battlefield"), then re-parse this card's target. Effect is otherwise right — MINOR, not WRONG.

---

## MINOR cards (round 1)

### [MINOR] Navori Fighting Pit (Origins, Battlefield)

**Raw effect:** When you hold here, buff a unit here. (If it doesn't have a buff, it gets a +1 [might] buff.)

**Round 1 verdict:** Minor — "manca clausola 'here', quello che proponi qui è probabilmente un battlefield..."

**New parsed effects:**
```json
[]
```
**New parsed keywords:** []
**Status:** EMPTY — regression vs round 1's populated parse. Likely the prompt's "don't add `here` unless text says so" guidance conflicted with the actual text which DOES say "here". Suspect over-flagging.

**Round 2 Verdict:** FLAGGED_WRONG
**Notes:** All pieces exist — this is a regression, not a real block. (1) on_hold trigger exists and fires at scoring (loop.py:29, :330); for a battlefield card it's inherently "here". (2) all_friendly_units_here target exists (effects.py:233). (3) buff_unit is the CORRECT verb here — this card genuinely places a BUFF OBJECT ("if it doesn't have a buff, it gets a +1 might buff", max 1) — contrast Grand Strategem which needed a raw modifier. Correct parse: trigger on_hold -> buff_unit target=all_friendly_units_here scope=single. PARSER-PROMPT BUG: the "don't add here unless text says so" guidance over-corrected on text that explicitly says "here" — needs softening (see below). Re-parse should repopulate.

---

### [MINOR] Trifarian War Camp (Origins, Battlefield)

**Raw effect:** Units here have +1 [might] . (Including attackers.)

**Round 1 verdict:** minor — "'duration: permanent' vero fino a che sono su questo battlefield."

**New parsed effects:**
```json
[
  {
    "effect": "grant_might",
    "trigger": "passive",
    "target": "all_units_here",
    "amount": 1
  }
]
```
**New parsed keywords:** []
**Status:** POPULATED — switched from `buff_unit` to `grant_might`, dropped `duration: permanent` (addresses your concern).

**Round 2 Verdict:** MINOR
**Notes:** Verb + mechanism CORRECT: grant_might (effects.py:31) folded as a passive (loop.py:485 _recompute_passives) = continuous +1 that stops when a unit leaves — exactly right, and the switch off buff_unit + dropping duration:permanent was the right call. BUG: target "all_units_here" resolves to NEITHER the friendly set NOR _BOTH_SIDES_TARGETS ({battlefield,both,both_players,everyone,all_units}, effects.py:296) — so it silently falls through to friendly-only. User confirms this card grants +1 to ALL units here, BOTH players. TARGET GAP: no existing key means "both sides AND here" (all_friendly_units_here = here but friendly; all_units/battlefield = both sides but not here-scoped). Step 3: add a both-sides-here target (e.g. all_units_here registered into the both-sides + here path), then re-parse. MINOR — one wrong target key on an otherwise correct passive.

---

### [MINOR] Windswept Hillock (Origins, Battlefield)

**Raw effect:** Units here have Ganking . (They can move battlefield to battlefield.)

**Round 1 verdict:** Minor — "ho aggiunto Ganking alle keyword non perché il battlefield abbia ganking ma perché effettivamente c'è"

**New parsed effects:**
```json
[
  {
    "effect": "give_keyword",
    "trigger": "passive",
    "target": "all_units_here",
    "keyword": "GANKING"
  }
]
```
**New parsed keywords:** []  *(was ["GANKING"] in round 1)*
**Status:** POPULATED — fixed: GANKING no longer (incorrectly) on the battlefield's own keywords.

**Round 2 Verdict:** MINOR
**Notes:** Verb correct: give_keyword as passive (effects.py:448 + passive_keywords fold loop.py:552) — units here continuously have GANKING, stops when they leave. Round-1 fix (GANKING off the battlefield's own keywords into a proper grant) was right. SAME BUG as Trifarian War Camp: target "all_units_here" resolves friendly-only (not in _BOTH_SIDES_TARGETS). User confirms this grants GANKING to ALL units here, BOTH players. Same fix: add a both-sides-here target, re-parse. MINOR.

---

### [MINOR] Yasuo Remorseful (Origins, Champion)

**Raw effect:** When I attack, deal damage equal to my Might to an enemy here.

**Round 1 verdict:** Minor — "'on_attack' verifica che il gioco gestisca correttamente la dichiarazione di attaccanti e difensori..."

**New parsed effects:**
```json
[
  {
    "effect": "deal_damage",
    "trigger": "on_attack",
    "target": "enemy_unit",
    "amount_source": "self_might"
  }
]
```
**New parsed keywords:** []
**Status:** POPULATED — identical to round 1 (your concern was an engine question, not a parse error).

**Round 2 Verdict:** OK
**Notes:** All pieces verified: on_attack trigger exists and fires in combat (loop.py:1518); self_might amount_source exists (effects.py:341); enemy_unit resolves. "An enemy here" IS correctly enforced — verified the mechanism: enemy_unit -> _units_for_side -> `self.battlefield.units_A/B` (SINGULAR battlefield = the one carried in the effect context). For an on_attack trigger, ctx.battlefield IS the battlefield Yasuo is attacking, so enemy_unit = enemies at THAT battlefield only, not global. Here-scoping holds by construction for combat/scoring triggers. Round-1 note was an engine-behavior question (attacker/defender declaration), not a parse error. Clean OK — but note the location correctness comes from the CONTEXT being one battlefield, not from the target key (see KNOWN_ISSUES #6 refinement).

---

### [MINOR] Poro Snax (Spiritforged, Gear)

**Raw effect:** When you play this, draw 1. [1] [calm], [tap], Kill this: Draw 1.

**Round 1 verdict:** Minor, MISSING_TRIGGER — "on_play per la prima parte, activated per la seconda. 'kill this' è un trigger di attivazione per pescare ulteriormente 1"

**New parsed effects:**
```json
[]
```
**New parsed keywords:** []
**Status:** EMPTY — the activated cost includes `kill_self` which isn't a known activated-cost key (engine parses 6 keys; `kill_self` is not one of them). Possibly over-conservative: the on_play `draw 1` alone is parseable.

**Round 2 Verdict:** FLAGGED_WRONG
**Notes:** PARTIAL-PARSE failure. Card has TWO independent abilities: (1) on_play "draw 1" — fully parseable NOW (draw_cards exists, effects.py:38, no exotic cost). (2) activated "[1][calm][tap] Kill this: draw 1" — blocked, kill_self is NOT in KNOWN_ACTIVATED_COST_KEYS (the 6: energy/power/tap/recycle/sacrifice/spend_xp; engine_vocab.py:92). Per the project's own partial-parse rule, the parser should emit ability (1) and flag only (2). Emitting [] discards a working ability. Fix: re-parse with partial-parse enforced -> on_play draw_cards(1); flag activated half for cost:kill_self (Step 3 queue x4). CHECK: does existing `sacrifice` cost key accept self ("Kill this" = sacrifice self)? If so the activated half is nearly ready; if `sacrifice` means target-only, kill_self is the needed addition.

---

### [MINOR] Recurve Bow (Spiritforged, Gear)

**Raw effect:** EQUIP [fury] ([fury]: Attach this to a unit you control.)
**Raw effect (equipped):** When I attack or defend, deal 2 to an enemy unit here.

**Round 1 verdict:** Minor — "il danno applicato deve essere su una unit 'here'"
**Round 1 notes:** per questa carta Equip costa solo 1 power, non 2

**New parsed effects:**
```json
[
  {"effect": "deal_damage", "trigger": "on_attack", "amount": 2, "target": "enemy_unit"},
  {"effect": "deal_damage", "trigger": "on_defend", "amount": 2, "target": "enemy_unit"}
]
```
**New parsed keywords:** ["EQUIP 1"]
**Status:** POPULATED — `EQUIP 1` corrected (was 2); `target: enemy_unit` IS the "here" semantics per the parser convention (the engine resolves `enemy_unit` against the current battlefield).

**Round 2 Verdict:** MINOR
**Notes:** PARSE is faithful: EQUIP 1 correct (matches your round-1 note), on_attack/on_defend deal_damage 2, target enemy_unit correctly here-scoped via combat context (same mechanism as Yasuo). BUT — found a systemic ENGINE GAP that makes these specs DEAD: the combat trigger loop (loop.py:1516-1521) fires on_attack/on_defend only on `unit.card` — it iterates units at the battlefield and resolves THEIR triggers, and does NOT iterate each unit's attached `gear` cards. So an equipped gear's "when I attack/defend..." never fires. Parse is right; engine can't execute it. This likely affects EVERY "when equipped, when I attack/defend/etc." gear. Logged as KNOWN_ISSUES #7. Verdict MINOR (parse correct); real work is the engine fix, not a re-parse.

---

### [MINOR] Serrated Dirk (Spiritforged, Gear)

**Raw effect:** EQUIP [fury] ([fury]: Attach this to a unit you control.)
**Raw effect (equipped):** ASSAULT 2 (+2 might while I'm an attacker.)

**Round 1 verdict:** Minor
**Round 1 notes:** per questa carta Equip costa solo 1 power, non 2

**New parsed effects:**
```json
[]
```
**New parsed keywords:** ["EQUIP 1", "ASSAULT 2"]
**Status:** EMPTY but probably FLAGGED_OK — `EQUIP 1` corrected; equipped effect is a pure keyword grant (ASSAULT 2) so empty `effects[]` is arguably correct (engine grants ASSAULT via the gear's keywords on attach).

**Round 2 Verdict:** MINOR
**Notes:** EQUIP 1 correct; ASSAULT 2 correctly captured as a keyword (empty effects[] is right — ASSAULT is a keyword, not an effect-spec). BUT the status-line claim "engine grants ASSAULT via the gear's keywords on attach" is FALSE. Verified: combat reads ASSAULT via keyword_value (combat.py:162), which checks the unit's OWN card keywords + passive_keywords — NOT attached gear keywords (cards.py keyword_value / combat.py keyword_value both ignore unit.gear). So Serrated Dirk's ASSAULT 2 sits on the gear card and the wearer never inherits it → wearer attacks with +0. Card is INERT. Same root cause as Recurve Bow (#7): equipped gear doesn't project onto the wearer — here it's the KEYWORD case (vs the trigger case). Extended KNOWN_ISSUES #7. Parse/keywords fine (MINOR); the fix is engine-side, no re-parse.

---

### [MINOR] Viktor Herald of the Arcane (Origins, Legend)

**Raw effect:** [1] , [tap] : Play a 1 [might] Recuit unit token.

**Round 1 verdict:** Minor — "la Recruit token ha sempre might 1, quindi basta specificare solo quale token mettere in play, poi i token hanno sempre gli stessi dati/parametri."

**New parsed effects:**
```json
[
  {
    "effect": "play_token",
    "trigger": "activated",
    "timing": "action",
    "cost": {"energy": 1, "tap": true},
    "params": {"token_name": "Recruit"}
  }
]
```
**New parsed keywords:** []
**Status:** POPULATED — fixed exactly as you asked: just `token_name`, no redundant might.

**Round 2 Verdict:** OK
**Notes:** Verified end-to-end functional (not just parsed). activatable_abilities (loop.py:1153) collects a unit/legend's trigger:activated effects and _apply_activated_ability (loop.py:1093) dispatches them; _parse_activated_cost handles energy+tap (both in the valid 6); play_token resolves (confirmed card 1). Params exactly as requested: token_name:"Recruit", no redundant might. Contrast the gear cases (#7) — unit/legend activated dispatch works fine; it's the gear path that's broken. Clean OK.

---

### [MINOR] Super Mega Death Rocket! (Origins, Signature Spell)

**Raw effect:** Deal 5 to a unit. When you conquer, you may discard 1 to return this from your trash to your hand.

**Round 1 verdict:** Minor — "return_from_trash e dove va? a volte può andare in mano, a volte in campo, manca specifica."

**New parsed effects:**
```json
[]
```
**New parsed keywords:** []
**Status:** EMPTY — regression. Round 1 had both effects parsed. The `return_from_trash` cost mechanism (`additional_cost: {discard_cards: 1}` on a trigger:on_conquer effect) may have triggered the flag if the prompt didn't connect that pattern.

**Round 2 Verdict:** FLAGGED_WRONG
**Notes:** Partial-parse REGRESSION — more parseable than the status line assumed. Part 1 "deal 5 to a unit" = deal_damage amount 5 (exists), trivially parseable NOW. Part 2 pieces ALSO all exist: on_conquer trigger (engine_vocab:18) + return_from_trash verb (effects.py:480) which moves a card trash->HAND (line 498 player.hand.append) — exactly right, and this RESOLVES your round-1 "where does it go?" concern (it goes to hand). Only genuinely fiddly bit: the OPTIONAL discard cost on a triggered effect ("you MAY discard 1 to return") — an additional_cost:{discard:1} on a trigger (vs on-play). Confirm optional-cost-on-trigger support in Step 3. Regardless, full-empty is wrong: re-parse should at minimum emit the deal-5, ideally the full card. FLAGGED_WRONG.

---

### [MINOR] Upstage Comedy (Unleashed, Spell)

**Raw effect:** REPEAT 2 (You may pay the additional cost to repeat this spell's effect.) Ready a unit.

**Round 1 verdict:** Minor — "La keyword in realtà è 'REPEAT' senza il valore... Ovviamente se ripetuta, I will ready 2 units."

**New parsed effects:**
```json
[
  {"effect": "ready_unit", "trigger": "on_cast", "target": "chosen_unit"}
]
```
**New parsed keywords:** ["REPEAT"]
**Status:** POPULATED — exactly your request: bare `REPEAT` keyword; engine defaults REPEAT cost to `card.cost_energy` (tested via `tests/test_repeat_cost.py`).

**Round 2 Verdict:** OK
**Notes:** ready_unit exists (effects.py:122); on_cast correct; "ready 2 if repeated" handled by REPEAT re-running the effect. RULES CONFIRMED (user): a spell's REPEAT cost = the spell's own cost UNLESS the card states otherwise. So engine logic is exactly right: bare REPEAT -> cost_energy; "REPEAT N" -> override N for exceptions (loop.py ~:900). Upstage Comedy printed "REPEAT 2" and cost_energy=2 (not an exception), so bare REPEAT is correct here. PARSER-HARDENING note (not blocking): parser should store bare REPEAT only when printed value == cost_energy; if they differ, store "REPEAT N" — so correctness doesn't rely on the parser silently having matched them. Clean OK.

---

### [MINOR] Sprite Queen (Unleashed, Unit)

**Raw effect:** When you play me or at the of your Beginning Phase, play a ready 3 [might] Sprite unit token with TEMPORARY to your base. (kill them at the start of the controller's Beginning Phase, before scoring.)

**Round 1 verdict:** Minor, ricorda l'appunto fatto sui token precedentemente

**New parsed effects:**
```json
[]
```
**New parsed keywords:** []
**Status:** EMPTY — regression. Round 1 had both `play_token` triggers parsed. The reinforced prompt's "omit redundant token specs" guidance may have caused over-flagging when the model couldn't decide what to keep.

**Round 2 Verdict:** FLAGGED_WRONG
**Notes:** Regression — fully parseable. Sibling of Sprite Fountain (card 1), same Sprite token. Both triggers exist: on_play (confirmed) + on_start_of_turn ("at the start of your Beginning Phase" — engine_vocab:22, fires at loop.py:1656 _fire_turn_trigger). play_token exists (effects.py:516), supports ready + to-base + TEMPORARY. Correct parse: TWO effects, trigger on_play AND trigger on_start_of_turn, each play_token(Sprite, ready=true, keyword=TEMPORARY, target=base). Round-1 note was just the "name the token, don't over-spec the 3 might" point (Sprite = fixed 3 might). Re-parse should repopulate both triggers. Same parser-prompt over-correction pattern as Navori/SMDR/Sprite Fountain — the "omit redundant / don't add here" guidance is dropping valid effects.

---

## Summary of round-2 results

- **POPULATED (7):** Blast Corps Cadet (kicker now works), Trifarian War Camp,
  Windswept Hillock, Yasuo Remorseful, Recurve Bow (EQUIP fixed), Viktor Herald
  of the Arcane (clean token spec), Upstage Comedy (bare REPEAT).
- **EMPTY but likely acceptable** (correctly refusing wrong parse): Kai'Sa,
  Shurelya's Requiem, Danger Zone, Grand Strategem, Rocket Barrage,
  Serrated Dirk.
- **EMPTY — regression suspects** (round 1 had a parse, now blank): Sprite
  Fountain, Navori Fighting Pit, Poro Snax, Super Mega Death Rocket!,
  Sprite Queen. These likely need a more permissive prompt for `play_token`,
  `return_from_trash`, and `buff_unit` mechanics that ARE engine-supported.
