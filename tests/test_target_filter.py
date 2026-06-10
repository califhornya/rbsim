"""B2 — new target_filter keys in effects._passes_filter."""

import random

from riftbound.core.cards import UnitCard
from riftbound.core.combat import UnitInPlay
from riftbound.core.effects import _passes_filter
from riftbound.core.loop import EffectContext, GameLoop
from riftbound.core.player import Deck, Player, RuneDeck
from riftbound.core.state import GameState


def _ctx(source_card=None) -> EffectContext:
    a = Player(name="A", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    b = Player(name="B", deck=Deck(cards=[]), rune_deck=RuneDeck([]))
    loop = GameLoop(GameState(rng=random.Random(1), A=a, B=b))
    bf = loop.gs.battlefields[0]
    return EffectContext(loop, source_card or UnitCard(name="Src"), a, b, bf)


def _unit(name="U", might=3, tags=None, is_token=False, might_counters=0) -> UnitInPlay:
    return UnitInPlay(card=UnitCard(name=name, might=might, tags=tags or []),
                      is_token=is_token, might_counters=might_counters)


def test_non_token():
    ctx = _ctx()
    assert _passes_filter(_unit(is_token=False), {"non_token": True}, ctx) is True
    assert _passes_filter(_unit(is_token=True), {"non_token": True}, ctx) is False


def test_is_buffed():
    ctx = _ctx()
    assert _passes_filter(_unit(might_counters=1), {"is_buffed": True}, ctx) is True
    assert _passes_filter(_unit(might_counters=0), {"is_buffed": True}, ctx) is False


def test_is_mighty():
    ctx = _ctx()
    assert _passes_filter(_unit(might=5), {"is_mighty": True}, ctx) is True
    assert _passes_filter(_unit(might=4), {"is_mighty": True}, ctx) is False


def test_might_less_than_self():
    src_card = UnitCard(name="Src", might=5)
    ctx = _ctx(source_card=src_card)
    # source must be on the board for _source_unit to find it
    ctx.battlefield.units_A.append(UnitInPlay(card=src_card))
    assert _passes_filter(_unit(might=3), {"might_less_than_self": True}, ctx) is True
    assert _passes_filter(_unit(might=5), {"might_less_than_self": True}, ctx) is False


def test_might_less_than_self_noop_without_source():
    # No source unit on the board (e.g. a spell) -> filter is a no-op, not exclude-all.
    ctx = _ctx()
    assert _passes_filter(_unit(might=3), {"might_less_than_self": True}, ctx) is True


def test_card_type():
    ctx = _ctx()
    assert _passes_filter(_unit(), {"card_type": "UNIT"}, ctx) is True
    assert _passes_filter(_unit(), {"card_type": "SPELL"}, ctx) is False


def test_is_legend_and_is_champion_exclude_plain_unit():
    ctx = _ctx()
    # A plain UNIT is neither a LEGEND nor a CHAMPION.
    assert _passes_filter(_unit(), {"is_legend": True}, ctx) is False
    assert _passes_filter(_unit(), {"is_champion": True}, ctx) is False
