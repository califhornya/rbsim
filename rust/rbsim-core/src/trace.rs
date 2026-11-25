//! The trace of a Rust game in the format of riftbound/rs/trace_py.py (raw
//! dumps instead of digests: Python canonicalizes both engines' trees), and
//! an agent / chooser that replay a Python trace, checking each recorded
//! option against the Rust menu before taking it.

use serde_json::{json, Value};
use std::cell::RefCell;
use std::collections::VecDeque;
use std::rc::Rc;

use crate::agent::{AIdx, Action, Agent, Chooser, Point};
use crate::game::Game;
use crate::model::Opt;
use crate::types::*;

/// The trace's events, and the live observer (`trace_on(watch)`) each event
/// is also passed to, complete, in the order it is recorded.
#[derive(Default)]
pub struct TraceBuf {
    pub events: Vec<Value>,
    pub watch: Option<Rc<dyn Fn(&Value) -> R<()>>>,
}

pub type Sink = Rc<RefCell<TraceBuf>>;

/// Record an event and show it to the observer; an error of the observer stops the game.
pub fn push_event(sink: &Sink, e: Value) -> R<()> {
    let mut b = sink.borrow_mut();
    b.events.push(e);
    match b.watch.clone() {
        Some(w) => w(b.events.last().unwrap()),
        None => Ok(()),
    }
}

/// A decision's event up to the question (k, seat, point, win, state_raw,
/// obs, menu) and its menu; the answer fields come with `finish_decision`.
/// The human seat is asked with this event.
pub fn decision_event(g: &mut Game, side: Side, point: Point) -> R<(Value, Vec<Action>)> {
    let win = g.window();
    let st = g.raw_dump();
    let legal = g.legal_actions(point, side)?;
    let labels: Vec<String> = legal.iter().map(|a| a.label.clone()).collect();
    let mut e = json!({"k": "decision", "seat": side.name(), "point": point.name(), "win": win,
        "state_raw": st, "obs": null, "menu": labels});
    add_correzioni(g, &mut e);
    Ok((e, legal))
}

thread_local! {
    /// The decision event a TraceAgent built for a seat that wants it.
    static PREBUILT: RefCell<Option<(Side, Point, Value, Vec<Action>)>> = const { RefCell::new(None) };
}

/// `decision_event` for the agent being asked: under a TraceAgent the event it
/// built just before (the menu's legal_actions notes control, so a second
/// build would differ), otherwise a fresh one.
pub fn decision_event_for(g: &mut Game, side: Side, point: Point) -> R<(Value, Vec<Action>)> {
    if let Some((s, p, e, l)) = PREBUILT.with(|c| c.borrow_mut().take()) {
        if s == side && p == point {
            return Ok((e, l));
        }
    }
    decision_event(g, side, point)
}

fn add_correzioni(g: &Game, e: &mut Value) {
    if g.gs.reg.regole.corrette() {
        // D72..D77 counted so far in this thread, the decision's search included.
        e["correzioni"] = json!(crate::registry::correzioni());
    }
}

/// Adds the answer fields to a decision's event.
pub fn finish_decision(g: &Game, e: &mut Value, act: &Action, idx: Option<usize>) {
    e["action"] = action_list(act);
    e["index"] = json!(idx);
    add_correzioni(g, e);
}

/// An optional / mulligan / mode / predict_recycle event up to the question
/// (k, seat, win, state_raw, args); `out` comes with the answer.
pub fn simple_event(g: &Game, side: Side, name: &str, args: Value) -> Value {
    json!({"k": name, "seat": side.name(), "win": g.real_window(), "state_raw": g.real_dump_for_trace(), "args": args})
}

