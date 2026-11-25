//! riftbound_rs: the Rust engine (rbsim-core) for Python. A Game is built from
//! two deck files and a seed (as game_factory.build_game) or imported from a
//! canonical tree; it plays with agents that replay a Python trace, or with
//! Python agents; it dumps its state in canon.py's raw format.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use std::cell::RefCell;
use std::collections::VecDeque;
use std::rc::Rc;

use rbsim_core::agent::{Agent, Chooser};
use rbsim_core::agents::{RandomAgent, SideChooser, SimpleTradeAgent};

mod human;
mod ppo;
mod search_py;
use rbsim_core::search::{Layers, SearchAgent, SearchCore};
use rbsim_core::game::Game as CoreGame;
use rbsim_core::registry::Registry as CoreRegistry;
use rbsim_core::trace::{ReplayAgent, ReplayChooser, ScriptAgent, Sink, TraceAgent, TraceBuf, TraceChooser};
use rbsim_core::types::{EngineError, Side};

fn perr(e: EngineError) -> PyErr {
    PyRuntimeError::new_err(e.to_string())
}

fn serr(e: String) -> PyErr {
    PyRuntimeError::new_err(e)
}

fn seat_of(seat: &str) -> PyResult<Side> {
    match seat {
        "A" => Ok(Side::A),
        "B" => Ok(Side::B),
        _ => Err(serr(format!("seat {seat}"))),
    }
}

#[pyclass(unsendable)]
struct Registry {
    reg: Rc<CoreRegistry>,
}

#[pymethods]
impl Registry {
    /// `regole`: the rules profile ("6427b90", the default, or
    /// "6427b90+D72-D76" or "6427b90+D72-D77"); every game built on this registry plays it.
    #[new]
    #[pyo3(signature = (path, regole=None))]
    fn new(path: &str, regole: Option<&str>) -> PyResult<Self> {
        let text = std::fs::read_to_string(path).map_err(|e| serr(e.to_string()))?;
        let regole = rbsim_core::registry::Regole::parse(regole.unwrap_or(rbsim_core::registry::Regole::STORICHE))
            .map_err(serr)?;
        Ok(Registry { reg: Rc::new(CoreRegistry::from_json_regole(&text, regole).map_err(serr)?) })
    }
    fn __len__(&self) -> usize {
        self.reg.cards.len()
    }
    #[getter]
    fn regole(&self) -> &'static str {
        self.reg.regole.name()
    }
    /// The effective cards' fingerprint (the profile's data correction applied).
    #[getter]
    fn impronta(&self) -> String {
        self.reg.impronta.clone()
    }
    #[getter]
    fn correzione_dati(&self) -> Option<&'static str> {
        self.reg.regole.corrette().then_some(rbsim_core::registry::CORREZIONE_DATI)
    }
}

#[pyclass(unsendable)]
struct Game {
    g: CoreGame,
    ppo: [Option<Rc<RefCell<ppo::PpoAgent>>>; 2],
    sink: Option<Sink>,
    winner: Option<String>,
    turns: i64,
    /// The search agents (py: HandwrittenAgent / PPOPriorAgent) and their
    /// shared choosers on the real loop.
    search: [Option<Rc<RefCell<SearchCore>>>; 2],
    layers: Option<Rc<RefCell<Layers>>>,
}

#[pymethods]
impl Game {
    /// py: build_game(game_seed, deck_a_path, deck_b_path, first_player, max_turns)
    #[staticmethod]
    #[pyo3(signature = (reg, seed, deck_a_json, deck_b_json, first_player, max_turns, bf_a=None, bf_b=None))]
    fn build(reg: &Registry, seed: i64, deck_a_json: &str, deck_b_json: &str, first_player: &str, max_turns: i64,
             bf_a: Option<&str>, bf_b: Option<&str>) -> PyResult<Game> {
        let a = rbsim_core::setup::load_deck(deck_a_json).map_err(serr)?;
        let b = rbsim_core::setup::load_deck(deck_b_json).map_err(serr)?;
        let g = rbsim_core::setup::build_game(reg.reg.clone(), seed, &a, &b, first_player, max_turns, bf_a, bf_b).map_err(serr)?;
        Ok(Game { g, ppo: [None, None], sink: None, winner: None, turns: 0, search: [None, None], layers: None })
    }

