//! py: loop.py, PHASE HELPERS (mulligan, awaken, beginning, scoring
//! triggers, exhaust, SHOW OFF, DEPLOY gear, draws).

use serde_json::Value;

use crate::game::*;
use crate::model::*;
use crate::not_ported;
use crate::types::*;

impl Game {
    /// py: _as_task — the abilities it triggers wait till the outermost task ends.
    pub fn as_task<T>(&mut self, f: impl FnOnce(&mut Game) -> R<T>) -> R<T> {
        self.task_depth += 1;
        let out = f(self);
        self.task_depth -= 1;
        let out = out?;
        if self.task_depth == 0 {
            self.flush_triggers(true)?;
        }
        Ok(out)
    }

    /// py: _as_step — its triggers go on the chain and resolve before moving on.
    pub fn as_step<T>(&mut self, f: impl FnOnce(&mut Game) -> R<T>) -> R<T> {
        self.task_depth += 1;
        let out = f(self);
        self.task_depth -= 1;
        let out = out?;
        self.flush_triggers(true)?;
        Ok(out)
    }

    /// py: _phase_mulligan
    pub fn phase_mulligan(&mut self) -> R<()> {
        for s in Side::BOTH {
            let Some(a) = self.agent(s) else { continue };
            let idx = a.borrow_mut().decide_mulligan(self, s)?;
            let gs = &mut self.gs;
            let p = &mut gs.players[s.idx()];
            p.mulligan(&idx, &mut gs.rng);
        }
        Ok(())
    }

    /// py: _ready_active_units
    pub fn ready_active_units(&mut self, active: Side) -> R<()> {
        let mut exhausted: Vec<UnitId> =
            self.gs.player(active).base_units.iter().copied().filter(|&u| !self.gs.unit(u).ready).collect();
        for bf in &self.gs.battlefields {
            exhausted.extend(bf.units_for(active).iter().copied().filter(|&u| !self.gs.unit(u).ready));
        }
        if Side::BOTH.iter().any(|&s| self.side_has_passive(s, "no_awaken_ready")) {
            exhausted.clear();
        } else {
            self.gs.ready_base_units(active);
            for i in 0..self.gs.battlefields.len() {
                self.gs.ready_side(i, active);
            }
        }
        for u in exhausted {
            if self.gs.unit(u).cant_ready {
                self.gs.unit_mut(u).ready = false;
                continue;
            }
            self.fire_readied(u, active)?;
        }
        for lu in self.legend_units(active) {
            self.gs.unit_mut(lu).ready = true;
        }
        let bg = self.gs.player(active).base_gear.clone();
        for g in bg {
            self.gs.card_mut(g).tapped = false;
        }
        let bu = self.gs.player(active).base_units.clone();
        for u in bu {
            for g in self.gs.unit(u).gear.clone() {
                self.gs.card_mut(g).tapped = false;
            }
        }
        for i in 0..self.gs.battlefields.len() {
            for u in self.gs.battlefields[i].units_for(active).clone() {
                for g in self.gs.unit(u).gear.clone() {
                    self.gs.card_mut(g).tapped = false;
                }
            }
        }
        Ok(())
    }

    /// py: _phase_beginning
    pub fn phase_beginning(&mut self, active: Side) -> R<i64> {
        self.gs.in_beginning_phase = true;
        let mut m = crate::pydict::PyDict::new();
        for s in Side::BOTH {
            m.set(s, self.gs.player(s).total_runes_in_play());
        }
        self.gs.runes_at_beginning = (self.gs.turn, m);
        let r = self.phase_beginning_steps(active);
        self.gs.in_beginning_phase = false;
        r
    }

