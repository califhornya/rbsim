from pydantic import BaseModel, Field
from typing import Optional, List
from .enums import Domain

class GameConfig(BaseModel):
    games: int = Field(default=1000, ge=1)
    seed: Optional[int] = 42
    record_draws: bool = False

class GameResult(BaseModel):
    id: int
    winner: str
    turns: int
    score_a: int
    score_b: int

class DeckSpec(BaseModel):
    name: str
    legend: str
    domains: List[Domain]
