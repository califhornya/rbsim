//! py: loop.py — paying and playing activated abilities, putting them on
//! the chain, resolving them; removing a unit from play.

use crate::agent::{AIdx, AKind, Action};
use crate::cards::truthy;
use crate::game::*;
use crate::lp_abilities::{AbilityEntry, ParsedCost};
use crate::lp_triggers::{is_add_verb, Ctx};
use crate::model::*;
use crate::not_ported;
use crate::registry::Spec;
use crate::types::*;

impl Game {
    /// py: _banish_from_trash
    pub fn banish_from_trash(&mut self, ap: Side, card: Option<CardId>) -> R<()> {
        if let Some(c) = card {
            if self.gs.player(ap).trash.contains(&c) {
                self.gs.player_mut(ap).trash.retain(|&x| x != c);
                self.gs.player_mut(ap).banished.push(c);
                self.note_banished(ap)?;
            }
        }
        Ok(())
    }

    /// py: _unit_ability_cost
    pub fn unit_ability_cost(&self, ap: Side, unit: UnitId, parsed: &ParsedCost) -> ParsedCost {
        let e = self.gs.player(ap).earmarked_energy_unit;
        if !self.gs.is_unit_card(self.gs.ucard(unit)) || e == 0 {
            return parsed.clone();
        }
        let mut p = parsed.clone();
        p.energy = (p.energy - e).max(0);
        p
    }

    /// py: _spend_buff(unit, side=None) — "When you spend a buff" (Fae Dragon) for its controller.
    pub fn spend_buff(&mut self, unit: UnitId, side: Option<Side>) -> R<()> {
        if self.gs.unit(unit).might_counters <= 0 {
            return Ok(());
        }
        self.gs.unit_mut(unit).might_counters -= 1;
        if self.gs.reg.regole.corrette() {
            // D75: a buff spent changes Sett Kingpin's Might at once.
            self.recompute_passives_counted(75)?;
        }
        let side = side.or_else(|| self.locate_unit(unit).map(|w| w.0));
        if let Some(s) = side {
            let mut ex = Extra::default();
            ex.set("triggering_unit", XVal::Unit(unit));
            let c = self.gs.ucard(unit);
            self.fire_units_trigger("on_buff_spent", s, None, Some(c), Some(ex))?;
        }
        Ok(())
    }

    /// py: _buff_to_spend(side, unit, who) — the unit whose buff a "spend a buff"
    /// cost takes: "self", "other" (not the source), "any": one in base first, the weakest.
    pub fn buff_to_spend(&mut self, side: Side, unit: Option<UnitId>, who: &str) -> R<Option<UnitId>> {
        if who == "self" {
            return Ok(unit.filter(|&u| self.gs.unit(u).might_counters > 0));
        }
        let cands: Vec<UnitId> = self
            .friendly_units_of(side)
            .into_iter()
            .filter(|&u| self.gs.unit(u).might_counters > 0 && !(who == "other" && Some(u) == unit))
            .collect();
        if cands.is_empty() {
            return Ok(None);
        }
        let key = |g: &Game, u: UnitId| (g.locate_unit(u).map_or(false, |w| w.1.is_some()), g.gs.unit_might(u));
        let mut best = cands[0];
        for &u in &cands[1..] {
            if key(self, u) < key(self, best) {
                best = u;
            }
        }
        let opts: Vec<Opt> = cands.iter().map(|&u| Opt::Unit(u)).collect();
        match self.choose("spend_buff", side, &opts, Opt::Unit(best), None)? {
            Opt::Unit(u) => Ok(Some(u)),
            _ => unreachable!("spend_buff chose a non-unit"),
        }
    }

