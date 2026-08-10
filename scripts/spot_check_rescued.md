# Spot-check — revisione semantica manuale

Campione di 30 carte (RNG seed fisso) dalle carte con `effects[]`. Compila **Verdict** per ciascuna con uno dei codici qui sotto, poi esegui `scripts/spot_check_summary.py`.

**Tassonomia verdict:**

- `OK` — interpretazione corretta
- `MINOR` — verb principale giusto ma manca una clausola secondaria
- `WRONG_TRIGGER` — verb giusto, trigger sbagliato
- `WRONG_TARGET` — target sbagliato
- `WRONG_AMOUNT` — quantità sbagliata / mancato amount_source
- `WRONG_FILTER` — filtro mancante o sbagliato
- `MISSING_EFFECT` — clausole intere ignorate
- `PHANTOM_EFFECT` — effetto inventato non presente nel testo
- `MISSING_CONDITION` — condition non riconosciuta
- `UNCERTAIN` — il testo è genuinamente ambiguo

Soglia di accettazione: OK+MINOR ≥ 80% → PROSEGUI; altrimenti RIPARSARE.

---

### Frozen Fortress (Unleashed, Battlefield)

**Raw effect:** At the start of each player's Beginning Phase, deal 1 to each unit here. (This happens before scoring.)

**Parsed effects:**

