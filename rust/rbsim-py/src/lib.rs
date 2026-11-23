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
use rbsim_core::game::Game as CoreGame;
use rbsim_core::registry::Registry as CoreRegistry;
use rbsim_core::trace::{ReplayAgent, ReplayChooser, Sink, TraceAgent, TraceChooser};
use rbsim_core::types::{EngineError, Side};

fn perr(e: EngineError) -> PyErr {
    PyRuntimeError::new_err(e.to_string())
}

fn serr(e: String) -> PyErr {
    PyRuntimeError::new_err(e)
}

#[pyclass(unsendable)]
struct Registry {
    reg: Rc<CoreRegistry>,
}

#[pymethods]
impl Registry {
    #[new]
    fn new(path: &str) -> PyResult<Self> {
        let text = std::fs::read_to_string(path).map_err(|e| serr(e.to_string()))?;
        Ok(Registry { reg: Rc::new(CoreRegistry::from_json(&text).map_err(serr)?) })
    }
    fn __len__(&self) -> usize {
        self.reg.cards.len()
    }
}

#[pyclass(unsendable)]
struct Game {
    g: CoreGame,
    sink: Option<Sink>,
    winner: Option<String>,
    turns: i64,
}

#[pymethods]
impl Game {
    /// py: build_game(game_seed, deck_a_path, deck_b_path, first_player, max_turns)
    #[staticmethod]
    fn build(reg: &Registry, seed: i64, deck_a_json: &str, deck_b_json: &str, first_player: &str, max_turns: i64) -> PyResult<Game> {
        let a = rbsim_core::setup::load_deck(deck_a_json).map_err(serr)?;
        let b = rbsim_core::setup::load_deck(deck_b_json).map_err(serr)?;
        let g = rbsim_core::setup::build_game(reg.reg.clone(), seed, &a, &b, first_player, max_turns).map_err(serr)?;
        Ok(Game { g, sink: None, winner: None, turns: 0 })
    }

    /// A game from a canonical tree (canon.canonical_state), RNG seeded with `seed`.
    #[staticmethod]
    fn from_canonical(reg: &Registry, tree_json: &str, seed: i64) -> PyResult<Game> {
        let tree: serde_json::Value = serde_json::from_str(tree_json).map_err(|e| serr(e.to_string()))?;
        let gs = rbsim_core::import::from_canonical(reg.reg.clone(), &tree, seed as i128).map_err(serr)?;
        Ok(Game { g: CoreGame::new(gs), sink: None, winner: None, turns: 0 })
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

    /// Trace the game (trace_py's events, raw dumps), from now on.
    fn trace_on(&mut self) {
        let sink: Sink = Rc::new(RefCell::new(Vec::new()));
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
    fn start(&mut self) -> PyResult<(String, i64)> {
        let r = self.g.start();
        if let Some(s) = self.sink.clone() {
            self.g.drain_rng(&s);
        }
        let r = r.map_err(perr)?;
        self.winner = Some(r.winner_name().to_string());
        self.turns = r.turns;
        Ok((r.winner_name().to_string(), r.turns))
    }

    /// A segment of a position (consegna1.segment_py): `turns` times the
    /// active player's actions, the end of the turn, the next turn's
    /// beginning. -> the winner if the game ended in it.
    fn run_segment(&mut self, turns: i64) -> PyResult<Option<String>> {
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
        if let Some(s) = self.sink.clone() {
            self.g.drain_rng(&s);
        }
        r.map_err(perr)
    }

    /// The trace's events (JSON list).
    fn events(&self) -> String {
        match &self.sink {
            Some(s) => serde_json::Value::Array(s.borrow().clone()).to_string(),
            None => "[]".into(),
        }
    }

    #[getter]
    fn turn(&self) -> i64 {
        self.g.gs.turn
    }
}

#[pymodule]
fn riftbound_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Registry>()?;
    m.add_class::<Game>()?;
    Ok(())
}
