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

### Abandoned Hall (Unleashed, Battlefield)

**Raw effect:** When a player plays a spell, they may give a unit they control here +1 [might] this turn.

**Parsed effects:**

```json
[
  {
    "effect": "grant_temporary_might",
    "trigger": "on_play_spell",
    "target": "friendly_unit",
    "amount": 1,
    "duration": "this_turn"
  }
]
```

**Parsed keywords:** []

**Verdict:** MINOR
**Notes:** Core right: grant_temporary_might +1 this_turn on on_play_spell to a friendly unit. on_play_spell fires for the caster's own units (loop.py:1422), so "a unit they control" = friendly resolves for whoever cast. Dropped: the "here" battlefield-location restriction and the optional "may". Right shape, secondary scope/optionality lost.

---

### Forgotten Library (Unleashed, Battlefield)

**Raw effect:** While you control this battlefield, when you play a spell, if you spent [4] or more, PREDICT. (Look at the top card of your Main Deck. You may recycle it.)

**Parsed effects:**

```json
[
  {
    "effect": "predict",
    "trigger": "passive",
    "condition": {
      "type": "spell_cost_at_least",
      "params": {
        "amount": 4
      }
    },
    "amount": 1
  }
]
```

**Parsed keywords:** []

**Verdict:** WRONG_TRIGGER
**Notes:** predict + spell_cost_at_least type are right, but this is a TRIGGERED ability ("when you play a spell ... PREDICT"), not continuous — trigger should be on_play_spell, not passive. As passive it never hooks spell-play. Also drops the "while you control this battlefield" gate. SECONDARY: param key `amount`; engine's spell_cost_at_least reads params["n"] (loop.py:627), so the [4]+ threshold silently defaults to 0 (see systemic note). WRONG_TRIGGER dominates.

---

### Frozen Fortress (Unleashed, Battlefield)

**Raw effect:** At the start of each player's Beginning Phase, deal 1 to each unit here. (This happens before scoring.)

**Parsed effects:**

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

**Parsed keywords:** []

**Verdict:** MINOR
**Notes:** [Anchor: identical parse graded MINOR in spot_check_rescued.] Verb/trigger/amount right. `all_units_here` resolves FRIENDLY-only (in _FRIENDLY_TARGET_ALIASES, loop.py:87; not in _BOTH_SIDES_TARGETS) while card says "each unit here" = BOTH sides. Under-scoped target. MINOR.

---

### Trapping Grounds (Unleashed, Battlefield)

**Raw effect:** When you conquer here, if you assigned 3 or more excess damage, play a 1 power Bird unit token with DEFLECT.

**Parsed effects:**

```json
[
  {
    "effect": "play_token",
    "trigger": "on_conquer",
    "token_name": "Bird"
  }
]
```

**Parsed keywords:** []

**Verdict:** MISSING_CONDITION
**Notes:** play_token Bird on_conquer is right, but the gate "if you assigned 3+ excess damage" is dropped → token plays on every conquer. (excess_damage_at_least is SAFE_FALSE — unsupportable today — but should still be emitted + flagged.) Also drops DEFLECT on the token, the "1 power" stat, and "here" scope. Same class as Mushroom Pouch (rescued → MISSING_CONDITION).

---

### Aphelios Exalted (Spiritforged, Champion)

**Raw effect:** When you attach an Equipment to me, choose one that hasn't been chosen this turn — • Ready 2 runes. • Channel 1 rune exhausted. • Buff a friendly unit.

**Parsed effects:**

```json
[
  {
    "effect": "buff_unit"
  }
]
```

**Parsed keywords:** []

**Verdict:** MISSING_EFFECT
**Notes:** Modal on-attach ability collapsed to a bare buff_unit. Dropped: the trigger entirely (on-attach-equipment), the modal "choose one not chosen this turn" structure, and 2 of 3 modes (ready_runes 2; channel_rune 1 exhausted). One mode, no trigger, no cost. Disease A, severe.

