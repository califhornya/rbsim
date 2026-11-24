//! What the PPO policy sees of a question and of each option: py:
//! ai/ppo/features.py (Descriptor, describe_action, describe_choice,
//! mulligan_menu, describe_mulligan, context, question_of).

use crate::agent::{AIdx, AKind, Action};
use crate::game::Game;
use crate::lp_abilities::AbilityEntry;
use crate::model::Opt;
use crate::obs::{unit_features, Observation, N_TOKEN_FEATURES};
use crate::types::*;

pub const QUESTIONS: [&str; 23] = ["main", "reaction", "showdown", "mulligan",
    "optional", "target", "trigger_order", "combat_damage_order", "keep", "discard",
    "destination", "card", "mode", "cost_extras", "battlefield", "domain", "player", "tag",
    "equip", "predict_recycle", "show_off", "token_location", "other"];
pub const OPTION_TYPES: [&str; 26] = ["PASS", "UNIT", "SPELL", "GEAR", "CHAMPION", "MOVE", "HIDE", "HIDDEN_PLAY", "ABILITY",
    "ACTION_OTHER", "mulligan", "unit", "card", "battlefield", "yes", "no", "me", "opponent",
    "domain", "number", "no_more", "chain_item", "trigger", "gear", "nothing", "other"];
pub const LOCS: [&str; 11] = ["base", "bf0", "bf1", "bf2", "hand", "trash", "chain", "champion", "facedown", "deck", "none"];
pub const DOMAINS: [&str; 6] = ["FURY", "CALM", "MIND", "BODY", "CHAOS", "ORDER"];
pub const F_OPT: usize = 2 * N_TOKEN_FEATURES + 4 + 2 * LOCS.len() + DOMAINS.len() + 3;
pub const F_CTX: usize = 4;

/// py: question_of(kind)
pub fn question_of(kind: &str) -> i64 {
    let k = kind.split(':').next().unwrap_or("");
    QUESTIONS.iter().position(|q| *q == k).unwrap_or(QUESTIONS.len() - 1) as i64
}

fn type_index(t: &str) -> i64 {
    OPTION_TYPES.iter().position(|x| *x == t).unwrap_or(OPTION_TYPES.len() - 1) as i64
}

/// py: _bf_loc(i, n_bf)
fn bf_loc(i: Option<i64>, n_bf: usize) -> String {
    match i {
        None => "base".into(),
        Some(i) if i == n_bf as i64 => "base".into(),
        Some(i) if (0..3).contains(&i) => format!("bf{i}"),
        _ => "none".into(),
    }
}

/// py: Descriptor
#[derive(Clone, Debug)]
pub struct Descriptor {
    pub type_: i64,
    pub cards: [i64; 3],
    pub feats: Vec<f32>,
}

impl Descriptor {
    pub fn new(t: &str) -> Descriptor {
        Descriptor { type_: type_index(t), cards: [0; 3], feats: vec![0.0; F_OPT] }
    }
    /// py: Descriptor.unit(slot, u)
    fn unit(&mut self, g: &Game, slot: usize, u: UnitId) {
        self.cards[slot] = g.gs.reg.card_id(Some(g.gs.name(g.gs.unit(u).card)));
        let f = unit_features(&Observation::uview(&g.gs, u));
        let off = slot * N_TOKEN_FEATURES;
        for (k, x) in f.iter().enumerate() {
            self.feats[off + k] = *x as f32;
        }
    }
    fn owner(&mut self, slot: usize, mine: Option<bool>) {
        if let Some(m) = mine {
            self.feats[2 * N_TOKEN_FEATURES + 2 * slot + if m { 0 } else { 1 }] = 1.0;
        }
    }
    fn loc(&mut self, which: usize, loc: &str) {
        let l = LOCS.iter().position(|x| *x == loc).unwrap_or(LOCS.len() - 1);
        self.feats[2 * N_TOKEN_FEATURES + 4 + which * LOCS.len() + l] = 1.0;
    }
    fn domain(&mut self, name: &str) {
        if let Some(i) = DOMAINS.iter().position(|d| *d == name) {
            self.feats[2 * N_TOKEN_FEATURES + 4 + 2 * LOCS.len() + i] = 1.0;
        }
    }
    fn scalars(&mut self, number: f64, slot: f64, count: f64) {
        let base = 2 * N_TOKEN_FEATURES + 4 + 2 * LOCS.len() + DOMAINS.len();
        self.feats[base] = (number / 4.0) as f32;
        self.feats[base + 1] = (slot / 4.0) as f32;
        self.feats[base + 2] = (count / 2.0) as f32;
    }
    /// py: Descriptor.unknown
    pub fn unknown(&self) -> bool {
        self.type_ == type_index("other")
    }
}

