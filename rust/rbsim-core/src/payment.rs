//! The coach page's "Come paghi?" (py: ai/coach.py `payment_options`,
//! `gold_only_plays`, `_golds`, `_pay_outcome`): the ways to pay a move that
//! recycle different runes, found by playing the move on copies of the game.
//! The engine's own payment is untouched: a way is played by setting
//! `Game::recycle_first` (the page's preference, see lp_pay.rs / lp_costs.rs)
//! after the Golds it needs.

use std::cell::{Cell, RefCell};
use std::rc::Rc;

use crate::agent::{AIdx, AKind, Action, Chooser, Point};
use crate::game::Game;
use crate::lp_abilities::AbilityEntry;
use crate::model::Opt;
use crate::types::*;

/// One way to pay a move (py: a `payment_options` dict, without its `text`).
#[derive(Clone, Debug, PartialEq)]
pub struct PayWay {
    /// Golds (Add a Power of any domain) used before the move.
    pub golds: i64,
    /// The domain those Golds Add (None without Golds).
    pub gold_domain: Option<Domain>,
    /// The domain the move's [rune] cost is paid from first (None: the engine's way).
    pub prefer: Option<Domain>,
    /// Where the move asks "Pagare ACCELERATE?" (and it can be paid): the answer this way is for
    /// (yes first); None where it asks nothing.
    pub accelerate: Option<bool>,
    /// The runes the move recycles, (domain, how many), in the rune pool's order.
    pub recycled: Vec<(Domain, i64)>,
}

/// A play payable only with Golds, and the ways to pay it.
#[derive(Clone, Debug)]
pub struct GoldOnly {
    pub action: Action,
    pub ways: Vec<PayWay>,
}

/// py: _PAY_KINDS
fn pay_kind(k: AKind) -> bool {
    matches!(k, AKind::Unit | AKind::Spell | AKind::Gear | AKind::Champion | AKind::Hide | AKind::Ability)
}

/// py: the chooser of `_pay_outcome`: the player's "which domain" choice
/// takes `domain`.
struct DomainPicker {
    side: Side,
    domain: Option<Domain>,
    /// The answer to the seat's `optional:accelerate` (None: the default, yes) and whether it was asked.
    accelerate: Option<bool>,
    asked: Rc<Cell<bool>>,
}

impl Chooser for DomainPicker {
    fn choose(&mut self, _g: &mut Game, kind: &str, side: Side, options: &[Opt], _default: usize,
              _source: Option<CardId>) -> R<Option<usize>> {
        if kind == "optional:accelerate" && side == self.side {
            self.asked.set(true);
            return Ok(self.accelerate.and_then(|b| options.iter().position(|o| *o == Opt::Bool(b))));
        }
        if kind.starts_with("domain") && side == self.side {
            if let Some(d) = self.domain {
                return Ok(options.iter().position(|o| *o == Opt::Domain(d)));
            }
        }
        Ok(None)
    }
}

/// py: CoachLoop(gs.clone()): a fresh loop over a copy, no agents; its
/// "which domain" choices of `side` answered with `domain`.
fn sim_copy(g: &Game, side: Side, domain: Option<Domain>) -> Game {
    sim_copy_acc(g, side, domain, None, Rc::new(Cell::new(false)))
}

/// `sim_copy`, its ACCELERATE question answered `accelerate` and noted in `asked`.
fn sim_copy_acc(g: &Game, side: Side, domain: Option<Domain>, accelerate: Option<bool>, asked: Rc<Cell<bool>>) -> Game {
    let mut gs = g.gs.clone();
    for s in Side::BOTH {
        gs.players[s.idx()].has_agent = false;
    }
    let mut c = Game::new(gs);
    let ch: Rc<RefCell<dyn Chooser>> = Rc::new(RefCell::new(DomainPicker { side, domain, accelerate, asked }));
    c.chooser = Some(ch);
    c
}

fn is_gold_entry(e: &AbilityEntry) -> bool {
    matches!(e, AbilityEntry::GearAbility { eff, .. } if eff.effect == "gain_power_any_domain")
}

