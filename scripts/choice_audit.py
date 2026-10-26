#!/usr/bin/env python
"""Choice audit: how the engine's fixed choices hold up in self-play.

The rules give players many choices inside effects, costs and combat (a target,
a mode, a "you may", the unit an Equipment goes on, which enemy combat damage
kills first, how many buffs to spend...). The engine makes them with fixed
baseline policies, and every such pick goes through `GameLoop.choose`. This
script attaches a chooser to it and:

1. **survey**: plays games between random legal decks built from the whole card
   pool (the repo decks are outdated) and counts each kind of choice: how often
   it comes up, and how often there was more than one option.
2. **regret**: for a sample of real choices (more than one option), replays the
   game up to that choice, forces each other option, reshuffles both decks (the
   hidden cards) and plays on, many times, paired with the baseline's pick.
   Stage 1 finds the best alternative, stage 2 measures it against the
   baseline on fresh reshuffles, so the gain is not inflated by picking the
   luckiest alternative. A kind of choice with a large gain is one the baseline
   gets wrong in ways that cost games.

Both seats play the same agent (`simple_trade` by default) in all games, and the
gain is measured with that agent's play after the choice: a weak player can
under-rate a choice whose payoff needs good follow-up.

Usage:
  uv run python scripts/choice_audit.py                         # writes CHOICE_AUDIT.md
  uv run python scripts/choice_audit.py --games 500 --events 200 --out /tmp/a.md
"""
from __future__ import annotations

import _thread
import json
import os
import random
import subprocess
import sys
import tempfile
import threading
import traceback
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass
from multiprocessing import Pool
from pathlib import Path
from statistics import mean

import typer

ROOT = Path(__file__).resolve().parents[1]

app = typer.Typer(add_completion=False)

PLAYABLE = {"Unit", "Spell", "Gear", "Champion", "Signature Spell", "Signature Gear", "Signature Unit"}


# ---------------------------------------------------------------------------
# Decks

def random_decks(n: int, seed: int, out: Path) -> list[Path]:
    """`n` random legal decks over the whole card pool: a two-domain legend, a
    champion of its tag, 39 cards of its domains (its signature cards included,
    3 copies at most), 12 runes split between the domains, 3 battlefields."""
    from riftbound.registry.cards_registry import BANNED_CARDS, CARD_REGISTRY
    cards = json.loads((ROOT / "riftbound/data/cards/all_cards.json").read_text(encoding="utf-8"))

    def tags(c):
        return {t.strip() for t in (c.get("sub_type") or "").split(",") if t.strip()}

    legends = [c for c in cards if c["category"] == "Legend" and c["name"] in CARD_REGISTRY
               and len((c["domain"] or "").split()) == 2]
    bfs = sorted(c["name"] for c in cards if c["category"] == "Battlefield" and c["name"] in CARD_REGISTRY)
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(n):
        legend = rng.choice(legends)
        doms = legend["domain"].split()
        pool, champs = set(), []
        for c in cards:
            if c["category"] not in PLAYABLE or c["name"] not in CARD_REGISTRY or c["name"] in BANNED_CARDS:
                continue
            if not set((c["domain"] or "").split() or ["-"]) <= set(doms):
                continue
            if c["category"].startswith("Signature") and legend["sub_type"] not in tags(c):
                continue
            if c["category"] == "Champion" and legend["sub_type"] in tags(c):
                champs.append(c["name"])
            pool.add(c["name"])
        champion = rng.choice(sorted(champs)) if champs else None
        names = sorted(pool - {champion})
        counts: Counter = Counter()
        while sum(counts.values()) < 39:
            name = rng.choice(names)
            if counts[name] < 3:
                counts[name] += 1
        split = rng.randint(4, 8)
        deck = {
            "name": f"random {legend['name']} {i}",
            "legend": legend["name"],
            "champion": champion,
            "runes": [{"domain": doms[0].upper(), "count": split},
                      {"domain": doms[1].upper(), "count": 12 - split}],
            "battlefields": [{"name": b} for b in rng.sample(bfs, 3)],
            "cards": [{"name": k, "count": v} for k, v in sorted(counts.items())],
        }
        path = out / f"deck_{i:03d}.json"
        path.write_text(json.dumps(deck, indent=2, ensure_ascii=False), encoding="utf-8")
        paths.append(path)
    return paths


