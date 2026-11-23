//! py: loop.py — playing a card: ACCELERATE, units, gear, spells (played,
//! finalized), tokens, rally, "played here", VISION.

use serde_json::Value;

use crate::cards::truthy;
use crate::game::*;
use crate::lp_triggers::Ctx;
use crate::model::*;
use crate::not_ported;
use crate::types::*;

impl Game {
    /// py: _pay_accelerate(card, ap, granted=False)
    pub fn pay_accelerate(&mut self, card: CardId, ap: Side, granted: bool) -> R<bool> {
        if !(self.gs.has_keyword(card, "ACCELERATE") || granted) {
            return Ok(false);
        }
        let domain = self.gs.domain(card);
        let can = match domain {
            Some(d) => self.gs.player(ap).can_pay_cost(1, Some(1), Some(d)),
            None => self.gs.player(ap).energy() >= 1 && self.can_pay_generic_power(ap, 1),
        };
        if !can || !self.wants_optional_keyword(ap, card, "accelerate")? {
            return Ok(false);
        }
        match domain {
            Some(d) => {
                self.gs.player_mut(ap).pay_cost(1, Some(1), Some(d));
            }
            None => {
                let e = self.gs.player(ap).energy() - 1;
                self.gs.player_mut(ap).set_energy(e);
                self.pay_generic_power(ap, 1)?;
            }
        }
        Ok(true)
    }

    /// py: _play_unit(card, side, bf=None, ready=False, from_zone="hand", accelerate=True)
    pub fn play_unit(&mut self, card: CardId, side: Side, bf: Option<usize>, from_zone: &str) -> R<UnitId> {
        self.play_unit_x(card, side, bf, false, from_zone, true)
    }

    pub fn play_unit_x(&mut self, card: CardId, side: Side, bf: Option<usize>, ready: bool, from_zone: &str,
                       accelerate: bool) -> R<UnitId> {
        let mut ready = ready;
        let mut granted = from_zone != "hand" && self.side_has_passive(side, "accelerate_non_hand");
        if self.gs.next_unit_accelerate.get(&side) == Some(&self.gs.turn) {
            self.gs.next_unit_accelerate.pop(&side);
            granted = true;
        }
        if accelerate && self.pay_accelerate(card, side, granted)? {
            ready = true;
        }
        let last_caress = self.gs.next_unit_any_bf.get(&side) == Some(&self.gs.turn);
        if last_caress {
            self.gs.next_unit_any_bf.pop(&side);
        }
        if self.enters_ready(card, side, bf)? {
            ready = true;
        }
        if self.gs.next_units_enter_ready[side.idx()] > 0 {
            self.gs.next_units_enter_ready[side.idx()] -= 1;
            ready = true;
        }
        if self.gs.spec(card).effects.iter().any(|es| es.effect == "add_battlefield") {
            not_ported!("_add_battlefield_token", "Baron Nashor");
        }
        let enter = bf;
        let mut u = Unit::new(card);
        u.ready = ready;
        if last_caress {
            u.might_counters = u.might_counters.max(1);
        }
        let unit = self.gs.new_unit(u);
        match enter {
            None => self.gs.player_mut(side).base_units.push(unit),
            Some(b) => {
                let before = self.gs.battlefields[b].controller();
                self.gs.battlefields[b].add_unit(side, unit);
                self.contest(b, side, before)?;
            }
        }
        self.units_played += 1;
        self.try_pay_additional_costs(card, side, enter)?;
        self.show_off(card, side)?;
        self.enter_ready_self(card, side, unit, bf)?;
        self.count_card_played(card, side)?;
        self.resolve_card_effects(card, enter.unwrap_or(0), side)?;
        if self.gs.has_keyword(card, "WEAPONMASTER") {
            not_ported!("_play_unit", "WEAPONMASTER");
        }
        self.fire_units_trigger("on_friendly_unit_played", side, Some(card), None, None)?;
        self.rally(unit, side)?;
        self.fire_enemy_unit_played(unit, side)?;
        self.fire_card_played(side, card, from_zone)?;
        if self.gs.is_gear(card) {
            not_ported!("_play_unit", "a unit that is a gear too");
        }
        if let Some(b) = bf {
            self.unit_played_here(b, side, unit)?;
        }
        self.unit_play_draw(side)?;
        self.vision(card, side)?;
        Ok(unit)
    }

