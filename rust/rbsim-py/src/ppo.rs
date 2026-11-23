//! The PPO agent on the Rust engine (py: ai/ppo/agent.py PPOAgent): Rust
//! builds the question (the real game's observation and turn, the menu's
//! descriptors, the context), Python's `ask` does the net's forward, the
//! sampling with the agent's torch generator and the record
//! (riftbound/rs/agent_rs.py AskPPO). A menu with fewer than two options is
//! not a decision: no call, no draw.

use numpy::{PyArray1, PyArrayMethods};
use pyo3::prelude::*;
use std::collections::BTreeMap;

use rbsim_core::agent::{Action, Agent, Point};
use rbsim_core::features::{self as F, Descriptor};
use rbsim_core::game::Game;
use rbsim_core::model::Opt;
use rbsim_core::obs::{encode_observation, Observation};
use rbsim_core::types::*;

pub struct PpoAgent {
    /// py: AskPPO(net, sample, seed, record): (x, q, src, ctx, otype, ocards, ofeats, turn) -> int
    pub ask: Py<PyAny>,
    pub side: Side,
    /// py: PPOAgent.counts (a Counter)
    pub counts: BTreeMap<String, i64>,
    /// py: PPOAgent._many = (key, made); key = (id(loop), kind, id(source))
    many: (Option<(u64, String, Option<CardId>)>, i64),
}

impl PpoAgent {
    pub fn new(ask: Py<PyAny>, side: Side) -> PpoAgent {
        PpoAgent { ask, side, counts: BTreeMap::new(), many: (None, 0) }
    }

    fn count(&mut self, k: &str, n: i64) {
        *self.counts.entry(k.to_string()).or_insert(0) += n;
    }

    /// py: PPOAgent._ask(question, descs, source, ctx)
    fn ask(&mut self, g: &mut Game, question: &str, descs: &[Descriptor], source: Option<CardId>,
           ctx: Option<[f32; F::F_CTX]>) -> R<usize> {
        self.count(question, 1);
        if descs.len() < 2 {
            return Ok(0);
        }
        self.count("decisioni", 1);
        self.count("opzioni", descs.len() as i64);
        self.count("opzioni sconosciute", descs.iter().filter(|d| d.unknown()).count() as i64);
        let src_name = source.map(|c| g.gs.name(c).to_string());
        // The real game's state and turn, also asked on a declaration's copy.
        let real: &mut Game = match g.real_game {
            // SAFETY: the real game's frame runs this copy and does not use the
            // game meanwhile.
            Some(p) => unsafe { &mut *p },
            None => g,
        };
        let o = Observation::from_state(&mut real.gs, self.side);
        let x = encode_observation(&o, &real.gs.reg);
        let turn = real.gs.turn;
        let reg = real.gs.reg.clone();
        let q = F::question_of(question);
        let src = match &src_name {
            Some(n) => reg.card_id(Some(n)),
            None => 0,
        };
        let c = ctx.unwrap_or_else(|| F::context(descs.len(), 0, false, false));
        let n = descs.len();
        let otype: Vec<i64> = descs.iter().map(|d| d.type_).collect();
        let ocards: Vec<i64> = descs.iter().flat_map(|d| d.cards).collect();
        let ofeats: Vec<f32> = descs.iter().flat_map(|d| d.feats.iter().copied()).collect();
        let i = Python::attach(|py| -> PyResult<usize> {
            let x = PyArray1::from_vec(py, x);
            let c = PyArray1::from_vec(py, c.to_vec());
            let otype = PyArray1::from_vec(py, otype);
            let ocards = PyArray1::from_vec(py, ocards).reshape([n, 3])?;
            let ofeats = PyArray1::from_vec(py, ofeats).reshape([n, F::F_OPT])?;
            self.ask.bind(py).call1((x, q, src, c, otype, ocards, ofeats, turn))?.extract::<usize>()
        });
        i.map_err(|e| EngineError::Py(format!("ask: {e}")))
    }

    /// py: PPOAgent._menu(point, question)
    fn menu(&mut self, g: &mut Game, point: Point, question: &str) -> R<Action> {
        let legal = g.legal_actions(point, self.side)?;
        if legal.is_empty() {
            return Ok(Action::pass());
        }
        let mut descs = Vec::with_capacity(legal.len());
        for a in &legal {
            descs.push(F::describe_action(g, self.side, a)?);
        }
        let i = self.ask(g, question, &descs, None, None)?;
        Ok(legal[i].clone())
    }
}

impl Agent for PpoAgent {
    fn decide_action(&mut self, g: &mut Game, _side: Side, _cards_played: i64) -> R<Action> {
        self.menu(g, Point::TurnAction, "main")
    }
    fn decide_reaction(&mut self, g: &mut Game, _side: Side) -> R<Action> {
        self.menu(g, Point::Reaction, "reaction")
    }
    fn decide_showdown_action(&mut self, g: &mut Game, _side: Side, _bf_idx: usize) -> R<Action> {
        self.menu(g, Point::ShowdownAction, "showdown")
    }
    fn decide_mulligan(&mut self, g: &mut Game, _side: Side) -> R<Vec<i64>> {
        let hand = g.gs.player(self.side).hand.clone();
        let menu = F::mulligan_menu(hand.len());
        let descs: Vec<Descriptor> = menu.iter().map(|s| F::describe_mulligan(g, &hand, s)).collect();
        let i = self.ask(g, "mulligan", &descs, None, None)?;
        Ok(menu[i].clone())
    }
    fn decide_optional(&mut self, _g: &mut Game, _side: Side, _card: CardId, _name: &str) -> R<bool> {
        self.count("euristica: optional", 1);
        Ok(true)
    }
    fn decide_mode(&mut self, _g: &mut Game, _side: Side, _card: CardId, _n: i64) -> R<Option<i64>> {
        self.count("euristica: mode", 1);
        Ok(None)
    }
    fn decide_predict_recycle(&mut self, _g: &mut Game, _side: Side, _card: CardId) -> R<bool> {
        self.count("euristica: predict_recycle", 1);
        Ok(false)
    }
    /// py: PPOAgent.inner(loop, kind, options, default, source)
    fn inner(&mut self, g: &mut Game, kind: &str, _side: Side, options: &[Opt], _default: usize,
             source: Option<CardId>) -> R<Option<usize>> {
        let key = (g.loop_id, kind.to_string(), source);
        let made = if g.in_many && self.many.0.as_ref() == Some(&key) { self.many.1 + 1 } else { 0 };
        self.many = (Some(key), made);
        let descs: Vec<Descriptor> = options.iter().map(|o| F::describe_choice(g, self.side, kind, o)).collect();
        let ctx = F::context(options.len(), made, options.iter().any(|o| matches!(o, Opt::NoMore)),
                             g.real_game.is_some());
        if options.len() < 2 {
            return Ok(None);
        }
        Ok(Some(self.ask(g, kind, &descs, source, Some(ctx))?))
    }
}