    /// A game from a canonical tree (canon.canonical_state), RNG seeded with `seed`.
    #[staticmethod]
    fn from_canonical(reg: &Registry, tree_json: &str, seed: i64) -> PyResult<Game> {
        let tree: serde_json::Value = serde_json::from_str(tree_json).map_err(|e| serr(e.to_string()))?;
        let gs = rbsim_core::import::from_canonical(reg.reg.clone(), &tree, seed as i128).map_err(serr)?;
        Ok(Game { g: CoreGame::new(gs), ppo: [None, None], sink: None, winner: None, turns: 0, search: [None, None], layers: None })
    }

    /// The state, raw (canon.py's RawDumper format), as JSON.
    fn raw_dump(&self) -> String {
        self.g.raw_dump().to_string()
    }

    /// Replay agents from a Python trace's events (JSON list): each seat takes
    /// its decisions in order; `chooser`: the chooser's answers too;
    /// `has_optional`: the Python agents had decide_optional/mode/predict.
    fn set_replay(&mut self, events_json: &str, chooser: bool, has_optional: bool) -> PyResult<()> {
        let events: Vec<serde_json::Value> = serde_json::from_str(events_json).map_err(|e| serr(e.to_string()))?;
        let seat_kinds = ["decision", "decide_mulligan", "decide_optional", "decide_mode", "decide_predict_recycle"];
        for s in Side::BOTH {
            let evs: VecDeque<serde_json::Value> = events
                .iter()
                .filter(|e| e["seat"] == s.name() && seat_kinds.contains(&e["k"].as_str().unwrap_or("")))
                .cloned()
                .collect();
            let a: Rc<RefCell<dyn Agent>> = Rc::new(RefCell::new(ReplayAgent { events: evs, has_optional }));
            self.g.agents[s.idx()] = Some(a);
            self.g.gs.players[s.idx()].has_agent = true;
        }
        if chooser {
            let evs: VecDeque<serde_json::Value> = events.iter().filter(|e| e["k"] == "choice").cloned().collect();
            let c: Rc<RefCell<dyn Chooser>> = Rc::new(RefCell::new(ReplayChooser { events: evs }));
            self.g.chooser = Some(c);
        }
        Ok(())
    }

    /// A Rust agent for seat "A" / "B": "simple_trade" or "random" (its
    /// generator seeded with `seed`, as random.Random(seed)).
    fn set_agent(&mut self, seat: &str, kind: &str, seed: i64) -> PyResult<()> {
        let s = match seat {
            "A" => Side::A,
            "B" => Side::B,
            _ => return Err(serr(format!("seat {seat}"))),
        };
        let a: Rc<RefCell<dyn Agent>> = match kind {
            "simple_trade" => Rc::new(RefCell::new(SimpleTradeAgent::default())),
            "random" => Rc::new(RefCell::new(RandomAgent::new(seed as i128))),
            _ => return Err(serr(format!("agent {kind}"))),
        };
        self.g.agents[s.idx()] = Some(a);
        self.g.gs.players[s.idx()].has_agent = true;
        Ok(())
    }

    /// A PPO agent for seat "A" / "B": Rust builds each question, `ask`
    /// (riftbound/rs/agent_rs.AskPPO) answers it.
    fn set_ppo_agent(&mut self, seat: &str, ask: Py<PyAny>) -> PyResult<()> {
        let s = seat_of(seat)?;
        let a = Rc::new(RefCell::new(ppo::PpoAgent::new(ask, s)));
        self.ppo[s.idx()] = Some(a.clone());
        let d: Rc<RefCell<dyn Agent>> = a;
        self.g.agents[s.idx()] = Some(d);
        self.g.gs.players[s.idx()].has_agent = true;
        Ok(())
    }