    /// py: _activated_affordable(ap, unit, parsed)
    pub fn activated_affordable(&mut self, ap: Side, unit: Option<UnitId>, parsed: &ParsedCost) -> R<bool> {
        if parsed.tap && unit.map_or(false, |u| !self.gs.unit(u).ready) {
            return Ok(false);
        }
        if parsed.disempower && !unit.map_or(false, |u| self.gs.unit(u).empowered) {
            return Ok(false);
        }
        if !self.can_pay_energy_and_generic(ap, parsed.energy, parsed.power, parsed.domain) {
            return Ok(false);
        }
        if parsed.exhaust_friendly_unit.is_some() {
            not_ported!("_activated_affordable", "exhaust_friendly_unit cost");
        }
        if parsed.recycle != 0 && (self.recyclable(ap, &parsed.recycle_type).len() as i64) < parsed.recycle {
            return Ok(false);
        }
        if parsed.banish_from_trash.as_ref().map_or(false, |v| truthy(Some(v))) && self.trash_card_to_banish(ap, parsed).is_none() {
            return Ok(false);
        }
        if parsed.discard != 0 && (self.discardable(ap, parsed).len() as i64) < parsed.discard {
            return Ok(false);
        }
        if let Some(sb) = parsed.spend_buff.clone().filter(|s| !s.is_empty()) {
            if self.buff_to_spend(ap, unit, &sb)?.is_none() {
                return Ok(false);
            }
        }
        if parsed.kill_other_token || parsed.kill_other_friendly {
            not_ported!("_activated_affordable", "kill cost");
        }
        if parsed.spend_xp != 0 && self.gs.get_xp(ap) < parsed.spend_xp {
            return Ok(false);
        }
        Ok(true)
    }

