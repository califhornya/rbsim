"""Scelta del campo di battaglia per posto (bf_a, bf_b) in Rust, come Python
`build_game(bf_a=, bf_b=)` / `_select_battlefield`:
- senza scelte le estrazioni sono quelle di prima (campi uguali a Python);
- con scelte forzate: campi e victory_score uguali a Python (tutte le 9 combinazioni);
- scelta non valida = a caso, come Python;
- partite intere identiche Rust / Python con campi forzati."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/rust"))

import json  # noqa: E402

STORICO = "6427b90"


def _rust(seed, mu, a=None, b=None, first="a"):
    from riftbound.rs import rust_bridge as rb
    from riftbound.rs.mazzi import decks
    g = rb.build(seed, *decks(mu), first, 40, regole=STORICO, bf_a=a, bf_b=b)
    raw = json.loads(g.raw_dump())
    objs = raw["objs"]
    names = [objs[objs[r["$ref"]]["card"]["$ref"]]["name"] for r in raw["root"]["battlefields"]]
    return names, raw["root"]["victory_score"]


def _py(seed, mu, a=None, b=None, first="a"):
    from riftbound.core.game_factory import build_game
    from riftbound.rs.mazzi import decks
    da, db = decks(mu)
    gs = build_game(game_seed=seed, deck_a_path=da, deck_b_path=db, ai_a=None, ai_b=None,
                    first_player=first, bf_a=a, bf_b=b)
    return [bf.card.name for bf in gs.battlefields], gs.victory_score


def _names(mu):
    from riftbound.core.game_factory import deck_battlefield_names
    from riftbound.rs.mazzi import decks
    da, db = decks(mu)
    return deck_battlefield_names(da), deck_battlefield_names(db)


@pytest.mark.parametrize("mu", ["EK", "ES"])
def test_senza_scelte_uguale_a_python(mu):
    for seed in range(1, 61):
        assert _rust(seed, mu) == _py(seed, mu), seed


@pytest.mark.parametrize("mu", ["EK", "ES"])
def test_nove_combinazioni(mu):
    na, nb = _names(mu)
    assert len(na) == 3 and len(nb) == 3
    for i, a in enumerate(na):
        for j, b in enumerate(nb):
            for seed in (3, 8):
                r = _rust(seed, mu, a, b)
                assert r == _py(seed, mu, a, b), (seed, a, b)
                assert r[0] == [a, b]


def test_scelta_non_valida_a_caso():
    for seed in range(1, 21):
        assert _rust(seed, "EK", "Inesistente", None) == _py(seed, "EK", "Inesistente", None)
        assert _rust(seed, "EK", None, "Inesistente") == _py(seed, "EK", None, "Inesistente")


def test_scelta_non_consuma_il_caso():
    # scelto un campo, l'altro posto resta quello che sarebbe stato a caso con il solo suo tiro
    na, nb = _names("EK")
    for seed in range(1, 11):
        assert _rust(seed, "EK", na[1], None) == _py(seed, "EK", na[1], None)


@pytest.mark.parametrize("mu,seed,starter", [("EK", 3, "a"), ("EK", 4, "b"), ("ES", 5, "a"), ("ES", 6, "b")])
def test_partita_intera_con_campi_forzati(mu, seed, starter):
    import autonome
    na, nb = _names(mu)
    for a, b in ((na[0], nb[2]), (na[2], nb[1])):
        r = autonome.compare(seed, {"A": "simple_trade", "B": "simple_trade"}, starter, mu, a, b)
        assert r["rust_error"] is None
        assert "first_difference" not in r, r.get("first_difference")
        assert r["py"] == r["rs"]
