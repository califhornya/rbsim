"""Le stesse partite in Rust sui due profili delle regole (decisione del 25/11):
6427b90 (lo storico, identico a Python) e 6427b90+D72-D76. Stessi semi, posti,
agenti; per ogni partita la prima differenza fra le due tracce (evento, campo,
dettaglio) e la sua spiegazione: le correzioni D72..D76 che sono scattate dalla
decisione precedente (contatori di Rust, ricerca compresa). Se menu e stato
coincidono e cambia solo la mossa scelta, la differenza nasce in una
simulazione della ricerca: lo dicono i contatori di quella decisione.

  python scripts/rust/confronto_regole.py --semi 1-20 --matchup ES --posti --agenti mano mano --iterazioni 50
  python scripts/rust/confronto_regole.py --semi 1-20 --matchup ES --posti --agenti simple_trade simple_trade
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/rust"))

STORICHE, CORRETTE = "6427b90", "6427b90+D72-D76"
CODICI = ("D72", "D73", "D74", "D75", "D76")


def semi(spec: str) -> list:
    a, _, b = spec.partition("-")
    return list(range(int(a), int(b or a) + 1))


def gioca(seed: int, mu: str, starter: str, agenti: tuple, iterazioni: int, regole: str):
    """(start, events, end, (winner, turns) | None, error) of one Rust game."""
    import riftbound_rs

    from riftbound.rs import rust_bridge as rb
    from riftbound.rs.mazzi import decks
    g = rb.build(seed, *decks(mu), starter, 40, regole=regole)
    for s, kind in zip("AB", agenti):
        if kind == "mano":
            g.set_search_agent(s, iterazioni, seed * 2 + (s == "B"), None, None, False)
        else:
            g.set_agent(s, kind, seed * 2 + (s == "B"))
    start = json.loads(g.raw_dump())
    g.trace_on()
    riftbound_rs.azzera_correzioni()
    err = None
    try:
        res = g.start()
    except RuntimeError as e:
        res, err = None, str(e)
    return start, json.loads(g.events()), json.loads(g.raw_dump()), res, err


def _delta(events: list, i: int) -> dict:
    """D72..D76 counted from the decision before raw event `i` to the decision
    at or after it (the corrected trace's snapshots)."""
    snaps = [(k, e["correzioni"]) for k, e in enumerate(events) if e["k"] == "decision" and "correzioni" in e]
    after = next((c for k, c in snaps if k >= i), snaps[-1][1] if snaps else [0] * 5)
    before = next((c for k, c in reversed(snaps) if k < i), [0] * 5)
    return {d: a - b for d, a, b in zip(CODICI, after, before) if a - b}


def confronta(seed: int, mu: str, agenti: tuple, iterazioni: int) -> dict:
    from diff_trace import canonical_rust_events, first_difference
    starter = "a" if seed % 2 == 0 else "b"
    s0, e0, f0, r0, err0 = gioca(seed, mu, starter, agenti, iterazioni, STORICHE)
    s1, e1, f1, r1, err1 = gioca(seed, mu, starter, agenti, iterazioni, CORRETTE)
    h, h_trees = canonical_rust_events(s0, e0, f0)
    c, c_trees = canonical_rust_events(s1, e1, f1)
    totali = [0] * 5
    snaps = [e["correzioni"] for e in e1 if e["k"] == "decision" and "correzioni" in e]
    if snaps:
        totali = snaps[-1]
    out = {"seed": seed, "matchup": mu, "starter": starter, "agenti": list(agenti),
           "storiche": list(r0) if r0 else err0, "corrette": list(r1) if r1 else err1,
           "correzioni": {d: n for d, n in zip(CODICI, totali) if n}}
    d = first_difference(h, c, h_trees, c_trees)
    if d is None:
        return out
    i, field, va, vb, detail = d
    raw_i = i - 1                                  # canonical_rust_events puts "start" first
    ev = c[i] if i < len(c) else {}
    diff = {"evento": i, "campo": field, "tipo": ev.get("k"), "seat": ev.get("seat"),
            "point": ev.get("point") or ev.get("kind"), "dettaglio": detail}
    if field == "menu":
        diff["solo_storiche"] = [m for m in va if m not in vb]
        diff["solo_corrette"] = [m for m in vb if m not in va]
    if field in ("action", "index"):
        diff["storiche"], diff["corrette"] = va, vb
    delta = _delta(e1, raw_i)
    diff["correzioni"] = delta
    if field in ("action", "index"):
        diff["origine"] = "ricerca" if delta else "?"
    elif field == "options":
        diff["origine"] = "partita (bersagli)"
    else:
        diff["origine"] = "partita"
    out["prima_differenza"] = diff
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semi", nargs="+", required=True)
    ap.add_argument("--matchup", default="ES")
    ap.add_argument("--posti", action="store_true", help="anche il matchup a posti scambiati")
    ap.add_argument("--agenti", nargs=2, default=["mano", "mano"])
    ap.add_argument("--iterazioni", type=int, default=50, help="il bot a mano a lavoro fisso")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    mus = [args.matchup] + ([args.matchup[::-1]] if args.posti else [])
    rows = []
    for mu in mus:
        for s in [x for spec in args.semi for x in semi(spec)]:
            rows.append(confronta(s, mu, tuple(args.agenti), args.iterazioni))
            r = rows[-1]
            d = r.get("prima_differenza")
            print(f"{mu} {s}: " + ("identiche" if d is None else
                  f"evento {d['evento']} ({d['tipo']} {d['seat']} {d['point']}), campo {d['campo']}, "
                  f"origine {d['origine']}, correzioni {d['correzioni']}"), flush=True)
    diverse = [r for r in rows if "prima_differenza" in r]
    cause = Counter(tuple(sorted(r["prima_differenza"]["correzioni"])) for r in diverse)
    print(f"\n{len(rows) - len(diverse)}/{len(rows)} partite identiche sui due profili; "
          f"prime differenze per correzioni scattate: "
          + ", ".join(f"{'+'.join(k) or 'nessuna'} {n}" for k, n in cause.most_common()))
    if args.out:
        args.out.write_text(json.dumps(rows, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
