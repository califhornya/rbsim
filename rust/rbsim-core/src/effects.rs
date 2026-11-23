//! py: effects.py — the effect REGISTRY (dispatch by verb) and the handlers
//! of the ported cards. A verb Python registers but not ported here is
//! NotPorted; a verb Python doesn't register doesn't exist (a marker).

use serde_json::{Map, Value};
use std::collections::HashSet;
use std::sync::OnceLock;

use crate::cards::{py_int, truthy};
use crate::effects_core::*;
use crate::game::*;
use crate::lp_phases::py_str;
use crate::lp_triggers::Ctx;
use crate::model::*;
use crate::not_ported;
use crate::types::*;

const PY_VERBS: &str = include_str!("py_registry_verbs.txt");

fn py_verbs() -> &'static HashSet<&'static str> {
    static S: OnceLock<HashSet<&'static str>> = OnceLock::new();
    S.get_or_init(|| PY_VERBS.lines().map(|l| l.trim()).filter(|l| !l.is_empty()).collect())
}

/// py: EFFECT_REGISTRY.get(verb) is not None
pub fn exists(verb: &str) -> bool {
    py_verbs().contains(verb)
}

pub const SINGLE_UNIT_TARGETS: [&str; 7] = ["chosen_unit", "chosen", "any_unit", "a_unit", "unit", "enemy_unit", "friendly_unit"];

/// py: _coerce_bool
pub fn coerce_bool(v: Option<&Value>) -> bool {
    match v {
        Some(Value::Bool(b)) => *b,
        Some(Value::String(s)) => {
            let l = s.trim().to_lowercase();
            if ["false", "0", "no", "off"].contains(&l.as_str()) {
                false
            } else if ["true", "1", "yes", "on"].contains(&l.as_str()) {
                true
            } else {
                !s.is_empty()
            }
        }
        other => truthy(other),
    }
}

/// The first element with the greatest key (py: max(xs, key=...)).
pub fn max_first<T: Copy, K: PartialOrd>(xs: &[T], mut key: impl FnMut(T) -> K) -> T {
    let mut best = xs[0];
    let mut bk = key(best);
    for &x in &xs[1..] {
        let k = key(x);
        if k > bk {
            best = x;
            bk = k;
        }
    }
    best
}

/// The first element with the smallest key (py: min(xs, key=...)).
pub fn min_first<T: Copy, K: PartialOrd>(xs: &[T], mut key: impl FnMut(T) -> K) -> T {
    let mut best = xs[0];
    let mut bk = key(best);
    for &x in &xs[1..] {
        let k = key(x);
        if k < bk {
            best = x;
            bk = k;
        }
    }
    best
}

fn kind(what: &str, spec: &Map<String, Value>) -> String {
    format!("{what}:{}", spec.get("effect").map(py_str).unwrap_or_else(|| "?".into()))
}

fn with(spec: &Map<String, Value>, k: &str, v: Value) -> Map<String, Value> {
    let mut s = spec.clone();
    s.insert(k.into(), v);
    s
}

fn units_of(v: &[Opt]) -> Vec<UnitId> {
    v.iter().filter_map(|o| if let Opt::Unit(u) = o { Some(*u) } else { None }).collect()
}

impl Game {
    /// py: REGISTRY[verb](ctx, params)
    pub fn run_effect(&mut self, verb: &str, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        match verb {
            "grant_might" => self.fx_grant_might(ctx, spec),
            "draw_cards" => self.fx_draw_cards(ctx, spec),
            "mode_choice" => self.fx_mode_choice(ctx, spec),
            "sequence" => self.fx_sequence(ctx, spec),
            "fight" => self.fx_fight(ctx, spec),
            "bounce_enemy_at_crowded_battlefield" => self.fx_bounce_crowded(ctx, spec),
            "xp_when_it_wins" => {
                for u in Game::it_units(ctx) {
                    self.gs.unit_mut(u).win_xp_turn = self.gs.turn;
                }
                Ok(())
            }
            "return_gear_to_hand" => self.fx_return_gear_to_hand(ctx, spec),
            "cant_move_this_turn" => {
                let t = spec.get("target").cloned().unwrap_or(Value::String("triggering_unit".into()));
                let s = with(spec, "target", t);
                for u in self.resolve_targets(ctx, &s, "none", None)? {
                    self.gs.unit_mut(u).cant_move_turn = self.gs.turn;
                }
                Ok(())
            }
            "gain_power_any_domain" => self.fx_gain_power_any_domain(ctx, spec),
            "channel_rune" => self.fx_channel_rune(ctx, spec),
            "grant_temporary_might" => self.fx_grant_temporary_might(ctx, spec),
            "buff_unit" => self.fx_buff_unit(ctx, spec),
            "stun_unit" => self.fx_stun_unit(ctx, spec),
            "recall_unit" => self.fx_recall_unit(ctx, spec),
            "move_unit" => self.fx_move_units(ctx, spec, false),
            "move_units_to_base" => self.fx_move_units(ctx, spec, true),
            "give_keyword" => self.fx_give_keyword(ctx, spec),
            "give_temporary_assault" => self.fx_give_temp_keyword(ctx, spec, "ASSAULT"),
            "give_temporary_shield" => self.fx_give_temp_keyword(ctx, spec, "SHIELD"),
            "swap_might" => self.fx_swap_might(ctx, spec),
            "swap_position" => self.fx_swap_position(ctx, spec),
            "discard_card" => self.fx_discard_card(ctx, spec),
            "play_token" => self.fx_play_token(ctx, spec),
            "attach_gear" => self.fx_attach_gear(ctx, spec),
            "gain_xp" => {
                let amount = if truthy(spec.get("amount_source")) { self.effect_amount(ctx, spec)? } else { spec.get("amount").map(py_int).unwrap_or(1) };
                let t = sstr(spec, "target", "actor").to_lowercase();
                let side = if ["actor", "ally", "self", "friendly_unit", "all_friendly_units_here"].contains(&t.as_str()) { ctx.actor } else { ctx.opponent };
                self.gs.add_xp(side, amount);
                Ok(())
            }
            "predict" | "scry" => self.fx_predict(ctx, spec),
            "recycle_from_opponent_hand" => self.fx_recycle_from_opponent_hand(ctx, spec),
            "play_from_trash" => self.fx_play_from_zone(ctx, spec, "trash"),
            other => {
                if exists(other) {
                    not_ported!("effects", "handler {other}");
                }
                Err(EngineError::Py(format!("KeyError: {other}")))
            }
        }
    }

    pub fn it_units(ctx: &Ctx) -> Vec<UnitId> {
        match ctx.extra.get("it") {
            Some(XVal::List(v)) => v.iter().filter_map(|x| if let XVal::Unit(u) = x { Some(*u) } else { None }).collect(),
            _ => Vec::new(),
        }
    }

    fn set_it(ctx: &mut Ctx, units: &[UnitId]) {
        ctx.extra.set("it", XVal::List(units.iter().map(|&u| XVal::Unit(u)).collect()));
    }

    /// py: EffectContext.grant_might / _grant_might
    fn fx_grant_might(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let amount = spec.get("amount").map(py_int).unwrap_or(0);
        let target = sstr(spec, "target", "actor");
        let scope = sstr(spec, "scope", "all");
        if amount == 0 {
            return Ok(());
        }
        let tk = target.to_lowercase();
        let side = if ["actor", "ally", "self"].contains(&tk.as_str()) { ctx.actor } else { ctx.opponent };
        let units = self.gs.battlefields[ctx.bf].units_for(side).clone();
        if units.is_empty() {
            return Ok(());
        }
        let it: Vec<UnitId> = if scope.to_lowercase() == "single" { units[..1].to_vec() } else { units };
        for u in it {
            self.gs.unit_mut(u).aura_might += amount;
        }
        Ok(())
    }

