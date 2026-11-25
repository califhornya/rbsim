//! py: loop.py — can a card be paid, paying it, counting it as played and
//! "when you play a card" triggers.

use serde_json::{Map, Value};

use crate::game::*;
use crate::model::*;
use crate::not_ported;
use crate::types::*;

impl Game {
    /// py: _graceful_credit — None unless a friendly unit has Irelia Graceful's discount.
    pub fn graceful_credit_any(&self, card: CardId, side: Side, lane: i64) -> R<bool> {
        if !self.gs.is_spell(card) || lane < 0 || lane as usize >= self.gs.battlefields.len() || self.dry_run
            || self.lookahead
        {
            return Ok(false);
        }
        let mut mine: Vec<UnitId> = Vec::new();
        for bf in &self.gs.battlefields {
            mine.extend(bf.units_for(side).iter().copied());
        }
        mine.extend(self.gs.player(side).base_units.iter().copied());
        if mine.iter().all(|&u| self.graceful_count(u) == 0) {
            return Ok(false);
        }
        not_ported!("_graceful_credit", "Irelia Graceful")
    }

    /// py: _can_pay_card(actor, card, energy, power, discounts=True, domain=None, lane=None)
    pub fn can_pay_card(&mut self, actor: Side, card: CardId, energy: i64, power: Option<i64>, discounts: bool,
                        domain: Option<Domain>, lane: Option<i64>) -> R<bool> {
        if self.play_forbidden(actor, card)? {
            return Ok(false);
        }
        if discounts && lane.is_some() && self.gs.is_spell(card)
            && !self.can_pay_card(actor, card, energy, power, true, domain, None)?
        {
            return self.graceful_credit_any(card, actor, lane.unwrap());
        }
        if discounts && energy > 0 && self.songstress_offer(actor, card)? {
            unreachable!();
        }
        if discounts && self.kill_discount_offered(card)? {
            unreachable!();
        }
        if discounts && self.alt_cost_offered(card)? {
            unreachable!();
        }
        let domain = domain.or(self.gs.cost_power_domain(card));
        let mut energy = energy;
        let mut power = power;
        let p = self.gs.player(actor);
        let (is_unit, is_gear_c, is_spell) = (self.gs.is_unit_card(card), self.gs.is_gear_card(card), self.gs.is_spell(card));
        if (is_unit || is_gear_c) && power.unwrap_or(0) != 0 {
            power = Some((power.unwrap() - p.earmarked_power_permanent).max(0));
        }
        if is_gear_c {
            return Ok(self.can_pay_gear(actor, energy, power, domain));
        }
        if is_spell {
            power = if power.unwrap_or(0) != 0 { Some((power.unwrap() - p.earmarked_power_spell).max(0)) } else { power };
            energy = (energy - p.earmarked_energy_spell).max(0);
        }
        if is_unit {
            energy = (energy - p.earmarked_energy_unit).max(0);
            if power.unwrap_or(0) != 0 && self.gs.is_gear(card) {
                power = Some((power.unwrap() - p.earmarked_power_gear).max(0));
            }
        }
        if power.unwrap_or(0) != 0 && domain.is_none() {
            let doms = self.power_domains(card);
            if !p.can_pay_power_of(power.unwrap(), &doms) {
                return Ok(false);
            }
            power = None;
        }
        if self.gs.showdown_active {
            return Ok(self.can_pay_showdown(actor, energy, power, domain));
        }
        Ok(self.gs.player(actor).can_pay_cost(energy, power, domain))
    }

    /// py: _pay_card(actor, card, energy, power, extras=True, lane=None)
    pub fn pay_card(&mut self, actor: Side, card: CardId, energy: i64, power: Option<i64>, lane: Option<i64>) -> R<bool> {
        self.pay_card_x(actor, card, energy, power, None, lane)
    }

    /// `extras`: None = py extras=True (chosen now), Some = already chosen (a dict, maybe empty).
    pub fn pay_card_x(&mut self, actor: Side, card: CardId, energy: i64, power: Option<i64>,
                      extras: Option<Map<String, Value>>, lane: Option<i64>) -> R<bool> {
        let (mut energy, mut power) = (energy, power);
        if !self.can_pay_card(actor, card, energy, power, true, None, lane)? {
            return Ok(false);
        }
        self.gs.card_mut(card).chosen_card = None;
        if self.gs.is_spell(card) {
            self.gs.card_mut(card).graceful_owed = Some(Vec::new());
            self.gs.card_mut(card).graceful_prepaid = Some(Value::from(0));
            if lane.is_some() && !self.can_pay_card(actor, card, energy, power, true, None, None)? {
                not_ported!("_pay_card", "Irelia Graceful credit");
            }
        }
        // _choose_alt_cost: EK has no alternate costs (alt_cost_offered checked above).
        let extras = match extras {
            Some(m) => m,
            None => {
                let ex0 = self.cost_extras(card, actor)?;
                let (ex, e2, p2) = self.choose_cost_extras(card, actor, ex0, energy, power)?;
                energy = e2;
                power = p2;
                ex
            }
        };
        // _songstress_discount / _kill_discount: not offered in EK (checked in can_pay_card).
        let domain: Option<Domain> = None;
        if !self.pay_card_cost(actor, card, energy, power, domain)? {
            self.gs.card_mut(card).graceful_owed = Some(Vec::new());
            self.gs.card_mut(card).graceful_prepaid = Some(Value::from(0));
            return Ok(false);
        }
        if !extras.is_empty() {
            self.spend_cost_extras(&extras, actor, card)?;
        }
        self.drain_rune_recycles()?;
        Ok(true)
    }

