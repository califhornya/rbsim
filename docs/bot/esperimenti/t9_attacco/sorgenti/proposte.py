"""Proposte di attacco ricavate dalle mosse legali e dal tavolo visibile al giocatore."""
import json
import re
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path

from ev import E, D, P, base, root, table


@dataclass(frozen=True)
class Proposal:
    gear_target: str
    waves: int
    spell_wave: int
    ambush_index: int


def proposals():
    for gear, waves, ambush in product(("none", "weak", "strong"), (1, 2), (0, 1)):
        for wave in range(1, waves + 1):
            yield Proposal(gear, waves, wave, ambush)


def indexed(menu, predicate):
    # Legally identical card copies are interchangeable in this probe.
    distinct = {}
    for i, entry in enumerate(menu):
        if predicate(entry):
            distinct.setdefault(entry, i)
    return list(distinct.items())


class Attack:
    def __init__(self, proposal, seat, field):
        self.p = proposal
        self.seat = seat
        self.field = field
        self.prepared = False
        self.wave = 0
        self.declaring = False
        self.used_spell = False
        self.used_ambush = False
        self.events = []

    def act(self, event):
        e = json.loads(event)
        kind = e["k"]
        if kind == "decision":
            menu = e["menu"]
            i = self.decision(e, menu)
            if menu[i] != "Pass":
                self.events.append([self.wave, e["point"], menu[i]])
            return i
        if kind == "choice":
            i = self.choice(e)
            self.events.append([self.wave, e["kind"], E.etichette_scelta(e)[i]])
            return i
        return {"decide_optional": True, "decide_mulligan": [],
                "decide_predict_recycle": False, "decide_mode": None}[kind]

    def decision(self, e, menu):
        skip = next(i for i, label in enumerate(menu) if label.startswith("Pass"))
        field = f"BF{self.field}"
        if e["point"] == "turn_action":
            if not self.prepared:
                self.prepared = True
                gear = indexed(menu, lambda s: s.startswith("Play gear ") and s.endswith("@" + field))
                if self.p.gear_target != "none" and gear:
                    return gear[0][1]
            moves = indexed(menu, lambda s: s.startswith("Move ") and s.endswith(" base→" + field))
            if self.declaring:
                if self.p.waves == 1 and moves:
                    return moves[0][1]
                self.declaring = False
                return skip
            if self.wave < self.p.waves and moves:
                view = D.riassunto(e["state_raw"], self.seat)
                force = dict(view["base"]["campione"]["unita"])
                self.wave += 1
                self.declaring = True
                return min(moves, key=lambda item: force[item[0][5:].rsplit(" base→", 1)[0]])[1]
            return skip
        if e["point"] == "showdown_action" and self.wave > 0:
            if self.wave == self.p.waves and not self.used_ambush:
                ambush = indexed(menu, lambda s: s.startswith("AMBUSH ") and s.endswith("@" + field))
                if ambush:
                    self.used_ambush = True
                    return ambush[min(self.p.ambush_index, len(ambush)-1)][1]
            if self.wave == self.p.spell_wave and not self.used_spell:
                spells = indexed(menu, lambda s: s.startswith("Showdown ") and s.endswith("@" + field))
                if spells:
                    self.used_spell = True
                    return spells[0][1]
        return skip

    def choice(self, e):
        k = e["kind"]
        labels = E.etichette_scelta(e)
        def subjects(seat):
            out = []
            for i, s in enumerate(labels):
                m = re.search(r"\(([AB]), Might (\d+), (.+)\)$", s)
                if m and m.group(1) == seat:
                    out.append((int(m.group(2)), i, m.group(3)))
            return out
        ours = subjects(self.seat)
        other = subjects("B" if self.seat == "A" else "A")
        if k == "target:buff_unit" and ours:
            return (min if self.p.gear_target == "weak" else max)(ours)[1]
        if k == "target:grant_temporary_might":
            here = [x for x in ours if x[2] != "base"]
            if here:
                return max(here)[1]
        if k == "target:stun_unit" and other:
            return max(other)[1]
        if k == "combat_damage_order" and other:
            # Prefer an affordable kill. Resolve a tie by the later legal slot.
            return min(other, key=lambda x: (x[0], -x[1]))[1]
        if k.startswith("optional:"):
            return next((i for i,s in enumerate(labels) if s.endswith(": sì")), e["default"])
        return e["default"]


def run():
    seat = P["camp"]
    other = "B" if seat == "A" else "A"
    game = E.gioco(P, root, base)
    view = D.riassunto(json.loads(game.raw_dump()), seat)
    fields = [f["campo"] for f in view["campi"] if f["controlla"] == "avversario"]
    results = []
    for field, proposal in product(fields, proposals()):
        game = E.gioco(P, root, base)
        E._agente_campione(game, P, other, 2*base + (other == "B") + 1_000_003)
        policy = Attack(proposal, seat, field)
        game.set_human_agent(seat, policy.act, False, None)
        game.set_side_chooser()
        game.run_actions_end()
        results.append({"field": field, "proposal": asdict(proposal), "events": policy.events,
                        "waves": policy.wave, "ambush": policy.used_ambush, "spell": policy.used_spell,
                        "state": table(game)})
    out = Path(__file__).with_name("proposte.json")
    out.write_text(json.dumps(results, ensure_ascii=False))
    print(len(results), "proposte", sum(r["ambush"] and r["spell"] for r in results),
          "usano sia ambush che magia")

if __name__ == "__main__":
    run()
