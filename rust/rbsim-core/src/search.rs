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
use std::collections::{BTreeMap, VecDeque};
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

/// Valutazione delle foglie. `Storica` = handwritten.table_value (default, parita con Python).
/// `Accumulo`: su un campo controllato dal visualizzatore senza nemici, la Might oltre
/// `need = opp_base_might + k` vale `alpha` volte (invece di 1): l'eccesso non e' preferibile
/// a un'unita' in base, che minaccerebbe il campo avversario.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Valutazione {
    Storica,
    Accumulo { k: f64, alpha: f64 },
    /// Storica + 0.30 * minaccia (vedi `threat`).
    Minaccia,
    /// Storica + w * minaccia, con w secondo la corsa ai punti (`race_info`): 0.45 se si perde, 0.15 se si vince, 0.30 altrimenti.
    Corsa,
    /// Storica, ma solo se si perde la corsa (race == -1) e l'avversario non vince subito: premio 0.04 * min(A, D+2)
    /// verso la conquista del campo avversario con D minima, e Might oltre (Might base avversaria + 3) sui campi
    /// propri sicuri conta 0.2 invece di 1. Negli altri stati = storica. Il premio verso la conquista non conta se un
    /// campo proprio sicuro ha Might sotto `need` (li' il rinforzo vale piu' dell'attacco: dedotto dal caso di controllo).
    Rimonta,
}

/// Corsa ai punti a campi fissi (solo le tenute segnano): -> (race, op_next_wins).
/// La prossima Beginning Phase e' di chi NON e' attivo alla foglia (`o.active`); da li' si alternano le tenute
/// fino a V (massimo 30 passi). race = +1 se il visualizzatore arriva prima, -1 se l'avversario, 0 se nessuno segna.
/// op_next_wins: l'avversario arriva a V alla sua prossima tenuta prima del prossimo turno del visualizzatore.
pub fn race_info(o: &Observation) -> (i64, bool) {
    let me = o.viewer;
    let h_me = o.battlefields.iter().filter(|b| b.controller == Some(me)).count() as i64;
    let h_op = o.battlefields.iter().filter(|b| b.controller == Some(me.other())).count() as i64;
    let v = o.victory_score;
    let next = o.active.other();
    let op_next_wins = next != me && o.opp_points + h_op >= v && h_op > 0;
    if h_me == 0 && h_op == 0 {
        return (0, op_next_wins);
    }
    let (mut pm, mut po, mut turno) = (o.my_points, o.opp_points, next);
    for _ in 0..30 {
        if turno == me {
            pm += h_me;
            if pm >= v {
                return (1, op_next_wins);
            }
        } else {
            po += h_op;
            if po >= v {
                return (-1, op_next_wins);
            }
        }
        turno = turno.other();
    }
    (0, op_next_wins)
}

/// Minaccia in [0,1]: possibilita' del visualizzatore di conquistare un campo avversario al prossimo turno.
/// Attaccanti = Might duratura in base + quella dei suoi GANKING su un altro campo; per ogni campo controllato
/// dall'avversario t = logistica((A - D - 2) / 2), D = Might duratura avversaria li'; minaccia = max. 0 se
/// `op_next_wins` (troppo tardi) o senza attaccanti. Non conta incantesimi che muovono o potenziano.
pub fn threat(o: &Observation, op_next_wins: bool) -> f64 {
    if op_next_wins {
        return 0.0;
    }
    let me = o.viewer;
    let base: i64 = o.my_base_units.iter().map(|u| u.lasting_might).sum();
    let mut best = 0.0f64;
    for (i, bf) in o.battlefields.iter().enumerate() {
        if bf.controller != Some(me.other()) {
            continue;
        }
        let mut a = base;
        for (j, other) in o.battlefields.iter().enumerate() {
            if j != i {
                let mine = if me == Side::A { &other.a } else { &other.b };
                a += mine.iter().filter(|u| u.keywords.contains(&"GANKING")).map(|u| u.lasting_might).sum::<i64>();
            }
        }
        if a <= 0 {
            continue;
        }
        let theirs = if me == Side::A { &bf.b } else { &bf.a };
        let d: i64 = theirs.iter().map(|u| u.lasting_might).sum();
        let t = 1.0 / (1.0 + (-((a - d) as f64 - 2.0) / 2.0).exp());
        best = best.max(t);
    }
    best
}

fn campo_proprio_scoperto(o: &Observation, need: f64) -> bool {
    let me = o.viewer;
    o.battlefields.iter().any(|bf| {
        let (mine_v, theirs_v) = if me == Side::A { (&bf.a, &bf.b) } else { (&bf.b, &bf.a) };
        bf.controller == Some(me) && theirs_v.is_empty() && (mine_v.iter().map(|u| u.lasting_might).sum::<i64>() as f64) < need
    })
}

/// Progresso verso la conquista: min(A, D + 2) con D = Might duratura avversaria minima fra i campi che l'avversario
/// controlla, A = Might duratura in base + dei GANKING miei sugli altri campi. 0 se l'avversario non controlla campi.
pub fn rimonta_progresso(o: &Observation) -> i64 {
    let me = o.viewer;
    let theirs_of = |bf: &crate::obs::BattlefieldView| if me == Side::A { bf.b.clone() } else { bf.a.clone() };
    let target = o.battlefields.iter().enumerate()
        .filter(|(_, bf)| bf.controller == Some(me.other()))
        .map(|(i, bf)| (i, theirs_of(bf).iter().map(|u| u.lasting_might).sum::<i64>()))
        .min_by_key(|&(_, d)| d);
    let Some((i, d)) = target else { return 0 };
    let mut a: i64 = o.my_base_units.iter().map(|u| u.lasting_might).sum();
    for (j, other) in o.battlefields.iter().enumerate() {
        if j != i {
            let mine = if me == Side::A { &other.a } else { &other.b };
            a += mine.iter().filter(|u| u.keywords.contains(&"GANKING")).map(|u| u.lasting_might).sum::<i64>();
        }
    }
    a.max(0).min(d + 2)
}

/// py: handwritten.table_value
pub fn table_value(o: &Observation) -> f64 {
    table_value_v(o, Valutazione::Storica)
}

