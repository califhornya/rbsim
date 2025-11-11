# Riftbound Simulator | Dev Agent Guide

## Repo Overview
**Project:** `rbsim`  
A fully automated Riftbound match simulator for AI self-play, testing decks and heuristics.  
Repository: [github.com/califhornya/rbsim](https://github.com/califhornya/rbsim)

---

## Dev Environment
- Run `uv venv && uv sync` to create and sync the virtual environment.
- Launch interactive shell: `uv run python -i`
- CLI entrypoint: `rbsim`  
  - Example: `rbsim --games 50 --aiA aggro --aiB control --victory-score 8`
- Add dependencies with `uv add <package>`.
- Check imports and formatting with `ruff check . && black .`.

---

## Testing
- All logic is deterministic via seeded RNG.  
- Database results can be inspected manually:
  ```python
  import sqlite3
  con = sqlite3.connect("results.db")
  print(con.execute("SELECT COUNT(*) FROM games").fetchall())
  con.close()
  ```
- For quick smoke tests:  
  ```bash
  rbsim --games 5 --seed 123
  ```
- Future: integrate `pytest` once combat and resource systems are finalized.

---

## Code Architecture
```
riftbound/
├── ai/heuristics/        # Agents (SimpleAggro, SimpleControl, base)
├── core/                 # Game logic (battlefields, loop, state)
├── data/                 # Database schema + writer
└── cli/                  # CLI entrypoint (Typer)
```

---

## Dev Tasks & Conventions
### Commit Rules
- Use present tense: *“Add Rune system,” “Refactor combat loop.”*
- Always run local lint + simulation before committing:
  ```bash
  ruff check . && uv run rbsim --games 1
  ```

### Pull Requests
- **Title format:** `[rbsim] <feature>`  
- Include a one-line summary of the rules implemented.  
- Ensure the CLI runs end-to-end with no DB schema breaks.

---

## Next Milestone — Core Riftbound Mechanics
**Goal:** transition from abstract simulation to full rules-based Riftbound play.

### Phase 1
- Two total **Battlefields** (confirmed per rulebook).
- Full **Hold** and **Conquer** logic (implemented).

### Phase 2
- Implement **Rune Channeling / Energy** system (implemented).
- Add **Card costs** + resource tracking.
- Introduce **Movement**, **Showdowns**, and basic **Keywords**.

---

## Design Notes
- Deterministic seeds for reproducibility.
- Modular, pluggable AI system.
- SQLite logs for analysis.
- Parallelizable core loop (future).
