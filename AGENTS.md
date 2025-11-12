# RIFTBOUND MECHANICS IMPLEMENTATION NOTES

## Overview
This document defines structural and gameplay updates to align the simulator with Riftbound’s real resource and setup rules.  
The changes concern **Runes**, **Legends**, and supporting directory organization.

---

## 1. RUNE SYSTEM

### 1.1 Summary
Runes act as the player’s renewable energy source.  
They exist in a **separate deck**, not the main deck, and are **not drawn** into the hand.  
They can be **ready** or **exhausted**, and sometimes **recycled** (placed at the bottom of the rune deck).

### 1.2 New Class: `RuneDeck`
```python
@dataclass
class RuneDeck:
    runes: list[RuneCard]

    def recycle(self, rune: RuneCard) -> None:
        """Put a rune at the bottom of the deck."""
        self.runes.append(rune)
```

### 1.3 Player Integration
Add fields to `Player`:
```python
rune_deck: RuneDeck
rune_pool: Dict[Domain, List[Rune]]
```

Add methods:
```python
def unlock_runes(self, n: int = 2) -> None:
    """Bring n runes from the deck into play (max 12 total)."""
    for _ in range(n):
        if len(self.rune_pool) >= 12 or not self.rune_deck.runes:
            break
        rune_card = self.rune_deck.runes.pop(0)
        self.add_rune(rune_card.domain)

def recycle_rune(self, domain: Domain) -> bool:
    """Recycle one rune of the given domain (move from play to bottom of deck)."""
    runes = self.rune_pool.get(domain, [])
    if not runes:
        return False
    rune = runes.pop(0)
    self.rune_deck.recycle(rune)
    return True
```

Extend `pay_cost()`:
```python
def pay_cost(self, cost_energy: int = 0, cost_power: Optional[Domain] = None) -> bool:
    if self.energy < cost_energy:
        return False
    self.energy -= cost_energy
    if cost_power:
        return self.recycle_rune(cost_power)
    return True
```

### 1.4 Game Setup
Starting runes:
- Player A (first): 2
- Player B (second): 3

Add:
```python
A.unlock_runes(2)
B.unlock_runes(3)
```
to `GameLoop.start()` before the first turn.

### 1.5 Rune Ramp per Turn
At the start of **each of your turns**, unlock 2 more runes:
```python
def _phase_beginning(self, active: str) -> int:
    ...
    player = self.gs.get_player(active)
    player.unlock_runes(2)
```

### 1.6 Channeling (unchanged)
Existing `Player.channel()` logic already handles refreshing all runes and exhausting two per turn for +energy and +power.  
No change needed.

---

## 2. LEGENDS

### 2.1 Standardization
- Legends are **not part of the main deck**.
- Stored separately in `/data/cards/legends/`.
- Always tagged:
  ```json
  "tags": ["legend"]
  ```
- Category: `"LEGEND"`
- Have no Might or combat stats.

### 2.2 Optional Zone
Add optional structure (future use):
```python
@dataclass
class LegendZone:
    legend: LegendCard
```
and reference in `GameState`:
```python
legend_A: Optional[LegendCard] = None
legend_B: Optional[LegendCard] = None
```

### 2.3 Passives
Legend passives (e.g., Ahri, Nine-Tailed Fox) can remain unimplemented for now.  
Only data tagging is required for analytics and deck metadata.

---

## 3. DIRECTORY STRUCTURE

Proposed structure to organize cards, runes, and decks:

```
rbsim/
├─ core/
│  ├─ ...
│
├─ data/
│  ├─ cards/
│  │  ├─ units/
│  │  ├─ spells/
│  │  ├─ gear/
│  │  ├─ runes/
│  │  └─ legends/
│  ├─ decks/
│  │  ├─ ahri_control.json
│  │  ├─ jynx_aggro.json
│  │  └─ volibear_big.json
│  └─ schema.py
│
├─ ai/
│  ├─ heuristics/
│  │  ├─ simple_control.py
│  │  ├─ simple_aggro.py
│  │  └─ ...
│
└─ AGENTS.md
```

---

## 4. SUMMARY TABLE

| Mechanic | Implemented | Change Required | Notes |
|-----------|--------------|----------------|-------|
| Energy / Power system | ✅ | — | Works via `channel()` and `pay_cost()`. |
| Separate Rune deck | ❌ | Add `RuneDeck` | Prevents runes being drawn from main deck. |
| Recycling mechanic | ❌ | Add `recycle_rune()` | For power payment (put rune bottom of deck). |
| Rune unlock ramp | ❌ | Add `unlock_runes(2)` | Beginning of each turn. |
| Starting runes | ❌ | Initialize 2/3 runes per player | Done in `GameLoop.start()`. |
| Legends excluded from deck | ⚠️ Partial | Ensure `"tags": ["legend"]` | Stored in separate folder. |
| Legend passives | ❌ | Deferred | Implement later. |

---

## 5. EXAMPLE DATA

### 5.1 Rune Example
```json
{
  "name": "Mind Rune",
  "category": "RUNE",
  "domain": "MIND",
  "tags": ["basic_rune"]
}
```

### 5.2 Legend Example
```json
{
  "name": "Ahri, Nine-Tailed Fox",
  "category": "LEGEND",
  "domain": "MIND",
  "tags": ["legend"],
  "effects": [
    {"effect": "passive_placeholder", "description": "When an enemy unit attacks a battlefield you control, give it -1 Might this turn (min 1)."}
  ]
}
```

---

**End of file.**