    /// py: _phase_beginning_steps
    pub fn phase_beginning_steps(&mut self, active: Side) -> R<i64> {
        for bf in self.gs.battlefields.iter_mut() {
            bf.begin_turn_reset();
        }
        for i in 0..self.gs.battlefields.len() {
            let us: Vec<UnitId> =
                self.gs.battlefields[i].units[0].iter().chain(self.gs.battlefields[i].units[1].iter()).copied().collect();
            for u in us {
                self.gs.unit_mut(u).stunned = false;
            }
        }
        self.ready_active_units(active)?;
        {
            let p = self.gs.player_mut(active);
            p.empty_rune_pool();
            p.set_energy(0);
            p.power_pool.clear();
            p.awaken_runes();
            p.channel();
        }
        // Beginning Step: TEMPORARY units die.
        for i in 0..self.gs.battlefields.len() {
            let units = self.gs.battlefields[i].units_for(active).clone();
            if units.iter().any(|&u| self.has_effect(self.gs.ucard(u), "no_temporary_here")) {
                continue;
            }
            let dead: Vec<UnitId> = units.iter().copied().filter(|&u| self.gs.unit_has_keyword(u, "TEMPORARY")).collect();
            for &u in &dead {
                let l = self.gs.battlefields[i].units_for_mut(active);
                if let Some(p) = l.iter().position(|&x| x == u) {
                    l.remove(p);
                }
            }
            if !dead.is_empty() {
                let d: Vec<(UnitId, Side)> = dead.iter().map(|&u| (u, active)).collect();
                self.route_deaths(&d, i, false, None, false)?;
            }
        }
        let dead: Vec<UnitId> =
            self.gs.player(active).base_units.iter().copied().filter(|&u| self.gs.unit_has_keyword(u, "TEMPORARY")).collect();
        for &u in &dead {
            let l = &mut self.gs.player_mut(active).base_units;
            if let Some(p) = l.iter().position(|&x| x == u) {
                l.remove(p);
            }
        }
        if !dead.is_empty() {
            let d: Vec<(UnitId, Side)> = dead.iter().map(|&u| (u, active)).collect();
            self.route_deaths(&d, 0, true, None, false)?;
        }
        let temp_gear: Vec<CardId> =
            self.gs.player(active).base_gear.iter().copied().filter(|&g| self.gs.has_keyword(g, "TEMPORARY")).collect();
        for g in temp_gear {
            self.remove_gear(g, active)?;
        }
        let mut tg: Vec<CardId> = self.gs.player(active).base_gear.clone();
        tg.extend(self.controlled_attached_gear(active));
        for g in tg {
            if self.gs.card(g).temporary.unwrap_or(false) {
                not_ported!("_phase_beginning_steps", "gear with _temporary (Turn to Dust)");
            }
        }
        for i in 0..self.gs.battlefields.len() {
            let temp: Vec<GearId> = self.gs.battlefields[i]
                .gear[active.idx()]
                .iter()
                .copied()
                .filter(|&dg| self.gs.card(self.gs.dgear[dg.i()].card).temporary.unwrap_or(false))
                .collect();
            if !temp.is_empty() {
                not_ported!("_phase_beginning_steps", "deployed gear with _temporary");
            }
        }
        for bf in self.gs.battlefields.iter_mut() {
            bf.last_controller = bf.controller();
        }
        for bf in self.gs.battlefields.iter_mut() {
            if !bf.units[0].is_empty() && !bf.units[1].is_empty() {
                bf.contested_this_turn = true;
                if bf.controller().is_none() {
                    bf.showdown_pending = true;
                }
            }
        }
        self.fire_turn_trigger("on_start_of_turn", active)?;
        self.recompute_passives()?;
        let mut vps = 0;
        for i in 0..self.gs.battlefields.len() {
            if self.gs.battlefields[i].can_score_hold(active) {
                vps += self.gain_points(active, 1, "hold", Some(i))?;
                self.gs.battlefields[i].mark_scored(active);
                let other = active.other();
                let g = self.gs.battlefields[i].gear[other.idx()].clone();
                self.kill_deployed_gear(i, other, &g)?;
                self.fire_scoring_trigger("on_hold", i, active)?;
            }
        }
        let mut channel_count = 2;
        if self.gs.turn == 2 {
            channel_count = 3;
        }
        if Side::BOTH.iter().any(|&s| !self.units_at_battlefields_with(s, "channel_only_one").is_empty()) {
            channel_count = 1;
        }
        self.gs.player_mut(active).unlock_runes(channel_count, false);
        self.extra_channel(active);
        self.gs.player_mut(active).channel();
        Ok(vps)
    }

