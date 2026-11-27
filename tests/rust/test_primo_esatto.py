"""Prima mossa forzata (`set_search_first_move`, `A.linea_primo`): l'etichetta identica vince sulla voce che la contiene.
Posizione: ES, seme 7, k=1, menu con "Play Rengar Trophy Hunter" e "Play Rengar Trophy Hunter to BF1" (ripetute).
Una scansione di 40 partite a pesi casuali non ha trovato un menu con la voce lunga PRIMA di quella corta (il motore
elenca prima la corta): il caso che distingue identica da contiene non si costruisce dal gioco; qui si controlla che
l'etichetta giocata sia sempre esattamente quella chiesta, e che senza voce identica valga ancora il "contiene"."""
from __future__ import annotations

import pytest

pytest.importorskip("torch")

from riftbound.rs import attacco as A  # noqa: E402
from riftbound.rs import decisione_rs as D  # noqa: E402

PARTITA = D.autonoma("ES", 7, None, True, 6, "A", valutazione=("rimonta", 3.0, 0.2), entrambi=True)
K = 1
CORTA = "Play Rengar Trophy Hunter"


@pytest.fixture(scope="module")
def pos():
    return A.posizione(PARTITA, K)


def _gioca(pos, etichetta):
    st = A.mondo(pos, "ignote", pos["base"])
    return A.continua(pos, st, A.linea_primo("p", etichetta), 0, "ignote")


def test_gioca_la_voce_identica_e_non_quella_piu_lunga(pos):
    r = _gioca(pos, CORTA)
    assert r["primo_ok"] and r["primo_giocata"] == CORTA


def test_etichette_esatte_giocate(pos):
    for lab in [x for x in pos["menu"] if x != "Pass"][:3]:
        r = _gioca(pos, lab)
        assert r["primo_giocata"] == lab and r["primo_ok"], lab


def test_senza_voce_identica_cade_sul_contiene(pos):
    r = _gioca(pos, "rengar trophy hunter to bf")      # nessuna identica: la prima che lo contiene
    assert r["primo_giocata"].startswith("Play Rengar Trophy Hunter to BF") and not r["primo_ok"]
