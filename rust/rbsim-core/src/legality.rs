//! py: core/legality.py — the legal actions at a decision point, in the
//! same order and with the same labels as Python.

use crate::agent::{AIdx, AKind, Action, Point};
use crate::game::Game;
use crate::lp_abilities::AbilityEntry;
use crate::types::*;

fn play(kind: AKind, idx: i64, lane: i64, label: String) -> Action {
    Action::new(kind, AIdx::Int(idx), Some(lane), None, label)
}

impl Game {
    /// py: legality.legal_actions(loop, point, player)
    pub fn legal_actions(&mut self, point: Point, player: Side) -> R<Vec<Action>> {
        match point {
            Point::TurnAction => self.turn_actions(player),
            Point::Reaction => self.reaction_actions(player),
            Point::ShowdownAction => self.showdown_actions(player),
            Point::Mulligan => Ok(Vec::new()),
        }
    }

    /// py: _affordable(loop, ap, card, lane=None, dst=None)
    pub fn affordable(&mut self, ap: Side, card: CardId, lane: Option<i64>, dst: Option<i64>) -> R<bool> {
        let (e, p) = self.effective_cost(card, ap, lane)?;
        let e = (e - self.destination_discount(card, dst, ap)?).max(0);
        let l = if self.gs.is_spell(card) { lane } else { None };
        self.can_pay_card(ap, card, e, p, true, None, l)
    }

    fn turn_actions(&mut self, side: Side) -> R<Vec<Action>> {
        let n_bf = self.gs.battlefields.len() as i64;
        let mut actions = vec![Action::pass()];
        if let Some((pd, ps)) = self.gs.pending_move {
            if ps == side {
                actions.extend(self.move_actions(side, Some(pd as i64))?);
                return Ok(actions);
            }
        }
        let hand = self.gs.player(side).hand.clone();
        for (idx, &card) in hand.iter().enumerate() {
            let idx = idx as i64;
            let name = self.gs.name(card).to_string();
            if self.gs.is_unit_card(card) || self.gs.is_legend_card(card) {
                for dst in self.unit_play_destinations(card, side) {
                    let dsti = dst.map(|d| d as i64);
                    if self.affordable(side, card, None, dsti)? {
                        let sur = self.destination_surcharge(card, dsti, side);
                        if sur != 0 {
                            let p = self.effective_cost(card, side, None)?.1.unwrap_or(0);
                            if !self.can_pay_generic_power(side, sur + p) {
                                continue;
                            }
                        }
                        match dst {
                            None => actions.push(play(AKind::Unit, idx, 0, format!("Play {name}"))),
                            Some(d) => actions.push(Action::new(AKind::Unit, AIdx::Int(idx), Some(0), Some(d as i64), format!("Play {name} to BF{d}"))),
                        }
                    }
                }
            } else if self.gs.is_spell(card) {
                for lane in 0..n_bf {
                    if self.affordable(side, card, Some(lane), None)? && self.spell_has_targets(card, side, lane as usize)? {
                        actions.push(play(AKind::Spell, idx, lane, format!("Cast {name} @BF{lane}")));
                    }
                }
            } else if self.gs.is_gear_card(card) {
                for lane in 0..n_bf {
                    let dst = if self.gs.has_keyword(card, "DEPLOY") { Some(lane) } else { None };
                    if self.affordable(side, card, None, dst)? {
                        actions.push(play(AKind::Gear, idx, lane, format!("Play gear {name} @BF{lane}")));
                    }
                }
            }
        }
        if let Some(champ) = self.gs.champion[side.idx()] {
            if !self.gs.champion_deployed[side.idx()] {
                let name = self.gs.name(champ).to_string();
                for dst in self.unit_play_destinations(champ, side) {
                    let dsti = dst.map(|d| d as i64);
                    if !self.affordable(side, champ, None, dsti)? {
                        continue;
                    }
                    let sur = self.destination_surcharge(champ, dsti, side);
                    if sur != 0 {
                        let p = self.effective_cost(champ, side, None)?.1.unwrap_or(0);
                        if !self.can_pay_generic_power(side, sur + p) {
                            continue;
                        }
                    }
                    match dst {
                        None => actions.push(Action::new(AKind::Champion, AIdx::None, Some(0), None, format!("Deploy champion {name}"))),
                        Some(d) => actions.push(Action::new(AKind::Champion, AIdx::None, Some(0), Some(d as i64), format!("Deploy champion {name} to BF{d}"))),
                    }
                }
            }
        }
        actions.extend(self.move_actions(side, None)?);
        if !self.gs.showdown_active && self.gs.chain.is_empty() {
            let hide_lanes = self.hide_lanes(side);
            if !hide_lanes.is_empty() && self.can_hide_pay(side) {
                let hand = self.gs.player(side).hand.clone();
                for (idx, &card) in hand.iter().enumerate() {
                    if self.gs.has_keyword(card, "HIDDEN") {
                        let name = self.gs.name(card).to_string();
                        for &lane in &hide_lanes {
                            actions.push(Action::new(AKind::Hide, AIdx::Int(idx as i64), Some(lane as i64), None, format!("Hide {name} @BF{lane}")));
                        }
                    }
                }
                if let Some(champ) = self.hideable_champion(side) {
                    let name = self.gs.name(champ).to_string();
                    for &lane in &hide_lanes {
                        actions.push(Action::new(AKind::Hide, AIdx::Str("champion".into()), Some(lane as i64), None, format!("Hide {name} @BF{lane}")));
                    }
                }
            }
            actions.extend(self.hidden_play_actions(side)?);
        }
        actions.extend(self.ability_actions(side)?);
        if let Some((pd, ps)) = self.gs.pending_move {
            if ps == side {
                actions.retain(|a| a.kind == AKind::Pass || (a.kind == AKind::Move && a.dst == Some(pd as i64)));
            }
        }
        Ok(actions)
    }

