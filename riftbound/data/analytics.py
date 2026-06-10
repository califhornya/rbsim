"""Utility helpers to aggregate simulation results from the SQLite database."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, TYPE_CHECKING, Any

try:  # pragma: no cover - optional dependency at runtime
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session
except ModuleNotFoundError:  # pragma: no cover - environment without SQLAlchemy
    func = select = None  # type: ignore[assignment]
    Session = Any  # type: ignore[assignment]
    _HAS_SQLALCHEMY = False
else:  # pragma: no cover - import success path exercised in tests when available
    _HAS_SQLALCHEMY = True

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session as SessionType
else:
    SessionType = Any

from riftbound.data.schema import Deck, Game, Play


@dataclass
class GameSummary:
    total_games: int
    wins_A: int
    wins_B: int
    draws: int
    avg_turns: float
    avg_units_played: float
    avg_spells_cast: float


@dataclass
class AISummary:
    ai_name: str
    games: int
    wins: int
    losses: int
    draws: int
    win_rate: float
    avg_turns: float


@dataclass
class CardUsage:
    card_name: str
    action: str
    plays: int


@dataclass
class AnalyticsReport:
    games: GameSummary
    ai_stats: List[AISummary]
    top_cards: List[CardUsage]


def summarize_session(session: "SessionType", *, top_cards: int = 10) -> AnalyticsReport:
    """Build an :class:`AnalyticsReport` from the provided SQLAlchemy session."""

    _require_sqlalchemy()
    games_summary = _summarize_games(session)
    ai_summary = _summarize_ai(session)
    cards_summary = _summarize_cards(session, limit=top_cards)
    return AnalyticsReport(games_summary, ai_summary, cards_summary)


def _summarize_games(session: "SessionType") -> GameSummary:
    total_games = session.execute(select(func.count(Game.id))).scalar_one()

    wins_A = session.execute(select(func.count()).where(Game.winner == "A")).scalar_one()
    wins_B = session.execute(select(func.count()).where(Game.winner == "B")).scalar_one()
    draws = session.execute(select(func.count()).where(Game.winner == "DRAW")).scalar_one()

    avg_turns = _scalar_avg(session, Game.turns)
    avg_units = _scalar_avg(session, Game.total_units_played)
    avg_spells = _scalar_avg(session, Game.total_spells_cast)

    return GameSummary(
        total_games=total_games,
        wins_A=wins_A,
        wins_B=wins_B,
        draws=draws,
        avg_turns=avg_turns,
        avg_units_played=avg_units,
        avg_spells_cast=avg_spells,
    )


def _summarize_ai(session: "SessionType") -> List[AISummary]:
    rows = session.execute(
        select(Deck.ai_name, Deck.player, Game.winner, Game.turns)
        .join(Game, Deck.game_id == Game.id)
        .where(Deck.ai_name.is_not(None))
    ).all()

    aggregates: dict[str, dict[str, float]] = {}
    for ai_name, player, winner, turns in rows:
        if not ai_name:
            continue
        bucket = aggregates.setdefault(
            ai_name,
            {"games": 0, "wins": 0, "losses": 0, "draws": 0, "turns": 0.0},
        )
        bucket["games"] += 1
        bucket["turns"] += float(turns or 0)

        if winner == "DRAW":
            bucket["draws"] += 1
        elif (player == "A" and winner == "A") or (player == "B" and winner == "B"):
            bucket["wins"] += 1
        else:
            bucket["losses"] += 1

    summaries: List[AISummary] = []
    for ai_name in sorted(aggregates):
        bucket = aggregates[ai_name]
        games = int(bucket["games"])
        wins = int(bucket["wins"])
        losses = int(bucket["losses"])
        draws = int(bucket["draws"])
        avg_turns = bucket["turns"] / games if games else 0.0
        win_rate = wins / games if games else 0.0
        summaries.append(
            AISummary(
                ai_name=ai_name,
                games=games,
                wins=wins,
                losses=losses,
                draws=draws,
                win_rate=win_rate,
                avg_turns=avg_turns,
            )
        )

    return summaries


def _summarize_cards(session: "SessionType", *, limit: int = 10) -> List[CardUsage]:
    if limit <= 0:
        return []

    stmt = (
        select(Play.card_name, Play.action, func.count())
        .where(Play.action.in_(["UNIT", "SPELL", "GEAR"]))
        .group_by(Play.card_name, Play.action)
        .order_by(func.count().desc(), Play.card_name.asc())
        .limit(limit)
    )
    rows = session.execute(stmt).all()

    return [CardUsage(card_name=row[0], action=row[1], plays=int(row[2])) for row in rows]


def _scalar_avg(session: "SessionType", column) -> float:
    value = session.execute(select(func.avg(column))).scalar_one()
    return float(value or 0.0)


def _require_sqlalchemy() -> None:
    if not _HAS_SQLALCHEMY:
        raise RuntimeError(
            "SQLAlchemy is required for analytics utilities. "
            "Install the 'sqlalchemy' package to use this module."
        )


__all__ = [
    "AISummary",
    "AnalyticsReport",
    "CardUsage",
    "GameSummary",
    "summarize_session",
]