    /// A human seat "A" / "B": every decision of the seat (mulligan, turn_action,
    /// reaction, showdown_action, even with a single legal option) and every
    /// in-move choice (all `choice` kinds, decide_optional, decide_mode,
    /// decide_predict_recycle) calls `ask(event_json: str)`, whose return value
    /// is the answer. `event_json` is the event the trace records for it
    /// (same builder, same keys, the state before the answer), without the
    /// answer fields. The answer is a Python object (not JSON) shaped like the
    /// missing field: decision -> int index into `menu` (None only for an
    /// empty menu: a Pass; a list/tuple [kind, index, lane(, dst)], the
    /// trace's `action` shape, is played as is even if outside the menu: for
    /// bots and replays, a human page answers with an index); choice -> int index into `options_raw`;
    /// decide_mulligan -> list of at most 2 distinct hand indices ([] keeps
    /// the hand); decide_optional / decide_predict_recycle -> bool;
    /// decide_mode -> int in 0..n (args[1]) or None (the engine picks).
    ///
    /// `payments=True` (the coach page's "Come paghi?", port of
    /// coach.payment_options / gold_only_plays / _gold_step): a decision event
    /// of a menu with more than one move also has `pay` (one entry per menu
    /// move: null, or, where the page would offer a choice, the list of ways
    /// to pay it, the engine's own first) and `gold_only` (the plays payable
    /// only with Golds, [{"action": [kind, index, lane(, dst)], "ways": [...]}]).
    /// A way is {"golds": n, "gold_domain": "FURY".. or null, "prefer": domain
    /// name or null (the domain the [rune] cost is paid from first), "accelerate":
    /// null, or true / false where the move asks "Pagare ACCELERATE?" (the answer
    /// the way is for; the seat gives it to the engine's question itself), "recycled":
    /// [[domain name, runes], ...] (what it recycles, in the rune pool's order)};
    /// the page's Italian `text` is the caller's. Besides the answers above a
    /// decision takes {"index": i, "via": w} (menu move i paid with its way
    /// number w in `pay[i]`) or {"solo_gold": j, "via": w} (gold_only[j] with
    /// its way w): the seat then uses the Golds the way needs (each its own
    /// decision in the trace, answering the Gold's "which domain" itself) and
    /// plays the move, without asking `ask` for those steps. Computed on copies
    /// of the game; the game is not touched.
    /// A bool where an int is wanted (or vice versa), a wrong type or an index
    /// out of range raises ValueError out of start() / run_segment(). An
    /// exception of `ask` propagates as the same object. In-move choices reach
    /// the seat through the side chooser: it is set here if the game has none.
    /// Call it before trace_on() (as the other set_* methods); do not touch the
    /// Game from inside `ask`.
    /// `notify(event_json)`: what the engine shows the seat without a question (no answer, never in
    /// the trace): {"k": "look", args: {"cards": [raw card, ...]}} when it looks at cards on top of its
    /// deck. The seat's sett_save choice event (for `ask` alone) also carries `dying`: {"group": {"bf",
    /// "units": [{"id", "unit": raw}]}, "now": {"id", "unit"}}, the units of its side dying together.
    #[pyo3(signature = (seat, ask, payments=false, notify=None))]
    fn set_human_agent(&mut self, seat: &str, ask: Py<PyAny>, payments: bool, notify: Option<Py<PyAny>>) -> PyResult<()> {
        let s = seat_of(seat)?;
        let a: Rc<RefCell<dyn Agent>> = Rc::new(RefCell::new(human::HumanAgent::new(ask, self.g.loop_id, payments, notify)));
        self.g.agents[s.idx()] = Some(a);
        self.g.gs.players[s.idx()].has_agent = true;
        if self.g.chooser.is_none() {
            self.set_side_chooser();
        }
        Ok(())
    }

