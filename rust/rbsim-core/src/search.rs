//! py: ai/net_mcts.py (NetGuidedMCTSAgent), ai/handwritten.py (HandwrittenAgent,
//! table_value), ai/ppo/prior_bot.py (PPOPriorAgent): the search of the arena.
//! Backup "best", the root move with the highest Q, `table_value` at the
//! leaves, priors equal (the hand-written bot) or from the PPO net over the
//! whole menu (`Prior`, the forward done by the caller). As the arena runs it:
//! no exploration (noise, temperature), no training records, tie_break
//! "first", advance_forced_move off; fixed iterations or a CPU budget.
//!
//! The real game's choosers (py: the chain _Plan -> _Fallback -> PPOChooser)
//! are one `Layers` chooser shared by the two search agents: its layers, top
//! first, then the chooser that was there before (`base`).

use std::cell::RefCell;
use std::rc::{Rc, Weak};

use serde_json::{json, Value};

use crate::agent::{AKind, Action, Agent, Chooser, Point};
use crate::features::{self as F, Descriptor};
use crate::game::{Game, JEntry};
use crate::model::{Facedown, GameState, Opt, PendingTrigger, XVal};
use crate::pydict::PyDict;
use crate::obs::{encode_observation, Observation};
use crate::rng::PyRandom;
use crate::trace::action_list;
use crate::types::*;

const MAX_TURN_ACTIONS: usize = 30;

/// py: a choice key (kind, the card making the choice, the option's label).
pub type CKey = (String, String, String);

// ------------------------------------------------------------- value ---

/// What table_value reads, for a diagnosis.
pub fn obs_summary(o: &Observation) -> Value {
    let us = |v: &Vec<crate::obs::UnitView>| -> Vec<Value> {
        v.iter().map(|u| json!([u.name, u.might, u.lasting_might])).collect()
    };
    json!({"points": [o.my_points, o.opp_points], "hand": [o.my_hand.len(), o.opp_hand_count],
           "bfs": o.battlefields.iter().map(|b| json!([b.controller.map(|s| s.name()), us(&b.a), us(&b.b)])).collect::<Vec<_>>(),
           "base": [us(&o.my_base_units), us(&o.opp_base_units)]})
}

/// py: handwritten.table_value
pub fn table_value(o: &Observation) -> f64 {
    let me = o.viewer;
    let mut s = 0.45 * ((o.my_points - o.opp_points) as f64);
    for bf in &o.battlefields {
        let (mine_v, theirs_v) = if me == Side::A { (&bf.a, &bf.b) } else { (&bf.b, &bf.a) };
        let mine: i64 = mine_v.iter().map(|u| u.lasting_might).sum();
        let theirs: i64 = theirs_v.iter().map(|u| u.lasting_might).sum();
        if bf.controller == Some(me) {
            s += 0.30;
        } else if bf.controller.is_some() {
            s -= 0.30;
        }
        s += 0.05 * ((mine - theirs) as f64);
    }
    let base: i64 = o.my_base_units.iter().map(|u| u.lasting_might).sum::<i64>()
        - o.opp_base_units.iter().map(|u| u.lasting_might).sum::<i64>();
    s += 0.03 * (base as f64);
    s += 0.03 * ((o.my_hand.len() as i64 - o.opp_hand_count as i64) as f64);
    s.tanh()
}

/// py: table_value(Observation.from_state(gs, side)) (the observation notes
/// battlefield control, as Python's does).
pub fn state_value(gs: &mut GameState, side: Side) -> f64 {
    table_value(&Observation::from_state(gs, side))
}

/// py: NetGuidedMCTSAgent._terminal_value
pub fn terminal_value(gs: &GameState, side: Side) -> Option<f64> {
    let vs = gs.victory_score;
    let (pa, pb) = (gs.points[0], gs.points[1]);
    if pa >= vs || pb >= vs {
        let win = if side == Side::A { pa > pb } else { pb > pa };
        return Some(if win { 1.0 } else if pa != pb { -1.0 } else { 0.0 });
    }
    None
}

/// The PPO net's probabilities over a menu (PPOPriorAgent._evaluate: the
/// forward and the softmax, float32), given what Rust builds: the encoded
/// observation, the question, the context and the options' descriptors.
/// Two copies of one game in step (scripts/rust/arena_mista.py): before each
/// search `before` says whether this copy repeats the other's search (Some(n):
/// exactly n iterations) or leads it (None: the agent's own budget, once the
/// other copy is waiting); after a led search `after` passes its count on.
/// `info`: the search's identity (seat, progressive, point, turn).
pub trait Lockstep {
    fn before(&mut self, info: &Value) -> R<Option<usize>>;
    fn after(&mut self, info: &Value, n: usize) -> R<()>;
}

pub trait Prior {
    fn probs(&mut self, x: Vec<f32>, q: i64, ctx: [f32; F::F_CTX], descs: &[Descriptor]) -> R<Vec<f32>>;
}

// -------------------------------------------------------- determinize ---

fn card_sort_key(gs: &GameState, c: CardId) -> (String, &'static str, i64, i64) {
    (gs.name(c).to_string(), gs.category(c).name(), gs.cost_energy(c), gs.might(c).unwrap_or(0))
}

/// py: state.determinize — the information hidden from `observer`
/// resampled in place: the opponent's unknown hand cards and facedown cards
/// redealt from their unseen pool, both decks' unknown orders, both rune
/// decks' unseen runes.
pub fn determinize(gs: &mut GameState, observer: Side, rng: &mut PyRandom) {
    let other = observer.other();
    let known = gs.player(other).hand_known();
    let hand = gs.player(other).hand.clone();
    let slots: Vec<usize> = (0..hand.len()).filter(|&i| !known.contains(&hand[i])).collect();
    let mut fds: Vec<(usize, usize)> = Vec::new();
    for (b, bf) in gs.battlefields.iter().enumerate() {
        for (s, fd) in bf.facedowns.iter().enumerate() {
            if fd.owner == other {
                fds.push((b, s));
            }
        }
    }
    let mut pool: Vec<CardId> = slots.iter().map(|&i| hand[i]).collect();
    pool.extend(gs.player(other).deck.cards.iter().copied());
    pool.extend(fds.iter().map(|&(b, s)| gs.battlefields[b].facedowns[s].card));
    {
        let g: &GameState = gs;
        pool.sort_by(|&a, &b| card_sort_key(g, a).cmp(&card_sort_key(g, b)));
    }
    rng.shuffle(&mut pool);
    for &(b, s) in &fds {
        let pick = pool.iter().copied().find(|&c| gs.has_keyword(c, "HIDDEN")).or(pool.first().copied());
        let Some(pick) = pick else { continue };
        let pos = pool.iter().position(|&c| c == pick).unwrap();
        pool.remove(pos);
        let fd = gs.battlefields[b].facedowns[s].clone();
        gs.battlefields[b].facedowns[s] = Facedown { card: pick, owner: fd.owner, turn_hidden: fd.turn_hidden };
    }
    let mut h = hand;
    for (j, &i) in slots.iter().enumerate() {
        h[i] = pool[j];
    }
    gs.player_mut(other).hand = h;
    gs.player_mut(other).deck.cards = pool[slots.len()..].to_vec();

    let k = gs.player(observer).deck.known_on_top().len();
    let n = gs.player(observer).deck.cards.len() - k;
    let mut below: Vec<CardId> = gs.player(observer).deck.cards[..n].to_vec();
    {
        let g: &GameState = gs;
        below.sort_by(|&a, &b| card_sort_key(g, a).cmp(&card_sort_key(g, b)));
    }
    rng.shuffle(&mut below);
    gs.player_mut(observer).deck.cards[..n].copy_from_slice(&below);
    gs.player_mut(other).deck.shuffle(rng);

    for p in [observer, other] {
        let rd = &mut gs.player_mut(p).rune_deck;
        let n = match rd.unseen {
            None => rd.runes.len(),
            Some(u) => (u.max(0) as usize).min(rd.runes.len()),
        };
        let mut head = rd.runes[..n].to_vec();
        head.sort_by(|a, b| a.domain.name().cmp(b.domain.name()));
        rng.shuffle(&mut head);
        rd.runes[..n].copy_from_slice(&head);
    }
}

