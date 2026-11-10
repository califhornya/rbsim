# Riftbound Simulator

A Python simulator for **Riftbound**, the League of Legends TCG, built as the
environment for an AlphaZero-style self-play agent. A learner wins the game it
is trained in, bugs included, so the rules engine has to be right before
training means anything.

This README is the entry point: what is here, how to run it, and where it
stands. Open work is in [`BACKLOG.md`](BACKLOG.md) ("Open now").

## Quick start

```bash
uv sync                  # engine only (numpy, no torch)
uv run pytest -q         # the suite; torch tests skip without the rl extra
uv run rbsim simulate --deckA riftbound/data/decks/precon_zed.json \
                      --deckB riftbound/data/decks/precon_shen.json --games 100 --seed 42
```

With the training stack (PyTorch, an optional extra):

```bash
uv sync --extra rl
uv run python scripts/train_selfplay.py \
    --decks riftbound/data/decks/precon_zed.json riftbound/data/decks/precon_shen.json \
    --iterations 50 --games-per-iter 16 --mcts-iters 100 --run-dir runs/precons
uv run python scripts/coach.py --net runs/precons/net.pt   # coach mode, http://127.0.0.1:8765
```

The net uses CUDA when available, else the CPU; all randomness is seedable.

## Layout

| Path | What |
|---|---|
| `riftbound/core/` | The rules engine: `loop.py` (turn structure, chain, payments), `effects.py` (effect handlers), `combat.py`, `legality.py`, `match.py` (Bo3) |
| `riftbound/registry/` | Card loading (`cards_registry.py`) and the engine vocabulary (`engine_vocab.py`) |
| `riftbound/data/cards/all_cards.json` | The card corpus with its encoded effects. Every `.json` under `data/cards/` is loaded as cards |
| `riftbound/data/decks/` | 10 decks; training uses `precon_zed` and `precon_shen` |
| `riftbound/data/reference/` | `piltover_archive.json`: the official printed text, errata included (not loaded by the engine) |
| `riftbound/ai/` | Heuristic agents, MC / ISMCTS search, the net (`net.py`, `encoding.py`), net-guided MCTS, self-play, coach |
| `scripts/` | Training, coach, round robin, game tracer, audits (`card_text_audit.py`, `coverage_audit.py`, `choice_audit.py`, `piltover_sync.py`) |
| `tests/` | ~1660 tests, including the golden games (`tests/golden_games.json`) |
| `docs/rules/` | Core Rules (revision 2026-10-09) and Tournament Rules as text |
| `docs/MECHANICS.md` | Rules mechanics, one row each, with status (some rows lag the code: see its header) |
| `docs/reports/` | Generated reports (coverage, choice audit) |
| `docs/history/` | Old status notes and issue logs, kept for the record. Not the current state |

## Where it stands (2026-11-10)

- **Engine.** 1100 cards (Origins, Spiritforged, Unleashed, Vendetta, Radiance,
  Proving Grounds), every set read card by card with a test per card
  (`BACKLOG.md` A-G, closed). The two training precons match the official text
  on all 51 cards; the other eight decks have 15 cards that don't
  (`BACKLOG.md` O1).
- **Tests.** Without torch: 1628 passed, 5 skipped. With torch: 1660 passed.
- **AI.** Heuristic agents, search agents, net-guided MCTS with self-play
  training, learned mulligan and battlefield choice, coach mode. The last
  training runs reached 0.50 against `simple_trade`; nets saved before F3 don't
  load (the encoding changed) and were trained on older rules.
- **Next.** An independent rules audit (`BACKLOG.md` O2), then training.

## Conventions

- A card or rule is done when a test plays the situation and checks what the
  card text / Core Rules say, not when the card "has effects".
- `tests/golden_games.json` freezes 20 seeded games. Regenerate it
  (`RBSIM_REGEN_GOLDEN=1 uv run pytest tests/test_golden_games.py -q`) only for
  an intended rules change, and read the diff.
- Card text: check `all_cards.json` against the printed text with
  `uv run python scripts/piltover_sync.py compare` (`fetch` refreshes the
  reference data).
- New work goes in `BACKLOG.md` "Open now".
