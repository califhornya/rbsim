"""Provenienza di una run (decisione del 24/11: Python congelato).

Ogni run di training o d'arena registra con che cosa è stata giocata:
- `regole`: il riferimento storico delle regole Python, fermo a 6427b90;
- `agente_ppo`: la versione dell'agente PPO (PPOAgent.inner col contesto
  `made` legato agli oggetti, fix f8a50e4);
- `revisione`: il commit del codice che gira e se ha modifiche locali;
- `registro`: le carte (hash dei file da cui il motore le legge);
- `liste`: i mazzi, identificati dal contenuto e non dal percorso;
- `motore`: quale motore ha giocato ciascun matchup;
- `checkpoint`: l'hash dei pesi usati.

Le liste si riconoscono dal contenuto (`lista_sha`): una copia dello stesso
mazzo in un altro file è lo stesso mazzo, un file con lo stesso nome e carte
diverse no.
"""
from __future__ import annotations

import functools
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]

REGOLE_PYTHON = "6427b90"
AGENTE_PPO = "f8a50e4"

_REGISTRO_PY = (ROOT / "riftbound/data/cards/all_cards.json", ROOT / "riftbound/registry/cards_registry.py")
_REGISTRO_RS = ROOT / "rust/data/registry.json"


def file_sha(path) -> Optional[str]:
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.is_file() else None


@functools.lru_cache(maxsize=None)
def _lista_sha(path: str, mtime: float) -> str:
    data = json.loads(Path(path).read_text())
    canon = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


def lista_sha(path) -> str:
    """L'hash del contenuto di una lista (JSON in forma canonica)."""
    p = Path(path).resolve()
    return _lista_sha(str(p), p.stat().st_mtime)


def stessa_lista(a, b) -> bool:
    return lista_sha(a) == lista_sha(b)


def revisione() -> dict:
    def git(*args) -> str:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
    try:
        commit = git("rev-parse", "HEAD")
        dirty = bool(git("status", "--porcelain", "--untracked-files=no"))
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "modifiche_locali": None}
    return {"commit": commit or None, "modifiche_locali": dirty}


def registro() -> dict:
    h = hashlib.sha256()
    for p in _REGISTRO_PY:
        h.update(p.read_bytes() if p.is_file() else b"")
    return {"python": h.hexdigest()[:16], "rust": file_sha(_REGISTRO_RS)}


def estensione_rust() -> Optional[str]:
    """L'hash del modulo riftbound_rs caricato (None se non c'è)."""
    try:
        import riftbound_rs
    except ImportError:
        return None
    return file_sha(riftbound_rs.__file__) if getattr(riftbound_rs, "__file__", None) else "?"


def provenienza(*, motore: dict, liste: dict, checkpoint: dict, **extra) -> dict:
    """`motore`: matchup -> "python" | "rust"; `liste`: lettera -> percorso;
    `checkpoint`: nome -> percorso (o None)."""
    return {
        "quando": time.strftime("%Y-%m-%d %H:%M:%S"),
        "regole": REGOLE_PYTHON,
        "agente_ppo": AGENTE_PPO,
        "revisione": revisione(),
        "registro": registro(),
        "estensione_rust": estensione_rust() if "rust" in motore.values() else None,
        "motore": dict(motore),
        "liste": {k: {"file": Path(p).name, "sha": lista_sha(p)} for k, p in liste.items()},
        "checkpoint": {k: (None if p is None else {"file": str(p), "sha": file_sha(p)})
                       for k, p in checkpoint.items()},
    } | extra


def registra(run_dir, riga: dict) -> None:
    """Aggiunge la riga a <run_dir>/provenienza.jsonl (una per lancio)."""
    with open(Path(run_dir) / "provenienza.jsonl", "a") as f:
        f.write(json.dumps(riga, ensure_ascii=False, default=str) + "\n")