/// A copy of the game for the search (py: clone = gs.clone(); clone.rng =
/// Random(seed); determinize(clone, side, clone.rng); GameLoop(clone)): no
/// agents, a fresh loop.
fn search_copy(gs: &GameState, side: Side, seed: u64) -> Game {
    let mut gs = gs.clone();
    for s in Side::BOTH {
        gs.players[s.idx()].has_agent = false;
    }
    let mut rng = PyRandom::new(seed as i128);
    determinize(&mut gs, side, &mut rng);
    gs.rng = rng;
    Game::new(gs)
}

/// `f` on a fresh loop over `g`'s state (py: GameLoop(clone) on the same
/// state, as PPOPriorAgent._evaluate builds one for the descriptors).
fn on_fresh_loop<T>(g: &mut Game, f: impl FnOnce(&mut Game) -> T) -> T {
    let reg = g.gs.reg.clone();
    let gs = std::mem::replace(&mut g.gs, crate::setup::empty_state(reg, PyRandom::new(0)));
    let mut fresh = Game::new(gs);
    let out = f(&mut fresh);
    g.gs = fresh.gs;
    out
}

// -------------------------------------------------------------- labels ---

fn card_repr(gs: &GameState, c: CardId) -> String {
    let card = gs.card(c);
    format!("Card({}#{}|{:?}|{})", gs.name(c), card.uuid, gs.might(c), card.tapped)
}

fn unit_repr(gs: &GameState, u: UnitId) -> String {
    let x = gs.unit(u);
    let gear: Vec<String> = x.gear.iter().map(|&g| card_repr(gs, g)).collect();
    let copied = x.copied_from.map(|c| card_repr(gs, c));
    format!("U({}|{:?}|{:?}|{:?})", card_repr(gs, x.card), gear, copied, x)
}

fn dgear_repr(gs: &GameState, g: GearId) -> String {
    let d = &gs.dgear[g.i()];
    format!("DG({}|{})", card_repr(gs, d.card), d.is_token)
}

/// py: repr(Battlefield) (its dataclass fields; prev_controller is a
/// dynamic attribute, not in the repr). combat_designated is a set: sorted.
fn bf_repr(gs: &GameState, b: usize) -> String {
    let bf = &gs.battlefields[b];
    let us = |v: &Vec<UnitId>| -> Vec<String> { v.iter().map(|&u| unit_repr(gs, u)).collect() };
    let fds: Vec<String> = bf.facedowns.iter()
        .map(|f| format!("FD({}|{:?}|{})", card_repr(gs, f.card), f.owner, f.turn_hidden)).collect();
    let mut cd = us(&bf.combat_designated);
    cd.sort();
    let gr = |v: &Vec<GearId>| -> Vec<String> { v.iter().map(|&g| dgear_repr(gs, g)).collect() };
    format!("BF({:?}|{:?}|{}|{:?}|{:?}|{:?}|{:?}|{:?}|{:?}|{:?}|{}|{:?}|{:?}|{:?}|{:?}|{:?}|{:?}|{}|{:?}|{:?}|{:?}|{:?}|{:?})",
            us(&bf.units[0]), us(&bf.units[1]), bf.contested_this_turn, bf.scored_this_turn, bf.first_unit_here,
            bf.plays_here, bf.last_controller, bf.held_by, bf.gained_control, bf.contested_by, bf.showdown_pending,
            bf.card.map(|c| card_repr(gs, c)), bf.replaced.map(|c| card_repr(gs, c)), fds, bf.conquered_turn,
            bf.excess_damage, cd, bf.combat_started, bf.combat_attacker, gr(&bf.gear[0]), gr(&bf.gear[1]),
            bf.kills, bf.deaths)
}

/// An extra / flags value as Python's repr shows it: objects by their repr.
fn xval_repr(gs: &GameState, v: &XVal) -> String {
    match v {
        XVal::Bf(b) => bf_repr(gs, *b),
        XVal::Unit(u) => unit_repr(gs, *u),
        XVal::Card(c) => card_repr(gs, *c),
        XVal::List(xs) => format!("[{}]", xs.iter().map(|x| xval_repr(gs, x)).collect::<Vec<_>>().join(", ")),
        other => format!("{other:?}"),
    }
}

fn xdict_repr(gs: &GameState, d: &PyDict<String, XVal>) -> String {
    let rows: Vec<String> = d.iter().map(|(k, v)| format!("{k:?}: {}", xval_repr(gs, v))).collect();
    format!("{{{}}}", rows.join(", "))
}

fn trigger_repr(gs: &GameState, p: &PendingTrigger) -> String {
    let extra = p.extra.as_ref().map(|e| xdict_repr(gs, &e.items));
    let flags = p.flags.as_ref().map(|f| xdict_repr(gs, f));
    format!("PT({}|{}|{:?}|{}|{:?}|{:?}|{}|{:?}|{}|{:?})", card_repr(gs, p.card), p.trigger, p.side,
            bf_repr(gs, p.bf), p.specs, extra, p.additional, flags, p.once, p.replay)
}

/// py: repr / str of a plain value (a dict of str keys: `{'energy': 3, 'buffs': 1}`).
fn py_repr(v: &serde_json::Value) -> String {
    use serde_json::Value as V;
    fn s_repr(s: &str) -> String {
        if s.contains('\'') && !s.contains('"') {
            format!("\"{s}\"")
        } else {
            format!("'{}'", s.replace('\\', "\\\\").replace('\'', "\\'"))
        }
    }
    match v {
        V::Null => "None".into(),
        V::Bool(b) => (if *b { "True" } else { "False" }).into(),
        V::Number(n) => n.to_string(),
        V::String(s) => s_repr(s),
        V::Array(a) => format!("[{}]", a.iter().map(py_repr).collect::<Vec<_>>().join(", ")),
        V::Object(m) => format!("{{{}}}", m.iter().map(|(k, x)| format!("{}: {}", s_repr(k), py_repr(x))).collect::<Vec<_>>().join(", ")),
    }
}

/// py: str(getattr(x, "name", x)) for a tuple's first element.
fn name_of(g: &Game, x: &Opt) -> String {
    match x {
        Opt::Card(c) => g.gs.name(*c).to_string(),
        Opt::Str(s) => s.clone(),
        Opt::Json(v) => py_repr(v),
        Opt::Int(i) => i.to_string(),
        Opt::Bool(b) => (if *b { "True" } else { "False" }).into(),
        Opt::None => "None".into(),
        Opt::Side(s) => s.name().into(),
        Opt::Domain(d) => d.name().into(),
        Opt::Unit(u) => unit_repr(&g.gs, *u),
        Opt::Bf(b) => bf_repr(&g.gs, *b),
        other => format!("{other:?}"),
    }
}