---

### Kha'Zix Evolving Hunter (Unleashed, Champion)

**Raw effect:** HUNT (When I conquer or hold, gain 1 XP.) When I attack, you may spend 3 XP to deal damage equal to my Might to an enemy unit here.

**Parsed effects:**

```json
[
  {
    "effect": "deal_damage",
    "trigger": "on_attack",
    "amount_source": "self_might",
    "target": "enemy_unit",
    "cost": {
      "spend_xp": 3
    }
  }
]
```

**Parsed keywords:** ['HUNT']

**Verdict:** OK
**Notes:** Clean. HUNT captured as keyword and IS engine-handled (loop.py:356-361 grants XP on conquer/hold). Attack ability: deal_damage on_attack, amount_source self_might, target enemy_unit, cost spend_xp:3 (optional "you may" = optional XP cost). All verbs/sources exist. Nothing dropped.

---

### Renata Glasc Mastermind (Spiritforged, Champion)

**Raw effect:** [1] [mind]: Draw 1. [4] [mind] [mind] [mind] [mind], [tap]: Score 1 point. Use my abilities only while I'm at a battlefield.

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

**Verdict:** MISSING_EFFECT
**Notes:** Two activated abilities; only the first survives, stripped of its cost ([1][mind]) and `activated` trigger — reads as a free static draw. The whole second ability (score_point for [4][mind]x4 + tap) and the "only while at a battlefield" restriction are gone. Half+ the card missing. Disease A.

---

### Viktor Innovator (Origins, Champion)

**Raw effect:** When you play a card on an opponent's turn, play a 1 [might] Recruit unit token in your base.

**Parsed effects:**

```json
[
  {
    "effect": "play_token",
    "trigger": "on_play_spell",
    "timing": null,
    "token_name": "Recruit"
  }
]
```

**Parsed keywords:** []

**Verdict:** WRONG_TRIGGER
**Notes:** play_token Recruit is right. Trigger wrong: card = "when you play a CARD on an OPPONENT'S turn"; parse = on_play_spell, which narrows card→spell AND drops the "on an opponent's turn" gate — so it fires on your own spells on your own turn. No engine trigger captures "card played during opponent's turn," but on_play_spell is the wrong semantics. Also drops "1 might" and "in your base". Disease B (trigger mis-map).

---

### Sterak's Gage (Spiritforged, Gear)

**Raw effect:** QUICK-DRAW (This has Reaction. When you play it, attach it to a unit you control.) Equip [calm] ([calm]: Attach this to a unit you control.)

**Parsed effects:**

```json
[
  {
    "effect": "attach_gear",
    "trigger": "on_play",
    "target": "friendly_unit"
  }
]
```

**Parsed keywords:** ['QUICK-DRAW', 'EQUIP']

**Verdict:** MINOR
**Notes:** QUICK-DRAW auto-attach-on-play captured as attach_gear on_play friendly_unit; QUICK-DRAW + EQUIP keywords present. Secondary path (EQUIP [calm] = pay 1 power to attach later) isn't modeled as a distinct activated cost — just the EQUIP tag, without the [calm] cost. Core attach right, alternate-attach cost thin. MINOR.

---

### Trinity Force (Spiritforged, Gear)

**Raw effect:** EQUIP [body] ([body]: Attach this to a unit you control.)

**Raw effect (equipped):** When I hold, score 1 point.

**Parsed effects:**

```json
[
  {
    "effect": "score_point",
    "trigger": "on_hold",
    "target": "self",
    "amount": 1
  }
]
```

**Parsed keywords:** ['EQUIP']

