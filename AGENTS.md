# Riftbound Simulator | Milestone 6: Core Riftbound Mechanics

### Overview
This milestone begins the transition from a simplified simulation engine into a **mechanically faithful Riftbound rules model**.

All previous systems (Hold/Conquer scoring, two battlefields, AI heuristics, and energy) are complete. We now expand to include **Might-based combat, rune/power resources, movement, and basic keyword support.**

**EDIT**: We should now have completed Phase 1 and 2. 

---

## Phase 1 — Combat & Might System
- Add `might: int` to `UnitCard`.
- Replace simple 1-for-1 removal with **Might-based combat** using the rulebook's structure (section 439).
- Implement damage marking and cleanup:
  - Units take damage up to their Might.
  - Damage clears at end of combat or turn.
- Extend `Battlefield.resolve_combat_simple()` → `resolve_combat_might()`.
- Track combat outcomes for stats (`kills`, `deaths`).

### Stretch
- Add hooks for **Shield**, **Stun**, **Guard** (non-functional placeholders for now).

---

## Phase 2 — Rune & Power System
Replace static energy gain with a **true Rune Pool** resource system.

#### Player-side Changes
- Add `rune_pool` (dict of {domain: count}).
- Replace `energy` and `channel_rate` with `channel()` that:
  - Channels 2 runes per turn (per §315.3.b).
  - Produces Energy + Power tokens.
- Modify `can_pay()` and `pay()` to consider both Energy and Domain Power costs.

#### Card-side Changes
- Extend cost structure: `cost_energy: int`, `cost_power: Optional[Domain]`.
- Update play logic in `GameLoop._apply_action`.

#### Example Rune Model
```python
@dataclass
class Rune:
    domain: Domain
    ready: bool = True

    def activate(self):
        if not self.ready:
            return None
        self.ready = False
        return self.domain
```

---

## Phase 3 — Movement & Showdown
- Introduce **Base** and **Battlefield** locations for units.
- Implement agent action `("MOVE", None, src, dst)`.
- Update `GameLoop._apply_action` to handle:
  - Move Base → Battlefield.
  - Battlefield → Base.
  - (Future) Battlefield ↔ Battlefield (for Ganking).
- Add Showdown phase per §340–345:
  - Triggered when a battlefield becomes contested but uncontrolled.
  - Simple alternating-play system between players.
  - Placeholder for *Action*/*Reaction* keywords.

---

## Phase 4 — Card Model Expansion
Restructure card hierarchy for rule-completeness.

```
Card
├── Unit
├── Spell
├── Gear
├── Rune
├── Legend
└── Battlefield
```

Each card gains:
- `domain: Optional[Domain]`
- `tags: list[str]`
- `keywords: list[str]`
- `might: Optional[int]`
- `category: CardType`

---

## Phase 5 — Minimal Keyword Layer
Implement the following keywords:

| Keyword | Effect |
|----------|---------|
| **Accelerate** | Unit enters ready (no exhaustion) |
| **Guard** | Prioritized when assigning combat damage |
| **Ganking** | Allows battlefield-to-battlefield movement |

> Later expansions: Hidden, Shield, Temporary, Deathknell, etc.

---

## Phase 6 — Testing & Validation
- Add `pytest` suite under `/tests`:
  - Hold and Conquer scoring tests
  - Rune pool and energy channel tests
  - Combat simulation validation (Might vs damage)
- Deterministic results via RNG seed.

---


## Status
🟢 Previous: Functional Hold/Conquer, AI, logging, CLI complete.  
🟡 Current: Begin true Riftbound mechanics (combat, runes, movement).  
⚪ Next: Add full ability system (Active, Triggered, Passive) + keyword stack resolution.