    /// A search agent for seat "A" / "B" (py: HandwrittenAgent(p, iterations,
    /// rng=random.Random(seed), budget); with `probs`, PPOPriorAgent: the net's
    /// softmax over each menu, see search_py.rs). `log`: one row per searched
    /// decision (search_log).
    #[pyo3(signature = (seat, iterations, seed, budget=None, probs=None, log=false, before=None, after=None))]
    #[allow(clippy::too_many_arguments)]
    fn set_search_agent(&mut self, seat: &str, iterations: usize, seed: i64, budget: Option<f64>,
                        probs: Option<Py<PyAny>>, log: bool, before: Option<Py<PyAny>>,
                        after: Option<Py<PyAny>>) -> PyResult<()> {
        let s = seat_of(seat)?;
        let layers = self.layers.get_or_insert_with(|| Rc::new(RefCell::new(Layers::default()))).clone();
        let prior: Option<Box<dyn rbsim_core::search::Prior>> =
            probs.map(|p| Box::new(search_py::PyPrior { probs: p }) as Box<dyn rbsim_core::search::Prior>);
        let core = SearchCore::new(s, iterations, seed as i128, budget, prior, layers);
        if log {
            core.borrow_mut().log = Some(Vec::new());
        }
        if let (Some(before), Some(after)) = (before, after) {
            core.borrow_mut().lockstep = Some(Box::new(search_py::PyLockstep { before, after }));
        }
        self.search[s.idx()] = Some(core.clone());
        let a: Rc<RefCell<dyn Agent>> = Rc::new(RefCell::new(SearchAgent { core }));
        self.g.agents[s.idx()] = Some(a);
        self.g.gs.players[s.idx()].has_agent = true;
        Ok(())
    }

    /// Opt-in: a search seat looks for a win this turn (by moves) before searching.
    fn set_search_win_probe(&mut self, seat: &str, on: bool) -> PyResult<()> {
        let s = seat_of(seat)?;
        match &self.search[s.idx()] {
            Some(c) => {
                c.borrow_mut().win_probe = on;
                Ok(())
            }
            None => Err(pyo3::exceptions::PyValueError::new_err(format!("no search agent on seat {seat}"))),
        }
    }

    /// Observation only: the search_log rows of this seat also carry `iters`, `secs`
    /// (CPU seconds of the search) and `probe_secs` (win probe since the previous row).
    fn set_search_timing(&mut self, seat: &str, on: bool) -> PyResult<()> {
        let s = seat_of(seat)?;
        match &self.search[s.idx()] {
            Some(c) => {
                c.borrow_mut().timing = on;
                Ok(())
            }
            None => Err(pyo3::exceptions::PyValueError::new_err(format!("no search agent on seat {seat}"))),
        }
    }

    /// A search seat's rows (JSON list), [] for another seat.
    fn search_log(&self, seat: &str) -> PyResult<String> {
        let s = seat_of(seat)?;
        Ok(match &self.search[s.idx()] {
            Some(c) => serde_json::Value::Array(c.borrow().log.clone().unwrap_or_default()).to_string(),
            None => "[]".into(),
        })
    }

    /// Diagnosis: dump the copy of search `k` (0-based), simulation `j`, at every step.
    fn set_search_debug(&mut self, seat: &str, k: usize, j: usize) -> PyResult<()> {
        let s = seat_of(seat)?;
        if let Some(c) = &self.search[s.idx()] {
            c.borrow_mut().debug = Some((k, j));
        }
        Ok(())
    }

    /// The dumps of set_search_debug (JSON list).
    fn search_debug(&self, seat: &str) -> PyResult<String> {
        let s = seat_of(seat)?;
        Ok(match &self.search[s.idx()] {
            Some(c) => serde_json::Value::Array(c.borrow().debug_out.clone()).to_string(),
            None => "[]".into(),
        })
    }

    /// A search seat's (iterations of each main-turn search under a budget,
    /// empty turns, turns).
    fn search_stats(&self, seat: &str) -> PyResult<(Vec<usize>, i64, i64)> {
        let s = seat_of(seat)?;
        Ok(match &self.search[s.idx()] {
            Some(c) => {
                let c = c.borrow();
                (c.main_iters.clone(), c.empty_turns, c.turns)
            }
            None => (Vec::new(), 0, 0),
        })
    }