    /// py: _apply_activated_ability(ap, opponent, arg)
    pub fn apply_activated_ability(&mut self, ap: Side, index: i64) -> R<()> {
        let side = ap;
        let abilities = self.activatable_abilities(side)?;
        if index < 0 || index as usize >= abilities.len() {
            return Ok(());
        }
        let entry = abilities[index as usize].clone();
        if !self.ability_usable(ap, &entry)? {
            return Ok(());
        }
        match &entry {
            AbilityEntry::Equip { gear } => {
                let gear = *gear;
                let mut cost = self.equip_cost(gear).unwrap();
                let base_energy = cost.energy;
                cost.energy = (cost.energy - self.gear_ability_discount(side)).max(0);
                if self.has_effect(gear, "equip_less_by_might") {
                    not_ported!("_apply_activated_ability", "equip_less_by_might");
                }
                if !self.pay_equip(ap, &cost)? {
                    return Ok(());
                }
                self.note_gear_ability(side);
                let units = self.friendly_units_of(side);
                if units.is_empty() {
                    return Ok(());
                }
                let base = self.equip_baseline(&units);
                let opts: Vec<Opt> = units.iter().map(|&u| Opt::Unit(u)).collect();
                let Opt::Unit(target) = self.choose("equip", side, &opts, Opt::Unit(base), Some(gear))? else { unreachable!() };
                return self.activate(side, gear, None, 0, "equip", base_energy, None, Some(target));
            }
            AbilityEntry::Flow { card } => return self.play_with_flow(*card, side),
            AbilityEntry::BanishedPlay { .. } | AbilityEntry::TrashPlay { .. } | AbilityEntry::BfAbility { .. } => {
                not_ported!("_apply_activated_ability", "{}", entry.type_name())
            }
            AbilityEntry::GearAbility { gear, eff } => {
                let (gear, eff) = (*gear, eff.clone());
                let parsed = self.parse_activated_cost(eff.cost.as_ref())?;
                let energy = (parsed.energy - self.gear_ability_discount(side)).max(0);
                if !self.pay_gear(ap, energy, Some(parsed.power), parsed.domain)? {
                    return Ok(());
                }
                self.note_gear_ability(side);
                if parsed.tap {
                    self.exhaust_gear(gear, ap)?;
                }
                if parsed.disempower {
                    not_ported!("_apply_activated_ability", "disempower gear");
                }
                self.recycle_from_trash(ap, parsed.recycle, &parsed.recycle_type)?;
                self.pay_discard_and_banish(ap, &parsed, None)?;
                if parsed.kill_friendly_gear || parsed.exhaust_friendly_unit.is_some() {
                    not_ported!("_apply_activated_ability", "gear ability kill/exhaust cost");
                }
                if parsed.spend_xp != 0 {
                    self.gs.add_xp(side, -parsed.spend_xp);
                }
                if parsed.sacrifice {
                    self.remove_gear(gear, ap)?;
                }
                if parsed.banish_self {
                    not_ported!("_apply_activated_ability", "banish_self");
                }
                if !crate::effects::exists(&eff.effect) {
                    return Ok(());
                }
                return self.activate(side, gear, Some(eff), 0, "gear_ability", parsed.energy, None, None);
            }
            AbilityEntry::Ability { unit, bf_idx, eff, copy } => {
                let (unit, eff) = (*unit, eff.clone());
                if truthy(eff.params.get("once_per_turn")) {
                    let k = Game::once_key(self.gs.ucard(unit), &eff, *copy);
                    let t = self.gs.turn;
                    self.gs.once_per_turn_used.set(k, t);
                }
                let base_energy = self.parse_activated_cost(eff.cost.as_ref())?.energy;
                let p0 = self.parse_activated_cost(eff.cost.as_ref())?;
                let mut parsed = self.adjust_ability_cost(Some(unit), &eff, &p0, side)?;
                let uc = self.unit_ability_cost(ap, unit, &parsed);
                if !self.can_pay_energy_and_generic(ap, uc.energy, parsed.power, parsed.domain) {
                    return Ok(());
                }
                if self.gs.is_unit_card(self.gs.ucard(unit)) {
                    let p = self.gs.player_mut(ap);
                    let fe = parsed.energy.min(p.earmarked_energy_unit);
                    p.earmarked_energy_unit -= fe;
                    parsed.energy -= fe;
                }
                if !self.pay_energy_and_generic(ap, parsed.energy, parsed.power, parsed.domain)? {
                    return Ok(());
                }
                if parsed.tap {
                    self.exhaust(unit, None, None)?;
                }
                if parsed.disempower {
                    not_ported!("_apply_activated_ability", "disempower");
                }
                if parsed.exhaust_friendly_unit.is_some() {
                    not_ported!("_apply_activated_ability", "exhaust_friendly_unit");
                }
                self.recycle_from_trash(ap, parsed.recycle, &parsed.recycle_type)?;
                self.pay_discard_and_banish(ap, &parsed, Some(unit))?;
                if parsed.spend_xp != 0 {
                    self.gs.add_xp(side, -parsed.spend_xp);
                }
                if parsed.sacrifice {
                    self.remove_unit_from_play(unit, side)?;
                    let c = self.gs.ucard(unit);
                    self.to_trash(ap, c)?;
                }
                if !crate::effects::exists(&eff.effect) {
                    return Ok(());
                }
                let src = self.gs.ucard(unit);
                return self.activate(side, src, Some(eff), bf_idx.unwrap_or(0), "ability", base_energy, None, None);
            }
        }
    }

    /// py: _activate(side, source, eff, bf_idx, kind, energy, extra=None, target=None)
    pub fn activate(&mut self, side: Side, source: CardId, eff: Option<Spec>, bf_idx: usize, kind: &str, energy: i64,
                    extra: Option<Extra>, target: Option<UnitId>) -> R<()> {
        let mut ab = Ability::new(kind);
        ab.eff = eff.clone();
        ab.energy = energy;
        ab.extra = extra.unwrap_or_default();
        ab.target = target;
        let item = ChainItem { uid: 0, player: side, card: source, bf_idx, declared: None, choices_noted: false, owner: None, ability: Some(ab) };
        if eff.as_ref().map_or(false, |e| is_add_verb(&e.effect)) {
            return self.resolve_ability(item);
        }
        let opened = self.gs.chain.is_empty();
        self.chained_abilities += 1;
        self.put_on_chain(item)?;
        if opened {
            self.run_chain(side)?;
        }
        Ok(())
    }

