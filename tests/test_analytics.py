import pytest

pytest.importorskip("sqlalchemy")

from riftbound.core.cards import SpellCard, UnitCard
from riftbound.data.analytics import summarize_session
from riftbound.data.session import make_session
from riftbound.data.writer import record_deck, record_game, record_play


def _make_card_pool():
    return [UnitCard(name="Recruit", might=2), SpellCard(name="Bolt", damage=3)]


def test_analytics_summary_basic():
    session = make_session(":memory:")
    try:
        cards = _make_card_pool()
        game1 = record_game(session, seed=1, winner="A", turns=5, total_units=3, total_spells=1)
        record_deck(session, game1, "A", [cards[0]], ai_name="aggro")
        record_deck(session, game1, "B", [cards[1]], ai_name="control")
        record_play(session, game1, "A", 1, cards[0], action="UNIT", battlefield_index=0)
        record_play(session, game1, "A", 1, cards[1], action="SPELL", battlefield_index=0)

        game2 = record_game(session, seed=2, winner="B", turns=7, total_units=5, total_spells=2)
        record_deck(session, game2, "A", [cards[0]], ai_name="aggro")
        record_deck(session, game2, "B", [cards[1]], ai_name="control")
        record_play(session, game2, "B", 2, cards[1], action="SPELL", battlefield_index=0)

        session.commit()

        report = summarize_session(session, top_cards=5)

        assert report.games.total_games == 2
        assert report.games.wins_A == 1
        assert report.games.wins_B == 1
        assert report.games.draws == 0
        assert report.games.avg_turns == 6.0
        assert report.games.avg_units_played == 4.0
        assert report.games.avg_spells_cast == 1.5

        ai_stats = {stat.ai_name: stat for stat in report.ai_stats}
        assert ai_stats["aggro"].wins == 1
        assert ai_stats["aggro"].losses == 1
        assert ai_stats["aggro"].win_rate == 0.5
        assert ai_stats["control"].wins == 1
        assert ai_stats["control"].losses == 1

        assert report.top_cards[0].card_name == "Bolt"
        assert report.top_cards[0].plays == 2
    finally:
        session.close()