# Spot-check v2 — re-grade after parser reinforcement

Same 30 gate-sample cards, re-parsed under the reinforced prompt + completeness
heuristic. **v1 Verdict** is shown for reference; fill **v2 Verdict** with the same
taxonomy (OK / MINOR / WRONG_* / MISSING_* / PHANTOM_EFFECT / MISSING_CONDITION /
UNCERTAIN / FLAGGED_OK = empty-but-correctly-refused / FLAGGED_WRONG = empty-but-
was-parseable). Gate: OK + MINOR + FLAGGED_OK >= 80%.

---

### Frozen Fortress

**Raw:** At the start of each player's Beginning Phase, deal 1 to each unit here. (This happens before scoring.)

**New effects:**
```json
[
  {
    "effect": "deal_damage",
    "trigger": "on_start_of_turn",
    "target": "all_units_here",
    "amount": 1
  }
]
```
**New keywords:** []
**v1 Verdict:** MINOR

**v2 Verdict:** MINOR
**Notes:** Verb deal_damage OK, amount 1 OK. target `all_units_here` is the right LABEL for "each unit here", but engine mis-resolves it: `_deal_damage`->`ctx.deal_damage` (loop.py:108-119) maps only {actor,ally,self} to friendly, so `all_units_here` hits OPPONENT units only, not both sides (see new KNOWN_ISSUES #11). Also "each player's Beginning Phase" (fires on BOTH turns) can't be expressed: `on_start_of_turn` fires only for gs.active (loop.py:1656). Parser did best-available; engine gaps logged.

---

### Ornn's Forge

**Raw:** When you control this battlefield, the first friendly non-token gear played each turn costs [1] less.

**New effects:**
```json
[
  {
    "effect": "reduce_cost",
    "trigger": "cost_modifier",
    "amount": 1,
    "target_filter": {
      "is_gear": true,
      "non_token": true
    }
  }
]
```
**New keywords:** []
**Flagged this run:** first-per-turn gear cost reduction while controlling battlefield; aura reduces other cards
**v1 Verdict:** MISSING_EFFECT

**v2 Verdict:** MINOR
**Notes:** reduce_cost + is_gear + non_token is the natural encoding of "non-token gear costs 1 less". Missed clauses: "first ... each turn" limiter and "while you control this battlefield" gate. Engine can't apply it anyway — `_cost_reduction` (loop.py:669-686) self-reduces only; auras on OTHER cards + target_filter on cost_modifier are ignored (already KNOWN_ISSUES #4/#10). Parse acceptable, engine gap pre-logged.

---

### Power Nexus

**Raw:** When you hold here, you may pay [rune] [rune] [rune] [rune] to score 1 point.

**New effects:**
```json
[
  {
    "effect": "score_point",
    "trigger": "on_hold",
    "amount": 1,
    "additional_cost": {
      "power": 4
    },
    "condition": {
      "type": "kicker_paid"
    }
  }
]
```
**New keywords:** []
**Flagged this run:** score-point via optional rune payment on hold; additional_cost only supports up to power domain payment
**v1 Verdict:** OK

**v2 Verdict:** OK
**Notes:** Faithful encoding: score_point on_hold, amount 1, additional_cost power:4 (4 generic runes), gated on kicker_paid. A cost-aware engine executes this correctly. NB engine gap: `_resolve_triggered_effects` (loop.py:447-455) never pays cost/additional_cost, so on-hold kicker is not paid and kicker_paid stays False -> effect silently no-ops (new KNOWN_ISSUES #12). Parser is not at fault.

---

### Fizz Trickster

**Raw:** When you play me, you may play a spell from your trash with Energy cost no more than [3], ignoring its Energy cost. Recycle that spell after you play it. (You must still pay its Power cost.)

**New effects:**
```json
[]
```
**New keywords:** []
**Flagged this run:** Play a spell from trash ignoring energy cost then recycle it; no matching verb
**v1 Verdict:** MINOR

**v2 Verdict:** FLAGGED_OK
**Notes:** Empty is correct. "Play a spell from trash ignoring its ENERGY cost (still pay POWER), then recycle it" is not faithfully representable: `play_from_trash` (effects.py:588) routes non-units to HAND (does not cast) and has no cost-ignore/partial-cost logic. Mechanic genuinely unsupported -> refusing is right.

---

### Kha'Zix Mutating Horror

**Raw:** AMBUSH (You may play me as a REACTION to a battlefield where you have units.) When I attack or defend, if an enemy unit is alone here, give me +2 [might] this turn and gain 2 XP.

**New effects:**
```json
[]
```
**New keywords:** ['AMBUSH']
**Flagged this run:** trigger fires on attack OR defend and gated on enemy-alone-here which is not supported; unknown condition type 'enemy_is_alone'; unknown condition type 'enemy_is_alone'
**v1 Verdict:** WRONG_CONDITION

**v2 Verdict:** FLAGGED_OK
**Notes:** Empty is defensible. Effects (grant_temporary_might, gain_xp) exist and AMBUSH was captured, but they're gated on "an enemy unit is alone here" — there is no enemy-alone condition (this_is_alone = FRIENDLY side, loop.py:628-633). Emitting the buff/XP ungated would fire wrongly; refusing avoids a false-positive. Condition genuinely unsupported.

---

### Nami Headstrong

**Raw:** You may pay [calm] as an additional cost to play me. When you play me, if you paid the additional cost, STUN an enemy unit. (It doesn't deal combat damage this turn.) When I hold, the next time you play a unit this turn, ready it and BUFF it.

**New effects:**
```json
[
  {
    "effect": "stun_unit",
    "trigger": "on_play",
    "target": "enemy_unit",
    "condition": {
      "type": "kicker_paid"
    },
    "additional_cost": {
      "power": 1
    }
  }
]
```
**New keywords:** []
**Flagged this run:** when-I-hold delayed next-unit ready and buff not supported
**v1 Verdict:** MISSING_EFFECT

**v2 Verdict:** MISSING_EFFECT
**Notes:** First ability captured well: stun_unit on_play enemy_unit, additional_cost power:1 ([calm]), condition kicker_paid — all valid. But the SECOND whole ability "When I hold, the next time you play a unit this turn, ready it and BUFF it" is dropped entirely (no delayed-next-unit trigger). Whole clause missing -> not acceptable.

---

### Soraka Wanderer

**Raw:** I must be assigned combat damage last. If another unit you control here would die, if it has less Might than me, instead heal it, exhaust it, and recall it. (Send it to base. This isn't a move.)

**New effects:**
```json
[]
```
**New keywords:** []
**Flagged this run:** must-be-assigned-damage-last and conditional death-replacement heal/exhaust/recall for lower-might allies not supported
**v1 Verdict:** MINOR

**v2 Verdict:** FLAGGED_OK
**Notes:** Empty is correct. "Must be assigned combat damage last" + conditional death-replacement (heal+exhaust+recall an OTHER lower-might ally) is not faithfully supported: replace_death_with_recall/prevent_death exist but not the multi-action, might_less_than_self, other-unit death replacement. Refusing is right.

---

### Assembly Rig

**Raw:** [1] [fury], Recycle a unit from your trash, [tap]: Play a 3 [might] Mech unit token to your base.

**New effects:**
```json
[
  {
    "effect": "play_token",
    "trigger": "activated",
    "timing": "action",
    "token_name": "Mech",
    "cost": {
      "energy": 1,
      "power": 1,
      "tap": true
    }
  }
]
```
**New keywords:** []
**Flagged this run:** Cost includes recycling a unit from trash; no matching cost key
**v1 Verdict:** OK

**v2 Verdict:** MINOR
**Notes:** play_token Mech via cost {energy:1, power:1([fury]), tap} is captured. BUT the cost "Recycle a unit from your trash" IS supported — `recycle` is a KNOWN_ACTIVATED_COST key and `_parse_activated_cost`/pay (loop.py:1200,1271) recycles from trash. Parser omitted it, so the ability is cheaper than printed. Missing an executable cost clause -> MINOR (downgrade from v1 OK). Token might 3 not parameterizable (token-def limit).

---

### Cursed Sarcophagus

**Raw:** When you play this, banish all units from your trash. [tap]: Play a unit banished with this. (You must pay its costs.)

**New effects:**
```json
[
  {
    "effect": "banish_card",
    "trigger": "on_play",
    "target": "self",
    "scope": "all"
  }
]
```
**New keywords:** []
**Flagged this run:** banish all units from own trash, then play a unit banished with this via tap ability
**v1 Verdict:** MISSING_EFFECT

**v2 Verdict:** MISSING_EFFECT
**Notes:** Two problems. (a) "banish ALL units from trash": parse uses scope:all but `_banish_card` (effects.py:611-622) reads `count` (default 1) and ignores scope + has no unit filter -> banishes 1 arbitrary card (new KNOWN_ISSUES #13). (b) the entire activated "[tap]: Play a unit banished with this" ability is dropped. Whole ability missing -> not acceptable.

---

### Divining Shells

**Raw:** VISION (When you play this, look at the top card of your Main Deck. You may recycle it.) ACTION[>] Kill this, [tap]: Give a unit +2 [might] this turn.

**New effects:**
```json
[
  {
    "effect": "predict",
    "trigger": "on_play",
    "amount": 1
  },
  {
    "effect": "grant_temporary_might",
    "trigger": "activated",
    "timing": "action",
    "target": "chosen_unit",
    "amount": 2,
    "duration": "this_turn",
    "cost": {
      "tap": true
    }
  }
]
```
**New keywords:** ['PREDICT 1', 'ACTION']
**Flagged this run:** activated ability additional cost 'Kill this' not in cost key list
**v1 Verdict:** WRONG_AMOUNT

**v2 Verdict:** MINOR
**Notes:** Second ability good: grant_temporary_might +2 this_turn (amount/duration correct). First ability weak: VISION ("look at top 1, may recycle") mapped to predict amount 1, but `_predict` (effects.py:555) no-ops for n<=1 and models reorder, not look-1/recycle-to-bottom. Also activated cost misses "Kill this" (`sacrifice` key exists). No clear amount error now (predict 1 = 1 card, grant = +2) so v1 WRONG_AMOUNT -> MINOR. VISION-recycle + kill-cost are the small gaps.

---

### Mushroom Pouch

**Raw:** At the start of your Beginning Phase, if you control a facedown card at a battlefield, draw 1.

**New effects:**
```json
[]
```
**New keywords:** []
**Flagged this run:** Start-of-turn draw gated on controlling a facedown card; no matching condition
**v1 Verdict:** MISSING_CONDITION

**v2 Verdict:** FLAGGED_OK
**Notes:** Empty is correct. Draw is gated on "you control a facedown card at a battlefield" = `controller_has_facedown_card`, which is a SAFE_FALSE condition the parser must NOT emit (engine always evaluates it False, loop.py:664-667). Emitting draw_cards ungated would draw unconditionally (wrong). Refusing is the correct call.

---

### Treasure Trove

**Raw:** When this leaves the board, draw 1 and channel 1 rune exhausted. [Chaos], [Tap]: Kill this.

**New effects:**
```json
[
  {
    "effect": "channel_rune",
    "trigger": "activated",
    "timing": "action",
    "amount": 1,
    "cost": {
      "power": 1,
      "tap": true
    }
  }
]
```
**New keywords:** []
**Flagged this run:** leaves-the-board trigger is broader than on_death; also the activated ability's kill-self and the draw+channel leave effect
**v1 Verdict:** WRONG_TRIGGER

**v2 Verdict:** MISSING_EFFECT
**Notes:** Both abilities mishandled. The leaves-the-board clause "draw 1 and channel 1 rune exhausted" is dropped (draw gone) and its channel got mis-attached to an ACTIVATED ability with cost {power:1([Chaos]), tap} — but the card's real activated ability is "[Chaos],[Tap]: Kill this" (a sacrifice), also dropped. leaves_board != on_death (KNOWN_ISSUES #9 — RULING CONFIRMED: leaving the board covers recall/bounce/banish, not just death). Net: draw + kill-self clauses missing -> not acceptable.

---

### Jax Grandmaster at Arms

**Raw:** [1], [tap]: Attach a detached Equipment you control to a unit you control. [tap]: Attach an attached Equipment you control to a unit you control.

**New effects:**
```json
[]
```
**New keywords:** []
**Flagged this run:** attach/re-attach Equipment activated abilities not supported
**v1 Verdict:** MINOR

**v2 Verdict:** FLAGGED_WRONG
**Notes:** Emitted empty but the FIRST ability was parseable: "[1],[tap]: Attach a detached Equipment you control to a unit you control" maps to `attach_gear` (effects.py:527, pops base_gear -> chosen unit) with cost {energy:1, tap}. attach_gear achieves that core effect, so refusing outright is a miss. (2nd ability — re-attach an already-attached Equipment — IS genuinely unsupported; and note gear-projection gap KNOWN_ISSUES #7.) Because >=1 whole ability was representable -> FLAGGED_WRONG.

---

### Kha'Zix Voidreaver

**Raw:** When you win a combat, gain 1 XP. Spend 1 XP, [tap]: Buff a unit. Spend 2 XP, [tap]: Move and exhausted friendly unit from a battlefield to its base.

**New effects:**
```json
[
  {
    "effect": "gain_xp",
    "trigger": "on_win_combat",
    "amount": 1
  },
  {
    "effect": "buff_unit",
    "trigger": "activated",
    "timing": "action",
    "target": "chosen_unit",
    "cost": {
      "spend_xp": 1,
      "tap": true
    }
  },
  {
    "effect": "move_units_to_base",
    "trigger": "activated",
    "timing": "action",
    "target": "friendly_unit",
    "cost": {
      "spend_xp": 2,
      "tap": true
    }
  }
]
```
**New keywords:** []
**Flagged this run:** third ability moves an exhausted friendly unit from a battlefield to its base
**v1 Verdict:** OK

**v2 Verdict:** MINOR
**Notes:** Abilities 1-2 correct: gain_xp on_win_combat; buff_unit via {spend_xp:1, tap}. Ability 3 "Move an exhausted friendly unit ... to its base" is SINGLE, but parse uses move_units_to_base which moves ALL friendly units at the BF (effects.py:138-146) and ignores the "exhausted" filter — `move_unit` (single) was the better verb (new KNOWN_ISSUES #14). Right family, wrong scope -> MINOR (downgrade from v1 OK).

---

### Volibear Relentless Storm

**Raw:** When you play a MIGHTY unit, you may exhaust me to channel 1 rune exhausted. (A unit is Mighty while it has 5+ [might].)

**New effects:**
```json
[
  {
    "effect": "channel_rune",
    "trigger": "on_friendly_unit_played",
    "amount": 1,
    "condition": {
      "type": "this_is_mighty"
    },
    "cost": {
      "tap": true
    }
  }
]
```
**New keywords:** []
**Flagged this run:** Trigger is when you play a MIGHTY unit (condition on the played unit, not self); exhaust-me is an optional cost on a triggered ability
**v1 Verdict:** MINOR

**v2 Verdict:** WRONG_CONDITION
**Notes:** Trigger on_friendly_unit_played is right, but condition `this_is_mighty` checks the SOURCE card's might (loop.py:634-635 reads `card.might` = Volibear), not the triggering unit. Card gates on "a MIGHTY unit you PLAY". So it fires on every unit played iff Volibear itself is 5+, else never — wrong entity (new KNOWN_ISSUES #15). No condition for "triggering unit is mighty" exists, so parser had no correct option. Also the optional tap cost is ignored (triggered effects don't pay cost, KNOWN_ISSUES #12).

---

### Rabadon's Deathcrown

**Raw:** UNIQUE (Your deck can have only 1 card with this name.) EQUIP [rune] ([rune]: Attach this to a unit you control.)
**Raw (equipped):** Your spells and abilities deal 3 Bonus Damage (while this is attached).

**New effects:**
```json
[]
```
**New keywords:** ['EQUIP 1']
**Flagged this run:** bonus damage to spells and abilities while attached not supported
**v1 Verdict:** MINOR

**v2 Verdict:** FLAGGED_OK
**Notes:** Empty is correct. EQUIP 1 captured. Equipped effect "Your spells and abilities deal 3 Bonus Damage while attached" has no supporting verb (no bonus-damage modifier on spells/abilities). Mechanic unsupported -> refusing is right.

---

### Alpha Strike

**Raw:** ACTION (Play on your turn or in showdowns.) Choose a friendly unit. It deals damage equal to its Might split among enemy units at battlefields. Then for each unit this kills: Gain 1 XP.

**New effects:**
```json
[]
```
**New keywords:** ['ACTION']
**Flagged this run:** friendly unit deals might split among enemy units; gain XP per kill
**v1 Verdict:** WRONG_TARGET

**v2 Verdict:** FLAGGED_OK
**Notes:** Empty is correct. "Friendly unit deals damage = its Might SPLIT among enemy units at battlefields, then gain 1 XP per unit it kills" needs a might-split-across-battlefields damage verb + per-kill XP counter — neither exists. ACTION captured. Refusing is right.

---

### Death from Below

**Raw:** Kill a unit at a battlefield. Then, if it had 3 [might] or less, you may play this from your trash for [rune].

**New effects:**
```json
[
  {
    "effect": "kill_unit",
    "trigger": "on_cast",
    "target": "chosen_unit"
  }
]
```
**New keywords:** []
**Flagged this run:** conditional replay from trash for killed unit with 3 might or less
**v1 Verdict:** MISSING_EFFECT

**v2 Verdict:** MISSING_EFFECT
**Notes:** Main clause kill_unit is present but the whole conditional "if it had 3 [might] or less, you may play this from your trash for [rune]" is dropped. Target `chosen_unit` is CORRECT here (unrestricted "a unit" = either side, player choice); the parser is fine. Separately, the engine currently mis-files chosen_unit under friendly aliases so it hits only your side — a systemic engine bug across 82 effects (KNOWN_ISSUES #16), not a parse fault. Verdict driven by the missing clause: whole conditional "play from trash for [rune]" dropped -> not acceptable.

---

### Thrill of the Hunt

**Raw:** REACTION (Play any time, even before spells and abilities resolve.) Banish a friendly unit, then its owner plays it to any battlefield, ignoring its cost.

**New effects:**
```json
[]
```
**New keywords:** ['REACTION']
**Flagged this run:** banish a friendly unit then replay it to any battlefield ignoring cost
**v1 Verdict:** MISSING_EFFECT

**v2 Verdict:** FLAGGED_OK
**Notes:** Empty is correct. "Banish a friendly unit IN PLAY, then its owner replays it to any battlefield ignoring cost" is a board-flicker; `banish_card` operates on zones (trash/hand/deck), not units in play, and there's no replay-to-chosen-battlefield path. REACTION captured. Mechanic unsupported -> refusing is right.

---

### Daisy!

**Raw:** I enter ready. Reduce my cost by [1] for each of the following tags among your units — Bird, Cat, Dog, and Poro. When I attack while your units have all 4 tags, STUN an enemy unit here. (It doesn't deal combat damage this turn.)

**New effects:**
```json
[
  {
    "effect": "stun_unit",
    "trigger": "on_attack",
    "target": "enemy_unit",
    "condition": {
      "type": "you_control_subtype"
    }
  }
]
```
**New keywords:** []
**Flagged this run:** enters ready; cost reduction per distinct tag among units; attack stun gated on controlling all 4 tags
**v1 Verdict:** MISSING_EFFECT

**v2 Verdict:** MISSING_EFFECT
**Notes:** Two whole abilities dropped: "I enter ready" and "reduce my cost by [1] for each of Bird/Cat/Dog/Poro tags among your units" (amount_source n_distinct_tags exists but the cost-reduction wiring isn't emitted). The attack-stun is gated on `you_control_subtype` with NO tag param and no way to require ALL 4 tags — wrong/empty condition (tag="" never matches, loop.py:652-658). Whole clauses missing -> not acceptable.

---

### Shadow

**Raw:** If you play me to a battlefield, I enter ready. ACTION[>] [1] [rune], [tap]: STUN an enemy unit attacking here. (It doesn't deal combat damage this turn.)

**New effects:**
```json
[
  {
    "effect": "stun_unit",
    "trigger": "activated",
    "timing": "action",
    "target": "enemy_unit",
    "cost": {
      "energy": 1,
      "power": 1,
      "tap": true
    }
  }
]
```
**New keywords:** ['ACTION']
**Flagged this run:** enters ready if played to a battlefield; stun target restricted to enemy attacking here
**v1 Verdict:** MINOR

**v2 Verdict:** MINOR
**Notes:** Primary ability captured: stun_unit via activated cost {energy:1, power:1([rune]), tap}. Missed: the "If you play me to a battlefield, I enter ready" entry clause, and the target restriction "an enemy unit ATTACKING here" (stun resolves first enemy at the BF, no attacking filter). Small clause/scope misses -> MINOR.

---

### Blood Money

**Raw:** ACTION (Play on your turn or in showdowns.) Kill a unit at a battlefield with 2 [might] or less. If it was an enemy unit, play a Gold gear token exhausted. If it was a friendly unit, play two Gold gear tokens exhausted.

**New effects:**
```json
[
  {
    "effect": "kill_unit",
    "trigger": "on_cast",
    "timing": "action",
    "target": "chosen_unit",
    "target_filter": {
      "might_at_most": 2
    }
  }
]
```
**New keywords:** ['ACTION']
**Flagged this run:** enemy-vs-friendly branch spawning Gold tokens not supported
**v1 Verdict:** MISSING_EFFECT

**v2 Verdict:** MISSING_EFFECT
**Notes:** kill_unit with might_at_most:2 filter is correct, but the entire branch "if it was an ENEMY unit play a Gold gear token; if FRIENDLY play TWO" is dropped (no token spawn at all). Target `chosen_unit` is CORRECT (either side, player choice); parser fine. The engine mis-files chosen_unit as friendly-only (systemic, KNOWN_ISSUES #16) — an engine bug, not a parse fault. Verdict driven by the missing branch: enemy/friendly Gold-token spawn dropped -> not acceptable.

---

### Fading Memories

**Raw:** Give a unit at a battlefield or a gear TEMPORARY. (Kill it at the start of its controller's Beginning Phase, before scoring.)

**New effects:**
```json
[
  {
    "effect": "give_keyword",
    "trigger": "on_cast",
    "timing": "action",
    "target": "chosen_unit",
    "keyword": "TEMPORARY"
  }
]
```
**New keywords:** []
**Flagged this run:** Target can be a unit OR a gear; gear target not representable
**v1 Verdict:** MINOR

**v2 Verdict:** MINOR
**Notes:** give_keyword TEMPORARY on a chosen unit is correct. Missed alternative: target may be "a unit at a battlefield OR a GEAR" — the gear target isn't representable (_resolve_targets only yields units). One arm of an OR-target missing -> MINOR.

---

### Lotus Trap

**Raw:** HIDDEN (Hide now for [rune] to react with later for [0].) REACTION (Play any time, even before spells and abilities resolve.) Choose a unit. Double all damage that would be dealt to it this turn.

**New effects:**
```json
[]
```
**New keywords:** ['HIDDEN', 'REACTION']
**Flagged this run:** double all damage dealt to chosen unit is a damage-taken modifier, not double_might
**v1 Verdict:** WRONG_EFFECT

**v2 Verdict:** FLAGGED_OK
**Notes:** Empty is correct — and the parser explicitly refused rather than misusing double_might. "Double all damage that would be dealt to a chosen unit this turn" is a damage-TAKEN modifier; double_might doubles MIGHT (effects.py:110-113), a different thing. HIDDEN + REACTION captured. No damage-taken modifier verb exists -> refusing is right.

---

### Adaptatron

**Raw:** When I conquer, you may kill a gear. If you do, buff me. (If I don't have a buff, I get a +1 [might] buff.)

**New effects:**
```json
[
  {
    "effect": "kill_gear",
    "trigger": "on_conquer",
    "target": "chosen_unit",
    "target_filter": {
      "is_gear": true
    }
  },
  {
    "effect": "buff_unit",
    "trigger": "on_conquer",
    "target": "self"
  }
]
```
**New keywords:** []
**Flagged this run:** The buff is gated on the optional kill actually happening (if you do)
**v1 Verdict:** MINOR

**v2 Verdict:** MINOR
**Notes:** Right shape (kill_gear + buff on on_conquer) but two issues. (a) the buff is gated on the OPTIONAL kill actually happening ("if you do") — parse has two independent on_conquer effects, so buff always fires; no "if-you-did" gate exists. (b) engine `kill_gear` (effects.py:389-405) ignores target/target_filter and destroys ALL gear on BOTH sides (new KNOWN_ISSUES #17). Verb choice reasonable; gating gap -> MINOR.

---

### Carnivorous Snapvine

**Raw:** When you play me, choose a unit at a battlefield. We deal damage equal to our Mights to each other.

**New effects:**
```json
[]
```
**New keywords:** []
**Flagged this run:** Mutual damage equal to each other's Might between me and a chosen unit; no supported verb for reciprocal Might damage
**v1 Verdict:** MINOR

**v2 Verdict:** FLAGGED_OK
**Notes:** Empty is correct. "We deal damage equal to our Mights to each other" (reciprocal Might-damage between me and a chosen unit) has no supporting verb — deal_damage takes a fixed/sourced amount, not simultaneous mutual self-Might exchange. Refusing is right.

---

### Dune Drake

**Raw:** When I attack, give me +2 [might] this turn if there is a ready enemy unit here.

**New effects:**
```json
[]
```
**New keywords:** []
**Flagged this run:** Buff gated on a ready enemy unit being here; no matching condition
**v1 Verdict:** WRONG_CONDITION

**v2 Verdict:** FLAGGED_OK
**Notes:** Empty is defensible. grant_temporary_might exists but the buff is gated on "there is a READY enemy unit here" — no such condition (KNOWN_CONDITIONS has no ready-enemy check). Emitting the +2 ungated would fire wrongly; refusing avoids a false-positive.

---

### Pickpocket

**Raw:** When you play me, you may kill a gear with Energy cost no more than [1]. If you do, play a Gold gear token exhausted.

**New effects:**
```json
[
  {
    "effect": "kill_gear",
    "trigger": "on_play",
    "target": "chosen_unit",
    "target_filter": {
      "is_gear": true
    }
  },
  {
    "effect": "play_token",
    "trigger": "on_play",
    "token_name": "Gold"
  }
]
```
**New keywords:** []
**Flagged this run:** Kill limited to gear with energy cost <=1; play-token gated on the optional kill happening
**v1 Verdict:** MINOR

**v2 Verdict:** MINOR
**Notes:** kill_gear + play_token(Gold) on on_play is the right shape. Gaps: (a) "gear with Energy cost <= 1" is not expressible — no energy-cost filter key (might_at_most is MIGHT). (b) the Gold token is gated on the optional kill ("if you do"), not modeled. (c) engine kill_gear kills ALL gear (KNOWN_ISSUES #17). Right verbs, scope/gating missed -> MINOR.

---

### Soul Shepherd

**Raw:** Your token units have +1 [might].

**New effects:**
```json
[
  {
    "effect": "grant_might",
    "trigger": "passive",
    "amount": 1,
    "target_filter": {
      "is_token": true,
      "is_unit": true
    }
  }
]
```
**New keywords:** []
**Flagged this run:** static buff to your token units anywhere; aura scope
**v1 Verdict:** MINOR

**v2 Verdict:** MINOR
**Notes:** grant_might passive + filter {is_token,is_unit} is the natural encoding of "your token units +1 might". Engine gap: the passive path `_apply_passive_grant` (loop.py:543-572) IGNORES target_filter and applies to ALL friendlies at the source's battlefield (not just tokens, and not board-wide) — new KNOWN_ISSUES #18. Parse acceptable; engine filter gap logged -> MINOR.

---

### Ultrasoft Poro

**Raw:** [tap]: Play two 1 [might] Bird unit tokens with DEFLECT. Use this ability only while I'm at a battlefield. (Opponents must pay [rune] to choose a DEFLECT unit with a spell or ability.)

**New effects:**
```json
[
  {
    "effect": "play_token",
    "trigger": "activated",
    "timing": "action",
    "cost": {
      "tap": true
    },
    "token_name": "Bird",
    "count": 2
  }
]
```
**New keywords:** []
**Flagged this run:** Bird token with DEFLECT is non-canonical; ability restricted to while at a battlefield
**v1 Verdict:** MINOR

**v2 Verdict:** MINOR
**Notes:** play_token count 2 (Bird) via {tap} captured. Missed: DEFLECT on the tokens and the 1-[might] stat (play_token only carries token_name/count/ready — no per-token keyword or might), plus the "use only while I'm at a battlefield" restriction. Small token-def/scope misses -> MINOR.

---