    /// py: _draw_cards / EffectContext.draw_cards
    fn fx_draw_cards(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let count = if truthy(spec.get("amount_source")) {
            self.effect_amount(ctx, spec)?
        } else {
            match spec.get("count") {
                Some(v) => py_int(v),
                None => spec.get("amount").map(py_int).unwrap_or(1),
            }
        };
        let mut target = sstr(spec, "target", "actor");
        if target == "it_controller" {
            not_ported!("_draw_cards", "it_controller");
        }
        if count <= 0 {
            return Ok(());
        }
        let _ = &mut target;
        let player = self.player_for_target(ctx, &target)?;
        let mut drawn = 0;
        for _ in 0..count {
            if self.draw_one(player, false)?.is_none() {
                break;
            }
            drawn += 1;
        }
        if drawn > 0 {
            self.zero_point_overflow(player, drawn)?;
        }
        Ok(())
    }

    /// py: _mode_choice
    fn fx_mode_choice(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let modes: Vec<Value> = spec.get("modes").and_then(|v| v.as_array()).cloned().unwrap_or_default();
        if modes.is_empty() {
            return Ok(());
        }
        let mut taken: Vec<usize> = Vec::new();
        let n = spec.get("choose").map(py_int).filter(|&x| x != 0).unwrap_or(1).max(1);
        for _ in 0..n {
            if !self.choose_one_mode(ctx, spec, &modes, &mut taken)? {
                return Ok(());
            }
        }
        Ok(())
    }

    fn mode_steps(mode: &Value) -> Vec<Map<String, Value>> {
        match mode {
            Value::Array(a) => a.iter().filter_map(|x| x.as_object().cloned()).collect(),
            Value::Object(o) => vec![o.clone()],
            _ => Vec::new(),
        }
    }

    fn choose_one_mode(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>, modes: &[Value], taken: &mut Vec<usize>) -> R<bool> {
        let mut free: Vec<usize> = Vec::new();
        for j in 0..modes.len() {
            if !taken.contains(&j) && self.mode_payable(ctx, &modes[j])? {
                free.push(j);
            }
        }
        if truthy(spec.get("unique_per_turn")) {
            not_ported!("_choose_one_mode", "unique_per_turn (Aphelios)");
        }
        if free.is_empty() {
            return Ok(false);
        }
        let mut i: Option<usize> = None;
        let replaying = self.replaying("mode", Some(ctx.card));
        if let Some(a) = self.agent(ctx.actor).filter(|a| a.borrow().has("decide_mode")) {
            if !replaying {
                match a.borrow_mut().decide_mode(self, ctx.actor, ctx.card, modes.len() as i64) {
                    Ok(Some(x)) => i = Some(x.max(0).min(modes.len() as i64 - 1) as usize),
                    Ok(None) => {}
                    Err(e) if e.swallowable() => {}
                    Err(e) => return Err(e),
                }
            }
        }
        let mut i = match i {
            Some(x) => x,
            None => if replaying { free[0] } else { self.best_mode(ctx, modes, &free)? },
        };
        if !free.contains(&i) {
            i = free[0];
        }
        let opts: Vec<Opt> = free.iter().map(|&j| Opt::Int(j as i64)).collect();
        let got = self.choose("mode", ctx.actor, &opts, Opt::Int(i as i64), Some(ctx.card))?;
        let Opt::Int(i) = got else { unreachable!() };
        let i = i as usize;
        taken.push(i);
        self.run_mode(ctx, &modes[i])?;
        Ok(true)
    }

    /// py: _mode_payable
    fn mode_payable(&mut self, ctx: &Ctx, mode: &Value) -> R<bool> {
        let steps = Self::mode_steps(mode);
        if let Some(s0) = steps.first() {
            if s0.get("effect").and_then(|v| v.as_str()) == Some("spend_buff") && s0.get("target").and_then(|v| v.as_str()) == Some("self") {
                not_ported!("_mode_payable", "spend_buff mode");
            }
            if truthy(s0.get("condition")) {
                let c = s0["condition"].clone();
                if !self.check_condition(Some(&c), ctx.card, ctx.actor, Some(&ctx.extra))? {
                    return Ok(false);
                }
            }
            if truthy(s0.get("additional_cost")) {
                let ac = s0["additional_cost"].clone();
                if !self.pay_one_additional_cost_x(ctx.card, ctx.actor, &ac, true)? {
                    return Ok(false);
                }
            }
        }
        Ok(true)
    }

    /// py: _run_mode
    fn run_mode(&mut self, ctx: &mut Ctx, mode: &Value) -> R<()> {
        for sub in Self::mode_steps(mode) {
            if truthy(sub.get("additional_cost")) {
                let ac = sub["additional_cost"].clone();
                if !self.pay_one_additional_cost(ctx.card, ctx.actor, &ac)? {
                    return Ok(());
                }
            }
            let verb = sub.get("effect").map(py_str).unwrap_or_default();
            if exists(&verb) {
                self.run_effect(&verb, ctx, &sub)?;
            }
        }
        Ok(())
    }

    /// py: _best_mode — each mode on a copy of the game (a fresh loop, no
    /// agents, looking ahead), the best _position_value wins.
    fn best_mode(&mut self, ctx: &Ctx, modes: &[Value], free: &[usize]) -> R<usize> {
        if free.len() < 2 || self.lookahead {
            return Ok(free[0]);
        }
        let mut best = free[0];
        let mut best_value: Option<f64> = None;
        for &j in free {
            let mut g2 = Game::new(self.gs.clone());
            g2.lookahead = true;
            let mut ctx2 = ctx.clone();
            let chain_before: Vec<ChainItem> = g2.gs.chain.clone();
            match g2.run_mode(&mut ctx2, &modes[j]) {
                Ok(()) => {}
                Err(e) if e.swallowable() => continue,
                Err(e) => return Err(e),
            }
            let mut value = g2.position_value(ctx.actor);
            for item in chain_before.iter() {
                let still = g2.gs.chain.iter().any(|x| x.card == item.card && x.player == item.player);
                if !still {
                    let cost = match &item.ability {
                        Some(a) => a.energy,
                        None => g2.gs.cost_energy(item.card) + g2.gs.cost_power(item.card).unwrap_or(0),
                    };
                    let worth = 1.0 + 1.5 * cost as f64;
                    value += if item.player != ctx.actor { worth } else { -worth };
                }
            }
            if best_value.map_or(true, |b| value > b) {
                best = j;
                best_value = Some(value);
            }
        }
        Ok(best)
    }

    /// py: _position_value(gs, side)
    pub fn position_value(&mut self, side: Side) -> f64 {
        let mut score = |g: &mut Game, s: Side| -> f64 {
            let mut units: Vec<UnitId> = Vec::new();
            for bf in &g.gs.battlefields {
                units.extend(bf.units_for(s).iter().copied());
            }
            units.extend(g.gs.player(s).base_units.iter().copied());
            let mut v: i64 = units.iter().map(|&u| 1 + if g.gs.unit(u).stunned { 0 } else { (g.gs.unit_might(u) - g.gs.unit(u).damage).max(0) }).sum();
            let p = g.gs.player(s);
            v += p.hand.len() as i64 + p.rune_pool.values().map(|r| r.len() as i64).sum::<i64>();
            v += p.base_gear.len() as i64 + units.iter().map(|&u| g.gs.unit(u).gear.len() as i64).sum::<i64>()
                + g.gs.battlefields.iter().map(|b| b.gear[s.idx()].len() as i64).sum::<i64>();
            v += 4 * g.gs.points[s.idx()];
            let mut ctl = 0;
            for i in 0..g.gs.battlefields.len() {
                if g.gs.battlefields[i].control() == Some(s) {
                    ctl += 1;
                }
            }
            v += 2 * ctl;
            v as f64
        };
        let a = score(self, side);
        let b = score(self, side.other());
        a - b
    }