/// py: decisions.describe_option(loop, side, option) on `g`. `foreign`: the
/// options belong to a copy of `g`'s game (a declaration's), which `g` does
/// not contain: a unit is not located there, a battlefield is not in its
/// list (py: ValueError).
pub fn describe_option(g: &Game, side: Side, kind: &str, o: &Opt, foreign: bool) -> R<String> {
    let o = match o {
        Opt::Tuple(v) if matches!(v.last(), Some(Opt::Unit(_))) => v.last().unwrap(),
        _ => o,
    };
    let gs = &g.gs;
    Ok(match o {
        Opt::Unit(u) => {
            let wh = if foreign { None } else { g.locate_unit(*u) };
            let whose = if matches!(wh, Some((s, _)) if s == side) { "yours" } else { "theirs" };
            let at = match wh {
                Some((_, Some(b))) => format!("battlefield {b}"),
                _ => "base".to_string(),
            };
            let x = gs.unit(*u);
            let token = if x.is_token { ", token" } else { "" };
            format!("{} ({whose}, Might {}, {at}{token})", gs.name(x.card), gs.unit_might(*u))
        }
        Opt::Bf(b) => {
            if foreign {
                return Err(EngineError::Py("ValueError: battlefield is not in list".into()));
            }
            match gs.battlefields[*b].card {
                Some(c) => format!("battlefield {b} ({})", gs.name(c)),
                None => format!("battlefield {b}"),
            }
        }
        Opt::Bool(t) => (if *t { "yes" } else { "no" }).to_string(),
        // facedown_trash offers FacedownCard (py), their cards in Rust: the repr.
        Opt::Card(c) if kind.starts_with("facedown_trash") => {
            let fd = gs.battlefields.iter().flat_map(|bf| bf.facedowns.iter()).find(|f| f.card == *c);
            match fd {
                Some(f) => format!("FD({}|{:?}|{})", card_repr(gs, f.card), f.owner, f.turn_hidden),
                None => card_repr(gs, *c),
            }
        }
        Opt::Card(c) => format!("{} ({}, {} energy)", gs.name(*c), gs.category(*c).name().to_lowercase(),
                                gs.cost_energy(*c)),
        Opt::Tuple(v) => match v.first() {
            Some(x) => name_of(g, x),
            None => return Err(EngineError::Py("IndexError: tuple index out of range".into())),
        },
        Opt::Int(i) => format!("mode {}", i + 1),
        Opt::Domain(d) => d.name().to_string(),
        Opt::Side(s) => s.name().to_string(),
        Opt::Str(s) => s.clone(),
        Opt::Json(v) => py_repr(v),
        Opt::None => "None".to_string(),
        Opt::NoMore => "no more".to_string(),
        Opt::Gear(gid) => dgear_repr(gs, *gid),
        Opt::Trigger(i) => match g.trigger_menu.get(*i) {
            Some(p) => trigger_repr(gs, p),
            None => format!("Trigger #{i}"),
        },
        Opt::Chain(i) => match gs.chain_pos(*i).map(|p| &gs.chain[p]) {
            Some(it) => format!("CI({}|{:?}|{}|{:?}|{:?}|{:?})", card_repr(gs, it.card), it.player, it.bf_idx,
                                it.owner, it.declared, it.ability),
            None => format!("ChainItem #{i}"),
        },
    })
}

/// py: _choice_keys(loop, kind, side, options, source)
pub fn choice_keys(g: &Game, kind: &str, side: Side, options: &[Opt], source: Option<CardId>, foreign: bool)
                   -> R<Vec<CKey>> {
    let src = source.map(|c| g.gs.name(c).to_string()).unwrap_or_default();
    options.iter().map(|o| Ok((kind.to_string(), src.clone(), describe_option(g, side, kind, o, foreign)?))).collect()
}

/// py: _searchable (UNSEARCHED_CHOICES is empty).
fn searchable(side: Side, me: Side, n: usize) -> bool {
    side == me && n > 1
}

// ---------------------------------------------------------------- tree ---

#[derive(Clone, Default)]
pub struct Node {
    pub n: i64,
    pub w: f64,
    pub q: f64,
    pub p: Vec<(Action, f64)>,
    pub children: Vec<(Action, usize)>,
    pub expanded: bool,
    pub value: f64,
    /// (choice key, node, prior), in the order met.
    pub choices: Vec<(CKey, usize, f64)>,
}

#[derive(Default)]
pub struct Tree {
    pub nodes: Vec<Node>,
}

impl Tree {
    fn add(&mut self) -> usize {
        self.nodes.push(Node::default());
        self.nodes.len() - 1
    }
    fn choice(&self, n: usize, k: &CKey) -> Option<usize> {
        self.nodes[n].choices.iter().find(|(kk, _, _)| kk == k).map(|(_, c, _)| *c)
    }

    /// py: _backup
    fn backup(&mut self, path: &[usize], value: f64) {
        for &n in path {
            self.nodes[n].n += 1;
            self.nodes[n].w += value;
        }
        for &n in path.iter().rev() {
            let node = &self.nodes[n];
            let mut best: Option<f64> = None;
            let below = node.children.iter().map(|(_, c)| *c).chain(node.choices.iter().map(|(_, c, _)| *c));
            for c in below {
                let c = &self.nodes[c];
                if c.n != 0 {
                    best = Some(match best {
                        Some(b) if !(c.q > b) => b,
                        _ => c.q,
                    });
                }
            }
            let q = best.unwrap_or(node.w / node.n as f64);
            self.nodes[n].q = q;
        }
    }

    /// py: _puct_select -> the index in node.children
    fn puct_select(&self, n: usize, legal: &[Action], c_puct: f64) -> Option<usize> {
        let node = &self.nodes[n];
        let sqrt_total = (node.n.max(1) as f64).sqrt();
        let fpu = if node.n != 0 { node.q } else { 0.0 };
        let mut best: Option<usize> = None;
        let mut best_val = -1e30;
        for (i, (a, c)) in node.children.iter().enumerate() {
            if !legal.iter().any(|l| l.same(a)) {
                continue;
            }
            let child = &self.nodes[*c];
            let q = if child.n > 0 { child.q } else { fpu };
            let p = node.p.iter().find(|(pa, _)| pa.same(a)).map_or(0.0, |(_, p)| *p);
            let u = c_puct * p * sqrt_total / ((1 + child.n) as f64);
            let val = q + u;
            if val > best_val {
                best_val = val;
                best = Some(i);
            }
        }
        best
    }

    /// py: _select_option
    fn select_option(&self, n: usize, keys: &[CKey], default: usize, c_puct: f64) -> usize {
        let node = &self.nodes[n];
        let sqrt_total = (node.n.max(1) as f64).sqrt();
        let fpu = if node.n != 0 { node.q } else { 0.0 };
        let (mut best, mut best_val) = (default, -1e30);
        let mut seen: Vec<&CKey> = Vec::new();
        let order = std::iter::once(default).chain((0..keys.len()).filter(|&i| i != default));
        for i in order {
            let k = &keys[i];
            if seen.contains(&k) {
                continue;
            }
            seen.push(k);
            let (_, c, prior) = node.choices.iter().find(|(kk, _, _)| kk == k).unwrap();
            let child = &self.nodes[*c];
            let q = if child.n != 0 { child.q } else { fpu };
            let val = q + c_puct * prior * sqrt_total / ((1 + child.n) as f64);
            if val > best_val {
                best = i;
                best_val = val;
            }
        }
        best
    }
}

/// py: dict assignment d[a] = v (the first position kept).
fn dict_set(d: &mut Vec<(Action, f64)>, a: &Action, v: f64) {
    match d.iter_mut().find(|(k, _)| k.same(a)) {
        Some(e) => e.1 = v,
        None => d.push((a.clone(), v)),
    }
}

fn dict_add(d: &mut Vec<(Action, f64)>, a: &Action, v: f64) {
    match d.iter_mut().find(|(k, _)| k.same(a)) {
        Some(e) => e.1 += v,
        None => d.push((a.clone(), 0.0 + v)),
    }
}

