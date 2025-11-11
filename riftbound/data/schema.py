from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

DB_VERSION = 2

Base = declarative_base()
victory_mode = Column(String(16), default="control")
points_A = Column(Integer, default=0)
points_B = Column(Integer, default=0)

class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, autoincrement=True)
    seed = Column(Integer, nullable=False)
    winner = Column(String(1), nullable=False)
    turns = Column(Integer, nullable=False)
    total_units_played = Column(Integer, default=0)
    total_spells_cast = Column(Integer, default=0)

    turns_rel = relationship("Turn", back_populates="game", cascade="all, delete")
    decks_rel = relationship("Deck", back_populates="game", cascade="all, delete")
    draws_rel = relationship("Draw", back_populates="game", cascade="all, delete")
    hands_rel = relationship("Hand", back_populates="game", cascade="all, delete")
    boards_rel = relationship("Board", back_populates="game", cascade="all, delete")
    plays_rel = relationship("Play", back_populates="game", cascade="all, delete")

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


class Deck(Base):
    __tablename__ = "decks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    player = Column(String(1), nullable=False)
    ai_name = Column(String(64))
    card_hash = Column(String(64), nullable=False)
    cards_json = Column(Text, nullable=False)

    game = relationship("Game", back_populates="decks_rel")


class Draw(Base):
    __tablename__ = "draws"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    player = Column(String(1), nullable=False)
    turn_number = Column(Integer, nullable=False)
    draw_index = Column(Integer, nullable=False)
    card_name = Column(String(64), nullable=False)
    card_uuid = Column(String(36), nullable=False)
    card_type = Column(String(16), nullable=False)
    source = Column(String(32), default="deck")

    game = relationship("Game", back_populates="draws_rel")


class Hand(Base):
    __tablename__ = "hands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    player = Column(String(1), nullable=False)
    turn_number = Column(Integer, nullable=False)
    cards_json = Column(Text, nullable=False)

    game = relationship("Game", back_populates="hands_rel")


class Board(Base):
    __tablename__ = "boards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    turn_number = Column(Integer, nullable=False)
    battlefield_index = Column(Integer, nullable=False)
    units_A = Column(Text, nullable=False)
    units_B = Column(Text, nullable=False)
    controller = Column(String(1))
    contested = Column(Boolean, default=False)
    points_A = Column(Integer, default=0)
    points_B = Column(Integer, default=0)

    game = relationship("Game", back_populates="boards_rel")


class Play(Base):
    __tablename__ = "plays"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    player = Column(String(1), nullable=False)
    turn_number = Column(Integer, nullable=False)
    battlefield_index = Column(Integer)
    action = Column(String(16), default="PLAY", nullable=False)
    card_name = Column(String(64), nullable=False)
    card_uuid = Column(String(36), nullable=False)
    card_type = Column(String(16), nullable=False)
    result = Column(String(32))

    game = relationship("Game", back_populates="plays_rel")


class AIStats(Base):
    __tablename__ = "ai_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ai_name = Column(String(64), unique=True, nullable=False)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    avg_turns = Column(Float, default=0.0)