pub fn table_value_v(o: &Observation, val: Valutazione) -> f64 {
    let me = o.viewer;
    let mut s = 0.45 * ((o.my_points - o.opp_points) as f64);
    let opp_base: i64 = o.opp_base_units.iter().map(|u| u.lasting_might).sum();
    let rimonta = val == Valutazione::Rimonta && {
        let (race, onw) = race_info(o);
        race == -1 && !onw
    };
    for bf in &o.battlefields {
        let (mine_v, theirs_v) = if me == Side::A { (&bf.a, &bf.b) } else { (&bf.b, &bf.a) };
        let mine: i64 = mine_v.iter().map(|u| u.lasting_might).sum();
        let theirs: i64 = theirs_v.iter().map(|u| u.lasting_might).sum();
        if bf.controller == Some(me) {
            s += 0.30;
        } else if bf.controller.is_some() {
            s -= 0.30;
        }
        match val {
            Valutazione::Accumulo { k, alpha } if bf.controller == Some(me) && theirs_v.is_empty() => {
                let need = opp_base as f64 + k;
                let m = mine as f64;
                s += 0.05 * (m.min(need) + alpha * (m - need).max(0.0));
            }
            Valutazione::Rimonta if rimonta && bf.controller == Some(me) && theirs_v.is_empty() => {
                let need = (opp_base + 3) as f64;
                let m = mine as f64;
                s += 0.05 * (m.min(need) + 0.2 * (m - need).max(0.0));
            }
            _ => s += 0.05 * ((mine - theirs) as f64),
        }
    }
    // il premio non conta se un campo proprio sicuro e' sotto `need`: li' il rinforzo vale piu' dell'attacco
    if rimonta && !campo_proprio_scoperto(o, (opp_base + 3) as f64) {
        s += 0.04 * rimonta_progresso(o) as f64;
    }
    let base: i64 = o.my_base_units.iter().map(|u| u.lasting_might).sum::<i64>()
        - o.opp_base_units.iter().map(|u| u.lasting_might).sum::<i64>();
    s += 0.03 * (base as f64);
    s += 0.03 * ((o.my_hand.len() as i64 - o.opp_hand_count as i64) as f64);
    match val {
        Valutazione::Minaccia => {
            let (_, onw) = race_info(o);
            s += 0.30 * threat(o, onw);
        }
        Valutazione::Corsa => {
            let (race, onw) = race_info(o);
            let w = if race < 0 { 0.45 } else if race > 0 { 0.15 } else { 0.30 };
            s += w * threat(o, onw);
        }
        _ => {}
    }
    s.tanh()
}

/// py: table_value(Observation.from_state(gs, side)) (the observation notes
/// battlefield control, as Python's does).
pub fn state_value(gs: &mut GameState, side: Side) -> f64 {
    state_value_v(gs, side, Valutazione::Storica)
}

