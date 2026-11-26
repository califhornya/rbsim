"""Confronto a fine partita: selezione e verifica su mondi tenuti da parte."""
import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

from ev import D, E, P, Release, base, finish, start_tree
from proposte import Attack, proposals


class Branch(Attack):
    """Restituisce la posizione al campione alla prima azione libera dopo l'attacco."""
    def __init__(self, proposal, seat, field):
        super().__init__(proposal, seat, field)
        self.attack = None
        self.complete = False
        self.reason = None

    def ask(self, event):
        e = json.loads(event)
        if e["k"] == "decision" and e["point"] == "turn_action" and self.prepared and not self.declaring:
            target = f" base→BF{self.field}"
            can_move = any(s.startswith("Move ") and s.endswith(target) for s in e["menu"])
            if self.wave >= self.p.waves or not can_move:
                self.resumed = e["state_raw"]
                self.complete = self.wave >= self.p.waves
                self.reason = None if self.complete else "mossa non disponibile"
                raise Release()
        return self.act(event)


def score_one(args):
    i, keys = args
    mode = "ignote"
    st = start_tree(mode, base+i)
    state = json.loads(E.gioco(P, st, base+i).raw_dump())
    target = next(f["campo"] for f in D.riassunto(state, P["camp"])["campi"] if f["controlla"] == "avversario")
    opts = list(proposals())
    out = []
    for k in keys:
        c = None if k == -1 else Branch(opts[k], P["camp"], target)
        label = "valley" if c is None else f"p{k:02d}"
        r = finish(st, label, i, mode, controller=c)
        out.append(r)
    return out


def batch(path, indices, keys):
    totals = dict.fromkeys(keys, 0)
    ctx = multiprocessing.get_context("spawn")
    with path.open("w") as out, ProcessPoolExecutor(4, mp_context=ctx) as pool:
        for j, rs in enumerate(pool.map(score_one, ((i,keys) for i in indices)), 1):
            out.write(json.dumps(rs,ensure_ascii=False)+"\n")
            out.flush()
            for key,r in zip(keys,rs):
                totals[key] += r["returns"]
    return totals


if __name__ == "__main__":
    where = Path(__file__).resolve().parent
    options = list(proposals())
    keys = [-1, *range(len(options))]
    train = batch(where/"scelta.jsonl", range(2000,2016), keys)
    best = max(keys, key=train.get)
    print("SELEZIONE",train,"scelta",best, asdict(options[best]) if best!=-1 else "valley",flush=True)
    test_keys = [-1, best] if best != -1 else [-1]
    test = batch(where/"verifica.jsonl", range(4000,4100), test_keys)
    print("VERIFICA",test,flush=True)
