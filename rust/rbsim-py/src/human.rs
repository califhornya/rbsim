//! A human seat: every decision and every in-move choice of the seat is a
//! question to a Python callable `ask(event_json)`, built by the trace's own
//! builders (rbsim-core trace.rs) without the answer fields. The answer is a
//! Python object of the shape of the missing field; an invalid one raises
//! ValueError out of the game. An exception raised by `ask` (or by the
//! trace's `watch`) is kept here and re-raised, the same object, by the call
//! that was running the game.
//!
//! With `payments` the decision event also carries the ways to pay each move
//! (rbsim-core payment.rs, the page's "Come paghi?") and a decision may be
//! answered with one: the seat then plays the Golds and the move itself, as the
//! page's `CoachAgent._coached` / `_gold_step` do, asking nothing for the steps
//! after the first (they still reach the trace as decisions and choices).

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyList, PyTuple};
use std::cell::RefCell;

use rbsim_core::agent::{AIdx, AKind, Action, Agent, Point};
use rbsim_core::game::Game;
use rbsim_core::model::Opt;
use rbsim_core::payment::{gold_action, gold_only_plays, golds_of, payment_options, GoldOnly, PayWay};
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
    /// Add the ways to pay to the decision event and accept `via` answers.
    pub payments: bool,
    /// A move paid with Golds (py: CoachAgent._gold_plan): the Golds first, then the move.
    plan: Option<Plan>,
    /// The domains the Golds just used Add, answered to the next "which domain"
    /// choice of the seat, newest first (py: the _GoldDomain choosers).
    gold_domains: Vec<Domain>,
}

struct Plan {
    left: i64,
    domain: Option<Domain>,
    prefer: Option<Domain>,
    action: Action,
    point: Point,
}

/// What a decision's answer says.
enum Answer {
    /// A move of the menu or an action list, played as the engine pays.
    Act(Action),
    /// A move paid with a way (a menu move, or a gold-only play).
    Via(Action, PayWay),
}

