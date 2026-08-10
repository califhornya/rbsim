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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

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

**v2 Verdict:** 
**Notes:** 

---
