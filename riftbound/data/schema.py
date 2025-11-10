from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, autoincrement=True)
    seed = Column(Integer, nullable=False)
    winner = Column(String(1), nullable=False)
    turns = Column(Integer, nullable=False)
    total_units_played = Column(Integer, default=0)
    total_spells_cast = Column(Integer, default=0)

    turns_rel = relationship("Turn", back_populates="game", cascade="all, delete")

class Turn(Base):
    __tablename__ = "turns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id"))
    turn_number = Column(Integer, nullable=False)
    active_player = Column(String(1))
    units_A = Column(Integer)
    units_B = Column(Integer)
    hp_A = Column(Integer)
    hp_B = Column(Integer)

    game = relationship("Game", back_populates="turns_rel")
