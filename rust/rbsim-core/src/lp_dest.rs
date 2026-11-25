//! py: loop.py — where a unit may be played, arriving and contesting,
//! staging showdowns, AMBUSH units, entering ready.

use serde_json::{Map, Value};

use crate::cards::truthy;
use crate::game::*;
use crate::lp_phases::py_str;
use crate::model::*;
use crate::not_ported;
use crate::types::*;

impl Game {
    /// py: _unit_play_draw
    pub fn unit_play_draw(&mut self, side: Side) -> R<()> {
        if let Some(&(t, n)) = self.gs.unit_play_draws.get(&side) {
            if t == self.gs.turn && n > 0 {
                not_ported!("_unit_play_draw", "Fanfare");
            }
        }
        Ok(())
    }

    /// py: _play_permissions
    pub fn play_permissions(&self, card: CardId, side: Side) -> Vec<String> {
        let mut perms: Vec<String> = Vec::new();
        let mut add = |p: String| {
            if !perms.contains(&p) {
                perms.push(p);
            }
        };
        for es in self.gs.spec(card).effects.iter() {
            if es.effect == "play_location" {
                add(es.params.get("where").map(py_str).unwrap_or_else(|| "None".into()));
            }
        }
        for (src, _) in self.sources_in_play(side) {
            for es in self.gs.spec(src).effects.iter() {
                if es.effect == "play_location_aura" {
                    add(es.params.get("where").map(py_str).unwrap_or_else(|| "None".into()));
                }
            }
        }
        if self.gs.next_unit_any_bf.get(&side) == Some(&self.gs.turn) {
            add("any".into());
        }
        perms
    }

    /// py: _unit_play_destinations -> None (base) and battlefield indices
    pub fn unit_play_destinations(&mut self, card: CardId, side: Side) -> Vec<Option<usize>> {
        let opp = side.other();
        let perms = self.play_permissions(card, side);
        let has = |p: &str| perms.iter().any(|x| x == p);
        let only_conquered = has("conquered_this_turn_only");
        // D72 (profile 6427b90+D72-D76): "I can be played to a battlefield
        // where there are enemy units" (Rengar Trophy Hunter), from hand or the
        // Champion Zone, in the Main Phase too.
        let enemy_ok = self.gs.reg.regole.corrette() && self.ambush_enemy_ok(card);
        let mut out: Vec<Option<usize>> = if only_conquered { Vec::new() } else { vec![None] };
        if !self.units_at_battlefields_with(opp, "warden_only_base").is_empty() {
            return out;
        }
        for i in 0..self.gs.battlefields.len() {
            if let Some(bc) = self.gs.battlefields[i].card {
                if self.has_effect(bc, "no_unit_plays_here") {
                    continue;
                }
            }
            let mine = self.gs.battlefields[i].units_for(side).clone();
            let theirs = self.gs.battlefields[i].units_for(opp).clone();
            let ok = if only_conquered {
                self.gs.battlefields[i].conquered_turn.get(&side) == Some(&self.gs.turn)
            } else {
                let pets = ["Bird", "Cat", "Dog", "Poro"];
                let ctl = self.gs.battlefields[i].control();
                ctl == Some(side)
                    || has("any")
                    || (self.gs.battlefields[i].card.map_or(false, |c| self.has_effect(c, "dragon_roost"))
                        && self.gs.tags(card).iter().any(|t| t == "Dragon"))
                    || (has("pet_battlefield") && mine.iter().any(|&u| self.gs.unit_tags(u).iter().any(|t| pets.contains(&t.as_str()))))
                    || (has("open") && mine.is_empty() && theirs.is_empty() && self.gs.battlefields[i].controller().is_none())
                    || (has("occupied_enemy") && !theirs.is_empty())
                    || (has("enemy_alone") && theirs.len() == 1)
                    || (enemy_ok && !theirs.is_empty())
            };
            if ok {
                out.push(Some(i));
            }
        }
        out
    }

    /// py: _arrive_at
    pub fn arrive_at(&mut self, bf: usize, side: Side, prev_controller: Option<Side>) {
        let b = &mut self.gs.battlefields[bf];
        b.prev_controller = Some(prev_controller);
        let gained = prev_controller != Some(side) && b.controller() == Some(side);
        if gained || (!b.units[0].is_empty() && !b.units[1].is_empty()) {
            b.contested_this_turn = true;
        }
    }

    /// py: _contest
    pub fn contest(&mut self, bf: usize, side: Side, before: Option<Side>) -> R<()> {
        if self.gs.battlefields[bf].contest(side, before) {
            self.gs.battlefields[bf].contested_this_turn = true;
            self.stage_showdown(bf, side);
        }
        Ok(())
    }

    /// py: _stage_showdown
    pub fn stage_showdown(&mut self, dst: usize, side: Side) {
        let gs = &mut self.gs;
        if (gs.showdown_active && gs.showdown_bf_idx == Some(dst)) || gs.pending_move == Some((dst, side)) {
            return;
        }
        if !gs.staged_showdowns.contains(&(dst, side)) {
            gs.staged_showdowns.push((dst, side));
        }
    }

