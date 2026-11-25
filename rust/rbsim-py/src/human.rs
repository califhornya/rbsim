//! A human seat: every decision and every in-move choice of the seat is a
//! question to a Python callable `ask(event_json)`, built by the trace's own
//! builders (rbsim-core trace.rs) without the answer fields. The answer is a
//! Python object of the shape of the missing field; an invalid one raises
//! ValueError out of the game. An exception raised by `ask` (or by the
//! trace's `watch`) is kept here and re-raised, the same object, by the call
//! that was running the game.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyList, PyTuple};
use std::cell::RefCell;

use rbsim_core::agent::{AIdx, AKind, Action, Agent, Point};
use rbsim_core::game::Game;
use rbsim_core::model::Opt;
use rbsim_core::trace::{choice_event, decision_event_for, simple_event};
use rbsim_core::types::*;
use serde_json::{json, Value};

thread_local! {
    /// The first Python exception raised in a callback of the running game.
    static PENDING: RefCell<Option<PyErr>> = const { RefCell::new(None) };
}

/// Keep a Python exception and give the engine the error that stops the game
/// (an agent error: a handler's `except Exception` does not swallow it).
pub fn stash(e: PyErr, what: &str) -> EngineError {
    PENDING.with(|p| {
        let mut p = p.borrow_mut();
        if p.is_none() {
            *p = Some(e);
        }
    });
    EngineError::Agent(format!("{what}: Python exception"))
}

/// The exception kept by a callback, if any (clears it).
pub fn take() -> Option<PyErr> {
    PENDING.with(|p| p.borrow_mut().take())
}

pub struct HumanAgent {
    /// ask(event_json: str) -> the answer
    pub ask: Py<PyAny>,
    /// The loop the trace calls real (a choice on a copy is "declaring").
    pub real_loop: u64,
}

fn bad(msg: String) -> PyErr {
    PyValueError::new_err(msg)
}

/// An int that is not a bool.
fn int_of(o: &Bound<'_, PyAny>, what: &str) -> PyResult<i64> {
    if o.is_instance_of::<PyBool>() {
        return Err(bad(format!("{what}: a bool is not an int")));
    }
    o.extract::<i64>().map_err(|_| bad(format!("{what}: expected an int, got {}", o.repr().map(|r| r.to_string()).unwrap_or_default())))
}

fn bool_of(o: &Bound<'_, PyAny>, what: &str) -> PyResult<bool> {
    if !o.is_instance_of::<PyBool>() {
        return Err(bad(format!("{what}: expected a bool, got {}", o.repr().map(|r| r.to_string()).unwrap_or_default())));
    }
    o.extract::<bool>()
}

fn index_of(o: &Bound<'_, PyAny>, n: usize, what: &str) -> PyResult<usize> {
    let i = int_of(o, what)?;
    if i < 0 || i as usize >= n {
        return Err(bad(format!("{what}: {i} is not in 0..{n}")));
    }
    Ok(i as usize)
}

impl HumanAgent {
    /// Ask with `e`, parse the answer with `parse`; any Python error is kept.
    fn query<T>(&self, e: &Value, what: &str, parse: impl FnOnce(&Bound<'_, PyAny>) -> PyResult<T>) -> R<T> {
        Python::attach(|py| -> PyResult<T> {
            let r = self.ask.bind(py).call1((e.to_string(),))?;
            parse(&r)
        })
        .map_err(|er| stash(er, what))
    }

    fn menu(&self, g: &mut Game, side: Side, point: Point) -> R<Action> {
        let (e, legal) = decision_event_for(g, side, point)?;
        let n = legal.len();
        // An int indexes the menu; None is a Pass when the menu is empty; a
        // list is the trace's `action` field, played as is (see set_human_agent).
        let act = self.query(&e, "ask", |r| {
            if r.is_instance_of::<PyList>() || r.is_instance_of::<PyTuple>() {
                return action_of(r);
            }
            if n == 0 && r.is_none() {
                return Ok(Action::pass());
            }
            index_of(r, n, "decision").map(|i| legal[i].clone())
        })?;
        Ok(act)
    }
}

/// An action from the trace's `action` shape: [kind, index, lane(, dst)].
fn action_of(r: &Bound<'_, PyAny>) -> PyResult<Action> {
    let v: Vec<Bound<'_, PyAny>> = r.try_iter()?.collect::<PyResult<_>>()?;
    if v.len() != 3 && v.len() != 4 {
        return Err(bad("decision: an action is [kind, index, lane] or [kind, index, lane, dst]".into()));
    }
    let kind = v[0].extract::<String>().ok().and_then(|k| AKind::from_name(&k))
        .ok_or_else(|| bad("decision: unknown action kind".into()))?;
    let index = if v[1].is_none() {
        AIdx::None
    } else if let Ok(s) = v[1].extract::<String>() {
        AIdx::Str(s)
    } else {
        AIdx::Int(int_of(&v[1], "decision: action index")?)
    };
    let opt = |o: &Bound<'_, PyAny>, what: &str| -> PyResult<Option<i64>> {
        if o.is_none() { Ok(None) } else { int_of(o, what).map(Some) }
    };
    let lane = opt(&v[2], "decision: action lane")?;
    let dst = if v.len() == 4 { opt(&v[3], "decision: action dst")? } else { None };
    let mut a = Action::new(kind, index, lane, dst, String::new());
    a.len4 = v.len() == 4;
    Ok(a)
}

