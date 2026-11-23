//! py: loop.py — showdowns, opening combat, combat at one battlefield and
//! at the end of the turn; py: combat.py — damage assignment.

use crate::agent::{AIdx, AKind, Action};
use crate::game::*;
use crate::model::*;
use crate::not_ported;
use crate::types::*;

impl Game {
    /// py: _run_showdown(bf_idx, attacker)
    pub fn run_showdown(&mut self, bf_idx: usize, attacker: Option<Side>) -> R<()> {
        let attacker = attacker.unwrap();
        if self.gs.showdown_active || self.gs.winner.is_some() {
            return Ok(());
        }
        self.gs.showdown_active = true;
        self.gs.showdown_attacker = Some(attacker);
        self.gs.showdown_bf_idx = Some(bf_idx);
        self.gs.focus_player = Some(attacker);
        let ctl = self.gs.battlefields[bf_idx].control();
        self.gs.battlefields[bf_idx].contest(attacker, ctl);
        for side in [attacker, attacker.other()] {
            for u in self.gs.battlefields[bf_idx].units_for(side).clone() {
                self.resolve_triggered_effects(self.gs.ucard(u), "on_showdown_begin", bf_idx, side, Some(crate::lp_phases::bf_extra(bf_idx)))?;
            }
        }
        self.open_combat(bf_idx, attacker)?;
        let mut passes = 0;
        let mut rounds = 0;
        while passes < 2 && rounds < PRIORITY_ROUNDS_CAP && self.gs.winner.is_none() {
            rounds += 1;
            let fp = self.gs.focus_player.unwrap();
            let Some(agent) = self.agent(fp) else {
                passes += 1;
                self.gs.focus_player = Some(fp.other());
                continue;
            };
            let action = agent.borrow_mut().decide_showdown_action(self, fp, bf_idx)?;
            if let Some(j) = self.journal.as_mut() {
                j.push(JEntry::Decision(fp, "showdown_action".into(), action.clone()));
            }
            if action.kind == AKind::Pass {
                passes += 1;
            } else {
                let step = self.showdown_step(fp, &action, bf_idx)?;
                self.open_combat(bf_idx, attacker)?;
                if step == "kept" {
                    passes = 0;
                    continue;
                }
                passes = if step == "acted" { 0 } else { passes + 1 };
            }
            let fp = self.gs.focus_player.unwrap();
            self.gs.focus_player = Some(fp.other());
        }
        self.finish_showdown(bf_idx, attacker)?;
        if self.gs.chain.is_empty() {
            self.cleanup_hidden_cards()?;
        }
        self.run_staged_showdowns()
    }

