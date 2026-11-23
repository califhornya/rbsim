//! Rust agents for games played without Python callbacks:
//! - RandomAgent (py: ai/search/random_agent.py), uniform over legal_actions
//!   with its own generator (a CPython-compatible MT19937);
//! - SimpleTradeAgent (py: ai/heuristics/simple_trade_agent.py) with the
//!   paying helpers of its base class (py: ai/heuristics/base_agent.py Agent).
//! Both keep the base Agent's defaults: decide_optional -> True,
//! decide_predict_recycle -> False, decide_mode -> None.

use std::collections::BTreeSet;

use crate::agent::{AIdx, AKind, Action, Agent, Point};
use crate::cards::truthy;
use crate::game::{new_loop_id, Game};
use crate::lp_abilities::AbilityEntry;
use crate::lp_triggers::is_add_verb;
use crate::pydict::PyDict;
use crate::rng::PyRandom;
use crate::types::*;

// ------------------------------------------------------------------ random --

/// py: RandomAgent(player, rng)
pub struct RandomAgent {
    pub rng: PyRandom,
}

impl RandomAgent {
    pub fn new(seed: i128) -> RandomAgent {
        RandomAgent { rng: PyRandom::new(seed) }
    }
    /// py: RandomAgent._pick
    fn pick(&mut self, g: &mut Game, point: Point, side: Side) -> R<Action> {
        let options = g.legal_actions(point, side)?;
        if options.is_empty() {
            return Ok(Action::pass());
        }
        let i = self.rng.choice_index(options.len());
        Ok(options[i].clone())
    }
}

impl Agent for RandomAgent {
    fn decide_action(&mut self, g: &mut Game, side: Side, _cards_played: i64) -> R<Action> {
        self.pick(g, Point::TurnAction, side)
    }
    fn decide_reaction(&mut self, g: &mut Game, side: Side) -> R<Action> {
        self.pick(g, Point::Reaction, side)
    }
    fn decide_showdown_action(&mut self, g: &mut Game, side: Side, _bf_idx: usize) -> R<Action> {
        self.pick(g, Point::ShowdownAction, side)
    }
    fn decide_mulligan(&mut self, _g: &mut Game, _side: Side) -> R<Vec<i64>> {
        Ok(Vec::new())
    }
    fn decide_optional(&mut self, _g: &mut Game, _side: Side, _card: CardId, _effect_name: &str) -> R<bool> {
        Ok(true)
    }
    fn decide_mode(&mut self, _g: &mut Game, _side: Side, _card: CardId, _n_modes: i64) -> R<Option<i64>> {
        Ok(None)
    }
    fn decide_predict_recycle(&mut self, _g: &mut Game, _side: Side, _card: CardId) -> R<bool> {
        Ok(false)
    }
}

// ------------------------------------------------------- base Agent: paying --

/// py: _MAX_ADDS, _ADD_SEARCH
const MAX_ADDS: usize = 8;
const ADD_SEARCH: usize = 24;