    /// py: _can_move_bf_to_bf
    pub fn can_move_bf_to_bf(&self, unit: UnitId, dst: usize) -> bool {
        self.gs.unit_has_keyword(unit, "GANKING")
            || self.gs.battlefields[dst].card.map_or(false, |c| self.has_effect(c, "move_here_from_anywhere"))
    }

    /// py: _vision
    pub fn vision(&mut self, card: CardId, side: Side) -> R<()> {
        let n = if self.gs.has_keyword(card, "PREDICT") { self.gs.keyword_value(card, "PREDICT") } else { 0 };
        if n == 0 || self.gs.spec(card).effects.iter().any(|es| es.effect == "predict" && es.trigger == "on_play") {
            return Ok(());
        }
        let mut ctx = Ctx::new(card, side, 0);
        let mut p = serde_json::Map::new();
        p.insert("amount".into(), Value::from(n));
        self.run_effect("predict", &mut ctx, &p)
    }

    /// py: _fire_enemy_unit_played
    pub fn fire_enemy_unit_played(&mut self, unit: UnitId, side: Side) -> R<()> {
        let mut ex = Extra::default();
        ex.set("triggering_unit", XVal::Unit(unit));
        let c = self.gs.ucard(unit);
        self.fire_units_trigger("on_enemy_unit_played", side.other(), None, Some(c), Some(ex))
    }

    /// py: _play_gear(card, side, lane=0, from_zone="hand")
    pub fn play_gear(&mut self, card: CardId, side: Side, lane: i64, from_zone: &str) -> R<()> {
        let lane = lane.max(0) as usize;
        if from_zone == "hand" {
            self.use_gear_discount(side);
        }
        let mut deployed_bf: Option<usize> = None;
        if self.gs.has_keyword(card, "DEPLOY") {
            deployed_bf = Some(lane);
        } else if self.quick_draw(card, side) {
            not_ported!("_play_gear", "QUICK-DRAW");
        }
        if let Some(d) = deployed_bf {
            self.deploy_gear(side, d, card, false)?;
            self.note_play_here(d, side, card);
        } else {
            self.gs.player_mut(side).base_gear.push(card);
        }
        let hidden_bf = if from_zone == "facedown" && deployed_bf.is_none() { Some(lane) } else { None };
        if let Some(h) = hidden_bf {
            self.note_play_here(h, side, card);
        }
        let text = self.gs.spec(card).raw.get("effect").and_then(|v| v.as_str()).unwrap_or("").to_lowercase();
        if text.contains("enters exhausted") {
            self.gs.card_mut(card).tapped = true;
        }
        let play_bf = deployed_bf.unwrap_or(lane);
        self.try_pay_additional_costs(card, side, Some(play_bf))?;
        self.show_off(card, side)?;
        self.count_card_played(card, side)?;
        self.resolve_card_effects(card, play_bf, side)?;
        self.fire_card_played(side, card, from_zone)?;
        self.vision(card, side)?;
        self.fire_units_trigger("on_enemy_gear_played", side.other(), None, Some(card), None)?;
        if let Some(d) = deployed_bf {
            let mut ex = Extra::default();
            ex.set("deployed_at", XVal::Bf(d));
            self.fire_units_trigger("on_friendly_deploy", side, None, Some(card), Some(ex))?;
            self.fire_first_play_here(side, d, card, None)?;
        }
        if let Some(h) = hidden_bf {
            self.fire_first_play_here(side, h, card, None)?;
        }
        Ok(())
    }

    /// py: _cast_spell_now
    pub fn cast_spell_now(&mut self, card: CardId, side: Side, lane: usize, from_zone: &str) -> R<()> {
        self.spell_played(card, side, from_zone)?;
        self.put_on_chain(ChainItem { player: side, card, bf_idx: lane, declared: None, choices_noted: false, owner: None, ability: None })?;
        self.run_chain(side)
    }

