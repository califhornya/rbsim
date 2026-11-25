"""The coach page on the Rust engine (riftbound/ai/coach_rs.py): `CoachSession` driven through its
public methods as the server does (state / answer / rewind / new_game), no HTTP. The human is a
seeded random choice among the offered options (payments included). Games against simple_trade
(ES, EK, RS) and the champion with few iterations; the rewind returns to the checkpoint and the
game that goes on with the same answers ends as the one without it."""
from __future__ import annotations

import json
import random
import time

import pytest

torch = pytest.importorskip("torch")

from riftbound.ai.coach import CoachSession  # noqa: E402
from riftbound.provenienza import REGOLE_D72_D77  # noqa: E402

PROFILO = REGOLE_D72_D77
RUN = {}           # statistics of the full games, read by the last test


def _deck(letter: str):
    from riftbound.ai.ppo.collect import DECK_OF
    return DECK_OF[letter]


def _session(tmp_path, **kw) -> CoachSession:
    return CoachSession(None, tmp_path / "coach", opponent_pause=0, **{"motore": "rust", **kw})


def _campione(tmp_path):
    from riftbound.ai.ppo.model import PPONet, save
    torch.manual_seed(0)
    path = tmp_path / "campione.pt"
    save(PPONet(), path)
    return path


def _wait(session: CoachSession, timeout: float = 180.0) -> dict:
    """The state once the game waits for an answer or is over."""
    end = time.time() + timeout
    while time.time() < end:
        st = session.state()
        if st["status"] == "over" or (st["status"] == "waiting" and st["pending"] is not None):
            return st
        time.sleep(0.002)
    raise AssertionError("the coached game neither waits nor ends")


def _check(st: dict) -> str:
    """What every pending question must have: its texts and a board."""
    p = st["pending"]
    assert st["observation"] is not None and st["board"] is not None and isinstance(st["cards"], dict)
    t = p["type"]
    if t == "decision":
        assert p["context"] and p["actions"] and all(a["text"] and a["kind"] for a in p["actions"])
    elif t == "choice":
        assert p["question"] and p["options"] and all(o["text"] for o in p["options"])
        return "payment" if p["kind"] == "payment" else "choice"
    elif t == "mulligan":
        assert p["hand"] and all(c["text"] for c in p["hand"])
    else:
        assert t == "notice" and p["context"]
    return t


def _answer(pending: dict, rng: random.Random) -> dict:
    t = pending["type"]
    if t == "mulligan":
        return {"return": sorted(rng.sample(range(len(pending["hand"])), rng.randrange(0, 3)))}
    if t == "decision":
        return {"action": rng.randrange(len(pending["actions"]))}
    if t == "choice":
        return {"option": rng.randrange(len(pending["options"]))}
    return {}


def _drive(session: CoachSession, rng: random.Random, answers=None, stop_after=None, stats=None):
    """Answer the questions until the game is over (or `stop_after` of them were answered: the state
    waiting at the next one is returned). `answers`: the payloads to give, in order (else random).
    -> (state, [(pending, observation, payload) of the questions answered])."""
    seen = []
    while True:
        st = _wait(session)
        if st["status"] == "over" or (stop_after is not None and len(seen) == stop_after):
            return st, seen
        kind = _check(st)
        if stats is not None:
            stats[kind] = stats.get(kind, 0) + 1
        payload = answers[len(seen)] if answers is not None and len(seen) < len(answers) \
            else _answer(st["pending"], rng)
        seen.append((st["pending"], st["observation"], payload))
        session.answer(payload)


GAMES = (("ES", 3), ("ES", 11), ("EK", 5), ("EK", 12), ("RS", 7), ("RS", 13))


@pytest.mark.parametrize("mu,seed", GAMES)
def test_a_whole_game_against_simple_trade(tmp_path, mu, seed):
    session = _session(tmp_path)
    session.new_game(_deck(mu[0]), _deck(mu[1]), seat="A", opponent="simple_trade", seed=seed)
    assert session.state()["info"]["motore"] == "rust"
    stats: dict = {}
    st, seen = _drive(session, random.Random(seed), stats=stats)
    assert st["status"] == "over" and st["result"] and "error" not in st["result"], st["result"]
    assert st["regole"] == PROFILO and st["info"]["regole"] == PROFILO and st["motore"] == "rust"
    assert st["result"]["winner"] in ("A", "B", "DRAW") and st["result"]["turns"] > 1
    assert stats["decision"] > 5 and stats["mulligan"] == 1 and st["events"] and st["log"] is not None
    RUN[(mu, seed)] = stats
    row = json.loads((tmp_path / "coach" / "games.jsonl").read_text().splitlines()[-1])
    assert row["motore"] == "rust" and row["regole"] == PROFILO and row["opponent"] == "simple_trade"


