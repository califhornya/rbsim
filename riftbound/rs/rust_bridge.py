"""Bridge to the Rust engine (riftbound_rs, built from rust/rbsim-py with
maturin): the registry, building games, canonicalizing Rust dumps with the
same Canon as Python's (riftbound/rs/canon.py)."""
from __future__ import annotations

import json
import threading
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


_LOCAL = threading.local()


def registry():
    """The card registry, one per thread: a riftbound_rs object stays in the
    thread that made it (arena_mista.py plays the Rust copy in a thread)."""
    reg = getattr(_LOCAL, "registry", None)
    if reg is None:
        import riftbound_rs
        if not REGISTRY_JSON.exists():
            from riftbound.rs.export_registry import main as export
            export()
        reg = _LOCAL.registry = riftbound_rs.Registry(str(REGISTRY_JSON))
    return reg


def build(seed: int, deck_a: Path, deck_b: Path, first_player: str = "a", max_turns: int = 40):
    import riftbound_rs
    return riftbound_rs.Game.build(registry(), seed, Path(deck_a).read_text(), Path(deck_b).read_text(),
                                   first_player, max_turns)


def canonical(raw: dict, canon: Canon) -> dict:
    """A raw dump (Rust's or Python's RawDumper) through `canon`."""
    return canon.canonical(raw)


def canonical_rust(game, canon: Canon | None = None) -> dict:
    return (canon or Canon()).canonical(json.loads(game.raw_dump()))