    /// py: _sequence
    fn fx_sequence(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let steps: Vec<Value> = spec.get("steps").and_then(|v| v.as_array()).cloned().unwrap_or_default();
        for sub in steps {
            if let Some(o) = sub.as_object() {
                let verb = o.get("effect").map(py_str).unwrap_or_default();
                if exists(&verb) {
                    self.run_effect(&verb, ctx, o)?;
                }
            }
        }
        Ok(())
    }

    /// py: EffectContext.damage_units(units, amount, kind, by)
    pub fn damage_units(&mut self, ctx: &Ctx, units: &[UnitId], amount: i64, kind_: &str, by: Option<Side>) -> R<()> {
        if amount <= 0 {
            return Ok(());
        }
        let by = by.unwrap_or(ctx.actor);
        // id(bf or None) -> (bf, dead) in first-seen order
        let mut dead_at: Vec<(Option<usize>, Vec<(UnitId, Side)>)> = Vec::new();
        for &unit in units {
            let Some((side, bf)) = self.locate_unit(unit) else { continue };
            let bonus = self.bf_passive_amount(bf, "bonus_damage_here", 0);
            let t = self.take_damage(unit, amount + bonus, kind_, Some(by), Some(ctx.card))?;
            self.gs.unit_mut(unit).damage += t;
            if self.is_dead(unit) {
                match bf {
                    None => self.gs.player_mut(side).base_units.retain(|&u| u != unit),
                    Some(b) => self.gs.battlefields[b].remove_unit(side, unit),
                }
                if let Some(e) = dead_at.iter_mut().find(|(b, _)| *b == bf) {
                    e.1.push((unit, side));
                } else {
                    dead_at.push((bf, vec![(unit, side)]));
                }
            }
        }
        for (bf, dead) in dead_at {
            self.route_deaths(&dead, bf.unwrap_or(0), bf.is_none(), Some((by, ctx.card)), false)?;
        }
        Ok(())
    }

    /// py: _fight
    fn fx_fight(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let (me, them) = (ctx.actor, ctx.opponent);
        let mod_a = spec.get("friendly_might").map(py_int).unwrap_or(0);
        let mod_b = spec.get("enemy_might").map(py_int).unwrap_or(0);
        let where_ = sstr(spec, "where", "anywhere");
        let ua = self.units_at(ctx, them, &where_);
        let enemies = self.choosable(ctx, &ua)?;
        let first = sstr(spec, "first", "friendly").to_lowercase();
        let (a, b);
        if first == "any" && enemies.len() >= 2 {
            not_ported!("_fight", "first any");
        } else {
            let a0: Option<UnitId> = if first == "it" {
                let it: Vec<UnitId> = Game::it_units(ctx).into_iter().filter(|&u| self.locate_unit(u).is_some()).collect();
                if let Some(&x) = it.first() {
                    Some(x)
                } else {
                    let mine = self.units_at(ctx, me, "anywhere");
                    if mine.is_empty() {
                        None
                    } else {
                        let base = max_first(&mine, |u| self.gs.unit_might(u));
                        let opts: Vec<Opt> = mine.iter().map(|&u| Opt::Unit(u)).collect();
                        match self.choose(&kind("target", spec), me, &opts, Opt::Unit(base), Some(ctx.card))? {
                            Opt::Unit(u) => Some(u),
                            _ => unreachable!(),
                        }
                    }
                }
            } else if first == "self" {
                self.source_unit(ctx)
            } else {
                let mine = self.units_at(ctx, me, "anywhere");
                if mine.is_empty() { None } else { Some(max_first(&mine, |u| self.gs.unit_might(u))) }
            };
            let Some(a1) = a0 else { return Ok(()) };
            if enemies.is_empty() {
                return Ok(());
            }
            let am = self.gs.unit_might(a1);
            let ad = self.gs.unit(a1).damage;
            let value = |g: &Game, e: UnitId| {
                let em = g.gs.unit_might(e);
                let kills = am + mod_a >= em + mod_b - g.gs.unit(e).damage;
                let survives = em + mod_b < am + mod_a - ad;
                (kills && survives, kills, survives, em)
            };
            let base = max_first(&enemies, |e| value(self, e));
            let opts: Vec<Opt> = enemies.iter().map(|&u| Opt::Unit(u)).collect();
            let Opt::Unit(b1) = self.choose(&kind("target", spec), me, &opts, Opt::Unit(base), Some(ctx.card))? else { unreachable!() };
            a = a1;
            b = b1;
        }
        self.note_chosen(ctx.card, me, &[a, b])?;
        for (unit, amount) in [(b, mod_b), (a, mod_a)] {
            if amount != 0 {
                Self::set_it(ctx, &[unit]);
                let s = serde_json::json!({"target": "it", "amount": amount, "duration": "this_turn"});
                self.fx_grant_temporary_might(ctx, s.as_object().unwrap())?;
            }
        }
        let (am, bm) = (self.gs.unit_might(a), self.gs.unit_might(b));
        self.damage_units(ctx, &[b], am, "unit", Some(me))?;
        self.damage_units(ctx, &[a], bm, "unit", Some(them))
    }

    /// py: _bounce_enemy_at_crowded_battlefield
    fn fx_bounce_crowded(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let mut crowded: Vec<usize> = Vec::new();
        for i in 0..self.gs.battlefields.len() {
            let b = &self.gs.battlefields[i];
            if b.units[0].len() + b.units[1].len() >= 4 {
                let en = b.units_for(ctx.opponent).clone();
                if !self.choosable(ctx, &en)?.is_empty() {
                    crowded.push(i);
                }
            }
        }
        if crowded.is_empty() {
            return Ok(());
        }
        let base = max_first(&crowded, |b| self.gs.battlefields[b].units_for(ctx.opponent).iter().map(|&u| self.gs.unit_might(u)).max().unwrap());
        let opts: Vec<Opt> = crowded.iter().map(|&b| Opt::Bf(b)).collect();
        let Opt::Bf(bf) = self.choose(&kind("battlefield", spec), ctx.actor, &opts, Opt::Bf(base), Some(ctx.card))? else { unreachable!() };
        let en = self.gs.battlefields[bf].units_for(ctx.opponent).clone();
        let enemies = self.choosable(ctx, &en)?;
        let base = max_first(&enemies, |u| self.gs.unit_might(u));
        let opts: Vec<Opt> = enemies.iter().map(|&u| Opt::Unit(u)).collect();
        let Opt::Unit(unit) = self.choose(&kind("target", spec), ctx.actor, &opts, Opt::Unit(base), Some(ctx.card))? else { unreachable!() };
        self.note_chosen(ctx.card, ctx.actor, &[unit])?;
        self.unit_leaves_to(ctx, unit, ctx.opponent, "hand")
    }

    /// py: _unit_leaves_to(ctx, unit, side, to)
    pub fn unit_leaves_to(&mut self, _ctx: &Ctx, unit: UnitId, side: Side, to: &str) -> R<()> {
        let Some(where_) = self.locate_unit(unit) else { return Ok(()) };
        match where_.1 {
            None => self.gs.player_mut(side).base_units.retain(|&u| u != unit),
            Some(b) => self.gs.battlefields[b].remove_unit(side, unit),
        }
        let gear = std::mem::take(&mut self.gs.unit_mut(unit).gear);
        self.gs.player_mut(side).base_gear.extend(gear);
        let c = self.gs.ucard(unit);
        self.fire_leaves_board(c, side, where_.1.unwrap_or(0))?;
        if to == "hand" {
            if let Some(b) = where_.1 {
                if let Some(bc) = self.gs.battlefields[b].card {
                    if self.has_effect(bc, "rippers_bay") && self.gs.player(side).energy() >= 1 && !self.gs.player(side).rune_deck.runes.is_empty() {
                        not_ported!("_unit_leaves_to", "rippers_bay");
                    }
                }
            }
        }
        if self.gs.unit(unit).is_token {
            return Ok(());
        }
        let owner = self.owner_of(c, side);
        self.gs.card_mut(c).owner = None;
        match to {
            "hand" => self.gs.player_mut(owner).to_hand(c, true),
            "deck_bottom" => self.gs.player_mut(owner).deck.cards.insert(0, c),
            _ => self.gs.player_mut(owner).deck.cards.push(c),
        }
        Ok(())
    }