/// A way as the event carries it (py: a `payment_options` dict, no `text`).
fn way_json(w: &PayWay) -> Value {
    json!({"golds": w.golds, "gold_domain": w.gold_domain.map(|d| d.name()), "prefer": w.prefer.map(|d| d.name()),
           "recycled": w.recycled.iter().map(|(d, n)| json!([d.name(), n])).collect::<Vec<_>>()})
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
    pub fn new(ask: Py<PyAny>, real_loop: u64, payments: bool) -> HumanAgent {
        HumanAgent { ask, real_loop, payments, plan: None, gold_domains: Vec::new() }
    }

    /// Ask with `e`, parse the answer with `parse`; any Python error is kept.
    fn query<T>(&self, e: &Value, what: &str, parse: impl FnOnce(&Bound<'_, PyAny>) -> PyResult<T>) -> R<T> {
        Python::attach(|py| -> PyResult<T> {
            let r = self.ask.bind(py).call1((e.to_string(),))?;
            parse(&r)
        })
        .map_err(|er| stash(er, what))
    }

    /// py: CoachAgent._gold_step: the next step of a card paid with Golds: a
    /// Gold (Adding the domain the card needs), then the card. None: the plan
    /// is over or no longer possible (the decision is asked as usual).
    fn gold_step(&mut self, g: &mut Game, side: Side, point: Point, legal: &[Action]) -> R<Option<Action>> {
        let Some(plan) = self.plan.as_mut() else { return Ok(None) };
        if plan.point != point {
            self.plan = None;
            return Ok(None);
        }
        let lanes = golds_of(g, side, point).unwrap_or_default();
        let gold = lanes.first().map(|&l| gold_action(l));
        if let Some(gold) = gold {
            if plan.left > 0 {
                if let Some(a) = legal.iter().find(|a| a.same(&gold)) {
                    plan.left -= 1;
                    if let Some(d) = plan.domain {
                        self.gold_domains.insert(0, d);
                    }
                    return Ok(Some(a.clone()));
                }
            }
        }
        let plan = self.plan.take().unwrap();
        let Some(a) = legal.iter().find(|a| a.same(&plan.action)) else { return Ok(None) };
        if let Some(d) = plan.prefer {
            g.recycle_first = Some((side, d));
        }
        Ok(Some(a.clone()))
    }

    fn menu(&mut self, g: &mut Game, side: Side, point: Point) -> R<Action> {
        g.recycle_first = None; // py: _coached: a [rune] domain chosen for a move is for that move only
        self.gold_domains.clear();
        let (mut e, legal) = decision_event_for(g, side, point)?;
        if self.plan.is_some() {
            if let Some(a) = self.gold_step(g, side, point, &legal)? {
                return Ok(a);
            }
        }
        let n = legal.len();
        // The ways to pay (py: payment_options; only where the page would offer a choice: more than one).
        let mut pay: Vec<Option<Vec<PayWay>>> = vec![None; n];
        let mut solo: Vec<GoldOnly> = Vec::new();
        if self.payments {
            if n > 1 {
                for (i, a) in legal.iter().enumerate() {
                    let ways = payment_options(g, side, point, a);
                    if ways.len() > 1 {
                        pay[i] = Some(ways);
                    }
                }
                solo = gold_only_plays(g, side, point, &legal);
            }
            e["pay"] = Value::Array(
                pay.iter().map(|w| w.as_ref().map_or(Value::Null, |w| Value::Array(w.iter().map(way_json).collect()))).collect(),
            );
            e["gold_only"] = Value::Array(
                solo.iter()
                    .map(|s| json!({"action": rbsim_core::trace::action_list(&s.action),
                                    "ways": s.ways.iter().map(way_json).collect::<Vec<_>>()}))
                    .collect(),
            );
        }
        let payments = self.payments;
        // An int indexes the menu; None is a Pass when the menu is empty; a
        // list is the trace's `action` field, played as is; {"index": i, "via":
        // w} / {"solo_gold": j, "via": w} pay with a way (see set_human_agent).
        let ans = self.query(&e, "ask", |r| {
            if r.is_instance_of::<PyDict>() {
                if !payments {
                    return Err(bad("decision: a `via` answer needs set_human_agent(..., payments=True)".into()));
                }
                return via_of(r, &legal, &pay, &solo);
            }
            if r.is_instance_of::<PyList>() || r.is_instance_of::<PyTuple>() {
                return action_of(r).map(Answer::Act);
            }
            if n == 0 && r.is_none() {
                return Ok(Answer::Act(Action::pass()));
            }
            index_of(r, n, "decision").map(|i| Answer::Act(legal[i].clone()))
        })?;
        Ok(match ans {
            Answer::Act(a) => a,
            Answer::Via(a, w) if w.golds == 0 => {
                if let Some(d) = w.prefer {
                    g.recycle_first = Some((side, d));
                }
                a
            }
            Answer::Via(a, w) => {
                // py: _gold_plan, then _gold_step for the first Gold
                self.plan = Some(Plan { left: w.golds, domain: w.gold_domain, prefer: w.prefer, action: a, point });
                match self.gold_step(g, side, point, &legal)? {
                    Some(step) => step,
                    None => return self.menu_again(g, side, point),
                }
            }
        })
    }

    /// py: a plan that is not possible after all: the decision is asked again.
    fn menu_again(&mut self, g: &mut Game, side: Side, point: Point) -> R<Action> {
        self.menu(g, side, point)
    }
}

/// {"index": i, "via": w} or {"solo_gold": j, "via": w}.
fn via_of(r: &Bound<'_, PyAny>, legal: &[Action], pay: &[Option<Vec<PayWay>>], solo: &[GoldOnly]) -> PyResult<Answer> {
    let d = r.cast::<PyDict>()?;
    let get = |k: &str| d.get_item(k);
    let via = get("via")?.ok_or_else(|| bad("decision: a dict answer needs `via`".into()))?;
    let w = int_of(&via, "decision: via")?;
    let (index, solo_j) = (get("index")?, get("solo_gold")?);
    if d.len() != 2 || index.is_some() == solo_j.is_some() {
        return Err(bad("decision: the dict answer is {\"index\": i, \"via\": w} or {\"solo_gold\": j, \"via\": w}".into()));
    }
    let (action, ways): (&Action, &[PayWay]) = match (index, solo_j) {
        (Some(i), _) => {
            let i = index_of(&i, legal.len(), "decision: index")?;
            match &pay[i] {
                Some(ways) => (&legal[i], ways.as_slice()),
                None => return Err(bad(format!("decision: menu action {i} has no ways to choose from"))),
            }
        }
        (_, Some(j)) => {
            let j = index_of(&j, solo.len(), "decision: solo_gold")?;
            (&solo[j].action, solo[j].ways.as_slice())
        }
        _ => unreachable!(),
    };
    if w < 0 || w as usize >= ways.len() {
        return Err(bad(format!("decision: via {w} is not in 0..{}", ways.len())));
    }
    Ok(Answer::Via(action.clone(), ways[w as usize].clone()))
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
        // py: _GoldDomain: the domain a Gold just used Adds answers the seat's next "which domain".
        if kind.starts_with("domain") {
            for k in 0..self.gold_domains.len() {
                if let Some(i) = options.iter().position(|o| *o == Opt::Domain(self.gold_domains[k])) {
                    self.gold_domains.remove(k);
                    return Ok(Some(i));
                }
            }
        }
        let e = choice_event(g, kind, side, options, default, source, self.real_loop);
        let n = options.len();
        let what = format!("choice {kind}");
        self.query(&e, "ask", |r| index_of(r, n, &what).map(Some))
    }
}