    /// py: _resolve_ability(item)
    pub fn resolve_ability(&mut self, mut item: ChainItem) -> R<()> {
        let side = item.player;
        let kind = item.ability.as_ref().unwrap().kind.clone();
        if kind == "triggered" {
            return self.resolve_trigger(&mut item);
        }
        if kind == "reflexive" {
            not_ported!("_resolve_ability", "reflexive replay");
        }
        if kind == "equip" {
            let gear = item.card;
            let unit = item.ability.as_ref().unwrap().target.unwrap();
            match self.locate_unit(unit) {
                Some((s, _)) if s == side && self.gs.player(side).base_gear.contains(&gear) => {}
                _ => return Ok(()),
            }
            self.gs.player_mut(side).base_gear.retain(|&g| g != gear);
            self.gs.unit_mut(unit).gear.push(gear);
            self.fire_attached(unit, side)?;
        } else {
            let ab = item.ability.as_ref().unwrap();
            let eff = ab.eff.clone().unwrap();
            let mut ctx = Ctx::new(item.card, side, item.bf_idx);
            ctx.extra = ab.extra.clone();
            let outer = self.slot;
            self.slot = Some([0, 0, 0]);
            let r = self.run_effect(&eff.effect, &mut ctx, &eff.merged);
            self.slot = outer;
            match r {
                Ok(()) | Err(EngineError::Ignored(_)) => {}
                Err(e) => return Err(e),
            }
        }
        let energy = item.ability.as_ref().unwrap().energy;
        self.note_ability_played(side, item.card, energy)?;
        if kind == "gear_ability" || kind == "equip" {
            self.fire_units_trigger("on_gear_ability_used", side, None, Some(item.card), None)?;
        }
        Ok(())
    }

    /// py: _use_ability_now(player, ability_id, arg) -> whether it changed the game
    pub fn use_ability_now(&mut self, player: Side, ability_id: &AIdx, arg: Option<i64>) -> R<bool> {
        let before = self.action_fingerprint(player, player.other());
        let a = Action::new(AKind::Ability, ability_id.clone(), arg, None, String::new());
        self.apply_action(player, &a, 0)?;
        self.recompute_passives()?;
        Ok(self.action_fingerprint(player, player.other()) != before)
    }

    /// py: _equip_baseline: min by (is_token, stunned, might)
    pub fn equip_baseline(&self, units: &[UnitId]) -> UnitId {
        let key = |u: UnitId| (self.gs.unit(u).is_token, self.gs.unit(u).stunned, self.gs.unit_might(u));
        let mut best = units[0];
        for &u in &units[1..] {
            if key(u) < key(best) {
                best = u;
            }
        }
        best
    }

    /// py: _first_friendly_unit_on_board
    pub fn first_friendly_unit_on_board(&self, side: Side) -> Option<UnitId> {
        for bf in &self.gs.battlefields {
            if let Some(&u) = bf.units_for(side).iter().find(|&&u| !self.gs.unit(u).is_token) {
                return Some(u);
            }
        }
        None
    }

    /// py: _remove_unit_from_play (plain list removal, no control update)
    pub fn remove_unit_from_play(&mut self, unit: UnitId, side: Side) -> R<()> {
        for bf in self.gs.battlefields.iter_mut() {
            let l = bf.units_for_mut(side);
            if let Some(p) = l.iter().position(|&u| u == unit) {
                l.remove(p);
                return Ok(());
            }
        }
        let l = &mut self.gs.player_mut(side).base_units;
        if let Some(p) = l.iter().position(|&u| u == unit) {
            l.remove(p);
        }
        Ok(())
    }
}
