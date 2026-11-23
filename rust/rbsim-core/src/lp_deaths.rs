//! py: loop.py — death replacements, routing deaths (a task), damage taken.

use crate::cards::py_int;
use crate::game::*;
use crate::model::*;
use crate::not_ported;
use crate::types::*;

const DEATH_REPLACEMENT_EFFECTS: [&str; 2] = ["replace_death_with_recall", "prevent_death"];

impl Game {
    /// py: _unit_death_replacement (whether there is one; none in EK)
    pub fn unit_death_replacement_any(&self, unit: UnitId) -> bool {
        let c = self.gs.ucard(unit);
        let own = self.gs.spec(c).effects.iter().any(|es| es.trigger == "death_replacement" && DEATH_REPLACEMENT_EFFECTS.contains(&es.effect.as_str()));
        own || self.gs.unit(unit).gear.iter().any(|&g| {
            self.gs.spec(g).effects.iter().any(|es| es.trigger == "death_replacement" && DEATH_REPLACEMENT_EFFECTS.contains(&es.effect.as_str()))
        })
    }

    /// py: _try_replace_death(dead_unit, owner_side, bf=None, in_combat=False)
    pub fn try_replace_death(&mut self, dead: UnitId, owner: Side, bf: Option<usize>, in_combat: bool) -> R<bool> {
        if self.has_effect(self.gs.ucard(dead), "sacrifice_instead_of_dying") {
            not_ported!("_try_replace_death", "sacrifice_instead_of_dying (Mordekaiser)");
        }
        if let Some(b) = bf {
            let dm = self.gs.unit_might(dead);
            if self.gs.battlefields[b].units_for(owner).iter().any(|&u| {
                u != dead && self.has_effect(self.gs.ucard(u), "protect_weaker_here") && dm < self.gs.unit_might(u)
            }) {
                not_ported!("_try_replace_death", "protect_weaker_here (Soraka)");
            }
        }
        let mut repl = self.unit_death_replacement_any(dead);
        if !repl {
            for &g in &self.gs.player(owner).base_gear {
                if self.gs.spec(g).effects.iter().any(|e| e.trigger == "death_replacement" && DEATH_REPLACEMENT_EFFECTS.contains(&e.effect.as_str())) {
                    repl = true;
                    break;
                }
            }
        }
        if !repl && self.gs.unit(dead).ward_turn == self.gs.turn {
            not_ported!("_try_replace_death", "ward (Tactical Retreat, Unlicensed Armory)");
        }
        if !repl && self.legend_with(owner, "sett_save", true).is_some() && self.gs.unit(dead).might_counters > 0 {
            not_ported!("_try_replace_death", "sett_save");
        }
        if !repl && in_combat {
            if let Some(b) = bf {
                if let Some(bc) = self.gs.battlefields[b].card {
                    if self.has_effect(bc, "altar_of_blood") {
                        not_ported!("_try_replace_death", "altar_of_blood");
                    }
                }
            }
        }
        if !repl {
            return Ok(false);
        }
        not_ported!("_try_replace_death", "death replacement (Guardian Angel / Zhonya's)")
    }

    /// py: _route_combat_deaths(stats, bf)
    pub fn route_combat_deaths(&mut self, dead_a: &[UnitId], dead_b: &[UnitId], bf: usize) -> R<()> {
        let mut ordered: Vec<(UnitId, Side)> = dead_a.iter().map(|&u| (u, Side::A)).collect();
        ordered.extend(dead_b.iter().map(|&u| (u, Side::B)));
        self.route_deaths(&ordered, bf, false, None, true)
    }

    /// py: _route_deaths(ordered, bf, in_base=False, killer=None, in_combat=False) (a task)
    pub fn route_deaths(&mut self, ordered: &[(UnitId, Side)], bf: usize, in_base: bool, killer: Option<(Side, CardId)>,
                        in_combat: bool) -> R<()> {
        let ordered = ordered.to_vec();
        self.as_task(move |g| g.route_deaths_body(&ordered, bf, in_base, killer, in_combat))
    }