/// A choice's event up to the question (everything but `chosen` and `by`).
pub fn choice_event(g: &Game, kind: &str, side: Side, options: &[Opt], default: usize, source: Option<CardId>,
                    real_loop: u64) -> Value {
    let opts: Vec<Value> = options.iter().map(|o| g.raw_opt(o)).collect();
    let src = source.map(|c| g.raw_opt(&Opt::Card(c))).unwrap_or(Value::Null);
    json!({"k": "choice", "seat": side.name(), "kind": kind, "options_raw": opts, "default": default,
        "declaring": g.loop_id != real_loop, "source_raw": src, "state_raw": g.real_dump_for_trace()})
}

pub fn action_list(a: &Action) -> Value {
    let idx = match &a.index {
        AIdx::None => Value::Null,
        AIdx::Int(i) => json!(i),
        AIdx::Str(s) => json!(s),
    };
    let mut v = vec![json!(a.kind.name()), idx, a.lane.map(|l| json!(l)).unwrap_or(Value::Null)];
    if a.len4 {
        v.push(a.dst.map(|d| json!(d)).unwrap_or(Value::Null));
    }
    Value::Array(v)
}

impl Game {
    /// Trace's "win": the window a decision is taken in.
    pub fn window(&self) -> Value {
        let gs = &self.gs;
        json!({"turn": gs.turn, "active": gs.active.name(), "chain": gs.chain.len(),
               "showdown": if gs.showdown_active { gs.showdown_bf_idx.map(|b| json!(b)).unwrap_or(Value::Null) } else { Value::Null },
               "focus": gs.focus_player.map(|s| s.name()), "pending_move": gs.pending_move.map(|(b, s)| json!([b, s.name()])),
               "points": [gs.points[0], gs.points[1]]})
    }

    /// The window of the real game (a declaration's copy asks its players).
    pub fn real_window(&self) -> Value {
        match self.real {
            // SAFETY: see Game::real_gs.
            Some(p) => Game::new(unsafe { (*p).clone() }).window(),
            None => self.window(),
        }
    }

    /// Move the real game's RNG draws into the trace.
    pub fn drain_rng(&mut self, sink: &Sink) -> R<()> {
        if self.real.is_some() {
            return Ok(());
        }
        let draws: Vec<(u64, u64)> = match self.gs.rng.log.as_mut() {
            Some(l) => l.drain(..).collect(),
            None => Vec::new(),
        };
        for (n, r) in draws {
            push_event(sink, json!({"k": "rng", "op": "randbelow", "n": n, "r": r}))?;
        }
        Ok(())
    }
}

/// Wraps a seat's agent: records each decision as trace_py does.
pub struct TraceAgent {
    pub inner: Rc<RefCell<dyn Agent>>,
    pub sink: Sink,
}

impl TraceAgent {
    fn menu(&self, g: &mut Game, side: Side, point: Point, f: impl FnOnce(&mut Game) -> R<Action>) -> R<Action> {
        let (mut e, legal) = decision_event(g, side, point)?;
        let wants = self.inner.borrow().wants_event();
        if wants {
            PREBUILT.with(|c| *c.borrow_mut() = Some((side, point, e.clone(), legal.clone())));
        }
        let act = f(g);
        if wants {
            PREBUILT.with(|c| *c.borrow_mut() = None);
        }
        let act = act?;
        let idx = legal.iter().position(|a| a.same(&act));
        g.drain_rng(&self.sink)?;
        finish_decision(g, &mut e, &act, idx);
        push_event(&self.sink, e)?;
        Ok(act)
    }
    fn simple(&self, g: &mut Game, mut e: Value, out: Value) -> R<()> {
        g.drain_rng(&self.sink)?;
        e["out"] = out;
        push_event(&self.sink, e)
    }
}