    /// py: _showdown_step(player, side, action, bf_idx)
    pub fn showdown_step(&mut self, side: Side, action: &Action, bf_idx: usize) -> R<&'static str> {
        let hand_len = self.gs.player(side).hand.len() as i64;
        let idx = action.idx_int();
        match action.kind {
            AKind::Spell => {
                if let Some(i) = idx.filter(|&i| 0 <= i && i < hand_len) {
                    let card = self.gs.player(side).hand[i as usize];
                    if self.gs.is_spell(card) {
                        let has = self.gs.has_keyword(card, "ACTION") || self.has_reaction(card, side);
                        let (e, p) = self.effective_cost(card, side, Some(bf_idx as i64))?;
                        if has && self.spell_has_targets(card, side, bf_idx)? && self.pay_card(side, card, e, p, Some(bf_idx as i64))? {
                            self.gs.player_mut(side).hand.remove(i as usize);
                            self.spell_played(card, side, "hand")?;
                            self.put_on_chain(ChainItem { player: side, card, bf_idx, declared: None, choices_noted: false, owner: None, ability: None })?;
                            self.run_chain(side)?;
                            return Ok("acted");
                        }
                    }
                }
            }
            AKind::Unit if action.len4 && action.dst.is_some() => {
                if self.play_ambush_unit(side, idx.unwrap_or(-1), action.dst.unwrap())? {
                    return Ok("acted");
                }
            }
            AKind::Unit => {
                if let Some(i) = idx.filter(|&i| 0 <= i && i < hand_len) {
                    let card = self.gs.player(side).hand[i as usize];
                    if self.gs.is_unit_card(card) && (self.gs.has_keyword(card, "ACTION") || self.gs.has_keyword(card, "REACTION")) {
                        let before = self.gs.player(side).base_units.len();
                        let a = Action { len4: true, ..Action::new(AKind::Unit, AIdx::Int(i), Some(bf_idx as i64), None, String::new()) };
                        self.apply_action(side, &a, 0)?;
                        if self.gs.player(side).base_units.len() > before {
                            return Ok("acted");
                        }
                    }
                }
            }
            AKind::Gear => {
                if let Some(i) = idx.filter(|&i| 0 <= i && i < hand_len) {
                    let card = self.gs.player(side).hand[i as usize];
                    if self.gs.is_gear_card(card) && matches!(self.play_timing(card, side), Some("action") | Some("reaction")) {
                        let before = self.gs.player(side).hand.len();
                        let a = Action { len4: true, ..Action::new(AKind::Gear, AIdx::Int(i), Some(bf_idx as i64), None, String::new()) };
                        self.apply_action(side, &a, 0)?;
                        if self.gs.player(side).hand.len() < before {
                            return Ok("acted");
                        }
                    }
                }
            }
            AKind::Champion => {
                let lane = action.lane.map(|l| l as usize).unwrap_or(bf_idx);
                if self.deploy_ambush_champion(side, lane)? {
                    return Ok("acted");
                }
            }
            AKind::HiddenPlay => {
                let lane = action.lane.map(|l| l as usize).unwrap_or(bf_idx);
                if self.play_from_hidden(side, lane, idx.unwrap_or(0) as usize)? {
                    return Ok("acted");
                }
            }
            AKind::Ability => {
                let chained = (self.chained_abilities, self.spells_cast);
                if self.use_ability_now(side, &action.index, action.lane)? {
                    return Ok(if (self.chained_abilities, self.spells_cast) != chained { "acted" } else { "kept" });
                }
            }
            _ => {}
        }
        Ok("noop")
    }

    /// py: _finish_showdown (a step)
    pub fn finish_showdown(&mut self, bf_idx: usize, attacker: Side) -> R<()> {
        self.as_step(|g| {
            g.gs.showdown_active = false;
            g.gs.showdown_bf_idx = None;
            g.gs.showdown_attacker = None;
            g.gs.focus_player = None;
            let b = &g.gs.battlefields[bf_idx];
            if !b.units[0].is_empty() && !b.units[1].is_empty() {
                return g.phase_combat_and_conquer_single(bf_idx, attacker);
            }
            let b = &mut g.gs.battlefields[bf_idx];
            b.combat_designated.clear();
            b.combat_started = false;
            b.establish_control();
            for s in Side::BOTH {
                let b = &g.gs.battlefields[bf_idx];
                if !b.units_for(s).is_empty() && b.units_for(s.other()).is_empty() {
                    if b.can_score_conquer(s) {
                        g.gain_points(s, 1, "conquer", Some(bf_idx))?;
                        g.gs.battlefields[bf_idx].mark_scored(s);
                        g.fire_scoring_trigger("on_conquer", bf_idx, s)?;
                    }
                }
            }
            Ok(())
        })
    }

    /// py: _open_combat (a step)
    pub fn open_combat(&mut self, bf: usize, attacker: Side) -> R<()> {
        self.as_step(|g| g.open_combat_body(bf, attacker))
    }

    fn open_combat_body(&mut self, bf: usize, attacker: Side) -> R<()> {
        let defender = attacker.other();
        if self.gs.battlefields[bf].units[0].is_empty() || self.gs.battlefields[bf].units[1].is_empty() {
            return Ok(());
        }
        let fresh = !self.gs.battlefields[bf].combat_started;
        if fresh {
            self.gs.battlefields[bf].combat_started = true;
            if let Some(bc) = self.gs.battlefields[bf].card {
                for s in [attacker, defender] {
                    self.resolve_triggered_effects(bc, "on_combat_start_here", bf, s, Some(crate::lp_phases::bf_extra(bf)))?;
                }
            }
        }
        let mut new: [Vec<UnitId>; 2] = [Vec::new(), Vec::new()];
        for s in [attacker, defender] {
            let b = &self.gs.battlefields[bf];
            new[s.idx()] = b.units_for(s).iter().copied().filter(|u| !b.combat_designated.contains(u)).collect();
        }
        for s in [attacker, defender] {
            for &u in &new[s.idx()] {
                if !self.gs.battlefields[bf].combat_designated.contains(&u) {
                    self.gs.battlefields[bf].combat_designated.push(u);
                }
            }
        }
        self.gs.battlefields[bf].combat_attacker = Some(attacker);
        self.refresh_combat_keywords();
        for &unit in &new[attacker.idx()] {
            let mut cards = vec![self.gs.ucard(unit)];
            cards.extend(self.gs.unit(unit).gear.iter().copied());
            for c in cards {
                self.resolve_triggered_effects(c, "on_attack", bf, attacker, Some(crate::lp_phases::bf_extra(bf)))?;
            }
            self.apply_disarm(unit, bf, defender)?;
        }
        for (s, trig) in [(attacker, "on_friendly_attack"), (defender, "on_friendly_defend")] {
            let n_fighters = self.gs.battlefields[bf].units_for(s).len();
            for &unit in &new[s.idx()] {
                let mut ex = crate::lp_phases::bf_extra(bf);
                ex.set("triggering_unit", XVal::Unit(unit));
                ex.set("alone", XVal::Bool(n_fighters == 1));
                let c = self.gs.ucard(unit);
                self.fire_units_trigger(trig, s, None, Some(c), Some(ex))?;
            }
        }
        for &unit in &new[defender.idx()] {
            let mut cards = vec![self.gs.ucard(unit)];
            cards.extend(self.gs.unit(unit).gear.iter().copied());
            for c in cards {
                self.resolve_triggered_effects(c, "on_defend", bf, defender, Some(crate::lp_phases::bf_extra(bf)))?;
            }
        }
        if self.gs.battlefields[bf].control() == Some(defender) {
            for &unit in &new[attacker.idx()] {
                let mut ex = crate::lp_phases::bf_extra(bf);
                ex.set("triggering_unit", XVal::Unit(unit));
                let c = self.gs.ucard(unit);
                self.fire_units_trigger("on_enemy_attack", defender, None, Some(c), Some(ex))?;
            }
        }
        if fresh {
            for (s, trig) in [(attacker, "on_attack"), (defender, "on_defend")] {
                if let Some(bc) = self.gs.battlefields[bf].card {
                    self.resolve_triggered_effects(bc, trig, bf, s, Some(crate::lp_phases::bf_extra(bf)))?;
                }
                self.fire_deployed_gear_trigger(trig, bf, s)?;
            }
            let mut ex = Extra::default();
            ex.set("defended_at", XVal::Bf(bf));
            self.fire_units_trigger("on_you_defend", defender, None, None, Some(ex))?;
        }
        Ok(())
    }

    /// py: _phase_combat_and_conquer_single (a step)
    pub fn phase_combat_and_conquer_single(&mut self, bf_idx: usize, attacker: Side) -> R<()> {
        self.as_step(|g| g.combat_single_body(bf_idx, attacker))
    }

    fn combat_single_body(&mut self, bf: usize, attacker: Side) -> R<()> {
        self.recompute_passives()?;
        let before = [self.gs.battlefields[bf].units[0].clone(), self.gs.battlefields[bf].units[1].clone()];
        let defender = attacker.other();
        self.open_combat(bf, attacker)?;
        self.gs.battlefields[bf].combat_designated.clear();
        self.gs.battlefields[bf].combat_started = false;
        let (dead_a, dead_b, excess_a, excess_b) = self.resolve_combat_might(bf, attacker)?;
        let t = self.gs.turn;
        let mut ex = crate::pydict::PyDict::new();
        ex.set(Side::A, (t, excess_a));
        ex.set(Side::B, (t, excess_b));
        self.gs.battlefields[bf].excess_damage = ex;
        self.route_combat_deaths(&dead_a, &dead_b, bf)?;
        for u in self.all_units_in_play() {
            self.gs.unit_mut(u).damage = 0;
        }
        if !self.gs.battlefields[bf].units[0].is_empty() && !self.gs.battlefields[bf].units[1].is_empty() {
            let tie_all = self.sources_in_play(attacker).iter().any(|(s, _)| self.has_effect(*s, "tie_recall_all"));
            let sides: Vec<Side> = if tie_all { vec![attacker, defender] } else { vec![attacker] };
            for s in sides {
                for u in self.gs.battlefields[bf].units_for(s).clone() {
                    self.gs.battlefields[bf].remove_unit(s, u);
                    self.gs.player_mut(s).base_units.push(u);
                }
            }
        }
        for s in Side::BOTH {
            for &unit in &before[s.idx()] {
                if self.locate_unit(unit).is_some() {
                    self.resolve_triggered_effects(self.gs.ucard(unit), "on_combat_end", bf, s, Some(crate::lp_phases::bf_extra(bf)))?;
                }
                self.gs.unit_mut(unit).clear_combat_bonuses();
            }
        }
        for winner in Side::BOTH {
            let b = &self.gs.battlefields[bf];
            if !b.units_for(winner).is_empty() && b.units_for(winner.other()).is_empty() {
                self.fire_units_trigger("on_win_combat", winner, None, None, None)?;
                self.fire_deployed_gear_trigger("on_win_combat", bf, winner)?;
                for u in self.gs.battlefields[bf].units_for(winner).clone() {
                    if self.gs.unit(u).win_xp_turn == self.gs.turn {
                        self.gs.add_xp(winner, 2);
                    }
                }
            }
        }
        self.gs.battlefields[bf].establish_control();
        if self.gs.battlefields[bf].can_score_conquer(attacker) {
            self.gain_points(attacker, 1, "conquer", Some(bf))?;
            self.gs.battlefields[bf].mark_scored(attacker);
            self.fire_scoring_trigger("on_conquer", bf, attacker)?;
        }
        Ok(())
    }

    /// py: _combat_might_mods(bf, attacker) -> (unit, change)
    pub fn combat_might_mods(&self, bf: usize, attacker: Option<Side>) -> Vec<(UnitId, i64)> {
        let Some(attacker) = attacker else { return Vec::new() };
        let defender = attacker.other();
        let b = &self.gs.battlefields[bf];
        let mut mods: Vec<(UnitId, i64)> = Vec::new();
        let mut add = |u: UnitId, n: i64| {
            if let Some(e) = mods.iter_mut().find(|(x, _)| *x == u) {
                e.1 += n;
            } else {
                mods.push((u, n));
            }
        };
        if b.card.map_or(false, |c| self.has_effect(c, "lone_defender_minus")) && b.units_for(defender).len() == 1 {
            add(b.units_for(defender)[0], -2);
        }
        if self.legend_with(defender, "lone_defender_bonus", false).is_some() && b.units_for(defender).len() == 1 {
            add(b.units_for(defender)[0], 2);
        }
        for s in [attacker, defender] {
            let f = b.units_for(s);
            if f.len() == 1 && self.has_effect(self.gs.ucard(f[0]), "lone_fighter_bonus") {
                add(f[0], 2);
            }
        }
        let atk = b.units_for(attacker);
        if atk.len() >= 2 {
            for &u in atk {
                if self.has_effect(self.gs.ucard(u), "attacking_with_another_bonus") {
                    add(u, 2);
                }
            }
        }
        mods
    }

    /// py: _phase_combat_and_conquer(active)
    pub fn phase_combat_and_conquer(&mut self, active: Side) -> R<()> {
        self.recompute_passives()?;
        for i in 0..self.gs.battlefields.len() {
            self.gs.battlefields[i].establish_control();
            if !self.gs.battlefields[i].contested_this_turn {
                continue;
            }
            if !self.gs.battlefields[i].units[0].is_empty() && !self.gs.battlefields[i].units[1].is_empty() {
                self.phase_combat_and_conquer_single(i, active)?;
                continue;
            }
            if self.gs.battlefields[i].can_score_conquer(active) {
                self.gain_points(active, 1, "conquer", Some(i))?;
                self.gs.battlefields[i].mark_scored(active);
                self.fire_scoring_trigger("on_conquer", i, active)?;
            }
        }
        Ok(())
    }

    // ------------------------------------------------- py: combat.py ---

    /// py: combat._is_dead
    pub fn is_dead(&self, u: UnitId) -> bool {
        let m = self.gs.unit_might(u);
        if m == 0 { self.gs.unit(u).damage > 0 } else { self.gs.unit(u).damage >= m }
    }

    /// py: combat._lethal
    pub fn lethal(&self, u: UnitId) -> i64 {
        let m = self.gs.unit_might(u);
        (if m == 0 { 1 } else { (m - self.gs.unit(u).damage).max(0) }) + self.gs.unit(u).damage_shield
    }

    /// py: combat.kill_order
    pub fn kill_order(&self, units: &[UnitId], damage: i64) -> Vec<UnitId> {
        if units.len() > 10 {
            let mut v = units.to_vec();
            v.sort_by_key(|&u| self.lethal(u));
            return v;
        }
        let mut best: Vec<UnitId> = Vec::new();
        let mut best_value = (0i64, 0usize);
        for mask in 1u32..(1u32 << units.len()) {
            let pick: Vec<UnitId> = units.iter().enumerate().filter(|(i, _)| mask >> i & 1 == 1).map(|(_, &u)| u).collect();
            if pick.iter().map(|&u| self.lethal(u)).sum::<i64>() > damage {
                continue;
            }
            let value = (pick.iter().map(|&u| self.gs.unit_might(u)).sum::<i64>(), pick.len());
            if value > best_value {
                best = pick;
                best_value = value;
            }
        }
        best.sort_by_key(|&u| -self.gs.unit_might(u));
        let mut out = best.clone();
        out.extend(units.iter().copied().filter(|u| !best.contains(u)));
        out
    }

    /// py: combat._chosen_order with first = the combat_damage_order choice of `assigner`
    fn chosen_order(&mut self, group: &[UnitId], damage: i64, assigner: Side) -> R<(Vec<UnitId>, i64)> {
        let mut alive: Vec<UnitId> = group.iter().copied().filter(|&u| !self.is_dead(u)).collect();
        let dead: Vec<UnitId> = group.iter().copied().filter(|&u| self.is_dead(u)).collect();
        let mut order: Vec<UnitId> = Vec::new();
        let mut damage = damage;
        while alive.len() > 1 && 0 < damage && damage < alive.iter().map(|&u| self.lethal(u)).sum::<i64>() {
            let base = self.kill_order(&alive, damage)[0];
            let opts: Vec<Opt> = alive.iter().map(|&u| Opt::Unit(u)).collect();
            let Opt::Unit(pick) = self.choose("combat_damage_order", assigner, &opts, Opt::Unit(base), None)? else { unreachable!() };
            order.push(pick);
            alive.retain(|&u| u != pick);
            damage -= self.lethal(pick);
        }
        let rest: Vec<UnitId>;
        if damage > 0 {
            rest = if alive.is_empty() { Vec::new() } else { self.kill_order(&alive, damage) };
            damage -= alive.iter().map(|&u| self.lethal(u)).sum::<i64>();
        } else {
            rest = alive;
        }
        order.extend(rest);
        order.extend(dead);
        Ok((order, damage.max(0)))
    }

    /// py: combat._ordered_targets (with `first` and `conflict` callbacks of `assigner`)
    fn ordered_targets(&mut self, units: &[UnitId], ignore_tank: bool, damage: i64, assigner: Side) -> R<Vec<UnitId>> {
        let (mut tanks, mut normal, mut backline) = (Vec::new(), Vec::new(), Vec::new());
        for &u in units {
            let mut tank = self.gs.unit_has_keyword(u, "TANK") && !ignore_tank;
            if tank && self.gs.unit_has_keyword(u, "BACKLINE") {
                let opts = [Opt::Str("TANK".into()), Opt::Str("BACKLINE".into())];
                let c = self.gs.ucard(u);
                let got = self.choose("combat_tank_or_backline", assigner, &opts, opts[0].clone(), Some(c))?;
                tank = got != Opt::Str("BACKLINE".into());
            }
            if tank {
                tanks.push(u);
            } else if self.gs.unit_has_keyword(u, "BACKLINE") {
                backline.push(u);
            } else {
                normal.push(u);
            }
        }
        if ignore_tank {
            normal.sort_by_key(|&u| self.gs.unit_might(u) - self.gs.unit(u).damage);
        }
        let mut out = Vec::new();
        let mut damage = damage;
        for group in [tanks, normal, backline] {
            let (ordered, d) = self.chosen_order(&group, damage, assigner)?;
            damage = d;
            out.extend(ordered);
        }
        Ok(out)
    }

    /// py: combat._apply_damage (take = combat _take_damage)
    fn apply_combat_damage(&mut self, units: &[UnitId], damage: i64, ignore_tank: bool, assigner: Side) -> R<(i64, i64)> {
        let mut damage = damage;
        let mut assigned = 0;
        let mut kills = 0;
        for unit in self.ordered_targets(units, ignore_tank, damage, assigner)? {
            if damage <= 0 {
                break;
            }
            if self.is_dead(unit) {
                continue;
            }
            if self.gs.unit_might(unit) == 0 {
                let n = (1 + self.gs.unit(unit).damage_shield).min(damage);
                let t = self.take_damage(unit, n, "combat", None, None)?;
                self.gs.unit_mut(unit).damage += t;
                damage -= n;
                assigned += n;
                if self.is_dead(unit) {
                    kills += 1;
                }
                continue;
            }
            let remaining = self.gs.unit_might(unit) - self.gs.unit(unit).damage + self.gs.unit(unit).damage_shield;
            let to_assign = remaining.min(damage);
            let t = self.take_damage(unit, to_assign, "combat", None, None)?;
            self.gs.unit_mut(unit).damage += t;
            damage -= to_assign;
            assigned += to_assign;
            if self.is_dead(unit) {
                kills += 1;
            }
        }
        Ok((kills, assigned))
    }

    /// py: Battlefield.resolve_combat_might + combat.resolve_might_combat with
    /// _combat_mods. -> (dead A, dead B, excess by A, excess by B)
    pub fn resolve_combat_might(&mut self, bf: usize, attacker: Side) -> R<(Vec<UnitId>, Vec<UnitId>, i64, i64)> {
        let mods = self.combat_might_mods(bf, Some(attacker));
        let surfer = |g: &Game, s: Side| g.gs.battlefields[bf].units_for(s).iter().any(|&u| g.has_effect(g.gs.ucard(u), "ignore_tank_here"));
        let (ignore_a, ignore_b) = (surfer(self, Side::B), surfer(self, Side::A));
        let a_attacks = attacker == Side::A;
        let units_a = self.gs.battlefields[bf].units[0].clone();
        let units_b = self.gs.battlefields[bf].units[1].clone();
        for &u in &units_a {
            let v = self.gs.unit_keyword_value(u, if a_attacks { "ASSAULT" } else { "SHIELD" });
            self.gs.unit_mut(u).bonus_might = v;
        }
        for &u in &units_b {
            let v = self.gs.unit_keyword_value(u, if !a_attacks { "ASSAULT" } else { "SHIELD" });
            self.gs.unit_mut(u).bonus_might = v;
        }
        for &u in units_a.iter().chain(units_b.iter()) {
            let m = mods.iter().find(|(x, _)| *x == u).map(|m| m.1).unwrap_or(0);
            self.gs.unit_mut(u).bonus_might += m;
        }
        let total = |g: &Game, us: &[UnitId]| -> i64 {
            us.iter().filter(|&&u| !g.gs.unit(u).stunned && !g.gs.unit(u).no_combat_damage).map(|&u| g.gs.unit_might(u)).sum()
        };
        let damage_to_a = total(self, &units_b);
        let damage_to_b = total(self, &units_a);
        let (kills_a, assigned_a) = self.apply_combat_damage(&units_a, damage_to_a, ignore_a, Side::B)?;
        let (kills_b, assigned_b) = self.apply_combat_damage(&units_b, damage_to_b, ignore_b, Side::A)?;
        let excess_by_b = (damage_to_a - assigned_a).max(0);
        let excess_by_a = (damage_to_b - assigned_b).max(0);
        let dead_a: Vec<UnitId> = units_a.iter().copied().filter(|&u| self.is_dead(u)).collect();
        let dead_b: Vec<UnitId> = units_b.iter().copied().filter(|&u| self.is_dead(u)).collect();
        // units_a[:] = alive (the battlefield's own lists, in place)
        let alive_a: Vec<UnitId> = self.gs.battlefields[bf].units[0].iter().copied().filter(|&u| !self.is_dead(u)).collect();
        let alive_b: Vec<UnitId> = self.gs.battlefields[bf].units[1].iter().copied().filter(|&u| !self.is_dead(u)).collect();
        self.gs.battlefields[bf].units[0] = alive_a.clone();
        self.gs.battlefields[bf].units[1] = alive_b.clone();
        for u in alive_a.into_iter().chain(alive_b) {
            self.gs.unit_mut(u).reset_damage();
        }
        let b = &mut self.gs.battlefields[bf];
        b.kills[0] += kills_a;
        b.kills[1] += kills_b;
        b.deaths[0] += kills_a;
        b.deaths[1] += kills_b;
        b.note_control();
        b.after_change();
        Ok((dead_a, dead_b, excess_by_a, excess_by_b))
    }

    /// Not in EK: abilities that need a target arena (placeholder for clarity).
    pub fn not_in_ek(&self, what: &str) -> R<()> {
        not_ported!("engine", "{what}")
    }
}