    fn gear_opt(e: &(Side, GearHolder, GearRef)) -> Opt {
        let h = match e.1 {
            GearHolder::Unit(u) => Opt::Unit(u),
            GearHolder::Base => Opt::None,
            GearHolder::Bf(b) => Opt::Bf(b),
        };
        let g = match e.2 {
            GearRef::Card(c) => Opt::Card(c),
            GearRef::Deployed(d) => Opt::Gear(d),
        };
        Opt::Tuple(vec![Opt::Side(e.0), h, g])
    }

    /// py: _zone_value(card)
    pub fn zone_value(&self, c: CardId) -> (i64, i64) {
        (self.gs.cost_energy(c), self.gs.might(c).unwrap_or(0))
    }

    /// py: _return_gear_to_hand
    fn fx_return_gear_to_hand(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let entries: Vec<(Side, GearHolder, GearRef)> = if spec.get("target").and_then(|v| v.as_str()) == Some("self") {
            self.gear_entries(ctx, false, true).into_iter().filter(|e| self.gear_card(e.2) == ctx.card).collect()
        } else {
            self.gear_entries(ctx, true, true)
        };
        if entries.is_empty() {
            return Ok(());
        }
        let pick = max_first(&(0..entries.len()).collect::<Vec<_>>(), |i| (entries[i].0 == ctx.opponent, self.zone_value(self.gear_card(entries[i].2))));
        let opts: Vec<Opt> = entries.iter().map(Self::gear_opt).collect();
        let got = self.choose(&kind("target", spec), ctx.actor, &opts, opts[pick].clone(), Some(ctx.card))?;
        let i = opts.iter().position(|o| *o == got).unwrap();
        let (side, holder, gear) = entries[i];
        self.note_gear_chosen(ctx.card, ctx.actor, side);
        if let GearHolder::Unit(u) = holder {
            if self.gs.unit_is_gear(u) && self.gs.ucard(u) == self.gear_card(gear) {
                not_ported!("_return_gear_to_hand", "unit gear");
            }
        }
        let card = self.gear_card(gear);
        match (holder, gear) {
            (GearHolder::Bf(b), GearRef::Deployed(d)) => self.gs.battlefields[b].gear[side.idx()].retain(|&x| x != d),
            (GearHolder::Unit(u), _) => self.gs.unit_mut(u).gear.retain(|&x| x != card),
            _ => self.gs.player_mut(side).base_gear.retain(|&x| x != card),
        }
        self.fire_leaves_board(card, side, 0)?;
        if !self.gs.card_is_token(card) {
            self.gs.card_mut(card).empowered = Some(false);
            self.gs.player_mut(side).to_hand(card, true);
        }
        Ok(())
    }

    /// py: _gain_power_any_domain
    fn fx_gain_power_any_domain(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let amount = spec.get("amount").map(py_int).unwrap_or(1);
        if amount <= 0 {
            return Ok(());
        }
        let player = self.player_for_target(ctx, &sstr(spec, "target", "actor"))?;
        let mut need: Vec<(Domain, i64)> = Vec::new();
        {
            let p = self.gs.player(player);
            for &c in &p.hand {
                let d = self.gs.cost_power_domain(c);
                let n = self.gs.cost_power(c).unwrap_or(0);
                if let Some(d) = d {
                    let have = p.power_pool.get_or(&d, 0);
                    if n > have {
                        if let Some(e) = need.iter_mut().find(|(x, _)| *x == d) {
                            e.1 += n - have;
                        } else {
                            need.push((d, n - have));
                        }
                    }
                }
            }
        }
        let domain = if !need.is_empty() {
            let mut best = need[0];
            for &e in &need[1..] {
                if e.1 > best.1 {
                    best = e;
                }
            }
            best.0
        } else {
            let runes: Vec<(Domain, usize)> = self.gs.player(player).rune_pool.iter().filter(|(_, rs)| !rs.is_empty()).map(|(d, rs)| (*d, rs.len())).collect();
            if runes.is_empty() {
                Domain::Fury
            } else {
                let mut best = runes[0];
                for &e in &runes[1..] {
                    if e.1 > best.1 {
                        best = e;
                    }
                }
                best.0
            }
        };
        let opts: Vec<Opt> = Domain::ALL.iter().map(|&d| Opt::Domain(d)).collect();
        let Opt::Domain(d) = self.choose(&kind("domain", spec), player, &opts, Opt::Domain(domain), Some(ctx.card))? else { unreachable!() };
        self.gs.player_mut(player).add_power(d, amount);
        if self.gs.name(ctx.card) == "Gold" && self.gold_bonus(player) {
            self.gs.player_mut(player).add_energy(1);
        }
        Ok(())
    }

    /// py: _channel_rune
    fn fx_channel_rune(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let count = match spec.get("count") {
            Some(v) => py_int(v),
            None => spec.get("amount").map(py_int).unwrap_or(1),
        };
        let target = sstr(spec, "target", "actor");
        let players = if target == "each_player" { vec![ctx.actor, ctx.opponent] } else { vec![self.player_for_target(ctx, &target)?] };
        for p in players {
            let before = self.gs.player(p).total_runes_in_play();
            let ex = coerce_bool(spec.get("exhausted").or(Some(&Value::Bool(false))));
            self.gs.player_mut(p).unlock_runes(count, ex);
            self.extra_channel(p);
            if truthy(spec.get("draw_if_short")) && self.gs.player(p).total_runes_in_play() - before < count {
                not_ported!("_channel_rune", "draw_if_short");
            }
        }
        Ok(())
    }

    /// py: _fire_might_reduced
    pub fn fire_might_reduced(&mut self, unit: UnitId, by_side: Side) -> R<()> {
        let Some((ws, wbf)) = self.locate_unit(unit) else { return Ok(()) };
        if ws == by_side {
            return Ok(());
        }
        let mut ex = Extra::default();
        ex.set("triggering_unit", XVal::Unit(unit));
        ex.set("died_at", match wbf { Some(b) => XVal::Bf(b), None => XVal::None });
        let c = self.gs.ucard(unit);
        self.fire_units_trigger("on_enemy_might_reduced", by_side, None, Some(c), Some(ex))
    }

    /// py: _grant_temporary_might
    fn fx_grant_temporary_might(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let mut amount = self.effect_amount(ctx, spec)?;
        let floor = sget(spec, "minimum").or(sget(spec, "min_might")).map(py_int);
        if amount < 0 && !sstr(spec, "target", "").starts_with("all") {
            let mel = self.friendly_units_of(ctx.actor).iter().any(|&u| self.gs.unit(u).empowered && self.has_effect(self.gs.ucard(u), "extra_might_reduction"));
            if mel {
                amount -= 1;
            }
        }
        let units = self.resolve_targets(ctx, spec, if amount < 0 { "enemy" } else { "none" }, None)?;
        for unit in units {
            if truthy(spec.get("amount_if_empowered")) && self.gs.unit(unit).empowered {
                self.gs.unit_mut(unit).temporary_might += py_int(&spec["amount_if_empowered"]);
                continue;
            }
            if amount < 0 && self.gangplank_redirect(unit) {
                continue;
            }
            if amount < 0 {
                self.fire_might_reduced(unit, ctx.actor)?;
            }
            if amount < 0 && floor.is_some() {
                let m = self.gs.unit_might(unit);
                self.gs.unit_mut(unit).temporary_might -= (-amount).min((m - floor.unwrap()).max(0));
            } else {
                self.gs.unit_mut(unit).temporary_might += amount;
            }
        }
        Ok(())
    }