    /// A seat scripted by label prefixes (positions in tests): per point the
    /// entries in order, PASS once a script runs out (rbsim_core ScriptAgent).
    #[pyo3(signature = (seat, main=Vec::new(), showdown=Vec::new(), reaction=Vec::new()))]
    fn set_script(&mut self, seat: &str, main: Vec<String>, showdown: Vec<String>, reaction: Vec<String>)
                  -> PyResult<()> {
        let s = seat_of(seat)?;
        let a: Rc<RefCell<dyn Agent>> = Rc::new(RefCell::new(ScriptAgent {
            scripts: [main.into(), showdown.into(), reaction.into()],
        }));
        self.g.agents[s.idx()] = Some(a);
        self.g.gs.players[s.idx()].has_agent = true;
        Ok(())
    }

    /// The loop's chooser: each choice to the agent of the side making it
    /// (py: PPOChooser).
    fn set_side_chooser(&mut self) {
        let c: Rc<RefCell<dyn Chooser>> = Rc::new(RefCell::new(SideChooser));
        self.g.chooser = Some(c);
    }

    /// A PPO seat's counts (py: PPOAgent.counts), {} for another seat.
    fn counts(&self, seat: &str) -> PyResult<std::collections::BTreeMap<String, i64>> {
        let s = seat_of(seat)?;
        Ok(match &self.ppo[s.idx()] {
            Some(a) => a.borrow().counts.clone(),
            None => Default::default(),
        })
    }

    /// Trace the game (trace_py's events, raw dumps), from now on. With
    /// `watch`, every event recorded is also passed live to `watch(event_json:
    /// str)`: the complete event, answer included, in the order `events()`
    /// returns them. An exception of `watch` propagates out of start() /
    /// run_segment() as the same object. Do not touch the Game from inside it.
    #[pyo3(signature = (watch=None))]
    fn trace_on(&mut self, watch: Option<Py<PyAny>>) {
        let watch: Option<Rc<dyn Fn(&serde_json::Value) -> rbsim_core::types::R<()>>> = watch.map(|w| {
            Rc::new(move |e: &serde_json::Value| -> rbsim_core::types::R<()> {
                Python::attach(|py| w.call1(py, (e.to_string(),)).map(|_| ())).map_err(|er| human::stash(er, "watch"))
            }) as Rc<dyn Fn(&serde_json::Value) -> rbsim_core::types::R<()>>
        });
        let sink: Sink = Rc::new(RefCell::new(TraceBuf { events: Vec::new(), watch }));
        for s in Side::BOTH {
            if let Some(a) = self.g.agents[s.idx()].clone() {
                let t: Rc<RefCell<dyn Agent>> = Rc::new(RefCell::new(TraceAgent { inner: a, sink: sink.clone() }));
                self.g.agents[s.idx()] = Some(t);
            }
        }
        if let Some(c) = self.g.chooser.clone() {
            let t: Rc<RefCell<dyn Chooser>> = Rc::new(RefCell::new(TraceChooser { inner: c, sink: sink.clone(), real_loop: self.g.loop_id }));
            self.g.chooser = Some(t);
        }
        self.g.gs.rng.log = Some(Vec::new());
        self.sink = Some(sink);
    }

    /// GameLoop.start(): -> (winner "A" | "B" | "DRAW", turns)
    /// An exception of a callback (`ask`, `watch`) is raised as the same object.
    fn start(&mut self) -> PyResult<(String, i64)> {
        drop(human::take());
        let r = self.g.start();
        let d = match &self.sink {
            Some(s) => self.g.drain_rng(s),
            None => Ok(()),
        };
        if let Some(e) = human::take() {
            return Err(e);
        }
        let r = r.map_err(perr)?;
        d.map_err(perr)?;
        self.winner = Some(r.winner_name().to_string());
        self.turns = r.turns;
        Ok((r.winner_name().to_string(), r.turns))
    }

