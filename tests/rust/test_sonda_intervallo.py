"""Intervallo della differenza sonda - campione nel riepilogo fuori campione (riftbound/rs/sonda.py, Astra 27/11):
ricampionando le partite di origine dentro ogni matchup, non i singoli mondi."""
from __future__ import annotations

import pytest

pytest.importorskip("riftbound_rs")

from riftbound.rs import sonda  # noqa: E402


def _e(mu, partita, diff):
    return {"matchup": mu, "nome_partita": partita, "diff_mondi": diff, "partita": {}}


def test_media_delle_posizioni_con_gli_zeri():
    es = [_e("ES", "p1", [1.0, 0.0]), _e("ES", "p1", [0.0, 0.0]), _e("EK", "p2", [-0.5, -0.5])]
    m, lo, hi, n = sonda.intervallo_partite(es, n_boot=2000)
    assert m == pytest.approx((0.5 + 0.0 - 0.5) / 3)
    assert n == 2 and lo <= m <= hi


def test_le_partite_restano_intere():
    # due partite per matchup, ciascuna con molte posizioni uguali: l'intervallo deve essere largo come fra 2 partite,
    # non stretto come fra 40 posizioni indipendenti
    es = [_e("ES", "a", [1.0])] * 20 + [_e("ES", "b", [-1.0])] * 20
    m, lo, hi, n = sonda.intervallo_partite(es, n_boot=4000)
    assert m == pytest.approx(0.0) and n == 2
    assert lo <= -0.9 and hi >= 0.9


def test_deterministico_e_vuoto():
    es = [_e("ES", "a", [0.5, 0.0]), _e("ES", "b", [0.0, 0.0]), _e("KR", "c", [1.0, 1.0])]
    assert sonda.intervallo_partite(es, n_boot=1000) == sonda.intervallo_partite(es, n_boot=1000)
    assert sonda.intervallo_partite([]) is None
    assert sonda.intervallo_partite([_e("ES", "a", [])]) is None


def test_sonda_mac_usa_d83_per_le_partite_nuove():
    from pathlib import Path
    testo = (Path(__file__).resolve().parents[2] / "scripts/rust/sonda_mac.command").read_text()
    assert "--regole 6427b90+D72-D83" in testo and "D72-D82" not in testo