    /// py: _buff_unit
    fn fx_buff_unit(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let instead = spec.get("if_buffed_might").map(py_int).unwrap_or(0);
        let pref = move |g: &Game, u: UnitId| -> i64 { (instead == 0 && g.gs.unit(u).might_counters >= 1) as i64 };
        let units = self.resolve_targets(ctx, spec, "none", Some(&pref))?;
        for unit in units {
            if instead != 0 && self.gs.unit(unit).might_counters >= 1 {
                self.gs.unit_mut(unit).temporary_might += instead;
                continue;
            }
            if self.gs.unit(unit).might_counters < 1 || self.has_effect(self.gs.ucard(unit), "unlimited_buffs") {
                self.gs.unit_mut(unit).might_counters += 1;
                if let Some((ws, wbf)) = self.locate_unit(unit) {
                    let bf = wbf.unwrap_or(0);
                    self.resolve_triggered_effects(self.gs.ucard(unit), "on_buffed", bf, ws, Some(crate::lp_phases::bf_extra(bf)))?;
                    if ws == ctx.actor {
                        let mut ex = Extra::default();
                        ex.set("triggering_unit", XVal::Unit(unit));
                        let c = self.gs.ucard(unit);
                        self.fire_units_trigger("on_friendly_unit_buffed", ws, None, Some(c), Some(ex))?;
                    }
                }
            }
        }
        Ok(())
    }

    /// py: _stun_unit
    fn fx_stun_unit(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let t = spec.get("target").cloned().unwrap_or(Value::String("opponent".into()));
        let s = with(spec, "target", t);
        let mut stunned_at: Vec<Option<usize>> = Vec::new();
        for unit in self.resolve_targets(ctx, &s, "enemy", None)? {
            if self.gangplank_redirect(unit) {
                continue;
            }
            self.gs.unit_mut(unit).stunned = true;
            if let Some((ws, wbf)) = self.locate_unit(unit) {
                if ws == ctx.opponent {
                    stunned_at.push(wbf);
                }
            }
        }
        if let Some(&first) = stunned_at.first() {
            ctx.extra.set("stunned_at", match first { Some(b) => XVal::Bf(b), None => XVal::None });
            self.fire_stun_enemy(ctx.actor, first)?;
        }
        Ok(())
    }

    /// py: _recall_unit
    fn fx_recall_unit(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let t = spec.get("target").cloned().unwrap_or(Value::String("actor".into()));
        let s = with(spec, "target", t);
        if truthy(spec.get("then_play_smaller")) {
            not_ported!("_recall_unit", "then_play_smaller");
        }
        for unit in self.resolve_targets(ctx, &s, "enemy", None)? {
            self.return_unit(ctx, unit, spec)?;
        }
        Ok(())
    }

    /// py: _return_unit(ctx, unit, spec)
    pub fn return_unit(&mut self, ctx: &Ctx, unit: UnitId, spec: &Map<String, Value>) -> R<bool> {
        if self.gangplank_redirect(unit) {
            return Ok(false);
        }
        let Some((side, bf)) = self.take_off_board(unit) else { return Ok(false) };
        let gear = std::mem::take(&mut self.gs.unit_mut(unit).gear);
        self.gs.player_mut(side).base_gear.extend(gear);
        let c = self.gs.ucard(unit);
        if !self.gs.unit(unit).is_token {
            let owner = self.owner_of(c, side);
            if spec.get("to").and_then(|v| v.as_str()) == Some("deck_bottom") {
                self.gs.player_mut(owner).deck.cards.insert(0, c);
            } else {
                self.gs.player_mut(owner).to_hand(c, true);
            }
            self.gs.card_mut(c).owner = None;
        }
        self.fire_leaves_board(c, side, bf.unwrap_or(ctx.bf))?;
        Ok(true)
    }

    /// py: _move_units(ctx, spec, to_base_verb)
    fn fx_move_units(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>, to_base: bool) -> R<()> {
        let (me, them) = (ctx.actor, ctx.opponent);
        let target = sstr(spec, "target", "friendly_unit").to_lowercase();
        let scope_all = sstr(spec, "scope", "").to_lowercase() == "all" || target.starts_with("all_");
        let count = if scope_all { self.gs.battlefields.len() as i64 * 99 } else { spec.get("count").map(py_int).unwrap_or(1) };
        let candidates = self.move_candidates(ctx, spec, to_base)?;
        if candidates.is_empty() {
            ctx.extra.set("it", XVal::List(Vec::new()));
            return Ok(());
        }
        // priority, evaluated per candidate, sorted descending (stable)
        let mut keyed: Vec<(Vec<i64>, (Side, UnitId))> = Vec::new();
        for &(side, unit) in &candidates {
            let dest = self.move_dest_kind(ctx, spec, to_base, side);
            let where_ = self.locate_unit(unit);
            let at_bf = where_.map_or(false, |w| w.1.is_some());
            let m = self.gs.unit_might(unit);
            let key = if side == them {
                if dest == "here" || dest == "this_battlefield" { vec![-m] } else { vec![at_bf as i64, m] }
            } else if dest == "base" {
                let bf = where_.and_then(|w| w.1);
                let losing = bf.map_or(false, |b| {
                    let t: i64 = self.gs.battlefields[b].units_for(them).iter().map(|&u| self.gs.unit_might(u)).sum();
                    let mm: i64 = self.gs.battlefields[b].units_for(me).iter().map(|&u| self.gs.unit_might(u)).sum();
                    t > mm
                });
                vec![losing as i64, m]
            } else {
                vec![(!at_bf) as i64, m]
            };
            keyed.push((key, (side, unit)));
        }
        keyed.sort_by(|a, b| b.0.cmp(&a.0));
        let mut order: Vec<(Side, UnitId)> = keyed.into_iter().map(|k| k.1).collect();
        let mover = if sstr(spec, "mover", "") == "opponent" { them } else { me };
        let to_opt = |o: &(Side, UnitId)| Opt::Tuple(vec![Opt::Side(o.0), Opt::Unit(o.1)]);
        let from_opt = |o: &Opt| -> (Side, UnitId) {
            match o {
                Opt::Tuple(v) => match (&v[0], &v[1]) {
                    (Opt::Side(s), Opt::Unit(u)) => (*s, *u),
                    _ => unreachable!(),
                },
                _ => unreachable!(),
            }
        };
        if truthy(spec.get("any_number")) {
            not_ported!("_move_units", "any_number");
        }
        if !scope_all {
            let opts: Vec<Opt> = order.iter().map(to_opt).collect();
            let picks: Vec<Opt> = opts.iter().take(count.max(0) as usize).cloned().collect();
            let up_to = if truthy(spec.get("up_to")) { Some(count.min(order.len() as i64)) } else { None };
            let got = self.choose_many(&kind("target", spec), mover, &opts, &picks, Some(ctx.card), up_to, None)?;
            order = got.iter().map(from_opt).collect();
        }
        let mut moved: Vec<UnitId> = Vec::new();
        let mut taxed: Vec<usize> = Vec::new();
        for (side, unit) in order {
            let options = self.move_destinations(ctx, spec, to_base, side, unit)?;
            let dst: Option<usize> = if options.len() == 1 {
                options[0]
            } else {
                let fields: Vec<usize> = options.iter().filter_map(|x| *x).collect();
                let best: Option<usize> = if (side == them && options.contains(&None)) || fields.is_empty() {
                    None
                } else if side == me {
                    let mut vals = Vec::new();
                    for &f in &fields {
                        vals.push(self.attack_value_mut(side, unit, f));
                    }
                    let mut bi = 0;
                    for i in 1..vals.len() {
                        if vals[i] > vals[bi] {
                            bi = i;
                        }
                    }
                    Some(fields[bi])
                } else {
                    let mut vals = Vec::new();
                    for &f in &fields {
                        vals.push(self.attack_value_mut(side, unit, f));
                    }
                    let mut bi = 0;
                    for i in 1..vals.len() {
                        if vals[i] < vals[bi] {
                            bi = i;
                        }
                    }
                    Some(fields[bi])
                };
                let opts: Vec<Opt> = options.iter().map(|o| match o { Some(b) => Opt::Bf(*b), None => Opt::None }).collect();
                let base = match best { Some(b) => Opt::Bf(b), None => Opt::None };
                match self.choose(&kind("destination", spec), me, &opts, base, Some(ctx.card))? {
                    Opt::Bf(b) => Some(b),
                    _ => None,
                }
            };
            if let Some(d) = dst {
                if !taxed.contains(&d) {
                    if !self.pay_move_tax(mover, d)? {
                        continue;
                    }
                    taxed.push(d);
                }
            }
            if let Some((_, Some(sb))) = self.locate_unit(unit) {
                ctx.extra.set("last_move_src", XVal::Bf(sb));
            }
            if self.move_unit_by_effect(unit, dst)? {
                if truthy(spec.get("ready")) && self.can_ready(unit) {
                    self.gs.unit_mut(unit).ready = true;
                }
                moved.push(unit);
                ctx.extra.set("last_move_dst", match dst { Some(b) => XVal::Bf(b), None => XVal::None });
                if side != mover {
                    let mut ex = Extra::default();
                    ex.set("triggering_unit", XVal::Unit(unit));
                    let c = self.gs.ucard(unit);
                    self.fire_units_trigger("on_you_move_enemy", mover, None, Some(c), Some(ex))?;
                }
            }
        }
        Self::set_it(ctx, &moved);
        Ok(())
    }