# ---------------------------------------------------------------------------
# Playing with a chooser

@dataclass
class Event:
    kind: str
    side: str
    source: str
    n: int
    default: int
    turn: int
    flags: tuple = ()


class Audit:
    """The chooser: records every choice; `force=(k, j)` takes option j at the
    k-th choice and asks for the hidden cards to be reshuffled right after."""

    def __init__(self, force=None):
        self.events: list[Event] = []
        self.force = force
        self.resample = False
        self.options: list[str] = []      # the forced choice's options, described

    def __call__(self, loop, kind, side, options, default, source):
        k = len(self.events)
        self.events.append(Event(kind, side, getattr(source, "name", "") or "", len(options),
                                 default, loop.gs.turn, _flags(loop, side, options, default)))
        if self.force is not None and k == self.force[0]:
            self.resample = True
            self.options = [_describe(loop, side, o) for o in options]
            return self.force[1]
        return None


def _describe(loop, side, option) -> str:
    """A short label for an option: a unit (whose, Might, where), a card (cost,
    type), a battlefield, a mode / yes-no."""
    from riftbound.core.battlefield import Battlefield
    from riftbound.core.combat import UnitInPlay
    if isinstance(option, tuple) and option and isinstance(option[-1], UnitInPlay):
        option = option[-1]                    # (side, unit) in effect moves
    if isinstance(option, UnitInPlay):
        where = loop._locate_unit(option)
        whose = "mine" if where and where[0] == side else "theirs"
        at = "base" if where and where[1] is None else "bf"
        return f"{whose} {option.card.name} ({option.might}, {at}{', token' if option.is_token else ''})"
    if isinstance(option, Battlefield):
        return f"battlefield {loop.gs.battlefields.index(option)}"
    if hasattr(option, "cost_energy"):
        cat = getattr(getattr(option, "category", None), "name", "?")
        return f"{option.name} ({cat.lower()}, {option.cost_energy or 0} energy)"
    if isinstance(option, tuple):
        return str(getattr(option[0], "name", option[0]))
    return str(getattr(option, "name", option))


def _flags(loop, side, options, default) -> tuple:
    """For a choice among units: whether the baseline took a friendly unit, an
    enemy one, and whether it was the mightiest / weakest of its side."""
    from riftbound.core.combat import UnitInPlay
    if not options or not isinstance(options[0], UnitInPlay):
        return ()
    where = loop._locate_unit(options[default])
    mine = where is not None and where[0] == side
    same = [u for u in options if (loc := loop._locate_unit(u)) is not None and (loc[0] == side) == mine]
    pick = options[default]
    out = ["friendly" if mine else "enemy"]
    if any(u.might > pick.might for u in same):
        out.append("not_mightiest")
    if any(u.might < pick.might for u in same):
        out.append("not_weakest")
    has_enemy = any((loc := loop._locate_unit(u)) is not None and loc[0] != side for u in options)
    has_friend = any((loc := loop._locate_unit(u)) is not None and loc[0] == side for u in options)
    if mine and has_enemy:
        out.append("enemy_available")
    if not mine and has_friend:
        out.append("friendly_available")
    return tuple(out)


def _agent(name: str, player, game: int):
    from riftbound.ai.heuristics.simple_trade_agent import SimpleTradeAgent
    from riftbound.ai.search.random_agent import RandomAgent
    if name == "random":
        return RandomAgent(player, random.Random(game * 2 + (player.name == "B")))
    return SimpleTradeAgent(player)


def _resample(gs, seed: int) -> None:
    """New hidden information: both Main Decks and rune decks reshuffled, the
    game's and the agents' random numbers reseeded."""
    r = random.Random(seed)
    for p in (gs.A, gs.B):
        r.shuffle(p.deck.cards)
        r.shuffle(p.rune_deck.runes)
        if hasattr(p.agent, "rng"):
            p.agent.rng.seed(r.randrange(1 << 30))
    gs.rng.seed(r.randrange(1 << 30))


def _hook(agent, audit: Audit, gs, seed) -> None:
    """Reshuffle at the first top-level decision after a forced choice (never
    in the middle of an effect)."""
    for name in ("decide_action", "decide_showdown_action", "decide_reaction"):
        inner = getattr(agent, name)

        def wrapped(*a, _inner=inner, **k):
            if audit.resample:
                audit.resample = False
                _resample(gs, seed)
            return _inner(*a, **k)
        setattr(agent, name, wrapped)