/// py: describe_action(loop, side, a): a GameAction of the main phase, a
/// reaction or a showdown.
pub fn describe_action(g: &mut Game, side: Side, a: &Action) -> R<Descriptor> {
    let n_bf = g.gs.battlefields.len();
    let kind = a.kind.name();
    let mut d = Descriptor::new(kind);
    let reg = g.gs.reg.clone();
    let hand_len = g.gs.player(side).hand.len() as i64;
    match a.kind {
        AKind::Unit | AKind::Spell | AKind::Gear | AKind::Hide if matches!(a.index, AIdx::Int(i) if i < hand_len) => {
            let i = a.idx_int().unwrap() as usize;
            d.cards[0] = reg.card_id(Some(g.gs.name(g.gs.player(side).hand[i])));
            d.loc(0, "hand");
            let dst = if a.kind == AKind::Unit { a.dst } else { a.lane };
            if a.kind != AKind::Gear {
                d.loc(1, &bf_loc(dst, n_bf));
            } else {
                d.loc(1, "base");
            }
        }
        AKind::Champion => {
            if let Some(c) = g.gs.champion[side.idx()] {
                d.cards[0] = reg.card_id(Some(g.gs.name(c)));
            }
            d.loc(0, "champion");
            d.loc(1, &bf_loc(a.dst, n_bf));
        }
        AKind::Move => {
            let (src, dst) = (a.lane.unwrap_or(-1), a.dst);
            let units: Vec<UnitId> = if src == n_bf as i64 {
                g.gs.player(side).base_units.clone()
            } else {
                g.gs.battlefields[src as usize].units_for(side).clone()
            };
            let u = match a.index {
                AIdx::Int(i) if (i as usize) < units.len() => Some(units[i as usize]),
                _ => units.iter().copied().find(|&u| g.gs.unit(u).ready),
            };
            if let Some(u) = u {
                d.unit(g, 0, u);
            }
            d.owner(0, Some(true));
            d.loc(0, &bf_loc(Some(src), n_bf));
            d.loc(1, &bf_loc(dst, n_bf));
        }
        AKind::HiddenPlay => {
            let slot = a.idx_int().unwrap_or(0);
            if let Some(l) = a.lane.filter(|&l| (l as usize) < n_bf) {
                let fds = &g.gs.battlefields[l as usize].facedowns;
                if (slot as usize) < fds.len() {
                    d.cards[0] = reg.card_id(Some(g.gs.name(fds[slot as usize].card)));
                }
                d.loc(0, "facedown");
                d.loc(1, &bf_loc(Some(l), n_bf));
            }
            d.scalars(0.0, slot as f64, 0.0);
        }
        AKind::Ability => {
            let entries = g.activatable_abilities(side)?;
            let e = a.lane.filter(|&l| l >= 0 && (l as usize) < entries.len()).map(|l| entries[l as usize].clone());
            let unit = match &e {
                Some(AbilityEntry::Ability { unit, .. }) => Some(*unit),
                _ => None,
            };
            if let Some(u) = unit {
                d.unit(g, 0, u);
                let loc = match g.locate_unit(u) {
                    Some((_, bf)) => bf_loc(bf.map(|b| b as i64), n_bf),
                    None => "none".into(),
                };
                d.loc(0, &loc);
            }
            let src = match &e {
                Some(AbilityEntry::GearAbility { gear, .. }) | Some(AbilityEntry::Equip { gear }) => Some(*gear),
                Some(AbilityEntry::Flow { card }) | Some(AbilityEntry::TrashPlay { card, .. })
                | Some(AbilityEntry::BanishedPlay { card }) => Some(*card),
                _ => None,
            };
            if let (Some(c), None) = (src, unit) {
                d.cards[0] = reg.card_id(Some(g.gs.name(c)));
            }
            let types = ["ability", "equip", "flow", "banished_play", "trash_play"];
            let n = e.as_ref().and_then(|e| types.iter().position(|t| *t == e.type_name())).map_or(4.0, |i| i as f64);
            d.scalars(n, 0.0, 0.0);
        }
        _ => {}
    }
    Ok(d)
}

