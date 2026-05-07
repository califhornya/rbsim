from enum import Enum, auto

class Domain(Enum):
    FURY = "R"
    CALM = "G"
    MIND = "B"
    BODY = "O"
    CHAOS = "P"
    ORDER = "Y"

class CardType(Enum):
    UNIT = auto()
    GEAR = auto()
    SPELL = auto()
    RUNE = auto()
    LEGEND = auto()
    CHAMPION = auto()      # Champion supertype — starts in Champion Zone, plays as a Unit
    BATTLEFIELD = auto()

class Phase(Enum):
    AWAKEN = auto()
    BEGINNING = auto()
    DRAW = auto()
    ACTION = auto()
    COMBAT = auto()   # explicit combat phase (contested → 1-for-1 → control/Conquer)
    END = auto()