    /// py: _attack_value (its bf.control() notes control: mutating)
    pub fn attack_value_mut(&mut self, side: Side, unit: UnitId, bf: usize) -> i64 {
        let mine: i64 = self.gs.battlefields[bf].units_for(side).iter().filter(|&&u| u != unit).map(|&u| self.gs.unit_might(u)).sum();
        let theirs: i64 = self.gs.battlefields[bf].units_for(side.other()).iter().map(|&u| self.gs.unit_might(u)).sum();
        if theirs != 0 && mine + self.gs.unit_might(unit) >= theirs {
            return 3;
        }
        if theirs == 0 && self.gs.battlefields[bf].control() != Some(side) {
            return 2;
        }
        if self.gs.battlefields[bf].control() == Some(side) {
            return 1;
        }
        0
    }

    /// py: _give_keyword
    fn fx_give_keyword(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let keyword = spec.get("keyword").map(py_str).unwrap_or_default().trim().to_string();
        if keyword.is_empty() || spec.get("keyword").is_none() {
            return Ok(());
        }
        let duration = sstr(spec, "duration", "").to_lowercase();
        for u in self.resolve_targets(ctx, spec, "none", None)? {
            let unit = self.gs.unit_mut(u);
            match duration.as_str() {
                "this_combat" => unit.combat_keywords.push(keyword.clone()),
                "this_turn" => unit.turn_keywords.push(keyword.clone()),
                _ => unit.granted_keywords.push(keyword.clone()),
            }
        }
        Ok(())
    }

    /// py: _give_temp_keyword
    fn fx_give_temp_keyword(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>, kw: &str) -> R<()> {
        let amount = spec.get("amount").map(py_int).unwrap_or(1);
        let mut token = format!("{kw} {amount}");
        let this_combat = sstr(spec, "duration", "").to_lowercase() == "this_combat";
        for u in self.resolve_targets(ctx, spec, "none", None)? {
            if spec.get("amount_source").and_then(|v| v.as_str()) == Some("target_might") {
                token = format!("{kw} {}", self.gs.unit_might(u));
            }
            let unit = self.gs.unit_mut(u);
            if this_combat {
                unit.combat_keywords.push(token.clone());
            } else {
                unit.turn_keywords.push(token.clone());
            }
        }
        Ok(())
    }

    /// py: _swap_might (Switcheroo, as in the reference: D71 not applied)
    fn fx_swap_might(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let side = ctx.actor;
        let mut best: Option<(UnitId, UnitId)> = None;
        let mut best_gain = 0;
        for bf in &self.gs.battlefields {
            let friendly = bf.units_for(side);
            let enemy = bf.units_for(side.other());
            if friendly.is_empty() || enemy.is_empty() {
                continue;
            }
            let u_f = min_first(friendly, |u| self.gs.unit_might(u));
            let u_e = max_first(enemy, |u| self.gs.unit_might(u));
            let gain = self.gs.unit_might(u_e) - self.gs.unit_might(u_f);
            if gain > best_gain {
                best_gain = gain;
                best = Some((u_f, u_e));
            }
        }
        let Some((mut u_f, mut u_e)) = best else { return Ok(()) };
        let bfs: Vec<usize> = (0..self.gs.battlefields.len())
            .filter(|&b| self.gs.battlefields[b].units[0].len() + self.gs.battlefields[b].units[1].len() >= 2)
            .collect();
        let base = self.locate_unit(u_f).unwrap().1.unwrap();
        let opts: Vec<Opt> = bfs.iter().map(|&b| Opt::Bf(b)).collect();
        let Opt::Bf(here) = self.choose(&kind("battlefield", spec), side, &opts, Opt::Bf(base), Some(ctx.card))? else { unreachable!() };
        let there: Vec<UnitId> = self.gs.battlefields[here].units[0].iter().chain(self.gs.battlefields[here].units[1].iter()).copied().collect();
        if !there.contains(&u_f) {
            u_f = there[0];
            u_e = there[1];
        }
        let opts: Vec<Opt> = there.iter().map(|&u| Opt::Unit(u)).collect();
        let Opt::Unit(uf) = self.choose(&kind("target", spec), side, &opts, Opt::Unit(u_f), Some(ctx.card))? else { unreachable!() };
        let others: Vec<UnitId> = there.iter().copied().filter(|&u| u != uf).collect();
        let base = if others.contains(&u_e) { u_e } else { others[0] };
        let opts: Vec<Opt> = others.iter().map(|&u| Opt::Unit(u)).collect();
        let k = kind("target", spec) + ":other";
        let Opt::Unit(ue) = self.choose(&k, side, &opts, Opt::Unit(base), Some(ctx.card))? else { unreachable!() };
        let (m_f, m_e) = (self.gs.unit_might(uf), self.gs.unit_might(ue));
        self.gs.unit_mut(uf).temporary_might += m_e - m_f;
        self.gs.unit_mut(ue).temporary_might += m_f - m_e;
        Ok(())
    }