    /// py: _move_actions(loop, ap, only_dst=None)
    fn move_actions(&mut self, side: Side, only_dst: Option<i64>) -> R<Vec<Action>> {
        let n_bf = self.gs.battlefields.len();
        let base_index = n_bf;
        let mut out = Vec::new();
        if self.gs.showdown_active || !self.gs.chain.is_empty() {
            return Ok(out);
        }
        let where_ = |l: usize| if l == base_index { "base".to_string() } else { format!("BF{l}") };
        for src in 0..=n_bf {
            let units = if src == base_index { self.gs.player(side).base_units.clone() } else { self.gs.battlefields[src].units_for(side).clone() };
            for (ui, &u) in units.iter().enumerate() {
                if !self.gs.unit(u).ready || self.gs.unit(u).cant_move_turn == self.gs.turn {
                    continue;
                }
                for dst in 0..=n_bf {
                    if dst == src || (only_dst.is_some() && Some(dst as i64) != only_dst) {
                        continue;
                    }
                    if src != base_index && dst != base_index && !self.can_move_bf_to_bf(u, dst) {
                        continue;
                    }
                    if dst == base_index && !self.can_move_to_base(u, if src == base_index { None } else { Some(src) }) {
                        continue;
                    }
                    if !self.can_pay_generic_power(side, self.group_move_toll(side, dst)) {
                        continue;
                    }
                    let joining = self.gs.pending_move == Some((dst, side));
                    if dst != base_index && !joining && !self.can_pay_move_tax(side, dst) {
                        continue;
                    }
                    let name = self.gs.name(self.gs.ucard(u)).to_string();
                    out.push(Action::new(AKind::Move, AIdx::Int(ui as i64), Some(src as i64), Some(dst as i64),
                                         format!("Move {name} {}→{}", where_(src), where_(dst))));
                }
            }
        }
        Ok(out)
    }

    /// py: _ability_actions
    fn ability_actions(&mut self, side: Side) -> R<Vec<Action>> {
        let mut out = Vec::new();
        let entries = self.activatable_abilities(side)?;
        for (i, entry) in entries.iter().enumerate() {
            if !self.ability_usable(side, entry)? {
                continue;
            }
            let label = match entry {
                AbilityEntry::Equip { gear } => format!("Equip {}", self.gs.name(*gear)),
                AbilityEntry::Flow { card } => format!("Play {} from trash (FLOW)", self.gs.name(*card)),
                AbilityEntry::BanishedPlay { card } => format!("Play {} from banishment", self.gs.name(*card)),
                AbilityEntry::TrashPlay { card, .. } => format!("Play {} from trash", self.gs.name(*card)),
                AbilityEntry::GearAbility { gear, eff } => format!("Gear {} ({})", eff.effect, self.gs.name(*gear)),
                AbilityEntry::BfAbility { bf, eff } => format!("Battlefield {} ({})", eff.effect, self.gs.name(self.gs.battlefields[*bf].card.unwrap())),
                AbilityEntry::Ability { unit, eff, .. } => format!("Activate {} ({})", eff.effect, self.gs.name(self.gs.ucard(*unit))),
            };
            out.push(Action::new(AKind::Ability, AIdx::Str("ACTIVATED".into()), Some(i as i64), None, label));
        }
        Ok(out)
    }