    /// py: _spell_played(card, ap, from_zone="hand")
    pub fn spell_played(&mut self, card: CardId, ap: Side, from_zone: &str) -> R<()> {
        let energy_before = self.gs.player(ap).energy();
        self.try_pay_additional_costs(card, ap, None)?;
        self.gs.card_mut(card).repeat_paid = Some(Value::Bool(false));
        self.gs.card_mut(card).granted_repeat = Some(Value::Bool(false));
        if self.gs.next_spell_repeat.get(&ap) == Some(&self.gs.turn) {
            not_ported!("_spell_played", "next_spell_repeat (Temporal Portal)");
        }
        if self.gs.showdown_active {
            if let Some(sb) = self.gs.showdown_bf_idx {
                if self.gs.battlefields[sb]
                    .units_for(ap)
                    .iter()
                    .any(|&u| self.has_effect(self.gs.ucard(u), "spells_repeat_in_showdown"))
                {
                    not_ported!("_spell_played", "spells_repeat_in_showdown (Syndra)");
                }
            }
        }
        self.gs.card_mut(card).repeat_extra = Some(Value::from(1));
        if self.gs.spec(card).effects.iter().any(|es| es.effect == "repeat_costs" && truthy(es.params.get("costs"))) {
            not_ported!("_spell_played", "repeat_costs (Curtain Call)");
        } else if self.gs.has_keyword(card, "REPEAT") {
            not_ported!("_spell_played", "REPEAT");
        }
        self.show_off(card, ap)?;
        if self.gs.next_spell_bonus.get(&ap) == Some(&self.gs.turn) {
            not_ported!("_spell_played", "next_spell_bonus (Ravenborn Tome)");
        }
        self.gs.card_mut(card).played_from = Some(from_zone.to_string());
        let spent = self.spell_energy_paid.unwrap_or(0) + (energy_before - self.gs.player(ap).energy()).max(0);
        self.spell_energy_paid = Some(0);
        self.gs.card_mut(card).spent = Some(spent);
        let pp = self.spell_power_paid.unwrap_or(0);
        self.gs.card_mut(card).power_paid = Some(pp);
        self.spell_power_paid = Some(0);
        self.gs.card_mut(card).graceful_from = Some(Value::Array(Vec::new()));
        self.note_card_played(card, ap, from_zone)?;
        self.gs.card_mut(card).play_pending = Some(Value::String(ap.name().into()));
        self.drain_rune_recycles()
    }

    /// py: _spell_finalized
    pub fn spell_finalized(&mut self, card: CardId) -> R<()> {
        let prepaid = self.gs.card(card).graceful_prepaid.as_ref().map(crate::cards::py_int).unwrap_or(0);
        self.gs.card_mut(card).graceful_owed = Some(Vec::new());
        self.gs.card_mut(card).graceful_prepaid = Some(Value::from(0));
        let side = self.gs.card(card).play_pending.as_ref().and_then(|v| v.as_str()).and_then(Side::from_str);
        self.gs.card_mut(card).play_pending = None;
        let Some(side) = side else { return Ok(()) };
        if prepaid > 0 {
            not_ported!("_spell_finalized", "Irelia prepaid discount");
        }
        let spent = self.gs.card(card).spent.unwrap_or(0);
        let (turn, most) = self.gs.spell_spent.get(&side).copied().unwrap_or((-1, 0));
        let t = self.gs.turn;
        self.gs.spell_spent.set(side, (t, spent.max(if turn == t { most } else { 0 })));
        self.fire_spell_played(card, side, spent)?;
        self.drain_rune_recycles()
    }

