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

**Verdict:** MINOR
**Notes:** Verb/trigger/amount right (deal_damage, on_start_of_turn=Beginning Phase, 1). BUT target all_units_here resolves FRIENDLY-ONLY (not in _BOTH_SIDES_TARGETS) while card says 'each unit here' = BOTH sides. Same both-sides-here target gap as Trifarian/Windswept (KNOWN_ISSUES #6-adjacent). Also 'each PLAYER's Beginning Phase' = fires on both turns; on_start_of_turn firing needs to be player-agnostic here. MINOR: right shape, target under-scoped to friendly.

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

**Verdict:** MISSING_EFFECT
**Notes:** Verb reduce_cost DOES NOT EXIST in engine (confirmed: only missing verb in the sample). trigger cost_modifier exists but there's no handler to apply it. Also drops 'first ... each turn' limiter and 'while you control this battlefield' gate. Effectively unsupported -> should be flagged, not emitted as a populated parse referencing a nonexistent verb. NEEDS: reduce_cost verb (aura:reduce_cost is in Step 3 queue x6).

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

**Verdict:** OK
**Notes:** score_point + on_hold + optional additional_cost power:4 + kicker_paid condition all correct. [rune]x4 = 4 power (rune=power symbol). 'you may pay to score' = optional cost gate, modeled right. Verify score_point exists (it does). Clean.

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

**Verdict:** MINOR
**Notes:** play_from_trash + on_play + is_spell filter + max_energy:3 correct and all exist EXCEPT target 'chosen_spell' is MISSING as a target key (engine has chosen_unit; no chosen_spell). Likely resolves via target_filter is_spell so may function, but the target name is non-canonical. Also drops the 'Recycle that spell after' clause (recycle-after-play). MINOR: core right, target key non-standard + one trailing clause dropped.

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

**Verdict:** WRONG_CONDITION
**Notes:** RULING (user): condition must check the ENEMY unit is alone. Engine this_is_alone (loop.py:628) checks len(units on Kha'Zix's OWN side) <= 1 — that's SELF alone, semantically inverted. Wrong condition. PLUS missing on_defend branch ('when I attack OR defend' — only on_attack emitted). Needs an enemy-is-alone condition + the defend copies. Downgraded MINOR -> WRONG_CONDITION.

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

**Verdict:** MISSING_EFFECT
**Notes:** First ability (kicker STUN on_play) is correct: stun_unit, kicker_paid, additional_cost power:1 ([calm]=power). BUT the ENTIRE second ability is dropped: 'When I hold, the next time you play a unit this turn, ready it and BUFF it.' That's a whole on_hold triggered ability missing (ready + buff_unit, delayed 'next unit played'). Half the card gone -> MISSING_EFFECT.

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

**Verdict:** MINOR
**Notes:** RULING (user): Recalls leave damage/exhausted/buff UNAFFECTED unless the card states otherwise. Soraka DOES state otherwise ('heal it, exhaust it'), and engine _try_replace_death does reset_damage()+ready=False — so for THIS card the heal+exhaust is CORRECT. Stays MINOR (only 'must be assigned combat damage last' ordering clause dropped). ENGINE NOTE for Step 3: _try_replace_death ALWAYS heals+exhausts on recall; per the rule a GENERIC recall must leave state untouched unless stated. Soraka is fine; a generic recall verb built on this path would be wrong. Log as recall-semantics issue.

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

**Verdict:** OK
**Notes:** play_token Mech, activated, cost energy:1 power:1 ([fury]=power) tap, and correctly FLAGS the recycle-a-unit cost via suggested_vocab cost:recycle_unit_from_trash. This is exactly the right partial-parse behavior: emit what's supported, flag the unsupported cost. OK (with honest flag).

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

**Verdict:** MISSING_EFFECT
**Notes:** Only the on_play 'banish all units from your trash' is parsed (banish_card self scope:all — reasonable). The entire activated ability '[tap]: Play a unit banished with this' is DROPPED. That's the actual engine of the card. Also banish-from-trash targeting 'self' (the gear) is odd — should target your trash. MISSING_EFFECT: second ability gone.

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

**Verdict:** WRONG_AMOUNT
**Notes:** grant_temporary_might +2 this_turn, activated, chosen_unit — the ACTION ability body is right. BUT: (1) cost is missing 'Kill this' (kill_self cost dropped — only tap kept); (2) keywords say 'PREDICT 1' but card text is VISION — WRONG keyword (VISION vs PREDICT are different); (3) VISION on-play (look at top, may recycle) is entirely dropped. Multiple issues -> at least WRONG_AMOUNT/MISSING; the PREDICT-vs-VISION keyword error is a real parser hallucination. Flag as WRONG.

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

**Verdict:** MISSING_CONDITION
**Notes:** draw_cards + on_start_of_turn + count 1 correct, BUT the condition 'if you control a facedown card at a battlefield' is completely dropped — the draw is unconditional in the parse. That's a free draw every turn vs a conditional one. MISSING_CONDITION.

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

**Verdict:** WRONG_TRIGGER
**Notes:** RULING (user): 'leaves the board' is BROADER than death — a bounce to hand also triggers it. Parse uses on_death, which misses recall/bounce-to-hand. Wrong trigger scope. Also channel 'exhausted' flag dropped and the activated '[Chaos],[tap]: Kill this' ability dropped. Downgraded MINOR -> WRONG_TRIGGER. NEEDS: a 'leaves_board' trigger distinct from on_death.

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

**Verdict:** MINOR
**Notes:** Two activated attach_gear abilities, costs right (energy:1+tap; tap). BUT target_filter subtype:Equipment is on the UNIT target — should describe the GEAR being attached, not the unit. The detached-vs-attached distinction between the two abilities is lost (both look identical). MINOR: attaches modeled, but the detached/attached source distinction dropped.

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

**Verdict:** OK
**Notes:** Three abilities all parsed: gain_xp on_win_combat; buff_unit for spend_xp:1+tap; move_units_to_base for spend_xp:2+tap. All verbs/costs exist and match. Minor typo in card text ('and exhausted' likely 'an exhausted') doesn't affect the parse. Clean OK.

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

**Verdict:** MINOR
**Notes:** channel_rune + on_friendly_unit_played + is_mighty filter + tap cost — good. 'exhausted' flag on channel dropped (channel 1 rune EXHAUSTED). 'you MAY exhaust me' optional cost modeled as cost tap — reasonable. MINOR: exhausted-channel flag missing.

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

**Verdict:** MINOR
**Notes:** EQUIP 1 correct. Equipped effect '+3 Bonus Damage to your spells/abilities' parsed as deal_damage passive amount:3 with a NOTE — but this is a damage-MODIFIER (adds 3 to your other damage sources), not a standalone deal_damage. bonus_damage is a Step 3 queue item and likely has no engine verb yet. Also this is equipped-gear projection (KNOWN_ISSUES #7). MINOR/flag: intent captured in note but no real mechanic.

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

**Verdict:** WRONG_TARGET
**Notes:** Card: choose a friendly unit, IT deals its Might SPLIT AMONG enemy units at battlefieldS (plural, everywhere). Parse: deal_damage self_might to all_enemy_units_here. Wrong on two counts: (1) 'split among' != full might to each (all_enemy_units_here would hit each for full self_might); (2) 'at battlefields' = all battlefields, not just here. Also drops 'for each unit this kills, gain 1 XP'. WRONG_TARGET + MISSING (split semantics + XP clause).

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

**Verdict:** MISSING_EFFECT
**Notes:** kill_unit + on_cast + chosen_unit correct for the first clause, but drops the entire recursion clause: 'if it had 3 might or less, you may play this from your trash for [rune]' (a conditional play-from-trash). Half the card. Also target should be battlefield-restricted ('at a battlefield'). MISSING_EFFECT.

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

**Verdict:** MISSING_EFFECT
**Notes:** Only banish_friendly parsed. The core effect — 'then its owner plays it to any battlefield ignoring its cost' (a banish-then-replay/blink) — is dropped. As parsed this just banishes your own unit (strictly bad). REACTION kept. MISSING_EFFECT: the replay half is the whole point.

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

**Verdict:** MISSING_EFFECT
**Notes:** stun_unit on_attack with you_control_subtype(all 4 tags) condition — the conditional STUN is right. BUT drops: 'I enter ready' and the cost-reduction-per-tag ability ('Reduce my cost by 1 for each tag among Bird/Cat/Dog/Poro'). Two static/on-enter effects gone. cost-reduction is aura/self-cost — likely unsupported, should be flagged. MISSING_EFFECT.

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

**Verdict:** MINOR
**Notes:** stun_unit activated, energy:1+tap correct. Drops 'I enter ready' (on-play ready-self). Target 'enemy unit ATTACKING here' loses the 'attacking' restriction (just enemy_unit). ACTION kept. MINOR: enter-ready dropped + attacking-filter lost.

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

**Verdict:** MISSING_EFFECT
**Notes:** kill_unit + might_at_most:2 + ACTION correct for the kill. BUT the entire payoff is dropped: 'if enemy -> 1 Gold token; if friendly -> 2 Gold tokens' (conditional play_token with a friendly/enemy branch). That's a mode/branch on what was killed. Also target should be battlefield-restricted. MISSING_EFFECT.

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

**Verdict:** MINOR
**Notes:** give_keyword TEMPORARY on_cast chosen_unit — right for the unit case. Card also targets 'a unit at a battlefield OR A GEAR' — the gear-target branch is dropped (can only TEMPORARY a unit, not a gear). Also battlefield-location restriction on the unit. MINOR: gear target option missing.

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

**Verdict:** WRONG_EFFECT
**Notes:** double_might is the WRONG VERB. Engine double_might does unit.temporary_might += unit.might (doubles MIGHT). Card doubles 'all DAMAGE dealt to it this turn' — a damage-taken modifier, totally different (and defensive/harmful, not a buff). No engine verb for 'double incoming damage' exists. HIDDEN+REACTION kept. This is a semantic mis-parse -> flag. (tag as MISSING_EFFECT/PHANTOM: the emitted effect does something the card doesn't say.)

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

**Verdict:** MINOR
**Notes:** on_conquer, kill_gear (optional 'you may'), then buff_unit self — buff_unit is CORRECT here (card literally says '+1 might buff', the Buff object, max 1). Good. Issues: kill_gear target is 'chosen_unit' with is_gear filter (should be chosen_gear/gear target, minor); the 'if you do' linkage (buff only if a gear was killed) isn't encoded as a condition — buff looks unconditional. MINOR.

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

**Verdict:** MINOR
**Notes:** on_play, deal_damage self_might to chosen_unit — captures 'I deal my might to it'. BUT card is MUTUAL: 'We deal damage equal to our Mights to EACH OTHER' — the return damage (chosen unit deals ITS might back to me) is dropped. Also 'at a battlefield' restriction. MINOR-to-WRONG: only half the mutual exchange.

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

**Verdict:** WRONG_CONDITION
**Notes:** grant_temporary_might +2 on_attack this_turn correct. Condition WRONG: card = 'if there is a READY ENEMY unit here', parse = you_have_n_or_more_units_here (that's YOUR units, count-based, no ready/enemy filter). Condition semantics inverted (your units vs ready enemy). WRONG_CONDITION/WRONG_FILTER.

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

**Verdict:** MINOR
**Notes:** kill_gear (optional, max_energy filter should be there) + play_token Gold — both halves present, good structure. Issues: kill_gear drops the 'Energy cost no more than 1' filter (max_energy:1 on the gear); the 'if you do' linkage (token only if a gear was killed) not encoded — token looks unconditional. Gold token 'exhausted' flag dropped. MINOR.

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

**Verdict:** MINOR
**Notes:** grant_might passive +1 is_token filter — verb/filter right (this is the passive anthem, grant_might correct not buff_unit). BUT target all_friendly_units_here is HERE-scoped while 'Your token units' = ALL your tokens ANYWHERE. Should be all_friendly_units_anywhere (Step 3 queue). MINOR: scope too narrow (here vs anywhere).

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

**Verdict:** MINOR
**Notes:** play_token Bird count:2 activated tap — right. Drops: DEFLECT keyword on the tokens (tokens should enter with DEFLECT); 'use only while I'm at a battlefield' location restriction on the ability. DEFLECT is a Step 3 queue keyword. MINOR: token keyword + activation restriction dropped.

---