/// py: _entry_key(entry): (type, uuid of the source card, effect, copy).
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct EntryKey(&'static str, Option<CardId>, Option<String>, i64);

fn entry_key(g: &Game, e: &AbilityEntry) -> EntryKey {
    let src = match e {
        AbilityEntry::Ability { unit, .. } => Some(g.gs.ucard(*unit)),
        AbilityEntry::GearAbility { gear, .. } | AbilityEntry::Equip { gear } => Some(*gear),
        AbilityEntry::Flow { card } | AbilityEntry::TrashPlay { card, .. } | AbilityEntry::BanishedPlay { card } => Some(*card),
        AbilityEntry::BfAbility { bf, .. } => g.gs.battlefields[*bf].card,
    };
    let copy = match e {
        AbilityEntry::Ability { copy, .. } => *copy,
        _ => 0,
    };
    EntryKey(e.type_name(), src, e.eff().map(|s| s.effect.clone()), copy)
}

/// What a check asks (py: the closures of _card_check / _entry_check).
#[derive(Clone, Debug)]
pub enum Check {
    /// py: _card_check(card, lane, dst)
    Card { card: CardId, lane: Option<i64>, dst: Option<i64> },
    /// py: _entry_check(entry)
    Entry { entry: AbilityEntry, key: EntryKey },
}

/// py: _RESOURCES, a player's resources an Add ability changes.
#[derive(Clone, Debug)]
struct Resources {
    ints: [i64; 8],
    power_pool: PyDict<Domain, i64>,
    floating_power: PyDict<Domain, i64>,
}

fn resources(g: &Game, side: Side) -> Resources {
    let p = g.gs.player(side);
    Resources {
        ints: [p.rune_energy, p.pool_energy, p.earmarked_energy_showdown, p.earmarked_power_gear,
               p.earmarked_power_spell, p.earmarked_power_permanent, p.earmarked_energy_spell,
               p.earmarked_energy_unit],
        power_pool: p.power_pool.clone(),
        floating_power: p.floating_power.clone(),
    }
}

fn set_resources(g: &mut Game, side: Side, r: &Resources) {
    let p = g.gs.player_mut(side);
    [p.rune_energy, p.pool_energy, p.earmarked_energy_showdown, p.earmarked_power_gear,
     p.earmarked_power_spell, p.earmarked_power_permanent, p.earmarked_energy_spell,
     p.earmarked_energy_unit] = r.ints;
    p.power_pool = r.power_pool.clone();
    p.floating_power = r.floating_power.clone();
}

/// What using the Add abilities changed: per int resource, per pool domain.
#[derive(Clone, Debug)]
struct Gains {
    ints: [i64; 8],
    power_pool: Vec<(Domain, i64)>,
    floating_power: Vec<(Domain, i64)>,
}

fn pool_gain(was: &PyDict<Domain, i64>, now: &PyDict<Domain, i64>) -> Vec<(Domain, i64)> {
    // py: {d: now.get(d, 0) - was.get(d, 0) for d in set(now) | set(was)}
    let mut out: Vec<(Domain, i64)> = Vec::new();
    for d in now.keys().chain(was.keys()) {
        if !out.iter().any(|(x, _)| x == d) {
            out.push((*d, now.get_or(d, 0) - was.get_or(d, 0)));
        }
    }
    out
}

fn add_gain(pool: &PyDict<Domain, i64>, gain: &[(Domain, i64)]) -> PyDict<Domain, i64> {
    let mut p = pool.clone();
    for (d, n) in gain {
        let v = (p.get_or(d, 0) + n).max(0);
        p.set(*d, v);
    }
    p
}

/// A game copy for trying Add abilities (py: GameLoop(loop.gs.clone()), the
/// agents detached).
fn agent_copy(g: &Game) -> Game {
    let mut gs = g.gs.clone();
    for s in Side::BOTH {
        gs.players[s.idx()].has_agent = false;
    }
    let mut c = Game::new(gs);
    c.loop_id = new_loop_id();
    c
}

/// The paying helpers of py: base_agent.Agent, as state an agent keeps.
#[derive(Default)]
pub struct Paying {
    /// py: self._adds_now = (id(loop.gs), turn, keys of the usable Add abilities)
    adds_now: Option<(u64, i64, Vec<EntryKey>)>,
    /// py: self._adds_cache = (adds_now, (gains, conclusive))
    adds_cache: Option<((u64, i64, Vec<EntryKey>), (Gains, bool))>,
}

impl Paying {
    /// py: _begin_decision
    pub fn begin(&mut self) {
        self.adds_now = None;
    }

    /// The check on game `g` (`real`: g is the agent's own loop), for `side`.
    pub fn check(&self, g: &mut Game, real: bool, side: Side, c: &Check) -> R<bool> {
        match c {
            Check::Card { card, lane, dst } => {
                let card = if real {
                    Some(*card)
                } else {
                    // py: _find_card: the copy's card with this uuid in hand or the Champion Zone.
                    let p = g.gs.player(side);
                    if p.hand.contains(card) || g.gs.champion[side.idx()] == Some(*card) { Some(*card) } else { None }
                };
                let Some(card) = card else { return Ok(false) };
                if !g.affordable(side, card, *lane, *dst)? {
                    return Ok(false);
                }
                Ok(!(g.gs.is_spell(card) && lane.is_some()) || g.spell_has_targets(card, side, lane.unwrap() as usize)?)
            }
            Check::Entry { entry, key } => {
                let found = if real {
                    Some(entry.clone())
                } else {
                    let entries = g.activatable_abilities(side)?;
                    entries.into_iter().find(|e| entry_key(g, e) == *key)
                };
                match found {
                    Some(e) => g.ability_usable(side, &e),
                    None => Ok(false),
                }
            }
        }
    }

    pub fn card_check(card: CardId, lane: Option<i64>, dst: Option<i64>) -> Check {
        Check::Card { card, lane, dst }
    }

    pub fn entry_check(g: &Game, entry: &AbilityEntry) -> Check {
        Check::Entry { entry: entry.clone(), key: entry_key(g, entry) }
    }

    /// py: _paying(action, check)
    pub fn paying(&mut self, g: &mut Game, side: Side, action: Action, check: &Check) -> R<Option<Action>> {
        if self.check(g, true, side, check)? {
            return Ok(Some(action));
        }
        if !self.adds_may_pay(g, side, check)? {
            return Ok(None);
        }
        Ok(self.first_add(g, side, check)?
            .map(|first| Action::new(AKind::Ability, AIdx::Str("ACTIVATED".into()), Some(first as i64), None, String::new())))
    }

    /// py: _best_payable(candidates): best score first, ties in order.
    pub fn best_payable(&mut self, g: &mut Game, side: Side, mut cands: Vec<(i64, Action, Option<Check>)>)
        -> R<Option<Action>> {
        cands.sort_by_key(|c| -c.0);
        for (_s, action, check) in cands {
            let paid = match check {
                None => Some(action),
                Some(c) => self.paying(g, side, action, &c)?,
            };
            if paid.is_some() {
                return Ok(paid);
            }
        }
        Ok(None)
    }

    /// py: _adds_may_pay(check)
    fn adds_may_pay(&mut self, g: &mut Game, side: Side, check: &Check) -> R<bool> {
        if self.adds_now.is_none() {
            let entries = g.activatable_abilities(side)?;
            let idx = add_entries(g, side)?;
            let keys = idx.iter().map(|&i| entry_key(g, &entries[i])).collect();
            self.adds_now = Some((g.loop_id, g.gs.turn, keys));
        }
        if self.adds_now.as_ref().unwrap().2.is_empty() {
            return Ok(false);
        }
        let (gains, conclusive) = self.all_adds(g, side)?;
        let saved = resources(g, side);
        let mut with = saved.clone();
        for i in 0..8 {
            with.ints[i] = (saved.ints[i] + gains.ints[i]).max(0);
        }
        with.power_pool = add_gain(&saved.power_pool, &gains.power_pool);
        with.floating_power = add_gain(&saved.floating_power, &gains.floating_power);
        set_resources(g, side, &with);
        let ok = self.check(g, true, side, check);
        set_resources(g, side, &saved);
        if ok? {
            return Ok(true);
        }
        Ok(!conclusive && self.first_add(g, side, check)?.is_some())
    }

    /// py: _all_adds(loop)
    fn all_adds(&mut self, g: &Game, side: Side) -> R<(Gains, bool)> {
        if let Some((key, res)) = &self.adds_cache {
            if Some(key) == self.adds_now.as_ref() {
                return Ok(res.clone());
            }
        }
        let mut tmp = agent_copy(g);
        let before = resources(&tmp, side);
        let mut conclusive = true;
        for _ in 0..MAX_ADDS {
            let adds = add_entries(&mut tmp, side)?;
            if adds.is_empty() {
                break;
            }
            let entries = tmp.activatable_abilities(side)?;
            let eff = entries[adds[0]].eff().cloned().expect("an Add ability");
            let parsed = tmp.parse_activated_cost(eff.cost.as_ref())?;
            if parsed.energy != 0 || parsed.power != 0 || eff.effect == "convert_x" {
                conclusive = false;
            }
            if !tmp.use_ability_now(side, &AIdx::Str("ACTIVATED".into()), Some(adds[0] as i64))? {
                break;
            }
        }
        let now = resources(&tmp, side);
        let mut ints = [0i64; 8];
        for i in 0..8 {
            ints[i] = now.ints[i] - before.ints[i];
        }
        let gains = Gains {
            ints,
            power_pool: pool_gain(&before.power_pool, &now.power_pool),
            floating_power: pool_gain(&before.floating_power, &now.floating_power),
        };
        let res = (gains, conclusive);
        self.adds_cache = Some((self.adds_now.clone().unwrap(), res.clone()));
        Ok(res)
    }

    /// py: _first_add(check): the first Add ability of the shortest sequence
    /// after which `check` holds, each tried on a copy of the game.
    fn first_add(&mut self, g: &mut Game, side: Side, check: &Check) -> R<Option<usize>> {
        // A node: (its game, None = the agent's own; the first ability; used keys).
        let mut frontier: Vec<(Option<Game>, Option<usize>, BTreeSet<EntryKey>)> = vec![(None, None, BTreeSet::new())];
        let mut seen: BTreeSet<Vec<EntryKey>> = BTreeSet::new();
        let mut tried = 0usize;
        for _depth in 0..MAX_ADDS {
            let mut nxt: Vec<(Option<Game>, Option<usize>, BTreeSet<EntryKey>)> = Vec::new();
            for (node, first, used) in frontier.iter_mut() {
                let ng: &mut Game = match node {
                    Some(x) => x,
                    None => &mut *g,
                };
                let entries = ng.activatable_abilities(side)?;
                for idx in add_entries(ng, side)? {
                    let mut done = used.clone();
                    done.insert(entry_key(ng, &entries[idx]));
                    let dk: Vec<EntryKey> = done.iter().cloned().collect();
                    if seen.contains(&dk) {
                        continue;
                    }
                    seen.insert(dk);
                    if tried >= ADD_SEARCH {
                        return Ok(None);
                    }
                    tried += 1;
                    let mut tmp = agent_copy(ng);
                    if !tmp.use_ability_now(side, &AIdx::Str("ACTIVATED".into()), Some(idx as i64))? {
                        continue;
                    }
                    let lead = first.unwrap_or(idx);
                    if self.check(&mut tmp, false, side, check)? {
                        return Ok(Some(lead));
                    }
                    nxt.push((Some(tmp), Some(lead), done));
                }
            }
            if nxt.is_empty() {
                return Ok(None);
            }
            frontier = nxt;
        }
        Ok(None)
    }
}

/// py: Agent._add_entries(loop, player): indices of the usable Add abilities,
/// those that only exhaust first, then those that pay or convert, then those
/// that give something up.
pub fn add_entries(g: &mut Game, side: Side) -> R<Vec<usize>> {
    let mut out: Vec<(i64, usize)> = Vec::new();
    for (i, entry) in g.activatable_abilities(side)?.into_iter().enumerate() {
        let Some(eff) = entry.eff().cloned() else { continue };
        if !matches!(entry.type_name(), "ability" | "gear_ability") || !is_add_verb(&eff.effect)
            || !g.ability_usable(side, &entry)? {
            continue;
        }
        let p = g.parse_activated_cost(eff.cost.as_ref())?;
        let unit = match &entry {
            AbilityEntry::Ability { unit, .. } => Some(*unit),
            _ => None,
        };
        if p.kill_other_token && token_to_kill(g, side, unit).is_none() {
            continue;
        }
        let gives_up = p.sacrifice || p.kill_other_token || p.kill_other_friendly || p.kill_friendly_gear
            || truthy(p.banish_from_trash.as_ref()) || p.banish_self || p.discard != 0 || p.recycle != 0
            || p.spend_xp != 0 || p.spend_buff.as_deref().map_or(false, |s| !s.is_empty());
        let pays = p.energy != 0 || p.power != 0 || eff.effect == "convert_x";
        out.push((if gives_up { 2 } else if pays { 1 } else { 0 }, i));
    }
    out.sort();
    Ok(out.into_iter().map(|(_, i)| i).collect())
}

/// What `_token_to_kill` gives up (a unit or a gear token).
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum TokenToKill {
    Unit(UnitId),
    Gear(CardId),
}

/// py: GameLoop._token_to_kill(side, unit)
pub fn token_to_kill(g: &Game, side: Side, unit: Option<UnitId>) -> Option<TokenToKill> {
    let tokens: Vec<UnitId> = g.friendly_units_of(side).into_iter()
        .filter(|&u| g.gs.unit(u).is_token && Some(u) != unit)
        .collect();
    if !tokens.is_empty() {
        let mut best = tokens[0];
        for &u in &tokens[1..] {
            if g.gs.unit_might(u) < g.gs.unit_might(best) {
                best = u;
            }
        }
        return Some(TokenToKill::Unit(best));
    }
    g.gs.player(side).base_gear.iter().copied().find(|&c| g.gs.card_is_token(c)).map(TokenToKill::Gear)
}

// ------------------------------------------------------------ simple_trade --

/// py: SimpleTradeAgent
#[derive(Default)]
pub struct SimpleTradeAgent {
    pub pay: Paying,
}

fn act(kind: AKind, index: AIdx, lane: Option<i64>, dst: Option<i64>) -> Action {
    Action::new(kind, index, lane, dst, String::new())
}

impl SimpleTradeAgent {
    /// py: _trade_math(bf, my_side) -> (my_might, opp_might, my_units, opp_units)
    fn trade_math(g: &Game, bf: usize, side: Side) -> (i64, i64, Vec<UnitId>, Vec<UnitId>) {
        let b = &g.gs.battlefields[bf];
        let mine = b.units_for(side).clone();
        let opp = b.units_for(side.other()).clone();
        let sum = |us: &[UnitId]| us.iter().filter(|&&u| !g.gs.unit(u).stunned).map(|&u| g.gs.unit_might(u)).sum::<i64>();
        (sum(&mine), sum(&opp), mine, opp)
    }

    /// py: _score_combat_spell(card, ...)
    fn score_combat_spell(g: &Game, card: CardId) -> i64 {
        let mut score = 0;
        for eff in g.gs.effects(card) {
            let name = eff.get("effect").and_then(|v| v.as_str()).unwrap_or("");
            let amount = match eff.get("amount") {
                Some(v) if truthy(Some(v)) => crate::cards::py_int(v),
                _ => 0,
            };
            if matches!(name, "grant_might" | "grant_temporary_might" | "grant_temporary_might_per_enemy"
                | "grant_temporary_might_per_friendly") {
                score += 4 + amount;
            } else if matches!(name, "deal_damage" | "kill_unit") {
                score += 4 + amount;
            } else {
                score += 1;
            }
        }
        if score == 0 && (g.gs.has_keyword(card, "REACTION") || g.gs.has_keyword(card, "ACTION")) {
            score = 2;
        }
        score
    }

    /// py: _maybe_deploy_champion
    fn maybe_deploy_champion(&mut self, g: &mut Game, side: Side) -> R<Option<Action>> {
        let Some(champ) = g.gs.champion[side.idx()] else { return Ok(None) };
        if g.gs.champion_deployed[side.idx()] {
            return Ok(None);
        }
        let check = Paying::card_check(champ, None, None);
        self.pay.paying(g, side, act(AKind::Champion, AIdx::None, Some(0), None), &check)
    }

    /// py: _find_trade_move
    fn find_trade_move(g: &Game, side: Side) -> Option<Action> {
        let base = g.gs.player(side).base_units.clone();
        let base_idx = g.gs.battlefields.len() as i64;
        let mut ready: Vec<UnitId> = base.iter().copied().filter(|&u| g.gs.unit(u).ready && g.gs.unit_might(u) > 0).collect();
        if ready.is_empty() {
            return None;
        }
        ready.sort_by_key(|&u| g.gs.unit_might(u));
        let pending = g.gs.pending_move;
        let mut best: Option<(i64, Action)> = None;
        for bf_idx in 0..g.gs.battlefields.len() {
            let (my_now, opp_now, _mine, opp) = Self::trade_math(g, bf_idx, side);
            if opp.is_empty() {
                continue;
            }
            let joining = pending.map_or(false, |(d, _)| d == bf_idx);
            if joining && my_now >= opp_now {
                return None;
            }
            if my_now + ready.iter().map(|&u| g.gs.unit_might(u)).sum::<i64>() < opp_now {
                continue;
            }
            let single = ready.iter().copied().find(|&u| my_now + g.gs.unit_might(u) >= opp_now);
            let unit = single.unwrap_or(*ready.last().unwrap());
            let mut score = 10;
            if g.gs.battlefields[bf_idx].controller() == Some(side.other()) {
                score += 5;
            }
            if single.is_some() && my_now + g.gs.unit_might(unit) > opp_now {
                score += 3;
            }
            if joining {
                score += 100;
            }
            let i = base.iter().position(|&u| u == unit).unwrap() as i64;
            let action = act(AKind::Move, AIdx::Int(i), Some(base_idx), Some(bf_idx as i64));
            if best.as_ref().map_or(true, |(s, _)| score > *s) {
                best = Some((score, action));
            }
        }
        best.map(|(_, a)| a)
    }

    /// py: _find_gear_play
    fn find_gear_play(&mut self, g: &mut Game, side: Side) -> R<Option<Action>> {
        let mut best_lane: Option<usize> = None;
        let mut best_might = -1;
        for (i, bf) in g.gs.battlefields.iter().enumerate() {
            let mine = bf.units_for(side);
            if mine.is_empty() {
                continue;
            }
            let top = mine.iter().map(|&u| g.gs.unit_might(u)).max().unwrap();
            if top > best_might {
                best_might = top;
                best_lane = Some(i);
            }
        }
        match best_lane {
            None => Ok(None),
            Some(l) => self.first_gear(g, side, l as i64),
        }
    }

    /// py: _first_gear(lane)
    fn first_gear(&mut self, g: &mut Game, side: Side, lane: i64) -> R<Option<Action>> {
        let hand = g.gs.player(side).hand.clone();
        for (idx, &card) in hand.iter().enumerate() {
            if !g.gs.is_gear_card(card) {
                continue;
            }
            let dst = if g.gs.has_keyword(card, "DEPLOY") { Some(lane) } else { None };
            let check = Paying::card_check(card, None, dst);
            let a = self.pay.paying(g, side, act(AKind::Gear, AIdx::Int(idx as i64), Some(lane), None), &check)?;
            if a.is_some() {
                return Ok(a);
            }
        }
        Ok(None)
    }

    /// py: _find_combat_spell
    fn find_combat_spell(&mut self, g: &mut Game, side: Side) -> R<Option<Action>> {
        let mut target: Option<usize> = None;
        let mut best_gap = 999;
        for i in 0..g.gs.battlefields.len() {
            let (my, opp, mine, theirs) = Self::trade_math(g, i, side);
            if mine.is_empty() || theirs.is_empty() {
                continue;
            }
            let gap = opp - my;
            if gap >= 0 && gap < best_gap {
                best_gap = gap;
                target = Some(i);
            }
        }
        let Some(t) = target else { return Ok(None) };
        let mut cands = Vec::new();
        for (idx, &card) in g.gs.player(side).hand.clone().iter().enumerate() {
            if !g.gs.is_spell(card) {
                continue;
            }
            let score = Self::score_combat_spell(g, card);
            if score <= 0 {
                continue;
            }
            cands.push((score, act(AKind::Spell, AIdx::Int(idx as i64), Some(t as i64), None),
                        Some(Paying::card_check(card, Some(t as i64), None))));
        }
        self.pay.best_payable(g, side, cands)
    }

    /// py: _find_activated_ability
    fn find_activated_ability(&mut self, g: &mut Game, side: Side) -> R<Option<Action>> {
        let abilities = g.activatable_abilities(side)?;
        for (idx, entry) in abilities.iter().enumerate() {
            match entry.type_name() {
                "flow" | "banished_play" | "trash_play" => continue,
                "equip" => {
                    if g.friendly_units_of(side).is_empty() {
                        continue;
                    }
                }
                _ => {
                    let eff = entry.eff().cloned().expect("an ability");
                    if is_add_verb(&eff.effect) {
                        continue;
                    }
                    let p = g.parse_activated_cost(eff.cost.as_ref())?;
                    if !(p.tap || p.energy != 0 || p.power != 0) {
                        continue;
                    }
                    let unit = match entry {
                        AbilityEntry::Ability { unit, .. } => Some(*unit),
                        _ => None,
                    };
                    if p.kill_other_token && token_to_kill(g, side, unit).is_none() {
                        continue;
                    }
                }
            }
            let check = Paying::entry_check(g, entry);
            let a = act(AKind::Ability, AIdx::Str("ACTIVATED".into()), Some(idx as i64), None);
            if let Some(a) = self.pay.paying(g, side, a, &check)? {
                return Ok(Some(a));
            }
        }
        Ok(None)
    }

    /// py: _find_flow_play
    fn find_flow_play(&mut self, g: &mut Game, side: Side) -> R<Option<Action>> {
        let mut cands = Vec::new();
        for (idx, entry) in g.activatable_abilities(side)?.iter().enumerate() {
            let card = match entry {
                AbilityEntry::Flow { card } | AbilityEntry::TrashPlay { card, .. } | AbilityEntry::BanishedPlay { card } => *card,
                _ => continue,
            };
            let score = if !g.gs.is_spell(card) { 5 } else { Self::score_combat_spell(g, card) };
            if score > 0 {
                cands.push((score, act(AKind::Ability, AIdx::Str("ACTIVATED".into()), Some(idx as i64), None),
                            Some(Paying::entry_check(g, entry))));
            }
        }
        self.pay.best_payable(g, side, cands)
    }

    /// py: _find_unit_to_develop
    fn find_unit_to_develop(&mut self, g: &mut Game, side: Side) -> R<Option<Action>> {
        let mut cands = Vec::new();
        for (idx, &card) in g.gs.player(side).hand.clone().iter().enumerate() {
            if !(g.gs.is_unit_card(card) || g.gs.is_legend_card(card)) {
                continue;
            }
            let dests = g.unit_play_destinations(card, side);
            if dests.is_empty() {
                continue;
            }
            let dst = if dests.contains(&None) { None } else { dests[0] };
            let mut score = g.gs.might(card).unwrap_or(0);
            for kw in ["TANK", "SHIELD", "ASSAULT"] {
                if g.gs.has_keyword(card, kw) {
                    score += 1;
                }
            }
            let dst = dst.map(|d| d as i64);
            cands.push((score, act(AKind::Unit, AIdx::Int(idx as i64), Some(0), dst), Some(Paying::card_check(card, None, dst))));
        }
        self.pay.best_payable(g, side, cands)
    }

    /// py: _find_empty_bf_move
    fn find_empty_bf_move(g: &Game, side: Side) -> Option<Action> {
        let base = &g.gs.player(side).base_units;
        let i = base.iter().position(|&u| g.gs.unit(u).ready)?;
        let base_idx = g.gs.battlefields.len() as i64;
        for (bf_idx, bf) in g.gs.battlefields.iter().enumerate() {
            if bf.units_for(Side::A).is_empty() && bf.units_for(Side::B).is_empty() && bf.controller() != Some(side) {
                return Some(act(AKind::Move, AIdx::Int(i as i64), Some(base_idx), Some(bf_idx as i64)));
            }
        }
        None
    }
}

impl Agent for SimpleTradeAgent {
    /// py: SimpleTradeAgent.decide_action
    fn decide_action(&mut self, g: &mut Game, side: Side, _cards_played: i64) -> R<Action> {
        self.pay.begin();
        if let Some(a) = self.maybe_deploy_champion(g, side)? {
            return Ok(a);
        }
        if let Some(a) = Self::find_trade_move(g, side) {
            return Ok(a);
        }
        if let Some(a) = self.find_gear_play(g, side)? {
            return Ok(a);
        }
        if let Some(a) = self.find_combat_spell(g, side)? {
            return Ok(a);
        }
        if let Some(a) = self.find_activated_ability(g, side)? {
            return Ok(a);
        }
        if let Some(a) = self.find_unit_to_develop(g, side)? {
            return Ok(a);
        }
        if let Some(a) = Self::find_empty_bf_move(g, side) {
            return Ok(a);
        }
        if let Some(a) = self.find_flow_play(g, side)? {
            return Ok(a);
        }
        if let Some(a) = self.first_gear(g, side, 0)? {      // py: _find_gear_to_stage
            return Ok(a);
        }
        Ok(Action::pass())
    }

    /// py: decide_mulligan: cards that cost 5 or more go back.
    fn decide_mulligan(&mut self, g: &mut Game, side: Side) -> R<Vec<i64>> {
        Ok(g.gs.player(side).hand.iter().enumerate()
            .filter(|(_, c)| g.gs.cost_energy(**c) >= 5)
            .map(|(i, _)| i as i64)
            .collect())
    }

    /// py: decide_showdown_action: an ACTION / REACTION spell that scores.
    fn decide_showdown_action(&mut self, g: &mut Game, side: Side, bf_idx: usize) -> R<Action> {
        self.pay.begin();
        let mut cands = Vec::new();
        for (idx, &card) in g.gs.player(side).hand.clone().iter().enumerate() {
            if !g.gs.is_spell(card) || !(g.gs.has_keyword(card, "ACTION") || g.gs.has_keyword(card, "REACTION")) {
                continue;
            }
            let score = Self::score_combat_spell(g, card);
            if score <= 0 {
                continue;
            }
            cands.push((score, act(AKind::Spell, AIdx::Int(idx as i64), Some(bf_idx as i64), None),
                        Some(Paying::card_check(card, Some(bf_idx as i64), None))));
        }
        Ok(self.pay.best_payable(g, side, cands)?.unwrap_or_else(Action::pass))
    }

    /// py: decide_reaction: a REACTION spell scoring 3 or more, at the newest
    /// chain item's battlefield.
    fn decide_reaction(&mut self, g: &mut Game, side: Side) -> R<Action> {
        self.pay.begin();
        let mut target = 0usize;
        if let Some(last) = g.gs.chain.last() {
            if last.bf_idx < g.gs.battlefields.len() {
                target = last.bf_idx;
            }
        }
        let mut cands = Vec::new();
        for (idx, &card) in g.gs.player(side).hand.clone().iter().enumerate() {
            if !g.gs.is_spell(card) || !g.gs.has_keyword(card, "REACTION") {
                continue;
            }
            let score = Self::score_combat_spell(g, card);
            if score < 3 {
                continue;
            }
            cands.push((score, act(AKind::Spell, AIdx::Int(idx as i64), Some(target as i64), None),
                        Some(Paying::card_check(card, Some(target as i64), None))));
        }
        Ok(self.pay.best_payable(g, side, cands)?.unwrap_or_else(Action::pass))
    }

    fn decide_optional(&mut self, _g: &mut Game, _side: Side, _card: CardId, _effect_name: &str) -> R<bool> {
        Ok(true)
    }
    fn decide_mode(&mut self, _g: &mut Game, _side: Side, _card: CardId, _n_modes: i64) -> R<Option<i64>> {
        Ok(None)
    }
    fn decide_predict_recycle(&mut self, _g: &mut Game, _side: Side, _card: CardId) -> R<bool> {
        Ok(false)
    }
}

// ------------------------------------------------------------- PPOChooser --

/// py: ppo/agent.PPOChooser: each choice goes to the agent of the side that
/// makes it (its `inner`; None, the baseline, for agents that are not PPO
/// agents). The agents are the real game's, also on a declaration's copy.
pub struct SideChooser;

impl crate::agent::Chooser for SideChooser {
    fn choose(&mut self, g: &mut Game, kind: &str, side: Side, options: &[crate::model::Opt], default: usize,
              source: Option<CardId>) -> R<Option<usize>> {
        let agent = match g.real_game {
            // SAFETY: the real game's frame runs this copy and does not touch
            // its agents meanwhile.
            Some(p) => unsafe { (*p).agents[side.idx()].clone() },
            None => g.agents[side.idx()].clone(),
        };
        match agent {
            Some(a) => a.borrow_mut().inner(g, kind, side, options, default, source),
            None => Ok(None),
        }
    }
}