    /// py: _fire_turn_trigger (a task)
    pub fn fire_turn_trigger(&mut self, trigger: &str, side: Side) -> R<()> {
        self.as_task(|g| {
            for i in 0..g.gs.battlefields.len() {
                let units = g.gs.battlefields[i].units_for(side).clone();
                for u in units {
                    let mut ex = Extra::default();
                    ex.items.set("battlefield".into(), XVal::Bf(i));
                    g.resolve_triggered_effects(g.gs.ucard(u), trigger, i, side, Some(ex))?;
                    for gc in g.gs.unit(u).gear.clone() {
                        let mut ex = Extra::default();
                        ex.items.set("battlefield".into(), XVal::Bf(i));
                        ex.items.set("triggering_unit".into(), XVal::Unit(u));
                        g.resolve_triggered_effects(gc, trigger, i, side, Some(ex))?;
                    }
                }
            }
            let anchor = 0usize;
            for u in g.gs.player(side).base_units.clone() {
                g.resolve_triggered_effects(g.gs.ucard(u), trigger, anchor, side, Some(bf_extra(anchor)))?;
            }
            for lu in g.legend_units(side) {
                g.resolve_triggered_effects(g.gs.ucard(lu), trigger, anchor, side, Some(bf_extra(anchor)))?;
            }
            for gc in g.gs.player(side).base_gear.clone() {
                g.resolve_triggered_effects(gc, trigger, anchor, side, Some(bf_extra(anchor)))?;
            }
            for i in 0..g.gs.battlefields.len() {
                g.fire_deployed_gear_trigger(trigger, i, side)?;
            }
            for i in 0..g.gs.battlefields.len() {
                if let Some(c) = g.gs.battlefields[i].card {
                    g.resolve_triggered_effects(c, trigger, i, side, Some(bf_extra(i)))?;
                }
            }
            Ok(())
        })
    }

    /// py: _fire_scoring_trigger (a task)
    pub fn fire_scoring_trigger(&mut self, trigger: &str, bf: usize, side: Side) -> R<()> {
        self.as_task(|g| {
            if trigger == "on_conquer" {
                g.gs.conquered_this_turn[side.idx()] += 1;
                let t = g.gs.turn;
                g.gs.battlefields[bf].conquered_turn.set(side, t);
                for src in g.gs.player(side).trash.clone() {
                    g.resolve_triggered_effects(src, "trash_on_conquer", bf, side, Some(bf_extra(bf)))?;
                }
            } else if trigger == "on_hold" {
                g.gs.hold_points_this_turn[side.idx()] += 1;
            }
            let marker = if trigger == "on_conquer" { "double_conquer_here" } else { "double_hold_here" };
            let mut times = 1;
            for &u in g.gs.battlefields[bf].units_for(side) {
                let unit = g.gs.unit(u);
                times += g.card_effects(unit.card, &unit.gear).iter().filter(|es| es.effect == marker).count();
            }
            let here = g.gs.battlefields[bf].card;
            for _ in 0..times {
                g.scoring_effects(trigger, bf, side, here)?;
            }
            Ok(())
        })
    }

    /// py: _scoring_effects
    pub fn scoring_effects(&mut self, trigger: &str, bf: usize, side: Side, here: Option<CardId>) -> R<()> {
        let units = self.gs.battlefields[bf].units_for(side).clone();
        for u in units {
            if self.gs.unit_has_keyword(u, "HUNT") {
                let v = self.gs.unit_keyword_value(u, "HUNT");
                let amount = if v != 0 { v } else { 1 };
                self.gs.add_xp(side, amount);
            }
            if trigger == "on_conquer" {
                self.gs.unit_mut(u).conquered_turn = self.gs.turn;
                if self.gs.conquer_return.iter().any(|&(x, t)| x == u && t == self.gs.turn) {
                    not_ported!("_scoring_effects", "conquer_return (Relentless Pursuit)");
                }
            }
            let mut triggers = vec![trigger.to_string()];
            if self.gs.unit(u).gear.clone().iter().any(|&gc| self.has_effect(gc, "hold_conquer_swap")) {
                triggers.push(if trigger == "on_conquer" { "on_hold".into() } else { "on_conquer".into() });
            }
            for trig in &triggers {
                let mut cards = vec![self.gs.ucard(u)];
                cards.extend(self.gs.unit(u).gear.iter().copied());
                for c in cards {
                    self.resolve_triggered_effects(c, trig, bf, side, Some(bf_extra(bf)))?;
                }
            }
        }
        if trigger == "on_hold" && self.gs.held_hostage.iter().any(|&(s, _)| s == side) {
            not_ported!("_scoring_effects", "held_hostage (Ashe Focused)");
        }
        for lu in self.legend_units(side) {
            self.resolve_triggered_effects(self.gs.ucard(lu), trigger, bf, side, Some(bf_extra(bf)))?;
        }
        self.fire_units_trigger("on_opponent_scores", side.other(), None, None, None)?;
        self.fire_deployed_gear_trigger(trigger, bf, side)?;
        let here = if here.is_none() { self.gs.battlefields[bf].card } else { here };
        if let Some(h) = here {
            self.resolve_triggered_effects(h, trigger, bf, side, Some(bf_extra(bf)))?;
        }
        Ok(())
    }

