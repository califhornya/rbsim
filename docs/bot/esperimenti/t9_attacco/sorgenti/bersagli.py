"""Diagnosi dopo la verifica, sullo stesso campione: bersagli e Armory."""
import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from ev import D, P, Turn, base, finish, start_tree
from selezione import Branch
from proposte import proposals


def observed(i):
    state = start_tree("ignote", base+i)
    indexed = list(proposals())
    assert indexed[16].gear_target == "strong" and indexed[16].spell_wave == 1
    arms = (("p16", Branch(indexed[16], P["camp"], 0)), ("buff_sett", Turn("buff_sett")))
    output = []
    for name, player in arms:
        ask = player.ask
        at_second = []

        def record(event):
            index = ask(event)
            e = json.loads(event)
            if e["k"] == "decision" and e["point"] == "turn_action" and e["menu"][index] == "Move Sett Kingpin base→BF0":
                enemy = D.riassunto(e["state_raw"], P["camp"])["campi"][0]["avversario"]["unita"]
                at_second.append([unit for unit, might in enemy])
            return index

        player.ask = record
        row = finish(state, name, i, "ignote", controller=player)
        assert len(at_second) == 1
        row["nemici_prima_di_Sett"] = at_second[0]
        output.append(row)
    return output


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    ctx = multiprocessing.get_context("spawn")
    with (folder/"bersagli.jsonl").open("w") as f, ProcessPoolExecutor(4, mp_context=ctx) as pool:
        for rows in pool.map(observed, range(4000,4100)):
            f.write(json.dumps(rows,ensure_ascii=False)+"\n")
            f.flush()
