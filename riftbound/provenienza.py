"""Provenienza di una run (decisione del 24/11: Python congelato).

Ogni run di training o d'arena registra con che cosa è stata giocata:
- `regole`: il profilo delle regole scelto (`--regole`, RBSIM_REGOLE): lo
  storico 6427b90 (il motore Python congelato), 6427b90+D72-D76 (Rust con
  D72-D76 corretti), 6427b90+D72-D77 (come questo, con D77), 6427b90+D72-D80 (come questo, con D78-D80) 6427b90+D72-D81 (come questo, con D81) 6427b90+D72-D82 (come questo, con D82) o 6427b90+D72-D83 (come questo, con D83; docs/audit/AUDIT.md); `regole_partite` quello che gioca
  davvero ciascun matchup (su Python sempre lo storico);
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
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]

REGOLE_PYTHON = "6427b90"
REGOLE_D72_D76 = "6427b90+D72-D76"
REGOLE_D72_D77 = "6427b90+D72-D77"
REGOLE_D72_D80 = "6427b90+D72-D80"
REGOLE_D72_D81 = "6427b90+D72-D81"
REGOLE_D72_D82 = "6427b90+D72-D82"
REGOLE_D72_D83 = "6427b90+D72-D83"
REGOLE = (REGOLE_PYTHON, REGOLE_D72_D76, REGOLE_D72_D77, REGOLE_D72_D80, REGOLE_D72_D81, REGOLE_D72_D82, REGOLE_D72_D83)


def regole_scelte() -> str:
    """Il profilo delle regole di questo processo e dei suoi worker
    (RBSIM_REGOLE, impostato da --regole); di default lo storico."""
    r = os.environ.get("RBSIM_REGOLE") or REGOLE_PYTHON
    if r not in REGOLE:
        raise ValueError(f"regole sconosciute: {r!r} (note: {', '.join(REGOLE)})")
    return r


def regole_di(motore: str, regole: Optional[str] = None) -> str:
    """Le regole che gioca davvero una partita su `motore`: Python ha solo lo storico."""
    return (regole or regole_scelte()) if motore == "rust" else REGOLE_PYTHON
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


def registro(regole: Optional[str] = None) -> dict:
    """Gli hash dei file delle carte; col profilo corretto anche l'impronta
    del registro effettivo di Rust (la correzione dati applicata al caricamento)."""
    h = hashlib.sha256()
    for p in _REGISTRO_PY:
        h.update(p.read_bytes() if p.is_file() else b"")
    out = {"python": h.hexdigest()[:16], "rust": file_sha(_REGISTRO_RS)}
    if (regole or regole_scelte()) != REGOLE_PYTHON:
        try:
            from riftbound.rs.rust_bridge import registry
            reg = registry(regole)
            out |= {"rust_effettivo": reg.impronta, "correzione_dati": reg.correzione_dati}
        except ImportError:
            out |= {"rust_effettivo": None}
    return out


def estensione_rust() -> Optional[str]:
    """L'hash del modulo riftbound_rs caricato (None se non c'è)."""
    try:
        import riftbound_rs
    except ImportError:
        return None
    return file_sha(riftbound_rs.__file__) if getattr(riftbound_rs, "__file__", None) else "?"


def provenienza(*, motore: dict, liste: dict, checkpoint: dict, regole: Optional[str] = None,
                **extra) -> dict:
    """`motore`: matchup -> "python" | "rust"; `liste`: lettera -> percorso;
    `checkpoint`: nome -> percorso (o None); `regole`: il profilo (default
    quello del processo)."""
    regole = regole or regole_scelte()
    return {
        "quando": time.strftime("%Y-%m-%d %H:%M:%S"),
        "regole": regole,
        "regole_partite": {mu: regole_di(m, regole) for mu, m in motore.items()},
        "agente_ppo": AGENTE_PPO,
        "revisione": revisione(),
        "registro": registro(regole),
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