/// py: _TreeChooser — on a search copy: PUCT over each choice of `me`.
struct TreeChooser {
    tree: Rc<RefCell<Tree>>,
    me: Side,
    node: usize,
    path: Vec<usize>,
    c_puct: f64,
    /// Diagnosis: each choice met, with the node's options and statistics.
    dbg: Option<Vec<Value>>,
}

impl Chooser for TreeChooser {
    fn choose(&mut self, g: &mut Game, kind: &str, side: Side, options: &[Opt], default: usize,
              source: Option<CardId>) -> R<Option<usize>> {
        if !searchable(side, self.me, options.len()) {
            return Ok(None);
        }
        let keys = choice_keys(g, kind, side, options, source, false)?;
        let mut t = self.tree.borrow_mut();
        let n = options.len();
        for k in &keys {
            if t.choice(self.node, k).is_none() {
                let c = t.add();
                t.nodes[self.node].choices.push((k.clone(), c, 1.0 / n as f64));
            }
        }
        let i = t.select_option(self.node, &keys, default, self.c_puct);
        if let Some(d) = self.dbg.as_mut() {
            let node = &t.nodes[self.node];
            let opts: Vec<Value> = node.choices.iter().map(|(k, c, p)| {
                let x = &t.nodes[*c];
                json!([k.0, k.2.chars().take(60).collect::<String>(), x.n, x.q, p])
            }).collect();
            d.push(json!({"kind": kind, "n": options.len(), "default": default, "pick": i,
                          "node_n": node.n, "node_q": node.q, "choices": opts}));
        }
        self.node = t.choice(self.node, &keys[i]).unwrap();
        self.path.push(self.node);
        Ok(Some(i))
    }
}

/// py: the probe of _choices_ahead.
struct Probe {
    me: Side,
    met: bool,
}

impl Chooser for Probe {
    fn choose(&mut self, _g: &mut Game, _kind: &str, side: Side, options: &[Opt], _default: usize,
              _source: Option<CardId>) -> R<Option<usize>> {
        if searchable(side, self.me, options.len()) {
            self.met = true;
        }
        Ok(None)
    }
}

// ------------------------------------------------------- the real loop ---

/// py: _LEVEL
fn level(p: Point) -> i64 {
    match p {
        Point::TurnAction => 0,
        Point::ShowdownAction => 1,
        Point::Reaction => 2,
        Point::Mulligan => 0,
    }
}

pub struct Plan {
    me: Side,
    tree: Rc<RefCell<Tree>>,
    node: usize,
    level: i64,
    turn: i64,
}

pub enum Layer {
    /// py: _Plan
    Plan(Plan),
    /// py: _Fallback. The agent's core by a weak reference: the core holds
    /// these layers (`stack`), a strong one would be a cycle and the agents,
    /// their trees and logs would outlive the game.
    Fallback(Side, Weak<RefCell<SearchCore>>),
}

/// py: the chain of choosers the search agents put on the real loop.
#[derive(Default)]
pub struct Layers {
    pub layers: Vec<Layer>,
    pub base: Option<Rc<RefCell<dyn Chooser>>>,
    pub installed: bool,
}

impl Layers {
    fn call(&mut self, idx: usize, g: &mut Game, kind: &str, side: Side, options: &[Opt], default: usize,
            source: Option<CardId>) -> R<Option<usize>> {
        if idx >= self.layers.len() {
            return match self.base.clone() {
                Some(b) => b.borrow_mut().choose(g, kind, side, options, default, source),
                None => Ok(None),
            };
        }
        enum Info {
            Plan(Side, i64, Rc<RefCell<Tree>>, usize),
            Fallback(Side, Weak<RefCell<SearchCore>>),
        }
        let info = match &self.layers[idx] {
            Layer::Plan(p) => Info::Plan(p.me, p.turn, p.tree.clone(), p.node),
            Layer::Fallback(me, core) => Info::Fallback(*me, core.clone()),
        };
        match info {
            Info::Plan(me, turn, tree, node) => {
                if g.gs.turn != turn || !searchable(side, me, options.len()) {
                    return self.call(idx + 1, g, kind, side, options, default, source);
                }
                let keys = choice_keys(g, kind, side, options, source, false)?;
                let pick = {
                    let t = tree.borrow();
                    let mut seen: Option<(i64, i64)> = None;
                    for (i, k) in keys.iter().enumerate() {
                        if let Some(c) = t.choice(node, k) {
                            let cn = t.nodes[c].n;
                            if cn > 0 {
                                let v = (cn, -(i as i64));
                                if seen.is_none_or(|s| v > s) {
                                    seen = Some(v);
                                }
                            }
                        }
                    }
                    // The tree saw other options for this kind of choice: it
                    // depends on hidden cards; the chooser below sees the real ones.
                    let hidden = t.nodes[node].choices.iter().any(|(k, _, _)| k.0 == kind && !keys.contains(k));
                    match seen {
                        Some(s) if !hidden => Some((-s.1) as usize),
                        _ => None,
                    }
                };
                let i = match pick {
                    Some(i) => Some(i),
                    None => self.call(idx + 1, g, kind, side, options, default, source)?,
                };
                let got = i.unwrap_or(default);
                let next = tree.borrow().choice(node, &keys[got]).unwrap_or(node);
                if let Some(Layer::Plan(p)) = self.layers.get_mut(idx) {
                    p.node = next;
                }
                Ok(i)
            }
            Info::Fallback(me, core) => {
                if !searchable(side, me, options.len()) {
                    return self.call(idx + 1, g, kind, side, options, default, source);
                }
                let core = core.upgrade()
                    .ok_or_else(|| EngineError::Agent("search: the agent of a Fallback is gone".into()))?;
                let mut c = core.try_borrow_mut()
                    .map_err(|_| EngineError::Agent("search: a real choice while the agent decides".into()))?;
                let values = c.replay_values(g, kind, side, options, source)?;
                if let Some(values) = values {
                    let mut best = 0;
                    for i in 1..values.len() {
                        // py: max(range(n), key=lambda i: (values[i], i == default))
                        if (values[i], i == default) > (values[best], best == default) {
                            best = i;
                        }
                    }
                    if values[best] > values[default] + 1e-6 {
                        return Ok(Some(best));
                    }
                }
                Ok(None)
            }
        }
    }
}

impl Chooser for Layers {
    fn choose(&mut self, g: &mut Game, kind: &str, side: Side, options: &[Opt], default: usize,
              source: Option<CardId>) -> R<Option<usize>> {
        self.call(0, g, kind, side, options, default, source)
    }
}

// ------------------------------------------------------------- replay ---

/// py: _Cursor — replays a loop's journal on a copy of its segment, then
/// forces the option weighed (its randomness from here on new, `seed`).
struct Cursor {
    journal: Vec<JEntry>,
    target: (Side, String, usize),
    force: usize,
    seed: u64,
    k: usize,
    done: bool,
}

const STOP: &str = "search: _Stop";
const DIVERGED: &str = "search: _Diverged";

impl Cursor {
    fn decision(&mut self, side: Side, point: Point) -> R<Action> {
        if self.k >= self.journal.len() {
            return Err(EngineError::Agent(STOP.into()));
        }
        match &self.journal[self.k] {
            JEntry::Decision(s, p, a) if *s == side && p == point.name() => {
                self.k += 1;
                Ok(a.clone())
            }
            _ => Err(EngineError::Agent(DIVERGED.into())),
        }
    }
}

struct CursorChooser(Rc<RefCell<Cursor>>);