/// py: _golds(loop, side, point): the ABILITY lanes of `side`'s gear that Add
/// a Power of any domain and are legal moves now. Runs on `c`, a copy.
pub fn golds(c: &mut Game, side: Side, point: Point) -> R<Vec<i64>> {
    let entries = c.activatable_abilities(side)?;
    let legal = c.legal_actions(point, side)?;
    Ok(legal
        .iter()
        .filter(|a| a.kind == AKind::Ability)
        .filter_map(|a| a.lane)
        .filter(|&l| l >= 0 && (l as usize) < entries.len() && is_gold_entry(&entries[l as usize]))
        .collect())
}

/// `golds` for the real game `g`, asked on a copy (the real game stays as it is).
pub fn golds_of(g: &Game, side: Side, point: Point) -> R<Vec<i64>> {
    golds(&mut sim_copy(g, side, None), side, point)
}

pub fn gold_action(lane: i64) -> Action {
    Action::new(AKind::Ability, AIdx::Str("ACTIVATED".into()), Some(lane), None, String::new())
}

/// py: _paid_card: the card whose cost `action` pays (from hand, or the champion).
fn paid_card(g: &Game, side: Side, a: &Action) -> Option<CardId> {
    if a.kind == AKind::Champion || (a.kind == AKind::Hide && a.index == AIdx::Str("champion".into())) {
        return g.gs.champion[side.idx()];
    }
    if a.kind == AKind::Ability {
        return None;
    }
    match a.index {
        AIdx::Int(i) if i >= 0 => g.gs.player(side).hand.get(i as usize).copied(),
        _ => None,
    }
}

/// py: _pay_domains: the domains that may pay `card`'s Power: its own, then the player's.
fn pay_domains(g: &Game, side: Side, card: Option<CardId>) -> Vec<Domain> {
    let own = card.and_then(|c| g.gs.cost_power_domain(c));
    let mut doms: Vec<Domain> = own.into_iter().collect();
    if let Some(c) = card {
        if own.is_none() {
            let pd = g.power_domains(c);
            if pd.len() < Domain::ALL.len() {
                doms.extend(pd);
            }
        }
    }
    doms.extend(g.gs.player(side).power_pool.keys().copied());
    let mut out: Vec<Domain> = Vec::new();
    for d in doms {
        if !out.contains(&d) {
            out.push(d);
        }
    }
    out
}

/// py: _pay_outcome: the runes `action` recycles once `golds` Golds Added
/// `gold_domain` Power, its [rune] paid from `prefer` first; on a copy.
/// ACCELERATE answered `accelerate`; also whether the move asked it. None if it can't be played so.
fn pay_outcome(g: &Game, side: Side, point: Point, action: &Action, golds_n: i64, gold_domain: Option<Domain>,
               prefer: Option<Domain>, accelerate: Option<bool>) -> Option<(Vec<(Domain, i64)>, bool)> {
    let asked = Rc::new(Cell::new(false));
    let mut c = sim_copy_acc(g, side, gold_domain, accelerate, asked.clone());
    (|| -> R<Option<(Vec<(Domain, i64)>, bool)>> {
        for _ in 0..golds_n {
            let lanes = golds(&mut c, side, point)?;
            let Some(&l) = lanes.first() else { return Ok(None) };
            c.apply_action(side, &gold_action(l), 0)?;
        }
        if !c.legal_actions(point, side)?.iter().any(|a| a.same(action)) {
            return Ok(None);
        }
        let before: Vec<(Domain, i64)> =
            c.gs.player(side).rune_pool.iter().map(|(d, rs)| (*d, rs.len() as i64)).collect();
        c.recycle_first = prefer.map(|d| (side, d));
        c.apply_action(side, action, 0)?;
        let p = c.gs.player(side);
        Ok(Some((
            before
                .iter()
                .filter_map(|&(d, n)| {
                    let now = p.rune_pool.get(&d).map(|v| v.len() as i64).unwrap_or(0);
                    (n > now).then_some((d, n - now))
                })
                .collect(),
            asked.get(),
        )))
    })()
    .unwrap_or(None) // py: a comparison never stops the game
}

