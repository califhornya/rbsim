"""Rules audit, ninth pass (docs/audit/AUDIT.md): copies of the Chosen Champion.

§103.3.b / §103.3.b.1: up to 3 copies of a named card, the Chosen Champion
included ("Volibear, Furious as its Chosen Champion and still include 2 more
copies of Volibear, Furious in their Main Deck"). §103.3.a.3: any Champion
Unit with the Chosen Champion's name, wherever it is, is also the Chosen
Champion for rules and effects. The real case: 82FAW's Ivern list (RiftAtlas,
2026-11-18), `docs/bot/partite/82FAW_ivern_lista.txt`, with Ivern, Nurturer
as champion and one more copy in the MainDeck."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from riftbound.core.combat import UnitInPlay
from riftbound.core.game_factory import make_deck_from_file
from riftbound.registry.cards_registry import load_deck_json

from audit_helpers import act, card, choices, labels, legend, setup, unit

ROOT = Path(__file__).resolve().parents[2]
IVERN_TXT = ROOT / "docs" / "bot" / "partite" / "82FAW_ivern_lista.txt"
IVERN = "Ivern Nurturer"


def _ivern_list() -> dict:
    """The list as `scripts/deck_from_txt.py` reads it (before validation)."""
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from deck_from_txt import build_deck
    return build_deck(IVERN_TXT.read_text(encoding="utf-8"))


def _write(tmp_path: Path, deck: dict) -> Path:
    path = tmp_path / "deck.json"
    path.write_text(json.dumps(deck), encoding="utf-8")
    return path


def _with(deck: dict, section: str, name: str, count: int) -> dict:
    """`deck` with `count` copies of `name` in `section` (0 removes them)."""
    out = dict(deck)
    entries = [dict(e) for e in deck.get(section, []) if e["name"] != name]
    if count:
        entries.append({"name": name, "count": count})
    out[section] = entries
    return out


# -- D69. The loader refuses the Chosen Champion in the Main Deck --------------------

def test_the_ivern_list_loads_with_its_champion_and_one_more_copy(tmp_path):
    """82FAW's list: Ivern, Nurturer as champion and 1 in the MainDeck (39
    cards with it): 40 cards, legal. It raised "Champion ... must not appear
    in the cards list"."""
    cards, _runes, champion, legend_spec, _bfs = load_deck_json(_write(tmp_path, _ivern_list()))
    assert champion is not None and champion.name == IVERN
    assert legend_spec is not None and legend_spec.name == "Ivern Green Father"
    assert len(cards) == 39 and [c.name for c in cards].count(IVERN) == 1


def test_the_champion_plus_two_copies_is_legal_a_fourth_copy_is_not(tmp_path):
    """§103.3.b.1, the Volibear example: the champion and 2 more copies in the
    Main Deck. The champion counts towards the 3: a third copy in the Main
    Deck, or a third one in the sideboard (main deck and sideboard combined,
    Tournament Rules 403.3), is a fourth copy."""
    base = _with(_ivern_list(), "cards", "Block", 1)        # 38 + the copies below
    base = _with(base, "sideboard", "Disarming Rake", 0)     # 3 Rake: 1 main + 2 sideboard
    two = _with(base, "cards", IVERN, 2)
    cards, *_ = load_deck_json(_write(tmp_path, two))
    assert [c.name for c in cards].count(IVERN) == 2

    three = _with(_with(base, "cards", IVERN, 3), "cards", "Block", 0)
    with pytest.raises(ValueError, match="4 copies of 'Ivern Nurturer'"):
        load_deck_json(_write(tmp_path, three))

    sided = _with(two, "sideboard", IVERN, 1)
    with pytest.raises(ValueError, match="4 copies of 'Ivern Nurturer'"):
        load_deck_json(_write(tmp_path, sided))


def test_a_copy_of_the_champion_drawn_and_played_from_hand(tmp_path):
    """The copy in the Main Deck is drawn and played from hand as the unit it
    is ("when you play me": Ivern looks at the top 3, draws the Poro, buffs a
    friendly unit). The Chosen Champion stays in its zone, undeployed, and can
    still be played: two Ivern on the board."""
    deck, _runes, champion, _legend, _bfs = make_deck_from_file(_write(tmp_path, _ivern_list()))
    loop, a, b = setup()
    legend(loop, "A", "Ivern Green Father")
    loop.gs.champion_A = champion
    copy = next(c for c in deck.cards if c.name == IVERN)
    rest = [c for c in deck.cards if c is not copy]
    poro = next(c for c in rest if c.name == "Stalwart Poro")
    spells = [c for c in rest if c.name in ("Defy", "Block")][:2]
    others = [c for c in rest if c is not poro and c not in spells]
    a.deck.cards = others + [spells[0], poro, spells[1], copy]   # the copy on top

    drawn = a.draw()
    assert drawn is copy and a.hand == [copy]
    offered = labels(loop, "A")
    assert f"Play {IVERN}" in offered and f"Deploy champion {IVERN}" in offered

    choices(loop, {})                                   # baseline answers
    act(loop, "A", f"Play {IVERN}")
    assert [u.card for u in a.base_units] == [copy]
    assert a.hand == [poro]                             # "draw it"
    assert a.base_units[0].might_counters == 1          # a Poro: "[Buff] a friendly unit"
    assert loop.gs.champion_A is champion and not loop.gs.champion_A_deployed

    act(loop, "A", f"Deploy champion {IVERN}")
    assert [u.card for u in a.base_units] == [copy, champion]
    assert loop.gs.champion_A_deployed
    assert not [lab for lab in labels(loop, "A") if lab.startswith("Deploy champion")]