    /// py: _reaction_actions
    fn reaction_actions(&mut self, side: Side) -> R<Vec<Action>> {
        let n_bf = self.gs.battlefields.len() as i64;
        let mut actions = vec![Action::pass()];
        let hand = self.gs.player(side).hand.clone();
        for (idx, &card) in hand.iter().enumerate() {
            let idx = idx as i64;
            let name = self.gs.name(card).to_string();
            if self.gs.is_spell(card) && self.has_reaction(card, side) {
                for lane in 0..n_bf {
                    if self.affordable(side, card, Some(lane), None)? && self.spell_has_targets(card, side, lane as usize)? {
                        actions.push(play(AKind::Spell, idx, lane, format!("React {name} @BF{lane}")));
                    }
                }
            } else if self.gs.is_gear_card(card) && self.play_timing(card, side) == Some("reaction") {
                for lane in 0..n_bf {
                    let dst = if self.gs.has_keyword(card, "DEPLOY") { Some(lane) } else { None };
                    if self.affordable(side, card, None, dst)? {
                        actions.push(play(AKind::Gear, idx, lane, format!("Quick-Draw {name} @BF{lane}")));
                    }
                }
            }
        }
        for (idx, &card) in hand.iter().enumerate() {
            let idx = idx as i64;
            if self.gs.is_unit_card(card) {
                let name = self.gs.name(card).to_string();
                for lane in self.ambush_unit_lanes(card, side) {
                    if self.affordable(side, card, None, Some(lane as i64))? {
                        actions.push(Action::new(AKind::Unit, AIdx::Int(idx), Some(0), Some(lane as i64), format!("AMBUSH {name} @BF{lane}")));
                    }
                }
                if self.gs.has_keyword(card, "REACTION") && self.affordable(side, card, None, None)? {
                    actions.push(Action::new(AKind::Unit, AIdx::Int(idx), Some(0), Some(n_bf), format!("React {name} to base")));
                }
            }
        }
        if let Some(champ) = self.gs.champion[side.idx()] {
            let name = self.gs.name(champ).to_string();
            for lane in self.ambush_legal_lanes(side) {
                if self.affordable(side, champ, None, Some(lane as i64))? {
                    actions.push(Action::new(AKind::Champion, AIdx::None, Some(lane as i64), None, format!("AMBUSH {name} @BF{lane}")));
                }
            }
        }
        actions.extend(self.hidden_play_actions(side)?);
        actions.extend(self.ability_actions(side)?);
        Ok(actions)
    }

    /// py: _showdown_actions
    fn showdown_actions(&mut self, side: Side) -> R<Vec<Action>> {
        let lane = self.gs.showdown_bf_idx.unwrap_or(0) as i64;
        let mut actions = vec![Action::pass()];
        let hand = self.gs.player(side).hand.clone();
        for (idx, &card) in hand.iter().enumerate() {
            let idx = idx as i64;
            let name = self.gs.name(card).to_string();
            if self.gs.is_spell(card) && (self.gs.has_keyword(card, "ACTION") || self.has_reaction(card, side)) {
                if self.affordable(side, card, Some(lane), None)? && self.spell_has_targets(card, side, lane as usize)? {
                    actions.push(play(AKind::Spell, idx, lane, format!("Showdown {name} @BF{lane}")));
                }
            } else if self.gs.is_unit_card(card) && (self.gs.has_keyword(card, "ACTION") || self.gs.has_keyword(card, "REACTION")) {
                if self.affordable(side, card, None, None)? {
                    actions.push(play(AKind::Unit, idx, lane, format!("Showdown unit {name}")));
                }
            }
            if self.gs.is_unit_card(card) {
                for dst in self.ambush_unit_lanes(card, side) {
                    if self.affordable(side, card, None, Some(dst as i64))? {
                        actions.push(Action::new(AKind::Unit, AIdx::Int(idx), Some(lane), Some(dst as i64), format!("AMBUSH {name} @BF{dst}")));
                    }
                }
            }
            if self.gs.is_gear_card(card) && matches!(self.play_timing(card, side), Some("action") | Some("reaction")) {
                let dst = if self.gs.has_keyword(card, "DEPLOY") { Some(lane) } else { None };
                if self.affordable(side, card, None, dst)? {
                    actions.push(play(AKind::Gear, idx, lane, format!("Quick-Draw {name} @BF{lane}")));
                }
            }
        }
        if let Some(champ) = self.gs.champion[side.idx()] {
            let name = self.gs.name(champ).to_string();
            for dst in self.ambush_legal_lanes(side) {
                if self.affordable(side, champ, None, Some(dst as i64))? {
                    actions.push(Action::new(AKind::Champion, AIdx::None, Some(dst as i64), None, format!("AMBUSH {name} @BF{dst}")));
                }
            }
        }
        actions.extend(self.hidden_play_actions(side)?);
        actions.extend(self.ability_actions(side)?);
        Ok(actions)
    }

    /// py: _hidden_play_actions
    fn hidden_play_actions(&mut self, side: Side) -> R<Vec<Action>> {
        let mut actions = Vec::new();
        for (lane, slot) in self.hidden_playable(side)? {
            let name = self.gs.name(self.gs.battlefields[lane].facedowns[slot].card).to_string();
            let idx = if slot == 0 { AIdx::None } else { AIdx::Int(slot as i64) };
            actions.push(Action::new(AKind::HiddenPlay, idx, Some(lane as i64), None, format!("Play {name} from Hidden @BF{lane}")));
        }
        Ok(actions)
    }
}
