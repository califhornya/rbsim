//! py: loop.py — delayed effects, start of main / ending step, legends,
//! continuous abilities (_recompute_passives and its helpers), DEFLECT tax.

use serde_json::Value;

use crate::cards::py_int;
use crate::game::*;
use crate::lp_phases::py_str;
use crate::lp_triggers::Ctx;
use crate::model::*;
use crate::not_ported;
use crate::registry::Spec;
use crate::types::*;

const PASSIVE_ENEMY_TARGETS: [&str; 4] = ["opponent", "enemy", "enemy_unit", "all_enemy_units_here"];
const PASSIVE_BOARD_WIDE_SCOPES: [&str; 5] = ["board", "all_battlefields", "everywhere", "global", "all"];

impl Game {
    /// py: _resolve_delayed_effects
    pub fn resolve_delayed_effects(&mut self) -> R<()> {
        if !self.gs.delayed_effects.is_empty() {
            not_ported!("_resolve_delayed_effects", "delayed 'at end of turn' effects");
        }
        Ok(())
    }

    /// py: _resolve_delayed_main
    pub fn resolve_delayed_main(&mut self, _side: Side) -> R<()> {
        if !self.gs.delayed_main.is_empty() {
            not_ported!("_resolve_delayed_main", "delayed 'start of your next main' effects");
        }
        Ok(())
    }

    /// py: _start_of_main (a step)
    pub fn start_of_main(&mut self, side: Side) -> R<()> {
        self.as_step(|g| {
            g.gs.players[0].empty_rune_pool();
            g.gs.players[1].empty_rune_pool();
            g.fire_turn_trigger("on_start_of_main", side)?;
            g.resolve_delayed_main(side)
        })
    }

    /// py: _ending_step (a step)
    pub fn ending_step(&mut self, side: Side) -> R<()> {
        self.as_step(|g| {
            g.fire_turn_trigger("on_end_of_turn", side)?;
            g.resolve_delayed_effects()
        })
    }

    /// py: _legend_unit
    pub fn legend_unit(&self, side: Side) -> Option<UnitId> {
        self.gs.legend_unit[side.idx()]
    }

    /// py: _legend_units
    pub fn legend_units(&self, side: Side) -> Vec<UnitId> {
        let mut v: Vec<UnitId> = self.legend_unit(side).into_iter().collect();
        v.extend(self.gs.added_legends[side.idx()].iter().map(|(l, _)| *l));
        v
    }

    /// py: _legend_with
    pub fn legend_with(&self, side: Side, verb: &str, ready: bool) -> Option<UnitId> {
        self.legend_units(side)
            .into_iter()
            .find(|&lu| self.has_effect(self.gs.ucard(lu), verb) && (self.gs.unit(lu).ready || !ready))
    }

    /// py: _drop_added_legends
    pub fn drop_added_legends(&mut self) {
        for s in Side::BOTH {
            let kept: Vec<(UnitId, UnitId)> = self.gs.added_legends[s.idx()]
                .iter()
                .copied()
                .filter(|(_, neeko)| self.locate_unit(*neeko).is_some())
                .collect();
            if kept.len() != self.gs.added_legends[s.idx()].len() {
                self.gs.added_legends[s.idx()] = kept;
            }
        }
    }

    /// py: _all_units_in_play
    pub fn all_units_in_play(&self) -> Vec<UnitId> {
        let mut units = Vec::new();
        for bf in &self.gs.battlefields {
            units.extend(bf.units[0].iter().copied());
            units.extend(bf.units[1].iter().copied());
        }
        units.extend(self.gs.players[0].base_units.iter().copied());
        units.extend(self.gs.players[1].base_units.iter().copied());
        units.extend(self.legend_units(Side::A));
        units.extend(self.legend_units(Side::B));
        units
    }

    /// py: _drain_rune_recycles
    pub fn drain_rune_recycles(&mut self) -> R<()> {
        for s in Side::BOTH {
            let p = self.gs.player_mut(s);
            let n = p.runes_recycled.unwrap_or(0);
            p.runes_recycled = Some(0);
            for _ in 0..n {
                self.fire_units_trigger("on_recycle_rune", s, None, None, None)?;
            }
        }
        Ok(())
    }