    /// py: _fire_spell_played
    pub fn fire_spell_played(&mut self, card: CardId, side: Side, spent: i64) -> R<()> {
        let mut extra = Extra::default();
        extra.set("triggering_spell_cost", XVal::Int(spent));
        self.fire_units_trigger("on_play_spell", side, Some(card), Some(card), Some(extra.clone()))?;
        for i in 0..self.gs.battlefields.len() {
            if let Some(bc) = self.gs.battlefields[i].card {
                let mut ex = crate::lp_phases::bf_extra(i);
                ex.set("triggering_card", XVal::Card(card));
                let ex = ex.merged(&extra);
                self.resolve_triggered_effects(bc, "on_play_spell", i, side, Some(ex))?;
            }
        }
        Ok(())
    }

    /// py: _play_token(name, side, bf=None, ready=False, might=None) -> unit or gear card
    pub fn play_token(&mut self, name: &str, side: Side, bf: Option<usize>, ready: bool, might: Option<i64>)
                      -> R<Option<TokenOut>> {
        let Some(spec) = self.gs.reg.index(name) else { return Ok(None) };
        let card = self.gs.new_card(spec as u32);
        self.gs.card_mut(card).is_token = Some(true);
        if let Some(m) = might {
            self.gs.card_mut(card).might_override = Some(m);
        }
        let is_gear = self.gs.is_gear_card(card);
        if !is_gear {
            if name != "Mech" && self.gs.might(card).unwrap_or(0) < 3
                && !self.units_at_battlefields_with(side, "mech_instead_of_tokens").is_empty()
            {
                not_ported!("_play_token", "mech_instead_of_tokens (Heimerdinger)");
            }
            if !self.units_at_battlefields_with(side, "double_tokens_once").is_empty() {
                not_ported!("_play_token", "double_tokens_once (Zilean)");
            }
        }
        if is_gear {
            self.gs.card_mut(card).tapped = !ready;
            if self.gs.has_keyword(card, "DEPLOY") {
                not_ported!("_play_token", "DEPLOY gear token (Bomb)");
            }
            self.gs.player_mut(side).base_gear.push(card);
            return Ok(Some(TokenOut::Gear(card)));
        }
        let mut u = Unit::new(card);
        u.ready = ready || self.enters_ready(card, side, bf)?;
        u.is_token = true;
        let unit = self.gs.new_unit(u);
        match bf {
            None => self.gs.player_mut(side).base_units.push(unit),
            Some(b) => {
                let before = self.gs.battlefields[b].controller();
                self.gs.battlefields[b].add_unit(side, unit);
                self.contest(b, side, before)?;
            }
        }
        self.fire_units_trigger("on_friendly_unit_played", side, Some(card), None, None)?;
        self.rally(unit, side)?;
        self.fire_enemy_unit_played(unit, side)?;
        if let Some(b) = bf {
            self.unit_played_here(b, side, unit)?;
        }
        self.unit_play_draw(side)?;
        Ok(Some(TokenOut::Unit(unit)))
    }

    /// py: _rally
    pub fn rally(&mut self, unit: UnitId, side: Side) -> R<()> {
        if self.gs.rally_turn.get(&side) == Some(&self.gs.turn) && self.gs.unit(unit).might_counters < 1 {
            self.gs.unit_mut(unit).might_counters = 1;
        }
        if self.gs.next_unit_ready_buff.get(&side) == Some(&self.gs.turn) {
            not_ported!("_rally", "next_unit_ready_buff (Nami Headstrong)");
        }
        Ok(())
    }

    /// py: _unit_played_here
    pub fn unit_played_here(&mut self, bf: usize, side: Side, unit: UnitId) -> R<()> {
        if !self.gs.unit(unit).is_token {
            let c = self.gs.ucard(unit);
            self.note_play_here(bf, side, c);
        }
        if let Some(bc) = self.gs.battlefields[bf].card {
            let mut ex = crate::lp_phases::bf_extra(bf);
            ex.set("triggering_unit", XVal::Unit(unit));
            self.resolve_triggered_effects(bc, "on_unit_played_here", bf, side, Some(ex))?;
            let c = self.gs.ucard(unit);
            self.fire_first_play_here(side, bf, c, Some(unit))?;
        }
        Ok(())
    }
}

/// What _play_token returns.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum TokenOut {
    Unit(UnitId),
    Gear(CardId),
}
