from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from riftbound.data.schema import Board, Deck, Draw, Game, Hand, Play, Turn


def _card_to_dict(card) -> dict:
    """Serialize a card-like object into primitives for JSON storage."""

    name = getattr(card, "name", "")
    category = getattr(getattr(card, "category", None), "name", None)
    cost_energy = getattr(card, "cost_energy", None)
    cost_power = getattr(getattr(card, "cost_power", None), "name", None)
    domain = getattr(getattr(card, "domain", None), "name", None)
    keywords = list(getattr(card, "keywords", []) or [])
    tags = list(getattr(card, "tags", []) or [])
    might = getattr(card, "might", None)
    uuid = getattr(card, "uuid", None)

    return {
        "name": name,
        "category": category,
        "cost_energy": cost_energy,
        "cost_power": cost_power,
        "domain": domain,
        "keywords": keywords,
        "tags": tags,
        "might": might,
        "uuid": uuid,
    }


def _unit_to_dict(unit) -> dict:
    card_dict = _card_to_dict(getattr(unit, "card", None))
    return {
        "card": card_dict,
        "damage": getattr(unit, "damage", 0),
        "ready": getattr(unit, "ready", False),
    }


def _serialize_cards(cards: Iterable) -> str:
    payload = [_card_to_dict(card) for card in cards]
    return json.dumps(payload)


def _serialize_units(units: Iterable) -> str:
    payload = [_unit_to_dict(unit) for unit in units]
    return json.dumps(payload)


def _deck_hash(cards: Iterable) -> str:
    buffer = "|".join(getattr(card, "name", "") for card in cards)
    return hashlib.sha1(buffer.encode("utf-8")).hexdigest()


def record_game(
    session: Session,
    seed: int,
    winner: str,
    turns: int,
    total_units: int,
    total_spells: int,
    *,
    game_id: Optional[int] = None,
) -> int:
    if game_id is None:
        g = Game(
            seed=seed,
            winner=winner,
            turns=turns,
            total_units_played=total_units,
            total_spells_cast=total_spells,
        )
        session.add(g)
        session.flush()
        return g.id

    game = session.get(Game, game_id)
    if game is None:
        raise ValueError(f"Unknown game id {game_id}")

    game.seed = seed
    game.winner = winner
    game.turns = turns
    game.total_units_played = total_units
    game.total_spells_cast = total_spells
    session.flush()
    return game.id


def record_turn(
    session: Session,
    game_id: int,
    turn_no: int,
    active: str,
    units_A: int,
    units_B: int,
    hp_A: int,
    hp_B: int,
) -> None:
    t = Turn(
        game_id=game_id,
        turn_number=turn_no,
        active_player=active,
        units_A=units_A,
        units_B=units_B,
        hp_A=hp_A,
        hp_B=hp_B,
    )
    session.add(t)


def record_deck(
    session: Session,
    game_id: int,
    player: str,
    cards: Iterable,
    ai_name: Optional[str] = None,
) -> int:
    deck = Deck(
        game_id=game_id,
        player=player,
        ai_name=ai_name,
        card_hash=_deck_hash(cards),
        cards_json=_serialize_cards(cards),
    )
    session.add(deck)
    session.flush()
    return deck.id


def record_draw(
    session: Session,
    game_id: int,
    player: str,
    turn_number: int,
    draw_index: int,
    card,
    *,
    source: str = "deck",
) -> int:
    payload = _card_to_dict(card)
    entry = Draw(
        game_id=game_id,
        player=player,
        turn_number=turn_number,
        draw_index=draw_index,
        card_name=payload["name"],
        card_uuid=payload["uuid"] or "",
        card_type=payload["category"] or "UNKNOWN",
        source=source,
    )
    session.add(entry)
    session.flush()
    return entry.id


def record_hand(
    session: Session,
    game_id: int,
    player: str,
    turn_number: int,
    cards: Iterable,
) -> int:
    entry = Hand(
        game_id=game_id,
        player=player,
        turn_number=turn_number,
        cards_json=_serialize_cards(cards),
    )
    session.add(entry)
    session.flush()
    return entry.id


def record_board(
    session: Session,
    game_id: int,
    turn_number: int,
    battlefield_index: int,
    units_a: Iterable,
    units_b: Iterable,
    *,
    controller: Optional[str] = None,
    contested: bool = False,
    points_a: int = 0,
    points_b: int = 0,
) -> int:
    entry = Board(
        game_id=game_id,
        turn_number=turn_number,
        battlefield_index=battlefield_index,
        units_A=_serialize_units(units_a),
        units_B=_serialize_units(units_b),
        controller=controller,
        contested=contested,
        points_A=points_a,
        points_B=points_b,
    )
    session.add(entry)
    session.flush()
    return entry.id


def record_play(
    session: Session,
    game_id: int,
    player: str,
    turn_number: int,
    card,
    *,
    action: str,
    battlefield_index: Optional[int] = None,
    result: Optional[str] = None,
) -> int:
    payload = _card_to_dict(card)
    entry = Play(
        game_id=game_id,
        player=player,
        turn_number=turn_number,
        battlefield_index=battlefield_index,
        action=action,
        card_name=payload["name"],
        card_uuid=payload["uuid"] or "",
        card_type=payload["category"] or "UNKNOWN",
        result=result,
    )
    session.add(entry)
    session.flush()
    return entry.id


class GameRecorder:
    """Helper bound to a DB session to persist per-game analytics."""

    def __init__(self, session: Session, game_id: int):
        self.session = session
        self.game_id = game_id
        self._draw_counters = defaultdict(int)

    def record_deck(self, player: str, cards: Iterable, ai_name: Optional[str] = None) -> int:
        return record_deck(self.session, self.game_id, player, cards, ai_name)

    def record_draw(
        self,
        player: str,
        turn_number: int,
        card,
        *,
        source: str = "deck",
    ) -> int:
        self._draw_counters[player] += 1
        return record_draw(
            self.session,
            self.game_id,
            player,
            turn_number,
            self._draw_counters[player],
            card,
            source=source,
        )

    def record_hand(self, player: str, turn_number: int, cards: Iterable) -> int:
        return record_hand(self.session, self.game_id, player, turn_number, cards)

    def record_board(
        self,
        turn_number: int,
        battlefield_index: int,
        units_a: Iterable,
        units_b: Iterable,
        *,
        controller: Optional[str] = None,
        contested: bool = False,
        points_a: int = 0,
        points_b: int = 0,
    ) -> int:
        return record_board(
            self.session,
            self.game_id,
            turn_number,
            battlefield_index,
            units_a,
            units_b,
            controller=controller,
            contested=contested,
            points_a=points_a,
            points_b=points_b,
        )

    def record_play(
        self,
        player: str,
        turn_number: int,
        card,
        *,
        action: str,
        battlefield_index: Optional[int] = None,
        result: Optional[str] = None,
    ) -> int:
        return record_play(
            self.session,
            self.game_id,
            player,
            turn_number,
            card,
            action=action,
            battlefield_index=battlefield_index,
            result=result,
        )