**Verdict:** OK
**Notes:** Equipped effect exact: score_point on_hold amount 1; target "self" → actor side in score_point (loop.py:131), i.e. you score. EQUIP present. Equipped-gear trigger projection onto the wearer is a separate ENGINE issue (KNOWN_ISSUES #7) — parser is correct.

---

### Vanguard of Helm (Origins, Gear)

**Raw effect:** When a buffed friendly unit dies, buff another friendly unit. (If it doesn't have a buff, it gets a +1 [might] buff.)

**Parsed effects:**

```json
[
  {
    "effect": "buff_unit",
    "trigger": "on_friendly_unit_death",
    "target": "friendly_unit",
    "target_filter": {
      "exclude_self": true
    },
    "condition": {
      "type": "this_is_buffed"
    }
  }
]
```

**Parsed keywords:** []

**Verdict:** WRONG_CONDITION
**Notes:** buff_unit (correct — "+1 might buff" = Buff object), on_friendly_unit_death, exclude_self ("another") reasonable. But the "a BUFFED unit died" gate is mis-bound: on the death path _check_condition receives the SURVIVING candidate as `card`, and this_is_buffed (loop.py:649-651) tests THAT unit's might_counters — it checks whether the buff RECIPIENT is buffed, not the DYING unit. Wrong entity (same class as Kha'Zix this_is_alone → WRONG_CONDITION). Compounded: Vanguard is a Gear, so on_friendly_unit_death never fires on it without gear→wearer projection (ENGINE #7). Borderline MINOR, but the central gate runs wrong → Disease B.

---

### Ezreal Prodigal Explorer (Spiritforged, Legend)

**Raw effect:** [tap]: REACTION — Draw 1. Use only if you've chosen enemy units and/or gear twice this turn with spells or unit abilities.

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

**Verdict:** MISSING_CONDITION
**Notes:** Reduced to a bare draw_cards. Dropped: the tap cost, the `activated` trigger, the REACTION timing, and — critically — the entire usage gate ("only if you've chosen enemy units/gear twice this turn"). As parsed it's a free, ungated, repeatable draw. The defining constraint is the missing condition (no engine analogue — would need flagging). MISSING_CONDITION.

---

### Garen Might of Demacia (Proving Grounds, Legend)

**Raw effect:** When you conquer, if you have 4+ units at that battlefield, draw 2.

**Parsed effects:**

```json
[
  {
    "effect": "draw_cards",
    "trigger": "on_conquer",
    "condition": {
      "type": "you_have_n_or_more_units_here",
      "params": {
        "amount": 4
      }
    },
    "target": "self",
    "amount": 2
  }
]
```

**Parsed keywords:** []

**Verdict:** OK
**Notes:** Parser understood the card fully: draw 2, on_conquer, condition you_have_n_or_more_units_here threshold 4, you draw. Verb/trigger/condition-type/threshold-value/target all correct. CAVEAT (systemic, not a misparse): param key `amount` — engine reads params["n"] (loop.py:625), so at runtime "4+" silently becomes "0+" and the gate always passes. This is the param-key drift below; a loader/schema normalization bug (data is inconsistent: n/amount/count all appear), NOT a semantic parse error → graded OK on parser understanding.

---

### Rengar Pridestalker (Unleashed, Legend)

**Raw effect:** When you play a unit, give a unit +1 [might] this turn.

**Parsed effects:**

```json
[
  {
    "effect": "grant_temporary_might",
    "trigger": "on_friendly_unit_played",
    "target": "friendly_unit",
    "amount": 1,
    "duration": "this_turn"
  }
]
```

**Parsed keywords:** []

**Verdict:** OK
**Notes:** grant_temporary_might +1 this_turn on on_friendly_unit_played (fires when Rengar's controller plays a unit; Rengar excluded via the played-card exclusion, loop.py:864). target friendly_unit is the sensible reading of "a unit". Clean.

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

**Verdict:** OK
**Notes:** "When I attack OR defend" correctly split into on_attack + on_defend, each deal 2 to all_enemy_units_here. Exactly right. EQUIP present. (Equipped-gear projection = ENGINE #7, separate.)

---

### Hextech Gauntlets (Unleashed, Signature Gear)

**Raw effect:** EQUIP [3] [rune]. This ability's Energy cost is reduced by the Might of the unit you choose. (Pay the cost: Attach this to a unit you control.)

**Raw effect (equipped):** When I conquer, if you assigned 3 or more excess damage, draw 1.

**Parsed effects:**

```json
[
  {
    "effect": "draw_cards",
    "trigger": "on_conquer",
    "count": 1
  }
]
```

**Parsed keywords:** ['EQUIP 3']

**Verdict:** MISSING_CONDITION
**Notes:** draw_cards on_conquer count 1 + EQUIP 3 are right, but "if you assigned 3+ excess damage" is dropped → unconditional draw on conquer. Same excess-damage class as Trapping Grounds (SAFE_FALSE, unsupportable today, should be emitted + flagged). EQUIP cost-reduction-by-chosen-Might not modeled, but EQUIP 3 covers the base. MISSING_CONDITION.

---

### Shurelya's Requiem (Spiritforged, Signature Gear)

**Raw effect:** UNIQUE (Your deck can have only 1 card with this name.) EQUIP [rune] ([rune]: Attach this to a unit you control.) When you play this, ready your units.

**Raw effect (equipped):** Your units here have GANKING (We can move from battlefield to battlefield.)

**Parsed effects:**

```json
[
  {
    "effect": "ready_units",
    "trigger": "on_play",
    "target": "all_friendly_units_here"
  },
  {
    "effect": "give_keyword",
    "trigger": "passive",
    "keyword": "GANKING",
    "target": "all_friendly_units_here"
  }
]
```

**Parsed keywords:** ['EQUIP 1']

**Verdict:** OK
**Notes:** Both abilities captured: on_play ready_units, and passive give_keyword GANKING to your units here (equipped effect explicitly says "here", so all_friendly_units_here is exact). EQUIP present. Only tiny ambiguity in "ready your units" scope (here vs all your units), fine for a battlefield gear. Solid.

---

### Decisive Strike (Proving Grounds, Signature Spell)

**Raw effect:** ACTION (Play on your turn or in showdowns.) Give friendly units +2 [might] this turn.

**Parsed effects:**

```json
[
  {
    "effect": "grant_temporary_might",
    "trigger": "on_cast",
    "timing": "action",
    "target": "all_friendly_units_here",
    "scope": "all",
    "amount": 2,
    "duration": "this_turn"
  }
]
```

**Parsed keywords:** ['ACTION']

**Verdict:** OK
**Notes:** grant_temporary_might +2 this_turn to all_friendly_units_here, scope all, ACTION — matches "give friendly units +2 might this turn." An ACTION combat pump is naturally here-scoped. OK.

---

### Void Assault (Unleashed, Signature Spell)

**Raw effect:** Move a friendly unit, then move an enemy unit. (If they both move to a battlefield you don't control, you're the attacker.)

**Parsed effects:**

```json
[
  {
    "effect": "move_unit",
    "trigger": "on_cast",
    "target": "friendly_unit",
    "scope": "single"
  },
  {
    "effect": "move_unit",
    "trigger": "on_cast",
    "target": "enemy_unit",
    "scope": "single"
  }
]
```

**Parsed keywords:** []

**Verdict:** MINOR
**Notes:** Structurally faithful: move a friendly then an enemy (two move_unit, correct targets/order). But the point of the card — moving units TO a chosen battlefield to become attacker — isn't expressible: move_unit (effects.py:433) is minimal, only sends a FRIENDLY unit to its own base and ignores target/destination, so the enemy move + destination/attacker semantics are lost at engine level. Vocab gap (move_unit has no destination). Intent captured, destination not. MINOR.

---

### Zenith Blade (Origins, Signature Spell)

**Raw effect:** ACTION (Play on your turn or in showdowns.) Stun an enemy at a battlefield. You may move a friendly unit to that enemy unit's battlefield. (A stunned unit doesn't deal combat damage this turn.)

**Parsed effects:**

```json
[
  {
    "effect": "stun_unit",
    "trigger": "on_cast",
    "target": "enemy_unit"
  },
  {
    "effect": "move_unit",
    "trigger": "on_cast",
    "target": "friendly_unit"
  }
]
```

**Parsed keywords:** ['ACTION']

**Verdict:** MINOR
**Notes:** Both clauses present: stun_unit enemy_unit + move_unit friendly_unit, ACTION. Lost: the optional "may" on the move and the destination ("to that enemy's battlefield" — move_unit only goes to base). Same move_unit destination limitation as Void Assault. Core captured, secondary lost. MINOR.

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
      "params": {}
    }
  }
]
```

**Parsed keywords:** []

**Verdict:** MISSING_EFFECT
**Notes:** [Anchor: same card graded MISSING_EFFECT in spot_check_rescued.] Conditional STUN captured, but drops "I enter ready" and the per-tag cost reduction. Worse than the rescued version: you_control_subtype params are EMPTY {} — engine reads params["tag"] (loop.py:653), so the 4-tag gate degrades to no-tag. Two static/on-enter effects gone → MISSING_EFFECT.

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
**Notes:** [Anchor: identical parse graded MINOR in spot_check_rescued.] stun_unit activated, energy:1 + tap, ACTION correct. Drops "I enter ready" (on-play) and the "attacking here" restriction on the target (just enemy_unit). MINOR.

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

**Verdict:** MINOR
**Notes:** deal_damage 3 on_play; target "battlefield" = both-sides token (effects.py:296). Gaps: "at battlefieldS" = ALL battlefields, but the effect resolves on one battlefield only (here vs everywhere → MINOR, Soul Shepherd precedent). The stray `filter` key is non-canonical (inert). Note: loop.deal_damage (loop.py:108) doesn't honor _BOTH_SIDES_TARGETS anyway (logged deal_damage ENGINE issue), so both-sides won't apply at runtime — engine-side. MINOR.

---

### Crescent Strike (Unleashed, Spell)

**Raw effect:** ACTION (Play on your turn or in showdowns.) Choose a battlefield and an enemy unit there. Deal 4 to that unit and 1 to each other enemy unit there.

**Parsed effects:**

```json
[
  {
    "effect": "deal_damage",
    "trigger": "on_cast",
    "timing": "action",
    "target": "enemy_unit",
    "amount": 4
  },
  {
    "effect": "deal_damage",
    "trigger": "on_cast",
    "timing": "action",
    "target": "all_enemy_units_here",
    "amount": 1
  }
]
```

**Parsed keywords:** ['ACTION']

**Verdict:** MINOR
**Notes:** The 4-to-chosen + 1-to-others AoE split is captured well (4 to enemy_unit; 1 to all_enemy_units_here), ACTION correct. Only miss: "each OTHER enemy unit" — all_enemy_units_here also hits the chosen unit, so it takes 4+1=5 instead of 4 (no exclude-chosen filter). MINOR.

---

### Feral Strength (Spiritforged, Spell)

**Raw effect:** REACTION (Play any time, even before spells and abilities resolve.) REPEAT [2] (You may pay the additional cost to repeat this spell's effect.) Give a unit +2 [might] this turn.

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

**Verdict:** MINOR
**Notes:** Core effect correct (grant_temporary_might +2, this-turn implicit in the verb), would function on a default friendly target. Dropped: the REACTION keyword (parsed keywords empty — timing lost) and the REPEAT [2] optional-repeat mechanic. Also thin on explicit target/trigger. Two secondary mechanics missing → MINOR (borderline; empty keyword list + REPEAT loss worth flagging).

---

### Get Excited! (Origins, Spell)

**Raw effect:** ACTION (Play on your turn or in showdowns.) Discard 1. Deal its Energy cost as damage to a unit at a battlefield. (Ignore its Power cost.)

**Parsed effects:**

```json
[
  {
    "effect": "discard_card",
    "trigger": "on_cast",
    "timing": "action",
    "count": 1
  },
  {
    "effect": "deal_damage",
    "trigger": "on_cast",
    "timing": "action",
    "target": "chosen_unit"
  }
]
```

**Parsed keywords:** ['ACTION']

**Verdict:** WRONG_AMOUNT
**Notes:** Two-step structure right (discard 1 → deal damage to chosen_unit), ACTION correct, chosen_unit is the right unrestricted target. But the damage MAGNITUDE — "its Energy cost" (the discarded card's energy) — is entirely missing: no amount, no amount_source, and there's no amount_source for "discarded-card energy" in KNOWN_AMOUNT_SOURCES. deal_damage fires with no/zero magnitude. Classic mancato amount_source → WRONG_AMOUNT.

---

### Mobilize (Origins, Spell)

**Raw effect:** Channel 1 rune exhausted, if you couldn't, draw 1.

**Parsed effects:**

```json
[
  {
    "effect": "channel_rune",
    "trigger": "on_cast",
    "amount": 1,
    "exhausted": true
  }
]
```

**Parsed keywords:** []

**Verdict:** MINOR
**Notes:** channel_rune 1 with exhausted:true captured correctly (many parses drop the exhausted flag; this one keeps it — good). Missing only the fallback secondary clause: "if you couldn't, draw 1." One conditional secondary effect dropped → MINOR.

---

### Angler Beast (Unleashed, Unit)

**Raw effect:** When you play me, return all units with 2 [might] or less to their owners' hands.

**Parsed effects:**

```json
[
  {
    "effect": "recall_unit",
    "trigger": "on_play",
    "target": "battlefield",
    "scope": "all",
    "target_filter": {
      "might_at_most": 2,
      "is_unit": true
    }
  }
]
```

**Parsed keywords:** []

**Verdict:** MINOR
**Notes:** Strong parse: recall_unit on_play, target "battlefield" = both sides (recall_unit uses _resolve_targets, effects.py:303/420), scope all, might_at_most:2. recall_unit routes non-tokens to owner's hand and dissolves tokens (effects.py:414-430). Only gap: "all units" = across ALL battlefields, but _resolve_targets sees only the current one (here vs everywhere → MINOR, Soul Shepherd precedent). is_unit redundant but harmless. MINOR.

---

### Bubble Bot (Spiritforged, Unit)

**Raw effect:** When you play me, ready another friendly Mech.

**Parsed effects:**

```json
[
  {
    "effect": "ready_units"
  }
]
```

**Parsed keywords:** []

**Verdict:** WRONG_FILTER
**Notes:** Bare ready_units — the defining restriction "another friendly MECH" is gone: no subtype:Mech filter, no exclude_self ("another"), and even the on_play trigger and target are absent. As parsed it readies friendly units with no Mech gate (a materially different effect). Dominant loss is the missing/wrong filter; trigger + "another" also dropped. WRONG_FILTER.

---

### Trifarian Gloryseeker (Origins, Unit)

**Raw effect:** LEGION — When you play me, buff me. (If I don't have a buff, I get a +1 [might] buff. Get the effect if you've played another card this turn.)

**Parsed effects:**

```json
[
  {
    "effect": "buff_unit",
    "trigger": "on_play",
    "target": "self",
    "amount": 1
  }
]
```

**Parsed keywords:** ['LEGION']

**Verdict:** MISSING_CONDITION
**Notes:** buff_unit on_play self is the right verb (buff = Buff object, "+1 might buff"), LEGION keyword present — but the LEGION gate is dropped. The engine's LEGION handling only does COST reduction (legion_effects.py / loop.py:815); it does NOT auto-gate effects, so "get the effect if you've played another card this turn" must be an explicit you_already_played_another_card_this_turn condition. Every other LEGION card in the registry emits it (Dangerous Duo, Scrapyard Champion, Vanguard Captain, Darius Executioner…); Trifarian alone has condition:None, so its buff fires unconditionally on play. Disease B (dropped LEGION condition). MISSING_CONDITION.

---