    /// py: _exhaust(unit, side=None, bf=None)
    pub fn exhaust(&mut self, unit: UnitId, side: Option<Side>, bf: Option<usize>) -> R<()> {
        if !self.gs.unit(unit).ready {
            return Ok(());
        }
        self.gs.unit_mut(unit).ready = false;
        let sides: Vec<Side> = match side {
            Some(s) => vec![s],
            None => vec![Side::A, Side::B],
        };
        for s in sides {
            let here = self.gs.battlefields.iter().position(|b| b.units_for(s).contains(&unit));
            if side.is_none() && here.is_none() && !self.gs.player(s).base_units.contains(&unit)
                && !self.legend_units(s).contains(&unit)
            {
                continue;
            }
            let b = here.or(bf).unwrap_or(0);
            self.resolve_triggered_effects(self.gs.ucard(unit), "on_exhaust", b, s, Some(bf_extra(b)))?;
            let exc = self.gs.ucard(unit);
            self.fire_units_trigger("on_friendly_exhaust", s, Some(exc), None, None)?;
            return Ok(());
        }
        Ok(())
    }

    /// py: _fire_stun_enemy
    pub fn fire_stun_enemy(&mut self, side: Side, at: Option<usize>) -> R<()> {
        let mut ex = Extra::default();
        ex.items.set("stunned_at".into(), match at { Some(b) => XVal::Bf(b), None => XVal::None });
        self.fire_units_trigger("on_stun_enemy", side, None, None, Some(ex))
    }

    /// py: _exhaust_gear
    pub fn exhaust_gear(&mut self, gear: CardId, actor: Side) -> R<()> {
        if self.gs.card(gear).tapped {
            return Ok(());
        }
        self.gs.card_mut(gear).tapped = true;
        self.resolve_triggered_effects(gear, "on_exhaust", 0, actor, Some(bf_extra(0)))
    }

    /// py: _apply_disarm
    pub fn apply_disarm(&mut self, unit: UnitId, bf: usize, defender: Side) -> R<()> {
        let x = self.gs.unit_keyword_value(unit, "DISARM");
        let enemies = self.gs.battlefields[bf].units_for(defender).clone();
        if x <= 0 || enemies.is_empty() {
            return Ok(());
        }
        not_ported!("_apply_disarm", "DISARM")
    }

    /// py: _owner_of
    pub fn owner_of(&self, card: CardId, side: Side) -> Side {
        self.gs.card(card).owner.unwrap_or(side)
    }

    /// py: _extra_channel
    pub fn extra_channel(&mut self, side: Side) {
        let n = self.sources_in_play(side).iter().filter(|(src, _)| self.has_effect(*src, "channel_plus_one")).count();
        if n > 0 {
            self.gs.player_mut(side).unlock_runes(n as i64, true);
        }
    }

