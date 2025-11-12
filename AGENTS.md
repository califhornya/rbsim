# ⚔️ rbsim | Real Riftbound Mechanics Roadmap (Final)

## Objective
Implement **real Riftbound game mechanics** on top of the simulator, using the *Riftbound Core Rules v1.1*.  
This roadmap is now actionable — you can start coding directly from Phase 0.

---

## Phase 0 — Card Registry & Effect System (Integration Step)

### Goal
Introduce a data-driven card registry and minimal effect resolution. This enables loading cards from JSON instead of hardcoding classes.

### Tasks
1. **Card Registry Setup**
   - File: `riftbound/core/cards_registry.py`
   - Add dataclass `CardSpec` and `load_cards_json()` loader.
   - Registry loads all `.json` files under `riftbound/data/cards/`.
   - Example `riftbound/data/cards/core/unit.json`:
     ```json
     [
       {
         "name": "Stalwart Recruit",
         "category": "UNIT",
         "domain": "ORDER",
         "cost_energy": 1,
         "might": 2,
         "keywords": []
       }
     ]
     ```

2. **Effect Registry**
   - File: `riftbound/core/effects.py`
   - Define `@effect` decorator to register functions in `REGISTRY`.
   - Example effects:
     ```python
     @effect("deal_damage")
     def _deal_damage(ctx, spec): ...

     @effect("grant_might")
     def _grant_might(ctx, spec): ...
     ```

3. **Integrate with GameLoop**
   - Add small `EffectContext` class inside `loop.py`.
   - On Spell or Gear play, resolve registered effects:
     ```python
     spec = CARD_REG.get(card.name)
     if spec and spec.effects:
         self._resolve_on_play_effects(spec)
     ```

4. **Minimal Example Cards**
   - Only three cards at this stage:
     - **Stalwart Recruit** (Unit)
     - **Bolt** (Spell)
     - **Iron Shield** (Gear)
   - Place under `riftbound/data/cards/core/`.

✅ *Deliverable:* Running simulation uses JSON-driven cards. “Bolt” resolves via the effect system.

---

## Phase 1 — Phases & Turn Structure

### Tasks
1. Expand `Phase` enum with `AWAKEN`, `BEGINNING`, `DRAW`, `MAIN`, `COMBAT`, `SHOWDOWN`, `END`.
   NB: (if no battlefields are challegend, no showdows nor combats happen.
      it means a player just cast some spells or directly passed the turn)
2. Add dedicated phase handlers in `GameLoop`.
3. Introduce lightweight event bus:
   ```python
   game.trigger(event="BEGINNING", actor=player)
   ```
4. Add placeholder functions for advanced phases (Showdown, Recovery).

---

## Phase 2 — Battlefield & Legend System

### Tasks
1. Add real `BattlefieldCard` logic with passive modifiers. (e.g., +1 Might, Spells do +1 damage).
2. Implement `LegendCard` mechanics (unique per player, persistent, affects scoring or stats).

---

## Phase 3 — Stack & Priority System

### Tasks
1. Implement minimal spell stack:
   ```python
   class Stack:
       def push(effect): ...
       def resolve(): ...
   ```
2. Modify `_apply_action()` to push Spell effects instead of resolving immediately.
3. Add response window before resolution (AI opportunity to act).

---

## Phase 4 — Resource & Rune Expansion

### Tasks
1. Implement *Advanced Channeling* rules (exhaustion, recycle).

---

## Phase 5 — Controlled Card Expansion

### Tasks
1. User will expand JSON library.
   - Add 3 placeholder cards.
   - Validate format with `rbsim validate-cards`.
3. Keep effects modular — all logic in `effects.py`.

---

## Phase 6 — AI Adaptation & Validation

### Tasks
1. Update SimpleAggro and SimpleControl to evaluate card metadata.
2. Add new heuristic agents for testing (e.g., Midrange, Combo).
3. Build regression tests: 100-game runs to ensure determinism.
4. Connect to analytics layer to analyze card/AI performance.

---

## Milestone Result
After Phase 6:
- All actions, effects, and outcomes are logged to the analytics DB.
- The engine is modular: new cards or rules only require JSON or effect updates.

---

## Implementation Notes
- Keep deterministic RNG (`seed`) for reproducibility.
- Always log plays and effects using the existing `GameRecorder`.
- Keep cards modular and data-driven — no class-per-card.
- Reference: *Riftbound Core Rules v1.1* for card behavior and phase timing.

