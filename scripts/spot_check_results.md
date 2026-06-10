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

### Fortified Position (Origins, Battlefield)

**Raw effect:** When you defend here, choose a unit. It gains SHIELD 2 this combat. (+2 might while It's a defender.)

**Parsed effects:**

```json
[
  {
    "effect": "give_temporary_shield",
    "trigger": "on_defend",
    "target": "chosen_unit",
    "amount": 2,
    "duration": "this_turn"
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Trifarian War Camp (Origins, Battlefield)

**Raw effect:** Units here have +1 [might] . (Including attackers.)

**Parsed effects:**

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

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Windswept Hillock (Origins, Battlefield)

**Raw effect:** Units here have Ganking . (They can move battlefield to battlefield.)

**Parsed effects:**

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

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Janna Savior (Spiritforged, Champion)

**Raw effect:** REACTION (Play any time, even before spells and abilities resolve, including to a battlefield you control.) When you play me, heal your units here, then move up to one enemy unit from here to its base.

**Parsed effects:**

```json
[
  {
    "effect": "heal_unit",
    "trigger": "on_play",
    "timing": "reaction",
    "target": "all_friendly_units_here",
    "scope": "all"
  },
  {
    "effect": "move_unit",
    "trigger": "on_play",
    "timing": "reaction",
    "target": "enemy_unit",
    "scope": "single"
  }
]
```

**Parsed keywords:** ['REACTION']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Kog'Maw Caustic (Origins, Champion)

**Raw effect:** DEATHKNELL - Deal 4 to all units at my battlefield. (When I die, get the effect)

**Parsed effects:**

```json
[
  {
    "effect": "deal_damage",
    "trigger": "on_death",
    "amount": 4,
    "target": "all_units_here",
    "scope": "all"
  }
]
```

**Parsed keywords:** ['DEATHKNELL']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Nilah Joyful Ascetic (Unleashed, Champion)

**Raw effect:** ACCELERATE (You may pay [1] [body] as an additional cost to have me enter ready.) GANKING (I can move from battlefield to battlefield.) When I move, gain 1 XP.

**Parsed effects:**

```json
[
  {
    "effect": "gain_xp",
    "trigger": "on_move",
    "amount": 1
  }
]
```

**Parsed keywords:** ['ACCELERATE', 'GANKING']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Arena Bar (Origins, Gear)

**Raw effect:** [tap]: Buff an exhausted friendly unit. (If it doesn't have a buff, it gets a +1 [might] buff.)

**Parsed effects:**

```json
[
  {
    "effect": "buff_unit",
    "trigger": "activated",
    "target": "friendly_unit",
    "amount": 1
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Boneshiver (Spiritforged, Gear)

**Raw effect:** EQUIP [1] [body] ([1] [body]: Attach this to a unit you control.)

**Raw effect (equipped):** When I conquer, channel 1 rune exhausted.

**Parsed effects:**

```json
[
  {
    "effect": "add_rune",
    "trigger": "on_conquer",
    "amount": 1,
    "exhausted": true
  }
]
```

**Parsed keywords:** ['EQUIP 1']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Heart of Dark Ice (Spiritforged, Gear)

**Raw effect:** [tap]: Give a unit +3 [might] this turn.

**Parsed effects:**

```json
[
  {
    "effect": "grant_temporary_might",
    "amount": 3
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Seal of Rage (Origins, Gear)

**Raw effect:** [tap]: REACTION — ADD [fury] . (Abilities that add resources can't be reacted to.)

**Parsed effects:**

```json
[
  {
    "effect": "gain_energy",
    "trigger": "activated",
    "timing": "reaction",
    "target": "actor",
    "amount": 1,
    "domain": "Fury"
  }
]
```

**Parsed keywords:** ['REACTION']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Darius Hand of Noxus (Origins, Legend)

**Raw effect:** [tap] REACTION, LEGION — ADD [1] (Abilities that add resources can't be reacted to. Get the effect if you've played a card this turn.)

**Parsed effects:**

```json
[
  {
    "effect": "gain_energy",
    "trigger": "activated",
    "timing": "reaction",
    "cost": "exhaust",
    "condition": {
      "type": "you_already_played_another_card_this_turn",
      "params": {}
    },
    "amount": 1
  }
]
```

**Parsed keywords:** ['REACTION', 'LEGION']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Lucian Purifier (Spiritforged, Legend)

**Raw effect:** Your Equipment each give ASSAULT. (+1 [might] while equipped unit is an attacker.)

**Parsed effects:**

```json
[
  {
    "effect": "buff_unit"
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Miss Fortune Bounty Hunter (Origins, Legend)

**Raw effect:** [tap]: Give a unit GANKING this tum. (It can move from battlefield to battlefield.)

**Parsed effects:**

```json
[
  {
    "effect": "give_keyword",
    "trigger": "activated",
    "target": "chosen_unit",
    "duration": "this_turn",
    "keyword": "GANKING",
    "cost": {
      "exhaust_self": true
    }
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Forgefire Cape (Spiritforged, Signature Gear)

**Raw effect:** UNIQUE (Your deck can only have 1 card with this name.) EQUIP [rune] ([rune]: Attach this to a unit you control.)

**Raw effect (equipped):** When I attack or defend, deal 2 to all enemy units here.

**Parsed effects:**

```json
[
  {
    "effect": "deal_damage",
    "trigger": "on_attack",
    "amount": 2,
    "target": "all_enemy_units_here"
  },
  {
    "effect": "deal_damage",
    "trigger": "on_defend",
    "amount": 2,
    "target": "all_enemy_units_here"
  }
]
```

**Parsed keywords:** ['EQUIP']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Arcane Shift (Spiritforged, Signature Spell)

**Raw effect:** ACTION (Play on your turn or in showdowns.) Banish a friendly unit, then its owner plays it, ignoring its cost. Deal 3 to an enemy unit at a battlefield. Banish this.

**Parsed effects:**

```json
[
  {
    "effect": "deal_damage",
    "amount": 3
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Defiant Dance (Spiritforged, Signature Spell)

**Raw effect:** REACTION (Play any time, even before spells and abilities resolve.) Give a unit +2 [might] this turn and another unit -2 [might] this turn.

**Parsed effects:**

```json
[
  {
    "effect": "grant_temporary_might",
    "amount": 2
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Icathian Rain (Origins, Signature Spell)

**Raw effect:** Deal 2 to a unit. Deal 2 to a unit. Deal 2 to a unit. Deal 2 to a unit. Deal 2 to a unit. Deal 2 to a unit.

**Parsed effects:**

```json
[
  {
    "effect": "deal_damage",
    "trigger": "on_cast",
    "target": "chosen_unit",
    "amount": 2
  },
  {
    "effect": "deal_damage",
    "trigger": "on_cast",
    "target": "chosen_unit",
    "amount": 2
  },
  {
    "effect": "deal_damage",
    "trigger": "on_cast",
    "target": "chosen_unit",
    "amount": 2
  },
  {
    "effect": "deal_damage",
    "trigger": "on_cast",
    "target": "chosen_unit",
    "amount": 2
  },
  {
    "effect": "deal_damage",
    "trigger": "on_cast",
    "target": "chosen_unit",
    "amount": 2
  },
  {
    "effect": "deal_damage",
    "trigger": "on_cast",
    "target": "chosen_unit",
    "amount": 2
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Tibbers (Proving Grounds, Signature Unit)

**Raw effect:** When you play me, deal 3 damage to all units at battlefields.

**Parsed effects:**

```json
[
  {
    "effect": "deal_damage",
    "trigger": "on_play",
    "target": "battlefield",
    "scope": "all",
    "amount": 3,
    "filter": "all_units_at_battlefields"
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Against the Odds (Spiritforged, Spell)

**Raw effect:** REACTION (Play any time, even before spells and abilities resolve.) Give a friendly unit at a battlefield +2 [might] this turn for each enemy unit there.

**Parsed effects:**

```json
[
  {
    "effect": "grant_temporary_might_per_enemy",
    "amount": 2
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Back to Back (Origins, Spell)

**Raw effect:** REACTION (Play any time, even before spells and abilities resolve.) Give two friendly units each +2 [might] this turn.

**Parsed effects:**

```json
[
  {
    "effect": "grant_temporary_might",
    "trigger": "on_cast",
    "timing": "reaction",
    "target": "friendly_unit",
    "scope": "single",
    "amount": 2,
    "count": 2,
    "duration": "this_turn"
  }
]
```

**Parsed keywords:** ['REACTION']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Friendship (Unleashed, Spell)

**Raw effect:** REACTION (Play any time, even before spells and abilities resolve.) Choose a unit. Give it +1 [might] this turn for each of the following tags among your units — Bird, Cat, Dog, and Poro.

**Parsed effects:**

```json
[
  {
    "effect": "grant_temporary_might",
    "trigger": "on_cast",
    "timing": "reaction",
    "target": "chosen_unit",
    "amount_source": "n_distinct_tags_among_friendlies",
    "params": {
      "tags": [
        "Bird",
        "Cat",
        "Dog",
        "Poro"
      ]
    }
  }
]
```

**Parsed keywords:** ['REACTION']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Recruit the Vanguard (Proving Grounds, Spell)

**Raw effect:** ACTION (Play on your turn or in showdowns.) Play four 1 might Recruit unit tokens. (They can be played to your base or to battlefields you control.)

**Parsed effects:**

```json
[
  {
    "effect": "play_token",
    "trigger": "on_cast",
    "timing": "action",
    "token_name": "Recruit",
    "might": 1,
    "count": 4
  }
]
```

**Parsed keywords:** ['ACTION']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Vault Breaker (Unleashed, Spell)

**Raw effect:** ACTION (Play on your turn or in showdowns.) Give a unit ASSAULT 2 and GANKING this turn. (+2 [might] while it's an attacker. It can move from battlefield to battlefield.)

**Parsed effects:**

```json
[
  {
    "effect": "give_temporary_assault",
    "trigger": "on_cast",
    "timing": "action",
    "target": "chosen_unit",
    "amount": 2,
    "duration": "this_turn"
  },
  {
    "effect": "give_keyword",
    "trigger": "on_cast",
    "timing": "action",
    "target": "chosen_unit",
    "keyword": "GANKING",
    "duration": "this_turn"
  }
]
```

**Parsed keywords:** ['ACTION']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Wages of Pain (Spiritforged, Spell)

**Raw effect:** HIDDEN (Hide now for [rune] to react with later for [0].) ACTION (Play on your turn or in showdowns.) Deal 3 to a unit at a battlefield. Play a Gold gear token exhausted.

**Parsed effects:**

```json
[
  {
    "effect": "deal_damage",
    "amount": 3
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Corrupt Enforcer (Spiritforged, Unit)

**Raw effect:** When I move to a battlefield, discard 1. When I win a combat, draw 1.

**Parsed effects:**

```json
[
  {
    "effect": "draw_cards",
    "count": 1
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Crowd Favorite (Unleashed, Unit)

**Raw effect:** HUNT (When I conquer or hold, gain 1 XP.) Spend 2 XP: BUFF me. (Give me a +1 Buff if I don't have one.)

**Parsed effects:**

```json
[
  {
    "effect": "buff_unit",
    "trigger": "activated",
    "timing": "action",
    "target": "self",
    "cost": {
      "spend_xp": 2
    }
  }
]
```

**Parsed keywords:** ['HUNT 1']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Inviolus Vox (Unleashed, Unit)

**Raw effect:** When I conquer, give a friendly unit +8 [might] this turn.

**Parsed effects:**

```json
[
  {
    "effect": "grant_temporary_might",
    "trigger": "on_conquer",
    "target": "friendly_unit",
    "amount": 8,
    "duration": "this_turn"
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Loyal Poro (Unleashed, Unit)

**Raw effect:** DEATHKNELL[>] If I didn't die alone, draw 1. (When I die, get the effect. I wasn't alone if there were other friendly units here.)

**Parsed effects:**

```json
[
  {
    "effect": "draw_cards",
    "trigger": "on_death",
    "target": "actor",
    "count": 1,
    "condition": {
      "type": "you_have_n_or_more_units_here",
      "params": {
        "n": 1
      }
    }
  }
]
```

**Parsed keywords:** ['DEATHKNELL']

**Verdict:** ⬜ TODO
**Notes:** 

---

### Sentinel Adept (Spiritforged, Unit)

**Raw effect:** WEAPONMASTER (When you play me, you may EQUIP one of your Equipment to me for [rune] less, even if it's already attached.)

**Parsed effects:**

```json
[
  {
    "effect": "ready_units"
  }
]
```

**Parsed keywords:** []

**Verdict:** ⬜ TODO
**Notes:** 

---

### Windsinger (Spiritforged, Unit)

**Raw effect:** HIDDEN (Hide now for [rune] to react with later for [0].) When you play me, you may return another unit at a battlefield with 3 [might] or less to its owner's hand.

**Parsed effects:**

```json
[
  {
    "effect": "recall_unit",
    "trigger": "on_play",
    "target": "chosen_unit",
    "target_filter": {
      "exclude_self": true,
      "might_at_most": 3
    }
  }
]
```

**Parsed keywords:** ['HIDDEN']

**Verdict:** ⬜ TODO
**Notes:** 

---