impl Agent for TraceAgent {
    fn decide_action(&mut self, g: &mut Game, side: Side, cp: i64) -> R<Action> {
        let inner = self.inner.clone();
        self.menu(g, side, Point::TurnAction, |g| inner.borrow_mut().decide_action(g, side, cp))
    }
    fn decide_reaction(&mut self, g: &mut Game, side: Side) -> R<Action> {
        let inner = self.inner.clone();
        self.menu(g, side, Point::Reaction, |g| inner.borrow_mut().decide_reaction(g, side))
    }
    fn decide_showdown_action(&mut self, g: &mut Game, side: Side, bf: usize) -> R<Action> {
        let inner = self.inner.clone();
        self.menu(g, side, Point::ShowdownAction, |g| inner.borrow_mut().decide_showdown_action(g, side, bf))
    }
    fn decide_mulligan(&mut self, g: &mut Game, side: Side) -> R<Vec<i64>> {
        let e = simple_event(g, side, "decide_mulligan", json!([]));
        let out = self.inner.borrow_mut().decide_mulligan(g, side)?;
        self.simple(g, e, json!(out))?;
        Ok(out)
    }
    fn decide_optional(&mut self, g: &mut Game, side: Side, card: CardId, name: &str) -> R<bool> {
        let c = g.raw_opt(&Opt::Card(card));
        let e = simple_event(g, side, "decide_optional", json!([c, name]));
        let out = self.inner.borrow_mut().decide_optional(g, side, card, name)?;
        self.simple(g, e, json!(out))?;
        Ok(out)
    }
    fn decide_mode(&mut self, g: &mut Game, side: Side, card: CardId, n: i64) -> R<Option<i64>> {
        let c = g.raw_opt(&Opt::Card(card));
        let e = simple_event(g, side, "decide_mode", json!([c, n]));
        let out = self.inner.borrow_mut().decide_mode(g, side, card, n)?;
        self.simple(g, e, json!(out))?;
        Ok(out)
    }
    fn decide_predict_recycle(&mut self, g: &mut Game, side: Side, card: CardId) -> R<bool> {
        let c = g.raw_opt(&Opt::Card(card));
        let e = simple_event(g, side, "decide_predict_recycle", json!([c]));
        let out = self.inner.borrow_mut().decide_predict_recycle(g, side, card)?;
        self.simple(g, e, json!(out))?;
        Ok(out)
    }
    fn inner(&mut self, g: &mut Game, kind: &str, side: Side, options: &[Opt], default: usize, source: Option<CardId>)
             -> R<Option<usize>> {
        self.inner.borrow_mut().inner(g, kind, side, options, default, source)
    }
    fn has(&self, method: &str) -> bool {
        self.inner.borrow().has(method)
    }
    fn wants_event(&self) -> bool {
        self.inner.borrow().wants_event()
    }
}

/// Wraps the loop's chooser: records each choice as trace_py does.
pub struct TraceChooser {
    pub inner: Rc<RefCell<dyn Chooser>>,
    pub sink: Sink,
    pub real_loop: u64,
}

impl Chooser for TraceChooser {
    fn choose(&mut self, g: &mut Game, kind: &str, side: Side, options: &[Opt], default: usize, source: Option<CardId>)
              -> R<Option<usize>> {
        let mut e = choice_event(g, kind, side, options, default, source, self.real_loop);
        let i = self.inner.borrow_mut().choose(g, kind, side, options, default, source)?;
        e["chosen"] = json!(i.unwrap_or(default));
        e["by"] = json!(if i.is_none() { "base" } else { "agent" });
        push_event(&self.sink, e)?;
        Ok(i)
    }
}

impl Game {
    /// The real game's dump (trace_py dumps the traced gs, not a copy).
    pub fn real_dump_for_trace(&self) -> Value {
        match self.real {
            Some(p) => {
                // SAFETY: see Game::real_gs.
                let gs: &crate::model::GameState = unsafe { &*p };
                let tmp = Game::new(gs.clone());
                tmp.raw_dump()
            }
            None => self.raw_dump(),
        }
    }
}

/// Plays back the decisions of a Python trace (one queue per seat).
pub struct ReplayAgent {
    pub events: VecDeque<Value>,
    pub has_optional: bool,
}