    /// py: _pay_card_cost(actor, card, energy, power, domain=None)
    pub fn pay_card_cost(&mut self, actor: Side, card: CardId, energy: i64, power: Option<i64>,
                         domain: Option<Domain>) -> R<bool> {
        // py: CoachLoop._pay_card_cost: the page's preference pays a Power with no domain of its own.
        let first = if power.unwrap_or(0) != 0 && domain.or(self.gs.cost_power_domain(card)).is_none() {
            self.preferred(actor)
        } else {
            None
        };
        if first.is_none() {
            return self.pay_card_cost_engine(actor, card, energy, power, domain);
        }
        self.gs.player_mut(actor).pay_first = first;
        let r = self.pay_card_cost_engine(actor, card, energy, power, domain);
        self.gs.player_mut(actor).pay_first = None;
        r
    }

    fn pay_card_cost_engine(&mut self, actor: Side, card: CardId, energy: i64, power: Option<i64>,
                            domain: Option<Domain>) -> R<bool> {
        let domain = domain.or(self.gs.cost_power_domain(card));
        let (is_unit, is_gear_c, is_spell) = (self.gs.is_unit_card(card), self.gs.is_gear_card(card), self.gs.is_spell(card));
        let mut energy = energy;
        let mut power = power;
        if (is_unit || is_gear_c) && power.unwrap_or(0) != 0 {
            let p = self.gs.player_mut(actor);
            let fe = power.unwrap().min(p.earmarked_power_permanent);
            p.earmarked_power_permanent -= fe;
            power = Some(power.unwrap() - fe);
        }
        if is_gear_c {
            return self.pay_gear(actor, energy, power, domain);
        }
        if is_spell {
            self.spell_energy_paid = Some(energy);
            self.spell_power_paid = Some(power.unwrap_or(0));
            let p = self.gs.player_mut(actor);
            if power.unwrap_or(0) != 0 {
                let fe = power.unwrap().min(p.earmarked_power_spell);
                p.earmarked_power_spell -= fe;
                power = Some(power.unwrap() - fe);
            }
            let fe = energy.min(p.earmarked_energy_spell);
            p.earmarked_energy_spell -= fe;
            energy -= fe;
        }
        if is_unit {
            let also_gear = self.gs.is_gear(card);
            let p = self.gs.player_mut(actor);
            let fe = energy.min(p.earmarked_energy_unit);
            p.earmarked_energy_unit -= fe;
            energy -= fe;
            if power.unwrap_or(0) != 0 && also_gear {
                let fe = power.unwrap().min(p.earmarked_power_gear);
                p.earmarked_power_gear -= fe;
                power = Some(power.unwrap() - fe);
            }
        }
        if power.unwrap_or(0) != 0 && domain.is_none() {
            let doms = self.power_domains(card);
            if !self.gs.player_mut(actor).pay_power_of(power.unwrap(), &doms) {
                return Ok(false);
            }
            power = None;
        }
        if self.gs.showdown_active {
            return Ok(self.pay_showdown(actor, energy, power, domain));
        }
        Ok(self.gs.player_mut(actor).pay_cost(energy, power, domain))
    }

    /// py: _count_card_played
    pub fn count_card_played(&mut self, card: CardId, side: Side) -> R<()> {
        if let Some(d) = self.next_card_discount(card, side) {
            let _ = d;
            not_ported!("_count_card_played", "next card discount");
        }
        self.gs.played_cards_this_turn[side.idx()].push(card);
        self.gs.cards_played_this_turn[side.idx()] += 1;
        if self.gs.is_spell(card) {
            self.gs.spells_played_this_turn[side.idx()] += 1;
        }
        Ok(())
    }

    /// py: _note_ability_played
    pub fn note_ability_played(&mut self, side: Side, source: CardId, energy: i64) -> R<()> {
        let mut ex = Extra::default();
        ex.set("ability_energy", XVal::Int(energy));
        self.fire_units_trigger("on_ability_played", side, None, Some(source), Some(ex))
    }

    /// py: _note_card_played
    pub fn note_card_played(&mut self, card: CardId, side: Side, from_zone: &str) -> R<()> {
        self.count_card_played(card, side)?;
        self.fire_card_played(side, card, from_zone)
    }

    /// py: _fire_card_played
    pub fn fire_card_played(&mut self, side: Side, card: CardId, from_zone: &str) -> R<()> {
        let sources = self.sources_in_play(side);
        let own = self.find_unit_by_card(card);
        let own_bf = own.and_then(|u| self.locate_unit(u)).and_then(|(_, b)| b).unwrap_or(0);
        let mk = |bf: usize| {
            let mut ex = crate::lp_phases::bf_extra(bf);
            ex.set("triggering_card", XVal::Card(card));
            ex.set("from_zone", XVal::Str(from_zone.to_string()));
            ex
        };
        self.resolve_triggered_effects(card, "on_self_played", own_bf, side, Some(mk(own_bf)))?;
        for src in self.gs.player(side).trash.clone() {
            self.resolve_triggered_effects(src, "trash_on_card_played", 0, side, Some(mk(0)))?;
        }
        for (src, bf) in sources {
            if src == card {
                continue;
            }
            self.resolve_triggered_effects(src, "on_card_played", bf, side, Some(mk(bf)))?;
        }
        Ok(())
    }
}