impl Chooser for CursorChooser {
    fn choose(&mut self, g: &mut Game, kind: &str, side: Side, options: &[Opt], _default: usize,
              _source: Option<CardId>) -> R<Option<usize>> {
        let mut c = self.0.borrow_mut();
        if c.k < c.journal.len() {
            return match &c.journal[c.k] {
                JEntry::Choice(s, k, n, i) if *s == side && k == kind && *n == options.len() => {
                    let i = *i;
                    c.k += 1;
                    Ok(Some(i))
                }
                _ => Err(EngineError::Agent(DIVERGED.into())),
            };
        }
        if c.done {
            return Ok(None);
        }
        if (side, kind.to_string(), options.len()) != c.target {
            return Err(EngineError::Agent(DIVERGED.into()));
        }
        c.done = true;
        c.k += 1;
        // py: self.gs.rng = random.Random(self.seed) — the replayed game's.
        let real: &mut Game = match g.real_game {
            // SAFETY: the replayed game's frame runs this declaration's copy.
            Some(p) => unsafe { &mut *p },
            None => g,
        };
        real.gs.rng = PyRandom::new(c.seed as i128);
        Ok(Some(c.force))
    }
}

/// py: _ReplayAgent
struct ReplayAgent(Rc<RefCell<Cursor>>);

impl Agent for ReplayAgent {
    fn decide_action(&mut self, _g: &mut Game, side: Side, _cp: i64) -> R<Action> {
        self.0.borrow_mut().decision(side, Point::TurnAction)
    }
    fn decide_reaction(&mut self, _g: &mut Game, side: Side) -> R<Action> {
        self.0.borrow_mut().decision(side, Point::Reaction)
    }
    fn decide_showdown_action(&mut self, _g: &mut Game, side: Side, _bf: usize) -> R<Action> {
        self.0.borrow_mut().decision(side, Point::ShowdownAction)
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
}

fn is_stop(e: &EngineError) -> bool {
    matches!(e, EngineError::Agent(s) if s == STOP)
}

// --------------------------------------------------------------- agent ---

/// CPU seconds of this process (py: time.process_time()).
pub fn process_time() -> f64 {
    let mut ts = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    // SAFETY: clock_gettime writes the timespec it is given.
    unsafe { libc::clock_gettime(libc::CLOCK_PROCESS_CPUTIME_ID, &mut ts) };
    ts.tv_sec as f64 + ts.tv_nsec as f64 * 1e-9
}

/// The state of a search agent (py: NetGuidedMCTSAgent's attributes).
pub struct SearchCore {
    pub side: Side,
    pub iterations: usize,
    pub reaction_iterations: usize,
    pub c_puct: f64,
    pub mulligan_samples: usize,
    pub budget: Option<f64>,
    pub rng: PyRandom,
    pub prior: Option<Box<dyn Prior>>,
    question: &'static str,
    pub decisions: i64,
    pub turns: i64,
    pub empty_turns: i64,
    turn_seen: Option<i64>,
    pub main_iters: Vec<usize>,
    stack: Rc<RefCell<Layers>>,
    fallback_on: bool,
    /// For the parity checks: one row per searched decision (and mulligan).
    pub log: Option<Vec<Value>>,
    /// The arena in step with a Python copy (None: the agent's own budget).
    pub lockstep: Option<Box<dyn Lockstep>>,
    searches: usize,
    /// With `log`: the value each simulation of the current search backed up.
    vals: Vec<f64>,
    /// Diagnosis: (search, simulation) whose copy is dumped at every step
    /// into `debug_out` (raw states, the leaf's observation and value).
    pub debug: Option<(usize, usize)>,
    pub debug_out: Vec<Value>,
    cur_search: usize,
    sim: usize,
    me_ref: Option<Weak<RefCell<SearchCore>>>,
    /// Opt-in (off by default): before searching, look for a win this turn by moves.
    pub win_probe: bool,
}

static LIVE_CORES: std::sync::atomic::AtomicI64 = std::sync::atomic::AtomicI64::new(0);

/// How many search cores are alive (a check that a finished game frees its agents).
pub fn live_cores() -> i64 {
    LIVE_CORES.load(std::sync::atomic::Ordering::Relaxed)
}

impl Drop for SearchCore {
    fn drop(&mut self) {
        LIVE_CORES.fetch_sub(1, std::sync::atomic::Ordering::Relaxed);
    }
}

impl SearchCore {
    /// py: HandwrittenAgent(player, iterations, rng, budget) / PPOPriorAgent(..., net).
    pub fn new(side: Side, iterations: usize, seed: i128, budget: Option<f64>, prior: Option<Box<dyn Prior>>,
               stack: Rc<RefCell<Layers>>) -> Rc<RefCell<SearchCore>> {
        let core = Rc::new(RefCell::new(SearchCore {
            side,
            iterations,
            reaction_iterations: iterations.max(8),
            c_puct: 1.5,
            mulligan_samples: 3,
            budget,
            rng: PyRandom::new(seed),
            prior,
            question: "main",
            decisions: 0,
            turns: 0,
            empty_turns: 0,
            turn_seen: None,
            main_iters: Vec::new(),
            stack,
            fallback_on: false,
            log: None,
            lockstep: None,
            searches: 0,
            vals: Vec::new(),
            debug: None,
            debug_out: Vec::new(),
            cur_search: 0,
            sim: 0,
            me_ref: None,
            win_probe: false,
        }));
        core.borrow_mut().me_ref = Some(Rc::downgrade(&core));
        LIVE_CORES.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        core
    }

    fn seed(&mut self) -> u64 {
        self.rng.randrange(1 << 30)
    }

    /// py: _evaluate — (priors over the menu, value).
    fn evaluate(&mut self, c: &mut Game, legal: &[Action]) -> R<(Vec<(Action, f64)>, f64)> {
        let side = self.side;
        match self.prior.as_mut() {
            None => {
                let u = 1.0 / legal.len().max(1) as f64;
                let mut p = Vec::new();
                for a in legal {
                    dict_set(&mut p, a, u);
                }
                let v = state_value(&mut c.gs, side);
                Ok((p, v))
            }
            Some(net) => {
                let obs = Observation::from_state(&mut c.gs, side);
                let tv = table_value(&obs);
                let mut p = Vec::new();
                if legal.len() < 2 {
                    for a in legal {
                        dict_set(&mut p, a, 1.0);
                    }
                    return Ok((p, tv));
                }
                let descs = on_fresh_loop(c, |fg| -> R<Vec<Descriptor>> {
                    legal.iter().map(|a| F::describe_action(fg, side, a)).collect()
                })?;
                let x = encode_observation(&obs, &c.gs.reg);
                let q = F::question_of(self.question);
                let ctx = F::context(descs.len(), 0, false, false);
                let probs = net.probs(x, q, ctx, &descs)?;
                for (a, pr) in legal.iter().zip(probs) {
                    dict_add(&mut p, a, pr as f64);
                }
                Ok((p, tv))
            }
        }
    }

    fn expand(&mut self, t: &mut Tree, n: usize, priors: Vec<(Action, f64)>, v: f64) {
        let kids: Vec<(Action, usize)> = priors.iter().map(|(a, _)| (a.clone(), t.add())).collect();
        let node = &mut t.nodes[n];
        node.p = priors;
        node.children = kids;
        node.expanded = true;
        node.value = v;
    }

    /// py: _ensure_fallback — the real loop journals, and this player's
    /// choices no plan answers go to a Fallback (once per loop).
    fn ensure_fallback(&mut self, g: &mut Game) {
        if self.fallback_on {
            return;
        }
        self.fallback_on = true;
        if g.journal.is_none() {
            g.journal = Some(Vec::new());
        }
        let mut st = self.stack.borrow_mut();
        if !st.installed {
            st.installed = true;
            st.base = g.chooser.take();
            let c: Rc<RefCell<dyn Chooser>> = self.stack.clone();
            g.chooser = Some(c);
        }
        let me = self.me_ref.clone().expect("search core");
        st.layers.insert(0, Layer::Fallback(self.side, me));
    }

