from sqlalchemy.orm import Session
from riftbound.data.schema import Game, Turn

def record_game(session: Session, seed: int, winner: str, turns: int,
                 total_units: int, total_spells: int) -> int:
    g = Game(
        seed=seed,
        winner=winner,
        turns=turns,
        total_units_played=total_units,
        total_spells_cast=total_spells,
    )
    session.add(g)
    session.commit()
    return g.id

def record_turn(session: Session, game_id: int, turn_no: int, active: str,
                units_A: int, units_B: int, hp_A: int, hp_B: int):
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