impl ReplayAgent {
    fn next(&mut self, k: &str) -> R<Value> {
        let e = self.events.pop_front().ok_or_else(|| EngineError::Agent(format!("replay: no more events, wanted {k}")))?;
        if e["k"] != k {
            return Err(EngineError::Agent(format!("replay: wanted {k}, trace has {}", e["k"])));
        }
        Ok(e)
    }
    fn pick(&mut self, g: &mut Game, side: Side, point: Point) -> R<Action> {
        let e = self.next("decision")?;
        let legal = g.legal_actions(point, side)?;
        let labels: Vec<String> = legal.iter().map(|a| a.label.clone()).collect();
        let want: Vec<String> = e["menu"].as_array().map(|a| a.iter().map(|x| x.as_str().unwrap_or("").to_string()).collect()).unwrap_or_default();
        if labels != want {
            return Err(EngineError::Agent(format!("replay: menu differs at {}: rust {labels:?} python {want:?}", e["i"])));
        }
        match e["index"].as_u64() {
            Some(i) if (i as usize) < legal.len() => Ok(legal[i as usize].clone()),
            Some(i) => Err(EngineError::Agent(format!("replay: index {i} not legal"))),
            None => {
                // An action not in the menu (a PASS outside it, or a no-op).
                let a = &e["action"];
                Ok(Action::new(
                    crate::agent::AKind::from_name(a[0].as_str().unwrap_or("PASS")).unwrap(),
                    match &a[1] {
                        Value::Null => AIdx::None,
                        Value::String(s) => AIdx::Str(s.clone()),
                        v => AIdx::Int(v.as_i64().unwrap_or(0)),
                    },
                    a[2].as_i64(),
                    a.get(3).and_then(|v| v.as_i64()),
                    String::new(),
                ))
            }
        }
    }
}

impl Agent for ReplayAgent {
    fn decide_action(&mut self, g: &mut Game, side: Side, _cp: i64) -> R<Action> {
        self.pick(g, side, Point::TurnAction)
    }
    fn decide_reaction(&mut self, g: &mut Game, side: Side) -> R<Action> {
        self.pick(g, side, Point::Reaction)
    }
    fn decide_showdown_action(&mut self, g: &mut Game, side: Side, _bf: usize) -> R<Action> {
        self.pick(g, side, Point::ShowdownAction)
    }
    fn decide_mulligan(&mut self, _g: &mut Game, _side: Side) -> R<Vec<i64>> {
        let e = self.next("decide_mulligan")?;
        Ok(e["out"].as_array().map(|a| a.iter().filter_map(|x| x.as_i64()).collect()).unwrap_or_default())
    }
    fn decide_optional(&mut self, _g: &mut Game, _side: Side, _card: CardId, _name: &str) -> R<bool> {
        Ok(self.next("decide_optional")?["out"].as_bool().unwrap_or(true))
    }
    fn decide_mode(&mut self, _g: &mut Game, _side: Side, _card: CardId, _n: i64) -> R<Option<i64>> {
        Ok(self.next("decide_mode")?["out"].as_i64())
    }
    fn decide_predict_recycle(&mut self, _g: &mut Game, _side: Side, _card: CardId) -> R<bool> {
        Ok(self.next("decide_predict_recycle")?["out"].as_bool().unwrap_or(false))
    }
    fn has(&self, method: &str) -> bool {
        match method {
            "decide_optional" | "decide_mode" | "decide_predict_recycle" => self.has_optional,
            _ => true,
        }
    }
}

/// A seat scripted by label prefixes (positions in tests; py: the Scripted
/// of tests/audit/audit_helpers.py): at each decision of a point the next
/// entry of its script, PASS once it runs out. An entry that isn't legal is
/// an error naming the menu. Optional decisions keep the engine's baseline.
pub struct ScriptAgent {
    /// main, showdown, reaction
    pub scripts: [VecDeque<String>; 3],
}