GAME_SECONDS = 20     # a game takes ~20 ms; one past this is stuck in a loop


class Hung(Exception):
    """A game ran past GAME_SECONDS; the message is where it was."""


def play(decks: list[Path], game: int, agent: str, audit: Audit, resample_seed: int = 0) -> str:
    """Play game number `game` (its seed and its deck pair) with `audit` as the
    chooser; returns the winner ("A", "B" or "DRAW"). Raises Hung."""
    from riftbound.core.game_factory import build_game
    from riftbound.core.loop import GameLoop
    a, b = random.Random(game).sample(decks, 2)
    gs = build_game(game_seed=game, deck_a_path=a, deck_b_path=b, ai_a=None, ai_b=None)
    for p in (gs.A, gs.B):
        p.agent = _agent(agent, p, game)
        _hook(p.agent, audit, gs, resample_seed)
    loop = GameLoop(gs)
    loop.chooser = audit
    timer = threading.Timer(GAME_SECONDS, _thread.interrupt_main)
    timer.start()
    try:
        return loop.start().winner
    except KeyboardInterrupt:
        frames = traceback.extract_tb(sys.exc_info()[2])
        raise Hung(" <- ".join(f"{Path(f.filename).name}:{f.lineno} {f.name}"
                               for f in reversed(frames[-8:]))) from None
    finally:
        timer.cancel()


def _score(winner: str, side: str) -> float:
    return 1.0 if winner == side else 0.5 if winner == "DRAW" else 0.0


# ---------------------------------------------------------------------------
# Workers

_DECKS: list[Path] = []
_AGENT = "simple_trade"


def _init(decks, agent):
    global _DECKS, _AGENT
    warnings.filterwarnings("ignore")
    _DECKS, _AGENT = decks, agent


def _survey_game(game: int) -> tuple[int, list[Event], str]:
    audit = Audit()
    try:
        winner = play(_DECKS, game, _AGENT, audit)
    except Hung as exc:
        return game, [], f"HUNG {exc}"
    return game, audit.events, winner


def _regret(job) -> dict:
    """Stage 1: every option (at most 4: the baseline's and 3 others) on `r1`
    reshuffles; stage 2: the best alternative vs the baseline's pick on `r2`
    fresh ones."""
    game, k, ev, r1, r2 = job
    rng = random.Random(game * 1000 + k)
    others = [i for i in range(ev.n) if i != ev.default]
    opts = others if len(others) <= 3 else sorted(rng.sample(others, 3))

    def run(j, seed):
        audit = Audit(force=(k, j))
        winner = play(_DECKS, game, _AGENT, audit, resample_seed=seed)
        got = audit.events[k] if len(audit.events) > k else None
        if got is None or (got.kind, got.n, got.source) != (ev.kind, ev.n, ev.source):
            raise RuntimeError("replay diverged")
        return _score(winner, ev.side)

    try:
        stage1 = {j: mean(run(j, 10_000 + s) for s in range(r1)) for j in [ev.default] + opts}
        best = max(opts, key=lambda j: stage1[j])
        base2 = [run(ev.default, 20_000 + s) for s in range(r2)]
        alt2 = [run(best, 20_000 + s) for s in range(r2)]
    except RuntimeError:
        return {"game": game, "k": k, "diverged": True}
    except Hung as exc:
        return {"game": game, "k": k, "diverged": True, "hung": str(exc), "kind": ev.kind,
                "source": ev.source}
    return {"game": game, "k": k, "kind": ev.kind, "source": ev.source, "n": ev.n,
            "flags": list(ev.flags), "diverged": False,
            "stage1_default": stage1[ev.default],
            "stage1_alts": mean(stage1[j] for j in opts),
            "spread": max(stage1.values()) - min(stage1.values()),
            "base": mean(base2), "alt": mean(alt2), "gain": mean(alt2) - mean(base2)}


# ---------------------------------------------------------------------------
# Report

def _family(kind: str) -> str:
    """Group kinds for the summary: "optional:accelerate" -> "optional",
    "target:kill_unit" and the keyword "you may"s stay (they differ a lot)."""
    head = kind.split(":", 1)[0]
    if head == "target" or kind in ("optional:accelerate", "optional:SHOW OFF"):
        return kind
    return head


