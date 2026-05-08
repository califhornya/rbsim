from pydantic import BaseModel, Field
from typing import Optional


class GameConfig(BaseModel):
    games: int = Field(default=1000, ge=1)
    seed: Optional[int] = 42
    record_draws: bool = False
