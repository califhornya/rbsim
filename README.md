# Riftbound Simulator

A Python simulator for **Riftbound**, the League of Legends TCG, built as the
environment for an AlphaZero-style self-play agent. A learner wins the game it
is trained in, bugs included, so the rules engine has to be right before
training means anything.

This README is the entry point: what is here, how to run it, and where it
stands. Current state, decisions and next steps: [`STATO.md`](STATO.md) (Italian).
Open work: [`BACKLOG.md`](BACKLOG.md).

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
uv run --extra rl python scripts/coach.py                  # play against the champion, http://127.0.0.1:8765
uv run --extra rl python scripts/coach.py --net runs/precons/net.pt   # coach mode: the net's advice
```

The champion is `runs/sett/ekris_s12/ckpt_040000.pt` (`--campione`, `--budget 0.4`);
on the Mac double-click `scripts/allenatore.command`.

The net uses CUDA when available, else the CPU; all randomness is seedable.

## Layout

| Path | What |
|---|---|
| `riftbound/core/` | The rules engine: `loop.py` (turn structure, chain, payments), `effects.py` (effect handlers), `combat.py`, `legality.py`, `match.py` (Bo3) |
| `riftbound/registry/` | Card loading (`cards_registry.py`) and the engine vocabulary (`engine_vocab.py`) |
| `riftbound/data/cards/all_cards.json` | The card corpus with its encoded effects. Every `.json` under `data/cards/` is loaded as cards |
| `riftbound/data/decks/` | The two precons (`precon_zed`, `precon_shen`) and the owner's competitive decks: `competitive_evelynn`, `competitive_khazix` (in use); `competitive_kaisa`, `competitive_kennen` (banned since 2026-11-17, kept as test fixtures and for the existing nets) |
| `riftbound/data/reference/` | `piltover_archive.json`: the official printed text, errata included (not loaded by the engine) |
| `riftbound/ai/` | Heuristic agent (`simple_trade`), random, MC / ISMCTS search, the net (`net.py`, `encoding.py`), net-guided MCTS, self-play, coach |
| `scripts/` | Training, coach, scenarios, round robin, game tracer, card import, audits (`card_text_audit.py`, `coverage_audit.py`, `choice_audit.py`, `piltover_sync.py`); `diag/`: net measurements |
| `tests/` | ~1790 tests (`tests/audit/`: one per rules deviation), including the golden games (`tests/golden_games.json`) |
| `docs/rules/` | Core Rules (revision 2026-10-09) and Tournament Rules as text |
| `docs/MECHANICS.md` | Rules mechanics, one row each, with status (some rows lag the code: see its header) |
| `docs/reports/` | Generated reports (coverage, choice audit) |
| `docs/audit/AUDIT.md` | The rules audit: every deviation found (D1-D68; D59-D68 open), the owner's rulings (Q1-Q6), what was not checked. `docs/audit/revisione_esterna/`: the external review behind D59-D68 |
| `docs/PIANO_MOTORE.md` | The plan for the engine's fixes and structure (not started) |
| `docs/bot/` | The owner's judgments for the bot (`GIUDIZI.md`) and the scenarios |
| `docs/archivio/` | Old status notes, issue logs and the closed backlog (A-G, cited in code comments). Not the current state |

## Where it stands

See [`STATO.md`](STATO.md): it is the only status file, updated at the end of
each work phase. Short version: the engine is audited against the Core Rules and
the printed cards (`docs/audit/AUDIT.md`); training is paused because the nets
stay weak against `simple_trade`.

## Conventions

- A card or rule is done when a test plays the situation and checks what the
  card text / Core Rules say, not when the card "has effects".
- `tests/golden_games.json` freezes 28 seeded games (final state only). Regenerate it
  (`RBSIM_REGEN_GOLDEN=1 uv run pytest tests/test_golden_games.py -q`) only for
  an intended rules change, and read the diff.
- Card text: check `all_cards.json` against the printed text with
  `uv run python scripts/piltover_sync.py compare` (`fetch` refreshes the
  reference data).
- New open items go in `BACKLOG.md`; the state goes in `STATO.md`.
