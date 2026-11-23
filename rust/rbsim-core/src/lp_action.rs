//! py: loop.py _apply_action — one player action (a task).

use crate::agent::{AIdx, AKind, Action};
use crate::game::*;
use crate::model::*;
use crate::not_ported;
use crate::types::*;

impl Game {
    /// py: _apply_action(ap, action, cards_played_this_turn=0) (a task)
    pub fn apply_action(&mut self, ap: Side, action: &Action, cards_played: i64) -> R<()> {
        let _ = cards_played;
        self.as_task(|g| g.apply_action_body(ap, action))
    }

    fn apply_action_body(&mut self, ap: Side, action: &Action) -> R<()> {
        let kind = action.kind;
        let idx = action.index.clone();
        let mut lane = action.lane;
        let mut dst_lane = if action.len4 { action.dst } else { None };
        let n_bf = self.gs.battlefields.len() as i64;
        if !matches!(kind, AKind::Move | AKind::Ability) {
            if let Some(l) = lane {
                if !(0 <= l && l < n_bf) {
                    lane = Some(0);
                }
            }
        }
        if let Some(d) = dst_lane {
            if !(0 <= d && d < n_bf + 1) {
                dst_lane = None;
            }
        }
        let base_index = n_bf;
        if let Some((pd, _)) = self.gs.pending_move {
            if !(kind == AKind::Move && dst_lane == Some(pd as i64)) {
                return self.flush_pending_move();
            }
        }
        if kind != AKind::Move {
            self.gs.move_group = None;
        }
        let hand_idx = |g: &Game| -> Option<usize> {
            match idx {
                AIdx::Int(i) if i >= 0 && (i as usize) < g.gs.player(ap).hand.len() => Some(i as usize),
                _ => None,
            }
        };
        match kind {
            AKind::Unit => {
                if let Some(i) = hand_idx(self) {
                    let card = self.gs.player(ap).hand[i];
                    if self.gs.is_unit_card(card) || self.gs.is_legend_card(card) {
                        let dst = match dst_lane {
                            None => None,
                            Some(d) if d == base_index => None,
                            Some(d) => Some(d as usize),
                        };
                        if !self.unit_play_destinations(card, ap).contains(&dst) {
                            return Ok(());
                        }
                        let prev = dst.and_then(|d| self.gs.battlefields[d].controller());
                        let extras = self.cost_extras(card, ap)?;
                        let surcharge = self.destination_surcharge(card, dst.map(|d| d as i64), ap);
                        let (e, p) = self.effective_cost(card, ap, None)?;
                        let e = (e - self.destination_discount(card, dst.map(|d| d as i64), ap)?).max(0);
                        if !extras.is_empty() {
                            not_ported!("_apply_action", "cost extras");
                        }
                        if surcharge != 0 && !self.can_pay_generic_power(ap, surcharge + p.unwrap_or(0)) {
                            return Ok(());
                        }
                        if !self.pay_card_x(ap, card, e, p, false, None)? {
                            return Ok(());
                        }
                        if surcharge != 0 {
                            self.pay_generic_power(ap, surcharge)?;
                        }
                        self.gs.player_mut(ap).hand.retain(|&c| c != card);
                        self.play_unit(card, ap, dst, "hand")?;
                        if let Some(d) = dst {
                            self.arrive_at(d, ap, prev);
                        }
                    }
                }
            }
            AKind::Spell => {
                if let Some(i) = hand_idx(self) {
                    let card = self.gs.player(ap).hand[i];
                    if self.gs.is_spell(card) {
                        let target_lane = lane.unwrap_or(0) as usize;
                        if !self.spell_has_targets(card, ap, target_lane)? {
                            return Ok(());
                        }
                        let (e, p) = self.effective_cost(card, ap, Some(target_lane as i64))?;
                        if !self.pay_card(ap, card, e, p, Some(target_lane as i64))? {
                            return Ok(());
                        }
                        self.gs.player_mut(ap).hand.remove(i);
                        self.spell_played(card, ap, "hand")?;
                        self.put_on_chain(ChainItem {
                            player: ap,
                            card,
                            bf_idx: target_lane,
                            declared: None,
                            choices_noted: false,
                            owner: None,
                            ability: None,
                        })?;
                        self.run_chain(ap)?;
                    }
                }
            }
            AKind::Gear => {
                if let Some(i) = hand_idx(self) {
                    let card = self.gs.player(ap).hand[i];
                    if self.gs.is_gear_card(card) {
                        let (mut e, p) = self.effective_cost(card, ap, None)?;
                        if self.gs.has_keyword(card, "DEPLOY") {
                            e = (e - self.destination_discount(card, Some(lane.unwrap_or(0)), ap)?).max(0);
                        }
                        if !self.pay_card(ap, card, e, p, None)? {
                            return Ok(());
                        }
                        self.gs.player_mut(ap).hand.remove(i);
                        self.play_gear(card, ap, lane.unwrap_or(0), "hand")?;
                    }
                }
            }
            AKind::Champion => {
                let active = self.gs.active;
                let Some(champion) = self.gs.champion[active.idx()] else { return Ok(()) };
                if self.gs.champion_deployed[active.idx()] {
                    return Ok(());
                }
                let dst = match dst_lane {
                    None => None,
                    Some(d) if d == base_index => None,
                    Some(d) => Some(d as usize),
                };
                if !self.unit_play_destinations(champion, ap).contains(&dst) {
                    return Ok(());
                }
                let prev = dst.and_then(|d| self.gs.battlefields[d].controller());
                let surcharge = self.destination_surcharge(champion, dst.map(|d| d as i64), ap);
                let (e, p) = self.effective_cost(champion, ap, None)?;
                let e = (e - self.destination_discount(champion, dst.map(|d| d as i64), ap)?).max(0);
                if surcharge != 0 && !self.can_pay_generic_power(ap, surcharge + p.unwrap_or(0)) {
                    return Ok(());
                }
                if !self.pay_card(ap, champion, e, p, None)? {
                    return Ok(());
                }
                if surcharge != 0 {
                    self.pay_generic_power(ap, surcharge)?;
                }
                self.gs.champion_deployed[active.idx()] = true;
                self.play_unit(champion, ap, dst, "champion")?;
                if let Some(d) = dst {
                    self.arrive_at(d, ap, prev);
                }
            }
            AKind::Hide => {
                if let (Some(l), false) = (lane, matches!(idx, AIdx::None)) {
                    let i = match &idx {
                        AIdx::Int(i) => Some(*i),
                        AIdx::Str(s) if s == "champion" => None,
                        _ => return Ok(()),
                    };
                    self.hide_card(ap, i, l)?;
                }
            }
            AKind::HiddenPlay => {
                if let Some(l) = lane {
                    let slot = match idx {
                        AIdx::Int(i) => i,
                        _ => 0,
                    };
                    self.play_from_hidden(ap, l as usize, slot as usize)?;
                }
            }
            AKind::Move => {
                if self.gs.showdown_active || !self.gs.chain.is_empty() {
                    return Ok(());
                }
                let (Some(src), Some(dst)) = (lane, dst_lane) else { return Ok(()) };
                let n_loc = n_bf + 1;
                if src == dst || !(0..n_loc).contains(&src) || !(0..n_loc).contains(&dst) {
                    return Ok(());
                }
                let side = self.gs.active;
                let src_bf = if src == base_index { None } else { Some(src as usize) };
                let units: Vec<UnitId> = match src_bf {
                    None => self.gs.player(ap).base_units.clone(),
                    Some(s) => self.gs.battlefields[s].units_for(side).clone(),
                };
                let unit = match idx {
                    AIdx::None => units.iter().copied().find(|&u| self.gs.unit(u).ready),
                    AIdx::Int(i) if i >= 0 && (i as usize) < units.len() => Some(units[i as usize]),
                    _ => None,
                };
                let Some(unit) = unit else { return Ok(()) };
                if !self.gs.unit(unit).ready || self.gs.unit(unit).cant_move_turn == self.gs.turn {
                    return Ok(());
                }
                if src_bf.is_some() && dst != base_index && !self.can_move_bf_to_bf(unit, dst as usize) {
                    return Ok(());
                }
                if dst == base_index && !self.can_move_to_base(unit, src_bf) {
                    return Ok(());
                }
                let toll = self.group_move_toll(side, dst as usize);
                if toll != 0 && !self.pay_generic_power(ap, toll)? {
                    return Ok(());
                }
                let joining = self.gs.pending_move == Some((dst as usize, side));
                if dst != base_index && !joining && !self.pay_move_tax(side, dst as usize)? {
                    return Ok(());
                }
                match src_bf {
                    None => self.gs.player_mut(ap).base_units.retain(|&u| u != unit),
                    Some(s) => self.gs.battlefields[s].remove_unit(side, unit),
                }
                self.standard_move(unit, side, src as usize, dst as usize)?;
            }
            AKind::Ability => {
                if let AIdx::Str(s) = &idx {
                    if s == "ACTIVATED" {
                        self.apply_activated_ability(ap, lane.unwrap_or(-1))?;
                    }
                }
            }
            AKind::Pass => {}
        }
        self.flush_triggers(true)?;
        if kind != AKind::Move && self.gs.pending_move.is_some() {
            self.flush_pending_move()?;
        }
        if kind != AKind::Move {
            self.run_staged_showdowns()?;
        }
        if self.gs.chain.is_empty() {
            self.cleanup_hidden_cards()?;
        }
        Ok(())
    }
}