```json
[
  {
    "effect": "deal_damage",
    "trigger": "on_start_of_turn",
    "amount": 1,
    "target": "all_units_here"
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Ornn's Forge (Spiritforged, Battlefield)

**Raw effect:** When you control this battlefield, the first friendly non-token gear played each turn costs [1] less.

**Parsed effects:**

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

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Power Nexus (Spiritforged, Battlefield)

**Raw effect:** When you hold here, you may pay [rune] [rune] [rune] [rune] to score 1 point.

**Parsed effects:**

```json
[
  {
    "effect": "score_point",
    "trigger": "on_hold",
    "amount": 1,
    "condition": {
      "type": "kicker_paid"
    },
    "additional_cost": {
      "power": 4
    }
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Fizz Trickster (Spiritforged, Champion)

**Raw effect:** When you play me, you may play a spell from your trash with Energy cost no more than [3], ignoring its Energy cost. Recycle that spell after you play it. (You must still pay its Power cost.)

**Parsed effects:**

```json
[
  {
    "effect": "play_from_trash",
    "trigger": "on_play",
    "target": "chosen_spell",
    "target_filter": {
      "is_spell": true
    },
    "max_energy": 3
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Kha'Zix Mutating Horror (Unleashed, Champion)

**Raw effect:** AMBUSH (You may play me as a REACTION to a battlefield where you have units.) When I attack or defend, if an enemy unit is alone here, give me +2 [might] this turn and gain 2 XP.

**Parsed effects:**

```json
[
  {
    "effect": "grant_temporary_might",
    "trigger": "on_attack",
    "amount": 2,
    "target": "self",
    "duration": "this_turn",
    "condition": {
      "type": "this_is_alone",
      "params": {}
    }
  },
  {
    "effect": "gain_xp",
    "trigger": "on_attack",
    "amount": 2,
    "target": "self",
    "condition": {
      "type": "this_is_alone",
      "params": {}
    }
  }
]
```

**Parsed keywords:** ['AMBUSH']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Nami Headstrong (Unleashed, Champion)

**Raw effect:** You may pay [calm] as an additional cost to play me. When you play me, if you paid the additional cost, STUN an enemy unit. (It doesn't deal combat damage this turn.) When I hold, the next time you play a unit this turn, ready it and BUFF it.

**Parsed effects:**

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

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Soraka Wanderer (Spiritforged, Champion)

**Raw effect:** I must be assigned combat damage last. If another unit you control here would die, if it has less Might than me, instead heal it, exhaust it, and recall it. (Send it to base. This isn't a move.)

**Parsed effects:**

```json
[
  {
    "effect": "replace_death_with_recall",
    "trigger": "death_replacement",
    "target": "friendly_unit",
    "target_filter": {
      "exclude_self": true,
      "might_less_than_self": true
    }
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Assembly Rig (Spiritforged, Gear)

**Raw effect:** [1] [fury], Recycle a unit from your trash, [tap]: Play a 3 [might] Mech unit token to your base.

**Parsed effects:**

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
    },
    "suggested_vocab": [
      "cost:recycle_unit_from_trash"
    ]
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Cursed Sarcophagus (Unleashed, Gear)

**Raw effect:** When you play this, banish all units from your trash. [tap]: Play a unit banished with this. (You must pay its costs.)

**Parsed effects:**

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

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Divining Shells (Unleashed, Gear)

**Raw effect:** VISION (When you play this, look at the top card of your Main Deck. You may recycle it.) ACTION[>] Kill this, [tap]: Give a unit +2 [might] this turn.

**Parsed effects:**

```json
[
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

**Parsed keywords:** ['PREDICT 1', 'ACTION']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Mushroom Pouch (Origins, Gear)

**Raw effect:** At the start of your Beginning Phase, if you control a facedown card at a battlefield, draw 1.

**Parsed effects:**

```json
[
  {
    "effect": "draw_cards",
    "trigger": "on_start_of_turn",
    "count": 1
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Treasure Trove (Origins, Gear)

**Raw effect:** When this leaves the board, draw 1 and channel 1 rune exhausted. [Chaos], [Tap]: Kill this.

**Parsed effects:**

```json
[
  {
    "effect": "draw_cards",
    "trigger": "on_death",
    "count": 1
  },
  {
    "effect": "channel_rune",
    "trigger": "on_death",
    "amount": 1
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Jax Grandmaster at Arms (Spiritforged, Legend)

**Raw effect:** [1], [tap]: Attach a detached Equipment you control to a unit you control. [tap]: Attach an attached Equipment you control to a unit you control.

**Parsed effects:**

```json
[
  {
    "effect": "attach_gear",
    "trigger": "activated",
    "timing": "action",
    "cost": {
      "energy": 1,
      "tap": true
    },
    "target": "friendly_unit",
    "target_filter": {
      "subtype": "Equipment"
    }
  },
  {
    "effect": "attach_gear",
    "trigger": "activated",
    "timing": "action",
    "cost": {
      "tap": true
    },
    "target": "friendly_unit",
    "target_filter": {
      "subtype": "Equipment"
    }
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Kha'Zix Voidreaver (Unleashed, Legend)

**Raw effect:** When you win a combat, gain 1 XP. Spend 1 XP, [tap]: Buff a unit. Spend 2 XP, [tap]: Move and exhausted friendly unit from a battlefield to its base.

**Parsed effects:**

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

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Volibear Relentless Storm (Origins, Legend)

**Raw effect:** When you play a MIGHTY unit, you may exhaust me to channel 1 rune exhausted. (A unit is Mighty while it has 5+ [might].)

**Parsed effects:**

```json
[
  {
    "effect": "channel_rune",
    "trigger": "on_friendly_unit_played",
    "target_filter": {
      "is_mighty": true
    },
    "amount": 1,
    "cost": {
      "tap": true
    }
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Rabadon's Deathcrown (Spiritforged, Signature Gear)

**Raw effect:** UNIQUE (Your deck can have only 1 card with this name.) EQUIP [rune] ([rune]: Attach this to a unit you control.)

**Raw effect (equipped):** Your spells and abilities deal 3 Bonus Damage (while this is attached).

**Parsed effects:**

```json
[
  {
    "effect": "deal_damage",
    "trigger": "passive",
    "amount": 3,
    "note": "bonus damage to your spells and abilities while attached"
  }
]
```

**Parsed keywords:** ['EQUIP 1']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Alpha Strike (Unleashed, Signature Spell)

**Raw effect:** ACTION (Play on your turn or in showdowns.) Choose a friendly unit. It deals damage equal to its Might split among enemy units at battlefields. Then for each unit this kills: Gain 1 XP.

**Parsed effects:**

```json
[
  {
    "effect": "deal_damage",
    "trigger": "on_cast",
    "timing": "action",
    "target": "all_enemy_units_here",
    "amount_source": "self_might"
  }
]
```

**Parsed keywords:** ['ACTION']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Death from Below (Unleashed, Signature Spell)

**Raw effect:** Kill a unit at a battlefield. Then, if it had 3 [might] or less, you may play this from your trash for [rune].

**Parsed effects:**

```json
[
  {
    "effect": "kill_unit",
    "trigger": "on_cast",
    "target": "chosen_unit"
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Thrill of the Hunt (Unleashed, Signature Spell)

**Raw effect:** REACTION (Play any time, even before spells and abilities resolve.) Banish a friendly unit, then its owner plays it to any battlefield, ignoring its cost.

**Parsed effects:**

```json
[
  {
    "effect": "banish_card",
    "trigger": "on_cast",
    "timing": "reaction",
    "target": "friendly_unit"
  }
]
```

**Parsed keywords:** ['REACTION']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Daisy! (Unleashed, Signature Unit)

**Raw effect:** I enter ready. Reduce my cost by [1] for each of the following tags among your units — Bird, Cat, Dog, and Poro. When I attack while your units have all 4 tags, STUN an enemy unit here. (It doesn't deal combat damage this turn.)

**Parsed effects:**

```json
[
  {
    "effect": "stun_unit",
    "trigger": "on_attack",
    "target": "enemy_unit",
    "condition": {
      "type": "you_control_subtype",
      "params": {
        "subtypes": [
          "Bird",
          "Cat",
          "Dog",
          "Poro"
        ]
      }
    }
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Shadow (Unleashed, Signature Unit)

**Raw effect:** If you play me to a battlefield, I enter ready. ACTION[>] [1] [rune], [tap]: STUN an enemy unit attacking here. (It doesn't deal combat damage this turn.)

**Parsed effects:**

```json
[
  {
    "effect": "stun_unit",
    "trigger": "activated",
    "timing": "action",
    "target": "enemy_unit",
    "cost": {
      "energy": 1,
      "tap": true
    }
  }
]
```

**Parsed keywords:** ['ACTION']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Blood Money (Spiritforged, Spell)

**Raw effect:** ACTION (Play on your turn or in showdowns.) Kill a unit at a battlefield with 2 [might] or less. If it was an enemy unit, play a Gold gear token exhausted. If it was a friendly unit, play two Gold gear tokens exhausted.

**Parsed effects:**

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

**Parsed keywords:** ['ACTION']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Fading Memories (Origins, Spell)

**Raw effect:** Give a unit at a battlefield or a gear TEMPORARY. (Kill it at the start of its controller's Beginning Phase, before scoring.)

**Parsed effects:**

```json
[
  {
    "effect": "give_keyword",
    "trigger": "on_cast",
    "keyword": "TEMPORARY",
    "target": "chosen_unit"
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Lotus Trap (Unleashed, Spell)

**Raw effect:** HIDDEN (Hide now for [rune] to react with later for [0].) REACTION (Play any time, even before spells and abilities resolve.) Choose a unit. Double all damage that would be dealt to it this turn.

**Parsed effects:**

```json
[
  {
    "effect": "double_might",
    "trigger": "on_cast",
    "timing": "reaction",
    "target": "chosen_unit"
  }
]
```

**Parsed keywords:** ['HIDDEN', 'REACTION']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Adaptatron (Origins, Unit)

**Raw effect:** When I conquer, you may kill a gear. If you do, buff me. (If I don't have a buff, I get a +1 [might] buff.)

**Parsed effects:**

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

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Carnivorous Snapvine (Origins, Unit)

**Raw effect:** When you play me, choose a unit at a battlefield. We deal damage equal to our Mights to each other.

**Parsed effects:**

```json
[
  {
    "effect": "deal_damage",
    "trigger": "on_play",
    "target": "chosen_unit",
    "amount_source": "self_might"
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Dune Drake (Origins, Unit)

**Raw effect:** When I attack, give me +2 [might] this turn if there is a ready enemy unit here.

**Parsed effects:**

```json
[
  {
    "effect": "grant_temporary_might",
    "trigger": "on_attack",
    "target": "self",
    "amount": 2,
    "duration": "this_turn",
    "condition": {
      "type": "you_have_n_or_more_units_here",
      "params": {}
    }
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Pickpocket (Spiritforged, Unit)

**Raw effect:** When you play me, you may kill a gear with Energy cost no more than [1]. If you do, play a Gold gear token exhausted.

**Parsed effects:**

```json
[
  {
    "effect": "kill_gear",
    "trigger": "on_play",
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

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Soul Shepherd (Unleashed, Unit)

**Raw effect:** Your token units have +1 [might].

**Parsed effects:**

```json
[
  {
    "effect": "grant_might",
    "trigger": "passive",
    "amount": 1,
    "target": "all_friendly_units_here",
    "target_filter": {
      "is_token": true
    }
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Ultrasoft Poro (Unleashed, Unit)

**Raw effect:** [tap]: Play two 1 [might] Bird unit tokens with DEFLECT. Use this ability only while I'm at a battlefield. (Opponents must pay [rune] to choose a DEFLECT unit with a spell or ability.)

**Parsed effects:**

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

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---
