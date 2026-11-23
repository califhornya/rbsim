"""Bridge to the Rust engine (riftbound_rs, built from rust/rbsim-py with
maturin): the registry, building games, canonicalizing Rust dumps with the
same Canon as Python's (riftbound/rs/canon.py)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from riftbound.rs.canon import Canon

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_JSON = ROOT / "rust/data/registry.json"


def available() -> bool:
    try:
        import riftbound_rs  # noqa: F401
        return True
    except ImportError:
        return False


@lru_cache(maxsize=1)
def registry():
    import riftbound_rs
    if not REGISTRY_JSON.exists():
        from riftbound.rs.export_registry import main as export
        export()
    return riftbound_rs.Registry(str(REGISTRY_JSON))


def build(seed: int, deck_a: Path, deck_b: Path, first_player: str = "a", max_turns: int = 40):
    import riftbound_rs
    return riftbound_rs.Game.build(registry(), seed, Path(deck_a).read_text(), Path(deck_b).read_text(),
                                   first_player, max_turns)


def canonical(raw: dict, canon: Canon) -> dict:
    """A raw dump (Rust's or Python's RawDumper) through `canon`."""
    return canon.canonical(raw)


def canonical_rust(game, canon: Canon | None = None) -> dict:
    return (canon or Canon()).canonical(json.loads(game.raw_dump()))
