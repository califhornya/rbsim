"""The rules profile on the Python side (decisions of 25/11): the arena's
resume key, ppo.py's checks before launching, the provenance."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STORICHE, CORRETTE = "6427b90", "6427b90+D72-D76"


def _script(name: str, path: str):
    sys.path.insert(0, str(ROOT / "scripts/diag"))
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_historical_game_leaves_the_seed_to_play_on_the_new_profile(tmp_path):
    arena = _script("arena_mazzi_t", "scripts/diag/arena_mazzi.py")
    righe = tmp_path / "arena.jsonl"
    base = {"ckpt": "c.pt", "avversario": "a.pt", "starter": "a", "score": 1.0, "motore": "rust"}
    righe.write_text("\n".join(json.dumps(base | r) for r in [
        {"seed": 7, "seat": "A", "mu": "ES"},                         # before 25/11: no "regole"
        {"seed": 7, "seat": "B", "mu": "ES", "regole": STORICHE},
        {"seed": 8, "seat": "A", "mu": "ES", "regole": CORRETTE}]) + "\n")
    kw = dict(ckpt="c.pt", avversario="a.pt", budget_c=None, budget_a=None, motore={"ES": "rust"},
              sha_c=None, sha_a=None)
    old = arena.riprese(righe, regole={"ES": STORICHE}, **kw)
    new = arena.riprese(righe, regole={"ES": CORRETTE}, **kw)
    assert sorted((r[0], r[2]) for r in old) == [(7, "A"), (7, "B")]
    assert [(r[0], r[2]) for r in new] == [(8, "A")]         # seed 7 is still to play


def _ppo_args(run, regole, motore="rust", mazzi="ek"):
    return argparse.Namespace(regole=regole, motore=motore, mazzi=mazzi, run_dir=run)


class _Ap:
    def error(self, msg):
        raise SystemExit(msg)


def test_ppo_checks_the_profile_before_launching(tmp_path, monkeypatch):
    ppo = _script("ppo_t", "scripts/ppo.py")
    run = tmp_path / "run"
    run.mkdir()
    # A new folder: the corrected profile on Rust is fine, on Python not.
    monkeypatch.setenv("RBSIM_MOTORE", "rust")
    ppo._check_regole(_Ap(), _ppo_args(run, CORRETTE), run)
    monkeypatch.setenv("RBSIM_MOTORE", "python")
    with pytest.raises(SystemExit, match="devono giocare su Rust"):
        ppo._check_regole(_Ap(), _ppo_args(run, CORRETTE, motore="python"), run)
    # A run trained on the historical rules (provenance without "regole"):
    # not resumed on the corrected profile.
    (run / "stato.json").write_text("{}")
    (run / "provenienza.jsonl").write_text(json.dumps({"motore": {}}) + "\n")
    assert ppo._regole_run(run) == STORICHE
    monkeypatch.setenv("RBSIM_MOTORE", "rust")
    with pytest.raises(SystemExit, match="--init in una nuova cartella"):
        ppo._check_regole(_Ap(), _ppo_args(run, CORRETTE), run)
    ppo._check_regole(_Ap(), _ppo_args(run, STORICHE), run)


def test_the_provenance_says_the_rules_each_matchup_played(monkeypatch):
    from riftbound import provenienza as P
    monkeypatch.setenv("RBSIM_REGOLE", CORRETTE)
    assert P.regole_scelte() == CORRETTE
    assert P.regole_di("rust") == CORRETTE and P.regole_di("python") == STORICHE
    monkeypatch.setenv("RBSIM_REGOLE", "6427b90+D99")
    with pytest.raises(ValueError, match="regole sconosciute"):
        P.regole_scelte()
    monkeypatch.delenv("RBSIM_REGOLE")
    assert P.regole_scelte() == STORICHE