    /// py: _show_off
    pub fn show_off(&mut self, card: CardId, side: Side) -> R<()> {
        self.gs.card_mut(card).showed_off = Some(false);
        self.gs.card_mut(card).shown = None;
        if !self.gs.has_keyword(card, "SHOW OFF") {
            return Ok(());
        }
        let specs = self.gs.spec(card).effects.clone();
        let marker = specs.iter().find(|es| es.effect == "show_off").cloned();
        let tf: Value = marker.as_ref().and_then(|m| m.target_filter.clone()).unwrap_or(Value::Object(Default::default()));
        // (object card, its Might)
        let mut cands: Vec<(CardId, i64)> = Vec::new();
        for &c in &self.gs.player(side).hand {
            if c != card {
                cands.push((c, self.gs.might(c).unwrap_or(0)));
            }
        }
        let mut units: Vec<UnitId> = Vec::new();
        for bf in &self.gs.battlefields {
            units.extend(bf.units_for(side).iter().copied());
        }
        units.extend(self.gs.player(side).base_units.iter().copied());
        for u in units {
            if self.gs.ucard(u) != card {
                cands.push((self.gs.ucard(u), self.gs.unit_might(u)));
            }
            for &g in &self.gs.unit(u).gear {
                cands.push((g, 0));
            }
        }
        for &g in &self.gs.player(side).base_gear {
            if g != card {
                cands.push((g, 0));
            }
        }
        for bf in &self.gs.battlefields {
            for &dg in &bf.gear[side.idx()] {
                let c = self.gs.dgear[dg.i()].card;
                if c != card {
                    cands.push((c, 0));
                }
            }
        }
        let cands: Vec<(CardId, i64)> = cands.into_iter().filter(|(c, _)| self.show_off_matches(*c, &tf)).collect();
        if cands.is_empty() || !self.wants_optional_keyword(side, card, "SHOW OFF")? {
            return Ok(());
        }
        let reads: String = specs
            .iter()
            .find_map(|es| {
                let s = es.params.get("amount_source").map(|v| py_str(v)).unwrap_or_default();
                if s.starts_with("shown_") { Some(s) } else { None }
            })
            .unwrap_or_else(|| "shown_might".into());
        let value = |g: &Game, cm: &(CardId, i64)| -> (i64, i64, i64, i64) {
            let power = g.gs.cost_power(cm.0).unwrap_or(0);
            let energy = g.gs.cost_energy(cm.0);
            let first = match reads.as_str() {
                "shown_power_cost" => power,
                "shown_energy_cost" => energy,
                _ => cm.1,
            };
            (first, cm.1, power, energy)
        };
        // max(): the first with the highest value
        let mut best = 0;
        for i in 1..cands.len() {
            if value(self, &cands[i]) > value(self, &cands[best]) {
                best = i;
            }
        }
        let opts: Vec<Opt> = cands.iter().map(|(c, m)| Opt::Tuple(vec![Opt::Card(*c), Opt::Int(*m)])).collect();
        let got = self.choose("show_off", side, &opts, opts[best].clone(), Some(card))?;
        let (obj, might) = match got {
            Opt::Tuple(v) => match (&v[0], &v[1]) {
                (Opt::Card(c), Opt::Int(m)) => (*c, *m),
                _ => return Err(EngineError::Invalid("show_off option".into())),
            },
            _ => return Err(EngineError::Invalid("show_off option".into())),
        };
        self.gs.card_mut(card).showed_off = Some(true);
        let shown = serde_json::json!({
            "might": might,
            "power_cost": self.gs.cost_power(obj).unwrap_or(0),
            "energy_cost": self.gs.cost_energy(obj),
        });
        self.gs.card_mut(card).shown = Some(shown);
        Ok(())
    }

    /// py: _show_off_matches
    pub fn show_off_matches(&self, obj: CardId, tf: &Value) -> bool {
        if !self.zone_card_matches(obj, tf) {
            return false;
        }
        if let Some(k) = tf.get("has_keyword") {
            let kw = py_str(k).to_uppercase();
            if !self.gs.keywords(obj).iter().any(|x| {
                let x = x.to_uppercase();
                x == kw || x.starts_with(&(kw.clone() + " "))
            }) {
                return false;
            }
        }
        let energy = self.gs.cost_energy(obj);
        if let Some(v) = tf.get("energy_at_least") {
            if energy < crate::cards::py_int(v) {
                return false;
            }
        }
        if let Some(v) = tf.get("energy_at_most") {
            if energy > crate::cards::py_int(v) {
                return false;
            }
        }
        true
    }

    /// py: _deploy_gear
    pub fn deploy_gear(&mut self, side: Side, bf: usize, card: CardId, is_token: bool) -> R<()> {
        let id = self.gs.new_dgear(DGear { card, is_token });
        self.gs.battlefields[bf].gear[side.idx()].push(id);
        self.recompute_passives()
    }