    /// py: _release_forced(level)
    fn release_forced(&mut self, g: &Game, lv: i64) {
        let turn = g.gs.turn;
        let side = self.side;
        self.stack.borrow_mut().layers.retain(|l| match l {
            Layer::Plan(p) => !(p.me == side && (p.level >= lv || p.turn != turn)),
            _ => true,
        });
    }

    pub fn decide_action(&mut self, g: &mut Game, cards_played: i64) -> R<Action> {
        self.ensure_fallback(g);
        self.release_forced(g, 0);
        let root_legal = g.legal_actions(Point::TurnAction, self.side)?;
        if root_legal.len() <= 1 {
            return Ok(root_legal.first().cloned().unwrap_or_else(Action::pass));
        }
        let probed = if self.win_probe && self.lockstep.is_none() {
            self.win_this_turn(g, &root_legal, cards_played)?
        } else {
            None
        };
        let action = match probed {
            Some(a) => a,
            None => {
                let tree = self.search(g, Point::TurnAction, &root_legal, cards_played, None)?;
                self.conclude(g, &tree, &root_legal, Point::TurnAction)?
            }
        };
        if self.turn_seen != Some(g.gs.turn) {
            self.turn_seen = Some(g.gs.turn);
            self.turns += 1;
            if action.kind == AKind::Pass && g.gs.pending_move.is_none() {
                self.empty_turns += 1;
            }
        }
        Ok(action)
    }

    /// Opt-in probe: a line of moves (and the commit of the pending move) that
    /// wins this turn by conquests. Uses no `self.rng`. Some(first action) or None.
    fn win_this_turn(&mut self, g: &Game, root_legal: &[Action], cards_played: i64) -> R<Option<Action>> {
        const PROBE_SEED: u64 = 0x5EED;
        const MAX_DEPTH: usize = 8;
        const MAX_APPLIES: usize = 3000;
        let side = self.side;
        let n_bf = g.gs.battlefields.len() as i64;
        let need = g.gs.victory_score - g.gs.points[side.idx()];
        let unscored = g.gs.battlefields.iter().filter(|b| !b.scored_this_turn[side.idx()]).count() as i64;
        if need < 1 || need > unscored {
            return Ok(None);
        }
        let mut applies = 0usize;
        let mut stack: Vec<Vec<Action>> = vec![Vec::new()];
        // Depth-first: the stack holds prefixes still to expand (children pushed in reverse).
        while let Some(prefix) = stack.pop() {
            let legal: Vec<Action> = if prefix.is_empty() {
                root_legal.to_vec()
            } else {
                // rebuild the state of this node to list its menu
                let Some(c) = Self::probe_replay(&g.gs, side, PROBE_SEED, &prefix, cards_played, &mut applies, MAX_APPLIES) else {
                    if applies > MAX_APPLIES { return Ok(None); }
                    continue;
                };
                let mut c = c;
                match c.legal_actions(Point::TurnAction, side) {
                    Ok(l) => l,
                    Err(_) => continue,
                }
            };
            let mut kids: Vec<Action> = Vec::new();
            for a in legal.iter() {
                let ok = match a.kind {
                    AKind::Move => matches!(a.dst, Some(d) if d >= 0 && d < n_bf),
                    AKind::Pass => true, // only the commit of a pending move; checked on the state below
                    _ => false,
                };
                if ok {
                    kids.push(a.clone());
                }
            }
            for a in kids.into_iter() {
                let mut line = prefix.clone();
                line.push(a.clone());
                let Some(c) = Self::probe_replay(&g.gs, side, PROBE_SEED, &prefix, cards_played, &mut applies, MAX_APPLIES) else {
                    if applies > MAX_APPLIES { return Ok(None); }
                    continue;
                };
                let mut c = c;
                if a.kind == AKind::Pass && !matches!(c.gs.pending_move, Some((_, s)) if s == side) {
                    continue;
                }
                if applies >= MAX_APPLIES {
                    return Ok(None);
                }
                applies += 1;
                let cpt = cards_played + prefix.len() as i64;
                if c.apply_action(side, &a, cpt).is_err() || c.recompute_passives().is_err() {
                    continue;
                }
                match terminal_value(&c.gs, side) {
                    Some(v) if v == 1.0 => {
                        if let Some(log) = self.log.as_mut() {
                            let labels: Vec<String> = line.iter().map(|x| x.label.clone()).collect();
                            log.push(json!({"k": "vittoria", "seat": side.name(), "turn": g.gs.turn, "line": labels}));
                        }
                        return Ok(Some(line[0].clone()));
                    }
                    Some(_) => continue,
                    None => {}
                }
                if c.gs.active != side || line.len() >= MAX_DEPTH {
                    continue;
                }
                stack.push(line);
            }
        }
        Ok(None)
    }

    /// A fresh copy of the root with `prefix` applied (counts every apply).
    fn probe_replay(gs: &GameState, side: Side, seed: u64, prefix: &[Action], cards_played: i64,
                    applies: &mut usize, max: usize) -> Option<Game> {
        let mut c = search_copy(gs, side, seed);
        for (i, a) in prefix.iter().enumerate() {
            if *applies >= max {
                *applies = max + 1;
                return None;
            }
            *applies += 1;
            if c.apply_action(side, a, cards_played + i as i64).is_err() || c.recompute_passives().is_err() {
                return None;
            }
        }
        Some(c)
    }

    /// py: search (and _Budget.search): the root is node 0.
    fn search(&mut self, g: &mut Game, point: Point, legal: &[Action], cards_played: i64, bf_idx: Option<usize>)
              -> R<Rc<RefCell<Tree>>> {
        self.question = match point {
            Point::Reaction => "reaction",
            Point::ShowdownAction => "showdown",
            _ => "main",
        };
        let tree = Rc::new(RefCell::new(Tree::default()));
        tree.borrow_mut().add();
        let turn = point == Point::TurnAction;
        let info = json!({"seat": self.side.name(), "k": self.searches, "point": point.name(), "turn": g.gs.turn});
        self.cur_search = self.searches;
        self.sim = 0;
        self.searches += 1;
        let fixed = match self.lockstep.as_mut() {
            Some(l) => l.before(&info)?,
            None => None,
        };
        if let Some(n) = fixed {
            for _ in 0..n {
                if turn {
                    self.iterate(g, &tree, cards_played, legal)?;
                } else {
                    self.iterate_now(g, &tree, point, legal, bf_idx)?;
                }
            }
            return Ok(tree);
        }
        let led = match self.budget {
            None => {
                let n = if turn { self.iterations } else { self.reaction_iterations };
                for _ in 0..n {
                    if turn {
                        self.iterate(g, &tree, cards_played, legal)?;
                    } else {
                        self.iterate_now(g, &tree, point, legal, bf_idx)?;
                    }
                }
                n
            }
            Some(b) => {
                let (t0, mut n) = (process_time(), 0usize);
                while n < 1 || process_time() - t0 < b {
                    if turn {
                        self.iterate(g, &tree, cards_played, legal)?;
                    } else {
                        self.iterate_now(g, &tree, point, legal, bf_idx)?;
                    }
                    n += 1;
                }
                if turn {
                    self.main_iters.push(n);
                }
                n
            }
        };
        if let Some(l) = self.lockstep.as_mut() {
            l.after(&info, led)?;
        }
        Ok(tree)
    }