    /// py: _swap_position
    fn fx_swap_position(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let side = ctx.actor;
        let Some(me) = self.find_unit_by_card(ctx.card) else { return Ok(()) };
        // locate: ("base") | ("bf", i) among `side`'s lists
        let locate = |g: &Game, u: UnitId| -> Option<Option<usize>> {
            if g.gs.player(side).base_units.contains(&u) {
                return Some(None);
            }
            for (i, bf) in g.gs.battlefields.iter().enumerate() {
                if bf.units_for(side).contains(&u) {
                    return Some(Some(i));
                }
            }
            None
        };
        let Some(my_loc) = locate(self, me) else { return Ok(()) };
        let named = sget(spec, "with_name").filter(|v| truthy(Some(v))).map(py_str);
        let eligible = |g: &Game, u: UnitId| u != me && match &named {
            Some(n) => g.gs.name(g.gs.ucard(u)) == n,
            None => !g.gs.unit(u).is_token,
        };
        let mut cands = Vec::new();
        for (i, bf) in self.gs.battlefields.iter().enumerate() {
            for &u in bf.units_for(side) {
                if eligible(self, u) && my_loc != Some(i) {
                    cands.push(u);
                }
            }
        }
        for &u in &self.gs.player(side).base_units {
            if eligible(self, u) && my_loc.is_some() {
                cands.push(u);
            }
        }
        if cands.is_empty() {
            return Ok(());
        }
        let base = max_first(&cands, |u| self.gs.unit_might(u));
        let opts: Vec<Opt> = cands.iter().map(|&u| Opt::Unit(u)).collect();
        let Opt::Unit(target) = self.choose(&kind("target", spec), ctx.actor, &opts, Opt::Unit(base), Some(ctx.card))? else { unreachable!() };
        let tgt_loc = locate(self, target).unwrap();
        if named.is_some() {
            self.move_unit_by_effect(me, tgt_loc)?;
            self.move_unit_by_effect(target, my_loc)?;
            return Ok(());
        }
        if truthy(spec.get("take_equipment")) && !self.gs.unit(target).gear.is_empty() {
            not_ported!("_swap_position", "take_equipment");
        }
        let remove = |g: &mut Game, u: UnitId, loc: Option<usize>| match loc {
            None => g.gs.player_mut(side).base_units.retain(|&x| x != u),
            Some(b) => g.gs.battlefields[b].units_for_mut(side).retain(|&x| x != u),
        };
        remove(self, me, my_loc);
        remove(self, target, tgt_loc);
        let place = |g: &mut Game, u: UnitId, loc: Option<usize>| match loc {
            None => g.gs.player_mut(side).base_units.push(u),
            Some(b) => g.gs.battlefields[b].add_unit(side, u),
        };
        place(self, me, tgt_loc);
        place(self, target, my_loc);
        Ok(())
    }

    /// py: _discard_card
    fn fx_discard_card(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let player = self.player_for_target(ctx, &sstr(spec, "target", "actor"))?;
        let count = if truthy(spec.get("all")) {
            self.gs.player(player).hand.len() as i64
        } else {
            match spec.get("count") {
                Some(v) => py_int(v),
                None => spec.get("amount").map(py_int).unwrap_or(1),
            }
        };
        if spec.get("chosen_by").and_then(|v| v.as_str()) == Some("controller") {
            not_ported!("_discard_card", "chosen_by controller");
        }
        let picker = player;
        let card_src = ctx.card;
        let mut last: Option<CardId> = None;
        self.discard_event(|g| {
            for _ in 0..count {
                if g.gs.player(player).hand.is_empty() {
                    break;
                }
                let hand = g.gs.player(player).hand.clone();
                let c = g.discard_choice_for(picker, player, &hand, Some(card_src))?;
                g.discard(player, c)?;
                last = Some(c);
            }
            Ok(())
        })?;
        if let Some(c) = last {
            ctx.extra.set("discarded", XVal::Card(c));
        }
        Ok(())
    }

    /// py: _play_token
    fn fx_play_token(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        if truthy(spec.get("count_if_it_friendly")) {
            not_ported!("_play_token", "count_if_it_friendly");
        }
        let token_name = sstr(spec, "token_name", "Recruit");
        let count = match spec.get("count") {
            Some(v) => py_int(v),
            None => spec.get("amount").map(py_int).unwrap_or(1),
        };
        let ready = coerce_bool(spec.get("ready").or(Some(&Value::Bool(false))));
        let player = match self.player_for_target(ctx, &sstr(spec, "target", "actor")) {
            Ok(p) => p,
            Err(EngineError::Py(_)) => ctx.actor,
            Err(e) => return Err(e),
        };
        if spec.get("target").and_then(|v| v.as_str()) == Some("it_controller") {
            not_ported!("_play_token", "it_controller");
        }
        if let Some(ts) = self.gs.reg.get(&token_name) {
            if ts.keywords.iter().any(|k| k == "DEPLOY") {
                not_ported!("_play_token", "DEPLOY token");
            }
        }
        let side = player;
        let location = sstr(spec, "location", "base").to_lowercase();
        let bf: Option<usize> = match location.as_str() {
            "here" => {
                let src = self.find_unit_by_card(ctx.card);
                let in_base = src.map_or(false, |u| self.gs.player(player).base_units.contains(&u));
                if in_base { None } else { Some(ctx.bf) }
            }
            "moved_from" => ctx.extra.bf("moved_from"),
            "choose" | "enemy_occupied" => not_ported!("_play_token", "location {location}"),
            _ => None,
        };
        let might = sget(spec, "might").map(py_int);
        let mut played: Vec<UnitId> = Vec::new();
        for _ in 0..count {
            if let Some(crate::lp_play::TokenOut::Unit(u)) = self.play_token(&token_name, side, bf, ready, might)? {
                played.push(u);
            }
        }
        Self::set_it(ctx, &played);
        Ok(())
    }

    /// py: _attach_gear (Edge of Night)
    fn fx_attach_gear(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let player = ctx.actor;
        if !self.gs.player(player).base_gear.contains(&ctx.card) {
            return Ok(());
        }
        let where_ = if truthy(spec.get("here")) { Value::String(String::new()) } else { spec.get("where").cloned().unwrap_or(Value::String("anywhere".into())) };
        let mut s = spec.clone();
        s.insert("target".into(), spec.get("target").cloned().unwrap_or(Value::String("friendly_unit".into())));
        s.insert("where".into(), where_);
        s.insert("scope".into(), Value::String("single".into()));
        let units = self.resolve_targets(ctx, &s, "none", None)?;
        if units.is_empty() {
            return Ok(());
        }
        self.gs.player_mut(player).base_gear.retain(|&g| g != ctx.card);
        self.gs.unit_mut(units[0]).gear.push(ctx.card);
        self.fire_attached(units[0], ctx.actor)
    }

    /// py: _predict
    fn fx_predict(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let amount = if truthy(spec.get("amount_source")) {
            self.effect_amount(ctx, spec)?
        } else {
            match spec.get("amount") {
                Some(v) => py_int(v),
                None => spec.get("count").map(py_int).unwrap_or(1),
            }
        };
        let side = ctx.actor;
        let n = amount.min(self.gs.player(side).deck.cards.len() as i64).max(0) as usize;
        if n == 0 {
            return Ok(());
        }
        let known = self.gs.player(side).deck.known_on_top();
        let len = self.gs.player(side).deck.cards.len();
        let look: Vec<CardId> = self.gs.player(side).deck.cards[len - n..].to_vec();
        self.offer_reveal_from_top(side, &look)?;
        let look: Vec<CardId> = look.into_iter().filter(|c| self.gs.player(side).deck.cards.contains(c)).collect();
        if look.is_empty() {
            return Ok(());
        }
        let (mut kept, mut recycled): (Vec<CardId>, Vec<CardId>) = (Vec::new(), Vec::new());
        for &card in look.iter().rev() {
            let mut recycle = false;
            if let Some(a) = self.agent(side).filter(|a| a.borrow().has("decide_predict_recycle")) {
                recycle = a.borrow_mut().decide_predict_recycle(self, side, card)?;
            }
            let got = self.choose("predict_recycle", side, &[Opt::Bool(false), Opt::Bool(true)], Opt::Bool(recycle), Some(card))?;
            if got == Opt::Bool(true) {
                recycled.push(card);
            } else {
                kept.push(card);
            }
        }
        if kept.len() > 1 {
            let mut sorted = kept.clone();
            sorted.sort_by_key(|&c| -self.gs.might(c).unwrap_or(0));
            let opts: Vec<Opt> = kept.iter().map(|&c| Opt::Card(c)).collect();
            let picks: Vec<Opt> = sorted.iter().map(|&c| Opt::Card(c)).collect();
            let got = self.choose_many("predict_order", side, &opts, &picks, Some(ctx.card), None, None)?;
            kept = got.iter().filter_map(|o| if let Opt::Card(c) = o { Some(*c) } else { None }).collect();
        }
        let deck = &mut self.gs.player_mut(side).deck;
        let rest: Vec<CardId> = deck.cards[..deck.cards.len() - look.len()].to_vec();
        let mut new: Vec<CardId> = recycled.iter().rev().copied().collect();
        new.extend(rest);
        new.extend(kept.iter().rev().copied());
        deck.cards = new;
        let mut kt = kept.clone();
        kt.extend(known.into_iter().filter(|c| !look.contains(c)));
        deck.known_top = kt;
        if !recycled.is_empty() {
            self.note_recycled(side)?;
        }
        Ok(())
    }