    /// py: _recompute_passives
    pub fn recompute_passives(&mut self) -> R<()> {
        self.drain_rune_recycles()?;
        self.drop_added_legends();
        for u in self.all_units_in_play() {
            if self.gs.unit(u).copied_from.is_some() {
                not_ported!("_recompute_passives", "copied_from (Shady Spectacles)");
            }
            let unmovable = self.gs.unit(u).gear.iter().any(|&g| self.has_effect(g, "unmovable_by_enemies"));
            let unit = self.gs.unit_mut(u);
            unit.passive_might = 0;
            unit.passive_keywords.clear();
            unit.no_combat_damage = false;
            unit.equip_bonus_mult = 1;
            unit.unchoosable = false;
            unit.no_move_to_base = false;
            unit.cant_ready = false;
            unit.spell_immune = false;
            unit.unmovable_by_enemies = unmovable;
        }
        for i in 0..self.gs.battlefields.len() {
            for side in Side::BOTH {
                for u in self.gs.battlefields[i].units_for(side).clone() {
                    self.apply_unit_passives(u, side, i, false)?;
                }
                for dg in self.gs.battlefields[i].gear[side.idx()].clone() {
                    let c = self.gs.dgear[dg.i()].card;
                    self.apply_gear_passives(c, side, i, false)?;
                }
            }
        }
        let anchor = 0usize;
        for side in Side::BOTH {
            for u in self.gs.player(side).base_units.clone() {
                self.apply_unit_passives(u, side, anchor, true)?;
            }
            for lu in self.legend_units(side) {
                self.apply_unit_passives(lu, side, anchor, true)?;
            }
            for g in self.gs.player(side).base_gear.clone() {
                if self.equip_cost(g).is_none() {
                    self.apply_gear_passives(g, side, anchor, true)?;
                }
            }
        }
        for i in 0..self.gs.battlefields.len() {
            self.apply_battlefield_passives(i)?;
            self.trim_facedowns(i)?;
        }
        for side in Side::BOTH {
            if self.gs.buff_bonus_turn.get(&side) == Some(&self.gs.turn) {
                not_ported!("_recompute_passives", "buff_bonus_turn (Stand United)");
            }
        }
        for i in 0..self.gs.battlefields.len() {
            for side in Side::BOTH {
                for &v in self.gs.battlefields[i].units_for(side) {
                    if self.has_effect(self.gs.ucard(v), "weaker_enemies_no_damage") {
                        not_ported!("_recompute_passives", "weaker_enemies_no_damage (Vilemaw)");
                    }
                }
            }
        }
        for i in 0..self.gs.battlefields.len() {
            for side in Side::BOTH {
                let mut n = 0;
                for &u in self.gs.battlefields[i].units_for(side) {
                    let unit = self.gs.unit(u);
                    for es in self.card_effects(unit.card, &unit.gear) {
                        if es.effect == "stunned_enemies_here_minus" {
                            n += es.params.get("amount").map(py_int).unwrap_or(8);
                        }
                    }
                }
                if n != 0 {
                    not_ported!("_recompute_passives", "stunned_enemies_here_minus (Leona Zealot)");
                }
            }
        }
        self.refresh_combat_keywords();
        for side in Side::BOTH {
            for u in self.friendly_units_of(side) {
                for es in self.gs.spec(self.gs.ucard(u)).effects.iter() {
                    if es.effect == "empower_at_might" && !self.gs.unit(u).empowered
                        && self.gs.unit_might(u) >= es.params.get("amount").map(py_int).unwrap_or(10)
                    {
                        not_ported!("_recompute_passives", "empower_at_might (Renekton Brute)");
                    }
                }
            }
        }
        for side in Side::BOTH {
            for u in self.friendly_units_of(side) {
                let now = self.gs.unit_might(u) >= 5;
                if now && !self.gs.unit(u).was_mighty {
                    self.gs.unit_mut(u).was_mighty = true;
                    let mut ex = Extra::default();
                    ex.set("triggering_unit", XVal::Unit(u));
                    let c = self.gs.ucard(u);
                    self.fire_units_trigger("on_friendly_becomes_mighty", side, None, Some(c), Some(ex))?;
                }
                let w = self.gs.unit(u).was_mighty && now;
                self.gs.unit_mut(u).was_mighty = w;
            }
        }
        Ok(())
    }

    /// py: _apply_battlefield_passives
    pub fn apply_battlefield_passives(&mut self, bf: usize) -> R<()> {
        let Some(card) = self.gs.battlefields[bf].card else { return Ok(()) };
        let specs: Vec<Spec> = self.gs.spec(card).effects.clone();
        for es in specs {
            if es.trigger != "passive" || !(es.effect == "grant_might" || es.effect == "give_keyword") {
                continue;
            }
            let t = es.target.clone().unwrap_or_default().to_lowercase();
            let both = t == "all_units_here" || t == "all_units" || t == "battlefield";
            let side = if both { Some(Side::A) } else { self.gs.battlefields[bf].control() };
            let Some(side) = side else { continue };
            let ex = crate::lp_phases::bf_extra(bf);
            if !self.check_condition(es.condition.as_ref(), card, side, Some(&ex))? {
                continue;
            }
            let ctx = Ctx::new(card, side, bf);
            self.apply_passive_grant(None, &ctx, &es)?;
        }
        Ok(())
    }

