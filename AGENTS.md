# 📊 rbsim | Analytics Roadmap (Codex-Optimized)

## Objective
Upgrade `rbsim` into a **data-rich simulator** for large-scale analysis.  
Focus: analytics infrastructure — not game-rule fidelity.

---

## Phase A — Database Expansion

### Tasks
1. Extend `riftbound/data/schema.py`:
   - Add ORM models: `Deck`, `Draw`, `Hand`, `Board`, `Play`, `AIStats`.
   - Use `UUID` for card instances.
   - Keep backward-compatible `DB_VERSION = 2`.
2. Update `writer.py`:
   - Add `record_draw()`, `record_play()`, `record_board()`, etc.
3. Modify `GameLoop` and `Player`:
   - Log all card transitions: draw, play, death.
   - Hook `record_*` functions after each event.

### Schema Summary
| Table | Purpose |
|--------|----------|
| `Deck` | Stores cardlist, hash, and AI used. |
| `Game` | Match metadata (seed, winner, turns, etc.). |
| `Turn` | Turn-level summary. |
| `Draw` | Card draw events. |
| `Hand` | Hand snapshot at turn end. |
| `Board` | Battlefield summary per turn. |
| `Play` | Card play / cast events. |
| `AIStats` | Aggregate results per AI type. |

---

## Phase B — Replay / Export Layer

### Tasks
1. Add module: `riftbound/data/export.py`.
2. Implement:
   ```bash
   rbsim export --query "SELECT winner, turns FROM games" --out results.csv
   ```
3. Support formats: `.csv`, `.json`, `.parquet`.
4. Add `rbsim replay <game_id>` to reconstruct a single match from logs.

---

## Phase C — Card Tracking

### Tasks
1. Each `Card` gets `uuid = uuid4()`.
2. Record state transitions:
   - `DECK → HAND` → `BOARD` → `GRAVE`.
3. Add helper:
   ```python
   def record_card_event(session, game_id, card_uuid, phase, action, turn_no): ...
   ```
4. Enable queries like:
   ```sql
   SELECT card_name, AVG(turns_alive)
   FROM plays
   JOIN cards USING (card_uuid)
   GROUP BY card_name;
   ```

---

## Phase D — AI Benchmarking

### Tasks
1. Extend `record_game()` with `ai_a`, `ai_b`, `avg_turns`, `avg_energy_used`.
2. Create new table `AIStats`:
   - `ai_name`, `wins`, `losses`, `draws`, `avg_turns`.
3. Provide summary CLI:
   ```bash
   rbsim stats
   ```

---

## Expected Outcome
- Full per-turn, per-card, per-AI data capture.
- Ready for analytics via SQL or Python (pandas).
- Reproducible, deterministic simulation datasets.
- Scalable to millions of games.

---

## References
Repo: [github.com/califhornya/rbsim](https://github.com/califhornya/rbsim)  
Rulebook: *Riftbound Core Rules v1.1* (for mechanics context).  
Inspiration: *Magic Simulator (Genesis Project)*.