impl Agent for HumanAgent {
    fn wants_event(&self) -> bool {
        true
    }
    fn decide_action(&mut self, g: &mut Game, side: Side, _cards_played: i64) -> R<Action> {
        self.menu(g, side, Point::TurnAction)
    }
    fn decide_reaction(&mut self, g: &mut Game, side: Side) -> R<Action> {
        self.menu(g, side, Point::Reaction)
    }
    fn decide_showdown_action(&mut self, g: &mut Game, side: Side, _bf_idx: usize) -> R<Action> {
        self.menu(g, side, Point::ShowdownAction)
    }
    fn decide_mulligan(&mut self, g: &mut Game, side: Side) -> R<Vec<i64>> {
        let e = simple_event(g, side, "decide_mulligan", json!([]));
        let hand = g.gs.player(side).hand.len();
        self.query(&e, "ask", |r| {
            let items: Vec<Bound<'_, PyAny>> = r
                .try_iter()
                .map_err(|_| bad("decide_mulligan: expected a list of hand indices".into()))?
                .collect::<PyResult<_>>()?;
            if items.len() > 2 {
                return Err(bad("decide_mulligan: at most 2 cards".into()));
            }
            let mut out: Vec<i64> = Vec::new();
            for it in &items {
                let i = index_of(it, hand, "decide_mulligan")? as i64;
                if out.contains(&i) {
                    return Err(bad(format!("decide_mulligan: {i} twice")));
                }
                out.push(i);
            }
            Ok(out)
        })
    }
    fn decide_optional(&mut self, g: &mut Game, side: Side, card: CardId, name: &str) -> R<bool> {
        let c = g.raw_opt(&Opt::Card(card));
        let e = simple_event(g, side, "decide_optional", json!([c, name]));
        self.query(&e, "ask", |r| bool_of(r, "decide_optional"))
    }
    fn decide_mode(&mut self, g: &mut Game, side: Side, card: CardId, n: i64) -> R<Option<i64>> {
        let c = g.raw_opt(&Opt::Card(card));
        let e = simple_event(g, side, "decide_mode", json!([c, n]));
        self.query(&e, "ask", |r| {
            if r.is_none() {
                return Ok(None);
            }
            index_of(r, n.max(0) as usize, "decide_mode").map(|i| Some(i as i64))
        })
    }
    fn decide_predict_recycle(&mut self, g: &mut Game, side: Side, card: CardId) -> R<bool> {
        let c = g.raw_opt(&Opt::Card(card));
        let e = simple_event(g, side, "decide_predict_recycle", json!([c]));
        self.query(&e, "ask", |r| bool_of(r, "decide_predict_recycle"))
    }
    fn inner(&mut self, g: &mut Game, kind: &str, side: Side, options: &[Opt], default: usize,
             source: Option<CardId>) -> R<Option<usize>> {
        let e = choice_event(g, kind, side, options, default, source, self.real_loop);
        let n = options.len();
        let what = format!("choice {kind}");
        self.query(&e, "ask", |r| index_of(r, n, &what).map(Some))
    }
}