pub fn state_value_v(gs: &mut GameState, side: Side, val: Valutazione) -> f64 {
    table_value_v(&Observation::from_state(gs, side), val)
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
    /// The probabilities and, when the caller's function gives it, the net's value of the state. The value is
    /// seen from the seat of the observation `x` encodes (the one who decides: PPONet's critic, trained on the
    /// outcome of the observed seat), the same point of view as `table_value`. Default: no value.
    fn eval(&mut self, x: Vec<f32>, q: i64, ctx: [f32; F::F_CTX], descs: &[Descriptor]) -> R<(Vec<f32>, Option<f32>)> {
        Ok((self.probs(x, q, ctx, descs)?, None))
    }
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

/// What the pilots played in one simulation: (seat, point, action label), in order.
type PilotLog = Rc<RefCell<Vec<(Side, &'static str, String)>>>;
type SharedPrior = Rc<RefCell<Box<dyn Prior>>>;

/// The agent a seat of a search copy has with `finestre`: it plays the reaction and showdown windows
/// (nothing else: `has()` is true only for those two) from the PPO prior's probabilities over the
/// legal menu, as seen from its own seat; without a prior, uniform over the menu (Pass included);
/// with one option, that one. Its own RNG, apart from the search's. Choices inside the windows
/// (targets...) still go through the game's choosers. `script` (tests): per point the label
/// prefixes to play in order ("PASS" or an exhausted script pass), a menu with one option taking
/// the only one without using an entry.
pub struct Pilota {
    prior: Option<SharedPrior>,
    rng: PyRandom,
    /// showdown, reaction
    script: Option<[VecDeque<String>; 2]>,
    log: Option<PilotLog>,
}

impl Pilota {
    fn decide(&mut self, g: &mut Game, side: Side, point: Point) -> R<Action> {
        let menu = g.legal_actions(point, side)?;
        let (question, slot, pname) = match point {
            Point::ShowdownAction => ("showdown", 0, "showdown"),
            _ => ("reaction", 1, "reaction"),
        };
        let action = if menu.len() < 2 {
            menu.first().cloned().unwrap_or_else(Action::pass)
        } else if let Some(sc) = self.script.as_mut() {
            match sc[slot].pop_front() {
                None => Action::pass(),
                Some(w) if w == "PASS" => Action::pass(),
                Some(w) => menu.iter().find(|a| a.label.starts_with(&w)).cloned().ok_or_else(|| {
                    let labels: Vec<&str> = menu.iter().map(|a| a.label.as_str()).collect();
                    EngineError::Agent(format!("pilot script: {w:?} is not legal: {labels:?}"))
                })?,
            }
        } else if let Some(net) = self.prior.clone() {
            let obs = Observation::from_state(&mut g.gs, side);
            let descs = on_fresh_loop(g, |fg| -> R<Vec<Descriptor>> {
                menu.iter().map(|a| F::describe_action(fg, side, a)).collect()
            })?;
            let x = encode_observation(&obs, &g.gs.reg);
            let ctx = F::context(descs.len(), 0, false, false);
            let probs = net.borrow_mut().probs(x, F::question_of(question), ctx, &descs)?;
            let total: f64 = probs.iter().map(|&p| p.max(0.0) as f64).sum();
            if total > 0.0 && total.is_finite() {
                let r = self.rng.random() * total;
                let mut acc = 0.0;
                let mut pick = menu.len() - 1;
                for (i, &p) in probs.iter().enumerate().take(menu.len()) {
                    acc += p.max(0.0) as f64;
                    if r < acc {
                        pick = i;
                        break;
                    }
                }
                menu[pick].clone()
            } else {
                menu[self.rng.choice_index(menu.len())].clone()
            }
        } else {
            menu[self.rng.choice_index(menu.len())].clone()
        };
        if let Some(l) = self.log.as_ref() {
            let label = if action.kind == AKind::Pass { "PASS".to_string() } else { action.label.clone() };
            l.borrow_mut().push((side, pname, label));
        }
        Ok(action)
    }
}

impl Agent for Pilota {
    fn decide_action(&mut self, _: &mut Game, _: Side, _: i64) -> R<Action> {
        Err(EngineError::Py("AttributeError: decide_action".into()))
    }
    fn decide_reaction(&mut self, g: &mut Game, side: Side) -> R<Action> {
        self.decide(g, side, Point::Reaction)
    }
    fn decide_showdown_action(&mut self, g: &mut Game, side: Side, _bf: usize) -> R<Action> {
        self.decide(g, side, Point::ShowdownAction)
    }
    fn decide_mulligan(&mut self, _: &mut Game, _: Side) -> R<Vec<i64>> {
        Err(EngineError::Py("AttributeError: decide_mulligan".into()))
    }
    fn decide_optional(&mut self, _: &mut Game, _: Side, _: CardId, _: &str) -> R<bool> {
        Err(EngineError::Py("AttributeError: decide_optional".into()))
    }
    fn decide_mode(&mut self, _: &mut Game, _: Side, _: CardId, _: i64) -> R<Option<i64>> {
        Err(EngineError::Py("AttributeError: decide_mode".into()))
    }
    fn decide_predict_recycle(&mut self, _: &mut Game, _: Side, _: CardId) -> R<bool> {
        Err(EngineError::Py("AttributeError: decide_predict_recycle".into()))
    }
    fn has(&self, method: &str) -> bool {
        matches!(method, "decide_showdown_action" | "decide_reaction")
    }
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

    /// Root quota: among the children whose label contains one of `subs` (lower case) and that have
    /// fewer than `n` visits, the one with the fewest (ties: menu order); None when there is none.
    fn quota_select(&self, node: usize, legal: &[Action], subs: &[String], n: usize) -> Option<usize> {
        let mut best: Option<(usize, i64)> = None;
        for (i, (a, c)) in self.nodes[node].children.iter().enumerate() {
            if !legal.iter().any(|l| l.same(a)) {
                continue;
            }
            let label = a.label.to_lowercase();
            if !subs.iter().any(|x| label.contains(x.as_str())) {
                continue;
            }
            let v = self.nodes[*c].n;
            if v < n as i64 && best.map_or(true, |(_, bv)| v < bv) {
                best = Some((i, v));
            }
        }
        best.map(|b| b.0)
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
/// Option `esplorazione` (default off, only for collecting games): Dirichlet noise at the turn
/// search's root, and the first `mosse` searched turn decisions of the seat sampled by visits.
#[derive(Clone, Copy, Debug)]
pub struct Esplorazione {
    pub alfa: f64,
    pub eps: f64,
    pub mosse: usize,
}

/// What `evaluate` gave the net for a root: the inputs of a training example.
#[derive(Clone, Debug)]
pub struct RootIn {
    pub x: Vec<f32>,
    pub q: i64,
    pub ctx: [f32; F::F_CTX],
    pub descs: Vec<Descriptor>,
}

/// Option `registro`: one record per decision of the seat. `kind`: "cercata" (a search ran: P, N, Q and the
/// net's inputs), "forzata" (one option), "sonda" (the win probe decided), "prima" (the first forced move).
#[derive(Clone, Debug)]
pub struct Record {
    pub kind: &'static str,
    pub turn: i64,
    pub point: &'static str,
    pub menu: Vec<String>,
    pub azioni: Vec<Value>,
    pub giocata: i64,
    pub p: Vec<f64>,
    pub p_rumore: Option<Vec<f64>>,
    pub n: Vec<i64>,
    pub q: Vec<f64>,
    pub iters: usize,
    pub campionata: bool,
    pub input: Option<RootIn>,
}

/// Gamma(a, 1) by Marsaglia-Tsang (a < 1 through Gamma(a+1) * U^(1/a)), from `rng`'s uniforms.
fn gamma_mt(rng: &mut PyRandom, a: f64) -> f64 {
    if a < 1.0 {
        let u = 1.0 - rng.random();
        return gamma_mt(rng, a + 1.0) * u.powf(1.0 / a);
    }
    let d = a - 1.0 / 3.0;
    let c = 1.0 / (9.0 * d).sqrt();
    loop {
        let (u1, u2) = (1.0 - rng.random(), rng.random());
        let x = (-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos();
        let v = 1.0 + c * x;
        if v <= 0.0 {
            continue;
        }
        let v = v * v * v;
        let u = 1.0 - rng.random();
        if u.ln() < 0.5 * x * x + d - d * v + d * v.ln() {
            return d * v;
        }
    }
}

pub struct SearchCore {
    pub side: Side,
    pub iterations: usize,
    pub reaction_iterations: usize,
    pub c_puct: f64,
    pub mulligan_samples: usize,
    pub budget: Option<f64>,
    pub rng: PyRandom,
    pub prior: Option<SharedPrior>,
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
    /// Observation only: iterations / CPU seconds of the last search and the win-probe seconds since.
    pub timing: bool,
    last_iters: usize,
    last_secs: f64,
    probe_secs: f64,
    /// Diagnosis: (search, simulation) whose copy is dumped at every step
    /// into `debug_out` (raw states, the leaf's observation and value).
    pub debug: Option<(usize, usize)>,
    pub debug_out: Vec<Value>,
    cur_search: usize,
    sim: usize,
    me_ref: Option<Weak<RefCell<SearchCore>>>,
    /// Opt-in (off by default): before searching, look for a win this turn by moves.
    pub win_probe: bool,
    /// Valutazione delle foglie (default Storica).
    pub valutazione: Valutazione,
    /// Diagnosi: la ricerca di indice k (come `info["k"]`) usa questa valutazione.
    pub valutazione_at: Option<(usize, Valutazione)>,
    /// Diagnosi: la ricerca di indice k (come `info["k"]`) usa questo peso del valore della rete (le altre `peso_valore_rete`).
    pub valore_rete_at: Option<(usize, f64)>,
    /// Diagnosis (decisione_rs): the search with this index (k, as `info["k"]`) does exactly this
    /// many iterations at a fixed workload, whatever the point or the budget; nothing else changes.
    pub override_at: Option<(usize, usize)>,
    /// Option `finestre` (default off): the simulations play the reaction and showdown windows for both
    /// seats with a `Pilota` each; a window search resumes the window as the real loop would go on.
    pub finestre: bool,
    /// Diagnosis: `finestre` only for the search with this index (k, as `info["k"]`).
    /// Per-search override of `finestre` (search index, on/off); otherwise `finestre` holds.
    pub finestre_at: Option<(usize, bool)>,
    /// Option `quota` (default off): (label substrings, n): in the turn search's root, while a child whose
    /// label contains one of them has fewer than n visits, the one with the fewest is simulated (not PUCT).
    pub quota: Option<(Vec<String>, usize)>,
    /// Diagnosis: the quota only for the search with this index.
    pub quota_at: Option<(usize, Vec<String>, usize)>,
    /// Tests: scripted pilots instead of sampled ones, per seat (showdown, reaction) label prefixes.
    pub pilot_script: Option<[(Vec<String>, Vec<String>); 2]>,
    /// Tests: the diagnosis also keeps each simulation's window plays.
    pub diag_trace: bool,
    /// Continuations: the seat's first turn decision plays the first legal action whose label contains this
    /// (case-insensitive); then the search goes on as usual.
    pub first_forced: Option<String>,
    /// Diagnosis, one entry per search that ran with `finestre` or a quota: per root child its visits, q and
    /// the tally of the pilots' window plays (seat, point, label) in its simulations.
    pub diag: Vec<Value>,
    cur_fin: bool,
    cur_quota: Option<(Vec<String>, usize)>,
    tally: BTreeMap<usize, BTreeMap<(String, String, String), i64>>,
    sim_traces: Vec<Value>,
    sim_seeds: Vec<u64>,
    /// Option `esplorazione` (default off) and the searched turn decisions made so far.
    pub esplorazione: Option<Esplorazione>,
    esp_mosse: usize,
    esp_rng: Option<PyRandom>,
    /// Option `registro` (default off): the records, drained by the caller.
    pub registro: bool,
    pub records: Vec<Record>,
    /// Of the current search: the root's inputs and priors (before the noise), the priors after it.
    root_in: Option<RootIn>,
    root_p_pre: Option<Vec<(Action, f64)>>,
    root_noised: bool,
    /// Option `peso_valore_rete` (default 0 = off: nothing changes): leaf value of a node evaluated with the net =
    /// (1 - w) * hand-written value + w * net's value (same point of view: the searching seat).
    pub peso_valore_rete: f64,
    /// Statistics: calls of the net's forward, and those made only for the value (menus of fewer than 2
    /// options, with `peso_valore_rete` > 0; they were not made before).
    pub chiamate_rete: i64,
    pub chiamate_solo_valore: i64,
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
            prior: prior.map(|p| Rc::new(RefCell::new(p))),
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
            timing: false,
            last_iters: 0,
            last_secs: 0.0,
            probe_secs: 0.0,
            debug: None,
            debug_out: Vec::new(),
            cur_search: 0,
            sim: 0,
            me_ref: None,
            win_probe: false,
            valutazione: Valutazione::Storica,
            valutazione_at: None,
            valore_rete_at: None,
            override_at: None,
            finestre: false,
            finestre_at: None,
            quota: None,
            quota_at: None,
            pilot_script: None,
            diag_trace: false,
            first_forced: None,
            diag: Vec::new(),
            cur_fin: false,
            cur_quota: None,
            tally: BTreeMap::new(),
            sim_traces: Vec::new(),
            sim_seeds: Vec::new(),
            esplorazione: None,
            esp_mosse: 0,
            esp_rng: None,
            registro: false,
            records: Vec::new(),
            root_in: None,
            root_p_pre: None,
            root_noised: false,
            peso_valore_rete: 0.0,
            chiamate_rete: 0,
            chiamate_solo_valore: 0,
        }));
        core.borrow_mut().me_ref = Some(Rc::downgrade(&core));
        LIVE_CORES.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        core
    }

    fn seed(&mut self) -> u64 {
        self.rng.randrange(1 << 30)
    }

    /// The generator of the exploration, derived from the search's own one the first time it is needed.
    fn esp_rng(&mut self) -> &mut PyRandom {
        if self.esp_rng.is_none() {
            let sd = self.seed();
            self.esp_rng = Some(PyRandom::new(sd as i128 * 2 + 0x5EED_0000));
        }
        self.esp_rng.as_mut().unwrap()
    }

    /// The turn search's root, just evaluated: keep the priors as they are (for the record) and, with
    /// `esplorazione`, mix in Dirichlet noise when the root has at least two distinct actions.
    fn root_noise(&mut self, priors: &mut Vec<(Action, f64)>) {
        if self.question != "main" {
            return;
        }
        if self.registro {
            self.root_p_pre = Some(priors.clone());
        }
        let Some(e) = self.esplorazione else { return };
        if priors.len() < 2 || e.eps <= 0.0 {
            return;
        }
        let rng = self.esp_rng();
        let mut d: Vec<f64> = priors.iter().map(|_| gamma_mt(rng, e.alfa)).collect();
        let sum: f64 = d.iter().sum();
        if !(sum > 0.0) {
            return;
        }
        for x in d.iter_mut() {
            *x /= sum;
        }
        for ((_, p), n) in priors.iter_mut().zip(d) {
            *p = (1.0 - e.eps) * *p + e.eps * n;
        }
        self.root_noised = true;
    }

    /// A light record (a decision without a search).
    fn registra_leggero(&mut self, kind: &'static str, turn: i64, point: Point, legal: &[Action], chosen: &Action) {
        if !self.registro {
            return;
        }
        let giocata = legal.iter().position(|a| a.same(chosen)).map_or(-1, |i| i as i64);
        self.records.push(Record {
            kind, turn, point: point.name(), menu: legal.iter().map(|a| a.label.clone()).collect(), azioni: Vec::new(),
            giocata, p: Vec::new(), p_rumore: None, n: Vec::new(), q: Vec::new(), iters: 0, campionata: false, input: None,
        });
    }

    /// The full record of a searched decision.
    fn registra(&mut self, turn: i64, t: &Tree, legal: &[Action], point: Point, chosen: &Action, campionata: bool) {
        if !self.registro {
            return;
        }
        let root = &t.nodes[0];
        let find_p = |src: &[(Action, f64)], a: &Action| src.iter().find(|(k, _)| k.same(a)).map_or(0.0, |(_, p)| *p);
        let (pre, post): (Vec<f64>, Option<Vec<f64>>) = match &self.root_p_pre {
            Some(pre) => (legal.iter().map(|a| find_p(pre, a)).collect(),
                          if self.root_noised { Some(legal.iter().map(|a| find_p(&root.p, a)).collect()) } else { None }),
            None => (legal.iter().map(|a| find_p(&root.p, a)).collect(), None),
        };
        let (mut n, mut q) = (Vec::new(), Vec::new());
        for a in legal {
            match root.children.iter().find(|(k, _)| k.same(a)) {
                Some((_, c)) if t.nodes[*c].n > 0 => {
                    n.push(t.nodes[*c].n);
                    q.push(t.nodes[*c].q);
                }
                _ => {
                    n.push(0);
                    q.push(f64::NAN);
                }
            }
        }
        let giocata = legal.iter().position(|a| a.same(chosen)).map_or(-1, |i| i as i64);
        self.records.push(Record {
            kind: "cercata", turn, point: point.name(), menu: legal.iter().map(|a| a.label.clone()).collect(),
            azioni: legal.iter().map(action_list).collect(), giocata, p: pre, p_rumore: post, n, q,
            iters: self.last_iters, campionata, input: self.root_in.take(),
        });
    }

    /// py: _evaluate — (priors over the menu, value).
    fn evaluate(&mut self, c: &mut Game, legal: &[Action]) -> R<(Vec<(Action, f64)>, f64)> {
        let side = self.side;
        match self.prior.clone() {
            None => {
                let u = 1.0 / legal.len().max(1) as f64;
                let mut p = Vec::new();
                for a in legal {
                    dict_set(&mut p, a, u);
                }
                let v = state_value_v(&mut c.gs, side, self.valutazione);
                Ok((p, v))
            }
            Some(net) => {
                let obs = Observation::from_state(&mut c.gs, side);
                let tv = table_value_v(&obs, self.valutazione);
                let w = self.peso_valore_rete;
                let mut p = Vec::new();
                if legal.len() < 2 {
                    for a in legal {
                        dict_set(&mut p, a, 1.0);
                    }
                    // Only with the value weight on: one forward for the value alone (a one-option menu).
                    if w > 0.0 && legal.len() == 1 {
                        let descs = on_fresh_loop(c, |fg| -> R<Vec<Descriptor>> {
                            legal.iter().map(|a| F::describe_action(fg, side, a)).collect()
                        })?;
                        let x = encode_observation(&obs, &c.gs.reg);
                        let q = F::question_of(self.question);
                        let ctx = F::context(descs.len(), 0, false, false);
                        let (_, nv) = net.borrow_mut().eval(x, q, ctx, &descs)?;
                        self.chiamate_rete += 1;
                        self.chiamate_solo_valore += 1;
                        if let Some(nv) = nv {
                            return Ok((p, (1.0 - w) * tv + w * nv as f64));
                        }
                    }
                    return Ok((p, tv));
                }
                let descs = on_fresh_loop(c, |fg| -> R<Vec<Descriptor>> {
                    legal.iter().map(|a| F::describe_action(fg, side, a)).collect()
                })?;
                let x = encode_observation(&obs, &c.gs.reg);
                let q = F::question_of(self.question);
                let ctx = F::context(descs.len(), 0, false, false);
                if self.registro && self.root_in.is_none() {
                    self.root_in = Some(RootIn { x: x.clone(), q, ctx, descs: descs.clone() });
                }
                let (probs, nv) = net.borrow_mut().eval(x, q, ctx, &descs)?;
                self.chiamate_rete += 1;
                for (a, pr) in legal.iter().zip(probs) {
                    dict_add(&mut p, a, pr as f64);
                }
                let v = match nv {
                    Some(nv) if w > 0.0 => (1.0 - w) * tv + w * nv as f64,
                    _ => tv,
                };
                Ok((p, v))
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
        if let Some(sub) = self.first_forced.take() {
            let sub = sub.to_lowercase();
            return match root_legal.iter().find(|a| a.label.to_lowercase().contains(&sub)) {
                Some(a) => {
                    let a = a.clone();
                    self.registra_leggero("prima", g.gs.turn, Point::TurnAction, &root_legal, &a);
                    Ok(a)
                }
                None => Err(EngineError::Agent(format!("first forced move not legal: {sub}"))),
            };
        }
        if root_legal.len() <= 1 {
            let a = root_legal.first().cloned().unwrap_or_else(Action::pass);
            self.registra_leggero("forzata", g.gs.turn, Point::TurnAction, &root_legal, &a);
            return Ok(a);
        }
        let probed = if self.win_probe && self.lockstep.is_none() {
            let t_probe = process_time();
            let r = self.win_this_turn(g, &root_legal, cards_played);
            self.probe_secs += process_time() - t_probe;
            r?
        } else {
            None
        };
        let action = match probed {
            Some(a) => {
                self.registra_leggero("sonda", g.gs.turn, Point::TurnAction, &root_legal, &a);
                a
            }
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
    /// wins this turn by conquests and that the opponent cannot answer: the
    /// opponent has no energy, a watcher agent on the opponent seat of every
    /// copy flags any showdown/reaction option besides Pass (a branch where it
    /// fires is dead), and a line found on one determinization must win on 8 more.
    /// Uses no `self.rng`. Some(first action) or None.
    fn win_this_turn(&mut self, g: &Game, root_legal: &[Action], cards_played: i64) -> R<Option<Action>> {
        const PROBE_SEED: u64 = 0x5EED;
        const MAX_DEPTH: usize = 8;
        const MAX_APPLIES: usize = 3000;
        const EXTRA_SEEDS: u64 = 8;
        let side = self.side;
        if g.gs.player(side.other()).energy() != 0 {
            return Ok(None);
        }
        let n_bf = g.gs.battlefields.len() as i64;
        let need = g.gs.victory_score - g.gs.points[side.idx()];
        let unscored = g.gs.battlefields.iter().filter(|b| !b.scored_this_turn[side.idx()]).count() as i64;
        if need < 1 || need > unscored {
            return Ok(None);
        }
        let mut applies = 0usize;
        let mut stack: Vec<Vec<Action>> = vec![Vec::new()];
        while let Some(prefix) = stack.pop() {
            // The menu of this node, and whether a Pass here commits a pending move.
            let (legal, commit): (Vec<Action>, bool) = if prefix.is_empty() {
                (root_legal.to_vec(), matches!(g.gs.pending_move, Some((_, s)) if s == side))
            } else {
                let Some(mut c) = Self::probe_replay(&g.gs, side, PROBE_SEED, &prefix, cards_played, &mut applies, MAX_APPLIES)
                else {
                    if applies > MAX_APPLIES {
                        return Ok(None);
                    }
                    continue;
                };
                match c.legal_actions(Point::TurnAction, side) {
                    Ok(l) => (l, matches!(c.gs.pending_move, Some((_, s)) if s == side)),
                    Err(_) => continue,
                }
            };
            for a in legal.iter() {
                let ok = match a.kind {
                    AKind::Move => matches!(a.dst, Some(d) if d >= 0 && d < n_bf),
                    AKind::Pass => commit,
                    _ => false,
                };
                if !ok {
                    continue;
                }
                let mut line = prefix.clone();
                line.push(a.clone());
                let Some(c) = Self::probe_replay(&g.gs, side, PROBE_SEED, &line, cards_played, &mut applies, MAX_APPLIES)
                else {
                    if applies > MAX_APPLIES {
                        return Ok(None);
                    }
                    continue;
                };
                match terminal_value(&c.gs, side) {
                    Some(v) if v == 1.0 => {
                        let mut all = true;
                        for k in 1..=EXTRA_SEEDS {
                            let r = Self::probe_replay(&g.gs, side, PROBE_SEED + k, &line, cards_played, &mut applies, MAX_APPLIES);
                            match r {
                                Some(c2) if terminal_value(&c2.gs, side) == Some(1.0) => {}
                                Some(_) => {
                                    all = false;
                                    break;
                                }
                                None => {
                                    if applies > MAX_APPLIES {
                                        return Ok(None);
                                    }
                                    all = false;
                                    break;
                                }
                            }
                        }
                        if all {
                            if let Some(log) = self.log.as_mut() {
                                let labels: Vec<String> = line.iter().map(|x| x.label.clone()).collect();
                                log.push(json!({"k": "vittoria", "seat": side.name(), "turn": g.gs.turn, "line": labels}));
                            }
                            return Ok(Some(line[0].clone()));
                        }
                    }
                    Some(_) => {}
                    None => {
                        if c.gs.active == side && line.len() < MAX_DEPTH {
                            stack.push(line);
                        }
                    }
                }
            }
        }
        Ok(None)
    }

    /// A fresh copy of the root (determinized with `seed`) with `prefix` applied, a watcher on
    /// the opponent seat. None: an error, a response by the opponent, or the apply cap (then
    /// `applies > max`). Stops early at a terminal state or when the turn passes to the other side.
    fn probe_replay(gs: &GameState, side: Side, seed: u64, prefix: &[Action], cards_played: i64,
                    applies: &mut usize, max: usize) -> Option<Game> {
        let mut c = search_copy(gs, side, seed);
        let flag = Rc::new(std::cell::Cell::new(false));
        let w: Rc<RefCell<dyn Agent>> = Rc::new(RefCell::new(crate::agent::Watcher { responded: flag.clone() }));
        c.agents[side.other().idx()] = Some(w);
        for (i, a) in prefix.iter().enumerate() {
            if *applies >= max {
                *applies = max + 1;
                return None;
            }
            *applies += 1;
            if c.apply_action(side, a, cards_played + i as i64).is_err() || c.recompute_passives().is_err() {
                return None;
            }
            if flag.get() {
                return None;
            }
            if terminal_value(&c.gs, side).is_some() || c.gs.active != side {
                break;
            }
        }
        Some(c)
    }

    /// Con `valutazione_at = (k, v)` la ricerca di indice k usa la valutazione v (le altre `valutazione`).
    fn search(&mut self, g: &mut Game, point: Point, legal: &[Action], cards_played: i64, bf_idx: Option<usize>)
              -> R<Rc<RefCell<Tree>>> {
        let saved = self.valutazione;
        if let Some((k, v)) = self.valutazione_at {
            if k == self.searches {
                self.valutazione = v;
            }
        }
        // Peso del valore della rete solo alla ricerca k (come `valutazione_at`).
        let saved_peso = self.peso_valore_rete;
        if let Some((k, w)) = self.valore_rete_at {
            if k == self.searches {
                self.peso_valore_rete = w;
            }
        }
        let k = self.searches;
        self.cur_fin = match self.finestre_at {
            Some((kk, on)) if kk == k => on,
            _ => self.finestre,
        };
        self.cur_quota = match &self.quota_at {
            Some((qk, labels, n)) if *qk == k => Some((labels.clone(), *n)),
            _ => self.quota.clone(),
        }
        .map(|(l, n)| (l.iter().map(|x| x.to_lowercase()).collect(), n));
        self.tally.clear();
        self.sim_traces.clear();
        self.sim_seeds.clear();
        let r = self.search_inner(g, point, legal, cards_played, bf_idx);
        self.valutazione = saved;
        self.peso_valore_rete = saved_peso;
        if let Ok(tree) = &r {
            if self.cur_fin || self.cur_quota.is_some() || self.diag_trace {
                self.finish_diag(&tree.borrow(), k, point, g.gs.turn);
            }
        }
        self.cur_fin = false;
        self.cur_quota = None;
        r
    }

    /// A copy of the game for one simulation; with `finestre` a `Pilota` on each seat, its RNG derived
    /// from the simulation's `seed` (never drawn from `self.rng`: the hidden worlds stay the same).
    fn sim_copy(&self, gs: &GameState, side: Side, seed: u64) -> (Game, Option<PilotLog>) {
        let mut c = search_copy(gs, side, seed);
        if !self.cur_fin {
            return (c, None);
        }
        let log: PilotLog = Rc::new(RefCell::new(Vec::new()));
        for s in Side::BOTH {
            let script = self.pilot_script.as_ref().map(|ps| {
                let (sd, re) = &ps[s.idx()];
                [sd.iter().cloned().collect::<VecDeque<_>>(), re.iter().cloned().collect::<VecDeque<_>>()]
            });
            let p: Rc<RefCell<dyn Agent>> = Rc::new(RefCell::new(Pilota {
                prior: self.prior.clone(),
                rng: PyRandom::new((seed as i128) * 2 + s.idx() as i128),
                script,
                log: Some(log.clone()),
            }));
            c.agents[s.idx()] = Some(p);
        }
        (c, Some(log))
    }

    /// The pilots' window plays of a finished simulation, to the tally of its root child.
    fn record_sim(&mut self, child: Option<(usize, &Action)>, plog: Option<PilotLog>, c: &Game) {
        let Some((ci, a)) = child else { return };
        let plays: Vec<(Side, &'static str, String)> = plog.map(|l| l.borrow().clone()).unwrap_or_default();
        let t = self.tally.entry(ci).or_default();
        for (seat, point, label) in plays.iter() {
            *t.entry((seat.name().to_string(), point.to_string(), label.clone())).or_insert(0) += 1;
        }
        if self.diag_trace {
            let w: Vec<Value> = plays.iter().map(|(s, p, l)| json!([s.name(), p, l])).collect();
            self.sim_traces.push(json!({"child": a.label, "window": w,
                                        "end": {"chain": c.gs.chain.len(), "showdown": c.gs.showdown_active}}));
        }
    }

    fn finish_diag(&mut self, t: &Tree, k: usize, point: Point, turn: i64) {
        let kids: Vec<Value> = t.nodes[0].children.iter().enumerate().map(|(i, (a, c))| {
            let n = &t.nodes[*c];
            let tally: Vec<Value> = self.tally.get(&i).map(|m| m.iter()
                .map(|((s, p, l), x)| json!([s, p, l, x])).collect()).unwrap_or_default();
            json!({"label": a.label, "n": n.n, "q": if n.n > 0 { json!(n.q) } else { Value::Null }, "tally": tally})
        }).collect();
        let mut row = json!({"k": k, "seat": self.side.name(), "point": point.name(), "turn": turn,
                             "finestre": self.cur_fin, "children": kids});
        if self.diag_trace {
            row["sims"] = Value::Array(std::mem::take(&mut self.sim_traces));
            row["seeds"] = json!(std::mem::take(&mut self.sim_seeds));
        }
        self.diag.push(row);
    }

    /// py: search (and _Budget.search): the root is node 0.
    fn search_inner(&mut self, g: &mut Game, point: Point, legal: &[Action], cards_played: i64, bf_idx: Option<usize>)
              -> R<Rc<RefCell<Tree>>> {
        self.question = match point {
            Point::Reaction => "reaction",
            Point::ShowdownAction => "showdown",
            _ => "main",
        };
        let tree = Rc::new(RefCell::new(Tree::default()));
        tree.borrow_mut().add();
        let turn = point == Point::TurnAction;
        let t_search = process_time();
        let info = json!({"seat": self.side.name(), "k": self.searches, "point": point.name(), "turn": g.gs.turn});
        self.cur_search = self.searches;
        self.sim = 0;
        self.searches += 1;
        self.root_in = None;
        self.root_p_pre = None;
        self.root_noised = false;
        let fixed = match (self.override_at, self.lockstep.as_mut()) {
            (Some((k, n)), _) if k == self.cur_search => Some(n),
            (_, Some(l)) => l.before(&info)?,
            _ => None,
        };
        if let Some(n) = fixed {
            for _ in 0..n {
                if turn {
                    self.iterate(g, &tree, cards_played, legal)?;
                } else {
                    self.iterate_now(g, &tree, point, legal, bf_idx)?;
                }
            }
            self.last_iters = n;
            self.last_secs = process_time() - t_search;
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
        self.last_iters = led;
        self.last_secs = process_time() - t_search;
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
        if self.diag_trace {
            self.sim_seeds.push(seed);
        }
        let (mut c, plog) = self.sim_copy(&g.gs, side, seed);
        let mut root_child: Option<(usize, Action)> = None;
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
                value = state_value_v(&mut c.gs, side, self.valutazione);
                break;
            }
            steps += 1;
            if let Some(v) = terminal_value(&c.gs, side) {
                value = v;
                break;
            }
            if c.gs.active != side {
                value = state_value_v(&mut c.gs, side, self.valutazione);
                break;
            }
            let legal_ga = if node == 0 { root_legal.to_vec() } else { c.legal_actions(Point::TurnAction, side)? };
            if legal_ga.is_empty() {
                value = state_value_v(&mut c.gs, side, self.valutazione);
                break;
            }
            if !tree.borrow().nodes[node].expanded {
                let (mut priors, v) = self.evaluate(&mut c, &legal_ga)?;
                if node == 0 {
                    self.root_noise(&mut priors);
                }
                self.expand(&mut tree.borrow_mut(), node, priors, v);
                value = v;
                break;
            }
            let quota = match (&self.cur_quota, node) {
                (Some((subs, n)), 0) => tree.borrow().quota_select(0, &legal_ga, subs, *n),
                _ => None,
            };
            let pick = quota.or_else(|| tree.borrow().puct_select(node, &legal_ga, self.c_puct));
            let Some(ci) = pick else {
                value = state_value_v(&mut c.gs, side, self.valutazione);
                break;
            };
            let (key, child) = tree.borrow().nodes[node].children[ci].clone();
            if node == 0 {
                root_child = Some((ci, key.clone()));
            }
            node = child;
            path.push(node);
            if key.kind == AKind::Pass && c.gs.pending_move.is_none() {
                value = state_value_v(&mut c.gs, side, self.valutazione);
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
        self.record_sim(root_child.as_ref().map(|(i, a)| (*i, a)), plog, &c);
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
        if self.diag_trace {
            self.sim_seeds.push(seed);
        }
        let (mut c, plog) = self.sim_copy(&g.gs, side, seed);
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
        let r = if self.cur_fin {
            self.resume(g, &mut c, point, &key).and_then(|done| {
                if done {
                    Ok(())
                } else {
                    self.step(&mut c, point, &key, bf_idx).and_then(|_| Self::settle(&mut c))
                }
            })
        } else {
            self.step(&mut c, point, &key, bf_idx).and_then(|_| Self::settle(&mut c))
        };
        c.chooser = None;
        r?;
        let mut path = vec![0, child];
        path.extend(tc.borrow().path.iter().copied());
        let value = match terminal_value(&c.gs, side) {
            Some(v) => v,
            None => state_value_v(&mut c.gs, side, self.valutazione),
        };
        tree.borrow_mut().backup(&path, value);
        if self.log.is_some() {
            self.vals.push(value);
        }
        self.record_sim(Some((ci, &key)), plog, &c);
        Ok(())
    }

    /// With `finestre`, a window search's simulation after our action `action`: the window goes on
    /// exactly as the real loop would, from the (side, passes) recorded when we were asked, the pilots
    /// playing both seats, up to what the loop does after it (finish_showdown, hidden cards, staged
    /// showdowns). Ok(false): no record of the window (the caller settles the old way).
    fn resume(&self, g: &Game, c: &mut Game, point: Point, action: &Action) -> R<bool> {
        match point {
            Point::ShowdownAction => {
                let Some((fp, passes, bf, att)) = g.win_show else { return Ok(false) };
                if fp != self.side {
                    return Ok(false);
                }
                let p = c.showdown_apply(fp, passes, action, bf, att)?;
                c.showdown_loop(bf, att, p)?;
                Ok(true)
            }
            Point::Reaction => {
                let Some((active, passes)) = g.win_chain else { return Ok(false) };
                if active != self.side {
                    return Ok(false);
                }
                let (a, p) = c.chain_apply(active, passes, action)?;
                c.run_chain_from(a, p)?;
                // The chain was opened by a step of an open showdown: its loop goes on after it.
                if c.gs.showdown_active {
                    if let Some((_, _, bf, att)) = g.win_show {
                        if c.gs.showdown_bf_idx == Some(bf) {
                            c.showdown_after_acted(bf, att)?;
                        }
                    }
                }
                Ok(true)
            }
            _ => Ok(false),
        }
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
            let a = legal.first().cloned().unwrap_or_else(Action::pass);
            self.registra_leggero("forzata", g.gs.turn, point, &legal, &a);
            return Ok(a);
        }
        let tree = self.search(g, point, &legal, 0, bf_idx)?;
        self.conclude(g, &tree, &legal, point)
    }

    /// py: _conclude + _play
    fn conclude(&mut self, g: &mut Game, tree: &Rc<RefCell<Tree>>, legal: &[Action], point: Point) -> R<Action> {
        let t = tree.borrow();
        let root = &t.nodes[0];
        if root.children.is_empty() || !root.children.iter().any(|(_, c)| t.nodes[*c].n != 0) {
            self.registra(g.gs.turn, &t, legal, point, &Action::pass(), false);
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
        let mut campionata = false;
        if self.esplorazione.is_none() {
            for i in 1..items.len() {
                if t.nodes[items[i].1].q > t.nodes[items[best].1].q {
                    best = i;
                }
            }
        } else {
            // Exploring: the most visited (ties: the higher Q, then the menu order); a turn decision among
            // the first `mosse` of the seat is sampled in proportion to the visits instead.
            for i in 1..items.len() {
                let (a, b) = (&t.nodes[items[i].1], &t.nodes[items[best].1]);
                if a.n > b.n || (a.n == b.n && a.q > b.q) {
                    best = i;
                }
            }
            if point == Point::TurnAction {
                let e = self.esplorazione.unwrap();
                if self.esp_mosse < e.mosse && items.len() > 1 {
                    let total: i64 = items.iter().map(|(_, c)| t.nodes[*c].n).sum();
                    let mut r = self.esp_rng().random() * total as f64;
                    best = items.len() - 1;
                    for (i, (_, c)) in items.iter().enumerate() {
                        r -= t.nodes[*c].n as f64;
                        if r < 0.0 {
                            best = i;
                            break;
                        }
                    }
                    campionata = true;
                }
                self.esp_mosse += 1;
            }
        }
        let (key, child) = items[best].clone();
        self.registra(g.gs.turn, &t, legal, point, &key, campionata);
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
        let mut row = json!({"k": "search", "seat": self.side.name(), "point": point.name(), "turn": g.gs.turn,
                        "menu": legal.iter().map(action_list).collect::<Vec<_>>(), "value": root.value,
                        "P": p, "children": ch, "action": action_list(chosen), "nodes": t.nodes.len(),
                        "vals": std::mem::take(&mut self.vals)});
        // Only on request (set_search_timing): the seconds differ from run to run, and the
        // log is compared between runs and engines.
        if self.timing {
            row["iters"] = json!(self.last_iters);
            row["secs"] = json!(self.last_secs);
            row["probe_secs"] = json!(std::mem::take(&mut self.probe_secs));
        }
        log.push(row);
        self.last_iters = 0;
        self.last_secs = 0.0;
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
                None => state_value_v(&mut rl.gs, self.side, self.valutazione),
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
                sum += state_value_v(&mut c.gs, side, self.valutazione);
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
