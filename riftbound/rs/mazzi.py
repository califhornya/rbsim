"""Mazzi delle prove di parità Python / Rust.

Una lettera maiuscola è la lista di `collect.DECK_OF` (E, K, R, I, S), quella
del training e dell'arena. La stessa lettera minuscola è quella lista con
tutta la sideboard dentro: le carte di `FUORI` lasciano il posto alle carte
della sideboard (le partite di training non fanno sideboarding, così le carte
di sideboard entrano davvero in partita). La lista variata è un file in
`tests/rust/mazzi/`, scritto da `deck_path` e riconoscibile dal contenuto
(`provenienza.lista_sha`) come le altre.

  from riftbound.rs.mazzi import deck_path, decks
  deck_path("r")            # Rengar con la sideboard
  decks("Er")               # (Evelynn, Rengar con la sideboard)
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "tests/rust/mazzi"

# Per lista: le carte del mazzo che escono per far posto alla sideboard
# (quante ne entrano: la somma deve essere la stessa).
FUORI = {
    "R": {"Noxus Hopeful": 3, "Pit Rookie": 3, "First Mate": 2, "Irresistible Faefolk": 2},
    # Ivern: entrano Disarming Rake ×2, Janna Savior ×2, Vilemaw (unità) e Hush ×2, Salvage ×2,
    # Grand Strategem (magie); escono unità e magie di pari ruolo, almeno una copia di ciascuna resta.
    "I": {"Stalwart Poro": 2, "Mutated Mouser": 2, "Trusty Ramhound": 1,
          "Defy": 2, "Back Off": 1, "Friendship": 1, "Raucous Anthem": 1},
    # Sett: entrano solo magie (Decree of Strength, Decree of Unity, Repulse, Sabotage, Salvage, ×2);
    # escono magie (una copia di ciascuna resta) e due unità da 3 copie.
    "S": {"Call to Glory": 2, "Punch First": 2, "Rampage": 2, "Showstopper": 2, "Pit Rookie": 1, "First Mate": 1},
}


def with_sideboard(deck: dict, out: dict) -> dict:
    """La lista `deck` con la sideboard nel mazzo al posto delle carte `out`:
    l'ordine delle carte resta quello della lista, le carte nuove in fondo."""
    sb = {c["name"]: int(c["count"]) for c in deck.get("sideboard", [])}
    if sum(sb.values()) != sum(out.values()):
        raise ValueError(f"sideboard {sum(sb.values())} carte, ne escono {sum(out.values())}")
    cards = []
    for c in deck["cards"]:
        n = int(c["count"]) - out.get(c["name"], 0) + sb.pop(c["name"], 0)
        if n < 0:
            raise ValueError(f"{c['name']}: ne escono più di quante ce ne sono")
        if n:
            cards.append({"name": c["name"], "count": n})
    cards += [{"name": k, "count": v} for k, v in sb.items()]
    new = {k: v for k, v in deck.items() if k not in ("cards", "sideboard", "sideboard_plans")}
    new["name"] = f"{deck['name']} (sideboard)"
    new["cards"] = cards
    new["sideboard"] = []
    return new


def deck_path(code: str) -> Path:
    """Il file della lista `code` (una lettera: vedi il modulo)."""
    from riftbound.ai.ppo.collect import DECK_OF
    if code.isupper():
        return Path(DECK_OF[code])
    up = code.upper()
    base = json.loads(Path(DECK_OF[up]).read_text())
    text = json.dumps(with_sideboard(base, FUORI[up]), indent=1, ensure_ascii=False) + "\n"
    path = OUT_DIR / f"{Path(DECK_OF[up]).stem}_sideboard.json"
    if not path.exists() or path.read_text() != text:
        import os
        import tempfile
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")      # atomic: processes in parallel
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp, path)
    return path


def decks(matchup: str) -> tuple[Path, Path]:
    """(lista in A, lista in B) di un matchup come "ER" o "Er"."""
    return deck_path(matchup[0]), deck_path(matchup[1])