    /// py: _kill_deployed_gear
    pub fn kill_deployed_gear(&mut self, bf: usize, side: Side, dead: &[GearId]) -> R<()> {
        let gear = self.gs.battlefields[bf].gear[side.idx()].clone();
        let dead: Vec<GearId> = dead.iter().copied().filter(|d| gear.contains(d)).collect();
        if dead.is_empty() {
            return Ok(());
        }
        self.gs.friendly_gear_died_this_turn[side.idx()] = true;
        for &dg in &dead {
            let l = &mut self.gs.battlefields[bf].gear[side.idx()];
            if let Some(p) = l.iter().position(|&x| x == dg) {
                l.remove(p);
            }
            if !self.gs.dgear[dg.i()].is_token {
                let c = self.gs.dgear[dg.i()].card;
                self.put_in_trash(side, c, true)?;
            }
        }
        let left = self.gs.battlefields[bf].gear[side.idx()].clone();
        let times = 1 + self.passive_count(side, "double_deathknell")
            + left.iter().filter(|&&g| self.has_effect(self.gs.dgear[g.i()].card, "double_deathknell_here")).count() as i64;
        for &dg in &dead {
            let c = self.gs.dgear[dg.i()].card;
            for _ in 0..times {
                self.resolve_triggered_effects(c, "on_death", bf, side, Some(bf_extra(bf)))?;
            }
            if !self.gs.dgear[dg.i()].is_token {
                self.fire_units_trigger("on_friendly_gear_died_at_bf", side, None, Some(c), None)?;
            }
        }
        self.recompute_passives()
    }

    /// py: _fire_deployed_gear_trigger (a task)
    pub fn fire_deployed_gear_trigger(&mut self, trigger: &str, bf: usize, side: Side) -> R<()> {
        self.as_task(|g| {
            for dg in g.gs.battlefields[bf].gear[side.idx()].clone() {
                let c = g.gs.dgear[dg.i()].card;
                g.resolve_triggered_effects(c, trigger, bf, side, Some(bf_extra(bf)))?;
            }
            Ok(())
        })
    }

    /// py: _draw_one
    pub fn draw_one(&mut self, side: Side, overflow: bool) -> R<Option<CardId>> {
        let mut card = self.gs.player_mut(side).draw();
        if card.is_none() {
            self.burn_out(side)?;
            card = self.gs.player_mut(side).draw();
        }
        if card.is_some() && overflow {
            self.zero_point_overflow(side, 1)?;
            self.gs.player_mut(side).draws_this_turn += 1;
            if self.gs.player(side).draws_this_turn == 2 {
                self.fire_units_trigger("on_second_draw", side, None, None, None)?;
            }
        }
        Ok(card)
    }

    /// py: _zero_point_overflow
    pub fn zero_point_overflow(&mut self, side: Side, drawn: i64) -> R<()> {
        let zpi = self.gs.player(side).base_gear.iter().copied().find(|&g| self.has_effect(g, "zero_point_overflow"));
        if zpi.is_none() || (self.gs.player(side).hand.len() as i64) - drawn < 9 {
            return Ok(());
        }
        not_ported!("_zero_point_overflow", "Zero Point Inflection")
    }

    /// py: _burn_out
    pub fn burn_out(&mut self, side: Side) -> R<()> {
        if !self.gs.player(side).trash.is_empty() {
            let gs = &mut self.gs;
            let p = &mut gs.players[side.idx()];
            let t: Vec<CardId> = p.trash.drain(..).collect();
            p.deck.cards.extend(t);
            p.deck.shuffle(&mut gs.rng);
        }
        self.gain_points(side.other(), 1, "burn_out", None)?;
        Ok(())
    }

    /// py: _phase_draw
    pub fn phase_draw(&mut self, ap: Side) -> R<()> {
        self.draw_one(ap, true)?;
        Ok(())
    }
}

/// {"battlefield": bf}
pub fn bf_extra(bf: usize) -> Extra {
    let mut ex = Extra::default();
    ex.items.set("battlefield".into(), XVal::Bf(bf));
    ex
}

/// py: str(v) for a JSON value as the engine reads it (a string as is).
pub fn py_str(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Null => "None".into(),
        Value::Bool(b) => if *b { "True".into() } else { "False".into() },
        other => other.to_string(),
    }
}