impl ScriptAgent {
    fn pick(&mut self, g: &mut Game, side: Side, point: Point, i: usize) -> R<Action> {
        let legal = g.legal_actions(point, side)?;
        let pass = || Action::new(crate::agent::AKind::from_name("PASS").unwrap(), AIdx::None, None, None, String::new());
        match self.scripts[i].pop_front() {
            None => Ok(pass()),
            Some(w) if w == "PASS" => Ok(pass()),
            Some(w) => legal.iter().find(|a| a.label.starts_with(&w)).cloned().ok_or_else(|| {
                let labels: Vec<&str> = legal.iter().map(|a| a.label.as_str()).collect();
                EngineError::Agent(format!("script: {w:?} is not legal: {labels:?}"))
            }),
        }
    }
}

impl Agent for ScriptAgent {
    fn decide_action(&mut self, g: &mut Game, side: Side, _cp: i64) -> R<Action> {
        self.pick(g, side, Point::TurnAction, 0)
    }
    fn decide_showdown_action(&mut self, g: &mut Game, side: Side, _bf: usize) -> R<Action> {
        self.pick(g, side, Point::ShowdownAction, 1)
    }
    fn decide_reaction(&mut self, g: &mut Game, side: Side) -> R<Action> {
        self.pick(g, side, Point::Reaction, 2)
    }
    fn decide_mulligan(&mut self, _g: &mut Game, _side: Side) -> R<Vec<i64>> {
        Ok(Vec::new())
    }
    fn decide_optional(&mut self, _g: &mut Game, _side: Side, _card: CardId, _name: &str) -> R<bool> {
        Ok(true)
    }
    fn decide_mode(&mut self, _g: &mut Game, _side: Side, _card: CardId, _n: i64) -> R<Option<i64>> {
        Ok(None)
    }
    fn decide_predict_recycle(&mut self, _g: &mut Game, _side: Side, _card: CardId) -> R<bool> {
        Ok(false)
    }
    fn has(&self, method: &str) -> bool {
        !matches!(method, "decide_optional" | "decide_mode" | "decide_predict_recycle")
    }
}

/// Plays back the chooser's answers of a Python trace.
pub struct ReplayChooser {
    pub events: VecDeque<Value>,
}

impl Chooser for ReplayChooser {
    fn choose(&mut self, g: &mut Game, kind: &str, _side: Side, options: &[Opt], _default: usize, _source: Option<CardId>)
              -> R<Option<usize>> {
        let e = self.events.pop_front().ok_or_else(|| EngineError::Agent(format!("replay: no more choices, wanted {kind}")))?;
        if e["kind"] != kind {
            return Err(EngineError::Agent(format!("replay: choice {kind}, trace has {}", e["kind"])));
        }
        if e["options"].as_array().map(|a| a.len()) != Some(options.len()) {
            let names: Vec<String> = options.iter().map(|o| match o {
                Opt::Unit(u) => format!("unit {}@{:?}", g.gs.name(g.gs.unit(*u).card), g.locate_unit(*u)),
                Opt::Card(c) => format!("card {}", g.gs.name(*c)),
                x => format!("{x:?}"),
            }).collect();
            return Err(EngineError::Agent(format!("replay: choice {kind}: {} options {names:?}, trace {}", options.len(), e["options"])));
        }
        if e["by"] == "agent" {
            // py: the PPO agent's question builds an Observation of the real
            // game (also on a declaration's copy), whose bf.control() notes
            // control (rbsim-py ppo.rs does the same).
            let real: &mut Game = match g.real_game {
                // SAFETY: as in ppo.rs, the real game's frame runs this copy.
                Some(p) => unsafe { &mut *p },
                None => g,
            };
            for i in 0..real.gs.battlefields.len() {
                real.gs.battlefields[i].control();
            }
            Ok(e["chosen"].as_u64().map(|x| x as usize))
        } else {
            Ok(None)
        }
    }
}