    /// py: _recycle_from_opponent_hand
    fn fx_recycle_from_opponent_hand(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>) -> R<()> {
        let opp = ctx.opponent;
        let hand = self.gs.player(opp).hand.clone();
        self.gs.player_mut(opp).mark_hand_public(&hand);
        let dom = sstr(spec, "domain", "").to_uppercase();
        let cands: Vec<CardId> = if truthy(spec.get("non_unit")) {
            hand.iter().copied().filter(|&c| !matches!(self.card_category_name(c), "UNIT" | "CHAMPION")).collect()
        } else {
            hand.iter().copied().filter(|&c| self.gs.domain(c).map(|d| d.name()).unwrap_or("") == dom).collect()
        };
        if cands.is_empty() {
            return Ok(());
        }
        let base = max_first(&cands, |c| self.zone_value(c));
        let opts: Vec<Opt> = cands.iter().map(|&c| Opt::Card(c)).collect();
        let Opt::Card(card) = self.choose(&kind("card", spec), ctx.actor, &opts, Opt::Card(base), Some(ctx.card))? else { unreachable!() };
        self.gs.player_mut(opp).hand.retain(|&c| c != card);
        self.gs.player_mut(opp).deck.cards.insert(0, card);
        self.note_recycled(opp)
    }

    /// py: _play_from_zone(ctx, spec, zone)
    fn fx_play_from_zone(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>, zone: &str) -> R<()> {
        let player = self.player_for_target(ctx, &sstr(spec, "target", "actor"))?;
        let side = player;
        let count = match spec.get("count") {
            Some(v) => py_int(v),
            None => spec.get("amount").map(py_int).unwrap_or(1),
        };
        let pay_power = truthy(spec.get("ignore_energy_cost")) || truthy(spec.get("pay_power"));
        let pay_cost = truthy(spec.get("pay_cost"));
        let lane = ctx.bf;
        let pool: Vec<CardId> = if zone == "trash" { self.gs.player(player).trash.clone() } else { self.gs.player(player).banished.clone() };
        let mut picks: Vec<CardId> = pool.iter().copied().filter(|&c| self.zone_effect_card_ok(c, spec)).collect();
        picks.sort_by(|&a, &b| self.zone_value(b).cmp(&self.zone_value(a)));
        if truthy(spec.get("energy_below_points")) || truthy(spec.get("cost_at_most_cost_unit")) {
            not_ported!("_play_from_zone", "energy_below_points / cost_at_most_cost_unit");
        }
        let chosen = self.gs.card(ctx.card).chosen_card;
        if let Some(ch) = chosen {
            self.gs.card_mut(ctx.card).chosen_card = None;
            picks.retain(|&c| c == ch);
        } else if !picks.is_empty() {
            let opts: Vec<Opt> = picks.iter().map(|&c| Opt::Card(c)).collect();
            let pk: Vec<Opt> = opts.iter().take(count.max(0) as usize).cloned().collect();
            let up_to = if truthy(spec.get("up_to")) { Some(count) } else { None };
            let got = self.choose_many(&kind("card", spec), side, &opts, &pk, Some(ctx.card), up_to, None)?;
            let chosen: Vec<CardId> = got.iter().filter_map(|o| if let Opt::Card(c) = o { Some(*c) } else { None }).collect();
            if truthy(spec.get("up_to")) {
                picks = chosen;
            } else {
                let mut p = chosen.clone();
                p.extend(picks.iter().copied().filter(|c| !chosen.contains(c)));
                picks = p;
            }
        }
        let mut played = 0;
        for card in picks {
            if played >= count {
                break;
            }
            let in_pool = if zone == "trash" { self.gs.player(player).trash.contains(&card) } else { self.gs.player(player).banished.contains(&card) };
            if !in_pool {
                continue;
            }
            if pay_cost {
                not_ported!("_play_from_zone", "pay_cost");
            } else if pay_power {
                let power = self.gs.cost_power(card).unwrap_or(0);
                match self.gs.cost_power_domain(card) {
                    None => {
                        if !self.pay_generic_power(player, power)? {
                            continue;
                        }
                    }
                    Some(d) => {
                        if !self.gs.player_mut(player).pay_cost(0, Some(power), Some(d)) {
                            continue;
                        }
                    }
                }
            }
            if zone == "trash" {
                self.gs.player_mut(player).trash.retain(|&c| c != card);
            } else {
                self.gs.player_mut(player).banished.retain(|&c| c != card);
            }
            if self.gs.is_unit_card(card) {
                self.play_unit(card, side, None, zone)?;
            } else if self.gs.is_gear_card(card) {
                self.play_gear(card, side, lane as i64, zone)?;
            } else if self.gs.is_spell(card) {
                self.cast_spell_now(card, side, lane, zone)?;
                if spec.get("then").and_then(|v| v.as_str()) == Some("recycle") && self.gs.player(player).trash.contains(&card) {
                    self.gs.player_mut(player).trash.retain(|&c| c != card);
                    self.gs.player_mut(player).deck.cards.insert(0, card);
                    self.note_recycled(side)?;
                }
            } else {
                self.gs.player_mut(player).to_hand(card, true);
            }
            played += 1;
        }
        Ok(())
    }

    /// py: _zone_effect_card_ok(card, spec)
    pub fn zone_effect_card_ok_impl(&self, card: CardId, spec: &Map<String, Value>) -> bool {
        let legacy: Option<&[&str]> = match spec.get("filter").map(|v| if v.is_null() { String::new() } else { py_str(v) }).unwrap_or_default().to_lowercase().as_str() {
            "gear" => Some(&["GEAR"]),
            "unit" => Some(&["UNIT", "CHAMPION"]),
            "unit_or_gear" => Some(&["UNIT", "CHAMPION", "GEAR"]),
            _ => None,
        };
        if let Some(l) = legacy {
            let cat = self.card_category_name(card);
            if !l.contains(&cat) && !(l.contains(&"GEAR") && self.gs.is_gear(card)) {
                return false;
            }
        }
        let tf = spec.get("target_filter").filter(|v| truthy(Some(v))).cloned().unwrap_or(Value::Object(Map::new()));
        if !self.zone_card_matches(card, &tf) {
            return false;
        }
        if let Some(t) = tf.get("tag") {
            if !self.gs.tags(card).contains(&py_str(t)) {
                return false;
            }
        }
        if let Some(k) = tf.get("has_keyword") {
            if !self.gs.has_keyword(card, &py_str(k)) {
                return false;
            }
        }
        let energy = self.gs.cost_energy(card);
        let power = self.gs.cost_power(card).unwrap_or(0);
        if let Some(v) = tf.get("is_token") {
            if self.gs.card_is_token(card) != truthy(Some(v)) {
                return false;
            }
        }
        if let Some(v) = tf.get("power_at_least") {
            if power < py_int(v) {
                return false;
            }
        }
        if let Some(v) = tf.get("energy_at_most") {
            if energy > py_int(v) {
                return false;
            }
        }
        if let Some(v) = tf.get("energy_at_least") {
            if energy < py_int(v) {
                return false;
            }
        }
        if let Some(v) = tf.get("power_at_most") {
            if power > py_int(v) {
                return false;
            }
        }
        true
    }
}

#[allow(dead_code)]
fn _unused(v: &[Opt]) -> Vec<UnitId> {
    units_of(v)
}
