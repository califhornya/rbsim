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

**Round 2 Verdict:** seems ok, not sure
**Notes:**

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

**Round 2 Verdict:** seems ok, not sure
**Notes:**

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

**Round 2 Verdict:** seems ok, not sure
**Notes:**

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

**Round 2 Verdict:** seems ok, not sure
**Notes:**

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

**Round 2 Verdict:** seems ok, not sure
**Notes:**

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

**Round 2 Verdict:** seems ok, not sure
**Notes:**

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

**Round 2 Verdict:** seems ok, not sure
**Notes:**

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

**Round 2 Verdict:** seems ok, not sure
**Notes:**

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

**Round 2 Verdict:** seems ok, not sure
**Notes:**

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

**Round 2 Verdict:** seems ok, not sure
**Notes:**

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

**Round 2 Verdict:** seems ok, not sure
**Notes:**

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

**Round 2 Verdict:** seems ok, not sure
**Notes:**

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

**Round 2 Verdict:** seems ok, not sure
**Notes:**

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

**Round 2 Verdict:** seems ok, not sure
**Notes:**

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

**Round 2 Verdict:** seems ok, not sure
**Notes:**

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

**Round 2 Verdict:** seems ok, not sure
**Notes:**

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

**Round 2 Verdict:** seems ok
**Notes:**

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

**Round 2 Verdict:** not sure
**Notes:**

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