    fn route_deaths_body(&mut self, ordered: &[(UnitId, Side)], bf: usize, in_base: bool, killer: Option<(Side, CardId)>,
                         in_combat: bool) -> R<()> {
        let mut truly_dead: Vec<(UnitId, Side)> = Vec::new();
        if let Some((ksi, kcard)) = killer {
            if self.gs.is_spell(kcard) && !ordered.is_empty() {
                for src in self.gs.player(ksi).trash.clone() {
                    self.resolve_triggered_effects(src, "trash_on_spell_kill", bf, ksi, Some(crate::lp_phases::bf_extra(bf)))?;
                }
            }
        }
        for &(dead, owner_side) in ordered {
            if self.gs.unit(dead).banish_if_dies_turn == self.gs.turn {
                not_ported!("_route_deaths", "banish_if_dies (Smite)");
            }
            if self.try_replace_death(dead, owner_side, if in_base { None } else { Some(bf) }, in_combat)? {
                continue;
            }
            let c = self.gs.ucard(dead);
            let to = self.owner_of(c, owner_side);
            self.to_trash(to, c)?;
            self.gs.card_mut(c).owner = None;
            let gear = self.gs.unit(dead).gear.clone();
            self.gs.player_mut(owner_side).base_gear.extend(gear);
            self.gs.friendly_unit_died_this_turn[owner_side.idx()] = true;
            if self.gs.unit_is_gear(dead) {
                self.gs.friendly_gear_died_this_turn[owner_side.idx()] = true;
            }
            if self.gs.in_beginning_phase && owner_side == self.gs.active {
                let t = self.gs.turn;
                self.gs.died_in_beginning.set(owner_side, t);
            }
            truly_dead.push((dead, owner_side));
        }
        for &(dead, owner_side) in &truly_dead {
            let here_empty = if in_base {
                self.gs.player(owner_side).base_units.is_empty()
            } else {
                self.gs.battlefields[bf].units_for(owner_side).is_empty()
            };
            let alone = here_empty && truly_dead.iter().filter(|(_, s)| *s == owner_side).count() == 1;
            let mut times = 1 + self.passive_count(owner_side, "double_deathknell");
            if !in_base {
                times += self.gs.battlefields[bf].gear[owner_side.idx()]
                    .iter()
                    .filter(|&&dg| self.has_effect(self.gs.dgear[dg.i()].card, "double_deathknell_here"))
                    .count() as i64;
            }
            let dcard = self.gs.ucard(dead);
            let dgear = self.gs.unit(dead).gear.clone();
            for _ in 0..times {
                let mut cards = vec![dcard];
                cards.extend(dgear.iter().copied());
                for c in cards {
                    let mut ex = crate::lp_phases::bf_extra(bf);
                    ex.set("died_alone", XVal::Bool(alone));
                    ex.set("died_might", XVal::Int(self.gs.unit_might(dead)));
                    ex.set("died_empowered", XVal::Bool(self.gs.unit(dead).empowered));
                    ex.set("died_in_combat", XVal::Bool(in_combat));
                    ex.set("died_card", XVal::Card(dcard));
                    ex.set("died_gear", XVal::List(dgear.iter().map(|&g| XVal::Card(g)).collect()));
                    self.resolve_triggered_effects(c, "on_death", bf, owner_side, Some(ex))?;
                }
            }
            self.gs.unit_mut(dead).gear.clear();
            if let Some(b) = &self.gs.unit(dead).death_bonus {
                if b.get(1).map(py_int) == Some(self.gs.turn) {
                    not_ported!("_route_deaths", "death_bonus (Deadly Flourish)");
                }
            }
            self.fire_leaves_board(dcard, owner_side, bf)?;
            let mut ex = Extra::default();
            ex.set("triggering_unit", XVal::Unit(dead));
            self.fire_units_trigger("on_friendly_unit_death", owner_side, Some(dcard), None, Some(ex))?;
            let mut ex = Extra::default();
            ex.set("triggering_unit", XVal::Unit(dead));
            ex.set("died_at", if in_base { XVal::None } else { XVal::Bf(bf) });
            self.fire_units_trigger("on_enemy_unit_died", owner_side.other(), None, Some(dcard), Some(ex))?;
            if !in_base && !self.gs.unit(dead).is_token {
                if let Some(bc) = self.gs.battlefields[bf].card {
                    if self.has_trigger(bc, "on_unit_dies_here") {
                        not_ported!("_route_deaths", "on_unit_dies_here (Black Rose Sanctum)");
                    }
                }
            }
            if self.gs.unit(dead).stunned && !in_base {
                let enemy = owner_side.other();
                for u in self.gs.battlefields[bf].units_for(enemy).clone() {
                    let mut ex = crate::lp_phases::bf_extra(bf);
                    let _ = &mut ex;
                    self.resolve_triggered_effects(self.gs.ucard(u), "on_stunned_enemy_dies_here", bf, enemy, Some(ex))?;
                }
            }
        }
        Ok(())
    }

