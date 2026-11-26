"""Riassunto dei confronti per mondo: vittorie, campo e differenze appaiate."""
import argparse
import json
from math import sqrt
from pathlib import Path
from statistics import mean, stdev


def rows(directory, filename, expected):
    data = [json.loads(line) for line in (directory / filename).read_text().splitlines()]
    assert len(data) == len(expected)
    assert [row[0]["world"] for row in data] == list(expected)
    order = [arm["line"] for arm in data[0]]
    for row in data:
        assert [arm["line"] for arm in row] == order
        assert len({(arm["world"], arm["face"]) for arm in row}) == 1
        assert all(arm["winner"] in ("A", "B", "DRAW") for arm in row)
    return data


def compare(data):
    result = {}
    for arm in zip(*data):
        delta = [a["returns"]-same[0]["returns"] for a,same in zip(arm,data)]
        avg = mean(delta)
        margin = 1.96 * stdev(delta) / sqrt(len(delta))
        result[arm[0]["line"]] = {
            "n": len(arm), "punti_partita": sum(a["returns"] for a in arm),
            "vittorie_Sett": sum(a["winner"] == "B" for a in arm),
            "patte": sum(a["winner"] == "DRAW" for a in arm),
            "delta_pp": round(100 * avg, 1),
            "intervallo_95_pp": [round(100 * (avg-margin), 1), round(100 * (avg+margin), 1)],
            "vince_solo_variante": sum(v > 0 for v in delta),
            "vince_solo_riferimento": sum(v < 0 for v in delta),
            "controllo_Bandle_Sett": sum(a["t9"]["fields"][0] == "campione" for a in arm),
            "controllo_Bandle_Evelynn": sum(a["t9"]["fields"][0] == "avversario" for a in arm),
            "resta_solo_Pyke": sum(a["t9"]["theirs"] == ["Pyke Returned"] for a in arm),
            "prefisso_completo": sum(a["prefix_ok"] for a in arm),
        }
    return result



def targets(directory):
    data = rows(directory, "bersagli.jsonl", range(4000, 4100))
    hold = rows(directory, "verifica.jsonl", range(4000, 4100))
    paired = [[earlier[0], *again] for earlier, again in zip(hold, data)]
    assert all(len({(a["face"], a["world"]) for a in s}) == 1 for s in paired)
    comparisons = compare(paired)
    for arm in zip(*data):
        summary = comparisons[arm[0]["line"]]
        summary["Vex_assente_prima_di_Sett"] = sum("Vex Apathetic" not in a["nemici_prima_di_Sett"] for a in arm)
    return comparisons


def summary(directory):
    selected = rows(directory, "scelta.jsonl", range(2000, 2016))
    ranked = {arm[0]["line"]: sum(r["returns"] for r in arm) for arm in zip(*selected)}
    best = max(ranked, key=ranked.get)
    held = rows(directory, "verifica.jsonl", range(4000, 4100))
    assert [r["line"] for r in held[0]] == (["valley",best] if best != "valley" else ["valley"])
    return {
        "carte_del_replay": compare(rows(directory, "fisse_0_100.jsonl", range(100))),
        "carte_ignote_a_Sett": compare(rows(directory, "ignote_0_100.jsonl", range(100))),
        "selezione_16_mondi": ranked, "selezionata": best,
        "verifica_100_nuovi_mondi": compare(held),
        "diagnosi_bersagli_stessi_100_mondi": targets(directory),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    print(json.dumps(summary(parser.parse_args().directory), indent=2, ensure_ascii=False))