# -- D70. Hallowed Tomb returns only the card chosen as champion ----------------------

def test_hallowed_tomb_returns_a_copy_of_the_champion_from_the_trash():
    """Hallowed Tomb: "When you hold here, you may return your Chosen Champion
    from your trash to your Champion Zone if it is empty." §103.3.a.3: a copy
    of the champion in the trash is the Chosen Champion too ("Any additional
    copies of Jinx, Rebel in their ... trash ... also count as their Chosen
    Champion"). The champion was deployed and is on the board, the copy played
    from hand died: the Tomb returned nothing (it looked for the champion card
    itself). The copy goes to the Champion Zone and can be played from there."""
    loop, a, b = setup()
    loop.gs.battlefields[0].card = card("Hallowed Tomb")
    champion, copy = card(IVERN), card(IVERN)
    loop.gs.champion_A, loop.gs.champion_A_deployed = champion, True
    a.base_units.append(UnitInPlay(card=champion, ready=True))   # deployed, on the board
    a.trash.extend([card("Ivern Friend to All"), copy])          # another name: not it
    loop.gs.battlefields[0].add_unit("A", unit("Holder", 1))
    loop._fire_scoring_trigger("on_hold", loop.gs.battlefields[0], "A")
    assert [c.name for c in a.trash] == ["Ivern Friend to All"]
    assert loop.gs.champion_A is copy and not loop.gs.champion_A_deployed
    assert f"Deploy champion {IVERN}" in labels(loop, "A")


def test_hallowed_tomb_still_returns_nothing_with_the_champion_zone_full():
    """"If it is empty": with the champion still in its zone, a copy in the
    trash stays there."""
    loop, a, b = setup()
    loop.gs.battlefields[0].card = card("Hallowed Tomb")
    champion, copy = card(IVERN), card(IVERN)
    loop.gs.champion_A, loop.gs.champion_A_deployed = champion, False
    a.trash.append(copy)
    loop.gs.battlefields[0].add_unit("A", unit("Holder", 1))
    loop._fire_scoring_trigger("on_hold", loop.gs.battlefields[0], "A")
    assert a.trash == [copy] and loop.gs.champion_A is champion



# -- The deck: competitive_ivern, 82FAW's list ---------------------------------------

DECKS = ROOT / "riftbound" / "data" / "decks"


def test_competitive_ivern_is_82faws_list():
    """`competitive_ivern.json` is `scripts/deck_from_txt.py` on the .txt: 40
    cards with the champion (one more Ivern, Nurturer in the Main Deck), 12
    runes, 3 battlefields, 10 in the sideboard."""
    data = json.loads((DECKS / "competitive_ivern.json").read_text(encoding="utf-8"))
    assert data == _ivern_list()
    cards, runes, champion, _legend, battlefields = load_deck_json(DECKS / "competitive_ivern.json")
    assert len(cards) + 1 == 40 and champion is not None and champion.name == IVERN
    assert sum(n for _, n in runes) == 12 and len(battlefields) == 3
    assert sum(c["count"] for c in data["sideboard"]) == 10


def test_ivern_plays_its_champion_copy_from_hand_in_whole_games():
    """Twenty seeded games, Ivern against Evelynn, `simple_trade` on both sides:
    they all end, and in some of them the copy in the Main Deck is drawn and
    played from hand while the Chosen Champion is another card."""
    from riftbound.core.game_factory import build_game
    from riftbound.core.loop import GameLoop

    copies_played = 0
    for seed in range(20):
        gs = build_game(game_seed=seed, deck_a_path=DECKS / "competitive_ivern.json",
                        deck_b_path=DECKS / "competitive_evelynn.json",
                        ai_a="simple_trade", ai_b="simple_trade")
        loop = GameLoop(gs)
        play_unit = loop._play_unit

        def spy(c, side, *args, _play=play_unit, _gs=gs, **kw):
            nonlocal copies_played
            if side == "A" and c.name == IVERN and c is not _gs.champion_A:
                copies_played += 1
            return _play(c, side, *args, **kw)
        loop._play_unit = spy
        assert loop.start().winner in ("A", "B", "DRAW")
    assert copies_played >= 1
