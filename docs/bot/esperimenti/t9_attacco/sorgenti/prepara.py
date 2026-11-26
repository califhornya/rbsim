"""Ricostruisce la posizione dalla partita salvata e ripete la traccia della ricerca."""
import argparse
import json
import pickle
from pathlib import Path

from riftbound.rs import decisione_esp as esperimenti, decisione_rs as decisioni


if __name__ == "__main__":
    replay = "docs/bot/partite/coach/20261126_013325_competitive_evelynn_vs_competitive_sett.json"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", default=replay)
    parser.add_argument("--ckpt", default="../rbsim/runs/sett/ekris_s12/ckpt_040000.pt")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    spec = {"tipo": "pagina", "file": args.replay, "ckpt": args.ckpt}
    profile, event = esperimenti.posizione(spec, 10)
    assert event["turn"] == 9 and profile["camp"] == "B" and profile["iterazioni"] == 138
    tree = esperimenti.albero(event["state_raw"])
    with (args.out / "position.pkl").open("wb") as fp:
        pickle.dump((profile, tree), fp)
    logs = {str(windows): decisioni.rifai(spec, 10, 138, posizione=False,
                                          finestre=windows, semi=True) for windows in (False, True)}
    quota = decisioni.rifai(spec, 10, 138, posizione=False, finestre=True, quota=([""], 4), semi=True)
    assert all(entry["prefisso_ok"] for entry in [*logs.values(), quota])
    assert logs["True"]["diagnosi"]["seeds"] == quota["diagnosi"]["seeds"]
    for filename, contents in (("radice.json", logs), ("quota4.json", quota)):
        (args.out / filename).write_text(json.dumps(contents), encoding="utf-8")