    /// py: _ambush_unit_lanes
    pub fn ambush_unit_lanes(&mut self, card: CardId, side: Side) -> Vec<usize> {
        let mut lanes: Vec<usize> = Vec::new();
        if self.gs.has_keyword(card, "AMBUSH") {
            // D72 (profile 6427b90+D72-D76): Rengar Trophy Hunter from hand
            // also where only enemy units are (as from the Champion Zone).
            let enemy_ok = self.gs.reg.regole.corrette() && self.ambush_enemy_ok(card);
            for (i, bf) in self.gs.battlefields.iter().enumerate() {
                let here = !bf.units_for(side).is_empty() || (enemy_ok && !bf.units_for(side.other()).is_empty());
                if here && !lanes.contains(&i) {
                    lanes.push(i);
                }
            }
        }
        if self.gs.has_keyword(card, "REACTION") {
            for i in 0..self.gs.battlefields.len() {
                if self.gs.battlefields[i].control() == Some(side) && !lanes.contains(&i) {
                    lanes.push(i);
                }
            }
            if self.play_permissions(card, side).iter().any(|p| p == "attacking") && self.gs.showdown_active
                && self.gs.showdown_attacker == Some(side)
            {
                if let Some(s) = self.gs.showdown_bf_idx {
                    if !lanes.contains(&s) {
                        lanes.push(s);
                    }
                }
            }
        }
        if !self.units_at_battlefields_with(side.other(), "warden_only_base").is_empty() {
            return Vec::new();
        }
        lanes.sort();
        lanes
            .into_iter()
            .filter(|&i| !self.gs.battlefields[i].card.map_or(false, |c| self.has_effect(c, "no_unit_plays_here")))
            .collect()
    }

    /// py: _play_ambush_unit(ap, idx, lane)
    pub fn play_ambush_unit(&mut self, side: Side, idx: i64, lane: i64) -> R<bool> {
        if idx < 0 || idx as usize >= self.gs.player(side).hand.len() {
            return Ok(false);
        }
        let card = self.gs.player(side).hand[idx as usize];
        if lane == self.gs.battlefields.len() as i64 {
            if !(self.gs.is_unit_card(card) && self.gs.has_keyword(card, "REACTION")) {
                return Ok(false);
            }
            let (e, p) = self.effective_cost(card, side, None)?;
            if !self.pay_card(side, card, e, p, None)? {
                return Ok(false);
            }
            self.gs.player_mut(side).hand.retain(|&c| c != card);
            self.play_unit(card, side, None, "hand")?;
            return Ok(true);
        }
        if lane < 0 || !self.ambush_unit_lanes(card, side).contains(&(lane as usize)) {
            return Ok(false);
        }
        let (e, p) = self.effective_cost(card, side, None)?;
        let e = (e - self.destination_discount(card, Some(lane), side)?).max(0);
        if !self.pay_card(side, card, e, p, None)? {
            return Ok(false);
        }
        self.gs.player_mut(side).hand.retain(|&c| c != card);
        let l = lane as usize;
        self.play_unit(card, side, Some(l), "hand")?;
        if self.gs.reg.regole.corrette() {
            // D73: the battlefield's passives (Packed Amphitheater) before
            // the showdown's first decision.
            self.recompute_passives()?;
        }
        let b = &mut self.gs.battlefields[l];
        if !b.units[0].is_empty() && !b.units[1].is_empty() {
            b.contested_this_turn = true;
            self.run_showdown(l, Some(side))?;
        }
        Ok(true)
    }

    /// py: _enters_ready(card, side, bf)
    pub fn enters_ready(&mut self, card: CardId, side: Side, bf: Option<usize>) -> R<bool> {
        if self.gs.units_enter_ready_turn[side.idx()] == self.gs.turn {
            return Ok(true);
        }
        if Side::BOTH.iter().any(|&s| self.side_has_passive(s, "others_enter_ready")) {
            return Ok(true);
        }
        for (src, src_bf) in self.sources_in_play(side) {
            if src == card {
                continue;
            }
            for es in self.gs.spec(src).effects.clone() {
                if es.trigger != "enter_ready_aura" {
                    continue;
                }
                let f = es.params.get("filter").cloned().filter(|v| truthy(Some(v))).unwrap_or(Value::Object(Map::new()));
                if !self.zone_effect_card_ok_tf(card, &f) {
                    continue;
                }
                let mut ex = crate::lp_phases::bf_extra(src_bf);
                ex.set("triggering_card", XVal::Card(card));
                ex.set("played_to", match bf { Some(b) => XVal::Bf(b), None => XVal::None });
                if self.check_condition(es.condition.as_ref(), src, side, Some(&ex))? {
                    return Ok(true);
                }
            }
        }
        Ok(false)
    }

    /// py: _enter_ready_self
    pub fn enter_ready_self(&mut self, card: CardId, side: Side, unit: UnitId, bf: Option<usize>) -> R<()> {
        if self.gs.unit(unit).ready {
            return Ok(());
        }
        for es in self.gs.spec(card).effects.clone() {
            if es.trigger != "self_enter_ready" {
                continue;
            }
            let mut ex = Extra::default();
            ex.set("battlefield", match bf { Some(b) => XVal::Bf(b), None => XVal::None });
            ex.set("played_to", match bf { Some(b) => XVal::Bf(b), None => XVal::None });
            if !self.check_condition(es.condition.as_ref(), card, side, Some(&ex))? {
                continue;
            }
            if !self.wants_optional(side, card, &es)? {
                continue;
            }
            self.gs.unit_mut(unit).ready = true;
            if es.params.get("then").map_or(false, |t| t.is_object()) {
                not_ported!("_enter_ready_self", "then");
            }
            return Ok(());
        }
        Ok(())
    }
}