def _stderr(xs) -> float:
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1) / len(xs)) ** 0.5


def _report(games: int, agent: str, survey: dict, results: list, n_decks: int,
            r1: int, r2: int, diverged: int, stuck: list) -> str:
    per_kind = survey["per_kind"]
    lines = [
        "# Choice audit",
        "",
        f"Generated by `scripts/choice_audit.py`: {games} games between {n_decks} random "
        f"decks from the whole card pool, `{agent}` on both seats. Regret: {len(results)} sampled "
        f"real choices, {r1} reshuffles per option to find the best alternative, then {r2} "
        f"fresh reshuffles for it vs the baseline ({diverged} replays diverged and were dropped).",
        "",
        *([f"**{len(stuck)} games got stuck** (stopped after {GAME_SECONDS} s, dropped):", "",
           *[f"- {s}" for s in stuck], ""] if stuck else []),
        "**gain** = win rate with the best alternative minus win rate with the baseline's "
        "pick, for the player making the choice (percentage points, ± standard error). "
        "**per game** = gain × how often the choice comes up: the win rate a player would "
        "gain per game if this choice were made well.",
        "",
        "## By kind of choice",
        "",
        "| choice | times/game | real % | sampled | baseline vs a random pick (pts) | gain (pts) "
        "| clearly worse* | per game (pts) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    by_fam: dict = defaultdict(list)
    for r in results:
        by_fam[_family(r["kind"])].append(r)
    fam_counts: Counter = Counter()
    fam_real: Counter = Counter()
    for kind, (count, real) in per_kind.items():
        fam_counts[_family(kind)] += count
        fam_real[_family(kind)] += real
    rows = []
    for fam in fam_counts:
        rs = by_fam.get(fam, [])
        gains = [r["gain"] for r in rs]
        g = mean(gains) if gains else 0.0
        per_game_real = fam_real[fam] / games
        rows.append((per_game_real * g, fam, rs, gains, g))
    for impact, fam, rs, gains, g in sorted(rows, key=lambda t: -t[0]):
        if not fam_real[fam]:
            continue
        worse = sum(1 for x in gains if x >= 0.10)
        vs_random = [r["stage1_default"] - r["stage1_alts"] for r in rs]
        lines.append(
            f"| `{fam}` | {fam_counts[fam] / games:.2f} | {100 * fam_real[fam] / fam_counts[fam]:.0f} | "
            f"{len(rs)} | {100 * mean(vs_random) if rs else 0:+.1f} | "
            f"{100 * g:+.1f} ± {100 * _stderr(gains):.1f} | "
            f"{(100 * worse / len(rs)) if rs else 0:.0f}% | {100 * impact:+.2f} |")
    total = sum(max(0.0, t[0]) for t in rows)
    lines += ["", f"Total over the choices with a positive gain: **{100 * total:+.1f} points per game**.",
              "", "\\* share of sampled choices where the best alternative wins at least 10 "
              "points more often than the baseline's pick. **baseline vs a random pick**: the "
              "baseline's win rate minus the average alternative's (stage 1); positive means the "
              "baseline beats picking at random.", ""]

    lines += ["## Cards whose choices cost the most", "",
              "| card | choice | sampled | gain (pts) |", "|---|---|---:|---:|"]
    by_card: dict = defaultdict(list)
    for r in results:
        by_card[(r["source"] or "(combat)", _family(r["kind"]))].append(r["gain"])
    worst = sorted(by_card.items(), key=lambda kv: -sum(kv[1]))[:30]
    for (card, fam), gains in worst:
        lines.append(f"| {card} | `{fam}` | {len(gains)} | {100 * mean(gains):+.1f} |")

    lines += ["", "## What the baseline picked (unit choices)", "",
              "| choice | events | took a friendly unit | friendly with an enemy available | "
              "enemy with a friendly available | not the mightiest of its side |",
              "|---|---:|---:|---:|---:|---:|"]
    for fam, fl in sorted(survey["flags"].items(), key=lambda kv: -kv[1]["events"]):
        e = fl["events"]
        if e < 20:
            continue
        lines.append(f"| `{fam}` | {e} | {100 * fl['friendly'] / e:.0f}% | "
                     f"{100 * fl['enemy_available'] / e:.0f}% | {100 * fl['friendly_available'] / e:.0f}% | "
                     f"{100 * fl['not_mightiest'] / e:.0f}% |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------

@app.command()
def main(
    games: int = typer.Option(2000, "--games", help="Survey games"),
    events: int = typer.Option(1200, "--events", help="Real choices to replay for regret"),
    per_kind: int = typer.Option(80, "--per-kind", help="At most this many sampled per kind family"),
    r1: int = typer.Option(8, "--r1", help="Reshuffles per option, stage 1"),
    r2: int = typer.Option(32, "--r2", help="Reshuffles per side, stage 2"),
    n_decks: int = typer.Option(120, "--decks", help="Random decks to build"),
    agent: str = typer.Option("simple_trade", "--agent", help="simple_trade | random"),
    seed: int = typer.Option(7, "--seed"),
    workers: int = typer.Option(max(1, (os.cpu_count() or 2) - 2), "--workers"),
    out: Path = typer.Option(ROOT / "CHOICE_AUDIT.md", "--out"),
    raw: Path = typer.Option(None, "--raw", help="Optional: write the per-choice results as JSON"),
) -> None:
    deck_dir = Path(tempfile.mkdtemp(prefix="choice_audit_"))
    decks = random_decks(n_decks, seed, deck_dir)
    with Pool(workers, initializer=_init, initargs=(decks, agent)) as pool:
        played = pool.map(_survey_game, range(games), chunksize=8)

        per: dict = defaultdict(lambda: [0, 0])
        flags: dict = defaultdict(Counter)
        real: dict = defaultdict(list)
        for game, evs, _winner in played:
            for k, ev in enumerate(evs):
                per[ev.kind][0] += 1
                if ev.n > 1:
                    per[ev.kind][1] += 1
                    real[_family(ev.kind)].append((game, k, ev))
                    if ev.flags:
                        f = flags[_family(ev.kind)]
                        f["events"] += 1
                        for name in ev.flags:
                            f[name] += 1
        hung = [(g, w) for g, _evs, w in played if w.startswith("HUNG")]
        print(f"survey: {games} games, {sum(c for c, _ in per.values())} choices "
              f"({sum(r for _, r in per.values())} with more than one option), "
              f"{len(hung)} stuck", flush=True)
        for g, w in hung:
            print(f"  game {g} {w}", flush=True)

        # Sample: up to per_kind per family, then fill to `events` in proportion.
        rng = random.Random(seed)
        jobs = []
        for fam, items in sorted(real.items()):
            rng.shuffle(items)
            jobs += [(g, k, ev, r1, r2) for g, k, ev in items[:per_kind]]
        rng.shuffle(jobs)
        jobs = jobs[:events]
        print(f"regret: {len(jobs)} choices x up to {4 * r1 + 2 * r2} games each", flush=True)
        results = []
        for r in pool.imap_unordered(_regret, jobs, chunksize=2):
            results.append(r)
            if r.get("hung"):
                print(f"  stuck: game {r['game']} choice {r['k']} ({r['kind']}, {r['source']}): "
                      f"{r['hung']}", flush=True)
            if len(results) % 200 == 0:
                print(f"  {len(results)}/{len(jobs)}", flush=True)

    results.sort(key=lambda r: (r["game"], r["k"]))
    ok = [r for r in results if not r["diverged"]]
    stuck = [f"survey game {g}: `{w[5:]}`" for g, w in hung]
    stuck += [f"game {r['game']}, choice {r['k']} (`{r['kind']}`, {r['source']}): `{r['hung']}`"
              for r in results if r.get("hung")]
    survey = {"per_kind": {k: tuple(v) for k, v in per.items()}, "flags": flags}
    n_div = sum(1 for r in results if r["diverged"] and not r.get("hung"))
    out.write_text(_report(games, agent, survey, ok, n_decks, r1, r2, n_div, stuck),
                   encoding="utf-8")
    if raw is not None:
        raw.write_text(json.dumps({"per_kind": survey["per_kind"], "results": ok}, indent=1),
                       encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    # Same games in every worker process: no per-process hash randomization.
    if os.environ.get("PYTHONHASHSEED") != "0":
        env = {**os.environ, "PYTHONHASHSEED": "0"}
        sys.exit(subprocess.call([sys.executable, *sys.argv], env=env))
    app()
