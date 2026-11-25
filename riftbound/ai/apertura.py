"""Le decisioni del campione nell'apertura di una partita 1v1 (come su RiftAtlas, 25/11):
il campo di battaglia fra i 3 del suo mazzo e, se vince il d20, chi comincia.

PROVVISORIO: la scelta ponderata arriva con la tabella misurata (parte 2).
Per ora: campo a caso fra i 3 (con l'rng dato), inizio = True (regola generale: chi comincia ha il
controllo). Le firme portano già i due mazzi (e i campi scelti) perché la tabella sia per matchup.
"""
from __future__ import annotations

import random
from typing import Sequence


def scegli_campo(mazzo_mio: str, mazzo_avv: str, campi_miei: Sequence[str], rng: random.Random) -> str:
    """Il campo del campione fra i suoi `campi_miei` (nomi). Provvisorio: a caso."""
    return rng.choice(list(campi_miei))


def scegli_inizio(mazzo_mio: str, mazzo_avv: str, campo_mio: str, campo_avv: str) -> bool:
    """Vinto il d20, se il campione comincia (True) o lascia cominciare l'avversario. Provvisorio: comincia."""
    return True