def test_payment_choices_were_asked_and_played():
    """After the full games: the page asked "Come paghi?" and some answer was not the engine's way."""
    if not RUN:
        pytest.skip("run with the full games")
    paid = sum(s.get("payment", 0) for s in RUN.values())
    print(f"payment questions: {paid}; choices: {sum(s.get('choice', 0) for s in RUN.values())}")
    assert paid > 0


def test_rewind_goes_back_and_the_game_goes_on_the_same(tmp_path):
    mu, seed = "EK", 5
    rng = random.Random(seed)

    def new(path):
        s = _session(path)
        s.new_game(_deck("E"), _deck("K"), seat="A", opponent="simple_trade", seed=seed)
        return s

    # the game with no rewind: its answers (given by a seeded random choice)
    full, seen = _drive(new(tmp_path / "a"), rng)
    assert full["result"] and "error" not in full["result"]
    answers = [p for _q, _o, p in seen]
    # the same game: stop after k answers (the last one a decision), take it back, answer as before
    kinds = [q["type"] for q, _o, _p in seen]
    k = next(i for i in range(20, len(seen) - 5) if kinds[i - 1] == "decision" and kinds[i] == "decision") + 1
    session = new(tmp_path / "b")
    st, got = _drive(session, rng, answers=answers, stop_after=k)
    assert st["can_rewind"]
    last = max(i for i in range(k) if kinds[i] in ("decision", "mulligan"))
    session.rewind()
    st = _wait(session)
    assert st["pending"] == seen[last][0] and st["observation"] == seen[last][1]   # the checkpoint's page
    assert st["rewinds"] == 1 and st["events"][-1]["text"].startswith("Mossa annullata")
    # more rewinds, one after another, down to the first decision and the mulligan
    for _ in range(2):
        session.rewind()
        st = _wait(session)
        assert st["pending"]["type"] in ("decision", "mulligan")
    assert st["rewinds"] == 3
    back = max(i for i in range(last) if kinds[i] in ("decision", "mulligan"))
    back = max(i for i in range(back) if kinds[i] in ("decision", "mulligan"))
    assert st["pending"] == seen[back][0] and st["observation"] == seen[back][1]
    end, more = _drive(session, rng, answers=answers[back:])
    assert end["result"] == full["result"] and end["observation"] == full["observation"]
    assert end["board"] == full["board"] and end["info"]["seed"] == full["info"]["seed"]
    assert [q for q, _o, _p in more] == [q for q, _o, _p in seen[back:]]


def test_the_champion_with_few_iterations_is_deterministic_and_rewinds(tmp_path):
    camp = _campione(tmp_path)

    def play(path, rewind_at=None, answers=None):
        s = _session(path, campione_path=camp, iterazioni=10)
        s.new_game(_deck("E"), _deck("S"), seat="B", opponent="campione", seed=4)
        rng = random.Random(4)
        out, n, rewound = [], 0, False
        end = time.time() + 240
        while time.time() < end and n < 40:
            st = _wait(s)
            if st["status"] == "over":
                break
            _check(st)
            if rewind_at is not None and n == rewind_at and not rewound and st["can_rewind"]:
                rewound = True
                s.rewind()
                st2 = _wait(s)
                assert st2["rewinds"] == 1 and st2["pending"]["type"] in ("decision", "mulligan")
                out = out[:next(i for i in range(len(out) - 1, -1, -1)
                                if out[i][0]["type"] in ("decision", "mulligan"))]
                n = len(out)
                continue
            payload = answers[n] if answers is not None and n < len(answers) else _answer(st["pending"], rng)
            out.append((st["pending"], payload))
            n += 1
            s.answer(payload)
        st = s.state()
        assert st["info"]["opponent"] == "campione" and st["regole"] == PROFILO and st["motore"] == "rust"
        s.abandon()
        s._thread.join(timeout=120)
        return out, rewound

    a, _ = play(tmp_path / "a")
    b, _ = play(tmp_path / "b")
    assert [q for q, _ in a] == [q for q, _ in b] and len(a) >= 10     # deterministic: same questions
    answers = [p for _q, p in a]
    assert [p for _q, p in b] == answers
    # a rewind after 12 answers, then the same answers: the same questions (the champion decides again,
    # with the same iterations and seed: the same moves)
    c, rewound = play(tmp_path / "c", rewind_at=12, answers=answers)
    assert rewound and len(c) >= 12
    assert [q for q, _ in c] == [q for q, _ in a][:len(c)]


def test_what_rust_does_not_cover_plays_on_python(tmp_path):
    from pathlib import Path
    repo = Path(__file__).resolve().parents[2]
    zed, shen = repo / "riftbound/data/decks/precon_zed.json", repo / "riftbound/data/decks/precon_shen.json"
    session = _session(tmp_path)         # motore rust, but precon_zed / precon_shen are not covered
    session.new_game(zed, shen, seat="A", opponent="simple_trade", seed=3)
    st = session.state()
    assert st["info"]["motore"] == "python" and st["info"]["regole"] == "6427b90" and st["regole"] == "6427b90"
    session.abandon()
    session._thread.join(timeout=120)
    # the motore python option: a covered game plays on Python too
    session = _session(tmp_path, motore="python")
    session.new_game(_deck("E"), _deck("K"), seat="A", opponent="simple_trade", seed=3)
    assert session.state()["info"]["motore"] == "python" and session.state()["regole"] == "6427b90"
    session.abandon()
    session._thread.join(timeout=120)