    /// A segment of a position (consegna1.segment_py): `turns` times the
    /// active player's actions, the end of the turn, the next turn's
    /// beginning. -> the winner if the game ended in it.
    /// An exception of a callback (`ask`, `watch`) is raised as the same object.
    fn run_segment(&mut self, turns: i64) -> PyResult<Option<String>> {
        drop(human::take());
        let r = (|| -> Result<Option<String>, EngineError> {
            for _ in 0..turns {
                if let Some(res) = self.g.run_main_actions()? {
                    return Ok(Some(res.winner_name().to_string()));
                }
                if let Some(res) = self.g.end_turn()? {
                    return Ok(Some(res.winner_name().to_string()));
                }
                if let Some(res) = self.g.begin_turn()? {
                    return Ok(Some(res.winner_name().to_string()));
                }
            }
            Ok(None)
        })();
        let d = match &self.sink {
            Some(s) => self.g.drain_rng(s),
            None => Ok(()),
        };
        if let Some(e) = human::take() {
            return Err(e);
        }
        let r = r.map_err(perr)?;
        d.map_err(perr)?;
        Ok(r)
    }

    /// The trace's events (JSON list).
    fn events(&self) -> String {
        match &self.sink {
            Some(s) => serde_json::Value::Array(s.borrow().events.clone()).to_string(),
            None => "[]".into(),
        }
    }

    /// The units in play, for tests: JSON list of {side, where ("base",
    /// "bf0"...), card, might (unit_might), ready, buffs}; legends too
    /// (where "legend").
    fn units(&self) -> String {
        let gs = &self.g.gs;
        let mut out = Vec::new();
        let mut put = |side: Side, place: String, u: rbsim_core::types::UnitId| {
            let un = gs.unit(u);
            out.push(serde_json::json!({"side": side.name(), "where": place, "card": gs.name(gs.ucard(u)),
                                        "might": gs.unit_might(u), "ready": un.ready, "buffs": un.might_counters}));
        };
        for s in Side::BOTH {
            for &u in &gs.player(s).base_units {
                put(s, "base".into(), u);
            }
            for (i, bf) in gs.battlefields.iter().enumerate() {
                for &u in bf.units_for(s) {
                    put(s, format!("bf{i}"), u);
                }
            }
            if let Some(l) = gs.legend_unit[s.idx()] {
                put(s, "legend".into(), l);
            }
        }
        serde_json::Value::Array(out).to_string()
    }

    /// py: _recompute_passives (tests: the continuous Might of a position).
    fn recompute_passives(&mut self) -> PyResult<()> {
        self.g.recompute_passives().map_err(perr)
    }

    /// The rules profile this game plays (its registry's).
    #[getter]
    fn regole(&self) -> &'static str {
        self.g.gs.reg.regole.name()
    }

    #[getter]
    fn turn(&self) -> i64 {
        self.g.gs.turn
    }
}

/// How many search agents are alive (a finished, dropped game frees its own).
/// D72..D77 counted in this thread since the last reset: {"D72": n, ...}
/// (the corrected branches that changed something, search copies included).
#[pyfunction]
fn correzioni() -> std::collections::BTreeMap<String, u64> {
    let c = rbsim_core::registry::correzioni();
    (0..6).map(|i| (format!("D{}", 72 + i), c[i])).collect()
}

#[pyfunction]
fn azzera_correzioni() {
    rbsim_core::registry::azzera_correzioni();
}

#[pyfunction]
fn live_search_agents() -> i64 {
    rbsim_core::search::live_cores()
}

#[pymodule]
fn riftbound_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(live_search_agents, m)?)?;
    m.add_function(wrap_pyfunction!(correzioni, m)?)?;
    m.add_function(wrap_pyfunction!(azzera_correzioni, m)?)?;
    m.add_class::<Registry>()?;
    m.add_class::<Game>()?;
    Ok(())
}
