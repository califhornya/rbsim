#!/usr/bin/env python
"""Switcheroo nel motore (23/11, domanda 1 di Astra sulla partita 35.010):
"Swap the Might of two units at the same battlefield this turn." (SFD-145,
HIDDEN, ACTION). Ogni caso: un tavolo costruito, che cosa il motore offre,
che cosa chiede, le Might dopo, e che cosa dicono testo e regole.

  python scripts/diag/switcheroo_casi.py      # sul codice di questa copia

Regole: §355.7-355.10 (le due unità sono bersagli; "at the same battlefield"
è una restrizione del gruppo, §355.11); §355.8 (senza bersagli validi la
spell non si gioca); §811.1.d.2 (da coperto, i bersagli al campo dove era
nascosta); §809.1.c (DEFLECT: chi sceglie paga [rune] in più, se non può
non sceglie).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/audit"))

from audit_helpers import act, card, choices, hide, labels, setup, unit  # noqa: E402
from riftbound.core.enums import Domain  # noqa: E402


def _name(o):
    if hasattr(o, "units_A"):
        return "campo[" + ",".join(u.card.name for u in o.units_A + o.units_B) + "]"
    return getattr(getattr(o, "card", None), "name", o)


def caso(title, rule, build, pick_bf=None, pick=(), hidden_lane=None, power=None):
    loop, a, b = setup(active="A", rich=("B",) if power is not None else ("A", "B"))
    if power is not None:
        a.energy = 4
        a.add_power(Domain.CHAOS, power)
    units = build(loop)
    loop._recompute_passives()
    if hidden_lane is None:
        a.hand.append(card("Switcheroo"))
    else:
        hide(loop, "A", hidden_lane, "Switcheroo")
    picks = {}
    if pick_bf is not None:
        picks["battlefield"] = lambda _l, opts: pick_bf
    if pick:
        def pt(_l, opts):
            names = [u.card.name for u in opts]
            return next((names.index(w) for w in pick if w in names), 0)
        picks["target"] = pt
    seen = choices(loop, picks)
    offers = [l for l in labels(loop, "A") if "Switcheroo" in l and not l.startswith("Hide")]
    before = {k: u.might for k, u in units.items()}
    p0 = sum((a.power_pool or {}).values())
    if offers:
        act(loop, "A", offers[0])
    after = {k: u.might for k, u in units.items()}
    print(f"\n{title}\n  testo/regole: {rule}\n  offerto: {offers or 'no'}")
    print(f"  scelte chieste: {[(k.split(':')[0] + (':altra' if k.endswith('other') else ''), [_name(o) for o in opts]) for k, s, opts in seen] or 'nessuna'}")
    print(f"  Might prima {before}\n        dopo  {after}" + (f"\n  potere {p0} -> {sum((a.power_pool or {}).values())}"
                                                             if power is not None else ""))


def at(loop, lane, side, name, might=None, **kw):
    u = unit(name, might, **kw)
    loop.gs.battlefields[lane].add_unit(side, u)
    return u


def replay_board(loop):
    """Il tavolo dello showdown della partita 35.010 (unità e Might come nel
    replay; il resto no): BF0 Bandle, BF1 Valley."""
    vex = at(loop, 0, "A", "Vex Apathetic")
    fae = at(loop, 0, "B", "Irresistible Faefolk")
    fiora = at(loop, 0, "B", "Fiora Victorious")
    fiora.temporary_might += 2                      # 6: MIGHTY (DEFLECT, GANKING, SHIELD)
    ev = at(loop, 1, "A", "Evelynn Entrancing")
    pyke = at(loop, 1, "A", "Pyke Returned")
    return {"Vex": vex, "Faefolk": fae, "Fiora": fiora, "Evelynn": ev, "Pyke": pyke}


def main() -> None:
    caso("1. Due unità amiche sullo stesso campo, nessuna nemica",
         "scambio valido (due unità allo stesso campo)",
         lambda l: {"amica2": at(l, 0, "A", "a2", 2), "amica5": at(l, 0, "A", "a5", 5)})
    caso("2. Amica 5 contro nemica 2",
         "scambio valido",
         lambda l: {"amica5": at(l, 0, "A", "a5", 5), "nemica2": at(l, 0, "B", "n2", 2)})
    caso("3. Due nemiche, una 5 con 3 danni",
         "scambio valido: a 1 Might con 3 danni muore",
         lambda l: {"nemica5_3danni": at(l, 0, "B", "n5", 5, damage=3), "nemica1": at(l, 0, "B", "n1", 1)})
    caso("4. Nessun campo con due unità",
         "§355.8: non si può giocare",
         lambda l: {"amica3@BF0": at(l, 0, "A", "a3", 3), "nemica3@BF1": at(l, 1, "B", "n3", 3)})
    caso("5. Tavolo del replay, Valley scelta (come la rete)",
         "valido: Evelynn e Pyke sono allo stesso campo", replay_board, pick_bf=1)
    caso("6. Tavolo del replay, Bandle: Vex con Fiora (DEFLECT), potere solo per Switcheroo",
         "§809.1.c: Fiora costa [rune] in più; senza, non si può scegliere",
         replay_board, pick_bf=0, pick=("Vex Apathetic", "Fiora Victorious"), power=2)
    caso("7. Come 6, con un potere in più",
         "Fiora scelta, la tassa pagata",
         replay_board, pick_bf=0, pick=("Vex Apathetic", "Fiora Victorious"), power=3)
    caso("8. Da coperto a Bandle, scelta Valley",
         "§811.1.d.2: i bersagli a Bandle, dove era nascosta",
         replay_board, pick_bf=1, hidden_lane=0)


if __name__ == "__main__":
    main()