    /// py: _apply_unit_passives
    pub fn apply_unit_passives(&mut self, unit: UnitId, side: Side, bf: usize, in_base: bool) -> R<()> {
        let (card, gear) = (self.gs.ucard(unit), self.gs.unit(unit).gear.clone());
        let effects = self.card_effects(card, &gear);
        if effects.is_empty() {
            return self.apply_equipment_conditions(unit, side, bf);
        }
        let mut ctx = Ctx::new(card, side, bf);
        ctx.extra.set("in_base", XVal::Bool(in_base));
        for es in effects {
            if es.trigger != "passive" {
                continue;
            }
            let ex = crate::lp_phases::bf_extra(bf);
            if !self.check_condition(es.condition.as_ref(), card, side, Some(&ex))? {
                continue;
            }
            self.apply_passive_grant(Some(unit), &ctx, &es)?;
        }
        self.apply_equipment_conditions(unit, side, bf)
    }

    /// py: _apply_equipment_conditions
    pub fn apply_equipment_conditions(&mut self, unit: UnitId, side: Side, bf: usize) -> R<()> {
        for g in self.gs.unit(unit).gear.clone() {
            for es in self.gs.spec(g).effects.clone() {
                if es.effect == "give_keyword" && es.trigger == "passive" && es.condition.is_none() {
                    let kw = es.params.get("keyword").map(py_str).unwrap_or_default();
                    let kw = kw.trim();
                    if !kw.is_empty() && es.params.get("keyword").is_some() {
                        self.gs.unit_mut(unit).passive_keywords.push(kw.to_string());
                    }
                }
                if es.effect == "equip_conditional_might" {
                    let mut ex = crate::lp_phases::bf_extra(bf);
                    ex.set("gear", XVal::Card(g));
                    if self.check_condition(es.condition.as_ref(), self.gs.ucard(unit), side, Some(&ex))? {
                        let a = es.params.get("amount").map(py_int).unwrap_or(0);
                        self.gs.unit_mut(unit).passive_might += a;
                    }
                }
            }
        }
        Ok(())
    }

    /// py: _apply_gear_passives
    pub fn apply_gear_passives(&mut self, card: CardId, side: Side, bf: usize, in_base: bool) -> R<()> {
        let specs = self.gs.spec(card).effects.clone();
        if specs.is_empty() {
            return Ok(());
        }
        let mut ctx = Ctx::new(card, side, bf);
        ctx.extra.set("in_base", XVal::Bool(in_base));
        for es in specs {
            if es.trigger != "passive" {
                continue;
            }
            let ex = crate::lp_phases::bf_extra(bf);
            if !self.check_condition(es.condition.as_ref(), card, side, Some(&ex))? {
                continue;
            }
            self.apply_passive_grant(None, &ctx, &es)?;
        }
        Ok(())
    }

    /// py: _passive_targets
    pub fn passive_targets(&self, source_unit: Option<UnitId>, bf: usize, side: Side, target: Option<&str>,
                           scope: Option<&str>, in_base: bool) -> Vec<Option<UnitId>> {
        let key = target.unwrap_or("self").to_lowercase();
        if key == "self" || key == "this" {
            return vec![source_unit];
        }
        let board_wide = PASSIVE_BOARD_WIDE_SCOPES.contains(&scope.unwrap_or("").to_lowercase().as_str());
        let (friendly, enemy): (Vec<UnitId>, Vec<UnitId>) = if board_wide {
            let mut f: Vec<UnitId> = Vec::new();
            let mut e: Vec<UnitId> = Vec::new();
            for b in &self.gs.battlefields {
                f.extend(b.units_for(side).iter().copied());
            }
            f.extend(self.gs.player(side).base_units.iter().copied());
            for b in &self.gs.battlefields {
                e.extend(b.units_for(side.other()).iter().copied());
            }
            e.extend(self.gs.player(side.other()).base_units.iter().copied());
            (f, e)
        } else if in_base {
            (self.gs.player(side).base_units.clone(), Vec::new())
        } else {
            (self.gs.battlefields[bf].units_for(side).clone(), self.gs.battlefields[bf].units_for(side.other()).clone())
        };
        if key == "all_units_here" {
            return friendly.into_iter().chain(enemy).map(Some).collect();
        }
        if PASSIVE_ENEMY_TARGETS.contains(&key.as_str()) {
            return enemy.into_iter().map(Some).collect();
        }
        friendly.into_iter().map(Some).collect()
    }