def _choice_events(kind_head: str, n_min: int):
    """Real choice events of the opponent's seat B (the coach is A) with at least `n_min` options."""
    from riftbound.rs import rust_bridge as rb
    out = []
    for mu, seed in (("ES", 3), ("EK", 5), ("RS", 7), ("ES", 11), ("EK", 12)):
        g = rb.build(seed, _deck(mu[0]), _deck(mu[1]), "a", 40, regole=PROFILO)
        for s in "AB":
            g.set_agent(s, "simple_trade", 0)
        g.set_side_chooser()
        g.trace_on()
        g.start()
        out += [e for e in json.loads(g.events()) if e["k"] == "choice" and e["seat"] == "B"
                and e["kind"].partition(":")[0] == kind_head and len(e["options_raw"]) >= n_min]
        if out:
            return out
    return out


def test_a_choice_is_logged_once_with_its_picks_together():
    """The log says a choice once, as the Python page does: the picks of one "up to N" choice together
    ("nessuno" if none), one line for a single pick, nothing doubled."""
    from types import SimpleNamespace

    from riftbound.ai.coach import CoachSession
    from riftbound.ai.coach_rs import RustGame
    evs = _choice_events("target", 3)
    assert evs, "no target choice with 3 options in the test games"
    base = evs[0]
    calls = []
    fake = SimpleNamespace(side="A", gs=None, _PUBLIC_CHOICES=CoachSession._PUBLIC_CHOICES,
                           _log_choice=lambda *a: calls.append(a), _replaying=False)
    game = RustGame.__new__(RustGame)
    game.s, game.objs, game._batch = fake, {}, None
    raw = base["options_raw"]
    no_more = {"root": {"o": "$NO_MORE"}, "objs": {}}

    def event(options, chosen):
        return {**base, "options_raw": options, "chosen": chosen}

    def feed(*es):
        for e in es:
            game._logged_choice(e, False)
        game._flush()
    # one pick: a line with the option; then a state change (another event) flushes it
    feed(event(raw, 1))
    assert len(calls) == 1 and not isinstance(calls[0][3], list)
    calls.clear()
    # "up to 2" with two picks and then the stop: ONE line with both, in the order picked
    feed(event(raw + [no_more], 0), event(raw[1:] + [no_more], 0), event(raw[2:] + [no_more], len(raw) - 2))
    assert len(calls) == 1 and isinstance(calls[0][3], list) and len(calls[0][3]) == 2
    assert calls[0][3][0] is not calls[0][3][1]
    calls.clear()
    # "up to N" stopped at once: "nessuno"
    feed(event(raw + [no_more], len(raw)))
    assert len(calls) == 1 and calls[0][3] == []
    calls.clear()
    # two separate choices (the second's options are not the first's without its pick): two lines
    feed(event(raw, 0), event(raw, 0))
    assert len(calls) == 2


def _pendings(mu: str, seed: int, want):
    """The pending choices of a random-answered game on Rust for which want(pending) holds."""
    session = _session(__import__("pathlib").Path(__import__("tempfile").mkdtemp()))
    session.new_game(_deck(mu[0]), _deck(mu[1]), seat="A", opponent="simple_trade", seed=seed)
    rng, out = random.Random(seed), []
    while True:
        st = _wait(session)
        if st["status"] == "over":
            return out
        if want(st["pending"]):
            out.append(st["pending"])
        session.answer(_answer(st["pending"], rng))


def test_the_cards_looked_at_are_shown_with_the_choice_that_follows():
    """A dig (Ivern, IS seed 11) shows the cards with "Quale carta tenere?"; Predict (ES seed 3) with
    "Mandare in fondo al mazzo questa carta?"."""
    keep = _pendings("IS", 11, lambda p: p["type"] == "choice" and p["kind"].startswith("keep"))
    assert keep and all(p["seen"] and len(p["seen"]) >= 2 for p in keep)
    pred = _pendings("ES", 3, lambda p: p["type"] == "choice" and p["kind"] == "predict_recycle")
    assert pred and all(len(p["seen"]) == 1 for p in pred)


@pytest.mark.xfail(strict=True, reason="Rust gives the human seat no information on a look: the cards are "
                                       "taken off the deck inside the effect (fx_dig) and only the choice "
                                       "after it lists them; needs a hook in rbsim-core")
def test_the_cards_looked_at_are_shown_in_prendere_una_delle_carte_guardate():
    asked = _pendings("IS", 11, lambda p: p["type"] == "choice" and p["kind"] == "optional:keep")
    assert asked and all(p.get("seen") for p in asked)