/// py: _card_loc(gs, side, card) -> (location, mine)
fn card_loc(g: &Game, side: Side, card: CardId) -> (&'static str, Option<bool>) {
    for who in [side, side.other()] {
        let p = g.gs.player(who);
        if p.hand.contains(&card) {
            return ("hand", Some(who == side));
        }
        if p.trash.contains(&card) {
            return ("trash", Some(who == side));
        }
    }
    for item in &g.gs.chain {
        if item.card == card {
            return ("chain", Some(item.player == side));
        }
    }
    ("none", None)
}

/// py: describe_choice(loop, side, option): an option of a GameLoop.choose,
/// on `g` (the game, or the copy a spell's choices are declared on).
/// `kind`: the choice's kind ("facedown_trash" offers facedown cards, which
/// Python passes as FacedownCard and Rust as their cards).
pub fn describe_choice(g: &Game, side: Side, kind: &str, option: &Opt) -> Descriptor {
    let n_bf = g.gs.battlefields.len();
    let reg = g.gs.reg.clone();
    let mut where_first: Option<usize> = None;
    let mut option = option;
    if let Opt::Tuple(xs) = option {
        if !xs.is_empty() {
            where_first = xs[..xs.len() - 1].iter().find_map(|x| if let Opt::Bf(b) = x { Some(*b) } else { None });
            option = &xs[xs.len() - 1];
        }
    }
    let mut d;
    match option {
        Opt::NoMore => d = Descriptor::new("no_more"),
        Opt::None => d = Descriptor::new("nothing"),
        Opt::Trigger(i) => {
            d = Descriptor::new("trigger");
            if let Some(p) = g.trigger_menu.get(*i) {
                d.cards[1] = reg.card_id(Some(g.gs.name(p.card)));
                d.owner(1, Some(p.side == side));
                let loc = if p.bf < n_bf { bf_loc(Some(p.bf as i64), n_bf) } else { "none".into() };
                d.loc(1, &loc);
            }
        }
        Opt::Gear(gid) => {
            d = Descriptor::new("gear");
            d.cards[1] = reg.card_id(Some(g.gs.name(g.gs.dgear[gid.i()].card)));
            for (i, b) in g.gs.battlefields.iter().enumerate() {
                for who in Side::BOTH {
                    if b.gear[who.idx()].contains(gid) {
                        d.owner(1, Some(who == side));
                        d.loc(1, &bf_loc(Some(i as i64), n_bf));
                    }
                }
            }
        }
        Opt::Bool(x) => d = Descriptor::new(if *x { "yes" } else { "no" }),
        Opt::Side(s) => d = Descriptor::new(if *s == side { "me" } else { "opponent" }),
        Opt::Str(s) if s == "A" || s == "B" => d = Descriptor::new(if *s == side.name() { "me" } else { "opponent" }),
        Opt::Str(s) if s.to_lowercase() == "yes" || s.to_lowercase() == "no" => d = Descriptor::new(&s.to_lowercase()),
        Opt::Domain(dm) => {
            d = Descriptor::new("domain");
            d.domain(dm.name());
        }
        Opt::Int(n) => {
            d = Descriptor::new("number");
            d.scalars(*n as f64, 0.0, 0.0);
        }
        Opt::Unit(u) => {
            d = Descriptor::new("unit");
            d.unit(g, 1, *u);
            match g.locate_unit(*u) {
                Some((s, bf)) => {
                    d.owner(1, Some(s == side));
                    d.loc(1, &bf_loc(bf.map(|b| b as i64), n_bf));
                }
                None => d.loc(1, "none"),
            }
        }
        Opt::Bf(b) => {
            d = Descriptor::new("battlefield");
            let bf = &g.gs.battlefields[*b];
            d.cards[1] = reg.card_id(bf.card.map(|c| g.gs.name(c)));
            d.loc(1, &bf_loc(Some(*b as i64), n_bf));
            let ctrl = bf.controller();
            d.owner(1, ctrl.map(|c| c == side));
        }
        Opt::Chain(uid) => {
            d = Descriptor::new("chain_item");
            let i = &g.gs.chain_pos(*uid).expect("a chain option off the chain");
            let it = &g.gs.chain[*i];
            d.cards[1] = reg.card_id(Some(g.gs.name(it.card)));
            d.owner(1, Some(it.player == side));
            d.loc(1, "chain");
            let depth = g.gs.chain.len() - 1 - *i;
            d.scalars(0.0, depth as f64, 0.0);
        }
        Opt::Card(c) if kind == "facedown_trash" => {
            // py: a FacedownCard
            d = Descriptor::new("card");
            let owner = g.gs.battlefields.iter().flat_map(|b| b.facedowns.iter()).find(|f| f.card == *c).map(|f| f.owner);
            let mine = owner == Some(side);
            d.cards[1] = if mine { reg.card_id(Some(g.gs.name(*c))) } else { 0 };
            d.owner(1, Some(mine));
            d.loc(1, "facedown");
        }
        Opt::Card(c) => {
            d = Descriptor::new("card");
            d.cards[1] = reg.card_id(Some(g.gs.name(*c)));
            let (loc, mine) = card_loc(g, side, *c);
            d.loc(1, loc);
            d.owner(1, mine);
        }
        _ => d = Descriptor::new("other"),
    }
    if let Some(b) = where_first {
        d.loc(0, &bf_loc(Some(b as i64), n_bf));
    }
    d
}

/// py: mulligan_menu(hand_size): keep-all, then one card, then two.
pub fn mulligan_menu(n: usize) -> Vec<Vec<i64>> {
    let mut out = vec![Vec::new()];
    for i in 0..n {
        out.push(vec![i as i64]);
    }
    for i in 0..n {
        for j in i + 1..n {
            out.push(vec![i as i64, j as i64]);
        }
    }
    out
}

/// py: describe_mulligan(hand, subset)
pub fn describe_mulligan(g: &Game, hand: &[CardId], subset: &[i64]) -> Descriptor {
    let mut d = Descriptor::new("mulligan");
    for (k, &i) in subset.iter().take(2).enumerate() {
        d.cards[1 + k] = g.gs.reg.card_id(Some(g.gs.name(hand[i as usize])));
    }
    d.loc(1, "hand");
    d.scalars(0.0, 0.0, subset.len() as f64);
    d
}

/// py: context(n_options, made, up_to, declaring)
pub fn context(n: usize, made: i64, up_to: bool, declaring: bool) -> [f32; F_CTX] {
    [(n as f64 / 16.0) as f32, (made as f64 / 4.0) as f32, if up_to { 1.0 } else { 0.0 }, if declaring { 1.0 } else { 0.0 }]
}