    /// py: _apply_passive_grant
    pub fn apply_passive_grant(&mut self, source_unit: Option<UnitId>, ctx: &Ctx, es: &Spec) -> R<()> {
        let params = es.merged.clone();
        let side = ctx.actor;
        let bf = ctx.bf;
        let in_base = matches!(ctx.extra.get("in_base"), Some(XVal::Bool(true)));
        let mut targets = self.passive_targets(source_unit, bf, side, es.target.as_deref(), es.scope.as_deref(), in_base);
        if let Some(tf) = es.target_filter.as_ref().filter(|v| crate::cards::truthy(Some(v))) {
            let mut kept = Vec::new();
            for t in targets {
                if self.passes_filter_opt(t, tf, ctx)? {
                    kept.push(t);
                }
            }
            targets = kept;
        }
        // A None target (a "self" passive on a non-unit source) raises
        // AttributeError in Python when set: swallowed by nobody — it is an
        // error there too; here it is skipped only where Python skips it.
        let set_flag = |g: &mut Game, f: &dyn Fn(&mut Unit)| -> R<()> {
            for t in &targets {
                match t {
                    Some(u) => f(g.gs.unit_mut(*u)),
                    None => return Err(EngineError::Py("AttributeError: None passive target".into())),
                }
            }
            Ok(())
        };
        match es.effect.as_str() {
            "no_combat_damage" => return set_flag(self, &|u| u.no_combat_damage = true),
            "double_equipment_might" => return set_flag(self, &|u| u.equip_bonus_mult = 2),
            "cant_be_chosen" => return set_flag(self, &|u| u.unchoosable = true),
            "cant_move_to_base" => return set_flag(self, &|u| u.no_move_to_base = true),
            "cant_be_readied" => return set_flag(self, &|u| u.cant_ready = true),
            "prevent_enemy_spell_damage" => return set_flag(self, &|u| u.spell_immune = true),
            _ => {}
        }
        if es.effect == "give_keyword" {
            let keyword = params.get("keyword").map(py_str).unwrap_or_default().trim().to_string();
            if keyword.is_empty() || params.get("keyword").is_none() {
                return Ok(());
            }
            let src = params.get("amount_source").cloned().filter(|v| crate::cards::truthy(Some(v)));
            for t in &targets {
                let Some(u) = t else { return Err(EngineError::Py("AttributeError: None passive target".into())) };
                let n = match &src {
                    Some(Value::String(s)) if s == "own_equipment" => {
                        let gear = self.gs.unit(*u).gear.clone();
                        gear.iter().filter(|&&g| self.equip_cost(g).is_some()).count() as i64
                    }
                    Some(_) => self.effect_amount(ctx, &params)?,
                    None => {
                        self.gs.unit_mut(*u).passive_keywords.push(keyword.clone());
                        continue;
                    }
                };
                if n > 0 {
                    let head = keyword.split_whitespace().next().unwrap_or("").to_string();
                    self.gs.unit_mut(*u).passive_keywords.push(format!("{head} {n}"));
                }
            }
            return Ok(());
        }
        if matches!(es.effect.as_str(), "grant_might" | "grant_temporary_might" | "buff_unit" | "grant_temporary_might_if_alone") {
            let mut amount = self.effect_amount(ctx, &params)?;
            if es.effect == "buff_unit" && !crate::cards::truthy(params.get("amount")) {
                amount = 1;
            }
            if es.effect == "grant_temporary_might_if_alone" && self.gs.battlefields[bf].units_for(side).len() > 1 {
                return Ok(());
            }
            for t in &targets {
                let Some(u) = t else { return Err(EngineError::Py("AttributeError: None passive target".into())) };
                self.gs.unit_mut(*u).passive_might += amount;
            }
        }
        Ok(())
    }

    /// py: _bf_passive_amount(bf, verb, default=0)
    pub fn bf_passive_amount(&self, bf: Option<usize>, verb: &str, default: i64) -> i64 {
        let Some(card) = bf.and_then(|b| self.gs.battlefields[b].card) else { return default };
        for es in self.gs.spec(card).effects.iter() {
            if es.trigger == "passive" && es.effect == verb {
                return match es.params.get("amount") {
                    Some(Value::Number(n)) => n.as_i64().unwrap_or_else(|| n.as_f64().unwrap_or(0.0) as i64),
                    _ => 1,
                };
            }
        }
        default
    }

    /// py: _deflect_tax
    pub fn deflect_tax(&self, unit: UnitId, chooser: Side, source: Option<CardId>) -> R<i64> {
        let Some((ws, wbf)) = self.locate_unit(unit) else { return Ok(0) };
        if ws == chooser {
            return Ok(0);
        }
        if let Some(s) = source {
            if self.has_effect(s, "ignore_deflect") {
                return Ok(0);
            }
        }
        if wbf.is_some() && self.bf_passive_amount(wbf, "ignore_deflect_here", 0) != 0 {
            return Ok(0);
        }
        Ok(self.gs.unit_keyword_value(unit, "DEFLECT"))
    }
}