    /// py: _take_damage(unit, amount, kind="spell", source_side=None, source=None)
    pub fn take_damage(&mut self, unit: UnitId, amount: i64, kind: &str, source_side: Option<Side>,
                       source: Option<CardId>) -> R<i64> {
        let _ = source;
        if amount <= 0 {
            return Ok(0);
        }
        let mut amount = amount;
        let owner = self.locate_unit(unit).map(|(s, _)| s);
        let turn = self.gs.turn;
        let mut source_side = source_side;
        if kind == "spell" {
            if self.gs.no_spell_damage_turn == turn {
                return Ok(0);
            }
            if let Some(ss) = source_side {
                amount += self.spell_bonus(ss);
                if self.gs.unit(unit).spell_immune && owner.is_some() && Some(ss) != owner {
                    return Ok(0);
                }
            }
        }
        if self.has_effect(self.gs.ucard(unit), "no_damage_if_moved_twice") && self.gs.unit(unit).moves_this_turn >= 2 {
            return Ok(0);
        }
        if self.gs.unit(unit).prevent_next_turn == turn {
            self.gs.unit_mut(unit).prevent_next_turn = -1;
            return Ok(0);
        }
        if kind != "combat" && self.gs.unit(unit).empowered && self.has_effect(self.gs.ucard(unit), "no_damage_outside_combat") {
            not_ported!("_take_damage", "no_damage_outside_combat (Ambessa)");
        }
        if self.gs.unit(unit).double_damage_turn == turn {
            amount *= 2;
        }
        if self.gs.unit(unit).damage_shield != 0 {
            let absorbed = self.gs.unit(unit).damage_shield.min(amount);
            self.gs.unit_mut(unit).damage_shield -= absorbed;
            amount -= absorbed;
        }
        if kind == "combat" && source_side.is_none() {
            if let Some(o) = owner {
                source_side = Some(o.other());
            }
        }
        if amount > 0 {
            self.gs.unit_mut(unit).damaged_turn = turn;
        }
        if amount > 0 {
            if let (Some(ss), Some(o)) = (source_side, owner) {
                if o != ss && self.side_has_passive(ss, "lethal_damage") {
                    self.gs.unit_mut(unit).doomed_turn = turn;
                }
            }
        }
        if amount > 0 && (self.gs.decree_turn == turn || self.gs.unit(unit).doomed_turn == turn) {
            self.gs.unit_mut(unit).doomed_turn = -1;
            let m = self.gs.unit_might(unit) - self.gs.unit(unit).damage;
            return Ok(amount.max(m).max(1));
        }
        Ok(amount)
    }

    /// py: _spell_bonus
    pub fn spell_bonus(&self, side: Side) -> i64 {
        let mut total = 0;
        for (src, _) in self.sources_in_play(side) {
            if self.gs.player(side).base_gear.contains(&src) && self.equip_cost(src).is_some() {
                continue;
            }
            total += self
                .card_effects_auto(src)
                .iter()
                .filter(|es| es.trigger == "passive" && es.effect == "spell_bonus_damage")
                .map(|es| es.params.get("amount").map(py_int).unwrap_or(1))
                .sum::<i64>();
        }
        total
    }
}