    /// py: _iterate — one simulation of the turn.
    fn iterate(&mut self, g: &Game, tree: &Rc<RefCell<Tree>>, cards_played: i64, root_legal: &[Action])
               -> R<()> {
        let side = self.side;
        let seed = self.seed();
        let mut c = search_copy(&g.gs, side, seed);
        let dbg = self.debug == Some((self.cur_search, self.sim));
        self.sim += 1;
        if dbg {
            self.debug_out.push(json!({"step": "inizio", "seed": seed, "state": c.raw_dump()}));
            c.journal = Some(Vec::new());
        }
        let mut node = 0usize;
        let mut path = vec![0usize];
        let mut cpt = cards_played;
        let value: f64;
        let mut steps = 0;
        loop {
            if steps >= MAX_TURN_ACTIONS {
                value = state_value(&mut c.gs, side);
                break;
            }
            steps += 1;
            if let Some(v) = terminal_value(&c.gs, side) {
                value = v;
                break;
            }
            if c.gs.active != side {
                value = state_value(&mut c.gs, side);
                break;
            }
            let legal_ga = if node == 0 { root_legal.to_vec() } else { c.legal_actions(Point::TurnAction, side)? };
            if legal_ga.is_empty() {
                value = state_value(&mut c.gs, side);
                break;
            }
            if !tree.borrow().nodes[node].expanded {
                let (priors, v) = self.evaluate(&mut c, &legal_ga)?;
                self.expand(&mut tree.borrow_mut(), node, priors, v);
                value = v;
                break;
            }
            let pick = tree.borrow().puct_select(node, &legal_ga, self.c_puct);
            let Some(ci) = pick else {
                value = state_value(&mut c.gs, side);
                break;
            };
            let (key, child) = tree.borrow().nodes[node].children[ci].clone();
            node = child;
            path.push(node);
            if key.kind == AKind::Pass && c.gs.pending_move.is_none() {
                value = state_value(&mut c.gs, side);
                break;
            }
            let tc = Rc::new(RefCell::new(TreeChooser { tree: tree.clone(), me: side, node, path: Vec::new(),
                                                         c_puct: self.c_puct, dbg: if dbg { Some(Vec::new()) } else { None } }));
            let dyn_tc: Rc<RefCell<dyn Chooser>> = tc.clone();
            c.chooser = Some(dyn_tc);
            let r = c.apply_action(side, &key, cpt);
            c.chooser = None;
            r?;
            c.recompute_passives()?;
            cpt += 1;
            if dbg {
                let j: Vec<String> = c.journal.replace(Vec::new()).unwrap_or_default().iter().map(|e| format!("{e:?}")).collect();
                let tree_choices = tc.borrow_mut().dbg.take().unwrap_or_default();
                self.debug_out.push(json!({"step": steps, "action": action_list(&key), "state": c.raw_dump(), "journal": j,
                                           "tree": tree_choices}));
            }
            let t = tc.borrow();
            path.extend(t.path.iter().copied());
            node = t.node;
        }
        if dbg {
            let mut gs = c.gs.clone();
            let o = Observation::from_state(&mut gs, side);
            self.debug_out.push(json!({"step": "fine", "value": value, "obs": obs_summary(&o), "state": c.raw_dump()}));
        }
        tree.borrow_mut().backup(&path, value);
        if self.log.is_some() {
            self.vals.push(value);
        }
        Ok(())
    }

    /// py: _step
    fn step(&self, c: &mut Game, point: Point, action: &Action, bf_idx: Option<usize>) -> R<()> {
        if action.kind == AKind::Pass {
            return Ok(());
        }
        if point == Point::ShowdownAction {
            let bf = bf_idx.ok_or_else(|| EngineError::Invalid("showdown step without a battlefield".into()))?;
            c.showdown_step(self.side, action, bf)?;
        } else {
            c.reaction_step(self.side, action)?;
        }
        Ok(())
    }

    /// py: _settle
    fn settle(c: &mut Game) -> R<()> {
        if !c.gs.chain.is_empty() {
            c.resolve_chain_passing()?;
        }
        if c.gs.showdown_active {
            if let Some(bf) = c.gs.showdown_bf_idx {
                let Some(att) = c.gs.showdown_attacker else {
                    return Err(EngineError::NotPorted { at: "search._settle".into(),
                                                        what: "a showdown with no attacker".into() });
                };
                c.finish_showdown(bf, att)?;
            }
        }
        Ok(())
    }

    /// py: _iterate_now — one simulation of a showdown / chain decision.
    fn iterate_now(&mut self, g: &Game, tree: &Rc<RefCell<Tree>>, point: Point, legal: &[Action],
                   bf_idx: Option<usize>) -> R<()> {
        let side = self.side;
        let seed = self.seed();
        let mut c = search_copy(&g.gs, side, seed);
        if !tree.borrow().nodes[0].expanded {
            let (priors, v) = self.evaluate(&mut c, legal)?;
            let mut t = tree.borrow_mut();
            self.expand(&mut t, 0, priors, v);
            t.backup(&[0], v);
            if self.log.is_some() {
                self.vals.push(v);
            }
            return Ok(());
        }
        let pick = tree.borrow().puct_select(0, legal, self.c_puct);
        let Some(ci) = pick else { return Ok(()) };
        let (key, child) = tree.borrow().nodes[0].children[ci].clone();
        let tc = Rc::new(RefCell::new(TreeChooser { tree: tree.clone(), me: side, node: child, path: Vec::new(),
                                                     c_puct: self.c_puct, dbg: None }));
        let dyn_tc: Rc<RefCell<dyn Chooser>> = tc.clone();
        c.chooser = Some(dyn_tc);
        let r = self.step(&mut c, point, &key, bf_idx).and_then(|_| Self::settle(&mut c));
        c.chooser = None;
        r?;
        let mut path = vec![0, child];
        path.extend(tc.borrow().path.iter().copied());
        let value = match terminal_value(&c.gs, side) {
            Some(v) => v,
            None => state_value(&mut c.gs, side),
        };
        tree.borrow_mut().backup(&path, value);
        if self.log.is_some() {
            self.vals.push(value);
        }
        Ok(())
    }

    /// py: _choices_ahead
    fn choices_ahead(&mut self, g: &Game, action: &Action, point: Point, bf_idx: Option<usize>) -> R<bool> {
        let seed = self.seed();
        let mut c = search_copy(&g.gs, self.side, seed);
        let probe = Rc::new(RefCell::new(Probe { me: self.side, met: false }));
        let dyn_p: Rc<RefCell<dyn Chooser>> = probe.clone();
        c.chooser = Some(dyn_p);
        match self.step(&mut c, point, action, bf_idx).and_then(|_| Self::settle(&mut c)) {
            Ok(()) => {}
            Err(e @ EngineError::NotPorted { .. }) => return Err(e),
            Err(_) => return Ok(false),
        }
        let met = probe.borrow().met;
        Ok(met)
    }

    /// py: _search_now — a decision in a showdown or on an open chain.
    pub fn search_now(&mut self, g: &mut Game, point: Point, bf_idx: Option<usize>) -> R<Action> {
        self.ensure_fallback(g);
        self.release_forced(g, level(point));
        let legal = g.legal_actions(point, self.side)?;
        if legal.len() <= 1 && !(!legal.is_empty() && self.choices_ahead(g, &legal[0], point, bf_idx)?) {
            return Ok(legal.first().cloned().unwrap_or_else(Action::pass));
        }
        let tree = self.search(g, point, &legal, 0, bf_idx)?;
        self.conclude(g, &tree, &legal, point)
    }