/// py: payment_options(loop, side, point, action): the ways to pay `action`
/// that recycle different runes, fewest Golds first (the engine's own way
/// first); a Gold only where it saves a rune. `g` is the real game (read only).
pub fn payment_options(g: &Game, side: Side, point: Point, action: &Action) -> Vec<PayWay> {
    if !pay_kind(action.kind) {
        return Vec::new();
    }
    let mut probe = sim_copy(g, side, None);
    let Ok(gold_lanes) = golds(&mut probe, side, point) else { return Vec::new() };
    if action.kind == AKind::Ability && action.lane.map_or(false, |l| gold_lanes.contains(&l)) {
        return Vec::new();
    }
    let p = g.gs.player(side);
    let doms = pay_domains(g, side, paid_card(g, side, action));
    let mut out: Vec<PayWay> = Vec::new();
    for k in 0..=(gold_lanes.len() as i64) {
        let ways: Vec<(Option<Domain>, Option<Domain>)> = if k == 0 {
            let mut w = vec![(None, None)];
            w.extend(p.power_pool.keys().filter(|&&d| p.power_left(d) != 0).map(|&d| (None, Some(d))));
            w
        } else {
            doms.iter().map(|&d| (Some(d), Some(d))).collect()
        };
        let sum = |r: &[(Domain, i64)]| r.iter().map(|x| x.1).sum::<i64>();
        for (gold_domain, prefer) in ways {
            let Some(got) = pay_outcome(g, side, point, action, k, gold_domain, prefer, Some(true)) else { continue };
            let mut outcomes: Vec<(Option<bool>, Vec<(Domain, i64)>)> = vec![(None, got.0.clone())];
            if got.1 {
                // the move asks ACCELERATE: both answers
                outcomes = vec![(Some(true), got.0)];
                if let Some(other) = pay_outcome(g, side, point, action, k, gold_domain, prefer, Some(false)) {
                    outcomes.push((Some(false), other.0));
                }
            }
            for (acc, recycled) in outcomes {
                let fewest = if k == 0 {
                    None
                } else {
                    out.iter().filter(|o| o.golds == k - 1 && o.accelerate == acc).map(|o| sum(&o.recycled)).min()
                };
                if out.iter().any(|o| o.golds == k && o.accelerate == acc && o.recycled == recycled) {
                    continue;
                }
                if k != 0 && fewest.map_or(false, |f| sum(&recycled) >= f) {
                    continue;
                }
                out.push(PayWay { golds: k, gold_domain, prefer, accelerate: acc, recycled });
            }
        }
    }
    out
}

/// py: gold_only_plays(loop, side, point, legal): the cards `side` can play
/// only with its Golds' Power, with their ways (only those that have some).
pub fn gold_only_plays(g: &Game, side: Side, point: Point, legal: &[Action]) -> Vec<GoldOnly> {
    let mut probe = sim_copy(g, side, None);
    let Ok(lanes) = golds(&mut probe, side, point) else { return Vec::new() };
    if lanes.is_empty() {
        return Vec::new();
    }
    let p = g.gs.player(side);
    let champ = g.gs.champion[side.idx()];
    let mut domains: Vec<Domain> = Vec::new();
    for card in p.hand.iter().copied().chain(champ) {
        for d in pay_domains(g, side, Some(card)) {
            if !domains.contains(&d) {
                domains.push(d);
            }
        }
    }
    let mut out: Vec<Action> = Vec::new();
    for domain in domains {
        let mut c = sim_copy(g, side, Some(domain));
        let found = (|| -> R<Vec<Action>> {
            for _ in 0..lanes.len() {
                let now = golds(&mut c, side, point)?;
                let Some(&l) = now.first() else { return Err(EngineError::Invalid("no gold".into())) };
                c.apply_action(side, &gold_action(l), 0)?;
            }
            Ok(c.legal_actions(point, side)?)
        })();
        let Ok(found) = found else { continue };
        for a in found {
            if pay_kind(a.kind) && a.kind != AKind::Ability && !legal.iter().any(|l| l.same(&a))
                && !out.iter().any(|o| o.same(&a))
            {
                out.push(a);
            }
        }
    }
    out.into_iter()
        .filter_map(|a| {
            let ways = payment_options(g, side, point, &a);
            (!ways.is_empty()).then_some(GoldOnly { action: a, ways })
        })
        .collect()
}