    /// py: _conclude + _play
    fn conclude(&mut self, g: &mut Game, tree: &Rc<RefCell<Tree>>, legal: &[Action], point: Point) -> R<Action> {
        let t = tree.borrow();
        let root = &t.nodes[0];
        if root.children.is_empty() || !root.children.iter().any(|(_, c)| t.nodes[*c].n != 0) {
            self.note(g, &t, legal, point, &Action::pass());
            return Ok(Action::pass());
        }
        let mut items: Vec<(Action, usize)> = root.children.iter().filter(|(_, c)| t.nodes[*c].n > 0).cloned().collect();
        if items.is_empty() {
            items = root.children.clone();
        }
        if items.len() > 1 {
            self.decisions += 1;
        }
        let mut best = 0;
        for i in 1..items.len() {
            if t.nodes[items[i].1].q > t.nodes[items[best].1].q {
                best = i;
            }
        }
        let (key, child) = items[best].clone();
        self.note(g, &t, legal, point, &key);
        if !t.nodes[child].choices.is_empty() {
            let plan = Plan { me: self.side, tree: tree.clone(), node: child, level: level(point), turn: g.gs.turn };
            self.stack.borrow_mut().layers.insert(0, Layer::Plan(plan));
        }
        Ok(key)
    }

    fn note(&mut self, g: &Game, t: &Tree, legal: &[Action], point: Point, chosen: &Action) {
        let Some(log) = self.log.as_mut() else { return };
        let root = &t.nodes[0];
        let p: Vec<Value> = root.p.iter().map(|(a, p)| json!([action_list(a), p])).collect();
        fn sub(t: &Tree, n: usize, depth: usize) -> Value {
            let node = &t.nodes[n];
            if depth == 0 || node.choices.is_empty() {
                return Value::Array(Vec::new());
            }
            Value::Array(node.choices.iter().filter(|(_, c, _)| t.nodes[*c].n > 0).map(|(k, c, _)| {
                let x = &t.nodes[*c];
                json!([[k.0, k.1, k.2], x.n, x.q, x.w, sub(t, *c, depth - 1)])
            }).collect())
        }
        let ch: Vec<Value> = root.children.iter()
            .map(|(a, c)| { let n = &t.nodes[*c]; json!([action_list(a), n.n, n.q, n.w, sub(t, *c, 3)]) }).collect();
        log.push(json!({"k": "search", "seat": self.side.name(), "point": point.name(), "turn": g.gs.turn,
                        "menu": legal.iter().map(action_list).collect::<Vec<_>>(), "value": root.value,
                        "P": p, "children": ch, "action": action_list(chosen), "nodes": t.nodes.len(),
                        "vals": std::mem::take(&mut self.vals)}));
    }

    /// py: replay_values — each option of the real loop's choice, its segment
    /// replayed on a copy with that option up to the next decision, valued.
    fn replay_values(&mut self, g: &mut Game, kind: &str, side: Side, options: &[Opt], source: Option<CardId>)
                     -> R<Option<Vec<f64>>> {
        // py: self.loop — the real loop, also when the choice is on a
        // declaration's copy: its options are the copy's, labelled there as
        // objects the real loop does not hold.
        let foreign = g.real_game.is_some();
        let keys = choice_keys(g, kind, side, options, source, foreign)?;
        let real_ptr: *mut Game = g.real_game.unwrap_or(g as *mut Game);
        // SAFETY: the real game's frame runs this choice and does not use the game meanwhile.
        let real: &Game = unsafe { &*real_ptr };
        let (Some(seg), Some(journal)) = (real.segment.clone(), real.journal.clone()) else { return Ok(None) };
        let seed = self.seed();
        let mut values: Vec<f64> = Vec::new();
        for (j, key) in keys.iter().enumerate() {
            if let Some(first) = keys[..j].iter().position(|k| k == key) {
                values.push(values[first]);
                continue;
            }
            let mut gs = seg.gs.clone();
            gs.rng.log = None;
            let cursor = Rc::new(RefCell::new(Cursor { journal: journal.clone(), target: (side, kind.to_string(), options.len()),
                                                       force: j, seed, k: 0, done: false }));
            let mut rl = Game::new(gs);
            for s in Side::BOTH {
                let a: Rc<RefCell<dyn Agent>> = Rc::new(RefCell::new(ReplayAgent(cursor.clone())));
                rl.agents[s.idx()] = Some(a);
                rl.gs.players[s.idx()].has_agent = true;
            }
            let ch: Rc<RefCell<dyn Chooser>> = Rc::new(RefCell::new(CursorChooser(cursor.clone())));
            rl.chooser = Some(ch);
            rl.segment = Some(seg.clone());
            match rl.replay_segment() {
                Ok(()) => {}
                Err(e) if is_stop(&e) => {}
                Err(e @ EngineError::NotPorted { .. }) => return Err(e),
                Err(_) => return Ok(None),
            }
            if !cursor.borrow().done {
                return Ok(None);
            }
            rl.agents = [None, None];
            let v = match terminal_value(&rl.gs, self.side) {
                Some(v) => v,
                None => state_value(&mut rl.gs, self.side),
            };
            values.push(v);
        }
        Ok(Some(values))
    }

    /// py: decide_mulligan / mulligan_values — every keep (up to two cards
    /// back), valued over a few determinized openings; the best.
    pub fn decide_mulligan(&mut self, g: &mut Game) -> R<Vec<i64>> {
        self.release_forced(g, 0);
        let side = self.side;
        let n = g.gs.player(side).hand.len();
        if n == 0 {
            return Ok(Vec::new());
        }
        let worlds: Vec<u64> = (0..self.mulligan_samples.max(1)).map(|_| self.seed()).collect();
        let mut combos: Vec<Vec<i64>> = vec![Vec::new()];
        for i in 0..n {
            combos.push(vec![i as i64]);
        }
        for i in 0..n {
            for j in i + 1..n {
                combos.push(vec![i as i64, j as i64]);
            }
        }
        let (mut best, mut best_v) = (Vec::new(), -1e30);
        let mut rows = Vec::new();
        for combo in combos {
            let mut sum = 0.0;
            for &seed in &worlds {
                let mut c = search_copy(&g.gs, side, seed);
                let mut rng = std::mem::replace(&mut c.gs.rng, PyRandom::new(0));
                c.gs.player_mut(side).mulligan(&combo, &mut rng);
                c.gs.rng = rng;
                sum += state_value(&mut c.gs, side);
            }
            let v = sum / worlds.len() as f64;
            rows.push(json!([combo, v]));
            if v > best_v {
                best_v = v;
                best = combo;
            }
        }
        if let Some(log) = self.log.as_mut() {
            log.push(json!({"k": "mulligan", "seat": side.name(), "values": rows, "chosen": best}));
        }
        Ok(best)
    }
}

/// The search agent the engine asks (py: HandwrittenAgent / PPOPriorAgent).
pub struct SearchAgent {
    pub core: Rc<RefCell<SearchCore>>,
}

impl SearchAgent {
    fn core(&self) -> R<std::cell::RefMut<'_, SearchCore>> {
        self.core.try_borrow_mut().map_err(|_| EngineError::Agent("search: agent asked while it decides".into()))
    }
}

impl Agent for SearchAgent {
    fn decide_action(&mut self, g: &mut Game, _side: Side, cards_played: i64) -> R<Action> {
        self.core()?.decide_action(g, cards_played)
    }
    fn decide_reaction(&mut self, g: &mut Game, _side: Side) -> R<Action> {
        self.core()?.search_now(g, Point::Reaction, None)
    }
    fn decide_showdown_action(&mut self, g: &mut Game, _side: Side, bf_idx: usize) -> R<Action> {
        self.core()?.search_now(g, Point::ShowdownAction, Some(bf_idx))
    }
    fn decide_mulligan(&mut self, g: &mut Game, _side: Side) -> R<Vec<i64>> {
        self.core()?.decide_mulligan(g)
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
}
